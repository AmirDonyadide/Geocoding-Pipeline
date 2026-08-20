from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from safe_geocoding_pipeline.phase01.config import DEFAULT_PARSER_FIELD_LIMIT_CHARS
from safe_geocoding_pipeline.phase01.constants import INVENTORY_VERSION, REPORT_NAMES
from safe_geocoding_pipeline.phase01.reports import MANIFEST_COLUMNS
from safe_geocoding_pipeline.phase01.runner import TERMINAL_MARKER_TEXT
from safe_geocoding_pipeline.preprocessing.stages.s00_inventory import (
    ADOPTION_RECORD_NAME,
    Stage00InventoryRecord,
    Stage00ValidationError,
    adopt_phase01_bundle,
    harden_phase01_work_state,
    parser_contract_fingerprint_v1,
    source_population_sha256_v1,
    stage00_scientific_inventory_sha256_v1,
    validate_phase01_bundle,
)
from safe_geocoding_pipeline.raw_csv import (
    CSV_DELIMITER,
    CSV_DOUBLEQUOTE,
    CSV_ESCAPE_CHARACTER,
    CSV_NEWLINE,
    CSV_QUOTE_CHARACTER,
    CSV_SKIP_INITIAL_SPACE,
    CSV_STRICT,
    SOURCE_COLUMNS,
    SOURCE_ENCODING_POLICY,
)

PRODUCING_COMMIT = "a" * 40
ADOPTING_COMMIT = "b" * 40
SCHEMA_SHA256 = hashlib.sha256("\x1f".join(SOURCE_COLUMNS).encode()).hexdigest()


def _record(**changes: object) -> Stage00InventoryRecord:
    values: dict[str, object] = {
        "file_id": 1,
        "relative_path": "fictional_a.csv",
        "file_size_bytes": 123,
        "file_sha256": "1" * 64,
        "source_stable_during_scan": True,
        "encoding_status": "UTF8_VALID",
        "bom_type": "NONE",
        "header_present": True,
        "observed_column_count": len(SOURCE_COLUMNS),
        "schema_fingerprint": SCHEMA_SHA256,
        "schema_matches_contract": True,
        "logical_record_count": 3,
        "valid_schema_record_count": 3,
        "wrong_column_count_record_count": 0,
        "parser_error_count": 0,
        "multiline_record_count": 1,
        "counts_complete": True,
        "scan_status": "COMPLETE",
        "duplicate_file_group": None,
        "duplicate_file_group_size": 0,
        "max_record_length_chars": 80,
        "max_field_length_chars": 40,
    }
    values.update(changes)
    return Stage00InventoryRecord(**values)  # type: ignore[arg-type]


