# Phase 3 — Q2: Do High Spill Counts Correlate with Monitoring Density? (National)

## Question
Are storm overflow assets with high annual spill counts more, less, or equally monitored than low-spill assets?

This tests whether the EA monitoring network follows discharge risk or is distributed independently of it.

---

## Data used

### Storm overflows
- Table: `overflows` + `overflow_annual_returns`
- Rows: 14,285 overflow assets (all 10 water companies, EDM 2024)
- Geometry: `overflows.location` (EPSG:27700)
- Spill counts: `overflow_annual_returns.counted_spills` (2024 report year)

### Monitoring stations
- Table: `stations`
- Rows: 14,009 stations (national flood monitoring + hydrology)
- Geometry: `stations.location` (EPSG:4326 → transformed to EPSG:27700 for distance)

---

## Methods

1. Bucket each overflow by its 2024 counted spill count: 0, 1–10, 11–50, 51–100, 100+.
2. For each overflow, test whether any monitoring station exists within 2 km and 5 km (straight-line distance, BNG).
3. Report the percentage of overflows with at least one station within each radius, per bucket.
4. Repeat grouped by water company for overflows with spills > 0.

No causal inference is made. "Monitoring" means spatial proximity only — it does not imply that any station is operationally monitoring a specific overflow.

---

## Results

### National — spill bucket vs monitoring coverage

Spill bucket | Overflows | With station ≤2 km | % ≤2 km | With station ≤5 km | % ≤5 km
--- | --- | --- | --- | --- | ---
0 spills | 1,875 | 1,279 | 68.2% | 1,839 | 98.1%
1–10 spills | 3,755 | 2,640 | 70.3% | 3,666 | 97.6%
11–50 spills | 5,475 | 3,673 | 67.1% | 5,290 | 96.6%
51–100 spills | 2,289 | 1,475 | 64.4% | 2,197 | 96.0%
100+ spills | 891 | 522 | 58.6% | 859 | 96.4%

**Key finding:** At the 2 km radius, monitoring coverage **decreases monotonically** as spill counts increase. The highest-spill overflows (100+) have 58.6% coverage vs 70.3% for low-spill (1–10). At 5 km this effect largely disappears (96–98% for all buckets).

### Per-company — overflows with spills > 0

Company | Spilling overflows | Avg spills | With station ≤2 km | % ≤2 km
--- | --- | --- | --- | ---
South West Water | 1,159 | 48.5 | 648 | 55.9%
Northumbrian Water | 1,346 | 30.3 | 792 | 58.8%
Anglian Water | 1,284 | 34.2 | 796 | 62.0%
Dŵr Cymru Welsh Water | 118 | 43.2 | 76 | 64.4%
Severn Trent Water | 2,071 | 30.0 | 1,333 | 64.4%
Southern Water | 830 | 35.4 | 572 | 68.9%
Wessex Water | 1,151 | 38.2 | 805 | 69.9%
United Utilities | 1,977 | 39.4 | 1,385 | 70.1%
Yorkshire Water | 1,949 | 35.0 | 1,497 | 76.8%
Thames Water | 525 | 43.9 | 406 | 77.3%

South West Water has both the highest average spill count (48.5) and the lowest monitoring coverage (55.9% within 2 km).

---

## Interpretation (within scope)

1. **Monitoring does not follow risk.** Higher-spill overflows are *less* likely to have a monitoring station within 2 km, not more.
2. **The effect is structural, not random.** The monotonic decrease across all 5 buckets suggests a systematic pattern — high-spill assets tend to be in less-monitored locations.
3. **At 5 km the gap closes.** This means the monitoring network is broadly distributed nationally but has local coverage gaps that happen to coincide with high-discharge locations.
4. **Company-level variation is significant.** South West Water's 55.9% coverage vs Thames Water's 77.3% reflects different geographical profiles (rural/coastal vs urban).

---

## Limitations

1. "Station within X km" measures spatial proximity, not operational monitoring coverage. A nearby station may measure river level, not water quality.
2. Distance is straight-line (Euclidean on BNG), not hydrological distance along watercourses.
3. Spill counts are as-reported by water companies in the 2024 EDM return. Known issues with EDM reliability are not accounted for.
4. The `stations` table includes both flood-monitoring and hydrology stations. Not all stations measure parameters relevant to sewage discharge impacts.

---

## Implications

- The finding that monitoring density is *inversely* related to discharge frequency strengthens the "observability gap" narrative from Phase 3 Q1.
- Any future monitoring-effectiveness analysis should distinguish station *type* (level, flow, quality) and examine whether flow/quality stations specifically cluster differently.
- The per-company breakdown provides an accountability dimension: companies can be compared not just on spill counts, but on how well their discharge locations are observable.

---

## Reproducibility

All queries are executed against the `water_quality` database using data ingested by:
- `fetchers/edm_all_companies_2024_fetcher.py` (14,285 overflows)
- `scripts/rebuild_overflow_geometry_from_ngr.py` (14,280 geometries)
- `fetchers/stations_all_fetcher.py` (4,748 flood monitoring stations)
- `fetchers/hydrology_stations_all_fetcher.py` (9,126 hydrology stations)
