from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from phase03_helpers import engine, fictional_script_reference, phase02_row
from safe_geocoding_pipeline.execution_policy import ExecutionPolicyError
from safe_geocoding_pipeline.phase02.fingerprints import fingerprint
from safe_geocoding_pipeline.phase02.schema import base_staging_schema
from safe_geocoding_pipeline.phase03.cli import build_parser
from safe_geocoding_pipeline.phase03.constants import PARSER_VERSION_V2
from safe_geocoding_pipeline.phase03.development_targeted_opportunity_profiler import (
    MAX_PATTERN_TOKENS,
    TARGET_PATTERN_FAMILIES,
    _numeric_position,
    profile_targeted_development_opportunities,
)
from safe_geocoding_pipeline.phase03.pilot_runner import write_identity_set
from safe_geocoding_pipeline.phase03.rules import load_rule_registry
from safe_geocoding_pipeline.phase03.schema import core_schema, evidence_schema


def _identity(index: int) -> bytes:
    return hashlib.sha256(f"fictional-targeted-profile:{index}".encode()).digest()


def _staging_row(index: int, raw: str, *, native: str) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for field in base_staging_schema():
        if pa.types.is_string(field.type):
            row[field.name] = ""
        elif pa.types.is_uint64(field.type):
            row[field.name] = index + 1
        else:
            row[field.name] = _identity(index)
    row.update(
        phase02_row(
            id=f"fictional-provider-{index}",
            street_address_line_1=raw,
            street_address_line_1_native=native,
            postcode="01234",
            city="Exampleville",
            region_in_country="Example Region",
            country_iso_code="XZ",
            source_file="fictional_targeted.parquet",
            source_logical_record_number=index + 1,
            stable_source_row_id_v1=_identity(index),
            source_file_sha256=bytes.fromhex("22" * 32),
        )
    )
    if index < 2:
        row["street_address_line_2"] = "12 Example Street"
        row["street_address_line_2_native"] = "13 Example Street"
    row.update(
        {
            "batch_priority": "fictional",
            "location_information": "no_geocoding_information",
            "source_schema_version": "fictional_source_v1",
            "parser_version": "fictional_phase02_parser_v1",
            "staging_version": "fictional_staging_v1",
        }
    )
    return row


def _write_parquet(path: Path, rows: list[dict[str, Any]], schema: pa.Schema) -> None:
    pq.write_table(
        pa.Table.from_pylist(rows, schema=schema),
        path,
        write_page_checksum=True,
        write_statistics=False,
    )


def _fixture(tmp_path: Path) -> tuple[dict[str, Path], tuple[str, ...]]:
    patterns = (
        "PrivateAlpha 12",
        "PrivateBeta 34",
        "12 PrivateGamma",
        "34 PrivateDelta",
        "PrivateEpsilon 12 PrivateZeta",
        "PrivateEta 34 PrivateTheta",
        "12, PrivateIota",
        "34, PrivateKappa",
        "PrivateLambda, 12",
        "PrivateMu, 34",
        "12/3 PrivateNu",
        "34/5 PrivateXi",
        "PrivateOmicron 12/3",
        "PrivatePi 34/5",
        "12-14 PrivateRho",
        "PrivateRare 12-14",
    )
    staging = [
        _staging_row(index, raw, native=f"NativeWord {40 + index}")
        for index, raw in enumerate(patterns)
    ]
    parser = engine(tmp_path, parser_version=PARSER_VERSION_V2)
    transformed = [parser.transform(row) for row in staging]
    core = [item.core_row for item in transformed]
    evidence = [row for item in transformed for row in item.evidence_rows]
    paths = {
        "payload": tmp_path / "development_payload.parquet",
        "core": tmp_path / "development_core.parquet",
        "evidence": tmp_path / "development_evidence.parquet",
        "identities": tmp_path / "development.identities",
    }
    _write_parquet(paths["payload"], staging, base_staging_schema())
    _write_parquet(paths["core"], core, core_schema())
    _write_parquet(paths["evidence"], evidence, evidence_schema())
    write_identity_set(
        paths["identities"],
        (_identity(index) for index in range(len(staging))),
        partition="DEVELOPMENT",
        manifest_identity="fictional-phase02-manifest",
        sampling_config_fingerprint="fictional-sampling-config",
    )
    return (
        paths,
        patterns
        + tuple(f"NativeWord {40 + index}" for index in range(16))
        + (
            "12 Example Street",
            "13 Example Street",
            "Exampleville",
            "Example Region",
        ),
    )


