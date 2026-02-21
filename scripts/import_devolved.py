#!/usr/bin/env python3
"""
Import devolved-nation data into the UK Water Observatory.

Sources:
  1. Welsh bathing waters  — NRW Linked Data API  (112 sites)
  2. Scottish bathing waters — SEPA ArcGIS MapServer (89 sites)
  3. Welsh overflows        — EA/NRW 2024 EDM ArcGIS (country='Wales')
  4. Scottish overflows     — Scottish Water ArcGIS live endpoint (1,538 monitored)

Usage:
  python scripts/import_devolved.py
"""
import json
import math
import sys
import uuid
from urllib.request import urlopen, Request
from urllib.parse import urlencode, quote

import psycopg

DB = "dbname=water_quality"

# ────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────

def fetch_json(url):
    """GET a URL and return parsed JSON."""
    req = Request(url, headers={"User-Agent": "CISH-import/1.0"})
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def arcgis_all(base_url, where="1=1", out_fields="*", batch=1000):
    """Page through an ArcGIS FeatureServer/query endpoint."""
    offset = 0
    all_features = []
    while True:
        params = urlencode({
            "where": where,
            "outFields": out_fields,
            "f": "json",
            "resultRecordCount": batch,
            "resultOffset": offset,
        })
        url = f"{base_url}/query?{params}"
        data = fetch_json(url)
        features = data.get("features", [])
        if not features:
            break
        all_features.extend(features)
        print(f"  … fetched {len(all_features)} records", end="\r")
        if len(features) < batch:
            break
        offset += batch
    print(f"  → {len(all_features)} records total      ")
    return all_features


def bng_to_wgs84(easting, northing):
    """Rough BNG (OSGB36) to WGS84 conversion — good enough for display.
    Uses a simple Helmert transform approximation."""
    # Use PostGIS for accurate conversion; this is a fallback.
    # We'll do the real conversion in SQL instead.
    return None, None  # handled by ST_Transform in SQL


# ────────────────────────────────────────────────────────────────
# 1. WELSH BATHING WATERS (NRW API)
# ────────────────────────────────────────────────────────────────

NRW_BW_URL = "https://environment.data.gov.uk/wales/bathing-waters/id/bathing-water.json?_pageSize=200"

