# Decision register

This register contains durable scientific and operational decisions for the
active library-first pipeline. Empirical reports are evidence, not permission
to change a decision or start a stage.

## Locked decisions

### D001 — Raw source values are immutable

- **Date:** 2026-08-27 (consolidated; decision predates this record)
- **Scope:** All stages
- **Decision:** Source values are never overwritten, silently cleaned, skipped,
  truncated, or discarded. Every transformation is a separate derived value.
- **Rationale:** Scientific auditability and exact source traceability.
- **Status:** LOCKED.

### D002 — Stable row identity and source-row preservation

- **Scope:** Stage 1 onward
- **Decision:** `stable_source_row_id_v1` remains unchanged. Provider `id` is
  not assumed globally unique. Source rows are never deduplicated away;
  candidate/query deduplication retains a complete map-back.
- **Rationale:** Prevent row loss, join ambiguity, and irreproducible identity.
- **Status:** LOCKED.

### D003 — Library-first preprocessing is the active architecture

- **Scope:** Stages 0–19
- **Decision:** Prefer mature offline libraries and pinned direct references
  when they meet scientific, privacy, licensing, and reproducibility needs.
  SAFE code provides orchestration, provenance, evidence, conservative policy,
  validation semantics, execution guards, and verified gaps.
- **Rationale:** Reduce custom algorithm risk while retaining SAFE-specific
  scientific control.
- **Status:** LOCKED. The current repository presents only this architecture;
  immutable Git ancestry retains prior development provenance.

### D004 — DEVELOPMENT, HOLDOUT, and production are separate tracks

- **Scope:** Evaluation and execution
- **Decision:** DEVELOPMENT is used for design/tuning; HOLDOUT remains sealed
  until a single final evaluation; production requires separate stage-specific
  authorization. DEVELOPMENT acceptance never authorizes production.
- **Rationale:** Prevent evaluation leakage and uncontrolled scaling.
- **Status:** LOCKED.

### D005 — Benchmark V1 remains based on 1,405 files

- **Scope:** Benchmark
- **Decision:** Benchmark V1 is permanently 50,000 rows: 35,000 DEVELOPMENT and
  15,000 HOLDOUT, fingerprint
  `014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf`.
  The six later files are not added and the benchmark is not rebuilt.
- **Rationale:** Preserve a fixed comparable evaluation population.
- **Status:** LOCKED.

### D006 — Fixed 500-row qualitative review

- **Scope:** DEVELOPMENT reporting
- **Decision:** The same 500 deterministic DEVELOPMENT identities, fingerprint
  `014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52`,
  are followed in immutable per-stage review artifacts. Full 35,000-row metrics
  remain the quantitative evidence.
- **Rationale:** Stable same-row human comparison without example cherry-picking.
- **Status:** LOCKED.

### D007 — Standard and native representations are separate candidates

- **Scope:** Stage 2 onward
- **Decision:** Both representations originate from Orbis and are preserved,
  reconstructed, parsed, evaluated, and potentially queried independently.
  Native values are not overwritten by English/standard translations. Any
  future transliteration is a separate candidate. All address lines are not
  blindly concatenated.
- **Rationale:** Preserve original-script evidence and avoid false equivalence.
- **Status:** LOCKED.

### D008 — Lowercase follows safe cleaning

- **Scope:** Stages 3–4
- **Decision:** Stage 3 performs safe cleaning without lowercase. Derived
  Unicode lowercase forms belong to Stage 4.
- **Rationale:** Isolate and audit distinct transformations.
- **Status:** LOCKED sequence. Accepted DEVELOPMENT Stage 4 implements this
  boundary exactly.

### D009 — Reconstruction precedes parsing

- **Scope:** Stages 5–7
- **Decision:** Reconstruct standard/native candidates before libpostal parsing;
  do not parse isolated lines and infer a complete address without the approved
  reconstruction layer.
- **Rationale:** Parsing needs a reviewed candidate boundary and line-use
  provenance.
- **Status:** LOCKED sequence. Stages 5 and 6 are accepted on DEVELOPMENT;
  Stage 7 is in a revised DEVELOPMENT design diagnostic under D023.

### D010 — Abbreviation normalization is component-aware and post-parsing

- **Scope:** Stage 9
- **Decision:** Abbreviation/linguistic normalization occurs after parsing and
  component mapping, using component/country/language/script context. Blind
  English rules on native candidates are prohibited.
- **Rationale:** Prevent semantic damage across address components and scripts.
- **Status:** LOCKED sequence; Stage 9 is NOT STARTED.

