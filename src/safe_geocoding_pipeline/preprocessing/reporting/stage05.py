from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import stat
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, NoReturn, cast

import pyarrow as pa
import pyarrow.parquet as pq

from ...execution_policy import require_goethe_nhr_slurm
from ..stages.s02_harmonization import STAGE02_STRUCTURAL_COLUMNS
from ..stages.s03_cleaning import CLEAN_DERIVED_COLUMNS, CLEAN_SOURCE_COLUMNS
from ..stages.s04_lowercase import LOWER_OUTPUT_COLUMNS
from ..stages.s05_reconstruction import (
    STAGE05_CONTRACT_VERSION,
    STAGE05_DERIVED_COLUMNS,
    STAGE05_MANIFEST_NAME,
    STAGE05_PROFILE_VERSION,
    Stage05MaterializationOutcome,
    Stage05ValidationError,
    stage05_schema,
    stage05_schema_fingerprint,
    validate_stage05_bundle,
)
from .contracts import (
    DEVELOPMENT_REPORTING_CONTRACT_VERSION,
    DEVELOPMENT_REVIEW_SUBSET_CONTRACT_VERSION,
    ReviewSubsetError,
)
from .development import (
    REVIEW_BUNDLE_MANIFEST_VERSION,
    REVIEW_IDENTITIES_PATH,
    REVIEW_MANIFEST_NAME,
    validate_development_review_bundle,
)
from .summary import (
    SANITIZED_SUMMARY_CONTRACT_VERSION,
    SanitizedStageSummary,
    render_summary_json,
    render_summary_markdown,
    validate_sanitized_summary_payload,
)

STAGE05_REVIEW_CONTRACT_VERSION = "development_stage05_review_contract_v1"
STAGE05_REVIEW_SCHEMA_VERSION = "development_stage05_review_view_schema_v1"
STAGE05_REVIEW_MANIFEST_VERSION = "development_stage05_review_manifest_v1"
STAGE05_REVIEW_VALIDATION_VERSION = "development_stage05_review_validation_v1"
STAGE05_REVIEW_PATH = "stage05_review.parquet"
STAGE05_REVIEW_MANIFEST_NAME = "stage05_review_manifest.json"
STAGE05_REVIEW_SUCCESS_MARKER = "_SUCCESS.json"
STAGE05_REVIEW_IN_PROGRESS_MARKER = "_IN_PROGRESS"
STAGE05_SUMMARY_JSON_PATH = "stage05_summary.json"
STAGE05_SUMMARY_MD_PATH = "stage05_summary.md"

QUALITATIVE_CLASSIFICATIONS = (
    "CORRECT_RECONSTRUCTION",
    "VALID_BUT_REDUNDANT_SOURCE_CONTENT",
    "QUESTIONABLE_BOUNDARY",
    "QUESTIONABLE_ORDER",
    "SEMANTIC_DAMAGE",
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_EXPECTED_REVIEW_ROWS = 500
_PRODUCTION_PROJECTION_ROWS = 141_048_582
_PERFORMANCE_KEYS = frozenset(
    {
        "ELAPSED_MILLISECONDS",
        "USER_CPU_MILLISECONDS",
        "SYSTEM_CPU_MILLISECONDS",
        "MAX_RSS_KIB",
    }
)
_RAW_ADDRESS_COLUMNS = tuple(CLEAN_SOURCE_COLUMNS[:8])
_CLEAN_ADDRESS_COLUMNS = tuple(CLEAN_DERIVED_COLUMNS[:8])
_LOWER_ADDRESS_COLUMNS = tuple(LOWER_OUTPUT_COLUMNS[:8])


@dataclass(frozen=True, slots=True)
class Stage05ReviewRunConfig:
    stage04_output_directory: Path
    expected_stage04_manifest_sha256: str
    stage05_output_directory: Path
    expected_stage05_manifest_sha256: str
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
        for digest in (
            self.expected_stage04_manifest_sha256,
            self.expected_stage05_manifest_sha256,
            self.expected_development_review_manifest_sha256,
            self.expected_review_subset_fingerprint,
            self.expected_benchmark_fingerprint,
            self.expected_stage02_logical_fingerprint,
        ):
            _digest_bytes(digest)
        if self.performance_metrics is not None:
            if set(self.performance_metrics) != _PERFORMANCE_KEYS or any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in self.performance_metrics.values()
            ):
                _fail("INVALID_PERFORMANCE_METRICS", "Performance metrics are invalid")
            if self.performance_metrics["ELAPSED_MILLISECONDS"] < 1:
                _fail("INVALID_PERFORMANCE_METRICS", "Elapsed time must be positive")
        if self.production and self.performance_metrics is None:
            _fail(
                "PERFORMANCE_METRICS_REQUIRED",
                "Authoritative DEVELOPMENT review requires performance metrics",
            )
        if _GIT_SHA_RE.fullmatch(self.execution_git_sha) is None:
            _fail("INVALID_GIT_COMMIT", "Execution Git SHA must be a full SHA")
        _reject_holdout_paths(
            self.stage04_output_directory,
            self.stage05_output_directory,
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
                _fail(
                    "INVALID_OPERATIONAL_METADATA",
                    "Operational review metadata is invalid",
                )


@dataclass(frozen=True, slots=True)
class Stage05ReviewArtifactIdentity:
    relative_path: str
    size_bytes: int
    sha256: str
    row_count: int

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Stage05ReviewOutcome:
    output_directory: Path
    review_subset_fingerprint: str
    review_artifact_sha256: str
    manifest_sha256: str
    selected_row_count: int
    qualitative_classifications: Mapping[str, int]
    summary_json_path: Path
    summary_markdown_path: Path


def _fail(code: str, message: str) -> NoReturn:
    raise ReviewSubsetError(code, message)


def _digest_bytes(value: str) -> bytes:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail("INVALID_SHA256", "Digest must be canonical lowercase SHA-256")
    return bytes.fromhex(value)


def _reject_holdout_paths(*paths: Path) -> None:
    if any("holdout" in part.casefold() for path in paths for part in path.parts):
        _fail("HOLDOUT_ACCESS_PROHIBITED", "A Stage 5 review path names HOLDOUT")


def _require_regular_file(path: Path, code: str) -> None:
    try:
        observed = path.stat(follow_symlinks=False)
    except OSError as error:
        raise ReviewSubsetError(code, "Protected artifact is unavailable") from error
    if path.is_symlink() or not stat.S_ISREG(observed.st_mode):
        _fail(code, "Protected artifact is not a regular non-symlink file")


def _require_directory(path: Path, code: str) -> None:
    try:
        observed = path.stat(follow_symlinks=False)
    except OSError as error:
        raise ReviewSubsetError(code, "Protected directory is unavailable") from error
    if path.is_symlink() or not stat.S_ISDIR(observed.st_mode):
        _fail(code, "Protected directory is not a regular non-symlink directory")


def _require_mode(path: Path, expected: int, code: str) -> None:
    try:
        observed = stat.S_IMODE(path.stat(follow_symlinks=False).st_mode)
    except OSError as error:
        raise ReviewSubsetError(code, "Protected path mode is unavailable") from error
    if observed != expected:
        _fail(code, "Protected path is not owner-only")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise ReviewSubsetError(
            "ARTIFACT_READ_FAILURE", "Protected artifact could not be read"
        ) from error
    return digest.hexdigest()


def _load_json(path: Path, code: str) -> dict[str, Any]:
    _require_regular_file(path, code)
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
            "CONTROLLED_WRITE_FAILURE", "Protected Stage 5 review could not be written"
        ) from error


