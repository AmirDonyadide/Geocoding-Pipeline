from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import pyarrow as pa

from ...raw_csv import SOURCE_COLUMNS
from .s01_constants import PROVENANCE_COLUMNS, STAGING_COLUMNS
from ..fingerprints import fingerprint


def base_staging_schema() -> pa.Schema:
    fields = [pa.field(name, pa.string(), nullable=False) for name in SOURCE_COLUMNS]
    fields.extend(
        (
            pa.field("source_file", pa.string(), nullable=False),
            pa.field("source_logical_record_number", pa.uint64(), nullable=False),
            pa.field("stable_source_row_id_v1", pa.binary(32), nullable=False),
            pa.field("source_file_sha256", pa.binary(32), nullable=False),
            pa.field("source_schema_version", pa.string(), nullable=False),
            pa.field("parser_version", pa.string(), nullable=False),
            pa.field("staging_version", pa.string(), nullable=False),
        )
    )
    schema = pa.schema(fields)
    if schema.names != list(STAGING_COLUMNS) or len(PROVENANCE_COLUMNS) != 7:
        raise AssertionError("internal accepted Stage 1 ingestion schema order error")
    return schema


def schema_with_metadata(metadata: Mapping[str, str]) -> pa.Schema:
    encoded = {
        key.encode("utf-8"): value.encode("utf-8") for key, value in metadata.items()
    }
    return base_staging_schema().with_metadata(encoded)


def schema_fingerprint() -> str:
    schema = base_staging_schema()
    return fingerprint(
        {
            "version": "phase02_arrow_schema_v1",
            "fields": [
                {
                    "name": field.name,
                    "type": str(field.type),
                    "nullable": field.nullable,
                }
                for field in schema
            ],
        }
    )


def exact_schema_matches(observed: pa.Schema) -> bool:
    return cast(
        bool,
        observed.remove_metadata().equals(base_staging_schema(), check_metadata=False),
    )
