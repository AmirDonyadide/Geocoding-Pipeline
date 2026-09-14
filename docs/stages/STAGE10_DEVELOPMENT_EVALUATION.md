# Stage 10 — context-aware DEVELOPMENT evaluation and freeze gates

Normative revision of the [design package](STAGE10_MULTI_HYPOTHESIS_QUERY_GENERATION.md).
Implementation, protected access, jobs, human review and retrieval are not
currently authorized. This document describes the next reviewable procedure.

## Implementation and synthetic validation gate

After final owner approval to implement, freeze exact executable contract/profile/
schema/runtime build fingerprints matching this design before proposing any
protected run. Synthetic fixtures must be invented/public. Required challenge
cases cover the complete design, including:

- same exact candidate on two rows with different country, geography, line masks,
  boundaries and representations; eligible context A unchanged by context B;
- same-row equal STANDARD/NATIVE candidate IDs producing two contexts; Q1/Q2
  role exclusivity, Q6 native-only, and exact later many-context request map-back;
- missing/malformed source country for one context, SOURCE_ROW Q01 recognition,
  all-unresolved Stage 9 country assessment, and candidate-wide Stage 9 NE checks
  without blocking full-text/line/transform families with valid local country;
- same-context versus other-row/candidate/parser postcode contradictions,
  exact argument/country/authority/witness gates, GeoNames negative prohibition,
  NOT_FOUND/NOT_EVALUABLE and internal conflicts without false negative claims;
- Q4 locality/postcode/pair support, unchanged full address, source-only field
  use, unsupported region/admin level and missing expected evidence as fatal;
- four-slot Q3 gaps, repeated lines, equal texts with different layouts, embedded
  LF versus inserted LF, unchanged one-line convergence and invalid source FKs;
- Q5 complete-line versus mixed-content marker, uniquely aligned components,
  source-geography veto, duplicate/unknown labels, empty evidence, multiple
  possible alignments, retained byte equality and no reliance on warning absence;
- Q6 pinned canonical ICU IDs (not unverified aliases), asset/data/version/filter
  mutations, Greek/Cyrillic/Latin mixtures, unsupported scripts, inherited marks,
  exact pre/post NFC, empty/unchanged/residual-script output and native retention;
- the four-per-context/eight-per-row reachable synthetic construction, Q1/Q2 and
  Q5/Q6 mutual exclusion, six decisions, complete eligible catalog, no arbitrary
  budget suppression and zero Q7 pseudo-rows/IDs under any simulated result history;
- full-intent equality/difference including endpoint, fields, country and policy
  slot; injected collisions, cross-context FK attachment and orphan family rows;
- context/source/candidate cardinality and exact reconstruction of every selector,
  query and transformation from immutable input identity; repeated witnesses
  shared without candidate×occurrence×component/reference explosions;
- giant candidate/component inputs, tiny byte batches, spills, context sharding,
  cache order independence, restart and logical-hash invariance; and
- pre-input guard, private topology, expected PanFS same-mechanism preflight,
  publication fault/adoption/uncertain outcomes and strict portable reporting.

Tests must falsify scientific invariants, not merely mirror implementation.
No materializer/test implementation is part of this documentation revision.

## First future DEVELOPMENT run: all eligible static hypotheses

After separate execution authorization, submit exactly one reviewed offline job
from a clean exact pushed SHA. Use `ALL_ELIGIBLE_CATALOG`, operating budget null.
Materialize every eligible Q1–Q6 construction, converge complete intents within
each context and retain all memberships. No operating budget suppresses an
eligible family. Exceeding a mathematically derived engineering bound is a
fatal implementation defect, never truncation. No Q7 query/decision ID exists.
Do not tune policy or inspect protected individual examples to change it during
this first run; reuse the immutable artifact once completed.

