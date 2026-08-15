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
from safe_geocoding_pipeline.phase03.constants import (
    PARSER_VERSION_V2,
    PARSER_VERSION_V3,
)
from safe_geocoding_pipeline.phase03.pilot_runner import write_identity_set
from safe_geocoding_pipeline.phase03.schema import core_schema, evidence_schema
from safe_geocoding_pipeline.phase03.targeted_experiment_review import (
    TARGETED_LABEL_FIELDS,
    TargetedContext,
    TargetedReviewStore,
    export_completed_targeted_labels,
    initialize_targeted_review_workspace,
    prepare_targeted_review_artifacts,
    render_targeted_case,
    score_completed_targeted_review,
    targeted_review_label_schema,
    validate_targeted_labels,
)
from safe_geocoding_pipeline.phase03.targeted_review_cli import (
    _stable_artifact_reference,
    build_parser,
    main,
)


def _identity(index: int) -> bytes:
    return hashlib.sha256(f"fictional-targeted-review:{index}".encode()).digest()


def _staging_row(index: int, raw: str, *, supported: bool) -> dict[str, Any]:
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
            postcode="12345" if supported else "",
            city="Fiction City" if supported else "",
            country_iso_code="XZ",
            source_file="fictional_targeted_review.parquet",
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


def _write(path: Path, rows: list[dict[str, Any]], schema: pa.Schema) -> None:
    pq.write_table(
        pa.Table.from_pylist(rows, schema=schema),
        path,
        compression="zstd",
        write_page_checksum=True,
        write_statistics=False,
    )
    path.chmod(0o600)


def _fixture(tmp_path: Path) -> tuple[dict[str, Path], tuple[str, ...]]:
    raw_values = (
        "Annex 12 Example Street",
        "Wing 7 Sample Road",
        "34 Fiction Avenue",
    )
    staging = [
        _staging_row(0, raw_values[0], supported=True),
        _staging_row(1, raw_values[1], supported=False),
        _staging_row(2, raw_values[2], supported=True),
    ]
    (tmp_path / "v2").mkdir()
    (tmp_path / "v3").mkdir()
    v2 = engine(tmp_path / "v2", parser_version=PARSER_VERSION_V2)
    v3 = engine(tmp_path / "v3", parser_version=PARSER_VERSION_V3)
    v2_results = [v2.transform(row) for row in staging]
    v3_results = [v3.transform(row) for row in staging]
    paths = {
        "payload": tmp_path / "development.parquet",
        "identities": tmp_path / "development.identities.bin",
        "v2_core": tmp_path / "v2-core.parquet",
        "v2_evidence": tmp_path / "v2-evidence.parquet",
        "v3_core": tmp_path / "v3-core.parquet",
        "v3_evidence": tmp_path / "v3-evidence.parquet",
    }
    _write(paths["payload"], staging, base_staging_schema())
    _write(paths["v2_core"], [item.core_row for item in v2_results], core_schema())
    _write(
        paths["v2_evidence"],
        [row for item in v2_results for row in item.evidence_rows],
        evidence_schema(),
    )
    _write(paths["v3_core"], [item.core_row for item in v3_results], core_schema())
    _write(
        paths["v3_evidence"],
        [row for item in v3_results for row in item.evidence_rows],
        evidence_schema(),
    )
    write_identity_set(
        paths["identities"],
        (_identity(index) for index in range(3)),
        partition="DEVELOPMENT",
        manifest_identity="fictional-phase02-manifest",
        sampling_config_fingerprint="fictional-sampling-config",
    )
    return paths, raw_values


def _prepare(tmp_path: Path) -> tuple[Path, dict[str, Path], tuple[str, ...]]:
    paths, raw_values = _fixture(tmp_path)
    output = tmp_path / "prepared"
    prepare_targeted_review_artifacts(
        development_payload_path=paths["payload"],
        development_identities_path=paths["identities"],
        baseline_core_path=paths["v2_core"],
        baseline_evidence_path=paths["v2_evidence"],
        experimental_core_path=paths["v3_core"],
        experimental_evidence_path=paths["v3_evidence"],
        output_directory=output,
        experiment_iteration="fictional_parser_v3_experiment",
        experimental_parser_commit="a" * 40,
        review_implementation_commit="b" * 40,
        expected_development_rows=3,
        expected_population_count=2,
        production=False,
    )
    return output, paths, raw_values


def _valid_labels() -> dict[str, str]:
    return {
        "street_label": "CORRECT",
        "house_number_label": "CORRECT",
        "joint_street_house_label": "CORRECT",
        "residual_role_label": "UNKNOWN_RESIDUAL",
        "candidate_support_label": "SUPPORTED",
        "blind_parse_comparison_label": "BOTH_CORRECT",
        "parser_overreach_label": "ABSENT",
        "missed_information_label": "ABSENT",
        "overall_parse_acceptability_label": "ACCEPTABLE",
    }


