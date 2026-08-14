# Phase 3 executable rule-registry review

## DEVELOPMENT parser-v2 amendment

This file's original review below remains the historical review of the frozen
12-rule `phase03_rule_registry_v2` used by
`conservative_address_parser_v1`. Protected DEVELOPMENT evidence later rejected
that parser for materially inadequate street-address recall.

The approved DEVELOPMENT successor is the 16-rule
`phase03_rule_registry_v3` (canonical SHA-256
`a2aadae857b7d4bf7262bd37e6dacf58aae220e00b402ca971c51cea320d6f55`),
paired only with `conservative_address_parser_v2`. It retains all v1 structured
geography, country, PO-box, historical, placeholder, reference, safety, and
shadow-house boundaries while adding bounded explicit and generic selectable
street/house, unit, floor, building, and organization rules. The packaged
`street_designators_v2` resource has 56 entries across seven explicitly scoped
families and raw SHA-256
`0bfbc60f843f8ecf8c3b84cc05e7f342a3da6f5f0f18f1961623566d15dc28cf`.
Its exact rule-by-rule precedence, marker scope, false-positive boundaries,
native-conflict behavior, tests, and Goethe execution boundary are authoritative
in `docs/PHASE03_PARSER_V2.md`.

Registry v3 is a DEVELOPMENT revision only. It does not change the frozen
sampling contract or identity sets, and it is not authorized for the sealed
LOCKED_EVALUATION subset.

## Registry identity

The reviewed executable registry is
`src/safe_geocoding_pipeline/phase03/resources/rule_registry_v2.json`:

- registry version: `phase03_rule_registry_v2`;
- SHA-256 of canonical registry JSON:
  `d1448859f8436dbe466cab81aee926ab6851b294f5ec664491840bac84627fd5`;
- actual rule count: **12**;
- maximum input for every rule: `65536` UTF-8 bytes.

No authoritative rule was added, broadened, or promoted, and the house matcher
grammar is unchanged. Registry schema v2 adds a closed scientific execution
disposition and retains same-span house candidates as development shadow
evidence, which changes the registry identity and effective configuration
fingerprint.

## Rule-by-rule readiness

`AS` means authoritative selectable, `AC` authoritative candidate-only, `AD`
authoritative diagnostic-only, and `DS` development shadow-only. The country
collision guard remains encoded in candidate behavior inside `AS`. Test
references name executable pytest coverage or an explicit development
measurement boundary.

