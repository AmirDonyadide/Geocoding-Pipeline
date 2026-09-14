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
- **IMPLEMENTATION READY — NOT EXECUTED:** the reviewed design is implemented
  and synthetic/local gates pass; protected execution still requires separate
  explicit authorization.
- **PLANNED — NOT STARTED:** conceptual placement and likely technology only.
  No accepted design or implementation exists.

Stages 0–9 are accepted on DEVELOPMENT. Stage 7's frozen v1 contract completed
authoritative DEVELOPMENT parsing and machine validation, but the candidate
was not ready for semantic handoff: qualitative and targeted root-cause
evidence found material libpostal label/boundary errors. A frozen evidence-only
v2 preserves the
immutable v1 raw evidence and adds trusted-country applicability plus
deterministic structural warnings. Optimized audit job `1763358` found that
the former warning rule catches all six known boundary failures but cannot establish
semantic label truth. The frozen rule subsequently failed its fresh 240-case
DEVELOPMENT validation: READY precision, clear-misparse leakage, and usable
abstention all missed their predeclared thresholds. It is retained only as
warning-feature history; evidence-only v2 publishes no semantic readiness
gate. Its 51,779-row DEVELOPMENT projection and independent reopen validation
passed in job `1763516`. The first independent review found only stale status
and downstream-contract documentation. Corrected candidate
`656a16d3d1f33cb152ace557c26f42df047bc7d6` then passed independent rereview
job `1763656` and is accepted as `STAGE_7_ACCEPTED`. Acceptance preserves exact
evidence; it does not establish semantic component correctness, geographic
truth, or trust from warning absence. Stage 8 DEVELOPMENT job `1763747`
completed from exact executable
`a2544401b4b699f6c020970f3507a2ae432746c5`. Independent review rejected exact
reporting candidate `adde81d2237e99993222994ce56efb0d74f7c2d3` for a
publication terminal-state defect and stale Stage 8/Stage 9 technology wording.
The bounded repair is executable
`bd89a032eb6fcf16a7515e0bd2991165d87246b1`. Repaired DEVELOPMENT job
`1763984` passed exact scientific reconciliation and the first corrected
terminal-publication flow for executable `bd89a032…`. Independent rereview
then failed reporting candidate `fdf2f8c…` because a rename could take effect
and subsequently raise before Python-side state changed, leaving a successful
final tree while reporting failure. Second repair executable `bdea7232…`
reconciles both paths by captured filesystem identity and adopts final-only
state only after parent fsync plus complete published reopen validation.
Authorized job `1764219` published manifest `346ea27a…` and the unchanged
logical dataset `9c9d431c…`; all frozen validators and ordinary-path
publication checks passed. Independent rereview then failed candidate
`70e3de95…` because a post-commit stdout exception produced a nonzero exit and
because policy-A ownership was not rechecked after parent fsync/final reopen.
Third repair executable `c04cb972…` separates publication and presentation
status and ends publication with a final no-follow identity check. Authorized
job `1764273` published manifest `2a50bd8c…` and the unchanged logical dataset
`9c9d431c…`; every frozen scientific and v3 terminal-publication check passed.
Exact candidate `231cdbf9db755fb56486c46b3b3faa02f5b5f3b6` then passed
corrected independent rereview commit `f8a456f…` and Goethe job `1764376` with
zero candidate defects and zero infrastructure-incomplete checks. The owner
accepted it as `STAGE_8_ACCEPTED`; Stage 8 science remained unchanged through
all publication remediations.
Jobs `1763747`, `1763984`, and `1764219` remain immutable historical evidence for
their exact executables and cannot validate the accepted executable.
Production Stage 0 and Stage 1 are accepted for the 1,411-file population;
production Stage 2 through Stage 6 have not started. The old Stages 8–19 have
not started. The first three compact replacement Stage 8 DEVELOPMENT
candidates remain rejected and immutable; the third-remediation candidate is
accepted on DEVELOPMENT. Stage 9 has an owner-approved, reference-frozen design;
its separately authorized implementation/local tests are complete and one
controlled DEVELOPMENT job `1770156` failed in the synthetic filesystem preflight,
before protected input access. After the approved PanFS publication repair,
corrected job `1771191` passed; independent review `a9ae443c…` / job `1772139`
passed with zero candidate defects. D060 records `STAGE_9_ACCEPTED`, with no
scientific change or rerun. Replacement Stages 10–14 remain
proposed and not started. Production Stage 7 and Stage 8 have not started.

