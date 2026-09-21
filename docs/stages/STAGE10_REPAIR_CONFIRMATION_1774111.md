# Stage 10 replacement confirmation 1774111 — timeout reconciliation

## Terminal result

**STAGE10_THROUGHPUT_REPAIR_CONFIRMATION_FAILED**. Confirmation **1774111**
exhausted its four-hour limit: **TIMEOUT**, elapsed **04:00:18 (14418 s)**.
The batch step was **CANCELLED / 0:15 (SIGTERM)**, elapsed 14419 s. The parent
job's accounting exit `0:0` does not override TIMEOUT or imply success.
One terminal accounting query was made on owner continuation, 2026-09-21.
No replacement, full DEVELOPMENT run, resource increase or code repair followed.

- Repaired computation: `808123bb145107d7b025471b3b02869cc95fb44a`.
- Confirmation harness: `68ce5fbd61c242fd44bdf9094a892d2d040cd628`.
- Submission reporting: `525ea7eb82362f55788b44e8e9ca04ffe8fb4c3f`.
- Requested: 4 CPUs, 32 GiB, four hours; no dependency/requeue.
- Accounting: 80 allocated CPUs on `node18-012` reflects the allocation
  topology, not measured use of 80 cores. TotalCPU 04:58:30, UserCPU 04:42:07,
  SystemCPU 16:23.034. Average accounted CPU use is about 1.24 core equivalents.
- Scheduler batch MaxRSS: **3972984 KiB (3.789 GiB)**. Application snapshots:
  **5059920 KiB (4.826 GiB)**. Distinct measurement sources; the application
  value is the highest preserved snapshot, not an unavailable terminal receipt.
- Site-local start/end: `2026-09-20T23:14:32` / `2026-09-21T03:14:50` (UTC+02).

Protected attempt:

`/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage10/confirmations/stage10_repair_20260920T190012Z_68ce5fbd61c2`

The attempt, all unit outputs, incomplete resume fixture, database and logs are
preserved. The exact detached checkout remains clean. Only sanitized aggregate
JSON was transferred locally; no protected selections, rows, query strings,
Parquet, database or WAL payload was opened or copied locally. Login-node work
was accounting, metadata/hashes and explicit aggregate-file transfer. Protected
computation occurred only in the already authorized job.

## What completed and what did not

| Check / pass | Contexts | Decisions | Hypotheses | Completed units | Outcome |
| --- | ---: | ---: | ---: | ---: | --- |
| Preserved old/new gate | 16 | 96 | 35 | Not a checkpoint pass | Exact complete-row equality PASS |
| First, 64-context units | 4424 / 4424 | 26544 | 9065 | 70 / 70 | Full generation and validation completed |
| Repartition, 32-context units | 4424 / 4424 | 26544 | 9065 | 139 / 139 | Same complete logical relations PASS |
| Resume, last durable receipt | 1984 / 4424 | 11904 adopted | 4035 adopted | 31 / 70 | Partial; full reconciliation NOT completed |

First-pass units are 69 × 64 + 8; repartition units are 138 × 32 + 8.
The durable pass receipts are written only after prefix/unit validation,
map-back/integrity checks, six decisions per context, and logical equality
checks in the actual harness. No context loss, orphan/identity/engineering-bound
failure was reported in either completed pass. Local aggregate reconciliation
also verifies all receipt sequences, counts, per-unit limits and hashes.
This review does not rerun protected validators outside the allocation.

The common relation identities are:

| Relation | Rows | Logical SHA-256 |
| --- | ---: | --- |
| query_hypothesis | 9065 | `547f880b41f0e061b92e2f7822f46bfa707be87d970543df64020ea5d2b47aae` |
| query_family_decision | 26544 | `2ab22ee9d079d62cecadd02bae9b86779a01c760a0bc914e8daeebc2ff6a94d7` |

