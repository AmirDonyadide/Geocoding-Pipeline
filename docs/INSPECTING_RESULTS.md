# Inspecting completed-stage results

## Evidence layers

Stage contracts select from three complementary evidence layers.

1. **Full 35,000-row DEVELOPMENT evaluation.** This is the quantitative and
   scientific evidence: counts, preservation checks, reason distributions,
   fingerprints, resource observations, and other aggregate diagnostics.
2. **Fixed 500-row DEVELOPMENT review subset.** Stages using this contract
   follow the same source identities for authorized before/after review.
   The subset does not replace full-DEVELOPMENT evaluation.
3. **Sanitized Git-safe reports.** The authoritative human explanation for
   each accepted stage is committed under `reports/development/`; Stage 0–8
   structured summaries are under `reports/generated/`. Neither class contains
   row-level source values or stable identities.

Every stage comparison is keyed by `stable_source_row_id_v1`. Never compare by
row position alone unless the artifact contract explicitly proves the same
ordered identity stream.

## What is in Git

Start with the [reports index](../reports/README.md). Each accepted stage has
one `reports/development/stageXX.md` report. Stages 0–8 also have paired
`reports/generated/stageXX.json` summaries with exact SHAs, jobs, counts and
fingerprints. Stage 9 uses its acceptance report and
[independent review evidence](../review/stage09_independent/REVIEW_EVIDENCE.json);
there is no `reports/generated/stage09.json`.

These records contain aggregate audit evidence, never protected rows. Their
historical stop statements describe the recorded checkpoint; use
[current progress](DEVELOPMENT_PROGRESS.md) for subsequent stage status.

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

The example uses the installed PyArrow dependency and prints only a count.
Inspect the selected values only inside the authorized controlled environment.

```python
import os
from pathlib import Path

import pyarrow.parquet as pq

review_root = Path(os.environ["SAFE_STAGE03_REVIEW_ROOT"])
table = pq.read_table(review_root / "stage03_review.parquet")
comparison = table.filter(table["stage03_row_changed"]).select(
    [
        "stable_source_row_id_v1",
        "street_address_line_1",
        "stage03_clean_street_address_line_1",
        "stage03_change_details",
    ]
)
print(comparison.num_rows)
```

Do not print, paste, screenshot, or transmit protected values outside the
controlled review setting. For shared discussion, use the sanitized aggregate
reports or synthetic examples.

## Comparing Stage 2 and Stage 3 explicitly

Stage 3 already contains raw/clean pairs. To compare Stage 2-only fields, set
`SAFE_DEVELOPMENT_REVIEW_ROOT` to the authorized Stage 2 review bundle and align
the two tables by stable identity, checking uniqueness and complete membership:

```python
import os
from pathlib import Path

import pyarrow.compute as pc
import pyarrow.parquet as pq

stage2_root = Path(os.environ["SAFE_DEVELOPMENT_REVIEW_ROOT"])
stage3_root = Path(os.environ["SAFE_STAGE03_REVIEW_ROOT"])
stage2 = pq.read_table(stage2_root / "stages/stage02/stage02_review.parquet")
stage3 = pq.read_table(stage3_root / "stage03_review.parquet")
key = "stable_source_row_id_v1"
assert stage2.num_rows == stage3.num_rows == 500
assert stage2[key].null_count == stage3[key].null_count == 0
assert len(pc.unique(stage2[key])) == len(pc.unique(stage3[key])) == 500
positions = pc.index_in(stage2[key], value_set=stage3[key])
assert positions.null_count == 0
stage3_aligned = stage3.take(positions)
assert stage2[key].equals(stage3_aligned[key])
```

This preserves nested review columns and needs no optional pandas installation.
The aligned tables remain protected; do not emit their rows to shared logs.

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
| 9 | Scoped offline reference checks, witnesses, coverage and publication | Authorized aggregate/public/synthetic review; no protected human address inspection | [Stage 9](../reports/development/stage09.md#owner-acceptance-and-freeze--2026-09-14) | [Review evidence](../review/stage09_independent/REVIEW_EVIDENCE.json) |

Stage records under [`docs/stages/`](stages/README.md) explain the exact
accepted evidence and production status.

## HOLDOUT boundary

HOLDOUT is a separate 15,000-row protected artifact. It must not be opened,
profiled, copied, inspected, joined, or used for documentation and tuning. It
is reserved for one explicitly authorized final evaluation after Stages 2–19
are frozen. Paths containing a `holdout` component are rejected by the
DEVELOPMENT reporting interfaces.
