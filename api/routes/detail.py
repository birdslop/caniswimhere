"""
/api/site/detail — swim spot deep-dive endpoint.

Given a lat/lon, synthesises:
  1. Nearest WIMS sampling point + recent water quality readings
  2. Overflow threat summary (counts, spills within 1km / 2km)
  3. Traffic-light verdict (green / amber / red) with plain-English summary

Optionally enriches with EA official bathing water risk prediction
if a designated bathing water is nearby.
"""
import asyncio
import csv
import io
import logging
import httpx
from datetime import date, timedelta, datetime, timezone
from fastapi import APIRouter, Query, HTTPException
from api.db import pool
from api.routes.research import _normalise_duration

log = logging.getLogger(__name__)

router = APIRouter()

# ── Key WIMS determinand codes for swim safety ────────────────
# Multiple codes map to the same logical determinand (different lab methods).
SWIM_DETERMINANDS = {
    # E. coli / faecal coliforms
    "0936": "E. coli",
    "0937": "E. coli",
    "0938": "E. coli",
    "0939": "E. coli",
    "2348": "E. coli",  # Confirmed : MF (bathing water method)
    "3458": "E. coli",
    "3461": "E. coli",
    # Enterococci / faecal streptococci
    "0942": "Enterococci",
    "2551": "Enterococci",
    "3722": "Enterococci",  # Intestinal: Presumptive: MF
    "3723": "Enterococci",  # Intestinal: Confirmed: MF
    "6423": "Enterococci",
    # Total coliforms
    "2331": "Total coliforms",
    "0940": "Total coliforms",
    "0941": "Total coliforms",
    # General water quality
    "0076": "Water temperature",
    "0061": "pH",
    "0111": "Ammonia",
    "0068": "Turbidity",
    "0067": "Transparency",
    "0085": "BOD",
    "0082": "Dissolved oxygen",
    "0078": "Dissolved oxygen",
}

# EU Bathing Water Directive thresholds (cfu/100ml, 95th percentile)
BWD_THRESHOLDS = {
    "E. coli": {"excellent": 250, "good": 500, "sufficient": 900},
    "Enterococci": {"excellent": 100, "good": 200, "sufficient": 330},
}

EA_TIMEOUT = 5.5
WIMS_TIMEOUT = 10.0   # WIMS CSV can take a few seconds for large stations
NSOH_TIMEOUT = 4.0
WIMS_BASE = "https://environment.data.gov.uk/water-quality"
WIMS_CSV_HEADERS = {"Accept": "text/csv"}
EA_FLOOD_BASE = "https://environment.data.gov.uk/flood-monitoring"
EA_JSON_HEADERS = {"Accept": "application/json"}

# ── NSOH config (shared with polling scripts) ────────────────
from api.nsoh_config import NSOH_DEFAULT_FIELDS as _NSOH_DEFAULT_FIELDS, NSOH_ENDPOINTS

STALE_DAYS = 180          # >6 months = stale
VERY_STALE_DAYS = 365     # >1 year = very stale


def _parse_csv_observation(row: dict) -> dict | None:
    """Parse a single row from WIMS CSV response into a reading dict."""
    det_code = row.get("determinand.notation", "")
    if det_code not in SWIM_DETERMINANDS:
        return None
    raw_result = (row.get("result") or "").strip()
    if not raw_result:
        return None
    # Below-detection-limit results start with '<'
    below_limit = raw_result.startswith("<")
    try:
        value = float(raw_result.lstrip("<"))
    except (ValueError, TypeError):
        return None
    unit = row.get("unit", "")
    obs_time = row.get("phenomenonTime") or ""
    return {
        "determinand": SWIM_DETERMINANDS[det_code],
        "determinand_code": det_code,
        "value": value,
        "unit": unit,
        "display_value": f"<{value:g}" if below_limit else f"{value:g}",
        "below_limit": below_limit,
        "date": obs_time[:10],
    }


def _assess_reading(determinand: str, value: float) -> str:
    """Return 'good', 'moderate', or 'poor' for a single reading."""
    thresholds = BWD_THRESHOLDS.get(determinand)
    if not thresholds:
        return "unknown"
    if value <= thresholds["excellent"]:
        return "excellent"
    if value <= thresholds["good"]:
        return "good"
    if value <= thresholds["sufficient"]:
        return "sufficient"
    return "poor"


