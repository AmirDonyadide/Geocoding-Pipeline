# Stage 10 — context, data, identity and Stage 11 handoff

Normative frozen revision of the [Stage 10 design](STAGE10_MULTI_HYPOTHESIS_QUERY_GENERATION.md),
awaiting final owner approval to implement. No executable schema or materializer
is introduced here. The owner superseded the candidate-wide first draft.

## Minimal relation set and exact context grain

One query context is exactly one **present Stage 8 representation occurrence**.
Its upstream key is `(stable_source_row_id_v1, stage08_representation)`; the
role is STANDARD or NATIVE, never BOTH. The Stage 8 occurrence view fixes its
candidate. Zero/one/two contexts per source row are possible. Equal standard
and native candidates remain separate contexts. No grouping/deduplication of
contexts occurs before generation, even when complete context values are equal.

| Object | Grain / key | Authority / downstream consumer |
|---|---|---|
| `query_hypothesis` | Query context × distinct complete Stage 10 intent; PK hypothesis_id, unique (query_context_id, representation_fingerprint) | Stage 11 handoff; context/source/candidate FKs inline |
| `query_family_decision` | Query context × family Q1–Q6; PK family_decision_id, unique (query_context_id, family) | Eligibility, membership/convergence, lineage and abstention; same-context hypothesis FK |
| `query_generation_summary` | One manifest-bound canonical aggregate object; content hash, no row PK | Portable diagnostics only; no source/context mapping authority |

No third physical query-context/source mapping relation is necessary. Contexts
are a deterministic view of Stage 8 occurrences, and each of the two protected
relations contains the same compact upstream FK tuple. The six decision rows
provide totality even for a context with no emitted hypothesis. Their context
fields must agree exactly. Stage 8 remains the sole authority for original ID,
file, logical record, candidate slots and source-row/representation membership.
Q7 exists once as a global deferred status in summary/manifest, with no row or ID.

## Input object and context identity

Let H(name, values...) be SHA256 of ASCII `SAFE:` + name + NUL + framed E(values).
E uses schema order and the typed encoding below. Bind exact accepted Stage 8,
Stage 9/public-pack and transitive Stage 6 row-map identities from the scientific
contract; paths/files come only from those manifests, never directory discovery.

The `stage10_input_binding_v1` object has required keys: binding_version, split,
benchmark_sha256, stage08, stage09, stage06_row_map, read_projection. Split is
DEVELOPMENT. Each stage entry carries manifest SHA, logical SHA, contract name/
fingerprint (null only if no separate upstream fingerprint exists), profile SHA
where supplied, schema bundle/combined schema SHA, exact transitive_bindings,
approved anchor and files (relative path, bytes, SHA-256 sorted by UTF-8 path).
Stage 9 also binds the public-pack manifest/lock and referenced relation/index
schemas, hashes and inventory. Stage 6 files are its row-map payload only. The read_projection lists relation
names in UTF-8 order, then selected fields in upstream schema order: all fields
of Stage 8 candidate/component/source-map and Stage 9 evidence/members plus
reached pack witness objects/capabilities/registry; Stage 6 stable ID, both
candidate slots and both representations' four lower lines and Stage 5
lower-candidate/availability/count/mask. Stage 9 coverage_summary is validation
only. Explicit relation filters/selectors are this document's closed definitions,
not implementation-dependent column discovery.
Unknown keys, changed expected identities, escaping paths and missing expected
files fail closed. No Stage 7 payload or raw CSV is added to the input set.

```
I = H('stage10-input:v1', canonical_JSON_bytes(input_binding))
U = H('stage10-context-input:v1', stage08_manifest_sha256,
      stage06_row_map_manifest_sha256, stage09_manifest_sha256)
query_context_id = H('stage10-context:v1', U,
                     stable_source_row_id_v1, stage08_representation)
S = H('stage10-science:v1', contract_sha256, schema_bundle_sha256,
      family_eligibility_format_selector_versions, transformation_spec_lock)
P = H('stage10-budget:v1', 'ALL_ELIGIBLE_CATALOG', null,
      family_order_Q1_to_Q6, context_ceiling=4, source_row_ceiling=8)
representation_fingerprint = H('stage10-intent:v1', QueryIntent)
hypothesis_id = H('stage10-hypothesis:v1', I, S, query_context_id,
                  representation_fingerprint)
family_decision_id = H('stage10-family-decision:v1', I, S,
                      query_context_id, family)
```

