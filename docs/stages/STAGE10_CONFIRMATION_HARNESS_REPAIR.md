# Stage 10 confirmation harness repair — 2026-09-20

## Authorization and preserved evidence

The owner classified job **1774012** as a confirmation harness/observability
failure and authorized **one harness-only repair and one replacement confirmation**.
The repaired computation remains
`808123bb145107d7b025471b3b02869cc95fb44a`. No query-generation, evidence,
identity, family, convergence, engineering ceiling or operating-budget change.
The operating budget remains UNSELECTED. No full DEVELOPMENT retry, candidate
publication, Stage 11, HOLDOUT, production or Pelias is authorized.

The [1774012 reconciliation](STAGE10_REPAIR_CONFIRMATION_1774012.md) and all
original receipts remain unchanged. Its 16-context gate passed exactly:
96 decisions / 35 hypotheses. Certificate time was 0.610358 seconds versus
13.844582 seconds in diagnostic 1773901; instrumentation/workspace scopes differ.
Parser preparation was 554.549410 seconds, context preparation 6.952050 seconds,
and the gate 4.337835 seconds. Scheduler MaxRSS 3.423 GiB and application peak
5.095 GiB are different measurements. Gate sampled WAL maximum 535 bytes and
absence after close do not establish long-replay WAL behavior. The 4424-context
replay never started; the original 24-hour degradation remains unresolved.

## H01: final table names before index creation

The confirmation operates only on a new, hash-verified private copy of the
original failed database/WAL. The complete original key relation is copied to
its final `stage10_all_context_keys` name and validated with symmetric
`EXCEPT ALL` before its unique index is created. The copied `stage10_context_keys`
table is then dropped normally, including its own index. It is recreated under
its final name using the unchanged prefix-zero predicate, validated for exact
rows and 4424 cardinality, then indexed. These steps share one explicit
transaction; any mismatch rolls back. There is no indexed rename, CASCADE,
exception suppression or modification of a historical attempt.

The complete selected occurrence tuples receive a sanitized fingerprint using
`stage10-confirmation-population:v1`. Selection still means the **exact original
first hexadecimal query-context-ID prefix `0`**, not source-text selection.
The original database/WAL hashes and accepted input pins are unchanged. The
private derivative context join is rebuilt and checkpointed before starting
the replay clock. It does not replace an upstream authoritative relation.

## H02: actual setup and replay path tests

Tests execute `prepare_replay_population`, the function used by the real job,
under **DuckDB 1.5.5**, starting with the real synthetic upstream/context schema
and its unique index. They cover table population, an excluded invented ID,
rollback on cardinality mismatch, final names/indexes, no rename, two fresh
executions, stable selection fingerprint, close and read-only reopen.

The historical synthetic equality test now calls the real
`replay_confirmations` setup-to-replay function. It verifies complete row
equality against the original executable, first/repartition logical equality,
completed-unit reuse, and regeneration of one deliberately incomplete unit.
Observer wrappers are tested for scientific transparency and restoration on
exceptions. A missing/changed protected gate row fails before the long replay.
The real protected gate remains **exactly 16 / 96 / 35**, and runs before any
first-shard output. No golden full-shard result exists from the timed-out job;
full-shard equivalence means partition/resume equality, supplemented by the
preserved old/new gate and unchanged repaired computation pins.

## H03: immutable phase snapshots and measurement scopes

`Progress.snapshot()` copies each nested timing entry, counters and observations.
Later updates cannot mutate earlier snapshots. Tests change counters and the
same timing entry after capture, compare serialized receipts, and make use of
the civil wall clock fail: elapsed timing uses monotonic clocks.

The only shared operational change is the `Progress` observability class.
Preflight verifies all other Stage 10 stage modules against the repaired
executable inventory. For `s10_query_operations.py`, it compares the entire AST
outside `Progress`, rejecting any computation change. Frozen design, schema,
profile, runtime lock and clean exact detached checkout gates remain intact.

The harness installs temporary delegating wrappers only within the confirmation
allocation. They preserve arguments/results and restore functions on exit.
No wrapper logs SQL, parameters, identities, source values or query strings.
Inclusive timers overlap and must not be summed as exclusive durations.

| Measurement | Scope |
| --- | --- |
| Snapshot copy/hash and recovery | One-time private preparation, before generation |
| Parser-certificate preparation | One full preparation; count must be one |
| Context/index preparation | Initial preparation and separately labeled confirmation selection rebuild |
| Historical equivalence gate | 16-context comparison, independent immutable receipt |
| First/repartition/resume replay | Separate monotonic durations, excluding setup and later final validation |
| Output close/checkpoint, coalescing, serialization/fsync | Inclusive suboperations within the appropriate replay |
| Final validation | Separate per-pass duration and post-validation snapshot |
| Resume-fixture preparation | Separate copy/validation cost, excluded from resume throughput |

The 554-second parser preparation is **not optimized in this repair**. Every
replay must report zero parser-preparation calls and no context-index rebuild;
an unexpected repeat fails the harness. Reference witness certificates remain
lazy per-context work with the already approved bounded caches. Cold reference
caches are used per pass, as before. Count actual registry encodes (one per
registry record on a cache miss), selector add attempts, distinct insertions
within each bounded buffer, and SQL selector insertions separately. Buffer
insertions may recur across certificate builds/spills; they are not a global
distinct-count claim. SQL selector insertions should remain zero.

Q5/alignment, Q6/ICU, certificate calls/builds, SQL execute/fetch/cursor,
identity hashing, certificate serialization, relation serialization, writes,
checkpoint validation and coalescing have fixed aggregate timer names. No
per-string profiling or scientific policy change is introduced.

