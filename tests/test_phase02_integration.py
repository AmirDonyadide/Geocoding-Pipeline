from __future__ import annotations

import csv
import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from safe_geocoding_pipeline.phase01.parser import file_metadata
from safe_geocoding_pipeline.phase02.config import Phase02Config
from safe_geocoding_pipeline.phase02.constants import (
    DICTIONARY_COLUMNS,
    SOURCE_SCHEMA_VERSION,
    STATISTICS_COLUMNS,
)
from safe_geocoding_pipeline.phase02.conversion import (
    SENSITIVE_NO_STATISTICS,
    validate_temporary_parquet,
    write_source_to_temporary_parquet,
)
from safe_geocoding_pipeline.phase02.errors import Phase02FileError
from safe_geocoding_pipeline.phase02.models import (
    KnownExtreme,
    Phase01FileEntry,
    Phase01Manifest,
)
from safe_geocoding_pipeline.phase02.reconciliation import reconcile_completed_parquet
from safe_geocoding_pipeline.phase02.runner import run_phase02
from safe_geocoding_pipeline.phase02.runner import (
    _validate_source_paths,
    _validate_stage00_population,
    _verify_source_scope_unchanged,
    _verify_stage00_binding_unchanged,
)
from safe_geocoding_pipeline.phase02.state import RunState
from safe_geocoding_pipeline.preprocessing.stages.s00_inventory import (
    ArtifactIdentity,
    Stage00InventoryRecord,
    ValidatedPhase01Bundle,
)
from safe_geocoding_pipeline.preprocessing.stages.s01_ingestion import (
    Stage00Binding,
)
from safe_geocoding_pipeline.raw_csv import SOURCE_COLUMNS


def _raw_row(identifier: str, **overrides: str) -> list[str]:
    values = {column: "" for column in SOURCE_COLUMNS}
    values.update(
        {
            "id": identifier,
            "street_address_line_1": "Fictional Road 1",
            "postcode": "00123",
            "city": "Example City",
            "country_iso_code": "DE",
            "batch_priority": "1",
            "location_information": "fictional",
        }
    )
    values.update(overrides)
    return [values[column] for column in SOURCE_COLUMNS]


def _write_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(
            stream,
            delimiter=",",
            quotechar='"',
            doublequote=True,
            escapechar=None,
            lineterminator="\n",
        )
        writer.writerow(SOURCE_COLUMNS)
        writer.writerows(rows)


def _entry(path: Path, rows: int) -> Phase01FileEntry:
    metadata = file_metadata(path)
    assert metadata.size_bytes is not None
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return Phase01FileEntry(
        file_id=1,
        relative_path=path.name,
        file_name=path.name,
        size_bytes=metadata.size_bytes,
        mtime_utc=metadata.mtime_utc,
        sha256=digest,
        logical_record_count=rows,
        schema_fingerprint="f" * 64,
        bom_type="NONE",
    )


