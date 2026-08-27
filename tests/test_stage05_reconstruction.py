from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import safe_geocoding_pipeline.preprocessing.stages.s05_reconstruction as stage05
from safe_geocoding_pipeline.preprocessing.stages.s02_harmonization import (
    NATIVE_ADDRESS_COLUMNS,
    STANDARD_ADDRESS_COLUMNS,
)
from safe_geocoding_pipeline.preprocessing.stages.s03_cleaning import (
    CLEAN_DERIVED_COLUMNS,
)
from safe_geocoding_pipeline.preprocessing.stages.s04_lowercase import (
    LOWER_OUTPUT_COLUMNS,
    STAGE04_CONTRACT_VERSION,
    STAGE04_PROFILE_VERSION,
    stage04_schema,
)
from safe_geocoding_pipeline.preprocessing.stages.s05_reconstruction import (
    ACCEPTED_STAGE04_SCHEMA_FINGERPRINT,
    CANONICAL_OUTPUT_COLUMNS,
    CASE_PRESERVED_OUTPUT_COLUMNS,
    STAGE05_AUDIT_COLUMNS,
    STAGE05_CONTRACT_VERSION,
    STAGE05_DERIVED_COLUMNS,
    STAGE05_PROFILE_VERSION,
    STAGE05_SEPARATOR,
    Stage05InputBinding,
    Stage05RunConfig,
    Stage05ValidationError,
    materialize_stage05,
    reconstruct_candidate,
    stage05_logical_dataset_sha256_v1,
    stage05_schema,
    stage05_schema_fingerprint,
    validate_stage05_bundle,
    validate_stage05_input_binding,
    write_stage05_input_binding,
)

EXECUTION_GIT_SHA = "a" * 40
BENCHMARK_FINGERPRINT = "b" * 64


@pytest.mark.parametrize(
    ("lines", "candidate", "mask"),
    (
        (("", "", "", ""), "", "0000"),
        (("A", "", "", ""), "A", "1000"),
        (("", "B", "", ""), "B", "0100"),
        (("", "", "", "D"), "D", "0001"),
        (("A", "B", "", ""), "A B", "1100"),
        (("A", "", "C", ""), "A C", "1010"),
        (("", "B", "", "D"), "B D", "0101"),
        (("A", "B", "C", "D"), "A B C D", "1111"),
        (("A", "A", "", ""), "A A", "1100"),
        (("A,", "B", "", ""), "A, B", "1100"),
        (("A;", "B", "", ""), "A; B", "1100"),
        (("A/", "B", "", ""), "A/ B", "1100"),
        (("A-", "B", "", ""), "A- B", "1100"),
        (("A(", "B)", "", ""), "A( B)", "1100"),
        (("A،", "B", "", ""), "A، B", "1100"),
        (("École", "Straße", "", ""), "École Straße", "1100"),
        (("العربية", "خیابان آزادی", "", ""), "العربية خیابان آزادی", "1100"),
        (("МОСКВА", "УЛИЦА", "", ""), "МОСКВА УЛИЦА", "1100"),
        (("東京都", "新宿区", "", ""), "東京都 新宿区", "1100"),
        (("Tokyo 東京", "", "", ""), "Tokyo 東京", "1000"),
    ),
)
def test_reconstruction_contract_vectors(
    lines: tuple[str, str, str, str], candidate: str, mask: str
) -> None:
    result = reconstruct_candidate(lines)
    assert result.candidate == candidate
    assert result.contributing_line_mask == mask
    assert result.contributing_line_count == mask.count("1")
    assert result.available is bool(candidate)
    assert reconstruct_candidate((candidate, "", "", "")).candidate == candidate


def test_separator_content_is_never_mutated() -> None:
    lines = ("A,", "B;", "C / D", "（E）")
    result = reconstruct_candidate(lines)
    assert result.candidate == STAGE05_SEPARATOR.join(lines)
    assert result.candidate == "A, B; C / D （E）"


