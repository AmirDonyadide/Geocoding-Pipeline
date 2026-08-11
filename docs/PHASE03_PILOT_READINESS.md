# Phase 3 pilot-readiness assessment

## Gate decision

**PILOT_READY**

This assessment used only fictional synthetic rows. It did not read Phase 2
address columns, select real pilot identities, expose evaluation identities,
create `address_key`, geocode, or begin Phase 4.

The former country-reference blocker is removed by replacing UNSD M49 in the
active configuration with the official, versioned, Unicode-3.0-licensed CLDR
46.1 mapping. ISO 3166 remains the normative code-system authority; CLDR is the
operational machine-readable implementation reference. Both country rules are
now ready for the development pilot.

The two former methodology blockers are resolved. The versioned registry now
runs `HOUSE_NUMBER_EDGE_CANDIDATE_V1` only as protected development shadow
measurement, and `manual_review_reason_codes_v1` is closed and enforced. All
12 rules, including both country rules and the intentionally shadow-only house
rule, are ready for their approved development dispositions.
No real pilot selection or execution is authorized by this assessment.
Separate explicit user authorization is still required before any real Phase 2
row or pilot identity is read.

## Readiness-maintenance outcome

- Registry `phase03_rule_registry_v2` has 12 rules and canonical SHA-256
  `d1448859f8436dbe466cab81aee926ab6851b294f5ec664491840bac84627fd5`.
- `HOUSE_NUMBER_EDGE_CANDIDATE_V1` is
  `DEVELOPMENT_SHADOW_ONLY`; it writes protected development evidence but is
  isolated from core selection, completeness, parse status, conflicts, and
  readiness, and is skipped for locked evaluation and authoritative scope.
- `manual_review_reason_codes_v1` is closed, versioned, multi-valued,
  deduplicated, and stored in canonical vocabulary order. Unknown codes fail.
  `OTHER_ADJUDICATION_REQUIRED` requires a separate protected note.
- Country reference
  `country_reference_v2_iso_normative_cldr_46_1_operational` is bound into the
  base configuration fingerprint
  `e5d8821750f6454fa9e9d4d12c9181412438eda6e0f74a191a5a9fdbc4f00002`.
  The production-reference DEVELOPMENT effective fingerprint is
  `92c80594f547716359318924522a1a2ef76dbd1b96b397ec070674e0437a48cc`.
- Development review may change/version rules. Locked evaluation may not be
  used for tuning; a methodological defect found there yields `FAIL/REVISE`, a
  new rule/parser version, and a new locked sample/version.

## Reference readiness

- Unicode 16.0.0 `Scripts.txt`: pinned, vendored under `Unicode-3.0`, and
  technically validated (`2253` ranges; exact hash/size/version checks pass).
- ISO 3166: documented only as normative authority; no paid ISO collection was
  obtained or reproduced.
- CLDR 46.1 operational mapping: three minimum official source files, Unicode
  License v3 notice, deterministic four-string-field canonical extraction, and
  all hashes are vendored and validated; 249 selectable rows pass exact
  identity, schema, uniqueness, exclusion, and repeated-extraction checks.
- UNSD M49: superseded and absent from active startup, lookups, fingerprints,
  and readiness gates. Its prior legal question remains unresolved but is not
  relevant to an implementation that does not use the artifact.

See `docs/PHASE03_REFERENCE_READINESS.md` for exact identities and licensing
analysis.

## Synthetic performance evidence

Benchmark version `phase03_synthetic_benchmark_v1` was measured before the
registry-v2 disposition maintenance. It used Python 3.14.3,
PyArrow 25.0.0, production Unicode/country loaders, ZSTD level 3, 25,000-row
core/evidence row groups, page checksums, independent read-back, and both
semantic digests. The first four populations contain 30,000 fictional rows
each. The oversized population contains 3,000 fictional rows spanning 65,535,
65,536, 65,537, 262,145, 1,048,576, and 1,048,577 UTF-8 bytes.

| Scenario | Rows | Candidates / row | Evidence rows | Evidence / row | Core bytes | Evidence bytes | Total seconds | Rows/s | Peak RSS MiB | Read-back seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STRUCTURED_HEAVY | 30,000 | 4.00 | 0 | 0.00 | 1,064,318 | 6,512 | 10.799 | 2,777.9 | 570.8 | 3.182 |
| CANDIDATE_HEAVY | 30,000 | 9.00 | 210,000 | 7.00 | 1,080,987 | 1,175,588 | 30.703 | 977.1 | 1,270.9 | 8.262 |
| AMBIGUITY_CONFLICT_HEAVY | 30,000 | 6.83 | 390,000 | 13.00 | 1,065,266 | 1,460,365 | 33.823 | 887.0 | 1,528.0 | 9.438 |
| UNICODE_NATIVE_HEAVY | 30,000 | 4.00 | 150,000 | 5.00 | 1,055,715 | 1,112,038 | 22.567 | 1,329.4 | 897.7 | 5.654 |
| OVERSIZED_SAFETY | 3,000 | 3.00 | 1,000 | 0.33 | 125,791 | 41,367 | 21.763 | 137.8 | 114.4 | 0.310 |

Every scenario passed semantic-digest equality and explicit Parquet page-checksum
verification. Core row groups were `[25000, 5000]` for the 30,000-row cases;
evidence row groups were independently capped at 25,000. The oversized scenario
processed approximately 1.278 GB of fictional UTF-8 text without row loss or
scientific-limit changes.

Peak RSS reflects an intentionally simple synthetic harness that retains a
scenario's core and evidence rows for write/read-back validation. The
conflict-heavy 13x evidence expansion is a deliberate stress cohort, not an
estimate of the real distribution. Runtime for real rows remains unknown until
an authorized development pilot.

