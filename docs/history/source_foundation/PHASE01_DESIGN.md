# Phase 1 design — raw file inventory

## Status

The Phase 1 design is approved in principle with the revisions recorded here. Implementation and the complete 206-file run are not approved.

This document is authoritative for Phase 1 design together with `AGENTS.md` and `docs/DECISIONS.md`. `docs/PROJECT_BRIEF.md` remains the detailed project reference.

## Objective and boundary

Phase 1 establishes the real contract and diagnostic profile of the immutable current source collection:

- 206 CSV files;
- approximately 3.29 GB apparent total size;
- located in the previously inspected `csv_files` directory.

Phase 1 inventories and diagnoses. It does not:

- normalize missing markers;
- clean or correct addresses;
- infer cities, regions, or countries from free-form lines;
- determine geocoding eligibility;
- create canonical addresses;
- deduplicate addresses;
- create staging Parquet;
- call SAFE/Pelias;
- begin Phase 2.

CSV/parsing validity and content/data-quality anomalies are separate. A syntactically valid 19-million-character field is a content anomaly, not automatically malformed CSV.

## Architecture

```text
configured immutable source root
    -> deterministic file discovery and bounded preflight
    -> one strict logical CSV parsing pass
       -> file/record/schema/field profiles
       -> multiline and content anomalies
       -> compact exact SQLite ID state
    -> one separate sequential raw-byte SHA-256 pass
    -> duplicate-file and duplicate-ID analysis
    -> durable generated reports
    -> sanitized docs/history/source_foundation/PHASE01.md after review
    -> STOP
```

The implementation is intentionally local, sequential, and bounded-memory. It does not use Spark, Dask, or a distributed stack.

## Technology

The authoritative parser is Python's standard-library `csv` module. SQLite provides exact temporary ID working state, and `hashlib` computes file fingerprints. DuckDB may later provide an independent cross-check, but it must not replace or weaken the authoritative parser.

This combination is preferred because it provides explicit logical-record handling, precise failure behavior, exact string semantics, low memory use, straightforward tests, and portability between macOS and Goethe-NHR without unnecessary infrastructure.

## Source discovery and stability

The source root is configuration, not a hardcoded business-logic path. Discovery is non-recursive over direct `*.csv` files, does not follow symlinks, and sorts portable relative paths deterministically before assigning `file_id`.

Before a complete run:

- all 206 files must be fully hydrated locally;
- adequate local free space must be confirmed;
- the source collection must not be actively modified;
- pausing OneDrive synchronization is recommended when practical;
- no source file is copied, rewritten, renamed, moved, or otherwise modified automatically.

For each file, record size and modification metadata before parsing, after parsing, and after hashing. If these values change, mark the file incomplete with `FILE_CHANGED_DURING_SCAN`. The exact hash is also retained. A changed file cannot pass the Phase 1 gate.

## Pass strategy

### Bounded preflight

Read only enough data to collect filesystem metadata, inspect a BOM, and parse the first logical record under the expected contract. Heuristic dialect detection may be used only to explain a failure; it never silently selects an alternative parser.

### Full logical CSV parsing passes

Exactly one full logical CSV parsing pass is planned. It collects row, schema, field, identity, multiline, and content diagnostics simultaneously.

### Raw byte hashing passes

Use one separate sequential raw-byte pass per file to compute SHA-256. This is deliberately separate from `TextIOWrapper` and `csv.reader` so hashing remains simple, exact, and independently testable. At approximately 3.29 GB, the additional sequential read is acceptable.

Additional source reads are limited to targeted diagnosis of failed files and, if approved, byte-for-byte confirmation of equal-size/equal-hash duplicate-file candidates.

## Expected parser contract

Open the text stream with strict UTF-8 decoding and `newline=""`. Detect and record a UTF-8 BOM explicitly. Do not replace undecodable bytes or silently fall back to another encoding.

The expected dialect is:

```text
delimiter=","
quotechar='"'
doublequote=True
escapechar=None
skipinitialspace=False
strict=True
```

Use positional `csv.reader`, not `DictReader`, so wrong-column-count records cannot be padded or hidden. Do not strip, normalize, infer types, or apply missing-value conversion.

The expected 15-column header, in order, is:

1. `id`
2. `street_address_line_1`
3. `street_address_line_2`
4. `street_address_line_3`
5. `street_address_line_4`
6. `street_address_line_1_native`
7. `street_address_line_2_native`
8. `street_address_line_3_native`
9. `street_address_line_4_native`
10. `postcode`
11. `city`
12. `region_in_country`
13. `country_iso_code`
14. `batch_priority`
15. `location_information`

