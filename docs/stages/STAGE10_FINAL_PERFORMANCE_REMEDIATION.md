# Stage 10 final performance remediation

## Authority and preserved evidence

The owner authorized one consolidated operational correction after
[confirmation 1774111](STAGE10_REPAIR_CONFIRMATION_1774111.md), followed by exactly
one final confirmation of its original 4424-context first shard. Full DEVELOPMENT
is **not authorized** by this action. Stage 0–9, Stage 10 science, Q1–Q6/reasons,
Q7 deferral, identities, convergence and ceilings remain frozen. Operating budget
is UNSELECTED. HOLDOUT sealed; production/Pelias untouched; Stage 11 NOT STARTED.

Baseline branch commit is `39c0470adb6c99b7f08f70775fa2e21906e913ec`.
Job 1774111 completed both scientific partitions: 4424 contexts, 26544 decisions,
9065 hypotheses, with 70 and 139 checkpoints and identical logical relations.
Its 16/96/35 old/new gate passed. No monotonic lifetime throughput collapse was
observed; sampled WAL cleared at checkpoints. The historical 1772639 causal
mechanism remains unresolved/informational; no additional investigation pursues it.

## Execution plan and progress

1. Replace fine-grained reference SQL and repeated canonical material encoding.
2. Seal fully validated checkpoint outputs and adopt their bytes/diagnostics.
3. Persist phase evidence atomically; preserve sanitized SIGTERM evidence.
4. Prove exact synthetic equivalence, count bounds, partition independence,
   interruption and adoption behavior; run the complete safe validation gates.
5. Complete one bounded code review and record every material finding together.
6. Commit/push the exact executable, prepare a clean detached Goethe checkout,
   then submit one four-hour confirmation. Pending/running: report once and stop.

Implementation is in progress; no new confirmation has been submitted at this
record's initial creation. Validation and submission evidence will be appended.
The owner-provided plan is binding; there is no renewed scientific design phase.

## SQL decomposition and complexity

The prior first pass measured **2,329,428 `execute` calls** and 2848.611 seconds
inside SQL execution. The historical instrumentation did not record statement
categories; exact historical category counts cannot be recovered from that total.
Static decomposition of the exact former path is:

| Caller / statement | Previous multiplicity |
|---|---|
| `ReferenceAccess._material` → `one(SELECT … WHERE id=?)` | One registry/capability/object query per LRU miss; eviction repeats queries for immutable IDs |
| `_select_object` → `object`, `_select_record`, `_select_registry`, parent traversal | Repeats the previous row for every witness/pointer and ancestor; shared global LRU is only 256 entries |
| `members` → ordered match-set SELECT | Per match-set cache miss; sets too large for the byte cache are scanned again for member selection and witness traversal |
| Context source-reference SELECT | One per generated context |
| Parser-certificate SELECT | At most one per context; complete candidate cache can reduce this |
| Q5 forward/reverse component streams | At most two per context, independent of component count |
| Spilled selector ordered DISTINCT SELECT | At most one per uncached context certificate |
| Context pages, diagnostics, checkpoints | Bounded per page/checkpoint, not per witness |

For the historical C=4424/K=70 pass, the conservative non-reference bound
below is 40,097 executions (it even includes a diagnostic-export operation absent
from that old implementation). Thus **at least 2,289,331 of 2,329,428 executions**
belong to registry/capability/object/member resolution, inferred from the closed
code paths rather than a missing historical per-statement trace. The exact split
among those four categories remains unmeasured; no invented split is reported.

The new private reference store executes **one recursive set-based closure and
four sorted streams** per preparation. It writes canonical payload bytes once for
each exact registry, capability, needed object (including parents), and match
member. A read-only fixed-width disk index, binary search and bounded payload
reads replace SQL lookup. Only needed objects are copied. No all-reference Python
map, candidate-by-reference join, new source map or authoritative relation is added.
The index is memory-mapped; payloads are read one at a time. Existing byte-bounded
LRUs remain accelerators; eviction never causes SQL or canonical re-encoding.
Material identity includes relation kind and complete upstream immutable ID;
match members include match-set ID and ordinal. Certificate cache keys retain all
previous frozen witness/capability/question fields. No country/context is merged.

All SQL executions receive fixed statement-category counters/timers. SQL text,
parameters and values are never recorded. The generation-only bound is derived:

- C generated contexts; K checkpoint units; C ≤ 64K.
- Source evidence ≤ C, parser certificate ≤ C, component streams ≤ 2C,
  spilled certificate sort ≤ C; **registry/capability/object/member SQL = 0**.
- Context pages P ≤ C+K (includes terminal pages), diagnostic flushes F ≤ C
  (two statements each), database checkpoints D ≤ C+K.
- Key windows K+1; diagnostic snapshot export K.
- Total ≤ **9C + 4K + 1 ≤ 580K + 1**. Normal batches are cheaper than this
  conservative one-context-per-byte-page upper bound. The bound is independent
  of parser/reference component count. Setup and final integrity validation are
  separately timed/counted, never hidden in this generation bound.