def import_welsh_bathing(conn):
    print("\n=== 1. Welsh Bathing Waters (NRW API) ===")
    data = fetch_json(NRW_BW_URL)
    items = data["result"]["items"]
    print(f"  Fetched {len(items)} Welsh bathing waters")

    inserted = 0
    with conn.cursor() as cur:
        for item in items:
            eubwid = item.get("eubwidNotation", "")
            if not eubwid:
                continue

            # Check if already exists
            cur.execute("SELECT 1 FROM sites WHERE eubwid = %s", (eubwid,))
            if cur.fetchone():
                continue

            name_obj = item.get("name", {})
            name = name_obj.get("_value", "") if isinstance(name_obj, dict) else str(name_obj)

            sp = item.get("samplingPoint", {})
            lat = sp.get("lat")
            lon = sp.get("long")
            if lat is None or lon is None:
                continue

            # Classification
            latest = item.get("latestComplianceAssessment", {})
            classification = None
            if latest:
                cc = latest.get("complianceClassification", {})
                cc_name = cc.get("name", {})
                classification = cc_name.get("_value", "") if isinstance(cc_name, dict) else str(cc_name)

            site_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO sites (site_id, site_type, name, location, eubwid,
                                   latest_risk_level, raw_metadata)
                VALUES (%s, 'bathing_water', %s,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                        %s, %s, %s)
                ON CONFLICT (eubwid) WHERE site_type = 'bathing_water' DO NOTHING
            """, (site_id, name, lon, lat, eubwid, classification,
                  json.dumps({"source": "NRW", "country": "Wales"})))
            inserted += 1

    conn.commit()
    print(f"  ✓ Inserted {inserted} Welsh bathing waters")


# ────────────────────────────────────────────────────────────────
# 2. SCOTTISH BATHING WATERS (SEPA ArcGIS)
# ────────────────────────────────────────────────────────────────

SEPA_BW_URL = "https://map.sepa.org.uk/server/rest/services/Open/Environmental_Monitoring/MapServer/1"

def import_scottish_bathing(conn):
    print("\n=== 2. Scottish Bathing Waters (SEPA ArcGIS) ===")
    features = arcgis_all(SEPA_BW_URL)
    print(f"  Fetched {len(features)} Scottish bathing waters")

    inserted = 0
    with conn.cursor() as cur:
        for f in features:
            attrs = f.get("attributes", {})
            geom = f.get("geometry", {})

            name = attrs.get("description", "")
            classification = attrs.get("class_description")
            bw_url = attrs.get("bw_url", "")

            # Geometry is in BNG (27700), convert via PostGIS
            easting = geom.get("x")
            northing = geom.get("y")
            if easting is None or northing is None:
                continue

            # Create a pseudo-eubwid from the name for dedup
            # SEPA doesn't expose eubwid directly in this endpoint
            pseudo_eubwid = f"sepa-{name.lower().replace(' ', '-').replace('(', '').replace(')', '')}"

            cur.execute("SELECT 1 FROM sites WHERE eubwid = %s", (pseudo_eubwid,))
            if cur.fetchone():
                continue

            site_id = str(uuid.uuid4())
            meta = json.dumps({"source": "SEPA", "country": "Scotland",
                               "classification_year": attrs.get("year")})
            insert_name = name
            for attempt in range(2):
                try:
                    cur.execute("""
                        INSERT INTO sites (site_id, site_type, name, location, eubwid,
                                           latest_risk_level, latest_profile_url, raw_metadata)
                        VALUES (%s, 'bathing_water', %s,
                                ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 27700), 4326),
                                %s, %s, %s, %s)
                    """, (site_id, insert_name, easting, northing, pseudo_eubwid,
                          classification, bw_url, meta))
                    break
                except psycopg.errors.UniqueViolation:
                    conn.rollback()
                    insert_name = f"{name}, Scotland"
            inserted += 1

    conn.commit()
    print(f"  ✓ Inserted {inserted} Scottish bathing waters")


# ────────────────────────────────────────────────────────────────
# 3. WELSH OVERFLOWS (2024 EDM ArcGIS, country='Wales')
# ────────────────────────────────────────────────────────────────

EDM_2024_URL = "https://services3.arcgis.com/Bb8lfThdhugyc4G3/arcgis/rest/services/Storm_Overflow_EDM_Annual_Returns_2024/FeatureServer/0"

def import_welsh_overflows(conn):
    print("\n=== 3. Welsh Overflows (2024 EDM ArcGIS) ===")
    features = arcgis_all(EDM_2024_URL, where="country='Wales'")
    print(f"  Fetched {len(features)} Welsh overflow records from EDM 2024")

    ov_inserted = 0
    ar_inserted = 0
    with conn.cursor() as cur:
        for f in features:
            a = f.get("attributes", {})

            # Build a unique_id — Welsh data doesn't always have UID
            permit = a.get("permitReferenceEA") or a.get("permitReferenceWaSC") or ""
            activity = a.get("activityReference") or ""
            company = a.get("waterCompanyName") or ""

            # Use the permit+activity as unique key, similar to English data
            unique_id = a.get("UID") or a.get("UIDPre2024")
            if not unique_id:
                # Construct a deterministic ID
                unique_id = f"W-{permit}-{activity}".strip("-")
            if not unique_id:
                continue

            # Check if already exists
            cur.execute("SELECT 1 FROM overflows WHERE unique_id = %s", (unique_id,))
            if cur.fetchone():
                # Still insert annual return if missing
                pass
            else:
                lat = a.get("Latitude")
                lon = a.get("Longitude")
                easting = a.get("Eastings")
                northing = a.get("Northings")

                overflow_id = str(uuid.uuid4())
                cur.execute("""
                    INSERT INTO overflows (
                        overflow_id, unique_id, water_company_name,
                        site_name_ea, site_name_wasc,
                        ea_permit_reference, activity_reference,
                        asset_type, outlet_discharge_ngr,
                        wfd_waterbody_id, wfd_catchment_name,
                        receiving_water_name, receiving_water_canonical,
                        location, raw_metadata
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        CASE WHEN %s IS NOT NULL AND %s IS NOT NULL
                             THEN ST_SetSRID(ST_MakePoint(%s, %s), 27700)
                             ELSE NULL END,
                        %s
                    )
                    ON CONFLICT DO NOTHING
                """, (
                    overflow_id, unique_id, company,
                    a.get("siteNameEA"), a.get("siteNameWASC"),
                    str(permit), str(activity),
                    a.get("assetType"), a.get("outletDischargeNGRoriginal"),
                    a.get("wfdWaterbodyID"), a.get("wfdWaterbodyName"),
                    a.get("recievingWaterName"), a.get("recievingWaterName"),  # sic in source
                    easting, northing, easting, northing,
                    json.dumps({"source": "EDM_2024_ArcGIS", "country": "Wales",
                                "sourceDB": a.get("sourceDB"),
                                "localAuthority": a.get("localAuthority"),
                                "riverBasinDistrict": a.get("riverBasinDistrict")}),
                ))
                ov_inserted += 1

            # Annual return
            spills = a.get("countedSpills")
            duration = a.get("totalDurationAllSpillsHrs")
            edm_pct = a.get("edmOperationPercent")
            lta = a.get("longTermAverageSpillCount")

            duration_text = f"{duration} hours" if duration is not None else None

            cur.execute("""
                INSERT INTO overflow_annual_returns (
                    return_id, unique_id, report_year,
                    counted_spills, total_duration_text,
                    edm_operational_pct, long_term_avg_spill_count,
                    raw_metadata
                ) VALUES (%s, %s, 2024, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                str(uuid.uuid4()), unique_id,
                spills, duration_text, edm_pct, lta,
                json.dumps({"source": "EDM_2024_ArcGIS", "country": "Wales"}),
            ))
            ar_inserted += 1

    conn.commit()
    print(f"  ✓ Inserted {ov_inserted} Welsh overflows, {ar_inserted} annual returns")


