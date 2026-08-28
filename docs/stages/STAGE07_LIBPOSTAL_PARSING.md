# Stage 7 — libpostal parsing

## Status

**DEVELOPMENT DESIGN AND PARSER-BUNDLE PROVENANCE IN PROGRESS.**

This branch starts from accepted `main` commit
`76435eb7ca5cd9a47a2a77fb36278568ba3bfc29`. The owner authorized one fresh
Stage 7 DEVELOPMENT workflow from design through candidate evidence, but not
Stage 7 acceptance. A later fresh independent-review session controls
acceptance. HOLDOUT, production Stages 2–7, Stage 8, and geocoding remain
unauthorized.

The scientific contract/profile names proposed for freezing after the
controlled design diagnostic are `stage07_libpostal_parsing_contract_v1` and
`stage07_libpostal_parsing_profile_v1`. The diagnostic can still expose a
scientific conflict; therefore this record does not yet declare those semantics
accepted or final.

## Accepted Stage 6 input boundary

Stage 7 is bound only to the immutable accepted Stage 6 DEVELOPMENT
publication:

- contract: `stage06_early_exact_deduplication_contract_v1`;
- profile: `stage06_early_exact_deduplication_profile_v1`;
- schema fingerprint:
  `9c07b7a4c3f7a5c43ad457dcf6f7fe3fd746d54d82a731139905b30828b6c9ce`;
- logical fingerprint:
  `2f6379c0cd5dc9654c03895cae6fdd48f3a7af528158c33e44d2030c816640b6`;
- input-binding fingerprint:
  `6ba224d6d24c3631aae8aac69f4a362bb054f01d9e3d09327ec6b0fdd85a0e7d`;
- manifest fingerprint:
  `e1da7b8ef04b65b1ece8e710720b57a8536841766fcf9de641f889b42eadd241`;
- ordered source identity:
  `fe2a4758582c1880d2b5c62dfc5c587d865e05d13033af9f5e8208b58e2a0487`;
- Benchmark V1 fingerprint:
  `014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf`;
- fixed-500 fingerprint:
  `014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52`;
- 51,779 ID-sorted unique candidates; and
- 69,747 source-representation occurrences over 35,000 DEVELOPMENT rows.

The processing unit is one Stage 6 unique registry row. Stage 7 will parse
`stage06_candidate_lower` exactly once and preserve its
`stage06_exact_candidate_id` plus all four other registry fields exactly. It
will not independently parse 69,747 occurrences or 35,000 source rows.

## Provisional scientific boundary

The exact parser call is intended to be:

```text
postal.parser.parse_address(stage06_candidate_lower)
```

No argument other than the exact accepted candidate is supplied. SAFE adds no
trim, case conversion, Unicode normalization, punctuation or whitespace
normalization, abbreviation expansion, geographic field, language hint, or
country hint. The accepted Stage 5 body deliberately excludes postcode, city,
region, and country; Stage 7 does not append them.

Pypostal returns an ordered list of `(value, label)` tuples. The adapter will
validate that exact wrapper contract and serialize it as an ordered Arrow list
of non-null structs with `label` then `value` fields. It will not sort,
deduplicate, combine repeated labels, convert the result to dictionary
semantics, map labels to SAFE fields, or alter returned strings. Stage 8 owns
label mapping.

The proposed output is one row per Stage 6 registry row, preserving the five
Stage 6 columns in order and appending:

- non-null `stage07_parse_status`, with `PARSED_NONEMPTY` or `PARSED_EMPTY`;
  and
- non-null `stage07_libpostal_components`, an ordered list of non-null
  `{label, value}` structs whose strings are non-null and exact UTF-8.

An exception, malformed wrapper result, null, non-string member, invalid UTF-8
round-trip, or partial output fails the run. Stage 7 does not synthesize a
component or relabel a technical failure as a successful empty parse. The
controlled diagnostic must confirm that this fail-closed policy covers real
DEVELOPMENT candidates without requiring an arbitrary hidden recovery rule.

## Exact parser bundle under construction

The controlled environment initially had neither libpostal nor pypostal.
Stage 7 therefore builds one self-contained public parser bundle in a scheduled
SLURM job before protected parsing. The source choices are exact, not moving:

- libpostal repository `openvenues/libpostal`, commit
  `25099c506612b34b23b1bfe286ca6321fcf06f35`, implementation 1.1.4,
  upstream description `v1.1.4-2-g25099c50`;
- upstream default libpostal model, with base/parser/language-classifier asset
  version files all pinned to `v1.0.0` by that source commit;