## Exact replay, checkpoint and WAL protocol

The first pass processes **4424 contexts**, **26544 decisions**, with hypotheses
determined by unchanged science. Units contain at most **64 contexts**:
**70 units = 69 × 64 + 8**. The second pass uses **32 contexts**:
**139 units = 138 × 32 + 8**. Both must have identical relation logical hashes,
counts, schema fingerprints and exact context map-back. Protected row values
stay inside Goethe compute execution.

For resume, a new private fixture copies the first 69 completed units and
creates one explicitly incomplete final unit without a completion marker.
The original first-pass tree is unchanged. Resume into another new directory
must reuse 69 validated units, regenerate the final 8 contexts, preserve the
incomplete fixture byte-for-byte and reproduce the same complete relations.
An incomplete unit is never adopted. This exercises actual resume behavior,
not only completed-checkpoint copying.

Checkpoint receipts include cumulative contexts, decisions, hypotheses, unit
counts, inclusive timings, database size and sampled WAL high-water values.
WAL is sampled before/after database checkpoints and must be zero after each
successful checkpoint under the existing core assertion. These are **sampled
high-water marks**, not a continuous maximum. Explicit setup transaction
duration/count and checkpoint counts are separate from replay's bounded
autocommit diagnostic-write batches. No open read cursor is introduced by the
harness. WAL/throughput correlation alone is not causal evidence.

EARLY/MIDDLE/LATE are successive thirds of completed checkpoint observations,
with exact counts and elapsed intervals reported for each; first-pass groups
contain 23/23/24 units. Each reports contexts/s, decisions/s and hypotheses/s.
They exclude one-time setup and final coalescing/validation; the separately
reported whole replay includes coalescing. Resume throughput includes validated
adoption and reconciliation and must not be presented as fresh generation.
Duplicate exception receipts cannot inflate completed-unit observations.
No arbitrary speedup threshold grants success: owner continuation must assess
degradation, bounded memory/WAL, exact equality and operational reasonableness.

## Complete bounded harness review ledger

| ID | Disposition | Resolution / retained limitation |
| --- | --- | --- |
| H01 / C01 | FIXED | Indexed rename removed; final-name tables validated before index creation; exact-version setup/rollback test. |
| H02 / C02 | FIXED | Actual setup-to-replay path tested; selected/excluded IDs, indexes, repeat execution, close/reopen and interruption fixture covered. |
| H03 / C03 | FIXED | Independent nested snapshots, monotonic timing and immutable on-disk receipt tests. |
| H04 | FIXED | Setup, replay, coalescing/checkpoints and final validation reported separately; costly parser preparation unchanged and repeat detection explicit. |
| H05 | FIXED | Repaired computation pinned independently of the harness SHA; transparent temporary observers tested with exact scientific equality and exception restoration. |
| H06 | FIXED | Per-checkpoint sampled WAL/database counters, real incomplete-unit resume and early/middle/late rates retained; no protected values logged. |
| H07 | INFORMATIONAL | Original 24-hour degradation and full-shard throughput/WAL/resume remain unproven until the replacement completes. No full-run projection now. |

The full P01–P12 ledger remains in the [failure reconciliation](STAGE10_REPAIR_CONFIRMATION_1774012.md#complete-p01p12-ledger-after-confirmation).
No performance item is dropped or promoted to cluster-validated status by local
harness tests. P05/P10 observability defects are repaired here; P04/P08/P09
sustained checkpoint/WAL/population evidence still requires this confirmation.
P02's measured preparation cost remains visible, P03's slice certificate gain
retains its scope, and P11 publication/reopen costs are outside this harness.

## Validation and execution boundary

Local validation passed: **12 confirmation harness tests** under DuckDB 1.5.5 /
Python 3.14.3; **262 focused Stage 10 tests** including the exact public Mac ICU
runtime; **1036 safe repository tests** including Stage 8/9 regressions; mypy
128 files; Ruff lint/format; shell syntax; CLI help; design/schema/profile/runtime
lock/hash inventory and stage-report validation; document links/anchors;
tracked-data/privacy and diff checks. The [sanitized validation receipt](../scientific_assets/stage10_confirmation_harness_validation_v1.json)
records the scopes. The safe suite excludes production transfer payload tests
and the two real-ICU modules already covered by the focused suite.

The first full focused invocation used the separate Python 3.14.3 test
environment with the Mac runtime locked to `.venv`; it correctly failed that
local runtime identity setup (15 fixture errors, 247 other tests passed).
The complete 262-test rerun used the matching locked Mac environment and passed.
No runtime/specification was changed, and this is not a Goethe runtime mismatch.
Earlier test-only typing/fixture assertions were corrected before final checks.
No wall-clock performance assertion is used in unit tests.

The complete bounded review H01–H07 above is resolved for submission, with H07
explicitly awaiting cluster evidence. Exact replacement submission identity is
recorded separately after submission. The launcher retains 4 CPUs, 32 GiB, four hours,
`--no-requeue`, no dependencies, private permissions, exact pushed detached SHA,
Goethe/SLURM guards and offline execution. It binds the reviewed failure ancestry.
Only a fresh private confirmation destination is permitted. It has no candidate
registration or publication path.

On submission, observe PENDING/RUNNING once, record the job and stop. No polling
loop, cancellation, automatic replacement or full DEVELOPMENT execution.
On owner continuation, reconcile all expected contexts/checkpoints and the
complete P01–P12 ledger before making a performance claim. Stage 0–9 unchanged;
HOLDOUT sealed; production/Pelias untouched; Stage 11 NOT STARTED; Stage 10
NOT ACCEPTED.
