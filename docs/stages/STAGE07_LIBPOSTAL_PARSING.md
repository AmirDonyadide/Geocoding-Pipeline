# Stage 7 — libpostal parsing

## Status

**`STAGE_7_DEVELOPMENT_IN_PROGRESS` (candidate not yet ready).**

This branch starts from accepted `main` commit
`76435eb7ca5cd9a47a2a77fb36278568ba3bfc29`. The owner authorized one fresh
Stage 7 DEVELOPMENT workflow from design through candidate evidence, but not
Stage 7 acceptance. A later fresh independent-review session controls
acceptance. HOLDOUT, production Stages 2–7, Stage 8, and geocoding remain
unauthorized.

The controlled design diagnostic exposed a material parser limitation before
the contract/profile freeze: four of the 23 accepted candidates with at least
1,000,000 code points crashed their isolated native parser process, including
the accepted 25,920,495-code-point maximum. The session therefore stopped as
required. Proposed names `stage07_libpostal_parsing_contract_v1` and
`stage07_libpostal_parsing_profile_v1` were not frozen, implementation and the
authoritative 51,779-candidate run did not begin, and no candidate is eligible
for independent review.

That not-ready conclusion remains immutable and historically correct at
evidence commit `d132fd9d665995fc07743c512769e44fa7fcae0b`. The owner has now
authorized a later revised Stage 7 design attempt, limited first to a targeted
supervisor diagnostic over the same 23 accepted giant candidates. This does
not retroactively pass the first design, freeze the contract/profile, accept
Stage 7, authorize independent review, or change accepted Stage 6 science.

That targeted diagnostic completed as job `1760182` from exact pushed commit
`7e9abc43aee8285ac0cf47d8c56acd883c6f4cd4`. It reproduced the prior 19/4
split under the original 48 GiB ceiling, then parsed all 23 exact giants
successfully on their first uncapped attempt in a 180 GiB job. The four prior
failures were therefore resource-cap dependent. Per the owner's stop rule, the
technical-failure status and resource contract require reconsideration before
contract freeze. The sanitized [revised diagnostic report](../../reports/development/stage07_supervisor_diagnostic_summary.md)
records the aggregate evidence.

## Owner-authorized revised proposal — v1 contract frozen for implementation

The complete 123-group / 246-surface case diagnostic is controlling evidence:
all ordered parses were exactly equal. The accepted
`stage06_candidate_lower` therefore remains the sole Stage 7 parse-once key.
Clean/case-preserving surfaces remain upstream provenance and are not added to
the key or parsed independently in the authoritative pipeline.

Every Stage 6 candidate must receive exactly one Stage 7 row. The owner’s
resource-sufficient decision freezes fail-closed handling: an unresolved native
parser crash aborts publication and is not a v1 row status. The v1 vocabulary is:

| Status | Parser outcome | Component representation |
|---|---|---|
| `PARSED_NONEMPTY` | Parser returned normally with at least one component | non-null ordered list of length at least one |
| `PARSED_EMPTY` | Parser returned normally with zero components | non-null exact empty list `[]` |

A wrapper exception, malformed result, Python failure, schema error,
publication error, crash→success retry, repeated crash, or changed technical
failure aborts the complete publication. No size threshold skips parsing and
no candidate timeout is part of the status contract; authoritative DEVELOPMENT
uses a validated 180 GiB allocation with no internal address-space ceiling.

The earlier `PARSER_PROCESS_CRASH` proposal remains rejected historical design
evidence and is not part of the v1 schema.

## Revised supervised execution design

A synchronous parent owns one exact active candidate and one long-lived
spawned libpostal child. Requests and results carry an internal monotonic frame
sequence. Before calling libpostal, the child acknowledges that sequence plus
the exact input code-point count and SHA-256. An exit before this acknowledgment
aborts and cannot qualify as a candidate crash. The parent accepts a result
only when sequence and input identity match, so a neighbor cannot be omitted or
cross-wired. The child initializes the frozen parser bundle once and remains
alive across normal candidates.

If the active child terminates before returning a valid frame, the parent
records privacy-safe exit/signal, framing, runtime, and observable memory
metadata, starts a fresh child with the same frozen bundle, and retries the
same exact candidate once:

1. crash then the same crash signature: publish `PARSER_PROCESS_CRASH` with
   null components;
2. crash then success: fail with parser/execution nondeterminism; or
3. crash then another technical outcome or different exit/signal signature:
   fail with technical nondeterminism.

