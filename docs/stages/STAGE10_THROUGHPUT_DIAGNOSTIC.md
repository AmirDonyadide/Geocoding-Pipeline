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
