# Stage 10 repair confirmation 1774012 — failure reconciliation

## Terminal result and scope

**STAGE10_THROUGHPUT_REPAIR_CONFIRMATION_FAILED**. Job `1774012` at executable
`808123bb145107d7b025471b3b02869cc95fb44a` ended **FAILED / 1:0** after
**631 seconds (00:10:31)**. This is an **IMPLEMENTATION / REVIEW_HARNESS** failure,
not walltime exhaustion, an observed memory failure or a scientific mismatch.
The original four-hour limit was not reached. The single authorized confirmation
has been consumed; no replacement or full DEVELOPMENT retry was submitted.

One terminal `sacct` query was made on owner continuation. Requested resources
were 4 CPUs and 32 GiB; accounting reports 80 allocated CPUs on `node19-021`,
consistent with the allocation topology, not measured use of 80 cores. TotalCPU
was 619.185 seconds. Batch MaxRSS was **3589792 KiB (3.423 GiB)**; application
`RUSAGE_SELF` reported **5342460 KiB (5.095 GiB)**. These are distinct measurement
sources; neither is substituted for the other. Scheduler start/end were
`2026-09-20T14:32:41` / `2026-09-20T14:43:12` in site-local accounting output.

The protected attempt remains at:

`/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage10/confirmations/stage10_repair_20260920T104009Z_808123bb1451`

Only explicitly sanitized aggregate receipts were copied locally. No protected
selection, row, query, Parquet, database or WAL payload was copied, printed or
inspected locally. Login-node work was accounting/file metadata/receipt transfer;
all protected computation was inside the existing scheduled job. The failed
attempt, original `1772639` evidence and accepted inputs remain unchanged.

## Exact failure and bounded synthetic reproduction

The failure receipt identifies `duckdb.DependencyException` at
`stage10_repair_confirmation.py:399`, through `s10_query_operations.py:131`:

```sql
ALTER TABLE stage10_context_keys RENAME TO stage10_all_context_keys;
```

The recovered original table has the `context_key` unique index. A public-only
local reproduction under the same **DuckDB 1.5.5 / Python 3.14.3** reproduced
the dependency exception with an empty invented table and that index. Dropping
the index in this disposable synthetic database allowed the rename. No index
was dropped on Goethe or in any preserved work database.

This index dependency is sufficient to explain the observed exception. The
failure occurs after the historical equivalence receipt is written and before
the first-shard loop, output writers or checkpoint units are created. It does
not explain the original 24-hour generation slowdown.

The synthetic confirmation test exercised comparison, partition generation and
resume helpers directly. It did **not** execute this intervening table-rename
setup with the original indexed table. That is the specific test-coverage gap;
the earlier passing test counts do not certify this omitted path.

For owner review, a minimal future harness correction could explicitly handle
this index dependency on the private copy, restoring the required selected-key
index, or avoid renaming the indexed table through an explicitly scoped
validation view. Either option must test the exact indexed setup and selection
before any new execution. Neither correction has been implemented here.

## Scientific equivalence and progress reached

- Exact locked runtime gate and public ICU vectors passed before protected
  database copying. Runtime lock SHA remains
  `20bfe735dca8b35b0ea10f1e3d729f2007e4cf3333dd5d5b5cdd527ef638d2cd`.
- Original attempt, copied database/WAL, Stage 6/8/9 manifest and diagnostic
  report/selection pins passed before the equivalence gate.
- Prepared indexes contained **69,747 contexts**, **6,106,088 parser components**
  and **933,012 source-reference rows**. Context-index cardinality was 69,747.
- The exact historical **16-context** gate passed: **96 decisions / 35
  hypotheses**, with every complete row equal to its preserved counterpart.
  Comparison includes context/hypothesis/decision IDs, protected representations,
  Q1–Q6 statuses/reasons, convergence, lineage, Stage 9 gates and Q5/Q6 results.
- The scheduled **4,424-context first-shard pass did not start**: zero contexts
  processed in that pass, zero checkpoint units and no first/repartition/resume
  output directories. One gate context belongs to prefix 0; gate overlap is not
  counted as progress in the unstarted full-shard pass.
- Gate counters `contexts_completed`, `hypotheses_written` and
  `family_decisions_written` are zero because those counters belong to the
  checkpoint writer. The gate's explicit 16/96/35 counts are authoritative for
  the in-memory comparison; no new protected hypothesis relations were emitted.
