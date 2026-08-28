from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from safe_geocoding_pipeline.preprocessing.reporting import stage07
from safe_geocoding_pipeline.preprocessing.reporting.stage07 import (
    QUALITATIVE_CLASSIFICATIONS,
    Stage07ReviewConfig,
    Stage07ReviewError,
    _fixed500_evidence,
    _render_html,
    _risk_selection,
)
from safe_geocoding_pipeline.preprocessing.stages.s06_exact_deduplication import (
    ROW_MAP_ID_COLUMNS,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_libpostal_adapter import (
    PARSED_NONEMPTY,
    LibpostalComponent,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_output_schema import (
    one_component_list_array,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_parsing import stage07_schema


class _FakeSupervisor:
    def __enter__(self) -> _FakeSupervisor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def parse(self, candidate: str) -> SimpleNamespace:
        return SimpleNamespace(
            status=PARSED_NONEMPTY,
            components=(LibpostalComponent(label="road", value=candidate),),
        )


def _candidate_id(index: int) -> bytes:
    return index.to_bytes(32, "big")


def _stage07_table(count: int) -> pa.Table:
    components = pa.concat_arrays(
        [
            one_component_list_array(
                (LibpostalComponent(label="road", value=f"candidate-{index}"),)
            )
            for index in range(count)
        ]
    )
    return pa.Table.from_arrays(
        (
            pa.array((_candidate_id(index) for index in range(count)), type=pa.binary(32)),
            pa.array((f"candidate-{index}" for index in range(count)), type=pa.string()),
            pa.array((1 for _ in range(count)), type=pa.uint64()),
            pa.array((1 for _ in range(count)), type=pa.uint64()),
            pa.array((0 for _ in range(count)), type=pa.uint64()),
            pa.array((PARSED_NONEMPTY for _ in range(count)), type=pa.string()),
            components,
        ),
        schema=stage07_schema(),
    )


def test_fixed500_reparses_all_613_and_resolves_all_937_occurrences(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage07_path = tmp_path / "stage07.parquet"
    pq.write_table(_stage07_table(613), stage07_path, write_page_checksum=True)
    monkeypatch.setattr(stage07, "SupervisedParser", _FakeSupervisor)

    standard = [_candidate_id(index) for index in range(500)]
    native: list[bytes | None] = [None] * 500
    for index in range(113):
        native[index] = _candidate_id(500 + index)
    for index in range(113, 437):
        native[index] = _candidate_id(index - 113)
    fixed = pa.table(
        {
            "review_order": pa.array(range(1, 501), type=pa.uint32()),
            "stable_source_row_id_v1": pa.array(
                (_candidate_id(10_000 + index) for index in range(500)),
                type=pa.binary(32),
            ),
            ROW_MAP_ID_COLUMNS[0]: pa.array(standard, type=pa.binary(32)),
            ROW_MAP_ID_COLUMNS[1]: pa.array(native, type=pa.binary(32)),
        }
    )
    evidence, metrics = _fixed500_evidence(fixed, (stage07_path,))

    assert evidence.num_rows == 500
    assert metrics == {
        "SOURCE_ROWS": 500,
        "OCCURRENCES": 937,
        "UNIQUE_CANDIDATES": 613,
        "DUPLICATE_OCCURRENCES": 324,
        "INDEPENDENT_REPARSES": 613,
        "MISMATCHES": 0,
        "CROSS_WIRES": 0,
    }


def test_risk_selection_is_deterministic_and_html_hides_stable_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage07_path = tmp_path / "stage07.parquet"
    pq.write_table(_stage07_table(4), stage07_path, write_page_checksum=True)
    stage06 = tmp_path / "stage06"
    (stage06 / "row_map" / "data").mkdir(parents=True)
    row_map = stage06 / "row_map" / "data" / "part-000001.parquet"
    pq.write_table(pa.table({"dummy": [1]}), row_map)
    (stage06 / "stage06_manifest.json").write_text(
        '{"physical_identity":{"row_map_artifacts":['
        '{"relative_path":"row_map/data/part-000001.parquet"}]}}',
        encoding="utf-8",
    )
    clean_groups = {
        _candidate_id(1000 + index): ("synthetic A", "synthetic a")
        for index in range(123)
    }
    monkeypatch.setattr(stage07, "_clean_surface_groups", lambda *args, **kwargs: clean_groups)

    work_one = tmp_path / "work_one"
    work_two = tmp_path / "work_two"
    work_one.mkdir()
    work_two.mkdir()
    first, first_fingerprint = _risk_selection(stage06, (stage07_path,), work_one)
    second, second_fingerprint = _risk_selection(stage06, (stage07_path,), work_two)
    assert first == second
    assert first_fingerprint == second_fingerprint
    assert len(first) == 4

    html_path = tmp_path / "review.html"
    _render_html(html_path, (stage07_path,), first, first_fingerprint)
    rendered = html_path.read_text(encoding="utf-8")
    assert "candidate-0" in rendered
    assert _candidate_id(0).hex() not in rendered
    assert "stage06_exact_candidate_id" not in rendered
    for classification in QUALITATIVE_CLASSIFICATIONS:
        assert classification in rendered


def test_review_config_rejects_holdout() -> None:
    config = Stage07ReviewConfig(
        stage05_output_directory=Path("stage05"),
        stage06_output_directory=Path("stage06"),
        stage06_review_directory=Path("stage06_review"),
        expected_stage06_review_manifest_sha256="1" * 64,
        stage07_output_directory=Path("stage07"),
        expected_stage07_manifest_sha256="2" * 64,
        parser_bundle_directory=Path("bundle"),
        output_directory=Path("HOLDOUT") / "review",
        execution_git_sha="3" * 40,
        production=False,
    )
    with pytest.raises(Stage07ReviewError, match="HOLDOUT_ACCESS_PROHIBITED"):
        config.validate()

