from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path, PurePosixPath
from typing import Any

from .models import KnownExtreme, Phase01FileEntry, Phase01Manifest


def _require_direct_csv(relative_path: str) -> None:
    candidate = PurePosixPath(relative_path)
    if candidate.is_absolute() or len(candidate.parts) != 1 or candidate.suffix.lower() != ".csv":
        raise ValueError(f"Unsafe Phase 1 relative source path: {relative_path!r}")


def _required(row: dict[str, str], key: str) -> str:
    value = row.get(key, "")
    if value == "":
        raise ValueError(f"Phase 1 manifest is missing required {key}")
    return value


def load_phase01_manifest(run_dir: Path) -> Phase01Manifest:
    resolved = run_dir.resolve()
    run_path = resolved / "phase01_run.json"
    manifest_path = resolved / "phase01_file_manifest.csv"
    anomaly_path = resolved / "phase01_anomalies.csv.gz"
    with run_path.open(encoding="utf-8") as stream:
        run: dict[str, Any] = json.load(stream)
    if run.get("scope_gate") != "PASS" or run.get("phase01_completion_gate") != "PASS":
        raise ValueError("Phase 1 run did not pass its complete inventory gate")
    run_id = str(run.get("run_id", ""))
    input_manifest = str(run.get("input_manifest_sha256", ""))
    if not run_id or len(input_manifest) != 64:
        raise ValueError("Phase 1 run metadata is incomplete")

    files: dict[str, Phase01FileEntry] = {}
    with manifest_path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            relative = _required(row, "relative_path")
            _require_direct_csv(relative)
            if relative in files:
                raise ValueError(f"Duplicate Phase 1 manifest path: {relative}")
            entry = Phase01FileEntry(
                file_id=int(_required(row, "file_id")),
                relative_path=relative,
                file_name=_required(row, "file_name"),
                size_bytes=int(_required(row, "size_bytes_before")),
                mtime_utc=_required(row, "mtime_utc_before"),
                sha256=_required(row, "sha256"),
                logical_record_count=int(_required(row, "logical_record_count")),
                schema_fingerprint=_required(row, "schema_fingerprint"),
                bom_type=_required(row, "bom_type"),
            )
            if entry.file_name != relative or len(entry.sha256) != 64:
                raise ValueError(f"Invalid Phase 1 file identity: {relative}")
            if row.get("scan_status") != "COMPLETE" or row.get("counts_complete") != "True":
                raise ValueError(f"Phase 1 file is not complete: {relative}")
            files[relative] = entry
    if len(files) != 206:
        raise ValueError(f"Authoritative Phase 1 manifest must contain 206 files, found {len(files)}")

    extremes: dict[str, list[KnownExtreme]] = {}
    with gzip.open(anomaly_path, "rt", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if row.get("anomaly_type") != "OVERSIZED_FIELD":
                continue
            relative = _required(row, "relative_path")
            if relative not in files:
                raise ValueError(f"Extreme anomaly has unknown source file: {relative}")
            extreme = KnownExtreme(
                relative_path=relative,
                logical_record_number=int(_required(row, "logical_record_number")),
                column_name=_required(row, "column_name"),
                field_length_chars=int(_required(row, "field_length_chars")),
                value_sha256=_required(row, "value_sha256"),
                physical_line_start=int(row["physical_line_start"])
                if row.get("physical_line_start")
                else None,
                physical_line_end=int(row["physical_line_end"])
                if row.get("physical_line_end")
                else None,
            )
            extremes.setdefault(relative, []).append(extreme)
    return Phase01Manifest(
        run_id=run_id,
        input_manifest_sha256=input_manifest,
        files=files,
        extremes={key: tuple(value) for key, value in extremes.items()},
    )
