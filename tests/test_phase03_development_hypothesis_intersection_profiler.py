from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from phase03_helpers import engine, phase02_row
from safe_geocoding_pipeline.execution_policy import ExecutionPolicyError
from safe_geocoding_pipeline.phase02.schema import base_staging_schema
from safe_geocoding_pipeline.phase03.cli import build_parser
from safe_geocoding_pipeline.phase03.constants import (
    PARSER_VERSION_V2_1,
    PARSER_VERSION_V3_2,
)
from safe_geocoding_pipeline.phase03.development_hypothesis_intersection_profiler import (
    ROLE_RULES,
    REPORT_SCHEMA_VERSION,
    RuleEvidenceSemantics,
    _EvidenceGroup,
    _date_or_year_reason,
    _h1_profile,
    _intersection_report,
    _population_digest,
    profile_development_hypothesis_intersections,
)
from safe_geocoding_pipeline.phase03.pilot_runner import write_identity_set
from safe_geocoding_pipeline.phase03.rules import load_rule_registry
from safe_geocoding_pipeline.phase03.schema import core_schema, evidence_schema


def _identity(index: int) -> bytes:
    return hashlib.sha256(f"fictional-hypothesis-profile:{index}".encode()).digest()


def _staging_row(
    index: int, lines: tuple[str, str, str, str], *, native_line_2: str = ""
) -> dict[str, Any]:
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
            street_address_line_1=lines[0],
            street_address_line_2=lines[1],
            street_address_line_3=lines[2],
            street_address_line_4=lines[3],
            street_address_line_2_native=native_line_2,
            postcode="1234" if index == 2 else "54321",
            city="Fictionville",
            region_in_country="Fiction Region",
            country_iso_code="XZ",
            source_file="fictional_hypothesis.parquet",
            source_logical_record_number=index + 1,
            stable_source_row_id_v1=_identity(index),
            source_file_sha256=bytes.fromhex("22" * 32),
        )
    )
    row.update(
        {
            "batch_priority": "fictional",
            "location_information": "fictional",
            "source_schema_version": "fictional_source_v1",
            "parser_version": "fictional_phase02_parser_v1",
            "staging_version": "fictional_staging_v1",
        }
    )
    return row


def _write(path: Path, rows: list[dict[str, Any]], schema: pa.Schema) -> None:
    pq.write_table(
        pa.Table.from_pylist(rows, schema=schema),
        path,
        write_page_checksum=True,
        write_statistics=False,
    )


