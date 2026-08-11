# Phase 3 design — canonical address component table

## Status and authority

This corrected design is approved in principle but does **not** authorize Phase 3 implementation, the real-data pilot, a full-data transformation, Phase 4, address deduplication, `address_key` construction, geocoding, or SAFE/Pelias calls.

Phase 3 consumes only the immutable successful Phase 2 run:

`phase02_20260810T173851Z_1349152b`

That run contains 206 controlled Parquet shards and exactly 20,600,000 rows with lossless raw values and complete provenance. Phase 3 must never modify it.

## Responsibility and boundary

Phase 3 creates deterministic derived address components and parsing diagnostics. It preserves one core output row per Phase 2 row and retains uncertainty instead of maximizing component fill.

Phase 3 may:

- classify exact raw values as semantic missing, ambiguous placeholder-like, or content;
- normalize derived strings only under approved deterministic rules;
- create selected address components and native alternatives;
- retain candidate, provenance, raw-span, conflict, and evaluation evidence;
- create descriptive parse and completeness outcomes.

Phase 3 must not:

- overwrite or duplicate the authoritative role of Phase 2 raw values;
- create a canonical address string or `address_key`;
- deduplicate observations or addresses;
- choose a SAFE query or native/transliterated rescue strategy;
- determine geocoding readiness, final eligibility, or `usable_for_analysis`;
- geocode or begin Phase 4.

PO-box, historical, non-physical, company-only, completeness, and conflict fields produced here are descriptive parsing evidence. Phase 4 remains responsible for interpreting that evidence as geocoding readiness or eligibility.

## Architecture and products

```text
immutable successful Phase 2 shard
    -> verify manifest identity, output hash, schema, and page checksums
    -> bounded row transformation using frozen rules/references
    -> core component row (always exactly one per input row)
    -> zero or more sparse detailed-evidence rows
    -> write temporary core/evidence Parquet
    -> independent checksum and semantic-digest read-back
    -> atomic per-shard promotion
    -> exact dataset reconciliation
    -> dataset manifest and _SUCCESS written last
    -> STOP
```

### Product A — core component table

The core table contains exactly one row per Phase 2 row. It is optimized for Phase 4/5 joins and ordinary diagnostics. It stores selected components and compact selected-component provenance, not all competing candidate values.

### Product B — detailed evidence sidecar

The controlled evidence sidecar is sparse and keyed by `stable_source_row_id_v1`. It stores detailed evidence only where it adds audit value, including:

- ambiguity, conflicts, or multiple candidates;
- unassigned material content;
- ambiguous placeholder/reference collisions;
- selected values requiring nontrivial deterministic parsing;
- manual-review or pilot cases;
- source spans and supporting rules that do not fit compact core provenance.

Straightforward structured-field propagation needs only compact provenance in the core. The sidecar may therefore have no row for many observations.

### Why the split is preferred

| Concern | Single nested table | Core plus sparse evidence sidecar |
|---|---|---|
| One-row invariant | Preserved | Preserved in core |
| Auditability | Strong but carried on every row | Strong where needed; simple cases remain compact |
| Storage/compression | Repeated nested structures and candidate values | Repeated enums compress well; confidential values limited to sparse rows |
| Query ergonomics | Ordinary queries must traverse nested evidence | Phase 4/5 use the core; audits join the sidecar |
| Confidentiality | Candidate values spread across every main shard | Candidate values isolated in a separately protected product |
| Join complexity | Lower | One stable-ID join for detailed audits |
| Operational risk | Nested layout locked before evidence | Sidecar rate and size can be measured before full processing |

The split layout is recommended. The pilot must benchmark both the compact core and sidecar before any full Phase 3 run. Benchmark evidence includes sidecar rows per source row, bytes per source row, compression, write/read throughput, peak RSS, and stable-ID join latency.

## Placeholder policy

Use `placeholder_policy_v1`. Classification occurs on the exact Phase 2 raw string before NFC, whitespace transformation, trimming, case comparison, or reference lookup.

The policy applies only to the 12 address/geographic fields: the four non-native lines, four native lines, `postcode`, `city`, `region_in_country`, and `country_iso_code`. It does not reinterpret `id`, `batch_priority`, or `location_information`.

| Exact raw value | Semantic state | Candidate/selection behavior |
|---|---|---|
| `""` | `SEMANTIC_MISSING` | No candidate. |
| `"."` | `SEMANTIC_MISSING` | No candidate. |
| `"-"` | `SEMANTIC_MISSING` | No candidate. |
| `"Na"` | `AMBIGUOUS_PLACEHOLDER_LIKE` | May be retained as evidence; cannot populate a selected component without independent compatible evidence. |
| `"Nan"` | `AMBIGUOUS_PLACEHOLDER_LIKE` | Same. It is not automatically missing or meaningful. |
| `"Null"` | `AMBIGUOUS_PLACEHOLDER_LIKE` | Same. It is not automatically missing or meaningful. |
| Any other string | `CONTENT` | Eligible for safety checks and approved rules. |

Matching is whole-field and case-sensitive. Variants such as `null`, `NAN`, or ` Null ` are not members of this exact observed vocabulary; they remain content and receive a placeholder-variant diagnostic only if an exact registered diagnostic rule recognizes them. They must not silently become missing after normalization.

### Placeholder/reference collisions

An ambiguous placeholder-like token cannot become selected merely because normalization or case conversion makes it match a field reference.

For `country_iso_code`:

- exact uppercase assigned `NA` may be selected normally as Namibia;
- exact raw `Na` creates an ambiguous candidate/reference collision;
- `Na` alone cannot be case-normalized and selected as Namibia;
- compatible independent evidence, such as a separately supported `Namibia` country candidate from an address line, may corroborate `NA`;
- without corroboration, `country_clean` is null;
- incompatible independent evidence produces an ordinary country conflict.

This generalizes to any future collision between a placeholder-like literal and a valid code/name.

Exact related diagnostic values are:

- `AMBIGUOUS_PLACEHOLDER_LIKE_PRESENT`
- `PLACEHOLDER_REFERENCE_COLLISION_UNRESOLVED`
- `PLACEHOLDER_REFERENCE_COLLISION_CORROBORATED`
- `PLACEHOLDER_VARIANT_PRESENT`

## Derived normalization

Normalization applies only to bounded derived candidates. Phase 2 raw values remain unchanged.

| Transformation | Phase 3 v1 policy |
|---|---|
| Leading/trailing Unicode whitespace | Allowed on derived candidates. |
| Internal Unicode whitespace runs | Collapse to one U+0020 on derived candidates. |
| Unicode normalization | NFC only. |
| Controls/line separators | Replace with U+0020; never delete and concatenate neighbors. |
| Repeated punctuation cleanup | Deferred. |
| Comma cleanup | Deferred. |
| Hyphen/dash normalization | Deferred. |
| General casing changes | Deferred. Reference-rule comparison keys may use explicitly declared case behavior. |
| Abbreviation expansion | Deferred. |
| Spelling correction | Prohibited. |
| Accent removal | Prohibited. |
| Transliteration | Deferred. |
| General punctuation removal | Prohibited. |
| Country-specific transformations | Deferred until exact versioned rules and pilot evidence exist. |

The required order is placeholder classification, safety check, extraction from raw token spans, then candidate normalization. A normalized empty candidate becomes null, never an empty selected scalar.

## Python and Unicode version contract

NFC behavior is defined by the pinned Python runtime's `unicodedata` database, not an assumed external version.

