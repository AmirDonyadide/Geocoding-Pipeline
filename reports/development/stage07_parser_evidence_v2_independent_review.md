# Stage 7 evidence-only v2 independent review

## Verdict

`STAGE07_EVIDENCE_ONLY_INDEPENDENT_REVIEW_FAIL`

Reviewed candidate: `318b70b00a52376b1b4fe865f41a789e2dd3feb9`.
Implementation under review: `e684d84a8d68498ea790542143c8e125b3eb87b5`.

This review stopped before controlled-artifact replay because the exact Git
candidate contains two material contract/report contradictions. A Goethe job
cannot repair or disambiguate the reviewed SHA. No controlled input was opened,
no parser was called, and no SLURM job was submitted.

## Material findings

### P1 — The downstream contract reintroduces the rejected readiness gate

The controlling evidence-only design removes `COMPONENTS_READY` and
`COMPONENTS_ABSTAIN`, says warnings are diagnostic features only, and states
that absence of a warning is never semantic trust. The tracked detailed
post-Stage-7 architecture nevertheless instructs Stage 8 to map components
only when `COMPONENTS_READY`, describes the result as trusted mapped
components, and instructs later hypothesis generation to use only ready parser
components. It also still names fresh readiness validation as the next task.

This is not harmless history: `docs/PIPELINE.md` links that report as the
detailed source for the proposed Stage 8 responsibilities. A downstream
implementer therefore receives mutually exclusive contracts, and could either
depend on a field that evidence-only v2 does not publish or recreate the failed
semantic-trust gate. Independent-review check 10 fails.

### P1 — Current Stage 7 status and sanitized reports contradict each other

The evidence-only DEVELOPMENT report and progress index say the candidate is
ready for independent review. Other current-facing tracked surfaces say Stage
7 is not ready, that its contract/implementation remain unfrozen, or that no
candidate is eligible for independent review. These include the stage-record
status header, the stage index, the current execution-policy boundary, the
generic Stage 7 DEVELOPMENT candidate report and companion JSON, and the
post-Stage-7 architecture report and companion JSON.

Earlier not-ready decisions must remain preserved, but these files present the
old result as current rather than clearly superseded history. The repository
therefore has no single reliable current Stage 7 status or downstream handoff.
Independent-review check 12 fails.

## Checks completed before the material stop

- Read the exact two-commit candidate range and complete new implementation,
  CLI, launcher, tests, design report, and DEVELOPMENT report.
- Candidate-focused synthetic tests passed: 6/6.
- Ruff, strict mypy for the two new Python source files, shell syntax, JSON
  syntax, and `git diff --check` passed.
- Static inspection found no libpostal parser entry point in the v2 projection.
- The failed fresh-readiness report, its Markdown companion, and the frozen
  readiness implementation retain identical Git blobs between the failed-rule
  evidence commit and the reviewed candidate.
- The projection implementation is streaming and its synthetic tests exercise
  exact Stage 6 fields, ordered duplicate raw components, empty parses,
  map-back, artifact mutation, output collision, HOLDOUT rejection, and
  batch/shard logical invariance.
- The broader local-safe suite produced 567 passes and 24 failures; all 24
  observed failures were the repository's intentional pinned-Python runtime
  guard under the unpinned Mac interpreter, not evidence-only v2 failures.

Because checks 10 and 12 are material failures in the exact reviewed SHA, the
review does not claim independent confirmation of the protected 51,779-row
artifact. Stage 7 returns to DEVELOPMENT. This report changes no Stage 7
science and proposes no repair.

