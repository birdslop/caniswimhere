# UK Water Pollution Observatory (Prototype)

## Execution Mode
This repository is built by executing a defined plan without scope drift.
Phase boundaries are respected. No inference-based inclusion criteria are used.

## Phase 1 Scope (Complete)
**Geography:** Thames catchment (Phase 1 prototype slice)  
**Dataset:** Environment Agency bathing water dataset + in-season samples  
**Primary output:** Evidence-grade ingestion into PostGIS + sample ingestion into relational tables

### Phase 1 Thames Definition (Strict, Non-Inferential)
For Phase 1 bathing waters, “Thames membership” is defined strictly as:

- Bathing waters whose **name explicitly contains “River Thames”** in the EA bathing water record.

No additional heuristics are used (e.g., sewerage undertaker, region, district), because those would be inferential and would risk including non-Thames sites.

### Phase 1 Result
Using the strict definition above, the EA bathing water dataset contains exactly **one** bathing water explicitly labelled on the River Thames:

- Wallingford Beach, River Thames

This is an expected outcome of a provenance-first approach.

## Data Model (Phase 1)
The Phase 1 database contains three tables:

- `sources` — provenance for every ingestion run
- `sites` — geolocated bathing water sites (PostGIS point geometry)
- `samples` — lab sample values linked to `sites`

## What This Is Not
- Not a public safety or swim-advice service
- Not an official public-health advisory
- Not a complete representation of UK water pollution
- Not a scoring or prediction system

## Running Phase 1
### Requirements
- PostgreSQL 17 + PostGIS
- Python (venv recommended)

### Scripts
- `fetchers/bathing_water_fetcher.py`  
  Fetches all EA bathing waters, filters to Phase 1 Thames definition, inserts `sites`.

- `fetchers/bathing_water_samples_fetcher.py`  
  Fetches the in-season sample JSON for Wallingford Beach and inserts:
  - `escherichia_coli`
  - `intestinal_enterococci`

## Next Steps
Phase 2 will expand within the Thames geography to additional EA datasets (rivers and/or continuous monitoring),
while preserving Phase 1 definitions and results.
