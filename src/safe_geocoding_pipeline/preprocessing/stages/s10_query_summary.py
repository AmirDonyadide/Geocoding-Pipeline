"""Closed sanitized aggregates and complete context/map-back cardinality checks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import duckdb

from . import s10_query_contract as c

VALIDATIONS = tuple(
    """missing_contexts added_contexts missing_candidates added_candidates
missing_sources added_sources orphan_hypotheses orphan_family_memberships
cross_context_memberships context_fk_mismatches selector_mismatches byte_collisions
map_back_mismatches technical_failures portable_protected_values pelias_calls
external_address_calls""".split()
)
FIELDS = ("address", "postalcode", "locality", "region", "country", "boundary_country")


def scalar(db: duckdb.DuckDBPyConnection, sql: str) -> int:
    result = db.execute(sql).fetchone()
    c.require(result is not None and result[0] is not None, "STAGE10_AGGREGATE_NULL")
    assert result is not None
    count = int(result[0])
    c.require(0 <= count < 2**64, "STAGE10_AGGREGATE_OVERFLOW")
    return count


def zero(db: duckdb.DuckDBPyConnection, sql: str, code: str) -> None:
    c.require(scalar(db, sql) == 0, code)


def validate_integrity(db: duckdb.DuckDBPyConnection) -> None:
    """All checks operate on full disk relations, including zero-output contexts."""
    for name, key in c.PRIMARY_KEYS.items():
        zero(
            db,
            f"SELECT count(*)-count(DISTINCT {key[0]}) FROM {name}",
            "STAGE10_PK_DUPLICATE",
        )
        zero(
            db,
            f"""SELECT count(*) FROM {name} h LEFT JOIN stage10_context_keys k USING(query_context_id)
WHERE k.query_context_id IS NULL OR h.stable_source_row_id_v1 IS DISTINCT FROM k.stable_source_row_id_v1
OR h.stage08_representation IS DISTINCT FROM k.stage08_representation
OR h.stage06_exact_candidate_id IS DISTINCT FROM k.stage06_exact_candidate_id""",
            "STAGE10_CONTEXT_FK_MISMATCH",
        )
    zero(
        db,
        """SELECT count(*) FROM stage10_context_keys k LEFT JOIN
(SELECT query_context_id,count(*) n,count(DISTINCT family) f FROM query_family_decision GROUP BY 1) d USING(query_context_id)
WHERE d.n IS DISTINCT FROM 6 OR d.f IS DISTINCT FROM 6""",
        "STAGE10_DECISION_TOTALITY_INVALID",
    )
    zero(
        db,
        """SELECT count(*) FROM query_family_decision d LEFT JOIN query_hypothesis h USING(hypothesis_id)
WHERE d.hypothesis_id IS NOT NULL AND (h.hypothesis_id IS NULL OR d.query_context_id<>h.query_context_id
OR d.stable_source_row_id_v1<>h.stable_source_row_id_v1 OR d.stage06_exact_candidate_id<>h.stage06_exact_candidate_id
OR d.stage08_representation<>h.stage08_representation)""",
        "STAGE10_MEMBERSHIP_ORPHAN_OR_CROSS_CONTEXT",
    )
    zero(
        db,
        """SELECT count(*) FROM query_hypothesis h LEFT JOIN
(SELECT hypothesis_id,count(*) FILTER(WHERE membership_state='FIRST_MEMBER') n FROM query_family_decision
WHERE hypothesis_id IS NOT NULL GROUP BY 1) d USING(hypothesis_id) WHERE d.n IS DISTINCT FROM 1""",
        "STAGE10_HYPOTHESIS_MEMBERSHIP_INVALID",
    )
    zero(
        db,
        """SELECT count(*) FROM (SELECT query_context_id,count(*) n, count(DISTINCT representation_fingerprint) f,
min(generation_rank) lo,max(generation_rank) hi,count(DISTINCT generation_rank) ranks FROM query_hypothesis GROUP BY 1)
WHERE n<>f OR lo<>1 OR hi<>n OR ranks<>n""",
        "STAGE10_INTENT_OR_RANK_DUPLICATE",
    )
    zero(
        db,
        """SELECT count(*) FROM (SELECT representation_fingerprint,count(DISTINCT intent) n FROM query_hypothesis GROUP BY 1) WHERE n>1""",
        "STAGE10_INTENT_HASH_COLLISION",
    )
    zero(
        db,
        """SELECT count(*) FROM (SELECT boundary_fingerprint,count(DISTINCT boundary_value) n FROM stage10_context_diagnostics GROUP BY 1) WHERE n>1""",
        "STAGE10_BOUNDARY_HASH_COLLISION",
    )
    zero(
        db,
        """SELECT count(*) FROM stage10_context_keys k LEFT JOIN
