"""Synthetic source/reference lineage; no protected reference or address reads."""

from __future__ import annotations

from typing import Any

import copy
import dataclasses

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s09_reference_contract as s9
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_evaluator as e
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_pack as p
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_questions as q
from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s10_query_evidence as evidence
from test_stage09_reference_evaluator import (
    candidate as _candidate,
    source as _source,
    reference_view as reference_view,
)
from test_stage10_query_families import context, decision


source: Any = _source
candidate: Any = _candidate


class SyntheticAccess:
    def __init__(self, view: Any) -> None:
        self.capabilities = copy.deepcopy(view.capabilities)
        self.objects = copy.deepcopy(view.objects)
        self.members: dict[bytes, list[Any]] = {}

    def capability(self, identifier: Any) -> Any:
        return self.capabilities[identifier]

    def object(self, identifier: Any) -> Any:
        return self.objects[identifier]

    def witnesses(self, row: Any) -> Any:
        if row["single_witness"] is not None:
            yield row["single_witness"]
        elif row["match_set_id"] is not None:
            yield from self.members[row["match_set_id"]]


def fixture_rows(
    view: Any,
    *,
    row: Any = None,
    cand: Any = None,
    postal_state: Any = "SUPPORTED",
    pair_state: Any = "SUPPORTED",
) -> Any:
    row = source() if row is None else row
    cand = candidate() if cand is None else cand
    access = SyntheticAccess(view)
    version = view.registry[s9.GN]["reference_version_id"]
    asset = view.registry[s9.GN]["assets"][0]["asset_id"]
    obj = p.make_object(
        version,
        asset,
        "synthetic:postal:1",
        "POSTAL_ASSOCIATION",
        "US",
        [
            p.field(
                "postal_code",
                row["stage03_clean_postcode"],
                "synthetic:postal:1/postal",
            ),
            p.field(
                "place_name", row["stage03_clean_city"], "synthetic:postal:1/locality"
            ),
            p.field("country_code", "US", "synthetic:postal:1/country"),
        ],
    )
    access.objects[obj["reference_object_id"]] = obj
    rows = []
    for question in q.source_questions(row, cand):
        for family in s9.QUESTIONS[question.question_id].references:
            prepared = view.prepare(question, family)
            if family == s9.GN:
                state = pair_state if question.question_id == "Q06" else postal_state
                if prepared.unavailable_reason:
                    result = e.LookupResult(
                        "NOT_EVALUABLE", prepared.unavailable_reason
                    )
                elif state == "SUPPORTED":
                    result = e.LookupResult(
                        "SUPPORTED",
                        "EXACT_REFERENCE_SUPPORT",
                        [e.witness(obj, [e.pointer(obj, x) for x in obj["fields"]])],
                    )
                else:
                    result = e.LookupResult(
                        state,
                        "REFERENCE_ASSOCIATION_MISMATCH"
                        if state == "NOT_FOUND"
                        else "COMPONENT_CAPABILITY_MISSING",
                    )
            elif family == "NONE":
                result = e.LookupResult("NOT_EVALUABLE", "CAPABILITY_NOT_CONFIGURED")
            else:
                result = view.lookup_small(prepared)
            r, members = e.finalize_small(
                prepared, result, profile=b"p" * 32, stage08_logical=b"l" * 32
            )
            rows.append(r)
            for member in members:
                access.members.setdefault(member["match_set_id"], []).append(
                    member["witness"]
                )
    return row, cand, rows, access


def test_source_anchored_postcode_locality_supported(reference_view: Any) -> None:
    args = fixture_rows(reference_view)
    policy = evidence.evaluate_source_fields(*args)
    assert (
        policy.country == "US"
        and policy.postcode == "00123"
        and policy.locality == "Exampletown"
    )
    assert policy.contradiction_capabilities == ()


@pytest.mark.parametrize("state", ["NOT_FOUND", "NOT_EVALUABLE"])
def test_nonpositive_geonames_is_not_negative(reference_view: Any, state: Any) -> None:
    args = fixture_rows(reference_view, postal_state=state)
    policy = evidence.evaluate_source_fields(*args)
    assert (
        policy.country == "US"
        and policy.locality == "Exampletown"
        and policy.postcode is None
    )
    assert (
        policy.contradiction_capabilities == ()
        and "CONTRADICTION_GATE" not in policy.postcode_reasons
    )


def test_pair_support_required_when_locality_included(reference_view: Any) -> None:
    args = fixture_rows(reference_view, pair_state="NOT_FOUND")
    policy = evidence.evaluate_source_fields(*args)
    assert (
        policy.locality == "Exampletown"
        and policy.postcode is None
        and policy.contradiction_capabilities == ()
    )


@pytest.mark.parametrize(
    "postcode,expected_question", [("1234", "Q04"), ("99123", "Q08")]
)
def test_authorized_postcode_conflict_excludes_only_structured(
    reference_view: Any, tmp_path: Any, postcode: Any, expected_question: Any
) -> None:
    args = fixture_rows(reference_view, row=source(postcode=postcode))
    policy = evidence.evaluate_source_fields(*args)
    assert policy.postcode is None and policy.locality == "Exampletown"
    assert policy.contradiction_capabilities == (expected_question,)
    assert policy.postcode_reasons == ("CONTRADICTION_GATE",)
    ctx = dataclasses.replace(context(tmp_path), fields=policy)
    assert decision(ctx, "Q2")[1]["intent"]["text"] == ctx.text
    assert decision(ctx, "Q4")[1]["intent"]["address"] == ctx.text


