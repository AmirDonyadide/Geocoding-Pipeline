# Stage 11 — complete bounded design review and owner decisions

## Review status and evidence boundary

**OWNER REVIEW INCORPORATED — READY TO FREEZE.** The owner reviewed revision
`63f070643a2f877536cd2777ec381a49498553ed`, approved the architecture in principle
and architecture A explicitly, and directed sixteen final clarifications.
This record incorporates them and documents one bounded author self-review of
the four-document [design](STAGE11_SEMANTIC_REQUEST_DEDUPLICATION.md). It is not
an independent implementation review, protected evaluation, final merge or
execution authorization. Unresolved owner design decisions = **0**; unresolved
bounded design defects = **0**. Actual deployment conformance is future evidence.

The review used the accepted Stage 10 contract, actual schema/validator source,
acceptance report, Stage 8/9 acceptance and publication history, repository
privacy/execution rules, and pinned public Pelias docs/source. No protected
payloads, HOLDOUT, production, remote compute/storage or Pelias were accessed.

## Complete design-defect ledger

Each row is **RESOLVED IN FINAL DESIGN**. “Required check” is a future
implementation/evaluation obligation, not executed evidence. L01–L48 retain
their original scopes with resolutions reconciled to the owner-directed model.

| ID | Challenge / possible defect | Resolution and required check |
|---|---|---|
| L01 | Text-only dedup merges different retrieval inputs | Identity binds all 19 typed fields; full payload equality, not text equality; mutate each semantic dimension synthetically |
| L02 | Free-text and structured appear textually equal | Exact mode/path and named structured slots are in the core; no flattening or mode conversion |
| L03 | Same text with different countries collapses | Exact singleton boundary and namespace in identity; no trimming/aliases/union or country-inference |
| L04 | Missing/malformed country quietly becomes unbounded | Illegal upstream state aborts publication; zero unbounded cores; Q7 stays deferred |
| L05 | Omission incorrectly equals explicit default | Closed schema permits only frozen omission states; no explicit-default collapse; wire null/empty prohibited |
| L06 | Server `defaultParameters` silently changes omitted filters | Mandatory future effective API/client/proxy compatibility gate; no hidden injected filter/focus/language; unknown/incompatible settings block execution |
| L07 | Omitted layers misleadingly called “all layers” | Public source shows an omitted-layer address optimization; policy explicitly preserves OMITTED_API_SELECTION; never replace with an all/address-only list |
| L08 | Sources/layers order or aliases normalized without proof | No list parameter support in v1; reject lists, aliases/duplicates and comma strings; future support needs a new equivalence contract |
| L09 | Machine language or script selects response language | NO_REQUEST_LANGUAGE_OVERRIDE forbids lang/Accept-Language; no inferred preference or unsupported dataset-locale promise; effective no-override language behavior is explicit and execution-bound |
| L10 | Unknown generic Pelias parameters accidentally enabled | Only Stage 10 paths/fields and policy constants supported; focus/extra boundaries/parser flags/categories/other params explicitly prohibited |
| L11 | Unicode, LF, whitespace or punctuation changed | Copy exact upstream scalar strings; strict UTF-8 with byte lengths; no cleaning/casefold/NFC or normalization library |
| L12 | Ambiguous concatenation or dictionary ordering changes IDs | Named/type-tagged, length-framed canonical binary, fixed 19-field order, full versioned domain; independent byte-vector oracle required |
| L13 | Null, missing, empty, bool, integer become interchangeable | Required schema columns, narrowly nullable values, strict type validation; bool/int/string distinctions and invalid encodings covered |
| L14 | Raw URL encoding becomes scientific identity | Typed core precedes HTTP; Stage 12 owns deterministic transport with decoded-value round-trip; no arbitrary URL canonicalizer |
| L15 | Arbitrary top-N is frozen to finish an ID | Architecture A; core explicitly non-executable, Stage 12 REQUIRED retrieval policy with explicit size; no N selected |
| L16 | Excluding size falsely promises equal/prefix-stable results | Execution IDs/cache keys include retrieval policy; no cross-size result/prefix equivalence; later empirical calibration only |
| L17 | Frozen Stage 10 handoff still says Stage 11 resolves size | Owner explicitly approves architecture A; D087 records prospective handoff refinement; Stage 10 docs/artifacts and D086 proposal history stay unchanged |
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

