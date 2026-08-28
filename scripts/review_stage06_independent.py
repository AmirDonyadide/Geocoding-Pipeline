#!/usr/bin/env python3
"""Independent, privacy-safe Stage 6 DEVELOPMENT verifier.

This script intentionally does not import the Stage 6 implementation. It
streams the accepted Stage 5 and candidate Stage 6 bundles, independently
recomputes content IDs and fingerprints, rebuilds occurrence groups in a
disk-backed DuckDB database, and emits aggregate evidence only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import resource
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, cast

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq


BASE_SHA = "58019837b8a9474f3e5b6d5b00e96b4210ae84cc"
TARGET_CANDIDATE_SHA = "03bab36bc2f45d218eb289abff0ad2aed72cffd8"
IMPLEMENTATION_SHA = "f39047cc825d9baef91915478f657aefecc86d4c"
DESIGN_SHA = "9f9a5a07a2dd3825c895b23406311651e5480324"
AUTHORITATIVE_JOB = "1759819"

STAGE05_CONTRACT = "stage05_address_reconstruction_contract_v2"
STAGE05_PROFILE = "stage05_address_reconstruction_profile_v2"
STAGE05_SCHEMA = "63d4cdb3707eda65c67cc5196891fa5005adce2b12eb7109554793c48c5303c3"
STAGE05_LOGICAL = "ba5829621fc15347d7cd4e168a48587bab896cd0be98924627876ae853dfaff2"
STAGE05_INPUT_BINDING = (
    "7e68c33f7daa482b442eca82c00c6904ec5e38bec1b3fc598d5be4d52a6bcb9f"
)
STAGE05_MANIFEST = "fd945163e3be0242c43b98972350904631279cb99f366baadb0a3094ab6a1fc5"
ORDERED_IDENTITY = "fe2a4758582c1880d2b5c62dfc5c587d865e05d13033af9f5e8208b58e2a0487"
BENCHMARK = "014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf"
FIXED_500 = "014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52"
FIXED_MANIFEST = "1fa69ce953cb6e4ef70d611e372ab8e8565b8e9aa577d00292a20219dcdd5c92"
FIXED_IDENTITIES = "ffe7b51b67b2db1f64dcb202ab28fd22f32cd863de2e2cb7a7d112f1244f8779"

STAGE06_CONTRACT = "stage06_early_exact_deduplication_contract_v1"
STAGE06_PROFILE = "stage06_early_exact_deduplication_profile_v1"
STAGE06_INPUT_BINDING_VERSION = "stage06_input_binding_v1"
STAGE06_ROW_MAP_SCHEMA_VERSION = "stage06_row_map_schema_v1"
STAGE06_REGISTRY_SCHEMA_VERSION = "stage06_unique_candidate_registry_schema_v1"
STAGE06_SCHEMA_VERSION = "stage06_early_exact_deduplication_schema_v1"
STAGE06_CANDIDATE_ID_VERSION = "stage06_exact_candidate_id_v1"
STAGE06_CANDIDATE_ID_DOMAIN = b"safe_geocoding_pipeline:stage06_exact_candidate_id_v1\0"
STAGE06_SCHEMA = "9c07b7a4c3f7a5c43ad457dcf6f7fe3fd746d54d82a731139905b30828b6c9ce"
STAGE06_CONTRACT_FINGERPRINT = (
    "d4fc73d7fabb734bb0996db4d5c02d6002131179259404eaab20699dacfba8c0"
)
STAGE06_ROW_MAP_LOGICAL = (
    "1ff9067c521ae93d28c300d7120a03c39681ce7830bf23b6619e2ca6129a4fe1"
)
STAGE06_REGISTRY_LOGICAL = (
    "6d6d937472c44661e0bff522affb0ed39b41610fa174df3bde36145f749a6c50"
)
STAGE06_LOGICAL = "2f6379c0cd5dc9654c03895cae6fdd48f3a7af528158c33e44d2030c816640b6"
STAGE06_INPUT_BINDING = (
    "6ba224d6d24c3631aae8aac69f4a362bb054f01d9e3d09327ec6b0fdd85a0e7d"
)
STAGE06_MANIFEST = "e1da7b8ef04b65b1ece8e710720b57a8536841766fcf9de641f889b42eadd241"
STAGE06_SUCCESS = "1373abafccd619b6f05aa61181bf7909e54d532ecdebc87ade9f79c1e6e35002"
STAGE06_ROW_MAP_ARTIFACT = (
    "a17a1ac8e9574ad6cb6199660dfbf33918e345b1a15168d03b254761250d8bb2"
)
STAGE06_REGISTRY_ARTIFACT = (
    "fe5a36617de811cf2c0d56595e73e4189cd16ba632a88c6f8b53f9be03ecb325"
)
STAGE06_REVIEW_MANIFEST = (
    "1eda47b375a432788e5f8366ce73e5364fdf97efac1742bd95981a15b87c0fb1"
)
STAGE06_REVIEW_ARTIFACT = (
    "624978c807fce7f9a76383b76d88e52eb85fa9bfbd5c41ced071d4a40c079190"
)
STAGE06_REVIEW_SUCCESS = (
    "a10808d03187667248ab28b959df219f83cc58814d6516ed7685c1896a07007c"
)

EXPECTED_ROWS = 35_000
EXPECTED_STANDARD = 34_822
EXPECTED_NATIVE = 34_925
EXPECTED_OCCURRENCES = 69_747
EXPECTED_UNIQUE = 51_779
EXPECTED_DUPLICATES = 17_968
EXPECTED_SINGLETONS = 33_889
EXPECTED_DUPLICATE_GROUPS = 17_890
EXPECTED_MULTI_SOURCE_GROUPS = 41
EXPECTED_SAME_ROW_EQUAL = 17_913
EXPECTED_STANDARD_ONLY = 16_899
EXPECTED_NATIVE_ONLY = 16_998
EXPECTED_BOTH = 17_882
EXPECTED_CLEAN_VARIANTS = 123
EXPECTED_MAX_GROUP = 8
EXPECTED_MAX_STANDARD_CODEPOINTS = 25_920_495
EXPECTED_STANDARD_MILLION = 23
EXPECTED_GROUP_DISTRIBUTION = {
    "1": 33_889,
    "2": 17_855,
    "3": 5,
    "4": 24,
    "5": 1,
    "6": 4,
    "8": 1,
}
EXPECTED_LENGTH_BUCKETS = {
    "1_to_24": (19_170, 24_853, 5_619, 5_683),
    "25_to_49": (20_807, 29_763, 8_944, 8_956),
    "50_to_99": (10_882, 14_140, 3_256, 3_258),
    "100_to_1023": (862, 933, 71, 71),
    "1024_to_65535": (17, 17, 0, 0),
    "65536_to_999999": (18, 18, 0, 0),
    "1000000_or_more": (23, 23, 0, 0),
}

EXPECTED_FIXED_ROWS = 500
EXPECTED_FIXED_OCCURRENCES = 937
EXPECTED_FIXED_UNIQUE = 613
EXPECTED_FIXED_DUPLICATES = 324
EXPECTED_FIXED_SAME_ROW_EQUAL = 323

DATA_ROOT = Path("/work/footprint/donyadidegan/safe_geocoding_pipeline")
EXPECTED_PYTHON = (3, 14, 3)
EXPECTED_PYARROW = "25.0.0"
EXPECTED_DUCKDB = "1.5.5"
HASH_CHUNK_CODEPOINTS = 262_139
TARGET_BATCH_BYTES = 64 * 1024 * 1024

ROW_ID_COLUMNS = (
    "stage06_standard_exact_candidate_id",
    "stage06_native_exact_candidate_id",
)
REGISTRY_COLUMNS = (
    "stage06_exact_candidate_id",
    "stage06_candidate_lower",
    "stage06_occurrence_count",
    "stage06_standard_occurrence_count",
    "stage06_native_occurrence_count",
)

SCHEMA_DOMAIN = b"SAFE_STAGE06_COMBINED_ARROW_SCHEMA_V1"
CONTRACT_DOMAIN = b"SAFE_STAGE06_SCIENTIFIC_CONTRACT_V1"
ROW_LOGICAL_DOMAIN = b"SAFE_STAGE06_ROW_MAP_LOGICAL_V1"
REGISTRY_LOGICAL_DOMAIN = b"SAFE_STAGE06_REGISTRY_LOGICAL_V1"
DATASET_LOGICAL_DOMAIN = b"SAFE_STAGE06_LOGICAL_DATASET_V1"
ORDERED_IDENTITY_DOMAIN = b"SAFE_STAGE03_ORDERED_STABLE_IDENTITIES_V1"
REVIEW_SUBSET_DOMAIN = b"SAFE_DEVELOPMENT_REVIEW_SUBSET_V1"
REVIEW_ID_DOMAIN = b"SAFE_DEVELOPMENT_REVIEW_ID_V1"

TYPE_UINT64 = b"\x01"
TYPE_TEXT = b"\x02"
TYPE_DIGEST = b"\x03"
TYPE_BYTES = b"\x04"
NULL_ID = b"\x00"
PRESENT_ID = b"\x01"
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class ReviewFailure(RuntimeError):
    """Privacy-safe independent-review failure."""


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


def require_digest(value: object, expected: str) -> None:
    if (
        not isinstance(value, str)
        or value != expected
        or SHA_RE.fullmatch(value) is None
    ):
        fail("DIGEST_MISMATCH")


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


def reject_holdout(*paths: Path) -> None:
    if any("holdout" in part.casefold() for path in paths for part in path.parts):
        fail("HOLDOUT_ACCESS_PROHIBITED")


def ensure_new_output(path: Path) -> None:
    if path.exists() or path.is_symlink():
        fail("OUTPUT_COLLISION")


def encode_uint64(digest: Any, value: int) -> None:
    if isinstance(value, bool) or not 0 <= value <= 0xFFFF_FFFF_FFFF_FFFF:
        fail("INVALID_UINT64")
    digest.update(TYPE_UINT64 + struct.pack(">Q", value))


def encode_text(digest: Any, value: str) -> None:
    payload = value.encode("utf-8", errors="strict")
    digest.update(TYPE_TEXT + struct.pack(">Q", len(payload)) + payload)


def encode_digest(digest: Any, value: str) -> None:
    if SHA_RE.fullmatch(value) is None:
        fail("INVALID_DIGEST")
    digest.update(TYPE_DIGEST + bytes.fromhex(value))


def encode_bytes(digest: Any, value: bytes) -> None:
    digest.update(TYPE_BYTES + struct.pack(">Q", len(value)) + value)


def update_utf8(digest: Any, value: str, chunk_codepoints: int) -> None:
    for start in range(0, len(value), chunk_codepoints):
        digest.update(value[start : start + chunk_codepoints].encode("utf-8"))


def utf8_length(value: str, chunk_codepoints: int) -> int:
    return sum(
        len(value[start : start + chunk_codepoints].encode("utf-8"))
        for start in range(0, len(value), chunk_codepoints)
    )


def candidate_id(value: str, *, chunk_codepoints: int = HASH_CHUNK_CODEPOINTS) -> bytes:
    if not isinstance(value, str) or not value:
        fail("INVALID_AVAILABLE_CANDIDATE")
    digest = hashlib.sha256(STAGE06_CANDIDATE_ID_DOMAIN)
    update_utf8(digest, value, chunk_codepoints)
    return digest.digest()


class OrderedIdentityHasher:
    def __init__(self) -> None:
        self.digest = hashlib.sha256(ORDERED_IDENTITY_DOMAIN)
        self.rows = 0

    def update(self, values: pa.Array) -> None:
        if (
            not pa.types.is_fixed_size_binary(values.type)
            or values.type.byte_width != 32
            or values.null_count
        ):
            fail("STABLE_IDENTITY_TYPE_MISMATCH")
        for value in values:
            raw = value.as_py()
            if not isinstance(raw, bytes) or len(raw) != 32:
                fail("STABLE_IDENTITY_VALUE_MISMATCH")
            self.digest.update(raw)
            self.rows += 1

    def hexdigest(self) -> str:
        copy = self.digest.copy()
        copy.update(b"\x00ROWS" + struct.pack(">Q", self.rows))
        return copy.hexdigest()


class RowMapLogicalHasher:
    def __init__(self, contract_fingerprint: str) -> None:
        self.digest = hashlib.sha256(ROW_LOGICAL_DOMAIN)
        self.digest.update(bytes.fromhex(contract_fingerprint))
        self.rows = 0

    def update(
        self, stable: bytes, standard: bytes | None, native: bytes | None
    ) -> None:
        self.digest.update(stable)
        for value in (standard, native):
            self.digest.update(NULL_ID if value is None else PRESENT_ID + value)
        self.rows += 1

    def hexdigest(self) -> str:
        copy = self.digest.copy()
        copy.update(b"\x00ROWS" + struct.pack(">Q", self.rows))
        return copy.hexdigest()


class RegistryLogicalHasher:
    def __init__(self, contract_fingerprint: str) -> None:
        self.digest = hashlib.sha256(REGISTRY_LOGICAL_DOMAIN)
        self.digest.update(bytes.fromhex(contract_fingerprint))
        self.rows = 0

    def update(
        self,
        value_id: bytes,
        text: str,
        total: int,
        standard: int,
        native: int,
    ) -> None:
        self.digest.update(value_id)
        self.digest.update(struct.pack(">Q", utf8_length(text, HASH_CHUNK_CODEPOINTS)))
        update_utf8(self.digest, text, HASH_CHUNK_CODEPOINTS)
        for value in (total, standard, native):
            self.digest.update(struct.pack(">Q", value))
        self.rows += 1

    def hexdigest(self) -> str:
        copy = self.digest.copy()
        copy.update(b"\x00ROWS" + struct.pack(">Q", self.rows))
        return copy.hexdigest()


def input_binding_payload() -> dict[str, str | int]:
    return {
        "stage06_input_binding_version": STAGE06_INPUT_BINDING_VERSION,
        "upstream_contract_version": STAGE05_CONTRACT,
        "upstream_profile_version": STAGE05_PROFILE,
        "upstream_logical_fingerprint": STAGE05_LOGICAL,
        "upstream_schema_fingerprint": STAGE05_SCHEMA,
        "upstream_input_binding_sha256": STAGE05_INPUT_BINDING,
        "upstream_manifest_sha256": STAGE05_MANIFEST,
        "upstream_ordered_identity_sha256": ORDERED_IDENTITY,
        "input_benchmark_fingerprint": BENCHMARK,
        "fixed_500_fingerprint": FIXED_500,
        "expected_row_count": EXPECTED_ROWS,
    }


def input_binding_sha256(payload: Mapping[str, object]) -> str:
    encoded = (
        json.dumps(
            payload, ensure_ascii=True, allow_nan=False, indent=2, sort_keys=True
        )
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def schema_fingerprint(stage05: pa.Schema, registry: pa.Schema) -> str:
    row_map = pa.schema(
        [
            *list(stage05.remove_metadata()),
            pa.field(ROW_ID_COLUMNS[0], pa.binary(32), nullable=True),
            pa.field(ROW_ID_COLUMNS[1], pa.binary(32), nullable=True),
        ]
    )
    digest = hashlib.sha256(SCHEMA_DOMAIN)
    encode_text(digest, STAGE06_SCHEMA_VERSION)
    for version, schema in (
        (STAGE06_ROW_MAP_SCHEMA_VERSION, row_map),
        (STAGE06_REGISTRY_SCHEMA_VERSION, registry.remove_metadata()),
    ):
        encode_text(digest, version)
        encode_uint64(digest, len(schema))
        for field in schema:
            encode_text(digest, field.name)
            encode_text(digest, str(field.type))
            encode_text(digest, str(field.nullable).lower())
    return digest.hexdigest()


def contract_fingerprint(schema_sha: str) -> str:
    binding = input_binding_payload()
    digest = hashlib.sha256(CONTRACT_DOMAIN)
    for value in (
        STAGE06_CONTRACT,
        STAGE06_PROFILE,
        STAGE06_SCHEMA_VERSION,
        STAGE06_CANDIDATE_ID_VERSION,
        "EXACT_UTF8_BYTES",
        "GLOBAL_STANDARD_NATIVE_ALL_SOURCE_ROWS",
        "NULL_ID_NO_OCCURRENCE_NO_REGISTRY_ROW",
        "ASCENDING_UNSIGNED_CANDIDATE_ID_BYTES",
        "ONE_UNIQUE_TWO_OCCURRENCES_TWO_MAPPINGS",
        "PRESERVE_UPSTREAM_EXCLUDE_FROM_KEY",
        "NO_TRIM_WHITESPACE_PUNCTUATION_OR_UNICODE_NORMALIZATION",
        "NO_PARSING_FUZZY_MATCHING_GEOGRAPHIC_LOGIC_OR_GEOCODING",
        STAGE05_CONTRACT,
        STAGE05_PROFILE,
    ):
        encode_text(digest, value)
    encode_bytes(digest, STAGE06_CANDIDATE_ID_DOMAIN)
    for value in (*ROW_ID_COLUMNS, *REGISTRY_COLUMNS):
        encode_text(digest, value)
    for value in (
        STAGE05_LOGICAL,
        STAGE05_SCHEMA,
        STAGE05_INPUT_BINDING,
        STAGE05_MANIFEST,
        ORDERED_IDENTITY,
        BENCHMARK,
        FIXED_500,
        schema_sha,
    ):
        encode_digest(digest, value)
    encode_uint64(digest, cast(int, binding["expected_row_count"]))
    return digest.hexdigest()


def dataset_logical(
    contract_sha: str,
    row_sha: str,
    registry_sha: str,
    rows: int,
    unique: int,
) -> str:
    digest = hashlib.sha256(DATASET_LOGICAL_DOMAIN)
    encode_digest(digest, contract_sha)
    encode_digest(digest, row_sha)
    encode_digest(digest, registry_sha)
    encode_uint64(digest, rows)
    encode_uint64(digest, unique)
    return digest.hexdigest()


def bounded_batches(
    parquet: pq.ParquetFile, *, batch_rows: int
) -> Iterator[pa.RecordBatch]:
    for row_group in range(parquet.metadata.num_row_groups):
        metadata = parquet.metadata.row_group(row_group)
        if metadata.num_rows < 1:
            fail("EMPTY_ROW_GROUP")
        bytes_per_row = max(1, metadata.total_byte_size // metadata.num_rows)
        adaptive = max(1, min(batch_rows, TARGET_BATCH_BYTES // bytes_per_row))
        yield from parquet.iter_batches(
            batch_size=adaptive, row_groups=[row_group], use_threads=False
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
        if left_batch is None:
            left_batch = next(left_iterator, None)
            left_offset = 0
        if right_batch is None:
            right_batch = next(right_iterator, None)
            right_offset = 0
        if left_batch is None or right_batch is None:
            if left_batch is None and right_batch is None:
                return
            fail("PAIRED_STREAM_LENGTH_MISMATCH")
        count = min(
            left_batch.num_rows - left_offset,
            right_batch.num_rows - right_offset,
        )
        if count < 1:
            fail("EMPTY_ALIGNED_BATCH")
        yield (
            left_batch.slice(left_offset, count),
            right_batch.slice(right_offset, count),
        )
        left_offset += count
        right_offset += count
        if left_offset == left_batch.num_rows:
            left_batch = None
        if right_offset == right_batch.num_rows:
            right_batch = None


def artifact_inventory(
    root: Path,
    manifest: Mapping[str, Any],
    key: str,
    *,
    expected_prefix: str | None = None,
) -> list[Path]:
    physical = manifest.get("physical_identity")
    if not isinstance(physical, dict) or not isinstance(physical.get(key), list):
        fail("ARTIFACT_INVENTORY_INVALID")
    paths: list[Path] = []
    for sequence, raw in enumerate(physical[key], start=1):
        if not isinstance(raw, dict):
            fail("ARTIFACT_IDENTITY_INVALID")
        relative = raw.get("relative_path")
        if not isinstance(relative, str):
            fail("ARTIFACT_PATH_INVALID")
        if expected_prefix is not None and relative != (
            f"{expected_prefix}/part-{sequence:06d}.parquet"
        ):
            fail("ARTIFACT_ORDER_INVALID")
        path = root / relative
        require_file(path)
        if path.stat(follow_symlinks=False).st_size != raw.get("size_bytes"):
            fail("ARTIFACT_SIZE_MISMATCH")
        if sha256_file(path) != raw.get("sha256"):
            fail("ARTIFACT_SHA256_MISMATCH")
        paths.append(path)
    if not paths:
        fail("ARTIFACT_INVENTORY_EMPTY")
    return paths


def observed_tree(root: Path) -> tuple[set[str], set[str]]:
    directories: set[str] = set()
    files: set[str] = set()
    for current_root, directory_names, file_names in os.walk(root, followlinks=False):
        current = Path(current_root)
        require_directory(current)
        for name in directory_names:
            path = current / name
            require_directory(path)
            directories.add(path.relative_to(root).as_posix())
        for name in file_names:
            path = current / name
            require_file(path)
            files.add(path.relative_to(root).as_posix())
    return directories, files


def verify_git(repository: Path, review_git_sha: str) -> None:
    actual = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if actual != review_git_sha or len(actual) != 40:
        fail("REVIEW_GIT_SHA_MISMATCH")
    if subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout:
        fail("REVIEW_WORKTREE_DIRTY")
    if (
        subprocess.run(
            ["git", "symbolic-ref", "-q", "HEAD"],
            cwd=repository,
            check=False,
            capture_output=True,
            text=True,
        ).returncode
        == 0
    ):
        fail("REVIEW_WORKTREE_NOT_DETACHED")
    for ancestor, descendant in (
        (BASE_SHA, TARGET_CANDIDATE_SHA),
        (DESIGN_SHA, IMPLEMENTATION_SHA),
        (IMPLEMENTATION_SHA, TARGET_CANDIDATE_SHA),
        (TARGET_CANDIDATE_SHA, review_git_sha),
    ):
        if subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=repository,
            check=False,
        ).returncode:
            fail("REVIEW_GIT_ANCESTRY_MISMATCH")
    changed = set(
        subprocess.run(
            ["git", "diff", "--name-only", f"{TARGET_CANDIDATE_SHA}..{review_git_sha}"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    )
    allowed = {
        "cluster/goethe_nhr/stage06_independent_review.sbatch",
        "scripts/review_stage06_independent.py",
    }
    if changed != allowed:
        fail("REVIEW_HARNESS_SCOPE_MISMATCH")


def verify_runtime() -> None:
    if sys.version_info[:3] != EXPECTED_PYTHON:
        fail("PYTHON_VERSION_MISMATCH")
    if pa.__version__ != EXPECTED_PYARROW:
        fail("PYARROW_VERSION_MISMATCH")
    if duckdb.__version__ != EXPECTED_DUCKDB:
        fail("DUCKDB_VERSION_MISMATCH")


def stage06_expected_metadata(
    contract_sha: str, schema_sha: str
) -> tuple[dict[bytes, bytes], dict[bytes, bytes]]:
    common = {
        b"stage06_contract_version": STAGE06_CONTRACT.encode(),
        b"stage06_profile_version": STAGE06_PROFILE.encode(),
        b"stage06_schema_fingerprint": schema_sha.encode(),
        b"stage06_contract_fingerprint": contract_sha.encode(),
        b"stage06_candidate_id_version": STAGE06_CANDIDATE_ID_VERSION.encode(),
        b"upstream_stage05_manifest_sha256": STAGE05_MANIFEST.encode(),
    }
    row = {
        **common,
        b"stage06_row_map_schema_version": STAGE06_ROW_MAP_SCHEMA_VERSION.encode(),
    }
    registry = {
        **common,
        b"stage06_registry_schema_version": STAGE06_REGISTRY_SCHEMA_VERSION.encode(),
        b"stage06_registry_order": b"ASCENDING_UNSIGNED_CANDIDATE_ID_BYTES",
    }
    return row, registry


def validate_manifests(
    stage05_root: Path,
    stage06_root: Path,
    fixed_root: Path,
    stage06_review_root: Path,
) -> tuple[list[Path], list[Path], list[Path], Path, Path]:
    for root in (stage05_root, stage06_root, fixed_root, stage06_review_root):
        require_directory(root)

    stage05_manifest_path = stage05_root / "stage05_manifest.json"
    stage06_manifest_path = stage06_root / "stage06_manifest.json"
    stage06_success_path = stage06_root / "_SUCCESS.json"
    fixed_manifest_path = fixed_root / "development_review_manifest.json"
    review_manifest_path = stage06_review_root / "stage06_review_manifest.json"
    review_success_path = stage06_review_root / "_SUCCESS.json"
    for path in (
        stage05_manifest_path,
        stage06_manifest_path,
        stage06_success_path,
        fixed_manifest_path,
        review_manifest_path,
        review_success_path,
    ):
        require_file(path)
    require_digest(sha256_file(stage05_manifest_path), STAGE05_MANIFEST)
    require_digest(sha256_file(stage06_manifest_path), STAGE06_MANIFEST)
    require_digest(sha256_file(stage06_success_path), STAGE06_SUCCESS)
    require_digest(sha256_file(fixed_manifest_path), FIXED_MANIFEST)
    require_digest(sha256_file(review_manifest_path), STAGE06_REVIEW_MANIFEST)
    require_digest(sha256_file(review_success_path), STAGE06_REVIEW_SUCCESS)

    stage05 = load_json(stage05_manifest_path)
    stage06 = load_json(stage06_manifest_path)
    review = load_json(review_manifest_path)
    stage05_scientific = stage05.get("scientific_identity")
    stage06_scientific = stage06.get("scientific_identity")
    stage06_physical = stage06.get("physical_identity")
    stage06_operational = stage06.get("operational_provenance")
    review_scientific = review.get("scientific_identity")
    review_physical = review.get("physical_identity")
    review_operational = review.get("operational_provenance")
    if not all(
        isinstance(value, dict)
        for value in (
            stage05_scientific,
            stage06_scientific,
            stage06_physical,
            stage06_operational,
            review_scientific,
            review_physical,
            review_operational,
        )
    ):
        fail("MANIFEST_IDENTITY_INVALID")
    stage05_scientific = cast(dict[str, Any], stage05_scientific)
    stage06_scientific = cast(dict[str, Any], stage06_scientific)
    stage06_physical = cast(dict[str, Any], stage06_physical)
    stage06_operational = cast(dict[str, Any], stage06_operational)
    review_scientific = cast(dict[str, Any], review_scientific)
    review_physical = cast(dict[str, Any], review_physical)
    review_operational = cast(dict[str, Any], review_operational)

    expected_stage05 = {
        "stage05_contract_version": STAGE05_CONTRACT,
        "stage05_profile_version": STAGE05_PROFILE,
        "stage05_schema_fingerprint": STAGE05_SCHEMA,
        "stage05_logical_dataset_sha256_v1": STAGE05_LOGICAL,
        "upstream_ordered_identity_sha256": ORDERED_IDENTITY,
        "input_benchmark_fingerprint": BENCHMARK,
        "row_count": EXPECTED_ROWS,
    }
    if any(
        stage05_scientific.get(key) != value for key, value in expected_stage05.items()
    ):
        fail("STAGE05_BINDING_MISMATCH")
    expected_stage06 = {
        "stage06_contract_version": STAGE06_CONTRACT,
        "stage06_profile_version": STAGE06_PROFILE,
        "stage06_schema_fingerprint": STAGE06_SCHEMA,
        "stage06_contract_fingerprint": STAGE06_CONTRACT_FINGERPRINT,
        "stage06_logical_dataset_sha256_v1": STAGE06_LOGICAL,
        "stage06_row_map_logical_sha256_v1": STAGE06_ROW_MAP_LOGICAL,
        "stage06_registry_logical_sha256_v1": STAGE06_REGISTRY_LOGICAL,
        "stage06_candidate_id_domain_hex": STAGE06_CANDIDATE_ID_DOMAIN.hex(),
        "upstream_stage05_contract_version": STAGE05_CONTRACT,
        "upstream_stage05_profile_version": STAGE05_PROFILE,
        "upstream_stage05_schema_fingerprint": STAGE05_SCHEMA,
        "upstream_stage05_logical_fingerprint": STAGE05_LOGICAL,
        "upstream_stage05_input_binding_sha256": STAGE05_INPUT_BINDING,
        "upstream_stage05_manifest_sha256": STAGE05_MANIFEST,
        "upstream_ordered_identity_sha256": ORDERED_IDENTITY,
        "input_benchmark_fingerprint": BENCHMARK,
        "fixed_500_fingerprint": FIXED_500,
        "source_row_count": EXPECTED_ROWS,
        "unique_candidate_count": EXPECTED_UNIQUE,
    }
    if any(
        stage06_scientific.get(key) != value for key, value in expected_stage06.items()
    ):
        fail("STAGE06_MANIFEST_SCIENCE_MISMATCH")
    if (
        stage06_physical.get("stage06_input_binding_sha256") != STAGE06_INPUT_BINDING
        or stage06_physical.get("owner_only_permissions") is not True
        or stage06_operational.get("execution_git_sha") != IMPLEMENTATION_SHA
        or stage06_operational.get("slurm_job_id") != AUTHORITATIVE_JOB
        or stage06_operational.get("execution_site") != "goethe-nhr"
    ):
        fail("STAGE06_MANIFEST_PROVENANCE_MISMATCH")
    if (
        review_scientific.get("stage06_contract_version") != STAGE06_CONTRACT
        or review_scientific.get("stage06_profile_version") != STAGE06_PROFILE
        or review_scientific.get("stage06_logical_fingerprint") != STAGE06_LOGICAL
        or review_scientific.get("review_subset_fingerprint") != FIXED_500
        or review_scientific.get("selected_row_count") != EXPECTED_FIXED_ROWS
        or review_physical.get("stage05_manifest_sha256") != STAGE05_MANIFEST
        or review_physical.get("stage06_manifest_sha256") != STAGE06_MANIFEST
        or review_physical.get("accepted_development_review_manifest_sha256")
        != FIXED_MANIFEST
        or review_operational.get("execution_git_sha") != IMPLEMENTATION_SHA
        or review_operational.get("slurm_job_id") != AUTHORITATIVE_JOB
    ):
        fail("STAGE06_REVIEW_PROVENANCE_MISMATCH")

    stage05_paths = artifact_inventory(
        stage05_root, stage05, "output_artifacts", expected_prefix="data"
    )
    row_paths = artifact_inventory(
        stage06_root,
        stage06,
        "row_map_artifacts",
        expected_prefix="row_map/data",
    )
    registry_paths = artifact_inventory(
        stage06_root,
        stage06,
        "registry_artifacts",
        expected_prefix="registry/data",
    )
    if len(row_paths) != len(stage05_paths):
        fail("ROW_MAP_SHARD_COUNT_MISMATCH")
    require_digest(sha256_file(row_paths[0]), STAGE06_ROW_MAP_ARTIFACT)
    require_digest(sha256_file(registry_paths[0]), STAGE06_REGISTRY_ARTIFACT)

    fixed_identity_path = fixed_root / "selection/selected_identities.parquet"
    require_file(fixed_identity_path)
    require_digest(sha256_file(fixed_identity_path), FIXED_IDENTITIES)
    review_artifact_path = stage06_review_root / "stage06_fixed500_verification.parquet"
    require_file(review_artifact_path)
    require_digest(sha256_file(review_artifact_path), STAGE06_REVIEW_ARTIFACT)
    artifact_inventory(stage06_review_root, review, "artifacts")
    stage06_directories, stage06_files = observed_tree(stage06_root)
    if stage06_directories != {
        "row_map",
        "row_map/data",
        "registry",
        "registry/data",
    } or stage06_files != {
        "stage06_manifest.json",
        "_SUCCESS.json",
        *(path.relative_to(stage06_root).as_posix() for path in row_paths),
        *(path.relative_to(stage06_root).as_posix() for path in registry_paths),
    }:
        fail("STAGE06_TOPOLOGY_OR_MODE_MISMATCH")
    review_directories, review_files = observed_tree(stage06_review_root)
    if review_directories or review_files != {
        "stage06_fixed500_verification.parquet",
        "stage06_review_manifest.json",
        "stage06_summary.json",
        "stage06_summary.md",
        "_SUCCESS.json",
    }:
        fail("STAGE06_REVIEW_TOPOLOGY_OR_MODE_MISMATCH")
    return (
        stage05_paths,
        row_paths,
        registry_paths,
        fixed_identity_path,
        review_artifact_path,
    )


def review_subset_fingerprint(identities: list[bytes]) -> str:
    if len(identities) != EXPECTED_FIXED_ROWS or len(set(identities)) != len(
        identities
    ):
        fail("FIXED_IDENTITY_SET_MISMATCH")
    digest = hashlib.sha256(REVIEW_SUBSET_DOMAIN)
    for value in (
        "development_reporting_contract_v1",
        "development_review_subset_contract_v1",
        "development_review_balanced_selection_v1",
        "development_review_allocation_policy_v1",
    ):
        encode_text(digest, value)
    encode_digest(digest, BENCHMARK)
    encode_uint64(digest, EXPECTED_ROWS)
    encode_uint64(digest, EXPECTED_FIXED_ROWS)
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
    for name, policy_value in policy:
        encode_text(digest, name)
        if isinstance(policy_value, str):
            encode_text(digest, policy_value)
        else:
            encode_uint64(digest, policy_value)
    ordered = sorted(identities)
    encode_uint64(digest, len(ordered))
    for identity in ordered:
        digest.update(TYPE_BYTES + identity)
    return digest.hexdigest()


@dataclass(frozen=True)
class FixedRow:
    standard_id: bytes | None
    native_id: bytes | None
    standard_lower: str | None
    native_lower: str | None


def load_fixed_identities(path: Path) -> tuple[pa.Table, set[bytes]]:
    table = pq.ParquetFile(path, page_checksum_verification=True).read(
        use_threads=False
    )
    expected_names = [
        "review_order",
        "development_review_id_v1",
        "stable_source_row_id_v1",
    ]
    if table.num_rows != EXPECTED_FIXED_ROWS or table.schema.names != expected_names:
        fail("FIXED_IDENTITY_SCHEMA_MISMATCH")
    orders = table.column("review_order").to_pylist()
    identities = cast(list[bytes], table.column("stable_source_row_id_v1").to_pylist())
    review_ids = cast(list[bytes], table.column("development_review_id_v1").to_pylist())
    expected_review_ids = [
        hashlib.sha256(REVIEW_ID_DOMAIN + bytes.fromhex(BENCHMARK) + value).digest()
        for value in identities
    ]
    if (
        orders != list(range(1, EXPECTED_FIXED_ROWS + 1))
        or review_ids != expected_review_ids
        or review_subset_fingerprint(identities) != FIXED_500
    ):
        fail("FIXED_IDENTITY_CONTENT_MISMATCH")
    return table, set(identities)


def configure_duckdb(connection: duckdb.DuckDBPyConnection, work: Path) -> None:
    spill = work / "spill"
    spill.mkdir(mode=0o700)
    connection.execute("SET memory_limit='8GB'")
    connection.execute("SET threads=3")
    connection.execute("SET preserve_insertion_order=false")
    connection.execute("SET temp_directory=?", [str(spill.resolve())])


def create_tables(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute("CREATE TABLE source_rows (row_number UBIGINT, stable_id BLOB)")
    connection.execute(
        """
        CREATE TABLE occurrences (
            row_number UBIGINT,
            stable_id BLOB,
            representation VARCHAR,
            candidate_id BLOB,
            candidate_text VARCHAR,
            clean_surface VARCHAR,
            candidate_codepoints UBIGINT
        )
        """
    )


def insert_arrow(
    connection: duckdb.DuckDBPyConnection, name: str, table: pa.Table, target: str
) -> None:
    connection.register(name, table)
    try:
        connection.execute(f"INSERT INTO {target} SELECT * FROM {name}")
    finally:
        connection.unregister(name)


def scan_row_map(
    connection: duckdb.DuckDBPyConnection,
    stage05_paths: Sequence[Path],
    row_paths: Sequence[Path],
    fixed_targets: set[bytes],
    contract_sha: str,
    expected_row_metadata: Mapping[bytes, bytes],
) -> tuple[dict[str, int], str, str, dict[bytes, FixedRow], pa.Schema]:
    identities = OrderedIdentityHasher()
    logical = RowMapLogicalHasher(contract_sha)
    fixed: dict[bytes, FixedRow] = {}
    metrics = {
        "rows": 0,
        "standard_available": 0,
        "standard_unavailable": 0,
        "native_available": 0,
        "native_unavailable": 0,
        "same_row_equal": 0,
        "max_standard_codepoints": 0,
        "standard_million_codepoints": 0,
        "upstream_mismatches": 0,
        "mapping_mismatches": 0,
    }
    observed_stage05_schema: pa.Schema | None = None
    for stage05_path, row_path in zip(stage05_paths, row_paths, strict=True):
        upstream = pq.ParquetFile(stage05_path, page_checksum_verification=True)
        mapped = pq.ParquetFile(row_path, page_checksum_verification=True)
        stage05_schema = upstream.schema_arrow.remove_metadata()
        row_schema = mapped.schema_arrow
        if observed_stage05_schema is None:
            observed_stage05_schema = stage05_schema
        elif not stage05_schema.equals(observed_stage05_schema, check_metadata=True):
            fail("STAGE05_SCHEMA_INCONSISTENT")
        prefix = pa.schema(list(row_schema.remove_metadata())[: len(stage05_schema)])
        if not prefix.equals(stage05_schema, check_metadata=True):
            fail("ROW_MAP_UPSTREAM_SCHEMA_MISMATCH")
        appended = list(row_schema.remove_metadata())[len(stage05_schema) :]
        if appended != [
            pa.field(ROW_ID_COLUMNS[0], pa.binary(32), nullable=True),
            pa.field(ROW_ID_COLUMNS[1], pa.binary(32), nullable=True),
        ]:
            fail("ROW_MAP_ID_SCHEMA_MISMATCH")
        if row_schema.metadata != dict(expected_row_metadata):
            fail("ROW_MAP_METADATA_MISMATCH")

        left_batches = bounded_batches(upstream, batch_rows=173)
        right_batches = bounded_batches(mapped, batch_rows=257)
        for left, right in aligned_batches(left_batches, right_batches):
            if any(
                not left.column(index).equals(right.column(index))
                for index in range(left.num_columns)
            ):
                metrics["upstream_mismatches"] += 1
                fail("UPSTREAM_VALUE_OR_ORDER_MISMATCH")
            names = right.schema.names
            indexes = {
                name: right.schema.get_field_index(name)
                for name in (
                    "stable_source_row_id_v1",
                    "stage05_standard_candidate_clean",
                    "stage05_native_candidate_clean",
                    "stage05_standard_candidate_lower",
                    "stage05_native_candidate_lower",
                    "stage05_standard_candidate_available",
                    "stage05_native_candidate_available",
                    *ROW_ID_COLUMNS,
                )
            }
            if (
                any(value < 0 for value in indexes.values())
                or len(names) != right.num_columns
            ):
                fail("REQUIRED_ROW_MAP_COLUMN_MISSING")
            stable_array = right.column(indexes["stable_source_row_id_v1"])
            identities.update(stable_array)
            row_numbers: list[int] = []
            source_ids: list[bytes] = []
            occurrence_rows: list[int] = []
            occurrence_ids: list[bytes] = []
            occurrence_source_ids: list[bytes] = []
            occurrence_representations: list[str] = []
            occurrence_texts: list[str] = []
            occurrence_clean: list[str] = []
            occurrence_lengths: list[int] = []
            for index in range(right.num_rows):
                row_number = metrics["rows"] + 1
                stable = stable_array[index].as_py()
                if not isinstance(stable, bytes) or len(stable) != 32:
                    fail("STABLE_IDENTITY_INVALID")
                row_numbers.append(row_number)
                source_ids.append(stable)
                row_values: dict[str, tuple[bytes | None, str | None]] = {}
                for representation, prefix_name in (
                    ("STANDARD", "standard"),
                    ("NATIVE", "native"),
                ):
                    available = right.column(
                        indexes[f"stage05_{prefix_name}_candidate_available"]
                    )[index].as_py()
                    lower = right.column(
                        indexes[f"stage05_{prefix_name}_candidate_lower"]
                    )[index].as_py()
                    clean = right.column(
                        indexes[f"stage05_{prefix_name}_candidate_clean"]
                    )[index].as_py()
                    published = right.column(
                        indexes[
                            ROW_ID_COLUMNS[0]
                            if representation == "STANDARD"
                            else ROW_ID_COLUMNS[1]
                        ]
                    )[index].as_py()
                    if (
                        not isinstance(available, bool)
                        or not isinstance(lower, str)
                        or not isinstance(clean, str)
                    ):
                        fail("STAGE05_CANDIDATE_TYPE_MISMATCH")
                    metric_key = (
                        f"{prefix_name}_{'available' if available else 'unavailable'}"
                    )
                    metrics[metric_key] += 1
                    if not available:
                        if lower != "" or clean != "" or published is not None:
                            fail("UNAVAILABLE_REPRESENTATION_MISMATCH")
                        row_values[prefix_name] = (None, None)
                        continue
                    if not lower or not clean or clean.lower() != lower:
                        fail("AVAILABLE_REPRESENTATION_MISMATCH")
                    expected = candidate_id(lower)
                    if not isinstance(published, bytes) or published != expected:
                        metrics["mapping_mismatches"] += 1
                        fail("CANDIDATE_ID_MISMATCH")
                    occurrence_rows.append(row_number)
                    occurrence_source_ids.append(stable)
                    occurrence_representations.append(representation)
                    occurrence_ids.append(published)
                    occurrence_texts.append(lower)
                    occurrence_clean.append(clean)
                    occurrence_lengths.append(len(lower))
                    row_values[prefix_name] = (published, lower)
                    if representation == "STANDARD":
                        metrics["max_standard_codepoints"] = max(
                            metrics["max_standard_codepoints"], len(lower)
                        )
                        metrics["standard_million_codepoints"] += int(
                            len(lower) >= 1_000_000
                        )
                standard_id, standard_lower = row_values["standard"]
                native_id, native_lower = row_values["native"]
                if standard_lower is not None and standard_lower == native_lower:
                    metrics["same_row_equal"] += 1
                logical.update(stable, standard_id, native_id)
                if stable in fixed_targets:
                    if stable in fixed:
                        fail("FIXED_IDENTITY_DUPLICATED")
                    fixed[stable] = FixedRow(
                        standard_id=standard_id,
                        native_id=native_id,
                        standard_lower=standard_lower,
                        native_lower=native_lower,
                    )
                metrics["rows"] += 1
            insert_arrow(
                connection,
                "source_batch",
                pa.table(
                    {
                        "row_number": pa.array(row_numbers, type=pa.uint64()),
                        "stable_id": pa.array(source_ids, type=pa.binary(32)),
                    }
                ),
                "source_rows",
            )
            if occurrence_rows:
                insert_arrow(
                    connection,
                    "occurrence_batch",
                    pa.table(
                        {
                            "row_number": pa.array(occurrence_rows, type=pa.uint64()),
                            "stable_id": pa.array(
                                occurrence_source_ids, type=pa.binary(32)
                            ),
                            "representation": pa.array(occurrence_representations),
                            "candidate_id": pa.array(
                                occurrence_ids, type=pa.binary(32)
                            ),
                            "candidate_text": pa.array(occurrence_texts),
                            "clean_surface": pa.array(occurrence_clean),
                            "candidate_codepoints": pa.array(
                                occurrence_lengths, type=pa.uint64()
                            ),
                        }
                    ),
                    "occurrences",
                )
    if observed_stage05_schema is None or set(fixed) != fixed_targets:
        fail("ROW_MAP_OR_FIXED_STREAM_INCOMPLETE")
    return (
        metrics,
        identities.hexdigest(),
        logical.hexdigest(),
        fixed,
        observed_stage05_schema,
    )


def one(connection: duckdb.DuckDBPyConnection, query: str) -> int:
    row = connection.execute(query).fetchone()
    if row is None or len(row) != 1 or isinstance(row[0], bool):
        fail("AGGREGATE_QUERY_INVALID")
    return int(row[0])


def aggregate_occurrences(
    connection: duckdb.DuckDBPyConnection,
    registry_paths: Sequence[Path],
) -> dict[str, Any]:
    connection.execute(
        """
        CREATE TABLE candidate_text_groups AS
        SELECT
            candidate_id,
            encode(candidate_text) AS candidate_bytes,
            count(*)::UBIGINT AS occurrence_count,
            count(*) FILTER (WHERE representation='STANDARD')::UBIGINT
                AS standard_count,
            count(*) FILTER (WHERE representation='NATIVE')::UBIGINT
                AS native_count,
            count(DISTINCT stable_id)::UBIGINT AS source_row_count,
            count(DISTINCT encode(clean_surface))::UBIGINT AS clean_surface_count,
            min(candidate_codepoints)::UBIGINT AS candidate_codepoints,
            max(candidate_codepoints)::UBIGINT AS maximum_candidate_codepoints
        FROM occurrences
        GROUP BY candidate_id, encode(candidate_text)
        """
    )
    collision_row = connection.execute(
        """
        SELECT count(*), coalesce(sum(distinct_texts - 1), 0)
        FROM (
            SELECT candidate_id, count(*)::UBIGINT AS distinct_texts
            FROM candidate_text_groups
            GROUP BY candidate_id
            HAVING count(*) > 1
        )
        """
    ).fetchone()
    if collision_row is None:
        fail("COLLISION_QUERY_INVALID")
    collision_groups = int(collision_row[0])
    distinct_text_collisions = int(collision_row[1])
    duplicate_text_ids = one(
        connection,
        """
        SELECT count(*) FROM (
            SELECT candidate_bytes FROM candidate_text_groups
            GROUP BY candidate_bytes HAVING count(*) > 1
        )
        """,
    )
    if collision_groups or distinct_text_collisions or duplicate_text_ids:
        fail("ACTUAL_DIGEST_COLLISION_OR_IDENTITY_SPLIT")
    connection.execute(
        "CREATE VIEW candidate_groups AS SELECT * FROM candidate_text_groups"
    )
    connection.read_parquet([str(path) for path in registry_paths]).create_view(
        "published_registry"
    )
    registry_duplicates = connection.execute(
        """
        SELECT
            count(*) - count(DISTINCT stage06_exact_candidate_id),
            count(*) - count(DISTINCT encode(stage06_candidate_lower))
        FROM published_registry
        """
    ).fetchone()
    if registry_duplicates is None or any(int(value) for value in registry_duplicates):
        fail("REGISTRY_DUPLICATE_ID_OR_TEXT")
    registry_mismatches = one(
        connection,
        """
        SELECT count(*) FROM candidate_groups g
        FULL OUTER JOIN published_registry r
          ON g.candidate_id = r.stage06_exact_candidate_id
         AND g.candidate_bytes = encode(r.stage06_candidate_lower)
        WHERE g.candidate_id IS NULL OR r.stage06_exact_candidate_id IS NULL
           OR g.occurrence_count != r.stage06_occurrence_count
           OR g.standard_count != r.stage06_standard_occurrence_count
           OR g.native_count != r.stage06_native_occurrence_count
        """,
    )
    map_back_mismatches = one(
        connection,
        """
        SELECT count(*) FROM occurrences o
        LEFT JOIN published_registry r
          ON o.candidate_id = r.stage06_exact_candidate_id
         AND encode(o.candidate_text) = encode(r.stage06_candidate_lower)
        WHERE r.stage06_exact_candidate_id IS NULL
        """,
    )
    duplicate_sources = one(
        connection,
        "SELECT count(*) - count(DISTINCT stable_id) FROM source_rows",
    )
    if registry_mismatches or map_back_mismatches or duplicate_sources:
        fail("REGISTRY_OR_MAP_BACK_MISMATCH")

    totals = connection.execute(
        """
        SELECT count(*), coalesce(sum(occurrence_count),0),
               coalesce(sum(standard_count),0), coalesce(sum(native_count),0),
               count(*) FILTER (WHERE occurrence_count=1),
               count(*) FILTER (WHERE occurrence_count>1),
               coalesce(max(occurrence_count),0),
               count(*) FILTER (
                 WHERE occurrence_count>1 AND source_row_count>1
               ),
               count(*) FILTER (WHERE standard_count>0 AND native_count=0),
               count(*) FILTER (WHERE standard_count=0 AND native_count>0),
               count(*) FILTER (WHERE standard_count>0 AND native_count>0),
               count(*) FILTER (WHERE clean_surface_count>1),
               count(*) FILTER (WHERE octet_length(candidate_bytes)=0)
        FROM candidate_groups
        """
    ).fetchone()
    if totals is None:
        fail("GROUP_TOTAL_QUERY_INVALID")
    distribution = {
        str(int(size)): int(count)
        for size, count in connection.execute(
            "SELECT occurrence_count, count(*) FROM candidate_groups "
            "GROUP BY occurrence_count ORDER BY occurrence_count"
        ).fetchall()
    }
    clean_distribution = {
        str(int(size)): int(count)
        for size, count in connection.execute(
            "SELECT clean_surface_count, count(*) FROM candidate_groups "
            "GROUP BY clean_surface_count ORDER BY clean_surface_count"
        ).fetchall()
    }
    length_rows = connection.execute(
        """
        SELECT
          CASE
            WHEN candidate_codepoints <= 24 THEN '1_to_24'
            WHEN candidate_codepoints <= 49 THEN '25_to_49'
            WHEN candidate_codepoints <= 99 THEN '50_to_99'
            WHEN candidate_codepoints <= 1023 THEN '100_to_1023'
            WHEN candidate_codepoints <= 65535 THEN '1024_to_65535'
            WHEN candidate_codepoints <= 999999 THEN '65536_to_999999'
            ELSE '1000000_or_more'
          END AS bucket,
          count(*)::UBIGINT,
          sum(occurrence_count)::UBIGINT,
          count(*) FILTER (WHERE occurrence_count>1)::UBIGINT,
          sum(occurrence_count-1)::UBIGINT
        FROM candidate_groups
        GROUP BY bucket ORDER BY bucket
        """
    ).fetchall()
    length_buckets = {
        str(row[0]): tuple(int(value) for value in row[1:]) for row in length_rows
    }
    return {
        "unique_candidates": int(totals[0]),
        "occurrence_sum": int(totals[1]),
        "standard_sum": int(totals[2]),
        "native_sum": int(totals[3]),
        "singletons": int(totals[4]),
        "duplicate_groups": int(totals[5]),
        "maximum_group_size": int(totals[6]),
        "multi_source_duplicate_groups": int(totals[7]),
        "standard_only": int(totals[8]),
        "native_only": int(totals[9]),
        "both": int(totals[10]),
        "multi_clean_surface_groups": int(totals[11]),
        "empty_registry_candidates": int(totals[12]),
        "group_size_distribution": distribution,
        "clean_surface_distribution": clean_distribution,
        "length_buckets": length_buckets,
        "candidate_id_collision_groups": collision_groups,
        "distinct_text_digest_collision_groups": distinct_text_collisions,
        "registry_mismatches": registry_mismatches,
        "occurrence_map_back_mismatches": map_back_mismatches,
        "duplicate_source_ids": duplicate_sources,
    }


def scan_registry(
    registry_paths: Sequence[Path],
    expected_metadata: Mapping[bytes, bytes],
    contract_sha: str,
) -> tuple[str, int, dict[str, int], pa.Schema]:
    logical = RegistryLogicalHasher(contract_sha)
    previous: bytes | None = None
    rows = 0
    sums = {"total": 0, "standard": 0, "native": 0}
    schema_observed: pa.Schema | None = None
    expected_schema = pa.schema(
        (
            pa.field(REGISTRY_COLUMNS[0], pa.binary(32), nullable=False),
            pa.field(REGISTRY_COLUMNS[1], pa.string(), nullable=False),
            pa.field(REGISTRY_COLUMNS[2], pa.uint64(), nullable=False),
            pa.field(REGISTRY_COLUMNS[3], pa.uint64(), nullable=False),
            pa.field(REGISTRY_COLUMNS[4], pa.uint64(), nullable=False),
        )
    )
    for path in registry_paths:
        parquet = pq.ParquetFile(path, page_checksum_verification=True)
        if not parquet.schema_arrow.remove_metadata().equals(
            expected_schema, check_metadata=True
        ) or parquet.schema_arrow.metadata != dict(expected_metadata):
            fail("REGISTRY_SCHEMA_OR_METADATA_MISMATCH")
        schema_observed = expected_schema
        for batch in bounded_batches(parquet, batch_rows=193):
            if any(
                batch.column(index).null_count for index in range(batch.num_columns)
            ):
                fail("REGISTRY_NULL")
            for index in range(batch.num_rows):
                value_id = batch.column(0)[index].as_py()
                text = batch.column(1)[index].as_py()
                counts = [int(batch.column(i)[index].as_py()) for i in range(2, 5)]
                if (
                    not isinstance(value_id, bytes)
                    or len(value_id) != 32
                    or not isinstance(text, str)
                    or not text
                ):
                    fail("REGISTRY_VALUE_INVALID")
                if previous is not None and value_id <= previous:
                    fail("REGISTRY_ORDER_MISMATCH")
                if candidate_id(text) != value_id:
                    fail("REGISTRY_ID_TEXT_MISMATCH")
                if counts[0] < 1 or counts[0] != counts[1] + counts[2]:
                    fail("REGISTRY_COUNT_INVALID")
                logical.update(value_id, text, *counts)
                previous = value_id
                sums["total"] += counts[0]
                sums["standard"] += counts[1]
                sums["native"] += counts[2]
                rows += 1
    if schema_observed is None:
        fail("REGISTRY_EMPTY_INVENTORY")
    return logical.hexdigest(), rows, sums, schema_observed


def verify_fixed_500(
    connection: duckdb.DuckDBPyConnection,
    identity_table: pa.Table,
    fixed_rows: Mapping[bytes, FixedRow],
    review_artifact_path: Path,
) -> dict[str, int]:
    review = pq.ParquetFile(review_artifact_path, page_checksum_verification=True).read(
        use_threads=False
    )
    expected_names = [
        "review_order",
        "development_review_id_v1",
        "stable_source_row_id_v1",
        *ROW_ID_COLUMNS,
        "stage06_all_stage05_fields_exact",
        "stage06_standard_mapping_exact",
        "stage06_native_mapping_exact",
        "stage06_same_key_relation_exact",
        "stage06_standard_registry_resolution_exact",
        "stage06_native_registry_resolution_exact",
        "stage06_standard_registry_occurrence_count",
        "stage06_native_registry_occurrence_count",
    ]
    if review.num_rows != EXPECTED_FIXED_ROWS or review.schema.names != expected_names:
        fail("FIXED500_REVIEW_SCHEMA_MISMATCH")
    for name in (
        "review_order",
        "development_review_id_v1",
        "stable_source_row_id_v1",
    ):
        if not review.column(name).equals(identity_table.column(name)):
            fail("FIXED500_IDENTITY_OR_ORDER_MISMATCH")
    identities = cast(
        list[bytes], identity_table.column("stable_source_row_id_v1").to_pylist()
    )
    selected_ids: list[bytes] = []
    same_row_equal = 0
    cache: dict[bytes, tuple[str, int, int, int]] = {}
    for index, stable in enumerate(identities):
        row = fixed_rows[stable]
        expected_standard = (
            candidate_id(row.standard_lower) if row.standard_lower is not None else None
        )
        expected_native = (
            candidate_id(row.native_lower) if row.native_lower is not None else None
        )
        if review.column(ROW_ID_COLUMNS[0])[index].as_py() != expected_standard:
            fail("FIXED500_STANDARD_ID_MISMATCH")
        if review.column(ROW_ID_COLUMNS[1])[index].as_py() != expected_native:
            fail("FIXED500_NATIVE_ID_MISMATCH")
        relation = (expected_standard == expected_native) == (
            row.standard_lower is not None
            and row.native_lower is not None
            and row.standard_lower == row.native_lower
        )
        if not relation:
            fail("FIXED500_SAME_KEY_RELATION_MISMATCH")
        if row.standard_lower is not None and row.standard_lower == row.native_lower:
            same_row_equal += 1
        for representation, value_id, text, count_column in (
            ("STANDARD", expected_standard, row.standard_lower, 11),
            ("NATIVE", expected_native, row.native_lower, 12),
        ):
            if value_id is None:
                if review.column(count_column)[index].as_py() is not None:
                    fail("FIXED500_UNAVAILABLE_COUNT_MISMATCH")
                continue
            selected_ids.append(value_id)
            if value_id not in cache:
                registered_rows = connection.execute(
                    """
                    SELECT stage06_candidate_lower, stage06_occurrence_count,
                           stage06_standard_occurrence_count,
                           stage06_native_occurrence_count
                    FROM published_registry
                    WHERE stage06_exact_candidate_id=?
                    """,
                    [value_id],
                ).fetchall()
                if len(registered_rows) != 1:
                    fail("FIXED500_REGISTRY_RESOLUTION_MISMATCH")
                cache[value_id] = (
                    str(registered_rows[0][0]),
                    int(registered_rows[0][1]),
                    int(registered_rows[0][2]),
                    int(registered_rows[0][3]),
                )
            registered_entry = cache[value_id]
            if (
                registered_entry[0] != text
                or review.column(count_column)[index].as_py() != (registered_entry[1])
            ):
                fail(f"FIXED500_{representation}_REGISTRY_MISMATCH")
        for column in range(5, 11):
            if review.column(column)[index].as_py() is not True:
                fail("FIXED500_RECORDED_BOOLEAN_MISMATCH")
    metrics = {
        "rows": len(identities),
        "available_occurrences": len(selected_ids),
        "unique_candidates": len(set(selected_ids)),
        "duplicate_occurrences": len(selected_ids) - len(set(selected_ids)),
        "same_row_equal": same_row_equal,
        "mismatches": 0,
    }
    expected = {
        "rows": EXPECTED_FIXED_ROWS,
        "available_occurrences": EXPECTED_FIXED_OCCURRENCES,
        "unique_candidates": EXPECTED_FIXED_UNIQUE,
        "duplicate_occurrences": EXPECTED_FIXED_DUPLICATES,
        "same_row_equal": EXPECTED_FIXED_SAME_ROW_EQUAL,
        "mismatches": 0,
    }
    if metrics != expected:
        fail("FIXED500_AGGREGATE_MISMATCH")
    return metrics


def synthetic_matrix() -> list[str]:
    cases: list[str] = []
    values = [
        "a",
        "b",
        "a ",
        "a!",
        "É".lower(),
        "شارع",
        "خیابان",
        "москва",
        "東京",
        "é",
        "🏠",
    ]
    ids = [candidate_id(value) for value in values]
    if len(ids) != len(set(ids)):
        fail("SYNTHETIC_EXACT_DISTINCTION_FAILURE")
    for value in values:
        direct = hashlib.sha256(STAGE06_CANDIDATE_ID_DOMAIN + value.encode()).digest()
        if (
            candidate_id(value, chunk_codepoints=1) != direct
            or candidate_id(value, chunk_codepoints=7) != direct
        ):
            fail("SYNTHETIC_HASH_CHUNK_FAILURE")
    cases.extend(
        [
            "one_codepoint_difference",
            "whitespace_difference",
            "punctuation_difference",
            "unicode_latin",
            "arabic_persian",
            "cyrillic",
            "cjk",
            "combining_marks",
            "emoji",
            "deterministic_id",
            "batch_invariance",
        ]
    )
    giant = "東京-é-شارع-" * 100_000
    giant_id = candidate_id(giant, chunk_codepoints=4093)
    if (
        giant_id
        != hashlib.sha256(STAGE06_CANDIDATE_ID_DOMAIN + giant.encode()).digest()
        or len({giant_id, candidate_id(giant)}) != 1
    ):
        fail("SYNTHETIC_GIANT_HASH_FAILURE")
    cases.extend(["giant_text", "multiple_giant_duplicate_occurrences"])

    synthetic = [
        (None, None, None, None),
        ("alpha", None, "Alpha", None),
        (None, "beta", None, "Beta"),
        ("same", "same", "Same", "same"),
        ("left", "right", "Left", "Right"),
        ("repeat", None, "Repeat", None),
        (None, "repeat", None, "REPEAT"),
        ("surface", "surface", "Surface", "surface"),
    ]
    occurrences: list[tuple[bytes, str, str]] = []
    for standard, native, standard_clean, native_clean in synthetic:
        for representation, text, clean in (
            ("STANDARD", standard, standard_clean),
            ("NATIVE", native, native_clean),
        ):
            if text is not None and clean is not None:
                occurrences.append((candidate_id(text), representation, clean))
    groups: dict[bytes, tuple[set[str], set[str]]] = {}
    for value_id, representation, clean in occurrences:
        reps, surfaces = groups.setdefault(value_id, (set(), set()))
        reps.add(representation)
        surfaces.add(clean)
    if len(occurrences) != 10 or len(groups) != 7:
        fail("SYNTHETIC_GLOBAL_NAMESPACE_FAILURE")
    cases.extend(
        [
            "no_candidates_available",
            "standard_only",
            "native_only",
            "same_row_standard_native_equal",
            "same_row_standard_native_different",
            "repeated_across_rows",
            "repeated_across_representations",
            "distinct_clean_surfaces_same_lower_key",
            "unavailable_empty_candidate",
        ]
    )

    constant = b"\x07" * 32
    collision_groups: dict[bytes, set[str]] = {}
    for text in ("different one", "different two"):
        collision_groups.setdefault(constant, set()).add(text)
    if not any(len(texts) > 1 for texts in collision_groups.values()):
        fail("SYNTHETIC_FORCED_COLLISION_FAILURE")
    cases.append("simulated_digest_collision")

    payload = input_binding_payload()
    if input_binding_sha256(payload) != STAGE06_INPUT_BINDING:
        fail("SYNTHETIC_BINDING_REPRODUCTION_FAILURE")
    for key in payload:
        binding_changed = dict(payload)
        binding_changed[key] = 34_999 if key == "expected_row_count" else "0" * 64
        if input_binding_sha256(binding_changed) == STAGE06_INPUT_BINDING:
            fail("SYNTHETIC_BINDING_SUBSTITUTION_FAILURE")
    cases.extend(
        [
            "wrong_stage05_manifest",
            "wrong_stage05_ordered_identity",
            "wrong_benchmark",
            "wrong_fixed500_binding",
        ]
    )

    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        first = root / "first.parquet"
        second = root / "second.parquet"
        changed_path = root / "changed.parquet"
        table = pa.table({"value": [1, 2, 3, 4, 5]})
        pq.write_table(table, first, row_group_size=2, write_page_checksum=True)
        pq.write_table(table, second, row_group_size=3, write_page_checksum=True)
        pq.write_table(
            pa.table({"value": [1, 2, 9, 4, 5]}),
            changed_path,
            row_group_size=3,
            write_page_checksum=True,
        )
        left = pq.ParquetFile(first, page_checksum_verification=True).iter_batches(
            batch_size=2
        )
        right = pq.ParquetFile(second, page_checksum_verification=True).iter_batches(
            batch_size=3
        )
        if any(not a.equals(b) for a, b in aligned_batches(left, right)):
            fail("SYNTHETIC_ROW_GROUP_ALIGNMENT_FAILURE")
        left = pq.ParquetFile(first, page_checksum_verification=True).iter_batches(
            batch_size=2
        )
        wrong = pq.ParquetFile(
            changed_path, page_checksum_verification=True
        ).iter_batches(batch_size=3)
        if not any(not a.equals(b) for a, b in aligned_batches(left, wrong)):
            fail("SYNTHETIC_REAL_ORDER_VALUE_FAILURE_NOT_DETECTED")
        partial = root / "partial"
        partial.mkdir()
        try:
            require_file(partial / "_SUCCESS.json")
        except OSError:
            pass
        else:
            fail("SYNTHETIC_PARTIAL_OUTPUT_ACCEPTED")
        collision = root / "collision"
        collision.mkdir()
        try:
            ensure_new_output(collision)
        except ReviewFailure:
            pass
        else:
            fail("SYNTHETIC_OUTPUT_COLLISION_ACCEPTED")
        permissive = root / "permissive"
        permissive.write_text("x", encoding="utf-8")
        permissive.chmod(0o644)
        try:
            require_file(permissive)
        except ReviewFailure:
            pass
        else:
            fail("SYNTHETIC_PERMISSION_FAILURE_ACCEPTED")
        try:
            reject_holdout(root / "HOLDOUT")
        except ReviewFailure:
            pass
        else:
            fail("SYNTHETIC_HOLDOUT_PATH_ACCEPTED")
    cases.extend(
        [
            "row_group_invariance",
            "real_row_difference_failure",
            "partial_output_failure",
            "output_collision_failure",
            "permission_failure",
            "holdout_path_rejection",
        ]
    )

    thread_results = []
    table = pa.table({"candidate": ["b", "a", "b", "c", "a"]})
    for threads in (1, 4):
        connection = duckdb.connect()
        try:
            connection.execute("SET threads=?", [threads])
            connection.register("synthetic", table)
            thread_results.append(
                connection.execute(
                    "SELECT encode(candidate), count(*) FROM synthetic "
                    "GROUP BY encode(candidate) ORDER BY encode(candidate)"
                ).fetchall()
            )
        finally:
            connection.close()
    if thread_results[0] != thread_results[1]:
        fail("SYNTHETIC_DUCKDB_THREAD_INVARIANCE_FAILURE")
    ordered_ids = sorted(candidate_id(value) for value in ("c", "a", "b"))
    if ordered_ids != sorted(reversed(ordered_ids)):
        fail("SYNTHETIC_REGISTRY_ORDER_INVARIANCE_FAILURE")
    cases.extend(["duckdb_thread_invariance", "registry_order_invariance"])
    return cases


def validate_expected_metrics(
    row: Mapping[str, int], groups: Mapping[str, Any]
) -> None:
    expected_row = {
        "rows": EXPECTED_ROWS,
        "standard_available": EXPECTED_STANDARD,
        "standard_unavailable": EXPECTED_ROWS - EXPECTED_STANDARD,
        "native_available": EXPECTED_NATIVE,
        "native_unavailable": EXPECTED_ROWS - EXPECTED_NATIVE,
        "same_row_equal": EXPECTED_SAME_ROW_EQUAL,
        "max_standard_codepoints": EXPECTED_MAX_STANDARD_CODEPOINTS,
        "standard_million_codepoints": EXPECTED_STANDARD_MILLION,
        "upstream_mismatches": 0,
        "mapping_mismatches": 0,
    }
    if dict(row) != expected_row:
        fail("ROW_METRICS_MISMATCH")
    expected_groups: dict[str, Any] = {
        "unique_candidates": EXPECTED_UNIQUE,
        "occurrence_sum": EXPECTED_OCCURRENCES,
        "standard_sum": EXPECTED_STANDARD,
        "native_sum": EXPECTED_NATIVE,
        "singletons": EXPECTED_SINGLETONS,
        "duplicate_groups": EXPECTED_DUPLICATE_GROUPS,
        "maximum_group_size": EXPECTED_MAX_GROUP,
        "multi_source_duplicate_groups": EXPECTED_MULTI_SOURCE_GROUPS,
        "standard_only": EXPECTED_STANDARD_ONLY,
        "native_only": EXPECTED_NATIVE_ONLY,
        "both": EXPECTED_BOTH,
        "multi_clean_surface_groups": EXPECTED_CLEAN_VARIANTS,
        "empty_registry_candidates": 0,
        "group_size_distribution": EXPECTED_GROUP_DISTRIBUTION,
        "clean_surface_distribution": {"1": 51_656, "2": 123},
        "length_buckets": EXPECTED_LENGTH_BUCKETS,
        "candidate_id_collision_groups": 0,
        "distinct_text_digest_collision_groups": 0,
        "registry_mismatches": 0,
        "occurrence_map_back_mismatches": 0,
        "duplicate_source_ids": 0,
    }
    if dict(groups) != expected_groups:
        fail("GROUP_METRICS_MISMATCH")


def write_exclusive(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def write_json(path: Path, value: object) -> None:
    write_exclusive(
        path,
        (
            json.dumps(
                value, ensure_ascii=True, allow_nan=False, indent=2, sort_keys=True
            )
            + "\n"
        ).encode("utf-8"),
    )


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("self-test")
    review = subparsers.add_parser("review")
    review.add_argument("--repository", required=True, type=Path)
    review.add_argument("--stage05-root", required=True, type=Path)
    review.add_argument("--stage06-root", required=True, type=Path)
    review.add_argument("--fixed-review-root", required=True, type=Path)
    review.add_argument("--stage06-review-root", required=True, type=Path)
    review.add_argument("--output", required=True, type=Path)
    review.add_argument("--review-git-sha", required=True)
    return parser


def run_review(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    verify_runtime()
    if os.environ.get("SAFE_EXECUTION_SITE") != "goethe-nhr" or not os.environ.get(
        "SLURM_JOB_ID"
    ):
        fail("GOETHE_NHR_SLURM_REQUIRED")
    paths = (
        args.repository,
        args.stage05_root,
        args.stage06_root,
        args.fixed_review_root,
        args.stage06_review_root,
        args.output,
    )
    reject_holdout(*paths)
    controlled_root = DATA_ROOT.resolve(strict=True)
    for path in paths:
        resolved = path.resolve(strict=False)
        try:
            resolved.relative_to(controlled_root)
        except ValueError:
            fail("CONTROLLED_PATH_REQUIRED")
    verify_git(args.repository, args.review_git_sha)
    if input_binding_sha256(input_binding_payload()) != STAGE06_INPUT_BINDING:
        fail("INPUT_BINDING_FINGERPRINT_MISMATCH")
    synthetic = synthetic_matrix()
    ensure_new_output(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output.parent.chmod(0o700)
    require_directory(args.output.parent)
    temporary = args.output.parent / f".{args.output.name}.{os.getpid()}.in_progress"
    ensure_new_output(temporary)
    temporary.mkdir(mode=0o700)
    work = temporary / "work"
    work.mkdir(mode=0o700)
    write_exclusive(temporary / "_IN_PROGRESS", b"IN_PROGRESS\n")

    (
        stage05_paths,
        row_paths,
        registry_paths,
        fixed_identity_path,
        review_artifact_path,
    ) = validate_manifests(
        args.stage05_root,
        args.stage06_root,
        args.fixed_review_root,
        args.stage06_review_root,
    )
    fixed_identity_table, fixed_targets = load_fixed_identities(fixed_identity_path)

    database = work / "stage06_independent.duckdb"
    connection = duckdb.connect(str(database))
    database.chmod(0o600)
    try:
        configure_duckdb(connection, work)
        create_tables(connection)
        registry_file = pq.ParquetFile(
            registry_paths[0], page_checksum_verification=True
        )
        stage05_file = pq.ParquetFile(stage05_paths[0], page_checksum_verification=True)
        schema_sha = schema_fingerprint(
            stage05_file.schema_arrow.remove_metadata(),
            registry_file.schema_arrow.remove_metadata(),
        )
        contract_sha = contract_fingerprint(schema_sha)
        if schema_sha != STAGE06_SCHEMA or contract_sha != STAGE06_CONTRACT_FINGERPRINT:
            fail("INDEPENDENT_SCHEMA_OR_CONTRACT_FINGERPRINT_MISMATCH")
        row_metadata, registry_metadata = stage06_expected_metadata(
            contract_sha, schema_sha
        )
        row_metrics, ordered, row_logical, fixed_rows, observed_stage05_schema = (
            scan_row_map(
                connection,
                stage05_paths,
                row_paths,
                fixed_targets,
                contract_sha,
                row_metadata,
            )
        )
        registry_logical, registry_rows, registry_sums, observed_registry_schema = (
            scan_registry(registry_paths, registry_metadata, contract_sha)
        )
        if (
            schema_fingerprint(observed_stage05_schema, observed_registry_schema)
            != schema_sha
        ):
            fail("INDEPENDENT_SCHEMA_REPEAT_MISMATCH")
        groups = aggregate_occurrences(connection, registry_paths)
        fixed_metrics = verify_fixed_500(
            connection,
            fixed_identity_table,
            fixed_rows,
            review_artifact_path,
        )
        validate_expected_metrics(row_metrics, groups)
        logical = dataset_logical(
            contract_sha,
            row_logical,
            registry_logical,
            row_metrics["rows"],
            registry_rows,
        )
        if (
            ordered != ORDERED_IDENTITY
            or row_logical != STAGE06_ROW_MAP_LOGICAL
            or registry_logical != STAGE06_REGISTRY_LOGICAL
            or logical != STAGE06_LOGICAL
            or registry_rows != EXPECTED_UNIQUE
            or registry_sums
            != {
                "total": EXPECTED_OCCURRENCES,
                "standard": EXPECTED_STANDARD,
                "native": EXPECTED_NATIVE,
            }
        ):
            fail("INDEPENDENT_LOGICAL_FINGERPRINT_MISMATCH")
        spill = work / "spill"
        spill_bytes = sum(
            path.stat(follow_symlinks=False).st_size
            for path in spill.rglob("*")
            if path.is_file() and not path.is_symlink()
        )
        spill_files = sum(
            1 for path in spill.rglob("*") if path.is_file() and not path.is_symlink()
        )
    finally:
        connection.close()

    elapsed = round((time.perf_counter() - started) * 1000)
    result: dict[str, Any] = {
        "status": "STAGE06_INDEPENDENT_REVIEW_VERIFICATION_PASS",
        "review_contract": "stage06_independent_review_v1",
        "review_git_sha": args.review_git_sha,
        "candidate_sha": TARGET_CANDIDATE_SHA,
        "implementation_sha": IMPLEMENTATION_SHA,
        "base_sha": BASE_SHA,
        "authoritative_job": AUTHORITATIVE_JOB,
        "slurm_job_id": os.environ["SLURM_JOB_ID"],
        "fingerprints": {
            "stage05_schema": STAGE05_SCHEMA,
            "stage05_logical": STAGE05_LOGICAL,
            "stage05_input_binding": STAGE05_INPUT_BINDING,
            "stage05_manifest": STAGE05_MANIFEST,
            "benchmark": BENCHMARK,
            "fixed_500": FIXED_500,
            "stage06_schema": schema_sha,
            "stage06_contract": contract_sha,
            "stage06_input_binding": STAGE06_INPUT_BINDING,
            "stage06_row_map_logical": row_logical,
            "stage06_registry_logical": registry_logical,
            "stage06_logical": logical,
            "stage06_manifest": STAGE06_MANIFEST,
            "ordered_identity": ordered,
        },
        "row_metrics": row_metrics,
        "group_metrics": groups,
        "fixed_500": fixed_metrics,
        "registry": {
            "rows": registry_rows,
            "sums": registry_sums,
            "strict_unsigned_id_order": True,
        },
        "collision_guard": {
            "grouped_by_candidate_id_and_full_candidate_bytes": True,
            "then_grouped_by_candidate_id": True,
            "forced_collision_path_exercised": True,
            "actual_candidate_id_collision_groups": groups[
                "candidate_id_collision_groups"
            ],
            "actual_distinct_text_digest_collision_groups": groups[
                "distinct_text_digest_collision_groups"
            ],
        },
        "synthetic_matrix": synthetic,
        "boundedness": {
            "population_sized_python_candidate_map": False,
            "fixed_review_python_identity_bound": EXPECTED_FIXED_ROWS,
            "arrow_target_batch_bytes": TARGET_BATCH_BYTES,
            "hash_chunk_codepoints": HASH_CHUNK_CODEPOINTS,
            "disk_backed_duckdb": True,
            "duckdb_memory_limit": "8GB",
            "duckdb_threads": 3,
            "duckdb_spill_bytes": spill_bytes,
            "duckdb_spill_files": spill_files,
        },
        "runtime": {
            "python": platform.python_version(),
            "pyarrow": pa.__version__,
            "duckdb": duckdb.__version__,
            "elapsed_milliseconds": elapsed,
            "process_max_rss_kib": int(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            ),
        },
        "scope": {
            "holdout_accessed": False,
            "production_stage02_started": False,
            "production_stage03_started": False,
            "production_stage04_started": False,
            "production_stage05_started": False,
            "production_stage06_started": False,
            "stage07_started": False,
            "libpostal_invoked": False,
            "addresses_parsed": False,
            "geocoding_performed": False,
        },
        "privacy": "AGGREGATE_ONLY_NO_CANDIDATE_TEXT_OR_ROW_IDENTITIES",
    }
    shutil.rmtree(work)
    result_path = temporary / "stage06_independent_review.json"
    write_json(result_path, result)
    result_sha = sha256_file(result_path)
    write_json(
        temporary / "_SUCCESS.json",
        {
            "status": "STAGE06_INDEPENDENT_REVIEW_VERIFICATION_PASS",
            "review_result_sha256": result_sha,
            "review_git_sha": args.review_git_sha,
            "candidate_sha": TARGET_CANDIDATE_SHA,
            "implementation_sha": IMPLEMENTATION_SHA,
            "slurm_job_id": os.environ["SLURM_JOB_ID"],
        },
    )
    (temporary / "_IN_PROGRESS").unlink()
    for path in temporary.iterdir():
        require_file(path)
    fsync_directory(temporary)
    os.replace(temporary, args.output)
    fsync_directory(args.output.parent)
    return result


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "self-test":
            cases = synthetic_matrix()
            print("status=STAGE06_INDEPENDENT_SELF_TEST_PASS")
            print(f"synthetic_cases={len(cases)}")
            return 0
        result = run_review(args)
    except (
        ReviewFailure,
        OSError,
        ValueError,
        duckdb.Error,
        pa.ArrowException,
    ) as error:
        code = str(error) if isinstance(error, ReviewFailure) else type(error).__name__
        print(f"error={code}", file=sys.stderr)
        return 1
    print("status=STAGE06_INDEPENDENT_REVIEW_VERIFICATION_PASS")
    print(f"review_git_sha={result['review_git_sha']}")
    print(f"candidate_sha={result['candidate_sha']}")
    print(f"implementation_sha={result['implementation_sha']}")
    print(f"source_rows={result['row_metrics']['rows']}")
    print(f"candidate_occurrences={result['group_metrics']['occurrence_sum']}")
    print(f"unique_candidates={result['group_metrics']['unique_candidates']}")
    print(
        "candidate_id_collision_groups="
        f"{result['group_metrics']['candidate_id_collision_groups']}"
    )
    print(
        "distinct_text_digest_collision_groups="
        f"{result['group_metrics']['distinct_text_digest_collision_groups']}"
    )
    print(f"fixed500_mismatches={result['fixed_500']['mismatches']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