def test_population_is_exact_union_deduplicated_and_provenance_bound(
    tmp_path: Path,
) -> None:
    output, paths, raw_values = _prepare(tmp_path)
    context = pq.ParquetFile(
        output / "protected_targeted_review_context.parquet",
        page_checksum_verification=True,
    ).read()
    template = pq.ParquetFile(
        output / "protected_targeted_review_template.parquet",
        page_checksum_verification=True,
    ).read()
    manifest = json.loads((output / "targeted_review_input_manifest.json").read_text())
    assert context.num_rows == template.num_rows == 2
    assert template["is_independent_review"].to_pylist() == [True, True]
    assert manifest["scientific_output_change_rows"] == 1
    assert manifest["experimental_rule_evidence_rows"] == 2
    assert manifest["targeted_review_population_rows"] == 2
    assert manifest["reviewer_1_rows"] == manifest["reviewer_2_rows"] == 2
    assert manifest["locked_rows_read"] == 0
    assert output.stat().st_mode & 0o777 == 0o700
    for artifact_name in (
        "protected_targeted_review_context.parquet",
        "protected_targeted_review_template.parquet",
        "targeted_review_input_manifest.json",
    ):
        assert (output / artifact_name).stat().st_mode & 0o777 == 0o600
    serialized = (output / "targeted_review_input_manifest.json").read_text()
    assert not any(value in serialized for value in raw_values)
    assert str(tmp_path) not in serialized
    assert "fictional-provider" not in serialized
    assert not any(_identity(index).hex() in serialized for index in range(3))
    for path in paths.values():
        assert path.exists()


def test_population_count_mismatch_fails_before_output(tmp_path: Path) -> None:
    paths, _ = _fixture(tmp_path)
    output = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match="TARGETED_REVIEW_POPULATION_COUNT_MISMATCH"):
        prepare_targeted_review_artifacts(
            development_payload_path=paths["payload"],
            development_identities_path=paths["identities"],
            baseline_core_path=paths["v2_core"],
            baseline_evidence_path=paths["v2_evidence"],
            experimental_core_path=paths["v3_core"],
            experimental_evidence_path=paths["v3_evidence"],
            output_directory=output,
            experiment_iteration="fictional_parser_v3_experiment",
            experimental_parser_commit="a" * 40,
            review_implementation_commit="b" * 40,
            expected_development_rows=3,
            expected_population_count=3,
            production=False,
        )
    assert not output.exists()


def test_prepare_rejects_nonuniform_configuration_fingerprint(
    tmp_path: Path,
) -> None:
    paths, _ = _fixture(tmp_path)
    baseline_rows = pq.read_table(paths["v2_core"]).to_pylist()
    baseline_rows[1]["configuration_fingerprint"] = bytes.fromhex("ff" * 32)
    _write(paths["v2_core"], baseline_rows, core_schema())
    output = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match="configuration fingerprint is not uniform"):
        prepare_targeted_review_artifacts(
            development_payload_path=paths["payload"],
            development_identities_path=paths["identities"],
            baseline_core_path=paths["v2_core"],
            baseline_evidence_path=paths["v2_evidence"],
            experimental_core_path=paths["v3_core"],
            experimental_evidence_path=paths["v3_evidence"],
            output_directory=output,
            experiment_iteration="fictional_parser_v3_experiment",
            experimental_parser_commit="a" * 40,
            review_implementation_commit="b" * 40,
            expected_development_rows=3,
            expected_population_count=2,
            production=False,
        )
    assert not output.exists()


def test_production_guard_and_locked_rejection_precede_input_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "missing"
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    with pytest.raises(ExecutionPolicyError):
        prepare_targeted_review_artifacts(
            development_payload_path=missing,
            development_identities_path=missing,
            baseline_core_path=missing,
            baseline_evidence_path=missing,
            experimental_core_path=missing,
            experimental_evidence_path=missing,
            output_directory=tmp_path / "output",
            experiment_iteration="fictional",
            experimental_parser_commit="a" * 40,
            review_implementation_commit="b" * 40,
            expected_development_rows=3,
            expected_population_count=2,
            production=True,
        )
    with pytest.raises(ValueError, match="LOCKED"):
        prepare_targeted_review_artifacts(
            development_payload_path=tmp_path / "locked" / "payload.parquet",
            development_identities_path=missing,
            baseline_core_path=missing,
            baseline_evidence_path=missing,
            experimental_core_path=missing,
            experimental_evidence_path=missing,
            output_directory=tmp_path / "output",
            experiment_iteration="fictional",
            experimental_parser_commit="a" * 40,
            review_implementation_commit="b" * 40,
            expected_development_rows=3,
            expected_population_count=2,
            production=True,
        )


