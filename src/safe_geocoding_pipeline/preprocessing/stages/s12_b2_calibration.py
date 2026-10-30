"""Frozen full-C/tail/paired witness retention tests, never N selection."""

from __future__ import annotations

from pathlib import Path
import json
import hashlib
from dataclasses import dataclass
from typing import Callable

from . import s12_b2_contract as b
from . import s12_b2_catalog as catalogs
from . import s12_retrieval_contract as c
from . import s12_response as response
from . import s09_reference_contract as s9
from . import s12_b2_diagnostics as diagnostics

PROTOCOL = "stage12_calibration_protocol_v1"
K_FIELDS = tuple(
    x
    for x in c.columns("request_candidate")
    if x
    not in (
        "request_execution_id",
        "rank",
        "response_sha256",
        "raw_feature_sha256",
        "feature_byte_offset",
        "feature_byte_length",
        "confidence",
        "match_type",
    )
)


def order(domain, q):
    return c.identity(
        domain, [("protocol_version", PROTOCOL), ("query_semantic_id", q)]
    )


def select(
    catalog,
    scratch: Path,
    *,
    C: int,
    T: int,
    supported: int,
    authority,
    decision_hash: str,
):
    """Pre-outcome greedy quota coverage and deterministic stratum round-robin."""
    catalog.verify()
    for n in (C, T, supported):
        b.uint(n, True)
    b.require(5 <= C < T <= supported <= 40 and T > 10, "B2_CALIBRATION_LIMITS")
    authority.require(
        "calibration_depths",
        decision_hash,
        {"C": C, "T": T, "supported": supported, "binding": catalog.binding},
    )
    db = catalogs.connect(scratch)
    db.execute("attach database ? as input", (str(catalog.path),))
    db.executescript(
        """create table chosen(q blob primary key,ordinal integer);create table covered(cell blob,source blob,primary key(cell,source));create table quota(cell blob primary key,n integer);create table ordering(q blob primary key,tie blob,pair blob);"""
    )
    db.execute(
        "insert into quota select cell,min(2,count(distinct source)) from input.membership group by cell"
    )
    for (q,) in db.execute("select q from input.semantic order by q"):
        db.execute(
            "insert into ordering values(?,?,?)",
            (
                q,
                order("SAFE:stage12-tail-sample:v1", q),
                order("SAFE:stage12-paired-sample:v1", q),
            ),
        )
    selected = 0

    def missing():
        return db.execute(
            "select count(*) from quota z where (select count(*) from covered c where c.cell=z.cell)<z.n"
        ).fetchone()[0]

    while missing() and selected < 2000:
        row = db.execute(
            """select m.q,count(distinct m.cell) gain from input.membership m join quota z on z.cell=m.cell join ordering o on o.q=m.q where not exists(select 1 from chosen x where x.q=m.q) and (select count(*) from covered cc where cc.cell=m.cell)<z.n and not exists(select 1 from covered cc where cc.cell=m.cell and cc.source=m.source) group by m.q order by gain desc,o.tie,m.q limit 1"""
        ).fetchone()
        if row is None:
            break
        selected += 1
        db.execute("insert into chosen values(?,?)", (row[0], selected))
        db.execute(
            "insert or ignore into covered select cell,source from input.membership where q=?",
            (row[0],),
        )
    b.require(missing() == 0, "INSUFFICIENT_CALIBRATION_COVERAGE")
    # Round-robin complete strata, request order by full domain hash then full ID.
    depth = 0
    while selected < min(2000, catalog.binding["semantic_count"]):
        added = 0
        for body, ordering_hash in db.execute(
            "select body,min(ordering) from input.stratum group by body order by min(ordering),body"
        ):
            row = db.execute(
                "select s.q from input.stratum s join ordering o on o.q=s.q where s.body=? and not exists(select 1 from chosen c where c.q=s.q) order by o.tie,s.q limit 1",
                (body,),
            ).fetchone()
            if row:
                selected += 1
                added += 1
                db.execute("insert into chosen values(?,?)", (row[0], selected))
                if selected == min(2000, catalog.binding["semantic_count"]):
                    break
        if not added:
            break
        depth += 1
    tail = [q.hex() for (q,) in db.execute("select q from chosen order by q")]
    paired = [
        q.hex()
        for (q,) in db.execute(
            "select c.q from chosen c join ordering o on o.q=c.q order by o.pair,c.q limit 400"
        )
    ]
    # Tail IDs <=2000 and paired<=400 are explicitly bounded scientific subsets.
    coverage = []
    for cell, n in db.execute("select cell,n from quota order by cell"):
        actual = db.execute(
            "select count(distinct m.source) from input.membership m join chosen c on c.q=m.q where m.cell=?",
            (cell,),
        ).fetchone()[0]
        available = db.execute(
            "select count(distinct source) from input.membership where cell=?", (cell,)
        ).fetchone()[0]
        coverage.append(
            {
                "cell": json.loads(cell),
                "required_sources": n,
                "selected_sources": actual,
                "available_sources": available,
            }
        )
    db.commit()
    db.close()
    catalog.verify()
    grid = sorted({1, 3, 5, C})
    intents = [
        {
            "kind": "FULL_C",
            "size": C,
            "repetition": 0,
            "subset": None,
            "count": catalog.binding["semantic_count"],
        },
        *(
            {
                "kind": "TAIL",
                "size": T,
                "repetition": r,
                "subset": tail,
                "count": len(tail),
            }
            for r in (0, 1)
        ),
    ]
    for g in grid:
        for repetition in (1,) if g == C else (0, 1):
            intents.append(
                {
                    "kind": "PAIRED",
                    "size": g,
                    "repetition": repetition,
                    "subset": paired,
                    "count": len(paired),
                }
            )
    return {
        "population_scope": catalog.binding["population_scope"],
        "C": C,
        "T": T,
        "grid": grid,
        "tail": tail,
        "paired": paired,
        "coverage": coverage,
        "intents": intents,
        "ordinary_observations": catalog.binding["semantic_count"]
        + 2 * len(tail)
        + (2 * len(grid) - 1) * len(paired),
        "maximum_attempts": 5
        * (
            catalog.binding["semantic_count"]
            + 2 * len(tail)
            + (2 * len(grid) - 1) * len(paired)
        ),
    }


