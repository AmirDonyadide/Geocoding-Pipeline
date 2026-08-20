# Stage 1 — lossless CSV-to-Parquet ingestion

## Status

**STAGE_1_ACCEPTED.** Stage 1 passed its final critical review and complete
local-safe validation. Stage 2 has not started.

## Purpose and reuse boundary

Stage 1 represents every source record from the exact accepted Stage 0 snapshot
in one logical Parquet dataset. Lossless means preservation of the authoritative
decoded CSV field values and source provenance. It does not mean reconstructing
CSV quoting, delimiter, BOM, or line-ending bytes from Parquet; Stage 0 retains
the original source-file hashes for raw-byte identity.

Historical Phase 2 remains the single authoritative CSV-to-Parquet converter.
The library-first module
`safe_geocoding_pipeline.preprocessing.stages.s01_ingestion` validates,
fingerprints, and adopts a completed Phase 2 bundle. It contains no CSV reader,
Arrow/Parquet writer, semantic-digest calculator, stable-ID generator, or
reconciliation engine.

Stage 1 performs no text cleaning, Unicode normalization, address
reconstruction, parsing, correction, address deduplication, or geocoding.

## Stage 0 binding

Adoption requires the exact Stage 0 adoption-record SHA-256 and validates its
accepted contract, scientific fingerprints, parser-contract fingerprint,
Phase 1 run and producing commit, artifact identities, terminal state, and
complete file inventory. The existing Stage 0 Phase 1 validator remains
authoritative.

Stage 1 then proves exact equality between the Stage 0/Phase 1 and Phase 2
projections for every canonical source path:

- source relative path;
- raw source-file SHA-256;
- logical source-row count.

No source CSV is opened during adoption, and file count alone is never accepted
as population evidence.

For a new `FULL_CONVERSION`, the Phase 2 CLI requires both the accepted Stage 0
adoption record and its exact SHA-256. The hash-pinned record resolves the
Phase 1 run, canonical source paths, source hashes, logical counts, and Stage 0
scientific identities. The source directory must match that path set exactly
before conversion and remain unchanged through reconciliation. No default
population count or directory-discovery fallback is permitted.

## Source-row identity

Stage 1 reuses `stable_source_row_id_v1` unchanged:

```text
SHA-256(
  UTF8("safe_geocoding_pipeline:stable_source_row_id_v1\0")
  || raw 32-byte source_file_sha256
  || unsigned 64-bit big-endian one-based logical record number
)
```

The identifier excludes address values, provider ID, source path, and physical
Parquet placement. Exact duplicate source-file content would therefore collide
at matching ordinals. Stage 1 fails closed on duplicate source SHA values and
on any non-unique global stable-ID reconciliation; it does not add a path or
silently remove a source file. `address_id` belongs to later Stage 5, not Stage
1.

## Logical dataset fingerprint

`stage01_logical_dataset_sha256_v1` uses SHA-256 and the exact domain bytes
`SAFE_STAGE01_LOGICAL_DATASET_V1`. Every encoded value has an explicit one-byte
type tag:

- `0x01 || U64_BE(value)` for unsigned integers;
- `0x02 || U64_BE(UTF8 byte length) || UTF8 bytes` for text;
- `0x03 || raw 32-byte digest` for SHA-256 values.

The encoded field order is:

1. Stage 1, Stage 0, and Phase 1 inventory contract versions;
2. Stage 0 source-population, scientific-inventory, and parser-contract
   fingerprints;
3. Phase 2 parser, source-schema, and staging versions;
4. exact Arrow schema fingerprint;
5. stable-source-row-ID and raw-semantic-digest versions;
6. source-file count and total logical row count;
7. for each source in canonical Stage 0 relative-path order: relative path,
   raw source SHA-256, logical row count, and matching
   `raw_semantic_digest_v1`.

The digest excludes Parquet names/paths, output shard count and boundaries,
row groups, compression, page layout, Parquet sizes and hashes, Git/runtime
versions, timestamps, host, and SLURM identity. A physical repartition of the
same logical records and provenance therefore does not change logical identity.
Golden fictional vectors are frozen in `tests/test_stage01_ingestion.py`.