def test_blinded_context_hides_versions_rule_and_selection_state(
    tmp_path: Path,
) -> None:
    output, _, _ = _prepare(tmp_path)
    context = TargetedContext.open(
        output / "protected_targeted_review_context.parquet",
        "fictional_parser_v3_experiment",
    )
    hashed = next(iter(context.by_hashed_id))
    first = context.case(hashed, "Targeted-R01")
    second = context.case(hashed, "Targeted-R02")
    rendered = render_targeted_case(first)
    assert "conservative_address_parser_v2" not in rendered
    assert "conservative_address_parser_v3" not in rendered
    assert "EXPERIMENT_V4" not in rendered
    assert "selected:" not in rendered.casefold()
    assert "provider" not in rendered.casefold()
    assert "stable_source" not in rendered.casefold()
    assert first["parse_a"] in (second["parse_a"], second["parse_b"])


def test_targeted_label_vocabulary_and_cross_field_validation() -> None:
    labels = _valid_labels()
    assert set(labels) == set(TARGETED_LABEL_FIELDS)
    assert validate_targeted_labels(labels, ["CORRECT_AS_IS"], protected_note=None) == (
        "CORRECT_AS_IS",
    )
    unknown = {**labels, "street_label": "MAYBE"}
    with pytest.raises(ValueError, match="street"):
        validate_targeted_labels(unknown, ["CORRECT_AS_IS"], protected_note=None)
    missed = {
        **labels,
        "street_label": "MISSED",
        "missed_information_label": "ABSENT",
    }
    with pytest.raises(ValueError, match="MISSED"):
        validate_targeted_labels(
            missed, ["MISSED_EXTRACTABLE_COMPONENT"], protected_note=None
        )
    uncertain = {**labels, "candidate_support_label": "CANNOT_ASSESS"}
    with pytest.raises(ValueError, match="uncertainty"):
        validate_targeted_labels(
            uncertain, ["OTHER_ADJUDICATION_REQUIRED"], protected_note="note"
        )


def test_independent_reviewers_have_separate_deterministic_orders_and_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared, _, raw_values = _prepare(tmp_path)
    monkeypatch.setattr(
        "safe_geocoding_pipeline.phase03.targeted_experiment_review.current_repository_commit",
        lambda: "b" * 40,
    )
    progress = tmp_path / "progress"
    first_path, second_path = initialize_targeted_review_workspace(
        context_path=prepared / "protected_targeted_review_context.parquet",
        template_path=prepared / "protected_targeted_review_template.parquet",
        manifest_path=prepared / "targeted_review_input_manifest.json",
        output_directory=progress,
        implementation_commit="b" * 40,
    )
    with (
        TargetedReviewStore(first_path) as first,
        TargetedReviewStore(second_path) as second,
    ):
        assert set(first.assignment_ids()) == set(second.assignment_ids())
        assert len(first.assignment_ids()) == len(second.assignment_ids()) == 2
        assert first.metadata()["reviewer_id"] == "Targeted-R01"
        assert second.metadata()["reviewer_id"] == "Targeted-R02"
        first_order = first.assignment_ids()
        second_order = second.assignment_ids()
        for store in (first, second):
            for hashed in store.assignment_ids():
                store.save_completed(
                    hashed,
                    _valid_labels(),
                    ["CORRECT_AS_IS"],
                    protected_note=None,
                )
            assert store.summary()["status"] == "COMPLETE"
    assert first_path.stat().st_mode & 0o777 == 0o600
    assert second_path.stat().st_mode & 0o777 == 0o600
    assert first_path.parent.stat().st_mode & 0o777 == 0o700
    assert second_path.parent.stat().st_mode & 0o777 == 0o700

    repeat = tmp_path / "progress-repeat"
    repeat_first, repeat_second = initialize_targeted_review_workspace(
        context_path=prepared / "protected_targeted_review_context.parquet",
        template_path=prepared / "protected_targeted_review_template.parquet",
        manifest_path=prepared / "targeted_review_input_manifest.json",
        output_directory=repeat,
        implementation_commit="b" * 40,
    )
    with (
        TargetedReviewStore(repeat_first, readonly=True) as first,
        TargetedReviewStore(repeat_second, readonly=True) as second,
    ):
        assert first.assignment_ids() == first_order
        assert second.assignment_ids() == second_order
    export = tmp_path / "controlled-export" / "targeted_labels.parquet"
    export_completed_targeted_labels(
        reviewer_one_database=first_path,
        reviewer_two_database=second_path,
        output_path=export,
    )
    table = pq.ParquetFile(export, page_checksum_verification=True).read()
    assert table.schema.remove_metadata().equals(
        targeted_review_label_schema(), check_metadata=False
    )
    assert table.num_rows == 4
    assert set(table["reviewer_id"].to_pylist()) == {
        "Targeted-R01",
        "Targeted-R02",
    }
    assert table["is_independent_review"].to_pylist() == [True] * 4
    exported_bytes = export.read_bytes()
    assert not any(value.encode() in exported_bytes for value in raw_values)

    score_path = tmp_path / "scores" / "aggregate.json"
    payload = score_completed_targeted_review(
        reviewer_one_database=first_path,
        reviewer_two_database=second_path,
        context_path=prepared / "protected_targeted_review_context.parquet",
        output_path=score_path,
    )
    assert payload["number_reviewed"] == 2
    assert payload["review_completion"] == {
        "Targeted-R01": 2,
        "Targeted-R02": 2,
    }
    assert payload["adjudication_needed_count"] == 0
    assert payload["scientific_promotion_threshold_applied"] is False
    serialized = score_path.read_text()
    assert not any(value in serialized for value in raw_values)
    assert "hashed_review_id" not in serialized
    assert str(tmp_path) not in serialized