The table uses **OD01–OD16 in the owner's latest numbered order**. The former
O01–O16 proposal choices remain preserved at the previous design SHA; they are
not an additional open decision list. All directions below are **INCORPORATED**.
Implementation, SLURM, protected reads, HOLDOUT, production and Stage 12 remain
unauthorized; final freeze/merge of the exact design revision is next.

| Owner ID | Decision | Final disposition |
|---|---|---|
| OD01 | Architecture A | APPROVED: non-executable Stage 11 core; Stage 12 owns size/retrieval policy, transport, deployment/index, execution identity and network; no N selection |
| OD02 | retrieval_policy_binding | REMOVE under preferred option A; no per-core sentinel or concrete retrieval value; contract requires future Stage 12 binding |
| OD03 | header_policy | REMOVE generic field; semantic header meaning needs an explicit core policy, language handled through language_policy; access/protocol headers excluded |
| OD04 | Endpoint/search mode | Closed EndpointPath and SearchMode enums with exactly two legal pairs; no scheme/host/query string/deployment |
| OD05 | Exact text/structured fields | Exact Stage 10 strings; full-text requires structured nulls, structured requires text null; impossible combinations fail, never normalize |
| OD06 | Country boundary | Exact singleton uppercase alpha-2 filter distinct from structured address country (null in v1); no Q7/unbounded fallback |
| OD07 | Language | NO_REQUEST_LANGUAGE_OVERRIDE; do not claim an unverified SAFE dataset-default guarantee; explicitly bind actual no-override language/naming behavior in Stage 12; new per-request preference requires new Stage 11 contract |
| OD08 | Layers/sources | Explicit OMITTED_API_SELECTION for both; no omission/explicit-list equivalence; actual configured availability/behavior execution-bound |
| OD09 | Spatial policy | Fixed NONE for all additional spatial parameters; country boundary remains separately required; unknown focus/boundary fails |
| OD10 | Additional parameters | Singleton REJECT_UNLISTED, closed field allowlist, no key/value bag; unknown result-affecting input requires new contract version |
| OD11 | Absent/null/empty/value | Exhaustive per-field validity matrix; absent schema field invalid; nullable slots encode only legal wire omission; empty text/structured strings invalid |
| OD12 | Canonical bytes | Exactly 19 ordered named pairs, explicit type tags, uint64 big-endian lengths, strict UTF-8 and versioned domain; no locale/platform/URL dependence |
| OD13 | ID/collision guard | Full 32-byte SHA-256 of canonical bytes with contract/version; same ID and different bytes fails publication; no truncation |
| OD14 | Minimal relations | semantic_request(query_semantic_id, core); hypothesis_request_map(hypothesis_id, query_semantic_id); one sanitized aggregate object, no lineage copies |
| OD15 | Totality/orphans | Input/map rows exactly 142,677; zero missing/multiple mappings, zero orphan cores, zero collisions; any contract-impossible input fails candidate |
| OD16 | Convergence interpretation | Workload/lineage convergence only, no independent confidence; full memberships retained for Stage 13 dependency reasoning |

The owner also approved DEVELOPMENT diagnostics, deterministic bounded-memory
global reduction, privacy and publication reuse subject to implementation-time
topology preflight. Those requirements remain in the scientific/evaluation
documents. No scientific threshold or operating budget was selected.

**Unresolved owner design decisions = 0.** Remaining actions are final owner
freeze/merge and, separately, any implementation authorization. Actual Stage 12
retrieval calibration, effective service conformance, transport limits,
execution schema freeze and Stage 19 gate reconciliation remain future stage
obligations, not hidden defaults or open Stage 11 design choices.

## Final bounded critical review

One final design review challenges all fourteen owner-specified failure modes
after applying OD01–OD16. Each disposition is **RESOLVED / DESIGN PASS**, not a
claim that implementation or deployment tests ran.

