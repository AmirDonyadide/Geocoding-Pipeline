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
- **Status:** LOCKED sequence. Stages 5–7 are accepted on DEVELOPMENT. Stage 7
  acceptance is evidence-only under D037 and does not promote parser output to
  semantic or geographic truth.

### D010 — Abbreviation normalization is component-aware and post-parsing

- **Scope:** Stage 9
- **Decision:** Abbreviation/linguistic normalization occurs after parsing and
  component mapping, using component/country/language/script context. Blind
  English rules on native candidates are prohibited.
- **Rationale:** Prevent semantic damage across address components and scripts.
- **Status:** LOCKED scientific principle. The old Stage 9 number was never
  implemented; D038 prospectively places any such derived value under the
  Stage 10 hypothesis boundary rather than Stage 8 or Stage 9.

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
  Stages 0–7. D038 freezes the prospective Stage 8 tool boundary without
  pycountry or libaddressinput. Proposed replacement Stages 9–14 are not
  started. pgeocode is proof-of-concept only. Pandas is inspection-only.

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

### D035 — Redefine Stage 7 v2 as an evidence-only projection

- **Date:** 2026-09-01.
- **Scope:** Stage 7 DEVELOPMENT design, implementation, and one prospective
  projection/validation from immutable Stage 6, Stage 7 v1, and eligibility
  evidence; no parser calls or semantic review.
- **Decision:** Freeze `stage07_parser_evidence_contract_v2` and
  `stage07_parser_evidence_profile_v2`. Stage 7 guarantees exact source and raw
  parser-evidence preservation, parser/applicability/technical provenance,
  deterministic structural warnings, and full map-back. It does not guarantee
  semantic labels, component boundaries, postal validity, geographic truth, or
  semantic correctness when no structural warning fires.
- **Readiness disposition:** Retire `COMPONENTS_READY` and
  `COMPONENTS_ABSTAIN` as a downstream semantic-trust gate. Preserve the failed
  `stage07_component_readiness_rule_v1` and its fresh validation immutably.
  Reuse only its deterministic structural signals under
  `stage07_structural_warning_features_v1`; publish no readiness field or
  semantic-trust assertion.
- **Historical execution:** v2 makes zero parser calls. It copies the exact v1
  `PARSED_NONEMPTY`/`PARSED_EMPTY` status and ordered raw component stream and
  records origin `REUSED_IMMUTABLE_STAGE07_V1`. Country applicability remains
  a separate field. Country-unresolved rows retain historical raw evidence but
  receive `STRUCTURAL_WARNINGS_NOT_EVALUATED`.
- **Downstream meaning:** Future Stage 8 may consume raw libpostal labels only
  as hypotheses/evidence and must retain exact whole-string STANDARD/NATIVE
  candidates in parallel. No-warning is not trust.
- **Execution evidence:** Goethe-NHR job `1763516` at exact pushed SHA
  `e684d84a8d68498ea790542143c8e125b3eb87b5` completed the bounded projection
  and independent reopen validation in 5 minutes 19 seconds. It reconciled
  51,779 → 51,779 candidates and all 69,747 occurrences, preserved every Stage
  6 field and raw v1 status/component stream, replayed warnings exactly, and
  made zero parser calls and zero semantic-trust claims. Manifest SHA-256 is
  `f58410877a7810562df7985c7316de7546d4dd8e11a647fd659c53a272e9c266`.
- **Status:**
  `STAGE07_EVIDENCE_ONLY_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW`.
  This is not Stage 7 acceptance. Independent review, Stage 8, HOLDOUT,
  production, geocoding, and merge remain unauthorized.

### D036 — Correct the evidence-only candidate's review-documentation conflicts

- **Date:** 2026-09-01.
- **Scope:** Documentation-only Stage 7 DEVELOPMENT remediation after the first
  independent review; no science, implementation, or protected artifact change.
- **Finding:** Independent review of candidate
  `318b70b00a52376b1b4fe865f41a789e2dd3feb9`, recorded at review evidence
  `6ea2ba2cef1a63f91a5a831755d8ecb0cd7d179f`, found that the detailed proposed
  Stage 8 architecture still depended on the rejected `COMPONENTS_READY` gate
  and that several current-facing status/report surfaces still presented older
  not-ready states as current. Implementation and static checks passed.
- **Decision:** Remove readiness-based semantic consumption from every current
  downstream contract. Raw libpostal components are always hypotheses/evidence;
  structural warnings and their absence never establish semantic trust. Keep
  all failed-readiness classifications and reports immutable as explicitly
  historical evidence. Reconcile current status surfaces without altering Stage
  6, Stage 7 v1, the evidence-only contract/profile, job `1763516`, or its
  protected output.
- **Status:**
  `STAGE07_EVIDENCE_ONLY_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REREVIEW`.
  At that decision point this was not Stage 7 acceptance and did not authorize
  Stage 8, HOLDOUT, production, geocoding, or merge. D037 records the later
  independent rereview and final owner acceptance.

### D037 — Accept the exact Stage 7 evidence-only DEVELOPMENT candidate

- **Date:** 2026-09-01.
- **Scope:** Final owner acceptance and main integration of Stage 7
  DEVELOPMENT evidence only; no scientific rerun or later-stage authorization.
- **Decision:** Accept exact reviewed candidate
  `656a16d3d1f33cb152ace557c26f42df047bc7d6` as `STAGE_7_ACCEPTED` on
  DEVELOPMENT. Preserve its ancestry through merge commit
  `b36b995809fe902fe80af25856cb24786b795b1c`. Retain only the two sanitized
  rereview report blobs from evidence commit
  `356de44f3e86e37972d60cac45d01703ad1f6856`; do not merge the independent-
  review harness branch or implementation.
- **Independent evidence:** Rereview verdict
  `STAGE07_EVIDENCE_ONLY_INDEPENDENT_REREVIEW_PASS`, Goethe job `1763656`
  (`COMPLETED 0:0`, elapsed `00:03:49`, MaxRSS about 2.02 GiB), review harness
  SHA `a2fa6e99e75336155363dc1f566b34cf3da8e0a8`, and controlled aggregate
  SHA-256
  `c0955062e5f407fdf8586f1811992a8a2e26e202295f467f41b5994b59bbc3b6`.
- **Accepted meaning:** Exact parser evidence is reproducibly preserved;
  applicability, technical status, provenance, deterministic warnings, and
  complete map-back are accepted. Libpostal labels, values, and boundaries
  remain evidence/hypotheses only. Stage 7 guarantees neither semantic
  component correctness nor geographic truth, and absence of a structural
  warning provides no trust guarantee.
- **Historical preservation:** The original v1 semantic-quality findings,
  DeepParse closure, failed `COMPONENTS_READY`/`COMPONENTS_ABSTAIN` validation,
  first independent-review documentation failure, and successful corrected
  rereview remain distinct, correctly classified evidence. Acceptance does not
  relabel any failure or experiment as success.
- **Status:** `STAGE_7_ACCEPTED` on DEVELOPMENT. Production Stage 7, HOLDOUT,
  Stage 8, Senzing, geocoding, and every later scientific workload remain not
  started and unauthorized. The exact next task is Stage 8 design and explicit
  authorization only.

### D038 — Freeze Stage 8 as a lossless parser-evidence projection and index

- **Date:** 2026-09-01.
- **Scope:** Prospective Stage 8 DEVELOPMENT scientific contract only; no
  implementation or execution.
- **Decision:** Stage 8 is not semantic normalization or hypothesis generation.
  It preserves the complete accepted Stage 7 v2 candidate row, publishes a
  reversible ordered long-form parser-component evidence index, and preserves
  a minimal exact source-row map with separate STANDARD/NATIVE candidate links.
  Candidate-level representation scope may be `STANDARD`, `NATIVE`, or `BOTH`;
  occurrence-level provenance remains STANDARD or NATIVE. Missing
  representations remain explicit.
- **Evidence taxonomy:** Every field is classified as `SOURCE_VALUE`,
  `SOURCE_LINEAGE`, `UPSTREAM_DERIVED_REPRESENTATION`,
  `TRUSTED_SOURCE_CONTEXT`, `PARSER_TECHNICAL_PROVENANCE`, `PARSER_EVIDENCE`,
  `STRUCTURAL_DIAGNOSTIC`, or `MECHANICAL_INDEX`. Stage 8 publishes no
  `HYPOTHESIS`, `REFERENCE_EVIDENCE`, `GEOCODER_RESULT`, or `ACCEPTED_MATCH`
  field and no confidence/correctness score.
- **Mapping:** `stage08_libpostal_label_mapping_v1` maps the 20 exact labels
  defined by the pinned libpostal source one-to-one to visibly parser-scoped
  SAFE evidence names. It never changes values, order, or duplicates. Any
  other label is retained exactly with `UNMAPPED_LABEL` and a null mapped
  concept. `house` is not narrowed to `building`; `city` is not narrowed to
  `locality`; parser `country` is not trusted country.
