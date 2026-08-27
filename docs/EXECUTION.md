# Execution guide

## Environment split

| Environment | Intended work |
|---|---|
| Mac/local | Code, documentation, Git, unit/synthetic tests, small diagnostics, lightweight validation, and small authorized DEVELOPMENT inspection |
| Goethe-NHR compute node | Protected/heavy DEVELOPMENT work and all heavy production execution through SLURM |
| Goethe-NHR login node | Git synchronization, light shell inspection, file transfer, submission, allocation, and scheduler/accounting commands only |

Production data is not run locally merely because it is accessible. When a
workload classification is uncertain, use Goethe-NHR.

## Required execution markers

Every protected/heavy entry point fails closed before opening production input
unless both markers are present:

```text
SAFE_EXECUTION_SITE=goethe-nhr
SLURM_JOB_ID=<non-empty scheduler job identity>
```

The shared guard is
`safe_geocoding_pipeline.execution_policy.require_goethe_nhr_slurm`. There is
no ordinary force-local bypass. A scientific authorization never waives this
site policy.

## Exact Git SHA binding

GitHub `origin` is the shared source for code and documentation. A protected
job runs code from an exact pushed commit, not a moving branch:

1. fetch remote state and inspect the intended branch;
2. require a clean worktree;
3. verify the reviewed commit is present on `origin`;
4. create or select a detached/exact execution worktree;
5. record the full commit in the submission environment;
6. have the job compare the declared SHA with `git rev-parse HEAD`; and
7. never pull or select new code inside an SBATCH job.

If a cluster checkout is dirty, diverged, or retained as audit evidence, stop.
Do not reset, clean, overwrite, or repurpose it for convenience.

## Controlled storage

The institutional deployment contract currently uses:

```text
/work/footprint/donyadidegan/safe_geocoding_pipeline
```

Within that controlled root, high-volume data, generated reports, and logs use
environment-specific subdirectories such as:

```text
derived/controlled/
reports/generated/
logs/slurm/
```

These institutional paths legitimately remain in reviewed cluster launchers.
Portable documentation and local configuration use placeholders or environment
variables instead of personal absolute paths.

Controlled directories are mode `0700`; controlled files are mode `0600`.
`/scratch` is not used, `/work/footprint/public` is not modified, and the shared
Conda base environment is not modified. Important code and documentation stay
in Git-backed storage because `/work` is not backed up.

## Immutable runs and atomic publication

Each run receives a new, non-colliding output directory and binds input
artifacts, contracts, fingerprints, Git SHA, runtime, and SLURM job identity.
Writers build in a private in-progress directory, validate content and
permissions, fsync where required, and atomically rename the complete bundle
into its final location. A pre-existing output or temporary path is an error.

Terminal success markers are written only after validation. A partial or
failed run is preserved with its evidence; it is not silently resumed,
overwritten, or reported as accepted. A new attempt uses a new run ID unless an
approved restart contract explicitly says otherwise.

## Runtime and dependencies

Local package development supports Python 3.11 or newer with the pinned
dependencies in `pyproject.toml`. Reproducing accepted Stage 3 requires Python
3.14.3, Unicode 16.0.0, ftfy 6.3.1, and PyArrow 25.0.0. The Stage 3 bootstrap
fails rather than substituting another runtime.

Production transformations use PyArrow, DuckDB, or other approved bounded
engines. Pandas is restricted to small DEVELOPMENT inspection/notebooks.

## Local-safe validation

Install and run the local-safe suite without opening the controlled
production-transfer payload:

```bash
python3 -m pip install -e '.[dev]'
python3 -m pytest -m "not requires_production_transfer_payload"
```

The excluded marker covers four tests that exercise the real historical
controlled-transfer payload. Their deselection must be reported; it is not a
claim that those integration tests passed.

The full environment command is `python3 -m pytest`, but it requires the exact
ignored protected transfer prerequisites and fails if they are absent. Do not
obtain or open protected artifacts merely to run documentation validation.

## Current production boundary

Production Stage 0 and Stage 1 are accepted for
`production_population_1411_v1`. Production Stage 2 and Stage 3 have not
started. No command in this guide authorizes production Stage 2, Stage 3,
geocoding, or Stage 4.

The permanent detailed rules are in [EXECUTION_POLICY.md](EXECUTION_POLICY.md).
