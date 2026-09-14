# Stage 10 — bounded multi-hypothesis query generation

## Status and authority

**OWNER REVISIONS INCORPORATED — DESIGN FROZEN FOR FINAL OWNER REVIEW.**
Architecture is approved in principle. The owner required occurrence-aware
contexts, a proven engineering ceiling, exact transformations and a normal
branch push. This revised design is not implementation authorization and is
not Stage 10 scientific acceptance. The first draft at
`642fa170ac594f6fe425a9272b5dae6bdff584cc` remains reachable history;
its cross-occurrence unanimity and candidate-level budgets are superseded.
Stop after the frozen revision is pushed for final owner approval to implement.

Normative package:

- this scientific contract, inputs, budget, execution and publication boundary;
- [family definitions](STAGE10_QUERY_FAMILIES.md), including exact gates;
- [data contract](STAGE10_DATA_CONTRACT.md), identities and Stage 11 handoff;
- [evaluation plan](STAGE10_DEVELOPMENT_EVALUATION.md); and
- [complete design review and owner decisions](STAGE10_DESIGN_REVIEW.md).

Design identifiers remain `stage10_multi_hypothesis_query_contract_v1`,
`stage10_multi_hypothesis_query_profile_v1`,
`stage10_multi_hypothesis_query_schema_v1`,
`stage10_query_intent_v1`, `stage10_query_logical_encoding_v1`,
`stage10_query_validation_v1`, and `stage10_query_manifest_v1`.
The [design freeze inventory](../scientific_assets/stage10_design_freeze_v1.json)
hashes the review documents and exact transliteration specification. These are
design-byte hashes; executable contract,
Arrow schema, runtime-asset and output fingerprints do not yet exist. No future
fingerprint is invented or described as verified.

## Baseline gate and evidence limits

Before design, `git fetch --prune origin` succeeded. The tree was clean and
HEAD = main = origin/main = `23cfb85f428b00301d68591ea5992763abf9ad88`.
Annotated tag `stage09-offline-reference-evidence-v1` exists and peels to that
same owner-acceptance commit. D047/D060 and accepted reports record
`STAGE_8_ACCEPTED`, `STAGE_9_ACCEPTED`, Stage 10 NOT STARTED, HOLDOUT SEALED,
and production/Pelias untouched. No unexpected baseline divergence was found.
Before owner revision, fetch again verified clean design HEAD `642fa170…`, with
main/origin-main still at the accepted baseline. No accepted artifact was opened.

Verification used Git, committed contracts, code and sanitized records only.
It did not reopen controlled artifacts, inspect the HOLDOUT seal on storage,
contact Goethe, or attest to unobserved external activity. Those exclusions
preserve the session's explicit no-access boundary. The accepted records are
the authority for baseline data status. This session made no protected reads,
job submissions, Pelias requests or external address/API calls. Public ICU
documentation was consulted without protected input.

Accepted Stage 9 bindings (full SHA-256 unless marked otherwise):

| Binding | Frozen value |
|---|---|
| Accepted executable, Git SHA-1 | `3e10ac7c1309c2636f35c0709fa283305d60d998` |
| DEVELOPMENT job | `1771191`, COMPLETED, ExitCode `0:0` |
| Manifest | `321c9d8352fac5b78612a7c8e52f6f810f92bddb1e91f7cfe348398a6d707240` |
| Logical dataset | `7ae84e149f4c9c2de7a791c9b326b88e387a70d155d8be55acf6b55e06bafae3` |
| Contract | `6dc0410556bad44a6a6d1b3695beb6219c54a61dab39747a5ffa92ac9fcda3f9` |
| Profile | `b12be7ba06de2360ba7cd9b971c4b562b1c8df5d25c30024975869fd2b34efd1` |
| Schema bundle | `7374b70fae76149b825f523e8317577bd6d868bee3fde648ea915301d4bcb716` |
| Stage 8 input binding | `64f7678a76e3f29f57859f050329be925b216d2b1290eff5d36b9cb4482cea90` |
| Reference-pack manifest | `dd7994b907250d515470b820bcbf42993a08e4f3116409b7c94168446e1c064a` |
| Reference lock | `61cc5850372886eb4ba6477a178ebd74f6ca878815036874ad47069ca32a1c63` |
| Independent review, Git SHA-1 | `a9ae443ca140627acf1712886670f39f227c1dc6` |
| Independent job | `1772139`, PASS, candidate defects = 0 |

