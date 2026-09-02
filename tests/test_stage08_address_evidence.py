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


def _retained_attempt(config: Stage08Config) -> Path:
    attempts = tuple(
        config.output_directory.parent.glob(
            f".{config.output_directory.name}.*.in_progress"
        )
    )
    assert len(attempts) == 1
    return attempts[0]


def _assert_reader_rejects_incomplete(root: Path, config: Stage08Config) -> None:
    assert (root / stage08.STAGE08_IN_PROGRESS_NAME).read_bytes() == b"in_progress\n"
    assert not (root / stage08.STAGE08_SUCCESS_NAME).exists()
    with pytest.raises(Stage08ValidationError):
        validate_stage08_bundle(
            root,
            expected_manifest_sha256="0" * 64,
            config=replace(config, output_directory=root),
        )


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


def test_successful_publication_terminal_state_order_is_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, validated = _fixture(tmp_path)
    monkeypatch.setattr(stage08, "_validated_inputs", lambda _: validated)
    observed: list[str] = []
    real_validate = stage08._validate_stage08_bundle_state
    real_publish = stage08._atomic_publish_directory

    def observe_validation(
        output_directory: Path, **kwargs: Any
    ) -> stage08.Stage08Outcome:
        terminal_state = kwargs["terminal_state"]
        if terminal_state == stage08._TERMINAL_STATE_IN_PROGRESS:
            assert (output_directory / stage08.STAGE08_IN_PROGRESS_NAME).is_file()
            assert not (output_directory / stage08.STAGE08_SUCCESS_NAME).exists()
        else:
            assert terminal_state == stage08._TERMINAL_STATE_PUBLISHED
            assert not (output_directory / stage08.STAGE08_IN_PROGRESS_NAME).exists()
            assert (output_directory / stage08.STAGE08_SUCCESS_NAME).is_file()
        outcome = real_validate(output_directory, **kwargs)
        observed.append(terminal_state)
        return outcome

    def observe_publish(source: Path, destination: Path) -> None:
        assert (source / stage08.STAGE08_SUCCESS_NAME).is_file()
        assert not (source / stage08.STAGE08_IN_PROGRESS_NAME).exists()
        assert not destination.exists()
        observed.append("ATOMIC_RENAME")
        real_publish(source, destination)

    monkeypatch.setattr(stage08, "_validate_stage08_bundle_state", observe_validation)
    monkeypatch.setattr(stage08, "_atomic_publish_directory", observe_publish)
    outcome = materialize_stage08(config)

    assert outcome.output_directory == config.output_directory
    assert observed == [
        stage08._TERMINAL_STATE_IN_PROGRESS,
        "ATOMIC_RENAME",
        stage08._TERMINAL_STATE_PUBLISHED,
    ]
    assert (config.output_directory / stage08.STAGE08_SUCCESS_NAME).is_file()
    assert not (config.output_directory / stage08.STAGE08_IN_PROGRESS_NAME).exists()
    _, files = stage08._topology(config.output_directory)
    assert stage08.STAGE08_SUCCESS_NAME in files
    assert stage08.STAGE08_IN_PROGRESS_NAME not in files
    assert not tuple(
        config.output_directory.parent.glob(
            f".{config.output_directory.name}.*.in_progress"
        )
    )


def test_injected_prepublication_reopen_failure_retains_only_incomplete_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, validated = _fixture(tmp_path)
    monkeypatch.setattr(stage08, "_validated_inputs", lambda _: validated)
    real_validate = stage08._validate_stage08_bundle_state

    def inject_failure(output_directory: Path, **kwargs: Any) -> stage08.Stage08Outcome:
        if kwargs["terminal_state"] == stage08._TERMINAL_STATE_IN_PROGRESS:
            assert (output_directory / stage08.STAGE08_IN_PROGRESS_NAME).is_file()
            assert not (output_directory / stage08.STAGE08_SUCCESS_NAME).exists()
            raise Stage08ValidationError(
                "INJECTED_PREPUBLICATION_FAILURE", "synthetic boundary failure"
            )
        return real_validate(output_directory, **kwargs)

    monkeypatch.setattr(stage08, "_validate_stage08_bundle_state", inject_failure)
    with pytest.raises(Stage08ValidationError, match="INJECTED_PREPUBLICATION_FAILURE"):
        materialize_stage08(config)

    attempt = _retained_attempt(config)
    assert (attempt / stage08.STAGE08_IN_PROGRESS_NAME).read_bytes() == (
        b"in_progress\n"
    )
    assert not (attempt / stage08.STAGE08_SUCCESS_NAME).exists()
    assert not config.output_directory.exists()
    with pytest.raises(Stage08ValidationError, match="STAGE08_TERMINAL_STATE_MISMATCH"):
        validate_stage08_bundle(
            attempt,
            expected_manifest_sha256="0" * 64,
            config=replace(config, output_directory=attempt),
        )


