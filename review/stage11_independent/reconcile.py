"""Full-population relational reconciliation; no candidate Stage 11 utilities."""

import hashlib
import re
from collections import Counter

import pyarrow as pa

import oracle as o


def rows(db, sql):
    cursor = db.cursor()
    try:
        for batch in cursor.execute(sql).to_arrow_reader(batch_size=1):
            yield batch.to_pylist()[0]
    finally:
        cursor.close()


def scalar(db, sql):
    return db.execute(sql).fetchone()[0]


def ordered(row, schema):
    def value(v, kind):
        if v is None:
            return None
        if pa.types.is_struct(kind):
            return [value(v[f.name], f.type) for f in kind]
        if pa.types.is_list(kind) or pa.types.is_large_list(kind):
            return [value(x, kind.value_type) for x in v]
        return v

    return [value(row[f.name], f.type) for f in schema]


def hypothesis_digest(db, schema, schema_sha, count):
    digest = hashlib.sha256(
        b"SAFE:stage10-relation:v1\0" + o.sequence([bytes.fromhex(schema_sha), count])
    )
    previous, seen = None, 0
    for row in rows(
        db, "SELECT * FROM h ORDER BY query_context_id,representation_fingerprint"
    ):
        key = row["query_context_id"], row["representation_fingerprint"]
        if previous is not None and key <= previous:
            raise ValueError("UPSTREAM_ORDER")
        digest.update(o.sequence(ordered(row, schema)))
        previous, seen = key, seen + 1
    if seen != count:
        raise ValueError("UPSTREAM_COUNT")
    return digest.hexdigest()


