#!/usr/bin/env python3
"""
Ingest Defra Water Recreation Locations (England) into recreation_sites.

Source: EA Chief Scientist's Group research report SC230022/R
        "Exploring water recreation in England"

Data: 3,347 aggregated recreation locations from 17 organisations
      (SAS, Swim England, Wild Swims, rowing/sailing clubs, etc.)
CRS:  EPSG:27700 (British National Grid) → transformed to 4326 on insert.

Idempotent: safe to re-run (ON CONFLICT DO NOTHING on location_id).
"""
import json
import pathlib
import psycopg2
from psycopg2.extras import Json
from datetime import datetime, timezone

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
GEOJSON_PATH = _REPO_ROOT / "data" / "recreation" / "Water_recreation_locations.geojson"

DATASET_URL = (
    "https://environment.data.gov.uk/dataset/"
    "40032292-6737-480f-a6c1-cd49f1e57695"
)


def main():
    print(f"Reading {GEOJSON_PATH} ...")
    with open(GEOJSON_PATH) as f:
        data = json.load(f)

    features = data["features"]
    print(f"  {len(features)} recreation locations loaded.")

    conn = psycopg2.connect(dbname="water_quality")
    cur = conn.cursor()

    # ── Create table if not exists ──────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS recreation_sites (
            rec_site_id     uuid DEFAULT public.uuid_generate_v4() NOT NULL
                            PRIMARY KEY,
            location_id     text NOT NULL UNIQUE,
            location        geometry(Point, 4326) NOT NULL,
            waterbody_salinity  text,
            waterbody_type      text,
            recreation_types    text,
            num_reports         integer,
            num_data_sources    integer,
            num_recreation_types integer,
            swimming            boolean DEFAULT false,
            paddling            boolean DEFAULT false,
            rowing              boolean DEFAULT false,
            sailing             boolean DEFAULT false,
            surfing             boolean DEFAULT false,
            easting             numeric,
            northing            numeric,
            source_id           uuid REFERENCES sources(source_id),
            raw_properties      jsonb
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS recreation_sites_location_idx
        ON recreation_sites USING gist (location)
    """)

    # ── Provenance ──────────────────────────────────────────────
    cur.execute("""
        INSERT INTO sources (
            provider, dataset_name, source_url, license,
            fetched_at, raw_metadata
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING source_id
    """, (
        "Environment Agency / Defra",
        "Water Recreation Locations (England)",
        DATASET_URL,
        "Open Government Licence v3.0",
        datetime.now(timezone.utc),
        Json({"feature_count": len(features), "crs": "EPSG:27700"}),
    ))
    source_id = cur.fetchone()[0]

    # ── Insert features ─────────────────────────────────────────
    inserted = 0
    skipped = 0

    for feat in features:
        props = feat["properties"]
        geom = feat["geometry"]

        loc_id = props.get("location_id")
        if not loc_id or not geom or not geom.get("coordinates"):
            skipped += 1
            continue

        easting, northing = geom["coordinates"]

        cur.execute("""
            INSERT INTO recreation_sites (
                location_id,
                location,
                waterbody_salinity,
                waterbody_type,
                recreation_types,
                num_reports,
                num_data_sources,
                num_recreation_types,
                swimming,
                paddling,
                rowing,
                sailing,
                surfing,
                easting,
                northing,
                source_id,
                raw_properties
            )
            VALUES (
                %s,
                ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 27700), 4326),
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            ON CONFLICT (location_id) DO NOTHING
        """, (
            loc_id,
            easting,
            northing,
            props.get("waterbody_salinity"),
            props.get("waterbody_type"),
            props.get("list_of_recreation_types"),
            props.get("number_of_recreation_reports"),
            props.get("number_of_data_sources"),
            props.get("number_of_recreation_types"),
            bool(props.get("swimming__activity_presence_")),
            bool(props.get("paddling__activity_presence_")),
            bool(props.get("rowing__activity_presence_")),
            bool(props.get("sailing__activity_presence_")),
            bool(props.get("surfing__activity_presence_")),
            props.get("easting"),
            props.get("northing"),
            source_id,
            Json(props),
        ))

        if cur.rowcount == 1:
            inserted += 1

    conn.commit()
    cur.close()
    conn.close()

    print(f"Inserted {inserted} recreation sites.")
    print(f"Skipped  {skipped} (missing location_id or geometry).")


if __name__ == "__main__":
    main()
