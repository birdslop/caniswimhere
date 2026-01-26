Phase 3 — Analytical Stress Test Plan

Purpose

Phase 3 is an analytical phase, not a product phase.

Its purpose is to stress-test the data model built in Phases 1–2 by asking substantive, publishable questions about the River Thames using only the data already ingested, plus a small number of clearly justified additions if and only if they strengthen those questions.

No API, UI, or expansion to new basins occurs in this phase.

⸻

Why Phase 3 exists

At the end of Phase 2, the project has proven that:
	•	heterogeneous datasets can coexist cleanly,
	•	provenance and idempotency are enforceable,
	•	Thames is a defensible reference basin.

What has not yet been proven is that the model:
	•	supports non-trivial analysis,
	•	surfaces structural blind spots in monitoring,
	•	can underpin accountability narratives.

Phase 3 exists to answer that.

⸻

Guiding principles

Phase 3 analysis must:
	•	be question-led, not tool-led,
	•	avoid inference beyond what the data supports,
	•	make uncertainty and absence visible,
	•	be reproducible from the repository alone.

If an analysis requires speculative joins or inferred geography, it is out of scope.

⸻

Core analytical questions

The following questions are ordered by value-to-effort ratio and by how well they stress different parts of the data model.

Q1 — Where do storm overflows exist without corresponding environmental monitoring?

Question:
Which Thames stretches contain storm overflow assets but lack nearby:
	•	bathing water sites, and/or
	•	hydrology or flood monitoring stations?

Why this matters:
This exposes potential regulatory blind spots where discharges occur without meaningful environmental observation.

Data used:
	•	overflows
	•	overflow_annual_returns
	•	stations
	•	sites

Stress-test dimension:
	•	spatial reasoning
	•	asset vs observation separation

⸻

Q2 — Do high spill counts correlate with monitoring density?

Question:
Are stretches of the Thames with high annual spill counts more, less, or equally monitored than low-spill stretches?

Why this matters:
It tests whether monitoring follows risk or convenience.

Data used:
	•	overflow_annual_returns
	•	stations

Stress-test dimension:
	•	aggregation
	•	uneven spatial coverage

⸻

Q3 — Where does regulatory reporting outpace public-facing water quality data?

Question:
Which areas have detailed regulatory discharge reporting but no publicly visible bathing water quality samples?

Why this matters:
This highlights asymmetries between what regulators know and what the public can see.

Data used:
	•	overflows
	•	samples

Stress-test dimension:
	•	temporal mismatch
	•	dataset granularity differences

⸻

Q4 — Temporal misalignment: annual vs sub-daily data

Question:
What analytical distortions arise when comparing:
	•	annual overflow returns
	•	against sub-daily hydrology and flood data?

Why this matters:
It forces explicit handling of temporal grain mismatch instead of smoothing it away.

Data used:
	•	overflow_annual_returns
	•	measures

Stress-test dimension:
	•	temporal semantics
	•	aggregation discipline

⸻

Explicit non-goals for Phase 3

Phase 3 will not:
	•	rank water companies,
	•	estimate ecological harm,
	•	infer causality between spills and samples,
	•	produce a public dashboard.

Those are downstream activities that require either more data or a public interface.

⸻

Potential supporting datasets (only if justified)

Additional datasets may be considered only if they strengthen one of the above questions.

Examples (not commitments):
	•	EA river catchment polygons (for visualisation only)
	•	EA monitoring coverage metadata

Any addition must:
	•	slot into existing tables or views, or
	•	be stored as auxiliary reference data

No new core entity types are allowed.

⸻

Expected outputs of Phase 3

By the end of Phase 3, the project should have:
	•	3–5 concrete analytical findings,
	•	at least one finding driven by data absence, not presence,
	•	a clear sense of where the model strains or holds.

These outputs should be expressible as:
	•	narrative text,
	•	simple tables,
	•	minimal static maps or plots (optional).

⸻

Exit criteria

Phase 3 is complete when:
	•	the data model has been meaningfully exercised,
	•	no schema changes are required to support the analyses,
	•	it is clear whether the next step is:
	•	a reference API, or
	•	expansion to a second basin.

⸻

Status

This document defines Phase 3.

No implementation has begun.
