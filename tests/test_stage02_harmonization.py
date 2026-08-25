from __future__ import annotations

import hashlib
import os
import stat
import struct
from dataclasses import replace
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from safe_geocoding_pipeline.execution_policy import ExecutionPolicyError
from safe_geocoding_pipeline.phase02.constants import (
    PARSER_VERSION,
    SOURCE_SCHEMA_VERSION,
    STAGING_VERSION,
)
from safe_geocoding_pipeline.phase02.identity import stable_source_row_id_v1
from safe_geocoding_pipeline.phase02.schema import (
    base_staging_schema,
    schema_fingerprint,
)
from safe_geocoding_pipeline.preprocessing.benchmark_runner import (
    BENCHMARK_OUTPUT_SCHEMA_VERSION,
    FEATURE_COLUMNS,
    benchmark_schema,
    benchmark_schema_fingerprint,
)
from safe_geocoding_pipeline.preprocessing.benchmark_sample import (
    BENCHMARK_CONTRACT_VERSION,
    FEATURE_CONTRACT_VERSION,
)
from safe_geocoding_pipeline.preprocessing.stages.s01_ingestion import (
    STAGE01_CONTRACT_VERSION,
)
from safe_geocoding_pipeline.preprocessing.stages.s02_harmonization import (
    STAGE02_CONTRACT_VERSION,
    STAGE02_LOGICAL_DATASET_DOMAIN,
    STAGE02_MANIFEST_NAME,
    STAGE02_REPRESENTATION_RELATIONSHIP,
    STAGE02_REPRESENTATION_SOURCE_SYSTEM,
    STAGE02_SCHEMA_VERSION,
    STAGE02_STRUCTURAL_METADATA_VERSION,
    STAGE02_SUCCESS_MARKER,
    Stage02InputArtifact,
    Stage02InputBinding,
    Stage02InputKind,
    Stage02RunConfig,
    Stage02ValidationError,
    materialize_stage02,
    stage02_logical_dataset_sha256_v1,
    stage02_schema,
    stage02_schema_fingerprint,
    validate_stage02_bundle,
    write_stage02_input_binding,
)
from safe_geocoding_pipeline.raw_csv import SOURCE_COLUMNS

UPSTREAM_LOGICAL_IDENTITY = "11" * 32
SOURCE_POPULATION_IDENTITY = "22" * 32
BENCHMARK_FINGERPRINT = "33" * 32
ADOPTING_COMMIT = "a" * 40


def _raw_row(**updates: str) -> list[str]:
    row = {column: "" for column in SOURCE_COLUMNS}
    row.update(
        {
            "id": "fictional-id",
            "postcode": "00123",
            "city": "Example City",
            "region_in_country": "Example Region",
            "country_iso_code": "DE",
            "batch_priority": "1",
            "location_information": "no_geocoding_information",
        }
    )
    row.update(updates)
    return [row[column] for column in SOURCE_COLUMNS]


def _scenario_rows() -> list[list[str]]:
    return [
        _raw_row(
            id="standard-only",
            street_address_line_1='  Fictional "Road", 1  ',
            street_address_line_2="Suite A\nLevel 2",
            street_address_line_1_native="",
            location_information="previous_geocoding_failure",
        ),
        _raw_row(
            id="native-only",
            street_address_line_1="",
            street_address_line_1_native="Москва, корпус 2",
            street_address_line_2_native="подъезд 3\nэтаж 4",
            postcode="00007",
            country_iso_code="RU",
            location_information="postcode_interpolated",
        ),
        _raw_row(
            id="both-distinct",
            street_address_line_1="Fictional Munich Street 5",
            street_address_line_1_native="架空通り五丁目",
            country_iso_code="JP",
            location_information="region_interpolated",
        ),
        _raw_row(
            id="neither",
            street_address_line_1="",
            street_address_line_1_native="",
            postcode="",
            city="",
            region_in_country="",
            country_iso_code="",
        ),
        _raw_row(
            id="unusual-length",
            street_address_line_1="x" * 12_000,
            street_address_line_4="punctuation;:/[]{}!?",
            street_address_line_1_native="北京",
            batch_priority="rare-fictional-priority",
        ),
        _raw_row(
            id="whitespace-is-present",
            street_address_line_1=" ",
            street_address_line_1_native="\t",
        ),
    ]


