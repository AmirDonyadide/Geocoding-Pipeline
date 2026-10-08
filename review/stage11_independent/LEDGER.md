# Independent review coverage and defect ledger

Status: **complete — PASS**, reconciled 2026-10-08. All areas A–X were reviewed.
Job **1790315** completed **0:0**, with **124 checks / 609,517 evaluations PASS**,
zero failed checks and zero harness errors. The [complete report](FINAL_REVIEW.md)
and [unaltered protected-job evidence](evidence_1790315.json) bind the verdict.
Candidate code and artifacts were not modified. Stage 11 is not owner accepted.

## Candidate defect ledger

**Complete candidate defect ledger: candidate defects = 0.**

| Classification | Confirmed defects | Unresolved defects |
|---|---:|---:|
| CANDIDATE_SCIENTIFIC | 0 | 0 |
| CANDIDATE_IMPLEMENTATION | 0 | 0 |
| CANDIDATE_DATA_INTEGRITY | 0 | 0 |
| CANDIDATE_PUBLICATION | 0 | 0 |
| CANDIDATE_PRIVACY | 0 | 0 |

No frozen invariant is violated; no candidate severity or remediation applies.
Candidate regeneration is **not required**. Review-harness and informational
findings below remain separate from candidate defects.

## Full coverage matrix

