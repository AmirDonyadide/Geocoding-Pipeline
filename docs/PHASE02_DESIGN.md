# Phase 2 design — controlled staging dataset

## Status

This finalized Phase 2 design is approved in principle. It does not authorize implementation, a real-data smoke conversion, or the complete 206-file conversion.

Phase 2 is lossless controlled staging only. It preserves every verified source observation and its provenance without cleaning, normalization, semantic missing-value interpretation, address parsing, canonicalization, deduplication, eligibility classification, Parquet reuse from previous work, or geocoding.

## Authoritative input snapshot

Phase 2 is designed for the exact Phase 1 source snapshot with input-manifest SHA-256:

`94254dadab515194a4d292f7095107f94c58508d83d7bf70d63608dc8002bba8`

That snapshot contains:

- 206 immutable direct-child CSV files;
- exactly 3,285,318,564 source bytes;
- exactly 20,600,000 logical records;
- exactly 100,000 records per file;
- one verified strict UTF-8, comma, header, double-quote, 15-column parser contract;
- no parser, encoding, schema, wrong-column, incomplete-file, source-change, or exact duplicate-file failures;
- 20,600,000 non-empty globally unique source `id` values under exact UTF-8/BINARY comparison.

These findings are validation expectations, not values that Phase 2 may force or fabricate.

## Boundary

Phase 2 must not:

- strip, collapse, or otherwise clean whitespace;
- normalize Unicode, countries, postcodes, or address text;
- convert placeholder-like strings to null;
- infer structured geography from free-form lines;
- convert `id`, postcode, or `batch_priority` to numeric values;
- select native versus non-native address fields;
- construct canonical addresses or an `address_key`;
- deduplicate source observations or addresses;
- determine geocoding eligibility or analytical usability;
- call SAFE/Pelias;
- read the historical `parquet_files` collection as staging truth;
- start Phase 3.

## Architecture

```text
Phase 1 manifest + immutable source CSV
    -> verify source identity and metadata
    -> parse with the approved strict Python csv.reader contract
    -> compute raw_semantic_digest_v1 while preserving exact strings
    -> add deterministic provenance in bounded Arrow batches
    -> write a temporary PyArrow Parquet file
    -> close and independently read the temporary Parquet file
    -> verify page checksums, schema, values, provenance, and digests
    -> atomically promote only a per-file PASS
    -> reconcile all completed Parquet files exactly
    -> write the dataset manifest and final success marker
    -> STOP
```

Python's standard-library CSV reader remains the authoritative source parser. PyArrow is the primary Arrow/Parquet writer and reader. DuckDB may perform exact global validation over completed Parquet only; it must not parse source CSV during Phase 2. A small SQLite database may track the 206 file states and attempts, but no new 20.6-million-row ID occurrence store is required.

## Exact staging schema

All 22 columns are non-null and have this exact order:

| Position | Column | Arrow type | Meaning |
|---:|---|---|---|
| 1 | `id` | `string` | Exact raw source value. |
| 2 | `street_address_line_1` | `string` | Exact raw source value. |
| 3 | `street_address_line_2` | `string` | Exact raw source value. |
| 4 | `street_address_line_3` | `string` | Exact raw source value. |
| 5 | `street_address_line_4` | `string` | Exact raw source value. |
| 6 | `street_address_line_1_native` | `string` | Exact raw source value. |
| 7 | `street_address_line_2_native` | `string` | Exact raw source value. |
| 8 | `street_address_line_3_native` | `string` | Exact raw source value. |
| 9 | `street_address_line_4_native` | `string` | Exact raw source value. |
| 10 | `postcode` | `string` | Exact raw source value; never numeric. |
| 11 | `city` | `string` | Exact raw source value. |
| 12 | `region_in_country` | `string` | Exact raw source value. |
| 13 | `country_iso_code` | `string` | Exact raw source value; not normalized or ISO-validated here. |
| 14 | `batch_priority` | `string` | Exact raw source value; never numeric. |
| 15 | `location_information` | `string` | Exact raw source value; not an eligibility decision. |
| 16 | `source_file` | `string` | Portable POSIX relative path beneath the approved source root. |
| 17 | `source_logical_record_number` | `uint64` | One-based data-record number, excluding the header. |
| 18 | `stable_source_row_id_v1` | `fixed_size_binary[32]` | Raw 32-byte deterministic provenance identifier. |
| 19 | `source_file_sha256` | `fixed_size_binary[32]` | Raw 32-byte Phase 1 source-file SHA-256. |
| 20 | `source_schema_version` | `string` | Fixed value `source_csv_15col_v1`. |
| 21 | `parser_version` | `string` | Version of the approved strict CSV parser contract. |
| 22 | `staging_version` | `string` | Fixed value `phase02_v1`. |