def test_separator_does_not_add_punctuation_or_component_semantics() -> None:
    assert reconstruct_candidate(("North,", "Quarter", "", "")).candidate == (
        "North, Quarter"
    )
    assert reconstruct_candidate(("Long", "name", "", "")).candidate == "Long name"
    assert reconstruct_candidate(("21st", "District", "", "")).candidate == (
        "21st District"
    )


def test_giant_values_are_not_truncated() -> None:
    giant = "東京-É-العربية-" * 250_000
    result = reconstruct_candidate((giant, giant, giant, giant))
    assert result.candidate == STAGE05_SEPARATOR.join((giant,) * 4)
    assert len(result.candidate) == len(giant) * 4 + len(STAGE05_SEPARATOR) * 3


def test_reconstruction_rejects_malformed_input() -> None:
    with pytest.raises(Stage05ValidationError, match="INVALID_RECONSTRUCTION_INPUT"):
        reconstruct_candidate(("A", "B"))
    with pytest.raises(Stage05ValidationError, match="INVALID_RECONSTRUCTION_INPUT"):
        reconstruct_candidate(("A", "B", "C", None))  # type: ignore[arg-type]
    with pytest.raises(Stage05ValidationError, match="INVALID_RECONSTRUCTION_INPUT"):
        reconstruct_candidate(("A", "B", "C", "bad\ud800"))


def _stage04_batch(rows: list[dict[str, str]]) -> pa.RecordBatch:
    schema = stage04_schema()
    values: dict[str, list[object]] = {
        field.name: ["" for _ in rows] for field in schema
    }
    for field in schema:
        if pa.types.is_uint64(field.type) or pa.types.is_uint8(field.type):
            values[field.name] = [0 for _ in rows]
        elif pa.types.is_boolean(field.type):
            values[field.name] = [False for _ in rows]
        elif pa.types.is_fixed_size_binary(field.type):
            values[field.name] = [
                hashlib.sha256(f"{field.name}-{index}".encode()).digest()
                for index in range(len(rows))
            ]
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
        standard_count = sum(
            values[name][index] != "" for name in STANDARD_ADDRESS_COLUMNS
        )
        native_count = sum(values[name][index] != "" for name in NATIVE_ADDRESS_COLUMNS)
        values["standard_nonempty_source_line_count"][index] = standard_count
        values["native_nonempty_source_line_count"][index] = native_count
        values["standard_has_nonempty_source_line"][index] = bool(standard_count)
        values["native_has_nonempty_source_line"][index] = bool(native_count)
    arrays = [pa.array(values[field.name], type=field.type) for field in schema]
    return pa.RecordBatch.from_arrays(arrays, schema=schema)


def test_projected_batch_appends_only_stage05_fields_and_keeps_representations() -> (
    None
):
    batch = _stage04_batch(
        [
            {
                "stage03_clean_street_address_line_1": "A",
                "stage03_clean_street_address_line_3": "C",
                "stage03_clean_street_address_line_1_native": "甲",
                "stage03_clean_street_address_line_2_native": "乙",
            },
            {
                "stage03_clean_street_address_line_2": "Only standard",
            },
            {
                "stage03_clean_street_address_line_4_native": "فقط بومی",
            },
            {},
            {
                "stage03_clean_street_address_line_1": "Same",
                "stage03_clean_street_address_line_1_native": "Same",
            },
        ]
    )
    projected = stage05._project_batch(batch, metadata={})
    assert projected.num_rows == batch.num_rows
    assert projected.schema.names[: len(stage04_schema())] == stage04_schema().names
    for index in range(batch.num_columns):
        assert projected.column(index).equals(batch.column(index))
    assert projected.column(
        projected.schema.get_field_index(CASE_PRESERVED_OUTPUT_COLUMNS[0])
    ).to_pylist() == [
        "A C",
        "Only standard",
        "",
        "",
        "Same",
    ]
    assert projected.column(
        projected.schema.get_field_index(CASE_PRESERVED_OUTPUT_COLUMNS[1])
    ).to_pylist() == [
        "甲 乙",
        "",
        "فقط بومی",
        "",
        "Same",
    ]
    assert projected.column(
        projected.schema.get_field_index(CANONICAL_OUTPUT_COLUMNS[0])
    ).to_pylist() == [
        "a c",
        "only standard",
        "",
        "",
        "same",
    ]
    assert projected.column(
        projected.schema.get_field_index(STAGE05_AUDIT_COLUMNS[4])
    ).to_pylist() == [
        "1010",
        "0100",
        "0000",
        "0000",
        "1000",
    ]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ordered_digest(batch: pa.RecordBatch) -> str:
    hasher = stage05._OrderedStableIdentityHasher()
    hasher.update(batch.column(batch.schema.get_field_index("stable_source_row_id_v1")))
    return hasher.hexdigest()