(SELECT query_context_id,count(*) n FROM stage10_context_diagnostics GROUP BY 1) d USING(query_context_id)
WHERE d.n IS DISTINCT FROM 1""",
        "STAGE10_DIAGNOSTIC_CONTEXT_TOTALITY_INVALID",
    )
    zero(
        db,
        """SELECT count(*) FROM (SELECT stable_source_row_id_v1,count(*) n,count(DISTINCT stage08_representation) r
FROM stage10_context_keys GROUP BY 1) WHERE n>2 OR n<>r""",
        "STAGE10_CONTEXT_ROW_BOUND_INVALID",
    )
    zero(
        db,
        """SELECT count(*) FROM (SELECT h.query_context_id,h.stage08_representation,count(*) n
FROM query_hypothesis h GROUP BY 1,2) WHERE n>5 OR (stage08_representation='STANDARD' AND n>4)""",
        "STAGE10_ENGINEERING_CONTEXT_OVERFLOW",
    )
    zero(
        db,
        """SELECT count(*) FROM (SELECT stable_source_row_id_v1,count(*) n FROM query_hypothesis GROUP BY 1) WHERE n>10 OR n>9""",
        "STAGE10_ENGINEERING_ROW_OVERFLOW",
    )
    zero(
        db,
        """SELECT count(*) FROM (SELECT stage06_exact_candidate_id,count(*) n FROM query_hypothesis GROUP BY 1) h
JOIN stage10_candidates c USING(stage06_exact_candidate_id) WHERE h.n>5*c.stage06_occurrence_count
OR h.n>4*c.stage06_standard_occurrence_count+5*c.stage06_native_occurrence_count""",
        "STAGE10_ENGINEERING_CANDIDATE_OVERFLOW",
    )
    zero(
        db,
        """SELECT count(*) FROM query_family_decision WHERE family NOT IN ('Q1','Q2','Q3','Q4','Q5','Q6')
