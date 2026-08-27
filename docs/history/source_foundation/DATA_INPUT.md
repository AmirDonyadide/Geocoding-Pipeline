# Current source-data evidence

This document records what has been learned from filesystem metadata and read-only inspection of ten representative CSV files. It is evidence for Phase 1 design, not a substitute for the complete Phase 1 inventory.

## Observed

### Authoritative location and scope

The current source directory is:

`<CONTROLLED_SOURCE_ROOT>/`

The original run used an environment-specific protected local path. The exact
personal absolute path is intentionally omitted from current portable
documentation; accepted manifests and Git history preserve run identity.

Filesystem metadata showed:

- 206 CSV files;
- approximately 3.29 GB total apparent size;
- shard-like filenames, including the `remaining_addresses_` family;
- meaningful file-size variation.

This directory is the authoritative current source dataset. There is no currently known additional source collection that this pipeline must process.

### Observed 15-column schema

The inspected files used this exact order:

1. `id`
2. `street_address_line_1`
3. `street_address_line_2`
4. `street_address_line_3`
5. `street_address_line_4`
6. `street_address_line_1_native`
7. `street_address_line_2_native`
8. `street_address_line_3_native`
9. `street_address_line_4_native`
10. `postcode`
11. `city`
12. `region_in_country`
13. `country_iso_code`
14. `batch_priority`
15. `location_information`

Fields that must remain strings include, at minimum, `id`, every address field, `postcode`, `country_iso_code`, `batch_priority`, and `location_information`. Phase 1 must determine whether any narrower analytical typing is safe for derived staging fields.

### CSV and record behavior

Across the ten inspected files, bounded or streaming inspection observed:

- UTF-8-compatible text;
- no BOM in the inspected files;
- comma delimiter;
- a header row;
- double-quote CSV quoting, including doubled double quotes where escaping was needed;
- no observed backslash escape convention;
- 15 fields per successfully parsed logical record;
- 100,000 logical records in each inspected file;
- quoted records spanning multiple physical lines.

A physical line is therefore not equivalent to a CSV record.

Extreme anomalies included address fields of approximately 3.59 million, 8.3 million, and 19.4 million characters. One extreme logical record occupied roughly 95,462 physical lines. These values must be diagnosed and preserved or explicitly rejected under an approved rule; they must not be silently truncated, whitespace-collapsed, skipped, or converted to null.

### Address and geography patterns

- Population of address lines 1–4 varies materially. Units, suites, floors, buildings, company-like text, and geography can appear outside an assumed fixed line.
- Structured `postcode`, `city`, `region_in_country`, and `country_iso_code` fields range from nearly absent to highly populated, depending on the shard.
- Geographic information may instead appear inside free-form address lines.
- Native fields range from blank, to exact copies of non-native fields, to substantially different native-script representations.
- Postcodes include leading-zero, alphabetic, alphanumeric, hyphenated, spaced, decimal-looking, and placeholder-like forms. They are not numeric fields.
- Missing or placeholder-like text observed in the broader samples includes empty strings and forms such as `.`, `-`, `Na`, `Nan`, and `Null`. Their semantics have not been approved as equivalent.
- Address structures differ substantially across countries and shards; a single US-style interpretation is not supported.

### IDs and processing status

Within-file IDs were unique in the files for which detailed uniqueness checks were performed. No overlap was observed among those specifically compared files, but this does not establish global uniqueness.

Observed `location_information`/processing-status vocabulary includes values such as:

- `no_geocoding_information`
- `previous_geocoding_failure`
- `region_interpolated`

These are source observations, not approved final pipeline quality decisions. In particular, a historical `region_interpolated` status does not make a coordinate usable for point-level research.

## Strong sample evidence

The following characteristics were consistent across the ten inspected files and are therefore strong working evidence:

- UTF-8-compatible encoding;
- comma-separated, headered, double-quoted CSV;
- the same 15 columns in the same order;
- 100,000 logical records per inspected shard;
- preservation of all fields as strings is the safest initial contract.

The samples also strongly indicate that:

- multiline records are not unique to the first shard;
- extreme fields can occur outside the first shard;
- structured geographic completeness and country concentration differ sharply across source shards;
- native/non-native relationships and postcode formats are heterogeneous;
- line 1–4 semantics cannot be assigned globally from position alone.

These conclusions guide Phase 1 validation but are not claims about every file.

## Unknown until Phase 1

Phase 1 must verify across all 206 files:

- encoding and BOM status;
- delimiter, header, quoting, double-quote/escape behavior, line endings, and exact parser contract;
- exact schema and column order;
- logical row counts and whether the 100,000-record pattern holds;
- malformed, unparseable, empty, truncated, or wrong-column-count records;
- full distribution and maximum size of fields and logical records;
- quoted-multiline frequency;
- per-column population and missing-marker vocabulary;
- whether placeholders represent missingness consistently enough to normalize;
- global ID uniqueness, cross-file overlap, and duplicate-file status;
- country, postcode, native-script, address-line, batch-priority, and processing-status distributions;
- whether every file belongs to one source family and schema version;
- reproducible source-row identity and the exact full-collection row count.

No Phase 1 result should be inferred solely from the ten-file sample.
