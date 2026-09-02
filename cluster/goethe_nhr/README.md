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

`stage07_build_parser_bundle.sbatch` is a public-software-only provenance job
from the accepted Stage 7 DEVELOPMENT history. It compiles exact libpostal and
pypostal commits, freezes every runtime/model artifact by content, and opens no
protected input. Its existence does not authorize protected parsing; the later
controlled diagnostic must require the resulting exact bundle fingerprint.
`stage07_design_diagnostic.sbatch` and `stage07_bootstrap_env.sh` are historical
aggregate-only protected design-gate assets. They bind accepted Stage 6, the
frozen fixed-500 mapping, every case-variant group, every giant candidate, and
the exact parser bundle before parsing. They do not freeze the final contract,
materialize Stage 7, access HOLDOUT/production, map labels, or geocode.

`stage07_supervisor_diagnostic.sbatch` is the later owner-authorized revised
pre-contract gate. It reuses the same frozen parser bundle, binds the immutable
first not-ready evidence, and first replays that diagnostic's exact capped
isolated path to recover the protected candidate-level 19/4 reference that the
aggregate-only artifact did not publish. It then retests all 23 accepted giant
candidates through an uncapped, timeout-free supervisor path with exact-input
acknowledgment, fresh-process crash confirmation, and nullable `LargeList`
round-trip. The replay is comparison evidence, not proposed publication
policy. This is not a materializer or authoritative Stage 7 run.

`stage07_libpostal_parsing.sbatch` and
`stage07_parser_evidence_v2.sbatch` are the accepted DEVELOPMENT execution-
provenance assets for immutable v1 parsing and the zero-parser-call evidence-
only v2 projection. Their acceptance does not authorize reruns, production,
HOLDOUT, Senzing, or geocoding. The reviewed
`stage08_address_evidence.sbatch` produced DEVELOPMENT job `1763984` at exact
executable `bd89a032…`. Independent rereview later found a post-effect rename
failure hole; second repair executable `bdea7232…` has not been run. Job
`1763984` remains historical evidence only. No new Stage 8 job, production,
HOLDOUT, Stage 9, or geocoding is authorized without the required separate
owner authorization.

All protected/heavy jobs require an exact pushed Git SHA, a clean/exact
worktree, `SAFE_EXECUTION_SITE=goethe-nhr`, a non-empty `SLURM_JOB_ID`, owner-only
paths, and new immutable outputs. See `docs/EXECUTION.md` and
`docs/EXECUTION_POLICY.md`.
