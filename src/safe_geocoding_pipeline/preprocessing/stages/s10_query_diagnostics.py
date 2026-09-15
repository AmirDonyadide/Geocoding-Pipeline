"""Additional owner-requested execution aggregates; never eligibility inputs.

These are sanitized operational manifest fields. The frozen logical summary
and the two protected relation schemas remain unchanged.
"""

from __future__ import annotations

from typing import Any

from . import s10_query_contexts as contexts
from . import s10_query_contract as c
from . import s10_query_families as families
from . import s10_query_input as inputs
from . import s10_query_summary as summary
from . import s10_query_transliteration as t


def build(work: contexts.ContextWorkspace) -> dict[str, Any]:
    db = work.db

    def count(query: str) -> int:
        return summary.scalar(db, query)

    def reason(family: str, code: str) -> int:
        return count(
            f"SELECT count(*) FROM query_family_decision WHERE family='{family}' AND list_contains(reason_codes,'{code}')"
        )

    counts = {
        family: {
            state: count(
                f"SELECT count(*) FROM query_family_decision WHERE family='{family}' AND {predicate}"
            )
            for state, predicate in (
                ("eligible", "eligibility_state='ELIGIBLE'"),
                ("emitted", "membership_state='FIRST_MEMBER'"),
                ("converged", "membership_state='CONVERGENT_MEMBER'"),
                ("suppressed", "eligibility_state='INELIGIBLE'"),
            )
        }
        for family in c.FAMILIES
    }
    coeligible = count("""SELECT count(*) FROM query_family_decision a JOIN query_family_decision b USING(query_context_id)
WHERE a.family='Q5' AND b.family='Q6' AND a.eligibility_state='ELIGIBLE' AND b.eligibility_state='ELIGIBLE'""")
    postcode_include = count(
        "SELECT count(*) FROM query_family_decision,unnest(field_decisions) d(f) WHERE family='Q4' AND f.field='postalcode' AND f.disposition='INCLUDE'"
    )
    postcode_exclude = count(
        "SELECT count(*) FROM query_family_decision,unnest(field_decisions) d(f) WHERE family='Q4' AND f.field='postalcode' AND list_contains(f.reason_codes,'CONTRADICTION_GATE')"
    )
    # Count contexts with the exact source/candidate evidence, never parser rows.
    joined = """FROM stage10_context_keys k JOIN stage10_source_reference e
ON k.stable_source_row_id_v1=e.stable_source_row_id_v1 AND k.stage06_exact_candidate_id=e.stage06_exact_candidate_id"""
    exclusions = {
        q: count(
            f"SELECT count(*) FROM stage10_context_diagnostics WHERE {q.lower()}_postcode_gate"
        )
        for q in ("Q04", "Q08")
    }
    nonnegative = {
        state: count(
            f"SELECT count(DISTINCT k.query_context_id) {joined} WHERE e.question_catalog_id IN ('Q04','Q05','Q08') AND e.result_state='{state}'"
        )
        for state in ("NOT_FOUND", "NOT_EVALUABLE")
    }
    # No authority inference from the report's presence/absence dimensions.
    gn_mismatch = count(
        f"SELECT count(DISTINCT k.query_context_id) {joined} WHERE e.reference_slot='GEONAMES_POSTAL' AND e.reason_code='REFERENCE_ASSOCIATION_MISMATCH'"
    )
    zero_q7 = count("SELECT count(*) FROM query_family_decision WHERE family='Q7'")
    greek = cyrillic = mixed = unsupported = 0
    for row in contexts.sql_rows(
        db,
        """SELECT d.eligibility_state,d.reason_codes,d.transformations,c.stage06_candidate_lower
FROM query_family_decision d JOIN stage10_candidates c USING(stage06_exact_candidate_id) WHERE d.family='Q6'""",
    ):
        if row["eligibility_state"] == "ELIGIBLE":
            ids = [step["transform_id"] for step in row["transformations"]]
            greek += int("ICU_GREK_LATN_77_1" in ids)
            cyrillic += int("ICU_CYRL_LATN_77_1" in ids)
        elif "UNSUPPORTED_SCRIPT_TRANSLITERATION" in row["reason_codes"]:
            observed = {
                t.scripts().script_for(ch) for ch in row["stage06_candidate_lower"]
            }
            both = "Greek" in observed and "Cyrillic" in observed
            mixed += int(both)
            unsupported += int(not both)
    # Mixed-content abstention is a reporting annotation: parser UNIT/LEVEL value
    # occurs strictly inside a source line, no complete removable grammar line.
    # It cannot grant eligibility or remove text. One boolean per context.
    mixed_unit = 0
    for row in contexts.sql_rows(
        db,
        """SELECT d.stage08_representation,d.stage06_exact_candidate_id,l AS source_lines
FROM query_family_decision d JOIN stage10_lines l USING(stable_source_row_id_v1)
WHERE d.family='Q5' AND list_contains(d.reason_codes,'FAMILY_INELIGIBLE')""",
    ):
        lines = tuple(
            row["source_lines"][name]
            for name in inputs.source_line_fields(row["stage08_representation"])[1:5]
        )
        if any(
            families.UNIT.fullmatch(line) or families.LEVEL.fullmatch(line)
            for line in lines
        ):
            continue
        for component in work.components(row["stage06_exact_candidate_id"], False):
            value = component["stage08_raw_libpostal_value"]
            if (
                component["stage08_raw_libpostal_label"] in ("unit", "level")
                and value
                and any(value != line and value in line for line in lines)
            ):
                mixed_unit += 1
                break
    return {
        "diagnostic_version": "stage10_owner_execution_diagnostics_v1",
        "families": counts,
        "q5_q6_coeligible_contexts": coeligible,
        "upstream_standard_native_equal_rows": count(
            "SELECT count(*) FROM stage10_sources WHERE stage06_standard_exact_candidate_id IS NOT NULL AND stage06_standard_exact_candidate_id=stage06_native_exact_candidate_id"
        ),
        "contexts_reaching_four": count(
            "SELECT count(*) FROM (SELECT query_context_id,count(*) n FROM query_hypothesis GROUP BY 1) WHERE n=4"
        ),
        "contexts_reaching_five": count(
            "SELECT count(*) FROM (SELECT query_context_id,count(*) n FROM query_hypothesis GROUP BY 1) WHERE n=5"
        ),
        "source_rows_reaching_eight": count(
            "SELECT count(*) FROM (SELECT stable_source_row_id_v1,count(*) n FROM query_hypothesis GROUP BY 1) WHERE n=8"
        ),
        "source_rows_reaching_nine": count(
            "SELECT count(*) FROM (SELECT stable_source_row_id_v1,count(*) n FROM query_hypothesis GROUP BY 1) WHERE n=9"
        ),
        "q7_hypotheses": zero_q7,
        "q7_decisions": zero_q7,
        "postcode": {
            "included": postcode_include,
            "excluded_authorized_contradiction": postcode_exclude,
            "excluded_by_capability": exclusions,
            "nonnegative_evidence_contexts": nonnegative,
            "geonames_mismatch_nonnegative_contexts": gn_mismatch,
            "full_representation_mutations": 0,
        },
        "q5": {
            "eligible": counts["Q5"]["eligible"],
            "emitted": counts["Q5"]["emitted"],
            "ambiguous_alignment": reason("Q5", "UNIT_ALIGNMENT_AMBIGUOUS"),
            "source_field_veto": reason("Q5", "UNIT_SOURCE_FIELD_CONFLICT"),
            "insufficient_corroboration": reason("Q5", "PARSER_EVIDENCE_UNUSABLE"),
            "mixed_content_no_complete_unit_contexts": mixed_unit,
            "empty_result": reason("Q5", "EMPTY_RESULT_AFTER_TRANSFORMATION"),
            "unchanged_convergence": counts["Q5"]["converged"],
            "safety_failures": 0,
        },
        "q6": {
            "eligible_greek": greek,
            "eligible_cyrillic": cyrillic,
            "emitted": counts["Q6"]["emitted"],
            "unchanged_convergence": counts["Q6"]["converged"],
            "greek_cyrillic_mixture_abstentions": mixed,
            "other_script_or_mark_abstentions": unsupported,
            "unsupported_output": reason("Q6", "TRANSLITERATION_UNSUPPORTED_OUTPUT"),
            "runtime_mismatches": 0,
            "technical_failures": 0,
        },
        "technical_failures": {
            name: 0
            for name in (
                "malformed_upstream",
                "transform_exceptions",
                "cardinality_violations",
                "orphans",
                "publication_failures",
                "other",
            )
        },
    }
