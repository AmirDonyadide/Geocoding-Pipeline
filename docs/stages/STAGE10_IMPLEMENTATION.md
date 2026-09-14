# Stage 10 implementation and controlled DEVELOPMENT execution

## Authorization and design freeze

The owner approved final design `ca0bac7acd8bae709e171c481ddea52df3e5304d`
and authorized implementation, comprehensive synthetic/fault validation, one
complete bounded implementation self-review, a pushed executable and exactly
one controlled DEVELOPMENT execution. No Stage 11, Pelias, HOLDOUT or production.

The approved branch was merged into main with a normal non-squash merge,
`1443bb3b3c1bb50220bf38231e01552c66c4eaee`, and main was pushed normally.
Its first parent is accepted Stage 9 main
`23cfb85f428b00301d68591ea5992763abf9ad88`; the approved design is the second
parent. All implementation descends from that freeze. No Stage 10 acceptance tag.
Historical status wording in the normative design remains frozen; this separate
record carries the new implementation authorization.

**IMPLEMENTATION IN PROGRESS — NO DEVELOPMENT JOB SUBMITTED — NOT ACCEPTED.**

## Public transliteration runtime preparation

The existing Mac ICU 78.3 is ineligible. A new isolated build uses the exact
ICU source commit `457157a92aa053e632cc7fcfd0e12f8a943b2d11`, with source archive
SHA-256 `629e7e6e309d1eeeb29c3eaf49e4f4532534fcf2613bcf0e51cd7850fa85a007`.
Every registry/rule/UCD asset in the approved specification is rehashed before
building. Source, compiler outputs and logs remain private outside Git.

The first public source check rejected the archive's internal ICU license
symlink. The helper now permits only that exact confined link; arbitrary links
remain prohibited. The failed preparation directory is preserved. This did
not involve protected input or a DEVELOPMENT execution.

ICU is compiled statically with its data from source. The narrow C++ bridge uses
the exact canonical IDs, forward direction, original-filter intersection and
whole-string transformation. ICU file-based data loading is disabled. Linux
linking binds the static ICU symbols locally; the lock binds bridge, i18n,
common and compiled-data archives, compiler/flags, source/spec hashes, platform,
build provenance and exact public synthetic vectors. No system ICU fallback.

The isolated Mac build reports ICU 77.1, Unicode 16.0.0 and CLDR 47 and passes
the exact public/synthetic vectors. Mac Python is 3.14.7/Unicode 16; it supports
synthetic function tests only, not the protected exact-runtime gate requiring
Python 3.14.3. Goethe's previously accepted Python runtime path was verified by
shell metadata. A separately scoped public-only compute preparation must build
and verify the Linux ICU lock before any protected DEVELOPMENT submission.

`scripts/stage10_build_runtime.py` has no address arguments, no protected data
reader and no geocoder capability. Linux invocation requires the shared Goethe
SLURM guard. Code reaches Goethe only through a clean exact pushed Git commit.
A preparation commit is not the complete Stage 10 executable or permission to
submit protected DEVELOPMENT before the remaining gates pass.

## Validation in progress

Initial focused validation passed 70 synthetic tests, including the actual
Mac ICU vectors, version/spec/data-hash faults, mixed/inherited scripts, native
preservation, Q5/Q6 coexistence, five NATIVE/four STANDARD/nine row hypotheses,
whole-line stripping, ambiguity/source-field vetoes, boundaries, context identity
and convergence. These do not replace the required complete repository/static
checks, final bounded self-review, Linux runtime verification or candidate review.

Operating budget remains UNSELECTED. The initial artifact must retain every
eligible Q1–Q6 intent; Q7 remains globally deferred with no machinery or rows.
Stage 0–9 science/history is unchanged. HOLDOUT remains sealed; production/Pelias
untouched; Stage 11 NOT STARTED. Stage 10 is not yet accepted.
