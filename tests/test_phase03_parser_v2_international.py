from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import pytest

from safe_geocoding_pipeline.phase03.constants import PARSER_VERSION_V2
from safe_geocoding_pipeline.phase03.config import Phase03Config
from safe_geocoding_pipeline.phase03.engine import Phase03Engine
from safe_geocoding_pipeline.phase03.errors import Phase03Error
from safe_geocoding_pipeline.phase03.rules import load_rule_registry
from safe_geocoding_pipeline.phase03.street_resources import load_street_designators

from phase03_helpers import engine, phase02_row


def _selected(result: Any, component: str) -> list[dict[str, Any]]:
    return [
        row
        for row in result.evidence_rows
        if row["component"] == component and row["selected"] is True
    ]


def test_street_designator_resource_is_versioned_and_multilingual() -> None:
    resource = load_street_designators()
    assert resource.resource_id == "street_designators_v2"
    assert resource.resource_version == "2.0.0"
    assert len(resource.designators) == 56
    assert resource.artifact_sha256 == (
        "0bfbc60f843f8ecf8c3b84cc05e7f342a3da6f5f0f18f1961623566d15dc28cf"
    )
    assert {item.language for item in resource.designators} == {
        "de",
        "en",
        "es",
        "fr",
        "it",
        "nl",
        "pt",
    }


def test_changed_street_reference_binding_fails_closed_at_engine_startup(
    tmp_path: Path,
) -> None:
    source = (
        Path(__file__).parents[1]
        / "src/safe_geocoding_pipeline/phase03/resources/rule_registry_v3.json"
    )
    payload = json.loads(source.read_text(encoding="utf-8"))
    for rule in payload["rules"]:
        parameters = rule["matching_condition"]["parameters"]
        if "street_designator_artifact_sha256" in parameters:
            parameters["street_designator_artifact_sha256"] = "0" * 64
    changed = tmp_path / "changed_registry.json"
    changed.write_text(json.dumps(payload), encoding="utf-8")
    registry = load_rule_registry(changed)
    with pytest.raises(Phase03Error, match="STREET_DESIGNATOR_REFERENCE_MISMATCH"):
        Phase03Engine(
            Phase03Config.for_parser_version(PARSER_VERSION_V2),
            registry,
            implementation_fingerprint=bytes(32),
            execution_scope="DEVELOPMENT",
        )


@pytest.mark.parametrize(
    ("leading", "trailing", "street", "house"),
    [
        ("12 Example Street", "Example Street 12", "Example Street", "12"),
        ("12 Beispielstraße", "Beispielstraße 12", "Beispielstraße", "12"),
        ("12 Beispielweg", "Beispielweg 12", "Beispielweg", "12"),
        ("12 Rue Exemple", "Rue Exemple 12", "Rue Exemple", "12"),
        ("12 Via Roma", "Via Roma 12", "Via Roma", "12"),
        ("12 Calle Ejemplo", "Calle Ejemplo 12", "Calle Ejemplo", "12"),
        ("12 Rua Exemplo", "Rua Exemplo 12", "Rua Exemplo", "12"),
        ("12 Hoofdstraat", "Hoofdstraat 12", "Hoofdstraat", "12"),
        ("12 Hoofdlaan", "Hoofdlaan 12", "Hoofdlaan", "12"),
    ],
)
def test_designator_families_support_both_number_orders(
    tmp_path: Path, leading: str, trailing: str, street: str, house: str
) -> None:
    parser = engine(tmp_path, parser_version=PARSER_VERSION_V2)
    for raw in (leading, trailing):
        result = parser.transform(phase02_row(street_address_line_1=raw))
        assert result.core_row["street_clean"] == street
        assert result.core_row["house_number_clean"] == house
        assert result.core_row["address_conflict_flags"] == []
        assert _selected(result, "STREET")[0]["rule_id"] == (
            "STREET_EXPLICIT_DESIGNATOR_V3"
        )


