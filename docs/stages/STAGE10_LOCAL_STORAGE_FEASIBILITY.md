# Stage 10 job-local storage feasibility

## Authority and scope

The owner authorized one public/synthetic Goethe SLURM local-storage probe and
read-only historical storage measurements. No protected payload is needed by
the probe. No scientific candidate, full DEVELOPMENT execution, cleanup,
checkpoint-contract exception, HOLDOUT/production/Pelias access or Stage 11 work
is authorized here. Scientific executable remains
`7353e3197adcb1b38cc821f48ee3d7da6d1f529c`; its code is unchanged.

## Probe

`scripts/stage10_local_storage_probe.py` and
`cluster/goethe_nhr/stage10_local_storage_probe.sbatch` request one general1 node,
one CPU, 1 GiB memory, `--tmp=1024M`, five minutes, no requeue. Code must arrive
through Git in a clean detached checkout of the exact pushed probe commit.
The shared execution guard runs before filesystem access.

The probe checks the scheduler-created job-local root, creates a private child,
writes/reads/hashes 16 MiB of invented bytes, tests rename and file/directory
fsync, checks SQLite WAL/commit/checkpoint/reopen, and verifies a 64 KiB synthetic
copy onto a distinct PanFS filesystem. It creates no registration or commit
seal. Durable sanitized JSON/stdout live in a new private home-directory probe
area; only the small invented copy lives in its own private PanFS probe area.
The source directory and receipt paths are unique to this feasibility test.

No active waiting loop is permitted. After the single submission, inspect state
once; PENDING/RUNNING means report job details and stop until owner continuation.
On completion inspect accounting/result once. Attempt a read-only check of the
recorded job-local marker on that node after termination if cluster access
permits; otherwise automatic cleanup remains documented policy rather than an
experimentally observed outcome. Never treat node-local data as durable.

## Documentation versus measured configuration

