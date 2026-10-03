# Stage 11 — complete bounded design review and owner decisions

## Review status and evidence boundary

**DESIGN READY FOR OWNER REVIEW.** This is the author's complete critical
review of the four-document [proposal](STAGE11_SEMANTIC_REQUEST_DEDUPLICATION.md),
not an independent review, owner approval, implementation test result or
protected-data evaluation. All bounded design findings below have a specified
resolution. Future implementation checks and owner choices are distinguished
from unresolved defects; no future runtime success is asserted.

The review used the accepted Stage 10 contract, actual schema/validator source,
acceptance report, Stage 8/9 acceptance and publication history, repository
privacy/execution rules, and pinned public Pelias docs/source. No protected
payloads, HOLDOUT, production, remote compute/storage or Pelias were accessed.

## Complete design-defect ledger

Each row is **RESOLVED IN PROPOSAL**, conditional on owner approval. “Required
check” is a future implementation/evaluation obligation, not executed evidence.

| ID | Challenge / possible defect | Resolution and required check |
|---|---|---|
| L01 | Text-only dedup merges different retrieval inputs | Identity binds all 21 typed fields; full payload equality, not text equality; mutate each semantic dimension synthetically |
| L02 | Free-text and structured appear textually equal | Exact mode/path and named structured slots are in the core; no flattening or mode conversion |
| L03 | Same text with different countries collapses | Exact singleton boundary and namespace in identity; no trimming/aliases/union or country-inference |
| L04 | Missing/malformed country quietly becomes unbounded | Illegal upstream state aborts publication; zero unbounded cores; Q7 stays deferred |
| L05 | Omission incorrectly equals explicit default | Closed schema permits only frozen omission states; no explicit-default collapse; wire null/empty prohibited |
| L06 | Server `defaultParameters` silently changes omitted filters | Mandatory future effective API/client/proxy compatibility gate; no hidden injected filter/focus/language; unknown/incompatible settings block execution |
| L07 | Omitted layers misleadingly called “all layers” | Public source shows an omitted-layer address optimization; policy explicitly preserves OMITTED_API_SELECTION; never replace with an all/address-only list |
| L08 | Sources/layers order or aliases normalized without proof | No list parameter support in v1; reject lists, aliases/duplicates and comma strings; future support needs a new equivalence contract |
| L09 | Machine language or script selects response language | Both `lang` and `Accept-Language` absent; deliberate dataset-default naming; no language inference; execution binds actual data/behavior |
| L10 | Unknown generic Pelias parameters accidentally enabled | Only Stage 10 paths/fields and policy constants supported; focus/extra boundaries/parser flags/categories/other params explicitly prohibited |
| L11 | Unicode, LF, whitespace or punctuation changed | Copy exact upstream scalar strings; strict UTF-8 with byte lengths; no cleaning/casefold/NFC or normalization library |
| L12 | Ambiguous concatenation or dictionary ordering changes IDs | Named/type-tagged, length-framed canonical binary, fixed 21-field order, full versioned domain; independent byte-vector oracle required |
| L13 | Null, missing, empty, bool, integer become interchangeable | Required schema columns, narrowly nullable values, strict type validation; bool/int/string distinctions and invalid encodings covered |
| L14 | Raw URL encoding becomes scientific identity | Typed core precedes HTTP; Stage 12 owns deterministic transport with decoded-value round-trip; no arbitrary URL canonicalizer |
| L15 | Arbitrary top-N is frozen to finish an ID | Architecture A; core explicitly non-executable, Stage 12 REQUIRED retrieval policy with explicit size; no N selected |
| L16 | Excluding size falsely promises equal/prefix-stable results | Execution IDs/cache keys include retrieval policy; no cross-size result/prefix equivalence; later empirical calibration only |
| L17 | Frozen Stage 10 handoff still says Stage 11 resolves size | Explicit prospective owner-review refinement; Stage 10 docs/artifacts unchanged; D086 records proposal rather than silently rewriting accepted history |
| L18 | Concrete deployment leaks into semantic IDs | Excluded from core; Stage 12 execution binds concrete API/config/index/data and search engine/source/layer identities |
| L19 | Deployment drift silently reuses old results | Stage 12 needs verifiable immutable data/config identity and separate attempts; changed index/policy is a new execution; unknown identity blocks reuse |
| L20 | Dedup remains per context, family, role or candidate | One full-catalog hash partition/reduction domain; arbitrary cross-lineage identical cores share ID |
| L21 | Hash-prefix key or cryptographic collision loses content | Full 32-byte keys and full canonical byte equality in every group; differing bytes under one ID abort; no salted repair |
| L22 | Total counts pass despite orphan/missing/duplicate hypotheses | Exact bidirectional key-set differences, PK/FKs and per-hypothesis edge counts; zero orphan cores |
| L23 | Swapped valid edges pass PK/FK checks | Reconstruct F(h) for every hypothesis and compare mapped complete bytes and ID |
| L24 | Dedup loses STANDARD/NATIVE or candidate/source map-back | Two-column edge relation references immutable Stage 10 PK; exact source/context/role/candidate FKs retained upstream; no representative row |
| L25 | Family convergence is duplicated or lost | Join eligible upstream family rows on both context/hypothesis; no copied membership relation; 172,112 links and 142,677 hypotheses have distinct denominators |
| L26 | Zero-hypothesis contexts or source rows disappear downstream | Stage 10 decisions preserve 1,668 such contexts; source-grain future LEFT JOIN starts from 35,000 upstream rows; no fabricated Stage 11 requests |
| L27 | Redundant source/context/family tables become competing authority | Only semantic_request, hypothesis_request_map and one non-authoritative aggregate object; lineage via exact upstream binding |
| L28 | Stage 11 quietly regenerates address semantics | Primary scientific input is the accepted intent only; no raw, Stage 6/8 payload, parser or new reference lookup |
| L29 | UNSELECTED budget becomes family suppression | All 142,677 accepted hypotheses; selection status validated; no rank/family filtering or operating-budget tuning |
| L30 | Global dedup causes population-sized memory or quadratic work | Hash plus disk-backed external sort/joins, byte-bounded batches, streamed group equality, no list_agg/population dict/pairwise comparisons |
| L31 | Giant values become truncation, skip or null padding | Exact preservation or fatal resource failure; bounded memory accounts for largest value; no guessed HTTP cap |
| L32 | Transport-unschedulable request silently vanishes | Core/map retained; Stage 12 must freeze total materialization/technical outcomes for actual size/code limits, never truncate/broaden |
| L33 | Shard boundaries miss global duplicates or change IDs | Full semantic-ID partitioning and complete contributor inventory; canonical global merge; shuffled/repartitioned replay equality |
| L34 | Ephemeral local storage becomes authoritative | All adoptable payloads/edges and receipts copied/fsynced/validated/sealed on PanFS; committed reopen with local reads disabled |
| L35 | Partial/cross-SHA resume adopts stale or incomplete work | Exact executable/input/design/partition bindings, complete coverage certificates, immutable units/new attempts; preserve partial failures |
| L36 | Storage paths or operational timing change semantic identity | Only canonical semantic fields enter query ID; logical content separates physical layout/operational manifest evidence |
| L37 | Prior publication protocol assumed valid on new topology | Reuse only conditional on later same-PanFS/no-follow/permissions/primitive preflight; changed assumptions stop; no current probe |
| L38 | Stage-specific registration repeats Stage 10 naming defect | Exact Stage 11 kind and stage11_input_binding_sha256; adapter hash/registration/seal/reopen all must agree |
| L39 | Partial record or late failure reported as committed success | Permanent reservation and exclusive empty seal, prepared/committed full reopen, bounded uncertain-effect reconciliation, presentation separated |
| L40 | Protected payload leaks through IDs/errors/SQL/URLs/reports | All row-level values/IDs protected; static failure codes, allowlisted aggregates, poison synthetic tests; no external queries or portable examples |
| L41 | Dedup convergence becomes accuracy or independent support | Explicit workload-only interpretation; preserve correlated lineage for Stage 13; no votes/weights or correctness claims |
| L42 | Diagnostics multiply counts through family/role joins | Precompute exact distinct incidences externally; separate hypothesis/core/family denominators and reconcile all sums |
| L43 | “Design ready” implies measured dedup or runtime conformance | Unique count/reduction unmeasured; future test/evaluation evidence explicitly pending; no fabricated fingerprints or run report |
| L44 | Stage 12 placement bypasses existing Stage 19 gate | Gate retained; owner must separately reconcile architecture/execution permission before retrieval; no Stage 12 start |
| L45 | History/status edits mutate accepted Stage 0–10 | New Stage 11 docs plus minimal current indexes/append-only decision; accepted code/contracts/reports/review evidence unchanged |
| L46 | HOLDOUT/production mixed into a global namespace | Global reduction within bound catalog only; separate split artifacts; no cross-split discovery/cache scan; IDs alone grant no access |
| L47 | Aggregate hashing depends on circular or nondeterministic metadata | Canonical integer/rational summary excludes own/dataset/manifest hashes and runtime; physical/operational evidence separately manifest-bound |
| L48 | Common policy slot hides unresolved core parameters | Uniform closed mapping to frozen constants plus explicitly Stage12-owned depth; no other unresolved Stage 11 parameter or family override |

