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
import safe_geocoding_pipeline.preprocessing.stages.s06_exact_deduplication as stage06
from safe_geocoding_pipeline.preprocessing.stages.s04_lowercase import (
    STAGE04_CONTRACT_VERSION,
    STAGE04_PROFILE_VERSION,
)
from safe_geocoding_pipeline.preprocessing.stages.s05_reconstruction import (
    ACCEPTED_STAGE04_SCHEMA_FINGERPRINT,
    STAGE05_CONTRACT_VERSION,
    STAGE05_PROFILE_VERSION,
    Stage05InputBinding,
    Stage05RunConfig,
    materialize_stage05,
    stage05_schema,
    write_stage05_input_binding,
)
from safe_geocoding_pipeline.preprocessing.stages.s06_exact_deduplication import (
    ACCEPTED_BENCHMARK_FINGERPRINT,
    ACCEPTED_DEVELOPMENT_ROWS,
    ACCEPTED_FIXED_500_FINGERPRINT,
    ACCEPTED_STAGE05_INPUT_BINDING_SHA256,
    ACCEPTED_STAGE05_LOGICAL_FINGERPRINT,
    ACCEPTED_STAGE05_MANIFEST_SHA256,
    ACCEPTED_STAGE05_ORDERED_IDENTITY_SHA256,
    ACCEPTED_STAGE05_SCHEMA_FINGERPRINT,
    REGISTRY_COLUMNS,
    ROW_MAP_ID_COLUMNS,
    STAGE06_CANDIDATE_ID_DOMAIN,
    STAGE06_CONTRACT_VERSION,
    STAGE06_PROFILE_VERSION,
    Stage06InputBinding,
    Stage06RunConfig,
    Stage06ValidationError,
    exact_candidate_id_v1,
    materialize_stage06,
    registry_schema,
    row_map_schema,
    stage06_contract_fingerprint_v1,
    stage06_schema_fingerprint,
    validate_stage06_bundle,
    validate_stage06_input_binding,
    write_stage06_input_binding,
)
from test_stage05_reconstruction import (
    BENCHMARK_FINGERPRINT,
    EXECUTION_GIT_SHA,
    _ordered_digest,
    _sha256,
    _stage04_batch,
)

FIXED_500_FINGERPRINT = "c" * 64


class _ConstantDigest:
    def update(self, value: bytes) -> None:
        del value

    def digest(self) -> bytes:
        return bytes([7]) * 32

    def hexdigest(self) -> str:
        return self.digest().hex()


def _constant_digest() -> _ConstantDigest:
    return _ConstantDigest()


def _stage05_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rows: list[dict[str, str]],
) -> tuple[Path, object]:
    stage04_root = tmp_path / "stage04" / "accepted"
    stage04_data = stage04_root / "data"
    stage04_data.mkdir(parents=True, mode=0o700)
    stage04_root.chmod(0o700)
    stage04_data.chmod(0o700)
    batch = _stage04_batch(rows)
    stage04_path = stage04_data / "part-000001.parquet"
    pq.write_table(
        pa.Table.from_batches([batch]),
        stage04_path,
        row_group_size=max(1, min(3, len(rows))),
        compression="zstd",
        write_page_checksum=True,
    )
    stage04_path.chmod(0o600)
    ordered = _ordered_digest(batch)
    stage04_manifest = {
        "scientific_identity": {
            "stage04_contract_version": STAGE04_CONTRACT_VERSION,
            "stage04_profile_version": STAGE04_PROFILE_VERSION,
            "input_benchmark_fingerprint": BENCHMARK_FINGERPRINT,
        },
        "physical_identity": {
            "output_artifacts": [
                {
                    "relative_path": "data/part-000001.parquet",
                    "size_bytes": stage04_path.stat().st_size,
                    "sha256": _sha256(stage04_path),
                    "row_count": len(rows),
                }
            ]
        },
    }
    stage04_manifest_path = stage04_root / "stage04_manifest.json"
    stage04_manifest_path.write_text(json.dumps(stage04_manifest), encoding="utf-8")
    stage04_manifest_path.chmod(0o600)
    stage05_binding = Stage05InputBinding(
        upstream_contract_version=STAGE04_CONTRACT_VERSION,
        upstream_profile_version=STAGE04_PROFILE_VERSION,
        upstream_logical_fingerprint="1" * 64,
        upstream_schema_fingerprint=ACCEPTED_STAGE04_SCHEMA_FINGERPRINT,
        upstream_input_binding_sha256="2" * 64,
        upstream_manifest_sha256="3" * 64,
        upstream_ordered_identity_sha256=ordered,
        input_benchmark_fingerprint=BENCHMARK_FINGERPRINT,
        expected_row_count=len(rows),
    )
    stage04_outcome = SimpleNamespace(
        logical_dataset_sha256_v1=stage05_binding.upstream_logical_fingerprint,
        schema_fingerprint=stage05_binding.upstream_schema_fingerprint,
        input_binding_sha256=stage05_binding.upstream_input_binding_sha256,
        ordered_identity_sha256=ordered,
        row_count=len(rows),
    )
    monkeypatch.setattr(
        stage05, "validate_stage04_bundle", lambda *args, **kwargs: stage04_outcome
    )
    stage05_binding_path = tmp_path / "bindings" / "stage05.json"
    stage05_binding_sha = write_stage05_input_binding(
        stage05_binding_path, stage05_binding
    )
    stage05_outcome = materialize_stage05(
        Stage05RunConfig(
            stage04_output_directory=stage04_root,
            input_binding_file=stage05_binding_path,
            expected_input_binding_sha256=stage05_binding_sha,
            output_directory=tmp_path / "stage05" / "candidate",
            execution_git_sha=EXECUTION_GIT_SHA,
            production=False,
            authoritative_development=False,
            batch_rows=2,
            target_batch_bytes=4 * 1024 * 1024,
        )
    )
    return stage05_outcome.output_directory, stage05_outcome


