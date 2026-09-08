"""Only invented values and public country codes; no protected fixtures."""

from __future__ import annotations

import copy
import hashlib
import struct

import pyarrow as pa
import pytest

from safe_geocoding_pipeline.preprocessing.stages import s09_reference_contract as c


@pytest.mark.parametrize(
    "method,country,value,expected",
    [
        (c.ISO_NORM, "DE", "de", "DE"),
        (c.ISO_NORM, "DE", " de ", " DE "),
        (c.ISO_NORM, "DE", "ßéı", "ßéı"),
        (c.EXACT_NORM, "US", "00123", "00123"),
        (c.EXACT_NORM, "US", "00123-1234", "00123-1234"),
        (c.FORM_NORM, "GB", "ab1 2cd", "AB1 2CD"),
        (c.SEPARATOR_NORM, "JP", "001-2345", "0012345"),
        (c.SEPARATOR_NORM, "JP", "001 2345", "001 2345"),
        (c.SEPARATOR_NORM, "JP", "001--2345", "001--2345"),
        (c.SEPARATOR_NORM, "PL", "00-123", "00123"),
        (c.SEPARATOR_NORM, "PT", "0001-234", "0001234"),
        (c.SEPARATOR_NORM, "BR", "00123-456", "00123456"),
        (c.SEPARATOR_NORM, "SE", "001 23", "00123"),
        (c.SEPARATOR_NORM, "CZ", "001\u00a023", "001\u00a023"),
        (c.SEPARATOR_NORM, "SK", "00123", "00123"),
        (c.SEPARATOR_NORM, "PL", "٠٠-١٢٣", "٠٠-١٢٣"),
        (c.NAME_NORM, "DE", "E\u0301xample", "éxample"),
        (c.NAME_NORM, "DE", "Straße", "straße"),
        (c.NAME_NORM, "TR", "İ", "i\u0307"),
        (c.NAME_NORM, "CN", "示例A", "示例a"),
        (c.NAME_NORM, "GR", "Δοκιμή", "δοκιμή"),
    ],
)
def test_lossless_lookup_boundary(method, country, value, expected):
    original = value
    assert c.normalize(method, value, country) == expected
    assert value == original


@pytest.mark.parametrize("value", [-1, 2**64, b"short", 1.2, {"a": 1}])
def test_identity_rejects_untyped_values(value):
    with pytest.raises(c.Stage09Error):
        c.identity("TEST", (value,))


def test_exact_typed_identity_formula():
    domain = b"\x02" + struct.pack(">Q", 4) + b"TEST"
    values = (
        b"\x05"
        + struct.pack(">Q", 4)
        + b"\x00\x04\x01\x03"
        + struct.pack(">Q", 1)
        + b"\x01"
        + bytes(32)
    )
    prefix = struct.pack(">Q", 4)
    for text in ("SAFE_STAGE09", "V1"):
        prefix += b"\x02" + struct.pack(">Q", len(text)) + text.encode()
    assert (
        c.identity("TEST", (None, True, 1, bytes(32)))
        == hashlib.sha256(prefix + domain + values).digest()
    )
    assert (
        len({c.identity("TEST", (v,)) for v in (None, False, 0, "0", bytes(32), ())})
        == 6
    )
    assert c.identity("A", ("a", "bc")) != c.identity("A", ("ab", "c"))
    assert c.identity("A", ("x",)) != c.identity("B", ("x",))


def test_schema_is_exactly_six_relations_without_source_duplicates():
    assert set(c.RELATIONS) == {
        "reference_registry",
        "reference_capability",
        "reference_object",
        "candidate_reference_evidence",
        "reference_match_member",
        "coverage_summary",
    }
    for name in c.RELATIONS:
        schema = c.relation_schema(name)
        assert all(k in schema.names for k in c.PRIMARY_KEYS[name])
        assert len(c.schema_fingerprint(name)) == 32
        assert all(f.metadata[b"semantic_class"] for f in schema)
    evidence = c.relation_schema("candidate_reference_evidence")
    assert evidence.field("stage06_exact_candidate_id").type == pa.binary(32)
    for word in (
        "latitude",
        "longitude",
        "corrected",
        "accepted_match",
        "query",
        "score",
        "source_value",
        "parser_trust",
    ):
        assert not any(word in name for name in evidence.names)