The successful ordinary path is attempted once. The supervision rule applies
to every candidate and contains no giant-specific production semantics. The
targeted diagnostic additionally performs a third fresh attempt for each
reproducibly crashing giant as pre-contract evidence, but the proposed
publication contract remains exactly two attempts after an initial crash.

The first diagnostic imposed a 48 GiB child address-space ceiling and retained
only aggregate giant results. The targeted job first replays that immutable
isolated code path to reconstruct an owner-only candidate-level 19/4 reference
and ordered digests; its original 900-second guard and 48 GiB cap are reference
conditions, not proposed publication policy. The revised supervisor path then
has no per-candidate timeout or address-space ceiling and runs in a job
requesting 180 GiB on a 191 GB Goethe node. Candidate-by-candidate comparison
therefore tests whether the same prior failures persist under the larger
allocation rather than freezing a failure state around a potentially fixable
SAFE resource cap. The same parser-bundle fingerprint remains binding.

## Provisional revised output representation

The proposed registry continues to preserve the five Stage 6 registry columns
exactly and append only `stage07_parse_status` plus
`stage07_libpostal_components`. A separate published `stage07_failure_code` is
not proposed: with one approved technical-failure state it would duplicate the
status invariant. The internal/aggregate technical code for that state is the
fixed public value `NATIVE_PROCESS_CRASH`; low-level attempt evidence remains
owner-only and is not copied into the registry.

The proposed nested type is a nullable Arrow
`large_list<struct<label: large_string not null, value: large_string not
null> not null>`. A 64-bit list offset is justified by the observed 263,385
components in the first diagnostic and 881,338 in the uncapped giant audit,
plus future shard scalability. `large_string`
children avoid a 32-bit cumulative value-offset dependency within a batch.
List order, duplicate labels, duplicate values, and exact strings remain
authoritative. Parquet round-trip, one-row giant row groups, page sizing,
checksums, and per-candidate construction memory must pass the targeted gate
before this schema can be frozen.

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

## First-design scientific boundary and revision

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

The first design proposed one row per Stage 6 registry row, preserving the five
Stage 6 columns in order and appending:

- non-null `stage07_parse_status`, then limited to `PARSED_NONEMPTY` or
  `PARSED_EMPTY`; and
- non-null `stage07_libpostal_components`, then an ordinary ordered list of non-null
  `{label, value}` structs whose strings are non-null and exact UTF-8.

An exception, malformed wrapper result, null, non-string member, invalid UTF-8
round-trip, or partial output fails the run. Stage 7 does not synthesize a
component or relabel a technical failure as a successful empty parse. The
controlled diagnostic showed that this policy did not cover four real
DEVELOPMENT candidates. The later owner decision above revises only those
status/null semantics and the offset-width choice: confirmed native crashes
receive `PARSER_PROCESS_CRASH` with a null `LargeList`. All other wrapper,
schema, and publication failures remain fail-closed.

## Exact frozen parser bundle

The controlled environment initially had neither libpostal nor pypostal.
Stage 7 therefore builds one self-contained public parser bundle in a scheduled
SLURM job before protected parsing. The source choices are exact, not moving:

- libpostal repository `openvenues/libpostal`, commit
  `25099c506612b34b23b1bfe286ca6321fcf06f35`, implementation 1.1.4,
  upstream description `v1.1.4-2-g25099c50`, installed ABI binary
  `libpostal.so.1.0.1`;
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

The controlled Stage 7 runtime is created anew for each execution and pins
Python 3.14.3 / Unicode 16.0.0, pip 26.2.1, setuptools 80.9.0, wheel 0.45.1,
DuckDB 1.5.5, ftfy 6.3.1, and PyArrow 25.0.0. The exact pushed repository is
installed editable with dependency resolution and build isolation disabled.
Public dependency acquisition completes before any protected Stage 6 input is
opened; protected parser execution makes no network calls.

The replacement public-only bundle submission, SLURM job `1760128` at
diagnostic commit `6ea9dd2e0560e00f80a585d7c4e7e999e9b48a47`, failed after
17 seconds during upstream autotools bootstrap. Goethe provided libtool 2.4.6,
but `autoreconf` did not stage the libtool macros, so automake reported
`LIBTOOL` undefined. The owner-only logs remain mode `0600`; the failed build
root is preserved, and no immutable bundle output was published. No protected
input was opened and no parser call occurred. The bounded correction explicitly
runs the installed `libtoolize --copy --force` before the unchanged upstream
`bootstrap.sh`; the frozen build identity records the compiler, make,
autoconf, automake, libtoolize, and pkg-config versions. A replacement must use
new build and output identities.

