"""
/api/overview — lightweight national overview for the map.

Returns all bathing waters and overflows with minimal fields so the
frontend can render clustered markers on initial page load.
"""
from fastapi import APIRouter
from api.db import pool

router = APIRouter(tags=["Swim Map"])


@router.get("/overview")
def overview():
    """All bathing waters and overflows — minimal fields for map clusters."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            # ── Bathing waters (~581 rows) ──────────────────────
            cur.execute("""
                SELECT name, eubwid, latest_risk_level,
                       ST_Y(location) AS lat, ST_X(location) AS lon
                FROM sites
                WHERE site_type = 'bathing_water'
                  AND location IS NOT NULL
            """)
            bathing = [
                {
                    "name": r[0],
                    "eubwid": r[1],
                    "classification": r[2],
                    "lat": r[3],
                    "lon": r[4],
                }
                for r in cur.fetchall()
            ]

            # ── Overflows (~18k rows) ───────────────────────────
            cur.execute("""
                SELECT o.site_name_ea,
                       o.unique_id,
                       o.water_company_name,
                       ST_Y(ST_Transform(o.location, 4326)) AS lat,
                       ST_X(ST_Transform(o.location, 4326)) AS lon,
                       ar.counted_spills
                FROM overflows o
                LEFT JOIN overflow_annual_returns ar
                  ON ar.unique_id = o.unique_id AND ar.report_year = 2024
                WHERE o.location IS NOT NULL
            """)
            overflows = [
                {
                    "name": r[0],
                    "id": r[1],
                    "company": r[2],
                    "lat": r[3],
                    "lon": r[4],
                    "spills": r[5],
                }
                for r in cur.fetchall()
            ]

    return {
        "bathing_waters": bathing,
        "overflows": overflows,
    }
