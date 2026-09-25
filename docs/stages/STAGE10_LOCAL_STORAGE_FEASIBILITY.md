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