| Area | Final result and independent evidence |
|---|---|
| A Provenance | PASS: frozen tag/ancestry/design bytes, independently reconstructed contract/profile/schema bundle, exact executable/reporting, accepted Stage 10 physical inventory and independently recomputed hypothesis fingerprint, complete input binding, population, artifact and manifest. |
| B Input totality | PASS: 142,677 hypotheses and map rows/unique map keys; full bidirectional H/M sets; zero missing, extra or multiple mappings. Every accepted hypothesis inspected, with no sampling, budget or filtering. |
| C Request integrity | PASS: 105,805 unique full request IDs; exact Arrow types/nullability/order and metadata on all 257 relation files; both FK directions and zero orphan requests. Two relations only. |
| D Serialization | PASS: read complete implementation against frozen framing. Independent vectors cover ASCII, shortest strings, null, whitespace, U+0000/U+FEFF, RTL, multibyte/astral and combining text, BE lengths, explicit type tags and malformed framing. |
| E IDs | PASS: full independent SHA-256 on all 105,805 cores and 142,677 upstream projections; zero mismatches/collisions. Synthetic same-ID/different-payload collision abort and claimed-ID rejection pass. |
| F Global equality | PASS: every mapped hypothesis has exactly the published complete canonical bytes and independently recomputed ID. Unique request keys and totality establish global exact equivalence; no text-only/fuzzy/normalized collapse. |
| G Modes/endpoints | PASS: only `/v1/search` + FULL_TEXT (81,773 requests / 109,121 hypotheses) and `/v1/search/structured` + STRUCTURED (24,032 / 33,556). Invalid combinations fail synthetic challenges. |
| H Exact preservation | PASS: complete upstream-to-core bytes match on every edge. Unicode/whitespace/case/punctuation distinctions and direct-copy code review confirm no new normalization; no protected values exported. |
| I Country | PASS: 105,805 requests / 142,677 hypotheses country-bound, zero unbounded. Exact alpha-2 boundary/namespace participate in identity separately from the always-null structured country. Synthetic country changes cannot alias. No Q7/fallback/inference. |
| J Policies | PASS: every request uses the five exact frozen singleton policies. Complete schema excludes generic headers, retrieval binding and arbitrary parameter bags. |
| K Stage 11/12 | PASS: encoder consumes only frozen schema values. Input slot is validated then excluded. Retrieval/size/transport/host/index/auth/job/path extras rejected; execution provenance lives outside the core. No top-N selected. |
| L Validity states | PASS: independent mode-by-field matrix tests null, empty, missing, defaults, bool/int/float/bytes/list/object and invalid Unicode. Valid whitespace is preserved. |
| M Dedup aggregates | PASS: 142,677 hypotheses → 105,805 requests; reduction 36,872 (25.842988%); 36,822 multi-hypothesis requests; max 8. All seven frozen histogram bins and sums independently match. |
| N Lineage | PASS: independent hypothesis/context/source/role/candidate FK reconciliation and same-context family joins. Cross-context/source/family = 36,822 / 33 / 31,244; STANDARD-only/NATIVE-only/both = 33,240 / 35,759 / 36,806; same-source both = 36,806; family cardinalities = 74,561 / 23,145 / 8,099 / 0 / 0 / 0. All upstream population/abstention counts reconcile without a new lineage relation. |
| O Interpretation | PASS: read complete candidate report and implementation record. Reduction and cross-representation/family diagnostics are consistently workload-only, without accuracy/confidence claims. Summary fixed labels checked. |
| P Fingerprints | PASS: independent hypothesis, semantic-request, map and complete dataset fingerprints equal every pinned value. Complete independently rebuilt summary also matches exact canonical bytes/SHA. Synthetic physical order/shard/codec/path and partition/thread/resume changes preserve logical hashes. |
| Q Checkpoints | PASS: all 18 input + 256 reduction units / 274 seals; zero incomplete units. Independent payload hashes and exact bindings, ranges, contributors, prefixes, complete input-to-H and reduction/map-to-final equality pass. Synthetic interrupted/resumed equivalence passes. |
| R Publication | PASS: actual durable private inventory, 15 ordered phases, no premature seal, exact Stage 11 registration/domain/hash, zero-byte exclusive `_COMMITTED`, full reopen and unchanged before/after artifact hashes. Complete adapter and fault tests reviewed against accepted primitives. |
| S Local independence | PASS: complete independent review and supplemental candidate reopen succeeded with all Python `/local` opens prohibited and spill disabled. Native-library inputs are explicitly durable PanFS paths. All authoritative objects remain durable; synthetic full local loss also passes. |
| T Failure safety | PASS: first-error reserve and guarded secondary reporting reviewed and fault-tested. Collision/contract/manifest/registration failures prevent seal; primary static failure survives secondary reporting error. Actual completed candidate has no failure receipt, no premature seal, and validated final publication. |
| U Privacy | PASS: complete candidate stdout equals its sanitized completion receipt, stderr empty; private topology and before/after hashes pass for all 261 artifact and 842 attempt files. Shared guard precedes protected reads. Only code/synthetic fixtures/aggregate evidence exported; no protected values sent to external services/LLMs, no HOLDOUT/production/Pelias access. |
| V Architecture | PASS: candidate uses capped DuckDB sort/group/joins and single-row readers with byte-bounded writers; full hashes and streamed memberships, deterministic partitions and exact-bound resume. No pandas or pairwise quadratic path. Fixed-memory reopen fails on insufficient resources; no production envelope is inferred. |
| W Tests | PASS: pinned safe regression plus already-local public-only tests reproduces 1,343 passing tests; 24 unchanged optional ICU skips unrelated to Stage 11. All 158 candidate Stage 11 and 495 independent tests pass; self-tests are supplemental evidence. |
| X Ledger | PASS: all areas A–X complete; zero candidate defects in every class. R01–R06 resolved separately, with the historical R06 cause limit preserved. All informational items retained. No candidate regeneration, acceptance or next-stage work. |

## Review-harness findings

