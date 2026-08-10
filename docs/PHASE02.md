# Phase 2 report — controlled staging dataset

## Status

**Phase 2 gate: PASS.**

The complete authoritative Phase 1 source snapshot was converted into a lossless,
source-aligned controlled Parquet dataset. All 206 source files passed source
identity, strict parsing, semantic-integrity, provenance, stable-row-ID, Parquet
checksum, and atomic-promotion validation. Exact dataset-level reconciliation
also passed.

This report is sanitized. It contains no raw address, native-address, city,
postcode, or provider-ID values. Phase 3 has not started and is not authorized.

## Run identity and provenance

| Property | Value |
|---|---:|
| Run ID | `phase02_20260810T173851Z_1349152b` |
| Run scope | `FULL_CONVERSION` |
| Git commit | `1349152bcbfa240aa402c9794f4c4351c94100ec` (`Implement validated Phase 2 staging pipeline`) |
| Git working tree at execution | Clean (`git_dirty=false`) |
| Implementation fingerprint | `bacbed74015bc8b40a436d2a93f05c6ee4886a744eff1ca47b6bf3426f37f64a` |
| Configuration fingerprint | `b80be650147785322e2c1f56f4154e547eb6e4b54262c35dc46f8c2fc0f8c231` |
| Python | 3.14.3 |
| PyArrow | 25.0.0 |
| DuckDB | 1.5.5 |
| Started (UTC) | `2026-08-10T17:39:02.313153Z` |
| Completed (UTC) | `2026-08-10T17:45:50.207515Z` |

The authoritative input was Phase 1 run
`phase01_20260810T151626Z_7df9bc8f`, with input-manifest SHA-256
`94254dadab515194a4d292f7095107f94c58508d83d7bf70d63608dc8002bba8`.
Before conversion, all 206 source files received a fresh raw-byte SHA-256 check;
every size, modification time, hash, and direct-child filename matched Phase 1.

## Dataset reconciliation

| Measure | Source | Controlled staging | Result |
|---|---:|---:|---:|
| Files | 206 | 206 | PASS |
| Rows | 20,600,000 | 20,600,000 | PASS |
| Files with exactly 100,000 rows | 206 | 206 | PASS |
| Bytes | 3,285,318,564 | 1,602,748,600 | Recorded |
| Overall source/staging byte ratio | — | 2.0498027975 | Recorded |
| Failed file validations | — | 0 | PASS |
| Missing source mappings | — | 0 | PASS |
| Extra Parquet files | — | 0 | PASS |
| Approved schemas | — | 1 | PASS |

The 206 Parquet output sizes ranged from 5,555,441 to 11,232,606 bytes.
The median was 7,990,254.5 bytes, the first quartile was 7,062,111 bytes,
the third quartile was 8,403,009 bytes, and the mean was approximately
7,780,333 bytes. Files contained four to eight row groups; the median was four.

## Exact staging schema

All columns are non-null and retain this exact order:

| Position | Column | Arrow type |
|---:|---|---|
| 1 | `id` | `string` |
| 2 | `street_address_line_1` | `string` |
| 3 | `street_address_line_2` | `string` |
| 4 | `street_address_line_3` | `string` |
| 5 | `street_address_line_4` | `string` |
| 6 | `street_address_line_1_native` | `string` |
| 7 | `street_address_line_2_native` | `string` |
| 8 | `street_address_line_3_native` | `string` |
| 9 | `street_address_line_4_native` | `string` |
| 10 | `postcode` | `string` |
| 11 | `city` | `string` |
| 12 | `region_in_country` | `string` |
| 13 | `country_iso_code` | `string` |
| 14 | `batch_priority` | `string` |
| 15 | `location_information` | `string` |
| 16 | `source_file` | `string` |
| 17 | `source_logical_record_number` | `uint64` |
| 18 | `stable_source_row_id_v1` | `fixed_size_binary[32]` |
| 19 | `source_file_sha256` | `fixed_size_binary[32]` |
| 20 | `source_schema_version` | `string` |
| 21 | `parser_version` | `string` |
| 22 | `staging_version` | `string` |

The schema fingerprint is
`e0b98441948f98e570f9f52c1837db23c00c309c1a810d94d6b09541095cdd21`.

## Parquet configuration

| Setting | Production value |
|---|---:|
| Parquet logical/physical version | 1.0 |
| Data-page version | 1.0 |
| Compression | ZSTD |
| Compression level | 3 |
| Normal write batch | 25,000 rows |
| Normal row-group target | 25,000 rows |
| Extreme isolation threshold | 1,048,576 UTF-8 bytes |
| Parser field ceiling | 67,108,864 characters |
| Page checksums | Written and verified |
| DuckDB memory limit | 4 GB |

Dictionary encoding was restricted to approved low-cardinality columns.
Statistics were absent for all prohibited sensitive/high-cardinality columns.
An independent metadata audit found zero prohibited statistics and zero
prohibited dictionary encodings across all output row groups.

