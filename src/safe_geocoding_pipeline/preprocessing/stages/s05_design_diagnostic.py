from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import stat
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, NoReturn, cast

import pyarrow as pa
import pyarrow.parquet as pq

from ...execution_policy import require_goethe_nhr_slurm
from .s02_harmonization import NATIVE_ADDRESS_COLUMNS, STANDARD_ADDRESS_COLUMNS
from .s04_lowercase import (
    LOWER_OUTPUT_COLUMNS,
    STAGE04_MANIFEST_NAME,
    stage04_schema,
    validate_stage04_bundle,
)

STAGE05_DESIGN_DIAGNOSTIC_VERSION = "stage05_design_diagnostic_v1"
STAGE05_DESIGN_SEPARATOR = ", "
STAGE05_DESIGN_DIAGNOSTIC_NAME = "stage05_design_diagnostic.json"
STAGE05_DESIGN_SUCCESS_NAME = "_SUCCESS.json"

ACCEPTED_STAGE04_CONTRACT_VERSION = "stage04_lowercase_canonical_contract_v1"
ACCEPTED_STAGE04_PROFILE_VERSION = "stage04_lowercase_canonical_profile_v1"
ACCEPTED_STAGE04_SCHEMA_FINGERPRINT = (
    "dafb4f78b8bfce3120b6f4f7ae8cb44883f4c3a9cfd94b3137871b83c0ed5cbc"
)
ACCEPTED_STAGE04_LOGICAL_FINGERPRINT = (
    "054c66701f854a0108938170e1cb9bcee8a772f7fed29b82cda53c71aa9747ec"
)
ACCEPTED_STAGE04_INPUT_BINDING_SHA256 = (
    "90e0e94d4359bd5927820dfc06b2cfc1dc37485c032d95726d1260ec88a534b0"
)
ACCEPTED_STAGE04_MANIFEST_SHA256 = (
    "17a4854cddd8929b65ea79402f1a4f12a1574b720c1921567b577f23e152d1f3"
)
ACCEPTED_BENCHMARK_FINGERPRINT = (
    "014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf"
)
ACCEPTED_DEVELOPMENT_ROWS = 35_000

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_ALL_MASKS = tuple(f"{value:04b}" for value in range(16))
_LEFT_PACKED_MASKS = frozenset({"0000", "1000", "1100", "1110", "1111"})
_LENGTH_THRESHOLDS = (1_024, 65_536, 1_000_000)

_CLEAN_STANDARD_COLUMNS = tuple(
    f"stage03_clean_{name}" for name in STANDARD_ADDRESS_COLUMNS
)
_CLEAN_NATIVE_COLUMNS = tuple(
    f"stage03_clean_{name}" for name in NATIVE_ADDRESS_COLUMNS
)
_LOWER_STANDARD_COLUMNS = LOWER_OUTPUT_COLUMNS[:4]
_LOWER_NATIVE_COLUMNS = LOWER_OUTPUT_COLUMNS[4:8]


