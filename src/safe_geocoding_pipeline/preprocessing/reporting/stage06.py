from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import stat
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, NoReturn, cast

import pyarrow as pa
import pyarrow.parquet as pq

from ...execution_policy import require_goethe_nhr_slurm
from ..stages.s05_reconstruction import STAGE05_MANIFEST_NAME, stage05_schema
from ..stages.s06_exact_deduplication import (
    ROW_MAP_ID_COLUMNS,
    STAGE06_CANDIDATE_ID_DOMAIN,
    STAGE06_CANDIDATE_ID_VERSION,
    STAGE06_CONTRACT_VERSION,
    STAGE06_MANIFEST_NAME,
    STAGE06_PROFILE_VERSION,
    Stage06MaterializationOutcome,
    exact_candidate_id_v1,
    validate_stage06_bundle,
)
from .contracts import ReviewSubsetError
from .development import REVIEW_IDENTITIES_PATH, validate_development_review_bundle

STAGE06_REVIEW_CONTRACT_VERSION = "development_stage06_review_contract_v1"
STAGE06_REVIEW_SCHEMA_VERSION = "development_stage06_fixed500_schema_v1"
STAGE06_REVIEW_MANIFEST_VERSION = "development_stage06_review_manifest_v1"
STAGE06_REVIEW_VALIDATION_VERSION = "development_stage06_review_validation_v1"
STAGE06_REVIEW_PATH = "stage06_fixed500_verification.parquet"
STAGE06_REVIEW_MANIFEST_NAME = "stage06_review_manifest.json"
STAGE06_REVIEW_SUCCESS_MARKER = "_SUCCESS.json"
STAGE06_REVIEW_IN_PROGRESS_MARKER = "_IN_PROGRESS"
STAGE06_SUMMARY_JSON_PATH = "stage06_summary.json"
STAGE06_SUMMARY_MD_PATH = "stage06_summary.md"

_EXPECTED_REVIEW_ROWS = 500
_PRODUCTION_ROWS = 141_048_582
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_PERFORMANCE_KEYS = frozenset(
    {
        "ELAPSED_MILLISECONDS",
        "USER_CPU_MILLISECONDS",
        "SYSTEM_CPU_MILLISECONDS",
        "MAX_RSS_KIB",
    }
)


@dataclass(frozen=True, slots=True)
class Stage06ReviewRunConfig:
    stage05_output_directory: Path
    stage06_output_directory: Path
    expected_stage06_manifest_sha256: str
    development_review_bundle_directory: Path
    expected_development_review_manifest_sha256: str
    expected_review_subset_fingerprint: str
    expected_benchmark_fingerprint: str
    expected_stage02_logical_fingerprint: str
    output_directory: Path
    execution_git_sha: str
    performance_metrics: Mapping[str, int] | None = None
    production: bool = True
    authoritative_development: bool = True
    operational_metadata: Mapping[str, str] | None = None

    def validate(self) -> None:
        for value in (
            self.expected_stage06_manifest_sha256,
            self.expected_development_review_manifest_sha256,
            self.expected_review_subset_fingerprint,
            self.expected_benchmark_fingerprint,
            self.expected_stage02_logical_fingerprint,
        ):
            _digest_bytes(value)
        if _GIT_SHA_RE.fullmatch(self.execution_git_sha) is None:
            _fail("INVALID_GIT_COMMIT", "Execution Git SHA must be a full SHA")
        if self.performance_metrics is not None and (
            set(self.performance_metrics) != _PERFORMANCE_KEYS
            or any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in self.performance_metrics.values()
            )
            or self.performance_metrics["ELAPSED_MILLISECONDS"] < 1
        ):
            _fail("INVALID_PERFORMANCE_METRICS", "Performance metrics are invalid")
        if self.production and self.performance_metrics is None:
            _fail("PERFORMANCE_METRICS_REQUIRED", "Performance metrics are required")
        _reject_holdout_paths(
            self.stage05_output_directory,
            self.stage06_output_directory,
            self.development_review_bundle_directory,
            self.output_directory,
        )
        for key, value in (self.operational_metadata or {}).items():
            if (
                key not in {"execution_site", "slurm_job_id"}
                or not isinstance(value, str)
                or not value
                or "\x00" in value
                or len(value) > 128
            ):
                _fail("INVALID_OPERATIONAL_METADATA", "Review metadata is invalid")


@dataclass(frozen=True, slots=True)
class Stage06ReviewArtifactIdentity:
    relative_path: str
    size_bytes: int
    sha256: str
    row_count: int

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Stage06ReviewOutcome:
    output_directory: Path
    review_subset_fingerprint: str
    review_artifact_sha256: str
    manifest_sha256: str
    selected_row_count: int
    mismatch_count: int
    summary_json_path: Path
    summary_markdown_path: Path


@dataclass(frozen=True, slots=True)
class _SelectedRow:
    standard_id: bytes | None
    native_id: bytes | None
    standard_lower: str | None
    native_lower: str | None
    all_stage05_fields_exact: bool


def _fail(code: str, message: str) -> NoReturn:
    raise ReviewSubsetError(code, message)


def _digest_bytes(value: str) -> bytes:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail("INVALID_SHA256", "Digest must be canonical lowercase SHA-256")
    return bytes.fromhex(value)


def _reject_holdout_paths(*paths: Path) -> None:
    if any("holdout" in part.casefold() for path in paths for part in path.parts):
        _fail("HOLDOUT_ACCESS_PROHIBITED", "A Stage 6 review path names HOLDOUT")