The intended project command uses `python3`. On the design date it resolves to:

- Python `3.14.3`;
- `unicodedata.unidata_version == "16.0.0"`.

The proposed initial identifiers are therefore:

- `python_runtime_version = 3.14.3`;
- `unicode_runtime_version = 16.0.0`;
- `cleaning_rules_version = derived_text_nfc_ws_v1_ucd16.0.0`.

Implementation startup must assert the approved interpreter and `unicodedata.unidata_version` before reading Phase 2 data. A mismatch fails closed. The run manifest and every Parquet file's key-value metadata record both values; they are not additional row columns. A newer Unicode version is not adopted automatically.

If Script-property diagnostics are enabled, official Unicode `Scripts.txt` data from version 16.0.0 must be pinned and hashed before the pilot. Any additional Unicode data file must use the same release. Unicode source URLs, SHA-256 values, schemas, and the Unicode license note belong in the reference manifest.

## Native/non-native relationship model

Phase 3 v1 keeps the relationship vocabulary:

- `BOTH_SEMANTICALLY_MISSING`
- `NATIVE_ONLY`
- `NON_NATIVE_ONLY`
- `EXACT_EQUAL`
- `NFC_EQUAL`
- `SAME_SCRIPT_DIFFERENT`
- `DIFFERENT_SCRIPT`
- `MIXED_OR_UNDETERMINED`

Script determination is exact:

1. Look up every raw code point in pinned Unicode 16.0.0 `Scripts.txt`.
2. Ignore code points assigned `Common` or `Inherited` when building the distinctive-script set. They still remain in the raw string.
3. An empty distinctive-script set is `UNDETERMINED`.
4. One distinctive script is `SINGLE(<script property value>)`.
5. More than one distinctive script is `MIXED`.
6. Two different strings are `SAME_SCRIPT_DIFFERENT` only when both have the same single distinctive script.
7. They are `DIFFERENT_SCRIPT` only when each has one distinctive script and those scripts differ.
8. Every mixed or undetermined comparison is `MIXED_OR_UNDETERMINED`.

Exact equality is tested before NFC equality; script labels are used only when both tests fail. Script difference does not itself create an address conflict or prove transliteration equivalence.

## Safety coverage versus parse outcome

### Diagnostic evaluation status

`diagnostic_evaluation_status` has exactly three values:

- `FULLY_EVALUATED`: all eligible source fields were within operational limits and evaluated by all applicable rules.
- `PARTIALLY_SKIPPED_OVERSIZED`: at least one field was skipped for size, while at least one other safe address/geographic field was evaluated.
- `NOT_EVALUATED_OVERSIZED`: no address/geographic field could be safely evaluated beyond exact length/placeholder diagnostics.

Oversized rows also receive `OVERSIZED_INPUT`. Safe structured fields and safe lines remain usable by applicable rules. A large line never suppresses safe country, locality, region, postcode, or other safe-line evidence.

Initial configurable limits remain proposals requiring pilot measurement:

- 65,536 UTF-8 bytes per field for free-form rules;
- 262,144 UTF-8 bytes across free-form address lines;
- eight candidates per component;
- 64 candidates per row.

These are operational limits, not scientific invalidity thresholds. No raw value is truncated.

### Address parse status

`address_parse_status` contains no safety status:

- `PARSED`: supported selected address-level components exist and all evaluated material content is assigned or explicitly classified, with no ambiguity or conflict.
- `PARTIAL`: one or more components are selected, but evaluated material content or important roles remain unresolved.
- `AMBIGUOUS`: multiple supported alternatives prevent deterministic selection for at least one component.
- `CONFLICT`: supported evidence is incompatible for at least one component.
- `UNPARSEABLE`: evaluated semantic content exists, but no approved rule can structure it.
- `INSUFFICIENT`: evaluated content provides no address-level component beyond absent/coarse information.

Precedence is `CONFLICT`, `AMBIGUOUS`, then `PARSED`/`PARTIAL`, then `UNPARSEABLE`/`INSUFFICIENT`. Safety status is evaluated independently.

Completeness always describes components actually selected, including components derived from a partially evaluated row. It never becomes an unsafe class merely because a separate field was skipped.

## Completeness vocabulary

- `A_POINT_CORE_WITH_POSTCODE`: country + locality + street + house number + postcode.
- `B_POINT_CORE`: country + locality + street + house number without postcode.
- `C_STREET_LEVEL`: country + locality + street without house number.
- `D_LOCALITY_LEVEL`: country + locality without street or house number.
- `E_COUNTRY_ONLY`: country only among country/locality/street/house/building.
- `F_ADDRESS_WITH_GEOGRAPHY_GAPS`: street, house number, or building exists but country or locality is absent.
- `G_OTHER_PARTIAL`: at least one selected component exists and A–F do not apply.
- `Z_NO_COMPONENTS`: no component is selected.

There is no safety-specific completeness value. Completeness is diagnostic and does not determine querying or usability.

## Rule registry contract

All extraction, candidate, selection, diagnostic, and conflict behavior must come from a frozen rule registry. Implementation code may execute the registry but must not invent unregistered heuristics.

The registry contract requires: identical Phase 2 raw values and provenance + identical configuration + identical parser/rule/reference/runtime versions produce byte-identical candidates, confidence assignments, selections, flags, core rows, and evidence rows.

Each registry entry contains exactly:

| Field | Contract |
|---|---|
| `rule_id` | Stable uppercase identifier. |
| `rule_version` | Positive integer or immutable version string. |
| `execution_disposition` | Closed scientific execution role: `AUTHORITATIVE_SELECTABLE`, `AUTHORITATIVE_CANDIDATE_ONLY`, `AUTHORITATIVE_DIAGNOSTIC_ONLY`, or `DEVELOPMENT_SHADOW_ONLY`. |
| `component` | Approved component enum or diagnostic-only. |
| `representation` | `NON_NATIVE`, `NATIVE`, `SHARED`, or `ANY`. |
| `eligible_source_fields` | Ordered explicit field-name list. |
| `preconditions` | Exact Boolean predicates over semantic state, safety, prior candidates, and references. |
| `match_input` | `RAW_CODEPOINT_TOKENS`, `RAW_WHOLE_FIELD`, or another approved exact representation. |
| `comparison_normalization` | Exact comparison-key transformations; empty means none. |
| `matching_condition` | Fully specified token/character/reference condition. |
| `extraction_condition` | Exact raw span(s) emitted when matching succeeds. |
| `candidate_behavior` | Component/value/representation emitted and whether it is selectable or candidate-only. |
| `confidence` | Fixed `HIGH`, `MEDIUM`, or `LOW`; no computed score. |
| `selection_priority` | Unsigned integer; lower values run first. |
| `conflict_behavior` | Exact competing-candidate conditions and emitted conflict/diagnostic flags. |
| `maximum_input_utf8_bytes` | Hard applicability limit for this rule. |
| `reference_ids` | Ordered reference identifiers used, possibly empty. |
| `required_tests` | Golden positive, negative, boundary, Unicode, and false-positive test IDs. |

