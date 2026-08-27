# Inspecting completed-stage results

## Evidence layers

Completed stages are evaluated through three complementary evidence layers.

1. **Full 35,000-row DEVELOPMENT evaluation.** This is the quantitative and
   scientific evidence: counts, preservation checks, reason distributions,
   fingerprints, resource observations, and other aggregate diagnostics.
2. **Fixed 500-row DEVELOPMENT review subset.** The same deterministic source
   rows are followed across stages for protected human before/after inspection.
   The subset does not replace full-DEVELOPMENT evaluation.
3. **Sanitized Git-safe reports.** Allowlisted aggregates, fingerprints,
   statuses, and interpretation text are committed under
   `reports/development/`. They contain no row-level source values or stable
   identities.

Every stage comparison is keyed by `stable_source_row_id_v1`. Never compare by
row position alone unless the artifact contract explicitly proves the same
ordered identity stream.

## What is in Git

The current sanitized reports are:

- [`review_subset_v1_summary.md`](../reports/development/review_subset_v1_summary.md):
  fixed-500 selection coverage and fingerprint;
- [`stage02_summary.md`](../reports/development/stage02_summary.md): Stage 2
  35,000-row preservation and structural-field evidence; and
- [`stage03_summary.md`](../reports/development/stage03_summary.md): Stage 3
  cleaning, preservation, reason, performance, and v1/v2 evidence.

The paired JSON files are intended for machine-readable inspection. These
reports are sufficient for status and aggregate review, but not for viewing
individual protected records.

## Protected Stage 2 review artifact

The fixed review bundle contains:

```text
<DEVELOPMENT_REVIEW_BUNDLE>/
  selection/selected_identities.parquet
  stages/stage02/stage02_review.parquet
  review_subset_summary.json
  review_subset_summary.md
  development_review_manifest.json
  _SUCCESS.json
```

The Stage 2 view contains review order, stable/source provenance, source
address/geographic fields, prior-geocoding metadata, and the four Stage 2
structural fields. It does not transform source values.

## Protected Stage 3 review artifact

Stage 3 publishes a separate immutable review bundle containing
`stage03_review.parquet`, a protected manifest, summaries, and a terminal
success marker. The Parquet file contains the same fixed 500 identities in the
same review order, the 12 raw fields covered by cleaning, their 12
`stage03_clean_*` counterparts, change details, row-changed flag, and Stage 2
structural fields. It does not overwrite the Stage 2 review artifact.

Both directories must be owner-only (`0700`) and their files owner-only
(`0600`). Paths are environment-specific; do not commit personal absolute paths
as configuration.

## Small local inspection example

Only use a controlled DEVELOPMENT copy that is authorized for local
inspection. Never point this example at HOLDOUT or production. Set an
environment-specific root outside Git:

```bash
export SAFE_STAGE03_REVIEW_ROOT=/controlled/path/to/stage03_review_bundle
```

PyArrow is sufficient to read the fixed 500-row artifact. Pandas is acceptable
here because this is small, controlled DEVELOPMENT inspection—not a production
transformation.

```python
import os
from pathlib import Path

import pyarrow.parquet as pq

review_root = Path(os.environ["SAFE_STAGE03_REVIEW_ROOT"])
table = pq.read_table(review_root / "stage03_review.parquet")
df = table.to_pandas()

changed = df[df["stage03_row_changed"]]
print(changed.shape[0])

comparison = changed[
    [
        "stable_source_row_id_v1",
        "street_address_line_1",
        "stage03_clean_street_address_line_1",
        "stage03_change_details",
    ]
]
print(comparison.head())
```

Do not print, paste, screenshot, or transmit protected values outside the
controlled review setting. For shared discussion, use the sanitized aggregate
reports or synthetic examples.

## Comparing Stage 2 and Stage 3 explicitly

If separate protected artifacts must be joined, validate a one-to-one join on
the stable identity:

```python
import os
from pathlib import Path

import pyarrow.parquet as pq

stage2_root = Path(os.environ["SAFE_DEVELOPMENT_REVIEW_ROOT"])
stage3_root = Path(os.environ["SAFE_STAGE03_REVIEW_ROOT"])

stage2 = pq.read_table(
    stage2_root / "stages" / "stage02" / "stage02_review.parquet"
).to_pandas()
stage3 = pq.read_table(stage3_root / "stage03_review.parquet").to_pandas()

joined = stage2[["stable_source_row_id_v1"]].merge(
    stage3,
    on="stable_source_row_id_v1",
    how="inner",
    validate="one_to_one",
)
assert len(joined) == 500
```

The Stage 3 artifact already includes the covered raw/clean pairs, so this join
is normally needed only to inspect Stage 2-only provenance fields.

## Inspecting each completed stage

| Stage | Full DEVELOPMENT evidence | Fixed-500 evidence | Sanitized record |
|---:|---|---|---|
| 0 | Accepted population scope, file/row inventory, schema/parser evidence | Not a row-transform comparison | Stage record and historical Phase 1 report |
| 1 | Lossless ingestion manifest, logical fingerprint, reconciliation | Source identity is the downstream join foundation | Stage record and protected manifests |
| 2 | 35,000-to-35,000 preservation and derived-structure metrics | `stage02_review.parquet` | `stage02_summary.{md,json}` |
| 3 | 35,000-row cleaning/reason/performance and v1/v2 equality metrics | `stage03_review.parquet` | `stage03_summary.{md,json}` |

Stage records under [`docs/stages/`](stages/README.md) explain the exact
accepted evidence and production status.

## HOLDOUT boundary

HOLDOUT is a separate 15,000-row protected artifact. It must not be opened,
profiled, copied, inspected, joined, or used for documentation and tuning. It
is reserved for one explicitly authorized final evaluation after Stages 2–19
are frozen. Paths containing a `holdout` component are rejected by the
DEVELOPMENT reporting interfaces.
