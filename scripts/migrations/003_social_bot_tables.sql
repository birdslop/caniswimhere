-- Social media bot: NSOH event tracking + post logging
-- Run against the PostGIS database on Railway.

CREATE TABLE IF NOT EXISTS nsoh_events (
    id              SERIAL PRIMARY KEY,
    overflow_id     TEXT NOT NULL,
    company         TEXT,
    event_start     TIMESTAMPTZ NOT NULL,
    event_end       TIMESTAMPTZ,
    receiving_water TEXT,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (overflow_id, event_start)
);

CREATE INDEX IF NOT EXISTS idx_nsoh_events_start ON nsoh_events (event_start);
CREATE INDEX IF NOT EXISTS idx_nsoh_events_overflow ON nsoh_events (overflow_id);

CREATE TABLE IF NOT EXISTS nsoh_snapshots (
    id                SERIAL PRIMARY KEY,
    polled_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    total_monitored   INT,
    total_discharging INT,
    total_offline     INT,
    new_events        INT
);

CREATE TABLE IF NOT EXISTS social_posts (
    id          SERIAL PRIMARY KEY,
    posted_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    platform    TEXT NOT NULL,
    message     TEXT NOT NULL,
    success     BOOLEAN NOT NULL DEFAULT false,
    response_id TEXT
);
