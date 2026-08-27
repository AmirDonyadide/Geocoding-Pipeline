from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pyarrow.parquet as pq
import pytest

import safe_geocoding_pipeline.preprocessing.stages.s05_reconstruction as stage05_module
from safe_geocoding_pipeline.preprocessing.reporting.contracts import ReviewSubsetConfig
from safe_geocoding_pipeline.preprocessing.reporting.development import (
    REVIEW_IDENTITIES_PATH,
    DevelopmentReviewRunConfig,
    materialize_stage02_development_review,
)
from safe_geocoding_pipeline.preprocessing.reporting.stage05 import (
    STAGE05_REVIEW_PATH,
    STAGE05_SUMMARY_JSON_PATH,
    STAGE05_SUMMARY_MD_PATH,
    Stage05ReviewRunConfig,
    materialize_stage05_development_review,
    stage05_review_schema,
)
from safe_geocoding_pipeline.preprocessing.reporting.summary import (
    render_summary_json,
    render_summary_markdown,
    validate_sanitized_summary_payload,
)
from safe_geocoding_pipeline.preprocessing.stages.s04_lowercase import (
    STAGE04_CONTRACT_VERSION,
    STAGE04_PROFILE_VERSION,
    stage04_schema_fingerprint,
)
from safe_geocoding_pipeline.preprocessing.stages.s05_reconstruction import (
    Stage05InputBinding,
    Stage05RunConfig,
    materialize_stage05,
    write_stage05_input_binding,
)
from test_stage04_lowercase import (
    BENCHMARK_FINGERPRINT,
    EXECUTION_GIT_SHA,
    _sha256,
    _stage04_bundle,
    _synthetic_upstream,
)


def test_fixed_500_stage05_review_and_sanitized_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (
        stage03_root,
        stage03_manifest,
        stage03_logical,
        stage03_binding,
        ordered,
        benchmark_path,
        stage02_root,
        stage02_logical,
    ) = _synthetic_upstream(tmp_path, row_count=500)
    stage02_manifest = json.loads(
        (stage02_root / "_SUCCESS.json").read_text(encoding="utf-8")
    )["stage02_manifest_sha256"]
    accepted_review = tmp_path / "reporting" / "review_v1"
    fixed = materialize_stage02_development_review(
        DevelopmentReviewRunConfig(
            benchmark_development_artifact=benchmark_path,
            expected_benchmark_artifact_sha256=_sha256(benchmark_path),
            benchmark_fingerprint=BENCHMARK_FINGERPRINT,
            stage02_output_directory=stage02_root,
            expected_stage02_manifest_sha256=stage02_manifest,
            expected_stage02_logical_fingerprint=stage02_logical,
            output_directory=accepted_review,
            execution_git_sha=EXECUTION_GIT_SHA,
            subset_config=ReviewSubsetConfig(
                target_count=500, expected_development_rows=500
            ),
            production=False,
        )
    )
    stage04_root, stage04_manifest, stage04_logical, stage04_binding = _stage04_bundle(
        tmp_path,
        stage03_root,
        stage03_manifest,
        stage03_logical,
        stage03_binding,
        ordered,
        row_count=500,
    )
    stage04_outcome = SimpleNamespace(
        logical_dataset_sha256_v1=stage04_logical,
        schema_fingerprint=stage04_schema_fingerprint(),
        input_binding_sha256=stage04_binding,
        ordered_identity_sha256=ordered,
        row_count=500,
    )
    monkeypatch.setattr(
        stage05_module,
        "validate_stage04_bundle",
        lambda *args, **kwargs: stage04_outcome,
    )
    binding = Stage05InputBinding(
        upstream_contract_version=STAGE04_CONTRACT_VERSION,
        upstream_profile_version=STAGE04_PROFILE_VERSION,
        upstream_logical_fingerprint=stage04_logical,
        upstream_schema_fingerprint=stage04_schema_fingerprint(),
        upstream_input_binding_sha256=stage04_binding,
        upstream_manifest_sha256=stage04_manifest,
        upstream_ordered_identity_sha256=ordered,
        input_benchmark_fingerprint=BENCHMARK_FINGERPRINT,
        expected_row_count=500,
    )
    binding_path = tmp_path / "stage05_binding" / "input.json"
    binding_sha = write_stage05_input_binding(binding_path, binding)
    stage05_outcome = materialize_stage05(
        Stage05RunConfig(
            stage04_output_directory=stage04_root,
            input_binding_file=binding_path,
            expected_input_binding_sha256=binding_sha,
            output_directory=tmp_path / "stage05" / "candidate",
            execution_git_sha=EXECUTION_GIT_SHA,
            production=False,
            authoritative_development=False,
            batch_rows=64,
        )
    )
    output = tmp_path / "reporting" / "stage05"
    result = materialize_stage05_development_review(
        Stage05ReviewRunConfig(
            stage04_output_directory=stage04_root,
            expected_stage04_manifest_sha256=stage04_manifest,
            stage05_output_directory=stage05_outcome.output_directory,
            expected_stage05_manifest_sha256=stage05_outcome.manifest_sha256,
            development_review_bundle_directory=accepted_review,
            expected_development_review_manifest_sha256=fixed.manifest_sha256,
            expected_review_subset_fingerprint=fixed.review_subset_fingerprint,
            expected_benchmark_fingerprint=BENCHMARK_FINGERPRINT,
            expected_stage02_logical_fingerprint=stage02_logical,
            output_directory=output,
            execution_git_sha=EXECUTION_GIT_SHA,
            performance_metrics={
                "ELAPSED_MILLISECONDS": 1_000,
                "USER_CPU_MILLISECONDS": 500,
                "SYSTEM_CPU_MILLISECONDS": 100,
                "MAX_RSS_KIB": 12_345,
            },
            production=False,
            authoritative_development=False,
            operational_metadata={"slurm_job_id": "12345"},
        )
    )
    fixed_ids = pq.read_table(
        accepted_review / REVIEW_IDENTITIES_PATH,
        columns=["stable_source_row_id_v1"],
    ).column(0)
    review = pq.read_table(output / STAGE05_REVIEW_PATH)
    assert result.selected_row_count == review.num_rows == 500
    assert review.column("stable_source_row_id_v1").equals(fixed_ids)
    assert review.schema.remove_metadata().equals(
        stage05_review_schema(), check_metadata=False
    )
    assert result.qualitative_classifications["QUESTIONABLE_BOUNDARY"] == 0
    assert result.qualitative_classifications["QUESTIONABLE_ORDER"] == 0
    assert result.qualitative_classifications["SEMANTIC_DAMAGE"] == 0
    summary_json = (output / STAGE05_SUMMARY_JSON_PATH).read_text(encoding="utf-8")
    summary_markdown = (output / STAGE05_SUMMARY_MD_PATH).read_text(encoding="utf-8")
    summary = validate_sanitized_summary_payload(json.loads(summary_json))
    assert summary_json == render_summary_json(summary)
    assert summary_markdown == render_summary_markdown(summary)
    assert summary.status == (
        "STAGE_5_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW"
    )
    assert summary.checks["ALL_STAGE04_FIELDS_UNCHANGED"] is True
    assert summary.checks["NO_STAGE06_DEDUPLICATION"] is True
    assert summary.checks["NO_STAGE07_PARSING"] is True
    assert summary.metric_groups["PERFORMANCE"]["ROWS_PER_SECOND_MILLI"] == 500_000
    portable = summary_json + summary_markdown
    for forbidden in (
        "Fictional City",
        "fictional-source-",
        "stable_source_row_id_v1",
        "street_address_line_1",
        "МОСКВА",
    ):
        assert forbidden not in portable


