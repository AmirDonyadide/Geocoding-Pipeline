#!/usr/bin/env python3
"""Independent, privacy-safe Stage 5 DEVELOPMENT verifier.

The verifier intentionally does not import the Stage 5 implementation.  It
streams the exact accepted Stage 4 and reviewed Stage 5 bundles, emits only
aggregate evidence, and creates a protected offline human-review surface.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import platform
import re
import sqlite3
import stat
import struct
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, NoReturn, Sequence, cast

import pyarrow as pa
import pyarrow.parquet as pq


BASE_SHA = "fd598fda296879396f40d86a87ba37d96c339100"
TARGET_CANDIDATE_SHA = "97bd7fa74da358e81133ac4d38232931762d3e78"
IMPLEMENTATION_SHA = "cd0a5ae91c3602ec20e34f7c419f1ac76f0b9160"
V1_IMPLEMENTATION_SHA = "e69ccaaebbaeff73d88dd43018904671ee6005dd"
V1_JOB_ID = "1759565"
V2_JOB_ID = "1759603"

STAGE04_MANIFEST_SHA = (
    "17a4854cddd8929b65ea79402f1a4f12a1574b720c1921567b577f23e152d1f3"
)
STAGE05_MANIFEST_SHA = (
    "fd945163e3be0242c43b98972350904631279cb99f366baadb0a3094ab6a1fc5"
)
STAGE05_SUCCESS_SHA = "471959d8206999d5418e5fbc0384918ba186af7642f4f4a2dfef4ea83062200c"
STAGE05_INPUT_BINDING_SHA = (
    "7e68c33f7daa482b442eca82c00c6904ec5e38bec1b3fc598d5be4d52a6bcb9f"
)
FIXED_REVIEW_MANIFEST_SHA = (
    "1fa69ce953cb6e4ef70d611e372ab8e8565b8e9aa577d00292a20219dcdd5c92"
)
FIXED_REVIEW_ARTIFACT_SHA = (
    "ffe7b51b67b2db1f64dcb202ab28fd22f32cd863de2e2cb7a7d112f1244f8779"
)
STAGE05_REVIEW_MANIFEST_SHA = (
    "99d3134740c4560294312e6f3ee04dd315effa3796b6e84b8375b9c20c2b2ebb"
)
STAGE05_REVIEW_ARTIFACT_SHA = (
    "be074cc2d3f188931eda9f60e51dc66117acee21ee45d24119044104f5c8e1e7"
)

EXPECTED_STAGE04_LOGICAL = (
    "054c66701f854a0108938170e1cb9bcee8a772f7fed29b82cda53c71aa9747ec"
)
EXPECTED_STAGE04_SCHEMA = (
    "dafb4f78b8bfce3120b6f4f7ae8cb44883f4c3a9cfd94b3137871b83c0ed5cbc"
)
EXPECTED_STAGE04_INPUT_BINDING = (
    "90e0e94d4359bd5927820dfc06b2cfc1dc37485c032d95726d1260ec88a534b0"
)
EXPECTED_ORDERED_IDENTITY = (
    "fe2a4758582c1880d2b5c62dfc5c587d865e05d13033af9f5e8208b58e2a0487"
)
EXPECTED_BENCHMARK = "014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf"
EXPECTED_REVIEW_SUBSET = (
    "014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52"
)
EXPECTED_STAGE05_SCHEMA = (
    "63d4cdb3707eda65c67cc5196891fa5005adce2b12eb7109554793c48c5303c3"
)
EXPECTED_STAGE05_LOGICAL = (
    "ba5829621fc15347d7cd4e168a48587bab896cd0be98924627876ae853dfaff2"
)
EXPECTED_ROWS = 35_000
EXPECTED_REVIEW_ROWS = 500

SOURCE_STANDARD = tuple(f"street_address_line_{index}" for index in range(1, 5))
SOURCE_NATIVE = tuple(f"{name}_native" for name in SOURCE_STANDARD)
CLEAN_STANDARD = tuple(f"stage03_clean_{name}" for name in SOURCE_STANDARD)
CLEAN_NATIVE = tuple(f"stage03_clean_{name}" for name in SOURCE_NATIVE)
LOWER_STANDARD = tuple(f"stage04_lower_{name}" for name in SOURCE_STANDARD)
LOWER_NATIVE = tuple(f"stage04_lower_{name}" for name in SOURCE_NATIVE)
DERIVED_COLUMNS = (
    "stage05_standard_candidate_clean",
    "stage05_native_candidate_clean",
    "stage05_standard_candidate_lower",
    "stage05_native_candidate_lower",
    "stage05_standard_candidate_available",
    "stage05_native_candidate_available",
    "stage05_standard_contributing_line_count",
    "stage05_native_contributing_line_count",
    "stage05_standard_contributing_line_mask",
    "stage05_native_contributing_line_mask",
)
SEPARATOR = " "
ALL_MASKS = tuple(f"{value:04b}" for value in range(16))
LEFT_PACKED_MASKS = frozenset({"0000", "1000", "1100", "1110", "1111"})
PREVIOUS_QUESTIONABLE = frozenset({59, 116, 257, 322})
CLASSIFICATIONS = (
    "CORRECT_RECONSTRUCTION",
    "VALID_BUT_REDUNDANT_SOURCE_CONTENT",
    "QUESTIONABLE_BOUNDARY",
    "QUESTIONABLE_ORDER",
    "SEMANTIC_DAMAGE",
)

SHA_RE = re.compile(r"^[0-9a-f]{64}$")
TYPE_UINT64 = b"\x01"
TYPE_TEXT = b"\x02"
TYPE_DIGEST = b"\x03"
ORDERED_IDENTITY_DOMAIN = b"SAFE_STAGE03_ORDERED_STABLE_IDENTITIES_V1"
SCHEMA_DOMAIN = b"SAFE_STAGE05_ARROW_SCHEMA_V1"
LOGICAL_DOMAIN = b"SAFE_STAGE05_LOGICAL_DATASET_V1"
REVIEW_SUBSET_DOMAIN = b"SAFE_DEVELOPMENT_REVIEW_SUBSET_V1"
REVIEW_ID_DOMAIN = b"SAFE_DEVELOPMENT_REVIEW_ID_V1"
DERIVED_STREAM_DOMAIN = b"SAFE_STAGE05_INDEPENDENT_DERIVED_STREAM_V1"
ROW_COMPARE_DOMAIN = b"SAFE_STAGE05_INDEPENDENT_FIXED_ROW_V1"
SCOPE_DOMAIN = b"SAFE_STAGE05_V2_QUALITATIVE_SCOPE_V1"


class ReviewFailure(RuntimeError):
    """A privacy-safe independent-review failure."""


def fail(code: str) -> NoReturn:
    raise ReviewFailure(code)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail("JSON_OBJECT_REQUIRED")
    return cast(dict[str, Any], value)


def reject_holdout(*paths: Path) -> None:
    if any(
        "holdout" in component.casefold() for path in paths for component in path.parts
    ):
        fail("HOLDOUT_ACCESS_PROHIBITED")


def require_file(path: Path, *, mode: int = 0o600) -> None:
    observed = path.stat(follow_symlinks=False)
    if path.is_symlink() or not stat.S_ISREG(observed.st_mode):
        fail("REGULAR_FILE_REQUIRED")
    if stat.S_IMODE(observed.st_mode) != mode:
        fail("FILE_MODE_MISMATCH")


def require_directory(path: Path, *, mode: int = 0o700) -> None:
    observed = path.stat(follow_symlinks=False)
    if path.is_symlink() or not stat.S_ISDIR(observed.st_mode):
        fail("REGULAR_DIRECTORY_REQUIRED")
    if stat.S_IMODE(observed.st_mode) != mode:
        fail("DIRECTORY_MODE_MISMATCH")


def require_digest(value: object, expected: str) -> None:
    if (
        not isinstance(value, str)
        or value != expected
        or SHA_RE.fullmatch(value) is None
    ):
        fail("DIGEST_MISMATCH")


def encode_uint64(digest: Any, value: int) -> None:
    digest.update(TYPE_UINT64 + struct.pack(">Q", value))


def encode_text(digest: Any, value: str) -> None:
    payload = value.encode("utf-8", errors="strict")
    digest.update(TYPE_TEXT + struct.pack(">Q", len(payload)) + payload)


def encode_digest(digest: Any, value: str) -> None:
    digest.update(TYPE_DIGEST + bytes.fromhex(value))


def encode_value(digest: Any, value: object) -> None:
    if value is None:
        digest.update(b"N")
    elif isinstance(value, bool):
        digest.update(b"B1" if value else b"B0")
    elif isinstance(value, int):
        digest.update(b"I" + struct.pack(">q", value))
    elif isinstance(value, str):
        digest.update(b"T")
        encode_text(digest, value)
    elif isinstance(value, bytes):
        digest.update(b"Y" + struct.pack(">Q", len(value)) + value)
    elif isinstance(value, list):
        digest.update(b"L" + struct.pack(">Q", len(value)))
        for item in value:
            encode_value(digest, item)
    elif isinstance(value, dict):
        digest.update(b"D" + struct.pack(">Q", len(value)))
        for key in sorted(value):
            encode_text(digest, str(key))
            encode_value(digest, value[key])
    else:
        fail("UNSUPPORTED_CANONICAL_VALUE")


@dataclass(slots=True)
class IdentityHasher:
    digest: Any
    row_count: int = 0

    @classmethod
    def create(cls) -> IdentityHasher:
        return cls(hashlib.sha256(ORDERED_IDENTITY_DOMAIN))

    def update(self, values: pa.Array) -> None:
        if (
            not pa.types.is_fixed_size_binary(values.type)
            or values.type.byte_width != 32
            or values.null_count
        ):
            fail("IDENTITY_ARRAY_INVALID")
        buffer = values.buffers()[1]
        if buffer is None:
            fail("IDENTITY_BUFFER_MISSING")
        self.digest.update(
            buffer.slice(values.offset * 32, len(values) * 32).to_pybytes()
        )
        self.row_count += len(values)

    def hexdigest(self) -> str:
        copy = self.digest.copy()
        copy.update(b"\x00ROWS" + struct.pack(">Q", self.row_count))
        return cast(str, copy.hexdigest())


@dataclass(slots=True)
class RepresentationMetrics:
    available: int = 0
    unavailable: int = 0
    counts: Counter[str] = field(
        default_factory=lambda: Counter({str(value): 0 for value in range(5)})
    )
    masks: Counter[str] = field(
        default_factory=lambda: Counter({mask: 0 for mask in ALL_MASKS})
    )
    gaps: int = 0
    duplicate_rows_clean: int = 0
    duplicate_rows_lower: int = 0
    duplicate_excess_clean: int = 0
    duplicate_excess_lower: int = 0
    boundaries: int = 0
    predecessor_ends_comma: int = 0
    successor_starts_punctuation: int = 0
    separator_overhead: int = 0
    large: Counter[str] = field(
        default_factory=lambda: Counter(
            {
                "AT_LEAST_1024_CODEPOINTS": 0,
                "AT_LEAST_65536_CODEPOINTS": 0,
                "AT_LEAST_1000000_CODEPOINTS": 0,
            }
        )
    )


@dataclass(slots=True)
class Metrics:
    rows: int = 0
    standard: RepresentationMetrics = field(default_factory=RepresentationMetrics)
    native: RepresentationMetrics = field(default_factory=RepresentationMetrics)
    relationship: Counter[str] = field(
        default_factory=lambda: Counter(
            {"NO_REPRESENTATION": 0, "STANDARD_ONLY": 0, "NATIVE_ONLY": 0, "BOTH": 0}
        )
    )
    both_candidates: Counter[str] = field(
        default_factory=lambda: Counter({"EXACT_EQUAL_CANONICAL": 0, "DIFFERENT": 0})
    )
    both_counts: Counter[str] = field(
        default_factory=lambda: Counter(
            {"SAME_LINE_COUNT": 0, "DIFFERENT_LINE_COUNT": 0}
        )
    )


@dataclass(frozen=True, slots=True)
class Reconstruction:
    candidate: str
    available: bool
    count: int
    mask: str


def reconstruct(lines: Sequence[str], separator: str = SEPARATOR) -> Reconstruction:
    if len(lines) != 4 or any(not isinstance(value, str) for value in lines):
        fail("RECONSTRUCTION_INPUT_INVALID")
    contributors = tuple(value for value in lines if value != "")
    return Reconstruction(
        candidate=separator.join(contributors),
        available=bool(contributors),
        count=len(contributors),
        mask="".join("1" if value != "" else "0" for value in lines),
    )


def batches(parquet: pq.ParquetFile, *, batch_size: int) -> Iterator[pa.RecordBatch]:
    for row_group in range(parquet.metadata.num_row_groups):
        yield from parquet.iter_batches(
            batch_size=batch_size, row_groups=[row_group], use_threads=False
        )


def aligned_batches(
    left: Iterable[pa.RecordBatch], right: Iterable[pa.RecordBatch]
) -> Iterator[tuple[pa.RecordBatch, pa.RecordBatch]]:
    left_iterator = iter(left)
    right_iterator = iter(right)
    left_batch: pa.RecordBatch | None = None
    right_batch: pa.RecordBatch | None = None
    left_offset = 0
    right_offset = 0
    while True:
        if left_batch is None or left_offset == left_batch.num_rows:
            left_batch = next(left_iterator, None)
            left_offset = 0
        if right_batch is None or right_offset == right_batch.num_rows:
            right_batch = next(right_iterator, None)
            right_offset = 0
        if left_batch is None or right_batch is None:
            if left_batch is not None or right_batch is not None:
                fail("ROW_STREAM_LENGTH_MISMATCH")
            return
        size = min(
            left_batch.num_rows - left_offset, right_batch.num_rows - right_offset
        )
        yield left_batch.slice(left_offset, size), right_batch.slice(right_offset, size)
        left_offset += size
        right_offset += size


def artifact_inventory(manifest: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    physical = manifest.get("physical_identity")
    if not isinstance(physical, dict) or not isinstance(physical.get(key), list):
        fail("ARTIFACT_INVENTORY_INVALID")
    return cast(list[dict[str, Any]], physical[key])


def verify_artifact(root: Path, raw: Mapping[str, Any], sequence: int) -> Path:
    relative = raw.get("relative_path")
    if relative != f"data/part-{sequence:06d}.parquet":
        fail("ARTIFACT_PATH_OR_ORDER_MISMATCH")
    path = root / cast(str, relative)
    require_file(path)
    if path.stat(follow_symlinks=False).st_size != raw.get("size_bytes"):
        fail("ARTIFACT_SIZE_MISMATCH")
    observed = sha256_file(path)
    if observed != raw.get("sha256"):
        fail("ARTIFACT_SHA_MISMATCH")
    return path


def verify_runtime() -> None:
    if sys.version_info[:3] != (3, 14, 3):
        fail("PYTHON_RUNTIME_MISMATCH")
    if unicodedata.unidata_version != "16.0.0":
        fail("UNICODE_RUNTIME_MISMATCH")
    if pa.__version__ != "25.0.0":
        fail("PYARROW_RUNTIME_MISMATCH")


def verify_binding(path: Path) -> dict[str, Any]:
    require_file(path)
    require_digest(sha256_file(path), STAGE05_INPUT_BINDING_SHA)
    binding = load_json(path)
    expected = {
        "stage05_input_binding_version": "stage05_input_binding_v1",
        "upstream_contract_version": "stage04_lowercase_canonical_contract_v1",
        "upstream_profile_version": "stage04_lowercase_canonical_profile_v1",
        "upstream_logical_fingerprint": EXPECTED_STAGE04_LOGICAL,
        "upstream_schema_fingerprint": EXPECTED_STAGE04_SCHEMA,
        "upstream_input_binding_sha256": EXPECTED_STAGE04_INPUT_BINDING,
        "upstream_manifest_sha256": STAGE04_MANIFEST_SHA,
        "upstream_ordered_identity_sha256": EXPECTED_ORDERED_IDENTITY,
        "input_benchmark_fingerprint": EXPECTED_BENCHMARK,
        "expected_row_count": EXPECTED_ROWS,
    }
    if binding != expected:
        fail("INPUT_BINDING_MISMATCH")
    return binding


def recompute_schema_fingerprint(schema: pa.Schema) -> str:
    digest = hashlib.sha256(SCHEMA_DOMAIN)
    encode_text(digest, "stage05_address_reconstruction_schema_v1")
    encode_uint64(digest, len(schema))
    for schema_field in schema.remove_metadata():
        encode_text(digest, schema_field.name)
        encode_text(digest, str(schema_field.type))
        encode_text(digest, str(schema_field.nullable).lower())
    return digest.hexdigest()


def recompute_logical(binding: Mapping[str, Any], schema_fingerprint: str) -> str:
    digest = hashlib.sha256(LOGICAL_DOMAIN)
    for value in (
        "stage05_address_reconstruction_contract_v2",
        "stage05_address_reconstruction_profile_v2",
        "stage05_address_reconstruction_schema_v1",
        " ",
        "SOURCE_LINE_1_TO_4_RELATIVE_ORDER",
        "EXACT_EMPTY_STRING_FILTER",
        "SKIP_EMPTY_WITHOUT_ARTIFICIAL_SEPARATOR",
        "PRESERVE_EXACT_DUPLICATE_LINES",
        "EXCLUDED_FROM_RECONSTRUCTION",
        "STANDARD_NATIVE_SEPARATE",
        "CASE_PRESERVED_AND_LOWER_CANDIDATES",
        "ZERO_LINES_EMPTY_CANDIDATE_UNAVAILABLE",
        cast(str, binding["upstream_contract_version"]),
        cast(str, binding["upstream_profile_version"]),
    ):
        encode_text(digest, value)
    for value in (
        *CLEAN_STANDARD,
        *CLEAN_NATIVE,
        *LOWER_STANDARD,
        *LOWER_NATIVE,
        *DERIVED_COLUMNS,
    ):
        encode_text(digest, value)
    for value in (
        cast(str, binding["upstream_logical_fingerprint"]),
        cast(str, binding["upstream_schema_fingerprint"]),
        cast(str, binding["upstream_ordered_identity_sha256"]),
        cast(str, binding["input_benchmark_fingerprint"]),
        schema_fingerprint,
    ):
        encode_digest(digest, value)
    encode_uint64(digest, cast(int, binding["expected_row_count"]))
    return digest.hexdigest()


def validate_manifests(
    stage04_root: Path, stage05_root: Path, binding: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    stage04_manifest_path = stage04_root / "stage04_manifest.json"
    stage05_manifest_path = stage05_root / "stage05_manifest.json"
    stage05_success_path = stage05_root / "_SUCCESS.json"
    for path in (stage04_manifest_path, stage05_manifest_path, stage05_success_path):
        require_file(path)
    require_digest(sha256_file(stage04_manifest_path), STAGE04_MANIFEST_SHA)
    require_digest(sha256_file(stage05_manifest_path), STAGE05_MANIFEST_SHA)
    require_digest(sha256_file(stage05_success_path), STAGE05_SUCCESS_SHA)
    stage04 = load_json(stage04_manifest_path)
    stage05 = load_json(stage05_manifest_path)
    success = load_json(stage05_success_path)
    science = stage05.get("scientific_identity")
    physical = stage05.get("physical_identity")
    validation = stage05.get("validation")
    provenance = stage05.get("operational_provenance")
    if not all(
        isinstance(value, dict) for value in (science, physical, validation, provenance)
    ):
        fail("STAGE05_MANIFEST_STRUCTURE_INVALID")
    science = cast(dict[str, Any], science)
    physical = cast(dict[str, Any], physical)
    validation = cast(dict[str, Any], validation)
    provenance = cast(dict[str, Any], provenance)
    expected_science = {
        "stage05_contract_version": "stage05_address_reconstruction_contract_v2",
        "stage05_profile_version": "stage05_address_reconstruction_profile_v2",
        "stage05_schema_version": "stage05_address_reconstruction_schema_v1",
        "stage05_schema_fingerprint": EXPECTED_STAGE05_SCHEMA,
        "stage05_logical_dataset_sha256_v1": EXPECTED_STAGE05_LOGICAL,
        "case_preserved_input_columns": [*CLEAN_STANDARD, *CLEAN_NATIVE],
        "lower_input_columns": [*LOWER_STANDARD, *LOWER_NATIVE],
        "derived_columns": list(DERIVED_COLUMNS),
        "separator_unicode_escape": "\\u0020",
        "line_order": "SOURCE_LINE_1_TO_4_RELATIVE_ORDER",
        "empty_line_rule": "EXACT_EMPTY_STRING_FILTER",
        "gap_rule": "SKIP_EMPTY_WITHOUT_ARTIFICIAL_SEPARATOR",
        "duplicate_line_rule": "PRESERVE_EXACT_DUPLICATE_LINES",
        "geographic_field_rule": "EXCLUDED_FROM_RECONSTRUCTION",
        "standard_native_separate": True,
        "upstream_stage04_contract_version": binding["upstream_contract_version"],
        "upstream_stage04_profile_version": binding["upstream_profile_version"],
        "upstream_stage04_logical_fingerprint": EXPECTED_STAGE04_LOGICAL,
        "upstream_stage04_schema_fingerprint": EXPECTED_STAGE04_SCHEMA,
        "upstream_stage04_input_binding_sha256": EXPECTED_STAGE04_INPUT_BINDING,
        "upstream_ordered_identity_sha256": EXPECTED_ORDERED_IDENTITY,
        "input_benchmark_fingerprint": EXPECTED_BENCHMARK,
        "row_count": EXPECTED_ROWS,
    }
    if science != expected_science:
        fail("STAGE05_SCIENTIFIC_IDENTITY_MISMATCH")
    require_digest(
        physical.get("stage05_input_binding_sha256"), STAGE05_INPUT_BINDING_SHA
    )
    require_digest(
        physical.get("upstream_stage04_manifest_sha256"), STAGE04_MANIFEST_SHA
    )
    if (
        provenance.get("execution_git_sha") != IMPLEMENTATION_SHA
        or str(provenance.get("slurm_job_id")) != V2_JOB_ID
    ):
        fail("STAGE05_EXECUTION_PROVENANCE_MISMATCH")
    if (
        stage05.get("status") != "STAGE_5_DEVELOPMENT_CANDIDATE_MATERIALIZED"
        or success.get("status") != "STAGE_5_DEVELOPMENT_CANDIDATE_MATERIALIZED"
        or success.get("stage05_manifest_sha256") != STAGE05_MANIFEST_SHA
        or success.get("stage05_input_binding_sha256") != STAGE05_INPUT_BINDING_SHA
        or success.get("stage05_logical_dataset_sha256_v1") != EXPECTED_STAGE05_LOGICAL
        or success.get("stage05_schema_fingerprint") != EXPECTED_STAGE05_SCHEMA
        or success.get("ordered_stable_identity_sha256_v1") != EXPECTED_ORDERED_IDENTITY
        or success.get("row_count") != EXPECTED_ROWS
    ):
        fail("STAGE05_TERMINAL_IDENTITY_MISMATCH")
    if any(
        value != "PASS"
        for key, value in validation.items()
        if key != "validation_contract_version"
    ):
        fail("STAGE05_RECORDED_VALIDATION_INCOMPLETE")
    ordered = physical.get("ordered_identity_validation")
    bounded = physical.get("bounded_memory_architecture")
    if not isinstance(ordered, dict) or not isinstance(bounded, dict):
        fail("STAGE05_PHYSICAL_IDENTITY_INVALID")
    if (
        ordered.get("input_ordered_stable_identity_sha256_v1")
        != EXPECTED_ORDERED_IDENTITY
        or ordered.get("output_ordered_stable_identity_sha256_v1")
        != EXPECTED_ORDERED_IDENTITY
        or ordered.get("row_count") != EXPECTED_ROWS
        or bounded.get("maximum_configured_batch_rows") != 2048
        or bounded.get("target_uncompressed_batch_bytes") != 268_435_456
        or bounded.get("memory_scales_with_total_row_count") is not False
        or bounded.get("total_row_python_identity_set_used") is not False
        or bounded.get("length_quantiles_disk_backed") is not True
    ):
        fail("STAGE05_PHYSICAL_IDENTITY_MISMATCH")
    return (
        stage04,
        stage05,
        artifact_inventory(stage04, "output_artifacts"),
        artifact_inventory(stage05, "output_artifacts"),
    )


def row_digest(
    batch: pa.RecordBatch | pa.Table, row: int, columns: Sequence[str]
) -> str:
    digest = hashlib.sha256(ROW_COMPARE_DOMAIN)
    for name in columns:
        encode_text(digest, name)
        encode_value(digest, named_column(batch, name)[row].as_py())
    return digest.hexdigest()


def named_column(
    batch: pa.RecordBatch | pa.Table, name: str
) -> pa.Array | pa.ChunkedArray:
    if isinstance(batch, pa.RecordBatch):
        return batch.column(batch.schema.get_field_index(name))
    return batch.column(name)


def review_subset_fingerprint(identities: list[bytes]) -> str:
    if len(identities) != EXPECTED_REVIEW_ROWS or len(set(identities)) != len(
        identities
    ):
        fail("FIXED_REVIEW_IDENTITY_SET_INVALID")
    digest = hashlib.sha256(REVIEW_SUBSET_DOMAIN)
    for value in (
        "development_reporting_contract_v1",
        "development_review_subset_contract_v1",
        "development_review_balanced_selection_v1",
        "development_review_allocation_policy_v1",
    ):
        encode_text(digest, value)
    encode_digest(digest, EXPECTED_BENCHMARK)
    encode_uint64(digest, EXPECTED_ROWS)
    encode_uint64(digest, EXPECTED_REVIEW_ROWS)
    policy: tuple[tuple[str, str | int], ...] = (
        ("allocation_policy_version", "development_review_allocation_policy_v1"),
        ("minimum_per_country", 1),
        ("minimum_per_location", 30),
        ("minimum_per_batch_priority", 25),
        ("minimum_per_presence_class", 30),
        ("minimum_per_equality_class", 20),
        ("minimum_per_script_class", 30),
        ("minimum_per_line_count", 12),
        ("minimum_per_missingness_class", 8),
        ("minimum_per_challenge_flag", 100),
        ("minimum_per_challenge_reason", 20),
    )
    for name, value in policy:
        encode_text(digest, name)
        encode_text(digest, value) if isinstance(value, str) else encode_uint64(
            digest, value
        )
    ordered = sorted(identities)
    encode_uint64(digest, len(ordered))
    for identity in ordered:
        digest.update(b"\x04" + identity)
    return digest.hexdigest()


def load_fixed_review(
    fixed_root: Path, stage05_review_root: Path
) -> tuple[pa.Table, pa.Table, dict[bytes, str], tuple[str, ...]]:
    fixed_manifest = fixed_root / "development_review_manifest.json"
    fixed_path = fixed_root / "selection/selected_identities.parquet"
    review_manifest = stage05_review_root / "stage05_review_manifest.json"
    review_path = stage05_review_root / "stage05_review.parquet"
    for path in (fixed_manifest, fixed_path, review_manifest, review_path):
        require_file(path)
    require_digest(sha256_file(fixed_manifest), FIXED_REVIEW_MANIFEST_SHA)
    require_digest(sha256_file(fixed_path), FIXED_REVIEW_ARTIFACT_SHA)
    require_digest(sha256_file(review_manifest), STAGE05_REVIEW_MANIFEST_SHA)
    require_digest(sha256_file(review_path), STAGE05_REVIEW_ARTIFACT_SHA)
    fixed = pq.ParquetFile(fixed_path, page_checksum_verification=True).read(
        use_threads=False
    )
    review = pq.ParquetFile(review_path, page_checksum_verification=True).read(
        use_threads=False
    )
    if (
        fixed.num_rows != EXPECTED_REVIEW_ROWS
        or review.num_rows != EXPECTED_REVIEW_ROWS
    ):
        fail("FIXED_REVIEW_ROW_COUNT_MISMATCH")
    for name in ("review_order", "development_review_id_v1", "stable_source_row_id_v1"):
        if not fixed.column(name).equals(review.column(name)):
            fail("FIXED_REVIEW_IDENTITY_OR_ORDER_MISMATCH")
    orders = fixed.column("review_order").to_pylist()
    stable_ids = cast(list[bytes], fixed.column("stable_source_row_id_v1").to_pylist())
    if orders != list(range(1, EXPECTED_REVIEW_ROWS + 1)):
        fail("FIXED_REVIEW_ORDER_INVALID")
    expected_review_ids = [
        hashlib.sha256(
            REVIEW_ID_DOMAIN + bytes.fromhex(EXPECTED_BENCHMARK) + identity
        ).digest()
        for identity in stable_ids
    ]
    if fixed.column("development_review_id_v1").to_pylist() != expected_review_ids:
        fail("FIXED_REVIEW_DERIVED_IDENTITY_MISMATCH")
    if review_subset_fingerprint(stable_ids) != EXPECTED_REVIEW_SUBSET:
        fail("FIXED_REVIEW_FINGERPRINT_MISMATCH")
    common_columns = tuple(
        name
        for name in review.schema.names
        if name
        not in {
            "review_order",
            "development_review_id_v1",
            "stage05_review_classification",
        }
    )
    review_digests = {
        stable_ids[index]: row_digest(review, index, common_columns)
        for index in range(EXPECTED_REVIEW_ROWS)
    }
    return fixed, review, review_digests, common_columns


def observe_representation(
    metrics: RepresentationMetrics,
    clean_lines: tuple[str, str, str, str],
    lower_lines: tuple[str, str, str, str],
    clean: Reconstruction,
    lower: Reconstruction,
    lengths: sqlite3.Connection,
    representation: str,
) -> None:
    metrics.available += int(lower.available)
    metrics.unavailable += int(not lower.available)
    metrics.counts[str(lower.count)] += 1
    metrics.masks[lower.mask] += 1
    metrics.gaps += int(lower.mask not in LEFT_PACKED_MASKS)
    clean_values = tuple(value for value in clean_lines if value != "")
    lower_values = tuple(value for value in lower_lines if value != "")
    clean_excess = len(clean_values) - len(set(clean_values))
    lower_excess = len(lower_values) - len(set(lower_values))
    metrics.duplicate_rows_clean += int(clean_excess > 0)
    metrics.duplicate_rows_lower += int(lower_excess > 0)
    metrics.duplicate_excess_clean += clean_excess
    metrics.duplicate_excess_lower += lower_excess
    for predecessor, successor in zip(lower_values, lower_values[1:]):
        metrics.boundaries += 1
        metrics.predecessor_ends_comma += int(predecessor[-1] == ",")
        metrics.successor_starts_punctuation += int(
            unicodedata.category(successor[0]).startswith("P")
        )
    metrics.separator_overhead += max(lower.count - 1, 0)
    if lower.available:
        length = len(lower.candidate)
        lengths.execute(
            "INSERT INTO lengths (representation, codepoints) VALUES (?, ?)",
            (representation, length),
        )
        for threshold in (1024, 65536, 1000000):
            metrics.large[f"AT_LEAST_{threshold}_CODEPOINTS"] += int(
                length >= threshold
            )
    if clean.candidate.lower() != lower.candidate:
        fail("CLEAN_LOWER_RECONSTRUCTION_MISMATCH")


def length_statistics(
    connection: sqlite3.Connection, representation: str
) -> dict[str, int]:
    row = connection.execute(
        "SELECT COUNT(*), MIN(codepoints), SUM(codepoints), MAX(codepoints) "
        "FROM lengths WHERE representation = ?",
        (representation,),
    ).fetchone()
    if row is None:
        fail("LENGTH_STATISTICS_MISSING")
    count, minimum, total, maximum = (int(value or 0) for value in row)
    if not count:
        return {
            key: 0
            for key in (
                "COUNT",
                "MIN",
                "MEDIAN",
                "MEAN_MILLI",
                "P95_NEAREST_RANK",
                "P99_NEAREST_RANK",
                "MAX",
            )
        }

    def ordered(offset: int) -> int:
        value = connection.execute(
            "SELECT codepoints FROM lengths WHERE representation = ? "
            "ORDER BY codepoints LIMIT 1 OFFSET ?",
            (representation, offset),
        ).fetchone()
        if value is None:
            fail("LENGTH_ORDER_STATISTIC_MISSING")
        return int(value[0])

    median = (
        ordered(count // 2)
        if count % 2
        else (ordered(count // 2 - 1) + ordered(count // 2) + 1) // 2
    )
    return {
        "COUNT": count,
        "MIN": minimum,
        "MEDIAN": median,
        "MEAN_MILLI": (total * 1000 + count // 2) // count,
        "P95_NEAREST_RANK": ordered(math.ceil(0.95 * count) - 1),
        "P99_NEAREST_RANK": ordered(math.ceil(0.99 * count) - 1),
        "MAX": maximum,
    }


def metric_groups(
    metrics: Metrics,
    standard_lengths: Mapping[str, int],
    native_lengths: Mapping[str, int],
) -> dict[str, dict[str, int]]:
    duplicate = {
        "STANDARD_ROWS_WITH_EXACT_DUPLICATE_CLEAN_LINES": metrics.standard.duplicate_rows_clean,
        "NATIVE_ROWS_WITH_EXACT_DUPLICATE_CLEAN_LINES": metrics.native.duplicate_rows_clean,
        "STANDARD_ROWS_WITH_EXACT_DUPLICATE_LOWER_LINES": metrics.standard.duplicate_rows_lower,
        "NATIVE_ROWS_WITH_EXACT_DUPLICATE_LOWER_LINES": metrics.native.duplicate_rows_lower,
        "STANDARD_EXCESS_EXACT_DUPLICATE_CLEAN_VALUES": metrics.standard.duplicate_excess_clean,
        "NATIVE_EXCESS_EXACT_DUPLICATE_CLEAN_VALUES": metrics.native.duplicate_excess_clean,
        "STANDARD_EXCESS_EXACT_DUPLICATE_LOWER_VALUES": metrics.standard.duplicate_excess_lower,
        "NATIVE_EXCESS_EXACT_DUPLICATE_LOWER_VALUES": metrics.native.duplicate_excess_lower,
    }
    return {
        "ROW_INTEGRITY": {
            "INPUT_ROWS": metrics.rows,
            "OUTPUT_ROWS": metrics.rows,
            "DROPPED_ROWS": 0,
            "ADDED_ROWS": 0,
            "DUPLICATE_IDENTITIES": 0,
        },
        "REPRESENTATION_AVAILABILITY": {
            **dict(metrics.relationship),
            "STANDARD_AVAILABLE": metrics.standard.available,
            "STANDARD_UNAVAILABLE": metrics.standard.unavailable,
            "NATIVE_AVAILABLE": metrics.native.available,
            "NATIVE_UNAVAILABLE": metrics.native.unavailable,
        },
        "BOTH_CANDIDATE_RELATIONSHIP": dict(metrics.both_candidates),
        "BOTH_LINE_COUNT_RELATIONSHIP": dict(metrics.both_counts),
        "STANDARD_LINE_COUNT": dict(metrics.standard.counts),
        "NATIVE_LINE_COUNT": dict(metrics.native.counts),
        "STANDARD_OCCUPANCY_MASK": dict(metrics.standard.masks),
        "NATIVE_OCCUPANCY_MASK": dict(metrics.native.masks),
        "GAP_FINDINGS": {
            "STANDARD_GAP_ROWS": metrics.standard.gaps,
            "NATIVE_GAP_ROWS": metrics.native.gaps,
        },
        "DUPLICATE_LINE_FINDINGS": duplicate,
        "SEPARATOR_BOUNDARIES": {
            "STANDARD_INTERNAL_BOUNDARIES": metrics.standard.boundaries,
            "NATIVE_INTERNAL_BOUNDARIES": metrics.native.boundaries,
            "STANDARD_PREDECESSOR_ENDS_COMMA": metrics.standard.predecessor_ends_comma,
            "NATIVE_PREDECESSOR_ENDS_COMMA": metrics.native.predecessor_ends_comma,
            "STANDARD_SUCCESSOR_STARTS_PUNCTUATION": metrics.standard.successor_starts_punctuation,
            "NATIVE_SUCCESSOR_STARTS_PUNCTUATION": metrics.native.successor_starts_punctuation,
            "STANDARD_SEPARATOR_OVERHEAD_CODEPOINTS": metrics.standard.separator_overhead,
            "NATIVE_SEPARATOR_OVERHEAD_CODEPOINTS": metrics.native.separator_overhead,
        },
        "STANDARD_CANDIDATE_LENGTH_CODEPOINTS": dict(standard_lengths),
        "NATIVE_CANDIDATE_LENGTH_CODEPOINTS": dict(native_lengths),
        "VERY_LARGE_CANDIDATES": {
            **{
                f"STANDARD_{key}": value
                for key, value in metrics.standard.large.items()
            },
            **{f"NATIVE_{key}": value for key, value in metrics.native.large.items()},
        },
        "RECONSTRUCTION_VALIDATION": {
            "RECONSTRUCTION_MISMATCHES": 0,
            "AUDIT_MISMATCHES": 0,
            "CLEAN_LOWER_CONSISTENCY_MISMATCHES": 0,
            "IDEMPOTENCE_FAILURES": 0,
        },
    }


def expected_metric_checks(groups: Mapping[str, Mapping[str, int]]) -> None:
    expected = {
        "availability": {
            "STANDARD_ONLY": 75,
            "NATIVE_ONLY": 178,
            "BOTH": 34747,
            "NO_REPRESENTATION": 0,
            "STANDARD_AVAILABLE": 34822,
            "STANDARD_UNAVAILABLE": 178,
            "NATIVE_AVAILABLE": 34925,
            "NATIVE_UNAVAILABLE": 75,
        },
        "both": {"EXACT_EQUAL_CANONICAL": 17913, "DIFFERENT": 16834},
        "standard_counts": {"0": 178, "1": 14991, "2": 16890, "3": 2697, "4": 244},
        "native_counts": {"0": 75, "1": 15032, "2": 16912, "3": 2700, "4": 281},
        "standard_masks": {
            "0000": 178,
            "0001": 0,
            "0010": 6,
            "0011": 0,
            "0100": 61,
            "0101": 1,
            "0110": 2,
            "0111": 0,
            "1000": 14924,
            "1001": 0,
            "1010": 1516,
            "1011": 0,
            "1100": 15371,
            "1101": 11,
            "1110": 2686,
            "1111": 244,
        },
        "native_masks": {
            "0000": 75,
            "0001": 27,
            "0010": 4,
            "0011": 0,
            "0100": 35,
            "0101": 1,
            "0110": 1,
            "0111": 0,
            "1000": 14966,
            "1001": 56,
            "1010": 1516,
            "1011": 0,
            "1100": 15338,
            "1101": 97,
            "1110": 2603,
            "1111": 281,
        },
    }
    if groups["REPRESENTATION_AVAILABILITY"] != expected["availability"]:
        fail("INDEPENDENT_AVAILABILITY_DISCREPANCY")
    if groups["BOTH_CANDIDATE_RELATIONSHIP"] != expected["both"]:
        fail("INDEPENDENT_BOTH_RELATIONSHIP_DISCREPANCY")
    if groups["STANDARD_LINE_COUNT"] != expected["standard_counts"]:
        fail("INDEPENDENT_STANDARD_COUNT_DISCREPANCY")
    if groups["NATIVE_LINE_COUNT"] != expected["native_counts"]:
        fail("INDEPENDENT_NATIVE_COUNT_DISCREPANCY")
    if groups["STANDARD_OCCUPANCY_MASK"] != expected["standard_masks"]:
        fail("INDEPENDENT_STANDARD_MASK_DISCREPANCY")
    if groups["NATIVE_OCCUPANCY_MASK"] != expected["native_masks"]:
        fail("INDEPENDENT_NATIVE_MASK_DISCREPANCY")
    if groups["GAP_FINDINGS"] != {"STANDARD_GAP_ROWS": 1597, "NATIVE_GAP_ROWS": 1737}:
        fail("INDEPENDENT_GAP_DISCREPANCY")
    duplicate = groups["DUPLICATE_LINE_FINDINGS"]
    if any(
        duplicate[key] != value
        for key, value in {
            "STANDARD_ROWS_WITH_EXACT_DUPLICATE_CLEAN_LINES": 56,
            "NATIVE_ROWS_WITH_EXACT_DUPLICATE_CLEAN_LINES": 55,
            "STANDARD_EXCESS_EXACT_DUPLICATE_CLEAN_VALUES": 59,
            "NATIVE_EXCESS_EXACT_DUPLICATE_CLEAN_VALUES": 58,
        }.items()
    ):
        fail("INDEPENDENT_DUPLICATE_DISCREPANCY")
    if groups["STANDARD_CANDIDATE_LENGTH_CODEPOINTS"] != {
        "COUNT": 34822,
        "MIN": 1,
        "MEDIAN": 38,
        "MEAN_MILLI": 4841960,
        "P95_NEAREST_RANK": 88,
        "P99_NEAREST_RANK": 117,
        "MAX": 25920495,
    }:
        fail("INDEPENDENT_STANDARD_LENGTH_DISCREPANCY")
    if groups["NATIVE_CANDIDATE_LENGTH_CODEPOINTS"] != {
        "COUNT": 34925,
        "MIN": 1,
        "MEDIAN": 25,
        "MEAN_MILLI": 29781,
        "P95_NEAREST_RANK": 62,
        "P99_NEAREST_RANK": 83,
        "MAX": 21027,
    }:
        fail("INDEPENDENT_NATIVE_LENGTH_DISCREPANCY")


def compare_development(
    stage04_root: Path,
    stage05_root: Path,
    stage04_artifacts: list[dict[str, Any]],
    stage05_artifacts: list[dict[str, Any]],
    database: sqlite3.Connection,
    fixed_digests: Mapping[bytes, str],
    fixed_columns: tuple[str, ...],
) -> tuple[Metrics, str, str, str, pa.Schema, set[bytes], int]:
    if len(stage04_artifacts) != len(stage05_artifacts):
        fail("SHARD_COUNT_MISMATCH")
    metrics = Metrics()
    input_identity = IdentityHasher.create()
    output_identity = IdentityHasher.create()
    derived_digest = hashlib.sha256(DERIVED_STREAM_DOMAIN)
    found_fixed: set[bytes] = set()
    duplicate_identities = 0
    observed_schema: pa.Schema | None = None
    for sequence, (left_raw, right_raw) in enumerate(
        zip(stage04_artifacts, stage05_artifacts, strict=True), start=1
    ):
        if left_raw.get("row_count") != right_raw.get("row_count"):
            fail("SHARD_ROW_TOPOLOGY_MISMATCH")
        left_path = verify_artifact(stage04_root, left_raw, sequence)
        right_path = verify_artifact(stage05_root, right_raw, sequence)
        left_file = pq.ParquetFile(left_path, page_checksum_verification=True)
        right_file = pq.ParquetFile(right_path, page_checksum_verification=True)
        left_schema = left_file.schema_arrow.remove_metadata()
        right_schema = right_file.schema_arrow.remove_metadata()
        if observed_schema is None:
            observed_schema = right_schema
        elif not observed_schema.equals(right_schema, check_metadata=False):
            fail("STAGE05_SCHEMA_DRIFT")
        if len(right_schema) != len(left_schema) + 10:
            fail("STAGE05_SCHEMA_WIDTH_MISMATCH")
        if not pa.schema(list(right_schema)[: len(left_schema)]).equals(left_schema):
            fail("UPSTREAM_SCHEMA_PRESERVATION_FAILURE")
        expected_fields = (
            *(
                pa.field(name, pa.string(), nullable=False)
                for name in DERIVED_COLUMNS[:4]
            ),
            pa.field(DERIVED_COLUMNS[4], pa.bool_(), nullable=False),
            pa.field(DERIVED_COLUMNS[5], pa.bool_(), nullable=False),
            pa.field(DERIVED_COLUMNS[6], pa.uint8(), nullable=False),
            pa.field(DERIVED_COLUMNS[7], pa.uint8(), nullable=False),
            pa.field(DERIVED_COLUMNS[8], pa.string(), nullable=False),
            pa.field(DERIVED_COLUMNS[9], pa.string(), nullable=False),
        )
        if tuple(right_schema)[-10:] != expected_fields:
            fail("STAGE05_DERIVED_SCHEMA_MISMATCH")
        for left_batch, right_batch in aligned_batches(
            batches(left_file, batch_size=997), batches(right_file, batch_size=613)
        ):
            if any(
                right_batch.column(index).null_count
                for index in range(right_batch.num_columns)
            ):
                fail("STAGE05_NULL_VALUE")
            for index in range(left_batch.num_columns):
                if not left_batch.column(index).equals(right_batch.column(index)):
                    fail("UPSTREAM_VALUE_OR_ORDER_MISMATCH")
            left_ids = left_batch.column(
                left_batch.schema.get_field_index("stable_source_row_id_v1")
            )
            right_ids = right_batch.column(
                right_batch.schema.get_field_index("stable_source_row_id_v1")
            )
            input_identity.update(left_ids)
            output_identity.update(right_ids)
            for row_index in range(right_batch.num_rows):
                identity = right_ids[row_index].as_py()
                if not isinstance(identity, bytes) or len(identity) != 32:
                    fail("STABLE_IDENTITY_INVALID")
                before = database.total_changes
                database.execute(
                    "INSERT OR IGNORE INTO identities(value) VALUES (?)", (identity,)
                )
                duplicate_identities += int(database.total_changes == before)

                def lines(names: tuple[str, ...]) -> tuple[str, str, str, str]:
                    values = tuple(
                        named_column(right_batch, name)[row_index].as_py()
                        for name in names
                    )
                    if len(values) != 4 or any(
                        not isinstance(value, str) for value in values
                    ):
                        fail("ADDRESS_LINE_TYPE_MISMATCH")
                    return cast(tuple[str, str, str, str], values)

                sc_lines, nc_lines = lines(CLEAN_STANDARD), lines(CLEAN_NATIVE)
                sl_lines, nl_lines = lines(LOWER_STANDARD), lines(LOWER_NATIVE)
                sc, nc = reconstruct(sc_lines), reconstruct(nc_lines)
                sl, nl = reconstruct(sl_lines), reconstruct(nl_lines)
                expected: tuple[object, ...] = (
                    sc.candidate,
                    nc.candidate,
                    sl.candidate,
                    nl.candidate,
                    sl.available,
                    nl.available,
                    sl.count,
                    nl.count,
                    sl.mask,
                    nl.mask,
                )
                observed = tuple(
                    named_column(right_batch, name)[row_index].as_py()
                    for name in DERIVED_COLUMNS
                )
                if observed != expected:
                    fail("RECONSTRUCTION_OR_AUDIT_MISMATCH")
                if (
                    reconstruct((sl.candidate, "", "", "")).candidate != sl.candidate
                    or reconstruct((nl.candidate, "", "", "")).candidate != nl.candidate
                ):
                    fail("IDEMPOTENCE_MISMATCH")
                observe_representation(
                    metrics.standard, sc_lines, sl_lines, sc, sl, database, "STANDARD"
                )
                observe_representation(
                    metrics.native, nc_lines, nl_lines, nc, nl, database, "NATIVE"
                )
                if sl.available and nl.available:
                    metrics.relationship["BOTH"] += 1
                    metrics.both_candidates[
                        "EXACT_EQUAL_CANONICAL"
                        if sl.candidate == nl.candidate
                        else "DIFFERENT"
                    ] += 1
                    metrics.both_counts[
                        "SAME_LINE_COUNT"
                        if sl.count == nl.count
                        else "DIFFERENT_LINE_COUNT"
                    ] += 1
                elif sl.available:
                    metrics.relationship["STANDARD_ONLY"] += 1
                elif nl.available:
                    metrics.relationship["NATIVE_ONLY"] += 1
                else:
                    metrics.relationship["NO_REPRESENTATION"] += 1
                derived_digest.update(identity)
                for value in expected:
                    encode_value(derived_digest, value)
                if identity in fixed_digests:
                    if (
                        identity in found_fixed
                        or row_digest(right_batch, row_index, fixed_columns)
                        != fixed_digests[identity]
                    ):
                        fail("FIXED_REVIEW_VALUE_MISMATCH")
                    found_fixed.add(identity)
                metrics.rows += 1
    if observed_schema is None:
        fail("STAGE05_SCHEMA_MISSING")
    database.commit()
    return (
        metrics,
        input_identity.hexdigest(),
        output_identity.hexdigest(),
        derived_digest.hexdigest(),
        observed_schema,
        found_fixed,
        duplicate_identities,
    )


def repeat_derivation_digest(
    stage04_root: Path, artifacts: list[dict[str, Any]], batch_size: int
) -> str:
    digest = hashlib.sha256(DERIVED_STREAM_DOMAIN)
    rows = 0
    for sequence, raw in enumerate(artifacts, start=1):
        path = verify_artifact(stage04_root, raw, sequence)
        parquet = pq.ParquetFile(path, page_checksum_verification=True)
        for batch in batches(parquet, batch_size=batch_size):
            ids = batch.column(batch.schema.get_field_index("stable_source_row_id_v1"))
            for row_index in range(batch.num_rows):
                identity = ids[row_index].as_py()
                if not isinstance(identity, bytes):
                    fail("STABLE_IDENTITY_INVALID")
                values: list[object] = []
                for clean_names, lower_names in (
                    (CLEAN_STANDARD, LOWER_STANDARD),
                    (CLEAN_NATIVE, LOWER_NATIVE),
                ):
                    clean_lines = cast(
                        tuple[str, str, str, str],
                        tuple(
                            named_column(batch, name)[row_index].as_py()
                            for name in clean_names
                        ),
                    )
                    lower_lines = cast(
                        tuple[str, str, str, str],
                        tuple(
                            named_column(batch, name)[row_index].as_py()
                            for name in lower_names
                        ),
                    )
                    clean, lower = reconstruct(clean_lines), reconstruct(lower_lines)
                    values.extend(
                        (
                            clean.candidate,
                            lower.candidate,
                            lower.available,
                            lower.count,
                            lower.mask,
                        )
                    )
                expected = (
                    values[0],
                    values[5],
                    values[1],
                    values[6],
                    values[2],
                    values[7],
                    values[3],
                    values[8],
                    values[4],
                    values[9],
                )
                digest.update(identity)
                for value in expected:
                    encode_value(digest, value)
                rows += 1
    if rows != EXPECTED_ROWS:
        fail("REPEAT_DERIVATION_ROW_COUNT_MISMATCH")
    return digest.hexdigest()


def endpoint_type(character: str) -> str:
    category = unicodedata.category(character)
    if category.startswith("L"):
        return "LETTER"
    if category.startswith("N"):
        return "DIGIT" if character.isdecimal() else "NUMBER"
    if category.startswith("P"):
        return "PUNCTUATION"
    if category.startswith("M"):
        return "MARK"
    if category.startswith("S"):
        return "SYMBOL"
    if category.startswith("Z"):
        return "SEPARATOR"
    return "OTHER"


def script_class(value: str) -> str:
    scripts: set[str] = set()
    for character in value:
        if not character.isalpha():
            continue
        name = unicodedata.name(character, "")
        if "ARABIC" in name:
            scripts.add("ARABIC_PERSIAN")
        elif "CYRILLIC" in name:
            scripts.add("CYRILLIC")
        elif "LATIN" in name:
            scripts.add("LATIN")
        elif any(
            token in name
            for token in (
                "CJK",
                "IDEOGRAPH",
                "HIRAGANA",
                "KATAKANA",
                "HANGUL",
                "BOPOMOFO",
            )
        ):
            scripts.add("CJK_HANGUL")
        else:
            scripts.add("OTHER")
    if not scripts:
        return "COMMON_SYMBOL_ONLY" if value else "EMPTY"
    return next(iter(scripts)) if len(scripts) == 1 else "MIXED"


def excerpt(value: str, limit: int = 360) -> str:
    if len(value) <= limit:
        return value
    half = limit // 2
    return (
        f"{value[:half]} … [{len(value) - limit} code points omitted] … {value[-half:]}"
    )


def boundary_class(predecessor: str, successor: str) -> str:
    return f"{endpoint_type(predecessor[-1])}_TO_{endpoint_type(successor[0])}"


def punctuation_detail(character: str) -> str:
    category = unicodedata.category(character)
    if character == ",":
        return "ASCII_COMMA"
    if character == ";":
        return "ASCII_SEMICOLON"
    if character == "/":
        return "ASCII_SLASH"
    if character == "-" or category == "Pd":
        return "HYPHEN_OR_DASH"
    if category == "Ps":
        return "OPEN_PUNCTUATION"
    if category == "Pe":
        return "CLOSE_PUNCTUATION"
    if category.startswith("P"):
        return "OTHER_PUNCTUATION"
    return endpoint_type(character)


@dataclass(slots=True)
class ReviewRow:
    order: int
    stable_id: bytes
    reasons: set[str]
    scripts: set[str]
    standard_clean: tuple[str, str, str, str]
    native_clean: tuple[str, str, str, str]


def analyze_fixed_review(
    review: pa.Table,
) -> tuple[dict[str, Any], list[ReviewRow], str]:
    rows: list[ReviewRow] = []
    ordinary: list[ReviewRow] = []
    boundary_classes: Counter[str] = Counter()
    line_end_classes: Counter[str] = Counter()
    line_start_classes: Counter[str] = Counter()
    line_end_details: Counter[str] = Counter()
    line_start_details: Counter[str] = Counter()
    script_counts: Counter[str] = Counter()
    changed_rows = 0
    changed_representations = 0
    standard_multiline = 0
    native_multiline = 0
    punctuation_rows = 0
    alphanumeric_rows = 0
    gap_rows = 0
    duplicate_rows = 0
    total_v1_v2_length_reduction = 0
    for index in range(EXPECTED_REVIEW_ROWS):
        order = int(review.column("review_order")[index].as_py())
        identity = review.column("stable_source_row_id_v1")[index].as_py()
        if not isinstance(identity, bytes):
            fail("FIXED_REVIEW_IDENTITY_INVALID")
        standard = cast(
            tuple[str, str, str, str],
            tuple(review.column(name)[index].as_py() for name in CLEAN_STANDARD),
        )
        native = cast(
            tuple[str, str, str, str],
            tuple(review.column(name)[index].as_py() for name in CLEAN_NATIVE),
        )
        reasons: set[str] = set()
        scripts: set[str] = set()
        row_punctuation = False
        row_alphanumeric = False
        row_changed = False
        for label, values in (("STANDARD", standard), ("NATIVE", native)):
            reconstruction = reconstruct(values)
            nonempty = tuple(value for value in values if value != "")
            if reconstruction.count > 1:
                row_changed = True
                changed_representations += 1
                total_v1_v2_length_reduction += reconstruction.count - 1
                if label == "STANDARD":
                    standard_multiline += 1
                else:
                    native_multiline += 1
                current_script = script_class(reconstruction.candidate)
                scripts.add(current_script)
                script_counts[f"{label}_{current_script}"] += 1
            for predecessor, successor in zip(nonempty, nonempty[1:]):
                boundary_classes[boundary_class(predecessor, successor)] += 1
                end = endpoint_type(predecessor[-1])
                start = endpoint_type(successor[0])
                line_end_classes[end] += 1
                line_start_classes[start] += 1
                line_end_details[punctuation_detail(predecessor[-1])] += 1
                line_start_details[punctuation_detail(successor[0])] += 1
                if end == "PUNCTUATION" or start == "PUNCTUATION":
                    row_punctuation = True
                if end in {"LETTER", "DIGIT", "NUMBER"} and start in {
                    "LETTER",
                    "DIGIT",
                    "NUMBER",
                }:
                    row_alphanumeric = True
            if reconstruction.mask not in LEFT_PACKED_MASKS:
                reasons.add("GAP_PATTERN")
            if len(nonempty) != len(set(nonempty)):
                reasons.add("DUPLICATE_LINE")
        if order in PREVIOUS_QUESTIONABLE:
            reasons.add("PREVIOUS_V1_QUESTIONABLE")
        if row_punctuation:
            reasons.add("PUNCTUATION_SENSITIVE_BOUNDARY")
            punctuation_rows += 1
        if row_alphanumeric:
            reasons.add("ALPHANUMERIC_CONTINUATION_BOUNDARY")
            alphanumeric_rows += 1
        if any(reason == "GAP_PATTERN" for reason in reasons):
            gap_rows += 1
        if any(reason == "DUPLICATE_LINE" for reason in reasons):
            duplicate_rows += 1
        changed_rows += int(row_changed)
        row = ReviewRow(order, identity, reasons, scripts, standard, native)
        if reasons:
            rows.append(row)
        elif row_changed:
            ordinary.append(row)
    selected_by_order = {row.order: row for row in rows}
    ordinary.sort(
        key=lambda row: hashlib.sha256(
            b"SAFE_STAGE05_ORDINARY_SAMPLE_V1" + row.stable_id
        ).digest()
    )
    for row in ordinary[:32]:
        row.reasons.add("ORDINARY_MULTILINE_DETERMINISTIC_SAMPLE")
        selected_by_order[row.order] = row
    # Add deterministic script coverage after ReviewRow objects exist.
    for label in ("STANDARD", "NATIVE"):
        candidates: dict[str, list[ReviewRow]] = {}
        for row in [*rows, *ordinary]:
            values = row.standard_clean if label == "STANDARD" else row.native_clean
            candidate = reconstruct(values)
            if candidate.count > 1:
                candidates.setdefault(script_class(candidate.candidate), []).append(row)
        for current_script, candidates_for_script in candidates.items():
            ranked = sorted(
                candidates_for_script,
                key=lambda row: hashlib.sha256(
                    b"SAFE_STAGE05_SCRIPT_COVERAGE_V1"
                    + label.encode()
                    + current_script.encode()
                    + row.stable_id
                ).digest(),
            )
            for row in ranked[:2]:
                row.reasons.add(f"{label}_{current_script}_COVERAGE")
                selected_by_order[row.order] = row
    selected = sorted(selected_by_order.values(), key=lambda row: row.order)
    scope = hashlib.sha256(SCOPE_DOMAIN)
    encode_text(scope, TARGET_CANDIDATE_SHA)
    encode_digest(scope, EXPECTED_REVIEW_SUBSET)
    encode_digest(scope, STAGE05_REVIEW_ARTIFACT_SHA)
    encode_uint64(scope, len(selected))
    for row in selected:
        encode_uint64(scope, row.order)
        scope.update(b"\x04" + row.stable_id)
        for reason in sorted(row.reasons):
            encode_text(scope, reason)
    scope_fingerprint = scope.hexdigest()
    evidence = {
        "fixed_rows": EXPECTED_REVIEW_ROWS,
        "standard_multiline_rows": standard_multiline,
        "native_multiline_rows": native_multiline,
        "rows_with_any_v1_v2_change": changed_rows,
        "changed_representations": changed_representations,
        "punctuation_sensitive_rows": punctuation_rows,
        "alphanumeric_continuation_rows": alphanumeric_rows,
        "gap_pattern_rows": gap_rows,
        "duplicate_line_rows": duplicate_rows,
        "previous_v1_questionable_rows": len(PREVIOUS_QUESTIONABLE),
        "ordinary_multiline_sample_target": min(32, len(ordinary)),
        "selected_rows": len(selected),
        "v1_v2_length_reduction_codepoints": total_v1_v2_length_reduction,
        "direct_token_concatenations": 0,
        "separator_codepoint_mismatches": 0,
        "boundary_classes": dict(sorted(boundary_classes.items())),
        "line_end_unicode_classes": dict(sorted(line_end_classes.items())),
        "line_start_unicode_classes": dict(sorted(line_start_classes.items())),
        "line_end_boundary_details": dict(sorted(line_end_details.items())),
        "line_start_boundary_details": dict(sorted(line_start_details.items())),
        "multiline_script_classes": dict(sorted(script_counts.items())),
    }
    return evidence, selected, scope_fingerprint


def representation_html(label: str, lines: tuple[str, str, str, str]) -> str:
    result = reconstruct(lines)
    if not result.available:
        return f"<section><h4>{label}</h4><p>Unavailable (0000).</p></section>"
    occupied = [(index + 1, value) for index, value in enumerate(lines) if value != ""]
    rendered_lines = "".join(
        f"<li><b>line {position}</b> <span dir='auto'>{html.escape(excerpt(value))}</span></li>"
        for position, value in occupied
    )
    boundaries = "".join(
        "<li><span dir='auto'>"
        + html.escape(excerpt(left[-100:], 200))
        + "</span> <mark>␠ (U+0020)</mark> <span dir='auto'>"
        + html.escape(excerpt(right[:100], 200))
        + "</span> <small>["
        + boundary_class(left, right)
        + "]</small></li>"
        for left, right in zip(
            (value for _, value in occupied), (value for _, value in occupied[1:])
        )
    )
    v1 = ", ".join(value for _, value in occupied)
    return (
        f"<section><h4>{label}: mask {result.mask}, {result.count} contributors</h4>"
        f"<ol>{rendered_lines}</ol><p><b>v1 comma-space:</b> "
        f"<span dir='auto'>{html.escape(excerpt(v1))}</span></p>"
        f"<p><b>v2 U+0020:</b> <span dir='auto'>{html.escape(excerpt(result.candidate))}</span></p>"
        f"<p><b>v2 boundary-local views:</b></p><ul>{boundaries}</ul></section>"
    )


def human_review_html(
    selected: list[ReviewRow], scope_fingerprint: str, review_git_sha: str
) -> tuple[str, dict[str, Any]]:
    template = {
        "attestation_version": "stage05_v2_human_review_attestation_v1",
        "candidate_sha": TARGET_CANDIDATE_SHA,
        "implementation_sha": IMPLEMENTATION_SHA,
        "review_harness_sha": review_git_sha,
        "fixed_500_fingerprint": EXPECTED_REVIEW_SUBSET,
        "stage05_review_artifact_sha256": STAGE05_REVIEW_ARTIFACT_SHA,
        "qualitative_scope_fingerprint": scope_fingerprint,
        "selected_row_count": len(selected),
        "review_orders": [row.order for row in selected],
    }
    cards = []
    for row in selected:
        reasons = ", ".join(sorted(row.reasons))
        radios = "".join(
            f"<label><input type='radio' name='row-{row.order}' value='{value}'> {value}</label>"
            for value in CLASSIFICATIONS
        )
        cards.append(
            f"<article data-order='{row.order}'><h3>Review order {row.order}</h3>"
            f"<p><b>Selection reasons:</b> {html.escape(reasons)}</p>"
            + representation_html("STANDARD", row.standard_clean)
            + representation_html("NATIVE", row.native_clean)
            + f"<fieldset><legend>v2 row classification</legend>{radios}</fieldset></article>"
        )
    template_json = json.dumps(template, ensure_ascii=True, sort_keys=True)
    page = f"""<!doctype html>
