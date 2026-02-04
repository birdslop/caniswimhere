#!/usr/bin/env python3
import os
import requests
import psycopg2
from psycopg2.extras import Json
from datetime import datetime, timezone

EA_BATHING_WATER_URL = "https://environment.data.gov.uk/doc/bathing-water.json"

def fetch_all_items(url: str) -> list[dict]:
    items = []
    next_url = url

    while next_url:
        r = requests.get(next_url, timeout=60)
        r.raise_for_status()
        data = r.json()
        batch = data.get("result", {}).get("items", [])
        if isinstance(batch, list):
            items.extend(batch)
        next_url = data.get("result", {}).get("next")

    return items

def normalise_label(value) -> str:
    """
    EA API sometimes returns labels as strings,
    sometimes as dicts with '_value'.
    """
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("_value", "")).strip()
    return ""

def main() -> None:
    dbname = os.environ.get("DB_NAME", "water_quality")
    conn = psycopg2.connect(dbname=dbname)
    conn.autocommit = False

    items = fetch_all_items(EA_BATHING_WATER_URL)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sources (
                provider,
                dataset_name,
                source_url,
                license,
                fetched_at,
                raw_metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING source_id;
            """,
            (
                "Environment Agency",
                "Bathing Water (EA Bathing Water Profiles / API)",
                EA_BATHING_WATER_URL,
                "Open Government Licence v3.0",
                datetime.now(timezone.utc),
                Json({"fetched_pages": "all", "fetched_items": len(items)}),
            ),
        )
        source_id = cur.fetchone()[0]

        inserted = 0

        for item in items:
            label = normalise_label(item.get("label") or item.get("name"))
            if not label:
                continue

            sp = item.get("samplingPoint") or {}
            lat = sp.get("lat")
            lon = sp.get("long")

            if lat is None or lon is None:
                continue

            waterbody = item.get("waterBody") or item.get("waterBodyName")
            catchment = item.get("catchmentName")

            cur.execute(
                """
                INSERT INTO sites (
                    site_type,
                    name,
                    location,
                    waterbody_name,
                    catchment_name,
                    source_id,
                    raw_metadata
                )
                SELECT
                    %s,
                    %s,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                    %s,
                    %s,
                    %s,
                    %s
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM sites
                    WHERE site_type = %s AND name = %s
                );
                """,
                (
                    "bathing_water",
                    label,
                    float(lon),
                    float(lat),
                    waterbody,
                    catchment,
                    source_id,
                    Json(item),
                    "bathing_water",
                    label,
                ),
            )

            inserted += cur.rowcount

        conn.commit()

    print(f"Fetched {len(items)} bathing water records total.")
    print(f"Inserted {inserted} bathing water sites.")

if __name__ == "__main__":
    main()