[Goethe storage documentation](https://wiki.csc.uni-frankfurt.de/wiki/doku.php?id=public:usage:goethe)
describes `/local/$SLURM_JOB_ID`, requesting local space with `--tmp`, and
automatic deletion after a batch job ends. It describes up to 1.4 TB per node.
[Slurm sbatch documentation](https://slurm.schedmd.com/sbatch.html)
defines `--tmp=<size>[units]`, with explicit M/G suffixes and MiB default units.
Use explicit `1024M` to avoid decimal-GB ambiguity.

Read-only scheduler inspection on 2026-09-25 found `TmpFS=/local`, local
prolog/epilog hooks, general1 maximum walltime 21 days, and 1,400,000 MiB
configured TmpDisk on the sampled general1 nodes. These are configuration
values, not proof of currently writable capacity or exclusive allocation.
The probe must supply runtime evidence. Larger `--tmp` filters eligible nodes;
configured TmpDisk is not itself a filesystem free-space guarantee.

## Historical measurements and contract findings — preliminary

Read-only allocated-size measurements of candidates 1774362 and 1781277 include
all files under their immutable output and work roots. No relation contents were
opened. The old committed candidate occupies 169,463,808 allocated bytes
(0.157825 GiB), including its two relations, summary, manifest and seals.
The corrected-provenance attempt has the same measured relation-directory
allocation; final publication was not completed and its absent registration/seal
must be budgeted separately.

The latest completed generation workspace occupies 3,565,705,728 allocated bytes
(3.320822 GiB), including 907,564,032 bytes in its shards tree. Unit checkpoint
subtrees account for 746,172,416 bytes; coalesced prefix relation subtrees account
for 159,645,696 bytes. These are terminal allocations, not an observed peak.
WAL/spill high-water and publication overlap must be included before recommending
a local request or durable PanFS reserve. Exact final calculations remain pending
the synthetic test and final reconciliation.

The current executable hard-codes workspace creation under PanFS `work/`,
requires its resume root there, and enforces both filesystem and project-quota
256 GiB reserves. Merely adding `--tmp` does not redirect it. Any prospective
operational path/reserve change needs separate implementation approval and a new
executable; exact checkpoint execution identity cannot be rewritten.

Checkpoint v3 adoption validates relation payloads, diagnostics, inventories,
hashes and seals, not seals alone. Preserve durable payloads and exact bindings
for cross-job resume. Losing them at job termination would remove the approved
resume capability. The existing publication builder already performs exclusive
destination creation, copy, fsync, byte hash and logical fingerprint validation;
it does not rely on cross-filesystem rename of the workspace. Publication and
registration/sealing must remain on the approved PanFS topology.

## Local validation

Probe Ruff lint/format, mypy with repository source resolution, SBATCH syntax,
and diff checks passed. Synthetic helper checks passed readback/hash, fsync,
exclusive-create collision and rejection by the shared guard without the
required execution markers. No claim of Goethe local-storage success is made
until the one scheduled probe completes.

## Reconciliation of the one probe — 1784651

Probe executable `e88ea392ddb9ef7d1787ba3ec65d97f251d81a55` was submitted once
at 2026-09-25T11:04:04Z. It ran on `node26-015` and failed in one second,
`FAILED / 1:0`. Scheduler accounting reports 1 CPU requested, 80 allocated
(whole-node partition), 1 GiB memory and `MinTmpDiskNode=1G`.

Observed before failure:

- `/local/1784651` existed, owner donyadidegan/UID 60099, mode 0700.
- Local filesystem `/dev/sda4`: 1,776,353,848 KiB total;
  1,763,935,816 KiB available (1682.220 GiB). These are underlying filesystem
  values, not proof of a per-job quota guarantee.
- The Python entry point used system Python 3.9. Importing the shared guard first
  imports the package initializer, which requires installed distribution metadata.
  `importlib.metadata.PackageNotFoundError: safe-geocoding-pipeline` terminated
  the process before any invented bytes or SQLite data were created.
- The shell terminal receipt records exit 1. No synthetic result JSON or
  cross-filesystem copy exists. Protected payload access was zero.

This is a **probe launcher defect**, not evidence of local filesystem
incompatibility. Write/read/SHA-256/fsync/SQLite remain **NOT TESTED on Goethe**.
Post-job SSH to the node was denied; cleanup is documented policy, not directly
observed. No further allocation or job was requested to bypass that restriction.

The launcher correction selects the same installed Stage 6 Python environment
already used by the Stage 10 executable, without modifying that runtime. An
isolated local source checkout without installed metadata reproduced the import
failure; the installed local environment imports the same guard successfully.
A failing-then-passing launcher check requires the explicit installed interpreter.
Ruff, mypy, shell syntax and diff validation pass. The correction is prepared,
not cluster-validated. **A replacement probe requires fresh owner authorization;
the one-job allowance has been used.**

The [sanitized measurement record](../scientific_assets/stage10_local_storage_feasibility_1784651.json)
binds the failed probe and separates measurements from estimates.

## Component placement and checkpoint decision

The following is a proposed operational split, not an implemented exception to
the current executable's path/reserve guards.

| Component | Classification | Requirement |
|---|---|---|
| Generation DuckDB, WAL and spill | LOCAL_TRANSIENT_ALLOWED | Rebuild from pinned inputs and retained checkpoints; no scientific authority |
| Parser/reference certificates, reference index/payload store, context indexes/keys | LOCAL_TRANSIENT_ALLOWED | Exact deterministic derived work; source evidence stays on PanFS |
| Intermediate SQL tables, alignment/selector spill | LOCAL_TRANSIENT_ALLOWED | Keep all scientific identities and algorithms unchanged |
| Publication replay working state | LOCAL_TRANSIENT_ALLOWED | Existing three replays reuse the same workspace; no three full copied datasets |
| Independent validation/audit database and spill | LOCAL_TRANSIENT_ALLOWED | Read authoritative PanFS inputs; persist sanitized result separately |
| Unit relation payloads and diagnostics | PANFS_CHECKPOINT_REQUIRED | Inventories/hash validation and adopted output require actual bytes |
| Unit manifests/seals, prefix indexes and coalesced prefix relation files | PANFS_CHECKPOINT_REQUIRED | Preserve full checkpoint-v3 topology and exact executable binding |
| Phase/checkpoint/termination receipts and SLURM logs | PANFS_DURABLE_REQUIRED | Persist during execution, not just on graceful termination |
| Final relations, summary, manifest, registration, `_COMMITTED` | PANFS_DURABLE_REQUIRED | Accepted publication protocol/topology unchanged |
| Future unmeasured spill high-water | UNKNOWN | No historical peak trace establishes a hard upper bound |

**Checkpoint answer: A.** Keeping only compact seals on PanFS is insufficient.
The full existing checkpoint tree is included below, including coalesced prefix
relations; no pruning/reconstruction exception is assumed. Moving it entirely to
ephemeral local storage would lose the approved cross-job adoption capability.
Any split implementation must accept explicit transient and durable roots;
symlinks or bypassing `controlled_path` are not an acceptable shortcut.

## PanFS capacity calculation

Allocated bytes were measured read-only with `du -x -B1` and `stat/find` block
counts. Parent totals include directory allocation. No protected relation rows
were read or exported. All historical runs remain unchanged.

| Component | Allocated bytes | GiB |
|---|---:|---:|
| Final artifact (committed 1774362) | 169463808 | 0.157825470 |
| Full durable checkpoint tree (larger of 1774362/1781277) | 907564032 | 0.845234871 |
| Durable receipts/logs (larger measured aggregate) | 29304320 | 0.027291775 |
| Additional full publication staging tree | 0 | 0 |
| Measured durable subtotal | 1106332160 | 1.030352116 |
| Publication/operational safety margin | 77667328 | 0.072333336 |
| **Minimum planning headroom** | **1183999488** | **1.102685452** |
| **Recommended free PanFS capacity** | **2147483648** | **2.000000000** |

The receipt/log aggregate is the larger historical progress/attempt metadata
plus SLURM stdout/stderr allocation. Safety margin comprises one additional
largest checkpoint unit (31,965,184 bytes), the largest checkpoint relation file
(37,797,888), observed old/new checkpoint-tree allocation variation (7,891,968),
and an extra in-progress marker allocation (12,288). This is an explicitly
proposed engineering allowance grounded in measured objects, not a frozen science
change or a proven upper bound on every possible failure. Recommended capacity
rounds the resulting total up to the next whole GiB. Shared-user activity must
still be checked immediately before a future run.

Staging is not counted twice: current publication reserves the unique final
directory first and streams exclusively created destination files into it.
The incomplete bytes are already the final-artifact allocation. A design that
introduced a second full PanFS staging copy would need to add that copy.
No historical data is assumed deleted, overwritten or adopted under a new SHA.

Fresh quota at **2026-09-25T11:40:56Z**: limit 122558593750 KiB, used
122558531828 KiB, available **61922 KiB = 0.059053421 GiB**. The deficit is
**1.043632030 GiB** to the minimum planning headroom, or **1.940946579 GiB**
to the recommended 2 GiB free target. The final artifact alone is larger than
current capacity. This proves that current free PanFS space is insufficient even
before deciding the local-I/O question.

The 2 GiB target applies only to a separately approved/validated split-workspace
implementation. Exact executable 7353e319 still requires 256 GiB and writes its
workspace to PanFS. It cannot be run unchanged with this smaller reserve.

## Local request calculation — provisional, not a measured peak

The latest historical non-checkpoint/progress files occupy 2,630,419,968 allocated
bytes on PanFS but have **4,758,715,819 apparent bytes (4.431899 GiB)**. Use the
larger apparent size when estimating local storage: PanFS allocation/compression
must not be assumed on the local filesystem. Successful job 1774362 recorded a
sampled WAL high-water of **29,679,390 bytes (0.027641 GiB)**. Terminal spill was
empty; its earlier peak is unknown. The database alone has 3,776,720,896 apparent
bytes. One forensic validation left only 294,912 allocated bytes of receipts and
empty spill, but this does not establish every future audit's peak memory/spill.

Provisional model: terminal transient bytes plus sampled WAL = **4.459541 GiB**.
Allow a second full measured transient footprint for rewrite/temporary overlap,
then round up: ceil((2 × 4758715819 + 29679390) / 2^30) = **9 GiB**.
Proposed scheduler request **`#SBATCH --tmp=9216M`**, with **4.540459 GiB**
headroom over that terminal-plus-WAL estimate. This is a planning allowance,
not an experimentally validated full-run peak or a local quota guarantee.
Unknown spill peak and the failed write probe prevent presenting it as final
execution approval. No hundreds-of-GiB local request is supported by the measured
DEVELOPMENT footprint.

## Proposed publication flow and remaining gates

PanFS accepted inputs → local DuckDB/certificates/indexes/spill → durably written
PanFS checkpoint payloads/seals and receipts → exclusive copy into a new reserved
PanFS final directory → fsync and SHA-256/logical checks → required scientific
replays → corrected registration → exclusive `_COMMITTED` → PanFS reopen.

No cross-filesystem rename is used. The existing builder already copies and
verifies, but path routing, progress/checkpoint roots, local capacity checks,
audit scratch routing and a measured PanFS reserve gate would require explicit
operational implementation approval and validation. Frozen science, checkpoint
bindings and publication commit ordering must remain unchanged.

**Practical finding:** more available project space is required at today's quota.
Request a target of at least 2 GiB free (about 1.941 GiB additional availability)
for the proposed split, subject to its remaining gates. Local write capability
has not yet been established; none of the three successful/incompatible final
outcome markers can honestly be asserted from this failed probe. Stop for owner
authorization of one corrected public-only probe. No full DEVELOPMENT run,
second probe, cleanup, science change or Stage 11 work occurred.

## Owner-authorized replacement probe

The owner subsequently authorized exactly one replacement PUBLIC/SYNTHETIC
probe, with `--tmp=9216M`. No full DEVELOPMENT run or split-workspace
implementation is authorized. Historical job 1784651 and its receipts remain
unchanged. The launcher bytes from `44154e5aeced9863132095eb4821d2a303dd56f6`
remain unchanged; the submission command overrides only its `--tmp` directive.
The expanded probe script and tests are bound to a new descendant executable.

Before submission, read-only venv configuration/distribution metadata identifies
Python 3.14.3, SAFE 0.2.0 and DuckDB 1.5.5. The script checks the exact expected
Python executable and venv prefix, SAFE source location in the detached checkout,
installed package metadata and DuckDB version before I/O. It records those
identities and checks the live scheduler's `MinTmpDiskNode` equals 9 GiB.

The added public-only DuckDB test performs one bounded insert transaction,
observes a nonempty WAL, uses a temporary table, verifies rollback, checkpoints,
closes, fsyncs and reopens the database, and compares the ordered invented rows
and SHA-256 digest. The existing 16 MiB local file and SQLite checks remain.
The local-to-PanFS test streams only 64 KiB into a new exclusively created file,
fsyncs, reopens and hashes it. After checking the exact owning UID, inode/device,
regular-file type and link count, it removes that same synthetic file and
records allocated bytes used/released and before/after project-quota snapshots.
It never removes its parent, historical evidence or scientific files.

In-job cleanup validates a closed allowlist of invented files and an empty
DuckDB spill directory, removes only owned synthetic objects, then removes its
own empty local child directory. This tests in-job cleanup; it does not claim
to observe the scheduler epilog from inside the job. Sanitized success/failure
receipts and stdout/stderr remain in a new private home-directory test area.

Seven focused synthetic tests cover runtime rejection/identity, real DuckDB
WAL/transaction/checkpoint/reopen, copy/hash/cleanup, refusal of wrong ownership
or symlinks, exclusive destination collision, and complete local I/O/cleanup.
The initial missing helpers failed all seven tests; the implementation passes
all seven. Launcher identity remains pinned to the corrected 44154e5 version.
Submission still requires committed/pushed probe code, a clean detached Goethe
checkout, private new test destinations, and one exclusive submission receipt.
PENDING/RUNNING means report once and stop; no automatic retry after failure.

## Replacement result — 1784678

On owner continuation, one terminal accounting inspection reported **COMPLETED /
0:0, five seconds**, on `node24-005`. The controller had already expired the job;
the accounting record, durable JSON result and shell terminal receipt agree.
The [sanitized result and capacity reconciliation](../scientific_assets/stage10_local_storage_replacement_1784678.json)
bind probe executable `1dc03f99d0e53450d89b47b8fda92c9286a8c216` and the unchanged
approved launcher from `44154e5aeced9863132095eb4821d2a303dd56f6`.
Submission was 2026-09-25T11:54:32Z; execution ended at 12:17:27Z.

The request was 1 CPU, 1 GiB memory, five minutes, `--tmp=9216M`, general1.
The scheduler accepted `MinTmpDiskNode=9G`; its whole-node allocation used
80 CPUs, though the probe requested and used one task/thread. Runtime checks
confirmed Python 3.14.3 in the pinned SAFE venv, SAFE 0.2.0 loaded from the exact
detached checkout, and DuckDB 1.5.5. No system-Python fallback occurred.

Observed `/local/1784678`: donyadidegan/UID 60099, mode 0700; available capacity
**1682.220284 GiB**, total **1694.063042 GiB**. These are filesystem capacity
values, not a per-job reserved-capacity guarantee. All synthetic files were 0600.

- 16 MiB deterministic file: write, fsync, close/reopen, SHA-256, local rename
  and readback **PASS**; temporary-file removal **PASS**.
- SQLite: 1,000 invented rows, integrity check, WAL/checkpoint and exact reopen
  comparison **PASS**.
- DuckDB: 2,048 invented rows, 32-row temporary table, transaction rollback,
  checkpoint, close/fsync/reopen and ordered row/hash comparison **PASS**.
  WAL was 76,072 bytes before checkpoint and zero after checkpoint.
- Local-to-PanFS copy: 64 KiB synthetic payload, distinct filesystems, exclusive
  destination creation, fsync and SHA-256 equality **PASS**. Allocated file space
  used/released was **208,896 bytes (0.000194550 GiB)**. Only that verified-owned
  synthetic object was removed. Read-only post-job verification confirms absence.
  The in-job quota snapshots were equal before copy and after cleanup; this
  tiny test does not measure delayed or shared quota accounting precisely.
- In-job local cleanup **PASS**; free blocks/inodes returned to their starting
  values. This does not independently establish scheduler epilog cleanup.
  Sanitized evidence and the empty private PanFS probe parent remain preserved.

Fresh `pan_df -k /work/footprint` at **2026-09-25T12:32:16Z** reports limit
122558593750 KiB, used 122558537340 KiB, available **56410 KiB = 0.053796768 GiB**.
The measured-object planning minimum remains **1.102685452 GiB**, recommended
free capacity **2 GiB**. Current deficits are **1.048888683 GiB** to the minimum
and **1.946203232 GiB** to the recommendation. Ask for enough additional shared
project capacity to leave at least 2 GiB free immediately before a future split
run; shared activity can change this requirement.

The local terminal-plus-sampled-WAL estimate remains **4.459541 GiB**, with a
provisional **9 GiB / `--tmp=9216M`** request and **4.540459 GiB** headroom. The
small successful probe establishes filesystem/database primitives, not a peak
measurement of the full scientific workload. Historical spill peak is unknown.

**LOCAL STORAGE TECHNICALLY USABLE: YES.**
**PANFS ADMIN/QUOTA SPACE STILL REQUIRED RIGHT NOW: YES.**

No split-workspace implementation or full DEVELOPMENT run occurred. The existing
scientific executable still requires 256 GiB and PanFS workspace routing; the
smaller reserve applies only after separately approved operational changes and
validation. Full checkpoint payloads/seals and final publication stay durable on
PanFS. Stage 0–9/science unchanged; protected payload access zero; HOLDOUT sealed;
production/Pelias untouched; Stage 11 NOT STARTED; Stage 10 NOT ACCEPTED.

NEXT: OWNER REVIEW OF SPLIT-WORKSPACE IMPLEMENTATION.
