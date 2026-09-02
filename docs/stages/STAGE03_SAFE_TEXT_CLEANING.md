# Stage 3 — Safe text cleaning

## Purpose

Create auditable derived clean values for a narrow set of encoding, Unicode,
control-character, and whitespace issues while preserving all Stage 2 fields
and scientific meaning.

## Input

An exact accepted Stage 2 bundle and `stage03_input_binding_v1` containing
upstream manifest/logical identity, schema, expected rows/artifacts, benchmark
fingerprint, and contract versions. DEVELOPMENT execution is bound to all
35,000 accepted identities; HOLDOUT is rejected.

## Output

Stage 3 retains every Stage 2 column and adds:

- 12 clean fields named `stage03_clean_<source_field>` for eight standard/native
  address lines plus `postcode`, `city`, `region_in_country`, and
  `country_iso_code`;
- `stage03_change_details`, containing changed field names and canonical ordered
  reason codes; and
- `stage03_row_changed`.

The output includes protected Parquet, manifest/success markers, schema/logical
fingerprints, a fixed-500 review artifact, and sanitized aggregate evidence.

## Scientific rules

The frozen cleaning order and reason vocabulary are:

1. `ENCODING_REPAIRED` using the pinned conservative ftfy configuration;
2. `TERMINAL_ESCAPE_REMOVED`;
3. `CONTROL_CHARACTER_REMOVED`;
4. `TAB_NORMALIZED`;
5. `LINEBREAK_NORMALIZED`;
6. `UNICODE_WHITESPACE_NORMALIZED`;
7. `WHITESPACE_COLLAPSED`;
8. `WHITESPACE_TRIMMED`;
9. `WHITESPACE_ONLY_TO_EMPTY`;
10. `BOM_REMOVED`; and
11. `UNICODE_NFC_NORMALIZED`.

Reasons are present exactly when the derived value changes and are stored in
canonical order. All incoming fields and `stable_source_row_id_v1` remain
unchanged. Standard/native representations remain independent. Literal
punctuation codepoint changes caused by valid encoding repair are reported
separately from semantic punctuation normalization, which is zero and not part
of the cleaning policy.

## Non-goals

Stage 3 does not lowercase/casefold, parse/reconstruct addresses, assign
components, transliterate, normalize abbreviations, correct spelling/geography,
infer missing values, remove semantic punctuation, deduplicate, select geocoder
components, generate queries, or geocode.

## Libraries

Python 3.14.3 `unicodedata` (Unicode 16.0.0), ftfy 6.3.1 with an explicit
`TextFixerConfig`, PyArrow 25.0.0, regular-expression/Arrow fast paths, and
conservative SAFE bounded-batch orchestration.

## Validation

V2 validation proves exact Stage 2 batch/shard topology, ordered stable-ID
fingerprints, 35,000-to-35,000 rows, no duplicates/drops/additions, equality of
all 26 incoming Stage 2 columns, clean/reason consistency, idempotence, exact
v1/v2 scientific and ordered-reason equality, fixed-500 equality, BOM ordering,
ASCII fast path, identity-stream adversarial behavior, huge-value safety,
punctuation accounting, bounded memory, owner-only permissions, atomic
publication, and HOLDOUT exclusion.

## DEVELOPMENT evidence

The accepted v2 implementation commit is
`278414573fd465e261f3b9131c45fb564b93622d`. Goethe job `1759269` processed
35,000 rows and 420,000 cleanable fields in 36.605 seconds with 1,067,884 KiB
process peak RSS. It produced:

- 35,000 input and output rows;
- zero dropped/added rows and zero duplicate identities;
- exact preservation of all 26 incoming Stage 2 columns;
- 1,281 changed rows and 1,795 changed fields;
- zero idempotence failures;
- 9 literal punctuation-codepoint changes, all associated with the 9 accepted
  encoding repairs; and
- zero semantic punctuation normalizations.

The logical fingerprint is
`38df499bfaf61883832a9c718adf4cf92cfcea753337df68fa2e89afb6051bdb` and
schema fingerprint is
`fc991ef63bd80a754114ecae6a9d3c4cf1f33a35a28581fea997edd2e4565c9b`.
The fixed-500 review artifact was byte-identical between v1 and v2.

Evidence commit `82e945a2f41b61e4deff4c28fff4a02ef2af047a` was independently reviewed in
Goethe job `1759272`, which reproduced the complete aggregates, preservation,
v1/v2 equality, review equality, and adversarial/bounded-memory evidence. Final
integration commit `958dddc8a9769977453ea5588e6861b62162090a` records acceptance.

See the authoritative Git-safe
[Stage 3 report](../../reports/development/stage03.md).

## Production status

**NOT STARTED.** The 41-hour projection for 141,048,582 rows is an estimate from
DEVELOPMENT, not an execution record or authorization. The DEVELOPMENT evidence
launcher includes review/equivalence work and must not be reused as a production
launcher. A separate production materialization wrapper requires later review
after production Stage 2 acceptance.

## Privacy

Full and fixed-500 Stage 3 artifacts are protected (`0700` directories, `0600`
files), published atomically, and excluded from Git. Sanitized reports contain
only allowlisted aggregates/fingerprints. No protected value is sent to an
external API, web service, geocoder, or LLM.

## Acceptance status

**`STAGE_3_ACCEPTED` ON DEVELOPMENT.** Stage 3 is frozen.

Rejected v1 remains preserved and unsquashed: implementation
`8446190d1153aeb507678d0de18d027f89f0ec8d`, evidence
`9ed24cea8626b9cd674377636fe1d51e3cd6b456`, and job `1759109`. Its scientific
values were reproduced without semantic damage, but it was rejected for
total-row identity state, repeated cleaner lifecycle, incorrect/ambiguous
punctuation reporting, and incomplete BOM regression evidence. V2 changed
implementation/reporting/validation only and proved exact scientific equality.

At Stage 3 acceptance, Stage 4 was not started. Stages 4–6 are now separately
accepted on DEVELOPMENT; this does not change or reopen accepted Stage 3.
Production Stages 2–6 remain **NOT STARTED**.
