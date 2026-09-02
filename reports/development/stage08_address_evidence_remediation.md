# Stage 8 DEVELOPMENT independent-review remediation

## Verdict

`STAGE08_ADDRESS_EVIDENCE_IMPLEMENTATION_READY_FOR_CONTROLLED_DEVELOPMENT_REEXECUTION`

This is a bounded code, synthetic-test, and documentation remediation. It is
not a materialized Stage 8 candidate, independent-review pass, acceptance, or
execution authorization.

## Rejected candidate and exact findings

Independent review returned
`STAGE08_ADDRESS_EVIDENCE_INDEPENDENT_REVIEW_FAIL` for reporting candidate
`adde81d2237e99993222994ce56efb0d74f7c2d3` at executable
`a2544401b4b699f6c020970f3507a2ae432746c5`.

The review found exactly two blockers:

1. `_SUCCESS.json` was written and `_IN_PROGRESS` removed before required
   prepublication reopen validation, so an injected validation failure could
   leave a failed attempt represented as successful.
2. The current technology table in `docs/PROJECT_BRIEF.md` still assigned
   pycountry and offline libaddressinput metadata to Stage 8 rather than the
   Stage 9 reference/format-evidence boundary.

The candidate is rejected and must not be merged or accepted.

## Repaired executable

- Branch: `stage08-address-evidence-remediation`
- New executable SHA: `bd89a032eb6fcf16a7515e0bd2991165d87246b1`
- Frozen contract fingerprint:
  `8b3c530e714177fe2c30a97d61dcc199b7f9efba58f3c17a291b817af0f24d5e`
- Frozen schema-bundle fingerprint:
  `6c8ebecd24c495dbe2ce32125ac1cb89c4a9de4905c786b774d10ad728ed392f`
- Frozen label-mapping fingerprint:
  `b18167d2d5c1f1402d1bb0e92559befb92418f5f4f34df885596778a11d5c09d`

The contract/profile, four schemas, semantic taxonomy, exact 20-label mapping,
status vocabularies, field meanings, upstream bindings, ordering, nullability,
and candidate/component/source/occurrence grains are unchanged.

## Publication state-machine repair

The explicit publication flow is now:

```text
private attempt + _IN_PROGRESS
  -> materialize manifest/artifacts
  -> fsync every artifact, metadata file, manifest, marker, and directory
  -> complete prepublication scientific/integrity reopen validation
     while _IN_PROGRESS exists and _SUCCESS.json is absent
  -> create and fsync _SUCCESS.json
  -> remove _IN_PROGRESS and fsync the terminal attempt directory
  -> atomic sibling rename and parent-directory fsync
  -> immediate post-publication reopen validation
```

Any failure during success-marker creation, marker removal, terminal-directory
fsync, atomic rename, parent-directory fsync, or immediate post-publication
validation demotes the retained tree to explicit incomplete state: `_IN_PROGRESS`
is present and `_SUCCESS.json` is absent. Prepublication failures never create
the final output path. The published validator remains independently callable
and rejects later artifact, manifest, permission, topology, or marker tampering.

## Regression and static evidence

- Stage 8 focused suite: 17 passed. New injections cover prepublication reopen
  failure; failure immediately before success creation; artifact and manifest
  corruption before terminal success; marker-removal, terminal-fsync,
  atomic-rename, and parent-fsync failures after success creation; successful
  marker ordering; and post-publication tamper demotion.
- Unaffected Stage 2/Stage 7/Stage 8 and earlier publication regressions:
  60 passed.
- Safe full local suite: 584 passed, 24 failed, 4 deselected. All 24 failures
  are the known exact Python 3.14.3 Stage 3–6 runtime guards under local Python
  3.14.7; no guard was weakened.
- Ruff, Ruff format check for changed Python, strict mypy over 98 source/test
  targets, shell syntax, JSON validity, Markdown local links,
  `git diff --check`, privacy/tracked-data, and repository-state gates passed.

The tracked current-language audit found only the stale `docs/PROJECT_BRIEF.md`
row. It now states that Stage 8 is lossless typed projection/index with no
reference validation and that potential scientifically justified offline
pycountry/libaddressinput evidence belongs to Stage 9. Legitimate historical
design/tool-screening records remain unchanged.

## Historical evidence and privacy

Job `1763747` and its immutable controlled artifact remain scientifically
reconciled DEVELOPMENT evidence for executable `a2544401…`. They are not
modified, deleted, relabeled scientifically invalid, accepted, or eligible to
validate executable `bd89a03…`. The failed candidate and its two blockers stay
reachable in Git history.

No protected Stage 6/7 row value, controlled Stage 8 artifact, HOLDOUT,
production data, parser, reference tool, geocoder, external service, or SLURM
job was opened or used in this remediation.

## Proposed bounded Goethe reexecution

After separate owner authorization, submit exactly one controlled DEVELOPMENT
materialization from executable `bd89a032eb6fcf16a7515e0bd2991165d87246b1`
using the existing reviewed Stage 8 launcher: one node, one task, four CPUs,
32 GiB, four hours; DuckDB 8GB/four threads; Arrow input/candidate/component
batches 16/32/65,536; 128 MiB target batches; and candidate/component/source
shards of 2,048/500,000/4,096 rows. Use a new immutable run identity and the
exact accepted Stage 7 v2 and Stage 6 roots supplied only at authorized
submission.

Exact next action requiring separate owner authorization:

**AUTHORIZE ONE NEW CONTROLLED STAGE 8 DEVELOPMENT MATERIALIZATION AT THE NEW
EXECUTABLE SHA.**
