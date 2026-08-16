# Phase 3 parser-v3 targeted DEVELOPMENT review

## Status and boundary

This workflow prepares a protected human review of the repaired narrow
`conservative_address_parser_v3_1_experimental` comparison against
`conservative_address_parser_v2_1`. It does not promote the experiment, alter
either parser, rerun pilot selection, inspect
LOCKED_EVALUATION, geocode, or create a production rule.

The authoritative repaired input is iteration
`phase03_development_country_method_repair_20260816T001155Z_1749448_e4a47253`,
SLURM job `1749448`, produced by repair commit
`e4a4725399a635476e7d97adcc8e446a592404cd`. Its aggregate comparison found nine
scientific-output changes and 22 candidate groups from each experimental rule
(nine selected and thirteen unselected per rule). Before preparation can create
any review artifact, a separate verification-only command must compute and
validate the exact identity-level population and write a sanitized passing
report. It creates neither review input nor reviewer database.

## Exact population

`phase03_parser_v3_targeted_review_v2_repaired` retains the exact deduplicated
union of:

1. every fixed DEVELOPMENT identity for which any Phase 3 scientific core field
   (the existing `CORE_COLUMNS[5:41]` comparison contract) differs between
   repaired v2.1 and v3.1; and
2. every fixed DEVELOPMENT identity with evidence from
   `HOUSE_NUMBER_EMBEDDED_DESIGNATOR_EXPERIMENT_V4` or
   `STREET_EMBEDDED_DESIGNATOR_EXPERIMENT_V4`.

The historical pre-repair comparison remains immutable audit evidence. Goethe
preparation job `1749345` stopped on an obsolete expected count of 26 because
the historical union was 28: 26 scientific-change rows, 11
experimental-evidence rows, nine overlapping rows, 17 change-only rows, and two
evidence-only rows. The 17 change-only rows were subsequently proved to be the
nondeterministic `country_parse_method` defect. Neither 26 nor 28 may be reused
for the repaired review population.

The repaired hypothesis is 9 scientific-change rows, 11 experimental-evidence
rows, nine overlapping rows, zero change-only rows, two evidence-only rows, and
11 identities in the union. It is encoded as a fail-closed verification
contract, not accepted merely from aggregate arithmetic. The production
preparer no longer accepts an operator-supplied population count. It requires a
passing `phase03_parser_v3_targeted_review_population_v2_repaired` report and
then independently recomputes the same A-union-B population with an exact
11-row gate. A mismatch produces no review input and no reviewer state.

The verifier pins the repaired job/iteration/commit, the fixed DEVELOPMENT
identity artifact, all four repaired core/evidence files, their byte sizes and
SHA-256 values, parser/configuration roles, page checksums, and the ordered
8,000-row identity digest. Its output contains aggregate counts and artifact
digests only: no paths, raw values, row identities, source spans, or candidate
values.

| Repaired artifact | Bytes | SHA-256 |
|---|---:|---|
| DEVELOPMENT identities | 256,414 | `cab12eb1c1c2f61b8bbc5b53dff604e7569233518e5fb3c88467d848e648d71a` |
| v2.1 core | 611,090 | `644b22865486c27ecb7bd15297fc131a7fa282758fb245bc8c6e885dacfecaf5` |
| v2.1 evidence | 551,140 | `0f7ddae89755f2d8c6d2973e09be4670e851fb58867d8233998d10aa23443baa` |
| v3.1 core | 611,424 | `1c6bc7ba74003b7910d3d83ce37e579e6182f0a4d227aea528b10165c2d50927` |
| v3.1 evidence | 552,394 | `89080a0656eb77b5813acd7735d8721370fa8dbca9ae71cde88aed9cc54b10fb` |
| repaired `_SUCCESS.json` | 1,388 | `5a8535984fe8bfce2dcf1e7dd8ec07c4478717490e17b8ce3ea4411a37df16e9` |
| repaired aggregate comparison | 7,260 | `2964f134ecc98994e9b6ee89a23766c2531224e960f0506691dbf1f94857df3f` |