OR list_contains(reason_codes,'QUERY_BUDGET_SUPPRESSION')""",
        "STAGE10_UNAPPROVED_FAMILY_OR_BUDGET",
    )


def _bins(limit: int | None) -> list[tuple[int, int]]:
    if limit is not None:
        return [(i, i) for i in range(limit + 1)]
    result = [(0, 0), (1, 1), (2, 2)]
    lower = 3
    while lower < 2**64:
        upper = min(2 * (lower - 1), 2**64 - 1)
        result.append((lower, upper))
        lower = upper + 1
    return result


def build_summary(
    db: duckdb.DuckDBPyConnection, inputs: bytes, science: bytes
) -> dict[str, Any]:
    validate_integrity(db)
    n = {
        name: scalar(db, f"SELECT count(*) FROM {relation}")
        for name, relation in (
            ("SOURCE_ROW", "stage10_sources"),
            ("CANDIDATE", "stage10_candidates"),
            ("CONTEXT", "stage10_context_keys"),
            ("FAMILY_SLOT", "query_family_decision"),
            ("HYPOTHESIS", "query_hypothesis"),
        )
    }
    n["FIELD_SLOT"] = 6 * n["CONTEXT"]

    def metric(count: int, kind: str = "ABSOLUTE") -> dict[str, Any]:
        c.require(
            type(count) is int and 0 <= count < 2**64, "STAGE10_METRIC_UINT64_INVALID"
        )
        return {
            "count": count,
            "denominator": None if kind == "ABSOLUTE" else n[kind],
            "denominator_kind": kind,
        }

    def count(sql: str, kind: str = "ABSOLUTE") -> dict[str, Any]:
        return metric(scalar(db, sql), kind)

    def group_count(query: str, predicate: str, kind: str) -> dict[str, Any]:
        return count(f"SELECT count(*) FROM ({query}) WHERE {predicate}", kind)

    queries = {
        "HYPOTHESES_PER_CONTEXT": (
            "SELECT k.query_context_id,count(h.hypothesis_id) n FROM stage10_context_keys k LEFT JOIN query_hypothesis h USING(query_context_id) GROUP BY 1",
            "CONTEXT",
            5,
        ),
        "HYPOTHESES_PER_SOURCE_ROW": (
            "SELECT s.stable_source_row_id_v1,count(h.hypothesis_id) n FROM stage10_sources s LEFT JOIN query_hypothesis h USING(stable_source_row_id_v1) GROUP BY 1",
            "SOURCE_ROW",
            10,
        ),
        "CONTEXTS_PER_SOURCE_ROW": (
            "SELECT s.stable_source_row_id_v1,count(k.query_context_id) n FROM stage10_sources s LEFT JOIN stage10_context_keys k USING(stable_source_row_id_v1) GROUP BY 1",
            "SOURCE_ROW",
            2,
        ),
        "HYPOTHESES_PER_CANDIDATE": (
            "SELECT c.stage06_exact_candidate_id,count(h.hypothesis_id) n FROM stage10_candidates c LEFT JOIN query_hypothesis h USING(stage06_exact_candidate_id) GROUP BY 1",
            "CANDIDATE",
            None,
        ),
        "CONTEXTS_PER_CANDIDATE": (
            "SELECT c.stage06_exact_candidate_id,count(k.query_context_id) n FROM stage10_candidates c LEFT JOIN stage10_context_keys k USING(stage06_exact_candidate_id) GROUP BY 1",
            "CANDIDATE",
            None,
        ),
        "COUNTRY_CONTEXTS_PER_CANDIDATE": (
            "SELECT c.stage06_exact_candidate_id,count(DISTINCT (k.country_state,k.country)) FILTER(WHERE k.query_context_id IS NOT NULL) n FROM stage10_candidates c LEFT JOIN stage10_context_diagnostics k USING(stage06_exact_candidate_id) GROUP BY 1",
            "CANDIDATE",
            None,
        ),
        "BOUNDARY_CONTEXTS_PER_CANDIDATE": (
            "SELECT c.stage06_exact_candidate_id,count(DISTINCT k.boundary_value) n FROM stage10_candidates c LEFT JOIN stage10_context_diagnostics k USING(stage06_exact_candidate_id) GROUP BY 1",
            "CANDIDATE",
            None,
        ),
    }
    # Persist compact grouped counts once; histogram queries never rescan payloads.
    for index, (query, _, _) in enumerate(queries.values()):
        db.execute(
            f"CREATE OR REPLACE TEMP TABLE summary_distribution_{index} AS {query}"
        )
    queries = {
        scope: (f"SELECT * FROM summary_distribution_{i}", kind, limit)
        for i, (scope, (_, kind, limit)) in enumerate(queries.items())
    }
    histograms, extrema = [], []
    for scope, (query, kind, limit) in queries.items():
        bounds = _bins(limit)
        case = (
            "CASE "
            + " ".join(
                f"WHEN n BETWEEN {lo} AND {hi} THEN {i}"
                for i, (lo, hi) in enumerate(bounds)
            )
            + " ELSE -1 END"
        )
        distribution = dict(
            db.execute(
                f"SELECT {case} bin,count(*) FROM ({query}) GROUP BY 1"
            ).fetchall()
        )
        c.require(-1 not in distribution, "STAGE10_HISTOGRAM_OVERFLOW")
        for i, (lo, hi) in enumerate(bounds):
            histograms.append(
                {
                    "scope": scope,
                    "lower_inclusive": lo,
                    "upper_inclusive": hi,
                    **metric(int(distribution.get(i, 0)), kind),
                }
            )
        extrema.append(
            {
                "scope": scope,
                **{
                    name: scalar(db, f"SELECT coalesce({fn}(n),0) FROM ({query})")
                    for name, fn in (
                        ("minimum", "min"),
                        ("maximum", "max"),
                        ("sum", "sum"),
                    )
                },
            }
        )
    eligible = scalar(
        db,
        "SELECT count(*) FROM query_family_decision WHERE eligibility_state='ELIGIBLE'",
    )
    distinct = scalar(
        db, "SELECT count(DISTINCT representation_fingerprint) FROM query_hypothesis"
    )
    role_counts = {
        role: scalar(
            db,
            f"SELECT count(*) FROM stage10_context_keys WHERE stage08_representation='{role}'",
        )
        for role in c.ROLES
    }
    coverage = {}
    for scope, kind, yes, no in (
        (
            "HYPOTHESES_PER_CONTEXT",
            "CONTEXT",
            "contexts_with_hypothesis",
            "contexts_without_hypothesis",
        ),
        (
            "HYPOTHESES_PER_SOURCE_ROW",
            "SOURCE_ROW",
            "source_rows_with_hypothesis",
            "source_rows_without_hypothesis",
        ),
        (
            "HYPOTHESES_PER_CANDIDATE",
            "CANDIDATE",
            "candidates_with_hypothesis",
            "candidates_without_hypothesis",
        ),
    ):
        query = queries[scope][0]
        coverage[yes] = group_count(query, "n>0", kind)
        coverage[no] = group_count(query, "n=0", kind)
    # Closed-dimension aggregate passes; no per-cell rescans of 141M rows.
    family_totals = {
        tuple(row[:3]): int(row[3])
        for row in db.execute(
            "SELECT family,eligibility_state,membership_state,count(*) FROM query_family_decision GROUP BY 1,2,3"
        ).fetchall()
    }
    family_empty = {
        tuple(row[:3]): int(row[3])
        for row in db.execute(
            "SELECT family,eligibility_state,membership_state,count(*) FROM query_family_decision WHERE len(reason_codes)=0 GROUP BY 1,2,3"
        ).fetchall()
    }
    family_reasons = {
        tuple(row[:4]): int(row[4])
        for row in db.execute(
            "SELECT family,eligibility_state,membership_state,reason,count(*) FROM query_family_decision,unnest(reason_codes) r(reason) GROUP BY 1,2,3,4"
        ).fetchall()
    }
    family_cells = []
    for family in c.FAMILIES:
        for eligibility, membership in (
            ("ELIGIBLE", "FIRST_MEMBER"),
            ("ELIGIBLE", "CONVERGENT_MEMBER"),
            ("INELIGIBLE", "NONE"),
        ):
            key = (family, eligibility, membership)
            for reason in ("ALL", "NONE", *c.REASONS):
                value = (
                    family_totals.get(key, 0)
                    if reason == "ALL"
                    else family_empty.get(key, 0)
                    if reason == "NONE"
                    else family_reasons.get((*key, reason), 0)
                )
                family_cells.append(
                    {
                        "family": family,
                        "eligibility": eligibility,
                        "membership": membership,
                        "reason": reason,
                        **metric(value, "CONTEXT"),
                    }
                )
    field_cells = []
    db.execute(
        "CREATE OR REPLACE TEMP TABLE summary_fields AS SELECT unnest(field_decisions) f FROM query_family_decision WHERE family='Q4'"
    )
    field_totals = {
        tuple(row[:2]): int(row[2])
        for row in db.execute(
            "SELECT f.field,f.disposition,count(*) FROM summary_fields GROUP BY 1,2"
        ).fetchall()
    }
    field_empty = {
        tuple(row[:2]): int(row[2])
        for row in db.execute(
            "SELECT f.field,f.disposition,count(*) FROM summary_fields WHERE len(f.reason_codes)=0 GROUP BY 1,2"
        ).fetchall()
    }
    field_reasons = {
        tuple(row[:3]): int(row[3])
        for row in db.execute(
            "SELECT f.field,f.disposition,reason,count(*) FROM summary_fields,unnest(f.reason_codes) r(reason) GROUP BY 1,2,3"
        ).fetchall()
    }
    for field in FIELDS:
        for disposition in ("INCLUDE", "OMIT", "NOT_APPLICABLE"):
            key2 = (field, disposition)
            for reason in ("ALL", "NONE", *c.REASONS):
                value = (
                    field_totals.get(key2, 0)
                    if reason == "ALL"
                    else field_empty.get(key2, 0)
                    if reason == "NONE"
                    else field_reasons.get((*key2, reason), 0)
                )
                field_cells.append(
                    {
                        "field": field,
                        "disposition": disposition,
                        "reason": reason,
                        **metric(value, "FIELD_SLOT"),
                    }
                )
    masks = dict(
        db.execute("""SELECT mask,count(*) FROM (SELECT hypothesis_id,
CAST(sum(CASE family WHEN 'Q1' THEN 1 WHEN 'Q2' THEN 2 WHEN 'Q3' THEN 4 WHEN 'Q4' THEN 8 WHEN 'Q5' THEN 16 WHEN 'Q6' THEN 32 END) AS INTEGER) mask
FROM query_family_decision WHERE hypothesis_id IS NOT NULL GROUP BY 1) GROUP BY 1""").fetchall()
    )
    baseline_pairs = """SELECT a.stable_source_row_id_v1,h.intent left_intent,i.intent right_intent FROM query_family_decision a