The 15 raw values are passed exactly from the verified CSV parser to explicit Arrow `string` arrays. No pandas-style null inference is allowed. `None` in a raw Arrow array is a conversion failure.

Standard Arrow `string` is sufficient for the verified current snapshot and provides the preferred interoperability. If smoke testing exposes a real 32-bit Arrow string-buffer capacity problem, the run must stop and report it. The implementation must not silently switch to `large_string` or produce a mixed schema.

Empty source fields remain non-null zero-length strings. Literal `.`, `-`, `Na`, `Nan`, and `Null` values remain non-null literal strings.

File-level Parquet metadata records the Phase 1 run and input-manifest identity, pipeline Git commit, parser and staging configuration fingerprints, source relative path and SHA-256, stable-ID version, and semantic-digest version. It must contain no raw address, native-address, city, postcode, or ID value.

## `stable_source_row_id_v1`

Use this exact construction:

```text
SHA-256(
    UTF-8 bytes of "safe_geocoding_pipeline:stable_source_row_id_v1\0"
    || raw 32-byte source_file_sha256
    || source_logical_record_number encoded as unsigned 64-bit big-endian
)
```

The logical record number is one-based and excludes the CSV header. The stored value is the raw 32-byte digest; reports may represent it as lowercase hexadecimal when necessary.

The construction excludes provider `id`, filename, source schema version, parser version, and staging version. It therefore represents immutable source-content identity plus logical position. `source_file` and `source_logical_record_number` remain separate for human diagnosis. This identifier is not the later address-deduplication key.

Golden test vectors must fix the exact domain bytes, byte order, and digest output.

## `raw_semantic_digest_v1`

This digest covers the ordered values of the original 15 raw columns only. Provenance columns are validated independently.

Define these binary primitives:

- `U64(n)`: unsigned 64-bit big-endian encoding of `n`;
- `LP(bytes)`: `U64(byte_length) || bytes`;
- domain: UTF-8 bytes of `safe_geocoding_pipeline:raw_semantic_digest_v1\0`.

Hash the following stream with SHA-256:

1. The fixed domain bytes.
2. `LP` of the source schema version `source_csv_15col_v1`.
3. `U64(15)`.
4. `LP` of each exact UTF-8 column name in source-column order.
5. For each logical source row in order:
   - one-byte row marker `0x52`;
   - `U64` of its one-based logical row ordinal;
   - for each of the 15 fields in order:
     - null: one-byte tag `0x00`;
     - non-null: one-byte tag `0x01`, followed by `LP` of the exact strict UTF-8 value.
6. One-byte footer marker `0x46` followed by `U64` of the total logical row count.

Source fields are required to take the non-null branch. Empty string is therefore `0x01 || U64(0)`, which is distinct from null and from every literal placeholder-like value.

The source digest is calculated during authoritative CSV parsing. After the Parquet writer is closed, the staging digest is independently recalculated by reading only the 15 raw Parquet columns in physical row order and applying the same versioned serialization. Equality is mandatory. Golden test vectors must demonstrate field-boundary, row-boundary, empty/null, Unicode, and column-order behavior.

## Source identity and stability

For each file:

1. Confirm its portable relative path and expected Phase 1 manifest entry.
2. Record source size and modification metadata before parsing.
3. Parse and write only to a temporary staging path.
4. Record metadata after parsing.
5. Calculate a fresh raw-byte SHA-256 and compare it with Phase 1.
6. Record metadata after hashing.
7. Fail the file if its identity differs or metadata indicates a change.

Source files remain read-only and must be fully hydrated. Pausing OneDrive synchronization is recommended for a real run. Phase 2 never copies, rewrites, renames, or moves source files automatically.