## Physical bundle validation

The Stage 1 validator fails closed unless the completed Phase 2 bundle has:

- an exact manifest and matching full-conversion success marker;
- no contradictory failure/scope/in-progress state and an empty
  `.in_progress` directory;
- the exact manifest-declared non-symlink Parquet shard set;
- matching shard sizes and SHA-256 values;
- exact Arrow schema and required provenance metadata;
- matching source/staging row counts and raw semantic digests;
- complete Phase 2 SQLite state and attempt history;
- state output hashes/sizes, configuration identities, run metadata, and final
  attempt evidence matching the manifest;
- passing global row, null, schema, and stable-ID reconciliation;
- matching schema, run, reconciliation, file-validation, failure, and summary
  reports;
- recorded successful page-checksum read-back evidence;
- owner-only controlled directories/files; and
- unchanged file identities and exact run/data/work/progress/report directory
  topology between validation and adoption publication.

Full production shard hashing is guarded by the shared execution policy and
must run under Goethe-NHR/SLURM. Matching historical Parquet hashes bind the
current bytes to the files whose pages were independently checksum-read during
Phase 2.

SQLite validation never opens the authoritative database. A completed bundle
must have no non-empty WAL; the database is copied into an owner-only temporary
directory and the copy is integrity-checked and queried there. Authoritative
database, WAL, and SHM identities and protected-tree membership are checked
again before adoption publication.

## Output and identity separation

The existing Phase 2 data directory, `dataset_manifest.json`, and
`_SUCCESS.json` remain authoritative and byte-immutable. Stage 1 writes only an
owner-only `stage01_adoption.json`; it creates no second row-level manifest and
no Parquet copy.

The adoption record separates:

- **scientific identity:** Stage 0/1 contracts and fingerprints, Phase 1/2
  scientific versions, schema, stable-ID/semantic-digest contracts, source and
  row counts, and the logical dataset fingerprint;
- **physical identity:** Phase 2 run, manifest/marker/state/report identities,
  physical shard count/bytes, and a hash-bound reference to the existing
  manifest's per-shard size/SHA entries; and
- **operational provenance:** full producing/adopting Git commits, runtime
  versions, environment, and adoption time.

The adoption record does not hash itself recursively. Its external SHA-256
identifies its exact operational bytes.

## Current physical layout

The current accepted physical decision is `KEEP_CURRENT_SHARDS`: 206 existing
Phase 2 Parquet files form one logical dataset. Stage 1 does not compact,
rewrite, repartition, change compression, or change row groups.

One source per Parquet file is a historical Phase 2 v1 layout, not a permanent
scientific rule. A future source population may use benchmarked target-sized
shards while retaining the same source provenance and logical identity. Future
scope must derive from its accepted Stage 0 contract rather than a global
206-file constant.

Phase 2 restart state binds the Stage 0 adoption and scientific identities,
the Phase 1 manifest identity, and every source path/hash/size/logical count. A
run created for one accepted population cannot resume after source membership
or identity changes. The first accepted production result remains the immutable
historical 206-source snapshot; that observation is not a generic execution
constraint.

## Privacy, permissions, and failures

Controlled run, data, work, and in-progress directories are mode `0700`;
controlled files are mode `0600`. Symlinks and special files are rejected.
Sanitized historical reports are hash-bound but contain no raw address, city,
postcode, native-address, or raw-ID values. The compact adoption record contains
only contracts, counts, hashes, versions, statuses, and operational provenance.

Missing, malformed, partial, contradictory, changed, permission-invalid,
schema-invalid, digest-mismatched, duplicate-source, duplicate-stable-ID,
corrupt, or unexpected output fails adoption. Nothing is repaired or promoted
partially, and output collisions are never overwritten.

## Acceptance and Stage 2 boundary

Stage 1 acceptance establishes exact Stage 0 binding; one-for-one lossless
record preservation; unchanged stable IDs; deterministic layout-independent
logical identity; complete physical integrity, read-back evidence,
reconciliation, terminal state, and permissions; privacy-safe portable
metadata; adoption of the existing complete Phase 2 dataset without source
rescan or Parquet rewrite; and an explicit stop before Stage 2.