def _require_file(path: Path, code: str) -> None:
    try:
        observed = path.stat(follow_symlinks=False)
    except OSError as error:
        raise ReviewSubsetError(code, "Protected file is unavailable") from error
    if path.is_symlink() or not stat.S_ISREG(observed.st_mode):
        _fail(code, "Protected path is not a regular file")


def _require_directory(path: Path, code: str) -> None:
    try:
        observed = path.stat(follow_symlinks=False)
    except OSError as error:
        raise ReviewSubsetError(code, "Protected directory is unavailable") from error
    if path.is_symlink() or not stat.S_ISDIR(observed.st_mode):
        _fail(code, "Protected path is not a directory")


def _require_mode(path: Path, expected: int) -> None:
    if stat.S_IMODE(path.stat(follow_symlinks=False).st_mode) != expected:
        _fail("PERMISSION_FAILURE", "Protected path is not owner-only")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise ReviewSubsetError(
            "ARTIFACT_READ_FAILURE", "Artifact read failed"
        ) from error
    return digest.hexdigest()


def _load_json(path: Path, code: str) -> dict[str, Any]:
    _require_file(path, code)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReviewSubsetError(code, "Protected JSON is malformed") from error
    if not isinstance(value, dict):
        _fail(code, "Protected JSON is not an object")
    return cast(dict[str, Any], value)


def _write_private(path: Path, payload: bytes) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise ReviewSubsetError(
            "CONTROLLED_WRITE_FAILURE", "Stage 6 review write failed"
        ) from error