## Owner-review decisions

All decisions below are **PROPOSED / AWAITING OWNER APPROVAL**. Approving design
does not itself authorize implementation, SLURM, protected DEVELOPMENT reads,
HOLDOUT, production or Pelias. An owner may approve the exact package or require
revisions; neither a resolved ledger nor Git push is approval.

| Owner ID | Decision | Proposed disposition |
|---|---|---|
| O01 | Final relations and grains | One core row per globally distinct semantic request; one map edge per accepted hypothesis; one sanitized aggregate object; no copied source/context/family relation |
| O02 | Exact semantic field set | The 21 named fields/types/constants in the data contract; closed schema, unsupported parameters rejected |
| O03 | Free-text versus structured | Distinct endpoint/mode and exact named payload slots, never flattened |
| O04 | Country identity | Exact accepted single uppercase ISO alpha-2 boundary, namespace-bound; no unbounded or malformed state/Q7 |
| O05 | Layers/sources/language | OMITTED_API_SELECTION for both filters; DATASET_DEFAULT_NO_OVERRIDE, no lang/header; preserve built-in API behavior without asserting all-layer equivalence |
| O06 | Omitted/default/null | Null only means omission in permitted payload slots; no explicit-default equivalence; no hidden configuration/client/proxy injection; Stage 12 compatibility gate mandatory |
| O07 | List canonicalization | No list parameters in v1; reject supplied/empty lists; no sort/dedup or alias expansion without future proof and new contract |
| O08 | Unicode/string serialization | Exact strict UTF-8, no normalization; named typed binary framing in fixed schema order; independent byte vectors later |
| O09 | Global dedup/map-back | All 142,677 hypotheses, global full-core equality across lineage, exact total edge set, zero orphan cores, per-edge projection verification |
| O10 | query_semantic_id | Full SHA-256 of versioned domain plus canonical named core bytes; full-payload collision failure; no input/path/deployment/size in semantic ID |
| O11 | TOP-N/result-limit owner | **Stage 12**, architecture A; no scientific N here; explicit future size required, no cross-size cache/prefix assumption; prospective Stage 10 handoff refinement |
| O12 | Stage 11 ↔ Stage 12 identity | Core versus deployment/index/retrieval/execution identity; unknown or incompatible effective defaults block execution |
| O13 | Transport serializer ownership | Stage 12; Stage 11 fixes parameter/omission meaning and requires exact decoding round-trip; no URL identity or transport implementation now |
| O14 | Publication reuse | Conditional accepted Stage 9/10 state machine with stage-specific adapter and later topology preflight; Stage 8 unchanged |
| O15 | DEVELOPMENT diagnostics | Full-population exact checks, multiplicity/convergence/parameter aggregates, static failures, no protected examples or accuracy claims |
| O16 | Production-scale strategy | Byte-bounded Arrow/DuckDB hash/external sorting, deterministic partitioning, local transient plus durable PanFS, full-map checkpoints and exact resume; no pandas or pairwise path |

