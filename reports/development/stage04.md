# Stage 04 — Lowercase canonical forms

## Status

`STAGE_4_ACCEPTED` on DEVELOPMENT. Production Stage 4 and Stage 9 have not
started.

## Purpose

Stage 4 appends stable lowercase representations for later candidate work while
preserving all accepted Stage 3 values.

## Scope and scientific boundary

The only scientific text operation is exact Python Unicode `str.lower()`. The
stage does not casefold, apply locale rules, normalize after lowercasing, clean,
repair, transliterate, reconstruct, parse, deduplicate, or geocode.

## Inputs

- Exact accepted 35,000-row Stage 3 DEVELOPMENT bundle.
- `stage04_input_binding_v1`, bound to Stage 3 logical
  `38df499bfaf61883832a9c718adf4cf92cfcea753337df68fa2e89afb6051bdb`, schema
  `fc991ef63bd80a754114ecae6a9d3c4cf1f33a35a28581fea997edd2e4565c9b`,
  manifest `8f70745e31185abce52fdc1685c2b767f90874c21596152ea0463ec6677478d4`,
  and ordered identity
  `fe2a4758582c1880d2b5c62dfc5c587d865e05d13033af9f5e8208b58e2a0487`.
- Contract/profile `stage04_lowercase_canonical_contract_v1` and
  `stage04_lowercase_canonical_profile_v1`.

## Outputs

All Stage 3 columns remain exact. Twelve `stage04_lower_*` strings are appended,
together with the ordered `stage04_changed_fields` list and
`stage04_row_changed`. The logical grain remains one source row.

## Scientific contract

For each applicable clean string, the result is exactly `value.lower()` under
Python 3.14.3 and Unicode 16.0.0. PyArrow `utf8_lower`, casefold, locale-specific
casing, and post-lower Unicode normalization are prohibited. A proven-ASCII
fast path must be differentially identical to Python. Standard/native values
follow the same rule but remain separate.

## Implementation provenance

- Accepted implementation:
  `0d98ff6450875dfe8fb37c84729e5bbe632ef2fb`.
- Reviewed candidate:
  `4b6c60c3fb07bb33043e6d31cae3e88bac23393b`.
- Review-only harness:
  `2b77aab03526a4949682cacc0d77db40b7ef9c87`, retained by tag
  `stage04-independent-review-2b77aab`.
- Runtime: Python 3.14.3, Unicode 16.0.0, PyArrow 25.0.0.

## DEVELOPMENT execution

Job `1759421` retained 35,000 rows and all incoming columns. Across 420,000
derived fields, 186,166 fields on 34,994 rows changed; 233,834 fields and six
rows were unchanged. There were 181,549 ASCII and 4,617 Unicode case changes,
zero length changes, zero empty/nonempty transitions, and zero idempotence
failures. The fixed 500 classified all rows as expected case normalization,
with zero questionable or semantic-damage cases.

## Validation and review

- Logical fingerprint:
  `054c66701f854a0108938170e1cb9bcee8a772f7fed29b82cda53c71aa9747ec`.
- Schema fingerprint:
  `dafb4f78b8bfce3120b6f4f7ae8cb44883f4c3a9cfd94b3137871b83c0ed5cbc`.
- Input binding:
  `90e0e94d4359bd5927820dfc06b2cfc1dc37485c032d95726d1260ec88a534b0`.
- Manifest:
  `17a4854cddd8929b65ea79402f1a4f12a1574b720c1921567b577f23e152d1f3`.
- Fixed-500 artifact/manifest:
  `0a8fb68b2f4dfb332d3c8fde431898c2229aed42a3cd27184c5ac0f0a12fe75b` /
  `95f450948daddbbee065cf0a3742ab723549dd5ab69d00fc3186f2ce3bc2ad5c`.

Independent job `1759473` reproduced all rows, all 420,000 derived values,
aggregates, identities, and fingerprints with zero mismatches. Its aggregate
SHA-256 is
`972fb34d6084fc10aede4570bc35b594b948f85cbe5987dcdfe78812724a30c5`.

## Historical findings and rejected attempts

Job `1759398` failed before data access because a canonical `/panfs` child was
compared with an uncanonicalized `/work` root. Job `1759399` produced identical
science but exposed a slow per-character Script diagnostic; the final bounded
cache preserved classifications and fingerprints. Review jobs `1759437` and
`1759438` were review-launcher path failures before DEVELOPMENT scanning and
were not candidate defects.

## Accepted decision

Stage 4 was accepted because the exact runtime-pinned lowercase rule,
preservation, optimized-path equivalence, and fixed-500 interpretation were
independently reproduced without mismatch.

## Known limitations

Lowercase equality is not casefold equality, transliteration, semantic
equivalence, component correctness, or geographic truth. Production estimates
are not production evidence.

## Downstream handoff

Stage 5 may consume clean and lowercase lines to reconstruct separate ordered
standard/native candidates. It must retain upstream values and must not infer
line semantics.