# ────────────────────────────────────────────────────────────────
# 4. SCOTTISH OVERFLOWS (Scottish Water ArcGIS)
# ────────────────────────────────────────────────────────────────

SW_OVERFLOW_URL = "https://services3.arcgis.com/Bb8lfThdhugyc4G3/arcgis/rest/services/Scottish_Water_Storm_Overflow_Activity/FeatureServer/0"

def import_scottish_overflows(conn):
    print("\n=== 4. Scottish Overflows (Scottish Water ArcGIS) ===")
    features = arcgis_all(SW_OVERFLOW_URL)
    print(f"  Fetched {len(features)} Scottish overflow records")

    ov_inserted = 0
    with conn.cursor() as cur:
        for f in features:
            a = f.get("attributes", {})
            geom = f.get("geometry", {})

            asset_id = a.get("ASSET_ID")
            if not asset_id:
                continue

            unique_id = f"SW-{asset_id}"

            cur.execute("SELECT 1 FROM overflows WHERE unique_id = %s", (unique_id,))
            if cur.fetchone():
                continue

            lat = a.get("DISCHARGE_LOCATION_LATITUDE")
            lon = a.get("DISCHARGE_LOCATION_LONGITUDE")
            easting = a.get("DISCHARGE_LOCATION_X")
            northing = a.get("DISCHARGE_LOCATION_Y")

            overflow_id = str(uuid.uuid4())
            # Prefer BNG easting/northing; fall back to converting lat/lon via PostGIS
            cur.execute("""
                INSERT INTO overflows (
                    overflow_id, unique_id, water_company_name,
                    site_name_ea, ea_permit_reference,
                    asset_type, receiving_water_name, receiving_water_canonical,
                    location, raw_metadata
                ) VALUES (
                    %s, %s, 'Scottish Water', %s, %s, %s, %s, %s,
                    CASE WHEN %s IS NOT NULL AND %s IS NOT NULL
                         THEN ST_SetSRID(ST_MakePoint(%s, %s), 27700)
                         WHEN %s IS NOT NULL AND %s IS NOT NULL
                         THEN ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 27700)
                         ELSE NULL END,
                    %s
                )
                ON CONFLICT DO NOTHING
            """, (
                overflow_id, unique_id,
                a.get("ASSET_NAME"), a.get("LICENCE_NUMBER"),
                a.get("OVERFLOW_TYPE"),
                a.get("RECEIVING_WATER"), a.get("RECEIVING_WATER"),
                easting, northing, easting, northing,
                lon, lat, lon, lat,
                json.dumps({
                    "source": "Scottish_Water_ArcGIS",
                    "country": "Scotland",
                    "postcode": a.get("DISCHARGE_LOCATION_POSTCODE"),
                    "localAuthority": a.get("LOCAL_AUTHORITY_NAME"),
                    "gridRef": a.get("DISCHARGE_LOCATION_GRID_REF"),
                }),
            ))
            ov_inserted += 1

    conn.commit()
    print(f"  ✓ Inserted {ov_inserted} Scottish overflows")


# ────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────

def main():
    print("╔══════════════════════════════════════════════════════╗")
    print("║  Devolved Nations Data Import                       ║")
    print("║  Wales + Scotland bathing waters & overflows         ║")
    print("╚══════════════════════════════════════════════════════╝")

    with psycopg.connect(DB) as conn:
        import_welsh_bathing(conn)
        import_scottish_bathing(conn)
        import_welsh_overflows(conn)
        import_scottish_overflows(conn)

    print("\n✅ All imports complete.")

    # Print summary
    with psycopg.connect(DB) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM sites WHERE site_type = 'bathing_water'")
            print(f"  Total bathing waters: {cur.fetchone()[0]}")
            cur.execute("SELECT count(*) FROM overflows")
            print(f"  Total overflows: {cur.fetchone()[0]}")
            cur.execute("SELECT water_company_name, count(*) FROM overflows GROUP BY 1 ORDER BY 2 DESC")
            print("  By company:")
            for r in cur.fetchall():
                print(f"    {r[0]}: {r[1]}")


if __name__ == "__main__":
    main()
