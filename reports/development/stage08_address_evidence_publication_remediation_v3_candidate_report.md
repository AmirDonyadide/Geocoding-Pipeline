# Stage 8 third-remediation DEVELOPMENT candidate freeze

Current verdict:
`STAGE08_ADDRESS_EVIDENCE_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REREVIEW`.

The frozen candidate is exact executable
`c04cb97214a9f1e5d2b80512c756400321eefa80`, Goethe-NHR job `1764273`,
output
`/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage08/development/stage08_development_20260902T132726Z_c04cb97214a9`,
manifest `2a50bd8c066552c9cb7505ed2d6071f1ee36161b9a2cc07f3ed364cf00237827`,
logical dataset
`9c9d431c2c1b92712e0cb372f2661ad48f4fe8758dc0327d25aef90ab2c2d526`,
and final filesystem identity
`(st_dev, st_ino) = (54, 9363000937145638642)`.

The [execution report](stage08_address_evidence_publication_remediation_v3_development.md)
freezes the accepted Stage 7 manifest `f5841087…`, accepted Stage 6 manifest
`e1da7b8…`, upstream identities, runtime, resource accounting, scientific and
relation-logical fingerprints, topology, v3 publication state, permissions,
aggregate reconciliation, and privacy evidence.

The artifact contains 51,779 candidates, 6,106,088 ordered parser components,
35,000 source rows, and 69,747 occurrences: 34,822 STANDARD and 34,925 NATIVE.
Dangling components, unmapped components, component-count mismatches,
occurrence-count mismatches, parser calls, reference lookups, network calls,
geocoder/external-service calls, semantic-trust fields, HOLDOUT access, and
production access are all zero. Every frozen scientific validation field is
`PASS`.

Contract `8b3c530e…`, schema bundle `6c8ebecd…`, mapping `b18167d2…`, all four
schema fingerprints, all four relation-logical fingerprints, exact 20-label
mapping, Stage 6/7 bindings, semantic classes, candidate/component/source/
occurrence grains, logical-hash rules, and the Stage 8/Stage 9 boundary remain
exactly unchanged.

Job `1764273` followed the **ORDINARY successful publication path**. Complete
prepublication validation, temporary-tree durability, atomic rename,
parent-directory fsync, complete final reopen validation, outcome construction,
and `umask` restoration all preceded the final no-follow device/inode ownership
verification. That final ownership gate passed, was the last rejection-capable
publication operation, and bound success to `(54, 9363000937145638642)`.
`_SUCCESS.json` exactly binds the manifest and scientific identities;
`_IN_PROGRESS` is absent; no incomplete sibling remains; stderr is empty. All
eight directories are `0700`, all 52 files are `0600`, symlinks are zero, and
atomic and owner-only publication claims pass.

The materializer return after the final ownership gate is the program-level
commit boundary. Publication and presentation are separate results:
post-commit serialization, stdout write/flush, stream-detachment, or secondary
stderr failure preserves exit zero and leaves FINAL untouched, while every
genuine prepublication failure remains nonzero. The first success-marker
repair, policy-A ambiguous-rename adoption, and the v3 CLI-status/final-
ownership repair are all present and locally regressed in the exact executable.

No synthetic failure was injected into the controlled job. Post-commit stdout
write/flush/serialization failure, real-rename-then-raise, byte-identical
different-inode replacement, and replacement during parent fsync/final reopen/
the instant before final ownership remain local synthetic evidence. Fresh
independent rereview must challenge them again.

Runtime and resource evidence is Python 3.14.3, Unicode 16.0.0, PyArrow 25.0.0,
DuckDB 1.5.5, four requested CPUs, 32 GiB, DuckDB four threads/8GB, 16m08s
elapsed, `0:0`, and MaxRSS 1,789,612 KiB. `AllocCPUS=80` is supported as
exclusive-node allocation by `general1 OverSubscribe=EXCLUSIVE` and the
assigned 80-CPU node; it is not application concurrency.

The logical dataset SHA matches jobs `1763747`, `1763984`, `1764219`, and
`1764273`. The narrow conclusion is only that all publication remediations to
date left the frozen Stage 8 scientific dataset unchanged. Every historical
job validates only its exact executable; no failed review is rewritten as
success and no historical artifact is called corrupt.

Local finalization passed all 45 Stage 8 tests, the 14 exact v3 critical cases,
all 149 Stage 7 tests, all 129 Stage 0–2 tests, Ruff, scoped format, strict
mypy, shell, JSON, Markdown links, diff, privacy, executable-identity,
fingerprint, report-consistency, and Git gates. The executable remains byte-
identical to `c04cb97214a9f1e5d2b80512c756400321eefa80`; Python 3.14.3 guards
remain unchanged under local Python 3.14.7.

No additional controlled job, protected row-level inspection, HOLDOUT,
production, parser, reference, geocoder, DeepParse, Senzing, Stage 9,
implementation change, science change, merge, or independent review occurred
during this freeze.

Exact next action: **FRESH INDEPENDENT STAGE 8 REREVIEW OF THE C04CB972
REPAIRED CANDIDATE.**
