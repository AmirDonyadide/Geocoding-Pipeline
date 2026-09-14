# Stage 10 — owner revisions and complete final design review

Review target: the [Stage 10 design package](STAGE10_MULTI_HYPOTHESIS_QUERY_GENERATION.md)
on accepted baseline `23cfb85f428b00301d68591ea5992763abf9ad88`.
**OWNER REVISIONS INCORPORATED — FROZEN FOR FINAL OWNER REVIEW.** Architecture
was approved in principle; implementation still requires final owner approval.

The first draft `642fa170ac594f6fe425a9272b5dae6bdff584cc` remains immutable Git
history. Its candidate-wide unanimity, fixed per-candidate ceiling, seven family
rows and preliminary alias wording are superseded, not retrospectively accepted.
This is one bounded complete self-review of the revised design, not independent
implementation review or scientific acceptance. No agents, protected reads,
cluster probes or geocoder calls were used.

## Owner decision incorporation

| Owner decision | Incorporated final contract |
|---|---|
| 1 — context grain | One context per present Stage 8 source/representation occurrence; exact source/candidate FKs inline; no cross-row eligibility veto or duplicate mapping relation. |
| 2 — Q7 | Global DEFERRED_RESULT_DEPENDENT_DIAGNOSTIC; no per-context pseudo-row/hypothesis, request ID or country-unbounded query. |
| 3 — ceiling | Exact mutually exclusive family proof gives reachable maximum 4/context, 8/source row; no fixed candidate cap. No eligible family suppressed by engineering limit. |
| 4 — country | Row-local accepted clean country with exact source S9.Q01 code recognition; candidate-country unanimity and country-assessment resolution not required. |
| 5 — families | Q1/Q2 primary in their own representation contexts; conditional Q3–Q6; complete full representations survive structured contradictions. |
| 6 — contradictions | Only same-context source-postcode Q04/Q08 with exact locators/country/rule/witness and negative authority may gate structured postcode; GeoNames cannot supply negative suppression. |
| 7 — convergence | One context-scoped complete-intent hypothesis, multiple family membership FKs. Across-context equal intents preserve distinct lineage and await Stage 11 request dedup. |
| 8 — transliteration | Machine-readable frozen ICU/Unicode/data/rule/filter/chain/script/output specification; native-only Greek/Cyrillic, no runtime substitution. |
| 9 — Q5 | Whole-line filtering only, exact source boundary + narrow grammar + unique parser alignment + current-row source-field/role vetoes; no partial line deletion, abstain without corroboration. |
| 10 — Q3 | Current occurrence's exact four slots/mask, deterministic LF join; gaps/within-line LF unambiguous through source lineage. |
| 11 — publication | Reuse accepted Stage 9 state machine on same verified PanFS topology/primitive; Stage 10 adapter; no new diagnostic for stage-number change; stop on environment difference. |
| Handoff/model/calibration/reporting | Two protected context-aware relations plus aggregate summary; complete Stage 11/12 identity boundary; initial all-eligible catalog, context multiplicity/coverage/cost, later recall calibration. |

## Complete resolved bounded design-defect ledger

All 40 items below are resolved in this revised specification. They include the
original risk classes and every new issue found during owner-revision review.
The existence of a former self-review did not establish that its context policy
was acceptable; this ledger explicitly replaces that policy and its resolutions.

