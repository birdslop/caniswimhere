import requests
import psycopg2
from psycopg2.extras import Json
from datetime import datetime

EA_BATHING_WATER_URL = "https://environment.data.gov.uk/doc/bathing-water.json"

# Phase 1 Thames definition (strict, non-inferential):
# Only include bathing waters explicitly named as being on the River Thames.
THAMES_NAME_SUBSTRING = "river thames"

def is_thames_bathing_water(item: dict) -> bool:
    name = item.get("name", {}).get("_value", "")
    return THAMES_NAME_SUBSTRING in name.lower()

def fetch_all_items():
    items = []
    page = 0
    while True:
        data = requests.get(f"{EA_BATHING_WATER_URL}?_page={page}").json()
        result = data["result"]
        items.extend(result.get("items", []))
        if not result.get("next"):
            break
        page += 1
    return items

def main():
    items = fetch_all_items()

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
        "Bathing Water Quality",
        EA_BATHING_WATER_URL,
        "Open Government Licence v3.0",
        datetime.utcnow(),
        Json({"fetched_pages": "all", "fetched_items": len(items)})
    ))
    source_id = cur.fetchone()[0]

    inserted = 0

    for item in items:
        if not is_thames_bathing_water(item):
            continue

        sp = item.get("samplingPoint", {})
        lat = sp.get("lat")
        lon = sp.get("long")

        if lat is None or lon is None:
            continue

        cur.execute("""
            INSERT INTO sites (
                site_type,
                name,
                location,
                waterbody_name,
                catchment_name,
                source_id,
                raw_metadata
            )
            VALUES (
                %s,
                %s,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                %s,
                %s,
                %s,
                %s
            )
        """, (
            "bathing_water",
            item.get("name", {}).get("_value"),
            float(lon),
            float(lat),
            None,
            None,
            source_id,
            Json(item)
        ))

        inserted += 1

    conn.commit()
    cur.close()
    conn.close()

    print(f"Fetched {len(items)} bathing water records total.")
    print(f"Inserted {inserted} Thames bathing water sites.")

if __name__ == "__main__":
    main()