Remaining owner decisions are these sixteen proposals, approval of the exact
design SHA, and any later **separate** implementation authorization. Future
Stage 12 retrieval-depth calibration, concrete deployment compatibility,
transport limits, execution identity schema and the Stage 19 authorization
reconciliation are explicitly outside Stage 11's bounded design. They are not
defaults silently filled here. The Stage 10 operating budget remains UNSELECTED.

## Completion evidence and stop

Repository-only review must verify baseline/tag ancestry, accepted fingerprint
transcription, exact upstream field names, all required design topics and the
complete ledger, local Markdown links, no code/generated data changes, unchanged
accepted Stage 0–10 files, `git diff --check`, normal branch push and main
preservation. No scientific tests are run for this prose-only change; the
conformance matrix above is for later authorized implementation.

Completed local documentation checks: **PASS** across 10 Markdown files and
186 local links/anchors; 21 unique ordered core fields, L01–L48 and O01–O16
complete with no gaps. Accepted Stage 10 fingerprint transcription, input mode/
family arithmetic, baseline/tag and executable/report/review ancestry pass.
The decision-register addition is append-only; the pipeline diff is confined
to its Stage 11 section. Accepted Stage 0–10 stage records, code, tests,
launchers, scientific assets, reports and independent-review evidence are
byte-unchanged. No protected examples, client code, runtime assets or generated
scientific outputs are added. `git diff --check` passes. Git push verification
is reported with the exact resulting design commit, outside its own hashed
content; no circular self-SHA is inserted into this document.

Design ready means the proposal is coherent and the complete bounded ledger
has specified resolutions. It does not mean OWNER APPROVED, FROZEN SCIENCE,
IMPLEMENTED, EXECUTED or DEVELOPMENT ACCEPTED. The branch commit makes the
reviewable candidate immutable without merging it to main.

Stage 0–10 unchanged; HOLDOUT sealed by accepted authority and not accessed;
production/Pelias untouched; no implementation/SLURM. **Stage 12 NOT STARTED.**

**NEXT: OWNER REVIEW OF STAGE 11 DESIGN**