def opaque(feature):
    result = {
        k: v
        for k, v in feature.items()
        if k not in ("type", "id", "geometry", "properties")
    }
    geometry = {
        k: v for k, v in feature["geometry"].items() if k not in ("type", "coordinates")
    }
    properties = {
        k: v
        for k, v in feature["properties"].items()
        if k not in set(response.STRINGS) | {"confidence"}
    }
    if geometry:
        result["geometry"] = geometry
    if properties:
        result["properties"] = properties
    return response.structural(result) if result else None


def tokens(candidate, feature, context):
    """Exact conservative information tokens; no score or point usability gate."""
    K = c.framed([candidate[k] for k in K_FIELDS])
    result = set()
    compatible = False
    uncertain = False
    channels = context["channels"]
    b.require(
        not isinstance(channels, (str, bytes, dict)) and iter(channels) is not channels,
        "B2_WITNESS_INVALID",
    )
    for channel in channels:
        fields = {
            "kind",
            "candidate_field",
            "comparison_method",
            "source_value",
            "granularity",
            "candidate_granularity",
            "origin_claim_key",
            "ancestry_group",
            "dependence_class",
            "positive_reference",
            "origin_record_sha256",
        }
        b.require(
            set(channel) in (fields, fields | {"origin_detail"})
            and channel["candidate_field"] in candidate,
            "B2_WITNESS_INVALID",
        )
        b.validate_type(channel["origin_record_sha256"], "D")
        b.require(
            channel["kind"]
            in (
                "SOURCE_COUNTRY",
                "SOURCE_POSTCODE",
                "SOURCE_LOCALITY",
                "SOURCE_ADMIN",
                "ACCEPTED_REFERENCE",
            ),
            "B2_WITNESS_INVALID",
        )
        b.require(
            channel["dependence_class"]
            in (
                "SELF/DERIVED_FROM",
                "KNOWN_SHARED",
                "POSSIBLE_SHARED",
                "UNKNOWN",
                "PROVEN_DISJOINT",
            ),
            "B2_WITNESS_INVALID",
        )
        value = candidate[channel["candidate_field"]]
        source = channel["source_value"]
        comparable = (
            type(value) is str
            and type(source) is str
            and value != ""
            and source != ""
            and channel["granularity"] == channel["candidate_granularity"]
            and channel["granularity"]
            not in ("UNKNOWN", "UNRESOLVED", "NOT_EVALUABLE", "")
            and channel["comparison_method"] != s9.NO_NORM
        )
        b.require(
            channel["comparison_method"] in s9.NORMALIZATIONS, "B2_WITNESS_INVALID"
        )
        if channel["kind"] == "SOURCE_COUNTRY":
            b.require(
                channel["candidate_field"] == "country_a"
                and channel["comparison_method"] in (s9.ISO_NORM, s9.NO_NORM),
                "B2_WITNESS_INVALID",
            )
        elif channel["kind"] == "SOURCE_POSTCODE":
            b.require(
                channel["candidate_field"] == "postalcode"
                and channel["comparison_method"]
                in (s9.EXACT_NORM, s9.SEPARATOR_NORM, s9.NO_NORM),
                "B2_WITNESS_INVALID",
            )
        elif channel["kind"] in ("SOURCE_LOCALITY", "SOURCE_ADMIN"):
            b.require(
                channel["comparison_method"] in (s9.NAME_NORM, s9.NO_NORM),
                "B2_WITNESS_INVALID",
            )
        if (
            channel["kind"] == "ACCEPTED_REFERENCE"
            and channel["positive_reference"] is not True
        ):
            comparable = False
        if comparable:
            comparison = s9.normalize(
                channel["comparison_method"], value, context["country"]
            ) == s9.normalize(channel["comparison_method"], source, context["country"])
            if channel["kind"] == "ACCEPTED_REFERENCE":
                comparison &= channel["positive_reference"] is True
            if not comparison:
                uncertain = True
            if comparison:
                compatible = True
                result.add(
                    (
                        K,
                        channel["kind"],
                        channel["origin_claim_key"],
                        channel["ancestry_group"],
                        channel["dependence_class"],
                    )
                )
        uncertain |= not comparable or channel["dependence_class"] in (
            "POSSIBLE_SHARED",
            "UNKNOWN",
        )
    extension = opaque(feature)
    if not compatible or uncertain or extension is not None:
        result.add((K, "POTENTIAL_UNRESOLVED"))
    if extension is not None:
        result.add((K, "OPAQUE_EXTENSION", extension))
    return result


