# Stage 8 DEVELOPMENT publication remediation v3

## Verdict

`STAGE08_ADDRESS_EVIDENCE_IMPLEMENTATION_READY_FOR_CONTROLLED_DEVELOPMENT_REEXECUTION`

This is the third bounded Stage 8 DEVELOPMENT code, synthetic-test, and
documentation remediation. It is not a controlled materialization,
independent-review pass, Stage 8 acceptance, or execution authorization.

## Failed independent rereview and preserved history

Independent rereview returned
`STAGE08_ADDRESS_EVIDENCE_INDEPENDENT_REREVIEW_FAIL` for exact reporting
candidate `70e3de9536aee7074e27018d39e0164f3a2200ae`, executable
`bdea7232a3f92ebd381be87610b753b8e4c35481`, controlled DEVELOPMENT job
`1764219`, and its immutable artifact. Review evidence is commit
`2a6bba6060a2200e54d1a49a251a65e83875276d` on separate branch
`stage08-independent-rereview-bdea7232`; the independent harness SHA-256 is
`acf343ace7a8551d4a633cf4a65190150a329185b7f6d9f3bb455897425d20d8`.
The reviewer branch was not continued or modified.

The exact artifact is
`/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage08/development/stage08_development_20260902T112644Z_bdea7232a3f9`.

The artifact is not asserted corrupt. It remains immutable historical
DEVELOPMENT evidence only for executable `bdea7232…` and cannot validate the
new executable. The two independently falsified invariants were:

1. an injected stdout `OSError` after successful materialization made the CLI
   exit nonzero while the final tree remained reader-visible success; and
2. policy-A adoption did not recheck final-path ownership after parent fsync
   and complete final reopen validation, so a byte-identical different-inode
   replacement could be reported as the invocation's success.

Original executable `a2544401…` and job `1763747`, first remediation
`bd89a032…` and job `1763984`, second remediation `bdea7232…` and job `1764219`,
all three review failures, and every exact blocker remain distinct reachable
history. No historical artifact is relabeled corrupt or accepted.

## Executable remediation

- Branch: `stage08-address-evidence-publication-remediation-v3`
- Required base: `70e3de9536aee7074e27018d39e0164f3a2200ae`
- Executable commit: `c04cb97214a9f1e5d2b80512c756400321eefa80`
- Scope: terminal publication ownership and post-commit CLI presentation only
- Publication policy: policy A, `ADOPT COMPLETED PUBLICATION`, remains limited
  to the ambiguous rename/immediate post-rename phases

## Exact program-level commit boundary

Publication and presentation are separate results.

**Publication success** is established only when `materialize_stage08`
returns a `Stage08Outcome`. Before that return, the owned attempt must have
completed the success-marker transition, temporary-tree fsync, atomic rename
or exact policy-A reconciliation, first no-follow ownership verification,
parent-directory fsync, complete independent final reopen validation, all
fallible outcome/timing bookkeeping, `umask` restoration, and a final
no-follow device/inode identity verification. The final identity check is the
last rejection-capable publication operation; only local control transfer
returns the prepared outcome afterward.

**Presentation success** means the already-computed privacy-safe result was
serialized, written to stdout, and explicitly flushed. Presentation is not
part of the filesystem commit. Once publication success has returned, a
serialization, stdout write, stdout flush, or secondary stderr diagnostic
failure cannot change the CLI's success return code or demote/mutate the final
tree. A known-broken standard stream is detached from `sys.stdout` or
`sys.stderr` so interpreter-shutdown flushing cannot retry it; detachment and
the fixed secondary diagnostic are themselves best-effort and nonrecursive.

Before materializer return, `ExecutionPolicyError` and
`Stage08ValidationError` return code 1; other genuine exceptions propagate and
also produce a nonzero process result. The success-only presentation handler
is never entered on those paths.

## Full publication and CLI state machine

