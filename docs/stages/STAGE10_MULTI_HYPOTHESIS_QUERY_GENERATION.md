# Stage 10 — bounded multi-hypothesis query generation

## Status and authority

**DESIGN READY FOR OWNER REVIEW — NOT APPROVED, NOT IMPLEMENTED, NOT EXECUTED.**
This is the 2026-09-14 fresh DEVELOPMENT design session authorized by the owner.
The package freezes a review candidate, not accepted science or permission to
implement. All proposed policies below require the decisions in the
[review ledger](STAGE10_DESIGN_REVIEW.md). Stop after owner review preparation.

Normative package:

- this scientific contract, inputs, budget, execution and publication boundary;
- [family definitions](STAGE10_QUERY_FAMILIES.md), including exact gates;
- [data contract](STAGE10_DATA_CONTRACT.md), identities and Stage 11 handoff;
- [evaluation plan](STAGE10_DEVELOPMENT_EVALUATION.md); and
- [complete design review and owner decisions](STAGE10_DESIGN_REVIEW.md).

Proposed identifiers are `stage10_multi_hypothesis_query_contract_v1`,
`stage10_multi_hypothesis_query_profile_v1`,
`stage10_multi_hypothesis_query_schema_v1`,
`stage10_query_intent_v1`, `stage10_query_logical_encoding_v1`,
`stage10_query_validation_v1`, and `stage10_query_manifest_v1`.
The [design freeze inventory](../scientific_assets/stage10_design_freeze_v1.json)
hashes the review documents. These are design-byte hashes; executable contract,
Arrow schema, runtime-asset and output fingerprints do not yet exist. No future
fingerprint is invented or described as verified.

## Baseline gate and evidence limits

Before design, `git fetch --prune origin` succeeded. The tree was clean and
HEAD = main = origin/main = `23cfb85f428b00301d68591ea5992763abf9ad88`.
Annotated tag `stage09-offline-reference-evidence-v1` exists and peels to that
same owner-acceptance commit. D047/D060 and accepted reports record
`STAGE_8_ACCEPTED`, `STAGE_9_ACCEPTED`, Stage 10 NOT STARTED, HOLDOUT SEALED,
and production/Pelias untouched. No unexpected baseline divergence was found.

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

## Candidate context and map-back safety

Stage 6 identity contains text only. Equal text can occur in different rows,
countries, representations or line layouts. A candidate-wide hypothesis must
not borrow one occurrence's context and attach it to all others.

Proposed v1 uses **unanimity and abstention**, without occurrence-specific
hypotheses or context expansion:

- ordinary Q1–Q6 require accepted `COUNTRY_UNANIMOUS_VALID` and its non-null
  trusted ISO alpha-2 code; that code is the explicit country boundary;
- incomplete/invalid/conflicting source-country provenance yields no ordinary
  hypothesis for that candidate; never select majority/first/parser country;
- source geography used by Q4 must be exactly equal and nonempty at the Stage 3
  clean level across all distinct source rows mapped to the candidate;
- Q3/Q5 require one exact four-slot lowercase line vector, including empty
  positions, across **all** its STANDARD and NATIVE occurrences; and
- source-role Stage 9 prerequisites must pass for every relevant distinct
  source row. Two equal representation slots on one row are one source witness.

These restrictions are scientifically consequential proposals, not claims
that divergent candidates are invalid. Measure their lost coverage explicitly.
Any later occurrence-scoped extension requires a reviewed version, bounded
selection and explicit applicability map; it cannot be a hidden implementation
optimization. Query hypotheses may serve all candidate occurrences after these
gates. Family credit remains limited to its recorded representation provenance.

Stage 9 `COUNTRY_UNRESOLVED` is not this source-provenance gate: all 51,779
accepted country assessments were unresolved because there were zero qualifying
full subdivision-code witnesses. **No Q1–Q6 gate requires Stage 9 country
support.** Strong source context is retained even when a scoped contradiction
exists; Q4 may omit a contradicted field, and Q7 remains deferred.

## Architecture and budgets

Choose **B: deterministic initial plan plus an explicitly disabled/deferred
diagnostic phase**. Materialize all eligible Q1–Q6 representations for offline
accounting, collapse exact intents, and mark only the operating-budget prefix
as selected. Materialization does not authorize their execution. Q7 emits no
query payload and no activation program in v1.