def _accepted_population(
    entries: list[Phase01FileEntry],
    *,
    input_manifest_sha256: str = "a" * 64,
) -> tuple[Phase01Manifest, Stage00Binding]:
    files = {entry.relative_path: entry for entry in entries}
    manifest = Phase01Manifest(
        run_id="phase01_test",
        input_manifest_sha256=input_manifest_sha256,
        files=files,
        extremes={},
    )
    records = tuple(
        Stage00InventoryRecord(
            file_id=entry.file_id,
            relative_path=entry.relative_path,
            file_size_bytes=entry.size_bytes,
            file_sha256=entry.sha256,
            source_stable_during_scan=True,
            encoding_status="UTF8_VALID",
            bom_type=entry.bom_type,
            header_present=True,
            observed_column_count=len(SOURCE_COLUMNS),
            schema_fingerprint=entry.schema_fingerprint,
            schema_matches_contract=True,
            logical_record_count=entry.logical_record_count,
            valid_schema_record_count=entry.logical_record_count,
            wrong_column_count_record_count=0,
            parser_error_count=0,
            multiline_record_count=0,
            counts_complete=True,
            scan_status="COMPLETE",
            duplicate_file_group=None,
            duplicate_file_group_size=0,
            max_record_length_chars=1,
            max_field_length_chars=1,
        )
        for entry in entries
    )
    bundle = ValidatedPhase01Bundle(
        run_dir=Path("/fictional/phase01_test"),
        run_id=manifest.run_id,
        inventory_version="phase01_v1",
        producing_git_commit="1" * 40,
        records=records,
        artifacts=(),
        success_marker=ArtifactIdentity("_SCOPE_PASS", 1, "2" * 64),
        parser_contract_fingerprint="3" * 64,
        source_population_sha256_v1="4" * 64,
        stage00_scientific_inventory_sha256_v1="5" * 64,
    )
    return manifest, Stage00Binding(
        adoption_record=ArtifactIdentity("stage00_adoption.json", 1, "6" * 64),
        phase01_bundle=bundle,
        phase01_input_manifest_sha256=input_manifest_sha256,
        source_population_sha256_v1="4" * 64,
        scientific_inventory_sha256_v1="5" * 64,
        parser_contract_fingerprint="3" * 64,
    )


def _config(tmp_path: Path, **overrides: Any) -> Phase02Config:
    values: dict[str, Any] = {
        "source_root": tmp_path,
        "phase01_run_dir": tmp_path,
        "normal_batch_rows": 2,
        "isolation_threshold_bytes": 1024,
        "duckdb_memory_limit": "512MB",
    }
    values.update(overrides)
    return Phase02Config(**values)


def _metadata(entry: Phase01FileEntry) -> dict[str, str]:
    return {
        "source_file": entry.relative_path,
        "source_file_sha256": entry.sha256,
        "source_schema_version": SOURCE_SCHEMA_VERSION,
    }


def _convert(
    tmp_path: Path,
    rows: list[list[str]],
    *,
    extremes: tuple[KnownExtreme, ...] = (),
) -> tuple[Path, Phase01FileEntry, Any, Any]:
    source = tmp_path / "fictional.csv"
    output = tmp_path / "fictional.parquet.tmp"
    _write_csv(source, rows)
    entry = _entry(source, len(rows))
    config = _config(tmp_path)
    source_result = write_source_to_temporary_parquet(
        source_path=source,
        temporary_path=output,
        entry=entry,
        extremes=extremes,
        config=config,
        file_metadata_values=_metadata(entry),
    )
    validation = validate_temporary_parquet(
        temporary_path=output,
        entry=entry,
        extremes=extremes,
        source_result=source_result,
        config=config,
        required_metadata=_metadata(entry),
    )
    return output, entry, source_result, validation


def _rewrite_table(path: Path, table: pa.Table) -> None:
    pq.write_table(
        table,
        path,
        version="1.0",
        data_page_version="1.0",
        compression="zstd",
        compression_level=3,
        use_dictionary=list(DICTIONARY_COLUMNS),
        write_statistics=list(STATISTICS_COLUMNS),
        write_page_checksum=True,
        row_group_size=2,
    )