The exact historical gate compares full protected rows inside Goethe, including
IDs, representations, decisions/reasons, transformations, lineage, convergence
and Stage 9 gating. First/repartition equality covers all 4424 contexts through
the complete logical fingerprints. There is no complete original pre-repair
first-shard golden result; no full old/new equality claim is made.

Resume has **32 copied unit completion files**, but only **31 reconciled,
indexed completion receipts**. Core code copies and validates a prior unit before
reconstructing its contexts and appending its completion index/progress record.
The additional copied file is not proof that the 32nd unit was reconciled.
Last confirmed progress is 1984 contexts, not 2048. Prefix aggregate row counts
match the corresponding first-pass units exactly. The intended incomplete tail
unit 69 remains preserved and was **not reached**; its regeneration, final resume
logical equality and final fixture-preservation check remain unproven.

`confirmation_result.json`, `resume_pass.json` and the resumed prefix completion
record are absent. No static failure receipt was durably emitted before process
termination. Scheduler stderr confirms cancellation for time limit. The exact
in-flight operation and why Python finalization did not finish are unknown;
the last completed progress record is authoritative, not an inferred terminal
counter. No successful confirmation or zero-total-failures claim is possible.

## Measured timing and scopes

All durations below are seconds, from immutable monotonic phase snapshots.
Inclusive timers overlap; do not sum them as disjoint costs.

| Operation | First pass | Repartition | Resume through 31 completed units |
| --- | ---: | ---: | ---: |
| Whole replay, including coalescing | 5579.365 | 5588.608 | Incomplete; last progress at 2421.140 |
| Completed checkpoint interval, before final coalescing | 5503.040 | 5510.890 | 2421.140 |
| Separate final validation | 52.008 | 52.905 | Not reached |
| Context construction | 5451.260 | 5377.284 | 2396.333 |
| Witness certificate total | 5323.204 | 5290.328 | 2338.945 |
| Certificate serialization | 402.345 | 398.812 | 176.834 |
| SQL execute | 2848.611 | 2874.520 | 1251.829 |
| SQL cursor creation | 69.322 | 68.810 | 30.347 |
| Arrow-reader creation | 88.803 | 88.025 | 39.073 |
| Identity hashing | 4.683 | 4.675 | 1.176 |
| Q5 family / alignment | 0.133 / 0.104 | 0.122 / 0.093 | No family generation |
| Q6 family / actual ICU | 0.148 / 0.015 | 0.149 / 0.015 | No family generation |
| All family generation | 2.235 | 2.224 | No family generation |
| Output writes | 5.428 | 5.411 | Prior rows adopted |
| Output close and unit checkpoints | 39.087 | 41.451 | Prior units validated/copied |
| Database checkpoints | 41.931 | 77.632 | 19.022 |
| Coalescing, inclusive of prefix validation | 76.311 | 77.709 | Not reached |
| Completed-unit context reconciliation | Not applicable | Not applicable | 2397.595 |

Setup is excluded from all replay rates. The parser-certificate preparation
guard passed before the historical gate. Both completed replay receipts and all
partial resume observations report **zero parser-preparation calls** and no
context-index preparation during replay: the prepared index was reused.
However, the new preparation/gate-overall/population-setup timers were stored
only in the final in-memory report. Their exact durations were lost when that
report was not written. Separate durable phase records are a remaining
observability defect; do not substitute job 1774012's 554.549-second parser
preparation as a measurement from this job.

An approximately **635-second pre-replay interval** can be inferred from the
job start, first-pass last-receipt modification time and that receipt's
monotonic elapsed interval. This is a coarse filesystem/accounting inference
covering runtime checks, copy/recovery, parser/context preparation, gate and
selection setup; it is neither a measured parser duration nor an exclusive
setup timing. The historical gate's durable snapshot does retain its component
timers: 16 certificate calls / **0.622899 s**, context construction **1.056009 s**,
SQL **2.723763 s**, two ICU calls / **0.000216 s**.

The same gate previously measured certificate work **13.844582 s** (1773901)
and **0.610358 s** (1774012). Those observations retain their instrumentation
and workspace differences. The short-gate gain does not describe the much
larger reference-witness workload of the first shard.

