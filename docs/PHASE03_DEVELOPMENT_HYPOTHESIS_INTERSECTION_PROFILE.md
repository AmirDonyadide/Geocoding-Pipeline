# Phase 3 DEVELOPMENT hypothesis intersection profile

Status: **DEVELOPMENT profiling only; no parser rule is authorized.**

This profiler measures three previously shortlisted structural hypotheses on the immutable 8,000-row DEVELOPMENT population. It reads the authoritative Parser v2.1 baseline and Parser v3.2 DEVELOPMENT artifacts, but it does not transform rows, rerun selection, or change any scientific output.

## Frozen inputs

- DEVELOPMENT identity artifact SHA-256: `cab12eb1c1c2f61b8bbc5b53dff604e7569233518e5fb3c88467d848e648d71a`
- DEVELOPMENT payload SHA-256: `dc78fd5c814739008a9ce24e91c66bf7c1121898b06ce2dfc53b0620b07a3cb1`
- Parser v2.1 configuration: `25962a126cd5d30c13607bd564aa250e91096e6961745670772a1ce31b76ac4d`
- Parser v2.1 core/evidence SHA-256: `644b22865486c27ecb7bd15297fc131a7fa282758fb245bc8c6e885dacfecaf5` / `0f7ddae89755f2d8c6d2973e09be4670e851fb58867d8233998d10aa23443baa`
- Parser v3.2 DEVELOPMENT configuration: `89370fddf5f9dae8f381f62344df4da96f0b3dc34627cff23a8068555b909a73`
- Parser v3.2 core/evidence SHA-256: `28efa83eed2870c681891e9f0ecc526c8b5abdf3c6305dd63ef3f0ff2811f10f` / `ca6be7107a0dc72903542030a3b0846fe9e15ceee4bf2c9352682b4817f37b16`

All protected inputs must resolve beneath controlled Phase 3 DEVELOPMENT storage. Any path containing `locked`, any non-DEVELOPMENT identity partition, a hash mismatch, a parser/configuration mismatch, or an execution outside Goethe-NHR SLURM fails before profiling.

## Hypothesis definitions

### H1 — disjoint component-span guard

H1 is exactly the current Parser v3.2 DEVELOPMENT population carrying `COMPONENT_SPAN_OVERLAP_CONFLICT`. The profiler reconstructs the medium/high candidate overlap pairs that caused the flag. Registered unit/house-number and building/organization conflict pairs remain separate existing semantics and are not reclassified as H1.

### H2 — explicit role-ownership arbitration

H2 contains rows where evidence from one of the existing explicit unit, floor, building, or organization rules overlaps street or house-number evidence. The report keeps unique row counts separate from overlapping relationship memberships. Confidence and registry selection-priority relationships are reported as separate existing evidence properties; the profiler does not invent a new cross-component arbitration order.

The existing unassigned `HYPHEN_NUMBER WORDS` structural family is also counted and intersected with H2.

### H3 — adjacent explicit street/house-number pairing

H3 begins with `STREET_EXPLICIT_DESIGNATOR_V3` evidence and a non-empty immediately adjacent line in the same representation containing numeric morphology. A relationship is eligible only when the adjacent line consists of exactly one bounded house-like token and all of these diagnostic exclusions are absent:

- multiple numeric tokens or multiple eligible adjacent numeric lines;
- non-numeric-only extra material;
- structured-postcode equality;
- the existing zero-padded slash calendar boundary or a year from 1900 through 2099;
- stronger explicit role evidence on the adjacent line under the existing registry priority;
- disagreement with a non-empty corresponding native/non-native line.

These are profiling boundaries, not an implemented Parser v3.3 rule.

## Existing review coverage

The profiler binds the completed 11-row Targeted-v3.1 R01 controlled labels to their protected context without exporting identities or raw values. It reports identity overlap separately from scientific reusability. The v3.1 review assessed the distinct same-line embedded-V4 hypothesis, so identity overlap is not silently treated as reusable evidence for H1, H2, or H3. No rejected Parser-v1 review state is considered reusable.

## Output and privacy

The output directory contains:

- `phase03_development_hypothesis_intersection_profile.json`;
- `phase03_development_hypothesis_intersections.csv`;
- `phase03_development_hypothesis_intersection_profile.md`.

Only closed structural categories, aggregate counts, rule IDs, parser statuses, fingerprints, artifact hashes/sizes, and domain-separated population digests are portable. Raw addresses, source identities, candidate values, source spans, protected notes, and filesystem paths are prohibited. Output files use mode `0600`; directories use `0700`.

## Execution

Run only through `cluster/goethe_nhr/phase03_development_hypothesis_intersection_profile.sbatch` from a clean detached Goethe integration worktree pinned to the reviewed profiler commit. The job requests one node, two CPUs, 16 GiB RAM, and one hour on `general1`. It performs a bounded read-only scan of the fixed 8,000 DEVELOPMENT rows and atomically promotes the sanitized report directory after validation.

The report informs a later decision about exactly one experimental hypothesis. It does not authorize parser implementation, targeted review preparation, a new holdout, production transformation, geocoding, or Phase 4.
