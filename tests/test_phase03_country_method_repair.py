from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from safe_geocoding_pipeline.phase03.cli import build_parser
from safe_geocoding_pipeline.phase03.config import Phase03Config
from safe_geocoding_pipeline.phase03.constants import (
    CORE_COLUMNS,
    PARSER_VERSION_V2,
    PARSER_VERSION_V2_1,
    PARSER_VERSION_V3,
    PARSER_VERSION_V3_1,
    RULE_REGISTRY_VERSION_V3,
    RULE_REGISTRY_VERSION_V4,
)
from safe_geocoding_pipeline.phase03.engine import Phase03Engine
from safe_geocoding_pipeline.phase03.errors import Phase03Error
from safe_geocoding_pipeline.phase03.models import SelectedComponent
from safe_geocoding_pipeline.phase03.references import load_production_references
from safe_geocoding_pipeline.phase03.rules import load_rule_registry

from phase03_helpers import engine, phase02_row

_HOUSE_RULE = "HOUSE_NUMBER_EMBEDDED_DESIGNATOR_EXPERIMENT_V4"
_STREET_RULE = "STREET_EMBEDDED_DESIGNATOR_EXPERIMENT_V4"
_SCIENTIFIC_FIELDS = CORE_COLUMNS[5:41]


def _country_result(
    tmp_path: Path, *, parser_version: str, **overrides: Any
) -> Any:
    tmp_path.mkdir(parents=True, exist_ok=True)
    return engine(tmp_path, parser_version=parser_version).transform(
        phase02_row(**overrides)
    )


def _experimental_evidence(result: Any) -> list[dict[str, Any]]:
    return [
        row
        for row in result.evidence_rows
        if row["rule_id"] in {_HOUSE_RULE, _STREET_RULE}
    ]