## Layout

Use an immutable run-specific, one-to-one layout:

```text
staging/
  controlled/
    phase02_v1/
      runs/
        <run_id>/
          data/
            remaining_addresses_00001.parquet
            ...
          dataset_manifest.json
          _SUCCESS.json
```

Exactly one controlled Parquet file corresponds to each source CSV. The source filename stem is retained because all current direct-child names are unique. There is no automatic `CURRENT` pointer. Downstream work must reference an explicit completed run ID.

The historical `parquet_files/` collection is invalid reference material only and is never read as validation truth, overwritten, or reused.

## Parquet configuration

The provisional smoke-test configuration is:

| Setting | Value |
|---|---:|
| Compression | ZSTD |
| ZSTD level | 3 |
| Normal write batch | 25,000 rows |
| Normal row group | 25,000 rows |
| Extreme-row isolation | 1 MiB UTF-8 content |
| Page checksums | Enabled and verified on read-back |

The 1 MiB isolation threshold is memory management only. It is unrelated to the Phase 1 1,024-character anomaly-warning threshold. A 21,846-character value can be a Phase 1 content anomaly without requiring a singleton Phase 2 row group. A value around 19.4 million characters is isolated into a singleton batch and row group. No threshold authorizes rejection, truncation, or modification.

Use dictionary encoding only for approved low-cardinality or repeated fields such as `country_iso_code`, `batch_priority`, `location_information`, `source_file`, source/parser/staging version columns, and, subject to compatibility tests, the repeated source-file hash. Do not dictionary-encode raw address/native fields, city, postcode, `id`, or stable row IDs.

Disable min/max statistics for address/native fields, city, postcode, `id`, and stable identifiers. Statistics may be enabled for `source_logical_record_number` and the approved low-risk categorical fields. Tests must inspect Parquet key-value and column metadata and prove that prohibited raw sensitive values do not appear there.

Page checksums are mandatory. Temporary-file validation must explicitly enable checksum verification while reading every page. A supported PyArrow version and a technically feasible corruption test must prove that a checksum-invalid Parquet file fails validation; checksum support may not be silently disabled.

Compression, batch size, row-group size, dictionary selection, and resource limits are operational settings subject to smoke evidence. They are not scientific rules.

## Memory and extreme records

Process one source file at a time. Hold only the current logical record, bounded column buffers, one Arrow write batch, digest state, and small validation counters.

When a record crosses the configured 1 MiB UTF-8 isolation threshold:

1. flush any current normal batch;
2. construct and write a singleton Arrow batch and Parquet row group;
3. resume normal batches without changing source order.

The known `remaining_addresses_00205.csv` maximum field must remain exactly 19,413,972 characters after conversion. Its logical record remains one Parquet row despite spanning 95,462 physical source lines. Phase 1 anomaly provenance supplies the expected source file, logical record, field, character length, and value hash for targeted validation without exposing content.

## Per-file validation and promotion

A file receives PASS only if:

- source path, size, modification metadata, and fresh SHA-256 match the Phase 1 identity;
- the approved strict parser completes without an alternate dialect or salvage behavior;
- exactly 100,000 logical source rows are read;
- exactly 100,000 Parquet rows are read back;
- all 22 columns have the exact approved order, type, and non-nullability;
- every raw column has zero nulls and is Arrow `string`;
- source and staging `raw_semantic_digest_v1` values match;
- per-column source/staging empty-string and non-ASCII counts match;
- postcode remains a string and source IDs retain their exact order and count;
- `source_file`, source-file hash, and version columns contain the exact expected constants;
- logical record numbers are exactly ordered `1..100000` as `uint64` with no gap or duplication;
- every stable source-row ID recomputes correctly and is unique within the file;
- every Phase 1 extreme record in the file retains its field, length, value hash, and logical-row identity;
- the complete temporary Parquet file is read with successful page-checksum verification;
- the exact final output byte size and SHA-256 are recorded;
- logs and reports contain no confidential raw values.

Failure is file-level. There is no row salvage, `ignore_errors`, `null_padding`, alternate parser, truncation, or permissive recovery. A failed temporary file cannot be promoted.

## Dataset-level reconciliation

