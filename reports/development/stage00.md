# Stage 00 — Source inventory

## Status

`STAGE_0_ACCEPTED` on DEVELOPMENT. Production Stage 0 is separately accepted as
`NEW_STAGE0_1411_ACCEPTED`. Stage 9 has not started.

## Purpose

Stage 0 freezes an exact source population and records parser, schema,
file/hash, logical-record, anomaly, and identity evidence without transforming
source rows.

## Scope and scientific boundary

The stage inventories immutable CSV sources through an explicit population
scope. It does not ingest to Parquet, create stable row IDs, clean or normalize
text, reconstruct or parse addresses, deduplicate, or geocode.

## Inputs

- An owner-only `stage00_population_scope_v1` containing the exact sorted
  direct-child CSV paths, expected scope SHA-256, and population identity.
- Immutable source CSV files.
- The accepted strict CSV parser and inventory contract.
- For DEVELOPMENT, the accepted 1,405-file snapshot to which Benchmark V1 is
  permanently bound.

## Outputs

The output is an adoption/inventory record binding the authorized population,
source hashes, schemas, logical record counts, parser outcomes, anomalies, and
scientific fingerprints. Stage 0 produces no transformed row dataset.

## Scientific contract

- Python's strict CSV-aware logical-record parser is authoritative; a physical
  line is not assumed to be a record.
- UTF-8, delimiter, header, quoting, schema, and record counts are verified.
- Oversized or multiline fields are diagnosed, never silently cleaned,
  truncated, skipped, or null-padded.
- Population and scientific-inventory fingerprints are separate,
  domain-separated identities.
- Raw files remain read-only and immutable.

## Implementation provenance

The library-first Stage 0 adapter adopts the accepted historical inventory
scanner rather than duplicating it. The current sanitized accepted record does
not retain a distinct DEVELOPMENT candidate SHA, executable SHA, merge SHA, or
SLURM job, so those fields are explicitly `null` in the machine summary rather
than guessed.

PROV-002 performed one Git-only review of current and reachable sanitized
evidence. No exact 1,405-file DEVELOPMENT candidate, executable, merge, job,
independent-review, or DEVELOPMENT-candidate-fingerprint identity was retained.
Each remains `null` and is classified
`HISTORICAL_PROVENANCE_NOT_RETAINED`/`NOT_RETAINED` in the machine report.
Historical Phase 1 evidence concerns a distinct 206-file population and was
not used as a substitute. The null production-population fingerprint is
`NOT_APPLICABLE`: its canonical named identity is recorded separately as
`production_population_1411_v1`.

## DEVELOPMENT execution

The accepted Stage 0 snapshot contains 1,405 files and 140,448,582 logical
rows. Benchmark V1 selects 35,000 DEVELOPMENT rows and seals 15,000 HOLDOUT
rows from that fixed population; its fingerprint is
`014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf`.

Separately, accepted production Stage 0 covers
`production_population_1411_v1`: 1,411 files and 141,048,582 rows. The later six
files do not alter or rebuild Benchmark V1.

## Validation and review

Acceptance required the exact authorized path set, source hashes and sizes,
CSV-aware logical counts, parser/schema results for every file, absence of
unnoticed source mutation, owner-only permissions, sanitized portable evidence,
immutable atomic publication, and independent critical review.

## Historical findings and rejected attempts

The accepted scanner originated in the superseded Phase-era source-foundation
workflow. That implementation lineage remains relevant, but the old Phase
report hierarchy and its smaller historical population are not current Stage 0
evidence. Git history and `docs/history/source_foundation/` retain the concise
historical record.

## Accepted decision

Stage 0 was accepted because it freezes the population and its complete
inventory evidence without changing source data. Production expansion was
accepted separately and did not change DEVELOPMENT identity.

## Known limitations

Inventory evidence does not establish stable row identity, normalized content,
address quality, parser correctness, or geographic truth. Detailed paths and
row-level diagnostics remain controlled and are not in Git.

The historical DEVELOPMENT execution-provenance gap prevents Git-only
independent replay of the original Stage 0 execution. It does not change the
Benchmark V1 population identity, accepted Stage 2–8 chain, Stage 8 handoff,
or Stage 9 readiness.

## Downstream handoff

Stage 1 may consume only the exact accepted Stage 0 scope and hashes. It must
not infer additional files from directory contents or treat Stage 0 evidence as
permission to transform, inspect HOLDOUT, or begin production Stage 2.
