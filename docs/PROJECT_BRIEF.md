# SAFE Geocoding Pipeline — project brief

SAFE needs defensible physical locations for protected Orbis company and
facility records used in environmental and spatial research. Building-, plant-,
branch- and store-level exposure analysis requires more than a geocoder response:
the selected coordinate must have suitable precision and no unresolved major
geographic contradiction. Coarse centroids cannot stand in for physical sites.

## Intended research product

For every source row, the final dataset should retain immutable values and
provenance; derived representations; candidate, reference and query lineage;
geocoder attempts and evidence; the selected result and selection reason; and
an explicit usability decision (planned as `usable_for_analysis`). That final
schema and its acceptance thresholds are not implemented yet.

The pipeline separates source facts, parser/reference evidence, hypotheses,
geocoder results and accepted matches. Native and standard representations stay
separate. Uncertain cases remain unresolved; open-reference absence never proves
invalidity. Parser success and high geocoder confidence do not establish truth.

## Scope and status

| Track | Population | Status |
|---|---|---|
| DEVELOPMENT | 35,000 Benchmark V1 rows from 1,405 files | Stages 0–9 accepted; Stage 10 implemented but unaccepted |
| HOLDOUT | 15,000 Benchmark V1 rows | Sealed for one authorized final evaluation |
| Production | 1,411 files; 141,048,582 rows | Stages 0–1 accepted; Stage 2 onward not started |

The six later production files do not alter the benchmark. A fixed 500-row
DEVELOPMENT subset supports comparable review; quantitative evaluation uses the
full DEVELOPMENT population. See [current progress](DEVELOPMENT_PROGRESS.md)
and the [review workflow](DEVELOPMENT_WORKFLOW.md).

## Delivery constraints

Stage designs, execution and acceptance require explicit review and scoped
authorization. Rejected candidates, failed runs and their ancestry are retained.
Protected/heavy work runs through Goethe-NHR SLURM at an exact pushed Git SHA,
with pinned runtimes, immutable outputs and complete source-row map-back.
Production capacity must be demonstrated separately from DEVELOPMENT results.

Addresses, row-level artifacts and credentials remain controlled; they never
enter public APIs, external geocoders, LLMs or Git. SAFE Pelias is self-hosted,
but no geocoding run is authorized. The existing Stage 19 acceptance gate must
be reconciled explicitly before the proposed retrieval stage can execute.

For technical detail, use the [project overview](PROJECT_OVERVIEW.md),
[pipeline specification](PIPELINE.md), [data model](DATA_FLOW.md),
[execution guide](EXECUTION.md) and [sanitized reports](../reports/README.md).