def _stage06_binding(
    tmp_path: Path, stage05_outcome: object
) -> tuple[Stage06InputBinding, Path, str]:
    binding = Stage06InputBinding(
        upstream_contract_version=STAGE05_CONTRACT_VERSION,
        upstream_profile_version=STAGE05_PROFILE_VERSION,
        upstream_logical_fingerprint=stage05_outcome.logical_dataset_sha256_v1,
        upstream_schema_fingerprint=stage05_outcome.schema_fingerprint,
        upstream_input_binding_sha256=stage05_outcome.input_binding_sha256,
        upstream_manifest_sha256=stage05_outcome.manifest_sha256,
        upstream_ordered_identity_sha256=stage05_outcome.ordered_identity_sha256,
        input_benchmark_fingerprint=BENCHMARK_FINGERPRINT,
        fixed_500_fingerprint=FIXED_500_FINGERPRINT,
        expected_row_count=stage05_outcome.row_count,
    )
    path = tmp_path / "bindings" / "stage06.json"
    return binding, path, write_stage06_input_binding(path, binding)


def _rows() -> list[dict[str, str]]:
    return [
        {},
        {"stage03_clean_street_address_line_1": "Alpha"},
        {"stage03_clean_street_address_line_1_native": "ALPHA"},
        {
            "stage03_clean_street_address_line_1": "Alpha",
            "stage03_clean_street_address_line_1_native": "alpha",
        },
        {
            "stage03_clean_street_address_line_1": "A!",
            "stage03_clean_street_address_line_1_native": "A ",
        },
        {
            "stage03_clean_street_address_line_1": "É",
            "stage03_clean_street_address_line_1_native": "É",
        },
        {
            "stage03_clean_street_address_line_1": "شارع",
            "stage03_clean_street_address_line_1_native": "МОСКВА",
        },
        {
            "stage03_clean_street_address_line_1": "東京",
            "stage03_clean_street_address_line_1_native": "🏠",
        },
    ]


def test_candidate_id_formula_golden_unicode_chunk_and_giant() -> None:
    candidate = "École 東京 شارع é 🏠".lower()
    expected = hashlib.sha256(
        STAGE06_CANDIDATE_ID_DOMAIN + candidate.encode("utf-8")
    ).digest()
    assert exact_candidate_id_v1(candidate) == expected
    assert exact_candidate_id_v1(candidate, chunk_codepoints=1) == expected
    assert exact_candidate_id_v1(candidate, chunk_codepoints=7) == expected
    assert exact_candidate_id_v1("é") != exact_candidate_id_v1("é")
    assert exact_candidate_id_v1("a") != exact_candidate_id_v1("a ")
    giant = "東京-é-شارع-" * 250_000
    assert (
        exact_candidate_id_v1(giant, chunk_codepoints=1024)
        == hashlib.sha256(STAGE06_CANDIDATE_ID_DOMAIN + giant.encode("utf-8")).digest()
    )