def _write_json(path: Path, value: object) -> None:
    _write_private(
        path,
        (
            json.dumps(
                value, ensure_ascii=True, allow_nan=False, indent=2, sort_keys=True
            )
            + "\n"
        ).encode(),
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def stage06_review_schema(metadata: Mapping[bytes, bytes] | None = None) -> pa.Schema:
    return pa.schema(
        (
            pa.field("review_order", pa.uint32(), nullable=False),
            pa.field("development_review_id_v1", pa.binary(32), nullable=False),
            pa.field("stable_source_row_id_v1", pa.binary(32), nullable=False),
            pa.field(ROW_MAP_ID_COLUMNS[0], pa.binary(32), nullable=True),
            pa.field(ROW_MAP_ID_COLUMNS[1], pa.binary(32), nullable=True),
            pa.field("stage06_all_stage05_fields_exact", pa.bool_(), nullable=False),
            pa.field("stage06_standard_mapping_exact", pa.bool_(), nullable=False),
            pa.field("stage06_native_mapping_exact", pa.bool_(), nullable=False),
            pa.field("stage06_same_key_relation_exact", pa.bool_(), nullable=False),
            pa.field(
                "stage06_standard_registry_resolution_exact", pa.bool_(), nullable=False
            ),
            pa.field(
                "stage06_native_registry_resolution_exact", pa.bool_(), nullable=False
            ),
            pa.field(
                "stage06_standard_registry_occurrence_count", pa.uint64(), nullable=True
            ),
            pa.field(
                "stage06_native_registry_occurrence_count", pa.uint64(), nullable=True
            ),
        ),
        metadata=metadata,
    )


def stage06_review_schema_fingerprint() -> str:
    digest = hashlib.sha256(b"SAFE_DEVELOPMENT_STAGE06_REVIEW_SCHEMA_V1")
    for field in stage06_review_schema():
        for value in (field.name, str(field.type), str(field.nullable).lower()):
            encoded = value.encode()
            digest.update(len(encoded).to_bytes(8, "big") + encoded)
    return digest.hexdigest()


def _fixed_identities(config: Stage06ReviewRunConfig) -> pa.Table:
    outcome = validate_development_review_bundle(
        config.development_review_bundle_directory,
        expected_manifest_sha256=config.expected_development_review_manifest_sha256,
        expected_benchmark_fingerprint=config.expected_benchmark_fingerprint,
        expected_stage02_logical_fingerprint=config.expected_stage02_logical_fingerprint,
    )
    if outcome.review_subset_fingerprint != config.expected_review_subset_fingerprint:
        _fail("REVIEW_SUBSET_MISMATCH", "Fixed review subset fingerprint differs")
    path = config.development_review_bundle_directory / REVIEW_IDENTITIES_PATH
    _require_file(path, "REVIEW_IDENTITY_ARTIFACT_INVALID")
    _require_mode(path, 0o600)
    try:
        table = pq.ParquetFile(path, page_checksum_verification=True).read(
            use_threads=False
        )
    except (OSError, pa.ArrowException) as error:
        raise ReviewSubsetError(
            "REVIEW_IDENTITY_READ_FAILURE", "Fixed identities could not be read"
        ) from error
    expected = pa.schema(
        (
            pa.field("review_order", pa.uint32(), nullable=False),
            pa.field("development_review_id_v1", pa.binary(32), nullable=False),
            pa.field("stable_source_row_id_v1", pa.binary(32), nullable=False),
        )
    )
    stable = table.column("stable_source_row_id_v1").to_pylist()
    if (
        table.schema.remove_metadata() != expected
        or table.num_rows != _EXPECTED_REVIEW_ROWS
        or table.column("review_order").to_pylist() != list(range(1, 501))
        or len(set(stable)) != _EXPECTED_REVIEW_ROWS
    ):
        _fail("REVIEW_IDENTITY_MISMATCH", "Fixed identity rows are not exact")
    return table


def _artifact_paths(
    root: Path, manifest: Mapping[str, Any], key: str
) -> tuple[Path, ...]:
    physical = manifest.get("physical_identity")
    if not isinstance(physical, dict) or not isinstance(physical.get(key), list):
        _fail("MANIFEST_INVALID", "Artifact inventory is malformed")
    paths: list[Path] = []
    for raw in physical[key]:
        if not isinstance(raw, dict) or not isinstance(raw.get("relative_path"), str):
            _fail("MANIFEST_INVALID", "Artifact identity is malformed")
        paths.append(root / raw["relative_path"])
    return tuple(paths)


def _iter_aligned_batches(
    left: Iterable[pa.RecordBatch], right: Iterable[pa.RecordBatch]
) -> Iterable[tuple[pa.RecordBatch, pa.RecordBatch]]:
    left_iterator = iter(left)
    right_iterator = iter(right)
    left_batch: pa.RecordBatch | None = None
    right_batch: pa.RecordBatch | None = None
    left_offset = 0
    right_offset = 0
    while True:
        if left_batch is None:
            left_batch = next(left_iterator, None)
            left_offset = 0
        if right_batch is None:
            right_batch = next(right_iterator, None)
            right_offset = 0
        if left_batch is None or right_batch is None:
            if left_batch is None and right_batch is None:
                return
            _fail("ROW_MAP_MISMATCH", "Paired stream lengths differ")
        row_count = min(
            left_batch.num_rows - left_offset,
            right_batch.num_rows - right_offset,
        )
        if row_count < 1:
            _fail("ROW_MAP_MISMATCH", "Paired stream contains an empty batch")
        yield (
            left_batch.slice(left_offset, row_count),
            right_batch.slice(right_offset, row_count),
        )
        left_offset += row_count
        right_offset += row_count
        if left_offset == left_batch.num_rows:
            left_batch = None
        if right_offset == right_batch.num_rows:
            right_batch = None


def _paired_selected_rows(
    config: Stage06ReviewRunConfig,
    identities: pa.Table,
    stage06_manifest: Mapping[str, Any],
) -> dict[bytes, _SelectedRow]:
    stage05_manifest = _load_json(
        config.stage05_output_directory / STAGE05_MANIFEST_NAME,
        "STAGE05_MANIFEST_INVALID",
    )
    stage05_physical = stage05_manifest.get("physical_identity")
    if not isinstance(stage05_physical, dict) or not isinstance(
        stage05_physical.get("output_artifacts"), list
    ):
        _fail("STAGE05_MANIFEST_INVALID", "Stage 5 artifacts are malformed")
    stage05_paths = []
    for raw in stage05_physical["output_artifacts"]:
        if not isinstance(raw, dict) or not isinstance(raw.get("relative_path"), str):
            _fail("STAGE05_MANIFEST_INVALID", "Stage 5 artifact is malformed")
        stage05_paths.append(config.stage05_output_directory / raw["relative_path"])
    row_paths = _artifact_paths(
        config.stage06_output_directory, stage06_manifest, "row_map_artifacts"
    )
    if len(stage05_paths) != len(row_paths):
        _fail("ROW_MAP_MISMATCH", "Stage 5 and Stage 6 shard counts differ")
    target = set(
        cast(list[bytes], identities.column("stable_source_row_id_v1").to_pylist())
    )
    selected: dict[bytes, _SelectedRow] = {}
    columns = stage05_schema().names
    try:
        for stage05_path, row_path in zip(stage05_paths, row_paths, strict=True):
            upstream = pq.ParquetFile(stage05_path, page_checksum_verification=True)
            mapped = pq.ParquetFile(row_path, page_checksum_verification=True)
            upstream_batches = upstream.iter_batches(
                batch_size=2_048, use_threads=False
            )
            mapped_batches = mapped.iter_batches(batch_size=2_048, use_threads=False)
            for left, right in _iter_aligned_batches(upstream_batches, mapped_batches):
                exact = all(
                    left.column(index).equals(right.column(index))
                    for index in range(len(columns))
                )
                if not exact:
                    _fail("UPSTREAM_PRESERVATION_FAILURE", "A Stage 5 field differs")
                stable_index = right.schema.get_field_index("stable_source_row_id_v1")
                standard_lower_index = right.schema.get_field_index(
                    "stage05_standard_candidate_lower"
                )
                native_lower_index = right.schema.get_field_index(
                    "stage05_native_candidate_lower"
                )
                standard_available_index = right.schema.get_field_index(
                    "stage05_standard_candidate_available"
                )
                native_available_index = right.schema.get_field_index(
                    "stage05_native_candidate_available"
                )
                standard_id_index = right.schema.get_field_index(ROW_MAP_ID_COLUMNS[0])
                native_id_index = right.schema.get_field_index(ROW_MAP_ID_COLUMNS[1])
                for row_index in range(right.num_rows):
                    stable = right.column(stable_index)[row_index].as_py()
                    if stable not in target:
                        continue
                    if not isinstance(stable, bytes) or stable in selected:
                        _fail(
                            "REVIEW_IDENTITY_MISMATCH", "Fixed identity is duplicated"
                        )
                    standard_available = right.column(standard_available_index)[
                        row_index
                    ].as_py()
                    native_available = right.column(native_available_index)[
                        row_index
                    ].as_py()
                    standard_lower = (
                        right.column(standard_lower_index)[row_index].as_py()
                        if standard_available
                        else None
                    )
                    native_lower = (
                        right.column(native_lower_index)[row_index].as_py()
                        if native_available
                        else None
                    )
                    standard_id = right.column(standard_id_index)[row_index].as_py()
                    native_id = right.column(native_id_index)[row_index].as_py()
                    selected[stable] = _SelectedRow(
                        standard_id=standard_id,
                        native_id=native_id,
                        standard_lower=standard_lower,
                        native_lower=native_lower,
                        all_stage05_fields_exact=True,
                    )
    except ReviewSubsetError:
        raise
    except (OSError, pa.ArrowException) as error:
        raise ReviewSubsetError("ROW_MAP_READ_FAILURE", "Paired read failed") from error
    if set(selected) != target:
        _fail("REVIEW_IDENTITY_MISMATCH", "A fixed identity is absent")
    return selected


def _registry_rows(
    config: Stage06ReviewRunConfig,
    stage06_manifest: Mapping[str, Any],
    selected: Mapping[bytes, _SelectedRow],
) -> dict[bytes, tuple[str, int, int, int]]:
    expected_text: dict[bytes, str] = {}
    for row in selected.values():
        for candidate_id, text in (
            (row.standard_id, row.standard_lower),
            (row.native_id, row.native_lower),
        ):
            if candidate_id is None or text is None:
                continue
            prior = expected_text.setdefault(candidate_id, text)
            if prior != text:
                _fail("CANDIDATE_ID_COLLISION", "A fixed candidate ID has two texts")
    found: dict[bytes, tuple[str, int, int, int]] = {}
    for path in _artifact_paths(
        config.stage06_output_directory, stage06_manifest, "registry_artifacts"
    ):
        try:
            parquet = pq.ParquetFile(path, page_checksum_verification=True)
            for batch in parquet.iter_batches(batch_size=2_048, use_threads=False):
                for row_index in range(batch.num_rows):
                    candidate_id = batch.column(0)[row_index].as_py()
                    if candidate_id not in expected_text:
                        continue
                    if not isinstance(candidate_id, bytes) or candidate_id in found:
                        _fail(
                            "REGISTRY_RESOLUTION_FAILURE", "Registry ID is duplicated"
                        )
                    found[candidate_id] = (
                        batch.column(1)[row_index].as_py(),
                        int(batch.column(2)[row_index].as_py()),
                        int(batch.column(3)[row_index].as_py()),
                        int(batch.column(4)[row_index].as_py()),
                    )
        except ReviewSubsetError:
            raise
        except (OSError, pa.ArrowException) as error:
            raise ReviewSubsetError(
                "REGISTRY_READ_FAILURE", "Registry read failed"
            ) from error
    if set(found) != set(expected_text):
        _fail("REGISTRY_RESOLUTION_FAILURE", "A fixed candidate ID is unresolved")
    for candidate_id, text in expected_text.items():
        registered = found[candidate_id]
        if registered[0] != text or candidate_id != exact_candidate_id_v1(text):
            _fail("REGISTRY_RESOLUTION_FAILURE", "Registry candidate differs")
    return found


def _review_table(
    identities: pa.Table,
    selected: Mapping[bytes, _SelectedRow],
    registry: Mapping[bytes, tuple[str, int, int, int]],
    *,
    metadata: Mapping[bytes, bytes],
) -> tuple[pa.Table, dict[str, int]]:
    rows = [
        selected[cast(bytes, value)]
        for value in identities.column("stable_source_row_id_v1").to_pylist()
    ]
    arrays: list[pa.Array | pa.ChunkedArray] = [
        identities.column("review_order"),
        identities.column("development_review_id_v1"),
        identities.column("stable_source_row_id_v1"),
        pa.array([row.standard_id for row in rows], type=pa.binary(32)),
        pa.array([row.native_id for row in rows], type=pa.binary(32)),
    ]
    all_stage05: list[bool] = []
    standard_exact: list[bool] = []
    native_exact: list[bool] = []
    relation_exact: list[bool] = []
    standard_resolved: list[bool] = []
    native_resolved: list[bool] = []
    standard_counts: list[int | None] = []
    native_counts: list[int | None] = []
    occurrence_ids: list[bytes] = []
    same_row_equal = 0
    for row in rows:
        expected_standard = (
            exact_candidate_id_v1(row.standard_lower)
            if row.standard_lower is not None
            else None
        )
        expected_native = (
            exact_candidate_id_v1(row.native_lower)
            if row.native_lower is not None
            else None
        )
        standard_ok = row.standard_id == expected_standard
        native_ok = row.native_id == expected_native
        relation_ok = (row.standard_id == row.native_id) == (
            row.standard_lower is not None
            and row.native_lower is not None
            and row.standard_lower == row.native_lower
        )
        if row.standard_lower is not None and row.standard_lower == row.native_lower:
            same_row_equal += 1
        standard_resolution = row.standard_id is None or (
            row.standard_id in registry
            and registry[row.standard_id][0] == row.standard_lower
        )
        native_resolution = row.native_id is None or (
            row.native_id in registry and registry[row.native_id][0] == row.native_lower
        )
        all_stage05.append(row.all_stage05_fields_exact)
        standard_exact.append(standard_ok)
        native_exact.append(native_ok)
        relation_exact.append(relation_ok)
        standard_resolved.append(standard_resolution)
        native_resolved.append(native_resolution)
        standard_counts.append(
            registry[row.standard_id][1] if row.standard_id is not None else None
        )
        native_counts.append(
            registry[row.native_id][1] if row.native_id is not None else None
        )
        occurrence_ids.extend(
            value for value in (row.standard_id, row.native_id) if value is not None
        )
    arrays.extend(
        (
            pa.array(all_stage05),
            pa.array(standard_exact),
            pa.array(native_exact),
            pa.array(relation_exact),
            pa.array(standard_resolved),
            pa.array(native_resolved),
            pa.array(standard_counts, type=pa.uint64()),
            pa.array(native_counts, type=pa.uint64()),
        )
    )
    mismatches = sum(
        1
        for values in zip(
            all_stage05,
            standard_exact,
            native_exact,
            relation_exact,
            standard_resolved,
            native_resolved,
            strict=True,
        )
        if not all(values)
    )
    metrics = {
        "SELECTED_ROWS": len(rows),
        "DUPLICATE_IDENTITIES": 0,
        "AVAILABLE_OCCURRENCES": len(occurrence_ids),
        "UNIQUE_SELECTED_CANDIDATES": len(set(occurrence_ids)),
        "DUPLICATE_SELECTED_OCCURRENCES": len(occurrence_ids)
        - len(set(occurrence_ids)),
        "SAME_ROW_STANDARD_NATIVE_EXACT_EQUAL": same_row_equal,
        "MISMATCHES": mismatches,
    }
    return pa.Table.from_arrays(arrays, schema=stage06_review_schema(metadata)), metrics


def _write_parquet(table: pa.Table, path: Path) -> None:
    try:
        pq.write_table(
            table,
            path,
            version="2.6",
            compression="zstd",
            compression_level=3,
            use_dictionary=False,
            write_statistics=["review_order"],
            write_page_checksum=True,
            row_group_size=_EXPECTED_REVIEW_ROWS,
        )
        path.chmod(0o600)
    except (OSError, pa.ArrowException) as error:
        raise ReviewSubsetError(
            "REVIEW_WRITE_FAILURE", "Review Parquet write failed"
        ) from error


def _artifact(root: Path, relative: str, rows: int) -> Stage06ReviewArtifactIdentity:
    path = root / relative
    _require_file(path, "REVIEW_ARTIFACT_INVALID")
    _require_mode(path, 0o600)
    return Stage06ReviewArtifactIdentity(
        relative, path.stat().st_size, _sha256_file(path), rows
    )


def _planning_metrics(outcome: Stage06MaterializationOutcome) -> dict[str, int]:
    occurrences = cast(dict[str, int], outcome.metrics["CANDIDATE_OCCURRENCES"])[
        "TOTAL_AVAILABLE_OCCURRENCES"
    ]
    exact = cast(dict[str, int], outcome.metrics["EXACT_DEDUPLICATION"])
    projected_occurrences = (
        occurrences * _PRODUCTION_ROWS + outcome.row_count // 2
    ) // outcome.row_count
    projected_unique = (
        outcome.unique_candidate_count * _PRODUCTION_ROWS + outcome.row_count // 2
    ) // outcome.row_count
    return {
        "PRODUCTION_SOURCE_ROWS": _PRODUCTION_ROWS,
        "LINEAR_PROJECTED_CANDIDATE_OCCURRENCES": projected_occurrences,
        "LINEAR_PROJECTED_UNIQUE_CANDIDATES": projected_unique,
        "LINEAR_PROJECTED_STAGE7_PARSE_CALLS_SAVED": projected_occurrences
        - projected_unique,
        "PARSE_CALL_REDUCTION_MILLIONTHS": exact["PARSE_CALL_REDUCTION_MILLIONTHS"],
        "LINEAR_SCALING_GUARANTEED": 0,
    }


def _summary_payload(
    config: Stage06ReviewRunConfig,
    outcome: Stage06MaterializationOutcome,
    stage06_manifest: Mapping[str, Any],
    review_metrics: Mapping[str, int],
    review_sha: str,
) -> dict[str, Any]:
    scientific = stage06_manifest.get("scientific_identity")
    if not isinstance(scientific, dict):
        _fail("STAGE06_MANIFEST_INVALID", "Scientific identity is malformed")
    return {
        "status": "STAGE_6_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW",
        "stage": "STAGE_6",
        "contract": STAGE06_CONTRACT_VERSION,
        "profile": STAGE06_PROFILE_VERSION,
        "execution_git_sha": config.execution_git_sha,
        "slurm_job_id": (config.operational_metadata or {}).get("slurm_job_id", "0"),
        "fingerprints": {
            "stage06_logical": outcome.logical_dataset_sha256_v1,
            "stage06_schema": outcome.schema_fingerprint,
            "stage06_input_binding": outcome.input_binding_sha256,
            "stage06_manifest": outcome.manifest_sha256,
            "stage06_contract": scientific["stage06_contract_fingerprint"],
            "stage06_row_map_logical": outcome.row_map_logical_sha256_v1,
            "stage06_registry_logical": outcome.registry_logical_sha256_v1,
            "stage05_logical": scientific["upstream_stage05_logical_fingerprint"],
            "stage05_schema": scientific["upstream_stage05_schema_fingerprint"],
            "stage05_input_binding": scientific[
                "upstream_stage05_input_binding_sha256"
            ],
            "stage05_manifest": scientific["upstream_stage05_manifest_sha256"],
            "ordered_identity": outcome.ordered_identity_sha256,
            "benchmark": config.expected_benchmark_fingerprint,
            "fixed_500": config.expected_review_subset_fingerprint,
            "fixed_500_artifact": review_sha,
        },
        "candidate_id": {
            "version": STAGE06_CANDIDATE_ID_VERSION,
            "domain_hex": STAGE06_CANDIDATE_ID_DOMAIN.hex(),
            "digest": "SHA-256",
            "storage": "FIXED_SIZE_BINARY_32",
        },
        "metrics": outcome.metrics,
        "fixed_500": dict(review_metrics),
        "performance": {
            **dict(outcome.performance),
            **dict(config.performance_metrics or {}),
        },
        "production_planning_projection": _planning_metrics(outcome),
        "checks": {
            "ALL_STAGE05_FIELDS_EXACT": True,
            "SOURCE_ROWS_PRESERVED": True,
            "CANDIDATE_IDS_EXACT": True,
            "NULL_UNAVAILABLE_EXACT": True,
            "REGISTRY_RESOLUTION_EXACT": True,
            "COLLISION_GUARD_PASS": True,
            "OCCURRENCE_RECONCILIATION_PASS": True,
            "FIXED_500_PASS": review_metrics["MISMATCHES"] == 0,
            "HOLDOUT_ACCESSED": False,
            "PRODUCTION_STARTED": False,
            "STAGE7_STARTED": False,
        },
        "privacy": "AGGREGATE_ONLY_NO_PROTECTED_VALUES",
    }


def _render_markdown(payload: Mapping[str, Any]) -> str:
    metrics = cast(dict[str, Any], payload["metrics"])
    occurrences = cast(dict[str, int], metrics["CANDIDATE_OCCURRENCES"])
    exact = cast(dict[str, Any], metrics["EXACT_DEDUPLICATION"])
    fixed = cast(dict[str, int], payload["fixed_500"])
    fingerprints = cast(dict[str, str], payload["fingerprints"])
    return "\n".join(
        (
            "# Stage 6 DEVELOPMENT summary",
            "",
            "Status: `STAGE_6_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW`",
            "",
            f"- Source rows: {cast(dict[str, int], metrics['ROW_COUNTS'])['STAGE05_SOURCE_ROWS']:,}",
            f"- Candidate occurrences: {occurrences['TOTAL_AVAILABLE_OCCURRENCES']:,}",
            f"- Unique exact candidates: {exact['UNIQUE_EXACT_LOWER_CANDIDATES']:,}",
            f"- Duplicate downstream calls avoided: {exact['DUPLICATE_OCCURRENCES']:,}",
            f"- Parse-call reduction: {exact['PARSE_CALL_REDUCTION_MILLIONTHS'] / 10_000:.4f}%",
            f"- Fixed-500 mismatches: {fixed['MISMATCHES']}",
            f"- Stage 6 logical fingerprint: `{fingerprints['stage06_logical']}`",
            f"- Stage 6 schema fingerprint: `{fingerprints['stage06_schema']}`",
            f"- Stage 6 manifest fingerprint: `{fingerprints['stage06_manifest']}`",
            "",
            "The report is aggregate-only. No candidate text, address text, stable source identity, source filename, or company name is included.",
            "",
        )
    )


def materialize_stage06_development_review(
    config: Stage06ReviewRunConfig,
) -> Stage06ReviewOutcome:
    config.validate()
    if config.production:
        require_goethe_nhr_slurm("development-reporting-stage06-review")
    if config.output_directory.exists() or config.output_directory.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 6 review output already exists")
    outcome = validate_stage06_bundle(
        config.stage06_output_directory,
        expected_manifest_sha256=config.expected_stage06_manifest_sha256,
        stage05_output_directory=config.stage05_output_directory,
        authoritative_development=config.authoritative_development,
    )
    stage06_manifest = _load_json(
        config.stage06_output_directory / STAGE06_MANIFEST_NAME,
        "STAGE06_MANIFEST_INVALID",
    )
    identities = _fixed_identities(config)
    selected = _paired_selected_rows(config, identities, stage06_manifest)
    registry = _registry_rows(config, stage06_manifest, selected)
    metadata = {
        b"stage06_review_contract_version": STAGE06_REVIEW_CONTRACT_VERSION.encode(),
        b"stage06_review_schema_version": STAGE06_REVIEW_SCHEMA_VERSION.encode(),
        b"stage06_manifest_sha256": outcome.manifest_sha256.encode(),
        b"review_subset_fingerprint": config.expected_review_subset_fingerprint.encode(),
    }
    table, review_metrics = _review_table(
        identities, selected, registry, metadata=metadata
    )
    if review_metrics["MISMATCHES"]:
        _fail("FIXED500_MISMATCH", "Fixed-500 verification found a mismatch")

    parent = config.output_directory.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent.chmod(0o700)
    temporary = parent / f".{config.output_directory.name}.{os.getpid()}.in_progress"
    if temporary.exists() or temporary.is_symlink():
        _fail("OUTPUT_COLLISION", "Review temporary output already exists")
    temporary.mkdir(mode=0o700)
    _write_json(temporary / STAGE06_REVIEW_IN_PROGRESS_MARKER, {"status": "INCOMPLETE"})
    _write_parquet(table, temporary / STAGE06_REVIEW_PATH)
    review_artifact = _artifact(temporary, STAGE06_REVIEW_PATH, _EXPECTED_REVIEW_ROWS)
    summary = _summary_payload(
        config, outcome, stage06_manifest, review_metrics, review_artifact.sha256
    )
    _write_json(temporary / STAGE06_SUMMARY_JSON_PATH, summary)
    _write_private(
        temporary / STAGE06_SUMMARY_MD_PATH, _render_markdown(summary).encode()
    )
    summary_json = _artifact(temporary, STAGE06_SUMMARY_JSON_PATH, 0)
    summary_md = _artifact(temporary, STAGE06_SUMMARY_MD_PATH, 0)
    manifest = {
        "stage06_review_manifest_version": STAGE06_REVIEW_MANIFEST_VERSION,
        "status": "STAGE_6_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW",
        "scientific_identity": {
            "stage06_review_contract_version": STAGE06_REVIEW_CONTRACT_VERSION,
            "stage06_review_schema_version": STAGE06_REVIEW_SCHEMA_VERSION,
            "stage06_review_schema_fingerprint": stage06_review_schema_fingerprint(),
            "stage06_contract_version": STAGE06_CONTRACT_VERSION,
            "stage06_profile_version": STAGE06_PROFILE_VERSION,
            "stage06_logical_fingerprint": outcome.logical_dataset_sha256_v1,
            "stage06_schema_fingerprint": outcome.schema_fingerprint,
            "review_subset_fingerprint": config.expected_review_subset_fingerprint,
            "selected_row_count": _EXPECTED_REVIEW_ROWS,
            "review_metrics": review_metrics,
        },
        "physical_identity": {
            "accepted_development_review_manifest_sha256": config.expected_development_review_manifest_sha256,
            "stage05_manifest_sha256": cast(
                dict[str, Any], stage06_manifest["scientific_identity"]
            )["upstream_stage05_manifest_sha256"],
            "stage06_manifest_sha256": outcome.manifest_sha256,
            "artifacts": [
                review_artifact.to_dict(),
                summary_json.to_dict(),
                summary_md.to_dict(),
            ],
            "owner_only_permissions": True,
        },
        "validation": {
            "validation_contract_version": STAGE06_REVIEW_VALIDATION_VERSION,
            "accepted_fixed_subset_validated": "PASS",
            "same_ordered_500_identities": "PASS",
            "stage06_bundle_independently_validated": "PASS",
            "all_stage05_fields_exact": "PASS",
            "candidate_id_derivation_exact": "PASS",
            "registry_resolution_exact": "PASS",
            "occurrence_counts_resolved": "PASS",
            "no_source_row_disappears": "PASS",
            "protected_parquet_checksum_readback": "PASS",
            "aggregate_only_summary": "PASS",
            "holdout_exclusion": "PASS",
            "owner_only_permissions": "PASS",
            "atomic_publication": "PASS",
        },
        "operational_provenance": {
            "execution_git_sha": config.execution_git_sha,
            "created_at_utc": _utc_now(),
            "python_version": platform.python_version(),
            "pyarrow_version": pa.__version__,
            **dict(config.operational_metadata or {}),
        },
    }
    _write_json(temporary / STAGE06_REVIEW_MANIFEST_NAME, manifest)
    manifest_artifact = _artifact(temporary, STAGE06_REVIEW_MANIFEST_NAME, 0)
    _write_json(
        temporary / STAGE06_REVIEW_SUCCESS_MARKER,
        {
            "status": "STAGE_6_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW",
            "stage06_review_manifest_sha256": manifest_artifact.sha256,
            "stage06_manifest_sha256": outcome.manifest_sha256,
            "review_subset_fingerprint": config.expected_review_subset_fingerprint,
            "review_artifact_sha256": review_artifact.sha256,
            "selected_row_count": _EXPECTED_REVIEW_ROWS,
            "mismatch_count": 0,
        },
    )
    (temporary / STAGE06_REVIEW_IN_PROGRESS_MARKER).unlink()
    _fsync_directory(temporary)
    os.replace(temporary, config.output_directory)
    _fsync_directory(parent)
    return validate_stage06_development_review(
        config.output_directory,
        expected_manifest_sha256=manifest_artifact.sha256,
        expected_stage06_manifest_sha256=outcome.manifest_sha256,
        expected_review_subset_fingerprint=config.expected_review_subset_fingerprint,
        expected_identity_table=identities,
    )


def validate_stage06_development_review(
    output_directory: Path,
    *,
    expected_manifest_sha256: str,
    expected_stage06_manifest_sha256: str,
    expected_review_subset_fingerprint: str,
    expected_identity_table: pa.Table,
) -> Stage06ReviewOutcome:
    for digest in (
        expected_manifest_sha256,
        expected_stage06_manifest_sha256,
        expected_review_subset_fingerprint,
    ):
        _digest_bytes(digest)
    _reject_holdout_paths(output_directory)
    _require_directory(output_directory, "STAGE06_REVIEW_OUTPUT_INVALID")
    _require_mode(output_directory, 0o700)
    expected_files = {
        STAGE06_REVIEW_PATH,
        STAGE06_SUMMARY_JSON_PATH,
        STAGE06_SUMMARY_MD_PATH,
        STAGE06_REVIEW_MANIFEST_NAME,
        STAGE06_REVIEW_SUCCESS_MARKER,
    }
    if {path.name for path in output_directory.iterdir()} != expected_files:
        _fail("STAGE06_REVIEW_ARTIFACT_MISMATCH", "Review topology differs")
    for name in expected_files:
        _require_file(output_directory / name, "STAGE06_REVIEW_ARTIFACT_INVALID")
        _require_mode(output_directory / name, 0o600)
    manifest_path = output_directory / STAGE06_REVIEW_MANIFEST_NAME
    manifest_sha = _sha256_file(manifest_path)
    if manifest_sha != expected_manifest_sha256:
        _fail("STAGE06_REVIEW_MANIFEST_MISMATCH", "Review manifest SHA differs")
    manifest = _load_json(manifest_path, "STAGE06_REVIEW_MANIFEST_INVALID")
    success = _load_json(
        output_directory / STAGE06_REVIEW_SUCCESS_MARKER,
        "STAGE06_REVIEW_SUCCESS_INVALID",
    )
    scientific = manifest.get("scientific_identity")
    physical = manifest.get("physical_identity")
    validation = manifest.get("validation")
    if (
        manifest.get("stage06_review_manifest_version")
        != STAGE06_REVIEW_MANIFEST_VERSION
        or manifest.get("status")
        != "STAGE_6_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW"
        or success.get("status")
        != "STAGE_6_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW"
        or success.get("stage06_review_manifest_sha256") != manifest_sha
        or not isinstance(scientific, dict)
        or scientific.get("stage06_review_schema_fingerprint")
        != stage06_review_schema_fingerprint()
        or scientific.get("review_subset_fingerprint")
        != expected_review_subset_fingerprint
        or scientific.get("selected_row_count") != _EXPECTED_REVIEW_ROWS
        or cast(dict[str, int], scientific.get("review_metrics", {})).get("MISMATCHES")
        != 0
        or not isinstance(physical, dict)
        or physical.get("stage06_manifest_sha256") != expected_stage06_manifest_sha256
        or physical.get("owner_only_permissions") is not True
        or not isinstance(validation, dict)
        or validation.get("validation_contract_version")
        != STAGE06_REVIEW_VALIDATION_VERSION
        or any(
            value != "PASS"
            for key, value in validation.items()
            if key != "validation_contract_version"
        )
    ):
        _fail("STAGE06_REVIEW_MANIFEST_MISMATCH", "Review identity differs")
    artifacts = physical.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 3:
        _fail("STAGE06_REVIEW_MANIFEST_INVALID", "Review artifacts are malformed")
    by_path: dict[str, Mapping[str, Any]] = {}
    for raw in artifacts:
        if not isinstance(raw, dict) or not isinstance(raw.get("relative_path"), str):
            _fail("STAGE06_REVIEW_MANIFEST_INVALID", "Review artifact is malformed")
        path = output_directory / raw["relative_path"]
        if path.stat().st_size != raw.get("size_bytes") or _sha256_file(
            path
        ) != raw.get("sha256"):
            _fail("STAGE06_REVIEW_ARTIFACT_MISMATCH", "Review artifact SHA differs")
        by_path[raw["relative_path"]] = raw
    review_identity = by_path.get(STAGE06_REVIEW_PATH)
    if (
        review_identity is None
        or review_identity.get("row_count") != _EXPECTED_REVIEW_ROWS
    ):
        _fail("STAGE06_REVIEW_ARTIFACT_MISMATCH", "Review row count differs")
    try:
        table = pq.ParquetFile(
            output_directory / STAGE06_REVIEW_PATH, page_checksum_verification=True
        ).read(use_threads=False)
    except (OSError, pa.ArrowException) as error:
        raise ReviewSubsetError(
            "STAGE06_REVIEW_READ_FAILURE", "Review readback failed"
        ) from error
    if (
        table.schema.remove_metadata() != stage06_review_schema()
        or table.num_rows != _EXPECTED_REVIEW_ROWS
    ):
        _fail("STAGE06_REVIEW_SCHEMA_MISMATCH", "Review schema differs")
    for name in ("review_order", "development_review_id_v1", "stable_source_row_id_v1"):
        if not table.column(name).equals(expected_identity_table.column(name)):
            _fail("REVIEW_IDENTITY_MISMATCH", "Fixed identities or order differ")
    boolean_names = stage06_review_schema().names[5:11]
    if any(
        not all(cast(list[bool], table.column(name).to_pylist()))
        for name in boolean_names
    ):
        _fail("FIXED500_MISMATCH", "A fixed-500 exactness check failed")
    summary = _load_json(output_directory / STAGE06_SUMMARY_JSON_PATH, "UNSAFE_SUMMARY")
    if (
        summary.get("privacy") != "AGGREGATE_ONLY_NO_PROTECTED_VALUES"
        or cast(dict[str, Any], summary.get("fixed_500", {})).get("MISMATCHES") != 0
        or cast(dict[str, Any], summary.get("fingerprints", {})).get("stage06_manifest")
        != expected_stage06_manifest_sha256
        or (output_directory / STAGE06_SUMMARY_MD_PATH).read_text()
        != _render_markdown(summary)
    ):
        _fail("UNSAFE_SUMMARY", "Sanitized summary differs")
    review_sha = cast(str, review_identity["sha256"])
    if (
        success.get("stage06_manifest_sha256") != expected_stage06_manifest_sha256
        or success.get("review_subset_fingerprint")
        != expected_review_subset_fingerprint
        or success.get("review_artifact_sha256") != review_sha
        or success.get("selected_row_count") != _EXPECTED_REVIEW_ROWS
        or success.get("mismatch_count") != 0
    ):
        _fail("STAGE06_REVIEW_TERMINAL_MISMATCH", "Review terminal differs")
    return Stage06ReviewOutcome(
        output_directory=output_directory,
        review_subset_fingerprint=expected_review_subset_fingerprint,
        review_artifact_sha256=review_sha,
        manifest_sha256=manifest_sha,
        selected_row_count=_EXPECTED_REVIEW_ROWS,
        mismatch_count=0,
        summary_json_path=output_directory / STAGE06_SUMMARY_JSON_PATH,
        summary_markdown_path=output_directory / STAGE06_SUMMARY_MD_PATH,
    )


__all__ = [
    "STAGE06_REVIEW_CONTRACT_VERSION",
    "STAGE06_REVIEW_MANIFEST_NAME",
    "STAGE06_REVIEW_PATH",
    "STAGE06_SUMMARY_JSON_PATH",
    "STAGE06_SUMMARY_MD_PATH",
    "Stage06ReviewOutcome",
    "Stage06ReviewRunConfig",
    "materialize_stage06_development_review",
    "stage06_review_schema",
    "stage06_review_schema_fingerprint",
    "validate_stage06_development_review",
]