Phase 1 verifies this contract across every file. If a file violates it, record the deviation/failure and require review. Do not automatically retry it with a different dialect.

## Record accounting and failure semantics

Logical data-record numbering is 1-based and excludes the header. For every returned record, record the physical-line start and end using the CSV reader's cumulative physical-line count. A span greater than one is a multiline logical record.

Distinguish:

- a physically blank/logically empty record;
- a correctly shaped record whose 15 values are all empty;
- a syntactically valid record with the wrong number of columns;
- a fatal decoding or CSV parser error.

A wrong-column-count record remains part of the logical record count but is not mapped to expected field names. It produces a schema anomaly and is never padded or truncated.

A fatal parsing, encoding, or file-change error:

- stops the affected file at the last safe logical record;
- sets `counts_complete=false`;
- preserves the diagnostic;
- continues to other files where safe;
- makes the overall Phase 1 gate fail.

Do not attempt record resynchronization after malformed quoting.

## Oversized and multiline diagnostics

All thresholds are configurable. The provisional defaults are:

```text
field_warning_chars=1024
logical_record_warning_chars=4096
parser_hard_field_ceiling_chars=64 Mi
```

The two warning thresholds create `CONTENT` anomalies only. They do not classify CSV as malformed and do not authorize rejection, deletion, truncation, or cleaning.

The 64 Mi-character parser ceiling is a memory-safety limit. It is not a scientific address-validity threshold. If it is exceeded, record `FIELD_LIMIT_EXCEEDED`, stop the affected file safely, and require review before raising the ceiling.

Oversized/multiline anomaly provenance includes:

```text
relative_path
logical_record_number
physical_line_start
physical_line_end
physical_line_span
column_name
field_length_chars
logical_record_length_chars
value_sha256
warning_threshold
parser_ceiling
anomaly_type
```

No field content or preview is included.

## Field and value profiling

For each expected field, collect non-empty, empty, whitespace-only, maximum-length, newline-containing, and warning-threshold counts. Records with the wrong column count are excluded from named-field profiles because positional mapping is unsafe.

Raw categorical output is permitted only for:

- `country_iso_code`;
- `batch_priority`;
- `location_information`;
- exact configured placeholder candidates.

Do not emit raw frequency tables for address lines, native-address values, city, or postcode.

Postcodes receive lexical categories only, including empty, digits-only, leading-zero digits, alphabetic, alphanumeric, whitespace-containing, hyphen-containing, decimal-looking, exact-placeholder-candidate, and other. These categories are diagnostics and do not modify the postcode.

Each native/non-native line pair receives relationship diagnostics:

- both empty;
- native only;
- non-native only;
- exact equal;
- different.

Native fields may also receive aggregate script diagnostics, but never raw-value frequency output. The exact script classifier and cardinality safeguards remain implementation decisions.

Placeholder candidates such as blank, `.`, `-`, `Na`, `Nan`, and `Null` are counted exactly. Phase 1 does not decide that they are equivalent or normalize them to missing values.

## Compact exact SQLite ID design

IDs remain exact strings. Do not trim, normalize, case-fold, or numerically coerce them. Empty IDs are counted separately and are not inserted into the uniqueness store.

The working database is local, ignored by Git, and may contain exact raw IDs. It uses one transaction per source file so interruption rolls back the incomplete file without corrupting previously completed files.

### `unique_ids`

One row per exact non-empty ID:

```text
id_value TEXT COLLATE BINARY PRIMARY KEY
id_sha256 TEXT NOT NULL
first_file_id INTEGER NOT NULL
first_logical_record_number INTEGER NOT NULL
last_file_id INTEGER NOT NULL
occurrence_count INTEGER NOT NULL
file_count INTEGER NOT NULL
has_within_file_duplicate INTEGER NOT NULL
has_cross_file_duplicate INTEGER NOT NULL
```

The table should use `WITHOUT ROWID` if tests confirm the expected portability and benefit. `id_sha256` is SHA-256 over the exact UTF-8 bytes of the decoded ID, without normalization.

`last_file_id` supports exact `file_count` because files are processed serially, in deterministic order, and a committed file is never revisited within the same run. If implementation later permits interleaved file processing, this invariant is invalid and a separate `(id_value, file_id)` table would be required.

### `duplicate_occurrences`

Rows exist only for IDs whose `occurrence_count` becomes greater than one:

```text
id_value TEXT COLLATE BINARY NOT NULL
file_id INTEGER NOT NULL
logical_record_number INTEGER NOT NULL
is_first_occurrence INTEGER NOT NULL
PRIMARY KEY (id_value, file_id, logical_record_number)
FOREIGN KEY (id_value) REFERENCES unique_ids(id_value)
```

Processing rule:

1. On the first occurrence, insert only `unique_ids`.
2. On the second occurrence, insert the stored first location and current location into `duplicate_occurrences`, then update counts and duplicate-scope flags.
3. On later occurrences, insert only the new location and update counts/flags.
4. If the current `file_id` equals `last_file_id`, mark a within-file duplicate.
5. If it differs, increment `file_count`, update `last_file_id`, and mark a cross-file duplicate.

This structure determines exactly:

- within-file duplicate groups and occurrences;
- cross-file duplicate groups and occurrences;
- total duplicate groups;
- total occurrences belonging to duplicate groups;
- excess duplicate occurrences beyond the first;
- every occurrence location for duplicated IDs.

Durable generated reports contain `id_sha256`, not `id_value`. Raw IDs do not appear in Markdown. Exact raw IDs remain temporary unless a later internal report is separately approved.

## Duplicate-file detection

Every file receives an exact raw-byte SHA-256 from the separate hashing pass. Different sizes cannot be exact duplicates. Equal size plus equal SHA-256 defines a duplicate candidate group. Byte-for-byte confirmation of those candidates remains an implementation decision.

The manifest records the hash, duplicate group, group size, and verification method. Filenames, record counts, or ID ranges are not evidence of exact file duplication.

## Memory, temporary state, and restartability

Hold only the current logical record, bounded counters, and small SQLite operation state in memory. Do not create a dataframe or an in-memory set of all IDs. Avoid copying large field strings when calculating diagnostics.

The temporary SQLite database belongs outside the source directory and outside Git. Exact transaction size, SQLite pragmas, free-space threshold, and retention/deletion after review remain implementation decisions.

Checkpoint only at file transaction boundaries. A resume may skip a completed file only when its recorded source identity and stability metadata still match; otherwise it must be rescanned.

## Source outputs

Generated outputs are written under:

```text
reports/generated/phase01/<run_id>/
```

They remain outside Git and contain no raw row/address content.

### `phase01_run.json`

Run provenance and configuration:

```text
run_id, inventory_version, status, started_at_utc, completed_at_utc,
git_commit, python_version, platform, source_root_label, discovery_mode,
files_discovered, total_size_bytes, parser_configuration,
warning_thresholds, parser_limits, working_store_configuration,
resume_information, input_manifest_sha256, output_files, error_counts
```

### `phase01_file_manifest.csv`

One row per file:

```text
run_id, file_id, relative_path, file_name,
size_bytes_before, mtime_utc_before, size_bytes_after_parse,
mtime_utc_after_parse, size_bytes_after_hash, mtime_utc_after_hash,
file_changed_during_scan, sha256, duplicate_file_group,
duplicate_file_group_size, duplicate_verification_method,
bom_type, encoding_status, delimiter, quote_character, doublequote,
escape_character, header_present, observed_column_count,
schema_fingerprint, schema_matches_expected, logical_record_count,
valid_schema_record_count, empty_record_count,
all_fields_empty_record_count, wrong_column_count_record_count,
parser_error_count, multiline_record_count, max_physical_lines_per_record,
max_record_length_chars, max_field_length_chars, id_nonempty_count,
id_empty_count, id_distinct_within_file,
id_duplicate_group_count_within_file,
id_duplicate_occurrence_count_within_file, id_lexical_min_sha256,
id_lexical_min_length, id_lexical_max_sha256, id_lexical_max_length,
counts_complete, scan_status, error_code, duration_ms
```

ID min/max selection is lexical and diagnostic only. The durable manifest retains hashes and lengths rather than raw ID values; it is not evidence of uniqueness.

### `phase01_schema_report.csv`

One row per observed header position:

```text
run_id, file_id, relative_path, column_position, observed_column_name,
expected_column_name, name_matches_expected, position_matches_expected,
schema_fingerprint
```

### `phase01_field_profile.csv`

One row per file and safely mapped expected field:

```text
run_id, file_id, relative_path, column_position, column_name,
records_eligible_for_profile, nonempty_count, empty_count,
whitespace_only_count, nonempty_share, max_length_chars,
max_length_logical_record_number, contains_newline_count,
oversized_field_count, exact_placeholder_candidate_count,
profile_complete
```

### `phase01_value_profile.csv`