def _synthetic_stage04_root(tmp_path: Path) -> tuple[Path, Stage05InputBinding]:
    root = tmp_path / "stage04" / "accepted"
    data = root / "data"
    data.mkdir(parents=True, mode=0o700)
    root.chmod(0o700)
    data.chmod(0o700)
    batch = _stage04_batch(
        [
            {
                "stage03_clean_street_address_line_1": "A",
                "stage03_clean_street_address_line_3": "C",
                "stage03_clean_street_address_line_1_native": "甲",
            },
            {
                "stage03_clean_street_address_line_1": "A,",
                "stage03_clean_street_address_line_2": "A,",
                "stage03_clean_street_address_line_2_native": "Б",
                "stage03_clean_street_address_line_4_native": "В",
            },
            {},
        ]
    )
    path = data / "part-000001.parquet"
    pq.write_table(
        pa.Table.from_batches([batch]),
        path,
        row_group_size=2,
        compression="zstd",
        write_page_checksum=True,
    )
    path.chmod(0o600)
    ordered = _ordered_digest(batch)
    binding = Stage05InputBinding(
        upstream_contract_version=STAGE04_CONTRACT_VERSION,
        upstream_profile_version=STAGE04_PROFILE_VERSION,
        upstream_logical_fingerprint="1" * 64,
        upstream_schema_fingerprint=ACCEPTED_STAGE04_SCHEMA_FINGERPRINT,
        upstream_input_binding_sha256="2" * 64,
        upstream_manifest_sha256="3" * 64,
        upstream_ordered_identity_sha256=ordered,
        input_benchmark_fingerprint=BENCHMARK_FINGERPRINT,
        expected_row_count=3,
    )
    manifest = {
        "scientific_identity": {
            "stage04_contract_version": STAGE04_CONTRACT_VERSION,
            "stage04_profile_version": STAGE04_PROFILE_VERSION,
            "input_benchmark_fingerprint": BENCHMARK_FINGERPRINT,
        },
        "physical_identity": {
            "output_artifacts": [
                {
                    "relative_path": "data/part-000001.parquet",
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                    "row_count": 3,
                }
            ]
        },
    }
    manifest_path = root / "stage04_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    manifest_path.chmod(0o600)
    return root, binding


def _fake_stage04_validation(binding: Stage05InputBinding) -> SimpleNamespace:
    return SimpleNamespace(
        logical_dataset_sha256_v1=binding.upstream_logical_fingerprint,
        schema_fingerprint=binding.upstream_schema_fingerprint,
        input_binding_sha256=binding.upstream_input_binding_sha256,
        ordered_identity_sha256=binding.upstream_ordered_identity_sha256,
        row_count=binding.expected_row_count,
    )


