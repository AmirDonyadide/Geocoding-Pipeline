from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import sqlite3
import struct
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import safe_geocoding_pipeline.preprocessing.stages.s01_ingestion as s01

from safe_geocoding_pipeline.execution_policy import ExecutionPolicyError
from safe_geocoding_pipeline.preprocessing.stages.s00_constants import INVENTORY_VERSION
from safe_geocoding_pipeline.preprocessing.stages.s01_constants import (
    PARSER_VERSION,
    REPORT_NAMES,
    SEMANTIC_DIGEST_VERSION,
    SOURCE_SCHEMA_VERSION,
    STABLE_ROW_ID_VERSION,
    STAGING_VERSION,
)
from safe_geocoding_pipeline.preprocessing.stages.s01_identity import (
    stable_source_row_id_v1,
)
from safe_geocoding_pipeline.preprocessing.stages.s01_constants import (
    FILE_VALIDATION_COLUMNS,
)
from safe_geocoding_pipeline.preprocessing.stages.s01_schema import (
    base_staging_schema,
    schema_fingerprint,
    schema_with_metadata,
)
from safe_geocoding_pipeline.preprocessing.stages.s01_semantic import RawSemanticDigest
from safe_geocoding_pipeline.preprocessing.stages.s00_inventory import (
    STAGE00_CONTRACT_VERSION,
    ArtifactIdentity,
    Stage00InventoryRecord,
    ValidatedSourceInventoryBundle,
)
from safe_geocoding_pipeline.preprocessing.stages.s01_ingestion import (
    STAGE01_ADOPTION_RECORD_NAME,
    STAGE01_CONTRACT_VERSION,
    STAGE01_LOGICAL_DATASET_DOMAIN,
    Stage01SourceRecord,
    Stage01ValidationError,
    adopt_stage01_bundle,
    stage01_logical_dataset_sha256_v1,
    validate_stage01_bundle,
)
from safe_geocoding_pipeline.raw_csv import SOURCE_COLUMNS

SOURCE_INVENTORY_COMMIT = "1" * 40
INGESTION_COMMIT = "2" * 40
ADOPTING_COMMIT = "3" * 40
SOURCE_POPULATION_DIGEST = "4" * 64
SCIENTIFIC_INVENTORY_DIGEST = "5" * 64
PARSER_CONTRACT_DIGEST = "6" * 64
SOURCE_INVENTORY_MANIFEST_DIGEST = "7" * 64
CONFIGURATION_DIGEST = "8" * 64
IMPLEMENTATION_DIGEST = "9" * 64
RUN_ID = "phase02_20260101T000000Z_fixture"


@dataclass(slots=True)
class SyntheticBundle:
    stage00_record: Path
    stage00_record_sha256: str
    source_inventory_run: Path
    source_inventory_bundle: ValidatedSourceInventoryBundle
    ingestion_run: Path
    ingestion_reports: Path
    output: Path
    manifest: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SourceInventoryFileEntry:
    """Synthetic input used only to construct an accepted-format state fixture."""

    file_id: int
    relative_path: str
    file_name: str
    size_bytes: int
    mtime_utc: str
    sha256: str
    logical_record_count: int
    schema_fingerprint: str
    bom_type: str


