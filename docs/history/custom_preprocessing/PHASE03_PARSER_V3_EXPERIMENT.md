# Phase 3 parser-v3 narrow DEVELOPMENT experiment

## Status and evidence boundary

`conservative_address_parser_v3_experimental` is an unapproved DEVELOPMENT
experiment. It does not replace `conservative_address_parser_v2`, authorize
LOCKED_EVALUATION access, or establish a production parser. Promotion requires
review of an exact 8,000-row v2-v3 comparison and a separately authorized
protected human review. Engine construction fails closed if v3 is requested
with `LOCKED_EVALUATION` or `AUTHORITATIVE` execution scope.

The historical v2/v3 comparison later exposed a shared, unrelated
`country_parse_method` reproducibility defect. The explicit repaired rerun uses
`conservative_address_parser_v2_1` and
`conservative_address_parser_v3_1_experimental` with the same unchanged v3/v4
registries. This does not revise the V4 hypothesis. See
`docs/PHASE03_COUNTRY_METHOD_REPAIR.md`.

The experiment responds only to the sanitized targeted profile produced by
SLURM job `1749332`, profile
`phase03_development_targeted_opportunity_profile_20260815T165055Z_1749332_9f9ff679`.
Among eight predeclared families, only `WORDS HOUSELIKE_NUM WORDS` was surfaced
as a possible rule-design hypothesis: 214 DEVELOPMENT rows and 415 unresolved
segments, including 57 rows classified as possible rule hypotheses. Frequency
is not treated as correctness evidence.

## Exact hypothesis

The generic morphology is not sufficient. The v3 experiment accepts one
same-line, punctuation-free segment only when all of these conditions hold:

1. Tokenization yields only word tokens and exactly one 1–4 digit decimal
   integer strictly inside the segment. Years 1900–2099 are excluded.
2. Exactly one side of that integer contains an exact designator from the
   frozen `street_designators_v2` resource. The other side contains exactly one
   alphabetic word.
3. The opposite word is not a closed role marker for units, floors, buildings,
   organizations, post boxes, dates, identifiers, lots, blocks, parcels, or
   references.
4. The complete row has at least two distinct, unambiguous direct structured
   geography components among postcode, locality, region, and country.
5. No existing v2 candidate for street, house number, unit, floor, building,
   organization, or PO box competes anywhere in the row.
6. The proposed house number is not exactly the structured postcode. There is
   only one proposed street/house pair per representation.
7. If the corresponding native/non-native line contains material content, it
   must independently produce the exact same street/house pair. A missing,
   structurally different, or value-different counterpart disables the
   experiment.

Only the contiguous designator-bearing side becomes `street_clean`; the center
integer becomes `house_number_clean`. The opposite word is neither concatenated
into the street nor assigned to another component. It remains residual, so a
successful experimental extraction is normally `PARTIAL` with
`UNASSIGNED_CONTENT_PRESENT`, not `PARSED`.

This is one atomic scientific hypothesis represented by two registry entries
because the established registry contract emits exactly one component per
rule:

- `HOUSE_NUMBER_EMBEDDED_DESIGNATOR_EXPERIMENT_V4`, priority 124, MEDIUM;
- `STREET_EMBEDDED_DESIGNATOR_EXPERIMENT_V4`, priority 125, MEDIUM.

Both must pass the same row-level gate. Their priorities follow all v2
street/house rules and precede the unchanged LOW-confidence
`HOUSE_NUMBER_EDGE_CANDIDATE_V1` shadow rule. The gate rejects the pair whenever
existing address-role evidence is present; it does not override v2 arbitration.

## Version and integrity identities

- parser: `conservative_address_parser_v3_experimental`;
- registry: `phase03_rule_registry_v4_experimental`;
- registry schema: `phase03_rule_registry_schema_v4_experimental`;
- registry SHA-256: `2137c4a78cd062aa6f07784deea6046824e99ed7712a591d841e142d2f49dfc5`;
- base configuration SHA-256: `78b4782c29ee1676cd04c5ebc015bcab731111b280036bf3bee70121332f0871`;
- production-reference effective configuration SHA-256:
  `4ad2febb4c1d3a333a76a4a4ad02232958245f99715032d497ab1ee1c3266ee3`.

Parser v2 remains bound to `phase03_rule_registry_v3` and its existing hashes.
The component, evidence, diagnostic, cleaning, placeholder, reference, safety,
and candidate-limit schemas/contracts do not change. V3 core/evidence semantic
digests are expected to differ only where the experimental candidates, selected
components, residual accounting, status, or corresponding evidence differ.

## False-positive boundaries

Synthetic tests reject structured-postcode equality; insufficient geography;
years; dates; floor, unit, building, organization, lot, block, parcel, and
reference roles; multiple numeric tokens; designators on both sides; existing
street/house candidates; independent unit/floor/building/organization evidence;
native/non-native disagreement; commas, semicolons, parentheses, and other
punctuation; and structures distributed across different lines. The existing
65,536-byte per-field and 262,144-byte combined safety limits remain unchanged.

The experiment deliberately does not cover the seven other profile families,
compose discontinuous street text, infer semantics from line number, accept a
bare center number without an approved designator, transliterate, fuzzily match,
or consult a gazetteer/geocoder.

## Sanitized v2-v3 comparison contract

