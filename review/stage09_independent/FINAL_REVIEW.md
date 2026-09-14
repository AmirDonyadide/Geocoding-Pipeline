# Independent Stage 9 DEVELOPMENT review — PASS

STAGE09_OFFLINE_REFERENCE_EVIDENCE_INDEPENDENT_REVIEW_PASS

Completed 2026-09-14. Candidate defects = **0**: no CRITICAL, MAJOR or MINOR
candidate defects found within this bounded review. No candidate code, accepted
Stage 8 output, contract, reference, publication or scientific output was changed.
No DEVELOPMENT rerun or additional review execution is required. This verdict
is independent review evidence; Stage 9 still requires owner acceptance.

## Identity and reproducibility

| Item | Independently reconciled identity |
|---|---|
| Reporting candidate / main / origin/main | `1c7182931fd4be2a7d5dee00d3105a1e54377bae` |
| Reviewed executable | `3e10ac7c1309c2636f35c0709fa283305d60d998` |
| Approved publication protocol | `96d17e763addc21b0a1c321c3a03666e928c25c7` |
| Manifest SHA-256 | `321c9d8352fac5b78612a7c8e52f6f810f92bddb1e91f7cfe348398a6d707240` |
| Logical dataset SHA-256 | `7ae84e149f4c9c2de7a791c9b326b88e387a70d155d8be55acf6b55e06bafae3` |
| Contract | `6dc0410556bad44a6a6d1b3695beb6219c54a61dab39747a5ffa92ac9fcda3f9` |
| Profile | `b12be7ba06de2360ba7cd9b971c4b562b1c8df5d25c30024975869fd2b34efd1` |
| Schema bundle | `7374b70fae76149b825f523e8317577bd6d868bee3fde648ea915301d4bcb716` |
| Stage 8 binding | `64f7678a76e3f29f57859f050329be925b216d2b1290eff5d36b9cb4482cea90` |
| Reference-pack manifest | `dd7994b907250d515470b820bcbf42993a08e4f3116409b7c94168446e1c064a` |
| Frozen reference lock | `61cc5850372886eb4ba6477a178ebd74f6ca878815036874ad47069ca32a1c63` |

Reviewed artifact:
`/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage09/development/stage09_development_20260910T155542Z_3e10ac7c1309`.

Fetch/clean-tree/ancestry checks were performed before review and reconciled after
completion. Main still equals origin/main at the supplied reporting SHA. All
three supplied commits are ancestors. Review changes exist only on
`review/stage09-independent-20260912`, under `review/stage09_independent/`.

The corrected read-only review job **1772139** independently reconciles as
COMPLETED, exit **0:0**, **01:00:30**, 2026-09-14 **11:11:05–12:11:35**
(scheduler timestamps as recorded),
MaxRSS **7,619,240 KiB**. It ran exact pushed review executable
`89cc9f9667cacac7ff26e70e14ee651af27b2e36`, importing the clean exact candidate
checkout. Its stderr is empty; all twelve phase markers completed. The scheduler
and preserved output inventory were inspected once in this terminal continuation;
no further job was submitted.

Controlled cumulative receipt:
`/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage09/independent_review/review_89cc9f9667ca_1772139/complete.json`.
SHA-256: `9ce865fbaf7c6b7acf769a9e9c5c7e76a112eb3dd8bf4b6630867fca0f736a4b`.
Remote and retained aggregate-copy hashes agree. **100/100 named checks pass**,
`failed_checks=[]`, and all six complete-integrity result groups pass. All
intermediate receipts and the original failed harness attempt are preserved.
Only the allowlisted cumulative aggregate receipt was copied for small local
analysis; the review database and protected row-level inputs stayed on Goethe.

[REVIEW_EVIDENCE.json](REVIEW_EVIDENCE.json) contains portable aggregate evidence.
[summarize_evidence.py](summarize_evidence.py) deterministically derives it from
the exact hash-pinned receipt without accessing row-level inputs. Reproduce with:

```sh
python review/stage09_independent/summarize_evidence.py /private/path/1772139_complete.json
```

The completed compute harness is [review.py](review.py), with exact-source and
execution guards in [review.sbatch](review.sbatch). Reproducibility is documented;
this review does not authorize another execution.

