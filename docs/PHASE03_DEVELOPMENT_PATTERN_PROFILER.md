# Phase 3 DEVELOPMENT address-pattern profiler

Status: implemented and committed. Initial job `1748986` failed in shell
preflight after approximately two seconds with
`PATTERN_PROFILE_INPUT_OUTSIDE_CONTROLLED_DEVELOPMENT`; the profiler itself
never executed and no valid report exists. The failure was an operational path
canonicalization defect, not a profiler or parser scientific failure.

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

The original reviewed implementation is commit
`e4d15d426eb9e99d90c67450355e0527ec25be87`; the profiler source SHA-256 is
`56dd654cb35b8eef78c24e59a4c17574f6c9770e7f45411b25a6020265c8198a`
and the originally submitted SBATCH SHA-256 is
`b3554a92dacc4bfd79fd654235dee6510e6a7f0810b5feab78b61abf9a781f23`.
The detached Goethe worktree at that commit remains preserved as audit
evidence for failed job `1748986`.

The failed preflight canonicalized each input from `/work/...` to
`/panfs/vdura1/...` while comparing it with an uncanonicalized `/work/...`
trusted prefix. The corrected SBATCH canonicalizes both the trusted controlled
root and each candidate input; its SHA-256 is
`123998a872b63a75dc0f1f42667efa37afac13261a168aecbd933c0fac234ef7`.
The LOCKED path prohibition and controlled-tree containment boundary are
unchanged. A replacement must use a fresh detached integration worktree at the
exact reviewed correction commit and a new output identity.

The replacement broad profile completed successfully in Goethe-NHR job
`1749177` as
`phase03_development_pattern_profile_20260815T160357Z_1749177_9cd8b43c`.
It validated exactly 8,000 DEVELOPMENT rows, read zero LOCKED rows, emitted no
raw values, and passed. Its principal aggregate findings were 6,903 rows with
unassigned content and 2,308 rows whose unresolved street-line content had no
street/house candidate. The profile reported 4,371 `UNPARSEABLE`, 2,344
`PARTIAL`, 1,048 `PARSED`, 162 `CONFLICT`, 27 `AMBIGUOUS`, and 48
`INSUFFICIENT` rows. These counts motivate narrower diagnostics; they do not
approve Parser v3.

## Targeted opportunity diagnostic

`phase03_development_targeted_opportunity_profiler_v1` is a second-stage,
diagnostic-only cross-tab over the same immutable DEVELOPMENT payload and
parser-v2 core/evidence. It is limited to these predeclared structural
families:

- `WORDS HOUSELIKE_NUM`;
- `HOUSELIKE_NUM WORDS`;
- `WORDS HOUSELIKE_NUM WORDS`;
- `HOUSELIKE_NUM COMMA WORDS`;
- `WORDS COMMA HOUSELIKE_NUM`;
- `SLASH_NUMBER WORDS`;
- `WORDS SLASH_NUMBER`;
- `HYPHEN_NUMBER WORDS`.

For each family it reports thresholded counts for source line,
native/non-native representation, numeric position, same/cross-line scope,
adjacent-line structure, current component selections, candidate/rule
presence, candidate multiplicity, conflicts, structured corroboration,
native structural/script relationships, country group, script family, and a
cautious diagnostic-support class. A category is named only at five or more
distinct DEVELOPMENT rows, no distribution names more than 100 categories,
and patterns remain bounded to 16 tokens. Counts from one to four are omitted
or marked `SUPPRESSED`. The output contains no raw value, identity, path, or
source span.

The exact command is:

```bash
python -m safe_geocoding_pipeline.phase03.cli \
  development-targeted-opportunity-profile \
  --development-payload "${PHASE03_DEVELOPMENT_PAYLOAD}" \
  --development-core "${PHASE03_DEVELOPMENT_CORE}" \
  --development-evidence "${PHASE03_DEVELOPMENT_EVIDENCE}" \
  --development-identities "${PHASE03_DEVELOPMENT_IDENTITIES}" \
  --output-directory "${PHASE03_TARGETED_PROFILE_OUTPUT}"
```

The prepared Goethe-NHR wrapper is
`cluster/goethe_nhr/phase03_development_targeted_opportunity_profile.sbatch`.
It uses a clean detached worktree at the exact reviewed commit, invokes the
shared production execution guard, rejects any path containing `locked`, and
atomically promotes owner-only outputs under
`reports/generated/phase03/development_targeted_opportunity_profiles/`.
Parser v3 rule creation remains unauthorized.

## Scientific use

The outputs may prioritize synthetic parser-v3 experiments and protected
manual-review questions. They may not automatically set confidence, justify a
rule, infer language semantics, or alter parser-v2. Rare patterns, ambiguous
numeric-only content, date/postcode/unit/floor collisions, and mixed-role
segments remain unsafe until a separately approved rule design supplies exact
positive and false-positive boundaries.
