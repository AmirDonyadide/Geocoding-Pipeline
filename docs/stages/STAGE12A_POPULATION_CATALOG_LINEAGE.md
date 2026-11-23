# Scientific Stage 12A — population, catalog and lineage

**BLOCKED CHECKPOINT — SCIENTIFIC 12A INCOMPLETE.** Job **1823128** is queued
for Goethe compute reserved for maintenance. This is a status checkpoint;
METHOD_FROZEN and DEVELOPMENT_RESULT_VALIDATED are not claimed. The current
run has not executed its catalog build, population/relation validation or
artifact reopening. A qualifying actual 12A result is not available.

## Scope and authority

Amir's explicit 2026-11-14 instruction authorizes the offline DEVELOPMENT
catalog/lineage build, validation and reopening on Goethe compute, then stop.
Authority is relayed standing owner delegation; manager approval is
owner-reported, not administrator, controller, licensor or operator attestation.
The owner-instruction SHA-256 is
`1d829225cac40dac81a6a6017021b0f439ba0eb3de32d4e7a03e62211d6167e9`.

Raw data, postal strings, Unicode, STANDARD/NATIVE representations and accepted
Stages 0–11 remain unchanged. The catalog is a derived index of accepted
relations, not a replacement population or new semantic deduplication.
Protected rows and the catalog remain on controlled Goethe storage; portable
evidence contains only safe aggregates, paths, code and hashes. Network is
denied. HOLDOUT, production, public/provider/Pelias access, protected transfer,
calibration/tail/C/T/N selection, 12B and Stage 13 are excluded. Old synthetic-B
windows and preparation counters are not prerequisites or renewed authorities.

## Current queued execution

| Binding | Exact value |
|---|---|
| Pushed executable commit | `b8d3e10860ac3c8e6971f2843661b7818f57ab8a` |
| Executable tree | `0322e98fc76fca235c8559c1cabc815764dce767` |
| Run | `stage12a_development_20261123T092315Z_79761ce6cc41` |
| SLURM job | `1823128`, submitted 2026-11-23 09:34:01 UTC |
| Configuration SHA-256 | `bafd9e8fca959775a1b658a8d4a35006c5dcf9a051b2f42fa13a4ccb77159696` |
| Authorization SHA-256 | `2fcaf3c036880d36c5cb8e60667df374bfe287a1cf6f3e51ad8cb91edcc8d2b7` |
| Genuine job-binding SHA-256 | `65eb3acb39247b97beb47228bd5c07d8d05d1aad9907b0e130d9182d6f08df68` |

Exact source/five-control canonical native readback
`6e5edbb7f0e6f7558ccac376a21eb3ca0179c6df16c95aba0d9c98d393c01529`
and final prejob review
`3410f54efb3be76950d81bac04bde30bbf77477fea958969d453dc44e9548f84`
precede the single submission. Queries 01–02 report ACCOUNTING_PENDING, each
with one `PENDING` row, query-client exit 0 and no terminal outcome.

A read-only controller snapshot matches the actual owner/account, source
command, working directory, configuration comment and log paths. It reports
`JobState=PENDING`, `RunTime=00:00:00` and
`Reason=ReqNodeNotAvail,_Reserved_for_maintenance`. Its SHA-256 is
`c897a2d2dc8ef574bd2a34473b5942eb0044475cb003d77e1e968d089dda7805`.
The displayed provisional `StartTime=2026-12-20T06:00:00` is not a guaranteed
date. A bounded read-only placement snapshot shows only
`inval`/`drain`/`down`/`maint` states across the visible partitions; no runnable
authorized alternative is established. Its SHA-256 is
`b4b196a2218d703e5349957b3bff5d48af9049f5af4f1e4d9b94a1d2ae213217`.
Partition node counts may overlap and are not summed.

The job remains queued and authorized, without cancellation, replacement,
partition change or duplicate allocation. The original sole observer ends
**2026-11-24 09:34:01.985807 UTC**; this checkpoint does not extend or reset
that scope to the provisional December estimate. Future continuation needs
fresh metadata observations and actual completion within existing 12A
authority, while reusing the same job. The bounded postterminal reader is
prepared and independently reviewed; it has not collected this run's outputs.

## Accepted input and required method

[Stage 11 acceptance](STAGE11_OWNER_ACCEPTANCE.md) binds these exact relations:

| Accepted binding | SHA-256 |
|---|---|
| Manifest | `9dc8e3853cc474c331d08740981b11d0b8128a7b11fd36d9f978cb883414b6cc` |
| Semantic requests | `01b1c6f243e12c407d9df86b77d3068be46a11f3511e4d77170db39f73e83f5e` |
| Hypothesis/request map | `ea23792566398856cba1372c914cec5c70e00412c80dac7f5fec259d663dfcc3` |

The accepted-input expectations are **35,000 sources**, **69,747 contexts**
(34,822 STANDARD; 34,925 NATIVE), **105,805 semantic requests**, **142,677
hypothesis/request links** and **1,668 zero-query contexts**. They are not
results of queued execution 03. Its actual catalog and population/relation
checks and full reopening are **NOT EXECUTED** at this checkpoint.

Version `stage12a_catalog_lineage_local_v1` reuses `Catalog` and
`LineageProjection`. The reviewed interface surface retains `core`,
`semantics`, `contexts`, `mapback`, independent `source_rows`, source-rooted
`population_mapback`, relation validation, verification and close, plus the
complete `reopen_artifact` operation. Original provider ID, source file,
logical record, file hash and `stable_source_row_id_v1` remain linked to every
source. Shared requests retain all context/hypothesis/family associations;
zero-query and contextless source handling does not depend on inner joins.
Witness interpretation remains UNKNOWN. Memberships/strata are lineage
projections and select no scientific calibration, tail subset, C, T or N.

