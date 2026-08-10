I want you to read this entire message carefully and treat it as the initial project brief for this repository.

DO NOT IMPLEMENT ANYTHING YET.
DO NOT WRITE CODE YET.
DO NOT MODIFY THE DATA.
DO NOT CALL ANY API.
DO NOT START ANY LARGE PROCESS.
DO NOT CREATE A PRODUCTION PIPELINE YET.

Your task in this first interaction is ONLY to understand the project, its scientific objective, its infrastructure, the constraints, the decisions we have already made, the decisions that remain open, and the complete intended workflow.

After reading everything, I will ask you to summarize your understanding. We will then implement the project phase by phase.

======================================================================
1. PROJECT IDENTITY
======================================================================

This is a research-data engineering project for:

Leibniz Institute for Financial Research SAFE

The broader research work involves firm locations and environmental / remote-sensing information.

The purpose of this repository is to build a robust, reproducible, research-grade pipeline for:

1. inspecting the multi-file collection of address data;
2. validating how the source files must be read;
3. cleaning and restructuring address information;
4. creating canonical address representations;
5. identifying problematic or incomplete addresses;
6. deduplicating repeated addresses;
7. geocoding only unique addresses;
8. evaluating and selecting the best geocoding result;
9. deciding whether each coordinate is sufficiently reliable for the research;
10. validating the coordinates geographically;
11. merging the results back into the original full dataset;
12. producing an auditable and reproducible final dataset.

This should be treated as a DATA CONSTRUCTION PROJECT, not simply as a script that sends addresses to an API.

The main scientific output is not merely:

latitude + longitude

It is:

a coordinate
+
the evidence about what was matched
+
the quality of that match
+
the reason it was accepted or rejected
+
enough metadata to reproduce the decision later.

======================================================================
2. SIZE OF THE DATA
======================================================================

The authoritative current source dataset contains:

206 CSV files

with an apparent total size of approximately:

3.29 GB

There is currently no known additional 500 GB source dataset that this pipeline needs to process.

Therefore:

- we should not assume that the fully parsed in-memory representation will be close to the compressed CSV size;
- multi-million-character fields and quoted multiline records require robust CSV parsing;
- streaming, chunking, or lazy execution should be used where it improves memory safety and reproducibility;
- distributed or big-data technologies are not justified merely by the current dataset size;
- repeated full-collection scans should remain deliberate;
- intermediate formats and computation should be designed deliberately;
- we should avoid producing enormous numbers of tiny files.

The actual number of rows is not yet considered the main measure of the geocoding workload.

A very important principle is:

THE NUMBER OF UNIQUE CLEANED ADDRESSES is what determines the real geocoding workload.

The raw dataset may contain the same address many times, for example because:

- the same firm appears in multiple years;
- multiple observations refer to the same establishment;
- several rows contain identical location information;
- panel datasets repeat the same address.

Therefore we must clean and deduplicate BEFORE performing the production geocoding.

======================================================================
3. REPRESENTATIVE RAW DATA
======================================================================

A representative source schema contains columns such as:

id

street_address_line_1
street_address_line_2
street_address_line_3
street_address_line_4

street_address_line_1_native
street_address_line_2_native
street_address_line_3_native
street_address_line_4_native

postcode
city
region_in_country
country_iso_code

batch_priority
location_information

One example row looks conceptually like:

id:
960

street_address_line_1:
2711 Centerville Road

street_address_line_2:
Suite 400

street_address_line_3:
Wilmington

street_address_line_4:
Delaware 19808 USA

native address lines may contain the same or similar information.

Meanwhile the structured fields such as:

postcode
city
region_in_country
country_iso_code

may be empty.

location_information may contain:

no_geocoding_information

This means that useful structured information can sometimes be embedded inside the address lines even when dedicated columns are empty.

For this particular example, a reasonable canonical interpretation could eventually be:

address / street:
2711 Centerville Road

unit:
Suite 400

locality:
Wilmington

region:
Delaware

postalcode:
19808

country:
US

However:

THIS IS ONLY AN EXAMPLE.

The dataset is international.

We must NOT assume that all addresses follow US address conventions.

International address layouts can differ significantly.

The pipeline must therefore be conservative.

======================================================================
4. SCIENTIFIC RESEARCH REQUIREMENT
======================================================================

We have already made an important scientific decision.

The relevant research application is:

BUILDING / PLANT / BRANCH / STORE LEVEL EXPOSURE

In other words, we require POINT-LEVEL physical locations.

Examples could include:

- company buildings;
- plants;
- branches;
- stores;
- facilities;
- other physical business locations.

These coordinates may later be linked to:

- satellite imagery;
- remote-sensing measures;
- pollution data;
- biodiversity measures;
- climate variables;
- environmental exposure;
- land-cover data;
- neighborhood characteristics;
- other fine-grained spatial datasets.

Because of that, city-, region-, or country-level coordinates cannot be treated as successful matches for the main research analysis.

A coordinate representing Frankfurt, Hessen, Germany, or a country centroid is NOT equivalent to the location of a particular firm building.

======================================================================
5. FINAL ANALYTICAL QUALITY INDICATOR
======================================================================

We decided that we do NOT need multiple main analytical indicators such as:

usable_for_city_analysis
usable_for_region_analysis
usable_for_neighborhood_analysis

because the research objective is specifically point-level physical exposure.

The main final analytical variable should therefore be:

usable_for_analysis

with values:

True / False

This variable answers:

"Is this location sufficiently precise and trustworthy for the intended building / plant / branch / store-level analysis?"

We may still maintain diagnostic categories and flags internally.

For example:

quality_tier

may contain:

A
B
C
D
U

But those diagnostic categories are for:

- debugging;
- validation;
- reporting;
- auditing;
- understanding why an address was accepted/rejected.

The main research decision remains:

usable_for_analysis = True / False

======================================================================
6. IMPORTANT OPEN SCIENTIFIC DECISION
======================================================================

One issue is deliberately NOT finalized yet.

Exact address matches are clearly preferred.

Address-level interpolated matches may sometimes be acceptable.

But we have NOT yet decided the precise rule for when an interpolated address should be accepted.

We do NOT want Codex to silently decide this.

We want to examine the pilot results first.

Therefore:

address + exact + no major contradiction
    -> expected usable_for_analysis = True

address + interpolated + no major contradiction
    -> potentially usable, but FINAL POLICY IS STILL OPEN

street / venue / locality / localadmin / region / country / fallback
    -> not usable for point-level analysis

The decision about interpolated results should eventually be recorded explicitly after the pilot.

Potential evidence to consider includes:

- country agreement;
- locality agreement;
- postal-code agreement;
- street agreement;
- house-number information;
- manual validation;
- country-specific performance;
- downstream spatial resolution.

DO NOT make this methodological decision automatically.

======================================================================
7. SAFE GEOCODING SERVICE
======================================================================

The geocoding service is SAFE's internal research geocoding infrastructure.

Base URL:

https://geocode.safe-frankfurt.de

The service is operated by the SAFE Research Data Center.

It is based on:

Pelias

and uses open geographic data.

This service is intended for research workflows such as converting postal addresses into geographic coordinates and linking firm locations to spatial datasets.

It is NOT:

- a legal address registry;
- a delivery-address validator;
- a guarantee of building-level accuracy.

======================================================================
8. SAFE API AUTHENTICATION
======================================================================

All API endpoints under:

/v1/

require a personal API key.

The HTTP header is:

X-API-Key

The actual API key is secret.

CRITICAL SECURITY RULE:

NEVER put the actual API key in:

- Python source code;
- Git;
- GitHub;
- AGENTS.md;
- README;
- Markdown documentation;
- committed YAML;
- notebooks;
- SLURM scripts;
- logs;
- replication packages;
- papers;
- shared project files.

The API key should be supplied at runtime through an environment variable or another protected runtime mechanism.

A possible environment variable name is:

SAFE_GEOCODING_API_KEY

but the actual secret value must never be committed.

======================================================================
9. SAFE ENDPOINTS
======================================================================

Important endpoints include:

/v1/search

Purpose:
free-text forward geocoding.

Use when there is one combined address string.

/v1/search/structured

Purpose:
structured forward geocoding.

THIS IS THE DEFAULT / PREFERRED ENDPOINT FOR THIS PROJECT.

/v1/reverse

Purpose:
reverse geocoding from known coordinates.

/v1/autocomplete

Purpose:
interactive typeahead search.

This is generally NOT relevant for production batch geocoding.

/attribution

Purpose:
public data-attribution information.

======================================================================
10. DEFAULT SAFE QUERY
======================================================================

For tabular address data with separate components, the preferred query is:

/v1/search/structured

Typical parameters:

address
postalcode
locality
region
country
size=1

Country should preferably use a two-letter ISO code when reliable, for example:

DE
US
GB
FR

For normal batch processing, we should request:

size=1

because the normal primary operation only needs the best candidate.

Multiple candidates may later be requested selectively for ambiguous cases, but NOT for every address in the 206-file source dataset.

======================================================================
11. GEOJSON COORDINATE ORDER
======================================================================

Pelias returns GeoJSON.

GeoJSON coordinates are ordered:

[longitude, latitude]

NOT:

[latitude, longitude]

For example:

[8.6821, 50.1109]

means:

longitude = 8.6821
latitude  = 50.1109

This rule must be respected everywhere in the pipeline.

======================================================================
12. SAFE RESULT FIELDS
======================================================================

For every geocoding result, we should retain enough information for later diagnostics.

At minimum we should preserve:

label
layer
match_type
confidence
source
gid
lon
lat

Where available we should also preserve returned components such as:

country
region
locality
postalcode
street
housenumber

and operational/query metadata such as:

endpoint
query variant
fields used
fields removed
request date
request status
attempt count
HTTP status
response time
error information

======================================================================
13. MOST IMPORTANT GEOCODING PRINCIPLE
======================================================================

API SUCCESS IS NOT THE SAME AS GEOCODING SUCCESS.

A request can successfully return a feature while failing to identify the actual address.

For example, Pelias may return:

Hessen, Germany

with:

layer = region
match_type = fallback

The API call technically succeeded.

But for building-level analysis this is a failed geocode.

Therefore the existence of:

features[0]

must never automatically mean that the observation is usable.

======================================================================
14. RESULT QUALITY
======================================================================

Important Pelias fields include:

layer
match_type
confidence

But they must be interpreted together.

Typical high-quality result:

layer = address
match_type = exact

Potentially useful approximate result:

layer = address
match_type = interpolated

Too coarse for the main research objective:

layer = street
layer = venue
layer = locality
layer = localadmin
layer = region
layer = country

Low-confidence / unacceptable:

match_type = fallback

For our main point-level research design:

an address-level result is required for automatic point-level acceptance.

======================================================================
15. CONFIDENCE SCORE
======================================================================

Pelias confidence is useful diagnostic information.

However:

DO NOT SELECT OR ACCEPT A RESULT BASED ONLY ON CONFIDENCE.

For example:

confidence = 0.95
layer = country
match_type = fallback

is still NOT a good building-level geocode.

The decision should primarily use:

- layer;
- match_type;
- consistency between input and output geography;
- controlled comparison of query variants where appropriate.

Confidence can be:

- supporting evidence;
- a tie-breaker;
- a diagnostic metric.

It is not the entire quality policy.

======================================================================
16. GEOCODING DATA SOURCES AND LIMITATIONS
======================================================================

The SAFE Pelias instance uses open geospatial data sources such as:

- OpenStreetMap;
- OpenAddresses;
- Who's On First;
- GeoNames;
- related Pelias components.

Coverage differs by:

- country;
- city;
- street;
- house-number availability;
- script;
- address formatting;
- data source.

Important limitations:

- some countries have excellent address-level coverage;
- some countries have weak house-number coverage;
- historical addresses may be difficult;
- current map data may not represent past street names or past boundaries;
- PO boxes do not necessarily represent physical locations;
- headquarters/legal addresses may not equal physical production sites;
- non-Latin scripts and transliterations can produce different results;
- incomplete addresses can result in coarse fallback matches.

======================================================================
17. SAFE SERVICE ETIQUETTE
======================================================================

The SAFE geocoder is shared research infrastructure.

We must use it responsibly.

Normal default concurrency:

2 TO 4 PARALLEL REQUESTS TOTAL

This means:

2–4 total across the entire production process.

NOT:

2–4 per CPU
2–4 per SLURM job
2–4 per node
2–4 per shard

The cluster may have hundreds of CPUs.

That does NOT give us permission to send hundreds of simultaneous API requests.

The geocoding API is a separate shared service.

======================================================================
18. LARGE JOB COORDINATION
======================================================================

SAFE documentation says:

For jobs above roughly:

1 million addresses

contact the SAFE Research Data Center before starting the production job.

For very large jobs around:

10 million addresses or more

coordination with the RDC is required before running the batch.

Therefore:

we MUST first clean and deduplicate the data and determine the actual number of unique addresses.

Only then should we design the final production geocoding run.

