"""Independent complete-relation, occurrence, baseline and LF-boundary oracles."""

from __future__ import annotations

import hashlib
from collections import Counter

import pyarrow as pa
import pyarrow.parquet as pq

from common import (
    INTENT_FIELDS,
    REASONS,
    SELECTORS,
    certificate,
    framed,
    full_intent,
    identity,
    ordered,
    parquet_rows,
    rows,
    scalar,
    step,
)

EXPECTED_FAMILIES = {
    "Q1": (33977, 33977, 0, 35770),
    "Q2": (34102, 34102, 0, 35645),
    "Q3": (68079, 38644, 29435, 1668),
    "Q4": (33556, 33556, 0, 36191),
    "Q5": (50, 50, 0, 69697),
    "Q6": (2348, 2348, 0, 67399),
}


def derive_contexts(db, upstream, check):
    # Derive the accepted two scalar slots independently, retaining UNION ALL.
    db.execute("""CREATE TABLE review_occurrence_slots AS
      SELECT stable_source_row_id_v1,'STANDARD' stage08_representation,
             stage06_standard_exact_candidate_id stage06_exact_candidate_id
      FROM source_candidate_map WHERE stage06_standard_exact_candidate_id IS NOT NULL
      UNION ALL
      SELECT stable_source_row_id_v1,'NATIVE',stage06_native_exact_candidate_id
      FROM source_candidate_map WHERE stage06_native_exact_candidate_id IS NOT NULL""")
    db.execute(
        "CREATE TABLE contexts(query_context_id BLOB,stable_source_row_id_v1 BLOB,stage08_representation VARCHAR,stage06_exact_candidate_id BLOB)"
    )
    schema = pa.schema(
        [
            pa.field("query_context_id", pa.binary()),
            pa.field("stable_source_row_id_v1", pa.binary()),
            pa.field("stage08_representation", pa.string()),
            pa.field("stage06_exact_candidate_id", pa.binary()),
        ]
    )
    buffer = []

    def flush():
        if buffer:
            db.register(
                "review_context_batch", pa.Table.from_pylist(buffer, schema=schema)
            )
            db.execute("INSERT INTO contexts SELECT * FROM review_context_batch")
            db.unregister("review_context_batch")
            buffer.clear()

    for row in rows(db, "SELECT * FROM review_occurrence_slots"):
        buffer.append(
            {
                "query_context_id": identity(
                    "stage10-context:v1",
                    upstream,
                    row["stable_source_row_id_v1"],
                    row["stage08_representation"],
                ),
                **row,
            }
        )
        if len(buffer) == 256:
            flush()
    flush()
    check(
        "source_presence_slot_equivalence",
        scalar(
            db,
            """SELECT count(*) FROM source_candidate_map
      WHERE (stage08_standard_representation_status='PRESENT') IS DISTINCT FROM
        (stage06_standard_exact_candidate_id IS NOT NULL)
      OR (stage08_native_representation_status='PRESENT') IS DISTINCT FROM
        (stage06_native_exact_candidate_id IS NOT NULL)""",
        )
        == 0,
    )
    check(
        "accepted_occurrence_exact_bijection",
        scalar(
            db,
            """SELECT count(*) FROM
      ((SELECT stable_source_row_id_v1,stage08_representation,stage06_exact_candidate_id FROM contexts
        EXCEPT ALL SELECT stable_source_row_id_v1,stage08_representation,stage06_exact_candidate_id FROM stage08_occurrence)
       UNION ALL
       (SELECT stable_source_row_id_v1,stage08_representation,stage06_exact_candidate_id FROM stage08_occurrence
        EXCEPT ALL SELECT stable_source_row_id_v1,stage08_representation,stage06_exact_candidate_id FROM contexts))""",
        )
        == 0,
    )
    check(
        "stage06_source_slots_exact",
        scalar(
            db,
            """SELECT count(*) FROM source_candidate_map s
      FULL OUTER JOIN stage06_row_map r USING(stable_source_row_id_v1)
      WHERE s.stable_source_row_id_v1 IS NULL OR r.stable_source_row_id_v1 IS NULL
      OR s.stage06_standard_exact_candidate_id IS DISTINCT FROM r.stage06_standard_exact_candidate_id
      OR s.stage06_native_exact_candidate_id IS DISTINCT FROM r.stage06_native_exact_candidate_id""",
        )
        == 0,
    )
    check(
        "context_pk",
        scalar(db, "SELECT count(*)-count(DISTINCT query_context_id) FROM contexts")
        == 0,
    )
    check(
        "source_pk",
        scalar(
            db,
            "SELECT count(*)-count(DISTINCT stable_source_row_id_v1) FROM source_candidate_map",
        )
        == 0,
    )
    check(
        "candidate_population_exact",
        scalar(
            db,
            """SELECT count(*) FROM (
       (SELECT DISTINCT stage06_exact_candidate_id FROM contexts EXCEPT SELECT stage06_exact_candidate_id FROM candidate_evidence)
       UNION ALL (SELECT stage06_exact_candidate_id FROM candidate_evidence EXCEPT SELECT stage06_exact_candidate_id FROM contexts))""",
        )
        == 0,
    )
    distribution = dict(
        db.execute("""SELECT n,count(*) FROM
      (SELECT s.stable_source_row_id_v1,count(k.query_context_id) n FROM source_candidate_map s
       LEFT JOIN contexts k USING(stable_source_row_id_v1) GROUP BY 1) GROUP BY n""").fetchall()
    )
    check("source_context_distribution", distribution == {1: 253, 2: 34747})
    counts = {
        role: scalar(
            db, "SELECT count(*) FROM contexts WHERE stage08_representation=?", [role]
        )
        for role in ("STANDARD", "NATIVE")
    }
    check("occurrence_counts", counts == {"STANDARD": 34822, "NATIVE": 34925})
    same = scalar(
        db,
        """SELECT count(*) FROM source_candidate_map
      WHERE stage06_standard_exact_candidate_id=stage06_native_exact_candidate_id""",
    )
    check(
        "equal_candidate_roles_remain_two",
        scalar(
            db,
            """SELECT count(*) FROM
      (SELECT s.stable_source_row_id_v1,count(k.query_context_id) n FROM source_candidate_map s
       LEFT JOIN contexts k USING(stable_source_row_id_v1)
       WHERE s.stage06_standard_exact_candidate_id=s.stage06_native_exact_candidate_id GROUP BY 1) WHERE n<>2""",
        )
        == 0,
    )
    return {
        "source_rows": scalar(db, "SELECT count(*) FROM source_candidate_map"),
        "contexts": sum(counts.values()),
        "roles": counts,
        "source_context_distribution": [distribution.get(n, 0) for n in range(3)],
        "equal_candidate_two_role_rows": same,
    }


