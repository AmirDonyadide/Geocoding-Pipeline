# Project overview

## Purpose

This repository supports a SAFE research-data construction project linking firm locations to fine-grained environmental and remote-sensing measures. The target is a defensible physical point for a building, plant, branch, store, facility, or comparable business location—not merely any coordinate returned by a geocoder.

City, region, and country centroids are unsuitable for the main analysis because they cannot represent building-level exposure to biodiversity, pollution, climate, land cover, satellite-derived measures, or neighborhood conditions.

The scientific output is therefore:

- a selected coordinate;
- evidence describing what was matched;
- an explicit quality and acceptance decision;
- enough lineage and version metadata to reproduce that decision.

`docs/PROJECT_BRIEF.md` remains the long-form historical and methodological reference. This file is the concise current overview, while `docs/DECISIONS.md` records decision status.

## Analytical outcome

`usable_for_analysis` is the final Boolean decision: whether a coordinate is sufficiently precise, geographically consistent, and trustworthy for the intended point-level research.

Diagnostic quality tiers remain separate:

| Tier | Diagnostic meaning | Point-analysis treatment |
|---|---|---|
| A | Address layer, exact match, no major geographic contradiction | Expected `usable_for_analysis = True` |
| B | Address layer, interpolated match, no major contradiction | Acceptance remains open pending pilot evidence |
| C | Street, venue, locality, localadmin, or otherwise too coarse | `False` |
| D | Region, country, fallback, or major contradiction | `False` |
| U | Unmatched, unresolved, permanently failed, or unparseable | `False` |

Confidence is supporting evidence, not a standalone acceptance rule. A successful HTTP request or a returned first feature is not automatically a successful scientific geocode.

## Source-snapshot scope

The first accepted historical source snapshot is 206 CSV files totaling
approximately 3.29 GB. A later delivery becomes authoritative only after its
exact direct-child path population is explicitly frozen in a versioned Stage 0
scope and passes Stage 0. Directory contents or an approximate delivery count
are not an accepted scientific snapshot.

The compressed/on-disk size understates possible parsed memory use: quoted multiline records and multi-million-character fields have been observed. Processing should therefore remain CSV-aware, reproducible, and bounded-memory where useful, without introducing distributed technology solely on scale grounds.

## Architecture

The intended data flow is:

```text
immutable source CSVs
  -> verified file manifest and parser contract
  -> validated staging data with row lineage
  -> conservative canonical address components and input flags
  -> versioned address keys and unique-address table
  -> controlled SAFE query plan and pilot
  -> checkpointed geocoding of unique addresses
  -> deterministic candidate selection and quality classification
  -> geographic validation
  -> left join back to every source row
  -> versioned audit package and final research dataset
```

SAFE/Pelias `/v1/search/structured` is the preferred primary endpoint. Requests normally use reliable structured components and `size=1`. The production service must be accessed with protected runtime authentication and only 2–4 concurrent requests in total.

## Development and production environments

The MacBook is the development environment for design, implementation, Git,
unit/synthetic tests, small diagnostics, lightweight validation, and small
controlled manual-review work. Heavy production processing is Goethe-NHR only
and must run through SLURM. This includes a complete production Phase 2 scan,
at least one million production rows, multi-GB state, expected local execution
of at least ten minutes, and full-data joins, grouping, deduplication,
transformation, geocoding, selection, validation, or reconciliation. When
uncertain, use Goethe-NHR. See `docs/EXECUTION_POLICY.md` for the permanent
definition and fail-closed enforcement contract.

GitHub `origin` is the shared source of truth for code and documentation.
Coherent reviewed changes are committed and pushed from the Mac to an
appropriate branch; Goethe-NHR obtains code with Git and executes an exact
reviewed commit. Source files and Git metadata are not copied to the cluster by
rsync, and jobs never pull code after submission. Large controlled data and
generated outputs remain outside Git.

On Goethe-NHR, home is for small files and personal `/work` is for high-volume
project data and outputs but is not backed up. Heavy computation must not run on
login nodes. `/scratch` is retired, `/work/footprint/public` is not modified,
and the shared Conda base must not be modified.

## Safety and reproducibility principles

- Raw data is immutable; all transformations create explicit derived fields.
- Preserve every original row and enough source metadata to trace it.
- Treat IDs and postcodes as strings until proven otherwise; do not assume `id` is globally unique.
- Preserve Unicode plus native and non-native variants independently.
- Parse logical CSV records, not physical lines, and report malformed or oversized inputs explicitly.
- Clean conservatively: deterministic normalization is allowed; uncertain correction or inference must be flagged.
- Deduplicate stable geographic addresses before geocoding, while retaining a mapping to every original row.
- Record queries, responses, selection reasons, errors, quality decisions, versions, and counts.
- Use bounded retries, checkpoints, and restartable processing; never hide failures.
- Work one phase at a time and stop at every review gate.
