from __future__ import annotations

import json
import os
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

import duckdb
import pyarrow

from ..execution_policy import require_goethe_nhr_slurm
from ..phase01.parser import file_metadata, hash_file
from ..preprocessing.stages.s00_inventory import STAGE00_CONTRACT_VERSION
from ..preprocessing.stages.s01_ingestion import (
    Stage00Binding,
    resolve_stage00_binding,
)
from .config import Phase02Config
from .constants import (
    PARSER_VERSION,
    SEMANTIC_DIGEST_VERSION,
    SOURCE_SCHEMA_VERSION,
    STABLE_ROW_ID_VERSION,
    STAGING_VERSION,
)
from .conversion import (
    SourceWriteResult,
    validate_temporary_parquet,
    write_source_to_temporary_parquet,
)
from .errors import Phase02FileError
from .fingerprints import fingerprint, source_tree_fingerprint
from .manifest import load_phase01_manifest
from .models import (
    FileValidationResult,
    Phase01FileEntry,
    Phase01Manifest,
    Phase02Outcome,
)
from .reconciliation import reconcile_completed_parquet
from .reports import sha256_file, write_all_reports
from .schema import base_staging_schema, schema_fingerprint
from .state import RunState

_RUN_ID_RE = re.compile(r"^phase02_[0-9]{8}T[0-9]{6}Z_[A-Za-z0-9._-]+$")


@dataclass(frozen=True, slots=True)
class _SourceScopeSnapshot:
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
            ["git", "rev-parse", "--short=8", "HEAD"],
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


def _peak_rss_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def generate_run_id(now: datetime | None = None, git_commit: str | None = None) -> str:
    timestamp = (now or _utc_now()).strftime("%Y%m%dT%H%M%SZ")
    return f"phase02_{timestamp}_{git_commit or _git_commit()}"


def _directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _fsync_file_and_parent(path: Path) -> None:
    with path.open("rb") as stream:
        os.fsync(stream.fileno())
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _prepare_run_directories(config: Phase02Config) -> tuple[str, Path, Path, bool]:
    if config.resume_run_id is not None:
        run_id = config.resume_run_id
        if not _RUN_ID_RE.fullmatch(run_id):
            raise ValueError(f"Invalid resume run ID: {run_id!r}")
        staging_run = (config.staging_root / run_id).resolve()
        report_run = (config.reports_root / run_id).resolve()
        if not staging_run.is_dir() or not report_run.is_dir():
            raise FileNotFoundError(
                "Resume staging/report run directories must both exist"
            )
        return run_id, staging_run, report_run, True
    run_id = config.run_id or generate_run_id()
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError(f"Invalid run ID: {run_id!r}")
    staging_run = (config.staging_root / run_id).resolve()
    report_run = (config.reports_root / run_id).resolve()
    if staging_run.exists() or report_run.exists():
        raise FileExistsError(f"Run ID already exists: {run_id}")
    staging_run.mkdir(parents=True, mode=0o700)
    staging_run.chmod(0o700)
    report_run.mkdir(parents=True)
    return run_id, staging_run, report_run, False


def _select_entries(
    config: Phase02Config, files: dict[str, Phase01FileEntry]
) -> list[Phase01FileEntry]:
    if config.run_scope == "FULL_CONVERSION":
        selected = list(files.values())
    else:
        if not config.include_files:
            raise ValueError(
                f"{config.run_scope} requires explicit --include filenames"
            )
        missing = sorted(set(config.include_files) - set(files))
        if missing:
            raise FileNotFoundError(
                f"Selected files are absent from Phase 1 manifest: {missing}"
            )
        selected = [files[name] for name in config.include_files]
    return sorted(selected, key=lambda entry: entry.relative_path)


