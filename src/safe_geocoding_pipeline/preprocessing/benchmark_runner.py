from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import stat
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

import pyarrow as pa
import pyarrow.parquet as pq

from ..execution_policy import require_goethe_nhr_slurm
from ..phase01.config import DEFAULT_PARSER_FIELD_LIMIT_CHARS, InventoryConfig
from ..phase01.discovery import discover_source_files
from ..phase01.models import FileMetadata, SourceFile
from ..phase01.parser import detect_bom, file_metadata, hash_file
from ..phase01.population import PopulationScope, load_population_scope
from ..phase02.identity import stable_source_row_id_v1
from ..phase03.references import ScriptReference, production_reference_paths
from ..raw_csv import (
    CSV_NEWLINE,
    SOURCE_COLUMNS,
    SOURCE_TEXT_ENCODING,
    SOURCE_TEXT_ENCODING_WITH_BOM,
    SOURCE_TEXT_ERRORS,
    csv_field_limit,
    strict_csv_reader,
)
from .benchmark_sample import (
    ALLOCATION_POLICY_VERSION,
    BENCHMARK_CONTRACT_VERSION,
    FEATURE_CONTRACT_VERSION,
    SELECTION_ALGORITHM_VERSION,
    BenchmarkCandidate,
    BenchmarkConfig,
    BenchmarkSelection,
    BenchmarkSourceProjection,
    BenchmarkValidationError,
    SamplingPolicy,
    benchmark_fingerprint_v1,
    benchmark_fingerprint_from_identities_v1,
    build_quota_targets,
    classify_sampling_features,
    development_coverage,
    finalize_selection,
    make_candidate_heaps,
    offer_candidate,
)
from .stages.s00_inventory import parser_contract_fingerprint_v1

BENCHMARK_OUTPUT_SCHEMA_VERSION = "benchmark_sample_parquet_schema_v1"
BENCHMARK_MANIFEST_VERSION = "benchmark_sample_manifest_v1"
BENCHMARK_VALIDATION_VERSION = "benchmark_sample_validation_v1"
UNICODE_SCRIPT_REFERENCE_ID = "unicode_ucd_16_0_0_scripts_20240430"
SUCCESS_MARKER = "_SUCCESS.json"
IN_PROGRESS_MARKER = "_IN_PROGRESS"
MANIFEST_NAME = "benchmark_manifest.json"
SUMMARY_JSON_NAME = "benchmark_summary.json"
SUMMARY_MD_NAME = "benchmark_summary.md"
DEVELOPMENT_RELATIVE_PATH = "development/development_view.parquet"
HOLDOUT_RELATIVE_PATH = "holdout/holdout.parquet"
HOLDOUT_POLICY_RELATIVE_PATH = "holdout/DO_NOT_USE_FOR_PIPELINE_TUNING.txt"

FEATURE_COLUMNS = (
    "benchmark_split",
    "benchmark_challenge_flag",
    "benchmark_challenge_reasons",
    "location_information_stratum",
    "batch_priority_stratum",
    "country_stratum",
    "standard_native_presence_class",
    "standard_native_equality_class",
    "standard_line_count",
    "native_line_count",
    "postcode_present",
    "city_present",
    "region_present",
    "country_present",
    "missingness_class",
    "standard_script_class",
    "native_script_class",
    "combined_script_class",
    "benchmark_feature_contract_version",
)
PROVENANCE_COLUMNS = (
    "source_file",
    "source_logical_record_number",
    "stable_source_row_id_v1",
    "source_file_sha256",
)
BENCHMARK_COLUMNS = SOURCE_COLUMNS + PROVENANCE_COLUMNS + FEATURE_COLUMNS

_SAFE_STATISTICS_COLUMNS = (
    "benchmark_split",
    "benchmark_challenge_flag",
    "location_information_stratum",
    "batch_priority_stratum",
    "country_stratum",
    "standard_native_presence_class",
    "standard_native_equality_class",
    "standard_line_count",
    "native_line_count",
    "postcode_present",
    "city_present",
    "region_present",
    "country_present",
    "missingness_class",
    "standard_script_class",
    "native_script_class",
    "combined_script_class",
    "benchmark_feature_contract_version",
)


@dataclass(frozen=True, slots=True)
class BenchmarkRunConfig:
    source_root: Path
    population_scope_file: Path
    expected_population_scope_sha256: str
    expected_source_count: int
    output_directory: Path
    adopting_git_commit: str
    benchmark_config: BenchmarkConfig = BenchmarkConfig()
    parser_field_limit_chars: int = DEFAULT_PARSER_FIELD_LIMIT_CHARS
    hash_chunk_bytes: int = 1024 * 1024
    output_batch_rows: int = 1_000
    production: bool = True
    operational_metadata: Mapping[str, str] | None = None

    def validate(self) -> None:
        self.benchmark_config.validate()
        if (
            isinstance(self.expected_source_count, bool)
            or self.expected_source_count < 1
        ):
            raise BenchmarkValidationError(
                "INVALID_SOURCE_COUNT", "Expected source count must be positive"
            )
        if self.parser_field_limit_chars != DEFAULT_PARSER_FIELD_LIMIT_CHARS:
            raise BenchmarkValidationError(
                "PARSER_CONTRACT_MISMATCH",
                "Benchmark requires the accepted Stage 0 parser ceiling",
            )
        if self.hash_chunk_bytes < 1 or self.output_batch_rows < 1:
            raise BenchmarkValidationError(
                "INVALID_OPERATIONAL_SETTING",
                "Batch and hash settings must be positive",
            )
        if len(self.adopting_git_commit) != 40 or any(
            character not in "0123456789abcdef"
            for character in self.adopting_git_commit
        ):
            raise BenchmarkValidationError(
                "INVALID_GIT_COMMIT", "Adopting Git commit must be a full lowercase SHA"
            )


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    source: SourceFile
    size_bytes: int
    mtime_ns: int
    sha256: str
    bom_type: str

    def projection(self, logical_record_count: int) -> BenchmarkSourceProjection:
        return BenchmarkSourceProjection(
            relative_path=self.source.relative_path,
            size_bytes=self.size_bytes,
            sha256=self.sha256,
            logical_record_count=logical_record_count,
        )


@dataclass(slots=True)
class PopulationProfile:
    counts: dict[str, Counter[str]]
    country_non_latin_counts: Counter[str]
    rows_per_file: dict[str, int]
    total_rows: int


@dataclass(frozen=True, slots=True)
class BenchmarkArtifactIdentity:
    relative_path: str
    size_bytes: int
    sha256: str

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BenchmarkMaterializationOutcome:
    output_directory: Path
    benchmark_fingerprint: str
    manifest_sha256: str
    source_file_count: int
    total_source_rows: int
    development_rows: int
    holdout_rows: int
    development_source_files_represented: int


