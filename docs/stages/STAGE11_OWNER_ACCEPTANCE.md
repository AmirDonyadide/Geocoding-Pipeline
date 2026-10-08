# Stage 11 owner acceptance and freeze

**STAGE11_COMPLETE_SEMANTIC_REQUEST_DEDUPLICATION_ACCEPTED** /
**STAGE_11_ACCEPTED**. The owner **accepts and freezes Stage 11 on DEVELOPMENT**
on **2026-10-08**, following the fresh independent review's complete PASS.
Candidate defects **0**; regeneration required **NO**.

This is a separate acceptance record. The dated [candidate report](../../reports/development/stage11.md),
[implementation record](STAGE11_IMPLEMENTATION.md), [independent final review](../../review/stage11_independent/FINAL_REVIEW.md),
[review ledger](../../review/stage11_independent/LEDGER.md) and their evidence
remain byte-identical to their accepted commits, including their historically
correct pre-acceptance wording. No scientific run, SLURM submission, protected
relation scan, candidate mutation or Stage 12 work occurred during acceptance.

## Preserved Git histories and acceptance tag

| Binding | Exact value |
|---|---|
| Frozen design main | `125b3684a000ea79523f77049ae1a290b0da8109` |
| Owner-reviewed design SHA | `ac96b033e2ba7201fbb99ea38cd363d13410c7c4` |
| Design-freeze tag | `stage11-semantic-request-deduplication-design-v1` |
| Unchanged annotated design-tag object | `437e3bca124ca463a10abccee59a213306926923` |
| Implementation SHA | `8dce0e1078e123748ae692fa824200fc3e646aa4` |
| Candidate reporting SHA | `d49e9340ef3ae9cb3caaec65d5ccf0c490ecf366` |
| Actual implementation/reporting branch | `impl/stage11-semantic-request-deduplication` |
| Non-squash implementation/reporting merge | `ea806670a558254ec6a944bee7c7d22908d5d372` |
| Independent review branch | `review/stage11-independent-20261005` |
| Final review evidence SHA | `4284f97bb29c8aa4319202d75fd9e96223584fcc` |
| Successful review executable | `c4f1fac1596e89adf825786dce7d238e5adef34f` |
| Non-squash independent-review merge | `d598b4cea80163e4df8b725a3d1facd5ea8b0417` |
| Annotated owner-acceptance tag | `stage11-semantic-request-deduplication-v1` |

Integration order was implementation/reporting merge, reachability verification,
review merge, then this owner-acceptance documentation. Both normal merges
completed without conflicts. No squash, cherry-pick, rebase, history rewrite,
branch deletion or worktree cleanup occurred. The final accepted main SHA is
the peeled target of `stage11-semantic-request-deduplication-v1^{}`. Its tag
annotation and the final acceptance response record that exact commit without
a self-referential hash in this document. The tag is created once after this
documentation commit; the older design tag remains unchanged at frozen main.

## Accepted candidate and scientific bindings

DEVELOPMENT job **1788751**, **COMPLETED / 0:0**. Publication key:
**`stage11_development_20261004T095201Z_8dce0e1078e1`**.

Artifact:
`/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage11/development/stage11_development_20261004T095201Z_8dce0e1078e1`.

| Binding | Accepted SHA-256 |
|---|---|
| Stage 11 manifest | `9dc8e3853cc474c331d08740981b11d0b8128a7b11fd36d9f978cb883414b6cc` |
| Stage 10 manifest | `558298d7260199cc24f994d7480def9ad268aca057347f86ca41fad675a5a860` |
| Stage 10 query-hypothesis fingerprint | `c61ba899dbe4f714e2879995261b7d3a943e3b830ca69b4656e2d286230982e1` |
| Stage 10 upstream input binding | `531d512f6c177fb5a9d6cd262e66846cdfd5cc66ba818c5aba8030165648878e` |
| Complete Stage 11 input binding | `083830b8a8e696668f5956afc6405074dbec84e5bdb150994c2acb67d2897edf` |
| `stage11_semantic_request_contract_v1` | `e049305cfc100a7a84de01d395b4eceae5195e0730f50c91923cd5970c05885c` |
| `stage11_semantic_request_profile_v1` | `e25952c294ce486eff4969eef0ff709d10de89b6cdaf7072140a272e49a940a4` |
| `stage11_semantic_request_schema_v1` bundle | `a5c918291cd29e1824dd54e6b4d43bd7090e2492a06be408592a1a36f2f4b528` |

