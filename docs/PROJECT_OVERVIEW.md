# Project overview

## Research context

The SAFE Geocoding Pipeline supports research that links company and facility
locations to fine-grained environmental, remote-sensing, neighborhood, and
other spatial measures. Those uses require a defensible physical point for a
building, plant, branch, store, facility, or comparable establishment. A city,
region, or country centroid is too coarse for point-level exposure analysis.

The pipeline prepares protected Orbis address records for SAFE's self-hosted
Pelias service. It is a research-data construction system, not a general public
geocoding client.

## Goal

The final workflow must produce:

- controlled, versioned SAFE Pelias queries;
- candidate and query identities that map back to every source row;
- selected coordinates with match and geographic-agreement evidence;
- an explicit scientific usability decision; and
- enough contracts, manifests, fingerprints, and execution provenance to
  reproduce the result.

A successful HTTP request or returned feature is not sufficient. Match layer,
match type, component agreement, contradictions, ambiguity, and query lineage
must remain available for scientific review.

## Why preprocessing is separate from geocoding

Source addresses vary strongly across countries, scripts, and completeness
patterns. Quoted multiline fields and very large values exist. Address-line
positions do not have fixed meanings worldwide, `id` is not assumed globally
unique, and postal codes must remain strings. Directly concatenating raw fields
would hide assumptions and make geocoder behavior difficult to interpret.

The pipeline therefore establishes a controlled evidence chain:

1. verify and fingerprint the source population;
2. ingest every logical CSV record without loss;
3. preserve stable source identity and provenance;
4. create only explicit derived values;
5. build standard and native candidates separately;
6. preserve parser output as evidence and abstain from unsafe structural use;
7. generate multiple versioned address/query hypotheses;
8. validate hypotheses and geocoder results with independent evidence;
9. deduplicate candidates and queries without deleting source rows; and
10. accept a result only at an explicit evidence-supported granularity, or
    remain unresolved.

Stages 0–6 are implemented, independently reviewed, and accepted on
DEVELOPMENT. Stage 7's first controlled design diagnostic correctly returned
not ready. Its revised supervisor diagnostic then proved the prior four giant
crashes were resource-cap dependent, and its later authoritative DEVELOPMENT
run passed machine integrity. Stage 7 remains unaccepted because qualitative
and targeted root-cause evidence found material systematic parsing errors. The
country-aware applicability audit has reconciled DEVELOPMENT denominators. The
DeepParse infrastructure path is closed as
`DEEPPARSE_INFRASTRUCTURE_PATH_NOT_JUSTIFIED`; no protected DeepParse inference
occurred. Optimized bounded readiness audit job `1763358` found that a
deterministic Stage 7-local screen catches all six known boundary failures but
cannot guarantee semantic label correctness. Fresh prediction-blinded review
of the predeclared 240-case v2 validation selection then failed the frozen
READY-precision, clear-misparse-leakage, and usable-abstention gates. The rule
remains useful structural-warning evidence but is not publishable as the v2
component-consumption gate. Owner decision D035 freezes evidence-only
`stage07_parser_evidence_contract_v2`: exact v1 outputs and Stage 6 candidates
are preserved, applicability and technical execution remain separate, and
structural signals are warnings rather than semantic trust. Its full
DEVELOPMENT projection and reopen validation passed for all 51,779 candidates
in job `1763516`; the evidence-only candidate is ready for separately
authorized independent review. None of this alters immutable v1 output. The old
Stages 8–19 have not started, and compact evidence-first replacement Stages
8–14 are proposed but not started. See
[PIPELINE.md](PIPELINE.md).

## Standard and native Orbis representations

Both standard and native address representations originate from Orbis. Some
standard representations are English translations, while native fields may
retain the original script and local form. The pipeline treats them as
separate candidates:

- native values are never overwritten by a standard or English form;
- all address lines are not blindly concatenated;
- the two representations may be parsed, evaluated, and queried independently;
- transliteration, if approved later, remains a third derived candidate; and
- each candidate maps back to the same immutable source row.

## Conservative scientific philosophy

The project favors high-precision evidence over aggressive correction:

- raw source values are immutable;
- transformations add derived fields instead of overwriting inputs;
- `stable_source_row_id_v1` remains unchanged across stages;
- source rows are never deduplicated away;
- a missing open-reference record does not make an address invalid;
- `MISMATCH` requires strong positive contradictory evidence;
- uncertain interpretation stays explicit rather than being silently inferred;
- corrections, if later accepted, retain the original value, proposal,
  evidence, reference version, and decision; and
- protected addresses never leave controlled infrastructure.

Pre-geocoding validation uses the closed statuses `CONFIRMED`, `MISMATCH`,
`NOT_FOUND`, `AMBIGUOUS`, `UNSUPPORTED`, and `INVALID_FORMAT`.

## Library-first architecture

Mature offline libraries and pinned reference datasets are preferred when they
meet privacy, licensing, reproducibility, and scientific requirements. SAFE
code supplies conservative orchestration, provenance, deterministic identity,
evidence aggregation, policy, fail-closed validation, and verified gaps.

Accepted stages currently use Python's `csv` and `hashlib`, PyArrow/Parquet,
DuckDB, `unicodedata`, `ftfy`, regular-expression/Arrow operations, and SAFE
contracts. Current Stage 7 DEVELOPMENT evidence uses pinned
libpostal/pypostal. DeepParse is closed and is not a planned runtime
dependency. Proposed future evidence stages evaluate pinned offline pycountry
and libaddressinput metadata, direct GeoNames data, local Overture Maps
Addresses GeoParquet, optional approved OSM evidence, RapidFuzz inside strong
blocks, DuckDB, PyArrow/Parquet, and optional Polars transformations.
Self-hosted SAFE Pelias would retain top-N features for later scoring, never
treat the first result as truth. A planned library or dataset is not an
implemented dependency; every new stage requires design and review before use.

Pandas is limited to small DEVELOPMENT inspection and notebooks. Production
transformations use bounded, columnar or database-oriented execution.

## Development methodology

Each scientific stage follows a fixed lifecycle:

```text
design -> review -> implement -> synthetic tests -> 35k DEVELOPMENT run
       -> aggregate evaluation -> fixed-500 review -> independent review
       -> accept and freeze -> stop
```

Rejected candidates remain immutable evidence. A minimal fix produces a new
run and new review; it does not overwrite or relabel the rejected result.
HOLDOUT is opened once only after the complete governing pipeline is frozen.

## DEVELOPMENT and production separation

Benchmark V1 contains 35,000 DEVELOPMENT rows and 15,000 sealed HOLDOUT rows
drawn from the accepted 1,405-file population. Its identity is permanent; the
six files delivered later do not change it. A deterministic 500-row subset of
DEVELOPMENT supports repeated qualitative before/after review while all 35,000
rows provide quantitative evidence.

The production population is `production_population_1411_v1`: 1,411 files and
141,048,582 rows. Production Stage 0 and Stage 1 are accepted. Production
Stages 2–6 have not started. Heavy or protected execution runs only
through SLURM on Goethe-NHR after separate authorization.

## SAFE Pelias role

SAFE Pelias is self-hosted within the protected execution environment and is
used only after an accepted query registry, final workload QA, and separate
exact-workload authorization. The proposed architecture retains top-N results
from structured or whole-string queries as justified; it does not accept the
first feature automatically. Authentication is runtime-only and never logged.
Normal concurrency is 2–4 total requests across the complete process, not per
worker or job.

Result layer, match type, accuracy, independent component/geographic
agreement, contradictions, and cross-query convergence are retained. Final
acceptance is explicit at `EXACT_ADDRESS`, `STREET_ADDRESS`, `STREET`,
`POSTCODE`, `LOCALITY`, `ADMIN`, or `UNRESOLVED`; a lower-granularity truthful
result is preferable to a false point. Which granularities are usable for a
particular research endpoint remains a later predeclared scientific policy.

## Documentation map

The conceptual specification is [PIPELINE.md](PIPELINE.md), row evolution is
documented in [DATA_FLOW.md](DATA_FLOW.md), durable decisions are recorded in
[DECISIONS.md](DECISIONS.md), and exact stage status is summarized in
[DEVELOPMENT_PROGRESS.md](DEVELOPMENT_PROGRESS.md). Privacy, execution, and
reproduction requirements have separate guides. Accepted source-foundation
records are retained under [history/](history/README.md) as provenance rather
than as the active architecture.
