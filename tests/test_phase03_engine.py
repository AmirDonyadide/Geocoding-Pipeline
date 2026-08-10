from __future__ import annotations

from pathlib import Path

import pytest

from safe_geocoding_pipeline.phase03.config import Phase03Config
from safe_geocoding_pipeline.phase03.constants import CORE_COLUMNS, EVIDENCE_COLUMNS
from safe_geocoding_pipeline.phase03.engine import (
    native_relationship,
    select_candidates,
)
from safe_geocoding_pipeline.phase03.models import Candidate, RawSpan

from phase03_helpers import engine, fictional_script_reference, phase02_row


def test_structured_geography_and_postcode_are_conservative_strings(
    tmp_path: Path,
) -> None:
    result = engine(tmp_path).transform(
        phase02_row(
            postcode="00123",
            city="Exampleville",
            region_in_country="Demo Region",
            country_iso_code="XZ",
        )
    )
    core = result.core_row
    assert tuple(core) == CORE_COLUMNS
    assert core["postcode_clean"] == "00123"
    assert core["locality_clean"] == "Exampleville"
    assert core["region_clean"] == "Demo Region"
    assert core["country_clean"] == "XZ"
    assert core["address_completeness_class"] == "D_LOCALITY_LEVEL"
    assert core["diagnostic_evaluation_status"] == "FULLY_EVALUATED"
    assert core["address_parse_status"] == "INSUFFICIENT"
    assert result.evidence_rows == []


def test_blank_country_only_and_non_latin_component_boundaries(tmp_path: Path) -> None:
    parser = engine(tmp_path)
    blank = parser.transform(phase02_row())
    assert blank.core_row["address_parse_status"] == "INSUFFICIENT"
    assert blank.core_row["address_completeness_class"] == "Z_NO_COMPONENTS"
    assert blank.core_row["diagnostic_evaluation_status"] == "FULLY_EVALUATED"

    country_only = parser.transform(phase02_row(country_iso_code="XZ"))
    assert country_only.core_row["address_completeness_class"] == "E_COUNTRY_ONLY"
    assert country_only.core_row["country_clean"] == "XZ"

    non_latin = parser.transform(phase02_row(street_address_line_1_native="Apt غرفة"))
    assert non_latin.core_row["unit_native_clean"] == "غرفة"
    evidence = next(
        row for row in non_latin.evidence_rows if row["component"] == "UNIT"
    )
    raw = "Apt غرفة"
    assert (
        raw[evidence["start_character"] : evidence["end_character_exclusive"]] == "غرفة"
    )


@pytest.mark.parametrize("value", ["Na", "Nan", "Null"])
def test_ambiguous_country_placeholders_never_select_alone(
    tmp_path: Path, value: str
) -> None:
    result = engine(tmp_path).transform(phase02_row(country_iso_code=value))
    assert result.core_row["country_clean"] is None
    assert result.core_row["country_input_class"] == "AMBIGUOUS_PLACEHOLDER_LIKE"
    assert (
        "AMBIGUOUS_PLACEHOLDER_LIKE_PRESENT"
        in result.core_row["address_diagnostic_flags"]
    )
    assert all(tuple(row) == EVIDENCE_COLUMNS for row in result.evidence_rows)
    assert all(row["candidate_value"] is None for row in result.evidence_rows)


def test_uppercase_na_and_corroborated_mixed_case_na_are_distinct(
    tmp_path: Path,
) -> None:
    parser = engine(tmp_path)
    uppercase = parser.transform(phase02_row(country_iso_code="NA"))
    assert uppercase.core_row["country_clean"] == "NA"
    assert uppercase.core_row["country_parse_method"] == "STRUCTURED_ALPHA2_EXACT"

    corroborated = parser.transform(
        phase02_row(country_iso_code="Na", street_address_line_4="Namibia")
    )
    assert corroborated.core_row["country_clean"] == "NA"
    assert (
        corroborated.core_row["country_parse_method"]
        == "MULTISOURCE_CORROBORATED_PLACEHOLDER_COLLISION"
    )
    assert (
        "PLACEHOLDER_REFERENCE_COLLISION_CORROBORATED"
        in corroborated.core_row["address_diagnostic_flags"]
    )


