# Phase 1 report — raw file inventory

> **HISTORICAL / SUPERSEDED ARCHITECTURE.** This is preserved run evidence, not
> a current report or run instruction. The only active architecture is Stage 0–8.

## Status

**Phase 1 gate: PASS.**

The complete authoritative source collection was inventoried read-only. All 206 files completed under the approved strict parser contract. No source file was modified, no row was cleaned or canonicalized, no staging dataset was created, and no geocoding service was called.

This report contains aggregate diagnostics only. It contains no raw address, native-address, city, postcode, or ID values.

## Run identity and provenance

| Property | Value |
|---|---:|
| Run ID | `phase01_20260810T151626Z_7df9bc8f` |
| Inventory version | `phase01_v1` |
| Git commit | `7df9bc8f` (`Implement Phase 1 raw file inventory`) |
| Git working tree at execution | Clean (`git_dirty=false`) |
| Started (UTC) | `2026-08-10T15:16:26.437538Z` |
| Completed (UTC) | `2026-08-10T15:20:05.368915Z` |
| Python/platform | Python 3.14.3 on macOS |
| Input-manifest SHA-256 | `94254dadab515194a4d292f7095107f94c58508d83d7bf70d63608dc8002bba8` |
| Source files | 206 direct-child CSV files |
| Exact source bytes | 3,285,318,564 |
| Exact logical data records | 20,600,000 |

The historical run originally wrote local artifacts below
`reports/generated/phase01/phase01_20260810T151626Z_7df9bc8f/`. That obsolete
local report tree is no longer retained after Stage 0–8 report consolidation;
the accepted Stage 0 facts are in the authoritative
[Stage 0 report](../../../reports/development/stage00.md).

## Artifact validation

- All eight approved artifacts exist.
- Every output checksum and byte size recorded in `phase01_run.json` was independently recalculated and matched.
- Both gzip reports opened and parsed successfully.
- The manifest contains 206 unique file IDs and 206 unique relative paths.
- Every file has a 64-character SHA-256 fingerprint.
- SQLite `PRAGMA integrity_check` returned `ok`.
- No file has incomplete counts or source-change status.
- The duplicate-ID report contains `id_sha256`, not raw IDs.

## File, parser, and schema contract

| Finding | Result |
|---|---:|
| Direct CSV files discovered | 206 |
| Files with 100,000 logical records | 206 |
| Other row-count patterns | 0 files |
| Strict UTF-8 valid | 206 files |
| UTF-8 BOM present | 0 files |
| Header recognized | 206 files |
| Exact 15-column schema/order | 206 files |
| Comma/double-quote expected parser contract completed | 206 files |
| Parser errors | 0 |
| Wrong-column-count records | 0 |
| Files with incomplete counts | 0 |
| Files changed during scanning | 0 |
| Failed files | 0 |

The complete collection therefore confirms the sampled contract: strict UTF-8 without BOM, comma delimiter, header present, the approved 15 columns in the approved order, double-quote CSV handling with doubled quotes, no configured escape character, and complete parsing under `strict=True`. No alternate parser contract was tried.

## Field population

Counts below describe exact raw string emptiness. They do not apply placeholder normalization.

| Field | Non-empty | Empty | Maximum characters |
|---|---:|---:|---:|
| `id` | 20,600,000 | 0 | 9 |
| `street_address_line_1` | 20,539,778 | 60,222 | 19,413,972 |
| `street_address_line_2` | 12,509,802 | 8,090,198 | 246 |
| `street_address_line_3` | 4,284,345 | 16,315,655 | 155 |
| `street_address_line_4` | 272,098 | 20,327,902 | 79 |
| `street_address_line_1_native` | 20,561,662 | 38,338 | 7,950,078 |
| `street_address_line_2_native` | 12,584,403 | 8,015,597 | 242 |
| `street_address_line_3_native` | 4,336,093 | 16,263,907 | 155 |
| `street_address_line_4_native` | 561,075 | 20,038,925 | 79 |
| `postcode` | 17,032,747 | 3,567,253 | 40 |
| `city` | 17,347,529 | 3,252,471 | 225 |
| `region_in_country` | 4,623,156 | 15,976,844 | 67 |
| `country_iso_code` | 20,189,254 | 410,746 | 54 |
| `batch_priority` | 20,600,000 | 0 | 1 |
| `location_information` | 20,600,000 | 0 | 26 |

