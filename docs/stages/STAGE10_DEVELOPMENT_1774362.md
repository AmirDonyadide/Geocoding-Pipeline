# Stage 10 corrected DEVELOPMENT candidate — job 1774362

## Status and authority

**STAGE10_MULTI_HYPOTHESIS_QUERY_GENERATION_DEVELOPMENT_CANDIDATE_READY**.
Owner-authorized job **1774362 COMPLETED / 0:0**, elapsed **22:54:28 (82468 s)**.
On owner continuation, 2026-09-23, one terminal accounting check was followed by
bounded candidate reconciliation. No second job, diagnostic, confirmation or
scientific regeneration was submitted. Stage 10 is **NOT YET ACCEPTED**;
independent review is next. This is query-generation evidence only: no geocoding
accuracy, address validity, precision, recall or match-correctness claim.

| Provenance | Exact identity |
|---|---|
| Design freeze/merge | `1443bb3b3c1bb50220bf38231e01552c66c4eaee` |
| Approved performance integration/main | `8baf05be1bd7bac2f7cfa5c38f2ab994805b68db` |
| Executable, clean detached Goethe checkout | `63f3cd107e69c9ddc14b9b517b0c7ab3d5861e66` |
| Performance evidence reporting | `af4c95a0de5d99dfabe97ce8f9fac2d1a18f07e8` |
| Submission reporting | `eef5f0341f431c76a0edd574c7e682a3f7698351` |
| Submission / start / end UTC | `2026-09-21T11:26:41Z` / `2026-09-21T18:29:28Z` / `2026-09-22T17:23:56Z` |
| Request | 4 CPUs, 32 GiB, 36h; one node/task; general1 / footprint / normal; no dependency/requeue |
| Allocation / node | 80 CPUs / `node29-001`; topology allocation, not measured 80-core use |
| Scheduler batch MaxRSS | 13304912 KiB = **12.689 GiB** |
| Application process peak | 13595980 KiB = **12.966 GiB**, a different measurement scope |
| Accounted CPU | TotalCPU 23:02:27; UserCPU 22:09:51; SystemCPU 52:36.203 |

Publication key: **`stage10_development_20260921T112356Z_63f3cd107e69`**.
Artifact:
`/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage10/development/stage10_development_20260921T112356Z_63f3cd107e69`.
Preserved workspace is under the sibling `work/` directory, with suffix
`stage10_development_20260921T112356Z_63f3cd107e69_jqzh0f0s`.
All earlier failed/diagnostic/confirmation attempts remain preserved.

## Bound inputs, science and runtime

| Binding | SHA-256 |
|---|---|
| Stage 8 accepted manifest | `2a50bd8c066552c9cb7505ed2d6071f1ee36161b9a2cc07f3ed364cf00237827` |
| Stage 8 logical dataset | `9c9d431c2c1b92712e0cb372f2661ad48f4fe8758dc0327d25aef90ab2c2d526` |
| Stage 9 accepted manifest | `321c9d8352fac5b78612a7c8e52f6f810f92bddb1e91f7cfe348398a6d707240` |
| Stage 9 logical dataset | `7ae84e149f4c9c2de7a791c9b326b88e387a70d155d8be55acf6b55e06bafae3` |
| Stage 9 → Stage 8 binding | `64f7678a76e3f29f57859f050329be925b216d2b1290eff5d36b9cb4482cea90` |
| Stage 6 accepted manifest | `e1da7b8ef04b65b1ece8e710720b57a8536841766fcf9de641f889b42eadd241` |
| Combined Stage 10 input binding | `531d512f6c177fb5a9d6cd262e66846cdfd5cc66ba818c5aba8030165648878e` |
| Stage 10 contract | `be0a865f5217a82497cc3324fa11557df06441ec67e08f1cd2014cbf0d9b246b` |
| Profile | `6c42e00e7550edac184d6f8ba46e421e84f82a2df9b9234049ed3fca59a6798d` |
| Schema bundle | `659a98157951876b14078d0306b94f8f1e3e151fc92a7352243b3fce1b715070` |
| Transliteration specification | `5d0a8f6906a8d93ac38d73a862d69e31e2e9e454e8d0518e0c13f9792256a916` |
| Runtime build lock | `20bfe735dca8b35b0ea10f1e3d729f2007e4cf3333dd5d5b5cdd527ef638d2cd` |
| Runtime semantic fingerprint | `8b0a2232c28898f1dfd581e88fcbdbe8b7e7bebd458abcc852fab4cbfe225a8b` |