The context hash uses an immutable snapshot binding plus the minimal occurrence
key. Candidate ID is already determined by that key in the bound Stage 8 view;
country/source-line/geographic values and evidence are determined through its
bound Stage 8/6/9 FKs. They are not redundantly hashed as copied fields. A change
to any frozen context input changes U or fails input validation. Provider ID,
source filename, display text, counts, job, ordering and unrelated fields are
not extra context-ID arguments. Upstream manifest identifiers are immutable
snapshot references, not a claim that every manifest field affects generation.

Context identity is lineage identity, not complete-request equivalence. Two
contexts may generate identical intents and different hypothesis IDs; this is
required for exact occurrence map-back. Global intent counts are a read-only
cost diagnostic. Stage 11 later resolves global request equivalence; it cannot
replace or coalesce these context/source links.

## Exact schema draft

D = fixed_size_binary[32], T = large_string UTF-8, U = uint64, U8 = uint8.
Question mark means nullable; every column is required to be present. Other
fields/list members are non-null. Enums are strings, with meanings/order/bounds
in the schema metadata. All row-level data, including hashes and reason codes
attached to context IDs, is protected.

```
query_hypothesis(
  hypothesis_id D,
  query_context_id D,
  stable_source_row_id_v1 D,
  stage08_representation T,
  stage06_exact_candidate_id D,
  representation_fingerprint D,
  intent QueryIntent,
  generation_rank U8,
  selection_status T
)
QueryIntent(
  intent_version T, endpoint T, search_mode T,
  text T?, address T?, postalcode T?, locality T?, region T?, country T?,
  boundary_country T, retrieval_policy_slot T
)
query_family_decision(
  family_decision_id D,
  query_context_id D,
  stable_source_row_id_v1 D,
  stage08_representation T,
  stage06_exact_candidate_id D,
  family T,
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
SelectorCertificate(selector_id T, selected_count U, selected_stream_sha256 D)
TransformStep(ordinal U8, transform_id T, transform_asset_binding D?,
              input_value_sha256 D, output_value_sha256 D)
FieldDecision(field T, disposition T, reason_codes list<T>)
RemovedLine(source_slot U8, start_codepoint U, end_codepoint_exclusive U,
            category T, grammar_id T, stage08_component_ordinal U)
```

The source-ID/role pair FK resolves to exactly one Stage 8 occurrence; its
candidate ID must equal the inline candidate FK in both relations. Each
hypothesis is owned by exactly one context. Family→hypothesis is the composite
FK `(query_context_id, hypothesis_id)`, prohibiting cross-context attachment.
Do not infer a context or source map by joining candidate ID alone.

Intent version is stage10_query_intent_v1. FULL_TEXT requires `/v1/search`,
nonempty text and null structured fields. STRUCTURED requires
`/v1/search/structured`, null text, nonempty address and at least one nonempty
postalcode/locality. Region and country are null in v1. Null means omitted;
empty text/structured fields are not legal emitted values. Boundary is the
current-row recognized uppercase alpha-2 source code; no country-unbounded flag.
Retrieval policy slot is exactly SAFE_PELIAS_COMMON_RETRIEVAL_V1, identical across
families. It is a symbolic Stage 11 policy input, not executable defaults.

Selection status is ALL_ELIGIBLE_CATALOG for the first Stage 10 artifact.
Operating B is null; QUERY_BUDGET_SUPPRESSION is forbidden there. Rank is
contiguous 1..4 after context-local convergence, ordered by first supporting
family Q1..Q6 then unsigned intent fingerprint. The role's full baseline is
rank 1. A later accepted operating plan may introduce INITIAL_SELECTED and
BUDGET_SUPPRESSED statuses under a new profile; it cannot mutate this catalog.
Budget-only selection preserves generated identities; family/gate/transform
changes alter S. The profile binds S, P, intent-policy slot and encoding version.

