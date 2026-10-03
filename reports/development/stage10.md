# Stage 10 DEVELOPMENT owner acceptance

## Status and scope

**STAGE10_MULTI_HYPOTHESIS_QUERY_GENERATION_ACCEPTED** / **STAGE_10_ACCEPTED**.
The owner accepts and freezes the exact remediated DEVELOPMENT candidate on
**2026-10-03**, following [final independent rereview PASS](../../review/stage10_independent/FINAL_REREVIEW.md).
All **281 checks** and **1,158,338 evaluations** passed; failed checks **0**,
protected-run harness failures **0**, unresolved candidate defects **0**.

Stage 10 generates bounded deterministic search hypotheses only. It does not
geocode, retrieve/rank results, correct source truth, declare address validity,
produce coordinates/final granularity or accept matches. Scientific operating
budget remains **UNSELECTED**, intentionally deferred to later Stage 12/13
DEVELOPMENT evidence. Acceptance authorizes no new execution or Stage 11 work.

## Owner acceptance and freeze — 2026-10-03

### Git and execution provenance

| Binding | Accepted value |
|---|---|
| Scientific executable / split implementation / launcher | `cf9e0fe4c12eb85f78051904c636ad084d87a541` |
| Candidate integration/main baseline | `186d4220cbdede6556ce81d16504949215a6f034` |
| Authoritative candidate reporting commit | `b29b230dece88404712105fc485c41411e12ba5d` |
| DEVELOPMENT job / state / exit | `1785683` / COMPLETED / `0:0` |
| DEVELOPMENT elapsed / scheduler MaxRSS | 22:49:36 / 12.457726 GiB |
| Requested resources | 4 CPUs, 32 GiB, 36 h, `--tmp=9216M` |
| Independent review branch | `review/stage10-independent-20260923` |
| Final independent rereview evidence commit | `c9c8813b53bb6603c3e3e159b04e0729c4240b40` |
| Independent rereview executable | `6c0a93edbd85fb45f5bd3472c08d65a7c045223d` |
| Independent rereview job / state / exit / elapsed | `1786959` / COMPLETED / `0:0` / 01:17:08 |
| Non-squash review-branch merge | `baa9acad5e2f9cd334cba7c4d4923dbc035b92c5` |
| Acceptance tag | `stage10-multi-hypothesis-query-generation-v1` (annotated, final owner-accepted main state) |

**Reporting-SHA resolution:** Git identifies `b29b230dece88404712105fc485c41411e12ba5d`
as the commit introducing the final candidate report and sanitized manifest.
Both [raw independent evidence](../../review/stage10_independent/evidence_1786959.json)
and [review disposition](../../review/stage10_independent/REREVIEW_EVIDENCE.json)
bind that exact valid 40-character commit. It is an ancestor of current main
and final review evidence. The questioned pasted reporting value is a
transcription concern only; there is no repository/provenance mismatch.

The annotated tag resolves the final acceptance commit, following the review
merge and this documentation. It is distinct from the scientific executable.
Owner acceptance does not rewrite candidate-era unaccepted status fields,
artifacts, manifests, registrations, seals, frozen specifications, historical
reports or independent-review evidence. Those remain accurate dated records.

### Immutable artifact and fingerprints

Publication key: **`stage10_development_20260928T081247Z_cf9e0fe4c12e`**.

Artifact:
`/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage10/development/stage10_development_20260928T081247Z_cf9e0fe4c12e`.

| Identity | Accepted SHA-256 |
|---|---|
| Manifest | `558298d7260199cc24f994d7480def9ad268aca057347f86ca41fad675a5a860` |
| Logical dataset | `4c4e4e6a63f565f6b3ce97f54c74fcd817cbd79922189fdc07ad3e3d76205c1a` |
| Query hypotheses | `c61ba899dbe4f714e2879995261b7d3a943e3b830ca69b4656e2d286230982e1` |
| Decision/provenance | `2c915039f6b8653fbfbd2acd3629cb7d1efd86190e3cb636c69542750c695420` |
| Contract | `be0a865f5217a82497cc3324fa11557df06441ec67e08f1cd2014cbf0d9b246b` |
| Profile | `6c42e00e7550edac184d6f8ba46e421e84f82a2df9b9234049ed3fca59a6798d` |
| Schema bundle | `659a98157951876b14078d0306b94f8f1e3e151fc92a7352243b3fce1b715070` |
| Design package | `d76d2e3d865b3b2cf6c08b080fec34135b7b6fa4736ded1d50c48c1c92645fc2` |
| Combined upstream input binding | `531d512f6c177fb5a9d6cd262e66846cdfd5cc66ba818c5aba8030165648878e` |
| Accepted Stage 8 manifest | `2a50bd8c066552c9cb7505ed2d6071f1ee36161b9a2cc07f3ed364cf00237827` |
| Accepted Stage 9 manifest | `321c9d8352fac5b78612a7c8e52f6f810f92bddb1e91f7cfe348398a6d707240` |
| Transliteration specification | `5d0a8f6906a8d93ac38d73a862d69e31e2e9e454e8d0518e0c13f9792256a916` |
| Runtime build lock | `20bfe735dca8b35b0ea10f1e3d729f2007e4cf3333dd5d5b5cdd527ef638d2cd` |
| ICU semantic runtime | `8b0a2232c28898f1dfd581e88fcbdbe8b7e7bebd458abcc852fab4cbfe225a8b` |
| Portable registration commit-record ID | `d3a9df71b0be9ffb70d3d5ebe2c478bb70df81a205145443a67af42849aab532` |

