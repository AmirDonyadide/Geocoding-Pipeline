# Goethe-NHR execution assets

The `stage00_*` through `stage03_*` launchers are the active library-first
accepted-stage execution assets. `stage04_*` is the accepted DEVELOPMENT
launcher. `stage05_address_reconstruction.sbatch` is the accepted Stage 5
DEVELOPMENT launcher. `stage06_early_exact_deduplication.sbatch` is the accepted
Stage 6 DEVELOPMENT launcher: it uses a clean detached worktree at the exact
pushed SHA, binds accepted Stage 5 and the frozen fixed-500 subset, independently
reopens its publication, and emits controlled fixed-500 plus aggregate-only
review evidence. It does not authorize production, HOLDOUT, Stage 7, parsing, or
geocoding. `benchmark_sample_v1.sbatch` and `development_reporting.sbatch`
support the fixed benchmark/review infrastructure.

All protected/heavy jobs require an exact pushed Git SHA, a clean/exact
worktree, `SAFE_EXECUTION_SITE=goethe-nhr`, a non-empty `SLURM_JOB_ID`, owner-only
paths, and new immutable outputs. See `docs/EXECUTION.md` and
`docs/EXECUTION_POLICY.md`.
