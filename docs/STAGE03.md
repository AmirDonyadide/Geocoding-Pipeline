# Stage 3 — safe text cleaning

## Status and boundary

Stage 3 is a **DEVELOPMENT CANDIDATE** only. It is not scientifically accepted,
does not authorize Stage 4, and does not change Stage 0, Stage 1, or Stage 2.
The governing transformation contract is
`stage03_safe_text_cleaning_contract_v1`; its executable policy is
`stage03_safe_text_cleaning_profile_v1`.

Stage 3 is the first address-changing library-first stage. It creates
conservative derived strings that remove representation noise while preserving
the exact Stage 2 input. It does not lowercase, casefold, transliterate, parse,
reconstruct, validate, infer, correct, standardize, deduplicate, geocode, or
call an external service.

The candidate consumes only the accepted 35,000-row
`BENCHMARK_SAMPLE_V1` DEVELOPMENT Stage 2 bundle. Paths containing `holdout`
are rejected before input access. The sealed 15,000-row HOLDOUT and the
separate 1,411-file production track are outside this stage.

## Input contract and binding

An owner-only `stage03_input_binding_v1` binds exactly:

- `stage02_schema_provenance_harmonization_contract_v1`;
- Stage 2 logical fingerprint
  `ff95021bd2f4b2994e9e2a766f32e792e29797a128dc64fa3aef100ff9f5ca72`;
- Stage 2 schema fingerprint
  `3c4a2d616ab6dacf57f42fff7e84175a48fbd50c6a060046434593c5aefa74d4`;
- the protected Stage 2 manifest SHA-256;
- the input benchmark fingerprint
  `014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf`;
- exactly 35,000 rows.

The binding is SHA-pinned at execution. Stage 3 validates the complete Stage 2
bundle, exact schema and metadata, owner-only permissions, page checksums,
manifest identity, row count, and stable identities before transformation.
Directory contents never extend the input implicitly.

## Exact cleaning surface

Stage 3 cleans derived copies of these 12 non-null Stage 2 source strings, in
this fixed order:

1. `street_address_line_1`
2. `street_address_line_2`
3. `street_address_line_3`
4. `street_address_line_4`
5. `street_address_line_1_native`
6. `street_address_line_2_native`
7. `street_address_line_3_native`
8. `street_address_line_4_native`
9. `postcode`
10. `city`
11. `region_in_country`
12. `country_iso_code`

Each derived column is named `stage03_clean_<source-field>`. Standard and
native lines are transformed independently with the same universal rules.
They are never concatenated, compared, translated, transliterated, or given
English-specific treatment.

Every one of the 26 incoming Stage 2 columns remains first in the output, in
the exact incoming order, Arrow type, nullability, logical value, and row
order. In particular Stage 3 does not clean `id`, `batch_priority`,
`location_information`, provenance paths and hashes, row numbers, stable IDs,
version identifiers, or the four Stage 2 structural fields.

## Derived schema and change provenance

After the 12 non-null derived strings, Stage 3 adds:

- `stage03_change_details`: a non-null ordered
  `list<struct<field_name: string not null, reason_codes: list<string not null>
  not null>>`; unchanged fields are omitted, changed fields follow the fixed
  cleaning-field order, and reason codes follow the fixed profile order;
- `stage03_row_changed`: a non-null Boolean exactly equal to whether
  `stage03_change_details` is non-empty.

The detail list is the compact auditable record of whether each field changed
and why. A listed field must differ exactly from its raw source field and must
have at least one reason. An omitted field must be identical to its clean
value. Unknown, duplicate, or out-of-order fields/reasons fail validation.

## Cleaning profile

`stage03_safe_text_cleaning_profile_v1` applies the following operations in
order. Reasons are emitted only when that operation changes the current value.

