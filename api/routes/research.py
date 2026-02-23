"""
/api/research/* — Research & journalist query endpoints.

Provides ranking, filtering, aggregation, and export of overflow,
water quality, and bathing water data for investigative use.
"""
import csv
import io
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from api.db import pool

router = APIRouter(prefix="/research", tags=["Research"])


# ── helpers ───────────────────────────────────────────────────

def _csv_response(rows: list[dict], filename: str) -> StreamingResponse:
    """Return a list of dicts as a downloadable CSV."""
    cache_hdr = {"Cache-Control": "public, max-age=3600"}
    if not rows:
        return StreamingResponse(
            iter(["" ]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}", **cache_hdr},
        )
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}", **cache_hdr},
    )


# ── 1. National overview ─────────────────────────────────────

@router.get("/overview")
def overview():
    """High-level national summary: total overflows, spills, and per-company breakdown."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    count(DISTINCT o.unique_id)                         AS total_overflows,
                    count(DISTINCT o.unique_id)
                        FILTER (WHERE ar.counted_spills IS NOT NULL)    AS overflows_reporting,
                    coalesce(sum(ar.counted_spills), 0)                 AS total_spills,
                    round(avg(ar.counted_spills), 1)                    AS avg_spills_per_overflow,
                    max(ar.counted_spills)                              AS max_spills_single_overflow
                FROM overflows o
                LEFT JOIN overflow_annual_returns ar
                    ON ar.unique_id = o.unique_id AND ar.report_year = 2024
            """)
            r = cur.fetchone()
            national = {
                "total_overflows": r[0],
                "overflows_reporting": r[1],
                "total_spills_2024": r[2],
                "avg_spills_per_overflow": float(r[3]) if r[3] else 0,
                "max_spills_single_overflow": r[4],
                "report_year": 2024,
            }

            cur.execute("""
                SELECT
                    o.water_company_name,
                    count(DISTINCT o.unique_id)              AS overflow_count,
                    coalesce(sum(ar.counted_spills), 0)      AS total_spills,
                    round(avg(ar.counted_spills), 1)         AS avg_spills,
                    max(ar.counted_spills)                    AS max_spills
                FROM overflows o
                LEFT JOIN overflow_annual_returns ar
                    ON ar.unique_id = o.unique_id AND ar.report_year = 2024
                GROUP BY o.water_company_name
                ORDER BY total_spills DESC
            """)
            companies = [
                {
                    "company": r[0],
                    "overflow_count": r[1],
                    "total_spills": r[2],
                    "avg_spills": float(r[3]) if r[3] else 0,
                    "max_spills": r[4],
                }
                for r in cur.fetchall()
            ]

    return {
        "national": national,
        "by_company": companies,
    }


# ── 2. Filterable overflow list ──────────────────────────────