| Rule ID / version | Component; eligible fields | Matcher → extractor | Confidence; priority; mode; max | References | Registry-required tests | Positive / negative / false-positive boundary evidence | Status |
|---|---|---|---|---|---|---|---|
| `POSTCODE_STRUCTURED_DIRECT_V1` / 1 | POSTCODE; `postcode` | whole content → whole raw span | HIGH; 10; AS; 65536 | none | direct positive; leading zero; placeholder negative | structured-string/leading-zero tests; exact placeholder tests; safety-limit tests | **READY_FOR_DEVELOPMENT_PILOT** |
| `LOCALITY_STRUCTURED_DIRECT_V1` / 1 | LOCALITY; `city` | whole content → whole raw span | HIGH; 20; AS; 65536 | none | direct positive; placeholder negative; conflict | structured propagation; placeholder behavior; deterministic generic locality-conflict test | **READY_FOR_DEVELOPMENT_PILOT** |
| `REGION_STRUCTURED_DIRECT_V1` / 1 | REGION; `region_in_country` | whole content → whole raw span | HIGH; 30; AS; 65536 | none | region direct; placeholder negative; conflict | structured propagation; placeholder behavior; deterministic generic region-conflict test | **READY_FOR_DEVELOPMENT_PILOT** |
| `COUNTRY_STRUCTURED_REFERENCE_V1` / 1 | COUNTRY; `country_iso_code` | exact controlled reference → alpha-2 | HIGH; 40; AS; 65536 | logical `COUNTRY_ASSIGNMENTS`, `COUNTRY_NAMES` roles supplied by the ISO-normative/CLDR-operational model | `NA`; `Na` collision; `Nan`/`Null`; conflict | CLDR-production alpha-2/alpha-3/canonical-name/case/unknown/region/placeholder/corroboration tests all pass | **READY_FOR_DEVELOPMENT_PILOT** |
| `COUNTRY_FREEFORM_REFERENCE_V1` / 1 | COUNTRY; all eight address fields | exact whole-field controlled reference → alpha-2 | MEDIUM; 50; AC; 65536 | same country roles | exact; substring negative; placeholder corroboration | exact fictional and CLDR canonical names; substring/guessing absent; `Na` requires independent exact compatible evidence | **READY_FOR_DEVELOPMENT_PILOT** |
| `PO_BOX_MARKER_EN_V1` / 1 | PO_BOX; all eight address fields | marker plus following identifier → marker-and-identifier span | HIGH; 60; AS; 65536 | `po_box_markers_en_v1` | positive; marker alone; substring; identifier boundary | every marker positive; marker-alone/substrings negative; token and identifier limits tested | **READY_FOR_DEVELOPMENT_PILOT** |
| `UNIT_MARKER_EN_V1` / 1 | UNIT; all eight address fields | marker plus following identifier → identifier span | HIGH; 70; AS; 65536 | `unit_markers_en_v1` | positive; bare number; substring; house ambiguity | every marker positive; bare/substrings negative; same-span shadow house evidence is retained without a core conflict | **READY_FOR_DEVELOPMENT_PILOT** |
| `FLOOR_MARKER_EN_V1` / 1 | FLOOR; all eight address fields | marker plus following identifier → identifier span | HIGH; 80; AS; 65536 | `floor_markers_en_v1` | positive; ordinal negative; substring | every marker positive; unmarked/substring cases negative; exact token boundary | **READY_FOR_DEVELOPMENT_PILOT** |
| `BUILDING_MARKER_EN_V1` / 1 | BUILDING; all eight address fields | segment-leading marker and bounded name → identifier span | HIGH; 90; AS; 65536 | `building_markers_en_v1` | positive; segment-end negative; name boundary | every marker positive; `North Building` negative; leading-position and 4-token/64-code-point bounds executable | **READY_FOR_DEVELOPMENT_PILOT** |
| `ORGANIZATION_LEGAL_FORM_EN_V1` / 1 | ORGANIZATION; all eight address fields | segment-ending legal form → whole trimmed segment | MEDIUM; 100; AC; 65536 | `organization_legal_forms_v1` | positive; form alone; building ambiguity | every form positive; form-alone/substrings negative; building/organization overlap becomes conflict | **READY_FOR_DEVELOPMENT_PILOT** |
| `HISTORICAL_MARKER_EN_V1` / 1 | diagnostic only; all eight address fields | exact phrase present → phrase span | HIGH; 110; AD; 65536 | `historical_markers_en_v1` | positive; unlisted language; substring | every phrase positive; unlisted/substrings negative; never selects an address component | **READY_FOR_DEVELOPMENT_PILOT** |
| `HOUSE_NUMBER_EDGE_CANDIDATE_V1` / 1 | HOUSE_NUMBER; all eight address fields | bounded start/end token or three-token range → matched edge span | LOW; 120; DS; 65536 | none | edge; date negative; postcode negative; unit ambiguity | deterministic shadow evidence and scope isolation tested; known calendar/postcode/unit boundaries are development measurement cohorts, not authority | **READY_FOR_DEVELOPMENT_PILOT** — shadow measurement only |

## Marker-bundle review

All bundles are **English v1**, not multilingual. Matching tokenizes the raw
string with source offsets, NFC-normalizes each token for comparison, and
ASCII-lowercases ASCII tokens. Non-ASCII case folding is not performed.
Extraction then applies the separately versioned derived-text normalization;
raw spans remain anchored to the pre-normalized source. Marker sequences match
whole tokens only, not substrings.

