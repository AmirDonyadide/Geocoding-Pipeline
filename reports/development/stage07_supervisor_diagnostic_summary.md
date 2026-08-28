# Stage 7 revised supervisor-diagnostic summary

## Verdict

`STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY`

The revised pre-contract gate stopped for the resource-dependent outcome the
owner explicitly required Stage 7 to detect. Replaying the immutable first
diagnostic's exact 48 GiB isolated path reproduced 19 successful giants and
four process crashes. The same 23 exact candidates then ran through the
uncapped supervisor in a 180 GiB SLURM job: all 23 returned
`PARSED_NONEMPTY` on their first exact attempt, including the same four prior
failures and the accepted 25,920,495-code-point maximum.

The four earlier outcomes are therefore not reproducible native-parser
failures under the resource-sufficient configuration tested. The 48 GiB
address-space ceiling was materially causal. The proposed
`PARSER_PROCESS_CRASH` publication state cannot be frozen on the premise that
these four candidates require it. Stage 7 needs an explicit resource contract
and owner reconsideration of whether a published technical-failure state is
still scientifically necessary.

No contract/profile was frozen, no authoritative 51,779-candidate job was
submitted, and no independent review began. This is not Stage 7 acceptance.

## Immutable identity

- Base main: `76435eb7ca5cd9a47a2a77fb36278568ba3bfc29`
- Preserved first not-ready evidence HEAD:
  `d132fd9d665995fc07743c512769e44fa7fcae0b`
- Targeted supervisor implementation:
  `7e9abc43aee8285ac0cf47d8c56acd883c6f4cd4`
- Targeted diagnostic job: `1760182` (`COMPLETED`, exit `0:0`)
- Parser-bundle fingerprint:
  `f3c6db7e9f11ab75b2207be773e946d531dbba763008d9f7e5036d8c923dc2ae`
- Giant selection fingerprint:
  `c66e9c1301efe4e1b4bbf0ed48183d96dd335304220a23dd9d44a6b5a9c73c4b`
- Aggregate evidence SHA-256:
  `a14a92feddd64dd8f2b9720e3697808d0c1164fa02b6ed72e281d5f3ae2db067`
- Owner-only controlled evidence SHA-256:
  `affbcdb088489f4f92b8c5972692e82f3408a0413fbf1fab0ef45c49c91cbf9c`
- Success-marker SHA-256:
  `dc6748d94aed51b9f3a5ae2fe43204dc8a58cb48f3a3541514e525170a432e86`

All protected candidates and parser components remained on Goethe. Git-safe
evidence contains aggregates and public hashes only.

## Exact input and parser binding

The diagnostic remained bound to the accepted Stage 6 immutable registry:

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
- registry rows: 51,779; and
- occurrences: 69,747 total, 34,822 STANDARD, 34,925 NATIVE.

The exact parser input remained `stage06_candidate_lower`. SAFE supplied no
trim, normalization, appended geography, country hint, language hint, or
other context. The parser call remained
`postal.parser.parse_address(exact_candidate)` using the unchanged pinned
offline bundle. Accepted Stage 6 science was not changed.

## Candidate-by-candidate resource comparison

The first aggregate diagnostic did not persist candidate-level giant digests.
The targeted job therefore first replayed that immutable diagnostic's exact
isolated code path under its original 48 GiB address-space ceiling. This
owner-only reference recovered the prior candidate-level partition without
publishing protected IDs:

| Execution condition | Successful | Process crash | Total |
|---|---:|---:|---:|
| Replayed 48 GiB isolated reference | 19 | 4 | 23 |
| Uncapped supervised first pass, 180 GiB job | 23 | 0 | 23 |

All 19 prior successes matched their reference status and ordered parse digest
exactly. All four prior crash identities succeeded under the uncapped
supervisor. Each of the 23 revised attempts acknowledged the exact input
code-point count and SHA-256 before parsing; all 23 completed one valid result
frame with zero cross-wires and zero input-acknowledgment failures.

The revised first pass had:

- `PARSED_NONEMPTY`: 23;
- `PARSED_EMPTY`: 0;
- native process crashes: 0;
- child exit/signal aggregate: empty;
- worker restarts: 0;
- current same-resource crash→success nondeterminism: 0; and
- parent survival through all 23 candidates: yes.

The legacy reference helper classifies abnormal child completion only as
`PROCESS_CRASH`; it did not persist exit-code/signal or child-RSS details for
those four capped replays. The uncapped supervisor's exit/signal aggregate is
empty because it observed no native exit. The real-signal synthetic test
verified parent containment and worker restart after public `SIGABRT`, while
the protected uncapped run did not need a restart.