| Step | Possible exception and filesystem effect | Ownership and reader-visible state | Reversibility and process semantics |
|---:|---|---|---|
| 1. Create attempt tree | Private sibling creation may fail before or after effect. | On successful observation, capture its non-symlink `(st_dev, st_ino)`; final is absent; no reader success. | Owned attempt is demotable; failure is nonzero. |
| 2. Create `_IN_PROGRESS` | Exclusive create, write, flush, file fsync, or mode operation may fail. | Temporary tree is explicitly incomplete and success marker absent. | Identity-guarded cleanup retains incomplete state; failure is nonzero. |
| 3. Materialize artifacts | Arrow/Parquet writes, hashing, reconciliation, or shard closure may fail after partial files. | Captured temporary identity remains authoritative; no final success exists. | Attempt remains demotable/incomplete; failure is nonzero. |
| 4. Write manifest | Exclusive JSON serialization/write/flush/fsync may fail after partial effect. | `_IN_PROGRESS` remains and `_SUCCESS.json` is absent. | Attempt remains demotable/incomplete; failure is nonzero. |
| 5. Fsync materialized tree | Any artifact, metadata, manifest, marker, or directory fsync may fail. | Still temporary and incomplete; no reader accepts it. | Failure is nonzero after incomplete-state reconciliation. |
| 6. Prepublication reopen validation | Any scientific, schema, hash, topology, permission, totality, or privacy check may fail. | Validation occurs with `_IN_PROGRESS` present and success absent. | Failure cannot expose reader success; nonzero. |
| 7. Prepare success marker | Exclusive creation, JSON serialization, write, flush, file fsync, or mode may fail. | Both markers can transiently exist; published validator rejects the in-progress tree. | Cleanup removes success first, then re-establishes incomplete state; nonzero. |
| 8. Remove `_IN_PROGRESS` | Unlink may fail before or after effect. | Temporary tree may transiently have the terminal marker set but is not final. | Owned temporary tree is demotable; nonzero on unreconciled failure. |
| 9. Fsync terminal temporary tree | Directory fsync may fail after marker transition. | Temporary identity remains captured; final absent. | Demote owned temporary tree; nonzero. |
| 10. Rename temporary to final | Rename may fail before effect, succeed, or succeed then raise/interrupt. | All four TEMP/FINAL presence states are possible; readers may see a final terminal tree. | Outcome is ambiguous, not automatically failure or success. |
| 11. Reconcile ambiguous rename | No-follow inspection may fail; both, neither, temp-only, or final-only states are classified. | Only final-only with the captured identity is eligible for policy A; symlinks/unrelated identities are never eligible. | Noneligible owned trees are demoted; unrelated paths are preserved; failure is nonzero. |
| 12. First ownership verification | No-follow path observation may fail or differ. | FINAL must reference the captured device/inode and TEMP must be absent. | Mismatch fails closed; only an identity-matching owned tree may be demoted. |
| 13. Fsync parent directory | Parent fsync may fail or a fault may replace FINAL during the operation. | Earlier ownership is provisional; reader-visible terminal state is not yet invocation success. | Failure is fatal and identity-guarded; replacement is tested again later. |
| 14. Complete final reopen validation | Any full published-bundle check may fail; FINAL may be replaced before/during validation. | A byte-identical replacement can validate scientifically, so validation alone does not establish ownership. | Failure is fatal; exact owned tree may be demoted, unrelated replacement preserved. |
| 15. Reverify FINAL ownership | Final independent no-follow stat may fail, find absence/non-directory/symlink, or a different device/inode. | FINAL must still equal the captured attempt identity after steps 13–14 and all fallible outcome bookkeeping. | This is the last rejection-capable publication operation. Mismatch is nonzero and never adopts/demotes an unrelated tree. |
| 16. Return publication success | No additional I/O, validation, cleanup call, formatting, or filesystem mutation occurs. | Exact invocation-owned final tree has a valid success marker, no in-progress marker, parent fsync, and complete reopen pass. | `Stage08Outcome` return irrevocably establishes program-level publication success. |
| 17. Handle CLI result | Status and aggregate fields are serialized into one privacy-safe payload. | Filesystem publication is untouched. | Ordinary write plus explicit flush reports success; exit remains 0. |
| 18. Handle presentation failure | Serialization/write/flush may raise; fixed stderr write/flush may also raise. | Final tree is not mutated or demoted. | Broken streams are best-effort quarantined; diagnostic failure is swallowed without recursion; exit remains 0. |
| 19. Determine process exit | Successful publication returns 0 regardless of presentation result; prepublication known failures return 1 and other exceptions propagate. | Process status now agrees with publication outcome within the program-controlled model. | No claim covers external `SIGKILL`, power loss, kernel failure, or hostile mutation after the final identity check/return. |

## Ownership and TOCTOU model

The attempt identity is captured with a no-follow stat before rename and
remains meaningful across the same-filesystem directory rename. Policy-A
adoption first proves final-only placement and the captured identity, then
fsyncs the parent and fully reopens the final bundle. The common terminal path
performs all remaining fallible outcome construction and restores the process
`umask`, then independently no-follow stats FINAL again. Device/inode mismatch,
absence, symlink, or non-directory state is fatal.

If FINAL has changed identity, cleanup observes both canonical paths without
following symlinks and does not delete, alter, or demote the unrelated
replacement. If a final ownership check fails while FINAL still has the owned
identity, the frozen identity-guarded demotion policy may remove success and
restore `_IN_PROGRESS`.

The publication parent and attempt/final trees are owner-only (`0700`, files
`0600`). The design assumes no untrusted actor can traverse or mutate that
topology. It detects replacements during the in-program adoption/publication
sequence but does not claim an atomic compare-and-return primitive or immunity
to a privileged/owner adversary mutating FINAL after the last stat or after
return.

## Fault-injection and regression evidence

