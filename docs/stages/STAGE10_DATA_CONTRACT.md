# Stage 10 — data, identity, lineage and Stage 11 handoff

Normative draft within the [Stage 10 design package](STAGE10_MULTI_HYPOTHESIS_QUERY_GENERATION.md).
No executable schemas or materialization are introduced by this document.

## Minimal relation set

Propose **two protected logical relations and one sanitized aggregate object**.
An explicit family-decision relation supplies both convergence membership and
abstention evidence; no separate family-member, candidate-summary, semantic-text
registry, context registry or source map is needed.

| Object | Grain / PK | Foreign keys | Consumer |
|---|---|---|---|
| `query_hypothesis` | One exact candidate × distinct generated request intent; PK `hypothesis_id` | Exactly one Stage 8 `candidate_evidence.stage06_exact_candidate_id` | Stage 11 selects/deduplicates; later evaluation uses suppressed catalog too |
| `query_family_decision` | Exactly one candidate × family Q1–Q7; PK `family_decision_id`; unique `(candidate_id, family)` | Candidate mandatory; hypothesis nullable, same-candidate composite FK; lineage selectors bind accepted inputs | Stage 11 map-back, family credit, suppression and evaluation |
| `query_generation_summary` | One manifest-bound run aggregate object; identity is its canonical-content hash, no row PK/FK | Manifest/input/science/budget fingerprint references | Portable diagnostics; never map or eligibility authority |

`query_hypothesis` is the **converged scientific hypothesis**, not a future
Pelias request. Several family derivations can support it. Different candidates
can have hypotheses with identical intent fingerprints and still retain
different hypothesis IDs. Stage 11 handles that global convergence.

Every candidate has seven family decisions, even when no hypothesis exists.
Source rows without candidates remain solely in Stage 8 and summary denominators.
The summary is deliberately a bounded object of integer counts/grouped cells,
not a third row-level authority. There are no optional logical relations.

## Exact schema draft

`D` = fixed_size_binary[32], `T` = large_string, `U` = uint64,
`U8` = uint8, `B` = bool. `?` means nullable; all other fields and list
members are non-null. Field order below is normative. Enums are closed strings;
raw strings are never coerced to enum ordinals. All columns are required to be
present; only the marked values may be null. Schema metadata binds semantic
classes, enum sets, list bounds, PK/FK rules, order and null semantics.

```text
query_hypothesis(
  hypothesis_id D,
  stage06_exact_candidate_id D,
  representation_fingerprint D,
  intent QueryIntent,
  generation_rank U8,
  selection_status T
)

QueryIntent(
  intent_version T,
  endpoint T,
  search_mode T,
  text T?,
  address T?,
  postalcode T?,
  locality T?,
  region T?,
  country T?,
  boundary_country T,
  retrieval_policy_slot T
)

query_family_decision(
  family_decision_id D,
  stage06_exact_candidate_id D,
  family T,
  source_representation_scope T,
  eligibility_state T,
  membership_state T,
  hypothesis_id D?,
  primary_reason T?,
  reason_codes list<T>,
  eligibility_rule_id T,
  lineage list<SelectorCertificate>,
  transformations list<TransformStep>,
  field_decisions list<FieldDecision>,
  removed_lines list<RemovedLine>
)

SelectorCertificate(
  selector_id T,
  selected_count U,
  selected_stream_sha256 D
)
TransformStep(
  ordinal U8,
  transform_id T,
  transform_asset_binding D?,
  input_value_sha256 D,
  output_value_sha256 D
)
FieldDecision(
  field T,
  disposition T,
  reason_codes list<T>
)
RemovedLine(
  source_slot U8,
  start_codepoint U,
  end_codepoint_exclusive U,
  category T,
  grammar_id T,
  stage08_component_ordinal U
)
```

`QueryIntent` rules:

- `intent_version = stage10_query_intent_v1`.
- FULL_TEXT: endpoint `/v1/search`, nonempty `text`, all structured fields null.
- STRUCTURED: endpoint `/v1/search/structured`, null `text`, nonempty `address`,
  at least one non-null/nonempty `postalcode` or `locality`; `region` and
  `country` are null in v1. Empty strings never stand for omitted fields.
- `boundary_country` is the exact trusted uppercase ISO alpha-2 code; no array,
  empty value, alternate code, country-unbounded flag or inferred alias.
- `retrieval_policy_slot = SAFE_PELIAS_COMMON_RETRIEVAL_V1`. It is a **symbolic
  common policy reference**, not a URL, credentials or claim that Stage 11
  request defaults have already been frozen. It applies identically to every
  family. No family-specific hidden parameters are allowed.

