from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from safe_geocoding_pipeline.phase03.config import Phase03Config
from safe_geocoding_pipeline.phase03.cli import build_parser
from safe_geocoding_pipeline.phase03.constants import (
    PARSER_VERSION_V2,
    PARSER_VERSION_V3,
    RULE_REGISTRY_VERSION_V3,
    RULE_REGISTRY_VERSION_V4,
)
from safe_geocoding_pipeline.phase03.engine import Phase03Engine
from safe_geocoding_pipeline.phase03.errors import Phase03Error
from safe_geocoding_pipeline.phase03.references import load_production_references
from safe_geocoding_pipeline.phase03.rules import load_rule_registry
from safe_geocoding_pipeline.phase03.semantic import core_digest, evidence_digest
from safe_geocoding_pipeline.phase03.validation import (
    validate_core_evidence_relationship,
    validate_core_rows,
    validate_evidence_rows,
)

from phase03_helpers import engine, phase02_row

_HOUSE_RULE = "HOUSE_NUMBER_EMBEDDED_DESIGNATOR_EXPERIMENT_V4"
_STREET_RULE = "STREET_EMBEDDED_DESIGNATOR_EXPERIMENT_V4"


def _supported_row(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "street_address_line_1": "Annex 12 Example Street",
        "postcode": "12345",
        "city": "Fiction City",
        "country_iso_code": "XZ",
    }
    values.update(overrides)
    return phase02_row(**values)


def _parser(path: Path, *, config: Phase03Config | None = None) -> Any:
    path.mkdir(parents=True, exist_ok=False)
    return engine(
        path,
        config=config,
        parser_version=PARSER_VERSION_V3 if config is None else config.parser_version,
    )


def _experimental_evidence(result: Any) -> list[dict[str, Any]]:
    return [
        row
        for row in result.evidence_rows
        if row["rule_id"] in {_HOUSE_RULE, _STREET_RULE}
    ]


def test_v3_registry_and_configuration_have_new_frozen_identities() -> None:
    v2_registry = load_rule_registry(registry_version=RULE_REGISTRY_VERSION_V3)
    v3_registry = load_rule_registry(registry_version=RULE_REGISTRY_VERSION_V4)
    assert v2_registry.fingerprint == (
        "a2aadae857b7d4bf7262bd37e6dacf58aae220e00b402ca971c51cea320d6f55"
    )
    assert v3_registry.fingerprint == (
        "2137c4a78cd062aa6f07784deea6046824e99ed7712a591d841e142d2f49dfc5"
    )
    assert v3_registry.schema_version == "phase03_rule_registry_schema_v4_experimental"
    assert len(v2_registry.rules) == 16
    assert len(v3_registry.rules) == 18
    assert {rule.rule_id for rule in v3_registry.rules} - {
        rule.rule_id for rule in v2_registry.rules
    } == {_HOUSE_RULE, _STREET_RULE}
    config = Phase03Config.for_parser_version(PARSER_VERSION_V3)
    assert config.rule_registry_version == RULE_REGISTRY_VERSION_V4
    assert config.configuration_fingerprint().hex() == (
        "78b4782c29ee1676cd04c5ebc015bcab731111b280036bf3bee70121332f0871"
    )


def test_v3_production_reference_effective_fingerprint_is_frozen() -> None:
    config = Phase03Config.for_parser_version(PARSER_VERSION_V3)
    country, scripts = load_production_references(
        expected_country_reference_id=config.country_reference_version,
        expected_unicode_reference_id=config.unicode_reference_version,
    )
    parser = Phase03Engine(
        config,
        load_rule_registry(registry_version=config.rule_registry_version),
        country_reference=country,
        script_reference=scripts,
        implementation_fingerprint=bytes(32),
        execution_scope="DEVELOPMENT",
    )
    assert parser.configuration_fingerprint.hex() == (
        "4ad2febb4c1d3a333a76a4a4ad02232958245f99715032d497ab1ee1c3266ee3"
    )