def _manifest_row(record: Stage00InventoryRecord, run_id: str) -> dict[str, object]:
    row: dict[str, object] = {column: "" for column in MANIFEST_COLUMNS}
    row.update(
        {
            "run_id": run_id,
            "file_id": record.file_id,
            "relative_path": record.relative_path,
            "file_name": record.relative_path,
            "size_bytes_before": record.file_size_bytes,
            "mtime_utc_before": "2000-01-01T00:00:00+00:00",
            "size_bytes_after_parse": record.file_size_bytes,
            "mtime_utc_after_parse": "2000-01-01T00:00:00+00:00",
            "size_bytes_after_hash": record.file_size_bytes,
            "mtime_utc_after_hash": "2000-01-01T00:00:00+00:00",
            "file_changed_during_scan": not record.source_stable_during_scan,
            "sha256": record.file_sha256,
            "duplicate_file_group": record.duplicate_file_group or "",
            "duplicate_file_group_size": record.duplicate_file_group_size,
            "duplicate_verification_method": (
                "SIZE_AND_SHA256" if record.duplicate_file_group else ""
            ),
            "bom_type": record.bom_type,
            "encoding_status": record.encoding_status,
            "delimiter": CSV_DELIMITER,
            "quote_character": CSV_QUOTE_CHARACTER,
            "doublequote": CSV_DOUBLEQUOTE,
            "escape_character": CSV_ESCAPE_CHARACTER or "",
            "header_present": record.header_present,
            "observed_column_count": record.observed_column_count,
            "schema_fingerprint": record.schema_fingerprint,
            "schema_matches_expected": record.schema_matches_contract,
            "logical_record_count": record.logical_record_count,
            "valid_schema_record_count": record.valid_schema_record_count,
            "empty_record_count": 0,
            "all_fields_empty_record_count": 0,
            "wrong_column_count_record_count": record.wrong_column_count_record_count,
            "parser_error_count": record.parser_error_count,
            "multiline_record_count": record.multiline_record_count,
            "max_physical_lines_per_record": 2,
            "max_record_length_chars": record.max_record_length_chars,
            "max_field_length_chars": record.max_field_length_chars,
            "id_nonempty_count": record.logical_record_count,
            "id_empty_count": 0,
            "id_distinct_within_file": record.logical_record_count,
            "id_duplicate_group_count_within_file": 0,
            "id_duplicate_occurrence_count_within_file": 0,
            "counts_complete": record.counts_complete,
            "scan_status": record.scan_status,
            "error_code": "",
            "duration_ms": 10,
        }
    )
    return row


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_manifest(
    run_dir: Path, run_id: str, records: list[Stage00InventoryRecord]
) -> None:
    with (run_dir / "phase01_file_manifest.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        writer.writerows(_manifest_row(record, run_id) for record in records)


def _refresh_run_metadata(run_dir: Path, records: list[Stage00InventoryRecord]) -> None:
    run_path = run_dir / "phase01_run.json"
    run: dict[str, Any]
    if run_path.exists():
        run = json.loads(run_path.read_text(encoding="utf-8"))
    else:
        run = {}
    run.update(
        {
            "run_id": run_dir.name,
            "inventory_version": INVENTORY_VERSION,
            "status": "COMPLETED_SCOPE_PASS",
            "scope_gate": "PASS",
            "phase01_completion_gate": "PASS",
            "run_scope": "FULL_INVENTORY",
            "git_commit": PRODUCING_COMMIT[:8],
            "git_dirty": False,
            "discovery_mode": "DIRECT_CSV_CHILDREN_NON_RECURSIVE_NO_SYMLINKS",
            "approved_input_files": [record.relative_path for record in records],
            "files_discovered": len(records),
            "total_size_bytes": sum(record.file_size_bytes for record in records),
            "parser_configuration": {
                "encoding": SOURCE_ENCODING_POLICY,
                "newline": CSV_NEWLINE,
                "delimiter": CSV_DELIMITER,
                "quotechar": CSV_QUOTE_CHARACTER,
                "doublequote": CSV_DOUBLEQUOTE,
                "escapechar": CSV_ESCAPE_CHARACTER,
                "skipinitialspace": CSV_SKIP_INITIAL_SPACE,
                "strict": CSV_STRICT,
            },
            "parser_limits": {"field_limit_chars": DEFAULT_PARSER_FIELD_LIMIT_CHARS},
            "output_files": {
                name: {
                    "size_bytes": (run_dir / name).stat().st_size,
                    "sha256": _sha256_file(run_dir / name),
                }
                for name in REPORT_NAMES
                if name != "phase01_run.json"
            },
        }
    )
    run_path.write_text(json.dumps(run, sort_keys=True), encoding="utf-8")


def _synthetic_bundle(
    tmp_path: Path, records: list[Stage00InventoryRecord] | None = None
) -> Path:
    selected = records or [_record()]
    run_dir = tmp_path / "phase01_fictional_bundle"
    run_dir.mkdir()
    _write_manifest(run_dir, run_dir.name, selected)
    for name in REPORT_NAMES:
        if name not in {"phase01_run.json", "phase01_file_manifest.csv"}:
            (run_dir / name).write_text(
                f"fictional artifact: {name}\n", encoding="utf-8"
            )
    _refresh_run_metadata(run_dir, selected)
    (run_dir / "_SCOPE_PASS").write_text(TERMINAL_MARKER_TEXT, encoding="utf-8")
    work = run_dir / "_work"
    work.mkdir(mode=0o755)
    database = work / "phase01.sqlite3"
    database.write_bytes(b"fictional protected ID state")
    work.chmod(0o755)
    database.chmod(0o644)
    return run_dir


def _validate(run_dir: Path, expected_file_count: int = 1) -> None:
    validate_phase01_bundle(
        run_dir,
        expected_file_count=expected_file_count,
        expected_producing_git_commit=PRODUCING_COMMIT,
    )


def test_source_population_and_scientific_fingerprints_have_golden_vectors() -> None:
    records = [
        _record(
            file_id=2,
            relative_path="fictional_b.csv",
            file_size_bytes=456,
            file_sha256="2" * 64,
        ),
        _record(),
    ]
    assert source_population_sha256_v1(records) == (
        "2f0a8f71fb9c19f9bd34b3e82380b1dfa7cd3f8fb10ecae3df78009b83776a6a"
    )
    assert parser_contract_fingerprint_v1() == (
        "c68895992f58afc7ef22d45ec3df21e49ff97339641d57559d9e961333c1feb9"
    )
    assert stage00_scientific_inventory_sha256_v1(records) == (
        "98527edb6f37f2cd33b51b43950f5ae62e45ee17690660c972b58c5b6c266ec4"
    )
    assert source_population_sha256_v1(
        list(reversed(records))
    ) == source_population_sha256_v1(records)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("relative_path", "changed.csv"),
        ("file_size_bytes", 124),
        ("file_sha256", "2" * 64),
        ("source_stable_during_scan", False),
        ("encoding_status", "UNKNOWN"),
        ("bom_type", "UTF8"),
        ("header_present", False),
        ("observed_column_count", 16),
        ("schema_fingerprint", "3" * 64),
        ("schema_matches_contract", False),
        ("logical_record_count", 4),
        ("valid_schema_record_count", 2),
        ("wrong_column_count_record_count", 1),
        ("parser_error_count", 1),
        ("multiline_record_count", 2),
        ("counts_complete", False),
        ("scan_status", "FAILED"),
        ("max_record_length_chars", 81),
        ("max_field_length_chars", 41),
    ],
)
def test_every_scalar_scientific_field_changes_inventory_digest(
    field: str, value: object
) -> None:
    base = _record()
    changed = _record(**{field: value})
    assert stage00_scientific_inventory_sha256_v1([changed]) != (
        stage00_scientific_inventory_sha256_v1([base])
    )


