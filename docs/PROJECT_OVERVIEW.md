# Project overview

## Research context

The SAFE Geocoding Pipeline prepares protected Orbis company and facility
addresses for SAFE's self-hosted Pelias service. The research needs defensible
physical locations for buildings, plants, branches, stores and comparable
establishments, linked to environmental, remote-sensing and neighborhood
measures. City, region and country centroids are too coarse for point-level
exposure analysis.

The eventual output must retain each source row, its derived candidates and
queries, geocoder evidence, selected coordinates, and an explicit scientific
usability decision. Contracts, manifests, fingerprints and execution provenance
must make those decisions reproducible. HTTP success, rank and confidence
alone cannot establish a usable location.

## Why preprocessing is separate from geocoding

Source files contain quoted multiline fields, very large values, varied scripts
and incomplete geography. Address lines 1–4 have no universal component
meanings; provider `id` is not globally unique; postal codes are strings.
Preprocessing makes each transformation and assumption independently reviewable.

The implemented chain establishes source identity, preserves decoded values,
adds clean and lowercase forms, reconstructs separate standard/native
candidates, deduplicates exact candidate work, and records parser and reference
evidence. Stage 10 generates query hypotheses offline. Retrieval, scoring and
final selection remain proposed. See [PIPELINE.md](PIPELINE.md) for stage
boundaries and [DATA_FLOW.md](DATA_FLOW.md) for schemas and map-back.

## Standard and native Orbis representations

Both representations originate from Orbis. Standard values may be English
translations; native fields may preserve original script and local form.
Neither is globally authoritative. They remain separate representation
occurrences even when exact text shares a Stage 6 candidate ID.

Native text is never overwritten. Stage 5 joins nonempty lines in their original
order within each representation, preserving duplicates and excluding separate
geographic fields. Stage 10's narrowly eligible Greek/Cyrillic transliteration
is an additional hypothesis; the full native candidate remains intact.

## Scientific limits

- Raw source values and `stable_source_row_id_v1` are immutable. Transformations
  add derived fields; deduplication retains every source/representation mapping.
- Stage 7 preserves exact parser output, applicability, technical provenance
  and structural warnings. Its rejected readiness experiment demonstrated that
  warning absence cannot guarantee correct labels or boundaries.
- Stage 8 is a reversible evidence projection and index, with no semantic
  validation or reference lookup.
- Stage 9 uses `SUPPORTED`, `CONTRADICTED`, `NOT_FOUND` and `NOT_EVALUABLE`.
  These describe scoped reference checks, not address validity. GeoNames has
  no negative authority; absence is never invalidity.
- Stage 9's Q04 conflict rate is conditional on evaluable reference checks,
  weighted by parser-component repetition. It is not an invalid-address rate.
  Country assessments remain unresolved because the frozen rule found no
  qualifying full subdivision-code witnesses.
- Any future correction must retain the original value, proposal, evidence,
  reference version and decision. Uncertainty remains explicit.

The [Stage 7 report](../reports/development/stage07.md),
[Stage 8 report](../reports/development/stage08.md) and
[Stage 9 acceptance record](../reports/development/stage09.md#owner-acceptance-and-freeze--2026-09-14)
preserve the experiments, rejected candidates, publication repairs and review
limits behind these boundaries. No failure is retrospectively relabeled.

## Libraries and execution

The code uses Python CSV/hash functions, PyArrow/Parquet, DuckDB, `unicodedata`
and ftfy. Stage 7's immutable parsing run uses pinned libpostal/pypostal;
DeepParse was closed without protected inference. Stage 9 uses frozen iso-codes
JSON, offline libaddressinput metadata and GeoNames postal data. Stage 10 uses
pinned ICU4C 77.1 for its transliteration family. Pandas is permitted only for
small DEVELOPMENT inspection, not production transformations.

Protected/heavy processing runs on Goethe-NHR compute nodes through SLURM.
Local work is limited to code, documentation, synthetic tests, small diagnostics
and authorized small DEVELOPMENT review. Protected values never go to external
services, LLMs or Git. See [execution](EXECUTION.md) and
[privacy](PRIVACY_AND_SECURITY.md).

## Evaluation and current status

Benchmark V1 fixes 35,000 DEVELOPMENT and 15,000 sealed HOLDOUT rows from the
1,405-file population. A deterministic 500-row DEVELOPMENT subset supports
same-row review. The separate production population contains 1,411 files and
141,048,582 rows; the later six files never alter Benchmark V1.

Each stage requires design approval, implementation validation, authorized
DEVELOPMENT evaluation, independent review and owner acceptance, then stops.
Rejected runs remain immutable. HOLDOUT is reserved for one separately
authorized final evaluation after the governing pipeline is frozen.

Stages 0–10 are accepted and frozen on DEVELOPMENT; Stage 11 is NOT STARTED.
The [Stage 10 acceptance](../reports/development/stage10.md) preserves the exact
candidate, final independent rereview and UNSELECTED operating budget.
Production Stages 0–1 are accepted. The [progress index](DEVELOPMENT_PROGRESS.md)
records the latest execution checkpoint; [stage records](stages/README.md)
separate frozen design snapshots from later implementation evidence.

## SAFE Pelias role

The repository has no geocoding client or implementation for authentication,
request retries, rate limiting, result caching or match selection. Stage 10
stores offline intents for `/v1/search` and `/v1/search/structured`; it sends no
request.
There is no implemented `X-API-Key` configuration, `/v1/autocomplete` or
`/attribution` workflow.

The proposed retrieval stage retains top-N results and evaluates layer, match
type, accuracy, independent agreement, contradictions and cross-query
convergence. Proposed output granularities are `EXACT_ADDRESS`, `STREET_ADDRESS`,
`STREET`, `POSTCODE`, `LOCALITY`, `ADMIN` and `UNRESOLVED`. Research usability
thresholds remain undecided. Normal concurrency is constrained to 2–4 requests
across the complete process; this is a project policy, not an implemented
limiter or verified service quota.

The current Stage 19 acceptance and exact-workload authorization gate remains
controlling. The proposed Stage 12 retrieval placement and top-N policy require
explicit reconciliation with that gate and the current `size=1` preference
before execution. Credentials will remain runtime-only and must never be logged.
