# Stage 9 — Conservative offline geographic reference evidence

## Status, authority, and baseline

**Owner-approved scientific design with required revisions incorporated;
public reference lock FROZEN; implementation and execution NOT STARTED.**
This is the v1 design contract, not an accepted Stage 9 scientific result.
The owner approved the scientific direction and required concrete provenance
families, explicit authority gates, current suitable reference freezing and a
minimal data model. This session incorporates those revisions, acquires only
approved public reference bytes, freezes sanitized lock metadata, commits and
pushes the design, then stops. No materializer, reference index, protected
evidence, job, Stage 10 implementation, or acceptance report is created.

On 2026-09-07, `git fetch --prune origin` succeeded. The working tree was clean,
the branch was `main`, and HEAD, `origin/main`, and the dereferenced annotated
tag `pre-stage09-baseline-v1` all equalled:

`24b2679f8f487ebdbe65633c688996b1d36ea9eb`.

The repository records `STAGE_8_ACCEPTED` and Stage 9 NOT STARTED. The completed
Stages 0–8 audit is not reopened. Reading accepted contracts and code to design
their consumer does not repeat that audit or reopen protected artifacts.

Design identifiers (first owner-approved v1; the prior draft was uncommitted):

| Asset | Version |
|---|---|
| Scientific contract | `stage09_offline_reference_evidence_contract_v1` |
| Scientific/execution profile | `stage09_offline_reference_evidence_profile_v1` |
| Schema bundle | `stage09_offline_reference_evidence_schema_v1` |
| Registry specification | `stage09_reference_registry_contract_v1` |
| Reference pack build recipe | `stage09_reference_pack_recipe_v1` |
| Question catalog | `stage09_reference_question_catalog_v1` |
| Lookup normalization | `stage09_lookup_normalization_v1` |
| Semantic classes/dependence | `stage09_evidence_semantics_v1` |
| Identity/logical encoding | `stage09_reference_identity_v1` |
| Validation and manifest | `stage09_reference_validation_v1`, `stage09_reference_manifest_v1` |
| Downstream view | `stage09_stage10_handoff_v1` |

This document and the public reference lock are normative design assets.
Typed relation declarations and rules become executable contracts only during
separately approved implementation; schema/profile fingerprints are frozen
before protected execution. The acquisition lock hashes real public bytes,
not invented indexes or an unexecuted evidence relation.
There is no Stage 9 logical dataset fingerprint before a real execution.

## Purpose and scientific boundary

Stage 9 adds reference evidence about explicitly stated component or
relationship claims. It preserves the distinction:

```text
SOURCE TRUTH != DERIVED REPRESENTATION != PARSER EVIDENCE
             != REFERENCE EVIDENCE != GEOCODER RESULT != FINAL ACCEPTED RESULT
```

It evaluates country identifiers/context, metadata availability, postcode
patterns, recorded postcode membership, recorded postcode/locality/admin
associations, and recorded locality/admin hierarchy. Claims about a parser
value are conditional on its proposed role; reference agreement does not prove
that libpostal identified the right substring, component, or boundary.

No source field is corrected. There is no address-validity decision, parser
readiness decision, score, ranking, query, point, geometry, geocoder result, or
accepted match. No field named `CORRECTED_POSTCODE`, `CORRECTED_CITY`,
`CORRECTED_COUNTRY`, or `CORRECTED_STREET` is permitted. No new address string
is reconstructed. The reference stack is deliberately not a worldwide street
database or a second geocoder. STREET and HOUSE_NUMBER remain declared but
disabled capabilities in v1. Fuzzy matching is excluded entirely.

The four-state vocabulary below is specific to Stage 9. Historical downstream
vocabularies in D011 and the legacy proposal remain historical/later-stage
contracts; Stage 9 does not silently map them to validity or replace them.

## Exact accepted inputs

Read the accepted Stage 8 manifest and its three relations, and bind the
deterministic occurrence view. No alternative Stage 7 artifact is selected.
All values retain their existing semantic classes and upstream identities.

| Binding | Exact SHA-256, unless described otherwise |
|---|---|
| Accepted Stage 8 executable (Git SHA-1) | `c04cb97214a9f1e5d2b80512c756400321eefa80` |
| Reviewed Stage 8 candidate (Git SHA-1) | `231cdbf9db755fb56486c46b3b3faa02f5b5f3b6` |
| Stage 8 authoritative job | `1764273` |
| Stage 8 manifest | `2a50bd8c066552c9cb7505ed2d6071f1ee36161b9a2cc07f3ed364cf00237827` |
| Stage 8 logical dataset | `9c9d431c2c1b92712e0cb372f2661ad48f4fe8758dc0327d25aef90ab2c2d526` |
| Stage 8 contract | `8b3c530e714177fe2c30a97d61dcc199b7f9efba58f3c17a291b817af0f24d5e` |
| Stage 8 schema bundle | `6c8ebecd24c495dbe2ce32125ac1cb89c4a9de4905c786b774d10ad728ed392f` |
| Stage 8 mapping | `b18167d2d5c1f1402d1bb0e92559befb92418f5f4f34df885596778a11d5c09d` |
| Candidate schema | `b1d56ea33c22e639ab798581c5533b1a0981ef5452dce5cb24e168d4a684bd4c` |
| Component schema | `112fb17c2afac27b941d30f57fe5c1bb2e46d779f89bdf2efbd8c719a3b87ccf` |
| Source-map schema | `884eb8456fc6ee84a699a9e2371224e5c709363daac0febc5975f911bf48c398` |
| Occurrence-view schema | `df1cac9b6d9f86ffb76d1ea744fc64f15149c9e33fef980213286b91b2d02038` |
| Candidate logical relation | `11fbd6e6e32b7dcb293c5918e9d02f19badf52cc9d9c108c910d17d92b8645aa` |
| Component logical relation | `8b1af702c51bd40edc22302778ae2fda5851d9af8af39636a9a9733a94916030` |
| Source-map logical relation | `c4c9f8b3f425f93a1d61880f720136d1f71580871338c9a920c9abeffa93ee32` |
| Occurrence logical view | `57aa3dcc5caf796fbbe15b3c0df655a8f34902107ce9fed3fbb6aaf38e158774` |
| Transitive Stage 6 manifest | `e1da7b8ef04b65b1ece8e710720b57a8536841766fcf9de641f889b42eadd241` |
| Transitive Stage 6 row-map logical | `1ff9067c521ae93d28c300d7120a03c39681ce7830bf23b6619e2ca6129a4fe1` |
| Transitive Stage 6 logical dataset | `2f6379c0cd5dc9654c03895cae6fdd48f3a7af528158c33e44d2030c816640b6` |
| Transitive Stage 6 input binding | `6ba224d6d24c3631aae8aac69f4a362bb054f01d9e3d09327ec6b0fdd85a0e7d` |
| Transitive Stage 6 schema | `9c07b7a4c3f7a5c43ad457dcf6f7fe3fd746d54d82a731139905b30828b6c9ce` |