def benchmark_schema() -> pa.Schema:
    fields = [pa.field(name, pa.string(), nullable=False) for name in SOURCE_COLUMNS]
    fields.extend(
        (
            pa.field("source_file", pa.string(), nullable=False),
            pa.field("source_logical_record_number", pa.uint64(), nullable=False),
            pa.field("stable_source_row_id_v1", pa.binary(32), nullable=False),
            pa.field("source_file_sha256", pa.binary(32), nullable=False),
            pa.field("benchmark_split", pa.string(), nullable=False),
            pa.field("benchmark_challenge_flag", pa.bool_(), nullable=False),
            pa.field("benchmark_challenge_reasons", pa.string(), nullable=False),
            pa.field("location_information_stratum", pa.string(), nullable=False),
            pa.field("batch_priority_stratum", pa.string(), nullable=False),
            pa.field("country_stratum", pa.string(), nullable=False),
            pa.field("standard_native_presence_class", pa.string(), nullable=False),
            pa.field("standard_native_equality_class", pa.string(), nullable=False),
            pa.field("standard_line_count", pa.uint8(), nullable=False),
            pa.field("native_line_count", pa.uint8(), nullable=False),
            pa.field("postcode_present", pa.bool_(), nullable=False),
            pa.field("city_present", pa.bool_(), nullable=False),
            pa.field("region_present", pa.bool_(), nullable=False),
            pa.field("country_present", pa.bool_(), nullable=False),
            pa.field("missingness_class", pa.string(), nullable=False),
            pa.field("standard_script_class", pa.string(), nullable=False),
            pa.field("native_script_class", pa.string(), nullable=False),
            pa.field("combined_script_class", pa.string(), nullable=False),
            pa.field("benchmark_feature_contract_version", pa.string(), nullable=False),
        )
    )
    schema = pa.schema(fields)
    if tuple(schema.names) != BENCHMARK_COLUMNS:
        raise AssertionError("internal benchmark schema order error")
    return schema


def benchmark_schema_fingerprint() -> str:
    digest = hashlib.sha256(b"SAFE_BENCHMARK_SAMPLE_PARQUET_SCHEMA_V1")
    for field in benchmark_schema():
        for value in (field.name, str(field.type), str(field.nullable)):
            encoded = value.encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_identity(root: Path, relative_path: str) -> BenchmarkArtifactIdentity:
    path = root / relative_path
    if path.is_symlink() or not path.is_file():
        raise BenchmarkValidationError(
            "UNSAFE_BENCHMARK_ARTIFACT", "Benchmark artifact is not a regular file"
        )
    observed = path.stat(follow_symlinks=False)
    if stat.S_IMODE(observed.st_mode) != 0o600:
        raise BenchmarkValidationError(
            "BENCHMARK_PERMISSION_FAILURE", "Benchmark artifact is not mode 0600"
        )
    return BenchmarkArtifactIdentity(
        relative_path, observed.st_size, _sha256_file(path)
    )


def _same_metadata(first: FileMetadata, second: FileMetadata) -> bool:
    return first.size_bytes == second.size_bytes and first.mtime_ns == second.mtime_ns


def _load_script_reference() -> ScriptReference:
    paths = production_reference_paths()
    reference = ScriptReference.from_artifact(
        paths["unicode_manifest"], paths["unicode_artifact"]
    )
    if reference.version != UNICODE_SCRIPT_REFERENCE_ID:
        raise BenchmarkValidationError(
            "SCRIPT_REFERENCE_MISMATCH",
            "Unicode Script reference is not the benchmark-pinned version",
        )
    return reference