Accepted input counts: 35,000 source rows, 69,747 representation occurrences
(34,822 STANDARD, 34,925 NATIVE), 51,779 exact candidates, 6,106,088 parser
components and 6,565,329 Stage 9 evidence rows. Therefore the initial artifact
must represent **69,747 contexts and 418,482 family decisions** (6 × contexts).
It can contain at most **278,988 hypotheses** (4 × contexts), with <=8 on any
source row. Actual hypotheses/coverage remain unknown. These counts are not an
authorized Pelias workload. The candidate total is retained for reconciliation,
not used as the hypothesis-generation denominator.

## Required context-aware diagnostics

| Group | Required metrics and grain |
|---|---|
| Input/lineage | Complete source/candidate/occurrence/component/evidence counts; exact hashes; no missing/added/cross-wired/orphan contexts or source links |
| Context totality | Context count; STANDARD/NATIVE contexts; candidates with >1 context; source rows with >1 context; contexts/candidate and contexts/source-row distributions |
| Context diversity | Per-candidate distinct requested-country/status count and exact four-slot boundary-vector count; numbers with >1 each; no eligibility change from these diagnostic groupings |
| Coverage | Contexts with >=1/zero hypotheses; source rows and exact candidates with >=1/zero hypotheses; absent-representation/no-candidate source rows separately |
| Families | Six slot evaluations/context; eligible, ineligible, first-member, convergent-member and suppressed counts/reasons; Q7 one global deferred status |
| Output | Hypotheses/context, source row and candidate; eligible constructions; local distinct intents; global distinct intent opportunities and corresponding cross-context reduction |
| Convergence | Family masks per context hypothesis; Q3/Q5/Q6 baseline convergence; equal STANDARD/NATIVE intent incidence across the same source row; exact byte equality checks |
| Availability | Q3 line availability; Q4 locality/postcode/pair and field decisions; Q5 removals/vetoes; Q6 script/output availability and abstention |
| Budgets | Contexts at engineering ceiling 4, rows at 8; bound violations; zero initial QUERY_BUDGET_SUPPRESSION; operating B UNSELECTED |
| Publication/privacy | Protected relation rows, complete selector counts, one portable summary object, zero protected strings/row/query IDs in portable output |
| Technical | Closed failure categories, validators/reopen, elapsed/MaxRSS/spill/peak buffered bytes, giant values, output sizes/checkpoint reuse; no geocoder calls |

Country diversity counts distinct `(local_country_state, boundary_or_null)` per
candidate; states are SOURCE_CODE_RECOGNIZED, SOURCE_CODE_MISSING,
SOURCE_CODE_MALFORMED, SOURCE_CODE_UNRECOGNIZED. For boundary diversity compare
complete four-slot lower vectors including empties, not just hashes/LF text.
Role counts and context multiplicity remain separate. These aggregate questions
never select a representative context or require agreement across contexts.

Global distinct Stage 10 intents are a prospective **Stage 11 dedup opportunity**,
not finalized semantic requests. Stage 11 must first resolve the common request
policy and every result-affecting parameter. Later reconcile actual unique
semantic requests, unschedulable sizes and complete context/family map-back.
Stage 10 has no geocoder results and cannot measure accuracy, address validity,
correctness contribution or recall. Repeated parser evidence is not a denominator
for context/address prevalence; preserve the Stage 9 Q04 grain limitation.

## Exact sanitized summary contract

One canonical JSON object with required keys: summary_version,
input_binding_sha256, science_sha256, budget_policy_sha256, plan_mode,
operating_budget, ceilings, deferred_families, input_counts, context_counts,
coverage_counts, hypothesis_counts, engineering_counts, family_cells,
convergence_cells, field_decision_cells, histograms, artifact_row_counts,
validation_counts. Unknown keys/enum values fail validation. Version is
stage10_query_generation_summary_v1; plan_mode ALL_ELIGIBLE_CATALOG; B null;
ceilings = {per_context:4, per_source_row:8, per_candidate:'4*occurrence_count'};
deferred_families = {Q7:'DEFERRED_RESULT_DEPENDENT_DIAGNOSTIC'}.

