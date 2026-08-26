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
from typing import Any, Mapping, NoReturn, cast

import ftfy
import pyarrow as pa
import pyarrow.parquet as pq

from ...execution_policy import require_goethe_nhr_slurm
from ..stages.s02_harmonization import STAGE02_STRUCTURAL_COLUMNS
from ..stages.s03_cleaning import (
    CHANGE_DETAILS_TYPE,
    CLEAN_DERIVED_COLUMNS,
    CLEAN_SOURCE_COLUMNS,
    STAGE03_CONTRACT_VERSION,
    STAGE03_MANIFEST_NAME,
    STAGE03_PROFILE_VERSION,
    Stage03MaterializationOutcome,
    Stage03ValidationError,
    stage03_schema,
    stage03_schema_fingerprint,
    validate_stage03_bundle,
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

STAGE03_REVIEW_CONTRACT_VERSION = "development_stage03_review_contract_v1"
STAGE03_REVIEW_SCHEMA_VERSION = "development_stage03_review_view_schema_v1"
STAGE03_REVIEW_MANIFEST_VERSION = "development_stage03_review_manifest_v1"
STAGE03_REVIEW_VALIDATION_VERSION = "development_stage03_review_validation_v1"
STAGE03_REVIEW_PATH = "stage03_review.parquet"
STAGE03_REVIEW_MANIFEST_NAME = "stage03_review_manifest.json"
STAGE03_REVIEW_SUCCESS_MARKER = "_SUCCESS.json"
STAGE03_REVIEW_IN_PROGRESS_MARKER = "_IN_PROGRESS"
STAGE03_SUMMARY_JSON_PATH = "stage03_summary.json"
STAGE03_SUMMARY_MD_PATH = "stage03_summary.md"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_EXPECTED_REVIEW_ROWS = 500


@dataclass(frozen=True, slots=True)
class Stage03ReviewRunConfig:
    stage03_output_directory: Path
    expected_stage03_manifest_sha256: str
    development_review_bundle_directory: Path
    expected_development_review_manifest_sha256: str
    expected_review_subset_fingerprint: str
    expected_benchmark_fingerprint: str
    expected_stage02_logical_fingerprint: str
    output_directory: Path
    execution_git_sha: str
    production: bool = True
    operational_metadata: Mapping[str, str] | None = None

    def validate(self) -> None:
        for digest in (
            self.expected_stage03_manifest_sha256,
            self.expected_development_review_manifest_sha256,
            self.expected_review_subset_fingerprint,
            self.expected_benchmark_fingerprint,
            self.expected_stage02_logical_fingerprint,
        ):
            _digest_bytes(digest)
        if _GIT_SHA_RE.fullmatch(self.execution_git_sha) is None:
            _fail("INVALID_GIT_COMMIT", "Execution Git SHA must be a full SHA")
        _reject_holdout_paths(
            self.stage03_output_directory,
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
class Stage03ReviewArtifactIdentity:
    relative_path: str
    size_bytes: int
    sha256: str
    row_count: int

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Stage03ReviewOutcome:
    output_directory: Path
    review_subset_fingerprint: str
    review_artifact_sha256: str
    manifest_sha256: str
    selected_row_count: int
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
        _fail("HOLDOUT_ACCESS_PROHIBITED", "A Stage 3 review path names HOLDOUT")


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
            "CONTROLLED_WRITE_FAILURE", "Protected Stage 3 review could not be written"
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


def stage03_review_schema(
    metadata: Mapping[bytes, bytes] | None = None,
) -> pa.Schema:
    source_schema = stage03_schema()
    fields = [
        pa.field("review_order", pa.uint32(), nullable=False),
        pa.field("development_review_id_v1", pa.binary(32), nullable=False),
        pa.field("stable_source_row_id_v1", pa.binary(32), nullable=False),
    ]
    fields.extend(source_schema.field(name) for name in CLEAN_SOURCE_COLUMNS)
    fields.extend(source_schema.field(name) for name in CLEAN_DERIVED_COLUMNS)
    fields.extend(
        (
            pa.field("stage03_change_details", CHANGE_DETAILS_TYPE, nullable=False),
            pa.field("stage03_row_changed", pa.bool_(), nullable=False),
        )
    )
    fields.extend(source_schema.field(name) for name in STAGE02_STRUCTURAL_COLUMNS)
    return pa.schema(fields, metadata=metadata)


def stage03_review_schema_fingerprint() -> str:
    digest = hashlib.sha256(b"SAFE_DEVELOPMENT_STAGE03_REVIEW_SCHEMA_V1")
    for value in (STAGE03_REVIEW_SCHEMA_VERSION, str(len(stage03_review_schema()))):
        encoded = value.encode()
        digest.update(len(encoded).to_bytes(8, "big") + encoded)
    for schema_field in stage03_review_schema():
        for value in (
            schema_field.name,
            str(schema_field.type),
            str(schema_field.nullable).lower(),
        ):
            encoded = value.encode()
            digest.update(len(encoded).to_bytes(8, "big") + encoded)
    return digest.hexdigest()


def _fixed_review_identities(
    config: Stage03ReviewRunConfig,
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
    if not isinstance(physical, dict):
        _fail("REVIEW_MANIFEST_INVALID", "Review physical identity is malformed")
    artifacts = physical.get("artifacts")
    if not isinstance(artifacts, list):
        _fail("REVIEW_MANIFEST_INVALID", "Review artifact inventory is malformed")
    identity_sha: str | None = None
    for raw in artifacts:
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
        parquet = pq.ParquetFile(path, page_checksum_verification=True)
        table = parquet.read(use_threads=False)
    except (OSError, pa.ArrowException) as error:
        raise ReviewSubsetError(
            "REVIEW_IDENTITY_READ_FAILURE", "Fixed identities could not be read"
        ) from error
    expected_fields = (
        pa.field("review_order", pa.uint32(), nullable=False),
        pa.field("development_review_id_v1", pa.binary(32), nullable=False),
        pa.field("stable_source_row_id_v1", pa.binary(32), nullable=False),
    )
    if not table.schema.remove_metadata().equals(
        pa.schema(expected_fields), check_metadata=False
    ):
        _fail("REVIEW_IDENTITY_SCHEMA_MISMATCH", "Fixed identity schema differs")
    stable_ids = table.column("stable_source_row_id_v1").to_pylist()
    review_ids = table.column("development_review_id_v1").to_pylist()
    orders = table.column("review_order").to_pylist()
    if (
        table.num_rows != _EXPECTED_REVIEW_ROWS
        or orders != list(range(1, _EXPECTED_REVIEW_ROWS + 1))
        or any(not isinstance(value, bytes) or len(value) != 32 for value in stable_ids)
        or any(not isinstance(value, bytes) or len(value) != 32 for value in review_ids)
        or len(set(stable_ids)) != _EXPECTED_REVIEW_ROWS
        or len(set(review_ids)) != _EXPECTED_REVIEW_ROWS
    ):
        _fail("REVIEW_IDENTITY_MISMATCH", "Fixed identity rows are not exact")
    return table, identity_sha


def _stage03_table_and_manifest(
    config: Stage03ReviewRunConfig,
) -> tuple[pa.Table, Stage03MaterializationOutcome, dict[str, Any]]:
    try:
        outcome = validate_stage03_bundle(
            config.stage03_output_directory,
            expected_manifest_sha256=config.expected_stage03_manifest_sha256,
        )
    except Stage03ValidationError as error:
        raise ReviewSubsetError(
            "STAGE03_BUNDLE_INVALID", "Stage 3 bundle validation failed"
        ) from error
    manifest = _load_json(
        config.stage03_output_directory / STAGE03_MANIFEST_NAME,
        "STAGE03_MANIFEST_INVALID",
    )
    physical = manifest.get("physical_identity")
    scientific = manifest.get("scientific_identity")
    if not isinstance(physical, dict) or not isinstance(scientific, dict):
        _fail("STAGE03_MANIFEST_INVALID", "Stage 3 identity is malformed")
    if scientific.get("input_benchmark_fingerprint") != (
        config.expected_benchmark_fingerprint
    ) or scientific.get("upstream_stage02_logical_identity_sha256") != (
        config.expected_stage02_logical_fingerprint
    ):
        _fail("STAGE03_IDENTITY_MISMATCH", "Stage 3 upstream identity differs")
    artifacts = physical.get("output_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        _fail("STAGE03_MANIFEST_INVALID", "Stage 3 artifacts are absent")
    tables: list[pa.Table] = []
    try:
        for raw in artifacts:
            if not isinstance(raw, dict) or not isinstance(
                raw.get("relative_path"), str
            ):
                _fail("STAGE03_MANIFEST_INVALID", "Stage 3 artifact is malformed")
            path = config.stage03_output_directory / raw["relative_path"]
            parquet = pq.ParquetFile(path, page_checksum_verification=True)
            tables.append(parquet.read(use_threads=False))
        table = pa.concat_tables(tables)
    except ReviewSubsetError:
        raise
    except (OSError, pa.ArrowException) as error:
        raise ReviewSubsetError(
            "STAGE03_READ_FAILURE", "Stage 3 DEVELOPMENT output could not be read"
        ) from error
    if table.num_rows != outcome.row_count or not table.schema.remove_metadata().equals(
        stage03_schema(), check_metadata=False
    ):
        _fail("STAGE03_SCHEMA_MISMATCH", "Stage 3 DEVELOPMENT table differs")
    return table, outcome, manifest


def _selected_review_table(
    stage03_table: pa.Table,
    identity_table: pa.Table,
    *,
    metadata: Mapping[bytes, bytes],
) -> pa.Table:
    stage_ids = stage03_table.column("stable_source_row_id_v1").to_pylist()
    index_by_id: dict[bytes, int] = {}
    for index, identity in enumerate(stage_ids):
        if not isinstance(identity, bytes) or len(identity) != 32:
            _fail("STAGE03_IDENTITY_INVALID", "Stage 3 stable identity is malformed")
        if identity in index_by_id:
            _fail("STAGE03_IDENTITY_INVALID", "Stage 3 stable identity is duplicated")
        index_by_id[identity] = index
    selected_ids = identity_table.column("stable_source_row_id_v1").to_pylist()
    try:
        indices = [index_by_id[cast(bytes, identity)] for identity in selected_ids]
    except KeyError as error:
        raise ReviewSubsetError(
            "REVIEW_IDENTITY_MISMATCH", "A fixed review identity is absent from Stage 3"
        ) from error
    selected = stage03_table.take(pa.array(indices, type=pa.uint32()))
    arrays: list[pa.ChunkedArray] = [
        identity_table.column("review_order"),
        identity_table.column("development_review_id_v1"),
        identity_table.column("stable_source_row_id_v1"),
    ]
    arrays.extend(selected.column(name) for name in CLEAN_SOURCE_COLUMNS)
    arrays.extend(selected.column(name) for name in CLEAN_DERIVED_COLUMNS)
    arrays.extend(
        selected.column(name)
        for name in ("stage03_change_details", "stage03_row_changed")
    )
    arrays.extend(selected.column(name) for name in STAGE02_STRUCTURAL_COLUMNS)
    return pa.Table.from_arrays(arrays, schema=stage03_review_schema(metadata))


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
                "standard_has_nonempty_source_line",
                "native_has_nonempty_source_line",
                "standard_nonempty_source_line_count",
                "native_nonempty_source_line_count",
                "stage03_row_changed",
            ],
            write_page_checksum=True,
            row_group_size=_EXPECTED_REVIEW_ROWS,
        )
        path.chmod(0o600)
    except (OSError, pa.ArrowException) as error:
        raise ReviewSubsetError(
            "REVIEW_WRITE_FAILURE", "Stage 3 review Parquet could not be written"
        ) from error


def _artifact_identity(
    root: Path, relative_path: str, *, row_count: int
) -> Stage03ReviewArtifactIdentity:
    path = root / relative_path
    _require_regular_file(path, "STAGE03_REVIEW_ARTIFACT_INVALID")
    _require_mode(path, 0o600, "PERMISSION_FAILURE")
    return Stage03ReviewArtifactIdentity(
        relative_path=relative_path,
        size_bytes=path.stat(follow_symlinks=False).st_size,
        sha256=_sha256_file(path),
        row_count=row_count,
    )


def _summary(
    *,
    config: Stage03ReviewRunConfig,
    stage03_outcome: Stage03MaterializationOutcome,
    stage03_manifest: Mapping[str, Any],
    review_artifact_sha256: str,
) -> SanitizedStageSummary:
    physical = stage03_manifest.get("physical_identity")
    if not isinstance(physical, dict):
        _fail("STAGE03_MANIFEST_INVALID", "Stage 3 physical identity is malformed")
    input_binding_sha = physical.get("stage03_input_binding_sha256")
    stage02_manifest_sha = physical.get("upstream_stage02_manifest_sha256")
    if not isinstance(input_binding_sha, str) or not isinstance(
        stage02_manifest_sha, str
    ):
        _fail("STAGE03_MANIFEST_INVALID", "Stage 3 fingerprints are malformed")
    slurm_job_id = str((config.operational_metadata or {}).get("slurm_job_id", "0"))
    return SanitizedStageSummary(
        status="STAGE_3_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW",
        stage="STAGE_3",
        stage_contract_version=STAGE03_CONTRACT_VERSION,
        execution_git_sha=config.execution_git_sha,
        slurm_job_id=slurm_job_id,
        development_dataset="BENCHMARK_SAMPLE_V1_DEVELOPMENT",
        development_fingerprint=stage03_outcome.logical_dataset_sha256_v1,
        input_benchmark_fingerprint=config.expected_benchmark_fingerprint,
        logical_fingerprint=stage03_outcome.logical_dataset_sha256_v1,
        schema_fingerprint=stage03_schema_fingerprint(),
        extra_fingerprints={
            "input_binding": input_binding_sha,
            "manifest": stage03_outcome.manifest_sha256,
            "input_stage02_manifest": stage02_manifest_sha,
            "review_subset": config.expected_review_subset_fingerprint,
            "review_artifact": review_artifact_sha256,
        },
        metric_groups=stage03_outcome.metrics,
        checks={
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
            "PUNCTUATION_UNCHANGED": True,
            "STANDARD_NATIVE_INDEPENDENT": True,
        },
        interpretation_code="STAGE03_CONSERVATIVE_CLEANING_CANDIDATE",
    )


def materialize_stage03_development_review(
    config: Stage03ReviewRunConfig,
) -> Stage03ReviewOutcome:
    """Create the fixed 500-row Stage 3 review view and sanitized summary."""
    config.validate()
    if config.production:
        require_goethe_nhr_slurm("development-reporting-stage03-review")
    if config.output_directory.exists() or config.output_directory.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 3 review output already exists")
    identity_table, identity_artifact_sha = _fixed_review_identities(config)
    stage03_table, stage03_outcome, stage03_manifest = _stage03_table_and_manifest(
        config
    )
    metadata = {
        b"development_reporting_contract_version": (
            DEVELOPMENT_REPORTING_CONTRACT_VERSION.encode()
        ),
        b"development_review_subset_contract_version": (
            DEVELOPMENT_REVIEW_SUBSET_CONTRACT_VERSION.encode()
        ),
        b"stage03_review_contract_version": STAGE03_REVIEW_CONTRACT_VERSION.encode(),
        b"stage03_review_schema_version": STAGE03_REVIEW_SCHEMA_VERSION.encode(),
        b"review_subset_fingerprint": config.expected_review_subset_fingerprint.encode(),
        b"input_benchmark_fingerprint": config.expected_benchmark_fingerprint.encode(),
        b"stage_identifier": b"STAGE_3",
        b"stage_contract_version": STAGE03_CONTRACT_VERSION.encode(),
        b"stage_profile_version": STAGE03_PROFILE_VERSION.encode(),
        b"stage_logical_fingerprint": stage03_outcome.logical_dataset_sha256_v1.encode(),
        b"stage_schema_fingerprint": stage03_schema_fingerprint().encode(),
    }
    review_table = _selected_review_table(
        stage03_table, identity_table, metadata=metadata
    )

    parent = config.output_directory.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent.chmod(0o700)
    _require_directory(parent, "STAGE03_REVIEW_OUTPUT_INVALID")
    _require_mode(parent, 0o700, "PERMISSION_FAILURE")
    temporary = parent / f".{config.output_directory.name}.{os.getpid()}.in_progress"
    if temporary.exists() or temporary.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 3 review temporary output exists")
    temporary.mkdir(mode=0o700)
    _write_private_json(
        temporary / STAGE03_REVIEW_IN_PROGRESS_MARKER,
        {"status": "STAGE03_REVIEW_INCOMPLETE"},
    )
    _write_review_parquet(review_table, temporary / STAGE03_REVIEW_PATH)
    review_artifact = _artifact_identity(
        temporary, STAGE03_REVIEW_PATH, row_count=_EXPECTED_REVIEW_ROWS
    )
    summary = _summary(
        config=config,
        stage03_outcome=stage03_outcome,
        stage03_manifest=stage03_manifest,
        review_artifact_sha256=review_artifact.sha256,
    )
    _write_private(
        temporary / STAGE03_SUMMARY_JSON_PATH,
        render_summary_json(summary).encode("utf-8"),
    )
    _write_private(
        temporary / STAGE03_SUMMARY_MD_PATH,
        render_summary_markdown(summary).encode("utf-8"),
    )
    summary_json = _artifact_identity(temporary, STAGE03_SUMMARY_JSON_PATH, row_count=0)
    summary_markdown = _artifact_identity(
        temporary, STAGE03_SUMMARY_MD_PATH, row_count=0
    )
    manifest = {
        "stage03_review_manifest_version": STAGE03_REVIEW_MANIFEST_VERSION,
        "status": "STAGE_3_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW",
        "scientific_identity": {
            "development_reporting_contract_version": (
                DEVELOPMENT_REPORTING_CONTRACT_VERSION
            ),
            "sanitized_summary_contract_version": SANITIZED_SUMMARY_CONTRACT_VERSION,
            "development_review_subset_contract_version": (
                DEVELOPMENT_REVIEW_SUBSET_CONTRACT_VERSION
            ),
            "stage03_review_contract_version": STAGE03_REVIEW_CONTRACT_VERSION,
            "stage03_review_schema_version": STAGE03_REVIEW_SCHEMA_VERSION,
            "stage03_review_schema_fingerprint": stage03_review_schema_fingerprint(),
            "review_subset_fingerprint": config.expected_review_subset_fingerprint,
            "input_benchmark_fingerprint": config.expected_benchmark_fingerprint,
            "stage03_contract_version": STAGE03_CONTRACT_VERSION,
            "stage03_profile_version": STAGE03_PROFILE_VERSION,
            "stage03_logical_fingerprint": (stage03_outcome.logical_dataset_sha256_v1),
            "stage03_schema_fingerprint": stage03_schema_fingerprint(),
            "selected_row_count": _EXPECTED_REVIEW_ROWS,
        },
        "physical_identity": {
            "accepted_development_review_manifest_sha256": (
                config.expected_development_review_manifest_sha256
            ),
            "accepted_review_identity_artifact_sha256": identity_artifact_sha,
            "stage03_manifest_sha256": stage03_outcome.manifest_sha256,
            "artifacts": [
                review_artifact.to_dict(),
                summary_json.to_dict(),
                summary_markdown.to_dict(),
            ],
            "owner_only_permissions": True,
        },
        "validation": {
            "validation_contract_version": STAGE03_REVIEW_VALIDATION_VERSION,
            "accepted_fixed_subset_validated": "PASS",
            "same_ordered_500_identities": "PASS",
            "stage03_bundle_validated": "PASS",
            "stage03_review_schema_exact": "PASS",
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
            "ftfy_version": ftfy.__version__,
            **dict(config.operational_metadata or {}),
        },
    }
    _write_private_json(temporary / STAGE03_REVIEW_MANIFEST_NAME, manifest)
    manifest_artifact = _artifact_identity(
        temporary, STAGE03_REVIEW_MANIFEST_NAME, row_count=0
    )
    _write_private_json(
        temporary / STAGE03_REVIEW_SUCCESS_MARKER,
        {
            "status": "STAGE_3_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW",
            "stage03_review_manifest_sha256": manifest_artifact.sha256,
            "stage03_review_manifest_size_bytes": manifest_artifact.size_bytes,
            "review_subset_fingerprint": config.expected_review_subset_fingerprint,
            "review_artifact_sha256": review_artifact.sha256,
            "selected_row_count": _EXPECTED_REVIEW_ROWS,
        },
    )
    (temporary / STAGE03_REVIEW_IN_PROGRESS_MARKER).unlink()
    _fsync_directory(temporary)
    os.replace(temporary, config.output_directory)
    _fsync_directory(parent)
    return validate_stage03_development_review(
        config.output_directory,
        expected_manifest_sha256=manifest_artifact.sha256,
        expected_stage03_manifest_sha256=config.expected_stage03_manifest_sha256,
        expected_review_subset_fingerprint=config.expected_review_subset_fingerprint,
        expected_identity_table=identity_table,
    )


def validate_stage03_development_review(
    output_directory: Path,
    *,
    expected_manifest_sha256: str,
    expected_stage03_manifest_sha256: str,
    expected_review_subset_fingerprint: str,
    expected_identity_table: pa.Table,
) -> Stage03ReviewOutcome:
    for digest in (
        expected_manifest_sha256,
        expected_stage03_manifest_sha256,
        expected_review_subset_fingerprint,
    ):
        _digest_bytes(digest)
    _reject_holdout_paths(output_directory)
    _require_directory(output_directory, "STAGE03_REVIEW_OUTPUT_INVALID")
    _require_mode(output_directory, 0o700, "PERMISSION_FAILURE")
    expected_files = {
        STAGE03_REVIEW_PATH,
        STAGE03_SUMMARY_JSON_PATH,
        STAGE03_SUMMARY_MD_PATH,
        STAGE03_REVIEW_MANIFEST_NAME,
        STAGE03_REVIEW_SUCCESS_MARKER,
    }
    observed_files = {
        path.name for path in output_directory.iterdir() if path.is_file()
    }
    observed_directories = [
        path for path in output_directory.iterdir() if path.is_dir()
    ]
    if observed_files != expected_files or observed_directories:
        _fail("STAGE03_REVIEW_ARTIFACT_MISMATCH", "Review topology is not exact")
    for name in expected_files:
        _require_regular_file(
            output_directory / name, "STAGE03_REVIEW_ARTIFACT_INVALID"
        )
        _require_mode(output_directory / name, 0o600, "PERMISSION_FAILURE")
    manifest_path = output_directory / STAGE03_REVIEW_MANIFEST_NAME
    manifest_sha = _sha256_file(manifest_path)
    if manifest_sha != expected_manifest_sha256:
        _fail("STAGE03_REVIEW_MANIFEST_MISMATCH", "Review manifest SHA differs")
    manifest = _load_json(manifest_path, "STAGE03_REVIEW_MANIFEST_INVALID")
    success = _load_json(
        output_directory / STAGE03_REVIEW_SUCCESS_MARKER,
        "STAGE03_REVIEW_SUCCESS_INVALID",
    )
    scientific = manifest.get("scientific_identity")
    physical = manifest.get("physical_identity")
    validation = manifest.get("validation")
    if not isinstance(scientific, dict) or not isinstance(physical, dict):
        _fail("STAGE03_REVIEW_MANIFEST_INVALID", "Review identity is malformed")
    if (
        manifest.get("stage03_review_manifest_version")
        != STAGE03_REVIEW_MANIFEST_VERSION
        or manifest.get("status")
        != "STAGE_3_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW"
        or success.get("status")
        != "STAGE_3_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW"
        or success.get("stage03_review_manifest_sha256") != manifest_sha
        or success.get("stage03_review_manifest_size_bytes")
        != manifest_path.stat(follow_symlinks=False).st_size
        or scientific.get("review_subset_fingerprint")
        != expected_review_subset_fingerprint
        or scientific.get("stage03_review_schema_fingerprint")
        != stage03_review_schema_fingerprint()
        or scientific.get("selected_row_count") != _EXPECTED_REVIEW_ROWS
        or physical.get("stage03_manifest_sha256") != expected_stage03_manifest_sha256
        or physical.get("owner_only_permissions") is not True
    ):
        _fail("STAGE03_REVIEW_MANIFEST_MISMATCH", "Review terminal identity differs")
    if (
        not isinstance(validation, dict)
        or any(
            value != "PASS"
            for key, value in validation.items()
            if key != "validation_contract_version"
        )
        or validation.get("validation_contract_version")
        != (STAGE03_REVIEW_VALIDATION_VERSION)
    ):
        _fail("STAGE03_REVIEW_VALIDATION_INCOMPLETE", "Review validation is incomplete")
    raw_artifacts = physical.get("artifacts")
    if not isinstance(raw_artifacts, list) or len(raw_artifacts) != 3:
        _fail("STAGE03_REVIEW_MANIFEST_INVALID", "Review artifacts are malformed")
    artifact_by_path: dict[str, Mapping[str, Any]] = {}
    for raw in raw_artifacts:
        if not isinstance(raw, dict) or not isinstance(raw.get("relative_path"), str):
            _fail("STAGE03_REVIEW_MANIFEST_INVALID", "Review artifact is malformed")
        artifact_by_path[raw["relative_path"]] = raw
        path = output_directory / raw["relative_path"]
        if path.stat(follow_symlinks=False).st_size != raw.get(
            "size_bytes"
        ) or _sha256_file(path) != raw.get("sha256"):
            _fail("STAGE03_REVIEW_ARTIFACT_MISMATCH", "Review artifact SHA differs")
    review_identity = artifact_by_path.get(STAGE03_REVIEW_PATH)
    if (
        review_identity is None
        or review_identity.get("row_count") != _EXPECTED_REVIEW_ROWS
    ):
        _fail("STAGE03_REVIEW_ARTIFACT_MISMATCH", "Review row count is not exact")
    review_path = output_directory / STAGE03_REVIEW_PATH
    try:
        parquet = pq.ParquetFile(review_path, page_checksum_verification=True)
        table = parquet.read(use_threads=False)
    except (OSError, pa.ArrowException) as error:
        raise ReviewSubsetError(
            "STAGE03_REVIEW_READBACK_FAILURE", "Review Parquet read-back failed"
        ) from error
    if not table.schema.remove_metadata().equals(
        stage03_review_schema(), check_metadata=False
    ):
        _fail("STAGE03_REVIEW_SCHEMA_MISMATCH", "Review schema is not exact")
    for name in ("review_order", "development_review_id_v1", "stable_source_row_id_v1"):
        if not table.column(name).equals(expected_identity_table.column(name)):
            _fail("REVIEW_IDENTITY_MISMATCH", "Review identities or order differ")
    summary_value = _load_json(
        output_directory / STAGE03_SUMMARY_JSON_PATH, "UNSAFE_SUMMARY"
    )
    summary = validate_sanitized_summary_payload(summary_value)
    if (
        summary.extra_fingerprints.get("review_artifact")
        != review_identity.get("sha256")
        or summary.extra_fingerprints.get("review_subset")
        != expected_review_subset_fingerprint
        or summary.extra_fingerprints.get("manifest")
        != expected_stage03_manifest_sha256
    ):
        _fail("UNSAFE_SUMMARY", "Stage 3 summary fingerprints differ")
    markdown = (output_directory / STAGE03_SUMMARY_MD_PATH).read_text(encoding="utf-8")
    if markdown != render_summary_markdown(summary):
        _fail("UNSAFE_SUMMARY", "Stage 3 Markdown summary is not canonical")
    review_sha = cast(str, review_identity["sha256"])
    if (
        success.get("review_subset_fingerprint") != expected_review_subset_fingerprint
        or success.get("review_artifact_sha256") != review_sha
        or success.get("selected_row_count") != _EXPECTED_REVIEW_ROWS
    ):
        _fail("STAGE03_REVIEW_TERMINAL_MISMATCH", "Review terminal counts differ")
    return Stage03ReviewOutcome(
        output_directory=output_directory,
        review_subset_fingerprint=expected_review_subset_fingerprint,
        review_artifact_sha256=review_sha,
        manifest_sha256=manifest_sha,
        selected_row_count=_EXPECTED_REVIEW_ROWS,
        summary_json_path=output_directory / STAGE03_SUMMARY_JSON_PATH,
        summary_markdown_path=output_directory / STAGE03_SUMMARY_MD_PATH,
    )


__all__ = [
    "STAGE03_REVIEW_CONTRACT_VERSION",
    "STAGE03_REVIEW_MANIFEST_NAME",
    "STAGE03_REVIEW_PATH",
    "STAGE03_REVIEW_SCHEMA_VERSION",
    "STAGE03_SUMMARY_JSON_PATH",
    "STAGE03_SUMMARY_MD_PATH",
    "Stage03ReviewOutcome",
    "Stage03ReviewRunConfig",
    "materialize_stage03_development_review",
    "stage03_review_schema",
    "stage03_review_schema_fingerprint",
    "validate_stage03_development_review",
]
