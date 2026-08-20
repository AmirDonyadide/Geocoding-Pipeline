# Stage 0 — source freeze, inventory, and reproducibility

## Status

**IMPLEMENTED_PENDING_FINAL_REVIEW.** Stage 0 has not received final acceptance,
and Stage 1 is not authorized.

## Purpose and reuse boundary

Stage 0 answers “what exactly did we receive?” before any cleaning, address
reconstruction, deduplication, parsing, normalization, correction, query
generation, or geocoding.

Historical Phase 1 remains the single authoritative source scanner. Its strict
streaming CSV parser, source hashing, schema/count diagnostics, duplicate
analysis, privacy-safe reports, SQLite restart state, and execution-policy guard
are reused unchanged. The library-first module
`safe_geocoding_pipeline.preprocessing.stages.s00_inventory` only validates,
projects, fingerprints, and adopts a completed Phase 1 bundle. It has no source
CSV reader and delegates any future scan to `phase01.run_inventory`.

## Input contract

For the current snapshot, the source population is exactly the 206 regular,
non-symlink, direct-child CSV files discovered by Phase 1 in ascending portable
relative-path order. Original files are read-only. Duplicate content is
reported but no source path is removed. The approved parser contract is strict
UTF-8 with an optional UTF-8 BOM, `newline=""`, comma delimiter, double-quote
quoting, doubled quotes, no escape character, no initial-space skipping,
`strict=True`, the exact ordered 15-column source schema, and a 64 Mi-character
field safety ceiling.

A changed delivery requires a new versioned source-population contract. Stage 0
does not detect or substitute an alternative encoding or dialect.

## Output and adoption contract

The authoritative inventory remains the completed Phase 1 bundle. Stage 0 does
not copy its 206 rows and does not create a redundant Parquet inventory. The
owner-only `stage00_adoption.json` binds:

- the Stage 0, validation, Phase 1, and parser contracts;
- the full Phase 1 producing Git commit;
- the two scientific fingerprints;
- byte size and SHA-256 for all eight Phase 1 artifacts, including
  `phase01_run.json`;
- byte size and SHA-256 for `_SCOPE_PASS`, plus the required absence of
  `_SCOPE_FAIL` and `_IN_PROGRESS`;
- operational adoption provenance and permission-hardening results;
- explicit validation gates and `IMPLEMENTED_PENDING_FINAL_REVIEW` status.

The adoption record does not hash itself. Its external SHA-256 identifies the
exact operational record.

## Fingerprints

### `source_population_sha256_v1`

SHA-256 receives the ASCII domain bytes
`SAFE_STAGE00_SOURCE_POPULATION_V1`, followed immediately by:

1. file count as unsigned 64-bit big-endian;
2. for each relative-path-sorted file: UTF-8 path length as unsigned 64-bit
   big-endian, exact path bytes, file size as unsigned 64-bit big-endian, and
   raw 32-byte file SHA-256.

### Parser-contract fingerprint

SHA-256 receives `SAFE_STAGE00_PARSER_CONTRACT_V1`, then the Phase 1 inventory
version, ordered source-column count and names, encoding/BOM policy, newline and
CSV dialect fields, and hard parser ceiling. Text uses an unsigned 64-bit
big-endian UTF-8 byte-length prefix; Booleans are one byte; nullable text uses a
one-byte null/value tag; integers are unsigned 64-bit big-endian; digests are
raw 32-byte values.

### `stage00_scientific_inventory_sha256_v1`

SHA-256 receives `SAFE_STAGE00_SCIENTIFIC_INVENTORY_V1`, then the Stage 0 and
Phase 1 contract versions, raw parser-contract and source-population digests,
record count, and the declared deterministic inventory projection in sorted
file order using the same typed encoding.

Timestamps, mtimes, durations, host, SLURM identity, Git revision, Python and
SQLite versions, and permissions are operational provenance and never affect
either scientific fingerprint.

Golden fictional vectors are frozen in `tests/test_stage00_inventory.py`.

## Privacy and permissions

Source CSVs and retained `_work` state are protected. `_work` directories are
mode `0700`; retained files, especially `phase01.sqlite3`, are mode `0600`.
Hardening rejects symlinks and special files, never traverses the source root,
and does not change artifact bytes. New Stage 0 output directories are `0700`
and files are `0600`.

The eight Phase 1 reports and Stage 0 adoption record contain source identity,
structural counts, hashes, and approved aggregate diagnostics, but no raw
address, city, postcode, native-address, or raw-ID values. They remain internal
research metadata rather than public artifacts.

## Failure behavior

Adoption fails closed for missing, unsafe, size-mismatched, or hash-mismatched
artifacts; incomplete or contradictory markers; malformed manifest schema;
duplicate paths; non-sequential file IDs; source-population mismatch;
unapproved parser contract; unsuccessful/incomplete file rows; unsafe working
state; permission failure; or output collision. A failed bundle is never
partially adopted or repaired.

## Existing production adoption

The validator confirms that Phase 1 run
`phase01_20260810T151626Z_7df9bc8f`, produced by
`7df9bc8f6a43e279eb56247091a23a1d070ef475`, contains 206 complete files and
passes artifact, terminal-state, parser, manifest, and population validation.
No source CSV was opened for adoption.

- parser-contract fingerprint:
  `c68895992f58afc7ef22d45ec3df21e49ff97339641d57559d9e961333c1feb9`
- source-population fingerprint:
  `bdedb3f425a337048aaf21245b76246f92a36693cdbf0e28acb16f18b14fffc3`
- scientific-inventory fingerprint:
  `bd56d00c06e8711bf80a9dd08eb9630959119782e81bc58c058d00aa0cdba3a2`

The historical Phase 1 artifact bytes remain unchanged. Permission changes to
retained working state are operational privacy hardening only.

## Review gate and Stage 1 boundary

Prompt 3 must independently review the implementation, canonical encodings,
golden vectors, bundle validation, historical artifact integrity, permissions,
and adoption record before Stage 0 can be accepted. Until then, the status
remains `IMPLEMENTED_PENDING_FINAL_REVIEW`. Stage 0 emits no staging rows and
does not authorize or begin Stage 1.
