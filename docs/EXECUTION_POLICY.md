# Execution policy

## Permanent rule

**HEAVY OR PROTECTED PRODUCTION PROCESSING = GOETHE-NHR SLURM ONLY.**

It must not run on the MacBook or a Goethe login node. When uncertain, classify
the work as Goethe-NHR-only. Project approval of a scientific stage does not
waive the execution-site rule.

## Heavy-process definition

An operation is heavy when any one condition applies:

- scans the complete production Stage 1 snapshot;
- processes at least 1,000,000 production rows or a substantial fraction of
  the 141,048,582-row production population;
- creates at least 2 GiB of temporary/working state;
- is expected to run at least 10 minutes locally;
- performs full-production joins, grouping, sorting, deduplication, address
  keys, transformations, validation, query generation, geocoding, selection,
  merge-back, or reconciliation; or
- performs any complete production Stage 2 or later-stage run.

This is an OR rule. One condition is sufficient.

## Fail-closed guard

Heavy/protected production entry points invoke the common execution guard
before opening production input. Both values are mandatory:

```text
SAFE_EXECUTION_SITE=goethe-nhr
SLURM_JOB_ID=<non-empty>
```

Missing or incorrect markers raise `HEAVY_PROCESS_CLUSTER_REQUIRED`. There is
no ordinary local override. Synthetic fixtures use explicit non-production
paths and remain locally testable.

Future full-stage commands must reuse the shared guard instead of inventing a
permissive check.

## Goethe-NHR operating rules

- The login node is for SSH, Git/light shell operations, transfer, `sbatch`,
  `salloc`, `srun`, and scheduler/accounting inspection only.
- Python, tests, profiling, and data processing run inside a scheduled job or
  allocated compute-node shell.
- Controlled directories use `0700`; controlled files use `0600`.
- High-volume project storage uses personal `/work`.
- `/scratch` is prohibited.
- `/work/footprint/public` is not modified.
- The shared Conda base is not modified.
- Credentials and authorization headers are never printed or logged.
- Logs contain execution identity, stage transitions, aggregate timing, and
  validation status—not addresses, row identities, provider IDs, or secrets.

The canonical institutional repository root is
`/work/footprint/donyadidegan/safe_geocoding_pipeline`. It remains in cluster
assets because it is an explicit deployment contract, not a portable personal
path.

## Git and worktree contract

Code reaches Goethe through GitHub, not source-file rsync. Before submission:

- fetch `origin` and inspect status/divergence;
- use a clean exact pushed commit;
- use a clean tracking branch updated with fast-forward-only semantics or a new
  detached integration worktree;
- record the full SHA in submission arguments; and
- create the owner-only SLURM log directory before submission.

An SBATCH script never pulls code. It verifies the declared SHA against its
worktree before protected input access. Dirty, diverged, failed-run, or audit
worktrees are not overwritten or reused.

## Storage and publication contract

Protected inputs and outputs remain under controlled storage such as
`derived/controlled/`; generated protected reports remain under
`reports/generated/`; logs remain under `logs/slurm/`. All are ignored by Git.

Run directories are immutable and collision-failing. Publication uses private
temporary state, content/readback validation, permission validation, terminal
markers, fsync where required, and atomic rename. Failures and partial attempts
are preserved for diagnosis rather than silently replaced.

## Data transfer boundary

The repository's transfer scripts are explicit allowlist helpers for reviewed
historical payloads or hash-pinned source scopes. They do not upload to an
external service and do not transfer source code/Git metadata. Existing helpers
that name an exact historical 206-shard Phase 2 payload remain historical
reproducibility assets; they are not generic authorization for the 1,411-file
production population.

No full source collection is transferred without explicit approval. A transfer
does not itself authorize processing.

## Runtime contracts

The accepted Stage 3 execution runtime is Python 3.14.3 with
`unicodedata.unidata_version == "16.0.0"`, ftfy 6.3.1, and PyArrow 25.0.0.
Stage 3 bootstrap and preflight checks fail instead of substituting a different
runtime. Node-local temporary storage must be validated before use; network
filesystems and insufficient free space fail closed.

## Validation modes

Local-safe repository validation is:

```bash
python3 -m pytest -m "not requires_production_transfer_payload"
```

Full-environment validation is `python3 -m pytest` and requires exact ignored
controlled transfer artifacts. Missing protected prerequisites are a failure,
not a skip. Protected data must not be accessed merely to make a cleanup or
documentation test pass.

## Current authorization boundary

- Production Stage 0: `NEW_STAGE0_1411_ACCEPTED`.
- Production Stage 1: `NEW_STAGE1_1411_ACCEPTED`.
- Production Stage 2: **NOT STARTED**.
- Production Stage 3: **NOT STARTED**.
- Stage 4 DEVELOPMENT: **`STAGE_4_ACCEPTED`**.
- Production Stage 4: **NOT STARTED**.
- Stage 5 DEVELOPMENT: **`STAGE_5_ACCEPTED`**.
- Production Stage 5: **NOT STARTED**.
- Stage 6 DEVELOPMENT and production: **NOT STARTED**.

This policy grants no scientific-stage or production-run authorization.
