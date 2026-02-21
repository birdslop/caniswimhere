# UK Water Pollution Observatory

A PostGIS-backed data warehouse for UK water pollution data, built with provenance-first discipline.
Ingests open data from the Environment Agency, Natural Resources Wales (NRW),
SEPA, and Scottish Water into a relational model with full audit trails.

Covers **England, Wales and Scotland** — 18,000+ storm overflows, 580+ bathing
waters, 65K+ water quality sampling points, and near-real-time overflow
discharge status from 10 water companies.

## Setup

### Prerequisites
- PostgreSQL 17 + PostGIS
- Python 3.12+

### Quick Start
```bash
# 1. Clone and enter the repo
git clone <repo-url> && cd uk-water-observatory

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Create the database and apply schema
./scripts/setup_db.sh

# 4. Run fetchers (order matters: sources must exist before dependent tables)
# Phase 1 — Thames bathing water
python fetchers/bathing_water_fetcher.py
python fetchers/bathing_water_samples_fetcher.py

# Phase 2 — Thames stations + overflows
python fetchers/thames_stations_fetcher.py
python fetchers/thames_hydrology_stations_fetcher.py
python fetchers/edm_thames_2024_fetcher.py
python scripts/rebuild_overflow_geometry_from_ngr.py

# National — all bathing water sites + samples
python fetchers/bathing_water_all_fetcher.py
python fetchers/bathing_water_samples_all_fetcher.py

# National — all water company overflows (England)
python fetchers/edm_all_companies_2024_fetcher.py
python scripts/rebuild_overflow_geometry_from_ngr.py

# Devolved nations — Wales + Scotland bathing waters & overflows
python scripts/import_devolved.py

# National — all EA monitoring stations
python fetchers/stations_all_fetcher.py
python fetchers/hydrology_stations_all_fetcher.py

# 5. Validate
python scripts/validate.py
```

## Data Model

### Core tables
- `sources` — provenance for every ingestion run
- `sites` — geolocated bathing water sites (EPSG:4326) — EA (England), NRW (Wales), SEPA (Scotland)
- `samples` — lab sample values linked to sites
- `stations` — EA flood monitoring + hydrology stations (EPSG:4326)
- `measures` — measures associated with stations
- `overflows` — storm overflow assets (EPSG:27700) — EA EDM (England & Wales), Scottish Water
- `overflow_annual_returns` — annual spill data per overflow (England & Wales; not yet available for Scotland)

### Reference tables
- `receiving_water_aliases` — semantic normalisation of receiving water names
- `bathing_seasons` / `site_bathing_seasons` — bathing season dates

Full DDL: [`schema.sql`](schema.sql)

## Project Phases

| Phase | Status | Scope |
|-------|--------|-------|
| 1 | ✅ Complete | Thames bathing water (Wallingford Beach) |
| 2 | ✅ Complete | Thames reference basin (stations, hydrology, EDM overflows) |
| 3 | 🔶 Partial | Analytical stress test (Q1 ✓, Q3 ✓, Q4 ✓, Q2 in progress) |
| 4 | 🔶 Partial | Impact framing (Wallingford case study started) |
| National | ✅ Complete | All English water companies, all EA stations |
| Devolved | ✅ Complete | Wales (NRW bathing, EDM overflows) + Scotland (SEPA bathing, Scottish Water overflows) |

See [`docs/`](docs/) for detailed analysis reports.

## Design Principles
- **Provenance-first**: every row traces back to a source
- **Non-inferential**: no basin membership inferred from proximity or heuristics
- **Idempotent**: all ingestion paths safe to re-run
- **Temporal correctness**: no resampling or aggregation at ingest time

## What This Is Not
- Not a public safety or swim-advice service
- Not an official public-health advisory
- Not a scoring or prediction system