SAFE documentation mentions that internal tests of the public HTTPS endpoint have reached roughly 70–75 structured requests per second under some conditions.

THIS IS NOT a service guarantee.

IT IS NOT permission for us to increase concurrency.

Our normal default remains:

2–4 total parallel requests

unless SAFE RDC explicitly approves otherwise.

======================================================================
19. RETRIES AND FAILURE HANDLING
======================================================================

The production client should use controlled retries.

Potentially retry:

- network errors;
- timeouts;
- HTTP 429;
- temporary 5xx errors.

Use:

- bounded retry count;
- exponential backoff;
- random jitter;
- persistent error logging;
- checkpoints.

Never implement:

while True retry forever

or any equivalent unbounded retry mechanism.

Permanent failures should remain recorded for later analysis/retry.

======================================================================
20. DEVELOPMENT ARCHITECTURE
======================================================================

We made an important architecture decision.

PRIMARY DEVELOPMENT SHOULD HAPPEN ON THE MACBOOK.

The cluster is mainly the production execution environment.

Architecture:

MacBook
    ↓
Codex + Git repository
    ↓
development
unit testing
small representative data tests
documentation
review
    ↓
approved/versioned code
    ↓
Goethe-NHR cluster
    ↓
current full source data
SLURM
full production processing
production runs

This is preferred over writing/testing everything directly on the cluster.

======================================================================
21. LOCAL REPOSITORY
======================================================================

The current local repository is:

/Users/amir/Documents/GitHub/safe_geocoding_pipeline

It is already initialized as a Git repository.

The repository contains / will contain directories similar to:

AGENTS.md
README.md
.gitignore

docs/
src/
tests/
config/
slurm/
reports/

The exact internal Python package structure can be refined later.

Do not reorganize the repository unnecessarily before understanding the project.

======================================================================
22. LOCAL DATA
======================================================================

The actual address data exists on the MacBook and/or synchronized cloud storage / drive.

Real data should NOT be committed into Git.

The repository and the data should remain logically separate.

For example:

repository:
safe_geocoding_pipeline/

data:
some separate local/Drive directory

Paths to data should be supplied using configuration.

DO NOT hard-code one absolute Mac path throughout the Python code.

======================================================================
23. CONFIGURATION DESIGN
======================================================================

The same codebase should work:

locally on macOS

and:

on Goethe-NHR Linux.

Therefore environment-specific paths should be kept in configuration.

Conceptually:

config/local.yaml

could specify a local data root.

config/cluster.yaml

could specify a cluster data root.

Business logic should not contain many statements like:

if laptop:
    /Users/amir/...
else:
    /work/footprint/...

Instead, paths should be injected from configuration.

Sensitive values such as API keys must not be stored in committed configuration.

======================================================================
24. LOCAL TESTING STRATEGY
======================================================================

"Develop locally" does NOT mean repeatedly loading the complete 3.29 GB source collection, or its potentially much larger parsed representation, into memory on the Mac.

During development we should use:

1. unit tests;
2. tiny synthetic fixtures;
3. deliberately malformed fixtures;
4. small representative samples of the real dataset when permitted;
5. sampled output from cluster diagnostics where necessary.

Potential fixture categories include:

normal_addresses.csv
malformed_rows.csv
native_addresses.csv
missing_fields.csv
duplicate_addresses.csv
conflicting_addresses.csv
po_box_addresses.csv

Synthetic fixtures can be committed if they contain no confidential/restricted information.

Real SAFE data should not be committed.

======================================================================
25. GIT AS THE SOURCE OF TRUTH FOR CODE
======================================================================

Git should track:

- source code;
- tests;
- configuration templates;
- documentation;
- SLURM scripts;
- quality rules;
- pipeline decisions.

Git should NOT track:

- the real source CSV collection;
- generated Parquet outputs;
- API credentials;
- secret files;
- production logs containing sensitive information;
- temporary files.

Before pushing internal SAFE documentation to a public/personal Git host, institutional policy should be checked.

A private or institutional Git service may be preferable.

The use of an external Git hosting provider is therefore not yet considered automatically approved.

======================================================================
26. GOETHE-NHR CLUSTER
======================================================================

Final/full production processing may use, when beneficial:

Goethe-NHR

Account:

donyadidegan

Group:

footprint

Login:

ssh donyadidegan@goethe.hhlr-gu.de

Home:

/home/footprint/donyadidegan

Personal work directory:

/work/footprint/donyadidegan

Shared project area:

/work/footprint/public

======================================================================
27. CLUSTER STORAGE
======================================================================

HOME:

/home/footprint/donyadidegan

Characteristics:

- approximately 30 GB default;
- NFS;
- relatively slow;
- backed up nightly;
- good for:
  code,
  Git repo,
  scripts,
  documentation,
  small configuration,
  executables.

WORK:

/work/footprint/donyadidegan

Characteristics:

- PanFS;
- fast parallel filesystem;
- large workspace;
- group quota;
- NOT backed up;
- intended for:
  large input,
  staging data,
  intermediate data,
  outputs,
  temporary job data.

SCRATCH:

/scratch

IS RETIRED.

NEVER use /scratch.

NODE LOCAL:

/local/$SLURM_JOB_ID

Characteristics:

- local to compute node;
- temporary;
- deleted when the job finishes;
- potentially useful for temporary high-I/O workloads;
- requested using SLURM local-storage settings when appropriate.

======================================================================
28. SHARED CLUSTER DATA
======================================================================

Shared SAFE/footprint project resources exist under:

/work/footprint/public

DO NOT modify:

/work/footprint/public

unless explicitly instructed.

It may contain:

shared code
shared environments
shared datasets
other researchers' resources

We must distinguish:

personal workspace

from:

shared project workspace.

======================================================================
29. CLUSTER LOGIN NODE RULE
======================================================================

The SSH login node is NOT a compute node.

Login nodes should be used for:

- authentication;
- small file inspection;
- file transfers;
- preparing scripts;
- Git operations;
- environment setup;
- compiling where appropriate;
- submitting jobs;
- monitoring jobs.

NEVER run heavy CPU/RAM processing directly on the login node.

Large work must go through SLURM.

======================================================================
30. SLURM
======================================================================

Goethe-NHR uses:

SLURM

for scheduling and resource management.

Main commands include:

sbatch
squeue
sacct
scancel
srun
salloc

For production jobs, we will normally submit SLURM job scripts.

======================================================================
31. RELEVANT CLUSTER PARTITIONS
======================================================================

Relevant partitions include:

test

- Intel Skylake;
- maximum approximately 2 hours;
- for testing / pre-production.

