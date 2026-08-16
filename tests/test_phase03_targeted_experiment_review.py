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
    PARSER_VERSION_V2_1,
    PARSER_VERSION_V3_1,
)
from safe_geocoding_pipeline.phase03.development_comparison import (
    _SCIENTIFIC_CORE_FIELDS as COMPARISON_SCIENTIFIC_CORE_FIELDS,
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
from safe_geocoding_pipeline.phase03.targeted_review_population import (
    EXPERIMENTAL_RULE_IDS,
    ArtifactPin,
    PopulationExpectation,
    SCIENTIFIC_CORE_FIELDS,
    compute_targeted_population,
    development_identity_order_digest,
    file_sha256,
    validate_population_expectation,
    verify_repaired_targeted_review_population,
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
    v2 = engine(tmp_path / "v2", parser_version=PARSER_VERSION_V2_1)
    v3 = engine(tmp_path / "v3", parser_version=PARSER_VERSION_V3_1)
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


def _initialize_synthetic_targeted_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path, tuple[str, ...]]:
    prepared, _, raw_values = _prepare(tmp_path)
    monkeypatch.setattr(
        "safe_geocoding_pipeline.phase03.targeted_experiment_review.current_repository_commit",
        lambda: "b" * 40,
    )
    first_path, second_path = initialize_targeted_review_workspace(
        context_path=prepared / "protected_targeted_review_context.parquet",
        template_path=prepared / "protected_targeted_review_template.parquet",
        manifest_path=prepared / "targeted_review_input_manifest.json",
        output_directory=tmp_path / "progress",
        implementation_commit="b" * 40,
    )
    return prepared, first_path, second_path, raw_values


def _use_synthetic_single_reviewer_expectation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from safe_geocoding_pipeline.phase03 import targeted_experiment_review as module

    assert module.REPAIRED_POPULATION_EXPECTATION.union_rows == 11
    monkeypatch.setattr(
        module,
        "REPAIRED_POPULATION_EXPECTATION",
        PopulationExpectation(3, 1, 2, 1, 0, 1, 2, 2, 1),
    )
    monkeypatch.setattr(
        module, "REPAIRED_ITERATION_ID", "fictional_parser_v3_experiment"
    )


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


def test_repaired_population_definition_reports_exact_a_union_b(
    tmp_path: Path,
) -> None:
    assert SCIENTIFIC_CORE_FIELDS == COMPARISON_SCIENTIFIC_CORE_FIELDS
    paths, _ = _fixture(tmp_path)
    baseline = pq.read_table(paths["v2_core"]).to_pylist()
    experimental = pq.read_table(paths["v3_core"]).to_pylist()
    evidence = pq.read_table(paths["v3_evidence"]).to_pylist()
    population = compute_targeted_population(baseline, experimental, evidence)
    assert len(population.changed_ids) == 1
    assert len(population.evidence_ids) == 2
    assert population.overlap_rows == 1
    assert population.changed_only_rows == 0
    assert population.evidence_only_rows == 1
    assert len(population.population) == 2
    assert population.country_parse_method_only_rows == 0
    assert population.country_parse_method_changed_rows == 0
    assert population.rule_candidate_groups == {
        rule_id: 2 for rule_id in EXPERIMENTAL_RULE_IDS
    }
    assert population.rule_selected_candidate_groups == {
        rule_id: 1 for rule_id in EXPERIMENTAL_RULE_IDS
    }
    with pytest.raises(
        ValueError, match="REPAIRED_TARGETED_REVIEW_POPULATION_MISMATCH"
    ):
        validate_population_expectation(
            population,
            PopulationExpectation(3, 26, 11, 9, 17, 2, 28, 22, 9),
        )


def test_repaired_population_verifier_is_sanitized_and_creates_no_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from safe_geocoding_pipeline.phase03 import targeted_review_population as module

    paths, raw_values = _fixture(tmp_path)
    baseline = pq.read_table(paths["v2_core"]).to_pylist()
    experimental = pq.read_table(paths["v3_core"]).to_pylist()
    identity_digest = development_identity_order_digest(baseline)
    repair_success = tmp_path / "repair-success.json"
    repair_success.write_text(
        json.dumps(
            {
                "status": "DEVELOPMENT_COUNTRY_METHOD_REPAIR_COMPARISON_COMPLETE",
                "iteration_id": module.REPAIRED_ITERATION_ID,
                "git_commit": module.REPAIRED_EXECUTION_COMMIT,
                "development_rows": 3,
                "locked_payload_rows_read": 0,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    repair_comparison = tmp_path / "repair-comparison.json"
    repair_comparison.write_text(
        json.dumps(
            {
                "status": "EXPERIMENTAL_COMPARISON_COMPLETE_NO_PROMOTION_DECISION",
                "rows": 3,
                "identity_order_equal": True,
                "identity_digest": identity_digest,
                "baseline": {
                    "parser_version": PARSER_VERSION_V2_1,
                    "rule_registry_version": "phase03_rule_registry_v3",
                    "configuration_fingerprint": bytes(
                        baseline[0]["configuration_fingerprint"]
                    ).hex(),
                    "core_sha256": file_sha256(paths["v2_core"]),
                    "evidence_sha256": file_sha256(paths["v2_evidence"]),
                },
                "experimental": {
                    "parser_version": PARSER_VERSION_V3_1,
                    "rule_registry_version": "phase03_rule_registry_v4_experimental",
                    "configuration_fingerprint": bytes(
                        experimental[0]["configuration_fingerprint"]
                    ).hex(),
                    "core_sha256": file_sha256(paths["v3_core"]),
                    "evidence_sha256": file_sha256(paths["v3_evidence"]),
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    verifier_paths = {
        "development_identities": paths["identities"],
        "baseline_core": paths["v2_core"],
        "baseline_evidence": paths["v2_evidence"],
        "experimental_core": paths["v3_core"],
        "experimental_evidence": paths["v3_evidence"],
        "repair_success": repair_success,
        "repair_comparison": repair_comparison,
    }
    monkeypatch.setattr(
        module,
        "REPAIRED_ARTIFACT_PINS",
        {
            role: ArtifactPin(file_sha256(path), path.stat().st_size)
            for role, path in verifier_paths.items()
        },
    )
    monkeypatch.setattr(
        module,
        "REPAIRED_POPULATION_EXPECTATION",
        PopulationExpectation(3, 1, 2, 1, 0, 1, 2, 2, 1),
    )
    monkeypatch.setattr(
        module, "REPAIRED_DEVELOPMENT_IDENTITY_ORDER_DIGEST", identity_digest
    )
    monkeypatch.setattr(
        module,
        "REPAIRED_BASELINE_CONFIGURATION_FINGERPRINT",
        bytes(baseline[0]["configuration_fingerprint"]).hex(),
    )
    monkeypatch.setattr(
        module,
        "REPAIRED_EXPERIMENTAL_CONFIGURATION_FINGERPRINT",
        bytes(experimental[0]["configuration_fingerprint"]).hex(),
    )
    output = tmp_path / "report" / "population.json"
    payload = verify_repaired_targeted_review_population(
        development_identities_path=paths["identities"],
        baseline_core_path=paths["v2_core"],
        baseline_evidence_path=paths["v2_evidence"],
        experimental_core_path=paths["v3_core"],
        experimental_evidence_path=paths["v3_evidence"],
        repair_success_path=repair_success,
        repair_comparison_path=repair_comparison,
        output_path=output,
        verification_implementation_commit="b" * 40,
        verification_implementation_fingerprint="c" * 64,
        production=False,
    )
    assert payload["scientific_output_change_rows"] == 1
    assert payload["experimental_rule_evidence_rows"] == 2
    assert payload["overlap_rows"] == 1
    assert payload["changed_only_rows"] == 0
    assert payload["evidence_only_rows"] == 1
    assert payload["targeted_review_population_rows"] == 2
    assert payload["locked_rows_read"] == 0
    assert payload["review_inputs_created"] is False
    assert payload["review_databases_created"] is False
    serialized = output.read_text(encoding="utf-8")
    assert str(tmp_path) not in serialized
    assert "stable_source_row_id_v1" not in serialized
    assert not any(
        identity.hex() in serialized for identity in map(_identity, range(3))
    )
    assert not any(raw in serialized for raw in raw_values)


def test_repaired_population_verifier_rejects_resolved_locked_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from safe_geocoding_pipeline.phase03 import targeted_review_population as module

    locked_root = tmp_path / "locked-evaluation"
    locked_root.mkdir()
    protected = locked_root / "identities.bin"
    protected.write_bytes(b"synthetic-only")
    alias_root = tmp_path / "development-alias"
    alias_root.symlink_to(locked_root, target_is_directory=True)
    aliased = alias_root / protected.name
    monkeypatch.setattr(
        module,
        "REPAIRED_ARTIFACT_PINS",
        {
            **module.REPAIRED_ARTIFACT_PINS,
            "development_identities": ArtifactPin(
                file_sha256(aliased), aliased.stat().st_size
            ),
        },
    )
    with pytest.raises(ValueError, match="LOCKED paths are prohibited"):
        verify_repaired_targeted_review_population(
            development_identities_path=aliased,
            baseline_core_path=tmp_path / "missing-baseline-core",
            baseline_evidence_path=tmp_path / "missing-baseline-evidence",
            experimental_core_path=tmp_path / "missing-experimental-core",
            experimental_evidence_path=tmp_path / "missing-experimental-evidence",
            repair_success_path=tmp_path / "missing-success",
            repair_comparison_path=tmp_path / "missing-comparison",
            output_path=tmp_path / "report.json",
            verification_implementation_commit="b" * 40,
            verification_implementation_fingerprint="c" * 64,
            production=False,
        )


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
    from safe_geocoding_pipeline.phase03 import targeted_experiment_review as module

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
    exported_file = pq.ParquetFile(export, page_checksum_verification=True)
    table = exported_file.read()
    assert table.schema.remove_metadata().equals(
        targeted_review_label_schema(), check_metadata=False
    )
    assert table.num_rows == 4
    assert set(table["reviewer_id"].to_pylist()) == {
        "Targeted-R01",
        "Targeted-R02",
    }
    assert table["is_independent_review"].to_pylist() == [True] * 4
    assert exported_file.schema_arrow.metadata is None
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
    assert payload["report_version"] == module.TARGETED_SCORE_VERSION
    assert payload["status"] == (
        "TARGETED_REVIEW_SCORED_NO_PROMOTION_THRESHOLD_APPLIED"
    )
    assert payload["review_completion"] == {
        "Targeted-R01": 2,
        "Targeted-R02": 2,
    }
    assert payload["adjudication_needed_count"] == 0
    assert payload["scientific_promotion_threshold_applied"] is False
    assert "review_design" not in payload
    assert "independent_second_review" not in payload
    serialized = score_path.read_text()
    assert not any(value in serialized for value in raw_values)
    assert "hashed_review_id" not in serialized
    assert str(tmp_path) not in serialized


def test_completed_r01_only_export_and_score_are_explicit_and_do_not_open_r02(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from safe_geocoding_pipeline.phase03 import targeted_experiment_review as module

    prepared, first_path, second_path, raw_values = (
        _initialize_synthetic_targeted_review(tmp_path, monkeypatch)
    )
    _use_synthetic_single_reviewer_expectation(monkeypatch)
    protected_note = "private synthetic adjudication note"
    with TargetedReviewStore(first_path) as first:
        for hashed in first.assignment_ids():
            first.save_completed(
                hashed,
                _valid_labels(),
                ["OTHER_ADJUDICATION_REQUIRED"],
                protected_note=protected_note,
            )
    second_before = (second_path.read_bytes(), second_path.stat().st_mtime_ns)
    original_init = TargetedReviewStore.__init__
    opened_databases: list[Path] = []

    def tracked_init(
        self: TargetedReviewStore, path: Path, *, readonly: bool = False
    ) -> None:
        opened_databases.append(path)
        if path == second_path:
            raise AssertionError(
                "Targeted-R02 must not be opened in single-reviewer mode"
            )
        original_init(self, path, readonly=readonly)

    monkeypatch.setattr(TargetedReviewStore, "__init__", tracked_init)
    export = tmp_path / "single-export" / "targeted_labels.parquet"
    export_completed_targeted_labels(
        reviewer_one_database=first_path,
        reviewer_two_database=None,
        output_path=export,
        single_reviewer=True,
    )
    parquet = pq.ParquetFile(export, page_checksum_verification=True)
    table = parquet.read()
    assert table.num_rows == 2
    assert table.schema.remove_metadata().equals(
        targeted_review_label_schema(), check_metadata=False
    )
    assert table["reviewer_id"].to_pylist() == ["Targeted-R01"] * 2
    assert table["assignment_role"].to_pylist() == ["PRIMARY"] * 2
    assert table["is_independent_review"].to_pylist() == [True] * 2
    metadata = {
        key.decode("utf-8"): value.decode("utf-8")
        for key, value in (parquet.schema_arrow.metadata or {}).items()
    }
    assert metadata == {
        "evaluation_version": module.TARGETED_SINGLE_REVIEW_EXPORT_VERSION,
        "evaluation_implementation_commit": "b" * 40,
        "evaluation_implementation_fingerprint": (
            module.targeted_review_implementation_fingerprint()
        ),
        "review_input_implementation_commit": "b" * 40,
        "review_input_implementation_fingerprint": (
            module.targeted_review_implementation_fingerprint()
        ),
        "review_design": "SINGLE_REVIEWER",
        "primary_reviewer": "Targeted-R01",
        "primary_review_complete": "true",
        "primary_review_rows": "2",
        "independent_second_review": "SKIPPED_BY_EXPLICIT_DECISION",
        "independent_second_review_rows": "0",
        "inter_reviewer_agreement": "NOT_EVALUATED",
        "independent_double_review_completed": "false",
        "locked_rows_read": "0",
        "scientific_scope": "DEVELOPMENT_ONLY",
    }

    score_path = tmp_path / "single-score" / "aggregate.json"
    payload = score_completed_targeted_review(
        reviewer_one_database=first_path,
        reviewer_two_database=None,
        context_path=prepared / "protected_targeted_review_context.parquet",
        output_path=score_path,
        single_reviewer=True,
    )
    assert payload["report_version"] == module.TARGETED_SINGLE_REVIEW_SCORE_VERSION
    assert payload["status"] == (
        "TARGETED_SINGLE_REVIEWER_SCORED_NO_PROMOTION_THRESHOLD_APPLIED"
    )
    assert payload["review_design"] == "SINGLE_REVIEWER"
    assert payload["primary_reviewer"] == "Targeted-R01"
    assert payload["primary_review_complete"] is True
    assert payload["primary_review_rows"] == 2
    assert payload["independent_second_review"] == ("SKIPPED_BY_EXPLICIT_DECISION")
    assert payload["independent_second_review_rows"] == 0
    assert payload["inter_reviewer_agreement"] == "NOT_EVALUATED"
    assert payload["reviewer_agreement"] == "NOT_EVALUATED"
    assert payload["adjudication_needed_count"] is None
    assert payload["independent_double_review_completed"] is False
    assert payload["locked_rows_read"] == 0
    assert payload["scientific_scope"] == "DEVELOPMENT_ONLY"
    assert payload["scientific_promotion_threshold_applied"] is False
    assert payload["scientific_promotion_decision"] == "NOT_EVALUATED"
    assert payload["evaluation_implementation_commit"] == "b" * 40
    assert payload["review_input_implementation_commit"] == "b" * 40
    assert set(payload["per_reviewer"]) == {"Targeted-R01"}
    serialized_outputs = export.read_bytes() + score_path.read_bytes()
    assert protected_note.encode("utf-8") not in serialized_outputs
    assert not any(value.encode("utf-8") in serialized_outputs for value in raw_values)
    assert second_before == (second_path.read_bytes(), second_path.stat().st_mtime_ns)
    assert second_path not in opened_databases
    assert set(opened_databases) == {first_path}


def test_single_reviewer_mode_fails_closed_for_incomplete_or_wrong_reviewer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared, first_path, second_path, _ = _initialize_synthetic_targeted_review(
        tmp_path, monkeypatch
    )
    _use_synthetic_single_reviewer_expectation(monkeypatch)
    with pytest.raises(ValueError, match="exactly 2 completed assignments"):
        export_completed_targeted_labels(
            reviewer_one_database=first_path,
            reviewer_two_database=None,
            output_path=tmp_path / "incomplete" / "labels.parquet",
            single_reviewer=True,
        )
    with pytest.raises(ValueError, match="Targeted-R01 with PRIMARY role"):
        export_completed_targeted_labels(
            reviewer_one_database=second_path,
            reviewer_two_database=None,
            output_path=tmp_path / "wrong-reviewer" / "labels.parquet",
            single_reviewer=True,
        )
    assert not (tmp_path / "incomplete").exists()
    assert not (tmp_path / "wrong-reviewer").exists()
    assert not (tmp_path / "score").exists()
    with pytest.raises(ValueError, match="prohibits a reviewer-two database"):
        score_completed_targeted_review(
            reviewer_one_database=first_path,
            reviewer_two_database=second_path,
            context_path=prepared / "protected_targeted_review_context.parquet",
            output_path=tmp_path / "score" / "aggregate.json",
            single_reviewer=True,
        )
    with pytest.raises(ValueError, match="requires a reviewer-two database"):
        export_completed_targeted_labels(
            reviewer_one_database=first_path,
            reviewer_two_database=None,
            output_path=tmp_path / "implicit-single" / "labels.parquet",
            single_reviewer=False,
        )


def test_single_reviewer_mode_rejects_locked_paths_before_open(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="LOCKED"):
        export_completed_targeted_labels(
            reviewer_one_database=tmp_path / "locked" / "Targeted-R01.sqlite3",
            reviewer_two_database=None,
            output_path=tmp_path / "must-not-exist.parquet",
            single_reviewer=True,
        )
    assert not (tmp_path / "must-not-exist.parquet").exists()


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
            "--population-verification-report",
            "population-verification.json",
            "--output-directory",
            "targeted-review",
            "--experiment-iteration",
            "fictional-experiment",
            "--experimental-parser-commit",
            "a" * 40,
            "--review-implementation-commit",
            "b" * 40,
        ]
    )
    assert parsed.population_verification_report == Path("population-verification.json")
    single_export = build_parser().parse_args(
        [
            "export-controlled-labels",
            "--single-reviewer",
            "--reviewer-one-database",
            "Targeted-R01.sqlite3",
            "--output",
            "single-reviewer-labels.parquet",
        ]
    )
    assert single_export.single_reviewer is True
    assert single_export.reviewer_one_database == Path("Targeted-R01.sqlite3")
    assert single_export.reviewer_two_database is None
    single_score = build_parser().parse_args(
        [
            "score",
            "--single-reviewer",
            "--reviewer-one-database",
            "Targeted-R01.sqlite3",
            "--protected-context",
            "context.parquet",
            "--output",
            "single-reviewer-score.json",
        ]
    )
    assert single_score.single_reviewer is True
    assert single_score.reviewer_two_database is None
    script = Path(
        "cluster/goethe_nhr/phase03_parser_v3_targeted_review_prepare.sbatch"
    ).read_text()
    assert "#SBATCH --cpus-per-task=4" in script
    assert "#SBATCH --mem=16G" in script
    assert "#SBATCH --time=01:00:00" in script
    assert "pilot-select" not in script
    assert "development-transform" not in script
    assert "targeted_review_cli prepare" in script
    assert "EXPECTED_POPULATION_COUNT=11" in script
    assert "PHASE03_TARGETED_REVIEW_EXPECTED_COUNT" not in script
    assert "RESOLVED_POPULATION_REPORT_ROOT" in script
    assert "conservative_address_parser_v2_1" not in script
    assert "phase03_development_country_method_repair_20260816" in script
    verifier = Path(
        "cluster/goethe_nhr/phase03_parser_v3_targeted_review_population_verify.sbatch"
    ).read_text()
    assert "verify-repaired-population" in verifier
    assert "expected_population=9/11/9/0/2/11" in verifier
    assert "RESOLVED_REPAIR_REPORT_ROOT" in verifier
    assert "review_inputs_created=false" in verifier
    assert "review_databases_created=false" in verifier
    assert "pilot-select" not in verifier
    assert "locked" in verifier.casefold()
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
    with pytest.raises(ExecutionPolicyError):
        main(
            [
                "verify-repaired-population",
                "--development-identities",
                str(tmp_path / "missing-identities"),
                "--baseline-core",
                str(tmp_path / "missing-baseline-core"),
                "--baseline-evidence",
                str(tmp_path / "missing-baseline-evidence"),
                "--experimental-core",
                str(tmp_path / "missing-experimental-core"),
                "--experimental-evidence",
                str(tmp_path / "missing-experimental-evidence"),
                "--repair-success",
                str(tmp_path / "missing-success"),
                "--repair-comparison",
                str(tmp_path / "missing-comparison"),
                "--output",
                str(tmp_path / "must-not-exist.json"),
            ]
        )
    assert not (tmp_path / "must-not-exist.json").exists()