The population pattern confirms that address-line positions and structured geography cannot be assigned one universal international meaning.

## Multiline and oversized content

Warning thresholds were 1,024 characters per field and 4,096 characters per logical record. They were diagnostic only. No warned record was rejected, truncated, normalized, or treated as malformed CSV.

| Anomaly | Total |
|---|---:|
| Quoted multiline logical records | 13 |
| Oversized fields | 13 |
| Oversized logical records | 11 |
| Parser field-limit failures at 67,108,864 characters | 0 |

Nine files were affected:

| Source file | Multiline records | Oversized fields | Oversized records |
|---|---:|---:|---:|
| `remaining_addresses_00001.csv` | 3 | 3 | 3 |
| `remaining_addresses_00003.csv` | 3 | 3 | 1 |
| `remaining_addresses_00004.csv` | 1 | 1 | 1 |
| `remaining_addresses_00008.csv` | 1 | 1 | 1 |
| `remaining_addresses_00056.csv` | 1 | 1 | 1 |
| `remaining_addresses_00182.csv` | 1 | 1 | 1 |
| `remaining_addresses_00186.csv` | 1 | 1 | 1 |
| `remaining_addresses_00200.csv` | 1 | 1 | 1 |
| `remaining_addresses_00205.csv` | 1 | 1 | 1 |

The maximum field length was **19,413,972 characters**, and the maximum logical-record content length was **19,414,045 characters**. Both occurred in `remaining_addresses_00205.csv`. These are syntactically valid but scientifically suspicious content anomalies.

The maximum multiline span was **95,462 physical lines** for one logical record, also in `remaining_addresses_00205.csv`.

## Placeholder candidates

The following are exact string occurrences across profiled fields, not rows. A row may contribute more than one occurrence.

| Exact candidate | Occurrences |
|---|---:|
| `Null` | 10,360 |
| `Na` | 1,363 |
| `-` | 1,159 |
| `.` | 1,125 |
| `Nan` | 1,006 |

Placeholder-like occurrences appear in address lines, native lines, city, postcode, and—twice—`country_iso_code`. Phase 1 does not decide that these strings are equivalent to missing values.

## Postcode lexical patterns

Postcodes remained exact strings. No raw postcode frequency table was produced.

| Lexical category | Records |
|---|---:|
| Digits only | 9,606,417 |
| Decimal-looking | 5,131,098 |
| Empty | 3,567,253 |
| Contains whitespace | 1,482,475 |
| Leading-zero digits | 349,783 |
| Alphanumeric | 254,210 |
| Contains hyphen | 200,380 |
| Alphabetic only | 6,850 |
| Other | 1,118 |
| Exact placeholder candidate | 416 |

The large decimal-looking cohort and the substantial leading-zero, whitespace, hyphenated, and alphanumeric cohorts confirm that postcodes must remain strings and require conservative Phase 2 handling.

## Native/non-native relationships

No raw native-address values were emitted. Each line pair was classified independently.

| Pair | Both empty | Native only | Non-native only | Exact equal | Different |
|---|---:|---:|---:|---:|---:|
| Line 1 | 38,235 | 21,987 | 103 | 12,723,307 | 7,816,368 |
| Line 2 | 8,015,295 | 74,903 | 302 | 8,307,525 | 4,201,975 |
| Line 3 | 16,263,617 | 52,038 | 290 | 4,160,560 | 123,495 |
| Line 4 | 20,038,892 | 289,010 | 33 | 265,173 | 6,892 |

The relationships vary materially by line. Native values cannot be treated globally as redundant copies or as universally preferable replacements.

## Country distribution

`country_iso_code` has 20,189,254 non-empty and 410,746 empty records. The raw field contains 263 distinct non-empty strings:

- 20,188,979 records fall into 205 uppercase two-letter lexical categories;
- 275 records fall into 58 other lexical categories, including longer region-like strings and placeholder-like values.

Two uppercase letters are only a lexical pattern; Phase 1 did not validate membership in an approved ISO code list.

The largest uppercase two-letter cohorts are:

| Category | Records |
|---|---:|
| `IN` | 6,562,406 |
| `CN` | 5,734,801 |
| `GB` | 1,263,945 |
| `KR` | 947,306 |
| `IT` | 427,443 |
| `TH` | 403,056 |
| `TW` | 322,110 |
| `HK` | 267,925 |
| `IL` | 257,894 |
| `CR` | 243,096 |
| `ZA` | 203,352 |
| `SG` | 201,089 |
| `KG` | 186,499 |
| `NO` | 182,317 |
| `IE` | 157,260 |