def _write_stage1_parquet(
    path: Path,
    *,
    source_file: str,
    source_sha256: str,
    rows: list[list[str]],
    stable_id_override: bytes | None = None,
    null_column: str | None = None,
    logical_ordinals: list[int] | None = None,
) -> None:
    source_hash = bytes.fromhex(source_sha256)
    values_by_column: list[list[Any]] = [[] for _ in base_staging_schema()]
    ordinals = logical_ordinals or list(range(1, len(rows) + 1))
    for ordinal, raw in zip(ordinals, rows, strict=True):
        row: list[Any] = list(raw)
        if null_column is not None:
            row[SOURCE_COLUMNS.index(null_column)] = None
        row.extend(
            (
                source_file,
                ordinal,
                stable_id_override
                if stable_id_override is not None
                else stable_source_row_id_v1(source_hash, ordinal),
                source_hash,
                SOURCE_SCHEMA_VERSION,
                PARSER_VERSION,
                STAGING_VERSION,
            )
        )
        for target, value in zip(values_by_column, row, strict=True):
            target.append(value)
    metadata = {
        b"source_schema_version": SOURCE_SCHEMA_VERSION.encode(),
        b"parser_version": PARSER_VERSION.encode(),
        b"staging_version": STAGING_VERSION.encode(),
    }
    base_schema = base_staging_schema()
    if null_column is not None:
        schema = pa.schema(
            [
                pa.field(field.name, field.type, nullable=field.name == null_column)
                for field in base_schema
            ],
            metadata=metadata,
        )
    else:
        schema = base_schema.with_metadata(metadata)
    arrays = [
        pa.array(values, type=field.type, from_pandas=False, safe=True)
        for field, values in zip(schema, values_by_column, strict=True)
    ]
    table = pa.Table.from_arrays(arrays, schema=schema)
    pq.write_table(
        table,
        path,
        compression="zstd",
        compression_level=3,
        write_page_checksum=True,
        row_group_size=2,
    )
    path.chmod(0o600)


def _benchmark_feature_value(name: str, row_count: int) -> list[Any]:
    if name == "benchmark_split":
        return ["DEVELOPMENT"] * row_count
    if name in {
        "benchmark_challenge_flag",
        "postcode_present",
        "city_present",
        "region_present",
        "country_present",
    }:
        return [False] * row_count
    if name in {"standard_line_count", "native_line_count"}:
        return [0] * row_count
    return [f"fictional-{name}"] * row_count