def _load_scope_and_sources(
    config: BenchmarkRunConfig,
) -> tuple[PopulationScope, list[SourceFile]]:
    try:
        scope = load_population_scope(
            config.population_scope_file,
            expected_sha256=config.expected_population_scope_sha256,
            expected_parser_field_limit_chars=config.parser_field_limit_chars,
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise BenchmarkValidationError(
            "SOURCE_POPULATION_MISMATCH",
            "Authorized population scope could not be validated",
        ) from error
    if scope.expected_source_count != config.expected_source_count:
        raise BenchmarkValidationError(
            "SOURCE_POPULATION_MISMATCH",
            "Authorized scope count differs from the benchmark run",
        )
    inventory_config = InventoryConfig(source_root=config.source_root)
    try:
        sources = discover_source_files(
            inventory_config, authorized_relative_paths=scope.relative_paths
        )
    except (OSError, ValueError) as error:
        raise BenchmarkValidationError(
            "SOURCE_POPULATION_MISMATCH",
            "Source directory differs from the authorized benchmark scope",
        ) from error
    if len(sources) != config.expected_source_count:
        raise BenchmarkValidationError(
            "SOURCE_POPULATION_MISMATCH", "Source count differs from the benchmark run"
        )
    return scope, sources


def _hash_source_population(
    sources: Sequence[SourceFile], *, config: BenchmarkRunConfig
) -> tuple[SourceSnapshot, ...]:
    snapshots: list[SourceSnapshot] = []
    seen_hashes: set[str] = set()
    for source in sources:
        try:
            before = file_metadata(source.path)
            digest, _ = hash_file(source.path, config.hash_chunk_bytes)
            after = file_metadata(source.path)
            bom_type = detect_bom(source.path)
        except OSError as error:
            raise BenchmarkValidationError(
                "SOURCE_READ_FAILURE", "An authorized source could not be read safely"
            ) from error
        if not _same_metadata(before, after):
            raise BenchmarkValidationError(
                "SOURCE_CHANGED", "An authorized source changed during hashing"
            )
        if digest in seen_hashes:
            raise BenchmarkValidationError(
                "DUPLICATE_SOURCE_FILE",
                "Exact duplicate source content would collide stable row identities",
            )
        seen_hashes.add(digest)
        snapshots.append(
            SourceSnapshot(
                source=source,
                size_bytes=int(before.size_bytes or 0),
                mtime_ns=int(before.mtime_ns or 0),
                sha256=digest,
                bom_type=bom_type,
            )
        )
    return tuple(snapshots)


def _verify_population_unchanged(
    config: BenchmarkRunConfig,
    scope: PopulationScope,
    snapshots: Sequence[SourceSnapshot],
    *,
    rehash: bool,
) -> None:
    observed_scope, sources = _load_scope_and_sources(config)
    if observed_scope != scope:
        raise BenchmarkValidationError(
            "SOURCE_POPULATION_CHANGED", "Population scope changed during benchmark"
        )
    if tuple(source.relative_path for source in sources) != tuple(
        item.source.relative_path for item in snapshots
    ):
        raise BenchmarkValidationError(
            "SOURCE_POPULATION_CHANGED", "Source membership changed during benchmark"
        )
    for source, expected in zip(sources, snapshots, strict=True):
        try:
            observed = file_metadata(source.path)
        except OSError as error:
            raise BenchmarkValidationError(
                "SOURCE_POPULATION_CHANGED",
                "An authorized source became unreadable during benchmark",
            ) from error
        if (
            observed.size_bytes != expected.size_bytes
            or observed.mtime_ns != expected.mtime_ns
        ):
            raise BenchmarkValidationError(
                "SOURCE_POPULATION_CHANGED", "Source metadata changed during benchmark"
            )
        if rehash:
            try:
                digest, _ = hash_file(source.path, config.hash_chunk_bytes)
            except OSError as error:
                raise BenchmarkValidationError(
                    "SOURCE_POPULATION_CHANGED",
                    "An authorized source became unreadable during benchmark",
                ) from error
            if digest != expected.sha256:
                raise BenchmarkValidationError(
                    "SOURCE_POPULATION_CHANGED", "Source bytes changed during benchmark"
                )


def _iter_source_rows(
    snapshot: SourceSnapshot, *, parser_field_limit_chars: int
) -> Iterator[tuple[int, tuple[str, ...]]]:
    encoding = (
        SOURCE_TEXT_ENCODING_WITH_BOM
        if snapshot.bom_type == "UTF8"
        else SOURCE_TEXT_ENCODING
    )
    try:
        with csv_field_limit(parser_field_limit_chars):
            with snapshot.source.path.open(
                "r",
                encoding=encoding,
                errors=SOURCE_TEXT_ERRORS,
                newline=CSV_NEWLINE,
            ) as stream:
                reader = strict_csv_reader(stream)
                try:
                    header = next(reader)
                except StopIteration as error:
                    raise BenchmarkValidationError(
                        "EMPTY_SOURCE_FILE", "An authorized source has no header"
                    ) from error
                if tuple(header) != SOURCE_COLUMNS:
                    raise BenchmarkValidationError(
                        "SOURCE_SCHEMA_MISMATCH",
                        "An authorized source header differs from the accepted schema",
                    )
                for logical_record_number, row in enumerate(reader, start=1):
                    if len(row) != len(SOURCE_COLUMNS):
                        raise BenchmarkValidationError(
                            "WRONG_COLUMN_COUNT",
                            "An authorized logical record has the wrong width",
                        )
                    yield logical_record_number, tuple(row)
    except BenchmarkValidationError:
        raise
    except (OSError, UnicodeError, csv.Error) as error:
        raise BenchmarkValidationError(
            "STRICT_SOURCE_PARSE_FAILURE",
            "An authorized source failed strict CSV interpretation",
        ) from error


def _empty_profile() -> PopulationProfile:
    dimensions = (
        "source_file",
        "location_information",
        "batch_priority",
        "country",
        "standard_native_presence",
        "standard_native_equality",
        "standard_line_count",
        "native_line_count",
        "standard_script",
        "native_script",
        "combined_script",
        "missingness",
        "challenge_reason",
    )
    return PopulationProfile(
        counts={dimension: Counter() for dimension in dimensions},
        country_non_latin_counts=Counter(),
        rows_per_file={},
        total_rows=0,
    )


def _profile_population(
    snapshots: Sequence[SourceSnapshot],
    *,
    script_reference: ScriptReference,
    config: BenchmarkRunConfig,
) -> PopulationProfile:
    profile = _empty_profile()
    dimensions = tuple(profile.counts)
    for source_index, snapshot in enumerate(snapshots, start=1):
        rows = 0
        for _, values in _iter_source_rows(
            snapshot, parser_field_limit_chars=config.parser_field_limit_chars
        ):
            rows += 1
            row = dict(zip(SOURCE_COLUMNS, values, strict=True))
            features = classify_sampling_features(
                row, script_reference=script_reference
            )
            for dimension in dimensions:
                for category in features.categories_for(
                    dimension, snapshot.source.relative_path
                ):
                    profile.counts[dimension][category] += 1
            if features.combined_script_class in {
                "NON_LATIN_PRESENT",
                "MIXED_SCRIPT",
            }:
                profile.country_non_latin_counts[features.country_stratum] += 1
        profile.rows_per_file[snapshot.source.relative_path] = rows
        profile.total_rows += rows
        print(
            f"benchmark_profile_file_complete={source_index} rows={rows}",
            file=sys.stderr,
            flush=True,
        )
    return profile


def _select_population(
    snapshots: Sequence[SourceSnapshot],
    *,
    profile: PopulationProfile,
    script_reference: ScriptReference,
    config: BenchmarkRunConfig,
) -> BenchmarkSelection:
    targets = build_quota_targets(
        profile.counts,
        profile.country_non_latin_counts,
        policy=config.benchmark_config.policy,
    )
    quota_heaps, global_heap = make_candidate_heaps(
        targets, total_count=config.benchmark_config.total_count
    )
    for source_index, snapshot in enumerate(snapshots, start=1):
        rows = 0
        source_hash = bytes.fromhex(snapshot.sha256)
        for logical_record_number, values in _iter_source_rows(
            snapshot, parser_field_limit_chars=config.parser_field_limit_chars
        ):
            rows += 1
            row = dict(zip(SOURCE_COLUMNS, values, strict=True))
            candidate = BenchmarkCandidate(
                stable_source_row_id_v1=stable_source_row_id_v1(
                    source_hash, logical_record_number
                ),
                source_file=snapshot.source.relative_path,
                source_logical_record_number=logical_record_number,
                features=classify_sampling_features(
                    row, script_reference=script_reference
                ),
            )
            offer_candidate(candidate, quota_heaps=quota_heaps, global_heap=global_heap)
        if rows != profile.rows_per_file[snapshot.source.relative_path]:
            raise BenchmarkValidationError(
                "SOURCE_ROW_COUNT_CHANGED", "Source row count changed between passes"
            )
        print(
            f"benchmark_select_file_complete={source_index} rows={rows}",
            file=sys.stderr,
            flush=True,
        )
    return finalize_selection(
        targets=targets,
        counts=profile.counts,
        quota_heaps=quota_heaps,
        global_heap=global_heap,
        config=config.benchmark_config,
    )


def _row_payload(
    values: Sequence[str],
    *,
    snapshot: SourceSnapshot,
    candidate: BenchmarkCandidate,
    split: str,
) -> tuple[Any, ...]:
    features = candidate.features
    return tuple(values) + (
        snapshot.source.relative_path,
        candidate.source_logical_record_number,
        candidate.stable_source_row_id_v1,
        bytes.fromhex(snapshot.sha256),
        split,
        features.challenge_flag,
        "|".join(features.challenge_reasons),
        features.location_information_stratum,
        features.batch_priority_stratum,
        features.country_stratum,
        features.standard_native_presence_class,
        features.standard_native_equality_class,
        features.standard_line_count,
        features.native_line_count,
        features.postcode_present,
        features.city_present,
        features.region_present,
        features.country_present,
        features.missingness_class,
        features.standard_script_class,
        features.native_script_class,
        features.combined_script_class,
        FEATURE_CONTRACT_VERSION,
    )


class _BenchmarkWriter:
    def __init__(
        self, path: Path, *, metadata: Mapping[str, str], batch_rows: int
    ) -> None:
        self.path = path
        self.batch_rows = batch_rows
        schema = benchmark_schema().with_metadata(
            {
                key.encode("utf-8"): value.encode("utf-8")
                for key, value in metadata.items()
            }
        )
        self.schema = schema
        try:
            self.writer = pq.ParquetWriter(
                path,
                schema,
                version="1.0",
                data_page_version="1.0",
                compression="zstd",
                compression_level=3,
                use_dictionary=list(_SAFE_STATISTICS_COLUMNS),
                write_statistics=list(_SAFE_STATISTICS_COLUMNS),
                write_page_checksum=True,
                store_schema=True,
                use_compliant_nested_type=True,
            )
        except (OSError, pa.ArrowException) as error:
            raise BenchmarkValidationError(
                "PARQUET_WRITE_FAILURE", "Benchmark Parquet writer could not start"
            ) from error
        path.chmod(0o600)
        self.buffers: list[list[Any]] = [[] for _ in BENCHMARK_COLUMNS]
        self.buffered_rows = 0
        self.total_rows = 0

    def append(self, payload: tuple[Any, ...]) -> None:
        if len(payload) != len(self.buffers):
            raise AssertionError("internal benchmark row width error")
        for buffer, value in zip(self.buffers, payload, strict=True):
            buffer.append(value)
        self.buffered_rows += 1
        self.total_rows += 1
        if self.buffered_rows >= self.batch_rows:
            self.flush()

    def flush(self) -> None:
        if self.buffered_rows == 0:
            return
        try:
            arrays = [
                pa.array(values, type=field.type, from_pandas=False, safe=True)
                for field, values in zip(self.schema, self.buffers, strict=True)
            ]
        except (pa.ArrowException, OverflowError) as error:
            raise BenchmarkValidationError(
                "PARQUET_WRITE_FAILURE", "Benchmark row batch could not be encoded"
            ) from error
        if any(array.null_count for array in arrays):
            raise BenchmarkValidationError(
                "NULL_CREATION", "Benchmark materialization created a null"
            )
        batch = pa.RecordBatch.from_arrays(arrays, schema=self.schema)
        try:
            self.writer.write_batch(batch, row_group_size=self.buffered_rows)
        except (OSError, pa.ArrowException) as error:
            raise BenchmarkValidationError(
                "PARQUET_WRITE_FAILURE", "Benchmark row batch could not be written"
            ) from error
        self.buffers = [[] for _ in BENCHMARK_COLUMNS]
        self.buffered_rows = 0

    def close(self) -> None:
        self.flush()
        try:
            self.writer.close()
        except (OSError, pa.ArrowException) as error:
            raise BenchmarkValidationError(
                "PARQUET_WRITE_FAILURE", "Benchmark Parquet writer could not close"
            ) from error
        self.path.chmod(0o600)

    def abort(self) -> None:
        try:
            self.writer.close()
        except Exception:
            pass


def _materialize_selected_rows(
    snapshots: Sequence[SourceSnapshot],
    *,
    selection: BenchmarkSelection,
    script_reference: ScriptReference,
    config: BenchmarkRunConfig,
    output_root: Path,
    benchmark_fingerprint: str,
    expected_rows_per_file: Mapping[str, int],
) -> None:
    selected: dict[bytes, tuple[str, BenchmarkCandidate]] = {}
    for split, candidates in (
        ("DEVELOPMENT", selection.development),
        ("HOLDOUT", selection.holdout),
    ):
        for candidate in candidates:
            if candidate.stable_source_row_id_v1 in selected:
                raise BenchmarkValidationError(
                    "DUPLICATE_SELECTED_IDENTITY",
                    "Development and holdout identities overlap",
                )
            selected[candidate.stable_source_row_id_v1] = (split, candidate)
    metadata = {
        "benchmark_contract_version": BENCHMARK_CONTRACT_VERSION,
        "benchmark_feature_contract_version": FEATURE_CONTRACT_VERSION,
        "benchmark_fingerprint": benchmark_fingerprint,
        "benchmark_schema_version": BENCHMARK_OUTPUT_SCHEMA_VERSION,
        "unicode_script_reference": UNICODE_SCRIPT_REFERENCE_ID,
    }
    development_writer = _BenchmarkWriter(
        output_root / DEVELOPMENT_RELATIVE_PATH,
        metadata=metadata,
        batch_rows=config.output_batch_rows,
    )
    holdout_writer = _BenchmarkWriter(
        output_root / HOLDOUT_RELATIVE_PATH,
        metadata=metadata,
        batch_rows=config.output_batch_rows,
    )
    observed: set[bytes] = set()
    try:
        for source_index, snapshot in enumerate(snapshots, start=1):
            source_hash = bytes.fromhex(snapshot.sha256)
            rows = 0
            for logical_record_number, values in _iter_source_rows(
                snapshot, parser_field_limit_chars=config.parser_field_limit_chars
            ):
                rows += 1
                identity = stable_source_row_id_v1(source_hash, logical_record_number)
                selected_row = selected.get(identity)
                if selected_row is None:
                    continue
                split, candidate = selected_row
                row = dict(zip(SOURCE_COLUMNS, values, strict=True))
                observed_features = classify_sampling_features(
                    row, script_reference=script_reference
                )
                if observed_features != candidate.features:
                    raise BenchmarkValidationError(
                        "SAMPLING_FEATURE_CHANGED",
                        "Sampling features changed between selection and materialization",
                    )
                payload = _row_payload(
                    values,
                    snapshot=snapshot,
                    candidate=candidate,
                    split=split,
                )
                if split == "DEVELOPMENT":
                    development_writer.append(payload)
                else:
                    holdout_writer.append(payload)
                observed.add(identity)
            if rows != expected_rows_per_file[snapshot.source.relative_path]:
                raise BenchmarkValidationError(
                    "SOURCE_ROW_COUNT_CHANGED",
                    "Source row count changed during materialization",
                )
            print(
                f"benchmark_materialize_file_complete={source_index} rows={rows}",
                file=sys.stderr,
                flush=True,
            )
        development_writer.close()
        holdout_writer.close()
    except BaseException:
        development_writer.abort()
        holdout_writer.abort()
        raise
    if observed != set(selected):
        raise BenchmarkValidationError(
            "SELECTED_ROW_MISSING",
            "One or more selected identities were not materialized",
        )
    if development_writer.total_rows != config.benchmark_config.development_count:
        raise BenchmarkValidationError(
            "DEVELOPMENT_COUNT_MISMATCH", "Development output count is not exact"
        )
    if holdout_writer.total_rows != config.benchmark_config.holdout_count:
        raise BenchmarkValidationError(
            "HOLDOUT_COUNT_MISMATCH", "Holdout output count is not exact"
        )


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _write_text(path: Path, value: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def _quota_summary(selection: BenchmarkSelection) -> dict[str, dict[str, int]]:
    dimensions: dict[str, dict[str, int]] = {}
    for item in selection.quota_diagnostics:
        row = dimensions.setdefault(
            item.dimension,
            {
                "group_count": 0,
                "target_total": 0,
                "achieved_total": 0,
                "shortfall_group_count": 0,
                "shortfall_total": 0,
            },
        )
        row["group_count"] += 1
        row["target_total"] += item.target
        row["achieved_total"] += item.achieved
        row["shortfall_group_count"] += item.shortfall > 0
        row["shortfall_total"] += item.shortfall
    return dimensions


def _render_summary_markdown(summary: Mapping[str, Any]) -> str:
    development = summary["development_coverage"]
    assert isinstance(development, dict)
    return f"""# Benchmark Sample V1 — sanitized summary

Status: `{summary["status"]}`

This report contains aggregate DEVELOPMENT coverage only. HOLDOUT raw values,
identities, and split-specific structural distributions are intentionally absent.

## Population and sample

- Authorized source files: {summary["source_file_count"]}
- Source logical rows: {summary["total_source_rows"]}
- DEVELOPMENT rows: {summary["development_rows"]}
- HOLDOUT rows: {summary["holdout_rows"]}
- Sample source files represented: {summary["sample_source_files_represented"]}
- DEVELOPMENT source files represented: {development["source_files_represented"]}
- DEVELOPMENT challenge rows: {development["challenge_rows"]}

## Integrity

- Development/holdout overlap: 0
- Duplicate selected identities: 0
- Source transformation: none
- HOLDOUT tuning access: prohibited

The machine-readable summary contains sanitized DEVELOPMENT category counts.
"""


def _selected_identity_rows(
    selection: BenchmarkSelection,
) -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    for split, candidates in (
        ("DEVELOPMENT", selection.development),
        ("HOLDOUT", selection.holdout),
    ):
        for candidate in sorted(
            candidates, key=lambda item: item.stable_source_row_id_v1
        ):
            rows.append(
                {
                    "benchmark_split": split,
                    "stable_source_row_id_v1": candidate.stable_source_row_id_v1.hex(),
                    "source_file": candidate.source_file,
                    "source_logical_record_number": (
                        candidate.source_logical_record_number
                    ),
                }
            )
    return rows


def _validate_parquet_output(
    path: Path,
    *,
    expected_split: str,
    expected_ids: set[bytes],
    expected_fingerprint: str,
) -> None:
    try:
        parquet = pq.ParquetFile(path, page_checksum_verification=True, pre_buffer=True)
    except (OSError, pa.ArrowException) as error:
        raise BenchmarkValidationError(
            "PARQUET_READBACK_FAILURE", "Benchmark Parquet could not be opened safely"
        ) from error
    if not parquet.schema_arrow.remove_metadata().equals(
        benchmark_schema(), check_metadata=False
    ):
        raise BenchmarkValidationError(
            "BENCHMARK_SCHEMA_MISMATCH", "Benchmark Parquet schema is not exact"
        )
    metadata = parquet.schema_arrow.metadata or {}
    if metadata.get(b"benchmark_fingerprint") != expected_fingerprint.encode():
        raise BenchmarkValidationError(
            "BENCHMARK_METADATA_MISMATCH", "Benchmark Parquet identity is inconsistent"
        )
    observed: set[bytes] = set()
    rows = 0
    try:
        for batch in parquet.iter_batches(
            batch_size=10_000,
            columns=["stable_source_row_id_v1", "benchmark_split"],
            use_threads=False,
        ):
            identities = batch.column(0).to_pylist()
            splits = batch.column(1).to_pylist()
            rows += batch.num_rows
            if any(value != expected_split for value in splits):
                raise BenchmarkValidationError(
                    "BENCHMARK_SPLIT_MISMATCH",
                    "Benchmark split column is inconsistent",
                )
            for identity in identities:
                if identity in observed:
                    raise BenchmarkValidationError(
                        "DUPLICATE_SELECTED_IDENTITY",
                        "Benchmark Parquet contains a duplicate identity",
                    )
                observed.add(identity)
    except BenchmarkValidationError:
        raise
    except (OSError, pa.ArrowException) as error:
        raise BenchmarkValidationError(
            "PARQUET_READBACK_FAILURE",
            "Benchmark Parquet page-checksum readback failed",
        ) from error
    if rows != len(expected_ids) or observed != expected_ids:
        raise BenchmarkValidationError(
            "BENCHMARK_IDENTITY_MISMATCH",
            "Benchmark Parquet identities do not match the sealed selection",
        )


def materialize_benchmark_sample(
    config: BenchmarkRunConfig,
) -> BenchmarkMaterializationOutcome:
    """Materialize the fixed benchmark; production always requires Goethe SLURM."""
    config.validate()
    if config.production:
        require_goethe_nhr_slurm("benchmark-sample-v1.materialize")
    if config.output_directory.exists():
        raise BenchmarkValidationError(
            "OUTPUT_COLLISION", "Benchmark output directory already exists"
        )
    scope, sources = _load_scope_and_sources(config)
    script_reference = _load_script_reference()
    snapshots = _hash_source_population(sources, config=config)
    _verify_population_unchanged(config, scope, snapshots, rehash=False)
    profile = _profile_population(
        snapshots, script_reference=script_reference, config=config
    )
    if profile.total_rows < config.benchmark_config.total_count:
        raise BenchmarkValidationError(
            "INSUFFICIENT_SAMPLE_POPULATION",
            "Source population is smaller than the benchmark target",
        )
    _verify_population_unchanged(config, scope, snapshots, rehash=False)
    selection = _select_population(
        snapshots,
        profile=profile,
        script_reference=script_reference,
        config=config,
    )
    projections = tuple(
        snapshot.projection(profile.rows_per_file[snapshot.source.relative_path])
        for snapshot in snapshots
    )
    parser_fingerprint = parser_contract_fingerprint_v1(
        parser_field_limit_chars=config.parser_field_limit_chars
    )
    fingerprint = benchmark_fingerprint_v1(
        population_scope_version=scope.population_scope_version,
        population_id=scope.population_id,
        population_scope_sha256=scope.artifact_sha256,
        parser_contract_fingerprint=parser_fingerprint,
        unicode_script_reference_id=UNICODE_SCRIPT_REFERENCE_ID,
        sources=projections,
        selection=selection,
        config=config.benchmark_config,
    )

    output_parent = config.output_directory.parent
    output_parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_parent.chmod(0o700)
    temporary = output_parent / (
        f".{config.output_directory.name}.{os.getpid()}.in_progress"
    )
    if temporary.exists():
        raise BenchmarkValidationError(
            "OUTPUT_COLLISION", "Benchmark temporary directory already exists"
        )
    temporary.mkdir(mode=0o700)
    (temporary / "development").mkdir(mode=0o700)
    (temporary / "holdout").mkdir(mode=0o700)
    _write_text(
        temporary / IN_PROGRESS_MARKER,
        "BENCHMARK_SAMPLE_V1 materialization is incomplete.\n",
    )
    _write_text(
        temporary / HOLDOUT_POLICY_RELATIVE_PATH,
        "DO NOT USE HOLDOUT FOR PIPELINE TUNING. Explicit final-evaluation authorization is required.\n",
    )
    _materialize_selected_rows(
        snapshots,
        selection=selection,
        script_reference=script_reference,
        config=config,
        output_root=temporary,
        benchmark_fingerprint=fingerprint,
        expected_rows_per_file=profile.rows_per_file,
    )
    _verify_population_unchanged(config, scope, snapshots, rehash=True)

    development_ids = {item.stable_source_row_id_v1 for item in selection.development}
    holdout_ids = {item.stable_source_row_id_v1 for item in selection.holdout}
    if development_ids & holdout_ids:
        raise BenchmarkValidationError(
            "BENCHMARK_SPLIT_OVERLAP", "Development and holdout overlap"
        )
    _validate_parquet_output(
        temporary / DEVELOPMENT_RELATIVE_PATH,
        expected_split="DEVELOPMENT",
        expected_ids=development_ids,
        expected_fingerprint=fingerprint,
    )
    _validate_parquet_output(
        temporary / HOLDOUT_RELATIVE_PATH,
        expected_split="HOLDOUT",
        expected_ids=holdout_ids,
        expected_fingerprint=fingerprint,
    )
    coverage = development_coverage(selection.development)
    sample_source_files_represented = len(
        {candidate.source_file for candidate in selection.all_candidates}
    )
    summary: dict[str, Any] = {
        "summary_contract_version": "benchmark_sanitized_summary_v1",
        "status": "BENCHMARK_SAMPLE_V1_ACCEPTED",
        "benchmark_contract_version": BENCHMARK_CONTRACT_VERSION,
        "benchmark_fingerprint": fingerprint,
        "sampling_population_id": scope.population_id,
        "source_file_count": len(snapshots),
        "total_source_rows": profile.total_rows,
        "development_rows": len(selection.development),
        "holdout_rows": len(selection.holdout),
        "overlap_count": 0,
        "duplicate_selected_identity_count": 0,
        "sample_source_files_represented": sample_source_files_represented,
        "development_coverage": coverage,
        "quota_summary": _quota_summary(selection),
        "holdout_reporting_policy": (
            "COUNT_AND_INTEGRITY_ONLY_NO_SPLIT_SPECIFIC_STRUCTURAL_COUNTS"
        ),
    }
    _write_json(temporary / SUMMARY_JSON_NAME, summary)
    _write_text(temporary / SUMMARY_MD_NAME, _render_summary_markdown(summary))

    artifacts = tuple(
        _artifact_identity(temporary, relative_path)
        for relative_path in (
            DEVELOPMENT_RELATIVE_PATH,
            HOLDOUT_RELATIVE_PATH,
            HOLDOUT_POLICY_RELATIVE_PATH,
            SUMMARY_JSON_NAME,
            SUMMARY_MD_NAME,
        )
    )
    manifest: dict[str, Any] = {
        "benchmark_manifest_version": BENCHMARK_MANIFEST_VERSION,
        "status": "BENCHMARK_SAMPLE_V1_ACCEPTED",
        "scientific_identity": {
            "benchmark_contract_version": BENCHMARK_CONTRACT_VERSION,
            "feature_contract_version": FEATURE_CONTRACT_VERSION,
            "selection_algorithm_version": SELECTION_ALGORITHM_VERSION,
            "allocation_policy_version": ALLOCATION_POLICY_VERSION,
            "benchmark_fingerprint": fingerprint,
            "parser_contract_fingerprint": parser_fingerprint,
            "unicode_script_reference": UNICODE_SCRIPT_REFERENCE_ID,
            "population_scope_version": scope.population_scope_version,
            "population_id": scope.population_id,
            "population_scope_sha256": scope.artifact_sha256,
            "source_file_count": len(snapshots),
            "total_source_rows": profile.total_rows,
            "development_count": len(selection.development),
            "holdout_count": len(selection.holdout),
            "parquet_schema_version": BENCHMARK_OUTPUT_SCHEMA_VERSION,
            "parquet_schema_fingerprint": benchmark_schema_fingerprint(),
            "sampling_policy": config.benchmark_config.policy.to_dict(),
            "source_projection": [asdict(item) for item in projections],
            "selected_source_rows": _selected_identity_rows(selection),
        },
        "physical_identity": {
            "artifacts": [item.to_dict() for item in artifacts],
            "parquet_page_checksums_verified": True,
            "owner_only_permissions": True,
        },
        "validation": {
            "validation_contract_version": BENCHMARK_VALIDATION_VERSION,
            "source_population_stable": "PASS",
            "strict_csv_schema_and_counts": "PASS",
            "exact_sample_counts": "PASS",
            "development_holdout_disjoint": "PASS",
            "selected_identity_uniqueness": "PASS",
            "parquet_readback": "PASS",
            "privacy_safe_summary": "PASS",
            "holdout_isolation": "PASS",
        },
        "operational_provenance": {
            "adopting_git_commit": config.adopting_git_commit,
            "created_at_utc": _utc_now(),
            "python_version": platform.python_version(),
            "pyarrow_version": pa.__version__,
            **dict(config.operational_metadata or {}),
        },
    }
    _write_json(temporary / MANIFEST_NAME, manifest)
    manifest_identity = _artifact_identity(temporary, MANIFEST_NAME)
    success = {
        "status": "BENCHMARK_SAMPLE_V1_ACCEPTED",
        "benchmark_manifest_sha256": manifest_identity.sha256,
        "benchmark_manifest_size_bytes": manifest_identity.size_bytes,
        "benchmark_fingerprint": fingerprint,
        "development_count": len(selection.development),
        "holdout_count": len(selection.holdout),
    }
    _write_json(temporary / SUCCESS_MARKER, success)
    (temporary / IN_PROGRESS_MARKER).unlink()
    directory_fd = os.open(temporary, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    os.replace(temporary, config.output_directory)
    parent_fd = os.open(output_parent, os.O_RDONLY)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
    validate_materialized_benchmark(config.output_directory)
    represented_files = coverage["source_files_represented"]
    if not isinstance(represented_files, int):
        raise AssertionError("internal development coverage type error")
    return BenchmarkMaterializationOutcome(
        output_directory=config.output_directory,
        benchmark_fingerprint=fingerprint,
        manifest_sha256=manifest_identity.sha256,
        source_file_count=len(snapshots),
        total_source_rows=profile.total_rows,
        development_rows=len(selection.development),
        holdout_rows=len(selection.holdout),
        development_source_files_represented=represented_files,
    )


def _validate_scientific_identity(
    manifest: Mapping[str, Any], success: Mapping[str, Any]
) -> tuple[set[bytes], set[bytes], str]:
    scientific = manifest.get("scientific_identity")
    if not isinstance(scientific, dict):
        raise BenchmarkValidationError(
            "BENCHMARK_MANIFEST_INVALID", "Benchmark scientific identity is missing"
        )
    expected_versions = {
        "benchmark_contract_version": BENCHMARK_CONTRACT_VERSION,
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
        "selection_algorithm_version": SELECTION_ALGORITHM_VERSION,
        "allocation_policy_version": ALLOCATION_POLICY_VERSION,
        "unicode_script_reference": UNICODE_SCRIPT_REFERENCE_ID,
        "parquet_schema_version": BENCHMARK_OUTPUT_SCHEMA_VERSION,
        "parquet_schema_fingerprint": benchmark_schema_fingerprint(),
    }
    if any(scientific.get(key) != value for key, value in expected_versions.items()):
        raise BenchmarkValidationError(
            "BENCHMARK_CONTRACT_MISMATCH", "Benchmark scientific contract is unknown"
        )
    policy_payload = scientific.get("sampling_policy")
    default_policy_keys = set(SamplingPolicy().to_dict())
    if (
        not isinstance(policy_payload, dict)
        or set(policy_payload) != default_policy_keys
    ):
        raise BenchmarkValidationError(
            "BENCHMARK_MANIFEST_INVALID", "Sampling policy is malformed"
        )
    if policy_payload.get("allocation_policy_version") != ALLOCATION_POLICY_VERSION:
        raise BenchmarkValidationError(
            "BENCHMARK_CONTRACT_MISMATCH", "Allocation policy version is unknown"
        )
    policy_values: dict[str, int] = {}
    for key, value in policy_payload.items():
        if key == "allocation_policy_version":
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            raise BenchmarkValidationError(
                "BENCHMARK_MANIFEST_INVALID", "Sampling policy value is malformed"
            )
        policy_values[key] = value
    try:
        benchmark_config = BenchmarkConfig(
            development_count=scientific["development_count"],
            holdout_count=scientific["holdout_count"],
            policy=SamplingPolicy(**policy_values),
        )
        benchmark_config.validate()
    except (KeyError, TypeError, BenchmarkValidationError) as error:
        raise BenchmarkValidationError(
            "BENCHMARK_MANIFEST_INVALID", "Benchmark sample configuration is malformed"
        ) from error
    if (
        success.get("development_count") != benchmark_config.development_count
        or success.get("holdout_count") != benchmark_config.holdout_count
    ):
        raise BenchmarkValidationError(
            "BENCHMARK_TERMINAL_MISMATCH", "Terminal sample counts are inconsistent"
        )

    source_payload = scientific.get("source_projection")
    if not isinstance(source_payload, list):
        raise BenchmarkValidationError(
            "BENCHMARK_MANIFEST_INVALID", "Source projection is missing"
        )
    projections: list[BenchmarkSourceProjection] = []
    sources_by_path: dict[str, BenchmarkSourceProjection] = {}
    for row in source_payload:
        if not isinstance(row, dict) or set(row) != {
            "relative_path",
            "size_bytes",
            "sha256",
            "logical_record_count",
        }:
            raise BenchmarkValidationError(
                "BENCHMARK_MANIFEST_INVALID", "Source projection row is malformed"
            )
        relative_path = row["relative_path"]
        size_bytes = row["size_bytes"]
        sha256 = row["sha256"]
        logical_record_count = row["logical_record_count"]
        if (
            not isinstance(relative_path, str)
            or relative_path == ""
            or relative_path.startswith("/")
            or "\x00" in relative_path
            or any(part in {"", ".", ".."} for part in relative_path.split("/"))
            or isinstance(size_bytes, bool)
            or not isinstance(size_bytes, int)
            or size_bytes < 0
            or not isinstance(sha256, str)
            or len(sha256) != 64
            or isinstance(logical_record_count, bool)
            or not isinstance(logical_record_count, int)
            or logical_record_count < 0
        ):
            raise BenchmarkValidationError(
                "BENCHMARK_MANIFEST_INVALID", "Source projection row is invalid"
            )
        try:
            canonical_sha = bytes.fromhex(sha256).hex()
        except ValueError as error:
            raise BenchmarkValidationError(
                "BENCHMARK_MANIFEST_INVALID", "Source projection digest is invalid"
            ) from error
        if canonical_sha != sha256 or relative_path in sources_by_path:
            raise BenchmarkValidationError(
                "BENCHMARK_MANIFEST_INVALID", "Source projection is non-canonical"
            )
        projection = BenchmarkSourceProjection(
            relative_path, size_bytes, sha256, logical_record_count
        )
        projections.append(projection)
        sources_by_path[relative_path] = projection
    source_file_count = scientific.get("source_file_count")
    total_source_rows = scientific.get("total_source_rows")
    if (
        source_file_count != len(projections)
        or total_source_rows != sum(row.logical_record_count for row in projections)
        or [row.relative_path for row in projections]
        != sorted(sources_by_path, key=lambda value: value.encode("utf-8"))
    ):
        raise BenchmarkValidationError(
            "BENCHMARK_MANIFEST_INVALID",
            "Source projection totals or order are invalid",
        )

    selected = scientific.get("selected_source_rows")
    if not isinstance(selected, list):
        raise BenchmarkValidationError(
            "BENCHMARK_MANIFEST_INVALID", "Selected identity seal is missing"
        )
    development_ids: set[bytes] = set()
    holdout_ids: set[bytes] = set()
    for row in selected:
        if not isinstance(row, dict) or set(row) != {
            "benchmark_split",
            "stable_source_row_id_v1",
            "source_file",
            "source_logical_record_number",
        }:
            raise BenchmarkValidationError(
                "BENCHMARK_MANIFEST_INVALID", "Selected identity row is malformed"
            )
        identity_text = row["stable_source_row_id_v1"]
        split = row["benchmark_split"]
        source_file = row["source_file"]
        ordinal = row["source_logical_record_number"]
        source = (
            sources_by_path.get(source_file) if isinstance(source_file, str) else None
        )
        if (
            not isinstance(identity_text, str)
            or len(identity_text) != 64
            or split not in {"DEVELOPMENT", "HOLDOUT"}
            or source is None
            or isinstance(ordinal, bool)
            or not isinstance(ordinal, int)
            or not 1 <= ordinal <= source.logical_record_count
        ):
            raise BenchmarkValidationError(
                "BENCHMARK_MANIFEST_INVALID", "Selected identity row is invalid"
            )
        try:
            identity = bytes.fromhex(identity_text)
        except ValueError as error:
            raise BenchmarkValidationError(
                "BENCHMARK_MANIFEST_INVALID", "Selected identity digest is invalid"
            ) from error
        expected_identity = stable_source_row_id_v1(
            bytes.fromhex(source.sha256), ordinal
        )
        if identity.hex() != identity_text or identity != expected_identity:
            raise BenchmarkValidationError(
                "BENCHMARK_IDENTITY_MISMATCH",
                "Selected identity does not match immutable source provenance",
            )
        if identity in development_ids or identity in holdout_ids:
            raise BenchmarkValidationError(
                "DUPLICATE_SELECTED_IDENTITY", "Selected identity is duplicated"
            )
        (development_ids if split == "DEVELOPMENT" else holdout_ids).add(identity)
    if (
        len(development_ids) != benchmark_config.development_count
        or len(holdout_ids) != benchmark_config.holdout_count
        or development_ids & holdout_ids
    ):
        raise BenchmarkValidationError(
            "BENCHMARK_SPLIT_MISMATCH", "Benchmark split identity sets are inconsistent"
        )

    required_text = (
        "population_scope_version",
        "population_id",
        "population_scope_sha256",
        "parser_contract_fingerprint",
        "benchmark_fingerprint",
    )
    if any(not isinstance(scientific.get(key), str) for key in required_text):
        raise BenchmarkValidationError(
            "BENCHMARK_MANIFEST_INVALID", "Scientific identity field is malformed"
        )
    fingerprint = benchmark_fingerprint_from_identities_v1(
        population_scope_version=scientific["population_scope_version"],
        population_id=scientific["population_id"],
        population_scope_sha256=scientific["population_scope_sha256"],
        parser_contract_fingerprint=scientific["parser_contract_fingerprint"],
        unicode_script_reference_id=scientific["unicode_script_reference"],
        sources=projections,
        development_identities=tuple(development_ids),
        holdout_identities=tuple(holdout_ids),
        config=benchmark_config,
    )
    if (
        scientific["benchmark_fingerprint"] != fingerprint
        or success.get("benchmark_fingerprint") != fingerprint
    ):
        raise BenchmarkValidationError(
            "BENCHMARK_FINGERPRINT_MISMATCH",
            "Benchmark scientific fingerprint does not reproduce",
        )
    return development_ids, holdout_ids, fingerprint


def validate_materialized_benchmark(output_directory: Path) -> None:
    """Validate terminal state, permissions, hashes, and Parquet checksums."""
    if output_directory.is_symlink() or not output_directory.is_dir():
        raise BenchmarkValidationError(
            "BENCHMARK_OUTPUT_INVALID", "Benchmark output is not a regular directory"
        )
    if (output_directory / IN_PROGRESS_MARKER).exists():
        raise BenchmarkValidationError(
            "BENCHMARK_INCOMPLETE", "Benchmark retains an in-progress marker"
        )
    for directory in (
        output_directory,
        output_directory / "development",
        output_directory / "holdout",
    ):
        if directory.is_symlink() or not directory.is_dir():
            raise BenchmarkValidationError(
                "BENCHMARK_OUTPUT_INVALID", "Benchmark directory topology is unsafe"
            )
        if stat.S_IMODE(directory.stat(follow_symlinks=False).st_mode) != 0o700:
            raise BenchmarkValidationError(
                "BENCHMARK_PERMISSION_FAILURE", "Benchmark directory is not mode 0700"
            )
    expected_files = {
        MANIFEST_NAME,
        SUCCESS_MARKER,
        DEVELOPMENT_RELATIVE_PATH,
        HOLDOUT_RELATIVE_PATH,
        HOLDOUT_POLICY_RELATIVE_PATH,
        SUMMARY_JSON_NAME,
        SUMMARY_MD_NAME,
    }
    observed_files: set[str] = set()
    observed_directories: set[str] = set()
    for current_root, directory_names, file_names in os.walk(
        output_directory, followlinks=False
    ):
        current = Path(current_root)
        for directory_name in directory_names:
            directory = current / directory_name
            if directory.is_symlink():
                raise BenchmarkValidationError(
                    "BENCHMARK_OUTPUT_INVALID",
                    "Benchmark output contains a symlinked directory",
                )
            observed_directories.add(directory.relative_to(output_directory).as_posix())
        for file_name in file_names:
            file_path = current / file_name
            if file_path.is_symlink() or not file_path.is_file():
                raise BenchmarkValidationError(
                    "BENCHMARK_OUTPUT_INVALID",
                    "Benchmark output contains an unsafe file",
                )
            observed_files.add(file_path.relative_to(output_directory).as_posix())
    if (
        observed_directories != {"development", "holdout"}
        or observed_files != expected_files
    ):
        raise BenchmarkValidationError(
            "BENCHMARK_ARTIFACT_MISMATCH",
            "Benchmark output contains a missing or unexpected artifact",
        )
    manifest_path = output_directory / MANIFEST_NAME
    success_path = output_directory / SUCCESS_MARKER
    for path in (manifest_path, success_path):
        if path.is_symlink() or not path.is_file():
            raise BenchmarkValidationError(
                "BENCHMARK_INCOMPLETE", "Benchmark terminal artifact is missing"
            )
        if stat.S_IMODE(path.stat(follow_symlinks=False).st_mode) != 0o600:
            raise BenchmarkValidationError(
                "BENCHMARK_PERMISSION_FAILURE", "Benchmark file is not mode 0600"
            )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        success = json.loads(success_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BenchmarkValidationError(
            "BENCHMARK_MANIFEST_INVALID", "Benchmark terminal JSON is invalid"
        ) from error
    manifest_hash = _sha256_file(manifest_path)
    if (
        not isinstance(manifest, dict)
        or not isinstance(success, dict)
        or manifest.get("status") != "BENCHMARK_SAMPLE_V1_ACCEPTED"
        or success.get("status") != "BENCHMARK_SAMPLE_V1_ACCEPTED"
        or success.get("benchmark_manifest_sha256") != manifest_hash
        or success.get("benchmark_manifest_size_bytes") != manifest_path.stat().st_size
    ):
        raise BenchmarkValidationError(
            "BENCHMARK_TERMINAL_MISMATCH", "Benchmark terminal state is inconsistent"
        )
    physical = manifest.get("physical_identity")
    if not isinstance(physical, dict) or not isinstance(
        physical.get("artifacts"), list
    ):
        raise BenchmarkValidationError(
            "BENCHMARK_MANIFEST_INVALID", "Benchmark physical identity is incomplete"
        )
    expected_artifacts = {
        DEVELOPMENT_RELATIVE_PATH,
        HOLDOUT_RELATIVE_PATH,
        HOLDOUT_POLICY_RELATIVE_PATH,
        SUMMARY_JSON_NAME,
        SUMMARY_MD_NAME,
    }
    observed_artifacts: set[str] = set()
    for value in physical["artifacts"]:
        if not isinstance(value, dict):
            raise BenchmarkValidationError(
                "BENCHMARK_MANIFEST_INVALID", "Artifact identity is malformed"
            )
        relative_path = value.get("relative_path")
        if not isinstance(relative_path, str) or relative_path in observed_artifacts:
            raise BenchmarkValidationError(
                "BENCHMARK_MANIFEST_INVALID", "Artifact path is invalid or duplicated"
            )
        observed_artifacts.add(relative_path)
        observed = _artifact_identity(output_directory, relative_path)
        if value != observed.to_dict():
            raise BenchmarkValidationError(
                "BENCHMARK_ARTIFACT_MISMATCH", "Benchmark artifact identity changed"
            )
    if observed_artifacts != expected_artifacts:
        raise BenchmarkValidationError(
            "BENCHMARK_ARTIFACT_MISMATCH", "Benchmark artifact set is incomplete"
        )
    development_ids, holdout_ids, fingerprint = _validate_scientific_identity(
        manifest, success
    )
    _validate_parquet_output(
        output_directory / DEVELOPMENT_RELATIVE_PATH,
        expected_split="DEVELOPMENT",
        expected_ids=development_ids,
        expected_fingerprint=fingerprint,
    )
    _validate_parquet_output(
        output_directory / HOLDOUT_RELATIVE_PATH,
        expected_split="HOLDOUT",
        expected_ids=holdout_ids,
        expected_fingerprint=fingerprint,
    )


__all__ = [
    "BENCHMARK_COLUMNS",
    "BENCHMARK_MANIFEST_VERSION",
    "BENCHMARK_OUTPUT_SCHEMA_VERSION",
    "BENCHMARK_VALIDATION_VERSION",
    "DEVELOPMENT_RELATIVE_PATH",
    "HOLDOUT_RELATIVE_PATH",
    "MANIFEST_NAME",
    "SUCCESS_MARKER",
    "SUMMARY_JSON_NAME",
    "BenchmarkMaterializationOutcome",
    "BenchmarkRunConfig",
    "benchmark_schema",
    "benchmark_schema_fingerprint",
    "materialize_benchmark_sample",
    "validate_materialized_benchmark",
]
