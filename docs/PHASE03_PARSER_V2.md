# Phase 3 DEVELOPMENT parser v2

Status: implemented and synthetically validated; real 8,000-row DEVELOPMENT
rerun requires a reviewed commit and a separately submitted Goethe-NHR job.
LOCKED_EVALUATION remains sealed and unopened.

## Evidence-led reason for revision

The first two completed DEVELOPMENT diagnostic reviews are preserved as audit
evidence for the rejected `conservative_address_parser_v1` iteration. They are
not a completed scientific review. Inspection of the executable v1 path confirms
the recall mechanism:

- `phase03_rule_registry_v2` contains no street-scalar rule;
- `HOUSE_NUMBER_EDGE_CANDIDATE_V1` is LOW-confidence
  `DEVELOPMENT_SHADOW_ONLY`, so it cannot populate core values;
- the organization legal-form rule is candidate-only;
- floor and building grammars cover only narrow marker-leading forms;
- `UNASSIGNED_CONTENT_PRESENT` is calculated after this deliberately narrow
  selection and therefore legitimately dominates many otherwise structured
  lines;
- `NATIVE_NON_NATIVE_HOUSE_NUMBER_CONFLICT` existed in the closed vocabulary
  but the engine never emitted it.

The revision changes only deterministic DEVELOPMENT parsing. It does not change
the already selected 8,000 DEVELOPMENT identities, the sealed 4,000 LOCKED
identities, sampling contract, Phase 2 data, core/evidence schemas, cleaning,
safety limits, or Phase 4 policy.

## Version identities

| Item | Frozen v1 baseline | DEVELOPMENT v2 |
|---|---|---|
| Parser | `conservative_address_parser_v1` | `conservative_address_parser_v2` |
| Registry | `phase03_rule_registry_v2` | `phase03_rule_registry_v3` |
| Registry schema | `phase03_rule_registry_schema_v2` | `phase03_rule_registry_schema_v3` |
| Registry SHA-256 | `d1448859f8436dbe466cab81aee926ab6851b294f5ec664491840bac84627fd5` | `a2aadae857b7d4bf7262bd37e6dacf58aae220e00b402ca971c51cea320d6f55` |
| Base config fingerprint | unchanged historical value | `75911fb4d202eff0af92bc805aa0cfe2844e25d72e0a2e322d5de61fd420274c` |
| Production-reference DEVELOPMENT effective fingerprint | unchanged historical value | `1f3496947da779e3b31ae6d8925c5ec75ea9d7714904846d9fca9194bfd28c2b` |
| Street-designator resource | not used | `street_designators_v2`, raw artifact SHA-256 `0bfbc60f843f8ecf8c3b84cc05e7f342a3da6f5f0f18f1961623566d15dc28cf` |

The v1 config/registry remain the package defaults so the frozen sampler and
historical commands cannot change silently. A v2 transform must explicitly pass
`--parser-version conservative_address_parser_v2`. Parser and registry versions
are validated as a closed pair.

The 52-column core and 20-column evidence schemas remain unchanged. Core and
evidence semantic-digest algorithms remain v1, but their resulting digest values
are expected to change because selected values, evidence, parser/registry
versions, configuration fingerprints, and the future reviewed implementation
fingerprint change.

## Rule registry v3 and precedence

Rules still execute by numeric priority, then UTF-8 rule ID. Unchanged
structured geography, country, PO-box, historical, placeholder, and reference
rules retain their v1 identities. Every canonical v3 rule record also carries
a non-empty `intended_positive_behavior` statement and an ordered, non-empty
`principal_negative_boundaries` list; the loader rejects missing or malformed
rule-level scientific documentation.

