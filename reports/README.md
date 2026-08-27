# Reports

Only sanitized, Git-safe aggregate evidence is tracked here.

- `development/` contains allowlisted DEVELOPMENT summaries and paired JSON.
- `generated/` is ignored and may contain controlled or run-specific output; it
  must never be committed without a separate sanitation review.

Row-level DEVELOPMENT artifacts, the fixed 500-row Parquet views, HOLDOUT,
production outputs, stable identities, source paths, and protected manifests do
not belong in Git. See `docs/INSPECTING_RESULTS.md` for the evidence layers.