### D011 — Validation has closed outcomes; absence is not mismatch

- **Scope:** Stages 11–16
- **Decision:** Use `CONFIRMED`, `MISMATCH`, `NOT_FOUND`, `AMBIGUOUS`,
  `UNSUPPORTED`, and `INVALID_FORMAT`. Absence from an open reference is not
  invalidity. `MISMATCH` requires strong positive contradictory evidence.
- **Rationale:** Open spatial references have incomplete and uneven coverage.
- **Status:** LOCKED.

### D012 — Stage 3 v1 rejected; v2 scientifically identical and accepted

- **Scope:** Stage 3
- **Decision:** V1 implementation `8446190…` and evidence `9ed24ce…` remain
  rejected evidence. V2 implementation `2784145…` changed scalability,
  validation, lifecycle, and reporting—not cleaning rules—and proved exact
  clean-value and ordered-reason equality. Evidence `82e945a…` received
  `STAGE_3_ACCEPTED`; integration is `958dddc…`.
- **Rationale:** Preserve scientifically valid output while correcting
  production-unscalable identity state and inaccurate/incomplete evidence.
- **Status:** LOCKED. History must not be squashed or rewritten.

### D013 — Production uses all 1,411 files

- **Scope:** Production Stages 0–1
- **Decision:** `production_population_1411_v1` contains 1,411 files and
  141,048,582 rows. Production Stage 0 and Stage 1 are accepted. Production
  Stages 2–6 are not started.
- **Rationale:** Distinguish current production scope from frozen Benchmark V1.
- **Status:** LOCKED current state. Production Stages 2–6 are not started.

### D014 — Planned technology sequence

- **Scope:** Stages 0–19
- **Decision:** Current planned choices are those in [PIPELINE.md](PIPELINE.md):
  PyArrow/Parquet and DuckDB for ingestion; `unicodedata`/ftfy/Arrow for safe
  cleaning; Unicode `lower()` for Stage 4; PyArrow, DuckDB, and Python
  `hashlib` for Stage 6 exact deduplication; libpostal for parsing/mapping;
  pycountry;
  google-i18n-address; pinned direct GeoNames postal data; local Overture Maps
  Addresses GeoParquet with optional OSM fallback; RapidFuzz after blocking;
  and SAFE evidence/selection/query layers.
- **Rationale:** Library-first offline processing under reproducible privacy
  controls.
- **Status:** Accepted-stage choices are bound by the reviewed contracts for
  Stages 0–6. Stages 7–19 remain planned. pgeocode is proof-of-concept only.
  Pandas is inspection-only.

### D015 — Protected data never leaves controlled infrastructure

- **Scope:** All data and execution
- **Decision:** No protected address, row artifact, DEVELOPMENT view, HOLDOUT,
  production artifact, or query is sent to an external API/geocoder/web service
  or LLM, or committed to Git. SAFE Pelias is self-hosted.
- **Rationale:** Confidentiality and institutional data-governance obligations.
- **Status:** LOCKED.

### D016 — Heavy/protected execution is Goethe-NHR SLURM only

- **Scope:** Production/heavy processing
- **Decision:** Require `SAFE_EXECUTION_SITE=goethe-nhr` and non-empty
  `SLURM_JOB_ID` before input access. Controlled directories are `0700`, files
  `0600`; publication is atomic and fail-closed.
- **Rationale:** Protect data, resource use, reproducibility, and auditability.
- **Status:** LOCKED.

### D017 — SAFE Pelias scientific result policy

- **Scope:** Future geocoding
- **Decision:** Prefer `/v1/search/structured`, normally `size=1`, with 2–4
  requests total across the process. A returned first feature or high confidence
  is not automatic scientific success. Layer, match type, component/geographic
  agreement, and contradictions drive evaluation. Coarse results are not usable
  for point-level research.
- **Rationale:** Geocoder availability is distinct from location precision and
  scientific validity.
- **Status:** Historical future-geocoding rule. D032 prospectively supersedes
  the `size=1` and blanket coarse-result treatment with top-N retention and an
  explicit evidence-supported granularity decision. No geocoding is authorized
  until the proposed replacement architecture and execution gate are accepted.

### D018 — Production Stage 3 requires a separate launcher review

- **Scope:** Future production Stage 3
- **Decision:** The accepted DEVELOPMENT Stage 3 launcher is evidence
  infrastructure and must not be reused unchanged for production. A
  materialization-only production wrapper is reviewed after production Stage 2
  acceptance.
- **Rationale:** DEVELOPMENT launcher includes fixed-review and v1/v2 comparison
  work not appropriate for production materialization.
