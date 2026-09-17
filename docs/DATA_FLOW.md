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
Stage 5: address reconstruction (accepted on DEVELOPMENT)
  all Stage 4 fields unchanged
  + separate clean and lowercase standard/native candidates
  + availability, line count, and occupancy-mask evidence
        |
        v
Stage 6: early exact deduplication (accepted on DEVELOPMENT)
  all Stage 5 fields unchanged
  + nullable standard/native exact-candidate IDs
  + separate exact unique-candidate registry and occurrence counts
        |
        v
Stage 7: libpostal parser evidence (accepted on DEVELOPMENT)
  exact Stage 6 candidates + exact ordered raw parser evidence
  + applicability/technical provenance + structural warnings
  + complete occurrence map-back; no semantic/geographic truth guarantee
        |
        v
Stage 8 lossless address-evidence projection (accepted on DEVELOPMENT)
  exact Stage 7 candidate evidence + ordered long-form parser-evidence index
  + source-candidate map + deterministic STANDARD/NATIVE occurrence view
        |
        v
Stage 9: offline reference evidence (accepted on DEVELOPMENT)
  scoped reference checks and witnesses; no address-validity decision
        |
        v
Stage 10: query hypotheses (implemented, DEVELOPMENT not executed)
  occurrence-specific intents + family decisions + aggregate diagnostics
        |
        v
Proposed Stages 11–14 (not started)
  request identities/QA -> top-N results -> scoring/granularity
  -> complete source-row mappings
