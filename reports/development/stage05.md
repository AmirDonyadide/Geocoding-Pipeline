# Stage 05 — Address reconstruction

## Status

`STAGE_5_ACCEPTED` on DEVELOPMENT. Production Stage 5 and Stage 9 have not
started.

## Purpose

Stage 5 turns each ordered four-line standard or native representation into a
coherent line-body candidate while retaining case-preserving and lowercase
forms plus compact line provenance.

## Scope and scientific boundary

The stage joins line bodies; it does not decide what a line means. It does not
parse, normalize, repair, reorder, remove duplicates, append geographic fields,
choose an authoritative representation, deduplicate candidates, or geocode.

## Inputs

- Exact accepted 35,000-row Stage 4 DEVELOPMENT bundle.
- Contract/profile `stage05_address_reconstruction_contract_v2` and
  `stage05_address_reconstruction_profile_v2`.
- Stage 4 logical
  `054c66701f854a0108938170e1cb9bcee8a772f7fed29b82cda53c71aa9747ec`, schema
  `dafb4f78b8bfce3120b6f4f7ae8cb44883f4c3a9cfd94b3137871b83c0ed5cbc`,
  manifest `17a4854cddd8929b65ea79402f1a4f12a1574b720c1921567b577f23e152d1f3`,
  and ordered identity
  `fe2a4758582c1880d2b5c62dfc5c587d865e05d13033af9f5e8208b58e2a0487`.

## Outputs

Every Stage 4 field remains exact. Ten fields are appended: clean and lowercase
standard/native candidates, availability flags, contributing-line counts, and
four-position occupancy masks. The logical grain remains one source row;
standard and native are separate representations.

## Scientific contract

For each representation and clean/lower form, exact nonempty values are taken
in line positions 1–4 and joined by one U+0020 space. Empty positions are
skipped, gaps retain relative order, duplicate line occurrences remain, and
existing punctuation remains exact. A zero-line representation is unavailable
with an empty candidate, count zero, and mask `0000`.

## Implementation provenance

- Accepted v2 implementation:
  `cd0a5ae91c3602ec20e34f7c419f1ac76f0b9160`.
- Reviewed candidate:
  `97bd7fa74da358e81133ac4d38232931762d3e78`.
- Review-only harness:
  `cbafa0acd20dc3fa03ccd3db8c1f62104529666a`, retained by tag
  `stage05-independent-review-cbafa0a`.

## DEVELOPMENT execution

Job `1759603` retained 35,000 rows with zero additions, drops, duplicate
identities, reconstruction mismatches, or upstream changes. Standard candidates
were available for 34,822 rows and native candidates for 34,925; 34,747 rows
had both, 75 standard only, 178 native only, and zero neither. On rows with
both, 17,913 lowercase candidates were exactly equal and 16,834 differed.

Cleaned standard line counts for 0/1/2/3/4 were
178/14,991/16,890/2,697/244; cleaned native counts were
75/15,032/16,912/2,700/281. These are post-cleaning counts and therefore do not
contradict Stage 2's exact raw-string emptiness counts.

## Validation and review

- Logical fingerprint:
  `ba5829621fc15347d7cd4e168a48587bab896cd0be98924627876ae853dfaff2`.
- Schema fingerprint:
  `63d4cdb3707eda65c67cc5196891fa5005adce2b12eb7109554793c48c5303c3`.
- Input binding:
  `7e68c33f7daa482b442eca82c00c6904ec5e38bec1b3fc598d5be4d52a6bcb9f`.
- Manifest:
  `fd945163e3be0242c43b98972350904631279cb99f366baadb0a3094ab6a1fc5`.

Independent job `1759692` machine-verified the full candidate and reviewed a
179-row risk scope: 136 correct, 37 valid-but-redundant source cases, six
questionable boundaries, zero questionable order, and zero semantic damage.
The attestation SHA-256 is
`5981777021e55280278270c9821d9b02ccbd3fc0fd6711f11e0b833bed24cee8`.

## Historical findings and rejected attempts

V1 used comma-space and ran as job `1759565` at implementation
`e69ccaaebbaeff73d88dd43018904671ee6005dd`. Complete fixed-500 review found
four questionable boundaries, demonstrating that universal punctuation at
source line breaks was unsupported. V2 replaced only the separator with the
narrower neutral U+0020 rule. Six residual v2 boundary ambiguities reflect
numeric adjacency or upstream word wrapping; repairing them would require
semantics that Stage 5 does not own.

## Accepted decision

Stage 5 was accepted because U+0020 prevents literal token concatenation while
preserving source order, duplicates, punctuation, and all upstream evidence.
Independent review found no order error or semantic damage.

## Known limitations

Source line breaks have no universal component meaning. Neutral joining cannot
repair ambiguous numeric adjacency or split words without unsupported parsing.
The original lines remain available downstream.

## Downstream handoff

Stage 6 may globally deduplicate exact lowercase candidates while retaining a
complete occurrence map. It must not delete source rows, mutate candidates, or
collapse standard/native provenance.
