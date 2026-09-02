# Stage 8 DEVELOPMENT publication remediation v2

## Verdict

`STAGE08_ADDRESS_EVIDENCE_IMPLEMENTATION_READY_FOR_CONTROLLED_DEVELOPMENT_REEXECUTION`

This is the second bounded Stage 8 code, synthetic-test, and documentation
remediation. It is not a controlled materialization, independent-review pass,
Stage 8 acceptance, or execution authorization.

## Failed independent rereview and preserved history

Independent rereview returned
`STAGE08_ADDRESS_EVIDENCE_INDEPENDENT_REREVIEW_FAIL` for exact reporting
candidate `fdf2f8c78781a6bdb5dad637af5954ae81cf331d`, executable
`bd89a032eb6fcf16a7515e0bd2991165d87246b1`, repaired DEVELOPMENT job
`1763984`, and its immutable controlled artifact. The artifact is not asserted
corrupt. Its exact scientific reconciliation remains historical evidence for
`bd89a032…`; it cannot validate the new executable.

The rereview independently reproduced a post-effect rename hole: the real
temporary-to-final rename completed, the rename wrapper then raised before the
Python-side path variable changed, and cleanup inspected only the vanished
temporary path. The invocation reported `STAGE08_PUBLICATION_FAILURE` while
the final path still had `_SUCCESS.json`, lacked `_IN_PROGRESS`, and satisfied
the published-reader terminal definition.

The original executable `a2544401…`, job `1763747`, first independent-review
failure, first remediation executable `bd89a032…`, job `1763984`, its exact
scientific reconciliation, and the second rereview failure remain distinct,
reachable history. Neither controlled job is relabeled corrupt or accepted.

## Executable remediation

- Branch: `stage08-address-evidence-publication-remediation-v2`
- Required base: `fdf2f8c78781a6bdb5dad637af5954ae81cf331d`
- Executable commit: `bdea7232a3f92ebd381be87610b753b8e4c35481`
- Resolution class: **A — ADOPT COMPLETED PUBLICATION**, limited to an
  ambiguous rename or the immediate post-rename/pre-parent-fsync phase.

Adoption requires all of the following observable proofs:

1. only the final path exists;
2. `lstat`-equivalent, non-symlink inspection proves the final directory has
   the same device/inode identity captured from this attempt before rename;
3. the publication parent fsync succeeds; and
4. the final publication independently reopens and passes the complete frozen
   published-bundle validator.

Only then does the invocation return success. A rename exception is not itself
treated as evidence that the rename failed. Parent-fsync failure and
postpublication reopen failure are not adoption cases: they remain fatal and
demote the owned tree.

## Observable path-state reconciliation

| Observable state | Deterministic rule |
|---|---|
| `TEMP_PRESENT_FINAL_ABSENT` | Rename had no visible final effect. Never adopt. Demote the identity-matching temporary attempt to exact incomplete state and report the original failure. |
| `TEMP_ABSENT_FINAL_PRESENT` | Adopt only in the two permitted rename phases, only when the final directory is the captured attempt identity, and only after parent fsync plus complete independent published validation. In later fatal phases, demote the owned final tree. An unrelated final identity is never changed or adopted. |
| `TEMP_PRESENT_FINAL_PRESENT` | Never adopt. Use the captured identity to demote only this invocation's tree. Preserve the other path unchanged, including an unrelated valid final publication. |
| `TEMP_ABSENT_FINAL_ABSENT` | Never adopt. Report failure; neither canonical path exposes a successful artifact. |

Symlinks and non-directory objects count as present but have no adoptable
directory identity. Reconciliation never follows them. The captured
device/inode identity prevents repeated cleanup from mutating an unrelated
publication.

## Complete crash-consistency audit

| Ordered step | Failure/effect boundary | Observable state and reconciliation |
|---:|---|---|
| 1. Validate configuration, runtime, execution guard, and exact Stage 6/7 bindings | Failure remains possible before output creation. | Neither publication path belongs to the attempt; return the original fail-closed error. |
| 2. Create the private sibling attempt directory at `0700` and capture its non-symlink device/inode identity | Directory creation may have taken effect before an exception is observed. | A present temporary path is not successful because no valid success marker exists; later cleanup only acts when identity ownership is known. |
| 3. Create and fsync `_IN_PROGRESS` at `0600` | Marker creation may take effect before raising. | Temporary-only state remains incomplete; cleanup reconciles the marker by observation. |
| 4. Write candidate, component, source-map, mapping, and schema artifacts | Any write may fail after a partial file effect. | `_IN_PROGRESS` remains; `_SUCCESS.json` is absent; demotion is idempotent. |
| 5. Create and fsync the manifest | Creation/fsync may fail after file effect. | Still temporary and incomplete; no published reader can accept it. |
| 6. Fsync every artifact, metadata file, manifest, `_IN_PROGRESS`, and required temporary directory | Any fsync can fail after data reached storage. | Still temporary with `_IN_PROGRESS`; report failure after exact incomplete-state reconciliation. |
| 7. Prepublication reopen validation | Scientific/integrity rejection remains possible. | Validation runs with `_IN_PROGRESS` present and `_SUCCESS.json` absent. Failure cannot expose success. |
| 8. Recheck that the final path is absent | A competing path may have appeared. | Both paths are observed; never overwrite or adopt the unrelated final; demote only the captured attempt. |
| 9. Create and fsync `_SUCCESS.json` | Creation may take effect before raising. | Exception cleanup first removes success, then ensures `_IN_PROGRESS`; mutation outcomes are re-observed before retry. |
| 10. Remove `_IN_PROGRESS` | Removal may take effect before raising. | Cleanup reasons from marker state, removes success, recreates/validates `_IN_PROGRESS`, and fsyncs the incomplete tree. |
| 11. Fsync the terminal temporary directory | Fsync may fail after the success/no-in-progress namespace effect. | Still temporary; demote to `_IN_PROGRESS` present and success absent before reporting failure. |
| 12. Invoke the final sibling rename | Four path states are possible, including a real rename followed by an exception. | Set phase to ambiguous before the call, inspect both paths afterward, and apply the four-state rules above. No Python path assignment is trusted as publication evidence. |
| 13. Verify the immediate post-rename filesystem state and owned identity | An asynchronous exception may arrive immediately after rename. | Final-only owned state enters the same guarded adoption path; every other state fails/demotes. |
| 14. Fsync the final parent directory | Failure is possible after rename effect. | This phase is publication-fatal, not adoptable. Demote the owned final tree to exact incomplete state. |
| 15. Independently reopen and validate the final publication | Any scientific, hash, topology, schema, permission, marker, or reconciliation check may fail. | This phase is publication-fatal. Demote the owned final tree; no failed result retains reader-visible success. |
| 16. Return completion | Success is emitted only from the normal validated path or guarded adoption path. | Exact terminal state is final present, temporary absent, `_SUCCESS.json` valid, `_IN_PROGRESS` absent, parent fsynced, and complete reopen validation passed. |
| 17. Demotion/reconciliation on exception | Success removal, marker creation, or cleanup fsync may itself take effect and then raise. | Remove success first, ensure the exact in-progress marker, re-observe and retry idempotently, verify owner-only modes, and fsync. A cleanup failure is reported only after checking the tree cannot still expose success; unrelated identities are never modified. |

