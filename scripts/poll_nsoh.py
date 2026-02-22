#!/usr/bin/env python3
"""
Poll all NSOH (National Storm Overflow Hub) ArcGIS endpoints and persist
discharge events into the database.

Designed to run every 30 minutes via cron.
Requires: DATABASE_URL environment variable.

Usage:
    python scripts/poll_nsoh.py
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.parse import urlencode

import psycopg

# ── Shared NSOH endpoint config ────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.nsoh_config import NSOH_ENDPOINTS, NSOH_DEFAULT_FIELDS

DATABASE_URL = os.environ.get("DATABASE_URL", "dbname=water_quality")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

TIMEOUT = 15  # seconds per HTTP request


def fetch_json(url: str) -> dict:
    """GET a URL and return parsed JSON."""
    req = Request(url, headers={
        "User-Agent": "CISH-poll/1.0",
        "Accept": "application/json",
    })
    with urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read())


def _parse_ts(raw) -> datetime | None:
    """Parse a timestamp that may be epoch-ms (int/float) or ISO-8601 string."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        if raw <= 0:
            return None
        return datetime.fromtimestamp(raw / 1000, tz=timezone.utc)
    if isinstance(raw, str):
        try:
            # Try epoch-ms as string
            ms = float(raw)
            if ms <= 0:
                return None
            return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        except ValueError:
            pass
        try:
            # ISO-8601 string
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def query_discharging(company: str, base_url: str, field_map: dict | None) -> list[dict]:
    """Query a single NSOH endpoint for currently-discharging overflows."""
    fm = field_map or NSOH_DEFAULT_FIELDS
    status_field = fm["status"]
    out_fields = ",".join(fm.values())

    params = urlencode({
        "where": f"{status_field}=1",
        "outFields": out_fields,
        "returnGeometry": "false",
        "resultRecordCount": 5000,
        "f": "json",
    })
    url = f"{base_url}/query?{params}"

    try:
        data = fetch_json(url)
    except Exception as e:
        print(f"  ⚠ {company}: request failed — {e}")
        return []

    results = []
    for feat in data.get("features", []):
        a = feat.get("attributes", {})
        overflow_id = a.get(fm["id"])
        event_start_raw = a.get(fm["event_start"])
        if not overflow_id or not event_start_raw:
            continue

        # Parse timestamp — may be epoch-ms (int/float) or ISO string
        event_start = _parse_ts(event_start_raw)
        if event_start is None:
            continue

        event_end_raw = a.get(fm["event_end"])
        event_end = _parse_ts(event_end_raw)

        results.append({
            "overflow_id": str(overflow_id),
            "company": a.get(fm["company"]) or company,
            "event_start": event_start,
            "event_end": event_end,
            "receiving_water": a.get(fm["receiving_water"]),
        })
    return results


def query_count(base_url: str) -> int | None:
    """Get total feature count from an endpoint (all statuses)."""
    params = urlencode({
        "where": "1=1",
        "returnCountOnly": "true",
        "f": "json",
    })
    url = f"{base_url}/query?{params}"
    try:
        data = fetch_json(url)
        return data.get("count")
    except Exception:
        return None


def poll_all():
    """Poll every NSOH endpoint and persist results."""
    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting NSOH poll …")

    total_monitored = 0
    total_discharging = 0
    total_offline = 0  # we don't query offline separately; placeholder
    all_events: list[dict] = []

    for company, url, fm in NSOH_ENDPOINTS:
        # Get discharging overflows
        events = query_discharging(company, url, fm)
        print(f"  {company}: {len(events)} discharging")
        all_events.extend(events)
        total_discharging += len(events)

        # Get total monitored count
        count = query_count(url)
        if count is not None:
            total_monitored += count

        # Small delay to be polite to ArcGIS servers
        time.sleep(0.3)

    # ── Persist to database ───────────────────────────────────
    new_events = 0
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            for ev in all_events:
                cur.execute("""
                    INSERT INTO nsoh_events
                        (overflow_id, company, event_start, event_end,
                         receiving_water, first_seen_at, last_seen_at)
                    VALUES (%s, %s, %s, %s, %s, now(), now())
                    ON CONFLICT (overflow_id, event_start) DO UPDATE
                        SET event_end    = EXCLUDED.event_end,
                            last_seen_at = now()
                    RETURNING (xmax = 0) AS is_insert
                """, (
                    ev["overflow_id"],
                    ev["company"],
                    ev["event_start"],
                    ev["event_end"],
                    ev["receiving_water"],
                ))
                row = cur.fetchone()
                if row and row[0]:  # is_insert = True means new row
                    new_events += 1

            # Write snapshot
            cur.execute("""
                INSERT INTO nsoh_snapshots
                    (polled_at, total_monitored, total_discharging, total_offline, new_events)
                VALUES (now(), %s, %s, %s, %s)
            """, (total_monitored, total_discharging, total_offline, new_events))

        conn.commit()

    print(f"  ✓ Totals: {total_discharging} discharging / {total_monitored} monitored / {new_events} new events")
    print(f"[{datetime.now(timezone.utc).isoformat()}] Poll complete.")


if __name__ == "__main__":
    poll_all()