def _fixture(tmp_path: Path) -> dict[str, Path | str]:
    (tmp_path / "baseline").mkdir()
    (tmp_path / "candidate").mkdir()
    staging = [
        _staging_row(0, ("Example Street", "42", "", "")),
        _staging_row(1, ("Example Street", "2024", "", "")),
        _staging_row(2, ("Example Street", "1234", "", "")),
        _staging_row(3, ("Example Street", "Unit 3", "", "")),
        _staging_row(4, ("Example Street", "12/05", "", "")),
        _staging_row(5, ("Example Street", "42", "", ""), native_line_2="43"),
        _staging_row(6, ("10", "Example Street", "20", "")),
        _staging_row(7, ("Unit 7B", "", "", "")),
    ]
    baseline_parser = engine(tmp_path / "baseline", parser_version=PARSER_VERSION_V2_1)
    candidate_parser = engine(
        tmp_path / "candidate", parser_version=PARSER_VERSION_V3_2
    )
    baseline = [baseline_parser.transform(row) for row in staging]
    candidate = [candidate_parser.transform(row) for row in staging]
    paths: dict[str, Path | str] = {
        "payload": tmp_path / "payload.parquet",
        "baseline_core": tmp_path / "baseline_core.parquet",
        "baseline_evidence": tmp_path / "baseline_evidence.parquet",
        "candidate_core": tmp_path / "candidate_core.parquet",
        "candidate_evidence": tmp_path / "candidate_evidence.parquet",
        "identities": tmp_path / "development.identities",
    }
    _write(cast_path(paths["payload"]), staging, base_staging_schema())
    _write(
        cast_path(paths["baseline_core"]),
        [item.core_row for item in baseline],
        core_schema(),
    )
    _write(
        cast_path(paths["baseline_evidence"]),
        [row for item in baseline for row in item.evidence_rows],
        evidence_schema(),
    )
    _write(
        cast_path(paths["candidate_core"]),
        [item.core_row for item in candidate],
        core_schema(),
    )
    _write(
        cast_path(paths["candidate_evidence"]),
        [row for item in candidate for row in item.evidence_rows],
        evidence_schema(),
    )
    write_identity_set(
        cast_path(paths["identities"]),
        (_identity(index) for index in range(8)),
        partition="DEVELOPMENT",
        manifest_identity="fictional-manifest",
        sampling_config_fingerprint="fictional-sampling",
    )
    paths["payload_sha"] = hashlib.sha256(
        cast_path(paths["payload"]).read_bytes()
    ).hexdigest()
    paths["identity_sha"] = hashlib.sha256(
        cast_path(paths["identities"]).read_bytes()
    ).hexdigest()
    for role in (
        "baseline_core",
        "baseline_evidence",
        "candidate_core",
        "candidate_evidence",
    ):
        paths[f"{role}_sha"] = hashlib.sha256(
            cast_path(paths[role]).read_bytes()
        ).hexdigest()
    paths["baseline_config"] = baseline[0].core_row["configuration_fingerprint"].hex()
    paths["candidate_config"] = candidate[0].core_row["configuration_fingerprint"].hex()
    return paths


def cast_path(value: Path | str) -> Path:
    assert isinstance(value, Path)
    return value


def _semantics() -> dict[str, RuleEvidenceSemantics]:
    result: dict[str, RuleEvidenceSemantics] = {}
    for version in (
        "phase03_rule_registry_v3",
        "phase03_rule_registry_v5_experimental",
    ):
        for rule in load_rule_registry(registry_version=version).ordered_rules():
            result[rule.rule_id] = RuleEvidenceSemantics(
                confidence=rule.confidence,
                selection_priority=rule.selection_priority,
            )
    return result


def _run(tmp_path: Path, paths: dict[str, Path | str], name: str) -> dict[str, Any]:
    output = tmp_path / name
    profile_development_hypothesis_intersections(
        development_payload_path=cast_path(paths["payload"]),
        baseline_core_path=cast_path(paths["baseline_core"]),
        baseline_evidence_path=cast_path(paths["baseline_evidence"]),
        candidate_core_path=cast_path(paths["candidate_core"]),
        candidate_evidence_path=cast_path(paths["candidate_evidence"]),
        development_identities_path=cast_path(paths["identities"]),
        output_directory=output,
        rule_semantics=_semantics(),
        expected_rows=8,
        expected_targeted_review_rows=1,
        expected_identity_artifact_sha256=str(paths["identity_sha"]),
        expected_payload_sha256=str(paths["payload_sha"]),
        expected_baseline_core_sha256=str(paths["baseline_core_sha"]),
        expected_baseline_evidence_sha256=str(paths["baseline_evidence_sha"]),
        expected_candidate_core_sha256=str(paths["candidate_core_sha"]),
        expected_candidate_evidence_sha256=str(paths["candidate_evidence_sha"]),
        expected_baseline_configuration=str(paths["baseline_config"]),
        expected_candidate_configuration=str(paths["candidate_config"]),
        production=False,
    )
    return json.loads(
        (
            output / "phase03_development_hypothesis_intersection_profile.json"
        ).read_text()
    )


