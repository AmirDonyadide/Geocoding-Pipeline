# Stage 4 — Lowercase canonical forms

## Purpose

Create stable, case-normalized derived representations from the accepted Stage
3 clean text for later reconstruction, deduplication, parsing, component
normalization, validation, and matching. Stage 4 performs exactly one
scientific text operation and never overwrites an upstream value.

## Input boundary

The authoritative DEVELOPMENT run is restricted to the accepted 35,000-row
Stage 3 bundle. `stage04_input_binding_v1` binds:

- `stage03_safe_text_cleaning_contract_v1` and
  `stage03_safe_text_cleaning_profile_v1`;
- Stage 3 logical fingerprint
  `38df499bfaf61883832a9c718adf4cf92cfcea753337df68fa2e89afb6051bdb`;
- Stage 3 schema fingerprint
  `fc991ef63bd80a754114ecae6a9d3c4cf1f33a35a28581fea997edd2e4565c9b`;
- Stage 3 input-binding SHA-256
  `6a2a28d276884511f5b8f63f40d14d6b7f4bf4397aa09289c53acdb92a661e6f`;
- Stage 3 manifest SHA-256
  `8f70745e31185abce52fdc1685c2b767f90874c21596152ea0463ec6677478d4`;
- ordered stable-identity digest
  `fe2a4758582c1880d2b5c62dfc5c587d865e05d13033af9f5e8208b58e2a0487`;
- Benchmark V1 fingerprint
  `014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf`;
  and
- exactly 35,000 DEVELOPMENT rows.

The binding and launcher reject a different Stage 3 boundary, any path naming
HOLDOUT, and non-owner-only or incomplete protected artifacts before Stage 4
input values are processed.

## Scientific contract

The contract is `stage04_lowercase_canonical_contract_v1`; its exact profile is
`stage04_lowercase_canonical_profile_v1`. For each applicable Stage 3 clean
string `value`, the definition is:

```python
stage04_value = value.lower()
```

The authoritative runtime is Python 3.14.3 with Unicode 16.0.0. The operation
is locale-independent Python Unicode lowercasing. Casefolding is not used;
locale-specific casing is not used; and no NFC, NFD, NFKC, NFKD, or other
normalization is applied after lowercasing. Exact `str.lower()` output is the
scientific result even when a mapping changes code-point length.

Stage 3 already owns cleaning and NFC normalization. Stage 4 does not repeat or
repair Stage 3 work. Exact accepted Stage 3 bundle validation is the fail-closed
precondition.

## Unicode behavior

Synthetic contract vectors under Python 3.14.3 / Unicode 16.0.0 include:

| Input | Exact `str.lower()` result | Note |
|---|---|---|
| `MAIN STREET` | `main street` | ASCII |
| `Main Street 10` | `main street 10` | Mixed ASCII |
| `ÉCOLE` | `école` | Accented Latin |
| `STRAẞE` | `straße` | Uppercase sharp S lowers to sharp S |
| `STRASSE` | `strasse` | No casefold equivalence is asserted |
| `ß` | `ß` | Already lowercase |
| `I` | `i` | Locale-independent |
| `İ` | `i` plus U+0307 | Length-changing Unicode mapping |
| `ı` | `ı` | Locale-independent |
| `ΟΣ` | `ος` | Context-sensitive final sigma |
| `Σ` | `σ` | Standalone sigma |
| `МОСКВА` | `москва` | Cyrillic |
| Arabic/Persian, CJK, Hangul | unchanged | Representative uncased scripts |

Decomposed synthetic text remains decomposed except for casing changes. For
example, `E` + U+0301 + `COLE` becomes `e` + U+0301 + `cole`; Stage 4 does not
silently add normalization. An exhaustive Unicode 16.0 scalar diagnostic found
one scalar length-expanding lower mapping (U+0130), no scalar contraction, and
no NFC scalar whose lower result ceased to be NFC. This diagnostic does not
change the exact-output rule.

PyArrow 25.0.0 `utf8_lower` is not scientifically equivalent: it produces `i`
for U+0130 and non-final sigma for `ΟΣ`. It is therefore prohibited. The only
vectorized path is `ascii_lower` for values first proved ASCII; a large
deterministic Unicode differential test requires zero mismatches against Python
`str.lower()`.

## Column mapping

Every incoming Stage 3 column is retained exactly. Stage 4 appends these 12
derived strings:

| Stage 3 input | Stage 4 output |
|---|---|
| `stage03_clean_street_address_line_1` | `stage04_lower_street_address_line_1` |
| `stage03_clean_street_address_line_2` | `stage04_lower_street_address_line_2` |
| `stage03_clean_street_address_line_3` | `stage04_lower_street_address_line_3` |
| `stage03_clean_street_address_line_4` | `stage04_lower_street_address_line_4` |
| `stage03_clean_street_address_line_1_native` | `stage04_lower_street_address_line_1_native` |
| `stage03_clean_street_address_line_2_native` | `stage04_lower_street_address_line_2_native` |
| `stage03_clean_street_address_line_3_native` | `stage04_lower_street_address_line_3_native` |
| `stage03_clean_street_address_line_4_native` | `stage04_lower_street_address_line_4_native` |
| `stage03_clean_postcode` | `stage04_lower_postcode` |
| `stage03_clean_city` | `stage04_lower_city` |
| `stage03_clean_region_in_country` | `stage04_lower_region_in_country` |
| `stage03_clean_country_iso_code` | `stage04_lower_country_iso_code` |

`stage04_changed_fields` is a non-null ordered list of base source-field names
whose clean/lower pair differs. `stage04_row_changed` is true exactly when that
list is non-empty. The audit contains no character-level log or semantic
reason vocabulary because Stage 4 has only one operation.

## Validation and evidence design

Materialization and independent readback are bounded by Parquet row group,
configured rows, and target uncompressed bytes. They do not use pandas or a
Python identity set proportional to total rows. The accepted upstream
duplicate-free invariant plus the exact ordered identity digest proves identity
preservation.

After atomic publication, a separate bounded validator reopens both the
accepted Stage 3 bundle and immutable Stage 4 output. It checks every incoming
Stage 3 array again, every derived value against Python lowercase semantics,
audit consistency, idempotence, row counts, identity order, manifest/artifact
hashes, page checksums, permissions, and atomic publication. DEVELOPMENT
diagnostics report change counts by field and group, coarse Unicode Script
classes from the pinned Unicode 16.0 Scripts reference, length changes, empty
transitions, engine-path counts, timing, CPU, MaxRSS, throughput, and a
planning-only production projection.

The protected fixed-500 artifact preserves the frozen identity order and
contains raw covered fields, Stage 3 clean fields, Stage 4 lowercase fields,
both stages' audit fields, and Stage 2 structural fields. Its deterministic
contract classifications are `EXPECTED_CASE_NORMALIZATION`,
`BENIGN_UNCHANGED_SCRIPT`, `NO_CASE_CHANGE_REQUIRED`, `QUESTIONABLE`, and
`SEMANTIC_DAMAGE`. It is a comparison surface for independent human scrutiny;
it is not independent acceptance by this development session.

## Non-goals

Stage 4 does not casefold, apply locale rules, normalize Unicode after lower,
trim or collapse whitespace, repair encoding, alter punctuation, transliterate,
translate, expand abbreviations, reconstruct or parse addresses, infer or
validate components, correct values, fuzzy match, deduplicate source rows,
geocode, or call an external service.

## DEVELOPMENT evidence

The final candidate implementation is
`0d98ff6450875dfe8fb37c84729e5bbe632ef2fb`. Goethe-NHR SLURM job `1759421`
executed that exact pushed SHA from a clean detached worktree and completed with
exit code zero. Its immutable identities are:

- Stage 4 logical fingerprint:
  `054c66701f854a0108938170e1cb9bcee8a772f7fed29b82cda53c71aa9747ec`;
- Stage 4 schema fingerprint:
  `dafb4f78b8bfce3120b6f4f7ae8cb44883f4c3a9cfd94b3137871b83c0ed5cbc`;
- Stage 4 input-binding SHA-256:
  `90e0e94d4359bd5927820dfc06b2cfc1dc37485c032d95726d1260ec88a534b0`;
- Stage 4 manifest SHA-256:
  `17a4854cddd8929b65ea79402f1a4f12a1574b720c1921567b577f23e152d1f3`;
- ordered identity digest:
  `fe2a4758582c1880d2b5c62dfc5c587d865e05d13033af9f5e8208b58e2a0487`;
- fixed-500 review artifact SHA-256:
  `0a8fb68b2f4dfb332d3c8fde431898c2229aed42a3cd27184c5ac0f0a12fe75b`;
  and
- fixed-500 review manifest SHA-256:
  `95f450948daddbbee065cf0a3742ab723549dd5ab69d00fc3186f2ce3bc2ad5c`.

Independent post-publication validation reopened both the accepted Stage 3
bundle and the immutable Stage 4 output. It confirmed 35,000 input and output
rows, zero dropped or added rows, exact identity order, and exact equality of
every incoming Stage 3 column. All 420,000 derived fields equalled their clean
input's Python `str.lower()` result, with zero idempotence failures and zero
empty/nonempty transitions.