## Per-file semantic and provenance validation

| Validation | PASS | FAIL |
|---|---:|---:|
| Complete per-file validation | 206 | 0 |
| Source/staging `raw_semantic_digest_v1` equality | 206 | 0 |
| Exact 100,000-row reconciliation | 206 | 0 |
| Provenance columns | 206 | 0 |
| Within-file stable-row-ID recomputation/uniqueness | 206 | 0 |
| Known extreme-value reconciliation | 206 | 0 |
| Page-checksum read-back | 206 | 0 |

Every promoted Parquet output was independently read in full with
`page_checksum_verification=True`. A post-run audit repeated this for all
20,600,000 staging rows. The individual output SHA-256 values recorded in the
dataset manifest were also recalculated after promotion; all 206 matched.

## Raw IDs and stable source-row IDs

Parquet-only exact DuckDB reconciliation established:

| Finding | Result |
|---|---:|
| Raw ID rows | 20,600,000 |
| Distinct raw IDs | 20,600,000 |
| Null raw IDs | 0 |
| Empty-string raw IDs | 0 |
| Distinct `stable_source_row_id_v1` | 20,600,000 |
| Duplicate stable source-row IDs | 0 |

The stable source-row identifier remains a provenance identifier. It is not an
address-deduplication key.

## Null and empty-string preservation

All 15 raw columns contain zero nulls in staging. Source and staging empty-string
counts matched exactly:

| Raw column | Preserved empty strings |
|---|---:|
| `id` | 0 |
| `street_address_line_1` | 60,222 |
| `street_address_line_2` | 8,090,198 |
| `street_address_line_3` | 16,315,655 |
| `street_address_line_4` | 20,327,902 |
| `street_address_line_1_native` | 38,338 |
| `street_address_line_2_native` | 8,015,597 |
| `street_address_line_3_native` | 16,263,907 |
| `street_address_line_4_native` | 20,038,925 |
| `postcode` | 3,567,253 |
| `city` | 3,252,471 |
| `region_in_country` | 15,976,844 |
| `country_iso_code` | 410,746 |
| `batch_priority` | 0 |
| `location_information` | 0 |

Literal placeholder-like strings were not reclassified or converted to null.
Their semantic interpretation remains open for a later reviewed phase.

## Postcode, Unicode, and native fields

`postcode` remained an exact non-null Arrow `string`; no numeric inference or
normalization occurred. Its 3,567,253 empty strings and all non-empty lexical
forms were covered by the per-file semantic digests.

Unicode and native fields remained separate exact strings. Source/staging counts
of non-ASCII-containing values matched for every raw column. The native address
line counts were 7,785,652, 4,270,597, 165,459, and 295,547 respectively.
These counts are diagnostics only and do not select native or non-native text.

## Extreme and multiline preservation

Phase 1 supplied 37 relevant diagnostic entries:

- 13 quoted-multiline logical-record diagnostics;
- 13 oversized-field diagnostics;
- 11 oversized-logical-record diagnostics.

All 13 multiline logical row locations exist exactly once in staging. All 13
oversized fields matched the Phase 1 source file, logical record, column,
character length, and value SHA-256. Complete semantic-digest equality also
confirms exact ordered raw-field preservation for every affected record.

Eight records crossed the separate 1 MiB operational threshold and were written
as singleton row groups. This was memory isolation only; the other Phase 1
content warnings remained ordinary valid rows.

The maximum record again validated at 19,413,972 characters and 22,065,061
UTF-8 bytes. It remained one logical staging row despite spanning 95,462
physical CSV lines. Its value SHA-256 matched Phase 1 exactly. No extreme or
multiline record was rejected, truncated, normalized, or converted to null.

## DuckDB reconciliation

DuckDB 1.5.5 read completed Parquet files only; it did not read source CSV.
The production reconciliation returned:

- 206 files;
- 20,600,000 rows;
- 20,600,000 distinct raw IDs;
- 20,600,000 distinct stable source-row IDs;
- zero null raw IDs;
- zero duplicate stable source-row IDs;
- zero nulls across all 15 raw columns;
- one schema;
- zero missing or extra files.

Production DuckDB reconciliation took 1.214 seconds under a 4 GB memory limit
and wrote zero spill bytes. No DuckDB-specific peak-memory instrument was used;
the whole-process peak RSS, which includes reconciliation, is reported below.

## Runtime and resources

| Metric | Result |
|---|---:|
| Total measured runtime | 407.886 seconds |
| Conversion time | 180.116 seconds |
| Independent validation time | 221.575 seconds |
| Source/output hashing time | 1.806 seconds |
| DuckDB reconciliation time | 1.214 seconds |
| Peak process RSS | 3,125,608,448 bytes (about 2.91 GiB) |
| Largest temporary Parquet attempt | 11,232,606 bytes |
| Final SQLite state database | 1,048,576 bytes |
| DuckDB spill | 0 bytes |

