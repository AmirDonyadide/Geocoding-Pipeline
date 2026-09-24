# Stage 10 independent review ledger

Protected review job **1780706 COMPLETED / 0:0**, elapsed **01:12:43**. All eight
protected review phases completed. Original evidence is preserved unchanged in
`evidence_1780706.json` (SHA-256
`4ba802155b27390d8a33b88891abf0cbf19657c6fe9106ab145ae1a4627b0fcf`).
Of 206 named checks, 202 passed. Three false checks establish C01/C02 below;
the fourth was reviewer defect R05. Guarded log-only verification **1781037
COMPLETED / 0:0**, elapsed **11 seconds**, resolved R05 with all 20 checks passing.
Combined evidence has **212 passing / 3 failing checks across 215 distinct
names**; the three failures map exactly to **two candidate defects**. The review
is complete and the candidate verdict is **FAIL**. Candidate code/artifact was
not repaired or modified here.

## Candidate defects

### C01 — Required visible parser-geography exclusion is absent

- Classification: **CANDIDATE_IMPLEMENTATION**; severity **moderate (P2)**.
- Invariant: frozen Q4 field provenance and visible exclusion decisions.
- Evidence: frozen `docs/stages/STAGE10_QUERY_FAMILIES.md`, Q4 policy, requires
  `PARSER_ONLY_FIELD_EXCLUDED` for parser geography exclusion. The executable's
  `s10_query_families._structured` never emits that code; `region` records only
  `ADMIN_LEVEL_NOT_ESTABLISHED`, and omitted country text has no parser exclusion
  reason. Searching the executable finds the name only in the reason vocabulary.
  Independent synthetic complete-oracle runs reproduce missing reasons in all
  four country-eligible fixture contexts, including contexts with parser geography.
- Effect: consumers cannot recover the required explicit exclusion decision from
  the field-decision relation. This is not evidence that parser values populate Q4
  or that source-anchored query content is incorrect.
- Protected checks: **68,079** country-eligible contexts lack the visible reason;
  **21,773** of these have actual parser geography. The reason occurs in **zero**
  Q4 field-decision arrays. The broader policy count is not the number with
  observed parser geography. Independent Q4 content, eligibility, field disposition
  and other operational-reason checks report **zero mismatches**.
- Regeneration: correcting decision rows requires a new immutable candidate
  relation/artifact and its dependent hashes. No in-place repair is permitted.
- Disposition: unresolved candidate defect, established in the exact artifact.

### C02 — Registration names differ from the frozen publication interface

- Classification: **CANDIDATE_PUBLICATION**; severity **moderate (P2)**.
- Invariant: frozen Stage 10 publication adapter namespace and complete input
  binding field, `STAGE10_MULTI_HYPOTHESIS_QUERY_GENERATION.md` publication section
  at design freeze `1443bb3b3c1bb50220bf38231e01552c66c4eaee`.
- Evidence: that section specifies namespace `STAGE10_DEVELOPMENT_QUERY_PLAN`
  and `stage10_input_binding_sha256`. Executable `s10_query_publication.py` uses
  `STAGE10_DEVELOPMENT_QUERY_HYPOTHESES` and `stage10_input_sha256`. The committed
  sanitized registration `stage10_development_registration_1774362.json` confirms
  both differences. No subsequent documented authorization changing these frozen
  names was found. Candidate validation accepts its own adapter constants and
  therefore does not detect this design/interface discrepancy.
- Effect: a consumer of the frozen adapter cannot match the namespace or retrieve
  the required key. The input digest is present under the different key; this
  finding alone does not establish lost input binding, unsafe sealing, corruption,
  or a stale reservation. Those checks passed independently.
- Protected checks: `publication_frozen_namespace` and
  `publication_frozen_input_binding_key` both fail on the exact controlled
  registration. Independent registration hash, manifest/input bindings, private
  physical inventory, commit seal and terminal reopen checks pass.
- Regeneration: requires owner disposition and a new conforming immutable
  registration/artifact. The names alone do not intrinsically require repeating
  scientific query construction, but the existing committed artifact cannot be
  edited or accepted as conforming by this reviewer.
- Disposition: unresolved candidate defect, established in the exact artifact.

## Informational ledger

