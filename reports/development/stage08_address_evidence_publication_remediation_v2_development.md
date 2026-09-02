# Stage 8 second-remediation DEVELOPMENT materialization

## Candidate result

Current verdict:
`STAGE08_ADDRESS_EVIDENCE_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REREVIEW`.

The single authorized second-remediation Stage 8 DEVELOPMENT job `1764219`
completed `0:0` in 15m10s at exact executable
`bdea7232a3f92ebd381be87610b753b8e4c35481`. It published one immutable
artifact at:

`/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage08/development/stage08_development_20260902T112644Z_bdea7232a3f9`

The artifact manifest SHA-256 is
`346ea27ad60c1e00ef29c1126b2744f38049c1fa7d062647ab6df04e3330dee6`.
Its logical dataset SHA-256 is
`9c9d431c2c1b92712e0cb372f2661ad48f4fe8758dc0327d25aef90ab2c2d526`.
This is frozen DEVELOPMENT candidate evidence, not independent-rereview or
Stage 8 acceptance.

## Exact accepted inputs

- Stage 7 root:
  `/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage07/evidence_only_development/stage07_evidence_e684d84_attempt1`
- Stage 7 manifest/logical identities:
  `f58410877a7810562df7985c7316de7546d4dd8e11a647fd659c53a272e9c266` /
  `0f0706c1396803737f22845837753878bfd2e8b3f9af59b48cfcc1b8c5774530`
- Stage 7 contract/schema fingerprints:
  `c9561e6d08263b2a8824ff66f2a3aa8521e3ff880759abc14173cce440ced8a4` /
  `b0e0e83ea3d929b7df8a6a5f64c2e8eb026395a917da90e97a98858b27e9ead2`
- Stage 6 root:
  `/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage06/development/stage06_development_20260828T223804Z_f39047cc825d`
- Stage 6 manifest/logical/row-map/binding identities:
  `e1da7b8ef04b65b1ece8e710720b57a8536841766fcf9de641f889b42eadd241` /
  `2f6379c0cd5dc9654c03895cae6fdd48f3a7af528158c33e44d2030c816640b6` /
  `1ff9067c521ae93d28c300d7120a03c39681ce7830bf23b6619e2ca6129a4fe1` /
  `6ba224d6d24c3631aae8aac69f4a362bb054f01d9e3d09327ec6b0fdd85a0e7d`

The Stage 7 manifest itself binds the exact accepted Stage 6 manifest. Both
input roots had valid success markers, no in-progress marker, no symlink, and
owner-only modes during metadata-only preflight. The protected job then ran
the complete frozen Stage 6/7 input validators before materialization.

## Scientific reconciliation

| Evidence | Frozen expectation | Job 1764219 |
|---|---:|---:|
| Exact candidates | 51,779 | 51,779 |
| Ordered parser components | 6,106,088 | 6,106,088 |
| Source rows | 35,000 | 35,000 |
| Representation occurrences | 69,747 | 69,747 |
| STANDARD occurrences | 34,822 | 34,822 |
| NATIVE occurrences | 34,925 | 34,925 |
| `PARSED_NONEMPTY` | 51,774 | 51,774 |
| `PARSED_EMPTY` | 5 | 5 |
| Mapped components | 6,106,088 | 6,106,088 |
| Unmapped components | 0 | 0 |
| Dangling components | 0 | 0 |
| Component-count mismatches | 0 | 0 |
| Occurrence-count mismatches | 0 | 0 |

All frozen scientific validation fields pass: exact candidate identity, exact
Stage 7 fields, raw ordered component preservation, component-index
reversibility, duplicate/unknown-label preservation, source-row identity,
representation-slot correctness, occurrence map-back, applicability/technical
provenance, warning-field preservation, semantic-trust vocabulary absence,
later-stage behavior absence, and HOLDOUT/production exclusion.

Parser calls, reference lookups, network calls, and semantic-trust fields are
all zero. HOLDOUT and production access are false.

## Frozen scientific identities

- Contract fingerprint:
  `8b3c530e714177fe2c30a97d61dcc199b7f9efba58f3c17a291b817af0f24d5e`
- Schema-bundle fingerprint:
  `6c8ebecd24c495dbe2ce32125ac1cb89c4a9de4905c786b774d10ad728ed392f`
- Label-mapping fingerprint:
  `b18167d2d5c1f1402d1bb0e92559befb92418f5f4f34df885596778a11d5c09d`
- Candidate schema fingerprint:
  `b1d56ea33c22e639ab798581c5533b1a0981ef5452dce5cb24e168d4a684bd4c`
