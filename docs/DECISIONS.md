# Decision register

This register distinguishes approved project rules from questions that require evidence or explicit scientific approval. Previous code and sample behavior cannot change a decision's status.

## Locked decisions

- The research objective requires physical building/plant/branch/store/facility point locations.
- `usable_for_analysis` is the main Boolean indicator of suitability for point-level research; diagnostic tiers remain separate.
- An address-layer exact match without a major geographic contradiction is expected to be usable.
- Street, venue, locality, localadmin, region, country, fallback, and otherwise coarse matches are not usable for the main point-level analysis.
- API response success or the existence of a first feature is not scientific geocoding success.
- `layer`, `match_type`, and geographic/component agreement are primary quality evidence. Confidence alone is insufficient.
- Raw source data is immutable. Raw fields must not be overwritten, silently cleaned, or silently discarded.
- Every source row must remain traceable to its file, source row, and original ID.
- Postal codes are strings. Unicode and native-script fields must be preserved.
- Address-line positions 1–4 do not have globally fixed meanings.
- Cleaning is conservative; uncertain geography, spelling, or address interpretation is flagged rather than silently inferred.
- Geographic addresses are deduplicated before geocoding, while a mapping to every source row is retained.
- Only unique eligible addresses are sent to SAFE.
- `/v1/search/structured` is the preferred primary endpoint and normal requests use `size=1`.
- SAFE authentication is supplied through protected runtime configuration; credentials are never committed or logged.
- Normal API concurrency is 2–4 requests total across the complete process, regardless of workers, shards, nodes, or jobs.
- Production retries are bounded and use classified transient failures, exponential backoff, jitter, checkpoints, and persistent error status.
- MacBook development/testing is primary. Goethe-NHR may be used for final/full processing where beneficial, with substantial work submitted through SLURM.
- `/scratch` is not used; `/work/footprint/public` and the shared Conda base are not modified.
- The existing `parquet_files` products are invalid and cannot serve as staging data.
- Work proceeds one reviewed phase at a time and stops after every phase.

### Phase 1 approved design decisions

- Phase 1 is an inventory and diagnostic phase only. It does not normalize missing markers, clean or parse addresses, determine geocoding eligibility, create canonical addresses, deduplicate addresses, create Parquet staging, or call SAFE/Pelias.
- The authoritative Phase 1 CSV parser is Python's standard-library `csv` reader using strict UTF-8 decoding, `newline=""`, comma delimiter, `quotechar='"'`, `doublequote=True`, `escapechar=None`, `skipinitialspace=False`, and `strict=True`.
- That dialect is the expected contract, not an assumption that may be silently imposed. A file that violates it is recorded as a deviation/failure and requires review; Phase 1 does not silently select another parser contract.
- Phase 1 distinguishes CSV/parsing validity from content/data-quality anomalies. A syntactically valid extreme field remains valid CSV unless it exceeds a parser safety limit or has another structural error.
- Provisional configurable diagnostic defaults are 1,024 characters for a field warning, 4,096 characters for a logical-record warning, and 64 Mi characters for the parser hard field ceiling.
- Warning-threshold exceedance creates a `CONTENT` anomaly only. It does not make the CSV malformed and does not authorize rejection, truncation, cleaning, or deletion. The 64 Mi-character ceiling is a memory-safety ceiling, not a scientific address-validity rule.
- Physical start/end line spans are recorded for multiline logical records.
- SQLite is the exact temporary ID working store. It uses `TEXT COLLATE BINARY`, never coerces IDs numerically, keeps one row per unique ID, and stores occurrence locations separately only for IDs that become duplicates.
- Durable generated reports contain `id_sha256`, not raw IDs. The duplicate-ID report also contains occurrence locations, source file, logical record number, and duplicate scope. Exact raw IDs may exist only in the ignored temporary SQLite database unless a later internal report is separately approved. Markdown never contains raw IDs.
- Raw categorical output is allowed only for `country_iso_code`, `batch_priority`, `location_information`, and exact configured placeholder candidates. Street/address, native-address, city, and postcode values do not receive raw frequency tables.
- Postcodes receive lexical-pattern profiles only. Native fields receive relationship and script diagnostics rather than raw value profiles.
- Phase 1 uses one full logical CSV parsing pass plus a separate simple sequential raw-byte SHA-256 pass. The raw hashing pass is intentionally separate for correctness and testability; it is not a second CSV parsing pass.
- Before a full run, all 206 source files must be fully hydrated locally, adequate local free space must be confirmed, and active source modification must be prevented. Pausing OneDrive synchronization is recommended when practical. Pre/post size and modification metadata plus exact hashes detect changed files; changed files are incomplete.
- A fatal parsing, encoding, or source-change failure marks the affected file incomplete, preserves diagnostics, continues with other files where safe, and causes the overall Phase 1 gate to fail. The parser does not attempt unsafe resynchronization after malformed quoting.
- The MacBook was the approved environment for the full Phase 1 inventory, superseding the earlier assumption that final inventory automatically required Goethe-NHR. The full run was later separately authorized and completed.
- Synthetic/unit tests, small integration tests, one ordinary real-shard smoke test, one known anomalous real-shard smoke test, and a resource benchmark were mandatory prerequisites to the full Phase 1 run and were completed before full-run authorization.
- No speculative Phase 1 runtime estimate was locked before benchmarking. The completed full-run runtime and resource measurements are recorded in `docs/PHASE01.md`.
- Approved generated outputs are `phase01_run.json`, `phase01_file_manifest.csv`, `phase01_schema_report.csv`, `phase01_field_profile.csv`, `phase01_value_profile.csv`, `phase01_anomalies.csv.gz`, `phase01_duplicate_ids.csv.gz`, and `phase01_summary.md` under `reports/generated/phase01/<run_id>/`. Generated outputs remain outside Git and contain no confidential raw row/address content.
- The successfully reviewed sanitized Phase 1 summary is `docs/PHASE01.md`.
- DuckDB may be used only as an optional independent cross-check. It does not replace the authoritative parser.

