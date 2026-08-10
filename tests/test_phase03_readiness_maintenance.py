from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from safe_geocoding_pipeline.phase03.constants import (
    MANUAL_REVIEW_LABEL_SCHEMA_VERSION,
    MANUAL_REVIEW_REASON_CODES_VERSION,
    RULE_EXECUTION_DISPOSITIONS,
)
from safe_geocoding_pipeline.phase03.errors import Phase03Error
from safe_geocoding_pipeline.phase03.review import (
    MANUAL_REVIEW_REASON_CODE_DEFINITIONS_V1,
    MANUAL_REVIEW_REASON_CODES_V1,
    canonicalize_manual_review_reason_codes,
    manual_review_schema,
    validate_portable_review_row,
)
from safe_geocoding_pipeline.phase03.rules import load_rule_registry

from phase03_helpers import engine, phase02_row

_REGISTRY_PATH = Path(
    "src/safe_geocoding_pipeline/phase03/resources/rule_registry_v2.json"
)
_HOUSE_RULE_ID = "HOUSE_NUMBER_EDGE_CANDIDATE_V1"


def _portable_review_row(reason_codes: list[str]) -> dict[str, Any]:
    row: dict[str, Any] = {field.name: None for field in manual_review_schema()}
    row.update(
        {
            "hashed_review_id": "a" * 64,
            "pilot_version": "fictional_pilot_v1",
            "sample_partition": "DEVELOPMENT",
            "reviewer_id": "reviewer-1",
            "review_round": 1,
            "is_independent_review": True,
            "reason_codes": reason_codes,
            "reason_codes_version": MANUAL_REVIEW_REASON_CODES_VERSION,
            "label_schema_version": MANUAL_REVIEW_LABEL_SCHEMA_VERSION,
        }
    )
    return row


def test_house_rule_is_explicitly_development_shadow_only() -> None:
    registry = load_rule_registry()
    house = next(rule for rule in registry.rules if rule.rule_id == _HOUSE_RULE_ID)
    assert house.execution_disposition == "DEVELOPMENT_SHADOW_ONLY"
    assert house.development_shadow_only
    assert not house.selectable
    assert tuple(RULE_EXECUTION_DISPOSITIONS) == (
        "AUTHORITATIVE_SELECTABLE",
        "AUTHORITATIVE_CANDIDATE_ONLY",
        "AUTHORITATIVE_DIAGNOSTIC_ONLY",
        "DEVELOPMENT_SHADOW_ONLY",
    )


def test_shadow_house_evidence_is_deterministic_and_never_changes_core(
    tmp_path: Path,
) -> None:
    row = phase02_row(street_address_line_1="12 Fiction Road")
    development_parser = engine(tmp_path, execution_scope="DEVELOPMENT")
    locked_parser = engine(tmp_path, execution_scope="LOCKED_EVALUATION")

    first = development_parser.transform(row)
    second = development_parser.transform(row)
    locked = locked_parser.transform(row)
    shadow = [item for item in first.candidates if item.rule_id == _HOUSE_RULE_ID]
    shadow_evidence = [
        item for item in first.evidence_rows if item["rule_id"] == _HOUSE_RULE_ID
    ]

    assert first.evidence_rows == second.evidence_rows
    assert shadow and shadow_evidence
    assert all(not candidate.selectable for candidate in shadow)
    assert all(item["selected"] is False for item in shadow_evidence)
    assert {
        "candidate_value",
        "source_field",
        "start_character",
        "end_character_exclusive",
        "confidence",
        "rule_id",
    }.issubset(shadow_evidence[0])
    assert not any(item.rule_id == _HOUSE_RULE_ID for item in locked.candidates)
    assert not any(
        item["rule_id"] == _HOUSE_RULE_ID for item in locked.evidence_rows
    )

    core_fields = (
        "street_clean",
        "house_number_clean",
        "address_completeness_class",
        "address_parse_status",
        "address_conflict_flags",
        "address_diagnostic_flags",
        "selected_component_provenance",
    )
    assert {field: first.core_row[field] for field in core_fields} == {
        field: locked.core_row[field] for field in core_fields
    }
    assert first.core_row["street_clean"] is None
    assert first.core_row["house_number_clean"] is None
    assert development_parser.configuration_fingerprint != (
        locked_parser.configuration_fingerprint
    )


