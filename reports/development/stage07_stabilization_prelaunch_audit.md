# Stage 7 stabilization and prelaunch audit

Status: **IN PROGRESS**. The scientific verdict remains
`STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY`. This audit does not accept Stage 7,
alter the immutable authoritative libpostal registry, change Stage 6, start
Stage 8, access HOLDOUT, start production, geocode, or authorize independent
review.

## Purpose and guarantee

Stage 7 preserves the exact accepted Stage 6 candidate and attaches faithful,
ordered raw parser output only where the exact pinned parser/model is
scientifically applicable. It guarantees identity, lossless raw-output
serialization, deterministic technical execution, explicit applicability, and
fail-closed publication. A nonempty technical result is not a claim of semantic
correctness.

The authoritative v1 libpostal registry remains immutable. Country-aware
applicability is a later design principle under evaluation; this audit does not
retrofit statuses into that registry.

## Frozen country evidence

The trusted field is `stage04_lower_country_iso_code` from accepted occurrence
provenance. SAFE does not infer country from candidate text, parser output,
script, geocoding, or an external service. Candidate provenance is classified
as:

- `COUNTRY_UNANIMOUS_VALID`;
- `COUNTRY_MISSING`;
- `COUNTRY_PARTIAL`;
- `COUNTRY_INVALID`; or
- `COUNTRY_CONFLICTING`.

Majority, first-occurrence, and representation-priority selection are
prohibited. Missing, partial, invalid, and conflicting provenance makes a
country-dependent parse-once call ineligible or ambiguous. A future
candidate-plus-country key is a separate scientific change; Stage 6 is not
changed here.

The public evidence and exact ISO mapping are frozen in
[`stage07_parser_country_eligibility_v1.json`](../../docs/scientific_assets/stage07_parser_country_eligibility_v1.json).
Its SHA-256 is
`49dcda13e36d2692885efadffb606fa96207fc174a3385041c07af9bf0d1026a`.

### libpostal

The exact pinned bundle remains
`f3c6db7e9f11ab75b2207be773e946d531dbba763008d9f7e5036d8c923dc2ae`,
using libpostal source commit
`25099c506612b34b23b1bfe286ca6321fcf06f35`, default parser model v1.0.0,
and training-set pointer `20170304`. The exact pinned README documents parser
training over more than one billion examples from every inhabited country.
The bundle does not contain an enumerable model-country manifest. SAFE therefore
binds the documented worldwide inhabited-country scope and does not invent a
small quality-derived whitelist. A bad parse is not reclassified as an
unsupported country.

Under this definition, unanimous valid ISO provenance is within libpostal's
documented scope. Non-unanimous or unusable provenance is unresolved for the
new eligibility-aware policy.

### DeepParse

The selected diagnostic model is DeepParse 0.10.0, source commit
`5b17c0bccd6773044f8a61da68a7b8c91c4fd1e8`, official BPEmb-attention model
revision `4af74dad1d547804dfc2de8f40fb23fbbec5b811`. Conservative eligibility is
limited to the 20 countries documented as training countries:

`at, au, br, ca, ch, cz, de, dk, es, fi, fr, gb, it, kr, mx, nl, no, pl, ru, us`.

The separately documented 41 zero-shot evaluation countries are not eligible.
An otherwise valid country outside this trained set is
`PARSER_NOT_APPLICABLE_COUNTRY`, not a parser failure. DeepParse remains a
diagnostic-only trained-country alternative; it is not an approved global
replacement or fallback.

## Denominators

Coverage, technical success, and semantic quality are separate:

1. coverage = eligible unique candidates / 51,779 unique candidates;
2. technical success = technical outcomes among eligible attempted calls;
3. semantic quality = immutable qualitative classifications among reviewed
   eligible candidates.

The predeclared usable category is
`PLAUSIBLE_PARSE + PARTIAL_BUT_USABLE_PARSE`. `PARSED_NONEMPTY` is not semantic
correctness. Counts will be reported at source-row, occurrence, unique-candidate
(primary parser-call), and immutable 120-case review levels. The pairwise view
will additionally use only candidates eligible for both parsers.

Exact protected metadata-only counts: **PENDING ONE CONTROLLED ELIGIBILITY
AUDIT**. No parser call is needed to compute them.

