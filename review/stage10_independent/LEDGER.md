# Stage 10 independent review ledger

Pre-submission ledger. Complete static review and protected execution are separate
evidence sources; population impact remains pending. Ordinary findings do not
stop the remaining review. Candidate code/artifact will not be repaired here.

## Candidate defects

### C01 — Required visible parser-geography exclusion is absent

- Classification: **CANDIDATE_IMPLEMENTATION**; severity **moderate (P2)**.
- Invariant: frozen Q4 field provenance and visible exclusion decisions.
- Evidence: frozen `docs/stages/STAGE10_QUERY_FAMILIES.md`, Q4 policy, requires
  `PARSER_ONLY_FIELD_EXCLUDED` for parser geography exclusion. The executable's
  `s10_query_families._structured` never emits that code; `region` records only
  `ADMIN_LEVEL_NOT_ESTABLISHED`, and omitted country text has no parser exclusion
  reason. Searching the executable finds the name only in the reason vocabulary.
  Independent synthetic complete-oracle runs reproduce missing reasons in all
  four country-eligible fixture contexts, including contexts with parser geography.
- Effect: consumers cannot recover the required explicit exclusion decision from
  the field-decision relation. This is not evidence that parser values populate Q4
  or that source-anchored query content is incorrect.
- Protected checks: `q4_missing_visible_parser_geography_exclusion` and the
  narrower `q4_missing_exclusion_with_parser_geography`. Both aggregate counts
  must be reconciled before the final verdict. The broader unconditional-policy
  count must not be misrepresented as the number with observed parser geography.
- Regeneration: correcting decision rows requires a new immutable candidate
  relation/artifact and its dependent hashes. No in-place repair is permitted.
- Disposition: unresolved; static defect established, DEVELOPMENT extent pending.

### C02 — Registration names differ from the frozen publication interface

- Classification: **CANDIDATE_PUBLICATION**; severity **moderate (P2)**.
- Invariant: frozen Stage 10 publication adapter namespace and complete input
  binding field, `STAGE10_MULTI_HYPOTHESIS_QUERY_GENERATION.md` publication section
  at design freeze `1443bb3b3c1bb50220bf38231e01552c66c4eaee`.
- Evidence: that section specifies namespace `STAGE10_DEVELOPMENT_QUERY_PLAN`
  and `stage10_input_binding_sha256`. Executable `s10_query_publication.py` uses
  `STAGE10_DEVELOPMENT_QUERY_HYPOTHESES` and `stage10_input_sha256`. The committed
  sanitized registration `stage10_development_registration_1774362.json` confirms
  both differences. No subsequent documented authorization changing these frozen
  names was found. Candidate validation accepts its own adapter constants and
  therefore does not detect this design/interface discrepancy.
- Effect: a consumer of the frozen adapter cannot match the namespace or retrieve
  the required key. The input digest is present under the different key; this
  finding alone does not establish lost input binding, unsafe sealing, corruption,
  or a stale reservation. Those checks continue independently.
- Protected checks: `publication_frozen_namespace`,
  `publication_frozen_input_binding_key`, plus independent registration hash and
  physical inventory verification against the reporting identity.
- Regeneration: requires owner disposition and a new conforming immutable
  registration/artifact. The names alone do not intrinsically require repeating
  scientific query construction, but the existing committed artifact cannot be
  edited or accepted as conforming by this reviewer.
- Disposition: unresolved; static and portable-registration evidence established,
  exact controlled registration verification pending.

## Informational ledger

| ID | Observation / invariant | Evidence and remaining work | Severity; regeneration |
|---|---|---|---|
| I01 | Country abstention is structural, not invalidity | Frozen row-local Q01 gate permits zero output. Independently reconcile all 1668 contexts and all six decisions. | Informational; none if reconciled |
| I02 | Q5 and Q6 coexistence is permitted, not required | Zero observed coexistence is not a defect. Independent eligibility and synthetic safety checks retain both families. | Informational; none |
| I03 | Q5 diagnostic evaluation order | When a target is both uncorroborated and ambiguously alignable, the candidate may stop on missing corroboration first. Frozen reasons describe the actually evaluated failure. Independent oracle records this narrow overlap separately and still requires safe suppression. Actual overlap count pending. | Informational unless output/safety mismatch; none for order alone |
| I04 | Replays are deterministic reproducibility evidence | Exactly three full same-code comparisons are frozen; receipts and static call path are reviewed. They are supplemented by independent oracles, not counted as independent scientific proofs. | Informational; none |
| I05 | Performance measurements have limited scope | Publication time contains replays; sampled WAL is not continuous high-water telemetry; DEVELOPMENT throughput does not establish production capacity. Candidate report states these limits. | Informational; none |
| I06 | Local runtime coverage limit | 24 local candidate tests require unavailable exact ICU assets and were skipped. Goethe review must verify exact lock/assets/dependencies and outputs. No local protected workaround exists. | Informational; none if guarded runtime validates |
| I07 | Bounded independent witness certificate review | At most 40 context selections, complete streams within each; full-population identifiers, contents, source-line certificates, reference policies and checkpoint equality checked separately. No claim of exhaustive independent reference-certificate reconstruction. | Informational; none |
| I08 | Reporting and budget interpretation | Report disclaims geocoding accuracy/validity/precision/recall; no implication that abstention or Stage 9 contradiction means an invalid address. Scientific budget stays UNSELECTED. Protected budget checks pending. | Informational; none if reconciled |

## Review-harness defects resolved before submission

These are reviewer-created issues, never candidate defects. No protected job has
failed from them; all corrections are confined to review files.

| ID | Evidence / review invariant | Correction and validation | Severity; candidate regeneration |
|---|---|---|---|
| R01 | Prototype Python DuckDB UDF depended on unavailable local NumPy | Replaced with bounded Arrow batches; no environment modification; complete synthetic oracle passes. | REVIEW_HARNESS, low; no |
| R02 | Temporary tables were invisible across independent cursors; SQL aliases collided with reserved words | Reviewer tables made persistent only in the private review DB; aliases corrected; complete scientific and checkpoint fixtures pass. | REVIEW_HARNESS, moderate; no |
| R03 | Initial independent registration digest used the wrong protocol domain | Corrected to accepted `SAFE:publication-commit:v2` plus NUL; independently recomputed portable registration test passes; candidate primitive unchanged. | REVIEW_HARNESS, moderate; no |
| R04 | Initial absence fixture inherited positive GeoNames evidence | Explicit NOT_FOUND and NOT_EVALUABLE fixtures now assert zero negative gating; 25 harness tests pass. | REVIEW_HARNESS, low; no |

There are no unresolved reviewer-code defects known at submission. This is not a
claim that the protected harness execution has completed. Any execution defect
must be appended here, fixed only in the harness, committed/pushed and reconciled
without changing the candidate or abandoning the remaining scientific review.

## Pending final disposition

All 22 meaningful review areas must be completed before PASS/FAIL. False checks
must be assigned to candidate defects, resolved harness defects, or explicit
informational findings using actual evidence. No ordinary candidate defect is
permission to stop early. Privacy/scope violations, destructive mutation or
unrecoverable corruption invoke the owner's immediate-stop rule.

HOLDOUT remains sealed; production/Pelias untouched; Stage 11 NOT STARTED;
Stage 10 NOT YET OWNER ACCEPTED.
