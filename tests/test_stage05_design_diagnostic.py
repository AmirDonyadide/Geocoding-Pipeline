from __future__ import annotations

import sqlite3
from pathlib import Path

import pyarrow as pa
import pytest

import safe_geocoding_pipeline.preprocessing.stages.s05_design_diagnostic as diagnostic
from safe_geocoding_pipeline.preprocessing.stages.s05_design_diagnostic import (
    Stage05DesignDiagnosticConfig,
    Stage05DesignDiagnosticError,
)
from safe_geocoding_pipeline.preprocessing.stages.s02_harmonization import (
    NATIVE_ADDRESS_COLUMNS,
    STANDARD_ADDRESS_COLUMNS,
)
from safe_geocoding_pipeline.preprocessing.stages.s03_cleaning import (
    CLEAN_DERIVED_COLUMNS,
)
from safe_geocoding_pipeline.preprocessing.stages.s04_lowercase import (
    LOWER_OUTPUT_COLUMNS,
    stage04_schema,
)


def _batch(rows: list[dict[str, str | int]]) -> pa.RecordBatch:
    values: dict[str, list[object]] = {
        name: ["" for _ in rows] for name in stage04_schema().names
    }
    for field in stage04_schema():
        if pa.types.is_uint64(field.type) or pa.types.is_uint8(field.type):
            values[field.name] = [0 for _ in rows]
        elif pa.types.is_boolean(field.type):
            values[field.name] = [False for _ in rows]
        elif pa.types.is_fixed_size_binary(field.type):
            values[field.name] = [bytes(field.type.byte_width) for _ in rows]
        elif pa.types.is_list(field.type):
            values[field.name] = [[] for _ in rows]
    for index, row in enumerate(rows):
        for name, value in row.items():
            values[name][index] = value
        for raw_name, clean_name, lower_name in zip(
            (*STANDARD_ADDRESS_COLUMNS, *NATIVE_ADDRESS_COLUMNS),
            CLEAN_DERIVED_COLUMNS[:8],
            LOWER_OUTPUT_COLUMNS[:8],
            strict=True,
        ):
            clean = str(values[clean_name][index])
            values[raw_name][index] = clean
            values[lower_name][index] = clean.lower()
        values["standard_nonempty_source_line_count"][index] = sum(
            values[name][index] != "" for name in STANDARD_ADDRESS_COLUMNS
        )
        values["native_nonempty_source_line_count"][index] = sum(
            values[name][index] != "" for name in NATIVE_ADDRESS_COLUMNS
        )
        values["standard_has_nonempty_source_line"][index] = bool(
            values["standard_nonempty_source_line_count"][index]
        )
        values["native_has_nonempty_source_line"][index] = bool(
            values["native_nonempty_source_line_count"][index]
        )
    arrays = [
        pa.array(values[field.name], type=field.type) for field in stage04_schema()
    ]
    return pa.RecordBatch.from_arrays(arrays, schema=stage04_schema())


def test_aggregate_observation_preserves_gaps_duplicates_and_relationships(
    tmp_path: Path,
) -> None:
    batch = _batch(
        [
            {
                "stage03_clean_street_address_line_1": "A",
                "stage03_clean_street_address_line_3": "A",
                "stage03_clean_street_address_line_2_native": "a",
                "stage03_clean_street_address_line_4_native": "B",
            },
            {
                "stage03_clean_street_address_line_1": "X,",
                "stage03_clean_street_address_line_2": "Y",
                "stage03_clean_street_address_line_1_native": "X",
                "stage03_clean_street_address_line_2_native": "Y",
            },
        ]
    )
    database = tmp_path / "lengths.sqlite3"
    lengths = sqlite3.connect(database)
    lengths.execute(
        "CREATE TABLE candidate_lengths (representation TEXT NOT NULL, "
        "codepoints INTEGER NOT NULL)"
    )
    metrics = diagnostic._DiagnosticMetrics()
    diagnostic._observe_batch(batch, metrics, lengths)
    lengths.commit()
    assert metrics.rows == 2
    assert metrics.relationship["BOTH"] == 2
    assert metrics.standard.occupancy_masks["1010"] == 1
    assert metrics.native.occupancy_masks["0101"] == 1
    assert metrics.standard.gap_rows == 1
    assert metrics.native.gap_rows == 1
    assert metrics.standard.exact_duplicate_line_rows_lower == 1
    assert metrics.standard.boundary_predecessor_end["COMMA"] == 1
    assert metrics.both_candidate_relationship["DIFFERENT"] == 2
    assert diagnostic._length_statistics(lengths, "STANDARD")["COUNT"] == 2
    lengths.close()


def test_design_config_rejects_holdout_and_wrong_manifest(tmp_path: Path) -> None:
    with pytest.raises(Stage05DesignDiagnosticError, match="HOLDOUT_ACCESS_PROHIBITED"):
        Stage05DesignDiagnosticConfig(
            stage04_output_directory=tmp_path / "holdout",
            output_directory=tmp_path / "output",
            execution_git_sha="a" * 40,
        ).validate()
    with pytest.raises(Stage05DesignDiagnosticError, match="WRONG_STAGE04_BINDING"):
        Stage05DesignDiagnosticConfig(
            stage04_output_directory=tmp_path / "development",
            output_directory=tmp_path / "output",
            execution_git_sha="a" * 40,
            expected_stage04_manifest_sha256="b" * 64,
        ).validate()


def test_design_launcher_is_guarded_and_aggregate_only() -> None:
    repository = Path(__file__).resolve().parents[1]
    launcher = (
        repository / "cluster" / "goethe_nhr" / "stage05_design_diagnostic.sbatch"
    ).read_text(encoding="utf-8")
    module = (
        repository
        / "src"
        / "safe_geocoding_pipeline"
        / "preprocessing"
        / "stages"
        / "s05_design_diagnostic.py"
    ).read_text(encoding="utf-8")
    assert "SAFE_EXECUTION_SITE=goethe-nhr" in launcher
    assert "SLURM_JOB_ID" in launcher
    assert "HOLDOUT_ACCESS_PROHIBITED" in launcher
    assert "STAGE05_DESIGN_DIAGNOSTIC_COMPLETE" in module
    assert "ROW_VALUES_EMITTED" in module
    assert "print(" not in module
