"""Independent adversarial Stage 8 publication-state rereview.

This harness uses only synthetic values.  It exercises the real Stage 8
materializer, but creates upstream fixture files independently and makes its
publication/ownership assertions from no-follow filesystem observations.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq

from safe_geocoding_pipeline.preprocessing.stages import s08_address_evidence as stage08
from safe_geocoding_pipeline.preprocessing.stages.s06_exact_deduplication import (
    row_map_schema,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_country_eligibility import (
    COUNTRY_UNANIMOUS_VALID,
    PARSER_ELIGIBLE_COUNTRY,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_libpostal_adapter import (
    PARSED_NONEMPTY,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_parser_evidence import (
    NO_STRUCTURAL_WARNINGS_DETECTED,
    PARSER_EXECUTION_ORIGIN,
    stage07_evidence_schema,
)


REVIEWED_CANDIDATE_SHA = "70e3de9536aee7074e27018d39e0164f3a2200ae"
REVIEWED_EXECUTABLE_SHA = "bdea7232a3f92ebd381be87610b753b8e4c35481"


def _private_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


def _write_table(path: Path, table: pa.Table) -> Path:
    _private_directory(path.parent)
    pq.write_table(table, path, write_page_checksum=True)
    path.chmod(0o600)
    return path


def _default_stage06_value(field: pa.Field) -> object:
    if field.name == "id":
        return "synthetic-provider-id"
    if pa.types.is_string(field.type):
        return f"synthetic-{field.name}"
    if pa.types.is_boolean(field.type):
        return False
    if pa.types.is_unsigned_integer(field.type):
        return 1
    if pa.types.is_fixed_size_binary(field.type):
        return bytes([7]) * field.type.byte_width
    if pa.types.is_list(field.type) or pa.types.is_large_list(field.type):
        return []
    raise AssertionError(f"unsupported synthetic Stage 6 field type: {field.type}")


def _synthetic_config(
    root: Path,
) -> tuple[stage08.Stage08Config, stage08._ValidatedInputs]:
    candidate_id = bytes([3]) * 32
    components = [
        {"label": "house_number", "value": "synthetic-number"},
        {"label": "road", "value": "synthetic-road"},
    ]
    stage07_row: dict[str, Any] = {
        "stage06_exact_candidate_id": candidate_id,
        "stage06_candidate_lower": "synthetic candidate",
        "stage06_occurrence_count": 2,
        "stage06_standard_occurrence_count": 1,
        "stage06_native_occurrence_count": 1,
        "stage07_country_provenance_status": COUNTRY_UNANIMOUS_VALID,
        "stage07_trusted_country_iso_code": "de",
        "stage07_valid_country_occurrence_count": 2,
        "stage07_missing_country_occurrence_count": 0,
        "stage07_invalid_country_occurrence_count": 0,
        "stage07_distinct_valid_country_count": 1,
        "stage07_parser_applicability_status": PARSER_ELIGIBLE_COUNTRY,
        "stage07_parse_status": PARSED_NONEMPTY,
        "stage07_parser_execution_origin": PARSER_EXECUTION_ORIGIN,
        "stage07_libpostal_components": components,
        "stage07_structural_warning_status": NO_STRUCTURAL_WARNINGS_DETECTED,
        "stage07_structural_warning_reason_codes": [],
        "stage07_raw_ordered_substrings": True,
        "stage07_lexical_numeric_stream_equal": True,
        "stage07_internal_boundary_count": 0,
        "stage07_internal_single_codepoint_fragment_count": 0,
        "stage07_maximum_components_per_lexical_run": 1,
        "stage07_adjacent_repeated_label_internal_boundary_count": 0,
        "stage07_candidate_lexical_numeric_codepoints": 18,
        "stage07_output_lexical_numeric_codepoints": 18,
    }
    stage07_path = _write_table(
        root / "inputs" / "stage07.parquet",
        pa.Table.from_pylist([stage07_row], schema=stage07_evidence_schema()),
    )

    stage06_schema = row_map_schema()
    stage06_row = {
        field.name: _default_stage06_value(field) for field in stage06_schema
    }
    stage06_row["source_logical_record_number"] = 1
    stage06_row["stable_source_row_id_v1"] = bytes([5]) * 32
    stage06_row["source_file_sha256"] = bytes([6]) * 32
    stage06_row["stage06_standard_exact_candidate_id"] = candidate_id
    stage06_row["stage06_native_exact_candidate_id"] = candidate_id
    stage06_path = _write_table(
        root / "inputs" / "stage06.parquet",
        pa.Table.from_pylist([stage06_row], schema=stage06_schema),
    )

    binding = stage08.Stage08InputBinding(
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
        candidate_rows=1,
        parsed_nonempty_rows=1,
        parsed_empty_rows=0,
        raw_component_rows=2,
        maximum_component_count=2,
        maximum_candidate_codepoints=19,
        source_rows=1,
        occurrence_rows=2,
        standard_occurrences=1,
        native_occurrences=1,
    )
    config = stage08.Stage08Config(
        stage07_output_directory=root / "unused-stage07-root",
        stage06_output_directory=root / "unused-stage06-root",
        output_directory=root / "stage08-output",
        execution_git_sha=REVIEWED_EXECUTABLE_SHA,
        binding=binding,
        authoritative_development=False,
        controlled_execution=False,
        input_batch_rows=1,
        candidate_output_batch_rows=1,
        component_batch_rows=1,
        target_batch_bytes=4_096,
        candidate_shard_rows=2,
        component_shard_rows=4,
        source_shard_rows=2,
        duckdb_memory_limit="512MB",
        duckdb_threads=1,
    )
    inputs = stage08._ValidatedInputs(
        stage07_paths=(stage07_path,), stage06_row_map_paths=(stage06_path,)
    )
    return config, inputs


def _identity(path: Path) -> tuple[int, int]:
    status = path.stat(follow_symlinks=False)
    assert stat.S_ISDIR(status.st_mode)
    assert not path.is_symlink()
    return status.st_dev, status.st_ino


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _independent_terminal_success(root: Path) -> str:
    assert root.is_dir() and not root.is_symlink()
    success = root / stage08.STAGE08_SUCCESS_NAME
    in_progress = root / stage08.STAGE08_IN_PROGRESS_NAME
    assert success.is_file() and not success.is_symlink()
    assert not os.path.lexists(in_progress)
    payload = json.loads(success.read_text(encoding="utf-8"))
    manifest = root / stage08.STAGE08_MANIFEST_NAME
    assert manifest.is_file() and not manifest.is_symlink()
    assert payload["manifest_sha256"] == _sha256(manifest)
    return str(payload["manifest_sha256"])


def _exercise_real_rename_then_raise(root: Path) -> dict[str, object]:
    config, inputs = _synthetic_config(root)
    renamed_identity: tuple[int, int] | None = None

    def rename_then_raise(source: Path, destination: Path) -> None:
        nonlocal renamed_identity
        source_identity = _identity(source)
        os.rename(source, destination)
        assert not os.path.lexists(source)
        assert os.path.lexists(destination)
        renamed_identity = _identity(destination)
        assert renamed_identity == source_identity
        raise OSError("independent injected exception after real rename")

    with ExitStack() as stack:
        stack.enter_context(patch.object(stage08, "_validate_runtime", lambda: None))
        stack.enter_context(
            patch.object(stage08, "_validated_inputs", lambda _: inputs)
        )
        stack.enter_context(
            patch.object(stage08, "_atomic_publish_directory", rename_then_raise)
        )
        outcome = stage08.materialize_stage08(config)

    manifest_sha = _independent_terminal_success(config.output_directory)
    with (
        patch.object(stage08, "_validate_runtime", lambda: None),
        patch.object(stage08, "_validated_inputs", lambda _: inputs),
    ):
        reopened = stage08.validate_stage08_bundle(
            config.output_directory,
            expected_manifest_sha256=manifest_sha,
            config=config,
        )
    assert renamed_identity is not None
    assert _identity(config.output_directory) == renamed_identity
    assert reopened.logical_dataset_sha256 == outcome.logical_dataset_sha256
    return {
        "post_effect_rename_reproduced": True,
        "post_effect_rename_adopted_after_validation": True,
        "owned_identity_retained": True,
    }


def _exercise_replacement_between_identity_check_and_validation(
    root: Path,
) -> dict[str, object]:
    config, inputs = _synthetic_config(root)
    replacement = root / "unowned-byte-identical-replacement"
    displaced_owned = root / "displaced-owned-publication"
    captured_identity: tuple[int, int] | None = None
    replacement_identity: tuple[int, int] | None = None
    swap_complete = False
    real_parent_fsync = stage08._fsync_directory

    def rename_clone_then_raise(source: Path, destination: Path) -> None:
        nonlocal captured_identity, replacement_identity
        captured_identity = _identity(source)
        os.rename(source, destination)
        assert _identity(destination) == captured_identity
        shutil.copytree(destination, replacement, copy_function=shutil.copy2)
        replacement_identity = _identity(replacement)
        assert replacement_identity != captured_identity
        raise OSError("independent injected exception after real rename")

    def swap_during_parent_fsync(path: Path) -> None:
        nonlocal swap_complete
        if (
            not swap_complete
            and path == config.output_directory.parent
            and config.output_directory.is_dir()
            and replacement.is_dir()
        ):
            os.rename(config.output_directory, displaced_owned)
            os.rename(replacement, config.output_directory)
            swap_complete = True
            assert captured_identity is not None
            assert replacement_identity is not None
            assert _identity(displaced_owned) == captured_identity
            assert _identity(config.output_directory) == replacement_identity
        real_parent_fsync(path)

    with ExitStack() as stack:
        stack.enter_context(patch.object(stage08, "_validate_runtime", lambda: None))
        stack.enter_context(
            patch.object(stage08, "_validated_inputs", lambda _: inputs)
        )
        stack.enter_context(
            patch.object(stage08, "_atomic_publish_directory", rename_clone_then_raise)
        )
        stack.enter_context(
            patch.object(stage08, "_fsync_directory", swap_during_parent_fsync)
        )
        outcome = stage08.materialize_stage08(config)

    assert swap_complete
    assert captured_identity is not None and replacement_identity is not None
    assert _identity(config.output_directory) == replacement_identity
    assert _identity(config.output_directory) != captured_identity
    assert _identity(displaced_owned) == captured_identity
    final_manifest_sha = _independent_terminal_success(config.output_directory)
    owned_manifest_sha = _independent_terminal_success(displaced_owned)
    assert final_manifest_sha == outcome.manifest_sha256 == owned_manifest_sha
    with (
        patch.object(stage08, "_validate_runtime", lambda: None),
        patch.object(stage08, "_validated_inputs", lambda _: inputs),
    ):
        final_reopened = stage08.validate_stage08_bundle(
            config.output_directory,
            expected_manifest_sha256=final_manifest_sha,
            config=config,
        )
    assert final_reopened.logical_dataset_sha256 == outcome.logical_dataset_sha256
    return {
        "materializer_returned_success": True,
        "captured_owned_identity": list(captured_identity),
        "returned_final_identity": list(_identity(config.output_directory)),
        "returned_final_is_captured_owned_identity": False,
        "unowned_final_passes_stage08_validator": True,
        "displaced_owned_tree_still_exposes_success": True,
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="stage08-independent-rereview-") as tmp:
        base = Path(tmp)
        post_effect = _exercise_real_rename_then_raise(base / "post-effect")
        replacement = _exercise_replacement_between_identity_check_and_validation(
            base / "replacement-race"
        )
    result = {
        "reviewed_candidate_sha": REVIEWED_CANDIDATE_SHA,
        "reviewed_executable_sha": REVIEWED_EXECUTABLE_SHA,
        "post_effect_control": post_effect,
        "blocking_falsification": replacement,
        "verdict": "STAGE08_ADDRESS_EVIDENCE_INDEPENDENT_REREVIEW_FAIL",
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
