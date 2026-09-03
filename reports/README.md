# Reports

The repository has two current report classes. Together they provide one clear,
sanitized record for every accepted DEVELOPMENT stage from Stage 0 through
Stage 8.

## development/

[`development/`](development/README.md) contains the human-readable,
authoritative DEVELOPMENT reports. There is exactly one Markdown report per
stage. Start there to understand what a stage did, why it existed, how it was
validated, what failed historically, and why the final state was accepted.

## generated/

[`generated/`](generated/README.md) contains the machine-readable, sanitized
evidence summaries. There is exactly one JSON file per stage. Use these files
for automated checks and exact commits, jobs, counts, manifests, fingerprints,
and review provenance.

"Generated" does not mean raw or controlled output. No protected address,
company, source-row, HOLDOUT, production-row, credential, or arbitrary payload
belongs anywhere under `reports/`. Detailed superseded report history remains
available through Git history; protected execution artifacts remain only on
authorized controlled infrastructure.

The DEVELOPMENT pipeline is `STAGE_8_ACCEPTED`, so Stages 0–8 are accepted.
The pre-Stage-9 baseline is frozen and Stage 9 has not started. Production
Stage 0 and Stage 1 are accepted separately; production Stage 2 and later
stages have not started.
