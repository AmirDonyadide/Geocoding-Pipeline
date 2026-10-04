# Stage 11 implementation and authorized DEVELOPMENT execution

## Authority and unchanged baseline

The owner authorized implementation of the already frozen Stage 11 design,
synthetic validation, an exact pushed executable, and **one** complete DEVELOPMENT
candidate. The 2026-10-04 continuation directs this session to proceed. Stage 11
is **not owner accepted**. No Stage 12, HOLDOUT, production processing, Pelias,
operating-budget selection, or result-depth selection is authorized.

Fetch and clean-tree checks establish main = origin/main =
`125b3684a000ea79523f77049ae1a290b0da8109`. The annotated design tag
`stage11-semantic-request-deduplication-design-v1` peels to that commit; its tree
equals reviewed `ac96b033e2ba7201fbb99ea38cd363d13410c7c4`. Implementation uses
`impl/stage11-semantic-request-deduplication`; no integration is required before
the exact pushed branch executable runs. Main and Stage 0–10 scientific files
remain unchanged. The four normative design documents remain byte-identical.

The initial precheck stopped after observing old production Stage 1 jobs
1759120/1759121, submitted 2026-08-26, still dependency-blocked with zero runtime.
The owner's subsequent `continue` was interpreted explicitly in this session
as direction to proceed with Stage 11 while leaving those jobs untouched. No
cancellation, modification, resubmission, production payload access, or change
to accepted production history occurred.

The exact accepted Stage 10 artifact and 0600 zero-byte `_COMMITTED` were checked
using lightweight remote shell metadata. Its manifest still hashes to
`558298d7260199cc24f994d7480def9ad268aca057347f86ca41fad675a5a860`.
The accepted query-hypothesis fingerprint is
`c61ba899dbe4f714e2879995261b7d3a943e3b830ca69b4656e2d286230982e1`,
with 142,677 hypotheses. HOLDOUT's sealed status is established from accepted
authority and this session's non-access, without inspecting HOLDOUT storage.

## Machine-readable conformance

[Contract](../scientific_assets/stage11_semantic_request_contract_v1.json),
[profile](../scientific_assets/stage11_semantic_request_profile_v1.json),
[schema bundle](../scientific_assets/stage11_semantic_request_schema_v1.json),
the three descriptor assets and [input binding](../scientific_assets/stage11_input_binding_v1.json)
encode the frozen design. Both region and address-country are explicit constant
nulls; projection still copies and validates their upstream values, never repairs
them. The semantic profile contains only the frozen input policy, Stage 10 slot,
contract hash and exact core constants. Runtime/resources are operational assets.

| Binding | SHA-256 |
|---|---|
| Contract | `e049305cfc100a7a84de01d395b4eceae5195e0730f50c91923cd5970c05885c` |
| Profile | `e25952c294ce486eff4969eef0ff709d10de89b6cdaf7072140a272e49a940a4` |
| Schema bundle | `a5c918291cd29e1824dd54e6b4d43bd7090e2492a06be408592a1a36f2f4b528` |

The [authoritative serializer](../../src/safe_geocoding_pipeline/preprocessing/stages/s11_semantic_contract.py)
uses the exact 19 named fields, strict UTF-8, tagged values, unsigned 64-bit
big-endian framing, and `SAFE:stage11-query-semantic:v1` plus NUL. Full SHA-256
IDs exclude all lineage, storage, execution and Stage 12 values. Two independent
synthetic byte vectors fix the full encoding. Unsupported fields, types, defaults,
empty values, country/mode combinations and malformed framing fail closed.

Only `semantic_request(query_semantic_id, core)` and
`hypothesis_request_map(hypothesis_id, query_semantic_id)` are scientific relations.
No upstream source/context/family lineage is duplicated. The closed summary
contains integer counts and rational fractions, with country-bound/unbounded
counts rather than sparse country identities. It excludes operational metadata
and self/dataset/manifest hashes.

## Bounded processing, restart and publication

Stage 10 physical inventories and hypothesis logical identity are verified.
Decision payload access is restricted to the frozen lineage projection; no
certificates, Stage 8 source rows, Stage 6 payloads or reference packs are opened.
Identity/FK, six-family coverage, eligibility, first/convergent membership and
population checks precede generation. All accepted hypotheses participate.

Arrow reads decode one row at a time, bounding Python state by the largest
accepted scalar rather than population size. Writers flush on both estimated
bytes and row count. DuckDB memory is capped at 2 GB; external sort/spill and
rebuildable working state use the required job-local filesystem. Strings are
never shortened or skipped to fit a resource envelope. A resource error aborts.

