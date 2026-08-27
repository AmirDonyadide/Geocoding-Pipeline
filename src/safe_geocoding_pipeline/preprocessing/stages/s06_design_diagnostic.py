from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, NoReturn, cast

import duckdb

from ...execution_policy import require_goethe_nhr_slurm
from .s05_reconstruction import (
    STAGE05_MANIFEST_NAME,
    validate_stage05_bundle,
    validate_stage05_runtime,
)

STAGE06_DESIGN_DIAGNOSTIC_VERSION = "stage06_design_diagnostic_v1"
STAGE06_DESIGN_DIAGNOSTIC_NAME = "stage06_design_diagnostic.json"
STAGE06_DESIGN_SUCCESS_NAME = "_SUCCESS.json"
EXPECTED_DUCKDB_VERSION = "1.5.5"

ACCEPTED_STAGE05_CONTRACT_VERSION = "stage05_address_reconstruction_contract_v2"
ACCEPTED_STAGE05_PROFILE_VERSION = "stage05_address_reconstruction_profile_v2"
ACCEPTED_STAGE05_SCHEMA_FINGERPRINT = (
    "63d4cdb3707eda65c67cc5196891fa5005adce2b12eb7109554793c48c5303c3"
)
ACCEPTED_STAGE05_LOGICAL_FINGERPRINT = (
    "ba5829621fc15347d7cd4e168a48587bab896cd0be98924627876ae853dfaff2"
)
ACCEPTED_STAGE05_INPUT_BINDING_SHA256 = (
    "7e68c33f7daa482b442eca82c00c6904ec5e38bec1b3fc598d5be4d52a6bcb9f"
)
ACCEPTED_STAGE05_MANIFEST_SHA256 = (
    "fd945163e3be0242c43b98972350904631279cb99f366baadb0a3094ab6a1fc5"
)
ACCEPTED_STAGE05_ORDERED_IDENTITY_SHA256 = (
    "fe2a4758582c1880d2b5c62dfc5c587d865e05d13033af9f5e8208b58e2a0487"
)
ACCEPTED_BENCHMARK_FINGERPRINT = (
    "014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf"
)
ACCEPTED_FIXED_500_FINGERPRINT = (
    "014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52"
)
ACCEPTED_DEVELOPMENT_ROWS = 35_000

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_MEMORY_LIMIT_RE = re.compile(r"^[1-9][0-9]*(?:MB|GB)$")


