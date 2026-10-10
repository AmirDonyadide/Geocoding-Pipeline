# SAFE pre-geocoding pipeline

## Scope and status

This is the authoritative conceptual specification for the library-first
preprocessing pipeline before self-hosted SAFE Pelias. It states accepted
boundaries and planned direction; it is not permission to implement or run a
stage.

- **ACCEPTED:** implemented, evaluated, independently reviewed, and frozen on
  DEVELOPMENT.
- **DESIGN READY — NOT IMPLEMENTED:** prospective scientific contract is
  complete; implementation and execution still require explicit authorization.
- **DESIGN FROZEN — NOT IMPLEMENTED:** owner-approved scientific architecture
  and decision process are frozen; gated empirical parameters and separate
  implementation/execution authorization remain required.
- **IMPLEMENTATION READY — NOT EXECUTED:** the reviewed design is implemented
  and synthetic/local gates pass; protected execution still requires separate
  explicit authorization.
- **PLANNED — NOT STARTED:** conceptual placement and likely technology only.
  No accepted design or implementation exists.

Stages 0–11 are accepted and frozen on DEVELOPMENT. Stage 10
[owner acceptance](../reports/development/stage10.md), 2026-10-03, binds final
split-workspace candidate **1785683** after independent rereview **1786959**:
281 checks PASS, zero candidate defects. C01/C02, full publication, durable
checkpoints and three scientific replays pass. Operating budget remains
**UNSELECTED**. Historical candidate `1774362` failed review on Q4 provenance
and publication naming; remediation `1781277` failed before registration/commit.
Their [remediation](stages/STAGE10_REVIEW_REMEDIATION.md),
[forensic](stages/STAGE10_PUBLICATION_FORENSICS.md) and earlier timeout/performance
evidence remain preserved. Historical F01's exception remains unresolved.
Stage 11 [owner acceptance](stages/STAGE11_OWNER_ACCEPTANCE.md), 2026-10-08,
freezes job 1788751 after independent review 1790315: 124 checks PASS, zero defects.
Stage 12's design is [OWNER FROZEN](stages/STAGE12_DESIGN_FREEZE.md), with
implementation/execution not started; Stages 13–14 remain unstarted proposals.
Production Stages 0–1 are accepted for the
1,411-file population; production Stage 2 onward has not started.

Use [current progress](DEVELOPMENT_PROGRESS.md) for status and the
[stage reports](../reports/development/README.md) for exact execution/review
identities and rejected attempts. Frozen design documents retain their original
status wording; later authorization and execution records do not alter their
scientific bytes.

## Cross-stage scientific rules

- Raw source values are immutable; transformations add derived fields.
- `stable_source_row_id_v1` and source provenance persist unchanged.
- Source rows are never deduplicated away. Candidate/query deduplication retains
  a complete source-row map-back.
- Postal codes remain strings; Unicode and native scripts are preserved.
- Standard and native Orbis representations remain separate candidates.
- All source lines are not blindly concatenated.
- Stage 10 transliteration is a separate derived hypothesis; native text
  remains exact.
- Absence from an open reference is not invalidity. `MISMATCH` requires strong
  positive contradictory evidence.
- Legacy/later-stage validation statuses are `CONFIRMED`, `MISMATCH`,
  `NOT_FOUND`, `AMBIGUOUS`, `UNSUPPORTED`, and `INVALID_FORMAT`. The accepted
  Stage 9 evidence contract uses its own four-state model below.
- Protected address values never leave controlled infrastructure.
- Pandas is not used for production transformations; it is permitted for small
  DEVELOPMENT inspection.

## Dependency flow

```text
0 -> 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7
                                  |
                                  v
8 evidence projection -> 9 reference evidence -> 10 hypotheses
                                                    |
                                                    v
11 query identity/QA -> 12 Pelias top-N -> 13 scoring -> 14 granularity/abstain
```

