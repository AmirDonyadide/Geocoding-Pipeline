# Stage 10 independent-review remediation

Owner authorization, 2026-09-24: remediate **C01 and C02 together**, then submit
exactly one new immutable DEVELOPMENT candidate with 4 CPUs, 32 GiB and 36 hours.
No scientific redesign, performance experiment, operating-budget selection or
later-stage work is authorized. Stage 10 remains unaccepted.

## Accepted review and preserved history

The completed independent review is bound to branch
`review/stage10-independent-20260923`, evidence commit
`bced5920b5234e5598f1d0b3a4cb1269780862f4`, and jobs **1780706 / 1781037**
(COMPLETED / 0:0). It completed 22 areas: 212 passing checks, three failures
mapping to exactly two candidate defects. The review branch is unchanged.

Historical candidate **1774362**, executable
`63f3cd107e69c9ddc14b9b517b0c7ab3d5861e66`, reporting
`e7fe4878f585c0283e57edee16f64883b8f8f758`, remains immutable at:
`/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage10/development/stage10_development_20260921T112356Z_63f3cd107e69`.
Manifest `085b05f6201831de6aa908c599bb5541a85cc185a48022d2d93d1e0a9afcc3fa`;
logical dataset `70abebdaeee44cf0eae09eb89e4ed68ef087f1596bfa86ea1bef6aef57ceed92`.
Its [original report](STAGE10_DEVELOPMENT_1774362.md) remains the historical
pre-review checkpoint. It cannot be accepted or adopted as the corrected candidate.

The review found no additional scientific-content, integrity or privacy defect
within its scope. Review-harness R01–R05 were separately corrected. I01–I08 remain
informational: country abstentions reconcile; zero Q5/Q6 coexistence is permitted;
Q5 precedence overlap is zero; three replays support reproducibility alongside
independent checks; DEVELOPMENT is not production-capacity evidence; pinned Goethe
ICU covers local runtime skips; independently checked certificates matched; and
reports make no accuracy/validity claims or operating-budget selection.

## C01: existing Q4 field-slot provenance