## Complete review-area disposition

| Area | Evidence and conclusion |
|---|---|
| Publication | PASS. Permanent exclusive directory reservation, registration and `O_CREAT\|O_EXCL` empty `_COMMITTED` seal follow the approved protocol. No active `RENAME_NOREPLACE`, check-then-rename race, stale takeover, or historical cross-job inode condition. Exact committed adoption checks pinned identity and full inventory; conflicts/incomplete reservations fail closed. Catchable uncertain commit outcomes reconcile through validated reopening. Full topology, manifest, inventory, hashes, owner/private permissions and symlink rejection pass before/after scans. |
| PanFS primitive | PASS for the primitive actually used. Diagnostic job 1771149 and exact SHA `e8d8333201a8c0b061d12288fadf404d833a875ffe0a4d160d535b88e6844f35` independently verified. Ten synthetic cases cover fresh/colliding exclusive create/mkdir, three four-process races, empty seal, repeated reopening, fsync and symlink rejection. Flags 131265 include `O_WRONLY\|O_CREAT\|O_EXCL\|O_NOFOLLOW`. This supports single-node exclusive creation, without claiming a power-loss or cross-node experiment. |
| Input/reference binding | PASS. Accepted Stage 8 manifest/relations and transitive Stage 6 identity consumed at frozen hashes. Exact executable, contract, profile, schemas, public assets and frozen lock bind to the candidate. All raw objects/capabilities and GeoNames index are rederived/reconciled; no refresh/substitution. |
| Logical relations | PASS. All six physical inventories, logical hashes, counts and PKs reconcile. Candidate/source/capability/reference/member FKs and witness field bindings pass. Evidence IDs and complete match sets validate. Independent scheduling checks prove source-pair totality and parser-ordinal expansion; no authoritative Stage 8 map is duplicated or source row lost. Coverage is fully recomputed, including distinct occurrence incidence. |
| Four states | PASS. Evidence outcomes are exactly SUPPORTED, CONTRADICTED, NOT_FOUND and NOT_EVALUABLE. Every contradiction has enabled negative authority; open-reference absence remains NOT_FOUND. All 6,673 REFERENCE_ASSOCIATION_MISMATCH rows are NOT_FOUND, not contradiction. Coverage country-assessment labels are a separate contracted reduction. |
| ISO | PASS. Code recognition, full subdivision ownership and scoped code/name support only. No postal/locality/street truth. Negative authority is limited to recognized explicit full-code parent relationships; an unknown code abstains. |
| libaddressinput | PASS. Exact frozen `all.json`; correct root/path, parallel-array offsets, rule capability and full-match/prefix interpretation. Format/required fields are descriptive metadata. Missing metadata and unsupported/qualified rules abstain. CN alternate rules and BH unsupported dialect are disabled; independently derived enabled Q04 countries = 176. See investigation below. |
| GeoNames | PASS. CONTRADICTED = 0, negative authority = FALSE, association mismatches = 6,673 diagnostic disagreements. Partial-code country gates, BR major-code limitation, US extended-code abstention and excluded full variants are retained. Postal/locality/admin witnesses come from the same scoped reference record; absence never invalidates a source. |
| Country assessment | PASS with I-002. Independent accepted-source-to-ISO join finds zero recognized full subdivision-code witnesses. All 51,779 country assessments therefore remain unresolved under the frozen Q02-only witness rule. Recognition/name matches cannot manufacture geographic country support. This is an expected design limitation for this population, not a broken join. |
| Normalization | PASS. Original Stage 8 pointers and all Q04 normalized digests match independent ASCII-uppercase recomputation. Strings/leading zeros/native scripts are preserved; no numeric coercion, transliteration or fuzzy matching. NFC/lower names use frozen Unicode 16. Form matching preserves separators; membership separator equivalence is explicitly country-scoped. See counterfactual diagnostics below. |
| Scale/performance | PASS for DEVELOPMENT, I-001/I-003 retained. Candidate job 1771191 independently reconciles to 08:04:53 and 9.657 GiB RSS. DuckDB is bounded, large components/members stream, small reference metadata is bounded, and postal equality-join branches avoid an accidental Cartesian join. Observed skew explains substantial evaluation expansion. Production capacity for 141,048,582 rows is not established or authorized. |
| Privacy/execution | PASS. Protected scans were guarded Goethe SLURM work against exact DEVELOPMENT paths, with offline network restrictions, private outputs and sanitized logs. No external address API, Pelias, HOLDOUT, production, protected strings/IDs in Git, or address-text inspection. Owner explicitly confirmed Stage 9 country aggregate reporting authorization on 2026-09-14; missing earlier decision documentation is not a candidate defect. Authorization does not extend to protected strings, IDs, individual examples, fine geography or weakened disclosure controls. |
| Tests | PASS. Independently ran all 836 candidate tests in exact Python 3.14.3 / Unicode 16 / DuckDB 1.5.5 / PyArrow 25.0.0; production-transfer tests were outside scope. Coverage reviewed for authority, scheduling, country gates, exact binding, publication adoption/fault recovery and normalization. 23 additional public/synthetic cases pass; 33 review SQL statements bind on synthetic schemas; seven harness regression tests pass. Mypy and Ruff checks pass. Tests supplement, rather than replace, full artifact evidence. |
| Reporting | PASS. All totals reconcile. 59.996% is explicitly an evaluable reference-rule check rate, not an invalid-address rate, source/candidate incidence, geocoding accuracy or final correctness. Country context is accepted provenance, not established geographic truth. |
| Stage 10 handoff | **BOUNDARY_HANDOFF_SUFFICIENT**. Actual candidate IDs, scope/argument pointers, state, capability/rule, evidence family, reference version, inline/shared witnesses and explicit abstention survive full integrity checks. Original accepted Stage 8 source/occurrence/Stage 6 lineage remains accessible and unchanged. This does not authorize Stage 10 implementation. |

