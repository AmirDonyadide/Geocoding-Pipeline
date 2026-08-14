# Phase 3 DEVELOPMENT human-review interface

Status: implemented for synthetic validation; real-artifact integration and human
review remain separately authorized Goethe-NHR work.

## Boundary

The interface reviews only the frozen 800-row DEVELOPMENT review sample. Reviewer
1 receives all 800 identities. Reviewer 2 receives exactly the frozen 200
independent-double-review identities. The two reviewers use separate progress
databases and cannot see one another's labels. No adjudication, scientific
acceptance calculation, parser change, sampler change, or LOCKED_EVALUATION access
is part of this interface.

Protected context, candidate text, evidence, source spans, and optional notes stay
under owner-only controlled `/work` storage. Portable outputs contain pseudonymous
reviewer codes (`R01`, `R02`) and hashed review identities only. The program makes
no network or API calls.

## Portable label schema v2

`phase03_manual_review_labels_v2` is a new schema. The existing
`phase03_manual_review_labels_v1` schema and artifact remain unchanged.

| # | Column | Arrow type | Nullable |
|---:|---|---|---|
| 1 | `hashed_review_id` | string | no |
| 2 | `pilot_version` | string | no |
| 3 | `sample_partition` | string | no |
| 4 | `reviewer_id` | string | no |
| 5 | `review_round` | uint8 | no |
| 6 | `is_independent_review` | bool | no |
| 7 | `assignment_role` | string | no |
| 8 | `street_label` | string | no |
| 9 | `house_number_label` | string | no |
| 10 | `unit_label` | string | no |
| 11 | `floor_label` | string | no |
| 12 | `building_label` | string | no |
| 13 | `organization_address_role_label` | string | no |
| 14 | `postcode_label` | string | no |
| 15 | `locality_label` | string | no |
| 16 | `region_label` | string | no |
| 17 | `country_label` | string | no |
| 18 | `conflict_correctness_label` | string | no |
| 19 | `parser_overreach_label` | string | no |
| 20 | `missed_information_label` | string | no |
| 21 | `unsafe_handling_label` | string | no |
| 22 | `overall_parse_acceptability_label` | string | no |
| 23 | `reason_codes` | list<string> | no |
| 24 | `reason_codes_version` | string | no |
| 25 | `label_vocabulary_version` | string | no |
| 26 | `adjudicated_label` | string | yes |
| 27 | `adjudicator_id` | string | yes |
| 28 | `label_schema_version` | string | no |

The two adjudication columns are reserved and must be null in reviewer records.
Adjudication is a future controlled workflow.

## Closed vocabularies and validation

Component labels use exactly `CORRECT`, `INCORRECT`, `MISSED`, `NOT_PRESENT`, or
`CANNOT_ASSESS`. Error-condition labels use exactly `ABSENT`, `PRESENT`, or
`CANNOT_ASSESS`. Overall acceptability uses exactly `ACCEPTABLE`,
`NOT_ACCEPTABLE`, or `CANNOT_ASSESS`. Conflict handling uses exactly `CORRECT`,
`INCORRECT`, `NOT_APPLICABLE`, or `CANNOT_ASSESS`.

- `CORRECT`: Phase 3 selected the component correctly.
- `INCORRECT`: Phase 3 selected a component, value, or role, but it is wrong.
- `MISSED`: the source contains safely extractable information that Phase 3 did
  not select correctly.
- `NOT_PRESENT`: the source contains no extractable instance of the component.
- `CANNOT_ASSESS`: the reviewer cannot make a reliable judgment.
- `PRESENT`/`ABSENT`: the named error condition is present/absent.
- `ACCEPTABLE`/`NOT_ACCEPTABLE`: the overall parse is/is not acceptable for the
  available evidence.

The interface retains the immutable `manual_review_reason_codes_v1` vocabulary.
Reasons are sorted and deduplicated in its canonical order. Unknown labels and
reasons fail validation. `CORRECT_AS_IS` is exclusive. Incorrect, missed,
present-error, not-acceptable, and cannot-assess states require applicable reason
codes. `OTHER_ADJUDICATION_REQUIRED` requires a protected note. Notes are limited
to 500 Unicode characters and never enter portable labels or summaries.

Cross-field rules require every component `MISSED` label to coincide with
`missed_information_label=PRESENT`; `missed_information_label=ABSENT` forbids a
component `MISSED` label. `overall_parse_acceptability_label=ACCEPTABLE` does not
require every component to be `CORRECT`.

## Progress and reviewer isolation

The interface creates two owner-only SQLite databases, one per reviewer. Their
logical key is `(hashed_review_id, reviewer_id, review_round)`. Each contains:

- immutable input/version bindings and expected assignment count;
- immutable assignment role, frozen independent-review designation, display
  order, and status;
- closed label fields, canonical reason JSON, protected note, revision, and
  timestamps;
