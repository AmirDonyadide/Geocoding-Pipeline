# Stage 8 DEVELOPMENT candidate freeze

Current verdict:
`STAGE08_ADDRESS_EVIDENCE_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW`.

Exact executable commit
`a2544401b4b699f6c020970f3507a2ae432746c5` completed the single authorized
Goethe-NHR DEVELOPMENT materialization as job `1763747`. The immutable
candidate is bound to manifest
`bdf86738fb071e38b2ad090f4627a821149352fb1490e62b76e5819aa915bcf9`
and logical dataset
`9c9d431c2c1b92712e0cb372f2661ad48f4fe8758dc0327d25aef90ab2c2d526`.

The [execution report](stage08_address_evidence_development.md) freezes exact
counts, contract/schema/upstream fingerprints, relation identities, validation
results, topology, runtime, privacy evidence, and scheduler accounting. It
records 51,779 candidates, 6,106,088 ordered components, 35,000 source rows,
and 69,747 exact occurrence mappings with zero dangling/count/occurrence
mismatches. Reversibility and every frozen validator field passed.

`AllocCPUS=80` is not Stage 8 concurrency. The `general1` partition is
exclusive, so SLURM accounted the complete 80-CPU node while `ReqCPUS`, the
launcher, and the application remained at four CPUs. Stage 8 used one task and
DuckDB used four threads; scheduler `TotalCPU` corresponds to approximately
1.034 used core-equivalents on average. This allocation-accounting difference
is operationally relevant but not material to scientific validity or bounded
execution.

The implementation source remains byte-identical to executable commit
`a2544401…`. Focused Stage 8 tests, relevant Stage 7 regressions, Ruff, strict
mypy, shell syntax, JSON, Markdown links, diff hygiene, privacy/tracked-data,
and implementation-blob checks pass. No second job, HOLDOUT, production,
parser rerun, reference service, geocoder, Stage 9 work, science change, or
independent review occurred.

This candidate is not `STAGE_8_ACCEPTED`. Exact next action: start a **FRESH
independent Stage 8 critical-review session** and stop before any later stage.