Seven fixed family decisions per candidate, at most one construction per family,
no permutations, optional-field subsets, parser-duplicate expansion,
transliteration chains, source-context products or recursive transformations.
Order is Q1, Q2, Q3, Q4, Q5, Q6; Q7 has no initial priority. Q1/Q2 use identical
candidate bytes and country when both apply, so they necessarily converge.

**Proposed engineering ceiling: five distinct generated hypotheses per exact
candidate; ten per source row with two different candidates.** Seven family
decisions are bookkeeping, not seven requests. The ceiling follows from one
full baseline plus Q3/Q4/Q5/Q6, each single-valued. At most six eligible family
members may converge into those five. Row ceilings count the union of distinct
candidate hypotheses; equal STANDARD/NATIVE slots do not double it. No source
row is dropped, including rows with no candidate or no hypothesis.

Let `B` be the scientific operating budget, an integer in `[1,5]`. It is
**UNSELECTED**, with no implicit default. A future separately approved offline
calibration run may use `CATALOG_ONLY`: retain the complete bounded catalog but
export no Stage 11 selected workload. `INITIAL_PLAN` requires a reviewed numeric
B and budget-policy fingerprint. The first full baseline always occupies rank 1.
Eligible alternate intents rank by their earliest contributing family; ties
use unsigned representation-fingerprint bytes. Collapse precedes selection.
Select ranks `<= B`; preserve all other payloads and family lineage with
`QUERY_BUDGET_SUPPRESSION`. Duplicates consume no additional budget. Families
converging to a selected baseline keep credit even if their nominal family
order is beyond B. Candidate and row ceilings are hard validation invariants;
an algorithm producing more than five fails publication, rather than silently
truncating. Scientific B suppression is distinct from this defect.

There is no Stage 10 byte-based truncation or giant-address skip. Stage 11 must
later validate actual encoded request byte limits; oversize requests are
explicitly unschedulable with all source/hypothesis lineage retained. A numeric
service byte cap is not invented before its request/deployment contract exists.

Select B and any revised family order on DEVELOPMENT using the
[marginal-utility and ablation procedure](STAGE10_DEVELOPMENT_EVALUATION.md).
Offline coverage/cost can select a provisional trial workload, not an optimal
accuracy budget. Later Stage 12/13 evidence is necessary for recall utility.
Calibration creates a new immutable policy/plan; it never mutates accepted
artifacts or tunes an execution in flight. Q7 would need a separate ceiling and
activation contract before any enabled profile, including a combined row cap.

## Scale, reproducibility and privacy

Design for 141,048,582 production rows, while only future separately authorized
Benchmark V1 DEVELOPMENT can run next. Use pinned PyArrow for schemas,
`large_string`/Parquet and byte-bounded streaming; DuckDB for disk-backed joins,
grouping, external ordering, integrity and aggregates. No pandas production
path. Polars/Spark add no demonstrated v1 requirement.

Read candidate/component/evidence streams once in external candidate order.
Reduce source unanimity with streaming equality/min/max and counts, never
population dictionaries or `list_agg` of occurrences/components/witnesses.
Consume Stage 9 witness sets as ordered joins, not candidate × global reference
searches. Selected lineage sets use reproducible selectors and stream digests,
not unbounded lists in a hypothesis row. At most five payloads per candidate
may be spooled; giant payloads use controlled temporary files/Arrow slices.
The accepted maximum is 25,920,495 code points and 881,338 parser components;
resource limits must accommodate these or fail the run without scientific
abstention. Bound bytes, not just row counts. ICU transforms must operate as
whole logical strings with a reviewed size/resource strategy; independently
transliterating arbitrary chunks is prohibited.

Shards use candidate-ID prefixes with configured prefix width; external merge
restores canonical global order. Shard width, batches, compression and worker
count cannot change logical content. Worker parallelism is offline only.
Checkpoints bind exact input/science/runtime assets, candidate interval,
schema/count/logical and physical hashes. Completed immutable chunks may be
reused after full validation; resume never overwrites an incomplete attempt.
Only one reviewed job is submitted; pending is not grounds for duplication.
New-key restart or recovery requires the applicable execution authorization.

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

Propose reuse of the accepted Stage 9 publication **state machine and primitive
requirements unchanged**, conditional on future pre-input verification of the
configured anchor, approved `/work` alias resolution, private no-follow
topology, same filesystem assumptions, exclusive-create collision behavior,
zero-byte seal semantics, file/directory fsync and full prepared/committed reopen.
No probe is authorized now. Failed prerequisites stop; no rename fallback.

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
Owner approval and later environment confirmation remain separate gates.

NEXT: OWNER REVIEW OF STAGE 10 DESIGN
