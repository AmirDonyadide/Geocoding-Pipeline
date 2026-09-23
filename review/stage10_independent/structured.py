"""Independent, review-only Stage 10 country and structured-field oracle.

The caller alone opens/guards the manifest-bound input artifacts. This module
only queries its supplied DuckDB connection. No generator, Stage 10 evaluator,
reference lookup, external access, source mutation, or row-level output occurs.
All derived relations have reviewer-owned names. Witness work is bulk SQL at
the source/candidate grain, not a scan of public references per occurrence.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
from typing import Any, Callable
import pyarrow as pa
from common import rows

from safe_geocoding_pipeline.preprocessing.stages.s09_reference_contract import (
    normalize,
)


ISO = "ISO_CODES"
LIA = "LIBADDRESSINPUT_METADATA"
GN = "GEONAMES_POSTAL"
ISO_N = "ISO_CODE_ASCII_UPPER_V1"
NAME_N = "NAME_NFC_LOWER_U16_V1"
FORM_N = "POSTCODE_FORM_ASCII_UPPER_V1"
EXACT_N = "POSTCODE_EXACT_V1"
SEP_N = "POSTCODE_SEPARATORS_V1"
NO_N = "NOT_APPLIED_V1"
ALIASES = {"EXPLICIT_KEY", "NATIVE_ALIAS", "LATIN_ALIAS"}

# Transcribed from accepted S9 scheduling contract, deliberately independent of
# source_questions()/CATALOG and every candidate Stage 10 policy helper.
SCHEDULE = (
    ("Q01", ISO, "COUNTRY_CODE", "COUNTRY_CONTEXT", "COUNTRY_CODE"),
    ("Q02", ISO, "TRUSTED_COUNTRY ADMIN", "COUNTRY_CONTEXT", "FULL_ADMIN_CODE"),
    ("Q03", LIA, "TRUSTED_COUNTRY", "FORMAT", "METADATA"),
    ("Q04", LIA, "TRUSTED_COUNTRY POSTCODE", "POSTCODE_PATTERN", "FULL_POSTCODE"),
    ("Q05", GN, "TRUSTED_COUNTRY POSTCODE", "POSTCODE_EXISTENCE", "FULL_POSTCODE"),
    (
        "Q06",
        GN,
        "TRUSTED_COUNTRY POSTCODE LOCALITY",
        "POSTCODE_LOCALITY",
        "FULL_POSTCODE",
    ),
    ("Q07", GN, "TRUSTED_COUNTRY POSTCODE ADMIN", "POSTCODE_ADMIN", "FULL_POSTCODE"),
    (
        "Q08",
        LIA,
        "TRUSTED_COUNTRY POSTCODE ADMIN",
        "POSTCODE_PREFIX_BY_ADMIN",
        "POSTCODE_PREFIX_RULE",
    ),
    ("Q09", LIA, "TRUSTED_COUNTRY LOCALITY", "LOCALITY", "REFERENCE_NAME"),
    ("Q09", GN, "TRUSTED_COUNTRY LOCALITY", "LOCALITY", "REFERENCE_NAME"),
    ("Q10", ISO, "TRUSTED_COUNTRY ADMIN", "ADMIN", "REFERENCE_NAME"),
    ("Q10", LIA, "TRUSTED_COUNTRY ADMIN", "ADMIN_ENUMERATION", "REFERENCE_NAME"),
    ("Q10", GN, "TRUSTED_COUNTRY ADMIN", "ADMIN", "REFERENCE_NAME"),
    ("Q11", LIA, "TRUSTED_COUNTRY LOCALITY ADMIN", "LOCALITY_ADMIN", "REFERENCE_NAME"),
    ("Q11", GN, "TRUSTED_COUNTRY LOCALITY ADMIN", "LOCALITY_ADMIN", "REFERENCE_NAME"),
    ("Q12", "NONE", "TRUSTED_COUNTRY STREET", "STREET", "UNSUPPORTED"),
    (
        "Q13",
        "NONE",
        "TRUSTED_COUNTRY STREET HOUSE_NUMBER",
        "HOUSE_NUMBER",
        "UNSUPPORTED",
    ),
    ("Q15", LIA, "TRUSTED_COUNTRY", "REQUIRED_FIELDS", "METADATA"),
)
ROLE_FIELDS = {
    "COUNTRY_CODE": "stage03_clean_country_iso_code",
    "POSTCODE": "stage03_clean_postcode",
    "LOCALITY": "stage03_clean_city",
    "ADMIN": "stage03_clean_region_in_country",
    "TRUSTED_COUNTRY": "stage07_trusted_country_iso_code",
}
FIELDS = ("address", "postalcode", "locality", "region", "country", "boundary_country")
ARG_TYPE = "STRUCT(role VARCHAR, origin_relation VARCHAR, origin_field VARCHAR, component_ordinal UBIGINT, observed_role_count UBIGINT, origin_semantic_class VARCHAR, normalization_id VARCHAR, normalized_value_sha256 BLOB, value_granularity VARCHAR)[]"


def _claim(question: str) -> str:
    if question in {"Q01", "Q02"}:
        return "CODE_COUNTRY_RELATION"
    if question in {"Q03", "Q04", "Q08", "Q15"}:
        return "FROZEN_METADATA_RULE"
    return "REFERENCE_SNAPSHOT"


def _upper(value: str) -> str:
    return value.translate(
        str.maketrans("abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    )


def _normalized_digest(method: str, value: str) -> bytes:
    """Independent implementation of accepted S9 typed NORMALIZED_VALUE ID."""

    def text(value: str) -> bytes:
        raw = value.encode("utf-8")
        return b"\x02" + struct.pack(">Q", len(raw)) + raw

    return hashlib.sha256(
        struct.pack(">Q", 4)
        + text("SAFE_STAGE09")
        + text("V1")
        + text("NORMALIZED_VALUE")
        + b"\x05"
        + struct.pack(">Q", 2)
        + text(method)
        + text(value)
    ).digest()


def expected_arguments(
    question: str,
    reference: str,
    source_country: str | None,
    postcode: str | None,
    locality: str | None,
    admin: str | None,
    trusted: str | None,
    status: str,
) -> list[dict[str, Any]]:
    roles = next(row[2].split() for row in SCHEDULE if row[:2] == (question, reference))
    values = dict(
        zip(
            ("COUNTRY_CODE", "POSTCODE", "LOCALITY", "ADMIN", "TRUSTED_COUNTRY"),
            (source_country, postcode, locality, admin, trusted),
        )
    )
    country = (
        _upper(trusted)
        if status == "COUNTRY_UNANIMOUS_VALID" and trusted is not None
        else "UNRESOLVED"
    )
    result = []
    for role in roles:
        value = values.get(role)
        if value is None:
            method, origin, field, semantic, count = (
                NO_N,
                "MISSING_OR_AMBIGUOUS",
                None,
                "MECHANICAL_INDEX",
                0,
            )
        else:
            origin = (
                "STAGE08_CANDIDATE"
                if role == "TRUSTED_COUNTRY"
                else "STAGE08_SOURCE_MAP"
            )
            semantic = (
                "TRUSTED_SOURCE_CONTEXT"
                if role == "TRUSTED_COUNTRY"
                else "UPSTREAM_DERIVED_REPRESENTATION"
            )
            field, count = ROLE_FIELDS[role], 1
            if role in {"COUNTRY_CODE", "TRUSTED_COUNTRY"}:
                method = ISO_N
            elif role == "ADMIN" and (
                question == "Q02"
                or (
                    question == "Q10"
                    and reference == ISO
                    and re.fullmatch(r"[A-Z]{2}-[A-Z0-9]+", _upper(value))
                )
            ):
                method = ISO_N
            elif role == "POSTCODE":
                method = (
                    FORM_N
                    if question in {"Q04", "Q08"}
                    else SEP_N
                    if country in {"JP", "PL", "PT", "BR", "SE", "CZ", "SK"}
                    else EXACT_N
                )
            else:
                method = NAME_N
        granularity = (
            "COUNTRY_CODE"
            if role in {"COUNTRY_CODE", "TRUSTED_COUNTRY"}
            else "FULL_ADMIN_CODE"
            if method == ISO_N
            else "FULL_POSTCODE"
            if role == "POSTCODE"
            else "UNSUPPORTED"
            if method == NO_N
            else "REFERENCE_NAME"
        )
        result.append(
            {
                "role": role,
                "origin_relation": origin,
                "origin_field": field,
                "component_ordinal": None,
                "observed_role_count": count,
                "origin_semantic_class": semantic,
                "normalization_id": method,
                "normalized_value_sha256": None
                if method == NO_N
                else _normalized_digest(
                    method, normalize(method, value or "", country)
                ),
                "value_granularity": granularity,
            }
        )
    return result


def _equal(
    method: str | None, left: str | None, right: str | None, country: str | None
) -> bool:
    if left is None or right is None or method in {None, NO_N}:
        return False
    return normalize(method, left, country or "UNRESOLVED") == normalize(
        method, right, country or "UNRESOLVED"
    )


def _negative_certificate(payload: str) -> bool:
    """Check the precise already-recorded conflict certificate; never look up.

    Root and all selected fields have already been joined by exact object/field
    locator. Rechecking the frozen regex against its source argument is a
    certificate check, not a new reference search or new evidence row.
    """
    p = json.loads(payload)
    root, selected = p["root"], p["selected"]
    country, question = p["country"], p["question"]
    if not root or p["witness_role"] != "CONTRADICTION" or p["witness_count"] != 1:
        return False
    if (
        root["country_code"] != country
        or root["reference_version_id"] != p["version"]
        or root["asset_id"] != p["asset"]
    ):
        return False
    if not selected or any(
        not s["field"]
        or s["object_country"] != country
        or s["object_version"] != p["version"]
        or s["object_asset"] != p["asset"]
        for s in selected
    ):
        return False
    value = normalize(FORM_N, p["postcode"], country)
    if question == "Q04":
        s = selected[0]
        return (
            root["object_kind"] == "FORMAT_COUNTRY"
            and root["source_locator"] == country
            and p["rule_scope"] == country + "/zip"
            and len(selected) == 1
            and s["object_id"] == root["reference_object_id"]
            and s["field"]["field_name"] == "zip"
            and s["field"]["source_field_locator"] == country + "/zip"
            and bool(s["field"]["original_value"])
            and re.fullmatch(s["field"]["original_value"], value, re.ASCII) is None
        )
    if question != "Q08" or root["object_kind"] != "FORMAT_ADMIN":
        return False
    prefixes = [
        f
        for f in root["fields"]
        if f["field_name"] in {"zip", "sub_zips"} and f["original_value"]
    ]
    if not prefixes or any(
        f["field_name"] in {"xzip", "sub_xzips"} and f["original_value"]
        for f in root["fields"]
    ):
        return False
    scope = "PREFIX_BUNDLE:" + json.dumps(
        [
            root["source_locator"],
            country + "/zip",
            *sorted(f["source_field_locator"] for f in prefixes),
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    roots = [
        s
        for s in selected
        if s["object_kind"] == "FORMAT_COUNTRY"
        and s["object_locator"] == country
        and s["field"]["field_name"] == "zip"
        and s["field"]["source_field_locator"] == country + "/zip"
        and s["field"]["original_value"]
    ]
    names = [
        s["field"]
        for s in selected
        if s["object_id"] == root["reference_object_id"]
        and s["field"]["alias_role"] in ALIASES
    ]
    selected_keys = [
        (
            s["object_id"],
            s["field"]["field_name"],
            s["field"]["ordinal"],
            s["field"]["source_field_locator"],
        )
        for s in selected
    ]
    return (
        p["rule_scope"] == scope
        and len(roots) == 1
        and all(
            selected_keys.count(
                (
                    root["reference_object_id"],
                    f["field_name"],
                    f["ordinal"],
                    f["source_field_locator"],
                )
            )
            == 1
            for f in prefixes
        )
        and any(_equal(NAME_N, f["original_value"], p["admin"], country) for f in names)
        and re.fullmatch(roots[0]["field"]["original_value"], value, re.ASCII)
        is not None
        and all(
            re.match("(?:" + f["original_value"] + ")", value, re.ASCII) is None
            for f in prefixes
        )
    )


def _map_rows(db, query, target, schema, transform):
    """No Python UDF dependency; bounded Arrow transport into reviewer tables."""
    db.register("review_struct_batch", pa.Table.from_pylist([], schema=schema))
    db.execute("CREATE TABLE " + target + " AS SELECT * FROM review_struct_batch")
    db.unregister("review_struct_batch")
    buffer = []

    def flush():
        if buffer:
            db.register(
                "review_struct_batch", pa.Table.from_pylist(buffer, schema=schema)
            )
            db.execute("INSERT INTO " + target + " SELECT * FROM review_struct_batch")
            db.unregister("review_struct_batch")
            buffer.clear()

    for row in rows(db, query):
        buffer.append(transform(row))
        if len(buffer) == 256:
            flush()
    flush()


def run(db: Any, check: Callable[[str, bool], Any]) -> dict[str, Any]:
    """Check every context, returning only closed-name aggregate counters."""
    result: dict[str, Any] = {}

    def count(name: str, sql: str) -> int:
        value = int(db.execute(sql).fetchone()[0])
        result[name] = value
        return value

    def zero(name: str, sql: str) -> None:
        check(name, count(name, sql) == 0)

    db.execute(
        "CREATE TABLE review_struct_schedule(question VARCHAR, reference VARCHAR, roles VARCHAR[], capability VARCHAR, granularity VARCHAR, claim VARCHAR)"
    )
    db.executemany(
        "INSERT INTO review_struct_schedule VALUES (?, ?, ?, ?, ?, ?)",
        [
            (q, r, roles.split(), cap, gran, _claim(q))
            for q, r, roles, cap, gran in SCHEDULE
        ],
    )
    db.execute("""
        CREATE TABLE review_struct_pairs AS
        SELECT p.*, s.stage03_clean_country_iso_code source_country,
               s.stage03_clean_postcode postcode, s.stage03_clean_city locality,
               s.stage03_clean_region_in_country AS admin_value,
               c.stage07_trusted_country_iso_code trusted_country,
               c.stage07_country_provenance_status country_status
        FROM (SELECT DISTINCT stable_source_row_id_v1, stage06_exact_candidate_id FROM contexts) p
        JOIN source_candidate_map s USING(stable_source_row_id_v1)
        JOIN candidate_evidence c USING(stage06_exact_candidate_id)
    """)
    count("source_candidate_pairs", "SELECT count(*) FROM review_struct_pairs")
    zero(
        "source_schedule_missing_or_duplicate",
        """
        SELECT count(*) FROM (
          SELECT p.stable_source_row_id_v1, p.stage06_exact_candidate_id, q.question, q.reference, count(e.evidence_id) n
          FROM review_struct_pairs p CROSS JOIN review_struct_schedule q
          LEFT JOIN candidate_reference_evidence e ON e.evidence_scope='SOURCE_ROW'
            AND e.stable_source_row_id_v1=p.stable_source_row_id_v1
            AND e.stage06_exact_candidate_id=p.stage06_exact_candidate_id
            AND e.question_catalog_id=q.question AND e.reference_slot=q.reference
          GROUP BY ALL HAVING n<>1)
    """,
    )
    zero(
        "source_schedule_unexpected",
        """
        SELECT count(*) FROM candidate_reference_evidence e
        JOIN review_struct_pairs p USING(stable_source_row_id_v1, stage06_exact_candidate_id)
        LEFT JOIN review_struct_schedule q ON e.question_catalog_id=q.question AND e.reference_slot=q.reference
        WHERE e.evidence_scope='SOURCE_ROW' AND q.question IS NULL
    """,
    )
    _map_rows(
        db,
        """SELECT e.evidence_id,e.arguments,e.claim_scope,e.interpretation,q.question,q.reference,q.claim,
          p.source_country,p.postcode,p.locality,p.admin_value,p.trusted_country,p.country_status
        FROM candidate_reference_evidence e
        JOIN review_struct_pairs p USING(stable_source_row_id_v1,stage06_exact_candidate_id)
        JOIN review_struct_schedule q ON e.question_catalog_id=q.question AND e.reference_slot=q.reference
        WHERE e.evidence_scope='SOURCE_ROW'""",
        "review_struct_arg_checks",
        pa.schema([("evidence_id", pa.binary()), ("valid", pa.bool_())]),
        lambda r: {
            "evidence_id": r["evidence_id"],
            "valid": r["arguments"]
            == expected_arguments(
                r["question"],
                r["reference"],
                r["source_country"],
                r["postcode"],
                r["locality"],
                r["admin_value"],
                r["trusted_country"],
                r["country_status"],
            )
            and r["claim_scope"] == r["claim"]
            and r["interpretation"]
            == (
                "CONTEXT_METADATA"
                if r["question"] in ("Q03", "Q15")
                else "SOURCE_FIELD_ROLE"
            ),
        },
    )
    zero(
        "source_argument_lineage_mismatches",
        "SELECT count(*) FROM review_struct_arg_checks WHERE valid IS NOT TRUE",
    )
    zero(
        "geonames_contradicted_source_evidence",
        """
        SELECT count(*) FROM candidate_reference_evidence e
        JOIN review_struct_pairs p USING(stable_source_row_id_v1, stage06_exact_candidate_id)
        WHERE e.evidence_scope='SOURCE_ROW' AND e.reference_slot='GEONAMES_POSTAL' AND e.result_state='CONTRADICTED'
    """,
    )
    db.execute("""
        CREATE TABLE review_struct_evidence AS
        SELECT e.*, p.source_country,p.postcode,p.locality,p.admin_value,p.trusted_country,p.country_status,
          a.valid args_valid, cap AS matrix_capability, rule AS rule_capability,
          coalesce(a.valid AND reg.reference_id=e.reference_slot
            AND cap.reference_version_id=e.reference_version_id
            AND cap.question_catalog_id=e.question_catalog_id
            AND cap.scope_locator='COUNTRY_MATRIX' AND cap.claim_scope=q.claim
            AND cap.granularity=q.granularity AND cap.capability=q.capability
            AND cap.required_roles=q.roles AND cap.normalization_id='stage09_lookup_normalization_v1'
            AND cap.enabled, false) matrix_valid,
          coalesce(rule.reference_version_id=e.reference_version_id
            AND rule.question_catalog_id=e.question_catalog_id AND rule.enabled
            AND rule.claim_scope=q.claim AND rule.granularity=q.granularity
            AND rule.capability=q.capability AND rule.required_roles=q.roles
            AND rule.normalization_id='stage09_lookup_normalization_v1',false) rule_valid
        FROM candidate_reference_evidence e
        JOIN review_struct_pairs p USING(stable_source_row_id_v1,stage06_exact_candidate_id)
        JOIN review_struct_arg_checks a USING(evidence_id)
        JOIN review_struct_schedule q ON e.question_catalog_id=q.question AND e.reference_slot=q.reference
        LEFT JOIN reference_capability cap USING(capability_id)
        LEFT JOIN reference_capability rule ON rule.capability_id=e.rule_capability_id
        LEFT JOIN reference_registry reg ON reg.reference_version_id=e.reference_version_id
        WHERE e.evidence_scope='SOURCE_ROW' AND e.question_catalog_id IN ('Q01','Q04','Q05','Q06','Q08','Q09')
    """)
    # The source/candidate evidence grain is retained. Two role occurrences do
    # not duplicate costly witness expansion and cannot contaminate other rows.
    db.execute("""
        CREATE TABLE review_struct_witness AS
        SELECT e.evidence_id, 0::UBIGINT witness_ordinal, e.single_witness witness
        FROM review_struct_evidence e
        WHERE e.single_witness IS NOT NULL AND e.result_state IN ('SUPPORTED','CONTRADICTED')
        UNION ALL
        SELECT e.evidence_id,m.member_ordinal,m.witness
        FROM review_struct_evidence e JOIN reference_match_member m USING(match_set_id)
        WHERE e.match_set_id IS NOT NULL AND e.result_state IN ('SUPPORTED','CONTRADICTED')
    """)
    db.execute("""
        CREATE TABLE review_struct_pointer_raw AS
        SELECT row_number() OVER () pointer_id,w.evidence_id,w.witness_ordinal,w.witness.reference_object_id root_id,
          w.witness.witness_role witness_role, p.reference_object_id object_id,
          o.country_code object_country,o.reference_version_id object_version,o.asset_id object_asset,
          o.object_kind object_kind,o.source_locator object_locator,
          list_extract(list_filter(o.fields,x -> x.field_name=p.field_name AND x.ordinal=p.ordinal),1) field,
          len(list_filter(o.fields,x -> x.field_name=p.field_name AND x.ordinal=p.ordinal)) field_matches
        FROM review_struct_witness w CROSS JOIN unnest(w.witness.fields) t(p)
        LEFT JOIN reference_object o ON o.reference_object_id=p.reference_object_id
    """)
    _map_rows(
        db,
        """SELECT p.pointer_id,p.field.original_value AS field_value,e.locality,e.postcode,e.source_country,
          list_extract(list_filter(e.arguments,a -> a.role='POSTCODE'),1).normalization_id postcode_norm
          FROM review_struct_pointer_raw p JOIN review_struct_evidence e USING(evidence_id)""",
        "review_struct_pointer_matches",
        pa.schema(
            [
                ("pointer_id", pa.int64()),
                ("iso_match", pa.bool_()),
                ("locality_match", pa.bool_()),
                ("postcode_match", pa.bool_()),
            ]
        ),
        lambda r: {
            "pointer_id": r["pointer_id"],
            "iso_match": _equal(ISO_N, r["field_value"], r["source_country"], None),
            "locality_match": _equal(NAME_N, r["field_value"], r["locality"], None),
            "postcode_match": _equal(
                r["postcode_norm"],
                r["field_value"],
                r["postcode"],
                _upper(r["source_country"] or ""),
            ),
        },
    )
    db.execute(
        "CREATE TABLE review_struct_pointer AS SELECT p.*,m.* EXCLUDE(pointer_id) FROM review_struct_pointer_raw p JOIN review_struct_pointer_matches m USING(pointer_id)"
    )
    zero(
        "relevant_witness_pointer_resolution_mismatches",
        "SELECT count(*) FROM review_struct_pointer WHERE field_matches IS DISTINCT FROM 1",
    )
    # Country recognition deliberately does not depend on the candidate-wide
    # trusted-country status or country_assessment, just this row's Q01 code.
    db.execute("""
        CREATE TABLE review_struct_country_pair AS
        SELECT p.stable_source_row_id_v1,p.stage06_exact_candidate_id,
          CASE WHEN bool_or(coalesce(e.result_state='SUPPORTED' AND e.matrix_valid
            AND e.matrix_capability.positive_authority AND e.matrix_capability.country_scope='GLOBAL'
            AND regexp_full_match(p.source_country,'[A-Za-z]{2}')
            AND w.witness.witness_role='SUPPORT' AND o.object_kind='ISO_COUNTRY'
            AND o.reference_version_id=e.reference_version_id AND o.asset_id=e.reference_asset_id
            AND o.country_code=upper(p.source_country)
            AND f.object_id=o.reference_object_id AND f.field.field_name='alpha_2'
            AND f.field_matches=1 AND f.iso_match,false))
          THEN upper(p.source_country) ELSE NULL END boundary_country
        FROM review_struct_pairs p LEFT JOIN review_struct_evidence e
          ON e.stable_source_row_id_v1=p.stable_source_row_id_v1
          AND e.stage06_exact_candidate_id=p.stage06_exact_candidate_id AND e.question_catalog_id='Q01'
        LEFT JOIN review_struct_witness w USING(evidence_id)
        LEFT JOIN reference_object o ON o.reference_object_id=w.witness.reference_object_id
        LEFT JOIN review_struct_pointer f ON f.evidence_id=w.evidence_id AND f.witness_ordinal=w.witness_ordinal
        GROUP BY p.stable_source_row_id_v1,p.stage06_exact_candidate_id,p.source_country
    """)
    db.execute("""
        CREATE TABLE review_country_context AS
        SELECT c.query_context_id,p.boundary_country FROM contexts c
        LEFT JOIN review_struct_country_pair p USING(stable_source_row_id_v1,stage06_exact_candidate_id)
    """)
    count(
        "country_available_contexts",
        "SELECT count(*) FROM review_country_context WHERE boundary_country IS NOT NULL",
    )
    count(
        "country_unavailable_contexts",
        "SELECT count(*) FROM review_country_context WHERE boundary_country IS NULL",
    )
    # One row per original witness: Q06's two matches MUST come from one postal
    # record and both pointers MUST target that witness's object.
    db.execute("""
        CREATE TABLE review_struct_positive_witness AS
        SELECT e.evidence_id,w.witness_ordinal,
          bool_or(f.object_id=o.reference_object_id AND f.field.field_name='place_name'
            AND f.locality_match) gn_locality,
          bool_or(f.object_id=o.reference_object_id AND f.field.field_name='postal_code'
            AND f.postcode_match) gn_postcode,
          bool_or(f.object_id=o.reference_object_id AND f.field.alias_role IN ('EXPLICIT_KEY','NATIVE_ALIAS','LATIN_ALIAS')
            AND f.locality_match) lia_locality,
          e.question_catalog_id,e.reference_slot,o.object_kind
        FROM review_struct_evidence e JOIN review_struct_country_pair c USING(stable_source_row_id_v1,stage06_exact_candidate_id)
        JOIN review_struct_witness w USING(evidence_id)
        JOIN reference_object o ON o.reference_object_id=w.witness.reference_object_id
        JOIN review_struct_pointer f ON f.evidence_id=w.evidence_id AND f.witness_ordinal=w.witness_ordinal
        WHERE e.question_catalog_id IN ('Q05','Q06','Q09') AND e.result_state='SUPPORTED'
          AND c.boundary_country IS NOT NULL AND e.matrix_valid AND e.matrix_capability.positive_authority
          AND e.matrix_capability.country_scope=c.boundary_country
          AND upper(e.trusted_country)=c.boundary_country
          AND w.witness.witness_role='SUPPORT' AND o.country_code=c.boundary_country
          AND o.reference_version_id=e.reference_version_id AND o.asset_id=e.reference_asset_id
          AND f.field_matches=1
        GROUP BY e.evidence_id,w.witness_ordinal,e.question_catalog_id,e.reference_slot,o.object_kind
    """)
    db.execute("""
        CREATE TABLE review_struct_positive AS
        SELECT evidence_id, bool_or(CASE
          WHEN reference_slot='GEONAMES_POSTAL' AND object_kind='POSTAL_ASSOCIATION'
            THEN CASE question_catalog_id WHEN 'Q09' THEN gn_locality WHEN 'Q05' THEN gn_postcode
                      WHEN 'Q06' THEN gn_locality AND gn_postcode ELSE false END
          WHEN reference_slot='LIBADDRESSINPUT_METADATA' AND object_kind='FORMAT_LOCALITY' AND question_catalog_id='Q09'
            THEN lia_locality ELSE false END) positive
        FROM review_struct_positive_witness GROUP BY evidence_id
    """)
    _map_rows(
        db,
        """SELECT e.evidence_id,
          coalesce(e.matrix_valid AND e.rule_valid AND e.matrix_capability.negative_authority
            AND e.rule_capability.negative_authority
            AND e.matrix_capability.country_scope=c.boundary_country
            AND e.rule_capability.country_scope=c.boundary_country
            AND upper(e.trusted_country)=c.boundary_country
            AND e.contradiction_type=CASE e.question_catalog_id WHEN 'Q04' THEN 'FORMAT_RULE_CONFLICT' ELSE 'PREFIX_RULE_CONFLICT' END
            ,false) gates, to_json(struct_pack(
              root:=o, selected:=f.selected, country:=c.boundary_country, question:=e.question_catalog_id,
              version:=e.reference_version_id, asset:=e.reference_asset_id, witness_role:=w.witness.witness_role,
              witness_count:=e.witness_count, rule_scope:=e.rule_capability.scope_locator,
              postcode:=e.postcode, "admin":=e.admin_value)) payload
        FROM review_struct_evidence e JOIN review_struct_country_pair c USING(stable_source_row_id_v1,stage06_exact_candidate_id)
        JOIN review_struct_witness w USING(evidence_id)
        JOIN reference_object o ON o.reference_object_id=w.witness.reference_object_id
        JOIN (SELECT evidence_id,witness_ordinal,list(struct_pack(object_id:=object_id,object_country:=object_country,
                object_version:=object_version,object_asset:=object_asset,object_kind:=object_kind,object_locator:=object_locator,field:=field)) selected
              FROM review_struct_pointer GROUP BY evidence_id,witness_ordinal) f
          ON f.evidence_id=w.evidence_id AND f.witness_ordinal=w.witness_ordinal
        WHERE e.question_catalog_id IN ('Q04','Q08') AND e.reference_slot='LIBADDRESSINPUT_METADATA'
          AND e.result_state='CONTRADICTED' AND c.boundary_country IS NOT NULL
    """,
        "review_struct_negative_witness",
        pa.schema([("evidence_id", pa.binary()), ("negative", pa.bool_())]),
        lambda r: {
            "evidence_id": r["evidence_id"],
            "negative": bool(r["gates"]) and _negative_certificate(r["payload"]),
        },
    )
    db.execute(
        "CREATE TABLE review_struct_negative AS SELECT evidence_id,bool_or(negative) negative FROM review_struct_negative_witness GROUP BY evidence_id"
    )
    # Country-incompatible valid evidence is inapplicable, not negative. A
    # supposedly applicable malformed certificate is reported independently.
    zero(
        "applicable_negative_certificate_mismatches",
        """
        SELECT count(*) FROM review_struct_evidence e
        JOIN review_struct_country_pair c USING(stable_source_row_id_v1,stage06_exact_candidate_id)
        LEFT JOIN review_struct_negative n USING(evidence_id)
        WHERE e.question_catalog_id IN ('Q04','Q08') AND e.result_state='CONTRADICTED'
          AND e.matrix_capability.country_scope=c.boundary_country
          AND e.matrix_capability.enabled AND e.matrix_capability.negative_authority
          AND e.rule_capability.enabled AND e.rule_capability.negative_authority
          AND n.negative IS NOT TRUE
    """,
    )
    db.execute("""
        CREATE TABLE review_struct_pair_flags AS
        SELECT p.*, c.boundary_country,
          coalesce(bool_or(e.question_catalog_id='Q09' AND a.positive),false) locality_positive,
          coalesce(bool_or(e.question_catalog_id='Q05' AND a.positive),false) postcode_positive,
          coalesce(bool_or(e.question_catalog_id='Q06' AND a.positive),false) pair_positive,
          coalesce(bool_or(e.question_catalog_id='Q04' AND n.negative),false) q04_negative,
          coalesce(bool_or(e.question_catalog_id='Q08' AND n.negative),false) q08_negative
        FROM review_struct_pairs p JOIN review_struct_country_pair c USING(stable_source_row_id_v1,stage06_exact_candidate_id)
        LEFT JOIN review_struct_evidence e USING(stable_source_row_id_v1,stage06_exact_candidate_id)
        LEFT JOIN review_struct_positive a USING(evidence_id)
        LEFT JOIN review_struct_negative n USING(evidence_id)
        GROUP BY ALL
    """)
    db.execute("""
        CREATE TABLE review_struct_policy AS
        WITH eligible AS (SELECT *,
          boundary_country IS NOT NULL AND coalesce(locality<>'',false) AND locality_positive locality_ok,
          boundary_country IS NOT NULL AND coalesce(postcode<>'',false) AND postcode_positive
            AND NOT(q04_negative OR q08_negative) AND (NOT(coalesce(locality<>'',false) AND locality_positive) OR pair_positive) postcode_ok
          FROM review_struct_pair_flags)
        SELECT c.query_context_id, c.stable_source_row_id_v1,c.stage06_exact_candidate_id,c.stage08_representation,
          e.boundary_country, CASE WHEN e.locality_ok THEN e.locality ELSE NULL END locality,
          CASE WHEN e.postcode_ok THEN e.postcode ELSE NULL END postalcode,
          CASE WHEN e.boundary_country IS NULL THEN 'COUNTRY_CONTEXT_UNAVAILABLE'
               WHEN e.locality_ok THEN NULL WHEN coalesce(e.locality,'')='' THEN 'SOURCE_FIELD_UNAVAILABLE'
               ELSE 'INSUFFICIENT_TRUSTED_STRUCTURED_EVIDENCE' END locality_reason,
          CASE WHEN e.boundary_country IS NULL THEN 'COUNTRY_CONTEXT_UNAVAILABLE'
               WHEN e.postcode_ok THEN NULL WHEN e.q04_negative OR e.q08_negative THEN 'CONTRADICTION_GATE'
               WHEN coalesce(e.postcode,'')='' THEN 'SOURCE_FIELD_UNAVAILABLE'
               ELSE 'INSUFFICIENT_TRUSTED_STRUCTURED_EVIDENCE' END postcode_reason,
          e.q04_negative,e.q08_negative,e.locality_positive,e.postcode_positive,e.pair_positive
        FROM contexts c JOIN eligible e USING(stable_source_row_id_v1,stage06_exact_candidate_id)
    """)
    count(
        "q4_expected_eligible",
        "SELECT count(*) FROM review_struct_policy WHERE locality IS NOT NULL OR postalcode IS NOT NULL",
    )
    count(
        "q4_expected_postcode_included",
        "SELECT count(*) FROM review_struct_policy WHERE postalcode IS NOT NULL",
    )
    count(
        "q4_expected_locality_included",
        "SELECT count(*) FROM review_struct_policy WHERE locality IS NOT NULL",
    )
    count(
        "q4_expected_postcode_contradiction_omissions",
        "SELECT count(*) FROM review_struct_policy WHERE postcode_reason='CONTRADICTION_GATE'",
    )
    count(
        "q4_q04_negative_contexts",
        "SELECT count(*) FROM review_struct_policy WHERE q04_negative",
    )
    count(
        "q4_q08_negative_contexts",
        "SELECT count(*) FROM review_struct_policy WHERE q08_negative",
    )
    count(
        "q4_same_record_pair_gate_omissions",
        "SELECT count(*) FROM review_struct_policy WHERE boundary_country IS NOT NULL AND locality IS NOT NULL AND postcode_positive AND NOT pair_positive AND NOT(q04_negative OR q08_negative)",
    )
    zero(
        "q4_family_state_mismatches",
        """
        SELECT count(*) FROM review_struct_policy p LEFT JOIN query_family_decision d
          ON d.query_context_id=p.query_context_id AND d.family='Q4'
        WHERE d.family_decision_id IS NULL OR d.eligibility_state IS DISTINCT FROM
          CASE WHEN p.locality IS NOT NULL OR p.postalcode IS NOT NULL THEN 'ELIGIBLE' ELSE 'INELIGIBLE' END
          OR d.membership_state IS DISTINCT FROM CASE WHEN p.locality IS NOT NULL OR p.postalcode IS NOT NULL THEN 'FIRST_MEMBER' ELSE 'NONE' END
          OR (d.hypothesis_id IS NOT NULL) IS DISTINCT FROM (p.locality IS NOT NULL OR p.postalcode IS NOT NULL)
          OR d.reason_codes IS DISTINCT FROM CASE WHEN p.boundary_country IS NULL THEN ['COUNTRY_CONTEXT_UNAVAILABLE']
               WHEN p.locality IS NULL AND p.postalcode IS NULL THEN ['INSUFFICIENT_TRUSTED_STRUCTURED_EVIDENCE'] ELSE [] END
          OR d.primary_reason IS DISTINCT FROM CASE WHEN p.boundary_country IS NULL THEN 'COUNTRY_CONTEXT_UNAVAILABLE'
               WHEN p.locality IS NULL AND p.postalcode IS NULL THEN 'INSUFFICIENT_TRUSTED_STRUCTURED_EVIDENCE' ELSE NULL END
    """,
    )
    zero(
        "q4_intent_content_mismatches",
        """
        SELECT count(*) FROM review_struct_policy p JOIN candidate_evidence c USING(stage06_exact_candidate_id)
        JOIN query_family_decision d ON d.query_context_id=p.query_context_id AND d.family='Q4'
        LEFT JOIN query_hypothesis h ON h.query_context_id=p.query_context_id AND h.hypothesis_id=d.hypothesis_id
        WHERE (p.locality IS NOT NULL OR p.postalcode IS NOT NULL) AND (
          h.hypothesis_id IS NULL OR h.intent.intent_version IS DISTINCT FROM 'stage10_query_intent_v1'
          OR h.intent.endpoint IS DISTINCT FROM '/v1/search/structured' OR h.intent.search_mode IS DISTINCT FROM 'STRUCTURED'
          OR h.intent.text IS NOT NULL OR h.intent.address IS DISTINCT FROM c.stage06_candidate_lower
          OR h.intent.locality IS DISTINCT FROM p.locality OR h.intent.postalcode IS DISTINCT FROM p.postalcode
          OR h.intent.region IS NOT NULL OR h.intent.country IS NOT NULL
          OR h.intent.boundary_country IS DISTINCT FROM p.boundary_country
          OR h.intent.retrieval_policy_slot IS DISTINCT FROM 'SAFE_PELIAS_COMMON_RETRIEVAL_V1')
    """,
    )
    # Frozen six-field order and all operative field-policy reasons. The separate
    # parser-exclusion contract check below is intentionally stricter than the
    # candidate's absent emission; it is not erased by these content checks.
    db.execute("CREATE TABLE review_struct_field_names(field VARCHAR, ordinal INTEGER)")
    db.executemany(
        "INSERT INTO review_struct_field_names VALUES (?,?)",
        [(f, i) for i, f in enumerate(FIELDS, 1)],
    )
    zero(
        "q4_field_disposition_and_operational_reason_mismatches",
        """
        SELECT count(*) FROM review_struct_policy p JOIN query_family_decision d
          ON d.query_context_id=p.query_context_id AND d.family='Q4'
        CROSS JOIN review_struct_field_names f
        WHERE len(d.field_decisions)<>6 OR list_extract(d.field_decisions,f.ordinal).field IS DISTINCT FROM f.field
          OR list_extract(d.field_decisions,f.ordinal).disposition IS DISTINCT FROM
            CASE WHEN p.boundary_country IS NULL THEN 'NOT_APPLICABLE'
                 WHEN f.field IN ('address','boundary_country') OR f.field='locality' AND p.locality IS NOT NULL
                     OR f.field='postalcode' AND p.postalcode IS NOT NULL THEN 'INCLUDE' ELSE 'OMIT' END
          OR list_filter(list_extract(d.field_decisions,f.ordinal).reason_codes,r -> r<>'PARSER_ONLY_FIELD_EXCLUDED') IS DISTINCT FROM
            CASE WHEN p.boundary_country IS NULL THEN [] WHEN f.field='region' THEN ['ADMIN_LEVEL_NOT_ESTABLISHED']
                 WHEN f.field='locality' AND p.locality_reason IS NOT NULL THEN [p.locality_reason]
                 WHEN f.field='postalcode' AND p.postcode_reason IS NOT NULL THEN [p.postcode_reason] ELSE [] END
    """,
    )
    zero(
        "all_hypothesis_country_boundary_mismatches",
        """
        SELECT count(*) FROM query_hypothesis h LEFT JOIN review_country_context c USING(query_context_id)
        WHERE c.boundary_country IS NULL OR h.intent.boundary_country IS DISTINCT FROM c.boundary_country
    """,
    )
    zero(
        "baseline_mutations_or_missing_baselines",
        """
        SELECT count(*) FROM review_struct_policy p JOIN candidate_evidence c USING(stage06_exact_candidate_id)
        LEFT JOIN query_family_decision d ON d.query_context_id=p.query_context_id
          AND d.family=CASE p.stage08_representation WHEN 'STANDARD' THEN 'Q1' ELSE 'Q2' END
        LEFT JOIN query_hypothesis h ON h.query_context_id=p.query_context_id AND h.hypothesis_id=d.hypothesis_id
        WHERE p.boundary_country IS NOT NULL AND (h.hypothesis_id IS NULL OR d.eligibility_state IS DISTINCT FROM 'ELIGIBLE'
          OR h.intent.text IS DISTINCT FROM c.stage06_candidate_lower OR h.intent.endpoint IS DISTINCT FROM '/v1/search'
          OR h.intent.search_mode IS DISTINCT FROM 'FULL_TEXT' OR h.intent.address IS NOT NULL
          OR h.intent.postalcode IS NOT NULL OR h.intent.locality IS NOT NULL OR h.intent.region IS NOT NULL
          OR h.intent.country IS NOT NULL OR h.intent.boundary_country IS DISTINCT FROM p.boundary_country)
    """,
    )
    zero(
        "country_unavailable_emitted_hypotheses",
        """
        SELECT count(*) FROM query_hypothesis h JOIN review_country_context c USING(query_context_id) WHERE c.boundary_country IS NULL
    """,
    )
    # Contract explicitly requires visible parser-geography exclusion reasons.
    # Even without a geographic parser token the policy is unconditional; count
    # real-token incidence as a separately stricter lower bound when available.
    db.execute("""
        CREATE TABLE review_struct_parser_reason AS
        SELECT p.query_context_id,p.stage06_exact_candidate_id,
          coalesce(list_contains(flatten(list_transform(d.field_decisions,f -> f.reason_codes)),'PARSER_ONLY_FIELD_EXCLUDED'),false) present
        FROM review_struct_policy p JOIN query_family_decision d
          ON d.query_context_id=p.query_context_id AND d.family='Q4' WHERE p.boundary_country IS NOT NULL
    """)
    zero(
        "q4_missing_visible_parser_geography_exclusion",
        "SELECT count(*) FROM review_struct_parser_reason WHERE NOT present",
    )
    count(
        "q4_with_visible_parser_geography_exclusion",
        "SELECT count(*) FROM review_struct_parser_reason WHERE present",
    )
    tables = {row[0] for row in db.execute("SHOW TABLES").fetchall()}
    if "parser_component_evidence" in tables:
        count(
            "q4_missing_exclusion_with_parser_geography",
            """
          SELECT count(*) FROM review_struct_parser_reason r
          WHERE NOT r.present AND EXISTS (SELECT 1 FROM parser_component_evidence p
            WHERE p.stage06_exact_candidate_id=r.stage06_exact_candidate_id
              AND p.stage08_safe_parser_evidence_component IN ('PARSER_CITY','PARSER_SUBURB','PARSER_CITY_DISTRICT',
                'PARSER_ISLAND','PARSER_STATE_DISTRICT','PARSER_STATE','PARSER_COUNTRY_REGION','PARSER_COUNTRY','PARSER_POSTCODE'))
        """,
        )
    return result