Family is Q1..Q6 only. Eligibility is ELIGIBLE or INELIGIBLE. Membership is
FIRST_MEMBER, CONVERGENT_MEMBER or NONE. ELIGIBLE requires non-null hypothesis FK;
earliest eligible family with that complete intent is FIRST_MEMBER. Later
families share that FK and use CONVERGENT_MEMBER/EXACT_SEMANTIC_DUPLICATE. An
ineligible family has NONE and null FK. No hypothesis rows are emitted solely for family labels.
Rule ID is stage10_q<n>_eligibility_v1. Reasons follow the ordered family-document
vocabulary; primary_reason is first evaluated family reason or null. Field-only
exclusions remain on field_decisions, not falsely on the whole family outcome.

List bounds: <=18 unique ordered reasons, <=7 ordered selector certificates,
<=4 contiguous transform steps, <=6 field decisions in QueryIntent field order,
<=4 removed source slots in ascending order. Q4 has field decisions for address,
postalcode, locality, region, country, boundary_country (INCLUDE/OMIT/
NOT_APPLICABLE); a common gate failure marks all NOT_APPLICABLE. Other families
use []. Removed lines exist only for eligible Q5, source_slot 1..4, UNIT/LEVEL,
exact nonempty intervals and same-candidate component ordinals. Transform traces
record only actually completed steps, including attempts that produced an empty
or unsupported-output abstention; deferred/unattempted steps do not appear.
No trace of a fatal operational failure enters a committed artifact.

Semantic classes remain QUERY_HYPOTHESIS for intents, SOURCE_LINEAGE for
upstream FKs/removal slots, EVIDENCE_LINEAGE for selectors and parser ordinals,
QUERY_HYPOTHESIS_PROVENANCE for rule/transform decisions, MECHANICAL_INDEX for
IDs/ranks. No confidence, verified-component, validity, correction, coordinates,
geocoder-result or final-acceptance fields are introduced.

## Exact lineage selectors, scoped to the context

Each selector is a closed definition using the inline context FK tuple and the
bound snapshot. Its complete selected stream is independently replayable with
count and hash; no arbitrary SQL, omitted conflicting evidence or giant ID lists.

| Selector | Exact stream / order |
|---|---|
| CANDIDATE_V1 | This candidate's Stage 8 row, exact upstream schema order; count 1 |
| OCCURRENCE_V1 | This exact Stage 8 source/role occurrence; count 1 |
| SOURCE_CONTEXT_V1 | This source ID's exact Stage 8 source-map row; count 1 |
| SOURCE_LINES_V1 | This source/role joined to Stage 6: candidate slot, four lower lines in slot order, Stage 5 lower candidate/availability/count/mask; count 1 |
| PARSER_COMPONENTS_V1 | All Stage 8 raw long components for this candidate, by ordinal; duplicates/unknown labels preserved |
| SOURCE_REFERENCE_V1 | All Stage 9 SOURCE_ROW evidence with this exact source ID AND candidate ID, by unsigned evidence_id |
| REFERENCE_WITNESSES_V1 | Complete distinct referenced witnesses/objects/capabilities/registry of SOURCE_REFERENCE_V1, tagged ordering below |

Every family decision includes CANDIDATE, OCCURRENCE, SOURCE_CONTEXT,
SOURCE_REFERENCE and REFERENCE_WITNESSES, since country recognition needs exact
source S9.Q01 provenance. SOURCE_CONTEXT includes Stage 4 lower geography
needed by Q5 local source-field vetoes; no extra Stage 6 fields are required.
Q3/Q5 add SOURCE_LINES; Q5 also adds PARSER_COMPONENTS,
giving the maximum seven certificates. No parser-reference selector or parser
concordance metric changes Q4 eligibility in v1; parser fields remain addressable
through the accepted candidate/component inputs for later evaluation.