- **Status:** LOCKED. No production Stage 3 launcher is approved.

### D019 — Stage 4 uses exact Python Unicode lowercase

- **Scope:** Stage 4 DEVELOPMENT
- **Decision:** Derive each `stage04_lower_*` value as exact Python 3.14.3 /
  Unicode 16.0.0 `stage03_clean_value.lower()`. Do not casefold, use locale-
  specific casing, or normalize after lower. PyArrow `utf8_lower` is prohibited
  because it differs for U+0130 and context-sensitive Greek sigma. An ASCII-
  proven `ascii_lower` fast path is permitted only under zero-mismatch
  differential evidence.
- **Rationale:** Preserve the narrow planned Stage 4 boundary and exact Unicode
  semantics without changing science for speed.
- **Status:** `STAGE_4_ACCEPTED` on DEVELOPMENT. Production Stage 4 remains not
  started and is not authorized by this decision.

### D020 — Stage 5 conservatively reconstructs line bodies

- **Scope:** Stage 5 DEVELOPMENT
- **Decision:** Reconstruct standard and native representations independently
  from exact nonempty lines in source position order 1 through 4, using exact
  separator `" "`. Append both case-preserving clean and lowercase candidates
  plus compact availability/count/mask provenance. Preserve gaps and duplicate
  line occurrences; do not append geographic fields.
- **Rationale:** This is the narrowest representation that prevents token
  concatenation without inserting punctuation that asserts an unsupported
  component boundary. Full human review of v1 found four questionable comma-
  space boundaries, including punctuation adjacency and wrapped phrase/ordinal
  cases. A space preserves upstream punctuation and fixes the general issue
  without inspecting characters, parsing, or using country rules. Non-left-
  packed and repeated-line evidence remains unchanged.
- **Status:** `STAGE_5_ACCEPTED` on DEVELOPMENT after authoritative job
  `1759603` and independent job `1759692`. The independent risk-based human
  review found six questionable boundaries but zero questionable orders and
  zero semantic-damage cases. Numeric adjacency and upstream word-wrap
  ambiguity are accepted Stage 5 limitations: U+0020 prevents literal token
  concatenation while avoiding unsupported semantic punctuation, and repair
  would require parsing or heuristics outside this stage. The immutable v1 job
  `1759565` remains a scientifically unsuccessful first candidate attempt.

### D021 — Stage 5 defers address-format metadata

- **Scope:** Stage 5 DEVELOPMENT
- **Decision:** Do not use address-format metadata to label or reorder source
  lines. Stage 5 uses only their existing order.
- **Rationale:** Address lines 1–4 have no universal component meanings, and no
  evidence justifies a country-dependent semantic transformation at this stage.
- **Status:** LOCKED by the accepted Stage 5 DEVELOPMENT contract.

### D022 — Stage 6 deduplicates exact lowercase candidates globally

- **Scope:** Stage 6 DEVELOPMENT
- **Decision:** Use exact accepted Stage 5 lowercase reconstructed candidate
  equality as the sole early deduplication key. Apply one global namespace
  across STANDARD, NATIVE, all rows, and same-row representations. Derive a
  fixed 32-byte SHA-256 ID from the versioned Stage 6 domain plus exact UTF-8
  candidate bytes. Preserve every Stage 5 row and field; append nullable
  STANDARD/NATIVE mappings and publish a separate unique registry with exact
  total and representation occurrence counts. An unavailable representation
  creates no occurrence or registry row. Verify exact candidate bytes within
  every digest group and fail closed on a distinct-text collision.
- **Rationale:** Stage 4 deliberately established lowercase canonical text and
  Stage 5 reconstructed it without semantic interpretation. Exact global
  deduplication avoids 17,968 of 69,747 prospective Stage 7 parse calls on
  DEVELOPMENT while retaining complete occurrence provenance. Adding clean
  surface text would split 123 accepted canonical groups without protecting
  source information, because every clean form remains in the row map.
- **Status:** `STAGE_6_ACCEPTED` on DEVELOPMENT. Approved design commit
  `9f9a5a07a2dd3825c895b23406311651e5480324`, implementation
  `f39047cc825d9baef91915478f657aefecc86d4c`, reviewed candidate
  `03bab36bc2f45d218eb289abff0ad2aed72cffd8`, authoritative job `1759819`,
  and independent job `1760055` are bound as the accepted history. This Stage 6
  decision did not itself authorize production, HOLDOUT, or Stage 7; the later
  D023 authorization is separate and does not alter Stage 6.

