# Data flow and data model

## Governing idea

Each source row persists through the pipeline. Stages add representations and
evidence; they do not overwrite the source or replace source-row identity.

```text
RAW CSV logical record
  source fields
        |
        v
Stage 1: lossless ingestion
  same source fields
  + source_file
  + source_logical_record_number
  + stable_source_row_id_v1
  + source and parser/version provenance
        |
        v
Stage 2: schema/provenance harmonization
  all Stage 1 fields unchanged
  + standard/native presence and non-empty-line counts
        |
        v
Stage 3: safe text cleaning
  all Stage 2 fields unchanged
  + stage03_clean_* derived fields
  + stage03_change_details
  + stage03_row_changed
        |
        v
Stage 4: lowercase canonical forms (accepted on DEVELOPMENT)
  all Stage 3 fields unchanged
  + 12 stage04_lower_* derived fields
  + ordered changed-field and row-changed audit
        |
        v
Stage 5: address reconstruction (DEVELOPMENT evaluation pending)
  all Stage 4 fields unchanged
  + separate clean and lowercase standard/native candidates
  + availability, line count, and occupancy-mask evidence
        |
        v
Future Stages 6–19 (not started)
  candidate representations -> components -> evidence
  -> candidate/query identities -> complete source-row mappings
```

## Raw source record

The source contract contains 15 non-null string fields. Postal codes remain
strings. Standard address lines (`street_address_line_1` through `_4`) and
native lines (`street_address_line_1_native` through `_4_native`) remain
distinct. A physical newline is not assumed to delimit a record; Stage 0 and
Stage 1 use CSV-aware logical records.

A synthetic conceptual source row might contain:

```text
id = "SYNTHETIC-001"
street_address_line_1 = "  10 Example Street  "
street_address_line_1_native = ""
postcode = "00123"
city = "Example City"
country_iso_code = "ZZ"
```

These values are fictional. Real row values are protected and never belong in
documentation, Git, portable logs, or prompts.

## Stable source identity and provenance

Stage 1 adds seven provenance fields:

- `source_file`;
- `source_logical_record_number`;
- `stable_source_row_id_v1`;
- `source_file_sha256`;
- `source_schema_version`;
- `parser_version`; and
- `staging_version`.

`stable_source_row_id_v1` is a 32-byte, domain-separated identity derived from
the source-file SHA-256 and one-based logical record number. It deliberately
does not use the provider `id`, which is not assumed globally unique. It also
does not include the source path: exact duplicate source bytes at the same
logical ordinal would collide and therefore fail validation instead of being
silently disambiguated.

The stable identity is the join key for same-row comparisons, review subsets,
future candidate mappings, and final merge-back. Its formula and value are
frozen; later stages must preserve it exactly.

## Stage 2 structural fields

Stage 2 retains every Stage 1 field and adds only:

- `standard_has_nonempty_source_line`;
- `native_has_nonempty_source_line`;
- `standard_nonempty_source_line_count`; and
- `native_nonempty_source_line_count`.

"Non-empty" means exact source value `""` versus not `""`. Stage 2 does not
trim first, compare representations, infer language/script, reconstruct an
address, or assign meaning to a line position.

## Stage 3 derived clean values

Stage 3 creates derived fields for the eight standard/native address lines and
the four geographic strings (`postcode`, `city`, `region_in_country`, and
`country_iso_code`). The naming rule is:

```text
raw field:      street_address_line_1
derived field:  stage03_clean_street_address_line_1
```

`stage03_change_details` records the changed field and ordered reason codes;
`stage03_row_changed` is a row-level indicator. Unchanged values still have a
derived clean counterpart. No lowercase, parsing, transliteration,
abbreviation, or semantic correction occurs in Stage 3.

For the fictional input above, a conceptual Stage 3 result could be:

```text
street_address_line_1 = "  10 Example Street  "       # preserved raw
stage03_clean_street_address_line_1 = "10 Example Street"
stage03_change_details = [
  {field_name: "street_address_line_1",
   reason_codes: ["WHITESPACE_TRIMMED"]}
]
stage03_row_changed = true
```

## Stage 4 lowercase representation

Stage 4 maps each of the 12 accepted `stage03_clean_*` strings to a distinct
`stage04_lower_*` string using exact Python Unicode `str.lower()`. It appends a
canonical-order list of changed fields and a row-changed flag. It does not
rewrite any Stage 3 column, casefold, apply locale-specific casing, or normalize
after lower. This representation is accepted on DEVELOPMENT.

## Stage 5 reconstructed line-body candidates

Stage 5 independently selects exact nonempty cleaned standard lines and exact
nonempty cleaned native lines in source position order 1 through 4, then joins
each representation with exact `", "`. It repeats the derivation from accepted
Stage 4 lowercase lines. Empty positions create no artificial separators;
gaps preserve the relative order of contributing lines; duplicate line values
remain duplicated. Zero contributing lines yield an empty unavailable
candidate.

Postcode, city, region, and country are not appended. Stage 5 does not parse,
deduplicate, choose between representations, or generate a geocoder query.

## Future candidate representations

Stages 6–19 have not started. Their data model is constrained by these accepted
principles:

- lowercase, reconstructed, parsed, normalized, transliterated, corrected, and
  query-ready values are separate derived representations;
- standard and native candidates have separate identities and evidence;
- each candidate identity maps to one or more `stable_source_row_id_v1` values;
- a source row may map to multiple scientifically justified candidates;
- candidate and query deduplication does not delete source rows; and
- the final result maps selected query/geocoder evidence back to every source
  row through validated one-to-many/many-to-one mappings.

## Validation evidence

Planned component validation records the reference and version, compared
fields, outcome, ambiguity, and supporting/contradictory evidence. The closed
outcomes are:

| Status | Meaning |
|---|---|
| `CONFIRMED` | Positive compatible reference evidence |
| `MISMATCH` | Strong positive contradictory evidence |
| `NOT_FOUND` | No matching reference record; not proof of invalidity |
| `AMBIGUOUS` | More than one plausible interpretation/reference result |
| `UNSUPPORTED` | The check is unavailable for this geography/value |
| `INVALID_FORMAT` | A reviewed syntax contract is violated |

## Query identity and map-back

Future Stage 18 creates versioned query representations; Stage 19 will assign
query identities and deduplicate identical SAFE Pelias calls. A single unique
query may serve multiple candidates, and a candidate may serve multiple source
rows. The mapping chain must remain explicit:

```text
stable_source_row_id_v1 -> candidate_id -> query_id -> geocoder attempt/result
```

Final reconciliation must prove that every input source identity has the
expected mapping outcome, without row loss or join explosion.
