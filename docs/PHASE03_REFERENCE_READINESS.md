# Phase 3 production reference readiness

## Status

The active Phase 3 production references are pinned, vendored, reproducible,
and technically validated. The country-reference model is now:

- normative code system: ISO 3166 / ISO 3166 Maintenance Agency;
- operational machine-readable mapping: Unicode CLDR 46.1.

UNSD M49 is superseded for Phase 3 v1. Its unresolved institutional-use
question has not been reinterpreted or resolved; the artifact simply does not
participate in startup, country lookup, reference/configuration fingerprints,
or the pilot gate. No real Phase 2 row or pilot identity was read during this
reference change.

## Unicode Script property

The production Script-property reference remains official Unicode 16.0.0
`Scripts.txt`:

- reference ID: `unicode_ucd_16_0_0_scripts_20240430`;
- source: <https://www.unicode.org/Public/16.0.0/ucd/Scripts.txt>;
- bytes: `189588`;
- SHA-256: `9e88f0a677df47311106340be8ede2ecdacd9c1c931831218d2be6d5508e0039`;
- parsed ranges: `2253`;
- loader: `unicode_scripts_txt_v1`;
- technical validation: `PASS`.

The required runtime remains Python 3.14.3 with
`unicodedata.unidata_version == "16.0.0"`. CLDR 46 belongs to the release
family updated for Unicode 16.0; CLDR 46.1 is a maintenance release and does
not change the project's Unicode/runtime contract.

## Country authority model

ISO 3166 and its Maintenance Agency remain the normative code-system
authority. No commercial ISO Country Codes Collection was purchased, scraped,
copied, or reconstructed. CLDR is an operational implementation reference; it
is not described as the normative ISO authority. Country matches retain exact
rule provenance and the bound CLDR reference identity rather than claiming
`ISO_DATABASE_EXACT`. See the official [ISO 3166 overview][iso-3166].

## Pinned CLDR 46.1 release

The official versioned release artifact is:

- release: Unicode CLDR `46.1`, dated 2024-12-18;
- source: <https://www.unicode.org/Public/cldr/46.1/cldr-common-46.1.zip>;
- retrieved: `2026-08-10T21:27:22Z`;
- release bytes: `34308024`;
- release SHA-256:
  `c3828c9280c6b3bb921bc96baf53be2174b5416d72e740ec3915c1ff91a50a80`;
- release SHA-512:
  `6f5bece848d8187da35cc4c4022bea6a673e40a6032864b09ef24744f35bbf5e89e32e9852bbfd91d7466332db87c8f4f514ff70221729275701b7d95bac2925`.

The release README documents a versioned `hashes/SHASUM512.txt` location, but
that resource was unavailable at retrieval. The recorded SHA-256 and SHA-512
were therefore calculated from the exact official HTTPS artifact; no upstream
hash is claimed.

Only the minimum output-affecting files are vendored:

| CLDR archive path | Local file | Bytes | SHA-256 | Purpose |
|---|---|---:|---|---|
| `common/supplemental/supplementalData.xml` | `supplementalData.xml` | 396715 | `277105238ecaab5b0e476f3bc7d25a26358227c5c77d02b0921d311c3f940dbf` | alpha-3 and numeric mappings |
| `common/main/en.xml` | `en.xml` | 431277 | `5ac57cec48ab8d9a87cbd920444024ccdcc914ae6ffa4353f6e17bc0a9f8d6e7` | canonical English territory name with no `alt` |
| `common/validity/region.xml` | `region.xml` | 1905 | `e751e0eedd46b52c38f3cdb72b0fab61ac8b48e052e8b28ba74b6ac26c4c8cb1` | explicit CLDR region-status categories |

## License and redistribution

The exact release `LICENSE` is bundled unchanged (2036 bytes; SHA-256
`4e6e762822c88cf41c072b93568f3e1a6784b5b013e82bf42a61bb7a018d9239`).
It identifies Unicode License v3, SPDX `Unicode-3.0`. The official Unicode
terms and licensing policy place Unicode data files under this permissive
license unless a specific exception applies; none applies to these CLDR files.
See the official [Unicode terms][unicode-terms], [licensing policy][unicode-policy],
and [license FAQ][unicode-license-faq].

The license permits internal academic use, extraction/transformation, private
repository storage, publication, and redistribution, including a future
reproducibility package, provided the copyright and permission notice
accompanies copies or associated documentation. The vendored `LICENSE` must
therefore remain with the source and derived reference artifacts.

## Canonical extraction and selectable policy

`cldr_country_reference_extractor_v1` parses the three pinned XML files and
writes canonical UTF-8 JSON twice identically. The schema is four strings:

1. `territory_code`;
2. `alpha3_code`;
3. `numeric_code`;
4. `english_name`.

The numeric code remains a three-character string. Only CLDR `regular`
territories with all four required values and one canonical English name
without `alt` are candidates. ISO user-assigned alpha-2 ranges (`AA`, `QM-QZ`,
`XA-XZ`, `ZZ`) and numeric range `900-999` are excluded. This removes `XK`,
which CLDR marks `regular` but maps through user-assigned code space.

The canonical result contains `249` rows, is `23477` bytes, and has SHA-256
`6d38c9431a97dff511da8048381de42b27c5eef7b9a94409400f16f3d332325a`.
There are zero duplicate territory, alpha-3, numeric, or canonical-name values.

Explicit non-selectable categories are:

- CLDR statuses: 35 macroregions, 2 special, 12 deprecated, 13 reserved,
  23 private-use, and 1 unknown identifier;
- seven `regular` identifiers missing one or more required four-field values:
  `AC`, `CP`, `CQ`, `DG`, `EA`, `IC`, `TA`;
- one otherwise complete user-assigned mapping: `XK`.

Short names, variants, historical aliases, macroregions, subdivisions, fuzzy
names, spelling correction, and transliteration guessing are not loaded.

## Identity and fail-closed behavior

- country reference ID:
  `country_reference_v2_iso_normative_cldr_46_1_operational`;
- authority manifest: `country_reference_manifest_v2`;
- bundle manifest: `cldr_country_reference_manifest_v1`;
- canonical schema: `cldr_country_reference_json_v1`;
- selectable policy: `cldr_country_selectability_v1`;
- extractor configuration fingerprint:
  `141368c1838f67a7eb1544febb95c949554d36d86a6016b46e40fb2ab03f2383`.

Startup validates every source hash/size, license identity, release/version,
reference role, extractor fingerprint, exact repeated extraction, canonical
artifact identity, schema, row count, uniqueness, exclusions, Unicode scripts,
and configured reference IDs. A changed file, manifest, role, release, or
canonical output fails closed. Runtime performs no network download and never
uses `latest` or an unversioned CLDR URL.

[iso-3166]: https://www.iso.org/iso-3166-country-codes.html
[unicode-terms]: https://www.unicode.org/copyright.html
[unicode-policy]: https://www.unicode.org/policies/licensing_policy.html
[unicode-license-faq]: https://unicode.org/faq/unicode_license.html
