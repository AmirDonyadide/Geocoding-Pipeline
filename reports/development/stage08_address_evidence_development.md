# Stage 8 repaired DEVELOPMENT address-evidence materialization

## Candidate result

Current verdict:
`STAGE08_ADDRESS_EVIDENCE_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REREVIEW`.

Stage 8 DEVELOPMENT job `1763984` completed `0:0` in 15m36s at repaired
executable `bd89a032eb6fcf16a7515e0bd2991165d87246b1`. It published one
immutable candidate with manifest SHA-256
`d521240b42a40b9c1408f0f7241583bc76b7779e4107179e73fdcb7c7a69e119`
and logical dataset SHA-256
`9c9d431c2c1b92712e0cb372f2661ad48f4fe8758dc0327d25aef90ab2c2d526`.
Every frozen validation field passed. This is DEVELOPMENT candidate evidence,
not independent rereview or Stage 8 acceptance.

The immutable controlled output is:

`/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage08/development/stage08_development_20260902T080150Z_bd89a032eb6f`

## Exact reconciliation

| Evidence | Frozen expectation | Repaired materialization |
|---|---:|---:|
| Exact candidates | 51,779 | 51,779 |
| Ordered parser components | 6,106,088 | 6,106,088 |
| Source rows | 35,000 | 35,000 |
| Representation occurrences | 69,747 | 69,747 |
| STANDARD occurrences | 34,822 | 34,822 |
| NATIVE occurrences | 34,925 | 34,925 |
| `PARSED_NONEMPTY` | 51,774 | 51,774 |
| `PARSED_EMPTY` | 5 | 5 |
| Mapped component rows | 6,106,088 | 6,106,088 |
| Unmapped component rows | 0 | 0 |
| Distinct unmapped labels | 0 | 0 |
| Dangling components | 0 | 0 |
| Component-count mismatches | 0 | 0 |
| Occurrence-count mismatches | 0 | 0 |

All 51,779 candidate IDs and complete accepted Stage 7 fields are preserved.
The ordered long relation reverses exactly to the authoritative nested Stage 7
evidence. Source identity, STANDARD/NATIVE slots, applicability, technical
provenance, warnings, duplicate/unknown-label handling, and every occurrence
map-back check passed.

## Frozen identities and upstream bindings

- Contract/profile: `stage08_address_evidence_projection_contract_v1` /
  `stage08_address_evidence_projection_profile_v1`
- Contract fingerprint:
  `8b3c530e714177fe2c30a97d61dcc199b7f9efba58f3c17a291b817af0f24d5e`
- Schema-bundle fingerprint:
  `6c8ebecd24c495dbe2ce32125ac1cb89c4a9de4905c786b774d10ad728ed392f`
- Label-mapping fingerprint:
  `b18167d2d5c1f1402d1bb0e92559befb92418f5f4f34df885596778a11d5c09d`
- Accepted Stage 7 manifest/logical identities:
  `f58410877a7810562df7985c7316de7546d4dd8e11a647fd659c53a272e9c266` /
  `0f0706c1396803737f22845837753878bfd2e8b3f9af59b48cfcc1b8c5774530`
- Accepted Stage 6 manifest/logical/row-map/binding identities:
  `e1da7b8ef04b65b1ece8e710720b57a8536841766fcf9de641f889b42eadd241` /
  `2f6379c0cd5dc9654c03895cae6fdd48f3a7af528158c33e44d2030c816640b6` /
  `1ff9067c521ae93d28c300d7120a03c39681ce7830bf23b6619e2ca6129a4fe1` /
  `6ba224d6d24c3631aae8aac69f4a362bb054f01d9e3d09327ec6b0fdd85a0e7d`

The complete schema, relation-logical, and upstream identities are frozen in
the [machine-readable execution report](stage08_address_evidence_development.json).

## Repaired publication-state verification

The exact repaired executable keeps `_IN_PROGRESS` present and
`_SUCCESS.json` absent throughout materialization, recursive artifact/manifest
fsync, and complete prospective reopen validation. Job `1763984` reached
terminal success only after that validation. Its `_SUCCESS.json` binds the
final manifest hash above; `_IN_PROGRESS` is absent; no incomplete sibling
attempt remains; the immediate post-publication reopen validator passed; and
stderr is empty.

The final tree has eight directories and 52 files with no symlinks. Every
directory is `0700` and every file is `0600`. It contains:

- 26 candidate shards, 51,779 rows, 103,091,918 bytes;
- 13 component shards, 6,106,088 rows, 67,545,742 bytes;
- nine source-map shards, 35,000 rows, 4,924,221 bytes;
- two metadata files, 25,174 bytes;
- one 19,897-byte manifest; and
- one 567-byte success marker.

Atomic-publication, owner-only-publication, manifest binding, terminal-marker,
topology, permission, and post-publication validation claims all pass.

## Runtime and scheduler evidence

The runtime is Python 3.14.3, PyArrow 25.0.0, and DuckDB 1.5.5. The launcher
used one task, four requested CPUs, DuckDB `threads=4`, an 8GB DuckDB cap, and
32 GiB requested memory. It used frozen input/candidate/component batch sizes
of 16/32/65,536 rows, a 134,217,728-byte target batch, and
candidate/component/source shard limits of 2,048/500,000/4,096 rows. Batch
MaxRSS was 1,786,780 KiB and MaxVMSize was 2,209,224 KiB.

`AllocCPUS=80` remains exclusive-node accounting: `general1` is
`OverSubscribe=EXCLUSIVE`, while `ReqCPUS=4`, the launcher, and application
configuration remain at four CPUs. Batch `TotalCPU` was 960.208 seconds over
936 seconds elapsed, about 1.026 used core-equivalents on average. Whole-node
allocation is not 80-way application concurrency and does not alter the
scientific or bounded-execution result.

## Historical comparison and privacy

Historical job `1763747` used rejected executable `a2544401…` and manifest
`bdf86738…`. It produced the same logical dataset SHA-256,
`9c9d431c2c1b92712e0cb372f2661ad48f4fe8758dc0327d25aef90ab2c2d526`.
This equality is evidence that the publication-state remediation did not
change the frozen scientific dataset. It does not make job `1763747`
validation of repaired executable `bd89a032…`. The old job/artifact remain
immutable historical evidence for the rejected candidate, whose independent
review and two blockers remain preserved.

Parser, reference, network, geocoder, and semantic-trust calls/fields are all
zero. HOLDOUT and production access are false. The manifest contains no row
values, no protected value was logged, and this report was reconciled only
from sanitized manifest, success-marker, log, and scheduler evidence.

## Boundary and next action

No second job, parser run, reference lookup, Stage 9 work, geocoding,
production, or HOLDOUT access is authorized. This candidate is not
`STAGE_8_ACCEPTED`.

Exact next action: **FRESH INDEPENDENT STAGE 8 REREVIEW OF THIS REPAIRED
CANDIDATE.**
