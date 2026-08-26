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
from typing import Mapping, NoReturn, Sequence

import pyarrow as pa
import pyarrow.parquet as pq

from ...execution_policy import require_goethe_nhr_slurm
from ..benchmark_runner import (
    BENCHMARK_OUTPUT_SCHEMA_VERSION,
    benchmark_schema,
)
from ..benchmark_sample import BENCHMARK_CONTRACT_VERSION, FEATURE_CONTRACT_VERSION
from ..stages.s02_harmonization import (
    STAGE02_CONTRACT_VERSION,
    STAGE02_MANIFEST_NAME,
    STAGE02_SCHEMA_VERSION,
    STAGE02_STRUCTURAL_COLUMNS,
    Stage02ValidationError,
    stage02_schema,
    stage02_schema_fingerprint,
    validate_stage02_bundle,
)
from .contracts import (
    DEVELOPMENT_REPORTING_CONTRACT_VERSION,
    DEVELOPMENT_REVIEW_SUBSET_CONTRACT_VERSION,
    REVIEW_ALLOCATION_POLICY_VERSION,
    REVIEW_SELECTION_ALGORITHM_VERSION,
    ReviewCandidate,
    ReviewSelection,
    ReviewSubsetConfig,
    ReviewSubsetError,
    ReviewSubsetPolicy,
    development_review_id_v1,
    development_review_subset_sha256_v1,
    quota_shortfall_summary,
    select_development_review_subset,
)
from .summary import (
    SanitizedStageSummary,
    render_summary_json,
    render_summary_markdown,
    validate_sanitized_summary_payload,
)

REVIEW_BUNDLE_MANIFEST_VERSION = "development_review_bundle_manifest_v1"
REVIEW_BUNDLE_VALIDATION_VERSION = "development_review_bundle_validation_v1"
REVIEW_IDENTITY_SCHEMA_VERSION = "development_review_identity_schema_v1"
REVIEW_VIEW_SCHEMA_VERSION = "development_stage02_review_view_schema_v1"
REVIEW_MANIFEST_NAME = "development_review_manifest.json"
REVIEW_SUCCESS_MARKER = "_SUCCESS.json"
REVIEW_IN_PROGRESS_MARKER = "_IN_PROGRESS"
REVIEW_IDENTITIES_PATH = "selection/selected_identities.parquet"
STAGE02_REVIEW_PATH = "stages/stage02/stage02_review.parquet"
REVIEW_SUMMARY_JSON_PATH = "review_subset_summary.json"
REVIEW_SUMMARY_MD_PATH = "review_subset_summary.md"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

_BENCHMARK_CANDIDATE_COLUMNS = (
    "stable_source_row_id_v1",
    "source_file",
    "benchmark_split",
    "location_information_stratum",
    "batch_priority_stratum",
    "country_stratum",
    "standard_native_presence_class",
    "standard_native_equality_class",
    "standard_line_count",
    "native_line_count",
    "missingness_class",
    "combined_script_class",
    "benchmark_challenge_flag",
    "benchmark_challenge_reasons",
)

_STAGE02_VIEW_SOURCE_COLUMNS = (
    "stable_source_row_id_v1",
    "source_file",
    "source_logical_record_number",
    "source_file_sha256",
    "batch_priority",
    "location_information",
    "country_iso_code",
    "street_address_line_1",
    "street_address_line_2",
    "street_address_line_3",
    "street_address_line_4",
    "street_address_line_1_native",
    "street_address_line_2_native",
    "street_address_line_3_native",
    "street_address_line_4_native",
    "postcode",
    "city",
    "region_in_country",
    *STAGE02_STRUCTURAL_COLUMNS,
)


@dataclass(frozen=True, slots=True)
class DevelopmentReviewRunConfig:
    benchmark_development_artifact: Path
    expected_benchmark_artifact_sha256: str
    benchmark_fingerprint: str
    stage02_output_directory: Path
    expected_stage02_manifest_sha256: str
    expected_stage02_logical_fingerprint: str
    output_directory: Path
    execution_git_sha: str
    subset_config: ReviewSubsetConfig = ReviewSubsetConfig()
    production: bool = True
    operational_metadata: Mapping[str, str] | None = None

    def validate(self) -> None:
        self.subset_config.validate()
        for digest in (
            self.expected_benchmark_artifact_sha256,
            self.benchmark_fingerprint,
            self.expected_stage02_manifest_sha256,
            self.expected_stage02_logical_fingerprint,
        ):
            _digest_bytes(digest)
        if _GIT_SHA_RE.fullmatch(self.execution_git_sha) is None:
            _fail("INVALID_GIT_COMMIT", "Execution Git SHA must be a full SHA")
        if any(
            "holdout" in part.casefold()
            for path in (
                self.benchmark_development_artifact,
                self.stage02_output_directory,
                self.output_directory,
            )
            for part in path.parts
        ):
            _fail("HOLDOUT_ACCESS_PROHIBITED", "A review path names HOLDOUT")
        allowed_operational = {"execution_site", "slurm_job_id"}
        for key, value in (self.operational_metadata or {}).items():
            if (
                key not in allowed_operational
                or not isinstance(value, str)
                or not value
                or "\x00" in value
                or len(value) > 128
            ):
                _fail(
                    "INVALID_OPERATIONAL_METADATA",
                    "Operational reporting metadata is invalid",
                )


@dataclass(frozen=True, slots=True)
class ReviewArtifactIdentity:
    relative_path: str
    size_bytes: int
    sha256: str
    row_count: int

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DevelopmentReviewOutcome:
    output_directory: Path
    review_subset_fingerprint: str
    review_artifact_sha256: str
    manifest_sha256: str
    selected_row_count: int
    duplicate_identity_count: int
    source_files_represented: int
    quota_shortfall_category_count: int
    quota_shortfall_total: int


def _fail(code: str, message: str) -> NoReturn:
    raise ReviewSubsetError(code, message)