def test_candidate_id_rejects_empty_surrogate_and_invalid_digest() -> None:
    with pytest.raises(Stage06ValidationError, match="INVALID_CANDIDATE_TEXT"):
        exact_candidate_id_v1("")
    with pytest.raises(Stage06ValidationError, match="INVALID_CANDIDATE_TEXT"):
        exact_candidate_id_v1("bad\ud800")

    class ShortDigest(_ConstantDigest):
        def digest(self) -> bytes:
            return b"short"

    with pytest.raises(Stage06ValidationError, match="INVALID_DIGEST_IMPLEMENTATION"):
        exact_candidate_id_v1("valid", digest_factory=ShortDigest)


def test_independent_validation_aligns_different_record_batch_boundaries() -> None:
    table = pa.table({"value": [1, 2, 3]})
    left = (table.slice(0, 1).to_batches()[0], table.slice(1, 2).to_batches()[0])
    right = (table.slice(0, 2).to_batches()[0], table.slice(2, 1).to_batches()[0])
    aligned = list(stage06._iter_aligned_batches(left, right))
    assert [batch.num_rows for batch, _ in aligned] == [1, 1, 1]
    assert all(first.equals(second) for first, second in aligned)
    with pytest.raises(Stage06ValidationError, match="OUTPUT_ROW_MISMATCH"):
        list(stage06._iter_aligned_batches(left, right[:1]))


def test_schema_contract_and_binding_are_exact() -> None:
    assert row_map_schema().names[: len(stage05_schema())] == stage05_schema().names
    assert tuple(row_map_schema().names[-2:]) == ROW_MAP_ID_COLUMNS
    assert all(row_map_schema().field(name).nullable for name in ROW_MAP_ID_COLUMNS)
    assert registry_schema().names == list(REGISTRY_COLUMNS)
    assert registry_schema().field(REGISTRY_COLUMNS[0]).type == pa.binary(32)
    assert len(stage06_schema_fingerprint()) == 64
    binding = Stage06InputBinding(
        upstream_contract_version=STAGE05_CONTRACT_VERSION,
        upstream_profile_version=STAGE05_PROFILE_VERSION,
        upstream_logical_fingerprint="1" * 64,
        upstream_schema_fingerprint="2" * 64,
        upstream_input_binding_sha256="3" * 64,
        upstream_manifest_sha256="4" * 64,
        upstream_ordered_identity_sha256="5" * 64,
        input_benchmark_fingerprint="6" * 64,
        fixed_500_fingerprint="7" * 64,
        expected_row_count=8,
    )
    validate_stage06_input_binding(binding)
    assert stage06_contract_fingerprint_v1(binding) == stage06_contract_fingerprint_v1(
        binding
    )
    assert stage06_contract_fingerprint_v1(binding) != stage06_contract_fingerprint_v1(
        replace(binding, expected_row_count=9)
    )
    with pytest.raises(Stage06ValidationError, match="UPSTREAM_CONTRACT_MISMATCH"):
        validate_stage06_input_binding(
            replace(binding, upstream_contract_version="wrong")
        )


@pytest.mark.parametrize(
    ("field", "wrong"),
    (
        ("upstream_manifest_sha256", "1" * 64),
        ("upstream_ordered_identity_sha256", "2" * 64),
        ("input_benchmark_fingerprint", "3" * 64),
        ("fixed_500_fingerprint", "4" * 64),
    ),
)
def test_authoritative_manifest_order_benchmark_and_fixed500_bindings_fail_closed(
    field: str, wrong: str
) -> None:
    accepted = Stage06InputBinding(
        upstream_contract_version=STAGE05_CONTRACT_VERSION,
        upstream_profile_version=STAGE05_PROFILE_VERSION,
        upstream_logical_fingerprint=ACCEPTED_STAGE05_LOGICAL_FINGERPRINT,
        upstream_schema_fingerprint=ACCEPTED_STAGE05_SCHEMA_FINGERPRINT,
        upstream_input_binding_sha256=ACCEPTED_STAGE05_INPUT_BINDING_SHA256,
        upstream_manifest_sha256=ACCEPTED_STAGE05_MANIFEST_SHA256,
        upstream_ordered_identity_sha256=ACCEPTED_STAGE05_ORDERED_IDENTITY_SHA256,
        input_benchmark_fingerprint=ACCEPTED_BENCHMARK_FINGERPRINT,
        fixed_500_fingerprint=ACCEPTED_FIXED_500_FINGERPRINT,
        expected_row_count=ACCEPTED_DEVELOPMENT_ROWS,
    )
    validate_stage06_input_binding(accepted, authoritative_development=True)
    with pytest.raises(
        Stage06ValidationError, match="AUTHORITATIVE_DEVELOPMENT_BINDING_MISMATCH"
    ):
        validate_stage06_input_binding(
            replace(accepted, **{field: wrong}), authoritative_development=True
        )


