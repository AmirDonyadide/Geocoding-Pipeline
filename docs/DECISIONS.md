# Decision register

This register distinguishes approved project rules from questions that require evidence or explicit scientific approval. Previous code and sample behavior cannot change a decision's status.

## Locked decisions

- The active preprocessing architecture is library-first. Mature offline
  libraries and pinned reference datasets are preferred when they satisfy the
  scientific, privacy, licensing, and reproducibility contracts. Custom SAFE
  code primarily supplies orchestration, provenance, deterministic evidence
  aggregation, conservative policy, validation semantics, and verified gaps.
  The historical custom/from-scratch parser remains exactly recoverable at
  `baseline/custom-preprocessing-2026-08` for provenance and comparison; it is
  not the active production path.
- Library-first Stage 0 reuses historical Phase 1 as the single authoritative
  source scanner. Stage 0 may validate, project, fingerprint, permission-harden,
  and adopt Phase 1 output, but it does not duplicate discovery, CSV parsing,
  source hashing, schema inspection, duplicate analysis, or profiling.
- Stage 0 scientific identity uses the distinct domain-separated
  `source_population_sha256_v1` and
  `stage00_scientific_inventory_sha256_v1` binary contracts documented in
  `docs/STAGE00.md`. Operational timestamps, mtimes, durations, host/SLURM
  identity, Git/runtime versions, and permissions are excluded from both.
- The completed Phase 1 bundle is adopted without reopening or rescanning the
  source CSVs. Historical report bytes remain unchanged; owner-only hardening
  of retained protected working state is an operational privacy action.
- Stage 0 status is `STAGE_0_ACCEPTED` after its final critical review. Stage 1
  remains a separate stage and was not started by the Stage 0 acceptance work.
- Future Phase 1 `FULL_INVENTORY` execution is population-generic and requires
  an explicit hash-pinned owner-only `stage00_population_scope_v1` artifact.
  Its exact canonical direct-child CSV path set, expected count, Phase 1
  inventory version, source-schema fingerprint, and parser ceiling define the
  authorized scope. Directory contents cannot add files implicitly, and
  source/scope membership is bound to resume state and revalidated before
  success publication. The historical 206-file run remains unchanged evidence.
- Library-first Stage 1 reuses historical Phase 2 as the single authoritative
  CSV-to-Parquet converter. Stage 1 validates and adopts the existing complete
  Phase 2 bundle; it does not rescan source CSVs, rewrite Parquet, or duplicate
  conversion, stable-ID, semantic-digest, schema, or reconciliation logic.
- `stage01_logical_dataset_sha256_v1` binds Stage 0 scientific identity, the
  exact source/schema/stable-ID/semantic-digest contracts, and the canonical
  per-source path/SHA/count/semantic-digest projection. Physical shards,
  compression, row groups, Parquet hashes, Git/runtime provenance, and
  timestamps are excluded from logical scientific identity.
- Current Stage 1 physical layout is `KEEP_CURRENT_SHARDS`: the accepted 206
  historical Phase 2 Parquet files remain byte-immutable. One source per shard
  is operational Phase 2 v1 history, not a permanent Stage 1 scientific rule.
- Exact duplicate source content fails Stage 1 because
  `stable_source_row_id_v1` intentionally excludes path and would collide at
  matching logical ordinals. Stage 1 neither disambiguates by path nor removes
  a source record. Stage 1 status is `STAGE_1_ACCEPTED` after its final critical
  review. Stage 2 was subsequently implemented and accepted on the complete
  protected 35,000-row DEVELOPMENT population.
- Future Phase 2 `FULL_CONVERSION` execution is population-generic and requires
  an explicit hash-pinned accepted Stage 0 adoption record. Exact canonical
  path/SHA/logical-count scope, not a global count or current directory
  contents, controls conversion and resume. The historical 206-source result
  remains immutable evidence and remains reproducible from its exact historical
  commit and accepted Stage 0 snapshot.
