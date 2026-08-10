# Decision register

This register distinguishes approved project rules from questions that require evidence or explicit scientific approval. Previous code and sample behavior cannot change a decision's status.

## Locked decisions

- The research objective requires physical building/plant/branch/store/facility point locations.
- `usable_for_analysis` is the main Boolean indicator of suitability for point-level research; diagnostic tiers remain separate.
- An address-layer exact match without a major geographic contradiction is expected to be usable.
- Street, venue, locality, localadmin, region, country, fallback, and otherwise coarse matches are not usable for the main point-level analysis.
- API response success or the existence of a first feature is not scientific geocoding success.
- `layer`, `match_type`, and geographic/component agreement are primary quality evidence. Confidence alone is insufficient.
- Raw source data is immutable. Raw fields must not be overwritten, silently cleaned, or silently discarded.
- Every source row must remain traceable to its file, source row, and original ID.
- Postal codes are strings. Unicode and native-script fields must be preserved.
- Address-line positions 1–4 do not have globally fixed meanings.
- Cleaning is conservative; uncertain geography, spelling, or address interpretation is flagged rather than silently inferred.
- Geographic addresses are deduplicated before geocoding, while a mapping to every source row is retained.
- Only unique eligible addresses are sent to SAFE.
- `/v1/search/structured` is the preferred primary endpoint and normal requests use `size=1`.
- SAFE authentication is supplied through protected runtime configuration; credentials are never committed or logged.
- Normal API concurrency is 2–4 requests total across the complete process, regardless of workers, shards, nodes, or jobs.
- Production retries are bounded and use classified transient failures, exponential backoff, jitter, checkpoints, and persistent error status.
- MacBook development/testing is primary. Goethe-NHR may be used for final/full processing where beneficial, with substantial work submitted through SLURM.
- `/scratch` is not used; `/work/footprint/public` and the shared Conda base are not modified.
- The existing `parquet_files` products are invalid and cannot serve as staging data.
- Work proceeds one reviewed phase at a time and stops after every phase.

## Open decisions

- Whether, and under what evidence/rules, an address-layer interpolated result is `usable_for_analysis`.
- Whether `id` is globally unique across all 206 files.
- Whether the sampled 15-column UTF-8/comma/header/double-quote contract holds across all 206 files.
- Whether all shards contain 100,000 logical records and what the complete logical row count is.
- Complete malformed-record, multiline-record, oversized-field, missing-marker, and schema variation across the source collection.
- Exact placeholder/null semantics, including treatment of `.`, `-`, `Na`, `Nan`, `Null`, and source-specific status values.
- International canonical-address rules and deterministic extraction of structured geography from free-form lines.
- Native-script versus transliterated primary/rescue query rules.
- Exact versioned address-key serialization and fields included in it.
- Stable source-row ID implementation and collision/integrity checks.
- Final input eligibility/completeness thresholds and controlled rescue-query ladder.
- Pilot 2 necessity, sampling design, and size.
- Manual ground-truth protocol and evidence needed for interpolation policy.
- Candidate comparison, component-agreement thresholds, and manual-review thresholds.
- Any external geographic boundary/reference dataset, including source, license, vintage, and coverage.
- Final staging technology/layout, execution location, resource sizing, and output partitioning.
- Production unique-address count, API-call count, timing, SAFE RDC coordination, and production-run approval.
- Historical-address and location-type interpretation rules where source evidence permits them.

## Superseded / corrected assumptions

- **Superseded:** The current source collection was previously estimated at approximately 500 GB.
- **Replacement:** The authoritative current source dataset is 206 CSV files totaling approximately 3.29 GB.
- There is currently no known additional source collection that this pipeline must process.
- Engineering choices must reflect the verified current scale. CSV-aware parsing, chunking/streaming where useful, and robust diagnostics remain necessary because parsed memory use can be much larger and extreme multiline fields exist. Distributed or big-data technology is not justified solely by the superseded estimate.