| ID | Finding | Disposition |
|---|---|---|
| R01 | False-equivalence test accidentally included the same invented core twice while asserting all fixtures distinct. | RESOLVED: use a distinct invented address for the field-role pair; independent vectors rerun. No candidate defect. |
| R02 | First broad regression used Python 3.14.7 and a noncanonical `/tmp` import path. 28 frozen-runtime checks and one pre-existing path-filtered profiling test failed; three optional public assets were absent from the detached checkout. | RESOLVED: existing Python 3.14.3 environment and canonical `/private/tmp` import path produce 1,340 pass/27 skip. Three public-only tests pass separately using existing public assets; 24 optional ICU skips remain. No guard weakened or protected asset fetched. |
| R03 | Negative contract fixture used null in a non-nullable Parquet field, so Arrow rejected it before the intended application check. | RESOLVED: inject an empty country string, legal to the storage type and forbidden by the scientific contract. Candidate rejects and no seal appears. |
| R04 | Draft independent registration oracle initially named the reused protocol incorrectly. | RESOLVED during static construction: use the actual frozen `exclusive_run_commit_seal_v2_candidate` protocol and `SAFE:publication-commit:v2` hash domain; independent synthetic registration comparison passes. |
| R05 | New multi-defect collection test used SQL equality in a named struct-update argument. | RESOLVED: use DuckDB named assignment syntax; the synthetic test now verifies that multiple defects are recorded and aggregate review continues. |
| R06 | Job 1789589 failed at review-only `scratch.mkdir` before relation scans. Its 35 completed checks passed. Original sanitized receipt omitted OS exception class/errno, so the underlying filesystem cause is unknown. | RESOLVED / VERIFIED by job 1790315: remove the unnecessary review scratch dependency and use a 2 GB memory-capped, spill-disabled connection. All 124 protected checks pass with zero harness errors. Tests cover actual settings, no directory creation, full synthetic reconciliation and safe error classification. Candidate objects unchanged; original evidence/cause limit preserved. |

First protected review job **1789589** ended **FAILED / 1:0** after 25 seconds.
See [immutable sanitized evidence](evidence_1789589.json). Provenance and private
inventories passed; it supplied no completed scientific verdict. Follow-up job
**1790315 COMPLETED / 0:0** independently completed the entire review. The earlier
failure is not relabeled as a passing run and is not a candidate defect.

## Informational ledger

| ID | Observation and limits |
|---|---|
| I01 | Stage 11 is a non-executable semantic catalog. Equal IDs do not establish equal responses across size, engine or data builds; future execution identity remains Stage 12 work. |
| I02 | Upstream zero-hypothesis contexts and source lineage remain accepted Stage 10/8 authority. The review does not reopen raw/Stage 8 source payloads or regenerate Stage 10. |
| I03 | DEVELOPMENT runtime/memory/local sampling is informational; no production capacity extrapolation. Candidate's spill-disabled 2 GB reopen can fail safely when a future workload exceeds its envelope. |
| I04 | Optional ICU tests are unchanged accepted Stage 10 tests. Stage 11 uses no ICU/transliteration path; these skips cannot be treated as Stage 11 scientific validation. |
| I05 | Durable phase evidence and code establish publication behavior; review does not experimentally corrupt, race or interrupt the immutable protected artifact. Failure tests use invented objects only. |
| I06 | Audit hooks cover Python opens/mutations; they are not an operating-system sandbox for native libraries. Exact manifest paths, explicit DuckDB file registration, disabled network extensions, spill-disabled reopen and before/after hashes supply complementary evidence. |
| I07 | This fresh session verifies HOLDOUT sealed by accepted authority and non-access. It does not inspect HOLDOUT storage or attest to activity outside this session. |
| I08 | Historical review job 1789589's scratch-directory filesystem failure has no retained errno or established root cause. The failing dependency was removed and the complete follow-up succeeded. This unresolved historical explanation neither changes candidate science nor requires candidate regeneration. |

Regeneration decision: **NOT REQUIRED**. Review-harness findings R01–R06 are
resolved; informational I01–I08 remain explicitly retained. Operating budget
UNSELECTED; Stage 0–10 unchanged; Stage 11 design frozen; Stage 11 NOT YET OWNER
ACCEPTED; HOLDOUT sealed; production/Pelias untouched; Stage 12 NOT STARTED.

**NEXT: OWNER ACCEPTANCE OF STAGE 11**