| ID | Failure mode | Resolution / design evidence |
|---|---|---|
| R10-01 | Exact candidate conflates source contexts | Bijective Stage 8 occurrence→query context; generate before global dedup. |
| R10-02 | One row's country suppresses unrelated same-text rows | Row-local code recognition; no candidate-wide/unanimity gate. |
| R10-03 | Stage 9 country assessment required despite all-unresolved evidence | Code recognition is a different scoped claim; no country-assessment-success gate. |
| R10-04 | Stage 9 candidate-wide prerequisites silently reused in Stage 10 | Preserve resulting NE evidence; do not rerun/borrow it; optional Q4 limitation never blocks full/line/transform families with local evidence. |
| R10-05 | Boundaries borrowed across rows or inferred by splitting text | Exact occurrence→Stage 6 four-slot/mask selector; distinct layouts generate distinct context hypotheses. |
| R10-06 | Representation role inferred globally from candidate membership | Context role STANDARD/NATIVE is authoritative; Q1/Q2 exclusive; Q6 native-only. |
| R10-07 | Extra context map duplicates Stage 8 authority | No context table; inline existing FKs in two relations, verified against upstream view. |
| R10-08 | Query context hash bloated or values can drift under same identity | Immutable upstream snapshot IDs plus minimal source/role key; candidate/fields functionally determined and integrity-checked. |
| R10-09 | “Full” rewrites source or appends unsupported geography | Exact accepted lowercase line body only; raw/clean/lower distinction maintained. |
| R10-10 | Broad Unicode/whitespace/punctuation change damages evidence | No baseline cleanup; Q3 LF and Q6 NFC/transliteration isolated as explicit alternates. |
| R10-11 | Parser warning absence becomes truth or cross-row applicability gate | Q4 source fields only; Q5 independent exact alignment/local gates, no warning/provenance-summary eligibility. |
| R10-12 | Parser geography or ambiguous admin level becomes structured truth | Source-only postcode/locality under positive scoped support; admin/parser fields excluded. |
| R10-13 | Postcode conflict strips Q1/Q2 or unrelated fields | Negative gating only structured postcode, exact context and source field; full query/address remains. |
| R10-14 | GeoNames absence/NOT_FOUND/NE treated as contradiction | Positive-support requirements separate; explicit negative-authority prohibition and scoped four-state rules. |
| R10-15 | Contradiction from another source/parser grain applied locally | Exact candidate/source/argument/country/rule/witness checklist; inapplicable evidence has no gate effect. |
| R10-16 | Independent postcode/locality matches imply joint support | Including both requires same-source tuple S9.Q06 positive same-record evidence. |
| R10-17 | Internal conflict or duplicated evidence supplies votes | Scope-limited insufficient positivity; complete selectors; no additive votes/repetition expansion. |
| R10-18 | Q5 substring deletion damages mixed-content line | Filter complete source slots only; every retained line byte-equal; full-match grammar rejects mixed text. |
| R10-19 | Parser label alone authorizes unit removal | Complete-line marker + exact boundary + unique ordered alignment + local source-geography veto + surviving-content conjunction. |
| R10-20 | Whole-line removal called guaranteed semantic correctness | Mechanical no-partial-deletion proof distinguished from residual Unit-5 building-name ambiguity; full baseline retained; later human review, no source correction. |
| R10-21 | Parser offsets invented or arbitrary alignment chosen | Earliest/latest monotone exact embeddings must agree; uncertainty abstains, exact removal slots/ordinals recorded. |
| R10-22 | Unit alignment scales candidate×component repeatedly | Monotone scans/external ordinal reconciliation; shared candidate alignment work cannot merge context eligibility. |
| R10-23 | ICU version label hides mutable rules/data | Exact source commit, registry/rule/UCD SHA-256 inventory and pinned script/normalization specification; matching build lock required before execution. |
| R10-24 | Named ICU IDs are aliases despite blanket alias prohibition | Source check proves Greek-Latin→Grek-Latn and Cyrillic-Latin→Cyrl-Latn; canonical IDs and exact registry pinned, arbitrary fallback banned. |
| R10-25 | Mixed/unsupported scripts or inherited marks silently romanized | Explicit before/after-NFC Script16 and mark-context gate; original-filter intersection, nested filters preserved; ordered empty/unchanged/residual outcomes. |
| R10-26 | Chunk/locale/ASCII transformations silently alter Q6 | Exact whole-string forward chain with internal pinned normalization/filter; no system ICU, language guessing or Latin-ASCII; native remains. |
| R10-27 | Engineering ceiling hides eligible static families | Q1/Q2 and Q5/Q6 exclusion proof plus synthetic attainability witness gives 4/context and 8/row; excess fails rather than suppresses. |
| R10-28 | Popular exact candidate exhausts arbitrary global budget | Candidate bound 4×occurrence_count; each context independent; no fixed global cap. |
| R10-29 | Operating budget chosen without evidence or during first run | B UNSELECTED, ALL_ELIGIBLE_CATALOG, zero budget suppressions; structural versus later recall calibration separated. |
| R10-30 | Family duplication consumes requests or destroys lineage | Complete-intent convergence within context and shared family FK; across-context edges retained for later global request dedup. |
| R10-31 | Text-only identity or Stage 11 ID prematurely frozen | Stage 10 requested intent/policy inputs only; Stage 11 resolves ALL request semantics and computes its own ID. |
| R10-32 | Deployment/index change reuses execution identity | Stage 12 adds concrete deployment/config/index/data/execution contract; attempt identity separate. |
| R10-33 | Q7 creates IDs/pseudo-rows/hidden adaptivity | Global deferred status only; later exact trigger/workload/identity/map-back contract, no current activation evaluator. |
| R10-34 | Orphan/cross-context joins corrupt result map-back | Composite same-context FKs; source/role bijection; six decisions/context; explicit full reverse request→hypothesis→context→occurrence chain. |
| R10-35 | Source incidence/occurrence/candidate counts conflated | Separate counts/histograms and denominators, including no-candidate/zero-hypothesis rows and candidate multiplicity. |
| R10-36 | Production lineage/reference expansion unbounded | <=2 contexts/row, <=4 payloads/context, <=12 decisions/row; bounded selectors, exact caches, external streaming, no candidate×global-reference scan. |
| R10-37 | Byte/logical identity changes with worker/layout/order | Typed framed encoding, complete collision checks, canonical context sorting, summary without operational/self hashes, immutable checkpoints. |
| R10-38 | Protected examples/row digests leak through diagnostics | Row relations entirely protected; allowlisted global/family aggregates, no prompts or portable row/query IDs. |
| R10-39 | PanFS reuse assumes a new environment or reruns needless diagnostic | Same root/topology/mechanism/permissions preflight; stop on material difference; no new stage-number diagnostic; Stage 10 adapter only. |
| R10-40 | Design push implies implementation/HOLDOUT/production or rewrites science | Normal branch push only; main unchanged; full accepted-surface/ancestry checks and final owner implementation gate. |

