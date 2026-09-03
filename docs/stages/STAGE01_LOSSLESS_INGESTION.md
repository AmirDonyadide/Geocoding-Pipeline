# Stage 1 — Lossless ingestion

## Purpose

Convert accepted CSV logical records into validated PyArrow/Parquet storage
without changing any decoded source string, while adding immutable source
provenance and stable row identity. The canonical Stage 1 implementation
validates and adopts the accepted immutable ingestion bundle without
duplicating conversion or retaining the superseded Phase runner.

## Input

- accepted Stage 0 population/adoption record and exact SHA-256;
- exact source path/hash/logical-count scope;
- immutable source CSV files; and
- accepted parser, source-schema, stable-ID, and semantic-digest contracts.

## Output

Each row contains the 15 non-null source string fields plus:

- `source_file`;
- `source_logical_record_number`;
- `stable_source_row_id_v1`;
- `source_file_sha256`;
- `source_schema_version`;
- `parser_version`; and
- `staging_version`.

The bundle also contains validated Parquet shards, an integrity-bound manifest,
terminal success state, reconciliation evidence, and
`stage01_logical_dataset_sha256_v1`.

## Scientific rules

- CSV is parsed as logical records under the accepted strict contract.
- All 15 incoming values remain strings; postal codes are never numeric.
- Unicode and standard/native address values are preserved exactly.
- `stable_source_row_id_v1` is derived from source-file SHA-256 and the one-based
  logical record number under a frozen domain-separated formula.
- Provider `id` is not used as a global row key.
- The stable identity excludes source path. Exact duplicate source content at
  the same ordinal therefore fails because it would collide; Stage 1 neither
  renames the identity nor deletes a record.
- Physical Parquet layout/compression does not define logical scientific
  identity.

## Non-goals

Stage 1 performs no cleaning, trimming, normalization, missing-marker handling,
address reconstruction, parsing, deduplication, correction, eligibility
selection, or geocoding.

## Libraries

PyArrow/Parquet writes and validates columnar artifacts. DuckDB independently
reconciles completed Parquet files; it does not parse source CSV.

## Validation

Acceptance requires exact Stage 0 input binding, source snapshot stability,
file and row reconciliation, exact schema, stable-ID uniqueness and formula
verification, semantic-digest equality, Parquet page-checksum readback,
manifest integrity, owner-only permissions, atomic publication, and independent
review. Malformed or incomplete input fails; no record is silently dropped.

## DEVELOPMENT evidence

The population-generic implementation and logical identity contract are
accepted. Benchmark V1's 35,000 DEVELOPMENT rows retain Stage 1 provenance and
provide the accepted input foundation for Stage 2. Historical converter reports
are under [`docs/history/source_foundation/`](../history/source_foundation/README.md).
Phase-prefixed keys and filenames in that immutable bundle remain provenance
compatibility identifiers only.

## Production status

**ACCEPTED — `NEW_STAGE1_1411_ACCEPTED`.** For
`production_population_1411_v1`:

- files: 1,411;
- rows: 141,048,582;
- adoption SHA-256:
  `01809a1ea9d65c574b91f28a938fc27a7eda3e89c7b52252797c7cf0c7c6d9df`;
- logical fingerprint:
  `d68cc9990d476e8b7adbb3df53f158d9a73efe4a0f4a8407a2ab6a2f0d98a763`;
  and
- manifest SHA-256:
  `1fb6176d8eff6dfe71c3c02c1e36e00d35937c7bc662234b7620289d4b055bd7`.

Production Stage 2 has not started.

## Privacy

Raw CSV, Parquet, detailed manifests, source paths, identities, and row-level
diagnostics remain controlled. Directories are `0700`, files are `0600`, and
publication is fail-closed/atomic. No production artifact belongs in Git.

## Acceptance status

**IMPLEMENTED + ACCEPTED.** The stable-ID formula, source preservation, logical
fingerprint semantics, and accepted production identity are frozen.