## Sustained throughput

Checkpoint thirds use exactly the original deterministic order; no population
was selected or changed using protected content. Rates exclude setup, final
coalescing and final validation; whole-replay averages are separately
**0.792922** and **0.791610 contexts/s**.

| Pass / portion | Contexts | Contexts/s | Decisions/s | Hypotheses/s |
| --- | ---: | ---: | ---: | ---: |
| First EARLY | 1472 | 0.912609 | 5.475653 | 1.876056 |
| First MIDDLE | 1472 | 0.678349 | 4.070094 | 1.378357 |
| First LATE | 1480 | 0.860412 | 5.162470 | 1.771983 |
| Repartition EARLY | 1472 | 0.912650 | 5.475902 | 1.876141 |
| Repartition MIDDLE | 1472 | 0.684376 | 4.106258 | 1.390604 |
| Repartition LATE | 1480 | 0.847098 | 5.082588 | 1.744564 |
| Resume EARLY, adoption/reconciliation | 1472 | 0.925074 | 5.550442 | 1.901680 |
| Resume MIDDLE, partial only | 512 | 0.616930 | 3.701580 | 1.215786 |
| Resume LATE | Not reached | — | — | — |

The middle portions are materially slower, then throughput recovers. Late/early
ratios are 0.942804 and 0.928172; this is not a monotonic lifetime collapse.
The matching partition pattern suggests workload composition contributes, but
per-context evidence complexity was not instrumented, so this remains an
inference. The original 24-hour run's precise degradation mechanism is still
unresolved. Completing the formerly problematic shard in about 93 minutes is
positive evidence; it does not make the whole failed confirmation successful.

## Remaining certificate and resume cost

Each complete pass made **4424 certificate calls / 4423 builds**,
**16105520 selector-add attempts**, **4636651 buffer insertions**,
**7486356 certificate serialization calls**, and **zero selector SQL inserts**.
First/repartition SQL execution counts were **2329428 / 2329774**, roughly
527 calls/context. Actual ICU calls were 139 and Q5 alignment calls 4312 per
pass. The certificate path accounts for **95.41% / 94.66%** of replay wall time;
Q5, Q6, output writing and hypothesis identity hashing are not dominant here.

Invariant-registry encoding is **1540 calls per pass** despite the accepted
pack having only three registry rows. Re-encoding is therefore still present.
Static review finds that registry/capability/object material shares a bounded
16-MiB, 256-entry cache, with oversized-entry non-admission. Exact-key SQL is
still executed on misses. These mechanisms permit repeat work; the receipts
do not distinguish individual eviction from non-admission or quantify every
lookup's cause. Complete-certificate reuse also produced only one cache hit.
No arbitrary cache expansion or incomplete-key caching is proposed as a proven
fix. Any future repair must preserve complete witness certificates/lineage.

Resume reconstructs full contexts and certificates even for already validated
units: the core calls `work.contexts` to verify map-back after copying each unit.
Measured reconciliation was **2397.595 / 2421.140 s (99.03%)**, certificate work
2338.945 s, for 1984 adopted contexts with **zero family-generation calls**.
Resume supports durable progress but is computationally expensive. This is a
confirmed residual cost, not a reason to omit map-back or scientific validation.

## WAL, memory and durability

First and repartition sampled WAL high-water marks were **4679084 bytes
(4.462 MiB)**. Every durable checkpoint observation reports WAL zero after the
database checkpoint. Replay snapshot database-checkpoint counts were 140/141,
separate from scientific unit counts 70/139. The same peak first appears after
3200 contexts (unit 50 at size 64, unit 100 at size 32), with no later increase
in the sampled maximum. Late throughput recovers despite that higher cumulative
maximum; no WAL-induced slowdown is established.

