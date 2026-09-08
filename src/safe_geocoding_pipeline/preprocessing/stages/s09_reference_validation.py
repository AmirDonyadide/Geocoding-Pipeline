"""Independent state, lineage, witness, cardinality and reference checks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa

from . import s09_reference_contract as c
from . import s09_reference_evaluator as e
from . import s09_reference_io as io
from . import s09_reference_postal as postal
from .s09_reference_coverage import scalar_count


def _zero(db: duckdb.DuckDBPyConnection, sql: str, code: str) -> None:
    c.require(scalar_count(db, sql) == 0, code)


def validate_integrity(
    db: duckdb.DuckDBPyConnection,
    view: e.SmallReferenceView,
    evidence_paths: Sequence[Path],
    member_paths: Sequence[Path],
    object_paths: Sequence[Path],
    index_paths: Sequence[Path],
    *,
    profile: bytes,
    stage08_logical: bytes,
    counts: Mapping[str, int],
) -> dict[str, str]:
    """All joins bounded by the caller's private DuckDB memory/spill limits."""
    db.execute(
        "CREATE VIEW evidence AS SELECT * FROM " + io.parquet_sql(evidence_paths)
    )
    db.execute("CREATE VIEW members AS SELECT * FROM " + io.parquet_sql(member_paths))
    db.execute(
        "CREATE VIEW reference_objects AS SELECT * FROM " + io.parquet_sql(object_paths)
    )
    db.execute(
        "CREATE VIEW postal_index AS SELECT * FROM " + io.parquet_sql(index_paths)
    )
    db.register(
        "capabilities",
        pa.Table.from_pylist(
            list(view.capabilities.values()),
            schema=c.relation_schema("reference_capability"),
        ),
    )
    _zero(
        db,
        "SELECT count(*) FROM evidence e LEFT JOIN candidate_evidence c USING(stage06_exact_candidate_id) WHERE c.stage06_exact_candidate_id IS NULL",
        "EVIDENCE_CANDIDATE_FK_INVALID",
    )
    _zero(
        db,
        "SELECT count(*) FROM candidate_evidence c ANTI JOIN evidence e USING(stage06_exact_candidate_id)",
        "CANDIDATE_EVIDENCE_LOSS",
    )
    _zero(
        db,
        "SELECT count(*) FROM evidence e LEFT JOIN source_candidate_map s USING(stable_source_row_id_v1) WHERE e.evidence_scope='SOURCE_ROW' AND (s.stable_source_row_id_v1 IS NULL OR NOT (e.stage06_exact_candidate_id IS NOT DISTINCT FROM s.stage06_standard_exact_candidate_id OR e.stage06_exact_candidate_id IS NOT DISTINCT FROM s.stage06_native_exact_candidate_id))",
        "EVIDENCE_SOURCE_CANDIDATE_FK_INVALID",
    )
    c.require(
        scalar_count(db, "SELECT count(*) FROM candidate_evidence")
        == counts["candidate_evidence"],
        "INPUT_CANDIDATE_COUNT_MISMATCH",
    )
    c.require(
        scalar_count(db, "SELECT count(*) FROM source_candidate_map")
        == counts["source_candidate_map"],
        "INPUT_SOURCE_COUNT_MISMATCH",
    )
    c.require(
        scalar_count(db, "SELECT count(*) FROM stage08_occurrence")
        == counts["representation_occurrence_v1"],
        "INPUT_OCCURRENCE_COUNT_MISMATCH",
    )
    c.require(
        scalar_count(db, "SELECT count(*) FROM parser_component_evidence")
        == counts.get("parser_component_evidence", 0),
        "INPUT_COMPONENT_COUNT_MISMATCH",
    )
    _zero(
        db,
        "SELECT count(*) FROM (SELECT evidence_id FROM evidence GROUP BY evidence_id HAVING count(*)<>1)",
        "EVIDENCE_ID_COLLISION",
    )
    _zero(
        db,
        "SELECT count(*) FROM (SELECT match_set_id,member_ordinal FROM members GROUP BY ALL HAVING count(*)<>1)",
        "MEMBER_ID_COLLISION",
    )
    _zero(
        db,
        "SELECT count(*) FROM evidence WHERE reference_slot='GEONAMES_POSTAL' AND result_state='CONTRADICTED'",
        "GEONAMES_NEGATIVE_AUTHORITY_PROHIBITED",
    )
    _zero(
        db,
        "SELECT count(*) FROM evidence e JOIN capabilities c USING(capability_id) WHERE e.result_state='CONTRADICTED' AND (NOT c.enabled OR NOT c.negative_authority)",
        "UNAUTHORIZED_CONTRADICTION",
    )
    _zero(
        db,
        "SELECT count(*) FROM evidence e JOIN capabilities r USING(capability_id) JOIN candidate_evidence c USING(stage06_exact_candidate_id) WHERE r.country_scope<>CASE WHEN e.question_catalog_id IN ('Q01','Q14') THEN 'GLOBAL' WHEN c.stage07_country_provenance_status='COUNTRY_UNANIMOUS_VALID' THEN upper(c.stage07_trusted_country_iso_code) ELSE 'UNRESOLVED' END",
        "CAPABILITY_COUNTRY_SCOPE_MISMATCH",
    )
    _zero(
        db,
        "SELECT count(*) FROM members m ANTI JOIN evidence e USING(match_set_id)",
        "ORPHAN_MATCH_SET",
    )
    _zero(
        db,
        "WITH x AS (SELECT match_set_id,count(*) n,min(member_ordinal) lo,max(member_ordinal) hi FROM members GROUP BY match_set_id) SELECT count(*) FROM evidence e LEFT JOIN x USING(match_set_id) WHERE e.witness_count>1 AND (x.n IS NULL OR x.n<>e.witness_count OR x.lo<>0 OR x.hi<>x.n-1)",
        "MATCH_SET_TOTALITY_INVALID",
    )
    _zero(
        db,
        "SELECT count(*) FROM (SELECT match_set_id FROM evidence WHERE match_set_id IS NOT NULL GROUP BY match_set_id HAVING count(DISTINCT lookup_identity)<>1)",
        "MATCH_SET_LOOKUP_CROSS_WIRING",
    )
    # Inline and shared witnesses are validated once at their actual grain.
    db.execute(
        "CREATE TEMP VIEW witness_bindings AS SELECT DISTINCT reference_version_id,reference_asset_id,question_catalog_id,result_state,single_witness witness FROM evidence WHERE witness_count=1 UNION ALL SELECT DISTINCT e.reference_version_id,e.reference_asset_id,e.question_catalog_id,e.result_state,m.witness FROM (SELECT DISTINCT reference_version_id,reference_asset_id,question_catalog_id,result_state,match_set_id FROM evidence WHERE witness_count>1) e JOIN members m USING(match_set_id)"
    )
    _zero(
        db,
        "SELECT count(*) FROM witness_bindings w LEFT JOIN reference_objects o ON w.witness.reference_object_id=o.reference_object_id WHERE o.reference_object_id IS NULL OR o.reference_version_id<>w.reference_version_id OR o.asset_id<>w.reference_asset_id",
        "WITNESS_OBJECT_ASSET_FK_INVALID",
    )
    _zero(
        db,
        "SELECT count(*) FROM witness_bindings WHERE len(witness.fields)=0 OR len(witness.fields)>16 OR witness.witness_role<>CASE result_state WHEN 'SUPPORTED' THEN 'SUPPORT' WHEN 'CONTRADICTED' THEN 'CONTRADICTION' ELSE 'CONFLICTING_REFERENCE' END",
        "WITNESS_ROLE_OR_BOUND_INVALID",
    )
    db.execute(
        "CREATE TEMP VIEW witness_fields AS SELECT w.reference_version_id,w.reference_asset_id,u.f FROM witness_bindings w,unnest(w.witness.fields) u(f)"
    )
    _zero(
        db,
        "SELECT count(*) FROM witness_fields w LEFT JOIN reference_objects o ON w.f.reference_object_id=o.reference_object_id WHERE o.reference_object_id IS NULL OR o.reference_version_id<>w.reference_version_id OR o.asset_id<>w.reference_asset_id OR NOT list_contains(list_transform(o.fields,x -> struct_pack(field_name:=x.field_name,ordinal:=x.ordinal)),struct_pack(field_name:=w.f.field_name,ordinal:=w.f.ordinal))",
        "WITNESS_FIELD_FK_INVALID",
    )
    db.execute(
        "CREATE TEMP VIEW argument_bindings AS SELECT e.stage06_exact_candidate_id,e.stable_source_row_id_v1,e.evidence_scope,e.question_catalog_id,u.a FROM evidence e,unnest(e.arguments) u(a)"
    )
    _zero(
        db,
        "SELECT count(*) FROM argument_bindings a LEFT JOIN parser_component_evidence p ON a.stage06_exact_candidate_id=p.stage06_exact_candidate_id AND a.a.component_ordinal=p.stage08_component_ordinal WHERE a.a.origin_relation='STAGE08_COMPONENT' AND (p.stage06_exact_candidate_id IS NULL OR a.evidence_scope<>'PARSER_CANDIDATE' OR a.a.origin_field<>'stage08_raw_libpostal_value' OR a.a.observed_role_count<>1 OR a.a.origin_semantic_class<>'PARSER_EVIDENCE')",
        "COMPONENT_ARGUMENT_POINTER_INVALID",
    )
    _zero(
        db,
        "SELECT count(*) FROM argument_bindings WHERE a.origin_relation='STAGE08_SOURCE_MAP' AND (evidence_scope<>'SOURCE_ROW' OR a.component_ordinal IS NOT NULL OR a.observed_role_count<>1 OR a.origin_semantic_class<>'UPSTREAM_DERIVED_REPRESENTATION')",
        "SOURCE_ARGUMENT_POINTER_INVALID",
    )
    _zero(
        db,
        "SELECT count(*) FROM argument_bindings WHERE a.origin_relation='STAGE08_CANDIDATE' AND (a.origin_field<>'stage07_trusted_country_iso_code' OR a.component_ordinal IS NOT NULL OR a.observed_role_count<>1 OR a.origin_semantic_class<>'TRUSTED_SOURCE_CONTEXT')",
        "CONTEXT_ARGUMENT_POINTER_INVALID",
    )
    # Verify the complete multi-witness hash, not merely member row counts.
    db.execute(
        "CREATE TEMP VIEW match_set_bindings AS SELECT DISTINCT match_set_id,lookup_identity,witness_count FROM evidence WHERE witness_count>1"
    )
    current = None
    digest = None
    previous_witness = None
    seen = 0
    expected_count = 0
    for item in io.sorted_rows(
        db,
        "SELECT b.*,m.member_ordinal,m.witness FROM match_set_bindings b JOIN members m USING(match_set_id) ORDER BY match_set_id,member_ordinal",
    ):
        if current != item["match_set_id"]:
            if current is not None:
                c.require(
                    digest is not None
                    and digest.digest() == current
                    and seen == expected_count,
                    "MATCH_SET_IDENTITY_MISMATCH",
                )
            current = item["match_set_id"]
            expected_count = item["witness_count"]
            digest = postal._match_hasher(item["lookup_identity"], expected_count)
            seen = 0
            previous_witness = None
        encoded = c.framed(c.witness_tuple(item["witness"]))
        c.require(
            previous_witness is None or previous_witness < encoded,
            "MATCH_MEMBERS_NOT_CANONICAL_OR_DUPLICATE",
        )
        c.require(item["member_ordinal"] == seen, "MATCH_MEMBER_ORDINAL_GAP")
        assert digest is not None
        digest.update(encoded)
        previous_witness = encoded
        seen += 1
    if current is not None:
        c.require(
            digest is not None
            and digest.digest() == current
            and seen == expected_count,
            "MATCH_SET_IDENTITY_MISMATCH",
        )
    # Full evidence IDs, ordered pointers and normalized digests are recomputed
    # by the scheduling replay certificate; scalar safety is also independent.
    for row in io.parquet_rows(evidence_paths):
        capability = view.capabilities.get(row["capability_id"])
        c.validate_evidence_semantics(row, capability)
        catalog = c.QUESTIONS.get(row["question_catalog_id"])
        c.require(catalog is not None, "QUESTION_CATALOG_ID_INVALID")
        assert catalog is not None
        c.require(
            tuple(a["role"] for a in row["arguments"]) == catalog.roles
            and row["claim_scope"] == catalog.claim_scope
            and row["reference_slot"] in catalog.references,
            "QUESTION_ROLE_OR_CLAIM_SCOPE_MISMATCH",
        )
        if row["reference_slot"] != "NONE":
            c.require(
                row["reference_asset_id"]
                == view.asset_id(row["reference_slot"], row["question_catalog_id"]),
                "EVIDENCE_SCIENTIFIC_ASSET_INVALID",
            )
            assert capability is not None
            c.require(
                capability["question_catalog_id"] == row["question_catalog_id"]
                and capability["scope_locator"] == "COUNTRY_MATRIX",
                "EVIDENCE_MATRIX_CAPABILITY_INVALID",
            )
        rule = view.capabilities.get(row["rule_capability_id"])
        if row["rule_capability_id"] is not None:
            c.require(
                rule is not None
                and rule["enabled"]
                and rule["reference_version_id"] == row["reference_version_id"]
                and rule["question_catalog_id"] == row["question_catalog_id"]
                and rule["scope_locator"] != "COUNTRY_MATRIX",
                "RULE_CAPABILITY_BINDING_INVALID",
            )
            c.require(
                rule is not None
                and capability is not None
                and rule["country_scope"] == capability["country_scope"],
                "RULE_COUNTRY_SCOPE_MISMATCH",
            )
            if row["result_state"] == "CONTRADICTED":
                assert rule is not None
                c.require(
                    rule["negative_authority"], "RULE_NEGATIVE_AUTHORITY_REQUIRED"
                )
        if row["question_catalog_id"] in ("Q03", "Q04", "Q08", "Q15") and row[
            "result_state"
        ] in ("SUPPORTED", "CONTRADICTED"):
            c.require(rule is not None, "PERFORMED_RULE_CAPABILITY_REQUIRED")
        origins = tuple(
            (
                a["origin_relation"],
                a["origin_field"],
                a["component_ordinal"],
                a["observed_role_count"],
            )
            for a in row["arguments"]
        )
        question_id = c.identity(
            "QUESTION",
            (
                c.catalog_fingerprint(),
                stage08_logical,
                row["stage06_exact_candidate_id"],
                row["evidence_scope"],
                row["stable_source_row_id_v1"],
                row["question_catalog_id"],
                row["interpretation"],
                row["claim_scope"],
                origins,
            ),
        )
        c.require(
            row["evidence_id"]
            == c.identity(
                "EVIDENCE",
                (
                    profile,
                    question_id,
                    row["reference_slot"],
                    row["reference_version_id"],
                    row["capability_id"],
                    row["rule_capability_id"],
                ),
            ),
            "EVIDENCE_IDENTITY_INVALID",
        )
        for argument in row["arguments"]:
            c.require(
                argument["normalization_id"] in c.NORMALIZATIONS,
                "ARGUMENT_NORMALIZATION_INVALID",
            )
            c.require(
                argument["origin_relation"]
                in (
                    "MISSING_OR_AMBIGUOUS",
                    "STAGE08_CANDIDATE",
                    "STAGE08_SOURCE_MAP",
                    "STAGE08_COMPONENT",
                ),
                "ARGUMENT_ORIGIN_INVALID",
            )
            if argument["origin_relation"] == "STAGE08_SOURCE_MAP":
                c.require(
                    argument["origin_field"] == c.SOURCE_FIELDS.get(argument["role"]),
                    "SOURCE_FIELD_ROLE_POINTER_MISMATCH",
                )
            if argument["origin_relation"] == "MISSING_OR_AMBIGUOUS":
                c.require(
                    argument["observed_role_count"] != 1
                    and all(
                        argument[k] is None
                        for k in (
                            "origin_field",
                            "component_ordinal",
                            "normalized_value_sha256",
                        )
                    )
                    and argument["normalization_id"] == c.NO_NORM,
                    "MISSING_ARGUMENT_POINTER_INVALID",
                )
    return {
        "candidate_source_occurrence_totality": "PASS",
        "reference_capability_authority": "PASS",
        "evidence_identity_and_state": "PASS",
        "witness_asset_field_bindings": "PASS",
        "complete_match_member_integrity": "PASS",
        "geonames_no_contradictions": "PASS",
    }


def compare_replay(
    expected: Sequence[Mapping[str, Any]], actual: Sequence[Mapping[str, Any]]
) -> None:
    left = {
        r["name"]: (r["row_count"], r["schema_sha256"], r["logical_sha256"])
        for r in expected
    }
    right = {
        r["name"]: (r["row_count"], r["schema_sha256"], r["logical_sha256"])
        for r in actual
    }
    c.require(left == right, "FULL_SCHEDULING_NORMALIZATION_REFERENCE_REPLAY_MISMATCH")
