from __future__ import annotations

import hashlib
import json
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
    validate_explicit_phase02_inputs,
    write_country_profile,
)
from safe_geocoding_pipeline.phase03.pilot_runner import require_pilot_free_space


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