Fixed scalar count keys:

```
input_counts: source_rows, candidates, occurrences, standard_occurrences,
  native_occurrences, parser_components, reference_evidence_rows,
  source_rows_without_candidate
context_counts: contexts, standard_contexts, native_contexts,
  candidates_with_multiple_contexts, source_rows_with_multiple_contexts,
  candidates_with_multiple_country_contexts,
  candidates_with_multiple_boundary_contexts
coverage_counts: contexts_with_hypothesis, contexts_without_hypothesis,
  source_rows_with_hypothesis, source_rows_without_hypothesis,
  candidates_with_hypothesis, candidates_without_hypothesis
hypothesis_counts: eligible_family_constructions, hypotheses,
  global_distinct_intents, within_context_duplicate_reduction,
  across_context_intent_reduction, generated_query_utf8_bytes
engineering_counts: contexts_at_ceiling, source_rows_at_ceiling,
  bound_violations, operating_budget_suppressions
artifact_row_counts: query_hypothesis, query_family_decision,
  portable_summary_objects
validation_counts: missing_contexts, added_contexts, missing_candidates,
  added_candidates, missing_sources, added_sources, orphan_hypotheses,
  orphan_family_memberships, cross_context_memberships, context_fk_mismatches,
  selector_mismatches, byte_collisions, map_back_mismatches,
  technical_failures, portable_protected_values, pelias_calls,
  external_address_calls
```

Counts use unsigned integer arithmetic. Every scalar metric/cell has count,
denominator and denominator_kind; ABSOLUTE totals have null denominator. Other
kinds are SOURCE_ROW, CANDIDATE, CONTEXT, FAMILY_SLOT, HYPOTHESIS or FIELD_SLOT,
with the named complete input/slot population as denominator. Zero denominator
has no rate; no floating-point rates are stored. No output/manifest/summary
self-hashes occur in the object.

Family cells have unique (family Q1..Q6, eligibility, membership, reason); ALL
is the disjoint state-total reason and NONE means no reason. Individual reason
cells overlap and must not be summed as a partition. Denominator is all contexts
for that family. Q1 on NATIVE/Q2 on STANDARD record role unavailability, not
missing source representation on the whole row. Q7 is not counted as six-slot
eligibility or suppression. Field cells have (field, disposition, reason), with
one slot per context for each of Q4's six fields; NOT_APPLICABLE distinguishes
an unevaluated common-gate failure.

Convergence cells comprise by_family_mask (six-bit Q1..Q6 mask and hypothesis
count, denominator all hypotheses), same_row_full_standard_native_equal (row
incidence), and same_row_full_standard_native_evaluable (both full baselines
available). Equal cross-context full intents are counted as cost opportunity;
no context family membership is invented or merged. Mask histograms express
all within-context family overlaps; source-row incidence never counts twice.

Histograms have scope, lower_inclusive, upper_inclusive, count, denominator,
denominator_kind. Fixed exact bins: HYPOTHESES_PER_CONTEXT 0..4,
HYPOTHESES_PER_SOURCE_ROW 0..8, CONTEXTS_PER_SOURCE_ROW 0..2. For
HYPOTHESES_PER_CANDIDATE, CONTEXTS_PER_CANDIDATE,
COUNTRY_CONTEXTS_PER_CANDIDATE and BOUNDARY_CONTEXTS_PER_CANDIDATE use bounded
bins [0], [1], [2], [3,4], [5,8], ..., [2^63+1,2^64-1], clipping the final upper
bound to uint64 max. Also store exact min/max/sum for each histogram scope.
This retains bounded memory and portable size while measuring candidate reuse.
All candidate histograms include the complete accepted candidate set; source-row
histograms include no-candidate rows. Emit zero bins and sort by scope enum
in the order listed above, then lower bound. Family/field cells sort by declared
schema enum order; masks by unsigned integer. No arbitrary string dimension.