`selection_status` is CATALOG_ONLY, INITIAL_SELECTED or BUDGET_SUPPRESSED.
Generation rank is 1..5 and contiguous per candidate after local convergence.
CATALOG_ONLY requires null operating budget in the run metadata and selects no
workload. INITIAL_PLAN requires an approved B in 1..5; its two dispositions
follow rank exactly. The baseline must be rank 1 whenever a hypothesis exists.

Family enums Q1..Q7 are as defined in the family document.
`source_representation_scope`: STANDARD for Q1, NATIVE for Q2/Q6, actual
Stage 8 STANDARD/NATIVE/BOTH scope for Q3/Q4/Q5/Q7. This records family origin;
it is not a row-membership filter or inferred language.
`eligibility_state` is ELIGIBLE, INELIGIBLE or DEFERRED.
`membership_state` is FIRST_MEMBER, CONVERGENT_MEMBER or NONE.
Only ELIGIBLE has a non-null hypothesis FK and FIRST/CONVERGENT membership.
The earliest family contributing that exact intent is FIRST_MEMBER; all others
are CONVERGENT_MEMBER with `EXACT_SEMANTIC_DUPLICATE` recorded. Both contribute
to later family metrics. Q7 is always DEFERRED/NONE/null.

`eligibility_rule_id = stage10_q<n>_eligibility_v1` with n matching family.
Reasons use the closed ordered vocabulary in the family document. Family-level
reasons concern the family outcome; field-only reasons stay in `field_decisions`
and cannot imply the whole family abstained. For an eligible selected first
member, `primary_reason` is null unless a family-level diagnostic applies.
Budget-suppressed memberships all record QUERY_BUDGET_SUPPRESSION; convergence
can coexist and has earlier reason precedence. Ineligible decisions have their
failed evaluated gates and null FK. No committed row contains a fatal error.

Lists are bounded: reasons <=18 distinct in declared order, lineage <=8
certificates in selector order, transformations <=4 in contiguous ordinal
order, field decisions <=6 in intent field order, removed lines <=4 in source
slot order. Field decisions use INCLUDE/OMIT/NOT_APPLICABLE and address,
postalcode, locality, region, country, boundary_country. They are emitted for
Q4 only; all others use `[]`. Removed lines occur for eligible Q5 only, with
source_slot 1..4, UNIT/LEVEL category and exact interval bounds.
Transform steps for ineligible/deferred families are `[]`; hypothetical
unperformed transformations are not logged as performed.

All row-level fields are **protected**, including hashes, source scope,
selectors and reasons attached to a candidate. Intent text is QUERY_HYPOTHESIS;
IDs/ranks are MECHANICAL_INDEX; selectors/removed slots SOURCE_LINEAGE or
EVIDENCE_LINEAGE; rule/transform fields QUERY_HYPOTHESIS_PROVENANCE.
No row field is SOURCE_TRUTH, VERIFIED_COMPONENT, confidence, validity,
GEOCODER_RESULT or FINAL_ACCEPTED_RESULT. Original upstream semantic classes
are retained at their referenced locations.

## Lineage without duplicating authoritative maps

The immutable run metadata binds full input manifests and the read projection.
Each family stores selector certificates rather than a giant list of source
IDs, components or witness IDs. A selector is a **closed executable relational
definition**, not arbitrary SQL or an opaque digest. It uses this candidate key
and the bound input snapshot, and yields the complete selected evidence stream.
That stream can be independently reconstructed, with exact count and hash.

The v1 selector registry is ordered as follows:

| Selector | Exact selected stream / canonical order |
|---|---|
| CANDIDATE_V1 | Entire Stage 8 candidate row for this candidate, exact upstream field encoding; count 1 |
| OCCURRENCES_V1 | All Stage 8 occurrence-view rows with this candidate, by source-row ordinal then representation ordinal |
| SOURCE_CONTEXT_V1 | All distinct mapped Stage 8 source-map rows, by source-row ordinal; no STANDARD/NATIVE double-counting |
| SOURCE_LINES_V1 | Occurrences joined one-to-one to Stage 6 stable ID, representation-selected four lower lines and Stage 5 candidate/availability/count/mask, in occurrence order |
| PARSER_COMPONENTS_V1 | All exact Stage 8 long component rows for this candidate by ordinal, including duplicates/unknown labels |
| SOURCE_REFERENCE_V1 | All Stage 9 SOURCE_ROW evidence for this candidate by unsigned evidence_id, including every question/slot, not just favorable evidence |
| PARSER_REFERENCE_V1 | All Stage 9 PARSER_CANDIDATE evidence for this candidate by unsigned evidence_id |
| REFERENCE_WITNESSES_V1 | Distinct reached singleton witnesses, multi-match sets, objects, capabilities and registries in the tagged order below; complete members retained once per reached set |

