# Execution policy

## Permanent rule

**HEAVY PRODUCTION PROCESSING = GOETHE-NHR ONLY.**

Heavy production work must execute as a scheduled SLURM job on Goethe-NHR. It
must not run on the MacBook or on a cluster login node. When classification is
uncertain, default to Goethe-NHR.

The MacBook is for code and documentation work, Git, unit and synthetic tests,
small diagnostics, lightweight validation, and small controlled manual-review
workflows. It is not the default production executor merely because the
authoritative data is locally accessible.

## Heavy-process definition

An operation is heavy if any one of these conditions applies:

- it scans the complete production Phase 2 snapshot;
- it scans at least 1,000,000 production rows;
- it processes a substantial fraction of the 20,600,000-row dataset;
- it creates at least 2 GiB of temporary or working state;
- it is reasonably expected to run at least 10 minutes on the MacBook;
- it performs a production full-data join, deduplication, sort, or grouping;
- it performs production address-key generation over the full dataset;
- it performs full Phase 3 transformation or production geocoding;
- it performs full-result candidate selection, coordinate validation,
  merge-back, or reconciliation.

This is an OR rule. Meeting one condition is sufficient. Project authorization
for a scientific phase does not waive this execution-site policy.

## Fail-closed enforcement

Production-heavy commands call the shared
`safe_geocoding_pipeline.execution_policy.require_goethe_nhr_slurm` guard before
opening production inputs. Both environment markers must be present:

```text
SAFE_EXECUTION_SITE=goethe-nhr
SLURM_JOB_ID=<non-empty scheduler job identity>
```

A missing or incorrect marker raises `HEAVY_PROCESS_CLUSTER_REQUIRED` with the
message that the operation must run through SLURM on Goethe-NHR. There is no
ordinary `--force-local` or `--allow-heavy-local` bypass. Synthetic fixtures
remain locally testable through explicit non-production code paths.

The completed Phase 1 `FULL_INVENTORY` and Phase 2 `FULL_CONVERSION` entry
points also use the common guard for any future rerun. For the current real
Phase 3 pilot, `pilot-profile`, `pilot-select`, and
`pilot-materialize-development` are cluster-only. Validation of the complete
production Phase 2 snapshot is also cluster-only. `pilot-plan` reads no data and
may run locally. The 8,000-row DEVELOPMENT transformation is individually
lightweight, but it remains in the same cluster job for one reproducible pilot
environment.

The generic Stage 0 production launcher is
`cluster/goethe_nhr/stage00_inventory.sbatch`. Submission must provide the
exact reviewed Git commit/integration worktree, controlled source root,
owner-only population-scope JSON and its SHA-256, reports root, and run ID.
The launcher contains no population-count constant and performs no transfer.

Full `BENCHMARK_SAMPLE_V1` profiling, selection, and materialization is also
production-heavy. It runs through
`cluster/goethe_nhr/benchmark_sample_v1.sbatch`, which requires an exact pushed
commit, detached clean integration worktree, immutable controlled source root,
hash-pinned Stage 0 population scope, explicit source count, and new protected
output path. Production benchmark code calls the shared guard before opening
the source population. Source transfer, when required, uses the separate
scope-driven checksum-reconciling controlled transfer script; it performs no
processing on an external service.

Protected DEVELOPMENT review-subset materialization uses
`cluster/goethe_nhr/development_reporting.sbatch`. The launcher requires an
exact detached pushed commit, SHA-pinned DEVELOPMENT-only benchmark artifact,
accepted Stage 2 bundle/manifest identities, and a new controlled output path.
It rejects HOLDOUT-named paths before Python input access and calls the shared
Goethe/SLURM execution guard. The resulting 500-row artifact is a small review
product, but cluster execution preserves the accepted-data and runtime boundary.

Future full-production commands in Phases 4, 5, 8, 9, 10, 11, 12, and 13 must
reuse the shared guard for full diagnostics, address-key/deduplication,
geocoding orchestration, candidate selection, usability classification,
coordinate validation, merge-back, and reconciliation. A phase must not invent
an independent permissive environment check.

## Goethe-NHR layout and operating rules

Normal access uses the configured local SSH alias:

```bash
ssh goethe
```

The login node is an orchestration boundary, not a Python execution host. It is
limited to SSH, Git and light shell inspection, file transfer, `sbatch`,
`salloc`, `srun`, queue/accounting inspection, and similar low-impact work. Run
Python, tests, profiling, and data processing only within a scheduled batch job
or an allocated compute-node shell.

Repository root:

```text
/work/footprint/donyadidegan/safe_geocoding_pipeline
```

Persistent controlled data, portable generated reports, and SLURM logs use:

```text
derived/controlled/
reports/generated/
logs/slurm/
```

They are created owner-only. High-volume project storage uses personal `/work`,
not home. `/scratch` is prohibited, `/work/footprint/public` is not modified,
and the shared Conda base is not modified. Important code and documentation
remain Git-backed because `/work` is not backed up.