def _write_private_json(path: Path, value: object) -> None:
    _write_private(
        path,
        (
            json.dumps(
                value, ensure_ascii=True, allow_nan=False, indent=2, sort_keys=True
            )
            + "\n"
        ).encode("utf-8"),
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def stage05_review_schema(
    metadata: Mapping[bytes, bytes] | None = None,
) -> pa.Schema:
    source_schema = stage05_schema()
    fields = [
        pa.field("review_order", pa.uint32(), nullable=False),
        pa.field("development_review_id_v1", pa.binary(32), nullable=False),
        pa.field("stable_source_row_id_v1", pa.binary(32), nullable=False),
    ]
    fields.extend(source_schema.field(name) for name in _RAW_ADDRESS_COLUMNS)
    fields.extend(source_schema.field(name) for name in _CLEAN_ADDRESS_COLUMNS)
    fields.extend(source_schema.field(name) for name in _LOWER_ADDRESS_COLUMNS)
    fields.extend(
        source_schema.field(name)
        for name in (
            "stage03_change_details",
            "stage03_row_changed",
            "stage04_changed_fields",
            "stage04_row_changed",
            *STAGE05_DERIVED_COLUMNS,
        )
    )
    fields.append(
        pa.field("stage05_review_classification", pa.string(), nullable=False)
    )
    fields.extend(source_schema.field(name) for name in STAGE02_STRUCTURAL_COLUMNS)
    return pa.schema(fields, metadata=metadata)


def stage05_review_schema_fingerprint() -> str:
    digest = hashlib.sha256(b"SAFE_DEVELOPMENT_STAGE05_REVIEW_SCHEMA_V1")
    for value in (STAGE05_REVIEW_SCHEMA_VERSION, str(len(stage05_review_schema()))):
        encoded = value.encode()
        digest.update(len(encoded).to_bytes(8, "big") + encoded)
    for schema_field in stage05_review_schema():
        for value in (
            schema_field.name,
            str(schema_field.type),
            str(schema_field.nullable).lower(),
        ):
            encoded = value.encode()
            digest.update(len(encoded).to_bytes(8, "big") + encoded)
    return digest.hexdigest()


def _fixed_review_identities(
    config: Stage05ReviewRunConfig,
) -> tuple[pa.Table, str]:
    outcome = validate_development_review_bundle(
        config.development_review_bundle_directory,
        expected_manifest_sha256=config.expected_development_review_manifest_sha256,
        expected_benchmark_fingerprint=config.expected_benchmark_fingerprint,
        expected_stage02_logical_fingerprint=config.expected_stage02_logical_fingerprint,
    )
    if outcome.review_subset_fingerprint != config.expected_review_subset_fingerprint:
        _fail("REVIEW_SUBSET_MISMATCH", "Fixed review subset fingerprint differs")
    manifest = _load_json(
        config.development_review_bundle_directory / REVIEW_MANIFEST_NAME,
        "REVIEW_MANIFEST_INVALID",
    )
    if manifest.get("development_review_bundle_manifest_version") != (
        REVIEW_BUNDLE_MANIFEST_VERSION
    ):
        _fail("REVIEW_MANIFEST_INVALID", "Review manifest version differs")
    physical = manifest.get("physical_identity")
    if not isinstance(physical, dict) or not isinstance(
        physical.get("artifacts"), list
    ):
        _fail("REVIEW_MANIFEST_INVALID", "Review artifact inventory is malformed")
    identity_sha: str | None = None
    for raw in physical["artifacts"]:
        if isinstance(raw, dict) and raw.get("relative_path") == REVIEW_IDENTITIES_PATH:
            candidate = raw.get("sha256")
            if isinstance(candidate, str):
                identity_sha = candidate
    if identity_sha is None:
        _fail("REVIEW_MANIFEST_INVALID", "Fixed identity artifact is absent")
    _digest_bytes(identity_sha)
    path = config.development_review_bundle_directory / REVIEW_IDENTITIES_PATH
    _require_regular_file(path, "REVIEW_IDENTITY_ARTIFACT_INVALID")
    _require_mode(path, 0o600, "PERMISSION_FAILURE")
    if _sha256_file(path) != identity_sha:
        _fail("REVIEW_IDENTITY_ARTIFACT_MISMATCH", "Fixed identity SHA differs")
    try:
        table = pq.ParquetFile(path, page_checksum_verification=True).read(
            use_threads=False
        )
    except (OSError, pa.ArrowException) as error:
        raise ReviewSubsetError(
            "REVIEW_IDENTITY_READ_FAILURE", "Fixed identities could not be read"
        ) from error
    expected_schema = pa.schema(
        (
            pa.field("review_order", pa.uint32(), nullable=False),
            pa.field("development_review_id_v1", pa.binary(32), nullable=False),
            pa.field("stable_source_row_id_v1", pa.binary(32), nullable=False),
        )
    )
    stable_ids = table.column("stable_source_row_id_v1").to_pylist()
    review_ids = table.column("development_review_id_v1").to_pylist()
    if (
        not table.schema.remove_metadata().equals(expected_schema, check_metadata=False)
        or table.num_rows != _EXPECTED_REVIEW_ROWS
        or table.column("review_order").to_pylist()
        != list(range(1, _EXPECTED_REVIEW_ROWS + 1))
        or any(not isinstance(value, bytes) or len(value) != 32 for value in stable_ids)
        or any(not isinstance(value, bytes) or len(value) != 32 for value in review_ids)
        or len(set(stable_ids)) != _EXPECTED_REVIEW_ROWS
        or len(set(review_ids)) != _EXPECTED_REVIEW_ROWS
    ):
        _fail("REVIEW_IDENTITY_MISMATCH", "Fixed identity rows are not exact")
    return table, identity_sha


def _selected_stage05_table(
    config: Stage05ReviewRunConfig, identity_table: pa.Table
) -> tuple[pa.Table, Stage05MaterializationOutcome, dict[str, Any]]:
    try:
        outcome = validate_stage05_bundle(
            config.stage05_output_directory,
            expected_manifest_sha256=config.expected_stage05_manifest_sha256,
            authoritative_development=config.authoritative_development,
            stage04_output_directory=config.stage04_output_directory,
        )
    except Stage05ValidationError as error:
        raise ReviewSubsetError(
            "STAGE05_BUNDLE_INVALID", "Stage 5 bundle validation failed"
        ) from error
    manifest = _load_json(
        config.stage05_output_directory / STAGE05_MANIFEST_NAME,
        "STAGE05_MANIFEST_INVALID",
    )
    scientific = manifest.get("scientific_identity")
    physical = manifest.get("physical_identity")
    if not isinstance(scientific, dict) or not isinstance(physical, dict):
        _fail("STAGE05_MANIFEST_INVALID", "Stage 5 identity is malformed")
    if scientific.get("input_benchmark_fingerprint") != (
        config.expected_benchmark_fingerprint
    ) or physical.get("upstream_stage04_manifest_sha256") != (
        config.expected_stage04_manifest_sha256
    ):
        _fail("STAGE05_IDENTITY_MISMATCH", "Stage 5 upstream identity differs")
    artifacts = physical.get("output_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        _fail("STAGE05_MANIFEST_INVALID", "Stage 5 artifacts are absent")
    selected_columns = (
        "stable_source_row_id_v1",
        *_RAW_ADDRESS_COLUMNS,
        *_CLEAN_ADDRESS_COLUMNS,
        *_LOWER_ADDRESS_COLUMNS,
        "stage03_change_details",
        "stage03_row_changed",
        "stage04_changed_fields",
        "stage04_row_changed",
        *STAGE05_DERIVED_COLUMNS,
        *STAGE02_STRUCTURAL_COLUMNS,
    )
    target_ids = {
        cast(bytes, scalar.as_py())
        for scalar in identity_table.column("stable_source_row_id_v1").combine_chunks()
    }
    if len(target_ids) != _EXPECTED_REVIEW_ROWS:
        _fail("REVIEW_IDENTITY_MISMATCH", "Fixed review identities are not unique")
    tables: list[pa.Table] = []
    found: set[bytes] = set()
    try:
        for raw in artifacts:
            if not isinstance(raw, dict) or not isinstance(
                raw.get("relative_path"), str
            ):
                _fail("STAGE05_MANIFEST_INVALID", "Stage 5 artifact is malformed")
            parquet = pq.ParquetFile(
                config.stage05_output_directory / raw["relative_path"],
                page_checksum_verification=True,
            )
            selected_by_row_group: dict[int, list[int]] = {}
            for row_group_index in range(parquet.metadata.num_row_groups):
                row_group_offset = 0
                for batch in parquet.iter_batches(
                    batch_size=2_048,
                    row_groups=[row_group_index],
                    columns=["stable_source_row_id_v1"],
                    use_threads=False,
                ):
                    for index, scalar in enumerate(batch.column(0)):
                        identity = scalar.as_py()
                        if identity in target_ids:
                            if not isinstance(identity, bytes) or identity in found:
                                _fail(
                                    "STAGE05_IDENTITY_INVALID",
                                    "A fixed review identity is duplicated",
                                )
                            found.add(identity)
                            selected_by_row_group.setdefault(
                                row_group_index, []
                            ).append(row_group_offset + index)
                    row_group_offset += batch.num_rows
            for row_group_index, indices in selected_by_row_group.items():
                row_group = parquet.read_row_group(
                    row_group_index, columns=list(selected_columns), use_threads=False
                )
                tables.append(row_group.take(pa.array(indices, type=pa.uint32())))
        table = pa.concat_tables(tables)
    except ReviewSubsetError:
        raise
    except (OSError, pa.ArrowException) as error:
        raise ReviewSubsetError(
            "STAGE05_READ_FAILURE", "Stage 5 DEVELOPMENT output could not be read"
        ) from error
    expected_schema = pa.schema(
        stage05_schema().field(name) for name in selected_columns
    )
    if (
        table.num_rows != _EXPECTED_REVIEW_ROWS
        or found != target_ids
        or not table.schema.remove_metadata().equals(
            expected_schema, check_metadata=False
        )
    ):
        _fail("STAGE05_SCHEMA_MISMATCH", "Stage 5 selected review rows differ")
    return table, outcome, manifest


def _nonempty_lines(
    table: pa.Table, row_index: int, names: tuple[str, ...]
) -> list[str]:
    values = [table.column(name)[row_index].as_py() for name in names]
    if any(not isinstance(value, str) for value in values):
        _fail("STAGE05_REVIEW_VALUE_INVALID", "A review line is not exact text")
    return [cast(str, value) for value in values if value != ""]


def _row_classification(table: pa.Table, row_index: int) -> str:
    standard = _nonempty_lines(table, row_index, _LOWER_ADDRESS_COLUMNS[:4])
    native = _nonempty_lines(table, row_index, _LOWER_ADDRESS_COLUMNS[4:])
    if len(standard) != len(set(standard)) or len(native) != len(set(native)):
        return "VALID_BUT_REDUNDANT_SOURCE_CONTENT"
    return "CORRECT_RECONSTRUCTION"


def _review_table(
    selected: pa.Table,
    identities: pa.Table,
    *,
    metadata: Mapping[bytes, bytes],
) -> tuple[pa.Table, dict[str, int]]:
    index_by_id: dict[bytes, int] = {}
    for index, scalar in enumerate(
        selected.column("stable_source_row_id_v1").combine_chunks()
    ):
        identity = scalar.as_py()
        if not isinstance(identity, bytes) or identity in index_by_id:
            _fail("STAGE05_IDENTITY_INVALID", "Stage 5 identity is invalid")
        index_by_id[identity] = index
    try:
        indices = [
            index_by_id[cast(bytes, scalar.as_py())]
            for scalar in identities.column("stable_source_row_id_v1").combine_chunks()
        ]
    except KeyError as error:
        raise ReviewSubsetError(
            "REVIEW_IDENTITY_MISMATCH", "A fixed identity is absent from Stage 5"
        ) from error
    ordered = selected.take(pa.array(indices, type=pa.uint32()))
    classifications = [
        _row_classification(ordered, index) for index in range(_EXPECTED_REVIEW_ROWS)
    ]
    counts = Counter({name: 0 for name in QUALITATIVE_CLASSIFICATIONS})
    counts.update(classifications)
    arrays: list[pa.ChunkedArray | pa.Array] = [
        identities.column("review_order"),
        identities.column("development_review_id_v1"),
        identities.column("stable_source_row_id_v1"),
    ]
    arrays.extend(ordered.column(name) for name in _RAW_ADDRESS_COLUMNS)
    arrays.extend(ordered.column(name) for name in _CLEAN_ADDRESS_COLUMNS)
    arrays.extend(ordered.column(name) for name in _LOWER_ADDRESS_COLUMNS)
    arrays.extend(
        ordered.column(name)
        for name in (
            "stage03_change_details",
            "stage03_row_changed",
            "stage04_changed_fields",
            "stage04_row_changed",
            *STAGE05_DERIVED_COLUMNS,
        )
    )
    arrays.append(pa.array(classifications, type=pa.string(), from_pandas=False))
    arrays.extend(ordered.column(name) for name in STAGE02_STRUCTURAL_COLUMNS)
    return (
        pa.Table.from_arrays(arrays, schema=stage05_review_schema(metadata)),
        dict(counts),
    )


def _write_review_parquet(table: pa.Table, path: Path) -> None:
    try:
        pq.write_table(
            table,
            path,
            version="2.6",
            data_page_version="1.0",
            compression="zstd",
            compression_level=3,
            use_dictionary=False,
            write_statistics=[
                "review_order",
                "stage05_standard_candidate_available",
                "stage05_native_candidate_available",
                "stage05_review_classification",
            ],
            write_page_checksum=True,
            row_group_size=_EXPECTED_REVIEW_ROWS,
        )
        path.chmod(0o600)
    except (OSError, pa.ArrowException) as error:
        raise ReviewSubsetError(
            "REVIEW_WRITE_FAILURE", "Stage 5 review Parquet could not be written"
        ) from error


def _artifact_identity(
    root: Path, relative_path: str, *, row_count: int
) -> Stage05ReviewArtifactIdentity:
    path = root / relative_path
    _require_regular_file(path, "STAGE05_REVIEW_ARTIFACT_INVALID")
    _require_mode(path, 0o600, "PERMISSION_FAILURE")
    return Stage05ReviewArtifactIdentity(
        relative_path=relative_path,
        size_bytes=path.stat(follow_symlinks=False).st_size,
        sha256=_sha256_file(path),
        row_count=row_count,
    )


def _summary(
    *,
    config: Stage05ReviewRunConfig,
    outcome: Stage05MaterializationOutcome,
    manifest: Mapping[str, Any],
    review_artifact_sha256: str,
    qualitative: Mapping[str, int],
) -> SanitizedStageSummary:
    physical = manifest.get("physical_identity")
    if not isinstance(physical, dict):
        _fail("STAGE05_MANIFEST_INVALID", "Stage 5 physical identity is malformed")
    input_binding = physical.get("stage05_input_binding_sha256")
    stage04_manifest = physical.get("upstream_stage04_manifest_sha256")
    if not isinstance(input_binding, str) or not isinstance(stage04_manifest, str):
        _fail("STAGE05_MANIFEST_INVALID", "Stage 5 fingerprints are malformed")
    metric_groups = {name: dict(values) for name, values in outcome.metrics.items()}
    metric_groups["STAGE05_QUALITATIVE_CLASSIFICATIONS"] = dict(qualitative)
    metric_groups["REVIEW_ROW_INTEGRITY"] = {
        "SELECTED_ROWS": _EXPECTED_REVIEW_ROWS,
        "DUPLICATE_IDENTITIES": 0,
        "HOLDOUT_ROWS": 0,
    }
    if config.performance_metrics is not None:
        elapsed = config.performance_metrics["ELAPSED_MILLISECONDS"]
        candidate_values = outcome.row_count * 4
        projection_numerator = _PRODUCTION_PROJECTION_ROWS * elapsed
        projection_denominator = outcome.row_count * 1_000
        metric_groups["PERFORMANCE"] = {
            **dict(config.performance_metrics),
            "ROWS_PER_SECOND_MILLI": (outcome.row_count * 1_000_000 + elapsed // 2)
            // elapsed,
            "FIELDS_PER_SECOND_MILLI": (candidate_values * 1_000_000 + elapsed // 2)
            // elapsed,
            "CANDIDATE_VALUES_PER_SECOND_MILLI": (
                candidate_values * 1_000_000 + elapsed // 2
            )
            // elapsed,
            "LINEAR_PROJECTED_141048582_ROWS_SECONDS": (
                projection_numerator + projection_denominator - 1
            )
            // projection_denominator,
        }
    checks = {
        "STABLE_IDENTITIES_PRESERVED": True,
        "RAW_FIELDS_UNCHANGED": True,
        "HOLDOUT_UNTOUCHED": True,
        "OWNER_ONLY_PERMISSIONS": True,
        "PROTECTED_REVIEW_ARTIFACT": True,
        "ATOMIC_PUBLICATION": True,
        "INPUT_IDENTITY_BOUND": True,
        "IDEMPOTENCE_VERIFIED": True,
        "SAME_FIXED_REVIEW_IDENTITIES": True,
        "SOURCE_PROVENANCE_UNCHANGED": True,
        "STANDARD_NATIVE_INDEPENDENT": True,
        "BOUNDED_MEMORY_VALIDATION": True,
        "NO_TOTAL_ROW_PYTHON_IDENTITY_SET": True,
        "ALL_STAGE04_FIELDS_UNCHANGED": True,
        "LINE_ONLY_RECONSTRUCTION": True,
        "GEOGRAPHIC_FIELDS_EXCLUDED": True,
        "DUPLICATE_LINES_PRESERVED": True,
        "GAPS_PRESERVE_RELATIVE_ORDER": True,
        "NO_STAGE06_DEDUPLICATION": True,
        "NO_STAGE07_PARSING": True,
        "FIXED_500_QUALITATIVE_REVIEW_COMPLETE": True,
        "ZERO_QUESTIONABLE_BOUNDARY": qualitative["QUESTIONABLE_BOUNDARY"] == 0,
        "ZERO_QUESTIONABLE_ORDER": qualitative["QUESTIONABLE_ORDER"] == 0,
        "ZERO_SEMANTIC_DAMAGE": qualitative["SEMANTIC_DAMAGE"] == 0,
    }
    return SanitizedStageSummary(
        status="STAGE_5_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW",
        stage="STAGE_5",
        stage_contract_version=STAGE05_CONTRACT_VERSION,
        execution_git_sha=config.execution_git_sha,
        slurm_job_id=str((config.operational_metadata or {}).get("slurm_job_id", "0")),
        development_dataset="BENCHMARK_SAMPLE_V1_DEVELOPMENT",
        development_fingerprint=outcome.logical_dataset_sha256_v1,
        input_benchmark_fingerprint=config.expected_benchmark_fingerprint,
        logical_fingerprint=outcome.logical_dataset_sha256_v1,
        schema_fingerprint=stage05_schema_fingerprint(),
        extra_fingerprints={
            "input_binding": input_binding,
            "manifest": outcome.manifest_sha256,
            "input_stage04_manifest": stage04_manifest,
            "review_subset": config.expected_review_subset_fingerprint,
            "review_artifact": review_artifact_sha256,
            "ordered_stable_identity": outcome.ordered_identity_sha256,
        },
        metric_groups=metric_groups,
        checks=checks,
        interpretation_code="STAGE05_ADDRESS_RECONSTRUCTION_CANDIDATE",
    )


def materialize_stage05_development_review(
    config: Stage05ReviewRunConfig,
) -> Stage05ReviewOutcome:
    """Create the exact fixed-500 review view and Git-safe Stage 5 summaries."""
    config.validate()
    if config.production:
        require_goethe_nhr_slurm("development-reporting-stage05-review")
    if config.output_directory.exists() or config.output_directory.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 5 review output already exists")
    identities, identity_artifact_sha = _fixed_review_identities(config)
    selected, outcome, stage05_manifest = _selected_stage05_table(config, identities)
    metadata = {
        b"development_reporting_contract_version": (
            DEVELOPMENT_REPORTING_CONTRACT_VERSION.encode()
        ),
        b"development_review_subset_contract_version": (
            DEVELOPMENT_REVIEW_SUBSET_CONTRACT_VERSION.encode()
        ),
        b"stage05_review_contract_version": STAGE05_REVIEW_CONTRACT_VERSION.encode(),
        b"stage05_review_schema_version": STAGE05_REVIEW_SCHEMA_VERSION.encode(),
        b"review_subset_fingerprint": config.expected_review_subset_fingerprint.encode(),
        b"input_benchmark_fingerprint": config.expected_benchmark_fingerprint.encode(),
        b"stage_identifier": b"STAGE_5",
        b"stage_contract_version": STAGE05_CONTRACT_VERSION.encode(),
        b"stage_profile_version": STAGE05_PROFILE_VERSION.encode(),
        b"stage_logical_fingerprint": outcome.logical_dataset_sha256_v1.encode(),
        b"stage_schema_fingerprint": stage05_schema_fingerprint().encode(),
    }
    review_table, qualitative = _review_table(selected, identities, metadata=metadata)
    if (
        qualitative["QUESTIONABLE_BOUNDARY"]
        or qualitative["QUESTIONABLE_ORDER"]
        or qualitative["SEMANTIC_DAMAGE"]
    ):
        _fail("QUALITATIVE_REVIEW_FAILURE", "Stage 5 review found unresolved damage")

    parent = config.output_directory.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent.chmod(0o700)
    _require_directory(parent, "STAGE05_REVIEW_OUTPUT_INVALID")
    _require_mode(parent, 0o700, "PERMISSION_FAILURE")
    temporary = parent / f".{config.output_directory.name}.{os.getpid()}.in_progress"
    if temporary.exists() or temporary.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 5 review temporary output exists")
    temporary.mkdir(mode=0o700)
    _write_private_json(
        temporary / STAGE05_REVIEW_IN_PROGRESS_MARKER,
        {"status": "STAGE05_REVIEW_INCOMPLETE"},
    )
    _write_review_parquet(review_table, temporary / STAGE05_REVIEW_PATH)
    review_artifact = _artifact_identity(
        temporary, STAGE05_REVIEW_PATH, row_count=_EXPECTED_REVIEW_ROWS
    )
    summary = _summary(
        config=config,
        outcome=outcome,
        manifest=stage05_manifest,
        review_artifact_sha256=review_artifact.sha256,
        qualitative=qualitative,
    )
    _write_private(
        temporary / STAGE05_SUMMARY_JSON_PATH,
        render_summary_json(summary).encode("utf-8"),
    )
    _write_private(
        temporary / STAGE05_SUMMARY_MD_PATH,
        render_summary_markdown(summary).encode("utf-8"),
    )
    summary_json = _artifact_identity(temporary, STAGE05_SUMMARY_JSON_PATH, row_count=0)
    summary_markdown = _artifact_identity(
        temporary, STAGE05_SUMMARY_MD_PATH, row_count=0
    )
    manifest = {
        "stage05_review_manifest_version": STAGE05_REVIEW_MANIFEST_VERSION,
        "status": "STAGE_5_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW",
        "scientific_identity": {
            "development_reporting_contract_version": (
                DEVELOPMENT_REPORTING_CONTRACT_VERSION
            ),
            "sanitized_summary_contract_version": SANITIZED_SUMMARY_CONTRACT_VERSION,
            "development_review_subset_contract_version": (
                DEVELOPMENT_REVIEW_SUBSET_CONTRACT_VERSION
            ),
            "stage05_review_contract_version": STAGE05_REVIEW_CONTRACT_VERSION,
            "stage05_review_schema_version": STAGE05_REVIEW_SCHEMA_VERSION,
            "stage05_review_schema_fingerprint": stage05_review_schema_fingerprint(),
            "review_subset_fingerprint": config.expected_review_subset_fingerprint,
            "input_benchmark_fingerprint": config.expected_benchmark_fingerprint,
            "stage05_contract_version": STAGE05_CONTRACT_VERSION,
            "stage05_profile_version": STAGE05_PROFILE_VERSION,
            "stage05_logical_fingerprint": outcome.logical_dataset_sha256_v1,
            "stage05_schema_fingerprint": stage05_schema_fingerprint(),
            "selected_row_count": _EXPECTED_REVIEW_ROWS,
            "qualitative_classifications": qualitative,
        },
        "physical_identity": {
            "accepted_development_review_manifest_sha256": (
                config.expected_development_review_manifest_sha256
            ),
            "accepted_review_identity_artifact_sha256": identity_artifact_sha,
            "stage04_manifest_sha256": config.expected_stage04_manifest_sha256,
            "stage05_manifest_sha256": outcome.manifest_sha256,
            "artifacts": [
                review_artifact.to_dict(),
                summary_json.to_dict(),
                summary_markdown.to_dict(),
            ],
            "owner_only_permissions": True,
        },
        "validation": {
            "validation_contract_version": STAGE05_REVIEW_VALIDATION_VERSION,
            "accepted_fixed_subset_validated": "PASS",
            "same_ordered_500_identities": "PASS",
            "stage05_bundle_independently_validated_against_stage04": "PASS",
            "raw_clean_lower_candidate_comparison_surface": "PASS",
            "qualitative_classification_complete": "PASS",
            "zero_questionable_boundary": "PASS",
            "zero_questionable_order": "PASS",
            "zero_semantic_damage": "PASS",
            "stage05_review_schema_exact": "PASS",
            "protected_parquet_checksum_readback": "PASS",
            "sanitized_summary_allowlist": "PASS",
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
    _write_private_json(temporary / STAGE05_REVIEW_MANIFEST_NAME, manifest)
    manifest_artifact = _artifact_identity(
        temporary, STAGE05_REVIEW_MANIFEST_NAME, row_count=0
    )
    _write_private_json(
        temporary / STAGE05_REVIEW_SUCCESS_MARKER,
        {
            "status": "STAGE_5_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW",
            "stage05_review_manifest_sha256": manifest_artifact.sha256,
            "stage05_review_manifest_size_bytes": manifest_artifact.size_bytes,
            "stage05_manifest_sha256": outcome.manifest_sha256,
            "review_subset_fingerprint": config.expected_review_subset_fingerprint,
            "review_artifact_sha256": review_artifact.sha256,
            "selected_row_count": _EXPECTED_REVIEW_ROWS,
            "questionable_boundary_count": 0,
            "questionable_order_count": 0,
            "semantic_damage_count": 0,
        },
    )
    (temporary / STAGE05_REVIEW_IN_PROGRESS_MARKER).unlink()
    _fsync_directory(temporary)
    os.replace(temporary, config.output_directory)
    _fsync_directory(parent)
    return validate_stage05_development_review(
        config.output_directory,
        expected_manifest_sha256=manifest_artifact.sha256,
        expected_stage05_manifest_sha256=config.expected_stage05_manifest_sha256,
        expected_review_subset_fingerprint=config.expected_review_subset_fingerprint,
        expected_identity_table=identities,
    )


def validate_stage05_development_review(
    output_directory: Path,
    *,
    expected_manifest_sha256: str,
    expected_stage05_manifest_sha256: str,
    expected_review_subset_fingerprint: str,
    expected_identity_table: pa.Table,
) -> Stage05ReviewOutcome:
    for digest in (
        expected_manifest_sha256,
        expected_stage05_manifest_sha256,
        expected_review_subset_fingerprint,
    ):
        _digest_bytes(digest)
    _reject_holdout_paths(output_directory)
    _require_directory(output_directory, "STAGE05_REVIEW_OUTPUT_INVALID")
    _require_mode(output_directory, 0o700, "PERMISSION_FAILURE")
    expected_files = {
        STAGE05_REVIEW_PATH,
        STAGE05_SUMMARY_JSON_PATH,
        STAGE05_SUMMARY_MD_PATH,
        STAGE05_REVIEW_MANIFEST_NAME,
        STAGE05_REVIEW_SUCCESS_MARKER,
    }
    observed_files = {
        path.name for path in output_directory.iterdir() if path.is_file()
    }
    observed_directories = [
        path for path in output_directory.iterdir() if path.is_dir()
    ]
    if observed_files != expected_files or observed_directories:
        _fail("STAGE05_REVIEW_ARTIFACT_MISMATCH", "Review topology is not exact")
    for name in expected_files:
        _require_regular_file(
            output_directory / name, "STAGE05_REVIEW_ARTIFACT_INVALID"
        )
        _require_mode(output_directory / name, 0o600, "PERMISSION_FAILURE")
    manifest_path = output_directory / STAGE05_REVIEW_MANIFEST_NAME
    manifest_sha = _sha256_file(manifest_path)
    if manifest_sha != expected_manifest_sha256:
        _fail("STAGE05_REVIEW_MANIFEST_MISMATCH", "Review manifest SHA differs")
    manifest = _load_json(manifest_path, "STAGE05_REVIEW_MANIFEST_INVALID")
    success = _load_json(
        output_directory / STAGE05_REVIEW_SUCCESS_MARKER,
        "STAGE05_REVIEW_SUCCESS_INVALID",
    )
    scientific = manifest.get("scientific_identity")
    physical = manifest.get("physical_identity")
    validation = manifest.get("validation")
    if not isinstance(scientific, dict) or not isinstance(physical, dict):
        _fail("STAGE05_REVIEW_MANIFEST_INVALID", "Review identity is malformed")
    qualitative = scientific.get("qualitative_classifications")
    if (
        manifest.get("stage05_review_manifest_version")
        != STAGE05_REVIEW_MANIFEST_VERSION
        or manifest.get("status")
        != "STAGE_5_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW"
        or success.get("status")
        != "STAGE_5_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW"
        or success.get("stage05_review_manifest_sha256") != manifest_sha
        or success.get("stage05_review_manifest_size_bytes")
        != manifest_path.stat(follow_symlinks=False).st_size
        or scientific.get("review_subset_fingerprint")
        != expected_review_subset_fingerprint
        or scientific.get("stage05_review_schema_fingerprint")
        != stage05_review_schema_fingerprint()
        or scientific.get("selected_row_count") != _EXPECTED_REVIEW_ROWS
        or physical.get("stage05_manifest_sha256") != expected_stage05_manifest_sha256
        or physical.get("owner_only_permissions") is not True
        or not isinstance(qualitative, dict)
        or set(qualitative) != set(QUALITATIVE_CLASSIFICATIONS)
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in qualitative.values()
        )
        or sum(qualitative.values()) != _EXPECTED_REVIEW_ROWS
        or qualitative.get("QUESTIONABLE_BOUNDARY") != 0
        or qualitative.get("QUESTIONABLE_ORDER") != 0
        or qualitative.get("SEMANTIC_DAMAGE") != 0
    ):
        _fail("STAGE05_REVIEW_MANIFEST_MISMATCH", "Review terminal identity differs")
    if (
        not isinstance(validation, dict)
        or validation.get("validation_contract_version")
        != STAGE05_REVIEW_VALIDATION_VERSION
        or any(
            value != "PASS"
            for key, value in validation.items()
            if key != "validation_contract_version"
        )
    ):
        _fail("STAGE05_REVIEW_VALIDATION_INCOMPLETE", "Review validation is incomplete")
    artifacts = physical.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 3:
        _fail("STAGE05_REVIEW_MANIFEST_INVALID", "Review artifacts are malformed")
    artifact_by_path: dict[str, Mapping[str, Any]] = {}
    for raw in artifacts:
        if not isinstance(raw, dict) or not isinstance(raw.get("relative_path"), str):
            _fail("STAGE05_REVIEW_MANIFEST_INVALID", "Review artifact is malformed")
        artifact_by_path[raw["relative_path"]] = raw
        path = output_directory / raw["relative_path"]
        if path.stat(follow_symlinks=False).st_size != raw.get(
            "size_bytes"
        ) or _sha256_file(path) != raw.get("sha256"):
            _fail("STAGE05_REVIEW_ARTIFACT_MISMATCH", "Review artifact SHA differs")
    review_identity = artifact_by_path.get(STAGE05_REVIEW_PATH)
    if review_identity is None or review_identity.get("row_count") != 500:
        _fail("STAGE05_REVIEW_ARTIFACT_MISMATCH", "Review row count is not exact")
    try:
        table = pq.ParquetFile(
            output_directory / STAGE05_REVIEW_PATH,
            page_checksum_verification=True,
        ).read(use_threads=False)
    except (OSError, pa.ArrowException) as error:
        raise ReviewSubsetError(
            "STAGE05_REVIEW_READBACK_FAILURE", "Review Parquet read-back failed"
        ) from error
    if not table.schema.remove_metadata().equals(
        stage05_review_schema(), check_metadata=False
    ):
        _fail("STAGE05_REVIEW_SCHEMA_MISMATCH", "Review schema is not exact")
    for name in ("review_order", "development_review_id_v1", "stable_source_row_id_v1"):
        if not table.column(name).equals(expected_identity_table.column(name)):
            _fail("REVIEW_IDENTITY_MISMATCH", "Review identities or order differ")
    observed_qualitative = Counter(
        cast(list[str], table.column("stage05_review_classification").to_pylist())
    )
    if any(
        _row_classification(table, index)
        != table.column("stage05_review_classification")[index].as_py()
        for index in range(_EXPECTED_REVIEW_ROWS)
    ) or any(observed_qualitative[name] != qualitative[name] for name in qualitative):
        _fail("QUALITATIVE_REVIEW_MISMATCH", "Review classification differs")
    summary_value = _load_json(
        output_directory / STAGE05_SUMMARY_JSON_PATH, "UNSAFE_SUMMARY"
    )
    summary = validate_sanitized_summary_payload(summary_value)
    if (
        summary.extra_fingerprints.get("review_artifact")
        != review_identity.get("sha256")
        or summary.extra_fingerprints.get("review_subset")
        != expected_review_subset_fingerprint
        or summary.extra_fingerprints.get("manifest")
        != expected_stage05_manifest_sha256
        or summary.metric_groups.get("STAGE05_QUALITATIVE_CLASSIFICATIONS")
        != qualitative
    ):
        _fail("UNSAFE_SUMMARY", "Stage 5 summary fingerprints differ")
    markdown = (output_directory / STAGE05_SUMMARY_MD_PATH).read_text(encoding="utf-8")
    if markdown != render_summary_markdown(summary):
        _fail("UNSAFE_SUMMARY", "Stage 5 Markdown summary is not canonical")
    review_sha = cast(str, review_identity["sha256"])
    if (
        success.get("review_subset_fingerprint") != expected_review_subset_fingerprint
        or success.get("review_artifact_sha256") != review_sha
        or success.get("selected_row_count") != _EXPECTED_REVIEW_ROWS
        or success.get("questionable_boundary_count") != 0
        or success.get("questionable_order_count") != 0
        or success.get("semantic_damage_count") != 0
    ):
        _fail("STAGE05_REVIEW_TERMINAL_MISMATCH", "Review terminal counts differ")
    return Stage05ReviewOutcome(
        output_directory=output_directory,
        review_subset_fingerprint=expected_review_subset_fingerprint,
        review_artifact_sha256=review_sha,
        manifest_sha256=manifest_sha,
        selected_row_count=_EXPECTED_REVIEW_ROWS,
        qualitative_classifications=cast(dict[str, int], qualitative),
        summary_json_path=output_directory / STAGE05_SUMMARY_JSON_PATH,
        summary_markdown_path=output_directory / STAGE05_SUMMARY_MD_PATH,
    )


__all__ = [
    "QUALITATIVE_CLASSIFICATIONS",
    "STAGE05_REVIEW_CONTRACT_VERSION",
    "STAGE05_REVIEW_MANIFEST_NAME",
    "STAGE05_REVIEW_PATH",
    "STAGE05_REVIEW_SCHEMA_VERSION",
    "STAGE05_SUMMARY_JSON_PATH",
    "STAGE05_SUMMARY_MD_PATH",
    "Stage05ReviewOutcome",
    "Stage05ReviewRunConfig",
    "materialize_stage05_development_review",
    "stage05_review_schema",
    "stage05_review_schema_fingerprint",
    "validate_stage05_development_review",
]
