# Stage 10 — query families, eligibility and suppression

Part of the [review-candidate scientific contract](STAGE10_MULTI_HYPOTHESIS_QUERY_GENERATION.md).
All rules here are proposals for owner approval; no materializer or queries exist.
`Q1`–`Q7` below are Stage 10 family IDs. `S9.Q04`, for example, denotes the
different Stage 9 reference-question namespace.

## Common gates and conservative formatting

All input-integrity gates precede scientific selection. Hash/schema/FK/ordinal
corruption, missing expected evidence, runtime failure and resource exhaustion
are publication-fatal, never scientific absence or candidate exclusion.
Preserved empty parses, unknown labels, ambiguous roles and warnings are valid
upstream states; they are not file corruption.

Ordinary hypotheses require a nonempty accepted exact candidate and
`COUNTRY_UNANIMOUS_VALID` with a non-null trusted code. That explicit alpha-2
country boundary is mandatory for Q1–Q6. It is not inferred from script, parser,
Stage 9 lookup frequency or absence of contradictions. Stage 9 country
assessment success is not required. A recognized source country stays strong
context even if reference evidence challenges it. No ordinary family drops,
substitutes or silently broadens that country boundary.

Formatting version `stage10_exact_query_format_v1`:

| Surface | Exact operation |
|---|---|
| Source and accepted representations | Never modify them. References retain derivation level. |
| Q1/Q2 baseline | Exact UTF-8 encoding of `stage06_candidate_lower`; no new Unicode normalization, whitespace collapse, trim, case change, accent removal or punctuation rewrite. |
| Q3 source-line alternate | Exact lower-line bytes in source position order; join nonempty slots with a single U+000A LF. No punctuation insertion or stripping. |
| Q4 `address` | Entire exact Stage 6 candidate, including disputed postcode-like text if present in that line body. |
| Q4 other text fields | Exact unanimous Stage 3 clean source string, including leading zeros in postcode. Stage 9 normalization is a comparison method, never a replacement query value. |
| Q5 | Remove only qualifying complete source-line occurrences, then join remaining nonempty lower lines with U+0020. No substring/token deletion within a surviving line. |
| Q6 | Explicit NFC → one named script transform → NFC; only in this alternate. No NFKC/NFKD, Latin-ASCII, casefold, translation or abbreviation expansion. |
| Request transport | Stage 11 losslessly serializes query intent; percent-encoding/escaping must round-trip exact strings, including LF. No server-equivalence assumptions justify local duplicate collapse. |

Empty source slots do not become empty query fields. Null means omitted only
where the intent schema specifies omission; null is distinct from empty string.
Nonempty giant input is never truncated. Unexpected forbidden transport/control
characters are retained in evidence and flagged for Stage 11 QA, never silently
deleted. Malformed UTF-8 cannot occur in a conforming accepted input and is fatal.

## Family table

| Family | Maximum constructions | Required evidence beyond common gates | Query intent |
|---|---:|---|---|
| Q1 FULL_STANDARD | 1 | At least one STANDARD occurrence | `/v1/search`, full candidate as `text` |
| Q2 FULL_NATIVE | 1 | At least one NATIVE occurrence | `/v1/search`, full candidate as `text` |
| Q3 BOUNDARY_PRESERVING | 1 | Exact all-occurrence lower-line-vector unanimity | `/v1/search`, LF-joined lines |
| Q4 SOURCE_ANCHORED_STRUCTURED | 1 | At least one eligible source postcode/locality field under the rules below | `/v1/search/structured`, full `address` plus eligible fields |
| Q5 UNIT_FLOOR_STRIPPED_SECONDARY | 1 | Unanimous boundaries plus whole-line lexical and exact parser corroboration | `/v1/search`, remaining lines joined by space |
| Q6 NATIVE_TRANSLITERATION_ALTERNATE | 1 | NATIVE membership and one supported script; full baseline retained | `/v1/search`, one transliterated full native candidate |
| Q7 COUNTRY_DIAGNOSTIC_DEFERRED | 0 | Disabled in this Stage 10 profile | No request; later-phase boundary only |

Q1/Q2 are universal **within available representations and resolved unanimous
source context**. Q3–Q6 are conditional. Failure to meet a family gate is an
auditable abstention, not address invalidity. All active request intents use
the same explicit country and the same frozen retrieval-policy reference; no
family varies language, layers, sources, focus or size to multiply requests.

## Q1/Q2 — exact full baselines