After every per-file promotion, DuckDB may scan completed Parquet files using exact default binary equality and bounded memory/spill settings. It must not read source CSV.

Required validation expectations are:

| Check | Expected from Phase 1 |
|---|---:|
| Controlled Parquet files | 206 |
| Total rows | 20,600,000 |
| Files with 100,000 rows | 206 |
| Distinct raw `id` values | 20,600,000 |
| Distinct `stable_source_row_id_v1` values | 20,600,000 |
| Raw-column nulls | 0 |
| Failed files | 0 |

These values are checked, never injected or fabricated. Reconciliation also requires exact source/output filename sets, one approved schema fingerprint, no missing/extra/temporary Parquet files, all source/staging semantic-digest pairs equal, all output hashes matching the dataset manifest, and no duplicate or missing original/stable IDs.

Any mismatch fails the overall Phase 2 gate.

## Atomicity and restartability

Maintain a small ignored run-state SQLite database for source/configuration identity, output identity, semantic digests, attempt history, timestamps, status, and failure codes. Operational states may include `PENDING`, `WRITING`, `VALIDATING`, `COMPLETE`, and `FAILED`.

For each file:

1. write an attempt-specific `.parquet.tmp` file under an `.in_progress` directory on the same filesystem as the final output;
2. close and flush the writer;
3. independently read and validate the entire temporary file;
4. compute its exact SHA-256;
5. flush the file and parent directory where supported;
6. atomically rename it to its final `data/*.parquet` path;
7. commit COMPLETE state.

On resume:

- `PENDING` files are processed normally;
- `FAILED` files may restart from the beginning only when source and configuration identities remain exact, with previous failure history retained and abandoned temporary output quarantined;
- `COMPLETE` files are reusable only after their source identity, configuration/Git version, final hash, schema, row count, and validation record are reconfirmed.

A conflicting or corrupt COMPLETE file fails the run and requires a new run ID; it is not silently overwritten. An incomplete run has no `_SUCCESS.json` and cannot be consumed as approved staging. The immutable dataset manifest is written atomically after global reconciliation, and `_SUCCESS.json` is written last.

## Generated outputs

The controlled staging run contains:

- `data/*.parquet`: 206 lossless source-aligned shards after a successful full run;
- `dataset_manifest.json`: source/output mappings, hashes, sizes, row counts, schema fingerprint, semantic digests, versions, and per-file status;
- `_SUCCESS.json`: final gate record containing run ID, manifest hash, Git commit, file/row/byte totals, and completion time.

Generated reports belong under `reports/generated/phase02/<run_id>/`:

- `phase02_run.json`;
- `phase02_file_validation.csv`;
- `phase02_schema.json`;
- `phase02_reconciliation.json`;
- `phase02_failures.csv.gz`;
- `phase02_summary.md`.

Reports contain counts, paths relative to approved roots, hashes, versions, statuses, error codes, timings, and resource metrics. They never contain raw addresses, native values, city values, postcode values, raw IDs, full rows, or value previews.

## Error handling and privacy

Use explicit stable failure codes for at least source-identity mismatch, source change, parser failure, Arrow capacity/conversion failure, Parquet write failure, Parquet read/checksum failure, schema mismatch, row-count mismatch, semantic-digest mismatch, provenance mismatch, stable-ID mismatch, known-extreme mismatch, output corruption, and atomic-promotion failure.

Errors fail the affected file, preserve privacy-safe diagnostics, and allow other files to continue where safe. Any failed or incomplete file fails the overall gate. No exception path may print a full record or raw field value. Hashes, lengths, column names, relative paths, and logical record numbers are sufficient diagnostics.

## Testing

Unit tests must cover:

- the exact 22-column Arrow schema and non-nullability;
- exact raw-string preservation without missing-value or numeric inference;
- empty string versus `.`, `-`, `Na`, `Nan`, and `Null`;
- leading-zero, decimal-looking, alphabetic, alphanumeric, spaced, and hyphenated postcodes;
- Unicode and native/non-native fields;
- stable-row-ID golden vectors and `uint64` record-number encoding;
- semantic-digest golden vectors, boundaries, empty/null distinction, Unicode, row order, and column order;
- configuration and schema fingerprints;
- privacy-safe logs, Parquet metadata, and reports.