ICU4C **77.1**, Unicode **16.0.0**, CLDR **47**, frozen Grek-Latn/Cyrl-Latn
rules and runtime asset hashes are unchanged. Live runtime and input validation
preceded generation inside SLURM. Python 3.14.3, PyArrow 25.0.0, DuckDB 1.5.5.
Source truth, representations, parser/reference evidence and hypotheses retain
their distinct authority. No replacement source/candidate map was introduced.

## Contexts, coverage and cardinality

All **35000 source rows**, **51779 exact candidates** and **69747 occurrences /
query contexts** are retained. STANDARD **34822**, NATIVE **34925**. Source rows
with zero/one/two contexts: **0 / 253 / 34747**; maximum **2**.
Exactly **6 Q1–Q6 decisions/context** gives **418482** decisions; Q7 decisions
and hypotheses are **0**.

| Dimension | Distribution / result |
|---|---|
| Hypotheses/context (0, 1, 2, 3, 4, 5) | **1668, 14831, 31948, 21250, 50, 0** |
| Hypotheses/source row (0 through 10) | **845, 193, 6404, 1906, 14752, 500, 10364, 22, 14, 0, 0** |
| Hypotheses/candidate (0, 1, 2, 3–4, 5–8, 9–16) | **1076, 7165, 19946, 17966, 5624, 2**; actual maximum 12 |
| Contexts/candidate (1, 2, 3–4, 5–8) | **33889, 17855, 29, 6**; actual maximum 8 |
| Candidates with >1 context | **17890** |
| Country contexts/candidate (1, 2, 3) | **51761, 17, 1**; 18 candidates have multiplicity |
| Boundary contexts/candidate | **1 for all 51779** in this population |
| Contexts with/without hypotheses | **68079 / 1668** |
| Source rows with/without hypotheses | **34155 / 845** |
| Candidates with/without hypotheses | **50703 / 1076** |

Hypothesis maximum is **4/context, 8/source row**. Fifty contexts reach four;
none reaches five. Fourteen rows reach eight; none reaches nine. All enforced
5/context, 10/row, tighter STANDARD≤4 / NATIVE≤5 / row≤9 and occurrence-derived
candidate bounds pass. **Engineering overflow = 0; operating-budget suppression
= 0**. Absence of a five-hypothesis context here does not change the proven
engineering ceiling or synthetic Q5/Q6 coexistence witness.

The 1668 zero-output contexts comprise 845 STANDARD and 823 NATIVE occurrences
without suitable country context, across 845 rows. They remain mapped with all
six auditable decisions. No source row/candidate is deduplicated away.
This is the frozen bounded-country abstention, not a Stage 9 country-resolution
prerequisite or an individual-field contradiction deleting source text.

## Families, suppression and convergence

Counts below cover all 69747 contexts, including role-ineligible slots. Emitted
means FIRST_MEMBER; eligible includes converged memberships. Each eligible family
contributes one distinct hypothesis membership even when another family owns it.

| Family | Eligible / contributed | Emitted | Converged | Suppressed |
|---|---:|---:|---:|---:|
| Q1 FULL STANDARD | 33977 | 33977 | 0 | 35770 |
| Q2 FULL NATIVE | 34102 | 34102 | 0 | 35645 |
| Q3 BOUNDARY-PRESERVING | 68079 | 38644 | 29435 | 1668 |
| Q4 SOURCE-ANCHORED STRUCTURED | 33556 | 33556 | 0 | 36191 |
| Q5 COMPLETE-LINE UNIT/LEVEL ALTERNATE | 50 | 50 | 0 | 69697 |
| Q6 NATIVE TRANSLITERATION | 2348 | 2348 | 0 | 67399 |