- **Status semantics:** Applicability, historical technical status, execution
  origin, structural warnings, warning non-evaluation, mapping coverage, and
  source-representation presence remain separate. Accepted Stage 7 did
  historically parse country-unresolved candidates, so Stage 8 does not call
  them unattempted. A future not-attempted state requires a new contract and
  cannot equal `PARSED_EMPTY`. Empty parses, unknown labels, warnings,
  unresolved country, and absent representations never mean invalid address.
- **Metadata boundary:** Stage 8 introduces no pycountry, libaddressinput,
  public-reference, or external-service dependency. Exact-code ISO/subdivision
  and pinned offline country-format metadata may be considered as Stage 9
  reference/format evidence. Fuzzy pycountry inference, runtime Address Data
  Service calls, and Google Address Validation API are not approved.
- **Implementation boundary:** Prospective identities are
  `stage08_address_evidence_projection_contract_v1`,
  `stage08_address_evidence_projection_profile_v1`,
  `stage08_address_evidence_projection_schema_v1`, and
  `stage08_semantic_classification_v1`. PyArrow/Parquet own typed nested and
  long evidence; DuckDB performs bounded external reconciliation. Polars is
  not required in v1 and pandas remains prohibited for production
  transformations. Giant candidates are processed exactly or publication
  fails.
- **Architecture correction:** Keep compact Stage 8–14 numbering. Stage 8 is
  lossless projection/index, Stage 9 is independent reference/format evidence,
  and Stage 10 is the first hypothesis stage. This prospectively supersedes
  the unimplemented stage-number placement in D010/D014 without rewriting
  their scientific safeguards or historical context.
- **Status:**
  `STAGE08_ADDRESS_EVIDENCE_DESIGN_READY_FOR_IMPLEMENTATION`. Stage 8 is not
  implemented, executed, independently reviewed, or accepted. No DEVELOPMENT
  job, production, HOLDOUT, Stage 9, Pelias, geocoding, Senzing, or DeepParse
  work is authorized. The exact next task is a fresh Stage 8 DEVELOPMENT
  implementation session after explicit authorization.

### D039 — Freeze the Stage 8 DEVELOPMENT implementation candidate

- **Date:** 2026-09-01.
- **Scope:** Stage 8 DEVELOPMENT implementation and synthetic/local validation
  only; no protected execution.
- **Decision:** Implement D038 unchanged at exact Git commit
  `a2544401b4b699f6c020970f3507a2ae432746c5`. The candidate freezes contract
  fingerprint `8b3c530e714177fe2c30a97d61dcc199b7f9efba58f3c17a291b817af0f24d5e`,
  schema-bundle fingerprint
  `6c8ebecd24c495dbe2ce32125ac1cb89c4a9de4905c786b774d10ad728ed392f`,
  and label-mapping fingerprint
  `b18167d2d5c1f1402d1bb0e92559befb92418f5f4f34df885596778a11d5c09d`.
  It uses PyArrow/Parquet for authoritative storage and bounded nested
  projection, DuckDB for bounded reconciliation, atomic owner-only
  publication, and an independent reopen validator.
- **Evidence:** Required synthetic cases, Stage 7 regressions, Ruff, strict
  mypy, shell syntax, JSON, Markdown-link, diff, and privacy gates pass. The
  only safe full-suite local failures are unchanged Python 3.14.3 guards under
  the Mac's Python 3.14.7. No protected inputs, SLURM, parser, reference,
  geocoder, HOLDOUT, or production access occurred.
- **Status:**
  `STAGE08_ADDRESS_EVIDENCE_IMPLEMENTATION_READY_FOR_CONTROLLED_DEVELOPMENT_EXECUTION`.
  This is not execution authority or scientific acceptance. The exact next
  action is separate owner authorization for one bounded Goethe-NHR
  DEVELOPMENT materialization; a pending run must not be duplicated.

### D040 — Freeze the Stage 8 DEVELOPMENT materialization candidate

- **Date:** 2026-09-02.
- **Scope:** Stage 8 DEVELOPMENT execution evidence and candidate freeze only;
  no independent review or acceptance.
- **Decision:** Reuse the single immutable job `1763747` artifact produced by
  executable commit `a2544401b4b699f6c020970f3507a2ae432746c5`. Bind manifest
  SHA-256 `bdf86738fb071e38b2ad090f4627a821149352fb1490e62b76e5819aa915bcf9`
  and logical dataset SHA-256
  `9c9d431c2c1b92712e0cb372f2661ad48f4fe8758dc0327d25aef90ab2c2d526`.
  No second materialization is justified or authorized.
- **Reconciliation:** The immutable candidate contains 51,779 candidates,
  6,106,088 ordered component rows, 35,000 source rows, and 69,747 occurrence
  mappings (34,822 STANDARD; 34,925 NATIVE). It preserves 51,774
  `PARSED_NONEMPTY` and five `PARSED_EMPTY` states. All components use the
  frozen mapping in this input; unmapped, dangling, component-count-mismatch,
  and occurrence-count-mismatch totals are zero. Reversibility and every frozen
  validation field passed.
- **Scheduler accounting:** The launcher and `ReqCPUS` requested four CPUs;
  `AllocCPUS` records 80 because `general1` is
  `OverSubscribe=EXCLUSIVE` and the assigned node has 80 CPUs. Stage 8 remained
  one task with `--cpus-per-task=4`; DuckDB remained at four threads and an 8GB
  cap. Batch `TotalCPU` was 948.969 seconds over 918 seconds elapsed, about
  1.034 used core-equivalents on average. The whole-node allocation/accounting
  difference is operational, not 80-way application concurrency, and is not
  material to scientific validity or boundedness.
- **Privacy and semantics:** Parser, reference, network, and geocoder calls are
  zero; semantic-trust fields are zero; HOLDOUT and production access are
  false. Atomic publication, prepublication reopen validation, owner-only
  permissions, and exact accepted Stage 6/7 bindings passed. Parser evidence
  remains evidence rather than truth.
- **Status:**
  `STAGE08_ADDRESS_EVIDENCE_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW`.
  The next action is a fresh independent Stage 8 critical-review session. This
  decision does not accept Stage 8 or authorize another job, Stage 9, HOLDOUT,
  production, reference services, or geocoding.

### D041 — Reject the first Stage 8 candidate and repair terminal publication

- **Date:** 2026-09-02.
- **Scope:** Bounded Stage 8 DEVELOPMENT remediation after independent review;
  code, synthetic tests, and current-facing documentation only. No protected
  execution or scientific redesign.
- **Independent finding:** Exact reporting candidate
  `adde81d2237e99993222994ce56efb0d74f7c2d3` at executable
  `a2544401b4b699f6c020970f3507a2ae432746c5` received
  `STAGE08_ADDRESS_EVIDENCE_INDEPENDENT_REVIEW_FAIL`. First, it created
  `_SUCCESS.json` and removed `_IN_PROGRESS` before required prepublication
  reopen validation, so an injected validation failure could leave a failed
  attempt represented as successful. Second, the current technology table in
  `docs/PROJECT_BRIEF.md` incorrectly assigned pycountry and offline
  libaddressinput metadata to Stage 8 instead of Stage 9.
- **Decision:** Reject the candidate; do not merge or accept it. Repair only
  terminal publication at exact executable
  `bd89a032eb6fcf16a7515e0bd2991165d87246b1`. `_IN_PROGRESS` now remains
  present through materialization, artifact/manifest fsync, and the complete
  prospective scientific/integrity reopen validation. `_SUCCESS.json` is
  created only after that validation passes. Marker removal, terminal-directory
  fsync, atomic rename, parent-directory fsync, and immediate post-publication
  reopen failures all demote the retained tree to explicit incomplete state
  with no success marker. The standalone published validator remains
  non-mutating and rejects later corruption/tampering.
- **Scientific preservation:** The contract/profile, four schemas, semantic
  taxonomy, exact 20-label mapping, input bindings, field meanings, status
  vocabularies, ordering, nullability, and candidate/component/source/occurrence
  grains are unchanged. Stage 8 remains lossless projection/index only; Stage
  9 is the potential offline reference/format-evidence boundary for pycountry
  and libaddressinput where scientifically justified.
- **Historical evidence:** Job `1763747` and its immutable artifact remain
  scientifically reconciled DEVELOPMENT evidence for the old executable. They
  are not relabeled scientifically invalid, modified, deleted, accepted, or
  eligible to validate the repaired executable. The failed review and both
  exact blocking findings remain distinct history.
- **Local evidence:** Stage 8 focused tests pass 17/17, including injected
  prepublication validation, prospective marker, artifact/manifest corruption,
  marker removal, fsync, rename, parent-fsync, and post-publication tamper
  boundaries. Unaffected Stage 2/7/8 and earlier publication regressions pass
  60/60. The safe full suite has 584 passes, 24 expected exact Python 3.14.3
  guard failures under local Python 3.14.7, and four deselections. Ruff,
  changed-file format, strict mypy, shell syntax, JSON, Markdown links, diff,
  and privacy/tracked-data gates pass; no runtime guard was weakened.