### D023 — Stage 7 preserves the lowercase key and represents confirmed native crashes

- **Date:** 2026-08-28.
- **Scope:** Revised Stage 7 DEVELOPMENT design attempt only.
- **Decision:** The exact accepted Stage 6 lowercase candidate remains the
  parse-once key because all 123 multi-clean-surface groups and all 246 clean
  surfaces produced exact ordered parse equality. Every one of the 51,779
  Stage 6 candidate IDs must receive one Stage 7 row. After one native parser
  process exit, retry the same exact candidate once in a fresh frozen-bundle
  process. Two identical process-crash signatures may produce
  `PARSER_PROCESS_CRASH` with null components; `PARSED_EMPTY` remains a normal
  parse with `[]`. Crash→success or another technical signature aborts the
  publication. Never skip by size, truncate, parse a substring, synthesize a
  component, or alter/drop the Stage 6 candidate.
- **Rationale:** A parser result is derived information. A small, explicit,
  reproducible technical-failure state preserves total candidate lineage
  without misrepresenting failure as a valid empty parse or changing accepted
  Stage 6 science.
- **Status:** OWNER-APPROVED REVISED DESIGN ATTEMPT; TARGETED GATE DID NOT PASS.
  Job `1760182` proved the four motivating crashes disappear when the prior
  48 GiB address-space ceiling is removed. The proposed status was not frozen.
  This is not Stage 7 acceptance and does not authorize independent review,
  Stage 8, HOLDOUT, production, or geocoding.

### D024 — Stage 7 must not encode a fixable resource ceiling as parser failure

- **Date:** 2026-08-28.
- **Scope:** Targeted revised Stage 7 DEVELOPMENT design gate only.
- **Decision:** Do not freeze the proposed Stage 7 contract/profile after the
  revised diagnostic. The exact prior 48 GiB path reproduced 19 successful
  giants and four crashes, while the uncapped supervisor in a 180 GiB job
  parsed the same 23 exact candidates successfully on their first attempt.
  The four prior failures therefore do not justify published
  `PARSER_PROCESS_CRASH` rows. Preserve the lowercase parse-once decision, the
  exact candidates, the parser bundle, and both immutable not-ready evidence
  chains. Require a new owner decision on resource sufficiency and whether a
  prospective technical-failure state remains necessary before contract
  freeze.
- **Rationale:** A SAFE-imposed resource limit is not an intrinsic libpostal
  result. Encoding it as a candidate-level parser failure would make output
  depend on an avoidable execution configuration despite exact successful
  parsing being demonstrated locally on Goethe compute.
- **Status:** `STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY`. No authoritative Stage
  7 DEVELOPMENT run, independent review, Stage 8, HOLDOUT, production, or
  geocoding is authorized.

### D025 — Freeze Stage 7 v1 with resource-sufficient fail-closed supervision

- **Date:** 2026-08-28.
- **Scope:** Stage 7 DEVELOPMENT implementation and one authoritative run.
- **Decision:** Job `1760182` parsed all 23 giant candidates, including the
  25,920,495-code-point maximum, under 180 GiB with the prior 48 GiB ceiling
  removed. Freeze `stage07_libpostal_parsing_contract_v1` and
  `stage07_libpostal_parsing_profile_v1` with exact lowercase input,
  context-free pinned libpostal, one synchronous child, and one fresh exact
  retry after child death. Any unresolved crash or nondeterminism aborts the
  publication. Published statuses are only `PARSED_NONEMPTY` and
  `PARSED_EMPTY`; `PARSER_PROCESS_CRASH` is not in v1.
- **Rationale:** The earlier 4/23 crashes were resource-cap dependent, not an
  intrinsic parser limitation. The original not-ready evidence remains
  immutable and accepted Stage 6 science is unchanged.
- **Status:** OWNER-APPROVED CONTRACT FREEZE; Stage 7 DEVELOPMENT remains in
  progress and is not accepted. Independent review, Stage 8, HOLDOUT,
  production, and geocoding remain unauthorized.

### D026 — Stage 7 v1 is not ready after parser-quality diagnosis

- **Date:** 2026-08-30.
- **Scope:** Stage 7 DEVELOPMENT candidate only.
- **Decision:** Do not hand the current frozen context-free libpostal output to
  independent review or Stage 8 as a ready candidate. The 120-case
  risk-stratified qualitative review found 11 clear misparses, and targeted job
  `1760818` deterministically reproduced only those 11 plus seven questionable
  cases. Fourteen distinct cases have true libpostal label or boundary errors.
  All 11 clear cases are native, single-script candidates across five
  non-Latin strata; five are label-only errors and six contain within-word or
  token boundary failures. Although the exact Stage 6 candidate remains
  losslessly present, fixed Stage 8 label mapping can deterministically recover
  none of the clear cases without guessing.