| Priority | Rule | Disposition and behavior |
|---:|---|---|
| 70 | `UNIT_EXPLICIT_SEGMENT_V3` | HIGH selectable; bounded Flat/Apartment/Apt/Suite/Ste/Unit/Room/Rm forms, optional explicit `No.`/`#` after a unit marker, identifier-only scalar, full evidence span |
| 80 | `FLOOR_EXPLICIT_SEGMENT_V3` | HIGH selectable; bounded Floor/Fl./Level/Lvl., ordinal suffix, `nF`, and `n/F` forms; digit-only scalar, full evidence span |
| 90 | `BUILDING_EXPLICIT_SEGMENT_V3` | MEDIUM selectable; bounded explicit building segments, rejected when a street designator or legal form establishes a competing role |
| 100 | `ORGANIZATION_LEGAL_FORM_V3` | MEDIUM selectable; exact segment-ending legal forms, independent of line position, with same-line segment support |
| 120 | `HOUSE_NUMBER_EXPLICIT_STREET_V3` | HIGH selectable; bounded leading/trailing rich house grammar paired with a versioned street designator |
| 121 | `STREET_EXPLICIT_DESIGNATOR_V3` | HIGH selectable; exact designator-bearing street span, with only the paired house span and permitted separator whitespace excluded |
| 122 | `HOUSE_NUMBER_GENERIC_STREET_V3` | MEDIUM selectable; language-light bounded house grammar plus meaningful Unicode street text and strict negative-role classifier |
| 123 | `STREET_GENERIC_SEGMENT_V3` | MEDIUM selectable; paired language-light Unicode street span under the same negative classifier |
| 130 | `HOUSE_NUMBER_EDGE_CANDIDATE_V1` | unchanged LOW DEVELOPMENT shadow evidence only |

`street_designators_v2` is a project-owned, versioned precision resource, not a
language detector or universal dictionary. It contains 56 reviewed entries in
seven scoped families: English, German, French, Italian, Spanish, Portuguese,
and Dutch. It includes exact token prefix/suffix markers and the attached German
`-straße`/`-strasse` and Dutch `-straat` suffixes. Matching uses NFC token
comparison, ASCII lowercase only for ASCII tokens, exact non-ASCII case, and
Unicode boundaries. The resource raw SHA-256 is bound into every dependent rule,
the registry fingerprint, and the effective configuration; changed data fails
engine startup closed.

One centralized bounded house grammar supports a one-to-four-digit integer,
contiguous/spaced/hyphenated one-letter suffix, bounded slash/hyphen/en-dash
pair, and original punctuation. The explicit HIGH rule additionally requires a
registered designator. The generic MEDIUM rule requires conservative meaningful
Unicode-letter content (at least two words for all-ASCII unmarked text), no
competing numeric interpretation, and no reserved PO-box, unit, floor,
building, organization, venue, date, decimal, year, postcode, or identifier
role. Four-digit years 1900–2099, five-plus-digit numbers, zero-padded
calendar-like slash forms such as `12/05`, bare numbers, phone/coordinate-like
strings, and numeric organization lines remain unresolved. Exact equality with
the structured postcode makes a house candidate non-selectable while retaining
protected candidate evidence.

PO-box, unit, and floor recognition precedes street/house selection. Their HIGH
source spans own the numeric role and suppress overlapping authoritative house
claims. `#number` is accepted only following an explicit unit marker, never as a
free-standing global unit rule. Same-line comma/semicolon/newline segments can
yield multiple non-overlapping roles. Unresolved selectable cross-component
span overlap emits the existing `COMPONENT_SPAN_OVERLAP_CONFLICT`; LOW shadow
evidence may coexist but is never selected.

Building v3 accepts only bounded segments with 2–12 word tokens, an alphabetic
name outside the marker, and at most 128 code points. Markers are Industrial
Centre/Center, Building/Bldg., Tower, Centre/Center, Block, Complex, and Plaza.
Because several are role-ambiguous, the rule is MEDIUM and rejects a segment
when the street resource establishes a street (`Tower Road`, `Block Street`) or
a legal form establishes an organization (`Building Society Ltd`). Independent
organization, building, street, unit, and floor segments may coexist across or
within source lines; line number has no semantics.

## Semantic precedence and span ownership

The implemented precedence is: structured geography and safety exclusion;
PO-box; explicit unit/floor; explicit building; legal-form organization;
historical diagnostics; explicit HIGH street/house; generic MEDIUM
street/house; unchanged LOW development shadow; deterministic candidate
selection and conflicts; native/non-native conflict reconciliation; residual
spans; completeness and status. This ordering is registry-fingerprinted.