The next public-only bundle submission, SLURM job `1760131` at commit
`e042b65ea7890d8870ba91214866ab4293c11670`, failed after 12 seconds because
the compute-node image did not expose `libtoolize` (`127`) even though the
login-node image did. Its owner-only logs and build root remain preserved; no
bundle output was published, no protected input was opened, and no parser call
occurred. The next bounded correction downloads the official GNU libtool 2.4.6
release tarball inside the public-only job, requires SHA-256
`e3bd4d5d3d025a36c21dd6af7ea818a2afcd4dfc1ea5a17b39d7854bcd0c06e3`,
installs it under that attempt's private build root, and invokes the exact
private `libtoolize`. It does not depend on login-node tools or modify a shared
environment.

Public-only bundle job `1760139` at commit
`7eb16a84d9e6016f6c8ac8fce6d5bb9c0a2f334f` then failed after nine minutes
with curl exit `28`: the compute node could clone GitHub but could not connect
to the primary `ftp.gnu.org` HTTPS endpoint. Its logs are mode `0600`, its
failed build root remains mode `0700`, and its intended immutable output is
absent. No protected input or parser call occurred. The next bounded correction
uses the public GNU mirror at `mirrors.ibiblio.org`, which serves the same
official `libtool-2.4.6.tar.gz`; the existing required SHA-256 remains unchanged
and therefore controls artifact identity independently of the acquisition host.

Public-only bundle job `1760146` at commit
`ff44c596e7a5d0069a92be59c55ed8b078ee09f4` reached the GNU mirror, verified
and built libtool 2.4.6, and used the private `libtoolize` to stage libpostal's
macros and `ltmain.sh`. It then failed after 32 seconds because upstream
`bootstrap.sh` runs `autoreconf`, which invokes `libtoolize` again by command
name, while the private prefix was not yet in `PATH`. No bundle output was
published and no protected input or parser call occurred; logs and the failed
build root remain owner-only. The bounded correction exposes only that exact
private libtool `bin` directory to upstream bootstrap.

Public-only bundle job `1760148` at commit
`0021bbf5f94045d4ed8461691d2afd4b6dfa2478` then completed the pinned
libtool/libpostal build and downloaded all upstream default model assets. It
failed after 3 minutes 36 seconds on SAFE's shared-library filename assertion:
libpostal implementation 1.1.4 installs ABI binary `libpostal.so.1.0.1`, not
`libpostal.so.1.1.4`. The failed root and mode-`0600` logs are preserved, no
immutable bundle was published, and no protected input or parser call occurred.
The bounded correction binds and copies the actual installed ABI binary while
retaining implementation version 1.1.4 as a separate provenance field.

Public-only bundle job `1760150` at commit
`d8427a1584a534052ee10b375041346fd03b4af1` passed the corrected ABI gate and
again completed libpostal/model installation. It failed after 4 minutes 4
seconds immediately before pypostal compilation because Bash prohibits a
per-command assignment to the already-readonly shell variable
`LIBPOSTAL_PREFIX`. No immutable bundle was published and no protected input or
parser call occurred; its owner-only logs and failed root are preserved. The
bounded correction uses `env` to pass that exact prefix to pypostal's pinned
`setup.py` without assigning the shell variable.

Public-only parser-bundle job `1760151` at commit
`2063317745389465eb8cd62d8e5cbab50235de2a` completed in 4 minutes 35
seconds with MaxRSS 749,652 KiB. It initialized the parser in 4,948 ms, parsed
the public smoke fixture into two components, revalidated every artifact, and
atomically published the owner-only immutable bundle. Exact identities are:

- complete parser-bundle fingerprint:
  `f3c6db7e9f11ab75b2207be773e946d531dbba763008d9f7e5036d8c923dc2ae`;
- parser model/data fingerprint:
  `0b067a2697e9f90cef92c806701c08648a1f5127c17f0f3168ecaed186dc3293`;
- pypostal runtime fingerprint:
  `ccc547bfdcaf391685cbb3285be9a02d84c28c7671dcafb4450d25c03920f7ff`;
- exact `libpostal.so.1.0.1` SHA-256:
  `3e2aa3e23b62c22b77827b47d78692d49ae3d693c07ee7ad3763e9b97438cb5e`;
- parser-bundle manifest SHA-256:
  `12a0080bff6b3ed2420847124eb918d91b7582214e3d4b037628bf5b9022340d`.