Input units cover consecutive hypothesis-ID ranges (8,192 rows operationally),
retaining every edge and canonical payload. Reduction routes on one complete
digest byte and sorts by full unsigned digest, comparing full bytes inside
every group. It never collects a membership list. Reduction units bind the
complete input coverage inventory. Sealed units have exact executable, runtime,
input, design, contract/profile/schema/encoding and partition bindings, physical
hashes, coverage and logical payload hashes. Copies are exclusive, fsynced,
hashed and reopened before the unit seal. Partial units remain preserved and
are rebuilt only in a new authorized attempt. Resume cannot adopt cross-binding
or cross-executable state.

Scientific output is physically ordered by full semantic ID and hypothesis ID,
respectively. Logical digests sort by those keys and ignore file/shard order,
compression and execution layout. Canonical payload bytes are operational
checkpoint evidence, not an additional scientific relation.

The [Stage 11 adapter](../../src/safe_geocoding_pipeline/preprocessing/stages/s11_semantic_publication.py)
retains the accepted reservation → artifact/manifest → initial full validation →
registration → prepared full validation → exclusive seal → full committed reopen
state machine and exact portable hash domain `SAFE:publication-commit:v2`.
Registration version is **`stage11_publication_record_v1`**, kind is
**`STAGE11_DEVELOPMENT_SEMANTIC_REQUEST_CATALOG`**, and input key is
**`stage11_input_binding_sha256`**. Stage 10 names are not reused.

Every reopening recomputes core bytes, IDs, both relation fingerprints, every
hypothesis-to-core projection, map totality and all diagnostics. Independent
connections are memory-capped with disk spilling disabled and read authoritative
PanFS inputs/output only; generation local state and checkpoints are unnecessary.
An insufficient reopen memory envelope fails rather than spilling to PanFS.
The DEVELOPMENT resource envelope is measured below; no production-capacity
claim is made. Larger future populations require separately reviewed resources.

Before any input read, the shared Goethe/SLURM guard, exact clean executable,
pinned runtime, controlled no-follow topology, same PanFS mount, private modes,
local capacity and project quota must pass. Network connection entry points and
DuckDB remote filesystems/extensions are disabled. Errors and progress receipts
contain only static codes, counters and operational/artifact metadata. A 64 KiB
durable failure slot is allocated before input processing. The first failure
survives secondary reporting, local-stat and cleanup errors. Post-seal uncertainty
requires full reconciliation; a seal alone is never a ready-candidate claim.

## Validation and resource evidence

The [validation script](../../scripts/validate_stage11_implementation.py) checks
exact frozen design bytes, assets, independent byte vectors and launcher syntax.
Focused Stage 11 tests: **158 passed**. They cover clean/reversed input, different
input units/digest partitions/thread counts, interrupted and resumed execution,
complete local loss, skew, byte-heavy Unicode, corruptions, collision injection,
wrong-context lineage, concurrent publication, all authoritative publication
objects and content-free error handling.

The first full safe suite exposed two pre-existing report-surface failures:
the documentation validator omitted the already accepted `stage10.md`. Its
allowlist now recognizes that existing report; both focused report checks pass.
This maintenance changes no accepted report or scientific implementation.
The final safe suite passes **1,343 tests**, with zero failures, in 48.12 s.
Strict mypy passes all 134 source modules; Ruff lint/format (211 files), both
Stage 10/11 inventory/contract validators, report checks, 134 local Markdown
links, privacy scope, SBATCH syntax and `git diff --check` pass.
[Machine-readable validation evidence](../scientific_assets/stage11_implementation_validation_v1.json)
binds the exact implementation inventory.
The safe suite's existing 24 public ICU/runtime tests require an explicit Mac
build and remain skipped, as in previous Stage 10 safe-suite records. Stage 11
does not execute transliteration; exact accepted Stage 10 inventory/runtime
fingerprints are checked separately. No protected fixture is acquired for tests.

[Final bounded synthetic measurement](../scientific_assets/stage11_synthetic_resource_measurement_v1.json):
8,192 invented hypotheses, 4,097 requests, 7.340 s pipeline including all
publication validations; process RSS 340,934,656 bytes; sampled/terminal local
4,488,636 bytes; durable checkpoints 4,684,801 bytes; candidate 4,053,106 bytes.
Four input units and 256 reduction units validated. Python 3.14.3, Arrow 25.0.0,
DuckDB 1.5.5. This is sizing evidence, not a cluster throughput guarantee.

The accepted Stage 10 relation inventory is 134,911,179 compressed bytes, larger
than the 2,176,762-byte synthetic input. Planning allows approximately 0.5 GiB
durable state and 1 GiB transient state, with **2 GiB** reserves on each filesystem;
these are estimates, not measured protected peaks. The launcher requests **2 CPUs,
8 GiB RAM, 1 hour, `--tmp=2048M`**. Two memory-capped engines may coexist during
publication; the request leaves space for Arrow/Python and large scalar copies.
No hundreds-of-GiB request or performance experiment is introduced.

