# Reproducibility

## Reproducibility model

An accepted result is identified by more than a filename. Its reproducibility
chain binds scientific contracts, source population, stable identities,
schemas, logical content, physical artifacts, exact code, runtime, execution,
and review evidence.

```text
population scope + source hashes
  -> stage input binding
  -> contract/profile/reference versions
  -> schema and logical fingerprints
  -> immutable artifacts + manifest
  -> exact Git SHA + runtime + SLURM job
  -> sanitized evidence + independent decision
```

## Exact Git SHA

Protected execution uses a clean worktree at an exact full commit already
pushed to `origin`. Submission records the SHA, and the job verifies it before
opening protected inputs. Code is not selected dynamically inside an SBATCH
job. Branch names are navigation; commit ancestry is the durable scientific
record.

Accepted/rejected Stage 3 history is intentionally unsquashed. The accepted
integration commit is
`958dddc8a9769977453ea5588e6861b62162090a`; the accepted implementation and
evidence commits are
`278414573fd465e261f3b9131c45fb564b93622d` and
`82e945a2f41b61e4deff4c28fff4a02ef2af047a`. Rejected v1 remains reachable at
`9ed24cea8626b9cd674377636fe1d51e3cd6b456` with implementation
`8446190d1153aeb507678d0de18d027f89f0ec8d`.

The final accepted `main` before post-Stage-5 cleanup was
`d94c715c83e4ba7233e133a7f5156e33b1ca3023`. The Stage 5 implementation
`cd0a5ae91c3602ec20e34f7c419f1ac76f0b9160` and reviewed evidence head
`97bd7fa74da358e81133ac4d38232931762d3e78` are reachable from `main`.
Review-only commits outside `main` remain reachable through immutable
annotated tags: `stage04-independent-review-2b77aab` and
`stage05-independent-review-cbafa0a`.

## Contracts and profiles

Contracts define canonical inputs, transformations, outputs, identities,
failure behavior, and validation. Profiles pin scientific options such as the
Stage 3 cleaning order and ftfy behavior. Runtime or reporting improvements do
not silently change a scientific contract; any changed scientific semantics
require a new reviewed version.

External reference data used by future stages must be direct, licensed,
versioned, checksummed, and locally reproducible. A library name alone is not a
reproduction specification.

## Fingerprints

- **Schema fingerprints** bind ordered field names, types, nullability, and
  relevant metadata contracts.
- **Logical fingerprints** bind scientific content independent of physical
  Parquet layout, compression, timestamps, host, or file naming.
- **Ordered identity fingerprints** prove the stable row stream without
  retaining a total-row Python set.
- **Benchmark/review fingerprints** freeze the exact evaluation population and
  deterministic selection policy.
- **Artifact SHA-256 values** bind exact bytes for manifests, Parquet files,
  reports, and success markers where required.

These identities answer different questions and are not interchangeable.

## Manifests and immutable runs

Each run has a unique ID and a new output directory. Its manifest records the
input artifacts and expected hashes, scientific and physical identities,
contract/reference/runtime versions, output artifacts, permissions, exact Git
SHA, execution site, and SLURM job where applicable. Protected manifests stay
controlled if they reveal row-level topology or paths.

Writers publish atomically only after validation. A terminal success marker
binds the completed manifest; it is not created for partial output.

## SLURM job identity

The SLURM job ID records the scheduled execution instance and links scheduler
accounting/log evidence to the immutable run. It is operational provenance, not
the scientific dataset identity. Repeating identical scientific computation in
a new job should preserve the logical fingerprint while producing distinct
operational provenance.

Accepted Stage 3 DEVELOPMENT materialization ran as job `1759269`; independent
review ran as job `1759272`.

## Benchmark and fixed review identity

Benchmark V1 is fixed at 50,000 rows from the accepted 1,405-file population:
35,000 DEVELOPMENT and 15,000 sealed HOLDOUT. Its fingerprint is
`014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf`;
its manifest fingerprint is
`1cf8a36f77adde9aa5f80e73bbc273e8ef07430019eceac97f5eeda45e98d766`.
The later six production files do not alter Benchmark V1.

The fixed 500-row DEVELOPMENT review subset has fingerprint
`014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52`.
Each stage creates a new immutable review artifact for these identities rather
than rewriting earlier views.

## Production identity

The production population is `production_population_1411_v1`, containing 1,411
files and 141,048,582 rows. Accepted production Stage 1 is bound by:

- adoption SHA-256:
  `01809a1ea9d65c574b91f28a938fc27a7eda3e89c7b52252797c7cf0c7c6d9df`;
- logical fingerprint:
  `d68cc9990d476e8b7adbb3df53f158d9a73efe4a0f4a8407a2ab6a2f0d98a763`;
  and
- manifest SHA-256:
  `1fb6176d8eff6dfe71c3c02c1e36e00d35937c7bc662234b7620289d4b055bd7`.

Production Stages 2–6 have not started.

## Accepted and rejected evidence

An empirical run is evidence, not automatic acceptance. Independent review
returns a named decision bound to the exact candidate. Rejected evidence stays
available so the failure, fix scope, and equivalence claims can be audited.

Stage 3 v1 is preserved because its scientific values were sound while its
production scalability and reporting evidence were rejected. V2 created new
immutable output, proved exact scientific/reason equality, and received a new
review. Rewriting or squashing that sequence would remove meaningful evidence.

## Why failed attempts are preserved

A failed SLURM attempt can reveal runtime, environment, path, permissions,
input-binding, or implementation failures. Deleting or overwriting it would
make the final successful result harder to interpret and could conceal repeated
or selectively reported attempts. Failed directories and logs are therefore
retained under controlled permissions with explicit failure state; a new
attempt gets a new run identity.

## Sanitized reporting

Git-safe reports contain only allowlisted aggregates, statuses, versions,
fingerprints, job/commit identities, and non-sensitive resource metrics. They
provide portable progress evidence without attempting to reproduce protected
row content. Full scientific reproduction requires authorized access to the
controlled input and immutable artifacts; documentation alone never grants
that access.