Design freeze/merge: `1443bb3b3c1bb50220bf38231e01552c66c4eaee`.
The unchanged [manifest](../../docs/scientific_assets/stage10_remediated_manifest_1785683.json)
retains exact input anchors, inventories and Stage 8 → Stage 6/source-line
lineage. Stage 8 anchor is `stage08_development_20260902T132726Z_c04cb97214a9`;
Stage 9 anchor is `stage09_development_20260910T155542Z_3e10ac7c1309`, each under
its controlled DEVELOPMENT root. Stage 8 remains sole source/occurrence authority.
Runtime remains ICU4C **77.1**, Unicode **16.0.0**, CLDR **47**, with the frozen
Grek-Latn/Cyrl-Latn rules. Runtime mismatches: **0**.

## Accepted scientific results

**35,000 source rows; 69,747 query contexts = 34,822 STANDARD + 34,925 NATIVE;
418,482 family decisions; 142,677 hypotheses.** Source-row 0/1/2-context counts
are **0 / 253 / 34,747**. Exactly six Q1–Q6 decisions per context; Q7 decisions
and hypotheses **0**. Occurrence map-back, PK/FK, deterministic identities,
zero orphans and tighter role-derived engineering bounds pass.

| Hypotheses/context | 0 | 1 | 2 | 3 | 4 | 5 |
|---|---:|---:|---:|---:|---:|---:|
| Contexts | 1,668 | 14,831 | 31,948 | 21,250 | 50 | 0 |

Observed maxima: **4/context, 8/source row**; engineering overflow **0**.

| Family | Eligible | Emitted | Converged | Suppressed |
|---|---:|---:|---:|---:|
| Q1 | 33,977 | 33,977 | 0 | 35,770 |
| Q2 | 34,102 | 34,102 | 0 | 35,645 |
| Q3 | 68,079 | 38,644 | 29,435 | 1,668 |
| Q4 | 33,556 | 33,556 | 0 | 36,191 |
| Q5 | 50 | 50 | 0 | 69,697 |
| Q6 | 2,348 | 2,348 | 0 | 67,399 |

**172,112 eligible constructions → 142,677 distinct hypotheses**. All 29,435
convergences preserve complete intent within one query context: Q1/Q3 14,694,
Q2/Q3 14,741. No Stage 11 cross-context request deduplication was performed.
Q3 ordered source boundaries and complete-intent convergence pass.

Q4 remains source anchored. Postcodes included: **6,751**; authorized
contradiction exclusions: **17,529 = 17,527 Q04 + 2 Q08**. NOT_FOUND,
NOT_EVALUABLE and GeoNames remain non-negative. Q1/Q2 contradiction mutations:
**0**. Q5: **50 emitted, 0 safety defects**. Q6: **157 Greek + 2,191 Cyrillic =
2,348 emitted**, runtime mismatches **0**. All **1,668** country abstentions
are structural outcomes, not invalid-address labels.

## C01 and C02 closure

**C01 — CLOSED.** Independent six-field reconstruction verifies **237,263
expected and actual PARSER_ONLY_FIELD_EXCLUDED decisions**: postalcode 61,328,
locality 39,777, region 68,079, country 68,079. Missing, duplicates, wrong-context,
wrong-field, source-anchor violations, parser-only payload inclusions and
included-source mislabelling are **all zero**. Repeated parser components do
not multiply decisions. Parser-only geography remains evidence/provenance only.

Old/new complete hypothesis relations are **exactly equal**: symmetric difference
**0**, including IDs, content, lineage and convergence. Decision differences
are confined to required C01 provenance on 68,079 Q4 rows; removing only the
new exclusion reason restores complete prior decisions. No scientific drift.

