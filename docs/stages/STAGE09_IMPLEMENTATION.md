# Stage 9 implementation and controlled DEVELOPMENT execution

## Status and authority

Current owner authorization (2026-09-10, D058): integrate the approved permanent
reservation / exclusive commit-seal protocol, complete local/fault validation,
push an exact executable and submit **one corrected DEVELOPMENT retry**. The
integration below replaces only Stage 9 publication; no scientific/reference
change or Stage 0–8 modification. The prior failures and diagnostics below remain
historical evidence. Stage 9 is NOT ACCEPTED; no corrected candidate is claimed
before its scheduled execution and validation.
The corrected executable is `3e10ac7c1309c2636f35c0709fa283305d60d998`.
Job `1771191` was submitted once at `2026-09-10T15:56:41Z` and observed PENDING
(Resources), without dependencies or requeue. The execution record carries the
immutable targets and next accounting/reconciliation action; stop without polling.

The owner authorized implementation, synthetic/local validation, one controlled
Goethe-NHR SLURM DEVELOPMENT execution, publication validation and a candidate
report. Stage 9 is **IMPLEMENTED — DEVELOPMENT PREFLIGHT FAILED — NOT ACCEPTED**.
Job `1770156` failed before materializer invocation: the synthetic atomic
no-replace rename returned an error on the compute filesystem. No public pack
or protected candidate was created. Exact errno was not retained; a bounded
synthetic-only filesystem diagnostic was separately authorized by the owner on
2026-09-10. It does not authorize a DEVELOPMENT retry or publication fallback.
Diagnostic job `1771054`, executable
`4915852d874a11a5f437d6cfac8837b5f9b6ebd8`, completed in three seconds. The fresh
no-replace operation failed with `EINVAL` (22); all three collisions were
preserved with `EEXIST`, both ordinary-rename fresh-target baselines succeeded,
and directory fsync checks passed. The current no-replace primitive is unusable
in that observed environment. This does not authorize a check-then-rename
fallback or establish a replacement publication protocol. The bounded
compatibility ledger is recorded; publication correction requires owner review.
The subsequent bounded authorization produced the
[publication-protocol revision candidate](STAGE09_PUBLICATION_PROTOCOL_REVISION.md):
exclusive permanent run reservation plus an atomic empty commit seal, supported
by standard creation semantics and a tests-only synthetic model. The owner has
conditionally approved its logic but requires direct PanFS exclusive-create,
collision and multi-process evidence before integration. Exactly one small
synthetic-only diagnostic is authorized under D056. The active materializer and
DEVELOPMENT launcher remain unchanged; no DEVELOPMENT retry is authorized.
Exclusive-create diagnostic `1771149` was submitted once at exact executable
`a9e6ede7c8aa45f8f11b0eadc797839e46c5b057` and completed successfully. All ten
PanFS cases passed: fresh create, EEXIST collision preservation, three four-process
single-winner races, exact seal/reservation, fsync/reopen/private topology and
symlink rejection. The environment-evidence gate is met; integration still
requires explicit owner authorization. No DEVELOPMENT retry or source change.
Execution details and subsequent state belong in the
[DEVELOPMENT record](../../reports/development/stage09.md).

The [design](STAGE09_OFFLINE_REFERENCE_EVIDENCE.md),
[reference freeze](STAGE09_REFERENCE_FREEZE.md) and
[reference lock](../scientific_assets/stage09_reference_pack_lock_v1.json) remain
byte-for-byte frozen at `f85510f938a8506bf3d4a4f8d2b908d801957414`.
Their historical "implementation not started" statements describe the design
freeze, not the newly authorized implementation. No prior-stage audit is reopened.

## Scientific implementation

The production-capable primitives use PyArrow, exact typed SHA-256 and external
DuckDB joins/sorts; the protected CLI currently permits DEVELOPMENT only.
No pandas, parser execution, external service, source correction, coordinates,
query, geocoder ranking or final acceptance is implemented.

The six logical relations are unchanged:

| Relation | Grain and authority |
|---|---|
| reference_registry | One exact reference edition; immutable raw assets, licensing and source lineage |
| reference_capability | One edition/country/question/object scope with separate positive and negative authority |
| reference_object | One exact public object/record, with original public fields and locators; no coordinates projected |
| candidate_reference_evidence | One scheduled source-row/candidate or parser-candidate question/reference evaluation |
| reference_match_member | One ordered member of a complete multi-witness lookup set; singleton witness stays inline |
| coverage_summary | One typed diagnostic grouping/count/explicit-denominator cell |

The first three relations are bound from an immutable public pack, not copied
into every protected run. The latter three are the protected run's own relations.
Stage 8 remains the only authoritative source map and occurrence view. Evidence
contains original-value locators and digests, not a second copy of protected text.
Original values remain resolvable through the exact Stage 8 binding.

