"""C01/C02 regression and pinned pre-repair equivalence; synthetic values only."""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s10_query_evidence as evidence
from safe_geocoding_pipeline.preprocessing.stages import s10_query_families as f
from safe_geocoding_pipeline.preprocessing.stages import s10_query_io as io
from safe_geocoding_pipeline.preprocessing.stages import s10_query_publication as pub
from test_stage09_reference_evaluator import reference_view as reference_view
from test_stage10_query_evidence import fixture_rows, source
from test_stage10_query_families import SyntheticTransform, context, decision
from test_stage10_publication import build, validate

EXCLUDED = "PARSER_ONLY_FIELD_EXCLUDED"


def prior_scientific_projection(pair: Any) -> Any:
    """Remove only the authorized C01 field-policy addition for old goldens."""
    result = copy.deepcopy(pair)
    for row in result[1]:
        for field in row["field_decisions"]:
            if EXCLUDED in field["reason_codes"]:
                assert row["family"] == "Q4" and field["disposition"] == "OMIT"
                assert field["field"] in ("postalcode", "locality", "region", "country")
                field["reason_codes"].remove(EXCLUDED)
    return result


def fields(row: Any) -> Any:
    result = {v["field"]: v for v in row["field_decisions"]}
    assert len(result) == len(row["field_decisions"]) == 6
    return result


@pytest.mark.parametrize(
    "label,field",
    [
        ("postcode", "postalcode"),
        ("city", "locality"),
        ("state", "region"),
        ("country", "country"),
    ],
)
@pytest.mark.parametrize("copies", [1, 5])
def test_parser_only_geography_is_visible_once_per_field(
    tmp_path: Any, label: str, field: str, copies: int
) -> None:
    ctx = context(
        tmp_path,
        components=[(label, "invented parser value")] * copies,
        structured=False,
    )
    ctx = dataclasses.replace(ctx, source_clean_postcode="", source_clean_locality="")
    row, hypothesis = decision(ctx, "Q4")
    assert hypothesis is None
    assert fields(row)[field]["disposition"] == "OMIT"
    assert fields(row)[field]["reason_codes"].count(EXCLUDED) == 1
    assert EXCLUDED not in row["reason_codes"]
    assert row["primary_reason"] == "INSUFFICIENT_TRUSTED_STRUCTURED_EVIDENCE"
    assert decision(ctx, "Q2")[1]["intent"]["text"] == ctx.text


@pytest.mark.parametrize("value", ["Exampleville", "unrelated parser place"])
def test_source_anchored_field_not_relabelled_or_overwritten(
    tmp_path: Any, value: str
) -> None:
    ctx = context(tmp_path, components=[("city", value)])
    row, hypothesis = decision(ctx, "Q4")
    assert fields(row)["locality"] == {
        "field": "locality",
        "disposition": "INCLUDE",
        "reason_codes": [],
    }
    assert hypothesis["intent"]["locality"] == "Exampleville"
    assert fields(row)["region"]["reason_codes"] == [
        "ADMIN_LEVEL_NOT_ESTABLISHED",
        EXCLUDED,
    ]
    assert fields(row)["country"]["reason_codes"] == [EXCLUDED]


def test_matching_parser_postcode_does_not_relabel_eligible_source(
    reference_view: Any, tmp_path: Any
) -> None:
    args = fixture_rows(reference_view)
    policy = evidence.evaluate_source_fields(*args)
    assert policy.postcode is not None
    ctx = dataclasses.replace(
        context(tmp_path, components=[("postcode", policy.postcode)]), fields=policy
    )
    row, hypothesis = decision(ctx, "Q4")
    assert fields(row)["postalcode"] == {
        "field": "postalcode",
        "disposition": "INCLUDE",
        "reason_codes": [],
    }
    assert hypothesis["intent"]["postalcode"] == args[0]["stage03_clean_postcode"]


@pytest.mark.parametrize("state", ["NOT_FOUND", "NOT_EVALUABLE"])
def test_nonpositive_reference_does_not_admit_parser_postcode(
    reference_view: Any, tmp_path: Any, state: str
) -> None:
    policy = evidence.evaluate_source_fields(
        *fixture_rows(reference_view, postal_state=state)
    )
    ctx = dataclasses.replace(
        context(tmp_path, components=[("postcode", "77777")]), fields=policy
    )
    row, hypothesis = decision(ctx, "Q4")
    assert hypothesis["intent"]["postalcode"] is None
    assert fields(row)["postalcode"]["reason_codes"] == [
        "INSUFFICIENT_TRUSTED_STRUCTURED_EVIDENCE",
        EXCLUDED,
    ]
    assert "CONTRADICTION_GATE" not in fields(row)["postalcode"]["reason_codes"]


@pytest.mark.parametrize("postcode,question", [("1234", "Q04"), ("99123", "Q08")])
def test_contradiction_preserves_source_gate_and_baselines(
    reference_view: Any, tmp_path: Any, postcode: str, question: str
) -> None:
    policy = evidence.evaluate_source_fields(
        *fixture_rows(reference_view, row=source(postcode=postcode))
    )
    ctx = dataclasses.replace(
        context(tmp_path, components=[("postcode", postcode)]), fields=policy
    )
    row, hypothesis = decision(ctx, "Q4")
    assert policy.contradiction_capabilities == (question,)
    assert hypothesis["intent"]["postalcode"] is None
    assert fields(row)["postalcode"]["reason_codes"] == ["CONTRADICTION_GATE", EXCLUDED]
    for role, family in [("STANDARD", "Q1"), ("NATIVE", "Q2")]:
        assert (
            decision(dataclasses.replace(ctx, role=role), family)[1]["intent"]["text"]
            == ctx.text
        )