class Stage05DesignDiagnosticError(RuntimeError):
    """Privacy-safe failure for the aggregate Stage 5 design diagnostic."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class Stage05DesignDiagnosticConfig:
    stage04_output_directory: Path
    output_directory: Path
    execution_git_sha: str
    expected_stage04_manifest_sha256: str = ACCEPTED_STAGE04_MANIFEST_SHA256
    batch_rows: int = 2_048
    production: bool = True

    def validate(self) -> None:
        if _GIT_SHA_RE.fullmatch(self.execution_git_sha) is None:
            _fail("INVALID_GIT_COMMIT", "Execution Git commit must be a full SHA")
        if _SHA256_RE.fullmatch(self.expected_stage04_manifest_sha256) is None:
            _fail("INVALID_SHA256", "Stage 4 manifest SHA-256 is malformed")
        if self.expected_stage04_manifest_sha256 != ACCEPTED_STAGE04_MANIFEST_SHA256:
            _fail("WRONG_STAGE04_BINDING", "Stage 4 manifest is not accepted")
        if isinstance(self.batch_rows, bool) or self.batch_rows < 1:
            _fail("INVALID_BATCH_SIZE", "Diagnostic batch size must be positive")
        _reject_holdout_paths(self.stage04_output_directory, self.output_directory)


@dataclass(frozen=True, slots=True)
class Stage05DesignDiagnosticOutcome:
    row_count: int
    output_directory: Path
    diagnostic_sha256: str


@dataclass(slots=True)
class _RepresentationMetrics:
    line_counts: Counter[str] = field(
        default_factory=lambda: Counter({str(value): 0 for value in range(5)})
    )
    occupancy_masks: Counter[str] = field(
        default_factory=lambda: Counter({mask: 0 for mask in _ALL_MASKS})
    )
    candidate_available: int = 0
    candidate_unavailable: int = 0
    gap_rows: int = 0
    exact_duplicate_line_rows_clean: int = 0
    exact_duplicate_line_rows_lower: int = 0
    exact_duplicate_line_excess_values_clean: int = 0
    exact_duplicate_line_excess_values_lower: int = 0
    whitespace_only_clean_values: int = 0
    whitespace_only_lower_values: int = 0
    raw_to_clean_occupancy_changed_rows: int = 0
    internal_boundaries: int = 0
    boundary_predecessor_end: Counter[str] = field(
        default_factory=lambda: Counter(
            {
                "COMMA": 0,
                "SEMICOLON": 0,
                "SLASH": 0,
                "HYPHEN_OR_DASH": 0,
                "OTHER_PUNCTUATION": 0,
                "NO_PUNCTUATION": 0,
            }
        )
    )
    boundary_successor_starts_punctuation: int = 0
    candidate_length_overhead_codepoints: int = 0
    very_large_candidates: Counter[str] = field(
        default_factory=lambda: Counter(
            {f"AT_LEAST_{threshold}_CODEPOINTS": 0 for threshold in _LENGTH_THRESHOLDS}
        )
    )

    def to_dict(self, length_statistics: dict[str, int]) -> dict[str, object]:
        return {
            "candidate_availability": {
                "AVAILABLE": self.candidate_available,
                "UNAVAILABLE": self.candidate_unavailable,
            },
            "line_count_distribution": dict(self.line_counts),
            "occupancy_masks_line1_to_line4": dict(self.occupancy_masks),
            "gap_rows": self.gap_rows,
            "duplicate_line_findings": {
                "ROWS_WITH_EXACT_DUPLICATE_CLEAN_LINES": (
                    self.exact_duplicate_line_rows_clean
                ),
                "ROWS_WITH_EXACT_DUPLICATE_LOWER_LINES": (
                    self.exact_duplicate_line_rows_lower
                ),
                "EXCESS_EXACT_DUPLICATE_CLEAN_VALUES": (
                    self.exact_duplicate_line_excess_values_clean
                ),
                "EXCESS_EXACT_DUPLICATE_LOWER_VALUES": (
                    self.exact_duplicate_line_excess_values_lower
                ),
            },
            "whitespace_only_values": {
                "STAGE03_CLEAN": self.whitespace_only_clean_values,
                "STAGE04_LOWER": self.whitespace_only_lower_values,
            },
            "raw_to_clean_occupancy_changed_rows": (
                self.raw_to_clean_occupancy_changed_rows
            ),
            "separator_boundary_findings": {
                "INTERNAL_BOUNDARIES": self.internal_boundaries,
                "PREDECESSOR_END_CLASS": dict(self.boundary_predecessor_end),
                "SUCCESSOR_STARTS_PUNCTUATION": (
                    self.boundary_successor_starts_punctuation
                ),
                "TOTAL_SEPARATOR_OVERHEAD_CODEPOINTS": (
                    self.candidate_length_overhead_codepoints
                ),
            },
            "candidate_length_codepoints": length_statistics,
            "very_large_candidates": dict(self.very_large_candidates),
        }


@dataclass(slots=True)
class _DiagnosticMetrics:
    rows: int = 0
    standard: _RepresentationMetrics = field(default_factory=_RepresentationMetrics)
    native: _RepresentationMetrics = field(default_factory=_RepresentationMetrics)
    relationship: Counter[str] = field(
        default_factory=lambda: Counter(
            {
                "NO_REPRESENTATION": 0,
                "STANDARD_ONLY": 0,
                "NATIVE_ONLY": 0,
                "BOTH": 0,
            }
        )
    )
    both_candidate_relationship: Counter[str] = field(
        default_factory=lambda: Counter({"EXACT_EQUAL_CANONICAL": 0, "DIFFERENT": 0})
    )
    both_sequence_relationship: Counter[str] = field(
        default_factory=lambda: Counter(
            {"EXACT_EQUAL_ORDERED_NONEMPTY_SEQUENCE": 0, "DIFFERENT": 0}
        )
    )
    both_line_count_relationship: Counter[str] = field(
        default_factory=lambda: Counter(
            {"SAME_LINE_COUNT": 0, "DIFFERENT_LINE_COUNT": 0}
        )
    )


def _fail(code: str, message: str) -> NoReturn:
    raise Stage05DesignDiagnosticError(code, message)


def _reject_holdout_paths(*paths: Path) -> None:
    if any("holdout" in part.casefold() for path in paths for part in path.parts):
        _fail("HOLDOUT_ACCESS_PROHIBITED", "A diagnostic path names HOLDOUT")


def _require_mode(path: Path, expected: int) -> None:
    try:
        observed = path.stat(follow_symlinks=False)
    except OSError as error:
        raise Stage05DesignDiagnosticError(
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
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _load_manifest(root: Path) -> dict[str, Any]:
    path = root / STAGE04_MANIFEST_NAME
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Stage05DesignDiagnosticError(
            "STAGE04_MANIFEST_INVALID", "Stage 4 manifest is malformed"
        ) from error
    if not isinstance(value, dict):
        _fail("STAGE04_MANIFEST_INVALID", "Stage 4 manifest is not an object")
    return cast(dict[str, Any], value)


def _artifact_paths(root: Path, manifest: dict[str, Any]) -> tuple[Path, ...]:
    physical = manifest.get("physical_identity")
    if not isinstance(physical, dict):
        _fail("STAGE04_MANIFEST_INVALID", "Stage 4 physical identity is malformed")
    artifacts = physical.get("output_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        _fail("STAGE04_MANIFEST_INVALID", "Stage 4 output artifacts are absent")
    paths: list[Path] = []
    for sequence, raw in enumerate(artifacts, start=1):
        if not isinstance(raw, dict):
            _fail("STAGE04_MANIFEST_INVALID", "Stage 4 output artifact is malformed")
        relative = raw.get("relative_path")
        if relative != f"data/part-{sequence:06d}.parquet":
            _fail("STAGE04_MANIFEST_INVALID", "Stage 4 artifact order is not exact")
        paths.append(root / relative)
    return tuple(paths)


def _iter_batches(paths: tuple[Path, ...], batch_rows: int) -> Iterable[pa.RecordBatch]:
    expected_schema = stage04_schema()
    for path in paths:
        parquet = pq.ParquetFile(path, page_checksum_verification=True)
        if not parquet.schema_arrow.remove_metadata().equals(
            expected_schema, check_metadata=False
        ):
            _fail("STAGE04_SCHEMA_MISMATCH", "Stage 4 schema is not exact")
        for row_group in range(parquet.metadata.num_row_groups):
            yield from parquet.iter_batches(
                batch_size=batch_rows, row_groups=[row_group], use_threads=False
            )


def _line_end_class(value: str) -> str:
    final = value[-1]
    if final == ",":
        return "COMMA"
    if final == ";":
        return "SEMICOLON"
    if final == "/":
        return "SLASH"
    if final == "-" or unicodedata.category(final) == "Pd":
        return "HYPHEN_OR_DASH"
    if unicodedata.category(final).startswith("P"):
        return "OTHER_PUNCTUATION"
    return "NO_PUNCTUATION"


def _observe_representation(
    metrics: _RepresentationMetrics,
    *,
    clean_lines: tuple[str, ...],
    lower_lines: tuple[str, ...],
    raw_nonempty_count: int,
    lengths: sqlite3.Connection,
    representation: str,
) -> tuple[tuple[str, ...], str]:
    if len(clean_lines) != 4 or len(lower_lines) != 4:
        _fail("INTERNAL_DIAGNOSTIC_ERROR", "Address line count is not four")
    for clean, lower in zip(clean_lines, lower_lines, strict=True):
        if clean != "" and clean.isspace():
            metrics.whitespace_only_clean_values += 1
        if lower != "" and lower.isspace():
            metrics.whitespace_only_lower_values += 1
        if lower != clean.lower():
            _fail("STAGE04_SEMANTIC_MISMATCH", "Lower line differs from clean lower")
    nonempty_clean = tuple(value for value in clean_lines if value != "")
    nonempty_lower = tuple(value for value in lower_lines if value != "")
    mask = "".join("1" if value != "" else "0" for value in lower_lines)
    count = len(nonempty_lower)
    metrics.line_counts[str(count)] += 1
    metrics.occupancy_masks[mask] += 1
    if mask not in _LEFT_PACKED_MASKS:
        metrics.gap_rows += 1
    if count:
        metrics.candidate_available += 1
    else:
        metrics.candidate_unavailable += 1
    if raw_nonempty_count != count:
        metrics.raw_to_clean_occupancy_changed_rows += 1
    clean_excess = len(nonempty_clean) - len(set(nonempty_clean))
    lower_excess = len(nonempty_lower) - len(set(nonempty_lower))
    if clean_excess:
        metrics.exact_duplicate_line_rows_clean += 1
        metrics.exact_duplicate_line_excess_values_clean += clean_excess
    if lower_excess:
        metrics.exact_duplicate_line_rows_lower += 1
        metrics.exact_duplicate_line_excess_values_lower += lower_excess
    for predecessor, successor in zip(nonempty_lower, nonempty_lower[1:]):
        metrics.internal_boundaries += 1
        metrics.boundary_predecessor_end[_line_end_class(predecessor)] += 1
        if unicodedata.category(successor[0]).startswith("P"):
            metrics.boundary_successor_starts_punctuation += 1
    candidate = STAGE05_DESIGN_SEPARATOR.join(nonempty_lower)
    overhead = len(STAGE05_DESIGN_SEPARATOR) * max(0, count - 1)
    metrics.candidate_length_overhead_codepoints += overhead
    if count:
        candidate_length = len(candidate)
        lengths.execute(
            "INSERT INTO candidate_lengths (representation, codepoints) VALUES (?, ?)",
            (representation, candidate_length),
        )
        for threshold in _LENGTH_THRESHOLDS:
            if candidate_length >= threshold:
                metrics.very_large_candidates[f"AT_LEAST_{threshold}_CODEPOINTS"] += 1
    return nonempty_lower, candidate


def _length_statistics(
    connection: sqlite3.Connection, representation: str
) -> dict[str, int]:
    row = connection.execute(
        "SELECT COUNT(*), MIN(codepoints), SUM(codepoints), MAX(codepoints) "
        "FROM candidate_lengths WHERE representation = ?",
        (representation,),
    ).fetchone()
    assert row is not None
    count, minimum, total, maximum = (int(value or 0) for value in row)
    if count == 0:
        return {
            "COUNT": 0,
            "MIN": 0,
            "MEDIAN": 0,
            "MEAN_MILLI": 0,
            "P95_NEAREST_RANK": 0,
            "P99_NEAREST_RANK": 0,
            "MAX": 0,
        }

    def ordered(offset: int) -> int:
        value = connection.execute(
            "SELECT codepoints FROM candidate_lengths WHERE representation = ? "
            "ORDER BY codepoints LIMIT 1 OFFSET ?",
            (representation, offset),
        ).fetchone()
        assert value is not None
        return int(value[0])

    if count % 2:
        median = ordered(count // 2)
    else:
        median = (ordered(count // 2 - 1) + ordered(count // 2) + 1) // 2
    return {
        "COUNT": count,
        "MIN": minimum,
        "MEDIAN": median,
        "MEAN_MILLI": (total * 1_000 + count // 2) // count,
        "P95_NEAREST_RANK": ordered(math.ceil(0.95 * count) - 1),
        "P99_NEAREST_RANK": ordered(math.ceil(0.99 * count) - 1),
        "MAX": maximum,
    }


def _observe_batch(
    batch: pa.RecordBatch, metrics: _DiagnosticMetrics, lengths: sqlite3.Connection
) -> None:
    if any(batch.column(index).null_count for index in range(batch.num_columns)):
        _fail("STAGE04_NULL", "Stage 4 contains an unexpected null")
    names = batch.schema.names
    standard_clean_arrays = [
        batch.column(names.index(name)) for name in _CLEAN_STANDARD_COLUMNS
    ]
    native_clean_arrays = [
        batch.column(names.index(name)) for name in _CLEAN_NATIVE_COLUMNS
    ]
    standard_lower_arrays = [
        batch.column(names.index(name)) for name in _LOWER_STANDARD_COLUMNS
    ]
    native_lower_arrays = [
        batch.column(names.index(name)) for name in _LOWER_NATIVE_COLUMNS
    ]
    raw_standard_counts = batch.column(
        names.index("standard_nonempty_source_line_count")
    )
    raw_native_counts = batch.column(names.index("native_nonempty_source_line_count"))
    for row_index in range(batch.num_rows):
        standard_clean = tuple(
            array[row_index].as_py() for array in standard_clean_arrays
        )
        native_clean = tuple(array[row_index].as_py() for array in native_clean_arrays)
        standard_lower = tuple(
            array[row_index].as_py() for array in standard_lower_arrays
        )
        native_lower = tuple(array[row_index].as_py() for array in native_lower_arrays)
        if not all(
            isinstance(value, str)
            for value in (
                *standard_clean,
                *native_clean,
                *standard_lower,
                *native_lower,
            )
        ):
            _fail("STAGE04_TYPE_MISMATCH", "Stage 4 address line is not text")
        standard_sequence, standard_candidate = _observe_representation(
            metrics.standard,
            clean_lines=cast(tuple[str, ...], standard_clean),
            lower_lines=cast(tuple[str, ...], standard_lower),
            raw_nonempty_count=int(raw_standard_counts[row_index].as_py()),
            lengths=lengths,
            representation="STANDARD",
        )
        native_sequence, native_candidate = _observe_representation(
            metrics.native,
            clean_lines=cast(tuple[str, ...], native_clean),
            lower_lines=cast(tuple[str, ...], native_lower),
            raw_nonempty_count=int(raw_native_counts[row_index].as_py()),
            lengths=lengths,
            representation="NATIVE",
        )
        standard_available = bool(standard_sequence)
        native_available = bool(native_sequence)
        if standard_available and native_available:
            metrics.relationship["BOTH"] += 1
            if standard_candidate == native_candidate:
                metrics.both_candidate_relationship["EXACT_EQUAL_CANONICAL"] += 1
            else:
                metrics.both_candidate_relationship["DIFFERENT"] += 1
            if standard_sequence == native_sequence:
                metrics.both_sequence_relationship[
                    "EXACT_EQUAL_ORDERED_NONEMPTY_SEQUENCE"
                ] += 1
            else:
                metrics.both_sequence_relationship["DIFFERENT"] += 1
            if len(standard_sequence) == len(native_sequence):
                metrics.both_line_count_relationship["SAME_LINE_COUNT"] += 1
            else:
                metrics.both_line_count_relationship["DIFFERENT_LINE_COUNT"] += 1
        elif standard_available:
            metrics.relationship["STANDARD_ONLY"] += 1
        elif native_available:
            metrics.relationship["NATIVE_ONLY"] += 1
        else:
            metrics.relationship["NO_REPRESENTATION"] += 1
        metrics.rows += 1


def run_stage05_design_diagnostic(
    config: Stage05DesignDiagnosticConfig,
) -> Stage05DesignDiagnosticOutcome:
    """Publish aggregate-only Stage 4 structure evidence for Stage 5 design."""
    config.validate()
    if config.production:
        require_goethe_nhr_slurm("stage05-design-diagnostic")
    if config.output_directory.exists() or config.output_directory.is_symlink():
        _fail("OUTPUT_COLLISION", "Diagnostic output already exists")
    stage04 = validate_stage04_bundle(
        config.stage04_output_directory,
        expected_manifest_sha256=config.expected_stage04_manifest_sha256,
        authoritative_development=True,
    )
    if (
        stage04.row_count != ACCEPTED_DEVELOPMENT_ROWS
        or stage04.schema_fingerprint != ACCEPTED_STAGE04_SCHEMA_FINGERPRINT
        or stage04.logical_dataset_sha256_v1 != ACCEPTED_STAGE04_LOGICAL_FINGERPRINT
        or stage04.input_binding_sha256 != ACCEPTED_STAGE04_INPUT_BINDING_SHA256
        or stage04.manifest_sha256 != ACCEPTED_STAGE04_MANIFEST_SHA256
    ):
        _fail("WRONG_STAGE04_BINDING", "Stage 4 DEVELOPMENT boundary is not accepted")
    manifest = _load_manifest(config.stage04_output_directory)
    scientific = manifest.get("scientific_identity")
    if not isinstance(scientific, dict) or (
        scientific.get("stage04_contract_version") != ACCEPTED_STAGE04_CONTRACT_VERSION
        or scientific.get("stage04_profile_version") != ACCEPTED_STAGE04_PROFILE_VERSION
        or scientific.get("input_benchmark_fingerprint")
        != ACCEPTED_BENCHMARK_FINGERPRINT
    ):
        _fail("WRONG_STAGE04_BINDING", "Stage 4 scientific contract is not accepted")

    parent = config.output_directory.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent.chmod(0o700)
    _require_mode(parent, 0o700)
    temporary = parent / f".{config.output_directory.name}.{os.getpid()}.in_progress"
    if temporary.exists() or temporary.is_symlink():
        _fail("OUTPUT_COLLISION", "Diagnostic temporary output already exists")
    temporary.mkdir(mode=0o700)
    database_path = temporary / "candidate_lengths.sqlite3"
    lengths = sqlite3.connect(database_path)
    database_path.chmod(0o600)
    lengths.execute(
        "CREATE TABLE candidate_lengths (representation TEXT NOT NULL, "
        "codepoints INTEGER NOT NULL)"
    )
    metrics = _DiagnosticMetrics()
    try:
        for batch in _iter_batches(
            _artifact_paths(config.stage04_output_directory, manifest),
            config.batch_rows,
        ):
            _observe_batch(batch, metrics, lengths)
        lengths.commit()
        if metrics.rows != ACCEPTED_DEVELOPMENT_ROWS:
            _fail(
                "ROW_COUNT_MISMATCH", "Diagnostic did not observe all DEVELOPMENT rows"
            )
        standard_lengths = _length_statistics(lengths, "STANDARD")
        native_lengths = _length_statistics(lengths, "NATIVE")
    finally:
        lengths.close()
    database_path.unlink()
    result = {
        "diagnostic_version": STAGE05_DESIGN_DIAGNOSTIC_VERSION,
        "status": "STAGE05_DESIGN_DIAGNOSTIC_COMPLETE",
        "execution_git_sha": config.execution_git_sha,
        "stage04_binding": {
            "contract": ACCEPTED_STAGE04_CONTRACT_VERSION,
            "profile": ACCEPTED_STAGE04_PROFILE_VERSION,
            "schema_fingerprint": ACCEPTED_STAGE04_SCHEMA_FINGERPRINT,
            "logical_fingerprint": ACCEPTED_STAGE04_LOGICAL_FINGERPRINT,
            "input_binding_sha256": ACCEPTED_STAGE04_INPUT_BINDING_SHA256,
            "manifest_sha256": ACCEPTED_STAGE04_MANIFEST_SHA256,
            "benchmark_fingerprint": ACCEPTED_BENCHMARK_FINGERPRINT,
            "rows": ACCEPTED_DEVELOPMENT_ROWS,
        },
        "separator_under_evaluation": {
            "value_unicode_escape": "\\u002c\\u0020",
            "codepoint_count": len(STAGE05_DESIGN_SEPARATOR),
        },
        "representation_relationship": dict(metrics.relationship),
        "both_candidate_relationship": dict(metrics.both_candidate_relationship),
        "both_sequence_relationship": dict(metrics.both_sequence_relationship),
        "both_line_count_relationship": dict(metrics.both_line_count_relationship),
        "standard": metrics.standard.to_dict(standard_lengths),
        "native": metrics.native.to_dict(native_lengths),
        "privacy": {
            "ROW_VALUES_EMITTED": False,
            "STABLE_IDENTITIES_EMITTED": False,
            "SOURCE_FILENAMES_EMITTED": False,
            "HOLDOUT_ACCESSED": False,
        },
    }
    diagnostic_path = temporary / STAGE05_DESIGN_DIAGNOSTIC_NAME
    _write_json(diagnostic_path, result)
    diagnostic_sha256 = _sha256_file(diagnostic_path)
    _write_json(
        temporary / STAGE05_DESIGN_SUCCESS_NAME,
        {
            "status": "STAGE05_DESIGN_DIAGNOSTIC_COMPLETE",
            "diagnostic_sha256": diagnostic_sha256,
            "row_count": metrics.rows,
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
    return Stage05DesignDiagnosticOutcome(
        row_count=metrics.rows,
        output_directory=config.output_directory,
        diagnostic_sha256=diagnostic_sha256,
    )


__all__ = [
    "ACCEPTED_STAGE04_MANIFEST_SHA256",
    "STAGE05_DESIGN_DIAGNOSTIC_NAME",
    "STAGE05_DESIGN_SEPARATOR",
    "Stage05DesignDiagnosticConfig",
    "Stage05DesignDiagnosticError",
    "Stage05DesignDiagnosticOutcome",
    "run_stage05_design_diagnostic",
]