def test_relation_hash_is_layout_independent_and_exact_formula():
    rows = [
        {
            "match_set_id": bytes(32),
            "member_ordinal": i,
            "witness": {
                "reference_object_id": bytes([i]) * 32,
                "witness_role": "SUPPORT",
                "fields": [],
            },
        }
        for i in range(3)
    ]
    schema = c.relation_schema("reference_match_member")
    expected = c.identity(
        "RELATION",
        (
            "reference_match_member",
            c.schema_fingerprint("reference_match_member"),
            3,
            tuple(c.ordered_values(r, schema) for r in rows),
        ),
    )
    assert c.relation_fingerprint("reference_match_member", 3, iter(rows)) == expected
    batches = [
        pa.Table.from_pylist(rows[:1], schema=schema),
        pa.Table.from_pylist(rows[1:], schema=schema),
    ]
    restored = (r for batch in batches for r in batch.to_pylist())
    assert c.relation_fingerprint("reference_match_member", 3, restored) == expected
    with pytest.raises(c.Stage09Error, match="ORDER_OR_COLLISION"):
        c.relation_fingerprint("reference_match_member", 3, reversed(rows))
    with pytest.raises(c.Stage09Error, match="COUNT_MISMATCH"):
        c.relation_fingerprint("reference_match_member", 4, rows)


def _example(state="NOT_FOUND", family=c.GN):
    cap = {
        "capability_id": b"c" * 32,
        "reference_version_id": b"v" * 32,
        "enabled": True,
        "positive_authority": True,
        "negative_authority": False,
    }
    row = {
        "evidence_id": b"e" * 32,
        "stage06_exact_candidate_id": b"d" * 32,
        "evidence_scope": "SOURCE_ROW",
        "stable_source_row_id_v1": b"s" * 32,
        "question_catalog_id": "Q05",
        "reference_slot": family,
        "reference_version_id": b"v" * 32,
        "reference_asset_id": b"a" * 32,
        "capability_id": b"c" * 32,
        "rule_capability_id": None,
        "evidence_family": family,
        "interpretation": "SOURCE_FIELD_ROLE",
        "claim_scope": "REFERENCE_SNAPSHOT",
        "arguments": [],
        "result_state": state,
        "reason_code": "VALUE_ABSENT_FROM_REFERENCE",
        "contradiction_type": None,
        "country_assessment": "COUNTRY_UNRESOLVED",
        "country_assessment_basis": "NO_UNIFORM_WITNESS",
        "lookup_identity": b"l" * 32,
        "witness_count": 0,
        "single_witness": None,
        "match_set_id": None,
        "evidence_class": "REFERENCE_EVIDENCE",
    }
    if state in ("SUPPORTED", "CONTRADICTED"):
        row.update(
            witness_count=1,
            single_witness={
                "reference_object_id": b"o" * 32,
                "witness_role": "SUPPORT" if state == "SUPPORTED" else "CONTRADICTION",
                "fields": [],
            },
            reason_code="EXACT_REFERENCE_SUPPORT"
            if state == "SUPPORTED"
            else "EXPLICIT_RULE_CONFLICT",
        )
    if state == "CONTRADICTED":
        row["contradiction_type"] = "FORMAT_RULE_CONFLICT"
    if state == "NOT_EVALUABLE":
        row["reason_code"] = "COMPONENT_CAPABILITY_MISSING"
    return row, cap