- **Status:**
  `STAGE08_ADDRESS_EVIDENCE_IMPLEMENTATION_READY_FOR_CONTROLLED_DEVELOPMENT_REEXECUTION`.
  This is not a new materialized candidate and does not authorize execution or
  independent review. The exact next action requiring separate owner
  authorization is: **AUTHORIZE ONE NEW CONTROLLED STAGE 8 DEVELOPMENT
  MATERIALIZATION AT THE NEW EXECUTABLE SHA.**

### D042 — Freeze the repaired Stage 8 DEVELOPMENT materialization candidate

- **Date:** 2026-09-02.
- **Scope:** Sanitized repaired Stage 8 DEVELOPMENT execution reconciliation
  and candidate freeze only; no implementation/science change, second job,
  independent rereview, or acceptance.
- **Decision:** Designate the single authorized repaired job `1763984` artifact
  as the authoritative Stage 8 DEVELOPMENT candidate. Bind exact executable
  `bd89a032eb6fcf16a7515e0bd2991165d87246b1`, output
  `/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage08/development/stage08_development_20260902T080150Z_bd89a032eb6f`,
  manifest SHA-256
  `d521240b42a40b9c1408f0f7241583bc76b7779e4107179e73fdcb7c7a69e119`,
  and logical dataset SHA-256
  `9c9d431c2c1b92712e0cb372f2661ad48f4fe8758dc0327d25aef90ab2c2d526`.
  Accepted Stage 7/6 manifests remain exact `f5841087…`/`e1da7b8e…`; runtime
  remains Python 3.14.3, PyArrow 25.0.0, and DuckDB 1.5.5.
- **Reconciliation:** The repaired candidate contains 51,779 candidates,
  6,106,088 ordered parser-component rows, 35,000 source rows, and 69,747
  representation occurrences (34,822 STANDARD; 34,925 NATIVE). It preserves
  51,774 `PARSED_NONEMPTY` and five `PARSED_EMPTY` states. All 6,106,088
  components use the frozen mapping in this input; unmapped, dangling,
  component-count-mismatch, and occurrence-count-mismatch totals are zero.
  Every frozen scientific/integrity validator and reversibility check passed.
- **Publication evidence:** Prepublication reopen validation completed while
  `_IN_PROGRESS` remained present and `_SUCCESS.json` remained absent. The
  final success marker binds the manifest above; `_IN_PROGRESS` is absent only
  after successful terminal transition; no incomplete sibling remains; and
  post-publication reopen validation passed. All eight directories are `0700`,
  all 52 files are `0600`, no symlinks exist, atomic/owner-only publication
  claims pass, and stderr is empty.
- **Scientific equality to rejected history:** Repaired job `1763984` has the
  same logical dataset SHA-256 as historical job `1763747`. This is evidence
  that the publication-state repair did not alter the frozen Stage 8 scientific
  dataset. It does not make old job `1763747` validation of the repaired
  executable.
- **Historical preservation:** Rejected reporting candidate `adde81d…`, old
  executable `a2544401…`, job `1763747`, its immutable artifact, the independent
  review failure, and its publication/documentation blockers remain distinct
  historical evidence. They are neither overwritten nor relabeled accepted.
- **Privacy and boundary:** Parser, reference, network, geocoder, and
  semantic-trust calls/fields are zero; HOLDOUT and production access are
  false. No second Stage 8 job, Stage 9 work, or geocoding is authorized.
- **Status:**
  `STAGE08_ADDRESS_EVIDENCE_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REREVIEW`.
  This is not Stage 8 acceptance. The exact next action is **FRESH INDEPENDENT
  STAGE 8 REREVIEW OF THIS REPAIRED CANDIDATE.**

### D043 — Reject the first repair after rereview and reconcile ambiguous rename

- **Date:** 2026-09-02.
- **Scope:** Second bounded Stage 8 DEVELOPMENT publication remediation after
  independent rereview; code, synthetic tests, and current-facing sanitized
  documentation only. No protected execution or scientific redesign.
- **Independent finding:** Exact reporting candidate
  `fdf2f8c78781a6bdb5dad637af5954ae81cf331d` at executable
  `bd89a032eb6fcf16a7515e0bd2991165d87246b1` received
  `STAGE08_ADDRESS_EVIDENCE_INDEPENDENT_REREVIEW_FAIL`. A rename wrapper could
  perform the real final rename and then raise before Python-side state was
  updated. Cleanup then examined only the vanished temporary path and returned
  failure while the final path still had `_SUCCESS.json`, lacked
  `_IN_PROGRESS`, and satisfied the repository's success definition.
- **Decision:** Reject the candidate; do not merge or accept it. Adopt
  completed publication only for the narrowly proven ambiguous-rename case.
  Executable `bdea7232a3f92ebd381be87610b753b8e4c35481` captures the temporary
  directory device/inode identity before commit and classifies all four
  temporary/final presence combinations without following symlinks. A
  final-only path may be adopted only when it has that exact identity, its
  parent fsync succeeds, and the complete final bundle independently reopens
  and validates. Before-effect failures and all other owned failure trees are
  demoted to success absent and `_IN_PROGRESS` present. Both-path,
  neither-path, wrong-identity, symlink, parent-fsync, and postpublication
  validation failures are never adopted; unrelated paths are not modified.
- **Terminal semantics:** The filesystem, rather than a Python path variable,
  is authoritative after an ambiguous rename result. Success is returned only
  after the final publication independently validates. Failure cleanup is
  identity-guarded and idempotent, inspects both paths, and cannot relabel or
  corrupt an unrelated publication. This closes pre-effect, post-effect,
  immediate-interrupt, parent-fsync, postpublication-validation, and partial
  cleanup boundaries without adding a third reader-visible terminal state.
- **Scientific preservation:** Stage 8 contracts, four schemas, semantic
  classes, exact 20-label mapping, Stage 6/7 bindings, candidate/component/
  source/occurrence grains, occurrence/parser-evidence semantics, and the
  Stage 8/9 scientific boundary are unchanged. Contract, schema-bundle,
  mapping, and individual schema fingerprints exactly match `bd89a032…`.
  Pycountry and libaddressinput remain potential Stage 9 evidence only.
- **Historical evidence:** Original executable `a2544401…`, job `1763747`,
  the first independent-review failure, first repair `bd89a032…`, job
  `1763984`, its successful scientific reconciliation, and the second
  independent-rereview failure remain truthful immutable history. Neither job
  nor artifact is called corrupt; each is evidence only for its exact
  executable and cannot validate `bdea7232…`.
- **Local evidence:** Stage 8 focused tests pass 28/28, including actual rename
  then raise, immediate post-rename interrupt, parent-fsync failure,
  postpublication reopen failure, every temporary/final presence state,
  partial/idempotent demotion, unrelated-path preservation, and normal
  publication. Relevant Stage 7 tests pass 54/54 and the runnable Stage 2
  atomic-publication regression passes. The safe full suite has 595 passes,
  24 expected exact Python 3.14.3 guard failures under local Python 3.14.7,
  and four deselections. Ruff, changed-file format, strict source/Stage 8
  mypy, shell syntax, JSON, Markdown links, diff, and privacy/tracked-data
  gates pass; no runtime guard was weakened.
- **Status:**
  `STAGE08_ADDRESS_EVIDENCE_IMPLEMENTATION_READY_FOR_CONTROLLED_DEVELOPMENT_REEXECUTION`.
  This is not a materialized candidate and does not authorize execution,
  independent review, Stage 9, HOLDOUT, production, reference work, or
  geocoding. The exact next action requiring separate owner authorization is:
  **AUTHORIZE EXACTLY ONE NEW CONTROLLED STAGE 8 DEVELOPMENT MATERIALIZATION AT
  THE NEW EXECUTABLE SHA.**

### D044 — Freeze the second-remediation Stage 8 DEVELOPMENT candidate

- **Date:** 2026-09-02.
- **Scope:** Sanitized reconciliation and candidate freeze for the single
  owner-authorized second-remediation Stage 8 DEVELOPMENT materialization. No
  code/science change, second job, independent rereview, or acceptance.
- **Decision:** Freeze job `1764219` as the current Stage 8 DEVELOPMENT
  candidate at exact executable
  `bdea7232a3f92ebd381be87610b753b8e4c35481`, output
  `/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage08/development/stage08_development_20260902T112644Z_bdea7232a3f9`,
  manifest SHA-256
  `346ea27ad60c1e00ef29c1126b2744f38049c1fa7d062647ab6df04e3330dee6`,
  and logical dataset SHA-256
  `9c9d431c2c1b92712e0cb372f2661ad48f4fe8758dc0327d25aef90ab2c2d526`.
- **Accepted inputs:** Bind exact accepted Stage 7 manifest `f5841087…`,
  logical identity `0f0706c1…`, contract fingerprint `c9561e6d…`, and schema
  fingerprint `b0e0e83e…`; bind exact accepted Stage 6 manifest `e1da7b8e…`,
  logical identity `2f6379c0…`, row-map identity `1ff9067c…`, input binding
  `6ba224d6…`, and schema fingerprint `9c07b7a4…`.
