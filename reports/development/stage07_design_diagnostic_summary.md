# Stage 7 DEVELOPMENT design-diagnostic summary

## Verdict

`STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY`

The exact offline parser bundle was frozen successfully, and the complete
123-group lowercase/case-preserving comparison passed. The controlled design
diagnostic nevertheless exposed a material giant-input limitation: four of 23
accepted candidates with at least 1,000,000 code points crashed their isolated
native libpostal parser process, including the accepted maximum-length
candidate. The session stopped before freezing a contract/profile or beginning
implementation.

This is not Stage 7 acceptance. It is not a candidate for independent review.
HOLDOUT, production Stages 2–7, Stage 8, geocoding, and external protected-data
transmission did not occur.

## Scientific identity

- Base main: `76435eb7ca5cd9a47a2a77fb36278568ba3bfc29`
- Design commit: `f437ec0f68e37d5cde197a97e761ad57cf201361`
- Diagnostic implementation: `48c66f7beb0437d7f0a6cea575c560a2a9c6c920`
- Successful parser-bundle job: `1760151`
- Controlled diagnostic job: `1760156` (`COMPLETED`, exit `0:0`)
- Diagnostic evidence SHA-256:
  `7b09fb79a6ef905c1e41d9387fc7ebfa5a24b257c8aee50d779f96aa47e32283`
- Diagnostic selection fingerprint:
  `a81995f832f89cdc5053827d6479c2170641815a44f3e64c90c9d3a6816fe3df`
- Diagnostic gate: `SCIENTIFIC_CONFLICT`
- Conflict codes: `GIANT_CANDIDATE_PARSER_LIMITATION` and
  `PROTECTED_CANDIDATE_PARSER_FAILURE`

Proposed contract/profile names were
`stage07_libpostal_parsing_contract_v1` and
`stage07_libpostal_parsing_profile_v1`. They were not frozen. There is no
Stage 7 implementation SHA, authoritative output, schema fingerprint, logical
fingerprint, input-binding fingerprint, or manifest fingerprint.

## Accepted Stage 6 binding

- Contract: `stage06_early_exact_deduplication_contract_v1`
- Profile: `stage06_early_exact_deduplication_profile_v1`
- Schema fingerprint:
  `9c07b7a4c3f7a5c43ad457dcf6f7fe3fd746d54d82a731139905b30828b6c9ce`
- Logical fingerprint:
  `2f6379c0cd5dc9654c03895cae6fdd48f3a7af528158c33e44d2030c816640b6`
- Input-binding fingerprint:
  `6ba224d6d24c3631aae8aac69f4a362bb054f01d9e3d09327ec6b0fdd85a0e7d`
- Manifest fingerprint:
  `e1da7b8ef04b65b1ece8e710720b57a8536841766fcf9de641f889b42eadd241`
- Ordered source identity:
  `fe2a4758582c1880d2b5c62dfc5c587d865e05d13033af9f5e8208b58e2a0487`
- Benchmark fingerprint:
  `014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf`
- Fixed-500 fingerprint:
  `014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52`
- Registry rows: 51,779
- Occurrences: 69,747 total; 34,822 STANDARD; 34,925 NATIVE

The exact intended parser input was the accepted
`stage06_candidate_lower`, with no SAFE trim, normalization, added context,
country/language hint, or appended geographic field.

## Frozen public parser bundle

- libpostal source commit:
  `25099c506612b34b23b1bfe286ca6321fcf06f35`
- libpostal implementation/version: 1.1.4,
  `v1.1.4-2-g25099c50`
- Installed ABI binary: `libpostal.so.1.0.1`
- Shared-library SHA-256:
  `3e2aa3e23b62c22b77827b47d78692d49ae3d693c07ee7ad3763e9b97438cb5e`
- pypostal source commit:
  `d6666a4f6a2ae0e7b83e037a35412f0f6b45c318`
- pypostal version/description: 1.1.11, `1.1-53-gd6666a4`
- Pypostal runtime fingerprint:
  `ccc547bfdcaf391685cbb3285be9a02d84c28c7671dcafb4450d25c03920f7ff`
- Upstream default model asset versions: base/parser/language-classifier
  `v1.0.0`
- Model/data fingerprint:
  `0b067a2697e9f90cef92c806701c08648a1f5127c17f0f3168ecaed186dc3293`
- Complete parser-bundle fingerprint:
  `f3c6db7e9f11ab75b2207be773e946d531dbba763008d9f7e5036d8c923dc2ae`
- Bundle manifest SHA-256:
  `12a0080bff6b3ed2420847124eb918d91b7582214e3d4b037628bf5b9022340d`
