# Phase 3 — Q4: Receiving water normalisation (EDM 2024, Thames Water)

## Objective
Normalize the `receiving_water_name` field from the Thames Water 2024 EDM storm overflow annual return so that:
- raw source strings are preserved for provenance,
- we can group logically identical waterbodies safely (without guessing),
- we explicitly track mapping coverage and uncertainty.

This is an OSINT-style “reference layer” approach:
- deterministic transforms for canonicalisation
- explicit alias table for semantic merges
- do not merge ambiguous cases without an external reference layer

## Data inputs
- Table: `overflows`
- Column: `receiving_water_name` (raw)
- Scope: rows where `receiving_water_name IS NOT NULL AND receiving_water_name <> 'N/A'`

## Implementation

### Layer 1 — Raw (as-reported)
- `overflows.receiving_water_name` is treated as authoritative source text.

### Layer 2 — Canonical (mechanical clean-up)
Added columns:
- `receiving_water_canonical TEXT`
- `receiving_water_tidal BOOLEAN`

Canonicalisation transform (deterministic):
- lower-case
- remove bracketed text `( … )`
- strip leading “river”, “the river”, “r.”
- collapse whitespace
- INITCAP for presentation

Tidal flag:
- `receiving_water_tidal = (receiving_water_name ILIKE '%tidal%')`

This step is intentionally “string hygiene” only (not semantic).

### Layer 3 — Semantic mapping (auditable merges)
Created table:
- `receiving_water_aliases(alias PRIMARY KEY, canonical NOT NULL, notes)`

Added column:
- `overflows.receiving_water_semantic TEXT`

Rule:
- Only map exact-string aliases that are non-ambiguous.
- Avoid merging entries that might represent distinct watercourses/sections without external validation.

Examples of safe merges included:
- Thames variants → `River Thames` and `River Thames (Tidal)`
- Roding variants → `River Roding`
- Lee vs “The River Lee” → `River Lee`
- Kennet variants → `River Kennet`
- Kennet & Avon Canal variants (“&” vs “And”) → `Kennet & Avon Canal`

## Coverage metrics (checkpoint)
Current state:

- total_overflows: 590
- named_overflows (not null / not 'N/A'): 518
- semantically_mapped_rows: 137
- pct_named_semantically_mapped: 26.45%

Interpretation:
- This is a partial semantic layer by design.
- Remaining unmapped names include many that are already clean (no obvious alias) and others that are ambiguous and require an external reference layer (e.g., gazetteer or EA waterbody ID linkage).

## Outputs
- `docs/q4_receiving_water_aliases.csv` — snapshot of alias mappings used at this checkpoint.

## Next steps (not executed in this phase)
To raise semantic coverage without guessing:
- integrate a reference layer (e.g., EA waterbody IDs / gazetteer join),
- then re-map ambiguous strings using validated identifiers rather than name inference.

