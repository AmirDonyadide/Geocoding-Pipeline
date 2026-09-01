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

The pre-geocoding pipeline therefore establishes a controlled evidence chain:

1. verify and fingerprint the source population;
2. ingest every logical CSV record without loss;
3. preserve stable source identity and provenance;
4. create only explicit derived values;
5. build standard and native candidates separately;
6. validate components conservatively using independent evidence;
7. deduplicate candidates and queries without deleting source rows; and
8. submit only approved, versioned queries to self-hosted SAFE Pelias.

Stages 0–6 are implemented, independently reviewed, and accepted on
DEVELOPMENT. Stage 7's first controlled design diagnostic correctly returned
not ready. Its revised supervisor diagnostic then proved the prior four giant
crashes were resource-cap dependent, and its later authoritative DEVELOPMENT
run passed machine integrity. Stage 7 remains unaccepted because qualitative
and targeted root-cause evidence found material systematic parsing errors. The
country-aware applicability audit now has reconciled DEVELOPMENT denominators,
and the DeepParse trained-country diagnostic remains infrastructure-only. Its
first public bundle was valid at publication but was later mutated by a
login-side Python cache-resolution import because post-publication write
protection was absent. Both compute smokes stopped before scientific execution.
One final public-only physically read-only bundle architecture is undergoing
PRELAUNCH V2 validation; none of this alters the immutable v1 output.
Stages 8–19 have not started. See
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
libpostal/pypostal and is evaluating one pinned DeepParse model only as a
country-eligible diagnostic. Other planned libraries include pycountry,
google-i18n-address, direct pinned GeoNames postal data, local Overture Maps
Addresses GeoParquet, RapidFuzz, Polars, and optional OSM evidence. A planned
library is not an implemented dependency; every new stage requires design and
review before use.

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
HOLDOUT is opened once only after the complete Stage 2–19 pipeline is frozen.

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
used only after query construction and final QA. The preferred endpoint is
`/v1/search/structured`, normally with `size=1`. Authentication is runtime-only
and never logged. Normal concurrency is 2–4 total requests across the complete
process, not per worker or job.

An exact address-layer result without a major contradiction is expected to be
usable. Acceptance of interpolated address results remains an open scientific
policy until later evidence. Street, venue, locality, administrative, region,
country, and fallback results are not usable for point-level research.

## Documentation map

The conceptual specification is [PIPELINE.md](PIPELINE.md), row evolution is
documented in [DATA_FLOW.md](DATA_FLOW.md), durable decisions are recorded in
[DECISIONS.md](DECISIONS.md), and exact stage status is summarized in
[DEVELOPMENT_PROGRESS.md](DEVELOPMENT_PROGRESS.md). Privacy, execution, and
reproduction requirements have separate guides. Accepted source-foundation
records are retained under [history/](history/README.md) as provenance rather
than as the active architecture.
