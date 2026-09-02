# Stage 8 address-evidence implementation candidate

## Verdict

`STAGE08_ADDRESS_EVIDENCE_IMPLEMENTATION_READY_FOR_CONTROLLED_DEVELOPMENT_EXECUTION`

This report covers implementation and synthetic/local validation only. Stage 8
has not read protected Stage 7 or Stage 6 DEVELOPMENT values, run on SLURM,
materialized protected output, undergone independent implementation review, or
been accepted. HOLDOUT and production remain untouched.

## Immutable implementation identity

- Branch: `stage08-address-evidence-implementation`
- Frozen design commit: `ff84a35fc4ac2f890e383d24f62c099c75703105`
- Implementation commit: `a2544401b4b699f6c020970f3507a2ae432746c5`
- Contract: `stage08_address_evidence_projection_contract_v1`, fingerprint
  `8b3c530e714177fe2c30a97d61dcc199b7f9efba58f3c17a291b817af0f24d5e`
- Profile: `stage08_address_evidence_projection_profile_v1`
- Schema bundle: `stage08_address_evidence_projection_schema_v1`, fingerprint
  `6c8ebecd24c495dbe2ce32125ac1cb89c4a9de4905c786b774d10ad728ed392f`
- Label mapping: `stage08_libpostal_label_mapping_v1`, fingerprint
  `b18167d2d5c1f1402d1bb0e92559befb92418f5f4f34df885596778a11d5c09d`

The candidate, component, source-map, and occurrence schemas respectively have
fingerprints `b1d56ea3…`, `112fb17c…`, `884eb845…`, and `df1cac9b…`. The complete
identities and exact accepted upstream bindings are in the companion
[machine-readable report](stage08_address_evidence_implementation.json).

## Implemented projection

The implementation publishes three Parquet relations:

1. `candidate_evidence`: one row for each of the exact 51,779 Stage 6
   candidates, preserving the complete Stage 7 v2 row and appending only
   mechanical index counts/status;
2. `parser_component_evidence`: one row for each of the expected 6,106,088
   ordered raw components, keyed by exact candidate identity and zero-based
   ordinal; and
3. `source_candidate_map`: one row for each of the exact 35,000 source rows,
   preserving distinct raw, clean, lowercase, lineage, country-provenance, and
   STANDARD/NATIVE linkage fields.

The deterministic, non-materialized `representation_occurrence_v1` view
reconstructs all expected 69,747 mappings in source-row then STANDARD/NATIVE
order. Candidate input and nested evidence use PyArrow; component child arrays
are sliced in bounded batches, and DuckDB performs bounded source/occurrence
reconciliation. There is no pandas production path.

## Mapping and reversibility

The mapping is an exact, case-sensitive, one-to-one index from each of the 20
frozen libpostal labels to a parser-scoped `PARSER_*` name. Every raw label,
raw value, duplicate, and ordinal remains exact. Unknown labels remain exact
with `UNMAPPED_LABEL` and a null parser-scoped name. No mapping produces source
truth, a verified component, confidence, readiness, or geographic meaning.

The raw nested Stage 7 list remains authoritative. Reopen validation
mechanically reconstructs each ordered label/value list from the long relation
and checks it byte-for-byte against the nested evidence. It also verifies
candidate and Stage 7 field identity, warning/applicability/provenance
consistency, duplicate and unknown-label counts, source identity,
STANDARD/NATIVE slots, all occurrences, schema and upstream fingerprints,
artifact hashes/topology/modes, and layout-independent logical fingerprints.

## Synthetic and static evidence

- Focused Stage 8 suite: 7 passed, covering all 20 labels, exact unknowns,
  repeated labels, empty lists, unresolved applicability, absent/BOTH slots,
  shared candidates, multiple source rows, ordering, a 10,000-component giant
  row, batch/shard invariance, tampering, topology/modes, prohibited paths,
  and prohibited semantic vocabulary.
- Relevant Stage 7 regressions: 34 passed.
- Safe full local suite: 574 passed, 24 failed, 4 deselected. Every failure is
  an immutable Stage 3–6 Python 3.14.3 runtime guard under the Mac's Python
  3.14.7; no guard was weakened.
- Ruff, strict mypy, shell syntax, JSON validity, Markdown local links,
  `git diff --check`, and privacy/tracked-data checks passed.

No protected values, row-level artifacts, credentials, parser calls, reference
lookups, geocoders, or network data transfers were used. The report contains
only public metadata, fixed counts, hashes, and synthetic results.

## Proposed bounded Goethe DEVELOPMENT execution

After separate owner authorization, submit exactly one
[Stage 8 launcher](../../cluster/goethe_nhr/stage08_address_evidence.sbatch)
from detached pushed commit
`a2544401b4b699f6c020970f3507a2ae432746c5`: one node, one task, four CPUs,
32 GiB, four hours; DuckDB 8GB/four threads; Arrow input/candidate/component
batches 16/32/65,536; 128 MiB target batches; and candidate/component/source
shards of 2,048/500,000/4,096 rows. The accepted Stage 7 rereview artifact is
about 2.02 GiB, while the frozen maxima are 25,920,495 candidate code points
and 881,338 components; bounded child-array slicing and bounded reconciliation
justify these conservative resources.

The owner supplies the exact immutable accepted Stage 7 v2 root, Stage 6 root,
validated runtime, clean detached integration root, and a new controlled output
path at submission. The implementation validates their fixed manifests and
logical identities before reading Parquet. No data fingerprint is claimed
before this authorized materialization.

Exact next action: the owner may separately authorize that one bounded
Goethe-NHR DEVELOPMENT materialization. A pending immutable run must be waited
for and reused; no duplicate job is authorized.