Partial resume sampled WAL maximum was **16721 bytes**, also zero after each
observed checkpoint. The WAL is absent after the timed-out job; database size
is **2567974912 bytes**. These are samples and terminal filesystem metadata,
not proof that the incomplete resume database passed recovery validation.
No long explicit replay transaction is recorded; diagnostic writes remain
bounded autocommit batches. Exact setup-transaction duration was lost with the
final report. Whole-process I/O deltas are unavailable for the same reason.

Application high-water RSS remained 5059920 KiB throughout preserved gate and
checkpoint records. Neither it nor scheduler accounting indicates exhaustion
of the 32-GiB request. High-water constancy does not measure current memory or
exclude unsampled transient peaks. No continuous I/O/lock utilization sample
exists; nested SQL and certificate CPU measurements support a compute-heavy
remaining path but do not identify an exclusive hardware bottleneck.

## Complete P01–P12 disposition after replacement confirmation

| ID | Disposition | Evidence / remaining limitation |
| --- | --- | --- |
| P01 | MITIGATED; major residual | Indexed/batched operations remain, zero selector SQL inserts, but ~2.33 million SQL executes and ~2850 s SQL time/pass. Exact-key witness lookup amplification remains actionable. |
| P02 | FIXED for repeated preparation | Prepared parser index reused; zero preparation calls during both full replays and partial resume. Current exact one-time duration lost; earlier 554.549 s retains its prior-job scope. |
| P03 | MITIGATED; prior FIXED claim narrowed | Gate improvement reproduced with exact rows. Full-shard certificates still ~95% of replay; 1540 invariant-registry encodes, 4423 builds/pass. Original timeout attribution unresolved. |
| P04 | MITIGATED | 70/139 complete units with exact logical equality; 31 units safely reconciled in resume. Full resume/incomplete-tail regeneration untested; adoption still reconstructs costly certificates. |
| P05 | OBSERVABILITY_ONLY; incomplete durability | Unit/pass receipts survive and locate progress. Whole-result/failure receipt and setup timers did not survive timeout; terminal in-flight location unavailable. |
| P06 | NOT_CAUSAL in measured shard | Q5 alignment ~0.1 s and ICU ~0.015 s/pass; family generation ~2.2 s. No science/transform change indicated. |
| P07 | OBSERVABILITY_ONLY; resource review required | Four-hour limit exhausted during third context traversal. No memory exhaustion evidence; no blind walltime increase or full-run recommendation. |
| P08 | MITIGATED; measured | WAL sampled max 4.462 MiB, clears at every observed checkpoint; no cumulative growth beyond matched late-prefix peak. Incomplete resume recovery not validated. |
| P09 | MITIGATED | Exact original 4424-context shard completed twice; partition hashes equal, old/new 16-context gate passes. Full old-shard golden absent; resume remains partial. |
| P10 | OBSERVABILITY_ONLY | Immutable snapshots confirmed (earlier SQL counts stay unchanged after validation); CPU/RSS scope and sampled WAL limits explicit. Durable setup/final I/O evidence missing. |
| P11 | DEFERRED_WITH_JUSTIFICATION | Full candidate publication/reopen not invoked; each retained scientific replay would reconstruct contexts/certificates. Full-run cost remains substantial and unmeasured. Validation must not be weakened. |
| P12 | INFORMATIONAL | Original evidence and science unchanged, no candidate/acceptance/additional job. Operating budget UNSELECTED; HOLDOUT sealed; production/Pelias untouched; Stage 11 NOT STARTED. |

These dispositions supersede any inference that the small gate or synthetic
tests proved all performance issues resolved. No ledger item is discarded.
They preserve the [original repair record](STAGE10_PERFORMANCE_REPAIR.md) and
[previous failure reconciliation](STAGE10_REPAIR_CONFIRMATION_1774012.md).

## Complete new bounded findings and next boundary