def test_materialization_row_preservation_registry_and_readback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage05_root, stage05_outcome = _stage05_bundle(tmp_path, monkeypatch, _rows())
    _binding, binding_path, binding_sha = _stage06_binding(tmp_path, stage05_outcome)
    output = tmp_path / "stage06" / "candidate"
    config = Stage06RunConfig(
        stage05_output_directory=stage05_root,
        input_binding_file=binding_path,
        expected_input_binding_sha256=binding_sha,
        output_directory=output,
        execution_git_sha=EXECUTION_GIT_SHA,
        production=False,
        authoritative_development=False,
        batch_rows=2,
        registry_batch_rows=2,
        registry_shard_rows=3,
        target_batch_bytes=4 * 1024 * 1024,
        duckdb_memory_limit="512MB",
        duckdb_threads=2,
    )
    outcome = materialize_stage06(config)
    with pytest.raises(Stage06ValidationError, match="OUTPUT_COLLISION"):
        materialize_stage06(config)
    stage05_table = pq.read_table(stage05_root / "data" / "part-000001.parquet")
    row_map = pq.read_table(output / "row_map" / "data" / "part-000001.parquet")
    registry = pq.read_table(sorted((output / "registry" / "data").glob("*.parquet")))
    assert (
        outcome.row_count == row_map.num_rows == stage05_table.num_rows == len(_rows())
    )
    for name in stage05_schema().names:
        assert row_map.column(name).equals(stage05_table.column(name))
    assert row_map.column(ROW_MAP_ID_COLUMNS[0])[0].as_py() is None
    assert row_map.column(ROW_MAP_ID_COLUMNS[1])[0].as_py() is None
    assert row_map.column(ROW_MAP_ID_COLUMNS[0])[1].as_py() == exact_candidate_id_v1(
        "alpha"
    )
    assert row_map.column(ROW_MAP_ID_COLUMNS[1])[2].as_py() == exact_candidate_id_v1(
        "alpha"
    )
    assert (
        row_map.column(ROW_MAP_ID_COLUMNS[0])[3].as_py()
        == row_map.column(ROW_MAP_ID_COLUMNS[1])[3].as_py()
    )
    ids = registry.column(REGISTRY_COLUMNS[0]).to_pylist()
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids)) == outcome.unique_candidate_count
    assert (
        registry.column(REGISTRY_COLUMNS[2]).to_pylist()[
            ids.index(exact_candidate_id_v1("alpha"))
        ]
        == 4
    )
    assert sum(registry.column(REGISTRY_COLUMNS[2]).to_pylist()) == 12
    assert sum(registry.column(REGISTRY_COLUMNS[3]).to_pylist()) == 6
    assert sum(registry.column(REGISTRY_COLUMNS[4]).to_pylist()) == 6
    assert outcome.metrics["CLEAN_SURFACE_VARIANTS"] == {
        "CANONICAL_GROUPS_WITH_MULTIPLE_CLEAN_SURFACES": 1,
        "CLEAN_SURFACE_COUNT_DISTRIBUTION": {"1": 8, "3": 1},
    }
    assert (
        outcome.metrics["COLLISION_EXACTNESS"]["DISTINCT_TEXT_DIGEST_COLLISION_GROUPS"]
        == 0
    )
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o700
        for path in output.rglob("*")
        if path.is_dir()
    )
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o600
        for path in output.rglob("*")
        if path.is_file()
    )
    validated = validate_stage06_bundle(
        output,
        expected_manifest_sha256=outcome.manifest_sha256,
        stage05_output_directory=stage05_root,
        authoritative_development=False,
        batch_rows=3,
        target_batch_bytes=2 * 1024 * 1024,
        duckdb_memory_limit="512MB",
        duckdb_threads=1,
        hash_chunk_codepoints=3,
    )
    assert validated.logical_dataset_sha256_v1 == outcome.logical_dataset_sha256_v1
    assert validated.metrics == outcome.metrics