def test_injected_failure_immediately_before_success_transition_is_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, validated = _fixture(tmp_path)
    monkeypatch.setattr(stage08, "_validated_inputs", lambda _: validated)
    real_write = stage08._write_json_exclusive

    def reject_success_transition(path: Path, value: object) -> None:
        if path.name == stage08.STAGE08_SUCCESS_NAME:
            assert (path.parent / stage08.STAGE08_IN_PROGRESS_NAME).is_file()
            assert not path.exists()
            raise Stage08ValidationError(
                "INJECTED_SUCCESS_TRANSITION_FAILURE", "synthetic boundary failure"
            )
        real_write(path, value)

    monkeypatch.setattr(stage08, "_write_json_exclusive", reject_success_transition)
    with pytest.raises(
        Stage08ValidationError, match="INJECTED_SUCCESS_TRANSITION_FAILURE"
    ):
        materialize_stage08(config)

    attempt = _retained_attempt(config)
    assert (attempt / stage08.STAGE08_IN_PROGRESS_NAME).is_file()
    assert not (attempt / stage08.STAGE08_SUCCESS_NAME).exists()
    assert not config.output_directory.exists()


def test_rename_raises_before_filesystem_effect_and_attempt_remains_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, validated = _fixture(tmp_path)
    monkeypatch.setattr(stage08, "_validated_inputs", lambda _: validated)

    def raise_before_rename(source: Path, destination: Path) -> None:
        assert source.is_dir()
        assert not destination.exists()
        raise OSError("synthetic pre-effect rename failure")

    monkeypatch.setattr(stage08, "_atomic_publish_directory", raise_before_rename)
    with pytest.raises(Stage08ValidationError, match="STAGE08_PUBLICATION_FAILURE"):
        materialize_stage08(config)

    attempt = _retained_attempt(config)
    assert not config.output_directory.exists()
    _assert_reader_rejects_incomplete(attempt, config)


def test_rename_performs_real_effect_then_raises_and_valid_final_is_adopted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, validated = _fixture(tmp_path)
    monkeypatch.setattr(stage08, "_validated_inputs", lambda _: validated)
    real_publish = stage08._atomic_publish_directory

    def rename_then_raise(source: Path, destination: Path) -> None:
        real_publish(source, destination)
        assert not source.exists()
        assert destination.is_dir()
        raise OSError("synthetic post-effect rename failure")

    monkeypatch.setattr(stage08, "_atomic_publish_directory", rename_then_raise)
    outcome = materialize_stage08(config)

    assert outcome.output_directory == config.output_directory
    assert (config.output_directory / stage08.STAGE08_SUCCESS_NAME).is_file()
    assert not (config.output_directory / stage08.STAGE08_IN_PROGRESS_NAME).exists()
    assert not tuple(
        config.output_directory.parent.glob(
            f".{config.output_directory.name}.*.in_progress"
        )
    )
    reopened = validate_stage08_bundle(
        config.output_directory,
        expected_manifest_sha256=outcome.manifest_sha256,
        config=config,
    )
    assert reopened.logical_dataset_sha256 == outcome.logical_dataset_sha256


def test_exception_immediately_after_rename_adopts_only_after_full_reopen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, validated = _fixture(tmp_path)
    monkeypatch.setattr(stage08, "_validated_inputs", lambda _: validated)
    real_verify = stage08._verify_post_rename_state
    calls = 0

    def interrupt_once(
        temporary: Path, final: Path, expected_identity: tuple[int, int]
    ) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            assert not temporary.exists()
            assert final.is_dir()
            raise KeyboardInterrupt("synthetic immediate post-rename interrupt")
        real_verify(temporary, final, expected_identity)

    monkeypatch.setattr(stage08, "_verify_post_rename_state", interrupt_once)
    outcome = materialize_stage08(config)

    assert calls == 2
    assert outcome.output_directory == config.output_directory
    assert (config.output_directory / stage08.STAGE08_SUCCESS_NAME).is_file()
    assert not (config.output_directory / stage08.STAGE08_IN_PROGRESS_NAME).exists()