- Complete Stage 8 focused/publication suite: 45 passed.
- Exact reviewer stdout regression: real synthetic materialization completed,
  the final tree independently reopened as reader-visible success, the first
  CLI result write raised `OSError`, CLI returned 0, and final identity/markers
  remained unchanged.
- Explicit stdout-flush child-process regression: process exit was 0 after the
  CLI caught the post-commit flush `OSError` and quarantined stdout.
- Serialization failure, stdout first-write failure, stdout flush failure,
  simultaneous stderr failure, ordinary reporting, and two prepublication
  failure paths passed their exact status assertions.
- Exact byte-identical replacement regression passed at four boundaries:
  during parent fsync, after parent fsync/before final reopen, during final
  reopen, and after reopen/before final ownership. Every replacement had a
  different inode, independently validated as a complete published tree, and
  still caused `STAGE08_FINAL_OWNERSHIP_MISMATCH`; the unrelated replacement
  and retained owned tree were not demoted.
- Symlink replacement before the final check failed ownership without
  following or mutating the symlink target.
- An injected ownership rejection with unchanged owned identity demoted only
  that owned tree to `_IN_PROGRESS` present and success absent.
- Normal publication succeeded with trace `parent fsync -> final reopen
  validation -> final ownership`, and the final ownership event was last.
- Real rename then raise passed policy-A adoption with trace `complete adopted
  final reopen validation -> final ownership`; independent reader reopen then
  passed.
- Before-effect rename failure, immediate post-rename interrupt, failed parent
  fsync, failed final reopen validation, partial/repeated demotion, all four
  TEMP/FINAL states, symlink handling, unrelated-path preservation, marker
  transition failures, terminal-tree fsync failure, and prepublication
  corruption/validation failures remain passing.
- All 149 Stage 7 tests passed.
- Six selected earlier atomic-publication test functions passed all 33
  parameterized cases.
- Safe full local suite: 612 passed, 24 unchanged exact-Python-3.14.3 guard
  failures under local Python 3.14.7, and four protected-payload deselections.
- Ruff, changed-file Ruff format, strict mypy over the established 98
  source/Stage-8-test targets, shell syntax, JSON validity, Markdown local
  links, `git diff --check`, privacy/tracked-data, scientific fingerprints,
  executable surface, and Git ancestry/status gates passed. Repository-wide
  Ruff format still reports the same 19 unrelated historical files; none was
  changed or reformatted.

## Scientific-contract preservation

The frozen values remain exact:

- contract fingerprint:
  `8b3c530e714177fe2c30a97d61dcc199b7f9efba58f3c17a291b817af0f24d5e`;
- schema-bundle fingerprint:
  `6c8ebecd24c495dbe2ce32125ac1cb89c4a9de4905c786b774d10ad728ed392f`;
- label-mapping fingerprint:
  `b18167d2d5c1f1402d1bb0e92559befb92418f5f4f34df885596778a11d5c09d`;
- candidate schema:
  `b1d56ea33c22e639ab798581c5533b1a0981ef5452dce5cb24e168d4a684bd4c`;
- component schema:
  `112fb17c2afac27b941d30f57fe5c1bb2e46d779f89bdf2efbd8c719a3b87ccf`;
- source-map schema:
  `884eb8456fc6ee84a699a9e2371224e5c709363daac0febc5975f911bf48c398`;
  and
- occurrence schema:
  `df1cac9b6d9f86ffb76d1ea744fc64f15149c9e33fef980213286b91b2d02038`.

The contract/profile, all four schemas, exact 20-label mapping, semantic
classes, Stage 6/7 manifests and bindings, logical-hash construction,
candidate/component/source/occurrence grains, parser/occurrence semantics,
and Stage 8/Stage 9 boundary are unchanged from executable `bdea7232…`. The
executable source delta is confined to Stage 8 CLI terminal reporting and
Stage 8 publication ownership/state-machine handling. No pycountry,
libaddressinput, OSM, Overture, Pelias, geocoding, reference validation,
hypothesis generation, ranking, final matching, or semantic address logic was
added.

## Privacy, historical jobs, and next action

This remediation opened no protected Stage 6/7/8 row value or controlled
artifact, accessed no HOLDOUT or production data, submitted no SLURM job, and
made no parser, reference, external-service, network, Pelias, geocoder,
DeepParse, or Senzing call. Jobs `1763747`, `1763984`, and `1764219` and their
artifacts remain untouched historical evidence only for their exact
executables.

Proposed bounded Goethe resources remain unchanged: one node, one task, four
CPUs, 32 GiB, four hours; DuckDB 8GB/four threads; Arrow
input/candidate/component batches 16/32/65,536; 128 MiB target batches; and
candidate/component/source shards 2,048/500,000/4,096. A new immutable run
identity is required.

Exact next action requiring separate owner authorization:

**AUTHORIZE EXACTLY ONE NEW CONTROLLED STAGE 8 DEVELOPMENT MATERIALIZATION AT
THE NEW EXECUTABLE SHA.**