| ID | Challenge | Final resolution |
|---|---|---|
| F01 | Concrete Stage 12 retrieval value enters Stage 11 ID | Removed retrieval_policy_binding entirely; schema rejects size/top-N/policy ID; N variants cannot alter core bytes |
| F02 | Transport/auth headers enter identity | Removed header_policy; explicit classification excludes credentials/protocol metadata; semantic effects need named policy/new version |
| F03 | Hostname/deployment enters identity | EndpointPath is only the two exact paths, SearchMode only two enums; deployment/access scope appears only in Stage 12 execution |
| F04 | Hidden outcome-affecting defaults remain unbound | Replaced unsupported dataset-default promise; actual no-override language resolver/fallback/data and layer/source/API behavior are explicit execution bindings; unknowns block materialization; semantic parameter injection forbidden |
| F05 | Structured/free-text requests alias | Exact paired mode/path and typed field slots; mixed or wrong-mode payload is invalid rather than flattened |
| F06 | Country filter and address country alias | Separate field/namespace; filter required, address country null; codes never substitute or union |
| F07 | Omission/default/null/empty alias | Per-field four-state matrix, strict types and mode constraints; invalid input never coerced; explicit defaults/lists not permitted |
| F08 | Arbitrary parameters bypass versioning | Closed 19-field schema and singleton policies; unknown parameters or semantic headers fail; execution binding cannot authorize a new query override |
| F09 | Source lineage lost | One retained edge per original hypothesis, exact immutable Stage 10 FKs and same-context family joins; no representatives |
| F10 | Totality silently fails | Exactly 142,677 map rows plus bidirectional key-set, PK/FK and every-edge projection checks; any violation aborts candidate |
| F11 | IDs depend on storage/order/sharding | Hash contains only versioned canonical core fields; sharding uses full digest as partition hint; physical and operational provenance separate |
| F12 | Dedup count becomes independent evidence | Workload-only labels and exact correlated memberships; no votes, confidence or correctness claim |
| F13 | Protected data leaks into reporting | Only allowlisted aggregate objects/static errors; no row IDs/queries/URLs/credentials in portable reports; controlled artifacts and future poison tests |
| F14 | Stage 12 cannot materialize deterministically | Closed path/payload/filter/omission mapping plus explicit size, pinned transport and deployment/index/language behavior; no required Stage 11 value missing; unknown execution bindings block rather than guess |

The concrete clarifications close F01/F02/F04/F07/F08/F14 together, rather than
removing fields while leaving ambiguous replacement slots. No additional
scientific relation, language choice, top-N, spatial bias or parameter is added.
The final exact relation/core field lists are solely those in the data contract.

## Completion evidence and stop

Repository-only review must verify baseline/tag ancestry, accepted fingerprint
transcription, exact upstream field names, all required design topics and the
complete ledger, local Markdown links, no code/generated data changes, unchanged
accepted Stage 0–10 files, `git diff --check`, normal branch push and main
preservation. No scientific tests are run for this prose-only change; the
conformance matrix above is for later authorized implementation.

Historical draft validation at `63f070643a2f877536cd2777ec381a49498553ed`:
documentation checks **PASS** across 10 Markdown files and
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

Fresh amended-design checks: **OWNER_DESIGN_DOCUMENT_CHECKS_PASS** across all
10 changed Markdown files and **189 local links/anchors**. The sole core table
has exactly 19 ordered fields, closed endpoint/mode types and the final policy
constants; the two relation field lists match their specified grains. Removed
header/retrieval fields, concrete size, host and deployment are absent from the
core table. L01–L48, OD01–OD16 and F01–F14 are complete without gaps.
Accepted fingerprints, append-only D087, preserved Stage 0–10 bytes, main/tag,
Stage 11-only pipeline edit scope, privacy/file allowlist and `git diff --check`
pass. No new/untracked output or implementation file exists. This validates the
documentation and bounded design review, not an encoder, materializer, service
configuration or scientific run. The exact new design SHA and remote branch
equality are checked after normal commit/push, without inserting a self-SHA.

Ready to freeze means all owner directions are incorporated and the bounded
ledger is clean. It does not mean the branch is merged, implementation is
authorized or Stage 11 DEVELOPMENT is accepted. No Stage 12 work begins.

Stage 0–10 unchanged; HOLDOUT sealed by accepted authority and not accessed;
production/Pelias untouched; no implementation/SLURM. **Stage 12 NOT STARTED.**

**NEXT: OWNER FREEZE/MERGE OF STAGE 11 DESIGN**