- **Scientific reconciliation:** The candidate contains 51,779 candidates,
  6,106,088 ordered components, 35,000 source rows, and 69,747 occurrences
  (34,822 STANDARD; 34,925 NATIVE). All components are mapped; dangling,
  unmapped, component-count-mismatch, and occurrence-count-mismatch totals are
  zero. Every frozen validation field passes. Parser, reference, network,
  semantic-trust, HOLDOUT, and production counts/access are zero or false.
- **Scientific identity:** Contract `8b3c530e…`, schema bundle `6c8ebecd…`,
  label mapping `b18167d2…`, all four schema fingerprints, all four relation-
  logical fingerprints, exact 20-label mapping, Stage 6/7 bindings, semantic
  classes, occurrence/parser-evidence semantics, and candidate/component/
  source/occurrence grains are unchanged.
- **Publication evidence:** Job `1764219` followed the ordinary successful
  path. Complete prepublication reopen validation preceded terminal success;
  the temporary tree was ready and fsynced before atomic rename; parent fsync
  and immediate final reopen validation passed before success returned.
  `_SUCCESS.json` exactly binds the manifest/scientific identities,
  `_IN_PROGRESS` is absent, no incomplete sibling remains, and stderr is
  empty. Eight directories are `0700`, 52 files are `0600`, symlinks are zero,
  and atomic/owner-only publication claims pass. Policy-A synthetic adoption
  was not fault-injected in this protected run and requires fresh independent
  challenge.
- **Runtime/resources:** Python 3.14.3, Unicode 16.0.0, PyArrow 25.0.0, and
  DuckDB 1.5.5; four requested CPUs, 32 GiB, DuckDB four threads/8GB, 15m10s,
  `0:0`, and MaxRSS 1,785,464 KiB. `AllocCPUS=80` is exclusive-node allocation,
  not application concurrency.
- **Historical relation:** Jobs `1763747`, `1763984`, and `1764219` have the
  same logical dataset SHA. The narrow conclusion is that the two publication
  remediations did not alter frozen Stage 8 science. Original executable
  `a2544401…`, first repair `bd89a032…`, both review failures, and their exact
  blockers remain truthful history. Neither older job validates `bdea7232…`;
  neither historical artifact is called corrupt.
- **Local finalization:** Stage 8 focused/fault-injection tests pass 28/28,
  relevant Stage 7 tests pass 54/54, and six runnable prior atomic-publication
  regressions pass. Ruff, scoped format, strict source/Stage 8 mypy, shell,
  JSON, Markdown links, diff, privacy/tracked-data, executable-blob,
  scientific-fingerprint, report-consistency, and Git checks pass. Selected
  Stage 4–6 publication tests stop only at the unchanged Python 3.14.3 guards
  under local Python 3.14.7.
- **Status:**
  `STAGE08_ADDRESS_EVIDENCE_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REREVIEW`.
  Stage 8 remains unaccepted. No additional job, Stage 9, HOLDOUT, production,
  reference, parser, or geocoding authority follows. Exact next action: **FRESH
  INDEPENDENT STAGE 8 REREVIEW OF THE BDEA7232 REPAIRED CANDIDATE.**

### D045 — Reject the second repair and bind publication success to ownership

- **Date:** 2026-09-02.
- **Scope:** Third bounded Stage 8 DEVELOPMENT publication remediation after
  failed independent rereview; code, synthetic tests, and current-facing
  sanitized documentation only. No protected execution or scientific redesign.
- **Independent findings:** Exact candidate
  `70e3de9536aee7074e27018d39e0164f3a2200ae`, executable
  `bdea7232a3f92ebd381be87610b753b8e4c35481`, and job `1764219` received
  `STAGE08_ADDRESS_EVIDENCE_INDEPENDENT_REREVIEW_FAIL`. First, an injected
  stdout `OSError` after a fully committed, independently valid publication
  made the CLI exit nonzero. Second, policy-A adoption checked identity before
  parent fsync and final validation but did not recheck it afterward, allowing
  a byte-identical different-inode FINAL replacement to be reported as the
  invocation's success. Review evidence commit is `2a6bba60…`; harness
  SHA-256 is `acf343ac…`. The controlled artifact is not asserted corrupt.
- **Decision:** Reject that candidate without modifying its branch or artifact.
  Executable `c04cb97214a9f1e5d2b80512c756400321eefa80` separates the
  filesystem publication result from nonessential result presentation. Once
  the materializer returns, result serialization, stdout write/flush, and
  best-effort stderr diagnostic exceptions preserve exit 0 and cannot demote
  the publication. Genuine pre-return publication failures remain nonzero.
- **Ownership binding:** Both ordinary publication and policy-A adoption share
  a final no-follow device/inode verification. It occurs after parent-directory
  fsync, complete final reopen validation, fallible outcome/timing construction,
  and `umask` restoration, and is the last rejection-capable publication
  operation before return. Identity-changed or symlink replacements fail
  closed and are not demoted; only an exact identity-matching owned failure
  tree may be demoted under the frozen policy.
- **Threat model:** The contract detects replacement during the program-
  controlled publication/adoption sequence under owner-only parent topology.
  It does not claim immunity to external `SIGKILL`, power loss, kernel failure,
  or privileged/owner mutation after the last identity stat or return.
- **Scientific preservation:** Contract, profile, four schemas, exact 20-label
  mapping, semantic classes, Stage 6/7 bindings, logical-hash rules, candidate/
  component/source/occurrence grains, parser/occurrence semantics, and the
  Stage 8/Stage 9 boundary remain exact. Every scientific fingerprint matches
  `bdea7232…`.
- **Local evidence:** Stage 8 focused/fault-injection tests pass 45/45,
  including exact stdout-first-write, explicit-flush process, byte-identical
  replacement at four post-rename boundaries, symlink, owned-only demotion,
  final-check ordering, and real-rename-then-raise regressions. All 149 Stage 7
  tests and 33 selected earlier atomic-publication parameter cases pass. The
  safe full suite has 612 passes, 24 expected Python 3.14.3 guard failures on
  local Python 3.14.7, and four protected-payload deselections. Ruff,
  changed-file format, strict mypy, shell, JSON, Markdown-link, diff, privacy,
  scientific-fingerprint, executable-surface, and Git gates pass.
- **Historical evidence:** Jobs `1763747`, `1763984`, and `1764219`, their
  immutable artifacts, all three failed review findings, and executables
  `a2544401…`, `bd89a032…`, and `bdea7232…` remain truthful reachable history.
  None validates `c04cb972…`; none is relabeled corrupt.
- **Status:**
  `STAGE08_ADDRESS_EVIDENCE_IMPLEMENTATION_READY_FOR_CONTROLLED_DEVELOPMENT_REEXECUTION`.
  This is not execution authority or Stage 8 acceptance. The exact next action
  requiring separate owner authorization is: **AUTHORIZE EXACTLY ONE NEW
  CONTROLLED STAGE 8 DEVELOPMENT MATERIALIZATION AT THE NEW EXECUTABLE SHA.**

### D046 — Freeze the third-remediation Stage 8 DEVELOPMENT candidate

- **Date:** 2026-09-02.
- **Scope:** Sanitized Stage 8 DEVELOPMENT execution reconciliation and
  candidate freeze for the single owner-authorized third-remediation
  materialization. No additional protected execution, row-level inspection,
  implementation/science change, independent review, or acceptance.
- **Decision:** Freeze job `1764273` as the current Stage 8 DEVELOPMENT
  candidate. Bind exact executable
  `c04cb97214a9f1e5d2b80512c756400321eefa80`, output
  `/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage08/development/stage08_development_20260902T132726Z_c04cb97214a9`,
  manifest
  `2a50bd8c066552c9cb7505ed2d6071f1ee36161b9a2cc07f3ed364cf00237827`,
  logical dataset
  `9c9d431c2c1b92712e0cb372f2661ad48f4fe8758dc0327d25aef90ab2c2d526`,
  and final `(st_dev, st_ino)` identity `(54, 9363000937145638642)`.
- **Accepted inputs:** Stage 7 manifest remains `f5841087…`, and Stage 6
  manifest remains `e1da7b8…`. Their contract, schema, logical-dataset,
  parser-bundle, row-map, and input-binding identities match the frozen Stage 8
  contract exactly.
- **Scientific evidence:** The artifact contains 51,779 candidates, 6,106,088
  ordered components, 35,000 source rows, and 69,747 occurrences (34,822
  STANDARD; 34,925 NATIVE). Dangling/unmapped components and component/
  occurrence-count mismatches are zero. Every frozen scientific validator
  passes. Parser, reference, network, geocoder/external-service, and semantic-
  trust counts are zero; HOLDOUT and production access are false.
- **Scientific identity:** Contract, schema bundle, all four relation schemas,
  mapping, all four relation-logical fingerprints, semantic classes, exact
  20-label mapping, Stage 6/7 bindings, candidate/component/source/occurrence
  grains, logical-hash rules, and the Stage 8/Stage 9 boundary remain exact.