The normative [Q4 contract](STAGE10_QUERY_FAMILIES.md#q4--source-anchored-structured-hypothesis)
requires visible `PARSER_ONLY_FIELD_EXCLUDED`. The
[data contract](STAGE10_DATA_CONTRACT.md) defines exactly six Q4 FieldDecision
slots: address, postalcode, locality, region, country, boundary_country. There is
no parser-token decision relation and no optional concordance metric in v1.

The correction adds the missing reason once to every **OMIT geographic slot**
(postalcode, locality, region, country). It records that parser-only evidence
cannot fill this slot. This is an unconditional exclusion policy at the existing
field grain, as recognized by the accepted review; it does not classify a source
value as parser-only and does not claim that a parser token was observed.

- Included source fields retain their original INCLUDE decisions and reasons.
- A missing/unsupported/contradicted source field retains its original gate
  reason; the additional reason explicitly excludes filling the gap from parser
  evidence. A source postcode contradiction remains `CONTRADICTION_GATE`.
- Region retains `ADMIN_LEVEL_NOT_ESTABLISHED`; country text remains omitted
  because the boundary supplies source-country context. Both make the
  parser-only exclusion explicit.
- Common country-gate failure retains six NOT_APPLICABLE slots with no attempted
  field exclusions. Whole-family reasons, status and eligibility do not change.
- Duplicate parser components produce no duplicate decision. No parser values
  are scanned, matched, trusted or promoted to decide Q4. Exact upstream component
  lineage remains reachable through the existing candidate/snapshot identity.

This interpretation preserves the field decision's source/reference meaning:
`PARSER_ONLY_FIELD_EXCLUDED` explains the forbidden parser fallback in an omitted
slot; it never appears on an included source-anchored field. The audit separately
reports actual parser-geography incidence. It does not confuse policy counts
with observed token counts or infer geographic authority from parser labels.

### Identity domains

The frozen context, intent, hypothesis and family-decision ID formulas bind
upstream/scientific identities and context/family or intent, not executable SHA
or the FieldDecision payload. Their values stay unchanged. Query hypotheses,
all Q1–Q6 payloads, eligibility, membership and convergence remain identical.
Only the required field-reason values change in the decision relation. Therefore
its logical fingerprint, dependent summary/dataset/physical inventories,
manifest and publication record change. All contract/profile/schema/spec/runtime
fingerprints stay unchanged. No frozen design file is edited.

## C02: publication adapter

The active namespace and manifest kind are now exactly
`STAGE10_DEVELOPMENT_QUERY_PLAN`; registration uses exactly
`stage10_input_binding_sha256`. Terminal validation rejects the former namespace
at every state, and reopen requires byte-exact corrected registration.
The portable registration hash remains the accepted
`SHA256(b"SAFE:publication-commit:v2\0" + canonical({protocol, bindings}))`
(the domain terminator is the NUL byte). The adapter's corrected binding values
participate in that hash. No Stage 9 adapter or primitive changes.

Permanent reservation → immutable validated artifact → registration → exclusive
`_COMMITTED` → reopen remains intact. Old names remain only in historical
records and deliberate rejection fixtures, never in active new registration.

## Validation and complete bounded self-review

| Item | Disposition |
|---|---|
| C01 — CANDIDATE_IMPLEMENTATION | FIXED in code; six existing field slots, ordered unique reasons, included source fields unchanged; awaiting new immutable output reconciliation. |
| C02 — CANDIDATE_PUBLICATION | FIXED in code; exact names/domain and all-state/reopen rejection tested; awaiting new P11 publication. |
| M01 — historical performance goldens assume absent C01 provenance | FIXED in tests only: remove exactly the authorized field reason for old scientific projections; preserve byte-exact hypothesis equality and all other fields. Historical confirmation guards continue to reject this new executable. No diagnostic is rerun. |
| M02 — remediation audit's initial SQL had an ambiguous source join | FIXED before submission with an explicit source FK and a complete real-Parquet setup/read/hash/comparison test. |
| M03 — audit's initial external-access setting also blocked local Parquet | FIXED before submission by reusing the accepted bounded local connection and offline network guard. Full audit test executes the actual path. |
| M04 — synthetic corruption fixtures needed canonical ordering/mutable containers | FIXED in fixtures; injected content/provenance/context corruption now reaches the intended closed audit failures. |

The review covered field/context scope, parser trust leakage, repeated components,
source/reference gates, reason ordering, IDs, convergence, Q1–Q6 content,
registration naming/hash domain/reopen, privacy, bounded comparisons, performance
architecture, checkpoint/resume and historical immutability. No new scientific
candidate defect was found. Code changes in the generator are limited to the
seven-line field-provenance addition; the source/reference eligibility evaluator,
Q5/Q6, runtime, context/certificate/checkpoint code are unchanged.

The synthetic comparison executes the exact pinned pre-repair `_structured`
function (source SHA-256
`aca6b2230a903666bbf8825530f9b8877897362244c1a7b908b8080ce0b5fa64`)
across STANDARD/NATIVE, available/unavailable country and all locality/postcode
inclusion combinations. Entire hypotheses and all non-C01 decision contents
match exactly. Existing multi-context/certificate/partition tests independently
compare to the historical executable after only the authorized reason projection.

## One candidate and same-allocation audit

[Remediated launcher](../../cluster/goethe_nhr/stage10_remediated_development.sbatch)
invokes the established guarded launcher once, with the approved 36-hour SLURM
request. It then runs a read-only aggregate audit in that same allocation.
There is no second submission, diagnostic, performance confirmation, generation
or scientific replay in the audit. The existing candidate protocol alone performs
its three required replays. No completed checkpoint from the failed-review
executable is adopted under the new executable binding.

The [audit](../../src/safe_geocoding_pipeline/preprocessing/stage10_remediation_audit.py)
checks the pinned historical manifest and current corrected committed artifact,
hashes all compared relation files, recomputes both relation fingerprints and
compares full hypotheses in both directions with `EXCEPT ALL`. It independently
constructs required field provenance from the old independently validated field
gates, checks all remaining decision fields exactly, confirms source-payload
anchoring, and reports missing/duplicate/incorrect-scope counts. Actual parser
geography is counted from the accepted Stage 8 typed evidence, with distinct
candidate/field associations so repeated components cannot inflate field counts.
These associations are diagnostics only, never query-generation inputs.

The audit writes only sanitized aggregates and relation fingerprints to a new
sibling `<publication-key>_remediation_audit.json`. It cannot rewrite either
artifact. Bounded DuckDB/Arrow mechanisms are reused, with a private disk/spill
workspace, disabled extension downloads/HTTP filesystem and the shared pre-input
SLURM guard. Static failure output contains no engine exceptions or query values.
Audit failure is not candidate readiness, even if generation/publication passed.

Successful reconciliation requires identical old/new query hypotheses and
scientific decision projections, corrected decision fingerprints, zero missing
or duplicate provenance, exact corrected registration/domain, and the normal
Stage 10 full validation. Expected historical aggregate counts are diagnostics,
not hard-coded production eligibility. Unexpected content drift fails closed.

No protected payload has been accessed locally. Stage 0–9 unchanged; HOLDOUT
sealed; production/Pelias untouched; Stage 11 NOT STARTED. Scientific operating
budget **UNSELECTED**. Stage 10 **NOT YET ACCEPTED**.

## Local validation checkpoint

The safe Python 3.14.3 / DuckDB 1.5.5 suite passed **1132 tests**, with 24
explicit exact-ICU skips. One additional matching-parser/source-postcode test
was then added and passed in the focused run: **297 Stage 10 tests passed**,
24 exact-ICU skips. These include 45 new remediation/audit tests. The pinned
Goethe ICU/runtime-lock gates and the independent review's I06 conclusion remain
controlling; no replacement runtime was built or substituted.

Strict mypy passes **139 explicitly checked files**, using the established
`--follow-imports=silent` scope for historical imported test fixtures. An initial
broad import-following run reported 44 pre-existing Stage 9 test-fixture typing
diagnostics plus one new test return annotation; the new diagnostic was fixed.
No accepted Stage 9 test was changed. Maintained-tree Ruff lint/format, frozen
design/schema/profile/runtime-lock and refreshed implementation inventory,
stage-report validator, CLI help, shell syntax, links/anchors and diff checks
pass. All new fixture values are invented or public source code; no row-level
protected payload, output, log, runtime binary or local cache is tracked.
