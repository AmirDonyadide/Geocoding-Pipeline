from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from safe_geocoding_pipeline.phase03.config import Phase03Config
from safe_geocoding_pipeline.phase03.cli import build_parser
from safe_geocoding_pipeline.phase03.constants import (
    EVIDENCE_COLUMNS,
    PARSER_VERSION_V1,
    PARSER_VERSION_V2,
    RULE_REGISTRY_VERSION_V2,
    RULE_REGISTRY_VERSION_V3,
)
from safe_geocoding_pipeline.phase03.engine import Phase03Engine
from safe_geocoding_pipeline.phase03.references import load_production_references
from safe_geocoding_pipeline.phase03.rules import load_rule_registry
from safe_geocoding_pipeline.phase03.semantic import core_digest, evidence_digest
from safe_geocoding_pipeline.phase03.validation import (
    validate_core_evidence_relationship,
)

from phase03_helpers import engine, phase02_row


def _selected_evidence(
    result: Any, component: str, *, source_field: str = "street_address_line_1"
) -> dict[str, Any]:
    rows = [
        row
        for row in result.evidence_rows
        if row["component"] == component
        and row["source_field"] == source_field
        and row["selected"] is True
    ]
    assert len(rows) == 1
    return cast(dict[str, Any], rows[0])


def _assert_selected_span(
    result: Any,
    *,
    component: str,
    raw: str,
    expected_value: str,
    expected_rule: str,
    expected_source_text: str | None = None,
    source_field: str = "street_address_line_1",
) -> None:
    evidence = _selected_evidence(result, component, source_field=source_field)
    assert evidence["candidate_value"] == expected_value
    assert evidence["confidence"] in {"HIGH", "MEDIUM"}
    assert evidence["rule_id"] == expected_rule
    assert raw[evidence["start_character"] : evidence["end_character_exclusive"]] == (
        expected_source_text if expected_source_text is not None else expected_value
    )


def test_v2_is_explicit_and_v1_registry_remains_frozen() -> None:
    v1 = load_rule_registry(registry_version=RULE_REGISTRY_VERSION_V2)
    v2 = load_rule_registry(registry_version=RULE_REGISTRY_VERSION_V3)
    assert Phase03Config().parser_version == PARSER_VERSION_V1
    assert Phase03Config().rule_registry_version == RULE_REGISTRY_VERSION_V2
    assert Phase03Config.for_parser_version(PARSER_VERSION_V2).rule_registry_version == (
        RULE_REGISTRY_VERSION_V3
    )
    assert v1.fingerprint == (
        "d1448859f8436dbe466cab81aee926ab6851b294f5ec664491840bac84627fd5"
    )
    assert v2.fingerprint == (
        "a2aadae857b7d4bf7262bd37e6dacf58aae220e00b402ca971c51cea320d6f55"
    )
    assert v1.schema_version == "phase03_rule_registry_schema_v2"
    assert v2.schema_version == "phase03_rule_registry_schema_v3"
    assert len(v1.rules) == 12
    assert len(v2.rules) == 16
    assert all(
        rule.intended_positive_behavior and rule.principal_negative_boundaries
        for rule in v2.rules
    )
    assert all(
        not rule.intended_positive_behavior and not rule.principal_negative_boundaries
        for rule in v1.rules
    )
    assert Phase03Config.for_parser_version(
        PARSER_VERSION_V2
    ).configuration_fingerprint().hex() == (
        "75911fb4d202eff0af92bc805aa0cfe2844e25d72e0a2e322d5de61fd420274c"
    )


def test_v2_production_reference_effective_fingerprint_is_frozen() -> None:
    config = Phase03Config.for_parser_version(PARSER_VERSION_V2)
    registry = load_rule_registry(registry_version=config.rule_registry_version)
    country, scripts = load_production_references(
        expected_country_reference_id=config.country_reference_version,
        expected_unicode_reference_id=config.unicode_reference_version,
    )
    parser = Phase03Engine(
        config,
        registry,
        country_reference=country,
        script_reference=scripts,
        implementation_fingerprint=bytes(32),
        execution_scope="DEVELOPMENT",
    )
    assert parser.configuration_fingerprint.hex() == (
        "1f3496947da779e3b31ae6d8925c5ec75ea9d7714904846d9fca9194bfd28c2b"
    )


