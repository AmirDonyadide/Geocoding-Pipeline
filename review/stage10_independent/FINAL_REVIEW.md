# Stage 10 independent review — final disposition

**STAGE10_MULTI_HYPOTHESIS_QUERY_GENERATION_INDEPENDENT_REVIEW_FAIL**

All 22 requested areas were reviewed. Two P2 candidate contract defects remain:
missing required visible Q4 exclusion provenance and nonconforming publication
adapter names. No candidate repair, scientific tuning or acceptance occurred.
The [complete ledger](LEDGER.md) includes evidence, violated invariant, severity
and regeneration disposition for every finding. The
[22-area reconciliation](RECONCILIATION_1780706.md) records scientific results;
its outstanding log check is resolved below.

## Provenance

| Identity | Value |
|---|---|
| Candidate executable | `63f3cd107e69c9ddc14b9b517b0c7ab3d5861e66` |
| Candidate reporting / branch point / current main | `e7fe4878f585c0283e57edee16f64883b8f8f758` |
| Review branch | `review/stage10-independent-20260923` |
| Scientific review job / harness | `1780706` / `2f9ddf84f389eb9edc26880b091e6cd9b0ece15f` |
| Log-only verification job / harness | `1781037` / `9e921a89d5928bd8966bf60ca067b447475f4da3` |
| Scientific review evidence SHA-256 | `4ba802155b27390d8a33b88891abf0cbf19657c6fe9106ab145ae1a4627b0fcf` |
| Log-only evidence SHA-256 | `197c8074c1f5187261f0fdb1ff1811f7955665b7539bbb2f315647feb9a9646f` |
| Combined `REVIEW_EVIDENCE.json` SHA-256 | `1a71538a577e508c5ec83455b778cb1eaf3a1e9a88d50f7ec61d2e7ee9ef0b93` |

Publication key: `stage10_development_20260921T112356Z_63f3cd107e69`.
Candidate artifact:
`/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage10/development/stage10_development_20260921T112356Z_63f3cd107e69`.
Manifest SHA-256:
`085b05f6201831de6aa908c599bb5541a85cc185a48022d2d93d1e0a9afcc3fa`.
Logical dataset SHA-256:
`70abebdaeee44cf0eae09eb89e4ed68ef087f1596bfa86ea1bef6aef57ceed92`.
All supplied contract/profile/schema/transliteration/accepted-input/runtime hashes
validate. These exact bindings do not waive C01/C02 contract nonconformance.

## Complete candidate defect ledger

| ID / classification / severity | Frozen invariant and evidence | Regeneration required |
|---|---|---|
| C01 / CANDIDATE_IMPLEMENTATION / P2 | Frozen Q4 policy requires visible `PARSER_ONLY_FIELD_EXCLUDED`. No country-eligible Q4 slot emits it: 68079 lack the reason, including 21773 with actual parser geography. The executable never emits this reason. Independent Q4 query content and operational field checks otherwise match. | Yes: new immutable decision relation/artifact and dependent hashes are needed for conformity. |
| C02 / CANDIDATE_PUBLICATION / P2 | Frozen publication adapter requires `STAGE10_DEVELOPMENT_QUERY_PLAN` and `stage10_input_binding_sha256`; exact committed registration instead uses `STAGE10_DEVELOPMENT_QUERY_HYPOTHESES` and `stage10_input_sha256`. The digest exists, but under the wrong contract key. | New conforming immutable registration/artifact required; this naming defect alone does not intrinsically require rerunning query construction. |

Normative references: [Q4 field decisions](../../docs/stages/STAGE10_QUERY_FAMILIES.md)
and [publication adapter](../../docs/stages/STAGE10_MULTI_HYPOTHESIS_QUERY_GENERATION.md).
Implementation references: [`_structured`](../../src/safe_geocoding_pipeline/preprocessing/stages/s10_query_families.py)
and [registration adapter](../../src/safe_geocoding_pipeline/preprocessing/stages/s10_query_publication.py).
No documented subsequent authorization changing these frozen requirements was found.
P11 reservation, private topology, hash binding, exclusive commit seal, immutable
inventory and reopen checks passed; C02 is not a finding of unsafe sealing.

## Reconciled science and integrity

- 35000 sources; 34822 STANDARD + 34925 NATIVE = **69747 contexts**. Source
  context distribution 0/1/2 = **0/253/34747**; 17913 equal-candidate rows retain
  both role occurrences. Exact source/candidate/occurrence linkage holds.
- **142677 hypotheses / 418482 decisions**, six decisions per context, no Q7;
  full logical fingerprints and all row identifiers reproduce, with no PK/FK,
  orphan, role, rank or context integrity failures.
- Hypotheses/context 0–5 = **1668/14831/31948/21250/50/0**. Both context and
  weighted totals reconcile; maxima **4/context, 8/row**, zero engineering overflow.
