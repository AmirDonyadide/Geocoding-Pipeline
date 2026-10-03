# Stage 11 — future DEVELOPMENT validation and reporting

Normative proposal within the [Stage 11 design](STAGE11_SEMANTIC_REQUEST_DEDUPLICATION.md).
**PLAN ONLY. No output counts, tests of an implementation, protected inspection
or job results are claimed.** The approved input has 142,677 hypotheses;
Stage 11's unique-core count and reduction remain unmeasured.

## Question and acceptance criteria

Does one deterministic global equivalence partition preserve every accepted
hypothesis and exact lineage while reducing repeated request work? All exact
integrity checks must pass with zero defects. No minimum dedup percentage,
speed target, result recall, precision, correctness, family budget, retrieval
depth or geocoding threshold is an acceptance criterion for this stage.

Evaluate the entire accepted DEVELOPMENT catalog: 35,000 source rows,
69,747 contexts, 142,677 hypotheses and 418,482 upstream family decisions.
`ALL_ELIGIBLE_CATALOG` remains controlling; operating budget **UNSELECTED**.
No family/context/source sample replaces full totality checks. The 1,668
zero-hypothesis contexts remain upstream; they do not become Stage 11 failures.

## Synthetic conformance plan before protected execution

After explicit implementation authorization, use invented data only for these
meaningful positive/negative and fault tests. Do not copy protected examples
into fixtures. An independently written encoder/oracle must challenge byte
vectors and projection, rather than merely invoking the materializer twice.

| Area | Required evidence |
|---|---|
| Exact global grouping | Equal full cores across different contexts, sources, roles, families and candidate IDs produce one core and all edges; 50 invented hypotheses produce 50 edges |
| False-merge counterexamples | Same text with changed country, endpoint/mode, one structured field or policy/domain produces different IDs, or a closed-schema rejection when the mutation is illegal in v1 |
| Text preservation | LF versus literal backslash+n, space, repeated whitespace, case, punctuation, composed/decomposed Unicode, astral characters, combining marks, RTL and leading-zero postcodes |
| Field/type rules | Missing schema column, null, empty, literal `null`, bool/int/string confusion, empty list, wrong mode/endpoint, unknown key, duplicate serialized key, lone surrogate/invalid UTF-8 |
| Policy/defaults | Reject explicit layers/sources/lang, spatial extras and unknown slot; show omission never collapses with an explicit default; reject unbounded/Q7 input |
| Canonical bytes | Independent exact hex-byte vectors for invented cores, named field order, lengths, null/string distinctions and full digest; reject trailing bytes and malformed/overflow framing |
| Collision guard | Controlled synthetic hash collision with distinct canonical bytes aborts before seal; equal bytes with incorrect claimed ID fail recomputation |
| Map integrity | Missing, extra, duplicate edge, orphan core, dangling FK, swapped edges with equal counts, cross-context family join and many-to-many inflation all fail |
| Provenance | Restore each invented hypothesis's exact source/context/role/candidate tuple and same-context family links; preserve no-hypothesis contexts via upstream left join |
| Determinism | Reversed/shuffled input, different batch/partition counts, worker order and physical compression yield identical core/map rows and logical hashes |
| Scale/skew | Many unique cores and one highly popular core; byte-heavy synthetic values; no group-sized lists or population in-memory state; resource failure never becomes a skip |
| Restart | Complete local loss, interrupted copy, partial unit, corrupted bytes, wrong executable/input/profile and overlapping/gapped ranges; only complete validated units adopted |
| Publication | Concurrent reservations/seals, before/after-effect errors, wrong adapter names, partial registration, absent/foreign seal, permissions/symlinks, fsync/reopen and post-commit presentation failures |
| Privacy | Poison synthetic payload/exception/SQL values never appear in portable output/logs; only allowlisted codes/counters; site/split guards reject before input access |

No network call is needed for Stage 11 tests. A mock Stage 12 serializer may
later demonstrate the stated handoff congruence using synthetic inputs, but
Stage 11 implementation authorization does not authorize a Pelias client or
Stage 12 implementation. Actual deployment/default compatibility belongs to a
separate Stage 12 review and is not a missing Stage 11 runtime test.

## Future controlled evaluation sequence

One separately authorized Goethe-NHR run will bind the approved design,
reviewed executable/runtime, exact accepted Stage 10 input and operational
resource plan. Guard before input access. No new Stage 10 generation or
upstream scientific validation. Submit once, wait and reuse its immutable
artifact; no duplicate while pending.

Required scientific verification passes:

1. Generate both relations with global full-ID/byte collision checking and
   bounded streaming, then verify complete upstream key and map totality.
2. Before the publication seal, independently reopen durable Parquet, re-encode
   every core, recompute every ID and reconstruct F(h) from every upstream
   hypothesis. Check exact edge/payload equality, hashes, all lineage joins
   and aggregates; no sampled substitute.
3. After commit, full validation from authoritative PanFS with local transient
   access disabled, using exact external manifest/registration expectations.
   Recompute relation and summary hashes and all invariants again. Only this
   verified outcome can be reported as a published candidate.

These are Stage 11's own required generation/prepared/committed checks. They
do not mutate or claim to rerun Stage 10's three accepted scientific replays.
A later independent reviewer must inspect the complete candidate and the
synthetic fault/conformance evidence before owner acceptance. A successful
job or a high reduction alone is not acceptance.

## Sanitized report metrics and exact denominators

Let N = input hypothesis count, U = unique core count, m(s) = number of map
rows for core s. Let C(s), R(s), F(s), and P(s) be distinct upstream context,
source-row, eligible-family, and representation-role sets reached through M→H.
F(s) uses eligible FIRST_MEMBER/CONVERGENT_MEMBER rows joined on **both**
hypothesis and context. Family memberships do not multiply m(s).

