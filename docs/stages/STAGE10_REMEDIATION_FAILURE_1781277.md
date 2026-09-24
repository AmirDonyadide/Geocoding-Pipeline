# Stage 10 remediated DEVELOPMENT failure — job 1781277

**STAGE10_REMEDIATED_DEVELOPMENT_RUN_FAILED.** On owner continuation,
2026-09-24, one terminal accounting reconciliation found **FAILED / 1:0** after
**09:51:40**. Generation completed, but no registration or `_COMMITTED` seal
exists. This is a **PUBLICATION-phase failure with an unresolved underlying
exception**, plus missing durable failure diagnostics. No retry, repair,
protected validation job or acceptance is performed by this reconciliation.

The [submission receipt](../scientific_assets/stage10_remediation_submission_1781277.json)
and [failure reconciliation](../scientific_assets/stage10_remediation_failure_1781277.json)
bind the exact executable **`1b4c076c85ecb48c0a4e28668b69b99e0be128ad`**, accepted
inputs, frozen science and pinned runtime. The latter is a post-termination
report, not an in-job terminal receipt. All input/science/runtime bindings in
the uncommitted manifest match the prior candidate manifest. The executable and
detached checkout remain unchanged.

## Accounting and failure boundary

| Item | Observed evidence |
|---|---|
| Job / batch | 1781277 / FAILED / 1:0 |
| Elapsed | 35,500 s / 09:51:40 |
| Requested | 4 CPUs, 32 GiB, 36 h; general1 / footprint / normal |
| Allocated | 80 CPUs under the established exclusive-node allocation; application remains configured for 4 threads |
| Scheduler batch MaxRSS | 10,921,836 KiB, approximately 10.416 GiB |
| Application prepublication peak | 11,139,076 KiB, approximately 10.623 GiB; a separate measurement scope |
| Submission UTC | 2026-09-24T09:23:38Z |
| Scheduler start / end | 2026-09-24T11:31:18 / 2026-09-24T21:22:58; accounting strings do not embed an offset |
| Last durable phase event | `validation_start`, `progress-001105.json` |
| stderr | `STAGE10_OPERATIONAL_FAILURE_ATTEMPT_PRESERVED` only |

The target contains the generated relation files, summary and manifest, plus
`_IN_PROGRESS`. `_SUCCESS.json` and `_COMMITTED` are absent. The same-allocation
remediation audit never produced its report. Completion of the three required
scientific publication/reopen replays is **not established**.

The static [publication sequence](../../src/safe_geocoding_pipeline/preprocessing/stages/s10_query_publication.py)
writes the manifest before fsync, initial validation and durable registration.
The evidence bounds failure to the interval after manifest creation and before
durable registration; it does not identify which operation failed or establish
whether the initial validation returned successfully. No timeout, memory,
ICU, scientific-content or filesystem root cause is proven.

The [execution handler](../../src/safe_geocoding_pipeline/preprocessing/stages/s10_query_execution.py)
normally writes `failure.json` and a `terminal_failure` event. Neither exists.
The [CLI](../../src/safe_geocoding_pipeline/preprocessing/stage10_cli.py) emits
only a static operational code for an unhandled exception. The actual exception
and why the failure receipt is absent cannot be recovered from these receipts.
Do not expose raw engine exceptions or protected values to fill this gap.

## Completed generation, not a validated candidate

The [generation-complete receipt](../scientific_assets/stage10_remediation_generation_complete_1781277.json)
records **69,747 / 69,747 contexts**, **418,482 decisions**, **142,677 hypotheses**
and **1,099 completed unit checkpoints**, with zero reused units. The
[uncommitted summary](../scientific_assets/stage10_remediation_uncommitted_summary_1781277.json)
declares 35,000 source rows, 34,822 STANDARD and 34,925 NATIVE contexts.

| Family | Emitted | Converged |
|---|---:|---:|
| Q1 | 33,977 | 0 |
| Q2 | 34,102 | 0 |
| Q3 | 38,644 | 29,435 |
| Q4 | 33,556 | 0 |
| Q5 | 50 | 0 |
| Q6 | 2,348 | 0 |

These generation aggregates match the prior candidate. Q7 hypotheses/decisions
are zero; the summary reports zero engineering violations. Q4 postcode counts
remain 6,751 included and 17,529 excluded by authorized contradiction. These
are generation evidence, not substitutes for the incomplete full validation.

**C01 was exercised during generation:** the summary now records **237,263**
`PARSER_ONLY_FIELD_EXCLUDED` field decisions: postalcode 61,328; locality 39,777;
region 68,079; country 68,079. None has an INCLUDE status. These counts describe
the frozen field-slot policy provenance, not counts of parser tokens or contexts
carrying parser geography. The independent country/parser/source-anchoring
reconciliation was not run; missing/duplicate provenance violations cannot yet
be reported as zero.

The [uncommitted manifest](../scientific_assets/stage10_remediation_uncommitted_manifest_1781277.json)
declares the following logical fingerprints:

| Domain | Fingerprint / comparison |
|---|---|
| `query_hypothesis` | `c61ba899dbe4f714e2879995261b7d3a943e3b830ca69b4656e2d286230982e1`; matches prior manifest |
| New `query_family_decision` | `2c915039f6b8653fbfbd2acd3629cb7d1efd86190e3cb636c69542750c695420` |
| Prior `query_family_decision` | `227de0a64624eef84e7bf45664099ea6d7b5e52e53f16fc3ad361fa6e652c0a2` |
| New declared dataset | `4c4e4e6a63f565f6b3ce97f54c74fcd817cbd79922189fdc07ad3e3d76205c1a` |
| Uncommitted manifest SHA-256 | `56496ce7e5b23d8ce35141204173cea1fe9ac3a98f0c03b4dcb6e222a99baf74` |