def _write_benchmark_parquet(
    path: Path,
    *,
    rows: list[list[str]],
    split: str = "DEVELOPMENT",
) -> None:
    source_hash = bytes.fromhex("44" * 32)
    values: dict[str, list[Any]] = {name: [] for name in benchmark_schema().names}
    for ordinal, raw in enumerate(rows, start=1):
        for name, value in zip(SOURCE_COLUMNS, raw, strict=True):
            values[name].append(value)
        values["source_file"].append("fictional_benchmark.csv")
        values["source_logical_record_number"].append(ordinal)
        values["stable_source_row_id_v1"].append(
            stable_source_row_id_v1(source_hash, ordinal)
        )
        values["source_file_sha256"].append(source_hash)
        for name in FEATURE_COLUMNS:
            value = _benchmark_feature_value(name, 1)[0]
            values[name].append(split if name == "benchmark_split" else value)
    schema = benchmark_schema().with_metadata(
        {
            b"benchmark_contract_version": BENCHMARK_CONTRACT_VERSION.encode(),
            b"benchmark_fingerprint": BENCHMARK_FINGERPRINT.encode(),
            b"benchmark_schema_version": BENCHMARK_OUTPUT_SCHEMA_VERSION.encode(),
            b"benchmark_feature_contract_version": FEATURE_CONTRACT_VERSION.encode(),
        }
    )
    table = pa.Table.from_arrays(
        [
            pa.array(values[field.name], type=field.type, from_pandas=False, safe=True)
            for field in schema
        ],
        schema=schema,
    )
    pq.write_table(table, path, write_page_checksum=True, row_group_size=2)
    path.chmod(0o600)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _binding_for_files(
    paths: list[Path],
    *,
    input_kind: Stage02InputKind = "STAGE01",
    row_count: int,
) -> Stage02InputBinding:
    return Stage02InputBinding(
        input_kind=input_kind,
        upstream_contract_version=(
            STAGE01_CONTRACT_VERSION
            if input_kind == "STAGE01"
            else BENCHMARK_CONTRACT_VERSION
        ),
        upstream_logical_identity_sha256=(
            UPSTREAM_LOGICAL_IDENTITY
            if input_kind == "STAGE01"
            else BENCHMARK_FINGERPRINT
        ),
        source_population_identity_sha256=SOURCE_POPULATION_IDENTITY,
        input_schema_fingerprint=(
            schema_fingerprint()
            if input_kind == "STAGE01"
            else benchmark_schema_fingerprint()
        ),
        expected_row_count=row_count,
        artifacts=tuple(
            Stage02InputArtifact(
                sequence_number=index,
                relative_path=path.name,
                size_bytes=path.stat().st_size,
                sha256=_sha256(path),
            )
            for index, path in enumerate(paths, start=1)
        ),
    )


def _write_binding(tmp_path: Path, binding: Stage02InputBinding) -> tuple[Path, str]:
    path = tmp_path / "contracts" / "stage02_input.json"
    return path, write_stage02_input_binding(path, binding)


def _run_config(
    tmp_path: Path,
    input_root: Path,
    binding: Stage02InputBinding,
    output_name: str,
    *,
    operational_metadata: dict[str, str] | None = None,
) -> Stage02RunConfig:
    binding_path, binding_hash = _write_binding(tmp_path / output_name, binding)
    return Stage02RunConfig(
        input_root=input_root,
        input_binding_file=binding_path,
        expected_input_binding_sha256=binding_hash,
        output_directory=tmp_path / output_name / "output",
        adopting_git_commit=ADOPTING_COMMIT,
        production=False,
        batch_rows=2,
        operational_metadata=operational_metadata,
    )


def _stage1_fixture(
    tmp_path: Path,
) -> tuple[Path, Stage02InputBinding, list[list[str]]]:
    input_root = tmp_path / "input"
    input_root.mkdir(mode=0o700)
    rows = _scenario_rows()
    shard = input_root / "source-a.parquet"
    _write_stage1_parquet(
        shard,
        source_file="fictional_a.csv",
        source_sha256="55" * 32,
        rows=rows,
    )
    return input_root, _binding_for_files([shard], row_count=len(rows)), rows


def _read_output_table(output: Path) -> pa.Table:
    return pq.read_table(output / "data" / "part-000001.parquet")


