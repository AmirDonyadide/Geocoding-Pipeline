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

The implementation and synthetic/unit design are complete. Authoritative
35,000-row Goethe-NHR execution and fixed-500 evidence are pending. This record
will be updated with the exact pushed implementation SHA, SLURM job, immutable
fingerprints, metrics, and candidate verdict after that single run completes.

## Production and later-stage status

Production Stage 2, Stage 3, and Stage 4 are **NOT STARTED**. Stage 5 is **NOT
STARTED**. No production or geocoding authorization is implied.

## Current status

**IMPLEMENTED DEVELOPMENT CANDIDATE — AUTHORITATIVE DEVELOPMENT RUN PENDING.**

This session does not independently accept Stage 4. A successful candidate
must stop at `STAGE_4_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW`.
