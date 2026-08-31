# Stage 7 stabilization and prelaunch audit

Engineering status: **`STAGE07_PRELAUNCH_GATE_FAIL`**. The scientific verdict remains
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
correctness. Counts are reported at source-row, occurrence, unique-candidate
(primary parser-call), and immutable 120-case review levels. The pairwise view
uses only candidates eligible for both parsers.

Metadata-only job `1762293`, run once at
`aa15b1c4c078be8f2db50c9940347975f9e282a7`, completed in 11 seconds with no
candidate-text or component read, parser call, or network call. Independent
reopen validation rehashed all three artifacts, reconciled 51,779 candidate
rows, 69,747 occurrences, and 120 immutable selection rows, and confirmed
`0700`/`0600` modes. Its manifest SHA-256 is
`8395b0b5f8e0943dc6dd1a9c9553ea571294fc7bbe61fc9b9b1e6e8fd1cea1a6`; the
aggregate SHA-256 is
`a619974ba50da78a174b9344a1248a91340f5a83864296a5add6dae1e4bfb947`.

### Country provenance over unique candidates

| Provenance result | Candidates |
|---|---:|
| Unanimous valid | 50,685 |
| Missing | 721 |
| Partial | 4 |
| Invalid | 355 |
| Conflicting | 14 |
| **Total** | **51,779** |

The 1,094 non-unanimous/invalid candidate IDs are unresolved for a
country-dependent parse-once call. No majority, first value, or representation
priority was used.

### Parser-specific coverage

| Population | libpostal eligible | DeepParse trained-country eligible | DeepParse not applicable | Country unresolved |
|---|---:|---:|---:|---:|
| Unique candidates | 50,685 | 10,265 | 40,420 | 1,094 |
| Occurrences | 68,019 | 16,358 | 51,661 | 1,728 |

Candidate coverage is 97.887% for the documented libpostal scope and 19.825%
for the conservative DeepParse trained-country scope. The overlap contains
10,265 candidates and 16,358 occurrences. Because DeepParse's eligible set is
a subset of the broad libpostal scope, the remaining resolved population is
40,420 libpostal-only candidates; there are no DeepParse-only candidates.

At source-row level, 34,124 of 35,000 rows have at least one libpostal-eligible
representation and 876 have only unresolved country context. For DeepParse,
8,203 rows have at least one trained-country-eligible representation, 25,918
have no eligible representation, and 879 have only unresolved context.

Among libpostal-eligible candidates, the immutable authoritative output has
50,681 `PARSED_NONEMPTY`, four `PARSED_EMPTY`, and zero technical failures.
These are technical outcomes, not semantic accuracy. The immutable review has
114 libpostal-eligible candidates: 29 plausible, 41 partial-but-usable, seven
questionable, 11 clear misparses, and 26 upstream-corrupt/unassessable. The
predeclared usable count is therefore 70/114 (61.404%).

The immutable review contains only 20 DeepParse-trained-country-eligible
candidates: eight originally plausible libpostal parses, eight originally
partial-but-usable, three original clear misparses, and one upstream-corrupt/
unassessable case. None of the seven original questionable cases is eligible.
These are baseline libpostal categories, not DeepParse semantic-quality
results; DeepParse has not run.

## Failure-history ledger

The machine-readable chronological ledger is
[`stage07_failure_ledger.json`](stage07_failure_ledger.json). After the two
existing jobs resolved, known root categories are:

| Root category | Count | Controlling lesson |
|---|---:|---|
| `ORCHESTRATION_PATH_FAILURE` | 2 | Validate controlled worktree/output topology before submission. |
| `SHELL_OR_QUOTING_FAILURE` | 1 | Syntax and exact command framing are submission gates. |
| `MULTIPROCESS_LAUNCHER_FAILURE` | 1 | Exercise the real spawn entry point before protected work. |
| `RESOURCE_CEILING_FAILURE` | 1 | Do not impose the invalid 48 GiB process ceiling. |
| `BUNDLE_CONTAMINATION_FAILURE` | 1 | Reject cache/bytecode contamination and bind the runtime exactly. |
| `MISSING_RUNTIME_DEPENDENCY` | 5 | Validate stdlib/import closure and exact offline model-cache resolution. |
| `STATIC_LINK_DEPENDENCY_FAILURE` | 1 | Audit native transitive linkage, not only direct libraries. |
| `PARSER_SCIENTIFIC_FAILURE` | 2 | Machine success does not override parser-quality evidence. |
| `OTHER` | 2 | Preserve and diagnose every attempt rather than erase it. |