REFERENCE_WITNESSES has sections: (0) distinct singleton Witness structs sorted
by canonical bytes; (1) complete distinct reached reference_match_member sets
by set ID/member ordinal; (2) distinct reached reference objects by ID;
(3) matrix/rule-capability rows by ID; (4) registry rows by version ID. Hash tag
plus exact upstream framed row; count sums records in all sections. Preserve
all referenced fields and ancestors. Evidence retains its original set links,
so repeated witnesses are traversed once per context without losing lineage.
No all-reference lookup, cross-row evidence union, top-k or membership truncation.
Caches may share exact immutable selector results but cannot alter their scope.

SOURCE_LINES preserves empty positions, gaps and repeats independently of LF
serialization. Q5 alignment is reproduced from this vector, candidate text and
PARSER_COMPONENTS; only removed intervals/ordinals need inline storage. Raw/
clean siblings, provider/file/logical-record lineage are recoverable from the
same accepted row-map references. No second map or copied public pack is created.

Transforms: EXACT_CANDIDATE_V1 (Q1/Q2); SOURCE_LF_JOIN_V1 (Q3);
SOURCE_STRUCTURED_FIELDS_V1 (Q4); WHOLE_LINE_UNIT_LEVEL_REMOVE_V1 then
SOURCE_SPACE_JOIN_V1 (Q5); NFC_U16_V1 → ICU_GREK_LATN_77_1 or
ICU_CYRL_LATN_77_1 → NFC_U16_V1 (Q6). Q6 asset binding is
H('stage10-transform-assets:v1', transliteration_spec_sha256, runtime_build_lock_sha256).
The same binding is included in transformation_spec_lock within S; build hashes
are populated only after a real reviewed build, before any protected execution.
Input/output value hashes
use H('stage10-transform-value:v1', value). Exact/NFC/ICU values are strings;
line joins/removal take the four-slot string vector (derived removed slots become
empty without changing upstream); Q4 takes (exact candidate, source clean
postcode, source clean locality, context country) and yields QueryIntent. Its
field decisions explain omitted values. Step definitions and the science binding
supply all other rule identities; no digest replaces accessible protected values.

## Encoding, ordering and reproducibility

E begins with uint64 big-endian sequence count. Each value has one-byte tag:
null=00/no payload; string=01/uint64 UTF-8 byte length + exact bytes;
bytes=02/uint64 length + bytes; unsigned integer=03/eight big-endian bytes;
bool=04/00 or 01; list or ordered struct=05/uint64 count + tagged child values.
No locale normalization, floats, signed integers, ambiguous delimiter joins or
JSON key iteration enter these logical tuples. Enum strings remain exact UTF-8.
Lists retain specified order. Reject invalid UTF-8 or overflows.

Canonical JSON is sorted keys, ensure_ascii=true, compact separators, no NaN,
one final LF. I hashes these bytes through E's bytes tag. Schema fingerprints
bind ordered fields/types/nullability/semantic classes/metadata/enums/bounds and
PK/FK rules; schema bundle order is query_hypothesis, query_family_decision,
query_generation_summary. Specification JSON bytes and referenced public asset
hashes enter S; no future binary checksum is invented.

Hypothesis rows sort by unsigned (query_context_id, representation_fingerprint);
decisions by (query_context_id, numeric family). Selector row encodings reuse
exact upstream types, order and null semantics. Each relation hash streams
schema fingerprint, count and ordered E rows. Dataset hash binds I, S, P,
profile/schema fingerprints, relation hashes/counts and aggregate-summary hash.
Summary excludes its own/dataset/manifest hash, runtime/job/timing and physical
layout to avoid circularity and operational nondeterminism.

Collisions are checked using complete canonical bytes, not digest equality alone.
Different intents/context tuples under one observed ID fail publication. Logical
identity must be invariant to batch size, shard layout, order of workers and
Parquet compression. Exact physical file bytes/sizes and runtime/Git/SLURM
provenance are separately manifest-bound; byte-identical Parquet across layouts
is not promised. Restart must preserve exact context intervals and identities.

## Stage 11 complete-request boundary

