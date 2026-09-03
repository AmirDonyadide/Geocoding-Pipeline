from __future__ import annotations

import hashlib
import re
import resource
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ...execution_policy import require_goethe_nhr_slurm
from ...raw_csv import (
    CSV_DELIMITER,
    CSV_DOUBLEQUOTE,
    CSV_ESCAPE_CHARACTER,
    CSV_NEWLINE,
    CSV_QUOTE_CHARACTER,
    CSV_SKIP_INITIAL_SPACE,
    CSV_STRICT,
    SOURCE_ENCODING_POLICY,
)
from .s00_config import InventoryConfig
from .s00_constants import INVENTORY_VERSION
from .s00_discovery import discover_source_files
from .s00_models import FileMetadata, FileResult, SourceFile
from .s00_parser import (
    append_terminal_anomaly,
    file_metadata,
    hash_file,
    scan_csv_file,
)
from .s00_population import PopulationScope, load_population_scope
from .s00_reports import atomic_json, write_reports
from .s00_store import IdStore

# These phase-prefixed run IDs, artifact filenames, and serialized keys are a
# frozen Stage 0 provenance format. They are retained only so accepted bundles
# remain verifiable; this module is the sole Stage 0 scanner implementation.
_RUN_ID_RE = re.compile(r"^phase01_[0-9]{8}T[0-9]{6}Z_[A-Za-z0-9._-]+$")
TERMINAL_MARKER_TEXT = "This marker describes only the configured run scope.\n"


@dataclass(frozen=True, slots=True)
class InventoryOutcome:
    run_id: str
    run_dir: Path
    status: str
    scope_gate: str
    stage00_completion_gate: str
    file_results: tuple[FileResult, ...]
    metrics: dict[str, float | int]


@dataclass(frozen=True, slots=True)
class _SourcePopulationSnapshot:
    relative_path: str
    device: int
    inode: int
    size_bytes: int
    mtime_ns: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "nogit"


def _git_dirty() -> bool | None:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            check=True,
            capture_output=True,
            text=True,
        )
        return bool(result.stdout)
    except (OSError, subprocess.CalledProcessError):
        return None


def generate_run_id(now: datetime | None = None, git_commit: str | None = None) -> str:
    timestamp = (now or _utc_now()).strftime("%Y%m%dT%H%M%SZ")
    return f"phase01_{timestamp}_{(git_commit or _git_commit())[:8]}"