def test_development_transform_requires_explicit_experimental_v3_opt_in() -> None:
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
        PARSER_VERSION_V3,
    ]
    assert build_parser().parse_args(arguments).parser_version == PARSER_VERSION_V3


@pytest.mark.parametrize("scope", ["LOCKED_EVALUATION", "AUTHORITATIVE"])
def test_v3_experiment_fails_closed_outside_development(
    tmp_path: Path, scope: str
) -> None:
    with pytest.raises(Phase03Error, match="PARSER_V3_EXPERIMENT_DEVELOPMENT_ONLY"):
        engine(
            tmp_path,
            parser_version=PARSER_VERSION_V3,
            execution_scope=scope,
        )


@pytest.mark.parametrize(
    ("raw", "street_span", "house_span"),
    [
        ("Annex 12 Example Street", (9, 23), (6, 8)),
        ("Example Street 12 Annex", (0, 14), (15, 17)),
        ("Wing 7 Rue Exemple", (7, 18), (5, 6)),
    ],
)
def test_v3_supported_embedded_number_selects_exact_contiguous_spans(
    tmp_path: Path,
    raw: str,
    street_span: tuple[int, int],
    house_span: tuple[int, int],
) -> None:
    result = engine(tmp_path, parser_version=PARSER_VERSION_V3).transform(
        _supported_row(street_address_line_1=raw)
    )
    core = result.core_row
    assert core["street_clean"] == raw[slice(*street_span)]
    assert core["house_number_clean"] == raw[slice(*house_span)]
    assert core["address_parse_status"] == "PARTIAL"
    assert "UNASSIGNED_CONTENT_PRESENT" in core["address_diagnostic_flags"]
    evidence = _experimental_evidence(result)
    assert [row["rule_id"] for row in evidence] == [_STREET_RULE, _HOUSE_RULE]
    assert all(row["selected"] is True for row in evidence)
    spans = {
        row["rule_id"]: (row["start_character"], row["end_character_exclusive"])
        for row in evidence
    }
    assert spans == {_STREET_RULE: street_span, _HOUSE_RULE: house_span}
    assert {row["confidence"] for row in evidence} == {"MEDIUM"}
    assert {row["source_field"] for row in evidence} == {
        "street_address_line_1"
    }
    assert all(row["candidate_value"] != raw for row in evidence)
    validate_core_rows([core])
    validate_evidence_rows(result.evidence_rows)
    validate_core_evidence_relationship([core], result.evidence_rows)


@pytest.mark.parametrize(
    ("raw", "row_overrides"),
    [
        ("Annex 1234 Example Street", {"postcode": "1234"}),
        ("Floor 12 Example Street", {}),
        ("Unit 12 Example Street", {}),
        ("Building 12 Example Street", {}),
        ("Company 12 Example Street", {}),
        ("Lot 12 Example Street", {}),
        ("Block 12 Example Street", {}),
        ("Reference 12 Example Street", {}),
        ("Date 12 Example Street", {}),
        ("Annex 2024 Example Street", {}),
        ("Annex 12 Example Street 14", {}),
        ("Example Street 12 Sample Road", {}),
        ("Annex, 12 Example Street", {}),
        ("Annex 12 Example Street;", {}),
        ("Annex 12 Example Street (rear)", {}),
    ],
)
def test_v3_false_positive_boundaries_do_not_select_experimental_pair(
    tmp_path: Path, raw: str, row_overrides: dict[str, str]
) -> None:
    result = engine(tmp_path, parser_version=PARSER_VERSION_V3).transform(
        _supported_row(street_address_line_1=raw, **row_overrides)
    )
    assert not any(row["selected"] for row in _experimental_evidence(result))


