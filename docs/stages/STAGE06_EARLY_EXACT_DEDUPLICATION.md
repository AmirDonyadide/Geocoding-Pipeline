# Stage 6 — early exact deduplication

## Status

**`STAGE_6_ACCEPTED` on DEVELOPMENT.**

The user approved the scientific design at Git commit
`9f9a5a07a2dd3825c895b23406311651e5480324`. That approval froze the contract
below and authorized implementation and one authoritative 35,000-row
DEVELOPMENT execution. Authoritative job `1759819` completed successfully.
Independent job `1760055` then falsification-tested the exact candidate and
reproduced its scientific identity and aggregates. Nothing here authorizes
HOLDOUT, production, Stage 7, libpostal, or geocoding.

## Purpose and boundary

Stage 6 avoids repeated downstream parsing work for candidate strings that are
already exactly equal at the accepted Stage 5 lowercase boundary. It
deduplicates candidate occurrences, never source rows. Every Stage 5 row and
column remains exact in a row-preserving output, and each available standard or
native occurrence maps to one unique candidate registry row.

No trimming, whitespace or punctuation normalization, Unicode normalization,
casefolding, abbreviation expansion, parsing, fuzzy matching, geographic
evidence, correction, or geocoding belongs to Stage 6.

## Accepted input boundary

The design binds only the accepted immutable Stage 5 DEVELOPMENT artifact:

- contract: `stage05_address_reconstruction_contract_v2`;
- profile: `stage05_address_reconstruction_profile_v2`;
- schema fingerprint:
  `63d4cdb3707eda65c67cc5196891fa5005adce2b12eb7109554793c48c5303c3`;
- logical fingerprint:
  `ba5829621fc15347d7cd4e168a48587bab896cd0be98924627876ae853dfaff2`;
- input-binding fingerprint:
  `7e68c33f7daa482b442eca82c00c6904ec5e38bec1b3fc598d5be4d52a6bcb9f`;
- manifest fingerprint:
  `fd945163e3be0242c43b98972350904631279cb99f366baadb0a3094ab6a1fc5`;
- ordered identity:
  `fe2a4758582c1880d2b5c62dfc5c587d865e05d13033af9f5e8208b58e2a0487`;
- Benchmark V1 fingerprint:
  `014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf`;
- fixed-500 fingerprint:
  `014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52`;
  and
- exactly 35,000 DEVELOPMENT rows.

An earlier Stage 5 v1 artifact is not a valid input.

## Approved decision table

| Question | Approved contract |
|---|---|
| 1. Exact dedup key | Exact Unicode equality of each available `stage05_standard_candidate_lower` or `stage05_native_candidate_lower`. Because accepted values are valid Unicode, exact UTF-8 byte equality is equivalent to code-point equality. No added transformation. |
| 2. Standard/native scope | One global namespace across both representations and all rows. Representation remains occurrence provenance, not key material. |
| 3. Unavailable behavior | No occurrence and a null Stage 6 candidate ID. Exact empty text never becomes a registry candidate. |
| 4. Candidate ID | Fixed 32-byte `SHA-256(domain || UTF8(candidate_lower))`, where `domain` is the exact byte string `safe_geocoding_pipeline:stage06_exact_candidate_id_v1` followed by one NUL byte. |
| 5. Collision verification | Group first by candidate ID and exact candidate bytes. More than one distinct byte string for one ID fails closed before publication. A digest is never treated alone as proof of equality. The same guard is rerun during independent published validation. |
| 6. Row-preserving schema | Every Stage 5 field in exact order, then nullable fixed-size-binary(32) `stage06_standard_exact_candidate_id` and `stage06_native_exact_candidate_id`. |
| 7. Registry schema | Non-null fixed-size-binary(32) `stage06_exact_candidate_id`; non-null string `stage06_candidate_lower`; non-null uint64 `stage06_occurrence_count`, `stage06_standard_occurrence_count`, and `stage06_native_occurrence_count`. No representative clean surface replaces row provenance. |
| 8. Registry order | Ascending unsigned lexicographic candidate-ID bytes. Collision checks make the key unique before publication. |
| 9. Map-back | Each available representation maps to exactly one registry ID; each unavailable representation has null; both row mappings may reference the same ID. |
| 10. Clean variants | Not key material and not added to the registry. All clean surfaces remain exact in the Stage 5 columns of the row-preserving dataset; aggregate variant evidence is reported. |
| 11. Occurrence semantics | One occurrence per available source representation. Counts reconcile independently for total, standard, and native. |
| 12. Same-row equality | Equal available standard/native values produce one unique candidate, two occurrences, and two row mappings to the same ID. |
| 13. Bounded algorithm | Stream Stage 5 shards in adaptive Arrow batches; derive IDs with bounded UTF-8 hash chunks; preserve row/shard order; aggregate exact candidate bytes in a disk-backed DuckDB database; stream the ID-sorted registry into bounded Parquet shards. No population-sized Python dict/set/list. |
| 14. Library responsibilities | Python `hashlib` owns the exact ID; PyArrow owns schemas, bounded row-map/registry writing, page-checksum readback, and atomic publication; DuckDB owns disk-backed grouping, count reconciliation, collision detection, deterministic registry sorting, and aggregate diagnostics. |
| 15. Fingerprints | SHA-bound input binding; combined ordered schema fingerprint; a layout-independent logical bundle fingerprint over the scientific contract, ordered row mappings, and ID-sorted registry content; unchanged ordered source identity; exact artifact hashes and manifest SHA-256. Separate ordered row-map and registry logical digests remain in the manifest as audit evidence. |
| 16. Atomic publication | Owner-only private temporary tree, full validation, manifest and success marker, fsync, then atomic rename to a new non-colliding immutable run directory. Failed attempts remain preserved. |
| 17. Fixed-500 evidence | Reuse the frozen 500 identities and order. Machine-verify every Stage 5 field, ID/null derivation, same-key relation, registry resolution/counts, and source-row preservation. No human address review is proposed because Stage 6 does not mutate candidate text. |
| 18. Stage 7 interface | Stage 7 later reads the unique registry once and keys parse output by `stage06_exact_candidate_id`; standard/native row mappings join parsed results back without choosing an authoritative representation. |

