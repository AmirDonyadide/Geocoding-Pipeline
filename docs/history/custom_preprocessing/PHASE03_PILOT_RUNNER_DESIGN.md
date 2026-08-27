# Phase 3 production pilot runner

Status: **IMPLEMENTED AND SYNTHETICALLY VALIDATED — REAL PILOT NOT SELECTED**

Contract: `phase03_sampling_contract_v1`

Canonical contract SHA-256: `0fb7527db5b6a7eb1c7d7eb86d4a038abf4d605728bfe9cf761c74cd33c6d1c7`

Runner: `phase03_pilot_runner_v1`
Reviewed baseline: `df48d392e4eab990e609593d774cc7d3c716e407`

This is the frozen contract for the future 12,000-row Phase 3 pilot. This work
did not open a real Phase 2 Parquet shard, select a real identity, or run a real
transformation. Real selection still requires explicit authorization.

## Explicit stages and data-access boundary

The runner has no implicit discovery, network access, or automatic progression.
Each command requires explicit input and output paths.

1. `pilot-plan`: reports the frozen plan and reads no data.
2. `pilot-profile`: validates the supplied Phase 2 manifest/file set and reads
   only `country_iso_code` (Pass 1).
3. `pilot-select`: validates the same snapshot, reads exactly the 16 approved
   columns below (Pass 2), writes privacy-safe SQLite state, selects 12,000
   identities, and seals the 8,000/4,000 partition.
4. `pilot-validate-identity-set`: validates one controlled binary identity set.
5. `pilot-materialize-development`: performs the separate full-schema join and
   writes only the 8,000 DEVELOPMENT rows. Locked payload is never written.
6. `development-transform`: runs the frozen Phase 3 DEVELOPMENT configuration.
7. `development-review-sample`: selects the frozen 800-row review subset and
   200-row independent double-review subset.
8. `pilot-validate`: reconciles the explicit snapshot and identity partitions.

The two selection passes are:

- Pass 1: `country_iso_code` only.
- Pass 2: `stable_source_row_id_v1`, `source_file`,
  `source_logical_record_number`, the eight native/non-native address lines,
  `postcode`, `city`, `region_in_country`, `country_iso_code`, and
  `location_information`.

Provider `id`, `batch_priority`, and all unrelated columns are excluded. The
full 22-column Phase 2 schema is read only for the later DEVELOPMENT join.

## Frozen sampling classifiers

### Country groups and cohorts

`phase03_sampling_country_group_v1` applies exact, case-sensitive precedence:

1. `""`, `.`, `-` → `MISSING`;
2. `Na`, `Nan`, `Null` → `AMBIGUOUS_PLACEHOLDER`;
3. exact pinned-CLDR alpha-2, alpha-3, or canonical English name →
   `ASSIGNED:<ALPHA2>`;
4. any other content → `UNUSUAL:<digest>`.

The unusual digest is SHA-256 over the exact UTF-8 value with the domain
`safe_geocoding_pipeline:phase03_sampling_country_group_v1\0`. Raw unusual
values and their per-value hashes are never portable. Exact `Na` cannot resolve
to Namibia; exact `NA` may.

Pass-1 population counts classify every exact primary group as:

- `RARE`: fewer than 50 rows;
- `MEDIUM`: 50–499 rows;
- `LARGE`: at least 500 rows.

Every row from every rare exact primary group is mandatory. If all rare rows,
forced safety rows, quotas, the 500-row primary cap, and the 12,000-row total
cannot coexist, the runner fails instead of relaxing the contract.

### Structured completeness

Count `CONTENT` among postcode, city, region, and country: `HIGH` for 3–4,
`MEDIUM` for 2, `LOW` for 1, and `NONE` for 0. Ambiguous-placeholder presence is
an independent boolean diagnostic and never counts as content. This sampling
classifier cannot affect Phase 3 core completeness.

### Postcode lexical precedence

The exact raw string is classified, without trimming or normalization, by first
match: semantic missing; ambiguous placeholder; unsigned ASCII decimal-looking
`[0-9]+\.[0-9]+`; Unicode whitespace; ASCII hyphen; leading-zero ASCII digits
of length at least two; ASCII digits; ASCII letters; ASCII alphanumeric with
both letters and digits; other. Postcodes remain strings.

### Address lines, scripts, and native relationship

Only `CONTENT` counts as a populated line. Native and non-native counts are
separate (0–4); ambiguous presence is retained separately. Their count relation
is `EQUAL`, `MORE_NATIVE`, or `MORE_NON_NATIVE`.

Unicode script categories are calculated independently for native and
non-native content using pinned Unicode Scripts 16.0.0: `NO_CONTENT`,
`UNDETERMINED`, `LATIN_ONLY`, `SINGLE_NON_LATIN`, or `MIXED_DISTINCTIVE`.
Common, Inherited, and Unknown are not distinctive scripts. A field over 65,536
UTF-8 bytes is skipped for script comparison and receives an explicit safety
diagnostic.