- `BENCHMARK_SAMPLE_V1` is a fixed 50,000-source-row evaluation product from
  the explicitly authorized 1,405-file development population: 35,000
  DEVELOPMENT and 15,000 physically separate HOLDOUT rows. The six missing
  delivery files are not silently added later. Selection is deterministic,
  uses immutable source provenance plus raw structural strata, and performs no
  address transformation or deduplication. HOLDOUT is excluded from tuning and
  may be used only under an explicit final-evaluation protocol. See
  `docs/BENCHMARK_SAMPLE.md`.
- Library-first Stage 2 uses
  `stage02_schema_provenance_harmonization_contract_v1`. It preserves the exact
  15 source strings and immutable source provenance, leaves
  `stable_source_row_id_v1` unchanged, keeps standard and native address lines
  separate, and adds only raw non-empty-line presence/count fields. Empty means
  exact source `""`; no trim, normalization, comparison, language/script
  classification, parsing, or candidate construction occurs.
- A SHA-pinned `stage02_input_binding_v1` binds an exact accepted Stage 1 or
  benchmark DEVELOPMENT input. The benchmark interface rejects HOLDOUT paths
  and non-DEVELOPMENT rows and does not read HOLDOUT. Stage 2 logical identity
  binds upstream scientific identity, schema/derivation contracts, and row
  count while excluding physical layout and operational provenance. Protected
  execution remains Goethe/SLURM-only. DEVELOPMENT job `1758833` accepted the
  exact 35,000-to-35,000 result without changing incoming values or identities.
- DEVELOPMENT reporting uses the scientifically passive
  `development_reporting_contract_v1` and fixed
  `development_review_subset_contract_v1`. Exactly 500 DEVELOPMENT identities
  are selected from accepted benchmark structural metadata with
  domain-separated deterministic provenance hashes. The same identities are
  used by immutable per-stage protected review artifacts. Reporting does not
  change stage outputs or acceptance; portable summaries use a strict
  aggregate allowlist, full 35,000-row metrics remain quantitative evidence,
  and HOLDOUT is rejected and remains sealed.
- Stage 3 v1 under `stage03_safe_text_cleaning_contract_v1` and
  `stage03_safe_text_cleaning_profile_v1` was not accepted. Independent review
  reproduced the complete 35,000-row scientific output, found no questionable
  change or semantic damage, and accepted all observed encoding/control/
  whitespace behavior, but rejected the production implementation's total-row
  identity sets, repeated cleaning lifecycle, ambiguous zero-punctuation
  metric, and incomplete BOM regression evidence. V2 may change
  implementation, validation, manifest, performance, and reporting evidence
  only; the scientific cleaning rules remain unchanged and exact v1/v2 clean
  values are a required new gate.
- Stage 3 v2 identity integrity uses exact batch/shard equality to the accepted
  Stage 2 arrays plus domain-separated ordered stable-ID fingerprints and row
  counts. This binds the accepted upstream duplicate-free invariant without
  accumulating stable IDs in a total-row Python set. Idempotence re-cleans all
  changed results; unchanged results are already exact fixed points of the
  deterministic pinned cleaner. Readback, terminal validation, reporting, and
  v1/v2 comparison do not invoke the cleaner. Literal punctuation-codepoint
  changes are measured separately from the fixed zero count for semantic
  punctuation normalization.
- Stage 3 v2 implementation
  `278414573fd465e261f3b9131c45fb564b93622d` completed its immutable 35,000-row
  DEVELOPMENT run as job `1759269`. It proved exact v1/v2 clean-value and
  reason-code equality, preserved all incoming Stage 2 values, measured zero
  identity/idempotence failures, and corrected the punctuation evidence to 9
  literal codepoint changes in encoding-repaired fields and zero semantic
  punctuation normalizations. Its 36.605-second materialization and
  1,067,884-KiB process peak RSS support a 2-CPU, 16-GiB, 72-hour Goethe
  production request. The row-linear 141,048,582-row projection is about 41
  hours and is an estimate, not a runtime guarantee. This evidence makes v2 a
  DEVELOPMENT candidate ready for independent review; it does not accept Stage
  3 or authorize Stage 4.