@pytest.mark.parametrize(
    ("raw", "street", "house"),
    [
        ("12 Example Street", "Example Street", "12"),
        ("Example Street 12", "Example Street", "12"),
        ("12A Example Road", "Example Road", "12A"),
        ("Example Road 12A", "Example Road", "12A"),
        ("12-14 Example Avenue", "Example Avenue", "12-14"),
        ("12/3 Example Street", "Example Street", "12/3"),
    ],
)
def test_v2_street_and_house_number_forms_have_exact_evidence(
    tmp_path: Path, raw: str, street: str, house: str
) -> None:
    result = engine(tmp_path, parser_version=PARSER_VERSION_V2).transform(
        phase02_row(street_address_line_1=raw)
    )
    assert result.core_row["street_clean"] == street
    assert result.core_row["house_number_clean"] == house
    assert result.core_row["address_parse_status"] == "PARSED"
    assert "UNASSIGNED_CONTENT_PRESENT" not in result.core_row[
        "address_diagnostic_flags"
    ]
    _assert_selected_span(
        result,
        component="STREET",
        raw=raw,
        expected_value=street,
        expected_rule="STREET_EXPLICIT_DESIGNATOR_V3",
    )
    _assert_selected_span(
        result,
        component="HOUSE_NUMBER",
        raw=raw,
        expected_value=house,
        expected_rule="HOUSE_NUMBER_EXPLICIT_STREET_V3",
    )


def test_v2_clear_street_without_house_is_selected(tmp_path: Path) -> None:
    raw = "Example Street"
    result = engine(tmp_path, parser_version=PARSER_VERSION_V2).transform(
        phase02_row(street_address_line_1=raw)
    )
    assert result.core_row["street_clean"] == raw
    assert result.core_row["house_number_clean"] is None
    _assert_selected_span(
        result,
        component="STREET",
        raw=raw,
        expected_value=raw,
        expected_rule="STREET_EXPLICIT_DESIGNATOR_V3",
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Flat 42", "42"),
        ("Flat 42B", "42B"),
        ("Apt 5", "5"),
        ("Apartment 5", "5"),
        ("Unit 3", "3"),
        ("Suite 700", "700"),
        ("Room 21", "21"),
        ("Rm 21", "21"),
    ],
)
def test_v2_explicit_unit_markers_select_identifier(
    tmp_path: Path, raw: str, expected: str
) -> None:
    result = engine(tmp_path, parser_version=PARSER_VERSION_V2).transform(
        phase02_row(street_address_line_1=raw)
    )
    assert result.core_row["unit_clean"] == expected
    assert result.core_row["house_number_clean"] is None
    _assert_selected_span(
        result,
        component="UNIT",
        raw=raw,
        expected_value=expected,
        expected_rule="UNIT_EXPLICIT_SEGMENT_V3",
        expected_source_text=raw,
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("8/F", "8"),
        ("8F", "8"),
        ("Floor 8", "8"),
        ("8th Floor", "8"),
        ("Level 8", "8"),
    ],
)
def test_v2_explicit_floor_forms_are_not_house_numbers(
    tmp_path: Path, raw: str, expected: str
) -> None:
    result = engine(tmp_path, parser_version=PARSER_VERSION_V2).transform(
        phase02_row(street_address_line_1=raw)
    )
    assert result.core_row["floor_clean"] == expected
    assert result.core_row["house_number_clean"] is None
    _assert_selected_span(
        result,
        component="FLOOR",
        raw=raw,
        expected_value=expected,
        expected_rule="FLOOR_EXPLICIT_SEGMENT_V3",
        expected_source_text=raw,
    )


