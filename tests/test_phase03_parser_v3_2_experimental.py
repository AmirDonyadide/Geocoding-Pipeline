from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from safe_geocoding_pipeline.phase03.cli import build_parser
from safe_geocoding_pipeline.phase03.config import Phase03Config
from safe_geocoding_pipeline.phase03.constants import (
    CORE_COLUMNS,
    PARSER_VERSION_V2_1,
    PARSER_VERSION_V3_1,
    PARSER_VERSION_V3_2,
    RULE_REGISTRY_VERSION_V4,
    RULE_REGISTRY_VERSION_V5,
)
from safe_geocoding_pipeline.phase03.engine import Phase03Engine
from safe_geocoding_pipeline.phase03.errors import Phase03Error
from safe_geocoding_pipeline.phase03.references import load_production_references
from safe_geocoding_pipeline.phase03.rules import load_rule_registry
from safe_geocoding_pipeline.phase03.validation import (
    validate_core_evidence_relationship,
)

from phase03_helpers import engine, phase02_row

_V4_RULES = {
    "HOUSE_NUMBER_EMBEDDED_DESIGNATOR_EXPERIMENT_V4",
    "STREET_EMBEDDED_DESIGNATOR_EXPERIMENT_V4",
}
_V5_RULES = {
    "HOUSE_NUMBER_EMBEDDED_DESIGNATOR_EXPERIMENT_V5",
    "STREET_EMBEDDED_DESIGNATOR_EXPERIMENT_V5",
}
_SCIENTIFIC_FIELDS = CORE_COLUMNS[5:41]


def _row(raw: str = "Example Street 12 Annex", **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "street_address_line_1": raw,
        "postcode": "12345",
        "city": "Fiction City",
        "country_iso_code": "XZ",
    }
    values.update(overrides)
    return phase02_row(**values)


def _rule_evidence(result: Any, rules: set[str]) -> list[dict[str, Any]]:
    return [row for row in result.evidence_rows if row["rule_id"] in rules]


def test_v3_2_has_distinct_registry_parser_and_configuration_identities(
    tmp_path: Path,
) -> None:
    v4 = load_rule_registry(registry_version=RULE_REGISTRY_VERSION_V4)
    v5 = load_rule_registry(registry_version=RULE_REGISTRY_VERSION_V5)
    assert v5.registry_version == RULE_REGISTRY_VERSION_V5
    assert v5.schema_version == "phase03_rule_registry_schema_v5_experimental"
    assert v5.fingerprint != v4.fingerprint
    assert len(v5.rules) == len(v4.rules) == 18
    assert {rule.rule_id for rule in v5.rules} - {
        rule.rule_id
        for rule in load_rule_registry(
            registry_version="phase03_rule_registry_v3"
        ).rules
    } == _V5_RULES
    v5_rules = [rule for rule in v5.rules if rule.rule_id in _V5_RULES]
    assert all(
        rule.matching_condition["parameters"]["allowed_orientation"]
        == "STREET_NUMBER_RESIDUAL"
        for rule in v5_rules
    )
    assert all(
        "allowed_orientation" not in rule.matching_condition["parameters"]
        for rule in v4.rules
        if rule.rule_id in _V4_RULES
    )
    config = Phase03Config.for_parser_version(PARSER_VERSION_V3_2)
    assert config.rule_registry_version == RULE_REGISTRY_VERSION_V5
    assert (
        config.configuration_fingerprint()
        != Phase03Config.for_parser_version(
            PARSER_VERSION_V3_1
        ).configuration_fingerprint()
    )

    country, scripts = load_production_references(
        expected_country_reference_id=config.country_reference_version,
        expected_unicode_reference_id=config.unicode_reference_version,
    )
    parser = Phase03Engine(
        config,
        v5,
        country_reference=country,
        script_reference=scripts,
        implementation_fingerprint=bytes(32),
        execution_scope="DEVELOPMENT",
    )
    assert parser.configuration_fingerprint != bytes(32)
    assert (
        parser.configuration_fingerprint
        != engine(
            tmp_path, parser_version=PARSER_VERSION_V3_1
        ).configuration_fingerprint
    )