STANDARD and NATIVE are occurrence provenance, not competing truth labels.
Both families use the existing exact candidate. When both occur for one
candidate they yield one identical request intent and one hypothesis with two
family memberships. On a source row with different candidate IDs both full
baselines remain available, subject to each candidate's country gate.

There is no representative source row, clean-text casing choice, parser
reconstruction, recipient/building deletion or appended external geography.
The full native lowercase candidate remains exact; the accepted lowercasing
history is explicit and is not described as untouched raw native text.

## Q3 — accepted source boundaries

Resolve all occurrences through Stage 8's view to the exact Stage 6 row map.
For each occurrence take the four lower-line slots for its representation;
check availability, count, mask and space-joined equality with Stage 5 and
the Stage 6 candidate. Compare the **entire four-slot vector**, not just its
joined text, across all candidate occurrences. Gaps and repeated lines count.

If there is more than one vector, suppress Q3 with
`SOURCE_BOUNDARY_NONUNANIMOUS`. Selecting a modal or first vector is prohibited.
For one vector, join nonempty positions with LF. Preserve the original mask,
slot indices and complete all-occurrence lineage through a selector certificate.
No line is assigned a semantic role, and no line is split on commas, numbers
or parser labels. A one-line output normally converges with the full baseline.

Fictional example: lower slots `['12 example road', '', 'unit 5', '']` produce
`12 example road\nunit 5`, with mask `1010`. LF is a query hypothesis about
layout, not proof of a postal component boundary. Stage 5's rejected primary
comma-space reconstruction remains rejected; no upstream contract is changed.
Whether Pelias distinguishes LF from space is later empirical evidence. Until
the complete request contract explicitly proves equivalence, these are distinct
exact request strings. Stage 11 may reject unsupported transport; it may not
silently turn Q3 into a different query.

## Q4 — source-anchored structured hypothesis

Use `address = stage06_candidate_lower` intact. Do not assign a parser street,
house, house number, suburb, city district, island, state district, country
region, PO box, category, near or unknown label to a trusted structured field.
Keeping the whole line body in `address` asserts no parser street/house split.
It is still an experimental structured query, never a source correction.

For each source geographic field, exact all-source-row nonempty unanimity at
the **Stage 3 clean** level is necessary. Empty/partial or unequal values do
not pass, even when their normalized lookup keys coincide. Predicate evidence
is restricted to `SOURCE_ROW` rows for this candidate and the very same source
field. Each required support must exist for every distinct source row.

Evaluate locality first, postcode second, without enumerating field subsets:

1. **Locality L:** unanimous `stage03_clean_city`; at least one S9.Q09
   SUPPORTED witness at an explicit locality/place level, from enabled
   LIBADDRESSINPUT_METADATA `FORMAT_LOCALITY` or GEONAMES_POSTAL `place_name`.
   Admin, dependent-locality, suburb and parser-city evidence cannot substitute.
   Different source rows may have different recorded witnesses; this establishes
   compatible source-field use, not selection of a unique geographic entity.
2. **Postcode P:** unanimous `stage03_clean_postcode`; S9.Q05 SUPPORTED with
   FULL_POSTCODE granularity and positive authority in GEONAMES_POSTAL.
   An applicable source S9.Q04 FORMAT_RULE_CONFLICT or source S9.Q08
   PREFIX_RULE_CONFLICT vetoes **structured P only**. If L is eligible,
   S9.Q06 must also be SUPPORTED on the same source postcode/locality tuple
   and same-record postal witness. Otherwise omit P deterministically; retain L.
   If L is unavailable, positively supported P alone can accompany `address`.
3. Include the eligible fields together, once. If neither survives, suppress Q4
   with `INSUFFICIENT_TRUSTED_STRUCTURED_EVIDENCE`. No country-only or
   `address`-only Q4 is generated merely to fill this family slot.

**Region/admin and structured country text are always omitted in v1.** Country
is supplied by the explicit boundary. The source `region_in_country` field and
Stage 9 admin-name matches do not establish a universally valid Pelias region
level. No source line is repurposed as city/admin, and no public reference
alternative is inserted into any query. Region exclusion records
`ADMIN_LEVEL_NOT_ESTABLISHED`; parser geography exclusion records
`PARSER_ONLY_FIELD_EXCLUDED`. These are visible field decisions, not hidden
defaults. Their coverage cost is an owner-review issue.

