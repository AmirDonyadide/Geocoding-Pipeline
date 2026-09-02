# Stage 8 — Lossless address-evidence projection

## Status and authority

**`STAGE08_ADDRESS_EVIDENCE_IMPLEMENTATION_READY_FOR_CONTROLLED_DEVELOPMENT_REEXECUTION`.**

This remains the controlling scientific contract for Stage 8 DEVELOPMENT. The
first implementation at Git commit
`a2544401b4b699f6c020970f3507a2ae432746c5` produced controlled DEVELOPMENT
job `1763747`. Independent review rejected exact reporting candidate
`adde81d2237e99993222994ce56efb0d74f7c2d3` because its publication-state
ordering could expose success before prepublication reopen validation and
because `docs/PROJECT_BRIEF.md` retained a stale Stage 8 reference-tool
assignment. The bounded publication repair is executable
`bd89a032eb6fcf16a7515e0bd2991165d87246b1`. Repaired DEVELOPMENT job
`1763984` published manifest
`d521240b42a40b9c1408f0f7241583bc76b7779e4107179e73fdcb7c7a69e119`,
and passed exact scientific reconciliation for `bd89a032…`. Independent
rereview then failed reporting candidate
`fdf2f8c78781a6bdb5dad637af5954ae81cf331d`: the final rename could take
effect and then raise before Python-side publication-tree state changed,
leaving a reader-visible successful final artifact while the invocation
reported failure. The second bounded repair is executable
`bdea7232a3f92ebd381be87610b753b8e4c35481`. It is ready for one
separately authorized controlled DEVELOPMENT reexecution and is not accepted.
This status does not itself authorize that job, production, HOLDOUT access,
Stage 9, geocoding, Pelias, Senzing, DeepParse, or any external address service.

The design is based on accepted Stage 7 candidate
`656a16d3d1f33cb152ace557c26f42df047bc7d6`, its acceptance merge
`b36b995809fe902fe80af25856cb24786b795b1c`, and independent rereview job
`1763656`, which returned
`STAGE07_EVIDENCE_ONLY_INDEPENDENT_REREVIEW_PASS`; its sanitized evidence is
commit `356de44f3e86e37972d60cac45d01703ad1f6856`. DeepParse remains closed as
`DEEPPARSE_INFRASTRUCTURE_PATH_NOT_JUSTIFIED` and is not a Stage 8 dependency.

## Second repaired implementation

The implementation preserves this frozen design without changing its grains,
field semantics, nullability, ordering, or lineage rules. It provides bounded
PyArrow/Parquet materialization, bounded DuckDB reconciliation, immutable
publication, and an independent reopen validator. The first repair remains
intact: `_IN_PROGRESS` stays present through artifact/manifest fsync and the
complete prepublication reopen validation; only then may `_SUCCESS.json` be
written and `_IN_PROGRESS` removed.

The second repair captures the temporary attempt's non-symlink device/inode
identity before the commit boundary and explicitly classifies both temporary
and final paths after an ambiguous rename outcome. A final-only state is
adopted as success only during the rename/immediate-post-rename phases, only
when the final directory is the captured attempt, and only after parent fsync
plus complete independent published reopen validation. Parent-fsync failure or
postpublication validation failure remains fatal and demotes the identity-
matching owned tree. Demotion removes `_SUCCESS.json`, ensures the exact
`_IN_PROGRESS` marker, re-observes post-effect cleanup mutations, preserves
owner-only modes, and is idempotent. Symlinks are never followed, and an
unrelated final publication is never overwritten, adopted, or demoted.

The sanitized [second remediation report](../../reports/development/stage08_address_evidence_publication_remediation_v2.md)
records the complete crash-consistency audit. The
[first remediation report](../../reports/development/stage08_address_evidence_remediation.md)
and original [implementation report](../../reports/development/stage08_address_evidence_implementation.md)
remain historical evidence for their exact executables.

## Historical first-repair DEVELOPMENT evidence

Job `1763984` completed `0:0` in 15m36s from the exact clean detached first-
repair executable. Its immutable output is
`/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage08/development/stage08_development_20260902T080150Z_bd89a032eb6f`.
The success marker binds manifest SHA-256
`d521240b42a40b9c1408f0f7241583bc76b7779e4107179e73fdcb7c7a69e119`
and logical dataset SHA-256
`9c9d431c2c1b92712e0cb372f2661ad48f4fe8758dc0327d25aef90ab2c2d526`.

The result contains 51,779 candidates, 6,106,088 ordered component rows,
35,000 source rows, and 69,747 occurrences (34,822 STANDARD; 34,925 NATIVE).
Every frozen preservation, reversibility, foreign-key, occurrence, warning,
privacy, and later-stage-exclusion check passed; dangling and mismatch counts
are zero. The runtime is Python 3.14.3, PyArrow 25.0.0, and DuckDB 1.5.5.

Prepublication reopen validation completed with `_IN_PROGRESS` present and
`_SUCCESS.json` absent. Only then did the repaired transition create success,
remove the incomplete marker, fsync, atomically publish, fsync the parent, and
perform the post-publication reopen validation. The final tree has no
`_IN_PROGRESS`, no incomplete sibling, and no symlink; all directories are
`0700`, all files are `0600`, and stderr is empty. The sanitized
[execution report](../../reports/development/stage08_address_evidence_development.md)
and [candidate report](../../reports/development/stage08_address_evidence_development_candidate_report.md)
freeze the complete aggregate, topology, scheduler, input-binding, and
publication evidence for executable `bd89a032…`. Independent rereview's
post-effect rename finding does not assert this artifact corrupt, but the job
cannot validate executable `bdea7232…`.

## Historical rejected-candidate DEVELOPMENT evidence

Goethe-NHR job `1763747` completed `0:0` in 15m18s from the byte-identical
executable commit `a2544401b4b699f6c020970f3507a2ae432746c5`. Its immutable
manifest SHA-256 is
`bdf86738fb071e38b2ad090f4627a821149352fb1490e62b76e5819aa915bcf9` and its
logical dataset SHA-256 is
`9c9d431c2c1b92712e0cb372f2661ad48f4fe8758dc0327d25aef90ab2c2d526`.
The exact 51,779 candidates, 6,106,088 ordered components, 35,000 source rows,
and 69,747 representation occurrences reconciled with zero dangling,
component-count, or occurrence-count mismatches. All frozen validation fields,
reversibility, atomic publication, and owner-only permissions passed.
Those scientific reconciliation results remain valid evidence for the old
executable. The job and artifact remain immutable, but executable repair makes
them ineligible to serve as the final Stage 8 candidate.

