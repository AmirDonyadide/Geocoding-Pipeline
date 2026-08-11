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

Future full-production commands in Phases 4, 5, 8, 9, 10, 11, 12, and 13 must
reuse the shared guard for full diagnostics, address-key/deduplication,
geocoding orchestration, candidate selection, usability classification,
coordinate validation, merge-back, and reconciliation. A phase must not invent
an independent permissive environment check.

## Goethe-NHR layout and operating rules

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

- `scripts/sync_to_goethe_nhr.sh` uses a non-destructive rsync allowlist and
  supports `--dry-run`.
- `cluster/goethe_nhr/bootstrap_env.sh` creates or reuses an isolated exact
  runtime and fails `CLUSTER_RUNTIME_NOT_READY` rather than substituting Python.
- `cluster/goethe_nhr/phase03_preflight.sh` validates the site, SLURM job,
  commit, runtime, references, Phase 2 snapshot, Phase 1 anomaly report, and
  node-local space before a production row-column scan.
- `cluster/goethe_nhr/phase03_development_pilot.sbatch` runs the frozen pilot
  stages sequentially in one single-node job. It never creates or reads a
  LOCKED payload. Persistent results are validated and atomically promoted
  before `DEVELOPMENT_PILOT_PASS` is reported.

The initial job request is one node, one task, four CPUs, 16 GiB memory, and a
12-hour walltime. No partition or account is hardcoded; the user's permitted
SLURM defaults apply. The runner is mostly single-process, and per-stage GNU
`time` reports record actual CPU and memory use for later engineering review.

SLURM logs contain job/environment identity, stage transitions, aggregate
timing and validation outcomes. They must not contain addresses, stable or
provider identities, candidate values, credentials, or authorization headers.