| ID | Classification | Finding / disposition |
| --- | --- | --- |
| T01 | PERFORMANCE_ROOT_CAUSE of current replay cost | Witness certificate construction remains dominant, with extensive exact-key SQL and repeated registry encoding. Confirmed current cost, not proven sole cause of the original 24-hour degradation. OPEN for owner-reviewed remediation. |
| T02 | PERFORMANCE_SECONDARY / CHECKPOINTING | Completed-unit resume reconstructs full contexts/certificates, consuming 99.03% of its confirmed interval. OPEN; preserve exact map-back/validation in any future reorganization. |
| T03 | RESOURCE / REVIEW_HARNESS | Four-hour envelope did not cover setup plus two ~93-minute passes and an expensive third traversal. No automatic longer job; unresolved major costs must inform a later execution design. |
| T04 | OBSERVABILITY | Setup timers and final failure metadata lived only in memory until finalization. OPEN: durable per-phase snapshots are needed to preserve evidence across forced termination. |
| T05 | CHECKPOINTING / INFORMATIONAL | 31 durable resume completions versus 32 copied unit markers; incomplete tail and final resume checks not reached. Preserve and do not adopt the extra copied unit as reconciled. |

H01's indexed-table dependency is fixed and the actual setup ran. H02 now
covers that path; cluster first/repartition execution also passed. H03's
immutable snapshots are confirmed. No new scientific candidate defect is
observed in completed comparisons. T01–T05 remain bounded review findings;
no implementation change was made during this reconciliation.

**Conditional extrapolation, not a validated forecast:** assuming other
contexts cost the same as this one fixed shard, a single generation pass over
69747 contexts would take about **24.43 hours**, before input preparation,
remaining validation and publication/reopen scientific replays. Other shards,
cache reuse, reference complexity and contention are unmeasured. This does not
justify a 24/48-hour request, a production-scale claim or a full DEVELOPMENT
retry. No new full-run resources/walltime are recommended while major residual
costs and the incomplete confirmation remain unresolved.

**NEXT: OWNER REVIEW OF THE REMAINING PERFORMANCE AND CONFIRMATION LEDGER.**
The single replacement authorization is consumed. No new job, full DEVELOPMENT
run, science change, candidate publication or Stage 10 acceptance follows.

## Sanitized evidence and validation

- [Original immutable equivalence gate](../scientific_assets/stage10_repair_equivalence_gate_1774111.json), SHA-256 `594b320ed40ddc3a0402eb59fa4d2c97e7b0a327231f9bb45fd314263d519f9a`.
- [Original immutable first-pass receipt](../scientific_assets/stage10_repair_first_pass_1774111.json), SHA-256 `09120f9d72512f105cb7e8d23eb210a2ca52b5404f853207a0c2e1953d77acac`.
- [Original immutable repartition receipt](../scientific_assets/stage10_repair_repartition_pass_1774111.json), SHA-256 `91b76483622d532e147d04b3c8e5cfcd91516ae56f53e1a8cfcae346a0603cc3`.
- [All 31 sanitized resume observations with original hashes](../scientific_assets/stage10_repair_resume_progress_1774111.json); final original receipt SHA-256 `8b51d312b20c245892276f44700fe08319694983d98f073000136e4b48896bba`.
- [Accounting and filesystem reconciliation](../scientific_assets/stage10_repair_accounting_1774111.json), [submission receipt](../scientific_assets/stage10_repair_confirmation_submission_1774111.json) and [review hash inventory](../scientific_assets/stage10_repair_review_inventory_1774111.json).

Original portable receipt hashes were checked against Goethe metadata.
Aggregate checks reconcile all pass/unit counts, role-independent safety bounds,
window totals, monotonic progress, zero post-checkpoint WAL, zero repeated parser
preparation/selector SQL, immutable timer snapshots, exact gate totals and
partition relation equality. Resume prefix counts match completed first-pass
units; final resume success is deliberately not inferred. Document/link/hash,
stage-report, implementation-inventory, privacy and diff checks pass. The prior
262 focused / 1036 safe tests are historical pre-submission evidence, not rerun
claims for this reporting-only change. Stage 0–9 and all executable/scientific
files remain unchanged.