The aggregate harness reports one `crash_to_success_nondeterminism` and a
combined parent-survival failure because its optional diagnostic repeat phase
stopped at the first candidate that had crashed only under the capped
reference but succeeded again uncapped. That counter is not a current
same-resource first-crash/fresh-retry event. The controlling fact is stronger:
the complete uncapped first pass succeeded for all four prior crash identities.

## Giant output and provisional Arrow audit

The accepted maximum-length candidate returned `PARSED_NONEMPTY` under the
uncapped supervisor. The targeted evidence did not persist that candidate's
individual component count, so no value is inferred for it.

All 23 successful giant results were independently serialized and reopened one
candidate at a time using provisional nullable Arrow
`large_list<struct<label: large_string not null, value: large_string not
null> not null>` semantics. The audit found:

- maximum component count among the 23: 881,338;
- maximum output-value total among the 23: 25,187,643 code points;
- maximum one-row Parquet artifact: 7,932,166 bytes;
- serialization time: 3.202781 seconds;
- validation time: 47.987918 seconds;
- page checksum verification: pass; and
- dictionary materialization during construction: none.

This supports `LargeList`/`large_string` as a technically appropriate nested
representation, but the schema remains provisional because the scientific
contract did not freeze.

## Status and retry policy conclusion

The owner-approved proposal distinguished:

- `PARSED_NONEMPTY` → non-null component list of length at least one;
- `PARSED_EMPTY` → non-null exact empty list `[]`; and
- `PARSER_PROCESS_CRASH` → null component list after two identical exact
  fresh-process crashes.

The proposed retry path remains correctly fail-closed in code: one first
native crash causes one exact fresh-process retry; crash→success or a changed
failure aborts. No candidate timeout, size-based skip, SAFE truncation, or
substring parse exists in the revised supervisor.

However, this status vocabulary was not frozen. No current giant candidate
exercised the native-crash retry under the resource-sufficient configuration.
The minimum next scientific decision is whether Stage 7 should:

1. return to normal parse results plus fail-closed job abortion for any
   unexpected native crash, because DEVELOPMENT supplies no reproducible
   resource-sufficient crash example; or
2. retain the generic confirmed-crash row state as prospective resilience,
   with an explicit justification independent of the four now-resolved
   candidates.

Either choice also requires an explicit minimum resource/allocation policy for
giant candidates. The current session does not make that owner decision.

## Runtime and permissions

- Reference replay: 353.272384 seconds
- Diagnostic processing: 833.667551 seconds
- Total SLURM elapsed: 963 seconds
- Total CPU: 843.240 seconds
- User/system CPU: 731.644 / 111.596 seconds
- Requested resources: 4 CPUs, 180 GiB, 12 hours
- Scheduler allocation: one 80-CPU node because of the memory request
- Batch MaxRSS: 55,330,996 KiB
- Observed child MaxRSS min/mean/max:
  5,509,156 / 29,052,027.647059 / 56,327,384 KiB
- Attempt wall-time min/mean/max:
  1.654280 / 10.602988 / 45.016211 seconds
- Parser initialization min/mean/max:
  4.661751 / 4.667448 / 4.677178 seconds
- Submitted/started/ended: 2026-08-28 12:24:07 / 12:24:08 /
  12:40:11 cluster local time
- Protected directory/file/log modes: `0700` / `0600` / `0600`
- stderr: empty

The observed child maximum exceeding 48 GiB is consistent with the reference
ceiling being insufficient. This is diagnostic evidence on one Goethe node,
not yet a generally frozen minimum-memory guarantee.

## Work correctly not performed

The gate stopped before contract/profile freeze. Therefore there is no Stage 7
materializer, authoritative 51,779-row publication, full row reconciliation,
fixed-500 machine verification, risk-stratified qualitative review, Stage 7
schema/logical/input-binding/manifest fingerprint, or production throughput
projection. No second diagnostic or authoritative job was submitted.

Before job submission, 43 focused Stage 7 tests, 218 Stage 2–7 regressions,
and 485 full local-safe tests passed; four production-transfer tests were
deselected. Ruff, strict mypy over 72 source files, changed-file formatting,
shell syntax, JSON, Markdown links, privacy/tracked-data checks, and
`git diff --check` passed.

The first local test invocation in this revision used system Python and failed
during collection because the project package and PyArrow were unavailable.
A second invocation used the repository virtual environment but initially
resolved the editable package from `main`. No tests ran in either attempt. The
corrected command bound this worktree's `src`; all reported gates then passed.

## Scope stop

- HOLDOUT accessed: **NO**
- Production Stage 2 started: **NO**
- Production Stage 3 started: **NO**
- Production Stage 4 started: **NO**
- Production Stage 5 started: **NO**
- Production Stage 6 started: **NO**
- Production Stage 7 started: **NO**
- Stage 8 started: **NO**
- Geocoding performed: **NO**
- Independent review started: **NO**

This session returns only
`STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY`. It does not declare
`STAGE_7_ACCEPTED`.