def test_country_reference_conflict_is_retained(tmp_path: Path) -> None:
    result = engine(tmp_path).transform(
        phase02_row(country_iso_code="NA", street_address_line_4="Fictionland")
    )
    assert result.core_row["address_parse_status"] == "CONFLICT"
    assert result.core_row["country_clean"] is None
    assert "COUNTRY_SOURCE_CONFLICT" in result.core_row["address_conflict_flags"]
    assert any(
        row["evidence_kind"] == "CONFLICTING_EVIDENCE" for row in result.evidence_rows
    )


def test_country_input_diagnostics_are_explicit_and_do_not_infer(
    tmp_path: Path,
) -> None:
    parser = engine(tmp_path)
    unknown = parser.transform(phase02_row(country_iso_code="xx"))
    assert unknown.core_row["country_clean"] is None
    assert (
        "COUNTRY_STRUCTURED_UNRECOGNIZED"
        in unknown.core_row["address_diagnostic_flags"]
    )
    region_like = parser.transform(phase02_row(country_iso_code="Demo Province Name"))
    assert (
        "COUNTRY_STRUCTURED_REGION_LIKE"
        in region_like.core_row["address_diagnostic_flags"]
    )
    freeform = parser.transform(phase02_row(street_address_line_4="Fictionland"))
    assert freeform.core_row["country_clean"] is None
    assert (
        "STRUCTURED_GEOGRAPHY_MISSING_FREEFORM_PRESENT"
        in freeform.core_row["address_diagnostic_flags"]
    )


@pytest.mark.parametrize(
    ("line", "column", "expected"),
    [
        ("Apt. 7B", "unit_clean", "7B"),
        ("Level 4", "floor_clean", "4"),
        ("Building North Tower", "building_clean", "North Tower"),
        ("PO Box 77", None, None),
    ],
)
def test_explicit_marker_rules_are_bounded_and_selectable(
    tmp_path: Path, line: str, column: str | None, expected: str | None
) -> None:
    result = engine(tmp_path).transform(phase02_row(street_address_line_1=line))
    if column:
        assert result.core_row[column] == expected
    else:
        assert result.core_row["is_po_box"] is True
    assert result.core_row["address_parse_status"] == "PARSED"
    assert any(
        row["evidence_kind"] == "SELECTED_NONTRIVIAL_COMPONENT"
        for row in result.evidence_rows
    )


@pytest.mark.parametrize(
    "line",
    ["Box 77", "Aptitude 7", "Ground 4", "North Building", "Unit"],
)
def test_marker_false_positive_boundaries_remain_unresolved(
    tmp_path: Path, line: str
) -> None:
    result = engine(tmp_path).transform(phase02_row(street_address_line_1=line))
    assert not any(candidate.selectable for candidate in result.candidates)
    assert result.core_row["address_parse_status"] == "UNPARSEABLE"


def test_organization_historical_and_house_edges_are_not_overpromoted(
    tmp_path: Path,
) -> None:
    parser = engine(tmp_path)
    organization = parser.transform(
        phase02_row(street_address_line_1="Fictional Research GmbH")
    )
    assert organization.core_row["organization_clean"] is None
    assert organization.core_row["possible_company_only"] is True
    assert any(
        candidate.component == "ORGANIZATION" and not candidate.selectable
        for candidate in organization.candidates
    )

    historical = parser.transform(phase02_row(street_address_line_1="former address"))
    assert historical.core_row["is_historical"] is True
    assert "HISTORICAL_EVIDENCE" in historical.core_row["address_diagnostic_flags"]

    house = parser.transform(phase02_row(street_address_line_1="12 Fictional Road"))
    assert house.core_row["house_number_clean"] is None
    assert any(
        candidate.component == "HOUSE_NUMBER" and not candidate.selectable
        for candidate in house.candidates
    )