def test_stage05_review_prohibits_holdout_path(tmp_path: Path) -> None:
    config = Stage05ReviewRunConfig(
        stage04_output_directory=tmp_path / "stage04",
        expected_stage04_manifest_sha256="1" * 64,
        stage05_output_directory=tmp_path / "stage05",
        expected_stage05_manifest_sha256="2" * 64,
        development_review_bundle_directory=tmp_path / "holdout",
        expected_development_review_manifest_sha256="3" * 64,
        expected_review_subset_fingerprint="4" * 64,
        expected_benchmark_fingerprint="5" * 64,
        expected_stage02_logical_fingerprint="6" * 64,
        output_directory=tmp_path / "review",
        execution_git_sha=EXECUTION_GIT_SHA,
        production=False,
    )
    try:
        config.validate()
    except Exception as error:
        assert "HOLDOUT_ACCESS_PROHIBITED" in str(error)
    else:  # pragma: no cover - fail-closed guard must reject the path
        raise AssertionError("HOLDOUT path was not rejected")


def test_stage05_cluster_assets_and_scope_guards() -> None:
    repository = Path(__file__).resolve().parents[1]
    launcher = (
        repository / "cluster" / "goethe_nhr" / "stage05_address_reconstruction.sbatch"
    ).read_text(encoding="utf-8")
    bootstrap = (
        repository / "cluster" / "goethe_nhr" / "stage05_bootstrap_env.sh"
    ).read_text(encoding="utf-8")
    for required in (
        "STAGE05_GIT_COMMIT",
        "git symbolic-ref -q HEAD",
        "SAFE_EXECUTION_SITE=goethe-nhr",
        "HOLDOUT_ACCESS_PROHIBITED",
        'DATA_ROOT="$(realpath -e',
        "stage05_address_reconstruction_contract_v1",
        "stage05_address_reconstruction_profile_v1",
        "materialize-review",
        "validate-published",
        "054c66701f854a0108938170e1cb9bcee8a772f7fed29b82cda53c71aa9747ec",
        "17a4854cddd8929b65ea79402f1a4f12a1574b720c1921567b577f23e152d1f3",
        "fe2a4758582c1880d2b5c62dfc5c587d865e05d13033af9f5e8208b58e2a0487",
    ):
        assert required in launcher
    assert "Python 3.14.3" in bootstrap
    assert 'pyarrow.__version__ == "25.0.0"' in bootstrap
    assert "validate_stage05_runtime" in bootstrap
    assert "stage06" not in launcher.casefold()
    assert "production" not in launcher.casefold()
    protected = "data/controlled/development/stage05/stage05_review.parquet"
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "--", protected],
        cwd=repository,
        check=False,
    )
    assert ignored.returncode == 0
    tracked = subprocess.run(
        ["git", "ls-files", "--", "data/controlled"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    assert tracked.stdout == ""
