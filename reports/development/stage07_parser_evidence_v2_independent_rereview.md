# Stage 7 parser-evidence v2 independent rereview

Date: 2026-09-01

Reviewed candidate: `656a16d3d1f33cb152ace557c26f42df047bc7d6`

Verdict: `STAGE07_EVIDENCE_ONLY_INDEPENDENT_REREVIEW_PASS`

## Scope and independence

This rereview examined the corrected Stage 7 evidence-only DEVELOPMENT
candidate without modifying it. The candidate was reviewed from a clean exact
Git checkout. No libpostal call, Stage 8 work, geocoding, HOLDOUT access,
production access, DeepParse execution, or Senzing execution occurred.

The independent bounded verifier is committed separately from the candidate at
`a2fa6e99e75336155363dc1f566b34cf3da8e0a8`. Goethe job `1763656` ran that
verifier against the existing immutable Stage 6, Stage 7 v1, country-
eligibility, and Stage 7 v2 artifacts. It completed in 3 minutes 49 seconds
with 32 GiB requested memory and 2,114,228 KiB batch MaxRSS. The controlled
aggregate evidence SHA-256 is
`c0955062e5f407fdf8586f1811992a8a2e26e202295f467f41b5994b59bbc3b6`.

Two earlier independent-verifier attempts are retained as review provenance.
Jobs `1763560` and `1763561` each stopped after six seconds because the new
review harness compared, respectively, Arrow physical scalar types instead of
logical values and uppercase rather than the accepted lowercase country-code
provenance. Neither reached candidate comparison or produced scientific
evidence. The corrected harness added regression tests for both reviewer
defects before job `1763656`.

## Previous blocking findings

The remediation from the initially reviewed candidate
`318b70b00a52376b1b4fe865f41a789e2dd3feb9` to the corrected candidate changes
only tracked documentation and sanitized report surfaces. No Stage 7 source,
tests, execution assets, contract implementation, or protected artifacts were
changed.

Repository-wide current-state review confirms:

- `COMPONENTS_READY` and `COMPONENTS_ABSTAIN` are not a current downstream
  semantic-trust gate;
- raw parser labels and component boundaries are hypotheses/evidence only;
- absence of a structural warning does not imply semantic or geographic trust;
- exact whole-string STANDARD and NATIVE candidates remain available in
  parallel with parser evidence;
- the proposed Stage 8 handoff must evaluate hypotheses and may not promote
  libpostal output to source truth merely because no warning fired; and
- current status surfaces consistently identify the evidence-only candidate as
  requiring independent rereview.

References to the failed readiness rule remain only where needed for immutable
historical evidence, diagnostics, implementation provenance, or tests. The
failed fresh validation remains `STAGE07_V2_FRESH_DEVELOPMENT_VALIDATION_FAIL`;
it was not reclassified as success.

## Independent controlled replay

Job `1763656` established:

- candidate rows: 51,779;
- exact Stage 6 field preservation: PASS;
- exact immutable Stage 7 v1 status and ordered raw-component preservation:
  PASS;
- occurrence map-back: 69,747 total, comprising 34,822 STANDARD and 34,925
  NATIVE, with zero missing and zero non-unique mappings;
- applicability reconciliation: 50,685 eligible, 721 missing country, 4
  partial country, 355 invalid country, and 14 ambiguous country;
- technical status reconciliation: 51,774 `PARSED_NONEMPTY` and 5
  `PARSED_EMPTY`;
- country/applicability and technical-status consistency: PASS;
- structural warnings recomputed twice and matched exactly for every applicable
  row: PASS;
- raw-preservation digest:
  `188db8540fbede26647ab713dbddbae5a51362e7f20e51f25ba61dc26861ef16`;
- warning-replay digest:
  `1dafa0c59d1d0925c4458763db64bb056ea9d1b813205b0dbf3e8babc7a7e072`;
- parser calls made by the v2 projection: 0; and
- semantic-trust claims in the v2 artifact: 0.

The verifier independently bound the published artifact to:

- implementation `e684d84a8d68498ea790542143c8e125b3eb87b5`;
- contract fingerprint
  `c9561e6d08263b2a8824ff66f2a3aa8521e3ff880759abc14173cce440ced8a4`;
- schema fingerprint
  `b0e0e83ea3d929b7df8a6a5f64c2e8eb026395a917da90e97a98858b27e9ead2`;
- Stage 7 v2 manifest SHA-256
  `f58410877a7810562df7985c7316de7546d4dd8e11a647fd659c53a272e9c266`;
- the exact Stage 6 manifest, Stage 7 v1 manifest, frozen parser-bundle
  fingerprint, eligibility artifact, contract/profile/schema metadata, and
  lineage recorded by the publication.

The publication was reopened in bounded 32-row batches while retaining at most
one nested parser result for comparison. The independent run used about 2.02
GiB MaxRSS, and the published manifest remained byte-identical after review.
Controlled output permissions were `0700` for the directory and `0600` for the
aggregate evidence file.

## Static, reporting, and privacy review

The Stage 7-focused suite passed 153 tests. Ruff, strict mypy for the review
code, shell syntax, JSON parsing, Markdown-link validation, diff checks, and
tracked-data/privacy checks passed. The broad local-safe suite passed 571 tests;
its 24 failures were the repository's deliberate Python-runtime pin checks
because the local review environment is Python 3.14.7 rather than the pinned
3.14.3, not Stage 7 failures.

Sanitized candidate reports match the controlled counts, bindings, status
vocabulary, manifest identity, zero-parser-call claim, and zero-semantic-trust
claim. The independent evidence contains aggregates and fingerprints only and
remains owner-only and untracked on controlled infrastructure.

## Conclusion and next action

No material defect was found in the corrected evidence-only candidate. The
next action is an explicit scientific-owner acceptance of exact candidate
`656a16d3d1f33cb152ace557c26f42df047bc7d6`. Only after that acceptance may the
canonical Stage 7 candidate branch at that exact SHA be integrated into `main`
with ancestry preserved. The independent-review harness branch is evidence,
not the branch to merge. Starting Stage 8 still requires separate explicit
authorization.

`STAGE07_EVIDENCE_ONLY_INDEPENDENT_REREVIEW_PASS`