- The accepted current Stage 0 development snapshot contains 1,405 files and
  140,448,582 logical rows. It remains frozen. Six files became available only
  later and may form an independent 1,411-file source snapshot, but that
  population requires its own Stage 0 run before Stage 1 production. Neither
  the 1,405 Stage 0 result nor Benchmark V1 is retroactively redefined.
- `BENCHMARK_SAMPLE_V1` is accepted with fingerprint
  `014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf`.
  Its 35,000 DEVELOPMENT and 15,000 HOLDOUT rows are disjoint, have no
  duplicate selected identities, and cover all 1,405 source files. It remains
  permanently tied to that population; HOLDOUT is sealed until one explicitly
  authorized final evaluation after the complete pipeline is frozen.
- Both standard and native address representations originate from Orbis. Some
  standard representations are English translations; native is likely the
  more authoritative original form, and prior Nominatim work used native
  names. They are evaluated independently, including by country, and may both
  be geocoded where useful. Priority 0/1 are the most useful initial
  regeocoding groups. Interpolation describes location estimation from
  postcode or region and does not imply that source address text was filled or
  changed. Remaining authority and query-policy questions require evidence.
- Pre-geocoding component validation retains the closed outcomes `CONFIRMED`,
  `MISMATCH`, `NOT_FOUND`, `AMBIGUOUS`, `UNSUPPORTED`, and `INVALID_FORMAT`.
  Absence from an open reference dataset is not invalidity. Independent checks
  remain required even when Pelias uses overlapping sources because they
  provide component-level format, consistency, ambiguity, and correction
  evidence that a Pelias failure alone cannot explain.
- Each address-changing library-first stage follows the frozen-development
  discipline: design, implementation, synthetic tests, 35,000-row DEVELOPMENT
  execution, protected metrics/example review, tuning, acceptance/freeze, then
  the next stage. Once the entire pipeline is frozen, the untouched 15,000-row
  HOLDOUT is used once for unbiased evaluation before full production. Repeated
  HOLDOUT tuning is prohibited.

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
- GitHub `origin` is the shared source of truth for code, tests, configuration, and documentation. Coherent reviewed changes are committed and pushed from the Mac to an appropriate branch; force-pushes and shared-history rewrites require explicit approval. Goethe-NHR obtains code through Git, not source-file rsync.
- Cluster code is synchronized before job submission with fetch/status and a fast-forward-only update of a clean tracking branch, or with a detached integration worktree at an exact pushed commit. A SLURM job never performs an uncontrolled pull; it records and validates the exact commit used. Large data, generated outputs, logs, credentials, and environment files remain outside Git.
- `/scratch` is not used; `/work/footprint/public` and the shared Conda base are not modified.
- The existing `parquet_files` products are invalid and cannot serve as staging data.
- Work proceeds one reviewed phase at a time and stops after every phase.
- The completed parser-v3 experiment remains unpromoted. Its targeted human
  review population is the deterministic deduplicated union of DEVELOPMENT
  rows with v2-v3 scientific-output changes and rows with either experimental
  rule's evidence. The review was prepared for two independent blinded reviews
  in a separate owner-only Goethe namespace; the main 800-row review and
  LOCKED_EVALUATION remain untouched. No frequency, review result, or fill rate
  automatically promotes the experiment.
- After Targeted-R01 completed all 11 targeted DEVELOPMENT cases, the targeted
  review protocol was explicitly changed to single-reviewer evaluation.
  Targeted-R02 is skipped, its original pending SQLite assignments remain
  untouched, and no labels may be copied, fabricated, or inferred for it. The
  controlled export and sanitized score must declare `SINGLE_REVIEWER`, record
  `SKIPPED_BY_EXPLICIT_DECISION`, and leave inter-reviewer agreement and
  adjudication metrics unevaluated. This deliberate reduction in evidentiary
  strength does not promote Parser v3.1 or weaken the existing two-reviewer
  mode for any other invocation.