## Batch and source processing-status distributions

| `batch_priority` | Records |
|---|---:|
| `1` | 20,195,461 |
| `0` | 304,539 |
| `3` | 100,000 |

| `location_information` | Records |
|---|---:|
| `previous_geocoding_failure` | 20,195,461 |
| `no_geocoding_information` | 304,539 |
| `region_interpolated` | 100,000 |

These are source cohort/status values, not new geocoding-quality or eligibility decisions. In particular, `region_interpolated` does not imply point-level usability.

## ID identity results

| Finding | Result |
|---|---:|
| Non-empty IDs | 20,600,000 |
| Empty IDs | 0 |
| Exact distinct IDs | 20,600,000 |
| Within-file duplicate groups | 0 |
| Within-file excess duplicate occurrences | 0 |
| Cross-file duplicate groups | 0 |
| Occurrences in duplicate groups | 0 |

**Conclusion:** `id` is globally unique across this authoritative 206-file collection under exact UTF-8 string/BINARY comparison. This is an empirical property of the current inventory, not a universal guarantee for future source versions.

The durable duplicate-ID report contains only its header and no raw IDs.

## Exact duplicate-file results

Every file received a raw-byte SHA-256 fingerprint. No equal-size/equal-SHA-256 candidate group was found. Therefore, there are **zero exact duplicate-file groups** under the approved size-plus-SHA-256 method, and no byte-for-byte confirmation pass was needed.

## Runtime and resource use

| Metric | Result |
|---|---:|
| Internal measured runtime | 219.013 seconds |
| External wall time | 219.76 seconds |
| CSV parsing time | 200.679 seconds |
| Raw-byte hashing time | 1.160 seconds |
| Peak resident memory | 213,663,744 bytes (about 203.8 MiB) |
| Peak SQLite working size including active auxiliary state | 2,133,979,136 bytes |
| Post-close SQLite database file | 2,133,684,224 bytes |
| Durable generated report bytes excluding `phase01_run.json` | 3,039,982 |
| All top-level durable run files, including the scope marker | 3,050,550 bytes |

Generated artifact sizes:

| Artifact | Bytes |
|---|---:|
| `phase01_run.json` | 10,515 |
| `phase01_file_manifest.csv` | 127,862 |
| `phase01_schema_report.csv` | 571,215 |
| `phase01_field_profile.csv` | 414,604 |
| `phase01_value_profile.csv` | 1,916,584 |
| `phase01_anomalies.csv.gz` | 1,696 |
| `phase01_duplicate_ids.csv.gz` | 142 |
| `phase01_summary.md` | 7,879 |

## Failures and gate decision

- Failed or incomplete files: **0**
- Encoding failures: **0**
- Parser failures: **0**
- Schema deviations: **0**
- Wrong-column records: **0**
- Parser field-limit failures: **0**
- Source modifications detected: **0**
- SQLite integrity failures: **0**

All Phase 1 completion conditions are met. **Phase 1 PASS.**

## Questions and decisions remaining before Phase 2

Phase 1 establishes the raw contract but does not authorize or define staging transformations. Phase 2 design still requires explicit review of:

1. the stable source-row identifier and integrity checks, even though current IDs are globally unique;
2. exact treatment of empty strings versus `.`, `-`, `Na`, `Nan`, and `Null` without silently changing raw values;
3. conservative validation of `country_iso_code`, including empty, non-two-letter, and potentially non-standard two-letter categories;
4. postcode preservation and derived typing rules, especially decimal-looking, leading-zero, whitespace, hyphenated, and alphanumeric forms;
5. preservation and separate representation of native/non-native fields;
6. handling of syntactically valid extreme fields without silent truncation or cleanup;
7. Phase 2 staging engine, schema, output layout, reconciliation checks, and explicit failure policy;
8. how all raw columns and source file/logical-record lineage are retained unchanged.

No canonical-address rule, eligibility rule, missing-marker normalization, deduplication rule, geocoding policy, or interpolated-match acceptance policy is decided by this report.

## STOP

Phase 1 is complete. Phase 2 has not started and requires a separately reviewed design and explicit authorization.
