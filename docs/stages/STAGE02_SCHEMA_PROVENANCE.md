# Stage 2 — Schema and provenance harmonization

## Purpose

Create a stable preprocessing schema from accepted Stage 1 data while adding
only passive, raw-value structural indicators for standard and native address
representations.

## Input

A SHA-pinned `stage02_input_binding_v1` that identifies either an accepted
Stage 1 bundle or the accepted Benchmark V1 DEVELOPMENT artifact. The benchmark
interface rejects HOLDOUT paths and non-DEVELOPMENT split values before reading
row data.

## Output

All 22 Stage 1 fields remain unchanged. Stage 2 adds exactly:

- `standard_has_nonempty_source_line`;
- `native_has_nonempty_source_line`;
- `standard_nonempty_source_line_count`; and
- `native_nonempty_source_line_count`.

It publishes a protected Parquet bundle, `stage02_manifest.json`, `_SUCCESS.json`,
schema/logical fingerprints, and sanitized aggregate evidence.

## Scientific rules

- Incoming values, types, order, provenance, and `stable_source_row_id_v1` are
  preserved exactly.
- Standard and native Orbis lines remain separate alternative representations.
- "Non-empty" is exact source `""` semantics; values are not trimmed first.
- The four structural fields are deterministic functions of the eight raw
  address-line strings.
- Stage 2 does not interpret line position, language, script, equality,
  authority, or address content.

## Non-goals

No trimming, Unicode normalization, lowercasing, cleaning, missing-marker
normalization, comparison, reconstruction, parsing, candidate construction,
deduplication, correction, eligibility decision, or geocoding occurs.

## Libraries

PyArrow and the SAFE schema/provenance layer. Protected materialization uses the
shared Goethe-NHR/SLURM execution guard and bounded batch processing.

## Validation

Validation proves exact input binding and schema, 35,000-to-35,000 row equality,
ordered stable-identity preservation, equality of all 22 incoming columns,
correct four-field derivation, no duplicate identities, Parquet readback,
manifest/fingerprint integrity, owner-only permissions, atomic publication,
HOLDOUT exclusion, and sanitized-report allowlisting.

## DEVELOPMENT evidence

Goethe job `1758833` processed all 35,000 DEVELOPMENT rows and retained all
incoming values/identities while adding the four structural fields. Full
quantitative evidence is in
[`reports/development/stage02_summary.md`](../../reports/development/stage02_summary.md).
The protected fixed-500 view uses the same deterministic identities documented
in [INSPECTING_RESULTS.md](../INSPECTING_RESULTS.md).

## Production status

**NOT STARTED.** Production Stage 1 is accepted for 1,411 files and 141,048,582
rows, but no production Stage 2 scan, materialization, or launcher execution has
begun.

## Privacy

The full DEVELOPMENT bundle and fixed-500 view are protected. Directories are
`0700`, files are `0600`, paths containing HOLDOUT fail closed, and Git contains
only allowlisted aggregate reports.

## Acceptance status

**IMPLEMENTED + ACCEPTED ON DEVELOPMENT.** Acceptance does not authorize
production Stage 2 or Stage 3.