def scientific(db, check):
    n = scalar(db, "SELECT count(*) FROM h")
    u = scalar(db, "SELECT count(*) FROM s")
    m = scalar(db, "SELECT count(*) FROM m")
    integrity = {}
    queries = {
        "input_duplicate_ids": "SELECT count(*)-count(DISTINCT hypothesis_id) FROM h",
        "input_missing_ids": "SELECT count(*) FROM h WHERE hypothesis_id IS NULL",
        "missing_mappings": "SELECT count(*) FROM (SELECT hypothesis_id FROM h EXCEPT SELECT hypothesis_id FROM m)",
        "extra_mappings": "SELECT count(*) FROM (SELECT hypothesis_id FROM m EXCEPT SELECT hypothesis_id FROM h)",
        "multiple_mappings": "SELECT count(*) FROM (SELECT hypothesis_id FROM m GROUP BY hypothesis_id HAVING count(*)<>1)",
        "orphan_requests": "SELECT count(*) FROM (SELECT query_semantic_id FROM s EXCEPT SELECT query_semantic_id FROM m)",
        "orphan_foreign_keys": "SELECT count(*) FROM (SELECT query_semantic_id FROM m EXCEPT SELECT query_semantic_id FROM s)",
    }
    for key, sql in queries.items():
        integrity[key] = scalar(db, sql)
        check("B_C_" + key, integrity[key] == 0)
    check(
        "C_request_unique_pk",
        scalar(db, "SELECT count(DISTINCT query_semantic_id) FROM s") == u,
    )
    check(
        "C_null_ids",
        scalar(
            db,
            "SELECT count(*) FROM m WHERE hypothesis_id IS NULL OR query_semantic_id IS NULL",
        )
        == 0,
    )
    check(
        "B_exact_totality",
        n == m == scalar(db, "SELECT count(DISTINCT hypothesis_id) FROM m"),
    )
    invalid, id_bad, strings_bad, compared, collision = 0, 0, 0, 0, 0
    boundary_bad, policy_bad, encoding_bad = 0, 0, 0
    policy_counts, modes, masks = Counter(), Counter(), Counter()
    previous_id, previous_raw = None, None
    for row in rows(db, "SELECT * FROM s ORDER BY query_semantic_id"):
        core = row["core"]
        boundary = core.get("boundary_country") if isinstance(core, dict) else None
        boundary_bad += not (
            type(boundary) is str and re.fullmatch("[A-Z]{2}", boundary)
        )
        policy_bad += not (
            isinstance(core, dict)
            and set(core) == set(o.FIELDS)
            and all(core[k] == v for k, v in o.CONSTANTS.items())
        )
        for value in core.values() if isinstance(core, dict) else ():
            if isinstance(value, str):
                try:
                    value.encode("utf-8", "strict")
                except UnicodeError:
                    encoding_bad += 1
        if not o.valid(core):
            invalid += 1
            continue
        raw = o.core_bytes(core)
        id_bad += hashlib.sha256(raw).digest() != row["query_semantic_id"]
        collision += row["query_semantic_id"] == previous_id and raw != previous_raw
        previous_id, previous_raw = row["query_semantic_id"], raw
        policy_counts[tuple(core[k] for k in o.CONSTANTS if k.endswith("_policy"))] += 1
        modes[core["search_mode"]] += 1
        masks[
            (
                core["endpoint"],
                core["search_mode"],
                *(core[k] is not None for k in o.PAYLOAD[1:]),
            )
        ] += 1
    for row in rows(
        db,
        """SELECT h.intent,h.selection_status,s.core,m.query_semantic_id FROM h
                         JOIN m USING(hypothesis_id) JOIN s USING(query_semantic_id)""",
    ):
        try:
            expected = o.project(row["intent"], row["selection_status"])
            raw = o.core_bytes(expected)
            strings_bad += raw != o.core_bytes(row["core"])
            id_bad += hashlib.sha256(raw).digest() != row["query_semantic_id"]
        except (ValueError, UnicodeError, TypeError):
            invalid += 1
        compared += 1
    check("E_full_sha256_recomputation", id_bad == 0 and invalid == 0)
    check(
        "F_H_every_hypothesis_complete_core_exact_bytes",
        strings_bad == 0 and compared == n and invalid == 0,
    )
    check("E_F_same_id_different_payload", collision == 0)
    check("G_I_J_K_L_frozen_core_validity", invalid == 0)
    check(
        "J_exact_policy_combination",
        policy_counts
        == Counter(
            {tuple(v for k, v in o.CONSTANTS.items() if k.endswith("_policy")): u}
        ),
    )
    integrity.update(
        invalid_intents=invalid,
        invalid_boundaries=boundary_bad,
        invalid_policies=policy_bad,
        invalid_encodings=encoding_bad,
        id_payload_collisions=collision,
        id_recompute_mismatches=id_bad,
        projection_mismatches=strings_bad,
    )
    check(
        "N_lineage_roles",
        scalar(
            db,
            "SELECT count(*) FROM h WHERE stage08_representation NOT IN ('STANDARD','NATIVE') OR stage08_representation IS NULL",
        )
        == 0,
    )
    lineage_bad = scalar(
        db,
        """SELECT count(*) FROM d LEFT JOIN h
        ON d.hypothesis_id=h.hypothesis_id AND d.query_context_id=h.query_context_id
        AND d.stable_source_row_id_v1=h.stable_source_row_id_v1
        AND d.stage08_representation=h.stage08_representation
        AND d.stage06_exact_candidate_id=h.stage06_exact_candidate_id
        WHERE d.eligibility_state='ELIGIBLE' AND h.hypothesis_id IS NULL""",
    )
    integrity["lineage_mismatches"] = lineage_bad
    check("N_exact_upstream_foreign_keys", lineage_bad == 0)
    check(
        "N_six_unique_family_slots",
        scalar(
            db,
            "SELECT count(*) FROM (SELECT query_context_id FROM d GROUP BY query_context_id HAVING count(*)<>6 OR count(DISTINCT family)<>6)",
        )
        == 0,
    )
    check(
        "N_closed_decision_states",
        scalar(
            db,
            """SELECT count(*) FROM d WHERE
        family NOT IN ('Q1','Q2','Q3','Q4','Q5','Q6') OR NOT (
        (eligibility_state='ELIGIBLE' AND membership_state IN ('FIRST_MEMBER','CONVERGENT_MEMBER') AND hypothesis_id IS NOT NULL)
        OR (eligibility_state='INELIGIBLE' AND membership_state='NONE' AND hypothesis_id IS NULL))""",
        )
        == 0,
    )
    check(
        "N_one_first_member",
        scalar(
            db,
            """SELECT count(*) FROM (SELECT h.hypothesis_id
        FROM h LEFT JOIN d ON h.hypothesis_id=d.hypothesis_id AND h.query_context_id=d.query_context_id
        AND d.membership_state='FIRST_MEMBER' GROUP BY h.hypothesis_id HAVING count(d.hypothesis_id)<>1)""",
        )
        == 0,
    )
    db.execute(
        "CREATE TEMP TABLE counts AS SELECT query_semantic_id,count(*)::UBIGINT AS n FROM m GROUP BY query_semantic_id"
    )
    hist = dict(db.execute("SELECT n,count(*) FROM counts GROUP BY n").fetchall())
    integrity["multiplicity_sum_mismatch"] = abs(
        sum(k * v for k, v in hist.items()) - n
    )
    bins = [
        {
            "minimum": low,
            "maximum": high,
            "requests": sum(v for k, v in hist.items() if low <= k <= high),
            "hypotheses": sum(k * v for k, v in hist.items() if low <= k <= high),
        }
        for low, high in [
            (1, 1),
            (2, 2),
            (3, 5),
            (6, 10),
            (11, 50),
            (51, 100),
            (101, 2**64 - 1),
        ]
    ]
    db.execute(
        "CREATE TEMP VIEW links AS SELECT m.query_semantic_id,h.* FROM m JOIN h USING(hypothesis_id)"
    )
    db.execute("""CREATE TEMP TABLE context_counts AS SELECT query_semantic_id,
        count(DISTINCT query_context_id) AS contexts, count(DISTINCT stable_source_row_id_v1) AS sources,
        count(*) FILTER(WHERE stage08_representation='STANDARD') AS standard,
        count(*) FILTER(WHERE stage08_representation='NATIVE') AS native FROM links GROUP BY query_semantic_id""")
    db.execute("""CREATE TEMP TABLE family_counts AS SELECT query_semantic_id,count(DISTINCT family) AS n
        FROM links JOIN d USING(hypothesis_id,query_context_id) WHERE d.eligibility_state='ELIGIBLE'
        AND d.membership_state IN ('FIRST_MEMBER','CONVERGENT_MEMBER') GROUP BY query_semantic_id""")
    family_hist = [
        {
            "families": k,
            "requests": scalar(db, f"SELECT count(*) FROM family_counts WHERE n={k}"),
        }
        for k in range(1, 7)
    ]
    check("N_family_incidence_total", sum(v["requests"] for v in family_hist) == u)
    populations = {
        "hypotheses": n,
        "sources": scalar(db, "SELECT count(DISTINCT stable_source_row_id_v1) FROM d"),
        "contexts": scalar(db, "SELECT count(DISTINCT query_context_id) FROM d"),
        "standard_contexts": scalar(
            db,
            "SELECT count(DISTINCT query_context_id) FROM d WHERE stage08_representation='STANDARD'",
        ),
        "native_contexts": scalar(
            db,
            "SELECT count(DISTINCT query_context_id) FROM d WHERE stage08_representation='NATIVE'",
        ),
        "decisions": scalar(db, "SELECT count(*) FROM d"),
        "zero_hypothesis_contexts": scalar(
            db,
            "SELECT count(*) FROM (SELECT query_context_id FROM d EXCEPT SELECT query_context_id FROM h)",
        ),
        "eligible_family_links": scalar(
            db, "SELECT count(*) FROM d WHERE eligibility_state='ELIGIBLE'"
        ),
        "selection_status": "ALL_ELIGIBLE_CATALOG",
        "operating_budget": "UNSELECTED",
    }
    mode_rows = [
        {
            "search_mode": mode,
            "requests": modes[mode],
            "hypotheses": scalar(
                db, f"SELECT count(*) FROM h WHERE intent.search_mode='{mode}'"
            ),
        }
        for mode in ("FULL_TEXT", "STRUCTURED")
    ]
    unbound_s = scalar(db, "SELECT count(*) FROM s WHERE core.boundary_country IS NULL")
    unbound_h = scalar(
        db, "SELECT count(*) FROM h WHERE intent.boundary_country IS NULL"
    )
    combinations = []
    for key, requests in sorted(masks.items()):
        condition = " AND ".join(
            f"core.{k} IS {'NOT ' if present else ''}NULL"
            for k, present in zip(o.PAYLOAD[1:], key[2:])
        )
        hypotheses = scalar(
            db,
            f"SELECT coalesce(sum(n),0) FROM s JOIN counts USING(query_semantic_id) WHERE core.search_mode='{key[1]}' AND {condition}",
        )
        combinations.append(
            {
                "endpoint": key[0],
                "search_mode": key[1],
                "presence": dict(zip(o.PAYLOAD[1:], key[2:])),
                "requests": requests,
                "hypotheses": hypotheses,
            }
        )
    check(
        "M_histogram_arithmetic",
        sum(b["requests"] for b in bins) == u
        and sum(b["hypotheses"] for b in bins) == n,
    )
    check(
        "G_mode_arithmetic",
        sum(r["requests"] for r in mode_rows) == u
        and sum(r["hypotheses"] for r in mode_rows) == n,
    )
    return {
        "summary_version": "stage11_semantic_request_summary_v1",
        "input_population": populations,
        "request_counts": {
            "unique_requests": u,
            "map_rows": m,
            "modes": mode_rows,
            "country_boundary": {
                "bound": {"requests": u - unbound_s, "hypotheses": n - unbound_h},
                "unbounded": {"requests": unbound_s, "hypotheses": unbound_h},
            },
        },
        "reduction": {
            "hypotheses_saved": n - u,
            "reduction_fraction": {"numerator": n - u, "denominator": n or None},
            "unique_fraction": {"numerator": u, "denominator": n or None},
        },
        "multiplicity": {
            "bins": bins,
            "maximum": max(hist, default=0),
            "mean": {"numerator": n, "denominator": u or None},
            "requests_with_multiple_hypotheses": sum(
                v for k, v in hist.items() if k > 1
            ),
        },
        "lineage_convergence": {
            "denominator": u,
            "cross_context": scalar(
                db, "SELECT count(*) FROM context_counts WHERE contexts>1"
            ),
            "cross_source": scalar(
                db, "SELECT count(*) FROM context_counts WHERE sources>1"
            ),
            "cross_family": scalar(db, "SELECT count(*) FROM family_counts WHERE n>1"),
            "family_cardinality": family_hist,
            "standard_only": scalar(
                db, "SELECT count(*) FROM context_counts WHERE standard>0 AND native=0"
            ),
            "native_only": scalar(
                db, "SELECT count(*) FROM context_counts WHERE native>0 AND standard=0"
            ),
            "both_roles": scalar(
                db, "SELECT count(*) FROM context_counts WHERE native>0 AND standard>0"
            ),
            "same_source_both_roles": scalar(
                db,
                """SELECT count(DISTINCT query_semantic_id) FROM
                (SELECT query_semantic_id,stable_source_row_id_v1 FROM links GROUP BY ALL HAVING count(DISTINCT stage08_representation)=2)""",
            ),
        },
        "parameter_combinations": {
            "endpoint_mode_presence": combinations,
            "policies": [
                {
                    **{k: v for k, v in o.CONSTANTS.items() if k.endswith("_policy")},
                    "requests": u,
                    "hypotheses": n,
                }
            ],
        },
        "integrity": integrity,
        "interpretation": [
            "WORKLOAD_CONVERGENCE_ONLY",
            "NO_ACCURACY_ESTIMATE",
            "OPERATING_BUDGET_UNSELECTED",
            "NON_EXECUTABLE_CORE_CATALOG",
            "STAGE12_NOT_STARTED",
        ],
    }