The current registry is canonical UTF-8 JSON conforming to `phase03_rule_registry_schema_v2`; arbitrary executable expressions and prose-only conditions are prohibited. `preconditions` use a closed expression tree with `ALL`, `ANY`, `NOT`, `EQ`, `IN`, `SEMANTIC_STATE_IS`, `EVALUATION_STATUS_IS`, and `CANDIDATE_COUNT` operators. `matching_condition` names a registered matcher plus typed parameters. `extraction_condition` names a registered extractor plus typed parameters. Matcher and extractor identifiers are part of `parser_version`; adding or changing one changes that version. Canonical registry serialization uses sorted object keys, preserves array order, encodes UTF-8 without ASCII escaping, and uses no insignificant whitespace before SHA-256 fingerprinting. Disposition participates in the canonical registry fingerprint and, together with explicit execution scope, in the effective parser/configuration fingerprint and manifests.

### Deterministic execution

1. Classify raw semantic state and safety.
2. Tokenize eligible raw fields while retaining raw spans.
3. Execute registry rules by `selection_priority`, then `rule_id` UTF-8 byte order.
4. Canonicalize equal candidates by exact normalized value, component, and representation.
5. Merge supporting sources/rules in registry order.
6. Select only when the highest-priority selectable candidate is unique and no registered conflict applies.
7. A tie between different values is ambiguity unless a rule explicitly defines it as conflict.
8. LOW candidates never populate selected scalar components in v1.

Execution scope is an explicit closed value: `DEVELOPMENT`, `LOCKED_EVALUATION`, or `AUTHORITATIVE`. `DEVELOPMENT_SHADOW_ONLY` rules execute only in `DEVELOPMENT`. Their candidates are isolated from authoritative selection, completeness, parse-status, diagnostic, and conflict calculations. They may write protected evidence-sidecar rows, but cannot populate core components or affect geocoding readiness. They are skipped entirely in `LOCKED_EVALUATION` and `AUTHORITATIVE` scope.

Confidence is a declared property of the rule path. It is not a numeric model score.

### Initial rule scope

Phase 3 v1 deliberately favors low recall. Initial selectable rules may include only:

- direct non-placeholder structured postcode, locality, and region propagation;
- exact country-reference validation/mapping under the collision policy;
- exact agreement of free-form evidence with a structured component;
- explicit marker rules listed below.

Concepts such as a "plausible street-bearing segment" are not implementation rules. The v1 house edge rule is measurement-only under `DEVELOPMENT_SHADOW_ONLY`; street extraction remains unsupported.

## Marker rule bundles

Every bundle is project-owned, versioned, and explicit. No bundle may be described as generally multilingual unless its languages and tokens are enumerated.

### Tokenization and boundary contract

- Raw source strings are indexed by Unicode code point.
- A word token is a maximal run whose Unicode general category begins with `L`, `M`, or `N`.
- Punctuation is a separate token; whitespace separates tokens.
- Marker comparison uses NFC on each token and ASCII lowercase only for ASCII registry tokens.
- Token comparison never changes the raw source span.
- A phrase matches complete consecutive tokens only.
- Extracted candidate text is the exact union of matched raw span(s), normalized only after extraction.

For v1, a marker `identifier` is exactly one following word token of 1–32 Unicode code points containing at least one `L` or `N` category code point. Joined or multi-token identifiers are unsupported unless a separate registry rule defines them. A building `identifier/name` is one to four following word tokens, contains at least one `L` or `N` code point, spans at most 64 raw code points, and stops before comma, semicolon, or line break. These deliberately narrow definitions prevent implementation-specific interpretations.

Registry marker phrases are stored as token arrays, not display strings. For example, `P.O. Box` is `['p', '.', 'o', '.', 'box']` after the declared ASCII comparison-key transform, while `PO Box` is `['po', 'box']`.

### English PO-box bundle `po_box_markers_en_v1`

Exact case-insensitive token sequences:

- `PO Box`
- `P.O. Box`
- `P O Box`
- `Post Office Box`

`Box` alone never matches. A marker must be followed by a non-empty identifier token. This rule emits a PO-box component/diagnostic, not a physical street.

### English unit bundle `unit_markers_en_v1`

Exact markers:

- `Apartment`, `Apt`, `Apt.`
- `Suite`, `Ste`, `Ste.`
- `Unit`
- `Room`, `Rm`, `Rm.`

A marker must be followed by one bounded identifier token. A bare number has no unit meaning.

### English floor bundle `floor_markers_en_v1`

Exact markers:

- `Floor`, `Fl`, `Fl.`
- `Level`, `Lvl`, `Lvl.`

The marker must be adjacent to one bounded identifier token. Ordinal recognition, if used, must be a separate exact registry rule.

### English building bundle `building_markers_en_v1`

Exact segment-leading markers:

- `Building`, `Bldg`, `Bldg.`
- `Block`
- `Tower`

The marker must start a trimmed segment and be followed by a non-empty identifier/name. An arbitrary phrase ending in "Building" is not selected by v1.

### Organization legal-form bundle `organization_legal_forms_v1`

Candidate-only exact segment-ending forms:

- `Ltd`, `Ltd.`, `Limited`
- `LLC`
- `Inc`, `Inc.`, `Incorporated`
- `Corporation`, `Corp`, `Corp.`
- `GmbH`
- `PLC`
- `Pte Ltd`
- `Co., Ltd.`

The segment must contain at least one earlier letter token. The rule creates an organization candidate at fixed MEDIUM confidence. It cannot by itself prove company-only status or remove text from a street candidate.

### Historical bundle `historical_markers_en_v1`

Diagnostic-only exact phrases:

- `former address`
- `previous address`
- `old address`
- `address until`
- `address valid until`

No other language or historical inference is claimed by v1. `location_information` values are not historical evidence.

Unsupported languages, abbreviations, and patterns remain unresolved. Adding a token changes the applicable rule/bundle version and requires positive and false-positive tests.

## Component strategies

### Postcode

The raw postcode remains the exact Phase 2 `postcode`; it is not duplicated as a raw Phase 3 column. `postcode_clean` remains a nullable Arrow string.

Approved behavior is minimal only:

- apply the approved derived NFC/whitespace normalization after extraction;
- preserve leading zeros, letters, case, spaces, hyphens, decimal points, and other punctuation;
- never route a postcode through integer, decimal, or floating-point conversion;
- never infer a country or locality from postcode shape;
- do not apply country-specific formatting or validation in v1.

A safe non-placeholder structured postcode is selectable at rule-assigned HIGH confidence. An ambiguous placeholder-like postcode is not selectable without independent exact corroboration. A free-form postcode is candidate-only unless an explicit registered postal-code marker identifies it or it exactly confirms the structured postcode.

### Street and house number

Address lines are classified independently; they are not concatenated before rule execution. Phase 3 does not assume that any line position is a street.

No selectable Phase 3 v1 rule may depend on an undefined concept such as "plausible street-bearing content." `HOUSE_NUMBER_EDGE_CANDIDATE_V1` retains its exact current grammar but has disposition `DEVELOPMENT_SHADOW_ONLY`. On the future development subset only, it may emit LOW protected evidence candidates for bounded leading/trailing number tokens, alphanumeric tokens, ranges, and slash/hyphen forms. It never populates `house_number_clean` or `street_clean`, changes completeness or parse status, creates core conflicts solely from its candidate, or affects readiness. It is prohibited from locked-evaluation and authoritative execution.

Until such promotion is pre-registered and passes locked evaluation:

- no bare numeric token becomes `house_number_clean`;
- no residual line becomes `street_clean` by position alone;
- ambiguity is retained in the evidence sidecar;
- low recall and null street/house fields are valid outcomes.

