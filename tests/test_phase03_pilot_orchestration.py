from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from phase03_helpers import fictional_country_reference
from safe_geocoding_pipeline.phase02.schema import base_staging_schema
from safe_geocoding_pipeline.phase03.cli import build_parser
from safe_geocoding_pipeline.phase03.errors import Phase03Error
from safe_geocoding_pipeline.phase03.pilot_orchestration import (
    _review_artifact_reference,
    validate_explicit_phase02_inputs,
    write_country_profile,
)
from safe_geocoding_pipeline.phase03.pilot_runner import require_pilot_free_space
from safe_geocoding_pipeline.phase03.pilot_runner import write_review_artifacts
from safe_geocoding_pipeline.phase03.review import manual_review_schema


def _row(index: int, country: str) -> dict[str, object]:
    value: dict[str, object] = {}
    for field in base_staging_schema():
        if pa.types.is_string(field.type):
            value[field.name] = ""
        elif pa.types.is_uint64(field.type):
            value[field.name] = index + 1
        else:
            value[field.name] = hashlib.sha256(f"row:{index}:{field.name}".encode()).digest()
    value.update(
        {
            "id": f"fictional-{index}",
            "country_iso_code": country,
            "source_file": "fictional.csv",
            "source_schema_version": "fictional-v1",
            "parser_version": "fictional-v1",
            "staging_version": "fictional-v1",
        }
    )
    return value


def _write_manifest(tmp_path: Path) -> tuple[Path, Path]:
    parquet_path = tmp_path / "fictional.parquet"
    pq.write_table(
        pa.Table.from_pylist([_row(0, "XZ"), _row(1, "Na")], schema=base_staging_schema()),
        parquet_path,
        write_page_checksum=True,
        write_statistics=False,
    )
    digest = hashlib.sha256(parquet_path.read_bytes()).hexdigest()
    manifest = tmp_path / "dataset_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "phase02_completion_gate": "PASS",
                "files": [
                    {
                        "output_file": parquet_path.name,
                        "output_sha256": digest,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest, parquet_path


def test_profile_reads_only_explicit_synthetic_phase02_file(tmp_path: Path) -> None:
    manifest, parquet_path = _write_manifest(tmp_path)
    output = tmp_path / "controlled" / "country_profile.json"
    payload = write_country_profile(
        manifest,
        [parquet_path],
        output,
        country_reference=fictional_country_reference(tmp_path),
        production=False,
    )
    assert payload["row_count"] == 2
    assert payload["counts"] == {"AMBIGUOUS_PLACEHOLDER": 1, "ASSIGNED:XZ": 1}
    assert output.stat().st_mode & 0o777 == 0o600


def test_explicit_phase02_file_set_and_hash_fail_closed(tmp_path: Path) -> None:
    manifest, parquet_path = _write_manifest(tmp_path)
    with pytest.raises(Phase03Error, match="EXPLICIT_FILE_SET_MISMATCH"):
        validate_explicit_phase02_inputs(manifest, [], production=False)
    parquet_path.write_bytes(parquet_path.read_bytes() + b"changed")
    with pytest.raises(Phase03Error, match="SHARD_IDENTITY_MISMATCH"):
        validate_explicit_phase02_inputs(manifest, [parquet_path], production=False)


def test_production_pass2_free_disk_gate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "safe_geocoding_pipeline.phase03.pilot_runner.shutil.disk_usage",
        lambda _: SimpleNamespace(free=24 * 1024**3),
    )
    with pytest.raises(Phase03Error, match="PILOT_INSUFFICIENT_FREE_DISK"):
        require_pilot_free_space(tmp_path)


def test_all_approved_pilot_cli_stages_are_explicitly_registered() -> None:
    parser = build_parser()
    subcommands = next(
        action.choices
        for action in parser._actions
        if hasattr(action, "choices") and isinstance(action.choices, dict)
    )
    assert {
        "pilot-plan",
        "pilot-profile",
        "pilot-select",
        "pilot-validate-identity-set",
        "pilot-materialize-development",
        "development-transform",
        "development-review-sample",
        "pilot-validate",
    }.issubset(subcommands)


def test_review_report_references_survive_iteration_promotion_without_artifact_changes(
    tmp_path: Path,
) -> None:
    identities = tuple(index.to_bytes(32, "big") for index in range(1, 5))
    attempt_iteration = tmp_path / ".in_progress" / "fictional_iteration"
    review_directory = attempt_iteration / "review"
    context, labels = write_review_artifacts(
        review_directory,
        protected_rows=[
            {
                "stable_source_row_id_v1": identity,
                "fictional_raw_context": f"Synthetic context {index}",
            }
            for index, identity in enumerate(identities, start=1)
        ],
        review_ids=identities,
        independent_double_review_ids=identities[:2],
        pilot_version="fictional-pilot-v1",
    )
    references = {
        "protected_context_path": _review_artifact_reference(
            review_directory, context
        ),
        "portable_labels_path": _review_artifact_reference(review_directory, labels),
    }
    assert references == {
        "protected_context_path": "review/protected_review_context.parquet",
        "portable_labels_path": "review/portable_review_labels.parquet",
    }
    assert all(not Path(value).is_absolute() for value in references.values())
    assert all(".in_progress" not in Path(value).parts for value in references.values())

    original_bytes = {path.name: path.read_bytes() for path in (context, labels)}
    original_modes = {path.name: path.stat().st_mode & 0o777 for path in (context, labels)}
    original_context = pq.ParquetFile(
        context, page_checksum_verification=True
    ).read(use_threads=False)
    original_labels = pq.ParquetFile(
        labels, page_checksum_verification=True
    ).read(use_threads=False)
    report_bytes = (
        json.dumps(references, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    report_hash = hashlib.sha256(report_bytes).hexdigest()
    attempt_report = tmp_path / "reports" / ".in_progress" / "fictional_iteration"
    attempt_report.mkdir(parents=True)
    report_path = attempt_report / "review_sample_v2.json"
    report_path.write_bytes(report_bytes)

    final_iteration = tmp_path / "fictional_iteration"
    final_report = tmp_path / "reports" / "fictional_iteration"
    final_iteration.parent.mkdir(parents=True, exist_ok=True)
    os.replace(attempt_iteration, final_iteration)
    os.replace(attempt_report, final_report)

    promoted_context = final_iteration / references["protected_context_path"]
    promoted_labels = final_iteration / references["portable_labels_path"]
    assert promoted_context.read_bytes() == original_bytes[context.name]
    assert promoted_labels.read_bytes() == original_bytes[labels.name]
    assert promoted_context.stat().st_mode & 0o777 == original_modes[context.name]
    assert promoted_labels.stat().st_mode & 0o777 == original_modes[labels.name]
    promoted_context_table = pq.ParquetFile(
        promoted_context, page_checksum_verification=True
    ).read(use_threads=False)
    promoted_labels_table = pq.ParquetFile(
        promoted_labels, page_checksum_verification=True
    ).read(use_threads=False)
    assert promoted_context_table.equals(original_context)
    assert promoted_labels_table.equals(original_labels)
    assert promoted_labels_table.schema.remove_metadata() == (
        manual_review_schema().remove_metadata()
    )
    assert promoted_context_table["stable_source_row_id_v1"].to_pylist() == list(
        identities
    )
    assert sum(promoted_labels_table["is_independent_review"].to_pylist()) == 2
    assert hashlib.sha256(
        (final_report / "review_sample_v2.json").read_bytes()
    ).hexdigest() == report_hash