- **Rationale:** Machine totality, exact map-back, and deterministic parsing are
  necessary but do not override systematic semantic/boundary failures in the
  parsing layer. Raw-input preservation allows a future conservative design;
  it does not make incorrect component boundaries safe for mapping.
- **Status:** `STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY`, with controlling
  conclusion `MIXED_ROOT_CAUSES_REQUIRING_TARGETED_STAGE07_DESIGN_CHANGE`.
  No remedy is selected or implemented by this decision. A new owner
  scientific decision is required.

### D027 — Test only effective provenance-grounded libpostal context options

- **Date:** 2026-08-30.
- **Scope:** Non-authoritative Stage 7 DEVELOPMENT design diagnostic only.
- **Decision:** Inspect the exact frozen libpostal/pypostal API first, then
  compare only effective parser context parameters backed by unanimous
  accepted occurrence metadata over the existing 120-case selection. Never
  infer context, alter candidate text, select a majority context, or change
  the Stage 6 key in this diagnostic. The pinned wrapper exposes optional
  `language` and `country`, but the pinned native parser explicitly forces
  both to `NULL` before parser-context construction. Consequently there is no
  effective variant to execute; run only the required metadata provenance and
  ambiguity audit and do not fabricate a comparison.
- **Rationale:** A wrapper signature is not evidence that the bound model uses
  an option. A scientifically meaningful comparison requires both an effective
  parser mechanism and trusted unambiguous context.
- **Status:** DIAGNOSTIC COMPLETE —
  `CONTEXT_AWARE_LIBPOSTAL_NOT_SUFFICIENT`. Metadata-only job `1761212`
  verified the exact API finding and audited all 51,779 candidate IDs without
  a parser call. Country provenance was unanimous and complete for 50,761,
  absent for 1,000, partial for four, and conflicting for 14; all 18 targeted
  qualitative cases had unanimous country context. There is no accepted
  explicit language field. The authoritative Stage 7 v1 output and
  `STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY` verdict remain unchanged.
  Independent review, Stage 8, HOLDOUT, production, geocoding, and merge remain
  unauthorized.

### D028 — Compare one pinned second offline parser on the existing 120 cases

- **Date:** 2026-08-30.
- **Scope:** Non-authoritative Stage 7 DEVELOPMENT design diagnostic only.
- **Decision:** After a public, non-protected eligibility screen, select
  DeepParse `0.10.0` with its BPEmb-attention model for one controlled
  comparison against the immutable libpostal results for the existing
  120-candidate qualitative selection. Freeze all public code, model,
  embedding, tokenizer, dependency, runtime, option, seed, device, and license
  identities before protected inference. Protected execution is offline on a
  Goethe compute node and receives the exact `stage06_candidate_lower` with no
  SAFE preprocessing. Preserve the parser's native ordered token labels and
  probabilities. Require exact repeats over all 18 clear/questionable targets
  before semantic comparison.
- **Rationale:** Context-aware libpostal is unavailable in the pinned bundle.
  DeepParse is the only screened mature project with a general multinational
  structured parser, a documented offline mode, and pinnable public model
  assets. Its official address data are libpostal-derived, its direct Han
  evidence is weak, and direct Lao/Thai/Hebrew address evidence is absent;
  these are controlling limitations to measure, not reasons to assume a win.
  Competing screened tools are country-specific, geocoder-query classifiers,
  coarse locale formatters, town/country extractors, or structured-form
  validators rather than applicable multilingual component parsers.
- **Status:** PUBLIC ELIGIBILITY GATE COMPLETE; protected bundle construction
  and the 120-case comparison remain pending. The authoritative Stage 7 v1
  registry and `STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY` verdict are unchanged.
  No Stage 7 redesign, independent review, Stage 8, HOLDOUT, production,
  geocoding, or merge is authorized.

### D029 — Make parser applicability country-aware and require a prelaunch gate

- **Date:** 2026-08-31.
- **Scope:** Stage 7 DEVELOPMENT stabilization and non-authoritative parser
  diagnostics only.