Hypothesis equality is **manifest-declared fingerprint equality only**. The
independent protected old/new relation comparison did not run. The changed
decision fingerprint is consistent with the intended provenance repair but
does not establish full C01 conformance by itself.

**C02 is partly exercised:** the manifest kind is the corrected
`STAGE10_DEVELOPMENT_QUERY_PLAN`. No registration was durably created, so its
required `stage10_input_binding_sha256` key, portable registration hash, exclusive
seal and committed reopen cannot be declared validated. P11 remains incomplete
for this attempted candidate.

## Timing, checkpoint and WAL evidence

Timings are inclusive scoped measurements; nested phases must not be added as
independent durations. The receipts do not establish a final validation elapsed.

| Scope | Measured seconds |
|---|---:|
| Accepted input validation | 3,260.760 |
| Workspace preparation | 1,018.224 |
| Parser certificate preparation, within setup | 562.259 |
| Reference material preparation, within setup | 318.875 |
| Context/index preparation, within setup | 8.616 |
| Workspace clock start through generation completion, including setup | 21,463.991 |
| Generation complete to validation-start event | 126.191 |
| Publication copy, integer manifest provenance | 190 |
| Certificate generation, 69,747 calls | 17,352.213 |
| SQL at generation complete, 164,167 executions | 941.686 |
| SQL at validation-start event, 232,212 executions | 1,012.744 |
| Q5 alignment, 68,079 calls | 1.877 |
| ICU transform, 2,349 calls | 0.278 |
| Output writes | 73.999 |
| Output close/checkpoint | 668.545 |
| Prefix coalescing, 16 calls | 855.284 |

The [validation-start receipt](../scientific_assets/stage10_remediation_validation_start_1781277.json)
retains the exact SQL category and phase counters. No new performance experiment
or claim about the earlier historical slowdown is made.

Filesystem metadata records **1,115 checkpoint manifests and 1,115 validation
seals**, covering 1,099 units plus 16 prefixes. All are preserved, with the
3,776,720,896-byte database. Sampled WAL high-water was **29,679,390 bytes
(28.304 MiB)**; no WAL was present after close. Sampling is not a continuous
maximum. These are retained generation-validated units; fresh adoption/hash
validation has not been performed. Any future adoption requires exact immutable
bindings, inventory/hash verification and owner authorization. An uncommitted
reserved publication directory is not itself an adoptable published candidate.

## Preserved evidence and complete bounded ledger

Publication key: `stage10_development_20260924T092129Z_1b4c076c85ec`.

Reserved target:
`/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage10/development/stage10_development_20260924T092129Z_1b4c076c85ec`.

Work root:
`/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage10/development/work/stage10_development_20260924T092129Z_1b4c076c85ec_rlu4u7c1`.

The reservation, all 32 final relation files, uncommitted manifest/summary,
checkpoints, database, attempt/progress receipts, logs and submission receipts
remain private and unchanged. Observed directories are 0700 and files 0600.
Only sanitized aggregate/manifest metadata was retrieved; no protected relation
or database payload was processed during this reconciliation. The
[report inventory](../scientific_assets/stage10_remediation_failure_inventory_1781277.json)
binds the portable evidence. This record does not manufacture a missing in-job
failure receipt.

| Item | Classification | Disposition |
|---|---|---|
| C01 | CANDIDATE_IMPLEMENTATION | Repair generated; 237,263 visible exclusions in the summary. Full independent provenance reconciliation pending, not declared resolved at candidate level. |
| C02 | CANDIDATE_PUBLICATION | Correct manifest kind present. Registration contract/hash/seal/reopen not completed; candidate-level validation pending. |
| F01 | PUBLICATION | OPEN: failure after manifest creation and before durable registration. Underlying exception unresolved; no scientific drift or resource cause established. |
| F02 | IMPLEMENTATION / OBSERVABILITY | OPEN: missing failure receipt/terminal event; static CLI diagnostic does not retain the cause. Precise failing operation and receipt-loss mechanism unresolved. |
| F03 | REPORTING_ONLY | RESOLVED: current progress updated to FAILED with a separate dated report; historical submission, prior candidate and review evidence retained. |

No new evidence reopens independent-review I01–I08 or review-harness R01–R05.
The prior candidate manifest still hashes to
`085b05f6201831de6aa908c599bb5541a85cc185a48022d2d93d1e0a9afcc3fa`; review branch
remains `bced5920b5234e5598f1d0b3a4cb1269780862f4`. No executable, scientific
contract, runtime, accepted Stage 0–9 asset or historical artifact is changed.

Reporting verification covers evidence hashes, aggregate reconciliation,
document links/anchors, frozen implementation/design/schema/runtime inventory,
stage-report checks and diff/privacy scope. It does not rerun scientific output
or complete the missing protected audit/replays.

**NEXT: OWNER REVIEW OF REMEDIATED STAGE 10 DEVELOPMENT FAILURE.** No automatic
retry or diagnostic job. Operating budget **UNSELECTED**; Stage 0–9 unchanged;
HOLDOUT sealed; production/Pelias untouched; Stage 11 NOT STARTED; Stage 10
**NOT YET ACCEPTED**.