All five full accepted-input passes, exact relation fingerprints, keys/FKs,
membership reconstruction, representation/source reconciliation and read-only
reopening remain required. A completed artifact contains only `catalog.sqlite`,
`binding.json`, `accepted_inputs.json` and exclusive `_COMMITTED`. Reopening
checks all four originals, provenance/configuration, full catalog hash and
actual relations through close. Local tests or metadata integrity do not
establish these actual scientific checks.

## Reviewed repair and execution limits

Commit `b8d3e108` is a normal descendant of failed-run source
`d1c4797e7b0b3c168ab417f147467288f7bad5d3`. Current module postimages are:

| Module | SHA-256 |
|---|---|
| `s12a_local_preparation.py` | `8c3be9e5adcde2646ac37947427f24803b6b2b762623a030f72dfab402c5da03` |
| `s12_b2_catalog.py` | `5b633c834fe3dbd412fc566b2f2a490b7ed5e0bf036b49432042fb54fbb1bddf` |
| `s12_b2_lineage.py` | `5ed222b53e3906d0a03cb2b28f80528f2f4b3bb5043acf185e6281f9ddb39cb5` |

The repair uses one fresh bounded 17-key capability query with original order
and exact per-key cardinality, plus a country predicate that preserves Python
field-value, missing/null, duplicate and ambiguity semantics. A run-local
original guard exception is restored only for exact integer SQLite interrupt
code 9. Safe diagnostics report a bounded integer code, without messages, SQL,
operands or traceback. Catalog bytes, scientific relations, interfaces and all
five full validation passes remain unchanged. Job 1815564's cause is unknown.

Evidence `5d6e7b7e96b55df4696f1da2b32e45435d2b02a7d4311b1385a3db2e16666755`
records 132 affected passes before the final numeric diagnostic and 89 final
passes; those overlapping sets are not added. A 249-invented-country,
12-context comparison preserves complete logical catalog digests while
reducing materialized country rows 5,976→24 and capability queries 204→12.
Those synthetic measurements do not estimate native runtime. Source review
`79e36aed7de505396466471279c4192e56e16de270f8f16339125aae8470f45f`
passes the repair.

The plan retains two requested CPUs, 32 GiB, two method-owned 4-GiB/one-thread
DuckDB limits, 43,200 application seconds and 44,100 scheduler seconds. Generated
storage has a periodic 64-GiB stop and 128-GiB current-headroom check. These
are requests/application limits, not physical reservations or completion
guarantees. Historical job 1815564 showed ReqTRES CPU 2 and AllocTRES CPU 80;
no hard native CPU/memory containment is claimed. Network denial uses reviewed
process auditing and offline dependencies, not an asserted OS firewall.

## Preserved failures and checkpoint disposition

Job **1815311**, source `5d3aaca9a3140b6d972ace4bfbb1fb42f8aa6a9a`, ended
TIMEOUT after 7,529 seconds against its 7,500-second request, with batch
CANCELLED 0:15 and extern COMPLETED 0:0. Stdout was empty; stderr contained
only Slurm's time-limit notice. No application cause or complete artifact was
established. Failure review
`3837d48db1e80f98bf832252b3f209df0be3c7b197174b44ba3a700081bc6e26`
remains immutable.

Job **1815564**, source `d1c4797`, ran 2026-11-14 19:05:45–2026-11-15
07:05:55 UTC (43,210 seconds), ending FAILED 1:0 with batch FAILED 1:0 and
extern COMPLETED 0:0. Original terminal evidence
`b0e35169f82f82a04c73d0a29bb1c9a00ed8e6072d35a95994519692983e4c93`
and safe extraction
`9c6bf9137e864e3ff5a16c053d76619517758ce7932144bd2dda08a00bb61888`
retain OperationalError/UPSTREAM_OR_UNCLASSIFIED_FAILURE at CATALOG_BUILD,
empty stderr, and 24 progress records ending at context-projection BEGIN.
Result/seal/binding/provenance were individually NOT_PRESENT_OR_UNREADABLE,
not an absolute absence proof. Review
`ec58b0c9782778fcef407a1c952b432e9125e7c58e092b12e34b599f263f7347`
records FAIL_NO_SCIENTIFIC_COMPLETION. The sparse boundary and elapsed interval
do not isolate its cause or prove a deadline trigger. Failed scratch/artifacts,
original clocks and accepted/rejected history remain preserved.

The intervening account-credit interruption paused assistant coordination;
it does not revise native outcomes or establish an institutional permission
failure. This checkpoint references only immutable evidence already recorded
through execution-03 queries 01–02; later observer records are outside its
manifest, and growing directories are not hashed.

Independent review
`80a9c3ab07534bfd758f56608013293300f68fb199d8e629039693ef19c60f71`
records **DEVELOPMENT_RESULT_PENDING_EXTERNAL_GOETHE_MAINTENANCE**. Reviewed
software/prejob/submission checks pass within their scope; compute entry and
actual catalog/reconciliation/reopening acceptance remain unestablished.

The next dependency is usable authorized Goethe compute for the existing job,
then genuine terminal evidence, bounded safe metadata collection and the same
independent review of actual relations/full reopening. Scientific 12A remains
incomplete. No 12B or other stage begins from this checkpoint.