def _run(
    tmp_path: Path, paths: dict[str, Path], output_name: str
) -> tuple[Path, dict[str, Any]]:
    registry = load_rule_registry(registry_version="phase03_rule_registry_v3")
    output = tmp_path / output_name
    result = profile_targeted_development_opportunities(
        development_payload_path=paths["payload"],
        core_path=paths["core"],
        evidence_path=paths["evidence"],
        development_identities_path=paths["identities"],
        output_directory=output,
        script_reference=fictional_script_reference(tmp_path),
        rule_registry_fingerprint=registry.fingerprint,
        expected_rows=16,
        production=False,
        minimum_pattern_rows=2,
        maximum_categories=10,
    )
    assert result.rows == 16
    report = json.loads(result.report_json.read_text(encoding="utf-8"))
    return output, report


def test_target_pattern_classification_and_numeric_position_are_closed() -> None:
    assert TARGET_PATTERN_FAMILIES == (
        "WORDS HOUSELIKE_NUM",
        "HOUSELIKE_NUM WORDS",
        "WORDS HOUSELIKE_NUM WORDS",
        "HOUSELIKE_NUM COMMA WORDS",
        "WORDS COMMA HOUSELIKE_NUM",
        "SLASH_NUMBER WORDS",
        "WORDS SLASH_NUMBER",
        "HYPHEN_NUMBER WORDS",
    )
    assert _numeric_position(("HOUSELIKE_NUM", "WORDS")) == "LEADING_NUMBER"
    assert _numeric_position(("WORDS", "HOUSELIKE_NUM")) == "TRAILING_NUMBER"
    assert (
        _numeric_position(("WORDS", "HOUSELIKE_NUM", "WORDS"))
        == "EMBEDDED_NUMBER"
    )


def test_targeted_profile_is_deterministic_private_bounded_and_read_only(
    tmp_path: Path,
) -> None:
    paths, raw_values = _fixture(tmp_path)
    before = {name: path.read_bytes() for name, path in paths.items()}
    first, first_report = _run(tmp_path, paths, "targeted_one")
    second, second_report = _run(tmp_path, paths, "targeted_two")
    assert before == {name: path.read_bytes() for name, path in paths.items()}
    assert first_report == second_report

    names = (
        "phase03_development_targeted_opportunity_profile.json",
        "phase03_development_targeted_opportunities.csv",
        "phase03_development_targeted_opportunity_profile.md",
    )
    for name in names:
        assert (first / name).read_bytes() == (second / name).read_bytes()
        assert (first / name).stat().st_mode & 0o777 == 0o600
    assert first.stat().st_mode & 0o777 == 0o700
    portable = b"\n".join((first / name).read_bytes() for name in names)
    for value in raw_values:
        assert value.encode("utf-8") not in portable
    for index in range(16):
        assert _identity(index).hex().encode() not in portable
    assert b"fictional-provider" not in portable
    assert b"fictional_targeted.parquet" not in portable
    assert b"stable_source_row_id_v1" not in portable
    assert b"start_character" not in portable
    assert b"end_character_exclusive" not in portable
    assert str(tmp_path).encode() not in portable

    reported_fingerprint = first_report.pop("profile_fingerprint")
    assert fingerprint(first_report) == reported_fingerprint
    assert first_report["input_contract"]["locked_rows_read"] == 0
    assert first_report["privacy_configuration"] == {
        "identities_reported": False,
        "maximum_named_categories": 10,
        "maximum_pattern_tokens": MAX_PATTERN_TOKENS,
        "minimum_rows_for_named_category": 2,
        "paths_reported": False,
        "raw_values_reported": False,
        "source_spans_reported": False,
    }
    families = {
        row["pattern_family"]: row for row in first_report["pattern_families"]
    }
    assert set(TARGET_PATTERN_FAMILIES) - {
        "HYPHEN_NUMBER WORDS",
        "WORDS HYPHEN_NUMBER",
    } <= set(families)
    assert "WORDS HYPHEN_NUMBER" not in families
    assert all(
        len(profile["named_categories"]) <= 10
        for family in families.values()
        for profile in family["cross_tabs"].values()
    )
    words_number = families["WORDS HOUSELIKE_NUM"]
    assert words_number["cross_tabs"]["representation"]["named_categories"] == {
        "NATIVE": 16,
        "NON_NATIVE": 2,
    }
    assert words_number["cross_tabs"]["source_line"]["named_categories"] == {
        "LINE_1": 16
    }
    assert words_number["cross_tabs"]["native_structural_relationship"][
        "named_categories"
    ]["SAME_STRUCTURAL_PATTERN"] >= 2
    assert words_number["cross_tabs"]["target_rule_presence"][
        "named_categories"
    ]["HOUSE_NUMBER_EDGE_CANDIDATE_V1:PRESENT"] >= 2
    assert words_number["cross_tabs"]["target_rule_presence"][
        "named_categories"
    ]["STREET_EXPLICIT_DESIGNATOR_V3:PRESENT"] == 2
    assert words_number["cross_tabs"]["conflict_type"]["named_categories"][
        "NATIVE_NON_NATIVE_HOUSE_NUMBER_CONFLICT"
    ] == 2
    assert first_report["interpretation_guardrails"][
        "parser_v3_rule_creation_authorized"
    ] is False