@pytest.mark.parametrize("source_count", [1, 3, 7])
def test_full_conversion_accepts_variable_stage00_populations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_count: int,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    entries: list[Phase01FileEntry] = []
    for index in range(1, source_count + 1):
        source = source_root / f"fictional_{index:04d}.csv"
        _write_csv(source, [_raw_row(str(index))])
        entries.append(replace(_entry(source, 1), file_id=index))
    manifest, stage00 = _accepted_population(entries)
    monkeypatch.setattr(
        "safe_geocoding_pipeline.phase02.runner.require_goethe_nhr_slurm",
        lambda _: None,
    )
    monkeypatch.setattr(
        "safe_geocoding_pipeline.phase02.runner.resolve_stage00_binding",
        lambda *args, **kwargs: stage00,
    )
    monkeypatch.setattr(
        "safe_geocoding_pipeline.phase02.runner.load_phase01_manifest",
        lambda _: manifest,
    )
    outcome = run_phase02(
        _config(
            tmp_path,
            source_root=source_root,
            stage00_adoption_record=tmp_path / "stage00_adoption.json",
            expected_stage00_adoption_sha256=stage00.adoption_record.sha256,
            staging_root=tmp_path / "staging",
            reports_root=tmp_path / "reports",
            run_scope="FULL_CONVERSION",
            run_id=f"phase02_20260101T000000Z_generic{source_count}",
            require_free_bytes=0,
            authorize_full_conversion=True,
        )
    )
    assert outcome.scope_gate == "PASS"
    assert outcome.phase02_completion_gate == "PASS"
    assert outcome.reconciliation.file_count == source_count
    assert outcome.reconciliation.total_rows == source_count
    run = json.loads((outcome.report_run_dir / "phase02_run.json").read_text())
    accepted = run["configuration"]["accepted_stage00_population"]
    assert accepted["source_file_count"] == source_count
    assert accepted["stage00_adoption_record_sha256"] == stage00.adoption_record.sha256


@pytest.mark.parametrize(
    "mutation",
    ["expected_smaller", "expected_larger", "path", "sha", "logical_count"],
)
def test_stage00_phase01_projection_mismatches_fail_closed(
    tmp_path: Path, mutation: str
) -> None:
    entries: list[Phase01FileEntry] = []
    for index in range(1, 4):
        source = tmp_path / f"fictional_{index:04d}.csv"
        _write_csv(source, [_raw_row(str(index))])
        entries.append(replace(_entry(source, 1), file_id=index))
    manifest, stage00 = _accepted_population(entries)
    if mutation == "expected_smaller":
        _, stage00 = _accepted_population(entries[:2])
    elif mutation == "expected_larger":
        extra = replace(
            entries[-1],
            file_id=4,
            relative_path="fictional_0004.csv",
            file_name="fictional_0004.csv",
            sha256="9" * 64,
        )
        _, stage00 = _accepted_population([*entries, extra])
    elif mutation == "path":
        changed = replace(
            entries[-1],
            relative_path="different.csv",
            file_name="different.csv",
        )
        _, stage00 = _accepted_population([*entries[:-1], changed])
    elif mutation == "sha":
        changed = replace(entries[-1], sha256="9" * 64)
        _, stage00 = _accepted_population([*entries[:-1], changed])
    else:
        changed = replace(entries[-1], logical_record_count=2)
        _, stage00 = _accepted_population([*entries[:-1], changed])
    with pytest.raises(ValueError, match="accepted Stage 0"):
        _validate_stage00_population(phase01=manifest, stage00=stage00)


def test_exact_source_scope_rejects_missing_extra_and_late_arrival(
    tmp_path: Path,
) -> None:
    sources: list[Path] = []
    entries: list[Phase01FileEntry] = []
    for index in range(1, 3):
        source = tmp_path / f"fictional_{index:04d}.csv"
        _write_csv(source, [_raw_row(str(index))])
        sources.append(source)
        entries.append(replace(_entry(source, 1), file_id=index))
    initial = _validate_source_paths(tmp_path, entries, require_exact_scope=True)
    extra = tmp_path / "unexpected.csv"
    _write_csv(extra, [_raw_row("3")])
    with pytest.raises(ValueError, match="population differs"):
        _validate_source_paths(tmp_path, entries, require_exact_scope=True)
    with pytest.raises(RuntimeError, match="changed"):
        _verify_source_scope_unchanged(
            tmp_path, entries, initial, require_exact_scope=True
        )
    extra.unlink()
    sources[-1].unlink()
    with pytest.raises(ValueError, match="population differs"):
        _validate_source_paths(tmp_path, entries, require_exact_scope=True)


