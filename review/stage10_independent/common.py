"""Independent, specification-derived encodings and bounded review readers.

No protected I/O occurs at import. Never put row values in exceptions or reports.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def canonical(value):
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def encode(value):
    if value is None:
        yield b"\x00"
    elif type(value) is bool:
        yield b"\x04" + bytes([value])
    elif type(value) is str:
        n = sum(
            len(value[i : i + 65536].encode("utf8"))
            for i in range(0, len(value), 65536)
        )
        yield b"\x01" + struct.pack(">Q", n)
        for i in range(0, len(value), 65536):
            yield value[i : i + 65536].encode("utf8")
    elif type(value) is bytes:
        yield b"\x02" + struct.pack(">Q", len(value))
        yield value
    elif type(value) is int:
        if not 0 <= value < 2**64:
            raise ValueError("REVIEW_UINT_RANGE")
        yield b"\x03" + struct.pack(">Q", value)
    elif isinstance(value, (tuple, list)):
        yield b"\x05" + struct.pack(">Q", len(value))
        for item in value:
            yield from encode(item)
    else:
        raise TypeError("REVIEW_UNTYPED_VALUE")


def framed(values):
    yield struct.pack(">Q", len(values))
    for value in values:
        yield from encode(value)


def identity(domain, *values):
    digest = hashlib.sha256(b"SAFE:" + domain.encode("ascii") + b"\0")
    for chunk in framed(values):
        digest.update(chunk)
    return digest.digest()


def ordered(row, schema):
    def convert(value, kind):
        if value is None:
            return None
        if pa.types.is_struct(kind):
            return tuple(convert(value[field.name], field.type) for field in kind)
        if pa.types.is_list(kind) or pa.types.is_large_list(kind):
            return tuple(convert(item, kind.value_type) for item in value)
        return value

    return tuple(convert(row[field.name], field.type) for field in schema)


def rows(db, sql, parameters=()):
    cursor = db.cursor()
    try:
        for batch in cursor.execute(sql, list(parameters)).to_arrow_reader(
            batch_size=1
        ):
            yield batch.to_pylist()[0]
    finally:
        cursor.close()


def parquet_rows(paths):
    for path in paths:
        with pq.ParquetFile(path, page_checksum_verification=True) as reader:
            for batch in reader.iter_batches(batch_size=1, use_threads=False):
                yield batch.to_pylist()[0]


def scalar(db, sql, parameters=()):
    return int(db.execute(sql, list(parameters)).fetchone()[0])


def certificate(values):
    digest = hashlib.sha256()
    count = 0
    for row in values:
        for chunk in framed(row):
            digest.update(chunk)
        count += 1
    return {"selected_count": count, "selected_stream_sha256": digest.digest()}


INTENT_FIELDS = (
    "intent_version",
    "endpoint",
    "search_mode",
    "text",
    "address",
    "postalcode",
    "locality",
    "region",
    "country",
    "boundary_country",
    "retrieval_policy_slot",
)
REASONS = tuple(
    """REQUIRED_SOURCE_REPRESENTATION_UNAVAILABLE COUNTRY_CONTEXT_UNAVAILABLE
SOURCE_BOUNDARY_UNAVAILABLE SOURCE_FIELD_UNAVAILABLE MALFORMED_UPSTREAM_EVIDENCE
PARSER_EVIDENCE_UNUSABLE UNSUPPORTED_SCRIPT_TRANSLITERATION TRANSLITERATION_UNSUPPORTED_OUTPUT
UNIT_ALIGNMENT_AMBIGUOUS UNIT_SOURCE_FIELD_CONFLICT CONTRADICTION_GATE
INSUFFICIENT_TRUSTED_STRUCTURED_EVIDENCE ADMIN_LEVEL_NOT_ESTABLISHED PARSER_ONLY_FIELD_EXCLUDED
FAMILY_INELIGIBLE EMPTY_RESULT_AFTER_TRANSFORMATION EXACT_SEMANTIC_DUPLICATE
QUERY_BUDGET_SUPPRESSION""".split()
)
SELECTORS = (
    "CANDIDATE_V1",
    "OCCURRENCE_V1",
    "SOURCE_CONTEXT_V1",
    "SOURCE_LINES_V1",
    "PARSER_COMPONENTS_V1",
    "SOURCE_REFERENCE_V1",
    "REFERENCE_WITNESSES_V1",
)


def full_intent(text, country):
    return dict(
        zip(
            INTENT_FIELDS,
            (
                "stage10_query_intent_v1",
                "/v1/search",
                "FULL_TEXT",
                text,
                None,
                None,
                None,
                None,
                None,
                country,
                "SAFE_PELIAS_COMMON_RETRIEVAL_V1",
            ),
            strict=True,
        )
    )


def step(transform, before, after, ordinal=0, asset=None):
    return {
        "ordinal": ordinal,
        "transform_id": transform,
        "transform_asset_binding": asset,
        "input_value_sha256": identity("stage10-transform-value:v1", before),
        "output_value_sha256": identity("stage10-transform-value:v1", after),
    }