general1

- Intel Skylake;
- maximum approximately 21 days.

general2

- older Intel Broadwell / Ivy Bridge hardware;
- maximum approximately 21 days.

gpu

- AMD EPYC;
- AMD MI210 GPUs;
- maximum approximately 21 days.

gpu_test

- GPU testing;
- shared GPU environment;
- not relevant unless needed.

This project is primarily:

CPU + data engineering + I/O

There is no current reason to use GPUs.

Do NOT request GPUs merely because they exist.

======================================================================
32. CLUSTER NODE CHARACTERISTICS
======================================================================

The documentation describes hardware approximately like:

Skylake:
40 physical cores
80 logical threads
typically 192 GB RAM
some high-memory nodes around 772 GB

Broadwell:
20 physical cores
40 logical threads
around 128 GB RAM

GPU nodes:
AMD EPYC 7452
64 physical cores
128 threads
512 GB RAM
8 AMD MI210 GPUs

We should request only resources justified by the current job.

======================================================================
33. CLUSTER FILESYSTEM WARNING
======================================================================

Goethe-NHR explicitly warns users not to create huge numbers of very small files.

Therefore:

do not create millions of tiny Parquet files.

Prefer sensible output partitioning and reasonably large files.

The exact optimal size can be decided during implementation based on processing engine and access pattern.

======================================================================
34. CLUSTER PYTHON / CONDA
======================================================================

A shared Miniconda installation is available at:

/work/footprint/public/python_installs/miniconda/miniconda3

Initialization:

source /work/footprint/public/python_installs/miniconda/miniconda3/etc/profile.d/conda.sh

IMPORTANT:

DO NOT modify the shared base environment.

Personal environments should live under something like:

/work/footprint/donyadidegan/conda_envs/

For example eventually:

/work/footprint/donyadidegan/conda_envs/safe-geocoding

Environment specifications should be reproducible.

======================================================================
35. POSSIBLE CLUSTER DATA ROOT
======================================================================

A reasonable production workspace is:

/work/footprint/donyadidegan/geocoding_project/

Potential subdirectories:

raw_manifest/
staging_parquet/
cleaned_addresses/
unique_addresses/
geocoding_results/
row_level_results/
quality_control/
logs/
temp/

Do NOT create everything automatically merely because this document lists it.

Create directories when the relevant phase actually requires them.

======================================================================
36. DATA IMMUTABILITY
======================================================================

Raw data is immutable.

Never:

overwrite
edit in place
silently "fix"
replace

the original source dataset.

All cleaning must produce separate fields / datasets.

======================================================================
37. ROW TRACEABILITY
======================================================================

Every source row must remain traceable.

Preserve:

original id
source file
source row number

and eventually create a stable source-row identifier.

We have NOT yet proven that:

id

is globally unique across all CSV files.

Therefore Phase 1 must test this.

Until then:

do not rely solely on id as a global primary key.

A possible stable source-row ID could derive from:

source_file + source_row_number

but implementation details can be finalized later.

======================================================================
38. POSTAL CODES
======================================================================

Postal codes MUST be treated as strings.

Never automatically convert postal codes to integers.

Otherwise:

01234

could become:

1234

and information would be lost.

Country-specific postal-code validation may be used later.

However:

invalid-looking postal codes should generally be FLAGGED first.

Do not silently delete or "correct" uncertain postal codes.

======================================================================
39. UNICODE AND NATIVE SCRIPT
======================================================================

Preserve Unicode.

Do not strip meaningful:

accents
diacritics
non-Latin characters

Keep native-script address information separately from Latin/transliterated versions.

Do not automatically concatenate:

native address + transliterated address

into one geocoder query.

They may later become separate controlled query variants.

======================================================================
40. COMPANY NAMES VS ADDRESS COMPONENTS
======================================================================

A company name is not equivalent to a postal street address.

Do not mix:

firm name

into:

address

unless there is a very explicit methodological reason.

Company names can cause:

venue matches
institution matches
unrelated geographic results

We want primarily postal address geocoding.

======================================================================
41. UNIT / SUITE / FLOOR
======================================================================

Information like:

Suite 400
Floor 3
Building B
Unit 17

should normally be preserved separately.

For example:

unit_clean

These values may be useful for auditing or business identity.

But Pelias usually returns building/street coordinates, not an exact coordinate inside an office suite.

Therefore suite/unit information should NOT normally create separate geocoding requests or separate geographic address keys.

======================================================================
42. ADDRESS CLEANING PHILOSOPHY
======================================================================

Cleaning must be CONSERVATIVE.

Safe deterministic transformations can include:

- trimming whitespace;
- collapsing repeated whitespace;
- normalizing Unicode;
- removing control characters;
- standardizing deterministic missing-value markers;
- normalizing countries when mapping is certain;
- deterministic punctuation cleanup.

Dangerous transformations include:

automatic spelling correction
automatic city replacement
automatic country guessing
aggressive transliteration replacement

For example:

USA -> US

is deterministic.

But:

Frankfrt -> Frankfurt

may be plausible but should not automatically be assumed correct without a controlled rule.

When uncertain:

FLAG rather than silently modify.

======================================================================
43. CSV PARSING RISK
======================================================================

There has already been evidence that CSV/Parquet conversion can go wrong when the wrong parsing configuration is used.

A previous malformed conversion showed that incorrect delimiter/header/quote/escape assumptions can cause an entire row to appear inside one column.

Therefore existing files must not automatically be trusted simply because they have:

.csv

or:

.parquet

extensions.

Phase 1 must verify the actual source format.

We should inspect things such as:

delimiter
encoding
header
quote character
escape character
column count
schema
malformed rows
quoted line breaks

Do NOT hard-code one CSV dialect for all files before verifying it.

======================================================================
44. PARQUET STAGING PHILOSOPHY
======================================================================

CSV is useful as source data, but repeated analysis of the complete 206-file collection may still be inefficient.

After parsing is verified, we plan to create a controlled staging dataset, likely using:

Parquet

because it is:

columnar
compressed
typed
efficient for analytical processing.

But the source-to-Parquet conversion must be VALIDATED.

We must not blindly trust a previous Parquet conversion.

======================================================================
45. PHASE 0 — RESEARCH REQUIREMENT
======================================================================

STATUS:

DECIDED.

Use case:

building / plant / branch / store-level exposure.

Required precision:

point/address level.

Final analytical variable:

usable_for_analysis

No separate city/regional usability variables are needed for the main study.

Address exact:
expected acceptable if geographically consistent.

Address interpolated:
potentially acceptable; final policy deferred until pilot.