Parser values may be reported as concordant evidence through their exact
ordinal selectors, but cannot change Q4 eligibility, populate its fields or
override a source/reference gate in this version. Concordance is descriptive,
not an independent confirmation. Neither PARSED_NONEMPTY nor warning absence
is trust. This deliberately narrow v1 avoids reviving the rejected Stage 7
readiness gate; broader parser-origin structured fields require a new design.

## How Stage 9 evidence influences queries

| State | Allowed Stage 10 effect | Prohibited inference |
|---|---|---|
| SUPPORTED | Enable the precise Q4 source-field use above after role, scope, country, granularity, authority and witness checks | Correct parser label, valid address, unique place, independent vote |
| CONTRADICTED | Source S9.Q04/Q08 veto structured postcode; S9.Q02 informs only the deferred country diagnostic boundary | Delete source content, change source country, veto unrelated parser/source fields |
| NOT_FOUND | Positive-support requirement remains unmet; full text remains available | Invalidity, contradiction, geographic exclusion |
| NOT_EVALUABLE | Prerequisite/capability abstention; full text remains available | Negative evidence or absence claim |

For a negative gate, verify actual capability/rule IDs, negative authority,
contradiction type, witness and argument locators against the accepted Stage 9
contract. GeoNames negative authority is FALSE; a GeoNames CONTRADICTED row is
an upstream-integrity failure, never an eligible gate. Missing expected evidence
is fatal; a present NOT_EVALUABLE row is a scientific limitation.
For Q4, a SOURCE_ROW REFERENCE_INTERNAL_CONFLICT on any question/argument tuple
used for a field vetoes that field's inclusion, even if a different reference
supports it. This records insufficient structured evidence, not negative
geographic authority. Unrelated internal conflicts cannot veto the field.

Parser S9.Q04 contradictions, including repeated ordinals, **cannot veto a
source-derived postcode**, even if text happens to agree. Source Q04/Q08 may
omit only the structured postcode field; postcode-like text inside the full
`address` remains intact. No general postcode-deletion family is proposed.
Any diagnostic removal from free text would need an exact lineage-scoped new
rule; this version has none. There are no numeric down-weighting scores here.

The accepted 54,022 / 90,043 = 59.995780% S9.Q04 conflict rate is at evaluable
reference-rule grain, not candidate/address grain. Repeated parser components
remain counted in upstream evidence, but generate no repeated hypotheses and
no extra support or contradiction votes. Preserve ISO shared ancestry with
Stage 7, libaddressinput mirror lineage and possible GeoNames/Pelias overlap.
Evidence families, aliases, source/parser duplicates and representation
convergence never supply additive independent confirmations.

## Q5 — unit/floor alternate only

Proposed conservative v1 removal categories are **PARSER_UNIT (`unit`) and
PARSER_LEVEL (`level`) only**, mechanically corroborating whole source lines.
`house`, `house_number`, `road`, `staircase`, `entrance`, `po_box`, recipient-like
text and all other/unknown labels are excluded from removal. No parser offset
is assumed to exist in Stage 8.

Require Q3's unanimous four-slot vector, PARSED_NONEMPTY, and
NO_STRUCTURAL_WARNINGS_DETECTED. Warning absence is only a necessary risk
screen; the independent source-line and lexical gates below must also pass.
All input code points must have Unicode 16 Script in {Latin, Common, Inherited}.
This enables only literal English marker forms, not inferred source language.

For a complete nonempty lower line, the entire string must full-match one
grammar, with exact ASCII spaces, letters and digits:

```text
UNIT := (unit|suite|apt|apartment) U+0020 [0-9]+[a-z]?
LEVEL := (floor|level) U+0020 [0-9]+
```

No punctuation variants, signed/ranged/roman floors, building names, isolated
numbers, abbreviated periods or embedded markers are accepted. There are no
country-wide English lexical substitutions. The grammar is a deliberately
narrow alternate-hypothesis rule, not a universal definition of subpremise.

Independently align the entire ordered raw component sequence to exact
nonoverlapping substrings of the candidate. Compute the earliest monotone
embedding left-to-right and the latest monotone embedding right-to-left. Every
component must be nonempty and both embeddings must exist and agree at every
ordinal; otherwise Q5 abstains with UNIT_ALIGNMENT_AMBIGUOUS (empty components
use PARSER_EVIDENCE_UNUSABLE). This proves a unique mechanical ordered alignment,
not correct labels. Two monotone scans and an external ordinal reconciliation
avoid searching every component against the entire candidate repeatedly.
These derived offsets are Stage 10 evidence, never asserted to exist in Stage 8.

