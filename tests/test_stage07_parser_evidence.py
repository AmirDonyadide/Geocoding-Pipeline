from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from safe_geocoding_pipeline.preprocessing.stages import s07_parser_evidence
from safe_geocoding_pipeline.preprocessing.stages.s06_exact_deduplication import (
    REGISTRY_COLUMNS,
    registry_schema,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_country_eligibility import (
    COUNTRY_MISSING,
    COUNTRY_UNANIMOUS_VALID,
    PARSER_ELIGIBILITY_MISSING_COUNTRY,
    PARSER_ELIGIBLE_COUNTRY,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_libpostal_adapter import (
    PARSED_EMPTY,
    PARSED_NONEMPTY,
    LibpostalComponent,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_output_schema import (
    one_component_list_array,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_parser_evidence import (
    NO_STRUCTURAL_WARNINGS_DETECTED,
    STAGE07_EVIDENCE_CONTRACT_VERSION,
    STAGE07_EVIDENCE_PROFILE_VERSION,
    STRUCTURAL_WARNINGS_NOT_EVALUATED,
    STRUCTURAL_WARNINGS_PRESENT,
    Stage07EvidenceConfig,
    Stage07ValidationError,
    accepted_stage07_evidence_binding,
    materialize_stage07_evidence,
    stage07_evidence_contract_fingerprint,
    stage07_evidence_schema,
    validate_stage07_evidence_bundle,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_parsing import stage07_schema


def _private(path: Path) -> Path:
    path.mkdir(parents=True, mode=0o700)
    path.chmod(0o700)
    return path


def _write_private_table(path: Path, table: pa.Table) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    pq.write_table(table, path, write_page_checksum=True)
    path.chmod(0o600)
    return path


def _fixture(
    tmp_path: Path,
) -> tuple[Stage07EvidenceConfig, s07_parser_evidence._ValidatedInputs]:
    inputs = _private(tmp_path / "inputs")
    stage06 = _private(inputs / "stage06")
    ids = tuple(index.to_bytes(32, "big") for index in range(1, 4))
    candidates = ("12 main road", "---", "abc")
    counts = ((1, 1, 0), (1, 1, 0), (1, 0, 1))
    registry = pa.Table.from_arrays(
        (
            pa.array(ids, type=pa.binary(32)),
            pa.array(candidates, type=pa.string()),
            *(
                pa.array((row[index] for row in counts), type=pa.uint64())
                for index in range(3)
            ),
        ),
        schema=registry_schema(),
    )
    stage06_registry = _write_private_table(stage06 / "registry.parquet", registry)
    row_map = _write_private_table(
        stage06 / "row_map" / "data" / "part-000001.parquet",
        pa.table(
            {
                "stage06_standard_exact_candidate_id": pa.array(
                    (ids[0], ids[1], None), type=pa.binary(32)
                ),
                "stage06_native_exact_candidate_id": pa.array(
                    (None, None, ids[2]), type=pa.binary(32)
                ),
            }
        ),
    )
    (stage06 / "row_map").chmod(0o700)
    stage06_manifest = stage06 / "stage06_manifest.json"
    stage06_manifest.write_text(
        json.dumps(
            {
                "physical_identity": {
                    "row_map_artifacts": [
                        {"relative_path": row_map.relative_to(stage06).as_posix()}
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    stage06_manifest.chmod(0o600)

    v1_components = (
        (
            LibpostalComponent("house_number", "12"),
            LibpostalComponent("road", "main road"),
            LibpostalComponent("road", "main road"),
        ),
        (),
        (LibpostalComponent("road", "a"), LibpostalComponent("road", "bc")),
    )
    v1_schema = stage07_schema()
    component_arrays = [
        one_component_list_array((components,)[0]) for components in v1_components
    ]
    component_array = pa.concat_arrays(component_arrays)
    v1 = pa.Table.from_arrays(
        (
            *(registry.column(index).combine_chunks() for index in range(5)),
            pa.array(
                (PARSED_NONEMPTY, PARSED_EMPTY, PARSED_NONEMPTY), type=pa.string()
            ),
            component_array,
        ),
        schema=v1_schema,
    )
    v1_path = _write_private_table(inputs / "stage07_v1.parquet", v1)
    eligibility = _write_private_table(
        inputs / "eligibility.parquet",
        pa.table(
            {
                "candidate_id": pa.array(ids, type=pa.binary(32)),
                "occurrence_count": pa.array((1, 1, 1), type=pa.uint64()),
                "standard_occurrence_count": pa.array((1, 1, 0), type=pa.uint64()),
                "native_occurrence_count": pa.array((0, 0, 1), type=pa.uint64()),
                "valid_country_occurrence_count": pa.array((1, 1, 0), type=pa.uint64()),
                "missing_country_occurrence_count": pa.array(
                    (0, 0, 1), type=pa.uint64()
                ),
                "invalid_country_occurrence_count": pa.array(
                    (0, 0, 0), type=pa.uint64()
                ),
                "distinct_valid_country_count": pa.array((1, 1, 0), type=pa.uint32()),
                "country_provenance_status": pa.array(
                    (COUNTRY_UNANIMOUS_VALID, COUNTRY_UNANIMOUS_VALID, COUNTRY_MISSING)
                ),
                "unanimous_country_code": pa.array(
                    ("de", "de", None), type=pa.string()
                ),
                "libpostal_eligibility": pa.array(
                    (
                        PARSER_ELIGIBLE_COUNTRY,
                        PARSER_ELIGIBLE_COUNTRY,
                        PARSER_ELIGIBILITY_MISSING_COUNTRY,
                    )
                ),
                "stage07_parse_status": pa.array(
                    (PARSED_NONEMPTY, PARSED_EMPTY, PARSED_NONEMPTY)
                ),
            }
        ),
    )
    binding = replace(
        accepted_stage07_evidence_binding(),
        stage06_manifest_sha256="0" * 64,
        stage07_v1_manifest_sha256="1" * 64,
        eligibility_artifact_sha256="2" * 64,
        eligibility_audit_manifest_sha256="3" * 64,
        eligibility_policy_manifest_sha256="4" * 64,
        parser_bundle_fingerprint="5" * 64,
        stage06_candidate_rows=3,
        stage06_occurrences=3,
        stage06_standard_occurrences=2,
        stage06_native_occurrences=1,
        eligible_candidates=2,
        unresolved_candidates=1,
    )
    config = Stage07EvidenceConfig(
        stage06_output_directory=stage06,
        stage07_v1_output_directory=_private(inputs / "v1_root"),
        eligibility_artifact=eligibility,
        eligibility_audit_manifest=inputs / "unused_manifest.json",
        output_directory=tmp_path / "output",
        execution_git_sha="a" * 40,
        binding=binding,
        authoritative_development=False,
        production=False,
        input_batch_rows=1,
        output_batch_rows=1,
        target_batch_bytes=128,
        output_shard_rows=2,
    )
    validated = s07_parser_evidence._ValidatedInputs(
        stage06_registry_paths=(stage06_registry,),
        stage06_row_map_paths=(row_map,),
        stage07_v1_paths=(v1_path,),
        eligibility_path=eligibility,
        stage07_v1_identity={
            "contract": "stage07_libpostal_parsing_contract_v1",
            "profile": "stage07_libpostal_parsing_profile_v1",
            "schema_fingerprint": "6" * 64,
            "logical_dataset_sha256_v1": "7" * 64,
            "manifest_sha256": "1" * 64,
            "parser_bundle_fingerprint": "5" * 64,
        },
    )
    return config, validated


@pytest.fixture(autouse=True)
def _allow_developer_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    # Production uses the pinned Goethe Python/Arrow/DuckDB runtime. These
    # bounded synthetic tests isolate evidence-projection semantics from the
    # developer Mac's patch-level Python version.
    monkeypatch.setattr(s07_parser_evidence, "_validate_runtime", lambda: None)


def test_evidence_contract_has_no_readiness_or_semantic_trust_gate() -> None:
    schema = stage07_evidence_schema()
    assert STAGE07_EVIDENCE_CONTRACT_VERSION == "stage07_parser_evidence_contract_v2"
    assert STAGE07_EVIDENCE_PROFILE_VERSION == "stage07_parser_evidence_profile_v2"
    assert "component_readiness" not in " ".join(schema.names)
    assert "COMPONENTS_READY" not in str(schema)
    assert schema.names[:5] == list(REGISTRY_COLUMNS)
    assert schema.field("stage07_libpostal_components").nullable is False
    assert pa.types.is_large_list(schema.field("stage07_libpostal_components").type)
    assert pa.types.is_large_list(
        schema.field("stage07_structural_warning_reason_codes").type
    )
    assert (
        len(stage07_evidence_contract_fingerprint(accepted_stage07_evidence_binding()))
        == 64
    )


def test_projection_preserves_v1_raw_output_and_emits_warnings_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, validated = _fixture(tmp_path)
    monkeypatch.setattr(s07_parser_evidence, "_validated_inputs", lambda _: validated)
    outcome = materialize_stage07_evidence(config)
    assert outcome.candidate_count == 3
    table = pq.read_table(
        sorted((config.output_directory / "registry" / "data").glob("*.parquet"))
    )
    assert table.column("stage06_candidate_lower").to_pylist() == [
        "12 main road",
        "---",
        "abc",
    ]
    assert table.column("stage07_parse_status").to_pylist() == [
        PARSED_NONEMPTY,
        PARSED_EMPTY,
        PARSED_NONEMPTY,
    ]
    assert table.column("stage07_libpostal_components")[0].as_py() == [
        {"label": "house_number", "value": "12"},
        {"label": "road", "value": "main road"},
        {"label": "road", "value": "main road"},
    ]
    assert table.column("stage07_structural_warning_status").to_pylist() == [
        STRUCTURAL_WARNINGS_PRESENT,
        STRUCTURAL_WARNINGS_PRESENT,
        STRUCTURAL_WARNINGS_NOT_EVALUATED,
    ]
    assert table.column("stage07_structural_warning_reason_codes")[1].as_py() == [
        "PARSED_EMPTY_NO_COMPONENTS"
    ]
    assert table.column("stage07_structural_warning_reason_codes")[2].as_py() == []
    assert table.column("stage07_internal_boundary_count")[2].as_py() is None
    manifest = json.loads(
        (config.output_directory / "stage07_parser_evidence_manifest.json").read_text()
    )
    assert (
        manifest["scientific_identity"]["component_readiness_status_published"] is False
    )
    assert manifest["development_metrics"]["PARSER_CALLS"] == 0
    assert manifest["development_metrics"]["SEMANTIC_TRUST_CLAIMS"] == 0
    assert manifest["scientific_semantics"]["raw_libpostal_components_are"] == (
        "HYPOTHESES_AND_EVIDENCE_NOT_SOURCE_TRUTH"
    )
    assert outcome.metrics["MAP_BACK"] == {
        "TOTAL_OCCURRENCES": 3,
        "STANDARD_OCCURRENCES": 2,
        "NATIVE_OCCURRENCES": 1,
        "MISSING_STAGE07_ROWS": 0,
        "NON_UNIQUE_STAGE07_ROWS": 0,
    }


def test_logical_identity_is_batch_and_shard_invariant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, validated = _fixture(tmp_path / "first")
    monkeypatch.setattr(s07_parser_evidence, "_validated_inputs", lambda _: validated)
    first_outcome = materialize_stage07_evidence(first)
    second = replace(
        first,
        output_directory=tmp_path / "second_output",
        input_batch_rows=3,
        output_batch_rows=3,
        output_shard_rows=3,
        target_batch_bytes=1024 * 1024,
    )
    second_outcome = materialize_stage07_evidence(second)
    assert (
        first_outcome.logical_dataset_sha256_v2
        == second_outcome.logical_dataset_sha256_v2
    )
    assert first_outcome.contract_fingerprint == second_outcome.contract_fingerprint


def test_validation_rejects_artifact_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, validated = _fixture(tmp_path)
    monkeypatch.setattr(s07_parser_evidence, "_validated_inputs", lambda _: validated)
    outcome = materialize_stage07_evidence(config)
    artifact = next((config.output_directory / "registry" / "data").glob("*.parquet"))
    artifact.chmod(0o600)
    with artifact.open("ab") as stream:
        stream.write(b"mutation")
    with pytest.raises(Stage07ValidationError, match="ARTIFACT_MISMATCH"):
        validate_stage07_evidence_bundle(
            config.output_directory,
            expected_manifest_sha256=outcome.manifest_sha256,
            config=config,
        )


def test_output_collision_and_holdout_paths_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, validated = _fixture(tmp_path)
    monkeypatch.setattr(s07_parser_evidence, "_validated_inputs", lambda _: validated)
    config.output_directory.mkdir()
    with pytest.raises(Stage07ValidationError, match="OUTPUT_COLLISION"):
        materialize_stage07_evidence(config)
    with pytest.raises(Stage07ValidationError, match="HOLDOUT_ACCESS_PROHIBITED"):
        replace(config, output_directory=tmp_path / "holdout" / "output").validate()


def test_no_warning_is_not_named_or_encoded_as_semantic_readiness() -> None:
    status, reasons, signals = s07_parser_evidence._warning_values(
        PARSER_ELIGIBLE_COUNTRY,
        PARSED_NONEMPTY,
        "main road",
        (LibpostalComponent("road", "main road"),),
    )
    assert status == NO_STRUCTURAL_WARNINGS_DETECTED
    assert reasons == ()
    assert signals is not None
    assert "READY" not in status
