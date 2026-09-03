# Stage 01 — Lossless ingestion

## Status

`STAGE_1_ACCEPTED` on DEVELOPMENT. Production Stage 1 is separately accepted as
`NEW_STAGE1_1411_ACCEPTED`. Stage 9 has not started.

## Purpose

Stage 1 converts accepted CSV logical records into validated PyArrow/Parquet
storage without changing decoded source strings, while adding immutable source
provenance and stable row identity.

## Scope and scientific boundary

The stage is a lossless storage and provenance transformation. It performs no
cleaning, trimming, normalization, missing-marker handling, reconstruction,
parsing, deduplication, correction, eligibility selection, or geocoding.

## Inputs

- The exact accepted Stage 0 population/adoption record and SHA-256.
- Immutable source CSV files and their accepted path/hash/logical-count scope.
- The accepted parser, source-schema, stable-ID, and semantic-digest contracts.
- Benchmark V1 DEVELOPMENT input for the downstream DEVELOPMENT pipeline.

## Outputs

Each logical row preserves 15 non-null source strings and appends seven fields:
`source_file`, `source_logical_record_number`, `stable_source_row_id_v1`,
`source_file_sha256`, `source_schema_version`, `parser_version`, and
`staging_version`. The immutable bundle includes validated Parquet shards,
manifest, terminal success state, reconciliation evidence, and a logical
dataset fingerprint.

## Scientific contract

- CSV input is read as logical records under the accepted strict contract.
- All 15 incoming values remain strings; postal codes never become numeric.
- Unicode and standard/native representations are preserved exactly.
- `stable_source_row_id_v1` is derived from source-file SHA-256 and the one-based
  logical record number under the frozen domain-separated formula.
- Provider `id` is not a global key.
- Physical Parquet layout and compression do not define scientific identity.

## Implementation provenance

The library-first adapter reuses the accepted historical converter. The
sanitized accepted record does not expose a distinct DEVELOPMENT candidate,
executable, merge, or job identity, so the machine report records `null` for
those values. The accepted production fingerprints below are exact.

PROV-002 performed one Git-only review of current and reachable sanitized
evidence. No exact 1,405-file DEVELOPMENT candidate, executable, merge, job,
independent-review, or logical-dataset fingerprint was retained. Each remains
`null` and is classified
`HISTORICAL_PROVENANCE_NOT_RETAINED`/`NOT_RETAINED` in the machine report.
Historical Phase 2 evidence concerns a distinct 206-file population and was
not used as a substitute.

## DEVELOPMENT execution

Benchmark V1's 35,000 DEVELOPMENT rows retain the Stage 1 provenance and stable
identity foundation consumed by Stage 2. Benchmark V1 remains tied to the
1,405-file Stage 0 population and fingerprint
`014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf`.

For accepted `production_population_1411_v1`, Stage 1 contains 141,048,582 rows
from 1,411 files. Its adoption SHA-256 is
`01809a1ea9d65c574b91f28a938fc27a7eda3e89c7b52252797c7cf0c7c6d9df`,
logical fingerprint is
`d68cc9990d476e8b7adbb3df53f158d9a73efe4a0f4a8407a2ab6a2f0d98a763`, and
manifest SHA-256 is
`1fb6176d8eff6dfe71c3c02c1e36e00d35937c7bc662234b7620289d4b055bd7`.

## Validation and review

Acceptance proved exact Stage 0 binding, source snapshot stability, file and
row reconciliation, exact schema, stable-ID uniqueness and formula,
semantic-digest equality, Parquet checksum readback, manifest integrity,
owner-only permissions, atomic publication, and independent review. Malformed
or incomplete input fails rather than dropping records.

## Historical findings and rejected attempts

The accepted converter originated in the superseded Phase-era architecture.
That provenance is retained in the stage record and Git history; its separate
report hierarchy is no longer a current reporting system.

## Accepted decision

Stage 1 was accepted because every source value and logical record reconciled
exactly while the stable provenance required downstream was added. Production
acceptance is separately bound to the 1,411-file identity.

## Known limitations

Lossless ingestion does not establish address semantics, quality, uniqueness,
parser correctness, or geographic truth. Protected Parquet and row-level
provenance do not belong in Git.

The historical DEVELOPMENT execution-provenance gap prevents Git-only
independent replay of the original Stage 1 execution. It does not change the
Benchmark V1 population identity, accepted Stage 2–8 chain, Stage 8 handoff,
or Stage 9 readiness.

## Downstream handoff

Stage 2 may consume the exact accepted DEVELOPMENT bundle and stable identities.
It must preserve all 22 fields. Production Stage 2 and Stage 9 have not started.
