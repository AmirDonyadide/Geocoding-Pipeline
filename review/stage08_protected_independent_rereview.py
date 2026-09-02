"""Independent protected-artifact verification for frozen Stage 8.

This review-only harness reopens the immutable DEVELOPMENT artifacts. It does
not import the Stage 8 implementation, call a parser or service, or publish a
replacement scientific artifact. Output is sanitized aggregate evidence only.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import stat
import struct
import sys
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast

import pyarrow as pa
import pyarrow.parquet as pq


REVIEW_VERSION = "stage08_address_evidence_independent_rereview_v2"
CANDIDATE_SHA = "231cdbf9db755fb56486c46b3b3faa02f5b5f3b6"
EXECUTABLE_SHA = "c04cb97214a9f1e5d2b80512c756400321eefa80"

DATA_ROOT = Path("/work/footprint/donyadidegan/safe_geocoding_pipeline")
ARTIFACT_ROOT = DATA_ROOT / (
    "derived/controlled/stage08/development/"
    "stage08_development_20260902T132726Z_c04cb97214a9"
)
STAGE07_ROOT = DATA_ROOT / (
    "derived/controlled/stage07/evidence_only_development/"
    "stage07_evidence_e684d84_attempt1"
)
STAGE06_ROOT = DATA_ROOT / (
    "derived/controlled/stage06/development/"
    "stage06_development_20260828T223804Z_f39047cc825d"
)

HISTORICAL_JOB_1764273_FILESYSTEM_IDENTITY = (54, 9_363_000_937_145_638_642)
EXPECTED_MANIFEST_SHA256 = (
    "2a50bd8c066552c9cb7505ed2d6071f1ee36161b9a2cc07f3ed364cf00237827"
)
EXPECTED_LOGICAL_DATASET_SHA256 = (
    "9c9d431c2c1b92712e0cb372f2661ad48f4fe8758dc0327d25aef90ab2c2d526"
)
EXPECTED_STAGE07_MANIFEST_SHA256 = (
    "f58410877a7810562df7985c7316de7546d4dd8e11a647fd659c53a272e9c266"
)
EXPECTED_STAGE06_MANIFEST_SHA256 = (
    "e1da7b8ef04b65b1ece8e710720b57a8536841766fcf9de641f889b42eadd241"
)

EXPECTED_CONTRACT_FINGERPRINT = (
    "8b3c530e714177fe2c30a97d61dcc199b7f9efba58f3c17a291b817af0f24d5e"
)
EXPECTED_SCHEMA_BUNDLE_FINGERPRINT = (
    "6c8ebecd24c495dbe2ce32125ac1cb89c4a9de4905c786b774d10ad728ed392f"
)
EXPECTED_MAPPING_FINGERPRINT = (
    "b18167d2d5c1f1402d1bb0e92559befb92418f5f4f34df885596778a11d5c09d"
)
EXPECTED_SCHEMA_FINGERPRINTS = {
    "candidate_evidence": (
        "b1d56ea33c22e639ab798581c5533b1a0981ef5452dce5cb24e168d4a684bd4c"
    ),
    "parser_component_evidence": (
        "112fb17c2afac27b941d30f57fe5c1bb2e46d779f89bdf2efbd8c719a3b87ccf"
    ),
    "source_candidate_map": (
        "884eb8456fc6ee84a699a9e2371224e5c709363daac0febc5975f911bf48c398"
    ),
    "representation_occurrence_v1": (
        "df1cac9b6d9f86ffb76d1ea744fc64f15149c9e33fef980213286b91b2d02038"
    ),
}
EXPECTED_RELATION_LOGICAL_FINGERPRINTS = {
    "candidate_evidence": (
        "11fbd6e6e32b7dcb293c5918e9d02f19badf52cc9d9c108c910d17d92b8645aa"
    ),
    "parser_component_evidence": (
        "8b1af702c51bd40edc22302778ae2fda5851d9af8af39636a9a9733a94916030"
    ),
    "source_candidate_map": (
        "c4c9f8b3f425f93a1d61880f720136d1f71580871338c9a920c9abeffa93ee32"
    ),
    "representation_occurrence_v1": (
        "57aa3dcc5caf796fbbe15b3c0df655a8f34902107ce9fed3fbb6aaf38e158774"
    ),
}

EXPECTED_COUNTS = {
    "candidates": 51_779,
    "components": 6_106_088,
    "source_rows": 35_000,
    "occurrences": 69_747,
    "standard": 34_822,
    "native": 34_925,
}

EXPECTED_INPUT_BINDING: dict[str, str | int] = {
    "stage07_contract": "stage07_parser_evidence_contract_v2",
    "stage07_profile": "stage07_parser_evidence_profile_v2",
    "stage07_schema": "stage07_parser_evidence_schema_v2",
    "stage07_contract_fingerprint": (
        "c9561e6d08263b2a8824ff66f2a3aa8521e3ff880759abc14173cce440ced8a4"
    ),
    "stage07_schema_fingerprint": (
        "b0e0e83ea3d929b7df8a6a5f64c2e8eb026395a917da90e97a98858b27e9ead2"
    ),
    "stage07_logical_dataset_sha256": (
        "0f0706c1396803737f22845837753878bfd2e8b3f9af59b48cfcc1b8c5774530"
    ),
    "stage07_manifest_sha256": EXPECTED_STAGE07_MANIFEST_SHA256,
    "parser_bundle_fingerprint": (
        "f3c6db7e9f11ab75b2207be773e946d531dbba763008d9f7e5036d8c923dc2ae"
    ),
    "stage06_contract": "stage06_early_exact_deduplication_contract_v1",
    "stage06_profile": "stage06_early_exact_deduplication_profile_v1",
    "stage06_schema_fingerprint": (
        "9c07b7a4c3f7a5c43ad457dcf6f7fe3fd746d54d82a731139905b30828b6c9ce"
    ),
    "stage06_logical_dataset_sha256": (
        "2f6379c0cd5dc9654c03895cae6fdd48f3a7af528158c33e44d2030c816640b6"
    ),
    "stage06_row_map_logical_sha256": (
        "1ff9067c521ae93d28c300d7120a03c39681ce7830bf23b6619e2ca6129a4fe1"
    ),
    "stage06_input_binding_sha256": (
        "6ba224d6d24c3631aae8aac69f4a362bb054f01d9e3d09327ec6b0fdd85a0e7d"
    ),
    "stage06_manifest_sha256": EXPECTED_STAGE06_MANIFEST_SHA256,
    "candidate_rows": 51_779,
    "parsed_nonempty_rows": 51_774,
    "parsed_empty_rows": 5,
    "raw_component_rows": 6_106_088,
    "maximum_component_count": 881_338,
    "maximum_candidate_codepoints": 25_920_495,
    "source_rows": 35_000,
    "occurrence_rows": 69_747,
    "standard_occurrences": 34_822,
    "native_occurrences": 34_925,
}

LABEL_MAPPING = {
    "house": "PARSER_HOUSE",
    "category": "PARSER_CATEGORY",
    "near": "PARSER_NEAR",
    "house_number": "PARSER_HOUSE_NUMBER",
    "road": "PARSER_ROAD",
    "unit": "PARSER_UNIT",
    "level": "PARSER_LEVEL",
    "staircase": "PARSER_STAIRCASE",
    "entrance": "PARSER_ENTRANCE",
    "po_box": "PARSER_PO_BOX",
    "postcode": "PARSER_POSTCODE",
    "suburb": "PARSER_SUBURB",
    "city_district": "PARSER_CITY_DISTRICT",
    "city": "PARSER_CITY",
    "island": "PARSER_ISLAND",
    "state_district": "PARSER_STATE_DISTRICT",
    "state": "PARSER_STATE",
    "country_region": "PARSER_COUNTRY_REGION",
    "country": "PARSER_COUNTRY",
    "world_region": "PARSER_WORLD_REGION",
}

SOURCE_COPY_FIELDS = (
    "id",
    "source_file",
    "source_logical_record_number",
    "stable_source_row_id_v1",
    "source_file_sha256",
    "postcode",
    "city",
    "region_in_country",
    "country_iso_code",
    "stage03_clean_postcode",
    "stage03_clean_city",
    "stage03_clean_region_in_country",
    "stage03_clean_country_iso_code",
    "stage04_lower_postcode",
    "stage04_lower_city",
    "stage04_lower_region_in_country",
    "stage04_lower_country_iso_code",
    "stage06_standard_exact_candidate_id",
    "stage06_native_exact_candidate_id",
)

SCHEMA_VERSIONS = {
    "candidate_evidence": "stage08_candidate_evidence_schema_v1",
    "parser_component_evidence": "stage08_parser_component_evidence_schema_v1",
    "source_candidate_map": "stage08_source_candidate_map_schema_v1",
    "representation_occurrence_v1": ("stage08_representation_occurrence_schema_v1"),
}

_SCHEMA_DOMAIN = b"SAFE_STAGE08_ARROW_SCHEMA_V1"
_SCHEMA_BUNDLE_DOMAIN = b"SAFE_STAGE08_SCHEMA_BUNDLE_V1"
_CONTRACT_DOMAIN = b"SAFE_STAGE08_ADDRESS_EVIDENCE_CONTRACT_V1"
_MAPPING_DOMAIN = b"SAFE_STAGE08_LIBPOSTAL_LABEL_MAPPING_V1"
_CANDIDATE_DOMAIN = b"SAFE_STAGE08_CANDIDATE_EVIDENCE_LOGICAL_V1"
_COMPONENT_DOMAIN = b"SAFE_STAGE08_COMPONENT_EVIDENCE_LOGICAL_V1"
_SOURCE_DOMAIN = b"SAFE_STAGE08_SOURCE_CANDIDATE_MAP_LOGICAL_V1"
_OCCURRENCE_DOMAIN = b"SAFE_STAGE08_REPRESENTATION_OCCURRENCE_LOGICAL_V1"
_DATASET_DOMAIN = b"SAFE_STAGE08_ADDRESS_EVIDENCE_DATASET_V1"

_NETWORK_ATTEMPTS = 0
_PROTECTED_PATH_VIOLATIONS = 0
_ALLOWED_PROTECTED_ROOTS: tuple[Path, ...] = ()

OCCURRENCE_SQL = """SELECT
  stage08_source_row_ordinal,
  stable_source_row_id_v1,
  'STANDARD'::VARCHAR AS stage08_representation,
  0::UTINYINT AS stage08_representation_ordinal,
  stage06_standard_exact_candidate_id AS stage06_exact_candidate_id
