# Goethe-NHR execution assets

The `stage00_*` through `stage03_*` launchers are the active library-first
accepted-stage execution assets. `benchmark_sample_v1.sbatch` and
`development_reporting.sbatch` support the fixed benchmark/review
infrastructure.

Files named `phase03_*` belong to the preserved historical custom-preprocessing
pilot/parser program. They remain for reproducibility and are not production
Stage 3 safe-cleaning launchers. Do not submit them as part of the active
pipeline without a separate historical reproduction authorization.

All protected/heavy jobs require an exact pushed Git SHA, a clean/exact
worktree, `SAFE_EXECUTION_SITE=goethe-nhr`, a non-empty `SLURM_JOB_ID`, owner-only
paths, and new immutable outputs. See `docs/EXECUTION.md` and
`docs/EXECUTION_POLICY.md`.