- No full-shard equivalence, checkpoint resume, early/middle/late throughput,
  ceiling reconciliation or long-lived WAL result is available. Their absence
  is not a failed scientific comparison or proof of context loss.

## Measured phase and cost evidence

Use the separately written **immutable `equivalence_gate.json`** for gate
timings. All timings below are wall-clock seconds and inclusive where nested.
Do not add nested rows or treat the two jobs as a controlled speedup experiment.

| Phase / operation | Measured seconds | Scope |
| --- | ---: | --- |
| Snapshot copy and hash | 29.480064 | Verified private copy, original untouched |
| Snapshot recovery | 24.753780 | Copy only |
| Parser-certificate preparation | 554.549410 | Complete 6,106,088-component stream |
| Context-index preparation | 6.952050 | Complete 69,747-context join/index |
| Combined index preparation/checkpoint phase | 561.505488 | Includes the preceding preparation operations |
| Historical equivalence gate | 4.337835 | 16 contexts, all row comparisons, diagnostic writes/checkpoints |
| Gate context construction | 1.031588 | 16 calls |
| Gate witness certificate total | 0.610358 | 16 calls; cache-miss build time 0.598006 |
| Gate SQL execute | 2.449586 | 434 calls in immutable gate receipt |
| Gate diagnostic writes | 0.744821 | 16 calls |
| Gate database checkpoints | 1.058659 | 16 calls |
| Gate Q5 alignment | 0.000173 | 16 calls; historical slice has zero eligible Q5 removals |
| Gate Q6 family | 0.089559 | 16 decisions |
| Gate actual ICU calls | 0.000210 | 2 calls |
| Application total | 622.100895 | Scheduler elapsed is separately 631 seconds |

The same 16-context population previously measured 13.844582 seconds of witness
certificate work and 17.719525 seconds of context construction in job `1773901`.
The repaired observations are lower, with exact scientific row equality. The
older job used cProfile and different instrumentation/workspace preparation;
these observations do not isolate a hardware-normalized speedup or establish
long-shard behavior. Gate throughput, including its comparison and per-context
write/checkpoint overhead, was about **3.689 contexts/second**. It must not be
extrapolated to the full DEVELOPMENT run.

The complete parser pass measured about **11,011 components/second** and used
554.233 seconds of process CPU versus 554.549 seconds wall. This identifies a
substantial one-time preparation cost in this job; it is not evidence of the
original generation-phase degradation. Prepared database size was 2,539,663,360
bytes; closed database size is 2,566,402,048 bytes. Gate sampled WAL high-water
was 535 bytes and the WAL was absent after close. These observations cover only
preparation/the short gate, not the planned 70-unit lifetime.

Process I/O counters are preserved in the aggregate result. They distinguish
logical `rchar/wchar` from physical `read_bytes/write_bytes` and are not proof of
an I/O bottleneck. A defensible full-run projection, walltime increase or new
resource recommendation is **not available** from this failed confirmation.

## Complete P01–P12 ledger after confirmation

These dispositions preserve the consolidated repair's static findings and state
exactly what the failed confirmation did or did not establish.

| ID | Disposition | Post-confirmation evidence / limitation |
| --- | --- | --- |
| P01 | MITIGATED | Gate SQL execute calls 1881 previously versus 434 now, with differing instrumentation. Indexed/cached access is present; 385 cursors remain. Full-shard access cost unmeasured. |
| P02 | FIXED; measured preparation cost | Complete parser-certificate index built once in 554.549 s; schema/identity synthetic checks and protected 16-context equality pass. No claim the one-time cost is free or full-production scaling is established. |
| P03 | FIXED for confirmed slice bottleneck | Same-population witness time 13.844582 → 0.610358 s with exact rows. Original 24-hour attribution and full-shard tails remain unresolved. |
| P04 | DEFERRED_WITH_JUSTIFICATION | 64-context unit implementation/resume passed synthetic tests, but harness failed before any cluster unit. Zero completed units here do not establish checkpoint inefficiency. |
| P05 | MITIGATED | Static failure code/frame, phase timings and exact equivalence counts survived. Captured-timer aliasing is newly identified below; durable gate receipt is used. |
| P06 | NOT_CAUSAL in observed gate | ICU 2 calls / 0.000210 s, Q5 alignment 0.000173 s; no eligible Q5 removals. Rare/heavy behavior and coexistence on the full shard untested. |
| P07 | INFORMATIONAL | This failure is not a walltime/memory failure. CPU/RSS/accounting recorded; no resource increase or full-runtime extrapolation justified. |
| P08 | MITIGATED; long run unverified | Gate sampled WAL 535 bytes; absent after close; per-context checkpoints completed. Bounded long-shard transaction/WAL behavior untested. |
| P09 | DEFERRED_WITH_JUSTIFICATION | Exact 4424-context population was specified, but indexed-table rename prevented entering its replay. The short-slice coverage limitation persists. |
| P10 | OBSERVABILITY_ONLY; correction needed | Two RSS sources and inclusive timings preserved. Mutable nested snapshots included later SQL work in final report's earlier gate subsection; immutable gate receipt corrects reporting here. |
| P11 | MITIGATED statically; NOT_CAUSAL here | Full publication/reopen replays remain implemented and were not invoked by this nonpublication harness. Their full-run cost remains unmeasured. |
| P12 | INFORMATIONAL | 16-context scientific equality/runtime pins passed; all failed artifacts retained. No candidate, acceptance, replacement/full retry, science change or operating-budget selection. |

