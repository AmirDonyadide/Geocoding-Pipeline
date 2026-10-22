# Stage 12 conditional warning policy: offline implementation candidate

This record covers the owner's separately bounded authorization to develop a
successor validator, versioned limitation audit and synthetic tests. It is not
activation, a design-freeze amendment, deployment approval, scientific
publication or permission for another probe. Frozen v1 remains effective for
the existing runtime. C, T and N remain UNSELECTED.

The starting checkout and recorded failed-probe executable both equal
`63f8fc769658656ec4eeef800d52c3091cc92ace`, on
`impl/stage12-pelias-retrieval`. They are separate provenance facts. The starting
tree was clean. This task adds five files; it changes no pre-existing tracked
file, accepted stage, public fixture or historical evidence. These additions
are uncommitted; the existing SHA does not identify the new implementation.

## Authorized scope and scientific limit

The conditional exception concerns only:

```http
GET /v1/search?boundary.country=DE&size=1&text=Berlin
```

and exactly one warning at `geocoding.warnings`:
`performance optimization: excluding 'address' layer`.

The owner accepts that excluding the address layer may reduce retrieval
coverage. This does not establish harmlessness, live-service determinism,
irrelevance of address evidence, or broader eligibility. Parsed city metadata
is neither an eligibility test nor proof of adequate retrieval. No request
parameter, header rule, query fixture, policy depth or candidate schema changed.

Job 1792588 remains FAILED under v1. No retained response was reclassified or
replayed in this implementation task. A byte-hash-only preservation check
matched the prior diagnostic inventory, including the unchanged diagnostic
record. Only request 10's raw response and receipts were locally available;
requests 1–9 remain represented by fixture definitions and aggregate reporting.

## Implementation boundary

[s12_warning_policy.py](../../src/safe_geocoding_pipeline/preprocessing/stages/s12_warning_policy.py)
is a new, standalone module. No existing probe, transport, runtime, extractor,
checkpoint or publication path imports it. It has no network, secret, file
write, deployment registration, activation, checkpoint or publication API.

`validate_offline` returns an immutable offline assessment after all checks
pass. It includes full canonical validation descriptor bytes, their SHA-256,
the input payload hash, original feature slices/structures and a versioned
limitation audit. It creates no candidate relation and no scientific execution
or projection identity. The audit explicitly denies scientific publication
authority and labels its hash as offline computation, not capture-time
attestation. Rejection returns no assessment or limitation audit.

All ordinary warning-free response checks remain available without exception
bindings, including outside the exception's request scope. Unknown, additional,
duplicated, malformed or out-of-scope warnings retain failure treatment. Top
warnings and all errors still require absence or an empty array.

The warning path checks exact request materialization, semantic identity,
method, size and header-name policy. It requires complete reviewed test
bindings for deployment/index/effective identities, authenticity, immutability,
drift, literal query-key echo values, ordered effective layers and sources.
The exact effective layer list must exclude address; returned layers must
belong to both that list and the declared vocabulary. All other response and
candidate checks still apply. No warning is removed or JSON body reserialized
to get past the frozen v1 validator.

**Real approvals remain unavailable.** There is no real-binding activation
interface. Synthetic acceptance requires both an explicit top-level invented
response marker and matching synthetic engine marker, a synthetic-only review
scope and the `synthetic` source vocabulary. Arbitrary hashes or affirmative
test booleans do not authorize an unmarked retained SAFE response. Synthetic
results remain offline assessments with no scientific authority. Test metadata
is independently invented; it is not operator evidence about SAFE.

To leave the v1 implementation byte-for-byte unchanged, the new validator
reuses its parser and scalar/envelope helpers and implements the small remaining
feature-validation traversal separately. Differential regression tests compare
ordinary behavior, feature order and exact slices with the unchanged extractor.
Runtime integration or a shared-helper refactor requires separate review.

## Rule and audit identities

[stage12_response_validation_v2.json](../scientific_assets/stage12_response_validation_v2.json)
contains the complete rule-bearing exception descriptor and an empty real
approval set. The descriptor embeds any supplied synthetic review content;
that content also participates in the applicable validation SHA-256. It pins
the frozen v1 validation and materialization descriptor hashes and binds the
limitation-audit descriptor hash. Exact matching alone is not the exception.

