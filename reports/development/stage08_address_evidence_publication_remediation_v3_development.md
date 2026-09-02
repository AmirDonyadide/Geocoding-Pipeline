# Stage 8 third-remediation DEVELOPMENT materialization

## Candidate result

Current verdict:
`STAGE08_ADDRESS_EVIDENCE_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REREVIEW`.

The single authorized third-remediation Stage 8 DEVELOPMENT job `1764273`
completed `0:0` in 16m08s at exact executable
`c04cb97214a9f1e5d2b80512c756400321eefa80`. It published one immutable
artifact at:

`/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage08/development/stage08_development_20260902T132726Z_c04cb97214a9`

The artifact manifest SHA-256 is
`2a50bd8c066552c9cb7505ed2d6071f1ee36161b9a2cc07f3ed364cf00237827`.
Its logical dataset SHA-256 is
`9c9d431c2c1b92712e0cb372f2661ad48f4fe8758dc0327d25aef90ab2c2d526`.
Its final no-follow filesystem identity, recorded after the successful job, is
`(st_dev, st_ino) = (54, 9363000937145638642)`. This is frozen DEVELOPMENT
candidate evidence, not an independent-rereview result or Stage 8 acceptance.

## Exact accepted inputs

- Stage 7 root:
  `/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage07/evidence_only_development/stage07_evidence_e684d84_attempt1`
- Stage 7 manifest/logical identities:
  `f58410877a7810562df7985c7316de7546d4dd8e11a647fd659c53a272e9c266` /
  `0f0706c1396803737f22845837753878bfd2e8b3f9af59b48cfcc1b8c5774530`
- Stage 7 contract/schema fingerprints:
  `c9561e6d08263b2a8824ff66f2a3aa8521e3ff880759abc14173cce440ced8a4` /
  `b0e0e83ea3d929b7df8a6a5f64c2e8eb026395a917da90e97a98858b27e9ead2`
- Stage 6 root:
  `/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage06/development/stage06_development_20260828T223804Z_f39047cc825d`
- Stage 6 manifest/logical/row-map/binding identities:
  `e1da7b8ef04b65b1ece8e710720b57a8536841766fcf9de641f889b42eadd241` /
  `2f6379c0cd5dc9654c03895cae6fdd48f3a7af528158c33e44d2030c816640b6` /
  `1ff9067c521ae93d28c300d7120a03c39681ce7830bf23b6619e2ca6129a4fe1` /
  `6ba224d6d24c3631aae8aac69f4a362bb054f01d9e3d09327ec6b0fdd85a0e7d`

Both accepted manifests matched their exact hashes, both roots exposed only
their success terminal state with owner-only modes, and the Stage 7 manifest
bound the exact accepted Stage 6 manifest. The protected job ran the frozen
Stage 6/7 input validation before materialization.

## Scientific reconciliation

| Evidence | Frozen expectation | Job 1764273 |
|---|---:|---:|
| Exact candidates | 51,779 | 51,779 |
| Ordered parser components | 6,106,088 | 6,106,088 |
| Source rows | 35,000 | 35,000 |
| Representation occurrences | 69,747 | 69,747 |
| STANDARD occurrences | 34,822 | 34,822 |
| NATIVE occurrences | 34,925 | 34,925 |
| Mapped components | 6,106,088 | 6,106,088 |
| Unmapped components | 0 | 0 |
| Dangling components | 0 | 0 |
| Component-count mismatches | 0 | 0 |
| Occurrence-count mismatches | 0 | 0 |

Every frozen scientific validation field is `PASS`: exact candidate identity,
exact Stage 7 fields, raw ordered component preservation, component-index
reversibility, duplicate/unknown-label preservation, source-row identity,
representation-slot correctness, occurrence map-back, applicability/technical
provenance, warning-field preservation, semantic-trust vocabulary absence,
later-stage behavior absence, and HOLDOUT/production exclusion.

Parser calls, reference lookups, network calls, geocoder/external-service
calls, and semantic-trust fields are all zero. HOLDOUT and production access
are false.

## Frozen scientific identities

- Contract fingerprint:
  `8b3c530e714177fe2c30a97d61dcc199b7f9efba58f3c17a291b817af0f24d5e`
- Schema-bundle fingerprint:
  `6c8ebecd24c495dbe2ce32125ac1cb89c4a9de4905c786b774d10ad728ed392f`
- Label-mapping fingerprint:
  `b18167d2d5c1f1402d1bb0e92559befb92418f5f4f34df885596778a11d5c09d`
- Candidate schema fingerprint:
  `b1d56ea33c22e639ab798581c5533b1a0981ef5452dce5cb24e168d4a684bd4c`
- Component schema fingerprint:
  `112fb17c2afac27b941d30f57fe5c1bb2e46d779f89bdf2efbd8c719a3b87ccf`
- Source-map schema fingerprint:
  `884eb8456fc6ee84a699a9e2371224e5c709363daac0febc5975f911bf48c398`
- Occurrence schema fingerprint:
  `df1cac9b6d9f86ffb76d1ea744fc64f15149c9e33fef980213286b91b2d02038`

Relation-logical fingerprints also remain exact:

- candidate evidence:
  `11fbd6e6e32b7dcb293c5918e9d02f19badf52cc9d9c108c910d17d92b8645aa`;
- parser-component evidence:
  `8b1af702c51bd40edc22302778ae2fda5851d9af8af39636a9a9733a94916030`;
- source-candidate map:
  `c4c9f8b3f425f93a1d61880f720136d1f71580871338c9a920c9abeffa93ee32`;
  and
- representation occurrence:
  `57aa3dcc5caf796fbbe15b3c0df655a8f34902107ce9fed3fbb6aaf38e158774`.

