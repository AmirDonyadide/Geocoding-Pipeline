# Stage 11 semantic request deduplication DEVELOPMENT candidate

## Status and authority

**STAGE11_COMPLETE_SEMANTIC_REQUEST_DEDUPLICATION_DEVELOPMENT_CANDIDATE_READY**.
Candidate evidence reconciled on **2026-10-05**. Stage 11 is **NOT YET OWNER
ACCEPTED**. The next step is **FRESH INDEPENDENT REVIEW OF STAGE 11 DEVELOPMENT
CANDIDATE**; this implementation self-review is not that independent review.

The owner authorized the frozen design's implementation, synthetic validation
and exactly one complete DEVELOPMENT run (D088). The latest continuation named
job **1788751**, prohibited submission/cancellation/requeue/retry, and authorized
validation if it completed successfully. One accounting observation returned
**COMPLETED / 0:0**. No new job or protected processing occurred during this
reconciliation. The required full-population passes had completed within 1788751.

Scientific output is only `semantic_request(query_semantic_id, core)` and
`hypothesis_request_map(hypothesis_id, query_semantic_id)`, plus the frozen
sanitized summary/publication metadata. Checkpoints are protected operational
evidence. There is no extra scientific lineage relation.

## Exact provenance and bindings

| Binding | Value |
|---|---|
| Implementation/executable | `8dce0e1078e123748ae692fa824200fc3e646aa4` |
| Branch | `impl/stage11-semantic-request-deduplication` |
| Main/origin main, unchanged; no implementation integration | `125b3684a000ea79523f77049ae1a290b0da8109` |
| Owner-reviewed design | `ac96b033e2ba7201fbb99ea38cd363d13410c7c4` |
| Design-freeze tag | `stage11-semantic-request-deduplication-design-v1`, peeling to frozen main |
| Stage 10 executable | `cf9e0fe4c12eb85f78051904c636ad084d87a541` |
| Stage 10 publication | `stage10_development_20260928T081247Z_cf9e0fe4c12e` |
| Stage 10 manifest SHA-256 | `558298d7260199cc24f994d7480def9ad268aca057347f86ca41fad675a5a860` |
| Stage 10 query-hypothesis fingerprint | `c61ba899dbe4f714e2879995261b7d3a943e3b830ca69b4656e2d286230982e1` |
| Stage 10 upstream input binding | `531d512f6c177fb5a9d6cd262e66846cdfd5cc66ba818c5aba8030165648878e` |
| Complete Stage 11 input binding | `083830b8a8e696668f5956afc6405074dbec84e5bdb150994c2acb67d2897edf` |
| `stage11_semantic_request_contract_v1` | `e049305cfc100a7a84de01d395b4eceae5195e0730f50c91923cd5970c05885c` |
| `stage11_semantic_request_profile_v1` | `e25952c294ce486eff4969eef0ff709d10de89b6cdaf7072140a272e49a940a4` |
| `stage11_semantic_request_schema_v1` bundle | `a5c918291cd29e1824dd54e6b4d43bd7090e2492a06be408592a1a36f2f4b528` |
| Encoding | `stage11_semantic_request_encoding_v1` |
| Runtime | Python 3.14.3; PyArrow 25.0.0; DuckDB 1.5.5 |

The reporting SHA is the commit introducing this report and its four sanitized
evidence assets, resolved without a self-referential hash by
`git log --diff-filter=A --format=%H -- reports/development/stage11.md`.
The continuation's final response records that exact commit. Reporting changes
do not alter the executable, frozen assets or immutable candidate.

Accepted Stage 10 input resides at
`/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage10/development/stage10_development_20260928T081247Z_cf9e0fe4c12e`.
Its manifest includes the accepted Stage 10 context → Stage 8 occurrence →
source-row authority. All 142,677 hypothesis foreign keys remain reachable;
Stage 11 neither duplicates nor replaces this upstream lineage.

## Publication and fingerprints

Publication key: **`stage11_development_20261004T095201Z_8dce0e1078e1`**.

Immutable artifact:
`/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage11/development/stage11_development_20261004T095201Z_8dce0e1078e1`.