### Phase 1 resolved for the current source snapshot

The following findings are resolved for the exact source snapshot identified by Phase 1 input-manifest SHA-256 `94254dadab515194a4d292f7095107f94c58508d83d7bf70d63608dc8002bba8`:

- Phase 1 was authorized, completed, reviewed, and passed for the full current collection.
- The collection contains 206 direct-child CSV files totaling exactly 3,285,318,564 source bytes.
- Every file contains exactly 100,000 logical data records, for exactly 20,600,000 records overall.
- All 206 files satisfy the same strict UTF-8-without-BOM, comma-delimited, headered, double-quote CSV contract with the approved 15 columns in the approved order.
- Parser errors, wrong-column records, schema deviations, incomplete files, and source-change failures are all zero.
- `id` is non-empty and globally unique across all 20,600,000 records under exact UTF-8/BINARY comparison.
- There are no within-file or cross-file duplicate IDs and no exact duplicate source files under the approved size-plus-SHA-256 method.

These are empirical properties of the exact current snapshot, not permanent provider guarantees. A future or changed source snapshot must reverify file identity, parser/schema contract, counts, ID uniqueness, and duplicate-file status before it is staged.

### Phase 2 approved design decisions

- Phase 2 is controlled, lossless staging only. It does not normalize missing markers, clean or parse addresses, infer geography, create canonical or typed analytical values, deduplicate addresses, determine geocoding eligibility, create an `address_key`, or call SAFE/Pelias.
- Python's approved strict Phase 1 `csv.reader` contract remains the authoritative source parser. PyArrow is the primary Arrow/Parquet writer and reader. DuckDB may validate completed Parquet only and must not parse source CSV during Phase 2.
- All 15 source columns are non-null Arrow `string` columns in their original order. This includes `id`, `postcode`, and `batch_priority`; none is numerically or semantically converted.
- Empty string remains a non-null zero-length string. Literal `.`, `-`, `Na`, `Nan`, and `Null` values remain exact literal strings and are not converted to null.
- Row provenance columns are `source_file: string`, `source_logical_record_number: uint64`, `stable_source_row_id_v1: fixed_size_binary[32]`, `source_file_sha256: fixed_size_binary[32]`, `source_schema_version: string`, `parser_version: string`, and `staging_version: string`, all non-null.
- `stable_source_row_id_v1` is SHA-256 over a fixed versioned domain separator, the raw 32-byte source-file SHA-256, and the one-based logical record number encoded as unsigned 64-bit big-endian. It excludes provider ID, filename, parser version, and staging version.
- `raw_semantic_digest_v1` covers only the original 15 raw columns in logical row order. It uses a versioned domain, exact ordered column names, row ordinals, explicit null/non-null tags, unsigned 64-bit length-prefixed UTF-8 values, and a total-row-count footer. Provenance is validated independently.
- Phase 2 preserves a one-source-CSV-to-one-controlled-Parquet layout under an immutable run-specific staging path. It creates no automatic `CURRENT` pointer and never writes to or overwrites the historical `parquet_files` directory.
- Provisional smoke-test settings are ZSTD level 3, 25,000-row normal write batches, and 25,000-row normal row groups. These are operational, benchmark-driven settings rather than scientific requirements.
- A configurable 1 MiB UTF-8 extreme-row isolation threshold is approved for memory management only. It is unrelated to the Phase 1 1,024-character content-warning threshold and never authorizes rejection, truncation, or modification.
- Selective dictionary encoding and suppression of statistics for sensitive raw columns are required. Tests must confirm that prohibited raw sensitive values are absent from Parquet metadata.
- Parquet page checksums are enabled and explicitly verified during temporary-file read-back. A technically feasible corruption test must prove checksum-invalid output is rejected.
- Conversion is all-or-nothing per file. A file is promoted only after source identity, strict parsing, exact schema and counts, semantic equality, provenance, stable IDs, known extreme records, page checksums, and output hash all validate. There is no row salvage, permissive parsing, or alternate parser.
- Global reconciliation expects, but does not fabricate, 206 Parquet files, 20,600,000 rows, 20,600,000 distinct raw IDs, 20,600,000 distinct stable source-row IDs, zero raw-column nulls, and zero failed files.
- Temporary output is validated before same-filesystem atomic promotion. A run is not approved without complete dataset-level reconciliation and a final success marker.
- The ordinary and extreme real-shard smoke conversions must be separately authorized, executed, benchmarked, and reviewed before the complete 206-file Phase 2 conversion can be authorized.