def test_nullable_duplicate_fields_and_contract_digest_change_inventory_digest() -> (
    None
):
    base = [
        _record(),
        _record(file_id=2, relative_path="fictional_b.csv"),
    ]
    grouped = [
        replace(
            record,
            duplicate_file_group="duplicate-file-0001",
            duplicate_file_group_size=2,
        )
        for record in base
    ]
    assert stage00_scientific_inventory_sha256_v1(grouped) != (
        stage00_scientific_inventory_sha256_v1(base)
    )
    alternate_parser = parser_contract_fingerprint_v1(
        parser_field_limit_chars=DEFAULT_PARSER_FIELD_LIMIT_CHARS + 1
    )
    assert stage00_scientific_inventory_sha256_v1(
        base, parser_contract_fingerprint=alternate_parser
    ) != stage00_scientific_inventory_sha256_v1(base)


@pytest.mark.parametrize(
    "record",
    [
        _record(file_sha256="A" * 64),
        _record(file_sha256="not-a-digest"),
        _record(file_size_bytes=-1),
        _record(relative_path="nested/file.csv"),
        _record(file_id=2),
    ],
)
def test_fingerprints_reject_malformed_or_noncanonical_inputs(
    record: Stage00InventoryRecord,
) -> None:
    with pytest.raises(Stage00ValidationError):
        source_population_sha256_v1([record])


def test_fingerprint_rejects_duplicate_paths() -> None:
    with pytest.raises(Stage00ValidationError, match="DUPLICATE_RELATIVE_PATH"):
        source_population_sha256_v1([_record(), _record(file_id=2)])


@pytest.mark.parametrize(
    "argument",
    ["parser_contract_fingerprint", "source_population_fingerprint"],
)
def test_scientific_fingerprint_rejects_explicit_invalid_digest(
    argument: str,
) -> None:
    with pytest.raises(Stage00ValidationError, match="INVALID_SHA256"):
        stage00_scientific_inventory_sha256_v1([_record()], **{argument: ""})


