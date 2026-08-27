# Goethe-NHR execution assets

The `stage00_*` through `stage03_*` launchers are the active library-first
accepted-stage execution assets. `stage04_*` is the accepted DEVELOPMENT
launcher. `stage05_address_reconstruction.sbatch` is the Stage 5 DEVELOPMENT
candidate launcher and does not authorize production. `benchmark_sample_v1.sbatch`
and `development_reporting.sbatch` support the fixed benchmark/review infrastructure.

All protected/heavy jobs require an exact pushed Git SHA, a clean/exact
worktree, `SAFE_EXECUTION_SITE=goethe-nhr`, a non-empty `SLURM_JOB_ID`, owner-only
paths, and new immutable outputs. See `docs/EXECUTION.md` and
`docs/EXECUTION_POLICY.md`.
