# Phase 3 pilot-select engineering optimization

Status: **ENGINEERING WORK IN PROGRESS — SCIENTIFIC CONTRACT FROZEN**

This note records the measured/inspected baseline before optimization. It does
not authorize a production pilot, change `phase03_sampling_contract_v1`, or
replace the reference selector.

## Reference implementation and bottleneck

The reference backend is `SQLitePilotCandidateStore` in
`phase03/pilot_runner.py`. Its exact state is:

| Table | Primary key | Per-row behavior |
|---|---|---|
| `candidate` | `stable_id` | One row per Phase 2 row containing the exact 32-byte identity, primary group, quota/fill/split SHA-256 scores, and safety flag. |
| `membership` | `(dimension, category, stable_id)` | One row for every sampling-stratum membership of every Phase 2 row. |
| `selected` | `stable_id` | Populated only during final selection. |
| `safety_location` | `(source_file, logical_record_number)` | Populated only for approved Phase 1 safety locations. |
| `checkpoint` | `shard_id` | One completed-shard identity/count record. |
| `run_metadata` | `key` | Version, contract, binding, and configuration fingerprints. |

All tables are `WITHOUT ROWID`; their declared primary keys are the only
indexes. The reference connection uses `journal_mode=DELETE`,
`synchronous=FULL`, and `temp_store=FILE`.

Pass 2 holds one `BEGIN IMMEDIATE` transaction per 100,000-row source shard.
Within that transaction, `executemany` flushes candidate, membership, and
safety rows every 1,000 candidates. There is one durability commit per shard,
not one commit per row or insertion batch. The reference final selector does,
however, commit each of its 12,000 `selected` inserts separately. This is a
secondary end-of-run cost rather than the observed growing-ingest bottleneck.

The dominant costs are:

1. many B-tree insertions per input row, especially the multiple indexed
   `membership` rows;
2. progressively larger random B-tree working sets as the database grows;
3. three SHA-256 ranking values stored for every row even though only a small
   selected set is ultimately required;
4. quota queries that join `membership` to `candidate` and sort by quota score
   for each category;
5. a final full-population sort by `fill_score`, for which no score index
   exists;
6. a redundant per-shard SHA-256 read after the authoritative input validator
   has already verified the same manifest-bound hash.

Adding broad score indexes would make ingestion larger and more expensive and
would not remove the all-row membership state. The existing primary-key
indexes enforce identity/membership uniqueness and support exact joins; none is
removed without equivalence evidence.

## Frozen ordering semantics

The optimized implementation must reproduce this exact sequence:

1. targeted safety identities in stable-ID order;
2. every `country_cohort=RARE` identity in `(primary_group, stable_id)` order;
3. every non-primary `(dimension, category)` in UTF-8/SQLite binary order,
   selecting unrepresented identities by `(quota_score, stable_id)` while
   applying the 500-row primary cap;
4. deterministic fill by `(fill_score, stable_id)` under the same cap;
5. DEVELOPMENT/LOCKED partition by `(split_score, stable_id)`.

Quota, fill, and split scores remain the existing domain-separated SHA-256 of
the raw 32-byte `stable_source_row_id_v1`. Selection engine, worker count,
shard order, completion order, and temporary-store settings must not change any
selected identity or partition.

## Exact bounded-state proof obligation

An exact bounded reduction is possible without retaining every membership, but
the original proof used an insufficient quota frontier and was invalid:

- every targeted and rare candidate is retained in full;
- for each `(secondary dimension, category, primary group)`, retain the lowest
  `maximum_primary_stratum` candidates by `(quota_score, stable_id)`;
- for each primary group, retain the lowest `maximum_primary_stratum`
  candidates by `(fill_score, stable_id)`;
- retain exact population counts for every secondary group.

The frozen SQLite selector checks `represented >= target` only after processing
a cursor row. Consequently it deliberately adds one eligible candidate when an
overlapping earlier stratum has already satisfied the current target. A quota
frontier limited to `minimum_per_stratum` can consist entirely of candidates
already selected by earlier strata and omit the next candidate that the
reference adds. This is what job 1747430 exposed.

Let `C = maximum_primary_stratum`. Before any secondary quota stage, fewer than
or exactly `C` rows can be selected from a primary group. If the group is
already capped, every omitted candidate from it is rejected. Otherwise, among
the first `C` candidates for that `(dimension, category, primary)` frontier,
there are enough unselected candidates to fill the remaining primary capacity:
if `s` rows from that primary are already selected and `k <= s` of those occur
in the frontier, the first `C` entries contain `C-k >= C-s` unselected rows.
After those are considered, the primary is capped, so no later omitted row can
be selected. Thus retaining the first `C`, rather than the first quota minimum,
is sufficient to retain every identity the reference could select. The same
cap argument proves the existing fill frontier.