@pytest.mark.parametrize(
    ("raw", "street"),
    [
        ("Example St. 12", "Example St."),
        ("Example Rd. 12", "Example Rd."),
        ("Example Ave. 12", "Example Ave."),
        ("Example Blvd. 12", "Example Blvd."),
        ("Example Ln. 12", "Example Ln."),
        ("Example Dr. 12", "Example Dr."),
        ("Example Ct. 12", "Example Ct."),
        ("Example Pl. 12", "Example Pl."),
        ("Beispiel Str. 12", "Beispiel Str."),
    ],
)
def test_approved_dotted_designator_abbreviations_preserve_punctuation(
    tmp_path: Path, raw: str, street: str
) -> None:
    result = engine(tmp_path, parser_version=PARSER_VERSION_V2).transform(
        phase02_row(street_address_line_1=raw)
    )
    assert result.core_row["street_clean"] == street
    assert result.core_row["house_number_clean"] == "12"
    evidence = _selected(result, "STREET")
    assert len(evidence) == 1
    row = evidence[0]
    assert row["rule_id"] == "STREET_EXPLICIT_DESIGNATOR_V3"
    assert raw[row["start_character"] : row["end_character_exclusive"]] == street


@pytest.mark.parametrize(
    ("raw", "street", "house"),
    [
        ("12 A Example Street", "Example Street", "12 A"),
        ("Example Street 12-B", "Example Street", "12-B"),
        ("12/3 Example Street", "Example Street", "12/3"),
        ("Example Street 12-3", "Example Street", "12-3"),
        ("12–14 Example Avenue", "Example Avenue", "12–14"),
        ("Example Road 12A", "Example Road", "12A"),
    ],
)
def test_rich_house_grammar_preserves_exact_punctuation_and_spans(
    tmp_path: Path, raw: str, street: str, house: str
) -> None:
    result = engine(tmp_path, parser_version=PARSER_VERSION_V2).transform(
        phase02_row(street_address_line_1=raw)
    )
    assert result.core_row["street_clean"] == street
    assert result.core_row["house_number_clean"] == house
    for component, expected in (("STREET", street), ("HOUSE_NUMBER", house)):
        evidence = _selected(result, component)
        assert len(evidence) == 1
        row = evidence[0]
        assert row["candidate_value"] == expected
        assert raw[row["start_character"] : row["end_character_exclusive"]] == expected


@pytest.mark.parametrize(
    ("raw", "street"),
    [
        ("12 Центральная улица", "Центральная улица"),
        ("شارع المثال 12", "شارع المثال"),
        ("12 Οδός Παραδείγματος", "Οδός Παραδείγματος"),
        ("中央通り 12", "中央通り"),
        ("12 ถนนตัวอย่าง", "ถนนตัวอย่าง"),
        ("12 New Main", "New Main"),
    ],
)
def test_language_light_generic_street_is_bounded_and_unicode_safe(
    tmp_path: Path, raw: str, street: str
) -> None:
    result = engine(tmp_path, parser_version=PARSER_VERSION_V2).transform(
        phase02_row(street_address_line_1=raw)
    )
    assert result.core_row["street_clean"] == street
    assert result.core_row["house_number_clean"] == "12"
    assert _selected(result, "STREET")[0]["rule_id"] == "STREET_GENERIC_SEGMENT_V3"
    assert result.core_row["address_parse_status"] == "PARSED"


@pytest.mark.parametrize(
    "raw",
    [
        "42",
        "12/05 Example Street",
        "2024 Example Road",
        "12345 Example Street",
        "SW1A Example Street",
        "+49 69 1234 5678",
        "50.1109 8.6821",
        "Example 54 GmbH",
        "Studio 54 Example Street",
        "Hotel 12 Example Road",
        "Block 12",
        "#814",
        "Floor 8",
        "Unit 3",
        "PO Box 77",
        "123456789 Example Street",
        "12 14 Example Street",
    ],
)
def test_adversarial_numeric_and_role_forms_do_not_select_house(
    tmp_path: Path, raw: str
) -> None:
    result = engine(tmp_path, parser_version=PARSER_VERSION_V2).transform(
        phase02_row(street_address_line_1=raw, postcode="12345")
    )
    assert result.core_row["house_number_clean"] is None
    assert not _selected(result, "HOUSE_NUMBER")


