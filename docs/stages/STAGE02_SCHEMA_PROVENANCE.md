# Stage 2 — schema and provenance harmonization

## Status and purpose

Stage 2 status is **STAGE_2_ACCEPTED**. Its implementation ancestry includes
commit `8e4020a02d5d2ed3833f8c8f3fef9a777d568a20`; accepted DEVELOPMENT execution
job `1758833` used Git SHA
`6432c72ca496852551d3f9d4e9084632cf2766af`. All 35,000 input rows produced
exactly 35,000 output rows with unchanged incoming fields and stable
identities. Stage 2 converts an accepted Stage 1 representation, or the separately
accepted `BENCHMARK_SAMPLE_V1` DEVELOPMENT representation, into one stable
internal source-row schema. It is a lossless projection plus four raw structural
fields. It performs no cleaning, parsing, normalization, reconstruction,
transliteration, correction, deduplication, or geocoding.

Contract: `stage02_schema_provenance_harmonization_contract_v1`.

Accepted DEVELOPMENT identities:

- logical fingerprint:
  `ff95021bd2f4b2994e9e2a766f32e792e29797a128dc64fa3aef100ff9f5ca72`;
- schema fingerprint:
  `3c4a2d616ab6dacf57f42fff7e84175a48fbd50c6a060046434593c5aefa74d4`.

## Input contract

An owner-only, SHA-pinned `stage02_input_binding_v1` explicitly lists the
canonical ordered Parquet artifacts, their sizes and SHA-256 values, exact row
count, upstream contract and logical identity, source-population identity, and
input schema fingerprint. Directory contents never define the input implicitly.

Two input kinds are supported:

- `STAGE01`: exact `stage01_lossless_ingestion_contract_v1`/Phase 2 staging
  schema;
- `BENCHMARK_DEVELOPMENT`: exact accepted benchmark schema, with every selected
  row required to carry `benchmark_split == DEVELOPMENT`.

The DEVELOPMENT interface reads only explicitly bound DEVELOPMENT Parquet. A
path naming `holdout`, or a non-DEVELOPMENT split value, fails closed. It does
not require or open the HOLDOUT artifact or benchmark manifest.

## Canonical row schema

The first 22 columns are the exact Stage 1 schema, in its accepted order and
types: all 15 non-null source strings; `source_file`;
`source_logical_record_number`; `stable_source_row_id_v1`;
`source_file_sha256`; and the source-schema, parser, and staging versions.
Benchmark DEVELOPMENT supplies the same 15 source strings and four immutable
provenance values. Its source-schema and parser versions are the accepted
Stage 0/1 values, while `staging_version` truthfully records
`benchmark_sample_parquet_schema_v1` rather than claiming that the row was
physically produced by historical Phase 2.

Both standard and native representations are recorded as Orbis source
representations with relationship `ALTERNATIVE_SOURCE_REPRESENTATIONS`. This
dataset-level provenance is part of the Stage 2 scientific contract; it does
not choose either representation or combine them.

Four non-null structural fields follow, producing exactly 26 columns in total:

| Field | Type | Exact v1 meaning |
|---|---|---|
| `standard_has_nonempty_source_line` | bool | any standard raw line is not `""` |
| `native_has_nonempty_source_line` | bool | any native raw line is not `""` |
| `standard_nonempty_source_line_count` | uint8 | count of standard raw lines not equal to `""` |
| `native_nonempty_source_line_count` | uint8 | count of native raw lines not equal to `""` |

No trimming or Unicode operation participates. A whitespace-only source value
is therefore present. Null raw fields violate the accepted upstream schema and
fail. Standard and native lines remain independent; Stage 2 never concatenates
or compares them semantically.

## Scientific identity

`stage02_logical_dataset_sha256_v1` uses domain
`SAFE_STAGE02_LOGICAL_DATASET_V1` and typed length-delimited binary encoding. It
binds the Stage 2 contract, output schema, structural-metadata version, fixed
Orbis representation provenance/relationship, input kind and contract,
upstream logical identity, source-population identity, input schema fingerprint,
and expected row count.

Physical input/output paths, shard count and boundaries, Parquet byte hashes,
compression, Git/runtime identity, timestamps, host, SLURM job, and permissions
are excluded. Those values remain physical or operational provenance. Thus the
same accepted logical input produces the same Stage 2 identity under a
different valid physical layout.

## Validation and publication

Stage 2 validates exact schemas and Parquet page checksums; owner-only input;
input hashes before and after processing; canonical provenance order; source
path/SHA consistency; duplicate source-content exclusion; and recomputed
`stable_source_row_id_v1`. It writes the original Arrow arrays directly,
derives only the four structural arrays, then independently rereads input and
output and requires exact Arrow value equality.

The output contains owner-only Parquet shards, `stage02_manifest.json`, and
`_SUCCESS.json`. Publication is atomic: work remains under an in-progress
directory until all validation passes, the marker is removed, and the complete
directory is renamed. The terminal validator rechecks topology, modes, hashes,
schema metadata, page checksums, row counts, stable IDs, source identities, and
structural fields. A manifest SHA is returned for external adoption.

Directories are `0700`; files are `0600`. Errors contain stable codes and no
source values. The protected manifest contains identities and artifact hashes,
not address examples.

## Execution and boundary

Synthetic runs use the Python API with `production=False`. Protected execution
uses `safe-geocoding-stage02` through
`cluster/goethe_nhr/stage02_harmonization.sbatch`; the shared Goethe/SLURM guard
runs before input access. A future DEVELOPMENT run supplies only the accepted
development artifact and a reviewed binding. It does not inspect HOLDOUT.

Stage 2 stops at schema/provenance harmonization. Its sanitized evidence and
protected fixed-row qualitative interface use the separate passive reporting
framework in `docs/DEVELOPMENT_REPORTING.md`; reporting does not alter Stage 2
science. Stage 3 minimal text cleaning is separate and has not started.
