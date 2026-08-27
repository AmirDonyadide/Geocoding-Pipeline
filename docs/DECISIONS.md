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
- **Status:** LOCKED. Stage 4 is NOT STARTED.

### D009 — Reconstruction precedes parsing

- **Scope:** Stages 5–7
- **Decision:** Reconstruct standard/native candidates before libpostal parsing;
  do not parse isolated lines and infer a complete address without the approved
  reconstruction layer.
- **Rationale:** Parsing needs a reviewed candidate boundary and line-use
  provenance.
- **Status:** LOCKED sequence; stage designs remain future work.

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
  Stage 2 and Stage 3 are not started.
- **Rationale:** Distinguish current production scope from frozen Benchmark V1.
- **Status:** LOCKED current state.

### D014 — Planned technology sequence

- **Scope:** Stages 0–19
- **Decision:** Current planned choices are those in [PIPELINE.md](PIPELINE.md):
  PyArrow/Parquet and DuckDB for ingestion; `unicodedata`/ftfy/Arrow for safe
  cleaning; Unicode `lower()` for Stage 4; DuckDB/Polars/hashing for
  deduplication; libpostal for parsing/mapping; pycountry;
  google-i18n-address; pinned direct GeoNames postal data; local Overture Maps
  Addresses GeoParquet with optional OSM fallback; RapidFuzz after blocking;
  and SAFE evidence/selection/query layers.
- **Rationale:** Library-first offline processing under reproducible privacy
  controls.
- **Status:** Locked as current direction, not as implementation approval for
  Stages 4–19. pgeocode is proof-of-concept only. Pandas is inspection-only.

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

## Open decisions

These questions require future stage designs and explicit approval:

- exact Stage 4 lowercase schema, metadata, and acceptance gates;
- Stage 5 reconstruction rules and whether address-format metadata is needed;
- libpostal build/resource pinning and Stage 7 evaluation design;
- country-specific Stage 11 coverage and syntax policy;
- reference versions/licenses and blocking semantics for Stages 13–15;
- exact high-precision correction policy for Stage 16;
- Stage 17 component inclusion/omission policy;
- Stage 18 controlled query ladder; and
- whether interpolated address-layer Pelias results are usable for the final
  point-level analysis.

Nothing in this register resolves those questions or authorizes Stage 4.
