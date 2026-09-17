# Execution guide

## Environment split

| Environment | Intended work |
|---|---|
| Mac/local | Code, documentation, Git, synthetic/unit tests, small diagnostics and authorized small DEVELOPMENT review |
| Goethe compute node | Protected/heavy DEVELOPMENT work and heavy production processing through SLURM |
| Goethe login node | Git, light shell inspection, file transfer, submission and scheduler/accounting commands |

When classification is uncertain, use Goethe-NHR. Scientific approval never
waives the [execution policy](EXECUTION_POLICY.md).

## Required execution markers

Protected/heavy entry points call
`safe_geocoding_pipeline.execution_policy.require_goethe_nhr_slurm` before
input access. Both markers are required:

```text
SAFE_EXECUTION_SITE=goethe-nhr
SLURM_JOB_ID=<non-empty scheduler job identity>
```

A missing/wrong marker raises `HEAVY_PROCESS_CLUSTER_REQUIRED`. Do not forge a
job ID for local execution. Synthetic tests use explicit non-production paths.

## Exact Git SHA binding

Before an authorized submission:

1. Fetch `origin`, inspect status/divergence and verify the reviewed SHA is pushed.
2. Select a clean worktree at that exact commit; use a detached checkout where
   the launcher requires one.
3. Record the full SHA and exact input/runtime/output bindings in the
   stage-specific submission environment.
4. Create the owner-only SLURM log directory before submission.
5. Submit the reviewed job once and retain its job ID.

The job checks its SHA before protected input access and never pulls code.
Dirty, diverged or audit worktrees must not be reset, cleaned or repurposed.
A pending job is not grounds for a duplicate; follow the recorded stop rule.
See the [launcher index](../cluster/goethe_nhr/README.md) and the relevant
[stage record](stages/README.md), not a generic batch loop.

## Controlled storage

The deployment root is
`/work/footprint/donyadidegan/safe_geocoding_pipeline`, with controlled data
under `derived/controlled/`, execution reports under `reports/generated/`
and logs under `logs/slurm/`. These deployment paths are intentional bindings,
not portable configuration. Accepted later stages canonicalize the configured
`/work` anchor to its `/panfs/vdura1` mount spelling while rejecting disallowed
links below it.

Directories are `0700`; controlled files are `0600`. Use new immutable run
directories. Do not use `/scratch`, modify `/work/footprint/public` or modify
shared Conda base. Keep code and documentation in Git-backed storage; `/work`
is not backed up.

## Immutable runs and atomic publication

Publication is stage-specific. Earlier stages, including accepted Stage 8,
validate private temporary state and publish by their reviewed rename protocol.
Stage 9 uses permanent reservation, immutable validated artifacts, registration,
an atomic exclusive `_COMMITTED` seal and full reopen validation. Stage 10 reuses
those primitives through its own adapter after checking the accepted topology.

Directory or `_SUCCESS.json` existence alone cannot establish Stage 9/10 success.
Preserve failed/incomplete runs and uncertain commit outcomes. Never take over
an incomplete reservation, delete it for a retry or silently overwrite output.
Resume/adoption is permitted only by the exact stage contract. See
[publication policy](EXECUTION_POLICY.md#storage-and-publication-contract).

## Runtime and dependencies

Package development declares Python >=3.11, with DuckDB 1.5.5, ftfy 6.3.1 and
PyArrow 25.0.0 pinned in [pyproject.toml](../pyproject.toml). Accepted Stage 3–9
execution uses exact Python 3.14.3 / Unicode 16.0.0 plus each stage's frozen
dependencies. A newer Python does not satisfy an exact-runtime guard.

Stage 3–7 bootstrap scripts create isolated virtual environments from the
required interpreter. Run them on compute nodes under the reviewed launcher;
they are not a Conda setup recipe. Stage 7 also requires its pinned
libpostal/pypostal bundle. Stage 10's Q6 requires the locked ICU4C 77.1 /
Unicode 16.0.0 / CLDR 47 build; system ICU and a Mac build cannot substitute
for the verified Goethe runtime. See the
[runtime record](stages/STAGE10_IMPLEMENTATION.md#exact-goethe-runtime-established--2026-09-15).

## Local-safe validation

After [local setup](../README.md#local-setup), run the checks below. If a newly
added console command is missing from an existing environment, repeat
`python3 -m pip install -e '.[dev]'` to refresh the entry points.

```bash
python3 scripts/validate_stage_reports.py
python3 scripts/validate_stage10_implementation.py
python3 -m pytest -m "not requires_production_transfer_payload"
```

The marker excludes four tests that require the ignored historical production
transfer payload. Report them as deselected, not passed. The remaining suite
still includes exact-runtime and Stage 10 ICU checks. Follow their prerequisites;
do not weaken guards or acquire protected artifacts for documentation testing.

For static checks, use `python3 -m ruff check src tests scripts`,
`python3 -m ruff format --check src tests scripts` and `python3 -m mypy src`.
The latest [implementation validation record](stages/STAGE10_IMPLEMENTATION.md#validation-evidence-and-execution-boundary)
documents existing failures in broad `mypy src tests` and root-wide Ruff:
historical test typing and preserved Stage 9 review-archive issues. Those
historical findings are not evidence that current source checks fail.

## Current production boundary

Production Stages 0–1 are accepted for `production_population_1411_v1`;
production Stage 2 onward has not started. DEVELOPMENT launchers bind specific
accepted artifacts and may include review/equivalence work. They are not
general production wrappers. [Current progress](DEVELOPMENT_PROGRESS.md)
records the DEVELOPMENT checkpoint; this guide grants no execution authority.
