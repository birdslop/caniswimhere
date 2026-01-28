# Validation gates — Water Observatory

This project enforces explicit validation gates to prevent silent analytical failure.
Progress beyond any phase assumes **ALL validation checks pass**.

These gates exist because plausible-looking outputs can still be wrong.

---

## Gate 1 — Geometry presence and CRS correctness

**Invariant**
- All spatial tables must have geometry present.
- SRIDs must be correct:
  - overflows.location → EPSG:27700 (British National Grid)
  - sites.location, stations.location → EPSG:4326 (WGS84)

**Why**
CRS mismatch silently breaks all distance and spatial reasoning.

---

## Gate 2 — Coordinate plausibility (range checks)

**Invariant**
- BNG eastings and northings must fall within plausible UK ranges:
  - Easting ≈ 0–700,000
  - Northing ≈ 0–1,300,000

**Why**
National Grid References encode 100 km squares via letter pairs.
Dropping this information produces coordinates displaced by hundreds of km.

---

## Gate 3 — Distance sanity checks

**Invariant**
- Minimum distance between:
  - storm overflows and at least one bathing water site
  must be < 50 km

**Why**
Distances on the order of hundreds of km indicate broken geometry,
not real environmental separation.

---

## Gate 4 — Deterministic transforms only

**Invariant**
- Canonicalisation steps must be mechanical and reversible.
- Semantic merges must be:
  - explicit
  - documented
  - auditable via alias tables

**Why**
This prevents “analysis by guesswork” and preserves uncertainty.

---

## Enforcement

Validation is implemented in:

- `scripts/validate.py`

Any analysis, ingest, or geometry rebuild **must pass validation**
before results are interpreted or committed.

This is non-negotiable.
