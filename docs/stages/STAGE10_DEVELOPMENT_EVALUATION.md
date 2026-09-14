# Stage 10 — future DEVELOPMENT evaluation and freeze gates

Part of the [design candidate](STAGE10_MULTI_HYPOTHESIS_QUERY_GENERATION.md).
This plan authorizes no implementation, protected reading, human review,
SLURM job or retrieval. HOLDOUT remains sealed.

## Implementation and synthetic validation gate

After explicit design approval, a separately authorized implementation must
publish exact schema/contract/profile/runtime-asset fingerprints and a complete
synthetic-validation record before any protected job can be reviewed.
Fixtures are invented or public and contain no protected values or row IDs.
Required falsification cases include:

- equal STANDARD/NATIVE slots, two different candidates on a source row,
  repeated provider IDs, no-candidate rows and zero-hypothesis candidates;
- identical candidate text shared across conflicting/partial source countries,
  different clean geography, different masks and different line layouts;
- every Stage 9 state, applicable/inapplicable scoped contradictions,
  source/parser argument confusion, missing expected evidence, wrong authority,
  GeoNames negative-authority violation and full-code country witnesses;
- identical repeated parser ordinals, different values, unknown labels, empty
  parse, warning-present and warning-absent semantic errors;
- unchanged Q1/Q2 bytes, LF-vs-space, gaps/repeated lines, combining marks,
  native scripts, Unicode lowercasing history and strings with leading zeros;
- Q4 locality-only, postcode-only, supported pair, failed relationship support,
  postcode-pattern/prefix veto, admin-level exclusion and no eligible fields;
- Q5 embedded “unit” street/building text, whole-line false positives, digit-only
  street lines, repeated values, ambiguous/intersecting components, floors,
  unsupported markers/scripts, empty remainder and unchanged full baseline;
- Q6 exact registered transforms, asset mismatch, supported/unsupported/mixed
  scripts, Common/Inherited marks, existing Latin, preservation of digits and
  punctuation, residual script, empty/equal output and whole-string equivalence;
- complete-intent differences in endpoint, country, structured fields and shared
  policy reference; injected hash collision must fail, not collapse;
- convergence before budget selection, budgets 1..5, catalog-only mode,
  baseline rank, family credit beyond rank B, hard-ceiling violations and Q7's
  constant-false activation under every synthetic result/error history;
- full map-back/lineage-selector replay, orphan and cross-candidate membership,
  missing candidate decisions, source-row versus occurrence denominators;
- byte/component giants with tiny streaming batches, external spilling,
  deterministic shard order, restarts and logical-hash invariance; and
- shared execution guard before input access, split/path/runtime rejection,
  0700/0600 modes, publication fault/adoption/collision/reopen and strict
  aggregate-report allowlisting.

These tests should challenge scientific failure modes and cardinality, rather
than merely mirror implementation. No source or executable test is added in
this design session.

## One future offline DEVELOPMENT artifact

After separately reviewed implementation and exact-workload authorization,
submit the reviewed offline job once from an exact pushed SHA and reuse its
immutable artifact while pending/completed. Proposed first mode is CATALOG_ONLY:
complete bounded Q1–Q6 generation, no executable Stage 11 selection. A numeric
B must be approved separately for any INITIAL_PLAN. Candidate totality derives
from the exact accepted inputs, not a filtered development extract.

Expected input counts are 35,000 source rows, 69,747 representation occurrences
(34,822 STANDARD and 34,925 NATIVE), 51,779 exact candidates, 6,106,088 parser
components, and 6,565,329 Stage 9 evidence rows. Expected **family decisions**
are `7 × 51,779 = 362,453`; generated hypothesis counts remain unknown.
The engineering upper bound is `5 × 51,779 = 258,895` generated hypotheses,
not an expected count or an authorized Pelias workload.

Report the following exact integer metrics with named denominators:

| Group | Required outputs / denominator |
|---|---|
| Input preservation | Source/candidate/component/evidence/occurrence counts; input bindings; zero missing, added, cross-wired and orphan rows |
| Coverage | Candidates with >=1 and zero generated hypotheses / all candidates; selected coverage separately; source-row union and occurrence coverage separately; no-candidate source rows |
| Family eligibility | All seven evaluated slot counts; ELIGIBLE/INELIGIBLE/DEFERRED counts and family-level primary/all reasons / candidate × family slots |
| Output and cost | Generated/selected/suppressed hypotheses, candidate-local distinct intents, global distinct exact intent fingerprints with byte verification, UTF-8 bytes, future request estimate |
| Convergence | STANDARD/NATIVE equal-candidate cases; Q3/Q5/Q6 convergence to baseline/other families; family bitmask intersection counts; family constructions minus distinct intents |
| Alternatives | Q3 boundary unanimity and divergent-layout counts; Q4 locality/postcode/pair availability and field exclusions; Q5/Q6 availability and reasons |
| Budgets | Complete histogram 0..5 per candidate; selected histogram; number at B and number exceeding B before suppression; number at engineering ceiling; hard-ceiling failures |
| Suppression | Family/field reason counts, exact duplicate convergence, budget suppression, source-country and source-boundary abstention; multiple reasons labeled overlapping |
| Protected/portable | Row counts of both protected relations and complete selector counts; portable summary objects/cells; zero portable protected strings/row IDs/query digests |
| Technical | Failure count and closed error categories; validation/reopen outcomes, elapsed time, MaxRSS, spill, peak buffered bytes, largest candidate, output bytes and verified checkpoint reuse |

