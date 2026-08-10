# Previous-work review

## Scope and authority

The following colleague notebooks were inspected statically as reference material:

- `Address preparation for Pelias.ipynb`: pandas-based source loading, address construction, field selection, cleaning, and CSV export.
- `Geocoding with Pelias.ipynb`: sequential SAFE/Pelias structured geocoding and CSV output.
- `01_preview.ipynb`: DuckDB comparison of corresponding source CSV and generated Parquet files.

Checkpoint copies exist under `.ipynb_checkpoints/`; they are notebook autosaves, not separate authoritative implementations. No standalone production package, tests, durable run manifest, SLURM workflow, or original CSV-to-Parquet converter was found in the reviewed scope.

Project requirements and current empirical data have higher authority than this previous implementation.

## Previous workflow

```text
hardcoded sample CSV
  -> pandas loads the entire file as strings
  -> standard address lines 1–4 are concatenated
  -> seven-column prepared CSV; native and other raw fields omitted
  -> pandas loads the complete prepared file
  -> one sequential structured Pelias request per row
  -> first returned feature selected
  -> in-memory result collection
  -> one CSV written after completion
```

`01_preview.ipynb` is a separate diagnostic comparison workflow. It did not create the existing Parquet files.

## Useful ideas

- Source loading used string dtype and disabled pandas' default missing-value conversion, reducing accidental postcode coercion.
- The preparation and comparison notebooks assumed comma delimiter, a header, and standard double-quote CSV behavior, matching the inspected sample contract.
- The geocoder used the preferred SAFE `/v1/search/structured` endpoint.
- It requested `size=1` and removed empty query parameters.
- It interpreted GeoJSON coordinates in correct `[longitude, latitude]` order.
- It retained `layer`, `match_type`, `confidence`, and `source` as diagnostic fields.
- The DuckDB notebook contains useful concepts for file pairing, schema/count comparison, duplicate-aware content comparison with `EXCEPT ALL`, and sampled difference reporting.
- Confidence was retained but was not the sole acceptance criterion.

These are concepts to evaluate or adapt; they do not make either notebook production-ready.

## Problems and risks

### Security and portability

Previous work contains an embedded credential and it must not be reused or copied into the new implementation.

The notebooks also contain hardcoded personal filesystem paths. Authentication and environment-specific paths were not supplied through protected, portable runtime configuration.

### Input preparation and provenance

- The preparation notebook loads an entire file into memory and uses row-wise pandas operations.
- It ignores all native-address fields.
- It assumes line 1 is primary and blindly joins populated standard lines 1–4.
- It does not distinguish company, street, building, unit, locality, or other component roles.
- It exports only `original_id`, two address strings, postcode, locality, region, and country.
- It loses raw columns, source filename, source row number, parser diagnostics, and transformation lineage.
- It collapses whitespace in derived values without diagnosing extreme/multiline fields.
- It does not deduplicate addresses, create a stable address key, or maintain an explicit row-to-unique-address mapping.

### Geocoding execution

- It geocodes row by row instead of geocoding unique addresses.
- A single process is sequential, but multiple processes or jobs could multiply request concurrency because no global controller exists.
- It has no retry classification, bounded retries, exponential backoff, jitter, rate-limit handling, durable checkpoints, resume logic, or completed-address registry.
- Results remain in memory and are written only after the complete loop, so interruption can lose progress.
- Request, response, timing, attempt, service-version, and lineage metadata are incomplete.

### Scientific result handling

- Any `features[0]` is marked as found, even when coarse or contradictory.
- The fallback check recognizes only a subset of unsuitable layers.
- The old `is_high_quality` rule automatically accepts address-level interpolated results, although that policy remains open.
- It does not compare returned and input country, region, locality, postcode, street, or house number.
- It does not store returned address components.
- A misspelled successful-result key causes the GID to be written under the wrong output field.
- It has no project-compliant `usable_for_analysis`, quality-tier, acceptance-reason, or exclusion-reason decision.

### Invalid Parquet and permissive validation

The existing `parquet_files` collection is invalid and must not be used as staging data. The preview notebook records a pattern in which a complete CSV record was placed in the first Parquet column while remaining columns were null. The most likely class of cause is incorrect delimiter/header/quote/escape configuration during the missing original conversion, but the exact incorrect setting is unknown.

