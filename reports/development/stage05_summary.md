# Stage 5 DEVELOPMENT summary

## Verdict

`STAGE_5_ACCEPTED`

Acceptance is limited to DEVELOPMENT. Stage 6, HOLDOUT, geocoding, and
production Stages 2–5 remain untouched.

## Scientific identity

- Contract: `stage05_address_reconstruction_contract_v2`
- Profile: `stage05_address_reconstruction_profile_v2`
- Implementation: `cd0a5ae91c3602ec20e34f7c419f1ac76f0b9160`
- Reviewed candidate/evidence head:
  `97bd7fa74da358e81133ac4d38232931762d3e78`
- Authoritative job: `1759603` (`COMPLETED`, exit `0:0`)
- Schema fingerprint:
  `63d4cdb3707eda65c67cc5196891fa5005adce2b12eb7109554793c48c5303c3`
- Logical fingerprint:
  `ba5829621fc15347d7cd4e168a48587bab896cd0be98924627876ae853dfaff2`
- Input-binding fingerprint:
  `7e68c33f7daa482b442eca82c00c6904ec5e38bec1b3fc598d5be4d52a6bcb9f`
- Manifest fingerprint:
  `fd945163e3be0242c43b98972350904631279cb99f366baadb0a3094ab6a1fc5`
- Benchmark fingerprint:
  `014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf`
- Fixed-500 fingerprint:
  `014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52`

The input binds the exact accepted Stage 4 schema, logical, input-binding,
manifest, and ordered-identity fingerprints. Full independent readback passed.

## Reconstruction rule

For standard and native, and independently for case-preserving clean and
lowercase lines:

```text
contributing_lines = [line for line in line_1_to_4 if line != ""]
candidate = " ".join(contributing_lines)
```

The exact separator is one U+0020 space. Source order is 1→2→3→4; gaps skip
only exact empty strings; duplicate line occurrences remain. Zero lines yield
an empty unavailable candidate and one line remains unchanged. Standard and
native are never combined or ranked. Postcode, city, region, and country are
excluded. No parsing, semantic inference, repair, deduplication, query
generation, or geocoding occurs.

Stage 5 preserves every Stage 4 field and appends ten candidate/audit fields.

## Full 35,000-row evidence

- Rows: 35,000 input → 35,000 output; 0 dropped, 0 added, 0 duplicate IDs.
- Identity/order and every Stage 4 column: exact.
- Availability: 75 standard-only, 178 native-only, 34,747 both, 0 neither.
- Both candidates: 17,913 exact-equal canonical; 16,834 different.
- Standard line counts: 0=178, 1=14,991, 2=16,890, 3=2,697, 4=244.
- Native line counts: 0=75, 1=15,032, 2=16,912, 3=2,700, 4=281.
- Gap rows: standard 1,597; native 1,737.
- Exact repeated-line rows: standard 56; native 55. Occurrences remain.
- All reconstruction, audit, clean/lower consistency, and idempotence mismatch
  counts are zero.
- Separator overhead: 23,016 standard and 23,155 native code points; Stage 5
  inserted punctuation count is zero.

Standard occupancy masks:

```text
0000=178 0001=0 0010=6 0011=0 0100=61 0101=1 0110=2 0111=0
1000=14924 1001=0 1010=1516 1011=0 1100=15371 1101=11
1110=2686 1111=244
```

Native occupancy masks:

```text
0000=75 0001=27 0010=4 0011=0 0100=35 0101=1 0110=1 0111=0
1000=14966 1001=56 1010=1516 1011=0 1100=15338 1101=97
1110=2603 1111=281
```

Candidate lengths in code points:

| Representation | Count | Min | Median | Mean | P95 | P99 | Max |
|---|---:|---:|---:|---:|---:|---:|---:|
| Standard | 34,822 | 1 | 38 | 4,841.960 | 88 | 117 | 25,920,495 |
| Native | 34,925 | 1 | 25 | 29.781 | 62 | 83 | 21,027 |

The giant upstream values were not truncated: 23 standard candidates remain at
least one million code points.

## Human review and v2 resolution

The human review covered all 500 fixed rows on the immutable v1 artifact:

- `CORRECT_RECONSTRUCTION`: 453
- `VALID_BUT_REDUNDANT_SOURCE_CONTENT`: 43
- `QUESTIONABLE_BOUNDARY`: 4
- `QUESTIONABLE_ORDER`: 0
- `SEMANTIC_DAMAGE`: 0

The questionable orders were 59, 116, 257, and 322. Orders 59 and 257 showed
punctuation adjacency introduced by comma-space; orders 116 and 322 showed
unsupported component punctuation at wrapped phrase/ordinal boundaries. This
was a real general v1 defect, so job `1759565` and its artifacts remain
preserved but are not the final candidate.

The v2 artifact has exactly the same 500 identities and order. The targeted
controlled check established exact space-join behavior and zero inserted
punctuation, but it was not treated as independent qualitative validation.

The 43 redundant-source review orders were:

```text
8, 29, 31, 73, 74, 77, 100, 108, 125, 153, 178, 189, 201, 210,
211, 215, 222, 223, 227, 228, 247, 256, 290, 297, 300, 308, 309,
318, 338, 340, 348, 353, 360, 375, 379, 392, 397, 402, 409, 427,
441, 455, 499
```

They remain intentionally duplicated because the redundancy is upstream source
evidence; Stage 6 owns candidate deduplication.

The automatic bookkeeping split was 499 correct and one redundant. Its
material discrepancy from the human 453/43/4 review demonstrates that it is
not independent qualitative validation.

Independent job `1759692`, at review-harness SHA
`cbafa0acd20dc3fa03ccd3db8c1f62104529666a`, selected a risk-based v2 scope of
179 fixed-500 rows: every row whose multi-line candidate changed from v1 to v2
and nine additional gap-risk rows. The exact qualitative-scope fingerprint is
`801fe9820cae9ae6a9aaf03b0bffcd5c3b8c316fd32b0bc1d4470ef99fd554f5`.
Human review was complete:

- `CORRECT_RECONSTRUCTION`: 136
- `VALID_BUT_REDUNDANT_SOURCE_CONTENT`: 37
- `QUESTIONABLE_BOUNDARY`: 6
- `QUESTIONABLE_ORDER`: 0
- `SEMANTIC_DAMAGE`: 0

The questionable orders were 19, 68, 72, 116, 145, and 169. They concern
ambiguous numeric adjacency and upstream source line wraps that appear to split
a word or name. They are accepted non-damaging limitations: U+0020 prevents
literal token concatenation, preserves content and order, and adds no semantic
punctuation. Repair would require parsing or special-case inference outside
Stage 5. The protected attestation validated against the exact template; its
SHA-256 is
`5981777021e55280278270c9821d9b02ccbd3fc0fd6711f11e0b833bed24cee8`.

No protected row text, stable ID, source filename, or address appears in this
report.

## Performance and boundedness

- Materialization: 36.435 s; 32.366 s user CPU; 3.655 s system CPU.
- Materializer MaxRSS evidence: 1,984,496 KiB.
- Total SLURM elapsed: 111 s; total CPU 89.736 s; batch MaxRSS 672,316 KiB.
- Throughput: 960.615 rows/s and 3,842.459 candidate values/s.
- Linear planning projection for 141,048,582 rows: 146,832 s (40:47:12).

The projection is not a guarantee. Memory is row/batch bounded: adaptive Arrow
batches, no population-sized Python identity set or candidate list, disk-backed
length statistics, and a 500-row cap for qualitative evidence.

## Validation and scope gates

- Focused Stage 2–5 tests: 150 passed.
- Full local-safe suite: 417 passed; four policy-required transfer tests
  deselected.
- Ruff, strict mypy, changed-Python formatting, diff check, shell syntax,
  Markdown links, and privacy/tracked-data audit: pass.
- Controlled directories/files: `0700`/`0600`; publication atomic and immutable.
- HOLDOUT accessed: no.
- Production Stage 2, 3, 4, or 5 started: no.
- Stage 6 started: no.

Independent machine verification and the bound human review support
`STAGE_5_ACCEPTED`. This does not authorize any later stage.