For each grammar-matching line, require exactly one aligned raw component whose
entire exact value and code-point interval equal that line, with corresponding
UNIT/LEVEL label. No other aligned component, including an unknown label, may
intersect the removal interval. Locate source intervals using accepted
space-join offsets, not parser reconstruction. Repetition is retained at exact
ordinals; it never creates extra hypotheses or support votes. Missing or
nonunique exact whole-line corroboration suppresses Q5.

If a grammar-matching line fails corroboration/alignment, suppress the whole
family; do not choose a favorable subset. Otherwise remove all qualifying
lines together, at most four; keep every other line intact and in order. At
least one surviving line must contain a Unicode letter and an ASCII digit;
this is only a content screen, not a point-address validity claim. No matching
line or failure of that surviving-line screen means `FAMILY_INELIGIBLE`;
empty remainder takes precedence over that screen and means
`EMPTY_RESULT_AFTER_TRANSFORMATION`. Join survivors with U+0020.

Record exact removed source slot, code-point interval, category, grammar ID,
component ordinal and selector commitment to all tested components. Never
strip an already structured or transliterated query, never feed Q5 into Q6,
and never replace Q1/Q2. A legitimate building named “Unit 5” remains a risk
even under these gates; full text survives, and controlled human review must
evaluate that risk before acceptance.

## Q6 — native transliteration alternate

