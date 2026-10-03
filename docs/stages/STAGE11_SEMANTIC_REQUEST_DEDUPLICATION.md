# Stage 11 — complete semantic request deduplication design

## Status and authority

**OWNER REVIEW INCORPORATED — READY TO FREEZE; NOT IMPLEMENTED, NOT EXECUTED.**
After reviewing design `63f070643a2f877536cd2777ec381a49498553ed`, the owner
approved the architecture in principle, explicitly approved architecture A,
and authorized final clarification, one bounded design review, commit and
branch push. All sixteen owner directions are incorporated; unresolved owner
design decisions = **0**. Final freeze/merge of the exact revised design is
the next owner action, not performed here. Stage 10 is accepted/frozen.
No implementation, protected read, SLURM, HOLDOUT, production, Pelias,
Stage 12 start or scientific tuning is authorized. No acceptance tag is created.

The complete final design package is:

- this scope, input, scale, restart and publication contract;
- [request/data/identity contract](STAGE11_DATA_CONTRACT.md);
- [DEVELOPMENT validation and report plan](STAGE11_DEVELOPMENT_EVALUATION.md);
- [complete defect ledger and owner decisions](STAGE11_DESIGN_REVIEW.md).

Final v1 names are `stage11_semantic_request_contract_v1`,
`stage11_semantic_request_profile_v1`, `stage11_semantic_request_schema_v1`,
`stage11_semantic_request_encoding_v1`, `stage11_semantic_request_validation_v1`,
`stage11_semantic_request_manifest_v1`, `stage11_semantic_request_summary_v1`
and `stage11_publication_record_v1`. These are specifications, not installed
assets or executable fingerprints. Final owner freeze/merge must identify an
exact design Git SHA; later implementation must bind that package's bytes.
Architecture approval does not grant implementation or execution authority.

