# Phase 3 — Q3 Public-Facing Bathing Water Coverage (Thames Reference Basin)

## Question
How does the spatial footprint of publicly visible bathing-water sampling compare to the spatial footprint of reported storm overflows in the Thames reference basin?

This is a **coverage and representativeness** question, not an impact or causality claim.

---

## Data used

### Storm overflows
- Table: `overflows`
- Rows: 590
- Source: EDM Storm Overflow Annual Return 2024 (Thames Water)
- Geometry: `overflows.location` (EPSG:27700)

### Bathing water sites
- Table: `sites`
- Rows: 1
- Site: Wallingford Beach, River Thames
- Geometry: `sites.location` (EPSG:4326 → transformed to EPSG:27700 for analysis)

---

## Methods

1. Transform bathing-water site geometry to EPSG:27700.
2. Compute straight-line distance (`ST_Distance`) from each overflow to the bathing-water site.
3. Summarise distance distribution:
   - min / median / max
   - counts within 1 km, 5 km, and 10 km.
4. List the 10 closest overflows to characterise the best-case edge of coverage.

No buffering, interpolation, or impact inference is performed.

---

## Results

### Distance summary
- Total overflows: 590
- Minimum distance to bathing-water site: ~374 km
- Median distance: ~445 km
- Maximum distance: ~495 km

Coverage thresholds:
- Within 1 km: 0
- Within 5 km: 0
- Within 10 km: 0

### Closest overflows
The 10 closest overflows are all located hundreds of kilometres from the only bathing-water site, with the nearest at approximately 374 km.

---

## Interpretation (within scope)

Public-facing bathing-water sampling on the Thames is **spatially disconnected** from the reported storm overflow discharge footprint.

As a result:
- Bathing-water sampling cannot be interpreted as monitoring storm overflow locations.
- Any inference about storm overflows based on bathing-water data is necessarily indirect and system-level.

---

## Limitations

- Only one Thames bathing-water site exists in the dataset.
- This analysis does not claim environmental impact or pollutant transport.
- Distance is used purely as a coverage metric.

---

## Implications for the platform

- Public-facing sampling represents a **very narrow slice** of the river system.
- Coverage gaps must be exposed explicitly to avoid misleading downstream analysis.
- This supports the design principle of treating the platform as a **reference layer**, not a detector.

---

## Next steps

- Combine Q1 and Q3 findings into a single “observability gap” narrative.
- Expand hydrology ingestion nationally to unblock Q2.
- Introduce uncertainty and coverage visualisation as first-class features.