The current sanitized execution/candidate reports retain these historical
identities alongside the repaired candidate. `AllocCPUS=80` for both jobs is
exclusive-node scheduler accounting: `general1` is
`OverSubscribe=EXCLUSIVE`, while each job requested four CPUs and ran one task
with DuckDB at four threads. It is not 80-way application concurrency and is
not material to scientific validity.

## Decision

Stage 8 is a lossless, typed, provenance-rich projection of accepted evidence.
It is not a semantic address-normalization stage. It has three materialized
relations:

1. one candidate row preserving the complete accepted Stage 7 row and adding
   mechanical projection/index counts;
2. one ordered long-form row per raw libpostal component; and
3. one source row preserving the exact STANDARD/NATIVE candidate links and the
   minimum immutable source/country lineage needed for direct map-back.

The exact Stage 7 nested parser list remains authoritative. The long-form
component relation is a reversible evidence index over that list, not a
replacement parse. Its optional SAFE component name is a one-to-one,
versioned namespace over a pinned libpostal label; it is neither a verified
component nor a corrected value.

Stage 8 emits no address hypothesis. It performs no reference lookup, format
validation, geographic comparison, correction, query generation, scoring, or
match acceptance.

```text
accepted Stage 7 candidate evidence (51,779 rows)
              | exact copy + mechanical counts
              v
  candidate_evidence 1 ---- * parser_component_evidence
              |
              | stage06_exact_candidate_id
              *
     source_candidate_map (35,000 source rows; two representation slots)
              |
              v
  deterministic 69,747-row STANDARD/NATIVE occurrence view
```

## Governing scientific separation

The Stage 8 contract makes the following categories explicit and
non-interchangeable:

```text
SOURCE_VALUE
  != SOURCE_LINEAGE
  != UPSTREAM_DERIVED_REPRESENTATION
  != TRUSTED_SOURCE_CONTEXT
  != PARSER_TECHNICAL_PROVENANCE
  != PARSER_EVIDENCE
  != STRUCTURAL_DIAGNOSTIC
  != MECHANICAL_INDEX
  != HYPOTHESIS
  != REFERENCE_EVIDENCE
  != GEOCODER_RESULT
  != ACCEPTED_MATCH
```

These are field semantic classes, not confidence ranks. They establish no
hidden trust hierarchy and carry no numeric weight.

| Semantic class | Stage 8 meaning |
|---|---|
| `SOURCE_VALUE` | An exact immutable source field, such as provider `id` or raw `country_iso_code`; it is preserved, not asserted to be geographically correct. |
| `SOURCE_LINEAGE` | Source file, file hash, logical record number, stable source-row ID, candidate occurrence counts, and representation/source-row relationships. |
| `UPSTREAM_DERIVED_REPRESENTATION` | Exact accepted cleaned/lower strings, Stage 6 lowercase candidate text, and deterministic content ID. They are derived from source values and are not source truth. |
| `TRUSTED_SOURCE_CONTEXT` | Accepted source-country provenance/status and the unanimous valid country code when one exists. Trust is limited to provenance for operations requiring country context; it is not address validity. |
| `PARSER_TECHNICAL_PROVENANCE` | Parser applicability, historical technical status, execution origin, and pinned parser identity. |
| `PARSER_EVIDENCE` | Exact raw libpostal labels/values and their one-to-one SAFE evidence names. Labels, values, and boundaries may be wrong. |
| `STRUCTURAL_DIAGNOSTIC` | Exact Stage 7 warning status, reasons, and signals. Warning presence is not invalidity; warning absence is not correctness. |
| `MECHANICAL_INDEX` | Ordinals, counts, mapping coverage, representation scope, schemas, and fingerprints derived without semantic interpretation. |
| `HYPOTHESIS` | Prohibited in Stage 8; first allowed only under an accepted Stage 10 contract. |
| `REFERENCE_EVIDENCE` | Prohibited in Stage 8; belongs to Stage 9. |
| `GEOCODER_RESULT` / `ACCEPTED_MATCH` | Prohibited in Stage 8; belong to later separately authorized stages. |

Every field receives one of these classes in the machine-readable schema
contract and in Arrow field metadata. The Parquet schema also carries the
contract/profile/schema/mapping/taxonomy identities and the exact upstream
binding. A reader that drops Arrow metadata must still use the manifest schema
contract; field names alone are not the complete scientific contract.

## Purpose

Stage 8 exists to make accepted Stage 7 evidence safer and easier to consume
without increasing its scientific authority. It must:

- preserve the exact Stage 6 candidate and complete accepted Stage 7 row;
- preserve parser applicability, technical history, execution origin, raw
  ordered output, structural warnings, and warning non-evaluation separately;
- expose every raw component by zero-based ordinal without sorting,
  deduplication, coalescing, relabeling, or value transformation;
- retain multiple occurrences of one raw label and duplicate label/value
  pairs;
- attach a deterministic mapping-coverage result while retaining unknown raw
  labels exactly;
- keep STANDARD and NATIVE occurrence provenance separate while recording the
  candidate-level scope `STANDARD`, `NATIVE`, or `BOTH`;
- retain explicit missing/partial/invalid/conflicting country provenance; and
- guarantee complete source-row and representation map-back.

## Explicit non-purpose and boundary

Stage 8 must not:

- trim, normalize, transliterate, concatenate, reorder, correct, or replace
  any source or candidate text;
- infer country from candidate text, parser text, representation, script,
  majority vote, or first occurrence;
- convert parser output into a flattened semantic address record;
- coalesce repeated parser labels into one value;
- interpret a `house`, `city`, `country`, or other parser label as verified;
- resurrect `COMPONENTS_READY` or `COMPONENTS_ABSTAIN`;
- treat `NO_STRUCTURAL_WARNINGS_DETECTED` as semantic trust;
- validate postcode existence or syntax, postcode/locality agreement,
  locality/admin/country agreement, street existence, or house-number
  existence;
- perform fuzzy matching, correction, transliteration, address formatting,
  candidate scoring, geographic lookup, coordinate assignment, or final match
  acceptance;
- read GeoNames, Overture, OSM, Pelias, Google Address Validation API, or any
  external address service; or
- emit a correctness score, confidence weight, validity label, or geographic
  claim.

`CONFIRMED`, `MISMATCH`, `NOT_FOUND`, `AMBIGUOUS`, `UNSUPPORTED`, and
`INVALID_FORMAT` are later reference-validation outcomes. Stage 8 does not
emit them.

## Exact input contract

The Stage 8 DEVELOPMENT implementation is bound to two immutable accepted
inputs.

### Accepted Stage 7 v2 candidate evidence

- acceptance: `STAGE_7_ACCEPTED`;
- reviewed repository candidate:
  `656a16d3d1f33cb152ace557c26f42df047bc7d6`;