def test_registered_building_organization_overlap_is_a_conflict(
    tmp_path: Path,
) -> None:
    result = engine(tmp_path).transform(
        phase02_row(street_address_line_1="Building Fictional Research GmbH")
    )
    assert (
        "BUILDING_ORGANIZATION_ROLE_CONFLICT"
        in result.core_row["address_conflict_flags"]
    )
    assert result.core_row["building_clean"] is None
    assert result.core_row["organization_clean"] is None
    assert result.core_row["address_parse_status"] == "CONFLICT"
    conflict_rows = [
        row
        for row in result.evidence_rows
        if row["conflict_flag"] == "BUILDING_ORGANIZATION_ROLE_CONFLICT"
    ]
    assert {row["component"] for row in conflict_rows} == {
        "BUILDING",
        "ORGANIZATION",
    }


@pytest.mark.parametrize("line", ["2024 Fictional Road", "12345 Fictional Road"])
def test_house_candidate_excludes_years_and_postcode_like_numbers(
    tmp_path: Path, line: str
) -> None:
    result = engine(tmp_path).transform(phase02_row(street_address_line_1=line))
    assert not any(
        candidate.component == "HOUSE_NUMBER" for candidate in result.candidates
    )


def test_raw_source_spans_survive_whitespace_nfc_and_multiline(tmp_path: Path) -> None:
    raw = "  Apt.\tCafe\u0301\n"
    result = engine(tmp_path).transform(phase02_row(street_address_line_1=raw))
    unit = next(
        candidate for candidate in result.candidates if candidate.component == "UNIT"
    )
    assert unit.value == "Café"
    span = unit.spans[0]
    assert raw[span.start_character : span.end_character_exclusive] == "Cafe\u0301"
    evidence = next(row for row in result.evidence_rows if row["component"] == "UNIT")
    assert (
        raw[evidence["start_character"] : evidence["end_character_exclusive"]]
        == "Cafe\u0301"
    )


def test_native_non_native_relationships_cover_all_states(tmp_path: Path) -> None:
    scripts = fictional_script_reference(tmp_path)
    assert native_relationship("", ".", scripts) == "BOTH_SEMANTICALLY_MISSING"
    assert native_relationship("", "ABC", scripts) == "NATIVE_ONLY"
    assert native_relationship("ABC", "", scripts) == "NON_NATIVE_ONLY"
    assert native_relationship("ABC", "ABC", scripts) == "EXACT_EQUAL"
    assert native_relationship("Cafe\u0301", "Café", scripts) == "NFC_EQUAL"
    assert native_relationship("ABC", "DEF", scripts) == "SAME_SCRIPT_DIFFERENT"
    assert native_relationship("ABC", "АБВ", scripts) == "DIFFERENT_SCRIPT"
    assert native_relationship("AБ", "DEF", scripts) == "MIXED_OR_UNDETERMINED"


def test_oversized_field_is_separate_from_parse_status_and_safe_fields_survive(
    tmp_path: Path,
) -> None:
    limit = 64
    parser = engine(
        tmp_path,
        config=Phase03Config(
            per_field_freeform_limit_bytes=limit,
            combined_freeform_limit_bytes=256,
        ),
    )
    result = parser.transform(
        phase02_row(
            street_address_line_1="X" * (limit + 1),
            city="Exampleville",
            country_iso_code="XZ",
        )
    )
    assert (
        result.core_row["diagnostic_evaluation_status"] == "PARTIALLY_SKIPPED_OVERSIZED"
    )
    assert result.core_row["locality_clean"] == "Exampleville"
    assert result.core_row["country_clean"] == "XZ"
    assert result.core_row["address_parse_status"] == "INSUFFICIENT"
    assert result.core_row["skipped_oversized_fields"] == ["street_address_line_1"]


def test_all_address_geography_fields_oversized_is_not_evaluated(
    tmp_path: Path,
) -> None:
    limit = 8
    parser = engine(
        tmp_path,
        config=Phase03Config(
            per_field_freeform_limit_bytes=limit,
            combined_freeform_limit_bytes=limit * 8,
        ),
    )
    overrides = {
        field: "X" * (limit + 1)
        for field in (
            "street_address_line_1",
            "street_address_line_2",
            "street_address_line_3",
            "street_address_line_4",
            "street_address_line_1_native",
            "street_address_line_2_native",
            "street_address_line_3_native",
            "street_address_line_4_native",
            "postcode",
            "city",
            "region_in_country",
            "country_iso_code",
        )
    }
    result = parser.transform(phase02_row(**overrides))
    assert result.core_row["diagnostic_evaluation_status"] == "NOT_EVALUATED_OVERSIZED"
    assert result.core_row["address_parse_status"] == "INSUFFICIENT"
    assert len(result.core_row["skipped_oversized_fields"]) == 12


