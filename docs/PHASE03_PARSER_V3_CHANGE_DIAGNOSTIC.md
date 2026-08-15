# Phase 3 Parser-v3 DEVELOPMENT change diagnostic

## Status and scope

Goethe job `1749345` stopped before creating a targeted human-review workspace
because the computed review population was 28 rather than the reviewed expected
count of 26. The observed aggregate decomposition was:

- 26 DEVELOPMENT rows with a difference in `CORE_COLUMNS[5:41]` (set A);
- 11 DEVELOPMENT rows with either experimental v4 rule in evidence (set B);
- 9 rows in both sets;
- 17 rows only in A;
- 2 rows only in B; and
- 28 rows in the deduplicated union.

The mismatch is not resolved by changing the expected count. Version
`phase03_parser_v3_change_diagnostic_v2` explains the two non-overlap
populations from the already completed 8,000-row Parser v2 and Parser v3 core
and evidence outputs. It does not rerun either parser, pilot selection, or Phase
2; read human labels; create a review workspace; or access LOCKED_EVALUATION.

## Frozen definitions

The diagnostic deliberately reuses the exact scientific-change definition
already shared by the v2-v3 aggregate comparison and targeted-review
preparation:

```text
CORE_COLUMNS[5:41]
```

Those 36 fields include selected native and non-native values, country
classification, parse status and completeness, conflicts, diagnostics,
selected-component provenance, native/non-native relationships, evaluation and
safety state, address-role indicators, and maximum input size. Provider/source
identity and parser/configuration metadata outside this slice are not scientific
change fields.

Set B remains the identity-level union of evidence from exactly:

- `HOUSE_NUMBER_EMBEDDED_DESIGNATOR_EXPERIMENT_V4`; and
- `STREET_EMBEDDED_DESIGNATOR_EXPERIMENT_V4`.

The production command asserts all seven observed counts—8,000, 26, 11, 9,
17, 2, and 28—before writing a report. It does not modify the separate
targeted-review expected-count gate.

Goethe job `1749435` independently confirmed all seven counts, then exposed an
invalid diagnostic-only assumption: separate aggregate totals of nine selected
house candidates and nine selected street candidates do not prove that both
rules occur and are selected on the same nine identities. Version 1 therefore
stopped on `OVERLAP_EXPERIMENTAL_EVIDENCE_NOT_PAIRED_AND_SELECTED` before it
could report the changed-only field decomposition. Version 2 removes that
unproved invariant. Presence and selection pairing are measured as diagnostic
results; none is assumed.

## Sanitized output contract

The diagnostic produces two owner-only files:

- `phase03_parser_v3_change_diagnostic.json`; and
- `phase03_parser_v3_change_diagnostic.md`.

The JSON contains:

- report/diagnostic versions and status
  `SANITIZED_DEVELOPMENT_V3_CHANGE_DIAGNOSTIC_ONLY`;
- the A/B/overlap/changed-only/evidence-only/union/neither counts;
- exact per-field and fixed-family change counts for overlap, changed-only, and
  evidence-only populations;
- a changed-only field-combination table with a five-row minimum, 32-row-table
  cap, and explicit suppressed-combination/row residuals;
- aggregate provenance, representation, conflict, diagnostic, completeness,
  evaluation, and safety changes;
- per-population V4 presence topology (both rules, house only, or street only)
  and independent selection topology (both selected, either asymmetric
  selection, both unselected, or multiple candidate-group state), with counts
  from one to four suppressed;
- one bounded root-cause classification or an explicit insufficient-evidence
  result;
- input byte sizes and SHA-256 values keyed only by logical artifact role; and
- implementation/report fingerprints and explicit privacy/boundary fields.

The output contains no raw values, stable/provider/review identities, source
files, source ordinals, paths, candidate text, spans, human labels, or per-row
results. Fixed schema fields, vocabulary categories, and the two predeclared
experimental rule IDs are the only reported names. Rare changed-field
combinations are suppressed rather than emitted as unique structural
fingerprints. Frequency is not scientific correctness and the diagnostic
applies no promotion or review threshold.

The original diagnostic regression fixture contained 12 rows, not 500. Its
five overlap rows were generated from one symmetric non-native Parser-v3 form,
so both V4 rules were always present and selected together; its one
evidence-only row also emitted the same paired rules. The fixture therefore
encoded, rather than tested, the invalid pairing assumption. Version 2 adds
asymmetric one-rule, one-selected, neither-selected, repeated-span, and
multiple-candidate-group fixtures. Any unrelated 500-row tests in the
repository exercise sampling caps, not this evidence topology.

