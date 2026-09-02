# Inspecting completed-stage results

## Evidence layers

Completed stages are evaluated through three complementary evidence layers.

1. **Full 35,000-row DEVELOPMENT evaluation.** This is the quantitative and
   scientific evidence: counts, preservation checks, reason distributions,
   fingerprints, resource observations, and other aggregate diagnostics.
2. **Fixed 500-row DEVELOPMENT review subset.** The same deterministic source
   rows are followed across stages for protected human before/after inspection.
   The subset does not replace full-DEVELOPMENT evaluation.
3. **Sanitized Git-safe reports.** The authoritative human explanation for
   each accepted stage is committed under `reports/development/`; the matching
   structured evidence is under `reports/generated/`. Neither class contains
   row-level source values or stable identities.

Every stage comparison is keyed by `stable_source_row_id_v1`. Never compare by
row position alone unless the artifact contract explicitly proves the same
ordered identity stream.

## What is in Git

The [reports index](../reports/README.md) is the single entry point. Open exactly
one `reports/development/stageXX.md` file to understand a stage and its accepted
history. Use exactly one `reports/generated/stageXX.json` file for machine-
readable SHAs, jobs, counts, fingerprints, validation, and review evidence.
These reports support status and aggregate audit; they never expose individual
protected records. The fixed-500 selection fingerprint is consolidated into
the relevant stage summaries rather than maintained as a competing report.

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

| Stage | Full DEVELOPMENT evidence | Fixed-500 or qualitative evidence | Human report | Machine summary |
|---:|---|---|---|---|
| 0 | Population scope, file/row inventory, schema/parser evidence | Not a row-transform comparison | [Stage 0](../reports/development/stage00.md) | [JSON](../reports/generated/stage00.json) |
| 1 | Lossless ingestion, identity, manifest, and reconciliation | Identity is the downstream join foundation | [Stage 1](../reports/development/stage01.md) | [JSON](../reports/generated/stage01.json) |
| 2 | 35,000-to-35,000 preservation and structural metrics | `stage02_review.parquet` | [Stage 2](../reports/development/stage02.md) | [JSON](../reports/generated/stage02.json) |
| 3 | Cleaning, reasons, preservation, and v1/v2 equality | `stage03_review.parquet` | [Stage 3](../reports/development/stage03.md) | [JSON](../reports/generated/stage03.json) |
| 4 | Exact Python lowercase and preservation | Protected fixed-500 comparison | [Stage 4](../reports/development/stage04.md) | [JSON](../reports/generated/stage04.json) |
| 5 | Neutral line reconstruction and preservation | 179-row risk review | [Stage 5](../reports/development/stage05.md) | [JSON](../reports/generated/stage05.json) |
| 6 | Exact registry, collisions, counts, and complete map-back | Machine-verified fixed-500 mapping | [Stage 6](../reports/development/stage06.md) | [JSON](../reports/generated/stage06.json) |
| 7 | Pinned parser evidence, applicability, warnings, and map-back | 120-case diagnostic and failed 240-case readiness experiment | [Stage 7](../reports/development/stage07.md) | [JSON](../reports/generated/stage07.json) |
| 8 | Lossless projection, reversibility, publication, and map-back | Corrected independent rereview | [Stage 8](../reports/development/stage08.md) | [JSON](../reports/generated/stage08.json) |

Stage records under [`docs/stages/`](stages/README.md) explain the exact
accepted evidence and production status.

## HOLDOUT boundary

HOLDOUT is a separate 15,000-row protected artifact. It must not be opened,
profiled, copied, inspected, joined, or used for documentation and tuning. It
is reserved for one explicitly authorized final evaluation after Stages 2–19
are frozen. Paths containing a `holdout` component are rejected by the
DEVELOPMENT reporting interfaces.
