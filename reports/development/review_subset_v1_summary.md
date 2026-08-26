# DEVELOPMENT_REVIEW_SUBSET_V1 — sanitized DEVELOPMENT summary

Status: `DEVELOPMENT_REVIEW_SUBSET_V1_MATERIALIZED`

The fixed DEVELOPMENT review subset provides protected qualitative follow-through on the same source rows; full 35,000-row metrics remain the quantitative development evidence.

This Git-safe report contains aggregate counts and contract identities only. It contains no source row, address value, selected identity, or HOLDOUT value.

## Identity

- Stage contract: `development_review_subset_contract_v1`
- Execution Git SHA: `0cc5077ca80e23c69f15cb37dd29bf010d080958`
- SLURM job: `1758910`
- DEVELOPMENT fingerprint: `014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52`
- Input benchmark fingerprint: `014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf`
- Logical fingerprint: `014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52`
- Schema fingerprint: `bd3446085e3382d5fdbedd9483a4332ff26d2e5211a03f4b019c765534cfcc51`

## Batch Priority

- 0: 57
- 1: 200
- 2: 51
- 3: 192
- empty: 0
- other: 0

## Challenge Reasons

- city missing: 78
- country missing: 55
- mixed script: 53
- multiple address lines: 170
- non latin script: 30
- no geocoding information: 57
- postcode missing: 177
- previous geocoding failure: 200
- region missing: 190
- standard missing native present: 33
- standard native materially different: 106
- very long address field: 20

## Country Coverage

- available countries: 269
- represented countries: 269

## Location Information

- empty: 0
- no geocoding information: 57
- other: 0
- postcode interpolated: 51
- previous geocoding failure: 200
- region interpolated: 192

## Missingness

- city missing: 78
- country missing: 55
- postcode missing: 177
- region missing: 190

## Native Line Counts

- 0: 30
- 1: 306
- 2: 99
- 3: 44
- 4: 21

## Quota Shortfalls

- shortfall category count: 0
- shortfall total: 0

## Review Row Integrity

- duplicate identities: 0
- holdout rows: 0
- selected rows: 500

## Script Classes

- common or unknown only: 30
- empty: 0
- latin only: 387
- mixed script: 53
- non latin present: 30

## Source File Coverage

- development source files: 1405
- review source files: 243

## Standard Line Counts

- 0: 33
- 1: 298
- 2: 104
- 3: 42
- 4: 23

## Standard Native Availability

- both: 437
- native only: 33
- neither: 0
- standard only: 30

## Standard Native Equality

- case only or trivially equal: 22
- exactly equal: 309
- materially different: 106
- not both present: 63

## Provenance and privacy

- atomic publication: PASS
- holdout untouched: PASS
- input identity bound: PASS
- owner only permissions: PASS
- protected review artifact: PASS
- raw fields unchanged: PASS
- stable identities preserved: PASS