- **V3 terminal evidence:** Job `1764273` followed the ordinary successful
  publication path. Prepublication rejection-capable validation, temporary-
  tree durability, atomic rename, parent fsync, complete final reopen
  validation, outcome construction, and `umask` restoration all preceded the
  final no-follow device/inode ownership verification. That gate passed, was
  the last rejection-capable publication operation, and bound success to the
  reported identity. Success-marker binding, absent in-progress/incomplete
  state, owner-only modes, zero symlinks, atomic publication, and empty stderr
  all pass.
- **Fault boundary:** No fault was injected into the controlled job. Post-
  commit stdout/flush/serialization failures, real-rename-then-raise, and
  byte-identical/during-fsync/during-validation/pre-final-check replacements
  remain local synthetic evidence and require fresh independent challenge.
- **Resources:** Job `1764273` completed `0:0` in 16m08s with four requested
  CPUs, 32 GiB, DuckDB four threads/8GB, and MaxRSS 1,789,612 KiB.
  `AllocCPUS=80` is classified only as exclusive-node allocation because
  scheduler metadata records `general1 OverSubscribe=EXCLUSIVE` and an
  assigned node with 80 CPUs.
- **Historical evidence:** The logical dataset SHA matches jobs `1763747`,
  `1763984`, `1764219`, and `1764273`. The narrow conclusion is only that all
  publication remediations to date left the frozen Stage 8 scientific dataset
  unchanged. Historical jobs validate only their exact executables; previous
  failed reviews remain failures, and no artifact is called corrupt.
- **Local finalization:** All 45 Stage 8 tests, 14 exact v3 critical cases, 149
  Stage 7 tests, and 129 Stage 0–2 tests pass. Ruff, scoped format, strict mypy,
  shell, JSON, Markdown-link, diff, privacy, executable-identity, fingerprint,
  report-consistency, and Git gates pass. Python 3.14.3 guards remain exact.
- **Status:**
  `STAGE08_ADDRESS_EVIDENCE_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REREVIEW`.
  Stage 8 remains unaccepted. No additional job, Stage 9, HOLDOUT, production,
  parser, reference, or geocoding work is authorized. Exact next action:
  **FRESH INDEPENDENT STAGE 8 REREVIEW OF THE C04CB972 REPAIRED CANDIDATE.**

### D047 — Accept the exact Stage 8 address-evidence DEVELOPMENT candidate

- **Date:** 2026-09-02.
- **Scope:** Final owner acceptance and main integration of Stage 8
  DEVELOPMENT only; no scientific rerun, production authority, or later-stage
  authorization.
- **Decision:** Accept exact reviewed candidate
  `231cdbf9db755fb56486c46b3b3faa02f5b5f3b6` as `STAGE_8_ACCEPTED` on
  DEVELOPMENT. Its reviewed executable remains exact
  `c04cb97214a9f1e5d2b80512c756400321eefa80`. Preserve the complete candidate
  branch history through normal merge commit
  `ce9e9cac60ba1a767043a7bf09bbf0ad2589f3b3`; the accepted candidate is its
  second parent and remains an ancestor of final `main`.
- **Authoritative DEVELOPMENT evidence:** Job `1764273`, manifest SHA-256
  `2a50bd8c066552c9cb7505ed2d6071f1ee36161b9a2cc07f3ed364cf00237827`,
  and logical dataset SHA-256
  `9c9d431c2c1b92712e0cb372f2661ad48f4fe8758dc0327d25aef90ab2c2d526`.
- **Independent evidence:** Verdict
  `STAGE08_ADDRESS_EVIDENCE_INDEPENDENT_REREVIEW_PASS`; corrected review
  commit `f8a456f5c939c4061d2be232fd5037010b7a88c8`; independent harness SHA-256
  `4e728ca7cf90b270c892da49f9d3cfa56b2fb2e71b4aac6b54526a0380257586`;
  controlled evidence SHA-256
  `9fe9420779a96f8c3663e8876cb3206a72ca15931bdfa23105d13dddf7546de0`;
  and Goethe review job `1764376` (`COMPLETED 0:0`). Candidate defects are
  zero and infrastructure-incomplete checks are zero.
- **Independent result:** Stage 7-to-Stage 8 equality, component
  reconstruction, source map-back, dangling, unmapped, component-count, and
  occurrence-count mismatch totals are all zero. Every frozen scientific
  fingerprint and binding, filesystem/publication check, and
  privacy/prohibited-activity check passed. Parser, reference, network, and
  geocoder activity were zero; HOLDOUT and production were not accessed.
- **Review-only history:** RH-001 was an invalid cross-job device/inode
  equality assumption in the independent harness. Its failed review job and
  sanitized evidence remain reachable, and the corrected persistent-identity
  rule remains bound to the corrected review commit. RH-001 is not a Stage 8
  candidate or artifact defect.
- **Scientific preservation:** The Stage 8 contract, profile, schemas,
  semantic classes, 20-label mapping, Stage 6/7 bindings, grains, logical-hash
  rules, and Stage 8/Stage 9 boundary remained unchanged through all
  publication remediations. No executable, source, test, launcher, or
  configuration mutation followed executable `c04cb972…`; only reviewed
  reporting and documentation followed it on the accepted branch.
- **Historical preservation:** Rejected candidates `adde81d…`, `fdf2f8c…`,
  and `70e3de95…`; executables `a2544401…`, `bd89a032…`, and `bdea7232…`;
  jobs `1763747`, `1763984`, and `1764219`; all failed-review findings; and
  every remediation record remain truthful reachable history. No failure is
  relabeled as success, and each job validates only its exact executable.
- **Status:** `STAGE_8_ACCEPTED` on DEVELOPMENT. Production Stage 8, HOLDOUT,
  Stage 9, references, hypotheses, Senzing, Pelias, and geocoding remain not
  started and unauthorized. The exact next task is **FULL STAGES 0–8 PIPELINE
  AUDIT BEFORE STAGE 9**, then stop.

### D048 — Remove the superseded Phase implementation architecture

- **Date:** 2026-09-03.
- **Decision:** The only active pipeline architecture is Stage 0–8. Remove the
  `phase01` and `phase02` source packages, Phase-named entry points, the obsolete
  conversion runner, and the fixed historical payload synchronization helper.
- **Required migration:** Move the sole accepted source-inventory scanner into
  canonical `s00_*` modules. Move the Stage 1 constants, stable-row identity,
  Arrow schema, semantic digest, and generic fingerprint helper required by
  current Stage 0–2 validation into Stage/common locations. Update every caller
  without changing formulas, schemas, values, or accepted evidence.
- **Compatibility boundary:** Immutable source-foundation bundles retain their
  original phase-prefixed run IDs, filenames, serialized keys, schema/version
  identifiers, and diagnostic codes. Current Stage 0/1 code may read or emit
  those exact frozen identifiers, but no Phase package, CLI, runner, launcher,
  configuration, or report hierarchy remains active.
- **Historical preservation:** `docs/history/source_foundation/` remains
  explicitly marked historical/superseded. Git history remains the archive for
  deleted implementations and is not rewritten.
- **Scientific preservation:** Accepted Stage 0–8 science and fingerprints are
  unchanged. This decision does not authorize Stage 9, protected execution,
  HOLDOUT access, production Stage 2, parsing, references, or geocoding.

### D049 — Freeze the accepted pre-Stage-9 baseline

- **Date:** 2026-09-03.
- **Scope:** Repository-only consolidation of the completed pre-Stage-9 audit;
  no protected-artifact reopen, materialization, scientific redesign, or Stage
  9 work.
- **Baseline identity:** The final accepted `main` is frozen by annotated Git
  tag `pre-stage09-baseline-v1`; its target SHA-1 is recorded in the tag's
  sanitized message. `STAGE_8_ACCEPTED` remains the current DEVELOPMENT
  terminal state. Stage 9 is **NOT STARTED**.
- **Accepted population and chain:** Benchmark V1 remains exactly 1,405 source
  files, 35,000 DEVELOPMENT rows, and 15,000 sealed HOLDOUT rows. Stage 5/6
  remains 69,747 occurrences (34,822 STANDARD; 34,925 NATIVE) mapped completely
  to 51,779 exact candidates. All Stage 0→8 adjacent bindings passed.
- **Scientific boundary:** Stage 7 remains accepted evidence-only parser
  evidence, without semantic-trust claims. Stage 8 remains accepted lossless
  evidence/indexing only, with a complete handoff for a future separately
  designed Stage 9. No Stage 8 schema, mapping, contract, output, or Stage 9
  precursor was changed by this freeze.
