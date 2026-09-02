# Stage 8 DEVELOPMENT address-evidence materialization

## Technical result

Stage 8 DEVELOPMENT job `1763747` completed `0:0` in 15m18s at executable
commit `a2544401b4b699f6c020970f3507a2ae432746c5`. It published one immutable
candidate with manifest SHA-256
`bdf86738fb071e38b2ad090f4627a821149352fb1490e62b76e5819aa915bcf9`
and logical dataset SHA-256
`9c9d431c2c1b92712e0cb372f2661ad48f4fe8758dc0327d25aef90ab2c2d526`.
Every frozen validation field passed. This is DEVELOPMENT execution evidence,
not independent review or Stage 8 acceptance.

The immutable controlled output is:

`/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage08/development/stage08_development_20260901T214936Z_a2544401b4b6`

## Exact reconciliation passed

| Evidence | Frozen expectation | Materialized result |
|---|---:|---:|
| Exact candidates | 51,779 | 51,779 |
| Ordered parser components | 6,106,088 | 6,106,088 |
| Source rows | 35,000 | 35,000 |
| Occurrence mappings | 69,747 | 69,747 |
| STANDARD occurrences | 34,822 | 34,822 |
| NATIVE occurrences | 34,925 | 34,925 |
| `PARSED_NONEMPTY` | 51,774 | 51,774 |
| `PARSED_EMPTY` | 5 | 5 |
| Mapped component rows | 6,106,088 | 6,106,088 |
| Unmapped component rows | 0 | 0 |
| Dangling components | 0 | 0 |
| Component-count mismatches | 0 | 0 |
| Occurrence-count mismatches | 0 | 0 |

All 51,779 candidate IDs and complete Stage 7 fields were preserved. The
ordered long component relation was mechanically reversible to the
authoritative nested Stage 7 evidence. Source identity, STANDARD/NATIVE slots,
applicability, technical provenance, warnings, duplicate/unknown-label
behavior, and all 69,747 map-back occurrences passed the frozen validator.

No chart is included: these are exact audit identities and totals, not a trend
or comparison where a chart would improve interpretation.

## Frozen contract and upstream bindings

- Contract/profile: `stage08_address_evidence_projection_contract_v1` /
  `stage08_address_evidence_projection_profile_v1`
- Contract fingerprint: `8b3c530e714177fe2c30a97d61dcc199b7f9efba58f3c17a291b817af0f24d5e`
- Schema bundle fingerprint:
  `6c8ebecd24c495dbe2ce32125ac1cb89c4a9de4905c786b774d10ad728ed392f`
- Label mapping fingerprint:
  `b18167d2d5c1f1402d1bb0e92559befb92418f5f4f34df885596778a11d5c09d`
- Accepted Stage 7 manifest/logical identities: `f5841087…` / `0f0706c1…`
- Accepted Stage 6 manifest/logical/row-map/binding identities:
  `e1da7b8e…` / `2f6379c0…` / `1ff9067c…` / `6ba224d6…`

The full schema, relation-logical, and upstream identities are recorded in the
[machine-readable execution report](stage08_address_evidence_development.json).

## `AllocCPUS=80` is exclusive-node accounting

The launcher requested one task with four CPUs, and `sacct` records
`ReqCPUS=4`. It also records `AllocCPUS=80`. Scheduler metadata resolves the
difference:

- requested TRES: `billing=4,cpu=4,mem=32G,node=1`;
- allocated TRES: `billing=80,cpu=80,mem=32G,node=1`;
- partition `general1`: `OverSubscribe=EXCLUSIVE`; and
- allocated node `node20-031`: `CPUTot=80`.

SLURM exclusively assigned and accounted the complete 80-CPU node even though
the application requested four CPUs. Actual Stage 8 configuration remained
one task/process, `--cpus-per-task=4`, and DuckDB `threads=4` with an 8GB
memory cap. Batch `TotalCPU` was 948.969 seconds over 918 seconds elapsed,
approximately 1.034 core-equivalents on average; this is incompatible with
80-way application execution.

The difference is an operational allocation/utilization fact, not a change to
Stage 8 concurrency, ordering, memory bounds, scientific identity, or output.
It is not material to Stage 8 validity and does not justify a rerun. Batch
MaxRSS was 1,759,656 KiB, well below the 32 GiB request.

## Publication, topology, and privacy

The publication contains 26 candidate shards (103,091,918 bytes), 13 component
shards (67,545,742 bytes), nine source-map shards (4,924,221 bytes), and two
metadata files (25,174 bytes). Atomic publication, prepublication reopen
validation, and owner-only permissions passed. The output directory is `0700`;
the manifest, success marker, and logs are `0600`. stderr is empty.

Parser calls, reference lookups, network calls, geocoder calls, and
semantic-trust fields are all zero. HOLDOUT and production access are false.
The manifest contains no row values, and no protected value was logged. Stage
8 makes no correctness, geographic, address-validity, or warning-absence trust
claim.

## Limits and next step

This reconciliation reopens only sanitized manifest, success-marker, log, and
scheduler evidence. It does not independently reopen protected Parquet rows and
is not the fresh critical review required for acceptance.

Exact next action: begin a **fresh independent Stage 8 critical-review
session** against this immutable artifact and the reporting candidate. Do not
alter the artifact, rerun Stage 8, start Stage 9, or infer semantic truth from
parser evidence.
