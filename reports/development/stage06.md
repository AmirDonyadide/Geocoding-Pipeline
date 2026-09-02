# Stage 06 — Early exact deduplication

## Status

`STAGE_6_ACCEPTED` on DEVELOPMENT. Production Stage 6 and Stage 9 have not
started.

## Purpose

Stage 6 creates one global registry of exact lowercase address candidates and a
complete source/representation map-back so later parsing need not repeat work.

## Scope and scientific boundary

Deduplication applies only to candidate occurrences. No source row is removed,
no candidate text is changed, and standard/native occurrence provenance is
retained. The stage does not parse, assess semantics, correct, geocode, or use
fuzzy/normalized equality.

## Inputs

- Exact accepted 35,000-row Stage 5 DEVELOPMENT bundle.
- Contract/profile `stage06_early_exact_deduplication_contract_v1` and
  `stage06_early_exact_deduplication_profile_v1`.
- Stage 5 logical
  `ba5829621fc15347d7cd4e168a48587bab896cd0be98924627876ae853dfaff2`, schema
  `63d4cdb3707eda65c67cc5196891fa5005adce2b12eb7109554793c48c5303c3`,
  manifest `fd945163e3be0242c43b98972350904631279cb99f366baadb0a3094ab6a1fc5`,
  and ordered identity
  `fe2a4758582c1880d2b5c62dfc5c587d865e05d13033af9f5e8208b58e2a0487`.

## Outputs

The row-map relation preserves all Stage 5 columns and appends nullable
standard/native 32-byte candidate IDs. The ID-sorted registry has one row per
exact candidate with its exact lowercase string and total, standard, and native
occurrence counts. Grains are one source row for the row map and one exact
candidate for the registry.

## Scientific contract

The key is global exact Unicode equality of each available accepted Stage 5
lowercase candidate. The ID is
`SHA256(domain || exact_UTF8(candidate_lower))` under
`stage06_exact_candidate_id_v1`. Unavailable representations create neither an
occurrence nor a registry row. Distinct candidate bytes sharing a digest fail
closed. Grouping is disk-backed and complete map-back is mandatory.

## Implementation provenance

- Approved design: `9f9a5a07a2dd3825c895b23406311651e5480324`.
- Accepted implementation:
  `f39047cc825d9baef91915478f657aefecc86d4c`.
- Reviewed candidate:
  `03bab36bc2f45d218eb289abff0ad2aed72cffd8`.
- Review-only harness:
  `e3ec946fb64a154033095d3edcd4afef7203c507`, retained by tag
  `stage06-independent-review-e3ec946`.

## DEVELOPMENT execution

Job `1759819` retained all 35,000 source rows and mapped 69,747 available
occurrences (34,822 standard and 34,925 native) to 51,779 exact candidates.
Deduplication avoided 17,968 prospective parser calls, a 25.7617% reduction.
There were 33,889 singleton and 17,890 duplicate groups; 17,913 same-row
standard/native occurrences were exact-equal. All collision, missing-map,
text-mismatch, count-mismatch, upstream-mismatch, and fixed-500 mismatch counts
were zero. A total of 123 canonical groups retained multiple clean surfaces in
the upstream row map without changing the lowercase key.

## Validation and review

- Contract fingerprint:
  `d4fc73d7fabb734bb0996db4d5c02d6002131179259404eaab20699dacfba8c0`.
- Schema fingerprint:
  `9c07b7a4c3f7a5c43ad457dcf6f7fe3fd746d54d82a731139905b30828b6c9ce`.
- Logical bundle:
  `2f6379c0cd5dc9654c03895cae6fdd48f3a7af528158c33e44d2030c816640b6`.
- Input binding:
  `6ba224d6d24c3631aae8aac69f4a362bb054f01d9e3d09327ec6b0fdd85a0e7d`.
- Manifest:
  `e1da7b8ef04b65b1ece8e710720b57a8536841766fcf9de641f889b42eadd241`.
- Row-map / registry logical fingerprints:
  `1ff9067c521ae93d28c300d7120a03c39681ce7830bf23b6619e2ca6129a4fe1` /
  `6d6d937472c44661e0bff522affb0ed39b41610fa174df3bde36145f749a6c50`.

Independent job `1760055` reproduced every count, full candidate bytes,
fingerprint, collision check, occurrence mapping, and fixed-500 result. Its
aggregate SHA-256 is
`41dd5561ce0c7a57d97acec9eadbebe5f71f0754f017e0295ca324f5adb8579d`.

## Historical findings and rejected attempts

Before the authoritative job, tests corrected handling of legitimate zero
representation-specific counts, private intermediate-directory modes, and an
independent validator assumption about matching record-batch boundaries. An
aggregate-only diagnostic log mode was also corrected before execution. There
were no failed authoritative Stage 6 attempts.

## Accepted decision

Stage 6 was accepted because exact global deduplication reduced work while
preserving every source row, representation occurrence, full candidate string,
and collision-safe map-back; independent reconstruction found zero mismatches.

## Known limitations

Exact lowercase equality is not semantic equivalence. Clean-surface variation
remains upstream, and DEVELOPMENT reduction rates do not guarantee production
rates or runtime.

## Downstream handoff

Stage 7 may parse each registry candidate once and map evidence back through the
accepted row map. It must not treat deduplication as validation or discard the
exact candidate string and occurrence provenance.
