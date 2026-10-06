# Independent review coverage and defect ledger

Status: **in progress; protected evidence pending**. A passing local test is
not a final scientific verdict. All areas A–X must be reconciled before PASS
or FAIL. Candidate defects are recorded without modifying candidate objects.

## Candidate defect ledger

No confirmed candidate defect at the pre-submission checkpoint. All five
classes remain open for full-population evidence:
`CANDIDATE_SCIENTIFIC`, `CANDIDATE_IMPLEMENTATION`,
`CANDIDATE_DATA_INTEGRITY`, `CANDIDATE_PUBLICATION`, `CANDIDATE_PRIVACY`.
This is not a claim that the final candidate defect count is zero.

## Full coverage matrix

| Area | Independent review evidence / pending protected check |
|---|---|
| A Provenance | Fetch/tag/ancestry/design bytes verified locally; contract/profile independently reconstructed. Job pins exact executable/reporting, accepted Stage 10 inventory/fingerprint, complete input binding, population, artifact and manifest. Mismatch fails closed. |
| B Input totality | Full bidirectional H/M key sets, count/unique-PK/null checks; every accepted hypothesis inspected. No sampling, budget or filtering in candidate path. Protected results pending. |
| C Request integrity | Independently specified Arrow types/nullability/order, exact metadata, unique/full request IDs, both FK directions and no orphan requests. Two relations only. Protected results pending. |
| D Serialization | Read complete implementation against frozen framing. Independent vectors cover ASCII, shortest strings, null, whitespace, U+0000/U+FEFF, RTL, multibyte/astral and combining text, BE lengths, explicit type tags and malformed framing. Local tests pass. |
| E IDs | Full independent SHA-256 on every candidate core and mapped upstream projection; synthetic same-ID/different-payload collision abort and claimed-ID rejection pass. Protected results pending. |
| F Global equality | Candidate uses full-ID external ordering and complete byte comparison. Independent every-edge bytes plus unique request keys establishes complete-core equality globally; no text-only/fuzzy/normalized equivalence. Protected results pending. |
| G Modes/endpoints | Closed paired enums and incompatible payload rejection independently challenged. Full mode counts pending. |
| H Exact preservation | Direct projection contains no transformation. Unicode/whitespace/case/punctuation synthetic distinctions pass; full protected byte equality pending, no payload export. |
| I Country | Required separate alpha-2 boundary and namespace; country component remains null. Distinct country IDs and malformed/missing/empty rejection pass; full bound/unbounded counts pending. |
| J Policies | Five exact singleton policies and complete field set independently checked. No generic headers, retrieval binding or parameter bag; full protected policy count pending. |
| K Stage 11/12 | Encoder consumes only frozen schema values. Input slot is validated then excluded. Retrieval/size/transport/host/index/auth/job/path extras rejected; execution provenance lives outside the core. No top-N selected. |
| L Validity states | Independent mode-by-field matrix tests null, empty, missing, defaults, bool/int/float/bytes/list/object and invalid Unicode. Valid whitespace is preserved. Tests pass. |
| M Dedup aggregates | Independent exact multiplicity count histogram, arithmetic and complete summary reconstruction; protected 142,677/105,805/36,872 and 25.842988% assertions pending. |
| N Lineage | Independent H/M/D joins use hypothesis AND context plus accepted source/role/candidate FKs; complete family/role/source/context incidences and all upstream contexts computed without a new lineage relation. Protected counts pending. |
| O Interpretation | Read complete candidate report and implementation record. Reduction and cross-representation/family diagnostics are consistently workload-only, without accuracy/confidence claims. Summary fixed labels checked. |
| P Fingerprints | New encoder/hash oracle covers both relations and dataset. Synthetic physical order/shard/codec/path and generation partition/thread/resume changes preserve hashes. Protected exact hashes pending. |
| Q Checkpoints | Independent unit/seal/physical/logical hashes, exact bindings/key ranges/contributors/prefixes, full input-to-H and reduction-to-S/mapping equality; no omitted checkpoint. Synthetic interrupted/resumed oracle passes. Protected 18+256 seals pending. |
| R Publication | Complete adapter reviewed against unchanged accepted primitives; independent registration-domain/hash construction and fault tests pass. Actual private inventory, phase order, reservation/seal/registration and immutable before/after hashes pending. |
| S Local independence | Candidate reopen registers durable paths only and disables spill. Synthetic complete local loss passes. Job forbids former local opens throughout and all local opens during supplemental full reopen. Protected result pending. |
| T Failure safety | Candidate first-error reserve, closed error identities and guarded secondary reporting reviewed. Independent injected collision, contract, manifest and registration faults prohibit seal; primary static failure survives a secondary receipt error. Candidate post-seal failures require exact reconciliation. Local tests pass; actual phase/receipt observations pending. |
| U Privacy | Only code/synthetic fixtures/aggregate metadata tracked. Candidate CLI prints closed sanitized receipt; job compares stdout exactly to that receipt and requires empty stderr. Shared guard precedes protected stat/read; job disallows source-tree mutations and external sockets. No HOLDOUT/production/Pelias access. Protected log/tree checks pending. |
| V Architecture | Candidate uses capped DuckDB sort/group/joins and single-row readers with byte-bounded writers; full hashes and streamed memberships, deterministic partitions and exact-bound resume. No pandas or pairwise quadratic path. Fixed-memory reopen fails on insufficient resources; no production envelope is inferred. |
| W Tests | Pinned safe regression plus already-local public-only tests reproduces 1,343 passing tests; 24 unchanged optional ICU skips unrelated to Stage 11. All candidate Stage 11 tests and new independent checks pass; self-tests are supplemental evidence. |
| X Ledger | Candidate, harness and informational findings kept separately. Complete protected review and final ledger reconciliation remain required. |