@pytest.mark.parametrize("postcode", ["1234", "0123", "12-3", "A12", "12 3"])
def test_exact_structured_postcode_claim_prevents_house_selection(
    tmp_path: Path, postcode: str
) -> None:
    raw = f"{postcode} Example Street"
    result = engine(tmp_path, parser_version=PARSER_VERSION_V2).transform(
        phase02_row(street_address_line_1=raw, postcode=postcode)
    )
    assert result.core_row["postcode_clean"] == postcode
    assert result.core_row["house_number_clean"] is None
    assert not _selected(result, "HOUSE_NUMBER")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Flat No. 42", "42"),
        ("Flat 814B", "814B"),
        ("Apt #5", "5"),
        ("Apt. 814", "814"),
        ("Apartment No 5B", "5B"),
        ("Unit 3", "3"),
        ("Suite No. 700", "700"),
        ("Ste 814", "814"),
        ("Ste. 814", "814"),
        ("Room #21", "21"),
        ("Rm. 21", "21"),
    ],
)
def test_unit_optional_number_markers_are_bounded(
    tmp_path: Path, raw: str, expected: str
) -> None:
    result = engine(tmp_path, parser_version=PARSER_VERSION_V2).transform(
        phase02_row(street_address_line_1=raw)
    )
    assert result.core_row["unit_clean"] == expected
    assert result.core_row["house_number_clean"] is None
    evidence = _selected(result, "UNIT")
    assert len(evidence) == 1
    assert evidence[0]["candidate_value"] == expected
    assert raw[
        evidence[0]["start_character"] : evidence[0]["end_character_exclusive"]
    ] == raw


def test_same_line_composition_assigns_nonoverlapping_segments(tmp_path: Path) -> None:
    raw = (
        "Example Research GmbH; Example Tower; Example Street 12; "
        "Unit 7; Floor 8"
    )
    result = engine(tmp_path, parser_version=PARSER_VERSION_V2).transform(
        phase02_row(street_address_line_1=raw)
    )
    core = result.core_row
    assert (
        core["organization_clean"],
        core["building_clean"],
        core["street_clean"],
        core["house_number_clean"],
        core["unit_clean"],
        core["floor_clean"],
    ) == (
        "Example Research GmbH",
        "Example Tower",
        "Example Street",
        "12",
        "7",
        "8",
    )
    assert core["address_conflict_flags"] == []
    assert core["address_parse_status"] == "PARSED"
    assert "UNASSIGNED_CONTENT_PRESENT" not in core["address_diagnostic_flags"]


def test_unit_floor_same_line_and_safe_hash_identifier(tmp_path: Path) -> None:
    raw = "Unit #814, 8th Fl."
    result = engine(tmp_path, parser_version=PARSER_VERSION_V2).transform(
        phase02_row(street_address_line_1=raw)
    )
    assert result.core_row["unit_clean"] == "814"
    assert result.core_row["floor_clean"] == "8"
    assert result.core_row["house_number_clean"] is None
    assert result.core_row["address_conflict_flags"] == []


@pytest.mark.parametrize(
    "raw",
    [
        "Floor 8",
        "Fl 8",
        "Fl. 8",
        "Level 8",
        "Lvl 8",
        "8th Floor",
        "8th Fl",
        "8th Fl.",
        "8/F",
        "8F",
    ],
)
def test_floor_form_matrix_uses_digit_scalar_and_full_evidence(
    tmp_path: Path, raw: str
) -> None:
    result = engine(tmp_path, parser_version=PARSER_VERSION_V2).transform(
        phase02_row(street_address_line_1=raw)
    )
    assert result.core_row["floor_clean"] == "8"
    assert result.core_row["house_number_clean"] is None
    evidence = _selected(result, "FLOOR")
    assert len(evidence) == 1
    row = evidence[0]
    assert raw[row["start_character"] : row["end_character_exclusive"]] == raw