FROM source_candidate_map
WHERE stage08_standard_representation_status = 'PRESENT'
UNION ALL
SELECT
  stage08_source_row_ordinal,
  stable_source_row_id_v1,
  'NATIVE'::VARCHAR AS stage08_representation,
  1::UTINYINT AS stage08_representation_ordinal,
  stage06_native_exact_candidate_id AS stage06_exact_candidate_id
FROM source_candidate_map
WHERE stage08_native_representation_status = 'PRESENT'
ORDER BY stage08_source_row_ordinal, stage08_representation_ordinal"""


class IndependentRereviewError(RuntimeError):
    """A privacy-safe independent verification assertion failed."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise IndependentRereviewError(code)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _audit(event: str, args: tuple[object, ...]) -> None:
    global _NETWORK_ATTEMPTS, _PROTECTED_PATH_VIOLATIONS
    if event.startswith("socket.") or event.startswith("http.client."):
        _NETWORK_ATTEMPTS += 1
        _fail("NETWORK_ACTIVITY_PROHIBITED")
    if (
        event != "open"
        or not args
        or not isinstance(args[0], (str, bytes, os.PathLike))
    ):
        return
    try:
        path = Path(os.fsdecode(args[0])).resolve(strict=False)
    except (OSError, TypeError, ValueError):
        return
    controlled = DATA_ROOT / "derived/controlled"
    if not path.is_relative_to(controlled):
        return
    if any(
        path == root or path.is_relative_to(root) for root in _ALLOWED_PROTECTED_ROOTS
    ):
        return
    _PROTECTED_PATH_VIOLATIONS += 1
    _fail("PROTECTED_PATH_SCOPE_VIOLATION")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(8 * 1024 * 1024):
                digest.update(chunk)
    except OSError:
        _fail("CONTROLLED_FILE_READ_FAILURE")
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _fail("CONTROLLED_JSON_INVALID")
    if not isinstance(value, dict):
        _fail("CONTROLLED_JSON_INVALID")
    return cast(dict[str, Any], value)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat(follow_symlinks=False).st_mode)


def _require_directory(path: Path) -> None:
    status = path.stat(follow_symlinks=False)
    if path.is_symlink() or not stat.S_ISDIR(status.st_mode) or _mode(path) != 0o700:
        _fail("CONTROLLED_DIRECTORY_INVALID")


def _require_file(path: Path) -> None:
    status = path.stat(follow_symlinks=False)
    if path.is_symlink() or not stat.S_ISREG(status.st_mode) or _mode(path) != 0o600:
        _fail("CONTROLLED_FILE_INVALID")


def _safe_relative_path(value: object) -> str:
    if not isinstance(value, str):
        _fail("MANIFEST_ARTIFACT_INVALID")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or str(relative) != value:
        _fail("MANIFEST_ARTIFACT_INVALID")
    return value


@dataclass(frozen=True, slots=True)
class Artifact:
    relative_path: str
    size_bytes: int
    sha256: str
    row_count: int | None


def _artifacts(
    root: Path,
    raw: object,
    *,
    directory: str | None = None,
    expected_paths: Sequence[str] | None = None,
) -> tuple[Artifact, ...]:
    if not isinstance(raw, list) or not raw:
        _fail("MANIFEST_ARTIFACT_INVALID")
    if expected_paths is not None and len(raw) != len(expected_paths):
        _fail("MANIFEST_ARTIFACT_INVALID")
    result: list[Artifact] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            _fail("MANIFEST_ARTIFACT_INVALID")
        relative = _safe_relative_path(item.get("relative_path"))
        if (
            directory is not None
            and relative != f"{directory}/part-{index:06d}.parquet"
        ):
            _fail("MANIFEST_ARTIFACT_ORDER_MISMATCH")
        if expected_paths is not None and relative != expected_paths[index - 1]:
            _fail("MANIFEST_ARTIFACT_ORDER_MISMATCH")
        size = item.get("size_bytes")
        sha256 = item.get("sha256")
        rows = item.get("row_count")
        if (
            not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or not isinstance(sha256, str)
            or len(sha256) != 64
            or (
                rows is not None
                and (not isinstance(rows, int) or isinstance(rows, bool))
            )
        ):
            _fail("MANIFEST_ARTIFACT_INVALID")
        path = root / relative
        _require_file(path)
        status = path.stat(follow_symlinks=False)
        if status.st_size != size or _sha256_file(path) != sha256:
            _fail("STORED_FILE_HASH_MISMATCH")
        result.append(Artifact(relative, size, sha256, rows))
    return tuple(result)


def _paths(root: Path, artifacts: Sequence[Artifact]) -> tuple[Path, ...]:
    return tuple(root / item.relative_path for item in artifacts)


def _reverify_artifacts(root: Path, artifacts: Sequence[Artifact]) -> None:
    for item in artifacts:
        path = root / item.relative_path
        _require_file(path)
        if (
            path.stat(follow_symlinks=False).st_size != item.size_bytes
            or _sha256_file(path) != item.sha256
        ):
            _fail("STORED_FILE_HASH_MISMATCH")


def _iter_batches(
    paths: Sequence[Path], columns: Sequence[str] | None, batch_rows: int
) -> Iterator[pa.RecordBatch]:
    for path in paths:
        try:
            parquet = pq.ParquetFile(path, page_checksum_verification=True)
            for batch in parquet.iter_batches(
                batch_size=batch_rows,
                columns=None if columns is None else list(columns),
                use_threads=False,
            ):
                yield batch
        except pa.ArrowException:
            _fail("PARQUET_REOPEN_FAILURE")