Coarse/fallback:
not acceptable for point analysis.

======================================================================
46. PHASE 1 — INVENTORY THE RAW FILES
======================================================================

Goal:

Understand the complete raw dataset BEFORE altering it.

Do NOT start by concatenating all files.

Create an inventory / manifest.

Potential file-level fields include:

file_name
file_path
file_size
modified_date
encoding
delimiter
quote_character
escape_character
header_status
column_count
column_names
schema
row_count
parse_error_count
malformed_row_count
empty_row_count
schema_version

Also investigate:

- whether all files use the same schema;
- whether columns appear in the same order;
- whether all files have headers;
- whether encoding differs;
- whether delimiters differ;
- whether quoted line breaks occur;
- whether duplicate files exist;
- whether id is globally unique;
- whether IDs repeat;
- whether files contain unusual/malformed records.

Address-specific completeness metrics should include the share of observations with:

street_address_line_1
street_address_line_2
street_address_line_3
street_address_line_4
native address fields
postcode
city
region_in_country
country_iso_code
batch_priority
location_information

We should also examine:

missingness per column.

The inventory implementation must be:

streaming / chunked / out-of-core.

It must NOT require loading all source files, or the full parsed dataset, into memory at once.

LOCAL DEVELOPMENT:

develop and test inventory code on tiny/sample files.

FINAL LARGE INVENTORY:

run on Goethe-NHR through SLURM.

PHASE 1 GATE:

Do not move to Phase 2 until:

- files can be parsed consistently;
- parser rules are documented;
- expected schemas are understood;
- malformed rows can be detected;
- row counts are reproducible.

======================================================================
47. PHASE 2 — CONTROLLED STAGING DATASET
======================================================================

Once Phase 1 determines the correct parsing rules, convert source data into a controlled analytical staging format.

Likely:

Parquet.

Important:

Do NOT make up parser parameters.

Use the results verified in Phase 1.

During conversion:

preserve every original source column.

Add fields such as:

source_file
source_row_number
stable_source_row_id

Preserve:

Unicode
postal codes as strings
native-script text
raw address content

Malformed/rejected records must be written to explicit diagnostics.

Never silently discard them.

Validate each conversion using:

source row count vs staging row count
schema comparison
column count
ID comparison
missingness comparison
sampled cell equality
postal code preservation
Unicode/native text preservation

Each file/dataset should receive a clear validation status such as:

PASS
FAIL

Existing Parquet should be treated as untrusted until it passes the same validation.

Avoid generating a huge number of small Parquet files.

Production conversion should run through SLURM.

======================================================================
48. PHASE 3 — CANONICAL ADDRESS TABLE
======================================================================

Goal:

Create structured, cleaned address components while preserving every raw field.

Potential derived columns include:

stable_source_row_id
original_id

street_clean
house_number_clean
unit_clean
building_clean

postalcode_clean
locality_clean
region_clean
country_clean

country_raw
country_parse_method
country_parse_confidence

native components where useful

address_parse_status
address_completeness_class
address_conflict_flags

Potentially:

address_query_variant

Rules:

- do not overwrite originals;
- preserve native/transliterated versions separately;
- keep units/suites separately;
- do not mix company names into street fields;
- use deterministic country normalization;
- preserve postal codes as strings;
- do not aggressively correct uncertain data.

If dedicated columns are empty but the address lines contain structured information, information may be derived when sufficiently deterministic.

Example:

line1 = 2711 Centerville Road
line2 = Suite 400
line3 = Wilmington
line4 = Delaware 19808 USA

could potentially yield:

address = 2711 Centerville Road
unit = Suite 400
locality = Wilmington
region = Delaware
postalcode = 19808
country = US

But again:

do NOT make a US-specific parser and assume it works globally.

International parsing strategy must be investigated.

======================================================================
49. PHASE 4 — INPUT CONSTRAINTS AND QUALITY FLAGS
======================================================================

Before geocoding, create explicit input-quality indicators.

Potential flags:

has_country
has_locality
has_postalcode
has_street
has_house_number
has_unit

is_po_box
is_incomplete
is_historical
has_native_version

has_conflicting_country
has_conflicting_postcode
has_conflicting_locality

has_oversized_field

is_ready_for_geocoding

Suggested completeness classes:

A:
country + locality + street + house number + postal code

B:
country + locality + street + house number

C:
country + locality + street, but no house number

D:
country + locality only

E:
country only or severely conflicting

X:
cannot safely parse

For point-level research:

A and B are strong candidates.

C may still be worth querying but must not be assumed to produce a valid building result.

D, E, X should not be considered successful point-address inputs.

However:

do not prematurely delete unresolved observations.

Keep them for:

diagnostics
potential rescue logic
manual review
reporting.

DO NOT send country-only records just to get a country centroid and then treat the centroid as a firm location.

======================================================================
50. PHASE 5 — STABLE ADDRESS KEYS AND DEDUPLICATION
======================================================================

This is one of the most important scaling phases.

Goal:

create one canonical geographic address representation and identify unique locations.

Potential canonical key components:

country_clean
postalcode_clean
locality_clean
region_clean
street_clean
house_number_clean

Then generate a stable versioned hash, for example:

address_key_v1 = SHA256(versioned canonical representation)

The version is important because cleaning/key rules may later evolve.

Keep both:

canonical_address
address_key_v1

Do NOT normally include:

unit/suite
firm name
internal company ID
year
batch file name
source row

because those normally do not change the building location.

Two main outputs:

A. ROW-LEVEL MAPPING

stable_source_row_id
original_id
address_key_v1

B. UNIQUE-ADDRESS TABLE

address_key_v1
canonical_address

address
postalcode
locality
region
country

native query fields where relevant

completeness_class
quality flags

number_of_original_rows
batch_priority

ONLY UNIQUE ADDRESSES should be sent to SAFE.

Phase 5 should report:

total source rows
eligible rows
number of unique addresses
deduplication ratio
unique addresses by country
unique addresses by completeness class
top repeated addresses

This result determines the real production geocoding workload.

======================================================================
51. PHASE 6 — CONTROLLED QUERY STRATEGY
======================================================================

We do NOT want to generate dozens of arbitrary address permutations.

Use a controlled query ladder.

PRIMARY QUERY:

/v1/search/structured

with all reliable available components:

address
postalcode
locality
region
country
size=1

If the primary result is sufficiently good:

stop.

Only unresolved / low-quality cases should be considered for controlled rescue.

Possible rescue strategies:

1. remove a postal code known to be invalid/conflicting;
2. remove a region known to conflict;
3. use a deterministic alternative street representation;
4. use native-script structured address;
5. use transliterated structured address;
6. use free-text /v1/search only when structured decomposition is genuinely unreliable.

Every query attempt should record:

address_key_v1
query_variant
endpoint
fields_used
fields_removed
reason_for_variant

Do NOT try arbitrary permutations of every field.

Do NOT request multiple candidates for every address.

For selected ambiguous cases, a later stage may request multiple candidates for comparison.

======================================================================
52. PHASE 7 — PILOT BEFORE PRODUCTION
======================================================================

Do NOT immediately geocode the complete unique-address table.

Pilot first.

PILOT 1:

approximately 1,000 UNIQUE addresses.

Sampling should be reproducible and stratified.

It should represent:

different countries
different completeness classes
Latin/native scripts
missing postcode
missing house number
different source files/datasets
different batch priorities
historical/uncertain cases if present
other important quality groups

Measure:

request success rate

address exact rate
address interpolated rate

street/venue/locality rate

region/country/fallback rate

unmatched rate

country conflict rate
locality conflict where measurable

latency
HTTP failures
retry rate

expected production duration

likely rescue-query rate

countries / address types with weaker results

PILOT 1 should also produce candidates for manual validation.

After Pilot 1:

STOP.

Do NOT automatically launch Pilot 2.

Based on results, decide whether Pilot 2 should contain something like:

10,000
25,000
50,000
100,000

unique addresses.

Before production:

- parsing must be verified;
- query construction must be verified;
- response parsing must be verified;
- result-quality logic must be defined;
- SAFE RDC coordination must occur if scale requires it.

======================================================================
53. MANUAL GROUND-TRUTH SAMPLE
======================================================================

Where feasible, create a manually validated sample.

Why?

Because:

Pelias confidence
layer
match_type

are useful, but actual accuracy matters.

Manual checking may compare returned addresses/coordinates against:

known locations
maps
reliable external references
expected geography

This helps determine whether:

exact
interpolated

matches are truly reliable enough for the research.

======================================================================
54. PHASE 8 — SAFE PRODUCTION EXECUTION
======================================================================

Production architecture should be restartable.

Conceptually:

unique-address dataset
    ↓
controlled queue
    ↓
2–4 total request workers
    ↓
checkpointed results

Requirements:

- geocode UNIQUE addresses only;
- do not geocode all original panel rows;
- do not repeat completed requests;
- durable checkpoints;
- safe restart after failure;
- bounded retries;
- exponential backoff;
- random jitter;
- persistent result/error status;
- no secrets in logs.

Operational fields may include:

request_status
attempt_count
http_status
request_timestamp
response_time_ms
error_type
last_error
completed_at

Sharding may be used for:

checkpointing
organization
restartability

BUT NOT as a way to bypass the total API concurrency limit.

For example:

10 shards × 4 workers

would be 40 requests and would violate the intended 2–4 total policy.

Before a production run, report:

number of unique addresses
planned number of API calls
expected rescue calls
approved concurrency
estimated runtime
SLURM resources
checkpoint procedure
restart procedure

Then WAIT FOR EXPLICIT APPROVAL.

======================================================================
55. PHASE 9 — SELECT THE BEST RESULT
======================================================================

Selection must be:

deterministic
explainable
auditable

Do NOT simply select the highest confidence.

Suggested hierarchy:

STEP 1 — STRONG CONTRADICTIONS

Reject/flag when:

returned country conflicts with reliable input country

coordinate is geographically impossible for the expected country

returned locality clearly conflicts with input

apparently precise result has major street/house-number contradiction

STEP 2 — SPATIAL PRECISION

For the main study:

address-level result is required for point acceptance.

street
venue
locality
localadmin
region
country

are too coarse for building-level analysis.

STEP 3 — MATCH TYPE

Prefer:

exact

Potentially consider:

interpolated

Reject:

fallback

for the main point-level analysis.

STEP 4 — COMPONENT AGREEMENT

Compare:

country
region
postal code
locality
street
house number

STEP 5 — CONFIDENCE

Use confidence only as:

support
diagnostic
tie-breaker

STEP 6 — QUERY VARIANTS

If primary and rescue/native/transliterated queries produced different candidates:

compare them deterministically.

Store:

selected_query_variant
selected_candidate_index
selection_reason

and component-agreement/conflict indicators.

======================================================================
56. PHASE 10 — TRUST CATEGORIES
======================================================================

Maintain diagnostic quality tiers.

Suggested categories:

TIER A

address
exact
no major geographic contradiction

Interpretation:
high-quality point match

TIER B

address
interpolated
no major geographic contradiction

Interpretation:
estimated address-level point

Final acceptance policy:
NOT YET LOCKED

TIER C

street
venue
locality
localadmin

or otherwise too coarse

Interpretation:
geographically useful for some purposes but NOT for our main point-level analysis

TIER D

region
country
fallback
major contradiction

Interpretation:
unacceptable point result

TIER U

unmatched
unresolved
permanent request failure
unparseable address

Then final:

A -> usable_for_analysis = True

B -> determined by explicit future interpolation policy

C -> False
D -> False
U -> False

Keep:

quality_tier
usable_for_analysis
acceptance_reason
exclusion_reason
requires_manual_review

======================================================================
57. PHASE 11 — VALIDATE THE GEOCODED COORDINATES
======================================================================

Even selected address matches need validation.

Basic checks:

longitude between -180 and 180
latitude between -90 and 90

detect:

[0,0]

missing coordinates

country mismatches

region mismatches where data permits

suspicious repeated coordinates

large groups of addresses returning exactly the same location

possible:

country centroids
region centroids
city centers
fallback coordinates

unexpected clusters
geographic outliers

points obviously outside expected country

Potential spatial validation:

point-in-country
point-in-region

using documented boundary/reference data.

DO NOT silently download arbitrary boundary datasets.

Before introducing an external geographic dataset, document:

source
license
vintage/date
coverage
why it is appropriate

======================================================================
58. REPEATED COORDINATES
======================================================================

Repeated coordinates deserve explicit diagnostics.

Calculate things such as:

number of unique coordinates
largest coordinate-frequency groups
share of rows at repeated coordinates
layer/match_type distribution among repeated coordinates

Many observations at one identical coordinate may indicate:

a real shared building

OR:

a city centroid
region centroid
country centroid
fallback behavior
parsing error

It must be investigated rather than assumed.

======================================================================
59. SAMPLE-SELECTION BIAS
======================================================================

Geocoding success may not be random.

For example, failure rates may differ by:

country
year
industry
firm size
source dataset
address type
native script
address completeness

