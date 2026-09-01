"""Targeted protected gate for revised Stage 7 crash supervision semantics."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import time
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn, cast

import pyarrow as pa
import pyarrow.parquet as pq

from ...execution_policy import require_goethe_nhr_slurm
from .s06_exact_deduplication import (
    REGISTRY_COLUMNS,
    STAGE06_MANIFEST_NAME,
    validate_stage06_bundle,
)
from .s07_design_diagnostic import (
    ACCEPTED_GIANT_CANDIDATES,
    ACCEPTED_MAXIMUM_CODEPOINTS,
    ACCEPTED_STAGE06_INPUT_BINDING_FINGERPRINT,
    ACCEPTED_STAGE06_LOGICAL_FINGERPRINT,
    ACCEPTED_STAGE06_MANIFEST_FINGERPRINT,
    ACCEPTED_STAGE06_ROWS,
    ACCEPTED_STAGE06_SCHEMA_FINGERPRINT,
    GIANT_MINIMUM_CODEPOINTS,
    _isolated_parse,
)
from .s07_libpostal_adapter import (
    PARSED_EMPTY,
    PARSED_NONEMPTY,
    LibpostalComponent,
    ParsedAddress,
    ordered_parse_sha256,
)
from .s07_output_schema import (
    STAGE07_COMPONENTS_FIELD,
    STAGE07_STATUS_FIELD,
    component_list_field,
    one_component_list_array,
)
from .s07_parser_bundle import validate_parser_bundle
from .s07_supervised_parser import (
    PARSER_PROCESS_CRASH,
    ParseAttempt,
    ProcessFailureSignature,
    Stage07SupervisorError,
    SupervisedParseOutcome,
    SupervisedParser,
)


STAGE07_SUPERVISOR_DIAGNOSTIC_VERSION = "stage07_supervisor_diagnostic_v1"
STAGE07_SUPERVISOR_DIAGNOSTIC_NAME = "stage07_supervisor_diagnostic.json"
STAGE07_SUPERVISOR_CONTROLLED_NAME = "stage07_supervisor_controlled.json"
STAGE07_SUPERVISOR_SUCCESS_NAME = "_SUCCESS.json"
STAGE07_SUPERVISOR_SELECTION_DOMAIN = b"SAFE_STAGE07_SUPERVISOR_GIANTS_V1"
EXPECTED_PARSER_BUNDLE_FINGERPRINT = (
    "f3c6db7e9f11ab75b2207be773e946d531dbba763008d9f7e5036d8c923dc2ae"
)
EXPECTED_PRIOR_DIAGNOSTIC_SHA256 = (
    "7b09fb79a6ef905c1e41d9387fc7ebfa5a24b257c8aee50d779f96aa47e32283"
)
EXPECTED_PRIOR_SELECTION_FINGERPRINT = (
    "a81995f832f89cdc5053827d6479c2170641815a44f3e64c90c9d3a6816fe3df"
)
EXPECTED_PRIOR_GIANT_SUCCESSES = 19
EXPECTED_PRIOR_GIANT_CRASHES = 4
_PRIOR_GIANT_TIMEOUT_SECONDS = 900
_PRIOR_GIANT_ADDRESS_SPACE_BYTES = 48 * 1024 * 1024 * 1024

_REGISTRY_DIRECTORY = "registry/data"
_SHA256_LENGTH = 64
_GIT_SHA_LENGTH = 40
_NATIVE_SIGNALS = frozenset({"SIGABRT", "SIGSEGV", "SIGBUS", "SIGILL", "SIGFPE"})


class Stage07SupervisorDiagnosticError(RuntimeError):
    """Privacy-safe targeted-diagnostic failure."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class Stage07SupervisorDiagnosticConfig:
    stage05_output_directory: Path
    stage06_output_directory: Path
    expected_stage06_manifest_sha256: str
    prior_diagnostic_directory: Path
    expected_prior_diagnostic_sha256: str
    parser_bundle_directory: Path
    expected_parser_bundle_fingerprint: str
    output_directory: Path
    execution_git_sha: str
    duckdb_memory_limit: str = "8GB"
    duckdb_threads: int = 4
    production: bool = True
    authoritative_development: bool = True

    def validate(self) -> None:
        for value in (
            self.expected_stage06_manifest_sha256,
            self.expected_prior_diagnostic_sha256,
            self.expected_parser_bundle_fingerprint,
        ):
            _require_sha256(value)
        if len(self.execution_git_sha) != _GIT_SHA_LENGTH or any(
            character not in "0123456789abcdef" for character in self.execution_git_sha
        ):
            _fail("INVALID_GIT_COMMIT", "Execution Git SHA must be exact")
        if self.duckdb_threads < 1 or not self.duckdb_memory_limit:
            _fail("INVALID_DIAGNOSTIC_BOUNDS", "Diagnostic bounds are invalid")
        _reject_holdout_paths(
            self.stage05_output_directory,
            self.stage06_output_directory,
            self.prior_diagnostic_directory,
            self.parser_bundle_directory,
            self.output_directory,
        )


@dataclass(frozen=True, slots=True)
class Stage07SupervisorDiagnosticOutcome:
    output_directory: Path
    diagnostic_sha256: str
    controlled_sha256: str
    parser_bundle_fingerprint: str
    gate_result: str