def test_stage02_preserves_all_raw_values_ids_and_separate_representations(
    tmp_path: Path,
) -> None:
    input_root, binding, rows = _stage1_fixture(tmp_path)
    input_hash = _sha256(input_root / "source-a.parquet")
    outcome = materialize_stage02(_run_config(tmp_path, input_root, binding, "first"))
    validate_stage02_bundle(
        outcome.output_directory, expected_manifest_sha256=outcome.manifest_sha256
    )
    table = _read_output_table(outcome.output_directory)
    assert table.num_rows == len(rows)
    assert tuple(table.schema.remove_metadata().names) == tuple(stage02_schema().names)
    for index, column in enumerate(SOURCE_COLUMNS):
        assert table[column].to_pylist() == [row[index] for row in rows]
    source_hash = bytes.fromhex("55" * 32)
    assert table["stable_source_row_id_v1"].to_pylist() == [
        stable_source_row_id_v1(source_hash, ordinal)
        for ordinal in range(1, len(rows) + 1)
    ]
    assert table["standard_has_nonempty_source_line"].to_pylist() == [
        True,
        False,
        True,
        False,
        True,
        True,
    ]
    assert table["native_has_nonempty_source_line"].to_pylist() == [
        False,
        True,
        True,
        False,
        True,
        True,
    ]
    assert table["standard_nonempty_source_line_count"].to_pylist() == [
        2,
        0,
        1,
        0,
        2,
        1,
    ]
    assert table["native_nonempty_source_line_count"].to_pylist() == [
        0,
        2,
        1,
        0,
        1,
        1,
    ]
    assert "standard_native_combined" not in table.schema.names
    assert _sha256(input_root / "source-a.parquet") == input_hash


def test_deterministic_output_identity_ignores_operations_and_physical_layout(
    tmp_path: Path,
) -> None:
    input_root, binding, _rows = _stage1_fixture(tmp_path)
    first = materialize_stage02(
        _run_config(
            tmp_path,
            input_root,
            binding,
            "first",
            operational_metadata={"slurm_job_id": "fictional-one"},
        )
    )
    second = materialize_stage02(
        _run_config(
            tmp_path,
            input_root,
            binding,
            "second",
            operational_metadata={"slurm_job_id": "fictional-two"},
        )
    )
    relaid = replace(
        binding,
        artifacts=(
            Stage02InputArtifact(1, "different-layout.parquet", 999, "66" * 32),
            Stage02InputArtifact(2, "second-layout.parquet", 888, "77" * 32),
        ),
    )
    assert first.logical_dataset_sha256_v1 == second.logical_dataset_sha256_v1
    assert stage02_logical_dataset_sha256_v1(
        binding
    ) == stage02_logical_dataset_sha256_v1(relaid)
    assert first.manifest_sha256 != second.manifest_sha256


def _manual_logical_fingerprint(binding: Stage02InputBinding) -> str:
    payload = bytearray(STAGE02_LOGICAL_DATASET_DOMAIN)

    def text(value: str) -> None:
        encoded = value.encode("utf-8")
        payload.extend(b"\x02")
        payload.extend(struct.pack(">Q", len(encoded)))
        payload.extend(encoded)

    def digest(value: str) -> None:
        payload.extend(b"\x03")
        payload.extend(bytes.fromhex(value))

    def uint64(value: int) -> None:
        payload.extend(b"\x01")
        payload.extend(struct.pack(">Q", value))

    text(STAGE02_CONTRACT_VERSION)
    text(STAGE02_SCHEMA_VERSION)
    text(STAGE02_STRUCTURAL_METADATA_VERSION)
    text(STAGE02_REPRESENTATION_SOURCE_SYSTEM)
    text(STAGE02_REPRESENTATION_RELATIONSHIP)
    text(binding.input_kind)
    text(binding.upstream_contract_version)
    digest(binding.upstream_logical_identity_sha256)
    digest(binding.source_population_identity_sha256)
    digest(binding.input_schema_fingerprint)
    digest(stage02_schema_fingerprint())
    uint64(binding.expected_row_count)
    return hashlib.sha256(payload).hexdigest()


def test_logical_fingerprint_independent_golden_and_scientific_sensitivity() -> None:
    binding = Stage02InputBinding(
        input_kind="STAGE01",
        upstream_contract_version=STAGE01_CONTRACT_VERSION,
        upstream_logical_identity_sha256="10" * 32,
        source_population_identity_sha256="20" * 32,
        input_schema_fingerprint=schema_fingerprint(),
        expected_row_count=7,
        artifacts=(Stage02InputArtifact(1, "a.parquet", 10, "30" * 32),),
    )
    observed = stage02_logical_dataset_sha256_v1(binding)
    assert observed == _manual_logical_fingerprint(binding)
    assert (
        observed == "0d8424bc503eb09add34106aa60a419c114d706464f1ffb926ac3a3ae44acea3"
    )
    assert (
        stage02_logical_dataset_sha256_v1(replace(binding, expected_row_count=8))
        != observed
    )
    assert (
        stage02_logical_dataset_sha256_v1(
            replace(binding, upstream_logical_identity_sha256="40" * 32)
        )
        != observed
    )