Suppression reasons, excluding ALL bookkeeping cells:

- Q1: unavailable representation/role 34925; country context unavailable 845.
- Q2: unavailable representation/role 34822; country context unavailable 823.
- Q3: country context unavailable 1668. Every country-eligible context had
  sufficient accepted boundary lineage; 100% availability within that subset
  follows the accepted handoff, not inferred parser trust.
- Q4: country context unavailable 1668; insufficient structured evidence 34523.
- Q5: country context unavailable 1668; parser evidence unusable/corroboration
  insufficient 20; ambiguous unit alignment 4; family ineligible 68005.
- Q6: unavailable representation/role 34822; country context unavailable 823;
  unsupported script/mark 31753; unsupported transformed output 1.

**172112** eligible family constructions converge to **142677** hypotheses,
reducing within-context duplicates by **29435**. Convergent family pairs:
Q1/Q3 **14694**, Q2/Q3 **14741**; all others zero. Q5/Q6 unchanged-transformation
convergence is zero. All family lineage survives. Upstream STANDARD/NATIVE exact
candidate equality occurs on **17913 rows**; eligible full-intent equality is
**17326 / 33924 evaluable rows**. These have different denominators.

Aggregate distinct Stage 10 intents number **105805**, with 36872 repeated
across contexts. This is a descriptive intent statistic only. No cross-context
hypotheses were removed, Stage 11 semantic IDs were not defined, and no global
complete-request deduplication was performed.

## Reference evidence, Q5 and Q6

Q4 postcode field decisions include **6751** values and omit **17529** through
authorized contradiction: **Q04 17527; Q08 2**. These are context/field decisions,
not invalid-address rates or a claim that all other Q4 fields were eligible.
Contexts with relevant NOT_FOUND (**19723**) or NOT_EVALUABLE (**67999**) evidence
remain non-negative; categories can overlap. GeoNames mismatch in **7090**
contexts has no negative authority. **Q1/Q2 content mutations from these gates =
0**, established by full replay against original representations and frozen rules.

Q5 emits **50** whole-boundary-unit alternates. Ambiguous alignment **4**;
insufficient corroboration **20**; source-field veto **0**; empty result **0**;
unchanged **0**; safety failures **0**. A reporting annotation finds **7910**
family-ineligible contexts with mixed content and no complete removable unit;
it is a subset of family-ineligible suppression, not an additional decision or
authority for substring deletion. Complete-line grammar, unique parser alignment
and source-field vetoes remain binding. No protected examples were examined.

Q6 eligible/emitted: Greek **157**, Cyrillic **2191**. Greek/Cyrillic mixture
abstention **0**; other unsupported script/mark **31753**; unchanged/converged
**0**. One transformed output fails the frozen supported-output test and safely
abstains. **2349 ICU calls** during generation include that suppressed output;
**9396 calls** include all three exact replays. Runtime/version/hash mismatches
and technical failures are **0**. Native evidence is preserved.

Q5+Q6 coeligible contexts: **0**. This is an observed population result, not an
exclusion by script or evidence against the synthetic five-intent witness.
The complete old/new scientific and coexistence tests remain authoritative.

## Actual performance and checkpoint evidence

Times are measured wall seconds. Input and workspace clocks have different
origins; phase differences below use the appropriate monotonic snapshot pair.
Nested timers overlap and must not be summed as independent costs.

