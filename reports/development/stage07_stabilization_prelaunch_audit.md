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
[`stage07_failure_ledger.json`](stage07_failure_ledger.json). After the current
public attempts resolved, known root categories are:

| Root category | Count | Controlling lesson |
|---|---:|---|
| `ORCHESTRATION_PATH_FAILURE` | 2 | Validate controlled worktree/output topology before submission. |
| `ORCHESTRATION_ENVIRONMENT_FAILURE` | 1 | Assert required execution markers before scheduling. |
| `SHELL_OR_QUOTING_FAILURE` | 2 | Syntax and exact command framing are submission gates. |
| `MULTIPROCESS_LAUNCHER_FAILURE` | 1 | Exercise the real spawn entry point before protected work. |
| `RESOURCE_CEILING_FAILURE` | 1 | Do not impose the invalid 48 GiB process ceiling. |
| `BUNDLE_CONTAMINATION_FAILURE` | 2 | Reject cache/bytecode contamination and bind the runtime exactly. |
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
- exact 79-distribution version lock and SHA-256 acquisition lock, with
  `pip --require-hashes`, exact post-install freeze equality, and complete
  installed-file hashing;
- exact pinned paths and hashes for the model, tokenizer/embedding, public
  source archives, DeepParse/BPEmb wheels, licenses/notices, and runtime locks;
- physically enforced read-only publication: directories/executables `0555`,
  ordinary files `0444`, no external hard links, no symlinks, and zero writable
  paths or Python bytecode/cache artifacts;
- complete tree identity over path, type, mode, size, content hash, directories,
  and symlink policy, plus pre/post comparison of every mutation category;
- recursive payload and directory `fsync`, target-filesystem no-replace atomic
  rename probing, and race-safe output-collision rejection;
- every mutable HOME, temporary, XDG, Hugging Face, Transformers, Torch, and
  Python cache path bound to a fresh `0700` runtime root outside the bundle;
- Git-bound canonical launchers/eligibility asset, ignored-file rejection, and
  metadata-only login-node preflight without population/bundle payload rehash.

### Resolved bundle corrections and current smoke blocker

The minimum correction writes the exact revision as 40 bytes without a
terminating newline, checks both byte length and value, and requires
`huggingface_hub.try_to_load_from_cache(..., revision="main")` to resolve both
the config and weights before model initialization. Focused synthetic tests and
shell syntax pass locally, and a public metadata-only resolver check against a
temporary cache view resolved both preserved checkpoint files with the exact
40-byte reference. Job `1762661` validated this correction, the later exact-argv
publication correction, and the complete immutable bundle publication at that
time.

Compute smoke job `1762663` did not test the bundle: the launcher omitted
`SAFE_EXECUTION_SITE=goethe-nhr`, and the first guarded call failed before any
bundle or synthetic input access. Commit
`6a64c830b784eb9742e70ad648243e87b54a1b9b` corrected the launcher and added an
exact prelaunch check that exercises the real Goethe/SLURM guard and audits all
eight required smoke environment variables. That gate passed before replacement
job `1762669`.

Job `1762669` reached the bundle validator, proving the execution-site
correction, but the bundle tree was no longer identical to its successful
publication state. The manifest still declares 29,590 artifacts and none are
missing, while the current tree contains 363 additional unmanifested `.pyc`
files in 39 `__pycache__` directories with mode `0755`. Public timing and path
evidence proves they predate both compute smokes and match the import closure of
a login-side Hugging Face offline cache-resolution preflight. That command
invoked the published Python runtime while the tree was writable and without
`-B` or `PYTHONDONTWRITEBYTECODE=1`. The controlling root cause is
`POST_PUBLICATION_LOGIN_SIDE_PYTHON_IMPORT_MUTATED_WRITABLE_BUNDLE`; DeepParse
inference, Torch/model initialization, and the smoke jobs did not cause it. The
validator failed closed before model initialization, linkage inspection, or
public synthetic parsing. No output was published.

The frozen bundle must not be repaired in place: deleting files or changing
modes would mutate the preserved attempt again. Owner decision D030 authorizes
exactly one fresh public-only read-only v2 bundle after every prelaunch gate
passes. The contaminated tree remains historical provenance and is not reused.

### Final V2 prelaunch outcome

The exact pushed-SHA/path/resource gates passed, but the mandatory publication
filesystem probe failed with PanFS `EINVAL` before scheduling. Consequently no
fresh read-only bundle, compute-image linkage evidence, multilingual model
smoke, or imported-distribution runtime evidence exists for V2. The probe left
no build/output path. No protected DeepParse inference is justified, and D030
prohibits another infrastructure iteration.

## Prelaunch checklist

