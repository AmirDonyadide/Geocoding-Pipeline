"""Exact overlapping incidence sets; evidence diagnostics, never accuracy."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any

import duckdb
import pyarrow as pa

from . import s09_reference_contract as c
from . import s09_reference_io as io


def scalar_count(db: duckdb.DuckDBPyConnection, sql: str) -> int:
    row = db.execute(sql).fetchone()
    c.require(row is not None and len(row) == 1, "AGGREGATE_RESULT_MISSING")
    assert row is not None
    return int(row[0])


def coverage_rows(
    db: duckdb.DuckDBPyConnection, countries: Sequence[str], counts: Mapping[str, int]
) -> Iterator[dict[str, Any]]:
    """Caller registers evidence, candidate_evidence and stage08_occurrence views."""
    db.execute(
        "CREATE TEMP VIEW evaluation_dimensions AS SELECT e.*,CASE WHEN c.stage07_country_provenance_status='COUNTRY_UNANIMOUS_VALID' THEN upper(c.stage07_trusted_country_iso_code) ELSE 'UNRESOLVED' END AS country_scope, CASE WHEN e.question_catalog_id='Q10' AND e.reference_slot='LIBADDRESSINPUT_METADATA' THEN 'ADMIN_ENUMERATION' ELSE q.capability END capability FROM evidence e JOIN candidate_evidence c USING(stage06_exact_candidate_id) JOIN question_slots q ON e.question_catalog_id=q.question_catalog_id AND e.reference_slot=q.reference_slot AND e.evidence_scope=q.evidence_scope"
    )
    db.execute(
        "CREATE TEMP TABLE evaluation_counts AS SELECT country_scope,evidence_scope,question_catalog_id,reference_slot,capability,result_state,count(*) AS n FROM evaluation_dimensions GROUP BY ALL UNION ALL SELECT 'ALL',evidence_scope,question_catalog_id,reference_slot,capability,result_state,count(*) FROM evaluation_dimensions GROUP BY ALL"
    )
    db.execute(
        "CREATE TEMP TABLE evaluation_denominators AS SELECT country_scope,evidence_scope,question_catalog_id,reference_slot,capability,sum(n)::UBIGINT AS denominator FROM evaluation_counts GROUP BY ALL"
    )
    db.register(
        "country_cells", pa.table({"country_scope": [*countries, "UNRESOLVED", "ALL"]})
    )
    db.register("four_states", pa.table({"result_state": list(c.STATES)}))
    sql = "SELECT 'EVALUATION' summary_kind,g.country_scope,q.evidence_scope,'ALL' representation,q.question_catalog_id,q.reference_slot,q.capability,s.result_state,'ALL' reason_code,'NONE' contradiction_type,coalesce(n.n,0) count,coalesce(d.denominator,0) denominator FROM country_cells g CROSS JOIN question_slots q CROSS JOIN four_states s LEFT JOIN evaluation_counts n USING(country_scope,evidence_scope,question_catalog_id,reference_slot,capability,result_state) LEFT JOIN evaluation_denominators d USING(country_scope,evidence_scope,question_catalog_id,reference_slot,capability)"
    yield from io.sorted_rows(db, sql)
    sql = "WITH reasons AS (SELECT country_scope,evidence_scope,question_catalog_id,reference_slot,capability,result_state,reason_code,coalesce(contradiction_type,'NONE') contradiction_type,count(*) count FROM evaluation_dimensions GROUP BY ALL UNION ALL SELECT 'ALL',evidence_scope,question_catalog_id,reference_slot,capability,result_state,reason_code,coalesce(contradiction_type,'NONE'),count(*) FROM evaluation_dimensions GROUP BY ALL) SELECT 'EVALUATION_REASON' summary_kind,r.country_scope,r.evidence_scope,'ALL' representation,r.question_catalog_id,r.reference_slot,r.capability,r.result_state,r.reason_code,r.contradiction_type,r.count,d.denominator FROM reasons r JOIN evaluation_denominators d USING(country_scope,evidence_scope,question_catalog_id,reference_slot,capability)"
    yield from io.sorted_rows(db, sql)
    db.execute(
        "CREATE TEMP TABLE candidate_incidence AS SELECT DISTINCT stage06_exact_candidate_id,question_catalog_id,reference_slot,capability,result_state FROM evaluation_dimensions"
    )
    db.execute(
        "CREATE TEMP TABLE candidate_denominators AS SELECT question_catalog_id,reference_slot,capability,count(DISTINCT stage06_exact_candidate_id) denominator FROM candidate_incidence GROUP BY ALL"
    )
    sql = "SELECT 'CANDIDATE_INCIDENCE' summary_kind,'ALL' country_scope,'ALL' evidence_scope,'ALL' representation,i.question_catalog_id,i.reference_slot,i.capability,i.result_state,'ALL' reason_code,'NONE' contradiction_type,count(*) count,d.denominator FROM candidate_incidence i JOIN candidate_denominators d USING(question_catalog_id,reference_slot,capability) GROUP BY ALL"
    yield from io.sorted_rows(db, sql)
    # Source-scoped evidence is only incident on that source, never broadcast
    # to every row sharing its candidate. Parser-scoped evidence maps to all.
    db.execute(
        "CREATE TEMP TABLE occurrence_incidence AS SELECT DISTINCT o.stable_source_row_id_v1,o.stage08_representation_ordinal,o.stage08_representation,e.question_catalog_id,e.reference_slot,e.capability,e.result_state FROM evaluation_dimensions e JOIN stage08_occurrence o USING(stage06_exact_candidate_id) WHERE e.evidence_scope='PARSER_CANDIDATE' OR e.stable_source_row_id_v1=o.stable_source_row_id_v1"
    )
    sql = f"SELECT 'SOURCE_INCIDENCE' summary_kind,'ALL' country_scope,'ALL' evidence_scope,'ALL' representation,question_catalog_id,reference_slot,capability,result_state,'ALL' reason_code,'NONE' contradiction_type,count(DISTINCT stable_source_row_id_v1) count,{counts['source_candidate_map']} denominator FROM occurrence_incidence GROUP BY ALL"
    yield from io.sorted_rows(db, sql)
    for representation, denominator in (
        ("STANDARD", counts["standard_occurrences"]),
        ("NATIVE", counts["native_occurrences"]),
        ("ALL", counts["representation_occurrence_v1"]),
    ):
        where = (
            ""
            if representation == "ALL"
            else "WHERE stage08_representation=" + io.sql_literal(representation)
        )
        sql = f"SELECT 'OCCURRENCE_INCIDENCE' summary_kind,'ALL' country_scope,'ALL' evidence_scope,{io.sql_literal(representation)} representation,question_catalog_id,reference_slot,capability,result_state,'ALL' reason_code,'NONE' contradiction_type,count(DISTINCT (stable_source_row_id_v1,stage08_representation_ordinal)) count,{denominator} denominator FROM occurrence_incidence {where} GROUP BY ALL"
        yield from io.sorted_rows(db, sql)
    db.execute(
        "CREATE TEMP TABLE country_reduction AS SELECT c.stage06_exact_candidate_id,CASE WHEN coalesce(bool_or(e.country_assessment='COUNTRY_SUPPORTED'),false) AND NOT coalesce(bool_or(e.country_assessment='COUNTRY_CONTRADICTED'),false) THEN 'COUNTRY_SUPPORTED' WHEN coalesce(bool_or(e.country_assessment='COUNTRY_CONTRADICTED'),false) AND NOT coalesce(bool_or(e.country_assessment='COUNTRY_SUPPORTED'),false) THEN 'COUNTRY_CONTRADICTED' ELSE 'COUNTRY_UNRESOLVED' END assessment FROM candidate_evidence c LEFT JOIN evidence e ON c.stage06_exact_candidate_id=e.stage06_exact_candidate_id AND e.evidence_scope='SOURCE_ROW' AND e.question_catalog_id='Q02' GROUP BY c.stage06_exact_candidate_id"
    )
    for state in c.COUNTRY_STATES:
        yield {
            "summary_kind": "COUNTRY_ASSESSMENT",
            "country_scope": "ALL",
            "evidence_scope": "ALL",
            "representation": "ALL",
            "question_catalog_id": "ALL",
            "reference_slot": "ALL",
            "capability": "ALL",
            "result_state": state,
            "reason_code": "ALL",
            "contradiction_type": "NONE",
            "count": scalar_count(
                db,
                "SELECT count(*) FROM country_reduction WHERE assessment="
                + io.sql_literal(state),
            ),
            "denominator": counts["candidate_evidence"],
        }


def register_question_slots(db: duckdb.DuckDBPyConnection) -> None:
    rows = [
        {
            "evidence_scope": scope,
            "question_catalog_id": q.question_id,
            "reference_slot": reference,
            "capability": c.capability_name(q, reference),
        }
        for scope in c.SCOPES
        for q in c.CATALOG
        for reference in q.references
        if not (scope == "SOURCE_ROW" and q.question_id == "Q14")
    ]
    db.register("question_slots", pa.Table.from_pylist(rows))


def aggregate_metrics(db: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "total_stage06_candidates": scalar_count(
            db, "SELECT count(*) FROM candidate_evidence"
        ),
        "candidates_with_evidence": scalar_count(
            db, "SELECT count(DISTINCT stage06_exact_candidate_id) FROM evidence"
        ),
        "candidates_evaluable": scalar_count(
            db,
            "SELECT count(DISTINCT stage06_exact_candidate_id) FROM evidence WHERE result_state<>'NOT_EVALUABLE'",
        ),
        "source_rows_without_candidate": scalar_count(
            db,
            "SELECT count(*) FROM source_candidate_map WHERE stage06_standard_exact_candidate_id IS NULL AND stage06_native_exact_candidate_id IS NULL",
        ),
        "evidence_rows": scalar_count(db, "SELECT count(*) FROM evidence"),
        "technical_failures": 0,
        "network_calls": 0,
        "geocoder_calls": 0,
        "parser_calls": 0,
    }
    metrics["candidates_without_evidence"] = (
        metrics["total_stage06_candidates"] - metrics["candidates_with_evidence"]
    )
    for name, columns in (
        ("four_state_counts", "result_state"),
        ("reference_family_counts", "reference_slot"),
        ("reason_counts", "reason_code"),
        ("contradiction_counts", "contradiction_type"),
    ):
        metrics[name] = {
            row["dimension"]: row["n"]
            for row in io.sorted_rows(
                db,
                f"SELECT coalesce({columns},'NONE') AS dimension,count(*) n FROM evidence GROUP BY ALL ORDER BY dimension",
            )
        }
    metrics["geonames_contradicted"] = scalar_count(
        db,
        "SELECT count(*) FROM evidence WHERE reference_slot='GEONAMES_POSTAL' AND result_state='CONTRADICTED'",
    )
    metrics["geonames_association_mismatch"] = scalar_count(
        db,
        "SELECT count(*) FROM evidence WHERE reference_slot='GEONAMES_POSTAL' AND reason_code='REFERENCE_ASSOCIATION_MISMATCH'",
    )
    return metrics
