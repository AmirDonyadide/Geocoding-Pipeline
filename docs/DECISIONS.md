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
- Heavy production processing is Goethe-NHR-only and runs through SLURM. The MacBook is limited to development, documentation, Git, unit/synthetic tests, small diagnostics, lightweight validation, and small controlled manual-review workflows. When production workload classification is uncertain, default to Goethe-NHR. The exact OR-based heavy definition and fail-closed markers are in `docs/EXECUTION_POLICY.md`.
- `/scratch` is not used; `/work/footprint/public` and the shared Conda base are not modified.
- The existing `parquet_files` products are invalid and cannot serve as staging data.
- Work proceeds one reviewed phase at a time and stops after every phase.
- Production-heavy commands reuse the common execution guard and require both `SAFE_EXECUTION_SITE=goethe-nhr` and a non-empty `SLURM_JOB_ID`; there is no ordinary local-production bypass. This controls runtime and SSD/I/O load, improves scheduler resource control, preserves reproducible host/runtime boundaries, strengthens auditability, and supports later full-data phases.

### Phase 3 execution-site correction

- Local run `phase03_pilot_20260811T082940Z_025fb0ba` is `ABORTED_LOCAL_EXECUTION_POLICY_VIOLATION`, not a scientific failure. It was stopped before DEVELOPMENT/LOCKED identity sets or a seal were finalized and before either payload or any Phase 3 transformation existed.
- Its partial SQLite state is retained temporarily for audit, but is not resumed, deleted, or synchronized to Goethe-NHR. The production pilot restarts from scratch under a new cluster run ID; the frozen sampling methodology and scientific version remain unchanged.
- Real production `pilot-profile`, `pilot-select`, production-snapshot validation, and `pilot-materialize-development` are cluster-only. The 8,000-row DEVELOPMENT transform remains in the same cluster pilot workflow for reproducibility even though it is individually lightweight.

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

### Phase 3 approved design decisions

