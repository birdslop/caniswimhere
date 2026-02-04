import requests
import psycopg2
from psycopg2.extras import Json
from datetime import date

# Fixed Phase 1 identifiers (do not infer)
SITE_ID = "904bad11-27be-4742-8ad0-6dd1ad829ec3"

SAMPLE_URL = (
    "http://environment.data.gov.uk/data/bathing-water-quality/"
    "in-season/sample/point/11947/date/20250923/time/140100/recordDate/20250923.json"
)

SAMPLE_DATE = date(2025, 9, 23)

def main():
    r = requests.get(SAMPLE_URL)
    r.raise_for_status()
    data = r.json()

    topic = data["result"]["primaryTopic"]

    ecoli = topic.get("escherichiaColiCount")
    enterococci = topic.get("intestinalEnterococciCount")

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
        VALUES (%s, %s, %s, %s, NOW(), %s)
        RETURNING source_id
    """, (
        "Environment Agency",
        "Bathing Water In-Season Samples",
        SAMPLE_URL,
        "Open Government Licence v3.0",
        Json(data)
    ))
    source_id = cur.fetchone()[0]

    inserted = 0

    if ecoli is not None:
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
            ON CONFLICT (site_id, sample_date, parameter) DO NOTHING
        """, (
            SITE_ID,
            SAMPLE_DATE,
            "escherichia_coli",
            ecoli,
            "cfu/100ml",
            source_id,
            Json({"count": ecoli})
        ))
        if cur.rowcount == 1:
            inserted += 1

    if enterococci is not None:
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
            ON CONFLICT (site_id, sample_date, parameter) DO NOTHING
        """, (
            SITE_ID,
            SAMPLE_DATE,
            "intestinal_enterococci",
            enterococci,
            "cfu/100ml",
            source_id,
            Json({"count": enterococci})
        ))
        if cur.rowcount == 1:
            inserted += 1

    conn.commit()
    cur.close()
    conn.close()

    print(f"Inserted {inserted} sample rows for Wallingford Beach, River Thames.")

if __name__ == "__main__":
    main()