def test_v3_2_registry_rejects_an_unregistered_orientation(tmp_path: Path) -> None:
    registry = load_rule_registry(registry_version=RULE_REGISTRY_VERSION_V5)
    payload = json.loads(registry.canonical_bytes)
    for rule in payload["rules"]:
        if rule["rule_id"] in _V5_RULES:
            rule["matching_condition"]["parameters"]["allowed_orientation"] = (
                "RESIDUAL_NUMBER_STREET"
            )
    path = tmp_path / "invalid-registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(Phase03Error) as error:
        load_rule_registry(path)
    assert error.value.code == "RULE_REGISTRY_INVALID"
    assert error.value.detail == "experimental orientation invalid"


def test_registry_orientation_contract_is_version_bound(tmp_path: Path) -> None:
    v5 = json.loads(
        load_rule_registry(registry_version=RULE_REGISTRY_VERSION_V5).canonical_bytes
    )
    for rule in v5["rules"]:
        if rule["rule_id"] in _V5_RULES:
            del rule["matching_condition"]["parameters"]["allowed_orientation"]
    missing = tmp_path / "v5-missing-orientation.json"
    missing.write_text(json.dumps(v5), encoding="utf-8")
    with pytest.raises(Phase03Error) as missing_error:
        load_rule_registry(missing)
    assert missing_error.value.detail == (
        "experimental orientation does not match registry version"
    )

    v4 = json.loads(
        load_rule_registry(registry_version=RULE_REGISTRY_VERSION_V4).canonical_bytes
    )
    for rule in v4["rules"]:
        if rule["rule_id"] in _V4_RULES:
            rule["matching_condition"]["parameters"]["allowed_orientation"] = (
                "STREET_NUMBER_RESIDUAL"
            )
    introduced = tmp_path / "v4-introduced-orientation.json"
    introduced.write_text(json.dumps(v4), encoding="utf-8")
    with pytest.raises(Phase03Error) as introduced_error:
        load_rule_registry(introduced)
    assert introduced_error.value.detail == (
        "experimental orientation does not match registry version"
    )


def test_v3_2_keeps_only_street_number_residual_orientation(tmp_path: Path) -> None:
    (tmp_path / "forward").mkdir()
    forward = engine(
        tmp_path / "forward", parser_version=PARSER_VERSION_V3_2
    ).transform(_row())
    assert forward.core_row["street_clean"] == "Example Street"
    assert forward.core_row["house_number_clean"] == "12"
    evidence = _rule_evidence(forward, _V5_RULES)
    assert [row["rule_id"] for row in evidence] == [
        "STREET_EMBEDDED_DESIGNATOR_EXPERIMENT_V5",
        "HOUSE_NUMBER_EMBEDDED_DESIGNATOR_EXPERIMENT_V5",
    ]
    assert all(row["selected"] is True for row in evidence)
    assert {
        row["rule_id"]: (row["start_character"], row["end_character_exclusive"])
        for row in evidence
    } == {
        "STREET_EMBEDDED_DESIGNATOR_EXPERIMENT_V5": (0, 14),
        "HOUSE_NUMBER_EMBEDDED_DESIGNATOR_EXPERIMENT_V5": (15, 17),
    }
    assert "UNASSIGNED_CONTENT_PRESENT" in forward.core_row["address_diagnostic_flags"]
    validate_core_evidence_relationship([forward.core_row], forward.evidence_rows)

    (tmp_path / "reverse").mkdir()
    reverse = engine(
        tmp_path / "reverse", parser_version=PARSER_VERSION_V3_2
    ).transform(_row("Annex 12 Example Street"))
    assert reverse.core_row["street_clean"] is None
    assert reverse.core_row["house_number_clean"] is None
    assert not _rule_evidence(reverse, _V5_RULES)


def test_v3_1_historical_reverse_orientation_remains_reproducible(
    tmp_path: Path,
) -> None:
    result = engine(tmp_path, parser_version=PARSER_VERSION_V3_1).transform(
        _row("Annex 12 Example Street")
    )
    assert result.core_row["street_clean"] == "Example Street"
    assert result.core_row["house_number_clean"] == "12"
    assert {row["rule_id"] for row in _rule_evidence(result, _V4_RULES)} == _V4_RULES
    assert all(row["selected"] is True for row in _rule_evidence(result, _V4_RULES))


