from __future__ import annotations

import json
import subprocess
from pathlib import Path

import duckdb
import pyarrow as pa
import pytest

import safe_geocoding_pipeline.preprocessing.stages.s06_design_diagnostic as diagnostic
from safe_geocoding_pipeline.preprocessing.stages.s06_design_diagnostic import (
    Stage06DesignDiagnosticConfig,
    Stage06DesignDiagnosticError,
)


def _input_table(
    rows: list[tuple[bytes, str | None, str | None, str | None, str | None]],
) -> pa.Table:
    return pa.table(
        {
            "stable_source_row_id_v1": [row[0] for row in rows],
            "stage05_standard_candidate_clean": [row[1] or "" for row in rows],
            "stage05_native_candidate_clean": [row[2] or "" for row in rows],
            "stage05_standard_candidate_lower": [row[3] or "" for row in rows],
            "stage05_native_candidate_lower": [row[4] or "" for row in rows],
            "stage05_standard_candidate_available": [
                row[3] is not None for row in rows
            ],
            "stage05_native_candidate_available": [row[4] is not None for row in rows],
        }
    )


def _metrics(
    rows: list[tuple[bytes, str | None, str | None, str | None, str | None]],
    *,
    threads: int = 1,
) -> dict[str, object]:
    connection = duckdb.connect()
    try:
        connection.execute("SET threads=?", [threads])
        connection.register("stage05_input", _input_table(rows))
        diagnostic._build_candidate_groups(connection)
        return diagnostic._collect_metrics(connection)
    finally:
        connection.close()


def test_exact_global_dedup_and_clean_surface_evidence() -> None:
    rows = [
        (bytes([1]) * 32, None, None, None, None),
        (bytes([2]) * 32, "Alpha", None, "alpha", None),
        (bytes([3]) * 32, None, "ALPHA", None, "alpha"),
        (bytes([4]) * 32, "Alpha", "alpha", "alpha", "alpha"),
        (bytes([5]) * 32, "alpha!", "alpha ", "alpha!", "alpha "),
        (bytes([6]) * 32, "é", "é", "é", "é"),
        (bytes([7]) * 32, "شارع", "Москва", "شارع", "москва"),
        (bytes([8]) * 32, "東京", "🏠", "東京", "🏠"),
    ]
    metrics = _metrics(rows)
    occurrences = metrics["CANDIDATE_OCCURRENCES"]
    exact = metrics["EXACT_DEDUPLICATION"]
    representation = metrics["REPRESENTATION_CONTRIBUTION"]
    clean = metrics["CLEAN_SURFACE_VARIANTS"]
    empty = metrics["EMPTY_AND_UNAVAILABLE"]
    reconciliation = metrics["RECONCILIATION"]
    assert isinstance(occurrences, dict)
    assert isinstance(exact, dict)
    assert isinstance(representation, dict)
    assert isinstance(clean, dict)
    assert isinstance(empty, dict)
    assert isinstance(reconciliation, dict)
    assert occurrences == {
        "STANDARD_AVAILABLE": 6,
        "STANDARD_UNAVAILABLE": 2,
        "NATIVE_AVAILABLE": 6,
        "NATIVE_UNAVAILABLE": 2,
        "TOTAL_AVAILABLE_OCCURRENCES": 12,
        "SAME_ROW_STANDARD_NATIVE_EXACT_LOWER_EQUAL": 1,
    }
    assert exact["UNIQUE_EXACT_LOWER_CANDIDATES"] == 9
    assert exact["DUPLICATE_OCCURRENCES"] == 3
    assert exact["SINGLETON_GROUPS"] == 8
    assert exact["DUPLICATE_GROUPS"] == 1
    assert exact["MAXIMUM_GROUP_SIZE"] == 4
    assert representation == {
        "STANDARD_ONLY_CANDIDATE_GROUPS": 4,
        "NATIVE_ONLY_CANDIDATE_GROUPS": 4,
        "BOTH_REPRESENTATION_CANDIDATE_GROUPS": 1,
        "CROSS_REPRESENTATION_CANDIDATE_GROUPS": 1,
    }
    assert clean["CANONICAL_GROUPS_WITH_MULTIPLE_CLEAN_SURFACES"] == 1
    assert clean["CLEAN_SURFACE_COUNT_DISTRIBUTION"] == {"1": 8, "3": 1}
    assert empty["EMPTY_REGISTRY_CANDIDATES"] == 0
    assert reconciliation["TOTAL_OCCURRENCE_MISMATCHES"] == 0
    assert reconciliation["STANDARD_OCCURRENCE_MISMATCHES"] == 0
    assert reconciliation["NATIVE_OCCURRENCE_MISMATCHES"] == 0