Keep logical candidate-local intent counts separate from global distinct intents.
Global intent counts are a **prospective workload proxy**, not yet Stage 11
unique semantic requests: the common retrieval policy has not been resolved.
Once Stage 11 exists, reconcile complete semantic requests explicitly, including
request-contract QA failures such as byte limits and unresolved defaults.
No Stage 10 report may claim recall, geocoding accuracy, valid-address rate,
correct-candidate contribution or optimal family selection.

## Exact summary shape and disclosure

`query_generation_summary` is one canonical JSON object with these required
keys: `summary_version`, `input_binding_sha256`, `science_sha256`,
`budget_policy_sha256`, `plan_mode`, `operating_budget`, `engineering_ceiling`,
`source_row_ceiling`, `input_counts`, `coverage_counts`, `hypothesis_counts`,
`family_cells`, `convergence_cells`, `candidate_histogram`, `budget_counts`,
`field_decision_cells`, `artifact_row_counts`, `validation_counts`.
Version is `stage10_query_generation_summary_v1`. Integers are unsigned, B is
null only in CATALOG_ONLY, and no metric stores a floating-point rate.

Cell dimensions are closed family/reason/eligibility/membership/field enums and
the seven-bit family mask, never arbitrary strings. Histograms have fixed
bins 0..5 and counts. Each metric value/cell carries `count`, `denominator`,
`denominator_kind`; denominator kinds are ABSOLUTE, CANDIDATE, SOURCE_ROW,
OCCURRENCE, FAMILY_SLOT, GENERATED_HYPOTHESIS, SELECTED_HYPOTHESIS or FIELD_SLOT, with the
population named by its metric definition. Overlapping reason and family
incidence cells must not be summed as partitions. Canonical array order is
numeric family/mask/bin then declared enum order. Emit explicit zero cells for
closed histograms and family eligibility outcomes; reason cells are observed
only. There are no free-text error payloads or row-derived examples.

The fixed count-key allowlist is:

```text
input_counts: source_rows, candidates, occurrences, standard_occurrences,
  native_occurrences, parser_components, reference_evidence_rows,
  source_rows_without_candidate
coverage_counts: candidates_generated, candidates_zero_generated,
  candidates_selected, candidates_zero_selected, source_rows_generated,
  source_rows_selected, occurrences_generated, occurrences_selected,
  country_context_abstained_candidates, boundary_nonunanimous_candidates
hypothesis_counts: eligible_family_constructions, generated, selected,
  budget_suppressed, catalog_only, global_distinct_intents,
  candidate_local_duplicate_reduction, global_intent_duplicate_reduction,
  generated_text_utf8_bytes, selected_text_utf8_bytes
budget_counts: candidates_at_operating_budget,
  candidates_above_operating_budget_before_suppression,
  candidates_at_engineering_ceiling, source_rows_at_engineering_ceiling
artifact_row_counts: query_hypothesis, query_family_decision,
  portable_summary_objects
validation_counts: missing_candidates, added_candidates, missing_sources,
  added_sources, orphan_hypotheses, orphan_family_memberships,
  cross_candidate_memberships, selector_mismatches, byte_collisions,
  map_back_mismatches, ceiling_violations, technical_failures,
  portable_protected_values, pelias_calls, external_address_calls
```

Counts are unsigned integers, with null count permitted only for unselected
operating-budget metrics in CATALOG_ONLY. Absolute totals/byte sums use
denominator_kind ABSOLUTE and null denominator; other denominators are unsigned
integers. No rate is calculated for a zero denominator. Denominators
for candidate/source/occurrence incidence are the corresponding complete input
population; relation counts and byte sums are absolute totals. `family_cells`
have unique key `(family, eligibility_state, membership_state, reason)`;
include an ALL-reasons cell for disjoint state counts and separate overlapping
reason cells. NONE denotes no reason and ALL denotes the disjoint state total;
both are summary-only sentinels. Denominator is all candidates for that family.
`convergence_cells` is an object with keys `by_family_mask` (cells keyed by
family_mask/selection_status, denominator all generated hypotheses),
`standard_native_equal_source_rows` and `standard_native_equal_candidates`
(incidence metrics over their respective full input populations).
`candidate_histogram` has `(scope=GENERATED|SELECTED, bin, count)` with denominator
all candidates. `field_decision_cells` have `(field, disposition, reason_or_NONE,
count)` over all candidate Q4 slots. A field that was not evaluated because a
common gate failed is NOT_APPLICABLE, not an evaluated failure. Mask/state and
family cells allow exact Q3/Q5/Q6 convergence and availability without extra
row relations. Unknown keys or dimensions fail validation.