class Stage06DesignDiagnosticError(RuntimeError):
    """Privacy-safe failure for the aggregate Stage 6 design diagnostic."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class Stage06DesignDiagnosticConfig:
    stage05_output_directory: Path
    output_directory: Path
    execution_git_sha: str
    expected_stage05_manifest_sha256: str = ACCEPTED_STAGE05_MANIFEST_SHA256
    duckdb_memory_limit: str = "8GB"
    duckdb_threads: int = 4
    production: bool = True

    def validate(self) -> None:
        if _GIT_SHA_RE.fullmatch(self.execution_git_sha) is None:
            _fail("INVALID_GIT_COMMIT", "Execution Git commit must be a full SHA")
        if _SHA256_RE.fullmatch(self.expected_stage05_manifest_sha256) is None:
            _fail("INVALID_SHA256", "Stage 5 manifest SHA-256 is malformed")
        if self.expected_stage05_manifest_sha256 != ACCEPTED_STAGE05_MANIFEST_SHA256:
            _fail("WRONG_STAGE05_BINDING", "Stage 5 manifest is not accepted")
        if _MEMORY_LIMIT_RE.fullmatch(self.duckdb_memory_limit) is None:
            _fail("INVALID_MEMORY_LIMIT", "DuckDB memory limit is malformed")
        if (
            isinstance(self.duckdb_threads, bool)
            or self.duckdb_threads < 1
            or self.duckdb_threads > 64
        ):
            _fail("INVALID_THREAD_COUNT", "DuckDB thread count is invalid")
        _reject_holdout_paths(self.stage05_output_directory, self.output_directory)


@dataclass(frozen=True, slots=True)
class Stage06DesignDiagnosticOutcome:
    row_count: int
    candidate_occurrence_count: int
    unique_candidate_count: int
    output_directory: Path
    diagnostic_sha256: str


def _fail(code: str, message: str) -> NoReturn:
    raise Stage06DesignDiagnosticError(code, message)


def _reject_holdout_paths(*paths: Path) -> None:
    if any("holdout" in part.casefold() for path in paths for part in path.parts):
        _fail("HOLDOUT_ACCESS_PROHIBITED", "A diagnostic path names HOLDOUT")


def _require_mode(path: Path, expected: int) -> None:
    try:
        observed = path.stat(follow_symlinks=False)
    except OSError as error:
        raise Stage06DesignDiagnosticError(
            "CONTROLLED_PATH_INVALID", "Controlled path is unavailable"
        ) from error
    if path.is_symlink() or stat.S_IMODE(observed.st_mode) != expected:
        _fail("PERMISSION_FAILURE", "Controlled path is not owner-only")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> None:
    payload = (
        json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise Stage06DesignDiagnosticError(
            "CONTROLLED_WRITE_FAILURE", "Diagnostic output could not be written"
        ) from error


def _load_manifest(root: Path) -> dict[str, Any]:
    path = root / STAGE05_MANIFEST_NAME
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Stage06DesignDiagnosticError(
            "STAGE05_MANIFEST_INVALID", "Stage 5 manifest is malformed"
        ) from error
    if not isinstance(value, dict):
        _fail("STAGE05_MANIFEST_INVALID", "Stage 5 manifest is not an object")
    return cast(dict[str, Any], value)


def _artifact_paths(root: Path, manifest: Mapping[str, Any]) -> tuple[Path, ...]:
    physical = manifest.get("physical_identity")
    if not isinstance(physical, dict):
        _fail("STAGE05_MANIFEST_INVALID", "Stage 5 physical identity is malformed")
    artifacts = physical.get("output_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        _fail("STAGE05_MANIFEST_INVALID", "Stage 5 output artifacts are absent")
    paths: list[Path] = []
    for sequence, raw in enumerate(artifacts, start=1):
        if not isinstance(raw, dict):
            _fail("STAGE05_MANIFEST_INVALID", "Stage 5 artifact is malformed")
        relative = raw.get("relative_path")
        if relative != f"data/part-{sequence:06d}.parquet":
            _fail("STAGE05_MANIFEST_INVALID", "Stage 5 artifact order differs")
        paths.append(root / relative)
    return tuple(paths)


def _one_uint(connection: duckdb.DuckDBPyConnection, query: str) -> int:
    row = connection.execute(query).fetchone()
    if row is None or len(row) != 1 or isinstance(row[0], bool):
        _fail("DIAGNOSTIC_QUERY_FAILURE", "Aggregate query did not return one integer")
    return int(row[0])


def _row_uints(
    connection: duckdb.DuckDBPyConnection, query: str, width: int
) -> tuple[int, ...]:
    row = connection.execute(query).fetchone()
    if (
        row is None
        or len(row) != width
        or any(isinstance(value, bool) for value in row)
    ):
        _fail("DIAGNOSTIC_QUERY_FAILURE", "Aggregate query shape is invalid")
    return tuple(int(value) for value in row)


def _distribution(
    connection: duckdb.DuckDBPyConnection, *, value_column: str
) -> dict[str, int]:
    if value_column not in {"occurrence_count", "clean_surface_count"}:
        _fail("INTERNAL_DIAGNOSTIC_ERROR", "Distribution column is not allowlisted")
    rows = connection.execute(
        f"SELECT {value_column}, count(*) FROM candidate_groups "
        f"GROUP BY {value_column} ORDER BY {value_column}"
    ).fetchall()
    return {str(int(value)): int(count) for value, count in rows}


def _nearest_rank(
    connection: duckdb.DuckDBPyConnection, *, fraction: float, duplicates_only: bool
) -> int:
    where = "WHERE occurrence_count > 1" if duplicates_only else ""
    count = _one_uint(connection, f"SELECT count(*) FROM candidate_groups {where}")
    if count == 0:
        return 0
    offset = math.ceil(fraction * count) - 1
    return _one_uint(
        connection,
        "SELECT occurrence_count FROM candidate_groups "
        f"{where} ORDER BY occurrence_count LIMIT 1 OFFSET {offset}",
    )


def _directory_usage(path: Path) -> tuple[int, int]:
    total_bytes = 0
    files = 0
    if not path.exists():
        return total_bytes, files
    for candidate in path.rglob("*"):
        if candidate.is_file() and not candidate.is_symlink():
            files += 1
            total_bytes += candidate.stat(follow_symlinks=False).st_size
    return total_bytes, files


def _build_candidate_groups(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        CREATE OR REPLACE TEMP TABLE stage06_occurrences AS
        SELECT
            stable_source_row_id_v1 AS source_identity,
            'STANDARD'::VARCHAR AS representation,
            encode(stage05_standard_candidate_lower) AS candidate_bytes,
            encode(stage05_standard_candidate_clean) AS clean_surface_bytes,
            length(stage05_standard_candidate_lower)::UBIGINT AS candidate_codepoints
        FROM stage05_input
        WHERE stage05_standard_candidate_available
        UNION ALL
        SELECT
            stable_source_row_id_v1 AS source_identity,
            'NATIVE'::VARCHAR AS representation,
            encode(stage05_native_candidate_lower) AS candidate_bytes,
            encode(stage05_native_candidate_clean) AS clean_surface_bytes,
            length(stage05_native_candidate_lower)::UBIGINT AS candidate_codepoints
        FROM stage05_input
        WHERE stage05_native_candidate_available
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE TEMP TABLE candidate_groups AS
        SELECT
            candidate_bytes,
            count(*)::UBIGINT AS occurrence_count,
            count(*) FILTER (WHERE representation = 'STANDARD')::UBIGINT
                AS standard_occurrence_count,
            count(*) FILTER (WHERE representation = 'NATIVE')::UBIGINT
                AS native_occurrence_count,
            count(DISTINCT source_identity)::UBIGINT AS source_row_count,
            count(DISTINCT clean_surface_bytes)::UBIGINT AS clean_surface_count,
            min(candidate_codepoints)::UBIGINT AS candidate_codepoints,
            max(candidate_codepoints)::UBIGINT AS maximum_candidate_codepoints
        FROM stage06_occurrences
        GROUP BY candidate_bytes
        """
    )
    inconsistent_lengths = _one_uint(
        connection,
        "SELECT count(*) FROM candidate_groups "
        "WHERE candidate_codepoints != maximum_candidate_codepoints",
    )
    if inconsistent_lengths:
        _fail("EXACT_GROUPING_FAILURE", "One exact candidate has inconsistent length")