def test_rare_target_family_is_suppressed_without_leaking_its_label(
    tmp_path: Path,
) -> None:
    paths, _ = _fixture(tmp_path)
    _, report = _run(tmp_path, paths, "targeted")
    assert "WORDS HYPHEN_NUMBER" not in {
        row["pattern_family"] for row in report["pattern_families"]
    }
    assert report["suppression_summary"]["target_families_below_threshold"] >= 1


def test_production_guard_precedes_protected_input_open(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def forbidden_artifact_state(path: Path) -> tuple[int, str]:
        raise AssertionError(f"protected input opened before guard: {path.name}")

    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setattr(
        "safe_geocoding_pipeline.phase03.development_targeted_opportunity_profiler._artifact_state",
        forbidden_artifact_state,
    )
    with pytest.raises(ExecutionPolicyError, match="HEAVY_PROCESS_CLUSTER_REQUIRED"):
        profile_targeted_development_opportunities(
            development_payload_path=tmp_path / "payload.parquet",
            core_path=tmp_path / "core.parquet",
            evidence_path=tmp_path / "evidence.parquet",
            development_identities_path=tmp_path / "development.identities",
            output_directory=tmp_path / "output",
            script_reference=fictional_script_reference(tmp_path),
            rule_registry_fingerprint="0" * 64,
            production=True,
        )


def test_prohibited_path_and_non_development_partition_are_rejected(
    tmp_path: Path,
) -> None:
    paths, _ = _fixture(tmp_path)
    registry = load_rule_registry(registry_version="phase03_rule_registry_v3")
    with pytest.raises(ValueError, match="LOCKED_INPUT_PROHIBITED"):
        profile_targeted_development_opportunities(
            development_payload_path=tmp_path / "locked" / "payload.parquet",
            core_path=paths["core"],
            evidence_path=paths["evidence"],
            development_identities_path=paths["identities"],
            output_directory=tmp_path / "output",
            script_reference=fictional_script_reference(tmp_path),
            rule_registry_fingerprint=registry.fingerprint,
            expected_rows=16,
            production=False,
        )
    locked = tmp_path / "sealed.identities"
    write_identity_set(
        locked,
        (_identity(index) for index in range(16)),
        partition="LOCKED_EVALUATION",
        manifest_identity="fictional-phase02-manifest",
        sampling_config_fingerprint="fictional-sampling-config",
    )
    with pytest.raises(ValueError, match="TARGETED_PROFILE_IDENTITY_PARTITION_MISMATCH"):
        profile_targeted_development_opportunities(
            development_payload_path=paths["payload"],
            core_path=paths["core"],
            evidence_path=paths["evidence"],
            development_identities_path=locked,
            output_directory=tmp_path / "output",
            script_reference=fictional_script_reference(tmp_path),
            rule_registry_fingerprint=registry.fingerprint,
            expected_rows=16,
            production=False,
        )


def test_targeted_profile_cli_is_registered() -> None:
    arguments = build_parser().parse_args(
        [
            "development-targeted-opportunity-profile",
            "--development-payload",
            "payload.parquet",
            "--development-core",
            "core.parquet",
            "--development-evidence",
            "evidence.parquet",
            "--development-identities",
            "development.identities",
            "--output-directory",
            "targeted-output",
        ]
    )
    assert arguments.command == "development-targeted-opportunity-profile"