## Cross-stage scientific rules

- Raw source values are immutable; transformations add derived fields.
- `stable_source_row_id_v1` and source provenance persist unchanged.
- Source rows are never deduplicated away. Candidate/query deduplication retains
  a complete source-row map-back.
- Postal codes remain strings; Unicode and native scripts are preserved.
- Standard and native Orbis representations remain separate candidates.
- All source lines are not blindly concatenated.
- Transliteration, if later approved, is a separate derived candidate.
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

Stages 8 and 9 are accepted on DEVELOPMENT. Stage 9's scientific design and
public references remain frozen; Stages 10–14 remain proposed, not an accepted execution
order. Every stage still requires its
own design, owner
authorization, DEVELOPMENT evidence, independent review, acceptance, and stop
gate. The current prohibition on geocoding before the governing pre-geocoding
acceptance gate remains in force.

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
  standard/native non-empty-line arrays and counts.
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
- **Status:**
  **`STAGE_7_ACCEPTED`** on DEVELOPMENT.
  Historical authoritative v1 job
  `1760221` produced all 51,779 rows and machine validation/map-back passed,
  but the 120-case qualitative review found 11 clear misparses. Targeted job
  `1760818` confirmed 14/18 investigated cases have genuine libpostal label or
  boundary errors and selected conclusion
  `MIXED_ROOT_CAUSES_REQUIRING_TARGETED_STAGE07_DESIGN_CHANGE`. Country-aware
  stabilization treats libpostal's documented worldwide scope separately from
  semantic quality and keeps applicability, technical success, structural
  readiness, and semantic quality as separate concepts. The DeepParse path is
  closed as `DEEPPARSE_INFRASTRUCTURE_PATH_NOT_JUSTIFIED`. Optimized bounded
  v2 audit job `1763358` caught all six known boundary failures, but one of five
  label-only clear failures remained structurally ready. Fresh blinded
  validation of the frozen 240-case selection then produced 85/100 usable
  assessable READY cases, 10 clear misparses in READY, and 63/148 usable parses
  abstained. Those results fail the predeclared rule gates; they are validation
  evidence, not population-wide libpostal accuracy estimates. Controlling v2
  contract `stage07_parser_evidence_contract_v2` therefore removes
  `COMPONENTS_READY`/`COMPONENTS_ABSTAIN` and treats structural reasons as
  warnings only. Evidence-only job `1763516` projected and independently
  reopened all 51,779 candidates with exact v1 preservation, complete
  69,747-occurrence map-back, and zero parser/trust claims. Independent rereview
  job `1763656` passed against exact candidate `656a16d3…`; the authoritative
  [Stage 7 report](../reports/development/stage07.md) consolidates that rereview
  without merging the review harness branch.
- **Acceptance requirement:** Pinned build/resources, reproducible offline
  execution, trusted pre-parse applicability, multilingual DEVELOPMENT
  evaluation on eligible populations, exact raw preservation, deterministic
  structural warnings without trust claims, complete map-back, and independent
  rereview. These requirements are satisfied for DEVELOPMENT only. Stage 7
  does not guarantee semantic component correctness or geographic truth, and
  structural warning absence provides no trust guarantee.

## Replacement Stages 8–14