The accepted input is Stage 10 publication
`stage10_development_20260928T081247Z_cf9e0fe4c12e`, executable
`cf9e0fe4c12eb85f78051904c636ad084d87a541`. The exact [candidate manifest](../scientific_assets/stage11_development_manifest_1788751.json)
retains its complete input inventory and transitive lineage binding.
The [contract](../scientific_assets/stage11_semantic_request_contract_v1.json),
[profile](../scientific_assets/stage11_semantic_request_profile_v1.json) and
[schema bundle](../scientific_assets/stage11_semantic_request_schema_v1.json)
are frozen without modification.

## Accepted scientific state

| Metric | Accepted count |
|---|---:|
| Stage 10 input hypotheses | 142,677 |
| Stage 11 unique semantic requests | 105,805 |
| `hypothesis_request_map` rows | 142,677 |
| Exact reduction | 36,872 |
| Requests with more than one hypothesis | 36,822 |
| Maximum multiplicity | 8 |

Reduction is exactly **36,872 / 142,677**, displayed as **25.842988%** rounded.
All accepted hypotheses participate; no sample, family budget or drop applies.

| Hypotheses/request | Requests | Hypotheses |
|---|---:|---:|
| 1 | 68,983 | 68,983 |
| 2 | 36,803 | 73,606 |
| 3–5 | 14 | 56 |
| 6–10 | 5 | 32 |
| >10 | 0 | 0 |
| Total | 105,805 | 142,677 |

| Mode / boundary category | Requests | Hypotheses |
|---|---:|---:|
| FULL_TEXT | 81,773 | 109,121 |
| STRUCTURED | 24,032 | 33,556 |
| Country-bound | 105,805 | 142,677 |
| Unbounded | 0 | 0 |

Every request uses **NO_REQUEST_LANGUAGE_OVERRIDE**, layers and sources
**OMITTED_API_SELECTION**, spatial **NONE**, additional parameters
**REJECT_UNLISTED**. FULL_TEXT and STRUCTURED remain disjoint; country boundary
remains semantic identity and is distinct from structured address-country.

Cross-context requests **36,822**; cross-source **33**; cross-family **31,244**.
STANDARD-only **33,240**; NATIVE-only **35,759**; both representations **36,806**;
same-source STANDARD/NATIVE convergence **36,806**. Family cardinalities 1–6:
**74,561 / 23,145 / 8,099 / 0 / 0 / 0**. These remain workload/representation
convergence diagnostics, never correctness, validation, accuracy or confidence.

Missing/multiple/extra mappings, orphan semantic requests, foreign-key violations,
ID/payload collisions, `query_semantic_id` mismatches, projection mismatches and
contract failures are **all 0**. The complete [sanitized summary](../scientific_assets/stage11_development_summary_1788751.json)
and independently rebuilt summary are identical.

| Logical relation/dataset | Accepted SHA-256 |
|---|---|
| `semantic_request` | `01b1c6f243e12c407d9df86b77d3068be46a11f3511e4d77170db39f73e83f5e` |
| `hypothesis_request_map` | `ea23792566398856cba1372c914cec5c70e00412c80dac7f5fec259d663dfcc3` |
| Complete Stage 11 logical dataset | `e110ff3eb2ad01ac6bf298c48f6c489b3b79bc067f28b41deab8d1bc1e46f337` |

## Accepted identity and Stage 11/12 boundary

`query_semantic_id` is the **full SHA-256 of the frozen domain-separated
canonical semantic bytes**: named, typed, schema ordered, versioned, strict
UTF-8 and unsigned 64-bit big-endian framed. Acceptance freezes exact complete-core
equality, global exact deduplication and lossless hypothesis map-back. No fuzzy
matching, near-duplicate collapse or new string normalization is permitted.

Stage 11 freezes only the **non-executable semantic query core**. Stage 12 owns
top-N/result limit, retrieval policy, transport serialization, hostname/deployment,
concrete Pelias configuration, immutable index/data identity, execution identity
and actual retrieval. Changing top-N must **not** change `query_semantic_id`.
This acceptance makes no change to that boundary, selects no top-N and grants
no geocoding execution authorization. Stage 10 operating budget is **UNSELECTED**.

## Accepted checkpoint, publication and privacy state

Checkpoints: **18 input units + 256 reduction units = 274 seals**, incomplete
units **0**. Exact bindings, checkpoint coverage, resume and deterministic
logical equality **PASS**. Upstream lineage remains inherited through Stage 10
foreign keys to context → Stage 8 occurrence → source row.