@dataclass(frozen=True, slots=True)
class _GiantCandidate:
    candidate_id: bytes
    candidate: str


@dataclass(frozen=True, slots=True)
class _LargeListAudit:
    parquet_bytes: int
    serialization_seconds: float
    validation_seconds: float
    component_count: int
    output_codepoints: int


def _fail(code: str, detail: str) -> NoReturn:
    raise Stage07SupervisorDiagnosticError(code, detail)


def _require_sha256(value: str) -> None:
    if len(value) != _SHA256_LENGTH or any(
        character not in "0123456789abcdef" for character in value
    ):
        _fail("INVALID_FINGERPRINT", "A required SHA-256 is malformed")


def _reject_holdout_paths(*paths: Path) -> None:
    if any(
        "holdout" in part.casefold()
        for path in paths
        for part in path.resolve(strict=False).parts
    ):
        _fail("HOLDOUT_ACCESS_PROHIBITED", "HOLDOUT paths are prohibited")


def _require_mode(path: Path, expected: int) -> None:
    if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) != expected:
        _fail("PERMISSION_FAILURE", "Controlled path permissions differ")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(8 * 1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise Stage07SupervisorDiagnosticError(
            "DIAGNOSTIC_READ_FAILURE", "A controlled artifact could not be read"
        ) from error
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Stage07SupervisorDiagnosticError(
            "MANIFEST_INVALID", "Controlled metadata could not be read"
        ) from error
    if not isinstance(value, dict):
        _fail("MANIFEST_INVALID", "Controlled metadata root is not an object")
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _artifact_paths(
    root: Path, manifest: Mapping[str, Any], key: str, prefix: str
) -> tuple[Path, ...]:
    physical = manifest.get("physical_identity")
    if not isinstance(physical, dict) or not isinstance(physical.get(key), list):
        _fail("MANIFEST_INVALID", "Stage 6 physical identity is malformed")
    paths: list[Path] = []
    for raw in physical[key]:
        if not isinstance(raw, dict) or not isinstance(raw.get("relative_path"), str):
            _fail("MANIFEST_INVALID", "Stage 6 artifact identity is malformed")
        relative = cast(str, raw["relative_path"])
        if not relative.startswith(f"{prefix}/"):
            _fail("MANIFEST_INVALID", "Stage 6 artifact path is outside its role")
        path = root / relative
        if (
            not path.is_file()
            or path.is_symlink()
            or path.stat().st_size != raw.get("size_bytes")
            or _sha256_file(path) != raw.get("sha256")
        ):
            _fail("ARTIFACT_MISMATCH", "Stage 6 artifact identity differs")
        _require_mode(path, 0o600)
        paths.append(path)
    return tuple(paths)


def _validated_registry_paths(
    config: Stage07SupervisorDiagnosticConfig,
) -> tuple[Path, ...]:
    outcome = validate_stage06_bundle(
        config.stage06_output_directory,
        expected_manifest_sha256=config.expected_stage06_manifest_sha256,
        stage05_output_directory=config.stage05_output_directory,
        authoritative_development=config.authoritative_development,
        duckdb_memory_limit=config.duckdb_memory_limit,
        duckdb_threads=config.duckdb_threads,
    )
    if config.authoritative_development and (
        outcome.manifest_sha256 != ACCEPTED_STAGE06_MANIFEST_FINGERPRINT
        or outcome.schema_fingerprint != ACCEPTED_STAGE06_SCHEMA_FINGERPRINT
        or outcome.logical_dataset_sha256_v1 != ACCEPTED_STAGE06_LOGICAL_FINGERPRINT
        or outcome.input_binding_sha256 != ACCEPTED_STAGE06_INPUT_BINDING_FINGERPRINT
        or outcome.unique_candidate_count != ACCEPTED_STAGE06_ROWS
    ):
        _fail("STAGE06_BINDING_MISMATCH", "Accepted Stage 6 identity differs")
    manifest = _load_json(config.stage06_output_directory / STAGE06_MANIFEST_NAME)
    return _artifact_paths(
        config.stage06_output_directory,
        manifest,
        "registry_artifacts",
        _REGISTRY_DIRECTORY,
    )


def _validate_prior_diagnostic(config: Stage07SupervisorDiagnosticConfig) -> None:
    root = config.prior_diagnostic_directory
    path = root / "stage07_design_diagnostic.json"
    if (
        not root.is_dir()
        or root.is_symlink()
        or not path.is_file()
        or path.is_symlink()
    ):
        _fail("PRIOR_DIAGNOSTIC_INVALID", "Prior diagnostic is absent or unsafe")
    _require_mode(root, 0o700)
    _require_mode(path, 0o600)
    if _sha256_file(path) != config.expected_prior_diagnostic_sha256:
        _fail("PRIOR_DIAGNOSTIC_INVALID", "Prior diagnostic hash differs")
    value = _load_json(path)
    selection = value.get("selection")
    giant = value.get("giant_safety")
    parser_bundle = value.get("parser_bundle")
    failure_counts = giant.get("failure_counts") if isinstance(giant, dict) else None
    if (
        value.get("gate_result") != "SCIENTIFIC_CONFLICT"
        or not isinstance(selection, dict)
        or selection.get("selection_fingerprint")
        != EXPECTED_PRIOR_SELECTION_FINGERPRINT
        or not isinstance(giant, dict)
        or giant.get("candidates_tested") != ACCEPTED_GIANT_CANDIDATES
        or giant.get("successful") != EXPECTED_PRIOR_GIANT_SUCCESSES
        or not isinstance(failure_counts, dict)
        or failure_counts.get("PROCESS_CRASH") != EXPECTED_PRIOR_GIANT_CRASHES
        or giant.get("timeout_seconds_per_candidate") != _PRIOR_GIANT_TIMEOUT_SECONDS
        or giant.get("address_space_bytes_per_candidate")
        != _PRIOR_GIANT_ADDRESS_SPACE_BYTES
        or not isinstance(parser_bundle, dict)
        or parser_bundle.get("parser_bundle_fingerprint")
        != config.expected_parser_bundle_fingerprint
    ):
        _fail("PRIOR_DIAGNOSTIC_INVALID", "Prior giant evidence differs")


def _iter_giants(registry_paths: Sequence[Path]) -> Iterable[_GiantCandidate]:
    try:
        for path in registry_paths:
            parquet = pq.ParquetFile(path, page_checksum_verification=True)
            for batch in parquet.iter_batches(
                batch_size=16,
                columns=list(REGISTRY_COLUMNS[:2]),
                use_threads=False,
            ):
                for row_index in range(batch.num_rows):
                    candidate_id = batch.column(0)[row_index].as_py()
                    candidate = batch.column(1)[row_index].as_py()
                    if not isinstance(candidate_id, bytes) or not isinstance(
                        candidate, str
                    ):
                        _fail("REGISTRY_INVALID", "Stage 6 registry row is malformed")
                    if len(candidate) >= GIANT_MINIMUM_CODEPOINTS:
                        yield _GiantCandidate(candidate_id, candidate)
    except Stage07SupervisorDiagnosticError:
        raise
    except (OSError, pa.ArrowException) as error:
        raise Stage07SupervisorDiagnosticError(
            "REGISTRY_READ_FAILURE", "Stage 6 registry could not be streamed"
        ) from error


def _giant_selection_fingerprint(candidates: Iterable[_GiantCandidate]) -> str:
    digest = hashlib.sha256(STAGE07_SUPERVISOR_SELECTION_DOMAIN)
    count = 0
    maximum = 0
    for item in candidates:
        digest.update(len(item.candidate_id).to_bytes(8, "big"))
        digest.update(item.candidate_id)
        count += 1
        maximum = max(maximum, len(item.candidate))
    if count != ACCEPTED_GIANT_CANDIDATES or maximum != ACCEPTED_MAXIMUM_CODEPOINTS:
        _fail("GIANT_SELECTION_INVALID", "Accepted giant selection differs")
    return digest.hexdigest()


def _attempt_payload(attempt: ParseAttempt) -> dict[str, object]:
    return {
        "outcome": attempt.outcome,
        "technical_code": attempt.technical_code,
        "failure_signature": (
            asdict(attempt.failure_signature) if attempt.failure_signature else None
        ),
        "wall_seconds": round(attempt.wall_seconds, 6),
        "child_max_rss_kib": attempt.child_max_rss_kib,
        "input_codepoints_verified": attempt.input_codepoints_verified,
        "input_sha256_verified": attempt.input_sha256_verified,
        "result_framing_completed": attempt.result_framing_completed,
    }


def _ordered_from_arrow(value: object, status: str) -> ParsedAddress:
    if not isinstance(value, list):
        _fail("LARGE_LIST_AUDIT_FAILURE", "Nested parse did not round-trip as a list")
    components: list[LibpostalComponent] = []
    for item in value:
        if (
            not isinstance(item, dict)
            or set(item) != {"label", "value"}
            or not isinstance(item["label"], str)
            or not isinstance(item["value"], str)
        ):
            _fail("LARGE_LIST_AUDIT_FAILURE", "Nested component round-trip differs")
        components.append(LibpostalComponent(label=item["label"], value=item["value"]))
    parsed = ParsedAddress(status=status, components=tuple(components))
    if (status == PARSED_NONEMPTY) != bool(parsed.components):
        _fail("LARGE_LIST_AUDIT_FAILURE", "Nested status/list semantics differ")
    return parsed


def _audit_large_list(work: Path, outcome: SupervisedParseOutcome) -> _LargeListAudit:
    if outcome.components is None:
        _fail("LARGE_LIST_AUDIT_FAILURE", "Successful parse components are absent")
    path = work / "large_list_audit.parquet"
    if path.exists():
        path.unlink()
    schema = pa.schema(
        (
            pa.field(STAGE07_STATUS_FIELD, pa.string(), nullable=False),
            component_list_field(diagnostic_nullable=True),
        )
    )
    started = time.perf_counter()
    table = pa.Table.from_arrays(
        (
            pa.array((outcome.status,), type=pa.string()),
            one_component_list_array(outcome.components),
        ),
        schema=schema,
    )
    pq.write_table(
        table,
        path,
        compression="zstd",
        use_dictionary=False,
        write_page_checksum=True,
        data_page_size=1024 * 1024,
        row_group_size=1,
    )
    path.chmod(0o600)
    serialization = time.perf_counter() - started
    started = time.perf_counter()
    read = pq.ParquetFile(path, page_checksum_verification=True).read(use_threads=False)
    if read.schema != schema or read.num_rows != 1:
        _fail("LARGE_LIST_AUDIT_FAILURE", "Nested Arrow schema did not round-trip")
    scalar = read.column(STAGE07_COMPONENTS_FIELD)[0]
    parsed = _ordered_from_arrow(scalar.as_py(), outcome.status)
    expected = ParsedAddress(status=outcome.status, components=outcome.components)
    if ordered_parse_sha256(parsed) != ordered_parse_sha256(expected):
        _fail("LARGE_LIST_AUDIT_FAILURE", "Ordered nested values differ")
    validation = time.perf_counter() - started
    size = path.stat().st_size
    path.unlink()
    return _LargeListAudit(
        parquet_bytes=size,
        serialization_seconds=serialization,
        validation_seconds=validation,
        component_count=len(outcome.components),
        output_codepoints=sum(len(item.value) for item in outcome.components),
    )


def _distribution(values: Sequence[int | float]) -> dict[str, int | float]:
    if not values:
        return {"min": 0, "mean": 0, "max": 0}
    return {
        "min": round(min(values), 6),
        "mean": round(sum(values) / len(values), 6),
        "max": round(max(values), 6),
    }


def _signature_key(signature: ProcessFailureSignature) -> str:
    if signature.exit_category == "SIGNAL":
        return f"SIGNAL:{signature.signal_name}:{signature.signal_number}"
    return f"{signature.exit_category}:{signature.exit_code}"


def _write_json(path: Path, value: object) -> None:
    payload = (
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o600)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def run_stage07_supervisor_diagnostic(
    config: Stage07SupervisorDiagnosticConfig,
) -> Stage07SupervisorDiagnosticOutcome:
    """Retest all accepted giants using the owner-approved supervision path."""
    config.validate()
    if config.production:
        require_goethe_nhr_slurm("stage07-supervisor-diagnostic")
    if config.output_directory.exists() or config.output_directory.is_symlink():
        _fail("OUTPUT_COLLISION", "Diagnostic output already exists")

    total_started = time.perf_counter()
    bundle = validate_parser_bundle(
        config.parser_bundle_directory,
        expected_parser_bundle_fingerprint=config.expected_parser_bundle_fingerprint,
    )
    _validate_prior_diagnostic(config)
    registry_paths = _validated_registry_paths(config)
    selection_fingerprint = _giant_selection_fingerprint(_iter_giants(registry_paths))

    parent = config.output_directory.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent.chmod(0o700)
    _require_mode(parent, 0o700)
    temporary = parent / f".{config.output_directory.name}.{os.getpid()}.in_progress"
    if temporary.exists() or temporary.is_symlink():
        _fail("OUTPUT_COLLISION", "Diagnostic temporary output already exists")
    temporary.mkdir(mode=0o700)
    work = temporary / "work"
    work.mkdir(mode=0o700)

    scientific_conflicts: list[str] = []
    prior_reference: dict[bytes, dict[str, object]] = {}
    prior_replay_started = time.perf_counter()
    for item in _iter_giants(registry_paths):
        replay = _isolated_parse(
            item.candidate,
            timeout_seconds=_PRIOR_GIANT_TIMEOUT_SECONDS,
            address_space_bytes=_PRIOR_GIANT_ADDRESS_SPACE_BYTES,
        )
        prior_reference[item.candidate_id] = {
            "ok": replay.ok,
            "failure": replay.failure,
            "status": replay.status,
            "ordered_parse_sha256": replay.ordered_parse_sha256,
        }
    prior_replay_seconds = time.perf_counter() - prior_replay_started
    prior_replay_successes = sum(
        bool(value["ok"]) for value in prior_reference.values()
    )
    prior_replay_crashes = sum(
        value["failure"] == "PROCESS_CRASH" for value in prior_reference.values()
    )
    if (
        len(prior_reference) != ACCEPTED_GIANT_CANDIDATES
        or prior_replay_successes != EXPECTED_PRIOR_GIANT_SUCCESSES
        or prior_replay_crashes != EXPECTED_PRIOR_GIANT_CRASHES
        or any(
            not value["ok"] and value["failure"] != "PROCESS_CRASH"
            for value in prior_reference.values()
        )
    ):
        scientific_conflicts.append("PRIOR_GIANT_REFERENCE_REPLAY_MISMATCH")

    baseline: dict[bytes, dict[str, object]] = {}
    controlled_rows: list[dict[str, object]] = []
    controlled_row_by_id: dict[bytes, dict[str, object]] = {}
    large_list_audits: list[_LargeListAudit] = []
    all_attempts: list[ParseAttempt] = []
    first_phase_supervisor = SupervisedParser(diagnostic_crash_status=True)
    parent_survived = False
    first_phase_error: str | None = None
    prior_reference_success_matches = 0
    prior_reference_crash_matches = 0
    try:
        for item in _iter_giants(registry_paths):
            try:
                outcome = first_phase_supervisor.parse(item.candidate)
            except Stage07SupervisorError as error:
                first_phase_error = error.code
                scientific_conflicts.append(error.code)
                all_attempts.extend(first_phase_supervisor.last_failed_attempts)
                controlled_rows.append(
                    {
                        "candidate_id_hex": item.candidate_id.hex(),
                        "input_codepoints": len(item.candidate),
                        "prior_reference": prior_reference[item.candidate_id],
                        "status": "SUPERVISOR_ABORTED",
                        "technical_code": error.code,
                        "attempts": [
                            _attempt_payload(value)
                            for value in first_phase_supervisor.last_failed_attempts
                        ],
                    }
                )
                break
            all_attempts.extend(outcome.attempts)
            row: dict[str, object] = {
                "candidate_id_hex": item.candidate_id.hex(),
                "input_codepoints": len(item.candidate),
                "prior_reference": prior_reference[item.candidate_id],
                "status": outcome.status,
                "failure_code": outcome.failure_code,
                "attempts": [_attempt_payload(value) for value in outcome.attempts],
            }
            if outcome.components is not None:
                parsed = ParsedAddress(outcome.status, outcome.components)
                digest = ordered_parse_sha256(parsed)
                row["ordered_parse_sha256"] = digest
                audit = _audit_large_list(work, outcome)
                large_list_audits.append(audit)
                baseline[item.candidate_id] = {
                    "status": outcome.status,
                    "ordered_parse_sha256": digest,
                    "failure_signature": None,
                }
                reference = prior_reference[item.candidate_id]
                if (
                    reference["ok"]
                    and outcome.status == reference["status"]
                    and digest == reference["ordered_parse_sha256"]
                ):
                    prior_reference_success_matches += 1
                elif reference["failure"] == "PROCESS_CRASH":
                    scientific_conflicts.append(
                        "PRIOR_CRASH_SUCCEEDS_WITH_REVISED_RESOURCES"
                    )
                else:
                    scientific_conflicts.append("PRIOR_SUCCESS_RESULT_CHANGED")
            else:
                signature = outcome.attempts[0].failure_signature
                if signature is None:
                    _fail("SUPERVISOR_EVIDENCE_INVALID", "Crash signature is absent")
                baseline[item.candidate_id] = {
                    "status": outcome.status,
                    "ordered_parse_sha256": None,
                    "failure_signature": asdict(signature),
                }
                reference = prior_reference[item.candidate_id]
                if reference["failure"] == "PROCESS_CRASH":
                    prior_reference_crash_matches += 1
                else:
                    scientific_conflicts.append("PRIOR_SUCCESS_NOW_CRASHES")
            controlled_rows.append(row)
            controlled_row_by_id[item.candidate_id] = row
        parent_survived = first_phase_error is None and len(baseline) == 23
    finally:
        first_phase_supervisor.close()

    baseline_successes = sum(
        value["status"] in {PARSED_NONEMPTY, PARSED_EMPTY}
        for value in baseline.values()
    )
    baseline_crashes = sum(
        value["status"] == PARSER_PROCESS_CRASH for value in baseline.values()
    )
    if first_phase_error is None and (
        baseline_successes != EXPECTED_PRIOR_GIANT_SUCCESSES
        or baseline_crashes != EXPECTED_PRIOR_GIANT_CRASHES
    ):
        scientific_conflicts.append("PRIOR_GIANT_AGGREGATE_NOT_REPRODUCED")

    repeat_successes = 0
    repeat_exact_matches = 0
    third_attempt_crashes = 0
    third_attempt_identical = 0
    crash_success_nondeterminism = 0
    changed_technical_failures = 0
    repeat_parent_survived = False
    repeat_workers_started = 0
    repeat_worker_restarts = 0
    repeat_crash_success_inconsistencies = 0
    repeat_changed_failure_inconsistencies = 0
    repeat_rows_completed = 0
    worker_initialization_seconds = list(
        first_phase_supervisor.worker_initialization_seconds
    )
    repeat_supervisor = SupervisedParser(diagnostic_crash_status=True)
    try:
        if first_phase_error is None:
            for item in _iter_giants(registry_paths):
                expected = baseline[item.candidate_id]
                reference = prior_reference[item.candidate_id]
                if reference["ok"]:
                    try:
                        repeated = repeat_supervisor.parse(item.candidate)
                    except Stage07SupervisorError as error:
                        scientific_conflicts.append(error.code)
                        all_attempts.extend(repeat_supervisor.last_failed_attempts)
                        controlled_row_by_id[item.candidate_id][
                            "repeat_technical_code"
                        ] = error.code
                        controlled_row_by_id[item.candidate_id]["repeat_attempts"] = [
                            _attempt_payload(value)
                            for value in repeat_supervisor.last_failed_attempts
                        ]
                        break
                    all_attempts.extend(repeated.attempts)
                    controlled_row_by_id[item.candidate_id]["repeat_attempts"] = [
                        _attempt_payload(value) for value in repeated.attempts
                    ]
                    controlled_row_by_id[item.candidate_id]["repeat_status"] = (
                        repeated.status
                    )
                    if repeated.components is None:
                        scientific_conflicts.append("SUCCESS_TO_CRASH_NONDETERMINISM")
                        changed_technical_failures += 1
                        break
                    repeat_successes += 1
                    digest = ordered_parse_sha256(
                        ParsedAddress(repeated.status, repeated.components)
                    )
                    controlled_row_by_id[item.candidate_id][
                        "repeat_ordered_parse_sha256"
                    ] = digest
                    if (
                        repeated.status == expected["status"]
                        and digest == expected["ordered_parse_sha256"]
                        and repeated.status == reference["status"]
                        and digest == reference["ordered_parse_sha256"]
                    ):
                        repeat_exact_matches += 1
                    else:
                        scientific_conflicts.append("SUCCESS_PARSE_NONDETERMINISM")
                        break
                    repeat_rows_completed += 1
                else:
                    # One additional fresh attempt is diagnostic-only. The first
                    # phase already applied the exact two-attempt publication rule.
                    repeat_workers_started += repeat_supervisor.workers_started
                    repeat_worker_restarts += repeat_supervisor.worker_restarts
                    repeat_crash_success_inconsistencies += (
                        repeat_supervisor.crash_success_inconsistencies
                    )
                    repeat_changed_failure_inconsistencies += (
                        repeat_supervisor.changed_failure_inconsistencies
                    )
                    worker_initialization_seconds.extend(
                        repeat_supervisor.worker_initialization_seconds
                    )
                    repeat_supervisor.close()
                    repeat_supervisor = SupervisedParser(diagnostic_crash_status=True)
                    third = repeat_supervisor.attempt_once(item.candidate)
                    all_attempts.append(third)
                    controlled_row_by_id[item.candidate_id]["third_attempt"] = (
                        _attempt_payload(third)
                    )
                    if third.outcome == "SUCCESS":
                        crash_success_nondeterminism += 1
                        scientific_conflicts.append(
                            "PARSER_CRASH_SUCCESS_NONDETERMINISM"
                        )
                        break
                    if (
                        third.outcome != "PROCESS_CRASH"
                        or third.failure_signature is None
                        or not third.input_codepoints_verified
                        or not third.input_sha256_verified
                    ):
                        changed_technical_failures += 1
                        scientific_conflicts.append(
                            "PARSER_CRASH_FAILURE_NONDETERMINISM"
                        )
                        break
                    third_attempt_crashes += 1
                    raw_expected_signature = expected["failure_signature"]
                    if not isinstance(raw_expected_signature, dict):
                        changed_technical_failures += 1
                        scientific_conflicts.append("PRIOR_CRASH_BASELINE_NOT_CRASH")
                        break
                    expected_signature = cast(dict[str, object], raw_expected_signature)
                    if asdict(third.failure_signature) == expected_signature:
                        third_attempt_identical += 1
                    else:
                        changed_technical_failures += 1
                        scientific_conflicts.append(
                            "PARSER_CRASH_SIGNATURE_NONDETERMINISM"
                        )
                        break
                    repeat_rows_completed += 1
            repeat_parent_survived = repeat_rows_completed == len(baseline) == 23
    finally:
        repeat_workers_started += repeat_supervisor.workers_started
        repeat_worker_restarts += repeat_supervisor.worker_restarts
        repeat_crash_success_inconsistencies += (
            repeat_supervisor.crash_success_inconsistencies
        )
        repeat_changed_failure_inconsistencies += (
            repeat_supervisor.changed_failure_inconsistencies
        )
        worker_initialization_seconds.extend(
            repeat_supervisor.worker_initialization_seconds
        )
        repeat_supervisor.close()

    signatures = Counter(
        _signature_key(attempt.failure_signature)
        for attempt in all_attempts
        if attempt.failure_signature is not None
    )
    resource_ambiguity = any(
        signature.startswith("SIGNAL:SIGKILL:")
        or signature in {"EXIT_CODE:137", "EXIT_STATUS_UNAVAILABLE:None"}
        for signature in signatures
    )
    non_native_termination = any(
        signature.startswith("SIGNAL:")
        and signature.split(":", 2)[1] not in _NATIVE_SIGNALS | {"SIGKILL"}
        for signature in signatures
    ) or any(signature == "EXIT_CODE:0" for signature in signatures)
    if resource_ambiguity:
        scientific_conflicts.append("RESOURCE_FAILURE_AMBIGUITY")
    if non_native_termination:
        scientific_conflicts.append("UNCLASSIFIED_PROCESS_TERMINATION")

    worker_restart_correct = (
        first_phase_supervisor.first_attempt_crashes == baseline_crashes
        and first_phase_supervisor.confirmed_repeated_crashes == baseline_crashes
        and first_phase_supervisor.crash_success_inconsistencies == 0
        and first_phase_supervisor.changed_failure_inconsistencies == 0
    )
    crash_success_nondeterminism += (
        first_phase_supervisor.crash_success_inconsistencies
        + repeat_crash_success_inconsistencies
    )
    changed_technical_failures += (
        first_phase_supervisor.changed_failure_inconsistencies
        + repeat_changed_failure_inconsistencies
    )
    if not parent_survived or not repeat_parent_survived:
        scientific_conflicts.append("PARENT_SURVIVAL_FAILURE")
    if not worker_restart_correct:
        scientific_conflicts.append("WORKER_RESTART_FAILURE")
    if repeat_exact_matches != EXPECTED_PRIOR_GIANT_SUCCESSES:
        scientific_conflicts.append("PREVIOUS_SUCCESS_RETEST_FAILURE")
    if third_attempt_identical != EXPECTED_PRIOR_GIANT_CRASHES:
        scientific_conflicts.append("PREVIOUS_CRASH_RETEST_FAILURE")
    if prior_reference_success_matches != EXPECTED_PRIOR_GIANT_SUCCESSES:
        scientific_conflicts.append("PRIOR_SUCCESS_EXACT_COMPARISON_FAILURE")
    if prior_reference_crash_matches != EXPECTED_PRIOR_GIANT_CRASHES:
        scientific_conflicts.append("PRIOR_CRASH_IDENTITY_COMPARISON_FAILURE")
    if crash_success_nondeterminism or changed_technical_failures:
        scientific_conflicts.append("PARSER_EXECUTION_NONDETERMINISM")
    scientific_conflicts = list(dict.fromkeys(scientific_conflicts))
    gate_result = "PASS" if not scientific_conflicts else "SCIENTIFIC_CONFLICT"

    rss_values = [
        attempt.child_max_rss_kib
        for attempt in all_attempts
        if attempt.child_max_rss_kib is not None
    ]
    wall_values = [attempt.wall_seconds for attempt in all_attempts]
    crash_attempts = [
        attempt for attempt in all_attempts if attempt.outcome == "PROCESS_CRASH"
    ]
    total_seconds = time.perf_counter() - total_started
    controlled_payload = {
        "stage07_supervisor_diagnostic_version": (
            STAGE07_SUPERVISOR_DIAGNOSTIC_VERSION
        ),
        "privacy": "OWNER_ONLY_CONTAINS_PROTECTED_CANDIDATE_IDS_NO_TEXT",
        "selection_fingerprint": selection_fingerprint,
        "rows": controlled_rows,
    }
    controlled_path = temporary / STAGE07_SUPERVISOR_CONTROLLED_NAME
    _write_json(controlled_path, controlled_payload)
    controlled_sha = _sha256_file(controlled_path)
    payload: dict[str, object] = {
        "stage07_supervisor_diagnostic_version": (
            STAGE07_SUPERVISOR_DIAGNOSTIC_VERSION
        ),
        "status": "STAGE07_SUPERVISOR_DIAGNOSTIC_COMPLETE",
        "gate_result": gate_result,
        "scientific_conflicts": scientific_conflicts,
        "privacy": "AGGREGATE_ONLY_NO_PROTECTED_VALUES",
        "input_binding": {
            "stage06_manifest_fingerprint": ACCEPTED_STAGE06_MANIFEST_FINGERPRINT,
            "stage06_schema_fingerprint": ACCEPTED_STAGE06_SCHEMA_FINGERPRINT,
            "stage06_logical_fingerprint": ACCEPTED_STAGE06_LOGICAL_FINGERPRINT,
            "stage06_input_binding_fingerprint": (
                ACCEPTED_STAGE06_INPUT_BINDING_FINGERPRINT
            ),
            "stage06_registry_rows": ACCEPTED_STAGE06_ROWS,
            "parser_bundle_fingerprint": bundle.parser_bundle_fingerprint,
            "prior_diagnostic_sha256": config.expected_prior_diagnostic_sha256,
            "prior_selection_fingerprint": EXPECTED_PRIOR_SELECTION_FINGERPRINT,
            "giant_selection_fingerprint": selection_fingerprint,
        },
        "prior_evidence": {
            "giant_candidates": ACCEPTED_GIANT_CANDIDATES,
            "successful": EXPECTED_PRIOR_GIANT_SUCCESSES,
            "process_crashes": EXPECTED_PRIOR_GIANT_CRASHES,
            "original_candidate_level_digests_available": False,
            "reference_replay_code_path": ("IMMUTABLE_FIRST_DIAGNOSTIC_ISOLATED_PARSE"),
            "reference_replay_candidates": len(prior_reference),
            "reference_replay_successes": prior_replay_successes,
            "reference_replay_process_crashes": prior_replay_crashes,
            "reference_replay_seconds": round(prior_replay_seconds, 6),
            "reference_replay_timeout_seconds": _PRIOR_GIANT_TIMEOUT_SECONDS,
            "reference_replay_address_space_bytes": (_PRIOR_GIANT_ADDRESS_SPACE_BYTES),
            "reference_replay_is_publication_policy": False,
            "comparison_policy": (
                "PRIOR_CODE_PATH_REPLAY_PLUS_TWO_UNCAPPED_SUPERVISOR_RESULTS"
            ),
        },
        "supervision": {
            "giants_tested": len(baseline),
            "baseline_complete_successes": baseline_successes,
            "baseline_confirmed_process_crashes": baseline_crashes,
            "previous_success_giants_retested": repeat_successes,
            "prior_success_exact_first_pass_matches": (prior_reference_success_matches),
            "previous_success_exact_ordered_matches": repeat_exact_matches,
            "previous_crash_giants_retested": third_attempt_crashes,
            "prior_crash_identity_first_pass_matches": prior_reference_crash_matches,
            "reproducibly_crashing_giants": third_attempt_identical,
            "crash_to_success_nondeterminism": crash_success_nondeterminism,
            "changed_technical_failures": changed_technical_failures,
            "first_attempt_native_crashes": (
                first_phase_supervisor.first_attempt_crashes
            ),
            "confirmed_repeated_crashes": (
                first_phase_supervisor.confirmed_repeated_crashes
            ),
            "worker_processes_started": first_phase_supervisor.workers_started,
            "worker_restarts": first_phase_supervisor.worker_restarts,
            "diagnostic_total_worker_processes_started": (
                first_phase_supervisor.workers_started + repeat_workers_started
            ),
            "diagnostic_total_worker_restarts": (
                first_phase_supervisor.worker_restarts + repeat_worker_restarts
            ),
            "parent_process_survived": parent_survived and repeat_parent_survived,
            "repeat_rows_completed": repeat_rows_completed,
            "worker_restart_correct": worker_restart_correct,
            "result_cross_wires": 0,
            "exact_input_acknowledgements": sum(
                attempt.input_codepoints_verified and attempt.input_sha256_verified
                for attempt in all_attempts
            ),
            "unverified_crash_attempts": sum(
                attempt.outcome == "PROCESS_CRASH"
                and (
                    not attempt.input_codepoints_verified
                    or not attempt.input_sha256_verified
                )
                for attempt in all_attempts
            ),
            "stdout_result_framing_used": False,
            "private_ipc_result_framing_used": True,
            "result_framing_completed": sum(
                attempt.result_framing_completed for attempt in all_attempts
            ),
            "result_framing_absent_on_crashes": sum(
                not attempt.result_framing_completed for attempt in crash_attempts
            ),
            "child_exit_signal_aggregate": dict(sorted(signatures.items())),
            "failure_repeated_identically": third_attempt_identical,
            "resource_failure_ambiguity": resource_ambiguity,
            "unclassified_process_termination": non_native_termination,
            "retry_policy": "ONE_EXACT_FRESH_RETRY_AFTER_FIRST_NATIVE_PROCESS_CRASH",
            "candidate_timeout_exists": False,
            "size_based_skip_exists": False,
            "safe_truncation_applied": False,
            "substring_parse_applied": False,
        },
        "runtime": {
            "attempt_wall_seconds": _distribution(wall_values),
            "worker_initialization_seconds": _distribution(
                worker_initialization_seconds
            ),
            "child_max_rss_kib_available_attempts": len(rss_values),
            "child_max_rss_kib": _distribution(rss_values),
            "total_diagnostic_seconds": round(total_seconds, 6),
            "per_candidate_address_space_limit": None,
            "global_slurm_limit_only": True,
        },
        "large_list_audit": {
            "arrow_type": (
                "large_list<struct<label:large_string not null,"
                "value:large_string not null> not null> nullable"
            ),
            "successful_giant_rows_serialized_and_reopened": len(large_list_audits),
            "maximum_component_count": max(
                (value.component_count for value in large_list_audits), default=0
            ),
            "maximum_output_codepoints": max(
                (value.output_codepoints for value in large_list_audits), default=0
            ),
            "maximum_parquet_bytes": max(
                (value.parquet_bytes for value in large_list_audits), default=0
            ),
            "serialization_seconds": round(
                sum(value.serialization_seconds for value in large_list_audits), 6
            ),
            "validation_seconds": round(
                sum(value.validation_seconds for value in large_list_audits), 6
            ),
            "page_checksum_verified": True,
            "row_group_rows": 1,
            "data_page_size_bytes": 1048576,
            "construction_component_dict_materialization": False,
            "validation_one_row_as_py": True,
            "validation_scope": "ONE_SUCCESSFUL_GIANT_AT_A_TIME",
        },
        "controlled_evidence": {
            "controlled_sha256": controlled_sha,
            "candidate_text_stored": False,
            "candidate_ids_stored_owner_only": True,
        },
        "scope": {
            "holdout_accessed": False,
            "production_stage02_started": False,
            "production_stage03_started": False,
            "production_stage04_started": False,
            "production_stage05_started": False,
            "production_stage06_started": False,
            "production_stage07_started": False,
            "stage08_started": False,
            "geocoding_performed": False,
            "external_service_used_for_protected_data": False,
            "stage06_science_changed": False,
        },
        "operational_provenance": {
            "execution_git_sha": config.execution_git_sha,
            "execution_site": os.environ.get("SAFE_EXECUTION_SITE", ""),
            "slurm_job_id": os.environ.get("SLURM_JOB_ID", ""),
            "created_at_utc": _utc_now(),
        },
    }
    shutil.rmtree(work)
    diagnostic_path = temporary / STAGE07_SUPERVISOR_DIAGNOSTIC_NAME
    _write_json(diagnostic_path, payload)
    diagnostic_sha = _sha256_file(diagnostic_path)
    _write_json(
        temporary / STAGE07_SUPERVISOR_SUCCESS_NAME,
        {
            "status": "STAGE07_SUPERVISOR_DIAGNOSTIC_COMPLETE",
            "gate_result": gate_result,
            "diagnostic_sha256": diagnostic_sha,
            "controlled_sha256": controlled_sha,
            "parser_bundle_fingerprint": bundle.parser_bundle_fingerprint,
            "giants_tested": len(baseline),
        },
    )
    for path in temporary.iterdir():
        if path.is_file():
            _require_mode(path, 0o600)
    _fsync_directory(temporary)
    os.replace(temporary, config.output_directory)
    _fsync_directory(parent)
    return Stage07SupervisorDiagnosticOutcome(
        output_directory=config.output_directory,
        diagnostic_sha256=diagnostic_sha,
        controlled_sha256=controlled_sha,
        parser_bundle_fingerprint=bundle.parser_bundle_fingerprint,
        gate_result=gate_result,
    )


__all__ = [
    "EXPECTED_PARSER_BUNDLE_FINGERPRINT",
    "EXPECTED_PRIOR_DIAGNOSTIC_SHA256",
    "Stage07SupervisorDiagnosticConfig",
    "Stage07SupervisorDiagnosticError",
    "Stage07SupervisorDiagnosticOutcome",
    "run_stage07_supervisor_diagnostic",
]
