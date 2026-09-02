# Stage 07 — libpostal parsing and parser evidence

## Status

`STAGE_7_ACCEPTED` on DEVELOPMENT as an evidence-only projection. Production
Stage 7 and Stage 9 have not started.

## Purpose

Stage 7 parses each accepted Stage 6 exact candidate once with a pinned
libpostal bundle, preserves the exact ordered parser response, attaches trusted
country-applicability provenance and deterministic structural warnings, and
retains complete occurrence map-back.

## Scope and scientific boundary

The accepted output is parser evidence, not structured-address truth. A
successful parser call does **not** imply trustworthy components, semantic
correctness, geographic validity, or geocoding readiness. Raw component labels
and values are hypotheses/evidence; absence of a structural warning is not a
trust guarantee. The failed readiness statuses are not current fields or gates.
The stage performs no geocoding or external address-service call.

## Inputs

- Accepted Stage 6 registry and row map: manifest
  `e1da7b8ef04b65b1ece8e710720b57a8536841766fcf9de641f889b42eadd241`, logical
  bundle `2f6379c0cd5dc9654c03895cae6fdd48f3a7af528158c33e44d2030c816640b6`,
  and 51,779 exact candidates covering 69,747 occurrences.
- Immutable authoritative Stage 7 v1 parser output: manifest
  `98d4e9efd2e46bb725aa68d7c207065efb2089c59cdcba8bbe6ef3536d9f8f77`.
- Country eligibility artifact
  `a6ba110c0519873af898dcec0b5188a1db2659fe31aa619613cffcfdf82e499c`,
  audit manifest
  `8395b0b5f8e0943dc6dd1a9c9553ea571294fc7bbe61fc9b9b1e6e8fd1cea1a6`, and
  policy manifest
  `49dcda13e36d2692885efadffb606fa96207fc174a3385041c07af9bf0d1026a`.
- Accepted v2 contract/profile/schema:
  `stage07_parser_evidence_contract_v2`,
  `stage07_parser_evidence_profile_v2`, and
  `stage07_parser_evidence_schema_v2`.

## Outputs

There is one candidate-grain row for each Stage 6 candidate. Every Stage 6
registry field, v1 technical status, and ordered non-null list of exact raw
`{label, value}` components remains intact. V2 adds country provenance and
applicability, execution origin, and deterministic warning evidence. The
accepted map-back covers every standard/native occurrence. V2 made zero parser
calls: it projects the immutable v1 output and records
`REUSED_IMMUTABLE_STAGE07_V1`.

## Scientific contract

- Candidate text, ordered parser labels/values, duplicates, and empty output
  are exact evidence and are never silently repaired.
- Technical status is `PARSED_NONEMPTY` or `PARSED_EMPTY`; it is separate from
  applicability and semantic quality.
- Country applicability is derived from accepted source-row country provenance,
  not inferred from parser output.
- Structural warnings are deterministic parser-local diagnostics only.
- The rejected `COMPONENTS_READY` / `COMPONENTS_ABSTAIN` experiment is retired;
  neither status is published by the accepted contract.
- Candidate/occurrence map-back and exact Stage 6 preservation are mandatory.

## Implementation provenance

The authoritative v1 parser bundle is exact:

- libpostal commit `25099c506612b34b23b1bfe286ca6321fcf06f35`, implementation
  1.1.4, `libpostal.so.1.0.1` SHA-256
  `3e2aa3e23b62c22b77827b47d78692d49ae3d693c07ee7ad3763e9b97438cb5e`;
- pypostal commit `d6666a4f6a2ae0e7b83e037a35412f0f6b45c318`, package 1.1.11,
  with `six==1.17.0`;
- upstream default base/parser/language-classifier model assets at `v1.0.0`,
  model fingerprint
  `0b067a2697e9f90cef92c806701c08648a1f5127c17f0f3168ecaed186dc3293`;
- pypostal runtime fingerprint
  `ccc547bfdcaf391685cbb3285be9a02d84c28c7671dcafb4450d25c03920f7ff`;
- complete bundle fingerprint
  `f3c6db7e9f11ab75b2207be773e946d531dbba763008d9f7e5036d8c923dc2ae`
  and manifest
  `12a0080bff6b3ed2420847124eb918d91b7582214e3d4b037628bf5b9022340d`.

The accepted evidence-only v2 implementation is
`e684d84a8d68498ea790542143c8e125b3eb87b5`; reviewed candidate
`656a16d3d1f33cb152ace557c26f42df047bc7d6`; acceptance merge
`b36b995809fe902fe80af25856cb24786b795b1c`.

## DEVELOPMENT execution

