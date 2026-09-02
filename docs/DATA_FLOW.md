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
Stage 8 third-remediation DEVELOPMENT candidate awaiting independent rereview
  exact Stage 7 candidate evidence + ordered long-form parser-evidence index
  + source-candidate map + deterministic STANDARD/NATIVE occurrence view
        |
        v
Proposed Stages 9–14 (not started)
  reference evidence -> hypotheses -> query identities -> top-N results
  -> scoring/granularity -> complete source-row mappings
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

Stage 8 job `1763747` materialized the first DEVELOPMENT candidate and passed
exact count, binding, reversibility, publication, and privacy validation for
old executable `a2544401b4b699f6c020970f3507a2ae432746c5`. It
preserves the complete Stage 7 candidate row, emits one ordered long-form
evidence row per raw component without changing labels/values/order/duplicates,
and preserves a source-row map with separate STANDARD/NATIVE candidate slots.
The exact nested Stage 7 list remains authoritative. A mapped SAFE
parser-evidence name remains `PARSER_EVIDENCE`; Stage 8 emits no hypothesis or
reference result. pycountry and libaddressinput are deferred to the Stage 9
design boundary. Independent review rejected reporting candidate `adde81d…`
for publication-state ordering and stale current architecture wording.
First repair executable `bd89a03…` produced candidate job `1763984`; its exact
scientific reconciliation passed. Independent rereview then found that a real
rename followed by an exception could leave a reader-visible success while the
invocation reported failure. Second repair `bdea7232…` reconciles both
temporary and final paths by captured filesystem identity and permits adoption
only after parent fsync plus complete final reopen validation. Authorized job
`1764219` materialized the repair with manifest `346ea27a…`, unchanged logical
dataset `9c9d431c…`, and exact scientific and ordinary publication
reconciliation. Independent rereview then failed it because post-commit stdout
failure produced a failure exit and policy-A ownership was not rechecked after
parent fsync/final validation. Third repair `c04cb972…` separates publication
and presentation status and adds the terminal no-follow ownership check.
Authorized job `1764273` materialized it with manifest `2a50bd8c…`, the same
logical dataset `9c9d431c…`, and exact v3 terminal reconciliation. It is not
accepted. Jobs `1763747`, `1763984`, and `1764219` remain immutable historical
evidence for their exact executables and do not validate the new candidate.

The Stage 8 implementation and proposed Stages 9–14 are constrained by these
accepted principles:

- lowercase, reconstructed, parsed, normalized, transliterated, corrected, and
  query-ready values are separate derived representations;
- standard and native occurrences retain separate mappings/evidence, while
  exact-equal Stage 6 canonical text may share one content identity;
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

Under the proposed compact design, Stage 10 would create versioned query
hypotheses and Stage 11 would assign query identities and deduplicate identical
SAFE Pelias calls. A single unique query may serve multiple candidates, and a
candidate may serve multiple source rows. The mapping chain must remain
explicit:

```text
stable_source_row_id_v1 -> candidate_id -> query_id -> geocoder attempt/result
```

Final reconciliation must prove that every input source identity has the
expected mapping outcome, without row loss or join explosion.