Selection is still global per `(component, representation)`: multiple distinct
values fail closed rather than choosing by fill rate. Component spans retain
raw Unicode-codepoint, end-exclusive provenance. Separator punctuation is not
globally stripped. A selected unit/floor evidence span covers its explicit role
form while the scalar remains the identifier; selected street and house spans
cover their exact respective raw substrings.

## Selectable-rule false-positive boundaries

| Rule | Confidence | Strongest positive evidence | Main false-positive risk | Fail-closed boundary and synthetic evidence |
|---|---|---|---|---|
| `UNIT_EXPLICIT_SEGMENT_V3` | HIGH | exact bounded unit marker followed by one identifier; optional `No.`/`#` only after the marker | ordinary prose using “room” or “unit” | no bare number or free `#number`; exact token boundary; span owns number against house; bare/embedded/house-overlap negatives |
| `FLOOR_EXPLICIT_SEGMENT_V3` | HIGH | complete bounded marker/ordinal/compact floor form | `8F` could be a house suffix | compact floor must occupy its segment; explicit street context can instead establish house role; prefix/suffix/compact and house-context tests |
| `BUILDING_EXPLICIT_SEGMENT_V3` | MEDIUM | complete bounded segment with marker plus independent name text | Centre/Block/Plaza/Tower also occur in street or organization names | street-designator and legal-form arbitration runs before selection; `Research Center Road`, `Tower Road`, `Block Street`, and `Building Society Ltd` negatives |
| `ORGANIZATION_LEGAL_FORM_V3` | MEDIUM | exact registered legal form at bounded segment end with preceding word | a legal form proves role, not physical address status | no positional assumption, no title-case inference, legal form alone rejected, numeric organizations retain organization role and never provide house values |
| `HOUSE_NUMBER_EXPLICIT_STREET_V3` and `STREET_EXPLICIT_DESIGNATOR_V3` | HIGH | one bounded edge house form plus exact hash-bound designator and separate street name | marker homonyms and numbers in other roles | centralized numeric exclusions, higher-priority role span ownership, exact structured-postcode protection, street/building arbitration, date/year/phone/organization negatives |
| `HOUSE_NUMBER_GENERIC_STREET_V3` and `STREET_GENERIC_SEGMENT_V3` | MEDIUM | one bounded edge house form plus conservative meaningful Unicode street remainder | unmarked organization/venue/identifier text | two words for all-ASCII text, reserved-role exclusions, no other numeric token or known designator, no higher role, bare/date/year/decimal/postcode/phone/company/building negatives |

The unchanged structured geography/country rules retain their earlier reviewed
boundaries. `HOUSE_NUMBER_EDGE_CANDIDATE_V1` remains LOW protected shadow
evidence and is not a selectable-rule false-positive surface.

## Native/non-native and status behavior

Native and non-native address fields run the same rules independently. Exact or
NFC-equal selected values are reconciled into the non-native scalar slot with
both source fields and rule provenance; both protected evidence spans remain
selected, while the duplicate native scalar is null. MEDIUM plus MEDIUM does
**not** become HIGH: the canonical non-native candidate retains its original
confidence and no hidden elevation was approved. Different HIGH/MEDIUM selected house values emit
`NATIVE_NON_NATIVE_HOUSE_NUMBER_CONFLICT`; both house scalars remain null while
other non-conflicting components may remain selected. No transliteration or
inferred equivalence is introduced.

Residual content is evaluated only after all v3 rules. Parser v2 subtracts the
union of selected raw component spans and emits exact remaining material
Unicode-letter/mark/number spans; punctuation/whitespace alone is not residual.
This replaces v1's frozen field-level assignment only for v2. Reliably selected
street plus house is `PARSED` when no residual, ambiguity, conflict, or safety
skip remains; missing optional geography does not make it `UNPARSEABLE`.

## Safety and privacy invariants

