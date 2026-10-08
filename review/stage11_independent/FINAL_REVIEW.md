# Stage 11 fresh independent review — PASS

**STAGE11_COMPLETE_SEMANTIC_REQUEST_DEDUPLICATION_INDEPENDENT_REVIEW_PASS**

Completed **2026-10-08**, after the owner continued this same independent-review
session. All areas A–X are complete. **Candidate defects = 0**, with no candidate
repair or regeneration required. Stage 11 is **NOT YET OWNER ACCEPTED**.

The [complete ledger](LEDGER.md), [combined evidence](REVIEW_EVIDENCE.json),
[unaltered successful job evidence](evidence_1790315.json), and preserved
[failed harness evidence](evidence_1789589.json) distinguish candidate results,
review-harness corrections and informational limits.

## Exact identities and frozen bindings

| Identity | Value |
|---|---|
| Frozen main / review branch point | `125b3684a000ea79523f77049ae1a290b0da8109` |
| Owner-reviewed design | `ac96b033e2ba7201fbb99ea38cd363d13410c7c4` |
| Design-freeze tag | `stage11-semantic-request-deduplication-design-v1`, peeling to frozen main |
| Candidate implementation | `8dce0e1078e123748ae692fa824200fc3e646aa4` |
| Candidate reporting | `d49e9340ef3ae9cb3caaec65d5ccf0c490ecf366` |
| Review branch | `review/stage11-independent-20261005` |
| Successful review executable | `c4f1fac1596e89adf825786dce7d238e5adef34f` |
| Complete review job | `1790315` — COMPLETED / 0:0 |
| Earlier incomplete review job | `1789589` — FAILED / 1:0, review-harness R06 |
| Successful evidence bytes | 11,973 |
| Successful evidence SHA-256 | `ac43d1af51d0395fdde469b5bfb26d0560868facc1b519d164d2461c5fd2b32e` |

The final review evidence Git SHA is the commit introducing this report, resolved
without a self-reference by `git log --diff-filter=A --format=%H --
review/stage11_independent/FINAL_REVIEW.md`. The final response records that full
SHA. It is distinct from the exact harness SHA used by the completed job.

Candidate publication: `stage11_development_20261004T095201Z_8dce0e1078e1`.
Artifact:
`/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage11/development/stage11_development_20261004T095201Z_8dce0e1078e1`.

| Binding | Independently verified value |
|---|---|
| Candidate manifest | `9dc8e3853cc474c331d08740981b11d0b8128a7b11fd36d9f978cb883414b6cc` |
| Accepted Stage 10 publication | `stage10_development_20260928T081247Z_cf9e0fe4c12e` |
| Stage 10 manifest | `558298d7260199cc24f994d7480def9ad268aca057347f86ca41fad675a5a860` |
| Stage 10 hypothesis fingerprint | `c61ba899dbe4f714e2879995261b7d3a943e3b830ca69b4656e2d286230982e1` |
| Complete Stage 11 input binding | `083830b8a8e696668f5956afc6405074dbec84e5bdb150994c2acb67d2897edf` |
| Contract | `stage11_semantic_request_contract_v1` / `e049305cfc100a7a84de01d395b4eceae5195e0730f50c91923cd5970c05885c` |
| Profile | `stage11_semantic_request_profile_v1` / `e25952c294ce486eff4969eef0ff709d10de89b6cdaf7072140a272e49a940a4` |
| Schema bundle | `stage11_semantic_request_schema_v1` / `a5c918291cd29e1824dd54e6b4d43bd7090e2492a06be408592a1a36f2f4b528` |

**Frozen binding result: PASS.** The four normative design documents are
byte-identical to the owner-reviewed freeze. The executable descends from that
freeze; reporting changes do not alter candidate code. The review branch starts
at frozen main and changes only `review/stage11_independent/`. No candidate
implementation is integrated into main by this review.

## Full-population science

**142,677 accepted hypotheses → 105,805 unique semantic requests and 142,677
map rows.** Map hypothesis IDs are unique and exactly equal the accepted input
set. Reduction is **36,872 / 142,677 = 25.842988%** rounded to six decimals.
Requests with more than one hypothesis: **36,822**; maximum multiplicity: **8**.

| Hypotheses/request | Requests | Hypotheses |
|---|---:|---:|
| 1 | 68,983 | 68,983 |
| 2 | 36,803 | 73,606 |
| 3–5 | 14 | 56 |
| 6–10 | 5 | 32 |
| 11–50 | 0 | 0 |
| 51–100 | 0 | 0 |
| >100 | 0 | 0 |
| Total | 105,805 | 142,677 |