@pytest.mark.parametrize(
    "raw",
    [
        "Example Industrial Centre",
        "Example Industrial Center",
        "Example Building",
        "Example Tower",
        "Example Block",
        "Example Complex",
        "Example Plaza",
    ],
)
def test_v2_clear_building_segments_are_selected(tmp_path: Path, raw: str) -> None:
    result = engine(tmp_path, parser_version=PARSER_VERSION_V2).transform(
        phase02_row(street_address_line_1=raw)
    )
    assert result.core_row["building_clean"] == raw
    assert result.core_row["organization_clean"] is None
    _assert_selected_span(
        result,
        component="BUILDING",
        raw=raw,
        expected_value=raw,
        expected_rule="BUILDING_EXPLICIT_SEGMENT_V3",
    )


def test_v2_company_building_and_street_on_separate_lines_remain_separate(
    tmp_path: Path,
) -> None:
    organization = "Example Research GmbH"
    building = "Example Industrial Centre"
    street = "12 Example Street"
    result = engine(tmp_path, parser_version=PARSER_VERSION_V2).transform(
        phase02_row(
            street_address_line_1=organization,
            street_address_line_2=building,
            street_address_line_3=street,
        )
    )
    core = result.core_row
    assert core["organization_clean"] == organization
    assert core["building_clean"] == building
    assert core["street_clean"] == "Example Street"
    assert core["house_number_clean"] == "12"
    assert core["address_conflict_flags"] == []
    assert core["address_parse_status"] == "PARSED"
    for component, raw, field, rule in (
        ("ORGANIZATION", organization, "street_address_line_1", "ORGANIZATION_LEGAL_FORM_V3"),
        ("BUILDING", building, "street_address_line_2", "BUILDING_EXPLICIT_SEGMENT_V3"),
    ):
        evidence = _selected_evidence(result, component, source_field=field)
        assert evidence["rule_id"] == rule
        assert evidence["candidate_value"] == raw
        assert evidence["start_character"] == 0
        assert evidence["end_character_exclusive"] == len(raw)


def test_v2_legal_form_wins_over_ambiguous_building_marker(
    tmp_path: Path,
) -> None:
    result = engine(tmp_path, parser_version=PARSER_VERSION_V2).transform(
        phase02_row(street_address_line_1="Building Example GmbH")
    )
    core = result.core_row
    assert core["building_clean"] is None
    assert core["organization_clean"] == "Building Example GmbH"
    assert core["address_parse_status"] == "PARSED"
    assert core["address_conflict_flags"] == []


def test_v2_identical_native_non_native_components_do_not_conflict(
    tmp_path: Path,
) -> None:
    raw = "12 Example Street"
    parser = engine(tmp_path, parser_version=PARSER_VERSION_V2)
    input_row = phase02_row(
        street_address_line_1=raw,
        street_address_line_1_native=raw,
    )
    result = parser.transform(input_row)
    repeated = parser.transform(input_row)
    core = result.core_row
    assert core["street_clean"] == "Example Street"
    assert core["house_number_clean"] == "12"
    assert core["street_native_clean"] is None
    assert core["house_number_native_clean"] is None
    assert "NATIVE_NON_NATIVE_HOUSE_NUMBER_CONFLICT" not in core[
        "address_conflict_flags"
    ]
    assert "UNASSIGNED_CONTENT_PRESENT" not in core["address_diagnostic_flags"]
    assert core["native_non_native_relationships"][0]["relationship"] == "EXACT_EQUAL"
    provenance = {
        item["component"]: item for item in core["selected_component_provenance"]
    }
    assert provenance["STREET"]["source_fields"] == [
        "street_address_line_1",
        "street_address_line_1_native",
    ]
    assert provenance["HOUSE_NUMBER"]["source_fields"] == [
        "street_address_line_1",
        "street_address_line_1_native",
    ]
    selected_evidence = {
        (row["component"], row["representation"], row["source_field"])
        for row in result.evidence_rows
        if row["selected"]
    }
    assert selected_evidence == {
        ("STREET", "NON_NATIVE", "street_address_line_1"),
        ("HOUSE_NUMBER", "NON_NATIVE", "street_address_line_1"),
    }
    folded_native_evidence = [
        row
        for row in result.evidence_rows
        if row["component"] in {"STREET", "HOUSE_NUMBER"}
        and row["representation"] == "NATIVE"
        and row["rule_id"]
        in {"STREET_EXPLICIT_DESIGNATOR_V3", "HOUSE_NUMBER_EXPLICIT_STREET_V3"}
    ]
    assert len(folded_native_evidence) == 2
    assert all(row["selected"] is False for row in folded_native_evidence)
    assert all(
        row["evidence_kind"] == "UNSELECTED_CANDIDATE"
        for row in folded_native_evidence
    )
    assert not any(
        row["evidence_kind"] == "UNASSIGNED_MATERIAL_CONTENT"
        and row["source_field"] == "street_address_line_1_native"
        for row in result.evidence_rows
    )
    assert all(tuple(row) == EVIDENCE_COLUMNS for row in result.evidence_rows)
    assert result.core_row == repeated.core_row
    assert result.evidence_rows == repeated.evidence_rows
    assert core_digest([core], "phase03_component_core_v1").hex() == (
        "dfd3b8242d6dfb2aac719578f91a69a4dd5ae9bd8551727af484edba99c7a795"
    )
    assert evidence_digest(
        result.evidence_rows, "phase03_component_evidence_v1"
    ).hex() == "2e32fc3e41798d5d8bf3215b408cdb3825a8c8ccf01c06ba6d1cfed1cecfe6db"
    validate_core_evidence_relationship([core], result.evidence_rows)


