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
- The MacBook is the default environment for the full Phase 1 inventory. This supersedes the earlier assumption that the final inventory automatically requires Goethe-NHR, but it does not approve the full run yet.
- Before approval of the complete 206-file run, Phase 1 must pass synthetic/unit tests, small integration tests, one ordinary real-shard smoke test, one known anomalous real-shard smoke test, and a benchmark reporting runtime, peak memory, temporary SQLite size, parsing throughput, and anomaly handling.
- Runtime and full-run resource requirements remain unknown until the real-shard benchmark. No 30-minute-to-2-hour estimate is locked.
- Approved generated outputs are `phase01_run.json`, `phase01_file_manifest.csv`, `phase01_schema_report.csv`, `phase01_field_profile.csv`, `phase01_value_profile.csv`, `phase01_anomalies.csv.gz`, `phase01_duplicate_ids.csv.gz`, and `phase01_summary.md` under `reports/generated/phase01/<run_id>/`. Generated outputs remain outside Git and contain no confidential raw row/address content.
- After successful review, a sanitized Phase 1 summary becomes `docs/PHASE01.md`.
- DuckDB may be used only as an optional independent cross-check. It does not replace the authoritative parser.

## Open decisions

- Whether, and under what evidence/rules, an address-layer interpolated result is `usable_for_analysis`.
- Whether `id` is globally unique across all 206 files.
- Whether the sampled 15-column UTF-8/comma/header/double-quote contract holds across all 206 files.
- Whether all shards contain 100,000 logical records and what the complete logical row count is.
- Complete malformed-record, multiline-record, oversized-field, missing-marker, and schema variation across the source collection.
- Exact placeholder/null semantics, including treatment of `.`, `-`, `Na`, `Nan`, `Null`, and source-specific status values.
- International canonical-address rules and deterministic extraction of structured geography from free-form lines.
- Native-script versus transliterated primary/rescue query rules.
- Exact versioned address-key serialization and fields included in it.
- Stable source-row ID implementation and collision/integrity checks.
- Final input eligibility/completeness thresholds and controlled rescue-query ladder.
- Pilot 2 necessity, sampling design, and size.
- Manual ground-truth protocol and evidence needed for interpolation policy.
- Candidate comparison, component-agreement thresholds, and manual-review thresholds.
- Any external geographic boundary/reference dataset, including source, license, vintage, and coverage.
- Final staging technology/layout, execution location, resource sizing, and output partitioning.
- Production unique-address count, API-call count, timing, SAFE RDC coordination, and production-run approval.
- Historical-address and location-type interpretation rules where source evidence permits them.
- Exact SQLite transaction batch size, durability/performance pragmas, temporary database location, free-space threshold, and post-review retention/deletion procedure.
- Exact method for confirming that every OneDrive file is fully hydrated before the approved full run.
- The exact ordinary and anomalous real shards used for smoke tests and the benchmark acceptance criteria.
- Whether hash-equal duplicate-file candidates require byte-for-byte confirmation in addition to equal size and SHA-256.
- Cardinality safeguards for the approved raw low-risk categorical profiles if an ostensibly low-cardinality field contains unexpected high-cardinality content.
- Exact handling of any file that fails the expected UTF-8/CSV contract; no alternative contract is accepted without review.
- Approval to execute the complete 206-file Phase 1 inventory remains outstanding.

## Superseded / corrected assumptions

- **Superseded:** The current source collection was previously estimated at approximately 500 GB.
- **Replacement:** The authoritative current source dataset is 206 CSV files totaling approximately 3.29 GB.
- There is currently no known additional source collection that this pipeline must process.
- Engineering choices must reflect the verified current scale. CSV-aware parsing, chunking/streaming where useful, and robust diagnostics remain necessary because parsed memory use can be much larger and extreme multiline fields exist. Distributed or big-data technology is not justified solely by the superseded estimate.
