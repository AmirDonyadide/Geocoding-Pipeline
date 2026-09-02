# Stage 08 — Lossless address-evidence projection

## Status

`STAGE_8_ACCEPTED` on DEVELOPMENT. Stage 9 and production Stage 8 have not
started.

**Stage 8 science remained unchanged through every publication remediation.**
All four DEVELOPMENT executions produced the same logical dataset SHA-256:
`9c9d431c2c1b92712e0cb372f2661ad48f4fe8758dc0327d25aef90ab2c2d526`.

## Purpose

Stage 8 preserves the complete accepted Stage 7 candidate evidence, projects
the ordered nested libpostal response into a reversible long-form index, and
retains exact source-row and standard/native occurrence map-back.

## Scope and scientific boundary

This is a lossless evidence/index transformation. A SAFE parser-evidence name
is a mechanical mapping, not a verified component or hypothesis. Raw order,
duplicates, unknown labels, empty parses, applicability, technical status, and
warnings remain distinct. Stage 8 performs no reference lookup, semantic
correction, hypothesis generation, geocoding, scoring, or accepted-match
decision. It does not start Stage 9.

## Inputs

- Accepted Stage 7 candidate
  `656a16d3d1f33cb152ace557c26f42df047bc7d6`, manifest
  `f58410877a7810562df7985c7316de7546d4dd8e11a647fd659c53a272e9c266`, logical
  dataset `0f0706c1396803737f22845837753878bfd2e8b3f9af59b48cfcc1b8c5774530`,
  contract fingerprint
  `c9561e6d08263b2a8824ff66f2a3aa8521e3ff880759abc14173cce440ced8a4`, and
  schema fingerprint
  `b0e0e83ea3d929b7df8a6a5f64c2e8eb026395a917da90e97a98858b27e9ead2`.
- Accepted Stage 6 row map: manifest
  `e1da7b8ef04b65b1ece8e710720b57a8536841766fcf9de641f889b42eadd241`, logical
  bundle `2f6379c0cd5dc9654c03895cae6fdd48f3a7af528158c33e44d2030c816640b6`,
  row-map logical fingerprint
  `1ff9067c521ae93d28c300d7120a03c39681ce7830bf23b6619e2ca6129a4fe1`,
  and input binding
  `6ba224d6d24c3631aae8aac69f4a362bb054f01d9e3d09327ec6b0fdd85a0e7d`.

## Outputs

- `candidate_evidence`: one row per 51,779 Stage 6 candidate IDs, preserving
  the complete Stage 7 v2 row and adding mechanical index counts/status.
- `parser_component_evidence`: one row per 6,106,088 raw ordered parser
  components, keyed by candidate ID and zero-based ordinal.
- `source_candidate_map`: one row per 35,000 accepted source rows in exact
  order, with standard/native candidate map-back and upstream geography.
- `representation_occurrence_v1`: deterministic logical view of all 69,747
  occurrences (34,822 standard and 34,925 native).

The 20-label mapping is exact and case-sensitive; unknown labels remain raw and
unmapped rather than being dropped or guessed.

## Scientific contract

The frozen identities are `stage08_address_evidence_projection_contract_v1`,
`stage08_address_evidence_projection_profile_v1`,
`stage08_address_evidence_projection_schema_v1`,
`stage08_semantic_classification_v1`, and
`stage08_libpostal_label_mapping_v1`. Nested-to-long and long-to-nested
reconstruction must be exact. Candidate, component, source, and occurrence
grains remain separate. Hypothesis, reference-evidence, geocoder-result, and
accepted-match classes are prohibited outputs.

Publication follows Policy A: adopt a completed final tree only after the
temporary tree is durable, the rename and parent-directory fsync are reconciled,
the final tree is fully reopened, the outcome is constructed, umask is restored,
and a final nofollow device/inode ownership check is the last rejection-capable
operation. Post-commit presentation failure cannot demote a committed result.

## Implementation provenance

- Final accepted executable:
  `c04cb97214a9f1e5d2b80512c756400321eefa80`.
- Final accepted candidate:
  `231cdbf9db755fb56486c46b3b3faa02f5b5f3b6`.
- Acceptance merge:
  `ce9e9cac60ba1a767043a7bf09bbf0ad2589f3b3`.
- Corrected independent review commit:
  `f8a456f5c939c4061d2be232fd5037010b7a88c8`.
- Runtime: Python 3.14.3, Unicode 16.0.0, PyArrow 25.0.0, DuckDB 1.5.5.

## DEVELOPMENT execution

Authoritative job `1764273` completed with exit `0:0` in 16 minutes 8 seconds,
using four requested CPUs and 32 GiB memory; MaxRSS was 1,789,612 KiB. It
published 51,779 candidates, 6,106,088 component rows, 35,000 source rows, and
69,747 occurrences. All 6,106,088 components were mapped; dangling and
unmapped components, component-count mismatches, occurrence-count mismatches,
source-map mismatches, and upstream-preservation mismatches were zero.

The accepted manifest is
`2a50bd8c066552c9cb7505ed2d6071f1ee36161b9a2cc07f3ed364cf00237827`.
Publication contained 26 candidate shards, 13 component shards, nine source-map
shards, owner-only `0700` directories and `0600` files, and no symlinks.