Parser-bundle job `1760151` produced the pinned bundle. Authoritative v1 job
`1760221` parsed 51,779 candidates once and produced 51,774 `PARSED_NONEMPTY`,
five `PARSED_EMPTY`, zero crashes/unhandled failures, and 6,106,088 ordered
components. The maximum component count was 881,338; the accepted upstream
maximum candidate length was 25,920,495 code points. Validation job `1760226`
and qualitative-review job `1760494` followed.

Accepted v2 job `1763516` projected all 51,779 candidates and all 69,747
occurrences (34,822 standard, 34,925 native) with exact raw v1 and Stage 6
preservation, zero parser calls, and zero semantic-trust claims. Applicability
was 50,685 eligible, 721 missing-country, four partial-country, 355
invalid-country, and 14 ambiguous-country candidates. Warning status was
33,811 no warning detected, 16,874 warnings present, and 1,094 not evaluated.

## Validation and review

- V2 contract fingerprint:
  `c9561e6d08263b2a8824ff66f2a3aa8521e3ff880759abc14173cce440ced8a4`.
- V2 schema fingerprint:
  `b0e0e83ea3d929b7df8a6a5f64c2e8eb026395a917da90e97a98858b27e9ead2`.
- V2 logical dataset:
  `0f0706c1396803737f22845837753878bfd2e8b3f9af59b48cfcc1b8c5774530`.
- V2 manifest:
  `f58410877a7810562df7985c7316de7546d4dd8e11a647fd659c53a272e9c266`.
- Raw-preservation / warning-replay digests:
  `188db8540fbede26647ab713dbddbae5a51362e7f20e51f25ba61dc26861ef16` /
  `1dafa0c59d1d0925c4458763db64bb056ea9d1b813205b0dbf3e8babc7a7e072`.

The first review of candidate `318b70b00a52376b1b4fe865f41a789e2dd3feb9`
failed only on documentation/downstream-contract conflicts; evidence commit was
`6ea2ba2cef1a63f91a5a831755d8ecb0cd7d179f`. After documentation-only
correction, independent rereview job `1763656` at harness
`a2fa6e99e75336155363dc1f566b34cf3da8e0a8` passed exact candidate, complete
map-back, applicability/status consistency, warning replay, and zero parser or
trust claims. Controlled evidence SHA-256 is
`c0955062e5f407fdf8586f1811992a8a2e26e202295f467f41b5994b59bbc3b6`.

## Historical findings and rejected attempts

An early giant-candidate diagnostic job `1760156` saw 4 of 23 giant candidates
crash under a 48 GiB process ceiling. Supervisor job `1760182` parsed all 23
under 180 GiB, proving a resource-cap issue rather than an accepted parser
status; the final v1 run preserved all candidates without truncation.

The 120-case semantic review classified 30 plausible, 41 partial-but-usable,
seven questionable, 11 clear misparses, and 31 upstream-corrupt/unassessable.
Targeted job `1760818` confirmed genuine libpostal label or boundary errors in
14 of 18 investigated cases. This established the key conclusion: successful
parser output does not imply trustworthy structured address components.

Source inspection and country-context job `1761212` showed that the pinned
libpostal implementation nulls the exposed language/country options before
parsing; applicability therefore remains separate provenance, not a parser
quality claim. A bounded search for a second parser ultimately closed DeepParse
as `DEEPPARSE_INFRASTRUCTURE_PATH_NOT_JUSTIFIED`, with no protected inference
run.

The frozen semantic-readiness experiment used audit job `1763358` and
machine-selection job `1763433` (selection fingerprint
`c05cecf2aa9099045adc0d5c698c7e82a6bae187ae82222817f4bfb5264c2a89`).
Fresh review of 240 cases failed every central gate: READY precision was 85%,
clear-misparse leakage was 10%, and usable-parse abstention was 63/148
(42.5676%). The readiness statuses were therefore rejected and retired, not
accepted or reactivated.

## Accepted decision

Stage 7 was accepted only after the final contract represented libpostal output
as reproducible evidence, preserved country/technical/warning dimensions
separately, removed the failed semantic readiness gate, and passed independent
rereview with complete map-back.

## Known limitations

Libpostal evidence may contain material label and boundary errors, particularly
in native/non-Latin cases observed in DEVELOPMENT. Warning absence supplies no
semantic assurance. Stage 7 establishes neither component correctness,
geographic truth, query quality, nor match suitability.

## Downstream handoff

Stage 8 may losslessly project and index the exact candidate, raw ordered parser
evidence, country/applicability state, warnings, and occurrence map. It must not
promote parser components to truth, infer readiness, perform reference lookup,
or begin Stage 9.
