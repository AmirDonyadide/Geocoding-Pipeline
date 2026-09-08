# Stage 9 — Owner revisions and public reference freeze

## Status and authorization

`STAGE09_REFERENCE_DESIGN_OWNER_APPROVED_AND_FROZEN`.

The owner approved the scientific direction with four required revisions and
authorized bounded acquisition of the three public references, design/lock
commit and normal push. This record covers that work only. Stage 9 materializer,
indexes and protected DEVELOPMENT execution are **NOT STARTED**. This is not
`STAGE_9_ACCEPTED` and authorizes no later stage or geocoding.

Baseline: `24b2679f8f487ebdbe65633c688996b1d36ea9eb`, on main, equal to
origin/main after fetch and frozen tag `pre-stage09-baseline-v1`. The original
four-document candidate was uncommitted and is replaced by this approved v1
design; no accepted or rejected Stage 0–8 history is rewritten.

Normative assets: [design](STAGE09_OFFLINE_REFERENCE_EVIDENCE.md),
[public lock](../scientific_assets/stage09_reference_pack_lock_v1.json).
The lock records every acquired successful body and archive member, source URL,
retrieval completion time, content SHA-256, HTTP header hash/Last-Modified/ETag,
license evidence, comparison inventory, capability selectors and public counts.
It contains no protected row identifiers or address examples.

## Selected releases and scientific input hashes

All content digests below are SHA-256. Retrieval date: 2026-09-07 UTC.

| Family / input | Exact release / content SHA-256 |
|---|---|
| ISO_CODES / ISO 3166-1 | Debian 4.20.1-1, upstream v4.20.1 (2026-01-01); `f01b812b57fba9f31ff621bf33e7c7570a01964dbeb5be2167e94decf538c89f` |
| ISO_CODES / ISO 3166-2 | Same release; `78c90ef7fc25b5c2631aac5f089bc9ff6ec22c025c05b6ddbc087a1f1be2e46a` |
| LIBADDRESSINPUT_METADATA / distribution wheel | google-i18n-address 3.1.1 (2024-09-04); `f66f4fd2b75d1cd371fc0a7678a1d656da4aa3b32932279e78dd6cae776fc23d` |
| LIBADDRESSINPUT_METADATA / i18naddress/data/all.json | Actual selected metadata bytes; `acc76495cb29c995e73d41dd2f0c51c87695b6395a767d439f7780403deb092f` |
| GEONAMES_POSTAL / allCountries.zip | Acquired 2026-09-07T19:52:38+00:00, no semantic release; `5c89270e2192b157eb8014922158c1f8410b93ad4bc1e97225fe2e58cf46e074` |
| GEONAMES_POSTAL / allCountries.txt | Uncompressed member; `2a9780179d77fe299e52226931bf1d170767928eca773374b0ec543e64c6d198` |