def test_stage00_control_bundle_change_during_run_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "fictional.csv"
    _write_csv(source, [_raw_row("1")])
    _, expected = _accepted_population([_entry(source, 1)])
    changed = replace(
        expected,
        adoption_record=replace(expected.adoption_record, sha256="7" * 64),
    )
    monkeypatch.setattr(
        "safe_geocoding_pipeline.phase02.runner.resolve_stage00_binding",
        lambda *args, **kwargs: changed,
    )
    with pytest.raises(RuntimeError, match="changed during Phase 2 execution"):
        _verify_stage00_binding_unchanged(
            _config(
                tmp_path,
                run_scope="FULL_CONVERSION",
                authorize_full_conversion=True,
                stage00_adoption_record=tmp_path / "stage00_adoption.json",
                expected_stage00_adoption_sha256=expected.adoption_record.sha256,
            ),
            expected,
        )


def test_historical_206_population_projection_remains_representable() -> None:
    entries = [
        Phase01FileEntry(
            file_id=index,
            relative_path=f"historical_{index:04d}.csv",
            file_name=f"historical_{index:04d}.csv",
            size_bytes=index,
            mtime_utc="2026-01-01T00:00:00Z",
            sha256=f"{index:064x}",
            logical_record_count=100_000,
            schema_fingerprint="f" * 64,
            bom_type="NONE",
        )
        for index in range(1, 207)
    ]
    manifest, stage00 = _accepted_population(entries)
    _validate_stage00_population(phase01=manifest, stage00=stage00)
    assert len(stage00.phase01_bundle.records) == 206


def test_lossless_synthetic_conversion_and_metadata_policy(tmp_path: Path) -> None:
    rows = [
        _raw_row(
            "0001",
            street_address_line_1='Fictional "Tower", North\nFloor 7',
            street_address_line_1_native="架空ビル七階",
            postcode="00123",
            batch_priority="Na",
            location_information="Null",
        ),
        _raw_row(
            "0002",
            street_address_line_2=".",
            street_address_line_2_native="-",
            postcode="123.0",
            city="München",
            country_iso_code="JP",
        ),
        _raw_row("0003", postcode="AB 1-2", city="東京"),
    ]
    output, entry, source_result, result = _convert(tmp_path, rows)
    assert result.status == "PASS"
    assert result.semantic_digest_match
    assert result.source_rows == result.staging_rows == 3
    assert result.raw_null_count == 0
    assert result.provenance_valid and result.stable_ids_valid
    assert result.stable_ids_distinct == 3
    assert result.page_checksums_verified
    assert result.row_group_rows == [2, 1]
    assert source_result.empty_counts == result.staging_empty_counts

    table = pq.read_table(output)
    for index, column in enumerate(SOURCE_COLUMNS):
        assert table[column].to_pylist() == [row[index] for row in rows]
    assert table["source_logical_record_number"].to_pylist() == [1, 2, 3]
    assert table["source_file_sha256"].to_pylist() == [bytes.fromhex(entry.sha256)] * 3
    parquet_file = pq.ParquetFile(output, page_checksum_verification=True)
    for row_group_index in range(parquet_file.metadata.num_row_groups):
        row_group = parquet_file.metadata.row_group(row_group_index)
        for column_index in range(row_group.num_columns):
            column = row_group.column(column_index)
            if column.path_in_schema in SENSITIVE_NO_STATISTICS:
                assert column.statistics is None
            if column.path_in_schema not in DICTIONARY_COLUMNS:
                assert "RLE_DICTIONARY" not in column.encodings