Synthetic integration tests must cover:

- embedded commas, doubled quotes, and quoted multiline records;
- a generated extreme field at approximately the known 19.4-million-character scale;
- normal versus singleton extreme-row batching without changed row order;
- exact source/staging digest equality and deliberate value/order/schema/count mismatch detection;
- provenance and stable-ID mismatch detection;
- interrupted writes and absence of premature promotion or success markers;
- atomic promotion and PENDING/FAILED/COMPLETE resume behavior;
- changed-source detection;
- truncated or corrupted Parquet output;
- explicitly enabled page-checksum validation and rejection of a checksum-invalid file where technically feasible;
- staging-row loss, duplication, and reordering;
- exact global reconciliation over fictional multi-file data.

Large fixtures are generated in temporary directories at test time and contain fictional values; they are not committed as large static files.

## Real-data smoke gate

The proposed, not-yet-authorized smoke inputs are:

- ordinary: `remaining_addresses_00103.csv`;
- extreme: `remaining_addresses_00205.csv`.

The smoke run must use the intended production parser, schema, Parquet configuration, digest, identity, atomicity, and validation paths. It must report exact row and digest reconciliation, provenance correctness, preservation of the 19,413,972-character and 95,462-physical-line record, page-checksum verification, runtime, peak memory, temporary and final sizes, compression ratio, row-group layout, and bounded DuckDB reconciliation.

The user must review the smoke results before authorizing the full 206-file conversion. Runtime and final resource estimates remain unknown until that benchmark.

## Execution environment and resources

The MacBook remains the default environment. The verified 3.29 GB scale does not justify Goethe-NHR automatically.

Provisional planning, subject to smoke evidence, is:

- one source file processed at a time;
- normal conversion memory target below approximately 1 GiB;
- bounded DuckDB validation memory with local spill;
- at least 20 GiB free local space before a full run;
- no distributed processing.

Exact PyArrow/DuckDB versions, runtime, staging size, DuckDB memory/spill limits, and any revised free-space requirement are implementation decisions to establish through compatibility tests and smoke measurement.

## Completion and STOP gate

Phase 2 passes only when:

- the approved implementation passes all unit and synthetic integration tests;
- the separately authorized ordinary/extreme real-data smoke run passes and is reviewed;
- the complete conversion has received separate explicit authorization;
- all 206 source files exactly match the Phase 1 source identities;
- all 206 files receive per-file PASS and atomic promotion;
- exactly 206 controlled Parquet files contain exactly 20,600,000 rows, with exactly 100,000 rows each;
- every raw field is an exact non-null Arrow `string` and every per-file source/staging semantic digest matches;
- all provenance columns and stable source-row IDs validate for every row;
- distinct raw ID and stable source-row ID counts both equal 20,600,000, with no missing or duplicate values;
- all known multiline and extreme values are preserved exactly;
- page checksums are enabled and verified;
- no failed, incomplete, corrupt, missing, extra, or temporary file remains in the approved data set;
- all output hashes, schema fingerprints, manifests, and reports reconcile;
- generated artifacts and metadata are privacy-safe;
- the final dataset manifest and `_SUCCESS.json` are present;
- a sanitized `docs/PHASE02.md` is reviewed;
- the user explicitly approves Phase 2 completion.

Any failed condition makes the Phase 2 gate FAIL and prevents the run from serving Phase 3. The project then stops and does not begin Phase 3 automatically.

## Remaining implementation decisions

- Exact compatible PyArrow and DuckDB version pins.
- Parquet physical format/data-page version compatible with required page checksums and readers.
- Exact API and corruption-fixture method for proving page-checksum verification.
- Exact parser/staging/configuration fingerprint serialization.
- Exact run-ID format and SQLite run-state schema/pragmas.
- DuckDB memory limit, spill limit/location, and exact global-validation queries.
- Temporary-output quarantine and retention policy.
- Exact artifact permission/access controls for confidential lossless staging data.
- Smoke benchmark acceptance limits and any evidence-based revisions to operational batch, row-group, compression, memory, disk, or runtime settings.
- Separate approvals to implement Phase 2, run the real-data smoke conversion, and run the complete 206-file conversion.