The Stage 7 contract/schema remain `c9561e6d…` / `b0e0e83e…`, exactly as
bound by the [Stage 8 input contract](STAGE08_ADDRESS_EVIDENCE_PROJECTION.md#exact-input-contract).
The Stage 9 input-binding object includes their full values and every other
transitive binding from that accepted manifest, without changing any of them.
Artifact paths, sizes, and SHA-256 values come exclusively from these bound
manifests; a directory name or inode is not a persistent input identity.

DEVELOPMENT totality is 35,000 source rows, 69,747 occurrences (34,822 STANDARD,
34,925 NATIVE), 51,779 exact candidates, and 6,106,088 ordered parser components.
Preserve 51,774 nonempty and five empty historical parses. The largest candidate
has 25,920,495 code points; the largest component list has 881,338 members.
No input is filtered because it is empty, giant, native, warned, country
unresolved, or has a label unavailable to a reference.

Use the exact Stage 3 clean source geography in Stage 8 as the source lookup
surface: `stage03_clean_postcode`, `stage03_clean_city`,
`stage03_clean_region_in_country`, and `stage03_clean_country_iso_code`.
Retain their raw siblings and exact pointers to Stage 4 lower siblings. Do not
evaluate raw/clean/lower copies as three independent confirmations. Parser
lookups use exact `stage08_raw_libpostal_value` at its original ordinal.

The Stage 9 materializer needs no Stage 6 payload read: Stage 8 has its
geographic inputs. The Stage 6 manifest-bound route is retained for Stage 10
source-line access, described below. HOLDOUT, raw CSV, production payloads,
and unrelated protected review artifacts are outside the Stage 9 input set.
The consumer verifies Stage 8's own files, schemas, logical content, map-back,
success marker and transitive manifest bindings. It must not invoke an upstream
materialization-review mode that additionally opens Stage 6/7 payloads; that
would expand this consumer's inputs and repeat accepted upstream work.

## Reference selection, version selection and public freeze

The approved stack is exactly ISO country/subdivision JSON, libaddressinput
metadata and GeoNames postal data. Existing Stage 7 ISO 4.18.0-1 remains
immutable upstream evidence, not a constraint on the Stage 9 reference vintage.
Before freezing, inspect current upstream/Debian releases, compare 3166-1 and
3166-2 records with 4.18.0-1, and select a suitable reproducible release with
documented deltas. Inspect the current metadata mirror release and actual data
history, and freeze its selected content rather than only a code revision.
GeoNames has no semantic release: freeze one dated download and exact bytes.

| reference_id | Role | Actual evidence family | Boundaries |
|---|---|---|---|
| ISO_CODES | Country/subdivision code and name membership; explicitly defined full-code ownership | ISO_CODES | Debian/upstream iso-codes compilation, not postal or locality truth; no inference of government provenance |
| LIBADDRESSINPUT_METADATA | Explicit FORMAT, REQUIRED_FIELDS, POSTCODE_PATTERN, ADMIN_ENUMERATION, POSTCODE_PREFIX_BY_ADMIN and recorded hierarchy | LIBADDRESSINPUT_METADATA | Data only; no package normalization/validation/Latinization API; missing fields unavailable |
| GEONAMES_POSTAL | Recorded postcode membership and same-record place/admin relationships | GEONAMES_POSTAL | Positive-only open-world extract; no official-authority label or completeness presumption |

The companion [reference lock](../scientific_assets/stage09_reference_pack_lock_v1.json)
records the selected
releases, exact source/member SHA-256 values, retrieval timestamps, publisher
headers, full file inventory, country-level public capability observations,
license evidence, encoding assumptions, and comparative version-selection
evidence. Raw public payloads live in a new owner-only, Git-ignored
`external_data/stage09_reference_freeze_v1/` directory. Git receives sanitized
lock metadata, not the large archive. No reference refresh occurs during
DEVELOPMENT, HOLDOUT or an accepted production execution. A changed vintage
requires a new reviewed lock/profile and a new immutable execution.

Acquisition is bounded to 256 MiB compressed/public downloads and 1 GiB
uncompressed inspection, independent of protected country/address data.
Download only ISO JSON and release/license documentation; the public metadata
wheel/member and provenance/license documentation; one GeoNames postal
`allCountries.zip`, README and directory listing. Do not acquire the main
GeoNames gazetteer, alternate names, or full/special postal variants. Preserve
all downloaded bytes and archive-member hashes. No indexes are built here.
Validate strict UTF-8, duplicate-free JSON object keys, expected string types,
safe archive names, inventory, reference-code uniqueness/parent links, and
actual metadata fields before recording capabilities. Unknown fields remain
in raw bytes and do not enable a capability.

GeoNames uses strict UTF-8, 12 tab-separated string fields, no header and no
CSV quoting (QUOTE_NONE); LF/CRLF terminators are recognized. Assign zero-based
logical record ordinals, reject malformed records without skipping/repairing,
and retain all raw bytes. Coordinates already present in this public archive
are not geocoded, used, copied to indexes, or emitted by Stage 9.

Country-specific GeoNames policy:

- Country absent from the acquired archive: all capabilities unavailable.
- AR, CA, CL, CN, GB, IE, MT, NL: full-postcode questions disabled because of
  legacy/truncated/coarser postal representations. Do not manufacture prefixes.
  Non-postcode place/admin questions can use actually present fields as partial
  recorded associations; no postal completeness claim follows.
- BR: major-postcode-only limitation; exact recorded full-code support allowed,
  missing full codes remain NOT_FOUND.
- US: five-digit evidence only; ZIP+4 full-code questions are NOT_EVALUABLE.
- Other countries: only actually present postcode/place/admin fields enable
  their corresponding question, with partial coverage and negative authority
  FALSE. Blank record fields never act as wildcards.
- The manifest records separately offered CA/NL/GB full and special files,
  including GB Royal Mail terms, as NOT_ACQUIRED_NOT_ENABLED. A default archive
  country and its special/full variant are never treated as interchangeable.

Freshness is separate from retrieval: an HTTP date, wheel release or archive
timestamp does not establish per-country effective validity. Stale metadata is
evidence about a frozen rule, never current deliverability. Preserve Google's
CC-BY-4.0 data attribution separately from the mirror's BSD-3-Clause code
notice and Google's Apache-2.0 code license. Preserve ISO LGPL notices and
GeoNames' stated CC-BY-4.0 plus its retained legacy CC-BY-3.0 link without
concealing that inconsistency; satisfy attribution/source/change notices for
both. No full-variant license is imported into the selected payload by analogy.

Primary provenance sources: [ISO releases](https://salsa.debian.org/iso-codes-team/iso-codes/-/tags),
[Debian versions](https://sources.debian.org/src/iso-codes/),
[metadata package](https://pypi.org/project/google-i18n-address/),
[Google metadata specification](https://github.com/google/libaddressinput/wiki/AddressValidationMetadata),
[Google data license](https://github.com/google/libaddressinput),
[GeoNames postal README](https://download.geonames.org/export/zip/readme.txt).
The [public freeze report](STAGE09_REFERENCE_FREEZE.md) records actual observations and selection;
these procedural rules alone do not claim acquisition has occurred.

Excluded: OSM, Overture, OpenAddresses, streets/house numbers, global gazetteers,
fuzzy matching, pycountry runtime, pgeocode, Address Data Service runtime calls,
Google Address Validation API, paid validation, Senzing and DeepParse.
Three small public references add complementary scoped evidence without
building a second geocoder.

## Capability registry and dependence contract

The registry is a matrix over exact reference version, country, question,
capability and explicit object scope. Every row includes independent booleans
`positive_authority` and `negative_authority`, authority basis/claim scope,
coverage kind, required arguments, granularity, normalization and limitations.
Both default FALSE. Enabled positive evidence requires positive_authority TRUE.
CONTRADICTED requires negative_authority TRUE and an applicable positive
contradiction witness. Capability availability never follows from data volume.

| Reference / question | Positive authority | Negative authority | Exact permitted claim |
|---|---|---|---|
| ISO_CODES Q01/Q14/Q10 | TRUE where corresponding frozen codes/names exist | FALSE | Recorded code/name membership; absence is NOT_FOUND |
| ISO_CODES Q02 | TRUE for recognized complete subdivision code | TRUE only for explicit full-code owner relationship | Known complete code has same/different owning country; no name absence contradiction |
| LIBADDRESSINPUT_METADATA Q03/Q15 | TRUE only for explicit fmt/require respectively | FALSE | Published format/required-field metadata exists; no address completeness decision |
| LIBADDRESSINPUT_METADATA Q04 | TRUE only for explicitly present, compatible country zip rule | TRUE only for that frozen rule | Full value satisfies/conflicts with stated frozen regex, not postal validity |
| LIBADDRESSINPUT_METADATA Q08 | TRUE only for enabled explicit admin prefix rule and satisfied country rule | TRUE only for that frozen prefix rule | Scoped prefix compatibility; missing enumeration or rule cannot contradict |
| LIBADDRESSINPUT_METADATA Q09/Q10/Q11 | TRUE only for explicit enumeration/path at that level | FALSE | Recorded names/relationships; missing enumeration is unavailable, list miss NOT_FOUND |
| GEONAMES_POSTAL all | TRUE only for enabled country/component/granularity | FALSE always in v1 | Positive recorded membership/association; no geographical negative certificate |
| Disabled/unsupported | FALSE | FALSE | NOT_EVALUABLE |

Negative basis enum: NONE, EXPLICIT_CODE_PARENT, EXPLICIT_FORMAT_RULE.
No real v1 capability accepts an exclusive-postal/locality authority certificate.
Synthetic negative geographic fixtures belong to a separate test registry and
cannot be loaded by the real profile. A country-level permission cannot bypass
a missing/unsafe object-level rule: effective authority is the conjunction of
the frozen country row and every applicable object gate.

Capability enum: COUNTRY_CONTEXT, FORMAT, REQUIRED_FIELDS, POSTCODE_PATTERN,
POSTCODE_EXISTENCE, POSTCODE_LOCALITY, POSTCODE_ADMIN,
POSTCODE_PREFIX_BY_ADMIN, LOCALITY, ADMIN, ADMIN_ENUMERATION, LOCALITY_ADMIN,
STREET, HOUSE_NUMBER. Different references in Q10 use ADMIN (ISO/GeoNames) or
ADMIN_ENUMERATION (metadata). STREET/HOUSE_NUMBER are never enabled.

The active family enum is ISO_CODES, LIBADDRESSINPUT_METADATA, GEONAMES_POSTAL.
POSTAL_AUTHORITY, OFFICIAL_ADMIN, OFFICIAL_LOCALITY, OSM, OPENADDRESSES and
OTHER_OPEN_REFERENCE are reserved future provenance families, not aliases for
current scientific roles. A future asset must justify actual provenance before
using an authoritative name.

Each registry entry embeds explicit bounded lineage tokens/edges:

- ISO_CODES → DEBIAN_ISO_CODES → ISO_3166. Stage 7 eligibility shares this
  lineage even when its version differs: KNOWN_SHARED, never a second vote.
- LIBADDRESSINPUT_METADATA → GOOGLE_I18N_ADDRESS_MIRROR →
  GOOGLE_ADDRESS_METADATA. A mirror is not an independent confirmation.
- GEONAMES_POSTAL → GEONAMES. Possible later Pelias GeoNames/Who's on First
  overlap is POSSIBLE_SHARED, with actual SAFE import identity UNKNOWN.

Lineage relation enum: SELF, DERIVED_FROM, PART_OF_FAMILY,
POSSIBLE_COMMON_SOURCE. Pelias overlap enum: UNKNOWN, POSSIBLE_SHARED,
KNOWN_SHARED, PROVEN_DISJOINT; no current family claims PROVEN_DISJOINT.
[Pelias' public source documentation](https://github.com/pelias/documentation/blob/master/data-sources.md)
establishes possible lineage, not the unknown actual SAFE inventory.
Stage 13 must compare actual importer ancestors. Unknown ancestry is not
independence; different families, aliases, source/parser repetitions and
STANDARD/NATIVE occurrences supply no additive votes or weights.

Country scope uses the selected frozen ISO alpha-2 namespace. ZZ is metadata
defaults, not geography. Additional public reference territory codes remain
preserved but inactive where accepted source-country context cannot use them.
No automatic UK→GB, territory→parent or historical-code remapping is allowed.

## Four-state evidence semantics

Every scheduled reference check emits exactly one state. No null result,
boolean substitute, or hidden fifth state is allowed.

| State | Required interpretation and evidence |
|---|---|
| `SUPPORTED` | A reference object or rule positively supports the exact scoped claim. Multiple compatible matches can support existential compatibility without choosing an entity. It does not validate an entire address. |
| `CONTRADICTED` | A positively identified rule/relationship conflicts with the claim, and this exact capability has applicable negative authority at the required level, granularity and time scope. The contradiction carries a witness and type. A different returned locality is insufficient. |
| `NOT_FOUND` | An evaluable exact lookup completed without the requested value or relationship. Coverage/aliases may be incomplete; no invalidity is implied. A missing item in even a large open catalog remains absence. |
| `NOT_EVALUABLE` | Prerequisites, role resolution, country, capability, temporal interpretation, granularity, or safe comparison support are insufficient for this question. No absence claim is made. |

`NOT_FOUND != CONTRADICTED` and `REFERENCE_MISMATCH != SOURCE_INVALID`
are validation invariants, not documentation only. GeoNames relationship misses
with an otherwise recorded postcode return NOT_FOUND with diagnostic
REFERENCE_ASSOCIATION_MISMATCH; the differing association is not a contradiction.
Lookup failure, timeout, corrupted reference, or out-of-memory is fatal to the
run, never a scientific NOT_FOUND or NOT_EVALUABLE.

Decision order within one question/reference:

1. Missing input, unknown country where required, disabled/absent capability,
   unknown semantic level, or incompatible granularity → NOT_EVALUABLE.
2. Complete allowed exact match set is nonempty and contains compatible
   witnesses only → SUPPORTED (ambiguity remains a separate diagnostic).
3. No support and an applicable positive contradiction certificate exists →
   CONTRADICTED. Rule conflicts have scope `FROZEN_METADATA_RULE`, never
   `ADDRESS_INVALID`. Explicit ISO ownership has scope `CODE_COUNTRY_RELATION`.
4. Otherwise an eligible completed lookup with no witness → NOT_FOUND.
5. Internally conflicting positive witnesses for an exclusive question →
   NOT_EVALUABLE / REFERENCE_INTERNAL_CONFLICT; retain all witnesses. Never
   select the first reference/record. Results across references are separate
   evidence rows and are not collapsed by majority or priority.

Closed contradiction types: `FORMAT_RULE_CONFLICT`, `PREFIX_RULE_CONFLICT`,
`EXPLICIT_CODE_COUNTRY_CONFLICT`. No geographical exclusive-relation
contradiction is enabled in v1.
Contradiction type is null for all other states. A CONTRADICTED row requires
at least one contradiction witness, negative_authority TRUE, and its exact positive-conflict basis.

An impossible form may conflict with a frozen postcode regex. A syntactically
plausible missing postcode remains NOT_FOUND in a capable membership reference.
A partial-code reference is NOT_EVALUABLE for a full-code question, even when
its prefix occurs. A full-code match in an incomplete reference supports only
recorded membership at that vintage. No latest/historical address dates are
inferred: all v1 geographic membership claims are `REFERENCE_SNAPSHOT`, and
format claims are `FROZEN_METADATA_RULE`. Historical/current validity claims
are unsupported questions, not inferred time matches.

## Source country policy

Country-dependent lookups require accepted candidate provenance
`COUNTRY_UNANIMOUS_VALID` and non-null `stage07_trusted_country_iso_code`.
Missing, partial, invalid, and conflicting provenance produce explicit
NOT_EVALUABLE / COUNTRY_CONTEXT_UNRESOLVED for dependent questions, including
occurrence questions. A locally present occurrence country does not bypass
this gate. Exact code recognition itself is country-independent and may
report a recognized occurrence code without resolving candidate context.

No country is inferred from parser output, script, language, postcode shape,
reference search frequency, majority vote, or a first match. Source country
remains unchanged, including when a contradiction exists.

Country assessment is a separate three-state dimension:

- `COUNTRY_SUPPORTED`: a source occurrence supplies an exact, globally
  recognized full ISO subdivision identifier whose explicit country owner
  agrees with the trusted source country. Support is only for that explicit
  source-code relationship.
- `COUNTRY_CONTRADICTED`: that same positively identified full identifier has
  an explicit incompatible country owner. The country code prefix alone is
  insufficient: the complete code must exist in the frozen ISO reference.
- `COUNTRY_UNRESOLVED`: no such witness, unresolved trusted context, insufficient
  authority, or mixed supporting/contradicting source-context witnesses.

ISO country-code recognition, country-blocked locality matching, and postcode
regex agreement do not by themselves support geographic country. Parser-origin
identifiers never set this country assessment. For source names/abbreviations
without a full ISO identifier, do not search all countries for alternatives.

A derived candidate-level assessment summarizes *distinct source-row Q02
witnesses*, not votes:
only support witnesses → COUNTRY_SUPPORTED; only contradiction witnesses →
COUNTRY_CONTRADICTED; both or neither → COUNTRY_UNRESOLVED. Other unevaluable
contexts do not erase existing
witnesses, but their count stays visible; the status is an evidence summary,
not a universal assertion about all occurrences. Parser-origin evidence is always
COUNTRY_UNRESOLVED for this dimension. Every summary includes its assessment
basis (`EXPLICIT_SOURCE_SUBDIVISION_CODE` or `NO_UNIFORM_WITNESS`) and conflict
flag. Stage 10 may use a specific contradiction as input to its future
diagnostic hypothesis policy; Stage 9 generates neither an alternative country
assignment nor a diagnostic query.

## Deterministic lookup normalization

Normalization creates comparison keys only. Each evaluated argument retains
an exact immutable Stage 8 locator to the original queried string, its
method/version, normalized comparison digest and key granularity. Reopening
that bound locator retrieves the original without duplicating protected text. The original value
and upstream lower/clean values are never overwritten. Missing source strings
remain `""`; missing observation and empty observed string are distinct.

| Method | Exact transformation / scope |
|---|---|
| `ISO_CODE_ASCII_UPPER_V1` | Convert ASCII a–z to A–Z only. No trim, punctuation removal, aliases, code-system conversion, or historical mapping. Recognition is exact in the relevant ISO code namespace. |
| `NAME_NFC_LOWER_U16_V1` | Unicode NFC followed by Python Unicode 16.0.0 `lower()`, applied identically to lookup and reference name/alias; no post-lower normalization, casefold, accent removal, token sorting, punctuation deletion, transliteration, or abbreviation expansion. |
| `POSTCODE_FORM_ASCII_UPPER_V1` | ASCII upper only; retain digits, leading zeroes, all whitespace and hyphens exactly. Country regex evaluates this full value. Non-ASCII digits are not recoded to ASCII. |
| `POSTCODE_EXACT_V1` | Default membership key is ASCII upper only, retaining separators. |
| `POSTCODE_SEPARATORS_V1` | Only JP (3+4 digits), PL (2+3), PT (4+3), BR (5+3): remove one ASCII hyphen at that exact boundary, or keep an already unseparated all-digit form. Only SE/CZ/SK (3+2): remove one ASCII space at that exact boundary, or keep an all-digit form. Both input and reference must match the respective full grammar. No other characters/spaces/hyphens are removed; all other forms use the unchanged exact key. |

No US ZIP+4, Canadian FSA, UK outward code, or other shortened postcode is
manufactured for membership lookup. The country-specific separator equivalence
affects membership keys only; it does not make a failing format regex pass.
COUNTRY/ADMIN code lookups and NAME lookups are separate modes; a name is never
changed into a guessed subdivision code. Full explicit ISO codes can be
recognized before a country block for Q02; all name lookup stays country
blocked. Source `region_in_country` is not declared an admin1 globally:
association matching retains the particular recorded level (1/2/3) and tests
only existential compatibility, without inventing a hierarchy level.

Libaddressinput aliases use explicit `name`, `lname`, `lfname`, `sub_names`,
`sub_lnames`, `sub_lfnames`, keys, language-tagged nodes and their own parent.
Alias roles are `REFERENCE_NATIVE`, `REFERENCE_LATIN`, `REFERENCE_NAME`,
`REFERENCE_CODE`, or `UNSPECIFIED`; language tags are exact or null. A Latin
alias is reference text, not a generated Latin form of an input. Normalize
separate native/Latin aliases individually. Never assume list order agrees
between language variants. If explicit cross-language identity is unavailable,
keep the objects separate. Empty positions in tilde lists preserve positions;
misaligned array lengths disable the affected alias/edge capability with a
pack diagnostic instead of zipping to the shorter array.

GeoNames postal names are exactly those supplied; do not synthesize native
names or join in guessed aliases. ISO native translations are not invented.
Homonyms/normalization collisions yield all exact matching reference objects;
they cannot establish a unique entity or create a negative claim. Mixed script
passes unchanged except NFC/lower; a miss is ordinary open-world absence.

Regex implementation is DuckDB 1.5.5's bundled RE2, with full-match semantics
for country `zip` and anchored prefix-match semantics for subregion `zip` or
aligned `sub_zips`. Group the entire expression before anchoring; never turn
`a|b` into `^a|b`. Freeze a compiler allowlist: ASCII literals/escaped literals,
ASCII character classes/ranges, `\d` as `[0-9]`, grouping/noncapturing grouping,
alternation, `?`, `*`, `+`, bounded repetition, and anchors. Unsupported escapes,
Unicode classes, flags, backreferences, lookarounds, or ambiguous parsing disable
that pattern with `PATTERN_DIALECT_UNSUPPORTED`. Do not silently reinterpret it.
Public examples and synthetic boundary cases must establish equivalence for
every enabled pattern. RE2 avoids backtracking work proportional to exponential
input ambiguity. Inputs are processed whole, including giants.

The data contain additional `xzip`/`sub_xzips` and `xrequire` fields. Archive
them, but do not guess their semantics: postcode pattern/prefix capabilities
for a node affected by its own/ancestor alternate postcode rule are disabled
as `ALTERNATE_RULE_SEMANTICS_UNSUPPORTED`. Required-field metadata remains
descriptive. `ZZ` defaults may supply descriptive fields with an explicit
default-origin pointer; they never provide country-specific negative authority.
No web URL stored in metadata (`posturl`, for example) is followed.
An alternate field is relevant when nonempty. For an aligned `sub_xzips` list,
only the nonempty entry for that explicit child affects its branch; for a
misaligned list, disable all potentially affected child prefix capabilities.
An ancestor's own nonempty `xzip` affects every descendant branch. An unqualified
country Q04 is disabled if any explicit descendant/child alternate postcode
rule could be relevant: v1 therefore disables CN/zip, not only the three
exception branches. It cannot negatively apply a country regex while ignoring
known exceptions. An absent or empty extra field is not an alternate rule. These are applicability boundaries,
not interpretations of the additional rule language.

## Evidence grain and question generation

No second source map, occurrence view, context registry or argument-value
store is materialized. Stage 8 remains authoritative for all of them.

Two evidence scopes are sufficient:

- PARSER_CANDIDATE: one evaluation per candidate, catalog question/reference
  slot and selected raw component ordinal(s), or explicit missing/ambiguous
  slot. stable_source_row_id_v1 is null; exact parser arguments are located by
  candidate ID + Stage 8 component ordinal + field name.
- SOURCE_ROW: one evaluation per distinct (candidate ID, Stage 8 stable source
  row ID), question/reference slot. If the same row's STANDARD and NATIVE slots
  have the same candidate, they share this evaluation and remain two upstream
  occurrences. Different source rows do not share evidence IDs. Their equal
  lookups may share cached work/match members without losing lineage.

This intentionally accepts linear source-evidence incidence instead of
persisting a second exact-tuple context/map system. Stage 8 source/occurrence
joins give every representation, provider ID, original file/logical record and
raw/clean/lower field. Rows with no candidate stay in Stage 8 denominators;
Stage 9 invents no candidate for them. Candidate text and source values are
not copied into Stage 9. Original queried values are losslessly accessible
through required exact immutable pointers, not optional mutable external data.

Question catalog (normative order; ISO/LIA/GN denote the three reference IDs):

| ID | Question / ordered arguments | Capability | Reference slots |
|---|---|---|---|
| Q01 | COUNTRY_CODE_RECOGNIZED (country code) | COUNTRY_CONTEXT | ISO |
| Q02 | EXPLICIT_SOURCE_ADMIN_COUNTRY (trusted country, source admin full code) | COUNTRY_CONTEXT | ISO |
| Q03 | COUNTRY_FORMAT_METADATA (trusted country) | FORMAT | LIA |
| Q04 | POSTCODE_PATTERN (trusted country, postcode) | POSTCODE_PATTERN | LIA |
| Q05 | POSTCODE_RECORDED (trusted country, postcode) | POSTCODE_EXISTENCE | GN |
| Q06 | POSTCODE_LOCALITY_RECORDED (trusted country, postcode, locality) | POSTCODE_LOCALITY | GN |
| Q07 | POSTCODE_ADMIN_RECORDED (trusted country, postcode, admin) | POSTCODE_ADMIN | GN |
| Q08 | POSTCODE_ADMIN_PREFIX_RULE (trusted country, postcode, admin) | POSTCODE_PREFIX_BY_ADMIN | LIA |
| Q09 | LOCALITY_RECORDED (trusted country, locality) | LOCALITY | LIA, GN |
| Q10 | ADMIN_RECORDED (trusted country, admin) | ADMIN / ADMIN_ENUMERATION for LIA | ISO, LIA, GN |
| Q11 | LOCALITY_ADMIN_RECORDED (trusted country, locality, admin) | LOCALITY_ADMIN | LIA, GN |
| Q12 | STREET_RECORDED (trusted country, street) | STREET | NONE |
| Q13 | HOUSE_NUMBER_RECORDED (trusted country, street, house number) | HOUSE_NUMBER | NONE |
| Q14 | PARSER_COUNTRY_CODE_RECOGNIZED (parser country value) | COUNTRY_CONTEXT | ISO; parser scope only |
| Q15 | REQUIRED_FIELD_METADATA (trusted country) | REQUIRED_FIELDS | LIA |

SOURCE_ROW schedules Q01–Q13 and Q15 once: 18 evaluation slots, counting each
listed reference. Q01 uses clean source country, Q02 clean source region.
Source postcode/locality/admin use exact Stage 3 clean fields. Q12/Q13 have
missing street/house arguments: no accepted source geography column asserts
those semantic roles. No source-line position is repurposed.

PARSER_CANDIDATE schedules Q01 using trusted country, Q02 as
NOT_EVALUABLE/SOURCE_ONLY_QUESTION, Q03 and Q15. Atomic Q04/Q05 apply to each
PARSER_POSTCODE ordinal, Q09 to each PARSER_CITY, Q10 to each PARSER_STATE,
Q12 to each PARSER_ROAD, Q14 to each PARSER_COUNTRY. Each absent atomic role
gets one missing placeholder. Relationship Q06–Q08/Q11/Q13 is scheduled once
per candidate and evaluated only if all required non-country roles have
exactly one raw ordinal. Identical duplicate values still count separately.
Store observed counts and null selection for ambiguous roles. No Cartesian
products, coalescing, selection of first labels, boundary heuristics or parser/
source cross-products. House-number role is PARSER_HOUSE_NUMBER. Other raw
labels remain fully bound/countable in Stage 8, without invented geography.

The maximum argument list length is three. Role codes are COUNTRY_CODE,
PARSER_COUNTRY_CODE, TRUSTED_COUNTRY, POSTCODE, LOCALITY, ADMIN, STREET,
HOUSE_NUMBER in catalog order. Missing observation has count zero and null
locator; ambiguous has count >1 and null selected locator; an observed empty
value has count one and a non-null locator resolving to an empty string.
Every actual field's origin semantic class remains explicit. Parser warnings
are available from Stage 8 and never filter scheduling.

Every check runs independently of other reference states. For NONE, an explicit
NOT_EVALUABLE/CAPABILITY_NOT_CONFIGURED row has null reference fields; NONE is
not a fake dataset. Every other slot binds an actual reference and explicit
capability row even when input/coverage is insufficient. Q01/Q14 use GLOBAL
ISO recognition capability; other questions use trusted country or UNRESOLVED.
Q03/Q15 return only existence of explicit descriptive metadata; missing fmt or
require is NOT_EVALUABLE, not missing-address-field contradiction. Required
fields are exposed through their reference object, never applied as a source
completeness/invalidity rule in v1.

### Exact matching and witness rules

Q01/Q14 recognize only complete alpha-2 ISO codes with ASCII case equivalence.
Unrecognized nonempty codes return NOT_FOUND; empty/null arguments return
NOT_EVALUABLE. Q01 does not set the country assessment. Q02 requires trusted
country and an exact existing full subdivision code before comparing its
explicit owning country; ambiguous/unrecognized names/codes are NOT_EVALUABLE
for this explicit-code question. No parser Q02 produces a geographic claim.

Q04 uses a supplied enabled country rule; match/nonmatch is SUPPORTED/CONTRADICTED
against that rule alone. Missing rule/country/argument is NOT_EVALUABLE. Q08
requires the country full format to be evaluable and satisfied, plus an exact
unambiguous metadata admin object and its enabled prefix rule. Missing/ambiguous
admin, failing country format, missing prefix rule or unsupported alternate
rule semantics is NOT_EVALUABLE. All applicable prefix-rule witnesses must
agree; conflict is NOT_EVALUABLE. An incompatible prefix is only a
PREFIX_RULE_CONFLICT, not postcode-locality or country geographic contradiction.

GeoNames questions use exact normalized string equality under a country block.
Q05 tests full-code membership only where permitted. Q06/Q07 require postcode
and locality/admin on the same postal record. Q07 may match any nonempty admin
name level, recording which; it never invents an admin1 interpretation.
GeoNames admin codes are retained as public provenance but are not lookup
aliases in v1: an unqualified source region is not assigned their code system.
Q09/Q10/Q11
may use country plus place/admin records without a postcode, retaining explicit
reference level and same-record/explicit-parent witnesses. No country+postcode
hit followed by a different locality becomes contradiction: Q06/Q07 return
NOT_FOUND with REFERENCE_ASSOCIATION_MISMATCH when the postcode is recorded
but the requested same-record relationship is absent. No co-occurrence
is inferred by joining independent records on a homonymous city/admin name.

Libaddressinput Q09/Q10 use actual locality/admin nodes and aliases at the
appropriate metadata level, within the trusted country. Q11 requires an
explicit parent/ancestor path, not matching names across disconnected trees.
ISO Q10 accepts a recognized full code in the selected country or exact
subdivision name under that country; numeric/suffix codes without a full code
are not inferred. Missing reference fields/levels disable the corresponding
country capability; one available level never claims complete hierarchy coverage.

All matching objects are retained in deterministic order in the immutable
public index. Evidence links to a complete match set, without top-k truncation.
An alternative reference value may be exposed only through a witnessed object's
public fields as `ALTERNATIVE_REFERENCE_VALUE`; it is neither a correction nor
a ranked recommendation. V1 does not enumerate nearest alternatives after a
miss. Explicit country-code conflict may expose the witnessed owner-country
derived from the recognized code under that role, explicitly classified
REFERENCE_EVIDENCE, with original claim and contradiction unchanged.

Witness-field selection is deterministic. Q01/Q14 use ISO `alpha_2`; Q02 uses
the complete recognized subdivision `code`; its exact country prefix defines
the owner in that same ISO 3166-2 asset. No guessed/unrecognized prefix is a
witness. Q03 uses the explicit country `fmt`; Q15 uses explicit `require`.
Defaults alone cannot enable either capability. Q04 uses the explicit `zip`.
Q08 uses the matched admin alias/key, its applicable prefix field and country
`zip`; all are bound to their object and source field. Q05 uses postal country
and postcode; Q06/Q07 add the matched place/admin name fields on that record.
Q09/Q10/Q11 retain the matched name/alias/code field, country field or owning
country object, and every explicit parent link used for a hierarchy claim.
Parent witnesses point to the child key/ISO code and parent key/ISO code;
`explicit_parent_id` is independently verified against those source fields.
Return all satisfying record/path witnesses; no record rank breaks ties.

Normalization dispatch is fixed by role: country arguments always use
ISO_CODE_ASCII_UPPER_V1; Q02 admin uses that full-code method; Q04/Q08 postcode
uses POSTCODE_FORM_ASCII_UPPER_V1; Q05/Q06/Q07 postcode uses the country-specific
membership method in the normalization table; locality/admin names use
NAME_NFC_LOWER_U16_V1. For ISO Q10 alone, an ASCII-uppercased input matching
`[A-Z]{2}-[A-Z0-9]+` uses full-code lookup without name fallback; all other inputs
use name lookup. Libaddressinput explicitly supplied short keys are treated as
reference aliases under the name method, without an inferred ISO code. Disabled
street/house arguments use NOT_APPLIED_V1. Missing or ambiguous arguments have
null keys and NOT_APPLIED_V1; no country-independent cache entry bypasses the
prerequisite gates. Cache only actually executed lookups, after all prerequisites
pass, and include every ordered key, role, method and granularity in its identity.

## Minimal relational schema and necessity

D = Arrow fixed_size_binary[32], T = large_string UTF-8, U = uint64, B = bool.
? marks nullable; other fields are required. Lists have explicit bounds below.
Dates are ISO-8601 UTC/date strings or null for unknown effective dates.
Enumerations use closed string sets, not engine-dependent ordinal enums.
Default order is primary-key order using unsigned bytes, binary UTF-8,
numeric order and null first. Schema fingerprints bind ordered fields, types,
nullability, enum meanings, keys, bounds, sorting and semantic classes.

Exactly six scientific logical relations are retained:

| Relation | Why it exists / why not safely derive it from existing evidence | Grain and keys |
|---|---|---|
| reference_registry | Freezes external bytes, licenses and provenance absent from Stage 8; bounded inventory/lineage embedded, not separate tables | One reference edition; PK reference_version_id |
| reference_capability | Makes authority and abstention explicit; cannot infer authority from reference membership or observed success | One edition/country/question/object scope; PK capability_id; FK reference_version_id |
| reference_object | Required public indexed projection with stable field-level witnesses; reproducibly derived from raw assets but retained once for bounded repeated lookups, not rebuilt per candidate/run | One public record or metadata path; PK reference_object_id; FK version, nested asset ID, optional parent |
| candidate_reference_evidence | The new scientific evaluation absent upstream; bounded argument pointers inline | One scoped candidate/question/reference evaluation; PK evidence_id; FK exact Stage 8 candidate, optional source row, reference/capability, witnesses |
| reference_match_member | Only for a genuinely multiple-witness result; unbounded homonym sets cannot safely fit an evidence row. Shared once per equal lookup, never top-k | One member in a multi-match set; PK (match_set_id, member_ordinal); FK public object(s); referenced by evidence match_set_id |
| coverage_summary | Reproducibly derivable, deliberately retained as bounded aggregate publication/totality check and to avoid downstream billion-row rescans; no separate authority | One aggregate grouping/dimension/state/reason cell; composite PK below; reference/capability binding through dimensions |

reference_registry/capability/object reside in one immutable public pack and
are bound by the protected run, not duplicated per shard. A physical
reference_index is permitted solely as an exact derived acceleration structure
(country, lookup kind, normalization method, key, object/field locator); no new
scientific facts or independent identity. Its build recipe, schema, logical
content hash and physical hashes are validated against reference_object.
The raw lock exists now; these future indexes/relations are not claimed built.

Removed from the original draft: reference_asset and reference_lineage
(embedded bounded registry structs); reference_field (bounded per-object
fields); candidate_reference_evaluation (aggregate view, not an authoritative
table); evaluation_context, context_input, source_context_map,
reference_question, question_argument, reference_evaluation,
evaluation_argument, reference_match_set; and the proposed Stage 9
representation-occurrence view. Their necessary scalar information is inline
in candidate_reference_evidence or exactly derived from Stage 8. No
source-context digest/map is needed. Temporary external-sort/cache/checkpoint
tables are operational scratch, never additional final logical relations.

```text
reference_registry(
  reference_version_id D PK, reference_id T, dataset_name T,
  dataset_release T, edition T, evidence_family T,
  retrieval_utc T, effective_date T?, license_expression T,
  license_note T, normalization_contract T,
  countries list<T>, limitations list<T>,
  assets list<Asset>, lineage list<Lineage>,
  raw_dataset_sha256 D
)
Asset(
  asset_id D, role T, relative_path T, source_url T, member_path T?,
  retrieval_utc T, publisher_release T?, last_modified T?, etag T?,
  bytes U, sha256 D, media_type T, provenance T
)
Lineage(token T, parent_token T, relation T, pelias_overlap T, provenance T)
reference_capability(
  capability_id D PK, reference_version_id D FK,
  country_scope T, question_catalog_id T, capability T,
  scope_locator T, enabled B,
  positive_authority B, positive_authority_basis T,
  negative_authority B, negative_authority_basis T,
  claim_scope T, coverage_kind T, granularity T,
  required_roles list<T>, normalization_id T, limitations list<T>
)
reference_object(
  reference_object_id D PK, reference_version_id D FK, asset_id D FK,
  source_locator T, object_kind T, country_code T?,
  explicit_parent_id D? FK, fields list<ReferenceField>
)
ReferenceField(
  field_name T, ordinal U, original_value T, source_field_locator T,
  alias_role T, language_tag T?, geographic_level T?
)
candidate_reference_evidence(
  evidence_id D PK, stage06_exact_candidate_id D FK,
  evidence_scope T, stable_source_row_id_v1 D? FK,
  question_catalog_id T, reference_slot T,
  reference_version_id D? FK, reference_asset_id D? FK,
  capability_id D? FK, rule_capability_id D? FK,
  evidence_family T?, interpretation T, claim_scope T,
  arguments list<Argument>,
  result_state T, reason_code T, contradiction_type T?,
  country_assessment T, country_assessment_basis T,
  lookup_identity D?, witness_count U,
  single_witness Witness?, match_set_id D?,
  evidence_class T
)
Argument(
  role T, origin_relation T, origin_field T?,
  component_ordinal U?, observed_role_count U,
  origin_semantic_class T, normalization_id T,
  normalized_value_sha256 D?, value_granularity T
)
Witness(
  reference_object_id D FK, witness_role T,
  fields list<FieldPointer>
)
FieldPointer(reference_object_id D FK, field_name T, ordinal U)
reference_match_member(
  match_set_id D, member_ordinal U, witness Witness,
  PK(match_set_id, member_ordinal)
)
coverage_summary(
  summary_kind T, country_scope T, evidence_scope T, representation T,
  question_catalog_id T, reference_slot T, capability T,
  result_state T, reason_code T, contradiction_type T,
  count U, denominator U,
  PK(all preceding dimension fields)
)
```

Bounded structs: arguments ≤3; Witness.fields ≤16 (one record plus explicit
metadata ancestry of depth ≤3); Asset list ≤512, Lineage ≤32, countries ≤512,
limitations ≤64, required_roles ≤3, ReferenceField list ≤512 per object.
These are reference/schema structural limits, checked against public assets
before indexing; exceeding one is a build/design failure, not truncation.
Raw tilde-list fields are stored once; explicit child alias entries are attached
to child objects, not one unbounded exploded parent field list.

Object kinds: ISO_COUNTRY, ISO_ADMIN, FORMAT_COUNTRY, FORMAT_ADMIN,
FORMAT_LOCALITY, FORMAT_DEPENDENT_LOCALITY, POSTAL_ASSOCIATION.
Locators: exact JSON pointer/array index with code, metadata language/path key,
or GeoNames member + zero-based logical TSV ordinal. The actual source field
locator is retained for parent-provided aliases/prefixes. An explicit child
listed in sub_keys and its own node is one object within that language tree;
a listed child without its own node has the parent-list locator. Do not align
different language trees by array position. Aligned sub_names/sub_lnames keys
supply positive aliases only; misalignment disables that field capability.
ISO owning country is from a complete recognized code, explicit parent from
the actual parent field where supplied. GeoNames same-record fields do not
create official entities or inferred ISO code namespaces.

Field allowlist: ISO alpha_2, alpha_3, numeric, code, name, official_name,
common_name, type, parent. Metadata: fmt, id, isoid, key, lang, languages,
lfmt, lfname, lname, locality_name_type, name, postprefix, posturl, require,
state_name_type, sub_isoids, sub_keys, sub_lfnames, sub_lnames, sub_mores,
sub_names, sub_xrequires, sub_xzips, sub_zipexs, sub_zips,
sublocality_name_type, upper, xrequire, xzip, zip, zip_name_type, zipex.
GeoNames: country_code, postal_code, place_name, admin_name1, admin_code1,
admin_name2, admin_code2, admin_name3, admin_code3. No coordinates/accuracy
enter the object/index projection. Raw reference bytes remain complete.

Every scheduled country/question gets an explicit matrix capability, including
UNRESOLVED and absent countries; ISO Q01/Q14 use GLOBAL. Scope_locator is
COUNTRY_MATRIX for those rows. Metadata rule/enumeration rows additionally
name their exact JSON node/field; effective permission requires both rows.
Missing expected capability rows/index files are fatal, not NE. Frozen public
capability observations plus these deterministic expansion rules define the
registry before implementation; no data-derived authority promotion is allowed.

Coverage_kind: CODE_NAMESPACE, FORMAT_RULE, ENUMERATED_PARTIAL, UNAVAILABLE.
Claim_scope: CODE_COUNTRY_RELATION (Q01/Q02/Q14), FROZEN_METADATA_RULE
(Q03/Q04/Q08/Q15), REFERENCE_SNAPSHOT (other questions). Granularity:
COUNTRY_CODE, FULL_ADMIN_CODE, METADATA, FULL_POSTCODE,
POSTCODE_PREFIX_RULE, REFERENCE_NAME, UNSUPPORTED. Normalization dispatch is
the fixed catalog/reference/role contract, not arbitrary registry code.
A disabled row has both authorities FALSE and basis NONE. An enabled positive
row has explicit source-field/membership basis; negative FALSE always has
basis NONE. Negative TRUE requires one of the two scoped bases above.
Street/house NONE rows have no fictional capability FK.

SOURCE_ROW evidence must resolve to exactly that Stage 8 source row with this
candidate in at least one representation slot. Its arguments reference
STAGE08_SOURCE_MAP fields using the row key carried on the evidence.
PARSER_CANDIDATE arguments reference STAGE08_COMPONENT by candidate/ordinal
or STAGE08_CANDIDATE for trusted context. MISSING_OR_AMBIGUOUS has no selected
field/ordinal and null digest; observed_role_count distinguishes zero/>1.
Empty observed values retain a locator and count one. Source raw siblings and
upstream lower copies are recoverable from the same row without extra columns.
For each performed normalization, recompute the exact string from the locator
and method; normalized_value_sha256 binds it without duplicating giant strings.
Equality uses the actual normalized bytes, never digest equality alone.

Interpretation is SOURCE_FIELD_ROLE, CONDITIONAL_PARSER_ROLE or
CONTEXT_METADATA. Origins retain SOURCE_VALUE, UPSTREAM_DERIVED_REPRESENTATION,
TRUSTED_SOURCE_CONTEXT, PARSER_EVIDENCE or MECHANICAL_INDEX. Result/witness/
country-assessment fields are REFERENCE_EVIDENCE; reference fields/provenance
REFERENCE_PROVENANCE; IDs/counts are MECHANICAL_INDEX; comparison digests are
REFERENCE_LOOKUP_REPRESENTATION. evidence_class is always REFERENCE_EVIDENCE.
Family/version/asset/capability must match the registry and selected data member.
Only NONE permits null reference fields, with NOT_EVALUABLE and configured
absence reason. rule_capability_id is required for performed Q03/Q04/Q15 at their exact
country field and Q08 at its exact admin prefix-rule bundle; it is otherwise
null. A Q08 bundle binds own-node zip and aligned parent sub_zips field
locators together, with the country rule as an explicit prerequisite. Generic
positive enumeration checks use the matrix capability plus each witness's
verified field/parent gate, without inventing a selected unique admin entity.
One real evidence row binds one exact data asset; ISO Q02
ownership is witnessed by that subdivision code, not a synthetic second asset.

witness_count counts complete record/path witnesses, not individual fields.
Zero: single_witness and match_set_id null. One: single_witness present and
match_set_id null. More than one: single_witness null and match_set_id present;
all members retained once for the equal lookup, ordinal contiguous from zero.
Witness roles: SUPPORT, CONTRADICTION, CONFLICTING_REFERENCE,
ALTERNATIVE_REFERENCE_VALUE. Alternative alone cannot establish support or
contradiction. SUPPORTED/CONTRADICTED require corresponding positive witnesses.
NOT_FOUND has zero witnesses; mismatch diagnostic does not smuggle in a negative
certificate. NOT_EVALUABLE can retain conflicting reference witnesses only for
REFERENCE_INTERNAL_CONFLICT. Members sort by complete framed Witness bytes
and exact duplicates collapse; distinct source records keep distinct IDs.
Multiple metadata rule certificates may support one scoped result; conflicting
rule results cause NE. No arbitrary first match, top-k or giant nested list.

country_assessment is COUNTRY_SUPPORTED/COUNTRY_CONTRADICTED only on witnessed
SOURCE_ROW Q02; otherwise COUNTRY_UNRESOLVED. The candidate-wide reduction is
a deterministic derived aggregate, not a second candidate truth table.

Closed reasons:
EXACT_REFERENCE_SUPPORT, EXPLICIT_RULE_SUPPORT, EXPLICIT_RULE_CONFLICT,
EXPLICIT_CODE_COUNTRY_SUPPORT, EXPLICIT_CODE_COUNTRY_CONFLICT,
VALUE_ABSENT_FROM_REFERENCE, RELATION_ABSENT_FROM_REFERENCE,
REFERENCE_ASSOCIATION_MISMATCH, MISSING_COMPONENT, AMBIGUOUS_COMPONENT_SET,
COUNTRY_CONTEXT_UNRESOLVED, COUNTRY_NOT_COVERED,
COMPONENT_CAPABILITY_MISSING, CAPABILITY_NOT_CONFIGURED,
REFERENCE_GRANULARITY_INSUFFICIENT, PATTERN_DIALECT_UNSUPPORTED,
ALTERNATE_RULE_SEMANTICS_UNSUPPORTED, NO_COUNTRY_PATTERN, NO_PREFIX_RULE,
ADMIN_IDENTITY_UNRESOLVED, COUNTRY_FORMAT_PREREQUISITE_FAILED,
REFERENCE_INTERNAL_CONFLICT, SOURCE_ONLY_QUESTION,
EXPLICIT_CODE_NOT_IDENTIFIED, TEMPORAL_SCOPE_UNSUPPORTED,
METADATA_TREE_CAPABILITY_DISABLED.

Reason precedence: NONE; then source-only; unresolved required country;
missing/ambiguous inputs; country coverage; component capability; granularity;
temporal scope; safe rule/tree; admin identity; country-format prerequisite.
Internal rule conflicts precede support/contradiction. GeoNames Q06/Q07 miss
with recorded postcode yields REFERENCE_ASSOCIATION_MISMATCH, otherwise
RELATION_ABSENT_FROM_REFERENCE. Operational failures are fatal, not reasons.

coverage_summary is genuinely aggregate, never context/candidate-grained.
summary_kind is EVALUATION, CANDIDATE_INCIDENCE, SOURCE_INCIDENCE,
OCCURRENCE_INCIDENCE or COUNTRY_ASSESSMENT; EVALUATION_REASON is the separate diagnostic breakdown.
Unused dimensions have literal ALL,
unknown country UNRESOLVED, null contradiction dimension NONE. Required
groupings and exact denominators appear in DEVELOPMENT validation below.
Country assessment uses result_state to carry the three country statuses only
for that summary_kind; otherwise only the four reference states. Rates are
derived count/denominator (null for zero); they are not stored floating truth.
Exact aggregate grouping rules:

- EVALUATION: country (each of 249 ISO codes, UNRESOLVED and separate ALL),
  evidence scope, question, reference, capability and each of the four states;
  representation ALL, reason ALL, contradiction NONE. Denominator is all
  scheduled evaluations at those dimensions, including unevaluable rows. Emit
  zero counts for all four states and zero-denominator scheduled country cells.
- EVALUATION_REASON: same dimensions, actual reason and contradiction type;
  only observed diagnostic cells. Denominator remains all scheduled checks,
  not just that reason. Never sum this grouping into EVALUATION totals.
- CANDIDATE_INCIDENCE: question/reference/capability/state; country/scope/
  representation/reason ALL, contradiction NONE. Count distinct candidate IDs
  with that result, denominator distinct candidates scheduled for that slot.
- SOURCE_INCIDENCE: the same dimensions, count distinct stable source IDs
  reached through Stage 8; denominator 35,000. Parser/source evidence and
  two equal representation candidates are not double-counted for incidence.
- OCCURRENCE_INCIDENCE: the same dimensions plus STANDARD, NATIVE or separate
  ALL; count distinct upstream (source ID, representation ordinal) with the
  state, denominator 34,822, 34,925 or 69,747 respectively.
- COUNTRY_ASSESSMENT: all dimensions ALL except result_state in the three
  country statuses and contradiction NONE; count distinct candidates after
  source-only Q02 reduction, denominator 51,779.

These are separately named overlapping incidence/grouping sets, not one
additive cube. No-candidate source-row count is computed from Stage 8 and
recorded with input totality in the manifest; no fake question/evidence row is
created. No per-source/occurrence relation is published. Stage 8 is the sole map.

## Identity, fingerprints, and ordering

Keep all Stage 6/8 IDs unchanged. Let E(tuple) be uint64 big-endian arity then
typed values: null 00; D 01 + 32 bytes; T 02 + uint64 UTF-8 length + exact bytes;
U 03 + uint64 big-endian; B 04 + byte 0/1; list/tuple 05 + uint64 count + ordered
elements. Schema field order defines struct tuple order.
H(domain, tuple) = SHA256(E(("SAFE_STAGE09", "V1", domain, tuple))).

| Identity | Exact domain and ordered input tuple |
|---|---|
| Raw reference | RAW_REFERENCE: (reference_id, sorted (role, relative_path, member_path or null, content SHA) assets) |
| Reference version | REFERENCE_VERSION: (reference_id, dataset_release, frozen edition, raw reference hash) |
| Asset | REFERENCE_ASSET: (reference_version_id, relative_path, member_path, content SHA) |
| Object | REFERENCE_OBJECT: (reference_version_id, asset_id, source_locator, object_kind) |
| Capability | REFERENCE_CAPABILITY: (all ordered capability fields except capability_id) |
| Normalized value | NORMALIZED_VALUE: (normalization_id, exact normalized UTF-8 string) |
| Question | QUESTION: (catalog fingerprint, Stage 8 logical dataset, candidate ID, evidence scope, stable source ID or null, question ID, interpretation, claim scope, ordered argument origin/field/ordinal/count tuples) |
| Lookup | LOOKUP: (reference version, asset, matrix capability, rule capability or null, question ID, claim scope, ordered (role, normalization method, granularity, actual normalized string) tuples) |
| Multi-match set | MATCH_SET: (lookup_identity, ordered complete Witness tuples) |
| Evidence | EVIDENCE: (scientific profile fingerprint, question identity, reference slot, reference version or null, matrix capability or null, rule capability or null) |

Question identity is computed, not a separate persisted relation. Exact source
IDs distinguish source-row contexts without copying source strings. The lookup
identity omits source/candidate IDs so identical complete lookups can share
work, but every original evaluation/argument pointer remains distinct.
Input hashes alone never replace full comparison/collision checks. Equal
evidence IDs with different output/witnesses are fatal nondeterminism.

The input-binding hash H(INPUT_BINDING, (...)) contains DEVELOPMENT, benchmark
fingerprint, Stage 8 manifest SHA, all bound scientific schema/contract/mapping/
logical/transitive hashes and relation counts in named sorted tuples.
Benchmark remains
014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf.
No operational mount path or inode enters scientific identity.

The reference lock is canonical JSON (UTF-8, sorted keys, no duplicate keys,
no floats; arrays have declared order). Its file SHA binds real raw provenance,
capability audit and selection. Do not put its own SHA or final Git SHA inside
the hashed lock. Raw version identity excludes derived indexes and runtime
acquisition retries; immutable edition timestamp is not recomputed per run.

Index-manifest hashes are created only during later implementation/build.
Index logical hash binds recipe/schema and ordered public object/index rows;
physical files get separate byte hashes. Registry rows do not contain their
own logical hash. Raw versions → assets/objects/capabilities → registry/index
bundle → scientific profile → evidence is acyclic.

Schema descriptors bind names/types/order/classes/invariants and exclude their
own computed hashes. Contract/catalog/normalization fingerprints bind exact
v1 rules and closed enums. The scientific profile binds those fingerprints,
the immutable public lock, registry/index logical hashes, exact semantic runtime
and exact input binding. Executable commit/runtime environment/job/host/resource
settings remain separately recorded provenance. Sharding and run timestamps
do not alter scientific identity.

Relation logical hash is H(RELATION, (name, schema hash, row count, ordered
rows)); stream using known count then independently verify count and bytes.
Dataset logical hash is H(DATASET, (scientific profile hash, sorted (relation
name, schema hash, count, logical hash) tuples for evidence/members/coverage,
bound public-pack logical hash, bound Stage 8 occurrence-view hash)).
The last is the accepted upstream view hash, not a new Stage 9 view.
External canonical merging makes batch/shard/reference-order irrelevant.
Operational caches/checkpoints are excluded from scientific relations and
recorded separately. Physical Parquet hashes may differ across layouts while
logical identities remain equal.

## Bounded execution and eventual production scale

Use Python 3.14.3 / Unicode 16.0.0, PyArrow 25.0.0 and DuckDB 1.5.5 as the initial
profile, matching accepted Stage 8 semantics. No pandas, Polars, pycountry,
new parser, Python address-validation package API, or distributed orchestration
framework is needed for v1. Record the complete runtime lock and DuckDB/RE2
build identity; changing semantic runtime versions requires profile review.

The execution design is bounded batch processing with explicit external sorts:

1. Fail-closed site/split/path/runtime/reference-lock guards run before protected
   input access. Verify the complete accepted Stage 8 binding and counts.
2. Stream Stage 8 source-map keys/geographic columns; schedule each distinct
   source-row/candidate pair once. Stream candidate metadata for parser-scoped
   evaluations. Do not persist a new source/occurrence/context map or copy text.
3. Stream the ordered component relation once, using label/ordinal and role
   counts to generate atomic questions and singleton relationship questions.
   Spill per-candidate questions as needed. Retain at most fixed role counters,
   singleton pointers, and byte-bounded batches, never a candidate-sized list
   of Python dictionaries or a cross-product of components.
4. External-deduplicate complete lookup identities and exact normalized keys.
   Execute batch joins against read-only country/key-partitioned reference
   indexes. Reuse lookup match sets across candidates/contexts while retaining
   every evidence origin; all occurrence links remain in Stage 8. A different source row cannot reuse
   a country-dependent result unless all lookup inputs/capabilities agree.
5. Write deterministic relation shards, validate foreign keys/totality with
   bounded joins and replay semantics, derive coverage, then publish once.

Default DEVELOPMENT profile: one process, four DuckDB threads total, four
requested CPUs and 32 GiB job memory; DuckDB memory cap 8 GB, Arrow byte target
64 MiB, target Parquet row group 64 MiB and file size 512 MiB. These are proposed
resources, not an authorized SLURM submission. Metadata dictionaries are below
64 MiB per process; country/association indexes use read-only file-backed
DuckDB/Parquet scans and the shared OS cache, not one full Python copy per worker.
Bounded reference-index size is measured before job review.

Logical shards use the high 12 bits of candidate ID for evidence, and
lookup_identity for multi-match members. Source scan partitioning uses stable
source ID as an operational key, without a persisted mapping relation. DEVELOPMENT may group adjacent
logical shards into 16 physical task groups; output still uses canonical
relation order. Any physical partitioning needs an external canonical merge
for logical hashing (evidence IDs are not ordered by candidate ID).
Never assume file discovery or completion order is canonical. Shard count,
task grouping, resource caps, and row groups are operational, not scientific.

One giant scalar can exceed a target batch: admit it alone and process its
full UTF-8 value through bounded hashing/comparison buffers; Parquet uses
large_string and one-row groups when required. Do not split an input into
semantic substrings or use size to emit NOT_EVALUABLE. If the exact scalar
cannot be processed under reviewed resource limits, the publication fails and
resources are reviewed before any new run. Stream all matches to shared
match-set relations; no giant nested witness array or top-k loss.
The resident-state bound is O(largest scalar + fixed batch buffers + bounded
engine/metadata caches), independent of source-population size. Whole-value
Unicode normalization may require one complete scalar and temporary copies;
do not claim constant scalar-independent memory. Reference names/patterns have
known maximum sizes after public preparation; a size difference may reject
exact equality without allocating a reference-sized cross product, but the
complete original input/identity remains preserved. Resource sufficiency for
an actual scalar is an execution gate, never a semantic size-based abstention.

Spill is owner-only approved personal `/work` or a validated compute-node
temporary filesystem; never `/scratch` or shared public storage. Disk preflight
reserves at least 3× estimated spill/output plus raw/index inputs. Exhaustion,
memory-limit errors, or an I/O failure is fatal, with attempts preserved.

Workload estimates from accepted aggregate counts only:

| Quantity | DEVELOPMENT | Production planning scenario, not measured |
|---|---:|---:|
| Source rows | 35,000 | 141,048,582 fixed population |
| Occurrences | 69,747 | about 281.08M at DEVELOPMENT availability; hard ceiling 282,097,164 |
| Unique candidates | 51,779 | about 208.67M at DEVELOPMENT ratio; cannot exceed occurrences |
| Distinct source-row/candidate scopes | ≤69,747 | ≤occurrences |
| Parser + source scopes | ≤121,526 | about ≤489.74M in ratio scenario |
| Ordered parser components scanned | 6,106,088 | naive ratio 24.61B; giant-heavy diagnostic, not a capacity prediction |

Each source-row/candidate scope has 14 questions/18 scheduled evaluations. Parser contexts
have a constant base/relationship set plus linear atomic work: at most three
reference evaluations per relevant raw component, plus at most 19 placeholder/
constant evaluations per candidate (a conservative bound). DEVELOPMENT thus
has an upper planning bound of about 20.56M evaluation rows before exact lookup
reuse, using 18×69,747 + 3×6,106,088 + 19×51,779. This is not an expected hit
count. Question/evaluation lineage can still be large despite few unique
lookups. At 0.2–0.5 KiB/evaluation plus keys/witnesses, reserve roughly 10–30 GiB
DEVELOPMENT output/spill pending public/synthetic measurement. No protected
pilot is needed to choose semantics. Production may require multi-terabyte
output and a separately reviewed multi-job plan; 24.61B components alone rules
out treating production as a small in-memory DEVELOPMENT job.

Complexity is O(source rows + parser components + generated questions + actual
distinct-lookup witness memberships), plus external sort/join costs. There is
no address×world scan, component-pair explosion, per-row network traffic, or
population-sized Python state. Production cannot inherit DEVELOPMENT resource
requests or execution authorization. No promise of throughput or MaxRSS is
made before a real authorized benchmark.

### Restart/resume without duplicate scientific work

Each shard checkpoint records attempt ID, exact Stage 8 binding, profile and
pack fingerprints, executable SHA, logical shard interval, input range hashes,
output file hashes/counts, schema fingerprints and checkpoint state. Fsync the
completed checkpoint before its completion marker. An unfinished checkpoint
is never trusted and cannot expose run-level success.

A restart creates a new attempt, leaves the failed attempt unchanged, and
read-validates reusable complete shards with the identical execution/scientific
binding. Copy them as new owner-only files; do not hardlink mutable failure
trees. The final manifest records their original jobs and checkpoint ancestry.
Reject overlapping ranges, missing ranges, stale packs or mixed executable
checkpoints. Recompute incomplete shards only under the authorized restart;
do not launch a duplicate full job while a submitted job is pending. Logical
results must equal an uninterrupted run. A successful final run is reopened
and reused rather than rerun for convenience.

## Privacy, operational failure, and publication

Protected values, source IDs, selected reference match sets, and all arguments/
keys stay on controlled local/Goethe infrastructure. No protected strings in
prompts, web requests, Git, errors, stdout/stderr, or log filenames. Public
research in this design session used only public metadata and documentation.
No credential is required by Stage 9. Protected execution has network disabled;
do not invoke even a cached library API capable of lazy HTTP fetching.

Full DEVELOPMENT and any future production processing are Goethe-NHR SLURM
only. Entry points invoke the shared guard before input access and require
`SAFE_EXECUTION_SITE=goethe-nhr` and a nonempty `SLURM_JOB_ID`. Verify exact
clean pushed executable SHA, authorized DEVELOPMENT scope, allowlisted bound
paths, and owner-only topology. Reject HOLDOUT/non-DEVELOPMENT inputs before
reading payloads. There is no local protected/production bypass. Login nodes
are orchestration-only; do not modify `/work/footprint/public` or shared Conda.
Code arrives via Git, never rsync or a dynamic job-side pull.

Fatal conditions include every binding/hash/schema/permission/path mismatch;
missing/duplicate/cross-wired keys or arguments; unknown result/reason;
reference corruption; inconsistent same-ID results; dropped/truncated giant
values; skipped inputs; unexpected reference/network calls; guard failures;
disk/memory/read/write errors; and validation/publication failure. These never
become address evidence. Errors use fixed codes and aggregates; no arbitrary
exception text containing input values is printed. Missing capability declared
in the frozen registry is ordinary scientific abstention; a missing supposedly
present index is fatal.

Publication reuses the accepted Stage 8 terminal model:

Future final artifact topology (all names below are design declarations):

```text
<controlled-stage09-development-root>/<new-run-id>/
  <each-protected-relation-name>/data/part-*.parquet
  metadata/stage09_schema_contract.json
  metadata/stage09_question_catalog.json
  metadata/stage09_reference_pack_binding.json
  stage09_reference_manifest.json
  _SUCCESS.json
```

The reference binding points to a separate immutable public-input pack manifest
and its object/index files and complete raw snapshot inventory. Attempts
hold `_IN_PROGRESS` and checkpoint state. Final relation completeness is checked
against the exact schema bundle; unexpected files/relations fail validation.
Checkpoints retained in failed attempts are provenance, not final scientific
relations. No filesystem subtree is discovered dynamically as an input.

```text
new private sibling attempt + _IN_PROGRESS
  -> deterministic relations/checkpoints
  -> complete science/integrity validation
  -> manifest + file/tree fsync
  -> independent prepublication reopen while still IN_PROGRESS
  -> _SUCCESS.json, remove _IN_PROGRESS, fsync attempt
  -> atomic rename into new final run, fsync parent
  -> complete final reopen and validation
  -> final same-invocation no-follow ownership check
  -> materializer returns publication success
```

Markers in the private attempt are not reader-visible published success.
Readers require the final immutable run path, valid `_SUCCESS.json` bound to
manifest SHA and logical dataset hash, absent `_IN_PROGRESS`, and successful
non-mutating reopen validation. All directories are 0700 and files 0600; no
symlinks, output overwrite, or collision adoption. An existing final run can
be validated/reused by a separate read-only invocation, never attributed to a
new writer by content equality alone.

On an ambiguous rename-then-exception, only FINAL-only state with the captured
same-invocation attempt ownership may be adopted after parent fsync and full
final reopen validation. Both-path/neither-path/wrong-identity states fail.
Only currently owned failure trees may be demoted to no success marker plus
IN_PROGRESS; unrelated paths are preserved. Finish fallible outcome construction
and umask restoration before the final no-follow ownership check. After the
materializer returns, serialization/stdout/flush failures cannot demote the
publication or change program-controlled exit success. External kill/power loss
is reconciled by reopening filesystem state, not inferred from scheduler exit.

The device/inode test is **within the publishing invocation only**. A different
job validates persistent paths/topology, content/schema/logical hashes, marker
bindings, modes and symlink policy. It must never demand equality to a historical
cross-job device/inode number. Do not introduce the rejected exact-inode gate
or an unsupported filesystem primitive as a replacement publication design.

The manifest records exact Stage 8/transitive bindings; executable/review SHAs;
contract/profile/schema/catalog/normalization/registry/dependence fingerprints;
every reference release/asset/index/license hash; relation counts and logical/
physical hashes; complete runtime/environment lock; actual job/checkpoint
provenance; resource settings/metrics; privacy/network guards; and all validator
outcomes. Raw payloads, row values, selected IDs, and credentials are absent
from portable manifest summaries. Full manifests with controlled topology stay
controlled; allowlisted summaries alone enter Git.

## Tests required before execution

These are a test design, not tests already run. Fixtures are synthetic and
independent of protected DEVELOPMENT addresses. Public-reference contract
tests are distinct from synthetic authoritative-reference fixtures.

| Group | Required cases and pass assertions |
|---|---|
| A: four states | One independently specified fixture for each state; unsupported/missing argument is NOT_EVALUABLE; open miss NOT_FOUND; positive match SUPPORTED; witnessed authorized conflict CONTRADICTED. Exhaustively reject all invalid state/type/witness/authority combinations. |
| B: capabilities | Supported/unsupported country, present country with missing component, partial hierarchy, field-level absence, disabled country, ZZ defaults, truncated postcode granularity, missing scheduled capability row fatal, missing index fatal. No fallback to another reference. |
| C: postcodes | Leading zeroes, ASCII spaces/hyphens, Unicode spaces/hyphens/digits retained, JP/PL/PT/BR/SE/CZ/SK allowed separators and wrong-position cases; US extended ZIP never reduced; CA/GB/NL and other declared truncated populations abstain; impossible format; format-supported/reference-missing; same-record postcode/locality support; different-place GeoNames hit stays NOT_FOUND/REFERENCE_ASSOCIATION_MISMATCH. A test-only authoritative exclusive postcode/locality relation may contradict only with positive identity, exact level/time/coverage certificate and no compatible alternative; the real v1 profile must reject that test registry/authority. |
| D: multilingual | Native and reference Latin aliases separate, diacritics retained, NFC composed/decomposed comparison, Turkish dotted I/context-sensitive lowercase, mixed script, homonyms, no generated transliteration, no cross-language positional alias pairing, tilde empty positions and misalignment. |
| E: country | Full ISO source subdivision code agreeing/conflicting with trusted country; same values from parser cannot set geographic assessment; code recognition alone unresolved geographically; unsupported/historical/territory codes not remapped; conflicting/partial occurrence provenance abstains; mixed context witnesses produce unresolved summary; source country unchanged. |
| F: determinism | Exact rerun; change batch/row-group/task/shard layout/completion order; permute reference traversal; compare every logical relation hash/ID; same lookup shared across multiple origins without merging evaluations; deliberately mocked hash collision fails. |
| G: lineage | Every evidence→Stage 6 candidate and exact Stage 8 argument locator; every witness→exact pack/version/family/field; all 35k source rows and 69,747 occurrences; same-row equal STANDARD/NATIVE preserves two occurrences; two countries for one text cannot contaminate context; both-absent source row retained. |
| H: prohibited inference/privacy | Static/output allowlists reject corrections, query, coordinates, validity/final match, score or parser readiness; NOT_FOUND cannot enter contradiction/country-negative reduction; parser agreement never promoted to source truth; fake OSM/Pelias OSM share lineage; unknown ancestry yields no independent vote; canary protected strings never reach logs/reports/errors; offline network attempts fail. |
| I: publication faults | Interrupted data/manifest writes, prevalidation failure, pre-success interruption, marker/fsync failure, actual rename then raise, parent-fsync failure, final validation failure, byte-identical unrelated replacement, symlink/collision, idempotent owned-only demotion, stdout/flush errors after return, independent-job changed inode with identical persistent content, reopen corruption. No failure tree is published as success. |
| J: scale/resume | Giant scalar and 881,338 synthetic components under tiny batch targets, repeated-role questions abstain without Cartesian expansion, huge homonym set streamed once, external sort/spill limits, interrupted checkpoint, correct shard adoption into new attempt, stale/mixed/overlapping checkpoint rejection, complete coverage vs uninterrupted run. |
| K: reference build | Pin/member/hash/license/schema failures, TSV logical-record parsing (not physical-line inference), input country granularity exclusions, all enabled regex examples and differential full/prefix semantics, alternation anchoring, unsupported regex/alternate-rule downgrade, data defaults, explicit hierarchy, absence never upgraded by measured coverage. |

Use pytest/PyArrow synthetic fixtures and independent expected truth tables;
avoid constructing expected outputs by calling the same evaluator under test.
Full regression suites for accepted stages are not a new scientific audit;
implementation runs relevant compatibility checks without changing their pins.

## DEVELOPMENT evaluation and acceptance gate

After design approval, public pack lock completion, implementation review,
synthetic gates, and separate exact-workload authorization, submit one complete
DEVELOPMENT job. Reuse its immutable artifact for all validation/review; never
rerun merely to get a different evidence rate. HOLDOUT remains sealed.

Required full-population machine validation:

- Exact input binding, candidate/source/occurrence totality, all foreign keys,
  source-row/candidate membership, question scheduling, argument locators/values, reference
  version/family/capability identity, four-state logic and all fingerprints.
- Full ordered Stage 8 component scan accounting, including ignored labels,
  duplicates, giants and empty parses; no candidate/occurrence is omitted.
- Complete independent recomputation of state/witness constraints and country
  reduction. Zero unauthorized contradictions, source changes, parser-truth
  promotions, final-truth fields, network/geocoder/parser calls, or leakage.
- Reopen successful publication and bind measured wall time, MaxRSS, spill,
  batch/scalar maxima, generated questions, unique lookups, witness sizes,
  checkpoint reuse and cache reuse. Do not infer production readiness solely
  from DEVELOPMENT elapsed time.

Diagnostics must have explicit numerators/denominators and counts before rates:

1. By trusted country (including UNRESOLVED), question/component type, reference,
   family, evidence scope and representation: scheduled, evaluable and each of
   SUPPORTED/CONTRADICTED/NOT_FOUND/NOT_EVALUABLE counts. Four-state rates use all
   scheduled checks; conditional rates over evaluable checks are separately
   named. Zero denominators produce null rates, never zero success.
2. Country/reference capability matrix: configured availability and observed
   evaluability, granularities, missing components, ambiguous parser-role counts,
   country-provenance prerequisites and other abstention reasons. Report per-
   country coverage even when evaluability is zero.
3. Reference-family/lineage usage, unique lookups versus linked evaluations,
   normalization/alias-role usage, same-family duplication, contradiction-type
   and claim-scope distributions, and country assessment/conflict distributions.
4. Candidate incidence: for each state/question/reference, number of distinct
   candidate IDs with at least one such result divided by all candidate IDs
   scheduled for that question. State incidences may overlap and do not sum to
   one. Do not call a candidate with one support globally supported.
5. Source/occurrence views: map back without adding source and parser evidence
   as votes; deduplicate (source ID, question_catalog_id, reference_slot, state) for source
   incidence. Report denominator 35,000 and explicit no-candidate rows. Preserve
   occurrence denominator 69,747 and separate STANDARD/NATIVE views. Candidate,
   evaluation, occurrence and source counts must never be interchanged.

These measure reference behavior and evaluability, **not final address accuracy,
deliverability, geocoding success, or global validation**. No minimum SUPPORTED
rate is an acceptance gate; no contradiction quota is a target. Broad honest
NOT_EVALUABLE coverage is preferable to an unsupported capability claim.

All detailed country/component rates remain controlled. Portable summaries use
fixed allowlisted fields and the repository's approved disclosure rules. Until
an exact country-cell release policy is approved, publish only global aggregate
counts and the public reference capability matrix; do not improvise suppression
that permits subtraction/reconstruction of small protected cells. The required
full country diagnostics still exist in the controlled review artifact.

Qualitative evaluation uses the existing fixed 500 source identities, fingerprint
`014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52`.
After separate authorization for protected human review, a local/Goethe human
reviewer inspects a new immutable Stage 9 view alongside exact source/derived/
parser origins and public witnesses. No protected text is sent to an LLM.
Judge whether each displayed claim is supported at its stated scope, whether
abstention is appropriate, and whether a contradiction has a positive basis;
do not label the whole address correct/incorrect. Review all contradictions in
that fixed view and a deterministic supplementary maximum of 200 distinct
contradiction evidence IDs outside it, ordered by
`H("CONTRADICTION_REVIEW", (evidence_id,))`. Freeze that selection before human
labels; report a shortfall if fewer exist. This is risk review, not a random
population accuracy estimate. All evidence in giant cases remains accessible
through pagination, never truncated in storage; reviewed portions/unknowns
must be explicit.

Acceptance requires zero unresolved contract, authority, lineage, privacy,
publication, or confirmed false-contradiction defects. Human uncertainty about
a geographic address is not by itself a defect in correctly scoped evidence;
uncertainty about the validity of a claimed negative-authority rule is a defect
to resolve before acceptance. A reproducible defect rejects the exact candidate
and yields an explicitly reviewed correction/new immutable run, preserving
failed evidence. Never tune source transformations or thresholds to improve a
desired support rate; no fuzzy threshold exists here.

A fresh independent reviewer uses the exact candidate and reopens the single
artifact, independently checks hashes/totality/semantics, challenges all safety
and publication invariants with synthetic faults, and verifies the fixed review
protocol and sanitized reports. Stage 9 may be accepted only after that review
and explicit owner acceptance. Neither this design nor acceptance authorizes
production Stage 9, Stage 10, Stage 12, or geocoding.

## Stage 10 handoff and boundary sufficiency

Classification: **BOUNDARY_HANDOFF_SUFFICIENT**.

This follows from accepted schemas/code, without reading protected strings:

- Stage 8 `source_candidate_map` retains stable source ID, original provider
  ID/file/logical record/source hash and STANDARD/NATIVE candidate links.
- Stage 8's manifest binds the exact Stage 6 row-map artifacts and hashes.
- The Stage 6 row map preserves the complete Stage 5 schema; Stage 5 preserves
  Stage 4/3/raw source fields. Thus raw `street_address_line_1` through `_4`
  and `street_address_line_1_native` through `_4_native`, plus corresponding
  `stage03_clean_*` and `stage04_lower_*` fields, remain separately recoverable.
- Stage 5 contributing-line masks/counts and separate case-preserving/lower
  candidates remain available. Gaps, repeated lines, line position order and
  representation membership are retained. Exact candidate-ID linkage supplies
  the accepted whole string in parallel with parser evidence.

Stage 10's boundary-preserving access path is:

```text
Stage 9 candidate evidence + optional stable_source_row_id_v1
  -> authoritative Stage 8 source/occurrence map
  -> exact manifest-bound Stage 6 row map by the same stable ID
  -> representation-specific raw / clean / lower lines 1–4 + Stage 5 masks
```

A future Stage 10 validator must prove source-ID totality, exact candidate-slot
equality, expected line-field schemas and Stage 6 binding before generating any
hypothesis. It must not reconstruct line boundaries by splitting the Stage 6
whole string. Numeric adjacency and within-line ambiguity may remain; access
to original boundaries does not claim that every boundary is semantically good.
No Stage 8 line duplication or second Stage 9 mapping is needed for convenience.

`stage09_stage10_handoff_v1` exposes the immutable input bindings, all Stage 8
evidence/pointers, original source and parser arguments, every reference state/
reason/capability/witness/alternative, dependence lineage, country assessments
with scope/basis, coverage summaries, and exact bindings to Stage 8 source/occurrence links.
It exposes no preferred representation, correction, selected component set,
Pelias request or final result. Stage 10 may design a controlled hypothesis
ladder using this evidence, but must preserve whole-string and boundary lineage
and never treat NOT_FOUND as invalid or SUPPORTED as parser correctness.

No Stage 0–8 scientific, schema, fingerprint, or materialized-artifact change is
required. Stage 7 boundary weaknesses are accepted evidence limitations and
are not Stage 9 repair work. The current Stage 19 acceptance plus separate
exact-workload geocoding gate remains unchanged by prospective numbering.

## Owner revision ledger and bounded final review

The original uncommitted draft's 24-item self-review is superseded by this
owner-directed bounded revision, not relabeled as independent acceptance.

| Owner requirement | Incorporated design decision |
|---|---|
| R1 concrete lineage | ISO_CODES, LIBADDRESSINPUT_METADATA, GEONAMES_POSTAL; authoritative names reserved |
| R2 difficult contradictions | Separate explicit positive/negative booleans; only exact ISO ownership and eligible frozen regex/prefix predicates can contradict |
| R3 current suitable freeze | Inspect releases and actual content, compare ISO changes, freeze actual members/hashes/licenses; no refresh within an execution |
| R4 minimum model | Six justified logical relations; source/occurrence authority remains solely Stage 8; bounded pointers/witness structs replace intermediary tables |

The bounded post-acquisition review collected all nine requested risk classes
together and resolved the complete defect ledger in the
[freeze report](STAGE09_REFERENCE_FREEZE.md). This is design/public-reference
validation, not materializer testing, independent stage review or acceptance.

Implementation and protected execution remain NOT STARTED. Stage 0–8 science,
schemas, source and fingerprints remain unchanged. HOLDOUT stays sealed;
production and Pelias are untouched.

NEXT: STAGE 9 IMPLEMENTATION + SYNTHETIC TESTS + DEVELOPMENT RUN
