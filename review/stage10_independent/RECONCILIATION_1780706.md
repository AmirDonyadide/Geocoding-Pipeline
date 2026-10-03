# Independent review job 1780706

Historical first-job reconciliation, 2026-09-23. The R05 verification described
as pending below completed on 2026-09-24; see the [final review](FINAL_REVIEW.md).
Original first-job evidence is preserved without modification.

On owner continuation, one accounting check returned **COMPLETED / 0:0**,
elapsed **01:12:43**. Request: general1 / footprint / normal, one node/task,
4 CPUs, 32 GiB, 12 hours, no requeue. Submission UTC:
`2026-09-23T13:36:05Z`. Accounting displayed start `2026-09-23T15:44:56`
and end `2026-09-23T16:57:39`; these are retained as scheduler-displayed values.

Harness: `2f9ddf84f389eb9edc26880b091e6cd9b0ece15f` on
`review/stage10-independent-20260923`. Branch point/current main at submission:
`e7fe4878f585c0283e57edee16f64883b8f8f758`.
Candidate executable: `63f3cd107e69c9ddc14b9b517b0c7ab3d5861e66`.
Candidate reporting commit: `e7fe4878f585c0283e57edee16f64883b8f8f758`.
Artifact/publication key remains `stage10_development_20260921T112356Z_63f3cd107e69`.

Controlled review output:
`/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage10/independent_review/review_2f9ddf84f389_1780706`.
The immutable portable aggregate [evidence](evidence_1780706.json) hashes to
`4ba802155b27390d8a33b88891abf0cbf19657c6fe9106ab145ae1a4627b0fcf`.
No protected strings, row IDs, example addresses or raw relation files were
copied to the Mac or Git. The eight protected phases completed in 4358 seconds
with zero harness exceptions. 202 of 206 named checks pass. False checks are
fully classified in the [ledger](LEDGER.md): C01 (one), C02 (two), R05 (one).

| Review area | Independent result |
|---|---|
| 1 Frozen bindings | All candidate/executable/input/science/schema/profile/runtime identities pass; exact accepted Stage 6/8/9 and DEVELOPMENT population |
| 2 Query-context grain | 35000 rows; 34822 STANDARD + 34925 NATIVE = 69747 contexts; 0/1/2 distribution 0/253/34747; 17913 equal-candidate rows retain two role occurrences; zero linkage errors |
| 3 Relational integrity | 142677 hypotheses, 418482 decisions; full logical hashes and all identifiers match; zero PK/FK/orphan/context errors; six decisions/context, zero Q7 |
| 4 Family decisions | All six eligible/emitted/converged/suppressed aggregate rows reproduce exactly; closed reasons/statuses and membership checks pass; explicit Q4 omission C01 remains |
| 5 Q1/Q2 | Complete representations and intents preserved; zero contradiction mutations or missing valid baselines |
| 6 Country abstention | 1668 precisely justified by row-local source-code context; no Stage 9 country-assessment dependency, loss of valid context or invalid-address claim |
| 7 Q3 | 68079 eligible, 38644 emitted, 29435 converged, 1668 suppressed; 209241 Q1/Q2/Q3 slots audited; source boundaries, all Q3 source-line certificates and LF trace match |
| 8 Q4 | 33556 eligible; source-anchored content, eligibility, field dispositions and operational reasons match; C01: missing visible parser geography exclusion |
| 9 Stage 9 authority | Exact source schedule/arguments/capabilities/witnesses; postcode 6751 included, 17529 authorized omissions (Q04 17527, Q08 2); NOT_FOUND/NOT_EVALUABLE/GeoNames non-negative; zero baseline mutations |
| 10 Q5 | 50 eligible; zero eligibility/content/removal/trace/safety discrepancies; no substring deletion; zero diagnostic-precedence overlap |
| 11 Q6/runtime | Locked ICU4C 77.1 / Unicode 16.0.0 / CLDR 47; 157 Greek + 2191 Cyrillic = 2348; 2349 attempts, one unsupported output safely suppressed; zero mismatches |
| 12 Convergence | 172112 eligible constructions → 142677 context-local complete intents; Q1/Q3 14694 and Q2/Q3 14741, all other family pairs zero; memberships/ranks correct |
| 13 Cardinality | Hypotheses/context 0–5: 1668,14831,31948,21250,50,0; context sum 69747, weighted sum 142677; maximum 4/context and 8/row; tighter role bounds pass, zero engineering overflow |
| 14 Identity separation | Stage 10 context/intent identifiers match frozen encoding; global intent repeats retained; no Stage 11/12 identities or cross-context deletion |
| 15 Checkpoint/resume | 1099 units, 16 prefixes, 1115 seals; exact unit/final relation equality and context/diagnostic bijection; no partial accepted unit; actual reuse count zero |
| 16 Performance semantics | Scientifically complete immutable cache keys and selectors reviewed; 924 complete certificate comparisons over fixed 28-context selection, zero mismatches; unchanged partition-independent identifiers |
| 17 Publication | P11 primitive/path/device/private topology, reservation/registration/seal/reopen/inventory and unchanged final bytes pass; C02 frozen registration names fail |
| 18 Fingerprints | All supplied hashes validate; full independent logical relation and dataset fingerprints reproduced |
| 19 Replays | Three required full scientific comparisons and four full-population passes bound to exact candidate; 1117 receipt hashes valid; no substituted replay output or extra requirement |
| 20 Privacy | Git/static output review passes; original log schema/labels/aggregate values and empty stderr pass; one timer-name false failure needs R05 correction verification; no observed protected leakage |
| 21 Interpretation | Report stays within query generation, with no accuracy/validity/precision/recall/rooftop claim |
| 22 Budget | UNSELECTED/null, ALL_ELIGIBLE_CATALOG, zero scientific-budget suppression |

Family matrix order: eligible / emitted / converged / suppressed.

| Family | Counts |
|---|---|
| Q1 | 33977 / 33977 / 0 / 35770 |
| Q2 | 34102 / 34102 / 0 / 35645 |
| Q3 | 68079 / 38644 / 29435 / 1668 |
| Q4 | 33556 / 33556 / 0 / 36191 |
| Q5 | 50 / 50 / 0 / 69697 |
| Q6 | 2348 / 2348 / 0 / 67399 |

The review remains open only to reconcile R05. The owner's REVIEW_HARNESS rule
authorizes its isolated correction and necessary rerun. `review_logs.py` and
`review_logs.sbatch` read the pinned prior review, candidate manifest/registration,
two bound aggregate receipts and original candidate logs under the normal guard.
They rerun log checks and reproduce the old false result; no Stage 10 generation,
reference evaluation, protected relation read or performance confirmation occurs.
Request: one CPU, 2 GiB, 15 minutes, one task/node, no requeue. A new private review
output directory preserves the original evidence. Commit/push precedes execution
from another clean detached checkout. Pending/running ends the session immediately.

Candidate defects are not repaired. HOLDOUT sealed; production/Pelias untouched;
Stage 11 NOT STARTED; Stage 10 NOT YET OWNER ACCEPTED.