That candidate-retention argument is only half of the proof. Exact replay also
requires every local and global reduction to preserve the same top-`C`
invariant. Local top-`C` summaries merge exactly into global top-`C` summaries
only when the merge itself also retains `C` entries. With that invariant, an
induction over the frozen stage order gives identical selected sets and
primary-cap counts before and after every stage: the base mandatory stages are
retained in full, and each subsequent reference-selectable cursor row remains
in its frontier and is evaluated against the same preceding selected state.

Top-`C` retention does not preserve every rejected row that a full SQLite
cursor may inspect after a primary is already capped. Therefore full cursor
diagnostics such as the count/order digest of otherwise irrelevant rejected
fill rows are reported separately from scientific replay state. Exact selected
events, cumulative selection, and primary occupancy are the fail-closed
equivalence gate; a cursor-observability difference is not misreported as an
identity difference. Exact per-primary frontier population counters allow an
exhausted infeasible quota stage to reconcile its aggregate candidates-inspected
and cap-blocked counts even beyond the retained top-`C` identities. When omitted
rejected identities mean an ordered blocked-event or frontier digest cannot be
complete, the trace marks that digest incomplete rather than claiming false
equivalence.

The authoritative Phase 2 manifest already binds exact global uniqueness of
20,600,000 stable IDs. Synthetic/non-production bounded tests still perform
explicit duplicate checks. Production bounded execution must fail unless the
manifest reports total rows equal to distinct stable IDs and zero duplicate
stable IDs.

This proof is a prerequisite, not acceptance evidence. The bounded backend
remains optional until baseline and optimized identity files compare byte for
byte on controlled Goethe-NHR benchmarks.

## Benchmark 1747430: real-data equivalence failure

Job `1747430` reached the quota-feasible five-shard baseline case and completed
both the SQLite reference selection and the bounded preview. Their
`PilotSelection` objects differed, so the unchanged equality gate correctly
failed before any optimized result could be promoted.

The failed v2 job did not persist either selection, a trace, or an identity-safe
mismatch artifact, so the exact production identity and quota stage cannot be
recovered after its job-local state disappeared. A minimized nine-row fictional
fixture reproduces the structural defect. With quota minimum 2 and primary cap
5, earlier overlapping strata already represent `d0=C2` twice. The frozen
reference nevertheless enters that quota cursor and adds fictional identity
3018. The old bounded state retained only two candidates per
`(dimension, category, primary)` and had discarded 3018, so it added 3023 from
another primary instead. This changes the selected identity set and therefore
the DEVELOPMENT/LOCKED result; it is not metadata-only.

Benchmark v3 retains the first primary-cap candidates per quota frontier and
adds an optional deterministic trace to both selectors. On any future mismatch
it atomically persists an owner-only diagnostic containing privacy-safe identity
hashes, scientific and metadata fingerprints, the first divergent stage,
selected ranks, cumulative selection digests, primary-count digests, and quota
and fill frontier digests before failing closed. GNU Time output is also
retained when a benchmark stage fails. Evidence from failed jobs 1747375 and
1747430 remains untouched.

## Benchmark 1747527: merge-time replay-state failure

Job `1747527` failed closed on the one-shard real-data performance case. Both
selectors reached the same infeasible `postcode_lexical=ASCII_LETTERS` stage,
but the bounded replay selected five more rows and recorded five fewer
primary-cap blocks. The final visible failure was downstream evidence; the
first divergence had occurred earlier.

The implementation retained `maximum_primary_stratum` (`C=500`) rows when a
worker ingested each `(dimension, category, primary)` frontier, but
`ExactBoundedCandidateReducer.merge()` mistakenly re-truncated that worker
frontier to `minimum_per_stratum` (`50`). Even a one-shard bounded run creates a
worker snapshot and merges it into the parent, so this discarded candidates
51–500. Overlapping earlier stages could consume the first 50 entries; the
parent replay then chose a different primary group's row, producing a smaller
occupancy for the reference-saturated primary. Later rows from that primary
were consequently eligible in bounded replay although SQLite correctly
blocked them.

Benchmark v4 uses the primary cap for both ingestion and merge. Its trace
records pre- and post-stage selected counts/digests, primary occupancy,
represented counts, selected and cap-blocked event digests, and quota/fill
frontier digests. Mismatch artifacts now persist both the first scientific
state divergence and the first difference including bounded cursor
observability, with identities and primary groups privacy-hashed. Failed job
1747527 evidence remains untouched.

## Explicit engineering backends

`baseline-sqlite` remains the CLI default and reference implementation. The
optional `optimized-sqlite` backend changes only reconstructable working-state
operations: `journal_mode=OFF`, `synchronous=OFF`, `temp_store=MEMORY`, a
configurable negative `cache_size` (8 GiB by provisional default), a
configurable `mmap_size` (disabled by default pending measurement), and 10,000
candidate `executemany` batches inside the unchanged one-transaction-per-shard
boundary. Its final 12,000 selected-set writes use one transaction. These
parameters have a versioned operational fingerprint. They do
not participate in the scientific sampling fingerprint.