## Fail-closed validation

Production execution requires both `SAFE_EXECUTION_SITE=goethe-nhr` and a
non-empty `SLURM_JOB_ID` before any input filesystem access. Inputs must be
readable, non-symlink files below the canonical controlled Phase 3 root. Both
lexical and resolved paths containing `locked` are rejected. The identity file
must declare `DEVELOPMENT`, contain exactly 8,000 unique identities, and match
both core files in the same order.

The tool validates exact schemas, page checksums, Parser v2/v3 and registry
roles, uniform configuration fingerprints, core/evidence relationships, and
source provenance. It hashes all five read-only inputs before and after
analysis. A changed input, count mismatch, schema/role mismatch, or evidence
orphan fails before sanitized output is promoted.

## Goethe-NHR execution plan

Run only from a clean detached integration worktree at the exact reviewed
diagnostic commit. The dedicated job requests one node, two CPUs, 8 GiB RAM,
and one hour. It reads about 16,000 core rows plus the two existing evidence
sidecars and the DEVELOPMENT identity set; it does not read the Phase 2 payload
or scan 20.6 million rows.

After the reviewed commit is available on Goethe, prepare variables without
changing any preserved artifact:

```bash
ssh goethe

DATA_ROOT="/work/footprint/donyadidegan/safe_geocoding_pipeline"
PHASE03_GIT_COMMIT="<exact-reviewed-diagnostic-commit>"
PHASE03_INTEGRATION_ROOT="${DATA_ROOT}_v3_change_diagnostic_${PHASE03_GIT_COMMIT:0:12}"
SOURCE_RUN_ROOT="${DATA_ROOT}/derived/controlled/phase03_v1/pilots/.in_progress/phase03_pilot_goethe_20260813T224643Z_1748630_750a1655"
PARSER_V2_ITERATION="${DATA_ROOT}/derived/controlled/phase03_v1/development_iterations/phase03_development_parser_v2_20260814T134743Z_1748928_06acc59e"
PARSER_V3_ITERATION="${DATA_ROOT}/derived/controlled/phase03_v1/development_iterations/phase03_development_parser_v3_experimental_20260815T174529Z_1749335_fa3b9246"

git -C "${DATA_ROOT}" fetch --prune origin
git -C "${DATA_ROOT}" cat-file -e "${PHASE03_GIT_COMMIT}^{commit}"
git -C "${DATA_ROOT}" worktree add --detach \
  "${PHASE03_INTEGRATION_ROOT}" "${PHASE03_GIT_COMMIT}"
test "$(git -C "${PHASE03_INTEGRATION_ROOT}" rev-parse HEAD)" = "${PHASE03_GIT_COMMIT}"
test -z "$(git -C "${PHASE03_INTEGRATION_ROOT}" status --short)"

PHASE03_DEVELOPMENT_IDENTITIES="${SOURCE_RUN_ROOT}/selection/development.identities.bin"
PHASE03_PARSER_V2_CORE="${PARSER_V2_ITERATION}/transformed/core/development.parquet"
PHASE03_PARSER_V2_EVIDENCE="${PARSER_V2_ITERATION}/transformed/evidence/development.parquet"
PHASE03_PARSER_V3_CORE="${PARSER_V3_ITERATION}/transformed/core/development.parquet"
PHASE03_PARSER_V3_EVIDENCE="${PARSER_V3_ITERATION}/transformed/evidence/development.parquet"

cd "${PHASE03_INTEGRATION_ROOT}"
export PHASE03_GIT_COMMIT PHASE03_INTEGRATION_ROOT
export PHASE03_DEVELOPMENT_IDENTITIES
export PHASE03_PARSER_V2_CORE PHASE03_PARSER_V2_EVIDENCE
export PHASE03_PARSER_V3_CORE PHASE03_PARSER_V3_EVIDENCE
sbatch --export=ALL \
  cluster/goethe_nhr/phase03_parser_v3_change_diagnostic.sbatch
```

Successful output is atomically promoted beneath:

```text
reports/generated/phase03/parser_v3_change_diagnostics/
```

The diagnostic must be inspected before deciding whether 28 is the correct
review population or whether either change definition has an implementation
issue. Do not initialize the human-review workspace, change the expected count,
or promote Parser v3 automatically.