Lowercase changed 34,994 rows and 186,166 fields; 6 rows and 233,834 fields
were unchanged. Changed-field counts were 55,388 standard address-line fields,
36,489 native address-line fields, 31,411 city fields, 27,500 region fields,
34,359 country-source-geography fields, and 1,019 postcode fields. There were
181,549 ASCII case changes, 4,617 Unicode case changes, and no observed
length-changing lowercase mapping in DEVELOPMENT. Maximum length increase and
decrease were both zero.

The aggregate Script diagnostic covered 210,274 ASCII-only, 1,927 non-ASCII
Latin, 2,107 Cyrillic, 220 Greek, 3 Arabic/Persian, 18,501 CJK/Hangul, 1,807
mixed, 508 other, and 184,653 empty field values. Uncased-script values were
natural no-ops; standard and native fields were processed under the same rule.

The protected fixed-500 view retained the exact frozen identities and order.
All 500 rows were classified `EXPECTED_CASE_NORMALIZATION`; `QUESTIONABLE` and
`SEMANTIC_DAMAGE` were both zero. The view remains a protected comparison
surface for the independent reviewer, not acceptance evidence from an
independent session.

Materialization took 22.487 seconds, including its first complete readback,
with 20.095 seconds user CPU, 2.194 seconds system CPU, and 1,362,428 KiB
process peak RSS. Throughput was 1,556.455 rows/second and 18,677.458
fields/second. The row-linear projection to 141,048,582 rows is 90,622 seconds
(about 25.2 hours); it is a planning estimate, not a guarantee. Total job wall
time, including isolated runtime setup, separate published validation, and
fixed-500 review, was 76 seconds. SLURM recorded 56.640 seconds total CPU and
1,004,468 KiB batch-step MaxRSS. Processing remained bounded by at most 2,048
rows and a 256 MiB target uncompressed batch size.

Two earlier attempts are preserved. Job `1759398` failed in zero seconds,
before runtime setup or protected input access, because the path guard compared
a canonical `/panfs` child to an uncanonicalized `/work` root; commit
`1ffe46f662088b49710f367ace522e5dad956973` fixed the guard. Job `1759399`
then produced byte-identical scientific Parquet and fixed-500 review evidence,
but its per-character Script diagnostic made materialization take 342.997
seconds. The final bounded code-point cache and early bucket resolution retain
exact diagnostic classifications; deterministic differential tests and the two
DEVELOPMENT runs produced identical aggregate-metric, Stage 4 Parquet, review
Parquet, logical, and schema identities.

The focused Stage 4 suite passed 50 tests. The policy-compliant local-safe suite
passed 380 tests with four controlled production-transfer tests deselected.
Ruff, mypy, changed-file formatting, `git diff --check`, shell syntax, Markdown
links, and the tracked/protected-data audit passed. See the Git-safe aggregate
[summary](../../reports/development/stage04_summary.md).

## Production and later-stage status

Production Stage 2, Stage 3, and Stage 4 are **NOT STARTED**. Stage 5 is **NOT
STARTED**. No production or geocoding authorization is implied.

## Current status

**`STAGE_4_ACCEPTED` on DEVELOPMENT.**

A fresh independent review bound candidate head
`4b6c60c3fb07bb33043e6d31cae3e88bac23393b`, authoritative implementation
`0d98ff6450875dfe8fb37c84729e5bbe632ef2fb`, and job `1759421`. Independent
SLURM job `1759473` ran the review-only harness at
`2b77aab03526a4949682cacc0d77db40b7ef9c87` under Python 3.14.3, Unicode
16.0.0, and PyArrow 25.0.0. It independently streamed all 35,000 rows, compared
all 40 incoming Stage 3 columns and all 420,000 derived values, reconstructed
the ordered identity and Stage 4 fingerprints, and reproduced every reported
aggregate with zero mismatches.

The independent fixed-500 audit reconstructed the frozen fingerprint and
identity order, then evaluated all 500 rows and 2,466 changed value pairs.
Every change was exact Unicode lowercase casing; non-case code-point changes,
length changes, `QUESTIONABLE`, and `SEMANTIC_DAMAGE` were all zero. A separate
52,375-value optimized-path differential, exhaustive Unicode scalar scan, and
2.75-million-code-point giant value test also passed. The aggregate review
artifact SHA-256 is
`972fb34d6084fc10aede4570bc35b594b948f85cbe5987dcdfe78812724a30c5`.

Review-only jobs `1759437` and `1759438` are preserved as launcher failures.
Both failed in one second on controlled-path canonicalization before any
DEVELOPMENT scan and produced no review artifact; neither is a Stage 4
candidate defect.

Production Stage 2 through Stage 4 and Stage 5 remain **NOT STARTED**. This
acceptance does not authorize them.
