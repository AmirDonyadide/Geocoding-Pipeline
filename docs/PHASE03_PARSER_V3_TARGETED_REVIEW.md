# Phase 3 parser-v3 targeted DEVELOPMENT review

## Status and boundary

This workflow prepares a protected human review of the narrow
`conservative_address_parser_v3_experimental` comparison. It does not promote
the experiment, alter parser v2 or v3, rerun pilot selection, inspect
LOCKED_EVALUATION, geocode, or create a production rule.

The authoritative experimental input is iteration
`phase03_development_parser_v3_experimental_20260815T174529Z_1749335_fa3b9246`,
SLURM job `1749335`, produced by commit
`fa3b924657aed47bfe6aaa80d87353f8d9b78139`. Its aggregate comparison found 26
rows with a scientific-output change and 22 candidates from each experimental
rule (nine selected and thirteen unselected per rule). The review population is
computed, not assumed, and must pass an explicit expected-count gate before any
review artifact is created.

## Exact population

`phase03_parser_v3_targeted_review_v1` uses the deduplicated union of:

1. every fixed DEVELOPMENT identity for which any Phase 3 scientific core field
   (the existing `CORE_COLUMNS[5:41]` comparison contract) differs between v2
   and v3; and
2. every fixed DEVELOPMENT identity with evidence from
   `HOUSE_NUMBER_EMBEDDED_DESIGNATOR_EXPERIMENT_V4` or
   `STREET_EMBEDDED_DESIGNATOR_EXPERIMENT_V4`.

The implementation validates all 8,000 DEVELOPMENT identities, payload rows,
v2/v3 core rows, schemas, evidence relationships, page checksums, parser and
registry roles, source ordering, and hashes. The Goethe invocation supplies the
reviewed expected population (`26`). A mismatch fails with
`TARGETED_REVIEW_POPULATION_COUNT_MISMATCH` before an output directory exists;
the count is not hard-coded in the implementation.

## Protected artifacts and provenance

The preparation job atomically promotes one owner-only review directory under:

```text
derived/controlled/phase03_v1/reviews/parser_v3_experimental/<review_id>/
```

It contains:

- `protected_targeted_review_context.parquet`: selected DEVELOPMENT raw context
  plus protected v2/v3 core/evidence JSON;
- `protected_targeted_review_template.parquet`: hashed review identities and
  the frozen independent-review designation;
- `targeted_review_input_manifest.json`: hashes, sizes, DEVELOPMENT identity
  digest, v2/v3 semantic/configuration/registry identities, commits, population
  digest, counts, and boundary declarations.

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

Preparation runs through SLURM with 4 CPUs, 16 GiB RAM, and a one-hour limit.
It reads only the existing 8,000-row DEVELOPMENT payload and completed v2/v3
artifacts. It does not scan Phase 2, rerun selection, or accept any path whose
resolved components contain `locked`.

Use a clean detached integration worktree at the exact reviewed targeted-review
commit. Required production variables and commands are shown in the final
implementation report and in
`cluster/goethe_nhr/phase03_parser_v3_targeted_review_prepare.sbatch`.

After preparation, enter separate SLURM compute-node sessions for
initialization and each human reviewer. The terminal interface uses curses and
falls back to standard input/output with `--line-mode`. No network, API, LLM, or
automatic label generation is present. Every real command other than the
privacy-safe `schema` command requires both `SAFE_EXECUTION_SITE=goethe-nhr` and
a non-empty `SLURM_JOB_ID` before opening its inputs, so it cannot run on a Mac
or Goethe login node.

## STOP gate

Do not initialize the real workspace until the code, commit, input paths,
population count, and preparation output have been reviewed. Do not score until
both reviewers finish. Human evidence does not itself authorize promotion;
promotion criteria and any parser change require a separate scientific decision.
