from __future__ import annotations

import hashlib
import struct

STABLE_ROW_ID_DOMAIN = b"safe_geocoding_pipeline:stable_source_row_id_v1\0"


def stable_source_row_id_v1(
    source_file_sha256: bytes, logical_record_number: int
) -> bytes:
    """Return the approved source-content-and-position identifier."""
    if len(source_file_sha256) != 32:
        raise ValueError("source_file_sha256 must contain exactly 32 raw bytes")
    if not 1 <= logical_record_number <= 0xFFFF_FFFF_FFFF_FFFF:
        raise ValueError("logical_record_number must fit positive uint64")
    digest = hashlib.sha256()
    digest.update(STABLE_ROW_ID_DOMAIN)
    digest.update(source_file_sha256)
    digest.update(struct.pack(">Q", logical_record_number))
    return digest.digest()