class RowStream:
    def __init__(self, batches: Iterator[pa.RecordBatch]) -> None:
        self._batches = batches
        self._batch: pa.RecordBatch | None = None
        self._index = 0

    def one(self) -> tuple[pa.RecordBatch, int]:
        while self._batch is None or self._index >= self._batch.num_rows:
            try:
                self._batch = next(self._batches)
            except StopIteration:
                _fail("ROW_STREAM_ENDED_EARLY")
            self._index = 0
        current = self._batch
        index = self._index
        self._index += 1
        return current, index

    def exhausted(self) -> bool:
        if self._batch is not None and self._index < self._batch.num_rows:
            return False
        try:
            self._batch = next(self._batches)
        except StopIteration:
            return True
        self._index = 0
        return self._batch.num_rows == 0 and self.exhausted()


class BatchStream:
    def __init__(self, batches: Iterator[pa.RecordBatch]) -> None:
        self._batches = batches
        self._batch: pa.RecordBatch | None = None
        self._offset = 0

    def take(self, count: int) -> Iterator[pa.RecordBatch]:
        remaining = count
        while remaining:
            while self._batch is None or self._offset >= self._batch.num_rows:
                try:
                    self._batch = next(self._batches)
                except StopIteration:
                    _fail("COMPONENT_STREAM_ENDED_EARLY")
                self._offset = 0
            length = min(remaining, self._batch.num_rows - self._offset)
            yield self._batch.slice(self._offset, length)
            self._offset += length
            remaining -= length

    def exhausted(self) -> bool:
        if self._batch is not None and self._offset < self._batch.num_rows:
            return False
        try:
            self._batch = next(self._batches)
        except StopIteration:
            return True
        self._offset = 0
        return self._batch.num_rows == 0 and self.exhausted()


def _metadata_text(metadata: Mapping[bytes, bytes] | None) -> dict[str, str]:
    try:
        return {
            key.decode("ascii"): value.decode("ascii")
            for key, value in sorted((metadata or {}).items())
        }
    except UnicodeError:
        _fail("SCHEMA_METADATA_INVALID")


def _describe_schema(schema: pa.Schema) -> dict[str, object]:
    return {
        "metadata": _metadata_text(schema.metadata),
        "fields": [
            {
                "name": field.name,
                "type": str(field.type),
                "nullable": field.nullable,
                "metadata": _metadata_text(field.metadata),
            }
            for field in schema
        ],
    }


def _schema_fingerprint(version: str, descriptor: Mapping[str, object]) -> str:
    payload = {"version": version, "schema": descriptor}
    encoded = _canonical_json(payload)
    digest = hashlib.sha256(_SCHEMA_DOMAIN)
    digest.update(struct.pack(">Q", len(encoded)))
    digest.update(encoded)
    return digest.hexdigest()


def _contract_fingerprint(schemas: Mapping[str, Mapping[str, object]]) -> str:
    base_schemas: dict[str, dict[str, object]] = {}
    for name in (
        "candidate_evidence",
        "parser_component_evidence",
        "source_candidate_map",
        "representation_occurrence_v1",
    ):
        descriptor = schemas.get(name)
        if not isinstance(descriptor, dict):
            _fail("SCHEMA_CONTRACT_MISMATCH")
        fields = descriptor.get("fields")
        if not isinstance(fields, list):
            _fail("SCHEMA_CONTRACT_MISMATCH")
        base_schemas[name] = {"metadata": {}, "fields": fields}
    payload = {
        "contract": "stage08_address_evidence_projection_contract_v1",
        "profile": "stage08_address_evidence_projection_profile_v1",
        "schema_bundle": "stage08_address_evidence_projection_schema_v1",
        "semantic_taxonomy": "stage08_semantic_classification_v1",
        "label_mapping": "stage08_libpostal_label_mapping_v1",
        "label_mapping_fingerprint": EXPECTED_MAPPING_FINGERPRINT,
        "occurrence_view": "stage08_representation_occurrence_view_v1",
        "occurrence_view_sql": OCCURRENCE_SQL,
        "logical_encoding": "stage08_address_evidence_logical_encoding_v1",
        "validation": "stage08_address_evidence_validation_v1",
        "manifest": "stage08_address_evidence_manifest_v1",
        "input_binding": EXPECTED_INPUT_BINDING,
        "base_schemas": base_schemas,
        "status_vocabularies": {
            "component_index": [
                "COMPONENT_INDEX_EMITTED",
                "COMPONENT_INDEX_EMITTED_WITH_UNMAPPED_LABEL",
                "COMPONENT_INDEX_EMPTY",
            ],
            "label_mapping": ["MAPPED_DEFINED_LABEL", "UNMAPPED_LABEL"],
            "representation_status": ["PRESENT", "ABSENT"],
            "representation_scope": ["STANDARD", "NATIVE", "BOTH"],
        },
        "ordering": {
            "candidate": "ASCENDING_UNSIGNED_CANDIDATE_ID_BYTES",
            "component": "ASCENDING_UNSIGNED_CANDIDATE_ID_BYTES_THEN_ORDINAL",
            "source": "EXACT_ACCEPTED_STAGE06_SOURCE_ROW_ORDER",
            "occurrence": "SOURCE_ROW_ORDINAL_THEN_REPRESENTATION_ORDINAL",
        },
        "losslessness": {
            "complete_stage07_row": True,
            "raw_nested_authoritative": True,
            "ordered_long_reversible": True,
            "duplicates_preserved": True,
            "unknown_labels_preserved": True,
            "source_rows_preserved": True,
            "occurrence_map_preserved": True,
        },
        "semantic_trust_fields": False,
        "component_readiness_gate": False,
        "reference_behavior": False,
        "parser_calls": 0,
    }
    encoded = _canonical_json(payload)
    digest = hashlib.sha256(_CONTRACT_DOMAIN)
    digest.update(struct.pack(">Q", len(encoded)))
    digest.update(encoded)
    return digest.hexdigest()


class CanonicalRelationHasher:
    def __init__(self, domain: bytes, schema: pa.Schema) -> None:
        self._digest = hashlib.sha256(domain)
        self._digest.update(bytes.fromhex(EXPECTED_CONTRACT_FINGERPRINT))
        logical_schema = _schema_fingerprint(
            "logical_relation_schema", _describe_schema(schema)
        )
        self._digest.update(bytes.fromhex(logical_schema))
        self.row_count = 0

    def _bytes(self, value: bytes) -> None:
        self._digest.update(struct.pack(">Q", len(value)))
        self._digest.update(value)

    def _scalar(self, value: pa.Scalar, data_type: pa.DataType) -> None:
        if not value.is_valid:
            self._digest.update(b"\x00")
            return
        self._digest.update(b"\x01")
        if pa.types.is_string(data_type) or pa.types.is_large_string(data_type):
            raw = value.as_py()
            if not isinstance(raw, str):
                _fail("LOGICAL_ENCODING_FAILURE")
            self._bytes(raw.encode("utf-8", errors="strict"))
            return
        if pa.types.is_fixed_size_binary(data_type):
            raw = value.as_py()
            if not isinstance(raw, bytes) or len(raw) != data_type.byte_width:
                _fail("LOGICAL_ENCODING_FAILURE")
            self._bytes(raw)
            return
        if pa.types.is_unsigned_integer(data_type):
            raw = value.as_py()
            if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
                _fail("LOGICAL_ENCODING_FAILURE")
            self._digest.update(struct.pack(">Q", raw))
            return
        if pa.types.is_boolean(data_type):
            raw = value.as_py()
            if not isinstance(raw, bool):
                _fail("LOGICAL_ENCODING_FAILURE")
            self._digest.update(b"\x01" if raw else b"\x00")
            return
        if pa.types.is_large_list(data_type) or pa.types.is_list(data_type):
            values = cast(pa.ListScalar, value).values
            self._digest.update(struct.pack(">Q", len(values)))
            for child in values:
                self._scalar(child, data_type.value_type)
            return
        if pa.types.is_struct(data_type):
            raw_struct = cast(pa.StructScalar, value)
            for position, child_field in enumerate(data_type):
                self._scalar(raw_struct[position], child_field.type)
            return
        _fail("LOGICAL_ENCODING_FAILURE")

    def update_batch(self, batch: pa.RecordBatch) -> None:
        for row in range(batch.num_rows):
            self._digest.update(b"\x02")
            for column, field in enumerate(batch.schema):
                self._scalar(batch.column(column)[row], field.type)
            self.row_count += 1

    def hexdigest(self) -> str:
        result = self._digest.copy()
        result.update(b"\x00ROWS" + struct.pack(">Q", self.row_count))
        return result.hexdigest()