**C02 — CLOSED.** Durable registration kind is exactly
`STAGE10_DEVELOPMENT_QUERY_PLAN`; input-binding key is exactly
`stage10_input_binding_sha256`. Incorrect active forms are absent. Independent
portable hashing uses frozen `SAFE:publication-commit:v2` plus NUL and reproduces
the commit-record ID above. Registration, seal and reopen bind that identity.

## Accepted operations and publication

The accepted split workspace uses Goethe `/local/$SLURM_JOB_ID` for transient
computation and controlled PanFS for authoritative state. Scientific IDs,
decisions, C01 provenance, contents, convergence and logical fingerprints are
storage-path independent. Independent reopen with `/local` reads prohibited
verifies every authoritative relation, checkpoint payload, seal and required
receipt from PanFS. No authoritative-only dependency remains on ephemeral data.

All **1,099 durable checkpoints**, **16 prefix seals** and **1,115 total seals**
validate exact executable/upstream bindings, populations, inventories and
contents. Incomplete units cannot be adopted; exact `execution_git_sha` adoption
rules remain unchanged. Retained durable scientific/audit state is **1.037455
GiB**; the requested 9 GiB local storage is not a measured peak.

P11 **reservation → immutable validated artifact → manifest → corrected
registration → exclusive `_COMMITTED` → reopen/full validation: PASS**.
All three frozen required scientific replays pass. No false success or partial
publication. Sixteen publication phase records and 1,133 receipt hashes reconcile.
F02/F03 current exception-preservation, durable sanitized failure reporting and
quota preflight are accepted; historical F01 remains unexplained.

## Complete ledger and retained information

The [final independent ledger](../../review/stage10_independent/REREVIEW_LEDGER.md)
is preserved unchanged. **C01/C02 resolved; candidate defects = 0** across
scientific, implementation, integrity, publication and privacy classes.
Review-harness R01–R06 are resolved separately, with zero failures in job 1786959.
All I01–I10 remain informational and require no regeneration:

- I01: structural country abstentions; no address-validity interpretation.
- I02: absent Q5/Q6 coexistence is permitted for this population.
- I03: Q5 diagnostic-precedence overlap/discrepancies are zero.
- I04: three same-code replays complement independent checks.
- I05: DEVELOPMENT performance does not establish production capacity.
- I06: 24 local exact-ICU skips are covered by pinned Goethe runtime verification.
- I07: 28 fixed contexts / 924 certificate comparisons are bounded independent
  evidence, not re-derivation of every component; full-population integrity and
  contents were checked separately.
- I08: reporting makes no accuracy/validity/precision/recall/final-match claims;
  operating budget remains UNSELECTED.
- I09: historical F01 from job 1781277 has no established first exception/cause.
- I10: actual local-storage peak was not persisted.

Failed-review candidate 1774362, failed remediation 1781277, the original failed
review and all diagnostic/performance/forensic evidence remain preserved. The
[candidate report](../../docs/stages/STAGE10_REMEDIATED_DEVELOPMENT_1785683.md)
and [decision history](../../docs/DECISIONS.md) retain the chronology.

## Lightweight acceptance validation

Acceptance validates repository provenance and sanitized metadata only: exact
40-character reporting SHA, executable/report/review ancestry, normal merge
parents, unchanged candidate code/frozen assets/review evidence, exact manifest,
relation, runtime and registration fingerprints, status/docs/links, tracked-data
privacy and `git diff --check`. Frozen report and Stage 10 implementation
validators are used without protected inputs. Final main synchronization and
the annotated remote tag target are verified after push.

Acceptance checks: **STAGE_REPORTS_VALIDATION_PASS**;
**STAGE10_IMPLEMENTATION_INVENTORY_VALIDATION_PASS**; provenance, fingerprint,
registration-hash and privacy checks **PASS**. All **187** local links/anchors
in the **10** acceptance/status Markdown files validate. All **28** integrated
Stage 10 review files remain byte-identical to final review evidence; candidate
code, frozen assets, accepted Stage 0–9 records and the Stage 11 specification
section remain unchanged. `git diff --check` passes.

No protected access, scientific rerun, SLURM submission, candidate modification
or Stage 11 design occurs during acceptance. Stage 0–9 unchanged; Stage 10
**ACCEPTED/FROZEN**; HOLDOUT **SEALED**; production/Pelias untouched.

**NEXT: STAGE 11 COMPLETE SEMANTIC REQUEST DEDUPLICATION DESIGN**.
Stage 11 remains **NOT STARTED** and requires separate authorization. Stop here.