The revision preserves NFC plus approved whitespace cleaning only, exact raw
Unicode-code-point spans, no NFKC/transliteration/case rewriting/spelling
correction, immutable Phase 2 values, 65,536-byte per-field and 262,144-byte
combined limits, 8 candidates per component, 64 per row, deterministic ordering,
closed vocabularies, no truncation, page checksums, and confidential sidecar
handling. Committed tests contain fictional values only.

## Aggregate comparison command

`development-compare-parsers` reads validated v1 and v2 core Parquet for the
same ordered DEVELOPMENT identities and fails on any row-count, identity-order,
source-provenance, schema, checksum, or parser-role mismatch. Its owner-only JSON
contains only row counts, all approved parse statuses (including zeros), selected
counts for all ten requested scalar components, exact conflict-vocabulary counts,
native/non-native/shared provenance counts, native-disagreement,
unassigned/unsafe/candidate-limit counts, fingerprints, file and semantic hashes,
and a protected identity-set digest. It contains no raw values,
provider/stable IDs, source paths, or candidate values and applies no automatic
scientific PASS threshold.

## Goethe-NHR rerun boundary

`cluster/goethe_nhr/phase03_development_parser_v2.sbatch` is a prepared,
not-executed single-node workflow. It requires the existing immutable 8,000-row
DEVELOPMENT payload and DEVELOPMENT identity set. It never accepts a LOCKED
identity or payload path and never invokes `pilot-profile`, `pilot-select`, or
`pilot-materialize-development`.

The job requests one node, one task, four CPUs, 16 GiB RAM, and two hours on
`general1`. It writes to a new immutable
`derived/controlled/phase03_v1/development_iterations/<iteration_id>/` namespace,
outside every preserved failed-pilot/recovery directory. It sequentially:

1. verifies the reviewed Git/runtime/input boundary;
2. transforms exactly 8,000 DEVELOPMENT rows with explicit parser v2;
3. validates page checksums and core/evidence semantic digests during atomic
   write/read-back;
4. creates the aggregate v1-v2 comparison;
5. deterministically creates a fresh protected v2 DEVELOPMENT review sample
   using the existing read-only sampling state;
6. writes a privacy-safe success marker and atomically promotes outputs.

The sampling-state path is deliberately required rather than guessed. If the
read-only state needed by the approved review sampler is unavailable, the job
stops; it does not silently reuse or invent a review sample.

After the reviewed commit object is synchronized, the operator creates a new
detached integration worktree at that exact commit. The production checkout
does not need to change branches or advance its HEAD. Code, `PYTHONPATH`, and
the submitted SBATCH file all come from the integration worktree; the existing
production repository remains only the controlled data/output and virtual-
environment root.

```bash
DATA_ROOT="/work/footprint/donyadidegan/safe_geocoding_pipeline"
PHASE03_GIT_COMMIT="<exact-reviewed-parser-v2-commit>"
PHASE03_INTEGRATION_ROOT="${DATA_ROOT}_parser_v2_integration_${PHASE03_GIT_COMMIT:0:12}"
PHASE03_SOURCE_RUN_ROOT="${DATA_ROOT}/derived/controlled/phase03_v1/pilots/.in_progress/phase03_pilot_goethe_20260813T224643Z_1748630_750a1655"

git -C "${DATA_ROOT}" cat-file -e "${PHASE03_GIT_COMMIT}^{commit}"
git -C "${DATA_ROOT}" worktree add --detach \
  "${PHASE03_INTEGRATION_ROOT}" "${PHASE03_GIT_COMMIT}"

PHASE03_DEVELOPMENT_PAYLOAD="${PHASE03_SOURCE_RUN_ROOT}/development/payload/development.parquet"
PHASE03_DEVELOPMENT_IDENTITIES="${PHASE03_SOURCE_RUN_ROOT}/selection/development.identities.bin"
PHASE03_BASELINE_CORE="${PHASE03_SOURCE_RUN_ROOT}/development/repair_validation_f9699cbc/core/development.parquet"
PHASE03_REVIEW_SAMPLING_STATE="${PHASE03_SOURCE_RUN_ROOT}/development/state_reconstruction_1748775_f9699cbc/candidate_state.sqlite3"

cd "${PHASE03_INTEGRATION_ROOT}"
export PHASE03_GIT_COMMIT PHASE03_INTEGRATION_ROOT PHASE03_SOURCE_RUN_ROOT
export PHASE03_DEVELOPMENT_PAYLOAD PHASE03_DEVELOPMENT_IDENTITIES
export PHASE03_BASELINE_CORE PHASE03_REVIEW_SAMPLING_STATE
sbatch --export=ALL \
  "${PHASE03_INTEGRATION_ROOT}/cluster/goethe_nhr/phase03_development_parser_v2.sbatch"
```