@pytest.mark.parametrize("state", c.STATES)
def test_four_states_require_authorized_certificates(state):
    row, cap = _example(state, c.LIA)
    cap["negative_authority"] = state == "CONTRADICTED"
    c.validate_evidence_semantics(row, cap)
    pa.Table.from_pylist(
        [row], schema=c.relation_schema("candidate_reference_evidence")
    )


@pytest.mark.parametrize("negative", (True, False))
def test_geonames_cannot_contradict_even_if_capability_is_corrupt(negative):
    row, cap = _example("CONTRADICTED")
    cap["negative_authority"] = negative
    with pytest.raises(c.Stage09Error, match="NEGATIVE_AUTHORITY_REQUIRED"):
        c.validate_evidence_semantics(row, cap)


def test_association_mismatch_is_not_source_invalidity():
    row, cap = _example()
    row["reason_code"] = "REFERENCE_ASSOCIATION_MISMATCH"
    c.validate_evidence_semantics(row, cap)
    row["result_state"] = "CONTRADICTED"
    with pytest.raises(c.Stage09Error):
        c.validate_evidence_semantics(row, cap)


@pytest.mark.parametrize(
    "field,value",
    [
        ("result_state", "INVALID"),
        ("reason_code", "SOURCE_INVALID"),
        ("evidence_class", "FINAL_ACCEPTED_RESULT"),
        ("country_assessment", "COUNTRY_SUPPORTED"),
        ("contradiction_type", "FORMAT_RULE_CONFLICT"),
        ("evidence_family", "POSTAL_AUTHORITY"),
        ("witness_count", 1),
        ("reference_asset_id", None),
        ("stable_source_row_id_v1", None),
    ],
)
def test_semantic_mutation_fails_closed_without_values_in_errors(field, value):
    row, cap = _example()
    row[field] = value
    with pytest.raises(c.Stage09Error) as error:
        c.validate_evidence_semantics(row, cap)
    assert "00123" not in str(error.value)


def test_missing_capability_cannot_be_promoted_by_success():
    row, cap = _example("SUPPORTED")
    for field in ("positive_authority", "enabled"):
        mutated = copy.deepcopy(cap)
        mutated[field] = False
        with pytest.raises(c.Stage09Error, match="CAPABILITY_NOT_ENABLED"):
            c.validate_evidence_semantics(row, mutated)


def test_parser_country_never_sets_country_assessment():
    row, cap = _example("SUPPORTED", c.ISO)
    row.update(
        evidence_scope="PARSER_CANDIDATE",
        stable_source_row_id_v1=None,
        question_catalog_id="Q14",
        country_assessment="COUNTRY_SUPPORTED",
    )
    with pytest.raises(c.Stage09Error, match="COUNTRY_INFERENCE_PROHIBITED"):
        c.validate_evidence_semantics(row, cap)


def test_question_schedule_has_frozen_source_slot_count():
    assert sum(len(q.references) for q in c.CATALOG if q.question_id != "Q14") == 18
    assert max(len(q.roles) for q in c.CATALOG) == 3
    assert c.capability_name(c.QUESTIONS["Q10"], c.LIA) == "ADMIN_ENUMERATION"
    assert c.normalization_method("Q10", "ADMIN", c.ISO, "DE", "de-ab") == c.ISO_NORM
    assert c.normalization_method("Q10", "ADMIN", c.ISO, "DE", "ab") == c.NAME_NORM


def test_exact_runtime_guard_is_not_weakened(monkeypatch):
    c.require_runtime()
    monkeypatch.setattr(c.sys, "version_info", (3, 14, 7))
    with pytest.raises(c.Stage09Error, match="EXACT_RUNTIME_REQUIRED"):
        c.require_runtime()


def test_manifest_json_rejects_duplicates_floats_and_invalid_utf8(tmp_path):
    path = tmp_path / "synthetic.json"
    for content in (b'{"a":1,"a":2}', b'{"a":1.2}', b'{"a":NaN}', b"\xff"):
        path.write_bytes(content)
        with pytest.raises(c.Stage09Error):
            c.read_json(path)