def test_profile_is_deterministic_sanitized_and_does_not_mutate_parser_outputs(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    before = {
        name: hashlib.sha256(cast_path(paths[name]).read_bytes()).hexdigest()
        for name in (
            "payload",
            "baseline_core",
            "baseline_evidence",
            "candidate_core",
            "candidate_evidence",
            "identities",
        )
    }
    first = _run(tmp_path, paths, "first")
    second = _run(tmp_path, paths, "second")
    assert first == second
    assert first["report_schema_version"] == REPORT_SCHEMA_VERSION
    assert first["rows"] == 8
    assert first["hypotheses"]["H3"]["unique_rows"] == 1
    assert first["hypotheses"]["H3"]["orientation_relationship_counts"] == {
        "STREET_THEN_NUMBER": 1
    }
    assert first["hypotheses"]["H3"]["postcode_date_year_exclusion_rows"] == 3
    assert first["hypotheses"]["H3"]["representation_disagreement_exclusion_rows"] == 1
    assert first["hypotheses"]["H3"]["multiple_number_exclusion_rows"] == 1
    assert first["privacy"]["locked_rows_read"] == 0
    serialized = json.dumps(first, sort_keys=True)
    for protected in (
        "Example Street",
        "Unit 7B",
        "fictional-provider",
        str(tmp_path),
        _identity(0).hex(),
    ):
        assert protected not in serialized
    after = {
        name: hashlib.sha256(cast_path(paths[name]).read_bytes()).hexdigest()
        for name in before
    }
    assert after == before


def test_h1_reconstructs_only_unregistered_cross_component_overlap() -> None:
    identity = _identity(20)
    span = (("street_address_line_1", 0, 8),)
    groups = [
        _EvidenceGroup(
            identity,
            1,
            "CONFLICTING_EVIDENCE",
            "STREET",
            "NON_NATIVE",
            "fictional-a",
            True,
            "HIGH",
            "STREET_EXPLICIT_DESIGNATOR_V3",
            "COMPONENT_SPAN_OVERLAP_CONFLICT",
            None,
            span,
        ),
        _EvidenceGroup(
            identity,
            2,
            "CONFLICTING_EVIDENCE",
            "BUILDING",
            "NON_NATIVE",
            "fictional-b",
            False,
            "MEDIUM",
            "BUILDING_EXPLICIT_SEGMENT_V3",
            "COMPONENT_SPAN_OVERLAP_CONFLICT",
            None,
            span,
        ),
    ]
    population, report = _h1_profile(
        core_by_id={
            identity: {
                "address_conflict_flags": ["COMPONENT_SPAN_OVERLAP_CONFLICT"],
                "address_parse_status": "CONFLICT",
            }
        },
        groups_by_id={identity: groups},
    )
    assert population == {identity}
    assert report["unique_rows"] == 1
    assert report["selected_value_affected_rows"] == 1
    assert report["overlap_component_pairs"] == {
        "BUILDING+STREET": {"unique_rows": 1, "pair_memberships": 1}
    }


def test_intersection_regions_are_unique_identity_counts() -> None:
    ids = [_identity(index) for index in range(6)]
    report = _intersection_report(
        {
            "H1": {ids[0], ids[1], ids[5]},
            "H2": {ids[1], ids[2], ids[5]},
            "H3": {ids[3], ids[4], ids[5]},
        }
    )
    assert report["matrix"]["H1"]["H2"] == 2
    assert report["exclusive_regions"]["H1_H2_ONLY"]["rows"] == 1
    assert report["exclusive_regions"]["H1_H2_H3"]["rows"] == 1
    assert report["union"]["rows"] == 6


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2024", "YEAR_STYLE"),
        ("12/05", "DATE_STYLE"),
        ("12/3", None),
        ("42", None),
    ],
)
def test_date_and_year_exclusions_are_closed(value: str, expected: str | None) -> None:
    assert _date_or_year_reason(value) == expected