| Order | Reason code | Exact operation |
|---:|---|---|
| 1 | `ENCODING_REPAIRED` | Apply ftfy 6.3.1 encoding repair under the explicit conservative configuration below. |
| 2 | `TERMINAL_ESCAPE_REMOVED` | Remove only ftfy 6.3.1's documented ANSI pattern `ESC [` + digits/semicolons + one ASCII letter. |
| 3 | `CONTROL_CHARACTER_REMOVED` | Remove C0/C1 control code points except TAB and the exact line-break characters handled as whitespace. |
| 4 | `TAB_NORMALIZED` | Map U+0009 to U+0020 SPACE. |
| 5 | `LINEBREAK_NORMALIZED` | Map LF, VT, FF, CR, NEL, LINE SEPARATOR, and PARAGRAPH SEPARATOR to U+0020 SPACE. |
| 6 | `UNICODE_WHITESPACE_NORMALIZED` | Map the remaining Unicode White_Space code points to U+0020 SPACE. |
| 7 | `WHITESPACE_COLLAPSED` | Collapse each run of two or more U+0020 characters to one U+0020. |
| 8 | `WHITESPACE_TRIMMED` | Remove leading and trailing U+0020 characters; edge trimming and edge-BOM removal repeat together to a fixed point. |
| 9 | `WHITESPACE_ONLY_TO_EMPTY` | Record that a non-empty post-control value containing only Unicode White_Space became exact `""`. |
| 10 | `BOM_REMOVED` | Remove U+FEFF only while it occurs at an edge during the fixed-point edge cleanup; preserve interior U+FEFF. |
| 11 | `UNICODE_NFC_NORMALIZED` | Apply `unicodedata.normalize("NFC", value)` under Unicode data 16.0.0. |

Unicode White_Space is frozen as U+0009–U+000D, U+0020, U+0085, U+00A0,
U+1680, U+2000–U+200A, U+2028, U+2029, U+202F, U+205F, and U+3000. Python's
broader `str.isspace()` is not the contract because it also classifies several
C0 information separators as whitespace.

The removable controls are U+0000–U+0008, U+000E–U+001F, U+007F–U+0084,
and U+0086–U+009F. TAB, LF, VT, FF, CR, and NEL are whitespace instead. Stage 3
does not remove other Unicode categories. In particular it preserves ZWJ,
ZWNJ, bidi controls, variation selectors, other potentially meaningful format
characters, private-use characters, combining marks, native scripts, emoji,
and unusual symbols.

### Explicit ftfy policy

The only general ftfy operation is `ftfy.fix_encoding_and_explain()` from
ftfy 6.3.1. `TextFixerConfig` is constructed with every option explicit:

```text
unescape_html=False
remove_terminal_escapes=False
fix_encoding=True
restore_byte_a0=False
replace_lossy_sequences=False
decode_inconsistent_utf8=False
fix_c1_controls=True
fix_latin_ligatures=False
fix_character_width=False
uncurl_quotes=False
fix_line_breaks=False
fix_surrogates=False
remove_control_chars=False
normalization=None
max_decode_length=1000000
explain=True
```

Disabling byte-A0 restoration, lossy repair, and inconsistent mixed decoding
favours false negatives over speculative repair. HTML unescaping, quote
rewriting, ligature expansion, width conversion, line-break rewriting,
surrogate rewriting, general control removal, and normalization are not
delegated to ftfy. A non-empty ftfy explanation is required whenever
`ENCODING_REPAIRED` is emitted. Terminal-escape removal is invoked separately
and receives its own reason code.

The authoritative runner fails closed unless Python is exactly 3.14.3,
`unicodedata.unidata_version` is exactly `16.0.0`, ftfy is exactly 6.3.1, and
PyArrow is exactly 25.0.0.

## Punctuation and forbidden transformations

Stage 3 implements no punctuation-spacing or punctuation replacement rule.
Apostrophes, hyphens, periods, commas, colons, semicolons, slashes, backslashes,
fractions, dashes, and other punctuation remain untouched except when bytes
that visibly form mojibake are repaired by the constrained encoding step.
Consequently the Stage 3 punctuation-change metric is always zero and no
punctuation reason code exists.

NFKC/NFKD, accent stripping, ASCII folding, lowercasing, casefolding,
transliteration, abbreviation expansion, missing-marker interpretation,
postcode/country validation or correction, address parsing/reconstruction,
company/unit/floor removal, geographic lookup, fuzzy matching, deduplication,
query generation, and geocoding are forbidden.

## Idempotence and validation

For every valid string `x`, the required property is
`clean(clean(x)).value == clean(x).value`. The second application must also
emit no change reasons. Synthetic property-style tests cover arbitrary Unicode
plus adversarial examples. The authoritative DEVELOPMENT run repeats cleaning
over all 420,000 derived values and requires zero idempotence failures.

Publication additionally requires:

- exactly 35,000 input and output rows; zero dropped or added rows;
- zero duplicate stable identities and unchanged canonical row ordering;
- exact Arrow equality for every one of the 26 incoming Stage 2 columns;
- unchanged stable identity and provenance values;
- only the 14 permitted derived fields;
- reason/value consistency and deterministic ordering;
- input hashes unchanged before and after processing;
- exact independent page-checksum read-back;
- owner-only `0700` directories and `0600` files;
- atomic publication with no partial-success topology.

