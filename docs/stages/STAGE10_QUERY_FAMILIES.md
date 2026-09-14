# Stage 10 — query families, eligibility and suppression

Part of the [review-candidate scientific contract](STAGE10_MULTI_HYPOTHESIS_QUERY_GENERATION.md).
Owner revisions are incorporated; the frozen revision awaits final implementation approval. No materializer or queries exist.
`Q1`–`Q7` below are Stage 10 family IDs. `S9.Q04`, for example, denotes the
different Stage 9 reference-question namespace.

## Common gates and conservative formatting

All input-integrity gates precede scientific selection. Hash/schema/FK/ordinal
corruption, missing expected evidence, runtime failure and resource exhaustion
are publication-fatal, never scientific absence or candidate exclusion.
Preserved empty parses, unknown labels, ambiguous roles and warnings are valid
upstream states; they are not file corruption.

Ordinary hypotheses require a nonempty exact candidate in the current Stage 8
occurrence and a valid **source-row** country under the scientific contract's
SOURCE_ROW S9.Q01 code-recognition rule. The requested alpha-2 boundary is
mandatory for Q1–Q6. No cross-occurrence/candidate-country unanimity, parser
country, Stage 9 country assessment success, script inference or reference
frequency is required. An invalid row context affects only that occurrence.
Stage 9 contradictions of optional structured fields never remove Q1/Q2.

Formatting version `stage10_exact_query_format_v1`:

| Surface | Exact operation |
|---|---|
| Source and accepted representations | Never modify them. References retain derivation level. |
| Q1/Q2 baseline | Exact UTF-8 encoding of `stage06_candidate_lower`; no new Unicode normalization, whitespace collapse, trim, case change, accent removal or punctuation rewrite. |
| Q3 source-line alternate | Exact lower-line bytes in source position order; join nonempty slots with a single U+000A LF. No punctuation insertion or stripping. |
| Q4 `address` | Entire exact Stage 6 candidate, including disputed postcode-like text if present in that line body. |
| Q4 other text fields | Exact current-row Stage 3 clean source string, including leading zeros in postcode. Stage 9 normalization is a comparison method, never a replacement query value. |
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
| Q1 FULL_STANDARD | 1 | Current occurrence role STANDARD | `/v1/search`, full candidate as `text` |
| Q2 FULL_NATIVE | 1 | Current occurrence role NATIVE | `/v1/search`, full candidate as `text` |
| Q3 BOUNDARY_PRESERVING | 1 | Current occurrence exact lower-line vector and mask | `/v1/search`, LF-joined lines |
| Q4 SOURCE_ANCHORED_STRUCTURED | 1 | At least one eligible current-row source postcode/locality field under the rules below | `/v1/search/structured`, full `address` plus eligible fields |
| Q5 UNIT_FLOOR_STRIPPED_SECONDARY | 1 | Current occurrence boundaries plus whole-line lexical and exact parser corroboration | `/v1/search`, remaining lines joined by space |
| Q6 NATIVE_TRANSLITERATION_ALTERNATE | 1 | Current role NATIVE and one supported script; full baseline retained | `/v1/search`, one transliterated full native candidate |
| Q7 DEFERRED_RESULT_DEPENDENT_DIAGNOSTIC | 0 | Global reporting status only | No per-context decision, hypothesis or reserved ID |

Q1/Q2 are universal **within their current occurrence role and valid source-row
country context**. Q3–Q6 are conditional. Failure to meet a family gate is an
auditable abstention, not address invalidity. All active request intents use
the same explicit context country and the same frozen retrieval-policy reference; no
family varies language, layers, sources, focus or size to multiply requests.

## Q1/Q2 — exact full baselines

STANDARD and NATIVE are occurrence provenance, not competing truth labels.
Q1 is eligible only in a STANDARD context; Q2 only in a NATIVE context. Each
uses the complete exact Stage 6 lowercase candidate for that occurrence.
Same-row equal STANDARD/NATIVE text therefore retains two context-scoped full
hypotheses, which can share the same intent fingerprint. This preserves exact
occurrence map-back; Stage 11 later executes their complete request once if
all resolved semantics agree. Never add the other family label to one context
merely because that candidate text appears in that role somewhere else.