def _validate_stage00_population(
    *, phase01: Phase01Manifest, stage00: Stage00Binding
) -> None:
    if (
        phase01.run_id != stage00.phase01_bundle.run_id
        or phase01.input_manifest_sha256 != stage00.phase01_input_manifest_sha256
    ):
        raise ValueError("Accepted Stage 0 and Phase 1 run identities differ")
    expected = {
        record.relative_path: record for record in stage00.phase01_bundle.records
    }
    if set(phase01.files) != set(expected):
        raise ValueError("Phase 1 source path set differs from accepted Stage 0")
    for relative_path, entry in phase01.files.items():
        record = expected[relative_path]
        if (
            entry.file_id != record.file_id
            or entry.size_bytes != record.file_size_bytes
            or entry.sha256 != record.file_sha256
            or entry.logical_record_count != record.logical_record_count
            or entry.schema_fingerprint != record.schema_fingerprint
            or entry.bom_type != record.bom_type
        ):
            raise ValueError("Phase 1 source projection differs from accepted Stage 0")


def _validate_source_paths(
    source_root: Path,
    entries: list[Phase01FileEntry],
    *,
    require_exact_scope: bool,
) -> tuple[_SourceScopeSnapshot, ...]:
    root = source_root.resolve()
    if source_root.is_symlink() or not root.is_dir():
        raise FileNotFoundError(f"Source root is not a directory: {root}")
    observed: set[str] = set()
    with os.scandir(root) as children:
        for child in children:
            if not child.name.lower().endswith(".csv"):
                continue
            if child.is_symlink() or not child.is_file(follow_symlinks=False):
                raise FileNotFoundError(
                    "Source scope contains a non-regular or symlinked CSV entry"
                )
            observed.add(child.name)
    expected = {entry.relative_path for entry in entries}
    if require_exact_scope and observed != expected:
        raise ValueError(
            "Source directory CSV population differs from accepted Stage 0 scope"
        )
    snapshots: list[_SourceScopeSnapshot] = []
    for entry in entries:
        path = root / entry.relative_path
        if path.is_symlink() or not path.is_file() or path.parent != root:
            raise FileNotFoundError(
                f"Source is not a direct regular file: {entry.relative_path}"
            )
        stat = path.stat()
        snapshots.append(
            _SourceScopeSnapshot(
                relative_path=entry.relative_path,
                device=stat.st_dev,
                inode=stat.st_ino,
                size_bytes=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
            )
        )
    return tuple(sorted(snapshots, key=lambda item: item.relative_path))


def _verify_source_scope_unchanged(
    source_root: Path,
    entries: list[Phase01FileEntry],
    expected: tuple[_SourceScopeSnapshot, ...],
    *,
    require_exact_scope: bool,
) -> None:
    try:
        observed = _validate_source_paths(
            source_root, entries, require_exact_scope=require_exact_scope
        )
    except (OSError, ValueError) as error:
        raise RuntimeError(
            "Source population changed during Phase 2 execution"
        ) from error
    if observed != expected:
        raise RuntimeError("Source population changed during Phase 2 execution")


def _verify_stage00_binding_unchanged(
    config: Phase02Config, expected: Stage00Binding
) -> None:
    assert config.stage00_adoption_record is not None
    assert config.expected_stage00_adoption_sha256 is not None
    observed = resolve_stage00_binding(
        config.stage00_adoption_record,
        config.phase01_run_dir,
        expected_stage00_adoption_sha256=config.expected_stage00_adoption_sha256,
    )
    if observed != expected:
        raise RuntimeError(
            "Accepted Stage 0 population changed during Phase 2 execution"
        )


