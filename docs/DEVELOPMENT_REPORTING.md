# DEVELOPMENT reporting and fixed human review

## Status and contracts

The passive reporting layer uses `development_reporting_contract_v1`. Its
fixed protected review population uses
`development_review_subset_contract_v1`. Reporting reads accepted DEVELOPMENT
products but is not a scientific transformation: it cannot change stage
outputs, acceptance gates, source identities, or any stage fingerprint.

The fixed review subset contains exactly 500 rows selected only from the
accepted 35,000-row `BENCHMARK_SAMPLE_V1` DEVELOPMENT artifact. Selection uses
accepted immutable provenance and benchmark structural strata plus a
domain-separated SHA-256 rank. Address text does not enter the rank. HOLDOUT
paths and non-DEVELOPMENT split values fail closed.

## Why one fixed subset exists

The same 500 source rows are followed through Stage 2 and every later accepted
DEVELOPMENT stage. This supports qualitative inspection, debugging, and
colleague demonstrations without allowing convenient examples to drift from
stage to stage. Balanced deterministic quotas cover country, geocoding-history,
batch-priority, standard/native availability and equality, line counts,
missingness, script, and challenge-reason strata where possible. Remaining
capacity maximizes source-file coverage and then uses a deterministic global
fill. Impossible quotas are reported, never manually repaired.

The subset is not a replacement for full DEVELOPMENT evaluation. Quantitative
stage evidence always uses all 35,000 DEVELOPMENT rows. The 500 rows are a
protected qualitative review surface only.

## Identity and artifact model

`development_review_subset_sha256_v1` binds the reporting/subset, selection,
and allocation-policy versions; the accepted benchmark fingerprint; exact
35,000/500 counts; all quota values; and the sorted selected
`stable_source_row_id_v1` values. Timestamps, paths, filenames, Git/SLURM
identity, and physical Parquet properties are excluded.

The selected rows are frozen in one immutable protected bundle. Each stage
produces a separate immutable review artifact referencing that subset. Future
stages add their own derived review columns in a new stage artifact; they do
not rewrite the fixed selection or earlier stage views. All artifacts join by
the unchanged stable identity and a deterministic local review identity.

For Stage 2, the protected view contains source provenance, the standard and
native raw lines, raw postcode/city/region/country, prior-geocoding metadata,
and the four accepted Stage 2 structural fields. It does not invent or
transform a value. Future stage-specific schemas are intentionally not defined
by this reporting contract.

## Portable summaries and privacy

Git-safe summaries follow `development_sanitized_summary_v1`. Their exact
top-level schema, metric groups, metric categories, checks, and interpretation
text are allowlisted in code. Values are aggregate non-negative integers or
reviewed identities/statuses. Raw address fields, selected identities, source
filenames, and arbitrary free text cannot enter the renderer.

Protected directories are `0700`; protected files are `0600`; publication is
atomic and page-checksum read-back is mandatory. The Mac copy lives below the
ignored `data/controlled/development_review_subset_v1/` tree. No protected
review artifact is committed. Terminal output contains only aggregate counts,
fingerprints, and artifact hashes.

HOLDOUT remains physically separate and sealed. The reporting CLI and launcher
reject any path component named `holdout`, and selection validates every input
split as `DEVELOPMENT`. **Do not use HOLDOUT for reporting, review, debugging,
or tuning.**

## Future-stage integration

For each accepted DEVELOPMENT stage:

1. validate the complete accepted 35,000-row stage bundle;
2. bind the fixed subset fingerprint and exact stable identities;
3. create a new immutable protected per-stage view without rewriting earlier
   raw or derived columns;
4. generate a Git-safe aggregate summary through the allowlisted renderer;
5. compare the same 500 rows qualitatively while evaluating all 35,000 rows
   quantitatively.

This framework is evaluation infrastructure. It does not authorize or begin
Stage 3.
