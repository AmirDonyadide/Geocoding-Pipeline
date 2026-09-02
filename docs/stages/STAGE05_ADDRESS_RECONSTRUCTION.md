# Stage 5 — address reconstruction

## Status

**`STAGE_5_ACCEPTED` on DEVELOPMENT.**

Acceptance is limited to the 35,000-row Benchmark V1 DEVELOPMENT split. It
does not authorize Stage 6, HOLDOUT access, geocoding, or any production
preprocessing stage.

## Scientific purpose and boundary

Stage 5 converts each existing ordered four-line address representation into a
coherent line-body candidate. It does not decide what a line means. It does not
parse, normalize, validate, repair, reorder, deduplicate, geocode, or create a
final query. Postcode, city, region, and country remain separate structured
fields for later stages.

The contract and profile are:

- `stage05_address_reconstruction_contract_v2`;
- `stage05_address_reconstruction_profile_v2`.

The accepted Stage 4 DEVELOPMENT boundary is bound exactly by:

- contract: `stage04_lowercase_canonical_contract_v1`;
- profile: `stage04_lowercase_canonical_profile_v1`;
- schema fingerprint:
  `dafb4f78b8bfce3120b6f4f7ae8cb44883f4c3a9cfd94b3137871b83c0ed5cbc`;
- logical fingerprint:
  `054c66701f854a0108938170e1cb9bcee8a772f7fed29b82cda53c71aa9747ec`;
- input-binding fingerprint:
  `90e0e94d4359bd5927820dfc06b2cfc1dc37485c032d95726d1260ec88a534b0`;
- manifest fingerprint:
  `17a4854cddd8929b65ea79402f1a4f12a1574b720c1921567b577f23e152d1f3`;
- ordered identity fingerprint:
  `fe2a4758582c1880d2b5c62dfc5c587d865e05d13033af9f5e8208b58e2a0487`.

Benchmark V1 remains
`014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf`.
The fixed 500-row review subset remains
`014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52`.

## Design decision table

| Question | Stage 5 decision |
|---|---|
| Exact scope | Reconstruct ordered address-line bodies only |
| Standard input | Four accepted Stage 3 clean standard lines and their four accepted Stage 4 lowercase counterparts |
| Native input | Four accepted Stage 3 clean native lines and their four accepted Stage 4 lowercase counterparts |
| Standard/native relationship | Reconstruct independently; never combine, rank, translate, or collapse |
| Case-preserving output | Retain a clean, case-preserving candidate for display and audit |
| Canonical output | Retain a lowercase candidate for exact downstream candidate work |
| Geographic fields | Exclude postcode, city, region, and country from reconstruction |
| Empty line | Filter only exact `""`; Stage 3 already prohibits whitespace-only cleaned values |
| Gaps | Skip empty positions without an artificial empty separator; preserve relative order |
| Duplicate lines | Preserve every contributing occurrence |
| Order | Existing source positions 1, 2, 3, 4 |
| Separator | Exact single space, U+0020 |
| Zero lines | Candidate `""`, unavailable, count 0, mask `0000` |
| One line | Candidate is the line unchanged |
| Provenance | Availability, contributing-line count, and four-position occupancy mask per representation |
| Bounded execution | PyArrow/Parquet row-group streaming with adaptive batches and disk-backed length quantiles |
| Quantitative evidence | Full 35,000-row availability, relationship, line-count, mask, gap, duplicate, boundary, length, identity, and performance metrics |
| Qualitative evidence | Same ordered fixed 500 identities with raw, clean, lower, candidate, and audit comparison surface |
| Tests | Empty/gap/duplicate/punctuation/Unicode/giant/binding/manifest/permission/determinism and regression matrix |

## Exact reconstruction rule

For either representation and either clean or lowercase input:

```text
contributing_lines = [line for line in line_1_to_4 if line != ""]
candidate = " ".join(contributing_lines)
```

The rule does not trim or mutate a line. Existing commas, semicolons, slashes,
hyphens, parentheses, and Unicode punctuation remain exact. The separator adds
no punctuation of its own.

The occupancy mask is four characters in line 1-to-4 order: `1` means the
exact cleaned/lowercase value contributes and `0` means it is `""`. A gap such
as lines 1 and 3 yields mask `1010` and joins those two values once, in that
order. Repeated values such as lines 1 and 2 both equal to `A` yield `A A`.

## Separator decision

A single space prevents token concatenation, is deterministic, and preserves
all punctuation supplied by upstream lines without asserting that every line
boundary is a component boundary. This matters because source lines 1–4 have
no universal component semantics. It also handles a line already ending in
punctuation without adding a second punctuation mark and permits wrapped words,
names, or ordinals to remain a continuous phrase. The rule does not inspect
characters, infer components, or apply country-specific behavior.

The v1 comma-space rule was executed immutably in job `1759565`. Complete human
review of the fixed 500 found four questionable boundaries (review orders 59,
116, 257, and 322): two punctuation-adjacency cases and two unsupported
component-like breaks. With zero universal evidence that source line breaks
encode components, this was a general Stage 5 reconstruction defect. The v1
run and artifacts remain preserved as the first candidate attempt; they are not
overwritten or relabeled as ready.