- Targeted-review preparation job `1749345` is a fail-closed population-gate
  stop, not scientific evidence for changing the reviewed expected count. The
  observed DEVELOPMENT sets are A=26 scientific-core changes and B=11
  experimental-rule-evidence rows, with nine overlap, 17 A-only, two B-only,
  and 28 in the union. Before any workspace initialization, the separately
  versioned `phase03_parser_v3_change_diagnostic_v3` must explain those
  non-overlap populations using only aggregate fixed-field/family/provenance
  counts from immutable v2/v3 outputs. No Parser v3 rule, population gate, or
  human-review decision changes automatically from that diagnostic. Separate
  aggregate rule-selection totals do not establish identity-level V4 rule
  pairing; rule presence, asymmetric selection, rejection, and multiple-group
  states are measured and small cells are suppressed rather than treated as a
  fail-closed scientific invariant. Job `1749444` showed the 17 A-only rows
  differ solely in `country_parse_method`; diagnostic v3 adds a privacy-safe
  controlled-vocabulary transition table and evidence/provenance equality
  reconciliation. Shared v2/v3 country-method derivation is hash-seed-sensitive
  when an unselectable same-value free-form country candidate contributes a
  second reference kind. This defect is not removed from scientific comparison
  and is not treated as a Parser-v3 country-rule change. The explicit repaired
  v2.1/v3.1 lineages executed successfully in Goethe job `1749448`; their
  aggregate comparison contains nine substantive scientific changes and no
  remaining country-method-only population. Historical 26/28 counts remain
  audit evidence only. The active targeted-review population remains the exact
  A-union-B definition and has a fail-closed repaired expectation of 11 only
  after a separate identity-level verifier proves 8,000/9/11/9/0/2/11 against
  the hash-pinned repaired artifacts. Review preparation requires that passing
  sanitized report; neither preparation nor reviewer initialization is
  authorized by the verifier implementation.
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
- Before the historical 206-file full run, all source files had to be fully hydrated, adequate free space confirmed, and active source modification prevented. That historical execution evidence remains unchanged. Future runs apply the same quiescence/integrity rules to the exact explicitly authorized scope rather than a fixed count.
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
- Parser-v2 structural-gap profiling reuses only the fixed 8,000 DEVELOPMENT
  payload/core/evidence and never accesses LOCKED_EVALUATION or changes parser
  semantics. Portable outputs contain closed abstract token classes and
  aggregates only: named patterns require at least five distinct rows and each
  bounded distribution reports at most 100 names. These are disclosure
  controls, not parser confidence or acceptance thresholds; profiler frequency
  cannot authorize a parser-v3 rule.
- The follow-up targeted opportunity profile is restricted to eight
  predeclared numeric/text pattern families and the same fixed DEVELOPMENT
  artifacts. All cross-tab categories require at least five distinct rows,
  are capped at 100 names, and contain only closed structural labels and
  aggregate counts. This diagnostic cannot create or approve Parser v3 rules.
- Sanitized targeted profile job `1749332` supports one narrow, unapproved
  DEVELOPMENT experiment for the `WORDS HOUSELIKE_NUM WORDS` family. Parser
  `conservative_address_parser_v3_experimental` accepts only one same-line,
  punctuation-free center integer when exactly one side is an approved
  designator-bearing street, the opposite side is one non-role word, at least
  two unambiguous structured geography components corroborate the row, no
  existing address-role candidate competes, postcode equality is absent, and
  a material native/non-native counterpart independently agrees exactly. The
  opposite word remains residual. The atomic hypothesis is represented by the
  paired v4 street/house registry entries documented in
  `docs/PHASE03_PARSER_V3_EXPERIMENT.md`.