| Phase | Seconds | Scope |
|---|---:|---|
| Input validation | 3254.723 | Full accepted inputs, before context workspace |
| One-time workspace preparation | 1011.135 | Includes 315.001 reference, 560.553 parser, 7.979 initial context/index seconds and other setup |
| Generation | **20294.549** | 5.637h; includes 1099 units and 16 prefix coalescings |
| Post-generation summary preparation | 128.012 | Before publication/validation start |
| Publication and full validation | **57759.832** | 16.044h combined state-machine interval |
| Three scientific publication replays | **56550.975** | Inclusive subset of the previous row, 209241 context visits |
| Publication copy | 189 | Integer seconds recorded inside publication build |
| Application total | 82449 | Scheduler total is 82468 s |

The manifest's historical `generation_elapsed_seconds=24561` starts before
input validation; it is **not** generation-only timing. The separate durable
generation snapshots give 20294.549 s. Publication-only overhead excluding
validation is not independently timed; no fabricated separation is reported.
Context/index construction has four calls in the whole run: initial setup and
refresh after each publication output registration. Reference/parser preparation
is once, not per checkpoint or replay.

| Generation portion | Units | Contexts / decisions / hypotheses | Contexts/s | Decisions/s | Hypotheses/s |
|---|---:|---|---:|---:|---:|
| EARLY | 366 | 23214 / 139284 / 47642 | 3.526 | 21.158 | 7.237 |
| MIDDLE | 366 | 23261 / 139566 / 47554 | 3.514 | 21.084 | 7.184 |
| LATE | 367 | 23272 / 139632 / 47481 | 3.399 | 20.395 | 6.935 |

Portions group ordered checkpoint completion intervals; they include intervening
prefix coalescing and exclude the final 245.969 s coalescing tail. They are not
identical-work samples. Late throughput is about 3.6% below early, without
pathological collapse. The confirmation's 3.863/2.950/3.630 contexts/s and
4.477 MiB WAL observations covered a smaller shard; comparison is descriptive,
not a new tuning threshold. Actual total **22.91h** is below the conditional
24.3h central / 30.1h conservative forecasts and the approved 36h limit.

There are **1099 unit checkpoints and 16 sealed prefixes**. Units comprise
**1083 × 64**, plus one each of **7, 8, 9, 12, 15, 16, 18, 23, 24, 27, 28, 35,
42, 49, 59, 63** contexts. All sum to 69747. Current metadata hashes validate all
1115 seals against their manifests; private permissions remain 0600. The initial
job validated every unit's contents before sealing. No artificial resume or
partition experiment was added. Validated operational adoption semantics remain
available; actual regeneration/adoption was not needed in this fresh run.

| Computation | Generation | Entire workspace run including 3 replays |
|---|---:|---:|
| Certificate calls | 69747 | 278988 |
| Certificate wall time | 17223.806 s | 68877.550 s |
| SQL executions | **164114** | **905076** |
| Inclusive SQL time | 924.291 s | 4537.983 s |
| Q5 family time | 2.427 s | 9.511 s |
| Q5 alignment calls / time | 68079 / 1.901 s | 272316 / 7.395 s |
| Q6 family time | 2.404 s | 9.661 s |
| ICU calls / time | 2349 / 0.281 s | 9396 / 1.169 s |

Generation SQL obeys the summed 16-prefix bound **9C+4K+P = 632135**;
observed **164114**. Reference point SQL remains zero after setup. Whole-run SQL
includes four diagnostic scans, output/schema checks and the three required
scientific replays; comparing its total to one-shard generation would be wrong.

| SQL category | Generation calls | Whole-run calls |
|---|---:|---:|
| SOURCE_REFERENCE | 69747 | 278988 |
| PARSER_CERTIFICATE | 69623 | 278490 |
| SELECTOR_SPILL_SORT | 15629 | 62516 |
| CONTEXT_PAGE | 2321 | 5882 |
| COMPONENT_STREAM | 65 | 271877 |
| CHECKPOINT | 2205 | 2206 |
| CHECKPOINT_KEYS | 1118 | 1159 |
| DIAGNOSTIC_WRITE_OR_REGISTER | 1146 | 1155 |
| VALIDATION_OR_OTHER_SELECT | 2258 | 2721 |
| SETUP_OR_OTHER | 2 | 78 |
| Registry/capability/object/member streams | 0 | 1 each |