The OFF journal/synchronous modes are safe only because an interrupted or
failed optimized database is never resumed or promoted: it must be deleted and
reconstructed from the immutable Phase 2 snapshot. They are prohibited for
identity sets, seals, manifests, reports, and the compact selected-state
database. `temp_store=MEMORY`, page cache, and optional memory mapping are
performance choices that require Goethe-NHR memory measurements; none is
assumed beneficial without benchmark evidence.

`bounded-parallel` applies the exact reduction above independently per shard,
then merges shard summaries in the parent process. Workers never write to a
shared SQLite database. The merge result is sorted/reduced independently of
worker scheduling, completion order, worker count, and shard order. Only the
selected 12,000 candidates are written to the durable review-compatible SQLite
state after exact selection.

The dedicated cluster benchmark is restricted in code to 1, 5, or 10 Phase 2
shards for performance cases. It uses the already completed full-population
country profile so that country-cohort classification remains the production
classification.

## Benchmark 1747375: subset infeasibility

Benchmark job `1747375` stopped after 2 minutes 21 seconds in its first
`shards_1_baseline` case. The reference selector raised `pilot quotas/caps
cannot satisfy minimum stratum quota` before any optimized backend ran. This is
the frozen selector's correct response to an infeasible population, not an
optimized-engine mismatch.

The exact code path computes each row's `primary_country_group` and
`country_cohort` from the completed 20,600,000-row country profile. In contrast,
the membership `COUNT(*)`, available candidates, already-represented count,
and 500-row primary-cap state used by final quota selection contain only the
benchmark subset. For each subset `(dimension, category)`, the target is
`min(subset_available, 50)`. The selector raises when it exhausts every subset
candidate in quota-rank order but primary-cap rejections leave represented
below that target.

The old exception did not record the failing dimension, category, target,
represented count, or available count. Job-local SQLite disappeared after the
failed allocation, and non-interactive access to the cluster log was not
available during the local repair. Consequently the exact category for job
1747375 cannot be recovered from the supplied traceback without inventing it.
The v2 harness records those privacy-safe fields before final selection; an
`UNUSUAL:` country category is redacted in portable diagnostics. The same
infeasibility can occur for 5 or 10 arbitrary shards because neither shard
count guarantees coverage across overlapping secondary quotas under primary
caps.

## Benchmark v4 gates

Performance and final-selection evidence are now separate:

1. `PERFORMANCE_STATE` scans deterministic 1/5/10-shard prefixes and measures
   classification, ranks, SQLite ingestion, bounded summaries, reduction,
   memory, disk, and CPU. SQLite engines now independently execute the frozen
   reference allocation with structured infeasibility reporting; a bounded
   result can no longer be the sole feasibility oracle. Both paths must agree
   on feasibility and the scientific infeasibility reason. An infeasible case records
   `NOT_APPLICABLE_SUBSET_INFEASIBLE`; that status is explicitly not final
   selection equivalence.
2. Baseline and optimized SQLite must have the same canonical hash over every
   candidate, score, membership, safety location, and checkpoint. All SQLite
   and bounded engines must also have the same canonical selector-relevant hash
   over exact population counts, mandatory candidates, quota frontiers, fill
   frontiers, overlapping strata, ranks, and safety locations. A mismatch
   stops the matrix before larger cases.
3. A cluster-only corpus builder orders whole Phase 2 shards using an
   independent versioned benchmark hash and adds fixed 16-shard batches until
   the unchanged selector is feasible. Fixed batch boundaries make the corpus
   independent of worker count and completion order. The corpus must be a
   strict subset of the 206 shards and is bound to the exact Phase 2 manifest,
   production country profile, references, registry, Phase 3 configuration,
   sampling contract, and sampling configuration. It stores only shard
   identities, counts, and hashes—not candidate identities, payload, or
   DEVELOPMENT/LOCKED partitions. If no strict subset is feasible, it fails
   rather than running the production snapshot.
4. `FINAL_EQUIVALENCE` accepts only that validated corpus. Every engine must
   produce byte-identical DEVELOPMENT and LOCKED identity artifacts, identical
   selected-state hashes, quota/cap behavior, and scientific fingerprints.

Benchmark outputs live only below the versioned Phase 3 `benchmarks` namespace,
separate from production pilot runs and identities. Failed job 1747375 evidence
is not removed or overwritten. No optimized engine may be promoted on
synthetic evidence, preselection-state evidence, or any mismatch.

## Durability boundary

Relaxed SQLite PRAGMAs may apply only to reconstructable candidate working
state. Identity sets, seals, manifests, reports, and the compact selected-state
database used by later review stages retain atomic write, integrity validation,
owner-only permissions, and durable promotion. A failed disposable state is
reconstructed from immutable Phase 2 input; it is never treated as a successful
scientific artifact.