def test_v2_conflicting_native_non_native_house_numbers_fail_closed(
    tmp_path: Path,
) -> None:
    result = engine(tmp_path, parser_version=PARSER_VERSION_V2).transform(
        phase02_row(
            street_address_line_1="12 Example Street",
            street_address_line_1_native="14 Example Street",
        )
    )
    core = result.core_row
    assert core["house_number_clean"] is None
    assert core["house_number_native_clean"] is None
    assert "NATIVE_NON_NATIVE_HOUSE_NUMBER_CONFLICT" in core[
        "address_conflict_flags"
    ]
    assert core["address_parse_status"] == "CONFLICT"
    conflict_evidence = [
        row
        for row in result.evidence_rows
        if row["conflict_flag"] == "NATIVE_NON_NATIVE_HOUSE_NUMBER_CONFLICT"
    ]
    assert {row["source_field"] for row in conflict_evidence} == {
        "street_address_line_1",
        "street_address_line_1_native",
    }
    validate_core_evidence_relationship([core], result.evidence_rows)


def test_v1_native_non_native_selection_and_evidence_remain_unchanged(
    tmp_path: Path,
) -> None:
    result = engine(tmp_path, parser_version=PARSER_VERSION_V1).transform(
        phase02_row(
            street_address_line_1="Apt 7",
            street_address_line_1_native="Apt 7",
        )
    )
    core = result.core_row
    assert core["unit_clean"] == "7"
    assert core["unit_native_clean"] == "7"
    assert {
        (row["component"], row["representation"], row["source_field"])
        for row in result.evidence_rows
        if row["selected"]
    } == {
        ("UNIT", "NON_NATIVE", "street_address_line_1"),
        ("UNIT", "NATIVE", "street_address_line_1_native"),
    }
    assert core_digest([core], "phase03_component_core_v1").hex() == (
        "dbcf4f04d11600f370053b8c25c0f6ee5050ce227dfc0bd1dd3852c8bdcdc17f"
    )
    assert evidence_digest(
        result.evidence_rows, "phase03_component_evidence_v1"
    ).hex() == "31e84b4b95558ae9c22320a4068fd697e2dcdadb191b1456ce1cc059ccc7b6c2"
    validate_core_evidence_relationship([core], result.evidence_rows)


def test_v2_po_box_behavior_is_unchanged(tmp_path: Path) -> None:
    raw = "PO Box 77"
    result = engine(tmp_path, parser_version=PARSER_VERSION_V2).transform(
        phase02_row(street_address_line_1=raw)
    )
    assert result.core_row["is_po_box"] is True
    assert result.core_row["probable_non_physical_address"] is True
    assert result.core_row["street_clean"] is None
    assert result.core_row["house_number_clean"] is None
    evidence = _selected_evidence(result, "PO_BOX")
    assert evidence["rule_id"] == "PO_BOX_MARKER_EN_V1"
    assert raw[evidence["start_character"] : evidence["end_character_exclusive"]] == raw