@router.get("/overflows")
def overflows_list(
    site_name: Optional[str] = Query(None, description="Filter by site name (substring match)"),
    company: Optional[str] = Query(None, description="Filter by water company (substring match)"),
    min_spills: Optional[int] = Query(None, ge=0, description="Minimum spill count"),
    max_spills: Optional[int] = Query(None, ge=0, description="Maximum spill count"),
    receiving_water: Optional[str] = Query(None, description="Filter by receiving water (substring)"),
    near_bathing: Optional[bool] = Query(None, description="Only overflows near a bathing water"),
    near_bathing_km: float = Query(2.0, ge=0.1, le=50, description="Max km to bathing water (if near_bathing=true)"),
    sort: str = Query("spills_desc", description="Sort: spills_desc, spills_asc, name"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    format: Optional[str] = Query(None, description="Set to 'csv' for CSV download"),
):
    """Filterable, sortable, paginated overflow query with optional CSV export."""
    conditions = ["1=1"]
    params: list = []

    if site_name:
        conditions.append("o.site_name_ea ILIKE %s")
        params.append(f"%{site_name}%")
    if company:
        conditions.append("o.water_company_name ILIKE %s")
        params.append(f"%{company}%")
    if min_spills is not None:
        conditions.append("ar.counted_spills >= %s")
        params.append(min_spills)
    if max_spills is not None:
        conditions.append("ar.counted_spills <= %s")
        params.append(max_spills)
    if receiving_water:
        conditions.append(
            "(o.receiving_water_canonical ILIKE %s OR o.receiving_water_name ILIKE %s)"
        )
        params.extend([f"%{receiving_water}%", f"%{receiving_water}%"])

    join_bathing = ""
    if near_bathing:
        join_bathing = f"""
            INNER JOIN v_overflow_bathing_distances vd
                ON vd.overflow_id = o.overflow_id
                AND vd.distance_m <= {int(near_bathing_km * 1000)}
        """

    sort_clause = {
        "spills_desc": "ar.counted_spills DESC NULLS LAST",
        "spills_asc": "ar.counted_spills ASC NULLS LAST",
        "name": "o.site_name_ea ASC",
    }.get(sort, "ar.counted_spills DESC NULLS LAST")

    where = " AND ".join(conditions)

    # If near_bathing, we need to deduplicate (an overflow can be near multiple bathing waters)
    distinct_clause = "DISTINCT ON (o.unique_id)" if near_bathing else ""
    # For DISTINCT ON, the ORDER BY must start with the DISTINCT column
    order_clause = f"o.unique_id, {sort_clause}" if near_bathing else sort_clause

    sql = f"""
        SELECT {distinct_clause}
            o.unique_id,
            o.site_name_ea,
            o.water_company_name,
            o.receiving_water_name,
            o.receiving_water_canonical,
            ar.counted_spills,
            ar.total_duration_text,
            ar.edm_operational_pct,
            o.asset_type
        FROM overflows o
        LEFT JOIN overflow_annual_returns ar
            ON ar.unique_id = o.unique_id AND ar.report_year = 2024
        {join_bathing}
        WHERE {where}
        ORDER BY {order_clause}
    """

    # If using DISTINCT ON, wrap in subquery to apply real sort + pagination
    if near_bathing:
        sql = f"""
            SELECT * FROM ({sql}) sub
            ORDER BY {sort_clause}
            LIMIT %s OFFSET %s
        """
    else:
        sql += " LIMIT %s OFFSET %s"

    params.extend([limit, offset])

    # Also get total count for pagination
    count_sql = f"""
        SELECT count(*)
        FROM (
            SELECT {'DISTINCT o.unique_id' if near_bathing else '1'}
            FROM overflows o
            LEFT JOIN overflow_annual_returns ar
                ON ar.unique_id = o.unique_id AND ar.report_year = 2024
            {join_bathing}
            WHERE {where}
        ) cnt
    """

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(count_sql, params[:-2] if params else [])
            total = cur.fetchone()[0]

            cur.execute(sql, params)
            rows = [
                {
                    "unique_id": r[0],
                    "site_name": r[1],
                    "water_company": r[2],
                    "receiving_water": r[3],
                    "receiving_water_normalised": r[4],
                    "spills_2024": r[5],
                    "duration_2024": r[6],
                    "edm_operational_pct": float(r[7]) if r[7] else None,
                    "asset_type": r[8],
                }
                for r in cur.fetchall()
            ]

    if format == "csv":
        return _csv_response(rows, "overflows.csv")

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "results": rows,
    }


# ── 3. Company leaderboard ───────────────────────────────────

@router.get("/companies")
def companies():
    """Water company leaderboard ranked by total spills."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    o.water_company_name,
                    count(DISTINCT o.unique_id)              AS overflow_count,
                    count(DISTINCT o.unique_id)
                        FILTER (WHERE ar.counted_spills > 0) AS overflows_with_spills,
                    coalesce(sum(ar.counted_spills), 0)      AS total_spills,
                    round(avg(ar.counted_spills), 1)         AS avg_spills,
                    max(ar.counted_spills)                    AS max_spills,
                    round(avg(ar.edm_operational_pct), 1)    AS avg_edm_operational_pct
                FROM overflows o
                LEFT JOIN overflow_annual_returns ar
                    ON ar.unique_id = o.unique_id AND ar.report_year = 2024
                GROUP BY o.water_company_name
                ORDER BY total_spills DESC
            """)
            return [
                {
                    "company": r[0],
                    "overflow_count": r[1],
                    "overflows_with_spills": r[2],
                    "total_spills": r[3],
                    "avg_spills_per_overflow": float(r[4]) if r[4] else 0,
                    "max_spills_single_overflow": r[5],
                    "avg_edm_operational_pct": float(r[6]) if r[6] else None,
                }
                for r in cur.fetchall()
            ]


# ── 4. Receiving waters ranking ──────────────────────────────

