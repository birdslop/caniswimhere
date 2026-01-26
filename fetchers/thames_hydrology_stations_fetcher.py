import requests
import psycopg2
from psycopg2.extras import Json
from datetime import datetime

HYDRO_STATIONS_URL = "https://environment.data.gov.uk/hydrology/id/stations.json"

def to_text(x):
    if isinstance(x, str):
        return x
    if isinstance(x, list):
        return " ".join(str(i) for i in x)
    return ""

def is_thames_station(it: dict) -> bool:
    river = to_text(it.get("riverName")).lower()
    return "thames" in river

def main():
    data = requests.get(HYDRO_STATIONS_URL, params={"_limit": 10000}, timeout=30).json()
    items = data["items"]

    thames_items = [it for it in items if is_thames_station(it)]

    conn = psycopg2.connect(dbname="water_quality")
    cur = conn.cursor()

    # provenance
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
        "Hydrology Stations (Thames subset)",
        HYDRO_STATIONS_URL,
        "Open Government Licence v3.0",
        datetime.utcnow(),
        Json({"total_stations": len(items), "thames_stations": len(thames_items), "_limit": 10000})
    ))
    source_id = cur.fetchone()[0]

    inserted_stations = 0
    inserted_measures = 0

    for it in thames_items:
        # Hydrology stations use GUID-style identifiers; we store notation as station_reference
        station_ref = it.get("notation") or it.get("stationGuid") or it.get("@id")
        label = it.get("label")

        lat = it.get("lat")
        lon = it.get("long")

        if not station_ref or not label or lat is None or lon is None:
            continue

        # Insert station (idempotent via UNIQUE station_reference)
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
            float(lon),
            float(lat),
            source_id,
            Json(it)
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
                None,   # hydrology station->measures does not include parameterName in this view
                None,   # unitName not present here; will exist on measures endpoint if needed later
                m.get("period"),
                None,   # qualifier not present here
                Json(m)
            ))

            if cur.rowcount == 1:
                inserted_measures += 1

    conn.commit()
    cur.close()
    conn.close()

    print(f"Inserted {inserted_stations} Thames hydrology stations.")
    print(f"Inserted {inserted_measures} hydrology measures.")

if __name__ == "__main__":
    main()