Missing, multiple and extra mappings; duplicate/missing input IDs; orphan
requests/FKs; ID/payload collisions; recomputation, projection and lineage
mismatches; invalid intents, boundaries, policies or encodings; and multiplicity
sum errors are **all zero**. Contract failures **0**. No sampling or family budget.

| Review property | Result |
|---|---|
| Canonical serializer | PASS: independent named/order/type/domain framing, strict UTF-8, uint64 big-endian lengths and null vectors; no delimiter, repr, locale, path or platform dependence |
| `query_semantic_id` | PASS: independently recomputed full SHA-256 for every core and every upstream projection; no truncation or mismatches |
| Global deduplication | PASS: every mapped hypothesis has exactly the complete canonical bytes of its unique published request; full ID/byte equality and totality, no fuzzy or normalized collapse |
| Exact string preservation | PASS: complete upstream projection equality; no new trimming, casefolding, Unicode/punctuation normalization, transliteration, expansion or correction |
| Endpoint/mode | PASS: FULL_TEXT `/v1/search` **81,773 requests / 109,121 hypotheses**; STRUCTURED `/v1/search/structured` **24,032 / 33,556**; illegal combinations reject |
| Country | PASS: **105,805 / 142,677 bound**, **0 / 0 unbounded**; exact boundary participates in identity, separately from the null structured country; no Q7 or fallback |
| Policies | PASS: every request uses `NO_REQUEST_LANGUAGE_OVERRIDE`, `OMITTED_API_SELECTION` layers, `OMITTED_API_SELECTION` sources, `NONE` spatial, `REJECT_UNLISTED` additional parameters |
| Stage 11/12 separation | PASS: no size/top-N, retrieval depth/policy, transport serialization, hostname, deployment/index, auth/header bag, job or filesystem identity in the core |
| Null/absence/empty/default | PASS: all fields required, mode-specific nulls explicit; invalid states reject without repair or default equivalence |

The independently rebuilt complete summary is byte-identical to the published
canonical summary: SHA-256
`fc948834533daec7fa117f2acbdd636e18d542ed57c6f62926c104100d21e6c5`.
Its uint64 maximum is preserved exactly in the evidence, without floating-point
conversion during export/reconciliation.

## Upstream lineage and interpretation

All **35,000 sources**, **69,747 contexts** (34,822 STANDARD / 34,925 NATIVE),
**418,482 family decisions**, **172,112 eligible family links**, and **1,668
zero-hypothesis contexts** reconcile. Family joins use both hypothesis and
context, with exact accepted source/role/candidate FKs. No upstream lineage
relation is duplicated in Stage 11.

| Convergence metric | Requests |
|---|---:|
| Cross-context | 36,822 |
| Cross-source | 33 |
| Cross-family | 31,244 |
| STANDARD-only | 33,240 |
| NATIVE-only | 35,759 |
| Both representations | 36,806 |
| Same-source STANDARD/NATIVE convergence | 36,806 |

Family-cardinality counts 1–6: **74,561 / 23,145 / 8,099 / 0 / 0 / 0**.
**Interpretation PASS:** these are workload/representation convergence
diagnostics, not accuracy, validity, confidence, precision, recall or independent
scientific corroboration. Stage 11 is not an executable HTTP workload.

## Logical fingerprints

| Relation/dataset | Independent SHA-256 |
|---|---|
| `semantic_request` | `01b1c6f243e12c407d9df86b77d3068be46a11f3511e4d77170db39f73e83f5e` |
| `hypothesis_request_map` | `ea23792566398856cba1372c914cec5c70e00412c80dac7f5fec259d663dfcc3` |
| Complete Stage 11 logical dataset | `e110ff3eb2ad01ac6bf298c48f6c489b3b79bc067f28b41deab8d1bc1e46f337` |

Independent logical hashing sorts full unsigned primary keys and uses frozen
typed framing. Synthetic physical row order, shard boundaries, compression,
paths, partition/unit settings, threads and interrupted/resumed execution leave
logical fingerprints unchanged.

## Checkpoints, publication, failure safety and privacy

**Checkpoint/resume PASS:** all **18 input + 256 reduction = 274 sealed units**;
incomplete units **0**. Exact executable/input/design/runtime/assets/encoding
bindings, physical inventories, independent payload/key digests, ranges,
contributors, prefixes and complete checkpoint-to-final equality pass. All
142,677 intermediate inputs independently match their upstream projection and
all 105,805 reduced requests match the final relation. Synthetic interrupted
input/reduction and local-loss resume evidence supplements the clean candidate.

