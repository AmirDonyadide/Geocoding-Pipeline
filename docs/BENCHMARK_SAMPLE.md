# Benchmark Sample V1

## Status

**BENCHMARK_SAMPLE_V1_ACCEPTED.** The accepted product uses
`benchmark_sample_contract_v1` and is permanently bound to the frozen 1,405-file
Stage 0 population. It contains exactly 50,000 source rows: 35,000 DEVELOPMENT
and 15,000 HOLDOUT, with zero overlap and zero duplicate selected identities.
All 1,405 source files are represented. The benchmark fingerprint is
`014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf`.

## Purpose and boundary

`BENCHMARK_SAMPLE_V1` is the fixed protected real-data benchmark for comparing
library-first preprocessing Stages 3–19. It is a selection product, not Stage 2
and not an address transformation. The selected rows retain all 15 decoded
source strings byte-for-byte in their Python/Arrow UTF-8 representation. The
workflow performs no cleaning, Unicode normalization, whitespace repair,
reconstruction, deduplication, parsing, correction, or geocoding.

The authorized V1 sampling population is the frozen 1,405-file DEVELOPMENT
delivery. The six files absent when V1 was frozen are outside this benchmark
forever; their later arrival does not change V1. A different population would
require a new benchmark contract/version. The population is supplied by an
owner-only, hash-pinned `stage00_population_scope_v1` artifact. Current
directory contents cannot silently add a source.

## Fixed sample and split

The benchmark contains exactly 50,000 source rows before any address
deduplication:

- `DEVELOPMENT`: 35,000 rows, available for inspection and pipeline design;
- `HOLDOUT`: 15,000 rows, unavailable for tuning and reserved for a separately
  authorized final evaluation.

Selection and split assignment use independent domain-separated SHA-256 ranks
of `stable_source_row_id_v1`. Neither rank reads address text. The split rank
therefore cannot change when feature code or address-processing code changes.
DEVELOPMENT and HOLDOUT are disjoint and exact-size gates.

## Deterministic coverage policy

The selector makes three bounded-memory strict-CSV passes. The first profiles
only raw structural features, the second retains deterministic quota and
global-fill candidates, and the third writes the sealed selected identities.
The source population is hashed before processing and rehashed before atomic
publication.

Selection combines deterministic minimum quotas with a population-wide fill:

- at least 8 candidates per source file where available;
- minimum coverage for every observed geocoding-history, batch-priority,
  standard/native presence and equality, line-count, script, missingness, and
  challenge-reason category;
- 25 candidates per country where available, followed by a fixed 7,500-row
  country budget weighted by integer square-root volume and increased
  non-Latin representation;
- a deterministic provenance-hash fill to exactly 50,000 rows.

Overlapping quotas reuse rows. Impossible quotas never trigger cherry-picking:
they degrade deterministically and are reported as explicit aggregate
shortfalls. The equality class called
`CASE_ONLY_OR_TRIVIALLY_EQUAL` is deliberately narrow in V1: it means exact
four-line tuple equality after Python `casefold()` only. No whitespace or
Unicode normalization participates.

## Structural features and challenge flag

Sampling features use raw empty-string semantics and the pinned Unicode 16.0
Script property reference already vendored in the repository. They include:

- `location_information`, `batch_priority`, and raw country strata;
- standard/native `STANDARD_ONLY`, `NATIVE_ONLY`, `BOTH_PRESENT`, or
  `NEITHER_PRESENT` availability;
- exact, casefold-only, materially different, or not-both equality;
- 0–4 populated line counts for each representation;
- raw postcode/city/region/country presence and combined missingness;
- `LATIN_ONLY`, `NON_LATIN_PRESENT`, `MIXED_SCRIPT`, `EMPTY`, or
  `COMMON_OR_UNKNOWN_ONLY` script categories.

`benchmark_challenge_flag` is true when any fixed structural reason is present:
native-only representation, materially different standard/native lines,
missing geographic fields, multiple address lines, non-Latin or mixed script,
an address field of at least 1,024 characters, previous geocoding failure, or
no geocoding information. It is not a manual quality label.

## Scientific identity

`benchmark_sample_contract_v1` uses the domain
`SAFE_BENCHMARK_SAMPLE_V1`. Its canonical binary SHA-256 fingerprint binds:

- benchmark, feature, selection, and allocation-policy versions;
- the exact population-scope version, ID, and artifact hash;
- the Stage 0 parser-contract fingerprint and Unicode Script reference;
- exact DEVELOPMENT/HOLDOUT targets and quota policy;
- canonical source path, byte size, raw SHA-256, and logical-row projection;
- sorted selected immutable identities in each split.

Timestamps, Git SHA, host, SLURM job, runtime versions, permissions, and output
filenames are operational provenance and do not affect scientific identity.

## Protected artifacts and use policy

Real outputs live only in controlled project storage. Directories are `0700`
and files are `0600`. The bundle contains:

- `development/development_view.parquet`, the stable row-by-row join surface
  for future DEVELOPMENT outputs;
- `holdout/holdout.parquet`, physically separate and not for human inspection;
- a protected manifest binding selected identities and artifact hashes;
- sanitized JSON/Markdown summaries containing DEVELOPMENT aggregates only;
- terminal success and HOLDOUT-policy markers.

The manifest and Parquet data are protected, not portable. Portable reporting
must never include raw values, selected IDs, source filenames, or HOLDOUT
feature distributions. Future work normally reads DEVELOPMENT only.

The Mac development copy, when explicitly needed, lives only at the ignored
owner-only path
`data/controlled/benchmark_sample_v1/development/development_view.parquet`.
HOLDOUT is not copied to the Mac.

**DO NOT USE HOLDOUT FOR PIPELINE TUNING.** Opening or running evaluation on
HOLDOUT requires an explicit final-evaluation authorization.

Address-changing stages use DEVELOPMENT for metrics, protected example review,
and tuning. After every pipeline stage is frozen, HOLDOUT is opened once under
an explicitly authorized unbiased final-evaluation protocol. A later 1,411-file
production snapshot does not authorize rebuilding or modifying Benchmark V1.

## Execution and acceptance

The full 1,405-file scan is production-heavy. It runs only through
`cluster/goethe_nhr/benchmark_sample_v1.sbatch` with the shared fail-closed
Goethe/SLURM guard. If needed, the exact scope can be transferred through
`scripts/transfer_benchmark_sources_to_goethe_nhr.sh`; the transfer performs a
checksum reconciliation and no external processing.

Acceptance requires exact authorized topology, stable source bytes, strict
accepted CSV interpretation, no duplicate source SHA, exact 35,000/15,000
counts, disjoint and unique selected identities, exact protected Parquet
schema, page-checksum readback, owner-only permissions, sanitized summaries,
an integrity-bound manifest, and atomic terminal publication. A partial or
colliding output fails closed.