def test_materialization_preservation_determinism_permissions_and_readback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, binding = _synthetic_stage04_root(tmp_path)
    monkeypatch.setattr(
        stage05,
        "validate_stage04_bundle",
        lambda *args, **kwargs: _fake_stage04_validation(binding),
    )
    binding_path = tmp_path / "binding" / "stage05.json"
    binding_sha = write_stage05_input_binding(binding_path, binding)
    output = tmp_path / "stage05" / "candidate"
    outcome = materialize_stage05(
        Stage05RunConfig(
            stage04_output_directory=root,
            input_binding_file=binding_path,
            expected_input_binding_sha256=binding_sha,
            output_directory=output,
            execution_git_sha=EXECUTION_GIT_SHA,
            production=False,
            authoritative_development=False,
            batch_rows=2,
            target_batch_bytes=1024 * 1024,
        )
    )
    input_table = pq.read_table(root / "data" / "part-000001.parquet")
    output_table = pq.read_table(output / "data" / "part-000001.parquet")
    assert outcome.row_count == input_table.num_rows == output_table.num_rows == 3
    for name in stage04_schema().names:
        assert output_table.column(name).equals(input_table.column(name))
    assert output_table.schema.names[-10:] == list(STAGE05_DERIVED_COLUMNS)
    assert output_table.column(CANONICAL_OUTPUT_COLUMNS[0]).to_pylist() == [
        "a c",
        "a, a,",
        "",
    ]
    assert output_table.column(CANONICAL_OUTPUT_COLUMNS[1]).to_pylist() == [
        "甲",
        "б в",
        "",
    ]
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o600
        for path in output.rglob("*")
        if path.is_file()
    )
    validated = validate_stage05_bundle(
        output,
        expected_manifest_sha256=outcome.manifest_sha256,
        authoritative_development=False,
    )
    assert validated.metrics == outcome.metrics
    repeated = materialize_stage05(
        Stage05RunConfig(
            stage04_output_directory=root,
            input_binding_file=binding_path,
            expected_input_binding_sha256=binding_sha,
            output_directory=tmp_path / "stage05" / "repeated",
            execution_git_sha=EXECUTION_GIT_SHA,
            production=False,
            authoritative_development=False,
            batch_rows=2,
            target_batch_bytes=1024 * 1024,
        )
    )
    assert repeated.logical_dataset_sha256_v1 == outcome.logical_dataset_sha256_v1
    assert repeated.schema_fingerprint == outcome.schema_fingerprint
    assert repeated.ordered_identity_sha256 == outcome.ordered_identity_sha256
    assert repeated.metrics == outcome.metrics
    assert _sha256(repeated.output_directory / "data" / "part-000001.parquet") == (
        _sha256(output / "data" / "part-000001.parquet")
    )
    assert outcome.metrics["GAP_FINDINGS"] == {
        "STANDARD_GAP_ROWS": 1,
        "NATIVE_GAP_ROWS": 1,
    }
    assert (
        outcome.metrics["DUPLICATE_LINE_FINDINGS"][
            "STANDARD_ROWS_WITH_EXACT_DUPLICATE_LOWER_LINES"
        ]
        == 1
    )


def test_batch_boundary_independence(tmp_path: Path) -> None:
    batch = _stage04_batch(
        [
            {"stage03_clean_street_address_line_1": "A"},
            {"stage03_clean_street_address_line_2": "B"},
            {"stage03_clean_street_address_line_4": "D"},
        ]
    )
    complete = stage05._project_batch(batch, metadata={})
    split = [
        stage05._project_batch(batch.slice(0, 1), metadata={}),
        stage05._project_batch(batch.slice(1, 2), metadata={}),
    ]
    assert pa.Table.from_batches([complete]).equals(pa.Table.from_batches(split))


def test_schema_contract_binding_and_logical_fingerprint() -> None:
    assert stage05_schema().names[: len(stage04_schema())] == stage04_schema().names
    assert tuple(stage05_schema().names[-10:]) == STAGE05_DERIVED_COLUMNS
    assert len(stage05_schema_fingerprint()) == 64
    base = Stage05InputBinding(
        upstream_contract_version=STAGE04_CONTRACT_VERSION,
        upstream_profile_version=STAGE04_PROFILE_VERSION,
        upstream_logical_fingerprint="1" * 64,
        upstream_schema_fingerprint=ACCEPTED_STAGE04_SCHEMA_FINGERPRINT,
        upstream_input_binding_sha256="2" * 64,
        upstream_manifest_sha256="3" * 64,
        upstream_ordered_identity_sha256="4" * 64,
        input_benchmark_fingerprint=BENCHMARK_FINGERPRINT,
        expected_row_count=3,
    )
    validate_stage05_input_binding(base)
    observed = stage05_logical_dataset_sha256_v1(base)
    assert observed == stage05_logical_dataset_sha256_v1(base)
    assert observed != stage05_logical_dataset_sha256_v1(
        replace(base, upstream_logical_fingerprint="5" * 64)
    )
    with pytest.raises(Stage05ValidationError, match="UPSTREAM_CONTRACT_MISMATCH"):
        validate_stage05_input_binding(replace(base, upstream_contract_version="wrong"))
    with pytest.raises(
        Stage05ValidationError, match="AUTHORITATIVE_DEVELOPMENT_BINDING_MISMATCH"
    ):
        validate_stage05_input_binding(base, authoritative_development=True)