`stage11_semantic_request_summary_v1` is a single canonical aggregate object
with `summary_version`, `input_population`, `request_counts`, `reduction`,
`multiplicity`, `lineage_convergence`, `parameter_combinations`, `integrity`,
and `interpretation` groups. Unknown keys/arbitrary strings fail rendering.
Counters are uint64; proportions use integer numerator/denominator pairs,
not floating-point values in logical hashes. Renderer rounding is presentation
only. The following table defines its closed scientific metric content:

| Group | Required metrics / denominator |
|---|---|
| Input population | N; upstream sources=35,000, contexts=69,747, STANDARD=34,822, NATIVE=34,925, decisions=418,482; upstream contexts with zero hypotheses=1,668; ALL_ELIGIBLE_CATALOG and UNSELECTED constants |
| Core counts | U; FULL_TEXT and STRUCTURED core counts; their map/hypothesis counts separately; country-bound and unbounded counts at both grains |
| Reduction | `hypotheses_saved=N-U`; global reduction `(N-U)/N`; unique fraction `U/N`; these mean cores, not realized Stage 12 HTTP calls |
| Multiplicity | Counts of cores with m=1, 2, 3–5, 6–10, 11–50, 51–100, >100; corresponding sums of hypotheses per bin; max m; exact mean as N/U; empty-population denominator is null, never zero-divided |
| Cross-context | Count of cores with distinct contexts >1; denominator U |
| Cross-source | Count of cores with distinct source rows >1; denominator U; report separately from cross-context |
| Cross-family | Count of cores with distinct eligible families >1; denominator U; family-union cardinality histogram 1–6, with no request examples |
| STANDARD/NATIVE | Core counts STANDARD-only, NATIVE-only, both; count with at least one same-source STANDARD/NATIVE pair; latter uses distinct (core, source, role) incidence |
| Parameter combinations | Counts by endpoint/mode, structured presence mask for address/postalcode/locality/region/country, boundary present/unbounded, and fixed language/layers/sources/spatial/header/retrieval policy enums; both core and hypothesis denominators |
| Integrity | Input duplicate/missing IDs, invalid intents/boundaries/policies/encodings, ID collisions/recompute mismatches, missing/extra/duplicate map edges, orphan cores/FKs, projection mismatches, lineage mismatches, multiplicity-sum mismatch; all zero for publication |
| Interpretation | Fixed labels: WORKLOAD_CONVERGENCE_ONLY, NO_ACCURACY_ESTIMATE, OPERATING_BUDGET_UNSELECTED, NON_EXECUTABLE_CORE_CATALOG, STAGE12_NOT_STARTED |

Presence masks contain booleans about field presence only; they contain no
field values. Parameter-combination dimensions are closed and small. Do not
publish distinct-query digests, individual memberships, source names, full URLs,
postcodes/localities, rare payload examples or giant-payload excerpts. No
top-requests list. Country identities are not needed for the required v1 report;
bound/unbounded counts suffice without introducing an extra sparse cross-tab.

Expected input mode reconciliation from the accepted report is **33,556
structured hypotheses** and **109,121 free-text hypotheses**; U's split remains
unmeasured. Expected unbounded count is zero. Constant-policy combinations
must agree with the core schema; any unexpected combination is fatal, not a
new observed permissible policy. These baseline expectations do not predict
deduplication or accuracy.

Bin core counts sum to U; bin hypothesis sums sum to N. Mode counts at their
own grains sum to U/N; role categories sum to U; mean N/U and reduction use
the same populations. For every request m>=1 and |C|, |R|<=m. Families can
outnumber hypotheses for a core because Stage 10 preserved convergent
memberships; that is not a map anomaly. The full eligible-family link total
remains 172,112, distinct from 142,677 hypotheses and 418,482 decisions.

Attempt-only failure reports use a separate allowlisted operational envelope:
static phase/error counts, rows checked/unprocessed, durable receipt status,
resource/elapsed measurements and publication state. A failed attempt cannot
emit a successful scientific summary with unprocessed rows counted as valid.
Identity collision counts and technical failures must be reported even when
they abort; no protected offending value or ID is portable.

## Reporting artifacts, resource evidence and review limits

After an authorized run, `reports/development/stage11.md` would become the
sanitized human candidate/acceptance record under repository conventions.
Manifest-bound sanitized aggregate JSON could be committed under
`docs/scientific_assets/` following the Stage 10 pattern. Neither is created
as if measured in this design session. This plan is not a DEVELOPMENT report.

Operational receipts separately record exact executable/runtime, elapsed time,
peak RSS and measurement scope, local/spill peak if actually measured, durable
bytes, quota and checkpoint/restart/validation costs. Missing measurements are
UNAVAILABLE, not extrapolated from requested capacity. Report input throughput
in hypotheses and encoded bytes, and reduction as U/N. DEVELOPMENT success
does not prove production capacity; skew/giant synthetic results and later
resource evidence must support a production proposal.

No semantic human address adjudication is needed to prove exact deduplication.
All full-population checks occur within controlled compute; portable review is
aggregate/synthetic. The fixed 500-row infrastructure remains unchanged and is
not newly opened, rebuilt or required as an extra scientific relation. If a
later owner authorizes protected qualitative inspection, it must retain that
fixed selection and create a separate controlled review artifact.

Deduplication reduction measures repeated search input, not recall, precision,
address validity or geocoding accuracy. One unique core may eventually require
several execution identities because retrieval policy or deployment changes.
Stage 11 cannot claim N-U network calls saved as an observed outcome. Global
or cross-family convergence must never be counted as independent scientific
corroboration. Stage 12/13 calibration and scoring remain separate and unstarted.
