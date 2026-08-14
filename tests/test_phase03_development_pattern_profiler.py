from __future__ import annotations

import hashlib
import json
from collections import Counter
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
from safe_geocoding_pipeline.phase03.development_pattern_profiler import (
    MAX_PATTERN_TOKENS,
    _pattern,
    _suppressed_pattern_profile,
    profile_development_patterns,
)
from safe_geocoding_pipeline.phase03.pilot_runner import write_identity_set
from safe_geocoding_pipeline.phase03.rules import load_rule_registry
from safe_geocoding_pipeline.phase03.schema import core_schema, evidence_schema


def _identity(index: int) -> bytes:
    return hashlib.sha256(f"fictional-profile-identity:{index}".encode()).digest()


def _staging_row(index: int, raw: str, *, native: str = "") -> dict[str, Any]:
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
            country_iso_code="XZ",
            source_file="fictional_profile.parquet",
            source_logical_record_number=index + 1,
            stable_source_row_id_v1=_identity(index),
            source_file_sha256=bytes.fromhex("22" * 32),
        )
    )
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
    raw_values = [
        "PrivateLexemeOne",
        "PrivateLexemeTwo",
        "PrivateLexemeThree",
        "PrivateLexemeFour",
        "PrivateLexemeFive",
        "PrivateLexemeSix",
        "RareSentinel/#",
        "X" * 65_537,
    ]
    staging = [
        _staging_row(index, raw, native="سري" if index == 0 else "")
        for index, raw in enumerate(raw_values)
    ]
    parser = engine(tmp_path, parser_version=PARSER_VERSION_V2)
    transformed = [parser.transform(row) for row in staging]
    core = [item.core_row for item in transformed]
    evidence = [row for item in transformed for row in item.evidence_rows]

    payload_path = tmp_path / "development_payload.parquet"
    core_path = tmp_path / "development_core.parquet"
    evidence_path = tmp_path / "development_evidence.parquet"
    identities_path = tmp_path / "development.identities"
    _write_parquet(payload_path, staging, base_staging_schema())
    _write_parquet(core_path, core, core_schema())
    _write_parquet(evidence_path, evidence, evidence_schema())
    write_identity_set(
        identities_path,
        (_identity(index) for index in range(len(staging))),
        partition="DEVELOPMENT",
        manifest_identity="fictional-phase02-manifest",
        sampling_config_fingerprint="fictional-sampling-config",
    )
    paths = {
        "payload": payload_path,
        "core": core_path,
        "evidence": evidence_path,
        "identities": identities_path,
    }
    return paths, tuple(raw_values) + ("سري",)


def _run_profile(
    tmp_path: Path,
    paths: dict[str, Path],
    output_name: str,
) -> Path:
    registry = load_rule_registry(registry_version="phase03_rule_registry_v3")
    output = tmp_path / output_name
    result = profile_development_patterns(
        development_payload_path=paths["payload"],
        core_path=paths["core"],
        evidence_path=paths["evidence"],
        development_identities_path=paths["identities"],
        output_directory=output,
        script_reference=fictional_script_reference(tmp_path),
        rule_ids=tuple(rule.rule_id for rule in registry.ordered_rules()),
        rule_registry_fingerprint=registry.fingerprint,
        expected_rows=8,
        production=False,
        minimum_pattern_rows=5,
        maximum_reported_patterns=3,
    )
    assert result.rows == 8
    assert result.report_json.parent == output
    return output


def test_sanitized_profile_is_deterministic_bounded_and_does_not_mutate_inputs(
    tmp_path: Path,
) -> None:
    paths, raw_values = _fixture(tmp_path)
    before = {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in paths.items()
    }
    first = _run_profile(tmp_path, paths, "profile_one")
    second = _run_profile(tmp_path, paths, "profile_two")
    after = {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in paths.items()
    }
    assert before == after

    names = (
        "phase03_development_pattern_profile.json",
        "phase03_development_pattern_opportunities.csv",
        "phase03_development_pattern_profile.md",
    )
    for name in names:
        assert (first / name).read_bytes() == (second / name).read_bytes()
        assert (first / name).stat().st_mode & 0o777 == 0o600
    assert first.stat().st_mode & 0o777 == 0o700

    portable = b"\n".join((first / name).read_bytes() for name in names)
    for raw in raw_values:
        assert raw.encode("utf-8") not in portable
    for index in range(8):
        assert _identity(index).hex().encode() not in portable
    assert b"fictional-provider" not in portable
    assert b"fictional_profile.parquet" not in portable
    assert str(tmp_path).encode("utf-8") not in portable

    report = json.loads(
        (first / "phase03_development_pattern_profile.json").read_text(encoding="utf-8")
    )
    reported_fingerprint = report.pop("profile_fingerprint")
    assert fingerprint(report) == reported_fingerprint
    patterns = report["segment_structural_patterns"]["named_patterns"]
    assert len(patterns) <= 3
    assert (
        len(
            report["address_line_relationships"]["structural_relationships"][
                "named_patterns"
            ]
        )
        <= 3
    )
    assert len(report["potential_rule_opportunities"]) <= 3
    assert report["segment_structural_patterns"]["suppressed_distinct_patterns"] >= 1
    assert _pattern("RareSentinel/#") not in patterns
    assert report["input_contract"]["locked_rows_read"] == 0
    assert report["privacy_configuration"] == {
        "maximum_pattern_tokens": MAX_PATTERN_TOKENS,
        "maximum_reported_patterns": 3,
        "minimum_pattern_rows": 5,
        "raw_values_reported": False,
        "identities_reported": False,
        "source_spans_reported": False,
    }
    assert report["parser_v2_status"]["UNPARSEABLE"] >= 1
    assert report["unassigned_content"]["rows"] >= 1
    assert report["existing_rule_coverage"]["rows_without_street_or_house_rule"] >= 1
    assert report["safety_coverage"]["skipped_oversized_fields"] == {
        "street_address_line_1": 1
    }
    assert report["safety_coverage"]["oversized_raw_values_tokenized"] is False