- Bundle contents: 56 hashed artifacts; 2,013,605,137 bytes
- Runtime: Python 3.14.3, Unicode 16.0.0, UTF-8
- Parser call: `postal.parser.parse_address(exact_candidate)`
- Options/hints: wrapper default, context-free, none added by SAFE
- Initialization: once per parser process
- Concurrency: one canonical parser process; isolated one-candidate child
  processes only for giant safety diagnostics

The copied code licenses are libpostal MIT, bundled Sparkey Apache-2.0, and
pypostal MIT. No license/notice file was present in the downloaded upstream
model assets; the bundle records the absence and makes no additional license
claim.

## Diagnostic scope and structural output

- Selected candidates: 986
- Fixed-500 unique candidate IDs included: all 613
- Multi-clean-surface groups included: all 123
- Clean/case-preserving surfaces tested: all 246
- Giant candidates included: all 23
- Successful parses: 982
- `PARSED_NONEMPTY`: 979
- `PARSED_EMPTY`: 3
- Parser process crashes: 4
- Emitted components: 2,481,811
- Component count min/median/mean/p95/p99/max:
  0 / 2 / 2,527.302444 / 7 / 110,089 / 263,385
- Single-component parses: 231
- Candidates with at least eight components: 48
- Candidates with repeated labels: 184
- Maximum repetition of one label in a candidate: 68,431
- Output-value code points min/median/mean/p95/p99/max:
  0 / 26 / 66,001.437882 / 119 / 2,426,199 / 7,725,211

The high component tails are driven by accepted giant/adversarial input and
are structural risk indicators, not semantic correctness labels.

## Label vocabulary and frequencies

The diagnostic observed 19 exact libpostal labels. Stage 7 did not map,
rewrite, sort, combine, or discard them.

| Label | Components |
|---|---:|
| `category` | 17 |
| `city` | 421,225 |
| `city_district` | 39,783 |
| `country` | 74,022 |
| `country_region` | 79 |
| `entrance` | 107 |
| `house` | 510,924 |
| `house_number` | 389,953 |
| `island` | 413 |
| `level` | 38,137 |
| `near` | 349 |
| `po_box` | 2,667 |
| `postcode` | 237,301 |
| `road` | 461,017 |
| `staircase` | 12,396 |
| `state` | 20,719 |
| `state_district` | 110,204 |
| `suburb` | 100,318 |
| `unit` | 62,180 |

## Stratified results

Successful results by candidate length were:

| Code-point stratum | Candidates | Nonempty | Empty | Components |
|---|---:|---:|---:|---:|
| 1–24 | 432 | 429 | 3 | 846 |
| 25–99 | 474 | 474 | 0 | 1,399 |
| 100–1,023 | 35 | 35 | 0 | 119 |
| 1,024–999,999 | 22 | 22 | 0 | 220,593 |
| at least 1,000,000 | 19 | 19 | 0 | 2,258,854 |

Four additional giant candidates produced `PROCESS_CRASH` and are excluded
from successful-result component strata. The maximum 25,920,495-code-point
candidate did not yield a complete exact parse.

Successful results by Stage 6 representation contribution were:

| Provenance | Candidates | Nonempty | Empty | Components |
|---|---:|---:|---:|---:|
| BOTH | 465 | 465 | 0 | 1,037 |
| NATIVE only | 309 | 308 | 1 | 1,812 |
| STANDARD only | 208 | 206 | 2 | 2,478,962 |

The deterministic sample covered Latin, Arabic/Persian, Cyrillic, Han,
Hangul, Armenian, Georgian, Greek, Hebrew, Lao, Thai, mixed-script, common-only,
and giant-input strata. Per-script candidate/component counts are preserved in
the JSON companion without protected values.

## Case safety and determinism

- Groups tested: 123
- Clean surfaces tested: 246
- Exact-equality groups: 123
- Parse-difference groups: 0
- Label/value/component-count/order/empty-state difference groups: all 0
- Clean-surface parser errors: 0
- Lowercase parse-once safety conclusion for the tested groups: **PASS**
- Determinism candidates: 64
- Same-process mismatches: 0
- Fresh-process batch-1 mismatches: 0
- Fresh-process reversed batch-17 mismatches: 0
- Fresh-process outcomes: both **PASS**
- Worker-count invariance: not tested; the proposed execution policy used one
  ordinary parser process and assumed no native thread safety

## Giant-candidate conflict

Of all 23 accepted giant candidates, 19 returned complete parse results and
four isolated native parser processes terminated without a valid result. The
maximum accepted candidate was among the failures. SAFE passed exact full
strings and performed no truncation, substring parse, regex preprocessing,
component synthesis, or hidden recovery.