## Failure-history ledger

The machine-readable chronological ledger is
[`stage07_failure_ledger.json`](stage07_failure_ledger.json). Before the one-time
inspection of current job 1762078, known root categories are:

| Root category | Count | Controlling lesson |
|---|---:|---|
| `ORCHESTRATION_PATH_FAILURE` | 2 | Validate controlled worktree/output topology before submission. |
| `SHELL_OR_QUOTING_FAILURE` | 1 | Syntax and exact command framing are submission gates. |
| `MULTIPROCESS_LAUNCHER_FAILURE` | 1 | Exercise the real spawn entry point before protected work. |
| `RESOURCE_CEILING_FAILURE` | 1 | Do not impose the invalid 48 GiB process ceiling. |
| `BUNDLE_CONTAMINATION_FAILURE` | 1 | Reject cache/bytecode contamination and bind the runtime exactly. |
| `MISSING_RUNTIME_DEPENDENCY` | 4 | Validate the selected model's complete import closure. |
| `STATIC_LINK_DEPENDENCY_FAILURE` | 1 | Audit native transitive linkage, not only direct libraries. |
| `PARSER_SCIENTIFIC_FAILURE` | 2 | Machine success does not override parser-quality evidence. |
| `OTHER` | 2 | Preserve and diagnose every attempt rather than erase it. |

The original 48 GiB diagnostic, its four giant crashes, the later 180 GiB
23/23 giant success, authoritative job 1760221, validation job 1760226,
fixed-500/review job 1760494, quality job 1760818, and context job 1761212 all
remain immutable. Current public-only DeepParse bundle job 1762078 remains
untouched until the audit's single planned inspection.

## Methodology audit

Rules discovered reactively and now frozen before more protected execution:

- applicability must be decided from trusted country provenance before a
  country-scoped parser call;
- support/training coverage and parse quality are distinct;
- DeepParse zero-shot evaluation is not trained-country eligibility;
- unsupported country, missing country, and conflicting country are not parser
  failures;
- exact candidate text and parser-native raw output remain available even when
  Stage 7 abstains;
- parser-specific coverage denominators must not be conflated;
- pairwise quality comparison requires overlapping eligibility;
- the parse-once key remains the Stage 6 candidate ID only for context-free
  libpostal; country-dependent execution must abstain on unresolved provenance
  unless a separately approved key redesign occurs;
- technical empty output, technical failure, semantic misparse,
  non-applicability, and upstream corruption are separate concepts;
- no parser output may be selected because it merely “looks better” without a
  separately validated deterministic arbitration rule;
- giant/corrupt inputs are not skipped by size and must not be truncated;
- Stage 8 fixed mapping cannot be assumed to repair true Stage 7 boundaries.

The current blocker remains scientific parser quality. Country eligibility
prevents invalid quality denominators; it does not erase libpostal's documented
in-scope clear misparses.

## Implementation audit

### Resolved in the stabilization code

- versioned parser-specific country-support manifest and exact ISO mapping;
- deterministic missing/partial/invalid/conflicting provenance semantics;
- metadata-only candidate, occurrence, source-row, overlap, and 120-selection
  denominator audit;
- clean detached worktree and exact-SHA pre-submission checks;
- controlled-root, new-output, owner/mode, disk, inode, resource-directive,
  HOLDOUT-path, and address-space-cap checks;
- explicit public-build versus offline-execution network policy;
- fail-closed requirement for successful compute-smoke evidence before a bundle
  gate may report pass;
- standard-library native-extension and selected-model import-closure checks;
- full ELF `readelf`/`ldd` audit with unresolved-library rejection and hashed
  resolved-library evidence;
- offline exact-model initialization and deterministic public synthetic parses;
- explicit multiprocessing-spawn smoke;
- exact distribution inventory and stable scientific bundle fingerprint that
  excludes path/build-time Python bytecode caches;
- future build publication rejects `__pycache__`, `.pyc`, and `.pyo` artifacts.

### Remaining until executed evidence exists

- outcome and immutable bundle identity from job 1762078;
- validation of that bundle against its manifest and complete runtime closure;
- exact compute-image native linkage evidence;
- offline public multilingual model-initialization smoke on a Goethe compute
  node;