- Phase 3 is a deterministic derived-component phase only. It consumes only the immutable successful Phase 2 run `phase02_20260810T173851Z_1349152b` and must not modify it, create `address_key`, deduplicate addresses, determine geocoding readiness or `usable_for_analysis`, call SAFE/Pelias, or begin Phase 4.
- Phase 3 retains exactly one core component row per Phase 2 source row. Detailed competing candidates and raw-span evidence belong in a separate sparse controlled evidence sidecar keyed by `stable_source_row_id_v1`; the sidecar does not need one row for every source observation.
- The core table contains selected scalar components, compact selected-component provenance/rule identifiers, native alternatives, parse/completeness outcomes, conflicts/diagnostics, evaluation coverage, and version/fingerprint fields. Evidence-storage size, write/read cost, and join ergonomics must be benchmarked during the pilot before a full Phase 3 run.
- Placeholder interpretation is based on the exact raw value before normalization. Exact `""`, `"."`, and `"-"` are semantic missing in address/geographic fields. Exact `"Na"`, `"Nan"`, and `"Null"` are `AMBIGUOUS_PLACEHOLDER_LIKE` by default: they are neither automatically missing nor automatically meaningful and cannot populate a selected component without independent compatible evidence.
- Exact uppercase assigned ISO alpha-2 `NA` may be accepted as Namibia. Exact raw `Na` must not be case-normalized to Namibia by itself. It may resolve to `NA` only through separately supported compatible evidence; otherwise `country_clean` remains null and the placeholder/reference collision is recorded. The same collision rule applies to any placeholder-like literal that also matches a field-specific code or name after transformation.
- Python runtime `unicodedata.unidata_version` is authoritative for NFC behavior. The intended initial project interpreter currently resolves through `python3` to Python 3.14.3 with Unicode data 16.0.0, so the proposed initial cleaning identifier is `derived_text_nfc_ws_v1_ucd16.0.0`. Startup must assert the approved Python/Unicode versions and fail closed on mismatch; metadata records both.
- Any external Unicode Script-property files must come from the same Unicode release used for NFC, have recorded SHA-256 values and licensing metadata, and be pinned before the pilot. Phase 3 must not use undocumented script heuristics or silently upgrade Unicode data.
- `diagnostic_evaluation_status` describes how fully a row was safe to evaluate. Its exact vocabulary is `FULLY_EVALUATED`, `PARTIALLY_SKIPPED_OVERSIZED`, and `NOT_EVALUATED_OVERSIZED`. Oversized input is also recorded as a diagnostic, while safe structured fields and safe lines remain eligible for parsing.
- `address_parse_status` is separate from safety coverage and uses only `PARSED`, `PARTIAL`, `AMBIGUOUS`, `CONFLICT`, `UNPARSEABLE`, and `INSUFFICIENT`. Completeness describes actually selected components, including on partially evaluated rows.
- Extraction and selection behavior is defined only through a versioned rule registry. Every rule declares its eligible source fields, exact preconditions and matching/extraction condition, comparison normalization, candidate behavior, fixed confidence, selection priority, conflict behavior, maximum input size, and tests. Confidence is assigned by rules, never by an undocumented score.
- Evidence spans use zero-based Unicode code-point offsets `[start_character, end_character_exclusive)` into one exact Phase 2 raw string before NFC, whitespace collapse, control replacement, or trimming. Rules retain raw token spans and normalize extracted substrings only after locating them. A candidate assembled from multiple pieces carries multiple raw spans.
- Country validation and name mapping use an explicit reference abstraction. ISO 3166 remains the normative code-system authority, while pinned Unicode CLDR 46.1 is the operational machine-readable mapping. The two roles must never be conflated.
- Phase 3 integrity uses exact binary canonical serialization, not JSON or Python representations. Independent read-back must reproduce core and evidence semantic digests, and a dataset digest binds the ordered shard paths, row counts, and raw 32-byte per-shard digests.
- The approximately 12,000-row pilot is split into a rule-development subset and a locked evaluation subset. Rules may change only during development. Before locked evaluation, parser/rule/policy/reference/normalization versions and evaluation metrics are frozen and quantitative thresholds are pre-registered. Any revision after locked evaluation requires a new parser version and new locked evaluation sample/version.
- Manual review remains in a protected environment. Raw confidential addresses are not copied into Git, portable reports, public issue trackers, or external AI/services without explicit institutional permission. Review datasets use hashed review identifiers; labels and aggregate metrics may be stored separately from raw text.
- The official versioned Unicode 16.0.0 `Scripts.txt` is pinned as `unicode_ucd_16_0_0_scripts_20240430` (189,588 bytes; SHA-256 `9e88f0a677df47311106340be8ede2ecdacd9c1c931831218d2be6d5508e0039`) and vendored with the Unicode License v3 notice (`Unicode-3.0`).
- ISO 3166 and the ISO 3166 Maintenance Agency remain the normative country-code authority. No paid ISO Country Codes Collection is copied or reconstructed. The operational reference is `country_reference_v2_iso_normative_cldr_46_1_operational`, a deterministic 249-row four-string-field extraction from official Unicode CLDR 46.1 (23,477 bytes; SHA-256 `6d38c9431a97dff511da8048381de42b27c5eef7b9a94409400f16f3d332325a`).
- The minimum CLDR source files, canonical extraction, and exact Unicode License v3 notice are vendored. Unicode-3.0 permits internal use, modification/extraction, private-repository storage, and future redistribution when the notice is retained.
- The selectable CLDR country subset requires `idStatus=regular`, a canonical English name without `alt`, complete alpha-3/numeric mappings, and exclusion of ISO user-assigned alpha-2/numeric ranges. All other CLDR statuses, seven incomplete regular identifiers, and `XK` are non-selectable.
- `evidence_sidecar_policy_v1` omits ordinary conflict-free direct structured propagation, retains nontrivial selected/candidate/conflict/ambiguity/unassigned evidence with raw spans, and records unevaluated oversized skips compactly in the core rather than copying their raw values into the sidecar. Protected review joins raw context in place and never makes it portable.
- The executable `phase03_rule_registry_v2` contains exactly 12 rules. Its closed execution-disposition vocabulary is `AUTHORITATIVE_SELECTABLE`, `AUTHORITATIVE_CANDIDATE_ONLY`, `AUTHORITATIVE_DIAGNOSTIC_ONLY`, and `DEVELOPMENT_SHADOW_ONLY`. Disposition is part of the canonical registry and effective configuration fingerprints.
- `HOUSE_NUMBER_EDGE_CANDIDATE_V1` is LOW-confidence `DEVELOPMENT_SHADOW_ONLY`. It executes only on a separately authorized development subset, emits protected evidence only, and cannot populate street/house core values or affect completeness, parse status, core conflicts, or readiness. It never executes on locked evaluation or authoritative scope. Any future promotion requires development-review precision evidence and a new rule version; fill rate is insufficient.
- Manual review uses the closed `manual_review_reason_codes_v1` vocabulary. Reasons are multi-valued, deduplicated, and stored in canonical vocabulary order; unknown values fail. `OTHER_ADJUDICATION_REQUIRED` requires a separate protected note that is never portable. The portable schema contains no raw address values.
- Development review may lead to new rule versions. Locked evaluation may not be used for tuning. A locked-evaluation defect requiring methodological change yields `FAIL/REVISE`, a new parser/rule version, and a new locked-evaluation sample/version.
- Phase 3 framework/synthetic implementation is complete at baseline commit `64895b7`. Real pilot selection/execution and the full 206-shard Phase 3 run remain separately authorized actions.
- Phase 3 reference-readiness and readiness-maintenance work was committed at clean baseline `6c95fa2136a6f2bf92e51f30f41ae972c0a32a5b` before the CLDR replacement. The CLDR change does not authorize reading or selecting the real pilot.
- `phase03_sampling_contract_v1` is frozen. Selection uses exactly two selected-column passes: country-only profiling, then the approved 16-column classification pass; full rows are read only for the separate DEVELOPMENT join.
- Exact country groups are case-sensitive pinned-CLDR matches, semantic-missing/ambiguous buckets, or a domain-separated digest for unusual content. Cohorts are `RARE` below 50, `MEDIUM` at 50–499, and `LARGE` at 500 or more. All rare-group rows are mandatory; secondary minima are 50; exact primary groups are capped at 500.
- Sampling-only structured completeness is HIGH for 3–4 content fields, MEDIUM for 2, LOW for 1, and NONE for 0; ambiguous presence is independent. The exact postcode precedence, content-only address-line counts, separate native/non-native script categories, and native-relationship precedence are frozen in `docs/PHASE03_PILOT_RUNNER_DESIGN.md`.
- Production Pass 2 uses owner-only exact SQLite state and requires at least 25 GiB free local disk. The state, identity sets, and seal are bound to their versioned schemas, Phase 2 manifest, sampling contract, references, registry, Git/configuration identity, and deterministic seed/ranking rules.
- The DEVELOPMENT manual-review sample is exactly 800 unique rows: 400 broad-representation rows plus overlapping targeted minima and deterministic fill. Exactly 200 are designated for independent double review. Unavailable targets include all available rows and emit `TARGET_NOT_FULLY_AVAILABLE` diagnostics.
- The first completed DEVELOPMENT diagnostic reviews established a material
  recall defect in `conservative_address_parser_v1`; they are preserved as
  audit evidence for a rejected parser iteration, not treated as a completed
  scientific review.