- one reviewer cursor.

Reviewer 1 records use role `PRIMARY`; Reviewer 2 records use
`INDEPENDENT_SECOND`. Both records for a frozen double-review identity retain
`is_independent_review=true`. Review round is exactly 1; a repeated same-reviewer
record is not treated as independent review. SQLite uses foreign keys, full
synchronous durability, an explicit transaction for every completed case, and an
integrity check. A label is committed before the cursor advances, so the session
can safely resume after SSH or allocation termination.

## Interface and commands

The installed command is `safe-geocoding-phase03-review`:

```text
safe-geocoding-phase03-review schema
safe-geocoding-phase03-review initialize ...
safe-geocoding-phase03-review review ...
safe-geocoding-phase03-review progress ...
safe-geocoding-phase03-review export ...
```

The default review UI uses standard-library curses. `--line-mode` selects the
standard-library fallback explicitly; the same fallback is used when curses
cannot initialize. Both show one case at a time, support Unicode, collapse or
expand evidence, page long raw fields, move to the previous/incomplete case, save
before advancing, quit, and resume. The UI never displays provider IDs or stable
source-row IDs.

## Startup and export gates

Initialization verifies page checksums, exact v1 portable schema, exactly 800
DEVELOPMENT identities, exactly 200 frozen double-review designations, empty v1
labels, protected-context identity reconciliation, file hashes/sizes, owner-only
permissions, parser commit, interface commit, and implementation fingerprint.
Paths containing `locked` are rejected.

Export requires 800 complete R01 records and 200 complete R02 records. The exact
R02 identity set must equal the frozen double-review designation. It writes a
temporary Parquet file with page checksums and statistics disabled, validates it,
then atomically promotes it. The sanitized audit manifest binds both immutable
input hashes/sizes, parser and interface commits, implementation fingerprint,
schema/vocabulary/reason versions, reviewer counts, export time, and final
portable-Parquet SHA-256. It contains no raw input, evidence, provider/stable IDs,
candidate values, or protected notes.

## Later Goethe-NHR integration (not performed during Mac development)

1. Use the reviewed implementation commit in the existing project checkout on
   controlled Goethe `/work` storage.
2. Start an interactive SLURM compute-node allocation; do not run Python review
   work on the login node.
3. Treat the preserved failed-pilot directory as read-only audit evidence. The
   protected context and v1 label artifact remain at `SOURCE_REVIEW_ROOT`; do not
   copy, rename, or modify them and never copy them to the Mac.
4. Put every new mutable review artifact under the separate controlled
   `REVIEW_WORK_ROOT`. Run `schema`, then initialize the owner-only progress
   directory using the reviewed implementation commit. Keeping progress on
   `/work` allows it to survive session termination.
5. Run R01 and R02 in separate sessions with their respective progress database.
   Do not share a progress database or expose one reviewer's labels to the other.
6. Use `progress` for sanitized completion counts. Human reviewers, not software,
   supply all labels.
7. Only after both stores are complete, run `export`. Independently verify the
   resulting Parquet page checksums, hash, manifest, permissions, and privacy
   constraints before scientific analysis.

No real-artifact integration or human review has been performed by this
implementation task.

The approved path separation and initialization command are:

```bash
SOURCE_REVIEW_ROOT="derived/controlled/phase03_v1/pilots/.in_progress/phase03_pilot_goethe_20260813T224643Z_1748630_750a1655/development/review_repaired_1748775_f9699cbc"
REVIEW_WORK_ROOT="derived/controlled/phase03_v1/reviews/phase03_development_review_1748630_f9699cbc"
PROGRESS_ROOT="${REVIEW_WORK_ROOT}/review_progress_v2"
EXPORT_ROOT="${REVIEW_WORK_ROOT}/review_export_v2"
IMPLEMENTATION_COMMIT="$(git rev-parse HEAD)"

safe-geocoding-phase03-review initialize \
  --protected-context "${SOURCE_REVIEW_ROOT}/protected_review_context.parquet" \
  --portable-v1-labels "${SOURCE_REVIEW_ROOT}/portable_review_labels.parquet" \
  --output-directory "${PROGRESS_ROOT}" \
  --implementation-commit "${IMPLEMENTATION_COMMIT}"
```

Review sessions read the context at `SOURCE_REVIEW_ROOT` and write only their
SQLite database beneath `PROGRESS_ROOT`. Final portable-v2 Parquet and its
sanitized manifest are written beneath `EXPORT_ROOT`. The progress metadata
binds the immutable source paths operationally and records both source artifact
hashes and sizes. The sanitized manifest emits a normalized repository-relative
controlled path when available, otherwise only a logical artifact identifier,
hash, and size; absolute user- or machine-specific paths are never exported. No
protected source Parquet is copied into `REVIEW_WORK_ROOT`. Nothing in this
workflow writes another file beneath the preserved failed-pilot directory.