| Gate | Current state |
|---|---|
| Methodology consistency | PASS |
| Country eligibility definition frozen | PASS |
| Exact clean pushed/detached execution SHA | PASS — `1b6aa0c204a9e4369969b603f358763fcedec71c` |
| Controlled worktree/path policy | PASS until the exact target-filesystem atomic probe |
| Local focused tests/static/syntax | PASS — 119 Stage 7 tests, 294 Stage 2–7 regressions, and 561 local-safe tests (4 deselected) under exact Python 3.14.3; Ruff, strict mypy, shell syntax, and diff check |
| Eligibility denominators | PASS — job `1762293`, independently reopened |
| Dependency/import closure | Historical PASS in job `1762661`; exact 79-distribution hash lock frozen for v2 |
| Binary linkage | NOT RUN; smoke job `1762669` stopped during bundle reopen |
| Python runtime completeness | PASS in published bundle job `1762661` |
| Bundle/model hashes | Historical PASS in job `1762661`; v2 Python validator binds every required public asset path/hash |
| Offline cache binding | PASS in job `1762661` |
| Offline synthetic initialization | PASS in job `1762661`; zero network attempts |
| Public multilingual smoke | FAILED before model execution in job `1762669` |
| Read-only permission design | LOCAL BEHAVIORAL PASS; fresh bundle was not executed |
| Target-filesystem no-replace atomic publication | FAIL — PanFS returned `EINVAL` (errno 22) for same-parent `renameat2(RENAME_NOREPLACE)` |
| Disk/inode/resource preflight | PASS for bundle and smoke submissions |
| JSON and Markdown-link checks | PASS for changed sanitized evidence |
| Privacy/tracked-data audit | PASS; no protected or controlled artifact is tracked |
| No protected data in public tests | PASS BY DESIGN/STATIC REVIEW |
| No HOLDOUT / production | PASS |
| No network during protected execution | IMPLEMENTED; PROTECTED EXECUTION NOT AUTHORIZED |

## Small compute-node smoke design

One public-only job requests 4 CPUs, 16 GiB, and 30 minutes. It validates the
exact frozen bundle, imports the complete selected-model runtime closure,
initializes the exact BPEmb-attention model with network denied, parses Latin,
Cyrillic, and Hangul public synthetic inputs belonging only to documented
training countries twice, checks exact structured determinism, exercises
`multiprocessing` spawn, audits every material dynamic ELF dependency, writes
and reopens owner-only JSON evidence, and exits. It reads no protected input.

The first smoke was submitted as job `1762663` but stopped at the fail-closed
execution-site guard before bundle validation or public parsing. The corrected
replacement, job `1762669`, passed the execution-marker preflight and reached
bundle validation, which rejected post-publication bytecode/cache contamination.
The final smoke design adds a fresh external runtime root, Python `-B`, inherited
bytecode suppression, exact runtime/model/distribution identities, explicit
execution SHA/job/site provenance, exact input acknowledgements, nonempty output
counts, and complete pre/post tree identity. A larger or protected DeepParse
diagnostic remains prohibited.

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
- Corrected public bundle job `1762652` at
  `dee39ba71ae44b4bf4b6146a40057b31ab7fa008`: failed pre-scientifically after
  9 minutes 14 seconds. The exact 40-byte cache correction, all pinned public
  asset hashes, and offline synthetic initialization passed with zero network
  attempts. Publication then failed because configure values beginning with
  `--` were passed as separate `argparse` value tokens. The failed build tree is
  preserved, the immutable output path was never created, and no protected
  candidate processing began.
- Corrected public bundle job `1762661` at
  `843f30c10e4fc359258869ea3904ba90fb4abe6f` completed in 10 minutes 30
  seconds. It atomically published 29,590 public artifacts totaling
  1,745,597,602 bytes with bundle fingerprint
  `564f8e416b7e88f0d1d94e3d486b97ae33c73cb6c065adc31f060078f84700ab`.
  All pinned hashes, the exact cache reference, complete imports, model
  initialization, post-publication rehash, and the published offline smoke
  passed with zero network attempts. Independent metadata reopening confirmed
  owner-only permissions, five license/notice artifacts, zero symlinks, and
  zero bytecode/cache artifacts. Protected candidate processing did not begin.
- Metadata-only eligibility job `1762293`: completed in 11 seconds; its exact
  aggregate, row counts, artifact hashes, and permissions independently pass.
- Public compute smoke job `1762663` failed pre-scientifically after two
  seconds at the first guarded bundle-validation call. The launcher did not
  export `SAFE_EXECUTION_SITE=goethe-nhr`, so the fail-closed execution guard
  rejected the operation before bundle validation, model initialization,
  linkage inspection, or public synthetic parsing. The new owner-only runtime
  root contains only its empty temporary directory; no smoke output exists.
- Corrected public compute smoke job `1762669` at
  `6a64c830b784eb9742e70ad648243e87b54a1b9b` failed pre-scientifically after two
  seconds. Its exact execution-site/SLURM preflight passed and bundle validation
  began. Validation found 39 non-private cache directories and 363 unmanifested
  bytecode files in the published runtime tree. No manifest artifact is missing;
  model initialization, linkage checks, multiprocessing, and public synthetic
  parsing did not begin. Network attempts and protected inputs opened were zero,
  and no smoke output exists.
- Protected DeepParse inference: not submitted or started.

## Current engineering decision

`STAGE07_PRELAUNCH_GATE_FAIL` is controlling. The complete local V2 gates passed
and exact pushed SHA `1b6aa0c204a9e4369969b603f358763fcedec71c` was opened as a clean detached
Goethe worktree. The mandatory probe then established that the exact PanFS
publication parent rejects Linux same-parent
`renameat2(RENAME_NOREPLACE)` with `EINVAL` (errno 22). The probe cleaned its
temporary tree; neither the fresh build path nor output path was created, and
no SLURM job was submitted.

This is a target-filesystem reproducibility failure at the final architecture's
fail-closed atomic-publication boundary. Weakening no-replace semantics or
starting another packaging redesign would violate D030's hard stop. Therefore
`DEEPPARSE_INFRASTRUCTURE_PATH_NOT_JUSTIFIED` is the engineering conclusion.
Stage 7 should proceed only after a new owner scientific decision, using
libpostal on its eligible population, an explicit semantic-readiness policy,
and conservative abstention for unsafe structured parses while preserving the
exact Stage 6 candidate and raw Stage 7 evidence. Scientific status remains
`STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY`.