The frozen contract/profile names are
`stage06_early_exact_deduplication_contract_v1` and
`stage06_early_exact_deduplication_profile_v1`.

## Implementation profile

The row map retains the complete Stage 5 Arrow schema in its original order and
appends only two nullable `fixed_size_binary[32]` mapping fields. The unique
registry has the five fields defined in the decision table. Candidate IDs are
derived with Python `hashlib` while candidate UTF-8 is fed in bounded
code-point chunks. PyArrow streams source shards and publishes checksummed
Parquet into a new private tree. DuckDB performs disk-backed exact byte
grouping, collision detection, aggregate reconciliation, and deterministic
candidate-ID sorting.

Materialization validates accepted Stage 5 before reading candidates, checks
every source row and mapping while writing, fails before publication on any
distinct-text digest collision, and then independently reopens Stage 5 plus
every row-map and registry shard. Publication uses a private temporary tree,
manifest and terminal marker, directory fsync, and atomic rename. Fixed-500
evidence is machine-verifiable; the protected verification artifact contains
the frozen identities and mapping results, while its JSON and Markdown
summaries contain aggregate evidence only.

The local-safe implementation gates completed with 18 focused Stage 6 tests,
175 Stage 2–6 regression tests, and 442 full-suite tests with four explicitly
excluded production-transfer tests. Ruff, strict mypy over `src`, changed-file
format checks, shell syntax, and `git diff --check` also passed.

## Aggregate design diagnostic

Diagnostic-only commit `42134345f40816e5992ee8594003009cab88d63c` ran
through Goethe-NHR SLURM job `1759812` from a clean detached worktree. It
validated the exact accepted Stage 5 bundle before grouping and completed with
exit `0:0`. Its aggregate JSON SHA-256 is
`606493d91f160accc9780b205810e7ee298f87defa717c9926654942d1fb4af2`.

- Source rows: 35,000.
- Standard available/unavailable: 34,822 / 178.
- Native available/unavailable: 34,925 / 75.
- Total available candidate occurrences: 69,747.
- Unique exact lowercase candidates: 51,779.
- Duplicate occurrences avoided downstream: 17,968.
- Unique-to-occurrence ratio: 74.2383%.
- Estimated Stage 7 parse-call reduction: 25.7617%.
- Singleton groups: 33,889.
- Duplicate groups: 17,890.
- Duplicate groups spanning multiple source rows: 41.
- Same-row standard/native exact equality: 17,913 rows.
- Cross-representation groups: 17,882.
- Standard-only/native-only/both-representation groups:
  16,899 / 16,998 / 17,882.
- Canonical groups with multiple clean surfaces: 123; each observed group had
  exactly two clean surfaces.
- Maximum group size: 8.
- All-group p50/p90/p95/p99 sizes: 1 / 2 / 2 / 2.
- Duplicate-group p50/p90/p95/p99 sizes: 2 / 2 / 2 / 2.
- Group-size distribution:
  1=33,889; 2=17,855; 3=5; 4=24; 5=1; 6=4; 8=1.
- Empty available candidates, nonempty unavailable candidates, empty registry
  candidates, and occurrence reconciliation mismatches: all zero.
- Candidate groups at least 1,024 code points: 58, all singleton. The 23
  candidates at least one million code points are also all singleton.