The repaired core-order identity digest is
`4c3d34efd77b1af0774bd7eab0893c1e826ffd672d4fc13fc943bff1c4da1666`.
The baseline and experimental effective configuration fingerprints are,
respectively,
`25962a126cd5d30c13607bd564aa250e91096e6961745670772a1ce31b76ac4d`
and
`50e06ad6d7ad428811bdefe30ed6ef7e0d6b9eacbbbdce9a53c6809fd812333a`.

## Protected artifacts and provenance

The preparation job atomically promotes one owner-only review directory under:

```text
derived/controlled/phase03_v1/reviews/parser_v3_experimental/<review_id>/
```

It contains:

- `protected_targeted_review_context.parquet`: selected DEVELOPMENT raw context
  plus protected v2.1/v3.1 core/evidence JSON;
- `protected_targeted_review_template.parquet`: hashed review identities and
  the frozen independent-review designation;
- `targeted_review_input_manifest.json`: hashes, sizes, DEVELOPMENT identity
  digest, v2.1/v3.1 semantic/configuration/registry identities, repair and
  review commits, population-verification report identity, population digest,
  counts, and boundary declarations.

All files are mode `0600` and their directories are `0700`. Input artifacts are
hashed before and after preparation. The manifest contains no source paths, raw
values, provider/stable identities, evidence spans, or candidate values.
The sanitized preparation result uses promotion-stable references relative to
the targeted-review root; it never records a transient absolute
`.in_progress` path.

The three prepared input artifacts are immutable after promotion. The
preparation SLURM job creates no human labels or progress database. A later
explicit `initialize` command creates mutable Targeted-R01/Targeted-R02 SQLite
state in a separate owner-only `progress/` directory beneath the targeted
review root without modifying `prepared_inputs/`.

## Review schema

`phase03_parser_v3_targeted_review_labels_v1` is separate from and does not
modify `phase03_manual_review_labels_v1` or `phase03_manual_review_labels_v2`.
It contains:

| Column | Type | Meaning |
|---|---|---|
| `hashed_review_id` | string | Targeted-review pseudonymous identity |
| `experiment_iteration` | string | Frozen experimental iteration |
| `reviewer_id` | string | `Targeted-R01` or `Targeted-R02` only |
| `review_round` | uint8 | Exactly 1 |
| `is_independent_review` | bool | Always true for both records |
| `assignment_role` | string | `PRIMARY` or `INDEPENDENT_SECOND` |
| `street_label` | string | Existing component vocabulary |
| `house_number_label` | string | Existing component vocabulary |
| `joint_street_house_label` | string | `CORRECT`, `INCORRECT`, `NOT_APPLICABLE`, `CANNOT_ASSESS` |
| `residual_role_label` | string | Building/unit/floor/organization/other/unknown/no residual/uncertain |
| `candidate_support_label` | string | `SUPPORTED`, `NOT_SUPPORTED`, `NOT_APPLICABLE`, `CANNOT_ASSESS` |
| `blind_parse_comparison_label` | string | Parse A only, Parse B only, both correct, both incorrect, or uncertain |
| `parser_overreach_label` | string | Existing error-condition vocabulary |
| `missed_information_label` | string | Existing error-condition vocabulary |
| `overall_parse_acceptability_label` | string | Existing overall vocabulary |
| `reason_codes` | list<string> | Canonical `manual_review_reason_codes_v1` |
| version columns | string | Reason, label-vocabulary, and schema versions |

The existing component definitions distinguish `CORRECT`, `INCORRECT`,
`MISSED`, `NOT_PRESENT`, and `CANNOT_ASSESS`. Uncertainty requires
`SOURCE_AMBIGUOUS` or `INSUFFICIENT_SOURCE_EVIDENCE`. Missed components require
`MISSED_EXTRACTABLE_COMPONENT`; overreach and incorrect selections require an
applicable closed reason. `CORRECT_AS_IS` remains exclusive.
`OTHER_ADJUDICATION_REQUIRED` requires a protected note of at most 500 Unicode
characters. Notes remain only in SQLite and never enter label Parquet or
aggregate output.