Peak memory, time, host/job/runtime/Git, physical bytes and exact build hashes
belong in the operational manifest/receipt, not the logically reproducible
summary. Both row-level relations and selectors stay protected, including
hashed IDs. Portable output contains global/family aggregates only: no examples,
country/script labels cross-tabulated with small cells, source filenames or
arbitrary exception text. Future additional metrics require a reviewed schema
change; protected debugging output cannot be relabeled a sanitized report.

## Calibration A — structural and cost evidence available at Stage 10

From the one immutable all-eligible catalog, measure context/source coverage,
convergence, uniqueness and projected cost. Simulate operating prefixes B=1..4
per context with the frozen family order, retaining every underlying payload.
No first-run suppression or rerun is needed. Report effects by context and source
row and candidate reuse, not just totals. A later operating plan is a new
immutable policy/profile; it cannot modify the catalog or become an execution
workload without separate review/authorization. No fixed candidate cap is used.

Cost evidence can justify a provisional trial size, not an accuracy-optimal
budget. Any future family/rule/order change requires owner review and a new
scientific version; do not tune the initial run from individual protected cases.

## Calibration B — later recall and family value

Only after separately frozen/authorized Stage 11–13 behavior and outcomes exist:

1. Predeclare a paired DEVELOPMENT trial, complete request policy and exact
   deployment/index. Full-ceiling retrieval is one option for observing every
   family, not automatic workload authorization. Unexecuted families have missing
   evidence, never zero benefit. Freeze adjudication/granularity rules and a
   held-apart DEVELOPMENT validation frame before calibration.
2. Use independently adjudicated correct-candidate targets; returned feature,
   confidence and rank are not correctness. Report context and source-row recall,
   unique correct-candidate contribution, marginal benefit after earlier families,
   complete-request costs/response volume, false-candidate contribution,
   redundancy and convergence with explicit denominators and uncertainty.
3. Charge a shared complete request once across all contexts. Retain every
   contributing family but do not count shared parser/reference ancestry or
   STANDARD/NATIVE convergence as independent votes. Leave-one-family-out
   ablation removes a request only when no surviving family/context requires it;
   context/source-level availability and globally saved request cost differ.
4. Select the smallest B meeting predeclared owner cost/recall-loss tolerances,
   using DEVELOPMENT only. No qualifying B is a review outcome, not permission
   to exceed the ceiling. Enabled later Q7 would need a distinct conditional
   denominator, deterministic triggering evidence and paired diagnostic analysis.

## Controlled review, acceptance and HOLDOUT freeze

After the first immutable run, any separately authorized human qualitative
review uses the fixed-500 DEVELOPMENT identities and established order on
controlled infrastructure, never protected prompts or external services.
Examine Q3 boundary usefulness, Q4 over-constraint, Q5 whole-line false removals,
Q6 distortion, and contexts sharing a candidate with divergent source evidence.
Source rows with two contexts stay two linked review surfaces. Additional cases
require predeclared selection; historical parser examples are not fresh blinded
validation. No protected individual review is authorized in this design session.

Independent review later recomputes complete contexts, generation/gates, all
memberships, selectors, exact bytes/hashes, counts/map-back and publication from
the one immutable artifact. Rejection preserves history; acceptance requires
explicit owner approval and a stop. No approval of this design launches a job.

Before one-shot HOLDOUT freeze families, context identity/grain, transforms and
assets, eligibility, engineering/operating budgets, suppression/convergence,
lineage/identity/schema formulas, Stage 11 complete request semantics, Stage 12
deployment/execution identity and all enabled conditional rules. Q7 stays
explicitly deferred unless a separately approved sufficient contract exists.
No HOLDOUT tuning. Benchmark remains 35,000 DEVELOPMENT / 15,000 sealed HOLDOUT
from 1,405 files; later six production files do not alter it. Production Stage 2
is not started; the Stage 19 acceptance/explicit-workload geocoding gate remains.
