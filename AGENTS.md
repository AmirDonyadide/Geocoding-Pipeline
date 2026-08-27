# Mandatory repository instructions

## Project workflow

- Work one scientific stage at a time. Read `docs/PROJECT_OVERVIEW.md`,
  `docs/DECISIONS.md`, `docs/PIPELINE.md`, the relevant stage record, and other
  relevant documentation before acting.
- Design and obtain explicit review/approval before implementing a stage. Stop
  after every stage; evidence is not permission to continue.
- Stages 0–3 are accepted on DEVELOPMENT. Stage 4 and production Stage 2 are
  not started and require separate explicit authorization.
- Preserve accepted/rejected scientific history. Do not rebase, squash, or
  rewrite the Stage 3 v1/v2 ancestry.
- Maintain one active scientific stage workflow at a time. Submit a reviewed
  long-running job once, wait, and reuse its immutable artifact; do not launch a
  duplicate merely because it is pending.

## Data and scientific invariants

- The production population is `production_population_1411_v1`: 1,411 files
  and 141,048,582 rows. Production Stage 0 and Stage 1 are accepted.
- Benchmark V1 remains permanently tied to its 1,405-file population: 35,000
  DEVELOPMENT and 15,000 sealed HOLDOUT rows. Do not rebuild it for the later
  six files.
- Raw source data is immutable. Never edit, overwrite, rename, move, silently
  clean, truncate, skip, or null-pad it.
- Preserve original ID, source file, logical record number,
  `stable_source_row_id_v1`, and all source/derived lineage.
- Postal codes are strings. Preserve Unicode and native-script fields.
- Do not assume fixed meanings for address lines 1–4 or global uniqueness of
  provider `id`.
- Use CSV-aware parsing. A physical line is not necessarily a logical record.
- Source rows are never deduplicated away. Candidate/query deduplication must
  retain complete map-back.
- Standard and native representations remain separate candidates. Never
  overwrite native text with a standard/English translation or blindly
  concatenate all source address lines.
- Absence from an open reference is not invalidity. `MISMATCH` requires strong
  positive contradictory evidence.

## Privacy

- Protected addresses and row-level artifacts remain on controlled local or
  Goethe infrastructure. Never send them to public APIs, external geocoders,
  web services, LLMs, prompts, or Git.
- HOLDOUT must not be opened, copied, inspected, profiled, transformed, or used
  for debugging/tuning without final-evaluation authorization.
- Git contains only code, contracts, synthetic fixtures, execution assets,
  documentation, hashes, sanitized aggregate reports, and non-sensitive
  metrics.
- Credentials are runtime-only and never committed, printed, or logged.

## Execution

- Heavy/protected production work is Goethe-NHR SLURM only. When uncertain,
  default to Goethe-NHR.
- Production/heavy commands must invoke the shared fail-closed guard before
  input access and require `SAFE_EXECUTION_SITE=goethe-nhr` plus a non-empty
  `SLURM_JOB_ID`. Do not add a local bypass.
- Controlled directories are `0700`; controlled files are `0600`. Publication
  is atomic into new immutable run directories; failed attempts are preserved.
- The Mac is for code, documentation, Git, unit/synthetic tests, small
  diagnostics, lightweight validation, and small authorized DEVELOPMENT review.
- Goethe login nodes are orchestration-only. Run Python/data processing inside
  a scheduled job or compute-node allocation.
- Never use `/scratch`, modify `/work/footprint/public`, or modify the shared
  Conda base environment.
- Code reaches Goethe through Git at an exact pushed SHA. Do not rsync source
  code/Git metadata or pull dynamically inside a job.

## SAFE Pelias

- Prefer `/v1/search/structured`, normally with `size=1`.
- Normal concurrency is 2–4 requests total across the complete process, not per
  worker, shard, node, or job.
- A returned feature is not automatically a scientifically successful geocode.
  Use layer, match type, component/geographic agreement, and contradictions.
- Street, venue, locality, localadmin, region, country, fallback, and other
  coarse results are not usable for point-level research.
- Do not geocode until Stage 19 is accepted and an exact workload is separately
  authorized.

## Source-control hygiene

- `main` is the canonical branch. Use professional project/scientific branch
  names when a branch is required.
- Before integrating or pushing, fetch, inspect status/divergence, preserve
  colleagues' work, and use non-rewriting/fast-forward-safe operations.
- Exclude generated data, outputs, logs, caches, credentials, environments, and
  local tooling state before every commit.
