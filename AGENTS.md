# Mandatory repository instructions

## Project workflow

- Work one phase at a time. Read `docs/PROJECT.md`, `docs/DECISIONS.md`, `docs/PIPELINE.md`, the relevant phase report, and any other relevant documentation before acting.
- Design and obtain review of each phase before implementing it. Stop after each phase and never proceed automatically to the next phase.
- Treat `docs/PROJECT_BRIEF.md` as the long-form reference, `docs/DECISIONS.md` as the decision register, and empirical reports as evidence—not permission to start work.
- Do not implement Phase 1 or any later phase without explicit approval for that phase.

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

- The MacBook is the primary development and testing environment. Use small, synthetic, or explicitly approved representative inputs.
- Goethe-NHR may be used for final/full processing where beneficial. Run substantial work through SLURM, never on login nodes.
- Never use `/scratch`, modify `/work/footprint/public`, or modify the shared Conda base environment.
- Keep important code and documentation in Git-backed storage; `/work` is not backed up.
- Do not introduce distributed or big-data technology merely because of the superseded scale estimate.

## Prohibited without explicit approval

- Do not run the full 206-file dataset, start production geocoding, send large API workloads, raise concurrency, launch multiple geocoding jobs, transfer the full data collection, or download external spatial datasets.
- Do not choose an open scientific policy, infer uncertain geography, expose confidential data, commit real data, or move to the next project phase.