The temporary metric is the largest measured per-file temporary Parquet, not an
operating-system cache measurement. After completion, `.in_progress/` was empty
and no `.tmp` or `.temp` files remained anywhere in the controlled run.

## Artifact integrity

The controlled run directory has mode `0700`; controlled Parquet, SQLite,
manifest, and success-marker files have mode `0600`.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `dataset_manifest.json` | 130,905 | `5fa416ec9d79a55eeae372e21caecf1616e5443fc04fcb4de995ac0b29ea6a96` |
| `_SUCCESS.json` | 333 | `9ae9d67765e9c1fc702e3e0c8ebe3be69c22c4c845e4407f5b5042b974d989ea` |
| `phase02_run.json` | 10,233 | `c3210e6c261cf89515fc37e888cb606175f57c15c1b1e39a8a795bd27381fb01` |
| `phase02_file_validation.csv` | 460,891 | `859cd358488ccde9270543a8245b84f39e432bd1925ea03ae7093b9a1376e80f` |
| `phase02_schema.json` | 3,095 | `c0cdd1cfa183e90d8d1db30f26dd3e68031f01b6cf03929406d6ad61bbe66183` |
| `phase02_reconciliation.json` | 335 | `3a04de0e2a898e4a26a9ec1bb08f1f2a5e548c88cb6232cfcfff5630e445c417` |
| `phase02_failures.csv.gz` | 96 | `8f16bc431b04bd698ff67db407f313919b7205ec67bca034382bd36cb403020e` |
| `phase02_summary.md` | 19,279 | `de14f157eb648889cfa7a15eca697d52d967b577b6f11eaf2a5842098e4d68f6` |

The success marker references dataset-manifest SHA-256
`5fa416ec9d79a55eeae372e21caecf1616e5443fc04fcb4de995ac0b29ea6a96`;
an independent recalculation matched. `_SUCCESS.json` was written after the
generated reports and dataset manifest. The manifest contains all 206
source/output mappings, source and output hashes, row counts, semantic digests,
and implementation/configuration identities.

SQLite `PRAGMA integrity_check` returned `ok`. State and attempt history both
contain exactly 206 `COMPLETE` entries and no other terminal status.

### Post-run review notes

The committed production reconciliation records null raw IDs but does not carry
a separate empty-string-ID field in `phase02_reconciliation.json`. The required
post-run Parquet-only DuckDB audit therefore checked `id = ''` explicitly and
found zero rows. This is a generated-report completeness issue, not an
unverified data condition. A subsequent Phase 2 maintenance change persists the
empty-ID count for future runs; the successful run's artifact remains unchanged.

The generated `_SUCCESS.json` is a compact gate marker containing the run ID,
scope/gate status, dataset-manifest SHA-256, file count, row count, and
completion time. Git/dependency identities and source/staging byte totals are
recorded in `phase02_run.json`, while implementation/configuration identities
and all per-file hashes are recorded in `dataset_manifest.json`; they are not
duplicated in the marker. This differs from the fuller descriptive marker field
list in `docs/PHASE02_DESIGN.md` but does not weaken the verified manifest hash
link. A subsequent Phase 2 maintenance change includes the Git commit and byte
totals in success markers for future runs; this successful marker remains
unchanged.

## Failures, warnings, and gate decision

- Failed or incomplete files: **0**
- Source identity failures: **0**
- Strict parser or schema failures: **0**
- Row-count failures: **0**
- Semantic-digest mismatches: **0**
- Provenance or stable-ID failures: **0**
- Page-checksum failures: **0**
- Output-hash mismatches: **0**
- Raw-column nulls: **0**
- Missing or extra outputs: **0**
- Temporary files remaining: **0**
- Privacy-sensitive Parquet statistics/dictionaries: **0**

Two non-data-integrity reporting gaps are documented above: empty-ID count and
the fuller Git/byte metadata are not duplicated in their preferred generated
artifacts. Both values were independently verified and are recorded in this
sanitized report.

The Phase 1 content anomalies remain present as exact source values; they are
not Phase 2 conversion warnings or failures. All controlled staging completion
conditions are met. **Phase 2 PASS.**

## Remaining decisions before Phase 3

Phase 2 establishes lossless staging but does not resolve later scientific or
canonicalization policies. Phase 3 requires a separately reviewed design and
explicit authorization, including decisions or controlled diagnostics for:

1. placeholder/null semantics for `.`, `-`, `Na`, `Nan`, `Null`, and source
   status values;
2. conservative international canonical-address construction;
3. native-script versus transliterated primary/rescue rules;
4. exact versioned `address_key` serialization and included fields;
5. address eligibility/completeness diagnostics without geocoding;
6. treatment of uncertain or free-form geographic information;
7. later pilot design and the still-open interpolated-match acceptance policy.

No Phase 3 decision is made by this report.

## STOP

Phase 2 is complete and passed for the authoritative Phase 1 source snapshot.
Do not start Phase 3 without its reviewed design and explicit authorization.
