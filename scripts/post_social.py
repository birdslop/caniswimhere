#!/usr/bin/env python3
"""
Post sewage discharge statistics to Bluesky and X (Twitter).

Designed to run via cron at 05:00 and 17:00 UTC (covers both GMT and BST).
The script checks the current UK local time and only posts if it's
approximately 06:00 or 18:00 in Europe/London.

Requires environment variables:
    DATABASE_URL
    BLUESKY_HANDLE, BLUESKY_APP_PASSWORD
    X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET

Usage:
    python scripts/post_social.py          # normal (checks UK time)
    python scripts/post_social.py --force  # skip time check, post now
"""
import os
import sys
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import psycopg

# ── Config ─────────────────────────────────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL", "dbname=water_quality")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

BLUESKY_HANDLE = os.environ.get("BLUESKY_HANDLE", "")
BLUESKY_APP_PASSWORD = os.environ.get("BLUESKY_APP_PASSWORD", "")

X_API_KEY = os.environ.get("X_API_KEY", "")
X_API_SECRET = os.environ.get("X_API_SECRET", "")
X_ACCESS_TOKEN = os.environ.get("X_ACCESS_TOKEN", "")
X_ACCESS_TOKEN_SECRET = os.environ.get("X_ACCESS_TOKEN_SECRET", "")

UK_TZ = ZoneInfo("Europe/London")

HASHTAGS = (
    "#PoopsAway #flooding #FloodWarnings #Sewage "
    "#SewageCrisis #SaveOurRivers #RiverReclaim #cleanrivers"
)

SITE_URL = "www.caniswimhere.uk"


# ── Time gate ──────────────────────────────────────────────────
def should_post_now() -> bool:
    """Return True if the current UK local time is close to 06:00 or 18:00."""
    now_uk = datetime.now(UK_TZ)
    hour = now_uk.hour
    # Allow a 90-minute window: 05:00–06:30 or 17:00–18:30 UK time
    return hour in (5, 6, 17, 18)


# ── Stats queries ──────────────────────────────────────────────
def get_stats() -> dict:
    """Query nsoh_events for currently active and 12h counts."""
    now_utc = datetime.now(timezone.utc)
    twelve_hours_ago = now_utc - timedelta(hours=12)

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Currently discharging (last seen within 45 min, no event_end)
            cur.execute("""
                SELECT count(*) FROM nsoh_events
                WHERE event_end IS NULL
                  AND last_seen_at >= now() - interval '45 minutes'
            """)
            currently = cur.fetchone()[0]

            # Events started in the last 12 hours
            cur.execute(
                "SELECT count(*) FROM nsoh_events WHERE event_start >= %s",
                (twelve_hours_ago,),
            )
            last_12h = cur.fetchone()[0]

    return {
        "currently_discharging": currently,
        "last_12h": last_12h,
    }


# ── Build post text ────────────────────────────────────────────
def build_message(stats: dict) -> str:
    """Compose the post text from stats."""
    active = f"{stats['currently_discharging']:,}"
    n12 = f"{stats['last_12h']:,}"

    lines = [
        f"\U0001f6a8 In the last 12 hours, we\u2019ve recorded {n12} sewage "
        f"discharge events across England & Scotland.",
        "",
        f"Right now, {active} storm overflows are actively discharging.",
        "",
        f"\U0001f30a {SITE_URL}",
        "",
        HASHTAGS,
    ]
    return "\n".join(lines)


# ── Post to Bluesky ────────────────────────────────────────────
def post_bluesky(message: str) -> str | None:
    """Post to Bluesky via AT Protocol SDK. Returns post URI or None."""
    if not BLUESKY_HANDLE or not BLUESKY_APP_PASSWORD:
        print("  ⚠ Bluesky credentials not set — skipping")
        return None
    try:
        from atproto import Client
        client = Client()
        client.login(BLUESKY_HANDLE, BLUESKY_APP_PASSWORD)
        post = client.send_post(text=message)
        print(f"  ✓ Bluesky: posted {post.uri}")
        return post.uri
    except Exception as e:
        print(f"  ✗ Bluesky failed: {e}")
        return None


# ── Post to X ──────────────────────────────────────────────────
def post_x(message: str) -> str | None:
    """Post to X via Tweepy. Returns tweet ID or None."""
    if not X_API_KEY or not X_ACCESS_TOKEN:
        print("  ⚠ X credentials not set — skipping")
        return None
    try:
        import tweepy
        client = tweepy.Client(
            consumer_key=X_API_KEY,
            consumer_secret=X_API_SECRET,
            access_token=X_ACCESS_TOKEN,
            access_token_secret=X_ACCESS_TOKEN_SECRET,
        )
        resp = client.create_tweet(text=message)
        tweet_id = resp.data["id"]
        print(f"  ✓ X: posted tweet {tweet_id}")
        return str(tweet_id)
    except Exception as e:
        print(f"  ✗ X failed: {e}")
        # Print full error details for debugging
        if hasattr(e, 'response') and e.response is not None:
            print(f"    Status: {e.response.status_code}")
            print(f"    Headers: {dict(e.response.headers)}")
            print(f"    Body: {e.response.text}")
        if hasattr(e, 'api_errors'):
            print(f"    API errors: {e.api_errors}")
        if hasattr(e, 'api_messages'):
            print(f"    API messages: {e.api_messages}")
        return None


# ── Log to database ────────────────────────────────────────────
def log_post(platform: str, message: str, success: bool, response_id: str | None):
    """Write a record to social_posts for audit."""
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO social_posts (platform, message, success, response_id)
                    VALUES (%s, %s, %s, %s)
                """, (platform, message, success, response_id))
            conn.commit()
    except Exception as e:
        print(f"  ⚠ Failed to log {platform} post: {e}")


# ── Main ───────────────────────────────────────────────────────
def main():
    force = "--force" in sys.argv

    if not force and not should_post_now():
        now_uk = datetime.now(UK_TZ)
        print(f"Not posting — UK time is {now_uk.strftime('%H:%M')} "
              f"(need ~06:00 or ~18:00). Use --force to override.")
        return

    print(f"[{datetime.now(timezone.utc).isoformat()}] Generating social post …")

    stats = get_stats()
    print(f"  Stats: active={stats['currently_discharging']}, "
          f"12h={stats['last_12h']}")

    message = build_message(stats)
    print(f"  Message ({len(message)} chars):")
    print(f"  ---")
    for line in message.split("\n"):
        print(f"  | {line}")
    print(f"  ---")

    # Post to both platforms
    bsky_uri = post_bluesky(message)
    log_post("bluesky", message, bsky_uri is not None, bsky_uri)

    x_id = post_x(message)
    log_post("x", message, x_id is not None, x_id)

    print(f"[{datetime.now(timezone.utc).isoformat()}] Done.")


if __name__ == "__main__":
    main()
