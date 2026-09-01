from __future__ import annotations

import ast
import json
import stat
from dataclasses import replace
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from safe_geocoding_pipeline.preprocessing.stages import s08_address_evidence as stage08
from safe_geocoding_pipeline.preprocessing.stages.s06_exact_deduplication import (
    row_map_schema,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_country_eligibility import (
    COUNTRY_CONFLICTING,
    COUNTRY_INVALID,
    COUNTRY_MISSING,
    COUNTRY_PARTIAL,
    COUNTRY_UNANIMOUS_VALID,
    PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY,
    PARSER_ELIGIBILITY_INVALID_COUNTRY,
    PARSER_ELIGIBILITY_MISSING_COUNTRY,
    PARSER_ELIGIBILITY_PARTIAL_COUNTRY,
    PARSER_ELIGIBLE_COUNTRY,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_libpostal_adapter import (
    PARSED_EMPTY,
    PARSED_NONEMPTY,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_parser_evidence import (
    NO_STRUCTURAL_WARNINGS_DETECTED,
    PARSER_EXECUTION_ORIGIN,
    STRUCTURAL_WARNINGS_NOT_EVALUATED,
    STRUCTURAL_WARNINGS_PRESENT,
    stage07_evidence_schema,
)
from safe_geocoding_pipeline.preprocessing.stages.s08_address_evidence import (
    ABSENT,
    BOTH,
    COMPONENT_INDEX_EMPTY,
    COMPONENT_INDEX_EMITTED_WITH_UNMAPPED_LABEL,
    LIBPOSTAL_LABEL_MAPPING,
    MAPPED_DEFINED_LABEL,
    PARSER_EVIDENCE,
    PRESENT,
    STAGE08_CONTRACT_VERSION,
    STAGE08_LABEL_MAPPING_VERSION,
    STAGE08_PROFILE_VERSION,
    STAGE08_SCHEMA_BUNDLE_VERSION,
    Stage08Config,
    Stage08InputBinding,
    Stage08ValidationError,
    UNMAPPED_LABEL,
    candidate_evidence_schema,
    materialize_stage08,
    parser_component_evidence_schema,
    representation_occurrence_schema,
    source_candidate_map_schema,
    stage08_contract_fingerprint,
    stage08_label_mapping_fingerprint,
    stage08_schema_bundle_fingerprint,
    stage08_schema_fingerprints,
    validate_stage08_bundle,
)


def _private(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


def _write_private_table(path: Path, table: pa.Table) -> Path:
    _private(path.parent)
    pq.write_table(table, path, write_page_checksum=True)
    path.chmod(0o600)
    return path


def _candidate_row(
    *,
    candidate_id: bytes,
    text: str,
    counts: tuple[int, int, int],
    country_status: str,
    trusted_country: str | None,
    country_counts: tuple[int, int, int, int],
    applicability: str,
    components: list[dict[str, str]],
    parsed_empty: bool = False,
) -> dict[str, Any]:
    evaluated = applicability == PARSER_ELIGIBLE_COUNTRY
    if not evaluated:
        warning_status = STRUCTURAL_WARNINGS_NOT_EVALUATED
        reasons: list[str] = []
        signals: tuple[bool | int | None, ...] = (None,) * 8
    elif parsed_empty:
        warning_status = STRUCTURAL_WARNINGS_PRESENT
        reasons = ["PARSED_EMPTY_NO_COMPONENTS"]
        signals = (None,) * 8
    else:
        warning_status = NO_STRUCTURAL_WARNINGS_DETECTED
        reasons = []
        signals = (True, True, 0, 0, 1, 0, len(text), len(text))
    return {
        "stage06_exact_candidate_id": candidate_id,
        "stage06_candidate_lower": text,
        "stage06_occurrence_count": counts[0],
        "stage06_standard_occurrence_count": counts[1],
        "stage06_native_occurrence_count": counts[2],
        "stage07_country_provenance_status": country_status,
        "stage07_trusted_country_iso_code": trusted_country,
        "stage07_valid_country_occurrence_count": country_counts[0],
        "stage07_missing_country_occurrence_count": country_counts[1],
        "stage07_invalid_country_occurrence_count": country_counts[2],
        "stage07_distinct_valid_country_count": country_counts[3],
        "stage07_parser_applicability_status": applicability,
        "stage07_parse_status": PARSED_EMPTY if parsed_empty else PARSED_NONEMPTY,
        "stage07_parser_execution_origin": PARSER_EXECUTION_ORIGIN,
        "stage07_libpostal_components": components,
        "stage07_structural_warning_status": warning_status,
        "stage07_structural_warning_reason_codes": reasons,
        "stage07_raw_ordered_substrings": signals[0],
        "stage07_lexical_numeric_stream_equal": signals[1],
        "stage07_internal_boundary_count": signals[2],
        "stage07_internal_single_codepoint_fragment_count": signals[3],
        "stage07_maximum_components_per_lexical_run": signals[4],
        "stage07_adjacent_repeated_label_internal_boundary_count": signals[5],
        "stage07_candidate_lexical_numeric_codepoints": signals[6],
        "stage07_output_lexical_numeric_codepoints": signals[7],
    }


def _default_row_map_value(field: pa.Field, row_index: int) -> object:
    if field.name == "id":
        return "repeated-provider-id"
    if pa.types.is_string(field.type):
        return f"synthetic-{field.name}-{row_index}"
    if pa.types.is_boolean(field.type):
        return False
    if pa.types.is_unsigned_integer(field.type):
        return row_index
    if pa.types.is_fixed_size_binary(field.type):
        return (10_000 + row_index).to_bytes(field.type.byte_width, "big")
    if pa.types.is_list(field.type) or pa.types.is_large_list(field.type):
        return []
    raise AssertionError(f"unsupported synthetic field: {field}")


def _fixture(
    tmp_path: Path, *, giant_components: int = 0
) -> tuple[Stage08Config, stage08._ValidatedInputs]:
    input_root = _private(tmp_path / "inputs")
    candidate_ids = tuple(index.to_bytes(32, "big") for index in range(1, 7))
    known_components = [
        {"label": label, "value": f"known-{index}-東京"}
        for index, label in enumerate(LIBPOSTAL_LABEL_MAPPING)
    ]
    first_components = [
        *known_components,
        {"label": "future_ß_label", "value": "unknown\nvalue"},
        {"label": "Road", "value": "case-sensitive-near-miss"},
        {"label": "", "value": ""},
        {"label": "road", "value": "duplicate"},
        {"label": "road", "value": "duplicate"},
        {"label": "road", "value": "different"},
    ]
    first_components.extend(
        {"label": "road" if index % 2 else "house_number", "value": f"giant-{index}"}
        for index in range(giant_components)
    )
    rows = [
        _candidate_row(
            candidate_id=candidate_ids[0],
            text="12 é 東京 شارع",
            counts=(2, 1, 1),
            country_status=COUNTRY_UNANIMOUS_VALID,
            trusted_country="de",
            country_counts=(2, 0, 0, 1),
            applicability=PARSER_ELIGIBLE_COUNTRY,
            components=first_components,
        ),
        _candidate_row(
            candidate_id=candidate_ids[1],
            text="---",
            counts=(2, 1, 1),
            country_status=COUNTRY_UNANIMOUS_VALID,
            trusted_country="de",
            country_counts=(2, 0, 0, 1),
            applicability=PARSER_ELIGIBLE_COUNTRY,
            components=[],
            parsed_empty=True,
        ),
        _candidate_row(
            candidate_id=candidate_ids[2],
            text="missing country",
            counts=(1, 1, 0),
            country_status=COUNTRY_MISSING,
            trusted_country=None,
            country_counts=(0, 1, 0, 0),
            applicability=PARSER_ELIGIBILITY_MISSING_COUNTRY,
            components=[],
            parsed_empty=True,
        ),
        _candidate_row(
            candidate_id=candidate_ids[3],
            text="partial country",
            counts=(2, 1, 1),
            country_status=COUNTRY_PARTIAL,
            trusted_country=None,
            country_counts=(1, 1, 0, 1),
            applicability=PARSER_ELIGIBILITY_PARTIAL_COUNTRY,
            components=[{"label": "state", "value": "evidence"}],
        ),
        _candidate_row(
            candidate_id=candidate_ids[4],
            text="invalid country",
            counts=(1, 1, 0),
            country_status=COUNTRY_INVALID,
            trusted_country=None,
            country_counts=(0, 0, 1, 0),
            applicability=PARSER_ELIGIBILITY_INVALID_COUNTRY,
            components=[{"label": "country", "value": "parser only"}],
        ),
        _candidate_row(
            candidate_id=candidate_ids[5],
            text="conflicting country",
            counts=(2, 1, 1),
            country_status=COUNTRY_CONFLICTING,
            trusted_country=None,
            country_counts=(2, 0, 0, 2),
            applicability=PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY,
            components=[{"label": "postcode", "value": "00000"}],
        ),
    ]
    stage07_table = pa.Table.from_pylist(rows, schema=stage07_evidence_schema())
    stage07_path = _write_private_table(input_root / "stage07.parquet", stage07_table)

    slots: tuple[tuple[bytes | None, bytes | None], ...] = (
        (candidate_ids[0], None),
        (None, candidate_ids[0]),
        (candidate_ids[1], candidate_ids[1]),
        (candidate_ids[2], None),
        (None, candidate_ids[3]),
        (candidate_ids[3], None),
        (candidate_ids[4], None),
        (candidate_ids[5], candidate_ids[5]),
    )
    source_rows: list[dict[str, object]] = []
    schema = row_map_schema()
    for row_index, (standard_id, native_id) in enumerate(slots):
        row = {field.name: _default_row_map_value(field, row_index) for field in schema}
        row["source_logical_record_number"] = row_index + 1
        row["stable_source_row_id_v1"] = (1_000 + row_index).to_bytes(32, "big")
        row["source_file_sha256"] = (2_000 + row_index).to_bytes(32, "big")
        row["stage06_standard_exact_candidate_id"] = standard_id
        row["stage06_native_exact_candidate_id"] = native_id
        source_rows.append(row)
    stage06_table = pa.Table.from_pylist(source_rows, schema=schema)
    stage06_path = _write_private_table(
        input_root / "stage06_row_map.parquet", stage06_table
    )

    component_count = sum(len(row["stage07_libpostal_components"]) for row in rows)
    maximum_components = max(len(row["stage07_libpostal_components"]) for row in rows)
    maximum_candidate = max(len(str(row["stage06_candidate_lower"])) for row in rows)
    binding = Stage08InputBinding(
        stage07_contract="stage07_parser_evidence_contract_v2",
        stage07_profile="stage07_parser_evidence_profile_v2",
        stage07_schema="stage07_parser_evidence_schema_v2",
        stage07_contract_fingerprint="1" * 64,
        stage07_schema_fingerprint="2" * 64,
        stage07_logical_dataset_sha256="3" * 64,
        stage07_manifest_sha256="4" * 64,
        parser_bundle_fingerprint="5" * 64,
        stage06_contract="stage06_early_exact_deduplication_contract_v1",
        stage06_profile="stage06_early_exact_deduplication_profile_v1",
        stage06_schema_fingerprint="6" * 64,
        stage06_logical_dataset_sha256="7" * 64,
        stage06_row_map_logical_sha256="8" * 64,
        stage06_input_binding_sha256="9" * 64,
        stage06_manifest_sha256="a" * 64,
        candidate_rows=6,
        parsed_nonempty_rows=4,
        parsed_empty_rows=2,
        raw_component_rows=component_count,
        maximum_component_count=maximum_components,
        maximum_candidate_codepoints=maximum_candidate,
        source_rows=8,
        occurrence_rows=10,
        standard_occurrences=6,
        native_occurrences=4,
    )
    config = Stage08Config(
        stage07_output_directory=input_root / "stage07_root",
        stage06_output_directory=input_root / "stage06_root",
        output_directory=tmp_path / "stage08_output",
        execution_git_sha="b" * 40,
        binding=binding,
        authoritative_development=False,
        controlled_execution=False,
        input_batch_rows=2,
        candidate_output_batch_rows=2,
        component_batch_rows=7,
        target_batch_bytes=4_096,
        candidate_shard_rows=2,
        component_shard_rows=11,
        source_shard_rows=3,
        duckdb_memory_limit="512MB",
        duckdb_threads=1,
    )
    return config, stage08._ValidatedInputs(
        stage07_paths=(stage07_path,), stage06_row_map_paths=(stage06_path,)
    )


@pytest.fixture(autouse=True)
def _allow_developer_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stage08, "_validate_runtime", lambda: None)


def test_frozen_schemas_mapping_and_semantic_taxonomy_are_exact() -> None:
    binding = stage08.accepted_stage08_input_binding()
    candidate = candidate_evidence_schema(binding)
    upstream = stage07_evidence_schema()
    assert STAGE08_CONTRACT_VERSION == "stage08_address_evidence_projection_contract_v1"
    assert STAGE08_PROFILE_VERSION == "stage08_address_evidence_projection_profile_v1"
    assert (
        STAGE08_SCHEMA_BUNDLE_VERSION == "stage08_address_evidence_projection_schema_v1"
    )
    assert STAGE08_LABEL_MAPPING_VERSION == "stage08_libpostal_label_mapping_v1"
    assert len(LIBPOSTAL_LABEL_MAPPING) == 20
    assert tuple(candidate.names[:25]) == tuple(upstream.names)
    for output_field, upstream_field in zip(list(candidate)[:25], upstream):
        assert output_field.type == upstream_field.type
        assert output_field.nullable == upstream_field.nullable
    for schema in (
        candidate,
        parser_component_evidence_schema(binding),
        source_candidate_map_schema(binding),
        representation_occurrence_schema(binding),
    ):
        assert all(
            field.metadata and b"stage08_semantic_class" in field.metadata
            for field in schema
        )
        assert not any(
            token in " ".join(schema.names).casefold()
            for token in (
                "components_ready",
                "components_abstain",
                "confidence",
                "score",
            )
        )
    assert len(stage08_label_mapping_fingerprint()) == 64
    assert len(stage08_contract_fingerprint(binding)) == 64
    assert len(stage08_schema_bundle_fingerprint(binding)) == 64
    assert set(stage08_schema_fingerprints(binding)) == {
        "candidate_evidence",
        "parser_component_evidence",
        "source_candidate_map",
        "representation_occurrence_v1",
    }


def test_lossless_projection_reversibility_unknown_duplicates_and_mapback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, validated = _fixture(tmp_path)
    monkeypatch.setattr(stage08, "_validated_inputs", lambda _: validated)
    outcome = materialize_stage08(config)
    assert outcome.candidate_rows == 6
    assert outcome.source_rows == 8
    assert outcome.occurrence_rows == 10
    candidates = pq.read_table(
        sorted(
            (config.output_directory / "candidate_evidence" / "data").glob("*.parquet")
        )
    )
    components = pq.read_table(
        sorted(
            (config.output_directory / "parser_component_evidence" / "data").glob(
                "*.parquet"
            )
        )
    )
    source_map = pq.read_table(
        sorted(
            (config.output_directory / "source_candidate_map" / "data").glob(
                "*.parquet"
            )
        )
    )
    assert candidates.column("stage08_representation_scope")[0].as_py() == BOTH
    assert candidates.column("stage08_component_index_status")[0].as_py() == (
        COMPONENT_INDEX_EMITTED_WITH_UNMAPPED_LABEL
    )
    assert candidates.column("stage08_component_index_status")[1].as_py() == (
        COMPONENT_INDEX_EMPTY
    )
    first_id = candidates.column("stage06_exact_candidate_id")[0].as_py()
    first_long = components.filter(
        pa.compute.equal(components.column("stage06_exact_candidate_id"), first_id)
    )
    raw_labels = first_long.column("stage08_raw_libpostal_label").to_pylist()
    raw_values = first_long.column("stage08_raw_libpostal_value").to_pylist()
    assert raw_labels[:20] == list(LIBPOSTAL_LABEL_MAPPING)
    assert raw_labels[-3:] == ["road", "road", "road"]
    assert raw_values[-3:] == ["duplicate", "duplicate", "different"]
    unknown_index = raw_labels.index("future_ß_label")
    assert first_long.column("stage08_label_mapping_status")[unknown_index].as_py() == (
        UNMAPPED_LABEL
    )
    assert (
        first_long.column("stage08_safe_parser_evidence_component")[
            unknown_index
        ].as_py()
        is None
    )
    mapped_index = raw_labels.index("road")
    assert first_long.column("stage08_label_mapping_status")[mapped_index].as_py() == (
        MAPPED_DEFINED_LABEL
    )
    assert first_long.column("stage08_evidence_class")[mapped_index].as_py() == (
        PARSER_EVIDENCE
    )
    nested = candidates.column("stage07_libpostal_components")[0].as_py()
    assert [(item["label"], item["value"]) for item in nested] == list(
        zip(raw_labels, raw_values)
    )
    assert source_map.column("stage08_source_row_ordinal").to_pylist() == list(range(8))
    assert source_map.column("id").to_pylist() == ["repeated-provider-id"] * 8
    assert source_map.column("country_iso_code")[0].as_py() == (
        "synthetic-country_iso_code-0"
    )
    assert source_map.column("stage03_clean_country_iso_code")[0].as_py() == (
        "synthetic-stage03_clean_country_iso_code-0"
    )
    assert source_map.column("stage04_lower_country_iso_code")[0].as_py() == (
        "synthetic-stage04_lower_country_iso_code-0"
    )
    assert (
        len(
            {
                source_map.column("country_iso_code")[0].as_py(),
                source_map.column("stage03_clean_country_iso_code")[0].as_py(),
                source_map.column("stage04_lower_country_iso_code")[0].as_py(),
            }
        )
        == 3
    )
    assert (
        source_map.column("stage08_standard_representation_status").to_pylist()[1]
        == ABSENT
    )
    assert (
        source_map.column("stage08_native_representation_status").to_pylist()[1]
        == PRESENT
    )
    assert not (config.output_directory / "representation_occurrence_v1").exists()
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o700
        for path in config.output_directory.rglob("*")
        if path.is_dir()
    )
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o600
        for path in config.output_directory.rglob("*")
        if path.is_file()
    )
    manifest = json.loads(
        (config.output_directory / "stage08_address_evidence_manifest.json").read_text()
    )
    assert manifest["development_metrics"]["PARSER_CALLS"] == 0
    assert manifest["development_metrics"]["SEMANTIC_TRUST_FIELDS"] == 0
    assert (
        manifest["scientific_identity"]["representation_occurrence_view"][
            "materialized"
        ]
        is False
    )


def test_batch_and_shard_layout_invariance_with_giant_component_sequence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, validated = _fixture(tmp_path / "first", giant_components=10_000)
    monkeypatch.setattr(stage08, "_validated_inputs", lambda _: validated)
    first_outcome = materialize_stage08(first)
    second = replace(
        first,
        output_directory=tmp_path / "second_output",
        input_batch_rows=5,
        candidate_output_batch_rows=6,
        component_batch_rows=257,
        target_batch_bytes=64 * 1024,
        candidate_shard_rows=10,
        component_shard_rows=20_000,
        source_shard_rows=20,
        duckdb_threads=2,
    )
    second_outcome = materialize_stage08(second)
    assert first_outcome.logical_dataset_sha256 == second_outcome.logical_dataset_sha256
    assert first_outcome.contract_fingerprint == second_outcome.contract_fingerprint
    assert (
        first_outcome.schema_bundle_fingerprint
        == second_outcome.schema_bundle_fingerprint
    )
    long_table = pq.read_table(
        sorted(
            (first.output_directory / "parser_component_evidence" / "data").glob(
                "*.parquet"
            )
        )
    )
    first_id = (1).to_bytes(32, "big")
    first_rows = long_table.filter(
        pa.compute.equal(long_table.column("stage06_exact_candidate_id"), first_id)
    )
    assert first_rows.column("stage08_component_ordinal").to_pylist() == list(
        range(first_rows.num_rows)
    )


def test_tamper_permission_topology_and_scope_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, validated = _fixture(tmp_path / "tamper")
    monkeypatch.setattr(stage08, "_validated_inputs", lambda _: validated)
    outcome = materialize_stage08(config)
    artifact = next(
        (config.output_directory / "parser_component_evidence" / "data").glob(
            "*.parquet"
        )
    )
    with artifact.open("ab") as stream:
        stream.write(b"tamper")
    with pytest.raises(Stage08ValidationError, match="ARTIFACT_MISMATCH"):
        validate_stage08_bundle(
            config.output_directory,
            expected_manifest_sha256=outcome.manifest_sha256,
            config=config,
        )

    permission_config, permission_validated = _fixture(tmp_path / "permission")
    monkeypatch.setattr(stage08, "_validated_inputs", lambda _: permission_validated)
    permission_outcome = materialize_stage08(permission_config)
    metadata = (
        permission_config.output_directory
        / "metadata"
        / "stage08_schema_contract_v1.json"
    )
    metadata.chmod(0o644)
    with pytest.raises(Stage08ValidationError, match="PERMISSION_FAILURE"):
        validate_stage08_bundle(
            permission_config.output_directory,
            expected_manifest_sha256=permission_outcome.manifest_sha256,
            config=permission_config,
        )
    metadata.chmod(0o600)
    unexpected = permission_config.output_directory / "unexpected.txt"
    unexpected.write_text("synthetic\n", encoding="ascii")
    unexpected.chmod(0o600)
    with pytest.raises(Stage08ValidationError, match="TOPOLOGY_FAILURE"):
        validate_stage08_bundle(
            permission_config.output_directory,
            expected_manifest_sha256=permission_outcome.manifest_sha256,
            config=permission_config,
        )

    base, _ = _fixture(tmp_path / "scope")
    with pytest.raises(Stage08ValidationError, match="HOLDOUT_ACCESS_PROHIBITED"):
        replace(base, output_directory=tmp_path / "HOLDOUT" / "result").validate()
    with pytest.raises(Stage08ValidationError, match="PRODUCTION_ACCESS_PROHIBITED"):
        replace(
            base, stage07_output_directory=tmp_path / "production" / "stage07"
        ).validate()


def test_semantic_trust_vocabulary_is_rejected() -> None:
    forbidden = candidate_evidence_schema().append(
        pa.field(
            "stage08_confidence_score",
            pa.uint64(),
            nullable=False,
            metadata={b"stage08_semantic_class": b"MECHANICAL_INDEX"},
        )
    )
    with pytest.raises(Stage08ValidationError, match="SEMANTIC_TRUST_VOCABULARY"):
        stage08._assert_semantic_boundary(forbidden)


def test_stage08_has_no_external_or_later_stage_dependency() -> None:
    tree = ast.parse(Path(stage08.__file__).read_text(encoding="utf-8"))
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )
    assert imports.isdisjoint(
        {
            "pandas",
            "polars",
            "requests",
            "httpx",
            "urllib",
            "postal",
            "pycountry",
            "libaddressinput",
            "deepparse",
            "senzing",
        }
    )


def test_output_collision_fails_without_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, validated = _fixture(tmp_path)
    monkeypatch.setattr(stage08, "_validated_inputs", lambda _: validated)
    config.output_directory.mkdir(mode=0o700)
    with pytest.raises(Stage08ValidationError, match="OUTPUT_COLLISION"):
        materialize_stage08(config)