- pypostal repository `openvenues/pypostal`, commit
  `d6666a4f6a2ae0e7b83e037a35412f0f6b45c318`, package 1.1.11, upstream
  description `1.1-53-gd6666a4`; and
- pypostal runtime dependency `six==1.17.0`.

The default model is chosen because it is the upstream context-free default
for a worldwide input population. The alternative Senzing model is not
silently substituted or tuned on DEVELOPMENT. Parser quality remains subject
to the protected diagnostic and qualitative evaluation.

The bundle manifest enumerates every actual model/data file, pypostal runtime
file, dependency file, license file, and exact shared-library binary by
portable relative path, byte size, and SHA-256. It separately derives the
model/data fingerprint, pypostal runtime fingerprint, shared-library hash, and
complete `stage07_parser_bundle_fingerprint`. The scientific identity also
binds Python 3.14.3 / Unicode 16.0.0, compiler/glibc identities, UTF-8 runtime
settings, default no-hint parser options, and one initialization per process.

The locally available code-license files are copied without interpretation:
libpostal MIT, its bundled Sparkey Apache-2.0, and pypostal MIT. The bundle
records any license/notice file actually present in downloaded model assets.
If none exists, it records exactly that absence and does not guess model-data
license terms.

Bundle construction downloads public software/model assets only. It does not
open Stage 6 or any other protected input. Publication is owner-only, complete
content-hashed, fsynced, atomic, and immutable. Later protected jobs validate
the exact expected bundle fingerprint before opening input and make no network
calls while parsing.

The first public-only bundle submission, SLURM job `1760085` at design commit
`f437ec0f68e37d5cde197a97e761ad57cf201361`, failed in two seconds before
creating a build root or output. The path guard compared realpath-resolved
`/panfs/...` paths with the unresolved `/work/...` alias and returned
`STAGE07_CONTROLLED_PATH_REQUIRED`. Its empty stdout and 33-byte stderr remain
owner-only at mode `0600`. No software build, model download, protected input
access, or parser call occurred. The minimal correction resolves the controlled
root before comparison; any replacement uses new build/output identities and
does not overwrite this failed attempt.

## Controlled design diagnostic gate

After the bundle is frozen, one protected diagnostic will run through SLURM
from an exact pushed detached worktree. It will validate accepted Stage 6 and
cover:

1. all 613 unique candidates referenced by the frozen fixed-500 mapping;
2. all 123 multi-clean-surface lowercase groups and both clean surfaces per
   group;
3. all 23 candidates at least 1,000,000 code points, including the
   25,920,495-code-point maximum; and
4. deterministic length, script, mixed-script, punctuation, numeric,
   representation-provenance, singleton/repeated, and ordinary samples.

Protected strings and parser outputs remain in process memory or owner-only
diagnostic state and never enter stdout, Git, or portable evidence. The Git-safe
diagnostic contains aggregate counts, distributions, labels, timing,
determinism, and case-variant comparison results only.

Every clean surface in the 123 groups is compared against its accepted
lowercase canonical parse using ordered exact `(value, label)` equality. Any
label, value, count, order, or empty/nonempty difference is a scientific
conflict: the session stops before freezing the contract and does not silently
split the Stage 6 key or parse alternate surfaces.

The giant candidates receive exact full-string parser calls in isolated,
bounded compute processes so a native crash or resource failure becomes
aggregate technical evidence instead of corrupting another candidate. There is
no SAFE truncation, substring fallback, regex preprocessing, or inferred
component. Any inability to parse an accepted giant candidate exactly is a
scientific conflict requiring an explicit pipeline decision.

## Execution and scaling direction

DEVELOPMENT will prefer one parser process if diagnostic throughput is
adequate. This avoids assuming native thread safety and provides one model
initialization. The materializer is designed for independent candidate-ID range
shards in future work, but restores exact Stage 6 registry order and never
changes a result by worker count, input shard layout, Arrow batch size, Parquet
row-group size, or output shard size.

Production-capable code streams bounded Arrow batches and Parquet shards. It
does not use pandas, population-sized Python dictionaries/sets/lists, a whole
registry `to_pylist`, or a population-sized parse-result buffer. The estimated
208,667,272 production candidates remain planning-only; no production Stage 7
run is authorized.

## Required stop gate

This session may ultimately declare only
`STAGE_7_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW` or
`STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY`. It must not declare
`STAGE_7_ACCEPTED`, merge to `main`, start Stage 8, access HOLDOUT, start a
production stage, or geocode.