Registry encodes **3**, capability encodes **47578**, object encodes **524098**,
member encodes **554366**, each in one preparation. Reference-store lookups
143661292 include all scientific passes. Selector insertion and standalone
hash/serialization microtimers were confirmation-only instrumentation; the full
run does not invent missing counter values. Required exact outputs and replay
identities match regardless of instrumentation.

Generation writes **73.041 s**, close/checkpoint **656.254 s**, database checkpoints
**71.120 s**, coalescing **842.780 s**; inclusive scopes overlap. WAL sampled
high-water **29679390 bytes = 28.304 MiB**, absent after close. The exact executable
requires zero WAL after each database checkpoint and otherwise fails closed;
all **2206** calls completed. Full-run receipts retain the sampled high-water,
but do not separately persist each post-checkpoint size. This reporting limit
does not establish a continuously observed maximum or a causal relation to speed.

Peak memory is bounded within the 32 GiB request for DEVELOPMENT. This run does
not establish constant resource usage or production readiness for 141 million
rows. Full publication replay is now a measured major cost; no safeguards are
removed and no family/operating budget is tuned from this run.

## Publication, reproducibility and privacy validation

| Artifact identity | SHA-256 |
|---|---|
| Manifest | `085b05f6201831de6aa908c599bb5541a85cc185a48022d2d93d1e0a9afcc3fa` |
| Logical dataset | `70abebdaeee44cf0eae09eb89e4ed68ef087f1596bfa86ea1bef6aef57ceed92` |
| query_hypothesis logical relation | `c61ba899dbe4f714e2879995261b7d3a943e3b830ca69b4656e2d286230982e1` |
| query_family_decision logical relation | `227de0a64624eef84e7bf45664099ea6d7b5e52e53f16fc3ad361fa6e652c0a2` |
| Summary | `3748781b15c3b7451515ddadff88976da2cc119f02ba12040ec8bc69d8d51136` |
| Registration | `fd995aa99d8f4f69485146cca0af493a683e6521ba404ecf9136c6ccdf3c7f2d` |
| Commit record | `0572d91689161390cdc402a6e2e7d5fd9a7679edb73247c0ca7904b193a82feb` |

**P11 VALIDATED:** the scheduled run exercised exclusive reservation → immutable
validated artifact → exact registration → exclusive `_COMMITTED` → full reopen
validation. The final disposition is **PASS**. All three full scientific replays
compared both protected relations against deterministic regeneration inside
Goethe. They also validate physical inventories, ordering, logical fingerprints,
IDs, PK/FK/map-back, memberships, source/context totality, summary and diagnostics.
Q7/budget prohibition and tighter role/candidate bounds are enforced.

There are 16 files per relation: hypothesis **78785410 bytes**, decision
**56035132 bytes**. Current remote metadata matches every owned file's private
mode and declared size. Post-run review independently recomputed the combined
input fingerprint, dataset fingerprint and exact registration/commit identity
from sanitized metadata, agreeing with manifest, seal and CLI success. No extra
standalone adoption job or fourth scientific replay was performed. Exact adoption
identity agrees; full checkpoint adoption was already demonstrated in 1774301.

All **1117** copied sanitized receipt/metadata hashes match their controlled
originals. There are 1108 workspace phase/checkpoint receipts, 3 input receipts
and 6 root metadata/receipt files. Setup, generation, each checkpoint, validation
and terminal success are durable. Stdout has **1103** fixed-schema aggregate JSON
records; stderr is empty. Only sanitized aggregates, hash inventories and
operational seals were transferred for local review. Protected Parquet, context
keys, query strings, parser strings and row-level checkpoint manifests stayed
on Goethe. No protected examples were copied, printed or used for tuning.

## Complete bounded candidate self-review

