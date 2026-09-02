# Stage 02 — Schema and provenance harmonization

## Status

`STAGE_2_ACCEPTED` on DEVELOPMENT. Production Stage 2 and Stage 9 have not
started.

## Purpose

Stage 2 creates the stable preprocessing schema from accepted Stage 1 data and
adds only passive structural indicators for standard and native address lines.

## Scope and scientific boundary

The stage reports exact source-string emptiness. It does not trim, normalize,
clean, compare, reconstruct, parse, deduplicate, correct, select, or geocode,
and it does not infer the meaning of address-line positions.

## Inputs

- A SHA-pinned `stage02_input_binding_v1` for the accepted Benchmark V1
  DEVELOPMENT artifact.
- All 22 accepted Stage 1 fields and `stable_source_row_id_v1`.
- Benchmark fingerprint
  `014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf`.
- Contract `stage02_schema_provenance_harmonization_contract_v1`.

HOLDOUT paths and non-DEVELOPMENT split values fail before row access.

## Outputs

All 22 Stage 1 fields remain exact and ordered. Four fields are appended:
`standard_has_nonempty_source_line`, `native_has_nonempty_source_line`,
`standard_nonempty_source_line_count`, and
`native_nonempty_source_line_count`. The physical output is a protected
Parquet bundle with manifest and terminal success marker; the logical grain is
one row per source record.

## Scientific contract

- "Non-empty" means exact source `""`; values are not trimmed first.
- The four fields are deterministic functions of the eight raw address lines.
- Standard and native representations stay separate and equally provisional.
- Incoming values, types, order, provenance, and stable identity remain exact.

## Implementation provenance

- Executable/implementation SHA:
  `6432c72ca496852551d3f9d4e9084632cf2766af`.
- No separate candidate or merge SHA is identified in the accepted sanitized
  evidence; those machine-summary fields are `null`.

## DEVELOPMENT execution

Goethe-NHR job `1758833` processed 35,000 input rows into 35,000 output rows.
There were no added/dropped rows, duplicate identities, schema anomalies,
unexpected nulls, impossible structural values, or invariant violations.

Availability was 34,747 both representations, 178 native only, 75 standard
only, and zero neither. Standard nonempty-line counts for 0/1/2/3/4 lines were
178/14,991/16,889/2,698/244; native counts were
75/15,032/16,912/2,700/281.

## Validation and review

The accepted logical fingerprint is
`ff95021bd2f4b2994e9e2a766f32e792e29797a128dc64fa3aef100ff9f5ca72` and the
schema fingerprint is
`3c4a2d616ab6dacf57f42fff7e84175a48fbd50c6a060046434593c5aefa74d4`.
Validation established exact input binding, 35,000-to-35,000 preservation,
equality of all 22 incoming columns, correct derivation, identity uniqueness,
readback, permissions, publication, and HOLDOUT exclusion. The fixed-500
selection fingerprint is
`014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52`.
Reporting job `1758910` at executable
`0cc5077ca80e23c69f15cb37dd29bf010d080958` froze those 500 identities. The
selection represents all 269 observed country strata and 243 of the 1,405
DEVELOPMENT source files, with zero deterministic quota shortfalls; its schema
fingerprint is
`bd3446085e3382d5fdbedd9483a4332ff26d2e5211a03f4b019c765534cfcc51`.

## Historical findings and rejected attempts

No rejected Stage 2 scientific candidate remains material to the accepted
decision. The former separate fixed-subset and stage summary files supplied
useful evidence but are consolidated here and in the generated summary.

## Accepted decision

Stage 2 was accepted because every incoming row and value remained exact and
the four passive structural fields were reproduced without anomalies.

## Known limitations

Exact source emptiness is not cleaned-value availability and is not evidence of
address quality or semantics. This explains why later cleaned line-count
aggregates may differ without contradicting Stage 2.

## Downstream handoff

Stage 3 may derive clean fields while preserving the full Stage 2 row. It must
not reinterpret structural counts as semantics, access HOLDOUT, or imply that
production Stage 2 has started.