def test_one_codepoint_punctuation_whitespace_and_combining_marks_stay_distinct() -> (
    None
):
    values = ("a", "b", "a!", "a ", "é", "é")
    rows = [
        (bytes([index + 1]) * 32, value, None, value, None)
        for index, value in enumerate(values)
    ]
    metrics = _metrics(rows)
    exact = metrics["EXACT_DEDUPLICATION"]
    assert isinstance(exact, dict)
    assert exact["UNIQUE_EXACT_LOWER_CANDIDATES"] == len(values)
    assert exact["DUPLICATE_OCCURRENCES"] == 0


def test_empty_unavailable_representations_never_form_a_candidate() -> None:
    metrics = _metrics(
        [
            (bytes([1]) * 32, None, None, None, None),
            (bytes([2]) * 32, "Only standard", None, "only standard", None),
            (bytes([3]) * 32, None, "Only native", None, "only native"),
        ]
    )
    exact = metrics["EXACT_DEDUPLICATION"]
    empty = metrics["EMPTY_AND_UNAVAILABLE"]
    assert isinstance(exact, dict)
    assert isinstance(empty, dict)
    assert exact["UNIQUE_EXACT_LOWER_CANDIDATES"] == 2
    assert empty["EMPTY_REGISTRY_CANDIDATES"] == 0
    assert empty["UNAVAILABLE_OCCURRENCES_EXCLUDED_FROM_REGISTRY"] == 4


def test_aggregate_result_is_duckdb_thread_invariant() -> None:
    rows = [
        (
            index.to_bytes(32, "big"),
            f"Surface {index % 7}",
            f"surface {index % 11}",
            f"candidate {index % 7}",
            f"candidate {index % 11}",
        )
        for index in range(1, 200)
    ]
    assert _metrics(rows, threads=1) == _metrics(rows, threads=4)


def test_design_config_rejects_holdout_wrong_manifest_and_bad_resource_limits(
    tmp_path: Path,
) -> None:
    with pytest.raises(Stage06DesignDiagnosticError, match="HOLDOUT_ACCESS_PROHIBITED"):
        Stage06DesignDiagnosticConfig(
            stage05_output_directory=tmp_path / "holdout",
            output_directory=tmp_path / "output",
            execution_git_sha="a" * 40,
        ).validate()
    with pytest.raises(Stage06DesignDiagnosticError, match="WRONG_STAGE05_BINDING"):
        Stage06DesignDiagnosticConfig(
            stage05_output_directory=tmp_path / "development",
            output_directory=tmp_path / "output",
            execution_git_sha="a" * 40,
            expected_stage05_manifest_sha256="b" * 64,
        ).validate()
    with pytest.raises(Stage06DesignDiagnosticError, match="INVALID_MEMORY_LIMIT"):
        Stage06DesignDiagnosticConfig(
            stage05_output_directory=tmp_path / "development",
            output_directory=tmp_path / "output",
            execution_git_sha="a" * 40,
            duckdb_memory_limit="unbounded",
        ).validate()


def test_design_launcher_is_guarded_detached_and_aggregate_only() -> None:
    repository = Path(__file__).resolve().parents[1]
    launcher_path = (
        repository / "cluster" / "goethe_nhr" / "stage06_design_diagnostic.sbatch"
    )
    bootstrap_path = repository / "cluster" / "goethe_nhr" / "stage06_bootstrap_env.sh"
    module_path = (
        repository
        / "src"
        / "safe_geocoding_pipeline"
        / "preprocessing"
        / "stages"
        / "s06_design_diagnostic.py"
    )
    launcher = launcher_path.read_text(encoding="utf-8")
    bootstrap = bootstrap_path.read_text(encoding="utf-8")
    module = module_path.read_text(encoding="utf-8")
    subprocess.run(["bash", "-n", str(launcher_path)], check=True)
    subprocess.run(["bash", "-n", str(bootstrap_path)], check=True)
    assert "SAFE_EXECUTION_SITE=goethe-nhr" in launcher
    assert "SLURM_JOB_ID" in launcher
    assert "HOLDOUT_ACCESS_PROHIBITED" in launcher
    assert "STAGE06_WORKTREE_NOT_DETACHED" in launcher
    assert (
        "fd945163e3be0242c43b98972350904631279cb99f366baadb0a3094ab6a1fc5" in launcher
    )
    assert 'duckdb.__version__ == "1.5.5"' in bootstrap
    assert "STAGE06_DESIGN_DIAGNOSTIC_COMPLETE" in module
    assert "CANDIDATE_TEXT_EMITTED" in module
    assert "print(" not in module


def test_design_diagnostic_source_contains_no_protected_evidence() -> None:
    repository = Path(__file__).resolve().parents[1]
    payload = json.dumps(
        {
            "module": (
                repository
                / "src"
                / "safe_geocoding_pipeline"
                / "preprocessing"
                / "stages"
                / "s06_design_diagnostic.py"
            ).read_text(encoding="utf-8")
        }
    )
    assert "stage05_standard_candidate_lower" in payload
    assert "stage05_native_candidate_lower" in payload
    assert "HOLDOUT_ACCESSED" in payload