The question catalog, Arrow schemas, normalization rules, semantic enums and
domain-separated identities are executable in `s09_reference_contract.py`.
The profile binds the schema bundle, catalog, normalization, four-state semantics,
semantic runtime, raw reference lock, derived public pack and accepted Stage 8.
The executable/job/runtime provenance is also recorded, but operational layout
and job identity do not change a logically identical dataset fingerprint.
Evidence IDs identify scheduled evaluations; result/witness mutations change
their logical row/dataset fingerprint, not silently create another evaluation.

## Capability and interpretation gates

- ISO_CODES: exact ISO country-code membership, subdivision code/name support;
  only recognized full subdivision-code ownership can contradict country context.
- LIBADDRESSINPUT_METADATA: only locked enabled fields/rules. FORMAT and
  REQUIRED_FIELDS expose metadata, not completeness judgments about an address.
  Q04 country regex and Q08 qualified admin-prefix predicates have scoped negative
  authority. BH unsupported regex and CN unqualified exception rules abstain.
  Missing metadata/ambiguous admin identity/unsupported hierarchy abstains.
- GEONAMES_POSTAL: positive recorded membership and same-record associations,
  never negative validity authority. All 121 countries retain their locked
  capability differences. AR/CA/CL/CN/GB/IE/MT/NL full-code checks abstain;
  BR is major-code-only; US extended ZIPs abstain; excluded full variants are not
  acquired or used. Differing postcode associations produce NOT_FOUND with
  REFERENCE_ASSOCIATION_MISMATCH, never source invalidity.

Only SUPPORTED, CONTRADICTED, NOT_FOUND and NOT_EVALUABLE are semantic check
states. Every contradiction needs an enabled explicit negative certificate and
positive conflicting witness. Parser country cannot select/override source
country. COUNTRY_SUPPORTED/CONTRADICTED/UNRESOLVED is separate, source-only
Q02 evidence; conflicting source-context witnesses reduce to unresolved.

Lookup normalization is exactly versioned ASCII case handling, NFC/lowercase
Unicode 16 names and the frozen country-specific separator rules. It preserves
leading zeroes, scripts, diacritics and meaningful separators. There is no trim,
global transliteration, fuzzy comparison or postcode truncation.

## Reference preparation and bounded execution

`s09_reference_pack.py` verifies every locked raw file, HTTP provenance header
and archive member. The actual metadata member and postal archive are rehashed
before use. No auto-refresh, network fallback or package install exists.
`s09_reference_index.py` constructs public objects and a country/postcode-ordered
Parquet index with exact locality/admin lookup columns. Index logical hashing
uses external object-ID order, independent of its physical country/key order.
Public reopening compares every projected object with its locked raw origin,
rederives capabilities from the lock/metadata, and independently reprojects the
postal index. File hashes alone are not treated as proof of correct projection.

The metadata lookup view is bounded by the frozen small assets. The exact-runtime
test, including Arrow-deserialized registry/capabilities, measures less than
64 MiB reachable Python state. Positive enumeration capabilities remain in the
public relation; only the matrix and performed-rule certificates need a second
runtime lookup index. Public strings are interned within that view only, never
in a process-global protected-value cache.

Evidence logical shards use candidate-ID high 12 bits; equal multi-witness
lookups use lookup-identity high 12 bits. DEVELOPMENT coalesces candidate ranges
into 16 task groups, retaining canonical primary-key output order. Members are
globally merged/deduplicated by exact complete-set identity; they are not copied
per source/occurrence. Postal equal-key requests share work within each bounded
group; a lookup may be recalculated in another group or validation replay,
without duplicating its logical member set. Country/locality/admin joins use
equality hash-join branches, never a country-only Cartesian residual join.
This is a fixed 16-group DEVELOPMENT orchestration, not a production job plan.

Source/candidate scheduling streams narrow accepted columns; parser scheduling
uses ordered component cursors and fixed role counters, including a tested
881,338-component synthetic candidate. Physical predicate scans cover disjoint
candidate ranges. No population-sized Python candidate/component list exists.
Giant scalars are admitted alone; resource failure is fatal, not a semantic
abstention or truncation. The bounded small-result cache is optional and keys on
full normalized inputs. Postal full-key collision guards also span task groups.

Operational-only scratch consists of range checkpoints, normalized lookup
requests, external join/cache tables, unsorted relation files, canonical replay
files and engine spill. These exist for bounded execution/restart/replay; none
is another scientific mapping, context, question or summary relation. Complete
checkpoints bind profile, input range, references, executable and output hashes.
Authorized resume copies verified completed files into a new private attempt;
failed attempts are retained and never overwritten or hardlinked.

## Controlled execution and resources

The launcher is
[`stage09_offline_reference_evidence.sbatch`](../../cluster/goethe_nhr/stage09_offline_reference_evidence.sbatch).
Code arrives through Git at an exact pushed SHA in a new clean detached checkout.
The existing historical Goethe checkout is not reset, cleaned or repurposed.
The existing private Stage 6 runtime supplies exact Python 3.14.3, Unicode 16,
PyArrow 25.0.0 and DuckDB 1.5.5; new `PYTHONPATH` selects only the new executable.
No shared Conda or parser runtime is changed.