No representative source row, clean casing choice, parser reconstruction,
recipient/building deletion or appended geography occurs. Raw/clean/lower
lineage remains exact. Q4 exclusions never suppress the full baseline.

## Q3 — accepted source boundaries within the context

Resolve this occurrence through Stage 8 to the bound Stage 6 row by stable ID.
Read its representation-specific four lower-line slots; check candidate-slot
identity, availability, mask, count and space-joined equality with the accepted
Stage 5/6 candidate. Other occurrences' layouts are irrelevant.

Join nonempty slots in position order with exactly one LF (U+000A). Keep slot
indices and mask through the source-line selector, including gaps/repetitions.
No within-line character is removed and no semantic role is assigned. Do not
recover boundaries by splitting the joined candidate or parser output. A one-line
query converges with the baseline. A missing/corrupt required line artifact is
fatal; a supported future input explicitly lacking boundary evidence would
abstain, never silently substitute another occurrence. The accepted input has
sufficient boundaries: BOUNDARY_HANDOFF_SUFFICIENT remains unchanged.

Fictional slots `['12 example road', '', 'unit 5', '']` yield
`12 example road\nunit 5`, mask `1010`. The four-slot vector, not splitting the
LF string, is the canonical lineage authority. Exact empty slots are skipped;
no empty separators are invented. If a source line already contains LF, the
source slot/offset lineage still distinguishes it from the inserted LF. Stage 11
must define lossless request serialization and preserve the exact LF bytes;
unsupported transport is an explicit QA outcome, not silent space substitution.
Stage 5's rejected primary comma-space reconstruction remains rejected history.

## Q4 — source-anchored structured hypothesis

Use `address = stage06_candidate_lower` intact. Do not assign a parser street,
house, house number, suburb, city district, island, state district, country
region, PO box, category, near or unknown label to a trusted structured field.
Keeping the whole line body in `address` asserts no parser street/house split.
It is still an experimental structured query, never a source correction.

For each source geographic field use only the current row's nonempty Stage 3
clean value. Predicate evidence must have `evidence_scope=SOURCE_ROW`, this
exact candidate ID and stable source ID, and the precise argument field/role.
Its country argument must resolve to the current context boundary. No evidence
from another row or parser-origin argument can supply or veto this field.
Stage 9's candidate-wide prerequisites may have left this row's checks
NOT_EVALUABLE; preserve them as unavailable positive evidence. Do not rerun the
reference evaluator, borrow a different context or inhibit the full baseline.

Evaluate locality first, postcode second, without enumerating field subsets:

1. **Locality L:** current-row `stage03_clean_city`; at least one S9.Q09
   SUPPORTED witness at an explicit locality/place level, from enabled
   LIBADDRESSINPUT_METADATA `FORMAT_LOCALITY` or GEONAMES_POSTAL `place_name`.
   Admin, dependent-locality, suburb and parser-city evidence cannot substitute.
   Multiple compatible witnesses may remain; support establishes scoped field
   use, not selection of a unique geographic entity.
2. **Postcode P:** current-row `stage03_clean_postcode`; S9.Q05 SUPPORTED with
   FULL_POSTCODE granularity and positive authority in GEONAMES_POSTAL.
   An applicable source S9.Q04 FORMAT_RULE_CONFLICT or source S9.Q08
   PREFIX_RULE_CONFLICT vetoes **structured P only**. If L is eligible,
   S9.Q06 must also be SUPPORTED on this exact source-row postcode/locality tuple
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
defaults. Their coverage cost is a future DEVELOPMENT diagnostic, not a new permission request.

Parser values remain accessible through accepted candidate/component lineage,
but no optional parser-concordance relation or metric is added in v1. They
cannot change Q4 eligibility, populate its fields or override a source/reference
gate. Any future concordance is descriptive, not an independent confirmation. Neither PARSED_NONEMPTY nor warning absence
is trust. This deliberately narrow v1 avoids reviving the rejected Stage 7
readiness gate; broader parser-origin structured fields require a new design.