def test_no_available_candidates_publishes_empty_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage05_root, stage05_outcome = _stage05_bundle(tmp_path, monkeypatch, [{}])
    _binding, binding_path, binding_sha = _stage06_binding(tmp_path, stage05_outcome)
    output = tmp_path / "stage06" / "candidate"
    outcome = materialize_stage06(
        Stage06RunConfig(
            stage05_output_directory=stage05_root,
            input_binding_file=binding_path,
            expected_input_binding_sha256=binding_sha,
            output_directory=output,
            execution_git_sha=EXECUTION_GIT_SHA,
            production=False,
            authoritative_development=False,
            batch_rows=1,
            registry_batch_rows=1,
            registry_shard_rows=1,
            duckdb_memory_limit="512MB",
        )
    )
    row_map = pq.read_table(output / "row_map" / "data" / "part-000001.parquet")
    registry = pq.read_table(output / "registry" / "data" / "part-000001.parquet")
    assert outcome.row_count == 1
    assert outcome.unique_candidate_count == registry.num_rows == 0
    assert registry.schema.remove_metadata() == registry_schema()
    assert row_map.column(ROW_MAP_ID_COLUMNS[0])[0].as_py() is None
    assert row_map.column(ROW_MAP_ID_COLUMNS[1])[0].as_py() is None
    assert outcome.metrics["CANDIDATE_OCCURRENCES"]["TOTAL_AVAILABLE_OCCURRENCES"] == 0
    assert outcome.metrics["EMPTY_AND_UNAVAILABLE"]["EMPTY_REGISTRY_CANDIDATES"] == 0


def test_batch_thread_registry_shard_and_encounter_order_invariance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage05_root, stage05_outcome = _stage05_bundle(tmp_path, monkeypatch, _rows())
    binding, binding_path, binding_sha = _stage06_binding(tmp_path, stage05_outcome)
    first = materialize_stage06(
        Stage06RunConfig(
            stage05_output_directory=stage05_root,
            input_binding_file=binding_path,
            expected_input_binding_sha256=binding_sha,
            output_directory=tmp_path / "stage06" / "first",
            execution_git_sha=EXECUTION_GIT_SHA,
            production=False,
            authoritative_development=False,
            batch_rows=1,
            registry_batch_rows=1,
            registry_shard_rows=2,
            duckdb_memory_limit="512MB",
            duckdb_threads=1,
        )
    )
    second_binding_path = tmp_path / "bindings" / "stage06-second.json"
    second_binding_sha = write_stage06_input_binding(second_binding_path, binding)
    second = materialize_stage06(
        Stage06RunConfig(
            stage05_output_directory=stage05_root,
            input_binding_file=second_binding_path,
            expected_input_binding_sha256=second_binding_sha,
            output_directory=tmp_path / "stage06" / "second",
            execution_git_sha=EXECUTION_GIT_SHA,
            production=False,
            authoritative_development=False,
            batch_rows=7,
            registry_batch_rows=9,
            registry_shard_rows=20,
            duckdb_memory_limit="512MB",
            duckdb_threads=4,
        )
    )
    assert first.logical_dataset_sha256_v1 == second.logical_dataset_sha256_v1
    assert first.row_map_logical_sha256_v1 == second.row_map_logical_sha256_v1
    assert first.registry_logical_sha256_v1 == second.registry_logical_sha256_v1
    assert first.schema_fingerprint == second.schema_fingerprint
    assert first.metrics == second.metrics


def test_forced_digest_collision_fails_closed_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage05_root, stage05_outcome = _stage05_bundle(tmp_path, monkeypatch, _rows())
    _binding, binding_path, binding_sha = _stage06_binding(tmp_path, stage05_outcome)
    output = tmp_path / "stage06" / "collision"
    with pytest.raises(Stage06ValidationError, match="CANDIDATE_ID_COLLISION"):
        materialize_stage06(
            Stage06RunConfig(
                stage05_output_directory=stage05_root,
                input_binding_file=binding_path,
                expected_input_binding_sha256=binding_sha,
                output_directory=output,
                execution_git_sha=EXECUTION_GIT_SHA,
                production=False,
                authoritative_development=False,
                duckdb_memory_limit="512MB",
            ),
            digest_factory=_constant_digest,
        )
    assert not output.exists()
    assert list(output.parent.glob(".*.in_progress"))