@pytest.mark.parametrize(
    "raw",
    [
        "42",
        "12345 Example Street",
        "12/05 Example Street",
        "12.5 Example Street",
        "2024 Example Road",
        "Studio 54 Example Street",
        "12345A Example Street",
        "SW1A Example Street",
    ],
)
def test_v2_house_number_negative_boundaries_remain_unresolved(
    tmp_path: Path, raw: str
) -> None:
    result = engine(tmp_path, parser_version=PARSER_VERSION_V2).transform(
        phase02_row(street_address_line_1=raw, postcode="12345")
    )
    assert result.core_row["house_number_clean"] is None
    assert not any(
        row["component"] == "HOUSE_NUMBER" and row["selected"]
        for row in result.evidence_rows
    )


def test_v2_explicit_unit_and_floor_values_are_not_stolen_as_house_numbers(
    tmp_path: Path,
) -> None:
    parser = engine(tmp_path, parser_version=PARSER_VERSION_V2)
    unit = parser.transform(phase02_row(street_address_line_1="Unit 3"))
    floor = parser.transform(phase02_row(street_address_line_1="Floor 8"))
    assert unit.core_row["unit_clean"] == "3"
    assert unit.core_row["house_number_clean"] is None
    assert floor.core_row["floor_clean"] == "8"
    assert floor.core_row["house_number_clean"] is None


def test_v2_numeric_organization_line_is_not_a_house_number(tmp_path: Path) -> None:
    raw = "Example 54 GmbH"
    result = engine(tmp_path, parser_version=PARSER_VERSION_V2).transform(
        phase02_row(street_address_line_1=raw)
    )
    assert result.core_row["organization_clean"] == raw
    assert result.core_row["house_number_clean"] is None


def test_v2_oversized_safety_contract_is_unchanged(tmp_path: Path) -> None:
    config = Phase03Config.for_parser_version(PARSER_VERSION_V2)
    config = replace(
        config,
        per_field_freeform_limit_bytes=64,
        combined_freeform_limit_bytes=256,
    )
    result = engine(
        tmp_path,
        config=config,
        parser_version=PARSER_VERSION_V2,
    ).transform(
        phase02_row(
            street_address_line_1="X" * 65,
            street_address_line_2="12 Example Street",
        )
    )
    assert result.core_row["diagnostic_evaluation_status"] == (
        "PARTIALLY_SKIPPED_OVERSIZED"
    )
    assert result.core_row["skipped_oversized_fields"] == ["street_address_line_1"]
    assert result.core_row["street_clean"] == "Example Street"
    assert result.core_row["house_number_clean"] == "12"
    assert result.core_row["address_parse_status"] == "PARTIAL"


def test_v1_and_v2_semantics_and_fingerprints_are_distinct(tmp_path: Path) -> None:
    row = phase02_row(street_address_line_1="12 Example Street")
    v1 = engine(tmp_path, parser_version=PARSER_VERSION_V1)
    v2 = engine(tmp_path, parser_version=PARSER_VERSION_V2)
    old = v1.transform(row)
    revised = v2.transform(row)
    assert old.core_row["street_clean"] is None
    assert old.core_row["house_number_clean"] is None
    assert revised.core_row["street_clean"] == "Example Street"
    assert revised.core_row["house_number_clean"] == "12"
    assert old.core_row["parser_version"] == PARSER_VERSION_V1
    assert revised.core_row["parser_version"] == PARSER_VERSION_V2
    assert old.core_row["rule_registry_version"] == RULE_REGISTRY_VERSION_V2
    assert revised.core_row["rule_registry_version"] == RULE_REGISTRY_VERSION_V3
    assert v1.configuration_fingerprint != v2.configuration_fingerprint


def test_v2_shadow_house_evidence_never_becomes_selected(tmp_path: Path) -> None:
    result = engine(tmp_path, parser_version=PARSER_VERSION_V2).transform(
        phase02_row(street_address_line_1="12 Example Street")
    )
    shadow = [
        row
        for row in result.evidence_rows
        if row["rule_id"] == "HOUSE_NUMBER_EDGE_CANDIDATE_V1"
    ]
    assert shadow
    assert all(row["selected"] is False for row in shadow)


