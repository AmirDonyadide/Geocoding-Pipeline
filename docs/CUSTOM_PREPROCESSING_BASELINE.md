# Custom preprocessing baseline

## Role

This repository state preserves the historical custom preprocessing pipeline as
a benchmark baseline. Phase 1 inventory and Phase 2 lossless staging remain
reusable infrastructure. Phase 3 parsing, normalization, DEVELOPMENT work, and
LOCKED diagnostic history remain scientifically unchanged and available for
controlled comparison, but they are no longer the default future preprocessing
architecture.

Future preprocessing development is library-first and uses the distinct Stage
0–14 terminology. It proceeds one reviewed and accepted stage at a time. This
transition does not invalidate, rewrite, or delete earlier scientific history.

The annotated tag `baseline/custom-preprocessing-2026-08` identifies the exact
accepted baseline commit.

## Hardening boundary

The hardening branch started at
`0f29329a879dd43a239d571bc6a98ee25d547dfb`. Its permitted changes are limited
to historical test typing, validation policy, and general Git/worktree/transfer
governance. It does not modify parser source, normalization behavior, rule
registries, parser configuration or fingerprints, DEVELOPMENT sampling
contracts, LOCKED identity contracts, review labels, or generated scientific
artifacts.

All 28 initial mypy findings were test-typing maintenance defects: two incidental
re-export imports, two synthetic-fixture inference issues, and recursive JSON
values that tests had not narrowed before use. None required a source,
behavioral, scientific, or obsolete-contract change.

## Validation modes

Local-safe repository validation is:

```bash
python3 -m pytest -m "not requires_production_transfer_payload"
```

Four cluster-sync integration tests are explicitly deselected because their
real transfer-plan prerequisite is an ignored completed Phase 1/2 payload with
exactly 206 Phase 2 Parquet shards. Deselection is reported explicitly and is
not a pass.

Full-environment validation is:

```bash
python3 -m pytest
```

It includes those four tests. Missing or incomplete prerequisites fail; tests
are not automatically skipped and protected artifacts are never fabricated.

## Separate GitHub-first history

Commit `1efcc9e55f9b7b1c959112a965ecc1af36b14852` mixed generally useful
GitHub-first/data-transfer governance with dated Phase 3 operational reporting
and prospective SLURM notification changes. Only the general source-control,
ignore, documentation, and data-only transfer behavior is reproduced in the
hardened baseline. Dated scientific-state prose, review-state changes, and mail
directives are not imported.

Commit `61510ed92378e40c83d82fa1fe4b1a3c27519fcb` corrected two-sided canonical
path comparison for the DEVELOPMENT pattern profiler. That executable fix and
its synthetic regression coverage already exist in the baseline through
`9cd8b43cd8350ae1a396a7a9072989b011adcaa5`; they are not duplicated.