def _configuration_payload(
    config: Phase02Config, stage00: Stage00Binding | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "staging_version": STAGING_VERSION,
        "source_schema_version": SOURCE_SCHEMA_VERSION,
        "parser_version": PARSER_VERSION,
        "semantic_digest_version": SEMANTIC_DIGEST_VERSION,
        "stable_row_id_version": STABLE_ROW_ID_VERSION,
        "parser": {
            "encoding": "strict UTF-8 with Phase 1 BOM identity",
            "newline": "",
            "delimiter": ",",
            "quotechar": '"',
            "doublequote": True,
            "escapechar": None,
            "skipinitialspace": False,
            "strict": True,
            "field_limit_chars": config.parser_field_limit_chars,
        },
        "parquet": {
            "version": config.parquet_version,
            "data_page_version": config.data_page_version,
            "compression": config.compression,
            "compression_level": config.compression_level,
            "normal_batch_rows": config.normal_batch_rows,
            "normal_row_group_rows": config.normal_batch_rows,
            "isolation_threshold_bytes": config.isolation_threshold_bytes,
            "write_page_checksum": True,
        },
        "duckdb_memory_limit": config.duckdb_memory_limit,
        "schema_fingerprint": schema_fingerprint(),
    }
    if stage00 is not None:
        payload["accepted_stage00_population"] = {
            "stage00_contract_version": STAGE00_CONTRACT_VERSION,
            "stage00_adoption_record_sha256": stage00.adoption_record.sha256,
            "source_population_sha256_v1": stage00.source_population_sha256_v1,
            "stage00_scientific_inventory_sha256_v1": (
                stage00.scientific_inventory_sha256_v1
            ),
            "parser_contract_fingerprint": stage00.parser_contract_fingerprint,
            "phase01_run_id": stage00.phase01_bundle.run_id,
            "phase01_input_manifest_sha256": stage00.phase01_input_manifest_sha256,
            "source_file_count": len(stage00.phase01_bundle.records),
        }
    return payload


def _implementation_fingerprint() -> str:
    package_root = Path(__file__).resolve().parent
    raw_csv = package_root.parent / "raw_csv.py"
    return fingerprint(
        {
            "version": "phase02_implementation_identity_v1",
            "source_tree_sha256": source_tree_fingerprint((package_root, raw_csv)),
            "git_commit": _git_commit(),
            "dependencies": {
                "pyarrow": pyarrow.__version__,
                "duckdb": duckdb.__version__,
            },
        }
    )


def _parquet_metadata(
    *,
    run_id: str,
    entry: Phase01FileEntry,
    phase01_run_id: str,
    phase01_manifest_sha256: str,
    config_fingerprint: str,
    implementation_fingerprint: str,
) -> dict[str, str]:
    return {
        "phase02_run_id": run_id,
        "phase01_run_id": phase01_run_id,
        "phase01_input_manifest_sha256": phase01_manifest_sha256,
        "pipeline_git_commit": _git_commit(),
        "source_file": entry.relative_path,
        "source_file_sha256": entry.sha256,
        "source_schema_version": SOURCE_SCHEMA_VERSION,
        "parser_version": PARSER_VERSION,
        "staging_version": STAGING_VERSION,
        "semantic_digest_version": SEMANTIC_DIGEST_VERSION,
        "stable_source_row_id_version": STABLE_ROW_ID_VERSION,
        "configuration_fingerprint": config_fingerprint,
        "implementation_fingerprint": implementation_fingerprint,
        "pyarrow_version": pyarrow.__version__,
        "duckdb_version": duckdb.__version__,
    }


def _quarantine(temporary: Path, work_dir: Path) -> None:
    if not temporary.exists():
        return
    quarantine = work_dir / "quarantine"
    quarantine.mkdir(parents=True, exist_ok=True)
    target = quarantine / f"{temporary.name}.failed"
    if target.exists():
        target = quarantine / f"{temporary.name}.{time.time_ns()}.failed"
    os.replace(temporary, target)


def _quarantine_interrupted_attempt(
    *, state_row: dict[str, Any], staging_run: Path, in_progress: Path, work_dir: Path
) -> None:
    relative = str(state_row.get("temporary_path", ""))
    if not relative:
        return
    candidate = (staging_run / relative).resolve()
    if candidate.parent != in_progress.resolve():
        raise RuntimeError(
            "Interrupted temporary path escaped the approved .in_progress directory"
        )
    _quarantine(candidate, work_dir)


def _source_result_from_state(value: dict[str, Any]) -> SourceWriteResult:
    return SourceWriteResult(
        source_rows=int(value["source_rows"]),
        semantic_digest=str(value["source_semantic_digest"]),
        empty_counts=dict(value["source_empty_counts"]),
        non_ascii_counts=dict(value["source_non_ascii_counts"]),
        isolated_record_count=int(value["isolated_record_count"]),
        extreme_observations=list(value["extreme_observations"]),
        conversion_seconds=float(value["conversion_seconds"]),
        hashing_seconds=float(value["hashing_seconds"]),
        peak_temporary_bytes=int(value["peak_temporary_bytes"]),
    )


