# Stage 10 — complete design-defect ledger and owner review

Review target: the [Stage 10 documentation package](STAGE10_MULTI_HYPOTHESIS_QUERY_GENERATION.md)
on baseline `23cfb85f428b00301d68591ea5992763abf9ad88`.
Disposition: **DESIGN READY FOR OWNER REVIEW**. This is a critical self-review
of a design, not independent implementation review or scientific acceptance.
No sub-agents, protected artifacts, cluster probes or geocoder calls were used.

## Complete bounded defect ledger

The review collected the full set below before finalization. All bounded
specification defects are resolved in the proposed contract. Owner choices
remain explicitly unapproved and execution prerequisites remain unperformed.

| ID | Defect or failure mode challenged | Resolution in the review candidate |
|---|---|---|
| D10-01 | “Full” silently adds geography or selects clean source casing | Q1/Q2 are exact accepted Stage 6 lowercase line bodies; Stage 5 excluded geography; raw/clean/lower history remains distinct. |
| D10-02 | Destructive Unicode, whitespace, punctuation or native normalization | Exact baseline bytes; LF only in Q3; NFC only in Q6; no source overwrite or broad cleanup. |
| D10-03 | One exact candidate contains different countries/contexts | Unanimous accepted source-country gate; no majority/first occurrence, parser country or automatic unbounded search. Lost coverage is reported. |
| D10-04 | Candidate-wide boundary query borrows one row's layout | Compare all four slots/masks across all occurrences; suppress divergent vectors; validate Stage 8→6 stable-ID/slot totality. |
| D10-05 | Q3 rebuilds boundaries from parser output or joined text | Read exact manifest-bound Stage 6 line projection; LF preserves layout without assigning component meaning; no upstream mutation. |
| D10-06 | Parser warning absence reappears as a semantic readiness gate | Q4 uses source fields only; Q5 additionally requires whole-line grammar and unique exact alignment; warning absence never certifies meaning. |
| D10-07 | Unsupported parser city/state become trusted structured fields | V1 excludes parser-origin structured geography, street/house splits and admin-level assumptions; whole line body stays in `address`. |
| D10-08 | NOT_FOUND / NOT_EVALUABLE become contradictions | Positive eligibility requirements are distinct from negative claims; exact four-state handling and fatal missing-evidence distinction. |
| D10-09 | Global postcode deletion based on 59.995780% Q04 rate | Source-only scoped Q04/Q08 can veto structured P; baseline and structured address text remain intact; parser Q04 cannot veto source P. |
| D10-10 | Country-support gate excludes the accepted population | Q1–Q6 depend on Stage 7 unanimous source provenance, not the all-unresolved Stage 9 country-assessment dimension. |
| D10-11 | Reference repetition/shared ancestry supplies extra votes | Evidence locators, scopes and dependency lineage retained; no weights/votes; repeated parser values yield no new family slot. |
| D10-12 | Separate positive postcode/locality checks imply joint support | If locality is included, postcode also requires source S9.Q06 same-record support; otherwise omit postcode deterministically. |
| D10-13 | Favorable reference wins despite internal source-field conflict | Relevant source REFERENCE_INTERNAL_CONFLICT vetoes field inclusion; unrelated/parser evidence cannot silently gate it. |
| D10-14 | Unit stripping removes street/building substrings | Only complete source lines with narrow UNIT/LEVEL grammar, exact whole-line parser corroboration and surviving content; all other categories excluded. Full text remains. |
| D10-15 | Parser offsets are invented or ambiguous component matches chosen | Compute and compare earliest/latest ordered exact embeddings; disagreement abstains; exact removal slots/intervals/ordinals recorded. |
| D10-16 | Component × giant-string overlap checks scale quadratically | Two monotone alignment scans plus external ordinal reconciliation; no repeated full-candidate search per component; bounded list/spool design. |
| D10-17 | Transliteration selects host library, guesses language or damages native | ICU4C 77.1 source commit pinned, exact Greek/Cyrillic IDs, script allowlist and mandatory data/build lock; native parallel baseline; unsupported cases explicit. |
| D10-18 | Arbitrary chunk transliteration changes context-sensitive output | Whole logical string contract with reviewed resource handling and chunk-equivalence tests; no resource failure converted to scientific abstention. |
| D10-19 | Combinatorial family/field/script/context expansion | One construction per family; no chaining/subsets/products; Q1/Q2 converge; derived ceiling five per candidate/ten per row. |
| D10-20 | Arbitrary numeric budget masquerades as optimal science | Ceiling derived from architecture; B unselected; catalog-only exports no workload; DEVELOPMENT cost then later recall calibration. |
| D10-21 | Duplicate collapse loses family evidence or consumes budget twice | Two relations: candidate-scoped converged hypothesis plus seven family decisions; collapse before rank/B; convergent members retain FKs and lineage. |
| D10-22 | Text-only identity merges different endpoint/country/settings | Full intent digest includes endpoint/mode/fields/country/common policy reference; Stage 11 resolves all result-affecting semantics before its separate ID. |
| D10-23 | Hypothesis/request/execution IDs are conflated | Scientific IDs bind inputs/science/candidate; Stage 11 owns complete request ID; Stage 12 adds deployment/index/execution identity and separate attempts. |
| D10-24 | Incomplete fingerprints, null semantics or nondeterministic order | Typed framed encoding, exact input object, separate science/budget identities, deterministic relation/selector sorting and byte collision checks. |
| D10-25 | Map-back duplicates/drops sources or overcredits native/standard families | Stage 8 sole map; candidate totality and seven slots; zero orphans; distinct source, occurrence, request and family-edge reconciliation. |
| D10-26 | Per-hypothesis lineage lists and repeated shared-witness expansion grow with population | Closed selector certificates with exact replay/count/stream hashes; shared witness sets traversed once per candidate; authoritative maps reused; bounded inline structs only. |
| D10-27 | Q7 hides Stage 12-dependent adaptive behavior inside static Stage 10 | Q7 constant FALSE, no payload/activation slot; later enabled version needs sufficient frozen evidence/result predicates, combined cap and a new immutable globally deduplicated plan. |
| D10-28 | Missing ordinary country or technical query failure triggers global search | Neither qualifies; later diagnostic boundary requires scoped positive ownership contradiction and terminal valid ordinary evidence. Country-unbounded remains disabled. |
| D10-29 | Suppression conceals corrupt evidence or loses all candidates | Fatal integrity/resource/runtime errors cannot publish; valid scientific abstentions retain seven decisions and source left-join coverage. |
| D10-30 | Protected row digests/selector/error strings leak through “sanitized” artifacts | Both row-level relations entirely protected; one strict aggregate object; no row/query IDs, examples, arbitrary errors or geographic small-cell exports. |
| D10-31 | Physical layout or operational metrics alter logical reproduction | Ordered logical relation hashes separate from physical file/manifests; summary excludes timing/job/output self-hashes; budget changes affect P, not generated IDs. |
| D10-32 | Stage 9 PanFS acceptance assumed valid for untested Stage 10 path | Reuse state machine conditionally; same intended anchor, future pre-input verification, no current probe and no claim of measured Stage 10 compatibility. |
| D10-33 | Stage-specific publication record falsely reused unchanged | New Stage 10 namespace/input-binding adapter only; primitive/state-machine requirements unchanged; no edits to accepted Stage 8/9 code/contracts. |
| D10-34 | Design status implies implementation, Stage 11 or geocoding authority | Current indexes distinguish review-ready design from not-started implementation; Stage 19/size-policy reconciliation stays a later owner gate. |
| D10-35 | Future family utility claims use unexecuted families or retrieval rank as correctness | Predeclared paired DEVELOPMENT trial/adjudication, shared-cost attribution and ablation; missing observations explicit; no Stage 10 accuracy claims. |
| D10-36 | HOLDOUT tuning or historical scientific rewrite | HOLDOUT untouched; later full freeze required; accepted records/assets/reports and all Stage 3 ancestry remain unchanged. |

