Phase 2 — Thames Reference Basin Implementation Report

Purpose of this document

This document records what was built, why it was built that way, and what guarantees now exist at the end of Phase 2 of the Water Observatory project. It is intended to be read later by:
	•	you (future-you sanity check),
	•	collaborators,
	•	reviewers (journalists, NGOs, technical partners).

It deliberately avoids aspirational language and documents facts and decisions only.

⸻

Phase 2 objectives (as defined)

Phase 2 was intended to:
	•	complete a full reference implementation for a single UK river basin (the Thames),
	•	ingest multiple pollution-relevant datasets with different temporal grains,
	•	prove that provenance, idempotency, and temporal correctness could coexist,
	•	stop before UI or API work.

The Thames was explicitly chosen as the reference basin, not because it is representative of the UK, but because it is:
	•	data-dense,
	•	politically sensitive,
	•	institutionally fragmented,
	•	heavily monitored.

⸻

Datasets ingested

1. Bathing Water Quality (Environment Agency)

Tables:
	•	sites
	•	samples

What was ingested:
	•	All EA bathing waters whose official name contains “River Thames”.
	•	Sample-level measurements (E. coli, intestinal enterococci).

Key decisions:
	•	No inferred geography.
	•	Inclusion rule is explicit and reproducible.
	•	Sample timestamps preserved as authoritative.

⸻

2. Flood Monitoring Stations (Environment Agency)

Tables:
	•	stations
	•	measures

What was ingested:
	•	All flood-monitoring stations where riverName == "River Thames".
	•	Associated level measures.

Key decisions:
	•	Stations treated as assets; measures treated as observations.
	•	Station identity based on EA station references.

⸻

3. Hydrology Stations (Environment Agency Hydrology API)

Tables:
	•	stations
	•	measures

What was ingested:
	•	All hydrology stations where riverName contains “River Thames”.
	•	Flow and level measures at multiple temporal resolutions.

Key decisions:
	•	Hydrology and flood-monitoring share schema but not assumptions.
	•	Station count and inclusion were measured, not guessed.

⸻

4. Storm Overflows — EDM Annual Return 2024 (Defra / EA)

Tables:
	•	overflows
	•	overflow_annual_returns

What was ingested:
	•	Entire “Thames Water 2024” regulatory return.
	•	590 overflow assets.
	•	590 annual return rows (one per asset).

Key decisions:
	•	Regulatory Unique ID treated as the canonical identifier.
	•	Annual returns treated as immutable snapshots.
	•	Raw Excel rows preserved verbatim as JSON metadata.

⸻

Cross-cutting guarantees established in Phase 2

Provenance
	•	Every dataset creates a row in sources.
	•	Every asset and observation links back to a source.
	•	Raw upstream payloads are preserved (raw_metadata).

Idempotency
	•	All ingestion paths are safe to re-run.
	•	Natural keys enforced via uniqueness constraints.

Temporal correctness
	•	Sample-level, sub-daily, and annual data coexist without coercion.
	•	No resampling or aggregation performed at ingest time.

Non-inference
	•	No basin membership is inferred from proximity or heuristics.
	•	All inclusion rules are explicit and inspectable.

⸻

Reference basin status

The River Thames is now a complete reference implementation across:
	•	water quality samples,
	•	river level and flow monitoring,
	•	regulatory sewage discharge reporting.

All future basins must conform to the same structural contracts.

⸻

What Phase 2 intentionally did NOT do
	•	No frontend or visualisation.
	•	No public API.
	•	No national coverage.
	•	No derived analytics.

This was deliberate.

⸻

Outcome

At the end of Phase 2, the project has:
	•	a stable, defensible data model,
	•	a reference basin with real-world complexity,
	•	a foundation suitable for investigation, publication, or reuse.

This closes Phase 2.