def test_post_effect_rename_is_not_adopted_when_final_reopen_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, validated = _fixture(tmp_path)
    monkeypatch.setattr(stage08, "_validated_inputs", lambda _: validated)
    real_publish = stage08._atomic_publish_directory
    real_validate = stage08._validate_stage08_bundle_state

    def rename_then_raise(source: Path, destination: Path) -> None:
        real_publish(source, destination)
        assert not source.exists()
        assert destination.is_dir()
        raise OSError("synthetic post-effect rename failure")

    def reject_published_reopen(
        output_directory: Path, **kwargs: Any
    ) -> stage08.Stage08Outcome:
        if kwargs["terminal_state"] == stage08._TERMINAL_STATE_PUBLISHED:
            raise Stage08ValidationError(
                "INJECTED_POSTPUBLICATION_FAILURE", "synthetic reopen failure"
            )
        return real_validate(output_directory, **kwargs)

    monkeypatch.setattr(stage08, "_atomic_publish_directory", rename_then_raise)
    monkeypatch.setattr(
        stage08, "_validate_stage08_bundle_state", reject_published_reopen
    )
    with pytest.raises(
        Stage08ValidationError, match="INJECTED_POSTPUBLICATION_FAILURE"
    ):
        materialize_stage08(config)

    assert not tuple(
        config.output_directory.parent.glob(
            f".{config.output_directory.name}.*.in_progress"
        )
    )
    _assert_reader_rejects_incomplete(config.output_directory, config)


@pytest.mark.parametrize(
    "boundary",
    (
        "remove_in_progress",
        "terminal_directory_fsync",
        "publication_parent_fsync",
    ),
)
def test_every_failure_after_success_creation_is_demoted_to_incomplete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    config, validated = _fixture(tmp_path)
    monkeypatch.setattr(stage08, "_validated_inputs", lambda _: validated)
    real_remove = stage08._remove_in_progress_marker
    real_fsync = getattr(stage08, "_fsync_directory")

    def remove_in_progress(path: Path) -> None:
        if boundary == "remove_in_progress":
            assert (path.parent / stage08.STAGE08_SUCCESS_NAME).is_file()
            raise OSError("synthetic remove failure")
        real_remove(path)

    def fsync_directory(path: Path) -> None:
        terminal_tree = path.name.endswith(".in_progress")
        if (
            boundary == "terminal_directory_fsync"
            and terminal_tree
            and (path / stage08.STAGE08_SUCCESS_NAME).is_file()
        ):
            assert not (path / stage08.STAGE08_IN_PROGRESS_NAME).exists()
            raise OSError("synthetic terminal fsync failure")
        if (
            boundary == "publication_parent_fsync"
            and path == config.output_directory.parent
            and config.output_directory.is_dir()
        ):
            assert (config.output_directory / stage08.STAGE08_SUCCESS_NAME).is_file()
            assert not (
                config.output_directory / stage08.STAGE08_IN_PROGRESS_NAME
            ).exists()
            raise OSError("synthetic parent fsync failure")
        real_fsync(path)

    monkeypatch.setattr(stage08, "_remove_in_progress_marker", remove_in_progress)
    monkeypatch.setattr(stage08, "_fsync_directory", fsync_directory)

    with pytest.raises(Stage08ValidationError, match="STAGE08_PUBLICATION_FAILURE"):
        materialize_stage08(config)

    failure_root = (
        config.output_directory
        if config.output_directory.exists()
        else _retained_attempt(config)
    )
    assert (failure_root / stage08.STAGE08_IN_PROGRESS_NAME).is_file()
    assert not (failure_root / stage08.STAGE08_SUCCESS_NAME).exists()