| Item | Disposition and evidence |
|---|---|
| C01 source-context grain / cross-row contamination / map-back | PASS: all occurrences retained; row/candidate/role FK integrity and country-local reconstruction checked by full replay; 18 multi-country candidates preserved |
| C02 families / IDs / convergence / cardinality | PASS: exact six decisions/context, unique IDs/ranks/intents and complete memberships; histograms reconcile; all safety bounds pass |
| C03 zero-output country contexts | EXPECTED: 1668 contexts / 845 rows abstain through frozen country-context gate; no hidden country-unbounded fallback or source deletion |
| C04 Stage 9 authority | PASS: only authorized postcode capabilities gate Q4; NOT_FOUND/NOT_EVALUABLE/GeoNames remain non-negative; full baseline mutations zero |
| C05 Q5 safety | PASS: 50 exact whole-line alternates, all gates replayed; mixed-content reporting is not deletion authority; no safety failure |
| C06 Q6 reproducibility / one unsupported output | PASS: exact runtime, native preserved; one expected output abstention, zero runtime/transform failure |
| C07 zero Q5/Q6 coexistence / zero boundary multiplicity | INFORMATIONAL: observed DEVELOPMENT population; frozen independent family rules and synthetic coexistence/boundary tests unchanged |
| C08 checkpoints / publication / deterministic replay | PASS: all units and prefixes sealed; 3 complete scientific replays; full publication and reopen; P11 now VALIDATED |
| C09 cumulative timing label | REPORTING_ONLY RESOLVED: old generation_elapsed_seconds includes setup; report uses durable generation-start/end difference; no scientific artifact edited |
| C10 WAL / timing instrumentation scope | INFORMATIONAL: sampled WAL and enforced zero-after-checkpoint guard distinguished; combined publication/validation and absent microtimers stated explicitly |
| C11 privacy / prohibited stages / budgets | PASS: fixed sanitized log/schema checks; no protected local payload, HOLDOUT, production, Pelias, Q7 execution, Stage 11 or operating-budget tuning |
| C12 performance / production scale | PASS for DEVELOPMENT: stable throughput, checkpoints and memory; no production-readiness extrapolation or new tuning threshold |

No unresolved candidate-output defect was found; no regeneration is required.
Technical failures are zero: malformed upstream evidence, transformations,
cardinality, orphans, checkpoints and publication. The self-review is not an
independent candidate review and does not mark Stage 10 accepted.

The executable's pre-submission evidence remains **276 focused Stage 10 tests**,
**1050 safe repository tests** including Stage 8/9, mypy/Ruff, scientific equality,
SQL counts, checkpoint partition/adoption/interruption, exact runtime-lock,
privacy, CLI, shell and schema/spec checks. This continuation changes only
reports/indexes and applies fresh metadata/hash/cardinality/registration,
receipt/privacy/link, frozen implementation inventory and diff checks.

## Portable evidence and next boundary

- [Submission and exact preflight](../scientific_assets/stage10_development_submission_1774362.json)
- [Exact sanitized manifest](../scientific_assets/stage10_development_manifest_1774362.json)
- [Exact aggregate summary, including complete reason/field cells](../scientific_assets/stage10_development_summary_1774362.json)
- [Exact registration](../scientific_assets/stage10_development_registration_1774362.json)
- [Exact completed receipt](../scientific_assets/stage10_development_completed_1774362.json)
- [Bounded review, accounting, phase/SQL counters and ledger](../scientific_assets/stage10_development_review_1774362.json)
- [Receipt/checkpoint metadata inventory](../scientific_assets/stage10_development_review_inventory_1774362.json)

Stage 0–9 and Stage 10 science unchanged. Operating budget **UNSELECTED**;
HOLDOUT sealed; production/Pelias untouched; Stage 11 **NOT STARTED**;
Stage 10 **NOT YET ACCEPTED**. No acceptance tag created.

**NEXT: INDEPENDENT STAGE 10 DEVELOPMENT CANDIDATE REVIEW.**