def _evidence_science(rows: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    return [
        (
            row["component"],
            row["representation"],
            row["candidate_value"],
            row["selected"],
            row["confidence"],
            row["rule_id"],
            row["source_field"],
            row["start_character"],
            row["end_character_exclusive"],
            row["evidence_kind"],
        )
        for row in rows
    ]


def test_repaired_structured_alpha2_ignores_same_value_freeform_name(
    tmp_path: Path,
) -> None:
    structured_only = _country_result(
        tmp_path / "structured-only",
        parser_version=PARSER_VERSION_V2_1,
        country_iso_code="XZ",
    )
    corroborated = _country_result(
        tmp_path / "corroborated",
        parser_version=PARSER_VERSION_V2_1,
        country_iso_code="XZ",
        street_address_line_2="Fictionland",
    )
    assert structured_only.core_row["country_clean"] == "XZ"
    assert corroborated.core_row["country_clean"] == "XZ"
    assert structured_only.core_row["country_parse_method"] == (
        "STRUCTURED_ALPHA2_EXACT"
    )
    assert corroborated.core_row["country_parse_method"] == (
        "STRUCTURED_ALPHA2_EXACT"
    )
    assert corroborated.core_row["country_parse_confidence"] == "HIGH"
    assert corroborated.core_row["country_input_class"] == "ALPHA2_ASSIGNED_EXACT"
    country_provenance = [
        row
        for row in corroborated.core_row["selected_component_provenance"]
        if row["component"] == "COUNTRY"
    ]
    assert country_provenance == [
        {
            "component": "COUNTRY",
            "representation": "SHARED",
            "source_fields": ["country_iso_code"],
            "rule_ids": ["COUNTRY_STRUCTURED_REFERENCE_V1"],
            "confidence": "HIGH",
        }
    ]


def test_repaired_structured_country_name_uses_selected_source_kind(
    tmp_path: Path,
) -> None:
    result = _country_result(
        tmp_path,
        parser_version=PARSER_VERSION_V2_1,
        country_iso_code="Fictionland",
    )
    assert result.core_row["country_clean"] == "XZ"
    assert result.core_row["country_input_class"] == "COUNTRY_NAME_EXACT"
    assert result.core_row["country_parse_method"] == (
        "STRUCTURED_COUNTRY_NAME_EXACT"
    )


def test_repaired_selected_route_wins_over_multiple_candidate_reference_kinds(
    tmp_path: Path,
) -> None:
    result = _country_result(
        tmp_path,
        parser_version=PARSER_VERSION_V2_1,
        country_iso_code="XZ",
        street_address_line_2="Fictionland",
        street_address_line_3="XZZ",
    )
    assert result.core_row["country_clean"] == "XZ"
    assert result.core_row["country_parse_method"] == "STRUCTURED_ALPHA2_EXACT"
    country_candidates = [
        candidate
        for candidate in result.candidates
        if candidate.component == "COUNTRY"
    ]
    assert {candidate.rule_id for candidate in country_candidates} == {
        "COUNTRY_STRUCTURED_REFERENCE_V1",
        "COUNTRY_FREEFORM_REFERENCE_V1",
    }
    assert {candidate.value for candidate in country_candidates} == {"XZ"}


def test_repaired_country_conflict_behavior_is_unchanged(tmp_path: Path) -> None:
    historical = _country_result(
        tmp_path / "historical",
        parser_version=PARSER_VERSION_V2,
        country_iso_code="XZ",
        street_address_line_2="Namibia",
    )
    repaired = _country_result(
        tmp_path / "repaired",
        parser_version=PARSER_VERSION_V2_1,
        country_iso_code="XZ",
        street_address_line_2="Namibia",
    )
    for field in (
        "country_clean",
        "country_input_class",
        "country_parse_method",
        "country_parse_confidence",
        "address_conflict_flags",
        "selected_component_provenance",
    ):
        assert repaired.core_row[field] == historical.core_row[field]
    assert repaired.core_row["country_parse_method"] == "CONFLICT"


def test_repaired_country_method_fails_closed_without_one_selected_route(
    tmp_path: Path,
) -> None:
    parser = engine(tmp_path, parser_version=PARSER_VERSION_V2_1)
    selected = [
        SelectedComponent(
            component="COUNTRY",
            representation="SHARED",
            value="XZ",
            confidence="HIGH",
            source_fields=("country_iso_code",),
            rule_ids=("COUNTRY_STRUCTURED_REFERENCE_V1",),
        )
    ]
    with pytest.raises(
        Phase03Error, match="COUNTRY_SELECTED_SOURCE_METHOD_UNRESOLVED"
    ):
        parser._country_result(selected, {}, set(), set())

    ambiguous = [
        SelectedComponent(
            component="COUNTRY",
            representation="SHARED",
            value="XZ",
            confidence="HIGH",
            source_fields=("country_iso_code",),
            rule_ids=("STRUCTURED_ALPHA2_RULE", "STRUCTURED_NAME_RULE"),
        )
    ]
    with pytest.raises(
        Phase03Error, match="COUNTRY_SELECTED_SOURCE_METHOD_UNRESOLVED"
    ):
        parser._country_result(
            ambiguous,
            {
                ("STRUCTURED_ALPHA2_RULE", "country_iso_code", "XZ"): "ALPHA2",
                ("STRUCTURED_NAME_RULE", "country_iso_code", "XZ"): "NAME",
            },
            set(),
            set(),
        )


def test_repaired_v2_and_v3_match_without_v4_activation(tmp_path: Path) -> None:
    row = phase02_row(
        street_address_line_1="12 Example Street",
        street_address_line_2="Fictionland",
        country_iso_code="XZ",
    )
    baseline_root = tmp_path / "baseline"
    experimental_root = tmp_path / "experimental"
    baseline_root.mkdir()
    experimental_root.mkdir()
    baseline = engine(baseline_root, parser_version=PARSER_VERSION_V2_1).transform(row)
    experimental = engine(
        experimental_root, parser_version=PARSER_VERSION_V3_1
    ).transform(row)
    assert all(
        baseline.core_row[field] == experimental.core_row[field]
        for field in _SCIENTIFIC_FIELDS
    )
    assert not _experimental_evidence(experimental)


def test_repaired_v3_preserves_v4_positive_science(tmp_path: Path) -> None:
    row = phase02_row(
        street_address_line_1="Annex 12 Example Street",
        postcode="12345",
        city="Fiction City",
        country_iso_code="XZ",
    )
    historical_root = tmp_path / "historical"
    repaired_root = tmp_path / "repaired"
    historical_root.mkdir()
    repaired_root.mkdir()
    historical = engine(historical_root, parser_version=PARSER_VERSION_V3).transform(
        row
    )
    repaired = engine(repaired_root, parser_version=PARSER_VERSION_V3_1).transform(
        row
    )
    for field in _SCIENTIFIC_FIELDS:
        assert repaired.core_row[field] == historical.core_row[field]
    assert _evidence_science(_experimental_evidence(repaired)) == _evidence_science(
        _experimental_evidence(historical)
    )
    assert repaired.core_row["street_clean"] == "Example Street"
    assert repaired.core_row["house_number_clean"] == "12"


def test_repaired_parser_versions_have_new_configurations_and_frozen_registries() -> (
    None
):
    historical_v2 = Phase03Config.for_parser_version(PARSER_VERSION_V2)
    historical_v3 = Phase03Config.for_parser_version(PARSER_VERSION_V3)
    repaired_v2 = Phase03Config.for_parser_version(PARSER_VERSION_V2_1)
    repaired_v3 = Phase03Config.for_parser_version(PARSER_VERSION_V3_1)
    assert historical_v2.configuration_fingerprint().hex() == (
        "75911fb4d202eff0af92bc805aa0cfe2844e25d72e0a2e322d5de61fd420274c"
    )
    assert historical_v3.configuration_fingerprint().hex() == (
        "78b4782c29ee1676cd04c5ebc015bcab731111b280036bf3bee70121332f0871"
    )
    assert repaired_v2.rule_registry_version == RULE_REGISTRY_VERSION_V3
    assert repaired_v3.rule_registry_version == RULE_REGISTRY_VERSION_V4
    assert repaired_v2.configuration_fingerprint().hex() == (
        "a17d6be788f41dc07f3cd1b8041e60d034decd6f90a3bb058d66b13d18f44192"
    )
    assert repaired_v3.configuration_fingerprint().hex() == (
        "52f36ba37a218d6465eb314428bbfadb63cc7f34c0703b76907751f7908bfe17"
    )


@pytest.mark.parametrize(
    ("parser_version", "expected"),
    [
        (
            PARSER_VERSION_V2_1,
            "25962a126cd5d30c13607bd564aa250e91096e6961745670772a1ce31b76ac4d",
        ),
        (
            PARSER_VERSION_V3_1,
            "50e06ad6d7ad428811bdefe30ed6ef7e0d6b9eacbbbdce9a53c6809fd812333a",
        ),
    ],
)
def test_repaired_production_reference_effective_fingerprints_are_frozen(
    parser_version: str, expected: str
) -> None:
    config = Phase03Config.for_parser_version(parser_version)
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
    assert parser.configuration_fingerprint.hex() == expected


def test_repaired_method_is_invariant_across_python_hash_seeds() -> None:
    script = """
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "tests"))
from phase03_helpers import engine, phase02_row
from safe_geocoding_pipeline.phase03.constants import PARSER_VERSION_V2_1

with tempfile.TemporaryDirectory() as directory:
    result = engine(Path(directory), parser_version=PARSER_VERSION_V2_1).transform(
        phase02_row(
            country_iso_code="XZ",
            street_address_line_2="Fictionland",
            street_address_line_3="XZZ",
        )
    )
print(json.dumps({"method": result.core_row["country_parse_method"]}))
"""
    methods: list[str] = []
    for seed in ("0", "1", "2", "17", "41", "97", "4294967295", "random"):
        environment = os.environ.copy()
        environment["PYTHONHASHSEED"] = seed
        completed = subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
        methods.append(json.loads(completed.stdout)["method"])
    assert methods == ["STRUCTURED_ALPHA2_EXACT"] * len(methods)


def test_repaired_cli_and_goethe_workflow_are_explicit_and_development_only() -> (
    None
):
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
        "--parser-version",
    ]
    assert build_parser().parse_args(
        [*common, PARSER_VERSION_V2_1]
    ).parser_version == PARSER_VERSION_V2_1
    assert build_parser().parse_args(
        [*common, PARSER_VERSION_V3_1]
    ).parser_version == PARSER_VERSION_V3_1

    script = (
        Path(__file__).parents[1]
        / "cluster/goethe_nhr/phase03_country_method_repair.sbatch"
    ).read_text(encoding="utf-8")
    assert "#SBATCH --cpus-per-task=4" in script
    assert "#SBATCH --mem=16G" in script
    assert "#SBATCH --time=04:00:00" in script
    assert "#SBATCH --mail-type=BEGIN,END,FAIL" in script
    assert "COUNTRY_METHOD_REPAIR_WORKTREE_NOT_DETACHED" in script
    assert "COUNTRY_METHOD_REPAIR_SBATCH_SOURCE_MISMATCH" in script
    assert "COUNTRY_METHOD_REPAIR_LOCKED_PATH_PROHIBITED" in script
    assert "COUNTRY_METHOD_REPAIR_OUTPUT_UNDER_SOURCE_RUN_ROOT" in script
    assert "--parser-version conservative_address_parser_v2_1" in script
    assert (
        "--parser-version conservative_address_parser_v3_1_experimental" in script
    )
    assert "development-compare-parser-v2-1-v3-1" in script
    assert "pilot-profile" not in script
    assert "pilot-select" not in script
    assert "pilot-materialize-development" not in script
    assert "development-review-sample" not in script
    assert "PHASE03_LOCKED" not in script
    assert '"locked_payload_rows_read": 0' in script


@pytest.mark.parametrize("scope", ["LOCKED_EVALUATION", "AUTHORITATIVE"])
def test_repaired_v3_experiment_remains_development_only(
    tmp_path: Path, scope: str
) -> None:
    with pytest.raises(Phase03Error, match="PARSER_V3_EXPERIMENT_DEVELOPMENT_ONLY"):
        engine(
            tmp_path,
            parser_version=PARSER_VERSION_V3_1,
            execution_scope=scope,
        )
