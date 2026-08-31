# SAFE pre-geocoding pipeline

## Scope and status

This is the authoritative conceptual specification for the library-first
preprocessing pipeline before self-hosted SAFE Pelias. It states accepted
boundaries and planned direction; it is not permission to implement or run a
stage.

- **ACCEPTED:** implemented, evaluated, independently reviewed, and frozen on
  DEVELOPMENT.
- **PLANNED — NOT STARTED:** conceptual placement and likely technology only.
  No accepted design or implementation exists.

Stages 0–6 are accepted on DEVELOPMENT. Stage 7's frozen v1 contract completed
authoritative DEVELOPMENT parsing and machine validation, but the candidate
remains not ready: qualitative and targeted root-cause evidence found material
systematic libpostal label/boundary errors across multiple native non-Latin
strata. Parser applicability is now being audited from trusted country
provenance with parser-specific coverage denominators and a mandatory
prelaunch gate. No Stage 7 acceptance or Stage 8 handoff is authorized.
Production Stage 0 and Stage 1 are accepted for the 1,411-file population;
production Stage 2 through Stage 6 have not started. DEVELOPMENT and production
Stages 8–19 have not started, and production Stage 7 has not started.

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
- Validation statuses are `CONFIRMED`, `MISMATCH`, `NOT_FOUND`, `AMBIGUOUS`,
  `UNSUPPORTED`, and `INVALID_FORMAT`.
- Protected address values never leave controlled infrastructure.
- Pandas is not used for production transformations; it is permitted for small
  DEVELOPMENT inspection.

## Dependency flow

```text
0 -> 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10 -> 11
                                             |                 |
                                             +---------> 12 <-+
                                                         |
                                                         v
13 -> 14 -> 15 -> 16 -> 17 -> 18 -> 19 -> self-hosted SAFE Pelias
```

The linear stage numbers are the governing order. The diagram highlights that
component mapping and normalization feed later normalized deduplication. Every
stage consumes an accepted predecessor and must stop at its own review gate.

## Stage 0 — Source inventory

- **Purpose:** Freeze the exact source population and establish parser, schema,
  count, anomaly, hash, and identity evidence without transforming rows.
- **Input:** Immutable source CSV scope plus the accepted historical Phase 1
  inventory contract.
- **Output:** Population scope, file manifest, parser/schema evidence,
  scientific inventory fingerprints, and explicit diagnostics.
- **Primary libraries:** existing Phase 1 inventory, Python `hashlib`, Python
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

- **Purpose:** Parse standard and native reconstructed candidates into address
  components independently.
- **Input:** Accepted unique Stage 6 candidates.
- **Output:** Versioned libpostal labels, values, parse status, and evidence for
  each representation.
- **Primary libraries:** libpostal/pypostal.
- **Data effect:** Adds derived parsed components; candidate text is preserved.
- **Status:** **`STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY`**. Authoritative job
  `1760221` produced all 51,779 rows and machine validation/map-back passed,
  but the 120-case qualitative review found 11 clear misparses. Targeted job
  `1760818` confirmed 14/18 investigated cases have genuine libpostal label or
  boundary errors and selected conclusion
  `MIXED_ROOT_CAUSES_REQUIRING_TARGETED_STAGE07_DESIGN_CHANGE`. Country-aware
  stabilization treats libpostal's documented worldwide scope separately from
  DeepParse's exact 20-country training set, and keeps coverage, technical
  success, and semantic quality as separate denominators.
- **Acceptance requirement:** Pinned build/resources, reproducible offline
  execution, trusted pre-parse applicability, multilingual DEVELOPMENT
  evaluation on eligible populations, failure/abstention preservation,
  prelaunch gate, and independent review.

## Stage 8 — Internal component mapping

- **Purpose:** Map libpostal output to a stable SAFE component schema.
- **Input:** Accepted Stage 7 labels and candidates.
- **Output:** SAFE component fields plus mapping and unresolved-label evidence.
- **Primary libraries:** libpostal output plus SAFE mapping.
- **Data effect:** Adds derived mapped components; parsed output remains intact.
- **Status:** **PLANNED — NOT STARTED**.
- **Acceptance requirement:** Versioned mapping, complete/unmapped label
  accounting, no silent component loss, DEVELOPMENT review, and acceptance.

## Stage 9 — Component-aware abbreviation and linguistic normalization

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

## Stage 10 — Country and subdivision normalization

- **Purpose:** Resolve recognized country/subdivision codes and names without
  inferring uncertain geography.
- **Input:** Accepted Stage 9 components and source geography.
- **Output:** Derived standardized geography plus ambiguity/unsupported status.
- **Primary libraries:** pycountry.
- **Data effect:** Adds derived geographic canonical forms; source values remain.
- **Status:** **PLANNED — NOT STARTED**.
- **Acceptance requirement:** Pinned version, code-system policy, ambiguity and
  historical-value handling, coverage metrics, and independent review.

## Stage 11 — Country-specific address and postcode syntax validation

- **Purpose:** Check component format against conservative country rules.
- **Input:** Accepted Stage 10 geography and normalized components.
- **Output:** Format evidence using the closed validation-status vocabulary.
- **Primary libraries:** google-i18n-address and conservative country rules.
- **Data effect:** Adds validation evidence; it does not correct values.
- **Status:** **PLANNED — NOT STARTED**.
- **Acceptance requirement:** Pinned rules, supported-country declaration,
  `INVALID_FORMAT` precision review, no absence-as-invalid inference, and
  independent acceptance.

## Stage 12 — Normalized/component-level deduplication

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

## Stage 13 — Geographic cross-validation

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

## Stage 14 — Street and house-number validation

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

## Stage 15 — Constrained fuzzy matching

- **Purpose:** Compare plausible variants only inside strong geographic blocks.
- **Input:** Accepted Stage 14 candidates and blocking evidence.
- **Output:** Similarity evidence and bounded candidate sets.
- **Primary libraries:** RapidFuzz after geographic blocking.
- **Data effect:** Adds comparison evidence; no global fuzzy correction.
- **Status:** **PLANNED — NOT STARTED**.
- **Acceptance requirement:** Approved blocking and thresholds, false-positive
  analysis across countries/scripts, bounded candidate counts, and review.

## Stage 16 — Conservative correction

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

## Stage 17 — Geocoding-component selection

- **Purpose:** Choose components appropriate for point-level geocoding while
  avoiding recipient/person/floor/unit noise unless justified.
- **Input:** Accepted original and corrected candidate components plus evidence.
- **Output:** Versioned selected geocoding components and exclusion reasons.
- **Primary libraries:** SAFE geocoding-component selection.
- **Data effect:** Creates query-ready views; it does not alter prior candidates.
- **Status:** **PLANNED — NOT STARTED**.
- **Acceptance requirement:** Approved inclusion/omission policy, country and
  representation analysis, traceability, and independent review.

## Stage 18 — Query generation

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

## Stage 19 — Query deduplication and final QA

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

## SAFE Pelias boundary

Geocoding begins only after Stage 19 acceptance and a separate production
authorization. The preferred endpoint is `/v1/search/structured`, normally
with `size=1`. Credentials are protected runtime configuration. Total normal
concurrency is 2–4 requests across the entire process. A returned feature is
evaluated using layer, match type, input/output geographic agreement, and
contradictions; confidence alone is insufficient.