## New bounded confirmation defect ledger

| ID | Classification | Finding and disposition |
| --- | --- | --- |
| C01 | REVIEW_HARNESS / IMPLEMENTATION | Rename of indexed `stage10_context_keys` raises DependencyException before shard replay. Same-version synthetic reproduction confirms an independently sufficient cause. OPEN for owner-reviewed harness correction; no cluster mutation or resubmission. |
| C02 | REVIEW_HARNESS | Local helper-level test bypassed the failing indexed selection-setup statements. OPEN: require an end-to-end synthetic setup using the same recovered table/index shape and all setup-to-pass transitions. |
| C03 | OBSERVABILITY | `Progress.snapshot()` returns the mutable `self.timings` mapping. The final result's saved gate SQL timing changed from 434 calls / 2.449585547 s to 435 / 2.536447530 s after the failed rename. A public test reproduces mutation of a previously captured snapshot. Reporting here uses immutable gate bytes; code correction (independent nested timing copies plus regression test) remains OPEN. |

The C03 defect does not alter scientific rows, their comparison, the gate's
separately serialized bytes or its recorded completion counts. It does prohibit
treating the final report's nested gate timer as a frozen earlier observation.
All original receipts are retained verbatim; none is silently rewritten.

The original R01–R14 pre-submission findings remain documented in the
[consolidated repair record](STAGE10_PERFORMANCE_REPAIR.md). This reconciliation
supersedes any inference that passing helper tests validated the complete
cluster harness. No further bounded defect is established by the available
aggregate evidence and static review. Long-run throughput uncertainty remains
explicit rather than being mislabeled as resolved.

## Evidence and next boundary

- [Unmodified sanitized terminal result](../scientific_assets/stage10_repair_confirmation_1774012.json):
  SHA-256 `ff48639de91729d66e9927faed8d9042e556e2a9bf4af7ade433e654e92a20e5`.
- [Unmodified sanitized equivalence gate](../scientific_assets/stage10_repair_equivalence_gate_1774012.json):
  SHA-256 `e7dd39a3abf096f404be49a2e8faeca515e0b3951891644a95300aac755438b6`.
- [Accounting and file metadata](../scientific_assets/stage10_repair_accounting_1774012.json),
  [public synthetic reproductions](../scientific_assets/stage10_repair_synthetic_review_1774012.json)
  and [original submission receipt](../scientific_assets/stage10_repair_confirmation_submission_1774012.json).
- [Review hash inventory](../scientific_assets/stage10_repair_review_inventory_1774012.json) binds the portable evidence and this reconciliation.
- Original stdout/stderr remain private and hashed; stderr is empty. The exact
  Goethe checkout is still clean and detached at the executable SHA. There is
  no first-pass, repartition or resume directory, candidate manifest or seal.

**NEXT: OWNER REVIEW OF THE CONFIRMATION HARNESS/OBSERVABILITY FAILURE.** No
replacement execution or full DEVELOPMENT retry is authorized by this result.
Executable/scientific files and Stage 0–9 are unchanged in this reconciliation.
Operating budget UNSELECTED; HOLDOUT sealed; production/Pelias untouched;
Stage 11 NOT STARTED; Stage 10 NOT ACCEPTED.
