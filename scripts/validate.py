#!/usr/bin/env python3
import sys
import psycopg2

DB = "water_quality"

def fail(msg):
    print(f"[VALIDATION FAIL] {msg}", file=sys.stderr)
    sys.exit(1)

def ok(msg):
    print(f"[OK] {msg}")

def main():
    conn = psycopg2.connect(dbname=DB)
    cur = conn.cursor()

    # Basic presence
    cur.execute("SELECT COUNT(*) FROM overflows;")
    n_overflows = cur.fetchone()[0]
    if n_overflows == 0:
        fail("overflows is empty")

    cur.execute("SELECT COUNT(*) FROM sites;")
    n_sites = cur.fetchone()[0]
    if n_sites == 0:
        fail("sites is empty")

    # Geometry presence + SRID
    cur.execute("SELECT COUNT(*) FROM overflows WHERE location IS NULL;")
    n_null = cur.fetchone()[0]
    if n_null != 0:
        fail(f"overflows.location has NULLs: {n_null}")

    cur.execute("SELECT ST_SRID(location), COUNT(*) FROM overflows GROUP BY 1;")
    srids = cur.fetchall()
    if len(srids) != 1 or srids[0][0] != 27700:
        fail(f"overflows.location SRID must be 27700 only. Found: {srids}")
    ok("overflows.location present and SRID=27700")

    # Hard plausibility tripwire: nearest overflow to bathing site must not be hundreds of km
    cur.execute("""
      WITH bathing_site AS (
        SELECT ST_Transform(location, 27700) AS geom FROM sites
      )
      SELECT MIN(ST_Distance(o.location, b.geom))::INTEGER
      FROM overflows o
      CROSS JOIN bathing_site b;
    """)
    min_d = cur.fetchone()[0]
    if min_d is None:
        fail("distance check returned NULL")

    # This is a deliberate hard-stop to catch the exact failure you're seeing.
    if min_d > 50_000:
        fail(f"implausible min overflow→site distance: {min_d} m (geometry likely wrong)")

    ok(f"min overflow→site distance plausible: {min_d} m")

    conn.close()
    print("ALL VALIDATION CHECKS PASSED")

if __name__ == "__main__":
    main()