def _peak_memory_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def _input_manifest_hash(files: list[SourceFile]) -> str:
    digest = hashlib.sha256()
    for source in files:
        metadata = file_metadata(source.path)
        digest.update(source.relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(metadata.size_bytes).encode("ascii"))
        digest.update(b"\0")
        digest.update(str(metadata.mtime_ns).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _same_metadata(*values: FileMetadata) -> bool:
    pairs = {(item.size_bytes, item.mtime_ns) for item in values}
    return len(pairs) == 1


def _validate_scope(
    config: InventoryConfig,
    files: list[SourceFile],
    population_scope: PopulationScope | None,
) -> None:
    if not files:
        raise ValueError("No source CSV files were selected")
    if config.run_scope == "SMOKE_TEST":
        if not config.include_files:
            raise ValueError("SMOKE_TEST requires explicit --include filenames")
        if len(files) > 2:
            raise ValueError(
                "SMOKE_TEST is limited to at most two explicitly selected files"
            )
    if config.run_scope == "FULL_INVENTORY":
        if population_scope is None:
            raise ValueError("FULL_INVENTORY requires an authorized population scope")
        if tuple(source.relative_path for source in files) != (
            population_scope.relative_paths
        ):
            raise ValueError(
                "FULL_INVENTORY source paths differ from the authorized population"
            )
        disk_probe = config.reports_root.resolve()
        while not disk_probe.exists() and disk_probe != disk_probe.parent:
            disk_probe = disk_probe.parent
        free_bytes = shutil.disk_usage(disk_probe).free
        if free_bytes < config.require_free_bytes:
            raise OSError(
                f"FULL_INVENTORY requires {config.require_free_bytes} free bytes; "
                f"only {free_bytes} are available"
            )


def _prepare_run_directory(config: InventoryConfig) -> tuple[str, Path, bool]:
    if config.resume_run_dir is not None:
        run_dir = config.resume_run_dir.resolve()
        run_id = run_dir.name
        if not _RUN_ID_RE.fullmatch(run_id):
            raise ValueError(
                f"Unsafe or invalid resumed run directory name: {run_id!r}"
            )
        if not run_dir.is_dir():
            raise FileNotFoundError(f"Resume run directory does not exist: {run_dir}")
        return run_id, run_dir, True

    run_id = config.run_id or generate_run_id()
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError(f"Invalid run ID: {run_id!r}")
    run_dir = (config.reports_root / run_id).resolve()
    if run_dir.exists():
        raise FileExistsError(f"Run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True, mode=0o700)
    run_dir.chmod(0o700)
    return run_id, run_dir, False


def _initial_payload(
    *,
    config: InventoryConfig,
    run_id: str,
    files: list[SourceFile],
    started_at: datetime,
    input_manifest_sha256: str,
    population_scope: PopulationScope | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "run_id": run_id,
        "inventory_version": INVENTORY_VERSION,
        "status": "IN_PROGRESS",
        "scope_gate": "NOT_EVALUATED",
        "phase01_completion_gate": "NOT_EVALUATED",
        "run_scope": config.run_scope,
        "started_at_utc": _iso_utc(started_at),
        "completed_at_utc": None,
        "git_commit": _git_commit(),
        "git_dirty": _git_dirty(),
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
        "source_root_label": config.portable_source_label,
        "discovery_mode": "DIRECT_CSV_CHILDREN_NON_RECURSIVE_NO_SYMLINKS",
        "approved_input_files": [source.relative_path for source in files],
        "files_discovered": len(files),
        "total_size_bytes": sum(source.path.stat().st_size for source in files),
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
        "warning_thresholds": {
            "field_warning_chars": config.field_warning_chars,
            "record_warning_chars": config.record_warning_chars,
        },
        "parser_limits": {"field_limit_chars": config.parser_field_limit_chars},
        "working_store_configuration": {
            "engine": "SQLite",
            "journal_mode": "WAL",
            "synchronous": "NORMAL",
            "foreign_keys": True,
            "temp_store": "FILE",
            "insertion_batch_size": config.insertion_batch_size,
        },
        "resume_information": {"resumed": False},
        "input_manifest_sha256": input_manifest_sha256,
        "output_files": {},
        "error_counts": {},
        "metrics": {},
    }
    if population_scope is not None:
        payload["authorized_population_scope"] = population_scope.provenance()
    return payload


def _source_population_snapshot(
    files: list[SourceFile],
) -> tuple[_SourcePopulationSnapshot, ...]:
    snapshots: list[_SourcePopulationSnapshot] = []
    for source in files:
        if source.path.is_symlink() or not source.path.is_file():
            raise OSError("Authorized source population contains an unsafe CSV entry")
        metadata = source.path.stat(follow_symlinks=False)
        snapshots.append(
            _SourcePopulationSnapshot(
                relative_path=source.relative_path,
                device=metadata.st_dev,
                inode=metadata.st_ino,
                size_bytes=metadata.st_size,
                mtime_ns=metadata.st_mtime_ns,
            )
        )
    return tuple(snapshots)


def _verify_authorized_population_unchanged(
    config: InventoryConfig,
    population_scope: PopulationScope,
    expected_snapshot: tuple[_SourcePopulationSnapshot, ...],
) -> None:
    assert config.population_scope_file is not None
    assert config.expected_population_scope_sha256 is not None
    observed_scope = load_population_scope(
        config.population_scope_file,
        expected_sha256=config.expected_population_scope_sha256,
        expected_parser_field_limit_chars=config.parser_field_limit_chars,
    )
    if observed_scope != population_scope:
        raise RuntimeError("Authorized population scope changed during inventory")
    observed_files = discover_source_files(
        config, authorized_relative_paths=population_scope.relative_paths
    )
    if _source_population_snapshot(observed_files) != expected_snapshot:
        raise RuntimeError("Authorized source population changed during inventory")


def _verify_resumable_completed_file(
    source: SourceFile, state: dict[str, object], config: InventoryConfig
) -> float:
    current = file_metadata(source.path)
    if (
        current.size_bytes != state["size_bytes"]
        or current.mtime_ns != state["mtime_ns"]
    ):
        raise RuntimeError(
            f"Completed source changed before resume: {source.relative_path}; start a new run"
        )
    digest, duration = hash_file(source.path, config.hash_chunk_bytes)
    if digest != state["sha256"]:
        raise RuntimeError(
            f"Completed source hash changed before resume: {source.relative_path}; start a new run"
        )
    return duration


def run_inventory(config: InventoryConfig) -> InventoryOutcome:
    if config.run_scope == "FULL_INVENTORY":
        require_goethe_nhr_slurm("stage00.full-inventory")
    config.validate()
    population_scope: PopulationScope | None = None
    if config.run_scope == "FULL_INVENTORY":
        assert config.population_scope_file is not None
        assert config.expected_population_scope_sha256 is not None
        population_scope = load_population_scope(
            config.population_scope_file,
            expected_sha256=config.expected_population_scope_sha256,
            expected_parser_field_limit_chars=config.parser_field_limit_chars,
        )
    files = discover_source_files(
        config,
        authorized_relative_paths=(
            population_scope.relative_paths if population_scope is not None else None
        ),
    )
    _validate_scope(config, files, population_scope)
    population_snapshot = _source_population_snapshot(files)
    run_id, run_dir, resumed = _prepare_run_directory(config)
    run_dir.chmod(0o700)
    work_dir = run_dir / "_work"
    anomaly_dir = work_dir / "anomalies"
    anomaly_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    work_dir.chmod(0o700)
    anomaly_dir.chmod(0o700)
    started_at = _utc_now()
    overall_started = time.perf_counter()
    input_manifest_sha256 = _input_manifest_hash(files)
    payload = _initial_payload(
        config=config,
        run_id=run_id,
        files=files,
        started_at=started_at,
        input_manifest_sha256=input_manifest_sha256,
        population_scope=population_scope,
    )
    payload["resume_information"] = {"resumed": resumed}

    parse_seconds = 0.0
    hash_seconds = 0.0
    spool_paths = {
        source.file_id: anomaly_dir / f"file_{source.file_id:06d}.csv"
        for source in files
    }

    store_path = work_dir / "stage00_inventory.sqlite3"
    with IdStore(store_path) as store:
        expected_metadata = {
            "run_id": run_id,
            "inventory_version": INVENTORY_VERSION,
            "run_scope": config.run_scope,
            "input_manifest_sha256": input_manifest_sha256,
        }
        if population_scope is not None:
            expected_metadata.update(
                {
                    "population_scope_version": (
                        population_scope.population_scope_version
                    ),
                    "population_scope_sha256": population_scope.artifact_sha256,
                    "population_id": population_scope.population_id,
                    "population_expected_source_count": str(
                        population_scope.expected_source_count
                    ),
                }
            )
        if resumed:
            for key, value in expected_metadata.items():
                if store.get_meta(key) != value:
                    raise RuntimeError(f"Resumed run metadata mismatch: {key}")
        else:
            for key, value in expected_metadata.items():
                store.set_meta(key, value)
        store.prepare_files(files)
        states = store.file_states()

        marker = run_dir / "_IN_PROGRESS"
        (run_dir / "_SCOPE_PASS").unlink(missing_ok=True)
        (run_dir / "_SCOPE_FAIL").unlink(missing_ok=True)
        marker.write_text("Stage 0 inventory is in progress.\n", encoding="utf-8")
        marker.chmod(0o600)
        atomic_json(run_dir / "phase01_run.json", payload)

        for source in files:
            state = states[source.file_id]
            if state["status"] == "COMPLETE":
                hash_seconds += _verify_resumable_completed_file(source, state, config)
                continue

            before = file_metadata(source.path)
            store.mark_scanning(
                source, int(before.size_bytes or 0), int(before.mtime_ns or 0)
            )
            store.begin_file()
            result = FileResult(
                file_id=source.file_id,
                relative_path=source.relative_path,
                file_name=source.file_name,
                before=before,
                scan_status="SCANNING",
            )
            try:
                result = scan_csv_file(
                    config=config,
                    source=source,
                    store=store,
                    run_id=run_id,
                    anomaly_spool_path=spool_paths[source.file_id],
                    before=before,
                )
                parse_seconds += result.parse_duration_seconds
                result.after_parse = file_metadata(source.path)
                result.sha256, result.hash_duration_seconds = hash_file(
                    source.path, config.hash_chunk_bytes
                )
                hash_seconds += result.hash_duration_seconds
                result.after_hash = file_metadata(source.path)
                result.file_changed_during_scan = not _same_metadata(
                    result.before, result.after_parse, result.after_hash
                )
                if result.file_changed_during_scan:
                    result.error_code = "FILE_CHANGED_DURING_SCAN"
                    append_terminal_anomaly(
                        spool_path=spool_paths[source.file_id],
                        run_id=run_id,
                        source=source,
                        anomaly_type="FILE_CHANGED_DURING_SCAN",
                        domain="FILE",
                        observed="pre/post size or modification metadata changed",
                    )

                successful = (
                    result.counts_complete
                    and result.schema_matches_expected
                    and result.wrong_column_count_record_count == 0
                    and result.parser_error_count == 0
                    and not result.file_changed_during_scan
                )
                if successful:
                    result.scan_status = "COMPLETE"
                    store.commit_file_result(
                        result,
                        anomaly_spool_name=spool_paths[source.file_id].name,
                    )
                else:
                    store.rollback_file()
                    result.scan_status = "FAILED"
                    if not result.error_code:
                        result.error_code = (
                            "SCHEMA_DEVIATION"
                            if not result.schema_matches_expected
                            else "WRONG_COLUMN_COUNT"
                        )
            except (OSError, RuntimeError, ValueError) as error:
                store.rollback_file()
                result.scan_status = "FAILED"
                result.error_code = "UNEXPECTED_FILE_FAILURE"
                result.counts_complete = False
                try:
                    result.after_parse = file_metadata(source.path)
                    result.after_hash = result.after_parse
                except OSError:
                    pass
                append_terminal_anomaly(
                    spool_path=spool_paths[source.file_id],
                    run_id=run_id,
                    source=source,
                    anomaly_type="UNEXPECTED_FILE_FAILURE",
                    domain="FILE",
                    observed=type(error).__name__,
                )
            if result.scan_status != "COMPLETE":
                store.save_file_result(
                    result,
                    status="FAILED",
                    anomaly_spool_name=spool_paths[source.file_id].name,
                )

        results = store.load_results()
        store.checkpoint()
        sqlite_bytes = store.total_disk_bytes
        integrity = store.integrity_check()
        all_complete = (
            len(results) == len(files)
            and all(result.scan_status == "COMPLETE" for result in results)
            and integrity == "ok"
        )
        scope_gate = "PASS" if all_complete else "FAIL"
        stage00_gate = (
            scope_gate if config.run_scope == "FULL_INVENTORY" else "NOT_EVALUATED"
        )
        status = "COMPLETED_SCOPE_PASS" if all_complete else "COMPLETED_SCOPE_FAIL"
        completed_at = _utc_now()
        metrics: dict[str, float | int] = {
            "runtime_seconds": time.perf_counter() - overall_started,
            "csv_parse_seconds": parse_seconds,
            "hash_seconds": hash_seconds,
            "peak_memory_bytes": _peak_memory_bytes(),
            "sqlite_bytes": sqlite_bytes,
            "source_bytes": sum(result.before.size_bytes or 0 for result in results),
        }
        payload.update(
            {
                "status": status,
                "scope_gate": scope_gate,
                "phase01_completion_gate": stage00_gate,
                "completed_at_utc": _iso_utc(completed_at),
                "error_counts": {
                    "failed_files": sum(
                        result.scan_status != "COMPLETE" for result in results
                    ),
                    "parser_errors": sum(
                        result.parser_error_count for result in results
                    ),
                    "wrong_column_records": sum(
                        result.wrong_column_count_record_count for result in results
                    ),
                },
                "metrics": metrics,
                "working_store_integrity": integrity,
            }
        )
        if population_scope is not None:
            _verify_authorized_population_unchanged(
                config, population_scope, population_snapshot
            )
        write_reports(
            run_dir=run_dir,
            run_id=run_id,
            results=results,
            store=store,
            spool_paths=spool_paths,
            run_payload=payload,
            runtime_started=overall_started,
        )

    if population_scope is not None:
        _verify_authorized_population_unchanged(
            config, population_scope, population_snapshot
        )
    marker.unlink(missing_ok=True)
    terminal_marker = run_dir / (
        "_SCOPE_PASS" if scope_gate == "PASS" else "_SCOPE_FAIL"
    )
    terminal_marker.write_text(TERMINAL_MARKER_TEXT, encoding="utf-8")
    terminal_marker.chmod(0o600)
    return InventoryOutcome(
        run_id=run_id,
        run_dir=run_dir,
        status=status,
        scope_gate=scope_gate,
        stage00_completion_gate=stage00_gate,
        file_results=tuple(results),
        metrics=metrics,
    )