- acceptance merge: `b36b995809fe902fe80af25856cb24786b795b1c`;
- independent rereview: job `1763656`, verdict
  `STAGE07_EVIDENCE_ONLY_INDEPENDENT_REREVIEW_PASS`, sanitized evidence commit
  `356de44f3e86e37972d60cac45d01703ad1f6856`;
- contract: `stage07_parser_evidence_contract_v2`;
- profile: `stage07_parser_evidence_profile_v2`;
- schema: `stage07_parser_evidence_schema_v2`;
- implementation: `e684d84a8d68498ea790542143c8e125b3eb87b5`;
- contract fingerprint:
  `c9561e6d08263b2a8824ff66f2a3aa8521e3ff880759abc14173cce440ced8a4`;
- schema fingerprint:
  `b0e0e83ea3d929b7df8a6a5f64c2e8eb026395a917da90e97a98858b27e9ead2`;
- logical dataset SHA-256:
  `0f0706c1396803737f22845837753878bfd2e8b3f9af59b48cfcc1b8c5774530`;
- manifest SHA-256:
  `f58410877a7810562df7985c7316de7546d4dd8e11a647fd659c53a272e9c266`;
- parser bundle fingerprint:
  `f3c6db7e9f11ab75b2207be773e946d531dbba763008d9f7e5036d8c923dc2ae`;
- 51,779 candidate rows;
- 51,774 `PARSED_NONEMPTY` and 5 `PARSED_EMPTY` rows;
- 6,106,088 exact raw components;
- maximum 881,338 components in one candidate; and
- maximum accepted candidate length 25,920,495 code points.

Every accepted Stage 7 field, type, nullability, metadata identity, candidate
ID, candidate string, count, status, component sequence, warning value, and
signal is an exact input. Stage 8 fails before publication if any differ.

### Accepted Stage 6 row map

Stage 7 v2 binds Stage 6 but does not republish the source-row map, so Stage 8
also opens the exact accepted Stage 6 row-map artifacts through their manifest:

- contract: `stage06_early_exact_deduplication_contract_v1`;
- profile: `stage06_early_exact_deduplication_profile_v1`;
- schema fingerprint:
  `9c07b7a4c3f7a5c43ad457dcf6f7fe3fd746d54d82a731139905b30828b6c9ce`;
- logical dataset fingerprint:
  `2f6379c0cd5dc9654c03895cae6fdd48f3a7af528158c33e44d2030c816640b6`;
- row-map logical fingerprint:
  `1ff9067c521ae93d28c300d7120a03c39681ce7830bf23b6619e2ca6129a4fe1`;
- input-binding fingerprint:
  `6ba224d6d24c3631aae8aac69f4a362bb054f01d9e3d09327ec6b0fdd85a0e7d`;
- manifest SHA-256:
  `e1da7b8ef04b65b1ece8e710720b57a8536841766fcf9de641f889b42eadd241`;
- 35,000 source rows; and
- 69,747 representation occurrences: 34,822 STANDARD and 34,925 NATIVE.

No Stage 5, Stage 7 v1, eligibility, or raw source artifact is opened through
an unbound alternate path. Stage 7 v2 already binds immutable Stage 7 v1 and
eligibility evidence. Stage 6 is opened only because its row map is required
for source/representation lineage.

## Output grain and relational contract

The output is a linked three-table design plus one deterministic logical view.
It is not one flattened address table.

### `candidate_evidence`

Grain: exactly one row per accepted `stage06_exact_candidate_id`, sorted by
unsigned candidate-ID bytes. The primary key is the existing non-null
fixed-size 32-byte candidate ID.

The first 25 fields are the complete accepted Stage 7 v2 schema in exact order,
type, nullability, metadata, and logical value:

| Field(s) | Arrow type / nullability | Semantic class |
|---|---|---|
| `stage06_exact_candidate_id` | `fixed_size_binary[32]`, non-null | `UPSTREAM_DERIVED_REPRESENTATION` |
| `stage06_candidate_lower` | `string`, non-null | `UPSTREAM_DERIVED_REPRESENTATION` |
| `stage06_occurrence_count`, `stage06_standard_occurrence_count`, `stage06_native_occurrence_count` | `uint64`, non-null | `SOURCE_LINEAGE` |
| `stage07_country_provenance_status` | `string`, non-null | `TRUSTED_SOURCE_CONTEXT` |
| `stage07_trusted_country_iso_code` | `string`, nullable | `TRUSTED_SOURCE_CONTEXT` |
| `stage07_valid_country_occurrence_count`, `stage07_missing_country_occurrence_count`, `stage07_invalid_country_occurrence_count` | `uint64`, non-null | `TRUSTED_SOURCE_CONTEXT` |
| `stage07_distinct_valid_country_count` | `uint32`, non-null | `TRUSTED_SOURCE_CONTEXT` |
| `stage07_parser_applicability_status`, `stage07_parse_status`, `stage07_parser_execution_origin` | `string`, non-null | `PARSER_TECHNICAL_PROVENANCE` |
| `stage07_libpostal_components` | non-null `large_list<element: struct<label: large_string not null, value: large_string not null> not null>` | `PARSER_EVIDENCE` |
| `stage07_structural_warning_status`, `stage07_structural_warning_reason_codes` | non-null `string`; non-null `large_list<element: large_string not null>` | `STRUCTURAL_DIAGNOSTIC` |
| `stage07_raw_ordered_substrings`, `stage07_lexical_numeric_stream_equal` | nullable `bool` | `STRUCTURAL_DIAGNOSTIC` |
| `stage07_internal_boundary_count`, `stage07_internal_single_codepoint_fragment_count`, `stage07_maximum_components_per_lexical_run`, `stage07_adjacent_repeated_label_internal_boundary_count`, `stage07_candidate_lexical_numeric_codepoints`, `stage07_output_lexical_numeric_codepoints` | nullable `uint64` | `STRUCTURAL_DIAGNOSTIC` |

Stage 8 appends only these fields:

| Field | Arrow type / nullability | Meaning |
|---|---|---|
| `stage08_representation_scope` | `string`, non-null | `STANDARD`, `NATIVE`, or `BOTH`, derived solely from the two Stage 6 occurrence counts. |
| `stage08_raw_component_count` | `uint64`, non-null | Exact length of the nested raw component list. |
| `stage08_mapped_component_count` | `uint64`, non-null | Component rows whose exact raw label has a v1 mapping. |
| `stage08_unmapped_component_count` | `uint64`, non-null | Component rows whose exact raw label has no v1 mapping. |
| `stage08_component_index_status` | `string`, non-null | Mapping/index coverage only; never correctness. |

`stage08_component_index_status` is closed to:

- `COMPONENT_INDEX_EMITTED`;
- `COMPONENT_INDEX_EMITTED_WITH_UNMAPPED_LABEL`; and
- `COMPONENT_INDEX_EMPTY`.

For every candidate, raw count equals mapped plus unmapped count. Nonempty
technical status requires a positive raw count and one component-index row per
raw component. Empty technical status requires raw/mapped/unmapped counts of
zero and `COMPONENT_INDEX_EMPTY`.

### `parser_component_evidence`

Grain: exactly one row per raw Stage 7 component, sorted by unsigned candidate
ID bytes and then zero-based ordinal. The composite key is
`(stage06_exact_candidate_id, stage08_component_ordinal)`.

| Field | Arrow type / nullability | Semantic class |
|---|---|---|
| `stage06_exact_candidate_id` | `fixed_size_binary[32]`, non-null | `UPSTREAM_DERIVED_REPRESENTATION` |
| `stage08_component_ordinal` | `uint64`, non-null | `MECHANICAL_INDEX` |
| `stage08_raw_libpostal_label` | `large_string`, non-null | `PARSER_EVIDENCE` |
| `stage08_raw_libpostal_value` | `large_string`, non-null | `PARSER_EVIDENCE` |
| `stage08_label_mapping_status` | `string`, non-null | `MECHANICAL_INDEX` |
| `stage08_safe_parser_evidence_component` | `string`, nullable | `PARSER_EVIDENCE` |
| `stage08_evidence_class` | `string`, non-null | Constant `PARSER_EVIDENCE`; a conforming consumer cannot relabel the row as source or verified truth. |

Mapping status is exactly `MAPPED_DEFINED_LABEL` or `UNMAPPED_LABEL`.
`MAPPED_DEFINED_LABEL` requires a non-null mapped evidence component;
`UNMAPPED_LABEL` requires it to be null. The raw label/value remain present in
both cases. No component row contains a readiness, validity, confidence, or
geographic field.

### `source_candidate_map`

Grain: exactly one row per accepted Stage 6 source row, in exact accepted
source-row order. Provider `id` is preserved but is not a key. The stable
source-row ID is the non-null unique key.

| Field | Arrow type / nullability | Semantic class |
|---|---|---|
| `id` | `string`, non-null | `SOURCE_VALUE` |
| `source_file` | `string`, non-null | `SOURCE_LINEAGE` |
| `source_logical_record_number` | `uint64`, non-null | `SOURCE_LINEAGE` |
| `stable_source_row_id_v1` | `fixed_size_binary[32]`, non-null | `SOURCE_LINEAGE` |
| `source_file_sha256` | `fixed_size_binary[32]`, non-null | `SOURCE_LINEAGE` |
| `stage08_source_row_ordinal` | `uint64`, non-null | `MECHANICAL_INDEX` |
| `postcode`, `city`, `region_in_country` | `string`, non-null | `SOURCE_VALUE` |
| `country_iso_code` | `string`, non-null | `SOURCE_VALUE` |
| `stage03_clean_postcode`, `stage03_clean_city`, `stage03_clean_region_in_country`, `stage03_clean_country_iso_code` | `string`, non-null | `UPSTREAM_DERIVED_REPRESENTATION` |
| `stage04_lower_postcode`, `stage04_lower_city`, `stage04_lower_region_in_country`, `stage04_lower_country_iso_code` | `string`, non-null | `UPSTREAM_DERIVED_REPRESENTATION` |
| `stage06_standard_exact_candidate_id` | `fixed_size_binary[32]`, nullable | `SOURCE_LINEAGE` |
| `stage06_native_exact_candidate_id` | `fixed_size_binary[32]`, nullable | `SOURCE_LINEAGE` |
| `stage08_standard_representation_status` | `string`, non-null | `MECHANICAL_INDEX` |
| `stage08_native_representation_status` | `string`, non-null | `MECHANICAL_INDEX` |

Each representation status is exactly `PRESENT` or `ABSENT`, and `PRESENT` is
equivalent to a non-null candidate ID. An absent representation creates no
candidate and no parser-component row, but its explicit `ABSENT` state remains
on the source row. The raw, accepted Stage 3 clean, and accepted Stage 4 lower
postcode/locality/region/country values are copied exactly so Stage 9 can
consume source-derived geographic context without consulting parser fields.
These occurrence-level country strings are not themselves the candidate-level
trusted-country result; only the preserved Stage 7 country-provenance fields
carry `TRUSTED_SOURCE_CONTEXT`. All other Stage 6/Stage 5/source fields remain
recoverable by stable ID through the exact manifest-bound Stage 6 row map.

### Deterministic `representation_occurrence_v1` view

The contract defines a logical `UNION ALL` view over non-null STANDARD and
NATIVE slots in `source_candidate_map`. It has one row for each
`(stable_source_row_id_v1, representation)` with representation exactly
`STANDARD` or `NATIVE`; `BOTH` is never an occurrence value. On accepted
DEVELOPMENT it must contain exactly 69,747 rows. If a source row maps both
representations to the same candidate, two distinct occurrence rows remain.

Its exact fields are:

| Field | Arrow-equivalent type / nullability | Semantic class |
|---|---|---|
| `stage08_source_row_ordinal` | `uint64`, non-null | `MECHANICAL_INDEX` |
| `stable_source_row_id_v1` | `fixed_size_binary[32]`, non-null | `SOURCE_LINEAGE` |
| `stage08_representation` | `string`, non-null | `SOURCE_LINEAGE` |
| `stage08_representation_ordinal` | `uint8`, non-null | `MECHANICAL_INDEX` |
| `stage06_exact_candidate_id` | `fixed_size_binary[32]`, non-null | `UPSTREAM_DERIVED_REPRESENTATION` |

The source-row ordinal is zero-based and contiguous in exact accepted Stage 6
row-map order. Representation ordinal is `0` for STANDARD and `1` for NATIVE.
The canonical view operation is:

```sql
SELECT
  stage08_source_row_ordinal,
  stable_source_row_id_v1,
  'STANDARD'::VARCHAR AS stage08_representation,
  0::UTINYINT AS stage08_representation_ordinal,
  stage06_standard_exact_candidate_id AS stage06_exact_candidate_id
FROM source_candidate_map
WHERE stage08_standard_representation_status = 'PRESENT'
UNION ALL
SELECT
  stage08_source_row_ordinal,
  stable_source_row_id_v1,
  'NATIVE'::VARCHAR AS stage08_representation,
  1::UTINYINT AS stage08_representation_ordinal,
  stage06_native_exact_candidate_id AS stage06_exact_candidate_id
FROM source_candidate_map
WHERE stage08_native_representation_status = 'PRESENT'
ORDER BY stage08_source_row_ordinal, stage08_representation_ordinal
```