- All six family matrices reproduce. **172112** eligible constructions converge
  to **142677** distinct context-local complete intents; pairs Q1/Q3 **14694**,
  Q2/Q3 **14741**, all others zero. No cross-context deletion or Stage 11/12 identity.
- **1668** country abstentions follow the exact row-local Q01 contract, not
  country resolution or invalidity. Q1/Q2 content mutations are **zero**.
  Q3 slots, boundaries, LF construction and source-line certificates reconcile.
- Q4 remains source anchored: **6751** postcode inclusions; **17529** authorized
  contradictions, Q04 **17527** / Q08 **2**. Exact arguments/capabilities/witnesses
  apply; NOT_FOUND, NOT_EVALUABLE and GeoNames have no negative authority.
- Q5: **50** eligible, zero safety/content/line-removal/trace discrepancies.
  Q6: **157 Greek + 2191 Cyrillic = 2348**, one safely suppressed unsupported
  output. ICU4C **77.1**, Unicode **16.0.0**, CLDR **47** and exact runtime locked;
  no mismatch. Native representations retained.
- **1099** checkpoints / **1115** unit-prefix seals / **1117** receipt hashes
  validate. Complete unit and final relations are equal. Actual candidate reused
  zero units; no partial unit accepted. Static resume/cache/partition review and
  924 complete certificate comparisons on 28 fixed contexts found no difference.
- Three required scientific replays and four population passes reconcile to the
  exact published candidate. No extra replay or substituted artifact. Reporting
  interpretation is appropriately limited; operating budget **UNSELECTED** with
  zero scientific-budget suppression.

## Complete informational ledger

All are INFORMATIONAL, require no regeneration, and remain explicit scope limits.

| ID | Disposition |
|---|---|
| I01 | 1668 country abstentions are structural observations, not invalid-address labels. |
| I02 | Zero Q5/Q6 coexistence is permitted and is not a defect. |
| I03 | Potential Q5 diagnostic evaluation-order overlap occurs zero times; all reasons and safety checks reconcile. |
| I04 | Same-code replays establish reproducibility; independent output oracles provide separate scientific checks. |
| I05 | Publication timers include replays; sampled WAL is not continuous telemetry; DEVELOPMENT performance does not establish production capacity. |
| I06 | 24 local exact-ICU tests were skipped; the actual pinned Goethe runtime and every Q6 output were validated in the protected review. |
| I07 | Independent complete reference-certificate recomputation covered 28 fixed contexts/924 comparisons, not every context. Full identifiers, contents, source-line certificates, evidence policy and checkpoint equality were separately checked. |
| I08 | Report makes no unsupported geocoding accuracy/validity/precision/recall claim; scientific operating budget remains unselected. |

## Review-harness ledger and final log verification

All five REVIEW_HARNESS findings are resolved separately from candidate defects;
none requires candidate regeneration. R01 (low): unavailable prototype UDF
dependency, replaced by bounded Arrow batches. R02 (moderate): temporary-cursor
visibility/reserved SQL aliases, corrected and tested. R03 (moderate): reviewer
registration hash domain corrected and checked against the portable record.
R04 (low): absence fixture made explicitly NOT_FOUND/NOT_EVALUABLE. R05 (low):
separate input-validation and workspace timers now use their own closed names.
The final local harness suite passes **28 tests**; Ruff and shell syntax pass.

On 2026-09-24 one accounting observation showed **1781037 COMPLETED / 0:0**,
elapsed **00:00:11**, following submission at **2026-09-23T18:59:22Z**. It requested
one CPU, 2 GiB and 15 minutes; no requeue. Scheduler-displayed start/end were
`2026-09-24T02:48:42` / `2026-09-24T02:48:53` (no new timezone inference).
Output:
`/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage10/independent_review/review_9e921a89d592_1781037`.

All **20** log-only verification checks passed. The old check failed exactly once,
solely because of the bound input timer; no other old failure occurred. All **1103**
records pass the corrected audit; stderr is empty. Original log bytes, first-job
evidence and candidate terminal state remain unchanged. No protected relation or
scientific generation was rerun. Combined results are **212 passed / 3 failed**
across **215 unique check names**. The remaining three failures map exactly to
C01 (one) and C02 (two); no unknown failure remains.

No candidate scientific-content, data-integrity or privacy defect was found
within the documented review scope. No protected strings or row-level payloads
were exported. Only review files changed in Git; both jobs used the normal guard,
clean detached pushed checkouts and separate private output paths.

HOLDOUT remains sealed. Production and Pelias untouched. Stage 11 NOT STARTED.
Stage 10 NOT YET OWNER ACCEPTED. Candidate defects were not repaired.

**NEXT: OWNER REVIEW OF COMPLETE STAGE 10 DEFECT LEDGER**