This compact evidence-first architecture separates source truth,
parser/reference evidence, hypotheses, geocoder results, and the final accepted
match. The first three Stage 8 candidates are rejected. The third-remediation
candidate from job `1764273` passed corrected independent rereview job
`1764376` with zero candidate defects and is accepted as `STAGE_8_ACCEPTED`.
Stage 9 is **`STAGE_9_ACCEPTED`**, exact executable `3e10ac7c…`, DEVELOPMENT
job `1771191`, independent review `a9ae443c…` / job `1772139`, zero candidate
defects. Historical job `1770156` failed before materializer invocation and
remains preserved. D060 grants acceptance, not another execution.
Stages 10–14 remain **PROPOSED — NOT STARTED**.
Their responsibilities, tool
choices, and legacy mapping are maintained in this pipeline specification; the
accepted transition boundary is summarized in the authoritative
[Stage 8 report](../reports/development/stage08.md).

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
- **Status:**
  **`STAGE_8_ACCEPTED`** on DEVELOPMENT.
  Job `1763747` completed at old executable
  `a2544401b4b699f6c020970f3507a2ae432746c5` and remains immutable historical
  evidence after independent-review failure. Publication repair executable
  `bd89a032eb6fcf16a7515e0bd2991165d87246b1` completed repaired job `1763984`
  with manifest `d521240b…` and exact reconciliation, but independent rereview
  found the post-effect rename hole. Second repair `bdea7232…` completed
  authorized job `1764219` with manifest `346ea27a…`, unchanged logical
  dataset `9c9d431c…`, and exact ordinary-path publication reconciliation, but
  independent rereview found the post-commit CLI-status and missing final-
  ownership-recheck defects. Third repair executable `c04cb972…` closes only
  those terminal defects. Authorized job `1764273` published manifest
  `2a50bd8c…`, the unchanged logical dataset `9c9d431c…`, and exact scientific
  and v3 terminal-publication reconciliation. Corrected independent rereview
  commit `f8a456f…` and job `1764376` passed with zero candidate defects.
  Review-only RH-001 remains distinct from candidate history. The complete
  concise lineage is in the authoritative
  [Stage 8 report](../reports/development/stage08.md), with structured evidence
  in its [JSON summary](../reports/generated/stage08.json). The detailed stage
  contract remains in the
  [Stage 8 record](stages/STAGE08_ADDRESS_EVIDENCE_PROJECTION.md). The
  pre-Stage-9 baseline remains frozen; later Stage 9 activity is recorded separately below.

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
- **Status:** **`STAGE_9_ACCEPTED`** (2026-09-14, D060), tag
  `stage09-offline-reference-evidence-v1`. The following chronology preserves
  the design, implementation and publication-compatibility history.
  Separately authorized implementation/local validation completed; one controlled DEVELOPMENT
  job `1770156` failed in the synthetic atomic-rename preflight, before public-pack
  construction or protected input access. That historical job produced no candidate.
  The separately authorized synthetic-only diagnostic `1771054` completed:
  fresh-target no-replace rename returned EINVAL, while ordinary-rename baselines
  succeeded. Collision preservation and directory fsync checks passed. The
  publication compatibility blocker then required owner review before correction.
  Neither diagnostic alone authorized a DEVELOPMENT retry or fallback.
  A separately authorized design/local-only
  [publication revision candidate](stages/STAGE09_PUBLICATION_PROTOCOL_REVISION.md)
  proposed exclusive run reservation and a zero-byte commit seal; a tests-only
  model exercised its fault/recovery rules. The owner's conditional review
  required one separately authorized synthetic PanFS exclusive-create diagnostic
  before integration. No active materializer/DEVELOPMENT launcher change or
  DEVELOPMENT retry was authorized by that diagnostic alone.
  Diagnostic `1771149` completed with all ten required PanFS cases passing,
  including three four-process single-winner races. The capability gate is met;
  subsequent owner decision D058 authorizes integration and exactly one corrected
  DEVELOPMENT retry after complete local/fault validation. Stage 9 now uses the
  permanent reservation / exclusive `_COMMITTED` seal protocol in both public-pack
  and candidate publication. No active publication path or corrected preflight
  requires no-replace rename. This integration alone did not grant acceptance.
  Corrected job `1771191`, executable `3e10ac7c1309c2636f35c0709fa283305d60d998`,
  was submitted once, initially PENDING (Resources), then completed on 2026-09-12
  with exit `0:0`. Full in-job validation/reopening and sanitized reconciliation
  passed: 51,779 candidates, 6,565,329 evidence rows, zero GeoNames contradictions,
  zero technical failures. D059 recorded **DEVELOPMENT CANDIDATE READY — NOT ACCEPTED**.
  The report retains high conditional format-conflict rates and all unresolved
  country assessments as review diagnostics, not address-validity claims.
  No second corrected run was submitted. Independent review
  `a9ae443ca140627acf1712886670f39f227c1dc6` / job `1772139` subsequently passed
  100 artifact checks, 836 candidate tests and 23 additional public/synthetic
  checks with zero candidate defects. D060 records final owner acceptance;
  no scientific output change or DEVELOPMENT rerun was required. Q04
  54,022 / 90,043 = 59.995780% is a conditional reference-rule conflict rate,
  not address invalidity. Parser repetition can materially weight evidence-row
  denominators. Country assessment gives no resolving signal under the frozen
  full-subdivision-witness rule; other Stage 9 evidence remains usable.
  The complete design contract is the
  [Stage 9 design](stages/STAGE09_OFFLINE_REFERENCE_EVIDENCE.md). No Stage 0–8
  change is required; the Stage 10 boundary handoff is sufficient through the
  accepted Stage 8 → Stage 6 map-back. Stage 8 remains the sole source/occurrence
  mapping authority. The new [implementation record](stages/STAGE09_IMPLEMENTATION.md)
  and [execution report](../reports/development/stage09.md) describe the bounded
  owner authorization and accepted identity. Stop at `STAGE_9_ACCEPTED`; no
  Stage 10 design/implementation, rerun or geocoding is authorized by acceptance.
  The accepted Stage 9 reservation → immutable validated artifact → registration
  → exclusive `_COMMITTED` seal → full reopen protocol uses the demonstrated
  `O_CREAT|O_EXCL` primitive (PanFS job `1771149`). Reuse in Stages 10+ requires
  checking the same assumptions/path/filesystem; Stage 8 semantics are unchanged.

