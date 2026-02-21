#!/usr/bin/env python3
"""
Ingest ALL EA flood monitoring stations and their measures (national).

Based on thames_stations_fetcher.py but with no river-name filter.
Idempotent: safe to re-run (ON CONFLICT DO NOTHING).
"""
import requests
import psycopg2
from psycopg2.extras import Json
from datetime import datetime, timezone

STATIONS_URL = "https://environment.data.gov.uk/flood-monitoring/id/stations.json"


def to_text(x):
    if isinstance(x, str):
        return x
    if isinstance(x, list):
        return " ".join(str(i) for i in x)
    return ""


def first_float(v):
    """EA API sometimes returns lists for lat/lon. Take first value."""
    if isinstance(v, list):
        v = v[0] if v else None
    if v is None:
        return None
    return float(v)


def main():
    print("Fetching all flood monitoring stations...")
    data = requests.get(STATIONS_URL, timeout=120).json()
    items = data["items"]
    print(f"  Retrieved {len(items)} stations from API.")

    conn = psycopg2.connect(dbname="water_quality")
    cur = conn.cursor()

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
        "Flood Monitoring Stations (National)",
        STATIONS_URL,
        "Open Government Licence v3.0",
        datetime.now(timezone.utc),
        Json({"total_stations": len(items)}),
    ))
    source_id = cur.fetchone()[0]

    inserted_stations = 0
    inserted_measures = 0
    skipped = 0

    for it in items:
        station_ref = it.get("stationReference") or it.get("notation")
        label = it.get("label")
        lat = first_float(it.get("lat"))
        lon = first_float(it.get("long"))

        if not station_ref or not label or lat is None or lon is None:
            skipped += 1
            continue

        cur.execute("""
            INSERT INTO stations (
                station_reference,
                label,
                river_name,
                catchment_name,
                location,
                source_id,
                raw_metadata
            )
            VALUES (%s, %s, %s, %s,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                    %s, %s)
            ON CONFLICT (station_reference) DO NOTHING
        """, (
            station_ref,
            label,
            to_text(it.get("riverName")),
            to_text(it.get("catchmentName")),
            lon,
            lat,
            source_id,
            Json(it),
        ))

        if cur.rowcount == 1:
            inserted_stations += 1

        # Fetch station_id for measures insertion
        cur.execute("SELECT station_id FROM stations WHERE station_reference = %s", (station_ref,))
        station_id = cur.fetchone()[0]

        for m in it.get("measures", []):
            measure_ref = m.get("@id")
            if not measure_ref:
                continue

            cur.execute("""
                INSERT INTO measures (
                    station_id,
                    measure_ref,
                    parameter,
                    parameter_name,
                    unit_name,
                    period_seconds,
                    qualifier,
                    raw_metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (measure_ref) DO NOTHING
            """, (
                station_id,
                measure_ref,
                m.get("parameter"),
                m.get("parameterName"),
                m.get("unitName"),
                m.get("period"),
                m.get("qualifier"),
                Json(m),
            ))

            if cur.rowcount == 1:
                inserted_measures += 1

    conn.commit()
    cur.close()
    conn.close()

    print(f"Inserted {inserted_stations} stations (national).")
    print(f"Inserted {inserted_measures} measures.")
    print(f"Skipped (missing ref/label/lat/lon): {skipped}")


if __name__ == "__main__":
    main()
