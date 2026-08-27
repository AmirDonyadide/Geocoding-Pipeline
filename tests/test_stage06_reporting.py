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
from safe_geocoding_pipeline.preprocessing.reporting.stage06 import (
    STAGE06_REVIEW_PATH,
    STAGE06_SUMMARY_JSON_PATH,
    STAGE06_SUMMARY_MD_PATH,
    Stage06ReviewRunConfig,
    materialize_stage06_development_review,
    stage06_review_schema,
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
from safe_geocoding_pipeline.preprocessing.stages.s06_exact_deduplication import (
    Stage06InputBinding,
    Stage06RunConfig,
    materialize_stage06,
    write_stage06_input_binding,
)
from test_stage04_lowercase import (
    BENCHMARK_FINGERPRINT,
    EXECUTION_GIT_SHA,
    _sha256,
    _stage04_bundle,
    _synthetic_upstream,
)


def test_fixed_500_stage06_machine_verification_and_sanitized_summary(
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
    stage05_binding = Stage05InputBinding(
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
    stage05_binding_path = tmp_path / "bindings" / "stage05.json"
    stage05_binding_sha = write_stage05_input_binding(
        stage05_binding_path, stage05_binding
    )
    stage05 = materialize_stage05(
        Stage05RunConfig(
            stage04_output_directory=stage04_root,
            input_binding_file=stage05_binding_path,
            expected_input_binding_sha256=stage05_binding_sha,
            output_directory=tmp_path / "stage05" / "candidate",
            execution_git_sha=EXECUTION_GIT_SHA,
            production=False,
            authoritative_development=False,
            batch_rows=64,
        )
    )
    stage06_binding = Stage06InputBinding(
        upstream_contract_version="stage05_address_reconstruction_contract_v2",
        upstream_profile_version="stage05_address_reconstruction_profile_v2",
        upstream_logical_fingerprint=stage05.logical_dataset_sha256_v1,
        upstream_schema_fingerprint=stage05.schema_fingerprint,
        upstream_input_binding_sha256=stage05.input_binding_sha256,
        upstream_manifest_sha256=stage05.manifest_sha256,
        upstream_ordered_identity_sha256=stage05.ordered_identity_sha256,
        input_benchmark_fingerprint=BENCHMARK_FINGERPRINT,
        fixed_500_fingerprint=fixed.review_subset_fingerprint,
        expected_row_count=500,
    )
    stage06_binding_path = tmp_path / "bindings" / "stage06.json"
    stage06_binding_sha = write_stage06_input_binding(
        stage06_binding_path, stage06_binding
    )
    stage06 = materialize_stage06(
        Stage06RunConfig(
            stage05_output_directory=stage05.output_directory,
            input_binding_file=stage06_binding_path,
            expected_input_binding_sha256=stage06_binding_sha,
            output_directory=tmp_path / "stage06" / "candidate",
            execution_git_sha=EXECUTION_GIT_SHA,
            production=False,
            authoritative_development=False,
            batch_rows=64,
            registry_batch_rows=64,
            registry_shard_rows=100,
            duckdb_memory_limit="512MB",
        )
    )
    output = tmp_path / "reporting" / "stage06"
    result = materialize_stage06_development_review(
        Stage06ReviewRunConfig(
            stage05_output_directory=stage05.output_directory,
            stage06_output_directory=stage06.output_directory,
            expected_stage06_manifest_sha256=stage06.manifest_sha256,
            development_review_bundle_directory=accepted_review,
            expected_development_review_manifest_sha256=fixed.manifest_sha256,
            expected_review_subset_fingerprint=fixed.review_subset_fingerprint,
            expected_benchmark_fingerprint=BENCHMARK_FINGERPRINT,
            expected_stage02_logical_fingerprint=stage02_logical,
            output_directory=output,
            execution_git_sha=EXECUTION_GIT_SHA,
            performance_metrics={
                "ELAPSED_MILLISECONDS": 1_000,
                "USER_CPU_MILLISECONDS": 800,
                "SYSTEM_CPU_MILLISECONDS": 100,
                "MAX_RSS_KIB": 12_345,
            },
            production=False,
            authoritative_development=False,
            operational_metadata={"slurm_job_id": "12345"},
        )
    )
    fixed_ids = pq.read_table(accepted_review / REVIEW_IDENTITIES_PATH)
    review = pq.read_table(output / STAGE06_REVIEW_PATH)
    assert result.selected_row_count == review.num_rows == 500
    assert result.mismatch_count == 0
    assert review.schema.remove_metadata() == stage06_review_schema()
    for name in (
        "review_order",
        "development_review_id_v1",
        "stable_source_row_id_v1",
    ):
        assert review.column(name).equals(fixed_ids.column(name))
    assert all(
        all(review.column(name).to_pylist())
        for name in stage06_review_schema().names[5:11]
    )
    summary = json.loads((output / STAGE06_SUMMARY_JSON_PATH).read_text())
    assert summary["fixed_500"]["MISMATCHES"] == 0
    assert summary["checks"]["HOLDOUT_ACCESSED"] is False
    assert summary["checks"]["STAGE7_STARTED"] is False
    portable = (output / STAGE06_SUMMARY_JSON_PATH).read_text() + (
        output / STAGE06_SUMMARY_MD_PATH
    ).read_text()
    for forbidden in (
        "Fictional City",
        "fictional-source-",
        "stable_source_row_id_v1",
        "street_address_line_1",
        "МОСКВА",
    ):
        assert forbidden not in portable


def test_stage06_review_prohibits_holdout_path(tmp_path: Path) -> None:
    config = Stage06ReviewRunConfig(
        stage05_output_directory=tmp_path / "stage05",
        stage06_output_directory=tmp_path / "stage06",
        expected_stage06_manifest_sha256="1" * 64,
        development_review_bundle_directory=tmp_path / "holdout",
        expected_development_review_manifest_sha256="2" * 64,
        expected_review_subset_fingerprint="3" * 64,
        expected_benchmark_fingerprint="4" * 64,
        expected_stage02_logical_fingerprint="5" * 64,
        output_directory=tmp_path / "review",
        execution_git_sha=EXECUTION_GIT_SHA,
        production=False,
    )
    with pytest.raises(Exception, match="HOLDOUT_ACCESS_PROHIBITED"):
        config.validate()


def test_stage06_cluster_assets_and_scope_guards() -> None:
    repository = Path(__file__).resolve().parents[1]
    launcher = (
        repository
        / "cluster"
        / "goethe_nhr"
        / "stage06_early_exact_deduplication.sbatch"
    ).read_text()
    bootstrap = (
        repository / "cluster" / "goethe_nhr" / "stage06_bootstrap_env.sh"
    ).read_text()
    for required in (
        "STAGE06_GIT_COMMIT",
        "git symbolic-ref -q HEAD",
        "SAFE_EXECUTION_SITE=goethe-nhr",
        "HOLDOUT_ACCESS_PROHIBITED",
        'DATA_ROOT="$(realpath -e',
        "chmod 0600",
        "stage06_early_exact_deduplication_contract_v1",
        "stage06_early_exact_deduplication_profile_v1",
        "materialize-review",
        "validate-published",
        "ba5829621fc15347d7cd4e168a48587bab896cd0be98924627876ae853dfaff2",
        "fd945163e3be0242c43b98972350904631279cb99f366baadb0a3094ab6a1fc5",
        "014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52",
    ):
        assert required in launcher
    assert "Python 3.14.3" in bootstrap
    assert 'pyarrow.__version__ == "25.0.0"' in bootstrap
    assert "validate_stage06_runtime" in bootstrap
    assert "libpostal" not in launcher.casefold()
    assert "geocode" not in launcher.casefold()
    protected = (
        "data/controlled/development/stage06/stage06_fixed500_verification.parquet"
    )
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