This blocks the proposed fail-closed contract because a successful full
51,779-candidate materialization cannot currently cover every accepted Stage 6
registry row. A crash cannot be silently converted to `PARSED_EMPTY` or
represented as an exact ordered libpostal result. The minimum scientific next
step is explicit owner review of where exact giant-candidate failure semantics
belong before another Stage 7 contract is proposed. This report does not reopen
Stage 6 or choose a recovery policy.

## Runtime, permissions, and boundedness

- Parser/model initialization: 4.542275 s
- Non-giant canonical parse runtime: 9.508996 s
- Giant isolated-parse runtime: 349.376496 s
- Diagnostic processing runtime: 423.715916 s
- Total SLURM elapsed: 471 s
- Total CPU: 432.071 s (user 352.462 s; system 79.609 s)
- Overall risk-heavy diagnostic throughput: 2.327031 candidates/s and
  5,857.252244 components/s
- Non-giant diagnostic throughput: 101.272517 candidates/s
- SLURM MaxRSS: 25,062,976 KiB
- Requested resources: one task, four CPUs, 64 GiB, 12-hour limit
- Submitted/started/ended: 2026-08-28 11:17:44 / 11:18:09 / 11:26:00
  cluster local time
- Publication: immutable, fsynced, atomic, owner-only
- Protected directories/files/logs: `0700` / `0600` / `0600`
- Output files: two, no permission violations, no symlinks

This diagnostic is not population-representative and includes risk-heavy giant
inputs. No production throughput projection is scientifically reported. No
production-capable Stage 7 materializer exists, so the bounded-memory verdict
for authoritative output is not applicable. Static inspection found three
`to_pylist` calls limited to frozen 500-row review-mapping metadata in the
diagnostic selector; no Stage 7 materializer, pandas use, population-sized
candidate map, or whole-registry parse-output buffer exists.

## Work correctly not performed after the conflict

No authoritative 51,779-candidate DEVELOPMENT parse was submitted. Therefore
there are no Stage 7 candidate rows, full dropped/added/duplicate-ID metrics,
post-publication validation, output serialization evidence, full source-map
coverage proof, full fixed-500 machine verification, risk-stratified
qualitative review, qualitative HTML, schema/logical/input-binding/manifest
fingerprints, output bytes, serialization/publication timings, or production
planning projection.

The diagnostic did include all 613 fixed-500 unique candidate IDs, but that is
not a substitute for the required fixed-500 machine verification against a
published Stage 7 registry.

## Failed-attempt provenance

Public-only bundle attempts `1760085`, `1760128`, `1760131`, `1760139`,
`1760146`, `1760148`, and `1760150` failed during controlled path validation,
autotools setup, public acquisition, ABI expectation, or shell-variable
handling. Each failure is documented in the Stage 7 record; none opened
protected data or published an immutable bundle.

Protected diagnostic job `1760154` failed at the evidence harness after an
isolated child closed its pipe; it published no final result. The replacement
job recorded such events as `PROCESS_CRASH`, which exposed rather than masked
the scientific limitation. Failed logs, roots, and incomplete attempts remain
owner-only and immutable.

The first final local focused-test command used the system Python and failed
during collection because the project package and PyArrow were unavailable in
that interpreter. No test ran. The unchanged suite was immediately rerun with
the existing repository virtual environment and this worktree's `src`, passing
all 32 focused tests.

## Local-safe handoff gates

- Focused Stage 7 tests: 32 passed
- Stage 2–7 regression tests: 207 passed
- Full local-safe suite: 474 passed; four production-transfer tests deselected
- Ruff: pass
- Strict mypy: pass, 68 source files
- Changed Stage 7 Python formatting: pass, eight files
- `git diff --check`: pass
- Stage 7 Bash/SLURM syntax: pass, three assets
- Sanitized JSON parsing and internal Markdown links: pass
- Privacy/tracked-data audit: pass; no protected artifact type or controlled
  path was added to Git

## Scope and privacy

- HOLDOUT accessed: **NO**
- Production Stage 2 started: **NO**
- Production Stage 3 started: **NO**
- Production Stage 4 started: **NO**
- Production Stage 5 started: **NO**
- Production Stage 6 started: **NO**
- Production Stage 7 started: **NO**
- Stage 8 started: **NO**
- Geocoding performed: **NO**
- Protected input sent to an external service: **NO**
- Stage 7 accepted: **NO**

No protected candidate value, parser output, source identity, source filename,
company name, or stable candidate ID appears in this report.

## Required next decision

There is no independent-review target because the DEVELOPMENT candidate is not
ready. Before another Stage 7 development attempt, the owner must explicitly
review and approve a scientifically reproducible policy for accepted giant
candidates that libpostal cannot parse exactly. Any later candidate must use a
fresh immutable implementation/output and undergo the full authoritative,
fixed-500, qualitative, and independent-review gates.