## How Stage 9 evidence influences queries

| State | Allowed Stage 10 effect | Prohibited inference |
|---|---|---|
| SUPPORTED | Enable the precise Q4 source-field use above after role, scope, country, granularity, authority and witness checks | Correct parser label, valid address, unique place, independent vote |
| CONTRADICTED | Applicable source S9.Q04/Q08 veto structured postcode only; no active Q7 use | Delete source content, change source country, veto unrelated parser/source fields |
| NOT_FOUND | Positive-support requirement remains unmet; full text remains available | Invalidity, contradiction, geographic exclusion |
| NOT_EVALUABLE | Prerequisite/capability abstention; full text remains available | Negative evidence or absence claim |

The only v1 negative structured gate is **postcode**. A CONTRADICTED row can
veto that field only when all checks below pass:

1. It is SOURCE_ROW evidence for this context's exact candidate and source ID.
2. Its POSTCODE argument points to this very `stage03_clean_postcode` field;
   resolve exact bytes and the recorded normalization digest. Its country
   argument equals this context's requested boundary; for S9.Q08 its ADMIN
   argument also resolves to this row's exact clean region field.
3. The question is S9.Q04/FORMAT_RULE_CONFLICT or
   S9.Q08/PREFIX_RULE_CONFLICT, in LIBADDRESSINPUT_METADATA. Matrix and object
   rule capabilities are enabled, with explicit authorized negative authority,
   correct claim scope/granularity and the complete positive-conflict witness.
4. No missing/ambiguous locator, source/candidate mismatch, incompatible country,
   parser origin or grain ambiguity makes it inapplicable. Valid but inapplicable
   evidence has no gate effect; malformed supposedly applicable evidence is fatal.

No other negative gate is enabled for symmetry. GeoNames negative authority is
FALSE: absence/association mismatch cannot suppress a component through negative
authority. A GeoNames CONTRADICTED row violates upstream integrity. A source
REFERENCE_INTERNAL_CONFLICT on the precise question/argument tuple leaves
positive support insufficient; it is not a new geographic negative certificate.
Missing expected evidence is fatal; present NOT_FOUND/NOT_EVALUABLE are neither
negative claims nor inferred contradictions. The need for positive Q4 evidence
is distinct from negative suppression.

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

Require the current occurrence's Q3 source-line vector and PARSED_NONEMPTY.
Do not use candidate-wide warning/applicability/country summaries as a gate:
those may depend on unrelated occurrences. Current exact alignment, complete-line
lexical corroboration and the local source-field vetoes below are the gates.
Parser labels alone and absence of warnings provide no semantic trust.
The complete removable line must match the literal ASCII marker grammar below;
the **rest of the candidate has no Q5 script restriction**. A safely corroborated
`unit 5` line may accompany Greek/Cyrillic or other script in surviving lines.
The former candidate-wide Latin/Common/Inherited gate was not independently
justified by whole-line safety and is removed by the final owner ceiling review.
No source language is inferred and no marker grammar is expanded.

For a complete nonempty lower line, the entire string must full-match one
grammar, with exact ASCII spaces, letters and digits:

```text
UNIT := (unit|suite|apt|apartment) U+0020 [0-9]+[a-z]?
LEVEL := (floor|level) U+0020 [0-9]+
```

No punctuation variants, signed/ranged/roman floors, free-text building names,
isolated numbers, abbreviated periods or embedded markers are accepted. A
name that exactly mimics a marker grammar remains semantic ambiguity, as
explicitly limited below. There are no
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

For each proposed removable line, also veto if it equals any nonempty current-row
lower source city/postcode/region/country field, or if it contains any such value
as a complete Unicode-letter/digit-delimited token sequence. Comparison uses
exact Stage 4 lower strings; do not fuzzy-match. A token sequence is delimited
by start/end or a code point outside Unicode categories L* and N*. Empty source
fields are not evidence. A mixed line such as “unit 5 example road” fails the
full-match grammar; a parser labeling it `unit` cannot override that failure.

