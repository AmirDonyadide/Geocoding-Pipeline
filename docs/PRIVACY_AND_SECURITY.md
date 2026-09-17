# Privacy and security

## Protected material

The following are protected and must remain on controlled local or Goethe-NHR
infrastructure:

- raw company/facility addresses and source CSV files;
- all row-level source data and provenance;
- stable source identities when linked to row-level artifacts;
- controlled DEVELOPMENT artifacts, including the fixed 500-row review views;
- HOLDOUT identities, values, metadata, and outputs;
- production Parquet, manifests containing row-level topology, mappings,
  candidate/query tables, geocoder inputs/responses, and final datasets;
- credentials, tokens, API keys, and authorization headers; and
- logs or diagnostics containing any of the above.

Protected values must never be sent to an external geocoder, public API, web
service, LLM, or other uncontrolled system. The project uses only self-hosted
SAFE Pelias after the pre-geocoding pipeline is accepted and separately
authorized.

## Material that may be tracked in Git

Git may contain:

- source code and reviewed configuration/contracts;
- synthetic fixtures containing fictional values;
- tests and reproducible cluster/execution assets;
- documentation and durable scientific decisions;
- hashes, schema/logical fingerprints, and manifests that contain no protected
  row-level content;
- sanitized aggregate reports and non-sensitive metrics; and
- third-party licenses and pinned non-sensitive reference metadata.

Before committing, inspect both tracked and untracked state. A `.gitignore`
rule is a backstop, not permission to place protected data in the repository.

## Prohibited actions

Never:

- commit raw addresses, protected Parquet, review copies, HOLDOUT, production
  artifacts, secrets, or protected logs;
- paste protected values into issues, pull requests, documentation, prompts,
  chat, screenshots, or public notebooks;
- use public geocoding, mapping, translation, enrichment, or validation APIs on
  protected records;
- send protected values to LLMs, including for debugging or example generation;
- infer that a missing open-reference record is invalid;
- print credentials or authorization headers; or
- weaken execution/path/permission guards to simplify local work.

## Permissions

Controlled directories must be mode `0700` and controlled files mode `0600`.
Writers validate owner-only permissions before success publication. Symbolic
links, path escapes, pre-existing outputs, or unexpectedly permissive modes
fail closed where the stage contract requires a controlled path.

Temporary and in-progress outputs use the same owner-only boundary. Publication
requires readback and validation under the stage's frozen protocol. Stage 9/10
use permanent reservation and an exclusive commit seal; earlier stages retain
their accepted publication semantics. See
[publication policy](EXECUTION_POLICY.md#storage-and-publication-contract).

## Fail-closed execution

Protected/heavy production commands require:

```text
SAFE_EXECUTION_SITE=goethe-nhr
SLURM_JOB_ID=<non-empty>
```

The common guard runs before production input is opened. There is no normal
force-local bypass. The MacBook is limited to code, documentation, synthetic
tests, small diagnostics, and explicitly controlled small DEVELOPMENT review.

HOLDOUT-aware interfaces reject HOLDOUT-named paths and non-DEVELOPMENT split
values before reading row data. HOLDOUT remains sealed until a separately
approved final evaluation after Stages 2–19 freeze.

## Reporting boundary

Portable reports use strict allowlists. They may include aggregate integer
counts, approved status/interpretation codes, versions, Git SHAs, SLURM job
IDs, fingerprints, and non-sensitive performance observations. They may not
include raw/free-text address values, stable row identities, provider IDs,
source filenames, arbitrary error strings derived from data, or small-cell
information outside an approved disclosure policy.

For colleague discussion, use committed sanitized reports or synthetic
examples. Protected before/after review stays in the controlled environment.

## Credentials and SAFE Pelias

SAFE Pelias credentials are supplied only through protected runtime
configuration. They are never committed, echoed, included in command examples,
or written to logs/manifests. Normal geocoder concurrency is 2–4 requests total
across the full process. No geocoding workload is authorized by the existence
of code or credentials.

## Incident response

If protected material is suspected in Git, logs, terminal capture, or an
external system, stop further distribution, preserve the evidence, notify the
project owner/institutional security contact, and follow the applicable data
governance process. Do not attempt an unreviewed history rewrite: containment,
credential rotation where relevant, and a documented remediation decision are
required.