def _length_relationship(connection: duckdb.DuckDBPyConnection) -> dict[str, object]:
    rows = connection.execute(
        """
        SELECT
            CASE
                WHEN candidate_codepoints <= 24 THEN '000000001_TO_000000024'
                WHEN candidate_codepoints <= 49 THEN '000000025_TO_000000049'
                WHEN candidate_codepoints <= 99 THEN '000000050_TO_000000099'
                WHEN candidate_codepoints <= 1023 THEN '000000100_TO_000001023'
                WHEN candidate_codepoints <= 65535 THEN '000001024_TO_000065535'
                WHEN candidate_codepoints <= 999999 THEN '000065536_TO_000999999'
                ELSE '001000000_OR_MORE'
            END AS length_bucket,
            count(*)::UBIGINT AS unique_groups,
            sum(occurrence_count)::UBIGINT AS occurrences,
            count(*) FILTER (WHERE occurrence_count > 1)::UBIGINT
                AS duplicate_groups,
            sum(occurrence_count - 1)::UBIGINT AS duplicate_occurrences
        FROM candidate_groups
        GROUP BY length_bucket
        ORDER BY length_bucket
        """
    ).fetchall()
    return {
        str(bucket): {
            "UNIQUE_GROUPS": int(groups),
            "OCCURRENCES": int(occurrences),
            "DUPLICATE_GROUPS": int(duplicate_groups),
            "DUPLICATE_OCCURRENCES": int(duplicate_occurrences),
        }
        for bucket, groups, occurrences, duplicate_groups, duplicate_occurrences in rows
    }


