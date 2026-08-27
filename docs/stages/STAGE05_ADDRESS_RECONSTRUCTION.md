# Stage 5 — address reconstruction

## Status

**DEVELOPMENT IMPLEMENTATION — AUTHORITATIVE EVALUATION PENDING.**

Stage 5 is authorized only for the 35,000-row Benchmark V1 DEVELOPMENT split.
It is not accepted, is not merged to `main`, and does not authorize Stage 6,
HOLDOUT access, geocoding, or any production preprocessing stage.

## Scientific purpose and boundary

Stage 5 converts each existing ordered four-line address representation into a
coherent line-body candidate. It does not decide what a line means. It does not
parse, normalize, validate, repair, reorder, deduplicate, geocode, or create a
final query. Postcode, city, region, and country remain separate structured
fields for later stages.

The contract and profile are:

- `stage05_address_reconstruction_contract_v1`;
- `stage05_address_reconstruction_profile_v1`.

The accepted Stage 4 DEVELOPMENT boundary is bound exactly by:

- contract: `stage04_lowercase_canonical_contract_v1`;
- profile: `stage04_lowercase_canonical_profile_v1`;
- schema fingerprint:
  `dafb4f78b8bfce3120b6f4f7ae8cb44883f4c3a9cfd94b3137871b83c0ed5cbc`;
- logical fingerprint:
  `054c66701f854a0108938170e1cb9bcee8a772f7fed29b82cda53c71aa9747ec`;
- input-binding fingerprint:
  `90e0e94d4359bd5927820dfc06b2cfc1dc37485c032d95726d1260ec88a534b0`;
- manifest fingerprint:
  `17a4854cddd8929b65ea79402f1a4f12a1574b720c1921567b577f23e152d1f3`;
- ordered identity fingerprint:
  `fe2a4758582c1880d2b5c62dfc5c587d865e05d13033af9f5e8208b58e2a0487`.

Benchmark V1 remains
`014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf`.
The fixed 500-row review subset remains
`014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52`.

## Design decision table

| Question | Stage 5 decision |
|---|---|
| Exact scope | Reconstruct ordered address-line bodies only |
| Standard input | Four accepted Stage 3 clean standard lines and their four accepted Stage 4 lowercase counterparts |
| Native input | Four accepted Stage 3 clean native lines and their four accepted Stage 4 lowercase counterparts |
| Standard/native relationship | Reconstruct independently; never combine, rank, translate, or collapse |
| Case-preserving output | Retain a clean, case-preserving candidate for display and audit |
| Canonical output | Retain a lowercase candidate for exact downstream candidate work |
| Geographic fields | Exclude postcode, city, region, and country from reconstruction |
| Empty line | Filter only exact `""`; Stage 3 already prohibits whitespace-only cleaned values |
| Gaps | Skip empty positions without an artificial empty separator; preserve relative order |
| Duplicate lines | Preserve every contributing occurrence |
| Order | Existing source positions 1, 2, 3, 4 |
| Separator | Exact comma plus space, U+002C U+0020 |
| Zero lines | Candidate `""`, unavailable, count 0, mask `0000` |
| One line | Candidate is the line unchanged |
| Provenance | Availability, contributing-line count, and four-position occupancy mask per representation |
| Bounded execution | PyArrow/Parquet row-group streaming with adaptive batches and disk-backed length quantiles |
| Quantitative evidence | Full 35,000-row availability, relationship, line-count, mask, gap, duplicate, boundary, length, identity, and performance metrics |
| Qualitative evidence | Same ordered fixed 500 identities with raw, clean, lower, candidate, and audit comparison surface |
| Tests | Empty/gap/duplicate/punctuation/Unicode/giant/binding/manifest/permission/determinism and regression matrix |

## Exact reconstruction rule

For either representation and either clean or lowercase input:

```text
contributing_lines = [line for line in line_1_to_4 if line != ""]
candidate = ", ".join(contributing_lines)
```

The rule does not trim or mutate a line. Thus existing commas, semicolons,
slashes, hyphens, parentheses, and Unicode punctuation remain exact even when
the result contains adjacent punctuation at a source-line boundary.

The occupancy mask is four characters in line 1-to-4 order: `1` means the
exact cleaned/lowercase value contributes and `0` means it is `""`. A gap such
as lines 1 and 3 yields mask `1010` and joins those two values once, in that
order. Repeated values such as lines 1 and 2 both equal to `A` yield `A, A`.

## Separator decision

Comma plus space adds no component label, prevents token concatenation, is
deterministic, and supplies a conventional address boundary understood by
libpostal without invoking parsing in Stage 5. Public libpostal source and
documentation recognize both comma and newline boundaries. A local PyArrow
experiment was also decisive for implementation method: the available
element-wise join kernel dropped an all-null synthetic row under skip-null
semantics, so it could not implement the zero-line row contract exactly.
Stage 5 therefore uses a small reviewed per-row reconstruction helper inside
bounded Arrow batches. Newline is not used because Stage 5 outputs a scalar
candidate for later parser input, not a source-file layout.

## Appended schema

Stage 5 preserves every incoming Stage 4 field exactly and appends ten fields:

- `stage05_standard_candidate_clean`;
- `stage05_native_candidate_clean`;
- `stage05_standard_candidate_lower`;
- `stage05_native_candidate_lower`;
- `stage05_standard_candidate_available`;
- `stage05_native_candidate_available`;
- `stage05_standard_contributing_line_count`;
- `stage05_native_contributing_line_count`;
- `stage05_standard_contributing_line_mask`;
- `stage05_native_contributing_line_mask`.

Identical standard and native candidates remain two representation-specific
outputs. Exact candidate deduplication and map-back belong to Stage 6.
Component parsing belongs to Stage 7.

## Privacy and execution

Protected 35,000-row processing runs only through the fail-closed Goethe-NHR
SLURM asset at an exact pushed Git SHA. The materializer validates the accepted
Stage 4 manifest before opening its Parquet shards, processes bounded batches,
compares every upstream column independently on readback, and proves ordered
identity with a digest plus the accepted upstream duplicate-free invariant.
It does not build a population-sized Python identity set.

Controlled directories are `0700`; files are `0600`; publication is atomic to
a new immutable run directory. Failed attempts are preserved. Git-safe reports
contain aggregates and fingerprints only. HOLDOUT paths fail closed.

## Development evidence

The implementation, authoritative job identity, full 35,000-row results,
fixed-500 classification counts, fingerprints, performance, and candidate
verdict will be recorded here only after the immutable DEVELOPMENT execution
and independent readback complete.

This session cannot mark Stage 5 accepted. A fresh independent-review session
must decide acceptance.