| Object | SHA-256 |
|---|---|
| Manifest | `9dc8e3853cc474c331d08740981b11d0b8128a7b11fd36d9f978cb883414b6cc` |
| `semantic_request` logical fingerprint | `01b1c6f243e12c407d9df86b77d3068be46a11f3511e4d77170db39f73e83f5e` |
| `hypothesis_request_map` logical fingerprint | `ea23792566398856cba1372c914cec5c70e00412c80dac7f5fec259d663dfcc3` |
| Complete logical dataset | `e110ff3eb2ad01ac6bf298c48f6c489b3b79bc067f28b41deab8d1bc1e46f337` |
| Sanitized summary | `fc948834533daec7fa117f2acbdd636e18d542ed57c6f62926c104100d21e6c5` |
| Physical inventory | `d54f550eca1b061a756ec2694a623a0738d0fc02892af078c6d56f3154ac2042` |
| Registration `_SUCCESS.json` | `830e7632c4079cde548e4a3c7886749d39332fbb54c748bc0f54cd0bd5069964` |
| Publication commit-record ID | `62e042caa91e6229bcf422b2c04f5fa78d99356be9cee390d40ce81d0f02d01e` |

Exact sanitized copies: [manifest](../../docs/scientific_assets/stage11_development_manifest_1788751.json),
[summary](../../docs/scientific_assets/stage11_development_summary_1788751.json),
[registration](../../docs/scientific_assets/stage11_development_registration_1788751.json).
The [reconciliation evidence](../../docs/scientific_assets/stage11_development_evidence_1788751.json)
retains completed/preflight receipts, all 15 phase records, scheduler observation,
62 portable metadata checks, coverage hashes and resource measurement scopes.

Registration kind is **`STAGE11_DEVELOPMENT_SEMANTIC_REQUEST_CATALOG`**,
record version **`stage11_publication_record_v1`**, input-binding key
**`stage11_input_binding_sha256`**. No Stage 10 registration name is reused.
Exclusive reservation, immutable artifact, manifest/inventory, initial validation,
registration, prepared validation, exclusive `_COMMITTED`, committed full reopen
and final ownership check all completed. The zero-byte seal is 0600; directories
are 0700 and files 0600. Current metadata reconciles all **261 artifact files**
and their byte sizes; unsafe topology entries are **0**. Physical payload hashes
were recomputed within the guarded job, not on the login node or Mac.

Logical relation hashes sort by full unsigned primary keys; the dataset digest
binds relation hashes, counts, input/assets and summary. File order, shard count
and compression are outside logical hashing. Physical manifest/inventory hashes
intentionally describe the particular immutable publication, so they need not
match a differently partitioned synthetic run.

## Complete DEVELOPMENT counts

| Metric | Count |
|---|---:|
| Input hypotheses | 142,677 |
| Unique semantic requests | 105,805 |
| Map rows | 142,677 |
| Exact reduction | 36,872 |
| Requests with more than one hypothesis | 36,822 |
| Maximum multiplicity | 8 |

Reduction is exactly **36,872 / 142,677**, or **25.842988007877935%** in decimal
presentation. Unique fraction is **105,805 / 142,677**; mean multiplicity is
exactly **142,677 / 105,805**. No unique-request count was assumed before the run.

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

All **35,000 source rows**, **69,747 contexts** (34,822 STANDARD + 34,925 NATIVE),
**418,482 family decisions**, **172,112 eligible family links** and **1,668
zero-hypothesis contexts** reconcile to the accepted upstream population.
Zero-hypothesis contexts remain upstream and are not dropped Stage 11 inputs.

| Convergence diagnostic, denominator 105,805 requests | Requests |
|---|---:|
| More than one context | 36,822 |
| More than one source row | 33 |
| More than one eligible query family | 31,244 |
| STANDARD only | 33,240 |
| NATIVE only | 35,759 |
| Both representations | 36,806 |
| At least one same-source STANDARD/NATIVE pair | 36,806 |