def test_v3_requires_two_unambiguous_structured_geography_components(
    tmp_path: Path,
) -> None:
    result = engine(tmp_path, parser_version=PARSER_VERSION_V3).transform(
        phase02_row(
            street_address_line_1="Annex 12 Example Street",
            country_iso_code="XZ",
        )
    )
    assert result.core_row["street_clean"] is None
    assert result.core_row["house_number_clean"] is None
    assert not any(row["selected"] for row in _experimental_evidence(result))


def test_v3_rejects_conflicting_structured_and_freeform_geography(
    tmp_path: Path,
) -> None:
    result = engine(tmp_path, parser_version=PARSER_VERSION_V3).transform(
        _supported_row(street_address_line_2="Namibia")
    )
    assert "COUNTRY_SOURCE_CONFLICT" in result.core_row["address_conflict_flags"]
    assert not any(row["selected"] for row in _experimental_evidence(result))


def test_v3_rejects_existing_competing_house_and_cross_line_structure(
    tmp_path: Path,
) -> None:
    competing = _parser(tmp_path / "competing")
    result = competing.transform(
        _supported_row(street_address_line_2="99 Sample Road")
    )
    assert not any(row["selected"] for row in _experimental_evidence(result))

    cross_line = _parser(tmp_path / "cross-line")
    split = cross_line.transform(
        _supported_row(
            street_address_line_1="Annex",
            street_address_line_2="12",
            street_address_line_3="Example Street",
        )
    )
    assert split.core_row["house_number_clean"] is None
    assert not any(row["selected"] for row in _experimental_evidence(split))


@pytest.mark.parametrize(
    "competing_line",
    ["Flat 42", "Floor 8", "Sample Tower", "Sample GmbH"],
)
def test_v3_rejects_independent_unit_floor_building_or_organization_evidence(
    tmp_path: Path, competing_line: str
) -> None:
    result = engine(tmp_path, parser_version=PARSER_VERSION_V3).transform(
        _supported_row(street_address_line_2=competing_line)
    )
    assert not any(row["selected"] for row in _experimental_evidence(result))


def test_rejected_experiment_does_not_consume_candidate_limit_budget(
    tmp_path: Path,
) -> None:
    row = _supported_row(street_address_line_2="Flat 42")
    v2_root = tmp_path / "v2-limit"
    v3_root = tmp_path / "v3-limit"
    v2_root.mkdir()
    v3_root.mkdir()
    v2 = engine(v2_root, parser_version=PARSER_VERSION_V2).transform(row)
    v3 = engine(v3_root, parser_version=PARSER_VERSION_V3).transform(row)
    assert v3.core_row["unit_clean"] == v2.core_row["unit_clean"] == "42"
    assert v3.core_row["address_parse_status"] == v2.core_row["address_parse_status"]
    assert v3.core_row["address_diagnostic_flags"] == v2.core_row[
        "address_diagnostic_flags"
    ]
    assert "CANDIDATE_LIMIT_EXCEEDED" not in v3.core_row[
        "address_diagnostic_flags"
    ]


def test_v3_requires_exact_native_non_native_pair_agreement(tmp_path: Path) -> None:
    exact = _parser(tmp_path / "exact").transform(
        _supported_row(
            street_address_line_1_native="Annex 12 Example Street",
        )
    )
    assert exact.core_row["street_clean"] == "Example Street"
    assert exact.core_row["house_number_clean"] == "12"
    assert exact.core_row["street_native_clean"] is None
    assert exact.core_row["house_number_native_clean"] is None
    assert not exact.core_row["address_conflict_flags"]
    assert any(
        row["source_field"] == "street_address_line_1_native"
        and row["selected"] is False
        for row in _experimental_evidence(exact)
    )
    validate_core_evidence_relationship([exact.core_row], exact.evidence_rows)

    different = _parser(tmp_path / "different").transform(
        _supported_row(
            street_address_line_1_native="Annex 13 Example Street",
        )
    )
    assert different.core_row["street_clean"] is None
    assert different.core_row["house_number_clean"] is None
    assert not any(row["selected"] for row in _experimental_evidence(different))