def test_four_giant_duplicate_occurrences_are_exact_and_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    giant = "東京-é-شارع-" * 100_000
    rows = [
        {
            "stage03_clean_street_address_line_1": giant,
            "stage03_clean_street_address_line_1_native": giant,
        },
        {
            "stage03_clean_street_address_line_1": giant,
            "stage03_clean_street_address_line_1_native": giant,
        },
    ]
    stage05_root, stage05_outcome = _stage05_bundle(tmp_path, monkeypatch, rows)
    _binding, binding_path, binding_sha = _stage06_binding(tmp_path, stage05_outcome)
    outcome = materialize_stage06(
        Stage06RunConfig(
            stage05_output_directory=stage05_root,
            input_binding_file=binding_path,
            expected_input_binding_sha256=binding_sha,
            output_directory=tmp_path / "stage06" / "giant",
            execution_git_sha=EXECUTION_GIT_SHA,
            production=False,
            authoritative_development=False,
            batch_rows=2,
            target_batch_bytes=1024,
            hash_chunk_codepoints=4096,
            duckdb_memory_limit="512MB",
        )
    )
    assert outcome.unique_candidate_count == 1
    assert outcome.metrics["EXACT_DEDUPLICATION"]["DUPLICATE_OCCURRENCES"] == 3
    registry = pq.read_table(
        sorted((outcome.output_directory / "registry" / "data").glob("*.parquet"))
    )
    assert registry.column(REGISTRY_COLUMNS[1])[0].as_py() == giant
    assert registry.column(REGISTRY_COLUMNS[2])[0].as_py() == 4


def test_wrong_bindings_prohibited_path_partial_and_permissions_fail_closed(
    tmp_path: Path,
) -> None:
    base = Stage06InputBinding(
        upstream_contract_version=STAGE05_CONTRACT_VERSION,
        upstream_profile_version=STAGE05_PROFILE_VERSION,
        upstream_logical_fingerprint="1" * 64,
        upstream_schema_fingerprint="2" * 64,
        upstream_input_binding_sha256="3" * 64,
        upstream_manifest_sha256="4" * 64,
        upstream_ordered_identity_sha256="5" * 64,
        input_benchmark_fingerprint="6" * 64,
        fixed_500_fingerprint="7" * 64,
        expected_row_count=8,
    )
    with pytest.raises(Stage06ValidationError, match="HOLDOUT_ACCESS_PROHIBITED"):
        write_stage06_input_binding(tmp_path / "holdout" / "binding.json", base)
    with pytest.raises(
        Stage06ValidationError, match="AUTHORITATIVE_DEVELOPMENT_BINDING_MISMATCH"
    ):
        validate_stage06_input_binding(base, authoritative_development=True)
    path = tmp_path / "binding.json"
    binding_sha = write_stage06_input_binding(path, base)
    path.chmod(0o644)
    with pytest.raises(Stage06ValidationError, match="PERMISSION_FAILURE"):
        stage06.load_stage06_input_binding(path, expected_sha256=binding_sha)
    partial = tmp_path / "stage06" / "partial"
    partial.mkdir(parents=True, mode=0o700)
    partial.chmod(0o700)
    with pytest.raises(Stage06ValidationError, match="STAGE06_TERMINAL_MISSING"):
        validate_stage06_bundle(
            partial,
            expected_manifest_sha256="0" * 64,
            stage05_output_directory=tmp_path / "stage05",
            authoritative_development=False,
        )


def test_versions_and_non_goals_are_explicit() -> None:
    assert STAGE06_CONTRACT_VERSION == "stage06_early_exact_deduplication_contract_v1"
    assert STAGE06_PROFILE_VERSION == "stage06_early_exact_deduplication_profile_v1"
    source = Path(stage06.__file__).read_text(encoding="utf-8").casefold()
    assert "libpostal" not in source
    assert "geocode" not in source
    assert "rapidfuzz" not in source