def _digest_bytes(value: str) -> bytes:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail("INVALID_SHA256", "Digest must be canonical lowercase SHA-256")
    return bytes.fromhex(value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _require_regular_file(path: Path, code: str) -> None:
    if path.is_symlink():
        _fail(code, "Protected artifact must not be a symlink")
    try:
        mode = path.stat(follow_symlinks=False).st_mode
    except OSError as error:
        raise ReviewSubsetError(code, "Protected artifact is unavailable") from error
    if not stat.S_ISREG(mode):
        _fail(code, "Protected artifact must be a regular file")


def _require_directory(path: Path, code: str) -> None:
    if path.is_symlink():
        _fail(code, "Protected directory must not be a symlink")
    try:
        mode = path.stat(follow_symlinks=False).st_mode
    except OSError as error:
        raise ReviewSubsetError(code, "Protected directory is unavailable") from error
    if not stat.S_ISDIR(mode):
        _fail(code, "Protected directory is invalid")


def _require_mode(path: Path, expected: int, code: str) -> None:
    try:
        observed = stat.S_IMODE(path.stat(follow_symlinks=False).st_mode)
    except OSError as error:
        raise ReviewSubsetError(code, "Protected path mode is unavailable") from error
    if observed != expected:
        _fail(code, "Protected path is not owner-only")


def _write_private(path: Path, payload: bytes) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise ReviewSubsetError(
            "CONTROLLED_WRITE_FAILURE",
            "Protected reporting artifact could not be written",
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


def _metadata_text(metadata: Mapping[bytes, bytes], name: str) -> str:
    value = metadata.get(name.encode("utf-8"))
    if value is None:
        _fail("UPSTREAM_METADATA_MISMATCH", "Required upstream metadata is absent")
    try:
        return value.decode("utf-8", errors="strict")
    except UnicodeError as error:
        raise ReviewSubsetError(
            "UPSTREAM_METADATA_MISMATCH", "Upstream metadata is not UTF-8"
        ) from error


def _required_candidate_text(
    values: Mapping[str, list[object]], name: str, row_index: int
) -> str:
    value = values[name][row_index]
    if not isinstance(value, str):
        _fail("BENCHMARK_FEATURE_INVALID", "Benchmark text feature is malformed")
    return value


def _required_candidate_int(
    values: Mapping[str, list[object]], name: str, row_index: int
) -> int:
    value = values[name][row_index]
    if not isinstance(value, int) or isinstance(value, bool):
        _fail("BENCHMARK_FEATURE_INVALID", "Benchmark integer feature is malformed")
    return value


def _required_candidate_bool(
    values: Mapping[str, list[object]], name: str, row_index: int
) -> bool:
    value = values[name][row_index]
    if not isinstance(value, bool):
        _fail("BENCHMARK_FEATURE_INVALID", "Benchmark Boolean feature is malformed")
    return value


def _required_manifest_uint(
    values: Mapping[str, object], name: str, *, allow_zero: bool = True
) -> int:
    value = values.get(name)
    minimum = 0 if allow_zero else 1
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        _fail("REVIEW_MANIFEST_INVALID", "Review integer metadata is malformed")
    return value


def _load_benchmark_candidates(
    path: Path,
    *,
    expected_sha256: str,
    expected_fingerprint: str,
    expected_rows: int,
) -> tuple[tuple[ReviewCandidate, ...], int]:
    _require_regular_file(path, "BENCHMARK_DEVELOPMENT_INVALID")
    _require_mode(path, 0o600, "PERMISSION_FAILURE")
    before = path.stat(follow_symlinks=False)
    if _sha256_file(path) != expected_sha256:
        _fail("BENCHMARK_ARTIFACT_MISMATCH", "DEVELOPMENT artifact SHA-256 differs")
    try:
        parquet = pq.ParquetFile(path, page_checksum_verification=True)
    except (OSError, pa.ArrowException) as error:
        raise ReviewSubsetError(
            "BENCHMARK_READ_FAILURE", "DEVELOPMENT Parquet could not be opened"
        ) from error
    if not parquet.schema_arrow.remove_metadata().equals(
        benchmark_schema(), check_metadata=False
    ):
        _fail("BENCHMARK_SCHEMA_MISMATCH", "DEVELOPMENT schema is not exact")
    metadata = parquet.schema_arrow.metadata or {}
    required = {
        "benchmark_contract_version": BENCHMARK_CONTRACT_VERSION,
        "benchmark_feature_contract_version": FEATURE_CONTRACT_VERSION,
        "benchmark_schema_version": BENCHMARK_OUTPUT_SCHEMA_VERSION,
        "benchmark_fingerprint": expected_fingerprint,
    }
    for name, expected in required.items():
        if _metadata_text(metadata, name) != expected:
            _fail("BENCHMARK_IDENTITY_MISMATCH", "DEVELOPMENT identity is inconsistent")
    candidates: list[ReviewCandidate] = []
    source_files: set[str] = set()
    try:
        for batch in parquet.iter_batches(
            batch_size=4_096,
            columns=list(_BENCHMARK_CANDIDATE_COLUMNS),
            use_threads=False,
        ):
            values: dict[str, list[object]] = {
                name: batch.column(index).to_pylist()
                for index, name in enumerate(batch.schema.names)
            }
            for row_index in range(batch.num_rows):
                reasons_value = _required_candidate_text(
                    values, "benchmark_challenge_reasons", row_index
                )
                reasons = tuple(item for item in reasons_value.split("|") if item)
                identity = values["stable_source_row_id_v1"][row_index]
                if not isinstance(identity, bytes):
                    _fail(
                        "BENCHMARK_FEATURE_INVALID", "Provenance metadata is malformed"
                    )
                candidate = ReviewCandidate(
                    stable_source_row_id_v1=identity,
                    source_file=_required_candidate_text(
                        values, "source_file", row_index
                    ),
                    benchmark_split=_required_candidate_text(
                        values, "benchmark_split", row_index
                    ),
                    location_information_stratum=_required_candidate_text(
                        values, "location_information_stratum", row_index
                    ),
                    batch_priority_stratum=_required_candidate_text(
                        values, "batch_priority_stratum", row_index
                    ),
                    country_stratum=_required_candidate_text(
                        values, "country_stratum", row_index
                    ),
                    standard_native_presence_class=_required_candidate_text(
                        values, "standard_native_presence_class", row_index
                    ),
                    standard_native_equality_class=_required_candidate_text(
                        values, "standard_native_equality_class", row_index
                    ),
                    standard_line_count=_required_candidate_int(
                        values, "standard_line_count", row_index
                    ),
                    native_line_count=_required_candidate_int(
                        values, "native_line_count", row_index
                    ),
                    missingness_class=_required_candidate_text(
                        values, "missingness_class", row_index
                    ),
                    combined_script_class=_required_candidate_text(
                        values, "combined_script_class", row_index
                    ),
                    challenge_flag=_required_candidate_bool(
                        values, "benchmark_challenge_flag", row_index
                    ),
                    challenge_reasons=reasons,
                )
                candidate.validate()
                candidates.append(candidate)
                source_files.add(candidate.source_file)
    except ReviewSubsetError:
        raise
    except (OSError, pa.ArrowException, TypeError, ValueError) as error:
        raise ReviewSubsetError(
            "BENCHMARK_READ_FAILURE", "DEVELOPMENT candidate read-back failed"
        ) from error
    after = path.stat(follow_symlinks=False)
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or _sha256_file(path) != expected_sha256:
        _fail("BENCHMARK_ARTIFACT_CHANGED", "DEVELOPMENT artifact changed during read")
    if len(candidates) != expected_rows:
        _fail("DEVELOPMENT_ROW_COUNT_MISMATCH", "DEVELOPMENT row count is not exact")
    return tuple(candidates), len(source_files)


def _identity_schema(metadata: Mapping[bytes, bytes] | None = None) -> pa.Schema:
    return pa.schema(
        (
            pa.field("review_order", pa.uint32(), nullable=False),
            pa.field("development_review_id_v1", pa.binary(32), nullable=False),
            pa.field("stable_source_row_id_v1", pa.binary(32), nullable=False),
        ),
        metadata=metadata,
    )


def stage02_review_schema(metadata: Mapping[bytes, bytes] | None = None) -> pa.Schema:
    stage_schema = stage02_schema()
    fields = [
        pa.field("review_order", pa.uint32(), nullable=False),
        pa.field("development_review_id_v1", pa.binary(32), nullable=False),
    ]
    fields.extend(stage_schema.field(name) for name in _STAGE02_VIEW_SOURCE_COLUMNS)
    return pa.schema(fields, metadata=metadata)


def _schema_fingerprint(schema: pa.Schema, *, domain: bytes, version: str) -> str:
    digest = hashlib.sha256(domain)
    encoded_version = version.encode("utf-8")
    digest.update(len(encoded_version).to_bytes(8, "big"))
    digest.update(encoded_version)
    digest.update(len(schema).to_bytes(8, "big"))
    for field in schema.remove_metadata():
        for value in (field.name, str(field.type), str(field.nullable).lower()):
            encoded = value.encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
    return digest.hexdigest()


def stage02_review_schema_fingerprint() -> str:
    return _schema_fingerprint(
        stage02_review_schema(),
        domain=b"SAFE_DEVELOPMENT_STAGE02_REVIEW_SCHEMA_V1",
        version=REVIEW_VIEW_SCHEMA_VERSION,
    )


def _artifact_identity(
    root: Path, relative_path: str, *, row_count: int
) -> ReviewArtifactIdentity:
    path = root / relative_path
    _require_regular_file(path, "REVIEW_ARTIFACT_INVALID")
    _require_mode(path, 0o600, "PERMISSION_FAILURE")
    return ReviewArtifactIdentity(
        relative_path=relative_path,
        size_bytes=path.stat(follow_symlinks=False).st_size,
        sha256=_sha256_file(path),
        row_count=row_count,
    )


def _write_parquet(
    table: pa.Table,
    path: Path,
    *,
    statistics_columns: Sequence[str],
) -> None:
    try:
        pq.write_table(
            table,
            path,
            version="2.6",
            data_page_version="1.0",
            compression="zstd",
            compression_level=3,
            use_dictionary=False,
            write_statistics=list(statistics_columns),
            write_page_checksum=True,
            row_group_size=500,
        )
        path.chmod(0o600)
    except (OSError, pa.ArrowException) as error:
        raise ReviewSubsetError(
            "REVIEW_WRITE_FAILURE", "Protected review Parquet could not be written"
        ) from error


def _read_stage02_table(
    root: Path, *, expected_manifest_sha256: str, expected_logical_fingerprint: str
) -> tuple[pa.Table, str]:
    try:
        outcome = validate_stage02_bundle(
            root, expected_manifest_sha256=expected_manifest_sha256
        )
    except Stage02ValidationError as error:
        raise ReviewSubsetError(
            "STAGE02_BUNDLE_INVALID", "Accepted Stage 2 bundle validation failed"
        ) from error
    if outcome.logical_dataset_sha256_v1 != expected_logical_fingerprint:
        _fail("STAGE02_IDENTITY_MISMATCH", "Stage 2 logical fingerprint differs")
    manifest_path = root / STAGE02_MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReviewSubsetError(
            "STAGE02_BUNDLE_INVALID", "Stage 2 manifest could not be read"
        ) from error
    scientific = manifest.get("scientific_identity")
    if (
        not isinstance(scientific, dict)
        or scientific.get("stage02_contract_version") != STAGE02_CONTRACT_VERSION
        or scientific.get("stage02_schema_version") != STAGE02_SCHEMA_VERSION
        or scientific.get("stage02_schema_fingerprint") != stage02_schema_fingerprint()
    ):
        _fail("STAGE02_IDENTITY_MISMATCH", "Stage 2 scientific identity differs")
    artifacts = manifest.get("physical_identity", {}).get("output_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        _fail("STAGE02_BUNDLE_INVALID", "Stage 2 output artifacts are absent")
    tables: list[pa.Table] = []
    for raw in artifacts:
        if not isinstance(raw, dict) or not isinstance(raw.get("relative_path"), str):
            _fail("STAGE02_BUNDLE_INVALID", "Stage 2 artifact identity is malformed")
        path = root / raw["relative_path"]
        try:
            parquet = pq.ParquetFile(path, page_checksum_verification=True)
            tables.append(parquet.read(use_threads=False))
        except (OSError, pa.ArrowException) as error:
            raise ReviewSubsetError(
                "STAGE02_READ_FAILURE", "Stage 2 review input could not be read"
            ) from error
    try:
        table = pa.concat_tables(tables)
    except pa.ArrowException as error:
        raise ReviewSubsetError(
            "STAGE02_READ_FAILURE", "Stage 2 shards could not be combined"
        ) from error
    if not table.schema.remove_metadata().equals(
        stage02_schema(), check_metadata=False
    ):
        _fail("STAGE02_SCHEMA_MISMATCH", "Stage 2 review input schema is not exact")
    return table, _sha256_file(manifest_path)


def _selected_stage02_view(
    stage02_table: pa.Table,
    *,
    selection: ReviewSelection,
    benchmark_fingerprint: str,
    review_subset_fingerprint: str,
    stage02_logical_fingerprint: str,
) -> pa.Table:
    stable_ids = stage02_table.column("stable_source_row_id_v1").to_pylist()
    index_by_identity: dict[bytes, int] = {}
    for index, identity in enumerate(stable_ids):
        if not isinstance(identity, bytes):
            _fail("STAGE02_PROVENANCE_INVALID", "Stage 2 stable identity is malformed")
        if identity in index_by_identity:
            _fail("STAGE02_PROVENANCE_INVALID", "Stage 2 stable identity is duplicated")
        index_by_identity[identity] = index
    try:
        indices = [
            index_by_identity[item.stable_source_row_id_v1]
            for item in selection.selected
        ]
    except KeyError as error:
        raise ReviewSubsetError(
            "STAGE02_PROVENANCE_MISMATCH", "A selected DEVELOPMENT row is absent"
        ) from error
    selected = stage02_table.take(pa.array(indices, type=pa.uint32()))
    review_orders = pa.array(range(1, len(indices) + 1), type=pa.uint32())
    review_ids = pa.array(
        [
            development_review_id_v1(
                benchmark_fingerprint, item.stable_source_row_id_v1
            )
            for item in selection.selected
        ],
        type=pa.binary(32),
    )
    metadata = {
        b"development_reporting_contract_version": (
            DEVELOPMENT_REPORTING_CONTRACT_VERSION.encode()
        ),
        b"development_review_subset_contract_version": (
            DEVELOPMENT_REVIEW_SUBSET_CONTRACT_VERSION.encode()
        ),
        b"review_subset_fingerprint": review_subset_fingerprint.encode(),
        b"input_benchmark_fingerprint": benchmark_fingerprint.encode(),
        b"stage_identifier": b"STAGE_2",
        b"stage_contract_version": STAGE02_CONTRACT_VERSION.encode(),
        b"stage_logical_fingerprint": stage02_logical_fingerprint.encode(),
        b"stage_schema_fingerprint": stage02_schema_fingerprint().encode(),
        b"review_view_schema_version": REVIEW_VIEW_SCHEMA_VERSION.encode(),
    }
    arrays: list[pa.ChunkedArray | pa.Array] = [review_orders, review_ids]
    arrays.extend(selected.column(name) for name in _STAGE02_VIEW_SOURCE_COLUMNS)
    return pa.Table.from_arrays(arrays, schema=stage02_review_schema(metadata))


def _identity_table(
    selection: ReviewSelection,
    *,
    benchmark_fingerprint: str,
    review_subset_fingerprint: str,
) -> pa.Table:
    metadata = {
        b"development_reporting_contract_version": (
            DEVELOPMENT_REPORTING_CONTRACT_VERSION.encode()
        ),
        b"development_review_subset_contract_version": (
            DEVELOPMENT_REVIEW_SUBSET_CONTRACT_VERSION.encode()
        ),
        b"review_identity_schema_version": REVIEW_IDENTITY_SCHEMA_VERSION.encode(),
        b"input_benchmark_fingerprint": benchmark_fingerprint.encode(),
        b"review_subset_fingerprint": review_subset_fingerprint.encode(),
    }
    identities = [item.stable_source_row_id_v1 for item in selection.selected]
    return pa.Table.from_arrays(
        (
            pa.array(range(1, len(identities) + 1), type=pa.uint32()),
            pa.array(
                [
                    development_review_id_v1(benchmark_fingerprint, item)
                    for item in identities
                ],
                type=pa.binary(32),
            ),
            pa.array(identities, type=pa.binary(32)),
        ),
        schema=_identity_schema(metadata),
    )


def _safe_counter(
    values: Sequence[str], mapping: Mapping[str, str], *, allow_other: bool
) -> dict[str, int]:
    counts: Counter[str] = Counter({category: 0 for category in set(mapping.values())})
    if allow_other:
        counts["OTHER"] = 0
    for value in values:
        category = mapping.get(value)
        if category is None:
            if not allow_other:
                _fail("UNSAFE_SUMMARY", "Structural category is not allowlisted")
            category = "OTHER"
        counts[category] += 1
    return dict(sorted(counts.items()))


def _line_count_counter(values: Sequence[int]) -> dict[str, int]:
    counts: Counter[str] = Counter({str(index): 0 for index in range(5)})
    counts.update(str(value) for value in values)
    return dict(sorted(counts.items()))


def _review_summary(
    *,
    candidates: Sequence[ReviewCandidate],
    selection: ReviewSelection,
    benchmark_fingerprint: str,
    stage02_logical_fingerprint: str,
    review_subset_fingerprint: str,
    execution_git_sha: str,
    slurm_job_id: str,
) -> SanitizedStageSummary:
    selected = selection.selected
    location_mapping = {
        "no_geocoding_information": "NO_GEOCODING_INFORMATION",
        "previous_geocoding_failure": "PREVIOUS_GEOCODING_FAILURE",
        "postcode_interpolated": "POSTCODE_INTERPOLATED",
        "region_interpolated": "REGION_INTERPOLATED",
        "EMPTY": "EMPTY",
    }
    batch_mapping = {value: value for value in ("0", "1", "2", "3", "EMPTY")}
    presence_mapping = {
        "STANDARD_ONLY": "STANDARD_ONLY",
        "NATIVE_ONLY": "NATIVE_ONLY",
        "BOTH_PRESENT": "BOTH",
        "NEITHER_PRESENT": "NEITHER",
    }
    equality_mapping = {
        value: value
        for value in (
            "EXACTLY_EQUAL",
            "CASE_ONLY_OR_TRIVIALLY_EQUAL",
            "MATERIALLY_DIFFERENT",
            "NOT_BOTH_PRESENT",
        )
    }
    script_mapping = {
        value: value
        for value in (
            "LATIN_ONLY",
            "NON_LATIN_PRESENT",
            "MIXED_SCRIPT",
            "EMPTY",
            "COMMON_OR_UNKNOWN_ONLY",
        )
    }
    known_reasons = {
        "STANDARD_MISSING_NATIVE_PRESENT",
        "STANDARD_NATIVE_MATERIALLY_DIFFERENT",
        "POSTCODE_MISSING",
        "CITY_MISSING",
        "REGION_MISSING",
        "COUNTRY_MISSING",
        "MULTIPLE_ADDRESS_LINES",
        "NON_LATIN_SCRIPT",
        "MIXED_SCRIPT",
        "VERY_LONG_ADDRESS_FIELD",
        "PREVIOUS_GEOCODING_FAILURE",
        "NO_GEOCODING_INFORMATION",
    }
    reason_counts: Counter[str] = Counter({reason: 0 for reason in known_reasons})
    for item in selected:
        for reason in item.challenge_reasons:
            if reason not in known_reasons:
                _fail("UNSAFE_SUMMARY", "Challenge reason is not allowlisted")
            reason_counts[reason] += 1
    missingness_counts = {
        label: sum(label in item.missingness_class for item in selected)
        for label in (
            "POSTCODE_MISSING",
            "CITY_MISSING",
            "REGION_MISSING",
            "COUNTRY_MISSING",
        )
    }
    shortfalls = quota_shortfall_summary(selection.quota_diagnostics)
    return SanitizedStageSummary(
        status="DEVELOPMENT_REVIEW_SUBSET_V1_MATERIALIZED",
        stage="DEVELOPMENT_REVIEW_SUBSET_V1",
        stage_contract_version=DEVELOPMENT_REVIEW_SUBSET_CONTRACT_VERSION,
        execution_git_sha=execution_git_sha,
        slurm_job_id=slurm_job_id,
        development_dataset="BENCHMARK_SAMPLE_V1_DEVELOPMENT",
        development_fingerprint=review_subset_fingerprint,
        input_benchmark_fingerprint=benchmark_fingerprint,
        logical_fingerprint=review_subset_fingerprint,
        schema_fingerprint=stage02_review_schema_fingerprint(),
        metric_groups={
            "REVIEW_ROW_INTEGRITY": {
                "SELECTED_ROWS": len(selected),
                "DUPLICATE_IDENTITIES": 0,
                "HOLDOUT_ROWS": 0,
            },
            "SOURCE_FILE_COVERAGE": {
                "DEVELOPMENT_SOURCE_FILES": len(
                    {item.source_file for item in candidates}
                ),
                "REVIEW_SOURCE_FILES": len({item.source_file for item in selected}),
            },
            "LOCATION_INFORMATION": _safe_counter(
                [item.location_information_stratum for item in selected],
                location_mapping,
                allow_other=True,
            ),
            "BATCH_PRIORITY": _safe_counter(
                [item.batch_priority_stratum for item in selected],
                batch_mapping,
                allow_other=True,
            ),
            "STANDARD_NATIVE_AVAILABILITY": _safe_counter(
                [item.standard_native_presence_class for item in selected],
                presence_mapping,
                allow_other=False,
            ),
            "STANDARD_NATIVE_EQUALITY": _safe_counter(
                [item.standard_native_equality_class for item in selected],
                equality_mapping,
                allow_other=False,
            ),
            "STANDARD_LINE_COUNTS": _line_count_counter(
                [item.standard_line_count for item in selected]
            ),
            "NATIVE_LINE_COUNTS": _line_count_counter(
                [item.native_line_count for item in selected]
            ),
            "MISSINGNESS": missingness_counts,
            "SCRIPT_CLASSES": _safe_counter(
                [item.combined_script_class for item in selected],
                script_mapping,
                allow_other=False,
            ),
            "CHALLENGE_REASONS": dict(sorted(reason_counts.items())),
            "COUNTRY_COVERAGE": {
                "AVAILABLE_COUNTRIES": len(
                    {item.country_stratum for item in candidates}
                ),
                "REPRESENTED_COUNTRIES": len(
                    {item.country_stratum for item in selected}
                ),
            },
            "QUOTA_SHORTFALLS": dict(shortfalls),
        },
        checks={
            "STABLE_IDENTITIES_PRESERVED": True,
            "RAW_FIELDS_UNCHANGED": True,
            "HOLDOUT_UNTOUCHED": True,
            "OWNER_ONLY_PERMISSIONS": True,
            "PROTECTED_REVIEW_ARTIFACT": True,
            "ATOMIC_PUBLICATION": True,
            "INPUT_IDENTITY_BOUND": True,
        },
        interpretation_code="REVIEW_SUBSET_FIXED",
    )


def _validate_written_parquet(
    path: Path,
    *,
    expected_schema: pa.Schema,
    expected_rows: int,
    expected_stable_ids: Sequence[bytes],
) -> None:
    _require_regular_file(path, "REVIEW_ARTIFACT_INVALID")
    _require_mode(path, 0o600, "PERMISSION_FAILURE")
    try:
        parquet = pq.ParquetFile(path, page_checksum_verification=True)
        if not parquet.schema_arrow.equals(expected_schema, check_metadata=True):
            _fail("REVIEW_SCHEMA_MISMATCH", "Review artifact schema is not exact")
        table = parquet.read(columns=["stable_source_row_id_v1"], use_threads=False)
    except ReviewSubsetError:
        raise
    except (OSError, pa.ArrowException) as error:
        raise ReviewSubsetError(
            "REVIEW_READBACK_FAILURE", "Review artifact read-back failed"
        ) from error
    observed = table.column("stable_source_row_id_v1").to_pylist()
    if table.num_rows != expected_rows or observed != list(expected_stable_ids):
        _fail("REVIEW_IDENTITY_MISMATCH", "Review artifact identities differ")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def materialize_stage02_development_review(
    config: DevelopmentReviewRunConfig,
) -> DevelopmentReviewOutcome:
    """Create a passive fixed subset and Stage 2 view from DEVELOPMENT only."""
    config.validate()
    if config.production:
        require_goethe_nhr_slurm("development-reporting-stage02-review")
    if config.output_directory.exists() or config.output_directory.is_symlink():
        _fail("OUTPUT_COLLISION", "Review output directory already exists")
    candidates, _source_file_count = _load_benchmark_candidates(
        config.benchmark_development_artifact,
        expected_sha256=config.expected_benchmark_artifact_sha256,
        expected_fingerprint=config.benchmark_fingerprint,
        expected_rows=config.subset_config.expected_development_rows,
    )
    selection = select_development_review_subset(
        candidates,
        benchmark_fingerprint=config.benchmark_fingerprint,
        config=config.subset_config,
    )
    selected_identities = tuple(
        item.stable_source_row_id_v1 for item in selection.selected
    )
    subset_fingerprint = development_review_subset_sha256_v1(
        benchmark_fingerprint=config.benchmark_fingerprint,
        selected_identities=selected_identities,
        config=config.subset_config,
    )
    stage02_table, observed_manifest_sha = _read_stage02_table(
        config.stage02_output_directory,
        expected_manifest_sha256=config.expected_stage02_manifest_sha256,
        expected_logical_fingerprint=config.expected_stage02_logical_fingerprint,
    )
    if observed_manifest_sha != config.expected_stage02_manifest_sha256:
        _fail("STAGE02_MANIFEST_MISMATCH", "Stage 2 manifest changed")
    if stage02_table.num_rows != config.subset_config.expected_development_rows:
        _fail("STAGE02_ROW_COUNT_MISMATCH", "Stage 2 DEVELOPMENT row count differs")
    view_table = _selected_stage02_view(
        stage02_table,
        selection=selection,
        benchmark_fingerprint=config.benchmark_fingerprint,
        review_subset_fingerprint=subset_fingerprint,
        stage02_logical_fingerprint=config.expected_stage02_logical_fingerprint,
    )
    identity_table = _identity_table(
        selection,
        benchmark_fingerprint=config.benchmark_fingerprint,
        review_subset_fingerprint=subset_fingerprint,
    )

    parent = config.output_directory.parent
    if parent.is_symlink():
        _fail("REVIEW_OUTPUT_INVALID", "Review output parent must not be a symlink")
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _require_directory(parent, "REVIEW_OUTPUT_INVALID")
    parent.chmod(0o700)
    _require_mode(parent, 0o700, "PERMISSION_FAILURE")
    temporary = parent / f".{config.output_directory.name}.{os.getpid()}.in_progress"
    if temporary.exists() or temporary.is_symlink():
        _fail("OUTPUT_COLLISION", "Review temporary output already exists")
    temporary.mkdir(mode=0o700)
    for relative in ("selection", "stages", "stages/stage02"):
        directory = temporary / relative
        directory.mkdir(mode=0o700)
    _write_private_json(
        temporary / REVIEW_IN_PROGRESS_MARKER,
        {"status": "DEVELOPMENT_REVIEW_INCOMPLETE"},
    )
    _write_parquet(
        identity_table,
        temporary / REVIEW_IDENTITIES_PATH,
        statistics_columns=("review_order",),
    )
    _write_parquet(
        view_table,
        temporary / STAGE02_REVIEW_PATH,
        statistics_columns=("review_order", *STAGE02_STRUCTURAL_COLUMNS),
    )
    _validate_written_parquet(
        temporary / REVIEW_IDENTITIES_PATH,
        expected_schema=identity_table.schema,
        expected_rows=config.subset_config.target_count,
        expected_stable_ids=selected_identities,
    )
    _validate_written_parquet(
        temporary / STAGE02_REVIEW_PATH,
        expected_schema=view_table.schema,
        expected_rows=config.subset_config.target_count,
        expected_stable_ids=selected_identities,
    )

    slurm_job_id = str((config.operational_metadata or {}).get("slurm_job_id", "0"))
    summary = _review_summary(
        candidates=candidates,
        selection=selection,
        benchmark_fingerprint=config.benchmark_fingerprint,
        stage02_logical_fingerprint=config.expected_stage02_logical_fingerprint,
        review_subset_fingerprint=subset_fingerprint,
        execution_git_sha=config.execution_git_sha,
        slurm_job_id=slurm_job_id,
    )
    _write_private(
        temporary / REVIEW_SUMMARY_JSON_PATH,
        render_summary_json(summary).encode("utf-8"),
    )
    _write_private(
        temporary / REVIEW_SUMMARY_MD_PATH,
        render_summary_markdown(summary).encode("utf-8"),
    )
    artifacts = tuple(
        _artifact_identity(
            temporary,
            relative,
            row_count=(
                config.subset_config.target_count
                if relative.endswith(".parquet")
                else 0
            ),
        )
        for relative in (
            REVIEW_IDENTITIES_PATH,
            STAGE02_REVIEW_PATH,
            REVIEW_SUMMARY_JSON_PATH,
            REVIEW_SUMMARY_MD_PATH,
        )
    )
    shortfalls = quota_shortfall_summary(selection.quota_diagnostics)
    manifest = {
        "development_review_bundle_manifest_version": REVIEW_BUNDLE_MANIFEST_VERSION,
        "status": "DEVELOPMENT_REVIEW_SUBSET_V1_MATERIALIZED",
        "scientific_identity": {
            "development_reporting_contract_version": (
                DEVELOPMENT_REPORTING_CONTRACT_VERSION
            ),
            "development_review_subset_contract_version": (
                DEVELOPMENT_REVIEW_SUBSET_CONTRACT_VERSION
            ),
            "selection_algorithm_version": REVIEW_SELECTION_ALGORITHM_VERSION,
            "allocation_policy_version": REVIEW_ALLOCATION_POLICY_VERSION,
            "input_benchmark_contract_version": BENCHMARK_CONTRACT_VERSION,
            "input_benchmark_fingerprint": config.benchmark_fingerprint,
            "input_development_row_count": config.subset_config.expected_development_rows,
            "selected_row_count": config.subset_config.target_count,
            "review_subset_fingerprint": subset_fingerprint,
            "selection_policy": config.subset_config.policy.to_dict(),
            "stage02_contract_version": STAGE02_CONTRACT_VERSION,
            "stage02_logical_fingerprint": config.expected_stage02_logical_fingerprint,
            "stage02_schema_fingerprint": stage02_schema_fingerprint(),
            "review_view_schema_version": REVIEW_VIEW_SCHEMA_VERSION,
            "review_view_schema_fingerprint": stage02_review_schema_fingerprint(),
        },
        "protected_aggregate_evidence": {
            "development_only": True,
            "holdout_rows": 0,
            "duplicate_selected_identity_count": 0,
            "source_files_represented": len(
                {item.source_file for item in selection.selected}
            ),
            "quota_shortfall_category_count": shortfalls["SHORTFALL_CATEGORY_COUNT"],
            "quota_shortfall_total": shortfalls["SHORTFALL_TOTAL"],
            "quota_diagnostics": [asdict(item) for item in selection.quota_diagnostics],
        },
        "physical_identity": {
            "benchmark_development_artifact_sha256": (
                config.expected_benchmark_artifact_sha256
            ),
            "stage02_manifest_sha256": config.expected_stage02_manifest_sha256,
            "artifacts": [item.to_dict() for item in artifacts],
            "owner_only_permissions": True,
        },
        "validation": {
            "validation_contract_version": REVIEW_BUNDLE_VALIDATION_VERSION,
            "benchmark_identity_and_development_split": "PASS",
            "exact_selected_count": "PASS",
            "selected_identity_uniqueness": "PASS",
            "stage02_identity_and_schema": "PASS",
            "stable_identity_preservation": "PASS",
            "protected_parquet_readback": "PASS",
            "sanitized_summary_allowlist": "PASS",
            "holdout_exclusion": "PASS",
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
    _write_private_json(temporary / REVIEW_MANIFEST_NAME, manifest)
    manifest_identity = _artifact_identity(temporary, REVIEW_MANIFEST_NAME, row_count=0)
    success = {
        "status": "DEVELOPMENT_REVIEW_SUBSET_V1_MATERIALIZED",
        "development_review_manifest_sha256": manifest_identity.sha256,
        "development_review_manifest_size_bytes": manifest_identity.size_bytes,
        "review_subset_fingerprint": subset_fingerprint,
        "selected_row_count": config.subset_config.target_count,
        "duplicate_selected_identity_count": 0,
    }
    _write_private_json(temporary / REVIEW_SUCCESS_MARKER, success)
    (temporary / REVIEW_IN_PROGRESS_MARKER).unlink()
    for directory in (
        temporary / "selection",
        temporary / "stages" / "stage02",
        temporary / "stages",
        temporary,
    ):
        _fsync_directory(directory)
    os.replace(temporary, config.output_directory)
    _fsync_directory(parent)
    outcome = validate_development_review_bundle(
        config.output_directory,
        expected_manifest_sha256=manifest_identity.sha256,
        expected_benchmark_fingerprint=config.benchmark_fingerprint,
        expected_stage02_logical_fingerprint=config.expected_stage02_logical_fingerprint,
    )
    return outcome


def validate_development_review_bundle(
    output_directory: Path,
    *,
    expected_manifest_sha256: str,
    expected_benchmark_fingerprint: str,
    expected_stage02_logical_fingerprint: str,
) -> DevelopmentReviewOutcome:
    _digest_bytes(expected_manifest_sha256)
    _digest_bytes(expected_benchmark_fingerprint)
    _digest_bytes(expected_stage02_logical_fingerprint)
    _require_directory(output_directory, "REVIEW_OUTPUT_INVALID")
    _require_mode(output_directory, 0o700, "PERMISSION_FAILURE")
    if (output_directory / REVIEW_IN_PROGRESS_MARKER).exists():
        _fail("REVIEW_INCOMPLETE", "Review output retains an in-progress marker")
    expected_directories = {"selection", "stages", "stages/stage02"}
    observed_directories: set[str] = set()
    observed_files: set[str] = set()
    for current_root, directory_names, file_names in os.walk(
        output_directory, followlinks=False
    ):
        current = Path(current_root)
        _require_mode(current, 0o700, "PERMISSION_FAILURE")
        for name in directory_names:
            path = current / name
            _require_directory(path, "REVIEW_OUTPUT_INVALID")
            observed_directories.add(path.relative_to(output_directory).as_posix())
        for name in file_names:
            path = current / name
            _require_regular_file(path, "REVIEW_OUTPUT_INVALID")
            _require_mode(path, 0o600, "PERMISSION_FAILURE")
            observed_files.add(path.relative_to(output_directory).as_posix())
    expected_files = {
        REVIEW_IDENTITIES_PATH,
        STAGE02_REVIEW_PATH,
        REVIEW_SUMMARY_JSON_PATH,
        REVIEW_SUMMARY_MD_PATH,
        REVIEW_MANIFEST_NAME,
        REVIEW_SUCCESS_MARKER,
    }
    if observed_directories != expected_directories or observed_files != expected_files:
        _fail("REVIEW_ARTIFACT_MISMATCH", "Review output topology is not exact")
    manifest_path = output_directory / REVIEW_MANIFEST_NAME
    success_path = output_directory / REVIEW_SUCCESS_MARKER
    if _sha256_file(manifest_path) != expected_manifest_sha256:
        _fail("REVIEW_MANIFEST_MISMATCH", "Review manifest SHA-256 differs")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        success = json.loads(success_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReviewSubsetError(
            "REVIEW_MANIFEST_INVALID", "Review terminal JSON is malformed"
        ) from error
    if not isinstance(manifest, dict) or not isinstance(success, dict):
        _fail("REVIEW_MANIFEST_INVALID", "Review terminal JSON is malformed")
    expected_success_keys = {
        "status",
        "development_review_manifest_sha256",
        "development_review_manifest_size_bytes",
        "review_subset_fingerprint",
        "selected_row_count",
        "duplicate_selected_identity_count",
    }
    if set(success) != expected_success_keys:
        _fail("REVIEW_MANIFEST_INVALID", "Review success marker is malformed")
    scientific = manifest.get("scientific_identity")
    physical = manifest.get("physical_identity")
    validation = manifest.get("validation")
    if not isinstance(scientific, dict) or not isinstance(physical, dict):
        _fail("REVIEW_MANIFEST_INVALID", "Review identity is malformed")
    if (
        manifest.get("development_review_bundle_manifest_version")
        != REVIEW_BUNDLE_MANIFEST_VERSION
        or manifest.get("status") != "DEVELOPMENT_REVIEW_SUBSET_V1_MATERIALIZED"
        or success.get("status") != "DEVELOPMENT_REVIEW_SUBSET_V1_MATERIALIZED"
        or success.get("development_review_manifest_sha256") != expected_manifest_sha256
        or scientific.get("development_reporting_contract_version")
        != DEVELOPMENT_REPORTING_CONTRACT_VERSION
        or scientific.get("development_review_subset_contract_version")
        != DEVELOPMENT_REVIEW_SUBSET_CONTRACT_VERSION
        or scientific.get("input_benchmark_fingerprint")
        != expected_benchmark_fingerprint
        or scientific.get("stage02_logical_fingerprint")
        != expected_stage02_logical_fingerprint
        or scientific.get("stage02_schema_fingerprint") != stage02_schema_fingerprint()
        or scientific.get("review_view_schema_fingerprint")
        != stage02_review_schema_fingerprint()
        or success.get("selected_row_count") != scientific.get("selected_row_count")
        or success.get("duplicate_selected_identity_count") != 0
    ):
        _fail("REVIEW_IDENTITY_MISMATCH", "Review scientific identity differs")
    if (
        not isinstance(validation, dict)
        or validation.get("validation_contract_version")
        != REVIEW_BUNDLE_VALIDATION_VERSION
        or any(
            value != "PASS"
            for key, value in validation.items()
            if key != "validation_contract_version"
        )
    ):
        _fail("REVIEW_VALIDATION_INCOMPLETE", "Review validation gates are incomplete")
    raw_artifacts = physical.get("artifacts")
    if (
        not isinstance(raw_artifacts, list)
        or physical.get("owner_only_permissions") is not True
    ):
        _fail("REVIEW_MANIFEST_INVALID", "Review physical identity is incomplete")
    expected_artifact_paths = {
        REVIEW_IDENTITIES_PATH,
        STAGE02_REVIEW_PATH,
        REVIEW_SUMMARY_JSON_PATH,
        REVIEW_SUMMARY_MD_PATH,
    }
    artifacts: dict[str, ReviewArtifactIdentity] = {}
    for raw in raw_artifacts:
        if not isinstance(raw, dict):
            _fail("REVIEW_MANIFEST_INVALID", "Review artifact identity is malformed")
        if set(raw) != {"relative_path", "size_bytes", "sha256", "row_count"}:
            _fail("REVIEW_MANIFEST_INVALID", "Review artifact identity is malformed")
        relative_path = raw.get("relative_path")
        sha256 = raw.get("sha256")
        if not isinstance(relative_path, str) or not isinstance(sha256, str):
            _fail("REVIEW_MANIFEST_INVALID", "Review artifact identity is malformed")
        artifact = ReviewArtifactIdentity(
            relative_path=relative_path,
            size_bytes=_required_manifest_uint(raw, "size_bytes"),
            sha256=sha256,
            row_count=_required_manifest_uint(raw, "row_count"),
        )
        _digest_bytes(artifact.sha256)
        if artifact.relative_path in artifacts:
            _fail("REVIEW_MANIFEST_INVALID", "Review artifact path is duplicated")
        path = output_directory / artifact.relative_path
        if (
            path.stat(follow_symlinks=False).st_size != artifact.size_bytes
            or _sha256_file(path) != artifact.sha256
        ):
            _fail("REVIEW_ARTIFACT_MISMATCH", "Review artifact identity differs")
        artifacts[artifact.relative_path] = artifact
    if set(artifacts) != expected_artifact_paths:
        _fail("REVIEW_ARTIFACT_MISMATCH", "Review artifact set is incomplete")
    selected_rows = scientific.get("selected_row_count")
    subset_fingerprint = scientific.get("review_subset_fingerprint")
    if not isinstance(selected_rows, int) or isinstance(selected_rows, bool):
        _fail("REVIEW_MANIFEST_INVALID", "Selected row count is malformed")
    if not isinstance(subset_fingerprint, str):
        _fail("REVIEW_MANIFEST_INVALID", "Review fingerprint is malformed")
    _digest_bytes(subset_fingerprint)
    if (
        success.get("development_review_manifest_size_bytes")
        != manifest_path.stat(follow_symlinks=False).st_size
        or success.get("review_subset_fingerprint") != subset_fingerprint
    ):
        _fail("REVIEW_IDENTITY_MISMATCH", "Review success identity differs")
    try:
        identity_parquet = pq.ParquetFile(
            output_directory / REVIEW_IDENTITIES_PATH,
            page_checksum_verification=True,
        )
        view_parquet = pq.ParquetFile(
            output_directory / STAGE02_REVIEW_PATH,
            page_checksum_verification=True,
        )
        identities_table = identity_parquet.read(use_threads=False)
        view_identity_table = view_parquet.read(
            columns=(
                "review_order",
                "development_review_id_v1",
                "stable_source_row_id_v1",
            ),
            use_threads=False,
        )
    except (OSError, pa.ArrowException) as error:
        raise ReviewSubsetError(
            "REVIEW_READBACK_FAILURE", "Review page-checksum read-back failed"
        ) from error
    if identity_parquet.schema_arrow.metadata is None:
        _fail("REVIEW_SCHEMA_MISMATCH", "Review identity metadata is missing")
    identity_metadata = identity_parquet.schema_arrow.metadata
    if (
        _metadata_text(identity_metadata, "review_subset_fingerprint")
        != subset_fingerprint
        or _metadata_text(identity_metadata, "input_benchmark_fingerprint")
        != expected_benchmark_fingerprint
    ):
        _fail("REVIEW_IDENTITY_MISMATCH", "Review identity metadata differs")
    if not identity_parquet.schema_arrow.remove_metadata().equals(
        _identity_schema(), check_metadata=False
    ):
        _fail("REVIEW_SCHEMA_MISMATCH", "Review identity schema differs")
    view_metadata = view_parquet.schema_arrow.metadata or {}
    if not view_parquet.schema_arrow.remove_metadata().equals(
        stage02_review_schema(), check_metadata=False
    ) or (
        _metadata_text(view_metadata, "review_subset_fingerprint") != subset_fingerprint
        or _metadata_text(view_metadata, "input_benchmark_fingerprint")
        != expected_benchmark_fingerprint
        or _metadata_text(view_metadata, "stage_logical_fingerprint")
        != expected_stage02_logical_fingerprint
        or _metadata_text(view_metadata, "stage_schema_fingerprint")
        != stage02_schema_fingerprint()
    ):
        _fail("REVIEW_SCHEMA_MISMATCH", "Stage review schema or metadata differs")
    identities = identities_table.column("stable_source_row_id_v1").to_pylist()
    identity_orders = identities_table.column("review_order").to_pylist()
    identity_review_ids = identities_table.column(
        "development_review_id_v1"
    ).to_pylist()
    view_orders = view_identity_table.column("review_order").to_pylist()
    view_review_ids = view_identity_table.column("development_review_id_v1").to_pylist()
    view_ids = view_identity_table.column("stable_source_row_id_v1").to_pylist()
    expected_orders = list(range(1, selected_rows + 1))
    expected_review_ids = [
        development_review_id_v1(expected_benchmark_fingerprint, identity)
        for identity in identities
    ]
    if (
        identities_table.num_rows != selected_rows
        or len(set(identities)) != selected_rows
        or identity_orders != expected_orders
        or view_orders != expected_orders
        or identity_review_ids != expected_review_ids
        or view_review_ids != expected_review_ids
        or identities != view_ids
    ):
        _fail("REVIEW_IDENTITY_MISMATCH", "Review identity rows are inconsistent")
    raw_policy = scientific.get("selection_policy")
    if (
        not isinstance(raw_policy, dict)
        or raw_policy.get("allocation_policy_version")
        != REVIEW_ALLOCATION_POLICY_VERSION
    ):
        _fail("REVIEW_MANIFEST_INVALID", "Review selection policy is malformed")
    policy_field_names = (
        "minimum_per_country",
        "minimum_per_location",
        "minimum_per_batch_priority",
        "minimum_per_presence_class",
        "minimum_per_equality_class",
        "minimum_per_script_class",
        "minimum_per_line_count",
        "minimum_per_missingness_class",
        "minimum_per_challenge_flag",
        "minimum_per_challenge_reason",
    )
    if set(raw_policy) != {"allocation_policy_version", *policy_field_names}:
        _fail("REVIEW_MANIFEST_INVALID", "Review selection policy is malformed")
    try:
        policy = ReviewSubsetPolicy(
            **{
                name: _required_manifest_uint(raw_policy, name, allow_zero=False)
                for name in policy_field_names
            }
        )
        config = ReviewSubsetConfig(
            target_count=selected_rows,
            expected_development_rows=_required_manifest_uint(
                scientific, "input_development_row_count", allow_zero=False
            ),
            policy=policy,
        )
        config.validate()
    except (KeyError, TypeError, ValueError) as error:
        raise ReviewSubsetError(
            "REVIEW_MANIFEST_INVALID", "Review selection policy is malformed"
        ) from error
    if (
        development_review_subset_sha256_v1(
            benchmark_fingerprint=expected_benchmark_fingerprint,
            selected_identities=identities,
            config=config,
        )
        != subset_fingerprint
    ):
        _fail("REVIEW_FINGERPRINT_MISMATCH", "Review subset fingerprint differs")
    try:
        summary_payload = json.loads(
            (output_directory / REVIEW_SUMMARY_JSON_PATH).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReviewSubsetError(
            "UNSAFE_SUMMARY", "Sanitized summary JSON is malformed"
        ) from error
    if not isinstance(summary_payload, dict):
        _fail("UNSAFE_SUMMARY", "Sanitized summary is not an object")
    summary = validate_sanitized_summary_payload(summary_payload)
    if (
        summary.input_benchmark_fingerprint != expected_benchmark_fingerprint
        or summary.development_fingerprint != subset_fingerprint
        or summary.logical_fingerprint != subset_fingerprint
        or summary.schema_fingerprint != stage02_review_schema_fingerprint()
    ):
        _fail("UNSAFE_SUMMARY", "Sanitized summary identity differs")
    try:
        markdown = (output_directory / REVIEW_SUMMARY_MD_PATH).read_text(
            encoding="utf-8"
        )
    except (OSError, UnicodeError) as error:
        raise ReviewSubsetError(
            "UNSAFE_SUMMARY", "Sanitized summary Markdown is malformed"
        ) from error
    if markdown != render_summary_markdown(summary):
        _fail("UNSAFE_SUMMARY", "Sanitized Markdown is not canonical")
    protected = manifest.get("protected_aggregate_evidence")
    if not isinstance(protected, dict):
        _fail("REVIEW_MANIFEST_INVALID", "Review aggregate evidence is malformed")
    expected_protected_keys = {
        "development_only",
        "holdout_rows",
        "duplicate_selected_identity_count",
        "source_files_represented",
        "quota_shortfall_category_count",
        "quota_shortfall_total",
        "quota_diagnostics",
    }
    if set(protected) != expected_protected_keys:
        _fail("REVIEW_MANIFEST_INVALID", "Review aggregate evidence is malformed")
    raw_diagnostics = protected.get("quota_diagnostics")
    if (
        protected.get("development_only") is not True
        or protected.get("holdout_rows") != 0
        or protected.get("duplicate_selected_identity_count") != 0
        or not isinstance(raw_diagnostics, list)
    ):
        _fail("REVIEW_MANIFEST_INVALID", "Review aggregate evidence is malformed")
    diagnostic_shortfalls: list[int] = []
    for diagnostic in raw_diagnostics:
        if not isinstance(diagnostic, dict) or set(diagnostic) != {
            "dimension",
            "category",
            "available",
            "target",
            "achieved",
            "shortfall",
        }:
            _fail("REVIEW_MANIFEST_INVALID", "Review quota evidence is malformed")
        if not isinstance(diagnostic.get("dimension"), str) or not isinstance(
            diagnostic.get("category"), str
        ):
            _fail("REVIEW_MANIFEST_INVALID", "Review quota evidence is malformed")
        diagnostic_shortfalls.append(_required_manifest_uint(diagnostic, "shortfall"))
        for name in ("available", "target", "achieved"):
            _required_manifest_uint(diagnostic, name)
    expected_shortfall_categories = sum(value > 0 for value in diagnostic_shortfalls)
    expected_shortfall_total = sum(diagnostic_shortfalls)
    if (
        _required_manifest_uint(protected, "quota_shortfall_category_count")
        != expected_shortfall_categories
        or _required_manifest_uint(protected, "quota_shortfall_total")
        != expected_shortfall_total
    ):
        _fail("REVIEW_MANIFEST_INVALID", "Review quota totals are inconsistent")
    return DevelopmentReviewOutcome(
        output_directory=output_directory,
        review_subset_fingerprint=subset_fingerprint,
        review_artifact_sha256=artifacts[STAGE02_REVIEW_PATH].sha256,
        manifest_sha256=expected_manifest_sha256,
        selected_row_count=selected_rows,
        duplicate_identity_count=0,
        source_files_represented=_required_manifest_uint(
            protected, "source_files_represented"
        ),
        quota_shortfall_category_count=_required_manifest_uint(
            protected, "quota_shortfall_category_count"
        ),
        quota_shortfall_total=_required_manifest_uint(
            protected, "quota_shortfall_total"
        ),
    )


__all__ = [
    "DevelopmentReviewOutcome",
    "DevelopmentReviewRunConfig",
    "REVIEW_BUNDLE_MANIFEST_VERSION",
    "REVIEW_BUNDLE_VALIDATION_VERSION",
    "REVIEW_IDENTITIES_PATH",
    "REVIEW_MANIFEST_NAME",
    "REVIEW_SUCCESS_MARKER",
    "REVIEW_SUMMARY_JSON_PATH",
    "REVIEW_SUMMARY_MD_PATH",
    "REVIEW_VIEW_SCHEMA_VERSION",
    "STAGE02_REVIEW_PATH",
    "materialize_stage02_development_review",
    "stage02_review_schema",
    "stage02_review_schema_fingerprint",
    "validate_development_review_bundle",
]