## Reconciled totals

| Relation | Rows |
|---|---:|
| reference_registry | 3 |
| reference_capability | 47,578 |
| reference_object | 1,844,460 |
| candidate_reference_evidence | 6,565,329 |
| reference_match_member | 626,110 |
| coverage_summary | 48,479 |

All **51,779** Stage 6 candidates remain; **51,066** have an evaluable check.
Candidate loss = **0**; technical failures in the completed candidate = **0**.

| Family / slot | SUPPORTED | CONTRADICTED | NOT_FOUND | NOT_EVALUABLE | Total |
|---|---:|---:|---:|---:|---:|
| ISO_CODES | 112,940 | 0 | 270,961 | 223,170 | 607,071 |
| LIBADDRESSINPUT_METADATA | 333,896 | 54,025 | 790,919 | 1,200,439 | 2,379,279 |
| GEONAMES_POSTAL | 84,652 | 0 | 1,066,914 | 1,124,100 | 2,275,666 |
| Unconfigured slots (not a fourth family) | 0 | 0 | 0 | 1,303,313 | 1,303,313 |
| Total | 531,488 | 54,025 | 2,128,794 | 3,851,022 | 6,565,329 |

## Postcode-pattern conflict investigation

**Classification A — scientifically plausible and correctly implemented at the
frozen reference-rule evaluation grain. No Stage 9 implementation defect found.**

An independent Python ASCII-regex oracle resolved each Q04 input through its
accepted Stage 8 source-field/parser-ordinal pointer, selected the frozen public
country-root regex and independently applied evaluability gates. All **698,487**
Q04 states agree, all applicable normalized digests/origin fields agree, and
Python versus DuckDB/RE2 agrees on all **90,043** evaluable checks. Capability
country context also agrees with accepted trusted provenance for all evidence.
This establishes faithful conditional evaluation, not geographic truth of that
upstream context or semantic correctness of a parser's assigned postcode role.

| Capability | Conflicts | Evaluable checks | Conflict rate |
|---|---:|---:|---:|
| Q04 / POSTCODE_PATTERN | 54,022 | 90,043 | 59.995780% |
| Q08 / POSTCODE_PREFIX_BY_ADMIN | 3 | 904 | 0.331858% |

Q04 has 36,021 supports and 608,444 abstentions. Its conflicts are 0.822838% of all
6,565,329 Stage 9 evaluations. The remaining three contradictions belong to Q08;
the full integrity validator verifies their rule/authority/witness bindings.