def test_parser_and_registry_versions_are_a_closed_pair() -> None:
    with pytest.raises(ValueError, match="incompatible"):
        Phase03Config(
            parser_version=PARSER_VERSION_V2,
            rule_registry_version=RULE_REGISTRY_VERSION_V2,
        ).validate()


def test_development_transform_requires_explicit_v2_opt_in() -> None:
    parser = build_parser()
    common = [
        "development-transform",
        "--input-development-payload",
        "payload.parquet",
        "--development-identities",
        "development.identities.bin",
        "--output-directory",
        "output",
        "--git-commit",
        "deadbeef",
    ]
    assert parser.parse_args(common).parser_version == PARSER_VERSION_V1
    assert parser.parse_args(
        [*common, "--parser-version", PARSER_VERSION_V2]
    ).parser_version == PARSER_VERSION_V2


def test_goethe_v2_workflow_reuses_development_and_preserves_locked_firewall() -> None:
    script = (
        Path(__file__).parents[1]
        / "cluster/goethe_nhr/phase03_development_parser_v2.sbatch"
    ).read_text(encoding="utf-8")
    assert "#SBATCH --cpus-per-task=4" in script
    assert "#SBATCH --mem=16G" in script
    assert "#SBATCH --time=02:00:00" in script
    assert "development_iterations/.in_progress" not in script
    assert "development_iterations" in script
    assert 'readonly DATA_ROOT="/work/footprint/donyadidegan/safe_geocoding_pipeline"' in script
    assert "PHASE03_INTEGRATION_ROOT" in script
    assert "PHASE03_SOURCE_RUN_ROOT" in script
    assert "PARSER_V2_INTEGRATION_WORKTREE_NOT_DETACHED" in script
    assert "PARSER_V2_SBATCH_SOURCE_MISMATCH" in script
    assert 'git -C "${INTEGRATION_ROOT}" rev-parse HEAD' in script
    assert 'export PYTHONPATH="${INTEGRATION_ROOT}/src"' in script
    assert "PHASE03_DEVELOPMENT_PAYLOAD" in script
    assert "PHASE03_DEVELOPMENT_IDENTITIES" in script
    assert "PARSER_V2_REQUIRED_INPUT_NOT_READABLE" in script
    assert "PARSER_V2_LOCKED_PATH_PROHIBITED" in script
    assert "PARSER_V2_OUTPUT_UNDER_SOURCE_RUN_ROOT" in script
    assert 'resolved_input="$(realpath -e -- "${input}")"' in script
    assert "--parser-version conservative_address_parser_v2" in script
    assert "a2aadae857b7d4bf7262bd37e6dacf58aae220e00b402ca971c51cea320d6f55" in script
    assert "0bfbc60f843f8ecf8c3b84cc05e7f342a3da6f5f0f18f1961623566d15dc28cf" in script
    assert "validate-production-references" in script
    assert "development-compare-parsers" in script
    assert "development-review-sample" in script
    assert "pilot-profile" not in script
    assert "pilot-select" not in script
    assert "pilot-materialize-development" not in script
    assert "PHASE03_LOCKED" not in script
    assert "locked_payload_rows_read\": 0" in script


def test_goethe_v2_documented_inputs_use_repaired_read_only_artifacts() -> None:
    documentation = (
        Path(__file__).parents[1] / "docs/PHASE03_PARSER_V2.md"
    ).read_text(encoding="utf-8")
    assert (
        "${PHASE03_SOURCE_RUN_ROOT}/development/repair_validation_f9699cbc/"
        "core/development.parquet"
    ) in documentation
    assert (
        "${PHASE03_SOURCE_RUN_ROOT}/development/"
        "state_reconstruction_1748775_f9699cbc/candidate_state.sqlite3"
    ) in documentation
    assert "worktree add --detach" in documentation
    assert (
        '"${PHASE03_INTEGRATION_ROOT}/cluster/goethe_nhr/'
        'phase03_development_parser_v2.sbatch"'
    ) in documentation