Propose **ICU4C 77.1**, exact release `release-77-1`, source commit
`457157a92aa053e632cc7fcfd0e12f8a943b2d11`, C transliteration API,
with exact transform IDs `Greek-Latin` or `Cyrillic-Latin`, forward direction.
This older explicit release is selected to align with the accepted Unicode 16
runtime; no “latest” lookup or host/system ICU substitution is allowed.
The official [ICU 77 release record](https://unicode-org.github.io/icu/download/77.html)
documents the release and its Unicode 16/CLDR 47 context. ICU provides named
script transforms and also supports fallback resolution, so this profile must
verify the exact registered ID and reject fallback/alias substitution.
[ICU transform documentation](https://unicode-org.github.io/icu/userguide/transforms/general/).

Source is the exact Stage 6 candidate with at least one NATIVE occurrence.
Use the already vendored Unicode 16 Scripts.txt, SHA-256
`9e88f0a677df47311106340be8ede2ecdacd9c1c931831218d2be6d5508e0039`.
Ignoring Common/Inherited and permitting existing Latin, there must be exactly
one non-Latin script, Greek or Cyrillic. Every code point must be in that
allowlist, and at least one target-script letter must exist. Greek+Cyrillic
mixed text, Unknown/unassigned, Han, Kana, Hangul, Arabic, Hebrew, Indic and
other scripts are unsupported in v1. Latin-only input is ineligible. No source
language is guessed, and generic Cyrillic/Greek romanization is not claimed
language-specific or authoritative.

Order: exact native candidate → Unicode 16 NFC → chosen single whole-string
transform → Unicode 16 NFC. Set the ICU input filter to exactly the intersection
of (target Script or Inherited Script) with Unicode letter/mark general
categories. Script properties use the pinned Unicode 16 data; general categories
use the pinned Unicode 16 runtime. The filter permits transformation of target
letters and marks, while existing Latin, spaces, punctuation and digits remain
readable context outside the mutable input set. Bind the filter definition and
its compiled UnicodeSet digest in the asset lock and trace. Output characters
introduced by a script mapping are allowed; do not confuse them with mutation
of an existing punctuation character. Synthetic tagged-span checks must prove
preservation of input spans outside the filter relative to the NFC input. Do not
remove diacritics or force ASCII. Unexpected residual target/unsupported script
yields `TRANSLITERATION_UNSUPPORTED_OUTPUT` and no alternate; an operational
ICU failure is fatal. Empty output is an explicit abstention. Exact equality
with the baseline yields semantic convergence; native remains available.

The source commit above was verified against the public Git tag in this design
session. The implementation gate must additionally lock source archive SHA-256,
ICU data SHA-256, full transform/dependency rule bytes,
license, compiler/build flags, linked library hashes and Python C-API wrapper
source/version. No dependency installation/download is performed here and no
binary hash is invented. These mandatory runtime bindings complete the proposed
profile before any protected run; version or transform changes require owner
review. Synthetic outputs must be pinned and compared across batch/chunk layouts.
There is no arbitrary chunk-local transliteration or model/API transliteration.

## Q7 — later conditional phase, disabled in Stage 10 v1

Q7 belongs to a separately reviewed **post-ordinary-retrieval diagnostic plan**.
Stage 10 records `DIAGNOSTIC_FALLBACK_DEFERRED` for every candidate, with no
payload, alternate-country list, active predicate or reserved executable slot.
Its current activation function is the constant FALSE. This is versioned,
deterministic and prevents hidden feedback-driven expansion. Repeated Stage 12
requests/errors cannot activate anything in this profile.

A later enabled version must satisfy all of the following necessary gates;
they are a contract boundary, not a sufficient executable rule in this version:

- ordinary source country is unanimous and explicit; source-only S9.Q02 has
  an exact recognized full subdivision-code ownership contradiction, not a
  postcode-pattern miss or country-blocked place lookup;
- all relevant source rows carry compatible contradiction witnesses to exactly
  one alternate owner-country, with no supporting/conflicting source ownership
  witness; a candidate summary alone cannot establish occurrence-wide scope;
- source postcode/locality are nonempty/unanimous, and intact ordinary line-body
  evidence is present; the later version must freeze its exact completeness
  screen. Parser country disagreement may be additional flagged evidence,
  never the trigger or alternate-country authority;
- every selected ordinary complete request is terminal and technically valid;
  transport failures, timeouts, unexecuted/budget-suppressed requests and pending
  results cannot count as geographic failure;
- an independently frozen Stage 12/13 result-evidence predicate finds no usable
  ordinary candidate, with explicit layer/component/contradiction criteria;
  HTTP 200, nonempty results and confidence alone are insufficient; and
- an accepted activation contract, exact result-artifact bindings, separate
  diagnostic budget and separately authorized workload exist.

Accepted DEVELOPMENT has zero qualifying full-code witnesses, so even the
necessary evidence gate currently has no positive cases. Do not weaken it to
force a Q7 workload. A candidate with missing/conflicting source context does
not automatically become eligible for a country-unbounded query.

Prefer at most one witnessed alternate-country diagnostic over global search;
country-unbounded diagnostics remain disabled and would need their own strong
evidence, ceiling and owner policy. A later activation produces a **new immutable
plan**, a Stage 11 complete-request registry/dedup pass (including reuse against
already executed requests), and a separately authorized execution. It never
mutates this Stage 10 catalog or corrects source country. No actual Stage 11–13
design, acceptance or execution is granted here, and the Stage 19 geocoding gate
still controls until deliberately reconciled by the owner.

## Deterministic decision and suppression vocabulary

First validate input integrity. Then evaluate representation availability,
country context, source unanimity, field/transform prerequisites, exact
convergence, and finally the operating budget. Record every evaluated failed
prerequisite, in the order below, with the first as `primary_reason`. Do not
inspect downstream outcomes to choose a reason. Q7 short-circuits to DEFERRED.

Closed reason order:

1. `REQUIRED_SOURCE_REPRESENTATION_UNAVAILABLE`
2. `COUNTRY_CONTEXT_UNRESOLVED`
3. `SOURCE_BOUNDARY_NONUNANIMOUS`
4. `SOURCE_FIELD_NONUNANIMOUS`
5. `MALFORMED_UPSTREAM_EVIDENCE` (fatal record only; never in a committed plan)
6. `PARSER_EVIDENCE_UNUSABLE` (valid empty/unmapped/warned evidence)
7. `UNSUPPORTED_SCRIPT_TRANSLITERATION`
8. `TRANSLITERATION_UNSUPPORTED_OUTPUT`
9. `UNIT_ALIGNMENT_AMBIGUOUS`
10. `CONTRADICTION_GATE`
11. `INSUFFICIENT_TRUSTED_STRUCTURED_EVIDENCE`
12. `ADMIN_LEVEL_NOT_ESTABLISHED`
13. `PARSER_ONLY_FIELD_EXCLUDED`
14. `FAMILY_INELIGIBLE`
15. `EMPTY_RESULT_AFTER_TRANSFORMATION`
16. `EXACT_SEMANTIC_DUPLICATE`
17. `QUERY_BUDGET_SUPPRESSION`
18. `DIAGNOSTIC_FALLBACK_DEFERRED`

No reason is attached to a predicate that was not evaluated. Per-field Q4
decisions distinguish failed positivity, contradiction and nonunanimity even
when the family still emits using the other field. A convergent family retains
its hypothesis FK and all evidence; duplicate is never deletion of lineage.
Budget disposition is derived from the shared hypothesis, so all convergent
families agree on selected/suppressed/catalog-only state. Malformed upstream
evidence cannot be laundered into a successful zero-hypothesis candidate.