def test_v2_1_and_v3_1_are_unchanged_and_v3_2_changes_only_orientation(
    tmp_path: Path,
) -> None:
    unrelated = _row("34 Sample Road")
    outputs = {}
    for name, version in (
        ("v2-1", PARSER_VERSION_V2_1),
        ("v3-1", PARSER_VERSION_V3_1),
        ("v3-2", PARSER_VERSION_V3_2),
    ):
        (tmp_path / name).mkdir()
        outputs[name] = (
            engine(tmp_path / name, parser_version=version)
            .transform(unrelated)
            .core_row
        )
    assert all(
        outputs["v2-1"][field] == outputs["v3-1"][field] == outputs["v3-2"][field]
        for field in _SCIENTIFIC_FIELDS
    )


@pytest.mark.parametrize(
    "raw",
    [
        "Example Street 2024 Annex",
        "Example Street 12 Floor",
        "Example Street 12 Annex 14",
        "Example Street, 12 Annex",
    ],
)
def test_v3_2_retains_existing_false_positive_boundaries(
    tmp_path: Path, raw: str
) -> None:
    result = engine(tmp_path, parser_version=PARSER_VERSION_V3_2).transform(_row(raw))
    assert not any(row["selected"] for row in _rule_evidence(result, _V5_RULES))


def test_v3_2_retains_geography_and_native_agreement_gates(tmp_path: Path) -> None:
    (tmp_path / "insufficient").mkdir()
    insufficient = engine(
        tmp_path / "insufficient", parser_version=PARSER_VERSION_V3_2
    ).transform(
        phase02_row(
            street_address_line_1="Example Street 12 Annex",
            country_iso_code="XZ",
        )
    )
    assert insufficient.core_row["street_clean"] is None
    assert insufficient.core_row["house_number_clean"] is None

    (tmp_path / "conflicting").mkdir()
    conflicting = engine(
        tmp_path / "conflicting", parser_version=PARSER_VERSION_V3_2
    ).transform(_row(street_address_line_1_native="Example Street 13 Annex"))
    assert conflicting.core_row["street_clean"] is None
    assert conflicting.core_row["house_number_clean"] is None


@pytest.mark.parametrize("scope", ["LOCKED_EVALUATION", "AUTHORITATIVE"])
def test_v3_2_fails_closed_outside_development(tmp_path: Path, scope: str) -> None:
    with pytest.raises(Phase03Error, match="PARSER_V3_EXPERIMENT_DEVELOPMENT_ONLY"):
        engine(
            tmp_path,
            parser_version=PARSER_VERSION_V3_2,
            execution_scope=scope,
        )


def test_v3_2_is_an_explicit_cli_opt_in() -> None:
    arguments = [
        "development-transform",
        "--input-development-payload",
        "payload.parquet",
        "--development-identities",
        "development.identities.bin",
        "--output-directory",
        "output",
        "--git-commit",
        "deadbeef",
        "--parser-version",
        PARSER_VERSION_V3_2,
    ]
    assert build_parser().parse_args(arguments).parser_version == PARSER_VERSION_V3_2


def test_v3_2_goethe_workflow_is_development_only_and_fail_closed() -> None:
    script = (
        Path(__file__).parents[1]
        / "cluster/goethe_nhr/phase03_development_parser_v3_2_experimental.sbatch"
    ).read_text(encoding="utf-8")
    assert "#SBATCH --cpus-per-task=4" in script
    assert "#SBATCH --mem=16G" in script
    assert "#SBATCH --time=02:00:00" in script
    assert "#SBATCH --mail-type=BEGIN,END,FAIL" in script
    assert "PARSER_V3_2_GIT_COMMIT_MISMATCH" in script
    assert "PARSER_V3_2_WORKTREE_NOT_DETACHED" in script
    assert "PARSER_V3_2_WORKTREE_NOT_CLEAN" in script
    assert "PARSER_V3_2_LOCKED_PATH_PROHIBITED" in script
    assert "PARSER_V3_2_OUTPUT_UNDER_SOURCE_RUN_ROOT" in script
    assert "PARSER_V3_2_READ_ONLY_INPUT_CHANGED" in script
    assert "conservative_address_parser_v3_2_experimental" in script
    assert "development-compare-parser-v2-1-v3-2" in script
    assert "evaluate-v3-2-label-reuse" in script
    assert "analyze-v3-1-orientations" in script
    assert "pilot-profile" not in script
    assert "pilot-select" not in script
    assert "pilot-materialize-development" not in script
    assert "Targeted-R02" not in script
    assert 'echo "targeted_r02_access=PROHIBITED"' in script
    assert '"locked_payload_rows_read": 0' in script
    assert '"targeted_r02_rows_read": 0' in script
