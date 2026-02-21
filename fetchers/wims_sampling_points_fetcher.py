#!/usr/bin/env python3
"""
Ingest EA WIMS Water Quality sampling point LOCATIONS (reference layer).

Source: EA Water Quality Archive (Open WIMS)
API:    https://environment.data.gov.uk/water-quality/sampling-point
        Requires Accept: application/geo+json

65,190 sampling points with lat/lon, name, status, type, region, area.
Only locations are stored — actual readings will be fetched on demand
from the EA WIMS API at query time.

Idempotent: safe to re-run (ON CONFLICT DO NOTHING on notation).
"""
import requests
import psycopg2
from psycopg2.extras import Json
from datetime import datetime, timezone

BASE_URL = "https://environment.data.gov.uk/water-quality/sampling-point"
PAGE_SIZE = 250
HEADERS = {"Accept": "application/geo+json"}


def main():
    conn = psycopg2.connect(dbname="water_quality")
    cur = conn.cursor()

    # ── Create table if not exists ──────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS wq_sampling_points (
            sp_id           uuid DEFAULT public.uuid_generate_v4() NOT NULL
                            PRIMARY KEY,
            notation        text NOT NULL UNIQUE,
            label           text,
            sp_status       text,
            sp_type         text,
            region          text,
            area            text,
            sub_area        text,
            location        geometry(Point, 4326) NOT NULL,
            source_id       uuid REFERENCES sources(source_id),
            raw_properties  jsonb
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS wq_sampling_points_location_idx
        ON wq_sampling_points USING gist (location)
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
        "Environment Agency",
        "WIMS Water Quality Sampling Points (National)",
        BASE_URL,
        "Open Government Licence v3.0",
        datetime.now(timezone.utc),
        Json({"api": BASE_URL, "format": "geo+json"}),
    ))
    source_id = cur.fetchone()[0]

    # ── Paginated fetch ─────────────────────────────────────────
    inserted = 0
    skipped = 0
    skip = 0

    while True:
        url = f"{BASE_URL}?limit={PAGE_SIZE}&skip={skip}"
        page_num = skip // PAGE_SIZE + 1
        print(f"Page {page_num}: skip={skip} ...", end=" ", flush=True)
        resp = requests.get(url, headers=HEADERS, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        members = data.get("member", [])
        if not members:
            print("empty, done.")
            break

        total = data.get("totalItems", "?")
        print(f"{len(members)} items (total: {total})")

        for feat in members:
            geom = feat.get("geometry", {})
            props = feat.get("properties", {})

            notation = props.get("notation")
            coords = geom.get("coordinates")
            if not notation or not coords or len(coords) < 2:
                skipped += 1
                continue

            lon, lat = coords[0], coords[1]

            cur.execute("""
                INSERT INTO wq_sampling_points (
                    notation, label, sp_status, sp_type,
                    region, area, sub_area,
                    location, source_id, raw_properties
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                    %s, %s
                )
                ON CONFLICT (notation) DO NOTHING
            """, (
                notation,
                props.get("name"),
                props.get("status"),
                props.get("type"),
                props.get("region"),
                props.get("area"),
                props.get("subArea"),
                lon,
                lat,
                source_id,
                Json(props),
            ))

            if cur.rowcount == 1:
                inserted += 1

        skip += PAGE_SIZE

        # Commit every 50 pages for safety
        if page_num % 50 == 0:
            conn.commit()
            print(f"  [committed {inserted} rows so far]")

        if len(members) < PAGE_SIZE:
            break

    conn.commit()
    cur.close()
    conn.close()

    print(f"\nInserted {inserted} WIMS sampling points.")
    print(f"Skipped  {skipped} (missing notation or geometry).")


if __name__ == "__main__":
    main()