def witness(projection, raw, context, limit):
    parsed = response.Parser(raw).parse()
    features = parsed.value["features"]
    result = set()
    for candidate, feature in zip(
        projection.candidates[:limit], features[:limit], strict=True
    ):
        result.update(tokens(candidate, feature, context))
    return result


@dataclass(frozen=True)
class Observation:
    """Reader for one fully reopened, closed observation publication."""

    kind: str
    size: int
    repetition: int
    population_scope: str
    window_plan_sha256: str
    semantic_count: int
    semantic_digest: str
    publication_sha256: str
    campaign_closure_sha256: str
    workload_sha256: str
    read: Callable  # q bytes -> (Projection, exact raw bytes)
    semantic_ids: Callable  # ordered complete q bytes
    validate: Callable  # full publication reopen, mandatory before/after comparisons


def evaluate(
    catalog,
    selection,
    observations,
    *,
    window_hash,
    selection_hash,
    authority,
    comparison_writer: Callable,
):
    """Return eligible limits only; every linked context must preserve evidence."""
    catalog.verify()
    b.require(
        selection["population_scope"] == catalog.binding["population_scope"],
        "B2_POPULATION_SCOPE",
    )
    if catalog.binding["population_scope"] == b.DEVELOPMENT:
        b.require(
            all(catalog.binding[k] == v for k, v in catalogs.ACCEPTED.items()),
            "B2_ACCEPTED_POPULATION_REQUIRED",
        )
    authority.require("calibration_selection", selection_hash, selection)
    b.require(
        all(
            x["selected_sources"] >= x["required_sources"]
            for x in selection["coverage"]
        ),
        "INSUFFICIENT_CALIBRATION_COVERAGE",
    )
    comparison_hash = hashlib.sha256(b"[")
    comparison_count = 0
    original_writer = comparison_writer

    def write_comparison(row):
        nonlocal comparison_count
        if comparison_count:
            comparison_hash.update(b",")
        comparison_hash.update(b.canonical(row)[:-1])
        comparison_count += 1
        original_writer(row)

    for cell in selection["coverage"]:
        write_comparison({"diagnostic": "COVERAGE", **cell})
    observations = tuple(observations)
    expected = {
        (x["kind"], x["size"], x["repetition"]): x for x in selection["intents"]
    }
    b.require(
        len(observations) == len(expected)
        and {(x.kind, x.size, x.repetition) for x in observations} == set(expected),
        "B2_CALIBRATION_TOTALITY",
    )
    table = {}
    for obs in observations:
        b.require(
            obs.population_scope == catalog.binding["population_scope"]
            and obs.window_plan_sha256 == window_hash,
            "WINDOW_TRANSFER_FORBIDDEN",
        )
        obs.validate()
        intent = expected[(obs.kind, obs.size, obs.repetition)]
        actual = obs.semantic_ids()
        wanted = (
            (row["query_semantic_id"] for row in catalog.semantics())
            if intent["subset"] is None
            else (bytes.fromhex(q) for q in sorted(intent["subset"]))
        )
        from itertools import zip_longest

        count = 0
        for left, right in zip_longest(actual, wanted):
            b.require(left is not None and left == right, "B2_CALIBRATION_TOTALITY")
            count += 1
        b.require(
            count == obs.semantic_count == intent["count"], "B2_CALIBRATION_TOTALITY"
        )
        table[(obs.kind, obs.size, obs.repetition)] = obs
    C, T = selection["C"], selection["T"]
    full = table[("FULL_C", C, 0)]
    eligible = set(selection["grid"])
    stable = tail_ok = True
    tail = set(selection["tail"])
    paired = set(selection["paired"])
    comparisons = 0
    for semantic in catalog.semantics():
        q = semantic["query_semantic_id"]
        cp, cr = full.read(q)
        for context in catalog.contexts(q):
            all_c = witness(cp, cr, context, C)
            base = {
                "semantic": q.hex(),
                "context": context["query_context_id"],
                "source_row": context["stable_source_row_id_v1"],
                "representation": context["representation"],
            }
            for row in diagnostics.rank_rows(cp, cr, context, selection["grid"]):
                write_comparison({**base, "observation": "FULL_C", "size": C, **row})
            for n in selection["grid"]:
                preserved = witness(cp, cr, context, n) == all_c
                if not preserved:
                    eligible.discard(n)
                write_comparison(
                    {
                        "semantic": q.hex(),
                        "context": context["query_context_id"],
                        "comparison": "FULL_C_PREFIX",
                        "size": n,
                        "preserved": preserved,
                    }
                )
                comparisons += 1
            if q.hex() in tail:
                p0, r0 = table[("TAIL", T, 0)].read(q)
                p1, r1 = table[("TAIL", T, 1)].read(q)
                same = p0.feature_structures == p1.feature_structures
                stable &= same
                t0, t1 = witness(p0, r0, context, T), witness(p1, r1, context, T)
                prefix0, prefix1 = (
                    witness(p0, r0, context, C),
                    witness(p1, r1, context, C),
                )
                within = t0 == prefix0 and t1 == prefix1
                cross = t0 <= all_c and t1 <= all_c
                ok = within and cross
                for repeat, p, r in ((0, p0, r0), (1, p1, r1)):
                    for row in diagnostics.rank_rows(
                        p, r, context, sorted(set(selection["grid"] + [T]))
                    ):
                        write_comparison(
                            {
                                **base,
                                "observation": "TAIL",
                                "size": T,
                                "repetition": repeat,
                                **row,
                            }
                        )
                    write_comparison(
                        {
                            **base,
                            "diagnostic": "TAIL_PREFIX_POLICY",
                            "repetition": repeat,
                            "first_C_equal": p.feature_structures[:C]
                            == cp.feature_structures,
                            **diagnostics.features_delta(cp, p),
                        }
                    )
                # Every later rank, including T, is checked against C; tail
                # novelty cannot disappear into a maximum-size fallback.
                tail_ok &= ok
                write_comparison(
                    {
                        "semantic": q.hex(),
                        "context": context["query_context_id"],
                        "comparison": "TAIL",
                        "within_T_no_novelty_beyond_C": within,
                        "whole_T_preserved_by_C": cross,
                        "size": T,
                        "preserved": ok,
                        "repeats_equal": same,
                    }
                )
                comparisons += 1
            if q.hex() in paired:
                for n in selection["grid"]:
                    p0, r0 = (cp, cr) if n == C else table[("PAIRED", n, 0)].read(q)
                    p1, r1 = table[("PAIRED", n, 1)].read(q)
                    same = p0.feature_structures == p1.feature_structures
                    stable &= same
                    for repeat, p, r in ((0, p0, r0), (1, p1, r1)):
                        w = witness(p, r, context, n)
                        write_comparison(
                            {
                                **base,
                                "diagnostic": "DIRECT_POLICY",
                                "size": n,
                                "repetition": repeat,
                                "witness_additions": len(w - all_c),
                                "witness_losses": len(all_c - w),
                                **diagnostics.features_delta(cp, p),
                            }
                        )
                    ok = (
                        all_c <= witness(p0, r0, context, n)
                        and all_c <= witness(p1, r1, context, n)
                        and p0.feature_structures == cp.feature_structures[:n]
                        and p1.feature_structures == cp.feature_structures[:n]
                    )
                    if not ok:
                        eligible.discard(n)
                    write_comparison(
                        {
                            "semantic": q.hex(),
                            "context": context["query_context_id"],
                            "comparison": "PAIRED",
                            "size": n,
                            "preserved": ok,
                            "repeats_equal": same,
                        }
                    )
                    comparisons += 1
    for obs in observations:
        obs.validate()
    if not stable or not tail_ok:
        eligible.clear()
    disposition = (
        "REPEAT_DISAGREEMENT"
        if not stable
        else "INSUFFICIENT_CALIBRATION_DEPTH"
        if not tail_ok
        else "ELIGIBLE_FOR_OWNER_REVIEW"
        if eligible
        else "INCOMPLETE"
    )
    comparison_hash.update(b"]\n")
    inventory = sorted(
        [
            {
                "workload_kind": x.kind,
                "publication_sha256": x.publication_sha256,
                "campaign_closure_sha256": x.campaign_closure_sha256,
                "window_plan_sha256": x.window_plan_sha256,
                "workload_sha256": x.workload_sha256,
            }
            for x in observations
        ],
        key=lambda x: (x["workload_kind"], x["publication_sha256"]),
    )
    result = {
        "schema_version": "stage12_calibration_result_b2_v1",
        "population_scope": catalog.binding["population_scope"],
        "window_plan_sha256": window_hash,
        "selection_sha256": selection_hash,
        "calibration_inventory_sha256": b.digest(inventory),
        "comparison_inventory_sha256": comparison_hash.hexdigest(),
        "population_complete": True,
        "coverage_complete": True,
        "repeats_stable": stable,
        "tail_adequate": tail_ok,
        "eligible_limits": sorted(eligible),
        "proposed_limit": min(eligible) if eligible else None,
        "disposition": disposition,
        "scientific_N_selected": False,
    }
    b.validate(result)
    catalog.verify()
    return result