@pytest.mark.parametrize("cleanup_boundary", ("remove_success", "write_in_progress"))
def test_post_effect_demotion_mutation_errors_reconcile_idempotently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cleanup_boundary: str,
) -> None:
    config, validated = _fixture(tmp_path)
    monkeypatch.setattr(stage08, "_validated_inputs", lambda _: validated)
    real_fsync = getattr(stage08, "_fsync_directory")
    real_remove_success = stage08._remove_success_marker
    real_write_in_progress = stage08._write_in_progress_marker
    injected = False

    def fail_parent_fsync(path: Path) -> None:
        if path == config.output_directory.parent and config.output_directory.is_dir():
            raise OSError("synthetic parent fsync failure")
        real_fsync(path)

    def remove_then_raise(path: Path) -> None:
        nonlocal injected
        real_remove_success(path)
        if cleanup_boundary == "remove_success" and not injected:
            injected = True
            assert not path.exists()
            raise OSError("synthetic post-effect success removal failure")

    def write_then_raise(path: Path) -> None:
        nonlocal injected
        real_write_in_progress(path)
        if (
            cleanup_boundary == "write_in_progress"
            and path.parent == config.output_directory
            and not injected
        ):
            injected = True
            assert path.is_file()
            raise OSError("synthetic post-effect incomplete-marker failure")

    monkeypatch.setattr(stage08, "_fsync_directory", fail_parent_fsync)
    monkeypatch.setattr(stage08, "_remove_success_marker", remove_then_raise)
    monkeypatch.setattr(stage08, "_write_in_progress_marker", write_then_raise)
    with pytest.raises(Stage08ValidationError, match="STAGE08_PUBLICATION_FAILURE"):
        materialize_stage08(config)

    assert injected
    identity = stage08._directory_identity_if_present(config.output_directory)
    assert identity is not None
    _assert_reader_rejects_incomplete(config.output_directory, config)
    stage08._preserve_incomplete_publication(
        config.output_directory, expected_identity=identity
    )
    stage08._preserve_incomplete_publication(
        config.output_directory, expected_identity=identity
    )
    _assert_reader_rejects_incomplete(config.output_directory, config)


@pytest.mark.parametrize(
    "temporary_present,final_present,expected",
    (
        (True, False, stage08._PublicationPathState.TEMP_PRESENT_FINAL_ABSENT),
        (False, True, stage08._PublicationPathState.TEMP_ABSENT_FINAL_PRESENT),
        (True, True, stage08._PublicationPathState.TEMP_PRESENT_FINAL_PRESENT),
        (False, False, stage08._PublicationPathState.TEMP_ABSENT_FINAL_ABSENT),
    ),
)
def test_publication_path_observation_distinguishes_all_four_states(
    tmp_path: Path,
    temporary_present: bool,
    final_present: bool,
    expected: stage08._PublicationPathState,
) -> None:
    temporary = tmp_path / "temporary"
    final = tmp_path / "final"
    if temporary_present:
        temporary.mkdir()
    if final_present:
        final.mkdir()

    observation = stage08._observe_publication_paths(temporary, final)

    assert observation.state is expected
    assert observation.temporary_present is temporary_present
    assert observation.final_present is final_present
    assert (observation.temporary_identity is not None) is temporary_present
    assert (observation.final_identity is not None) is final_present


def test_reconciliation_never_follows_or_mutates_unrelated_final_symlink(
    tmp_path: Path,
) -> None:
    temporary = tmp_path / "temporary"
    unrelated = tmp_path / "unrelated"
    final = tmp_path / "final"
    temporary.mkdir(mode=0o700)
    unrelated.mkdir(mode=0o700)
    sentinel = unrelated / "sentinel"
    sentinel.write_text("unrelated\n", encoding="ascii")
    final.symlink_to(unrelated, target_is_directory=True)
    temporary_identity = stage08._directory_identity_if_present(temporary)
    assert temporary_identity is not None

    observation = stage08._observe_publication_paths(temporary, final)
    assert observation.state is stage08._PublicationPathState.TEMP_PRESENT_FINAL_PRESENT
    assert observation.final_identity is None
    stage08._demote_owned_publication(
        observation,
        temporary=temporary,
        final=final,
        expected_identity=temporary_identity,
    )

    assert final.is_symlink()
    assert sentinel.read_text(encoding="ascii") == "unrelated\n"
    assert (temporary / stage08.STAGE08_IN_PROGRESS_NAME).is_file()
    assert not (temporary / stage08.STAGE08_SUCCESS_NAME).exists()


