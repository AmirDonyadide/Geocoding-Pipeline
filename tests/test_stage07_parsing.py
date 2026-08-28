from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from safe_geocoding_pipeline.preprocessing import stage07_cli
from safe_geocoding_pipeline.preprocessing.stages import s07_parsing
from safe_geocoding_pipeline.preprocessing.stages.s06_exact_deduplication import (
    REGISTRY_COLUMNS,
    registry_schema,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_libpostal_adapter import (
    PARSED_EMPTY,
    PARSED_NONEMPTY,
    LibpostalComponent,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_output_schema import (
    component_list_type,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_parsing import (
    ACCEPTED_PARSER_BUNDLE_FINGERPRINT,
    STAGE07_CONTRACT_VERSION,
    STAGE07_PROFILE_VERSION,
    Stage07RunConfig,
    Stage07ValidationError,
    accepted_stage07_input_binding,
    materialize_stage07,
    stage07_contract_fingerprint,
    stage07_schema,
    validate_stage07_bundle,
    validate_stage07_input_binding,
    write_stage07_input_binding,
)


class _FakeSupervisor:
    parsed_inputs: list[str] = []

    def __init__(self) -> None:
        self.workers_started = 1
        self.worker_restarts = 0
        self.worker_initialization_seconds = [0.01]
        self.first_attempt_crashes = 0
        self.confirmed_repeated_crashes = 0
        self.crash_success_inconsistencies = 0
        self.changed_failure_inconsistencies = 0

    def __enter__(self) -> _FakeSupervisor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def parse(self, candidate: str) -> SimpleNamespace:
        self.parsed_inputs.append(candidate)
        if candidate == "---":
            return SimpleNamespace(status=PARSED_EMPTY, components=())
        return SimpleNamespace(
            status=PARSED_NONEMPTY,
            components=(
                LibpostalComponent(label="road", value=candidate),
                LibpostalComponent(label="road", value="duplicate-label"),
            ),
        )


def _private_directory(path: Path) -> Path:
    path.mkdir(parents=True, mode=0o700)
    path.chmod(0o700)
    return path


def _fixture_stage06(root: Path) -> tuple[Path, tuple[str, ...], tuple[bytes, ...]]:
    root = _private_directory(root)
    registry_directory = _private_directory(root / "registry" / "data")
    (root / "registry").chmod(0o700)
    row_map_directory = _private_directory(root / "row_map" / "data")
    (root / "row_map").chmod(0o700)
    candidates = ("  exact é road  ", "---", "مثال улица １２３")
    candidate_ids = tuple(index.to_bytes(32, "big") for index in range(1, 4))
    counts = ((2, 1, 1), (1, 1, 0), (3, 0, 3))
    table = pa.Table.from_arrays(
        (
            pa.array(candidate_ids, type=pa.binary(32)),
            pa.array(candidates, type=pa.string()),
            *(pa.array((row[index] for row in counts), type=pa.uint64()) for index in range(3)),
        ),
        schema=registry_schema(),
    )
    registry_path = registry_directory / "part-000001.parquet"
    pq.write_table(table, registry_path, write_page_checksum=True)
    registry_path.chmod(0o600)
    row_map_path = row_map_directory / "part-000001.parquet"
    pq.write_table(
        pa.table(
            {
                "stage06_standard_exact_candidate_id": pa.array(
                    (candidate_ids[0], candidate_ids[1], None, None),
                    type=pa.binary(32),
                ),
                "stage06_native_exact_candidate_id": pa.array(
                    (
                        candidate_ids[0],
                        candidate_ids[2],
                        candidate_ids[2],
                        candidate_ids[2],
                    ),
                    type=pa.binary(32),
                ),
            }
        ),
        row_map_path,
        write_page_checksum=True,
    )
    row_map_path.chmod(0o600)
    manifest = {
        "physical_identity": {
            "registry_artifacts": [
                {"relative_path": "registry/data/part-000001.parquet"}
            ],
            "row_map_artifacts": [
                {"relative_path": "row_map/data/part-000001.parquet"}
            ],
        }
    }
    manifest_path = root / "stage06_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    manifest_path.chmod(0o600)
    return registry_path, candidates, candidate_ids


def _binding(tmp_path: Path) -> tuple[Path, str, object]:
    binding = replace(
        accepted_stage07_input_binding(),
        stage06_registry_rows=3,
        stage06_occurrences=6,
        stage06_standard_occurrences=2,
        stage06_native_occurrences=4,
    )
    path = tmp_path / "binding" / "stage07_input_binding.json"
    sha256 = write_stage07_input_binding(path, binding)
    return path, sha256, binding


def _patch_protected_dependencies(
    monkeypatch: pytest.MonkeyPatch, stage06_root: Path, binding: object
) -> None:
    monkeypatch.setattr(s07_parsing, "SupervisedParser", _FakeSupervisor)
    monkeypatch.setattr(s07_parsing, "_validate_bundle_identity", lambda *args: None)
    monkeypatch.setattr(
        s07_parsing,
        "validate_stage06_bundle",
        lambda *args, **kwargs: SimpleNamespace(
            schema_fingerprint=binding.stage06_schema_fingerprint,
            logical_dataset_sha256_v1=binding.stage06_logical_fingerprint,
            input_binding_sha256=binding.stage06_input_binding_sha256,
            ordered_identity_sha256=binding.stage06_ordered_identity_sha256,
            unique_candidate_count=3,
        ),
    )


def _run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    output_name: str,
    input_batch_rows: int,
    output_batch_rows: int,
    output_shard_rows: int,
) -> tuple[object, tuple[str, ...], Path, Stage07RunConfig]:
    fixture_root = tmp_path / f"inputs_{output_name}"
    stage05 = _private_directory(fixture_root / "stage05")
    stage06 = fixture_root / "stage06"
    _, candidates, _ = _fixture_stage06(stage06)
    bundle = _private_directory(fixture_root / "bundle")
    binding_path, binding_sha, binding = _binding(fixture_root)
    _patch_protected_dependencies(monkeypatch, stage06, binding)
    _FakeSupervisor.parsed_inputs = []
    output = tmp_path / output_name
    config = Stage07RunConfig(
            stage05_output_directory=stage05,
            stage06_output_directory=stage06,
            input_binding_file=binding_path,
            expected_input_binding_sha256=binding_sha,
            parser_bundle_directory=bundle,
            expected_parser_bundle_fingerprint=ACCEPTED_PARSER_BUNDLE_FINGERPRINT,
            output_directory=output,
            execution_git_sha="a" * 40,
            authoritative_development=False,
            production=False,
            input_batch_rows=input_batch_rows,
            output_batch_rows=output_batch_rows,
            target_batch_bytes=256,
            output_shard_rows=output_shard_rows,
        )
    outcome = materialize_stage07(config)
    return outcome, candidates, output, config


def test_contract_profile_and_large_offset_schema_are_frozen() -> None:
    binding = accepted_stage07_input_binding()
    validate_stage07_input_binding(binding, authoritative_development=True)
    assert STAGE07_CONTRACT_VERSION == "stage07_libpostal_parsing_contract_v1"
    assert STAGE07_PROFILE_VERSION == "stage07_libpostal_parsing_profile_v1"
    assert len(stage07_contract_fingerprint(binding)) == 64
    schema = stage07_schema()
    assert schema.names[:5] == list(REGISTRY_COLUMNS)
    assert schema.field("stage07_parse_status").nullable is False
    components = schema.field("stage07_libpostal_components")
    assert components.type == component_list_type()
    assert components.nullable is False
    assert pa.types.is_large_list(components.type)
    assert pa.types.is_large_string(components.type.value_type.field("label").type)
    assert pa.types.is_large_string(components.type.value_type.field("value").type)


def test_binding_fails_closed_for_each_controlling_identity() -> None:
    binding = accepted_stage07_input_binding()
    for field in (
        "stage06_manifest_sha256",
        "stage06_logical_fingerprint",
        "stage06_schema_fingerprint",
        "stage06_input_binding_sha256",
        "benchmark_fingerprint",
        "fixed_500_fingerprint",
        "parser_bundle_fingerprint",
    ):
        with pytest.raises(
            Stage07ValidationError, match="AUTHORITATIVE_DEVELOPMENT_BINDING_MISMATCH"
        ):
            validate_stage07_input_binding(
                replace(binding, **{field: "0" * 64}), authoritative_development=True
            )


def test_streaming_materialization_preserves_exact_input_order_and_duplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outcome, candidates, output, _ = _run(
        tmp_path,
        monkeypatch,
        output_name="stage07_one",
        input_batch_rows=1,
        output_batch_rows=1,
        output_shard_rows=2,
    )
    assert _FakeSupervisor.parsed_inputs == list(candidates)
    assert outcome.candidate_count == 3
    assert outcome.shard_count == 2
    paths = sorted((output / "registry" / "data").glob("*.parquet"))
    table = pq.read_table(paths)
    assert table.column(REGISTRY_COLUMNS[0]).to_pylist() == [
        index.to_bytes(32, "big") for index in range(1, 4)
    ]
    assert table.column(REGISTRY_COLUMNS[1]).to_pylist() == list(candidates)
    assert table.column(REGISTRY_COLUMNS[2]).to_pylist() == [2, 1, 3]
    assert table.column(REGISTRY_COLUMNS[3]).to_pylist() == [1, 1, 0]
    assert table.column(REGISTRY_COLUMNS[4]).to_pylist() == [1, 0, 3]
    assert table.column("stage07_parse_status").to_pylist() == [
        PARSED_NONEMPTY,
        PARSED_EMPTY,
        PARSED_NONEMPTY,
    ]
    assert table.column("stage07_libpostal_components")[0].as_py() == [
        {"label": "road", "value": candidates[0]},
        {"label": "road", "value": "duplicate-label"},
    ]
    assert table.column("stage07_libpostal_components")[1].as_py() == []
    assert table.column("stage07_libpostal_components").null_count == 0


def test_logical_output_is_batch_row_group_and_shard_layout_invariant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, _, _, _ = _run(
        tmp_path,
        monkeypatch,
        output_name="first",
        input_batch_rows=1,
        output_batch_rows=1,
        output_shard_rows=1,
    )
    second, _, _, _ = _run(
        tmp_path,
        monkeypatch,
        output_name="second",
        input_batch_rows=3,
        output_batch_rows=3,
        output_shard_rows=10,
    )
    assert first.logical_dataset_sha256_v1 == second.logical_dataset_sha256_v1
    assert first.registry_logical_sha256_v1 == second.registry_logical_sha256_v1
    assert first.schema_fingerprint == second.schema_fingerprint


def test_published_validator_detects_partial_output_and_permission_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outcome, _, output, _ = _run(
        tmp_path,
        monkeypatch,
        output_name="published",
        input_batch_rows=2,
        output_batch_rows=2,
        output_shard_rows=2,
    )
    stage05 = tmp_path / "inputs_published" / "stage05"
    stage06 = tmp_path / "inputs_published" / "stage06"
    bundle = tmp_path / "inputs_published" / "bundle"
    artifact = sorted((output / "registry" / "data").glob("*.parquet"))[0]
    artifact.chmod(0o644)
    with pytest.raises(Stage07ValidationError, match="PERMISSION_FAILURE"):
        validate_stage07_bundle(
            output,
            expected_manifest_sha256=outcome.manifest_sha256,
            stage05_output_directory=stage05,
            stage06_output_directory=stage06,
            parser_bundle_directory=bundle,
            authoritative_development=False,
        )


def test_published_validator_rejects_partial_mutated_and_wrong_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outcome, _, output, config = _run(
        tmp_path,
        monkeypatch,
        output_name="valid_for_corruption",
        input_batch_rows=2,
        output_batch_rows=2,
        output_shard_rows=2,
    )

    def validate_copy(root: Path, manifest_sha256: str = outcome.manifest_sha256) -> None:
        validate_stage07_bundle(
            root,
            expected_manifest_sha256=manifest_sha256,
            stage05_output_directory=config.stage05_output_directory,
            stage06_output_directory=config.stage06_output_directory,
            parser_bundle_directory=config.parser_bundle_directory,
            authoritative_development=False,
        )

    partial = tmp_path / "partial"
    shutil.copytree(output, partial)
    sorted((partial / "registry" / "data").glob("*.parquet"))[-1].unlink()
    with pytest.raises(Stage07ValidationError, match="STAGE07_ARTIFACT_INVALID"):
        validate_copy(partial)

    mutated = tmp_path / "mutated"
    shutil.copytree(output, mutated)
    with sorted((mutated / "registry" / "data").glob("*.parquet"))[0].open(
        "ab"
    ) as stream:
        stream.write(b"synthetic mutation")
    with pytest.raises(Stage07ValidationError, match="STAGE07_ARTIFACT_MISMATCH"):
        validate_copy(mutated)

    with pytest.raises(Stage07ValidationError, match="STAGE07_MANIFEST_SHA256_MISMATCH"):
        validate_copy(output, "0" * 64)


def test_materializer_rejects_output_collision_and_wrong_parser_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, _, config = _run(
        tmp_path,
        monkeypatch,
        output_name="collision",
        input_batch_rows=2,
        output_batch_rows=2,
        output_shard_rows=2,
    )
    with pytest.raises(Stage07ValidationError, match="OUTPUT_COLLISION"):
        materialize_stage07(config)
    with pytest.raises(
        Stage07ValidationError, match="PARSER_BUNDLE_FINGERPRINT_MISMATCH"
    ):
        materialize_stage07(
            replace(config, expected_parser_bundle_fingerprint="0" * 64)
        )


def test_large_list_serializes_giant_repeated_label_result(tmp_path: Path) -> None:
    components = tuple(
        LibpostalComponent(label="road", value=f"segment-{index}")
        for index in range(70_000)
    )
    schema = stage07_schema()
    arrays: list[pa.Array] = [
        pa.array((b"x" * 32,), type=pa.binary(32)),
        pa.array(("synthetic giant",), type=pa.string()),
        pa.array((1,), type=pa.uint64()),
        pa.array((1,), type=pa.uint64()),
        pa.array((0,), type=pa.uint64()),
        pa.array((PARSED_NONEMPTY,), type=pa.string()),
        s07_parsing.one_component_list_array(components),
    ]
    table = pa.Table.from_arrays(arrays, schema=schema)
    path = tmp_path / "giant_nested.parquet"
    pq.write_table(table, path, write_page_checksum=True, compression="zstd")
    reopened = pq.ParquetFile(path, page_checksum_verification=True).read(
        use_threads=False
    )
    nested = reopened.column("stage07_libpostal_components")[0].as_py()
    assert len(nested) == 70_000
    assert nested[0] == {"label": "road", "value": "segment-0"}
    assert nested[-1] == {"label": "road", "value": "segment-69999"}


def test_holdout_output_collision_and_cli_execution_guard_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = Stage07RunConfig(
        stage05_output_directory=tmp_path / "stage05",
        stage06_output_directory=tmp_path / "stage06",
        input_binding_file=tmp_path / "binding",
        expected_input_binding_sha256="0" * 64,
        parser_bundle_directory=tmp_path / "bundle",
        expected_parser_bundle_fingerprint="0" * 64,
        output_directory=tmp_path / "HOLDOUT" / "stage07",
        execution_git_sha="a" * 40,
        production=False,
    )
    with pytest.raises(Stage07ValidationError, match="HOLDOUT_ACCESS_PROHIBITED"):
        config.validate()

    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setattr(
        "sys.argv",
        [
            "stage07",
            "create-input-binding",
            "--parser-bundle-directory",
            str(tmp_path / "bundle"),
            "--expected-parser-bundle-fingerprint",
            ACCEPTED_PARSER_BUNDLE_FINGERPRINT,
            "--output",
            str(tmp_path / "binding"),
        ],
    )
    assert stage07_cli.main() == 1
    assert "HEAVY_PROCESS_CLUSTER_REQUIRED" in capsys.readouterr().err


def test_source_has_no_population_materialization_or_failure_status_schema() -> None:
    source = Path(s07_parsing.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "read_table(",
        "combine_chunks(",
        "concat_tables(",
        "to_pylist(",
        "fetchall(",
        "fetchdf(",
        "RLIMIT_AS",
        "ulimit -v",
        "PARSER_PROCESS_CRASH\"",
    ):
        assert forbidden not in source
    binding = accepted_stage07_input_binding()
    assert binding.stage06_registry_rows == 51_779
    assert binding.stage06_occurrences == 69_747
    assert binding.stage06_standard_occurrences == 34_822
    assert binding.stage06_native_occurrences == 34_925