- **Decision:** Decide parser country eligibility before parsing from accepted
  `stage04_lower_country_iso_code` occurrence provenance. Never infer, vote,
  or select a country. Missing, partial, invalid, or conflicting provenance
  requires explicit abstention/ambiguity for a country-dependent parser.
  Bind the exact pinned libpostal bundle to its documented worldwide
  inhabited-country training scope without inventing a small quality-derived
  whitelist. Bind the exact DeepParse BPEmb-attention model conservatively to
  its 20 documented training countries; its 41 zero-shot evaluation countries
  are not eligible. Separate coverage, technical success, and reviewed
  semantic quality at source-row, occurrence, candidate, and review levels.
- **Engineering decision:** No new expensive or protected parser job may launch
  until a single fail-closed prelaunch gate verifies exact Git/path identity,
  country policy, complete runtime imports, native linkage, bundle/model hashes,
  offline public model initialization, compute-node smoke, permissions,
  resources, and network/privacy policy. Current public-only bundle job
  `1762078` is not cancelled or repeatedly polled and receives one status
  inspection only after the local audit.
- **Status:** OWNER-APPROVED STABILIZATION DESIGN. At the initial checkpoint,
  public bundle job `1762078` and metadata-only eligibility job `1762293` were
  both pending and had not started, so `STAGE07_PRELAUNCH_GATE_FAIL` correctly
  controlled. The existing jobs were later inspected without duplication:
  `1762293` completed and its 51,779-candidate/69,747-occurrence/120-selection
  aggregates independently reconcile; `1762078` failed pre-scientifically
  because its otherwise complete offline model cache wrote the exact revision
  plus a newline to Hugging Face `refs/main`. The minimal correction writes and
  verifies the exact 40-byte revision and verifies offline `main` resolution
  before model initialization. Corrected public-only job `1762652` validated
  that cache binding, all pinned hashes, and offline initialization with zero
  network attempts, then failed before publication because leading-`--`
  configure values were passed to `argparse` as separate value tokens.
  Corrected public-only job `1762661` then passed the exact-argv gate and
  published the fully pinned offline bundle. Public compute smoke `1762663`
  failed two seconds after starting because its launcher omitted the required
  `SAFE_EXECUTION_SITE=goethe-nhr` marker; the execution guard stopped it before
  bundle validation, model initialization, linkage, or synthetic parsing. The
  submission preflight had not asserted that marker. At that checkpoint no
  replacement smoke had been submitted. The engineering result remained
  `STAGE07_PRELAUNCH_GATE_FAIL`.
  The authoritative Stage 7 registry is unchanged and the scientific verdict
  remains `STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY`. No independent review,
  Stage 8, HOLDOUT, production, geocoding, or merge is authorized.

### D030 — Permit one final physically read-only DeepParse bundle architecture

- **Date:** 2026-09-01.
- **Scope:** Public-only Stage 7 DeepParse infrastructure stabilization; no
  protected parser inference.
- **Finding:** Job `1762661` published a valid bundle, but a later login-side
  Hugging Face offline cache-resolution preflight invoked its still-writable
  Python runtime without bytecode suppression. Before either compute smoke,
  ordinary import caching added 363 `.pyc` files in 39 `__pycache__`
  directories. The root cause is
  `POST_PUBLICATION_LOGIN_SIDE_PYTHON_IMPORT_MUTATED_WRITABLE_BUNDLE`. DeepParse
  inference, Torch/model initialization, and smoke jobs `1762663`/`1762669`
  did not create the contamination.
- **Decision:** Do not repair or reuse that tree. Authorize exactly one fresh
  public-only build using manifest v2 and physically enforced post-publication
  modes: directories and executables `0555`, ordinary files `0444`, zero
  writable paths, zero bytecode/cache artifacts, and no symlinks. Every mutable
  Python, Hugging Face, Transformers, Torch, XDG, HOME, and temporary path is
  bound to a fresh owner-only external runtime-state root. Post-publication
  Python uses `-B` and `PYTHONDONTWRITEBYTECODE=1`. A full tree identity binds
  relative path, type, mode, size, content hash, directories, and symlink
  policy; pre/post runtime identities and all mutation-category counts must be
  exactly equal/zero. V2 also rejects external hard links, recursively fsyncs
  the payload, requires target-filesystem no-replace atomic publication, binds
  every required public model/source/license path and hash, and installs the
  exact 79-package runtime using a SHA-256 acquisition lock with
  `pip --require-hashes`.
- **Stop rule:** Only after local behavioral permission/import/cache-resolution
  tests and every PRELAUNCH V2 gate pass may one fresh public bundle build be
  submitted. If the architecture or its one subsequent public compute smoke
  fails substantively, stop the DeepParse infrastructure path rather than
  enter another patch/resubmit cycle.