Registration kind **`STAGE11_DEVELOPMENT_SEMANTIC_REQUEST_CATALOG`**;
input-binding key **`stage11_input_binding_sha256`**;
record version **`stage11_publication_record_v1`**.
Exclusive reservation, immutable validated artifact, manifest/inventory,
Stage 11 registration, exclusive `_COMMITTED` and full reopen are **all PASS**.
Local-storage independence **PASS**. [Registration](../scientific_assets/stage11_development_registration_1788751.json)
SHA-256 is `830e7632c4079cde548e4a3c7886749d39332fbb54c748bc0f54cd0bd5069964`;
inventory SHA-256 is
`d54f550eca1b061a756ec2694a623a0738d0fc02892af078c6d56f3154ac2042`.

Privacy and failure safety **PASS**. No protected request payload export,
HOLDOUT or production access, Pelias/API access or external address service.
The acceptance precheck used only manifest/registration/summary hashes and
private file metadata: all **261 artifact files** matched the accepted inventory
names/sizes and 0600 file / 0700 directory permissions; the commit seal remained
empty and `_IN_PROGRESS` absent. Protected payload hashes/science were already
verified by the accepted full independent review and were not rerun here.

## Independent review and retained informational findings

Final review evidence **`4284f97bb29c8aa4319202d75fd9e96223584fcc`**;
successful review job **1790315**, **COMPLETED / 0:0**. All **124 protected
checks / 609,517 evaluations PASS**; **495 independent test passes**;
candidate suite **1,343 passes**, **24 pre-existing optional ICU skips**.
Candidate defects **0** in every review class; regeneration required **NO**.
The [combined review evidence](../../review/stage11_independent/REVIEW_EVIDENCE.json)
and [unchanged successful job evidence](../../review/stage11_independent/evidence_1790315.json)
remain authoritative. The latter hashes to
`ac43d1af51d0395fdde469b5bfb26d0560868facc1b519d164d2461c5fd2b32e`.

The complete informational ledger is retained without reopening it:

- Stage 11 intentionally publishes a non-executable catalog; later execution
  identity is separate.
- Upstream lineage remains inherited through accepted Stage 10 foreign keys.
- DEVELOPMENT resource measurements do not establish production capacity.
- The 24 optional ICU skips remain pre-existing, with relevant accepted runtime
  validation retained; Stage 11 performs no ICU transformation.
- Destructive failure tests use synthetic data; the protected candidate was
  never deliberately corrupted, interrupted or raced.
- Audit hooks are not an operating-system sandbox; their recorded scope remains.
- HOLDOUT sealing status relies on accepted authority and non-access evidence.
- Failed review-harness job **1789589** remains [preserved evidence](../../review/stage11_independent/evidence_1789589.json),
  **FAILED / 1:0**, not a candidate failure or a completed passing review.
- The underlying cause of that original review scratch failure remains
  **UNKNOWN**; the corrected harness's successful complete review is separate.
- Local-storage measurements are sampled, not guaranteed instantaneous peaks.

No item is reclassified as a candidate defect or a regeneration requirement.

## Acceptance validation and stop boundary

Lightweight acceptance checks verify both non-squash merge parentages and
reachability of frozen design, implementation, reporting and final review SHAs;
unchanged scientific files, accepted fingerprints, counts and publication
references; zero-defect review ledger; preserved historical report/evidence
bytes; privacy/tracked-data scope; documentation/index consistency; local links
and anchors; and `git diff --check`. No new scientific or review run is required.
All checks pass, including **227 local links / 21 anchors**, unchanged Stage 10
and Stage 11 implementation/asset validators, and the report validator. The
acceptance commit changes only ten owner-acceptance/status Markdown files.

The annotated acceptance tag points to final main after both history merges and
this documentation. Final synchronization verifies local main = origin/main,
clean working tree, no active Git operation and the same local/remote annotated
tag object and peeled target. Implementation and review branches remain intact.

Stage 0–10 unchanged; Stage 11 **ACCEPTED/FROZEN**. Operating budget **UNSELECTED**.
HOLDOUT sealed; production/Pelias untouched; Stage 12 **NOT STARTED**.

**NEXT: FRESH STAGE 12 PELIAS TOP-N RETRIEVAL DESIGN.** Stop; do not begin Stage 12
in this acceptance session.
