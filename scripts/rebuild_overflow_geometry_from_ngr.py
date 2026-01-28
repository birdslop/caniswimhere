#!/usr/bin/env python3
import re
import sys
import psycopg2

DB = "water_quality"
NGR_RE = re.compile(r"\b([A-HJ-Z]{2})\s*([0-9]{2,10})\b")

def fail(msg):
    print(f"[REBUILD FAIL] {msg}", file=sys.stderr)
    sys.exit(1)

def ok(msg):
    print(f"[OK] {msg}")

# 100km grid square lookup for OS National Grid (no I).
# This table is authoritative for converting the two-letter prefix to (E,N) 100km offsets.
# Layout is derived from the OS 5x5 letter scheme.
GRID_100KM = {
    # Row 0 (northmost)
    "HP": (400000, 1200000), "HT": (300000, 1200000), "HU": (400000, 1100000),
    # Row 1
    "NA": (0, 900000), "NB": (100000, 900000), "NC": (200000, 900000), "ND": (300000, 900000), "NE": (400000, 900000),
    "NF": (0, 800000), "NG": (100000, 800000), "NH": (200000, 800000), "NJ": (300000, 800000), "NK": (400000, 800000),
    "NL": (0, 700000), "NM": (100000, 700000), "NN": (200000, 700000), "NO": (300000, 700000), "NP": (400000, 700000),
    "NQ": (0, 600000), "NR": (100000, 600000), "NS": (200000, 600000), "NT": (300000, 600000), "NU": (400000, 600000),
    "NV": (0, 500000), "NW": (100000, 500000), "NX": (200000, 500000), "NY": (300000, 500000), "NZ": (400000, 500000),

    "OV": (500000, 500000), "OW": (600000, 500000), "OX": (700000, 500000),

    "SA": (0, 400000), "SB": (100000, 400000), "SC": (200000, 400000), "SD": (300000, 400000), "SE": (400000, 400000),
    "SF": (0, 300000), "SG": (100000, 300000), "SH": (200000, 300000), "SJ": (300000, 300000), "SK": (400000, 300000),
    "SL": (0, 200000), "SM": (100000, 200000), "SN": (200000, 200000), "SO": (300000, 200000), "SP": (400000, 200000),
    "SQ": (0, 100000), "SR": (100000, 100000), "SS": (200000, 100000), "ST": (300000, 100000), "SU": (400000, 100000),
    "SV": (0, 0),      "SW": (100000, 0),      "SX": (200000, 0),      "SY": (300000, 0),      "SZ": (400000, 0),

    "TA": (500000, 400000), "TB": (600000, 400000),
    "TF": (500000, 300000), "TG": (600000, 300000),
    "TL": (500000, 200000), "TM": (600000, 200000),
    "TQ": (500000, 100000), "TR": (600000, 100000),
    "TV": (500000, 0),      "TW": (600000, 0),
}

def parse_ngr(ngr: str):
    ngr = ngr.strip().replace(" ", "").upper()
    m = NGR_RE.search(ngr)
    if not m:
        raise ValueError(f"no NGR found in: {ngr}")

    letters = m.group(1)
    digits = m.group(2)

    if letters not in GRID_100KM:
        raise ValueError(f"unknown grid letters: {letters}")

    if len(digits) % 2 != 0:
        raise ValueError(f"odd digit count in NGR: {letters}{digits}")

    half = len(digits) // 2
    e_part = digits[:half]
    n_part = digits[half:]

    # pad to 5 digits each (metres)
    scale = 10 ** (5 - half)
    e_within = int(e_part) * scale
    n_within = int(n_part) * scale

    e0, n0 = GRID_100KM[letters]
    return e0 + e_within, n0 + n_within

def first_valid_ngr(text: str):
    if not text:
        return None
    m = NGR_RE.search(text.upper())
    if not m:
        return None
    return m.group(1) + m.group(2)

def main():
    conn = psycopg2.connect(dbname=DB)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM overflows;")
    total = cur.fetchone()[0]
    if total == 0:
        fail("overflows table is empty")

    cur.execute("SELECT unique_id, outlet_discharge_ngr FROM overflows ORDER BY unique_id;")
    rows = cur.fetchall()

    updated = skipped = errors = 0

    for unique_id, ngr_text in rows:
        token = first_valid_ngr(ngr_text or "")
        if not token:
            skipped += 1
            continue
        try:
            e, n = parse_ngr(token)
        except Exception as ex:
            errors += 1
            if errors <= 10:
                print(f"[PARSE ERROR] {unique_id} | {ngr_text!r} | {ex}", file=sys.stderr)
            continue

        cur.execute("""
          UPDATE overflows
          SET location = ST_SetSRID(ST_MakePoint(%s, %s), 27700)
          WHERE unique_id = %s;
        """, (e, n, unique_id))
        updated += 1

    conn.commit()
    ok(f"Updated {updated} overflow geometries from NGR")
    ok(f"Skipped (no parseable NGR): {skipped}")
    ok(f"Errors (parse failures): {errors}")

    cur.execute("""
      SELECT
        MIN(ST_X(location))::INTEGER AS min_e,
        MAX(ST_X(location))::INTEGER AS max_e,
        MIN(ST_Y(location))::INTEGER AS min_n,
        MAX(ST_Y(location))::INTEGER AS max_n
      FROM overflows;
    """)
    min_e, max_e, min_n, max_n = cur.fetchone()
    ok(f"BNG ranges: easting {min_e}..{max_e}, northing {min_n}..{max_n}")

    conn.close()

if __name__ == "__main__":
    main()
