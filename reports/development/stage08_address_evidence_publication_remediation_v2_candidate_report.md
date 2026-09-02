# Stage 8 second-remediation DEVELOPMENT candidate freeze

Current verdict:
`STAGE08_ADDRESS_EVIDENCE_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REREVIEW`.

The frozen candidate is exact executable
`bdea7232a3f92ebd381be87610b753b8e4c35481`, Goethe-NHR job `1764219`,
output
`/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage08/development/stage08_development_20260902T112644Z_bdea7232a3f9`,
manifest `346ea27ad60c1e00ef29c1126b2744f38049c1fa7d062647ab6df04e3330dee6`,
and logical dataset
`9c9d431c2c1b92712e0cb372f2661ad48f4fe8758dc0327d25aef90ab2c2d526`.

The [execution report](stage08_address_evidence_publication_remediation_v2_development.md)
freezes the accepted Stage 7 manifest `f5841087…`, accepted Stage 6 manifest
`e1da7b8…`, full upstream identities, runtime, resource accounting, scientific
fingerprints, relation-logical fingerprints, topology, publication state,
permissions, aggregate reconciliation, and privacy evidence.

The artifact contains 51,779 candidates, 6,106,088 ordered parser components,
35,000 source rows, and 69,747 occurrences: 34,822 STANDARD and 34,925 NATIVE.
Dangling components, component-count mismatches, occurrence-count mismatches,
unmapped components, parser calls, reference lookups, network calls, semantic-
trust fields, HOLDOUT access, and production access are all zero. Every frozen
scientific validation field passes.

The contract `8b3c530e…`, schema bundle `6c8ebecd…`, mapping `b18167d2…`, all
four schema fingerprints, all four relation-logical fingerprints, exact
20-label mapping, Stage 6/7 bindings, semantic classes, and candidate/
component/source/occurrence grains match the preceding scientific projection
exactly. The shared logical dataset SHA also matches historical jobs `1763747`
and `1763984`. The narrow conclusion is only that neither publication repair
altered Stage 8 science; neither historical job validates executable
`bdea7232…`.

Job `1764219` followed the ordinary successful publication path. Complete
prepublication reopen validation preceded terminal success; the temporary tree
was ready and fsynced before atomic rename; parent-directory fsync completed;
and immediate final reopen validation passed before success returned. The
success marker exactly binds the manifest and scientific identities,
`_IN_PROGRESS` is absent, no incomplete sibling remains, and stderr is empty.
All eight directories are `0700`; all 52 files are `0600`; symlinks are zero;
atomic and owner-only publication claims pass.

The policy-A post-effect rename adoption path was not fault-injected in this
protected run. The real-rename-then-raise boundary, failed adoption, fatal
parent-fsync/postpublication validation, partial/idempotent demotion, all four
path states, symlink non-following, unrelated-publication preservation, and
normal publication remain covered by the 28-test local Stage 8 suite. Fresh
independent rereview must challenge the adoption logic again.

Runtime and resource evidence is Python 3.14.3, Unicode 16.0.0, PyArrow 25.0.0,
DuckDB 1.5.5, four requested CPUs, 32 GiB, DuckDB four threads/8GB, 15m10s
elapsed, `0:0`, and MaxRSS 1,785,464 KiB. `AllocCPUS=80` is exclusive-node
allocation behavior, not application concurrency.

Local finalization passed the 28-test Stage 8 suite, 54 relevant Stage 7 tests,
six runnable earlier atomic-publication regressions, Ruff, changed-file format,
strict mypy over the established 98 source/Stage 8 targets, shell syntax, JSON,
Markdown local links, diff, privacy/tracked-data, executable blob identity,
scientific fingerprint, candidate/report consistency, and Git ancestry/status
checks. Selected Stage 4–6 publication tests stop only at the unchanged exact
Python 3.14.3 guards on local Python 3.14.7; no guard was weakened.

Original executable `a2544401…`, job `1763747`, the first independent-review
failure, first remediation `bd89a032…`, job `1763984`, the failed independent
rereview and exact post-effect rename blocker, second remediation `bdea7232…`,
policy A, and job `1764219` remain distinct truthful history. No historical
artifact is called corrupt and no previous failure is rewritten as success.

No additional controlled job, protected row-level inspection, HOLDOUT,
production, parser, reference, geocoder, DeepParse, Senzing, Stage 9,
implementation change, science change, merge, or independent review occurred
during this freeze.

Exact next action: **FRESH INDEPENDENT STAGE 8 REREVIEW OF THE BDEA7232
REPAIRED CANDIDATE.**
