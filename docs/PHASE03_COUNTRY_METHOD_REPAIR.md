# Phase 3 country-method reproducibility repair

## Status and scope

Goethe diagnostic job `1749446` established that all 17 Parser-v2/v3
changed-only DEVELOPMENT rows had the controlled-vocabulary transition
`STRUCTURED_COUNTRY_NAME_EXACT -> STRUCTURED_ALPHA2_EXACT`. The selected
country value, class, confidence, evidence semantics, provenance, and every
other scientific-core field were identical. This is a shared reproducibility
defect, not a Parser-v3 country-rule change.

The repaired lineages are:

- baseline `conservative_address_parser_v2_1`, still paired with the unchanged
  `phase03_rule_registry_v3`;
- experiment `conservative_address_parser_v3_1_experimental`, still paired
  with the unchanged `phase03_rule_registry_v4_experimental`.

The historical `conservative_address_parser_v2` iteration `1748928`,
`conservative_address_parser_v3_experimental` iteration `1749335`, and all
failed/diagnostic artifacts remain immutable. The package and sealed pilot
defaults remain Parser v1. No selection, identity, schema, rule, safety limit,
or LOCKED_EVALUATION contract changes.

## Defect and deterministic semantics

The historical `_country_result()` collected reference kinds from every
same-value country candidate. That set could contain the selected structured
`ALPHA2` route and an unselected free-form `NAME` route. Calling
`next(iter(kinds_for_value))` therefore made `country_parse_method` depend on
Python hash/set iteration.

The repaired lineages retain the exact reference kind keyed by rule, source
field, and canonical country value. Once country selection is complete, the
method is derived only from the selected component's rule IDs, source field,
and value:

- selected `country_iso_code` + `ALPHA2` -> `STRUCTURED_ALPHA2_EXACT`;
- selected `country_iso_code` + `ALPHA3` -> `STRUCTURED_ALPHA3_EXACT`;
- selected `country_iso_code` + canonical `NAME` ->
  `STRUCTURED_COUNTRY_NAME_EXACT`.

Candidate-only free-form evidence cannot influence this route. A repaired
parser fails with `COUNTRY_SELECTED_SOURCE_METHOD_UNRESOLVED` unless the
selected single-source route resolves to exactly one kind allowed by its
structured/free-form method mapping. Existing explicit multisource agreement,
corroborated `Na`/Namibia collision, unresolved, and conflict paths retain
their registered behavior. Historical executable behavior remains reproducible
from its exact Git commits and immutable artifacts; all parser invocations in
the repaired code use deterministic derivation, and production reruns must use
the new identifiers so the changed scientific lineage is explicit.

## Frozen identities

| Role | Identity |
|---|---|
| Parser-v2.1 base configuration | `a17d6be788f41dc07f3cd1b8041e60d034decd6f90a3bb058d66b13d18f44192` |
| Parser-v2.1 production-reference effective configuration | `25962a126cd5d30c13607bd564aa250e91096e6961745670772a1ce31b76ac4d` |
| Parser-v2.1 registry | `phase03_rule_registry_v3`, SHA-256 `a2aadae857b7d4bf7262bd37e6dacf58aae220e00b402ca971c51cea320d6f55` |
| Parser-v3.1 base configuration | `52f36ba37a218d6465eb314428bbfadb63cc7f34c0703b76907751f7908bfe17` |
| Parser-v3.1 production-reference effective configuration | `50e06ad6d7ad428811bdefe30ed6ef7e0d6b9eacbbbdce9a53c6809fd812333a` |
| Parser-v3.1 registry | `phase03_rule_registry_v4_experimental`, SHA-256 `2137c4a78cd062aa6f07784deea6046824e99ed7712a591d841e142d2f49dfc5` |

The new parser identifiers deliberately change configuration fingerprints.
The component/evidence schemas and both registry artifacts are unchanged.
Core semantic digests are expected to change where the repaired method differs
and wherever Parser v3.1's unchanged V4 experiment changes scientific output;
metadata-bound digests also bind the new parser/configuration identities.

## Historical and future comparison gates

The historical observed counts remain evidence and are not rewritten:

- scientific changes 26;
- experimental-evidence identities 11;
- overlap 9;
- changed-only 17;
- evidence-only 2;
- union 28.

The post-repair hypothesis is 9 scientific changes, 11 experimental-evidence
identities, overlap 9, changed-only 0, evidence-only 2, and union 11. These are
not hard-coded as success criteria. The repaired comparison requires exact
ordered identities, source provenance, schemas, page checksums, semantic
digests, configuration roles, and core/evidence relationships, then reports
the measured aggregates without a promotion decision. The existing targeted
review expected-count gate is unchanged pending those measured results.

## Goethe-NHR execution plan

Run only from a clean detached worktree at the exact reviewed repair commit.
The single scheduled job reuses the existing 8,000-row DEVELOPMENT payload and
identity set, executes Parser v2.1, executes Parser v3.1 on the same rows, then
runs the repaired-role comparison. It never runs pilot selection, scans the
20.6M-row snapshot, creates review material, or reads LOCKED_EVALUATION.

Read-only inputs:

```text
/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/phase03_v1/pilots/.in_progress/phase03_pilot_goethe_20260813T224643Z_1748630_750a1655/development/payload/development.parquet
/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/phase03_v1/pilots/.in_progress/phase03_pilot_goethe_20260813T224643Z_1748630_750a1655/selection/development.identities.bin
```

The script writes a new immutable
`phase03_development_country_method_repair_<timestamp>_<job>_<commit>`
iteration under `development_iterations/`, outside the preserved pilot run.
It hashes both inputs before and after, validates exact Python/Unicode,
references, registries, and configuration fingerprints, and promotes outputs
only after both transformations and comparison succeed. Requested resources
are one node, four CPUs, 16 GiB RAM, and four hours; the implementation remains
primarily single-process.

Submission template (replace `<REVIEWED_COMMIT>` only after review):

```bash
DATA_ROOT=/work/footprint/donyadidegan/safe_geocoding_pipeline
INTEGRATION_ROOT=/work/footprint/donyadidegan/safe_geocoding_pipeline_country_method_repair_<REVIEWED_COMMIT>
SOURCE_RUN_ROOT=${DATA_ROOT}/derived/controlled/phase03_v1/pilots/.in_progress/phase03_pilot_goethe_20260813T224643Z_1748630_750a1655

cd "${DATA_ROOT}"
git fetch --prune origin
git worktree add --detach "${INTEGRATION_ROOT}" <REVIEWED_COMMIT>
cd "${INTEGRATION_ROOT}"
test "$(git rev-parse HEAD)" = <REVIEWED_COMMIT>
test -z "$(git status --porcelain)"

sbatch --export=ALL,PHASE03_GIT_COMMIT=<REVIEWED_COMMIT>,PHASE03_INTEGRATION_ROOT="${INTEGRATION_ROOT}",PHASE03_SOURCE_RUN_ROOT="${SOURCE_RUN_ROOT}",PHASE03_DEVELOPMENT_PAYLOAD="${SOURCE_RUN_ROOT}/development/payload/development.parquet",PHASE03_DEVELOPMENT_IDENTITIES="${SOURCE_RUN_ROOT}/selection/development.identities.bin" cluster/goethe_nhr/phase03_country_method_repair.sbatch
```

Do not submit this workflow until separately authorized.