| ID | Observation / invariant | Evidence / disposition | Severity; regeneration |
|---|---|---|---|
| I01 | Country abstention is structural, not invalidity | All 1668 contexts reconcile to the frozen row-local Q01 gate; all six slots are consistent; no country-eligible context lost and no emitted hypothesis lacks country context. | Informational; none |
| I02 | Q5 and Q6 coexistence is permitted, not required | Zero observed coexistence is not a defect. Independent eligibility and synthetic safety checks retain both families. | Informational; none |
| I03 | Q5 diagnostic evaluation order | Frozen reasons describe the actually evaluated failure. The possible ambiguous/uncorroborated overlap and diagnostic precedence differences both occur zero times; all Q5 eligibility/reason/safety checks reconcile. | Informational; none |
| I04 | Replays are deterministic reproducibility evidence | Three replay calls and four complete population passes reconcile to bound completion receipts; full unit/final contents are equal. Static exact-row comparison path and independent science oracles support the finding. No new replay requirement or substituted artifact. | Informational; none |
| I05 | Performance measurements have limited scope | Publication time contains replays; sampled WAL is not continuous high-water telemetry; DEVELOPMENT throughput does not establish production capacity. Candidate report states these limits. | Informational; none |
| I06 | Local runtime coverage limit | 24 local candidate tests were skipped for missing exact ICU assets. Goethe review validated the exact runtime/lock/dependencies and all Q6 outputs: 157 Greek + 2191 Cyrillic, one safely suppressed unsupported output. | Informational; none |
| I07 | Bounded independent witness certificate review | Fixed selection produced 28 distinct contexts and 924 certificate comparisons, zero differences. Full-population identifiers, contents, source-line certificates, reference policies and checkpoint equality checked separately. No claim of exhaustive independent reference-certificate reconstruction. | Informational; none |
| I08 | Reporting and budget interpretation | Report disclaims geocoding accuracy/validity/precision/recall; abstention and Stage 9 contradiction are not invalidity. Null budget, ALL_ELIGIBLE_CATALOG and zero budget suppression independently verified. | Informational; none |

## Review-harness defects

These are reviewer-created issues, never candidate defects. R01–R04 were resolved
before the first submission. R05 was found in its results and resolved by the
isolated follow-up below. All corrections are confined to review files.

| ID | Evidence / review invariant | Correction and validation | Severity; candidate regeneration |
|---|---|---|---|
| R01 | Prototype Python DuckDB UDF depended on unavailable local NumPy | Replaced with bounded Arrow batches; no environment modification; complete synthetic oracle passes. | REVIEW_HARNESS, low; no |
| R02 | Temporary tables were invisible across independent cursors; SQL aliases collided with reserved words | Reviewer tables made persistent only in the private review DB; aliases corrected; complete scientific and checkpoint fixtures pass. | REVIEW_HARNESS, moderate; no |
| R03 | Initial independent registration digest used the wrong protocol domain | Corrected to accepted `SAFE:publication-commit:v2` plus NUL; independently recomputed portable registration test passes; candidate primitive unchanged. | REVIEW_HARNESS, moderate; no |
| R04 | Initial absence fixture inherited positive GeoNames evidence | Explicit NOT_FOUND and NOT_EVALUABLE fixtures now assert zero negative gating; 25 harness tests pass. | REVIEW_HARNESS, low; no |

### R05 — Log timer scope falsely compared two different progress objects

- Classification: **REVIEW_HARNESS**; severity **low**; candidate regeneration **no**.
- Evidence: `operations_stdout_numeric_timers` failed once in 1102 progress
  records; every other log structure/label/numeric-aggregate check passed.
  Frozen `s10_query_execution._run` creates a separate input-preparation Progress
  object. Its `input_validation` timer is absent from the workspace Progress
  object's final timer dictionary. The reviewer incorrectly required every timer
  name to belong to that final workspace dictionary.
- Correction: validate input-phase timers against exactly `input_validation`,
  with no SQL categories; preserve workspace-scoped names and nonnegative integer
  constraints for all other phases. No arbitrary name or payload is accepted.
- Verification: synthetic tests reproduce the old false failure, accept the two
  proper scopes, and reject cross-scope/unknown names, nonnumeric, boolean and
  negative timer values. Full log audit is factored for reuse.
- Controlled verification: **1781037** reproduced exactly **one** legacy failure,
  attributable solely to the hash-pinned input-validation receipt, and **zero**
  other legacy failures. Corrected full audit passed all **1103** log records
  (1102 progress records plus one terminal record); stderr is empty. All **20**
  follow-up checks pass, with original logs, prior evidence and candidate terminal
  state unchanged. It read no protected relation and regenerated no query.
- Evidence: `evidence_1781037.json`, SHA-256
  `197c8074c1f5187261f0fdb1ff1811f7955665b7539bbb2f315647feb9a9646f`.
- Disposition: **resolved**, including controlled verification. Local harness
  suite: **28 passed**. The first job's evidence remains unchanged.

## Final disposition

All **22** areas are complete. There are **two unresolved candidate defects**:
one CANDIDATE_IMPLEMENTATION and one CANDIDATE_PUBLICATION, both P2. No candidate
scientific-content, data-integrity or privacy defect was found within the stated
review scope. All **five REVIEW_HARNESS findings are resolved**; eight
INFORMATIONAL findings require no candidate regeneration. No ordinary defect
stopped the full review. Candidate relations/artifact and accepted inputs remain
unchanged. C01 requires regenerated immutable decision output/artifact to conform
to the frozen contract; C02 requires a conforming new publication. No remediation
or scientific retuning is performed or authorized by this review verdict.

**STAGE10_MULTI_HYPOTHESIS_QUERY_GENERATION_INDEPENDENT_REVIEW_FAIL**

**NEXT: OWNER REVIEW OF COMPLETE STAGE 10 DEFECT LEDGER**

HOLDOUT remains sealed; production/Pelias untouched; Stage 11 NOT STARTED;
Stage 10 NOT YET OWNER ACCEPTED.