Aggregate approved diagnostics:

```text
run_id, file_id, relative_path, field_name, profile_family,
category, count, denominator, share
```

Approved families are `PLACEHOLDER_EXACT`, `POSTCODE_LEXICAL_PATTERN`, `NATIVE_PAIR_STATE`, `NATIVE_SCRIPT_DIAGNOSTIC`, `COUNTRY_CODE_VALUE`, `BATCH_PRIORITY_VALUE`, and `LOCATION_INFORMATION_VALUE`.

### `phase01_anomalies.csv.gz`

Potentially row-level diagnostics without raw values:

```text
run_id, anomaly_id, severity, domain, anomaly_type, file_id,
relative_path, logical_record_number, physical_line_start,
physical_line_end, column_name, expected, observed,
field_length_chars, record_length_chars, value_sha256,
message_code, counts_complete
```

### `phase01_duplicate_ids.csv.gz`

One row per occurrence belonging to a duplicate group:

```text
run_id, id_sha256, occurrence_count, file_count, duplicate_scope,
file_id, relative_path, logical_record_number
```

`duplicate_scope` is `WITHIN_FILE`, `CROSS_FILE`, or `BOTH`. Raw IDs are excluded.

### `phase01_summary.md`

A human-readable summary of source scope, parsing/schema findings, row counts, content anomalies, field profiles, ID uniqueness, duplicate files, test/benchmark results, failures, and the Phase 1 gate. It contains no raw IDs or address content.

After successful review, a sanitized version becomes `docs/history/source_foundation/PHASE01.md`.

## Logging and privacy

Operational logs are structured and contain event codes, relative file identity, logical/physical record location, and non-sensitive diagnostics. The anomaly field `observed` is limited to non-sensitive structural facts such as a column count or configured limit; it never contains raw field or ID values. Never log full rows, raw addresses, native values, raw IDs, field snippets, credentials, or authorization data.

Reports and logs distinguish at least `FILE`, `ENCODING`, `PARSING`, `SCHEMA`, `CONTENT`, and `IDENTITY` domains. Content warnings do not become parsing errors.

## Testing and benchmark gate

Implementation must begin with synthetic/unit and small integration tests covering ordinary CSV, embedded comma, doubled quote, multiline record, generated large field, wrong column count, malformed quote, UTF-8/non-Latin content, leading-zero and alphanumeric postcodes, placeholder strings, duplicate IDs, duplicate files, and schema variation.

Before the complete collection may be scanned, run read-only smoke tests on:

1. one ordinary real shard;
2. one known anomalous real shard.

Then produce a benchmark reporting:

- runtime;
- peak memory;
- temporary SQLite size;
- parsing throughput;
- anomaly handling and correctness.

Runtime for the full inventory remains unknown until this benchmark. The user must review and approve the benchmark before the 206-file run.

## Execution environment

The MacBook is the default full Phase 1 environment. Goethe-NHR is a fallback or optional independent environment if evidence later justifies it. This local recommendation does not authorize the complete scan.

## Completion and STOP gate

Phase 1 can pass only when:

- the intended 206 files and total bytes are accounted for;
- every source file is stable and hashed;
- the expected parser contract is verified or every deviation is explicitly reviewed;
- every file has complete reproducible logical-record counts;
- malformed, wrong-column, multiline, and oversized cases are reported without silent loss;
- the approved field/value profiles are complete;
- within-file and cross-file ID duplication is determined exactly;
- duplicate-file groups are reported;
- generated outputs are complete, checksummed, and privacy-safe;
- all required tests, smoke tests, and benchmark checks pass;
- no file has `counts_complete=false`;
- `docs/history/source_foundation/PHASE01.md` is reviewed;
- the user explicitly approves completion.

The project then stops. It does not begin Phase 2 automatically.

## Remaining implementation decisions

- SQLite transaction batch size and pragmas.
- Temporary database path, minimum free-space threshold, and retention/deletion policy.
- Exact hydration-verification method for OneDrive files.
- Exact ordinary and anomalous smoke-test shards.
- Benchmark acceptance thresholds for runtime, peak memory, throughput, temporary storage, and anomaly behavior.
- Whether equal-size/equal-SHA-256 duplicate candidates require byte-for-byte confirmation.
- Native-script diagnostic classifier and categories.
- Cardinality cap/failure behavior for approved raw categorical profiles.
- Run-ID and inventory-version formats.
- Exact output atomic-write and resume protocol.
- Review procedure for files that violate strict UTF-8 or the expected CSV dialect.
- Full 206-file execution approval.
