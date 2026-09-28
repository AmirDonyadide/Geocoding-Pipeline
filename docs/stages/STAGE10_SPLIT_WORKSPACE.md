# Stage 10 split workspace implementation

## Approved boundary and implementation plan

The owner accepted public probe 1784678 and authorized this operational refactor
against scientific executable `7353e3197adcb1b38cc821f48ee3d7da6d1f529c`.
No full DEVELOPMENT execution, extra cluster test, science change, HOLDOUT,
production, Pelias or Stage 11 work is authorized. Operating budget UNSELECTED.
The [measured feasibility record](STAGE10_LOCAL_STORAGE_FEASIBILITY.md#replacement-result--1784678)
supplies the storage estimates. Frozen scientific documents are not edited.

Implement inline on `perf/stage10-split-workspace`:

1. Add a fail-closed operational storage module: scheduler/site and exact user,
   numeric job ID, nonsymlink private writable local root, distinct filesystem,
   9 GiB startup capacity; unique private child below
   `/local/$SLURM_JOB_ID/safe_geocoding_pipeline/stage10`. No path override or
   PanFS fallback in protected execution. Test rejection before input access.
2. Give `ContextWorkspace` explicit transient `root` and `durable_root`.
   Keep its database, certificates, indexes and spill under `root`; put progress
   and unchanged checkpoint payloads/seals under `durable_root`. Route materializer
   inventories and publication source files through the durable root. Preserve
   a colocated default only in unguarded synthetic/library mechanics; protected
   entry points always supply the split roots.
3. Allocate durable attempt/failure receipts before local working directories.
   Record local workspace class/path/presence as operational provenance only.
   Keep original exception handling and preallocated receipt guarantees. Route
   the post-publication audit database/spill locally and its result/failure
   receipts durably. Validate paths for audit without requiring another new-run
   reserve after the candidate has already consumed its allocation.
4. Change both active DEVELOPMENT launchers to 9 GiB tmp and retain the approved
   4 CPU / 32 GiB / 36 h request. Gate new generation at 2 GiB effective project
   quota and filesystem availability. Minimum 1.102685452 GiB is planning evidence,
   not a lower automatic execution threshold. Validation still enforces all
   identity, runtime, site, privacy and topology gates.
5. Add failing-then-passing guard, split generation/equivalence, local-loss resume,
   copy interruption/hash corruption and durable failure tests. Compare complete
   relations, including C01 provenance, across alternate transient roots and
   the colocated layout. Preserve exact checkpoint executable binding and C02.
6. Run focused/full safe tests, static checks, frozen assets/runtime inventory,
   shell/docs/privacy checks; complete one bounded review; update implementation
   inventory, commit/push and measure fresh PanFS quota. Stop without submission.

## Review focus

- Symlink/foreign owner/local capacity failure must never redirect writes to PanFS.
- All checkpoint bytes required for adoption must survive complete local loss.
- No transient root enters scientific or checkpoint identity payloads.
- New-generation reserve must not be reapplied after durable output exists.
- Input/preparation and post-publication audit failures must retain durable evidence.

## Storage accounting

Durable checkpoint layout and final copy topology remain unchanged: final
169463808 bytes, checkpoints 907564032, historical receipts/logs 29304320,
separate full staging 0, safety allowance 77667328. The new audit receipt set
adds a conservative 360448-byte allowance: the measured historical forensic
receipt-directory allocation (294912 bytes) plus its new 65536-byte reserved
failure slot. This budgets the durable audit result, phase receipt and directory
allocation without consuming the original publication margin. Receipt/log
planning total is therefore 29664768 bytes. Revised minimum planning reserve is
1184359936 bytes (1.103021145 GiB); recommended/automatic new-generation gate
remains 2147483648 bytes (2 GiB). No large transient database is copied back.
These are historical DEVELOPMENT planning estimates, not future peak guarantees.

Local estimate is 4788395209 bytes (terminal apparent transient files plus
sampled WAL), not an observed peak. Request 9663676416 bytes (9216 MiB); historical
spill peak remains unknown. Keep runtime capacity/error checks and durable
failure evidence. Synthetic plumbing cannot prove full-workload peak usage.

## Implementation and review ledger

| Area | Disposition and evidence |
|---|---|
| Explicit roots and fail-closed startup | PASS: exact scheduler/user, numeric job, private nonsymlink writable root, distinct filesystem and capacity; no PanFS fallback |
| Durable checkpoint payloads/seals | PASS: unchanged layouts/bindings; synthetic complete local loss followed by adoption with zero context/certificate generation |
| Scientific equivalence | PASS: load exact SHA-7353 context/materializer/checkpoint/family code with inventory hash checks; 16 invented contexts / 96 decisions compare exactly, including full hypotheses and C01 provenance |
| Scientific identity and C01/C02 | PASS: paths only in operational provenance; exact checkpoint bindings, corrected registration and source-anchoring rules retained; frozen design/runtime inventory checks pass |
| Cross-filesystem publication | PASS: explicit exclusive copy/fsync/hash/reopen, never cross-filesystem rename; interruption/corruption prevent seal; required scientific replays retained |
| Audit local database and durable receipts | FIXED: audit database/spill routed locally; successful audit result and failure evidence remain durable; validation does not reapply fresh-generation reserve |
| Local-stat error masking (review finding) | FIXED: unavailable local stat yields UNAVAILABLE/null presence; EIO/EACCES/ESTALE tests observed failing then passing while original exception remains recorded |
| Portable audit report-write failure (self-review finding) | FIXED: report persistence moved inside the preallocated failure-receipt scope; injected allocation failure produces durable primary-error evidence, no false audit completion |
| Resource model and privacy | PASS with stated limits: 9 GiB provisional local request, 2 GiB PanFS gate; no protected local tests, no scientific/archive cleanup; full-run local peak remains unmeasured |

Validation on pinned local Python 3.14.3: **1185 safe tests PASS, 24 exact-ICU
tests SKIP**, including Stage 8/9 regressions and all Stage 10 tests. Split
subset: **26 PASS**. Exact ICU runtime is unchanged and remains externally hash
pinned for Goethe startup; no version guard bypass. Strict mypy passes 148
maintained source/script/Stage 10 test files (`--follow-imports=silent` leaves
historical untyped imported test modules outside that check). Maintained-tree
Ruff lint/format, shell syntax, schema/spec/runtime lock, implementation
inventory, CLI/help, docs/links, privacy and diff checks pass. Historical Stage 9
review-archive Ruff findings and legacy test mypy diagnostics remain untouched.

The author completed the bounded ledger; a fresh read-only code reviewer
completed the remaining checks and found no unresolved material defect after
the local-stat repair. Synthetic verification does not prove future local peak
capacity or survival if PanFS itself is unavailable.

## Owner continuation and execution boundary — 2026-09-28

The owner subsequently authorized completing this implementation and **one**
new full DEVELOPMENT generation after all gates pass. Initial fresh quota at
2026-09-28T08:03:22Z: limit 122558593750 KiB, used 121856256657 KiB, available
702337093 KiB (669.800847 GiB). `pan_df -i` reports no inode quota figures.
Recheck authoritative project capacity immediately before the sole submission.
Use 4 CPUs / 32 GiB / 36 h / `--tmp=9216M`; preserve all historical attempts.
No job has been submitted at this implementation checkpoint. Stage 10 remains
NOT ACCEPTED, operating budget UNSELECTED; HOLDOUT sealed, production/Pelias
untouched, Stage 11 NOT STARTED.
