# Goethe-NHR execution assets

Stage-specific launchers bind exact Git, input, runtime and output identities.
They are execution provenance, not permission to rerun or general-purpose
production scripts. Inspect each launcher's required variables and fixed paths
before a separately authorized submission.

| Assets | Purpose and scope |
|---|---|
| [stage00_inventory.sbatch](stage00_inventory.sbatch), [stage01_adopt.sbatch](stage01_adopt.sbatch) | Inventory/adoption of frozen source-foundation artifacts; the Stage 1 launcher binds the historical 206-file run, not a new CSV conversion or the later 1,411-file population |
| [benchmark_sample_v1.sbatch](benchmark_sample_v1.sbatch) | Fixed 1,405-file Benchmark V1 selection; never rebuild for the later six files |
| [development_reporting.sbatch](development_reporting.sbatch) | Fixed DEVELOPMENT review subset and sanitized reporting |
| [stage02_harmonization.sbatch](stage02_harmonization.sbatch) through [stage06_early_exact_deduplication.sbatch](stage06_early_exact_deduplication.sbatch) | Accepted DEVELOPMENT harmonization, cleaning, lowercase, reconstruction and exact deduplication; Stage 3–6 bootstrap scripts pin isolated environments |
| `stage05_design_diagnostic.sbatch`, `stage06_design_diagnostic.sbatch` | Historical reconstruction/deduplication design diagnostics |
| [stage07_build_parser_bundle.sbatch](stage07_build_parser_bundle.sbatch) | Public-only pinned libpostal/pypostal build and provenance; no protected input |
| `stage07_*diagnostic.sbatch`, `stage07_context_provenance.sbatch`, `stage07_country_eligibility.sbatch`, `stage07_quality_root_cause.sbatch`, `stage07_v2_readiness_design_audit.sbatch`, `stage07_v2_validation_selection.sbatch` | Historical Stage 7 design, resource, applicability, quality and failed-readiness experiments |
| [stage07_libpostal_parsing.sbatch](stage07_libpostal_parsing.sbatch), [stage07_parser_evidence_v2.sbatch](stage07_parser_evidence_v2.sbatch) | Immutable v1 parsing and accepted v2 evidence-only projection; v2 makes zero parser calls |
| [stage08_address_evidence.sbatch](stage08_address_evidence.sbatch) | Accepted lossless evidence projection; publication repair history remains in the [report](../../reports/development/stage08.md) |
| `stage09_filesystem_diagnostic.sbatch`, `stage09_exclusive_create_diagnostic.sbatch` | Preserved synthetic filesystem capability experiments |
| [stage09_offline_reference_evidence.sbatch](stage09_offline_reference_evidence.sbatch) | Accepted offline reference evidence using the permanent reservation/commit-seal protocol |
| [stage10_build_transliteration_runtime.sbatch](stage10_build_transliteration_runtime.sbatch) | Public-only locked ICU runtime preparation; completed job `1772341` |
| [stage10_development.sbatch](stage10_development.sbatch) | One authorized execution, job `1772639`, timed out; partial work preserved; no rerun authorized; [checkpoint](../../docs/stages/STAGE10_IMPLEMENTATION.md#development-timeout-reconciliation--2026-09-19) |

The historical Stage 7 resource-cap crashes, DeepParse closure and failed
semantic-readiness rule remain distinct from accepted parser evidence. See the
[Stage 7 record](../../docs/stages/STAGE07_LIBPOSTAL_PARSING.md); do not revive an
old diagnostic as a current scientific gate.

All protected/heavy jobs require a clean exact pushed checkout,
`SAFE_EXECUTION_SITE=goethe-nhr`, a scheduler-provided `SLURM_JOB_ID`, private
paths and immutable output. Python/bootstrap/data work runs on compute nodes.
Jobs never pull code; pending jobs are not duplicated. Follow the
[execution guide](../../docs/EXECUTION.md) and
[execution policy](../../docs/EXECUTION_POLICY.md).