- Full adoption: exactly **3K+1** database statements (K+1 key windows,
  K diagnostic restores and K database checkpoints). No scientific generation,
  component lookups or certificate SQL. Hash validation scales with file bytes.

The confirmation enforces zero reference point SQL and the generation bound.
Tests exercise increasing witness multiplicity, forced cache eviction, spilled
selectors and exact equality against the original SQL implementation.

## Checkpoint adoption contract

Operational checkpoint format v3 binds the exact executable, contract, profile,
schema, transformation spec, runtime lock, Stage 8/9 manifests, complete input
binding, science and budget fingerprints. It retains the exact sorted context
IDs and prefix. On creation, complete relation/value/identity/map-back/lineage/
cardinality checks run before an atomic `_VALIDATED.json` seal binds the manifest.

Each unit also stores a **private work-state diagnostics snapshot**, validated
against the unit's exact occurrence keys and source/candidate/role identities.
This is not a third scientific output relation or authoritative occurrence map.
Only the two frozen scientific relations are published in a later candidate.

Adoption verifies canonical metadata and binding, the expected immutable key
window, seal, file inventories/permissions/topology, SHA-256, Parquet schema and
footer counts. Unchanged physical bytes preserve the logical fingerprints proven
before sealing. It then copies the unit and restores diagnostics in one bounded
SQL operation, without constructing contexts/certificates/decisions/hypotheses.
A sealed complete prefix can likewise adopt coalesced files by inventory/hash;
it does not deserialize scientific rows. An unsealed/absent unit is generated
only in the new attempt. The historical attempt is never edited or discarded.
A present but invalid seal/hash fails closed. V2 checkpoints are not silently
adopted under V3/executable bindings; their historical outputs remain references.

Partition size changes no scientific field, ordering, ID or fingerprint. Prior
70-vs-139 equality is preserved; local 1/2/64-unit synthetic equivalence remains.
Interruption before the seal leaves no adoptable completed checkpoint, even if
its relation files and checkpoint manifest have already been written.

## Durable evidence

Private single-writer operational receipts use an exclusively created temporary
file, fsync, atomic rename and directory fsync. These receipts are distinct from
candidate reservation/registration/_COMMITTED publication. Every recorded value
is a fixed label, count, timing or sanitized binding; snapshots are independent.
Setup, generation, checkpoint/write, adoption, final validation and terminal
states are persisted during execution. SIGTERM attempts a short terminal receipt
with current counters, then the scheduled entrypoints exit with code 143 via
`os._exit`, avoiding Python unwinding, selector flushing and temporary-directory
cleanup. No database cleanup or scientific commit is attempted in that handler. Forced SIGKILL or filesystem
failure can prevent a final receipt; its absence can never indicate success.

## Final confirmation

The dedicated `stage10_final_confirmation` launcher retains fail-closed Goethe
SLURM, exact detached pushed SHA, same controlled PanFS topology, pinned input
manifests, verified COPY of the original database/WAL, offline network guard and
exact locked ICU/runtime gates. It cannot publish a candidate. The historical
harness remains frozen to its older approved executable and rejects the new core.

- A: compare the exact preserved 16 contexts/96 decisions/35 hypotheses row for
  row, including protected payloads, inside the allocation only. Failure stops.
- B: replay the same prefix-zero 4424 occurrence keys, using 64-context units
  (69 full units plus 8 contexts = 70). Compare both complete logical relations
  and every protected output row to preserved 1774111 first-pass output.
- C: reopen/adopt all 70 completed units. Certificate calls, family generation
  and regenerated contexts must all equal zero; restore exact diagnostics.
- D: use a separate confirmation-only state with 69 completed units and one
  incomplete tail. Adopt 69, regenerate exactly 8 contexts, compare complete
  final logical relations. Phase-B output and historical evidence stay immutable.

One-time parser/reference and index setup are measured separately. Generation
reports early/middle/late context/decision/hypothesis rates, SQL categories,
certificate calls/time, invariant encodes, selector work, Q5/Q6, writes, fsync,
checkpoint count and sampled WAL. Each pass has a durable pre-validation receipt
and a validated receipt. Completion/failure metadata is persisted independently.
Resource request: 4 CPUs, 32 GiB, at most 4 hours, no dependency/requeue. No
speedup/production-readiness claim is made before measured completion. Full
DEVELOPMENT projection must include 69,747 contexts, one-time setup, sustained
rates, checkpoint overhead and all retained publication/reopen scientific replays.

## Complete P01–P12 remediation ledger

Dispositions below describe implementation intent; cluster evidence is pending.
No entry asserts that this new confirmation has already passed.