The exact Phase 3 scientific runtime remains Python 3.14.3 with
`unicodedata.unidata_version == "16.0.0"`. A different runtime is not an
acceptable fallback. Candidate SQLite state should use writable node-local
storage selected from `SLURM_TMPDIR`, `TMPDIR`, then a verified local `/tmp`.
Known network filesystem types are rejected and at least 26,843,545,600 bytes
(25 GiB) must be free before Pass 2. If no safe location exists, the job fails
with `NO_SAFE_CLUSTER_TEMP_STORAGE`.

## Paused local pilot record

Local run `phase03_pilot_20260811T082940Z_025fb0ba` is classified as
`ABORTED_LOCAL_EXECUTION_POLICY_VIOLATION`, not a scientific sampler failure.
Its process group was safely stopped before any DEVELOPMENT or LOCKED identity
set or seal was finalized. No DEVELOPMENT or LOCKED payload was materialized,
and no Phase 3 transformation occurred. Partial local SQLite state is retained
temporarily for audit and is neither resumed nor deleted by this maintenance
work.

The Goethe-NHR pilot starts from scratch with a new cluster run ID. The partial
`candidate_state.sqlite3` is not synchronized or resumed. This preserves a
clean host/runtime/filesystem audit boundary without changing the frozen
sampling methodology or its scientific version.

## Cluster workflow

- GitHub `origin` is the shared source of truth for code, tests, configuration,
  and documentation. Source code and Git metadata are never deployed with
  rsync.
- `scripts/sync_to_goethe_nhr.sh` is a controlled-data-only helper. It uses a
  non-destructive rsync allowlist, supports `--dry-run`, and transfers only the
  immutable completed Phase 2 data products plus the approved sanitized Phase
  1 anomaly artifact.
- `cluster/goethe_nhr/bootstrap_env.sh` creates or reuses an isolated exact
  runtime and fails `CLUSTER_RUNTIME_NOT_READY` rather than substituting Python.
- `cluster/goethe_nhr/phase03_preflight.sh` validates the site, SLURM job,
  commit, runtime, references, Phase 2 snapshot, Phase 1 anomaly report, and
  node-local space before a production row-column scan.
- `cluster/goethe_nhr/phase03_development_pilot.sbatch` runs the frozen pilot
  stages sequentially in one single-node job. It never creates or reads a
  LOCKED payload. Persistent results are validated and atomically promoted
  before `DEVELOPMENT_PILOT_PASS` is reported.

### GitHub-first code synchronization

Develop, review, and run lightweight validation on the Mac. Before pushing,
fetch `origin`, inspect status and upstream divergence, exclude all data,
generated output, logs, caches, credentials, environment files, and agent-local
state, then commit and push the coherent change to the appropriate branch.
Never force-push or rewrite shared history without explicit approval.

Before a new cluster submission, use the login node only for Git and light
orchestration:

```bash
ssh goethe
cd /work/footprint/donyadidegan/safe_geocoding_pipeline
git fetch --prune origin
git status --short --branch
git pull --ff-only
git rev-parse HEAD
install -d -m 700 /work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm
```

Run `git pull --ff-only` only on the intended clean tracking branch. If the
checkout is dirty, diverged, or is preserved audit evidence, stop and inspect
it; do not overwrite, reset, clean, or merge automatically. For a reviewed
experimental or historical revision, create a new detached integration
worktree from the exact commit already pushed to GitHub instead of advancing or
repurposing an audit worktree. Confirm the commit is available from `origin`
before submission.

Never run `git pull` or otherwise select code dynamically inside an SBATCH
script. A queued job may start much later; its executable worktree and declared
commit must already be fixed. Important jobs log `git rev-parse HEAD` and fail
closed when it differs from their submitted commit variable. The owner-only
SLURM log directory must exist before `sbatch`, because the scheduler opens its
stdout/stderr targets before the job body can create directories.

The initial job request is one node, one task, four CPUs, 16 GiB memory, and a
12-hour walltime. No partition or account is hardcoded; the user's permitted
SLURM defaults apply. The runner is mostly single-process, and per-stage GNU
`time` reports record actual CPU and memory use for later engineering review.

## Repository validation modes

The local-safe repository validation command is:

```bash
python3 -m pytest -m "not requires_production_transfer_payload"
```

The `requires_production_transfer_payload` marker identifies four cluster-sync
integration tests that execute the real transfer-plan script. They require the
ignored completed Phase 1/Phase 2 transfer payload, including exactly 206 Phase
2 Parquet shards and the approved Phase 1 anomaly artifact. Local-safe runs
report these tests as deselected; their absence is never reported as a pass.

Full-environment validation is:

```bash
python3 -m pytest
```

It runs those four integration tests only when the controlled prerequisites are
present. If they are absent or incomplete, the full command fails rather than
skipping or synthesizing protected artifacts.

SLURM logs contain job/environment identity, stage transitions, aggregate
timing and validation outcomes. They must not contain addresses, stable or
provider identities, candidate values, credentials, or authorization headers.