## Validation and review

- Contract fingerprint:
  `8b3c530e714177fe2c30a97d61dcc199b7f9efba58f3c17a291b817af0f24d5e`.
- Schema-bundle fingerprint:
  `6c8ebecd24c495dbe2ce32125ac1cb89c4a9de4905c786b774d10ad728ed392f`.
- Label-mapping fingerprint:
  `b18167d2d5c1f1402d1bb0e92559befb92418f5f4f34df885596778a11d5c09d`.
- Relation schema fingerprints (candidate/component/source/occurrence):
  `b1d56ea33c22e639ab798581c5533b1a0981ef5452dce5cb24e168d4a684bd4c`,
  `112fb17c2afac27b941d30f57fe5c1bb2e46d779f89bdf2efbd8c719a3b87ccf`,
  `884eb8456fc6ee84a699a9e2371224e5c709363daac0febc5975f911bf48c398`,
  `df1cac9b6d9f86ffb76d1ea744fc64f15149c9e33fef980213286b91b2d02038`.
- Relation logical fingerprints (same order):
  `11fbd6e6e32b7dcb293c5918e9d02f19badf52cc9d9c108c910d17d92b8645aa`,
  `8b1af702c51bd40edc22302778ae2fda5851d9af8af39636a9a9733a94916030`,
  `c4c9f8b3f425f93a1d61880f720136d1f71580871338c9a920c9abeffa93ee32`,
  `57aa3dcc5caf796fbbe15b3c0df655a8f34902107ce9fed3fbb6aaf38e158774`.

Corrected independent review job `1764376` completed at harness SHA-256
`4e728ca7cf90b270c892da49f9d3cfa56b2fb2e71b4aac6b54526a0380257586`.
Evidence SHA-256
`9fe9420779a96f8c3663e8876cb3206a72ca15931bdfa23105d13dddf7546de0`
records exact scientific, reversibility, source-map, publication, permission,
privacy, and prohibited-activity checks: candidate defects = 0 and
infrastructure-incomplete checks = 0.

## Historical findings and rejected attempts

The publication lineage is retained concisely and without relabeling failures:

1. Original executable `a2544401b4b699f6c020970f3507a2ae432746c5`, job
   `1763747`, candidate `adde81d2237e99993222994ce56efb0d74f7c2d3`, and
   manifest `bdf86738fb071e38b2ad090f4627a821149352fb1490e62b76e5819aa915bcf9`
   passed scientific reconciliation but failed review because success-marker
   publication preceded the final prepublication reopen and Stage 8/9 tool
   wording was stale.
2. First remediation executable
   `bd89a032eb6fcf16a7515e0bd2991165d87246b1`, job `1763984`, candidate
   `fdf2f8c78781a6bdb5dad637af5954ae81cf331d`, and manifest
   `d521240b42a40b9c1408f0f7241583bc76b7779e4107179e73fdcb7c7a69e119`
   fixed ordering. Rereview found a post-effect rename defect: rename could
   succeed and then raise before Python-side state reflected the final tree.
3. Second remediation adopted Policy A in executable
   `bdea7232a3f92ebd381be87610b753b8e4c35481`. Job `1764219`, candidate
   `70e3de9536aee7074e27018d39e0164f3a2200ae`, and manifest
   `346ea27ad60c1e00ef29c1126b2744f38049c1fa7d062647ab6df04e3330dee6`
   reconciled the rename outcome. Rereview then found two terminal defects: a
   post-commit CLI reporting/stdout failure returned nonzero, and ownership was
   not rechecked after parent fsync and final reopen.
4. Final executable `c04cb97214a9f1e5d2b80512c756400321eefa80` separated
   publication from presentation and made the final ownership recheck the last
   rejection-capable operation. Job `1764273` produced the accepted artifact.

All four jobs have the identical logical dataset SHA-256 shown in Status;
publication engineering changed, Stage 8 science did not.

Review job `1764372` exposed review-harness defect `RH-001`: it incorrectly
required device/inode equality across separate jobs. It stopped before row
review, found no candidate defect, and is classified **REVIEW-ONLY**. Its
evidence SHA-256 is
`5b7a2906e8d97f9268f09aa8f1f22f6a3d45480d2ea10ff0344606d82d0f25d9`.
The corrected harness removed that invalid cross-job assumption and produced
the successful job `1764376` result.

## Accepted decision

Stage 8 was accepted because the exact lossless projection and all scientific
fingerprints remained stable, the final publication contract closed every
reviewed failure mode, and corrected independent review found zero candidate
defects. `STAGE_8_ACCEPTED` applies to exact candidate
`231cdbf9db755fb56486c46b3b3faa02f5b5f3b6` only.

## Known limitations

The projection does not validate parser semantics or create address
hypotheses. It does not establish geographic truth, reference agreement,
geocoder suitability, or match granularity. External kill/power-loss behavior
beyond the documented commit boundary is not newly guaranteed.

## Downstream handoff

A separately designed and authorized Stage 9 may consume the exact evidence
relations and map-back. It must preserve source/parser evidence, treat mapped
components as hypotheses/evidence only, and must not assume Stage 9 has already
started. No Stage 9, HOLDOUT, production Stage 2+, or geocoding work is
authorized by Stage 8 acceptance.