<html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy"
content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>Protected Stage 5 v2 independent review</title>
<style>body{{font:15px system-ui;max-width:1100px;margin:auto;padding:24px}}article{{border:1px solid #aaa;padding:16px;margin:18px 0}}section{{background:#f6f6f6;padding:8px 14px;margin:8px 0}}label{{display:block;margin:5px}}mark{{padding:2px 5px}}.sticky{{position:sticky;top:0;background:white;border-bottom:1px solid #999;padding:10px;z-index:2}}span[dir=auto]{{unicode-bidi:plaintext}}</style></head>
<body><div class="sticky"><b>Protected offline review</b> — {len(selected)} rows.
Do not screenshot, paste, or transmit values. <span id="progress">0/{len(selected)}</span></div>
<h1>Stage 5 v2 U+0020 qualitative review</h1>
<p>Review every displayed standard/native boundary. Judge the v2 candidate, not whether
the upstream source content itself is elegant. Use QUESTIONABLE_BOUNDARY only when the
single space creates an unsupported or damaging boundary; QUESTIONABLE_ORDER only for
actual order damage; SEMANTIC_DAMAGE only for content meaning damage. Redundant source
content remains valid and must not be silently deduplicated.</p>
{"".join(cards)}
<p><label><input id="attested" type="checkbox"> I reviewed every displayed v2
standard/native boundary and classified every selected row.</label></p>
<button id="export">Export complete attestation JSON</button>
<script>const template={template_json};
function progress(){{let n=0;for(const order of template.review_orders){{if(document.querySelector(`input[name=row-${{order}}]:checked`))n++;}}document.getElementById('progress').textContent=`${{n}}/${{template.selected_row_count}}`;}}
document.addEventListener('change',progress);
document.getElementById('export').addEventListener('click',()=>{{const classifications=[];for(const order of template.review_orders){{const selected=document.querySelector(`input[name=row-${{order}}]:checked`);if(!selected){{alert(`Review order ${{order}} is unclassified.`);return;}}classifications.push({{review_order:order,classification:selected.value}});}}if(!document.getElementById('attested').checked){{alert('Complete the attestation checkbox.');return;}}const result={{...template,attested_complete:true,completed_at_utc:new Date().toISOString(),classifications}};delete result.review_orders;const blob=new Blob([JSON.stringify(result,null,2)+'\\n'],{{type:'application/json'}});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='stage05_v2_human_review_attestation.json';link.click();URL.revokeObjectURL(link.href);}});</script>
</body></html>"""
    return page, template


def verify_synthetic_edges() -> dict[str, int]:
    vectors = (
        (("", "", "", ""), ""),
        (("A", "", "", ""), "A"),
        (("", "B", "", ""), "B"),
        (("", "", "C", ""), "C"),
        (("", "", "", "D"), "D"),
        (("A", "B", "", ""), "A B"),
        (("A", "", "C", ""), "A C"),
        (("", "B", "", "D"), "B D"),
        (("A", "B", "C", "D"), "A B C D"),
        (("A", "A", "", ""), "A A"),
        (("A,", "B", "", ""), "A, B"),
        (("A;", "B", "", ""), "A; B"),
        (("A/", "B", "", ""), "A/ B"),
        (("A-", "B", "", ""), "A- B"),
        (("A(", "B)", "", ""), "A( B)"),
        (("A", ",B", "", ""), "A ,B"),
        (("Letter", "word", "", ""), "Letter word"),
        (("A", "7", "", ""), "A 7"),
        (("7", "A", "", ""), "7 A"),
        (("7", "8", "", ""), "7 8"),
        (("Cafe\u0301", "\u0301Suite", "", ""), "Cafe\u0301 \u0301Suite"),
        (("العربية", "خیابان آزادی", "", ""), "العربية خیابان آزادی"),
        (("МОСКВА", "УЛИЦА", "", ""), "МОСКВА УЛИЦА"),
        (("東京都", "新宿区", "", ""), "東京都 新宿区"),
        (("🏢", "7️⃣", "", ""), "🏢 7️⃣"),
    )
    for lines, expected in vectors:
        observed = reconstruct(lines)
        if observed.candidate != expected or observed.count != sum(
            value != "" for value in lines
        ):
            fail("SYNTHETIC_RECONSTRUCTION_FAILURE")
    giant = "東京-É-العربية-🏢" * 100_000
    one = reconstruct((giant, "", "", ""))
    four = reconstruct((giant, giant, giant, giant))
    if one.candidate != giant or four.candidate != " ".join((giant,) * 4):
        fail("GIANT_RECONSTRUCTION_FAILURE")
    for size in (1, 2, 3, 17, 2048):
        flattened = []
        for start in range(0, len(vectors), size):
            flattened.extend(
                reconstruct(lines).candidate
                for lines, _ in vectors[start : start + size]
            )
        if flattened != [expected for _, expected in vectors]:
            fail("SYNTHETIC_BATCH_DETERMINISM_FAILURE")
    return {
        "vectors": len(vectors),
        "giant_line_codepoints": len(giant),
        "four_giant_candidate_codepoints": len(four.candidate),
        "batch_sizes": 5,
    }


def write_outputs(
    output: Path, aggregate: dict[str, Any], page: str, template: dict[str, Any]
) -> None:
    if output.exists() or output.is_symlink():
        fail("REVIEW_OUTPUT_COLLISION")
    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent.chmod(0o700)
    require_directory(parent)
    temporary = parent / f".{output.name}.{os.getpid()}.in_progress"
    if temporary.exists() or temporary.is_symlink():
        fail("REVIEW_TEMPORARY_COLLISION")
    temporary.mkdir(mode=0o700)
    files = {
        "stage05_independent_review.json": json.dumps(
            aggregate, ensure_ascii=True, allow_nan=False, indent=2, sort_keys=True
        )
        + "\n",
        "stage05_v2_human_review.html": page,
        "stage05_v2_human_attestation_template.json": json.dumps(
            template, ensure_ascii=True, allow_nan=False, indent=2, sort_keys=True
        )
        + "\n",
    }
    hashes: dict[str, str] = {}
    for name, payload in files.items():
        path = temporary / name
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        hashes[name] = sha256_file(path)
    success = {
        "status": aggregate["status"],
        "review_target_sha": TARGET_CANDIDATE_SHA,
        "review_harness_git_sha": aggregate["review_harness_git_sha"],
        "slurm_job_id": aggregate["slurm_job_id"],
        "artifacts": hashes,
        "qualitative_scope_fingerprint": aggregate["qualitative_review"][
            "scope_fingerprint"
        ],
        "selected_row_count": aggregate["qualitative_review"]["structural_evidence"][
            "selected_rows"
        ],
        "human_review_required": True,
    }
    success_path = temporary / "_SUCCESS.json"
    descriptor = os.open(success_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(
            json.dumps(success, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
        )
        stream.flush()
        os.fsync(stream.fileno())
    directory_fd = os.open(temporary, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    os.replace(temporary, output)
    parent_fd = os.open(parent, os.O_RDONLY)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--stage04-root", required=True, type=Path)
    parser.add_argument("--stage05-root", required=True, type=Path)
    parser.add_argument("--stage05-input-binding", required=True, type=Path)
    parser.add_argument("--fixed-review-root", required=True, type=Path)
    parser.add_argument("--stage05-review-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--review-git-sha", required=True)
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    verify_runtime()
    paths = (
        args.repository,
        args.stage04_root,
        args.stage05_root,
        args.stage05_input_binding,
        args.fixed_review_root,
        args.stage05_review_root,
        args.output,
    )
    reject_holdout(*paths)
    for directory in (
        args.repository,
        args.stage04_root,
        args.stage05_root,
        args.fixed_review_root,
        args.stage05_review_root,
    ):
        require_directory(directory)
    binding = verify_binding(args.stage05_input_binding)
    stage04, stage05, stage04_artifacts, stage05_artifacts = validate_manifests(
        args.stage04_root, args.stage05_root, binding
    )
    fixed, review, fixed_digests, fixed_columns = load_fixed_review(
        args.fixed_review_root, args.stage05_review_root
    )
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output.parent.chmod(0o700)
    require_directory(args.output.parent)
    database_path = args.output.parent / f".{args.output.name}.{os.getpid()}.sqlite3"
    if database_path.exists() or database_path.is_symlink():
        fail("REVIEW_DATABASE_COLLISION")
    database = sqlite3.connect(database_path)
    database_path.chmod(0o600)
    database.execute(
        "CREATE TABLE lengths (representation TEXT NOT NULL, codepoints INTEGER NOT NULL)"
    )
    database.execute("CREATE TABLE identities (value BLOB PRIMARY KEY) WITHOUT ROWID")
    try:
        (
            metrics,
            input_identity,
            output_identity,
            first_digest,
            observed_schema,
            found_fixed,
            duplicate_ids,
        ) = compare_development(
            args.stage04_root,
            args.stage05_root,
            stage04_artifacts,
            stage05_artifacts,
            database,
            fixed_digests,
            fixed_columns,
        )
        standard_lengths = length_statistics(database, "STANDARD")
        native_lengths = length_statistics(database, "NATIVE")
    finally:
        database.close()
        if database_path.exists() and not database_path.is_symlink():
            database_path.unlink()
    if (
        metrics.rows != EXPECTED_ROWS
        or duplicate_ids
        or found_fixed != set(fixed_digests)
    ):
        fail("ROW_OR_FIXED_IDENTITY_INTEGRITY_FAILURE")
    if (
        input_identity != EXPECTED_ORDERED_IDENTITY
        or output_identity != EXPECTED_ORDERED_IDENTITY
    ):
        fail("ORDERED_IDENTITY_MISMATCH")
    schema_fingerprint = recompute_schema_fingerprint(observed_schema)
    logical_fingerprint = recompute_logical(binding, schema_fingerprint)
    if (
        schema_fingerprint != EXPECTED_STAGE05_SCHEMA
        or logical_fingerprint != EXPECTED_STAGE05_LOGICAL
    ):
        fail("INDEPENDENT_FINGERPRINT_MISMATCH")
    groups = metric_groups(metrics, standard_lengths, native_lengths)
    expected_metric_checks(groups)
    if groups != stage05.get("development_metrics"):
        fail("MANIFEST_METRIC_DISCREPANCY")
    repeated_digest = repeat_derivation_digest(
        args.stage04_root, stage04_artifacts, 137
    )
    if first_digest != repeated_digest:
        fail("BATCH_OR_REPEAT_DETERMINISM_MISMATCH")
    structural, selected, scope_fingerprint = analyze_fixed_review(review)
    page, template = human_review_html(selected, scope_fingerprint, args.review_git_sha)
    synthetic = verify_synthetic_edges()
    aggregate = {
        "status": "STAGE_5_INDEPENDENT_STRUCTURAL_VERIFICATION_PASS_HUMAN_REVIEW_REQUIRED",
        "reviewed_main_base_sha": BASE_SHA,
        "review_target_sha": TARGET_CANDIDATE_SHA,
        "authoritative_implementation_sha": IMPLEMENTATION_SHA,
        "review_harness_git_sha": args.review_git_sha,
        "slurm_job_id": os.environ["SLURM_JOB_ID"],
        "runtime": {
            "python": platform.python_version(),
            "unicode": unicodedata.unidata_version,
            "pyarrow": pa.__version__,
        },
        "fingerprints": {
            "stage04_manifest": STAGE04_MANIFEST_SHA,
            "stage05_manifest": STAGE05_MANIFEST_SHA,
            "stage05_input_binding": STAGE05_INPUT_BINDING_SHA,
            "stage05_schema": schema_fingerprint,
            "stage05_logical": logical_fingerprint,
            "ordered_identity": output_identity,
            "benchmark": EXPECTED_BENCHMARK,
            "fixed_review_subset": EXPECTED_REVIEW_SUBSET,
            "stage05_review_artifact": STAGE05_REVIEW_ARTIFACT_SHA,
        },
        "development": {
            "rows_in": metrics.rows,
            "rows_out": metrics.rows,
            "dropped": 0,
            "added": 0,
            "duplicate_identities": duplicate_ids,
            "incoming_stage04_columns_compared": len(observed_schema) - 10,
            "upstream_mismatches": 0,
            "reconstruction_mismatches": 0,
            "audit_mismatches": 0,
            "lowercase_consistency_mismatches": 0,
            "ordered_identity_mismatches": 0,
            "fixed_review_value_mismatches": 0,
            "metric_groups": groups,
        },
        "determinism": {
            "first_derived_stream_sha256": first_digest,
            "repeat_derived_stream_sha256": repeated_digest,
            "second_pass_batch_rows": 137,
            "mismatches": 0,
        },
        "synthetic_adversarial": synthetic,
        "qualitative_review": {
            "scope_fingerprint": scope_fingerprint,
            "structural_evidence": structural,
            "human_review_required": True,
            "human_review_completed": False,
        },
        "privacy": {
            "holdout_accessed": False,
            "row_values_emitted": False,
            "stable_identities_emitted": False,
            "protected_surface_owner_only": True,
        },
    }
    write_outputs(args.output, aggregate, page, template)
    return aggregate


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = run(args)
    except ReviewFailure as error:
        print(f"review_error={error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"review_error=UNEXPECTED_{type(error).__name__}", file=sys.stderr)
        return 1
    evidence = result["qualitative_review"]["structural_evidence"]
    print(f"status={result['status']}")
    print(f"review_target_sha={TARGET_CANDIDATE_SHA}")
    print(f"review_harness_git_sha={args.review_git_sha}")
    print(f"slurm_job_id={os.environ.get('SLURM_JOB_ID', '')}")
    print("development_rows=35000")
    print("upstream_mismatches=0")
    print("reconstruction_mismatches=0")
    print("audit_mismatches=0")
    print("duplicate_identities=0")
    print(f"fixed500_v2_changed_rows={evidence['rows_with_any_v1_v2_change']}")
    print(f"qualitative_selected_rows={evidence['selected_rows']}")
    print("human_review_required=YES")
    print("holdout_accessed=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
