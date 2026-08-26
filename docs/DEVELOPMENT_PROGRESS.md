# Library-first DEVELOPMENT progress

This Git-safe page summarizes accepted scientific state and the next explicit
gate. It contains no source rows, protected identities, or address values.

| Stage/product | Status | Dataset | Purpose | Key result |
|---|---|---|---|---|
| Stage 0 | ACCEPTED | frozen 1,405-file snapshot | immutable source inventory, schema/parser evidence, and scientific fingerprints | 140,448,582 logical rows; later six files remain outside this accepted identity |
| Benchmark Sample V1 | ACCEPTED | 35,000 DEVELOPMENT + 15,000 sealed HOLDOUT | fixed evaluation population | zero overlap and duplicate selected identities; all 1,405 source files represented |
| Stage 1 | SCIENTIFIC IMPLEMENTATION ACCEPTED | historical 206 execution; final 1,411 execution pending | lossless CSV-to-Parquet ingestion and stable source-row provenance | population-generic implementation; final production requires a new accepted 1,411 Stage 0 |
| Stage 2 | ACCEPTED ON DEVELOPMENT | 35,000 DEVELOPMENT rows | lossless schema and provenance harmonization | 35,000 → 35,000; exact 22 incoming fields preserved; four structural fields added; no raw transformation |
| DEVELOPMENT reporting | READY | fixed 500-row DEVELOPMENT-only protected review subset + full 35,000-row summaries | same-row qualitative comparison and sanitized progress reporting | fingerprint `014f7c…1dd52`; all 269 observed country strata represented; zero quota shortfalls |
| Stage 3 | V1 NOT ACCEPTED; V2 FIX ITERATION IN DEVELOPMENT | 35,000 DEVELOPMENT rows | conservative derived safe text cleaning | v1 science reproduced without semantic damage, but production scalability and punctuation evidence blocked acceptance; v2 bounded-memory implementation awaits a new authoritative run |

The rejected Stage 3 v1 candidate ran as Goethe SLURM job `1759109` from pushed commit
`8446190d1153aeb507678d0de18d027f89f0ec8d`. Its logical fingerprint is
`38df499bfaf61883832a9c718adf4cf92cfcea753337df68fa2e89afb6051bdb` and
its schema fingerprint is
`fc991ef63bd80a754114ecae6a9d3c4cf1f33a35a28581fea997edd2e4565c9b`.
Its historical Git-safe evidence remains in `reports/development/stage03_summary.json` and
`reports/development/stage03_summary.md`; the protected qualitative artifact
reuses exactly the fixed 500 identities. V2 preserves the cleaning contract and
profile while replacing total-row identity sets and repeated cleaning with
bounded streaming validation. It must produce a new immutable 35,000-row
artifact, corrected sanitized evidence, exact v1/v2 scientific equality, and a
new independent review. Stage 3 remains unaccepted and Stage 4 has not started.

## Planned sequence after Stage 3

- Stage 4: derived lowercase canonical forms while preserving raw values.
- Stage 5: separate standard/native address reconstruction.
- Stage 6: exact address-candidate deduplication with complete source map-back.
- Stage 7: independent standard/native libpostal parsing.
- Stage 8: stable SAFE component mapping.
- Stage 9: component/country/language/script-aware linguistic normalization.
- Stage 10: country/subdivision normalization.
- Stage 11: conservative country-specific address/postcode syntax.
- Stage 12: normalized/component-level deduplication.
- Stage 13: pinned-reference geographic cross-validation.
- Stage 14: street/house-number positive-evidence validation.
- Stage 15: geographically blocked constrained fuzzy matching.
- Stage 16: conservative evidence-preserving correction.
- Stage 17: geocoding component selection.
- Stage 18: separate standard/native query generation.
- Stage 19: query deduplication and final QA before SAFE Pelias.

Each address-changing stage follows: design → implementation → synthetic tests
→ full 35,000-row DEVELOPMENT metrics plus protected fixed-subset review →
tuning → acceptance/freeze → next stage. After all stages freeze, the untouched
15,000-row HOLDOUT is opened once for unbiased final evaluation.