def test_valid_bundle_adoption_is_owner_only_and_operationally_invariant(
    tmp_path: Path,
) -> None:
    run_dir = _synthetic_bundle(tmp_path)
    first = adopt_phase01_bundle(
        run_dir,
        tmp_path / "adoption-one",
        expected_file_count=1,
        expected_producing_git_commit=PRODUCING_COMMIT,
        adopting_git_commit=ADOPTING_COMMIT,
        adopting_git_dirty=False,
        adoption_timestamp_utc="2026-01-01T00:00:00Z",
        operational_metadata={
            "hostname": "host-one",
            "slurm_job_id": "1",
            "duration": "2",
        },
    )
    second = adopt_phase01_bundle(
        run_dir,
        tmp_path / "adoption-two",
        expected_file_count=1,
        expected_producing_git_commit=PRODUCING_COMMIT,
        adopting_git_commit="c" * 40,
        adopting_git_dirty=True,
        adoption_timestamp_utc="2027-02-02T03:04:05Z",
        operational_metadata={
            "hostname": "host-two",
            "slurm_job_id": "9",
            "duration": "8",
        },
    )
    first_record = json.loads(first.adoption_record_path.read_text(encoding="utf-8"))
    second_record = json.loads(second.adoption_record_path.read_text(encoding="utf-8"))
    assert first_record["identity"] == second_record["identity"]
    assert first_record["provenance"] != second_record["provenance"]
    assert first.adoption_record_path.name == ADOPTION_RECORD_NAME
    assert first.output_directory.stat().st_mode & 0o777 == 0o700
    assert first.adoption_record_path.stat().st_mode & 0o777 == 0o600
    assert (run_dir / "_work").stat().st_mode & 0o777 == 0o700
    assert (run_dir / "_work/phase01.sqlite3").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    ("mutation", "error_code"),
    [
        ("missing_artifact", "MISSING_OR_UNSAFE_ARTIFACT"),
        ("tampered_artifact", "ARTIFACT_INTEGRITY_MISMATCH"),
        ("mismatched_size", "ARTIFACT_INTEGRITY_MISMATCH"),
        ("missing_success", "MISSING_SUCCESS_MARKER"),
        ("tampered_success", "INCONSISTENT_TERMINAL_STATE"),
        ("failure_marker", "INCONSISTENT_TERMINAL_STATE"),
        ("in_progress", "BUNDLE_IN_PROGRESS"),
        ("unsuccessful_row", "UNSUCCESSFUL_INVENTORY_ROW"),
        ("contract_mismatch", "PARSER_CONTRACT_MISMATCH"),
    ],
)
def test_bundle_validator_fails_closed(
    tmp_path: Path, mutation: str, error_code: str
) -> None:
    run_dir = _synthetic_bundle(tmp_path)
    if mutation == "missing_artifact":
        (run_dir / "phase01_schema_report.csv").unlink()
    elif mutation == "tampered_artifact":
        with (run_dir / "phase01_schema_report.csv").open(
            "a", encoding="utf-8"
        ) as stream:
            stream.write("tampered\n")
    elif mutation == "mismatched_size":
        run = json.loads((run_dir / "phase01_run.json").read_text(encoding="utf-8"))
        run["output_files"]["phase01_schema_report.csv"]["size_bytes"] += 1
        (run_dir / "phase01_run.json").write_text(json.dumps(run), encoding="utf-8")
    elif mutation == "missing_success":
        (run_dir / "_SCOPE_PASS").unlink()
    elif mutation == "tampered_success":
        (run_dir / "_SCOPE_PASS").write_text("tampered\n", encoding="utf-8")
    elif mutation == "failure_marker":
        (run_dir / "_SCOPE_FAIL").write_text("fail\n", encoding="utf-8")
    elif mutation == "in_progress":
        (run_dir / "_IN_PROGRESS").write_text("pending\n", encoding="utf-8")
    elif mutation == "unsuccessful_row":
        changed = [_record(scan_status="FAILED")]
        _write_manifest(run_dir, run_dir.name, changed)
        _refresh_run_metadata(run_dir, changed)
    elif mutation == "contract_mismatch":
        run = json.loads((run_dir / "phase01_run.json").read_text(encoding="utf-8"))
        run["parser_configuration"]["strict"] = False
        (run_dir / "phase01_run.json").write_text(json.dumps(run), encoding="utf-8")
    with pytest.raises(Stage00ValidationError, match=error_code):
        _validate(run_dir)