def test_production_guard_precedes_input_open(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def forbidden(path: Path) -> tuple[int, str]:
        raise AssertionError(f"protected input opened: {path.name}")

    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setattr(
        "safe_geocoding_pipeline.phase03.development_hypothesis_intersection_profiler._artifact_state",
        forbidden,
    )
    with pytest.raises(ExecutionPolicyError, match="HEAVY_PROCESS_CLUSTER_REQUIRED"):
        profile_development_hypothesis_intersections(
            development_payload_path=tmp_path / "payload.parquet",
            baseline_core_path=tmp_path / "baseline-core.parquet",
            baseline_evidence_path=tmp_path / "baseline-evidence.parquet",
            candidate_core_path=tmp_path / "candidate-core.parquet",
            candidate_evidence_path=tmp_path / "candidate-evidence.parquet",
            development_identities_path=tmp_path / "identities.bin",
            output_directory=tmp_path / "output",
            rule_semantics={},
            production=True,
        )


def test_locked_paths_are_rejected(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    with pytest.raises(ValueError, match="LOCKED_INPUT_PROHIBITED"):
        profile_development_hypothesis_intersections(
            development_payload_path=tmp_path / "locked" / "payload.parquet",
            baseline_core_path=cast_path(paths["baseline_core"]),
            baseline_evidence_path=cast_path(paths["baseline_evidence"]),
            candidate_core_path=cast_path(paths["candidate_core"]),
            candidate_evidence_path=cast_path(paths["candidate_evidence"]),
            development_identities_path=cast_path(paths["identities"]),
            output_directory=tmp_path / "output",
            rule_semantics=_semantics(),
            expected_rows=8,
            expected_targeted_review_rows=1,
            expected_identity_artifact_sha256=str(paths["identity_sha"]),
            expected_payload_sha256=str(paths["payload_sha"]),
            expected_baseline_core_sha256=str(paths["baseline_core_sha"]),
            expected_baseline_evidence_sha256=str(paths["baseline_evidence_sha"]),
            expected_candidate_core_sha256=str(paths["candidate_core_sha"]),
            expected_candidate_evidence_sha256=str(paths["candidate_evidence_sha"]),
            expected_baseline_configuration=str(paths["baseline_config"]),
            expected_candidate_configuration=str(paths["candidate_config"]),
            production=False,
        )


def test_cli_registration() -> None:
    arguments = build_parser().parse_args(
        [
            "development-hypothesis-intersection-profile",
            "--development-payload",
            "payload.parquet",
            "--baseline-core",
            "baseline-core.parquet",
            "--baseline-evidence",
            "baseline-evidence.parquet",
            "--candidate-core",
            "candidate-core.parquet",
            "--candidate-evidence",
            "candidate-evidence.parquet",
            "--development-identities",
            "identities.bin",
            "--targeted-r01-context",
            "context.parquet",
            "--targeted-r01-labels",
            "labels.parquet",
            "--output-directory",
            "output",
        ]
    )
    assert arguments.command == "development-hypothesis-intersection-profile"


def test_sbatch_is_fail_closed_development_only() -> None:
    script = (
        Path(__file__).parents[1]
        / "cluster/goethe_nhr/phase03_development_hypothesis_intersection_profile.sbatch"
    ).read_text()
    assert "#SBATCH --partition=general1" in script
    assert "export SAFE_EXECUTION_SITE=goethe-nhr" in script
    assert '[[ "${resolved_input,,}" != *locked* ]]' in script
    assert "development-hypothesis-intersection-profile" in script
    assert "--development-identities" in script
    assert "--targeted-r01-context" in script
    assert "--targeted-r01-labels" in script
    assert "pilot-select" not in script
    assert "development-transform" not in script
    assert "locked-evaluation" not in script


def test_population_digest_does_not_expose_identity() -> None:
    identity = _identity(99)
    digest = _population_digest("TEST", {identity})
    assert len(digest) == 64
    assert identity.hex() not in digest
    assert set(ROLE_RULES) == {
        "UNIT_EXPLICIT_SEGMENT_V3",
        "FLOOR_EXPLICIT_SEGMENT_V3",
        "BUILDING_EXPLICIT_SEGMENT_V3",
        "ORGANIZATION_LEGAL_FORM_V3",
    }