def _occurrence_schema(descriptor: Mapping[str, object]) -> pa.Schema:
    type_map: dict[str, pa.DataType] = {
        "uint64": pa.uint64(),
        "uint8": pa.uint8(),
        "string": pa.string(),
        "fixed_size_binary[32]": pa.binary(32),
    }
    fields_raw = descriptor.get("fields")
    metadata_raw = descriptor.get("metadata")
    if not isinstance(fields_raw, list) or not isinstance(metadata_raw, dict):
        _fail("OCCURRENCE_SCHEMA_INVALID")
    fields: list[pa.Field] = []
    for item in fields_raw:
        if not isinstance(item, dict) or item.get("type") not in type_map:
            _fail("OCCURRENCE_SCHEMA_INVALID")
        field_metadata = item.get("metadata")
        if not isinstance(field_metadata, dict):
            _fail("OCCURRENCE_SCHEMA_INVALID")
        fields.append(
            pa.field(
                str(item.get("name")),
                type_map[str(item["type"])],
                nullable=bool(item.get("nullable")),
                metadata={
                    str(k).encode("ascii"): str(v).encode("ascii")
                    for k, v in field_metadata.items()
                },
            )
        )
    schema = pa.schema(
        fields,
        metadata={
            str(k).encode("ascii"): str(v).encode("ascii")
            for k, v in metadata_raw.items()
        },
    )
    if _describe_schema(schema) != descriptor:
        _fail("OCCURRENCE_SCHEMA_INVALID")
    return schema


def _scalar_equal(left: pa.Scalar, right: pa.Scalar) -> bool:
    return bool(left.equals(right))


def _column(batch: pa.RecordBatch, name: str) -> pa.Array:
    position = batch.schema.get_field_index(name)
    if position < 0:
        _fail("REQUIRED_COLUMN_ABSENT")
    return batch.column(position)


def _topology(root: Path, expected_files: set[str]) -> tuple[int, int, int]:
    directories = 1
    files: set[str] = set()
    symlinks = 0
    for current, names, file_names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        _require_directory(current_path)
        for name in names:
            path = current_path / name
            if path.is_symlink():
                symlinks += 1
            else:
                _require_directory(path)
                directories += 1
        for name in file_names:
            path = current_path / name
            if path.is_symlink():
                symlinks += 1
            else:
                _require_file(path)
            files.add(path.relative_to(root).as_posix())
    if files != expected_files:
        _fail("UNEXPECTED_TERMINAL_PUBLICATION_FILE")
    return directories, len(files), symlinks


def _verify_mapping(payload: Mapping[str, object]) -> None:
    expected_fingerprint_payload = {
        "version": "stage08_libpostal_label_mapping_v1",
        "source_commit": "25099c506612b34b23b1bfe286ca6321fcf06f35",
        "source_readme_sha256": (
            "14b9589f17f2cd88b2972d89bd98b463ed598885ec9b8778b11a8a128d7d43cb"
        ),
        "comparison": "CASE_SENSITIVE_EXACT_STRING",
        "mapping": list(LABEL_MAPPING.items()),
        "unmapped": {
            "status": "UNMAPPED_LABEL",
            "safe_component": None,
            "raw_preserved": True,
        },
    }
    encoded = _canonical_json(expected_fingerprint_payload)
    digest = hashlib.sha256(_MAPPING_DOMAIN)
    digest.update(struct.pack(">Q", len(encoded)))
    digest.update(encoded)
    if digest.hexdigest() != EXPECTED_MAPPING_FINGERPRINT:
        _fail("INDEPENDENT_MAPPING_FINGERPRINT_MISMATCH")
    if (
        payload.get("version") != "stage08_libpostal_label_mapping_v1"
        or payload.get("fingerprint") != EXPECTED_MAPPING_FINGERPRINT
        or payload.get("mapping") != LABEL_MAPPING
        or len(LABEL_MAPPING) != 20
        or payload.get("semantic_truth_claim") is not False
    ):
        _fail("MAPPING_CONTRACT_MISMATCH")


def _dataset_fingerprint(relations: Mapping[str, str]) -> str:
    digest = hashlib.sha256(_DATASET_DOMAIN)
    for value in (
        EXPECTED_CONTRACT_FINGERPRINT,
        EXPECTED_SCHEMA_BUNDLE_FINGERPRINT,
        EXPECTED_MAPPING_FINGERPRINT,
        relations["candidate_evidence"],
        relations["parser_component_evidence"],
        relations["source_candidate_map"],
        relations["representation_occurrence_v1"],
    ):
        digest.update(bytes.fromhex(value))
    for count in (
        EXPECTED_COUNTS["candidates"],
        EXPECTED_COUNTS["components"],
        EXPECTED_COUNTS["source_rows"],
        EXPECTED_COUNTS["occurrences"],
    ):
        digest.update(struct.pack(">Q", count))
    return digest.hexdigest()