SOURCE_LINES_V1 hashes each occurrence once with slot order 1..4, even for gaps
or identical STANDARD/NATIVE content. SOURCE_CONTEXT_V1 refers to source field
roles, never to a representative row. REFERENCE_WITNESSES_V1 has five tagged
sections in order: (0) distinct singleton Witness structs sorted by canonical
bytes; (1) every row of each distinct reached reference_match_member set, sorted
by set ID then member ordinal; (2) distinct referenced reference_object rows
sorted by object ID; (3) distinct capability/rule-capability rows sorted by
capability ID; (4) distinct registry rows sorted by reference-version ID.
Hash the tag plus exact upstream framed row; selected_count is the sum of
records across these sections. Follow all field/object locators transitively;
no member is truncated. Each source/parser evidence row retains its original
singleton/set link in the bound input, so sharing a repeated witness set loses
no lineage. Compute the selector with streaming/external joins and distinct
keys, never by expanding each repeated evidence row against every shared member.
Field predicates in Q4 specify which source reference arguments they consume;
the complete evidence selectors also retain conflicting/non-supporting evidence.
All reference locators remain resolvable through the bound pack without rerunning
lookups or copying it into Stage 10.

Every decision has CANDIDATE_V1 and OCCURRENCES_V1. Q3/Q5 also have
SOURCE_LINES_V1; Q4 has SOURCE_CONTEXT_V1, SOURCE_REFERENCE_V1 and
REFERENCE_WITNESSES_V1; Q5 has PARSER_COMPONENTS_V1; Q6 binds its script asset
and transform trace. When parser concordance is reported for Q4, include
PARSER_COMPONENTS_V1 and PARSER_REFERENCE_V1. Q7 has only the common two
selectors because no eligibility/activation computation occurs in v1.
REFERENCE_WITNESSES_V1 always uses both source and parser reference sets by its
definition, whether or not they have separate certificates on that row.

Trace IDs: EXACT_CANDIDATE_V1 (Q1/Q2 and Q4 address), SOURCE_LF_JOIN_V1 (Q3),
SOURCE_STRUCTURED_FIELDS_V1 (Q4), WHOLE_LINE_UNIT_LEVEL_REMOVE_V1 followed by
SOURCE_SPACE_JOIN_V1 (Q5), NFC_U16_V1 → ICU_GREEK_LATIN_77_1 or
ICU_CYRILLIC_LATIN_77_1 → NFC_U16_V1 (Q6). For structured transformation
digests use the canonical QueryIntent encoding instead of ambiguous joined text;
the transform definition declares that type. Transform assets for ICU/NFC are
mandatory D values; null is permitted only for rules whose full definition is
already bound by the scientific contract. No digest replaces the protected
string's availability in upstream inputs or the generated intent.
For Q5, the complete ordered alignment is reproducible from PARSER_COMPONENTS_V1
and the candidate selector; only the <=4 removed-line ordinals/intervals need
storage. Alignment's temporary external spool is not a published relation.
Transform value digests are `H('stage10-transform-value:v1', value)` using E
below. EXACT_CANDIDATE and NFC/ICU steps take/return a string. SOURCE_LF_JOIN
takes the four-slot string list and returns text. Q5 removal takes/returns that
four-slot list, representing removed slots by empty strings in its **derived**
intermediate; SOURCE_SPACE_JOIN returns text. SOURCE_STRUCTURED_FIELDS takes
the ordered tuple (candidate text, unanimous clean postcode-or-null, unanimous
clean locality-or-null, trusted country) and returns the complete QueryIntent.
Null input fields mean that unanimity/nonemptiness failed; field decisions
still bind the exact reason and source/evidence selectors.

## Deterministic identity formulas

Use SHA-256 with explicit domain separation. `H(name, values...)` means
`SHA256(ASCII('SAFE:') || ASCII(name) || NUL || E(values...))`.
`E` is a typed, framed sequence with explicit schema order: outer sequence count
uint64 big-endian; each value has a one-byte type tag, then its payload.
Tags: null 0x00 (no payload), UTF-8 string 0x01 (uint64 byte length + bytes),
bytes 0x02 (uint64 length + bytes), unsigned integer 0x03 (8 bytes big-endian),
bool 0x04 (0x00 or 0x01), list/struct 0x05 (uint64 element/field count + E values
without an extra outer count). No floats, implicit normalization, JSON object
ordering, delimiter concatenation or locale collation enters logical identity.
Signed integers and invalid UTF-8 are prohibited in these logical schemas.

