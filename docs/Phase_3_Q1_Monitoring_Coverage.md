# Phase 3 — Q1 Monitoring Coverage Check (Thames Reference Basin)

## Question
For storm overflow assets in the Thames reference basin (Thames Water EDM Annual Return 2024), which assets have **no nearby Environment Agency monitoring**?

“Nearby” is defined explicitly as **within 2,000 metres** (2 km) straight-line distance.

This is a **coverage / observability** test only. It does not claim environmental impact or causality.

---

## Data used (Phase 2 outputs)

### Storm overflow assets
- `overflows` (590 rows)
- Source: “EDM Storm Overflow Annual Return 2024 (Thames Water 2024 sheet)”
- Location input: `outlet_discharge_ngr` (grid reference)
- Location stored as: `overflows.location` geometry in EPSG:27700

### Monitoring stations
- `stations` (135 rows total)
  - Thames flood monitoring stations + Thames hydrology stations ingested in Phase 2
- `measures` (496 rows total)
  - used to identify hydrology flow stations via `parameter = 'flow'`

### Bathing water sites
- `sites` (1 row)
  - Thames bathing water site: Wallingford Beach, River Thames
  - Note: bathing waters are structurally sparse on the Thames.

---

## Methods

### Coordinate systems
- `overflows.location` is EPSG:27700 (British National Grid; metres)
- `stations.location` and `sites.location` are EPSG:4326 (WGS84; degrees)

All distance calculations are performed after transforming station geometries to EPSG:27700.

### Overflow location construction
Storm overflow locations were derived deterministically from `outlet_discharge_ngr`:

1. Standard format: `AA##########` (2 letters + 10 digits)
   - Parsed as 5-digit easting + 5-digit northing
2. Multi-reference cells containing `"... and ..."`
   - Rule: take the **first** grid reference only (explicit, non-inferential)
3. Short format: `AA########` (2 letters + 8 digits)
   - Rule: treat as 4-digit easting + 4-digit northing and expand to 5+5 by multiplying each by 10 (lower precision preserved)

After this, `overflows.location` was populated for **590/590** rows.

### Nearest-station calculation (all stations)
For each overflow, compute the minimum distance to any station:

- station geometries transformed to EPSG:27700
- distance computed with `ST_Distance`
- “no nearby station” means nearest distance > 2,000 metres

### Hydrology-only variant
Hydrology flow stations are identified without schema assumptions:

- Define hydrology stations as those with at least one measure where `measures.parameter = 'flow'`
- Repeat the same nearest-distance test using this hydrology-only subset

---

## Results

### Coverage test — any Thames station
- Overflows with **no station within 2 km**: **590**
- Total overflows: **590**
- Result: **100% (590/590)** have no station within 2 km.

### Coverage test — hydrology flow stations only
- Overflows with **no hydrology (flow) station within 2 km**: **590**
- Total overflows: **590**
- Result: **100% (590/590)** have no hydrology flow station within 2 km.

---

## Interpretation (strictly within scope)

1. Within the current Thames reference basin ingestion, storm overflow assets are **not colocated** with Environment Agency monitoring stations at a 2 km radius.
2. This holds even when restricting to **flow-monitoring (hydrology) stations**.

This indicates a structural disconnect between:
- **regulatory discharge reporting locations**, and
- **the monitoring network ingested for the Thames**.

---

## Limitations (explicit)

1. The `stations` table currently contains the **Thames-only station subset** ingested in Phase 2 (flood monitoring + hydrology).
   - This analysis does not claim that there are no monitoring stations nationally within 2 km; it claims no station within the ingested Thames monitoring set.
2. “2 km” is a coverage heuristic, not an environmental impact boundary.
3. No causality is claimed between overflows and any measured values.

---

## Next steps (still within Phase 3)

To extend this result without changing the data model:
- compute the same coverage statistic at multiple radii (e.g. 1 km, 5 km) as a labelled sensitivity check
- compute coverage relative to bathing water site(s) (expected to show extremely sparse public-facing sampling on Thames)
- produce a small table summarising “distance to nearest station” distribution (min/median/max)

No API/UI work is required for these.