| Item | Disposition | Change / evidence boundary |
|---|---|---|
| P01 SQL fine-grained execution | FIXED | Set-based preparation, indexed canonical bytes; closed category counters and derived generation/adoption bounds |
| P02 parser/reference preparation | FIXED | Prepared once, reused across checkpoints and resume; durable separate setup receipt; parser algorithm unchanged |
| P03 certificate dominance | MITIGATED | Immutable payloads encoded once, no lookup SQL, exact selector bytes/cache keys; remaining traversal/sort cost measured on full shard |
| P04 checkpoint/resume | FIXED | Validated seals and physical adoption, private diagnostic restoration, zero regeneration for completed units; unsealed tail rebuilt alone |
| P05 durable observability | FIXED | Atomic phase/checkpoint/pass receipts; short SIGTERM receipt attempt; no false committed state |
| P06 Q5/Q6 | INFORMATIONAL | Prior timings negligible; frozen scientific implementation and runtime unchanged; call/time instrumentation retained |
| P07 resources | MITIGATED | One generation plus cheap adoption/tail in 4h; no repeated full repartition or blind resource increase; full-run request awaits measurement |
| P08 transaction/WAL | MITIGATED | Existing bounded pages/transactions and WAL-zero checkpoint guard retained; adoption restores one unit per commit/checkpoint |
| P09 population/equivalence | VALIDATED | Synthetic old/new equality and prior 70/139 equality retained; final allocation must additionally pass original 16 gate and full 1774111 golden |
| P10 snapshots/termination | FIXED | Independent snapshot maps, monotonic timers, durable setup and terminal evidence; syscall/failure tests |
| P11 publication/reopen cost | DEFERRED_WITH_JUSTIFICATION | No candidate publication authorized; accepted validation is not weakened. Full-run projection must price unchanged scientific replays |
| P12 boundaries/history | INFORMATIONAL | Original failure cause unresolved; historical artifacts/executables preserved, science unchanged, no full DEVELOPMENT or acceptance |

New defects T01 certificate/SQL, T02 resume certificate reconstruction, T03
repeated confirmation traversals, T04 setup/terminal durability and T05 incomplete
resume coverage map respectively to P01/P03, P04, P07, P05/P10 and P04/P09.

## Bounded implementation review ledger

| Finding | Disposition | Verification |
|---|---|---|
| R01 registry/member/object SQL and repeated invariant encoding | FIXED | Preparation executes five statements; context certificates reuse canonical bytes; forced eviction and 2/2000-member tests compare exact legacy output with ≤1 spill-sort SQL |
| R02 completed checkpoints rebuild context/certificates | FIXED | Full adoption test makes context/certificate/family generation and scientific row deserialization fail if called; exact output and diagnostics still match |
| R03 incomplete copied unit could expose a copied seal | FIXED | Copy excludes seal; physical validation and fsync precede a fresh atomic seal; interruption test failed before correction and passes afterward |
| R04 private diagnostic snapshot lost on adoption | FIXED | Exact context/source/candidate/role linkage checked during initial full validation; sealed bytes restore the same diagnostics with one bounded INSERT |
| R05 setup/terminal evidence lived only in final result | FIXED | Phase receipts and independent pass receipts are atomic and immediate; SIGTERM snapshot and interrupted-rename tests preserve prior evidence |
| R06 historical harness pin rejects the new operational core | VALIDATED | Old entrypoint remains fail-closed; dedicated final launcher separately pins unchanged scientific files and exact current executable/inventory |
| R07 new telemetry category includes the token SELECT | INFORMATIONAL | Privacy assertion checks actual SQL text (`SELECT * FROM`) and invented protected sentinels; fixed public category names contain no query/parameters |
| R09 SIGTERM could unwind into spilled-selector flush/cleanup | FIXED | Scheduled entrypoints persist terminal progress then exit without unwinding; subprocess signal test proves no cleanup and durable counters |
| R08 reporting failure after publication could demote success | FIXED | Post-publication events stay inside the existing best-effort reporting block; immutable publication validation is unchanged |

Review covers scientific equality, source/country/boundary isolation, complete
cache identities, closure/ancestor handling, normalization/ICU preservation,
bounded memory/SQL/transactions, interruption and seal order, map-back, privacy,
actual confirmation setup, phase scopes and full-run authorization boundary.
No scientific decision is reopened. No full DEVELOPMENT candidate is generated.

A fresh-context review provided a partial check of reference framing/keys,
adoption and termination, then stopped at a tool usage limit. The author
completed the bounded self-review; no claim of a completed independent review
is made. Stage 10 candidate independent review remains a later boundary.

## Local validation before confirmation

- **276 focused Stage 10 tests PASS**, including the exact locked public/synthetic
  ICU runtime, scientific family tests, old/new certificates, per-component SQL
  counts, 1/2/64 partition equality, full adoption, partial tail, interruption,
  actual final harness sequence, immutable snapshots and subprocess SIGTERM.
- **1050 safe repository tests PASS**, including Stage 8/9 regressions. Protected
  production-transfer tests remain excluded by the established safe marker;
  runtime-dependent ICU tests run separately in the exact local locked runtime.
- Mypy passes across 136 source/test files; Ruff lint and format pass. Frozen
  design/spec/schema/runtime dependencies remain unchanged; inventory, report,
  Markdown link/anchor, CLI help, shell syntax, privacy/tracked-data and diff
  checks are recorded in the portable validation receipt.
- Self-review R01–R09 has no unresolved implementation defect. Remaining P03/P07/
  P08 measurements require the single authorized confirmation; P11 full candidate
  publication remains outside this authorization. No speedup claim is inferred
  from synthetic tests. No protected inputs were used locally.