This can affect the composition of the empirical sample.

Therefore quality reporting should eventually examine:

geocoding rate
acceptance rate
fallback rate
unmatched rate

across relevant research groups.

Do NOT simply remove failed geocodes and ignore who was removed.

======================================================================
60. PHASE 12 — MERGE BACK TO THE FULL DATA
======================================================================

Once unique addresses have final selected results:

merge them back to the complete row-level dataset.

Use:

address_key_v1

Perform a:

LEFT JOIN

Do NOT merge using:

street text alone

or:

latitude/longitude

or:

fuzzy approximate address strings

unless a separately justified methodology is later approved.

The original rows must remain present.

Validate:

source row count == final row count

unless an explicitly documented rule explains otherwise.

Check for:

unexpected one-to-many explosions
duplicate join keys
missing mappings

Final row-level dataset should retain:

original source fields

cleaned address fields

stable_source_row_id
address_key_v1

selected_query_variant
selected_candidate_index

found
label
layer
match_type
confidence
source
gid
lon
lat

quality_tier
selection_reason
usable_for_analysis
is_fallback
requires_manual_review
error

geocoding_endpoint
geocoding_date
pipeline_version

======================================================================
61. PHASE 13 — REPRODUCIBILITY AND AUDIT
======================================================================

The final pipeline must be reproducible.

Version things such as:

parser_version
cleaning_rules_version
address_key_version
query_strategy_version
candidate_selection_version
quality_rules_version
pipeline_version

Retain:

raw-file manifest
CSV/parser configuration
schema reports
rejected/malformed-row logs
cleaning rules
deduplication statistics
query metadata
response metadata
selected candidates
selection reasons
manual corrections
quality reports
Git commit
geocoding date
endpoint
service/API version information

Important code and documentation must not exist only under:

/work

because /work is not backed up.

======================================================================
62. PROCESSING STATE MACHINE
======================================================================

The pipeline should make processing states explicit.

Potential states:

RAW

PARSE_FAILED

PARSED

NOT_ELIGIBLE

READY_FOR_PRIMARY_QUERY

PRIMARY_HIGH_QUALITY

PRIMARY_LOW_QUALITY

READY_FOR_RESCUE_QUERY

RESCUE_HIGH_QUALITY

RESCUE_LOW_QUALITY

MANUAL_REVIEW

UNRESOLVED

FINAL_ACCEPTED

FINAL_EXCLUDED

These names can later be refined.

The important concept is:

do not lose the processing history.

An observation should not simply jump from raw data to a final coordinate with no trace of what happened.

======================================================================
63. ENGINEERING PRINCIPLES
======================================================================

This is a research infrastructure / data-engineering project.

Priorities are:

correctness
reproducibility
auditability
scalability
safe handling of data
clear quality rules

not clever code.

Prefer simple, understandable implementations.

Functions should be:

testable
deterministic where possible
modular

Rules should be explicit.

Important constants/policies should be configurable when appropriate.

Do not introduce unnecessary technologies.

Before choosing among:

pandas
Polars
PyArrow
DuckDB
Dask
other tools

consider:

the verified 206-file / approximately 3.29 GB compressed-CSV scale
potential expansion of the parsed in-memory representation
memory usage
streaming
parallelism
maintenance
dependency complexity
cluster compatibility

Explain important technology choices rather than introducing them silently.

======================================================================
64. TESTING REQUIREMENTS
======================================================================

Deterministic transformation logic should have unit tests.

Examples:

postal-code handling

Unicode normalization

country normalization

address-key creation

quality classification

candidate selection

row mapping

query construction

response parsing

Tests should include difficult cases.

Do not rely only on testing the "happy path."

======================================================================
65. ERROR HANDLING
======================================================================

Never silently:

drop rows
coerce critical columns incorrectly
ignore malformed files
convert postal codes to integers
overwrite source fields
accept parser errors

When an error could corrupt data:

FAIL LOUDLY

or:

record it explicitly in a rejected/diagnostic dataset

depending on the appropriate phase.

======================================================================
66. LOGGING AND METRICS
======================================================================

Each phase should report useful counts.

Examples:

input rows
output rows
malformed rows
missingness
unique addresses
addresses by completeness class
API success
API failure
exact matches
interpolated matches
fallback matches
accepted
rejected
manual review
join counts

These counts are important for identifying silent pipeline failures.

======================================================================
67. PHASE REPORTS
======================================================================

After each major phase, produce a concise documentation/report file describing:

- objective;
- inputs;
- outputs;
- implementation;
- assumptions;
- tests;
- counts;
- findings;
- unresolved issues;
- next decision.

Potential naming:

docs/PHASE01.md
docs/PHASE02.md
...

Do not automatically move to the next phase after generating the report.

======================================================================
68. DEVELOPMENT WORKFLOW WITH CODEX
======================================================================

We want to work ONE PHASE AT A TIME.

For every phase:

1. read the repository instructions and relevant documents;
2. inspect existing code;
3. inspect only the minimum necessary data/sample;
4. tell me what you understand;
5. propose the design;
6. identify assumptions;
7. identify risks;
8. WAIT if an important scientific decision is unclear;
9. implement the current phase;
10. write tests;
11. run safe local tests;
12. summarize results;
13. update phase documentation;
14. STOP.

Do NOT automatically implement the next phase.

======================================================================
69. LOCAL VS CLUSTER EXECUTION
======================================================================

The intended workflow is approximately:

MACBOOK

Codex
↓
write/review code
↓
unit tests
↓
small/synthetic test data
↓
git commit
↓
approved code

THEN:

GOETHE-NHR

sync / clone repository
↓
cluster config
↓
SLURM
↓
current full source data
↓
production outputs

We do NOT intend to write and test every small code change on the cluster.

======================================================================
70. GIT WORKFLOW
======================================================================

Git should preserve approved project evolution.

Commit after meaningful/approved phases.

Example commits:

Add project context and methodology

Implement Phase 1 raw-file inventory

Implement Phase 2 validated staging

Implement Phase 3 canonical addresses

etc.

Never commit secrets or real large datasets.

Before using an external hosted Git service for internal research material:

check project/institutional policy.

======================================================================
71. DATA MOVEMENT
======================================================================

The actual data currently exists locally/on Drive and may later be transferred to Goethe-NHR.

Data transfer is separate from Git.

Git transfers:

code
configuration templates
documentation
tests

Large data should later be moved separately to:

/work/footprint/donyadidegan/...

using an approved mechanism such as:

rsync

when the cluster data layout has been decided.