def _revalidate_complete(
    *,
    state_row: dict[str, Any],
    staging_run: Path,
    source_root: Path,
    entry: Phase01FileEntry,
    extremes: tuple[Any, ...],
    config: Phase02Config,
    metadata: dict[str, str],
) -> FileValidationResult:
    final_path = staging_run / str(state_row["final_path"])
    if (
        not final_path.is_file()
        or sha256_file(final_path) != state_row["output_sha256"]
    ):
        raise Phase02FileError(
            "COMPLETE_OUTPUT_IDENTITY_MISMATCH", "completed output hash changed"
        )
    source_path = source_root / entry.relative_path
    before = file_metadata(source_path)
    digest, _ = hash_file(source_path, config.hash_chunk_bytes)
    after = file_metadata(source_path)
    if (
        before.size_bytes != entry.size_bytes
        or before.mtime_utc != entry.mtime_utc
        or before.size_bytes != after.size_bytes
        or before.mtime_ns != after.mtime_ns
        or digest != entry.sha256
    ):
        raise Phase02FileError(
            "COMPLETE_SOURCE_IDENTITY_MISMATCH", "completed source identity changed"
        )
    prior = json.loads(str(state_row["validation_json"]))
    source_result = _source_result_from_state(prior)
    result = validate_temporary_parquet(
        temporary_path=final_path,
        entry=entry,
        extremes=extremes,
        source_result=source_result,
        config=config,
        required_metadata=metadata,
    )
    result.output_path = str(state_row["final_path"])
    result.output_sha256 = str(state_row["output_sha256"])
    result.output_size_bytes = final_path.stat().st_size
    result.compression_ratio = entry.size_bytes / result.output_size_bytes
    result.status = "PASS"
    return result