Implementation-time PanFS preflight at 2026-10-04T09:31:13Z: new Stage 11 parent
and accepted artifact are owner 60099, directories 0700, device 44; accepted seal
0600 and zero bytes. Project quota availability **11,127,172,420 KiB**; whole
filesystem availability **13,278,161,662,032 KiB**. The exact runtime executable
exists. A fresh quota/input-manifest check precedes submission; guarded runtime,
full relation and capacity checks repeat inside the single job before generation.

## Complete bounded implementation self-review

One bounded review is complete. PASS denotes implemented synthetic/static
evidence, not DEVELOPMENT acceptance. Candidate-level final self-review remains
required after the authorized job completes.

| ID | Challenge | Disposition and evidence |
|---|---|---|
| I01 | Stage 12 N, retrieval policy or host enters identity | PASS: closed 19-field allowlist; execution-field rejection and byte-vector tests |
| I02 | Headers, credentials or implicit language affect core | PASS: no header field; exact NO_REQUEST_LANGUAGE_OVERRIDE; no transport client |
| I03 | Full-text/structured or endpoint aliasing | PASS: disjoint paired modes and independent synthetic oracle |
| I04 | Country filter/address-country alias | PASS: separate required boundary and validated null country; no country inference |
| I05 | Null/empty/default/type alias | PASS: exhaustive scalar/missing-field/optional-null tests; no coercion |
| I06 | Unknown parameters bypass contract | PASS: upstream and core exact field sets and singleton policies |
| I07 | Unicode/whitespace normalization | PASS: LF/backslash, composed/decomposed, astral, RTL, punctuation and whitespace vectors |
| I08 | Framing/name/order ambiguity | PASS: independent encoder, fixed hex vectors, malformed/overflow/trailing-byte tests |
| I09 | Truncated IDs or hash-only merging | PASS: full binary[32], full-byte equality; injected collision fails before seal |
| I10 | Missing, duplicate, swapped or orphan map | PASS: bidirectional sets, PK/FKs and every-edge reconstruction; equal-count swapped-edge fault |
| I11 | Lost cross-source/role/family provenance | PASS: upstream exact IDs; both hypothesis/context joins; wrong-context family fault |
| I12 | Membership used as confidence | PASS: workload-only labels; separate family/hypothesis denominators; no scoring |
| I13 | O(N²) or population-sized Python structures | PASS: external sort/join, one-row reads and byte-bounded writes; streamed popular groups |
| I14 | Generic writer rejects canonical byte blobs | FIXED: Stage 11 byte-aware writer replaces the inherited digest-only size assumption; all pipeline tests pass |
| I15 | Giant value silently skipped or truncated | PASS: multi-megabyte Unicode end-to-end equality; fatal resource policy |
| I16 | Partial/cross-SHA/input/schema resume | PASS: immutable exact-bound units; mismatch faults and local-loss resumed equality |
| I17 | Gaps/overlaps/incomplete contributors | PASS: exact input key ranges/digests/counts and reduction contributor certificate; complete final projection |
| I18 | Shard/order/thread/path-dependent science | PASS: clean/reversed/repartitioned/multithread/resumed relation and dataset equality |
| I19 | Ephemeral bytes needed after publication | PASS: full reopen succeeds after deleting all synthetic generation local state |
| I20 | Wrong publication namespace/key | PASS: dedicated adapter and record version; Stage 11 namespace/key assertions |
| I21 | Premature/false seal or reservation race | PASS: concurrent publisher, before/after-effect, manifest/registration/payload/seal/topology faults |
| I22 | Failure telemetry masks primary error | FIXED/VALIDATED: preallocated first-failure record, guarded secondary errors and teardown; poison/local-stat fault tests |
| I23 | Protected payload/log/network leakage | PASS: execution guard before access, closed CLI/receipt errors, network disabled, synthetic poison tests |
| I24 | Historical scientific files/history rewritten | PASS: frozen design and Stage 10 inventory validator; branch-only implementation; no accepted artifact mutation |
| I25 | Stale general report-validator allowlist | FIXED: recognize existing accepted Stage 10 report; two report checks pass; science unchanged |
| I26 | Resource request presented as measured usage | PASS: explicit synthetic/scoped/sampled measurements; protected peaks remain unmeasured before execution |

## Execution boundary

The owner has already authorized the single DEVELOPMENT run once local gates
pass. Commit and push this branch, record the exact executable, create a new
detached Goethe checkout using Git, then submit the reviewed launcher **once**.
There is no main integration requirement. If pending/running, report the single
observation and stop for the owner's next `continue`; do not poll, cancel or
resubmit. Failures preserve all evidence and receive no automatic retry.

After completion, reconcile the immutable candidate, sanitized full-population
summary, exact manifests/fingerprints, scheduler/resource evidence and final
candidate self-review. Stage 11 remains **NOT YET OWNER ACCEPTED**; fresh
independent review follows candidate readiness. Stage 12 remains **NOT STARTED**.
