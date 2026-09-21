# Stage 10 throughput diagnostic plan and evidence

Owner authorization on 2026-09-19 permits one bounded diagnostic, no full
DEVELOPMENT retry, science change, candidate publication, HOLDOUT, production,
Pelias or Stage 11. Baseline is `ba03e17b406c5f9c953359e6efce9fbc4b8d2e74`;
the executable being investigated is `f83480d60449bcc904c0c622e394e12df3c3f2d9`.
The scientific operating budget remains UNSELECTED.

## Evidence before submission

The [timeout record](STAGE10_IMPLEMENTATION.md#development-timeout-reconciliation--2026-09-19)
binds the single original submission, accounting, logs, attempt and runtime.
Shell-only reopening confirms the same database (1,517,826,048 bytes), WAL
(3,802,981,496 bytes), and partial decision file (2,172,840 bytes). Its last four
bytes are `80 01 00 00`, not the Parquet `PAR1` footer; decoding row counts is
therefore not justified. Last decision-file modification was
2026-09-18T16:41:18.002906471Z, WAL 2026-09-18T22:47:26.537344056Z.
Two modification times do not establish steady/linear growth.

The owner-authorized extended terminal accounting read reports TotalCPU
`1-13:05:49`, UserCPU `1-11:56:08`, SystemCPU `01:09:41`, batch MaxDiskRead
`4157022.74K`, MaxDiskWrite `5562802.71K`, MaxVMSize `8815004K`. TotalCPU / elapsed
is about 1.545 CPU equivalents, not utilization of all 80 allocated CPUs.
This supports substantial CPU work but does not identify Python versus DuckDB,
I/O wait or a dominant phase. Disk counters are scheduler measurements, not
complete physical PanFS transfer accounting. No linear throughput inference.

Protected database queries/recovery require a compute node under repository
policy. They cannot be performed on the login node before submission. The
one diagnostic therefore begins by inspecting an exclusive verified copy of
the database/WAL; no separate inspection job or original-database connection.

## Static review ledger before measurement

| ID | Classification | Evidence and measurement needed |
| --- | --- | --- |
| P01 | PERFORMANCE_SECONDARY, dominance unproven | `sql_rows` creates a cursor/query and converts Arrow at batch size one. Source-reference, component, member and public-object access recur per context/cache miss. Indexed tables exist; do not assume full scans. Measure execute/fetch/cursor time and sanitized plan operators. |
| P02 | PERFORMANCE_SECONDARY, dominance unproven | Parser certificate traverses all candidate components and rebuilds the Stage 8 component schema for each row. A public Mac microbenchmark took 0.070489 seconds for 200 schema calls under cProfile; it is not a cluster throughput result. |
| P03 | PERFORMANCE_SECONDARY, dominance unproven | Witness certificate deletes/rebuilds a disk table per cache miss, with per-witness/object/ancestor/registry inserts and repeated member traversal. Cache is bounded at 256 entries; measure hits/misses, SQL insert/commit time and witness traversal. |
| P04 | CHECKPOINTING | Exactly 16 one-hex-prefix shards; complete checkpoint only after all contexts, writer close, relation hashing and validation in a shard. Average allocation is 69,747/16 = 4,359.1875 contexts, not measured first-shard count. Width was an engineering partition choice, not a calibrated restart bound. No checkpoint policy is changed here. Frozen IDs/order allow finer operational partitions later, subject to full equivalence tests. |
| P05 | OBSERVABILITY | No within-shard progress/termination receipt; DB diagnostics are inserted before yielding a context. After recovery, N diagnostic rows bounds completed generation calls between max(0,N-1) and N if distinct and confined to shard 0. Buffered output prevents exact persisted hypothesis counts. |
| P06 | INFORMATIONAL | ICU runtime/handles are initialized once; Q5 regexes are module constants; context convergence compares at most six family slots. No global context dedup, candidate×global Python list or per-record fsync found. Q5 can scan components twice; Q6 makes repeated script passes. Measure before assigning dominance. |
| P07 | RESOURCE | Full input validation preceded attempt creation; preparation completed before shard 0 creation. Most elapsed time followed shard creation. Snapshot WAL size alone cannot prove one long uncommitted transaction: witness operations commit per certificate and diagnostics autocommit while the outer cursor remains open. Inspect recovered counts; distinguish WAL bytes from live transaction state. |

The exact bottleneck is not proven. No runtime extrapolation or implementation
repair is justified yet.

## Diagnostic design

Goal: recover aggregate progress evidence and time the exact existing generation
functions without publishing a candidate. Implement in separate
`stage10_throughput_diagnostic.py`, one SBATCH launcher, and synthetic tests.
No existing executable, schema, identity, family, reference or ICU module changes.

- Shared Goethe/SLURM guard first; exact pushed detached diagnostic Git SHA;
  frozen implementation inventory verifies all old executable files unchanged.
- Bind original attempt SHA, accepted Stage 6/8/9 manifest hashes, ICU lock and
  readiness, fixed failed-work path and fixed diagnostic output parent.
- Copy database/WAL with exclusive files, `0600`, original no-follow checks,
  streaming SHA-256 and post-copy rehash; compare source metadata before/after.
  Open only the copy. Recovery can alter only this diagnostic copy.
- First inspect all context-key counts, first-shard count, recovered diagnostic
  counts, role distributions, selector table size and partial-file footer/count
  availability. Never print row IDs, values, SQL parameters or database contents.
- Select the lowest unsigned context ID in each existing one-hex-prefix shard:
  target **16** contexts, at most one per prefix, globally ordered. Selection
  uses only immutable IDs, no protected text, eligibility, country or script.
  Keep IDs private; report the selection fingerprint and aggregate size only.
- Time bounded upstream reads for these selected source/candidate IDs from the
  original Stage 8/9/6 views: at most 64 MiB or 100,000 decoded rows per view,
  respecting a whole Arrow scalar (no scientific truncation). This diagnoses
  loading and conversion; it does not repeat the original full logical-input
  certification, whose walltime would exceed the diagnostic target.
- Reuse the copied prepared indexed tables, with fresh bounded caches and
  separate diagnostic selector/diagnostic state. Run exact `contexts` and
  `generate` per selected prefix and take only the predeclared minimum ID.
  Each context has a **45-second diagnostic cap**, never an eligibility rule;
  native queries receive interruption first, with one second of Python-alarm
  grace to avoid a tested simultaneous-signal race. All nested cursors are
  interrupted, not only their parent connection.
  record incomplete timings and continue only after clean rollback/cursor close.
- Q1–Q6 run exactly as frozen on completed selected contexts. Q3/Q4/Q5/Q6
  eligibility remains evidence-based. If the ID-selected population has no
  eligible family example, report zero coverage; do not change selection.
  Exact public ICU vectors additionally exercise the locked Q6 bridge and are
  reported separately from DEVELOPMENT timings.
- Record wall/CPU time, fixed query classes, cursor/Arrow time, function-only
  cProfile totals (no locals/arguments), certificate/SQL/ICU/Q5/hash/serialization
  calls, writer-close/fsync time, RSS and `/proc/self/io` deltas. EXPLAIN output
  is reduced to operator names/counts; all filters/literals/extra-info discarded.
- Write diagnostic protected serializations in ordinal directories and a
  sanitized progress report per completed/limited context. No Stage 10 manifest,
  registration, publication key adoption or `_COMMITTED`; no candidate counts
  claimed for the failed run from newly generated diagnostic rows.
- Soft total limit 25 minutes; hard SLURM limit 30 minutes, 4 CPUs, 32 GiB,
  one node/task, general1/footprint, no dependencies/requeue. Time-capped work is
  labelled incomplete and cannot establish steady throughput. No blind total
  DEVELOPMENT runtime extrapolation. Failure/limits preserve all diagnostic work.

## Implementation and validation plan

1. Test exclusive copy, immutable original, symlink rejection, ID-only selection,
   sanitized timing/plan data, guard-before-read, partial footer abstention,
   diagnostic deadlines and exact instrumented/uninstrumented synthetic output.
2. Implement those helpers and the compute-only evidence-recovery / timing CLI.
3. Add tests for WAL recovery on copied synthetic data, function-profile privacy,
   original file immutability, no candidate publication and launcher guards.
4. Run diagnostic and existing Stage 10 synthetic tests, safe repository tests,
   scoped typing/lint/format, old inventory/doc/hash checks and shell syntax.
   Review instrumentation fidelity, rollback, privacy, bounds and copy isolation.
5. Commit/push diagnostic branch; clean detached Goethe checkout; exclusive
   diagnostic destination and submission receipt. Submit exactly once. One
   PENDING/RUNNING observation means report and STOP; terminal result is analyzed
   only at the authorized continuation boundary. No full DEVELOPMENT retry.

The owner already supplied the execution method and authorized this diagnostic;
the plan adds no approval gate. The existing session/workspace is retained,
on branch `diagnostic/stage10-throughput`, preserving the frozen executable.

## Complete diagnostic harness review

| ID | Classification | Resolution |
| --- | --- | --- |
| H01 | REVIEW_HARNESS | Simultaneous Python alarm/native query interruption could race and leave a synthetic query running. Native interruption now precedes the alarm by one second; repeated isolated deadline tests and nested-cursor interruption test cover it. Hung local synthetic processes were terminated; no SLURM job was cancelled. |
| H02 | REVIEW_HARNESS | DuckDB wraps some Python alarms as RuntimeError. Only the local deadline event permits classification as a diagnostic limit; arbitrary exceptions remain failures. |
| H03 | REVIEW_HARNESS | Temporary selected-ID views were invisible to the independent streaming cursor. Persist them only inside the recovered diagnostic copy; full synthetic input-read integration passes. |
| H04 | REVIEW_HARNESS | `disabled_filesystems` cannot be supplied before DuckDB database startup. Disable extension autoload/install at connection, then apply the existing filesystem block immediately after recovery; the enclosing offline-network guard also applies. Recovery spill path is private and set before startup. |
| H05 | OBSERVABILITY | Metrics are inclusive/nested; do not sum overlapping durations. Profile output allows only repository file/function names, line numbers and numeric counts/times; no arguments, locals, SQL text, raw plan filters or caller objects. |
| H06 | CHECKPOINTING | Diagnostic serialization closes per completed context for recoverable evidence. That timing is explicitly separate from the failed executable's shard-level writer/checkpoint behavior; it makes no claim of identical physical files or approved candidate checkpoint change. |
| H07 | INFORMATIONAL | Copied WAL recovery may commit recovered transactions and change copy bytes. Original files are never opened by DuckDB, and synthetic crash/WAL tests verify originals byte-for-byte. No interrupted shard adoption. |
| H08 | RESOURCE | Soft total and per-query/context limits are measurements, not candidate suppression. Full validation of all upstream rows is intentionally not repeated; recovered prepared state and bounded original-view reads are separate timed phases. No total-run scaling claim from an ID-minimum slice. |
| H09 | INFORMATIONAL | Instrumented contexts/family output equals uninstrumented output on complete synthetic inputs. Original implementation files and frozen design/runtime inventory remain byte-identical. All Q-family rules, IDs and safety ceilings remain unchanged. |

Any limited context has its partial function timings recorded and is excluded
from completed-output counters. A context may be fully computed but not fully
serialized before its limit; those counters deliberately require both. Unexpected
exceptions stop the diagnostic with static failure codes and preserve work.
No root-cause conclusion or repair is claimed before the diagnostic result.

## Validation before submission

17 focused diagnostic tests pass, including actual copied synthetic WAL recovery,
source-byte preservation, nested-query deadline/reuse, transaction rollback,
ID-only selection, partial-file abstention, profile/error privacy, exact output
equivalence and bounded upstream-view integration. The full Stage 10 selection
passes **232 tests** with the matching public Mac ICU runtime. The complete safe
collection passes **1,006 tests** in the existing Python 3.14.3 environment;
the remaining 62 ICU/runtime tests are included in the 232 focused total, as in
the prior implementation validation. No protected input is used locally.

Strict mypy passes 122 source/Stage 10 test/validator modules. Maintained-tree
Ruff lint/format, original Stage 10 inventory/schema/runtime/design checks,
stage-report validation, CLI help, SBATCH syntax and diff/privacy checks pass.
Historical Stage 0–9 broad-test typing/archive-style limitations remain exactly
as recorded; no exclusion or runtime guard was weakened.

Only standalone diagnostic code/tests/launcher and sanitized documentation are
changed. All original executable inventory entries remain byte-identical.
Error reports retain static codes, class and public file/line frames only;
raw native engine messages cannot expose protected values.

After a context time cap, the diagnostic closes its stream, rolls back any
remaining copied-workspace transaction, proves a new transaction can begin/end,
and resets the bounded caches. A synthetic interrupted-transaction test verifies
that original context-key rows remain present and no state contaminates the next
measurement. This changes diagnostic cleanup only, not candidate execution.

## Completed diagnostic reconciliation — 2026-09-20

**STAGE10_THROUGHPUT_DIAGNOSIS_COMPLETE.** The dominant measured generation cost
is reference-witness certificate construction, particularly repeated complete
registry encoding and selector inserts. **The original 24-hour timeout is not
fully explained.** The 16-context slice is substantially faster than the failed
run's recovered average and does not cover large parser-component populations,
long-running cursor/transaction retention, or elapsed-time-dependent slowdown.
No repaired executable, additional diagnostic, full DEVELOPMENT retry, changed
walltime or candidate publication is authorized by this evidence.

### Execution and evidence binding

- Diagnostic executable: `622c0589d1dc6c7fd16224a1c46a1d5249bd4bc4`, pushed on
  `diagnostic/stage10-throughput`; clean detached Goethe checkout.
- Exactly one diagnostic submission: job **1773901**, UTC
  `2026-09-19T12:32:04Z`; first observation PENDING / Resources, then STOP.
- One terminal accounting inspection on the owner's continuation: allocation
  and batch **COMPLETED / 0:0**, elapsed **102 seconds**. Scheduler start/end
  are `2026-09-19T20:12:48` / `2026-09-19T20:14:30`, retained without adding
  timezone information absent from the accounting fields.
- Request: one node/task, 4 CPUs, 32 GiB, 30 minutes, general1/footprint,
  no dependencies/requeue. Allocation reports 80 CPUs; this is not 80 worker
  threads. TotalCPU `01:31.076`, UserCPU `01:13.385`, SystemCPU `00:17.691`.
- Batch MaxRSS **2552312K** (2.43 GiB); application `RUSAGE_SELF` maximum
  **7643892 KiB** (7.29 GiB). Both measurements are retained. Their different
  collection methods/windows are not reconciled by available evidence; do not
  substitute the smaller scheduler value for the application high-water mark.
- Batch MaxDiskRead `19079574.86K`, MaxDiskWrite `8989951.63K`. Application
  I/O deltas include `rchar=19987091571`, `wchar=9208035265`,
  `read_bytes=33660928`, `write_bytes=9208344576`. These cover snapshot copying,
  recovery and measurements; they are not generation-only physical PanFS I/O.
- Stdout contains only `DIAGNOSTIC_COMPLETE`; stderr is empty. Hashes:
  stdout `5fa7f12b5ca68133362a61cb80e5cdee66ff7a85f87d55309f5f2e638646a0cb`,
  stderr `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

Private output:
`/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage10/diagnostics/stage10_throughput_20260919T122820Z_622c0589d1dc`.
It resolves through the established PanFS project anchor. The copied workspace,
private selected IDs and protected serializations remain there. Only the
[sanitized aggregate/function report](../scientific_assets/stage10_throughput_diagnostic_1773901.json)
is copied into Git, byte-identical with SHA-256
`260355d945ee7a2104848aa29a06989a3d0229223bf07b4cff6094a1f30dfed1`.
This is observational evidence, not a normative scientific asset or candidate
manifest. The frozen scientific/executable hash inventories are unchanged.

The original database/WAL were copied and hash-verified before recovery:

| Preserved file | Bytes | SHA-256 |
| --- | ---: | --- |
| `context.duckdb` | 1517826048 | `693d4c42c47cb3b4463dbb7f0f7730879213fd23b1118e1f075e1b2cdc65818a` |
| `context.duckdb.wal` | 3802981496 | `7290dc3872355d4efc5d0d7c3f4ba9fcf14ebb8aad84fcd3a8d628d07bf1c99b` |

Original attempt hash, file sizes, modes and modification timestamps match the
pre-diagnostic observations on reopening. DuckDB accessed only the copy.
`preserved_evidence.json` SHA is
`27dae34a7209a6dfe146f2b86cd1d64c1454d25ff2586da1cfd125ee21ac3cfe`.
Runtime/hash/input gates passed; six public ICU vectors passed. No candidate
registration, manifest, commit seal or adoption was attempted.

### Recovered original progress and observed rates

| Quantity | Recovered result |
| --- | ---: |
| Total query contexts | 69747 |
| STANDARD / NATIVE contexts | 34822 / 34925 |
| Exact first-shard allocation, prefix `0` | 4424 |
| Distinct diagnostic rows, all in shard `0` | 3365 |
| Completed generation calls | 3364–3365 |
| Generated family decisions | 20184–20190 |
| Exact generated/persisted hypothesis count | Unknown; upper bound 16825 |
| Readable completed partial-decision file row count | Unknown; missing closing Parquet footer |
| Complete shard checkpoints | 0 |
| Recovered selector rows | 517 |
| Prepared parser components / source-reference rows | 6106088 / 933012 |
| Prepared match members / public objects | 554366 / 1844460 |

The diagnostic-row insert occurs immediately before yielding a context. Thus
all but possibly the last yielded context completed generation; the last may
have completed too. These are bounds on calls/rows produced, not adopted output
counts. Buffering and the missing Parquet footer prevent exact durable output
counts. Recovery finding committed diagnostic rows disproves the interpretation
that all progress remained inside one uncommitted generation transaction.
It does not establish the state of the final interrupted certificate transaction.

Assuming original scheduler times use the same `+0200` site clock as the
explicitly offset file timestamps, approximately **69m09s** preceded attempt
creation (runtime/input validation and other setup), **2m08s** elapsed from attempt creation to shard
creation, and **22h49m03s** remained in shard 0 before SIGTERM. Those are phase
envelopes from timestamps, not isolated function timings; scheduler fields lack
their own timezone offset. Under that clock assumption, the last interval is
82142.519 seconds. Shard completion was **76.040–76.062%**.

**MEASURED, whole-job average:** 0.038926–0.038938 completed contexts/second
and 0.233557–0.233626 generated decisions/second over the scheduler's 86420
seconds, including startup. This needs no cross-clock assumption.
**DERIVED, generation-interval average under the clock assumption above:**
0.040953–0.040965 completed contexts/second,
0.245719–0.245792 generated decisions/second, or 24.411–24.418 seconds per
completed context across that interval, including any last incomplete work.
An exact hypotheses/second rate cannot be derived. No original per-context
time series exists, so steady progress, stalls and linear output growth are
unknown. **EXTRAPOLATED total DEVELOPMENT runtime: not justified.**

### Measured diagnostic phases and coverage

All 16 predeclared minimum-ID contexts completed; zero time caps, transform
failures or reported technical failures. Selection digest:
`fb285755e571bca37c7e3245a806ffee7cea180b2d1aab3783dee662a265763d`.
There were 96 Q1–Q6 decisions and 35 hypotheses. Eligible family counts were
Q1=7, Q2=9, Q3=16, Q4=8, Q5=0, Q6=2: 42 eligible contributions converged to
35 intents. These diagnostic rows are not a Stage 10 DEVELOPMENT candidate.
Q5 eligibility logic ran, but no eligible whole-line deletion was measured.
Two protected eligible Q6 calls and six separate public ICU vectors ran.

| Timed phase | Wall seconds | Interpretation |
| --- | ---: | --- |
| Runtime verification | 3.763 | Exact frozen runtime gate, not pure ICU initialization |
| Verified snapshot copy | 29.885 | Diagnostic overhead, absent from original generation |
| Copied WAL recovery | 24.732 | Diagnostic overhead |
| Preserved aggregate inspection | 0.066 | Includes deterministic slice selection |
| Bounded upstream reads, total | 9.894 | Source views, not full upstream recertification |
| Stage 9 selected-view read | 7.924 | 450 decoded rows / 424792 bytes, included above |
| Context construction | 17.720 | 16 measured contexts |
| Witness certificate | 13.845 | Included in context construction: **78.13%** |
| Parser certificate | 0.116 | Included in context construction; only 45 components |
| Q1–Q6 family generation | 0.095 | Evidence eligibility work also occurs in context construction |
| Q3 / Q4 / Q5 decision function totals | 0.00165 / 0.00163 / 0.00054 | Not complete upstream evidence cost |
| Q6 decision functions / actual ICU transform | 0.06720 / 0.000270 | Two transforms; includes initial script loading in decision time |
| Identity hashing / identity validation | 0.0347 / 0.0140 | Nested within measured work |
| Canonical JSON encoding | 0.00834 | Does not include typed evidence serialization |
| Serialization and writer close | 0.459 | 32 per-context relation writers, diagnostic grain |
| Writer close / directory fsync | 0.239 / 0.00206 | Included above; no original publication timing |

Application elapsed is 90.010 seconds, measured after preflight and before final
database/runtime close; scheduler elapsed is 102 seconds. Their difference is
not evidence of unexplained generation time. Timings are inclusive; nested
rows must not be summed. Completed-work time (context + families + serialization)
is 18.273 seconds: **0.875605 contexts/s**, **5.253629 decisions/s**,
**1.915386 hypotheses/s** for this instrumented slice only. Context construction
min/median/max is 0.748/0.951/3.157 seconds. Witness construction is
0.575/0.683/2.781 seconds. cProfile and wrappers add measurement overhead.

Function profiles localize certificate cost: `_select_registry` 627 calls /
10.441 cumulative seconds; `_select` 1426 calls / 10.405 seconds;
`encoded` 1907 calls / 6.362 seconds; recursive `value_chunks` 6284688 calls /
5.700 seconds; `ordered_values` 2042 calls / 2.544 seconds. These overlap.
Selector inserts alone take 4.082 seconds; total SQL execute count is 1881,
with 374 streaming cursor creations. Only three registry SQL reads occurred,
so caching decoded registry objects already works; their repeated recursive
ordering/encoding and selector submission remain on the hot path.

Selected component/source-reference lookup SQL took 0.032/0.121 seconds.
EXPLAIN operator summaries contain SEQ_SCAN and ORDER_BY, but retain neither
actual scanned-row counts nor execution profiles. This does **not** establish
a global full-scan bottleneck or prove index use at runtime. The diagnostic
also executes the shard join 16 times (3.031 seconds), where the original opens
one join/cursor per shard. Arrow-reader creation is 0.021 seconds; row conversion
is included in function timings rather than independently timed.

Context construction consumes 21.680 CPU seconds / 17.720 wall seconds; witness
construction 15.506 CPU / 13.845 wall. This shows active CPU work, serial Python
serialization and some native parallel work. It does not partition total time
into CPU, storage waits, locks or spilling. No lock-wait trace or original
spill time series exists. Native transforms and output fsync are negligible in
this slice; that does not exclude rare large-component/Q5 costs elsewhere.

### Diagnostic limits and public cursor experiment

The selected 16 distinct candidates have 45 parser components (2.8125/candidate).
The accepted 51779 exact candidates have 6106088 components
(117.925955/candidate). These aggregates establish weak coverage of component
volume; they neither identify protected examples nor characterize the tail.
There is no representative throughput estimate for the full population.

The diagnostic closes the streaming shard cursor after each selected context,
starts from recovered/checkpointed database state and fresh bounded caches, and
closes writers per context. Original generation holds the cursor across 4424
contexts, accumulating transactions/WAL until shard completion. The 45-second
caps did not censor this slice, but the slice cannot test those long-lived
conditions. These are material review-harness limits, not output differences.

A bounded public/invented local DuckDB 1.5.5 experiment checked that concern:
1000 committed cycles, each deleting and re-inserting the same three primary
keys with a 106496-byte invented payload, while an ordered 1100-row reader was
either held open or closed per cycle. Each fresh database used four DuckDB
threads, a 1GB memory limit, Arrow reader batch size one, and the same
`INSERT ... ON CONFLICT ... DO UPDATE ... RETURNING payload` selector SQL.
The payload was `b"public-synthetic-registry-" * 4096`; the key section was 4
with one-byte keys 0–2. Both modes ran sequentially in one Mac process.
No accepted inputs or code were used as
data. Five batches of 200 cycles took 0.437/0.433/0.443/0.427/0.422 seconds with
the reader held, versus 0.582/0.867/1.172/1.025/1.033 when closed. The held
reader left a 319778247-byte WAL and 12288-byte database; closing per cycle left
a 3837236-byte WAL and 616574976-byte database before final close.
Both retained the same three live selector rows and exact payloads.

This reproduces cursor-sensitive checkpoint/storage behavior, **not the timeout**:
the held reader did not slow down in this small experiment. Single local trials,
a different OS/filesystem and shared-process high-water RSS cannot justify a
Goethe speedup estimate, a memory comparison or attribution of the original
timeout to WAL growth. Synthetic artifacts remain in ignored local cache.

### Complete post-diagnostic performance defect ledger

| ID | Classification | Finding and disposition |
| --- | --- | --- |
| P01 | PERFORMANCE_SECONDARY | N+1 SQL/one-row Arrow access is confirmed: 1881 SQL calls, 374 cursor creations for 16 contexts. Indexed table creation exists; measured source/component lookups are small. Batch where equivalence is proven; no claim that full-table scans dominate. OPEN for repair review. |
| P02 | PERFORMANCE_SECONDARY | Parser schema rebuilt once per component: 45 calls / 0.070 seconds in the small slice. Six million upstream components make this avoidable repeat work relevant, but heavy contexts were not measured. Hoist immutable schema and preserve exact component stream/certificate. OPEN. |
| P03 | PERFORMANCE_ROOT_CAUSE (measured slice only) | Witness construction is 78.13% of context time. Registry SQL cache works but complete immutable registry payload is repeatedly ordered/encoded for every reference/witness/ancestor visit; selector writes repeat before database dedup. Exact code/profile evidence confirms this cost. Original 24-hour attribution remains incomplete. OPEN for narrow repair. |
| P04 | CHECKPOINTING | Actual shard 0 has 4424 contexts; 3364–3365 completed calls yielded no durable checkpoint. Sixteen prefixes were an uncalibrated operational choice. Smaller deterministic partitions can preserve logical rows/IDs; partition and crash/restart equivalence must be tested. No change made. |
| P05 | OBSERVABILITY | Original lacks within-shard counters/timing and SIGTERM receipt. Recovery bounds progress but cannot give exact hypothesis/durable decision counts or time series. Diagnostic records these only for itself. Add privacy-safe bounded progress and termination evidence in a reviewed repair; no raw exception text. OPEN. |
| P06 | INFORMATIONAL | ICU handles/regexes are reused and convergence remains bounded by six families. Q6 transform 0.000270 seconds; Q5 has zero eligible removals in slice. No evidence of ICU, Q3, family convergence or per-record fsync dominance here. Rare/heavy behavior remains untested. |
| P07 | RESOURCE | 24-hour walltime exhaustion is confirmed; memory was below the original request. Substantial original CPU use and generation-phase envelope are measured, but no representative full-runtime prediction or CPU/I/O/lock partition is possible. No walltime/memory increase proposed as a repair. |
| P08 | CHECKPOINTING | Long-lived streaming read plus per-certificate commits can defer storage checkpointing. Synthetic experiment reproduces WAL behavior without slowdown. Recovered committed diagnostics rule out one wholly uncommitted generation transaction. WAL alone is not root-cause proof. OPEN for lifecycle review. |
| P09 | REVIEW_HARNESS | Sixteen minimum-ID contexts, low component volume, short cursor lifetime and recovered state do not reproduce the original 22h49m generation regime. Measured speed is about 21 times the original interval average; no linear extrapolation, tail claim or full timeout explanation. Explicitly unresolved. |
| P10 | OBSERVABILITY | Inclusive profile timings, non-ANALYZE plans, missing row-conversion/spill/lock timings and differing RSS sources limit attribution. Preserve both RSS observations and all method distinctions. Resolved in reporting; future measurement coverage requires review. |
| P11 | PERFORMANCE_SECONDARY | Original publication validation calls full replay multiple times; static review finds the same costly context certificates regenerated during validation. This was not reached in job 1772639 and cannot cause its first-shard timeout. Preserve validation/reopen semantics and include replay cost in any later runtime estimate. OPEN, no validation weakened. |
| P12 | INFORMATIONAL | All 16 contexts/96 decisions completed with exact identity checks; hashes/runtime gates passed, original files preserved, no candidate published. No scientific/family/budget/accepted-stage change. This diagnostic is structural/performance evidence only. CLOSED for this review. |

H01–H09 above remain the pre-submission harness fixes. P09–P10 record additional
limitations learned after execution, rather than retroactively claiming the
experiment reproduced every original condition. The single diagnostic
authorization is exhausted; no second protected experiment is submitted.

### Smallest proposed repair and required proof

First remove repeated immutable registry serialization from
`ReferenceAccess._select_registry` / `_select`: validate and retain exact ordered
payload bytes per registry identity under the existing byte budget, and avoid
re-inserting an already verified identical registry in the current certificate.
Preserve FK/collision checks, section/key ordering, complete selector membership
and exact certificate bytes. Do not cache row-local eligibility by candidate.
If R is registry visits and B the encoded payload size, current serialization
cost is O(R×B); a byte-bounded immutable payload cache reduces it to
O(M×B + R) metadata lookup work, where M is cache misses. It is not an unlimited
global map. Registry selector inserts can become one per distinct verified
registry per certificate, while all reference evidence still contributes.

Then hoist the immutable parser schema and review set-based selector staging
and smaller deterministic checkpoints. Those are separate bounded repair
items, not permission to combine transformations, drop repeated evidence, skip
validation or alter scientific context grain. No speedup factor is promised:
10.441 seconds is overlapping profile attribution, not wholly removable work.

Required tests before any repaired executable/full retry: byte-exact selector
certificates and complete Q1–Q6 relation equality; repeated/shared registry and
ancestor cases; FK/collision rejection; bounded-cache eviction; extreme synthetic
component counts; all prior Stage 10 science and Stage 8/9 regression tests;
safe suite/static/privacy checks; partition/order/restart equivalence; fault
injection across checkpoints and publication. Add operation-count regressions
for repeated encoding/inserts, rather than machine-dependent speed thresholds.

Because this diagnostic does not explain the original runtime gap, a separately
owner-authorized bounded comparison should cover long-lived cursor behavior and
large-component workloads before a full retry. Selection must remain immutable
and mechanical, with no address-content tuning. No extra experiment or repair
is executed in this reporting continuation. **NEXT: OWNER REVIEW OF THE
PERFORMANCE LEDGER AND PROPOSED REPAIR.** Stage 10 NOT ACCEPTED; operating budget
UNSELECTED; Stage 0–9 unchanged; HOLDOUT sealed; production/Pelias untouched;
Stage 11 NOT STARTED.

Reporting validation passes: exact aggregate-report SHA, job/executable/count
reconciliation, public-function/profile field checks, absence of protected
value/ID/SQL-parameter fields, all changed-document links and anchors, original
Stage 10 implementation/design/runtime/schema inventory, accepted stage-report
validation and `git diff --check`. No executable changed, so the previously
recorded 232 focused / 1006 safe-suite results are retained without claiming a
new full-suite run. Only sanitized documentation and the aggregate evidence
record are added in this continuation; the diagnostic branch remains separate
from main pending owner review.