@pytest.mark.slow
def test_generated_known_scale_extreme_is_isolated_and_exact(tmp_path: Path) -> None:
    enormous = "X" * 19_413_972  # Known maximum character scale; fictional content.
    rows = [_raw_row("1"), _raw_row("2", street_address_line_1=enormous), _raw_row("3")]
    source = tmp_path / "fictional.csv"
    _write_csv(source, rows)
    expected = KnownExtreme(
        relative_path=source.name,
        logical_record_number=2,
        column_name="street_address_line_1",
        field_length_chars=len(enormous),
        value_sha256=hashlib.sha256(enormous.encode()).hexdigest(),
        physical_line_start=3,
        physical_line_end=3,
    )
    output, _, _, result = _convert(tmp_path, rows, extremes=(expected,))
    assert result.status == "PASS"
    assert result.isolated_record_count == 1
    assert result.row_group_rows == [1, 1, 1]
    assert (
        pq.read_table(output, columns=["street_address_line_1"])[0][1].as_py()
        == enormous
    )
    assert result.extreme_observations[0]["field_length_chars"] == len(enormous)
    assert result.extreme_observations[0]["field_length_utf8_bytes"] == len(
        enormous.encode()
    )


@pytest.mark.parametrize(
    ("mutation", "failure_code"),
    [
        ("value", "SEMANTIC_DIGEST_MISMATCH"),
        ("loss", "STAGING_ROW_COUNT_MISMATCH"),
        ("duplicate", "STAGING_ROW_COUNT_MISMATCH"),
        ("reorder", "SEMANTIC_DIGEST_MISMATCH"),
        ("null", "RAW_NULLS_PRESENT"),
    ],
)
def test_validation_detects_semantic_and_cardinality_damage(
    tmp_path: Path, mutation: str, failure_code: str
) -> None:
    output, entry, source_result, _ = _convert(
        tmp_path, [_raw_row("1"), _raw_row("2"), _raw_row("3")]
    )
    table = pq.read_table(output)
    if mutation == "value":
        table = table.set_column(
            1,
            table.schema.field(1),
            pa.array(["changed", "Fictional Road 1", "Fictional Road 1"]),
        )
    elif mutation == "loss":
        table = table.slice(0, 2)
    elif mutation == "duplicate":
        table = pa.concat_tables([table, table.slice(0, 1)])
    elif mutation == "reorder":
        table = table.take(pa.array([1, 0, 2]))
    else:
        values = table["city"].to_pylist()
        values[1] = None
        nullable_schema = pa.schema(
            [
                pa.field(field.name, field.type, nullable=True)
                if field.name == "city"
                else field
                for field in table.schema
            ],
            metadata=table.schema.metadata,
        )
        table = pa.Table.from_arrays(
            [
                pa.array(values, type=pa.string()) if name == "city" else table[name]
                for name in table.schema.names
            ],
            schema=nullable_schema,
        )
    damaged = tmp_path / f"{mutation}.parquet"
    _rewrite_table(damaged, table)
    with pytest.raises(Phase02FileError) as caught:
        validate_temporary_parquet(
            temporary_path=damaged,
            entry=entry,
            extremes=(),
            source_result=source_result,
            config=_config(tmp_path),
            required_metadata=_metadata(entry),
        )
    assert caught.value.code in {failure_code, "STAGING_SCHEMA_MISMATCH"}


def test_wrong_schema_source_change_and_corrupt_output_fail(tmp_path: Path) -> None:
    output, entry, source_result, _ = _convert(tmp_path, [_raw_row("1")])
    wrong = tmp_path / "wrong.parquet"
    pq.write_table(
        pq.read_table(output).drop(["city"]), wrong, write_page_checksum=True
    )
    with pytest.raises(Phase02FileError, match="STAGING_SCHEMA_MISMATCH"):
        validate_temporary_parquet(
            temporary_path=wrong,
            entry=entry,
            extremes=(),
            source_result=source_result,
            config=_config(tmp_path),
            required_metadata=_metadata(entry),
        )

    source = tmp_path / "fictional.csv"
    source.write_text(source.read_text(encoding="utf-8") + "changed", encoding="utf-8")
    with pytest.raises(Phase02FileError, match="SOURCE_IDENTITY_MISMATCH"):
        write_source_to_temporary_parquet(
            source_path=source,
            temporary_path=tmp_path / "changed.parquet",
            entry=entry,
            extremes=(),
            config=_config(tmp_path),
            file_metadata_values=_metadata(entry),
        )

    corrupt = tmp_path / "corrupt.parquet"
    corrupt.write_bytes(output.read_bytes()[:100])
    with pytest.raises(Phase02FileError, match="PARQUET_READ_OR_CHECKSUM_FAILURE"):
        validate_temporary_parquet(
            temporary_path=corrupt,
            entry=entry,
            extremes=(),
            source_result=source_result,
            config=_config(tmp_path),
            required_metadata=_metadata(entry),
        )


