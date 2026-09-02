# Stage 03 — Safe text cleaning

## Status

`STAGE_3_ACCEPTED` on DEVELOPMENT. Production Stage 3 and Stage 9 have not
started.

## Purpose

Stage 3 creates auditable derived clean values for a narrow set of encoding,
Unicode, control-character, and whitespace issues while preserving Stage 2 and
scientific meaning.

## Scope and scientific boundary

The stage performs only its frozen conservative cleaning sequence. It does not
lowercase, parse or reconstruct addresses, transliterate, normalize
abbreviations, infer missing values, remove semantic punctuation, deduplicate,
create queries, or geocode.

## Inputs

- The exact accepted 35,000-row Stage 2 DEVELOPMENT bundle.
- `stage03_input_binding_v1`, including upstream manifest, logical/schema
  identity, benchmark identity, expected rows/artifacts, and contract versions.
- Contract/profile `stage03_safe_text_cleaning_contract_v1` and
  `stage03_safe_text_cleaning_profile_v1`.

HOLDOUT is rejected.

## Outputs

Every Stage 2 field is retained. Stage 3 appends 12
`stage03_clean_<source_field>` strings for the eight standard/native address
lines plus postcode, city, region, and country code;
`stage03_change_details`; and `stage03_row_changed`. The protected physical
bundle includes Parquet, manifest/success markers, fixed-500 review evidence,
and schema/logical fingerprints. Its grain remains one source row.

## Scientific contract

The canonical operations are conservative ftfy encoding repair, terminal
escape/control removal, tab/linebreak/Unicode-whitespace normalization,
whitespace collapse and trim, whitespace-only to empty, BOM removal, and NFC,
in that frozen order. Reasons appear only for actual changes and in canonical
order. Incoming fields remain exact; standard/native remain independent.
Encoding-repair punctuation effects are accounted for separately, and semantic
punctuation normalization is prohibited.

## Implementation provenance

- Accepted v2 implementation:
  `278414573fd465e261f3b9131c45fb564b93622d`.
- Reviewed evidence/candidate:
  `82e945a2f41b61e4deff4c28fff4a02ef2af047a`.
- Acceptance integration:
  `958dddc8a9769977453ea5588e6861b62162090a`.
- Runtime: Python 3.14.3, Unicode 16.0.0, ftfy 6.3.1, PyArrow 25.0.0.

## DEVELOPMENT execution

Job `1759269` processed 35,000 rows and 420,000 cleanable fields in 36.605
seconds. It retained 35,000 rows with zero additions, drops, or duplicate
identities. There were 1,281 changed rows and 1,795 changed fields, zero
idempotence failures, nine punctuation-codepoint changes all tied to the nine
accepted encoding repairs, and zero semantic punctuation normalizations.

## Validation and review

- Logical fingerprint:
  `38df499bfaf61883832a9c718adf4cf92cfcea753337df68fa2e89afb6051bdb`.
- Schema fingerprint:
  `fc991ef63bd80a754114ecae6a9d3c4cf1f33a35a28581fea997edd2e4565c9b`.
- Input binding:
  `6a2a28d276884511f5b8f63f40d14d6b7f4bf4397aa09289c53acdb92a661e6f`.
- Manifest:
  `8f70745e31185abce52fdc1685c2b767f90874c21596152ea0463ec6677478d4`.
- Ordered stable identity:
  `fe2a4758582c1880d2b5c62dfc5c587d865e05d13033af9f5e8208b58e2a0487`.

Independent job `1759272` reproduced full aggregates, preservation, v1/v2
scientific and ordered-reason equality, fixed-500 equality, adversarial cases,
and bounded-memory behavior.

## Historical findings and rejected attempts

V1 remains rejected and unsquashed: implementation
`8446190d1153aeb507678d0de18d027f89f0ec8d`, evidence
`9ed24cea8626b9cd674377636fe1d51e3cd6b456`, job `1759109`. Its scientific
values were sound, but its total-row identity state, repeated cleaner
lifecycle, punctuation reporting, and BOM regression evidence were not
acceptable. V2 changed implementation, validation, and reporting—not cleaning
science—and proved exact equality.

## Accepted decision

Stage 3 was accepted because v2 preserved all upstream values, reproduced v1's
scientific output exactly, removed the implementation/evidence defects, and
passed independent review.

## Known limitations

The clean values do not establish address correctness, component semantics, or
geographic truth. The production runtime projection is planning evidence, not a
production result or authorization.

## Downstream handoff

Stage 4 may lowercase the accepted clean strings exactly while retaining Stage
3. It must not reinterpret cleaning reasons as semantic address judgments.