- Parser v3 is not scientifically approved and does not replace parser v2.
  Promotion requires exact same-identity 8,000-row DEVELOPMENT comparison,
  acceptable conflict/lost-selection diagnostics, and targeted protected human
  review. The seven other targeted morphology families remain unsupported.
- Country-method diagnostic job `1749446` established a shared v2/v3
  reproducibility defect: selected structured country evidence could receive a
  method label from an unselected same-value free-form candidate because
  `_country_result()` chose from an unordered set. The explicit repaired
  lineages are `conservative_address_parser_v2_1` and
  `conservative_address_parser_v3_1_experimental`, paired with the unchanged v3
  and v4 registries respectively. They derive the method only from the actual
  selected source/rule/value route and fail closed if that route is not unique.
  Historical v2/v3 iterations and identifiers remain unchanged for audit; the
  repaired 8,000-row comparison must be measured before any review gate changes.
  See `docs/PHASE03_COUNTRY_METHOD_REPAIR.md`.
- The DEVELOPMENT portable manual-review v2 schema intentionally has 28
  columns, superseding the earlier 27-column draft because `assignment_role`
  was added before any v2 artifact existed. Tests freeze its exact Arrow order,
  nullability, allowed values, and identity-level independent-review semantics.
- The completed Parser-v3.1 Targeted-R01 review is preserved as historical
  single-reviewer evidence: five of nine selected rows were jointly correct
  and four were false positives; Targeted-R02 was explicitly skipped and no
  promotion threshold was applied. Exact protected evidence confirmed an
  orientation split of 4/4 correct for `STREET_NUMBER_RESIDUAL` versus 1/5 for
  `RESIDUAL_NUMBER_STREET`.
- `conservative_address_parser_v3_2_experimental` with
  `phase03_rule_registry_v5_experimental` is the separately versioned,
  DEVELOPMENT-only narrowing. It retains only `STREET_NUMBER_RESIDUAL` and
  changes no other v3.1 condition. V2.1/v3.1 remain immutable and reproducible;
  v3.2 is not approved for promotion. Existing R01 labels may be reused only
  after exact identity/candidate/span equivalence is proved mechanically.
  See `docs/PHASE03_PARSER_V3_2_EXPERIMENT.md`.
- DEVELOPMENT evaluation job `1750488` established four retained v3.2
  selections, all four jointly street/house correct under the completed
  single-reviewer Targeted-R01 evidence, with zero observed false positives
  and three false-negative opportunities. Parser v3.1 remains unpromoted.
  Parser v3.2 is approved only as the candidate whose semantics may advance to
  a separately authorized LOCKED evaluation; production promotion remains
  `NOT_EVALUATED` and LOCKED remains sealed. Targeted-R02 was intentionally
  skipped, so no inter-reviewer agreement exists for this DEVELOPMENT result.
- The original DEVELOPMENT evaluation submission `1750475` was cancelled by
  the operator with zero runtime while pending for scheduler priority. The
  only DEVELOPMENT evaluation execution was replacement job `1750488`, which
  ran the exact commit `e78f52374c156477ce026e0d1dbb9755b85f5d82` on the
  frozen 8,000-row DEVELOPMENT inputs through Goethe SLURM's `test` partition.
  This differs from the job file's preferred `general1` partition but satisfies
  the repository's explicit execution-site contract, which requires Goethe
  plus SLURM and does not prohibit `test` for this bounded evaluation. The run
  is not repeated merely to change partition.
- The pre-LOCKED freeze is incomplete by design. The current v3.2 engine fails
  closed with `PARSER_V3_EXPERIMENT_DEVELOPMENT_ONLY` outside `DEVELOPMENT`,
  and no executable LOCKED materialization/transform/review workflow exists.
  Metric families are documented, but quantitative thresholds, exact metric
  formulas/aggregation, exact review-sample design, the chance-adjusted
  agreement measure, and the LOCKED PASS gate remain undefined. These must be
  separately reviewed and frozen before any LOCKED identity or payload is
  opened. The sanitized record is `docs/PHASE03_PRE_LOCKED_FREEZE.json`.
