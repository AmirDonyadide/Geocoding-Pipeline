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
| 10 | Bounded multi-hypothesis query generation | **DEVELOPMENT TIMEOUT — NOT ACCEPTED** | Executable `f83480d6…`; job `1772639` timed out; partial shard preserved, no committed candidate; [reconciliation](stages/STAGE10_IMPLEMENTATION.md#development-timeout-reconciliation--2026-09-19) | **NOT STARTED** |
| 11–14 proposed | Query QA → Pelias top-N → scoring → granularity/abstain | **PROPOSED — NOT STARTED** | Remaining compact replacement architecture; [pipeline specification](PIPELINE.md) | **NOT STARTED** |

Benchmark V1 contains 35,000 DEVELOPMENT and 15,000 sealed HOLDOUT rows from
the permanent 1,405-file population. The fixed 500-row qualitative subset has
fingerprint
`014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52`.

## Current checkpoint

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

Stage 7 acceptance guarantees reproducible parser evidence, not semantic truth
or trust from warning absence. Stage 8 acceptance preserves its lossless
projection and all rejected publication attempts. Stage 9 acceptance is scoped
reference evidence: Q04 conflict rates are not invalid-address rates, and its
country assessments remain unresolved under the frozen witness rule. Exact
limitations and histories remain in the linked reports.

Production Stage 2 onward, Stage 11 onward and geocoding remain unstarted.
HOLDOUT remains sealed. Documentation maintenance does not authorize execution.