Nulls, non-string cleaning inputs, wrong Stage 2 schema/fingerprint/manifest,
malformed binding metadata, partial outputs, or any path containing `holdout`
fail before scientific success publication. Errors carry stable codes and do
not contain source values.

## Scientific and physical identity

`stage03_logical_dataset_sha256_v1`, domain
`SAFE_STAGE03_LOGICAL_DATASET_V1`, uses typed length-delimited binary encoding
and binds the Stage 3 contract/profile/schema versions, exact cleaning-field
and reason-code order, explicit Unicode/ftfy policy and versions, Stage 2
contract/logical/schema identity, benchmark fingerprint, output schema
fingerprint, and expected row count. It excludes paths, Parquet layout and
hashes, Git/runtime host identity, timestamps, SLURM job, duration, and
permissions.

The protected Stage 3 manifest separately binds the SHA-pinned input binding,
exact Stage 2 manifest, input/output artifact identities, runtime versions,
Git SHA, SLURM job, metrics, and validations. Its byte SHA-256 is the physical
manifest fingerprint. The binding file has its own byte SHA-256.

## DEVELOPMENT reporting and review

All 35,000 DEVELOPMENT rows contribute to aggregate Stage 3 metrics. Portable
JSON/Markdown use `development_reporting_contract_v1` and
`development_sanitized_summary_v1`, extended only with fixed allowlisted Stage
3 metric/check names and one fixed factual interpretation. They contain no raw
or cleaned source value, selected identity, source filename, or HOLDOUT value.

The protected Stage 3 qualitative artifact uses exactly the 500 identities in
`DEVELOPMENT_REVIEW_SUBSET_V1`, fingerprint
`014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52`.
It reads the accepted immutable selected-identity artifact, does not reselect,
and writes a new `stage03_review.parquet`; it never changes or overwrites
`stage02_review.parquet`. Its schema contains review order and protected join
identity, the 12 raw source values, the 12 corresponding clean values, Stage 3
change details/row flag, and the existing four sanitized Stage 2 structural
fields. The artifact is owner-only, page-checksum validated, and hash-bound to
the fixed subset and Stage 3 identities.

The independent review session should examine every changed fixed-subset row,
a sample of unchanged multilingual rows, each observed reason family, encoding
repairs, empty-result cases, maximum length changes, standard/native behavior,
and any unexpected aggregate concentration before considering acceptance.

## Authoritative DEVELOPMENT candidate evidence

Candidate implementation commit
`8446190d1153aeb507678d0de18d027f89f0ec8d` ran unchanged on Goethe as SLURM
job `1759109`. The job completed with exit code `0:0`. It consumed the exact
accepted Stage 2 and benchmark identities declared above and produced:

- 35,000 input and output rows, zero dropped/added rows, and zero duplicate
  stable identities;
- exact preservation of all 26 incoming Stage 2 fields and source provenance;
- 1,281 changed rows (3.66%) and 1,795 changed fields out of 420,000;
- zero idempotence failures across all applicable DEVELOPMENT values;
- zero punctuation changes, zero BOM changes, and zero terminal-escape changes;
- nine encoding repairs, five NFC-normalized fields, two control-character
  removals, and two whitespace-only values becoming empty;
- logical fingerprint
  `38df499bfaf61883832a9c718adf4cf92cfcea753337df68fa2e89afb6051bdb`;
- schema fingerprint
  `fc991ef63bd80a754114ecae6a9d3c4cf1f33a35a28581fea997edd2e4565c9b`;
- manifest fingerprint
  `ef57c0ae62cb5466bc1067221370f5b40c7379f3d881aa4837e653dd5855ddd6`.

The maximum decrease was 1,379,388 code points. A separate privacy-safe SLURM
diagnostic (`1759110`) attributed the largest decreases to the previously known
oversized multiline-field class: only tab/linebreak normalization and repeated
whitespace collapse contributed to the maximum, while non-whitespace content
remained. The magnitude is therefore not evidence of an additional Stage 3
operation, but the independent reviewer should scrutinize the outlier class
and its downstream scalability implications.

The Stage 3 protected review artifact has exactly the frozen 500 ordered
identities and SHA-256
`e2233bad584662d4b9881b1fe14f3f4bc58a0f893b33d8fc3ed41a0bda70d987`.
The sanitized quantitative evidence is
`reports/development/stage03_summary.json` and
`reports/development/stage03_summary.md`. This state is a DEVELOPMENT candidate
ready for independent review, not scientific acceptance; Stage 4 remains
unstarted.
