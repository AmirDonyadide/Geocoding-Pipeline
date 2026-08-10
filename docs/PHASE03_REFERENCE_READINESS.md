# Phase 3 reference-data readiness

## Status

**NOT PILOT READY.** Phase 3 framework and fictional validation may proceed,
but a real-data pilot remains blocked until all production reference artifacts
below are explicitly reviewed, approved, pinned, and validated.

This document contains no country table, address, provider ID, pilot identity,
or confidential row value.

## Country assignment validation

Required production artifact:

- an approved ISO 3166 assignment-validation artifact;
- authority role `NORMATIVE_CODE_VALIDATION`;
- exact artifact SHA-256;
- stated source, vintage, and retrieval identity;
- loader schema `country_assignments_json_v1` or a separately reviewed version;
- license/terms note and explicit redistribution decision;
- controlled-local identity if redistribution does not permit vendoring.

The framework validates uppercase alpha-2 and alpha-3 assignments from this
artifact. It does not contain or reconstruct an ISO table from memory.

## Country name mapping

Required production artifact:

- an approved UN-maintained name-mapping artifact;
- authority role `NAME_MAPPING`;
- exact artifact SHA-256;
- stated source, vintage, and retrieval identity;
- loader schema `country_names_json_v1` or a separately reviewed version;
- license/terms note and explicit redistribution decision.

UN name mapping remains distinct from ISO assignment validation. Neither source
silently substitutes for the other's authority role.

## Reference manifest contract

Every controlled reference manifest contains:

- `reference_id`;
- `authority_role`;
- `source`;
- `vintage`;
- `artifact_sha256`;
- `loader_schema_version`;
- `license_note`;
- `redistribution_policy`.

The artifact is rejected if its SHA-256 differs, its authority role is wrong,
its schema version is unsupported, or required metadata is absent.

## Unicode Script reference

Required production artifact:

- official Unicode 16.0.0 `Scripts.txt`;
- authority role `UNICODE_SCRIPT_PROPERTY`;
- `unicode_version = 16.0.0`;
- exact artifact SHA-256;
- deterministic `unicode_scripts_txt_v1` loader contract;
- source, vintage, Unicode license note, and redistribution policy.

The loader rejects version/hash/schema mismatches and overlapping ranges.
`Common`, `Inherited`, and unmapped code points do not count as distinctive
scripts. The framework does not claim transliteration equivalence.

## Readiness gate

A real Phase 3 pilot remains blocked until:

1. both country artifacts and manifests are reviewed and validated;
2. the Unicode 16.0.0 Script artifact and manifest are reviewed and validated;
3. the approved hashes and reference IDs replace all `pending_*` versions;
4. licensing and redistribution decisions are recorded;
5. reference-loader synthetic and controlled-artifact tests pass;
6. the user separately authorizes real pilot selection and execution.