Accepted Stage 9 artifact:
`/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage09/development/stage09_development_20260910T155542Z_3e10ac7c1309`.
The [acceptance record](../../reports/development/stage09.md#owner-acceptance-and-freeze--2026-09-14)
remains unchanged and controls interpretation of the accepted run.

## Purpose and scientific separation

Stage 10 creates a small deterministic set of query hypotheses. It performs no
geocoding, ranking, correction, address acceptance, validity classification,
coordinate production or granularity assignment. No fuzzy replacement,
postcode neighbor search, street correction or house-number repair is allowed.

The separate concepts remain SOURCE_VALUE → DERIVED_REPRESENTATION;
PARSER_EVIDENCE and REFERENCE_EVIDENCE may inform QUERY_HYPOTHESIS; later
GEOCODER_RESULT and FINAL_ACCEPTED_RESULT are different relations and decisions.
These arrows describe provenance, not increasing truth. Source values never
change. A supported lookup does not certify a parser label or a hypothesis.

Q1/Q2 mean the complete accepted Stage 5/6 **lowercase line-body candidate**.
Stage 5 deliberately excludes separate postcode/city/region/country fields.
Stage 10 must not silently reinterpret “full” as concatenating those fields,
select a representative case-preserving source variant, or restore an invented
case. Raw, clean, lower, STANDARD and NATIVE provenance remains recoverable.

## Smallest authoritative input surface

1. **Accepted Stage 8** `candidate_evidence`, `parser_component_evidence`,
   `source_candidate_map` and its non-materialized `representation_occurrence_v1`
   view. This supplies exact Stage 6 candidate IDs/text, Stage 7 evidence,
   typed component ordinals, source geography and all source/representation links.
2. **Accepted Stage 9** `candidate_reference_evidence` and
   `reference_match_member`, plus bound public-pack `reference_registry`,
   `reference_capability`, and the witness fields in `reference_object` needed
   to interpret existing evidence. `coverage_summary` is a reconciliation
   input, never an eligibility shortcut. No reference lookup is rerun, refreshed
   or expanded; no new match set is created.
3. **The exact Stage 6 row map transitively bound by Stage 8**, read only for
   stable-ID/slot validation and the preserved Stage 5 line/mask/reconstruction
   surface. This is a column projection of an existing authoritative artifact,
   not a new source map. No Stage 6 registry payload, Stage 7 artifact, raw CSV,
   earlier-stage payload or protected review artifact is additionally required.

Exact additional anchors:

| Binding | SHA-256 |
|---|---|
| Stage 8 manifest | `2a50bd8c066552c9cb7505ed2d6071f1ee36161b9a2cc07f3ed364cf00237827` |
| Stage 8 logical dataset | `9c9d431c2c1b92712e0cb372f2661ad48f4fe8758dc0327d25aef90ab2c2d526` |
| Stage 8 contract | `8b3c530e714177fe2c30a97d61dcc199b7f9efba58f3c17a291b817af0f24d5e` |
| Stage 8 schema bundle | `6c8ebecd24c495dbe2ce32125ac1cb89c4a9de4905c786b774d10ad728ed392f` |
| Stage 8 label mapping | `b18167d2d5c1f1402d1bb0e92559befb92418f5f4f34df885596778a11d5c09d` |
| Stage 6 manifest | `e1da7b8ef04b65b1ece8e710720b57a8536841766fcf9de641f889b42eadd241` |
| Stage 6 row-map logical | `1ff9067c521ae93d28c300d7120a03c39681ce7830bf23b6619e2ca6129a4fe1` |
| Stage 6 logical dataset | `2f6379c0cd5dc9654c03895cae6fdd48f3a7af528158c33e44d2030c816640b6` |
| Stage 6 input binding | `6ba224d6d24c3631aae8aac69f4a362bb054f01d9e3d09327ec6b0fdd85a0e7d` |
| Stage 6 schema | `9c07b7a4c3f7a5c43ad457dcf6f7fe3fd746d54d82a731139905b30828b6c9ce` |

All individual Stage 8 relation/schema/occurrence fingerprints and transitive
Stage 7 identities are incorporated exactly from the
[accepted input table](STAGE09_OFFLINE_REFERENCE_EVIDENCE.md#exact-accepted-inputs),
not replaced by short hashes. The Stage 10 input object binds these anchors,
the Stage 9 anchors, exact manifests' file inventories/sizes/hashes, accepted
Benchmark V1 identity, split DEVELOPMENT, and this explicit read projection.
Manifest paths are resolved only within reviewed controlled anchors. No
directory scan chooses “latest.” Full readback validates the input versions,
schemas, logical/physical hashes, permissions and each stage's own publication
contract before hypotheses become publishable. Upstream acceptance is not
recomputed by opening unrelated upstream payloads.

The Stage 6 projection includes stable ID, both candidate slots, all four
representation-specific `stage04_lower_street_address_line_*` fields (native
suffix where appropriate), and Stage 5 candidate-lower/availability/count/mask.
Raw and clean siblings stay immutable and addressable through that row map;
they need not be copied/read to generate Q3/Q5. Validate exact Stage 8/6 stable-ID
totality, slots, field schema and Stage 5 reconstruction before using a line.
This implements the accepted **BOUNDARY_HANDOFF_SUFFICIENT** conclusion without
changing Stage 0–9 or duplicating the Stage 8 map.

## Source-occurrence query context

Define exactly one query context for each **present Stage 8 representation
occurrence**, keyed upstream by `(stable_source_row_id_v1, representation)`.
STANDARD and NATIVE are distinct roles, even when their Stage 6 candidate IDs
are equal. A source row therefore has zero, one or two contexts. Candidate
reuse across rows creates more contexts, never an eligibility vote or veto.

The context joins that occurrence to its exact Stage 6 candidate, its own
Stage 8 source geography, its own representation-specific Stage 6 lower lines
and masks, shared candidate parser evidence, and Stage 9 evidence applicable
to **that source row and candidate**. Accepted Stage 8 parsing is candidate-grain;
no occurrence-specific parse is invented. Its structural/country applicability
summaries cannot establish the new context's semantic trust or country validity.

`query_context_id` binds the immutable upstream snapshot identities and that
minimal occurrence key; candidate ID and all context values are functionally
determined by those references. The two output relations carry the existing
source ID/representation/candidate FKs inline. There is no third context table,
new authoritative source map, or pre-generation grouping across occurrences.
The [data contract](STAGE10_DATA_CONTRACT.md) gives the exact identity formula,
read projection and bijection invariants. Changing the bound source snapshot
changes the context identity; unrelated provider/display fields are not
additional hash arguments. Country and boundaries cannot change under a frozen
occurrence without failing the input hash/FK checks.

**Ordinary country context is row-local.** Read that row's exact
`stage03_clean_country_iso_code` through Stage 8. It must contain exactly two
ASCII letters; ASCII-uppercase them for the boundary, without trimming,
territory mapping or aliases. Reuse its SOURCE_ROW S9.Q01 ISO SUPPORTED witness
for the same candidate/source field/code and frozen positive code-namespace
capability. This is recognized source-code context, not country-resolution or
geographic truth. Missing/malformed/unrecognized country constrains only this
context. A missing expected evidence row/hash mismatch is fatal, not abstention.

Do not require candidate-wide COUNTRY_UNANIMOUS_VALID or Stage 9 country
assessment success. All 51,779 accepted country assessments are unresolved
under the frozen subdivision-witness rule; ordinary generation still proceeds
with valid source-row codes. S9.Q01 code recognition is country-independent.
Stage 9's other country-dependent checks may remain NOT_EVALUABLE because its
accepted evaluator used candidate-wide prerequisites. Preserve that limitation;
do not recompute Stage 9 or borrow another row's support. It can leave optional
Q4 fields unsupported, but cannot block Q1/Q2/Q3/Q5/Q6 with valid local inputs.
NOT_FOUND/NOT_EVALUABLE provide no negative geographic evidence.

No cross-row country, geography, boundary or representation unanimity is used.
One context's malformed country, unavailable structure or field contradiction
never changes another context's eligibility. Q1/Q2 retain their complete
source-derived line bodies regardless of individual structured-field conflicts.

## Architecture and engineering-ceiling proof

Generate the complete eligible Q1–Q6 static catalog per context, converge exact
complete intents **within that context**, and retain every family membership.
There are six auditable family decisions per context, not six guaranteed queries.
Q7 is globally `DEFERRED_RESULT_DEPENDENT_DIAGNOSTIC`: zero per-context rows,
zero pseudo-hypotheses, zero preallocated request/hypothesis IDs. Any later
activation belongs to a separate frozen result-dependent contract and workload.

The exact reachable maximum is derived from the frozen eligibility rules:

| Context / candidate script | Full baseline | Q3 | Q4 | Q5 | Q6 | Maximum |
|---|---:|---:|---:|---:|---:|---:|
| STANDARD, Latin/Common/Inherited | Q1 = 1; Q2 = 0 | 1 | 1 | 1 | 0 | 4 |
| NATIVE, Latin/Common/Inherited | Q2 = 1; Q1 = 0 | 1 | 1 | 1 | 0 | 4 |
| NATIVE, eligible Greek or Cyrillic | Q2 = 1; Q1 = 0 | 1 | 1 | 0 | 1 | 4 |
| Other supported-country contexts | Exactly one role baseline | <=1 | <=1 | 0 | 0 | <=3 |

Q1/Q2 are mutually exclusive **inside one occurrence context**. Q5 requires
all candidate code points to be Latin/Common/Inherited. Q6 requires a Greek or
Cyrillic letter; Q5 and Q6 therefore cannot both be eligible. Every family is
single-valued; no subsets, permutations, recursive transformations or parser
component repetitions create additional constructions. Thus
`H(context) <= 1 + 1 + 1 + max(Q5,Q6) = 4`, before any duplicate collapse.
The last table row also covers STANDARD non-Latin contexts (Q6 is native-only).

Four is reachable, not merely an upper estimate. An invented Latin context
with lower lines `['12 example road', 'unit 5', '', '']`, valid row country,
positive source-locality evidence and a uniquely aligned `unit` component
produces four distinct intents: full text; LF boundary text; structured address
plus locality; and the stripped first line. The structured endpoint distinguishes
Q4, and the other three texts differ exactly. A source row can have two such
valid contexts with different invented road/unit strings, so eight hypotheses
are reachable per source row. These are symbolic synthetic witnesses, not
claims that accepted DEVELOPMENT contains such rows.

**ENGINEERING SAFETY CEILING = 4 distinct hypotheses/context and 8/source row.**
It detects implementation/query-explosion bugs and suppresses no eligible
family. Exceeding it fails publication with a defect; it is not a truncation
rule. There is **no fixed global per-candidate cap**: if a candidate has `m`
occurrences, its safe bound is `4m`. Report that context multiplicity instead
of making one occurrence spend another's budget. Population bounds are
`contexts <= 2 × source_rows`, `hypotheses <= 4 × contexts <= 8 × source_rows`,
`family_decisions = 6 × contexts`. Equal STANDARD/NATIVE values still have two
contexts; global request deduplication is later Stage 11 work.

## Scientific operating budget

The operating budget is **UNSELECTED**. The first authorized DEVELOPMENT run
must use `ALL_ELIGIBLE_CATALOG`: materialize every eligible Q1–Q6 hypothesis up
to the proven engineering bound, with no budget suppression and no policy
tuning based on protected individual examples during the run. Nothing in this
catalog authorizes requests or starts Stage 11.

The family accounting order is Q1, Q2, Q3, Q4, Q5, Q6; the context's available
full baseline is rank 1. Other intents rank by earliest contributing family,
then unsigned intent fingerprint. Convergence precedes any future budget.
A later reviewed per-context operating B may lie in [1,4], never a global
candidate budget. A revised policy may select a prefix for a new immutable
plan, retaining every suppressed payload/membership in its catalog. Such an
INITIAL_PLAN requires explicit policy/version/authorization; v1's first run
cannot select B or emit QUERY_BUDGET_SUPPRESSION. The engineering cap cannot
stand in for scientific calibration. Any relaxation of the mutually exclusive
family rules requires rederiving both ceilings before approval.

Stage 10 can immediately measure structural coverage, context multiplicity,
convergence, unique intent counts and cost proxies. True family value/recall
requires later Stage 12/13 outcomes and independent DEVELOPMENT adjudication.
Use the [calibration procedure](STAGE10_DEVELOPMENT_EVALUATION.md); never call
structural coverage geocoding correctness. Q7 would require a separately
reviewed combined workload bound, not a reserved Stage 10 slot.

There is no Stage 10 byte truncation or giant-address skip. Stage 11 later
freezes actual encoded-request limits and retains explicit unschedulable
outcomes/map-back; a service byte cap is not guessed in this design.

## Scale, reproducibility and privacy

Design for 141,048,582 production rows, while only future separately authorized
Benchmark V1 DEVELOPMENT can run next. Use pinned PyArrow for schemas,
`large_string`/Parquet and byte-bounded streaming; DuckDB for disk-backed joins,
grouping, external ordering, integrity and aggregates. No pandas production
path. Polars/Spark add no demonstrated v1 requirement.

Externally join contexts to candidate/component/evidence streams using exact
keys. Reuse candidate-only text/script/parser-alignment work as a bounded,
content-verified cache without coalescing context eligibility. Filter source
reference evidence on `(candidate_id, stable_source_row_id_v1)` before gating.
Process contexts incrementally; never collect all occurrences of a popular
candidate or explode each occurrence against the full global reference pack.
Source lines have four slots; at most four intent payloads per context may be
spooled. Selector certificates stream complete evidence and share repeated
witness-set traversal. Private spill/checkpoint files are operational state,
not extra scientific relations. No population Python dict/list or list_agg.

The accepted maximum is 25,920,495 code points and 881,338 parser components;
resource limits must accommodate these or fail without semantic abstention.
Bound bytes, not only rows. ICU processes a whole logical string or a proven
context-preserving streaming equivalent; arbitrary chunk transforms are banned.
Production capacity is not claimed from DEVELOPMENT extrapolation.

Shard by `query_context_id` prefix with configured prefix width and canonical
external merge; candidate-only caches may use their own prefix partitions.
Batches, shards, workers and Parquet layout cannot change scientific content.
Checkpoints bind exact inputs/science/transformation assets and context interval,
schema/count/logical/physical hashes. Resume may reuse only complete immutable
validated chunks into a new authorized attempt; no overwrite or stale takeover.
Submit the reviewed job once and wait; pending is not grounds for duplication.

Runtime proposal retains Python 3.14.3 / Unicode 16.0.0, PyArrow 25.0.0,
DuckDB 1.5.5 and adds the tightly scoped ICU asset in Q6. Exact runtime/source/
binary/data locks must be reviewed before materialization. Missing pins or
different versions fail closed. Operational Git/runtime/SLURM provenance is
separate from logical fingerprints and scientific hypothesis identity.

Future protected DEVELOPMENT/heavy execution invokes the shared guard **before
input access**, with `SAFE_EXECUTION_SITE=goethe-nhr` and nonempty `SLURM_JOB_ID`.
Goethe login nodes orchestrate only; the Mac uses synthetic tests/docs only.
Code arrives through Git at an exact clean pushed SHA. No dynamic pull,
`/scratch`, shared Conda-base modification or `/work/footprint/public` writes.
Controlled directories/files are 0700/0600. Row IDs, candidate/query hashes,
strings, evidence selectors and errors derived from rows remain protected.
Git and prompts get synthetic fixtures and allowlisted aggregates only.

## Publication decision

Intended namespace:
`/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage10/development/<unique-run-key>`.
This is a new Stage 10 sibling under the same documented institutional `/work`
anchor as Stage 9. The intended filesystem is the same PanFS deployment;
**actual Stage 10 path/filesystem compatibility was not probed or verified in
this design session**. Stage 9's direct capability evidence is job `1771149`.

The owner approves reuse of the accepted Stage 9 publication **state machine
and primitive requirements unchanged**, conditional on future pre-input verification of the
configured anchor, approved `/work` alias resolution, private no-follow
topology, same filesystem assumptions, exclusive-create collision behavior,
zero-byte seal semantics, file/directory fsync and full prepared/committed reopen.
No new filesystem diagnostic is required merely because the stage number changed.
Implementation preflight verifies the controlled root, expected PanFS mount/
topology, the same exclusive-create mechanism and private permissions. A different
filesystem, mount or materially different topology must STOP for owner review;
do not assume earlier evidence applies or add a fallback. No probe occurs now.

Exclusive permanent reservation → immutable validated artifact → registration
→ exclusive `_COMMITTED` → durability/full reopen. Existing incomplete keys
are preserved; no stale takeover. Adoption requires externally pinned exact
manifest and bindings, not logical equality alone, directory existence or
historical cross-job inode equality. Preserve uncertain post-seal outcomes for
exact recovery; presentation failure cannot undo a committed result.

Stage 9's current implementation is stage-specific. Stage 10 needs only a
reviewed adapter/registration schema, `stage10_publication_record_v1`, binding
namespace `STAGE10_DEVELOPMENT_QUERY_PLAN`, Stage 10 manifest/logical/contract/
profile/schema/executable/inventory and complete `stage10_input_binding_sha256`.
It must not mislabel Stage 10 inputs as Stage 9's `stage08_input_sha256` or
weaken accepted Stage 9 validators to generalize them. This is a record adapter,
not a publication-protocol redesign; Stage 8 publication remains unchanged.
Final implementation approval and later preflight confirmation remain separate gates.

NEXT: FINAL OWNER APPROVAL TO IMPLEMENT STAGE 10
