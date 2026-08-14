# Phase 3 DEVELOPMENT address-pattern profiler

Status: implemented with fictional synthetic validation; not yet executed on
the protected 8,000-row DEVELOPMENT corpus.

## Purpose and boundary

`phase03_development_pattern_profiler_v1` is a deterministic diagnostic for
designing a future, separately reviewed parser revision. It profiles the fixed
8,000-row DEVELOPMENT payload together with its validated
`conservative_address_parser_v2` core and evidence outputs. It does not create
rules, parse with new semantics, use review labels, geocode, modify parser-v2
artifacts, resample identities, or access LOCKED_EVALUATION.

Production use is fail-closed behind the shared Goethe-NHR/SLURM execution
guard. The Mac pathway exists only as the explicit `production=False` test API
and uses fictional fixtures.

## Validated inputs

The command requires exactly four read-only artifacts:

- the existing 8,000-row Phase 2 DEVELOPMENT payload;
- the parser-v2 52-column core Parquet;
- the parser-v2 20-column evidence Parquet;
- the protected DEVELOPMENT identity set.

Before profiling, it verifies exact Arrow schemas, Parquet page checksums,
DEVELOPMENT partition metadata, the exact 8,000-identity set, row counts,
parser/registry versions, core/evidence validators, evidence source spans, and
the complete identity relationship. Any path containing `locked`
case-insensitively is rejected. Input byte size and SHA-256 are taken before and
after the read; a changed input fails the run. No input file is opened before
the production execution guard passes.

## Sanitized structural representation

Raw lexical values never enter an output. Unicode code points are reduced to a
closed structural vocabulary including `HOUSELIKE_NUM`, `NUM`, `WORDS`,
`ALNUM`, `LOCAL_SCRIPT`, `ROMAN_NUMERAL`, `SLASH_NUMBER`, `HYPHEN_NUMBER`,
`LETTER_SUFFIX_NUMBER`, punctuation classes, `NEWLINE`, and `OTHER`.
Consecutive word/script tokens are collapsed. Patterns longer than 16 tokens
become the single class `LONG_PATTERN_17_PLUS`.

Named structural patterns require at least five distinct affected rows and at
most 100 patterns are reported in any bounded distribution. Suppressed
patterns contribute only aggregate distinct-pattern and segment counts. The
opportunity table uses the same threshold and cap. Country output uses an exact
raw two-letter uppercase code only when parser v2 classified it as
`ALPHA2_ASSIGNED_EXACT`; every other value is reduced to its closed
`country_input_class`. No unusual/raw country text is emitted. Script labels
come only from the pinned Unicode 16.0 Scripts reference.

These thresholds are disclosure controls, not scientific parser thresholds.
Frequency does not establish correctness.

## Output contract

One atomically promoted owner-only directory contains:

- `phase03_development_pattern_profile.json`: version/configuration, logical
  input roles with byte sizes and hashes, parser-v2 status and component
  counts, unassigned-content distributions, morphology, line relationships,
  numeric morphology, all rule coverage, country/script aggregates, bounded
  opportunities, and privacy guardrails;
- `phase03_development_pattern_opportunities.csv`: the bounded opportunity
  table with pattern class, affected rows, segment count, current street/house
  selections, and country/script breadth;
- `phase03_development_pattern_profile.md`: a short sanitized interpretation
  and explicit false-positive cautions.

The JSON and CSV contain no path, identity, provider ID, source location, raw
span, candidate value, address word, company/locality/person name, or review
identifier. Only logical artifact roles, file hashes/sizes, closed vocabulary
labels, official rule IDs, assigned ISO alpha-2 codes, Unicode script classes,
and counts are portable.

## Exact CLI

This command is production-scoped and therefore succeeds only in a Goethe-NHR
SLURM allocation with `SAFE_EXECUTION_SITE=goethe-nhr`:

```bash
python -m safe_geocoding_pipeline.phase03.cli development-pattern-profile \
  --development-payload "${PHASE03_DEVELOPMENT_PAYLOAD}" \
  --development-core "${PHASE03_DEVELOPMENT_CORE}" \
  --development-evidence "${PHASE03_DEVELOPMENT_EVIDENCE}" \
  --development-identities "${PHASE03_DEVELOPMENT_IDENTITIES}" \
  --output-directory "${PHASE03_PROFILE_OUTPUT}"
```

The prepared job is
`cluster/goethe_nhr/phase03_development_pattern_profile.sbatch`. It requests
one node, one task, two CPUs, 16 GiB RAM, and one hour on `general1`. It runs
from a clean detached integration worktree at the exact reviewed commit,
validates Python 3.14.3, Unicode 16.0.0, CLDR/UCD references and registry v3,
then atomically promotes only the sanitized report directory under
`reports/generated/phase03/development_pattern_profiles/`.

No job is submitted by this implementation task.

## Scientific use

The outputs may prioritize synthetic parser-v3 experiments and protected
manual-review questions. They may not automatically set confidence, justify a
rule, infer language semantics, or alter parser-v2. Rare patterns, ambiguous
numeric-only content, date/postcode/unit/floor collisions, and mixed-role
segments remain unsafe until a separately approved rule design supplies exact
positive and false-positive boundaries.