def test_benchmark_development_interface_never_requires_holdout(tmp_path: Path) -> None:
    input_root = tmp_path / "development"
    input_root.mkdir(mode=0o700)
    rows = _scenario_rows()[:3]
    development = input_root / "development_view.parquet"
    _write_benchmark_parquet(development, rows=rows)
    binding = _binding_for_files(
        [development], input_kind="BENCHMARK_DEVELOPMENT", row_count=len(rows)
    )
    outcome = materialize_stage02(
        _run_config(tmp_path, input_root, binding, "benchmark")
    )
    table = _read_output_table(outcome.output_directory)
    assert table.num_rows == len(rows)
    assert table["source_schema_version"].to_pylist() == [SOURCE_SCHEMA_VERSION] * len(
        rows
    )
    assert table["staging_version"].to_pylist() == [
        BENCHMARK_OUTPUT_SCHEMA_VERSION
    ] * len(rows)
    assert all("holdout" not in str(path).casefold() for path in tmp_path.rglob("*"))


def test_benchmark_holdout_rows_and_paths_fail_closed(tmp_path: Path) -> None:
    input_root = tmp_path / "development"
    input_root.mkdir(mode=0o700)
    artifact = input_root / "view.parquet"
    _write_benchmark_parquet(artifact, rows=_scenario_rows()[:1], split="HOLDOUT")
    binding = _binding_for_files(
        [artifact], input_kind="BENCHMARK_DEVELOPMENT", row_count=1
    )
    with pytest.raises(Stage02ValidationError, match="HOLDOUT_ACCESS_PROHIBITED"):
        materialize_stage02(_run_config(tmp_path, input_root, binding, "row"))
    with pytest.raises(Stage02ValidationError, match="HOLDOUT_ACCESS_PROHIBITED"):
        stage02_logical_dataset_sha256_v1(
            replace(
                binding,
                artifacts=(
                    Stage02InputArtifact(
                        1,
                        "holdout/holdout.parquet",
                        artifact.stat().st_size,
                        _sha256(artifact),
                    ),
                ),
            )
        )