def test_inapplicable_country_gate_and_serialization(tmp_path: Any) -> None:
    ctx = context(tmp_path, country=None)
    row, hypothesis = decision(ctx, "Q4")
    assert hypothesis is None
    assert all(
        x["disposition"] == "NOT_APPLICABLE" and not x["reason_codes"]
        for x in row["field_decisions"]
    )
    row, _ = decision(context(tmp_path), "Q4")
    io.validate_values(row, "query_family_decision")
    path = tmp_path / "synthetic.parquet"
    pq.write_table(
        pa.Table.from_pylist([row], schema=io.output_schema("query_family_decision")),
        path,
    )
    assert pq.read_table(path).to_pylist() == [row]


@pytest.mark.parametrize("role", c.ROLES)
@pytest.mark.parametrize("country", [None, "DE"])
@pytest.mark.parametrize(
    "locality,postcode",
    [(None, None), ("Exampleville", None), (None, "01234"), ("Exampleville", "01234")],
)
def test_pinned_old_vs_repaired_complete_scientific_equality(
    tmp_path: Any,
    monkeypatch: Any,
    role: str,
    country: str | None,
    locality: str | None,
    postcode: str | None,
) -> None:
    # Exact _structured source from the reviewed executable, not a recreation of
    # the repaired function. Its imports are the byte-unchanged shared helpers.
    raw = (
        Path(__file__).parent / "fixtures/stage10/prior_structured_63f3cd10.txt"
    ).read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "aca6b2230a903666bbf8825530f9b8877897362244c1a7b908b8080ce0b5fa64"
    )
    namespace = dict(vars(f))
    exec(compile(raw, "pinned_public_prior_structured", "exec"), namespace)
    ctx = context(tmp_path, role=role)
    ctx = dataclasses.replace(
        ctx,
        fields=dataclasses.replace(
            ctx.fields, country=country, locality=locality, postcode=postcode
        ),
    )
    new_h, new_d = f.generate(ctx, SyntheticTransform())
    monkeypatch.setattr(f, "_structured", namespace["_structured"])
    old_h, old_d = f.generate(ctx, SyntheticTransform())
    assert new_h == old_h  # Complete payloads, contexts, IDs, rank, convergence.
    normalized = copy.deepcopy(new_d)
    for row in normalized:
        for field in row["field_decisions"]:
            field["reason_codes"] = [r for r in field["reason_codes"] if r != EXCLUDED]
    assert normalized == old_d  # Only missing field-policy reason changes.
    assert [d["family_decision_id"] for d in old_d] == [
        d["family_decision_id"] for d in new_d
    ]


def test_exact_registration_names_and_portable_hash(tmp_path: Any) -> None:
    result = pub.publish(tmp_path / "published", build, validate)
    record = json.loads((result.path / io.SUCCESS_NAME).read_bytes())
    bindings = record["bindings"]
    assert bindings["namespace"] == "STAGE10_DEVELOPMENT_QUERY_PLAN"
    assert (
        bindings["stage10_input_binding_sha256"]
        == result.manifest["input_binding_sha256"]
    )
    assert "stage10_input_sha256" not in bindings
    assert (
        record["commit_record_id"]
        == hashlib.sha256(
            b"SAFE:publication-commit:v2\0"
            + pub.canonical({"protocol": record["protocol"], "bindings": bindings})
        ).hexdigest()
    )
    assert validate(result.path, result.manifest_sha256, True) == result.manifest


@pytest.mark.parametrize("fault", ["namespace", "key", "hash_domain"])
def test_reopen_rejects_deprecated_contract_even_with_recomputed_hash(
    tmp_path: Any, fault: str
) -> None:
    result = pub.publish(tmp_path / "published", build, validate)
    record = json.loads((result.path / io.SUCCESS_NAME).read_bytes())
    if fault == "namespace":
        record["bindings"]["namespace"] = "STAGE10_DEVELOPMENT_QUERY_HYPOTHESES"
    elif fault == "key":
        record["bindings"]["stage10_input_sha256"] = record["bindings"].pop(
            "stage10_input_binding_sha256"
        )
    record = pub.registration(record["bindings"])
    if fault == "hash_domain":
        record["commit_record_id"] = hashlib.sha256(
            b"wrong-domain\0" + pub.canonical(record["bindings"])
        ).hexdigest()
    # Deliberate corruption of synthetic artifacts only.
    (result.path / io.SUCCESS_NAME).write_bytes(pub.canonical(record))
    with pytest.raises(c.Stage10Error, match="SUCCESS_BINDING_MISMATCH"):
        validate(result.path, result.manifest_sha256, True)


@pytest.mark.parametrize("state", [False, "prepared", True])
def test_wrong_manifest_namespace_rejected_in_every_publication_state(
    tmp_path: Any, state: Any
) -> None:
    result = pub.publish(tmp_path / "published", build, validate)
    manifest = dict(result.manifest, kind="STAGE10_DEVELOPMENT_QUERY_HYPOTHESES")
    path = result.path / io.MANIFEST_NAME
    path.write_bytes(c.canonical(manifest))
    with pytest.raises(c.Stage10Error, match="NAMESPACE_INVALID"):
        pub.validate_terminal(result.path, c.sha256_file(path), state)