@router.get("/receiving-waters")
def receiving_waters(
    name: Optional[str] = Query(None, description="Filter by receiving water name (substring match)"),
    company: Optional[str] = Query(None, description="Filter by water company"),
    min_overflows: int = Query(1, ge=1, description="Minimum overflow count"),
    limit: int = Query(50, ge=1, le=500),
    format: Optional[str] = Query(None),
):
    """Rank receiving waters (rivers, estuaries, coasts) by overflow count and total spills."""
    conditions = ["o.receiving_water_canonical IS NOT NULL"]
    params: list = []

    if name:
        conditions.append("o.receiving_water_canonical ILIKE %s")
        params.append(f"%{name}%")
    if company:
        conditions.append("o.water_company_name ILIKE %s")
        params.append(f"%{company}%")

    where = " AND ".join(conditions)

    sql = f"""
        SELECT
            o.receiving_water_canonical   AS receiving_water,
            count(DISTINCT o.unique_id)   AS overflow_count,
            coalesce(sum(ar.counted_spills), 0) AS total_spills,
            round(avg(ar.counted_spills), 1)    AS avg_spills,
            max(ar.counted_spills)               AS max_spills,
            array_agg(DISTINCT o.water_company_name) AS companies
        FROM overflows o
        LEFT JOIN overflow_annual_returns ar
            ON ar.unique_id = o.unique_id AND ar.report_year = 2024
        WHERE {where}
        GROUP BY o.receiving_water_canonical
        HAVING count(DISTINCT o.unique_id) >= %s
        ORDER BY total_spills DESC
        LIMIT %s
    """
    params.extend([min_overflows, limit])

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = [
                {
                    "receiving_water": r[0],
                    "overflow_count": r[1],
                    "total_spills": r[2],
                    "avg_spills": float(r[3]) if r[3] else 0,
                    "max_spills": r[4],
                    "companies": r[5],
                }
                for r in cur.fetchall()
            ]

    if format == "csv":
        # Flatten companies list for CSV
        for row in rows:
            row["companies"] = "; ".join(row["companies"]) if row["companies"] else ""
        return _csv_response(rows, "receiving_waters.csv")

    return rows


# ── 5. Bathing water impact ──────────────────────────────────