Record exact source slot, interval, category, grammar ID and component ordinal.
The removal algorithm filters whole line units: for every retained slot, output
bytes equal the complete input line bytes; the only other bytes are the frozen
join separator. Therefore **partial deletion of any street/house/building/
locality/postcode/country/mixed-content line is impossible by construction**.
This is a mechanical proof, not a claim that a complete line named “Unit 5”
cannot denote a building. Whole-line grammar + independent boundary + unique
parser corroboration + local geography/role veto are the necessary hypothesis
evidence. Without that conjunction suppress Q5. Semantic ambiguity cannot be
proved away by parser labels; retain the full baseline, make no correction/truth
claim, and audit false whole-line removals during later controlled DEVELOPMENT
review. No extra lexical guessing or classification is authorized.

Never strip Q4/Q6 output, never chain Q5 into Q6, and never overwrite Q1/Q2.
Q5 and Q6 are independently eligible: both can emit separate alternates from
the same full NATIVE context. This creates no stripped-and-transliterated family.

## Q6 — exact native transliteration alternate

The normative specification is
[`stage10_transliteration_spec_v1.json`](../scientific_assets/stage10_transliteration_spec_v1.json).
Its exact bytes are included in the design freeze. It pins ICU4C 77.1, Unicode
16.0.0 / CLDR 47 source data, source commit
`457157a92aa053e632cc7fcfd0e12f8a943b2d11`, transform registry/rule/UCD hashes,
normalization, filter, script tests and failure semantics. Runtime binaries and
compiler configuration must later be pinned before execution; they cannot
substitute a different source/data/transform specification.

Use the **current NATIVE occurrence's** exact Stage 6 candidate; no Q6 in a
STANDARD context merely because the same text has another NATIVE occurrence.
Apply NFC_U16, then the exact canonical ICU transform `Grek-Latn` or `Cyrl-Latn`
in UTRANS_FORWARD direction, then NFC_U16. Define the additional UnicodeSet
as letters/marks whose Unicode 16 Script is the target or Inherited. Intersect
it with the canonical transform's original top-level filter (universal if absent)
and install that intersection. Retain every nested filter and internal NFD/NFC
operation; replacing the original filter with the additional set alone is banned. Do not
flatten it into an invented rule or use a locale-specific romanizer.