```text
I = H('stage10-input:v1', canonical JSON bytes of the input-binding object)
S = H('stage10-science:v1', contract fingerprint, schema bundle fingerprint,
      family/eligibility/format/selector/identity versions, transformation asset lock)
P = H('stage10-budget:v1', plan mode, B-or-null, family order, ceiling=5,
      source-row ceiling=10, selection/suppression version)
representation_fingerprint = H('stage10-intent:v1', QueryIntent)
hypothesis_id = H('stage10-hypothesis:v1', I, S, stage06_exact_candidate_id,
                  representation_fingerprint)
family_decision_id = H('stage10-family-decision:v1', I, S,
                      stage06_exact_candidate_id, family)
```

The input-binding object has required keys `binding_version`, `split`,
`benchmark_sha256`, `stage08`, `stage09`, `stage06_row_map`, `read_projection`.
Version is `stage10_input_binding_v1`, split is DEVELOPMENT. Each stage entry
has exact `manifest_sha256`, `logical_sha256`, `contract_id`, `contract_sha256`,
`schema_bundle_sha256` (Stage 6 uses its combined schema fingerprint),
`profile_sha256`, `transitive_bindings`, `anchor` and `files`. Contract/profile
fingerprints are null only if that accepted upstream manifest has no such
separate identity; its exact manifest/contract definition remains bound. Never
invent absent upstream fingerprints. Stage 8/9 contract anchors listed in the
scientific contract are mandatory, non-null and exact.
Transitive bindings preserve every accepted input identity under its exact
upstream key. Stage 9 additionally binds the accepted public-pack manifest,
lock, inventory, registry/capability/object/index schemas and logical hashes.
`files` contains exact manifest-relative path, bytes and SHA-256, sorted by
UTF-8 path bytes, with separate explicit approved anchor for each manifest.
The Stage 6 list covers its bound row-map files, not an extra registry read.
`read_projection` is the exact relation/field and selector registry from this
package, lists ordered by relation name then upstream schema field position.
All hexadecimal values use lowercase; duplicate keys/paths and unknown keys
fail closed. JSON uses the manifest canonicalization below and enters E as
a bytes value. Paths are identity-bound access locators, not discovery hints.

`S` includes scientific/runtime transformation assets but excludes P, timestamps,
host, job, Git presentation metadata and physical layout. The proposed profile
fingerprint binds S, P, the shared retrieval-policy-slot name and logical-encoding
version. Budget-only recalibration preserves generated IDs while changing the
profile, dispositions, logical dataset and physical manifest. Any family/gate/
transformation/schema change creates a different S. Raw input-manifest changes
change I even if logical text is equal: exact input acceptance is intentional.

Complete canonical bytes must compare equal inside a digest group before
collapsing intents. A different payload for the same observed fingerprint or
ID is fatal. Across candidates, Stage 10 may count equal intents for diagnostics
but never merges candidate rows/hypotheses. `representation_fingerprint` is
neither `query_semantic_id` nor a protected-address anonymization mechanism.

Rows sort by unsigned `(candidate_id, representation_fingerprint)` for hypotheses
and `(candidate_id, numeric family ordinal)` for decisions. Generation rank is
an explicit field, not storage order. Each relation hash streams its schema
fingerprint, row count and exact ordered framed rows. Dataset hash binds I, S, P,
profile/schema fingerprints, both relation hashes/counts and the canonical
aggregate-summary hash. The summary does not include its own hash, output
manifest hash or dataset hash, preventing circularity.

Schema bundle hashes definitions in the order query_hypothesis,
query_family_decision, query_generation_summary, including metadata, bounds,
keys and enum values. Physical file SHA-256 and sizes are separate. Manifests
use the project's canonical JSON form (sorted keys, ASCII escapes, compact
separators, no NaN, one final LF); manifests bind logical hashes and Git/runtime/
job/paths/physical inventory. Reproducibility requires identical logical content
under different batch/shard/row-group layouts; byte-identical Parquet/manifests
are not promised across operational layouts or jobs.

## Stage 11 complete-request boundary

Stage 10 exports INITIAL_SELECTED hypotheses plus **all** their family decisions,
full immutable-input bindings and the authoritative Stage 8 map/view reference.
Catalog-only and budget-suppressed payloads are retained for controlled analysis
and are forbidden from the executable handoff. A Stage 11 plan cannot silently
activate them. Stage 11 starts with a separately reviewed contract and workload.

