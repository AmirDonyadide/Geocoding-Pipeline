# Stage 6 DEVELOPMENT summary

## Verdict

`STAGE_6_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW`

This is a DEVELOPMENT candidate, not Stage 6 acceptance. A fresh independent
review is required. HOLDOUT, production Stages 2–6, Stage 7, parsing, and
geocoding remain untouched.

## Scientific identity

- Contract: `stage06_early_exact_deduplication_contract_v1`
- Profile: `stage06_early_exact_deduplication_profile_v1`
- Implementation: `f39047cc825d9baef91915478f657aefecc86d4c`
- Authoritative job: `1759819` (`COMPLETED`, exit `0:0`)
- Schema fingerprint:
  `9c07b7a4c3f7a5c43ad457dcf6f7fe3fd746d54d82a731139905b30828b6c9ce`
- Logical fingerprint:
  `2f6379c0cd5dc9654c03895cae6fdd48f3a7af528158c33e44d2030c816640b6`
- Input-binding fingerprint:
  `6ba224d6d24c3631aae8aac69f4a362bb054f01d9e3d09327ec6b0fdd85a0e7d`
- Manifest fingerprint:
  `e1da7b8ef04b65b1ece8e710720b57a8536841766fcf9de641f889b42eadd241`
- Contract fingerprint:
  `d4fc73d7fabb734bb0996db4d5c02d6002131179259404eaab20699dacfba8c0`
- Ordered identity:
  `fe2a4758582c1880d2b5c62dfc5c587d865e05d13033af9f5e8208b58e2a0487`
- Benchmark fingerprint:
  `014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf`
- Fixed-500 fingerprint:
  `014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52`

The input binding exactly reproduces the accepted Stage 5 v2 contract,
profile, schema, logical, input-binding, manifest, ordered-identity, Benchmark,
fixed-500, and 35,000-row boundaries.

## Exact identity contract

The deduplication key is exact equality of an available accepted Stage 5
lowercase reconstructed candidate. No trimming, whitespace or punctuation
normalization, Unicode normalization, abbreviation handling, parsing, fuzzy
matching, or geographic logic occurs.

The fixed 32-byte ID is:

```text
SHA256(
  UTF8("safe_geocoding_pipeline:stage06_exact_candidate_id_v1\0")
  || exact_UTF8(candidate_lower)
)
```

Deduplication is global across STANDARD, NATIVE, rows, and same-row
representations. Representation provenance remains in the two row mappings.
Unavailable representations have a null ID and create no occurrence or
registry row. Registry rows are ordered by ascending unsigned candidate-ID
bytes. Every observed digest group is also grouped by exact candidate bytes;
distinct strings sharing one digest fail closed.

## Row map and registry

The row map retains every Stage 5 column exactly and appends only nullable
`stage06_standard_exact_candidate_id` and
`stage06_native_exact_candidate_id`, both `fixed_size_binary[32]`.

The unique registry contains non-null candidate ID, protected lowercase
candidate text, and total/STANDARD/NATIVE `uint64` occurrence counts. Candidate
text remains controlled and is not present in this report.

## Full 35,000-row evidence

- Source rows: 35,000 input → 35,000 row-map output.
- Dropped/added rows, duplicate identities, order mismatches, and upstream
  Stage 5 mismatches: all zero.
- STANDARD available/unavailable: 34,822 / 178.
- NATIVE available/unavailable: 34,925 / 75.
- Total available occurrences: 69,747.
- Unique exact candidates: 51,779.
- Duplicate downstream occurrences avoided: 17,968.
- Unique-to-occurrence ratio: 74.2383%.
- Estimated Stage 7 parse-call reduction: 25.7617%.
- Singleton/duplicate groups: 33,889 / 17,890.
- Duplicate groups spanning multiple source rows: 41.
- Same-row STANDARD/NATIVE exact-equal rows: 17,913.
- STANDARD-only/NATIVE-only/both-representation groups:
  16,899 / 16,998 / 17,882.
- Cross-representation duplicate groups: 17,882.
- Maximum group size: 8.
- All-group p50/p90/p95/p99: 1 / 2 / 2 / 2.
- Duplicate-group p50/p90/p95/p99: 2 / 2 / 2 / 2.
- Group sizes: 1=33,889; 2=17,855; 3=5; 4=24; 5=1; 6=4; 8=1.
- Canonical groups with multiple clean surfaces: 123; every such group has
  exactly two clean forms. Clean text remains excluded from the key while all
  source surfaces remain in the row map.
- Candidate-ID collision groups: 0.
- Distinct-text digest collision groups: 0.
- Empty registry candidates: 0.
- Registry total/STANDARD/NATIVE sums: 69,747 / 34,822 / 34,925.
- Occurrence, map-back, registry-text, and registry-count mismatches: all zero.