The following are the twelve largest country-rule contributions. All are
LIBADDRESSINPUT_METADATA / Q04 / POSTCODE_PATTERN with a full match against the
listed exact public `all.json` root rule; denominator = support + contradiction.
The full country/scope/representation/rule diagnostic cross-tab remains in the
controlled receipt (`q04_rule_representation`); portable figures here are selected
country aggregates, without per-country candidate concentration or finer geography.

| Country / rule locator | Frozen regex | Conflicts | Evaluable | Rate |
|---|---|---:|---:|---:|
| RU/zip | `\d{6}` | 20,274 | 26,329 | 77.0025% |
| UA/zip | `\d{5}` | 14,096 | 15,627 | 90.2029% |
| IT/zip | `\d{5}` | 5,874 | 7,814 | 75.1728% |
| RO/zip | `\d{6}` | 3,691 | 17,806 | 20.7290% |
| BR/zip | `\d{5}-?\d{3}` | 2,037 | 4,134 | 49.2743% |
| VN/zip | `\d{5}\d?` | 1,259 | 4,282 | 29.4021% |
| ZA/zip | `\d{4}` | 875 | 1,334 | 65.5922% |
| AR/zip | `((?:[A-HJ-NP-Z])?\d{4})([A-Z]{3})?` | 830 | 904 | 91.8142% |
| IN/zip | `\d{6}` | 795 | 2,450 | 32.4490% |
| BG/zip | `\d{4}` | 571 | 1,771 | 32.2417% |
| KR/zip | `\d{5}` | 565 | 765 | 73.8562% |
| TW/zip | `\d{3}(?:\d{2,3})?` | 436 | 470 | 92.7660% |

RU + UA contribute **63.62%** of Q04 conflicts; adding IT gives **74.50%**.
These are rule-check shares, not population shares. CN's **497,109** Q04 checks
all abstain, consistent with the independently verified exception gate.

| Input scope | Conflicts | Evaluable | Rate |
|---|---:|---:|---:|
| SOURCE_ROW | 11,320 | 20,407 | 55.471162% |
| PARSER_CANDIDATE | 42,702 | 69,636 | 61.321730% |

| Disjoint representation membership | Conflicts | Evaluable | Rate |
|---|---:|---:|---:|
| STANDARD_ONLY | 44,831 | 73,153 | 61.283884% |
| NATIVE_ONLY | 2,756 | 4,284 | 64.332400% |
| BOTH | 6,435 | 12,606 | 51.047120% |

Representation membership is derived from unchanged Stage 8 occurrences. A
source-scope BOTH row denotes the same source/candidate pair in both
representations; a parser-scope BOTH candidate is linked to both representations.
These three categories partition checks and are not competing language accuracy
estimates. Source and parser inputs are string-typed; no numeric conversion occurs.

All evaluable Q04 checks use **POSTCODE_FORM_ASCII_UPPER_V1**, with the same
54,022/90,043 conflict rate. Another 558,711 normalized checks abstain, and
49,733 checks carry NOT_APPLIED_V1 and abstain. Unicode text and leading zeros
are preserved. ASCII `\d` behavior is deliberate and independently agrees across
engines, rather than silently converting full-width or other Unicode digits.

**Normalization and shape diagnostics:** 33,736 contradictions are in the broad
OTHER_TEXT_OR_SEPARATORS bucket; 9,123 are six ASCII digits, 8,331 five digits,
2,484 four digits, and 84 non-ASCII decimal strings. Country-rule differences
explain why a length can pass one country's rule and conflict with another.
In the largest rules, RU has 6,298 five-digit conflicts, UA 7,954 six-digit
conflicts, IT 1,156 six-digit conflicts, and BR 1,992 five-digit conflicts.
These are format/representation diagnostics, not corrected postcodes or invalid
address determinations.

Non-mutating counterfactuals resolve **0** contradictions by trimming whitespace,
**627** by removing ASCII spaces/hyphens (1.16% of conflicts), and **7,481** by
prepending one zero (13.85%). Counterfactual sets can overlap and are not repairs.
In particular, any five-digit string can satisfy RU's six-digit format after a
zero is added; that does not prove a zero was lost or that the new value is true.
All actual original-to-normalized digests agree, excluding Stage 9 zero loss.
Another 1,382 conflicting strings already have a leading zero. These results
exclude trimming/separator/Unicode coercion or regex-engine differences as an
implementation explanation for the high overall rate.