def test_prohibited_scope_wrong_binding_manifest_and_incomplete_output_fail_closed(
    tmp_path: Path,
) -> None:
    base = Stage05InputBinding(
        upstream_contract_version=STAGE04_CONTRACT_VERSION,
        upstream_profile_version=STAGE04_PROFILE_VERSION,
        upstream_logical_fingerprint="1" * 64,
        upstream_schema_fingerprint=ACCEPTED_STAGE04_SCHEMA_FINGERPRINT,
        upstream_input_binding_sha256="2" * 64,
        upstream_manifest_sha256="3" * 64,
        upstream_ordered_identity_sha256="4" * 64,
        input_benchmark_fingerprint=BENCHMARK_FINGERPRINT,
        expected_row_count=3,
    )
    with pytest.raises(Stage05ValidationError, match="HOLDOUT_ACCESS_PROHIBITED"):
        write_stage05_input_binding(tmp_path / "holdout" / "binding.json", base)
    with pytest.raises(Stage05ValidationError, match="INVALID_SHA256"):
        Stage05RunConfig(
            stage04_output_directory=tmp_path / "development",
            input_binding_file=tmp_path / "binding.json",
            expected_input_binding_sha256="wrong",
            output_directory=tmp_path / "output",
            execution_git_sha=EXECUTION_GIT_SHA,
        ).validate()
    incomplete = tmp_path / "stage05" / "incomplete"
    (incomplete / "data").mkdir(parents=True, mode=0o700)
    incomplete.chmod(0o700)
    (incomplete / "data").chmod(0o700)
    with pytest.raises(Stage05ValidationError, match="STAGE05_TERMINAL_MISSING"):
        validate_stage05_bundle(
            incomplete,
            expected_manifest_sha256="0" * 64,
            authoritative_development=False,
        )


def test_published_validation_rejects_wrong_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, binding = _synthetic_stage04_root(tmp_path)
    monkeypatch.setattr(
        stage05,
        "validate_stage04_bundle",
        lambda *args, **kwargs: _fake_stage04_validation(binding),
    )
    binding_path = tmp_path / "binding" / "stage05.json"
    binding_sha = write_stage05_input_binding(binding_path, binding)
    outcome = materialize_stage05(
        Stage05RunConfig(
            stage04_output_directory=root,
            input_binding_file=binding_path,
            expected_input_binding_sha256=binding_sha,
            output_directory=tmp_path / "stage05" / "candidate",
            execution_git_sha=EXECUTION_GIT_SHA,
            production=False,
            authoritative_development=False,
        )
    )
    with pytest.raises(
        Stage05ValidationError, match="STAGE05_MANIFEST_SHA256_MISMATCH"
    ):
        validate_stage05_bundle(
            outcome.output_directory,
            expected_manifest_sha256="f" * 64,
            authoritative_development=False,
        )


def test_versions_are_explicit_and_stage6_is_absent() -> None:
    assert STAGE05_CONTRACT_VERSION == "stage05_address_reconstruction_contract_v2"
    assert STAGE05_PROFILE_VERSION == "stage05_address_reconstruction_profile_v2"
    assert all(name.startswith("stage05_") for name in STAGE05_DERIVED_COLUMNS)
    source = Path(stage05.__file__).read_text(encoding="utf-8")
    assert "stage06" not in source.casefold()
    assert "libpostal" not in source.casefold()