- Component schema fingerprint:
  `112fb17c2afac27b941d30f57fe5c1bb2e46d779f89bdf2efbd8c719a3b87ccf`
- Source-map schema fingerprint:
  `884eb8456fc6ee84a699a9e2371224e5c709363daac0febc5975f911bf48c398`
- Occurrence schema fingerprint:
  `df1cac9b6d9f86ffb76d1ea744fc64f15149c9e33fef980213286b91b2d02038`

Relation-logical fingerprints are also unchanged:

- candidate evidence:
  `11fbd6e6e32b7dcb293c5918e9d02f19badf52cc9d9c108c910d17d92b8645aa`;
- parser-component evidence:
  `8b1af702c51bd40edc22302778ae2fda5851d9af8af39636a9a9733a94916030`;
- source-candidate map:
  `c4c9f8b3f425f93a1d61880f720136d1f71580871338c9a920c9abeffa93ee32`;
  and
- representation occurrence:
  `57aa3dcc5caf796fbbe15b3c0df655a8f34902107ce9fed3fbb6aaf38e158774`.

The schemas, exact 20-label mapping, Stage 6/7 bindings, semantic classes,
candidate/component/source/occurrence grains, parser-evidence semantics,
occurrence semantics, and Stage 8/Stage 9 boundary are unchanged.

## Publication-state freeze

Job `1764219` exercised the ordinary successful publication path. Complete
prepublication reopen validation passed while `_IN_PROGRESS` remained present
and `_SUCCESS.json` remained absent. The validated temporary tree then
transitioned to the terminal marker set, was fsynced and atomically renamed,
the publication parent was fsynced, and the final bundle immediately reopened
and passed the complete published validator before the CLI returned success.

The final `_SUCCESS.json` exactly binds the manifest, logical dataset,
contract, schema bundle, and four row totals. `_IN_PROGRESS` is absent; no
attempt sibling for this run remains; stderr is empty; atomic publication and
owner-only publication claims pass.

The final topology is:

- 26 candidate shards, 103,091,918 bytes;
- 13 component shards, 67,545,742 bytes;
- nine source-map shards, 4,924,221 bytes;
- two metadata files, 25,174 bytes;
- one 19,897-byte manifest;
- one 567-byte success marker;
- eight directories and 52 files total; and
- zero symlinks, zero non-`0700` directories, and zero non-`0600` files.

Policy A, `ADOPT COMPLETED PUBLICATION`, remains the deterministic recovery
policy for an ambiguous post-effect rename. The controlled job did not inject
that fault and did not enter synthetic adoption recovery. The real-rename-then-
raise behavior remains validated by local synthetic tests and must be
challenged again during independent rereview.

## Runtime and resource reconciliation

The runtime was Python 3.14.3, Unicode 16.0.0, PyArrow 25.0.0, and DuckDB
1.5.5. The launcher requested one node, one task, four CPUs, 32 GiB, and four
hours. DuckDB used four threads with an 8GB cap. Input/candidate/component
batches remained 16/32/65,536 rows; target batches remained 134,217,728 bytes;
candidate/component/source shard limits remained 2,048/500,000/4,096 rows.

The job completed `0:0` in 15m10s. Batch MaxRSS was 1,785,464 KiB, MaxVMSize
was 2,208,464 KiB, and TotalCPU was 15m44.099s. Scheduler `AllocCPUS=80` is
exclusive-node allocation behavior on `general1`; requested and application
concurrency remained four CPUs.

## Historical relation and privacy

The logical dataset SHA-256 matches historical jobs `1763747` and `1763984`.
The narrow conclusion is that the two publication remediations did not alter
the frozen Stage 8 scientific dataset. Neither historical job validates
executable `bdea7232…`, and neither artifact is called corrupt.

Original executable `a2544401…`, job `1763747`, the first independent-review
failure, first repair `bd89a032…`, job `1763984`, its successful scientific
reconciliation, the failed independent rereview, the exact post-effect rename
blocker, second repair `bdea7232…`, policy A, and job `1764219` remain distinct
truthful provenance.

Only sanitized scheduler, manifest, success-marker, publication-topology, and
aggregate evidence was reopened for this freeze. No additional protected job,
HOLDOUT, production, parser, reference, geocoder, DeepParse, Senzing, or Stage
9 work occurred.

## Next action

Exact next action: **FRESH INDEPENDENT STAGE 8 REREVIEW OF THE BDEA7232
REPAIRED CANDIDATE.**