**Grain and concentration:** the 69,636 evaluable parser checks belong to **800**
candidates and **41,640** distinct candidate/normalized-value pairs. There are
27,996 repeated pairs at different retained component ordinals; one candidate
has 16,110 evaluable checks and one has 13,208 conflicting checks. Independent
scheduling agrees with the actual accepted Stage 8 component counts. This is
intentional occurrence-sensitive evidence, not duplicated authoritative candidate
rows or an accidental capability cross-product. Source checks involve 20,393
candidates, 20,403 distinct candidate/value pairs and 20,407 checks; maximum three
source checks per candidate. The two scopes overlap in candidate membership and
must not be summed as distinct candidates. Evaluation weighting is a material
interpretation limit (I-003), already compatible with the report's explicit grain.

Synthetic review independently demonstrates a valid leading-zero postcode,
invalid length, exact/incorrect hyphens, ASCII space versus NBSP, native digits,
unsupported country, disabled dialect/alternate rules, metadata with/without
subkeys, open enumeration misses, prefix alternation and full-format prerequisite,
and ISO explicit ownership. These are invented inputs, not protected examples.
Public metadata semantics distinguish a full country regex from subregion prefix
rules; the reviewed interpretation is consistent with the public
[libaddressinput metadata documentation](https://github.com/google/libaddressinput/wiki/AddressValidationMetadata).

## Complete findings ledger

There are **zero candidate defects requiring remediation**, zero unresolved
publication/integrity issues, and no privacy/HOLDOUT/production breach found.
No separately authorized protected human inspection is claimed; aggregate and
synthetic evidence resolved the implementation questions posed in this review.

| ID | Classification | Affected component and evidence | Impact / disposition | Scientific output changes | Candidate DEVELOPMENT rerun |
|---|---|---|---|---|---|
| I-001 | INFORMATIONAL | DEVELOPMENT capacity; measured candidate 08:04:53 / 9.657 GiB, full review 01:00:30 / 7,619,240 KiB. | Production scale is unproven. A proportional 141M-row workload would be vastly larger; future separately authorized capacity planning is required, not rejection for runtime. No present remediation. | No | No |
| I-002 | INFORMATIONAL | Q02/country assessment; independent full source subdivision-code witnesses = 0. | Expected design limitation: country assessment supplies no resolving signal in this population. Preserve unresolved labels and downstream limitations; no redesign in review. Other Stage 9 evidence remains usable. | No | No |
| I-003 | INFORMATIONAL | Q04 evaluation weighting; 69,636 evaluable parser checks / 800 candidates, repeated component ordinals and country-rule concentration. | High rate is faithful conditional evidence, not address invalidity or distinct-candidate prevalence. Retain explicit denominator and concentration context. No output remediation. | No | No |
| RH-001 | REVIEW_HARNESS | `review.py` SQL aliases were reserved DuckDB words (`role`, `value`, `rule`). | Fixed review aliases before execution in `89bcdc5`; all 33 synthetic SQL statements pass. Candidate untouched. | No | No |
| RH-002 | REVIEW_HARNESS | Local review runtime/public fixtures/package metadata initially incomplete or mismatched. | Created isolated exact runtime, installed package/dev dependencies and used retained frozen public assets; all 836 candidate tests pass without changing guards. | No | No |
| RH-003 | REVIEW_HARNESS | Integral DuckDB SUM returned Decimal; postcode snapshot and its failure receipt both failed in 1771693. | Preserved failed attempt and successful receipts. Fixed only allowlisted integral serialization and separate sanitized failure reporting in `89cc9f9`; seven regression tests pass. Corrected job 1772139 completed all phases and 100 checks. Fully resolved. | No | No |

The owner-confirmed country aggregate reporting authorization is resolved, not an
additional scientific, privacy or documentation defect. No consolidated candidate
remediation plan is needed. Review-harness fixes do not change frozen output.

NEXT: OWNER ACCEPTANCE OF STAGE 9