The view is not separately materialized in v1 because that would duplicate a
relation already represented losslessly by two nullable slots. Its canonical
SQL text, version, logical fingerprint, counts, and validation results are in
the manifest.

## Mechanically mapped SAFE parser-evidence vocabulary

The [pinned libpostal README](https://raw.githubusercontent.com/openvenues/libpostal/25099c506612b34b23b1bfe286ca6321fcf06f35/README.md)
with SHA-256
`14b9589f17f2cd88b2972d89bd98b463ed598885ec9b8778b11a8a128d7d43cb`
states that the parser may technically emit any label defined in its training
data and lists 20 currently defined labels. The Stage 7 sanitized diagnostic
observed 19 of them; `world_region` was defined upstream but absent from that
diagnostic. The diagnostic is not proof that an unknown label cannot occur in
the complete frozen registry or a later production artifact.

`stage08_libpostal_label_mapping_v1` is therefore a closed mapping for known
labels plus an open, lossless unknown path:

| Exact raw label | SAFE evidence component |
|---|---|
| `house` | `PARSER_HOUSE` |
| `category` | `PARSER_CATEGORY` |
| `near` | `PARSER_NEAR` |
| `house_number` | `PARSER_HOUSE_NUMBER` |
| `road` | `PARSER_ROAD` |
| `unit` | `PARSER_UNIT` |
| `level` | `PARSER_LEVEL` |
| `staircase` | `PARSER_STAIRCASE` |
| `entrance` | `PARSER_ENTRANCE` |
| `po_box` | `PARSER_PO_BOX` |
| `postcode` | `PARSER_POSTCODE` |
| `suburb` | `PARSER_SUBURB` |
| `city_district` | `PARSER_CITY_DISTRICT` |
| `city` | `PARSER_CITY` |
| `island` | `PARSER_ISLAND` |
| `state_district` | `PARSER_STATE_DISTRICT` |
| `state` | `PARSER_STATE` |
| `country_region` | `PARSER_COUNTRY_REGION` |
| `country` | `PARSER_COUNTRY` |
| `world_region` | `PARSER_WORLD_REGION` |

This mapping deliberately does not create `building` or `locality`: mapping
libpostal `house` to verified building semantics, or `city` to a narrower
locality concept, would add an unsupported interpretation. `unknown` is not a
mapped component value. An unknown exact label receives `UNMAPPED_LABEL`, a
null SAFE component, and its exact label/value remains in order.

Mapping is case-sensitive exact string equality. It never transforms the raw
value, groups concepts, reorders rows, selects a preferred duplicate, combines
values, or interprets the parser label as correct. A later consumer may use
the mapped field only as `PARSER_EVIDENCE` or
`PARSER_HYPOTHESIS_INPUT` under a separately accepted contract.

## Public/offline metadata placement

Stage 8 introduces no `pycountry` or libaddressinput dependency.

- The accepted Stage 7 country provenance is already bound to pinned Debian
  `iso-codes` 4.18.0-1 metadata. Stage 8 preserves that result and does not
  perform a second country lookup, fuzzy name search, subdivision lookup, or
  canonicalization with [pycountry](https://github.com/pycountry/pycountry).
- [libaddressinput](https://github.com/google/libaddressinput) is
  country-format and required-field metadata for collecting or checking
  structured postal-address forms. It is not a free-text parser and it is not
  Google Address Validation API. Applying its formats or required fields would
  be new format/reference evidence, not lossless projection.

Both libraries therefore move to the Stage 9 design boundary. Stage 9 may
propose exact-code ISO/subdivision metadata and a pinned offline
libaddressinput snapshot as descriptive/format evidence, subject to release,
hash, license, coverage, ambiguity, and absence-not-invalidity review. Fuzzy
`pycountry.search_fuzzy` is not approved by this decision. Runtime Address Data
Service calls and Google Address Validation API remain prohibited.

## Exact state handling

The status dimensions remain independent. No cross-product is compressed into
`VALID`, `INVALID`, `READY`, a score, or a confidence.

### Parsed nonempty

Preserve `PARSED_NONEMPTY`, the exact nonempty raw list, applicability,
execution origin, and warning fields. Emit one component-index row per list
element. `COMPONENT_INDEX_EMITTED` reports mapping coverage only. Structural
warnings do not remove or rewrite component rows.

### Historical parsed empty

Preserve `PARSED_EMPTY` and exact `[]`. Emit zero component rows and
`COMPONENT_INDEX_EMPTY`. Preserve the accepted distinction in which four
country-eligible empty rows have `STRUCTURAL_WARNINGS_PRESENT` with
`PARSED_EMPTY_NO_COMPONENTS`, while the country-unresolved empty row has
`STRUCTURAL_WARNINGS_NOT_EVALUATED`. None is an invalid-address decision.

### Unresolved parser applicability and country context

Preserve each exact Stage 7 status:

- `PARSER_ELIGIBILITY_MISSING_COUNTRY`;
- `PARSER_ELIGIBILITY_PARTIAL_COUNTRY`;
- `PARSER_ELIGIBILITY_INVALID_COUNTRY`; and
- `PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY`.

Preserve the country provenance counts/status and null trusted country. The
historical v1 parser did run these candidates, so Stage 8 must also preserve
`PARSED_NONEMPTY`/`PARSED_EMPTY` and
`REUSED_IMMUTABLE_STAGE07_V1`; it must not falsely label them “never
attempted.” The raw evidence may be mechanically indexed because that step is
country-independent. Any later operation requiring one trusted country must
fail closed or abstain rather than infer, vote, or choose one.

`PARSER_NOT_APPLICABLE_COUNTRY` exists in the frozen policy vocabulary but is
not present in the accepted Stage 7 v2 DEVELOPMENT registry and is not an
accepted Stage 8 v1 input state. Stage 8 v1 does not synthesize it. A future
separately accepted upstream contract containing that state requires a new
Stage 8 contract version that preserves it explicitly.

### Parser never attempted

This is not a state in the exact accepted Stage 7 v2 input. Stage 8 v1 accepts
only historical `PARSED_NONEMPTY` and `PARSED_EMPTY`. If a future upstream
contract introduces `NOT_ATTEMPTED_COUNTRY_UNRESOLVED` or another technical
state, it must remain distinct from parsed empty and requires a new Stage 8
contract version. The v1 implementation fails on the unknown status rather
than guessing its meaning.

### Unknown labels

Unknown labels do not fail materialization and are never dropped. They receive
`UNMAPPED_LABEL`, retain exact label/value/ordinal, increment explicit
candidate and aggregate counts, and cause
`COMPONENT_INDEX_EMITTED_WITH_UNMAPPED_LABEL`. Zero unknown labels is not a
scientific correctness claim and is not required for losslessness.

### Duplicate labels and values

Every list position becomes a separate row. Ordinals are contiguous from zero
to raw component count minus one. Duplicate labels, duplicate values, and
duplicate pairs remain separate. No dictionary or pivot is an authoritative
Stage 8 representation.

### Giant candidates

Size is not a scientific status. A giant candidate is processed in full or
the entire publication fails. Stage 8 never skips, truncates, substring-
processes, null-pads, or replaces it. The accepted 25,920,495-code-point
candidate and 881,338-component candidate are explicit DEVELOPMENT validation
targets.

### STANDARD, NATIVE, BOTH, and absence

STANDARD and NATIVE stay separate on each source row. Candidate-level scope is
derived as:

- positive STANDARD count and zero NATIVE count: `STANDARD`;
- zero STANDARD count and positive NATIVE count: `NATIVE`; and
- both positive: `BOTH`.

Zero total occurrences is fatal. An absent source representation is explicit
`ABSENT` with a null candidate ID and creates no occurrence. A same-row equal
STANDARD/NATIVE pair remains two occurrences mapping to one candidate. No
native string is overwritten by standard text, and Stage 8 emits no
transliteration.

## Losslessness and map-back guarantees

A conforming Stage 8 publication guarantees all of the following:

1. `candidate_evidence` has exactly the accepted Stage 7 candidate IDs and
   preserves every accepted Stage 7 field logically exactly.
2. Concatenating `parser_component_evidence` by candidate and ordinal
   reconstructs the exact nested Stage 7 label/value list, including empty
   lists, ordering, duplicates, Unicode, and unknown labels.
3. The candidate text is exact and is never reconstructed from parser values.
4. `source_candidate_map` has exactly the accepted 35,000 DEVELOPMENT stable
   source identities in exact order, with a contiguous zero-based row ordinal,
   exact candidate IDs, and selected source/country lineage fields.
5. The occurrence view has exactly 69,747 DEVELOPMENT rows, with 34,822
   STANDARD and 34,925 NATIVE, and every candidate occurrence count equals the
   number of occurrence-view references.
6. Every candidate ID in either downstream table exists in
   `candidate_evidence`; no dangling component or source mapping exists.
7. Original `id`, source file, logical record number, stable source-row ID, and
   source file hash are preserved. All remaining source values are exactly
   recoverable from the immutable Stage 6 row map through stable ID.
8. No source row or representation occurrence is deduplicated away.

These are equality and totality guarantees, not semantic address guarantees.

## Version and fingerprint identities

The implementation must use these frozen prospective identifiers:

- contract: `stage08_address_evidence_projection_contract_v1`;
- profile: `stage08_address_evidence_projection_profile_v1`;
- schema bundle: `stage08_address_evidence_projection_schema_v1`;
- semantic taxonomy: `stage08_semantic_classification_v1`;
- label mapping: `stage08_libpostal_label_mapping_v1`;
- occurrence view: `stage08_representation_occurrence_view_v1`;
- logical encoding: `stage08_address_evidence_logical_encoding_v1`;
- validation contract: `stage08_address_evidence_validation_v1`;
- manifest: `stage08_address_evidence_manifest_v1`.

Before any protected execution, implementation review must publish and freeze:

- one fingerprint per Arrow schema, including field order, type, nullability,
  field semantic class, and schema metadata;
- the schema-bundle fingerprint;
- the 20-entry exact label-mapping fingerprint;
- the complete contract fingerprint over identities, upstream bindings,
  schemas, vocabularies, mapping, ordering, and losslessness rules; and
- the exact implementation Git SHA.

Each relation has a layout-independent SHA-256 logical fingerprint. Canonical
encoding is domain-separated and length-prefixed; it distinguishes null from
empty, hashes strings as exact UTF-8, hashes fixed binary values as bytes,
encodes unsigned integers big-endian, preserves field and row order, and
encodes nested raw components by count followed by ordered label/value pairs.
The dataset fingerprint binds the contract fingerprint, the three relation
logical fingerprints, the occurrence-view logical fingerprint, and all row
counts. It must be invariant to input batch size, output batch size, row-group
size, and shard layout. Physical size and SHA-256 are recorded for every
artifact and verified after publication.

The original design-only session correctly invented no data fingerprint.
Repaired job `1763984` now supplies the manifest-bound logical dataset
fingerprint recorded above; it was derived only by the reviewed materializer
and successful reopen validation.

## Bounded-memory implementation strategy

The future materializer uses a single ordered streaming pass over the Stage 7
candidate registry and a separate ordered streaming pass over the Stage 6 row
map.

- PyArrow is authoritative for exact schemas, nested-list preservation,
  Parquet read/write, metadata, chunk-aware iteration, and incremental hashing.
- Candidate input is read in byte-bounded batches. A component list is handled
  from Arrow offsets/child arrays; it is not converted into a Python list of
  dictionaries.
- At most one candidate's nested component slice plus bounded input/output
  batches is retained. Giant candidate rows are written alone where needed.
- Component rows are emitted in byte-bounded child-array slices so the
  881,338-component case does not create one population-sized table.
- Candidate output retains the exact nested array by Arrow slicing and appends
  scalar mechanical counts; it does not rebuild raw components from the long
  table.
- Parquet uses `large_list`/`large_string` for nested evidence and
  `large_string` for long-form raw label/value columns. Row groups and pages
  are byte-bounded and checksum-enabled.
- DuckDB performs external, predicate-pushed source-map/occurrence
  reconciliation, referential-integrity joins, and aggregate validation with
  explicit memory/thread/temp limits. It does not own nested serialization.
- Polars is not a Stage 8 v1 dependency. Adding a second transformation engine
  has no demonstrated value for this projection and would expand the
  reproducibility surface.
- Pandas is prohibited for materialization and full validation.

The implementation records peak batch bytes, maximum candidate/component
sizes, shard/row-group counts, elapsed time, requested resources, MaxRSS, and
spill use. It does not promise production scale from a linear extrapolation.

## Runtime, execution, and privacy

The initial implementation should reuse the accepted controlled runtime where
compatible: Python 3.14.3, Unicode 16.0.0, PyArrow 25.0.0, and DuckDB 1.5.5.
Any dependency or version change is part of implementation review and changes
the profile identity.

Protected full DEVELOPMENT and all future production execution are Goethe-NHR
SLURM jobs. Production/heavy entry points invoke the shared guard before input
access and require `SAFE_EXECUTION_SITE=goethe-nhr` plus a nonempty
`SLURM_JOB_ID`; there is no local bypass. The login node is orchestration-only.
No work uses `/scratch`, modifies `/work/footprint/public`, modifies the shared
Conda base, or dynamically pulls code inside a job. Code arrives through Git at
an exact pushed SHA.

Protected candidates, component values, source identities, row artifacts, and
maps remain owner-only on controlled infrastructure. They are never included
in prompts, web requests, external services, logs, Git, or sanitized reports.
Logs contain only aggregate progress, status codes, timing, and fingerprints.
HOLDOUT paths fail closed. Stage 8 requires no network access or credential.

## Artifact topology and publication

A run publishes to a new immutable controlled directory:

```text
<controlled-stage08-root>/<unique-run-id>/
  candidate_evidence/data/part-*.parquet
  parser_component_evidence/data/part-*.parquet
  source_candidate_map/data/part-*.parquet
  metadata/stage08_libpostal_label_mapping_v1.json
  metadata/stage08_schema_contract_v1.json
  stage08_address_evidence_manifest.json
  _SUCCESS.json
```

Directories are `0700`; files are `0600`. The output target must not exist.
Writing occurs in a new private sibling attempt directory. Content, schemas,
logical/physical hashes, row counts, foreign keys, permissions, and reopen
validation must pass before terminal publication. Collision fails closed. A
failed attempt is retained under its distinct attempt identity and is never
relabeled or overwritten as success. `_SUCCESS.json` is created only after
prepublication reopen validation and binds the manifest SHA-256 and dataset
logical fingerprint.

The terminal commit boundary is driven by observable filesystem state. The
implementation captures the attempt directory identity, transitions to the
success/no-in-progress marker set, fsyncs the temporary tree, renames it, fsyncs
the parent, and validates the final tree. An exception from the rename is
ambiguous: only a final-only directory with the captured identity may be
adopted, and only after the parent fsync and complete published validator pass.
All other owned failure trees are demoted to success absent and `_IN_PROGRESS`
present. Both temporary and final paths are inspected without following
symlinks; unrelated paths are preserved.

The manifest contains no protected values. It records exact upstream
identities, contract/profile/schema/taxonomy/mapping versions and fingerprints,
status vocabularies, relation order, logical/physical identities, counts,
runtime/Git/SLURM provenance, permissions, bounded-memory settings/metrics,
zero-network and exclusion claims, and validation results.

## Failure and abstention semantics

### Publication-fatal failures

The complete run fails without publishing success on any:

- input path, manifest, artifact hash, schema, metadata, contract, profile, or
  count mismatch;
- missing, added, duplicate, out-of-order, or cross-wired candidate/source ID;
- malformed/null raw component member, invalid UTF-8 round trip, unknown
  technical status, or status/list inconsistency;
- component ordinal gap/duplicate, long/nested reconstruction mismatch, count
  mismatch, dangling foreign key, or occurrence-map mismatch;
- candidate-ID collision with different exact candidate text;
- giant-value truncation, size-based skip, incomplete read/write, Arrow or
  Parquet round-trip failure;
- unbounded-memory guard, runtime pin, execution-site guard, permission,
  topology, disk-space, fsync, or atomic-publication failure; or
- HOLDOUT, production, network, external-service, or path-policy violation.

### Preserved non-fatal evidence states

The following are preserved as distinct evidence and never collapsed into
“invalid address”:

| Situation | Stage 8 representation |
|---|---|
| Parser output preserved with warnings | Exact technical status/raw list plus `STRUCTURAL_WARNINGS_PRESENT`; component index still emitted. |
| Parser output preserved without warnings | Exact raw list plus `NO_STRUCTURAL_WARNINGS_DETECTED`; no trust claim. |
| Structural warnings not evaluated | Exact `STRUCTURAL_WARNINGS_NOT_EVALUATED`; usually unresolved country applicability; no inferred result. |
| Historical technical empty | `PARSED_EMPTY`, exact `[]`, zero component rows, `COMPONENT_INDEX_EMPTY`. |
| Parser applicability unresolved | Exact applicability/country status and null trusted country; historical technical evidence stays separate. |
| Unknown raw label | Exact row with `UNMAPPED_LABEL`, null SAFE component, and explicit counts. |
| Mapped parser evidence exists | `MAPPED_DEFINED_LABEL`; still `PARSER_EVIDENCE`, never verified. |
| Source representation absent | Explicit representation `ABSENT`, null candidate ID, no occurrence. |
| Giant candidate | Fully processed under the same statuses, or publication fails; never a semantic state. |

Stage 8 has no candidate-level scientific abstention because it makes no
semantic decision. It preserves upstream non-applicability/technical states
and exposes mechanical mapping coverage. Stage 9 and later stages must define
their own explicit prerequisite abstention without changing Stage 8.

## Synthetic and unit test plan

Implementation is not reviewable until tests cover:

1. exact field order, Arrow types, nullability, semantic-class metadata,
   schemas, mapping, vocabularies, and fingerprint determinism;
2. exact copy of every Stage 7 field and rejection of any mutation;
3. nonempty, empty, warning-present, warning-absent, and warning-not-evaluated
   combinations without semantic cross-classification;
4. missing, partial, invalid, conflicting, and unanimous-valid country
   provenance; unresolved country with preserved historical parse;
5. contiguous ordinals, duplicate labels, duplicate values, duplicate pairs,
   and exact nested-to-long-to-nested round trip;
6. all 20 pinned known labels, case-sensitive near misses, empty-string labels
   where upstream schema permits strings, and novel Unicode labels through the
   lossless unmapped path;
7. Unicode/native-script values, combining characters, embedded newlines,
   punctuation, empty values where allowed by the upstream string type, and
   very large strings without normalization;
8. synthetic byte/component giants under deliberately tiny byte-batch and
   shard limits, proving chunking, one-row groups, no truncation, and bounded
   resident state;
9. contiguous source-row ordinals, STANDARD-only, NATIVE-only, BOTH, absent
   representation, and same-row equal STANDARD/NATIVE mappings;
10. repeated provider `id` values with distinct stable source-row IDs;
11. candidate/source/component totality, foreign keys, occurrence-view counts,
    count reconciliation, and collision failure;
12. logical fingerprint invariance across input/output batch, row-group, and
    shard layouts, with sensitivity to value/order/status/mapping mutations;
13. exact Parquet schema/metadata and data reopen with page checksums;
14. fail-closed runtime/site/path/permission/publication/HOLDOUT/network gates;
15. static absence of pandas production transforms, web/API clients, Pelias,
    DeepParse, Senzing, pycountry, libaddressinput, geographic references,
    hypotheses, confidence scores, and semantic readiness fields; and
16. sanitized reporting that rejects candidate text, raw component values,
    source IDs/files, provider IDs, and other row-level data.

## DEVELOPMENT machine-validation plan and result

After a separately reviewed implementation and explicit job authorization,
submit one full DEVELOPMENT materialization on Goethe-NHR from an exact clean
pushed SHA. Do not launch a duplicate. Validate the immutable result in place.

The authoritative job must prove at minimum:

- 51,779 accepted candidate rows in and out;
- 51,774 nonempty and 5 empty technical results unchanged;
- 6,106,088 component-index rows and exact per-candidate nested reconstruction;
- maximum component count 881,338 processed without truncation;
- exact maximum candidate processed without truncation;
- 35,000 source-map rows, 69,747 occurrence-view rows, 34,822 STANDARD and
  34,925 NATIVE occurrences;
- zero missing/added/duplicate/cross-wired candidates or source rows;
- exact Stage 6 candidate/count preservation and exact Stage 7 schema/value
  preservation;
- exact Stage 7 applicability, technical, execution-origin, warning, reason,
  and signal distributions;
- mapped plus unmapped component counts equal 6,106,088, with a sanitized
  distinct-label/mapping-status profile and every unknown retained;
- raw nested/long reconstruction and occurrence-map logical fingerprints match
  an independent streaming recomputation;
- schema/contract/mapping/manifest/artifact hashes and permissions pass after
  reopen;
- parser calls, semantic corrections, hypotheses, reference lookups, network
  calls, protected inspection, HOLDOUT, production, Stage 9, and geocoding are
  all zero; and
- bounded-memory/resource evidence is consistent with the reviewed design.

No new qualitative address review is required for Stage 8 acceptance because
Stage 8 makes no semantic address claim. The fixed-500 identities may be used
only for machine lineage/reconstruction equality, not for opening or relabeling
protected values in this stage.

Repaired job `1763984` completed this machine-validation plan. All listed
counts, exact-input preservation, nested/long reversibility, map-back,
fingerprint, permission, privacy, resource, and zero-call requirements passed.
That execution evidence authorizes only fresh independent rereview, not Stage 8
acceptance or later-stage work.

## Independent-review plan

Independent review occurs only after the DEVELOPMENT candidate and sanitized
report are complete. A reviewer uses a clean exact candidate checkout and a
separate review harness to reopen the one immutable Stage 8 artifact; the
review does not rematerialize or alter it.

The reviewer independently verifies:

- the scientific boundary, taxonomy, schema, mapping, raw-label source pin,
  and absence of normalization/hypothesis/reference logic;
- exact Stage 6 and Stage 7 input bindings and file hashes;
- every candidate and source-map row, every raw nested component, every long
  ordinal/label/value/mapping row, and complete occurrence map-back using
  bounded streaming;
- unknown-label retention, duplicate/order preservation, giant handling,
  empty/unresolved/absent state separation, and zero trust claims;
- logical fingerprints independent of the materializer's reported values;
- artifact topology, permissions, immutability, source-control hygiene,
  privacy scans, tests, static analysis, and sanitized-report accuracy; and
- no Stage 9, HOLDOUT, production, parser, web service, or geocoding activity.

Independent evidence is aggregate/fingerprint-only. It is committed separately
and does not become scientific acceptance until the owner accepts the exact
reviewed candidate and integrates it without rewriting history.

## Acceptance criteria

Stage 8 DEVELOPMENT may become `STAGE_8_ACCEPTED` only when all are true:

1. implementation matches this exact purpose and boundary;
2. all frozen identities and fingerprints are present and exact;
3. all three schemas, field semantic classes, status vocabularies, mapping,
   ordering, and null semantics pass;
4. complete candidate/component/source/occurrence totality and exact upstream
   preservation pass;
5. raw nested-to-long reversibility, duplicates, unknown labels, Unicode,
   empty parses, unresolved country, absent representations, and giants pass;
6. no semantic readiness, correctness, confidence, validity, reference, or
   hypothesis field is present;
7. bounded-memory, runtime, SLURM guard, privacy, permissions, immutable
   publication, and sanitized-report gates pass;
8. local synthetic/unit/static checks pass;
9. one authorized full DEVELOPMENT artifact passes independent in-place
   validation and independent review; and
10. the owner explicitly accepts the exact candidate.

Zero unmapped labels is not required for losslessness. It may be reported, but
it cannot establish parser correctness. No acceptance criterion authorizes
Stage 9, production Stage 8, HOLDOUT, Pelias, or geocoding.

## Exact Stage 8 to Stage 9 handoff

An accepted Stage 9 design may read all three Stage 8 relations and their
manifest. It must receive every candidate and source row; it may not filter on
parser warning absence, mapping success, parser nonemptiness, or
representation type.

Stage 9 receives:

- the exact whole-string Stage 6 candidate and STANDARD/NATIVE source links;
- exact raw, accepted-clean, and accepted-lower source postcode, city, region,
  and country strings, kept distinct by derivation level;
- trusted source-country provenance/status as a separate context dimension;
- parser applicability and technical history;
- exact raw ordered parser evidence;
- optional one-to-one SAFE parser-evidence names and explicit unmapped labels;
- exact structural diagnostics; and
- all field semantic classes and upstream/artifact fingerprints.

For country-dependent work, Stage 9 must use trusted source-country provenance,
not the parser `PARSER_COUNTRY` component or parser-applicability status. Missing,
partial, invalid, or conflicting trusted-country provenance must fail closed or
receive an explicit Stage 9 prerequisite abstention. Stage 9 may add pinned
offline public reference/format evidence, including a separately reviewed role
for pycountry or libaddressinput. It must preserve `NOT_FOUND` as absence and
reserve `MISMATCH` for strong positive contradiction. It may not overwrite any
Stage 8 value or emit a geocoder query.

Hypothesis generation remains Stage 10. SAFE Pelias retrieval remains the
proposed Stage 12 and is still blocked by the repository's existing
pre-geocoding authorization rule. Stage 8 acceptance alone cannot advance any
of those stages.

## Design verdict and next task

The smallest coherent correction to the post-Stage-7 architecture is to keep
the Stage 8 name and number while narrowing it to lossless projection and a
mechanical parser-evidence index. Country-format/ISO lookup metadata moves to
Stage 9; hypotheses remain Stage 10. No broader renumbering is required.

Verdict:
`STAGE08_ADDRESS_EVIDENCE_IMPLEMENTATION_READY_FOR_CONTROLLED_DEVELOPMENT_REEXECUTION`.

Exact next action requiring separate owner authorization: **AUTHORIZE EXACTLY
ONE NEW CONTROLLED STAGE 8 DEVELOPMENT MATERIALIZATION AT THE NEW EXECUTABLE
SHA.** Do not submit it without that authorization, alter jobs `1763747` or
`1763984` or their artifacts, start Stage 9, or treat implementation readiness
as acceptance.