The preview notebook's own CSV reader uses `strict_mode=false`, `null_padding=true`, and `ignore_errors=true`. Those settings can skip or disguise malformed and oversized records, so its comparisons cannot certify lossless ingestion. Its configured 20,000,000-byte line limit is also uncomfortably close to the largest observed logical field/record. Difference samples may display confidential full rows, and results are not persisted as a durable validation artifact.

## Classification

| Classification | Component | Location | Rationale |
|---|---|---|---|
| REUSE | Observed CSV dialect values | `01_preview.ipynb`, configuration cell | Comma, header, and double-quote assumptions match the inspected files. Reuse only after Phase 1 confirms the complete collection. |
| REUSE | GeoJSON coordinate ordering | `Geocoding with Pelias.ipynb`, response extraction | Correctly maps coordinate index 0 to longitude and index 1 to latitude. |
| ADAPT | String-safe loading and disabled default NA conversion | `Address preparation for Pelias.ipynb`, `load_source_data` | Preserve the concept, but add strict contracts, bounded-memory processing, anomaly reporting, lineage, and portable configuration. |
| ADAPT | Standard-line joining | `Address preparation for Pelias.ipynb`, `combine_address_lines` cell | Could become one controlled derived query variant; it cannot replace structured/raw components or native variants. |
| ADAPT | Structured-field mapping and deterministic whitespace cleanup | `Address preparation for Pelias.ipynb`, mapping/cleaning cells | Useful only on derived fields with raw values retained and ambiguous/extreme inputs flagged. |
| ADAPT | File discovery, quoting helpers, and duplicate-aware comparisons | `01_preview.ipynb`, helper and `compare_pair` cells | Retain validation concepts but use strict parsing, stable row identity, privacy-safe samples, and durable reports. |
| ADAPT | Structured endpoint, `size=1`, and empty-parameter filtering | `Geocoding with Pelias.ipynb`, request cell | Preserve the request concept within a secure, deduplicated, globally rate-limited, restartable client. |
| ADAPT | Storage of layer, match type, confidence, and source | `Geocoding with Pelias.ipynb`, response cell | Necessary but incomplete; add GID, components, agreements, query metadata, statuses, timing, and reasons. |
| REPLACE | Existing generated Parquet files | `parquet_files/` | Known malformed conversion; invalid as staging or research data. |
| REPLACE | Permissive validation parser | `01_preview.ipynb`, `csv_relation` | `ignore_errors` and `null_padding` can hide data loss and schema errors. |
| REPLACE | Seven-column preparation output | `Address preparation for Pelias.ipynb`, final DataFrame/export | Discards raw fields, native text, component structure, and row provenance. |
| REPLACE | Row-wise geocoding loop | `Geocoding with Pelias.ipynb`, sole code cell | No deduplication, secure configuration, retries, checkpoints, global concurrency, or durable progress. |
| REPLACE | First-feature-is-found and old `is_high_quality` logic | `Geocoding with Pelias.ipynb`, response classification | Scientifically invalid and prematurely resolves interpolation policy. |
| REPLACE | Incomplete fallback logic and GID output | `Geocoding with Pelias.ipynb`, response classification | Misses coarse layers and writes successful GID under the wrong key. |
| INVESTIGATE | Original CSV-to-Parquet converter/settings | Not present | Required to determine the exact historical failure mechanism. |
| INVESTIGATE | Provenance of the colleague sample CSV | Hardcoded input reference | Its relationship to the authoritative 206-file source collection is undocumented. |
| INVESTIGATE | Historical geocoding runs and outputs | Not established | No durable run manifest or confirmed result collection was found. |
| INVESTIGATE | Exact corruption distribution in old Parquet | `parquet_files/` | A complete audit was outside the approved review scope. |

## Consequences for future design

Future phases should preserve the useful parser/query concepts while replacing notebook-state execution with explicit contracts, immutable raw lineage, strict diagnostics, deterministic address keys, geocoding of unique addresses, secure runtime configuration, process-wide concurrency control, checkpoints, and scientifically explicit candidate selection. The colleague logic must never override locked requirements or current source evidence.
