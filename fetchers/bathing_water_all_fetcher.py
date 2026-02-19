#!/usr/bin/env python3
import requests
import psycopg2
from psycopg2.extras import Json
from datetime import datetime, timezone

EA_BATHING_WATER_URL = "https://environment.data.gov.uk/doc/bathing-water.json"

def as_text(v) -> str:
    """
    EA fields often look like {"_value": "...", "_lang": "en"}.
    Sometimes they're plain strings. Sometimes None.
    """
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        # most common EA pattern
        if "_value" in v and isinstance(v["_value"], str):
            return v["_value"]
        # fallback: some dicts might have "name": {...}
        if "name" in v:
            return as_text(v.get("name"))
    return str(v)

def parse_sampling_point_id(sampling_point_about: str) -> str:
    # e.g. http://location.data.gov.uk/so/ef/SamplingPoint/bwsp.eaew/11700
    if not sampling_point_about:
        return ""
    return sampling_point_about.rstrip("/").split("/")[-1]

def fetch_all_items() -> tuple[list[dict], dict]:
    """
    Fetch all items from EA /doc/bathing-water.json with pagination.
    Returns (items, meta) where meta includes pages_fetched and items_total.
    """
    items: list[dict] = []
    page = 1
    pages_fetched = 0

    while True:
        url = f"{EA_BATHING_WATER_URL}?_page={page}"
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        j = r.json()

        result = j.get("result") or {}
        page_items = result.get("items") or []
        items.extend(page_items)
        pages_fetched += 1

        nxt = result.get("next")
        if not nxt:
            break
        page += 1

    meta = {"pages_fetched": pages_fetched, "items_total": len(items)}
    return items, meta

def main():
    items, meta = fetch_all_items()

    conn = psycopg2.connect(dbname="water_quality")
    cur = conn.cursor()

    # 1) create a source row for this fetch run
    cur.execute("""
        INSERT INTO sources (
            provider,
            dataset_name,
            source_url,
            license,
            fetched_at,
            raw_metadata
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING source_id
    """, (
        "Environment Agency",
        "Bathing Water (EA Bathing Water Profiles / API)",
        EA_BATHING_WATER_URL,
        "Open Government Licence v3.0",
        datetime.now(timezone.utc),
        Json(meta),
    ))
    source_id = cur.fetchone()[0]

    inserted = 0
    updated = 0
    skipped_no_samplingpoint = 0
    skipped_no_latlon = 0
    errors = 0

    for item in items:
        try:
            # Key identifiers
            eubwid = as_text(item.get("eubwidNotation")).strip()
            # Name can be dict in EA JSON; label may be None
            name = as_text(item.get("name") or item.get("label")).strip()

            sp = item.get("samplingPoint") or {}
            sp_about = as_text(sp.get("_about")).strip()
            sp_id = parse_sampling_point_id(sp_about).strip()

            lat = sp.get("lat")
            lon = sp.get("long")

            latest_profile_url = as_text(item.get("latestProfile")).strip()

            # latestRiskPrediction is a dict, with "_about" + expiresAt + riskLevel
            lrp = item.get("latestRiskPrediction") or {}
            latest_risk_url = as_text(lrp.get("_about")).strip()

            expires_at_raw = None
            expires_at = lrp.get("expiresAt")
            if isinstance(expires_at, dict):
                expires_at_raw = expires_at.get("_value")
            # keep as string; we’ll let Postgres cast text->timestamptz safely
            latest_risk_expires_at = expires_at_raw

            risk_level = ""
            rl = lrp.get("riskLevel")
            if isinstance(rl, dict):
                risk_level = as_text(rl.get("name")).strip()

            # We require sampling point lat/lon to build geometry (most have it)
            if not sp:
                skipped_no_samplingpoint += 1
                continue
            if lat is None or lon is None:
                skipped_no_latlon += 1
                continue

            # If eubwid is missing, we still can store, but it’s our stable key.
            # Practically, EA provides it for all designated bathing waters.
            if not eubwid:
                # Fallback keying becomes messy; skip rather than corrupt.
                errors += 1
                continue

            # 2) update-if-exists by (site_type, eubwid), else insert
            cur.execute("""
                UPDATE sites
                SET
                  name = %s,
                  location = ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                  eubwid = %s,
                  sampling_point_id = %s,
                  sampling_point_url = %s,
                  latest_profile_url = %s,
                  latest_risk_prediction_url = %s,
                  latest_risk_expires_at = %s::timestamptz,
                  latest_risk_level = %s,
                  source_id = %s,
                  raw_metadata = %s
                WHERE site_type = 'bathing_water'
                  AND eubwid = %s
            """, (
                name,
                float(lon), float(lat),
                eubwid,
                sp_id or None,
                sp_about or None,
                latest_profile_url or None,
                latest_risk_url or None,
                latest_risk_expires_at,
                risk_level or None,
                source_id,
                Json(item),
                eubwid,
            ))

            if cur.rowcount == 1:
                updated += 1
                continue

            # Insert new row
            cur.execute("""
                INSERT INTO sites (
                  site_type,
                  name,
                  location,
                  eubwid,
                  sampling_point_id,
                  sampling_point_url,
                  latest_profile_url,
                  latest_risk_prediction_url,
                  latest_risk_expires_at,
                  latest_risk_level,
                  source_id,
                  raw_metadata
                )
                VALUES (
                  'bathing_water',
                  %s,
                  ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                  %s,
                  %s,
                  %s,
                  %s,
                  %s,
                  %s::timestamptz,
                  %s,
                  %s,
                  %s
                )
            """, (
                name,
                float(lon), float(lat),
                eubwid,
                sp_id or None,
                sp_about or None,
                latest_profile_url or None,
                latest_risk_url or None,
                latest_risk_expires_at,
                risk_level or None,
                source_id,
                Json(item),
            ))
            inserted += 1

        except Exception:
            errors += 1
            continue

    conn.commit()
    cur.close()
    conn.close()

    print(f"Fetched {len(items)} bathing water records total.")
    print(f"Pages fetched: {meta.get('pages_fetched')}")
    print(f"Inserted: {inserted}")
    print(f"Updated: {updated}")
    print(f"Skipped (no samplingPoint): {skipped_no_samplingpoint}")
    print(f"Skipped (no lat/lon): {skipped_no_latlon}")
    print(f"Errors: {errors}")

if __name__ == "__main__":
    main()