Fill rate can never justify promotion. Development review must separately measure ordinary edge integers, alphanumeric edge tokens, numeric ranges, slash forms, hyphen forms, calendar-like false positives, postcode-like false positives, unit/floor collisions, and country/script cohorts where enough examples exist. Any selectable successor must have a new rule ID/version; V1 is never mutated into a selectable rule.

If a future selectable rule removes an extracted house-number span from a street candidate, both source spans and the exact rule IDs must be retained. The normalized street and house values must each be reproducible from their raw spans.

### Unit, floor, and building

Explicit marker rules in the enumerated English bundles are selectable at fixed HIGH confidence only when their exact marker, boundary, identifier, source-field, and size preconditions hold. A bare number is never assigned a role. Competing unit/house/postcode roles produce ambiguity or the registered role-conflict flag.

Unit, floor, and building values remain separate even though later Phase 5 may exclude unit/floor from a building-level address key. Phase 3 does not make that key decision.

### Locality and region

A safe source `city` or `region_in_country` value in semantic state `CONTENT` is selectable through direct structured propagation at fixed HIGH confidence unless a registered conflict applies. Ambiguous placeholder-like values require independent exact corroboration.

Free-form locality or region content may be selected only by:

- an exact registered explicit label rule; or
- exact agreement with a safe structured value.

An arbitrary trailing token is never a locality/region. Phase 3 v1 introduces no locality gazetteer or administrative-boundary database. Unsupported free-form geography remains an unselected candidate or unassigned material content.

### Organization and venue

The v1 legal-form bundle emits candidate-only organization evidence at fixed MEDIUM confidence. It cannot automatically populate `street_clean`, remove a line from street consideration, or prove that a row is company-only.

`organization_clean` may be selected only after a separate registry rule establishes a unique organization candidate and no registered building/organization conflict applies. A first line is never an organization merely because it is first. Unsupported venue/company patterns remain unresolved.

### Native alternatives

Native and non-native address lines execute the same eligible rule definitions with different `representation` values. They are never concatenated. Selected native components populate only native scalar columns. Structured postcode/city/region/country fields are `SHARED` evidence unless a rule explicitly establishes another representation.

Different native/non-native values are not automatically conflicts. A conflict requires a registered comparison of deterministically comparable values, such as incompatible selected house numbers, postcodes, or ISO country codes.

### PO box, historical, and non-physical diagnostics

The four core booleans are nullable because an oversized skipped field can prevent full evaluation:

- `is_po_box = true` only for the exact PO-box rule bundle with a following identifier;
- `is_historical = true` only for an exact historical marker rule;
- `probable_non_physical_address = true` for a selected PO-box result in v1; other virtual/mail-only concepts are unsupported until separately registered;
- `possible_company_only = true` only when organization evidence exists and no street, house number, building, postcode, or locality is selected from evaluated fields.

False means every applicable eligible field was evaluated and no registered evidence matched. Null means the diagnostic could not be fully evaluated. These booleans are not Phase 4 eligibility decisions.

## Country reference abstraction

Country processing uses explicit reference manifests rather than reconstructed code lists.

Every reference entry contains:

- `reference_id`;
- an explicit normative or operational authority role;
- source organization and URL;
- retrieval timestamp and stated vintage;
- media type and exact source SHA-256;
- loading schema version and field mapping;
- license/terms note;
- redistribution policy;
- controlled local relative path or external controlled-artifact identity.

Normative ISO authority and operational CLDR mapping remain separate:

- ISO 3166 and its Maintenance Agency define the normative code system.
- Pinned Unicode CLDR 46.1 supplies the reproducible machine-readable alpha-2,
  alpha-3, numeric-code, and canonical English-name mapping.
- CLDR does not silently replace ISO as the normative authority.

The active sources are the official ISO 3166 overview
(`https://www.iso.org/iso-3166-country-codes.html`), the versioned CLDR 46.1
release (`https://www.unicode.org/Public/cldr/46.1/`), and the matching Unicode
16.0.0 UCD Scripts file
(`https://www.unicode.org/Public/16.0.0/ucd/Scripts.txt`). UNSD M49 is a
superseded historical candidate and is not an active Phase 3 v1 dependency.

If ISO redistribution terms prevent vendoring, the controlled data remains outside Git. Git contains only the manifest schema, source description, expected digest, and loader contract. Exact files and digests must be pinned before the pilot. No codes are recreated from memory.

Country selection methods are:

- `STRUCTURED_ALPHA2_EXACT`
- `STRUCTURED_ALPHA2_CASE_NORMALIZED`
- `STRUCTURED_ALPHA3_EXACT`
- `STRUCTURED_COUNTRY_NAME_EXACT`
- `FREEFORM_ALPHA2_EXACT`
- `FREEFORM_ALPHA3_EXACT`
- `FREEFORM_COUNTRY_NAME_EXACT`
- `MULTISOURCE_AGREEMENT`
- `MULTISOURCE_CORROBORATED_PLACEHOLDER_COLLISION`
- `CONFLICT`
- `UNRESOLVED`

Case-normalized lookup is prohibited for `AMBIGUOUS_PLACEHOLDER_LIKE` input unless independent compatible evidence invokes the corroborated-collision method.

`country_input_class` uses only:

- `SEMANTIC_MISSING`
- `AMBIGUOUS_PLACEHOLDER_LIKE`
- `ALPHA2_ASSIGNED_EXACT`
- `ALPHA2_CASE_VARIANT`
- `ALPHA3_ASSIGNED_EXACT`
- `COUNTRY_NAME_EXACT`
- `REGION_LIKE`
- `UNKNOWN_TEXT`

Country confidence uses only `HIGH`, `MEDIUM`, `LOW`, and `UNRESOLVED`. Every confidence is assigned by the rule registry; there is no numeric confidence calculation.

The component enum is exactly `STREET`, `HOUSE_NUMBER`, `UNIT`, `FLOOR`, `BUILDING`, `ORGANIZATION`, `POSTCODE`, `LOCALITY`, `REGION`, `COUNTRY`, and `PO_BOX`. Representation is exactly `NON_NATIVE`, `NATIVE`, or `SHARED` in outputs; `ANY` is allowed only in registry applicability. Eligible source fields are limited to the 12 exact Phase 2 address/geographic field names.

## Core component schema

The recommended core schema has 52 columns. All selected component strings are nullable; null means absent, unresolved, ambiguous, or conflicting. Selected component strings must never be empty. All list columns are non-null and use an empty list when no value applies.