## Remaining owner decisions

The mandatory revisions are fully specified; no unresolved bounded design defect
or additional policy question is left open by this package. The owner must
**approve this exact revised design and authorize implementation**. Approval in
principle does not supply that final authorization. This includes confirmation
of the derived occurrence grain/4–8 ceiling and tightened Q5/Q6 specification.

Operating B intentionally remains unselected pending DEVELOPMENT evidence.
Actual runtime binary/build hashes and synthetic expected-output vectors are
implementation review deliverables, not guessed design facts. Stage 11 complete
request semantics, Stage 12 deployment/result criteria and any later Q7 activation
are separate future contracts. These are explicit stage boundaries, not missing
Stage 10 implementation policy or grounds to start later stages now.

Residual scientific limitations remain: Stage 9 NE checks can limit Q4 positive
support; Q3 may add little utility; Q5 whole-line semantics may still be ambiguous;
generic Greek/Cyrillic romanization may be poor for some languages; and byte-large
requests may later be unschedulable. None is represented as current correctness.
The full representations, clear abstention, immutable lineage and future
DEVELOPMENT evaluation make these limitations reviewable without source changes.

## Review validation and preservation

Validate all document links/anchors, JSON/schema-draft consistency, design/spec/
public-asset hashes, math/counts, status words and accepted-scientific-surface
preservation. Only local documentation/public/synthetic checks are permitted.
No protected fixture is opened to make a documentation check pass. Exact public
ICU source files were read for hashes/ID verification, not installed or executed.

Commit and push the revised design branch normally after fetch/divergence and
privacy checks. Do not force-push, merge main, tag acceptance or launch a job.
The original first draft and all Stage 0–9 accepted/rejected history remain
reachable. Local checks passed: 109 document links/anchors, JSON parsing,
Unicode script-asset hash, complete 40-item ledger, six public ICU source/data
hashes, family-exclusion bound enumeration, expected DEVELOPMENT count arithmetic,
accepted code/tests/launchers/assets/stage-record/report equality, Stage 3 and
first-draft ancestry, and diff/privacy scope. Design inventory is rehashed after
final edits and checked before commit. Final response records the pushed SHA.

STAGE10_MULTI_HYPOTHESIS_QUERY_GENERATION_DESIGN_OWNER_REVIEW_READY

NEXT: FINAL OWNER APPROVAL TO IMPLEMENT STAGE 10