def _data_freshness(readings: list) -> dict:
    """Compute freshness metadata from a list of readings."""
    if not readings:
        return {"status": "no_data", "newest_date": None, "age_days": None}
    newest = max(r["date"] for r in readings)
    try:
        age = (date.today() - date.fromisoformat(newest)).days
    except ValueError:
        return {"status": "unknown", "newest_date": newest, "age_days": None}
    if age > VERY_STALE_DAYS:
        status = "very_stale"
    elif age > STALE_DAYS:
        status = "stale"
    else:
        status = "recent"
    return {"status": status, "newest_date": newest, "age_days": age}


def _build_verdict(
    readings: list, overflow_summary: dict, freshness: dict,
    rainfall: dict | None = None, live_overflows: list | None = None,
) -> dict:
    """Synthesise a traffic-light verdict from readings + overflow data + rainfall + live status."""
    reasons = []
    level = "green"  # start optimistic

    # ── Live overflow status (NSOH near-real-time) ────────────
    if live_overflows:
        active = [o for o in live_overflows if o.get("status_code") == 1]
        recent_24h = [
            o for o in live_overflows
            if o.get("last_spill_hours_ago") is not None
            and o["last_spill_hours_ago"] <= 24
            and o.get("distance_m", 99999) <= 2000
        ]
        active_nearby = [o for o in active if o.get("distance_m", 99999) <= 2000]
        if active_nearby:
            level = "red"
            reasons.append(
                f"{len(active_nearby)} overflow{'s' if len(active_nearby) != 1 else ''} "
                f"within 2 km currently discharging sewage."
            )
        elif recent_24h:
            level = max(level, "amber", key=["green", "amber", "red"].index)
            reasons.append(
                f"{len(recent_24h)} nearby overflow{'s' if len(recent_24h) != 1 else ''} "
                f"discharged in the last 24 hours."
            )

    # ── Overflow threat (annual return 2024) ──────────────────
    within_1km = overflow_summary.get("within_1km", 0)
    total_spills = overflow_summary.get("total_spills_1km", 0)

    if within_1km > 0 and total_spills > 50:
        level = "red"
        reasons.append(
            f"{within_1km} overflow{'s' if within_1km != 1 else ''} within 1 km "
            f"discharged {total_spills} times in 2024."
        )
    elif within_1km > 0 and total_spills > 10:
        level = max(level, "amber", key=["green", "amber", "red"].index)
        reasons.append(
            f"{within_1km} overflow{'s' if within_1km != 1 else ''} within 1 km "
            f"with {total_spills} spills in 2024."
        )
    elif overflow_summary.get("within_2km", 0) > 0:
        spills_2km = overflow_summary.get("total_spills_2km", 0)
        if spills_2km > 20:
            level = max(level, "amber", key=["green", "amber", "red"].index)
            reasons.append(
                f"{overflow_summary['within_2km']} overflows within 2 km "
                f"({spills_2km} total spills in 2024)."
            )

    # ── Data staleness ────────────────────────────────────────
    fs = freshness.get("status", "no_data")
    if fs == "very_stale":
        level = max(level, "amber", key=["green", "amber", "red"].index)
        age_yrs = round(freshness["age_days"] / 365, 1)
        reasons.append(
            f"Water quality data is {age_yrs} years old — treat with caution."
        )
    elif fs == "stale":
        age_months = round((freshness.get("age_days") or 0) / 30)
        reasons.append(
            f"Note: newest water quality reading is ~{age_months} months old."
        )

    # ── Recent rainfall ───────────────────────────────────────
    if rainfall:
        r6 = rainfall.get("last_6h_mm") or 0.0
        r24 = rainfall.get("last_24h_mm") or 0.0
        if r6 >= 10 or r24 >= 25:
            # Very heavy recent rain → likely runoff risk
            level = max(level, "red", key=["green", "amber", "red"].index)
            reasons.append(
                f"Heavy rain in the last 24h (~{r24:.1f} mm) — high runoff risk."
            )
        elif r6 >= 3 or r24 >= 10:
            level = max(level, "amber", key=["green", "amber", "red"].index)
            reasons.append(
                f"Recent rain (~{r6:.1f} mm/6h, {r24:.1f} mm/24h) may reduce water quality."
            )

    # ── Water quality readings ────────────────────────────────
    # Only let readings influence the verdict if they are fresh (<=6 months)
    data_trustworthy = fs == "recent"
    ecoli = [r for r in readings if r["determinand"] == "E. coli"]
    enterococci = [r for r in readings if r["determinand"] == "Enterococci"]

    for label, data in [("E. coli", ecoli), ("Enterococci", enterococci)]:
        if not data:
            continue
        latest = data[0]
        display = latest.get("display_value", str(latest["value"]))
        assessment = _assess_reading(label, latest["value"])
        if assessment == "poor" and data_trustworthy:
            level = "red"
            reasons.append(
                f"Latest {label} reading: {display} {latest['unit']} "
                f"({latest['date']}) — exceeds safe limits."
            )
        elif assessment == "sufficient" and data_trustworthy:
            level = max(level, "amber", key=["green", "amber", "red"].index)
            reasons.append(
                f"Latest {label} reading: {display} {latest['unit']} "
                f"({latest['date']}) — elevated."
            )
        else:
            reasons.append(
                f"Latest {label} reading: {display} {latest['unit']} "
                f"({latest['date']}) — {assessment}."
            )

    if not readings:
        if within_1km == 0:
            reasons.append("No water quality readings available nearby.")
        level = max(level, "amber", key=["green", "amber", "red"].index)

    if not reasons:
        reasons.append("No nearby overflows and no recent water quality concerns.")

    return {
        "level": level,
        "summary": " ".join(reasons),
    }