The shipped, unbound validation descriptor SHA-256 is:
`b73ba2e3ef7e33d86aacda5be4542df0701f5ed7fd0d3ec83a87b8d21505e6c1`.
A descriptor with synthetic review content has a different hash and accompanies
its returned assessment; it is not silently identified by the unbound hash.

[stage12_warning_limitation_audit_v1.json](../scientific_assets/stage12_warning_limitation_audit_v1.json)
defines the new offline assessment record. Its SHA-256 is:
`fc6c97b6892f0584600245aa2e12798492446ea9efb15b5d62cabdaa86ce8b55`.
The audit preserves the exact warning and effective layer list, identifies the
coverage limitation and synthetic-only scope, and makes no confidence,
accuracy, harmlessness or determinism claim.

Validation descriptor changes would change the frozen projection identity
through its validation-hash input, where a future authorized projection has
sufficient authentic capture/deployment provenance. Request materialization,
semantic identity and the size-1 retrieval policy remain unchanged. No missing
deployment binding is replaced by an invented scientific identity. Identity
framing tests use explicitly synthetic digests only. No real projection was
constructed and no historical attempt, raw byte, hash or outcome was rewritten.

## Validation and bounded review

[Successor tests](../../tests/test_stage12_warning_policy.py): **163 PASS**.
Together with unchanged v1 response and identity-contract tests: **273 PASS**.
The selected tests are network-free. The successor tests additionally reject
socket connection/DNS attempts. No full repository suite or loopback HTTP
transport tests were run for this bounded task.

Coverage includes unchanged v1 rejection; guarded synthetic-only acceptance;
ordinary warning-free behavior with absent/unapproved exception bindings;
request/mode/country/size/header boundaries; every missing review binding;
unapproved/malformed/extra bindings; missing/contradictory metadata; warning
list/type/location failures; HTTP/JSON/schema/geometry/coordinate/source/layer
and optional-field checks; zero results and overflow; original order and
duplicates; whole-response failure; absence of audit emission on rejection;
raw-byte recompression/replay; descriptor identity separation; and absence of
imports from existing runtime code. Duplicates are tested in ordinary responses
because the warning exception is limited to size 1.

The historical replay stopped at warning validation. These new downstream
tests use synthetic responses and do not establish that the retained SAFE
response passes downstream validation or projection.

Static checks: strict mypy PASS for all 150 source files; Ruff PASS across
source/tests/scripts; new Python formatting PASS. The repository Stage 12
validator passes its 17 frozen descriptors, five frozen design hashes, four
relations, 64 unchanged public fixtures, file/privacy surface and shell/SBATCH
syntax checks. New descriptor-byte equality is tested separately. Existing
tracked files and retained evidence match the starting baseline. Local document
links and whitespace checks pass.

| Review finding | Disposition |
|---|---|
| Four initial mypy narrowing errors after fail-closed assertions | Resolved with explicit type narrowing; full source mypy passes. |
| Out-of-scope materialization could expose a different static contract code | Resolved: request-scope mismatch retains RESPONSE_CONTRACT_INVALID. |
| Assessment needed the exact bound descriptor, not only its hash | Resolved: canonical descriptor bytes accompany every assessment. |
| Real deployment/index/effective/echo/layer approvals | Unavailable; fail closed, no activation interface. |
| Public capture-audit omission | **OPEN, separate existing implementation defect; not repaired or waived.** |

## Stop and remaining gates

The public capture-audit omission still requires separate authorized repair and
review before any later probe authorization. This limitation audit does not
replace network receipts or manufacture retrospective capture-time attestation.
Historical files remain immutable.

Separate review and authorization are required before activation or execution.
Actual deployment/index/effective behavior, echo adapter and layer inventory
must be supplied and approved; synthetic bindings grant none of that authority.
Any broader eligibility needs another explicit owner decision. No network,
SSH, retrieval, jobs, reruns, protected inputs, HOLDOUT, production, secrets,
merge, tag, checkpoint adoption or scientific publication occurred. Stage 13
and protected calibration remain NOT STARTED. C, T and N remain UNSELECTED.