def test_phase1_modification_time_identity_is_enforced(tmp_path: Path) -> None:
    source = tmp_path / "fictional.csv"
    _write_csv(source, [_raw_row("1")])
    entry = _entry(source, 1)
    stat = source.stat()
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    with pytest.raises(Phase02FileError, match="SOURCE_IDENTITY_MISMATCH"):
        write_source_to_temporary_parquet(
            source_path=source,
            temporary_path=tmp_path / "changed-mtime.parquet",
            entry=entry,
            extremes=(),
            config=_config(tmp_path),
            file_metadata_values=_metadata(entry),
        )


def test_duckdb_exact_reconciliation(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first_output, first_entry, _, _ = _convert(
        first_dir, [_raw_row("1"), _raw_row("2")]
    )
    second_output, second_entry, _, _ = _convert(
        second_dir, [_raw_row("3"), _raw_row("4")]
    )
    data = tmp_path / "data"
    data.mkdir()
    first_final = data / Path(first_entry.file_name).with_suffix(".parquet")
    second_entry = Phase01FileEntry(
        file_id=2,
        relative_path="fictional_2.csv",
        file_name="fictional_2.csv",
        size_bytes=second_entry.size_bytes,
        mtime_utc=second_entry.mtime_utc,
        sha256=second_entry.sha256,
        logical_record_count=second_entry.logical_record_count,
        schema_fingerprint=second_entry.schema_fingerprint,
        bom_type=second_entry.bom_type,
    )
    second_final = data / "fictional_2.parquet"
    first_final.write_bytes(first_output.read_bytes())
    second_final.write_bytes(second_output.read_bytes())
    result = reconcile_completed_parquet(
        data_dir=data,
        entries=[first_entry, second_entry],
        memory_limit="512MB",
        spill_dir=tmp_path / "spill",
    )
    assert result.status == "PASS"
    assert result.total_rows == result.distinct_ids == result.distinct_stable_ids == 4
    assert result.empty_ids == 0
    assert result.to_dict()["empty_ids"] == 0


def test_duckdb_reconciliation_persists_empty_id_count(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    output, entry, _, _ = _convert(source_dir, [_raw_row(""), _raw_row("2")])
    data = tmp_path / "data"
    data.mkdir()
    final = data / Path(entry.file_name).with_suffix(".parquet")
    final.write_bytes(output.read_bytes())

    result = reconcile_completed_parquet(
        data_dir=data,
        entries=[entry],
        memory_limit="512MB",
        spill_dir=tmp_path / "spill",
    )

    assert result.status == "PASS"
    assert result.empty_ids == 1
    assert result.to_dict()["empty_ids"] == 1


def test_state_transitions_interruption_and_failure_history(tmp_path: Path) -> None:
    source = tmp_path / "fictional.csv"
    _write_csv(source, [_raw_row("1")])
    entry = _entry(source, 1)
    state_path = tmp_path / "state.sqlite3"
    with RunState(state_path) as state:
        state.prepare_files(
            [entry], config_fingerprint="c", implementation_fingerprint="i"
        )
        assert state.get(entry.relative_path)["status"] == "PENDING"
        assert (
            state.mark_writing(
                entry.relative_path, ".in_progress/a.tmp", "data/a.parquet"
            )
            == 1
        )
        assert state.get(entry.relative_path)["status"] == "WRITING"
    with RunState(state_path) as state:
        state.mark_failed(
            entry.relative_path, "INTERRUPTED_PREVIOUS_ATTEMPT", "safe detail"
        )
        assert state.get(entry.relative_path)["status"] == "FAILED"
        assert (
            state.mark_writing(
                entry.relative_path, ".in_progress/a.2.tmp", "data/a.parquet"
            )
            == 2
        )
        assert state.integrity_check() == "ok"


@pytest.mark.parametrize("field", ["sha256", "size_bytes", "logical_record_count"])
def test_resume_rejects_changed_source_population(tmp_path: Path, field: str) -> None:
    source = tmp_path / "fictional.csv"
    _write_csv(source, [_raw_row("1")])
    entry = _entry(source, 1)
    state_path = tmp_path / "state.sqlite3"
    with RunState(state_path) as state:
        state.prepare_files(
            [entry], config_fingerprint="c", implementation_fingerprint="i"
        )
    if field == "sha256":
        changed = replace(entry, sha256="9" * 64)
    elif field == "size_bytes":
        changed = replace(entry, size_bytes=entry.size_bytes + 1)
    else:
        changed = replace(entry, logical_record_count=entry.logical_record_count + 1)
    with RunState(state_path) as state:
        with pytest.raises(RuntimeError, match="source population"):
            state.prepare_files(
                [changed], config_fingerprint="c", implementation_fingerprint="i"
            )


def test_runner_atomic_promotion_scope_marker_and_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    source = source_root / "fictional.csv"
    private_fixture_value = "fictional-private-address-do-not-report"
    _write_csv(
        source,
        [_raw_row("1", street_address_line_1=private_fixture_value), _raw_row("2")],
    )
    entry = _entry(source, 2)
    manifest = Phase01Manifest(
        run_id="phase01_test",
        input_manifest_sha256="a" * 64,
        files={entry.relative_path: entry},
        extremes={},
    )
    monkeypatch.setattr(
        "safe_geocoding_pipeline.phase02.runner.load_phase01_manifest",
        lambda _: manifest,
    )
    config = _config(
        tmp_path,
        source_root=source_root,
        staging_root=tmp_path / "staging",
        reports_root=tmp_path / "reports",
        run_scope="TEST",
        include_files=(entry.relative_path,),
        run_id="phase02_20260101T000000Z_test",
    )
    outcome = run_phase02(config)
    assert outcome.scope_gate == "PASS"
    assert (outcome.staging_run_dir / "data/fictional.parquet").is_file()
    assert outcome.staging_run_dir.stat().st_mode & 0o777 == 0o700
    assert (
        outcome.staging_run_dir / "data/fictional.parquet"
    ).stat().st_mode & 0o777 == 0o600
    assert (
        outcome.staging_run_dir / "_work/phase02_state.sqlite3"
    ).stat().st_mode & 0o777 == 0o600
    assert (outcome.staging_run_dir / "_SCOPE_SUCCESS.json").is_file()
    assert not (outcome.staging_run_dir / "_SUCCESS.json").exists()
    marker = json.loads((outcome.staging_run_dir / "_SCOPE_SUCCESS.json").read_text())
    run_metadata = json.loads((outcome.report_run_dir / "phase02_run.json").read_text())
    reconciliation_report = json.loads(
        (outcome.report_run_dir / "phase02_reconciliation.json").read_text()
    )
    assert marker["git_commit"] == run_metadata["git_commit"]
    assert marker["source_bytes"] == outcome.metrics["source_bytes"]
    assert marker["staging_bytes"] == outcome.metrics["parquet_bytes"]
    assert reconciliation_report["empty_ids"] == 0
    assert not any((outcome.staging_run_dir / ".in_progress").iterdir())
    for report in outcome.report_run_dir.iterdir():
        if report.is_file():
            assert private_fixture_value.encode() not in report.read_bytes()

    resumed = run_phase02(
        _config(
            tmp_path,
            source_root=source_root,
            staging_root=tmp_path / "staging",
            reports_root=tmp_path / "reports",
            run_scope="TEST",
            include_files=(entry.relative_path,),
            resume_run_id=outcome.run_id,
        )
    )
    assert resumed.scope_gate == "PASS"


def test_failed_runner_has_no_success_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    source = source_root / "fictional.csv"
    _write_csv(source, [_raw_row("1")])
    entry = _entry(source, 1)
    source.write_text(source.read_text(encoding="utf-8") + "changed", encoding="utf-8")
    manifest = Phase01Manifest(
        run_id="phase01_test",
        input_manifest_sha256="b" * 64,
        files={entry.relative_path: entry},
        extremes={},
    )
    monkeypatch.setattr(
        "safe_geocoding_pipeline.phase02.runner.load_phase01_manifest",
        lambda _: manifest,
    )
    outcome = run_phase02(
        _config(
            tmp_path,
            source_root=source_root,
            staging_root=tmp_path / "staging",
            reports_root=tmp_path / "reports",
            run_scope="TEST",
            include_files=(entry.relative_path,),
            run_id="phase02_20260101T000000Z_failed",
        )
    )
    assert outcome.scope_gate == "FAIL"
    assert not (outcome.staging_run_dir / "_SCOPE_SUCCESS.json").exists()
    assert not (outcome.staging_run_dir / "_SUCCESS.json").exists()
    assert not any((outcome.staging_run_dir / "data").iterdir())


def test_report_failure_cannot_leave_success_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    source = source_root / "fictional.csv"
    _write_csv(source, [_raw_row("1")])
    entry = _entry(source, 1)
    manifest = Phase01Manifest(
        run_id="phase01_test",
        input_manifest_sha256="c" * 64,
        files={entry.relative_path: entry},
        extremes={},
    )
    monkeypatch.setattr(
        "safe_geocoding_pipeline.phase02.runner.load_phase01_manifest",
        lambda _: manifest,
    )

    def fail_reports(**_: Any) -> None:
        raise OSError("fictional report failure")

    monkeypatch.setattr(
        "safe_geocoding_pipeline.phase02.runner.write_all_reports", fail_reports
    )
    staging_root = tmp_path / "staging"
    run_id = "phase02_20260101T000000Z_reportfail"
    with pytest.raises(OSError, match="fictional report failure"):
        run_phase02(
            _config(
                tmp_path,
                source_root=source_root,
                staging_root=staging_root,
                reports_root=tmp_path / "reports",
                run_scope="TEST",
                include_files=(entry.relative_path,),
                run_id=run_id,
            )
        )
    staging_run = staging_root / run_id
    assert (staging_run / "dataset_manifest.json").is_file()
    assert not (staging_run / "_SCOPE_SUCCESS.json").exists()
    assert not (staging_run / "_SUCCESS.json").exists()


def test_failure_diagnostics_do_not_include_raw_values(tmp_path: Path) -> None:
    secret_value = "fictional-sensitive-address-value"
    source = tmp_path / "fictional.csv"
    _write_csv(source, [_raw_row("1", street_address_line_1=secret_value)])
    entry = _entry(source, 1)
    source.write_text(source.read_text(encoding="utf-8") + "x", encoding="utf-8")
    with pytest.raises(Phase02FileError) as caught:
        write_source_to_temporary_parquet(
            source_path=source,
            temporary_path=tmp_path / "out.parquet",
            entry=entry,
            extremes=(),
            config=_config(tmp_path),
            file_metadata_values=_metadata(entry),
        )
    assert secret_value not in str(caught.value)