Request: one process, four CPUs, 32 GiB RAM, 8 GB per active bulk DuckDB engine,
64 MiB Arrow byte target, 512 MiB target files, 24-hour walltime. The metadata
engine is sequential/small. At least 256 GiB free space is required for outputs,
preserved scratch, public preparation and full reversed-group validation replay.
These are conservative DEVELOPMENT resources, not measured throughput guarantees.
The frozen aggregate planning ceiling is 20.56M evaluations before lookup reuse;
the 141,048,582-row production scenario is not accessed or authorized.

The launcher verifies site/job, exact detached executable, controlled private
paths and a compute-node synthetic exclusive-create/reservation/seal preflight
before protected input. It no longer requires no-replace rename. Only the
configured mount alias is canonicalized; artifact-path symlinks are not resolved
away. Automatic requeue is disabled.
Public preparation and all protected processing are inside the same scheduled
job. Login nodes perform shell/Git/submission orchestration only. Python sockets
and DNS are denied during execution; DuckDB extension autoload/install is disabled.

Submit once. If materially PENDING/RUNNING, record ID/state/time/dependencies/
artifact/executable, stop and await owner `continue`. Do not cancel, resubmit or
poll repeatedly. A failed job is inspected through sanitized machine-level
diagnostics before any separately justified restart; never inspect address text
or launch an automatic retry loop.

## Publication and validation

Exclusive permanent run mkdir → IN_PROGRESS → deterministic relations/manifest →
full scientific validation → canonical bound registration `_SUCCESS.json` →
remove owned IN_PROGRESS, fsync → full prepared reopen → exclusive empty
`_COMMITTED` creation → seal/parent fsync → full committed reopen → descriptor
teardown → last-operation record/seal/ownership check. Directory or registration
existence alone is never success. All files are 0600, directories 0700; no
symlink/hardlink/uninventoried object is permitted.

The Stage 9-local reusable helper is `s09_reference_publication.py`, called by
the public-pack and candidate adapters through `s09_reference_io.publish`.
No Stage 0–8 or project-wide helper is migrated. The reviewed protocol identifier
remains exactly `exclusive_run_commit_seal_v2_candidate`; the retained spelling
is an operational version, not scientific acceptance. Its compact ASCII JSON,
domain-separated commit-record ID and streaming file-inventory hash are separate
from the unchanged scientific fingerprints. CLI receipts include protocol,
disposition, publication key, registration hash and commit-record ID.

Existing exact success requires an external expected manifest and all scientific,
executable, input/reference and publication bindings; `validate-published` uses
that same full read-only adoption path. `materialize --expected-manifest-sha256`
can adopt an already committed exact candidate without rebuilding. The single
corrected launcher intentionally requests a fresh key, not adoption. Existing
incomplete reservations are never stolen or repaired, even for identical jobs
or old timestamps. Verified checkpoints may only be copied to a separately
authorized new-key build as before.

Catchable errors after a possible commit trigger exactly one full reconciliation,
including descriptor-close-after-effect errors. Valid exact state is adopted;
unverifiable state is explicitly fail-closed/uncertain and preserved. No marker
demotion, cleanup or rename occurs. Cross-job identity remains byte/provenance
based; only immediate invocation ownership uses device/inode evidence. Fallible
descriptor teardown precedes the final ownership check. No global umask change
is introduced by publication. Presentation errors cannot demote committed data.

Before publication, a full reversed-group replay independently traverses accepted
inputs again and compares evidence/member logical fingerprints. This tests
determinism and input/reference derivation with the same executable, not an
independent scientific review. Separate integrity checks enforce complete
scheduling, IDs/FKs, capability scope, authority, witness membership/fields,
lineage, counts and the closed scientific schema. Coverage is recomputed during
both private and final reopen. Public/raw assets, input files, schemas, metadata,
inventories, manifest and success marker are all exact-bound.

The test suite covers four states, incomplete-reference safety, every enabled
country/capability selector, native/Latin aliases and scripts, prefix conflicts,
determinism/collisions, giant scalar/component streaming, source map-back,
guard/privacy boundaries, complete match sets, restart and publication faults.
The execution record lists the final checks and complete pre-run defect ledger.

## Downstream handoff and stop gate

BOUNDARY_HANDOFF_SUFFICIENT remains true: Stage 10 can follow immutable Stage 9
evidence → Stage 8 candidate/source map → accepted Stage 6/source-line lineage.
No Stage 5 or Stage 8 alteration or duplicate map is needed. Reference families
and transitive provenance remain available to prevent assumed independence from
later Pelias evidence. Stage 9 does not implement Stage 10 or geocoding.

After successful DEVELOPMENT validation, publish sanitized evidence/coverage
diagnostics only and stop for independent review. Stage 9 is not accepted by
implementation, test success, a SLURM completion or this record.