def test_v2_outputs_and_fingerprints_are_unchanged_by_v3(tmp_path: Path) -> None:
    row = _supported_row()
    v2_root = tmp_path / "v2"
    v2_root.mkdir()
    v2 = engine(v2_root, parser_version=PARSER_VERSION_V2).transform(row)
    assert v2.core_row["street_clean"] is None
    assert v2.core_row["house_number_clean"] is None
    assert v2.core_row["address_parse_status"] == "UNPARSEABLE"
    assert not _experimental_evidence(v2)
    assert Phase03Config.for_parser_version(
        PARSER_VERSION_V2
    ).configuration_fingerprint().hex() == (
        "75911fb4d202eff0af92bc805aa0cfe2844e25d72e0a2e322d5de61fd420274c"
    )


def test_goethe_v3_experiment_reuses_only_development_and_fails_closed() -> None:
    script = (
        Path(__file__).parents[1]
        / "cluster/goethe_nhr/phase03_development_parser_v3_experimental.sbatch"
    ).read_text(encoding="utf-8")
    assert "#SBATCH --cpus-per-task=4" in script
    assert "#SBATCH --mem=16G" in script
    assert "#SBATCH --time=02:00:00" in script
    assert "#SBATCH --mail-type=BEGIN,END,FAIL" in script
    assert "PHASE03_GIT_COMMIT" in script
    assert "PHASE03_INTEGRATION_ROOT" in script
    assert "PARSER_V3_INTEGRATION_WORKTREE_NOT_DETACHED" in script
    assert "PARSER_V3_SBATCH_SOURCE_MISMATCH" in script
    assert "PHASE03_DEVELOPMENT_PAYLOAD" in script
    assert "PHASE03_DEVELOPMENT_IDENTITIES" in script
    assert "PHASE03_PARSER_V2_CORE" in script
    assert "PHASE03_PARSER_V2_EVIDENCE" in script
    assert "PARSER_V3_REQUIRED_INPUT_NOT_READABLE" in script
    assert "PARSER_V3_LOCKED_PATH_PROHIBITED" in script
    assert "PARSER_V3_OUTPUT_UNDER_SOURCE_RUN_ROOT" in script
    assert 'RESOLVED_CONTROLLED_ROOT="$(realpath -e -- "${CONTROLLED_ROOT}")"' in script
    assert "--parser-version conservative_address_parser_v3_experimental" in script
    assert "development-compare-parser-v2-v3" in script
    assert "2137c4a78cd062aa6f07784deea6046824e99ed7712a591d841e142d2f49dfc5" in script
    assert "pilot-profile" not in script
    assert "pilot-select" not in script
    assert "pilot-materialize-development" not in script
    assert "development-review-sample" not in script
    assert "PHASE03_LOCKED" not in script
    assert '"locked_payload_rows_read": 0' in script


def test_v3_safety_caps_and_semantic_digests_remain_deterministic(
    tmp_path: Path,
) -> None:
    config = replace(
        Phase03Config.for_parser_version(PARSER_VERSION_V3),
        per_field_freeform_limit_bytes=64,
    )
    raw = "Annex 12 " + ("X" * 80) + " Street"
    first = _parser(tmp_path / "first", config=config).transform(
        _supported_row(street_address_line_1=raw)
    )
    second = _parser(tmp_path / "second", config=config).transform(
        _supported_row(street_address_line_1=raw)
    )
    assert (
        first.core_row["diagnostic_evaluation_status"]
        == "PARTIALLY_SKIPPED_OVERSIZED"
    )
    assert first.core_row["skipped_oversized_fields"] == ["street_address_line_1"]
    assert first.core_row["street_clean"] is None
    assert first.core_row["house_number_clean"] is None
    assert core_digest([first.core_row], config.component_schema_version) == core_digest(
        [second.core_row], config.component_schema_version
    )
    assert evidence_digest(
        first.evidence_rows, config.evidence_schema_version
    ) == evidence_digest(second.evidence_rows, config.evidence_schema_version)
