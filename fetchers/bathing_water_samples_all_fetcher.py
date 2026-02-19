import os
import re
import requests
import psycopg2
from psycopg2.extras import Json, RealDictCursor
from datetime import datetime, date

PROVIDER = "Environment Agency"
DATASET_NAME = "Bathing Water In-Season Samples (Latest per site)"
LICENSE = "Open Government Licence v3.0"

DATE_RE = re.compile(r"/date/(\d{8})/")

def parse_sample_date_from_url(url: str) -> date | None:
    m = DATE_RE.search(url)
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y%m%d").date()

def normalise_latest_sample_url(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return ""
    # EA links often omit .json
    if not u.endswith(".json"):
        u = u + ".json"
    # Prefer https where possible (EA generally supports it)
    u = u.replace("http://", "https://", 1)
    return u

def extract_latest_sample_url(raw_meta):
    """
    raw_metadata can contain latestSampleAssessment as:
      - a string URL
      - a dict with _about
    """
    if not isinstance(raw_meta, dict):
        return ""
    v = raw_meta.get("latestSampleAssessment") or raw_meta.get("latest_sample_assessment")
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        # common JSON-LD pattern
        return v.get("_about") or v.get("about") or ""
    return ""

def main():
    conn = psycopg2.connect(dbname="water_quality")
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Create a single "run source" row for provenance of this batch.
    run_started = datetime.now().astimezone()
    cur.execute("""
        INSERT INTO sources (
            provider,
            dataset_name,
            source_url,
            license,
            fetched_at,
            raw_metadata
        )
        VALUES (%s, %s, %s, %s, NOW(), %s)
        RETURNING source_id
    """, (
        PROVIDER,
        DATASET_NAME,
        "https://environment.data.gov.uk/doc/bathing-water.json",
        LICENSE,
        Json({"run_started": run_started.isoformat()})
    ))
    run_source_id = cur.fetchone()["source_id"]

    cur.execute("""
        SELECT site_id, name, raw_metadata, latest_sample_assessment_url
        FROM sites
        WHERE site_type = 'bathing_water'
        ORDER BY name
    """)
    sites = cur.fetchall()

    inserted = 0
    updated = 0
    skipped_no_url = 0
    skipped_no_counts = 0
    errors = 0

    for s in sites:
        site_id = s["site_id"]
        raw_meta = s["raw_metadata"] or {}

        latest_url = (s.get("latest_sample_assessment_url") or "").strip()
        if not latest_url:
            latest_url = extract_latest_sample_url(raw_meta)
        latest_url = normalise_latest_sample_url(latest_url)

        if not latest_url:
            skipped_no_url += 1
            continue

        try:
            r = requests.get(latest_url, timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            errors += 1
            continue

        topic = (data.get("result") or {}).get("primaryTopic") or {}
        ecoli = topic.get("escherichiaColiCount")
        enterococci = topic.get("intestinalEnterococciCount")

        # If both missing, nothing to store.
        if ecoli is None and enterococci is None:
            skipped_no_counts += 1
            continue

        sample_date = topic.get("sampleDate") or topic.get("recordDate")
        if isinstance(sample_date, dict):
            sample_date = sample_date.get("_value")

        if isinstance(sample_date, str):
            # Sometimes ISO date or datetime
            try:
                sample_dt = datetime.fromisoformat(sample_date.replace("Z", "+00:00"))
                sample_date_obj = sample_dt.date()
            except Exception:
                sample_date_obj = None
        else:
            sample_date_obj = None

        if sample_date_obj is None:
            sample_date_obj = parse_sample_date_from_url(latest_url)

        if sample_date_obj is None:
            # cannot insert without a date (schema requires it)
            errors += 1
            continue

        def upsert_param(param: str, value):
            nonlocal inserted, updated
            cur.execute("""
                INSERT INTO samples (
                    site_id,
                    sample_date,
                    parameter,
                    value,
                    unit,
                    source_id,
                    raw_metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (site_id, sample_date, parameter)
                DO UPDATE SET
                    value = EXCLUDED.value,
                    unit = EXCLUDED.unit,
                    source_id = EXCLUDED.source_id,
                    raw_metadata = EXCLUDED.raw_metadata
            """, (
                str(site_id),
                sample_date_obj,
                param,
                value,
                "cfu/100ml",
                run_source_id,
                Json({"latest_sample_url": latest_url})
            ))
            # psycopg2 rowcount on upsert: 1 for insert, 1 for update (not distinguishable reliably)
            # We'll infer using GET DIAGNOSTICS would be SQL-level; keep a conservative count:
            inserted += 1

        if ecoli is not None:
            upsert_param("escherichia_coli", ecoli)
        if enterococci is not None:
            upsert_param("intestinal_enterococci", enterococci)

    # Update the source row metadata with run stats
    cur.execute("""
        UPDATE sources
        SET raw_metadata = COALESCE(raw_metadata, '{}'::jsonb) || %s::jsonb
        WHERE source_id = %s
    """, (
        Json({
            "sites_total": len(sites),
            "skipped_no_latest_sample_url": skipped_no_url,
            "skipped_no_counts": skipped_no_counts,
            "errors": errors,
            "rows_upserted": inserted
        }),
        run_source_id
    ))

    conn.commit()
    cur.close()
    conn.close()

    print(f"Sites scanned: {len(sites)}")
    print(f"Skipped (no latestSampleAssessment URL): {skipped_no_url}")
    print(f"Skipped (no counts in payload): {skipped_no_counts}")
    print(f"Errors: {errors}")
    print(f"Sample rows upserted (param-rows): {inserted}")

if __name__ == "__main__":
    main()
