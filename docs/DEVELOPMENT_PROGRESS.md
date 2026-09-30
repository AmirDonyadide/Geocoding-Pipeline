# DEVELOPMENT progress

Current repository status. Execution checkpoints are dated records, not live
scheduler observations. Contracts and evidence are linked below.

| Stage | Name | Status | DEVELOPMENT evidence | Production status |
|---:|---|---|---|---|
| 0 | Source inventory | **`STAGE_0_ACCEPTED`** | Benchmark V1 bound to accepted 1,405-file population; [report](../reports/development/stage00.md) | **ACCEPTED** — `NEW_STAGE0_1411_ACCEPTED`, 1,411 files |
| 1 | Lossless ingestion | **`STAGE_1_ACCEPTED`** | Stable identity/provenance foundation; [report](../reports/development/stage01.md) | **ACCEPTED** — `NEW_STAGE1_1411_ACCEPTED`, 141,048,582 rows |
| 2 | Schema/provenance harmonization | **`STAGE_2_ACCEPTED`** | 35,000 → 35,000; all 22 incoming fields preserved; four structural fields added; [report](../reports/development/stage02.md) | **NOT STARTED** |
| 3 | Safe text cleaning | **`STAGE_3_ACCEPTED`** | Jobs `1759269`/`1759272`; exact v1/v2 scientific equality and bounded validation; [report](../reports/development/stage03.md) | **NOT STARTED** |
| 4 | Lowercase canonical forms | **`STAGE_4_ACCEPTED`** | Job `1759421`; independent job `1759473`; exact Python `str.lower()`; [report](../reports/development/stage04.md) | **NOT STARTED** |
| 5 | Address reconstruction | **`STAGE_5_ACCEPTED`** | Job `1759603`; independent job `1759692`; neutral U+0020 reconstruction; [report](../reports/development/stage05.md) | **NOT STARTED** |
| 6 | Early exact deduplication | **`STAGE_6_ACCEPTED`** | Job `1759819`; independent job `1760055`; 69,747 occurrences → 51,779 exact candidates; [report](../reports/development/stage06.md) | **NOT STARTED** |
| 7 | libpostal parsing/evidence | **`STAGE_7_ACCEPTED`** | Evidence-only job `1763516`; rereview job `1763656`; no semantic-trust claim; [report](../reports/development/stage07.md) | **NOT STARTED** |
| 8 | Lossless address-evidence projection | **`STAGE_8_ACCEPTED`** | Candidate `231cdbf9…`; executable `c04cb972…`; jobs `1764273`/`1764376`; zero candidate defects; [report](../reports/development/stage08.md) | **NOT STARTED** |
| 9 | Conservative offline reference evidence | **`STAGE_9_ACCEPTED`** | Executable `3e10ac7c…`; job `1771191`; independent review `a9ae443c…` / job `1772139`; zero candidate defects; [acceptance](../reports/development/stage09.md#owner-acceptance-and-freeze--2026-09-14) | **NOT STARTED** |
| 10 | Bounded multi-hypothesis query generation | **REMEDIATED CANDIDATE READY — NOT ACCEPTED** | Job `1785683`, COMPLETED / 0:0, 22:49:36; C01/C02, P11 and three replays PASS; [candidate and complete ledger](stages/STAGE10_REMEDIATED_DEVELOPMENT_1785683.md) | **NOT STARTED** |
| 11–14 proposed | Query QA → Pelias top-N → scoring → granularity/abstain | **PROPOSED — NOT STARTED** | Remaining compact replacement architecture; [pipeline specification](PIPELINE.md) | **NOT STARTED** |

Benchmark V1 contains 35,000 DEVELOPMENT and 15,000 sealed HOLDOUT rows from
the permanent 1,405-file population. The fixed 500-row qualitative subset has
fingerprint
`014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52`.

## Current checkpoint

Final remediated candidate reconciliation, **2026-09-30**: job **1785683 COMPLETED /
0:0 in 22:49:36**, scheduler MaxRSS **12.457726 GiB**. All 69,747 contexts,
418,482 decisions and 142,677 hypotheses validate. **C01: 237,263 required/actual
exclusions, zero missing/duplicate/source-anchor/parser-payload violations**.
The same-job relational oracle proves exact prior hypothesis equality and only
the required decision-provenance change. **C02/P11 pass** corrected registration,
portable hash, exclusive seal and full reopen. All **three required full replays**
pass. 1,099 durable unit checkpoints plus 16 prefix seals remain validated.

[Complete candidate report and bounded ledger](stages/STAGE10_REMEDIATED_DEVELOPMENT_1785683.md):
72 receipt/identity/storage checks pass; zero unresolved candidate-output defects.
Retained scientific/audit storage **1.037455 GiB PanFS**; local transient work
completed with the approved 9 GiB request, but actual local peak was not persisted.
Historical F01 remains unresolved. No new execution, code repair or acceptance tag.
**NEXT: FINAL INDEPENDENT REREVIEW OF REMEDIATED STAGE 10 CANDIDATE.**

The following paragraphs preserve the earlier submission checkpoint; their
pending observation and continuation instruction are superseded by this terminal
reconciliation. Operating budget UNSELECTED; HOLDOUT sealed; production/Pelias
untouched; Stage 11 NOT STARTED; Stage 10 NOT YET ACCEPTED.

Split-workspace continuation, 2026-09-28: owner authorized completion of the
storage implementation and **one final full DEVELOPMENT regeneration**, gated
by fresh shared project capacity. Implementation/executable
`cf9e0fe4c12eb85f78051904c636ad084d87a541` is pushed and merged normally into
`main` at `186d4220cbdede6556ce81d16504949215a6f034`. The
[implementation and bounded review](stages/STAGE10_SPLIT_WORKSPACE.md) passed
1,185 safe-suite tests (24 local exact-ICU skips), including 26 split tests.
Pre/post-split synthetic scientific relations agree exactly. Transient
DuckDB/certificates/replay state is job-local; checkpoint payloads, receipts and
publication remain durable on PanFS. C01/C02 and exact-executable adoption rules
are unchanged.

Job **1785683** was submitted exactly once at **2026-09-28T08:15:04Z** using a
clean detached checkout. Its sole initial observation was **PENDING / Priority**,
without dependencies. Request: **4 CPUs, 32 GiB, 36 h, `--tmp=9216M`**, no requeue.
Immediate pre-submission `pan_df` measured **669.782907 GiB** available, above the
**2 GiB** gate; revised planning minimum is **1.103021 GiB**. Inode figures were
not supplied by `pan_df -i`. The assigned job's local capacity is not yet observed;
the public probe verified 1682.220284 GiB and runtime startup fails closed unless
its own private local root has at least 9 GiB. All 96 metadata/input/runtime hash
checks and scheduler/topology checks passed. See the
[immutable submission record](scientific_assets/stage10_split_workspace_submission_1785683.json)
for exact bindings, target and quota values.

No candidate success is claimed. Stop without polling, cancellation or duplicate
submission. On owner `continue`, inspect this job once, then reconcile failure or
perform the complete candidate/C01/C02/publication validation as appropriate.
Operating budget UNSELECTED; Stage 0–9 unchanged; HOLDOUT sealed;
production/Pelias untouched; Stage 11 NOT STARTED; Stage 10 NOT YET ACCEPTED.

Historical storage checkpoint, 2026-09-25: replacement public probe 1784678
completed 0:0 in five seconds; local I/O, SQLite/DuckDB and local-to-PanFS
copy/hash/cleanup passed. At that time shared space was only 0.053797 GiB and no
split implementation/full submission had occurred. The supervisor subsequently
freed capacity. [Preserved probe evidence](stages/STAGE10_LOCAL_STORAGE_FEASIBILITY.md#replacement-result--1784678).

D064–D066 record authorization for Stage 10 implementation and exactly one
bounded DEVELOPMENT catalog, followed by independent review. Executable
`f83480d60449bcc904c0c622e394e12df3c3f2d9` is pushed. The pinned Goethe ICU
runtime was verified by public-only job `1772341`; that job is not a DEVELOPMENT
execution. After eduVPN was restored and preflight passed, DEVELOPMENT job
`1772639` was submitted exactly once at `2026-09-15T14:22:01Z`. Its initial
PENDING / Priority observation ended the session without polling or resubmission.

On the owner's 2026-09-19 continuation, accounting reported **TIMEOUT**, elapsed
`1-00:00:20`; batch exit `0:15`, MaxRSS `7583388K`. One incomplete generation
shard, the database/WAL and attempt receipt remain private. There are zero
complete shard checkpoints and no final artifact, registration or commit seal.
The [failure record and bounded ledger](stages/STAGE10_IMPLEMENTATION.md#development-timeout-reconciliation--2026-09-19)
classify walltime exhaustion and retain the unresolved throughput/observability
issues. No protected payload was opened during reconciliation. No repair,
restart or resubmission occurred at that checkpoint. The single
DEVELOPMENT execution authorization has been used. Stage 10 remains unaccepted.

The owner subsequently authorized **one bounded throughput diagnostic** (D068),
after preserved-evidence/static review, to determine the unknown bottleneck.
The [diagnostic plan and harness review](stages/STAGE10_THROUGHPUT_DIAGNOSTIC.md)
bind a 16-context immutable-ID slice, copied database/WAL inspection, 30-minute
SLURM bound and aggregate timings. This is separate from a full DEVELOPMENT
retry, which remains unauthorized. No candidate publication or science change.

On the owner's 2026-09-20 continuation, the single diagnostic **1773901** at
`622c0589d1dc6c7fd16224a1c46a1d5249bd4bc4` was COMPLETED / 0:0 in 102 seconds.
The copied database recovered 3365 diagnostic rows in shard 0 of 4424 contexts,
bounding original completed generation at 3364–3365 contexts. All 16 selected
diagnostic contexts completed. Reference-witness certificate construction is
the dominant measured cost, but the much faster small slice does **not fully
explain the original timeout**. The [complete performance ledger and proposal](stages/STAGE10_THROUGHPUT_DIAGNOSTIC.md#completed-diagnostic-reconciliation--2026-09-20)
distinguish measurement, coverage limits and proposed repairs. No repair or
additional job was executed; **owner review of that ledger is next**. Stage 10
remains unaccepted and its operating budget remains UNSELECTED.

The owner then approved one consolidated performance repair and **one first-shard
confirmation**, recorded in D070 and the [complete repair/review ledger](stages/STAGE10_PERFORMANCE_REPAIR.md).
The repair preserves science and all eligible families, adds bounded immutable
reference payload reuse, one private context join/index, parser certificates,
64-context checkpoints/resume and aggregate observability. Local validation:
258 focused Stage 10 tests and 1032 safe repository tests passed; exact
old/new synthetic equivalence, mypy, Ruff and execution/document gates passed.
The confirmation first gates on the preserved 16-context outputs, then processes
the exact original 4424-context shard and verifies repartition/resume equality.
At this pre-submission checkpoint no confirmation job has been submitted. A full
DEVELOPMENT retry remains unauthorized; Stage 10 is NOT ACCEPTED.

The repaired executable **`808123bb145107d7b025471b3b02869cc95fb44a`** was
pushed on `perf/stage10-query-generation`. The exact detached Goethe checkout
passed metadata/hash reconciliation. Confirmation **1774012** was submitted
once at `2026-09-20T10:40:09Z` (submission-request UTC), requesting 4 CPUs,
32 GiB and four hours, with no dependency/requeue. Its sole initial observation
was **PENDING / Resources**. The [sanitized submission receipt](scientific_assets/stage10_repair_confirmation_submission_1774012.json)
binds the destination, selection and next action. This is not a candidate
publication. No repeated poll, cancellation, resubmission or full DEVELOPMENT
retry occurred. **NEXT: owner continuation to reconcile this confirmation.**

On the next owner continuation, one terminal accounting check reported
confirmation **1774012 FAILED / 1:0**, elapsed **00:10:31**, batch MaxRSS
**3589792 KiB** (application peak **5342460 KiB**, a separate source). The exact
16-context gate passed with **96 decisions / 35 hypotheses**, but DuckDB rejected
the harness's indexed-table rename before the 4424-context pass. **Zero shard
checkpoint units completed.** The [complete failure reconciliation and ledger](stages/STAGE10_REPAIR_CONFIRMATION_1774012.md)
records the same-version synthetic reproduction, the omitted setup test and a
mutable timing-snapshot defect. Immutable gate receipts preserve exact timings.
No long-shard throughput/resume/WAL conclusion or full-run projection is
available. No executable fix, replacement job or full DEVELOPMENT retry was
made. **NEXT: OWNER REVIEW OF THE CONFIRMATION HARNESS/OBSERVABILITY FAILURE.**

The owner subsequently authorized **one harness-only repair and one replacement
confirmation** (D072). The [repair record](stages/STAGE10_CONFIRMATION_HARNESS_REPAIR.md)
fixes indexed-table setup, tests the actual setup-to-replay path, and captures
immutable timing snapshots. Repaired scientific computation remains pinned to
`808123bb145107d7b025471b3b02869cc95fb44a`; the material parser preparation cost
is measured without further optimization. The exact 16/96/35 gate still precedes
the original 4424-context replay with separate setup/replay timings, 64/32-context
checkpoint comparison and an incomplete-unit resume fixture. No replacement
job has been submitted at this repair checkpoint. No full DEVELOPMENT run,
candidate publication or Stage 10 acceptance is authorized by this repair.

The harness-only correction **`68ce5fbd61c242fd44bdf9094a892d2d040cd628`** is
pushed on `perf/stage10-query-generation`. Metadata preflight verified the clean
detached Goethe checkout, accepted Stage 6/8/9 manifest hashes, ICU lock/binaries,
and the same private PanFS topology. Replacement confirmation **1774111** was
submitted exactly once at **2026-09-20T19:00:12Z** (submission-request UTC), with
4 CPUs, 32 GiB, four hours, no dependency and no requeue. Its only scheduler
observation was **PENDING / Resources**. The [sanitized submission receipt](scientific_assets/stage10_repair_confirmation_submission_1774111.json)
binds the exact original prefix-zero 4424-context population and expected
70/139/70 checkpoint units, including 69 reused units and 8 regenerated contexts
in the resume test. No repeated poll, cancellation, extra submission, candidate
publication or full DEVELOPMENT run occurred. **NEXT: OWNER CONTINUATION TO
RECONCILE REPLACEMENT CONFIRMATION 1774111.**

On owner continuation **2026-09-21**, one terminal accounting observation showed
**1774111 TIMEOUT**, elapsed **04:00:18**, batch **CANCELLED / 0:15**. The exact
16/96/35 gate passed. Both first-shard and repartition passes completed all
**4424 contexts / 26544 decisions / 9065 hypotheses**, with equal logical hashes
and **70 / 139 completed units**. Resume reached **31 reconciled units / 1984
contexts** before timeout; the incomplete tail and final resume checks were not
reached. Certificates still consumed about 95% of each ~93-minute full replay.
WAL cleared at every observed checkpoint; its sampled maximum was 4.462 MiB.
The [complete timeout reconciliation and P01–P12/T01–T05 ledger](stages/STAGE10_REPAIR_CONFIRMATION_1774111.md)
preserve the positive equality/checkpoint evidence, remaining certificate/SQL
and resume costs, and missing durable setup/final failure timings. This is
**STAGE10_THROUGHPUT_REPAIR_CONFIRMATION_FAILED**, not validated remediation.
No further repair, job, full DEVELOPMENT retry or candidate publication was
performed. **NEXT: OWNER REVIEW OF THE REMAINING PERFORMANCE AND CONFIRMATION
LEDGER.** Stage 10 remains NOT ACCEPTED; operating budget UNSELECTED.

Stage 7 acceptance guarantees reproducible parser evidence, not semantic truth
or trust from warning absence. Stage 8 acceptance preserves its lossless
projection and all rejected publication attempts. Stage 9 acceptance is scoped
reference evidence: Q04 conflict rates are not invalid-address rates, and its
country assessments remain unresolved under the frozen witness rule. Exact
limitations and histories remain in the linked reports.

Production Stage 2 onward, Stage 11 onward and geocoding remain unstarted.
HOLDOUT remains sealed. Documentation maintenance does not authorize execution.

The owner has now authorized **one final consolidated performance remediation**
(D074), followed by **one final bounded confirmation**. The
[operational plan and complete ledger](stages/STAGE10_FINAL_PERFORMANCE_REMEDIATION.md)
replace fine-grained certificate SQL, make completed checkpoints adoptable
without scientific regeneration, and persist setup/termination evidence.
The preserved 70/139 scientific equality remains evidence; the new confirmation
will use one generation pass, full adoption and a separate incomplete-tail state.
No new confirmation or full DEVELOPMENT retry has been submitted at this local
implementation checkpoint. Stage 10 science remains frozen and unaccepted.

The final repaired executable **`63f3cd107e69c9ddc14b9b517b0c7ab3d5861e66`**
is pushed on `perf/stage10-query-generation`. Local validation passed **276
focused Stage 10 tests**, **1050 safe repository tests**, mypy, Ruff and the
frozen design/runtime/inventory/document/privacy gates. Self-review R01–R09 is
resolved; full-shard performance/adoption measurements remain pending.

Final performance confirmation **1774301** was submitted exactly once at
**2026-09-21T09:55:52Z** from a verified clean detached Goethe checkout. Its sole
initial observation was **PENDING / Priority**. Request: 4 CPUs, 32 GiB, one node,
four hours, no dependency/requeue. The [sanitized submission receipt](scientific_assets/stage10_final_confirmation_submission_1774301.json)
binds the exact original 4424-context shard, runtime, executable, output and
preserved 1774111 reference. This is **not a candidate publication or full
DEVELOPMENT retry**. No repeated poll, cancellation or resubmission occurred.
**NEXT: owner continuation to reconcile job 1774301 once.** Stage 10 is NOT
ACCEPTED; operating budget UNSELECTED; Stage 0–9 and Stage 10 science unchanged;
HOLDOUT sealed; production/Pelias untouched; Stage 11 NOT STARTED.

On owner continuation **2026-09-21**, one terminal accounting check reported
**1774301 COMPLETED / 0:0**, elapsed **40m27s**. The
[final confirmation reconciliation](stages/STAGE10_FINAL_CONFIRMATION_1774301.md)
validates all **4424 contexts / 26544 decisions / 9065 hypotheses**, with **70
checkpoints** and exact historical scientific equality. Generation took
**1339.761 s** after **903.036 s** of one-time preparation. Full resume adopted
all 70 units in **12.585 s**, with **zero certificate calls or regenerated
contexts**; separate partial-tail resume adopted 69 units and rebuilt only eight
contexts, preserving identical output. SQL calls fell **2329428 → 10449**;
certificate work **5323.204 → 1161.041 s**. Early/middle/late throughput was
**3.863 / 2.950 / 3.630 contexts/s**. Sampled WAL stayed within **4.477 MiB**,
cleared at observed checkpoints and was absent after close. All **379** durable
receipt hashes validate, including terminal success; no unresolved technical
failure or protected leakage. This is
**STAGE10_FINAL_PERFORMANCE_CONFIRMATION_VALIDATED**, not a candidate publication.

The conditional full-run forecast is **24.3h central / 30.1h conservative**,
including the unchanged **three scientific publication/reopen replays** and
explicit input/finalization allowances. Proposed request: **4 CPUs / 32 GiB /
36h**, subject to owner authorization. No corrected full DEVELOPMENT job has
been submitted. Complete P01–P12 disposition and measurement limits are in the
linked report. **NEXT: OWNER AUTHORIZATION FOR ONE CORRECTED STAGE 10 DEVELOPMENT
RUN.** Stage 10 remains NOT ACCEPTED; operating budget UNSELECTED; Stage 0–9
and Stage 10 science unchanged; HOLDOUT sealed; production/Pelias untouched;
Stage 11 NOT STARTED.

The owner approved confirmation 1774301 and authorized **one corrected full
Stage 10 DEVELOPMENT run** (D076). Approved performance history was merged
normally into main and pushed at **`8baf05be1bd7bac2f7cfa5c38f2ab994805b68db`**;
the run uses a clean detached checkout of exact approved executable
**`63f3cd107e69c9ddc14b9b517b0c7ab3d5861e66`**, not the integration/reporting SHA.

Corrected DEVELOPMENT job **1774362** was submitted exactly once at
**2026-09-21T11:26:41Z**. Its sole initial observation was **PENDING / Priority**:
4 CPUs, 32 GiB, **36h**, general1 / footprint / normal, no dependency/requeue.
Partition/account/QOS limits permit this request. Seventy-seven frozen code,
runtime and accepted-manifest hashes, private PanFS publication topology and
absent target/reservation passed preflight. No prior failed/confirmation attempt
was treated as a candidate. The
[submission receipt](scientific_assets/stage10_development_submission_1774362.json)
records all exact bindings and the new publication key
`stage10_development_20260921T112356Z_63f3cd107e69`.

**STAGE10_DEVELOPMENT_RUN_IN_PROGRESS.** Zero checkpoints at this initial
not-started observation; no repeated polling, cancellation or resubmission.
**NEXT: owner types continue in this SAME session to reconcile job 1774362
once.** No candidate is declared ready or accepted. Frozen science, Stage 0–9
and UNSELECTED operating budget remain unchanged; HOLDOUT sealed;
production/Pelias untouched; Stage 11 NOT STARTED.

On owner continuation **2026-09-23**, one terminal accounting check reported
**1774362 COMPLETED / 0:0**, elapsed **22:54:28**. The
[corrected DEVELOPMENT candidate](stages/STAGE10_DEVELOPMENT_1774362.md)
fully published and passed the three required scientific replays, including
committed reopen validation (**P11 VALIDATED**). Exact executable remains
`63f3cd107e69c9ddc14b9b517b0c7ab3d5861e66`; performance integration remains
`8baf05be1bd7bac2f7cfa5c38f2ab994805b68db`.

Candidate: **35000 source rows / 69747 query contexts / 142677 hypotheses /
418482 decisions**, **1099 unit checkpoints**, zero engineering overflows or
unresolved technical failures. Maximum hypotheses: **4/context, 8/source row**.
All six decisions/context and original source/occurrence map-back remain intact;
Q7 rows are zero. Manifest
`085b05f6201831de6aa908c599bb5541a85cc185a48022d2d93d1e0a9afcc3fa`;
logical dataset
`70abebdaeee44cf0eae09eb89e4ed68ef087f1596bfa86ea1bef6aef57ceed92`.

The complete C01–C12 self-review resolves the aggregate anomalies and records
timing/WAL limitations without modifying scientific output. All **1117 receipt
hashes** and **1115 unit/prefix seals** reconcile. No repeat job or extra
performance experiment occurred. **STAGE10_MULTI_HYPOTHESIS_QUERY_GENERATION_DEVELOPMENT_CANDIDATE_READY**.
**NEXT: INDEPENDENT STAGE 10 DEVELOPMENT CANDIDATE REVIEW.** Stage 10 is
**NOT YET ACCEPTED**, no acceptance tag created. Operating budget UNSELECTED;
Stage 0–9 and Stage 10 science unchanged; HOLDOUT sealed; production/Pelias
untouched; Stage 11 NOT STARTED.

## Independent-review remediation — 2026-09-24

The owner accepted the complete 22-area independent review at `bced5920…`: two
candidate defects, C01 missing visible Q4 parser-only exclusion provenance and
C02 publication adapter names. Exactly one consolidated repair and one new
immutable DEVELOPMENT candidate are authorized. The [remediation record](stages/STAGE10_REVIEW_REMEDIATION.md)
preserves the failed-review candidate and review branch, scientific equivalence,
full bounded ledger and same-allocation audit. No new run has been submitted at
this pre-submission checkpoint. Stage 10 is not accepted.

### Remediation submission — 2026-09-24

Exact executable **1b4c076c85ecb48c0a4e28668b69b99e0be128ad** is pushed to
main and retained in a clean detached Goethe checkout. All 89 metadata/design/
runtime hashes and the private controlled PanFS preflight passed. The initial
HTTPS clone lacked GitHub credentials; using the established SSH Git origin
resolved checkout preparation before any submission. No runtime or science changed.

Exactly one remediated DEVELOPMENT job, **1781277**, was submitted at
**2026-09-24T09:23:38Z**. The single initial observation is **PENDING / Resources**.
Request: 4 CPUs, 32 GiB, 36 h, general1 / footprint / normal, no dependency, no
requeue. The [sanitized receipt](scientific_assets/stage10_remediation_submission_1781277.json)
binds the exact inputs/runtime, new target and publication key. The former
failed-review candidate and independent-review branch remain unchanged.

**STAGE10_REMEDIATED_DEVELOPMENT_RUN_IN_PROGRESS.** No repeated polling,
cancellation or resubmission. Owner should later type **continue** in this same
session. Success still requires all ordinary candidate checks, three required
scientific replays, same-allocation C01/C02 population comparison, publication
validation and final independent rereview. Operating budget UNSELECTED; Stage
0–9 unchanged; HOLDOUT sealed; production/Pelias untouched; Stage 11 NOT STARTED;
Stage 10 NOT YET ACCEPTED.

### Remediation failure reconciliation — 2026-09-24

One terminal accounting reconciliation reports **1781277 FAILED / 1:0** after
**09:51:40**, scheduler MaxRSS **10,921,836 KiB**. Generation completed all
**69,747 contexts / 418,482 decisions / 142,677 hypotheses / 1,099 checkpoints**.
The reserved target contains the relation files and manifest but no registration
or `_COMMITTED` seal. The [complete failure record and ledger](stages/STAGE10_REMEDIATION_FAILURE_1781277.md)
classify a **PUBLICATION-phase failure with unresolved underlying exception**
and a separate missing-failure-receipt observability defect. No resource cause
or scientific-content drift is established.

C01 generation records **237,263 parser-only field exclusions**; the declared
hypothesis fingerprint matches the prior manifest. These are partial evidence:
the independent provenance/content audit did not run. C02's corrected manifest
kind is present; registration hash/seal/reopen validation did not complete.
Three required scientific replays are not established as completed. Preserved
generation-validated checkpoints require exact binding/hash validation before
any future authorized adoption. No protected payload processing, repair,
resubmission or additional job occurred during reconciliation.

**STAGE10_REMEDIATED_DEVELOPMENT_RUN_FAILED. NEXT: OWNER REVIEW OF REMEDIATED
STAGE 10 DEVELOPMENT FAILURE.** The prior candidate/review history remains
unchanged; operating budget UNSELECTED; Stage 0–9 unchanged; HOLDOUT sealed;
production/Pelias untouched; Stage 11 NOT STARTED; Stage 10 NOT YET ACCEPTED.

### Publication forensics authorized — 2026-09-25

The owner authorized bounded F01/F02 forensics, preserved-output/C01/content
validation and recovery-contract analysis. The [forensic record](stages/STAGE10_PUBLICATION_FORENSICS.md)
records the complete ledger and synthetic tests. Current project quota is
100% used with about 1.562 GiB available; filesystem-wide capacity did not
represent this effective limit. This is not proof of the historical errno.
Correct registration constructs from the retained manifest; F01 remains open.

Operational repairs add quota-aware preflight and reserved, sanitized failure
receipts. The frozen checkpoint contract requires the exact executable SHA, so
cross-executable adoption after these repairs is prohibited. A guarded read-only
Goethe validator is prepared to finish the independently required checkpoint,
C01 and old/new content checks. It performs no scientific generation, adoption,
replay or publication. No full retry or recovery publisher is authorized or
submitted at this preparation checkpoint. Stage 10 remains NOT ACCEPTED.

### Read-only publication forensic validation submitted — 2026-09-24T21:45:42Z

Repair/validator executable `7353e3197adcb1b38cc821f48ee3d7da6d1f529c` is pushed
on `fix/stage10-publication-forensics`. Local validation: **1,152 safe-suite
PASS / 24 pinned-ICU skips**, **316 Stage 10 PASS / 24 skips**, static/schema/lock/
documentation checks PASS. One read-only job **1781847** is **PENDING / Priority**
at initial observation; 4 CPUs / 32 GiB / 1 h, no dependency/requeue. See the
[submission receipt](scientific_assets/stage10_publication_forensics_submission_1781847.json)
and [complete forensic ledger](stages/STAGE10_PUBLICATION_FORENSICS.md).

**STAGE10_PUBLICATION_FORENSICS_IN_PROGRESS.** The job validates preserved
checkpoints, full C01 provenance and old/new scientific equality; it performs
zero generation, adoption or publication. F01 historical exception remains
unresolved. Frozen exact-executable bindings prohibit repaired cross-SHA
adoption. Owner should later type **continue**; no repeated polling or full
retry. Stage 0–9 unchanged; operating budget UNSELECTED; HOLDOUT sealed;
production/Pelias untouched; Stage 11 NOT STARTED; Stage 10 NOT YET ACCEPTED.

### Publication forensics complete — 2026-09-25

Read-only job **1781847 COMPLETED / 0:0**, **00:16:25**, MaxRSS **452,384 KiB**.
All 1,099 checkpoints, 69,747 contexts, 418,482 decisions and 142,677 hypotheses
validate. Full C01 reconciliation: **237,263** required/actual exclusions,
**zero** missing/duplicate provenance or source-anchor violations. Old/new
hypothesis relations are exactly equal; only required decision provenance
changes. Actual-manifest registration construction/hash passes in memory; no
registration, seal, adoption, generation or publication is performed.

**STAGE10_REMEDIATION_FULL_REGENERATION_REQUIRED.** Frozen checkpoint
`execution_git_sha` equality forbids adopting old units under repaired executable
`7353e3197adcb1b38cc821f48ee3d7da6d1f529c`. See the [complete reconciliation and
ledger](stages/STAGE10_PUBLICATION_FORENSICS.md#completed-forensic-reconciliation--2026-09-25).
F01's historical exception remains unresolved; F02 receipt/primary-error defects
and the project-quota preflight gap are repaired and tested. No full retry is
authorized/submitted. Proposed 4 CPUs / 32 GiB / 36 h also requires sufficient
project quota (256 GiB reserve; last observed about 1.54 GiB).

NEXT: OWNER REVIEW AND AUTHORIZATION FOR FULL REGENERATION. Operating budget
UNSELECTED; Stage 0–9 unchanged; HOLDOUT sealed; production/Pelias untouched;
Stage 11 NOT STARTED; Stage 10 NOT YET ACCEPTED.