def run_phase02(config: Phase02Config) -> Phase02Outcome:
    if config.run_scope == "FULL_CONVERSION":
        require_goethe_nhr_slurm("phase02.full-conversion")
    config.validate()
    stage00: Stage00Binding | None = None
    if config.run_scope == "FULL_CONVERSION":
        assert config.stage00_adoption_record is not None
        assert config.expected_stage00_adoption_sha256 is not None
        stage00 = resolve_stage00_binding(
            config.stage00_adoption_record,
            config.phase01_run_dir,
            expected_stage00_adoption_sha256=(config.expected_stage00_adoption_sha256),
        )
    phase01 = load_phase01_manifest(config.phase01_run_dir)
    if stage00 is not None:
        _validate_stage00_population(phase01=phase01, stage00=stage00)
    entries = _select_entries(config, phase01.files)
    source_root_input = config.source_root
    source_scope_snapshot = _validate_source_paths(
        source_root_input,
        entries,
        require_exact_scope=config.run_scope == "FULL_CONVERSION",
    )
    source_root = source_root_input.resolve()
    run_id, staging_run, report_run, resumed = _prepare_run_directories(config)
    data_dir = staging_run / "data"
    in_progress = staging_run / ".in_progress"
    work_dir = staging_run / "_work"
    for directory in (data_dir, in_progress, work_dir):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)
    if config.run_scope == "FULL_CONVERSION":
        free = shutil.disk_usage(staging_run).free
        if free < config.require_free_bytes:
            raise OSError(
                f"FULL_CONVERSION requires {config.require_free_bytes} free bytes; {free} available"
            )

    started_at = _utc_now()
    overall_started = time.perf_counter()
    configuration = _configuration_payload(config, stage00)
    config_fingerprint = fingerprint(configuration)
    implementation_fingerprint = _implementation_fingerprint()
    schema_payload = {
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
        "parquet_configuration": configuration["parquet"],
    }
    run_payload: dict[str, Any] = {
        "run_id": run_id,
        "staging_version": STAGING_VERSION,
        "run_scope": config.run_scope,
        "status": "IN_PROGRESS",
        "scope_gate": "NOT_EVALUATED",
        "phase02_completion_gate": "NOT_EVALUATED",
        "started_at_utc": _iso_utc(started_at),
        "completed_at_utc": None,
        "git_commit": _git_commit(),
        "git_dirty": _git_dirty(),
        "python_version": sys.version.split()[0],
        "dependencies": {"pyarrow": pyarrow.__version__, "duckdb": duckdb.__version__},
        "phase01_run_id": phase01.run_id,
        "phase01_input_manifest_sha256": phase01.input_manifest_sha256,
        "source_root_label": config.portable_source_label,
        "approved_input_files": [entry.relative_path for entry in entries],
        "configuration": configuration,
        "configuration_fingerprint": config_fingerprint,
        "implementation_fingerprint": implementation_fingerprint,
        "resume": resumed,
        "metrics": {},
    }
    results: list[FileValidationResult] = []
    state_path = work_dir / "phase02_state.sqlite3"
    with RunState(state_path) as state:
        state.set_meta("run_id", run_id)
        state.set_meta("run_scope", config.run_scope)
        state.set_meta("phase01_input_manifest_sha256", phase01.input_manifest_sha256)
        state.set_meta("configuration_fingerprint", config_fingerprint)
        state.set_meta("implementation_fingerprint", implementation_fingerprint)
        if stage00 is not None:
            state.set_meta(
                "stage00_adoption_record_sha256", stage00.adoption_record.sha256
            )
            state.set_meta(
                "stage00_source_population_sha256",
                stage00.source_population_sha256_v1,
            )
            state.set_meta(
                "stage00_scientific_inventory_sha256",
                stage00.scientific_inventory_sha256_v1,
            )
            state.set_meta(
                "stage00_parser_contract_fingerprint",
                stage00.parser_contract_fingerprint,
            )
        state.prepare_files(
            entries,
            config_fingerprint=config_fingerprint,
            implementation_fingerprint=implementation_fingerprint,
        )
        from ..phase01.reports import atomic_json

        atomic_json(report_run / "phase02_run.json", run_payload)
        for entry in entries:
            metadata = _parquet_metadata(
                run_id=run_id,
                entry=entry,
                phase01_run_id=phase01.run_id,
                phase01_manifest_sha256=phase01.input_manifest_sha256,
                config_fingerprint=config_fingerprint,
                implementation_fingerprint=implementation_fingerprint,
            )
            state_row = state.get(entry.relative_path)
            if state_row["status"] == "COMPLETE":
                try:
                    result = _revalidate_complete(
                        state_row=state_row,
                        staging_run=staging_run,
                        source_root=source_root,
                        entry=entry,
                        extremes=phase01.extremes.get(entry.relative_path, ()),
                        config=config,
                        metadata=metadata,
                    )
                    result.peak_rss_bytes = _peak_rss_bytes()
                    results.append(result)
                    continue
                except Phase02FileError as error:
                    state.mark_failed(entry.relative_path, error.code, error.detail)
                    results.append(
                        FileValidationResult(
                            relative_path=entry.relative_path,
                            status="FAILED",
                            failure_code=error.code,
                            failure_detail=error.detail,
                        )
                    )
                    continue
            if state_row["status"] in {"WRITING", "VALIDATING"}:
                _quarantine_interrupted_attempt(
                    state_row=state_row,
                    staging_run=staging_run,
                    in_progress=in_progress,
                    work_dir=work_dir,
                )
                state.mark_failed(
                    entry.relative_path,
                    "INTERRUPTED_PREVIOUS_ATTEMPT",
                    "previous attempt did not reach a terminal state",
                )
                state_row = state.get(entry.relative_path)

            next_attempt = int(state_row["attempt"]) + 1
            parquet_name = Path(entry.file_name).with_suffix(".parquet").name
            temporary = in_progress / f"{parquet_name}.{next_attempt}.parquet.tmp"
            final = data_dir / parquet_name
            temporary_relative = temporary.relative_to(staging_run).as_posix()
            final_relative = final.relative_to(staging_run).as_posix()
            if final.exists():
                path_error = Phase02FileError(
                    "IMMUTABLE_FINAL_PATH_EXISTS",
                    "final output exists without reusable COMPLETE state",
                )
                state.mark_failed(
                    entry.relative_path, path_error.code, path_error.detail
                )
                results.append(
                    FileValidationResult(
                        relative_path=entry.relative_path,
                        status="FAILED",
                        failure_code=path_error.code,
                        failure_detail=path_error.detail,
                    )
                )
                continue
            state.mark_writing(entry.relative_path, temporary_relative, final_relative)
            result = FileValidationResult(relative_path=entry.relative_path)
            try:
                source_result = write_source_to_temporary_parquet(
                    source_path=source_root / entry.relative_path,
                    temporary_path=temporary,
                    entry=entry,
                    extremes=phase01.extremes.get(entry.relative_path, ()),
                    config=config,
                    file_metadata_values=metadata,
                )
                state.mark_validating(entry.relative_path)
                result = validate_temporary_parquet(
                    temporary_path=temporary,
                    entry=entry,
                    extremes=phase01.extremes.get(entry.relative_path, ()),
                    source_result=source_result,
                    config=config,
                    required_metadata=metadata,
                )
                hash_started = time.perf_counter()
                result.output_sha256 = sha256_file(temporary, config.hash_chunk_bytes)
                result.hashing_seconds += time.perf_counter() - hash_started
                result.output_size_bytes = temporary.stat().st_size
                result.output_path = final_relative
                result.compression_ratio = entry.size_bytes / result.output_size_bytes
                _fsync_file_and_parent(temporary)
                promotion_started = time.perf_counter()
                try:
                    os.replace(temporary, final)
                    _fsync_file_and_parent(final)
                except OSError as error:
                    raise Phase02FileError(
                        "ATOMIC_PROMOTION_FAILURE", type(error).__name__
                    ) from error
                result.promotion_seconds = time.perf_counter() - promotion_started
                result.peak_rss_bytes = _peak_rss_bytes()
                result.status = "PASS"
                state.mark_complete(entry.relative_path, result.to_dict())
            except Phase02FileError as error:
                result.status = "FAILED"
                result.failure_code = error.code
                result.failure_detail = error.detail
                _quarantine(temporary, work_dir)
                state.mark_failed(entry.relative_path, error.code, error.detail)
            except Exception as error:
                result.status = "FAILED"
                result.failure_code = "UNEXPECTED_FILE_FAILURE"
                result.failure_detail = type(error).__name__
                _quarantine(temporary, work_dir)
                state.mark_failed(
                    entry.relative_path, result.failure_code, result.failure_detail
                )
            results.append(result)
        state_integrity = state.integrity_check()

    _verify_source_scope_unchanged(
        source_root_input,
        entries,
        source_scope_snapshot,
        require_exact_scope=config.run_scope == "FULL_CONVERSION",
    )
    if stage00 is not None:
        _verify_stage00_binding_unchanged(config, stage00)

    reconciliation = reconcile_completed_parquet(
        data_dir=data_dir,
        entries=entries,
        memory_limit=config.duckdb_memory_limit,
        spill_dir=work_dir / "duckdb_spill",
    )
    _verify_source_scope_unchanged(
        source_root_input,
        entries,
        source_scope_snapshot,
        require_exact_scope=config.run_scope == "FULL_CONVERSION",
    )
    if stage00 is not None:
        _verify_stage00_binding_unchanged(config, stage00)
    all_files_pass = len(results) == len(entries) and all(
        item.status == "PASS" for item in results
    )
    scope_gate = (
        "PASS" if all_files_pass and reconciliation.status == "PASS" else "FAIL"
    )
    phase02_completion_gate = (
        scope_gate if config.run_scope == "FULL_CONVERSION" else "NOT_EVALUATED"
    )
    completed_at = _utc_now()
    source_bytes = sum(item.source_size_bytes for item in results)
    parquet_bytes = sum(item.output_size_bytes for item in results)
    conversion_seconds = sum(item.conversion_seconds for item in results)
    validation_seconds = sum(item.validation_seconds for item in results)
    metrics: dict[str, float | int] = {
        "runtime_seconds": time.perf_counter() - overall_started,
        "source_bytes": source_bytes,
        "parquet_bytes": parquet_bytes,
        "compression_ratio": source_bytes / parquet_bytes if parquet_bytes else 0.0,
        "conversion_seconds": conversion_seconds,
        "validation_seconds": validation_seconds,
        "hashing_seconds": sum(item.hashing_seconds for item in results),
        "promotion_seconds": sum(item.promotion_seconds for item in results),
        "conversion_throughput_bytes_per_second": source_bytes / conversion_seconds
        if conversion_seconds
        else 0.0,
        "validation_throughput_bytes_per_second": parquet_bytes / validation_seconds
        if validation_seconds
        else 0.0,
        "duckdb_reconciliation_seconds": reconciliation.duckdb_seconds,
        "peak_rss_bytes": _peak_rss_bytes(),
        "peak_temporary_bytes": max(
            (item.peak_temporary_bytes for item in results), default=0
        ),
        "sqlite_bytes": _directory_size(work_dir)
        - _directory_size(work_dir / "duckdb_spill"),
        "duckdb_spill_bytes": _directory_size(work_dir / "duckdb_spill"),
    }
    status = "COMPLETED_SCOPE_PASS" if scope_gate == "PASS" else "COMPLETED_SCOPE_FAIL"
    run_payload.update(
        {
            "status": status,
            "scope_gate": scope_gate,
            "phase02_completion_gate": phase02_completion_gate,
            "completed_at_utc": _iso_utc(completed_at),
            "state_store_integrity": state_integrity,
            "metrics": metrics,
        }
    )
    manifest_payload = {
        "run_id": run_id,
        "run_scope": config.run_scope,
        "phase02_completion_gate": phase02_completion_gate,
        "phase01_input_manifest_sha256": phase01.input_manifest_sha256,
        "configuration_fingerprint": config_fingerprint,
        "implementation_fingerprint": implementation_fingerprint,
        "schema_fingerprint": schema_fingerprint(),
        "files": [
            {
                "source_file": item.relative_path,
                "source_sha256": item.source_sha256,
                "source_rows": item.source_rows,
                "output_file": item.output_path,
                "output_sha256": item.output_sha256,
                "output_size_bytes": item.output_size_bytes,
                "staging_rows": item.staging_rows,
                "source_semantic_digest": item.source_semantic_digest,
                "staging_semantic_digest": item.staging_semantic_digest,
                "status": item.status,
            }
            for item in results
        ],
        "reconciliation": reconciliation.to_dict(),
    }
    marker_name: str | None = None
    marker_payload: dict[str, Any] | None = None
    if scope_gate == "PASS":
        atomic_json(staging_run / "dataset_manifest.json", manifest_payload)
        (staging_run / "dataset_manifest.json").chmod(0o600)
        manifest_sha256 = sha256_file(staging_run / "dataset_manifest.json")
        marker_payload = {
            "run_id": run_id,
            "run_scope": config.run_scope,
            "scope_gate": scope_gate,
            "phase02_completion_gate": phase02_completion_gate,
            "dataset_manifest_sha256": manifest_sha256,
            "git_commit": _git_commit(),
            "files": len(entries),
            "rows": reconciliation.total_rows,
            "source_bytes": source_bytes,
            "staging_bytes": parquet_bytes,
            "completed_at_utc": _iso_utc(completed_at),
        }
        marker_name = (
            "_SUCCESS.json"
            if config.run_scope == "FULL_CONVERSION"
            else "_SCOPE_SUCCESS.json"
        )
    write_all_reports(
        report_run_dir=report_run,
        run_payload=run_payload,
        results=results,
        reconciliation=reconciliation,
        schema_payload=schema_payload,
    )
    if marker_name is not None and marker_payload is not None:
        atomic_json(staging_run / marker_name, marker_payload)
        (staging_run / marker_name).chmod(0o600)
    return Phase02Outcome(
        run_id=run_id,
        staging_run_dir=staging_run,
        report_run_dir=report_run,
        status=status,
        scope_gate=scope_gate,
        phase02_completion_gate=phase02_completion_gate,
        files=tuple(results),
        reconciliation=reconciliation,
        metrics=metrics,
    )