The readable names Greek-Latin and Cyrillic-Latin are **pinned registry aliases**
for Grek-Latn/Cyrl-Latn in this ICU source; the canonical IDs are used directly.
The first draft's instruction to reject all aliases while naming those aliases
is corrected. No fallback ID resolution or installed system ICU is permitted.
Sources: [pinned registry](https://github.com/unicode-org/icu/blob/457157a92aa053e632cc7fcfd0e12f8a943b2d11/icu4c/source/data/translit/root.txt),
[Greek rules](https://github.com/unicode-org/icu/blob/457157a92aa053e632cc7fcfd0e12f8a943b2d11/icu4c/source/data/translit/Grek_Latn.txt),
[Cyrillic rules](https://github.com/unicode-org/icu/blob/457157a92aa053e632cc7fcfd0e12f8a943b2d11/icu4c/source/data/translit/Cyrl_Latn.txt).

Before and after pre-NFC, all code points must have Script in {Latin, Common,
Inherited, Greek} or {Latin, Common, Inherited, Cyrillic}; exactly one target
script must have at least one letter. Mixed Greek+Cyrillic and any other/Unknown/
unassigned script abstain. NFC output with an Inherited mark is eligible only
if scanning left over adjacent marks reaches a target-script letter; isolated
marks or inherited marks attached to Latin/nonletters abstain. Existing Latin
and Common punctuation/digits are permitted but outside the mutable filter.
No language is guessed. Arabic/Hebrew/Han/Kana/Hangul/Indic/etc. are unsupported.

After post-NFC, check in order: empty output abstains; exact unchanged complete
intent converges with Q2 (EXACT_SEMANTIC_DUPLICATE), creating no new hypothesis;
otherwise residual script beyond Latin/Common/Inherited abstains. Then perform
complete-intent convergence with other eligible families or emit the alternate.
Unsupported output is transform non-applicability, whereas an ICU/runtime/asset
error fails publication. Preserve family provenance and native input always.
No casefold, NFKC, ASCII folding, diacritic stripping, translation or source
replacement. Context-aware whole-string processing and synthetic exact-output
verification are mandatory; arbitrary chunk-local transforms are prohibited.

## Q7 — globally deferred result-dependent diagnostic

Global status is exactly `DEFERRED_RESULT_DEPENDENT_DIAGNOSTIC` in the summary
and manifest. Stage 10 emits no Q7 per-context decision, pseudo-hypothesis,
country-unbounded query, payload, reserved ID or execution slot. There is no
Stage 10 activation evaluator. Deferral is invariant under every possible
ordinary outcome, not an invitation to runtime adaptive queries.

Any future enabled diagnostic must have a separately frozen sufficient activation
rule, exact immutable triggering Stage 12/13 evidence, complete workload
construction and semantic request identity, combined budgets, reproducibility
and context/source map-back. It must distinguish technically valid ordinary
failure from pending/error/unexecuted requests, and cannot infer country error
from GeoNames absence or postcode-pattern conflict. Source-context and
positive contradictory ownership evidence, parser limitations, representation
completeness and ordinary outcomes must be explicitly addressed in that future
contract. This design does not prejudge a sufficient rule before retrieval
behavior exists. It reserves no Stage 10 IDs for hypothetical requests and
cannot modify source country. A future workload passes its own Stage 11
complete-request dedup/authorization boundary, including reuse of prior results.
The repository's Stage 19 geocoding gate remains controlling.

## Deterministic decision and suppression vocabulary

First validate input integrity. Then assess this context's role, local country,
exact boundary and family prerequisites, complete-intent convergence, and only
in a separately authorized future plan an operating budget. Record every
actually evaluated failure in the closed order below, first as primary_reason.
No downstream outcome can influence a decision. Unavailable other-role Q1/Q2
uses REQUIRED_SOURCE_REPRESENTATION_UNAVAILABLE for this context only.

1. `REQUIRED_SOURCE_REPRESENTATION_UNAVAILABLE`
2. `COUNTRY_CONTEXT_UNAVAILABLE`
3. `SOURCE_BOUNDARY_UNAVAILABLE`
4. `SOURCE_FIELD_UNAVAILABLE`
5. `MALFORMED_UPSTREAM_EVIDENCE` (fatal receipt only, never committed row)
6. `PARSER_EVIDENCE_UNUSABLE` (valid empty/unmapped/unalignable evidence)
7. `UNSUPPORTED_SCRIPT_TRANSLITERATION`
8. `TRANSLITERATION_UNSUPPORTED_OUTPUT`
9. `UNIT_ALIGNMENT_AMBIGUOUS`
10. `UNIT_SOURCE_FIELD_CONFLICT`
11. `CONTRADICTION_GATE`
12. `INSUFFICIENT_TRUSTED_STRUCTURED_EVIDENCE`
13. `ADMIN_LEVEL_NOT_ESTABLISHED`
14. `PARSER_ONLY_FIELD_EXCLUDED`
15. `FAMILY_INELIGIBLE`
16. `EMPTY_RESULT_AFTER_TRANSFORMATION`
17. `EXACT_SEMANTIC_DUPLICATE`
18. `QUERY_BUDGET_SUPPRESSION` (reserved for a later approved operating plan;
    forbidden in the first ALL_ELIGIBLE_CATALOG)

Q7's global deferred status is not a per-context reason. Per-field Q4 decisions
remain separate even when the family emits using another field. Convergent
families retain the same context/hypothesis FK and their complete lineage.
No corruption, missing expected evidence or resource failure can be hidden in
successful zero-hypothesis output. NOT_FOUND/NOT_EVALUABLE record lack of positive
support, not a CONTRADICTION_GATE reason.