The common retrieval-policy slot leaves endpoint-specific operational defaults
to Stage 11 while making that unresolved boundary explicit. Stage 11 must bind
one accepted policy to the slot and resolve every result-affecting choice:

| Dimension | Stage 10 handoff | Stage 11 freeze obligation |
|---|---|---|
| Endpoint/mode | Exact path and FULL_TEXT/STRUCTURED | Preserve exact endpoint and mode in identity |
| Query body | Exact text or ordered structured fields | Lossless encoding; explicit omitted/null vs present; no text-only key |
| Country | Explicit trusted ISO alpha-2 boundary | Freeze exact parameter name/code serialization; do not broaden |
| Language | Common policy slot; no source-language inference | Bind query language and any result-affecting Accept-Language/header behavior, including intentional omission |
| Layers/sources | Common policy slot | Exact sets/lists and omitted vs explicit semantics; normalize order only when contract proves it immaterial |
| Size/top-N | Common policy slot | Explicit numeric value and result retention; no default chosen by this design |
| Other parameters | No per-family override | Enumerate focus, boundary rect/circle, viewbox, parser/legacy flags and every supported result-affecting option or explicit omission |
| Defaults/contract | `stage10_query_intent_v1` + slot | Request-contract version, resolved defaults, allowable headers/options; reject unknown/unresolved fields |

No coordinates/focus location are created in Stage 10. Stage 11 must reject
silent client/server/environment defaults that could alter results without
changing the declared request identity. Explicit omission remains bound to the
deployment's resolved behavior at Stage 12. Credentials are runtime-only, never
ID input or logged; any non-secret tenant/dataset routing that changes results
must be represented explicitly in the request/execution contract.

The future `query_semantic_id` hashes **all** canonical complete request
semantics plus request-contract version. Stage 10 deliberately does not define
that Stage 11 hash/domain/schema prematurely. Stage 12 execution identity then
additionally binds `query_semantic_id`, exact Pelias deployment/configuration,
index/data/import versions and execution-contract version. Retry/attempt IDs
are a further operational dimension, not new scientific hypotheses.

Changing a result-affecting parameter changes the Stage 11 semantic identity;
changing the deployment/index changes execution identity even with an identical
semantic request. Same text across free-text and structured endpoints never
converges just because it displays similarly. Missing deployment/index identity
blocks reproducible retrieval. The unresolved top-N versus size=1 policy and
Stage 19 acceptance gate must be explicitly reconciled before retrieval; this
Stage 10 design changes neither rule.

## Cardinality and map-back invariants

The exact chain is Stage 8 source/representation occurrence → Stage 6 candidate
→ Stage 10 hypothesis plus family decisions → Stage 11 complete request →
Stage 12 execution/result. Stage 8 remains the only source map authority.

1. Candidate-ID set in family decisions equals the complete Stage 8 candidate
   set; seven unique decisions per candidate. Zero orphan/duplicate decisions.
2. Every generated hypothesis has exactly one candidate and at least one
   eligible family membership; all referencing families share its candidate.
   Zero orphan hypotheses, memberships, evidence selectors or source links.
3. Hypothesis count is <=5 per candidate, selected count <=B, distinct source-row
   union <=10 (<=2B selected). One-candidate rows use that candidate once.
4. Each selected hypothesis maps to exactly one Stage 11 semantic request;
   many hypotheses may map to the same request. No selected hypothesis disappears.
5. All contributing family memberships survive global dedup. Their set/count
   and hash are reconciled independently of request count and execution attempts.
6. Rejoining results to Stage 8 uses explicit stable-ID and representation
   slots. Equal STANDARD/NATIVE slots stay two occurrences; source incidence
   counts use distinct stable IDs. Provider `id` is never a join key.
7. Expected selected occurrence/hypothesis edges equal the sum, over all Stage 8
   occurrences, of selected hypotheses on their candidate. Source-row union
   edges separately remove equal-candidate slot repetition; report both grains.
8. Family provenance edges use STANDARD only for Q1, NATIVE only for Q2/Q6 and
   all occurrences for Q3/Q4/Q5. They do not assert that a different-origin family
   independently supported every row to which the same request result maps.
9. Left joins preserve every original source row, candidate and absent/unresolved
   state, including zero-hypothesis/unschedulable/failed-execution outcomes.
   Final later-stage source output must reconcile 35,000 rows for DEVELOPMENT;
   intermediate evidence is one-to-many and must not be forced into that grain.

All invariants are independently recomputed, including complete payload
equality, selectors, decision counts, convergence and hypothetical stage-handoff
joins using synthetic inputs. Materialization cannot publish a partial candidate
set and call it scientific abstention.
