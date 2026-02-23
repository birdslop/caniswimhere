"""
/api/nearby — spatial proximity endpoint.

Given a lat/lon, returns everything relevant within a radius:
  - Designated bathing waters (sites)
  - Recreation swim spots (recreation_sites)
  - Storm overflows (overflows)
  - Water quality sampling points (wq_sampling_points)
  - Monitoring stations (stations)
"""
from fastapi import APIRouter, Query
from api.db import pool

router = APIRouter(tags=["Swim Map"])

# Default / max radius in metres
DEFAULT_RADIUS = 5000
MAX_RADIUS = 25000


@router.get("/nearby")
def nearby(
    lat: float = Query(..., ge=-90, le=90, description="Latitude (WGS84)"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude (WGS84)"),
    radius: int = Query(DEFAULT_RADIUS, ge=100, le=MAX_RADIUS,
                        description="Search radius in metres"),
):
    """Return all features within *radius* metres of the given point."""
    point_wgs84 = f"ST_SetSRID(ST_MakePoint({lon}, {lat}), 4326)"

    with pool.connection() as conn:
        with conn.cursor() as cur:
            results = {}

            # ── Designated bathing waters ───────────────────────
            cur.execute(f"""
                SELECT site_id, name, eubwid,
                       ST_Y(location) AS lat, ST_X(location) AS lon,
                       latest_risk_level,
                       round(ST_Distance(
                           location::geography,
                           {point_wgs84}::geography
                       ))::int AS distance_m
                FROM sites
                WHERE site_type = 'bathing_water'
                  AND ST_DWithin(
                      location::geography,
                      {point_wgs84}::geography,
                      %s)
                ORDER BY distance_m
            """, (radius,))
            results["bathing_waters"] = [
                {
                    "site_id": str(r[0]), "name": r[1], "eubwid": r[2],
                    "lat": r[3], "lon": r[4],
                    "risk_level": r[5], "distance_m": r[6],
                }
                for r in cur.fetchall()
            ]

            # ── Recreation swim spots ───────────────────────────
            cur.execute(f"""
                SELECT rec_site_id, location_id, recreation_types,
                       swimming, num_data_sources,
                       near_designated_bathing,
                       ST_Y(location) AS lat, ST_X(location) AS lon,
                       round(ST_Distance(
                           location::geography,
                           {point_wgs84}::geography
                       ))::int AS distance_m
                FROM recreation_sites
                WHERE ST_DWithin(
                    location::geography,
                    {point_wgs84}::geography,
                    %s)
                ORDER BY distance_m
            """, (radius,))
            results["recreation_sites"] = [
                {
                    "rec_site_id": str(r[0]),
                    "location_id": r[1],
                    "recreation_types": r[2],
                    "swimming": r[3],
                    "num_data_sources": r[4],
                    "near_designated_bathing": r[5],
                    "lat": r[6], "lon": r[7],
                    "distance_m": r[8],
                }
                for r in cur.fetchall()
            ]

            # ── Storm overflows ─────────────────────────────────
            cur.execute(f"""
                SELECT o.overflow_id, o.unique_id,
                       o.site_name_ea, o.receiving_water_name,
                       o.water_company_name,
                       ST_Y(ST_Transform(o.location, 4326)) AS lat,
                       ST_X(ST_Transform(o.location, 4326)) AS lon,
                       ar.counted_spills, ar.total_duration_text,
                       round(ST_Distance(
                           ST_Transform(o.location, 4326)::geography,
                           {point_wgs84}::geography
                       ))::int AS distance_m
                FROM overflows o
                LEFT JOIN overflow_annual_returns ar
                  ON ar.unique_id = o.unique_id AND ar.report_year = 2024
                WHERE o.location IS NOT NULL
                  AND ST_DWithin(
                      ST_Transform(o.location, 4326)::geography,
                      {point_wgs84}::geography,
                      %s)
                ORDER BY distance_m
                LIMIT 50
            """, (radius,))
            results["overflows"] = [
                {
                    "overflow_id": str(r[0]),
                    "unique_id": r[1],
                    "site_name": r[2],
                    "receiving_water": r[3],
                    "water_company": r[4],
                    "lat": r[5], "lon": r[6],
                    "spills_2024": r[7],
                    "duration_2024": r[8],
                    "distance_m": r[9],
                }
                for r in cur.fetchall()
            ]

            # ── Water quality sampling points ───────────────────
            cur.execute(f"""
                SELECT sp_id, notation, label, sp_type, sp_status,
                       ST_Y(location) AS lat, ST_X(location) AS lon,
                       round(ST_Distance(
                           location::geography,
                           {point_wgs84}::geography
                       ))::int AS distance_m
                FROM wq_sampling_points
                WHERE ST_DWithin(
                    location::geography,
                    {point_wgs84}::geography,
                    %s)
                ORDER BY distance_m
                LIMIT 50
            """, (radius,))
            results["sampling_points"] = [
                {
                    "sp_id": str(r[0]),
                    "notation": r[1],
                    "name": r[2],
                    "type": r[3],
                    "status": r[4],
                    "lat": r[5], "lon": r[6],
                    "distance_m": r[7],
                }
                for r in cur.fetchall()
            ]

            # ── Monitoring stations ─────────────────────────────
            cur.execute(f"""
                SELECT station_id, station_reference, label,
                       river_name,
                       ST_Y(location) AS lat, ST_X(location) AS lon,
                       round(ST_Distance(
                           location::geography,
                           {point_wgs84}::geography
                       ))::int AS distance_m
                FROM stations
                WHERE ST_DWithin(
                    location::geography,
                    {point_wgs84}::geography,
                    %s)
                ORDER BY distance_m
                LIMIT 30
            """, (radius,))
            results["stations"] = [
                {
                    "station_id": str(r[0]),
                    "reference": r[1],
                    "name": r[2],
                    "river": r[3],
                    "lat": r[4], "lon": r[5],
                    "distance_m": r[6],
                }
                for r in cur.fetchall()
            ]

    results["query"] = {
        "lat": lat, "lon": lon, "radius_m": radius,
    }
    return results