The manifest enumerates 56 public runtime/model artifacts totaling
2,013,605,137 bytes. Manifest and success marker reconcile exactly; all 58
published files are mode `0600`, every directory is mode `0700`, and there are
zero symlinks. No license/notice file was present in the downloaded upstream
model assets, so that absence is recorded without adding a SAFE license
interpretation. Protected inputs opened: no.

## Controlled design diagnostic result

The protected diagnostic ran through SLURM from exact pushed commit
`48c66f7beb0437d7f0a6cea575c560a2a9c6c920` as job `1760156`. It validated
the accepted Stage 6 binding and covered:

1. all 613 unique candidates referenced by the frozen fixed-500 mapping;
2. all 123 multi-clean-surface lowercase groups and both clean surfaces per
   group;
3. all 23 candidates at least 1,000,000 code points, including the
   25,920,495-code-point maximum; and
4. deterministic length, script, mixed-script, punctuation, numeric,
   representation-provenance, singleton/repeated, and ordinary samples.

Protected strings and parser outputs remained in process memory or owner-only
diagnostic state and never entered stdout, Git, or portable evidence. The
Git-safe [diagnostic summary](../../reports/development/stage07_design_diagnostic_summary.md)
contains aggregate counts, distributions, labels, timing, determinism, and
case-variant comparison results only.

Every clean surface in the 123 groups is compared against its accepted
lowercase canonical parse using ordered exact `(value, label)` equality. Any
label, value, count, order, or empty/nonempty difference is a scientific
conflict: the session stops before freezing the contract and does not silently
split the Stage 6 key or parse alternate surfaces.

The first protected design diagnostic, SLURM job `1760154` at commit
`47e80fae17ca7cfabda14d189f0aebf713cef841`, validated its pinned runtime and
bundle and entered giant-candidate parsing. It failed after 3 minutes 50
seconds with MaxRSS 25,051,868 KiB because an isolated child closed its pipe
without a payload and the parent allowed `EOFError` to escape. No final output
was published; its owner-only runtime, logs, and incomplete attempt are
preserved. The traceback contained paths and code only, no protected values.
This is a harness failure rather than evidence that the candidate parsed
successfully. The bounded correction treats EOF, OS-level pipe closure, or a
malformed child payload as aggregate `PROCESS_CRASH`, allowing the diagnostic
to complete and surface any genuine giant-parser limitation as a scientific
conflict instead of losing the evidence.

The giant candidates receive exact full-string parser calls in isolated,
bounded compute processes so a native crash or resource failure becomes
aggregate technical evidence instead of corrupting another candidate. There is
no SAFE truncation, substring fallback, regex preprocessing, or inferred
component. Any inability to parse an accepted giant candidate exactly is a
scientific conflict requiring an explicit pipeline decision.

The replacement diagnostic completed in 7 minutes 51 seconds with MaxRSS
25,062,976 KiB. Its deterministic 986-candidate selection included all 613
fixed-500 unique candidate IDs, all 123 multi-surface groups and 246 clean
surfaces, all 23 giant candidates, and the required stratified samples. Its
selection fingerprint is
`a81995f832f89cdc5053827d6479c2170641815a44f3e64c90c9d3a6816fe3df`;
the aggregate diagnostic evidence SHA-256 is
`7b09fb79a6ef905c1e41d9387fc7ebfa5a24b257c8aee50d779f96aa47e32283`.

The lowercase safety gate passed exactly: all 123 groups and all 246 clean
surfaces parsed without error; 123 groups had exact ordered output equality and
zero had label, value, count, ordering, or empty/nonempty differences. All 64
repeat-determinism candidates matched in-process, in a fresh process, with
batch size 1, and with reversed batch-17 input. This evidence supports the
accepted lowercase candidate as a parse-once key for the tested groups.

The parser emitted 2,481,811 components for 979 `PARSED_NONEMPTY` and three
`PARSED_EMPTY` diagnostic candidates. Four candidates had `PROCESS_CRASH` and
were not reclassified as empty parses. Nineteen of the 23 giant candidates
parsed; four crashed, including the maximum accepted candidate. Consequently,
the diagnostic gate is `SCIENTIFIC_CONFLICT` with
`GIANT_CANDIDATE_PARSER_LIMITATION` and
`PROTECTED_CANDIDATE_PARSER_FAILURE`.