The schemas, exact 20-label mapping, Stage 6/7 bindings, semantic classes,
candidate/component/source/occurrence grains, logical-hash construction,
parser-evidence and occurrence semantics, and the Stage 8/Stage 9 boundary are
unchanged from every preceding Stage 8 executable.

## V3 publication terminal contract

Job `1764273` followed the **ORDINARY successful publication path**. The
synthetic fault behaviors were not injected into this protected run.

At executable `c04cb972…`, publication success returns only after this exact
program-controlled sequence:

1. all prepublication rejection-capable validation;
2. temporary-tree durability;
3. atomic rename;
4. parent-directory fsync;
5. complete final reopen validation;
6. outcome construction;
7. process `umask` restoration; and
8. final no-follow `(st_dev, st_ino)` ownership verification.

The successful exact-executable return establishes that every gate passed.
Final ownership was the last rejection-capable publication operation and bound
success to `(54, 9363000937145638642)`. No validation, filesystem mutation, or
other rejection-capable publication work followed that check before return.

The exact program-level commit boundary is the materializer's return of its
prepared outcome after that final ownership gate. Publication and presentation
are separate results. Once that return establishes publication success,
privacy-safe result serialization, stdout write/flush, stream detachment, or a
best-effort stderr diagnostic may fail without changing exit code zero or
mutating/demoting FINAL. Before materializer return, known execution-policy or
validation failures return one; other genuine exceptions propagate to a
nonzero process result. This is a program-controlled exception contract, not a
claim about external `SIGKILL`, power loss, or hostile mutation after return.

Executable blob identity and local regressions also establish that the first
prepublication success-marker repair and policy-A exact-ownership ambiguous-
rename adoption remain intact, alongside the v3 CLI-status and terminal-
ownership repair. The ordinary protected run exercised the successful path;
faulted branches remain synthetic evidence only.

The final `_SUCCESS.json` exactly binds the manifest, logical dataset,
contract, schema bundle, and row totals. `_IN_PROGRESS` is absent; incomplete
siblings are zero; stderr is empty; and the atomic and owner-only publication
claims pass.

The final topology is:

- 26 candidate shards, 103,091,918 bytes;
- 13 component shards, 67,545,742 bytes;
- nine source-map shards, 4,924,221 bytes;
- two metadata files, 25,174 bytes;
- one 19,897-byte manifest;
- one 567-byte success marker;
- eight directories and 52 files total;
- zero symlinks, zero non-`0700` directories, and zero non-`0600` files.

The following remain local/synthetic evidence and require fresh independent
challenge: successful commit followed by stdout write failure; stdout flush
failure; serialization/reporting failure; real rename succeeds then raises;
FINAL replacement with a byte-identical different-inode tree; and replacement
during parent fsync, during final reopen validation, or immediately before the
final ownership gate. None was exercised by job `1764273`.

## Runtime and resource reconciliation

The runtime was Python 3.14.3, Unicode 16.0.0, PyArrow 25.0.0, and DuckDB
1.5.5. The launcher requested one node, one task, four CPUs, 32 GiB, and four
hours. DuckDB used four threads with an 8GB cap. Input/candidate/component
batches remained 16/32/65,536 rows; target batches remained 134,217,728 bytes;
candidate/component/source shard limits remained 2,048/500,000/4,096 rows.

The job completed `0:0` in 16m08s. Batch MaxRSS was 1,789,612 KiB, MaxVMSize
was 2,212,092 KiB, and TotalCPU was 16m37.793s. Scheduler evidence reports
`AllocCPUS=80`, `ReqCPUS=4`, `general1 OverSubscribe=EXCLUSIVE`, and 80 CPUs on
the assigned node. The 80-CPU value is therefore exclusive-node allocation,
not application concurrency; requested and application concurrency remained
four CPUs.

## Historical relation and privacy

The logical dataset SHA-256 exactly matches jobs `1763747`, `1763984`,
`1764219`, and `1764273`. The narrow conclusion is only that all publication
remediations to date left the frozen Stage 8 scientific dataset unchanged.
Historical jobs validate only their exact executables; no prior failed review
is rewritten as success, and no historical artifact is called corrupt.

The original executable/job (`a2544401…`/`1763747`), first independent-review
failure, first repair/job (`bd89a032…`/`1763984`), second failed rereview and
post-effect rename defect, second repair/job (`bdea7232…`/`1764219`), third
failed rereview and its CLI-status/final-ownership defects, third repair/job
(`c04cb972…`/`1764273`), and this candidate freeze remain distinct provenance.

Only sanitized scheduler, manifest, success-marker, topology, and aggregate
evidence was reopened for this freeze. No additional protected job, row-level
inspection, HOLDOUT, production, parser, reference, geocoder, DeepParse,
Senzing, Stage 9, implementation change, or science change occurred.

## Local finalization

- Full Stage 8 focused/publication suite: 45 passed.
- Exact v3 critical regression selection: 14 passed, covering stdout write,
  stdout flush, serialization/reporting, byte-identical replacement at all
  four boundaries, real-rename-then-raise, and prepublication marker safety.
- All Stage 7 tests: 149 passed.
- Complete local Stage 0–2 set, including earlier publication regressions: 129
  passed.
- Ruff, changed-file format, strict mypy, shell syntax, JSON, Markdown links,
  `git diff --check`, privacy/tracked-data, executable identity, scientific
  fingerprints, candidate/report consistency, and Git ancestry/status passed.
- Exact Python 3.14.3 execution guards remain unchanged under local Python
  3.14.7.

## Next action

Exact next action: **FRESH INDEPENDENT STAGE 8 REREVIEW OF THE C04CB972
REPAIRED CANDIDATE.**