@router.get("/bathing-impact")
def bathing_impact(
    name: Optional[str] = Query(None, description="Filter by bathing water name (substring match)"),
    max_distance_km: float = Query(5.0, ge=0.5, le=50, description="Max distance to consider"),
    min_spills: Optional[int] = Query(None, ge=0),
    sort: str = Query("total_spills", description="Sort: total_spills, overflow_count, name"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    format: Optional[str] = Query(None),
):
    """For each bathing water, summarise nearby overflow threat."""
    max_distance_m = int(max_distance_km * 1000)

    name_condition = ""
    if name:
        name_condition = "AND s.name ILIKE %s"

    having = ""
    params: list = [max_distance_m]
    if name:
        params.append(f"%{name}%")
    if min_spills is not None:
        having = "HAVING coalesce(sum(ar.counted_spills), 0) >= %s"
        params.append(min_spills)

    sort_clause = {
        "total_spills": "total_spills DESC",
        "overflow_count": "overflow_count DESC",
        "name": "s.name ASC",
    }.get(sort, "total_spills DESC")

    params.extend([limit, offset])

    sql = f"""
        SELECT
            s.name,
            s.eubwid,
            count(DISTINCT vd.overflow_id)                               AS overflow_count,
            count(DISTINCT vd.overflow_id) FILTER (WHERE vd.distance_m <= 1000) AS within_1km,
            count(DISTINCT vd.overflow_id) FILTER (WHERE vd.distance_m <= 2000) AS within_2km,
            coalesce(sum(ar.counted_spills), 0)                          AS total_spills,
            max(ar.counted_spills)                                       AS worst_spills,
            min(vd.distance_m)                                           AS nearest_overflow_m
        FROM sites s
        INNER JOIN v_overflow_bathing_distances vd
            ON vd.site_id = s.site_id AND vd.distance_m <= %s
        LEFT JOIN overflow_annual_returns ar
            ON ar.unique_id = vd.unique_id AND ar.report_year = 2024
        WHERE s.site_type = 'bathing_water' {name_condition}
        GROUP BY s.site_id, s.name, s.eubwid
        {having}
        ORDER BY {sort_clause}
        LIMIT %s OFFSET %s
    """

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = [
                {
                    "bathing_water": r[0],
                    "eubwid": r[1],
                    "overflow_count": r[2],
                    "within_1km": r[3],
                    "within_2km": r[4],
                    "total_nearby_spills": r[5],
                    "worst_single_overflow_spills": r[6],
                    "nearest_overflow_m": r[7],
                }
                for r in cur.fetchall()
            ]

    if format == "csv":
        return _csv_response(rows, "bathing_impact.csv")

    return {"max_distance_km": max_distance_km, "results": rows}


# ── 6. Single overflow deep-dive ─────────────────────────────

@router.get("/overflow/{unique_id}")
def overflow_detail(unique_id: str):
    """Everything about a single overflow: metadata, annual returns, nearby bathing waters."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            # Core overflow data
            cur.execute("""
                SELECT
                    o.unique_id, o.site_name_ea, o.site_name_wasc,
                    o.water_company_name, o.ea_permit_reference,
                    o.activity_reference, o.asset_type,
                    o.outlet_discharge_ngr,
                    o.receiving_water_name, o.receiving_water_canonical,
                    o.wfd_waterbody_id, o.wfd_catchment_name,
                    ST_Y(ST_Transform(o.location, 4326)),
                    ST_X(ST_Transform(o.location, 4326))
                FROM overflows o
                WHERE o.unique_id = %s
            """, (unique_id,))
            row = cur.fetchone()
            if not row:
                return {"error": "Overflow not found"}

            overflow = {
                "unique_id": row[0],
                "site_name_ea": row[1],
                "site_name_wasc": row[2],
                "water_company": row[3],
                "permit_reference": row[4],
                "activity_reference": row[5],
                "asset_type": row[6],
                "discharge_ngr": row[7],
                "receiving_water": row[8],
                "receiving_water_normalised": row[9],
                "wfd_waterbody_id": row[10],
                "wfd_catchment": row[11],
                "lat": row[12],
                "lon": row[13],
            }

            # Annual return
            cur.execute("""
                SELECT report_year, counted_spills, total_duration_text,
                       edm_operational_pct, long_term_avg_spill_count
                FROM overflow_annual_returns
                WHERE unique_id = %s
                ORDER BY report_year DESC
            """, (unique_id,))
            overflow["annual_returns"] = [
                {
                    "year": r[0],
                    "spills": r[1],
                    "duration": r[2],
                    "edm_operational_pct": float(r[3]) if r[3] else None,
                    "long_term_avg_spills": float(r[4]) if r[4] else None,
                }
                for r in cur.fetchall()
            ]

            # Nearby bathing waters
            cur.execute("""
                SELECT vd.bathing_site_name, vd.distance_m, s.eubwid
                FROM v_overflow_bathing_distances vd
                JOIN sites s ON s.site_id = vd.site_id
                WHERE vd.unique_id = %s
                ORDER BY vd.distance_m
                LIMIT 10
            """, (unique_id,))
            overflow["nearby_bathing_waters"] = [
                {"name": r[0], "distance_m": r[1], "eubwid": r[2]}
                for r in cur.fetchall()
            ]

    return overflow


# ── 7. Live overflow summary ─────────────────────────────────

@router.get("/live-summary")
def live_summary():
    """Current live discharge counts and recent event statistics from NSOH polling."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            # Currently discharging (seen within last 45 min, no end)
            cur.execute("""
                SELECT count(*) FROM nsoh_events
                WHERE event_end IS NULL
                  AND last_seen_at >= now() - interval '45 minutes'
            """)
            currently = cur.fetchone()[0]

            # Last 12 hours
            cur.execute("""
                SELECT count(*) FROM nsoh_events
                WHERE event_start >= now() - interval '12 hours'
            """)
            last_12h = cur.fetchone()[0]

            # Month-to-date
            cur.execute("""
                SELECT count(*) FROM nsoh_events
                WHERE event_start >= date_trunc('month', now())
            """)
            mtd = cur.fetchone()[0]

            # Year-to-date
            cur.execute("""
                SELECT count(*) FROM nsoh_events
                WHERE event_start >= date_trunc('year', now())
            """)
            ytd = cur.fetchone()[0]

            # Last polled
            cur.execute("SELECT max(polled_at) FROM nsoh_snapshots")
            last_polled = cur.fetchone()[0]

    return {
        "currently_discharging": currently,
        "last_12h": last_12h,
        "month_to_date": mtd,
        "year_to_date": ytd,
        "last_polled": last_polled.isoformat() if last_polled else None,
    }