@router.get("/site/detail")
async def site_detail(
    lat: float = Query(..., description="Latitude (WGS84)"),
    lon: float = Query(..., description="Longitude (WGS84)"),
):
    """Deep-dive into water quality and safety at a specific location."""
    point = f"ST_SetSRID(ST_MakePoint({lon}, {lat}), 4326)"

    with pool.connection() as conn:
        with conn.cursor() as cur:
            # ── 1. Find nearest WIMS sampling point (prefer freshwater/bathing) ──
            cur.execute(f"""
                SELECT notation, label, sp_type,
                       ST_Y(location) AS lat, ST_X(location) AS lon,
                       round(ST_Distance(
                           location::geography,
                           {point}::geography
                       ))::int AS distance_m
                FROM wq_sampling_points
                WHERE sp_type IN (
                    'FRESHWATER - RIVERS',
                    'FRESHWATER - LAKES/PONDS/RESERVOIRS',
                    'FRESHWATER - UNSPECIFIED',
                    'SALINE WATER - DESIGNATED BATHING BEACHES',
                    'SALINE WATER - NON DESIGNATED BATHING BEACHES',
                    'SALINE WATER - ESTUARINE SITES - NON BATHING/SHELLFISH'
                )
                AND ST_DWithin(location::geography, {point}::geography, 5000)
                ORDER BY distance_m
                LIMIT 1
            """)
            sp_row = cur.fetchone()

            # Fallback: try any type within 5km
            if not sp_row:
                cur.execute(f"""
                    SELECT notation, label, sp_type,
                           ST_Y(location) AS lat, ST_X(location) AS lon,
                           round(ST_Distance(
                               location::geography,
                               {point}::geography
                           ))::int AS distance_m
                    FROM wq_sampling_points
                    WHERE ST_DWithin(location::geography, {point}::geography, 5000)
                    ORDER BY distance_m
                    LIMIT 1
                """)
                sp_row = cur.fetchone()

            nearest_sp = None
            if sp_row:
                nearest_sp = {
                    "notation": sp_row[0],
                    "name": sp_row[1],
                    "type": sp_row[2],
                    "lat": sp_row[3],
                    "lon": sp_row[4],
                    "distance_m": sp_row[5],
                }

            # ── 2. Overflow threat summary ───────────────────────
            cur.execute(f"""
                SELECT
                    count(*) FILTER (WHERE dist <= 1000) AS within_1km,
                    count(*) FILTER (WHERE dist <= 2000) AS within_2km,
                    count(*) AS within_5km,
                    coalesce(sum(ar.counted_spills) FILTER (WHERE dist <= 1000), 0) AS spills_1km,
                    coalesce(sum(ar.counted_spills) FILTER (WHERE dist <= 2000), 0) AS spills_2km,
                    coalesce(sum(ar.counted_spills), 0) AS spills_5km
                FROM (
                    SELECT o.overflow_id, o.unique_id,
                           round(ST_Distance(
                               ST_Transform(o.location, 4326)::geography,
                               {point}::geography
                           ))::int AS dist
                    FROM overflows o
                    WHERE o.location IS NOT NULL
                      AND ST_DWithin(
                          ST_Transform(o.location, 4326)::geography,
                          {point}::geography, 5000)
                ) sub
                LEFT JOIN overflow_annual_returns ar
                    ON ar.unique_id = sub.unique_id AND ar.report_year = 2024
            """)
            ov_row = cur.fetchone()
            overflow_summary = {
                "within_1km": ov_row[0],
                "within_2km": ov_row[1],
                "within_5km": ov_row[2],
                "total_spills_1km": ov_row[3],
                "total_spills_2km": ov_row[4],
                "total_spills_5km": ov_row[5],
            }

            # ── 3. Worst nearby overflows (top 5 by spills) ─────
            cur.execute(f"""
                SELECT o.site_name_ea, o.water_company_name,
                       o.receiving_water_name,
                       ar.counted_spills, ar.total_duration_text,
                       round(ST_Distance(
                           ST_Transform(o.location, 4326)::geography,
                           {point}::geography
                       ))::int AS distance_m
                FROM overflows o
                LEFT JOIN overflow_annual_returns ar
                    ON ar.unique_id = o.unique_id AND ar.report_year = 2024
                WHERE o.location IS NOT NULL
                  AND ST_DWithin(
                      ST_Transform(o.location, 4326)::geography,
                      {point}::geography, 5000)
                ORDER BY ar.counted_spills DESC NULLS LAST
                LIMIT 5
            """)
            worst_overflows = [
                {
                    "name": r[0],
                    "water_company": r[1],
                    "receiving_water": r[2],
                    "spills_2024": r[3],
                    "duration_2024": _normalise_duration(r[4]),
                    "distance_m": r[5],
                }
                for r in cur.fetchall()
            ]

            # ── 4. Check for nearby designated bathing water ────
            cur.execute(f"""
                SELECT site_id, name, eubwid,
                       round(ST_Distance(
                           location::geography,
                           {point}::geography
                       ))::int AS distance_m
                FROM sites
                WHERE site_type = 'bathing_water'
                  AND ST_DWithin(location::geography, {point}::geography, 2000)
                ORDER BY distance_m
                LIMIT 1
            """)
            bw_row = cur.fetchone()
            bathing_water = None
            if bw_row:
                bathing_water = {
                    "site_id": str(bw_row[0]),
                    "name": bw_row[1],
                    "eubwid": bw_row[2],
                    "distance_m": bw_row[3],
                }

    # ── 5–6: Fetch remote datasets concurrently for speed ────
    async def fetch_wims():
        """Fetch water quality readings from EA WIMS API using fast CSV format."""
        readings_local = []
        if not nearest_sp:
            return readings_local
        notation = nearest_sp["notation"]
        date_windows = [
            date.today() - timedelta(days=730),   # last 2 years
            date.today() - timedelta(days=1825),  # last 5 years
            None,                                  # all time
        ]
        try:
            async with httpx.AsyncClient(timeout=WIMS_TIMEOUT) as client:
                for from_date in date_windows:
                    url = (
                        f"{WIMS_BASE}/sampling-point/{notation}"
                        f"/observation?limit=250"
                    )
                    if from_date:
                        url += f"&dateFrom={from_date.isoformat()}"
                    resp = await client.get(url, headers=WIMS_CSV_HEADERS)
                    if resp.status_code != 200:
                        log.warning("WIMS %s returned %s", url, resp.status_code)
                        continue
                    # Parse CSV response
                    reader = csv.DictReader(io.StringIO(resp.text))
                    parsed = []
                    for row in reader:
                        p = _parse_csv_observation(row)
                        if p:
                            parsed.append(p)
                    if parsed:
                        seen = {}
                        for r in parsed:
                            key = r["determinand"]
                            if key not in seen or r["date"] > seen[key]["date"]:
                                seen[key] = r
                        readings_local = sorted(seen.values(), key=lambda x: x["determinand"])
                        break
        except Exception as exc:
            log.warning("WIMS fetch failed for %s: %s", notation, exc)
        return readings_local

    async def fetch_bathing():
        if not (bathing_water and bathing_water.get("eubwid")):
            return None
        try:
            bwq_url = (
                "https://environment.data.gov.uk/doc/bathing-water-quality"
                f"/in-season/latest.json"
                f"?bathingWater.eubwidNotation={bathing_water['eubwid']}"
            )
            async with httpx.AsyncClient(timeout=EA_TIMEOUT) as client:
                resp = await client.get(bwq_url)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", data.get("result", {}).get("items", []))
                if items:
                    item = items[0]
                    return {
                        "classification": (
                            item.get("sampleClassification", {}).get("label")
                            or item.get("latestComplianceAssessment", {})
                            .get("complianceClassification", {})
                            .get("label")
                        ),
                        "risk_level": (
                            item.get("riskPrediction", {}).get("riskLevel", {}).get("label")
                        ),
                        "source": "EA Bathing Water Quality API",
                    }
        except Exception:
            return None
        return None

    async def fetch_rainfall():
        rainfall_local = None
        try:
            async with httpx.AsyncClient(timeout=EA_TIMEOUT) as client:
                for dist_km in (20, 40, 80):
                    stations_url = (
                        f"{EA_FLOOD_BASE}/id/stations?parameter=rainfall&lat={lat}&long={lon}&dist={dist_km}&_limit=10"
                    )
                    s_resp = await client.get(stations_url, headers=EA_JSON_HEADERS)
                    if s_resp.status_code != 200:
                        continue
                    s_items = s_resp.json().get("items", [])
                    station_ids = [
                        it.get("stationReference") or (it.get("@id", "").rsplit("/",1)[-1])
                        for it in s_items
                    ]
                    station_ids = [sid for sid in station_ids if sid][:1]
                    if not station_ids:
                        continue
                    since_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
                    totals_6, totals_24 = [], []
                    for sid in station_ids:
                        r_url = f"{EA_FLOOD_BASE}/id/stations/{sid}/readings?since={since_24h}&_sorted"
                        r_resp = await client.get(r_url, headers=EA_JSON_HEADERS)
                        if r_resp.status_code != 200:
                            continue
                        items = r_resp.json().get("items", [])
                        vals = [(it.get("dateTime"), it.get("value")) for it in items if it.get("value") is not None]
                        if not vals:
                            continue
                        now = datetime.now(timezone.utc)
                        total_24 = 0.0
                        total_6 = 0.0
                        for dt_str, v in vals:
                            try:
                                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                            except Exception:
                                continue
                            h_ago = (now - dt).total_seconds() / 3600.0
                            if h_ago <= 24.01:
                                total_24 += float(v)
                                if h_ago <= 6.01:
                                    total_6 += float(v)
                        totals_24.append(total_24)
                        totals_6.append(total_6)
                    if totals_24:
                        def median(xs):
                            ys = sorted(xs)
                            n = len(ys)
                            return ys[n//2] if n % 2 == 1 else (ys[n//2-1] + ys[n//2]) / 2
                        rainfall_local = {
                            "last_6h_mm": round(median(totals_6), 2),
                            "last_24h_mm": round(median(totals_24), 2),
                            "station_count": len(totals_24),
                        }
                        return rainfall_local
                # Fallback to measures
                measures_url = (
                    f"{EA_FLOOD_BASE}/id/measures?parameter=rainfall&lat={lat}&long={lon}&dist=80&_limit=50"
                )
                m_resp = await client.get(measures_url, headers=EA_JSON_HEADERS)
                items = m_resp.json().get("items", []) if m_resp.status_code == 200 else []
                station_measures = {}
                for it in items:
                    sid = it.get("stationReference") or (it.get("station") or {}).get("@id", "").rsplit("/",1)[-1]
                    mid = it.get("@id")
                    if sid and mid and sid not in station_measures:
                        station_measures[sid] = mid
                        if len(station_measures) >= 1:
                            break
                if station_measures:
                    since_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
                    totals_6, totals_24 = [], []
                    for sid, mid in station_measures.items():
                        r_url = f"{EA_FLOOD_BASE}/id/measures/{mid.rsplit('/',1)[-1]}/readings?since={since_24h}&_sorted"
                        r_resp = await client.get(r_url, headers=EA_JSON_HEADERS)
                        if r_resp.status_code != 200:
                            continue
                        r_items = r_resp.json().get("items", [])
                        vals = [(it.get("dateTime"), it.get("value")) for it in r_items if it.get("value") is not None]
                        if not vals:
                            continue
                        now = datetime.now(timezone.utc)
                        total_24 = 0.0
                        total_6 = 0.0
                        for dt_str, v in vals:
                            try:
                                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                            except Exception:
                                continue
                            h_ago = (now - dt).total_seconds() / 3600.0
                            if h_ago <= 24.01:
                                total_24 += float(v)
                                if h_ago <= 6.01:
                                    total_6 += float(v)
                        totals_24.append(total_24)
                        totals_6.append(total_6)
                    if totals_24:
                        def median(xs):
                            ys = sorted(xs)
                            n = len(ys)
                            return ys[n//2] if n % 2 == 1 else (ys[n//2-1] + ys[n//2]) / 2
                        rainfall_local = {
                            "last_6h_mm": round(median(totals_6), 2),
                            "last_24h_mm": round(median(totals_24), 2),
                            "station_count": len(totals_24),
                        }
        except Exception:
            return None
        return rainfall_local

    async def fetch_live_overflows():
        """Query all NSOH endpoints in parallel for nearby live overflow status."""
        # Build bounding box ~5km around the point
        # ~0.045 degrees latitude ≈ 5km; longitude adjusted for lat
        import math
        dlat = 0.045
        dlon = 0.045 / max(math.cos(math.radians(lat)), 0.5)
        bbox = f"{lon - dlon},{lat - dlat},{lon + dlon},{lat + dlat}"
        async def _query_one(company_name: str, endpoint: str, field_map: dict | None = None):
            fm = field_map or _NSOH_DEFAULT_FIELDS
            out_fields = ",".join(fm.values())
            try:
                params = (
                    f"?geometry={bbox}"
                    f"&geometryType=esriGeometryEnvelope"
                    f"&inSR=4326"
                    f"&outFields={out_fields}"
                    f"&returnGeometry=false"
                    f"&resultRecordCount=20"
                    f"&f=json"
                )
                async with httpx.AsyncClient(timeout=NSOH_TIMEOUT) as client:
                    resp = await client.get(endpoint + "/query" + params)
                if resp.status_code != 200:
                    return []
                data = resp.json()
                results = []
                now_ms = datetime.now(timezone.utc).timestamp() * 1000
                for feat in data.get("features", []):
                    a = feat.get("attributes", {})
                    status_code = a.get(fm["status"])
                    status_label = (
                        "Discharging" if status_code == 1
                        else "Offline" if status_code == -1
                        else "Not discharging"
                    )
                    # Compute distance (approximate)
                    flat = a.get(fm["lat"]) or 0
                    flon = a.get(fm["lon"]) or 0
                    dist_km = math.sqrt(
                        ((flat - lat) * 111.32) ** 2
                        + ((flon - lon) * 111.32 * math.cos(math.radians(lat))) ** 2
                    )
                    # Parse latest event timestamps
                    evt_start = a.get(fm["event_start"])
                    evt_end = a.get(fm["event_end"])
                    last_spill_ago = None
                    if evt_end and evt_end > 0:
                        hours_ago = (now_ms - evt_end) / 3_600_000
                        last_spill_ago = round(hours_ago, 1)
                    results.append({
                        "id": a.get(fm["id"]),
                        "company": a.get(fm["company"]) or company_name,
                        "status": status_label,
                        "status_code": status_code,
                        "receiving_water": a.get(fm["receiving_water"]),
                        "latest_event_start": (
                            datetime.fromtimestamp(evt_start / 1000, tz=timezone.utc).isoformat()
                            if evt_start and evt_start > 0 else None
                        ),
                        "latest_event_end": (
                            datetime.fromtimestamp(evt_end / 1000, tz=timezone.utc).isoformat()
                            if evt_end and evt_end > 0 else None
                        ),
                        "last_spill_hours_ago": last_spill_ago,
                        "distance_m": round(dist_km * 1000),
                        "lat": flat,
                        "lon": flon,
                    })
                return results
            except Exception:
                return []

        tasks = [_query_one(name, url, fm) for name, url, fm in NSOH_ENDPOINTS]
        all_results = await asyncio.gather(*tasks)
        combined = []
        for batch in all_results:
            combined.extend(batch)
        combined.sort(key=lambda x: x["distance_m"])
        return combined[:15]

    readings, bathing_assessment, rainfall_summary, live_overflows = await asyncio.gather(
        fetch_wims(), fetch_bathing(), fetch_rainfall(), fetch_live_overflows()
    )

    # ── 7. Build verdict ─────────────────────────────────────
    freshness = _data_freshness(readings)
    verdict = _build_verdict(
        readings, overflow_summary, freshness, rainfall_summary,
        live_overflows=live_overflows,
    )

    return {
        "location": {"lat": lat, "lon": lon},
        "nearest_sampling_point": nearest_sp,
        "water_quality": {
            "readings": readings,
            "reading_count": len(readings),
            "freshness": freshness,
        },
        "rainfall": rainfall_summary,
        "overflow_threat": {
            "summary": overflow_summary,
            "worst_overflows": worst_overflows,
        },
        "live_overflows": live_overflows,
        "bathing_water": bathing_water,
        "bathing_assessment": bathing_assessment,
        "verdict": verdict,
    }