def logical_and_identifiers(root, manifest, upstream, check):
    # Shared Arrow schema is only a byte-format adapter; IDs and E are independent.
    from safe_geocoding_pipeline.preprocessing.stages import s10_query_io as io

    inputs, science = (
        bytes.fromhex(manifest[k]) for k in ("input_binding_sha256", "science_sha256")
    )
    result = {}
    for record in manifest["relations"]:
        name = record["name"]
        is_h = name == "query_hypothesis"
        schema = io.output_schema(name)
        paths = [root / f["relative_path"] for f in record["files"]]
        bad = Counter()
        digest = hashlib.sha256(b"SAFE:stage10-relation:v1\0")
        for chunk in framed(
            (bytes.fromhex(record["schema_sha256"]), record["row_count"])
        ):
            digest.update(chunk)
        previous = None
        n = 0
        for path in paths:
            with pq.ParquetFile(path, page_checksum_verification=True) as parquet:
                bad["physical_schema"] += not parquet.schema_arrow.equals(
                    schema, check_metadata=True
                )
        for row in parquet_rows(paths):
            n += 1
            key = (
                row["query_context_id"],
                row["representation_fingerprint"] if is_h else row["family"],
            )
            bad["canonical_order"] += previous is not None and previous >= key
            previous = key
            for chunk in framed(ordered(row, schema)):
                digest.update(chunk)
            context = identity(
                "stage10-context:v1",
                upstream,
                row["stable_source_row_id_v1"],
                row["stage08_representation"],
            )
            bad["context_identity"] += context != row["query_context_id"]
            if is_h:
                intent = row["intent"]
                values = tuple(intent[field] for field in INTENT_FIELDS)
                fingerprint = identity("stage10-intent:v1", values)
                bad["intent_identity"] += (
                    fingerprint != row["representation_fingerprint"]
                )
                bad["hypothesis_identity"] += row["hypothesis_id"] != identity(
                    "stage10-hypothesis:v1", inputs, science, context, fingerprint
                )
                bad["policy"] += (
                    intent["intent_version"] != "stage10_query_intent_v1"
                    or intent["retrieval_policy_slot"]
                    != "SAFE_PELIAS_COMMON_RETRIEVAL_V1"
                )
                bad["budget"] += row["selection_status"] != "ALL_ELIGIBLE_CATALOG"
                if intent["search_mode"] == "FULL_TEXT":
                    valid = (
                        intent["endpoint"] == "/v1/search"
                        and bool(intent["text"])
                        and all(
                            intent[k] is None
                            for k in (
                                "address",
                                "postalcode",
                                "locality",
                                "region",
                                "country",
                            )
                        )
                    )
                elif intent["search_mode"] == "STRUCTURED":
                    valid = (
                        intent["endpoint"] == "/v1/search/structured"
                        and intent["text"] is None
                        and bool(intent["address"])
                        and bool(intent["postalcode"] or intent["locality"])
                        and intent["region"] is None
                        and intent["country"] is None
                        and all(
                            intent[k] is None or bool(intent[k])
                            for k in ("postalcode", "locality")
                        )
                    )
                else:
                    valid = False
                bad["intent_shape"] += not valid
            else:
                family = row["family"]
                bad["family_identity"] += row["family_decision_id"] != identity(
                    "stage10-family-decision:v1", inputs, science, context, family
                )
                reason = row["reason_codes"]
                bad["reason_closure"] += (
                    any(r not in REASONS for r in reason)
                    or "MALFORMED_UPSTREAM_EVIDENCE" in reason
                    or "QUERY_BUDGET_SUPPRESSION" in reason
                    or len(set(reason)) != len(reason)
                    or len(reason) > 18
                )
                if all(r in REASONS for r in reason):
                    bad["reason_order"] += reason != sorted(
                        set(reason), key=REASONS.index
                    )
                bad["primary_reason"] += row["primary_reason"] != (
                    reason[0] if reason else None
                )
                bad["rule_identity"] += (
                    row["eligibility_rule_id"]
                    != f"stage10_q{family[1:]}_eligibility_v1"
                )
                eligible = row["eligibility_state"] == "ELIGIBLE"
                bad["membership_state"] += not (
                    eligible
                    and row["membership_state"] in ("FIRST_MEMBER", "CONVERGENT_MEMBER")
                    and row["hypothesis_id"] is not None
                    or row["eligibility_state"] == "INELIGIBLE"
                    and row["membership_state"] == "NONE"
                    and row["hypothesis_id"] is None
                )
                bad["convergence_reason"] += (
                    row["membership_state"] == "CONVERGENT_MEMBER"
                ) != ("EXACT_SEMANTIC_DUPLICATE" in reason)
                wanted = [
                    s
                    for s in SELECTORS
                    if s not in ("SOURCE_LINES_V1", "PARSER_COMPONENTS_V1")
                    or s == "SOURCE_LINES_V1"
                    and family in ("Q3", "Q5")
                    or s == "PARSER_COMPONENTS_V1"
                    and family == "Q5"
                ]
                bad["selector_membership"] += [
                    v["selector_id"] for v in row["lineage"]
                ] != wanted
                traces = row["transformations"]
                bad["transform_ordinals"] += len(traces) > 4 or [
                    t["ordinal"] for t in traces
                ] != list(range(len(traces)))
                fields = row["field_decisions"]
                bad["field_slots"] += [f["field"] for f in fields] != (
                    list(
                        (
                            "address",
                            "postalcode",
                            "locality",
                            "region",
                            "country",
                            "boundary_country",
                        )
                    )
                    if family == "Q4"
                    else []
                )
                bad["field_reason_closure"] += any(
                    any(r not in REASONS for r in f["reason_codes"])
                    or f["disposition"] not in ("INCLUDE", "OMIT", "NOT_APPLICABLE")
                    for f in fields
                )
                bad["removed_scope"] += bool(row["removed_lines"]) and (
                    family != "Q5" or not eligible
                )
        check(name + "_logical_hash", digest.hexdigest() == record["logical_sha256"])
        check(name + "_row_count", n == record["row_count"])
        for label, count in sorted(bad.items()):
            check(name + "_" + label, count == 0)
        result[name] = {
            "rows": n,
            "logical_sha256": digest.hexdigest(),
            "defect_counts": dict(bad),
        }
    return result


