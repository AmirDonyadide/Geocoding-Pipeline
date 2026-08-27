# DEVELOPMENT workflow

## One scientific stage at a time

The project maintains one active scientific stage workflow at a time. A later
stage does not begin merely because an earlier run completed or an empirical
report exists. Each stage stops at an explicit review and acceptance gate.

```text
design
  -> design review and explicit approval
  -> implementation
  -> synthetic/unit tests
  -> full 35,000-row DEVELOPMENT execution
  -> aggregate scientific evaluation
  -> fixed-500 qualitative review
  -> independent review
  -> accept and freeze
  -> stop
```

Stages 0–3 have completed this lifecycle on DEVELOPMENT. Stage 4 has not begun.

## Design and implementation

A stage design defines input binding, output schema, scientific transformations
and non-goals, identity/provenance behavior, failure semantics, libraries and
reference versions, privacy boundary, expected evidence, and the stop gate.
Implementation begins only after explicit approval of that design.

Synthetic tests exercise both ordinary behavior and high-risk boundaries such
as malformed input, identity mismatch, Unicode behavior, huge values,
permission failures, path rejection, atomic publication, and HOLDOUT guards.
Synthetic success is necessary but not sufficient for scientific acceptance.

## DEVELOPMENT evaluation

Every address-changing stage is evaluated on all 35,000 protected DEVELOPMENT
rows. Quantitative evidence includes exact input/output counts, incoming-field
preservation, identity equality, derived-value distributions, reason/evidence
counts, fingerprints, and resource observations appropriate to the stage.

The same deterministic 500 DEVELOPMENT identities support human before/after
inspection. This qualitative surface detects changes that aggregates can hide,
but it does not replace full-DEVELOPMENT evaluation. Review uses
`stable_source_row_id_v1` and immutable stage-specific artifacts.

Only allowlisted aggregate reports may be committed to Git. Row-level values,
stable identities, source filenames, and free-text examples remain protected.

## Independent review and freeze

Independent review binds the exact implementation commit and immutable run
artifacts, reproduces critical counts/fingerprints, inspects the fixed review
surface in the controlled environment, and returns an explicit decision.
Acceptance freezes the contract, evidence, implementation lineage, and run
identity. It does not authorize production execution or the next stage.

## Rejected candidates

Rejection preserves the candidate and evidence:

```text
preserve candidate and run
  -> identify the narrow failure
  -> approve a minimal fix scope
  -> create a new immutable implementation/run
  -> repeat evaluation and independent review
```

Rejected output is never overwritten or relabeled as accepted. Stage 3 v1 is
the current example: its scientific output was retained, the production-
scalability/reporting implementation was repaired in v2, exact v1/v2
scientific equality was proved, and v2 received a new independent review.

## HOLDOUT

The 15,000-row HOLDOUT remains sealed while Stages 2–19 are designed, tuned,
and frozen. It is used once only under a separately approved final-evaluation
protocol. No stage workflow may inspect HOLDOUT for debugging, examples,
documentation, profiling, review selection, or threshold tuning.

## Long-running SLURM work

One reviewed job is submitted once:

```text
prepare exact pushed commit and immutable output identity
  -> submit once
  -> wait or monitor scheduler state
  -> resume the same scientific workflow
  -> reuse the resulting artifact
```

A pending job is not a reason to launch a duplicate. Failed attempts, logs, and
partial run directories remain evidence and are not silently overwritten. A
replacement submission requires a new explicit run identity and a documented
reason.

## Production separation

DEVELOPMENT acceptance and production execution are different decisions.
Production Stage 0 and Stage 1 are accepted for the 1,411-file population.
Production Stage 2 and Stage 3 have not started. Before production Stage 2 can
run, its exact launcher, commit, population binding, resources, output paths,
and validation plan require separate review and authorization.

## Repository workflow

The shared canonical branch is `main`. Work starts from the current remote
state, uses professional scientific/project branch names when a branch is
needed, and integrates without rewriting accepted history. Before execution or
review, record a clean exact Git SHA. Coherent changes are committed and pushed
so that Goethe can obtain the same code through Git.

Documentation-only maintenance may update navigation and current status, but
must still demonstrate that accepted scientific code, contracts, fingerprints,
HOLDOUT rules, and stage boundaries did not change.