The job requires `PHASE03_GIT_COMMIT` to equal the detached integration
worktree HEAD, requires a clean worktree and matching submitted script, and
fails closed otherwise. All four input files must resolve beneath the preserved
source-run root, exist, be readable, and have no case-insensitive `locked`
substring in their resolved paths. The iteration and report roots are separately
resolved and rejected if either lies beneath the source-run root. Consequently
the job reads the four preserved inputs but never writes beneath
`PHASE03_SOURCE_RUN_ROOT`; all mutable and final v2 products go only to the
separate `development_iterations` and generated-report namespaces.

After the job produces a reviewed immutable iteration, its new
`<iteration>/review/` directory becomes the read-only parser-v2 review source.
Mutable human-review state must be initialized separately, for example under
`derived/controlled/phase03_v1/reviews/<iteration_id>/review_progress_v2/`, and
portable v2 exports under the sibling `review_export_v2/`. No v1 progress
database or either completed v1 label is migrated. The protected v2 context is
not copied into the mutable workspace. The intentional 28-column review schema
(the earlier 27-column draft plus approved `assignment_role`) must validate
before initialization. Human review and initialization remain separately
authorized compute-node work.

No Goethe job is authorized or submitted by this implementation step.

## Known intentional limitations and synthetic evidence

The parser intentionally leaves unresolved address systems that require
country-specific administrative knowledge, non-explicit locality inference,
hierarchical lot/block interpretation, transliteration, fuzzy spelling,
gazetteers, attached unit/floor conventions without an approved marker, and
unmarked one-word ASCII street text. Centre/Center/Block/Plaza remain MEDIUM and
role-arbitrated, not universal building labels. `12/05` is conservatively
calendar-like; some legitimate forms will therefore be missed.

The mandatory synthetic suite covers explicit/generic patterns, all seven
designator families in both number orders, Unicode scripts, punctuation,
same-/cross-line composition, false-positive role boundaries, exact evidence,
candidate limits, repeated determinism, and near-limit runtime. The synthetic
benchmark scenario `PARSER_RECALL_STRESS` reports rows/sec, evidence expansion,
RSS, and known-truth component precision/recall without applying a scientific
acceptance threshold. Real scientific acceptance remains protected DEVELOPMENT
manual review.

One 6,000-row fictional `PARSER_RECALL_STRESS` run on the approved Python
3.14.3/PyArrow 25.0.0 development environment produced the following
engineering measurements. These include Parquet write, digest, checksum, and
independent read-back time, not only transform time.

| Parser | Transform seconds | Total seconds | End-to-end rows/s | Evidence rows/input | Candidates/input | Peak RSS MiB |
|---|---:|---:|---:|---:|---:|---:|
| v1 | 0.829 | 3.024 | 1,984 | 2.33 | 4.50 | 194 |
| v2 | 1.775 | 4.882 | 1,229 | 4.00 | 7.00 | 247 |

V2 therefore costs about 1.61 times the end-to-end synthetic runtime and 1.71
times the evidence rows in this candidate-heavy corpus. It remained bounded and
far below the 8/64 candidate caps. For the six intentionally supported truth
patterns repeated in the corpus, v2 recorded precision and recall 1.0 for each
applicable street, house, unit, floor, building, and organization component;
v1 recorded the expected misses. This corpus is deliberately favorable to the
implemented rules and is not an estimate of real-data quality.