def relational(db, check):
    queries = {
        "hypothesis_pk": "SELECT count(*)-count(DISTINCT hypothesis_id) FROM query_hypothesis",
        "decision_pk": "SELECT count(*)-count(DISTINCT family_decision_id) FROM query_family_decision",
        "six_decisions": """SELECT count(*) FROM (SELECT k.query_context_id,count(d.family_decision_id) n,count(DISTINCT d.family) f
         FROM contexts k LEFT JOIN query_family_decision d USING(query_context_id) GROUP BY 1) WHERE n<>6 OR f<>6""",
        "q7_or_unknown_family": "SELECT count(*) FROM query_family_decision WHERE family NOT IN ('Q1','Q2','Q3','Q4','Q5','Q6')",
        "hypothesis_membership": """SELECT count(*) FROM (SELECT h.hypothesis_id,count(d.family_decision_id) n,
         count(*) FILTER(WHERE d.membership_state='FIRST_MEMBER') firsts FROM query_hypothesis h
         LEFT JOIN query_family_decision d USING(hypothesis_id) GROUP BY 1) WHERE n=0 OR firsts<>1""",
        "membership_fk": """SELECT count(*) FROM query_family_decision d LEFT JOIN query_hypothesis h USING(hypothesis_id)
         WHERE d.hypothesis_id IS NOT NULL AND (h.hypothesis_id IS NULL OR d.query_context_id<>h.query_context_id
         OR d.stable_source_row_id_v1<>h.stable_source_row_id_v1 OR d.stage08_representation<>h.stage08_representation
         OR d.stage06_exact_candidate_id<>h.stage06_exact_candidate_id)""",
        "rank_and_intent_unique": """SELECT count(*) FROM (SELECT query_context_id,count(*) n,count(DISTINCT representation_fingerprint) i,
          count(DISTINCT intent) v,count(DISTINCT generation_rank) r,min(generation_rank) lo,max(generation_rank) hi
          FROM query_hypothesis GROUP BY 1) WHERE n<>i OR n<>v OR n<>r OR lo<>1 OR hi<>n""",
        "complete_intent_collisions": "SELECT count(*) FROM (SELECT representation_fingerprint,count(DISTINCT intent) n FROM query_hypothesis GROUP BY 1) WHERE n<>1",
        "family_ownership_order": """SELECT count(*) FROM query_family_decision d JOIN
         (SELECT hypothesis_id,min(family) first_family FROM query_family_decision WHERE hypothesis_id IS NOT NULL GROUP BY 1) m USING(hypothesis_id)
         WHERE (d.family=m.first_family)<>(d.membership_state='FIRST_MEMBER')""",
        "generation_rank_family_order": """SELECT count(*) FROM (
          SELECT h.generation_rank,row_number() OVER (PARTITION BY h.query_context_id ORDER BY d.family) expected
          FROM query_hypothesis h JOIN query_family_decision d USING(hypothesis_id)
          WHERE d.membership_state='FIRST_MEMBER') WHERE generation_rank<>expected""",
        "role_family": """SELECT count(*) FROM query_family_decision WHERE eligibility_state='ELIGIBLE' AND
         ((family='Q1' AND stage08_representation<>'STANDARD') OR (family IN ('Q2','Q6') AND stage08_representation<>'NATIVE'))""",
        "context_ceiling": "SELECT count(*) FROM (SELECT query_context_id,stage08_representation,count(*) n FROM query_hypothesis GROUP BY ALL) WHERE n>5 OR (stage08_representation='STANDARD' AND n>4)",
        "row_ceiling": "SELECT count(*) FROM (SELECT stable_source_row_id_v1,count(*) n FROM query_hypothesis GROUP BY 1) WHERE n>9",
        "all_catalog": "SELECT count(*) FROM query_hypothesis WHERE selection_status<>'ALL_ELIGIBLE_CATALOG'",
        "budget_suppression": "SELECT count(*) FROM query_family_decision WHERE list_contains(reason_codes,'QUERY_BUDGET_SUPPRESSION')",
    }
    for relation in ("query_hypothesis", "query_family_decision"):
        queries[
            relation + "_context_fk"
        ] = f"""SELECT count(*) FROM {relation} r LEFT JOIN contexts k USING(query_context_id)
          WHERE k.query_context_id IS NULL OR r.stable_source_row_id_v1 IS DISTINCT FROM k.stable_source_row_id_v1
          OR r.stage08_representation IS DISTINCT FROM k.stage08_representation
          OR r.stage06_exact_candidate_id IS DISTINCT FROM k.stage06_exact_candidate_id"""
    violations = {}
    for label, sql in queries.items():
        violations[label] = scalar(db, sql)
        check(label, violations[label] == 0)
    families = {}
    for family, expected in EXPECTED_FAMILIES.items():
        actual = tuple(
            int(x)
            for x in db.execute(
                """SELECT
           count(*) FILTER(WHERE eligibility_state='ELIGIBLE'),
           count(*) FILTER(WHERE membership_state='FIRST_MEMBER'),
           count(*) FILTER(WHERE membership_state='CONVERGENT_MEMBER'),
           count(*) FILTER(WHERE membership_state='NONE') FROM query_family_decision WHERE family=?""",
                [family],
            ).fetchone()
        )
        check(
            "family_matrix_" + family,
            actual == expected
            and actual[0] == actual[1] + actual[2]
            and actual[0] + actual[3] == 69747,
        )
        families[family] = list(actual)
    hist = dict(
        db.execute("""SELECT n,count(*) FROM (SELECT k.query_context_id,count(h.hypothesis_id) n FROM contexts k
                LEFT JOIN query_hypothesis h USING(query_context_id) GROUP BY 1) GROUP BY n""").fetchall()
    )
    check(
        "hypothesis_distribution",
        hist == {0: 1668, 1: 14831, 2: 31948, 3: 21250, 4: 50},
    )
    check(
        "hypothesis_distribution_sums",
        sum(hist.values()) == 69747
        and sum(n * count for n, count in hist.items()) == 142677,
    )
    source_max = scalar(
        db,
        "SELECT max(n) FROM (SELECT stable_source_row_id_v1,count(*) n FROM query_hypothesis GROUP BY 1)",
    )
    check("observed_maxima", max(hist) == 4 and source_max == 8)
    pairs = {}
    for f1 in EXPECTED_FAMILIES:
        for f2 in EXPECTED_FAMILIES:
            if f1 >= f2:
                continue
            n = scalar(
                db,
                """SELECT count(*) FROM query_family_decision a JOIN query_family_decision b
                 ON a.query_context_id=b.query_context_id AND a.hypothesis_id=b.hypothesis_id WHERE a.family=? AND b.family=?""",
                [f1, f2],
            )
            pairs[f1 + "_" + f2] = n
    check(
        "pair_convergence",
        all(
            n == ({"Q1_Q3": 14694, "Q2_Q3": 14741}.get(k, 0)) for k, n in pairs.items()
        ),
    )
    check("preconvergence_eligible", sum(v[0] for v in families.values()) == 172112)
    return {
        "violations": violations,
        "family_matrix": families,
        "hypotheses_per_context": [hist.get(i, 0) for i in range(6)],
        "max_per_source": source_max,
        "convergence_pairs": pairs,
        "global_distinct_intents": scalar(
            db,
            "SELECT count(DISTINCT representation_fingerprint) FROM query_hypothesis",
        ),
    }