- The approved DEVELOPMENT correction is
  `conservative_address_parser_v2` paired only with
  `phase03_rule_registry_v3`. The frozen v1/v2-registry pair remains the
  package default so the already selected DEVELOPMENT and sealed
  LOCKED_EVALUATION identity sets cannot change silently.
- Parser v2 adds bounded, deterministic selectable rules for explicit
  designator-bearing HIGH street/house segments and language-light Unicode
  MEDIUM street/house segments, plus explicit unit, floor, building, and
  legal-form organization roles. The project-owned `street_designators_v2`
  resource is exact, versioned, scoped to seven documented language families,
  and hash-bound into the registry/configuration identity. Parser v2 also makes
  the existing native/non-native house-number conflict vocabulary executable
  and computes residual material from unowned source spans. Exact rule scope,
  precedence, false-positive boundaries, limitations, and fingerprints are in
  `docs/PHASE03_PARSER_V2.md`.
- Parser v2 changes no Phase 2 raw value, pilot identity, sampling contract,
  component/evidence schema, cleaning rule, placeholder rule, country/Unicode
  reference, safety limit, candidate limit, or Phase 4 decision. It is
  authorized only for a new immutable rerun of the existing 8,000 DEVELOPMENT
  payload; LOCKED_EVALUATION remains sealed and inaccessible.
- Parser-v1 and parser-v2 DEVELOPMENT outputs must be compared on the identical
  ordered identities using only privacy-safe aggregate diagnostics. No
  scientific acceptance threshold is inferred automatically.
- The DEVELOPMENT portable manual-review v2 schema intentionally has 28
  columns, superseding the earlier 27-column draft because `assignment_role`
  was added before any v2 artifact existed. Tests freeze its exact Arrow order,
  nullability, allowed values, and identity-level independent-review semantics.

## Open decisions

- Whether, and under what evidence/rules, an address-layer interpolated result is `usable_for_analysis`.
- Whether parser-v2 DEVELOPMENT review supports freezing its selectable rules
  for a future, separately versioned and authorized evaluation.
- Final Phase 3 operational settings after the required real development-pilot benchmark of storage size, compression, write/read throughput, memory, and join ergonomics. Synthetic evidence currently supports retaining the provisional limits/settings.
- Quantitative Phase 3 parser/manual-review acceptance thresholds. These must be pre-registered after the development subset and before the locked evaluation subset is opened.
- Whether a pinned libpostal build/model should be evaluated only as a secondary candidate generator during the development pilot.
- International canonical-address rules that are not yet expressible as exact registry entries remain unresolved and must not be invented during implementation.
- Native-script versus transliterated primary/rescue query rules.
- Exact versioned address-key serialization and fields included in it.
- Final input eligibility/completeness thresholds and controlled rescue-query ladder.
- Pilot 2 necessity, sampling design, and size.
- Manual ground-truth protocol and evidence needed for interpolation policy.
- Candidate comparison, component-agreement thresholds, and manual-review thresholds.
- Any external geographic boundary/reference dataset, including source, license, vintage, and coverage.
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

- **Superseded for active Phase 3:** UNSD M49 as the operational country
  mapping. The associated institutional-use question remains unresolved but is
  no longer a project gate because active Phase 3 code does not load, query, or
  fingerprint the UNSD artifact.
- **Replacement:** ISO 3166 remains the normative code system; official Unicode
  CLDR 46.1 under Unicode-3.0 is the pinned operational mapping.
- **Superseded:** The current source collection was previously estimated at approximately 500 GB.
- **Replacement:** The authoritative current source dataset is 206 CSV files totaling approximately 3.29 GB.
- There is currently no known additional source collection that this pipeline must process.
- Engineering choices must reflect the verified current scale. CSV-aware parsing, chunking/streaming where useful, and robust diagnostics remain necessary because parsed memory use can be much larger and extreme multiline fields exist. Distributed or big-data technology is not justified solely by the superseded estimate.