The final core has **19 fields**. The
[single exact field list](STAGE11_DATA_CONTRACT.md#exact-typed-core-and-field-order)
removes per-core `retrieval_policy_binding` and `header_policy`, defines
`language_policy=NO_REQUEST_LANGUAGE_OVERRIDE`, preserves explicit omitted
layer/source policies, fixes `spatial_policy=NONE`, and retains the singleton
`additional_parameter_policy=REJECT_UNLISTED` with no parameter bag.

## Baseline verification and evidence limits

Owner-review continuation: a fresh `git fetch --prune origin` verified clean
design HEAD = origin/design branch = `63f070643a2f877536cd2777ec381a49498553ed`,
with main = origin/main still at the accepted baseline below and unchanged
local/remote Stage 10 acceptance tag. The following original baseline evidence
remains valid; the previous draft is preserved as the new commit's ancestor.

`git fetch --prune origin` succeeded before design. The working tree was clean;
HEAD = main = origin/main = **`d027da6c504a8fe864a7821a3e786c390ec05add`**.
Local and remote annotated tag `stage10-multi-hypothesis-query-generation-v1`
have object `819fe31c684113ee3f0c57c846ac75501bb43aca` and peel to that exact
main. Executable, reporting and final review commits are ancestors of main.
The branch starts at this accepted baseline, without rewriting history.

[Stage 8 acceptance](../../reports/development/stage08.md),
[Stage 9 acceptance](../../reports/development/stage09.md#owner-acceptance-and-freeze--2026-09-14),
[Stage 10 acceptance](../../reports/development/stage10.md), and D047/D060/D085
establish accepted/frozen DEVELOPMENT status. Tracked-file and source searches
found no Stage 11 implementation, client, launcher, schema or scientific
artifact; only prospective descriptions. The repository has no deployed SAFE
Pelias request/configuration contract to import as already proven.

Verification used Git, code, committed contracts and sanitized records. The
accepted records say HOLDOUT SEALED, production Stage 2 NOT STARTED and Pelias
untouched. No protected artifact, storage seal, production directory or remote
scheduler was inspected. Thus this is verification of recorded authority and
this session's non-access, not an attestation about unobserved external activity.
Public upstream documentation/source was read without any protected input;
no Pelias endpoint or storage was probed.

| Stage 10 binding | Accepted value |
|---|---|
| Scientific executable | `cf9e0fe4c12eb85f78051904c636ad084d87a541` |
| Authoritative reporting | `b29b230dece88404712105fc485c41411e12ba5d` |
| Final independent review evidence | `c9c8813b53bb6603c3e3e159b04e0729c4240b40` |
| Review merge | `baa9acad5e2f9cd334cba7c4d4923dbc035b92c5` |
| DEVELOPMENT job | `1785683` |
| Publication key | `stage10_development_20260928T081247Z_cf9e0fe4c12e` |
| Manifest SHA-256 | `558298d7260199cc24f994d7480def9ad268aca057347f86ca41fad675a5a860` |
| Logical dataset SHA-256 | `4c4e4e6a63f565f6b3ce97f54c74fcd817cbd79922189fdc07ad3e3d76205c1a` |
| `query_hypothesis` SHA-256 | `c61ba899dbe4f714e2879995261b7d3a943e3b830ca69b4656e2d286230982e1` |
| Decision/provenance SHA-256 | `2c915039f6b8653fbfbd2acd3629cb7d1efd86190e3cb636c69542750c695420` |
| Contract SHA-256 | `be0a865f5217a82497cc3324fa11557df06441ec67e08f1cd2014cbf0d9b246b` |
| Profile SHA-256 | `6c42e00e7550edac184d6f8ba46e421e84f82a2df9b9234049ed3fca59a6798d` |
| Schema bundle SHA-256 | `659a98157951876b14078d0306b94f8f1e3e151fc92a7352243b3fce1b715070` |
| Population | 35,000 source rows; 69,747 contexts; 142,677 hypotheses |
| Family decisions | 418,482; Q1–Q6; Q7 absent/deferred |
| Operating budget | **UNSELECTED**; `ALL_ELIGIBLE_CATALOG` |

Accepted artifact (a binding, not a path opened in this session):
`/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage10/development/stage10_development_20260928T081247Z_cf9e0fe4c12e`.
Stage 8/9 and transitive input identities remain those in this exact Stage 10
manifest and its acceptance record, not a newly discovered upstream snapshot.

## Scientific purpose and exact scope

Convert **all** accepted Stage 10 hypotheses into typed semantic search cores
and globally deduplicate exactly equal cores. Retain every hypothesis membership.
This is operational workload reduction and representation convergence only.
It selects no winning address, query family, hypothesis, rank, correctness,
coordinates, usability, granularity, scientific threshold or family budget.
It performs no reference lookup, parsing, correction, fuzzy or similarity match.

Global means across all query contexts, source rows, STANDARD/NATIVE roles,
families and Stage 6 candidates **within the complete bound input catalog**.
Never partition equivalence by these lineage attributes. Split-specific
artifacts remain separate: identical cores may have the same ID in another
separately authorized snapshot, but no cross-split scan or membership union is
authorized. HOLDOUT remains sealed.

Stage 10 already converged intents only within a context. Stage 11 preserves
that context and every hypothesis ID through a foreign-key map; it does not
regenerate Stage 10, change its decisions or retroactively suppress families.
If 50 hypotheses share a core there are still 50 map rows. Multiple families
supporting one upstream hypothesis remain distinct upstream family decisions.
Neither count is independent evidence that the address is correct.

## TOP-N decision and the prospective handoff amendment

**OWNER-APPROVED architecture A: NON-EXECUTABLE SEMANTIC QUERY CORE.**
Stage 11 fixes the complete meaning of the *search input and its request-side
constraints*, independent of how many results an execution asks to observe.
`semantic_request` is explicitly a **non-executable semantic core**, not a
complete HTTP request and not evidence of service schedulability.

Result limit belongs to Stage 12 retrieval policy because it controls observation
depth and the returned set for the same search question. It certainly affects
results; excluding it from the core does **not** assert size invariance, stable
rankings, or that size=10 is a prefix extension of size=1. Requests at different
sizes must have different execution identities and cannot share a response
cache merely because their Stage 11 IDs agree. Stage 12 must evaluate these
issues with authorized DEVELOPMENT evidence, including recall@1/3/5/10 or an
approved equivalent. Those values are evaluation examples, not selected N.

There is no Stage 11 numeric `size`, implicit server limit or default N. Every
future executable request requires a concrete Stage 12 retrieval policy with
an explicitly transmitted positive integer result limit, plus retention and
execution bindings. Until then, executable workload status is
`NOT_MATERIALIZED_RETRIEVAL_POLICY_REQUIRED`. Stage 11 can publish and validate
a complete offline core catalog without claiming any executable requests.
Following the owner's preferred option A, remove the draft's redundant
retrieval sentinel: neither `retrieval_policy_binding` nor a
replacement is a core field. The contract-level Stage 12 requirement is enough.
N=1/3/5/10 leave a given core's ID unchanged; distinct retrieval policies have
distinct execution identities. No N is selected here.

This **prospectively refines** the frozen Stage 10
[complete-request handoff](STAGE10_DATA_CONTRACT.md#stage-11-complete-request-boundary):
its requirement to resolve size in Stage 11 becomes a required Stage 12 binding.
The old wording, artifacts, intent slot and scientific history remain unchanged.
The owner has approved this explicit boundary. Implementation remains separately
unauthorized. Repository inspection found no direct interface contradiction;
no actual SAFE deployment or live API conformance is claimed.
This design neither activates the `size=1` preference nor waives the current
Stage 19 acceptance/exact-workload gate. Before Stage 12 execution, the owner
must separately reconcile that gate with the compact architecture and approve
the empirical retrieval plan. **Stage 12 NOT STARTED.**

## Authoritative input and permitted future read projection

Primary scientific input is accepted Stage 10 **`query_hypothesis`**. The
actual upstream PK is **`hypothesis_id`**; “query_hypothesis_id” is descriptive
terminology, not a new upstream column. Its exact `intent` is the sole source
of query strings, structured values, endpoint/mode and country boundary.
The frozen `SAFE_PELIAS_COMMON_RETRIEVAL_V1` slot maps uniformly to this Stage 11
profile; the contract requires future Stage 12 retrieval binding without a
per-core retrieval field. No family-specific
or context-specific runtime override is legal.

Future guarded validation reads the full accepted hypothesis relation to verify
its declared hash, schema, unique IDs, context/source/candidate FKs, selection
status and exact intent rules. Diagnostics additionally project only
`query_context_id`, `hypothesis_id`, `family`, `eligibility_state`,
`membership_state`, and source/role/candidate FKs from Stage 10
`query_family_decision`. Complete upstream file-byte integrity remains checked;
this projection does not authorize reinterpreting its protected certificates.
Use the accepted manifest/summary to reconcile zero-hypothesis contexts and
35,000-row population; there is no new Stage 8/10 source map.

The input binding, `stage11_input_binding_v1`, records the exact accepted
Stage 10 manifest, relation/logical/contract/profile/schema hashes, publication
key, acceptance Git/tag, Benchmark V1 fingerprint and DEVELOPMENT split; exact
manifest file paths, lengths/hashes and this closed read projection; transitive
Stage 8/9 identities; and the approved Stage 11 design/profile assets. Unknown
keys/versions or changed expectations fail closed. Paths must stay below the
reviewed controlled anchor; no “latest” discovery, glob-based input population,
new raw-address read, Stage 6 payload or refreshed reference is permitted.

Stage 10 lineage is immutable and already accepted. Stage 11 verifies its own
FK joins and upstream binding, without rerunning Stage 10 generation or opening
Stage 8 source payloads. Complete source identity, file/logical-record lineage,
and absent-context outcomes remain accessible through the bound accepted chain.

## Approved scale and deterministic processing design

Use pinned PyArrow/Parquet for the two protected relations and disk-backed
DuckDB for joins, external sorting, integrity and aggregate diagnostics. No
pandas production path, population-sized Python dict/list, giant membership
list or pairwise matching. Polars adds no required v1 role. Exact runtime
versions and resource requests belong to later reviewed implementation assets;
no new performance claim or scientific budget is frozen here.

1. Stream verified input in byte-bounded batches. Validate and project each
   hypothesis to exactly one core, encode it, hash it, and spool its map edge.
   Source multiplicity is never a reason to skip, shorten or filter a core.
2. Route by the first `k` complete bytes of the **full** query semantic digest
   (`k` is a bound operational partition setting). Input partitions are merely
   processing units. Equal full IDs always reach the same global reduction.
3. Externally sort/group by full 32-byte ID. Compare complete canonical bytes
   within every group; equal bytes emit one core, unequal bytes abort. Stream
   memberships as rows, without `list_agg` or collecting popular groups.
4. Merge runs in unsigned full-ID order. Externally enforce map-PK uniqueness
   and exact full input set equality. Repartition independently by hypothesis
   ID when helpful for map checks; never truncate keys to prefixes.
5. Compute lineage diagnostics through external joins/distinct pairs. Full
   reopen recomputes core encodings/IDs and every hypothesis-to-core projection.
   IDs and logical fingerprints are invariant to order, workers, batch size,
   shard count, storage path and physical compression.

Work is O(total encoded bytes + external sorting), ordinarily O(N log N) sorting
and O(N) joins/grouping, with no O(N²) comparisons. Memory is bounded by byte
buffers and a finite number of decoded rows/largest value, not population or
group size. Large strings require explicit single-value memory accounting;
do not claim a fixed row batch is byte-bounded. Reuse exact bytes or stream
framed values where supported. If a value cannot fit the reviewed resource
envelope, fail the attempt without truncation or scientific suppression.
The accepted upstream giant-value history must inform future capacity tests.

## Split workspace, durable restart and failure model

Use Goethe `/local/$SLURM_JOB_ID` for future transient databases, external-sort runs,
spill and rebuildable caches; controlled PanFS for all authoritative checkpoint
payloads, seals, manifests, audit receipts and final relations. Paths/job IDs
never enter semantic IDs. No storage probe occurs in this design session.

After separate implementation/execution approval, pre-input guard requires
`SAFE_EXECUTION_SITE=goethe-nhr`, nonempty `SLURM_JOB_ID`, exact clean pushed Git
SHA, pinned runtime, private no-follow topology, expected filesystems, project
quota and local capacity. No protected compute on login nodes, `/scratch`,
public-tree writes, shared Conda-base changes or local execution bypass. Missing
local workspace/capacity fails; no silent PanFS-spill fallback. Operational
memory/time/storage limits require later resource evidence, not top-N tuning.

Durable checkpoint descriptors bind exact executable SHA, input/design/profile/
schema/encoding identities, partition plan, completed input key ranges/counts,
core/map logical hashes, physical inventories and upstream coverage. Complete
input-unit checkpoints preserve the intermediate payloads **and every edge**
needed to rebuild the global reduction after total local loss. Reduction-unit
checkpoints also bind the complete contributing input-unit inventory; a shard
is not final while contributors are incomplete. A global coverage certificate
proves no overlap/gap and exactly one reduction of every complete partition.

Copy from local to fresh exclusive PanFS files, then fsync, hash, reopen and
seal complete checkpoint units. A cross-filesystem rename is never publication.
Durable descriptors cannot reference indispensable local bytes. Future resume
adopts only complete immutable units at the same exact executable and bindings
into a new authorized attempt. Partial units/failure evidence remain preserved;
no takeover, overwritten seals, cross-SHA adoption or silent binding repair.
Recovered final relations must match a fresh logical replay exactly.

Allocate durable phase/failure receipt space before work; preserve the first
static error code even if reporting or quota handling also fails. Log only
allowlisted phases/counters, never raw exception messages, strings, IDs or SQL
bound values. A failed attempt produces no valid scientific partial catalog.
No automatic replacement job: submit an approved long job once and reuse its
immutable artifact after completion; pending is not grounds for duplication.

## Conditionally approved publication plan

The owner approves the accepted Stage 9/10 state machine **unchanged**, through
a separate Stage 11 adapter, conditional on later verification of the same controlled
PanFS assumptions. Intended root is
`/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage11/development/<unique-run-key>`.
The intended sibling/root topology is a proposal, not measured capability.
Changed filesystem/topology stops for review; there is no fallback primitive.

Permanent exclusive reservation → durable immutable artifact and manifest →
full prepared validation → Stage 11 registration → atomic zero-byte
`O_CREAT|O_EXCL|O_NOFOLLOW` `_COMMITTED` → durability and full committed reopen,
with final same-invocation ownership checks. Directory, manifest, registration,
checkpoint seal or a successful log alone is never publication. Accepted Stage
8 publication semantics are unchanged.

`stage11_publication_record_v1` uses kind
**`STAGE11_DEVELOPMENT_SEMANTIC_REQUEST_CATALOG`** and input key
**`stage11_input_binding_sha256`**. It binds run key/namespace, exact manifest,
logical dataset, contract/profile/schema/encoding, approved design identity,
executable/runtime, inventories, counts and full input binding. Reuse the
accepted portable registration hash framing `SAFE:publication-commit:v2`
through this adapter, never Stage 9/10 field names with Stage 11 data.

Complete independent reopening checks both relations, totality, collision
guards, diagnostics and all hashes from PanFS with `/local` unavailable. The
manifest binds the canonical sanitized summary but the summary excludes its
own/dataset/manifest hashes and operational measurements, avoiding cycles.
Physical hashes and execution provenance are manifest-bound separately from
storage-independent logical content. The artifact is a candidate, not owner
acceptance or an executable Pelias workload.

Preserve incomplete reservations permanently. Exact-existing adoption requires
externally pinned manifest/registration/bindings plus full validation, never
directory existence, logical equality alone or historical cross-job inode
equality. Uncertain post-seal outcomes require bounded reconciliation; otherwise
report unverified failure and preserve the tree. Presentation failure cannot
undo a verified commit or manufacture one. Historical failed attempts remain.

## Privacy, freeze and stop

All semantic payloads, structured fields, map rows, row-level request hashes,
and attached error details are protected. Only controlled Goethe artifacts may
hold future DEVELOPMENT output: directories 0700, files 0600, including spill,
checkpoints and diagnostics. No protected examples in Git, terminal, LLM
context, public URLs or external services. Portable reports contain allowlisted
aggregate counts and artifact-level identities only; credentials remain runtime
only and never enter identity, logs or committed files.

Before any final HOLDOUT evaluation, freeze the approved schema, exact encoding,
ID domain, endpoint/mode, country, policy/default/list rules, global equivalence,
map-back, Stage 12 boundary and publication protocol at an immutable design/
implementation revision. Freeze Stage 12 retrieval and execution policy before
HOLDOUT too; this design selects neither. HOLDOUT is not opened now.

The [review ledger](STAGE11_DESIGN_REVIEW.md) records all sixteen owner directions,
the complete 48-item design ledger and final 14-item critical review, with zero
unresolved design defects or owner decisions. Final freeze/merge is pending;
implementation conformance and controlled evaluation remain future evidence.
Stage 0–10 science, code, frozen records and artifacts are unchanged.

**NEXT: OWNER FREEZE/MERGE OF STAGE 11 DESIGN**