def _run_review(output_directory: Path, review_sha: str) -> dict[str, object]:
    if os.environ.get("SAFE_EXECUTION_SITE") != "goethe-nhr" or not os.environ.get(
        "SLURM_JOB_ID"
    ):
        _fail("GOETHE_SLURM_GUARD_FAILURE")
    if review_sha != os.environ.get("STAGE08_REVIEW_GIT_SHA") or len(review_sha) != 40:
        _fail("REVIEW_GIT_IDENTITY_MISMATCH")
    if platform.python_version() != "3.14.3" or pa.__version__ != "25.0.0":
        _fail("REVIEW_RUNTIME_MISMATCH")
    for path in (ARTIFACT_ROOT, STAGE07_ROOT, STAGE06_ROOT, output_directory):
        lowered = path.as_posix().casefold()
        if "holdout" in lowered:
            _fail("HOLDOUT_ACCESS_PROHIBITED")
        if "production" in lowered:
            _fail("PRODUCTION_ACCESS_PROHIBITED")

    _require_directory(ARTIFACT_ROOT)

    incomplete_siblings = 0
    sibling_prefix = f".{ARTIFACT_ROOT.name}."
    try:
        for item in os.scandir(ARTIFACT_ROOT.parent):
            if item.name.startswith(sibling_prefix) and item.name.endswith(
                ".in_progress"
            ):
                incomplete_siblings += 1
    except OSError:
        _fail("PUBLICATION_PARENT_READ_FAILURE")
    if incomplete_siblings:
        _fail("INCOMPLETE_SIBLING_ATTEMPT_PRESENT")

    manifest_path = ARTIFACT_ROOT / "stage08_address_evidence_manifest.json"
    success_path = ARTIFACT_ROOT / "_SUCCESS.json"
    _require_file(manifest_path)
    _require_file(success_path)
    if (ARTIFACT_ROOT / "_IN_PROGRESS").exists() or (
        ARTIFACT_ROOT / "_IN_PROGRESS"
    ).is_symlink():
        _fail("IN_PROGRESS_MARKER_PRESENT")
    if _sha256_file(manifest_path) != EXPECTED_MANIFEST_SHA256:
        _fail("MANIFEST_SHA256_MISMATCH")
    manifest = _load_json(manifest_path)
    success = _load_json(success_path)
    scientific = manifest.get("scientific_identity")
    physical = manifest.get("physical_identity")
    metrics = manifest.get("development_metrics")
    reconciliation = manifest.get("reconciliation")
    privacy = manifest.get("privacy")
    operational = manifest.get("operational_provenance")
    validation = manifest.get("validation")
    if not all(
        isinstance(item, dict)
        for item in (
            scientific,
            physical,
            metrics,
            reconciliation,
            privacy,
            operational,
            validation,
        )
    ):
        _fail("STAGE08_MANIFEST_SECTION_INVALID")
    scientific = cast(dict[str, Any], scientific)
    physical = cast(dict[str, Any], physical)
    metrics = cast(dict[str, Any], metrics)
    reconciliation = cast(dict[str, Any], reconciliation)
    privacy = cast(dict[str, Any], privacy)
    operational = cast(dict[str, Any], operational)
    validation = cast(dict[str, Any], validation)

    expected_scientific_scalars = {
        "contract": "stage08_address_evidence_projection_contract_v1",
        "profile": "stage08_address_evidence_projection_profile_v1",
        "schema_bundle": "stage08_address_evidence_projection_schema_v1",
        "semantic_taxonomy": "stage08_semantic_classification_v1",
        "label_mapping": "stage08_libpostal_label_mapping_v1",
        "occurrence_view": "stage08_representation_occurrence_view_v1",
        "logical_encoding": "stage08_address_evidence_logical_encoding_v1",
        "contract_fingerprint": EXPECTED_CONTRACT_FINGERPRINT,
        "schema_bundle_fingerprint": EXPECTED_SCHEMA_BUNDLE_FINGERPRINT,
        "label_mapping_fingerprint": EXPECTED_MAPPING_FINGERPRINT,
        "logical_dataset_sha256": EXPECTED_LOGICAL_DATASET_SHA256,
    }
    if any(
        scientific.get(key) != value
        for key, value in expected_scientific_scalars.items()
    ):
        _fail("SCIENTIFIC_IDENTITY_MISMATCH")
    if (
        scientific.get("input_binding") != EXPECTED_INPUT_BINDING
        or scientific.get("schema_fingerprints") != EXPECTED_SCHEMA_FINGERPRINTS
        or scientific.get("relation_logical_fingerprints")
        != EXPECTED_RELATION_LOGICAL_FINGERPRINTS
        or operational.get("execution_git_sha") != EXECUTABLE_SHA
    ):
        _fail("SCIENTIFIC_BINDING_MISMATCH")

    expected_success = {
        "status": "STAGE08_ADDRESS_EVIDENCE_IMPLEMENTATION_CANDIDATE_MATERIALIZED",
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "logical_dataset_sha256": EXPECTED_LOGICAL_DATASET_SHA256,
        "contract_fingerprint": EXPECTED_CONTRACT_FINGERPRINT,
        "schema_bundle_fingerprint": EXPECTED_SCHEMA_BUNDLE_FINGERPRINT,
        "candidate_rows": EXPECTED_COUNTS["candidates"],
        "component_rows": EXPECTED_COUNTS["components"],
        "source_rows": EXPECTED_COUNTS["source_rows"],
        "occurrence_rows": EXPECTED_COUNTS["occurrences"],
    }
    if success != expected_success:
        _fail("SUCCESS_MARKER_BINDING_MISMATCH")

    candidate_artifacts = _artifacts(
        ARTIFACT_ROOT,
        physical.get("candidate_evidence_artifacts"),
        directory="candidate_evidence/data",
    )
    component_artifacts = _artifacts(
        ARTIFACT_ROOT,
        physical.get("parser_component_evidence_artifacts"),
        directory="parser_component_evidence/data",
    )
    source_artifacts = _artifacts(
        ARTIFACT_ROOT,
        physical.get("source_candidate_map_artifacts"),
        directory="source_candidate_map/data",
    )
    metadata_artifacts = _artifacts(
        ARTIFACT_ROOT,
        physical.get("metadata_artifacts"),
        expected_paths=(
            "metadata/stage08_libpostal_label_mapping_v1.json",
            "metadata/stage08_schema_contract_v1.json",
        ),
    )
    expected_files = {
        "stage08_address_evidence_manifest.json",
        "_SUCCESS.json",
        *(item.relative_path for item in candidate_artifacts),
        *(item.relative_path for item in component_artifacts),
        *(item.relative_path for item in source_artifacts),
        *(item.relative_path for item in metadata_artifacts),
    }
    directory_count, file_count, symlink_count = _topology(
        ARTIFACT_ROOT, expected_files
    )
    if (directory_count, file_count, symlink_count) != (8, 52, 0):
        _fail("PUBLICATION_TOPOLOGY_MISMATCH")

    mapping_payload = _load_json(
        ARTIFACT_ROOT / "metadata/stage08_libpostal_label_mapping_v1.json"
    )
    schema_payload = _load_json(
        ARTIFACT_ROOT / "metadata/stage08_schema_contract_v1.json"
    )
    _verify_mapping(mapping_payload)
    schemas_raw = schema_payload.get("schemas")
    if (
        not isinstance(schemas_raw, dict)
        or schema_payload.get("contract_fingerprint") != EXPECTED_CONTRACT_FINGERPRINT
        or schema_payload.get("schema_bundle_fingerprint")
        != EXPECTED_SCHEMA_BUNDLE_FINGERPRINT
        or schema_payload.get("schema_fingerprints") != EXPECTED_SCHEMA_FINGERPRINTS
        or schema_payload.get("input_binding") != EXPECTED_INPUT_BINDING
        or schema_payload.get("allowed_semantic_classes")
        != [
            "SOURCE_VALUE",
            "SOURCE_LINEAGE",
            "UPSTREAM_DERIVED_REPRESENTATION",
            "TRUSTED_SOURCE_CONTEXT",
            "PARSER_TECHNICAL_PROVENANCE",
            "PARSER_EVIDENCE",
            "STRUCTURAL_DIAGNOSTIC",
            "MECHANICAL_INDEX",
        ]
        or schema_payload.get("prohibited_output_classes")
        != ["HYPOTHESIS", "REFERENCE_EVIDENCE", "GEOCODER_RESULT", "ACCEPTED_MATCH"]
        or schema_payload.get("occurrence_view")
        != {
            "version": "stage08_representation_occurrence_view_v1",
            "materialized": False,
            "canonical_sql": OCCURRENCE_SQL,
        }
    ):
        _fail("SCHEMA_CONTRACT_MISMATCH")
    schemas_raw = cast(dict[str, dict[str, object]], schemas_raw)
    if _contract_fingerprint(schemas_raw) != EXPECTED_CONTRACT_FINGERPRINT:
        _fail("INDEPENDENT_CONTRACT_FINGERPRINT_MISMATCH")
    independently_computed_schema_fingerprints: dict[str, str] = {}
    for relation, expected in EXPECTED_SCHEMA_FINGERPRINTS.items():
        descriptor = schemas_raw.get(relation)
        if not isinstance(descriptor, dict):
            _fail("SCHEMA_CONTRACT_MISMATCH")
        independently_computed_schema_fingerprints[relation] = _schema_fingerprint(
            SCHEMA_VERSIONS[relation], descriptor
        )
        if independently_computed_schema_fingerprints[relation] != expected:
            _fail("INDEPENDENT_SCHEMA_FINGERPRINT_MISMATCH")
    bundle_payload = {
        "version": "stage08_address_evidence_projection_schema_v1",
        "schemas": independently_computed_schema_fingerprints,
    }
    bundle_encoded = _canonical_json(bundle_payload)
    bundle_digest = hashlib.sha256(_SCHEMA_BUNDLE_DOMAIN)
    bundle_digest.update(struct.pack(">Q", len(bundle_encoded)))
    bundle_digest.update(bundle_encoded)
    if bundle_digest.hexdigest() != EXPECTED_SCHEMA_BUNDLE_FINGERPRINT:
        _fail("INDEPENDENT_SCHEMA_BUNDLE_FINGERPRINT_MISMATCH")

    expected_metrics = {
        "CANDIDATE_ROWS": EXPECTED_COUNTS["candidates"],
        "COMPONENT_ROWS": EXPECTED_COUNTS["components"],
        "SOURCE_ROWS": EXPECTED_COUNTS["source_rows"],
        "OCCURRENCE_ROWS": EXPECTED_COUNTS["occurrences"],
        "STANDARD_OCCURRENCES": EXPECTED_COUNTS["standard"],
        "NATIVE_OCCURRENCES": EXPECTED_COUNTS["native"],
        "MAPPED_COMPONENT_ROWS": EXPECTED_COUNTS["components"],
        "UNMAPPED_COMPONENT_ROWS": 0,
        "PARSER_CALLS": 0,
        "SEMANTIC_TRUST_FIELDS": 0,
        "REFERENCE_LOOKUPS": 0,
        "NETWORK_CALLS": 0,
    }
    if any(metrics.get(key) != value for key, value in expected_metrics.items()):
        _fail("RECORDED_AGGREGATE_MISMATCH")
    for key in (
        "dangling_component_rows",
        "unmapped_component_rows",
        "component_count_mismatches",
        "occurrence_count_mismatches",
    ):
        if reconciliation.get(key) != 0:
            _fail("RECORDED_RECONCILIATION_MISMATCH")
    if privacy != {
        "row_values_in_manifest": False,
        "protected_values_logged": False,
        "external_services": False,
        "holdout_access": False,
        "production_access": False,
    }:
        _fail("RECORDED_PRIVACY_BOUNDARY_MISMATCH")
    if validation.get("version") != "stage08_address_evidence_validation_v1" or any(
        value != "PASS" for key, value in validation.items() if key != "version"
    ):
        _fail("RECORDED_VALIDATION_MISMATCH")
    if os.environ.get("STAGE08_PRODUCER_STDERR_EMPTY") != "true":
        _fail("PRODUCER_STDERR_EVIDENCE_MISMATCH")

    candidate_paths = _paths(ARTIFACT_ROOT, candidate_artifacts)
    component_paths = _paths(ARTIFACT_ROOT, component_artifacts)
    source_paths = _paths(ARTIFACT_ROOT, source_artifacts)
    relation_paths = {
        "candidate_evidence": candidate_paths,
        "parser_component_evidence": component_paths,
        "source_candidate_map": source_paths,
    }
    actual_schemas: dict[str, pa.Schema] = {}
    for relation, paths in relation_paths.items():
        first = pq.ParquetFile(paths[0], page_checksum_verification=True).schema_arrow
        if _describe_schema(first) != schemas_raw[relation]:
            _fail("PARQUET_SCHEMA_CONTRACT_MISMATCH")
        for path in paths[1:]:
            observed = pq.ParquetFile(
                path, page_checksum_verification=True
            ).schema_arrow
            if not observed.equals(first, check_metadata=True):
                _fail("PARQUET_SHARD_SCHEMA_MISMATCH")
        actual_schemas[relation] = first
    occurrence_schema = _occurrence_schema(schemas_raw["representation_occurrence_v1"])

    stage07_manifest_path = STAGE07_ROOT / "stage07_parser_evidence_manifest.json"
    stage06_manifest_path = STAGE06_ROOT / "stage06_manifest.json"
    _require_file(stage07_manifest_path)
    _require_file(stage06_manifest_path)
    if _sha256_file(stage07_manifest_path) != EXPECTED_STAGE07_MANIFEST_SHA256:
        _fail("STAGE07_MANIFEST_BINDING_MISMATCH")
    if _sha256_file(stage06_manifest_path) != EXPECTED_STAGE06_MANIFEST_SHA256:
        _fail("STAGE06_MANIFEST_BINDING_MISMATCH")
    stage07_manifest = _load_json(stage07_manifest_path)
    stage06_manifest = _load_json(stage06_manifest_path)
    stage07_physical = stage07_manifest.get("physical_identity")
    stage06_physical = stage06_manifest.get("physical_identity")
    if not isinstance(stage07_physical, dict) or not isinstance(stage06_physical, dict):
        _fail("UPSTREAM_MANIFEST_INVALID")
    stage07_artifacts = _artifacts(
        STAGE07_ROOT,
        stage07_physical.get("registry_artifacts"),
        directory="registry/data",
    )
    stage06_row_artifacts = _artifacts(
        STAGE06_ROOT,
        stage06_physical.get("row_map_artifacts"),
        directory="row_map/data",
    )

    candidate_schema = actual_schemas["candidate_evidence"]
    component_schema = actual_schemas["parser_component_evidence"]
    source_schema = actual_schemas["source_candidate_map"]
    candidate_hasher = CanonicalRelationHasher(_CANDIDATE_DOMAIN, candidate_schema)
    component_hasher = CanonicalRelationHasher(_COMPONENT_DOMAIN, component_schema)
    source_hasher = CanonicalRelationHasher(_SOURCE_DOMAIN, source_schema)
    occurrence_hasher = CanonicalRelationHasher(_OCCURRENCE_DOMAIN, occurrence_schema)

    stage07_paths = _paths(STAGE07_ROOT, stage07_artifacts)
    stage07_schema = pq.ParquetFile(
        stage07_paths[0], page_checksum_verification=True
    ).schema_arrow
    stage07_columns = tuple(stage07_schema.names)
    if tuple(candidate_schema.names[: len(stage07_columns)]) != stage07_columns:
        _fail("STAGE07_CANDIDATE_SCHEMA_PREFIX_MISMATCH")
    stage07_rows = RowStream(_iter_batches(stage07_paths, stage07_columns, 8))
    candidate_rows = RowStream(_iter_batches(candidate_paths, None, 8))
    component_rows = BatchStream(_iter_batches(component_paths, None, 65_536))

    candidate_ids: set[bytes] = set()
    expected_occurrences: dict[bytes, int] = {}
    stage07_mismatches = 0
    component_mismatches = 0
    component_count_mismatches = 0
    dangling_component_rows = 0
    component_count = 0
    unmapped_count = 0
    previous_id: bytes | None = None
    for candidate_ordinal in range(EXPECTED_COUNTS["candidates"]):
        upstream_batch, upstream_index = stage07_rows.one()
        output_batch, output_index = candidate_rows.one()
        row_mismatch = False
        for name in stage07_columns:
            if not _scalar_equal(
                _column(upstream_batch, name)[upstream_index],
                _column(output_batch, name)[output_index],
            ):
                row_mismatch = True
        candidate_id = _column(upstream_batch, "stage06_exact_candidate_id")[
            upstream_index
        ].as_py()
        if not isinstance(candidate_id, bytes):
            _fail("CANDIDATE_ID_INVALID")
        if previous_id is not None and candidate_id <= previous_id:
            row_mismatch = True
        previous_id = candidate_id
        candidate_ids.add(candidate_id)
        expected_occurrences[candidate_id] = int(
            _column(upstream_batch, "stage06_occurrence_count")[upstream_index].as_py()
        )
        raw_components = cast(
            pa.ListScalar,
            _column(upstream_batch, "stage07_libpostal_components")[upstream_index],
        ).values
        if not isinstance(raw_components, pa.StructArray):
            _fail("NESTED_COMPONENT_STRUCTURE_INVALID")
        raw_count = len(raw_components)
        mapped_count = 0
        offset = 0
        while offset < raw_count:
            requested = min(65_536, raw_count - offset)
            consumed = 0
            for observed in component_rows.take(requested):
                length = observed.num_rows
                labels = raw_components.field("label").slice(offset + consumed, length)
                values = raw_components.field("value").slice(offset + consumed, length)
                mismatch = False
                ids = _column(observed, "stage06_exact_candidate_id").to_pylist()
                ordinals = _column(observed, "stage08_component_ordinal").to_pylist()
                if ids != [candidate_id] * length or ordinals != list(
                    range(offset + consumed, offset + consumed + length)
                ):
                    mismatch = True
                dangling_component_rows += sum(value != candidate_id for value in ids)
                if not _column(observed, "stage08_raw_libpostal_label").equals(labels):
                    mismatch = True
                if not _column(observed, "stage08_raw_libpostal_value").equals(values):
                    mismatch = True
                label_values = labels.to_pylist()
                expected_safe = [
                    LABEL_MAPPING.get(str(label)) for label in label_values
                ]
                expected_status = [
                    "MAPPED_DEFINED_LABEL" if value is not None else "UNMAPPED_LABEL"
                    for value in expected_safe
                ]
                mapped_count += sum(value is not None for value in expected_safe)
                unmapped_count += sum(value is None for value in expected_safe)
                if (
                    _column(observed, "stage08_label_mapping_status").to_pylist()
                    != expected_status
                    or _column(
                        observed, "stage08_safe_parser_evidence_component"
                    ).to_pylist()
                    != expected_safe
                    or _column(observed, "stage08_evidence_class").to_pylist()
                    != ["PARSER_EVIDENCE"] * length
                ):
                    mismatch = True
                if mismatch:
                    component_mismatches += length
                component_hasher.update_batch(observed)
                component_count += length
                consumed += length
            offset += requested
        standard_count = int(
            _column(upstream_batch, "stage06_standard_occurrence_count")[
                upstream_index
            ].as_py()
        )
        native_count = int(
            _column(upstream_batch, "stage06_native_occurrence_count")[
                upstream_index
            ].as_py()
        )
        scope = (
            "BOTH"
            if standard_count and native_count
            else ("STANDARD" if standard_count else "NATIVE")
        )
        expected_appended = {
            "stage08_representation_scope": scope,
            "stage08_raw_component_count": raw_count,
            "stage08_mapped_component_count": mapped_count,
            "stage08_unmapped_component_count": raw_count - mapped_count,
            "stage08_component_index_status": (
                "COMPONENT_INDEX_EMPTY"
                if raw_count == 0
                else (
                    "COMPONENT_INDEX_EMITTED_WITH_UNMAPPED_LABEL"
                    if raw_count != mapped_count
                    else "COMPONENT_INDEX_EMITTED"
                )
            ),
        }
        if (
            _column(output_batch, "stage08_raw_component_count")[output_index].as_py()
            != raw_count
            or _column(output_batch, "stage08_mapped_component_count")[
                output_index
            ].as_py()
            != mapped_count
            or _column(output_batch, "stage08_unmapped_component_count")[
                output_index
            ].as_py()
            != raw_count - mapped_count
        ):
            component_count_mismatches += 1
        for name, expected_value in expected_appended.items():
            if _column(output_batch, name)[output_index].as_py() != expected_value:
                row_mismatch = True
        if row_mismatch:
            stage07_mismatches += 1
        candidate_hasher.update_batch(output_batch.slice(output_index, 1))
    if not stage07_rows.exhausted() or not candidate_rows.exhausted():
        _fail("CANDIDATE_TOTALITY_MISMATCH")
    if not component_rows.exhausted():
        _fail("COMPONENT_TOTALITY_MISMATCH")

    stage06_paths = _paths(STAGE06_ROOT, stage06_row_artifacts)
    stage06_rows = RowStream(_iter_batches(stage06_paths, SOURCE_COPY_FIELDS, 32))
    output_source_rows = RowStream(_iter_batches(source_paths, None, 32))
    observed_occurrences: Counter[bytes] = Counter()
    source_mismatches = 0
    dangling_candidates = 0
    standard_occurrences = 0
    native_occurrences = 0
    for source_ordinal in range(EXPECTED_COUNTS["source_rows"]):
        upstream_batch, upstream_index = stage06_rows.one()
        output_batch, output_index = output_source_rows.one()
        mismatch = False
        for name in SOURCE_COPY_FIELDS:
            if not _scalar_equal(
                _column(upstream_batch, name)[upstream_index],
                _column(output_batch, name)[output_index],
            ):
                mismatch = True
        if (
            _column(output_batch, "stage08_source_row_ordinal")[output_index].as_py()
            != source_ordinal
        ):
            mismatch = True
        stable_id = _column(upstream_batch, "stable_source_row_id_v1")[
            upstream_index
        ].as_py()
        if not isinstance(stable_id, bytes):
            _fail("SOURCE_ID_INVALID")
        for representation, representation_ordinal, field, status_field in (
            (
                "STANDARD",
                0,
                "stage06_standard_exact_candidate_id",
                "stage08_standard_representation_status",
            ),
            (
                "NATIVE",
                1,
                "stage06_native_exact_candidate_id",
                "stage08_native_representation_status",
            ),
        ):
            candidate_id = _column(upstream_batch, field)[upstream_index].as_py()
            representation_status = "ABSENT" if candidate_id is None else "PRESENT"
            if (
                _column(output_batch, status_field)[output_index].as_py()
                != representation_status
            ):
                mismatch = True
            if candidate_id is None:
                continue
            if not isinstance(candidate_id, bytes):
                _fail("SOURCE_CANDIDATE_ID_INVALID")
            if candidate_id not in candidate_ids:
                dangling_candidates += 1
            observed_occurrences[candidate_id] += 1
            values = (
                source_ordinal,
                stable_id,
                representation,
                representation_ordinal,
                candidate_id,
            )
            occurrence_batch = pa.RecordBatch.from_arrays(
                [
                    pa.array((value,), type=field.type)
                    for value, field in zip(values, occurrence_schema)
                ],
                schema=occurrence_schema,
            )
            occurrence_hasher.update_batch(occurrence_batch)
            if representation == "STANDARD":
                standard_occurrences += 1
            else:
                native_occurrences += 1
        if mismatch:
            source_mismatches += 1
        source_hasher.update_batch(output_batch.slice(output_index, 1))
    if not stage06_rows.exhausted() or not output_source_rows.exhausted():
        _fail("SOURCE_TOTALITY_MISMATCH")

    occurrence_count_mismatches = sum(
        observed_occurrences[candidate_id] != expected
        for candidate_id, expected in expected_occurrences.items()
    )
    relations = {
        "candidate_evidence": candidate_hasher.hexdigest(),
        "parser_component_evidence": component_hasher.hexdigest(),
        "source_candidate_map": source_hasher.hexdigest(),
        "representation_occurrence_v1": occurrence_hasher.hexdigest(),
    }
    independent_logical_dataset = _dataset_fingerprint(relations)
    scientific_fingerprint_pass = (
        relations == EXPECTED_RELATION_LOGICAL_FINGERPRINTS
        and independent_logical_dataset == EXPECTED_LOGICAL_DATASET_SHA256
    )

    _reverify_artifacts(
        ARTIFACT_ROOT,
        (
            *candidate_artifacts,
            *component_artifacts,
            *source_artifacts,
            *metadata_artifacts,
        ),
    )
    _require_directory(ARTIFACT_ROOT)
    _require_file(manifest_path)
    _require_file(success_path)
    if (
        _sha256_file(manifest_path) != EXPECTED_MANIFEST_SHA256
        or _load_json(success_path) != expected_success
        or (ARTIFACT_ROOT / "_IN_PROGRESS").exists()
        or (ARTIFACT_ROOT / "_IN_PROGRESS").is_symlink()
        or _topology(ARTIFACT_ROOT, expected_files) != (8, 52, 0)
    ):
        _fail("FINAL_PERSISTENT_PUBLICATION_IDENTITY_MISMATCH")

    aggregate_pass = (
        candidate_hasher.row_count == EXPECTED_COUNTS["candidates"]
        and component_count == EXPECTED_COUNTS["components"]
        and source_hasher.row_count == EXPECTED_COUNTS["source_rows"]
        and occurrence_hasher.row_count == EXPECTED_COUNTS["occurrences"]
        and standard_occurrences == EXPECTED_COUNTS["standard"]
        and native_occurrences == EXPECTED_COUNTS["native"]
        and unmapped_count == 0
    )
    all_mismatches = (
        stage07_mismatches
        + component_mismatches
        + component_count_mismatches
        + dangling_component_rows
        + source_mismatches
        + dangling_candidates
        + occurrence_count_mismatches
    )
    verdict = (
        "STAGE08_ADDRESS_EVIDENCE_INDEPENDENT_REREVIEW_PASS"
        if aggregate_pass and scientific_fingerprint_pass and all_mismatches == 0
        else "STAGE08_ADDRESS_EVIDENCE_INDEPENDENT_REREVIEW_FAIL"
    )
    return {
        "review_version": REVIEW_VERSION,
        "verdict": verdict,
        "candidate_sha": CANDIDATE_SHA,
        "executable_sha": EXECUTABLE_SHA,
        "review_git_sha": review_sha,
        "goethe_review_job_id": os.environ["SLURM_JOB_ID"],
        "artifact_identity": {
            "exact_path": ARTIFACT_ROOT.as_posix(),
            "nofollow_real_directory": True,
            "symlink": False,
            "mode": "0700",
            "persistent_identity_basis": [
                "EXACT_PATH",
                "NOFOLLOW_DIRECTORY_TOPOLOGY",
                "MANIFEST_SHA256",
                "SUCCESS_BINDING",
                "COMPLETE_FILE_INVENTORY",
                "STORED_FILE_SHA256",
                "RELATION_LOGICAL_FINGERPRINTS",
                "LOGICAL_DATASET_SHA256",
            ],
            "historical_publication_filesystem_identity": {
                "job_id": "1764273",
                "st_dev": HISTORICAL_JOB_1764273_FILESYSTEM_IDENTITY[0],
                "st_ino": HISTORICAL_JOB_1764273_FILESYSTEM_IDENTITY[1],
                "cross_job_equality_gate": False,
            },
        },
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "logical_dataset_sha256": independent_logical_dataset,
        "aggregate_reconciliation": {
            "candidates": candidate_hasher.row_count,
            "components": component_count,
            "source_rows": source_hasher.row_count,
            "occurrences": occurrence_hasher.row_count,
            "standard": standard_occurrences,
            "native": native_occurrences,
            "dangling_components": dangling_component_rows,
            "unmapped_components": unmapped_count,
            "component_count_mismatches": component_count_mismatches,
            "occurrence_count_mismatches": occurrence_count_mismatches,
        },
        "stage07_to_stage08_equality_mismatch_count": stage07_mismatches,
        "component_reconstruction_mismatch_count": component_mismatches
        + component_count_mismatches,
        "source_map_back_mismatch_count": source_mismatches
        + dangling_candidates
        + occurrence_count_mismatches,
        "filesystem_publication": {
            "verdict": "PASS",
            "directories": directory_count,
            "files": file_count,
            "symlinks": symlink_count,
            "in_progress_absent": True,
            "incomplete_sibling_attempts": incomplete_siblings,
            "manifest_listed_files_complete": True,
            "unexpected_terminal_files": 0,
            "stored_file_hashes_match": True,
            "producer_stderr_empty": os.environ.get("STAGE08_PRODUCER_STDERR_EMPTY")
            == "true",
            "cross_job_device_inode_equality_required": False,
        },
        "scientific_fingerprints": {
            "verdict": "PASS" if scientific_fingerprint_pass else "FAIL",
            "contract_fingerprint": EXPECTED_CONTRACT_FINGERPRINT,
            "schema_bundle_fingerprint": EXPECTED_SCHEMA_BUNDLE_FINGERPRINT,
            "schema_fingerprints": EXPECTED_SCHEMA_FINGERPRINTS,
            "mapping_fingerprint": EXPECTED_MAPPING_FINGERPRINT,
            "relation_logical_fingerprints": relations,
            "stage06_stage07_bindings": "PASS",
            "twenty_label_mapping": "PASS",
        },
        "privacy_and_prohibited_activity": {
            "verdict": "PASS",
            "parser_calls": 0,
            "reference_lookups": 0,
            "network_calls": _NETWORK_ATTEMPTS,
            "geocoder_calls": 0,
            "holdout_access": False,
            "production_access": False,
            "protected_path_scope_violations": _PROTECTED_PATH_VIOLATIONS,
        },
        "candidate_remained_unchanged": True,
        "review_harness_history": {
            "job_1764372": {
                "classification": "REVIEW_HARNESS_FAILURE",
                "invalid_assumption": "CROSS_JOB_DEVICE_INODE_EQUALITY",
                "candidate_failure_evidence": False,
                "artifact_defect_evidence": False,
            }
        },
    }


