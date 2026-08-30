# Stage 7 libpostal context-provenance diagnostic

The controlled decision is
`CONTEXT_AWARE_LIBPOSTAL_NOT_SUFFICIENT`. The frozen Stage 7 DEVELOPMENT
candidate remains `STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY`.

## Exact API finding

Pinned pypostal commit
`d6666a4f6a2ae0e7b83e037a35412f0f6b45c318` exposes the exact wrapper
signature `parse_address(address, language=None, country=None)` and forwards
both keywords. Its bound `postal/parser.py` SHA-256 is
`5fe25a6a23ed4845a6a22d25836c27e3651e603a64668b44f2a290178e306d02`.

Pinned libpostal commit
`25099c506612b34b23b1bfe286ca6321fcf06f35` exposes exactly `language` and
`country` in `libpostal_address_parser_options_t`. The bound header SHA-256 is
`d537b0709c4882919a3d6209b952c30ea072cf0ee90f3eeff655eb8c512df6bb`.
However, the exact parser implementation explicitly assigns both parameters to
`NULL` immediately before parser-context construction. Its source SHA-256 is
`a129328e4ac2301ccffdc092811a09663f01802e97c8be780c704e51a0e59222`.
The source documents that this parser was trained without language/country and
intentionally ignores the options until corresponding models exist.

The wrapper therefore exposes two syntactic arguments, but the frozen native
parser bundle has zero effective context parameters and zero applicable
context-aware configurations. SAFE did not fabricate an option, append
metadata, modify a candidate, or switch parser/model.

## Controlled execution

Metadata-only SLURM job `1761212` ran exact pushed implementation
`4d0569eecbfc2b2a1e6a0ce4782036c9ccb1406d` against parser-bundle fingerprint
`f3c6db7e9f11ab75b2207be773e946d531dbba763008d9f7e5036d8c923dc2ae`.
It completed in 17 seconds with exit `0:0`, 16 GiB requested memory, and zero
stderr bytes. The protected manifest SHA-256 is
`0ab71e71ae6be727699054378bbdc5891107c6d51f5e7343d55edcb4057985ab`;
the sanitized aggregate SHA-256 is
`9eadaac538f451f185a3da7b029f09ab972347f907b839b13582447aa29694b3`.

The job made zero parser calls and inspected zero candidate strings. It read
only accepted occurrence IDs and the explicit accepted
`stage04_lower_country_iso_code` provenance field. It did not infer country or
language from text, script, representation, parser output, or external data.
The owner-authorized paired LLM comparison was not exercised because no
variant output existed.

Independent metadata readback verified the exact five-file output topology,
`0700`/`0600` permissions, terminal-manifest linkage, all recorded SHA-256
identities, 51,779 candidate-audit rows, 120 selection-audit rows, schemas that
exclude candidate text and country values, and all aggregate reconciliations.

## Accepted provenance audit

Across all 51,779 accepted Stage 6 candidate IDs:

- 50,761 have one explicit usable country on every occurrence;
- 1,000 have no usable explicit country;
- four have one usable country but also missing or invalid occurrence context;
- 14 have conflicting explicit countries and are
  `CONTEXT_AMBIGUOUS_FOR_PARSE_ONCE`;
- 725 candidates have at least one missing-country occurrence, totaling 1,263
  occurrences;
- 279 candidates have at least one invalid-country occurrence, totaling 283
  occurrences;
- 17,882 candidates occur in both STANDARD and NATIVE provenance; and
- seven have country-context availability or values that differ between their
  STANDARD and NATIVE occurrences.

The accepted Stage 6 row map has no explicit language field. Consequently all
51,779 candidates have no explicit language context; zero have a unanimous
explicit language, zero have conflicting explicit languages, and zero have a
uniquely determined country-plus-language combination. No language was inferred.

For the immutable 120-case selection, 115 candidates have unanimous explicit
country context and five have no usable country context. There are no partial
or conflicting-country candidates and no STANDARD/NATIVE context differences
in the selection. All 11 prior clear misparses and all seven questionable
cases have unanimous explicit country metadata. Thus trusted country
provenance availability would not have blocked testing the 18 targets if the
parser option were effective; the pinned parser implementation itself blocks
the experiment.

## Predeclared quality questions

No context variant was scientifically executable, so structural-change and
paired semantic comparisons are not defined:

1. Clear-misparse corrections by configuration: not applicable.
2. Repairs among six boundary failures: not applicable.
3. Repairs among five label-only failures: not applicable.
4. Material regressions among the 109 non-clear controls: not applicable.
5. Cross-script improvement: not applicable.
6. Improvement dependent on ambiguous context: none observed because no
   variant ran; independently, 14 population candidates are context-ambiguous,
   while none of the 120 selected candidates is.
7. New failures in previously acceptable parses: not assessed because no
   context-aware parse exists in this bundle.

Deterministic variant repeats, label-error repair rate, boundary-error repair
rate, target regressions, control regressions, and script-stratum effects are
all `NOT_APPLICABLE`, not zero-effect estimates from a comparison.

## Scientific conclusion and next option

Context-aware libpostal is not a sufficient next Stage 7 remedy under the
frozen bundle because its only exposed context arguments are intentionally
ignored. Passing them would produce a nominally different call while leaving
the native scientific semantics unchanged; such a comparison would be false
evidence.

If a future parser genuinely uses country context, the 14 conflicting
candidate IDs cannot retain a single context-aware parse-once result: a
candidate-plus-context identity would be required for their occurrences. That
would not by itself resolve the 1,000 candidates with no usable context or the
four with partial occurrence context. This diagnostic does not change the
Stage 6 key.

The recommended next owner option is a controlled, non-authoritative
comparison of a second mature pinned offline parsing strategy on the existing
120 cases, preserving the current raw libpostal result and using predeclared
net-improvement/regression criteria. A conservative component-readiness or
abstention design is the fallback if no parser materially repairs the known
boundary errors without systematic regressions. Neither option is implemented
here.

The authoritative Stage 7 registry, contract/profile, parser bundle, Stage 6
science, and original qualitative classifications remain unchanged. No
authoritative rerun, independent review, Stage 8 work, HOLDOUT access,
production access, geocoding, web/API call, or merge occurred.