No new marker vocabulary or hidden terminal state was introduced. The
standalone validator continues to recognize exactly published success or to
reject the tree.

## Fault-injection and regression evidence

- Stage 8 focused suite: 28 passed.
- The key regression performed the real filesystem rename, asserted that the
  temporary path vanished and final path appeared, then raised. The invocation
  adopted the final publication only after parent fsync and full reopen
  validation; independent validation of the returned result also passed.
- A distinct before-effect rename failure retained only the temporary path with
  `_IN_PROGRESS`, no `_SUCCESS.json`, and a published-reader rejection.
- An immediate post-rename `KeyboardInterrupt` entered the guarded adoption
  path and returned success only after full reopen validation.
- Parent-directory fsync and postpublication reopen failures remained failures
  and left the owned final path explicitly incomplete.
- A post-effect rename followed by a failed adoption validation did not return
  success and demoted the final path.
- Post-effect exceptions during success-marker removal and incomplete-marker
  creation were reconciled from disk; repeated demotion was idempotent.
- All four temporary/final presence states, a non-followed unrelated final
  symlink, and a both-path state with an unrelated valid final were exercised.
  Repeated reconciliation left the unrelated publication byte-for-byte valid.
- Normal publication ordering and the complete first-remediation fault tests
  remain passing.
- Relevant Stage 7 regressions: 54 passed.
- Relevant runnable earlier-stage atomic-publication regression: 1 passed.
  Four Stage 4–6 cases stopped only at the unchanged Python 3.14.3 runtime
  guards under local Python 3.14.7; no guard was bypassed or weakened.
- Safe full local suite: 595 passed, 24 expected runtime-pin failures, and 4
  deselected protected-payload tests.
- Ruff, changed-file Ruff format, strict mypy over 98 source/test targets,
  shell syntax, JSON validity, Markdown local links, `git diff --check`, and
  privacy/tracked-data checks passed.

## Scientific-contract preservation

The frozen values remain exact:

- contract fingerprint:
  `8b3c530e714177fe2c30a97d61dcc199b7f9efba58f3c17a291b817af0f24d5e`;
- schema-bundle fingerprint:
  `6c8ebecd24c495dbe2ce32125ac1cb89c4a9de4905c786b774d10ad728ed392f`;
- label-mapping fingerprint:
  `b18167d2d5c1f1402d1bb0e92559befb92418f5f4f34df885596778a11d5c09d`;
- candidate, component, source-map, and occurrence schema fingerprints:
  `b1d56ea33c22e639ab798581c5533b1a0981ef5452dce5cb24e168d4a684bd4c`,
  `112fb17c2afac27b941d30f57fe5c1bb2e46d779f89bdf2efbd8c719a3b87ccf`,
  `884eb8456fc6ee84a699a9e2371224e5c709363daac0febc5975f911bf48c398`,
  and
  `df1cac9b6d9f86ffb76d1ea744fc64f15149c9e33fef980213286b91b2d02038`.

The contract/profile, four schemas, semantic taxonomy, exact 20-label mapping,
Stage 6/7 bindings, field meanings, status vocabularies, ordering, nullability,
parser-evidence semantics, occurrence semantics, and
candidate/component/source/occurrence grains are unchanged. The Stage 8/Stage
9 boundary and the first remediation's prepublication-validation guarantee are
unchanged.

## Privacy and next action

This remediation opened no protected Stage 6, Stage 7, or Stage 8 row-level
artifact; accessed no HOLDOUT or production data; submitted no SLURM job; and
made no parser, reference, external-service, Pelias, geocoder, DeepParse, or
Senzing call.

Proposed bounded Goethe resources remain one node, one task, four CPUs, 32 GiB,
four hours; DuckDB 8GB/four threads; Arrow input/candidate/component batches
16/32/65,536; 128 MiB target batches; and candidate/component/source shards
2,048/500,000/4,096. A new immutable run identity is required.

Exact next action requiring separate owner authorization:

**AUTHORIZE EXACTLY ONE NEW CONTROLLED STAGE 8 DEVELOPMENT MATERIALIZATION AT
THE NEW EXECUTABLE SHA.**