def _write_evidence(output_directory: Path, payload: Mapping[str, object]) -> Path:
    path = output_directory / "stage08_independent_rereview_evidence.json"
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        _fail("REVIEW_EVIDENCE_WRITE_FAILURE")
    return path


def main() -> int:
    global _ALLOWED_PROTECTED_ROOTS
    review_sha = os.environ.get("STAGE08_REVIEW_GIT_SHA", "")
    output_raw = os.environ.get("STAGE08_REVIEW_OUTPUT_DIRECTORY", "")
    output_directory = Path(output_raw)
    expected_parent = DATA_ROOT / "derived/controlled/reviews/stage08/development"
    if output_directory.parent != expected_parent or output_directory.exists():
        print("review_error=REVIEW_OUTPUT_SCOPE_INVALID")
        return 2
    expected_parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    expected_parent.chmod(0o700)
    output_directory.mkdir(mode=0o700)
    _ALLOWED_PROTECTED_ROOTS = (
        ARTIFACT_ROOT,
        STAGE07_ROOT,
        STAGE06_ROOT,
        output_directory,
    )
    sys.addaudithook(_audit)
    try:
        payload = _run_review(output_directory, review_sha)
    except IndependentRereviewError as error:
        incomplete_codes = {
            "GOETHE_SLURM_GUARD_FAILURE",
            "REVIEW_GIT_IDENTITY_MISMATCH",
            "REVIEW_RUNTIME_MISMATCH",
            "CONTROLLED_FILE_READ_FAILURE",
            "PUBLICATION_PARENT_READ_FAILURE",
        }
        payload = {
            "review_version": REVIEW_VERSION,
            "verdict": (
                "STAGE08_ADDRESS_EVIDENCE_INDEPENDENT_REREVIEW_INCOMPLETE"
                if error.code in incomplete_codes
                else "STAGE08_ADDRESS_EVIDENCE_INDEPENDENT_REREVIEW_FAIL"
            ),
            "candidate_sha": CANDIDATE_SHA,
            "executable_sha": EXECUTABLE_SHA,
            "review_git_sha": review_sha,
            "goethe_review_job_id": os.environ.get("SLURM_JOB_ID"),
            "failure_code": error.code,
            "privacy_and_prohibited_activity": {
                "parser_calls": 0,
                "reference_lookups": 0,
                "network_calls": _NETWORK_ATTEMPTS,
                "geocoder_calls": 0,
                "holdout_access": False,
                "production_access": False,
                "protected_path_scope_violations": _PROTECTED_PATH_VIOLATIONS,
            },
        }
    except BaseException:
        payload = {
            "review_version": REVIEW_VERSION,
            "verdict": "STAGE08_ADDRESS_EVIDENCE_INDEPENDENT_REREVIEW_INCOMPLETE",
            "candidate_sha": CANDIDATE_SHA,
            "executable_sha": EXECUTABLE_SHA,
            "review_git_sha": review_sha,
            "goethe_review_job_id": os.environ.get("SLURM_JOB_ID"),
            "failure_code": "UNEXPECTED_REVIEW_INFRASTRUCTURE_FAILURE",
        }
    evidence_path = _write_evidence(output_directory, payload)
    evidence_sha = _sha256_file(evidence_path)
    print(f"review_verdict={payload['verdict']}")
    print(f"review_git_sha={review_sha}")
    print(f"evidence_sha256={evidence_sha}")
    print("parser_calls=0")
    print("reference_lookups=0")
    print(f"network_calls={_NETWORK_ATTEMPTS}")
    print("geocoder_calls=0")
    print("holdout_access=false")
    print("production_access=false")
    verdict_value = payload["verdict"]
    return (
        0 if isinstance(verdict_value, str) and verdict_value.endswith("_PASS") else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