- **Frozen fingerprints:** Stage 7 contract
  `c9561e6d08263b2a8824ff66f2a3aa8521e3ff880759abc14173cce440ced8a4`;
  Stage 7 schema
  `b0e0e83ea3d929b7df8a6a5f64c2e8eb026395a917da90e97a98858b27e9ead2`;
  Stage 8 contract
  `8b3c530e714177fe2c30a97d61dcc199b7f9efba58f3c17a291b817af0f24d5e`;
  label mapping
  `b18167d2d5c1f1402d1bb0e92559befb92418f5f4f34df885596778a11d5c09d`;
  schema bundle
  `6c8ebecd24c495dbe2ce32125ac1cb89c4a9de4905c786b774d10ad728ed392f`;
  candidate evidence schema
  `b1d56ea33c22e639ab798581c5533b1a0981ef5452dce5cb24e168d4a684bd4c`;
  parser component evidence schema
  `112fb17c2afac27b941d30f57fe5c1bb2e46d779f89bdf2efbd8c719a3b87ccf`;
  source candidate map schema
  `884eb8456fc6ee84a699a9e2371224e5c709363daac0febc5975f911bf48c398`; and
  representation occurrence schema
  `df1cac9b6d9f86ffb76d1ea744fc64f15149c9e33fef980213286b91b2d02038`.
- **Provenance recovery:** Stage 2 output manifest
  `260b77fea50bc2db1bfb10dca8339cb33bcb2e2aad7de9c07ed55a71dec0d419`
  is `RECOVERED_EXACT` from the accepted Stage 3 sanitized upstream binding.
  The Stage 0/1 1,405-file DEVELOPMENT candidate, executable, merge, job,
  independent-review, and Stage 1 logical identities are
  `HISTORICAL_PROVENANCE_NOT_RETAINED`; their fields remain null. This prevents
  Git-only independent replay of those original executions but does not affect
  Benchmark identity, the accepted Stage 2→8 chain, the Stage 8 handoff, or
  Stage 9 readiness.
- **Nonblocking limitations:** Exact local Python 3.14.3 guarded validation was
  not available under local Python 3.14.7; the guard remains fail-closed.
  Protected artifact reopen/rehash was intentionally outside this repository
  audit scope. Neither limitation is a defect or Stage-9 blocker.
- **Decision:** No Stage-9-blocking scientific, contract, population, identity,
  map-back, privacy, reproducibility-for-consumption, or handoff defect remains.
  This freeze does not authorize Stage 9, HOLDOUT, production, reference work,
  parsing, Pelias, or geocoding.

### D050 — Approve the Stage 9 design revisions and freeze public references

- **Date:** 2026-09-07.
- **Authority/scope:** Owner approved the Stage 9 scientific direction with
  four required revisions, bounded public-reference acquisition, design/lock
  commit and normal push, then stop. Materializer/index implementation and
  protected execution are explicitly excluded from this session.
- **Design:** [Stage 9 contract](stages/STAGE09_OFFLINE_REFERENCE_EVIDENCE.md)
  and [freeze record](stages/STAGE09_REFERENCE_FREEZE.md). Actual provenance
  families are ISO_CODES, LIBADDRESSINPUT_METADATA and GEONAMES_POSTAL.
  Every capability has independent positive/negative authority booleans.
  GeoNames cannot contradict; missing metadata is unavailable. Only exact
  recognized ISO code ownership and enabled frozen format/prefix predicates
  have scoped negative authority. NOT_FOUND is never invalidity.
- **References:** iso-codes upstream 4.20.1 / Debian 4.20.1-1, selected after
  comparison with 4.18.0-1; actual libaddressinput all.json from the current
  suitable google-i18n-address 3.1.1 release; one GeoNames postal snapshot
  acquired 2026-09-07. The [lock](scientific_assets/stage09_reference_pack_lock_v1.json)
  freezes exact archives, members, provenance, licenses, per-country component
  observations and capability exclusions. Raw bytes remain offline/ignored;
  there is no automatic refresh within DEVELOPMENT, HOLDOUT or an accepted run.
- **Minimal model:** Registry, capability, public reference objects, candidate
  evidence, multi-match members only when necessary, and aggregate coverage.
  Stage 8 remains the only authoritative source/representation map; evidence
  uses exact immutable candidate/source/component pointers. No correction,
  query, coordinates, parser truth or final address-validity output.
- **Boundary:** BOUNDARY_HANDOFF_SUFFICIENT through Stage 8→Stage 6 source-line
  lineage. No Stage 0–8 science/source/schema/fingerprint change; accepted audit
  remains closed. HOLDOUT sealed, production and Pelias untouched.
- **Status:** STAGE09_REFERENCE_DESIGN_OWNER_APPROVED_AND_FROZEN is design/public
  reference status only. Stage 9 implementation and protected execution are
  NOT STARTED; no Stage 9 acceptance or geocoding authorization is granted.

### D051 — Implement frozen Stage 9 and prepare one controlled DEVELOPMENT run

- **Date:** 2026-09-08.
- **Authority:** The owner explicitly authorized Stage 9 implementation,
  substantial synthetic/local tests, exact executable commit/push and one
  controlled Goethe-NHR SLURM DEVELOPMENT execution with validation/publication
  and sanitized reporting. If PENDING/RUNNING, record the job and stop; do not
  repeatedly poll, cancel or submit a duplicate. Stop at the candidate for
  independent review; no Stage 9 acceptance or Stage 10 authority is granted.
- **Preservation:** Design-freeze commit `f85510f938a8506bf3d4a4f8d2b908d801957414`,
  frozen design/lock bytes, Stage 0–8 science and all accepted fingerprints remain
  unchanged. HOLDOUT stays sealed; production and Pelias are outside scope.
- **Implementation:** Six logical relations only; exact Stage 8 pointers,
  four-state/negative-authority enforcement, locked public inputs, bounded
  Arrow/DuckDB joins and deterministic canonical identities. Reusable public
  objects/indexes never project coordinates. No new authoritative mapping layer.
- **Execution/publication:** Exact detached Git executable, unchanged runtime
  guards, private directories/files, public raw-hash verification and full input
  binding before protected evaluation; checkpointed 16-group execution, full
  reversed-group validation replay and atomic no-replace publication/reopening.
  Historical cross-job inode equality is not used.
- **Evidence/status:** [Implementation record](stages/STAGE09_IMPLEMENTATION.md)
  and [DEVELOPMENT execution record](../reports/development/stage09.md) contain
  local validation, the complete pre-run defect ledger and current submission
  state. Implementation is complete and execution prepared; this is not a
  completed protected candidate or scientific acceptance.

### D052 — Record Stage 9 startup failure without weakening publication

- **Date:** 2026-09-10; continuation of the authorized Stage 9 session.
- **Evidence:** Job `1770156`, exact executable
  `3c3864f0b42a6bc69d293415f7cd755c74187fc2`, failed after five seconds with exit
  `1:0` on 2026-09-09. The scheduled synthetic filesystem preflight reached
  `renameat2(RENAME_NOREPLACE)` and returned `ATOMIC_NO_REPLACE_FAILED` before
  public-index construction or protected Stage 8 access. No candidate, manifest,
  success marker or reusable reference pack was created. Invented sentinels and
  logs remain private and preserved; the exact checkout remains clean.
- **Diagnostic limit:** Errno was discarded by the helper. PanFS flag support
  is not established; an unsupported-operation explanation is a hypothesis,
  not a verified kernel diagnosis. Do not weaken no-overwrite/publication guards
  or alter the frozen scientific design to guess around the failure.
- **Disposition:** Record the failed attempt in the
  [execution report](../reports/development/stage09.md); no automatic rerun or
  new SLURM job. Request owner authorization for one bounded synthetic-only
  compute-filesystem diagnostic, then resolve all compatibility issues before
  proposing a controlled DEVELOPMENT retry. No accepted Stage 0–8 science,
  source, fingerprints, reference versions or executable changed in this
  continuation. HOLDOUT sealed; production/Pelias untouched. Stage 9 remains
  NOT ACCEPTED and no ready candidate is claimed.

### D053 — Authorize one bounded synthetic filesystem diagnostic

- **Date:** 2026-09-10.
- **Authority:** The owner answered `continue` to the explicit request for one
  short synthetic-only SLURM filesystem diagnostic after D052. This authorizes
  preparing/testing/pushing the probe and submitting it once; not a protected
  DEVELOPMENT rerun, scientific redesign or publication fallback.
- **Scope:** A new owner-only diagnostic tree, fixed invented sentinels, immediate
  native errno capture, absent/existing-target collision behavior, fsync and
  same-invocation ownership checks. Zero-flag/POSIX fresh-target baselines are
  measurements only, never an enabled materializer fallback. No prior attempt,
  source data or public-reference payload is opened or altered.
- **Execution:** Exact pushed detached Git checkout, existing guarded runtime;
  one CPU, 2 GiB, five minutes on `general1`, automatic requeue disabled. No
  scientific Stage 9 output or success marker is produced. Stop if pending or
  running; use the completed diagnostic to establish the compatibility issue
  before proposing any Stage 9 execution correction or retry.
- **Evidence:** Test and submission details are maintained in the
  [Stage 9 execution record](../reports/development/stage09.md). The frozen
  contract/reference pack, Stage 0–8 accepted science and original failed
  executable remain unchanged; Stage 9 remains NOT ACCEPTED.

### D054 — Reconcile the synthetic diagnostic; retain the publication blocker

