# Stage 0 — Source inventory

## Purpose

Freeze an exact source population and establish its parser, schema, file/hash,
logical-record, anomaly, and identity evidence without transforming source
rows. Stage 0 adopts the existing Phase 1 inventory as the authoritative
scanner instead of duplicating it.

## Input

- an explicit owner-only `stage00_population_scope_v1` artifact containing the
  exact sorted direct-child CSV paths;
- the expected scope SHA-256 and population identity;
- immutable source CSV files; and
- completed Phase 1 inventory reports produced under the accepted parser
  contract.

Directory contents never expand the authorized population implicitly.

## Output

- exact source-population and scientific-inventory fingerprints;
- an adoption record binding population scope, Phase 1 artifacts, source
  hashes, schemas, and counts;
- explicit file/parser/schema/anomaly results; and
- owner-only terminal validation/publication evidence.

Stage 0 writes no row-level transformed dataset.

## Scientific rules

- Python's strict CSV-aware logical-record parser is authoritative.
- UTF-8, delimiter, header, quoting, schema, and record counts are verified, not
  assumed from a sample.
- Multiline and oversized fields are diagnosed; they are not silently cleaned,
  truncated, skipped, or null-padded.
- The source-population fingerprint and scientific-inventory fingerprint use
  separate domain-separated contracts.
- Operational timestamps, mtimes, durations, host/job identity, Git/runtime
  versions, and permissions do not alter scientific identity.
- Raw files are read-only and immutable.

## Non-goals

Stage 0 does not ingest to Parquet, create stable row IDs, clean or normalize
text, infer missingness, reconstruct/parse addresses, deduplicate, or geocode.

## Libraries

Existing Phase 1 inventory code, Python `csv`, and Python `hashlib`. DuckDB may
be used only as an independent check, not as the authoritative CSV parser.

## Validation

Acceptance requires the exact authorized path set, source hashes and sizes,
logical row counts, parser/schema result for every file, no unnoticed source
mutation, owner-only permissions, sanitized portable reports, immutable atomic
publication, and independent critical review.

## DEVELOPMENT evidence

The accepted Benchmark V1 development population is permanently tied to the
accepted 1,405-file Stage 0 snapshot containing 140,448,582 logical rows. That
identity remains frozen and is not retroactively changed by six later files.
Historical source-foundation reports are retained under
[`docs/history/source_foundation/`](../history/source_foundation/README.md).

## Production status

**ACCEPTED — `NEW_STAGE0_1411_ACCEPTED`.** The current production population is
`production_population_1411_v1`: 1,411 CSV files and 141,048,582 rows.

This production acceptance does not rebuild Benchmark V1 and does not authorize
production Stage 2.

## Privacy

Source scopes, raw files, detailed manifests, paths, and row-level diagnostics
remain controlled. Directories are `0700`, files are `0600`, and Git receives
only code, contracts, hashes, sanitized reports, metrics, and documentation.

## Acceptance status

**IMPLEMENTED + ACCEPTED.** Stage 1 is separately accepted. Stage 0 acceptance
does not authorize rerunning the population or starting a later stage.