def direct_n(
    catalog,
    full: Observation,
    direct: Observation,
    *,
    N,
    decision,
    authority,
    comparison_writer,
):
    catalog.verify()
    b.validate(decision, "stage12_n_decision_b2_v1")
    authority.require("N_selection", b.digest(decision), decision)
    b.require(
        decision["decision"] == "SELECTED"
        and decision["result_limit"] == N
        and decision["retrieval_policy_id"] == c.policy(N)["retrieval_policy_id"].hex()
        and full.window_plan_sha256
        == direct.window_plan_sha256
        == decision["window_plan_sha256"],
        "WINDOW_TRANSFER_FORBIDDEN",
    )
    b.require(
        full.population_scope
        == direct.population_scope
        == catalog.binding["population_scope"]
        and full.kind == "FULL_C"
        and direct.kind == "DIRECT_N"
        and direct.size == N
        and full.semantic_count
        == direct.semantic_count
        == catalog.binding["semantic_count"],
        "B2_DIRECT_N_TOTALITY",
    )
    full.validate()
    direct.validate()
    count = 0
    for semantic in catalog.semantics():
        q = semantic["query_semantic_id"]
        cp, cr = full.read(q)
        np, nr = direct.read(q)
        for context in catalog.contexts(q):
            preserved = witness(cp, cr, context, full.size) <= witness(
                np, nr, context, N
            )
            comparison_writer(
                {
                    "semantic": q.hex(),
                    "context": context["query_context_id"],
                    "comparison": "DIRECT_N",
                    "size": N,
                    "preserved": preserved,
                }
            )
            b.require(preserved, "B2_DIRECT_N_VALUE_LOSS")
            count += 1
    full.validate()
    direct.validate()
    catalog.verify()
    return count