Do NOT copy the complete source collection to the cluster before we know what Phase 1/2 expects unless specifically instructed.

======================================================================
72. RAW DATA VS GENERATED DATA IN GIT
======================================================================

Repository should ignore:

*.csv
*.tsv
*.parquet

when they are real/generated data.

Small synthetic test fixtures can be explicitly excepted if needed.

Never allow a broad `git add .` to accidentally commit confidential source data.

======================================================================
73. SECURITY
======================================================================

Do not expose:

SAFE API keys

passwords

SSH secrets

confidential research data

personal data

credentials

The pipeline must support secure runtime configuration.

Logs should never print authorization headers.

======================================================================
74. HISTORICAL ADDRESSES
======================================================================

If addresses contain historical information:

flag them where identifiable.

Do not assume current Pelias/open-map data accurately reflects:

past street names
past city names
past borders
past building locations

Historical observations may need separate evaluation.

======================================================================
75. PO BOXES
======================================================================

PO boxes should be identified when possible.

A PO box generally does not represent the physical building location required for our exposure analysis.

Therefore PO-box status should be preserved as a quality/input flag.

======================================================================
76. LOCATION CONCEPT
======================================================================

An important conceptual issue is:

What type of address does each record represent?

Possibilities include:

legal registration address
headquarters
plant
branch
store
facility
other business location

Do NOT automatically interpret all addresses as production locations.

Preserve available information about address/location type.

This is relevant for economic interpretation later.

======================================================================
77. STATA CONTEXT
======================================================================

Some SAFE/finance researchers may work primarily in Stata.

The geocoding pipeline itself should preferably remain in Python or another suitable scalable data-processing environment.

A research-friendly workflow is:

source/research data
↓
Python geocoding/data-engineering pipeline
↓
flat, validated output table
↓
merge/use in Stata if needed

We do NOT need to parse complex GeoJSON directly in Stata.

======================================================================
78. REPRODUCIBILITY METHODS NOTE
======================================================================

Eventually, a paper/internal documentation should be able to state things like:

- SAFE Geocoding Service was used;
- structured endpoint was used;
- street/locality/postal code/country components were supplied when available;
- top candidate was requested;
- returned layer, match type, confidence, source, GID, and coordinates were retained;
- exact/interpolated point-level rules were defined;
- fallback/coarse matches were excluded;
- geocoding date was recorded;
- validation procedures were performed.

The pipeline should naturally make producing such documentation possible.

======================================================================
79. SAFE API VERSION
======================================================================

Current project documentation states that the SAFE public API instance uses the pinned image:

pelias/api:v7.8.0

Pelias may display:

API Version: 1.0

which refers to the interface/engine version rather than the Docker image tag.

For final research reproducibility:

confirm the actual service version at the time of production rather than assuming it never changed.

======================================================================
80. PROJECT CONTACT FOR LARGE GEOCODING JOBS
======================================================================

SAFE Research Data Center contact:

datacenter@safe-frankfurt.de

Relevant for:

API access
keys
large jobs
methodological questions
request-rate coordination

======================================================================
81. THINGS CODEX MUST NOT DO WITHOUT EXPLICIT APPROVAL
======================================================================

DO NOT:

run the full 206-file source dataset without explicit approval

start production geocoding

send millions of API requests

increase API concurrency beyond agreed limits

launch many SLURM geocoding jobs

modify raw source data

delete raw data

modify shared /work/footprint/public resources

put API keys into files

push confidential data to Git

choose the interpolated-match policy silently

download new external spatial datasets without explaining them

use GPUs without justification

run heavy work on cluster login nodes

create millions of tiny files

silently drop malformed rows

silently change addresses

silently infer countries/cities when uncertain

move automatically from one major phase to the next

======================================================================
82. THINGS CODEX SHOULD DO
======================================================================

DO:

read existing repository context before coding

ask/flag important unresolved methodological decisions

preserve traceability

keep raw fields

make transformations explicit

make paths configurable

write tests

use small local tests during development

design code for the verified 206-file / approximately 3.29 GB source scale

produce auditable phase outputs

use Git-friendly code/documentation

design cluster execution through SLURM

be conservative with international address parsing

treat geocoding quality as a scientific measurement problem

keep API use controlled

======================================================================
83. CURRENT PROJECT STATUS
======================================================================

We are at the very beginning.

The scientific roadmap has been discussed and approved conceptually.

Phase 0 is decided.

Phases 1–13 are conceptually agreed.

However:

the implementation has NOT yet been built.

We have NOT yet:

run the raw inventory
validated all CSV dialects
created staging Parquet
created canonical addresses
determined number of unique addresses
performed the pilot
defined final interpolated acceptance policy
run production geocoding
merged final results

Therefore:

do not assume outputs from these phases already exist.

======================================================================
84. CURRENT LOCAL REPOSITORY STATUS
======================================================================

The local Git repository has been created at:

/Users/amir/Documents/GitHub/safe_geocoding_pipeline

It contains basic folders such as:

config
docs
reports
slurm
src
tests

and files such as:

AGENTS.md
README.md
.gitignore

At this stage they may still be empty or incomplete.

Do not assume project documentation already exists unless you inspect it.

======================================================================
85. WHAT I WANT FROM CODEX RIGHT NOW
======================================================================

Again:

DO NOT IMPLEMENT THE PIPELINE YET.

DO NOT EDIT FILES YET.

DO NOT PROCESS DATA YET.

First, read this entire project brief carefully.

Then respond with a detailed structured summary covering:

1. What is the scientific objective?

2. Why do we need building/address-level coordinates rather than city/region coordinates?

3. What exactly should `usable_for_analysis` represent?

4. What is the unresolved decision regarding interpolated matches?

5. What is the source-data situation?

6. What are the most important raw-data safety rules?

7. What are the most important international address-cleaning rules?

8. Why do we deduplicate before geocoding?

9. What is the SAFE Geocoding Service and which endpoint should normally be used?

10. What result fields need to be stored?

11. Why is API success not the same as geocoding success?

12. How should layer, match_type, confidence, and geographic agreement be used?

13. What are the SAFE API concurrency and retry restrictions?

14. What belongs on the MacBook versus Goethe-NHR?

15. What are the important Goethe-NHR storage and SLURM rules?

16. Explain all pipeline phases from Phase 0 through Phase 13.

17. What are the major gates where the project must STOP for review?

18. Which decisions are already locked?

19. Which methodological decisions are still open?

20. Which actions are you explicitly prohibited from performing without approval?

21. What should be our immediate next step?

After that:

STOP.

Do not create code until I review your summary and explicitly tell you to begin Phase 1.