| Pos. | Column | Arrow type | Nullability |
|---:|---|---|---|
| 1 | `stable_source_row_id_v1` | `fixed_size_binary[32]` | non-null |
| 2 | `id` | `string` | non-null |
| 3 | `source_file` | `string` | non-null |
| 4 | `source_logical_record_number` | `uint64` | non-null |
| 5 | `source_file_sha256` | `fixed_size_binary[32]` | non-null |
| 6 | `street_clean` | `string` | nullable |
| 7 | `house_number_clean` | `string` | nullable |
| 8 | `unit_clean` | `string` | nullable |
| 9 | `floor_clean` | `string` | nullable |
| 10 | `building_clean` | `string` | nullable |
| 11 | `organization_clean` | `string` | nullable |
| 12 | `postcode_clean` | `string` | nullable |
| 13 | `locality_clean` | `string` | nullable |
| 14 | `region_clean` | `string` | nullable |
| 15 | `country_clean` | `string` | nullable |
| 16 | `street_native_clean` | `string` | nullable |
| 17 | `house_number_native_clean` | `string` | nullable |
| 18 | `unit_native_clean` | `string` | nullable |
| 19 | `floor_native_clean` | `string` | nullable |
| 20 | `building_native_clean` | `string` | nullable |
| 21 | `organization_native_clean` | `string` | nullable |
| 22 | `locality_native_clean` | `string` | nullable |
| 23 | `region_native_clean` | `string` | nullable |
| 24 | `country_native_clean` | `string` | nullable |
| 25 | `country_input_class` | `string` enum | non-null |
| 26 | `country_parse_method` | `string` enum | non-null |
| 27 | `country_parse_confidence` | `string` enum | non-null |
| 28 | `address_parse_status` | `string` enum | non-null |
| 29 | `address_completeness_class` | `string` enum | non-null |
| 30 | `address_conflict_flags` | `list<string>` | non-null |
| 31 | `address_diagnostic_flags` | `list<string>` | non-null |
| 32 | `postcode_diagnostic_flags` | `list<string>` | non-null |
| 33 | `selected_component_provenance` | `list<struct>` | non-null |
| 34 | `native_non_native_relationships` | `list<struct>` | non-null |
| 35 | `diagnostic_evaluation_status` | `string` enum | non-null |
| 36 | `skipped_oversized_fields` | `list<string>` | non-null |
| 37 | `is_po_box` | `boolean` | nullable |
| 38 | `is_historical` | `boolean` | nullable |
| 39 | `probable_non_physical_address` | `boolean` | nullable |
| 40 | `possible_company_only` | `boolean` | nullable |
| 41 | `input_max_field_utf8_bytes` | `uint64` | non-null |
| 42 | `parser_version` | `string` | non-null |
| 43 | `rule_registry_version` | `string` | non-null |
| 44 | `cleaning_rules_version` | `string` | non-null |
| 45 | `placeholder_policy_version` | `string` | non-null |
| 46 | `country_reference_version` | `string` | non-null |
| 47 | `unicode_reference_version` | `string` | non-null |
| 48 | `diagnostic_vocabulary_version` | `string` | non-null |
| 49 | `component_schema_version` | `string` | non-null |
| 50 | `phase03_version` | `string` | non-null |
| 51 | `configuration_fingerprint` | `fixed_size_binary[32]` | non-null |
| 52 | `implementation_fingerprint` | `fixed_size_binary[32]` | non-null |

`selected_component_provenance` has struct-field order:

1. `component: string non-null`;
2. `representation: string non-null`;
3. `source_fields: list<string> non-null`;
4. `rule_ids: list<string> non-null`;
5. `confidence: string non-null`.

It contains selected components only. Entries use approved component order, then representation order. Source fields use the Phase 2 schema order. Rule IDs use registry execution order.

`native_non_native_relationships` has `line_number: uint8 non-null` followed by `relationship: string non-null`, ordered by line number 1–4.

## Detailed evidence sidecar schema

The sidecar is a long sparse table. A candidate supported by multiple raw spans uses multiple rows with the same `evidence_id` and increasing `span_ordinal`.

| Pos. | Column | Arrow type | Nullability |
|---:|---|---|---|
| 1 | `stable_source_row_id_v1` | `fixed_size_binary[32]` | non-null |
| 2 | `source_file` | `string` | non-null |
| 3 | `source_logical_record_number` | `uint64` | non-null |
| 4 | `evidence_id` | `uint32` | non-null |
| 5 | `span_ordinal` | `uint16` | non-null |
| 6 | `evidence_kind` | `string` enum | non-null |
| 7 | `component` | `string` enum | nullable |
| 8 | `representation` | `string` enum | nullable |
| 9 | `candidate_value` | `string` | nullable |
| 10 | `selected` | `boolean` | non-null |
| 11 | `confidence` | `string` enum | nullable |
| 12 | `rule_id` | `string` | nullable |
| 13 | `source_field` | `string` enum | non-null |
| 14 | `start_character` | `uint64` | non-null |
| 15 | `end_character_exclusive` | `uint64` | non-null |
| 16 | `conflict_flag` | `string` enum | nullable |
| 17 | `diagnostic_flag` | `string` enum | nullable |
| 18 | `parser_version` | `string` | non-null |
| 19 | `rule_registry_version` | `string` | non-null |
| 20 | `phase03_version` | `string` | non-null |

Evidence-kind vocabulary:

- `SELECTED_NONTRIVIAL_COMPONENT`
- `UNSELECTED_CANDIDATE`
- `COMPETING_CANDIDATE`
- `CONFLICTING_EVIDENCE`
- `UNASSIGNED_MATERIAL_CONTENT`
- `AMBIGUOUS_PLACEHOLDER`
- `MANUAL_REVIEW_CONTEXT`

Conditional sidecar invariants are exact:

- candidate-related kinds require non-null `component`, `representation`, `candidate_value`, `confidence`, and `rule_id`;
- `selected=true` is allowed only for `SELECTED_NONTRIVIAL_COMPONENT`;
- `CONFLICTING_EVIDENCE` requires `conflict_flag`;
- `AMBIGUOUS_PLACEHOLDER` requires `diagnostic_flag=AMBIGUOUS_PLACEHOLDER_LIKE_PRESENT`;
- every row refers to one valid non-empty raw span; whole-field evidence uses `[0, raw_codepoint_length)`;
- all rows sharing a source-row `evidence_id` have identical evidence/candidate fields other than `source_field`, span offsets, and `span_ordinal`.

Within a source row, evidence groups are sorted by evidence-kind vocabulary order, approved component order with null last, representation order with null last, candidate UTF-8 bytes with null first, rule-registry order with null last, then ordered raw spans. `evidence_id` is one-based in that order. Spans within a group are sorted by Phase 2 source-field order, `start_character`, then `end_character_exclusive`; `span_ordinal` is one-based. These rules make evidence identifiers and row ordering reproducible.

Sidecar rows are ordered within each source shard by `source_logical_record_number`, `evidence_id`, and `span_ordinal`. Candidate values and raw spans are confidential. Parquet statistics and dictionary encoding are disabled for `candidate_value`, stable IDs, source row numbers, and span offsets where metadata exposure would be inappropriate.

## Raw source-span contract

Every source span means:

```text
source_field raw_value[start_character:end_character_exclusive]
```

where:

- offsets are zero-based Unicode code-point indices;
- the indexed value is the exact non-null Phase 2 raw string;
- the end is exclusive;
- offsets are determined before NFC, whitespace collapse, control replacement, trimming, or case comparison;
- spans never refer to UTF-8 byte offsets or normalized-string positions;
- multiple non-contiguous or cross-field pieces produce multiple sidecar span rows.

Rules tokenize raw strings and retain raw offsets. Comparison keys may normalize token text as declared by the registry, but extraction always slices the original raw string and normalizes the resulting candidate afterward.

Required golden span tests cover:

- leading whitespace with a selected inner token;
- multiple internal whitespace code points collapsed in the candidate;
- decomposed text that composes under NFC;
- a quoted multiline raw field;
- a candidate made from multiple spans;
- astral-plane Unicode proving code-point rather than UTF-16/byte indexing.

## Conflict and diagnostic vocabularies

`address_conflict_flags` uses only:

- `COUNTRY_SOURCE_CONFLICT`
- `COUNTRY_MULTIPLE_CANDIDATES`
- `POSTCODE_SOURCE_CONFLICT`
- `POSTCODE_MULTIPLE_CANDIDATES`
- `LOCALITY_SOURCE_CONFLICT`
- `LOCALITY_MULTIPLE_CANDIDATES`
- `REGION_SOURCE_CONFLICT`
- `REGION_MULTIPLE_CANDIDATES`
- `STREET_MULTIPLE_CANDIDATES`
- `HOUSE_NUMBER_MULTIPLE_CANDIDATES`
- `HOUSE_NUMBER_POSTCODE_ROLE_CONFLICT`
- `UNIT_HOUSE_NUMBER_ROLE_CONFLICT`
- `BUILDING_ORGANIZATION_ROLE_CONFLICT`
- `COMPONENT_SPAN_OVERLAP_CONFLICT`
- `NATIVE_NON_NATIVE_HOUSE_NUMBER_CONFLICT`
- `NATIVE_NON_NATIVE_POSTCODE_CONFLICT`
- `NATIVE_NON_NATIVE_COUNTRY_CONFLICT`

`address_diagnostic_flags` uses only:

- `STRUCTURED_GEOGRAPHY_MISSING_FREEFORM_PRESENT`
- `COUNTRY_STRUCTURED_UNRECOGNIZED`
- `COUNTRY_STRUCTURED_REGION_LIKE`
- `POSTCODE_FREEFORM_PRESENT`
- `AMBIGUOUS_PLACEHOLDER_LIKE_PRESENT`
- `PLACEHOLDER_REFERENCE_COLLISION_UNRESOLVED`
- `PLACEHOLDER_REFERENCE_COLLISION_CORROBORATED`
- `PLACEHOLDER_VARIANT_PRESENT`
- `UNASSIGNED_CONTENT_PRESENT`
- `NATIVE_ONLY_CONTENT`
- `NON_NATIVE_ONLY_CONTENT`
- `NATIVE_NON_NATIVE_TEXT_DIFFERENT`
- `PROBABLE_ORGANIZATION_TEXT`
- `PO_BOX_EVIDENCE`
- `HISTORICAL_EVIDENCE`
- `PROBABLE_NON_PHYSICAL`
- `POSSIBLE_COMPANY_ONLY`
- `OVERSIZED_INPUT`
- `CANDIDATE_LIMIT_EXCEEDED`

`postcode_diagnostic_flags` uses only:

- `POSTCODE_SOURCE_EMPTY`
- `POSTCODE_SEMANTIC_MISSING`
- `POSTCODE_AMBIGUOUS_PLACEHOLDER_LIKE`
- `POSTCODE_DIGITS_ONLY`
- `POSTCODE_LEADING_ZERO`
- `POSTCODE_DECIMAL_LOOKING`
- `POSTCODE_ALPHABETIC`
- `POSTCODE_ALPHANUMERIC`
- `POSTCODE_CONTAINS_WHITESPACE`
- `POSTCODE_CONTAINS_HYPHEN`
- `POSTCODE_OTHER`
- `POSTCODE_FREEFORM_PRESENT`
- `POSTCODE_NORMALIZED_WHITESPACE`

Lists are deduplicated and stored in the ordinal order defined by `diagnostic_vocabulary_v1`, never arbitrary set or locale order.

## Phase 3 semantic integrity

Phase 3 defines separate core and evidence digests plus a binding dataset digest.

### Binary primitives

- `U16`, `U32`, `U64`: unsigned big-endian integers of the stated width.
- `LP(bytes)`: `U64(byte_length) || bytes`.
- Strings: exact UTF-8 bytes.
- Enums: serialized as their exact registered string values.

Type encodings are:

- null: `0x00`;
- non-null string/enum: `0x01 || LP(UTF-8)`;
- false: `0x02`;
- true: `0x03`;
- `uint8`: `0x10 || one byte`;
- `uint16`: `0x11 || U16(value)`;
- `uint32`: `0x12 || U32(value)`;
- `uint64`: `0x13 || U64(value)`;
- fixed binary: `0x20 || LP(raw bytes)`;
- list: `0x30 || U64(element_count) || encoded elements`;
- struct: `0x40 || U64(field_count) || encoded fields in declared schema order`.

Empty string and empty list are non-null and distinct from null. Struct field names are bound through the schema header and values are serialized in declared order.

### `phase03_core_semantic_digest_v1`

Hash with SHA-256:

1. UTF-8 domain `safe_geocoding_pipeline:phase03_core_semantic_digest_v1\0`.
2. `LP(UTF-8 component_schema_version)`.
3. `U64(52)`.
4. `LP(UTF-8 column name)` for every core column in the exact schema order above.
5. For each core row in Phase 2 source order: byte `0x52`, `U64(one-based row ordinal within the shard)`, then all 52 encoded values.
6. Footer byte `0x46 || U64(core_row_count)`.

### `phase03_evidence_semantic_digest_v1`

Hash with SHA-256:

1. UTF-8 domain `safe_geocoding_pipeline:phase03_evidence_semantic_digest_v1\0`.
2. `LP(UTF-8 evidence schema version)`.
3. `U64(20)`, followed by `LP(UTF-8 column name)` for every evidence column in declared order.
4. Evidence rows sorted by source logical record number, evidence ID, and span ordinal: `0x52`, `U64(one-based evidence-row ordinal)`, then all 20 encoded values.
5. Footer `0x46 || U64(evidence_row_count)`.

An empty sidecar shard still has the domain, schema header, and zero-row footer.

### `phase03_dataset_semantic_digest_v1`

Hash with SHA-256:

1. UTF-8 domain `safe_geocoding_pipeline:phase03_dataset_semantic_digest_v1\0`.
2. `LP(UTF-8 phase03_version)` followed immediately by the raw 32-byte configuration fingerprint.
3. `U64(shard_count)`.
4. For every shard in exact Phase 2 manifest path order: byte `0x53`, `LP(UTF-8 relative source path)`, raw 32-byte core digest, `U64(core rows)`, raw 32-byte evidence digest, `U64(evidence rows)`.
5. Footer `0x46 || U64(total core rows) || U64(total evidence rows)`.

Source-path, list, struct, and evidence ordering are deterministic. The independent Parquet read-back path recomputes both per-shard digests. The dataset digest is calculated only from validated per-shard values. Reports use lowercase hex only for display.

This digest is separate from Phase 2 `raw_semantic_digest_v1`.

## Atomicity, restart, and layout

Recommended immutable layout:

```text
derived/controlled/phase03_v1/runs/<run_id>/
  core/*.parquet
  evidence/*.parquet
  .in_progress/
  _work/phase03.sqlite3
  dataset_manifest.json
  _SUCCESS.json

reports/generated/phase03/<run_id>/
  phase03_run.json
  phase03_file_validation.csv
  phase03_schema.json
  phase03_reconciliation.json
  phase03_profile.json
  phase03_failures.csv.gz
  phase03_summary.md
```

Core preserves one output shard per Phase 2 shard. Evidence uses at most one sparse Parquet shard per Phase 2 shard; an empty evidence shard may be represented by a validated zero-row file so file-set reconciliation remains simple.

Temporary files are written on the final filesystem, independently read and validated, then atomically promoted. Completed shards are reusable only when Phase 2 input identity, implementation/configuration fingerprints, rule/reference versions, and output hashes match. `_SUCCESS.json` is written last.

## Processing and performance

The recommended stack remains Python, PyArrow 25.0.0, DuckDB 1.5.5 for completed-output reconciliation only, SQLite for run state, and `hashlib` for digests. No pandas, Spark, Dask, or external row-by-row service is required.