- **Status:** OWNER-APPROVED FINAL INFRASTRUCTURE ARCHITECTURE. Engineering
  remains `STAGE07_PRELAUNCH_GATE_FAIL` until execution evidence passes;
  scientific status remains `STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY`. No
  protected inference, independent review, Stage 8, HOLDOUT, production,
  geocoding, or merge is authorized.

### D031 — Stop the DeepParse infrastructure path at the final V2 prelaunch gate

- **Date:** 2026-09-01.
- **Scope:** Outcome of the owner-approved D030 public-only infrastructure
  attempt; no parser inference.
- **Evidence:** All local V2 behavioral/static gates passed and exact pushed SHA
  `1b6aa0c204a9e4369969b603f358763fcedec71c` was opened as a clean detached
  controlled Goethe worktree. Before scheduling, the exact publication-parent
  probe established that PanFS returns `EINVAL` (errno 22) for same-parent Linux
  `renameat2(RENAME_NOREPLACE)`. The probe cleaned its temporary tree. No fresh
  build/output path was created, no SLURM job was submitted, and no protected
  input was opened.
- **Decision:** Apply D030's hard stop. Do not weaken fail-closed no-replace
  publication semantics and do not enter another bundle/smoke redesign cycle.
  The engineering conclusion is
  `DEEPPARSE_INFRASTRUCTURE_PATH_NOT_JUSTIFIED`. A future Stage 7 scientific
  decision should instead consider libpostal within its eligible country scope,
  an explicit semantic-readiness policy, and conservative abstention while
  preserving exact Stage 6 candidates and immutable raw Stage 7 evidence.
- **Status:** `STAGE07_PRELAUNCH_GATE_FAIL` and
  `STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY`. No protected DeepParse inference,
  independent review, Stage 8, HOLDOUT, production, geocoding, merge, further
  bundle build, or compute smoke is authorized.

### D032 — Treat parser output as evidence and validate a structural abstention layer

- **Date:** 2026-09-01.
- **Scope:** Stage 7 v2 DEVELOPMENT design and proposed unstarted post-Stage-7
  architecture only.
- **Decision:** Keep Stage 7 v1 immutable and close DeepParse. Design a new v2
  that separates trusted-country applicability, technical execution, and
  component readiness. Preserve exact Stage 6 candidates and exact ordered raw
  libpostal output. Rule `stage07_component_readiness_rule_v1` abstains on
  empty parses, unresolved applicability, lexical/numeric stream anomalies,
  failed ordered alignment, token-internal boundaries/fragments, excessive
  within-run fragmentation, and adjacent repeated labels at internal
  boundaries. `COMPONENTS_READY` means structurally usable parser evidence, not
  semantic or geographic truth; `COMPONENTS_ABSTAIN` never drops or invalidates
  the address.
- **Evidence:** Optimized bounded job `1763358` at
  `372aad37370144d6ca85d05c56302a0af2cad4b3` used only the already-authorized
  120 semantic cases and fixed-500 metadata elsewhere. It completed in 84
  seconds without scanning the 51,779-row nested registry. The rule abstained
  on 10/11 clear misparses, including all 6/6 known boundary failures, but one
  label-only failure remained ready. Semantic label errors with regular
  structure are not reliably detectable from Stage 7-local evidence.
- **Validation decision:** The fixed 500-row selection predates the readiness
  hypothesis. Its candidate projection contains 613 IDs, overlaps the existing
  120 by nine and the targeted 18 by zero, leaving 604 untouched. It is the
  immutable validation frame, not an already-stratified review sample. A
  separately authorized machine-only rule application must freeze a 240-case
  balanced ready/abstain selection before any new semantic review.
- **Future architecture:** Propose compact Stages 8–14: lossless evidence
  projection, offline reference evidence, multiple hypotheses, global query
  identity/QA, self-hosted Pelias top-N retrieval, deterministic evidence
  scoring/convergence, and final granularity/abstention. The old Stages 8–19
  were never started and are proposed for replacement; their scientific
  safeguards remain. The current no-geocoding gate remains controlling until
  the redesign is separately approved and execution policy is deliberately
  reconciled.
- **Status:** `STAGE07_V2_READINESS_DESIGN_READY_FOR_FRESH_DEVELOPMENT_VALIDATION`
  and `STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY`. This does not authorize the
  604-candidate machine pass, 240-case semantic review, independent Stage 7
  review, Stage 8, HOLDOUT, production, geocoding, or merge.

### D033 — Freeze the Stage 7 v2 machine-only validation selection contract

