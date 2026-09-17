# Reports

| Evidence | Location | Coverage |
|---|---|---|
| Authoritative human reports | [development/](development/README.md) | One Markdown report per accepted DEVELOPMENT Stage 0–9 |
| Frozen machine summaries | [generated/](generated/README.md) | One sanitized JSON summary per Stage 0–8 |
| Independent Stage 9 review | [Final review](../review/stage09_independent/FINAL_REVIEW.md), [evidence JSON](../review/stage09_independent/REVIEW_EVIDENCE.json) | Preserved review harness, findings and aggregate checks |

Stage 9's [owner acceptance record](development/stage09.md#owner-acceptance-and-freeze--2026-09-14)
binds its exact frozen identities; it has no paired `generated/stage09.json`.
Reports retain accepted facts and historical failures. Later-stage stop/status
statements describe their original checkpoints, not the current repository.
Use [current progress](../docs/DEVELOPMENT_PROGRESS.md) for Stage 10's implementation
and execution status.

Only sanitized aggregates and provenance belong in tracked reports. Protected
rows, source filenames, stable row IDs, credentials and arbitrary payloads stay
in controlled storage. Ignored per-run execution reports are distinct from these
committed acceptance summaries. Superseded reports remain in Git history.