The original 48 GiB diagnostic, its four giant crashes, the later 180 GiB
23/23 giant success, authoritative job 1760221, validation job 1760226,
fixed-500/review job 1760494, quality job 1760818, and context job 1761212 all
remain immutable. Public-only DeepParse bundle job `1762078` also remains
immutable. It started at `2026-08-31T18:13:55` and failed pre-scientifically
after 8 minutes 35 seconds with exit `1:0`; protected processing never began.
Its batch maximum RSS was 723,276 KiB and maximum virtual size was 3,298,508
KiB, excluding resource exhaustion as the observed cause.

The private CPython runtime—including `_sqlite3`—built, dependencies installed,
and every pinned model/tokenizer/embedding download passed its SHA-256 check.
The failure occurred when offline DeepParse initialization asked Hugging Face
to resolve `main`: the staged `refs/main` file contained the correct 40-hex
revision plus a newline (41 bytes). Exact-revision cache lookup succeeds, while
`main` lookup fails. This is a pre-scientific offline-cache binding defect, not
a parser-quality, model-asset, or resource failure.

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

### Prepared correction from job 1762078

The minimum correction writes the exact revision as 40 bytes without a
terminating newline, checks both byte length and value, and requires
`huggingface_hub.try_to_load_from_cache(..., revision="main")` to resolve both
the config and weights before model initialization. Focused synthetic tests and
shell syntax pass locally, and a public metadata-only resolver check against a
temporary cache view resolved both preserved checkpoint files with the exact
40-byte reference. The correction has not been validated by SLURM, and no
replacement job has been submitted.

### Remaining until executed evidence exists

- a successful corrected public build and immutable bundle identity;
- validation of that bundle against its manifest and complete runtime closure;
- exact compute-image native linkage evidence;
- offline public multilingual model-initialization smoke on a Goethe compute
  node;
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
| Exact clean pushed/detached execution SHA | PASS for eligibility job `1762293` at `aa15b1c4c078be8f2db50c9940347975f9e282a7` |
| Controlled worktree/path policy | PASS for completed eligibility audit |
| Local-safe tests/static/syntax | PASS |
| Eligibility denominators | PASS — job `1762293`, independently reopened |
| Dependency/import closure | IMPLEMENTED; no published bundle evidence |
| Binary linkage | IMPLEMENTED; compute evidence unavailable |
| Python runtime completeness | Built in failed job; no published bundle |
| Bundle/model hashes | Source assets passed; no published bundle |
| Offline cache binding | CORRECTION PREPARED; not SLURM-validated |
| Offline synthetic initialization | FAILED before initialization in job `1762078` |
| Public multilingual smoke | NOT RUN; no valid bundle |
| Permissions | PASS for eligibility artifact; bundle not published |
| Disk/inode/resource preflight | PASS for completed eligibility audit |
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

The smoke cannot be submitted because job 1762078 did not publish a valid
bundle. A larger or protected DeepParse diagnostic remains prohibited until a
corrected bundle exists and this smoke passes.

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

## Current job handling

- Public bundle job `1762078`: failed pre-scientifically after 8 minutes 35
  seconds because the offline cache reference had a trailing newline. No bundle
  was published and no protected candidate processing began.
- Metadata-only eligibility job `1762293`: completed in 11 seconds; its exact
  aggregate, row counts, artifact hashes, and permissions independently pass.
- Public compute smoke: not submitted because no valid bundle exists.
- Protected DeepParse inference: not submitted or started.

## Current engineering decision

`STAGE07_PRELAUNCH_GATE_FAIL` is controlling. Remaining blockers are exact and
non-speculative:

1. one corrected public-only build must complete successfully and its immutable
   bundle must pass manifest, permissions, import-closure, stable-identity, and
   license/notices validation;
2. after bundle validation, the one public-only compute-node smoke must pass
   offline initialization, multilingual public synthetic determinism,
   multiprocessing spawn, and full native linkage;
3. a final exact-SHA prelaunch record must show all checks pass together.

Exactly one corrected replacement **public bundle build** is technically
justified by the isolated defect, but this report intentionally proposes the
correction before submission. No protected job is justified. Scientific status
remains `STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY`.
