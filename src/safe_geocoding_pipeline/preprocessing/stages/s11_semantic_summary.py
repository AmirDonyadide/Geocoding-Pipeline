"""Closed aggregate diagnostics. Multiplicity never measures correctness."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import duckdb

from . import s11_semantic_contract as c

BINS = ((1, 1), (2, 2), (3, 5), (6, 10), (11, 50), (51, 100), (101, 2**64 - 1))
INTEGRITY = (
    "input_duplicate_ids",
    "input_missing_ids",
    "invalid_intents",
    "invalid_boundaries",
    "invalid_policies",
    "invalid_encodings",
    "id_payload_collisions",
    "id_recompute_mismatches",
    "missing_mappings",
    "extra_mappings",
    "multiple_mappings",
    "orphan_requests",
    "orphan_foreign_keys",
    "projection_mismatches",
    "lineage_mismatches",
    "multiplicity_sum_mismatch",
)
LABELS = (
    "WORKLOAD_CONVERGENCE_ONLY",
    "NO_ACCURACY_ESTIMATE",
    "OPERATING_BUDGET_UNSELECTED",
    "NON_EXECUTABLE_CORE_CATALOG",
    "STAGE12_NOT_STARTED",
)


def descriptor() -> dict[str, Any]:
    return {
        "schema_version": c.SCHEMA,
        "summary_version": c.SUMMARY,
        "groups": {
            "summary_version": c.SUMMARY,
            "input_population": [
                "hypotheses",
                "sources",
                "contexts",
                "standard_contexts",
                "native_contexts",
                "decisions",
                "zero_hypothesis_contexts",
                "eligible_family_links",
                "selection_status",
                "operating_budget",
            ],
            "request_counts": [
                "unique_requests",
                "map_rows",
                "modes",
                "country_boundary",
            ],
            "reduction": ["hypotheses_saved", "reduction_fraction", "unique_fraction"],
            "multiplicity": [
                "bins",
                "maximum",
                "mean",
                "requests_with_multiple_hypotheses",
            ],
            "lineage_convergence": [
                "denominator",
                "cross_context",
                "cross_source",
                "cross_family",
                "family_cardinality",
                "standard_only",
                "native_only",
                "both_roles",
                "same_source_both_roles",
            ],
            "parameter_combinations": ["endpoint_mode_presence", "policies"],
            "integrity": list(INTEGRITY),
            "interpretation": list(LABELS),
        },
        "types": {
            "counters": "uint64",
            "fractions": {"numerator": "uint64", "denominator": "uint64_or_null"},
            "mode_values": ["FULL_TEXT", "STRUCTURED"],
            "boundary_values": ["bound", "unbounded"],
            "multiplicity_bins": BINS,
            "family_cardinalities": [1, 2, 3, 4, 5, 6],
            "presence_fields": [
                "address",
                "postalcode",
                "locality",
                "region",
                "country",
            ],
            "policy_constants": {
                k: v for k, v in c.CONSTANTS.items() if k.endswith("_policy")
            },
        },
        "constraints": [
            "NO_UNKNOWN_KEYS_OR_ARBITRARY_STRINGS",
            "RECOMPUTE_COMPLETE_AGGREGATES",
            "NO_FLOATS",
            "ZERO_INTEGRITY_FAILURES",
            "NO_ROW_VALUES_OR_IDS",
            "NO_OPERATIONAL_MEASUREMENTS",
            "NO_SELF_DATASET_OR_MANIFEST_HASH",
            "ALL_COUNTS_RECONCILE",
        ],
    }


def scalar(connection: duckdb.DuckDBPyConnection, sql: str) -> int:
    row = connection.execute(sql).fetchone()
    c.require(
        row is not None and type(row[0]) is int and 0 <= row[0] < 2**64,
        "S11_MAP_TOTALITY_INVALID",
    )
    assert row is not None
    return int(row[0])


def compute(
    connection: duckdb.DuckDBPyConnection, population: Mapping[str, int]
) -> dict[str, Any]:
    # s, m, h and d are exact validated relation views. Keep distinct incidence
    # tables disk backed; never collect memberships into Python or list_agg.
    connection.execute(
        "CREATE OR REPLACE TEMP TABLE multiplicity AS SELECT query_semantic_id,count(*)::UBIGINT AS n FROM m GROUP BY query_semantic_id"
    )
    connection.execute("""CREATE OR REPLACE TEMP TABLE incidence AS SELECT m.query_semantic_id,
        h.query_context_id,h.stable_source_row_id_v1,h.stage08_representation,h.hypothesis_id
        FROM m JOIN h USING(hypothesis_id)""")
    connection.execute("""CREATE OR REPLACE TEMP TABLE convergence AS
        SELECT query_semantic_id,count(DISTINCT query_context_id) AS contexts,
        count(DISTINCT stable_source_row_id_v1) AS sources,
        bool_or(stage08_representation='STANDARD') AS standard,
        bool_or(stage08_representation='NATIVE') AS native FROM incidence GROUP BY query_semantic_id""")
    connection.execute("""CREATE OR REPLACE TEMP TABLE families AS SELECT i.query_semantic_id,
        count(DISTINCT d.family) AS n FROM incidence i JOIN d
        ON i.hypothesis_id=d.hypothesis_id AND i.query_context_id=d.query_context_id
        WHERE d.eligibility_state='ELIGIBLE' AND d.membership_state IN ('FIRST_MEMBER','CONVERGENT_MEMBER')
        GROUP BY i.query_semantic_id""")
    n = population["hypotheses"]
    u = scalar(connection, "SELECT count(*) FROM s")

    def fraction(x: int, y: int) -> dict[str, int | None]:
        return {"numerator": x, "denominator": y if y else None}

    modes: list[dict[str, Any]] = []
    for endpoint, mode in c.PAIRS:
        core_count = scalar(
            connection, f"SELECT count(*) FROM s WHERE core.search_mode='{mode}'"
        )
        hypothesis_count = scalar(
            connection,
            f"SELECT count(*) FROM m JOIN s USING(query_semantic_id) WHERE core.search_mode='{mode}'",
        )
        modes.append(
            {
                "search_mode": mode,
                "requests": core_count,
                "hypotheses": hypothesis_count,
            }
        )
    bins: list[dict[str, Any]] = []
    for low, high in BINS:
        values = connection.execute(
            f"SELECT count(*),coalesce(sum(n),0)::UBIGINT FROM multiplicity WHERE n BETWEEN {low} AND {high}"
        ).fetchone()
        assert values is not None
        bins.append(
            {
                "minimum": low,
                "maximum": high,
                "requests": values[0],
                "hypotheses": values[1],
            }
        )
    combination_rows = connection.execute("""SELECT core.endpoint,core.search_mode,
        core.address IS NOT NULL,core.postalcode IS NOT NULL,core.locality IS NOT NULL,
        core.region IS NOT NULL,core.country IS NOT NULL,count(*)::UBIGINT,sum(n)::UBIGINT
        FROM s JOIN multiplicity USING(query_semantic_id) GROUP BY ALL ORDER BY 1,2,3,4,5,6,7""").fetchall()
    combinations = [
        {
            "endpoint": r[0],
            "search_mode": r[1],
            "presence": dict(
                zip(
                    ("address", "postalcode", "locality", "region", "country"),
                    r[2:7],
                    strict=True,
                )
            ),
            "requests": r[7],
            "hypotheses": r[8],
        }
        for r in combination_rows
    ]
    c.require(
        len(combinations) <= 4
        and sum(b["requests"] for b in bins) == u
        and sum(b["hypotheses"] for b in bins) == n
        and sum(m["requests"] for m in modes) == u
        and sum(m["hypotheses"] for m in modes) == n,
        "S11_MAP_TOTALITY_INVALID",
    )
    family_hist = [
        {
            "families": k,
            "requests": scalar(
                connection, f"SELECT count(*) FROM families WHERE n={k}"
            ),
        }
        for k in range(1, 7)
    ]
    c.require(sum(r["requests"] for r in family_hist) == u, "S11_MAP_TOTALITY_INVALID")
    return {
        "summary_version": c.SUMMARY,
        "input_population": {
            **population,
            "selection_status": "ALL_ELIGIBLE_CATALOG",
            "operating_budget": "UNSELECTED",
        },
        "request_counts": {
            "unique_requests": u,
            "map_rows": n,
            "modes": modes,
            "country_boundary": {
                "bound": {"requests": u, "hypotheses": n},
                "unbounded": {"requests": 0, "hypotheses": 0},
            },
        },
        "reduction": {
            "hypotheses_saved": n - u,
            "reduction_fraction": fraction(n - u, n),
            "unique_fraction": fraction(u, n),
        },
        "multiplicity": {
            "bins": bins,
            "maximum": scalar(
                connection, "SELECT coalesce(max(n),0)::UBIGINT FROM multiplicity"
            ),
            "mean": fraction(n, u),
            "requests_with_multiple_hypotheses": scalar(
                connection, "SELECT count(*) FROM multiplicity WHERE n>1"
            ),
        },
        "lineage_convergence": {
            "denominator": u,
            "cross_context": scalar(
                connection, "SELECT count(*) FROM convergence WHERE contexts>1"
            ),
            "cross_source": scalar(
                connection, "SELECT count(*) FROM convergence WHERE sources>1"
            ),
            "cross_family": scalar(
                connection, "SELECT count(*) FROM families WHERE n>1"
            ),
            "family_cardinality": family_hist,
            "standard_only": scalar(
                connection,
                "SELECT count(*) FROM convergence WHERE standard AND NOT native",
            ),
            "native_only": scalar(
                connection,
                "SELECT count(*) FROM convergence WHERE native AND NOT standard",
            ),
            "both_roles": scalar(
                connection, "SELECT count(*) FROM convergence WHERE native AND standard"
            ),
            "same_source_both_roles": scalar(
                connection,
                """SELECT count(DISTINCT query_semantic_id) FROM (
                SELECT query_semantic_id,stable_source_row_id_v1 FROM incidence GROUP BY ALL
                HAVING count(DISTINCT stage08_representation)=2)""",
            ),
        },
        "parameter_combinations": {
            "endpoint_mode_presence": combinations,
            "policies": [
                {
                    **{
                        k: c.CONSTANTS[k]
                        for k in (
                            "language_policy",
                            "layers_policy",
                            "sources_policy",
                            "spatial_policy",
                            "additional_parameter_policy",
                        )
                    },
                    "requests": u,
                    "hypotheses": n,
                }
            ],
        },
        "integrity": dict.fromkeys(INTEGRITY, 0),
        "interpretation": list(LABELS),
    }