The street and house-number labels assess the corresponding blinded candidate
hypotheses against the protected source. The joint label assesses the pair.
The neutral A/B label separately records whether either complete parser view is
preferable; the scorer unblinds that comparison only after both label sets are
complete.

## Independent blinding

Targeted-R01 and Targeted-R02 both review every affected identity. Their display
orders and A/B parse assignments are independently and deterministically derived from
`phase03_parser_v3_targeted_review_v1:seed:1`. The interface displays:

- protected source material;
- neutral `PARSE A` and `PARSE B` component/status views;
- neutral candidate hypotheses with candidate value, confidence, source field,
  and exact span;
- no parser version, registry/rule ID, or selected/rejected indicator.

The same operating-system account can deliberately inspect the underlying
protected Parquet, so this is procedural/tool-level blinding rather than
separate-account access control. The interface is the approved review path;
reviewers should not inspect the Parquet directly. Targeted-R01 and Targeted-R02
have separate SQLite databases and cannot see each other's labels through the
interface.

## Aggregate scorer

After both reviewers finish, the scorer can create one owner-only sanitized JSON
report. It unblinds deterministically and reports per reviewer:

- selected-row street, house-number, and joint exact correctness;
- incorrect and uncertain selected rows;
- correctly rejected, promotable, and uncertain rejected candidates;
- v2/v3 correctness cross-classification;
- component and joint precision numerators/denominators;
- false-positive and rejected-candidate false-negative-opportunity counts.

It also reports completion, exact field agreement, and the number of identities
requiring adjudication. It applies no promotion threshold. Protected labels
remain controlled on Goethe; only the aggregate score is eligible to leave the
controlled environment after an independent privacy check. The optional
`export-controlled-labels` Parquet is explicitly controlled and must not leave
Goethe because it contains hashed review identities; it is not a portable
aggregate report.

## Goethe-only execution plan

Identity verification is a separate SLURM step using one CPU, 8 GiB RAM, and a
30-minute limit. It reads only the fixed DEVELOPMENT identity file and the four
small completed v2.1/v3.1 core/evidence artifacts, and creates only a sanitized
aggregate JSON. Preparation remains a later separate SLURM step using 4 CPUs,
16 GiB RAM, and a one-hour limit. It additionally reads the existing 8,000-row
DEVELOPMENT payload only after the passing verification report is present. No
step scans Phase 2, reruns selection, or accepts a path whose resolved
components contain `locked`.

Use a clean detached integration worktree at the exact reviewed targeted-review
commit. Required production variables and commands are shown in the final
implementation report and in
`cluster/goethe_nhr/phase03_parser_v3_targeted_review_population_verify.sbatch`
and `cluster/goethe_nhr/phase03_parser_v3_targeted_review_prepare.sbatch`.

After preparation, enter separate SLURM compute-node sessions for
initialization and each human reviewer. The terminal interface uses curses and
falls back to standard input/output with `--line-mode`. No network, API, LLM, or
automatic label generation is present. Every real command other than the
privacy-safe `schema` command requires both `SAFE_EXECUTION_SITE=goethe-nhr` and
a non-empty `SLURM_JOB_ID` before opening its inputs, so it cannot run on a Mac
or Goethe login node.

## STOP gate

Do not prepare or initialize the real workspace until the verification-only
workflow has produced the exact 8,000/9/11/9/0/2/11 result from the immutable
repaired artifacts. This repository change does not execute that workflow.
After a separately reviewed passing report, preparation remains separately
authorized; initialization remains a later explicit action. Do not score until
both reviewers finish. Human evidence does not itself authorize promotion;
promotion criteria and any parser change require a separate scientific
decision.