def test_production_guard_runs_before_any_input_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def forbidden_open(*args: object, **kwargs: object) -> None:
        raise AssertionError("production input opened before execution guard")

    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setattr(
        "safe_geocoding_pipeline.phase03.development_pattern_profiler.pq.ParquetFile",
        forbidden_open,
    )
    with pytest.raises(ExecutionPolicyError, match="HEAVY_PROCESS_CLUSTER_REQUIRED"):
        profile_development_patterns(
            development_payload_path=tmp_path / "missing_payload.parquet",
            core_path=tmp_path / "missing_core.parquet",
            evidence_path=tmp_path / "missing_evidence.parquet",
            development_identities_path=tmp_path / "missing.identities",
            output_directory=tmp_path / "output",
            script_reference=fictional_script_reference(tmp_path),
            rule_ids=("FICTIONAL_RULE",),
            rule_registry_fingerprint="0" * 64,
            production=True,
        )


def test_locked_path_is_rejected_in_synthetic_pathway(tmp_path: Path) -> None:
    paths, _ = _fixture(tmp_path)
    with pytest.raises(ValueError, match="LOCKED_INPUT_PROHIBITED"):
        profile_development_patterns(
            development_payload_path=tmp_path / "locked" / "payload.parquet",
            core_path=paths["core"],
            evidence_path=paths["evidence"],
            development_identities_path=paths["identities"],
            output_directory=tmp_path / "output",
            script_reference=fictional_script_reference(tmp_path),
            rule_ids=("FICTIONAL_RULE",),
            rule_registry_fingerprint="0" * 64,
            expected_rows=8,
            production=False,
        )


def test_non_development_identity_partition_is_rejected_without_path_hint(
    tmp_path: Path,
) -> None:
    paths, _ = _fixture(tmp_path)
    sealed = tmp_path / "sealed.identities"
    write_identity_set(
        sealed,
        (_identity(index) for index in range(8)),
        partition="LOCKED_EVALUATION",
        manifest_identity="fictional-phase02-manifest",
        sampling_config_fingerprint="fictional-sampling-config",
    )
    with pytest.raises(
        ValueError, match="DEVELOPMENT_PROFILE_IDENTITY_PARTITION_MISMATCH"
    ):
        profile_development_patterns(
            development_payload_path=paths["payload"],
            core_path=paths["core"],
            evidence_path=paths["evidence"],
            development_identities_path=sealed,
            output_directory=tmp_path / "output",
            script_reference=fictional_script_reference(tmp_path),
            rule_ids=("FICTIONAL_RULE",),
            rule_registry_fingerprint="0" * 64,
            expected_rows=8,
            production=False,
        )


def test_pattern_labels_never_preserve_lexical_tokens() -> None:
    first = _pattern("SecretName 12/3, Дорога")
    second = _pattern("DifferentName 98/7, Улица")
    assert first == second == "WORDS SLASH_NUMBER COMMA LOCAL_SCRIPT"
    assert "SecretName" not in first
    assert "Дорога" not in first
    assert _pattern(" ".join(["word"] * 30)) == "WORDS"
    assert _pattern("word," * 30) == "LONG_PATTERN_17_PLUS"


def test_repeated_segments_in_one_row_cannot_defeat_rare_pattern_suppression() -> None:
    profile = _suppressed_pattern_profile(
        Counter({"WORDS HOUSELIKE_NUM": 12}),
        minimum_rows=5,
        maximum=100,
        distinct_row_counts={"WORDS HOUSELIKE_NUM": 1},
    )
    assert profile["named_patterns"] == {}
    assert profile["suppressed_distinct_patterns"] == 1
    assert profile["suppressed_segment_count"] == 12


def test_development_pattern_profile_cli_is_registered() -> None:
    arguments = build_parser().parse_args(
        [
            "development-pattern-profile",
            "--development-payload",
            "payload.parquet",
            "--development-core",
            "core.parquet",
            "--development-evidence",
            "evidence.parquet",
            "--development-identities",
            "development.identities",
            "--output-directory",
            "profile-output",
        ]
    )
    assert arguments.command == "development-pattern-profile"