The evidence supports the lowercase-only key: adding clean surface text would
split 123 otherwise identical accepted canonical keys and weaken the intended
Stage 4/6 boundary without protecting source information. Global
standard/native deduplication is also material: the dominant duplicate
structure is cross-representation equality, not source-row deletion.

DuckDB aggregation took 1.361 seconds with an 8 GiB memory limit, four
configured threads, and zero observed spill bytes/files. The full job took 42
seconds including isolated runtime setup and complete accepted Stage 5
validation. Batch MaxRSS was 23,600 KiB. These DEVELOPMENT observations do not
guarantee production scaling.

The output bundle was owner-only. SLURM initially created its aggregate-only
stdout/stderr files with mode `0644`; they were immediately tightened to
`0600`, the launcher was corrected to enforce `0600`, and the successful
diagnostic was not duplicated.

## Authoritative DEVELOPMENT candidate

Implementation commit `f39047cc825d9baef91915478f657aefecc86d4c` ran once
through Goethe-NHR SLURM job `1759819` from a clean detached worktree. The job
completed in 130 seconds with exit `0:0`, empty stderr, and owner-only logs. It
materialized, independently reopened the publication, and created fixed-500
machine evidence in the same allocation.

The candidate scientific identity is:

- schema:
  `9c07b7a4c3f7a5c43ad457dcf6f7fe3fd746d54d82a731139905b30828b6c9ce`;
- logical:
  `2f6379c0cd5dc9654c03895cae6fdd48f3a7af528158c33e44d2030c816640b6`;
- input binding:
  `6ba224d6d24c3631aae8aac69f4a362bb054f01d9e3d09327ec6b0fdd85a0e7d`;
- manifest:
  `e1da7b8ef04b65b1ece8e710720b57a8536841766fcf9de641f889b42eadd241`;
  and
- unchanged ordered identity:
  `fe2a4758582c1880d2b5c62dfc5c587d865e05d13033af9f5e8208b58e2a0487`.

All 35,000 source rows and every Stage 5 value/order were exact. The 69,747
available representation occurrences produced 51,779 unique candidates and
removed 17,968 repeated downstream calls, a 25.7617% reduction. There were
33,889 singleton groups, 17,890 duplicate groups, maximum group size 8, and
17,882 cross-representation groups. The same-row standard/native exact-equal
count was 17,913. STANDARD-only, NATIVE-only, and both-representation registry
groups numbered 16,899, 16,998, and 17,882.

All occurrence sums reconciled exactly. Candidate-ID collision groups,
distinct-text digest collision groups, source-to-registry missing mappings,
registry text/count mismatches, duplicate source identities, empty registry
candidates, and fixed-500 mismatches were zero. The 123 clean-surface-variant
groups were reproduced without changing the approved key. All 23 candidates
of at least one million code points, including the accepted
25,920,495-code-point adversarial value, passed exact preservation, hashing,
registry, and independent readback checks without truncation.

Candidate-ID derivation took 0.721 seconds, row-map materialization 7.335
seconds, registry aggregation 6.446 seconds, core materialization 13.816
seconds, and immediate publication validation 22.618 seconds. DuckDB reported
no spill. The aggregate evidence and complete performance record are in the
[sanitized Stage 6 report](../../reports/development/stage06_summary.md).

## Independent acceptance

Fresh independent review used harness commit
`e3ec946fb64a154033095d3edcd4afef7203c507`, preserved by annotated tag
`stage06-independent-review-e3ec946`. The harness did not import the Stage 6
implementation. It independently streamed accepted Stage 5 and immutable Stage
6 with different batch boundaries, recomputed every candidate ID and Stage 6
fingerprint, rebuilt exact occurrence groups in disk-backed DuckDB, compared
full candidate bytes within every ID group, reconciled every occurrence and
registry row, and verified the frozen 500 identities.

Independent SLURM job `1760055` completed with exit `0:0` in 33 seconds. Its
aggregate result SHA-256 is
`41dd5561ce0c7a57d97acec9eadbebe5f71f0754f017e0295ca324f5adb8579d`.
It reproduced 35,000 rows, 69,747 occurrences, 51,779 unique candidates, every
reported group distribution, all 23 STANDARD candidates of at least 1,000,000
code points, the 25,920,495-code-point maximum, and the fixed-500 result with
zero mismatches. Candidate-ID collision groups and distinct-text digest
collision groups were both zero. A separately injected
same-digest/different-text case exercised the fail-closed collision path.

The exact reviewed candidate is
`03bab36bc2f45d218eb289abff0ad2aed72cffd8`; its implementation is
`f39047cc825d9baef91915478f657aefecc86d4c`. The candidate was integrated into
`main` by fast-forward without rebasing, squashing, or rewriting history.
Stage 6 is frozen as `STAGE_6_ACCEPTED` on DEVELOPMENT. Production Stage 2
through Stage 6, HOLDOUT, and Stage 7 remain not started.