| Group | Exact count and scope | Matching boundary | Positive/negative coverage | Main residual risk |
|---|---|---|---|---|
| PO box | 4 sequences: `po box`, punctuated `p.o. box`, spaced `p o box`, `post office box` | requires one following word identifier, max 32 code points | all 4 positive; marker-alone, joined substring, and missing identifier negative | a textual PO-box mention followed by a word can still be classified; pilot review is required |
| Unit/apartment/suite | 10 sequences: apartment, apt (with/without dot), suite, ste (with/without dot), unit, room, rm (with/without dot) | requires one following word identifier, max 32 code points | all 10 positive; bare number, bare marker, substring, and house-role overlap tests | “room” or “unit” in non-address prose may be a false positive |
| Floor/level | 6 sequences: floor, fl (with/without dot), level, lvl (with/without dot) | requires one following word identifier, max 32 code points | all 6 positive; unmarked/substring/bare-marker negatives | “level” in non-address prose may be a false positive |
| Building/block/tower | 5 sequences: building, bldg (with/without dot), block, tower | marker must start the trimmed segment; name stops at comma, semicolon, or newline; max 4 word tokens and 64 code points | all 5 positive; segment-ending and substring negatives; building/organization conflict | “block” and “tower” can denote non-address concepts; extracted name is intentionally bounded |
| Organization legal form | 14 sequences: ltd variants, limited, llc, inc variants, incorporated, corporation, corp variants, gmbh, plc, pte ltd, co., ltd. | form must end the trimmed segment and have an earlier word token | all 14 positive; form-alone and substring negatives; overlap conflict | legal form identifies organization-like text, not that it is a postal address; remains candidate-only |
| Historical/former wording | 5 phrases: former/previous/old address, address until, address valid until | exact token phrase anywhere in the safe field | all 5 positive; substring and unlisted-language negatives | literal wording can occur in commentary; the rule remains diagnostic-only |

## Street and house-number boundary

There is no executable street-scalar extraction rule. `street_clean` therefore
cannot be populated by this registry; no street promotion is authorized.

The house edge rule is LOW confidence with disposition
`DEVELOPMENT_SHADOW_ONLY`. Its matching grammar is unchanged. It recognizes:

- a start- or end-token containing a digit and no punctuation, up to 16 code
  points;
- pure numeric tokens only up to four digits;
- alphanumeric Unicode word tokens containing at least one digit;
- a three-token start/end range joined by `/` or `-`;
- zero-based raw source spans for both a full range and any independently
  qualifying endpoint tokens.

It rejects interior tokens, inputs without another alphabetic word token,
pure 5-plus-digit numeric tokens, 4-digit years from 1900 through 2099, and
tokens over 16 code points. Same-span unit/floor collisions remain visible in
development shadow evidence rather than being suppressed or turned into core
conflicts.

The current “date protection” is only the 4-digit-year rejection. Calendar-like
edge forms such as fictional `12/05 Road` remain candidates. The postcode
protection is only pure numeric length; alphanumeric postcode-like edge tokens
can remain candidates. Slash/hyphen ranges also emit qualifying endpoint
candidates. On the future development subset only, protected evidence retains
the candidate, raw code-point span, confidence, source field, and rule ID.
Portable reports expose aggregate counts only. Shadow candidates are excluded
from authoritative selection, completeness, parse status, diagnostics, core
conflicts, and readiness. They do not execute in locked evaluation or
authoritative scope.

A future selectable version requires protected development manual review, not
fill rate. Precision must be measured separately for ordinary edge integers,
alphanumeric edge tokens, numeric ranges, slash forms, hyphen forms,
calendar-like false positives, postcode-like false positives, unit/floor
collisions, and country/script cohorts where enough examples exist. Promotion
requires an explicitly approved grammar, exact spans, acceptable precision,
and a **new rule version**. V1 is never mutated into a selectable rule.