- **Date:** 2026-09-01.
- **Scope:** One bounded Stage 7 DEVELOPMENT machine-only rule application;
  no semantic review.
- **Decision:** Apply unchanged rule `stage07_component_readiness_rule_v1` to
  the 604 semantically untouched candidates in the immutable fixed-500 frame
  and freeze exactly 240 predicted cases under
  `stage07_component_readiness_validation_selection_v1`. Bind the rule source
  SHA-256, select separate ready/abstain arms with deterministic short-arm
  transfer, balance reason/script/representation/country-frequency evidence,
  and break all ties using domain-separated SHA-256 over candidate IDs. Text
  and parser values may drive only the already-frozen readiness signals; they
  never enter selection rank. Unresolved applicability is decided without
  reading candidate/component values.
- **Rationale:** Predictions, reasons, IDs, thresholds, and the sample identity
  must be immutable before fresh semantic labels exist. This prevents tuning
  or sample selection in response to review outcomes while retaining the
  fixed-500 frame's pre-hypothesis independence.
- **Execution evidence:** Job `1763433` at exact SHA
  `20a46610b885919b5bad113f2b5763e98bf23ca5` completed the machine-only pass
  in 28 seconds. Across 604 candidates the frozen rule produced 330
  `COMPONENTS_READY`, 122 `COMPONENTS_ABSTAIN`, and 152 `NOT_ASSESSED`, then
  froze exactly 120 READY and 120 ABSTAIN cases. The selection fingerprint is
  `c05cecf2aa9099045adc0d5c698c7e82a6bae187ae82222817f4bfb5264c2a89`.
  No semantic inspection, parser call, network call, HOLDOUT, production, or
  Stage 8 access occurred.
- **Status:** MACHINE-ONLY SELECTION FROZEN. Qualitative inspection of the
  protected 240 remains separately unauthorized. Stage 7 is still
  `STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY`; independent review, Stage 8,
  HOLDOUT, production, geocoding, and merge remain unauthorized.

### D034 — Reject the frozen Stage 7 v2 readiness rule after fresh validation

- **Date:** 2026-09-01.
- **Scope:** Fresh Stage 7 v2 DEVELOPMENT validation of exactly the frozen
  240-candidate selection; no rule tuning or further stage execution.
- **Decision:** Do not publish `stage07_component_readiness_rule_v1` as the
  Stage 7 v2 component-consumption gate. The owner-authorized Codex semantic
  review was prediction-blinded until all 240 classifications were frozen.
  Selection fingerprint, membership, 120 READY/120 ABSTAIN predictions, reason
  codes, metrics, and thresholds remained unchanged.
- **Evidence:** Among 100 assessable READY cases, 85 were plausible/usable and
  10 were `CLEAR_MISPARSE`. READY precision was 85.000% versus the predeclared
  95.000% minimum; clear-misparse leakage was 10.000% and 10 cases versus the
  2.500% and two-case maxima. The rule abstained on 63/148 usable parses
  (42.568%) versus the 40.000% maximum. Eligible-frame abstention coverage was
  non-vacuous at 122/452 (26.991%), and structural-reason replay remained
  exact, but those passes do not override the three quality-gate failures.
- **Rationale:** Structural warnings detect many dangerous outputs but do not
  protect READY with sufficient precision and also discard too many usable
  component streams under the frozen decision rule. The balanced selection is
  validation evidence, not a population-wide libpostal accuracy estimate.
  Tuning on these fresh labels is prohibited.
- **Status:** `STAGE07_V2_FRESH_DEVELOPMENT_VALIDATION_FAIL` and
  `STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY`. Preserve v1 raw evidence and the
  protected validation artifacts. A new owner scientific decision is required
  before any replacement Stage 7 design. Independent review, Stage 8, HOLDOUT,
  production, geocoding, and merge remain unauthorized.

## Open decisions

These questions require future stage designs and explicit approval:

- a new owner scientific decision after the failed Stage 7 v2 validation;
- approval or revision of the proposed compact Stages 8–14;
- exact offline reference releases/licenses and blocking semantics;
- the bounded Stage 10 hypothesis/query ladder;
- Stage 13 scoring/calibration and contradiction policy; and
- Stage 14 granularity-specific usability thresholds, including treatment of
  interpolated Pelias address results.

Nothing in this register authorizes HOLDOUT, Stage 7 acceptance or independent
review, Stage 8, geocoding, or production Stage 2 through Stage 7. Stage 7
decisions D023–D034 authorize only their stated DEVELOPMENT scopes.
