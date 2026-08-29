# Stage 7 targeted parser-quality root-cause diagnostic

Verdict remains `STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY`. The controlling
scientific conclusion is
`MIXED_ROOT_CAUSES_REQUIRING_TARGETED_STAGE07_DESIGN_CHANGE`.

## Scope and binding

The diagnostic used only the 11 `CLEAR_MISPARSE` and seven
`QUESTIONABLE_PARSE` rows from the immutable 120-candidate qualitative
selection. The selection fingerprint remained
`1507900b27e4503eb33836c8465217092e9ffb8de2f1b6ef05026690be11a844`.
It did not regenerate the selection or qualitative review and did not rerun
the authoritative 51,779-candidate parse.

Job `1760818` ran implementation
`5f324fd8bbeacc1b5c9de1d249e6429796ed2c82` against parser bundle
`f3c6db7e9f11ab75b2207be773e946d531dbba763008d9f7e5036d8c923dc2ae`.
It completed in 00:01:13 with 2,140,712 KiB MaxRSS. The protected diagnostic
manifest SHA-256 is
`bcba55a56a9530a712b53caf94118affc4556abe25571efc8eefd226e901d858`;
the sanitized aggregate SHA-256 is
`62f6412e58191d3311119a8f2ed9244a174de5e7b432f7ded3dfef10e645d7a1`.

The first attempt, job `1760707` at
`1c781eb261b7361220563f425e0306ccbd9345ce`, failed before scientific
execution because unmanifested Python bytecode caches had appeared in the
otherwise frozen bundle tree. Fail-closed validation rejected that mutation.
The failed attempt remains preserved. The successful replacement used a new
private byte-identical bundle view that excluded only those runtime caches;
the source bundle and scientific parser/model assets were not changed.

## Root causes

All 18 exact reparses matched their authoritative ordered output; there were
zero parser crashes and zero worker restarts. Root-cause codes may overlap:

- `TRUE_LIBPOSTAL_LABEL_ERROR`: 6;
- `TRUE_LIBPOSTAL_BOUNDARY_ERROR`: 9;
- `TRANSLITERATION_OR_ROMANIZATION_DAMAGE`: 3;
- `AMBIGUOUS_BUT_INFORMATION_PRESERVED`: 4; and
- all other taxonomy codes: 0.

Fourteen distinct cases have a true libpostal label or boundary error. Three
cases show upstream transliteration/romanization damage; one of those also has
a true parser error. No selected case was attributed to multi-record input,
Stage 5 reconstruction, Stage 3/4 cleaning, or source corruption.

## Clear-misparse answers

For all 11 clear misparses, the important reviewed information was present in
the Stage 6 candidate, and Stage 7 retained that exact candidate. The ordered
component values preserved the complete lexical/numeric input stream in all
11. Five cases are semantic-label errors without a reported boundary error;
six have within-word/token boundary splitting. No information was lost from
the Stage 7 row because the exact Stage 6 candidate remains alongside the raw
parse.

That lossless row preservation does not make the components safely mappable.
A fixed Stage 8 label mapping could deterministically recover zero of the 11
clear cases without guessing; all 11 require more than straightforward label
mapping. None of the clear cases was classified as upstream-caused.

Across all 18 cases, component values preserved the complete lexical/numeric
stream in 18 and the exact non-whitespace stream in 12. The other six had only
non-lexical mechanical omissions; the exact candidate still remained present.
Stage 8 recoverability was: zero deterministically recoverable by fixed label
mapping, 14 not safely recoverable without guessing, two requiring upstream
non-Stage-8 repair, and two inconclusive.

## Script and provenance clustering

All 11 clear misparses are NATIVE, single-script candidates. They span five
non-Latin strata: Han 3, Hangul 3, Lao 2, Thai 2, and Hebrew 1. The seven
questionable cases comprise Latin 4, Greek 1, Han 1, and mixed-script 1; their
provenance is NATIVE 3, STANDARD 3, and BOTH 1.

The explicit `SCRIPT_SPECIFIC_PARSER_WEAKNESS` reason-code count is zero
because the abstract comments did not establish script causality case by case.
Nevertheless, the observed clear-error concentration is not isolated to one
record or one script: it covers multiple native non-Latin script strata, with
both label and boundary failure modes.

## Scientific conclusion and options

The frozen context-free parser is deterministic and lossless at the Stage 7
row level, but the evidence is not merely a Stage 8 column-mapping problem.
Fourteen of 18 risk cases contain genuine parser errors, including six
boundary failures among all 11 clear cases. Straightforward Stage 8 mapping
cannot be assumed to reconstruct the intended components safely.

Ranked options for a new owner scientific decision, from least to most
invasive, are:

1. Define a conservative Stage 7 parse-quality/eligibility outcome that keeps
   raw libpostal output and the exact candidate but prevents structurally risky
   parses from being treated as component-ready. Any detection rule requires a
   new controlled diagnostic and must not be fitted only to these 18 cases.
2. Run a controlled, non-authoritative comparison of explicitly specified
   libpostal language/context options on these 18 cases plus deterministic
   controls. Context must come from approved upstream provenance and must never
   be inferred or silently appended.
3. Evaluate a second pinned offline parsing strategy only for the affected
   classes, preserving the current libpostal result and defining a
   deterministic, reviewable selection/abstention rule.
4. Reconsider upstream transliteration policy separately for the three damaged
   cases; this cannot resolve the 11 clear native parser failures by itself.
5. Replace the global Stage 7 parser/model strategy only after a controlled
   multilingual comparison demonstrates a material net improvement without
   new systematic regressions.

No option was implemented. Stage 6 was unchanged. HOLDOUT, production, Stage
8, independent review, geocoding, and merge to main were not started.