@pytest.mark.parametrize(
    "raw",
    [
        "Example Building",
        "Example Bldg",
        "Example Bldg.",
        "Example Tower",
        "Example Centre",
        "Example Center",
        "Example Industrial Centre",
        "Example Complex",
        "Example Plaza",
    ],
)
def test_building_marker_matrix_is_medium_and_bounded(tmp_path: Path, raw: str) -> None:
    result = engine(tmp_path, parser_version=PARSER_VERSION_V2).transform(
        phase02_row(street_address_line_1=raw)
    )
    assert result.core_row["building_clean"] == raw
    evidence = _selected(result, "BUILDING")
    assert len(evidence) == 1
    assert evidence[0]["confidence"] == "MEDIUM"


@pytest.mark.parametrize(
    "raw",
    [
        "Research Center Road 12",
        "Central Plaza Street 12",
        "Tower Road 12",
        "Park Avenue 12",
        "Block Street 12",
    ],
)
def test_ambiguous_building_words_do_not_destroy_street_role(
    tmp_path: Path, raw: str
) -> None:
    result = engine(tmp_path, parser_version=PARSER_VERSION_V2).transform(
        phase02_row(street_address_line_1=raw)
    )
    assert result.core_row["street_clean"] is not None
    assert result.core_row["house_number_clean"] == "12"
    assert result.core_row["building_clean"] is None


def test_punctuation_and_accented_street_text_are_preserved(tmp_path: Path) -> None:
    raw = "12 Rue de l'École-Saint-Joseph"
    result = engine(tmp_path, parser_version=PARSER_VERSION_V2).transform(
        phase02_row(street_address_line_1=raw)
    )
    assert result.core_row["street_clean"] == "Rue de l'École-Saint-Joseph"
    assert result.core_row["house_number_clean"] == "12"


def test_residual_evidence_contains_only_unassigned_material_span(tmp_path: Path) -> None:
    raw = "Example Street 12, unexplained material"
    result = engine(tmp_path, parser_version=PARSER_VERSION_V2).transform(
        phase02_row(street_address_line_1=raw)
    )
    residual = [
        row
        for row in result.evidence_rows
        if row["diagnostic_flag"] == "UNASSIGNED_CONTENT_PRESENT"
    ]
    assert len(residual) == 1
    row = residual[0]
    assert raw[row["start_character"] : row["end_character_exclusive"]] == (
        "unexplained material"
    )
    assert result.core_row["address_parse_status"] == "PARTIAL"


def test_exact_native_agreement_and_strong_house_conflict_are_deterministic(
    tmp_path: Path,
) -> None:
    parser = engine(tmp_path, parser_version=PARSER_VERSION_V2)
    agreed = parser.transform(
        phase02_row(
            street_address_line_1="12 Example Street",
            street_address_line_1_native="12 Example Street",
        )
    )
    assert agreed.core_row["address_conflict_flags"] == []
    assert agreed.core_row["native_non_native_relationships"][0]["relationship"] == (
        "EXACT_EQUAL"
    )
    conflicted = parser.transform(
        phase02_row(
            street_address_line_1="12 Example Street",
            street_address_line_1_native="14 Example Street",
        )
    )
    assert "NATIVE_NON_NATIVE_HOUSE_NUMBER_CONFLICT" in conflicted.core_row[
        "address_conflict_flags"
    ]
    assert conflicted.core_row["house_number_clean"] is None
    assert conflicted.core_row["house_number_native_clean"] is None