Family-union cardinalities **1 / 2 / 3 / 4 / 5 / 6** contain
**74,561 / 23,145 / 8,099 / 0 / 0 / 0** requests. Families are joined through
both hypothesis and context. Existing convergent Stage 10 memberships can give
one hypothesis multiple families; these links do not multiply map rows.
All multi-hypothesis requests also span contexts in this candidate. Cross-source
convergence is reported separately from the much larger representation/context
convergence. These are exact workload diagnostics, never accuracy, validity,
confidence, independent corroboration or observed HTTP-call savings.

| Mode / structured presence | Requests | Hypotheses |
|---|---:|---:|
| FULL_TEXT, `/v1/search` | 81,773 | 109,121 |
| STRUCTURED, `/v1/search/structured`, total | 24,032 | 33,556 |
| Structured address + locality | 19,520 | 26,805 |
| Structured address + postalcode | 3,557 | 5,254 |
| Structured address + postalcode + locality | 955 | 1,497 |

Structured region and address-country are explicit nulls. Country-bound counts
are **105,805 requests / 142,677 hypotheses**; unbounded counts **0 / 0**.
The frozen report requires these boundary categories, not country identities
or sparse country cross-tabs. Every request/hypothesis uses the single policy
combination **NO_REQUEST_LANGUAGE_OVERRIDE / OMITTED_API_SELECTION layers /
OMITTED_API_SELECTION sources / NONE spatial / REJECT_UNLISTED additional
parameters**. Boundary country remains a separate semantic identity field.

Missing mappings, multiple mappings, extra mappings, orphan requests, orphan
foreign keys, ID/payload collisions, ID recomputation mismatches, invalid intents,
boundaries, policies or encodings, duplicate/missing input IDs, projection and
lineage mismatches, and multiplicity-sum discrepancies are **all zero**.
Contract failures **0**; job technical failures **0**.

## Checkpoint, replay and validation evidence

All **18 input units + 256 reduction units = 274 checkpoints** were copied,
hashed, schema/row/ID validated and sealed in the guarded job. Input units cover
all **142,677** hypotheses; final relations reconcile to the complete contributor
coverage. Binding includes exact executable, runtime, accepted input, design,
contract/profile/schema, encoding, key order, 8,192-row input unit size and one
digest-byte reduction partition. No incomplete checkpoint was adopted.

Input coverage SHA-256:
`5195ddb5a91d0f2d40c823dc84e6220885f1682e320b3b7ebee4ae1afb47fea9`.
Reduction coverage SHA-256:
`8c65a930e1bd2419bfb7cd8c8446804f84970703cdb824199e5fa3ffebf9e7b9`.
The continuation verified every descriptor/seal hash: **274 matches**, incomplete
units **0**, mismatches **0**; both coverage hashes still match the manifest.
Row-level descriptors/coverage were not exported. DEVELOPMENT adopted **0** units;
it was a clean run. Resume conformance is synthetic evidence, not a claim that
the DEVELOPMENT job restarted.

The frozen [evaluation plan](../../docs/stages/STAGE11_DEVELOPMENT_EVALUATION.md)
requires generation, independent durable pre-seal verification and full committed
reopen within the one run. The implementation performs initial and prepared
pre-seal reopen checks plus committed reopen. Each checks all inputs, re-encodes
every core, recomputes every ID/relation fingerprint, reconstructs F(h) for every
edge, checks all lineage joins and recomputes the entire summary/dataset.
Recorded phase intervals are **109.984027 s initial**, **110.470590 s prepared**,
and **110.665841 s committed reopen**, including phase bookkeeping.

Reopen creates an independent in-memory, 2 GB-capped connection with spilling
disabled and reads only authoritative PanFS. Generation `/local` state and
checkpoints are not inputs. Synthetic validation additionally deletes all local
state before reopening. No post-exit local access or extra replay job was needed.

The **158 Stage 11 synthetic tests** include an independent binary encoder and
fixed vectors; clean/reversed input, changed partition/unit/thread settings and
interrupted/resumed equality; full local loss; giant Unicode values and skew;
map/collision/checkpoint/publication fault injection; and privacy/error handling.
Both relation fingerprints and the complete logical dataset match across those
permitted variations. Pre-execution safe suite: **1,343 passed / 24 pre-existing
optional ICU-build skips / 0 failures**. Exact evidence and the complete I01–I26
implementation ledger remain in the [implementation record](../../docs/stages/STAGE11_IMPLEMENTATION.md).