The minimum next scientific decision is an explicitly reviewed pipeline policy
for exact accepted giant candidates. The current evidence does not authorize
arbitrary truncation, substring parsing, silently dropping candidates,
inventing a fake component, or treating a native crash as `PARSED_EMPTY`.
Whether the response belongs in upstream candidate construction/deduplication
or in an explicit Stage 7 technical-failure contract must be decided before a
new contract/profile can be frozen. This record makes no such choice.

## Targeted supervisor diagnostic result

The revised implementation commit
`7e9abc43aee8285ac0cf47d8c56acd883c6f4cd4` introduced exact-input
acknowledgment, synchronous private IPC, a long-lived spawned parser child,
one exact fresh retry after a native exit, privacy-safe attempt evidence, and a
bounded one-giant-at-a-time `LargeList` Parquet audit. Before submission, 43
focused Stage 7 tests, 218 Stage 2–7 regressions, and 485 full local-safe tests
passed; Ruff, strict mypy over 72 source files, formatting, shell syntax, JSON,
Markdown links, privacy checks, and `git diff --check` also passed.

Job `1760182` completed with exit `0:0` in 16 minutes 3 seconds. Its immutable
aggregate diagnostic SHA-256 is
`a14a92feddd64dd8f2b9720e3697808d0c1164fa02b6ed72e281d5f3ae2db067`;
the owner-only controlled evidence SHA-256 is
`affbcdb088489f4f92b8c5972692e82f3408a0413fbf1fab0ef45c49c91cbf9c`.
The parser bundle remained exactly
`f3c6db7e9f11ab75b2207be773e946d531dbba763008d9f7e5036d8c923dc2ae`.

The first-diagnostic code-path replay under its exact 48 GiB address-space
ceiling reproduced 19 successes and the same four owner-only crash identities.
The uncapped supervisor then produced 23 `PARSED_NONEMPTY` results, zero empty
results, zero native crashes, zero restarts, zero cross-wires, and 23 exact
input acknowledgments. All 19 prior-success ordered digests matched exactly;
all four prior-crash candidates succeeded. The maximum accepted candidate also
returned `PARSED_NONEMPTY` without truncation or substring parsing.

The revised children reached an observed maximum 56,327,384 KiB RSS, above
the earlier 48 GiB ceiling. This evidence establishes that the earlier cap was
materially causal; it does not establish an intrinsic parser crash class for
the four candidates. The contract-freeze gate is therefore
`SCIENTIFIC_CONFLICT`, controlled by
`PRIOR_CRASH_SUCCEEDS_WITH_REVISED_RESOURCES`.

All 23 successful giant parses round-tripped exactly through the provisional
nullable `LargeList` representation. The maximum observed component count was
881,338, maximum output-value total was 25,187,643 code points, and the largest
one-row Parquet audit was 7,932,166 bytes. This supports the provisional Arrow
offset choice but does not freeze the schema.

The aggregate harness stopped its optional repeat phase at the first prior
capped-crash identity that again succeeded uncapped. Consequently its combined
parent-survival and crash→success fields describe that cross-resource early
stop, not a current same-resource first-crash/retry event. The complete
uncapped first pass survived and returned valid results for all 23 candidates.

The minimum scientific decision is now an explicit owner choice about both:

1. the resource sufficiency contract required for exact giant parsing; and
2. whether `PARSER_PROCESS_CRASH` remains justified as prospective resilience
   despite no reproducible resource-sufficient DEVELOPMENT crash, or whether
   any unexpected native crash should instead abort Stage 7 fail-closed.

No such choice is made here. Accepted Stage 6 science, the lowercase parse-once
key, exact input, and the parser bundle remain unchanged.

## Work unexecuted after the targeted stop gate

Because both design gates failed, no Stage 7 materializer, output schema, input
binding, contract/profile, or materializer implementation was frozen. No authoritative
51,779-candidate DEVELOPMENT job was submitted. Post-publication validation,
full fixed-500 map-back verification, the risk-stratified qualitative review,
output invariance tests, throughput projection, and output fingerprints are
therefore not applicable. Proposed bounded streaming and single-process
execution remain unimplemented design direction, not evidence.

The estimated 208,667,272 production candidates remain planning-only. No
production run, HOLDOUT access, Stage 8 work, or geocoding occurred.

## Current required stop gate

The first design declared `STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY` and remains
preserved as such. The revised attempt also declares
`STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY`. It does not declare
`STAGE_7_ACCEPTED`, merge to `main`, begin independent review, start Stage 8,
access HOLDOUT, start a production stage, or geocode.