Stages 8–11 are accepted and frozen; Stage 12 DESIGN is frozen without
implementation or execution; Stages 13–14 remain proposed.
Each stage requires its own approved design,
authorized execution, DEVELOPMENT evidence, independent review and owner
acceptance, then stops. The [current geocoding gate](#current-safe-pelias-boundary)
remains in force.

## Stage 0 — Source inventory

- **Purpose:** Freeze the exact source population and establish parser, schema,
  count, anomaly, hash, and identity evidence without transforming rows.
- **Input:** Immutable source CSV scope plus the accepted Stage 0 inventory
  contract.
- **Output:** Population scope, file manifest, parser/schema evidence,
  scientific inventory fingerprints, and explicit diagnostics.
- **Primary libraries:** canonical Stage 0 scanner, Python `hashlib`, Python
  `csv`.
- **Data effect:** None. It reads and reports; it does not rewrite source data.
- **Status:** **ACCEPTED** on DEVELOPMENT and production. Production status is
  `NEW_STAGE0_1411_ACCEPTED` for 1,411 files and 141,048,582 rows.
- **Acceptance requirement:** Exact authorized path population, hashes, logical
  record counts, parser/schema outcome for every file, source immutability,
  protected permissions, sanitized reporting, and independent review.

## Stage 1 — Lossless ingestion

- **Purpose:** Convert logical CSV records into validated columnar storage while
  preserving every source value and adding stable provenance.
- **Input:** Accepted Stage 0 scope/manifest and immutable CSV files.
- **Output:** PyArrow/Parquet shards with 15 source strings plus provenance,
  including `stable_source_row_id_v1`; manifest, reconciliation, and logical
  fingerprint evidence.
- **Primary libraries:** PyArrow/Parquet and DuckDB. Python CSV behavior remains
  bound to the accepted source contract.
  Current Stage 1 code validates/adopts existing ingestion bundles; the
  historical conversion runner is removed.
- **Data effect:** Physical representation changes from CSV to Parquet; decoded
  source string values do not change.
- **Status:** **ACCEPTED** on DEVELOPMENT and production. Production status is
  `NEW_STAGE1_1411_ACCEPTED` for `production_population_1411_v1`.
- **Acceptance requirement:** Exact row/file reconciliation, no dropped or
  added rows, stable-ID integrity, exact source-value/semantic-digest checks,
  validated Parquet readback, immutable publication, and independent review.

## Stage 2 — Schema and provenance harmonization

- **Purpose:** Give the lossless Stage 1 records a stable preprocessing schema
  and passive address-structure indicators.
- **Input:** SHA-bound accepted Stage 1 data or Benchmark V1 DEVELOPMENT.
- **Output:** All 22 incoming Stage 1 fields unchanged plus four derived fields:
  standard/native nonempty-line presence flags and counts.
- **Primary libraries:** PyArrow and the SAFE schema/provenance layer.
- **Data effect:** Adds structural/provenance columns only. It does not trim,
  normalize, parse, compare, reconstruct, or alter source strings.
- **Status:** **ACCEPTED** on all 35,000 DEVELOPMENT rows. Production Stage 2 is
  **NOT STARTED**.
- **Acceptance requirement:** Exact input binding, 35,000-to-35,000 row and
  identity equality, exact preservation of every incoming value, correct
  four-field derivation, protected review, sanitized evidence, and independent
  review.

## Stage 3 — Safe text cleaning

- **Purpose:** Repair only well-defined encoding, Unicode, control, and
  whitespace issues into auditable derived values.
- **Input:** Accepted Stage 2 values and identities.
- **Output:** Twelve `*_clean` fields, row/field changed indicators, and ordered
  cleaning-reason evidence while retaining all Stage 2 columns.
- **Primary libraries:** Python `unicodedata`, `ftfy`, regular-expression/Arrow
  operations, and conservative SAFE orchestration.
- **Data effect:** Adds derived clean text. Raw and Stage 2 fields are never
  overwritten. No lowercase, parsing, abbreviation, or semantic correction.
- **Status:** **ACCEPTED** on all 35,000 DEVELOPMENT rows at integration commit
  `958dddc8a9769977453ea5588e6861b62162090a`. Production Stage 3 is
  **NOT STARTED**.
- **Acceptance requirement:** Exact incoming-column and identity preservation,
  exact v1/v2 clean-value and ordered-reason equality, idempotence, bounded
  memory, huge-value safety, corrected punctuation evidence, fixed-500 review,
  and independent review. The rejected v1 commits remain in ancestry.

## Stage 4 — Lowercase canonical forms

- **Purpose:** Create derived lowercase canonical text after safe cleaning.
- **Input:** Accepted Stage 3 clean values.
- **Output:** Twelve `stage04_lower_*` fields paired with their preserved raw
  and Stage 3 clean values, plus ordered changed-field and row-changed audit
  evidence.
- **Primary libraries:** Python Unicode `lower()`.
- **Data effect:** Derived text only; never overwrite raw, Stage 2, or Stage 3
  text. Exact Python 3.14.3 / Unicode 16.0.0 `str.lower()` is authoritative;
  there is no casefold, locale-specific casing, or normalization after lower.
- **Status:** **`STAGE_4_ACCEPTED`** on DEVELOPMENT. Production Stage 4 is
  **NOT STARTED**.
- **Acceptance requirement:** Exact accepted Stage 3 input binding, Unicode
  behavior, value provenance, idempotence, complete 35,000-row DEVELOPMENT
  metrics, same fixed-500 review, sanitized reporting, and independent
  acceptance. See the [Stage 4 record](stages/STAGE04_LOWERCASE_CANONICAL.md).

## Stage 5 — Address reconstruction

- **Purpose:** Reconstruct coherent address candidates without assuming fixed
  semantics for lines 1–4.
- **Input:** Accepted Stage 3 clean and Stage 4 lowercase standard/native
  address-line fields plus all preserved provenance.
- **Output:** Separate clean and lowercase standard/native line-body candidates
  plus availability, contributing-line count, and four-position occupancy mask.
- **Primary libraries:** Small SAFE reconstruction logic within bounded
  PyArrow/Parquet processing. Address-format metadata is intentionally deferred.
- **Data effect:** Appends ten derived fields; no source or upstream overwrite.
- **Status:** **`STAGE_5_ACCEPTED`** on DEVELOPMENT after independent job
  `1759692` and the bound 179-row human qualitative review.
- **Acceptance requirement:** Approved reconstruction rules, country/script
  coverage evidence, no blind concatenation, complete lineage, DEVELOPMENT and
  fixed-500 review, and independent acceptance. The exact rule and boundary are
  in the [Stage 5 record](stages/STAGE05_ADDRESS_RECONSTRUCTION.md).

## Stage 6 — Early exact deduplication

- **Purpose:** Remove duplicate candidate work before parsing while preserving
  every source relationship.
- **Input:** Accepted Stage 5 candidate representations.
- **Output:** A 35,000-row Stage 5-preserving row map with nullable STANDARD and
  NATIVE exact candidate IDs, plus an exact unique lowercase candidate registry
  with total and representation occurrence counts.
- **Primary libraries:** PyArrow/Parquet, DuckDB, and Python `hashlib`.
- **Data effect:** Exact candidate work is deduplicated globally across
  representations; source rows and representation occurrences are never
  discarded.
- **Status:** **`STAGE_6_ACCEPTED`** on DEVELOPMENT. Authoritative job
  `1759819` and independent job `1760055` verified 35,000 → 35,000 and 69,747
  occurrences → 51,779 unique candidates with zero reconciliation, map-back,
  collision, or fixed-500 mismatches. Production is not started.
- **Acceptance requirement:** Canonical serialization and collision design,
  deterministic keys, one-to-many map-back integrity, reconciled counts, and
  independent review. See the
  [Stage 6 record](stages/STAGE06_EARLY_EXACT_DEDUPLICATION.md).

## Stage 7 — libpostal parsing

- **Purpose:** Preserve exact candidate/parser evidence, decide trusted-country
  applicability, and attach deterministic parser-local structural warnings.
  The parser is evidence, not postal truth.
- **Input:** Accepted unique Stage 6 candidates.
- **Output:** Versioned exact ordered libpostal labels/values, applicability and
  technical statuses, parser provenance, non-semantic structural-warning
  evidence, and complete candidate/occurrence map-back.
- **Primary libraries:** libpostal/pypostal.
- **Data effect:** Adds derived parsed components; candidate text is preserved.
- **Status:** **`STAGE_7_ACCEPTED`** on DEVELOPMENT under
  `stage07_parser_evidence_contract_v2`. V2 preserves immutable v1 parser
  output without new parser calls. Its structural signals are warnings only;
  `COMPONENTS_READY` / `COMPONENTS_ABSTAIN` failed fresh validation and are not
  published trust gates. DeepParse was closed without protected inference.
  See the [Stage 7 report](../reports/development/stage07.md) for the diagnostic
  and review history, denominators and exact accepted identities.
- **Acceptance requirement:** Pinned build/resources, reproducible offline
  execution, trusted pre-parse applicability, multilingual DEVELOPMENT
  evaluation on eligible populations, exact raw preservation, deterministic
  structural warnings without trust claims, complete map-back, and independent
  rereview. These requirements are satisfied for DEVELOPMENT only. Stage 7
  does not guarantee semantic component correctness or geographic truth, and
  structural warning absence provides no trust guarantee.

## Replacement Stages 8–14

These stages separate source truth, parser/reference evidence, hypotheses,
geocoder results and the final accepted match. Stages 8–11 are accepted and
frozen; Stage 12 DESIGN is frozen without implementation, and Stages 13–14
are unstarted.

### Stage 8 — Lossless address-evidence projection

- **Purpose:** Preserve the complete accepted Stage 7 row, expose a reversible
  ordered long-form parser-evidence index, and retain exact source-row and
  STANDARD/NATIVE map-back. A one-to-one SAFE parser-evidence name is a
  mechanical index, not a hypothesis or verified component. Raw order,
  duplicates, unknown labels, empty parses, country/applicability states, and
  structural warnings remain exact and separate.
- **Input/output grain:** Accepted Stage 7 v2 candidate evidence plus the
  accepted Stage 6 row map; linked candidate, component, and source-map
  relations plus a deterministic representation-occurrence view.
- **Primary tools:** PyArrow/Parquet and bounded DuckDB validation. No
  pycountry, libaddressinput, external reference, or Polars dependency in v1.
- **Acceptance:** Exact upstream preservation, nested/long reversibility,
  complete known/unmapped-label retention, complete map-back, deterministic
  fingerprints, bounded memory, privacy, and zero semantic-trust claims.
- **Status:** **`STAGE_8_ACCEPTED`** on DEVELOPMENT. Accepted job `1764273`
  and corrected independent review `1764376` established exact scientific and
  publication reconciliation. The three rejected candidates and review-only
  RH-001 remain in the [Stage 8 report](../reports/development/stage08.md).
  Publication repairs preserved the logical dataset. The
  [Stage 8 contract](stages/STAGE08_ADDRESS_EVIDENCE_PROJECTION.md) and
  [machine summary](../reports/generated/stage08.json) bind the exact evidence.

### Stage 9 — Offline geographic reference evidence

- **Purpose:** Add conservative offline country/postcode/locality/admin and
  format evidence only. Each check is SUPPORTED, CONTRADICTED, NOT_FOUND, or
  NOT_EVALUABLE; absence never silently becomes contradiction or invalidity.
- **Frozen design tools/data:** iso-codes 4.20.1-1 country/subdivision JSON, offline
  libaddressinput metadata, one frozen GeoNames postal snapshot, DuckDB and
  PyArrow. Actual metadata and postal snapshot hashes are in the
  [reference freeze](stages/STAGE09_REFERENCE_FREEZE.md). V1 excludes street/house-number references, fuzzy matching,
  corrections, queries, and coordinates. References carry per-country/question
  capabilities with separate positive/negative authority, concrete ISO_CODES /
  LIBADDRESSINPUT_METADATA / GEONAMES_POSTAL families, and explicit dependence
  lineage for later Pelias comparisons. GeoNames negative authority is FALSE.
- **Acceptance:** Reviewed design/implementation, frozen reference pack,
  authority-scoped contradictions, exact source/representation map-back,
  DEVELOPMENT diagnostics, independent review and explicit owner acceptance.
- **Status:** **`STAGE_9_ACCEPTED`** (D060), frozen by
  `stage09-offline-reference-evidence-v1`. Job `1771191` and independent review
  `1772139` passed with zero candidate defects; no acceptance rerun was needed.
  The [report](../reports/development/stage09.md) retains failed preflight
  `1770156`, filesystem diagnostics and exact artifact identities.
- **Interpretation:** Q04's 54,022 / 90,043 = 59.995780% conflict rate is
  conditional reference evidence, not address invalidity. Repeated parser
  components weight evidence-row denominators. Country assessments remain
  unresolved because the frozen full-subdivision-code witness rule found no
  qualifying source witnesses; other reference evidence remains available.
- **Handoff:** Stage 8 remains the sole source/occurrence mapping authority,
  with original line boundaries available through Stage 6. No duplicate source
  map or upstream change is required. See the
  [scientific contract](stages/STAGE09_OFFLINE_REFERENCE_EVIDENCE.md) and
  [implementation record](stages/STAGE09_IMPLEMENTATION.md).
- **Publication:** Permanent reservation → immutable validated artifact →
  registration → exclusive `_COMMITTED` seal → full reopen validation.
  PanFS diagnostic `1771149` demonstrated `O_CREAT|O_EXCL`; no-replace rename
  failed on the tested path. Reuse requires verifying the same controlled
  topology/filesystem assumptions. Stage 8 publication semantics stay unchanged.

### Stage 10 — Multi-hypothesis query-plan generation

- **Purpose:** Generate bounded deterministic whole-string and evidence-backed
  structured hypotheses while keeping source truth immutable.
- **Input authority:** Accepted Stage 8 evidence and sole source/occurrence map,
  accepted Stage 9 reference evidence/pack, and the exact Stage 6 row-map line
  projection bound by Stage 8. No duplicated source map.
- **Implemented contract:** Exact full STANDARD/NATIVE, source-boundary LF alternate,
  source-anchored structured, narrow unit/floor stripping and native Greek/Cyrillic
  transliteration. Generation uses one context per Stage 8 source/representation
  occurrence, with local source-country and boundaries. Q7 is globally deferred.
  Q1/Q2 are exclusive by role; Q5/Q6 can coexist. The exact context maximum is
  five; the accepted two-slot occurrence view proves at most two contexts/row.
  Uniform safety ceilings are five/context and ten/row (reachable role maximum
  nine/row). No fixed global
  candidate cap; first DEVELOPMENT materializes all eligible hypotheses. The
  scientific operating budget remains unselected for DEVELOPMENT calibration.
- **Primary tools:** SAFE rules, PyArrow/DuckDB and pinned ICU4C 77.1 for Q6.
  Q6 requires the separately locked runtime; system ICU is not a substitute.
- **Acceptance:** Explicit hypothesis identity/type/reason, complete map-back,
  no overwrite, multilingual review, and bounded query ladders.
- **Status:** **ACCEPTED / FROZEN** on DEVELOPMENT, owner decision 2026-10-03.
  The [acceptance record](../reports/development/stage10.md) binds executable
  `cf9e0fe4c12eb85f78051904c636ad084d87a541`, job `1785683` and final independent
  rereview `1786959`. C01/C02 are closed; scientific query contents are unchanged.
  Job-local transient storage and durable PanFS checkpoints/publication are
  accepted. Operating budget remains UNSELECTED. Historical candidate `1774362`,
  failed remediation `1781277`, original timeout `1772639` and their evidence
  remain unchanged. No new execution is authorized. The
  [frozen design](stages/STAGE10_MULTI_HYPOTHESIS_QUERY_GENERATION.md)
  and [implementation record](stages/STAGE10_IMPLEMENTATION.md) distinguish
  scientific rules, local evidence and execution status. Stage 10 acceptance
  itself grants no Stage 11 or geocoding authorization; D088 separately
  authorized Stage 11. Geocoding remains unauthorized.

### Stage 11 — Global query identity, deduplication, and workload QA

- **Purpose:** Globally deduplicate complete typed semantic search cores from
  all accepted Stage 10 hypotheses, retaining every hypothesis/source map-back.
  This is offline deduplication; Stage 11 executes no query.
- **Primary tools:** DuckDB, PyArrow/Parquet, hashing; Polars optional.
- **Acceptance:** Canonical key/collision contract, exact totality/map-back,
  privacy, bounded resources/concurrency, and explicit pre-geocoding approval.
- **Final design:** [Stage 11 contract and review package](stages/STAGE11_SEMANTIC_REQUEST_DEDUPLICATION.md),
  D087. Owner-approved architecture A puts result limit/retrieval policy,
  transport, concrete deployment/index and execution identity in Stage 12.
  The final 19-field core excludes retrieval and generic header fields;
  NO_REQUEST_LANGUAGE_OVERRIDE requires explicit Stage 12 binding of effective
  no-override behavior. No N, operating budget or Stage 19 gate change selected.
- **Status:** **STAGE_11_ACCEPTED — FROZEN**.
  [Owner acceptance and exact identities](stages/STAGE11_OWNER_ACCEPTANCE.md),
  D090; job 1788751, independent review 1790315, zero candidate defects.
  The historical [candidate report](../reports/development/stage11.md) is unchanged.
  Stage 12's subsequent frozen design is linked below; Stage 11 is unchanged.

### Stage 12 — Self-hosted SAFE Pelias top-N retrieval

- **Purpose:** Execute only an accepted, separately authorized Stage 11
  workload and retain top-N results plus complete request/response provenance.
  The first result is not final truth.
- **Primary tool:** self-hosted SAFE Pelias, with total normal concurrency 2–4.
- **Acceptance:** Exact workload identity, privacy/authentication, bounded
  retries, complete results/errors, and no implicit match acceptance.
- **Design:** [Owner-revised contract package](stages/STAGE12_PELIAS_TOPN_RETRIEVAL.md),
  frozen by [owner decision](stages/STAGE12_DESIGN_FREEZE.md), D093.
  Four relations, scientific network IDs separate from executable and
  offline response projection; full calibration C plus predeclared deep-tail
  subset T>C and T>10. Exact protected C/T await the public-capability owner
  gate; final operational N remains UNSELECTED. N!=C requires complete direct-N
  retrieval. Useful evidence beyond C forces insufficient-depth review.
- **Status:** **DESIGN FROZEN; IMPLEMENTATION AND EXECUTION NOT STARTED**.
  C, T and final N remain UNSELECTED. Separate phase/workload authority is required.

### Stage 13 — Result evidence scoring and cross-query convergence

- **Purpose:** Rank top-N features against trusted country, postcode,
  locality/admin, street, house number, representation agreement, independent
  references, parser evidence, contradictions, and query convergence.
- **Primary tools:** DuckDB, bounded RapidFuzz, SAFE scoring policy,
  Arrow/Parquet.
- **Acceptance:** Predeclared evidence/contradiction policy, deterministic
  ranking, DEVELOPMENT calibration/ablation, bias analysis, and review. No
  numeric weights are frozen here.
- **Status:** **PROPOSED — NOT STARTED**.

### Stage 14 — Final match, granularity, and abstention

- **Purpose:** Accept only the strongest evidence-supported granularity or
  return `UNRESOLVED`; a truthful postcode/locality result is preferable to a
  false rooftop point.
- **Output granularity:** `EXACT_ADDRESS`, `STREET_ADDRESS`, `STREET`,
  `POSTCODE`, `LOCALITY`, `ADMIN`, or `UNRESOLVED` plus coordinates, winning
  query/result, supporting/contradicting evidence, and fallback provenance.
- **Acceptance:** Predeclared granularity thresholds, high-precision
  DEVELOPMENT evidence, complete source-row lineage, and independent review.
- **Status:** **PROPOSED — NOT STARTED**.

## Legacy unstarted Stages 8–19 — superseded proposal

The following decomposition was never implemented. It is retained as
historical planning context. Compact Stages 8–11 above have since been accepted;
Stage 12 is design-only and Stages 13–14 remain proposals. The legacy safeguards remain:
losslessness, bounded matching, absence-not-invalidity, query deduplication and
explicit review.

### Legacy Stage 8 — Internal component mapping

- **Purpose:** Map libpostal output to a stable SAFE component schema.
- **Input:** Accepted Stage 7 labels and candidates.
- **Output:** SAFE component fields plus mapping and unresolved-label evidence.
- **Primary libraries:** libpostal output plus SAFE mapping.
- **Data effect:** Adds derived mapped components; parsed output remains intact.
- **Status:** **PLANNED — NOT STARTED**.
- **Acceptance requirement:** Versioned mapping, complete/unmapped label
  accounting, no silent component loss, DEVELOPMENT review, and acceptance.

### Legacy Stage 9 — Component-aware abbreviation and linguistic normalization

- **Purpose:** Normalize linguistic variants only when component, country,
  language, and script make the operation defensible.
- **Input:** Accepted Stage 8 components and representation metadata.
- **Output:** Derived normalized components with rule/resource evidence.
- **Primary libraries:** libpostal resources/dictionaries and SAFE
  component-aware policy.
- **Data effect:** Adds derived normalized components. Blind English rules on
  native text are prohibited.
- **Status:** **PLANNED — NOT STARTED**.
- **Acceptance requirement:** Pinned resources, component-scoped rules,
  multilingual error analysis, raw/mapped preservation, and independent review.

### Legacy Stage 10 — Country and subdivision normalization

- **Purpose:** Resolve recognized country/subdivision codes and names without
  inferring uncertain geography.
- **Input:** Accepted Stage 9 components and source geography.
- **Output:** Derived standardized geography plus ambiguity/unsupported status.
- **Primary libraries:** pycountry.
- **Data effect:** Adds derived geographic canonical forms; source values remain.
- **Status:** **PLANNED — NOT STARTED**.
- **Acceptance requirement:** Pinned version, code-system policy, ambiguity and
  historical-value handling, coverage metrics, and independent review.

### Legacy Stage 11 — Country-specific address and postcode syntax validation

- **Purpose:** Check component format against conservative country rules.
- **Input:** Accepted Stage 10 geography and normalized components.
- **Output:** Format evidence using the closed validation-status vocabulary.
- **Primary libraries:** google-i18n-address and conservative country rules.
- **Data effect:** Adds validation evidence; it does not correct values.
- **Status:** **PLANNED — NOT STARTED**.
- **Acceptance requirement:** Pinned rules, supported-country declaration,
  `INVALID_FORMAT` precision review, no absence-as-invalid inference, and
  independent acceptance.

### Legacy Stage 12 — Normalized/component-level deduplication

- **Purpose:** Collapse scientifically equivalent normalized candidates while
  preserving all representations and source mappings.
- **Input:** Accepted Stages 9–11 components and evidence.
- **Output:** Versioned normalized keys, unique component candidates, and full
  map-back tables.
- **Primary libraries:** DuckDB, Polars, and hashing.
- **Data effect:** Deduplicates candidate representations, never source rows.
- **Status:** **PLANNED — NOT STARTED**.
- **Acceptance requirement:** Key contract and collision tests, map-back and row
  reconciliation, evidence retention, and independent acceptance.

### Legacy Stage 13 — Geographic cross-validation

- **Purpose:** Evaluate postcode/country/locality/region agreement using pinned
  independent reference evidence.
- **Input:** Accepted Stage 12 components and normalized geography.
- **Output:** Component-level evidence and closed validation statuses.
- **Primary libraries:** pinned direct GeoNames postal reference data and
  DuckDB; pgeocode is optional proof-of-concept only.
- **Data effect:** Adds evidence; no correction or invalidation by absence.
- **Status:** **PLANNED — NOT STARTED**.
- **Acceptance requirement:** Approved download/license/vintage and pinning,
  ambiguity semantics, strong-positive-evidence definition for `MISMATCH`,
  coverage/bias evaluation, and independent acceptance.

### Legacy Stage 14 — Street and house-number validation

- **Purpose:** Seek positive evidence that street, house number, and geography
  coexist plausibly.
- **Input:** Accepted Stage 13 candidates and geographic blocking context.
- **Output:** Street/house-number evidence with ambiguity and coverage status.
- **Primary libraries:** Overture Maps Addresses, local GeoParquet, and DuckDB;
  optional OSM fallback.
- **Data effect:** Adds evidence; absence is not invalidity.
- **Status:** **PLANNED — NOT STARTED**.
- **Acceptance requirement:** Approved spatial source/license/vintage, local
  protected execution, precision-focused joins, coverage caveats, and review.

### Legacy Stage 15 — Constrained fuzzy matching

- **Purpose:** Compare plausible variants only inside strong geographic blocks.
- **Input:** Accepted Stage 14 candidates and blocking evidence.
- **Output:** Similarity evidence and bounded candidate sets.
- **Primary libraries:** RapidFuzz after geographic blocking.
- **Data effect:** Adds comparison evidence; no global fuzzy correction.
- **Status:** **PLANNED — NOT STARTED**.
- **Acceptance requirement:** Approved blocking and thresholds, false-positive
  analysis across countries/scripts, bounded candidate counts, and review.

### Legacy Stage 16 — Conservative correction

- **Purpose:** Accept only high-precision correction proposals supported by
  multiple compatible evidence sources.
- **Input:** Accepted validation and fuzzy evidence from Stages 11–15.
- **Output:** Original value, proposal, evidence, reference/version, decision,
  and corrected candidate where accepted.
- **Primary libraries:** SAFE high-precision evidence/correction engine.
- **Data effect:** Adds separate corrected candidates; originals remain intact.
- **Status:** **PLANNED — NOT STARTED**.
- **Acceptance requirement:** Explicit correction policy and abstention rules,
  precision evaluation, contradiction safeguards, qualitative review, and
  independent acceptance.

### Legacy Stage 17 — Geocoding-component selection

- **Purpose:** Choose components appropriate for point-level geocoding while
  avoiding recipient/person/floor/unit noise unless justified.
- **Input:** Accepted original and corrected candidate components plus evidence.
- **Output:** Versioned selected geocoding components and exclusion reasons.
- **Primary libraries:** SAFE geocoding-component selection.
- **Data effect:** Creates query-ready views; it does not alter prior candidates.
- **Status:** **PLANNED — NOT STARTED**.
- **Acceptance requirement:** Approved inclusion/omission policy, country and
  representation analysis, traceability, and independent review.

### Legacy Stage 18 — Query generation

- **Purpose:** Generate a small deterministic query plan for self-hosted SAFE
  Pelias.
- **Input:** Accepted Stage 17 components and representation/evidence lineage.
- **Output:** Separate standard/native primary and controlled alternative
  queries with versioned reasons.
- **Primary libraries:** SAFE query generation.
- **Data effect:** Adds query representations; source/candidate data is retained.
- **Status:** **PLANNED — NOT STARTED**.
- **Acceptance requirement:** Approved structured-field policy and bounded query
  ladder, privacy/authentication review, exact logging contract, and review
  before any geocoder workload.

### Legacy Stage 19 — Query deduplication and final QA

- **Purpose:** Execute identical queries once, verify final workload integrity,
  and preserve complete result map-back.
- **Input:** Accepted Stage 18 query plans.
- **Output:** Unique query identities, source/candidate/query maps, final QA
  report, and separately authorizable SAFE workload.
- **Primary libraries:** DuckDB, Polars, PyArrow, and hashing.
- **Data effect:** Deduplicates query representations, never source records.
- **Status:** **PLANNED — NOT STARTED**.
- **Acceptance requirement:** Query-key/collision contract, exact map-back and
  counts, no protected leakage, reviewed concurrency/workload plan, and
  explicit acceptance before geocoding.

## Current SAFE Pelias boundary

Owner-directed D092 resolves the old Stage 19 reference as **stale architecture
numbering**, not a typo or genuine later-stage dependency. Legacy Stage 19
performed query deduplication/final QA; accepted Stage 11 now supplies semantic
identity/map-back QA and Stage 12 owns executable/deployment/workload QA.
Historical records remain intact.

The active gate is accepted Stages 0–11, owner-frozen Stage 12 design, validated
implementation and separate phase-specific exact-workload authorization.
The public/synthetic probe needs explicit authority; protected calibration
additionally needs the post-probe owner deployment/auth/operations/C/T freeze,
offline preflight and exact workload approval. No Stage 13 dependency or
implementation is introduced. This correction grants no current execution.

The old size=1 preference cannot choose N or override accepted request modes.
Stage 12 freezes explicit result limits by approved policy; final N is selected
only from DEVELOPMENT evidence after a passing deeper-tail audit. Initial
service policy is two connections and one request/second; increases require
public/synthetic evidence and owner approval. Rank, confidence, match_type and
point geometry do not establish correctness or rooftop precision.
