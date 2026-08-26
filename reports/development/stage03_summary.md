# STAGE_3 — sanitized DEVELOPMENT summary

Status: `STAGE_3_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW`

Stage 3 created conservative derived clean text for the complete 35,000-row DEVELOPMENT set while preserving every Stage 2 field; it remains a candidate pending independent scientific review.

This Git-safe report contains aggregate counts and contract identities only. It contains no source row, address value, selected identity, or HOLDOUT value.

## Identity

- Stage contract: `stage03_safe_text_cleaning_contract_v1`
- Execution Git SHA: `8446190d1153aeb507678d0de18d027f89f0ec8d`
- SLURM job: `1759109`
- DEVELOPMENT fingerprint: `38df499bfaf61883832a9c718adf4cf92cfcea753337df68fa2e89afb6051bdb`
- Input benchmark fingerprint: `014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf`
- Logical fingerprint: `38df499bfaf61883832a9c718adf4cf92cfcea753337df68fa2e89afb6051bdb`
- Schema fingerprint: `fc991ef63bd80a754114ecae6a9d3c4cf1f33a35a28581fea997edd2e4565c9b`
- Input Binding: `6a2a28d276884511f5b8f63f40d14d6b7f4bf4397aa09289c53acdb92a661e6f`
- Input Stage02 Manifest: `260b77fea50bc2db1bfb10dca8339cb33bcb2e2aad7de9c07ed55a71dec0d419`
- Manifest: `ef57c0ae62cb5466bc1067221370f5b40c7379f3d881aa4837e653dd5855ddd6`
- Review Artifact: `e2233bad584662d4b9881b1fe14f3f4bc58a0f893b33d8fc3ed41a0bda70d987`
- Review Subset: `014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52`

## Change Rate

- rows changed: 1281
- rows changed percent basis points: 3.66% (366 basis points)
- rows unchanged: 33719

## Field Changes

- changed fields: 1795
- total cleaned fields: 420000
- unchanged fields: 418205

## Field Group Affected Rows

- city locality: 422
- country source geography: 0
- native address lines: 452
- postcode: 8
- region: 5
- standard address lines: 858

## Field Group Changed Fields

- city locality: 422
- country source geography: 0
- native address lines: 477
- postcode: 8
- region: 5
- standard address lines: 883

## Field Group Total Fields

- city locality: 35000
- country source geography: 35000
- native address lines: 140000
- postcode: 35000
- region: 35000
- standard address lines: 140000

## Output Effects

- clean values became empty: 2
- idempotence failures: 0
- max length decrease codepoints: 1379388
- max length increase codepoints: 0

## Punctuation

- punctuation changed fields: 0

## Reason Affected Fields

- bom removed: 0
- control character removed: 2
- encoding repaired: 9
- linebreak normalized: 58
- tab normalized: 272
- terminal escape removed: 0
- unicode nfc normalized: 5
- unicode whitespace normalized: 4
- whitespace collapsed: 480
- whitespace only to empty: 2
- whitespace trimmed: 1130

## Reason Affected Rows

- bom removed: 0
- control character removed: 2
- encoding repaired: 9
- linebreak normalized: 58
- tab normalized: 264
- terminal escape removed: 0
- unicode nfc normalized: 4
- unicode whitespace normalized: 4
- whitespace collapsed: 334
- whitespace only to empty: 2
- whitespace trimmed: 807

## Row Integrity

- added rows: 0
- dropped rows: 0
- duplicate identities: 0
- input rows: 35000
- output rows: 35000

## Unicode Encoding

- bom removed fields: 0
- control character removed fields: 2
- encoding repaired fields: 9
- terminal escape removed fields: 0
- unicode nfc normalized fields: 5

## Whitespace

- linebreak normalized fields: 58
- tab normalized fields: 272
- unicode whitespace normalized fields: 4
- whitespace collapsed fields: 480
- whitespace only to empty fields: 2
- whitespace trimmed fields: 1130

## Provenance and privacy

- atomic publication: PASS
- holdout untouched: PASS
- idempotence verified: PASS
- input identity bound: PASS
- owner only permissions: PASS
- protected review artifact: PASS
- punctuation unchanged: PASS
- raw fields unchanged: PASS
- same fixed review identities: PASS
- source provenance unchanged: PASS
- stable identities preserved: PASS
- standard native independent: PASS