def test_candidate_limit_is_diagnostic_and_deterministic(tmp_path: Path) -> None:
    parser = engine(
        tmp_path,
        config=Phase03Config(max_candidates_per_component=1, max_candidates_per_row=4),
    )
    first = parser.transform(phase02_row(street_address_line_1="Apt 1 Unit 2"))
    second = parser.transform(phase02_row(street_address_line_1="Apt 1 Unit 2"))
    assert "CANDIDATE_LIMIT_EXCEEDED" in first.core_row["address_diagnostic_flags"]
    assert first.core_row == second.core_row
    assert first.evidence_rows == second.evidence_rows


def test_operational_safety_boundaries_are_inclusive_and_combined_limit_is_exact(
    tmp_path: Path,
) -> None:
    field_parser = engine(
        tmp_path,
        config=Phase03Config(
            per_field_freeform_limit_bytes=8,
            combined_freeform_limit_bytes=64,
        ),
    )
    at_field_limit = field_parser.transform(
        phase02_row(street_address_line_1="Apt 1234")
    )
    over_field_limit = field_parser.transform(
        phase02_row(street_address_line_1="Apt 12345")
    )
    assert at_field_limit.core_row["unit_clean"] == "1234"
    assert at_field_limit.core_row["diagnostic_evaluation_status"] == "FULLY_EVALUATED"
    assert over_field_limit.core_row["unit_clean"] is None
    assert (
        over_field_limit.core_row["diagnostic_evaluation_status"]
        == "PARTIALLY_SKIPPED_OVERSIZED"
    )

    combined_parser = engine(
        tmp_path,
        config=Phase03Config(
            per_field_freeform_limit_bytes=100,
            combined_freeform_limit_bytes=8,
        ),
    )
    at_combined_limit = combined_parser.transform(
        phase02_row(street_address_line_1="Apt 1", street_address_line_2="XYZ")
    )
    over_combined_limit = combined_parser.transform(
        phase02_row(street_address_line_1="Apt 1", street_address_line_2="WXYZ")
    )
    assert (
        at_combined_limit.core_row["diagnostic_evaluation_status"] == "FULLY_EVALUATED"
    )
    assert over_combined_limit.core_row["skipped_oversized_fields"] == [
        "street_address_line_2"
    ]


@pytest.mark.parametrize(
    ("component", "expected_flag"),
    [
        ("POSTCODE", "POSTCODE_MULTIPLE_CANDIDATES"),
        ("LOCALITY", "LOCALITY_MULTIPLE_CANDIDATES"),
        ("COUNTRY", "COUNTRY_MULTIPLE_CANDIDATES"),
    ],
)
def test_deterministic_selection_retains_component_conflicts(
    component: str, expected_flag: str
) -> None:
    span = RawSpan("street_address_line_1", 0, 1)
    candidates = [
        Candidate(
            component=component,
            value="A",
            representation="SHARED",
            confidence="HIGH",
            rule_id="FICTIONAL_RULE_A",
            selection_priority=1,
            selectable=True,
            spans=(span,),
            source_fields=("street_address_line_1",),
        ),
        Candidate(
            component=component,
            value="B",
            representation="SHARED",
            confidence="HIGH",
            rule_id="FICTIONAL_RULE_B",
            selection_priority=1,
            selectable=True,
            spans=(span,),
            source_fields=("street_address_line_1",),
        ),
    ]
    selected, conflicts, ambiguous = select_candidates(candidates)
    assert selected == []
    assert conflicts == {expected_flag}
    assert ambiguous


def test_explicit_unit_role_suppresses_same_span_house_candidate(
    tmp_path: Path,
) -> None:
    result = engine(tmp_path).transform(phase02_row(street_address_line_1="Unit 7B"))
    assert result.core_row["unit_clean"] == "7B"
    assert result.core_row["house_number_clean"] is None
    assert not any(
        candidate.component == "HOUSE_NUMBER" for candidate in result.candidates
    )
