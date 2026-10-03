"""Independent complete selector replay on a deterministic bounded context set.

Every selected stream is complete, including all repeated parser components and
all reached witness sets/ancestors. The sample is never exported or tuned.
"""

from __future__ import annotations

import hashlib
from collections import Counter

from common import certificate, framed, ordered, rows, scalar
from safe_geocoding_pipeline.preprocessing.stages import s08_address_evidence as s8
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_contract as s9


def run(db, check):
    # At most 40 contexts, fixed independently of observed protected strings.
    choices = [
        "SELECT query_context_id FROM contexts ORDER BY query_context_id LIMIT 16"
    ]
    for family in ("Q4", "Q5", "Q6"):
        choices.append(
            "SELECT query_context_id FROM query_family_decision WHERE family='"
            + family
            + "' AND eligibility_state='ELIGIBLE' ORDER BY query_context_id LIMIT 4"
        )
    choices.append(
        "SELECT query_context_id FROM query_family_decision WHERE family='Q3' AND eligibility_state='INELIGIBLE' ORDER BY query_context_id LIMIT 4"
    )
    choices.append(
        "SELECT query_context_id FROM query_family_decision WHERE family='Q4' AND list_contains(flatten(list_transform(field_decisions,x -> x.reason_codes)),'CONTRADICTION_GATE') ORDER BY query_context_id LIMIT 4"
    )
    choices.append(
        "SELECT k.query_context_id FROM contexts k JOIN source_candidate_map s USING(stable_source_row_id_v1) WHERE s.stage06_standard_exact_candidate_id=s.stage06_native_exact_candidate_id ORDER BY k.query_context_id LIMIT 4"
    )
    db.execute(
        "CREATE TABLE review_lineage_sample AS SELECT DISTINCT query_context_id FROM ("
        + " UNION ALL ".join("(" + sql + ")" for sql in choices)
        + ")"
    )
    db.execute("""CREATE TABLE review_lineage_source_evidence AS SELECT e.* FROM candidate_reference_evidence e
       WHERE e.evidence_scope='SOURCE_ROW' AND EXISTS(SELECT 1 FROM contexts k JOIN review_lineage_sample x USING(query_context_id)
         WHERE e.stable_source_row_id_v1=k.stable_source_row_id_v1 AND e.stage06_exact_candidate_id=k.stage06_exact_candidate_id)""")
    # Disk-backed exact pack index; no optimized Stage 10 cache/certificates reused.
    db.execute("CREATE TABLE review_lineage_objects AS SELECT * FROM reference_object")
    db.execute(
        "CREATE INDEX review_lineage_object_id ON review_lineage_objects(reference_object_id)"
    )
    db.execute(
        "CREATE TABLE review_lineage_members AS SELECT m.* FROM reference_match_member m WHERE m.match_set_id IN (SELECT match_set_id FROM review_lineage_source_evidence)"
    )
    schemas = {
        "CANDIDATE_V1": s8.candidate_evidence_schema(),
        "OCCURRENCE_V1": s8.representation_occurrence_schema(),
        "SOURCE_CONTEXT_V1": s8.source_candidate_map_schema(),
        "PARSER_COMPONENTS_V1": s8.parser_component_evidence_schema(),
        "SOURCE_REFERENCE_V1": s9.relation_schema("candidate_reference_evidence"),
    }
    selected = 0
    comparisons = Counter()
    failures = Counter()
    for context in rows(
        db,
        "SELECT k.* FROM contexts k JOIN review_lineage_sample x USING(query_context_id) ORDER BY query_context_id",
    ):
        selected += 1
        source = context["stable_source_row_id_v1"]
        candidate = context["stage06_exact_candidate_id"]
        role = context["stage08_representation"]
        args = [source, candidate]
        db.execute(
            "CREATE OR REPLACE TABLE review_lineage_current AS SELECT * FROM review_lineage_source_evidence WHERE stable_source_row_id_v1=? AND stage06_exact_candidate_id=?",
            args,
        )
        queries = {
            "CANDIDATE_V1": (
                "SELECT * FROM candidate_evidence WHERE stage06_exact_candidate_id=?",
                [candidate],
            ),
            "OCCURRENCE_V1": (
                "SELECT * FROM stage08_occurrence WHERE stable_source_row_id_v1=? AND stage08_representation=?",
                [source, role],
            ),
            "SOURCE_CONTEXT_V1": (
                "SELECT * FROM source_candidate_map WHERE stable_source_row_id_v1=?",
                [source],
            ),
            "PARSER_COMPONENTS_V1": (
                "SELECT * FROM parser_component_evidence WHERE stage06_exact_candidate_id=? ORDER BY stage08_component_ordinal",
                [candidate],
            ),
            "SOURCE_REFERENCE_V1": (
                "SELECT * FROM review_lineage_current ORDER BY evidence_id",
                [],
            ),
        }
        certs = {}
        for selector, (query, parameters) in queries.items():
            certs[selector] = certificate(
                ordered(row, schemas[selector]) for row in rows(db, query, parameters)
            )
        prefix = role.lower()
        suffix = "_native" if role == "NATIVE" else ""
        fields = (
            f"stage06_{prefix}_exact_candidate_id",
            *[f"stage04_lower_street_address_line_{i}{suffix}" for i in range(1, 5)],
            f"stage05_{prefix}_candidate_lower",
            f"stage05_{prefix}_candidate_available",
            f"stage05_{prefix}_contributing_line_count",
            f"stage05_{prefix}_contributing_line_mask",
        )
        certs["SOURCE_LINES_V1"] = certificate(
            tuple(r[f] for f in fields)
            for r in rows(
                db,
                "SELECT "
                + ",".join(fields)
                + " FROM stage06_row_map WHERE stable_source_row_id_v1=?",
                [source],
            )
        )
        db.execute("""CREATE OR REPLACE TABLE review_lineage_witness AS
          SELECT single_witness witness FROM review_lineage_current WHERE single_witness IS NOT NULL
          UNION SELECT m.witness FROM review_lineage_members m
          WHERE m.match_set_id IN (SELECT match_set_id FROM review_lineage_current)""")
        db.execute("""CREATE OR REPLACE TABLE review_lineage_reached AS WITH RECURSIVE reached(id) AS (
            (SELECT witness.reference_object_id FROM review_lineage_witness
             UNION SELECT p.reference_object_id FROM review_lineage_witness CROSS JOIN unnest(witness.fields) t(p))
            UNION SELECT o.explicit_parent_id FROM reached r JOIN review_lineage_objects o ON o.reference_object_id=r.id
                WHERE o.explicit_parent_id IS NOT NULL) SELECT DISTINCT id FROM reached""")
        db.execute("""CREATE OR REPLACE TABLE review_lineage_caps AS SELECT cap.* FROM reference_capability cap
           WHERE capability_id IN (SELECT capability_id FROM review_lineage_current UNION SELECT rule_capability_id FROM review_lineage_current)""")
        digest = hashlib.sha256()
        count = 0

        def append(section, payload):
            nonlocal count
            for chunk in framed((section,)):
                digest.update(chunk)
            digest.update(payload)
            count += 1

        witness_schema = (
            s9.relation_schema("reference_match_member").field("witness").type
        )
        # Source schedule is fixed at 18 slots; singleton set is bounded by 18.
        singletons = sorted(
            {
                b"".join(framed(ordered(r["single_witness"], witness_schema)))
                for r in rows(
                    db,
                    "SELECT single_witness FROM review_lineage_current WHERE single_witness IS NOT NULL",
                )
            }
        )
        for payload in singletons:
            append(0, payload)
        sections = (
            (
                1,
                "reference_match_member",
                "SELECT m.* FROM review_lineage_members m WHERE match_set_id IN (SELECT match_set_id FROM review_lineage_current) ORDER BY match_set_id,member_ordinal",
            ),
            (
                2,
                "reference_object",
                "SELECT o.* FROM review_lineage_objects o JOIN review_lineage_reached r ON o.reference_object_id=r.id ORDER BY o.reference_object_id",
            ),
            (
                3,
                "reference_capability",
                "SELECT * FROM review_lineage_caps ORDER BY capability_id",
            ),
            (
                4,
                "reference_registry",
                """SELECT reg.* FROM reference_registry reg WHERE reference_version_id IN (
              SELECT reference_version_id FROM review_lineage_current UNION SELECT reference_version_id FROM review_lineage_caps
              UNION SELECT o.reference_version_id FROM review_lineage_objects o JOIN review_lineage_reached r ON o.reference_object_id=r.id)
              ORDER BY reference_version_id""",
            ),
        )
        for section, name, query in sections:
            for r in rows(db, query):
                append(section, b"".join(framed(ordered(r, s9.relation_schema(name)))))
        certs["REFERENCE_WITNESSES_V1"] = {
            "selected_count": count,
            "selected_stream_sha256": digest.digest(),
        }
        for decision in rows(
            db,
            "SELECT lineage FROM query_family_decision WHERE query_context_id=?",
            [context["query_context_id"]],
        ):
            for actual in decision["lineage"]:
                selector = actual["selector_id"]
                comparisons[selector] += 1
                failures[selector] += any(
                    actual[k] != v for k, v in certs[selector].items()
                )
    for selector, count in comparisons.items():
        check("independent_selector_" + selector, failures[selector] == 0 and count > 0)
    check(
        "bounded_lineage_sample_totality",
        0 < selected <= 40
        and selected == scalar(db, "SELECT count(*) FROM review_lineage_sample"),
    )
    return {
        "contexts_reviewed": selected,
        "certificate_comparisons": dict(comparisons),
        "certificate_mismatches": dict(failures),
    }