ISO selection: current [upstream releases](https://salsa.debian.org/iso-codes-team/iso-codes/-/tags)
and [Debian versions](https://sources.debian.org/src/iso-codes/) both identify
4.20.1 / 4.20.1-1. Selected Debian JSON exactly equals the upstream-tag JSON.
Compared with 4.18.0-1: 249 country records are byte-identical; 5,046 subdivision
codes remain unchanged, with no code additions/removals or parent/type changes.
121 records have name-only changes across 16 countries. The lock records all
changed codes. Select the current published names, not the older design-time
version. Stage 7's 4.18.0-1 eligibility input remains untouched; shared lineage
remains explicit even across versions. Published names are partial reference
aliases, not a complete language inventory or sovereign-boundary adjudication.

Metadata selection: [PyPI](https://pypi.org/project/google-i18n-address/3.1.1/)
still lists 3.1.1 as latest. The current mirror's actual
`src/i18naddress/data/all.json` is byte-identical to the selected wheel member.
The latest data-path commit is
`8a99723644297542c58b138678e394b7f49b6bda` (2024-09-04). An old repository path
returned 404; the public tree resolved its move to `src/`, and both successful
content and failed request provenance are retained. No alternative scientific
asset was substituted. The member's archive timestamp is 2020-02-02; it is not
an effective date. The content hash, not a repository revision or package API,
is the scientific input. No package was installed or executed.

GeoNames selection: one current [postal dump](https://download.geonames.org/export/zip/),
not a gazetteer or per-country/full-variant mixture. HTTP Last-Modified is
2026-09-07 01:59:37 GMT; member timestamp is recorded separately without assuming
its timezone. These timestamps do not establish per-country effective dates.
The exact archive/member hashes are the frozen snapshot identity.

## Storage, inventory and licenses

25 successful downloaded bodies total 24,564,545 bytes, within the 256 MiB
budget. The archives contain 144,633,844 uncompressed bytes, within 1 GiB.
The wheel has 262 members; only all.json is scientific input. GeoNames has one
member: 140,617,550 bytes uncompressed, 19,701,128 bytes for the archive.
The metadata member is 1,978,328 bytes. All member hashes and byte counts are
recorded, including unused distribution files as inventory, not evidence.

Raw bytes and HTTP headers remain in the owner-only, Git-ignored directory
`external_data/stage09_reference_freeze_v1/` (directories 0700, files 0600).
Do not refresh, edit or replace these assets. Before a future authorized job,
copy retained public bytes to approved personal offline storage on Goethe and
verify the lock; do not download mutable URLs inside jobs. A mirror recovery
is acceptable only for the exact locked bytes. If unavailable, stop; never
silently select newer data. No derived reference index is claimed built.

| Reference | License disposition |
|---|---|
| ISO_CODES | Debian selected-data notice LGPL-2.1-or-later and full LGPL-2.1 text retained. Preserve source, notices and index-change/build provenance. |
| LIBADDRESSINPUT_METADATA | Google data CC-BY-4.0; mirror archive code BSD-3-Clause; Google code Apache-2.0 is distinct and unused. Preserve Google attribution, actual data source, mirror notice and change disclosure. |
| GEONAMES_POSTAL | Publisher states CC-BY-4.0 while retaining a legacy BY-3.0 link. Preserve both notices and satisfy attribution/source/change requirements for both; do not conceal the discrepancy. GB_full Royal Mail data is excluded. |

No selected asset has a newly discovered restriction blocking this offline
design. This is the project's documented license/provenance disposition, not
a claim that the data is complete or authoritative for postal validity.
Exact notice/license hashes are in the lock; no license is inferred from Pelias.

## Verified capability limits

GeoNames: 1,826,904 strict 12-field UTF-8 postal records across 121 ISO countries.
The lock gives every country's record counts, nonempty component/relationship
counts, postcode-length distribution, and all 128 absent ISO countries.
All GeoNames negative authority is FALSE. Postcode association differences are
NOT_FOUND / REFERENCE_ASSOCIATION_MISMATCH, never semantic contradiction.

Full-code Q05–Q07 are disabled for AR, CA, CL, CN, GB, IE, MT, NL; raw data and
non-postcode partial place/admin capability remain separately recorded. AR is
documented as the first five positions, not assumed to be the older four-digit
system. BR is major-code-only positive evidence. US ZIP+4 is not reduced to a
five-digit code. Empty fields and absent countries have explicit unavailable
capabilities; no country gets a blanket global authority level. CA_full.csv.zip,
GB_full.csv.zip and NL_full.csv.zip are recorded as not acquired/not enabled.

Libaddressinput: 12,261 keyed nodes, all 249 ISO country roots, four extra
non-active roots (AC, TA, XK, ZZ), and six language-tagged country variants.
String types and tilde-array alignment pass. Actual enabled country counts:

| Capability | Countries | Negative authority |
|---|---:|---|
| FORMAT (explicit fmt) | 194 | FALSE |
| REQUIRED_FIELDS (explicit require) | 94 | FALSE; metadata availability only |
| POSTCODE_PATTERN | 176 | Only the explicit compatible frozen rule |
| ADMIN_ENUMERATION | 48 | FALSE |
| POSTCODE_PREFIX_BY_ADMIN | 24 | Only an explicit unambiguous rule bundle plus satisfied country rule |
| LOCALITY / LOCALITY_ADMIN | 6 | FALSE; actual recorded hierarchy only |

Missing fields do not inherit negative authority from ZZ defaults. Bahrain's
postcode expression is outside the approved grammar. China's unqualified
country regex is disabled because known alternate branches cannot be ignored;
the six exact alternate field locations and affected branch rules are locked.
No absence of metadata or enumeration can invalidate a source address.

The audit examined 4,444 pattern fields, with 1,255 distinct permitted patterns.
Using local DuckDB CLI 1.5.5 (`d8cdaa33fd`, bundled RE2) and Python 3.14.7
re.ASCII, 23,682 full/prefix comparisons passed with zero differences, including
public examples and deterministic grammar probes. Of 1,093 supplied examples,
1,092 were evaluable and had zero misses; the one unsupported Bahrain example
was not evaluated or counted as a pass. This certifies the bounded public compatibility check,
not every conceivable regex property or a protected runtime execution. Future
synthetic tests still exercise the exact approved runtime and evaluator.

## Bounded design self-review: complete collected defect ledger

The nine owner questions were reviewed together after acquisition. Findings
were collected before the final design-only correction pass:

| Finding / owner risk | Resolution |
|---|---|
| Country regex could ignore an alternate branch; an excluded example could be counted as passing | Disable unqualified CN country pattern and affected branches; BH grammar disabled, its one example explicitly excluded from the 1,092 checked-example denominator. |
| Role-based family names overstated actual provenance | Only ISO_CODES, LIBADDRESSINPUT_METADATA and GEONAMES_POSTAL active; authoritative families reserved. |
| Open absence or differing GeoNames association could look like invalidity | GeoNames negative authority always FALSE; NOT_FOUND and mismatch diagnostic stay separate from source invalidity. |
| Country node existence could be mistaken for available fmt/require | Q03 witnesses actual fmt; Q15 actual require; missing fields NE and no defaults-based negative authority. |
| Version could freeze old ISO or code-only metadata identity | Current upstream/Debian compare, actual metadata byte comparison, all archives/members/notices hashed; no auto-refresh. |
| Proposed contexts/maps duplicated Stage 8 authority | Six logical relations only; source-row/candidate scope points directly to Stage 8; occurrences remain solely upstream. |
| ISO Q02 witness wording implied a second asset; scoped rule FK needed clarity | Full recognized ISO 3166-2 code itself witnesses owner; Q03/Q04/Q15 country and Q08 admin rule bundles have explicit scoped capability FKs. |
| Aggregate grouping/denominators could be over-normalized or double-counted | Exact state, reason, candidate/source/occurrence incidence and country-summary grouping sets; ALL never summed with its children. |
| Simplification could lose boundary lineage or giant-case scalability | Exact Stage 8→Stage 6 route preserved; bounded ≤3 argument locators, one inline witness or streamed shared multi-members, no text/map copies. |

All findings are resolved together in the final design. Negative authority is
limited to full recognized ISO code ownership and eligible frozen metadata
predicates, never open-catalog absence. Every real evidence row binds one
candidate, one exact data asset and one matrix capability; rule-level gates
are explicit. NONE rows are distinguishable scheduled abstentions, not fake
references. No Stage 0–8 change is required.

## Validation and unchanged boundaries

Validation for this change is documentation/schema/static and public-reference
only: strict JSON/unique keys; frozen inventory/byte/member hashes; permission
and archive-path checks; ISO namespace/parent validation and release comparison;
country/field capability checks; metadata grammar/examples/RE2 comparisons;
capability-authority invariants; relative links, catalog/schema consistency and
whitespace; and Git change-scope checks. Final static result: **PASS** for
25 acquired-body hashes, 263 archive-member hashes, 17 capability templates
expanding to 3,752 country-matrix rows, six typed logical relation declarations,
15 catalog questions, seven documentation files and 18 exact accepted Stage 8 /
transitive fingerprints. Zero protected inputs were opened. No synthetic
materializer tests or protected execution are claimed.

Frozen lock file SHA-256:
`61cc5850372886eb4ba6477a178ebd74f6ca878815036874ad47069ca32a1c63`.
This hash is outside the lock to avoid a self-referential fingerprint. Future
index/schema/profile hashes are not fabricated by this raw-reference freeze.

Stage 7 contract/schema remain
`c9561e6d08263b2a8824ff66f2a3aa8521e3ff880759abc14173cce440ced8a4` /
`b0e0e83ea3d929b7df8a6a5f64c2e8eb026395a917da90e97a98858b27e9ead2`.
Stage 8 contract/schema remain
`8b3c530e714177fe2c30a97d61dcc199b7f9efba58f3c17a291b817af0f24d5e` /
`6c8ebecd24c495dbe2ce32125ac1cb89c4a9de4905c786b774d10ad728ed392f`.
All other accepted Stage 8 fingerprints remain as listed in the design.
Stage 8 source and all Stage 0–8 scientific assets are untouched. The accepted
audit is not reopened; protected artifacts are not rehashed or accessed.

Stage 10 handoff: **BOUNDARY_HANDOFF_SUFFICIENT**, via immutable Stage 8 source/
candidate identity to Stage 6's complete Stage 5-preserving row map and original
STANDARD/NATIVE lines 1–4 and masks. No convenience upstream changes.

HOLDOUT remains sealed. Production and Pelias remain untouched. No SLURM,
protected DEVELOPMENT materialization, geocoding, new parser, address-validation
API or Stage 9 materializer is run or implemented.

NEXT: STAGE 9 IMPLEMENTATION + SYNTHETIC TESTS + DEVELOPMENT RUN