- protected metadata-only country denominator counts;
- complete transitive license/notice audit for the resulting installed
  distribution set;
- a final all-checks prelaunch record at one exact pushed SHA.

No protected DeepParse inference is justified until every applicable remaining
item passes.

## Prelaunch checklist

| Gate | Current state |
|---|---|
| Methodology consistency | PASS |
| Country eligibility definition frozen | PASS |
| Exact clean pushed/detached execution SHA | PENDING FINAL SHA |
| Controlled worktree/path policy | IMPLEMENTED; GOETHE EVIDENCE PENDING |
| Local-safe tests/static/syntax | PENDING FINAL GATES |
| Dependency/import closure | IMPLEMENTED; BUNDLE EVIDENCE PENDING |
| Binary linkage | IMPLEMENTED; COMPUTE EVIDENCE PENDING |
| Python runtime completeness | IMPLEMENTED; BUNDLE EVIDENCE PENDING |
| Bundle/model hashes | PENDING JOB 1762078 |
| Offline synthetic initialization | PENDING COMPUTE SMOKE |
| Public multilingual smoke | PENDING COMPUTE SMOKE |
| Permissions | IMPLEMENTED; ARTIFACT EVIDENCE PENDING |
| Disk/inode/resource preflight | IMPLEMENTED; GOETHE EVIDENCE PENDING |
| No protected data in public tests | PASS BY DESIGN/STATIC REVIEW |
| No HOLDOUT / production | PASS |
| No network during protected execution | IMPLEMENTED; RUNTIME EVIDENCE PENDING |

## Small compute-node smoke design

One public-only job requests 4 CPUs, 16 GiB, and 30 minutes. It validates the
exact frozen bundle, imports the complete selected-model runtime closure,
initializes the exact BPEmb-attention model with network denied, parses Latin,
Cyrillic, and Hangul public synthetic inputs belonging only to documented
training countries twice, checks exact structured determinism, exercises
`multiprocessing` spawn, audits every material dynamic ELF dependency, writes
and reopens owner-only JSON evidence, and exits. It reads no protected input.

The smoke will not be submitted while job 1762078 is pending/running. A larger
or protected DeepParse diagnostic remains prohibited until this smoke passes.

## Final design questions

1. **Stage 7 guarantee:** exact candidate identity, parser applicability,
   deterministic faithful raw output or explicit abstention, complete lineage,
   and separated technical/semantic evidence.
2. **libpostal countries:** documented worldwide inhabited-country training;
   no smaller pinned model manifest exists, so no quality-derived exclusions.
3. **DeepParse countries:** the exact 20-country trained set above; zero-shot
   countries excluded.
4. **Missing/conflicting country:** abstain with a specific unresolved
   eligibility status; never guess.
5. **Primary parse key:** current Stage 6 exact candidate ID for context-free
   libpostal; country-dependent parsing cannot use it on ambiguous context
   without a separately approved key change.
6. **Pre-parse eligibility:** yes, using only accepted occurrence provenance.
7. **Required new design statuses:** parser-specific not-applicable plus
   missing, partial, invalid, and ambiguous-country abstention; exact final
   registry vocabulary requires a later owner-approved Stage 7 redesign.
8. **Coverage versus quality:** parser-specific coverage over all candidates;
   technical results over eligible attempts; semantic outcomes over reviewed
   eligible cases.
9. **Primary parser:** libpostal remains the immutable v1 primary baseline but
   is not scientifically ready.
10. **DeepParse role:** trained-country diagnostic alternative only until
    eligibility-matched evidence supports another role.
11. **Abstention:** required for parser non-applicability, unresolved country,
    unsupported technical behavior, or a future validated risk policy; never
    fabricate components.
12. **Evidence before readiness:** exact bundle/runtime provenance, prelaunch
    and compute smoke pass, complete eligibility denominators, technical and
    semantic results on eligible populations, overlapping pairwise evidence,
    validation against overfitting, and a new explicit owner design decision.

## Current engineering decision

**PENDING** until job 1762078 is inspected once and the remaining executable
gates above are resolved. Scientific status remains
`STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY`.