def test_bundle_validator_rejects_duplicate_paths(tmp_path: Path) -> None:
    records = [_record(), _record(file_id=2)]
    run_dir = _synthetic_bundle(tmp_path, records)
    with pytest.raises(Stage00ValidationError, match="DUPLICATE_RELATIVE_PATH"):
        _validate(run_dir, expected_file_count=2)


def test_bundle_validator_rejects_nonsequential_file_ids_and_row_order(
    tmp_path: Path,
) -> None:
    wrong_ids = [
        _record(file_id=2),
        _record(file_id=1, relative_path="fictional_b.csv", file_sha256="2" * 64),
    ]
    run_dir = _synthetic_bundle(tmp_path, wrong_ids)
    with pytest.raises(Stage00ValidationError, match="INVALID_FILE_ID"):
        _validate(run_dir, expected_file_count=2)

    other_root = tmp_path / "other"
    other_root.mkdir()
    wrong_order = [
        _record(file_id=1, relative_path="fictional_b.csv", file_sha256="2" * 64),
        _record(file_id=2),
    ]
    second = _synthetic_bundle(other_root, wrong_order)
    with pytest.raises(Stage00ValidationError, match="MANIFEST_ORDER_MISMATCH"):
        _validate(second, expected_file_count=2)


def test_bundle_validator_rejects_manifest_schema_change(tmp_path: Path) -> None:
    run_dir = _synthetic_bundle(tmp_path)
    manifest = run_dir / "phase01_file_manifest.csv"
    content = manifest.read_text(encoding="utf-8")
    manifest.write_text(
        content.replace("file_id", "changed_file_id", 1), encoding="utf-8"
    )
    _refresh_run_metadata(run_dir, [_record()])
    with pytest.raises(Stage00ValidationError, match="MANIFEST_SCHEMA_MISMATCH"):
        _validate(run_dir)


def test_adoption_output_collision_is_fail_closed(tmp_path: Path) -> None:
    run_dir = _synthetic_bundle(tmp_path)
    output = tmp_path / "adoption"
    output.mkdir()
    with pytest.raises(Stage00ValidationError, match="OUTPUT_COLLISION"):
        adopt_phase01_bundle(
            run_dir,
            output,
            expected_file_count=1,
            expected_producing_git_commit=PRODUCING_COMMIT,
            adopting_git_commit=ADOPTING_COMMIT,
            adopting_git_dirty=False,
        )


def test_permission_hardening_does_not_touch_source_and_rejects_symlinks(
    tmp_path: Path,
) -> None:
    run_dir = _synthetic_bundle(tmp_path)
    fictional_source = tmp_path / "fictional-source.csv"
    fictional_source.write_text("fictional source\n", encoding="utf-8")
    fictional_source.chmod(0o644)
    harden_phase01_work_state(run_dir)
    assert fictional_source.stat().st_mode & 0o777 == 0o644

    unsafe = run_dir / "_work/unsafe-link"
    unsafe.symlink_to(fictional_source)
    (run_dir / "_work").chmod(0o755)
    with pytest.raises(Stage00ValidationError, match="UNSAFE_WORK_STATE_SYMLINK"):
        harden_phase01_work_state(run_dir)
    assert (run_dir / "_work").stat().st_mode & 0o777 == 0o755


def test_adoption_record_does_not_copy_fictional_protected_values(
    tmp_path: Path,
) -> None:
    run_dir = _synthetic_bundle(tmp_path)
    protected_values = ("fictional raw ID secret", "fictional address secret")
    with (run_dir / "_work/phase01.sqlite3").open("ab") as stream:
        stream.write("|".join(protected_values).encode())
    outcome = adopt_phase01_bundle(
        run_dir,
        tmp_path / "adoption",
        expected_file_count=1,
        expected_producing_git_commit=PRODUCING_COMMIT,
        adopting_git_commit=ADOPTING_COMMIT,
        adopting_git_dirty=False,
        adoption_timestamp_utc="2026-01-01T00:00:00Z",
    )
    portable = outcome.adoption_record_path.read_text(encoding="utf-8")
    assert all(value not in portable for value in protected_values)
    assert not (run_dir.parent / "source").exists()
