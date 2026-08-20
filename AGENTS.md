# Mandatory repository instructions

## Project workflow

- Work one phase at a time. Read `docs/PROJECT.md`, `docs/DECISIONS.md`, `docs/PIPELINE.md`, the relevant phase report, and any other relevant documentation before acting.
- Design and obtain review of each phase before implementing it. Stop after each phase and never proceed automatically to the next phase.
- Treat `docs/PROJECT_BRIEF.md` as the long-form reference, `docs/DECISIONS.md` as the decision register, and empirical reports as evidence—not permission to start work.
- Do not implement Phase 1 or any later phase without explicit approval for that phase.

## Source-control workflow

- GitHub `origin` is the shared source of truth for code, tests, configuration, and documentation. Develop and validate on the Mac, then commit and push each coherent completed change to an appropriate branch.
- Before integrating or pushing, fetch remote state, inspect the branch/worktree, and preserve colleagues' changes. Use fast-forward-only pulls when appropriate; never force-push or rewrite shared history without explicit approval.
- Do not copy source files or Git metadata to Goethe-NHR with rsync. The cluster obtains code from GitHub. The rsync helper is limited to explicitly approved ignored data artifacts.
- Synchronize the cluster checkout before submission, never from inside a SLURM job. Each job runs an exact reviewed commit, logs that commit, and fails closed if its declared commit differs from the executable worktree.
- Before committing, exclude generated outputs, large or raw data, logs, caches, credentials, environment files, and agent-local state. Use a feature branch for experimental or unfinished changes rather than destabilizing shared `main`.

## Data

- The authoritative current source scope is 206 CSV files totaling approximately 3.29 GB.
- Raw source data is immutable. Never edit, overwrite, rename, move, or silently alter it. Derived values belong in separate fields and datasets.
- Preserve row traceability, including original ID, source file, source row number, and eventually a stable source-row identifier.
- Treat postal codes as strings. Preserve Unicode and native-script address fields.
- Do not assume fixed meanings for address lines 1–4 or global uniqueness of `id`; Phase 1 must test these properties.
- Use CSV-aware parsing. A physical line is not necessarily a logical record.
- Diagnose oversized and quoted-multiline fields; never silently clean, truncate, skip, or null-pad them.
- Never silently drop malformed records. Fail loudly or write explicit diagnostics, according to the approved phase design.

## Current observed CSV evidence

- Across ten inspected files, the observed contract was UTF-8-compatible text, comma delimiter, a header, 15 columns, double-quote CSV behavior, no observed backslash escaping, and 100,000 logical records per inspected file.
- This is strong sample evidence, not dataset-wide proof. Phase 1 must verify all 206 files.
- Multi-million-character fields and quoted multiline records exist.
- Structured geographic completeness, missing-marker vocabulary, native/non-native relationships, and postcode representation vary strongly across samples.

## SAFE geocoding

- Prefer `/v1/search/structured` for the primary query and normally request `size=1`.
- Supply the API key only through protected runtime configuration. Never commit, print, or log credentials or authorization headers.
- Normal concurrency is 2–4 requests total across the entire process—not per worker, shard, node, or SLURM job.
- A returned API feature is not automatically a scientifically successful geocode.
- Use `layer`, `match_type`, and input/output geographic agreement as primary quality evidence. Confidence alone is insufficient.
- An exact address match without a major contradiction is expected to be usable. Acceptance of interpolated address matches remains open until after the pilot.
- Street, venue, locality, localadmin, region, country, fallback, and other coarse results are not usable for point-level research.

## Previous work

- Colleague notebooks are reference material, not authoritative implementation.
- Existing `parquet_files` outputs are invalid and must not be used as staging data.
- Do not reuse the old `is_high_quality` rule, first-feature-is-success behavior, permissive `ignore_errors`/`null_padding` validation, hardcoded credentials, or hardcoded personal paths.
- Previous work contains an embedded credential and it must not be reused or copied into the new implementation.

## Infrastructure

- **HEAVY PRODUCTION PROCESSING = GOETHE-NHR ONLY.** Read and follow `docs/EXECUTION_POLICY.md`. If uncertain whether a production task is heavy, default to Goethe-NHR.
- The MacBook is for code, documentation, Git, unit/synthetic tests, small diagnostics, lightweight validation, and small controlled manual-review workflows—not full-production scans or multi-GB processing.
- Heavy includes any complete production Phase 2 scan, at least 1,000,000 production rows, a substantial fraction of 20.6M rows, at least 2 GiB working state, an expected local runtime of at least 10 minutes, or full-production joins, grouping, deduplication, address keys, Phase 3 transformation, geocoding, selection, validation, merge-back, or reconciliation.
- Heavy work must run through SLURM on Goethe-NHR, never a login node. Production-heavy commands must invoke the shared fail-closed execution guard; do not add a local bypass.
- Use the configured `ssh goethe` alias for normal cluster access. Login nodes are limited to SSH, Git/light shell work, file transfer, `sbatch`/`salloc`/`srun`, and job inspection. Run Python, tests, profiling, and data processing only inside an allocated compute-node session or batch job.
- Never use `/scratch`, modify `/work/footprint/public`, or modify the shared Conda base environment.
- Keep important code and documentation in Git-backed storage; `/work` is not backed up.
- Do not introduce distributed or big-data technology merely because of the superseded scale estimate.

## Phase 3 DEVELOPMENT governance

- The selected 8,000-row DEVELOPMENT set is fixed. Do not rerun the full 20.6M-row selector or reconstruction merely to iterate on a parser or diagnostic that can reuse the preserved DEVELOPMENT payload.
- The 4,000-row LOCKED_EVALUATION set remains sealed. Do not materialize, inspect, transform, profile, review, or otherwise access LOCKED payload or identities without explicit authorization for that evaluation step.
- Protected real addresses remain on controlled Goethe `/work` storage. Never copy them to the Mac, Git, documentation, portable reports, prompts, or an external AI/service. Use fictional synthetic values in committed tests and examples.
- Preserve failed runs, reconstructed state, submitted-job evidence, and detached integration worktrees as audit boundaries. Do not advance, mutate, delete, or reuse them for convenience; create a new worktree/output identity for a new reviewed iteration.

## Prohibited without explicit approval

- Do not run the full 206-file dataset, start production geocoding, send large API workloads, raise concurrency, launch multiple geocoding jobs, transfer the full data collection, or download external spatial datasets.
- Never run an authorized heavy production task on the MacBook; scientific authorization does not waive the Goethe-NHR/SLURM requirement.
- Do not choose an open scientific policy, infer uncertain geography, expose confidential data, commit real data, or move to the next project phase.
