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
- **Status:** LOCKED except interpolated-address acceptance remains open.

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

## Open decisions

These questions require future stage designs and explicit approval:

- final Stage 7 resource policy, technical-failure necessity, and contract
  freeze after the targeted supervisor conflict;
- country-specific Stage 11 coverage and syntax policy;
- reference versions/licenses and blocking semantics for Stages 13–15;
- exact high-precision correction policy for Stage 16;
- Stage 17 component inclusion/omission policy;
- Stage 18 controlled query ladder; and
- whether interpolated address-layer Pelias results are usable for the final
  point-level analysis.

Nothing in this register authorizes HOLDOUT, Stage 7 acceptance or independent
review, Stage 8, geocoding, or production Stage 2 through Stage 7. D023
authorizes only its stated revised Stage 7 DEVELOPMENT design diagnostic.