Length evidence shows 23 candidates at least one million code points; all are
singletons. The accepted 25,920,495-code-point adversarial Stage 5 candidate
passed exact row-map, rehashed-ID, registry-text, checksum, and independent
readback validation without truncation.

## Fixed-500 machine verification

The same frozen 500 identities and order produced 937 available occurrences,
613 unique selected candidates, and 324 duplicate selected occurrences. There
were 323 same-row exact-equal STANDARD/NATIVE cases. All Stage 5 fields, ID/null
derivations, same-key relationships, registry resolutions, and counts passed;
fixed-500 mismatches are zero.

The protected verification artifact fingerprint is
`624978c807fce7f9a76383b76d88e52eb85fa9bfbd5c41ced071d4a40c079190`.
Its manifest fingerprint is
`1eda47b375a432788e5f8366ce73e5364fdf97efac1742bd95981a15b87c0fb1`.
A human address review was not needed because Stage 6 never mutates candidate
text.

## Determinism and boundedness

Synthetic materializations passed candidate-ID, encounter-order, Arrow batch,
record-batch boundary, registry shard, and DuckDB-thread invariance. A forced
digest collision failed before publication. The algorithm uses adaptive Arrow
batches, bounded UTF-8 hash chunks, bounded Parquet output, and disk-backed
DuckDB grouping; it holds no population-sized Python candidate map. The
authoritative run used an 8 GiB DuckDB limit, four threads, and spilled zero
bytes/files.

## Performance

- Candidate-ID derivation: 0.721 s.
- Registry/dedup aggregation: 6.446 s.
- Row-map materialization: 7.335 s, including ID derivation.
- Core materialization: 13.816 s.
- Immediate publication validation: 22.618 s.
- Materializer end-to-end: 46.355 s.
- Materializer user/system CPU: 43.653 / 7.473 s.
- Total SLURM elapsed/CPU: 130 / 118.152 s.
- Materializer process MaxRSS: 2,873,344 KiB; SLURM batch sampled MaxRSS:
  912,692 KiB.
- End-to-end throughput: 755.043 source rows/s, 1,504.627 occurrences/s, and
  1,117.010 unique candidates/s.

At DEVELOPMENT rates, a linear planning projection for 141,048,582 rows is
186,809 seconds (51.89 hours). Applying DEVELOPMENT ratios projects about
281,077,584 occurrences, 208,667,272 unique candidates, and 72,410,312 avoided
Stage 7 parse calls. These are planning figures, not guarantees; production
distributions, I/O, scheduling, spill, and giant-value density may differ.

## Gates, privacy, and provenance

- Focused Stage 6 tests: 18 passed.
- Stage 2–6 regression tests: 175 passed.
- Full local-safe suite: 442 passed; four production-transfer tests deselected.
- Ruff, strict mypy, changed-file formatting, diff check, shell syntax, and
  privacy/tracked-data audit: pass.
- Controlled directories/files and SLURM logs: `0700` / `0600`.
- Authoritative attempts: one; failed or replacement authoritative jobs: zero.
- Design diagnostic: job `1759812`, exit `0:0`.
- HOLDOUT accessed: no.
- Production Stages 2, 3, 4, 5, or 6 started: no.
- Stage 7, libpostal, parsing, and geocoding started: no.

Before the implementation SHA was frozen, focused tests found and corrected
three engineering defects: zero representation-specific counts were rejected
for valid STANDARD-only/NATIVE-only registry rows; intermediate parent
directories could inherit non-private modes; and paired readback assumed equal
record-batch boundaries. Regression tests cover all three. No protected
authoritative attempt failed.

The design diagnostic’s aggregate-only SLURM logs initially had mode `0644`;
they were immediately tightened to `0600`, and the launcher was corrected
before the authoritative run. The authoritative logs were created and retained
at `0600`.

The immutable run label’s timestamp was generated on the client host and does
not agree with the cluster clock. SLURM accounting and manifest UTC timestamps
are authoritative; the label is treated only as an immutable identifier. This
does not affect content, Git SHA, input binding, or artifact fingerprints.

No candidate text, address text, stable source identity, source filename,
company name, or protected value appears in this report.

## Independent-review gate

Independent review must verify the exact implementation/evidence ancestry,
accepted Stage 5 binding, candidate-ID golden formula, forced-collision guard,
full publication readback, all reconciliations, fixed-500 evidence, giant-value
handling, deterministic ordering, bounded-memory design, permissions, and
scope exclusions. This development session does not accept Stage 6.