- The separately versioned `phase03_locked_evaluation_protocol_v1` freezes the
  pre-unseal evaluation methodology: a 400-row deterministic structural review
  sample, exactly 100 independently double-reviewed rows, exact precision and
  overreach denominators, 0.95 precision minima, 0.05 maximum overreach,
  per-label Cohen's kappa minimum 0.80, and a pre-registered undefined-kappa
  fallback requiring at least 80 assessable pairs and 0.95 exact agreement.
  Fill rate is prohibited. Any hard-gate, provenance, privacy, unexplained
  change, unrelated regression, or methodological-defect failure yields
  `LOCKED_FAIL_REVISE`; PASS never promotes or authorizes production. The
  executable path requires an exact LOCKED protocol token and cannot run v3.2
  under `AUTHORITATIVE`. See
  `docs/PHASE03_LOCKED_EVALUATION_PROTOCOL.md`.
- The completed `LOCKED-R01` labels are a user-authorized methodological
  deviation from that frozen protocol: Codex/AI, not a human reviewer,
  produced all 400 primary judgments. They may be used only as
  `LOCKED_AI_R01_DIAGNOSTIC` evidence. `LOCKED-R02` remains untouched, so
  human-human agreement and the preregistered final LOCKED decision are not
  available. The diagnostic must report each quantitative threshold result
  separately without emitting `LOCKED_PASS` or `LOCKED_FAIL_REVISE`, and must
  not be represented as human-review evidence. See
  `docs/PHASE03_LOCKED_AI_R01_DIAGNOSTIC.md`.
- Run `phase03_locked_evaluation_20260817T140155Z_7472394` is frozen as
  diagnostic-only observed evaluation data. The frozen 4,000-row LOCKED set
  was opened and processed; v2.1 and v3.2 had zero scientific-output
  differences, and V5 produced zero candidate/evidence rows. The original
  human-human protocol was not completed because R01 was performed by
  Codex/AI and R02 remains untouched. No formal `LOCKED_PASS` or
  `LOCKED_FAIL_REVISE` exists. This observed LOCKED set is permanently excluded
  from parser tuning, rule design, example discovery, and any future claim of
  untouched holdout evaluation.
- The next Parser-v3 DEVELOPMENT cycle begins with an aggregate-only H1/H2/H3
  intersection profile on the fixed 8,000-row DEVELOPMENT population. H1 is
  the existing component-span-overlap conflict set; H2 is explicit
  unit/floor/building/organization evidence overlapping street/house evidence;
  H3 is the narrow adjacent explicit-street/single-house-like-line set after
  preregistered structural exclusions. Exact identity overlap and completed
  Targeted-v3.1 R01 identity coverage may be counted, but those same-line V4
  labels are not silently reused for a different scientific question. This
  diagnostic authorizes no parser implementation and uses no LOCKED evidence.

## Open decisions

- Whether, and under what evidence/rules, an address-layer interpolated result is `usable_for_analysis`.
- Whether parser-v2 DEVELOPMENT review supports freezing its selectable rules
  for a future, separately versioned and authorized evaluation.
- Explicit user authorization to unseal and execute the frozen LOCKED protocol;
  protocol implementation and pre-execution validation do not grant it.
- Final Phase 3 operational settings after the required real development-pilot benchmark of storage size, compression, write/read throughput, memory, and join ergonomics. Synthetic evidence currently supports retaining the provisional limits/settings.
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
- **Historical replacement:** The first accepted source snapshot is 206 CSV files totaling approximately 3.29 GB.
- A later delivery is not authoritative until its exact population is frozen and accepted through the versioned Stage 0 scope and inventory contracts.
- Engineering choices must reflect the verified current scale. CSV-aware parsing, chunking/streaming where useful, and robust diagnostics remain necessary because parsed memory use can be much larger and extreme multiline fields exist. Distributed or big-data technology is not justified solely by the superseded estimate.