`development-compare-parser-v2-v3` reads completed v2/v3 core and evidence
Parquets, verifies page checksums and exact schemas, validates each core/evidence
relationship, requires identical ordered DEVELOPMENT identities and source
provenance, and reproduces core/evidence semantic digests. Its JSON output
contains aggregates only:

- parse-status and selected-component counts for each parser;
- conflict counts by registered type;
- changed rows and status transitions;
- newly parsed and newly partial rows;
- new conflicts;
- new, lost, and changed selections by component;
- evidence rows and rule-specific candidate/selection/evidence-kind counts;
- artifact hashes, semantic digests, configuration hashes, and one ordered
  identity digest.

The report contains no addresses, candidates, provider IDs, stable identities,
source paths, or per-row results. It deliberately records
`EXPERIMENTAL_COMPARISON_COMPLETE_NO_PROMOTION_DECISION` and applies no
scientific PASS threshold.

## Completed Goethe-NHR comparison and targeted-review boundary

The approved comparison ran as SLURM job `1749335` at commit
`fa3b924657aed47bfe6aaa80d87353f8d9b78139`, producing immutable iteration
`phase03_development_parser_v3_experimental_20260815T174529Z_1749335_fa3b9246`.
It found 26 rows with scientific-output changes, nine new paired street/house
selections, and 22 candidate groups for each experimental rule (nine selected,
thirteen unselected), with no lost or changed v2 selections and no new
conflicts. Status remains
`EXPERIMENTAL_COMPARISON_COMPLETE_NO_PROMOTION_DECISION`.

The separately versioned protected targeted-review workflow is documented in
`docs/PHASE03_PARSER_V3_TARGETED_REVIEW.md`. It reviews the deduplicated union of
changed rows and rows with experimental-rule evidence, and does not alter this
parser or authorize promotion.

## Historical Goethe-NHR evaluation procedure

The job reads the fixed 8,000-row DEVELOPMENT payload and identities plus the
immutable successful parser-v2 core/evidence artifacts. It does not run
`pilot-profile`, `pilot-select`, or `pilot-materialize-development`, and exposes
no LOCKED input. Four CPUs, 16 GiB RAM, and a two-hour walltime are conservative
for an 8,000-row transform plus two small Parquet read-backs; no full Phase 2
scan occurs.

After the reviewed commit has been pushed, create a new detached integration
worktree at that exact commit. Do not advance or repurpose the production data
checkout:

```bash
ssh goethe

DATA_ROOT="/work/footprint/donyadidegan/safe_geocoding_pipeline"
PHASE03_GIT_COMMIT="<exact-reviewed-parser-v3-commit>"
PHASE03_INTEGRATION_ROOT="${DATA_ROOT}_parser_v3_experimental_${PHASE03_GIT_COMMIT:0:12}"
PHASE03_SOURCE_RUN_ROOT="${DATA_ROOT}/derived/controlled/phase03_v1/pilots/.in_progress/phase03_pilot_goethe_20260813T224643Z_1748630_750a1655"
PARSER_V2_ITERATION="${DATA_ROOT}/derived/controlled/phase03_v1/development_iterations/phase03_development_parser_v2_20260814T134743Z_1748928_06acc59e"

git -C "${DATA_ROOT}" fetch --prune origin
git -C "${DATA_ROOT}" cat-file -e "${PHASE03_GIT_COMMIT}^{commit}"
git -C "${DATA_ROOT}" worktree add --detach \
  "${PHASE03_INTEGRATION_ROOT}" "${PHASE03_GIT_COMMIT}"
test "$(git -C "${PHASE03_INTEGRATION_ROOT}" rev-parse HEAD)" = "${PHASE03_GIT_COMMIT}"
test -z "$(git -C "${PHASE03_INTEGRATION_ROOT}" status --short)"

PHASE03_DEVELOPMENT_PAYLOAD="${PHASE03_SOURCE_RUN_ROOT}/development/payload/development.parquet"
PHASE03_DEVELOPMENT_IDENTITIES="${PHASE03_SOURCE_RUN_ROOT}/selection/development.identities.bin"
PHASE03_PARSER_V2_CORE="${PARSER_V2_ITERATION}/transformed/core/development.parquet"
PHASE03_PARSER_V2_EVIDENCE="${PARSER_V2_ITERATION}/transformed/evidence/development.parquet"

cd "${PHASE03_INTEGRATION_ROOT}"
export PHASE03_GIT_COMMIT PHASE03_INTEGRATION_ROOT PHASE03_SOURCE_RUN_ROOT
export PHASE03_DEVELOPMENT_PAYLOAD PHASE03_DEVELOPMENT_IDENTITIES
export PHASE03_PARSER_V2_CORE PHASE03_PARSER_V2_EVIDENCE
sbatch --export=ALL \
  "${PHASE03_INTEGRATION_ROOT}/cluster/goethe_nhr/phase03_development_parser_v3_experimental.sbatch"
```

Preflight requires the exact clean detached commit, matching submitted SBATCH,
Python 3.14.3/Unicode 16.0.0, pinned references and fingerprints, and four
readable controlled DEVELOPMENT inputs whose resolved paths contain no
case-insensitive `locked`. All mutable output goes to a new
`development_iterations/.in_progress/<iteration>` and generated-report attempt,
then is promoted under a new immutable iteration ID. The job never writes below
the preserved source pilot root or overwrites parser-v2 artifacts.

No job is authorized or submitted by this implementation step. A protected
targeted review sample for changed/experimental rows requires separate review
and authorization after the aggregate comparison is inspected.
