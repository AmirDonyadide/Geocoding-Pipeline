# Stage 11 — semantic core, canonical bytes and lossless map-back

Final owner-directed contract within the [Stage 11 design](STAGE11_SEMANTIC_REQUEST_DEDUPLICATION.md).
**OWNER REVIEW INCORPORATED — READY TO FREEZE; NOT IMPLEMENTED.** The owner
approved architecture A and directed the clarifications below. Final Git
freeze/merge remains a separate owner action. This is prose/schema notation
only: no materializer, executable schema, client or scientific output exists.

## Supported interface and public evidence

Project authority is the accepted
[Stage 10 intent/handoff](STAGE10_DATA_CONTRACT.md), confirmed against
`s10_query_contract.py` at baseline `d027da6c504a8fe864a7821a3e786c390ec05add`.
There is no accepted SAFE deployment/configuration snapshot in the repository.
Only its two intended paths and existing fields are enabled here.

Public evidence was inspected on 2026-10-03, without querying a geocoder:

| Evidence | What it supports; limits |
|---|---|
| [Pelias search documentation](https://github.com/pelias/documentation/blob/b720f5fca86b04b18af68903d1b95c2a9aad7e2f/search.md) | Text search, country filters, size, optional layers/sources and spatial inputs; generic capabilities do not authorize extra project parameters |
| [Structured geocoding](https://github.com/pelias/documentation/blob/b720f5fca86b04b18af68903d1b95c2a9aad7e2f/structured-geocoding.md) | Distinct structured path and named fields; shared search filters |
| [Language behavior](https://github.com/pelias/documentation/blob/b720f5fca86b04b18af68903d1b95c2a9aad7e2f/language-codes.md) | Documents `lang`/`Accept-Language` and dataset-default naming; not a verified effective-language guarantee for SAFE |
| [Default injection](https://github.com/pelias/api/blob/1e08f147d6ed00ffaac6f8442fdfc42a7e56580d/sanitizer/_default_parameters.js), [search wiring](https://github.com/pelias/api/blob/1e08f147d6ed00ffaac6f8442fdfc42a7e56580d/sanitizer/search.js) | Configured defaults can fill omitted groups; omission is unsafe without a compatibility constraint |
| [Target handling](https://github.com/pelias/api/blob/1e08f147d6ed00ffaac6f8442fdfc42a7e56580d/sanitizer/_targets.js), [address-layer behavior](https://github.com/pelias/api/blob/1e08f147d6ed00ffaac6f8442fdfc42a7e56580d/sanitizer/_address_layer_filter.js) | Explicit positive layer filters can bypass behavior that applies when layers are omitted; an explicit list is not proven equivalent to omission |
| [Country sanitizer](https://github.com/pelias/api/blob/1e08f147d6ed00ffaac6f8442fdfc42a7e56580d/sanitizer/_boundary_country.js) | Public API accepts ISO alpha-2/alpha-3, but its actual code vocabulary must be verified for the future SAFE deployment |

These pinned public revisions are **design evidence**, not assertions about the
installed SAFE release, a selected Pelias deployment, or a runtime dependency
of Stage 11. Future Stage 12 must verify both intended endpoints against its
actual pinned software/configuration. No default N or result-quality conclusion
is taken from public examples.

## Meaning of semantic equivalence

A semantic core is a closed, typed description of the exact search input,
country restriction, and intentional request-side semantic parameter policy.
Equality means exact equality of every field below under one versioned domain.
For any **one compatible fixed Stage 12 retrieval policy and deployment**, equal
cores must materialize identical semantic parameter values and omission states.
That is the required congruence property. It is not equivalence of responses
across retrieval depths, indexes, deployments, API algorithms or time.

Equality is deliberately narrower than any server's text normalization. The
server might ignore case or normalize text internally; Stage 11 does neither.
No text-only, candidate, context, source, family, country-only or hash-prefix
deduplication. No fuzzy, near-duplicate, transliteration or address-correction
step. Free-text and structured remain disjoint even if displayed text matches.

## Exact typed core and field order

T = exact Unicode scalar-value string encoded with strict UTF-8; T? is nullable.
Every named field is required to exist. Null is legal only at the marked slots,
where it means **omit that HTTP parameter**. It is not an explicit wire null.
All enums are exact case-sensitive strings. There is no arbitrary parameter map.

| Ordinal | Field | Type | Final v1 value / source |
|---:|---|---|---|
| 1 | `contract_version` | T | `stage11_semantic_request_contract_v1` |
| 2 | `schema_version` | T | `stage11_semantic_request_schema_v1` |
| 3 | `encoding_version` | T | `stage11_semantic_request_encoding_v1` |
| 4 | `semantic_policy_version` | T | `stage11_semantic_request_profile_v1` |
| 5 | `endpoint` | EndpointPath | Closed enum: `/v1/search` or `/v1/search/structured`, exactly matching Stage 10 |
| 6 | `search_mode` | SearchMode | Closed enum: `FULL_TEXT` or `STRUCTURED`, exactly matching Stage 10 |
| 7 | `text` | T? | Exact Stage 10 value/null |
| 8 | `address` | T? | Exact Stage 10 value/null |
| 9 | `postalcode` | T? | Exact Stage 10 string/null; never integer |
| 10 | `locality` | T? | Exact Stage 10 value/null |
| 11 | `region` | T? | Null, as required by accepted Stage 10 v1 |
| 12 | `country` | T? | Null structured country slot; distinct from boundary |
| 13 | `boundary_country_namespace` | T | `STAGE10_RECOGNIZED_ISO_ALPHA2_V1` |
| 14 | `boundary_country` | T | Exact accepted Stage 10 uppercase ASCII alpha-2 |
| 15 | `language_policy` | T | `NO_REQUEST_LANGUAGE_OVERRIDE` |
| 16 | `layers_policy` | T | `OMITTED_API_SELECTION` |
| 17 | `sources_policy` | T | `OMITTED_API_SELECTION` |
| 18 | `spatial_policy` | T | `NONE` |
| 19 | `additional_parameter_policy` | T | `REJECT_UNLISTED` |

**This is the single final field list:** `semantic_request` contains exactly
`query_semantic_id` and `core`; `core` contains exactly the 19 fields above,
in that order. `hypothesis_request_map` contains exactly `hypothesis_id` and
`query_semantic_id`. Their grains and storage types are specified below.

EndpointPath and SearchMode are closed string enums encoded with the string
tag, not arbitrary URL/string extension points. Only the paired combinations
below are legal; scheme, hostname, port, query suffix and fragment are forbidden
in EndpointPath. No deployment appears in either enum.
Their Arrow storage is `large_string` with mandatory closed-domain validation;
an implementation-dependent enum ordinal/dictionary code is never hashed.

`retrieval_policy_binding` is **removed**, with no replacement per-core sentinel.
Architecture A already requires Stage 12 binding at contract level; a repeated
sentinel supplies no extra validation benefit. Concrete N/retrieval-policy IDs
are forbidden core fields, including values for N=1/3/5/10. Their future change
must leave the Stage 11 core and query_semantic_id unchanged.

Generic `header_policy` is **removed**. Header classification is a contract rule
below; the only supported header-carried semantic concept, language, is governed
by the explicit `language_policy`. Transport/authentication state is not hashed.

`SemanticRequestCore` is the ordered struct of these 19 fields. The profile
fixes the constants and `ALL_ACCEPTED_HYPOTHESES` input policy, with no threshold,
family budget, family-specific parameter, language inference or geographic
inference. Implementation fingerprints must bind these exact types, order,
nullability, enums, validation rules and the approved design bytes. Altering
any semantic rule requires a new contract domain; never reuse a v1 name for
different rules. A changed physical Parquet layout alone does not change IDs.
The former 21-field model exists only in unimplemented design revision
`63f070643a2f877536cd2777ec381a49498553ed`. No artifact or frozen identity domain
used it. These owner-directed changes finalize the initial v1 before freeze;
the previous draft remains reachable in Git, without claiming ID compatibility.

Mode validation is exhaustive:

- `FULL_TEXT`: endpoint `/v1/search`, nonempty `text`, all five structured
  slots null. “Nonempty” means length > 0 without trimming or content repair.
- `STRUCTURED`: endpoint `/v1/search/structured`, `text` null, nonempty
  `address`, at least one nonempty `postalcode` or `locality`; the other may
  be null. `region` and `country` must be null. No named-field flattening.
- Both: exactly one non-null `[A-Z]{2}` boundary, accepted intent version
  `stage10_query_intent_v1`, policy slot `SAFE_PELIAS_COMMON_RETRIEVAL_V1`,
  and upstream selection status `ALL_ELIGIBLE_CATALOG`. Unknown modes,
  mismatched endpoints or slots fail, without fallback.

Projection copies all seven upstream payload/boundary values exactly
(`text`, `address`, `postalcode`, `locality`, `region`, `country`,
`boundary_country`, plus endpoint/mode as separate fields); validates the
upstream version/slot; and adds only the specified constants. No source field
is re-derived. Family membership, generation rank, representation fingerprint,
candidate/source/context IDs and operating budget do not enter the core.

`spatial_policy=NONE` means no spatial semantics beyond the separately required
country boundary: focus point/viewport, circles, rectangles and other biases
are unsupported. This is one fixed enum value, not an extensible object.
`additional_parameter_policy=REJECT_UNLISTED` is likewise a singleton assertion
of the closed allowlist, not a key/value bag or parameter slot. An unknown
result-affecting parameter or new policy value fails validation and requires
a future contract version; Stage 12 cannot pass it through under v1.

## Country, language, layers, sources and default policy

The boundary namespace means the exact code recognized under accepted Stage 10
source-row evidence, not a new lookup against today's country list. Preserve
alpha-2; no alpha-3 conversion, trimming, case change, alias, territory mapping,
multi-country union or guessed country. Send the exact code as `boundary.country`
later. Country-bound equality includes the code. Missing, empty, malformed or
unbounded input cannot legally arrive from this catalog and fails Stage 11
publication; it is never interpreted as country-unbounded. Q7 stays deferred.
If the actual service cannot represent an accepted code, Stage 12 must stop
compatibility/materialization or record an explicit technical unschedulable
outcome under its approved contract; it cannot broaden the query or drop its map.

Structured `country` is an address-component slot, whereas `boundary_country`
is a retrieval filter. They never alias, substitute for one another or collapse
because codes look alike. The component is always null in accepted Stage 10 v1;
future component support would require a new contract preserving both roles.

The exact request policy for every supported/considered parameter is:

| Parameter or behavior | Stage 11 policy | Omitted versus explicit value/default |
|---|---|---|
| `text`, `address` | Required in its own mode; prohibited in the other | Missing required value is fatal; null only in inactive mode |
| `postalcode`, `locality` | Exact optional values in structured mode, at least one present | Null means omit; empty/default/inferred substitutes forbidden |
| Structured `region`, `country` | Always omit | Explicit value, even matching boundary, is forbidden |
| `boundary.country` | Always explicit, single exact alpha-2 | Omission/default not legal or equivalent |
| `lang`, `Accept-Language` | Both absent under NO_REQUEST_LANGUAGE_OVERRIDE | No requested language, including any purported default; effective no-override language/naming behavior must be explicit and execution-bound in Stage 12 |
| `layers` | Absent: use API's unfiltered-request selection behavior | Not an explicit “all” list and not a promise every layer is searched; do not substitute address-only, coarse or all layers |
| `sources` | Absent: use API's unfiltered-request selection behavior | No explicit source/alias/default list, no dataset exclusion; actual available sources are deployment/index evidence |
| `focus.point.*`, `focus.viewport`, other focus, `boundary.rect.*`, `boundary.circle.*`, `boundary.gid`, viewbox | All absent and prohibited under spatial_policy=NONE | No implicit IP/location focus, no zero coordinates, radius default or context-derived boundary |
| `size` | Required future Stage 12 policy; absent from this core schema | Neither absent/default wire size nor an arbitrary N is allowed in an executable request |
| Parser flags, categories, custom boosts, fuzziness, autocomplete, reverse, other parameters | Unsupported; reject if supplied | No arbitrary pass-through or “ignore unknown” behavior |
| Result-affecting semantic headers | Express their meaning in a named core semantic field or reject | Language uses language_policy; other search overrides require a new contract; execution binding alone cannot legalize them |
| Transport/authentication headers and deployment routing | Stage 12 only, excluded from the core | Access credentials/protocol metadata are not query semantics; nonsecret deployment/data-view identity is execution-bound |
| Service internal parsing, scoring, fallback, interpolation and built-in selection | Behavior of the pinned execution engine | Stage 11 does not add toggle parameters or claim these algorithms are invariant across releases |

**No omitted-to-explicit-default equivalence is used anywhere in v1.** There
are no numeric/Boolean defaults to fill in the core. Optional payload nulls
already mean omission in accepted Stage 10 and map to exactly that state.
The explicit policy enum records omission's intended meaning; it is not a
request parameter sent to Pelias.

Omission does not excuse unspecified deployment defaults. Stage 12 must verify
the effective endpoint/client/proxy/server contract **before any protected
request**: no configured `defaultParameters` or middleware may inject a layer,
source, language, focus, extra geographic restriction or structured field;
no result-affecting contextual header or nonsecret routing override may be
unbound. Both endpoints must meet the same requirement. If effective behavior
cannot be established, execution is blocked. Merely hashing unknown defaults
is insufficient; incompatible ones require a separately reviewed new semantic
contract, not compensation by adding deployment identity to Stage 11.

The distinction from internal algorithms is deliberate. A pinned API may use
its documented built-in omitted-layer path, including the address-layer
optimization seen in public source; v1 intentionally preserves that invocation
state rather than disabling it through an invented filter. The future service
compatibility record must document its actual behavior and bind its code,
configuration and data. No “all layers equal omission” claim is made. Similarly,
which names and sources exist is execution data, not an inferred language
preference. The following language rule replaces the draft's ambiguous default.

### Final language rule and evidence limit

The actual accepted project input contract has **no language field** and a
single common request-policy slot for all families. Repository inspection found
no SAFE client/configuration guarantee of dataset-local, English or any other
effective no-override language. Public documentation is not such a guarantee.
Accordingly the old `DATASET_DEFAULT_NO_OVERRIDE` label is **not frozen as a
promise of dataset-local naming**. The final `NO_REQUEST_LANGUAGE_OVERRIDE`
freezes the absence of a *requested* language; it does not claim that language
cannot affect results or that the installed service needs no compatibility work.

This resolves owner decision 7 through explicit **Stage 12 execution binding
of effective no-override behavior**, rather than claiming an unavailable SAFE
runtime guarantee. Stage 11 neither needs nor derives a per-hypothesis language
choice from its accepted input. The final project v1 interface prohibits such
a choice; Stage 12 must conform to that interface, not silently add one.

Before materialization, Stage 12 must freeze an
`effective_no_override_language_behavior_id` identifying the actual API language
resolver/version, configured global no-override language behavior (including
any fixed fallback), dataset default-name/translation selection rules and data
identity. Its specification must distinguish effects on retrieval/ranking from
response labels; absent proof of label-only behavior, bind it as result-affecting.
Do not use an unspecified literal “default”, ambient machine locale, browser
headers, IP language inference or unbound proxy negotiation. Unknown behavior
blocks materialization. No per-request `lang` or `Accept-Language` is added.

Any fixed engine no-override fallback is disclosed and execution-bound, not
mistaken for a Stage 11 per-request preference. Changed engine/data behavior
requires a new Stage 12 execution identity. An explicit client language choice
or a requirement for per-request override requires a **new Stage 11 semantic
contract**, even if some current outputs happen to match. Execution binding
cannot conceal that semantic change. Thus no unresolved Stage 11 language
choice or hidden result-affecting language default remains in the design;
actual deployment verification remains future Stage 12 evidence, not performed
or assumed here.
Stage 12 may not switch global fallback per hypothesis, family, source, country
or representation to simulate a forbidden per-request language choice. Any
engine configuration is fixed for its bound execution environment.

### Header classification rule

| Class | Examples / exact treatment |
|---|---|
| `SEMANTIC_RESULT_AFFECTING` | `Accept-Language` has language meaning, represented only by language_policy; v1 forbids sending it. A header changing query interpretation, geographic scope, bias or requested language needs an explicit core field/policy under a new version if not already represented; unknown such headers fail closed. |
| `TRANSPORT_EXECUTION_ONLY` | Authentication/API-key headers used only for access and ordinary protocol metadata such as representation/compression negotiation belong to Stage 12. Neither their names/values nor credential hashes enter query_semantic_id. Host/backend selection is deployment identity, not a semantic endpoint URL. |

Classification follows effective behavior, not a header's familiar name.
Stage 12 must verify protocol/representation headers preserve the returned
scientific content after decoding; if they change the search semantics they
cannot be accepted as transport-only. A credential-dependent data view must
have an explicit **nonsecret deployment/access-scope identity** bound to Stage
12, with no secret hashed/logged. Query-semantic overrides through auth,
tenant, locale or other headers remain forbidden without a named semantic
contract. A general execution-policy field is not an escape hatch for them.

## Absence, null, types, lists and Unicode

ABSENT below means missing from the typed schema, not HTTP omission. Every
field/column must exist. These constraints apply before encoding or grouping:

| Fields | ABSENT | NULL | EMPTY STRING | VALUE |
|---|---|---|---|---|
| All version/policy fields, boundary_country_namespace | Invalid | Invalid | Invalid | Only exact table constant |
| endpoint, search_mode | Invalid | Invalid | Invalid | Only one legal enum pair |
| text | Invalid | Required for STRUCTURED; invalid for FULL_TEXT | Invalid | Nonempty exact string only for FULL_TEXT |
| address | Invalid | Required for FULL_TEXT; invalid for STRUCTURED | Invalid | Nonempty exact string only for STRUCTURED |
| postalcode, locality | Invalid | Required for FULL_TEXT; optional for STRUCTURED subject to at least one present | Invalid | Nonempty exact string only for STRUCTURED |
| region, country | Invalid | Required in both modes | Invalid | Invalid in v1 |
| boundary_country | Invalid | Invalid | Invalid | Exact accepted uppercase ASCII alpha-2 |
| semantic_request.core | Invalid | Invalid | Invalid type | Complete valid 19-field struct |
| query_semantic_id, hypothesis_id | Invalid | Invalid | Invalid type | Exactly 32 binary bytes in their respective relation columns |

No invalid state is repaired into a valid one. Nullable slots are the unique
internal representation of legal HTTP omission, never an instruction to send
an empty value or wire null. Schema constraints include the cross-field mode
and at-least-one-of-postalcode/locality requirements; permissive Arrow physical
types alone do not authorize invalid rows.

| Value/state | Canonical treatment |
|---|---|
| Missing named core field | Invalid schema, even for a nullable field; never fill silently |
| Null in T? slot | One explicit tagged null; means absent HTTP parameter |
| Explicit HTTP null, string `null`, empty string | No wire-null form exists; string `null` is literal text if legally present, never coerced; empty query/structured value is invalid |
| Empty list | Not omission; lists are not legal parameter values in v1 |
| Explicit default | Never coalesced with omission; unsupported value rejected |
| Boolean | Type-distinct from unsigned integer; invalid in all core fields |
| Integer | Type-distinct from string; invalid in all core fields, including postcode/country; Stage 12 owns typed positive result limit |
| Float/NaN/infinity | Unsupported; no coercion or serialization |
| Invalid UTF-8 / lone surrogate | Fail closed, never replace invalid bytes |
| Unicode, LF, CR, tabs, punctuation, case, whitespace | Preserve exact accepted scalar sequence; no trimming, NFC/NFKC, casefold/lower, transliteration, escape decoding or punctuation rewrite |
| Structured field order | Fixed schema ordinals, independent of input map/key iteration order |

Null and an absent *schema column* are different. All nullable columns exist;
only their values can be null. Transport omission is their specified rendering,
not normalization of two accepted wire representations. A literal backslash+n
differs from LF, composed from decomposed Unicode, leading zero postcode from
an integer, and trailing space from its absence.

**No list-valued request parameter is enabled.** Public source-order claims
alone do not establish SAFE deployment-wide equivalence for lists, aliases,
duplicates or omitted defaults. Layers/source ordering is therefore **not
relied upon**; any supplied list (ordered, set-like, empty or comma-separated)
is rejected. Country is a singleton. Future list support requires a new
contract specifying element namespace, order semantics and duplicate rules;
preserve order/multiplicity unless the supported API contract proves equivalence.
The encoder's ordered-list tag below serves named records, not a hidden
authorization for list parameters. No sorting/deduplication of user values.

## Canonical encoding and identity

Use repository-style typed binary framing, **not URL bytes or JSON text**, for
scientific identity. Define E(sequence) as unsigned 64-bit big-endian element
count followed by the tagged encoding of each element, without trailing bytes:

| Tag (hex) | Value | Payload after tag |
|---|---|---|
| `00` | Null | None |
| `01` | String | uint64 UTF-8 byte length, then exact strict UTF-8 bytes |
| `02` | Bytes | uint64 byte length, then exact bytes |
| `03` | Unsigned integer | Exactly eight big-endian bytes |
| `04` | Boolean | Exactly one byte: `00` false or `01` true |
| `05` | Ordered list/record | E(children) |

Reject integer/length overflow, invalid type, malformed framing or extra bytes.
Type dispatch must not treat Boolean as integer. Strings have no BOM added and
no terminator; lengths count bytes, not code points. Exact Unicode U+FEFF or LF
already inside a legal string is content. No normalization library participates.

Let `NamedCore` be a sequence of exactly 19 two-element ordered records
`(field_name, typed_field_value)` in the table's ordinal order. Every field name
is encoded as its exact ASCII string; the value uses its specified type/null.
This explicitly binds names, types, version and values without delimiter
ambiguity. All schema-valid core fields are string or null in v1.

```text
canonical_core_bytes = ASCII("SAFE:stage11-query-semantic:v1") || 0x00
                       || E(NamedCore)
query_semantic_id = SHA256(canonical_core_bytes)        # full 32 bytes
```

The domain marker's fixed NUL is framing, never an ambiguous concatenation of
variable values. Store IDs as `fixed_size_binary[32]`; display lowercase 64-hex
only in controlled row-level diagnostics. Hash prefixes are partition hints,
never scientific identity. No source/context/family/candidate, input snapshot,
split, job, path, hostname, secret, N or deployment/index enters this ID.
Identical semantic content across catalog publications keeps its identity;
the catalog's manifest/input binding supplies population provenance separately.

Group **full** IDs and compare full canonical bytes. If a group contains distinct
bytes, fail with `S11_ID_COLLISION`; do not select the first, suffix the ID,
rehash with salt, or silently merge. Also reject equal canonical payloads under
different claimed IDs by recomputation. Byte comparison, not digest equality
alone, proves equivalence. The validator reconstructs bytes from the typed core
and checks its claimed ID on every row and every mapped hypothesis.

## Minimal relation set, schema and logical fingerprints

D = fixed_size_binary[32], T = large_string, U = uint64. Relations contain only:

```text
semantic_request(
  query_semantic_id D NOT NULL PRIMARY KEY,
  core SemanticRequestCore NOT NULL
)

hypothesis_request_map(
  hypothesis_id D NOT NULL PRIMARY KEY,
  query_semantic_id D NOT NULL
)
```

`semantic_request` has one row per globally distinct core. Its nested `core`
contains all 19 required named fields with the types/nullability above; mode,
contract and exact protected payload are available there. Canonical bytes are
uniquely reproducible from that struct, so no redundant authoritative URL,
byte-blob, payload hash, membership list or duplicated mode column is needed.
Parquet storage encoding is not the scientific encoding.

`hypothesis_request_map` has exactly one row per accepted Stage 10 hypothesis.
FK `hypothesis_id` resolves to `query_hypothesis.hypothesis_id` in the single
manifest-bound upstream artifact; FK `query_semantic_id` resolves locally.
There is no extra edge ID. No copied Stage 10 intent, family membership, context
map, source row, candidate map, representative member or winner.

One manifest-bound **sanitized aggregate object**,
`stage11_semantic_request_summary_v1`, has no row-level grain/PK or lineage
authority. Its exact allowed metric set is in the
[evaluation plan](STAGE11_DEVELOPMENT_EVALUATION.md). Checkpoints and publication
metadata are operational artifacts, not additional scientific relations.

Logical fingerprint specification:

1. Schema descriptors bind ordered names/types/nullability, enum constants,
   nested field order, PK/FK, constraints and this encoding version. Descriptor
   JSON follows existing convention: sorted keys, ASCII escaping, compact
   separators, no floats/NaN, exactly one final LF. Hash the exact descriptor
   bytes with SHA-256. This JSON is metadata, not the core identity encoding.
2. Rows sort by unsigned full `query_semantic_id` for cores and unsigned full
   `hypothesis_id` for maps. Encode a core row as E([ID bytes,
   canonical_core_bytes as bytes]); encode a map row as E([hypothesis ID bytes,
   semantic ID bytes]). There are no duplicate PKs.
3. A relation digest streams ASCII `SAFE:stage11-relation:v1` + NUL,
   E([relation name, schema SHA-256 bytes, U row count]), then each encoded row
   in that exact order. All framing lengths are included. This is independent
   of Parquet files/shards. A count mismatch or trailing row fails validation.
4. Input binding I is SHA256 of ASCII `SAFE:stage11-input:v1` + NUL +
   E([canonical input-binding JSON bytes]). Summary hash is SHA256 of its exact
   canonical JSON bytes. The logical dataset digest is SHA256 of ASCII
   `SAFE:stage11-dataset:v1` + NUL + E([I bytes, contract fingerprint bytes,
   profile fingerprint bytes, schema-bundle fingerprint bytes,
   encoding-version string, core relation digest bytes, U core count,
   map relation digest bytes, U map count, summary hash bytes]). The schema
   bundle binds descriptors in order: semantic_request, hypothesis_request_map,
   summary; its digest is SHA256 of ASCII `SAFE:stage11-schema-bundle:v1` +
   NUL + E([semantic_request descriptor digest bytes, hypothesis_request_map
   descriptor digest bytes, summary descriptor digest bytes]).

For these catalog fingerprints, contract fingerprint is SHA256 of canonical
JSON containing `contract_version` and `design_documents` (the four normative
relative paths in UTF-8 order, each with exact byte SHA-256, excluding indexes
and this object's own digest). Profile fingerprint is SHA256 of canonical JSON
containing `profile_version`, `contract_sha256`, `input_policy` equal to
`ALL_ACCEPTED_HYPOTHESES`, `stage10_policy_slot` equal to
`SAFE_PELIAS_COMMON_RETRIEVAL_V1`, and `core_constants`: the exact constant
field/value pairs from the 19-field table. Digest values in metadata JSON use
lowercase 64-hex strings. These bind the approved design without a self-hash
cycle. They do not replace the core's explicit semantic versions or enter its
ID as extra document-byte dependencies.

Before execution, implementation must publish exact descriptor/profile/
contract fingerprints and byte-vector evidence against this prose. No future
hash is invented here. Operational timings, checkpoints, layout, Git/SLURM and
physical file hashes belong to the manifest, not the logical summary. The
input-binding anchor is provenance, not a semantic-ID argument; relocating
an approved artifact may alter its catalog binding but cannot alter core IDs.

## Totality, exact projection and map-back invariants

Write H for the complete bound hypothesis set, S for core rows, M for map rows,
and F(h) for the deterministic validated projection/encoding above. Publication
requires all checks, not merely plausible counts:

1. `|H| = 142677` for this accepted DEVELOPMENT input; H has unique IDs and
   expected schema/fingerprint. Any changed population is a binding failure.
2. `|M| = |H|`, M has unique hypothesis PKs, and both set differences of its
   hypothesis keys against H are empty. Exactly one outgoing edge per h.
3. Every M request FK resolves to exactly one S row. S has unique IDs, and its
   key set equals the distinct request keys of M. **Zero orphan cores** allowed.
4. For **every** h, M[h].ID = SHA256(F(h)) and S[M[h].ID].bytes = F(h).
   This detects swapped-but-total edges and preservation failures.
5. Equal complete bytes have exactly one ID/row; unequal bytes never share an
   ID. Collision/malformed/duplicate/missing-key counts must all be zero.
6. Sum of request multiplicities is |H|. Joining M to its unique S and H
   returns exactly |H| rows, with each upstream hypothesis/context/source/role/
   candidate tuple unchanged. Cross-context global equality cannot expand an
   individual hypothesis's original family/evidence scope.
7. Upstream eligible-family links join on both hypothesis and context; every
   FIRST_MEMBER/CONVERGENT_MEMBER survives via H. No many-to-many diagnostic
   join may inflate hypothesis counts or attach another context's family.
8. The accepted Stage 10 decision relation covers 69,747 contexts including
   1,668 without hypotheses. They remain upstream explicit abstentions, not
   dropped Stage 11 rows or fabricated unbounded requests. Source-grain later
   joins start from all 35,000 Stage 8 source rows and LEFT JOIN the chain.

For this DEVELOPMENT candidate the required values are explicit:
input hypotheses = map rows = **142,677**; hypotheses with zero request = **0**;
hypotheses with more than one request = **0**; cores with zero hypotheses = **0**;
ID/payload collisions = **0**. One contract-impossible hypothesis fails the
whole candidate, even if the remaining rows could be deduplicated successfully.

```text
Stage 8 source row and representation occurrence
  -> Stage 10 query_context_id
  -> Stage 10 hypothesis_id
  -> Stage 11 hypothesis_request_map -> query_semantic_id
  -> Stage 12 execution -> attempt/result/candidate
  -> downstream evidence/scoring through the SAME hypothesis/context/occurrence
  -> original source row (including explicit no-hypothesis/no-result outcomes)
```

A request shared by multiple sources provides shared retrieval evidence. Its
results must be evaluated against each exact context downstream; do not award
extra support for each family label or each dedup edge. Stage 13 can inspect
those correlations via upstream FKs; Stage 11 defines no scoring rule.

## Technical failure semantics

All codes below are fatal publication failures, not address-validity labels,
scientific abstentions or permission to publish the valid subset. Controlled
attempt evidence may record multiple failed checks with static codes/counts;
processing stops safely when required data are no longer trustworthy. Future
diagnostics must distinguish rows checked from rows unprocessed after failure.

| Code | Meaning |
|---|---|
| `S11_INPUT_BINDING_INVALID` | Wrong split/population, upstream manifest/hash/schema/acceptance or file inventory |
| `S11_UPSTREAM_ID_INVALID` | Duplicate/missing hypothesis PK, invalid accepted FK or selection status |
| `S11_INTENT_CONTRACT_INVALID` | Wrong mode/endpoint/version/slot, illegal null/empty/type or structured combination |
| `S11_COUNTRY_BOUNDARY_INVALID` | Missing, malformed or nonconforming boundary; never an unbounded fallback |
| `S11_PARAMETER_POLICY_INVALID` | Extra key/parameter/header, non-frozen policy or attempted default/list substitution |
| `S11_ENCODING_INVALID` | Invalid Unicode/framing/length/type, overflow or encoder disagreement |
| `S11_ID_COLLISION` | Same full ID with distinct canonical bytes |
| `S11_ID_RECOMPUTE_MISMATCH` | Claimed ID differs from deterministic full payload hash |
| `S11_MAP_TOTALITY_INVALID` | Missing/duplicate/extra edge, orphan, count mismatch or lost multiplicity |
| `S11_MAP_PROJECTION_MISMATCH` | Total FK map attaches a hypothesis to the wrong core |
| `S11_RESOURCE_FAILURE` | Memory/local space/quota/time failure; no truncation or giant-row skip |
| `S11_CHECKPOINT_INVALID` | Incomplete, corrupted, wrong-executable/binding/coverage checkpoint |
| `S11_PUBLICATION_INVALID` | Topology/registration/seal/reopen/durability failure or unverified outcome |
| `S11_PRIVACY_GUARD_FAILURE` | Execution site, split, permissions or reporting allowlist failure |

Never interpolate row contents, URL, arbitrary exception text, row-level IDs
or query fragments into portable errors. Log allowlisted phase/code/counts;
store indispensable row associations only in controlled artifacts. Unexpected
exceptions map to a static operational failure while preserving the original
cause privately, without printing it. An error handler must not mask the first
failure with a secondary reporting failure.

Service byte/URL limits are **not guessed** by Stage 11. Every valid core,
including a giant value, retains its map. Stage 12 must freeze actual transport
limits and a total materialization/outcome ledger before execution. Too-large
requests remain explicit technical unschedulable outcomes with full map-back,
not truncated requests or valid empty results. Stage 11 publication is not a
claim that every core will fit GET transport.

## Stage 12 handoff, transport and execution identity

Handoff consists of the two committed relations, the exact approved Stage 11
contract/profile/schema/encoding and fingerprints, manifest/registration/seal,
summary/validation evidence, and the bound Stage 10 manifest/FKs. No protected
payload is copied into a portable report. Stage 12 must reopen/validate the
Stage 11 catalog under exact external expectations before using its contents.

Required identity layering (future Stage 12 formula is a requirement, not an
implemented schema):

```text
Stage 10: hypothesis_id = source-context-aware generation intent
Stage 11: query_semantic_id = exact globally shareable semantic core
Stage 12: request_execution_id = domain-separated typed hash of
          (query_semantic_id,
           concrete retrieval_policy_id including explicit size and retention,
           concrete Pelias deployment/configuration identity,
           immutable index/data/import identity,
           API/parser/search-engine/source/layer configuration identity,
           effective_no_override_language_behavior_id,
           execution contract and transport/materialization contract versions,
           any other proven result-affecting execution setting)
```

Stage 12 must freeze this exact execution schema before execution; unknown
index/config identity or hidden result-affecting settings block reuse. Index
drift creates a new execution identity; a rolling/mutable index without a
verifiable snapshot cannot support reproducible cache reuse. Attempts/retries
have separate attempt IDs and timestamps; a retry against changed data is a
different execution, not an invisible retry of the same experiment. Response
reuse is keyed by complete execution identity with retained results/errors.
For one unchanged Stage 11 core, later N=1, N=3, N=5 and N=10 experiments leave
query_semantic_id unchanged and require four distinct retrieval policies and
execution identities. This is an identity obligation, not selection of N or
authorization of those experiments.

**Stage 12 owns HTTP serialization.** Stage 11 freezes the typed-to-parameter
meaning: resolve the closed endpoint enum to its exact path with GET; map only
non-null text/address/postalcode/locality/region/country payload slots unchanged;
map `boundary_country` to the single `boundary.country`; omit nulls and all
policy-prohibited parameters/headers; add only the concrete Stage 12 `size`.
Version and policy fields are internal schema semantics, never wire parameters.
Any further result-affecting request parameter requires revisiting this contract.
Deployment-specific source/layer *availability/configuration* is execution
identity; silently adding a `sources` or `layers` filter is a semantic change.

Stage 12's transport contract must prescribe deterministic parameter ordering,
strict UTF-8 value percent-encoding with exact decoding round-trip (including
literal plus, ampersand, equals, percent and LF), no duplicate keys, and no
content-bearing URL/header logging. The core is built before URLs; Stage 11
does not ingest arbitrary URLs or prove arbitrary encodings equivalent. Host,
port, TLS/authentication and retries are execution/transport concerns, with
nonsecret routing bound if it changes the service and secrets kept runtime-only.
Wire parameter order/percent-encoding cannot change a core ID; a serializer
that alters decoded values fails, rather than changing the core to suit it.

Given a validated core plus frozen Stage 12 retrieval, transport, deployment,
index/configuration and effective language bindings, materialization is single-
valued: select the enum path, emit the legal payload/filter slots and explicit
size, preserve every decoded value and omission, and apply the pinned transport
rules. No context/family lookup, arbitrary header, language guess or new source
address derivation may fill a gap. Missing execution bindings yield an explicit
unmaterialized/technical outcome; they never authorize server-default requests.

No retrieval, candidate generation, scoring, N calibration or concurrency
tuning is performed here. Normal future concurrency remains 2–4 across the
whole process, subject to separate exact-workload authorization and the
unchanged Stage 19 gate.