Portable reconciliation independently recomputed manifest, summary, inventory,
registration, commit-record, input-binding and logical-dataset hashes from the
sanitized evidence, and reconciled aggregate arithmetic: **62 checks PASS**.
It does not claim a new row-level scan on the Mac or login node. Protected
relation fingerprints and all aggregates were independently recomputed in the
job's full durable reopen passes described above.

Final reporting-tree validation: the complete safe suite again passed **1,343
tests / 24 pre-existing optional ICU-build skips / 0 failures** in **45.67 s**,
including all 158 Stage 11 tests. Strict mypy (134 source modules), Ruff lint and
format (211 files), unchanged Stage 10 inventory, frozen Stage 11 assets/byte
vectors, report validator, local Markdown links, privacy/tracked-data review,
SBATCH syntax and `git diff --check` pass. No protected test fixture was fetched.

## Runtime, storage and measurement limits

| Measurement | Observed value |
|---|---|
| Submission UTC | 2026-10-04T09:52:01Z; submitted once |
| Job / node / exit | 1788751 / node18-006 / COMPLETED 0:0 |
| Scheduler elapsed | 00:10:52 (652 s) |
| Application elapsed, including validation/publication | 647.310877051 s |
| Request | 2 CPUs, 8 GiB RAM, 1 h, `--tmp=2048M`, no requeue |
| Scheduler batch MaxRSS | 1,956,968 KiB |
| Application `ru_maxrss` | 2,080,840 KiB |
| Local sampled high water / terminal file bytes | 145,468,476 / 145,468,476 bytes |
| Local samples / unavailable samples | 320 / 0; approximately 2-second sampling |
| Durable checkpoints | 145,690,922 bytes |
| Immutable artifact, all 261 files | 79,228,166 bytes |
| Durable artifact + checkpoints | 224,919,088 bytes, excluding attempt receipts/logs |
| Semantic request / map compressed bytes | 69,607,860 / 9,537,956 |
| PanFS project available before / after job | 11,394,203,328,512 / 11,393,878,986,752 bytes |
| PanFS filesystem available at preflight | 13,596,793,954,959,360 bytes |
| Job-local filesystem available at preflight | 1,806,270,275,584 bytes |
| Local and PanFS required free reserve | 2,147,483,648 bytes each |

The single accounting response reports `ReqTRES=billing=2,cpu=2,mem=8G,node=1`
and `AllocCPUS=80`. Preserve both: request/launcher/engine concurrency is 2;
80 is the reported allocation field, not a measured CPU-use claim. Scheduler
sampling and process high-water RSS are different measurements and are both
reported. Local sampling can miss short-lived peaks; terminal file bytes exclude
filesystem overhead. Local reclamation after job exit was not inspected.
Shared project-quota changes are not attributed exclusively to this job.

End-to-end input throughput is **142,677 / 647.310877051 hypotheses/s**;
generation/build including checkpointing and its validation took **275.102234 s**.
Encoded-input byte throughput and separate spill peak are **UNAVAILABLE**, not
estimated from compressed files or reserved capacity. No production capacity or
performance guarantee follows from this DEVELOPMENT run.

## Complete bounded candidate self-review

This completes the post-run challenge ledger in addition to the preserved
pre-execution I01–I26 ledger. No scientific/executable defect requiring repair,
redesign or regeneration was found. Reporting-only corrections are explicit.