A local PyArrow experiment was also decisive for implementation method: the
available element-wise join kernel dropped an all-null synthetic row under
skip-null semantics, so it could not implement the zero-line row contract
exactly. Stage 5 therefore uses a small reviewed per-row reconstruction helper
inside bounded Arrow batches. Newline is not used because Stage 5 outputs a
scalar candidate for later parser input, not a source-file layout.

## Appended schema

Stage 5 preserves every incoming Stage 4 field exactly and appends ten fields:

- `stage05_standard_candidate_clean`;
- `stage05_native_candidate_clean`;
- `stage05_standard_candidate_lower`;
- `stage05_native_candidate_lower`;
- `stage05_standard_candidate_available`;
- `stage05_native_candidate_available`;
- `stage05_standard_contributing_line_count`;
- `stage05_native_contributing_line_count`;
- `stage05_standard_contributing_line_mask`;
- `stage05_native_contributing_line_mask`.

Identical standard and native candidates remain two representation-specific
outputs. Exact candidate deduplication and map-back belong to Stage 6.
Component parsing belongs to Stage 7.

## Privacy and execution

Protected 35,000-row processing runs only through the fail-closed Goethe-NHR
SLURM asset at an exact pushed Git SHA. The materializer validates the accepted
Stage 4 manifest before opening its Parquet shards, processes bounded batches,
compares every upstream column independently on readback, and proves ordered
identity with a digest plus the accepted upstream duplicate-free invariant.
It does not build a population-sized Python identity set.

Controlled directories are `0700`; files are `0600`; publication is atomic to
a new immutable run directory. Failed attempts are preserved. Git-safe reports
contain aggregates and fingerprints only. HOLDOUT paths fail closed.

## Development evidence

The v1 implementation SHA was
`e69ccaaebbaeff73d88dd43018904671ee6005dd`; job `1759565` completed 35,000 to
35,000 with exact upstream and identity/order preservation. Human review was
complete for all 500 rows: 453 correct reconstructions, 43 valid but redundant
source cases, four questionable boundaries, zero questionable orders, and zero
semantic-damage cases. The automatic 499/1 bookkeeping split was not an
independent qualitative assessment and is superseded by that human evidence.

The v2 implementation is
`cd0a5ae91c3602ec20e34f7c419f1ac76f0b9160`. Authoritative job `1759603`
completed 35,000 to 35,000 with zero dropped, added, or duplicate identities;
exact identity/order and exact preservation of every Stage 4 column; and zero
reconstruction, audit, clean/lower-consistency, or idempotence mismatches. The
exact reviewed candidate/evidence head is
`97bd7fa74da358e81133ac4d38232931762d3e78`. The final accepted `main` before
post-Stage-5 repository cleanup was
`d94c715c83e4ba7233e133a7f5156e33b1ca3023`. The candidate fingerprints are:

- schema:
  `63d4cdb3707eda65c67cc5196891fa5005adce2b12eb7109554793c48c5303c3`;
- logical:
  `ba5829621fc15347d7cd4e168a48587bab896cd0be98924627876ae853dfaff2`;
- input binding:
  `7e68c33f7daa482b442eca82c00c6904ec5e38bec1b3fc598d5be4d52a6bcb9f`;
- manifest:
  `fd945163e3be0242c43b98972350904631279cb99f366baadb0a3094ab6a1fc5`.

The v2 fixed-500 artifact preserves the exact accepted 500 identity/order and
fingerprint. The v1 comma-space failure mechanism is removed, but independent
human review did not treat the targeted check alone as sufficient v2 evidence.
Independent job `1759692` selected all 170 fixed-500 rows whose multi-line
candidate changed from v1 to v2, plus nine gap-risk rows. Human review of all
179 selected rows classified 136 correct reconstructions, 37 valid upstream
redundancies, six questionable boundaries, zero questionable orders, and zero
semantic-damage cases. The questionable orders were 19, 68, 72, 116, 145, and
169.

The six findings cover ambiguous numeric adjacency and source line wraps that
appear to split a word or name. They are accepted limitations, not evidence of
content loss or reordering. A space prevents literal concatenation and adds no
component punctuation; repairing these cases would require line semantics,
numeric special cases, or word-joining heuristics that Stage 5 deliberately
does not own. The original Stage 4 lines remain exact for later parsing and
validation. No protected row text appears in Git-safe evidence.

The independent harness SHA is
`cbafa0acd20dc3fa03ccd3db8c1f62104529666a`; the qualitative-scope fingerprint
is `801fe9820cae9ae6a9aaf03b0bffcd5c3b8c316fd32b0bc1d4470ef99fd554f5`.
The harness remains reachable through the immutable annotated tag
`stage05-independent-review-cbafa0a`.
The bound protected human attestation validated successfully with SHA-256
`5981777021e55280278270c9821d9b02ccbd3fc0fd6711f11e0b833bed24cee8`.
Full aggregate metrics, performance, attempt history, and privacy gates are in
the authoritative [Stage 5 report](../../reports/development/stage05.md).