def test_shadow_house_candidate_cannot_create_unit_core_conflict(
    tmp_path: Path,
) -> None:
    result = engine(tmp_path, execution_scope="DEVELOPMENT").transform(
        phase02_row(street_address_line_1="Unit 12")
    )
    assert any(item.rule_id == _HOUSE_RULE_ID for item in result.candidates)
    assert result.core_row["unit_clean"] == "12"
    assert result.core_row["house_number_clean"] is None
    assert "UNIT_HOUSE_NUMBER_ROLE_CONFLICT" not in result.core_row[
        "address_conflict_flags"
    ]


def test_disposition_change_changes_registry_fingerprint(tmp_path: Path) -> None:
    original = load_rule_registry()
    value = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    house = next(item for item in value["rules"] if item["rule_id"] == _HOUSE_RULE_ID)
    house["execution_disposition"] = "AUTHORITATIVE_CANDIDATE_ONLY"
    changed_path = tmp_path / "changed_registry.json"
    changed_path.write_text(json.dumps(value), encoding="utf-8")
    changed = load_rule_registry(changed_path)
    assert changed.fingerprint != original.fingerprint


def test_unknown_or_inconsistent_disposition_is_rejected(tmp_path: Path) -> None:
    value = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    value["rules"][0]["execution_disposition"] = "UNKNOWN"
    path = tmp_path / "unknown_disposition.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(Phase03Error, match="RULE_REGISTRY_INVALID"):
        load_rule_registry(path)


def test_manual_review_reason_codes_are_closed_versioned_and_canonical() -> None:
    assert len(MANUAL_REVIEW_REASON_CODES_V1) == 15
    assert tuple(MANUAL_REVIEW_REASON_CODE_DEFINITIONS_V1) == (
        MANUAL_REVIEW_REASON_CODES_V1
    )
    assert all(MANUAL_REVIEW_REASON_CODE_DEFINITIONS_V1.values())
    for code in MANUAL_REVIEW_REASON_CODES_V1:
        note = "protected adjudication note" if code == "OTHER_ADJUDICATION_REQUIRED" else None
        assert canonicalize_manual_review_reason_codes(
            [code], protected_adjudication_note=note
        ) == (code,)
    assert canonicalize_manual_review_reason_codes(
        ["WRONG_VALUE", "CORRECT_AS_IS", "WRONG_VALUE"]
    ) == ("CORRECT_AS_IS", "WRONG_VALUE")
    with pytest.raises(ValueError, match="unknown"):
        canonicalize_manual_review_reason_codes(["FREE_TEXT_REASON"])


def test_other_reason_requires_separate_protected_note() -> None:
    row = _portable_review_row(["OTHER_ADJUDICATION_REQUIRED"])
    with pytest.raises(ValueError, match="protected adjudication note"):
        validate_portable_review_row(row)
    validate_portable_review_row(
        row, protected_adjudication_note="Controlled adjudication explanation"
    )
    assert "adjudication_note" not in row
    assert "raw_address" not in row


def test_portable_reason_codes_must_be_canonical_and_cannot_add_raw_values() -> None:
    row = _portable_review_row(["WRONG_VALUE", "CORRECT_AS_IS"])
    with pytest.raises(ValueError, match="not canonical"):
        validate_portable_review_row(row)
    row = _portable_review_row(["CORRECT_AS_IS"])
    row["raw_address"] = "fictional confidential text"
    with pytest.raises(ValueError, match="prohibited"):
        validate_portable_review_row(row)
