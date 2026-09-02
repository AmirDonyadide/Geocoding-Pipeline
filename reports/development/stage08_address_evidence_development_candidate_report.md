# Stage 8 repaired DEVELOPMENT candidate freeze

Current verdict:
`STAGE08_ADDRESS_EVIDENCE_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REREVIEW`.

The authoritative repaired candidate is exact executable
`bd89a032eb6fcf16a7515e0bd2991165d87246b1`, Goethe-NHR job `1763984`,
output
`/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage08/development/stage08_development_20260902T080150Z_bd89a032eb6f`,
manifest `d521240b42a40b9c1408f0f7241583bc76b7779e4107179e73fdcb7c7a69e119`,
and logical dataset
`9c9d431c2c1b92712e0cb372f2661ad48f4fe8758dc0327d25aef90ab2c2d526`.

The [execution report](stage08_address_evidence_development.md) freezes the
exact accepted Stage 7/6 bindings, runtime, relation/schema identities,
topology, scheduler evidence, permissions, privacy evidence, and all scientific
reconciliation. It records 51,779 candidates, 6,106,088 ordered components,
35,000 source rows, and 69,747 occurrences (34,822 STANDARD; 34,925 NATIVE).
Dangling, unmapped, component-count-mismatch, and occurrence-count-mismatch
totals are zero; reversibility and every frozen validation field pass.

The repaired terminal transition is exercised successfully. Complete
prepublication reopen validation ran while `_IN_PROGRESS` existed and
`_SUCCESS.json` did not. The final success marker binds the manifest;
`_IN_PROGRESS` is absent only after terminal success; no incomplete sibling
exists; and post-publication reopen validation passed. All directories are
`0700`, all files `0600`, symlink count is zero, atomic and owner-only
publication claims pass, and stderr is empty.

Historical job `1763747` at rejected executable `a2544401…` has the same
logical dataset SHA. That equality shows the publication-state repair did not
alter the frozen scientific dataset; it does not make the old job validation
of repaired executable `bd89a032…`. Rejected reporting candidate `adde81d…`,
its independent-review failure, and both blockers remain immutable history.

The repaired executable is byte-identical to `bd89a032…`: the Stage 8
materializer, CLI, launcher, project dependency contract, and 17-test Stage 8
suite retain their exact executable-commit blobs. This finalization changes
only sanitized reports and current-status documentation.

Local finalization passed:

- Stage 8 focused tests: 17 passed;
- relevant Stage 7 regressions: 27 passed;
- Stage 2/cluster publication regressions: 14 passed;
- Ruff lint and the scoped Stage 8 format check passed;
- strict mypy passed over the established 98 source/Stage 8 targets;
- shell syntax, JSON validity, 60-file Markdown local links, diff hygiene,
  privacy/tracked-data, implementation-blob, and repository-state checks
  passed.

Nine selected Stage 3–6 publication diagnostics stopped only at their immutable
exact-Python-3.14.3 guards under local Python 3.14.7. The guards were not
weakened. Optional broad probes also retain pre-existing unrelated baselines:
19 nonchanged Python files are outside repository-wide Ruff formatting, and
ten unrelated Stage 6/7 test files contain 71 broad-mypy findings. Neither is
in the executable or reporting diff; the established required scoped gates
pass.

No second job, HOLDOUT, production, parser rerun, reference service, geocoder,
Stage 9 work, science change, or independent rereview occurred. This candidate
is not `STAGE_8_ACCEPTED`.

Exact next action: **FRESH INDEPENDENT STAGE 8 REREVIEW OF THIS REPAIRED
CANDIDATE.**