## Review-harness findings

| ID | Finding | Disposition |
|---|---|---|
| R01 | False-equivalence test accidentally included the same invented core twice while asserting all fixtures distinct. | RESOLVED: use a distinct invented address for the field-role pair; independent vectors rerun. No candidate defect. |
| R02 | First broad regression used Python 3.14.7 and a noncanonical `/tmp` import path. 28 frozen-runtime checks and one pre-existing path-filtered profiling test failed; three optional public assets were absent from the detached checkout. | RESOLVED: existing Python 3.14.3 environment and canonical `/private/tmp` import path produce 1,340 pass/27 skip. Three public-only tests pass separately using existing public assets; 24 optional ICU skips remain. No guard weakened or protected asset fetched. |
| R03 | Negative contract fixture used null in a non-nullable Parquet field, so Arrow rejected it before the intended application check. | RESOLVED: inject an empty country string, legal to the storage type and forbidden by the scientific contract. Candidate rejects and no seal appears. |
| R04 | Draft independent registration oracle initially named the reused protocol incorrectly. | RESOLVED during static construction: use the actual frozen `exclusive_run_commit_seal_v2_candidate` protocol and `SAFE:publication-commit:v2` hash domain; independent synthetic registration comparison passes. |
| R05 | New multi-defect collection test used SQL equality in a named struct-update argument. | RESOLVED: use DuckDB named assignment syntax; the synthetic test now verifies that multiple defects are recorded and aggregate review continues. |
| R06 | Job 1789589 failed at review-only `scratch.mkdir` before relation scans. Its 35 completed checks passed. Original sanitized receipt omitted OS exception class/errno, so the underlying filesystem cause is unknown. | HARNESS REPAIRED / protected follow-up pending: remove review scratch dependency and use a 2 GB memory-capped, spill-disabled connection. New tests cover actual connection settings, no directory creation, synthetic full reconciliation and safe OS-error classification. Candidate objects remain unchanged; original job/evidence preserved. |

First protected review job **1789589** ended **FAILED / 1:0** after 25 seconds.
See [immutable sanitized evidence](evidence_1789589.json). Provenance and private
inventories passed, but protected scientific/operational reconciliation remains
incomplete. R06 is not a candidate defect or a reason to issue a verdict.

## Informational ledger

| ID | Observation and limits |
|---|---|
| I01 | Stage 11 is a non-executable semantic catalog. Equal IDs do not establish equal responses across size, engine or data builds; future execution identity remains Stage 12 work. |
| I02 | Upstream zero-hypothesis contexts and source lineage remain accepted Stage 10/8 authority. The review does not reopen raw/Stage 8 source payloads or regenerate Stage 10. |
| I03 | DEVELOPMENT runtime/memory/local sampling is informational; no production capacity extrapolation. Candidate's spill-disabled 2 GB reopen can fail safely when a future workload exceeds its envelope. |
| I04 | Optional ICU tests are unchanged accepted Stage 10 tests. Stage 11 uses no ICU/transliteration path; these skips cannot be treated as Stage 11 scientific validation. |
| I05 | Durable phase evidence and code establish publication behavior; review does not experimentally corrupt, race or interrupt the immutable protected artifact. Failure tests use invented objects only. |
| I06 | Audit hooks cover Python opens/mutations; they are not an operating-system sandbox for native libraries. Exact manifest paths, explicit DuckDB file registration, disabled network extensions, spill-disabled reopen and before/after hashes supply complementary evidence. |
| I07 | This fresh session verifies HOLDOUT sealed by accepted authority and non-access. It does not inspect HOLDOUT storage or attest to activity outside this session. |

Regeneration decision: **not made; full candidate review pending**.