### Stage 10 — Multi-hypothesis query-plan generation

- **Purpose:** Generate bounded deterministic whole-string and evidence-backed
  structured hypotheses while keeping source truth immutable.
- **Primary tools:** SAFE rules plus accepted Stages 8–9 evidence.
- **Acceptance:** Explicit hypothesis identity/type/reason, complete map-back,
  no overwrite, multilingual review, and bounded query ladders.
- **Status:** **PROPOSED — NOT STARTED**.

### Stage 11 — Global query identity, deduplication, and workload QA

- **Purpose:** Execute identical endpoint/parameter queries once, retain every
  hypothesis/source map-back, and freeze a separately authorizable workload.
- **Primary tools:** DuckDB, PyArrow/Parquet, hashing; Polars optional.
- **Acceptance:** Canonical key/collision contract, exact totality/map-back,
  privacy, bounded resources/concurrency, and explicit pre-geocoding approval.
- **Status:** **PROPOSED — NOT STARTED**.

### Stage 12 — Self-hosted SAFE Pelias top-N retrieval

- **Purpose:** Execute only an accepted, separately authorized Stage 11
  workload and retain top-N results plus complete request/response provenance.
  The first result is not final truth.
- **Primary tool:** self-hosted SAFE Pelias, with total normal concurrency 2–4.
- **Acceptance:** Exact workload identity, privacy/authentication, bounded
  retries, complete results/errors, and no implicit match acceptance.
- **Status:** **PROPOSED — NOT STARTED; NOT AUTHORIZED**.

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
historical planning context and is proposed for replacement by compact Stages
8–14 above. Its scientific safeguards—losslessness, bounded matching,
absence-not-invalidity, query deduplication, and explicit review—remain inputs
to the replacement design.

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

No geocoding is authorized by the proposed renumbering. Under the current
repository rule, geocoding begins only after Stage 19 acceptance and a separate
exact-workload authorization. If compact Stages 8–14 are later approved, that
execution rule must be deliberately reconciled before proposed Stage 12 can
run. Total normal concurrency remains 2–4 requests across the complete
process. Top-N features must be retained and evaluated using independent
agreement, layer, match type, accuracy, and contradictions; confidence and
rank alone are insufficient.