```

## Raw source record

The source contract contains 15 non-null string fields. Postal codes remain
strings. Standard address lines (`street_address_line_1` through `_4`) and
native lines (`street_address_line_1_native` through `_4_native`) remain
distinct. The ordered header in
[raw_csv.py](../src/safe_geocoding_pipeline/raw_csv.py) is:

```text
id,street_address_line_1,street_address_line_2,street_address_line_3,street_address_line_4,street_address_line_1_native,street_address_line_2_native,street_address_line_3_native,street_address_line_4_native,postcode,city,region_in_country,country_iso_code,batch_priority,location_information
```

The parser uses strict UTF-8 with an optional leading BOM, comma delimiter,
double-quote quoting with doubled quotes, no escape character and no initial
space skipping. Files are opened with `newline=""`; a physical newline need
not end a logical record. There is no delimiter sniffing or TSV mode. A one-column
parse or unexpected header is a schema problem to investigate, not permission
to rewrite or reinterpret raw input.

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
   reason_codes: ["WHITESPACE_COLLAPSED", "WHITESPACE_TRIMMED"]}
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
each representation with exact `" "`. It repeats the derivation from accepted
Stage 4 lowercase lines. Empty positions create no artificial separators;
gaps preserve the relative order of contributing lines; duplicate line values
remain duplicated. Zero contributing lines yield an empty unavailable
candidate.

Postcode, city, region, and country are not appended. Stage 5 does not parse,
deduplicate, choose between representations, or generate a geocoder query.

## Stage 6 exact candidate map and registry

Stage 6 preserves all 35,000 Stage 5 rows and fields, then appends nullable
STANDARD and NATIVE content-derived IDs. Each available lowercase candidate is
one occurrence; each unavailable representation has a null ID and no
occurrence. Exact candidate equality spans both representations and all rows.
Equal STANDARD/NATIVE text on one row maps twice to one registry row, preserving
two representation occurrences.

The separate registry contains one protected lowercase candidate per exact
ID, total/STANDARD/NATIVE occurrence counts, and deterministic ID ordering.
The ID is SHA-256 over the versioned Stage 6 domain and exact UTF-8 candidate
bytes. Exact byte equality is checked inside every observed digest group, so a
digest alone is never treated as equality proof. Stage 6 applies no additional
normalization or parsing. The Stage 6 output is accepted on DEVELOPMENT.

## Stage 7 evidence and Stage 8 projection

Stage 7 is accepted on DEVELOPMENT under
`stage07_parser_evidence_contract_v2`. It preserves all five Stage 6 registry
fields, immutable v1 technical status and ordered raw libpostal components,
trusted-country applicability/provenance, deterministic structural warnings,
and complete 69,747-occurrence map-back for all 51,779 exact candidates. Its
components remain hypotheses/evidence only; no warning status establishes
semantic correctness or geographic truth.

Stage 8 preserves the complete Stage 7 candidate row, emits one ordered
long-form row per parser component, and retains a source map with separate
STANDARD/NATIVE slots. Labels, values, order and duplicates remain exact; the
nested Stage 7 list is authoritative. Mapped names are parser evidence, not
verified components. Its three stored relations are `candidate_evidence`,
`parser_component_evidence` and `source_candidate_map`; the deterministic
`representation_occurrence_v1` view exposes each present source/role slot.
The [Stage 8 report](../reports/development/stage08.md) retains publication
repair history and scientific-equality evidence.

Each candidate can map to multiple source rows; one source row can have
multiple candidates and hypotheses. Exact-equal text may share a content ID,
but STANDARD/NATIVE occurrences retain distinct provenance. Final results must
map back through these relationships without dropping source rows.

## Validation evidence

Accepted Stage 9 records scoped offline checks against a frozen public reference
pack, with exact source/candidate/component pointers and witness provenance.
Its six relations are defined in the
[Stage 9 contract](stages/STAGE09_OFFLINE_REFERENCE_EVIDENCE.md#minimal-relational-schema-and-necessity).
They add reference evidence; Stage 8 remains the mapping authority.

| Stage 9 status | Meaning |
|---|---|
| `SUPPORTED` | Positive evidence within the reference capability's scope |
| `CONTRADICTED` | Positive conflict under an explicitly authorized negative capability |
| `NOT_FOUND` | An evaluable lookup found no support; absence is not invalidity |
| `NOT_EVALUABLE` | Prerequisites or a supported reference capability are unavailable |

GeoNames has no negative authority. Country assessments and individual checks
are separate; recognition of a country code is not proof that the address lies
in that country. Keep evidence-row, candidate, occurrence and source-row
denominators distinct.

The legacy/later-stage vocabulary `CONFIRMED`, `MISMATCH`, `NOT_FOUND`,
`AMBIGUOUS`, `UNSUPPORTED` and `INVALID_FORMAT` is not Stage 9's schema.
In that proposal, `CONFIRMED` means compatible positive evidence; `MISMATCH`
requires strong positive contradiction; `AMBIGUOUS` means multiple plausible
interpretations; `UNSUPPORTED` means the check is unavailable; and
`INVALID_FORMAT` means a reviewed syntax rule is violated. Neither vocabulary
makes reference absence an invalid-address decision.

## Query identity and map-back

The [Stage 10 revised contract](stages/STAGE10_DATA_CONTRACT.md) generates one
query context per present Stage 8 `(source row, representation)` occurrence.
Each context retains its own candidate, source country, geography, boundaries
and applicable evidence. No cross-occurrence unanimity or candidate-wide
eligibility gate is used. Two protected relations contain context/FKs inline:
`query_hypothesis` at context × distinct complete intent, and
`query_family_decision` at context × Q1–Q6 family. No source map is duplicated.

```text
Stage 8 source/representation occurrence -> Stage 10 query context
  -> hypothesis + all contributing family decisions
  -> Stage 11 complete semantic request -> Stage 12 execution/attempt/result
  -> the same hypothesis/context -> original occurrence/source row
```

Stage 11 later resolves every result-affecting parameter and globally deduplicates
complete requests, preserving all context edges. Stage 12 additionally binds
deployment/index/data identity. Stage 10 intent fingerprints are not final
query_semantic_id values. Contexts sharing candidate text cannot contaminate or
suppress each other. Equal intents across contexts retain separate hypotheses
until the future request layer shares their execution. Final left joins retain
no-candidate and zero-hypothesis source rows. Q7 is globally deferred, with no
pseudo-context hypotheses. Q5/Q6 may coexist. The uniform engineering bounds
are five hypotheses/context and ten/source row; the tighter reachable role
maximum is nine/row. The scientific operating budget is unselected. The
implementation is complete, but the latest
[execution record](stages/STAGE10_IMPLEMENTATION.md) reports no DEVELOPMENT
submission. Stage 11 remains unimplemented.