def test_both_path_reconciliation_demotes_only_owned_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, validated = _fixture(tmp_path)
    monkeypatch.setattr(stage08, "_validated_inputs", lambda _: validated)
    outcome = materialize_stage08(config)
    final_identity = stage08._directory_identity_if_present(config.output_directory)
    assert final_identity is not None
    temporary = config.output_directory.parent / ".synthetic-owned-attempt.in_progress"
    temporary.mkdir(mode=0o700)
    temporary_identity = stage08._directory_identity_if_present(temporary)
    assert temporary_identity is not None

    for _ in range(2):
        observation = stage08._observe_publication_paths(
            temporary, config.output_directory
        )
        assert (
            observation.state
            is stage08._PublicationPathState.TEMP_PRESENT_FINAL_PRESENT
        )
        stage08._demote_owned_publication(
            observation,
            temporary=temporary,
            final=config.output_directory,
            expected_identity=temporary_identity,
        )

    _assert_reader_rejects_incomplete(
        temporary, replace(config, output_directory=temporary)
    )
    assert stage08._directory_identity_if_present(config.output_directory) == (
        final_identity
    )
    reopened = validate_stage08_bundle(
        config.output_directory,
        expected_manifest_sha256=outcome.manifest_sha256,
        config=config,
    )
    assert reopened.logical_dataset_sha256 == outcome.logical_dataset_sha256


@pytest.mark.parametrize("corruption", ("artifact", "manifest"))
def test_corruption_is_detected_before_terminal_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, corruption: str
) -> None:
    config, validated = _fixture(tmp_path)
    monkeypatch.setattr(stage08, "_validated_inputs", lambda _: validated)
    real_validate = stage08._validate_stage08_bundle_state

    def corrupt_then_validate(
        output_directory: Path, **kwargs: Any
    ) -> stage08.Stage08Outcome:
        if kwargs["terminal_state"] == stage08._TERMINAL_STATE_IN_PROGRESS:
            target = (
                next(
                    (output_directory / "candidate_evidence" / "data").glob("*.parquet")
                )
                if corruption == "artifact"
                else output_directory / stage08.STAGE08_MANIFEST_NAME
            )
            with target.open("ab") as stream:
                stream.write(b"synthetic-corruption")
        return real_validate(output_directory, **kwargs)

    monkeypatch.setattr(
        stage08, "_validate_stage08_bundle_state", corrupt_then_validate
    )
    expected_error = (
        "ARTIFACT_MISMATCH" if corruption == "artifact" else "MANIFEST_SHA256_MISMATCH"
    )
    with pytest.raises(Stage08ValidationError, match=expected_error):
        materialize_stage08(config)

    attempt = _retained_attempt(config)
    assert (attempt / stage08.STAGE08_IN_PROGRESS_NAME).is_file()
    assert not (attempt / stage08.STAGE08_SUCCESS_NAME).exists()
    assert not config.output_directory.exists()


def test_postpublication_reopen_failure_demotes_success_to_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, validated = _fixture(tmp_path)
    monkeypatch.setattr(stage08, "_validated_inputs", lambda _: validated)
    real_validate = stage08._validate_stage08_bundle_state

    def tamper_after_publish(
        output_directory: Path, **kwargs: Any
    ) -> stage08.Stage08Outcome:
        if kwargs["terminal_state"] == stage08._TERMINAL_STATE_PUBLISHED:
            artifact = next(
                (output_directory / "parser_component_evidence" / "data").glob(
                    "*.parquet"
                )
            )
            with artifact.open("ab") as stream:
                stream.write(b"synthetic-postpublication-tamper")
        return real_validate(output_directory, **kwargs)

    monkeypatch.setattr(stage08, "_validate_stage08_bundle_state", tamper_after_publish)
    with pytest.raises(Stage08ValidationError, match="ARTIFACT_MISMATCH"):
        materialize_stage08(config)

    assert config.output_directory.is_dir()
    assert (config.output_directory / stage08.STAGE08_IN_PROGRESS_NAME).is_file()
    assert not (config.output_directory / stage08.STAGE08_SUCCESS_NAME).exists()
    with pytest.raises(Stage08ValidationError, match="STAGE08_TERMINAL_STATE_MISMATCH"):
        validate_stage08_bundle(
            config.output_directory,
            expected_manifest_sha256="0" * 64,
            config=config,
        )


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
