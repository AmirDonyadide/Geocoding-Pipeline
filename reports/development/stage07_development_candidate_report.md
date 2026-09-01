# Stage 7 DEVELOPMENT candidate report

Verdict: `STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY` because the completed
risk-stratified qualitative review found a material systematic Stage 7 parser
problem.

Contract: `stage07_libpostal_parsing_contract_v1`; profile:
`stage07_libpostal_parsing_profile_v1`. Exact input is
`stage06_candidate_lower`; context and hints are none; Stage 6 science is
unchanged. Published statuses are only `PARSED_NONEMPTY` and `PARSED_EMPTY`.
The ordered nested field is a non-null LargeList of non-null structs with
LargeString `label` and `value`; ordering and duplicates are preserved. Any
child crash is retried once exactly and aborts publication if unresolved.

Implementation SHA: `4a5f7495cf55121198981eae92ac3db8c73ad1fa`.
Pre-qualitative evidence SHA: `6d105c35c41181f96ec881d6501f9b53b5ceb11c`.
Base main: `76435eb7ca5cd9a47a2a77fb36278568ba3bfc29`.

Authoritative job `1760221` completed in 00:09:56 with 180 GiB, one
synchronous child, no internal address-space cap, and no candidate timeout.
It produced exactly 51,779 rows in 13 shards: 51,774 `PARSED_NONEMPTY` and 5
`PARSED_EMPTY`; 0 crashes, 0 retries, 0 unhandled failures, and 6,106,088
components. Maximum component count was 881,338; maximum nested Arrow row size
was 48,760,156 bytes; output bytes were 92,546,225.

Independent validation job `1760226` passed all 51,779 rows, exact Stage 6
preservation, fingerprints, and complete 69,747-occurrence map-back (34,822
STANDARD; 34,925 NATIVE).

Review job `1760494` passed fixed-500 verification: 500 source rows, 937
occurrences, 613 unique candidates, 324 duplicate occurrences, 0 mismatches,
and 0 cross-wires. It selected 120 candidates with fingerprint
`1507900b27e4503eb33836c8465217092e9ffb8de2f1b6ef05026690be11a844`.

The existing selection was reviewed in a separate, owner-authorized
LLM-assisted Codex helper session. The owner explicitly authorized the OpenAI
model to inspect exactly these 120 selected protected candidates and their raw
Stage 7 outputs. The authorization did not include HOLDOUT, production, or the
complete candidate population; no web search or third-party API was used.
Protected classifications and abstract comments remain owner-only and
untracked. Only these aggregate results enter Git:

- `PLAUSIBLE_PARSE`: 30;
- `PARTIAL_BUT_USABLE_PARSE`: 41;
- `QUESTIONABLE_PARSE`: 7;
- `CLEAR_MISPARSE`: 11; and
- `UPSTREAM_SOURCE_CORRUPTION_OR_UNASSESSABLE`: 31.

All 120 decisions and comments validated against the exact selection
fingerprint, with zero missing, duplicate, unknown, invalid, or classification-
mismatched records. All five `PARSED_EMPTY` cases were classified upstream
source corruption or unassessable; none was classified as a material parser
failure. The 13 giant/multi-record cases identified in the abstract review
evidence were likewise classified upstream corruption or unassessable rather
than intrinsic parser failure.

The exact existing HTML-export contract is recorded as
`stage07_qualitative_classifications_export_v1` (top-level selection fingerprint
plus 120 `review_order`/`classification` records). The owner-only classification
artifact SHA-256 is
`0df881a1f62db505175aa916ca259e090341f0ffde14893679a3571042a4760f`; the
abstract-comment sidecar SHA-256 is
`4c073e03d33182d5c7f73690424a90886dee70cf8cdf9a4d3deec817287f7796`.

The 11 clear misparses include aggregate patterns of severe component
mislabeling and material boundary/within-word splitting. Clear failures occur
across multiple non-Latin/script risk strata rather than a single isolated
candidate class. Seven additional parses remain questionable. These are raw
libpostal parsing defects that cannot be assumed repairable by Stage 8 label
mapping. The controlling finding is
`MATERIAL_SYSTEMATIC_STAGE07_PROBLEM`; machine-integrity success therefore does
not make the frozen parsing strategy ready for independent review.

The first diagnostic’s 48 GiB ceiling and 4/23 crashes remain immutable
history; job `1760182` showed 23/23 success under 180 GiB. HOLDOUT, production
Stages 2–7, Stage 8, and geocoding were not used.

## Targeted parser-quality root cause

Job `1760818` deterministically reparsed only the 11 clear and seven
questionable selected cases using the unchanged frozen bundle. All 18 ordered
results reproduced exactly, with zero crashes or restarts. Fourteen distinct
cases have true libpostal errors: six label errors and nine boundary errors,
with one case in both categories. Three cases show upstream
transliteration/romanization damage.

All 11 clear cases are native, single-script candidates distributed across
Han, Hangul, Lao, Thai, and Hebrew. The exact Stage 6 candidate remains in
every Stage 7 row, and component values preserve all lexical/numeric input in
all 11. Nevertheless, five are material label errors and six are within-word
or token boundary failures; fixed Stage 8 label mapping could safely recover
none without guessing. The controlling diagnosis is
`MIXED_ROOT_CAUSES_REQUIRING_TARGETED_STAGE07_DESIGN_CHANGE`.

See the sanitized [root-cause report](stage07_quality_root_cause_summary.md).
No redesign was implemented and a new owner scientific decision is required.

## Prospective v2 readiness/abstention

DeepParse is closed under `DEEPPARSE_INFRASTRUCTURE_PATH_NOT_JUSTIFIED` and no
protected DeepParse inference occurred. Stage 7 v1 remains immutable.

Optimized bounded audit job `1763358` at
`372aad37370144d6ca85d05c56302a0af2cad4b3` evaluated prospective
`stage07_component_readiness_rule_v1` using only the existing authorized 120
semantic cases and fixed-500 metadata outside them. It completed in 84 seconds
without scanning/decoding the authoritative nested registry, making a parser
call, or accessing HOLDOUT/production.

The rule predicted 69 ready, 45 abstain, and six not assessed. It abstained on
10/11 clear misparses, including all 6/6 known boundary failures; one of five
label-only clear failures remained structurally ready. This supports a useful
parser-local warning/abstention layer but not a claim of semantic correctness.

The fixed-500 candidate projection contains 613 IDs, with nine overlapping the
existing 120 and none overlapping the targeted 18; 604 were untouched by
semantic review. Machine-only job `1763433` applied the unchanged frozen rule
to those 604 and froze a 240-case balanced selection (120 ready/120 abstain),
fingerprinted as
`c05cecf2aa9099045adc0d5c698c7e82a6bae187ae82222817f4bfb5264c2a89`.
Semantic review remains unauthorized. The full status model, reason codes,
schema, metrics, thresholds, and authorization boundary are in the
[v2 readiness design](stage07_v2_readiness_design.md), with execution evidence
in the [selection-freeze report](stage07_v2_validation_selection_freeze.md).

The post-Stage-7 philosophy is now parser-as-evidence: preserve source truth,
generate multiple hypotheses, retrieve top-N self-hosted Pelias candidates,
score them against independent evidence, and accept an explicit granularity or
remain unresolved. Compact replacement Stages 8–14 are proposed in the
[architecture redesign](post_stage07_geocoding_architecture_redesign.md), but
none is started or authorized.

Current statuses remain:

- `STAGE07_V2_READINESS_DESIGN_READY_FOR_FRESH_DEVELOPMENT_VALIDATION`; and
- `STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY`.