Stage 10 supplies context/hypothesis identity, exact protected intent, structured
fields, requested country, transform/family lineage, complete input bindings and
the common request-policy slot. Its endpoint/mode fields are requested search
semantics, not an accepted executable request contract. The catalog permits
read-only future cost planning, not implicit execution or operating-B selection.

Stage 11 must separately freeze complete request semantics and resolve:

- endpoint/search mode and exact text or structured fields;
- boundary.country serialization/code namespace, preserving the requested context;
- layers, sources, language and result-affecting headers or explicit omission;
- size/top-N and retention, every other parameter (focus, spatial boundaries,
  viewbox, parser flags, etc.) or explicit omission;
- all client/server defaults and nonsecret result-affecting routing; and
- request-contract version, allowed parameters, canonicalization and collision rules.

Stage 11 then computes query_semantic_id from ALL complete result-affecting
semantics and globally deduplicates requests. No text-only ID and no silent
change to Stage 10 country, fields or LF. Unresolved policy inputs/unknown
parameters block workload publication. Intent fingerprint is a local convergence
and cost identity only; the final Stage 11 schema/hash formula does not yet exist.
Identical Stage 10 intents can serve many contexts after this resolution. Any
family-specific runtime override requires explicit new semantics and identity.

Stage 12 additionally binds concrete Pelias deployment/configuration, index/data/
import versions and execution-contract version for execution identity; retries
have separate attempt identity. Credentials remain runtime-only, never hashed
or logged. Changed index with the same request is a different execution identity.
Top-N versus the current size=1 rule and the Stage 19 geocoding acceptance gate
remain future owner reconciliations, not authority supplied by Stage 10.

## Map-back and cardinality invariants

```
Stage 8 (source row, representation) occurrence
  -> exactly one query_context_id
  -> zero to four hypotheses + six family decisions
  -> later complete Stage 11 semantic request
  -> Stage 12 execution/result
  -> the same context -> the original occurrence/source row
```

1. Distinct context/FK tuples in decisions are a bijection with all present
   Stage 8 occurrences. Exactly six unique family rows per context, no Q7 rows.
   Candidate set represented by contexts equals the full accepted candidate set.
2. Each context resolves exactly one source/role/candidate tuple; all rows with
   its ID have that tuple. No cross-source contamination or candidate-only join.
3. Every hypothesis has exactly one context, one candidate and >=1 eligible
   family membership; every non-null membership FK resolves within that context.
   Zero orphan/duplicate/cross-context hypotheses, decisions or selectors.
4. At most four distinct intents/hypotheses per context and eight per source row.
   Candidate bound is 4 × its occurrence count, not a fixed global budget.
   First-run output contains every eligible distinct Q1–Q6 intent, with zero
   operating-budget suppression. Exceeding engineering bounds fails, not truncates.
5. Context-local convergence compares complete QueryIntent bytes including mode,
   endpoint, fields, country and policy slot. It retains all family decisions.
   Across-context equal intents keep separate hypotheses and map-back.
6. Later every selected hypothesis maps to exactly one complete semantic request;
   many contexts/hypotheses can share one request. Preserve every membership,
   context and source/role edge after global dedup and execution-result reuse.
7. Expected context→hypothesis edge count equals hypothesis count. Expected
   source-row→hypothesis edges are the sum over its zero/one/two contexts, even
   when candidate IDs coincide. Distinct semantic requests/source row are a
   separate later metric. Source incidence deduplicates source IDs, not evidence.
8. Q1 provenance applies only to STANDARD contexts; Q2/Q6 only NATIVE. A request
   shared across contexts does not invent family support for another context.
9. Source rows without candidates, contexts without hypotheses, unschedulable
   requests and failed executions retain explicit left-join outcomes. Final
   source-grain output must retain 35,000 DEVELOPMENT rows, while intermediate
   hypothesis/evidence relations legitimately have greater cardinality.
10. Global dedup never broadens applicability by candidate ID; map results back
    through request→hypothesis→context→exact occurrence. All counts, complete
    FK sets and ordered fingerprints must reconcile independently.