Deterministic project rules are authoritative. libpostal is not part of the production design. A separately pinned libpostal build/model may be evaluated only as a secondary, unselected candidate generator on the development pilot if explicitly approved. Its software is MIT-licensed, but its statistical model/training sources and multi-gigabyte data introduce separate version, licensing, portability, and audit risks; it does not provide project-approved confidence and cannot verify that a string is a valid physical address. Any experiment must record the exact source commit, binary/platform identity, model/data hashes, and returned labels, and must never process oversized fields or externalize confidential data.

An eventual production run requires one logical Phase 2 transformation pass. All core/evidence outputs, counters, and source-side digests are produced together. Independent output read-back and a completed-Parquet reconciliation are additional output passes, not repeated Phase 2 transformations.

Process one source-aligned shard at a time in bounded batches. Inspect Arrow offsets before materializing extreme values. Candidate caps prevent combinatorial expansion. Initial batch, row-group, and compression settings remain provisional until the development pilot benchmarks the two-product layout.

## Validation and reconciliation

Per-shard PASS requires:

- exact successful Phase 2 run identity, input hash, schema, and checksum validation;
- 100,000 input and core rows in exact source order;
- zero missing or duplicate stable/provider IDs;
- exact 52-column core and 20-column evidence schemas;
- only approved rule, enum, provenance, status, conflict, and diagnostic values;
- every selected component supported by compact core provenance;
- detailed evidence required by the sidecar inclusion policy present and span-valid;
- raw source spans within the referenced field's code-point length;
- exact Python/Unicode/rule/reference/configuration versions;
- independent core/evidence semantic-digest equality;
- page-checksum verification and output SHA-256 recording;
- no confidential value in logs or portable reports.

Dataset PASS requires 206 validated core shards, exactly 20,600,000 core rows, exact identity reconciliation to Phase 2, one approved schema, validated evidence shard/file policy, no failed/incomplete output, and a matching dataset semantic digest. The number of evidence rows is measured, not predeclared.

`PARSED`, `PARTIAL`, `AMBIGUOUS`, `CONFLICT`, `UNPARSEABLE`, and `INSUFFICIENT` are valid data outcomes. Partial or skipped oversized evaluation is also a valid data outcome. Row loss, nondeterminism, unregistered rules, version mismatch, invalid spans, digest mismatch, or incomplete artifacts are pipeline failures.

## Synthetic tests

Required fictional fixtures cover:

- Western-style street and number, number-after-street, alphanumeric number, range, and slash/hyphen number; these remain candidate-only until their exact development rules are promoted;
- apartment, suite, unit, room, floor, level, building, block, and tower markers with positive and false-positive boundaries;
- company legal form before a separately represented address, company-only content, and building/organization ambiguity;
- locality in line 3/4 with an exact explicit marker, the same text without the marker, postcode/country in free-form text, and missing structured geography;
- structured/free-form country, postcode, locality, and region agreement/conflict;
- leading-zero, alphanumeric, decimal-looking, spaced, and hyphenated postcode strings with exact preservation;
- Unicode/non-Latin, native-only, non-native-only, exact-equal, NFC-equal, same-script-different, different-script, and mixed-script values;
- blank, country-only, ambiguous numeric, PO-box, historical, and probable company-only rows;
- ordinary multiline text and extreme unsafe input without committed large fixtures.

Corrected contract tests additionally include:

- `Na` alone in `country_iso_code` cannot select Namibia;
- exact `NA` can select Namibia through the assigned-code rule;
- raw `Na` plus independent exact Namibia evidence can select `NA` with collision-corroboration provenance;
- `Na` plus a conflicting country candidate becomes conflict;
- `Nan` and `Null` remain ambiguous placeholder-like without corroboration;
- runtime Unicode mismatch fails before input processing;
- NFC golden behavior is tied to Unicode 16.0.0;
- Common/Inherited-only, single-script, same-script-different, different-script, and mixed-script strings follow the exact script algorithm;
- one oversized line plus safe structured geography yields selected safe components, partial evaluation, and an ordinary parse/completeness result;
- all-fields-oversized yields `NOT_EVALUATED_OVERSIZED` without row loss;
- rule registry ordering, fixed confidence, candidate-only behavior, ties, and conflicts are deterministic;
- every marker has positive, negative, substring, boundary, and false-positive tests;
- raw spans survive leading whitespace, collapsed whitespace, NFC composition, multiline input, and multiple spans;
- core/evidence digest golden vectors distinguish null, empty string, empty list, ordering, Unicode, and struct-field order;
- candidate/evidence reorder changes the digest;
- sparse sidecar omission of a required audit row fails validation;
- no candidate value leaks into statistics, logs, or generated reports.

Large unsafe fixtures are generated temporarily and are not committed.

## Real-data pilot and locked evaluation

No pilot is authorized by this document.

The pilot remains approximately 12,000 deterministically selected rows. Proposed seed domain is `safe_geocoding_pipeline:phase03_pilot_v1:seed:1`; selection uses the lowest SHA-256 values over the domain and raw `stable_source_row_id_v1`.

Sampling uses overlapping, independently quota-controlled strata rather than a sparse full Cartesian product:

- country: largest cohorts, medium cohorts, rare/small cohorts, missing, and unusual/non-standard input;
- script: ASCII, single distinctive Latin, single distinctive non-Latin, mixed, and undetermined under the pinned script algorithm;
- structured completeness: highly complete, partial, sparse, and empty;
- postcode: missing, leading-zero, alphanumeric, decimal-looking, and other lexical patterns;
- country field: exact assigned alpha-2, missing, ambiguous placeholder-like, and unusual/unrecognized;
- source status: `previous_geocoding_failure`, `no_geocoding_information`, and `region_interpolated`;
- native relationship: exact, NFC-equal, different, native-only, and non-native-only where available;
- address lines: one through four populated lines, unit/building/company candidates, no number, PO box, and unsafe/extreme.

Use a minimum target of 50 where a primary stratum contains at least 50 rows, include all available rows below that threshold, and cap an exact primary stratum at 500 before de-duplication. Known Phase 1 extreme/multiline rows are targeted safety cases outside normal quotas. The union is de-duplicated by stable ID and deterministically filled/trimmed to the target without allowing one large country cohort to dominate.

### Sequence

1. **Select and seal sample v1:** assign 8,000 development and 4,000 locked evaluation rows deterministically. Evaluation identities are access-controlled and not inspected during development.
2. **Development pilot:** run and inspect only the 8,000 development rows. Rules, marker lists, confidence assignments, sidecar inclusion policy, and operational settings may be revised with new versions.
3. **Development manual review:** review approximately 800 protected development rows and measure component precision, missed information, overreach, conflict behavior, and evidence-sidecar performance.
4. **Freeze:** finalize parser version, rule registry, placeholder policy, country/Unicode references, normalization, schemas, evidence inclusion rules, metrics, and implementation/configuration fingerprints.
5. **Pre-register thresholds:** choose and record quantitative acceptance thresholds using development evidence only. Thresholds are fixed before the locked evaluation is opened.
6. **Locked evaluation:** run the frozen authoritative implementation on the 4,000 evaluation rows and manually review approximately 400 protected rows. Development-shadow rules do not execute and evaluation identities remain sealed until this step.
7. **PASS or REVISE:** compare locked results with pre-registered thresholds. Do not tune against the locked results.
8. **Revision consequence:** any methodological defect requiring a rule/policy/reference/schema change after locked evaluation yields `FAIL/REVISE`, a new parser/rule/configuration version, and a newly selected and sealed locked-evaluation sample/version. The same locked sample is never used to tune and certify a revision.

