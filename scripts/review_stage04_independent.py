#!/usr/bin/env python3
"""Independent, privacy-safe Stage 4 DEVELOPMENT verifier.

This review harness intentionally does not import the Stage 4 implementation.
It emits only aggregate counts, hashes, and fixed status tokens.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import os
import platform
import random
import re
import stat
import struct
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, NoReturn, cast

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


TARGET_CANDIDATE_SHA = "4b6c60c3fb07bb33043e6d31cae3e88bac23393b"
IMPLEMENTATION_SHA = "0d98ff6450875dfe8fb37c84729e5bbe632ef2fb"
STAGE03_MANIFEST_SHA = (
    "8f70745e31185abce52fdc1685c2b767f90874c21596152ea0463ec6677478d4"
)
STAGE04_MANIFEST_SHA = (
    "17a4854cddd8929b65ea79402f1a4f12a1574b720c1921567b577f23e152d1f3"
)
STAGE04_INPUT_BINDING_SHA = (
    "90e0e94d4359bd5927820dfc06b2cfc1dc37485c032d95726d1260ec88a534b0"
)
FIXED_REVIEW_MANIFEST_SHA = (
    "1fa69ce953cb6e4ef70d611e372ab8e8565b8e9aa577d00292a20219dcdd5c92"
)
FIXED_REVIEW_ARTIFACT_SHA = (
    "ffe7b51b67b2db1f64dcb202ab28fd22f32cd863de2e2cb7a7d112f1244f8779"
)
STAGE04_REVIEW_MANIFEST_SHA = (
    "95f450948daddbbee065cf0a3742ab723549dd5ab69d00fc3186f2ce3bc2ad5c"
)
STAGE04_REVIEW_ARTIFACT_SHA = (
    "0a8fb68b2f4dfb332d3c8fde431898c2229aed42a3cd27184c5ac0f0a12fe75b"
)
EXPECTED_STAGE03_LOGICAL = (
    "38df499bfaf61883832a9c718adf4cf92cfcea753337df68fa2e89afb6051bdb"
)
EXPECTED_STAGE03_SCHEMA = (
    "fc991ef63bd80a754114ecae6a9d3c4cf1f33a35a28581fea997edd2e4565c9b"
)
EXPECTED_STAGE03_INPUT_BINDING = (
    "6a2a28d276884511f5b8f63f40d14d6b7f4bf4397aa09289c53acdb92a661e6f"
)
EXPECTED_ORDERED_IDENTITY = (
    "fe2a4758582c1880d2b5c62dfc5c587d865e05d13033af9f5e8208b58e2a0487"
)
EXPECTED_BENCHMARK = "014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf"
EXPECTED_REVIEW_SUBSET = (
    "014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52"
)
EXPECTED_STAGE04_SCHEMA = (
    "dafb4f78b8bfce3120b6f4f7ae8cb44883f4c3a9cfd94b3137871b83c0ed5cbc"
)
EXPECTED_STAGE04_LOGICAL = (
    "054c66701f854a0108938170e1cb9bcee8a772f7fed29b82cda53c71aa9747ec"
)
EXPECTED_ROWS = 35_000
EXPECTED_REVIEW_ROWS = 500

SOURCE_COLUMNS = (
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
    "country_iso_code",
)
INPUT_COLUMNS = tuple(f"stage03_clean_{name}" for name in SOURCE_COLUMNS)
OUTPUT_COLUMNS = tuple(f"stage04_lower_{name}" for name in SOURCE_COLUMNS)
FIELD_GROUP = {
    **{name: "STANDARD_ADDRESS_LINES" for name in SOURCE_COLUMNS[:4]},
    **{name: "NATIVE_ADDRESS_LINES" for name in SOURCE_COLUMNS[4:8]},
    "postcode": "POSTCODE",
    "city": "CITY_LOCALITY",
    "region_in_country": "REGION",
    "country_iso_code": "COUNTRY_SOURCE_GEOGRAPHY",
}
SCRIPT_CLASSES = (
    "EMPTY",
    "ASCII_ONLY",
    "LATIN_NON_ASCII",
    "CYRILLIC",
    "GREEK",
    "ARABIC_PERSIAN",
    "CJK_HANGUL",
    "MIXED",
    "OTHER",
)
CJK_HANGUL_SCRIPTS = frozenset({"Han", "Hiragana", "Katakana", "Hangul", "Bopomofo"})
NON_DISTINCTIVE_SCRIPTS = frozenset({"Common", "Inherited", "Unknown"})
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
TYPE_UINT64 = b"\x01"
TYPE_TEXT = b"\x02"
TYPE_DIGEST = b"\x03"
ORDERED_IDENTITY_DOMAIN = b"SAFE_STAGE03_ORDERED_STABLE_IDENTITIES_V1"
SCHEMA_DOMAIN = b"SAFE_STAGE04_ARROW_SCHEMA_V1"
LOGICAL_DOMAIN = b"SAFE_STAGE04_LOGICAL_DATASET_V1"
REVIEW_SUBSET_DOMAIN = b"SAFE_DEVELOPMENT_REVIEW_SUBSET_V1"
REVIEW_ID_DOMAIN = b"SAFE_DEVELOPMENT_REVIEW_ID_V1"


class ReviewFailure(RuntimeError):
    """A fixed privacy-safe independent-review failure."""


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
        or SHA_RE.fullmatch(value) is None
        or value != expected
    ):
        fail("DIGEST_MISMATCH")


def encode_uint64(digest: Any, value: int) -> None:
    digest.update(TYPE_UINT64 + struct.pack(">Q", value))


def encode_text(digest: Any, value: str) -> None:
    payload = value.encode("utf-8")
    digest.update(TYPE_TEXT + struct.pack(">Q", len(payload)) + payload)


def encode_digest(digest: Any, value: str) -> None:
    digest.update(TYPE_DIGEST + bytes.fromhex(value))


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
class Metrics:
    rows: int = 0
    rows_changed: int = 0
    fields: int = 0
    changed_fields: int = 0
    ascii_fast_path: int = 0
    python_lower: int = 0
    length_increase_fields: int = 0
    length_decrease_fields: int = 0
    total_increase: int = 0
    total_decrease: int = 0
    max_increase: int = 0
    max_decrease: int = 0
    empty_to_nonempty: int = 0
    nonempty_to_empty: int = 0
    idempotence_failures: int = 0
    uncased_unchanged: int = 0
    field_changes: Counter[str] | None = None
    group_changes: Counter[str] | None = None
    group_rows: Counter[str] | None = None
    case_changes: Counter[str] | None = None
    script_total: Counter[str] | None = None
    script_changed: Counter[str] | None = None
    script_unchanged: Counter[str] | None = None

    def __post_init__(self) -> None:
        self.field_changes = Counter({name.upper(): 0 for name in SOURCE_COLUMNS})
        self.group_changes = Counter({group: 0 for group in set(FIELD_GROUP.values())})
        self.group_rows = Counter({group: 0 for group in set(FIELD_GROUP.values())})
        self.case_changes = Counter(
            {
                name: 0
                for name in (
                    "UNCHANGED",
                    "ASCII_CASE_CHANGED",
                    "UNICODE_CASE_CHANGED",
                    "UNICODE_LENGTH_CHANGED",
                )
            }
        )
        self.script_total = Counter({name: 0 for name in SCRIPT_CLASSES})
        self.script_changed = Counter({name: 0 for name in SCRIPT_CLASSES})
        self.script_unchanged = Counter({name: 0 for name in SCRIPT_CLASSES})

    def observe_value(self, source: str, before: str, after: str) -> None:
        assert self.field_changes is not None
        assert self.group_changes is not None
        assert self.case_changes is not None
        assert self.script_total is not None
        assert self.script_changed is not None
        assert self.script_unchanged is not None
        self.fields += 1
        script = classify_script(before)
        self.script_total[script] += 1
        if before.isascii():
            self.ascii_fast_path += 1
        else:
            self.python_lower += 1
        if before != after:
            self.changed_fields += 1
            self.field_changes[source.upper()] += 1
            self.group_changes[FIELD_GROUP[source]] += 1
            self.script_changed[script] += 1
            if before.isascii():
                self.case_changes["ASCII_CASE_CHANGED"] += 1
            elif len(before) != len(after):
                self.case_changes["UNICODE_LENGTH_CHANGED"] += 1
            else:
                self.case_changes["UNICODE_CASE_CHANGED"] += 1
        else:
            self.case_changes["UNCHANGED"] += 1
            self.script_unchanged[script] += 1
            if before and not any(has_case(ord(character)) for character in before):
                self.uncased_unchanged += 1
        delta = len(after) - len(before)
        if delta > 0:
            self.length_increase_fields += 1
            self.total_increase += delta
            self.max_increase = max(self.max_increase, delta)
        elif delta < 0:
            self.length_decrease_fields += 1
            self.total_decrease += -delta
            self.max_decrease = max(self.max_decrease, -delta)
        self.empty_to_nonempty += int(before == "" and after != "")
        self.nonempty_to_empty += int(before != "" and after == "")
        self.idempotence_failures += int(after.lower() != after)


@dataclass(frozen=True, slots=True)
class ScriptReference:
    starts: tuple[int, ...]
    ends: tuple[int, ...]
    scripts: tuple[str, ...]

    def script_for(self, codepoint: int) -> str:
        index = bisect.bisect_right(self.starts, codepoint) - 1
        if index >= 0 and codepoint <= self.ends[index]:
            return self.scripts[index]
        return "Unknown"


SCRIPT_REFERENCE: ScriptReference | None = None


def load_script_reference(repository: Path) -> ScriptReference:
    root = (
        repository
        / "src/safe_geocoding_pipeline/preprocessing/resources/references/unicode_ucd_16_0_0"
    )
    manifest_path = root / "manifest.json"
    artifact_path = root / "Scripts.txt"
    manifest = load_json(manifest_path)
    require_digest(sha256_file(artifact_path), cast(str, manifest["artifact_sha256"]))
    if manifest.get("unicode_version") != "16.0.0":
        fail("SCRIPT_REFERENCE_VERSION_MISMATCH")
    ranges: list[tuple[int, int, str]] = []
    for line in artifact_path.read_text(encoding="utf-8").splitlines():
        content = line.split("#", 1)[0].strip()
        if not content:
            continue
        bounds_text, script = (part.strip() for part in content.split(";"))
        bounds = bounds_text.split("..")
        ranges.append((int(bounds[0], 16), int(bounds[-1], 16), script))
    ranges.sort()
    return ScriptReference(
        tuple(item[0] for item in ranges),
        tuple(item[1] for item in ranges),
        tuple(item[2] for item in ranges),
    )


@lru_cache(maxsize=4096)
def script_for(codepoint: int) -> str:
    if SCRIPT_REFERENCE is None:
        fail("SCRIPT_REFERENCE_NOT_LOADED")
    return SCRIPT_REFERENCE.script_for(codepoint)


@lru_cache(maxsize=4096)
def has_case(codepoint: int) -> bool:
    character = chr(codepoint)
    return character.lower() != character or character.upper() != character


def classify_script(value: str) -> str:
    if value == "":
        return "EMPTY"
    if value.isascii():
        return "ASCII_ONLY"
    bucket: str | None = None
    for character in value:
        codepoint = ord(character)
        if codepoint < 128:
            if not character.isalpha():
                continue
            observed = "Latin"
        else:
            observed = script_for(codepoint)
            if observed in NON_DISTINCTIVE_SCRIPTS:
                continue
        current = "CJK_HANGUL" if observed in CJK_HANGUL_SCRIPTS else observed
        if bucket is None:
            bucket = current
        elif bucket != current:
            return "MIXED"
    if bucket in {None, "Latin"}:
        return "LATIN_NON_ASCII"
    assert bucket is not None
    return {
        "Cyrillic": "CYRILLIC",
        "Greek": "GREEK",
        "Arabic": "ARABIC_PERSIAN",
        "CJK_HANGUL": "CJK_HANGUL",
    }.get(bucket, "OTHER")


def recompute_stage04_schema_fingerprint(schema: pa.Schema) -> str:
    digest = hashlib.sha256(SCHEMA_DOMAIN)
    encode_text(digest, "stage04_lowercase_canonical_schema_v1")
    encode_uint64(digest, len(schema))
    for field in schema.remove_metadata():
        encode_text(digest, field.name)
        encode_text(digest, str(field.type))
        encode_text(digest, str(field.nullable).lower())
    return digest.hexdigest()


def recompute_logical(binding: Mapping[str, Any], schema_fingerprint: str) -> str:
    digest = hashlib.sha256(LOGICAL_DOMAIN)
    for contract_value in (
        "stage04_lowercase_canonical_contract_v1",
        "stage04_lowercase_canonical_profile_v1",
        "stage04_lowercase_canonical_schema_v1",
        "PYTHON_STR_LOWER",
        "(3, 14, 3)",
        "16.0.0",
        "CASEFOLD_FALSE",
        "LOCALE_SPECIFIC_CASING_FALSE",
        "NORMALIZATION_AFTER_LOWER_NONE",
        "ASCII_FAST_PATH_EQUIVALENT_TO_PYTHON_LOWER",
        "ARROW_UTF8_LOWER_FORBIDDEN",
        cast(str, binding["upstream_contract_version"]),
        cast(str, binding["upstream_profile_version"]),
    ):
        encode_text(digest, contract_value)
    for before, after in zip(INPUT_COLUMNS, OUTPUT_COLUMNS, strict=True):
        encode_text(digest, before)
        encode_text(digest, after)
    for value in ("stage04_changed_fields", "stage04_row_changed"):
        encode_text(digest, value)
    encode_digest(digest, cast(str, binding["upstream_logical_fingerprint"]))
    encode_digest(digest, cast(str, binding["upstream_schema_fingerprint"]))
    encode_digest(digest, cast(str, binding["upstream_ordered_identity_sha256"]))
    encode_digest(digest, cast(str, binding["input_benchmark_fingerprint"]))
    encode_digest(digest, schema_fingerprint)
    encode_uint64(digest, cast(int, binding["expected_row_count"]))
    return digest.hexdigest()


def recompute_review_subset_fingerprint(identities: list[bytes]) -> str:
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
    for name, policy_value in policy:
        encode_text(digest, name)
        if isinstance(policy_value, str):
            encode_text(digest, policy_value)
        else:
            encode_uint64(digest, policy_value)
    ordered = sorted(identities)
    encode_uint64(digest, len(ordered))
    for identity in ordered:
        if len(identity) != 32:
            fail("FIXED_REVIEW_IDENTITY_WIDTH_INVALID")
        digest.update(b"\x04" + identity)
    return digest.hexdigest()


def batches(
    parquet: pq.ParquetFile, *, batch_size: int = 997
) -> Iterator[pa.RecordBatch]:
    yield from parquet.iter_batches(batch_size=batch_size, use_threads=False)


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
            if (
                next(left_iterator, None) is not None
                or next(right_iterator, None) is not None
            ):
                fail("ROW_STREAM_LENGTH_MISMATCH")
            return
        length = min(
            left_batch.num_rows - left_offset,
            right_batch.num_rows - right_offset,
        )
        yield (
            left_batch.slice(left_offset, length),
            right_batch.slice(right_offset, length),
        )
        left_offset += length
        right_offset += length


def verify_runtime() -> None:
    if sys.version_info[:3] != (3, 14, 3):
        fail("PYTHON_VERSION_MISMATCH")
    if unicodedata.unidata_version != "16.0.0":
        fail("UNICODE_VERSION_MISMATCH")
    if pa.__version__ != "25.0.0":
        fail("PYARROW_VERSION_MISMATCH")
    if os.environ.get("SAFE_EXECUTION_SITE") != "goethe-nhr" or not os.environ.get(
        "SLURM_JOB_ID"
    ):
        fail("SLURM_SITE_REQUIRED")


def verify_binding(path: Path) -> dict[str, Any]:
    require_file(path)
    require_digest(sha256_file(path), STAGE04_INPUT_BINDING_SHA)
    binding = load_json(path)
    expected = {
        "stage04_input_binding_version": "stage04_input_binding_v1",
        "upstream_contract_version": "stage03_safe_text_cleaning_contract_v1",
        "upstream_profile_version": "stage03_safe_text_cleaning_profile_v1",
        "upstream_logical_fingerprint": EXPECTED_STAGE03_LOGICAL,
        "upstream_schema_fingerprint": EXPECTED_STAGE03_SCHEMA,
        "upstream_input_binding_sha256": EXPECTED_STAGE03_INPUT_BINDING,
        "upstream_manifest_sha256": STAGE03_MANIFEST_SHA,
        "upstream_ordered_identity_sha256": EXPECTED_ORDERED_IDENTITY,
        "input_benchmark_fingerprint": EXPECTED_BENCHMARK,
        "expected_row_count": EXPECTED_ROWS,
    }
    if binding != expected:
        fail("INPUT_BINDING_CONTENT_MISMATCH")
    return binding


def artifact_inventory(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    physical = manifest.get("physical_identity")
    if not isinstance(physical, dict):
        fail("MANIFEST_PHYSICAL_IDENTITY_INVALID")
    artifacts = physical.get("output_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        fail("OUTPUT_ARTIFACTS_INVALID")
    return cast(list[dict[str, Any]], artifacts)


def verify_artifact(root: Path, raw: Mapping[str, Any]) -> Path:
    relative = raw.get("relative_path")
    if not isinstance(relative, str) or not relative.startswith("data/part-"):
        fail("ARTIFACT_PATH_INVALID")
    path = root / relative
    require_file(path)
    if path.stat(follow_symlinks=False).st_size != raw.get("size_bytes"):
        fail("ARTIFACT_SIZE_MISMATCH")
    if sha256_file(path) != raw.get("sha256"):
        fail("ARTIFACT_SHA_MISMATCH")
    return path


def validate_scientific_manifests(
    stage03_root: Path, stage04_root: Path, binding: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    stage03_manifest_path = stage03_root / "stage03_manifest.json"
    stage04_manifest_path = stage04_root / "stage04_manifest.json"
    require_file(stage03_manifest_path)
    require_file(stage04_manifest_path)
    require_digest(sha256_file(stage03_manifest_path), STAGE03_MANIFEST_SHA)
    require_digest(sha256_file(stage04_manifest_path), STAGE04_MANIFEST_SHA)
    stage03 = load_json(stage03_manifest_path)
    stage04 = load_json(stage04_manifest_path)
    stage04_science = stage04.get("scientific_identity")
    stage04_physical = stage04.get("physical_identity")
    if not isinstance(stage04_science, dict) or not isinstance(stage04_physical, dict):
        fail("STAGE04_MANIFEST_INVALID")
    expected_science = {
        "stage04_contract_version": "stage04_lowercase_canonical_contract_v1",
        "stage04_profile_version": "stage04_lowercase_canonical_profile_v1",
        "stage04_schema_version": "stage04_lowercase_canonical_schema_v1",
        "stage04_schema_fingerprint": EXPECTED_STAGE04_SCHEMA,
        "stage04_logical_dataset_sha256_v1": EXPECTED_STAGE04_LOGICAL,
        "lower_input_columns": list(INPUT_COLUMNS),
        "lower_output_columns": list(OUTPUT_COLUMNS),
        "transformation": "PYTHON_STR_LOWER",
        "casefold_used": False,
        "locale_specific_casing_used": False,
        "normalization_after_lower": "NONE",
        "python_version": "3.14.3",
        "unicode_version": "16.0.0",
        "upstream_stage03_contract_version": binding["upstream_contract_version"],
        "upstream_stage03_profile_version": binding["upstream_profile_version"],
        "upstream_stage03_logical_fingerprint": EXPECTED_STAGE03_LOGICAL,
        "upstream_stage03_schema_fingerprint": EXPECTED_STAGE03_SCHEMA,
        "upstream_stage03_input_binding_sha256": EXPECTED_STAGE03_INPUT_BINDING,
        "upstream_ordered_identity_sha256": EXPECTED_ORDERED_IDENTITY,
        "input_benchmark_fingerprint": EXPECTED_BENCHMARK,
        "row_count": EXPECTED_ROWS,
    }
    if stage04_science != expected_science:
        fail("STAGE04_SCIENTIFIC_IDENTITY_MISMATCH")
    require_digest(
        stage04_physical.get("stage04_input_binding_sha256"), STAGE04_INPUT_BINDING_SHA
    )
    require_digest(
        stage04_physical.get("upstream_stage03_manifest_sha256"), STAGE03_MANIFEST_SHA
    )
    ordered = stage04_physical.get("ordered_identity_validation")
    if not isinstance(ordered, dict):
        fail("ORDERED_IDENTITY_MANIFEST_INVALID")
    for key in (
        "input_ordered_stable_identity_sha256_v1",
        "output_ordered_stable_identity_sha256_v1",
    ):
        require_digest(ordered.get(key), EXPECTED_ORDERED_IDENTITY)
    if (
        ordered.get("row_count") != EXPECTED_ROWS
        or ordered.get("upstream_duplicate_free_invariant_bound") is not True
    ):
        fail("ORDERED_IDENTITY_MANIFEST_INVALID")
    return stage03, stage04, artifact_inventory(stage03), artifact_inventory(stage04)


def compare_development(
    stage03_root: Path,
    stage04_root: Path,
    stage03_artifacts: list[dict[str, Any]],
    stage04_artifacts: list[dict[str, Any]],
) -> tuple[Metrics, str, str, pa.Schema]:
    if len(stage03_artifacts) != len(stage04_artifacts):
        fail("SHARD_COUNT_MISMATCH")
    input_identity = IdentityHasher.create()
    output_identity = IdentityHasher.create()
    metrics = Metrics()
    stage04_schema: pa.Schema | None = None
    for left_raw, right_raw in zip(stage03_artifacts, stage04_artifacts, strict=True):
        if left_raw.get("relative_path") != right_raw.get(
            "relative_path"
        ) or left_raw.get("row_count") != right_raw.get("row_count"):
            fail("SHARD_TOPOLOGY_MISMATCH")
        left_path = verify_artifact(stage03_root, left_raw)
        right_path = verify_artifact(stage04_root, right_raw)
        left_file = pq.ParquetFile(left_path, page_checksum_verification=True)
        right_file = pq.ParquetFile(right_path, page_checksum_verification=True)
        left_schema = left_file.schema_arrow.remove_metadata()
        right_schema = right_file.schema_arrow.remove_metadata()
        if stage04_schema is None:
            stage04_schema = right_schema
        elif not stage04_schema.equals(right_schema, check_metadata=False):
            fail("STAGE04_SCHEMA_DRIFT")
        if len(right_schema) != len(left_schema) + 14:
            fail("STAGE04_SCHEMA_WIDTH_MISMATCH")
        if not pa.schema(list(right_schema)[: len(left_schema)]).equals(
            left_schema, check_metadata=False
        ):
            fail("UPSTREAM_SCHEMA_PRESERVATION_FAILURE")
        for name in OUTPUT_COLUMNS:
            field = right_schema.field(name)
            if field.type != pa.string() or field.nullable:
                fail("LOWER_OUTPUT_SCHEMA_MISMATCH")
        changed_field = right_schema.field("stage04_changed_fields")
        if not pa.types.is_list(changed_field.type) or changed_field.nullable:
            fail("AUDIT_SCHEMA_MISMATCH")
        flag_field = right_schema.field("stage04_row_changed")
        if flag_field.type != pa.bool_() or flag_field.nullable:
            fail("AUDIT_SCHEMA_MISMATCH")
        for left_batch, right_batch in aligned_batches(
            batches(left_file), batches(right_file)
        ):
            if left_batch.num_rows != right_batch.num_rows:
                fail("BATCH_ROW_MISMATCH")
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
            details = right_batch.column(
                right_batch.schema.get_field_index("stage04_changed_fields")
            )
            flags = right_batch.column(
                right_batch.schema.get_field_index("stage04_row_changed")
            )
            for row_index in range(right_batch.num_rows):
                expected_fields: list[str] = []
                changed_groups: set[str] = set()
                for source, input_name, output_name in zip(
                    SOURCE_COLUMNS, INPUT_COLUMNS, OUTPUT_COLUMNS, strict=True
                ):
                    before = right_batch.column(
                        right_batch.schema.get_field_index(input_name)
                    )[row_index].as_py()
                    after = right_batch.column(
                        right_batch.schema.get_field_index(output_name)
                    )[row_index].as_py()
                    if not isinstance(before, str) or not isinstance(after, str):
                        fail("LOWER_VALUE_TYPE_MISMATCH")
                    if after != before.lower():
                        fail("LOWERCASE_SEMANTIC_MISMATCH")
                    metrics.observe_value(source, before, after)
                    if before != after:
                        expected_fields.append(source)
                        changed_groups.add(FIELD_GROUP[source])
                if details[row_index].as_py() != expected_fields or flags[
                    row_index
                ].as_py() is not bool(expected_fields):
                    fail("CHANGE_AUDIT_MISMATCH")
                if expected_fields:
                    metrics.rows_changed += 1
                    assert metrics.group_rows is not None
                    metrics.group_rows.update(changed_groups)
                metrics.rows += 1
    if stage04_schema is None:
        fail("NO_OUTPUT_SCHEMA")
    return (
        metrics,
        input_identity.hexdigest(),
        output_identity.hexdigest(),
        stage04_schema,
    )


def expected_metric_groups() -> dict[str, dict[str, int]]:
    return {
        "ROW_INTEGRITY": {
            "INPUT_ROWS": 35000,
            "OUTPUT_ROWS": 35000,
            "DROPPED_ROWS": 0,
            "ADDED_ROWS": 0,
            "DUPLICATE_IDENTITIES": 0,
        },
        "CHANGE_RATE": {
            "ROWS_CHANGED": 34994,
            "ROWS_UNCHANGED": 6,
            "ROWS_CHANGED_PERCENT_BASIS_POINTS": 9998,
        },
        "FIELD_CHANGES": {
            "TOTAL_LOWERCASE_FIELDS": 420000,
            "CHANGED_FIELDS": 186166,
            "UNCHANGED_FIELDS": 233834,
        },
        "FIELD_CHANGED_FIELDS": {
            "STREET_ADDRESS_LINE_1": 32682,
            "STREET_ADDRESS_LINE_2": 18031,
            "STREET_ADDRESS_LINE_3": 4432,
            "STREET_ADDRESS_LINE_4": 243,
            "STREET_ADDRESS_LINE_1_NATIVE": 21307,
            "STREET_ADDRESS_LINE_2_NATIVE": 10747,
            "STREET_ADDRESS_LINE_3_NATIVE": 4188,
            "STREET_ADDRESS_LINE_4_NATIVE": 247,
            "POSTCODE": 1019,
            "CITY": 31411,
            "REGION_IN_COUNTRY": 27500,
            "COUNTRY_ISO_CODE": 34359,
        },
        "FIELD_GROUP_AFFECTED_ROWS": {
            "STANDARD_ADDRESS_LINES": 33776,
            "NATIVE_ADDRESS_LINES": 24212,
            "POSTCODE": 1019,
            "CITY_LOCALITY": 31411,
            "REGION": 27500,
            "COUNTRY_SOURCE_GEOGRAPHY": 34359,
        },
        "FIELD_GROUP_CHANGED_FIELDS": {
            "STANDARD_ADDRESS_LINES": 55388,
            "NATIVE_ADDRESS_LINES": 36489,
            "POSTCODE": 1019,
            "CITY_LOCALITY": 31411,
            "REGION": 27500,
            "COUNTRY_SOURCE_GEOGRAPHY": 34359,
        },
        "FIELD_GROUP_TOTAL_FIELDS": {
            "STANDARD_ADDRESS_LINES": 140000,
            "NATIVE_ADDRESS_LINES": 140000,
            "POSTCODE": 35000,
            "CITY_LOCALITY": 35000,
            "REGION": 35000,
            "COUNTRY_SOURCE_GEOGRAPHY": 35000,
        },
        "CASE_CHANGE_CLASSIFICATION": {
            "UNCHANGED": 233834,
            "ASCII_CASE_CHANGED": 181549,
            "UNICODE_CASE_CHANGED": 4617,
            "UNICODE_LENGTH_CHANGED": 0,
        },
        "SCRIPT_CLASS_TOTAL_VALUES": {
            "EMPTY": 184653,
            "ASCII_ONLY": 210274,
            "LATIN_NON_ASCII": 1927,
            "CYRILLIC": 2107,
            "GREEK": 220,
            "ARABIC_PERSIAN": 3,
            "CJK_HANGUL": 18501,
            "MIXED": 1807,
            "OTHER": 508,
        },
        "SCRIPT_CLASS_CHANGED_VALUES": {
            "EMPTY": 0,
            "ASCII_ONLY": 181549,
            "LATIN_NON_ASCII": 1900,
            "CYRILLIC": 2033,
            "GREEK": 220,
            "ARABIC_PERSIAN": 0,
            "CJK_HANGUL": 0,
            "MIXED": 403,
            "OTHER": 61,
        },
        "SCRIPT_CLASS_UNCHANGED_VALUES": {
            "EMPTY": 184653,
            "ASCII_ONLY": 28725,
            "LATIN_NON_ASCII": 27,
            "CYRILLIC": 74,
            "GREEK": 0,
            "ARABIC_PERSIAN": 3,
            "CJK_HANGUL": 18501,
            "MIXED": 1404,
            "OTHER": 447,
        },
        "LOWERCASE_ENGINE": {
            "ASCII_FAST_PATH_VALUES": 394927,
            "PYTHON_LOWER_VALUES": 25073,
            "ARROW_UTF8_LOWER_VALUES": 0,
        },
        "OUTPUT_EFFECTS": {
            "CHARACTER_COUNT_INCREASE_FIELDS": 0,
            "CHARACTER_COUNT_DECREASE_FIELDS": 0,
            "TOTAL_CHARACTER_COUNT_INCREASE_CODEPOINTS": 0,
            "TOTAL_CHARACTER_COUNT_DECREASE_CODEPOINTS": 0,
            "MAX_LENGTH_INCREASE_CODEPOINTS": 0,
            "MAX_LENGTH_DECREASE_CODEPOINTS": 0,
            "EMPTY_TO_NONEMPTY_FIELDS": 0,
            "NONEMPTY_TO_EMPTY_FIELDS": 0,
            "UNICODE_LENGTH_CHANGED_FIELDS": 0,
            "UNCASED_SCRIPT_UNCHANGED_VALUES": 45782,
            "IDEMPOTENCE_FAILURES": 0,
        },
    }


def metric_groups(metrics: Metrics) -> dict[str, dict[str, int]]:
    assert metrics.field_changes is not None
    assert metrics.group_changes is not None
    assert metrics.group_rows is not None
    assert metrics.case_changes is not None
    assert metrics.script_total is not None
    assert metrics.script_changed is not None
    assert metrics.script_unchanged is not None
    return {
        "ROW_INTEGRITY": {
            "INPUT_ROWS": metrics.rows,
            "OUTPUT_ROWS": metrics.rows,
            "DROPPED_ROWS": 0,
            "ADDED_ROWS": 0,
            "DUPLICATE_IDENTITIES": 0,
        },
        "CHANGE_RATE": {
            "ROWS_CHANGED": metrics.rows_changed,
            "ROWS_UNCHANGED": metrics.rows - metrics.rows_changed,
            "ROWS_CHANGED_PERCENT_BASIS_POINTS": (
                metrics.rows_changed * 10000 + metrics.rows // 2
            )
            // metrics.rows,
        },
        "FIELD_CHANGES": {
            "TOTAL_LOWERCASE_FIELDS": metrics.fields,
            "CHANGED_FIELDS": metrics.changed_fields,
            "UNCHANGED_FIELDS": metrics.fields - metrics.changed_fields,
        },
        "FIELD_CHANGED_FIELDS": dict(metrics.field_changes),
        "FIELD_GROUP_AFFECTED_ROWS": dict(metrics.group_rows),
        "FIELD_GROUP_CHANGED_FIELDS": dict(metrics.group_changes),
        "FIELD_GROUP_TOTAL_FIELDS": {
            group: metrics.rows
            * sum(FIELD_GROUP[name] == group for name in SOURCE_COLUMNS)
            for group in set(FIELD_GROUP.values())
        },
        "CASE_CHANGE_CLASSIFICATION": dict(metrics.case_changes),
        "SCRIPT_CLASS_TOTAL_VALUES": dict(metrics.script_total),
        "SCRIPT_CLASS_CHANGED_VALUES": dict(metrics.script_changed),
        "SCRIPT_CLASS_UNCHANGED_VALUES": dict(metrics.script_unchanged),
        "LOWERCASE_ENGINE": {
            "ASCII_FAST_PATH_VALUES": metrics.ascii_fast_path,
            "PYTHON_LOWER_VALUES": metrics.python_lower,
            "ARROW_UTF8_LOWER_VALUES": 0,
        },
        "OUTPUT_EFFECTS": {
            "CHARACTER_COUNT_INCREASE_FIELDS": metrics.length_increase_fields,
            "CHARACTER_COUNT_DECREASE_FIELDS": metrics.length_decrease_fields,
            "TOTAL_CHARACTER_COUNT_INCREASE_CODEPOINTS": metrics.total_increase,
            "TOTAL_CHARACTER_COUNT_DECREASE_CODEPOINTS": metrics.total_decrease,
            "MAX_LENGTH_INCREASE_CODEPOINTS": metrics.max_increase,
            "MAX_LENGTH_DECREASE_CODEPOINTS": metrics.max_decrease,
            "EMPTY_TO_NONEMPTY_FIELDS": metrics.empty_to_nonempty,
            "NONEMPTY_TO_EMPTY_FIELDS": metrics.nonempty_to_empty,
            "UNICODE_LENGTH_CHANGED_FIELDS": metrics.case_changes[
                "UNICODE_LENGTH_CHANGED"
            ],
            "UNCASED_SCRIPT_UNCHANGED_VALUES": metrics.uncased_unchanged,
            "IDEMPOTENCE_FAILURES": metrics.idempotence_failures,
        },
    }


def verify_edge_cases() -> dict[str, int]:
    vectors = {
        "MAIN STREET": "main street",
        "Main Street 10": "main street 10",
        "ÉCOLE": "école",
        "STRAẞE": "straße",
        "STRASSE": "strasse",
        "ß": "ß",
        "I": "i",
        "İ": "i\u0307",
        "ı": "ı",
        "i": "i",
        "ΟΣ": "ος",
        "Σ": "σ",
        "ΣΟΣ": "σος",
        "ΟΣΑ": "οσα",
        "AΣ": "aς",
        "ΣA": "σa",
        "МОСКВА": "москва",
        "العربية": "العربية",
        "خیابان\u200cآزادی": "خیابان\u200cآزادی",
        "北京市": "北京市",
        "東京都": "東京都",
        "서울특별시": "서울특별시",
        "E\u0301COLE": "e\u0301cole",
        "🏢 MAIN 7️⃣": "🏢 main 7️⃣",
        "": "",
    }
    for before, expected in vectors.items():
        if before.lower() != expected or expected.lower() != expected:
            fail("UNICODE_EDGE_VECTOR_FAILURE")
    if unicodedata.normalize("NFC", "E\u0301COLE".lower()) == "E\u0301COLE".lower():
        fail("SYNTHETIC_NORMALIZATION_BOUNDARY_FAILURE")
    giant = "MAIN-İ-東京-🏢" * 250_000
    lowered = giant.lower()
    if (
        len(giant) <= 2_000_000
        or len(lowered) != len(giant) + 250_000
        or lowered.lower() != lowered
    ):
        fail("GIANT_VALUE_FAILURE")
    expansions: list[int] = []
    contractions: list[int] = []
    for codepoint in range(0x110000):
        if 0xD800 <= codepoint <= 0xDFFF:
            continue
        character = chr(codepoint)
        delta = len(character.lower()) - 1
        if delta > 0:
            expansions.append(codepoint)
        elif delta < 0:
            contractions.append(codepoint)
    if expansions != [0x0130] or contractions:
        fail("UNICODE_SCALAR_LENGTH_MAPPING_FAILURE")
    return {
        "edge_vectors": len(vectors),
        "unicode_scalar_expansions": len(expansions),
        "unicode_scalar_contractions": len(contractions),
        "giant_input_codepoints": len(giant),
    }


def optimized_lower(values: list[str]) -> list[str]:
    array = pa.array(values, type=pa.string(), from_pandas=False)
    mask = cast(pa.Array, pc.string_is_ascii(array))
    ascii_values = cast(pa.Array, pc.ascii_lower(array))
    python_values: list[str | None] = [None] * len(values)
    for index, value in enumerate(values):
        if not value.isascii():
            python_values[index] = value.lower()
    combined = pc.if_else(
        mask, ascii_values, pa.array(python_values, type=pa.string(), from_pandas=False)
    )
    return cast(list[str], combined.to_pylist())


def verify_optimized_path() -> dict[str, int]:
    corpus = [chr(codepoint) for codepoint in range(128)]
    for start, end in (
        (0x80, 0x250),
        (0x370, 0x530),
        (0x10A0, 0x1100),
        (0x1C80, 0x1CC0),
        (0x1E00, 0x2000),
        (0x2C60, 0x2D30),
        (0xA640, 0xA800),
    ):
        corpus.extend(chr(codepoint) for codepoint in range(start, end))
    corpus.extend(
        [
            "\t\n\r\x00\x1fABC",
            "Iİıi",
            "ΟΣ ΣΟΣ ΟΣΑ",
            "E\u0301COLE",
            "العربية خیابان\u200cآزادی",
            "北京市 東京都 서울특별시",
            "🏢 123 —",
        ]
    )
    rng = random.Random(20260827)
    for _ in range(50_000):
        characters: list[str] = []
        for _ in range(rng.randrange(0, 24)):
            while True:
                codepoint = rng.randrange(0x110000)
                if not 0xD800 <= codepoint <= 0xDFFF:
                    characters.append(chr(codepoint))
                    break
        corpus.append("".join(characters))
    mismatches = 0
    for start in range(0, len(corpus), 2048):
        chunk = corpus[start : start + 2048]
        observed = optimized_lower(chunk)
        expected = [value.lower() for value in chunk]
        mismatches += sum(
            left != right for left, right in zip(observed, expected, strict=True)
        )
        if any(value.lower() != value for value in observed):
            fail("OPTIMIZED_IDEMPOTENCE_FAILURE")
    if mismatches:
        fail("OPTIMIZED_PATH_MISMATCH")
    return {"synthetic_values": len(corpus), "semantic_mismatches": mismatches}


def verify_fixed_review(fixed_root: Path, stage04_review_root: Path) -> dict[str, int]:
    fixed_manifest_path = fixed_root / "development_review_manifest.json"
    stage04_review_manifest_path = stage04_review_root / "stage04_review_manifest.json"
    fixed_identity_path = fixed_root / "selection/selected_identities.parquet"
    stage04_review_path = stage04_review_root / "stage04_review.parquet"
    for path in (
        fixed_manifest_path,
        stage04_review_manifest_path,
        fixed_identity_path,
        stage04_review_path,
    ):
        require_file(path)
    require_digest(sha256_file(fixed_manifest_path), FIXED_REVIEW_MANIFEST_SHA)
    require_digest(
        sha256_file(stage04_review_manifest_path), STAGE04_REVIEW_MANIFEST_SHA
    )
    require_digest(sha256_file(fixed_identity_path), FIXED_REVIEW_ARTIFACT_SHA)
    require_digest(sha256_file(stage04_review_path), STAGE04_REVIEW_ARTIFACT_SHA)
    fixed_manifest = load_json(fixed_manifest_path)
    review_manifest = load_json(stage04_review_manifest_path)
    fixed_science = fixed_manifest.get("scientific_identity")
    review_science = review_manifest.get("scientific_identity")
    review_physical = review_manifest.get("physical_identity")
    if (
        not isinstance(fixed_science, dict)
        or not isinstance(review_science, dict)
        or not isinstance(review_physical, dict)
    ):
        fail("FIXED_REVIEW_MANIFEST_INVALID")
    if (
        fixed_science.get("review_subset_fingerprint") != EXPECTED_REVIEW_SUBSET
        or fixed_science.get("input_benchmark_fingerprint") != EXPECTED_BENCHMARK
    ):
        fail("FIXED_REVIEW_BINDING_MISMATCH")
    if (
        review_science.get("review_subset_fingerprint") != EXPECTED_REVIEW_SUBSET
        or review_science.get("input_benchmark_fingerprint") != EXPECTED_BENCHMARK
        or review_science.get("selected_row_count") != EXPECTED_REVIEW_ROWS
    ):
        fail("STAGE04_REVIEW_BINDING_MISMATCH")
    require_digest(
        review_physical.get("accepted_development_review_manifest_sha256"),
        FIXED_REVIEW_MANIFEST_SHA,
    )
    require_digest(
        review_physical.get("accepted_review_identity_artifact_sha256"),
        FIXED_REVIEW_ARTIFACT_SHA,
    )
    require_digest(review_physical.get("stage04_manifest_sha256"), STAGE04_MANIFEST_SHA)
    fixed = pq.ParquetFile(fixed_identity_path, page_checksum_verification=True).read(
        columns=["review_order", "development_review_id_v1", "stable_source_row_id_v1"],
        use_threads=False,
    )
    review = pq.ParquetFile(stage04_review_path, page_checksum_verification=True).read(
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
    stable_identities = cast(
        list[bytes], fixed.column("stable_source_row_id_v1").to_pylist()
    )
    if fixed.column("review_order").to_pylist() != list(
        range(1, EXPECTED_REVIEW_ROWS + 1)
    ):
        fail("FIXED_REVIEW_ORDER_INVALID")
    expected_review_ids = [
        hashlib.sha256(
            REVIEW_ID_DOMAIN + bytes.fromhex(EXPECTED_BENCHMARK) + identity
        ).digest()
        for identity in stable_identities
    ]
    if fixed.column("development_review_id_v1").to_pylist() != expected_review_ids:
        fail("FIXED_REVIEW_DERIVED_IDENTITY_MISMATCH")
    if recompute_review_subset_fingerprint(stable_identities) != EXPECTED_REVIEW_SUBSET:
        fail("FIXED_REVIEW_FINGERPRINT_MISMATCH")
    changed_rows = 0
    changed_values = 0
    non_case_codepoint_changes = 0
    length_changes = 0
    independent_expected_rows = 0
    for row_index in range(EXPECTED_REVIEW_ROWS):
        row_changed = False
        row_non_case_codepoint_changes = 0
        row_length_changes = 0
        expected_fields: list[str] = []
        for source, input_name, output_name in zip(
            SOURCE_COLUMNS, INPUT_COLUMNS, OUTPUT_COLUMNS, strict=True
        ):
            before = review.column(input_name)[row_index].as_py()
            after = review.column(output_name)[row_index].as_py()
            if (
                not isinstance(before, str)
                or not isinstance(after, str)
                or after != before.lower()
            ):
                fail("FIXED_REVIEW_LOWER_MISMATCH")
            if before != after:
                row_changed = True
                changed_values += 1
                expected_fields.append(source)
                if len(before) != len(after):
                    length_changes += 1
                    row_length_changes += 1
                else:
                    for old, new in zip(before, after, strict=True):
                        if old == new:
                            continue
                        if old.lower() != new and not (
                            old == "Σ" and new in {"σ", "ς"}
                        ):
                            non_case_codepoint_changes += 1
                            row_non_case_codepoint_changes += 1
        if (
            review.column("stage04_changed_fields")[row_index].as_py()
            != expected_fields
            or review.column("stage04_row_changed")[row_index].as_py()
            is not row_changed
        ):
            fail("FIXED_REVIEW_AUDIT_MISMATCH")
        changed_rows += int(row_changed)
        independent_expected_rows += int(
            row_changed
            and row_non_case_codepoint_changes == 0
            and row_length_changes == 0
        )
    if (
        non_case_codepoint_changes
        or length_changes
        or changed_rows != 500
        or independent_expected_rows != 500
    ):
        fail("FIXED_REVIEW_QUALITATIVE_FAILURE")
    return {
        "selected_rows": EXPECTED_REVIEW_ROWS,
        "changed_rows": changed_rows,
        "changed_values": changed_values,
        "non_case_codepoint_changes": non_case_codepoint_changes,
        "length_changes": length_changes,
        "questionable": 0,
        "semantic_damage": 0,
    }


def write_result(output: Path, result: Mapping[str, Any]) -> None:
    if output.exists() or output.is_symlink():
        fail("REVIEW_OUTPUT_COLLISION")
    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent.chmod(0o700)
    temporary = parent / f".{output.name}.{os.getpid()}.in_progress"
    temporary.mkdir(mode=0o700)
    payload = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8")
    for name, content in (
        ("stage04_independent_review.json", payload),
        (
            "_SUCCESS.json",
            (
                json.dumps(
                    {
                        "status": result["status"],
                        "review_target_sha": TARGET_CANDIDATE_SHA,
                    },
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8"),
        ),
    ):
        descriptor = os.open(
            temporary / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    directory_descriptor = os.open(temporary, os.O_RDONLY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)
    os.replace(temporary, output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--stage03-root", required=True, type=Path)
    parser.add_argument("--stage04-root", required=True, type=Path)
    parser.add_argument("--input-binding", required=True, type=Path)
    parser.add_argument("--fixed-review-root", required=True, type=Path)
    parser.add_argument("--stage04-review-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--review-git-sha", required=True)
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    global SCRIPT_REFERENCE
    verify_runtime()
    paths = (
        args.repository,
        args.stage03_root,
        args.stage04_root,
        args.input_binding,
        args.fixed_review_root,
        args.stage04_review_root,
        args.output,
    )
    reject_holdout(*paths)
    for directory in (
        args.repository,
        args.stage03_root,
        args.stage04_root,
        args.fixed_review_root,
        args.stage04_review_root,
    ):
        require_directory(directory)
    binding = verify_binding(args.input_binding)
    SCRIPT_REFERENCE = load_script_reference(args.repository)
    stage03, stage04, stage03_artifacts, stage04_artifacts = (
        validate_scientific_manifests(args.stage03_root, args.stage04_root, binding)
    )
    metrics, input_identity, output_identity, observed_schema = compare_development(
        args.stage03_root, args.stage04_root, stage03_artifacts, stage04_artifacts
    )
    observed_metrics = metric_groups(metrics)
    if observed_metrics != expected_metric_groups():
        fail("INDEPENDENT_METRIC_DISCREPANCY")
    manifest_metrics = stage04.get("development_metrics")
    if manifest_metrics != observed_metrics:
        fail("MANIFEST_METRIC_DISCREPANCY")
    schema_fingerprint = recompute_stage04_schema_fingerprint(observed_schema)
    if schema_fingerprint != EXPECTED_STAGE04_SCHEMA:
        fail("INDEPENDENT_SCHEMA_FINGERPRINT_MISMATCH")
    logical_fingerprint = recompute_logical(binding, schema_fingerprint)
    if logical_fingerprint != EXPECTED_STAGE04_LOGICAL:
        fail("INDEPENDENT_LOGICAL_FINGERPRINT_MISMATCH")
    if (
        input_identity != EXPECTED_ORDERED_IDENTITY
        or output_identity != EXPECTED_ORDERED_IDENTITY
    ):
        fail("INDEPENDENT_ORDERED_IDENTITY_MISMATCH")
    edge = verify_edge_cases()
    optimized = verify_optimized_path()
    fixed_review = verify_fixed_review(args.fixed_review_root, args.stage04_review_root)
    return {
        "status": "STAGE_4_INDEPENDENT_REVIEW_VERIFICATION_PASS",
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
            "stage03_manifest": STAGE03_MANIFEST_SHA,
            "stage04_manifest": STAGE04_MANIFEST_SHA,
            "stage04_input_binding": STAGE04_INPUT_BINDING_SHA,
            "stage04_schema": schema_fingerprint,
            "stage04_logical": logical_fingerprint,
            "ordered_identity": output_identity,
            "benchmark": EXPECTED_BENCHMARK,
            "fixed_review_subset": EXPECTED_REVIEW_SUBSET,
            "fixed_review_artifact": STAGE04_REVIEW_ARTIFACT_SHA,
        },
        "development": {
            "rows": metrics.rows,
            "fields_compared": metrics.fields,
            "incoming_stage03_columns_compared": len(observed_schema) - 14,
            "upstream_mismatches": 0,
            "lowercase_mismatches": 0,
            "audit_mismatches": 0,
            "identity_order_mismatches": 0,
            "metric_groups": observed_metrics,
        },
        "unicode_edges": edge,
        "optimized_path": optimized,
        "fixed_review": fixed_review,
        "privacy": {
            "holdout_accessed": False,
            "row_values_emitted": False,
            "stable_identities_emitted": False,
        },
    }


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = run(args)
        write_result(args.output, result)
    except ReviewFailure as error:
        print(f"review_error={error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"review_error=UNEXPECTED_{type(error).__name__}", file=sys.stderr)
        return 1
    print("status=STAGE_4_INDEPENDENT_REVIEW_VERIFICATION_PASS")
    print(f"review_target_sha={TARGET_CANDIDATE_SHA}")
    print(f"review_harness_git_sha={args.review_git_sha}")
    print(f"slurm_job_id={os.environ.get('SLURM_JOB_ID', '')}")
    print("development_rows=35000")
    print("derived_values_compared=420000")
    print("upstream_mismatches=0")
    print("lowercase_mismatches=0")
    print("optimized_mismatches=0")
    print("fixed_review_questionable=0")
    print("fixed_review_semantic_damage=0")
    print("holdout_accessed=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