def test_nfc_equal_representations_reconcile_without_confidence_elevation(
    tmp_path: Path,
) -> None:
    result = engine(tmp_path, parser_version=PARSER_VERSION_V2).transform(
        phase02_row(
            street_address_line_1="12 Rue de l'École",
            street_address_line_1_native="12 Rue de l'E\u0301cole",
        )
    )
    core = result.core_row
    assert core["street_clean"] == "Rue de l'École"
    assert core["street_native_clean"] is None
    assert core["native_non_native_relationships"][0]["relationship"] == "NFC_EQUAL"
    street_provenance = next(
        item
        for item in core["selected_component_provenance"]
        if item["component"] == "STREET"
    )
    assert street_provenance["confidence"] == "HIGH"
    assert street_provenance["source_fields"] == [
        "street_address_line_1",
        "street_address_line_1_native",
    ]


def test_building_organization_and_street_role_arbitration(tmp_path: Path) -> None:
    parser = engine(tmp_path, parser_version=PARSER_VERSION_V2)
    street = parser.transform(phase02_row(street_address_line_1="Tower Road 12"))
    assert street.core_row["street_clean"] == "Tower Road"
    assert street.core_row["building_clean"] is None
    organization = parser.transform(
        phase02_row(street_address_line_1="Building Society Ltd")
    )
    assert organization.core_row["organization_clean"] == "Building Society Ltd"
    assert organization.core_row["building_clean"] is None
    punctuated = parser.transform(
        phase02_row(street_address_line_1="Example Research Co., Ltd.")
    )
    assert punctuated.core_row["organization_clean"] == "Example Research Co., Ltd."


def test_generated_population_is_deterministic_and_within_candidate_caps(
    tmp_path: Path,
) -> None:
    parser = engine(tmp_path, parser_version=PARSER_VERSION_V2)
    templates = (
        "{number} Example Street; Unit {unit}",
        "Rue Exemple {number}; Floor {floor}",
        "{number} Центральная улица; Example Tower",
        "Via Roma {number}; Example Research GmbH",
    )
    first: list[str] = []
    second: list[str] = []
    for ordinal in range(200):
        raw = templates[ordinal % len(templates)].format(
            number=(ordinal % 98) + 1,
            unit=(ordinal % 20) + 1,
            floor=(ordinal % 40) + 1,
        )
        row = phase02_row(street_address_line_1=raw)
        for output in (first, second):
            transformed = parser.transform(row)
            assert len(transformed.candidates) <= 64
            output.append(
                hashlib.sha256(
                    repr(
                        (
                            transformed.core_row["street_clean"],
                            transformed.core_row["house_number_clean"],
                            transformed.core_row["unit_clean"],
                            transformed.core_row["floor_clean"],
                            transformed.core_row["building_clean"],
                            transformed.core_row["organization_clean"],
                            transformed.core_row["address_conflict_flags"],
                            transformed.evidence_rows,
                        )
                    ).encode()
                ).hexdigest()
            )
    assert first == second


def test_adversarial_near_limit_input_has_bounded_runtime(tmp_path: Path) -> None:
    parser = engine(tmp_path, parser_version=PARSER_VERSION_V2)
    raw = ("12-345/6789 " * 5_000)[:65_000]
    started = time.perf_counter()
    result = parser.transform(phase02_row(street_address_line_1=raw))
    elapsed = time.perf_counter() - started
    assert elapsed < 3.0
    assert result.core_row["house_number_clean"] is None
    assert len(result.candidates) <= 64


@pytest.mark.parametrize(
    "raw",
    [
        "9" * 60_000,
        ".-/#" * 5_000,
        ("Unit " * 5_000).strip(),
        "界" * 30_000,
        (" " * 60_000) + "42",
    ],
)
def test_long_synthetic_boundary_classes_remain_bounded(
    tmp_path: Path, raw: str
) -> None:
    parser = engine(tmp_path, parser_version=PARSER_VERSION_V2)
    started = time.perf_counter()
    result = parser.transform(phase02_row(street_address_line_1=raw))
    assert time.perf_counter() - started < 3.0
    assert len(result.candidates) <= 64
    assert result.core_row["street_clean"] is None
    assert result.core_row["house_number_clean"] is None