Evidence-sidecar benchmarking is mandatory during development and locked evaluation. No full run is approved until storage, compression, memory, throughput, privacy metadata, and join ergonomics are reviewed.

### Manual-review labels and metrics

Approximately 1,200 pilot rows are manually reviewed: about 800 development and 400 locked evaluation. At least 25% are independently double-reviewed, with separate reviewer labels and adjudication reason codes.

Reviewers see protected Phase 2 inputs, Phase 3 selected components, compact provenance, sidecar candidates/spans, conflicts, parse/completeness, and safety status under a hashed review ID. Labels cover component correctness, organization/building/unit role, conflict detection, parser overreach, missed extractable information, unsafe handling, and overall structuring acceptability.

`manual_review_reason_codes_v1` is closed, multi-valued, and stored in canonical registry order with duplicates removed. Unknown codes fail validation. Its exact codes are: `CORRECT_AS_IS`, `SOURCE_AMBIGUOUS`, `INSUFFICIENT_SOURCE_EVIDENCE`, `WRONG_COMPONENT_ROLE`, `WRONG_VALUE`, `WRONG_SPAN_BOUNDARY`, `FALSE_POSITIVE_EXTRACTION`, `MISSED_EXTRACTABLE_COMPONENT`, `WRONG_NORMALIZATION`, `WRONG_PROVENANCE`, `WRONG_CONFLICT_DETECTION`, `MISSED_CONFLICT`, `UNSUPPORTED_FORMAT`, `UNSAFE_INPUT_HANDLING`, and `OTHER_ADJUDICATION_REQUIRED`. Free text is never the primary reason. `OTHER_ADJUDICATION_REQUIRED` requires a separate protected adjudication note, which is excluded from portable artifacts.

| Reason code | Definition |
|---|---|
| `CORRECT_AS_IS` | The parser/result is correct for the available source evidence. |
| `SOURCE_AMBIGUOUS` | The source itself supports multiple reasonable interpretations. |
| `INSUFFICIENT_SOURCE_EVIDENCE` | The reviewer cannot establish the component from the supplied source. |
| `WRONG_COMPONENT_ROLE` | Extracted text belongs to another role, for example unit versus house number. |
| `WRONG_VALUE` | The component role is appropriate but the selected value is wrong. |
| `WRONG_SPAN_BOUNDARY` | The correct source region was targeted but span boundaries are incorrect. |
| `FALSE_POSITIVE_EXTRACTION` | The parser created structure not supported by the source. |
| `MISSED_EXTRACTABLE_COMPONENT` | A component was clearly extractable under the review standard but was not identified. |
| `WRONG_NORMALIZATION` | The underlying component is correct but the derived normalization changed it incorrectly. |
| `WRONG_PROVENANCE` | The value is correct but its recorded source/rule provenance is wrong. |
| `WRONG_CONFLICT_DETECTION` | The parser reported a conflict that is not supported. |
| `MISSED_CONFLICT` | A genuine conflict was present but not reported. |
| `UNSUPPORTED_FORMAT` | The source contains a legitimate pattern intentionally outside parser v1 coverage. |
| `UNSAFE_INPUT_HANDLING` | Operational safety/oversized handling was incorrect. |
| `OTHER_ADJUDICATION_REQUIRED` | No existing closed reason fits; a protected adjudication note is mandatory and use should be rare. |

Pre-registered metrics include selected-component precision, extractable-information recall, false-structure/overreach rate, conflict precision/recall, unresolved rate, missed-information rate, evidence-sidecar coverage, and results by country/script/completeness strata. Reviewer agreement uses percent agreement plus an approved chance-adjusted measure. Fill rate alone is never an acceptance metric.

## Manual-review privacy

Manual review runs only in a controlled local or institutionally approved environment. Review rows use hashed review IDs. Raw addresses are never copied into Git, portable reports, public issues, external AI/services, or other external systems without explicit institutional permission.

Review labels and aggregate metrics may be stored separately from raw text. Reviewer identity, duplicate review, adjudication, and disagreement reason codes are retained without placing confidential address values in reports.

## Version identifiers

Proposed initial identifiers, subject to the pre-pilot freeze, are:

- `parser_version = conservative_address_parser_v1`;
- `rule_registry_version = phase03_rule_registry_v2`;
- `cleaning_rules_version = derived_text_nfc_ws_v1_ucd16.0.0`;
- `placeholder_policy_version = placeholder_policy_v1`;
- `country_reference_version = country_reference_v2_iso_normative_cldr_46_1_operational`;
- `unicode_reference_version = unicode_ucd_16_0_0_scripts_20240430`;
- `diagnostic_vocabulary_version = diagnostic_vocabulary_v1`;
- `component_schema_version = phase03_component_core_v1`;
- evidence schema version `phase03_component_evidence_v1`;
- manual-review reason vocabulary `manual_review_reason_codes_v1`;
- `phase03_version = phase03_v1`.

`pending_*` identifiers are design placeholders and cannot appear in a pilot or production run. Exact reference IDs and digests must replace them before pilot execution.

## Remaining decisions before implementation or pilot

The following still require explicit approval or pilot evidence:

1. which future versioned street/house candidate rules, if any, are promoted after protected development evidence;
2. final operational size/candidate limits after the real development benchmark;
3. real-pilot confirmation of the frozen `evidence_sidecar_policy_v1` storage/query behavior;
4. final batch, row-group, compression, and memory settings;
5. whether a pinned libpostal model is evaluated only as a development-pilot secondary candidate generator;
6. the pre-registered quantitative evaluation thresholds, chosen after development but before locked evaluation;
7. separate authorization to select/read the real-data pilot;
8. separate authorization for any eventual full 206-shard Phase 3 run.

## Completion and STOP gate

Phase 3 can pass only when:

- the finalized implementation and synthetic tests are separately authorized and pass;
- the development pilot, rule freeze, threshold pre-registration, and locked evaluation are separately authorized and accepted;
- a full run is separately authorized;
- the immutable Phase 2 run validates exactly;
- 206 core shards contain exactly 20,600,000 rows with exact provider/stable-ID reconciliation;
- evidence sidecars follow the approved sparse inclusion policy and all raw spans validate;
- all core rows have parse status, completeness, evaluation status, and frozen versions;
- no rule/reference/runtime version differs from the frozen configuration;
- safe evidence from partially oversized rows is retained;
- all core, evidence, and dataset semantic digests match independent read-back;
- page checksums, hashes, schemas, state, manifests, and atomic promotion reconcile;
- no confidential raw/candidate value leaks into portable diagnostics;
- `_SUCCESS.json` is written last and a sanitized Phase 3 report is reviewed;
- the user explicitly approves Phase 3 completion.

Incomplete, ambiguous, conflicting, unparseable, insufficient, or partially evaluated addresses are valid retained data outcomes. Pipeline corruption, row loss, duplicate identity, unregistered behavior, invalid evidence, nondeterminism, or version mismatch fails the gate.

## STOP

This document finalizes the corrected Phase 3 parser design. The frozen,
synthetically validated pilot-runner contract is separately documented in
`PHASE03_PILOT_RUNNER_DESIGN.md`. Real pilot execution remains separately
authorized; full processing, Phase 4, deduplication,
`address_key`, and geocoding are not authorized.
