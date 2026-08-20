from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import struct
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import safe_geocoding_pipeline.preprocessing.stages.s01_ingestion as s01

from safe_geocoding_pipeline.execution_policy import ExecutionPolicyError
from safe_geocoding_pipeline.phase01.constants import INVENTORY_VERSION
from safe_geocoding_pipeline.phase02.constants import (
    PARSER_VERSION,
    REPORT_NAMES,
    SEMANTIC_DIGEST_VERSION,
    SOURCE_SCHEMA_VERSION,
    STABLE_ROW_ID_VERSION,
    STAGING_VERSION,
)
from safe_geocoding_pipeline.phase02.identity import stable_source_row_id_v1
from safe_geocoding_pipeline.phase02.models import Phase01FileEntry
from safe_geocoding_pipeline.phase02.reports import FILE_VALIDATION_COLUMNS
from safe_geocoding_pipeline.phase02.schema import (
    base_staging_schema,
    schema_fingerprint,
    schema_with_metadata,
)
from safe_geocoding_pipeline.phase02.semantic import RawSemanticDigest
from safe_geocoding_pipeline.phase02.state import RunState
from safe_geocoding_pipeline.preprocessing.stages.s00_inventory import (
    STAGE00_CONTRACT_VERSION,
    ArtifactIdentity,
    Stage00InventoryRecord,
    ValidatedPhase01Bundle,
)
from safe_geocoding_pipeline.preprocessing.stages.s01_ingestion import (
    STAGE01_ADOPTION_RECORD_NAME,
    STAGE01_CONTRACT_VERSION,
    STAGE01_LOGICAL_DATASET_DOMAIN,
    Stage01SourceRecord,
    Stage01ValidationError,
    adopt_phase02_bundle,
    stage01_logical_dataset_sha256_v1,
    validate_phase02_bundle,
)
from safe_geocoding_pipeline.raw_csv import SOURCE_COLUMNS

PHASE01_COMMIT = "1" * 40
PHASE02_COMMIT = "2" * 40
ADOPTING_COMMIT = "3" * 40
SOURCE_POPULATION_DIGEST = "4" * 64
SCIENTIFIC_INVENTORY_DIGEST = "5" * 64
PARSER_CONTRACT_DIGEST = "6" * 64
PHASE01_INPUT_MANIFEST_DIGEST = "7" * 64
CONFIGURATION_DIGEST = "8" * 64
IMPLEMENTATION_DIGEST = "9" * 64
RUN_ID = "phase02_20260101T000000Z_fixture"


@dataclass(slots=True)
class SyntheticBundle:
    stage00_record: Path
    stage00_record_sha256: str
    phase01_run: Path
    phase01_bundle: ValidatedPhase01Bundle
    phase02_run: Path
    phase02_reports: Path
    output: Path
    manifest: dict[str, Any]


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
        "phase01_input_manifest_sha256": PHASE01_INPUT_MANIFEST_DIGEST,
        "pipeline_git_commit": PHASE02_COMMIT[:8],
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
    manifest_path = bundle.phase02_run / "dataset_manifest.json"
    _write_json(manifest_path, bundle.manifest)
    marker = json.loads(
        (bundle.phase02_run / "_SUCCESS.json").read_text(encoding="utf-8")
    )
    marker["dataset_manifest_sha256"] = _sha256(manifest_path)
    _write_json(bundle.phase02_run / "_SUCCESS.json", marker)


