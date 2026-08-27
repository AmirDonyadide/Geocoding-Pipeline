# STAGE_4 — sanitized DEVELOPMENT summary

Status: `STAGE_4_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW`

Stage 4 created exact Python Unicode lowercase derived text for the complete 35,000-row DEVELOPMENT set while preserving every Stage 3 field; it remains a candidate pending independent scientific review.

This Git-safe report contains aggregate counts and contract identities only. It contains no source row, address value, selected identity, or HOLDOUT value.

## Identity

- Stage contract: `stage04_lowercase_canonical_contract_v1`
- Execution Git SHA: `0d98ff6450875dfe8fb37c84729e5bbe632ef2fb`
- SLURM job: `1759421`
- DEVELOPMENT fingerprint: `054c66701f854a0108938170e1cb9bcee8a772f7fed29b82cda53c71aa9747ec`
- Input benchmark fingerprint: `014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf`
- Logical fingerprint: `054c66701f854a0108938170e1cb9bcee8a772f7fed29b82cda53c71aa9747ec`
- Schema fingerprint: `dafb4f78b8bfce3120b6f4f7ae8cb44883f4c3a9cfd94b3137871b83c0ed5cbc`
- Input Binding: `90e0e94d4359bd5927820dfc06b2cfc1dc37485c032d95726d1260ec88a534b0`
- Input Stage03 Manifest: `8f70745e31185abce52fdc1685c2b767f90874c21596152ea0463ec6677478d4`
- Manifest: `17a4854cddd8929b65ea79402f1a4f12a1574b720c1921567b577f23e152d1f3`
- Ordered Stable Identity: `fe2a4758582c1880d2b5c62dfc5c587d865e05d13033af9f5e8208b58e2a0487`
- Review Artifact: `0a8fb68b2f4dfb332d3c8fde431898c2229aed42a3cd27184c5ac0f0a12fe75b`
- Review Subset: `014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52`

## Case Change Classification

- ascii case changed: 181549
- unchanged: 233834
- unicode case changed: 4617
- unicode length changed: 0

## Change Rate

- rows changed: 34994
- rows changed percent basis points: 99.98% (9998 basis points)
- rows unchanged: 6

## Field Changed Fields

- city: 31411
- country iso code: 34359
- postcode: 1019
- region in country: 27500
- street address line 1: 32682
- street address line 1 native: 21307
- street address line 2: 18031
- street address line 2 native: 10747
- street address line 3: 4432
- street address line 3 native: 4188
- street address line 4: 243
- street address line 4 native: 247

## Field Changes

- changed fields: 186166
- total lowercase fields: 420000
- unchanged fields: 233834

## Field Group Affected Rows

- city locality: 31411
- country source geography: 34359
- native address lines: 24212
- postcode: 1019
- region: 27500
- standard address lines: 33776

## Field Group Changed Fields

- city locality: 31411
- country source geography: 34359
- native address lines: 36489
- postcode: 1019
- region: 27500
- standard address lines: 55388

## Field Group Total Fields

- city locality: 35000
- country source geography: 35000
- native address lines: 140000
- postcode: 35000
- region: 35000
- standard address lines: 140000

## Lowercase Engine

- arrow utf8 lower values: 0
- ascii fast path values: 394927
- python lower values: 25073

## Output Effects

- character count decrease fields: 0
- character count increase fields: 0
- empty to nonempty fields: 0
- idempotence failures: 0
- max length decrease codepoints: 0
- max length increase codepoints: 0
- nonempty to empty fields: 0
- total character count decrease codepoints: 0
- total character count increase codepoints: 0
- uncased script unchanged values: 45782
- unicode length changed fields: 0

## Performance

- elapsed milliseconds: 22487
- fields per second milli: 18677458
- linear projected 141048582 rows seconds: 90622
- max rss kib: 1362428
- rows per second milli: 1556455
- system cpu milliseconds: 2194
- user cpu milliseconds: 20095

## Qualitative Classifications

- benign unchanged script: 0
- expected case normalization: 500
- no case change required: 0
- questionable: 0
- semantic damage: 0

## Review Row Integrity

- duplicate identities: 0
- holdout rows: 0
- selected rows: 500

## Row Integrity

- added rows: 0
- dropped rows: 0
- duplicate identities: 0
- input rows: 35000
- output rows: 35000

## Script Class Changed Values

- arabic persian: 0
- ascii only: 181549
- cjk hangul: 0
- cyrillic: 2033
- empty: 0
- greek: 220
- latin non ascii: 1900
- mixed: 403
- other: 61

## Script Class Total Values

- arabic persian: 3
- ascii only: 210274
- cjk hangul: 18501
- cyrillic: 2107
- empty: 184653
- greek: 220
- latin non ascii: 1927
- mixed: 1807
- other: 508

## Script Class Unchanged Values

- arabic persian: 3
- ascii only: 28725
- cjk hangul: 18501
- cyrillic: 74
- empty: 184653
- greek: 0
- latin non ascii: 27
- mixed: 1404
- other: 447

## Provenance and privacy

- all stage03 fields unchanged: PASS
- arrow utf8 lower not used: PASS
- ascii fast path equivalent: PASS
- atomic publication: PASS
- bounded memory validation: PASS
- casefold not used: PASS
- exact python lower semantics: PASS
- fixed 500 qualitative review complete: PASS
- holdout untouched: PASS
- idempotence verified: PASS
- input identity bound: PASS
- locale specific casing not used: PASS
- normalization after lower not used: PASS
- no total row python identity set: PASS
- no unexpected empty transitions: PASS
- owner only permissions: PASS
- protected review artifact: PASS
- raw fields unchanged: PASS
- same fixed review identities: PASS
- source provenance unchanged: PASS
- stable identities preserved: PASS
- standard native independent: PASS
- zero questionable: PASS
- zero semantic damage: PASS