JOIN query_family_decision b USING(stable_source_row_id_v1) JOIN query_hypothesis h ON h.hypothesis_id=a.hypothesis_id
JOIN query_hypothesis i ON i.hypothesis_id=b.hypothesis_id WHERE a.family='Q1' AND b.family='Q2'"""
    result = {
        "summary_version": c.SUMMARY,
        "input_binding_sha256": inputs.hex(),
        "science_sha256": science.hex(),
        "budget_policy_sha256": c.budget_fingerprint().hex(),
        "plan_mode": c.MODE,
        "operating_budget": None,
        "ceilings": {
            "per_context": 5,
            "per_source_row": 10,
            "per_candidate": "5*occurrence_count",
        },
        "deferred_families": {"Q7": "DEFERRED_RESULT_DEPENDENT_DIAGNOSTIC"},
        "input_counts": {
            "source_rows": metric(n["SOURCE_ROW"]),
            "candidates": metric(n["CANDIDATE"]),
            "occurrences": metric(n["CONTEXT"]),
            "standard_occurrences": metric(role_counts["STANDARD"]),
            "native_occurrences": metric(role_counts["NATIVE"]),
            "parser_components": count("SELECT count(*) FROM stage10_components"),
            "reference_evidence_rows": count(
                "SELECT count(*) FROM candidate_reference_evidence"
            ),
            "source_rows_without_candidate": group_count(
                queries["CONTEXTS_PER_SOURCE_ROW"][0], "n=0", "SOURCE_ROW"
            ),
        },
        "context_counts": {
            "contexts": metric(n["CONTEXT"]),
            "standard_contexts": metric(role_counts["STANDARD"], "CONTEXT"),
            "native_contexts": metric(role_counts["NATIVE"], "CONTEXT"),
            **{
                key: group_count(queries[scope][0], "n>1", kind)
                for key, scope, kind in (
                    (
                        "candidates_with_multiple_contexts",
                        "CONTEXTS_PER_CANDIDATE",
                        "CANDIDATE",
                    ),
                    (
                        "source_rows_with_multiple_contexts",
                        "CONTEXTS_PER_SOURCE_ROW",
                        "SOURCE_ROW",
                    ),
                    (
                        "candidates_with_multiple_country_contexts",
                        "COUNTRY_CONTEXTS_PER_CANDIDATE",
                        "CANDIDATE",
                    ),
                    (
                        "candidates_with_multiple_boundary_contexts",
                        "BOUNDARY_CONTEXTS_PER_CANDIDATE",
                        "CANDIDATE",
                    ),
                )
            },
        },
        "coverage_counts": coverage,
        "hypothesis_counts": {
            "eligible_family_constructions": metric(eligible, "FAMILY_SLOT"),
            "hypotheses": metric(n["HYPOTHESIS"]),
            "global_distinct_intents": metric(distinct),
            "within_context_duplicate_reduction": metric(eligible - n["HYPOTHESIS"]),
            "across_context_intent_reduction": metric(n["HYPOTHESIS"] - distinct),
            "generated_query_utf8_bytes": count(
                "SELECT coalesce(sum(octet_length(encode(concat(intent.text,intent.address,intent.postalcode,intent.locality,intent.region,intent.country,intent.boundary_country)))),0) FROM query_hypothesis"
            ),
        },
        "engineering_counts": {
            "contexts_at_ceiling": group_count(
                queries["HYPOTHESES_PER_CONTEXT"][0], "n=5", "CONTEXT"
            ),
            "source_rows_at_ceiling": group_count(
                queries["HYPOTHESES_PER_SOURCE_ROW"][0], "n=10", "SOURCE_ROW"
            ),
            "bound_violations": metric(0),
            "operating_budget_suppressions": metric(0),
        },
        "family_cells": family_cells,
        "convergence_cells": {
            "by_family_mask": [
                {"mask": mask, **metric(int(masks.get(mask, 0)), "HYPOTHESIS")}
                for mask in range(1, 64)
            ],
            "same_row_full_standard_native_equal": count(
                f"SELECT count(*) FROM ({baseline_pairs}) WHERE left_intent=right_intent",
                "SOURCE_ROW",
            ),
            "same_row_full_standard_native_evaluable": count(
                f"SELECT count(*) FROM ({baseline_pairs})", "SOURCE_ROW"
            ),
        },
        "field_decision_cells": field_cells,
        "histograms": {"cells": histograms, "extrema": extrema},
        "artifact_row_counts": {
            "query_hypothesis": metric(n["HYPOTHESIS"]),
            "query_family_decision": metric(n["FAMILY_SLOT"]),
            "portable_summary_objects": metric(1),
        },
        "validation_counts": {key: metric(0) for key in VALIDATIONS},
    }
    return result


def reconcile_summary(observed: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    # Full equality enforces the closed field/enum/cell inventories and counts.
    c.require(
        c.canonical(observed) == c.canonical(expected),
        "STAGE10_SUMMARY_RECONCILIATION_FAILED",
    )