Adding a new metric is a reviewed schema/profile change.
Timing, host/job/Git/resource and physical-byte measurements belong in the
operational manifest/receipt, not this logically reproducible summary. The
portable report can reproduce those non-sensitive operational metrics alongside
the exact summary hash. Country/script/length cross-tabs and review material
remain controlled unless separately approved for disclosure; this version's
portable summary contains only global/family aggregates and no geographic
small-cell joins. A portable CSV/Parquet of hypotheses is never a sanitized
summary, even when query strings have been removed.

## Budget calibration and marginal utility

1. Using one immutable catalog, compute every B in 1..5 under the same frozen
   order. Simulate each prefix by rank and convergence; no new generation or
   repeated protected run is needed. Compare candidate/source coverage, local
   and global intent counts, marginal new intents by family, redundancy,
   convergence and projected cost. Partition context-abstained candidates so
   a lower cost caused by lost country coverage remains visible.
2. Predeclare the DEVELOPMENT trial selection, complete Stage 11 request
   contract, retrieval policy, trial budgets and owner tolerances for marginal
   cost/recall before retrieval. A trial at the engineering ceiling is an option
   for unbiased family comparison, not an automatically authorized workload.
   A smaller partial trial cannot support utility claims for unexecuted families.
3. After later separately accepted/authorized Stage 12/13 data exists, compare
   the same source/candidate populations against independently adjudicated
   DEVELOPMENT targets. A returned feature is not a correct candidate. Freeze
   correctness/granularity/adjudication rules and deployment/index identity;
   use a held-apart DEVELOPMENT validation partition, not sealed HOLDOUT.
4. For each family report recall and unique correct-candidate contribution,
   marginal benefit after preceding families, added complete semantic requests,
   response volume/runtime cost, false-candidate contribution, redundancy and
   convergence support. Shared requests cost once; credit can belong to multiple
   families. Leave-one-family-out ablation must keep a request when another
   family still contributes it. Also report cumulative prefix ablation.
5. Select the smallest B meeting the predeclared owner recall-loss and cost
   tolerances on DEVELOPMENT, with uncertainty and country/script coverage
   reported. If no B qualifies, report that outcome for design review; do not
   silently exceed five. Family reordering/eligibility/transform changes require
   a new immutable scientific version and renewed validation. The thresholds
   are later owner choices, not arbitrary numeric claims in this design.

Do not equate identical text/requests, shared references or STANDARD/NATIVE
convergence with independent votes. When request budgets or populations differ,
report missing family observations explicitly; do not impute zero benefit.
Q7's later activation utility needs its own predeclared conditional denominator
and paired ordinary-versus-diagnostic analysis if it is ever enabled.

## Controlled qualitative review and independent review

Future Stage 10 transformation review uses the accepted fixed-500 DEVELOPMENT
identities and preserves their established order/lineage. Owner-authorized human
reviewers inspect full versus alternate forms on controlled infrastructure,
especially Q3 boundaries, Q4 role over-constraint, Q5 legitimate information loss
and Q6 script/language distortion. No protected text is sent to an LLM or
external service. Additional coverage-targeted DEVELOPMENT cases require a
predeclared selection and scope. Previously reviewed parser cases must not be
described as fresh blinded validation. Stage 10's fixed-500 review concerns
hypothesis defensibility, not current geocoding correctness.

Independent review later reopens the single immutable artifact and recomputes
all input bindings, hypotheses, exact intents, selectors, transformations,
gates, convergence, budgets, logical hashes, map-back and publication state.
Accepted-source preservation and family-related losses must be checked beyond
aggregate counts. Rejection preserves the artifact and requires owner review
before any bounded repair/reexecution. Scientific acceptance requires explicit
owner acceptance after independent review and then a stop.

## HOLDOUT and downstream freeze

Before one-shot HOLDOUT, freeze at minimum family definitions/order, exact
transform rules/assets/versions, all eligibility/abstention rules, engineering
and operating budgets, suppression/convergence policy, identity/selector/schema
formulas, Stage 11 complete semantic request contract and parameters, Stage 12
deployment/execution identity, and every enabled conditional activation rule.
If Q7 stays disabled, freeze constant FALSE and zero diagnostic slots explicitly.
If it is enabled, its sufficient result predicate, witness/completeness gates,
combined budget and immutable wave/dedup contract must be accepted first.

No HOLDOUT access/tuning is authorized here. Benchmark V1 stays 35,000
DEVELOPMENT / 15,000 HOLDOUT from 1,405 files; the later six production files do
not change it. Production Stage 2 remains not started. The current Stage 19
acceptance and separate exact-workload Pelias authorization gate remains in
force; a Stage 10 design freeze cannot reconcile or waive it.