def _write_completed_state(
    path: Path,
    entries: list[SourceInventoryFileEntry],
    manifest_files: list[dict[str, Any]],
) -> None:
    """Build the minimum frozen Stage 1 SQLite evidence used by the validator."""
    by_path = {item["source_file"]: item for item in manifest_files}
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE run_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
        CREATE TABLE file_state (
            relative_path TEXT PRIMARY KEY,
            source_sha256 TEXT NOT NULL,
            expected_rows INTEGER NOT NULL,
            status TEXT NOT NULL,
            attempt INTEGER NOT NULL,
            config_fingerprint TEXT NOT NULL,
            implementation_fingerprint TEXT NOT NULL,
            final_path TEXT NOT NULL,
            source_semantic_digest TEXT NOT NULL,
            staging_semantic_digest TEXT NOT NULL,
            output_sha256 TEXT NOT NULL,
            output_size_bytes INTEGER NOT NULL,
            source_rows INTEGER NOT NULL,
            staging_rows INTEGER NOT NULL,
            failure_code TEXT NOT NULL,
            failure_detail TEXT NOT NULL
        ) WITHOUT ROWID;
        CREATE TABLE attempt_history (
            relative_path TEXT NOT NULL,
            attempt INTEGER NOT NULL,
            completed_at_utc TEXT NOT NULL,
            terminal_status TEXT NOT NULL,
            failure_code TEXT NOT NULL,
            output_sha256 TEXT NOT NULL
        );
        """
    )
    connection.executemany(
        "INSERT INTO run_meta(key, value) VALUES (?, ?)",
        (
            ("run_id", RUN_ID),
            ("run_scope", "FULL_CONVERSION"),
            ("phase01_input_manifest_sha256", SOURCE_INVENTORY_MANIFEST_DIGEST),
            ("configuration_fingerprint", CONFIGURATION_DIGEST),
            ("implementation_fingerprint", IMPLEMENTATION_DIGEST),
        ),
    )
    for entry in entries:
        item = by_path[entry.relative_path]
        connection.execute(
            """
            INSERT INTO file_state VALUES (?, ?, ?, 'COMPLETE', 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '')
            """,
            (
                entry.relative_path,
                entry.sha256,
                entry.logical_record_count,
                CONFIGURATION_DIGEST,
                IMPLEMENTATION_DIGEST,
                item["output_file"],
                item["source_semantic_digest"],
                item["staging_semantic_digest"],
                item["output_sha256"],
                item["output_size_bytes"],
                item["source_rows"],
                item["staging_rows"],
            ),
        )
        connection.execute(
            "INSERT INTO attempt_history VALUES (?, 1, ?, 'COMPLETE', '', ?)",
            (entry.relative_path, "2026-01-01T00:00:00Z", item["output_sha256"]),
        )
    connection.commit()
    connection.close()
    path.chmod(0o600)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inventory_record(
    *, file_id: int, relative_path: str, source_sha256: str, rows: int
) -> Stage00InventoryRecord:
    return Stage00InventoryRecord(
        file_id=file_id,
        relative_path=relative_path,
        file_size_bytes=100 + file_id,
        file_sha256=source_sha256,
        source_stable_during_scan=True,
        encoding_status="UTF8_VALID",
        bom_type="NONE",
        header_present=True,
        observed_column_count=15,
        schema_fingerprint="a" * 64,
        schema_matches_contract=True,
        logical_record_count=rows,
        valid_schema_record_count=rows,
        wrong_column_count_record_count=0,
        parser_error_count=0,
        multiline_record_count=0,
        counts_complete=True,
        scan_status="COMPLETE",
        duplicate_file_group=None,
        duplicate_file_group_size=0,
        max_record_length_chars=100,
        max_field_length_chars=40,
    )


def _raw_row(identifier: str, postcode: str, city: str) -> list[str]:
    values = [""] * len(SOURCE_COLUMNS)
    values[0] = identifier
    values[1] = "Fictional Straße 1"
    values[5] = "架空住所一丁目"
    values[9] = postcode
    values[10] = city
    values[12] = "DE"
    values[13] = "1"
    values[14] = "fictional"
    return values


def _semantic_digest(rows: list[list[str]]) -> str:
    digest = RawSemanticDigest()
    for ordinal, row in enumerate(rows, start=1):
        digest.update_row(row, ordinal, require_non_null=True)
    return digest.hexdigest()


def _write_json(path: Path, value: object, *, mode: int = 0o600) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(mode)


def _write_parquet(
    path: Path,
    *,
    source_path: str,
    source_sha256: str,
    rows: list[list[str]],
) -> None:
    source_hash = bytes.fromhex(source_sha256)
    columns: list[list[Any]] = [[] for _ in range(22)]
    for ordinal, raw in enumerate(rows, start=1):
        values: tuple[Any, ...] = tuple(raw) + (
            source_path,
            ordinal,
            stable_source_row_id_v1(source_hash, ordinal),
            source_hash,
            SOURCE_SCHEMA_VERSION,
            PARSER_VERSION,
            STAGING_VERSION,
        )
        for target, value in zip(columns, values, strict=True):
            target.append(value)
    metadata = {
        "phase02_run_id": RUN_ID,
        "phase01_run_id": "phase01_fictional",
        "phase01_input_manifest_sha256": SOURCE_INVENTORY_MANIFEST_DIGEST,
        "pipeline_git_commit": INGESTION_COMMIT[:8],
        "source_file": source_path,
        "source_file_sha256": source_sha256,
        "source_schema_version": SOURCE_SCHEMA_VERSION,
        "parser_version": PARSER_VERSION,
        "staging_version": STAGING_VERSION,
        "semantic_digest_version": SEMANTIC_DIGEST_VERSION,
        "stable_source_row_id_version": STABLE_ROW_ID_VERSION,
        "configuration_fingerprint": CONFIGURATION_DIGEST,
        "implementation_fingerprint": IMPLEMENTATION_DIGEST,
    }
    schema = schema_with_metadata(metadata)
    table = pa.Table.from_arrays(
        [
            pa.array(values, type=field.type)
            for field, values in zip(schema, columns, strict=True)
        ],
        schema=schema,
    )
    pq.write_table(
        table,
        path,
        version="1.0",
        data_page_version="1.0",
        compression="zstd",
        compression_level=3,
        write_page_checksum=True,
        row_group_size=2,
    )
    path.chmod(0o600)


def _file_report_row(run_id: str, item: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {name: "" for name in FILE_VALIDATION_COLUMNS}
    row.update(
        {
            "run_id": run_id,
            "relative_path": item["source_file"],
            "status": "PASS",
            "source_size_bytes": 100,
            "source_sha256": item["source_sha256"],
            "source_rows": item["source_rows"],
            "staging_rows": item["staging_rows"],
            "source_semantic_digest": item["source_semantic_digest"],
            "staging_semantic_digest": item["staging_semantic_digest"],
            "semantic_digest_match": True,
            "output_path": item["output_file"],
            "output_size_bytes": item["output_size_bytes"],
            "output_sha256": item["output_sha256"],
            "compression_ratio": 1.0,
            "row_group_count": 1,
            "row_group_rows_json": json.dumps([item["source_rows"]]),
            "isolated_record_count": 0,
            "source_empty_counts_json": "{}",
            "staging_empty_counts_json": "{}",
            "source_non_ascii_counts_json": "{}",
            "staging_non_ascii_counts_json": "{}",
            "raw_null_count": 0,
            "provenance_valid": True,
            "stable_ids_valid": True,
            "stable_ids_distinct": item["source_rows"],
            "known_extremes_valid": True,
            "extreme_observations_json": "[]",
            "page_checksums_verified": True,
            "conversion_seconds": 0.1,
            "validation_seconds": 0.1,
            "hashing_seconds": 0.1,
            "promotion_seconds": 0.1,
            "peak_temporary_bytes": item["output_size_bytes"],
            "peak_rss_bytes": 1024,
        }
    )
    return row


def _refresh_manifest_and_marker(bundle: SyntheticBundle) -> None:
    manifest_path = bundle.ingestion_run / "dataset_manifest.json"
    _write_json(manifest_path, bundle.manifest)
    marker = json.loads(
        (bundle.ingestion_run / "_SUCCESS.json").read_text(encoding="utf-8")
    )
    marker["dataset_manifest_sha256"] = _sha256(manifest_path)
    _write_json(bundle.ingestion_run / "_SUCCESS.json", marker)


def _synthetic_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> SyntheticBundle:
    source_inventory_run = tmp_path / "phase01_fictional"
    source_inventory_run.mkdir(mode=0o700)
    _write_json(
        source_inventory_run / "phase01_run.json",
        {"input_manifest_sha256": SOURCE_INVENTORY_MANIFEST_DIGEST},
    )
    source_rows = {
        "fictional_a.csv": [
            _raw_row("0001", "00123", "München"),
            _raw_row("0002", "00124", "Example City"),
        ],
        "fictional_b.csv": [
            _raw_row("0003", "AB 1-2", "東京"),
            _raw_row("0004", "00007", "Example City"),
        ],
    }
    source_hashes = {"fictional_a.csv": "b" * 64, "fictional_b.csv": "c" * 64}
    inventory_records = tuple(
        _inventory_record(
            file_id=index,
            relative_path=relative,
            source_sha256=source_hashes[relative],
            rows=len(source_rows[relative]),
        )
        for index, relative in enumerate(sorted(source_rows), start=1)
    )
    source_inventory_artifacts = (
        ArtifactIdentity("phase01_run.json", 10, "d" * 64),
        ArtifactIdentity("phase01_file_manifest.csv", 20, "e" * 64),
    )
    source_inventory_bundle = ValidatedSourceInventoryBundle(
        run_dir=source_inventory_run,
        run_id="phase01_fictional",
        inventory_version=INVENTORY_VERSION,
        producing_git_commit=SOURCE_INVENTORY_COMMIT,
        records=inventory_records,
        artifacts=source_inventory_artifacts,
        success_marker=ArtifactIdentity("_SCOPE_PASS", 5, "f" * 64),
        parser_contract_fingerprint=PARSER_CONTRACT_DIGEST,
        source_population_sha256_v1=SOURCE_POPULATION_DIGEST,
        stage00_scientific_inventory_sha256_v1=SCIENTIFIC_INVENTORY_DIGEST,
    )
    monkeypatch.setattr(
        s01,
        "validate_stage00_inventory",
        lambda *_args, **_kwargs: source_inventory_bundle,
    )

    stage00_dir = tmp_path / "stage00"
    stage00_dir.mkdir(mode=0o700)
    stage00_record = stage00_dir / "stage00_adoption.json"
    _write_json(
        stage00_record,
        {
            "stage00_contract_version": STAGE00_CONTRACT_VERSION,
            "status": "STAGE_0_ACCEPTED",
            "identity": {
                "adopted_phase01_run_id": source_inventory_bundle.run_id,
                "phase01_inventory_version": source_inventory_bundle.inventory_version,
                "producing_git_commit": SOURCE_INVENTORY_COMMIT,
                "source_population_sha256_v1": SOURCE_POPULATION_DIGEST,
                "stage00_scientific_inventory_sha256_v1": SCIENTIFIC_INVENTORY_DIGEST,
                "parser_contract_fingerprint": PARSER_CONTRACT_DIGEST,
            },
            "bundle_integrity": {
                "artifacts": [item.to_dict() for item in source_inventory_artifacts],
                "terminal_state": {
                    "success_marker": source_inventory_bundle.success_marker.to_dict(),
                    "failure_marker_present": False,
                    "in_progress_marker_present": False,
                },
            },
            "validation": {
                "acceptance_status": "STAGE_0_ACCEPTED",
                "artifact_integrity": "PASS",
                "manifest_schema": "PASS",
                "parser_contract": "PASS",
                "per_file_completeness": "PASS",
                "population_contract": "PASS",
                "terminal_state": "PASS",
                "source_file_count": len(inventory_records),
            },
        },
    )

    ingestion_run = tmp_path / RUN_ID
    data = ingestion_run / "data"
    work = ingestion_run / "_work"
    in_progress = ingestion_run / ".in_progress"
    for directory in (ingestion_run, data, work, in_progress):
        directory.mkdir(mode=0o700, exist_ok=True)
        directory.chmod(0o700)

    manifest_files: list[dict[str, Any]] = []
    entries: list[SourceInventoryFileEntry] = []
    for index, relative in enumerate(sorted(source_rows), start=1):
        output_relative = f"data/part-{index:03d}.parquet"
        output = ingestion_run / output_relative
        _write_parquet(
            output,
            source_path=relative,
            source_sha256=source_hashes[relative],
            rows=source_rows[relative],
        )
        semantic = _semantic_digest(source_rows[relative])
        manifest_files.append(
            {
                "source_file": relative,
                "source_sha256": source_hashes[relative],
                "source_rows": len(source_rows[relative]),
                "output_file": output_relative,
                "output_sha256": _sha256(output),
                "output_size_bytes": output.stat().st_size,
                "staging_rows": len(source_rows[relative]),
                "source_semantic_digest": semantic,
                "staging_semantic_digest": semantic,
                "status": "PASS",
            }
        )
        entries.append(
            SourceInventoryFileEntry(
                file_id=index,
                relative_path=relative,
                file_name=relative,
                size_bytes=100 + index,
                mtime_utc="2026-01-01T00:00:00Z",
                sha256=source_hashes[relative],
                logical_record_count=len(source_rows[relative]),
                schema_fingerprint="a" * 64,
                bom_type="NONE",
            )
        )
    total_rows = sum(item["source_rows"] for item in manifest_files)
    reconciliation = {
        "status": "PASS",
        "file_count": len(manifest_files),
        "total_rows": total_rows,
        "distinct_ids": total_rows,
        "distinct_stable_ids": total_rows,
        "null_ids": 0,
        "empty_ids": 0,
        "duplicate_stable_ids": 0,
        "raw_null_count": 0,
        "schema_count": 1,
        "missing_files": [],
        "extra_files": [],
        "duckdb_seconds": 0.1,
        "duckdb_version": "fictional",
    }
    manifest = {
        "run_id": RUN_ID,
        "run_scope": "FULL_CONVERSION",
        "phase02_completion_gate": "PASS",
        "phase01_input_manifest_sha256": SOURCE_INVENTORY_MANIFEST_DIGEST,
        "configuration_fingerprint": CONFIGURATION_DIGEST,
        "implementation_fingerprint": IMPLEMENTATION_DIGEST,
        "schema_fingerprint": schema_fingerprint(),
        "files": manifest_files,
        "reconciliation": reconciliation,
    }
    manifest_path = ingestion_run / "dataset_manifest.json"
    _write_json(manifest_path, manifest)
    _write_json(
        ingestion_run / "_SUCCESS.json",
        {
            "run_id": RUN_ID,
            "run_scope": "FULL_CONVERSION",
            "scope_gate": "PASS",
            "phase02_completion_gate": "PASS",
            "dataset_manifest_sha256": _sha256(manifest_path),
            "files": len(manifest_files),
            "rows": total_rows,
            "completed_at_utc": "2026-01-01T00:00:00Z",
        },
    )

    state_path = work / "phase02_state.sqlite3"
    _write_completed_state(state_path, entries, manifest_files)

    reports = tmp_path / "ingestion_reports"
    reports.mkdir(mode=0o700)
    total_parquet_bytes = sum(item["output_size_bytes"] for item in manifest_files)
    _write_json(
        reports / "phase02_run.json",
        {
            "run_id": RUN_ID,
            "run_scope": "FULL_CONVERSION",
            "status": "COMPLETED_SCOPE_PASS",
            "scope_gate": "PASS",
            "phase02_completion_gate": "PASS",
            "git_commit": INGESTION_COMMIT[:8],
            "git_dirty": False,
            "phase01_run_id": source_inventory_bundle.run_id,
            "phase01_input_manifest_sha256": SOURCE_INVENTORY_MANIFEST_DIGEST,
            "configuration": {
                "source_schema_version": SOURCE_SCHEMA_VERSION,
                "parser_version": PARSER_VERSION,
                "staging_version": STAGING_VERSION,
                "semantic_digest_version": SEMANTIC_DIGEST_VERSION,
                "stable_row_id_version": STABLE_ROW_ID_VERSION,
                "schema_fingerprint": schema_fingerprint(),
            },
            "configuration_fingerprint": CONFIGURATION_DIGEST,
            "implementation_fingerprint": IMPLEMENTATION_DIGEST,
            "metrics": {
                "source_bytes": sum(
                    record.file_size_bytes for record in inventory_records
                ),
                "parquet_bytes": total_parquet_bytes,
            },
        },
    )
    _write_json(
        reports / "phase02_schema.json",
        {
            "schema_version": "phase02_arrow_schema_v1",
            "schema_fingerprint": schema_fingerprint(),
            "fields": [
                {
                    "position": index,
                    "name": field.name,
                    "type": str(field.type),
                    "nullable": field.nullable,
                }
                for index, field in enumerate(base_staging_schema(), start=1)
            ],
        },
    )
    _write_json(reports / "phase02_reconciliation.json", reconciliation)
    with (reports / "phase02_file_validation.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=FILE_VALIDATION_COLUMNS)
        writer.writeheader()
        writer.writerows(_file_report_row(RUN_ID, item) for item in manifest_files)
    with gzip.open(
        reports / "phase02_failures.csv.gz", "wt", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("run_id", "relative_path", "failure_code", "failure_detail"),
        )
        writer.writeheader()
    (reports / "phase02_summary.md").write_text(
        "# Fictional Stage 1 PASS\n", encoding="utf-8"
    )
    for name in REPORT_NAMES:
        (reports / name).chmod(0o600)

    return SyntheticBundle(
        stage00_record=stage00_record,
        stage00_record_sha256=_sha256(stage00_record),
        source_inventory_run=source_inventory_run,
        source_inventory_bundle=source_inventory_bundle,
        ingestion_run=ingestion_run,
        ingestion_reports=reports,
        output=tmp_path / "stage01",
        manifest=manifest,
    )


def _validate(bundle: SyntheticBundle) -> s01.ValidatedStage01Bundle:
    return validate_stage01_bundle(
        bundle.ingestion_run,
        bundle.ingestion_reports,
        bundle.source_inventory_run,
        bundle.stage00_record,
        expected_stage00_adoption_sha256=bundle.stage00_record_sha256,
        expected_source_population_sha256=SOURCE_POPULATION_DIGEST,
        expected_scientific_inventory_sha256=SCIENTIFIC_INVENTORY_DIGEST,
        expected_parser_contract_fingerprint=PARSER_CONTRACT_DIGEST,
        expected_ingestion_run_id=RUN_ID,
        expected_ingestion_producing_git_commit=INGESTION_COMMIT,
        production=False,
    )


def _adopt(bundle: SyntheticBundle) -> s01.Stage01AdoptionOutcome:
    return adopt_stage01_bundle(
        bundle.ingestion_run,
        bundle.ingestion_reports,
        bundle.source_inventory_run,
        bundle.stage00_record,
        bundle.output,
        expected_stage00_adoption_sha256=bundle.stage00_record_sha256,
        expected_source_population_sha256=SOURCE_POPULATION_DIGEST,
        expected_scientific_inventory_sha256=SCIENTIFIC_INVENTORY_DIGEST,
        expected_parser_contract_fingerprint=PARSER_CONTRACT_DIGEST,
        expected_ingestion_run_id=RUN_ID,
        expected_ingestion_producing_git_commit=INGESTION_COMMIT,
        adopting_git_commit=ADOPTING_COMMIT,
        adopting_git_dirty=False,
        production=False,
        adoption_timestamp_utc="2026-01-02T00:00:00Z",
        operational_metadata={
            "hostname": "fictional-host",
            "slurm_job_id": "fictional",
        },
    )


def test_resolve_stage00_binding_uses_hash_pinned_accepted_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _synthetic_bundle(tmp_path, monkeypatch)
    binding = s01.resolve_stage00_binding(
        bundle.stage00_record,
        bundle.source_inventory_run,
        expected_stage00_adoption_sha256=bundle.stage00_record_sha256,
    )
    assert binding.adoption_record.sha256 == bundle.stage00_record_sha256
    assert binding.source_population_sha256_v1 == SOURCE_POPULATION_DIGEST
    assert tuple(
        record.relative_path for record in binding.source_inventory_bundle.records
    ) == (
        "fictional_a.csv",
        "fictional_b.csv",
    )
    with pytest.raises(s01.Stage01ValidationError, match="ARTIFACT_SHA256_MISMATCH"):
        s01.resolve_stage00_binding(
            bundle.stage00_record,
            bundle.source_inventory_run,
            expected_stage00_adoption_sha256="0" * 64,
        )


def _independent_logical_digest(records: list[Stage01SourceRecord]) -> str:
    def u64(value: int) -> bytes:
        return b"\x01" + struct.pack(">Q", value)

    def text(value: str) -> bytes:
        encoded = value.encode("utf-8")
        return b"\x02" + struct.pack(">Q", len(encoded)) + encoded

    def digest(value: str) -> bytes:
        return b"\x03" + bytes.fromhex(value)

    ordered = sorted(records, key=lambda item: item.relative_path)
    payload = STAGE01_LOGICAL_DATASET_DOMAIN
    payload += text(STAGE01_CONTRACT_VERSION)
    payload += text(STAGE00_CONTRACT_VERSION)
    payload += text(INVENTORY_VERSION)
    payload += digest(SOURCE_POPULATION_DIGEST)
    payload += digest(SCIENTIFIC_INVENTORY_DIGEST)
    payload += digest(PARSER_CONTRACT_DIGEST)
    payload += text(PARSER_VERSION)
    payload += text(SOURCE_SCHEMA_VERSION)
    payload += text(STAGING_VERSION)
    payload += digest(schema_fingerprint())
    payload += text(STABLE_ROW_ID_VERSION)
    payload += text(SEMANTIC_DIGEST_VERSION)
    payload += u64(len(ordered))
    payload += u64(sum(record.logical_record_count for record in ordered))
    for record in ordered:
        payload += text(record.relative_path)
        payload += digest(record.source_file_sha256)
        payload += u64(record.logical_record_count)
        payload += digest(record.raw_semantic_digest_v1)
    return hashlib.sha256(payload).hexdigest()


def test_logical_dataset_fingerprint_golden_vector_and_layout_invariance(
    tmp_path: Path,
) -> None:
    records = [
        Stage01SourceRecord("fictional_b.csv", "b" * 64, 3, "d" * 64),
        Stage01SourceRecord("fictional_a.csv", "a" * 64, 2, "c" * 64),
    ]
    expected = "bc873ba0e080a7a8a2d28a680fa7533378a51be4f58415ba7309a0dc8716a948"
    assert _independent_logical_digest(records) == expected
    observed = stage01_logical_dataset_sha256_v1(
        records,
        stage00_source_population_sha256_v1=SOURCE_POPULATION_DIGEST,
        stage00_scientific_inventory_sha256_v1=SCIENTIFIC_INVENTORY_DIGEST,
        stage00_parser_contract_fingerprint=PARSER_CONTRACT_DIGEST,
    )
    assert observed == expected
    assert (
        stage01_logical_dataset_sha256_v1(
            list(reversed(records)),
            stage00_source_population_sha256_v1=SOURCE_POPULATION_DIGEST,
            stage00_scientific_inventory_sha256_v1=SCIENTIFIC_INVENTORY_DIGEST,
            stage00_parser_contract_fingerprint=PARSER_CONTRACT_DIGEST,
        )
        == observed
    )
    raw_rows = [
        ("fictional_a.csv", "a" * 64, _raw_row("1", "00123", "Example City")),
        ("fictional_a.csv", "a" * 64, _raw_row("2", "00124", "Example City")),
        ("fictional_b.csv", "b" * 64, _raw_row("3", "00125", "Example City")),
        ("fictional_b.csv", "b" * 64, _raw_row("4", "00126", "Example City")),
    ]
    columns: list[list[Any]] = [[] for _ in range(22)]
    ordinals = {"fictional_a.csv": 0, "fictional_b.csv": 0}
    for source_path, source_sha, raw in raw_rows:
        ordinals[source_path] += 1
        ordinal = ordinals[source_path]
        source_hash = bytes.fromhex(source_sha)
        values: tuple[Any, ...] = tuple(raw) + (
            source_path,
            ordinal,
            stable_source_row_id_v1(source_hash, ordinal),
            source_hash,
            SOURCE_SCHEMA_VERSION,
            PARSER_VERSION,
            STAGING_VERSION,
        )
        for target, value in zip(columns, values, strict=True):
            target.append(value)
    schema = base_staging_schema()
    table = pa.Table.from_arrays(
        [
            pa.array(values, type=field.type)
            for field, values in zip(schema, columns, strict=True)
        ],
        schema=schema,
    )
    one_shard = tmp_path / "all.parquet"
    pq.write_table(table, one_shard, row_group_size=4)
    multiple_shards = [tmp_path / "part-a.parquet", tmp_path / "part-b.parquet"]
    pq.write_table(table.slice(0, 2), multiple_shards[0], row_group_size=1)
    pq.write_table(table.slice(2, 2), multiple_shards[1], row_group_size=1)
    one_physical_identity = (_sha256(one_shard),)
    many_physical_identity = tuple(_sha256(path) for path in multiple_shards)
    assert one_physical_identity != many_physical_identity
    assert pq.read_table(one_shard).equals(table)
    assert pa.concat_tables([pq.read_table(path) for path in multiple_shards]).equals(
        table
    )
    layout_records = [
        Stage01SourceRecord(
            "fictional_a.csv",
            "a" * 64,
            2,
            _semantic_digest([raw_rows[0][2], raw_rows[1][2]]),
        ),
        Stage01SourceRecord(
            "fictional_b.csv",
            "b" * 64,
            2,
            _semantic_digest([raw_rows[2][2], raw_rows[3][2]]),
        ),
    ]
    layout_digest = stage01_logical_dataset_sha256_v1(
        layout_records,
        stage00_source_population_sha256_v1=SOURCE_POPULATION_DIGEST,
        stage00_scientific_inventory_sha256_v1=SCIENTIFIC_INVENTORY_DIGEST,
        stage00_parser_contract_fingerprint=PARSER_CONTRACT_DIGEST,
    )
    assert (
        stage01_logical_dataset_sha256_v1(
            list(reversed(layout_records)),
            stage00_source_population_sha256_v1=SOURCE_POPULATION_DIGEST,
            stage00_scientific_inventory_sha256_v1=SCIENTIFIC_INVENTORY_DIGEST,
            stage00_parser_contract_fingerprint=PARSER_CONTRACT_DIGEST,
        )
        == layout_digest
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("relative_path", "changed.csv"),
        ("source_file_sha256", "e" * 64),
        ("logical_record_count", 4),
        ("raw_semantic_digest_v1", "f" * 64),
    ],
)
def test_logical_fingerprint_changes_with_every_source_field(
    field: str, value: object
) -> None:
    base = Stage01SourceRecord("fictional.csv", "a" * 64, 2, "b" * 64)
    if field == "relative_path":
        changed = replace(base, relative_path=cast(str, value))
    elif field == "source_file_sha256":
        changed = replace(base, source_file_sha256=cast(str, value))
    elif field == "logical_record_count":
        changed = replace(base, logical_record_count=cast(int, value))
    else:
        changed = replace(base, raw_semantic_digest_v1=cast(str, value))

    def fingerprint(record: Stage01SourceRecord) -> str:
        return stage01_logical_dataset_sha256_v1(
            [record],
            stage00_source_population_sha256_v1=SOURCE_POPULATION_DIGEST,
            stage00_scientific_inventory_sha256_v1=SCIENTIFIC_INVENTORY_DIGEST,
            stage00_parser_contract_fingerprint=PARSER_CONTRACT_DIGEST,
        )

    assert fingerprint(changed) != fingerprint(base)


def test_logical_fingerprint_changes_with_accepted_population_size() -> None:
    first = Stage01SourceRecord("first.csv", "a" * 64, 2, "b" * 64)
    second = Stage01SourceRecord("second.csv", "c" * 64, 3, "d" * 64)

    def fingerprint(records: list[Stage01SourceRecord]) -> str:
        return stage01_logical_dataset_sha256_v1(
            records,
            stage00_source_population_sha256_v1=SOURCE_POPULATION_DIGEST,
            stage00_scientific_inventory_sha256_v1=SCIENTIFIC_INVENTORY_DIGEST,
            stage00_parser_contract_fingerprint=PARSER_CONTRACT_DIGEST,
        )

    assert fingerprint([first]) != fingerprint([first, second])


@pytest.mark.parametrize(
    "records",
    [
        [Stage01SourceRecord("nested/file.csv", "a" * 64, 1, "b" * 64)],
        [Stage01SourceRecord("fictional.csv", "A" * 64, 1, "b" * 64)],
        [Stage01SourceRecord("fictional.csv", "a" * 64, -1, "b" * 64)],
        [
            Stage01SourceRecord("a.csv", "a" * 64, 1, "c" * 64),
            Stage01SourceRecord("b.csv", "a" * 64, 1, "d" * 64),
        ],
    ],
)
def test_logical_fingerprint_rejects_malformed_or_duplicate_sources(
    records: list[Stage01SourceRecord],
) -> None:
    with pytest.raises(Stage01ValidationError):
        stage01_logical_dataset_sha256_v1(
            records,
            stage00_source_population_sha256_v1=SOURCE_POPULATION_DIGEST,
            stage00_scientific_inventory_sha256_v1=SCIENTIFIC_INVENTORY_DIGEST,
            stage00_parser_contract_fingerprint=PARSER_CONTRACT_DIGEST,
        )


def test_valid_adoption_is_source_free_private_and_sanitized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _synthetic_bundle(tmp_path, monkeypatch)
    outcome = _adopt(bundle)
    record = json.loads(outcome.adoption_record_path.read_text(encoding="utf-8"))
    assert record["status"] == "STAGE_1_ACCEPTED"
    assert record["scientific_identity"]["source_file_count"] == 2
    assert record["scientific_identity"]["total_row_count"] == 4
    assert record["validation"]["source_csv_access"] == "NOT_PERFORMED"
    assert all(
        record["validation"][key] == "PASS"
        for key in (
            "state_integrity",
            "state_manifest_reconciliation",
            "wal_checkpoint_state",
            "directory_topology",
        )
    )
    assert outcome.adoption_record_path.name == STAGE01_ADOPTION_RECORD_NAME
    assert outcome.output_directory.stat().st_mode & 0o777 == 0o700
    assert outcome.adoption_record_path.stat().st_mode & 0o777 == 0o600
    payload = outcome.adoption_record_path.read_bytes()
    for protected in (
        "Fictional Straße".encode(),
        "架空住所".encode(),
        b"Muenchen",
        b"0001",
    ):
        assert protected not in payload
    assert not hasattr(s01, "run_stage01")


def test_production_validation_requires_goethe_slurm_before_bundle_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    missing = tmp_path / "bundle-must-not-be-opened"
    with pytest.raises(ExecutionPolicyError, match="HEAVY_PROCESS_CLUSTER_REQUIRED"):
        validate_stage01_bundle(
            missing,
            missing,
            missing,
            missing,
            expected_stage00_adoption_sha256="0" * 64,
            expected_source_population_sha256="1" * 64,
            expected_scientific_inventory_sha256="2" * 64,
            expected_parser_contract_fingerprint="3" * 64,
            expected_ingestion_run_id=RUN_ID,
            expected_ingestion_producing_git_commit=INGESTION_COMMIT,
            production=True,
        )


@pytest.mark.parametrize(
    ("identity_key", "expected_code"),
    [
        ("source_population_sha256_v1", "STAGE00_IDENTITY_MISMATCH"),
        ("stage00_scientific_inventory_sha256_v1", "STAGE00_IDENTITY_MISMATCH"),
        ("parser_contract_fingerprint", "STAGE00_IDENTITY_MISMATCH"),
    ],
)
def test_stage00_fingerprint_mismatch_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    identity_key: str,
    expected_code: str,
) -> None:
    bundle = _synthetic_bundle(tmp_path, monkeypatch)
    record = json.loads(bundle.stage00_record.read_text(encoding="utf-8"))
    record["identity"][identity_key] = "0" * 64
    _write_json(bundle.stage00_record, record)
    bundle.stage00_record_sha256 = _sha256(bundle.stage00_record)
    with pytest.raises(Stage01ValidationError, match=expected_code):
        _validate(bundle)


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("path", "PHASE02_SOURCE_SCOPE_MISMATCH"),
        ("source_sha", "PHASE02_SOURCE_PROJECTION_MISMATCH"),
        ("logical_count", "PHASE02_SOURCE_PROJECTION_MISMATCH"),
        ("population", "PHASE02_SOURCE_SCOPE_MISMATCH"),
        ("semantic_digest", "PHASE02_SOURCE_PROJECTION_MISMATCH"),
        ("stable_uniqueness", "PHASE02_RECONCILIATION_FAILURE"),
    ],
)
def test_stage00_to_stage01_projection_and_reconciliation_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected_code: str,
) -> None:
    bundle = _synthetic_bundle(tmp_path, monkeypatch)
    if mutation == "path":
        bundle.manifest["files"][0]["source_file"] = "changed.csv"
    elif mutation == "source_sha":
        bundle.manifest["files"][0]["source_sha256"] = "0" * 64
    elif mutation == "logical_count":
        bundle.manifest["files"][0]["source_rows"] += 1
    elif mutation == "population":
        bundle.manifest["files"].pop()
    elif mutation == "semantic_digest":
        bundle.manifest["files"][0]["staging_semantic_digest"] = "0" * 64
    else:
        bundle.manifest["reconciliation"]["duplicate_stable_ids"] = 1
    _refresh_manifest_and_marker(bundle)
    with pytest.raises(Stage01ValidationError, match=expected_code):
        _validate(bundle)


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("missing_manifest", "MISSING_OR_UNSAFE_ARTIFACT"),
        ("malformed_manifest", "MALFORMED_PHASE02_MANIFEST"),
        ("tampered_manifest", "PHASE02_SUCCESS_MISMATCH"),
        ("missing_marker", "MISSING_OR_UNSAFE_ARTIFACT"),
        ("tampered_marker", "PHASE02_SUCCESS_MISMATCH"),
        ("unexpected_marker_field", "PHASE02_SUCCESS_SCHEMA_MISMATCH"),
        ("missing_shard", "PHASE02_SHARD_SET_MISMATCH"),
        ("unexpected_shard", "PHASE02_SHARD_SET_MISMATCH"),
        ("symlinked_shard", "UNSAFE_SHARD"),
        ("broken_symlinked_shard", "UNSAFE_SHARD"),
        ("special_shard", "UNSAFE_SHARD"),
        ("wrong_shard_size", "ARTIFACT_SIZE_MISMATCH"),
        ("same_size_shard_change", "ARTIFACT_SHA256_MISMATCH"),
        ("wrong_parquet_schema", "PARQUET_SCHEMA_MISMATCH"),
        ("wrong_parquet_row_count", "PARQUET_ROW_COUNT_MISMATCH"),
        ("wrong_configuration_identity", "PARQUET_METADATA_MISMATCH"),
        ("in_progress", "BUNDLE_IN_PROGRESS"),
        ("contradictory_marker", "CONTRADICTORY_TERMINAL_STATE"),
        ("permission", "PERMISSION_FAILURE"),
    ],
)
def test_physical_bundle_tampering_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected_code: str,
) -> None:
    bundle = _synthetic_bundle(tmp_path, monkeypatch)
    manifest_path = bundle.ingestion_run / "dataset_manifest.json"
    marker_path = bundle.ingestion_run / "_SUCCESS.json"
    shard = bundle.ingestion_run / bundle.manifest["files"][0]["output_file"]
    if mutation == "missing_manifest":
        manifest_path.unlink()
    elif mutation == "malformed_manifest":
        manifest_path.write_text("{", encoding="utf-8")
        manifest_path.chmod(0o600)
    elif mutation == "tampered_manifest":
        payload = manifest_path.read_bytes()
        manifest_path.write_bytes(payload + b" ")
        manifest_path.chmod(0o600)
    elif mutation == "missing_marker":
        marker_path.unlink()
    elif mutation == "tampered_marker":
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker["rows"] += 1
        _write_json(marker_path, marker)
    elif mutation == "unexpected_marker_field":
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker["unbound_claim"] = "PASS"
        _write_json(marker_path, marker)
    elif mutation == "missing_shard":
        shard.unlink()
    elif mutation == "unexpected_shard":
        extra = bundle.ingestion_run / "data/extra.parquet"
        extra.write_bytes(shard.read_bytes())
        extra.chmod(0o600)
    elif mutation == "symlinked_shard":
        replacement = tmp_path / "replacement.parquet"
        replacement.write_bytes(shard.read_bytes())
        replacement.chmod(0o600)
        shard.unlink()
        shard.symlink_to(replacement)
    elif mutation == "broken_symlinked_shard":
        shard.unlink()
        shard.symlink_to(bundle.ingestion_run / "absent.parquet")
    elif mutation == "special_shard":
        shard.unlink()
        os.mkfifo(shard, mode=0o600)
    elif mutation == "wrong_shard_size":
        shard.write_bytes(shard.read_bytes() + b"x")
        shard.chmod(0o600)
    elif mutation == "same_size_shard_change":
        changed_payload = bytearray(shard.read_bytes())
        changed_payload[len(changed_payload) // 2] ^= 1
        shard.write_bytes(changed_payload)
        shard.chmod(0o600)
    elif mutation == "wrong_parquet_schema":
        pq.write_table(pa.table({"wrong": ["schema"]}), shard)
        shard.chmod(0o600)
        bundle.manifest["files"][0]["output_size_bytes"] = shard.stat().st_size
        bundle.manifest["files"][0]["output_sha256"] = _sha256(shard)
        _refresh_manifest_and_marker(bundle)
    elif mutation == "wrong_parquet_row_count":
        item = bundle.manifest["files"][0]
        _write_parquet(
            shard,
            source_path=item["source_file"],
            source_sha256=item["source_sha256"],
            rows=[_raw_row("0001", "00123", "Fictional City")],
        )
        item["output_size_bytes"] = shard.stat().st_size
        item["output_sha256"] = _sha256(shard)
        _refresh_manifest_and_marker(bundle)
    elif mutation == "wrong_configuration_identity":
        bundle.manifest["configuration_fingerprint"] = "0" * 64
        _refresh_manifest_and_marker(bundle)
    elif mutation == "in_progress":
        pending = bundle.ingestion_run / ".in_progress/pending.tmp"
        pending.write_bytes(b"pending")
        pending.chmod(0o600)
    elif mutation == "contradictory_marker":
        _write_json(bundle.ingestion_run / "_FAILURE.json", {"status": "FAIL"})
    else:
        shard.chmod(0o640)
    with pytest.raises(Stage01ValidationError, match=expected_code):
        _validate(bundle)


def test_symlinked_stage01_run_directory_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _synthetic_bundle(tmp_path, monkeypatch)
    link = tmp_path / "stage01_run_link"
    link.symlink_to(bundle.ingestion_run, target_is_directory=True)
    bundle.ingestion_run = link
    with pytest.raises(Stage01ValidationError, match="INVALID_RUN_DIRECTORY"):
        _validate(bundle)


def test_schema_and_page_checksum_evidence_mismatch_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _synthetic_bundle(tmp_path, monkeypatch)
    schema_report = bundle.ingestion_reports / "phase02_schema.json"
    value = json.loads(schema_report.read_text(encoding="utf-8"))
    value["schema_fingerprint"] = "0" * 64
    _write_json(schema_report, value)
    with pytest.raises(Stage01ValidationError, match="SCHEMA_REPORT_MISMATCH"):
        _validate(bundle)

    other = tmp_path / "page-evidence"
    other.mkdir()
    bundle = _synthetic_bundle(other, monkeypatch)
    report = bundle.ingestion_reports / "phase02_file_validation.csv"
    with report.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    rows[0]["page_checksums_verified"] = "False"
    with report.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FILE_VALIDATION_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    report.chmod(0o600)
    with pytest.raises(Stage01ValidationError, match="FILE_REPORT_VALIDATION_MISMATCH"):
        _validate(bundle)


def test_extended_stage01_success_marker_is_validated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _synthetic_bundle(tmp_path, monkeypatch)
    marker_path = bundle.ingestion_run / "_SUCCESS.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker.update(
        {
            "git_commit": INGESTION_COMMIT,
            "source_bytes": sum(
                record.file_size_bytes
                for record in bundle.source_inventory_bundle.records
            ),
            "staging_bytes": sum(
                item["output_size_bytes"] for item in bundle.manifest["files"]
            ),
        }
    )
    _write_json(marker_path, marker)
    assert _validate(bundle).total_row_count == 4

    marker["staging_bytes"] += 1
    _write_json(marker_path, marker)
    with pytest.raises(Stage01ValidationError, match="PHASE02_SUCCESS_MISMATCH"):
        _validate(bundle)


def test_state_failure_and_output_collision_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _synthetic_bundle(tmp_path, monkeypatch)
    state = bundle.ingestion_run / "_work/phase02_state.sqlite3"
    connection = __import__("sqlite3").connect(state)
    connection.execute(
        "UPDATE file_state SET status='FAILED' WHERE relative_path='fictional_a.csv'"
    )
    connection.commit()
    connection.close()
    with pytest.raises(Stage01ValidationError, match="STATE_FILE_MISMATCH"):
        _validate(bundle)

    other = tmp_path / "second"
    other.mkdir()
    bundle = _synthetic_bundle(other, monkeypatch)
    bundle.output.mkdir()
    with pytest.raises(Stage01ValidationError, match="OUTPUT_COLLISION"):
        _adopt(bundle)


def test_state_validation_does_not_mutate_authoritative_sqlite_sidecars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _synthetic_bundle(tmp_path, monkeypatch)
    state = bundle.ingestion_run / "_work/phase02_state.sqlite3"
    shm = state.with_name(f"{state.name}-shm")
    shm.write_bytes(b"fictional sqlite shared-memory sidecar")
    shm.chmod(0o600)

    def identity(path: Path) -> tuple[int, int, int, int, int, str]:
        status = path.stat()
        return (
            status.st_dev,
            status.st_ino,
            status.st_size,
            status.st_mtime_ns,
            status.st_mode & 0o777,
            _sha256(path),
        )

    before = (identity(state), identity(shm))
    assert _validate(bundle).total_row_count == 4
    after = (identity(state), identity(shm))
    assert before == after


def test_uncheckpointed_state_wal_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _synthetic_bundle(tmp_path, monkeypatch)
    state = bundle.ingestion_run / "_work/phase02_state.sqlite3"
    wal = state.with_name(f"{state.name}-wal")
    wal.write_bytes(b"fictional uncheckpointed state")
    wal.chmod(0o600)
    with pytest.raises(Stage01ValidationError, match="STATE_NOT_CHECKPOINTED"):
        _validate(bundle)


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("output_sha", "STATE_FILE_MISMATCH"),
        ("output_size", "STATE_FILE_MISMATCH"),
        ("configuration", "STATE_FILE_MISMATCH"),
        ("run_meta", "STATE_META_MISMATCH"),
        ("attempt_history", "STATE_TERMINAL_MISMATCH"),
    ],
)
def test_state_manifest_and_terminal_evidence_must_reconcile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected_code: str,
) -> None:
    bundle = _synthetic_bundle(tmp_path, monkeypatch)
    state = bundle.ingestion_run / "_work/phase02_state.sqlite3"
    connection = __import__("sqlite3").connect(state)
    if mutation == "output_sha":
        connection.execute(
            "UPDATE file_state SET output_sha256=? WHERE relative_path=?",
            ("0" * 64, "fictional_a.csv"),
        )
    elif mutation == "output_size":
        connection.execute(
            "UPDATE file_state SET output_size_bytes=output_size_bytes+1 "
            "WHERE relative_path='fictional_a.csv'"
        )
    elif mutation == "configuration":
        connection.execute(
            "UPDATE file_state SET config_fingerprint=? "
            "WHERE relative_path='fictional_a.csv'",
            ("0" * 64,),
        )
    elif mutation == "run_meta":
        connection.execute(
            "UPDATE run_meta SET value=? WHERE key='run_id'", ("wrong-run",)
        )
    else:
        connection.execute(
            "UPDATE attempt_history SET terminal_status='FAILED', failure_code='X' "
            "WHERE relative_path='fictional_a.csv'"
        )
    connection.commit()
    connection.close()
    with pytest.raises(Stage01ValidationError, match=expected_code):
        _validate(bundle)


def test_duplicate_source_content_and_stable_id_policy_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _synthetic_bundle(tmp_path, monkeypatch)
    duplicate = replace(
        bundle.source_inventory_bundle.records[1],
        file_sha256=bundle.source_inventory_bundle.records[0].file_sha256,
    )
    bundle.source_inventory_bundle = replace(
        bundle.source_inventory_bundle,
        records=(bundle.source_inventory_bundle.records[0], duplicate),
    )
    monkeypatch.setattr(
        s01,
        "validate_stage00_inventory",
        lambda *_args, **_kwargs: bundle.source_inventory_bundle,
    )
    with pytest.raises(Stage01ValidationError, match="DUPLICATE_SOURCE_CONTENT"):
        _validate(bundle)

    source_hash = bytes.fromhex("a" * 64)
    assert stable_source_row_id_v1(source_hash, 1) == stable_source_row_id_v1(
        source_hash, 1
    )
    assert stable_source_row_id_v1(source_hash, 1) != stable_source_row_id_v1(
        source_hash, 2
    )
    assert stable_source_row_id_v1(bytes.fromhex("a" * 64), 1) != (
        stable_source_row_id_v1(bytes.fromhex("b" * 64), 1)
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "existing_marker",
        "new_shard",
        "new_work_file",
        "new_in_progress_file",
        "new_failure_marker",
        "new_report",
    ],
)
def test_bundle_mutation_before_publication_is_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    bundle = _synthetic_bundle(tmp_path, monkeypatch)
    original = s01._build_adoption_record

    def mutate(*args: Any, **kwargs: Any) -> dict[str, Any]:
        record = original(*args, **kwargs)
        if mutation == "existing_marker":
            marker = bundle.ingestion_run / "_SUCCESS.json"
            os.utime(
                marker, ns=(marker.stat().st_atime_ns, marker.stat().st_mtime_ns + 1)
            )
        elif mutation == "new_shard":
            added = bundle.ingestion_run / "data/late.parquet"
            added.write_bytes(b"late")
            added.chmod(0o600)
        elif mutation == "new_work_file":
            added = bundle.ingestion_run / "_work/late.state"
            added.write_bytes(b"late")
            added.chmod(0o600)
        elif mutation == "new_in_progress_file":
            added = bundle.ingestion_run / ".in_progress/late.tmp"
            added.write_bytes(b"late")
            added.chmod(0o600)
        elif mutation == "new_failure_marker":
            _write_json(bundle.ingestion_run / "_FAILURE.json", {"status": "FAIL"})
        else:
            added = bundle.ingestion_reports / "late_report.json"
            _write_json(added, {"status": "late"})
        return record

    monkeypatch.setattr(s01, "_build_adoption_record", mutate)
    with pytest.raises(Stage01ValidationError, match="BUNDLE_CHANGED_DURING_ADOPTION"):
        _adopt(bundle)
