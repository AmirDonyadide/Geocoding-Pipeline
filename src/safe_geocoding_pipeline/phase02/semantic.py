from __future__ import annotations

import hashlib
import struct
from collections.abc import Sequence

from ..raw_csv import SOURCE_COLUMNS
from .constants import SOURCE_SCHEMA_VERSION

SEMANTIC_DIGEST_DOMAIN = b"safe_geocoding_pipeline:raw_semantic_digest_v1\0"
_ROW_MARKER = b"\x52"
_FOOTER_MARKER = b"\x46"
_NULL_TAG = b"\x00"
_NON_NULL_TAG = b"\x01"


def uint64_bytes(value: int) -> bytes:
    if not 0 <= value <= 0xFFFF_FFFF_FFFF_FFFF:
        raise ValueError("value must fit uint64")
    return struct.pack(">Q", value)


def length_prefixed(value: bytes) -> bytes:
    return uint64_bytes(len(value)) + value


class RawSemanticDigest:
    """Streaming implementation of raw_semantic_digest_v1."""

    def __init__(self) -> None:
        self._digest = hashlib.sha256()
        self._digest.update(SEMANTIC_DIGEST_DOMAIN)
        self._digest.update(length_prefixed(SOURCE_SCHEMA_VERSION.encode("utf-8")))
        self._digest.update(uint64_bytes(len(SOURCE_COLUMNS)))
        for column in SOURCE_COLUMNS:
            self._digest.update(length_prefixed(column.encode("utf-8")))
        self._rows = 0
        self._finished = False

    def update_row(
        self,
        values: Sequence[str | None],
        logical_row_ordinal: int,
        *,
        require_non_null: bool,
    ) -> list[bytes | None]:
        if self._finished:
            raise RuntimeError("semantic digest is already finalized")
        if logical_row_ordinal != self._rows + 1:
            raise ValueError("logical row ordinals must be contiguous and one-based")
        if len(values) != len(SOURCE_COLUMNS):
            raise ValueError(f"expected {len(SOURCE_COLUMNS)} raw fields")
        encoded_values: list[bytes | None] = []
        self._digest.update(_ROW_MARKER)
        self._digest.update(uint64_bytes(logical_row_ordinal))
        for value in values:
            if value is None:
                if require_non_null:
                    raise ValueError("source raw fields must be non-null strings")
                self._digest.update(_NULL_TAG)
                encoded_values.append(None)
                continue
            if not isinstance(value, str):
                raise TypeError("raw semantic values must be strings or null")
            encoded = value.encode("utf-8", errors="strict")
            self._digest.update(_NON_NULL_TAG)
            self._digest.update(length_prefixed(encoded))
            encoded_values.append(encoded)
        self._rows += 1
        return encoded_values

    def hexdigest(self) -> str:
        if not self._finished:
            self._digest.update(_FOOTER_MARKER)
            self._digest.update(uint64_bytes(self._rows))
            self._finished = True
        return self._digest.hexdigest()

    @property
    def row_count(self) -> int:
        return self._rows