| ID | Challenge | Disposition and evidence |
|---|---|---|
| C01 | Top-N/retrieval policy leaks into semantic ID | PASS: closed 19-field encoder; upstream slot validated then excluded; frozen vectors and rejection tests |
| C02 | Host/deployment/index/config/header leaks | PASS: no such core fields; fixed language policy; no retrieval client |
| C03 | Path/job/shard/thread/order affects ID | PASS: serializer uses only schema fields; varied synthetic runs preserve relation/dataset hashes |
| C04 | FULL_TEXT/STRUCTURED or endpoint aliasing | PASS: two disjoint validated endpoint/mode pairs; 81,773 / 24,032 cores |
| C05 | Boundary/address-country alias or fallback | PASS: separate fields; required upstream alpha-2 boundary; address-country null; unbounded 0 |
| C06 | Null/empty/default/type alias | PASS: fields mandatory, explicit null tag, strict types/UTF-8, empty/default rejection tests |
| C07 | Unknown result-affecting parameters accepted | PASS: exact upstream/core field sets and singleton policy enums |
| C08 | New whitespace/case/Unicode normalization | PASS: direct projection; exact full-byte F(h) comparison on every edge; independent Unicode vectors |
| C09 | Ambiguous framing or dictionary field order | PASS: named schema order, typed u64-BE frames, version/domain, independent encoder and strict inverse |
| C10 | Hash collision or truncated ID | PASS: full 32-byte SHA-256, full-byte comparison within groups, fatal collision injection, recomputation on reopen |
| C11 | Lost/duplicate/swapped map edges | PASS: 142,677 unique map keys, bidirectional input sets and every-edge reconstruction; zero missing/multiple |
| C12 | Orphan/dangling semantic requests | PASS: both FK directions and unique core keys; orphan counts 0 |
| C13 | Lost upstream provenance | PASS: exact hypothesis/context/source/representation/candidate identities and accepted transitive binding remain reachable |
| C14 | Cross-context family inflation | PASS: family join uses hypothesis AND context; 172,112 links remain separate from 142,677 edges |
| C15 | Convergence presented as confidence/accuracy | PASS: workload-only labels; no correctness inference or realized API-savings claim |
| C16 | Unbounded pairwise/group materialization | PASS: external sort/hash joins, streamed groups and byte-bounded writes; giant/skew synthetic evidence; no pandas path |
| C17 | Shard-dependent logical fingerprint | PASS: full key sorting and physical-independent logical framing; varied synthetic fingerprint equality |
| C18 | Partial or wrong-bound checkpoint adoption | PASS: executable/input/runtime/assets/plan exact; 274 valid seals, 0 incomplete, synthetic corruption/mismatch rejection |
| C19 | Checkpoint gaps/overlaps or final coverage loss | PASS: ordered input key coverage, reduction contributor binding, 142,677 covered inputs and full final projection |
| C20 | Resume silently changes science | PASS: clean/interrupted/local-loss/resumed synthetic equality; DEVELOPMENT adoption count 0 explicitly reported |
| C21 | Registration namespace reuse or reservation race | PASS: Stage 11-specific kind/version/input key; exclusive reservation and synthetic concurrent-writer test |
| C22 | Premature/false `_COMMITTED` | PASS: initial/prepared validation precede seal; committed reopen/final check completed; all 15 phase records reconcile |
| C23 | Reopen depends on vanished `/local` state | PASS: memory-capped spill-disabled reopen reads authoritative PanFS only; full local-loss synthetic test |
| C24 | Protected payload/log/API/HOLDOUT leakage | PASS: guard before protected reads; offline network restriction; stdout equals sanitized completed receipt, stderr empty; no new protected access |
| C25 | Failure reporting hides primary error | PASS: first-failure reserve and poison/secondary-error tests; no failure receipt in this successful job; job technical failures 0 |
| C26 | Reporting/history/resource overclaim | RESOLVED: add Stage 11 report to existing validator allowlist; correct one local metadata-harness column index before all 62 checks passed; preserve raw AllocCPUS/RSS and sampling limits; no executable/artifact change |

The local metadata-harness correction was not a DEVELOPMENT job failure.
Unresolved candidate/self-review defects **0**. No protected payloads, individual
request/hypothesis IDs, query examples or checkpoint membership records are in
the portable evidence. HOLDOUT's sealed status follows accepted authority and
non-access; its storage was not inspected. Production and Pelias were untouched.

## Review boundary

Operating budget **UNSELECTED**. Stage 0–10 scientific code, accepted reports,
artifacts and history unchanged. The four normative Stage 11 design documents
remain byte-identical to the owner-reviewed freeze. Stage 11 **NOT YET OWNER
ACCEPTED**; no acceptance tag or main merge. HOLDOUT sealed; production/Pelias
untouched; Stage 12 **NOT STARTED**.

**NEXT: FRESH INDEPENDENT REVIEW OF STAGE 11 DEVELOPMENT CANDIDATE.**