def baselines_and_boundaries(db, check):
    bad = Counter()
    reviewed = 0
    for role in ("STANDARD", "NATIVE"):
        prefix = role.lower()
        suffix = "_native" if role == "NATIVE" else ""
        line_fields = [
            f"stage04_lower_street_address_line_{i}{suffix}" for i in range(1, 5)
        ]
        query = f"""SELECT k.*,g.boundary_country,c.stage06_candidate_lower AS text,
          [{",".join("r." + x for x in line_fields)}] lines,
          r.stage06_{prefix}_exact_candidate_id linked,
          r.stage05_{prefix}_candidate_lower lower_candidate,
          r.stage05_{prefix}_candidate_available available,
          r.stage05_{prefix}_contributing_line_count line_count,
          r.stage05_{prefix}_contributing_line_mask line_mask,
          d.family,d.eligibility_state,d.primary_reason,d.transformations,d.lineage,h.intent
          FROM contexts k JOIN review_country_context g USING(query_context_id)
          JOIN stage06_row_map r USING(stable_source_row_id_v1)
          JOIN candidate_evidence c USING(stage06_exact_candidate_id)
          JOIN query_family_decision d USING(query_context_id)
          LEFT JOIN query_hypothesis h ON h.hypothesis_id=d.hypothesis_id
          WHERE k.stage08_representation=? AND d.family IN ('Q1','Q2','Q3')"""
        for r in rows(db, query, [role]):
            reviewed += 1
            lines = tuple(r["lines"])
            bad["source_boundary_integrity"] += not (
                r["linked"] == r["stage06_exact_candidate_id"]
                and r["available"] is True
                and r["lower_candidate"] == r["text"] == " ".join(s for s in lines if s)
                and r["line_count"] == sum(bool(s) for s in lines)
                and r["line_mask"] == "".join("1" if s else "0" for s in lines)
            )
            family = r["family"]
            wrong_role = family == ("Q2" if role == "STANDARD" else "Q1")
            country = r["boundary_country"]
            reason = (
                "REQUIRED_SOURCE_REPRESENTATION_UNAVAILABLE"
                if wrong_role
                else "COUNTRY_CONTEXT_UNAVAILABLE"
                if country is None
                else None
            )
            eligible = reason is None
            bad["baseline_q3_eligibility"] += (
                r["eligibility_state"] == "ELIGIBLE"
            ) != eligible
            if eligible:
                text = "\n".join(s for s in lines if s) if family == "Q3" else r["text"]
                bad["baseline_content" if family != "Q3" else "q3_complete_intent"] += (
                    r["intent"] != full_intent(text, country)
                )
                trace = (
                    step("SOURCE_LF_JOIN_V1", lines, text)
                    if family == "Q3"
                    else step("EXACT_CANDIDATE_V1", r["text"], r["text"])
                )
                bad["baseline_q3_trace"] += r["transformations"] != [trace]
                expected_reason = (
                    "EXACT_SEMANTIC_DUPLICATE"
                    if family == "Q3" and text == r["text"]
                    else None
                )
                bad["baseline_q3_reason"] += r["primary_reason"] != expected_reason
            else:
                bad["baseline_q3_abstention"] += (
                    r["primary_reason"] != reason
                    or r["intent"] is not None
                    or bool(r["transformations"])
                )
            if family == "Q3":
                expected = certificate(
                    [
                        (
                            r["linked"],
                            *lines,
                            r["lower_candidate"],
                            r["available"],
                            r["line_count"],
                            r["line_mask"],
                        )
                    ]
                )
                observed = next(
                    v for v in r["lineage"] if v["selector_id"] == "SOURCE_LINES_V1"
                )
                bad["all_q3_source_line_certificates"] += any(
                    observed[k] != v for k, v in expected.items()
                )
    for label, n in bad.items():
        check(label, n == 0)
    check("all_baseline_q3_slots_reviewed", reviewed == 69747 * 3)
    return {"slots_reviewed": reviewed, "defect_counts": dict(bad)}