- **Date:** 2026-09-10; owner continuation after diagnostic submission.
- **Evidence:** Diagnostic `1771054`, exact executable
  `4915852d874a11a5f437d6cfac8837b5f9b6ebd8`, completed with exit `0:0` in three
  seconds. Immediate errno capture found `EINVAL` (22) for a fresh-target
  `renameat2(RENAME_NOREPLACE)`; three existing-target collisions returned
  `EEXIST` with both sides preserved. Zero-flag and POSIX fresh-target baselines
  succeeded; all 12 directory-fsync observations passed. The report hash is
  `8742918b6647ef4283a1f5445a6240c84009239257c782ee367903c30549ed5a`.
- **Conclusion and limits:** The current no-replace operation is incompatible
  with the tested kernel/filesystem environment. This is not a diagnosis of
  every PanFS installation or recovery of original job `1770156`'s lost errno.
  Baseline success does not prove a collision-safe replacement; fsync success
  is not a power-loss test. Diagnostic completion is not Stage 9 publication.
- **Disposition:** Preserve both attempts and all synthetic diagnostics. The
  [execution report](../reports/development/stage09.md) records the complete
  bounded compatibility ledger and proposes owner review of a publication-only
  correction, including ownership/concurrency/fault behavior. No fallback,
  scientific-design exception or additional job is authorized by this result.
  No executable, Stage 0–8 source/fingerprint or reference asset changed in this
  reconciliation. No protected/reference payload was opened by the diagnostic;
  HOLDOUT stays sealed and production/Pelias untouched. Stage 9 is NOT ACCEPTED;
  the operational blocker remains open and no ready candidate is claimed.

### D055 — Propose exclusive run reservation and commit seal for owner review

- **Date/authority:** 2026-09-10. The owner expressly authorized one bounded
  publication-protocol revision with design and synthetic/local validation only.
  No protected input, cluster probe, DEVELOPMENT retry or scientific change.
- **Proposal:** A canonical run is exclusively created once and never moved or
  taken over. Its bound registration is prepared and fully validated before
  exclusive creation of an empty `_COMMITTED` file atomically commits it.
  Directory or `_SUCCESS.json` existence alone is not success. Exact external
  expectations and complete reopening are mandatory; old consumers must be
  changed only in a subsequently approved integration. No replacing rename,
  hard-link, symlink or stale-lock recovery is introduced.
- **Evidence:** Existing diagnostic creation/fsync success plus the documented
  POSIX exclusive-create/mkdir semantics support selecting this protocol without
  another cluster capability probe. Local tests cover faults and concurrent
  publishers but do not claim a cross-node or power-loss experiment. The
  [revision candidate](stages/STAGE09_PUBLICATION_PROTOCOL_REVISION.md) states
  exact assumptions, identities, adoption rules, test matrix and full ledger.
- **Disposition:** Design addendum and tests-only executable model, not an
  installed publication change. Active Stage 9 source/launcher and generic
  infrastructure remain unchanged pending owner review. A commit that may have
  happened is reconciled once or reported explicitly unverified; it is never
  destructively demoted. Exact existing success may be adopted without claiming
  a new build. Failed/incomplete keys are never reused. Frozen Stage 9 science,
  references and accepted Stage 0–8 remain unchanged; HOLDOUT sealed and
  production/Pelias untouched. Stage 9 is NOT ACCEPTED.

### D056 — Require and authorize one PanFS exclusive-create diagnostic

- **Date/authority:** 2026-09-10. Owner conditionally approves the publication
  protocol's scientific/logical direction but explicitly withholds integration.
  The direct environment-evidence gap supersedes D055's original judgment that
  generic standards plus observed ordinary creation were enough to proceed.
- **Authorized scope:** Prepare/test/commit/push and submit exactly one
  synthetic-only SLURM diagnostic on the Stage 9 PanFS filesystem. One node,
  one requested CPU, 2 GiB, five minutes, `general1`, `--no-requeue`. No protected
  Stage 8, references, HOLDOUT, production, Pelias or DEVELOPMENT retry.
- **Required evidence:** Fresh O_CREAT|O_EXCL creation; exact collision errno
  and sentinel preservation; four independent spawned processes released only
  after all report ready; exact `_COMMITTED` seal and permanent mkdir reservation;
  directory fsync, same-invocation effects, repeated reopen/modes/single-link
  checks, and rejection of existing/dangling synthetic symlinks. No replacing
  rename, integration or unsafe fallback. Preserve all diagnostic fixtures.
- **Disposition:** Diagnostic source/tests/launcher only; original jobs `1770156`
  and `1771054` and their artifacts remain untouched. Fixed diagnostics capture
  native return/errno immediately. Stop after one submission if pending/running;
  after completion reconcile results, then stop for explicit owner integration
  authorization. The [execution record](../reports/development/stage09.md)
  carries exact executable/submission/result metadata. Stage 0–8 and frozen
  Stage 9 science/reference contracts remain unchanged; Stage 9 NOT ACCEPTED.

### D057 — Confirm measured PanFS exclusive-create capability; stop before integration

- **Date:** 2026-09-10; owner continuation of the one authorized synthetic job.
- **Evidence:** Job `1771149`, exact executable
  `a9e6ede7c8aa45f8f11b0eadc797839e46c5b057`, completed in five seconds with exit
  `0:0`. All ten cases passed on PanFS: fresh O_CREAT|O_EXCL|O_NOFOLLOW and
  mkdir, EEXIST collision preservation, three synchronized four-process races
  with one winner/three losers each, exact empty seal, repeated byte/mode/owner/
  single-link reopening and all four synthetic symlink rejections. All 23 recorded
  parent-fsync checks passed. Report SHA-256:
  `e8d8333201a8c0b061d12288fadf404d833a875ffe0a4d160d535b88e6844f35`.
- **Independent reconciliation:** Report bytes/hash and all case outcomes checked
  separately; exact hashes of all 11 regular files and full synthetic topology
  reconfirmed through read-only shell metadata. Attempts/sentinels/logs preserved.
  [Full evidence](../reports/development/stage09.md) distinguishes requested
  resources, allocated CPUs and unavailable peak-memory measurement.
- **Disposition:** D056's direct environment-evidence requirement is met for the
  tested same-node operations. No cross-node, power-loss or integrated-protocol
  result is inferred. This is capability evidence, not integration authorization
  or Stage 9 acceptance. Only sanitized documentation changes in this continuation;
  materializer/launcher, original jobs, accepted Stage 0–8 and frozen Stage 9
  scientific/reference contracts remain unchanged. No protected/reference payload,
  HOLDOUT, production or Pelias access and no DEVELOPMENT retry. Stop for explicit
  owner authorization to integrate the publication protocol.

### D058 — Integrate approved PanFS publication protocol; authorize one corrected retry

- **Date/authority:** 2026-09-10. Owner explicitly approves integration of protocol
  candidate `96d17e763addc21b0a1c321c3a03666e928c25c7` after PanFS diagnostic
  `1771149` confirmed the exact creation primitives. Starting main/origin-main
  `a2949199ea47ad453d3441e9f46429b395b00274` was clean and exact; protocol/diagnostic
  commits are in history. Read-only namespace inspection found no candidate or
  public-pack publication before integration.
- **Bounded change:** Stage 9-only reusable permanent reservation, canonical
  registration and exclusive empty `_COMMITTED` seal helper; both public-pack and
  candidate adapters and the compute preflight use it. No active no-replace rename,
  ordinary-rename fallback, destructive demotion or stale-reservation takeover.
  Prepared/committed validators remain separate and full scientific validation
  remains mandatory. Exact expected manifest and all transitive bindings govern
  adoption, not historical inode equality. One bounded effect reconciliation
  handles uncertain commit/close results; final ownership checks follow teardown.
- **Validation:** Full local/synthetic/fault gate and complete bounded ledger in
  the [execution report](../reports/development/stage09.md). Accepted Stage 7/8
  regressions and all frozen Stage 9 scientific/reference bytes remain unchanged.
  No protected local materialization or protected examples are needed.
- **Execution:** Commit/push before one fresh detached Goethe checkout; exactly
  one corrected DEVELOPMENT job, four requested CPUs, 32 GiB, 24 hours, general1,
  no requeue. Accepted 35k DEVELOPMENT and exact frozen offline pack only. If
  pending/running stop without polling/cancellation/resubmission; if failed,
  preserve and classify all evidence and stop for owner review; if successful,
  reconcile/publish a candidate and stop for independent review. No acceptance,
  Stage 10, HOLDOUT, production, Pelias or external validation authorization.
- **Preservation:** Original job `1770156`, executable `3c3864f0…`, and diagnostic
  jobs `1771054`/`1771149` remain immutable historical evidence. No Stage 0–8
  implementation/artifact/contract or Stage 9 scientific semantics are changed.

### D059 — Freeze corrected Stage 9 DEVELOPMENT candidate for independent review

- **Date/authority:** 2026-09-12; owner continuation of D058's one corrected run.
  No new SLURM job or materialization was submitted. Exact reporting main
  `86b9f264be967e7e5033d8f344b1993635b02b05` was clean/equal to origin before work.