Generated benchmark artifacts are ignored under
`reports/generated/phase03/phase03_reference_readiness_20260810T210000Z/`.

## Provisional pilot operational settings

The benchmark does not justify changing approved scientific safety limits.
Recommended provisional development-pilot settings are:

- transformation batch rows: `25000`;
- core and evidence row-group target: `25000` rows independently;
- compression: ZSTD level `3`;
- per-field safety limit: `65536` UTF-8 bytes, inclusive;
- combined eight-address-field safety limit: `262144` UTF-8 bytes, inclusive;
- maximum candidates per component: `8`;
- maximum candidates per source row: `64`;
- memory planning: budget at least 4 GiB for the process and retain substantial
  headroom on the 24 GiB development Mac; stop and review if a protected pilot
  materially exceeds the 1.53 GiB synthetic peak;
- minimum free disk before the 12,000-row pilot: 10 GiB, including temporary
  core/evidence pairs, controlled review projections, and validation copies.

The settings remain provisional until real development-pilot evidence is
reviewed. Performance alone cannot change rules or acceptance policy.

## `evidence_sidecar_policy_v1`

The policy is bound into the configuration fingerprint as
`evidence_sidecar_policy_v1`. It is deterministic:

- omit detailed sidecar rows for selected direct structured POSTCODE, LOCALITY,
  REGION, and COUNTRY propagation when no conflict exists; compact core
  provenance remains mandatory;
- write every selected component produced by a nontrivial extraction;
- write every candidate-only or otherwise unselected candidate;
- write the relevant candidate spans as conflicting evidence when a registered
  component/role conflict exists;
- write all candidate spans when multiple candidates create ambiguity;
- write one whole-field span for every exact ambiguous-placeholder-like field;
- write historical-marker spans and every safe, material address field not
  supporting a selected component as unassigned material content;
- record an oversized parsing skip in the core evaluation status, diagnostic,
  maximum byte length, and ordered skipped-field list, but do not copy the
  unevaluated oversized raw field into the sidecar by default;
- a protected manual-review projection joins the controlled raw/core/sidecar
  products by hashed review identity. It does not manufacture portable raw
  context, and ordinary direct rows need no artificial sidecar row solely
  because they were sampled.

Every included evidence record carries a valid non-empty raw code-point span.
Candidate values and spans remain confidential; statistics are disabled. The
policy's measured expansion is the scenario-specific `0.00`, `7.00`, `13.00`,
`5.00`, and `0.33` evidence rows per source row shown above. Existing sparse,
conflict, ambiguity, ordering, span, privacy, digest, and checksum tests cover
the policy; the benchmark exercises its storage behavior. Its exact evidence
counts remain the registry-v1 benchmark record and are not relabeled as a
registry-v2 measurement. Maintenance tests cover v2 shadow isolation and
determinism; exact shadow expansion remains a development-pilot measurement.

## Sampler readiness

Fictional populations validated both compact and full-size sampler settings:

- fixed domain seed and deterministic configuration fingerprint;
- input-order-independent stable-ID scoring;
- 8,000 development plus 4,000 locked-evaluation identities from a fictional
  25,000-row population;
- minimum-stratum quotas and primary-cohort caps;
- targeted rare/safety-case inclusion;
- no duplicate identities and disjoint development/evaluation sets;
- deterministic development and locked identity digests in the seal;
- normal portable summary contains only counts/digests/configuration identity,
  never either identity list.

No real Phase 2 identity was read or selected.

## Manual-review readiness and privacy

The 21-column review-label schema contains `hashed_review_id`, pilot version,
sample partition, reviewer identity, review round, independent-review flag,
component/role/correctness labels, adjudicated label/adjudicator, reason-code
list, reason-code vocabulary version, and label-schema version. It excludes
provider ID and raw address, postcode, and city columns. Separate reviewers and
adjudication are supported.

Raw addresses may later be displayed only through a controlled local or
institutionally approved review application that joins protected inputs in
place. Raw values must not be exported to portable labels, Git, reports, public
issues, external AI/services, or ordinary development artifacts. Controlled
directories use owner-only access; portable outputs contain hashed review IDs
and aggregate metrics only.

The exact closed vocabulary is `CORRECT_AS_IS`, `SOURCE_AMBIGUOUS`,
`INSUFFICIENT_SOURCE_EVIDENCE`, `WRONG_COMPONENT_ROLE`, `WRONG_VALUE`,
`WRONG_SPAN_BOUNDARY`, `FALSE_POSITIVE_EXTRACTION`,
`MISSED_EXTRACTABLE_COMPONENT`, `WRONG_NORMALIZATION`, `WRONG_PROVENANCE`,
`WRONG_CONFLICT_DETECTION`, `MISSED_CONFLICT`, `UNSUPPORTED_FORMAT`,
`UNSAFE_INPUT_HANDLING`, and `OTHER_ADJUDICATION_REQUIRED`. Free text is not a
primary reason and a protected adjudication note is kept outside portable
artifacts whenever the code is used.

## Exact next gate

The parser/reference/rule technical gate passes. The previously missing
production sampling layer is now frozen as `phase03_sampling_contract_v1`,
implemented, and synthetically validated as documented in
`PHASE03_PILOT_RUNNER_DESIGN.md`. Its status is
`PILOT_RUNNER_IMPLEMENTATION_READY_FOR_REVIEW`.

This readiness result is not authority to read Phase 2 rows. A new explicit
authorization is still required to select or process the real pilot.

Phase 3 remains incomplete and `docs/PHASE03.md` must not be created.