**Publication PASS:** exclusive reservation → durable immutable artifact →
manifest/inventory → Stage 11 registration → exclusive `_COMMITTED` → full
reopen. Fifteen durable phases reconcile with no premature seal. Registration
kind is exactly `STAGE11_DEVELOPMENT_SEMANTIC_REQUEST_CATALOG`, record version
`stage11_publication_record_v1`, input key `stage11_input_binding_sha256`.
The reused portable domain is `SAFE:publication-commit:v2`; active Stage 11
bindings contain no Stage 10 registration names.

Registration SHA-256:
`830e7632c4079cde548e4a3c7886749d39332fbb54c748bc0f54cd0bd5069964`.
Commit-record ID:
`62e042caa91e6229bcf422b2c04f5fa78d99356be9cee390d40ce81d0f02d01e`.
Independent inventory SHA-256:
`d54f550eca1b061a756ec2694a623a0738d0fc02892af078c6d56f3154ac2042`.

**Local-storage independence PASS:** job 1788751 had ended. Independent review
and supplemental candidate full reopen succeeded with all Python `/local` opens
prohibited and both connections spill-disabled. Every registered native-library
input path is durable controlled PanFS. No former local existence probe occurred.
The sampled implementation high-water measurement remains informational.

**Failure-safety PASS:** source review and independent synthetic faults verify
first-error preservation/durable sanitized receipt, guarded secondary errors,
and rejection before seal for collisions, invalid contracts, manifests and
registrations. Post-seal uncertainty requires exact reconciliation. The actual
candidate contains no failure receipt or premature seal. The protected artifact
was never deliberately interrupted, corrupted or raced.

**Privacy PASS:** shared execution guard precedes protected input access;
directories/files are 0700/0600. All **261 artifact files** and **842 attempt
files** are unchanged across review. Candidate stdout equals its sanitized
completion receipt; stderr is empty. Review evidence is 0600 and its transported
bytes match the durable SHA-256 exactly. Review stdout is a closed 85-byte status
record and stderr is empty. No protected strings, individual IDs, examples or
query payloads were exported, committed or sent to external services/LLMs.
HOLDOUT, production and Pelias were not accessed.

## Test, architecture and resource evidence

**495 independent synthetic tests pass**, no failures/skips. Candidate safe
regression reproduces **1,343 passes**, including **158 Stage 11 tests**, with
**24 pre-existing optional ICU skips**. Three public-only tests absent from the
detached worktree were run separately against already-local public assets.
The ICU test files are unchanged from accepted main and unrelated to Stage 11.
Implementation self-tests are supplemental to the independent full-population
oracle and static contract review.

**Scale/architecture PASS:** bounded readers/writers, full-ID external sort/group
and hash joins, streamed memberships, deterministic partitions and exact-bound
resume; no pandas production path or quadratic pairwise matching. Insufficient
resources fail closed. The fixed-memory reopen is not a production-capacity claim.

Review job 1790315 requested **2 CPUs / 8 GiB / 1 hour**, no local storage or
requeue. Scheduler elapsed **296 seconds**, application **289 seconds**;
batch MaxRSS **1,203,372 KiB**. The accounting job row reports ReqCPUS=2 and
batch step ReqCPUS=80; preserve the different scopes without inferring CPU use.
Review resource observations are informational and do not predict production.

## Complete ledger and stop

All candidate classes contain **0 defects**: scientific, implementation,
data integrity, publication and privacy. All six harness findings R01–R06 are
resolved. R06's original scratch-directory failure remains preserved, with its
underlying OS cause unknown; removal of that review-only dependency is verified
by the complete successful follow-up. No candidate repair was made.

Informational I01–I08 remain in the [ledger](LEDGER.md): non-executable catalog
and future execution identity; inherited upstream lineage; resource limits;
optional ICU skips; synthetic-only destructive fault tests; Python audit-hook
scope versus native libraries; HOLDOUT non-access evidence; historical R06
cause uncertainty. None requires candidate regeneration.

Operating budget **UNSELECTED**. Stage 0–10 unchanged. Stage 11 design frozen.
Stage 11 **NOT YET OWNER ACCEPTED**. HOLDOUT sealed; production/Pelias untouched;
Stage 12 **NOT STARTED**. No main integration or acceptance tag is created.

**NEXT: OWNER ACCEPTANCE OF STAGE 11**