Residual scientific risks are openly retained: candidate-wide unanimity may
reduce coverage, Q3 may have no request utility, narrow Q4/Q5 may often abstain,
unit-like building names can still be ambiguous, and generic script
transliteration may be inferior for particular languages. These require
DEVELOPMENT evidence and owner judgment, not claims of current correctness.

## Explicit owner-review decisions still needed

| Decision | Proposed choice for approval | Reasonable alternative / consequence |
|---|---|---|
| O10-01 relation set | Two protected relations (`query_hypothesis`, `query_family_decision`) plus one aggregate object | Separate family membership/abstention tables add relations; occurrence-specific hypotheses need a new bounded applicability design. |
| O10-02 static/conditional boundary | Catalog of Q1–Q6; Q7 deferred, constant FALSE, no payload | Enabled conditional diagnostics require a later sufficient activation/result contract and combined ceiling; do not approve implicit adaptivity. |
| O10-03 engineering budget | Five distinct hypotheses/candidate and ten/source row; one construction/family, collapse before selection | More variants require a revised family architecture and ceiling; no arbitrary overflow truncation. |
| O10-04 operating budget | B remains unselected; future offline CATALOG_ONLY then DEVELOPMENT calibration | A provisional numeric trial B may be separately approved with cost evidence; no accuracy-optimal B can be frozen now. |
| O10-05 ordinary eligibility/context | Q1/Q2 conditional only on representation and unanimous valid source country; Q3–Q6 narrower gates; unanimous all-occurrence boundaries/source fields | Occurrence-scoped context could recover coverage but changes boundedness and map-back. Country-unbounded baselines are a different scientific policy. |
| O10-06 Stage 9/Q4 policy | Source-only positive postcode/locality, joint support when both; exact source Q04/Q08 veto only structured postcode; no parser-origin fields/admin | Broader parser/admin structures require defensible scope/level rules and fresh evaluation; absence cannot become contradiction. |
| O10-07 convergence | One candidate-scoped hypothesis per exact intent; all contributing families retain decision FKs | Per-family hypothesis rows need a third payload relation or duplicated strings; global calls still must deduplicate later. |
| O10-08 transliteration | ICU4C 77.1, pinned source, Greek/Cyrillic only, NFC→one transform→NFC; exact runtime assets locked before execution | Defer Q6 entirely or review more scripts/language-specific systems; never translate/overwrite native. |
| O10-09 unit/floor rule | Whole-line UNIT/LEVEL only, literal narrow English-marker grammar and unique parser/source alignment | Defer Q5 or broaden with additional reviewed rules; substantial coverage and false-removal tradeoff. |
| O10-10 boundary rule | LF between unanimous lower source lines, preserve exact within-line text/mask | Keep Q3 audit-only if later endpoint QA or DEVELOPMENT evidence does not justify requests; no silent LF replacement. |
| O10-11 publication | Reuse accepted Stage 9 state machine conditionally, with a Stage 10 registration adapter | Actual filesystem assumptions remain to be verified in an authorized future session; no protocol redesign warranted by present requirements. |

An approval should identify the exact design commit, accepted/revised O10
decisions and the next authorized scope. Design approval is not implementation
or job authorization unless the owner explicitly grants that scope. Numeric B,
runtime artifact hashes, executable schemas, Stage 11 complete request contract,
Stage 12 result/deployment rules and any enabled Q7 predicate are clearly named
future gates; this review does not assert they exist.

## Review validation and preservation

Local review checks only documentation/freeze hashes, cross-links, baseline
anchors, scope/status consistency, unchanged accepted scientific paths and
source-control/privacy hygiene. No production/DEVELOPMENT materializer tests
or protected payload test prerequisites are opened for a documentation change.
The final design commit and local checks are reported to the owner; no push,
merge, tag of acceptance or cluster action occurs in this session.

STAGE10_MULTI_HYPOTHESIS_QUERY_GENERATION_DESIGN_READY

NEXT: OWNER REVIEW OF STAGE 10 DESIGN