def _collect_metrics(connection: duckdb.DuckDBPyConnection) -> dict[str, object]:
    input_rows = _one_uint(connection, "SELECT count(*) FROM stage05_input")
    (
        standard_available,
        standard_unavailable,
        native_available,
        native_unavailable,
        same_row_equal,
        standard_available_empty,
        native_available_empty,
        standard_unavailable_nonempty,
        native_unavailable_nonempty,
    ) = _row_uints(
        connection,
        """
        SELECT
            count(*) FILTER (WHERE stage05_standard_candidate_available),
            count(*) FILTER (WHERE NOT stage05_standard_candidate_available),
            count(*) FILTER (WHERE stage05_native_candidate_available),
            count(*) FILTER (WHERE NOT stage05_native_candidate_available),
            count(*) FILTER (
                WHERE stage05_standard_candidate_available
                  AND stage05_native_candidate_available
                  AND encode(stage05_standard_candidate_lower)
                      = encode(stage05_native_candidate_lower)
            ),
            count(*) FILTER (
                WHERE stage05_standard_candidate_available
                  AND octet_length(encode(stage05_standard_candidate_lower)) = 0
            ),
            count(*) FILTER (
                WHERE stage05_native_candidate_available
                  AND octet_length(encode(stage05_native_candidate_lower)) = 0
            ),
            count(*) FILTER (
                WHERE NOT stage05_standard_candidate_available
                  AND octet_length(encode(stage05_standard_candidate_lower)) != 0
            ),
            count(*) FILTER (
                WHERE NOT stage05_native_candidate_available
                  AND octet_length(encode(stage05_native_candidate_lower)) != 0
            )
        FROM stage05_input
        """,
        9,
    )
    total_occurrences = _one_uint(
        connection, "SELECT count(*) FROM stage06_occurrences"
    )
    unique_candidates = _one_uint(connection, "SELECT count(*) FROM candidate_groups")
    duplicate_occurrences = total_occurrences - unique_candidates
    singleton_groups = _one_uint(
        connection,
        "SELECT count(*) FROM candidate_groups WHERE occurrence_count = 1",
    )
    duplicate_groups = _one_uint(
        connection,
        "SELECT count(*) FROM candidate_groups WHERE occurrence_count > 1",
    )
    maximum_group_size = _one_uint(
        connection, "SELECT coalesce(max(occurrence_count), 0) FROM candidate_groups"
    )
    spanning_source_rows = _one_uint(
        connection,
        "SELECT count(*) FROM candidate_groups "
        "WHERE occurrence_count > 1 AND source_row_count > 1",
    )
    standard_only, native_only, both = _row_uints(
        connection,
        """
        SELECT
            count(*) FILTER (
                WHERE standard_occurrence_count > 0 AND native_occurrence_count = 0
            ),
            count(*) FILTER (
                WHERE standard_occurrence_count = 0 AND native_occurrence_count > 0
            ),
            count(*) FILTER (
                WHERE standard_occurrence_count > 0 AND native_occurrence_count > 0
            )
        FROM candidate_groups
        """,
        3,
    )
    multiple_clean_surfaces = _one_uint(
        connection,
        "SELECT count(*) FROM candidate_groups WHERE clean_surface_count > 1",
    )
    empty_registry_candidates = _one_uint(
        connection,
        "SELECT count(*) FROM candidate_groups WHERE octet_length(candidate_bytes) = 0",
    )
    occurrence_reconciliation = _row_uints(
        connection,
        """
        SELECT
            coalesce(sum(occurrence_count), 0),
            coalesce(sum(standard_occurrence_count), 0),
            coalesce(sum(native_occurrence_count), 0)
        FROM candidate_groups
        """,
        3,
    )
    return {
        "ROW_COUNTS": {
            "STAGE05_SOURCE_ROWS": input_rows,
        },
        "CANDIDATE_OCCURRENCES": {
            "STANDARD_AVAILABLE": standard_available,
            "STANDARD_UNAVAILABLE": standard_unavailable,
            "NATIVE_AVAILABLE": native_available,
            "NATIVE_UNAVAILABLE": native_unavailable,
            "TOTAL_AVAILABLE_OCCURRENCES": total_occurrences,
            "SAME_ROW_STANDARD_NATIVE_EXACT_LOWER_EQUAL": same_row_equal,
        },
        "EXACT_DEDUPLICATION": {
            "UNIQUE_EXACT_LOWER_CANDIDATES": unique_candidates,
            "DUPLICATE_OCCURRENCES": duplicate_occurrences,
            "UNIQUE_TO_OCCURRENCE_RATIO_MILLIONTHS": (
                (unique_candidates * 1_000_000 + total_occurrences // 2)
                // total_occurrences
                if total_occurrences
                else 0
            ),
            "PARSE_CALL_REDUCTION_MILLIONTHS": (
                (duplicate_occurrences * 1_000_000 + total_occurrences // 2)
                // total_occurrences
                if total_occurrences
                else 0
            ),
            "SINGLETON_GROUPS": singleton_groups,
            "DUPLICATE_GROUPS": duplicate_groups,
            "DUPLICATE_GROUPS_SPANNING_MULTIPLE_SOURCE_ROWS": spanning_source_rows,
            "MAXIMUM_GROUP_SIZE": maximum_group_size,
            "ALL_GROUP_SIZE_DISTRIBUTION": _distribution(
                connection, value_column="occurrence_count"
            ),
            "ALL_GROUP_SIZE_QUANTILES_NEAREST_RANK": {
                "P50": _nearest_rank(connection, fraction=0.50, duplicates_only=False),
                "P90": _nearest_rank(connection, fraction=0.90, duplicates_only=False),
                "P95": _nearest_rank(connection, fraction=0.95, duplicates_only=False),
                "P99": _nearest_rank(connection, fraction=0.99, duplicates_only=False),
            },
            "DUPLICATE_GROUP_SIZE_QUANTILES_NEAREST_RANK": {
                "P50": _nearest_rank(connection, fraction=0.50, duplicates_only=True),
                "P90": _nearest_rank(connection, fraction=0.90, duplicates_only=True),
                "P95": _nearest_rank(connection, fraction=0.95, duplicates_only=True),
                "P99": _nearest_rank(connection, fraction=0.99, duplicates_only=True),
            },
        },
        "REPRESENTATION_CONTRIBUTION": {
            "STANDARD_ONLY_CANDIDATE_GROUPS": standard_only,
            "NATIVE_ONLY_CANDIDATE_GROUPS": native_only,
            "BOTH_REPRESENTATION_CANDIDATE_GROUPS": both,
            "CROSS_REPRESENTATION_CANDIDATE_GROUPS": both,
        },
        "CLEAN_SURFACE_VARIANTS": {
            "CANONICAL_GROUPS_WITH_MULTIPLE_CLEAN_SURFACES": multiple_clean_surfaces,
            "CLEAN_SURFACE_COUNT_DISTRIBUTION": _distribution(
                connection, value_column="clean_surface_count"
            ),
        },
        "CANDIDATE_LENGTH_RELATIONSHIP": _length_relationship(connection),
        "EMPTY_AND_UNAVAILABLE": {
            "STANDARD_AVAILABLE_EMPTY": standard_available_empty,
            "NATIVE_AVAILABLE_EMPTY": native_available_empty,
            "STANDARD_UNAVAILABLE_NONEMPTY": standard_unavailable_nonempty,
            "NATIVE_UNAVAILABLE_NONEMPTY": native_unavailable_nonempty,
            "EMPTY_REGISTRY_CANDIDATES": empty_registry_candidates,
            "UNAVAILABLE_OCCURRENCES_EXCLUDED_FROM_REGISTRY": (
                standard_unavailable + native_unavailable
            ),
        },
        "RECONCILIATION": {
            "REGISTRY_OCCURRENCE_SUM": occurrence_reconciliation[0],
            "REGISTRY_STANDARD_OCCURRENCE_SUM": occurrence_reconciliation[1],
            "REGISTRY_NATIVE_OCCURRENCE_SUM": occurrence_reconciliation[2],
            "TOTAL_OCCURRENCE_MISMATCHES": abs(
                occurrence_reconciliation[0] - total_occurrences
            ),
            "STANDARD_OCCURRENCE_MISMATCHES": abs(
                occurrence_reconciliation[1] - standard_available
            ),
            "NATIVE_OCCURRENCE_MISMATCHES": abs(
                occurrence_reconciliation[2] - native_available
            ),
        },
    }


def _validate_metrics(metrics: Mapping[str, object]) -> tuple[int, int, int]:
    rows = cast(dict[str, int], metrics["ROW_COUNTS"])["STAGE05_SOURCE_ROWS"]
    occurrences = cast(dict[str, int], metrics["CANDIDATE_OCCURRENCES"])
    exact = cast(dict[str, Any], metrics["EXACT_DEDUPLICATION"])
    empty = cast(dict[str, int], metrics["EMPTY_AND_UNAVAILABLE"])
    reconciliation = cast(dict[str, int], metrics["RECONCILIATION"])
    total = occurrences["TOTAL_AVAILABLE_OCCURRENCES"]
    unique = int(exact["UNIQUE_EXACT_LOWER_CANDIDATES"])
    if rows != ACCEPTED_DEVELOPMENT_ROWS:
        _fail("ROW_COUNT_MISMATCH", "Diagnostic row count is not 35,000")
    if total != occurrences["STANDARD_AVAILABLE"] + occurrences["NATIVE_AVAILABLE"]:
        _fail("OCCURRENCE_RECONCILIATION_FAILURE", "Occurrence total differs")
    if unique + int(exact["DUPLICATE_OCCURRENCES"]) != total:
        _fail("OCCURRENCE_RECONCILIATION_FAILURE", "Unique/duplicate total differs")
    if any(
        value for key, value in empty.items() if key.endswith(("EMPTY", "NONEMPTY"))
    ):
        _fail("EMPTY_CANDIDATE_FAILURE", "Empty/unavailable semantics differ")
    if any(
        value for key, value in reconciliation.items() if key.endswith("MISMATCHES")
    ):
        _fail("OCCURRENCE_RECONCILIATION_FAILURE", "Registry counts differ")
    return rows, total, unique


def run_stage06_design_diagnostic(
    config: Stage06DesignDiagnosticConfig,
) -> Stage06DesignDiagnosticOutcome:
    """Publish aggregate-only exact-candidate evidence for Stage 6 design."""
    config.validate()
    validate_stage05_runtime()
    if duckdb.__version__ != EXPECTED_DUCKDB_VERSION:
        _fail("DUCKDB_VERSION_MISMATCH", "DuckDB runtime is not pinned")
    if config.production:
        require_goethe_nhr_slurm("stage06-design-diagnostic")
    if config.output_directory.exists() or config.output_directory.is_symlink():
        _fail("OUTPUT_COLLISION", "Diagnostic output already exists")
    _require_mode(config.stage05_output_directory, 0o700)
    if (
        _sha256_file(config.stage05_output_directory / STAGE05_MANIFEST_NAME)
        != config.expected_stage05_manifest_sha256
    ):
        _fail("WRONG_STAGE05_BINDING", "Stage 5 manifest bytes differ")
    try:
        stage05_outcome = validate_stage05_bundle(
            config.stage05_output_directory,
            expected_manifest_sha256=config.expected_stage05_manifest_sha256,
            authoritative_development=True,
        )
    except Exception as error:
        raise Stage06DesignDiagnosticError(
            "STAGE05_VALIDATION_FAILURE", "Accepted Stage 5 validation failed"
        ) from error
    if (
        stage05_outcome.logical_dataset_sha256_v1
        != ACCEPTED_STAGE05_LOGICAL_FINGERPRINT
        or stage05_outcome.schema_fingerprint != ACCEPTED_STAGE05_SCHEMA_FINGERPRINT
        or stage05_outcome.input_binding_sha256 != ACCEPTED_STAGE05_INPUT_BINDING_SHA256
        or stage05_outcome.manifest_sha256 != ACCEPTED_STAGE05_MANIFEST_SHA256
        or stage05_outcome.ordered_identity_sha256
        != ACCEPTED_STAGE05_ORDERED_IDENTITY_SHA256
        or stage05_outcome.row_count != ACCEPTED_DEVELOPMENT_ROWS
    ):
        _fail("WRONG_STAGE05_BINDING", "Stage 5 scientific identity differs")
    manifest = _load_manifest(config.stage05_output_directory)

    parent = config.output_directory.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent.chmod(0o700)
    _require_mode(parent, 0o700)
    temporary = parent / f".{config.output_directory.name}.{os.getpid()}.in_progress"
    if temporary.exists() or temporary.is_symlink():
        _fail("OUTPUT_COLLISION", "Diagnostic temporary output already exists")
    temporary.mkdir(mode=0o700)
    spill = temporary / "duckdb_spill"
    spill.mkdir(mode=0o700)
    database_path = temporary / "stage06_design.duckdb"
    started = time.perf_counter()
    connection: duckdb.DuckDBPyConnection | None = None
    try:
        connection = duckdb.connect(str(database_path))
        database_path.chmod(0o600)
        connection.execute("SET memory_limit=?", [config.duckdb_memory_limit])
        connection.execute("SET threads=?", [config.duckdb_threads])
        connection.execute("SET temp_directory=?", [str(spill.resolve())])
        connection.execute("SET preserve_insertion_order=false")
        connection.read_parquet(
            [
                str(path.resolve())
                for path in _artifact_paths(config.stage05_output_directory, manifest)
            ]
        ).create_view("stage05_input")
        aggregation_started = time.perf_counter()
        _build_candidate_groups(connection)
        metrics = _collect_metrics(connection)
        aggregation_milliseconds = round(
            (time.perf_counter() - aggregation_started) * 1_000
        )
        rows, occurrences, unique = _validate_metrics(metrics)
        spill_bytes, spill_files = _directory_usage(spill)
    except Stage06DesignDiagnosticError:
        raise
    except (OSError, duckdb.Error) as error:
        raise Stage06DesignDiagnosticError(
            "DIAGNOSTIC_EXECUTION_FAILURE", "DuckDB diagnostic execution failed"
        ) from error
    finally:
        if connection is not None:
            connection.close()
    total_milliseconds = round((time.perf_counter() - started) * 1_000)
    database_path.unlink()
    for path in spill.iterdir():
        if path.is_file() and not path.is_symlink():
            path.unlink()
    spill.rmdir()

    result = {
        "diagnostic_version": STAGE06_DESIGN_DIAGNOSTIC_VERSION,
        "status": "STAGE06_DESIGN_DIAGNOSTIC_COMPLETE",
        "execution_git_sha": config.execution_git_sha,
        "stage05_binding": {
            "contract": ACCEPTED_STAGE05_CONTRACT_VERSION,
            "profile": ACCEPTED_STAGE05_PROFILE_VERSION,
            "schema_fingerprint": ACCEPTED_STAGE05_SCHEMA_FINGERPRINT,
            "logical_fingerprint": ACCEPTED_STAGE05_LOGICAL_FINGERPRINT,
            "input_binding_sha256": ACCEPTED_STAGE05_INPUT_BINDING_SHA256,
            "manifest_sha256": ACCEPTED_STAGE05_MANIFEST_SHA256,
            "ordered_identity_sha256": ACCEPTED_STAGE05_ORDERED_IDENTITY_SHA256,
            "benchmark_fingerprint": ACCEPTED_BENCHMARK_FINGERPRINT,
            "fixed_500_fingerprint": ACCEPTED_FIXED_500_FINGERPRINT,
            "rows": ACCEPTED_DEVELOPMENT_ROWS,
        },
        "dedup_key_under_evaluation": {
            "standard_column": "stage05_standard_candidate_lower",
            "native_column": "stage05_native_candidate_lower",
            "comparison": "EXACT_UTF8_BYTES",
            "scope": "GLOBAL_ACROSS_STANDARD_AND_NATIVE_OCCURRENCES",
            "normalization_added": "NONE",
        },
        "metrics": metrics,
        "performance": {
            "AGGREGATION_MILLISECONDS": aggregation_milliseconds,
            "TOTAL_DIAGNOSTIC_MILLISECONDS": total_milliseconds,
            "DUCKDB_MEMORY_LIMIT": config.duckdb_memory_limit,
            "DUCKDB_THREADS": config.duckdb_threads,
            "DUCKDB_SPILL_BYTES": spill_bytes,
            "DUCKDB_SPILL_FILES": spill_files,
        },
        "runtime": {
            "DUCKDB_VERSION": duckdb.__version__,
        },
        "privacy": {
            "ROW_VALUES_EMITTED": False,
            "CANDIDATE_TEXT_EMITTED": False,
            "STABLE_IDENTITIES_EMITTED": False,
            "SOURCE_FILENAMES_EMITTED": False,
            "HOLDOUT_ACCESSED": False,
        },
    }
    diagnostic_path = temporary / STAGE06_DESIGN_DIAGNOSTIC_NAME
    _write_json(diagnostic_path, result)
    diagnostic_sha256 = _sha256_file(diagnostic_path)
    _write_json(
        temporary / STAGE06_DESIGN_SUCCESS_NAME,
        {
            "status": "STAGE06_DESIGN_DIAGNOSTIC_COMPLETE",
            "diagnostic_sha256": diagnostic_sha256,
            "row_count": rows,
            "candidate_occurrence_count": occurrences,
            "unique_candidate_count": unique,
        },
    )
    for path in temporary.iterdir():
        _require_mode(path, 0o600)
    descriptor = os.open(temporary, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, config.output_directory)
    descriptor = os.open(parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return Stage06DesignDiagnosticOutcome(
        row_count=rows,
        candidate_occurrence_count=occurrences,
        unique_candidate_count=unique,
        output_directory=config.output_directory,
        diagnostic_sha256=diagnostic_sha256,
    )


__all__ = [
    "ACCEPTED_STAGE05_MANIFEST_SHA256",
    "STAGE06_DESIGN_DIAGNOSTIC_NAME",
    "Stage06DesignDiagnosticConfig",
    "Stage06DesignDiagnosticError",
    "Stage06DesignDiagnosticOutcome",
    "run_stage06_design_diagnostic",
]
