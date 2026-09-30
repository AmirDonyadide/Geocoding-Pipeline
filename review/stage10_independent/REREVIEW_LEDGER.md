# Stage 10 final independent rereview ledger

Status: static/synthetic review complete; protected artifact rereview pending.
There is no final PASS/FAIL verdict. Historical `LEDGER.md`, its two candidate
defects, eight informational observations and resolved R01–R05 remain preserved.

## Candidate defect regression

| ID and class | Frozen invariant and evidence | Current disposition | Severity and regeneration |
|---|---|---|---|
| C01 — CANDIDATE_IMPLEMENTATION | Every omitted Q4 geographic field requires visible parser exclusion. Static correction adds that reason exactly once without changing query payloads; independent synthetic field/content fault tests pass. | Protected full expected/actual field attachment, payload safety and exact scientific equality pending. | Historical P2; original artifact required regeneration, now supplied as candidate 1785683. No further regeneration conclusion before full rereview. |
| C02 — CANDIDATE_PUBLICATION | Frozen namespace `STAGE10_DEVELOPMENT_QUERY_PLAN` and key `stage10_input_binding_sha256`. New code and portable registration/hash conform; old names rejected. | Actual durable registration, complete inventory and terminal reopen pending. | Historical P2; original artifact required conforming new publication, now supplied as candidate 1785683. |

No additional candidate defect has been established in code/synthetic review.
This statement is not an artifact verdict; all applicable A–T checks must finish.

## Review harness findings

R01–R05 remain resolved. The separate input-progress timer schema and historical
evidence are retained. The new marker/receipt scope adapter is specific to the
remediated candidate; the historical driver's defaults remain unchanged.

| ID | Evidence and affected review invariant | Resolution | Severity and regeneration |
|---|---|---|---|
| R06 — REVIEW_HARNESS | A new synthetic corruption test assumed an emitted Q4 payload in both eligible and ineligible fixture variants. The ineligible case correctly had no Q4 hypothesis, so the attempted payload mutation affected zero rows. | Apply payload corruption only to fixtures with emitted structured hypotheses; retain full C01 decision checks in both variants. Eligible fixture detects parser-payload and source-anchor corruption. All 36 harness tests pass. | Low; resolved before submission; no candidate regeneration or candidate change. |

## Informational ledger

| ID | Observation and evidence | Disposition and regeneration |
|---|---|---|
| I01–I08 | Previous structural abstention, allowed absent Q5/Q6 coexistence, Q5 precedence, three replay semantics, performance limits, exact-runtime local skips, bounded independent certificates and reporting/budget findings. | Retained as historical informational conclusions. Applicable current outputs rerun; no automatic reopening merely because the artifact is new. No regeneration based on these findings. |
| I09 | Historical F01 from job 1781277 remains without a demonstrated first exception/root cause. Current executable has primary-exception preservation, bounded durable failure recording and storage/project-quota checks, exercised synthetically. | Informational; historical uncertainty is preserved. Current successful receipts and publication still require protected verification. No speculative root cause or regeneration requirement. |
| I10 | Actual job-local storage peak was not persisted. Requested local capacity and durable state size do not establish the observed local peak. | Informational measurement limitation; no peak is inferred. Scientific equality and durable reopening are tested directly. No regeneration requirement solely for missing telemetry. |

Candidate artifacts, accepted inputs and candidate source remain unchanged.
HOLDOUT sealed; production/Pelias untouched; Stage 11 NOT STARTED;
Stage 10 NOT YET OWNER ACCEPTED.