def test_prepare_is_deterministic_and_does_not_mutate_parser_outputs(
    tmp_path: Path,
) -> None:
    paths, _ = _fixture(tmp_path)
    before = {name: path.read_bytes() for name, path in paths.items()}
    results = []
    for name in ("prepared-a", "prepared-b"):
        result = prepare_targeted_review_artifacts(
            development_payload_path=paths["payload"],
            development_identities_path=paths["identities"],
            baseline_core_path=paths["v2_core"],
            baseline_evidence_path=paths["v2_evidence"],
            experimental_core_path=paths["v3_core"],
            experimental_evidence_path=paths["v3_evidence"],
            output_directory=tmp_path / name,
            experiment_iteration="fictional_parser_v3_experiment",
            experimental_parser_commit="a" * 40,
            review_implementation_commit="b" * 40,
            expected_development_rows=3,
            expected_population_count=2,
            production=False,
        )
        results.append(result)
    assert results[0].population_digest == results[1].population_digest
    assert results[0].context_path.read_bytes() == results[1].context_path.read_bytes()
    assert (
        results[0].template_path.read_bytes() == results[1].template_path.read_bytes()
    )
    assert before == {name: path.read_bytes() for name, path in paths.items()}


def test_cli_and_cluster_asset_preserve_targeted_review_boundary() -> None:
    parsed = build_parser().parse_args(
        [
            "prepare",
            "--development-payload",
            "development.parquet",
            "--development-identities",
            "development.identities.bin",
            "--baseline-core",
            "v2-core.parquet",
            "--baseline-evidence",
            "v2-evidence.parquet",
            "--experimental-core",
            "v3-core.parquet",
            "--experimental-evidence",
            "v3-evidence.parquet",
            "--output-directory",
            "targeted-review",
            "--experiment-iteration",
            "fictional-experiment",
            "--experimental-parser-commit",
            "a" * 40,
            "--review-implementation-commit",
            "b" * 40,
            "--expected-population-count",
            "26",
        ]
    )
    assert parsed.expected_population_count == 26
    script = Path(
        "cluster/goethe_nhr/phase03_parser_v3_targeted_review_prepare.sbatch"
    ).read_text()
    assert "#SBATCH --cpus-per-task=4" in script
    assert "#SBATCH --mem=16G" in script
    assert "#SBATCH --time=01:00:00" in script
    assert "pilot-select" not in script
    assert "development-transform" not in script
    assert "targeted_review_cli prepare" in script
    assert "TARGETED_REVIEW_LOCKED_PATH_PROHIBITED" in script
    assert "human_labels_created=false" in script


def test_prepare_report_reference_is_relative_and_promotion_stable() -> None:
    attempt_root = Path("controlled/.in_progress/fictional-review")
    artifact = attempt_root / "prepared_inputs" / "protected_context.parquet"
    reference = _stable_artifact_reference(artifact, attempt_root)
    assert reference == "prepared_inputs/protected_context.parquet"
    assert ".in_progress" not in reference
    final_root = Path("controlled/fictional-review")
    assert final_root / reference == (
        final_root / "prepared_inputs" / "protected_context.parquet"
    )


def test_real_cli_fails_before_opening_inputs_outside_goethe_slurm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    with pytest.raises(ExecutionPolicyError):
        main(
            [
                "progress",
                "--progress-database",
                str(tmp_path / "does-not-exist.sqlite3"),
            ]
        )