def test_null_raw_value_and_wrong_schema_fail_closed(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    input_root.mkdir(mode=0o700)
    null_shard = input_root / "null.parquet"
    _write_stage1_parquet(
        null_shard,
        source_file="a.csv",
        source_sha256="55" * 32,
        rows=_scenario_rows()[:1],
        null_column="city",
    )
    binding = _binding_for_files([null_shard], row_count=1)
    with pytest.raises(Stage02ValidationError, match="UPSTREAM_SCHEMA_MISMATCH"):
        materialize_stage02(_run_config(tmp_path, input_root, binding, "null"))

    wrong_root = tmp_path / "wrong"
    wrong_root.mkdir(mode=0o700)
    wrong = wrong_root / "wrong.parquet"
    pq.write_table(pa.table({"id": ["fictional"]}), wrong, write_page_checksum=True)
    wrong.chmod(0o600)
    wrong_binding = _binding_for_files([wrong], row_count=1)
    with pytest.raises(Stage02ValidationError, match="UPSTREAM_SCHEMA_MISMATCH"):
        materialize_stage02(
            _run_config(tmp_path, wrong_root, wrong_binding, "wrong-schema")
        )


def test_invalid_upstream_identity_hash_and_permissions_fail_closed(
    tmp_path: Path,
) -> None:
    input_root, binding, _rows = _stage1_fixture(tmp_path)
    with pytest.raises(Stage02ValidationError, match="UPSTREAM_CONTRACT_MISMATCH"):
        stage02_logical_dataset_sha256_v1(
            replace(binding, upstream_contract_version="unknown")
        )
    with pytest.raises(Stage02ValidationError, match="INVALID_SHA256"):
        stage02_logical_dataset_sha256_v1(
            replace(binding, upstream_logical_identity_sha256="ABC")
        )
    shard = input_root / "source-a.parquet"
    tampered = bytearray(shard.read_bytes())
    tampered[-1] ^= 1
    shard.write_bytes(tampered)
    shard.chmod(0o600)
    with pytest.raises(Stage02ValidationError, match="INPUT_ARTIFACT_SHA256_MISMATCH"):
        materialize_stage02(_run_config(tmp_path, input_root, binding, "tampered"))


def test_stable_id_source_identity_and_canonical_order_fail_closed(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "input"
    input_root.mkdir(mode=0o700)
    bad_id = input_root / "bad-id.parquet"
    _write_stage1_parquet(
        bad_id,
        source_file="a.csv",
        source_sha256="55" * 32,
        rows=_scenario_rows()[:1],
        stable_id_override=b"x" * 32,
    )
    with pytest.raises(Stage02ValidationError, match="STABLE_SOURCE_ROW_ID_MISMATCH"):
        materialize_stage02(
            _run_config(
                tmp_path,
                input_root,
                _binding_for_files([bad_id], row_count=1),
                "bad-id",
            )
        )

    gap_root = tmp_path / "gap"
    gap_root.mkdir(mode=0o700)
    gap = gap_root / "gap.parquet"
    _write_stage1_parquet(
        gap,
        source_file="a.csv",
        source_sha256="77" * 32,
        rows=_scenario_rows()[:2],
        logical_ordinals=[1, 3],
    )
    with pytest.raises(
        Stage02ValidationError, match="NONCONTIGUOUS_STAGE01_PROVENANCE"
    ):
        materialize_stage02(
            _run_config(
                tmp_path,
                gap_root,
                _binding_for_files([gap], row_count=2),
                "gap",
            )
        )

    duplicate_root = tmp_path / "duplicate"
    duplicate_root.mkdir(mode=0o700)
    first = duplicate_root / "first.parquet"
    second = duplicate_root / "second.parquet"
    rows = _scenario_rows()[:1]
    _write_stage1_parquet(
        first, source_file="a.csv", source_sha256="66" * 32, rows=rows
    )
    _write_stage1_parquet(
        second, source_file="b.csv", source_sha256="66" * 32, rows=rows
    )
    with pytest.raises(Stage02ValidationError, match="DUPLICATE_SOURCE_CONTENT"):
        materialize_stage02(
            _run_config(
                tmp_path,
                duplicate_root,
                _binding_for_files([first, second], row_count=2),
                "duplicate",
            )
        )


def test_bundle_is_private_atomic_and_tampering_fails_closed(tmp_path: Path) -> None:
    input_root, binding, _rows = _stage1_fixture(tmp_path)
    config = _run_config(tmp_path, input_root, binding, "private")
    outcome = materialize_stage02(config)
    for root, directories, files in os.walk(outcome.output_directory):
        assert stat.S_IMODE(Path(root).stat().st_mode) == 0o700
        for directory in directories:
            assert stat.S_IMODE((Path(root) / directory).stat().st_mode) == 0o700
        for file_name in files:
            assert stat.S_IMODE((Path(root) / file_name).stat().st_mode) == 0o600
    with pytest.raises(Stage02ValidationError, match="OUTPUT_COLLISION"):
        materialize_stage02(config)
    manifest = outcome.output_directory / STAGE02_MANIFEST_NAME
    manifest.write_bytes(manifest.read_bytes().replace(b"PASS", b"FAIL", 1))
    manifest.chmod(0o600)
    with pytest.raises(Stage02ValidationError, match="TERMINAL_MISMATCH"):
        validate_stage02_bundle(outcome.output_directory)

    partial = tmp_path / "partial"
    partial.mkdir(mode=0o700)
    (partial / "data").mkdir(mode=0o700)
    (partial / "_IN_PROGRESS").write_text("incomplete", encoding="utf-8")
    (partial / "_IN_PROGRESS").chmod(0o600)
    with pytest.raises(Stage02ValidationError, match="STAGE02_INCOMPLETE"):
        validate_stage02_bundle(partial)


def test_input_symlinks_and_broad_permissions_fail_closed(tmp_path: Path) -> None:
    input_root, binding, _rows = _stage1_fixture(tmp_path)
    shard = input_root / "source-a.parquet"
    target = input_root / "target.parquet"
    shard.rename(target)
    shard.symlink_to(target.name)
    with pytest.raises(Stage02ValidationError, match="UNSAFE_INPUT_ARTIFACT"):
        materialize_stage02(_run_config(tmp_path, input_root, binding, "symlink"))

    permission_root = tmp_path / "permission"
    permission_root.mkdir(mode=0o700)
    broad = permission_root / "broad.parquet"
    _write_stage1_parquet(
        broad,
        source_file="a.csv",
        source_sha256="88" * 32,
        rows=_scenario_rows()[:1],
    )
    broad.chmod(0o644)
    with pytest.raises(Stage02ValidationError, match="PERMISSION_FAILURE"):
        materialize_stage02(
            _run_config(
                tmp_path,
                permission_root,
                _binding_for_files([broad], row_count=1),
                "broad",
            )
        )


def test_manifest_and_cli_surface_do_not_expose_raw_values(tmp_path: Path) -> None:
    input_root, binding, rows = _stage1_fixture(tmp_path)
    outcome = materialize_stage02(_run_config(tmp_path, input_root, binding, "privacy"))
    manifest = (outcome.output_directory / STAGE02_MANIFEST_NAME).read_bytes()
    success = (outcome.output_directory / STAGE02_SUCCESS_MARKER).read_bytes()
    protected_values = (
        '  Fictional "Road", 1  ',
        "Suite A\nLevel 2",
        "Москва, корпус 2",
        "架空通り五丁目",
        "Fictional Munich Street 5",
        "unusual-length",
        "rare-fictional-priority",
    )
    for value in protected_values:
        assert value.encode("utf-8") not in manifest
        assert value.encode("utf-8") not in success
    with pytest.raises(Stage02ValidationError, match="INVALID_OPERATIONAL_METADATA"):
        materialize_stage02(
            _run_config(
                tmp_path,
                input_root,
                binding,
                "unsafe-metadata",
                operational_metadata={"address": "Fictional Road 1"},
            )
        )


def test_production_guard_precedes_any_input_access(tmp_path: Path) -> None:
    config = Stage02RunConfig(
        input_root=tmp_path / "absent",
        input_binding_file=tmp_path / "absent.json",
        expected_input_binding_sha256="11" * 32,
        output_directory=tmp_path / "output",
        adopting_git_commit=ADOPTING_COMMIT,
        production=True,
    )
    with pytest.raises(ExecutionPolicyError, match="HEAVY_PROCESS_CLUSTER_REQUIRED"):
        materialize_stage02(config)
    assert not config.output_directory.exists()


def test_stage02_cluster_launcher_is_explicit_and_has_no_data_constants() -> None:
    script = Path("cluster/goethe_nhr/stage02_harmonization.sbatch").read_text(
        encoding="utf-8"
    )
    assert "SAFE_EXECUTION_SITE=goethe-nhr" in script
    assert "SLURM_JOB_ID:?SLURM_JOB_ID is required" in script
    assert "STAGE02_INPUT_BINDING_SHA256" in script
    assert "STAGE02_INPUT_ROOT" in script
    assert "python -m safe_geocoding_pipeline.preprocessing.stage02_cli" in script
    for forbidden in ("1405", "1411", "35000", "15000", "holdout.parquet"):
        assert forbidden not in script
