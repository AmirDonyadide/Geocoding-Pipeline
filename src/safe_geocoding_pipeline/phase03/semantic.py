from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import pyarrow as pa

from .constants import CORE_COLUMNS, EVIDENCE_COLUMNS
from .schema import core_schema, evidence_schema

CORE_DOMAIN = b"safe_geocoding_pipeline:phase03_core_semantic_digest_v1\0"
EVIDENCE_DOMAIN = b"safe_geocoding_pipeline:phase03_evidence_semantic_digest_v1\0"
DATASET_DOMAIN = b"safe_geocoding_pipeline:phase03_dataset_semantic_digest_v1\0"


def _uint(value: int, width: int) -> bytes:
    if not 0 <= value < 1 << (width * 8):
        raise ValueError(f"value does not fit uint{width * 8}")
    return value.to_bytes(width, "big")


def _lp(value: bytes) -> bytes:
    return _uint(len(value), 8) + value


def encode_typed_value(data_type: pa.DataType, value: Any) -> bytes:
    if value is None:
        return b"\x00"
    if pa.types.is_string(data_type):
        if not isinstance(value, str):
            raise TypeError("semantic string value has wrong type")
        return b"\x01" + _lp(value.encode("utf-8", errors="strict"))
    if pa.types.is_boolean(data_type):
        if not isinstance(value, bool):
            raise TypeError("semantic boolean value has wrong type")
        return b"\x03" if value else b"\x02"
    if pa.types.is_uint8(data_type):
        return b"\x10" + _uint(value, 1)
    if pa.types.is_uint16(data_type):
        return b"\x11" + _uint(value, 2)
    if pa.types.is_uint32(data_type):
        return b"\x12" + _uint(value, 4)
    if pa.types.is_uint64(data_type):
        return b"\x13" + _uint(value, 8)
    if pa.types.is_fixed_size_binary(data_type):
        if not isinstance(value, bytes) or len(value) != data_type.byte_width:
            raise TypeError("semantic fixed-binary value has wrong type/width")
        return b"\x20" + _lp(value)
    if pa.types.is_list(data_type):
        if not isinstance(value, (list, tuple)):
            raise TypeError("semantic list value has wrong type")
        child = data_type.value_type
        return (
            b"\x30"
            + _uint(len(value), 8)
            + b"".join(encode_typed_value(child, item) for item in value)
        )
    if pa.types.is_struct(data_type):
        if not isinstance(value, Mapping):
            raise TypeError("semantic struct value has wrong type")
        if set(value) != set(data_type.names):
            raise ValueError("semantic struct fields differ from schema")
        return (
            b"\x40"
            + _uint(data_type.num_fields, 8)
            + b"".join(
                encode_typed_value(field.type, value[field.name]) for field in data_type
            )
        )
    raise TypeError(f"unsupported semantic type: {data_type}")


class TableSemanticDigest:
    def __init__(
        self, *, domain: bytes, schema_version: str, schema: pa.Schema
    ) -> None:
        self._digest = hashlib.sha256()
        self._digest.update(domain)
        self._digest.update(_lp(schema_version.encode()))
        self._digest.update(_uint(len(schema), 8))
        for field in schema:
            self._digest.update(_lp(field.name.encode()))
        self._schema = schema
        self._rows = 0
        self._finished = False

    def update_row(self, row: Mapping[str, Any], ordinal: int) -> None:
        if self._finished:
            raise RuntimeError("semantic digest already finalized")
        if ordinal != self._rows + 1:
            raise ValueError("semantic row ordinals must be contiguous and one-based")
        if set(row) != set(self._schema.names):
            raise ValueError("semantic row fields differ from schema")
        self._digest.update(b"\x52")
        self._digest.update(_uint(ordinal, 8))
        for field in self._schema:
            self._digest.update(encode_typed_value(field.type, row[field.name]))
        self._rows += 1

    def digest(self) -> bytes:
        if not self._finished:
            self._digest.update(b"\x46")
            self._digest.update(_uint(self._rows, 8))
            self._finished = True
        return self._digest.digest()

    def hexdigest(self) -> str:
        return self.digest().hex()

    @property
    def row_count(self) -> int:
        return self._rows


def core_digest(rows: Iterable[Mapping[str, Any]], schema_version: str) -> bytes:
    digest = TableSemanticDigest(
        domain=CORE_DOMAIN, schema_version=schema_version, schema=core_schema()
    )
    for ordinal, row in enumerate(rows, start=1):
        digest.update_row(row, ordinal)
    return digest.digest()


def evidence_digest(rows: Sequence[Mapping[str, Any]], schema_version: str) -> bytes:
    ordered = sorted(
        rows,
        key=lambda row: (
            row["source_logical_record_number"],
            row["evidence_id"],
            row["span_ordinal"],
        ),
    )
    digest = TableSemanticDigest(
        domain=EVIDENCE_DOMAIN, schema_version=schema_version, schema=evidence_schema()
    )
    for ordinal, row in enumerate(ordered, start=1):
        digest.update_row(row, ordinal)
    return digest.digest()


@dataclass(frozen=True, slots=True)
class DatasetShardDigest:
    relative_source_path: str
    core_digest: bytes
    core_rows: int
    evidence_digest: bytes
    evidence_rows: int


def dataset_digest(
    *,
    phase03_version: str,
    configuration_fingerprint: bytes,
    shards: Sequence[DatasetShardDigest],
) -> bytes:
    if len(configuration_fingerprint) != 32:
        raise ValueError("configuration fingerprint must be 32 bytes")
    digest = hashlib.sha256()
    digest.update(DATASET_DOMAIN)
    digest.update(_lp(phase03_version.encode()))
    digest.update(configuration_fingerprint)
    digest.update(_uint(len(shards), 8))
    total_core = 0
    total_evidence = 0
    for shard in shards:
        if len(shard.core_digest) != 32 or len(shard.evidence_digest) != 32:
            raise ValueError("per-shard semantic digests must be 32 bytes")
        digest.update(b"\x53")
        digest.update(_lp(shard.relative_source_path.encode()))
        digest.update(shard.core_digest)
        digest.update(_uint(shard.core_rows, 8))
        digest.update(shard.evidence_digest)
        digest.update(_uint(shard.evidence_rows, 8))
        total_core += shard.core_rows
        total_evidence += shard.evidence_rows
    digest.update(b"\x46")
    digest.update(_uint(total_core, 8))
    digest.update(_uint(total_evidence, 8))
    return digest.digest()


assert len(CORE_COLUMNS) == 52 and len(EVIDENCE_COLUMNS) == 20