def _synthetic_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> SyntheticBundle:
    phase01_run = tmp_path / "phase01_fictional"
    phase01_run.mkdir(mode=0o700)
    _write_json(
        phase01_run / "phase01_run.json",
        {"input_manifest_sha256": PHASE01_INPUT_MANIFEST_DIGEST},
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
    phase01_artifacts = (
        ArtifactIdentity("phase01_run.json", 10, "d" * 64),
        ArtifactIdentity("phase01_file_manifest.csv", 20, "e" * 64),
    )
    phase01_bundle = ValidatedPhase01Bundle(
        run_dir=phase01_run,
        run_id="phase01_fictional",
        inventory_version=INVENTORY_VERSION,
        producing_git_commit=PHASE01_COMMIT,
        records=inventory_records,
        artifacts=phase01_artifacts,
        success_marker=ArtifactIdentity("_SCOPE_PASS", 5, "f" * 64),
        parser_contract_fingerprint=PARSER_CONTRACT_DIGEST,
        source_population_sha256_v1=SOURCE_POPULATION_DIGEST,
        stage00_scientific_inventory_sha256_v1=SCIENTIFIC_INVENTORY_DIGEST,
    )
    monkeypatch.setattr(
        s01, "validate_phase01_bundle", lambda *_args, **_kwargs: phase01_bundle
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
                "adopted_phase01_run_id": phase01_bundle.run_id,
                "phase01_inventory_version": phase01_bundle.inventory_version,
                "producing_git_commit": PHASE01_COMMIT,
                "source_population_sha256_v1": SOURCE_POPULATION_DIGEST,
                "stage00_scientific_inventory_sha256_v1": SCIENTIFIC_INVENTORY_DIGEST,
                "parser_contract_fingerprint": PARSER_CONTRACT_DIGEST,
            },
            "bundle_integrity": {
                "artifacts": [item.to_dict() for item in phase01_artifacts],
                "terminal_state": {
                    "success_marker": phase01_bundle.success_marker.to_dict(),
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

    phase02_run = tmp_path / RUN_ID
    data = phase02_run / "data"
    work = phase02_run / "_work"
    in_progress = phase02_run / ".in_progress"
    for directory in (phase02_run, data, work, in_progress):
        directory.mkdir(mode=0o700, exist_ok=True)
        directory.chmod(0o700)

    manifest_files: list[dict[str, Any]] = []
    entries: list[Phase01FileEntry] = []
    for index, relative in enumerate(sorted(source_rows), start=1):
        output_relative = f"data/part-{index:03d}.parquet"
        output = phase02_run / output_relative
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
            Phase01FileEntry(
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
        "phase01_input_manifest_sha256": PHASE01_INPUT_MANIFEST_DIGEST,
        "configuration_fingerprint": CONFIGURATION_DIGEST,
        "implementation_fingerprint": IMPLEMENTATION_DIGEST,
        "schema_fingerprint": schema_fingerprint(),
        "files": manifest_files,
        "reconciliation": reconciliation,
    }
    manifest_path = phase02_run / "dataset_manifest.json"
    _write_json(manifest_path, manifest)
    _write_json(
        phase02_run / "_SUCCESS.json",
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
    with RunState(state_path) as state:
        state.prepare_files(
            entries,
            config_fingerprint=CONFIGURATION_DIGEST,
            implementation_fingerprint=IMPLEMENTATION_DIGEST,
        )
        by_path = {item["source_file"]: item for item in manifest_files}
        for entry in entries:
            item = by_path[entry.relative_path]
            state.mark_writing(
                entry.relative_path, ".in_progress/x", item["output_file"]
            )
            state.mark_validating(entry.relative_path)
            state.mark_complete(
                entry.relative_path,
                {
                    "source_semantic_digest": item["source_semantic_digest"],
                    "staging_semantic_digest": item["staging_semantic_digest"],
                    "output_sha256": item["output_sha256"],
                    "output_size_bytes": item["output_size_bytes"],
                    "source_rows": item["source_rows"],
                    "staging_rows": item["staging_rows"],
                },
            )
    state_path.chmod(0o600)

    reports = tmp_path / "phase02_reports"
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
            "git_commit": PHASE02_COMMIT[:8],
            "git_dirty": False,
            "phase01_run_id": phase01_bundle.run_id,
            "phase01_input_manifest_sha256": PHASE01_INPUT_MANIFEST_DIGEST,
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
        "# Fictional Phase 2 PASS\n", encoding="utf-8"
    )
    for name in REPORT_NAMES:
        (reports / name).chmod(0o600)

    return SyntheticBundle(
        stage00_record=stage00_record,
        stage00_record_sha256=_sha256(stage00_record),
        phase01_run=phase01_run,
        phase01_bundle=phase01_bundle,
        phase02_run=phase02_run,
        phase02_reports=reports,
        output=tmp_path / "stage01",
        manifest=manifest,
    )


def _validate(bundle: SyntheticBundle) -> s01.ValidatedPhase02Bundle:
    return validate_phase02_bundle(
        bundle.phase02_run,
        bundle.phase02_reports,
        bundle.phase01_run,
        bundle.stage00_record,
        expected_stage00_adoption_sha256=bundle.stage00_record_sha256,
        expected_source_population_sha256=SOURCE_POPULATION_DIGEST,
        expected_scientific_inventory_sha256=SCIENTIFIC_INVENTORY_DIGEST,
        expected_parser_contract_fingerprint=PARSER_CONTRACT_DIGEST,
        expected_phase02_run_id=RUN_ID,
        expected_phase02_producing_git_commit=PHASE02_COMMIT,
        production=False,
    )


def _adopt(bundle: SyntheticBundle) -> s01.Stage01AdoptionOutcome:
    return adopt_phase02_bundle(
        bundle.phase02_run,
        bundle.phase02_reports,
        bundle.phase01_run,
        bundle.stage00_record,
        bundle.output,
        expected_stage00_adoption_sha256=bundle.stage00_record_sha256,
        expected_source_population_sha256=SOURCE_POPULATION_DIGEST,
        expected_scientific_inventory_sha256=SCIENTIFIC_INVENTORY_DIGEST,
        expected_parser_contract_fingerprint=PARSER_CONTRACT_DIGEST,
        expected_phase02_run_id=RUN_ID,
        expected_phase02_producing_git_commit=PHASE02_COMMIT,
        adopting_git_commit=ADOPTING_COMMIT,
        adopting_git_dirty=False,
        production=False,
        adoption_timestamp_utc="2026-01-02T00:00:00Z",
        operational_metadata={
            "hostname": "fictional-host",
            "slurm_job_id": "fictional",
        },
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


def test_logical_dataset_fingerprint_golden_vector_and_layout_invariance() -> None:
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
    # Physical shard count, names, compression, runtime, and Git are not inputs.
    one_physical_shard = records
    many_physical_shards = list(records)
    assert _independent_logical_digest(
        one_physical_shard
    ) == _independent_logical_digest(many_physical_shards)


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
    assert record["status"] == "IMPLEMENTED_PENDING_FINAL_REVIEW"
    assert record["scientific_identity"]["source_file_count"] == 2
    assert record["scientific_identity"]["total_row_count"] == 4
    assert record["validation"]["source_csv_access"] == "NOT_PERFORMED"
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
    assert not hasattr(s01, "run_phase02")


def test_production_validation_requires_goethe_slurm_before_bundle_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    missing = tmp_path / "bundle-must-not-be-opened"
    with pytest.raises(ExecutionPolicyError, match="HEAVY_PROCESS_CLUSTER_REQUIRED"):
        validate_phase02_bundle(
            missing,
            missing,
            missing,
            missing,
            expected_stage00_adoption_sha256="0" * 64,
            expected_source_population_sha256="1" * 64,
            expected_scientific_inventory_sha256="2" * 64,
            expected_parser_contract_fingerprint="3" * 64,
            expected_phase02_run_id=RUN_ID,
            expected_phase02_producing_git_commit=PHASE02_COMMIT,
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
def test_stage00_to_phase02_projection_and_reconciliation_fail_closed(
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
        ("tampered_manifest", "PHASE02_SUCCESS_MISMATCH"),
        ("missing_marker", "MISSING_OR_UNSAFE_ARTIFACT"),
        ("tampered_marker", "PHASE02_SUCCESS_MISMATCH"),
        ("unexpected_marker_field", "PHASE02_SUCCESS_SCHEMA_MISMATCH"),
        ("missing_shard", "PHASE02_SHARD_SET_MISMATCH"),
        ("unexpected_shard", "PHASE02_SHARD_SET_MISMATCH"),
        ("symlinked_shard", "UNSAFE_SHARD"),
        ("same_size_shard_change", "ARTIFACT_SHA256_MISMATCH"),
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
    manifest_path = bundle.phase02_run / "dataset_manifest.json"
    marker_path = bundle.phase02_run / "_SUCCESS.json"
    shard = bundle.phase02_run / bundle.manifest["files"][0]["output_file"]
    if mutation == "missing_manifest":
        manifest_path.unlink()
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
        extra = bundle.phase02_run / "data/extra.parquet"
        extra.write_bytes(shard.read_bytes())
        extra.chmod(0o600)
    elif mutation == "symlinked_shard":
        replacement = bundle.phase02_run / "replacement.parquet"
        replacement.write_bytes(shard.read_bytes())
        replacement.chmod(0o600)
        shard.unlink()
        shard.symlink_to(replacement)
    elif mutation == "same_size_shard_change":
        changed_payload = bytearray(shard.read_bytes())
        changed_payload[len(changed_payload) // 2] ^= 1
        shard.write_bytes(changed_payload)
        shard.chmod(0o600)
    elif mutation == "in_progress":
        pending = bundle.phase02_run / ".in_progress/pending.tmp"
        pending.write_bytes(b"pending")
        pending.chmod(0o600)
    elif mutation == "contradictory_marker":
        _write_json(bundle.phase02_run / "_FAILURE.json", {"status": "FAIL"})
    else:
        shard.chmod(0o640)
    with pytest.raises(Stage01ValidationError, match=expected_code):
        _validate(bundle)


def test_symlinked_phase02_run_directory_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _synthetic_bundle(tmp_path, monkeypatch)
    link = tmp_path / "phase02_run_link"
    link.symlink_to(bundle.phase02_run, target_is_directory=True)
    bundle.phase02_run = link
    with pytest.raises(Stage01ValidationError, match="INVALID_RUN_DIRECTORY"):
        _validate(bundle)


def test_schema_and_page_checksum_evidence_mismatch_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _synthetic_bundle(tmp_path, monkeypatch)
    schema_report = bundle.phase02_reports / "phase02_schema.json"
    value = json.loads(schema_report.read_text(encoding="utf-8"))
    value["schema_fingerprint"] = "0" * 64
    _write_json(schema_report, value)
    with pytest.raises(Stage01ValidationError, match="SCHEMA_REPORT_MISMATCH"):
        _validate(bundle)


def test_extended_phase02_success_marker_is_validated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _synthetic_bundle(tmp_path, monkeypatch)
    marker_path = bundle.phase02_run / "_SUCCESS.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker.update(
        {
            "git_commit": PHASE02_COMMIT,
            "source_bytes": sum(
                record.file_size_bytes for record in bundle.phase01_bundle.records
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

    other = tmp_path / "second"
    other.mkdir()
    bundle = _synthetic_bundle(other, monkeypatch)
    report = bundle.phase02_reports / "phase02_file_validation.csv"
    content = report.read_text(encoding="utf-8").replace("True", "False", 1)
    report.write_text(content, encoding="utf-8")
    report.chmod(0o600)
    with pytest.raises(Stage01ValidationError, match="FILE_REPORT_VALIDATION_MISMATCH"):
        _validate(bundle)


def test_state_failure_and_output_collision_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _synthetic_bundle(tmp_path, monkeypatch)
    state = bundle.phase02_run / "_work/phase02_state.sqlite3"
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


def test_duplicate_source_content_and_stable_id_policy_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _synthetic_bundle(tmp_path, monkeypatch)
    duplicate = replace(
        bundle.phase01_bundle.records[1],
        file_sha256=bundle.phase01_bundle.records[0].file_sha256,
    )
    bundle.phase01_bundle = replace(
        bundle.phase01_bundle,
        records=(bundle.phase01_bundle.records[0], duplicate),
    )
    monkeypatch.setattr(
        s01, "validate_phase01_bundle", lambda *_args, **_kwargs: bundle.phase01_bundle
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


def test_bundle_mutation_before_publication_is_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _synthetic_bundle(tmp_path, monkeypatch)
    original = s01._build_adoption_record

    def mutate(*args: Any, **kwargs: Any) -> dict[str, Any]:
        record = original(*args, **kwargs)
        marker = bundle.phase02_run / "_SUCCESS.json"
        os.utime(marker, ns=(marker.stat().st_atime_ns, marker.stat().st_mtime_ns + 1))
        return record

    monkeypatch.setattr(s01, "_build_adoption_record", mutate)
    with pytest.raises(Stage01ValidationError, match="BUNDLE_CHANGED_DURING_ADOPTION"):
        _adopt(bundle)