def test_missing_negative_authority_does_not_gate(reference_view: Any) -> None:
    row, cand, rows, access = fixture_rows(reference_view, row=source(postcode="99123"))
    conflict = next(x for x in rows if x["question_catalog_id"] == "Q08")
    access.capabilities[conflict["rule_capability_id"]]["negative_authority"] = False
    policy = evidence.evaluate_source_fields(row, cand, rows, access)
    assert policy.postcode == "99123" and policy.contradiction_capabilities == ()


def test_unresolved_candidate_country_does_not_block_local_q01(
    reference_view: Any,
) -> None:
    args = fixture_rows(reference_view, cand=candidate(country=None))
    policy = evidence.evaluate_source_fields(*args)
    assert policy.country == "US"
    assert policy.postcode is None and policy.locality is None
    assert policy.contradiction_capabilities == ()


@pytest.mark.parametrize("country", ["", " us", "ZZ", "usa", "U1"])
def test_malformed_or_unrecognized_row_country_abstains(
    reference_view: Any, country: Any
) -> None:
    args = fixture_rows(reference_view, row=source(country=country))
    policy = evidence.evaluate_source_fields(*args)
    assert policy.country is None


def test_same_candidate_different_row_country_independent(reference_view: Any) -> None:
    us = fixture_rows(reference_view)
    row = source(country="de")
    row["stable_source_row_id_v1"] = b"x" * 32
    de = fixture_rows(reference_view, row=row, cand=candidate(country=None))
    assert evidence.evaluate_source_fields(*us).country == "US"
    assert evidence.evaluate_source_fields(*de).country == "DE"
    assert us[1]["stage06_exact_candidate_id"] == de[1]["stage06_exact_candidate_id"]


@pytest.mark.parametrize(
    "mutation",
    [
        "source",
        "candidate",
        "parser",
        "argument",
        "duplicate",
        "missing",
        "geonames_negative",
    ],
)
def test_grain_and_lineage_corruption_fail_closed(
    reference_view: Any, mutation: Any
) -> None:
    row, cand, rows, access = fixture_rows(reference_view)
    target = next(x for x in rows if x["question_catalog_id"] == "Q05")
    if mutation == "source":
        target["stable_source_row_id_v1"] = b"X" * 32
    elif mutation == "candidate":
        target["stage06_exact_candidate_id"] = b"X" * 32
    elif mutation == "parser":
        target["evidence_scope"] = "PARSER_CANDIDATE"
    elif mutation == "argument":
        target["arguments"][1]["origin_field"] = "stage03_clean_city"
    elif mutation == "duplicate":
        rows.append(copy.deepcopy(target))
    elif mutation == "missing":
        rows.remove(target)
    else:
        target["result_state"] = "CONTRADICTED"
    with pytest.raises(c.Stage10Error, match="^STAGE10_"):
        evidence.evaluate_source_fields(row, cand, rows, access)


def test_parser_components_do_not_populate_q4(reference_view: Any) -> None:
    args = fixture_rows(reference_view, cand=candidate(component_count=881338))
    policy = evidence.evaluate_source_fields(*args)
    other = fixture_rows(reference_view, cand=candidate(component_count=0))
    assert policy == evidence.evaluate_source_fields(*other)


@pytest.mark.parametrize(
    "postcode,mutation",
    [
        ("1234", "scope"),
        ("1234", "field"),
        ("1234", "version"),
        ("99123", "prefix"),
        ("99123", "country_pattern"),
        ("99123", "admin_name"),
    ],
)
def test_complete_negative_certificate_required(
    reference_view: Any, postcode: Any, mutation: Any
) -> None:
    row, cand, rows, access = fixture_rows(
        reference_view, row=source(postcode=postcode)
    )
    target = next(r for r in rows if r["result_state"] == "CONTRADICTED")
    if mutation == "scope":
        access.capabilities[target["rule_capability_id"]]["scope_locator"] = "OTHER/zip"
    elif mutation == "version":
        access.objects[target["single_witness"]["reference_object_id"]][
            "reference_version_id"
        ] = b"x" * 32
    elif mutation == "field":
        target["single_witness"]["fields"][0]["field_name"] = "key"
    else:
        w = target["single_witness"]
        wanted = {
            "prefix": ("zip", "sub_zips"),
            "country_pattern": ("zip",),
            "admin_name": ("key", "name", "sub_keys", "sub_names"),
        }[mutation]
        w["fields"] = [
            p
            for p in w["fields"]
            if not (
                p["field_name"] in wanted
                and (
                    mutation != "country_pattern"
                    or access.object(p["reference_object_id"])["object_kind"]
                    == "FORMAT_COUNTRY"
                )
            )
        ]
    with pytest.raises(c.Stage10Error, match="WITNESS_INVALID"):
        evidence.evaluate_source_fields(row, cand, rows, access)