## Open decisions

- Whether, and under what evidence/rules, an address-layer interpolated result is `usable_for_analysis`.
- Exact placeholder/null semantics, including treatment of `.`, `-`, `Na`, `Nan`, `Null`, and source-specific status values.
- International canonical-address rules and deterministic extraction of structured geography from free-form lines.
- Native-script versus transliterated primary/rescue query rules.
- Exact versioned address-key serialization and fields included in it.
- Final input eligibility/completeness thresholds and controlled rescue-query ladder.
- Pilot 2 necessity, sampling design, and size.
- Manual ground-truth protocol and evidence needed for interpolation policy.
- Candidate comparison, component-agreement thresholds, and manual-review thresholds.
- Any external geographic boundary/reference dataset, including source, license, vintage, and coverage.
- Exact compatible PyArrow and DuckDB version pins, Parquet physical/data-page version, and checksum-verification API.
- Smoke-benchmark acceptance limits and any resulting change to the provisional Phase 2 batch, row-group, compression, memory, spill, free-space, or runtime settings.
- Exact Phase 2 run-ID/configuration-fingerprint formats, small run-state SQLite details, temporary-output quarantine/retention policy, and artifact permission/access controls.
- Authorization to implement Phase 2, execute the two-shard real-data smoke conversion, and later execute the complete 206-file conversion remain separate outstanding approvals.
- Production unique-address count, API-call count, timing, SAFE RDC coordination, and production-run approval.
- Historical-address and location-type interpretation rules where source evidence permits them.

### Must be reverified for a future source snapshot

- Direct-child source-file count and total source bytes.
- Exact raw-byte file identities and duplicate-file status.
- Strict encoding, CSV dialect, header, schema, and column-order contract.
- Per-file and total logical record counts, including malformed, multiline, and extreme-record diagnostics.
- Non-empty, within-file unique, and dataset-wide unique `id` properties.
- Compatibility of the approved Arrow `string` schema with future field and batch sizes. A capacity problem requires a stop and reviewed schema version; it does not permit a silent switch to `large_string`.

## Superseded / corrected assumptions

- **Superseded:** The current source collection was previously estimated at approximately 500 GB.
- **Replacement:** The authoritative current source dataset is 206 CSV files totaling approximately 3.29 GB.
- There is currently no known additional source collection that this pipeline must process.
- Engineering choices must reflect the verified current scale. CSV-aware parsing, chunking/streaming where useful, and robust diagnostics remain necessary because parsed memory use can be much larger and extreme multiline fields exist. Distributed or big-data technology is not justified solely by the superseded estimate.
