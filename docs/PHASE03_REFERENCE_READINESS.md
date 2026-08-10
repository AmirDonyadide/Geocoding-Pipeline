# Phase 3 production reference readiness

## Status

The production references are technically pinned and validated. Pilot use is
still blocked because institutional use of the controlled UNSD-derived
operational artifact has not been cleared under the applicable UN website
terms. This document contains no country table, address, provider ID, or pilot
identity.

## Unicode Script property

The production Script-property reference is the official versioned Unicode
Character Database 16.0.0 `Scripts.txt`:

- reference ID: `unicode_ucd_16_0_0_scripts_20240430`;
- source: <https://www.unicode.org/Public/16.0.0/ucd/Scripts.txt>;
- artifact: `Scripts.txt`;
- bytes: `189588`;
- SHA-256: `9e88f0a677df47311106340be8ede2ecdacd9c1c931831218d2be6d5508e0039`;
- Unicode version: `16.0.0`;
- parsed ranges: `2253` across `170` Script values;
- Common ranges: `608`; Inherited ranges: `35`;
- loader: `unicode_scripts_txt_v1`;
- technical validation: `PASS`.

The complete file is vendored with `LICENSE.txt`. Unicode identifies data files
under `/Public/` as Unicode Data Files licensed under the OSI-approved Unicode
License v3, SPDX `Unicode-3.0`. The license permits use, copying, modification,
publication, and redistribution provided the copyright and permission notice
accompanies the data or associated documentation. Vendoring is therefore the
reproducible choice. See the official [Unicode terms][unicode-terms],
[licensing policy][unicode-policy], and [license text][unicode-license].

The loader verifies filename, byte size, SHA-256, role, loader schema, and
Unicode version, decodes strict UTF-8, validates every range after deterministic
code-point sorting, and rejects overlaps. `Common`, `Inherited`, and unmapped
`Unknown` code points are excluded from distinctive-script sets. The required
runtime remains Python 3.14.3 with `unicodedata.unidata_version == "16.0.0"`.

## Country authority model

### Normative authority

ISO 3166 and the ISO 3166 Maintenance Agency define and maintain the claimed
country-code system. ISO states that the Maintenance Agency keeps the assigned
country-code set current and that ISO country codes may be used free of charge.
This project does not claim that UNSD is the normative ISO authority. See the
official [ISO 3166 overview][iso-3166].

ISO's downloadable ready-to-use Country Codes Collection is a subscription
product supplied in XML, CSV, and XLS formats. ISO's licence terms restrict
posting, publishing, resale, and redistribution of codes/collections and may
require additional rights for digital integration. The project has not
purchased, scraped, copied, or reconstructed that commercial collection. See
the official [ISO licence agreement][iso-license].

### Operational mapping

The official UNSD M49 English overview table is the operational machine-readable
source because it supplies the four required fields: country or area name, M49
code, ISO alpha-2, and ISO alpha-3. The source is an HTML data table with a
client-side semicolon-separated CSV export, not a durable static CSV endpoint.
The pinned runtime artifact is therefore a deterministic canonical extraction
of only those four fields from the exact official HTML snapshot.

- reference ID: `unsd_m49_country_area_codes_20260810T203327Z`;
- organization: United Nations Statistics Division;
- dataset: Standard country or area codes for statistical use (M49), English
  overview table;
- source: <https://unstats.un.org/unsd/methodology/m49/overview/>;
- retrieved: `2026-08-10T20:33:27Z`;
- controlled artifact: `un_m49_country_area_codes_v1.json`;
- bytes: `23218`;
- SHA-256: `c6bb72998f4cbdd174a941115556b1370d464471fb08ba36ec80f59f7e9581bb`;
- schema: `un_m49_country_area_json_v1`;
- rows: `248`;
- duplicate rows, names, M49, alpha-2, and alpha-3 codes: `0` each;
- missing alpha-2 and alpha-3 codes: `0` each;
- technical validation: `PASS`.

The exact official HTML snapshot is `1721568` bytes with SHA-256
`748f6ff7380c8a50ea9448f068b79e3a1ee31be63207249e8cc89bf1eb969d11`.
Both it and the canonical extraction remain in ignored controlled project
storage. Only manifests and hashes are committed.

The general [United Nations website terms][un-terms] permit personal,
non-commercial download/copy but do not grant resale, redistribution, or the
creation of compilations/derivative works. They do not clearly authorize this
institutional canonical extraction or a future replication-package
redistribution. Therefore:

- private Git vendoring: not approved;
- controlled local project storage: technically implemented, but production use
  requires institutional/legal confirmation;
- future replication package: not approved without explicit permission or a
  separately applicable licence.

The selected production policy is **Option C: remain blocked pending
institutional/legal clarification**. If SAFE confirms lawful institutional use,
the intended technical policy becomes Option B: ISO remains the documented
normative authority and the exact official UNSD snapshot remains the operational
mapping.

## Manifest structure and fail-closed behavior

`country_reference_v1.json` separates `normative_authority` from
`operational_reference`; it contains no ISO table. The atomic operational and
Unicode manifests record reference ID, authority role, source, vintage,
retrieval time, artifact filename, SHA-256, byte size, loader schema, license
identity/note, redistribution policy, and validation status. The country
manifest additionally records organization, dataset, schema, row count, source
snapshot identity, and validation counts.

Production validation fails closed on missing controlled data, filename/size/hash
mismatch, wrong role, wrong loader schema, wrong Unicode version, malformed
rows/ranges, duplicate mappings/ranges, or authority/operational-manifest
inconsistency. A changed snapshot requires a new reference ID and changes the
effective configuration fingerprint; it is never silently refreshed.

[iso-3166]: https://www.iso.org/iso-3166-country-codes.html
[iso-license]: https://www.iso.org/terms-conditions-licence-agreement.html
[un-terms]: https://www.un.org/en/about-us/terms-of-use
[unicode-license]: https://www.unicode.org/license.txt
[unicode-policy]: https://www.unicode.org/policies/licensing_policy.html
[unicode-terms]: https://www.unicode.org/terms_of_use.html