Native relationship precedence is: `NO_NATIVE_CONTENT`, `NATIVE_ONLY`,
`NO_ADDRESS_LINE_CONTENT`, `NFC_EQUIVALENT`, `DIFFERENT_SAME_STRUCTURE`, then
`PARTIAL_DIFFERENT_STRUCTURE`. NFC is comparison-only; raw text is unchanged.
No output is called transliteration.

### Markers and source status

Only the frozen registry may produce sampling marker flags for PO box, unit,
floor, building, organization, historical wording, and the house-number shadow
candidate. Matching reuses registry grammar and boundaries. The house-number
outputs are exactly `SHADOW_HOUSE_CANDIDATE_PRESENT` or
`SHADOW_HOUSE_CANDIDATE_ABSENT`; absence is not evidence that no house number
exists.

`location_information` maps exactly to `PREVIOUS_GEOCODING_FAILURE`,
`NO_GEOCODING_INFORMATION`, `REGION_INTERPOLATED`, or `OTHER_UNEXPECTED`.

## Selection, state, and identity sealing

The fixed pilot is 12,000 unique stable identities: 8,000 DEVELOPMENT and 4,000
LOCKED_EVALUATION. Each available secondary category has a minimum target of
50 (or all available below 50). Each exact primary country group is capped at
500. Known Phase 1 safety locations are matched exactly once and forced into the
union. Quota, fill, and split rankings are separate domain-separated SHA-256
scores over the raw 32-byte stable ID, making selection independent of file,
row, batch, and worker order.

The owner-only SQLite store uses exact BLOB IDs and contains only categorical
memberships, scores, safety flags, checkpoints, and version/configuration
fingerprints—never raw address, city, postcode, provider ID, or candidate text.
Its schema is `phase03_pilot_candidate_state_v1`. Production Pass 2 requires at
least 25 GiB free space. Mismatched shard or contract fingerprints fail closed.
The exact tables are `candidate` (identity, primary group, three scores, safety
flag), `membership` (dimension/category/identity), `selected` (final identity
and primary group), `safety_location` (approved source location only),
`checkpoint` (shard identity/count/status), and `run_metadata` (schema,
contract, sampler, binding, and effective fingerprints). All identity columns
use exact BLOB semantics; no raw source value is stored.

Identity sets use `phase03_identity_set_v1`: sorted 32-byte values, canonical
metadata, exact count, and whole-file checksum. The portable seal contains
counts/digests but no identities. It binds the Phase 2 manifest, seed, sampling
contract/version/fingerprint, Git commit, rule registry, references, Phase 3
configuration, timestamp, and partition counts/digests.

## Development review contract

Exactly 800 unique DEVELOPMENT rows are selected.

- Part A: 400 deterministic broad-representation rows across primary-country
  cohort, structured completeness, and script category without constructing a
  Cartesian product.
- Part B: overlapping targets are evaluated with the Part-A rows already
  counting. A greedy deterministic selector chooses the row that improves the
  most unmet targets, with hash tie-breaking. An unavailable target includes
  all available rows and records `TARGET_NOT_FULLY_AVAILABLE`; it is not
  silently treated as satisfied.
- Remaining slots are deterministically filled to exactly 800.

The overlapping minima are: PARTIAL 60, AMBIGUOUS 40, CONFLICT 40,
UNPARSEABLE 30, INSUFFICIENT 30, native/non-native difference 30, country
reference 30, PO box 20, unit/floor/building 30, organization 20, shadow house
candidate 50, placeholder-like 10, and oversized/safety 10.

Exactly 200 review identities are designated for independent double review,
with broad and targeted representation when available. Only these label rows
set `is_independent_review=true`. Portable labels contain hashed review IDs and
the closed `manual_review_reason_codes_v1`, never raw address text or provider
IDs. Protected review context is owner-only and excluded from Git.

## Validation and stop gate

Synthetic tests cover classifier precedence, `Na` safety, Unicode scripts,
oversized skips, rare-group forcing, order/batch independence, infeasible
quotas, disk gating, state/resume fingerprints, identity checksums, locked-set
exclusion, atomic development materialization, the 800/400/200 review contract,
unavailable-target diagnostics, and privacy-safe artifacts.

The final 100,000-row fictional benchmark processed 13,620.528 rows/second in
7.341859 seconds, used 58,589,184 bytes peak RSS, and produced a 55,140,352-byte
SQLite state file. A purely linear extrapolation is about 25 minutes and
11.36 GB of candidate state for 20.6 million rows, but the real category mix,
filesystem, hashing, and Parquet decoding may differ. The 25 GiB production
free-space gate is retained. Performance evidence does not change scientific
classifiers or quotas.

The runner is ready for review only when pytest, Ruff, mypy, `git diff --check`,
the synthetic benchmark, and code review pass. This does not authorize real
pilot selection. Full Phase 3, Phase 4, address keys, deduplication, geocoding,
and SAFE/Pelias remain prohibited.