- **Executable/job:** `3e10ac7c1309c2636f35c0709fa283305d60d998` / `1771191`;
  COMPLETED, `0:0`, 08:04:53, batch MaxRSS 10,125,844 KiB. Four requested CPUs,
  32 GiB; scheduler allocated 80 CPUs, not measured utilization.
- **Publication:** Approved permanent reservation/registration/exclusive seal
  protocol returned PASS after full scientific/hash prepared and committed
  reopening and last-operation ownership checks. Candidate manifest
  `321c9d8352fac5b78612a7c8e52f6f810f92bddb1e91f7cfe348398a6d707240`, logical
  `7ae84e149f4c9c2de7a791c9b326b88e387a70d155d8be55acf6b55e06bafae3`;
  public-pack manifest
  `dd7994b907250d515470b820bcbf42993a08e4f3116409b7c94168446e1c064a`.
  Exact input/reference/schema and registration identities and all file topology
  reconcile. Full protected payload checks ran in the job; this continuation
  used metadata and the small sanitized aggregate relation, not login-node
  protected processing or a second full validation job.
- **Scientific evidence:** All 35,000 source rows / 51,779 candidates / 69,747
  occurrences retained; 6,565,329 evidence rows; 51,066 candidates evaluable;
  zero candidate loss or technical failures. Four-state totals: SUPPORTED
  531,488; CONTRADICTED 54,025; NOT_FOUND 2,128,794; NOT_EVALUABLE 3,851,022.
  All contradictions are authorized frozen libaddressinput pattern/prefix
  conflicts. GeoNames contradictions zero; association-mismatch diagnostics
  6,673 remain NOT_FOUND, not invalidity.
- **Review limitations:** Q04 conflict rate among evaluable checks is 59.996%;
  source/parser and country breakdowns, exact-rule/runtime checks and interpretation
  limits are retained, not tuned away. All country assessments are unresolved
  because no qualifying exact source subdivision-code witness was obtained. No address
  accuracy, parser correctness or final geographic truth claim is made.
- **Disposition:** [Full candidate report](../reports/development/stage09.md)
  includes all six relation identities, 214 populated country contexts plus
  unresolved, capability/family diagnostics, complete bounded reconciliation
  ledger, resource limits and 836 passing local tests/static checks. Stage 7/8
  and frozen Stage 9 science/reference bytes unchanged; HOLDOUT sealed;
  production/Pelias untouched. Original failure and diagnostic evidence remain
  immutable. **Stage 9 DEVELOPMENT candidate ready, NOT YET ACCEPTED**.
  Stop for independent review; no Stage 10 authorization.

### D060 — Owner acceptance and freeze of Stage 9 offline reference evidence

- **Date/authority:** 2026-09-14; explicit owner acceptance after
  `STAGE09_OFFLINE_REFERENCE_EVIDENCE_INDEPENDENT_REVIEW_PASS`. Final status:
  **STAGE_9_ACCEPTED**, DEVELOPMENT only. Candidate defects = **0**; no scientific
  output change or DEVELOPMENT rerun is required. Acceptance is documentation/
  provenance only, not another execution or permission to begin Stage 10.
- **Provenance:** Starting main/origin-main
  `1c7182931fd4be2a7d5dee00d3105a1e54377bae`, clean. Remote review branch
  `review/stage09-independent-20260912` verified at
  `a9ae443ca140627acf1712886670f39f227c1dc6`, then merged normally without squash
  in `8a43e6a8baba5fe8e1cb366c6b811b01f1ad2d8e`. Both parents and all six review
  commits/harness history remain explicit; no merge conflicts or scientific
  edits. Annotated tag `stage09-offline-reference-evidence-v1` identifies the
  final owner-acceptance commit, not just the executable.
- **Accepted artifact:** Executable `3e10ac7c1309c2636f35c0709fa283305d60d998`,
  job `1771191`, COMPLETED `0:0`, 08:04:53, peak RSS 9.657 GiB. Publication key
  `stage09_development_20260910T155542Z_3e10ac7c1309`; manifest
  `321c9d8352fac5b78612a7c8e52f6f810f92bddb1e91f7cfe348398a6d707240`, logical
  `7ae84e149f4c9c2de7a791c9b326b88e387a70d155d8be55acf6b55e06bafae3`.
  The [authoritative acceptance record](../reports/development/stage09.md#owner-acceptance-and-freeze--2026-09-14)
  pins the full artifact path, contract/profile/schema fingerprints, accepted
  Stage 8 binding, reference-pack manifest and frozen lock. All remain unchanged.
- **Independent review:** Final evidence commit `a9ae443c…`, corrected job
  `1772139`, COMPLETED `0:0`, 01:00:30. 100 artifact checks, 836 candidate tests
  and 23 additional public/synthetic checks PASS. Full publication, inventory,
  reopen, PK/FK/integrity, bindings, four-state/ISO/libaddressinput/GeoNames,
  normalization, privacy/execution and handoff checks PASS; candidate defects 0.
  Review-harness history/fixes remain preserved and distinct from the candidate.
- **Scientific interpretation:** OFFLINE REFERENCE EVIDENCE only. SUPPORTED /
  CONTRADICTED / NOT_FOUND / NOT_EVALUABLE; NOT_FOUND != CONTRADICTED; GeoNames
  negative authority FALSE. Neither address validity nor final geocoding accuracy
  is established. Q04 54,022 / 90,043 = 59.995780% is a conditional evaluable
  postcode-pattern reference-rule conflict rate, independently classified A —
  scientifically plausible and correctly implemented, not invalid addresses.
  Parser-component repetition materially weights evidence-row denominators;
  all future reports must keep denominators explicit. Country assessments give
  no resolving signal in this population because there are zero qualifying full
  subdivision-code witnesses under the frozen rule. This expected limitation
  does not invalidate other Stage 9 evidence. BOUNDARY_HANDOFF_SUFFICIENT;
  accepted Stage 8 remains the sole map-back layer. Production capacity is unproven.
- **Publication acceptance:** For Stage 9, exclusive permanent reservation →
  immutable validated artifact → registration → atomic exclusive `_COMMITTED`
  seal → reopen/full validation. `O_CREAT|O_EXCL` is demonstrated by PanFS job
  `1771149`, diagnostic SHA-256
  `e8d8333201a8c0b061d12288fadf404d833a875ffe0a4d160d535b88e6844f35`.
  `RENAME_NOREPLACE` is incompatible with the tested path; failed job `1770156`
  and diagnostic `1771054` remain historical evidence. No Stage 8 publication
  semantics/artifact is changed. Reuse for Stages 10+ requires checking the same
  assumptions/path/filesystem; directory existence alone is not success.
- **Freeze boundary:** No source/tests/launcher or frozen scientific asset edits;
  candidate output/manifest/registration/seal and candidate-era acceptance flags
  remain immutable. This owner decision and tag add acceptance without rewriting
  history. Safe acceptance checks are recorded in the report. Stage 0–8 science
  unchanged; STAGE_8_ACCEPTED; HOLDOUT SEALED; production/Pelias untouched;
  Stage 10 NOT STARTED. Stop after acceptance; no cluster job or rerun.

## Open decisions

These questions require future stage designs and explicit approval:

- future reference vintages/country-specific extensions beyond frozen Stage 9 v1;
- the bounded Stage 10 hypothesis/query ladder;
- Stage 13 scoring/calibration and contradiction policy; and
- Stage 14 granularity-specific usability thresholds, including treatment of
  interpolated Pelias address results.

Nothing in this register authorizes HOLDOUT, another Stage 8 protected
execution, geocoding, or production Stage 2 through Stage 8. D050 records the
approved Stage 9 design/public-reference scope; D051 records the separate bounded
Stage 9 implementation/DEVELOPMENT authorization, not acceptance or later stages.
D060 alone records final Stage 9 DEVELOPMENT owner acceptance; it authorizes
neither a rerun nor later-stage design/implementation.
Stage 7 decisions
D023–D036 retain their stated historical DEVELOPMENT scopes; D037 alone
records final Stage 7 DEVELOPMENT acceptance. D038 records the prospective
Stage 8 design boundary; D039/D040 record the rejected implementation and its
single historical artifact; D041 records rejection and bounded implementation
remediation; D042 freezes the first repaired DEVELOPMENT candidate without
granting acceptance or later-stage authority; and D043 records the failed
independent rereview plus the second bounded publication remediation. D044
freezes the resulting DEVELOPMENT candidate without granting acceptance or
later-stage authority. D045 records its failed independent rereview and the
third bounded terminal-status/ownership remediation; it grants no execution or
later-stage authority. D046 freezes the resulting DEVELOPMENT candidate
without granting acceptance or later-stage authority. D047 alone records final
Stage 8 DEVELOPMENT acceptance and preserves all prior Stage 8 failures as
historical evidence. D048 records the architecture-only removal of superseded
Phase implementation surfaces while preserving frozen source-foundation
identifiers and accepted Stage 0–8 science.
