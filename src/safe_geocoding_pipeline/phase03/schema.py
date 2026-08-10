from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import pyarrow as pa

from .constants import CORE_COLUMNS, EVIDENCE_COLUMNS


def _selected_provenance_type() -> pa.DataType:
    return pa.list_(
        pa.struct(
            [
                pa.field("component", pa.string(), nullable=False),
                pa.field("representation", pa.string(), nullable=False),
                pa.field("source_fields", pa.list_(pa.string()), nullable=False),
                pa.field("rule_ids", pa.list_(pa.string()), nullable=False),
                pa.field("confidence", pa.string(), nullable=False),
            ]
        )
    )


def _native_relationship_type() -> pa.DataType:
    return pa.list_(
        pa.struct(
            [
                pa.field("line_number", pa.uint8(), nullable=False),
                pa.field("relationship", pa.string(), nullable=False),
            ]
        )
    )


def core_schema() -> pa.Schema:
    nullable_strings = {
        "street_clean",
        "house_number_clean",
        "unit_clean",
        "floor_clean",
        "building_clean",
        "organization_clean",
        "postcode_clean",
        "locality_clean",
        "region_clean",
        "country_clean",
        "street_native_clean",
        "house_number_native_clean",
        "unit_native_clean",
        "floor_native_clean",
        "building_native_clean",
        "organization_native_clean",
        "locality_native_clean",
        "region_native_clean",
        "country_native_clean",
    }
    fields: list[pa.Field] = []
    for name in CORE_COLUMNS:
        if name in nullable_strings:
            fields.append(pa.field(name, pa.string(), nullable=True))
        elif name in {
            "stable_source_row_id_v1",
            "source_file_sha256",
            "configuration_fingerprint",
            "implementation_fingerprint",
        }:
            fields.append(pa.field(name, pa.binary(32), nullable=False))
        elif (
            name == "source_logical_record_number"
            or name == "input_max_field_utf8_bytes"
        ):
            fields.append(pa.field(name, pa.uint64(), nullable=False))
        elif name in {
            "address_conflict_flags",
            "address_diagnostic_flags",
            "postcode_diagnostic_flags",
            "skipped_oversized_fields",
        }:
            fields.append(pa.field(name, pa.list_(pa.string()), nullable=False))
        elif name == "selected_component_provenance":
            fields.append(pa.field(name, _selected_provenance_type(), nullable=False))
        elif name == "native_non_native_relationships":
            fields.append(pa.field(name, _native_relationship_type(), nullable=False))
        elif name in {
            "is_po_box",
            "is_historical",
            "probable_non_physical_address",
            "possible_company_only",
        }:
            fields.append(pa.field(name, pa.bool_(), nullable=True))
        else:
            fields.append(pa.field(name, pa.string(), nullable=False))
    schema = pa.schema(fields)
    if schema.names != list(CORE_COLUMNS) or len(schema) != 52:
        raise AssertionError("internal Phase 3 core schema error")
    return schema


def evidence_schema() -> pa.Schema:
    nullable_strings = {
        "component",
        "representation",
        "candidate_value",
        "confidence",
        "rule_id",
        "conflict_flag",
        "diagnostic_flag",
    }
    fields: list[pa.Field] = []
    for name in EVIDENCE_COLUMNS:
        if name == "stable_source_row_id_v1":
            fields.append(pa.field(name, pa.binary(32), nullable=False))
        elif name in {
            "source_logical_record_number",
            "start_character",
            "end_character_exclusive",
        }:
            fields.append(pa.field(name, pa.uint64(), nullable=False))
        elif name == "evidence_id":
            fields.append(pa.field(name, pa.uint32(), nullable=False))
        elif name == "span_ordinal":
            fields.append(pa.field(name, pa.uint16(), nullable=False))
        elif name == "selected":
            fields.append(pa.field(name, pa.bool_(), nullable=False))
        else:
            fields.append(
                pa.field(name, pa.string(), nullable=name in nullable_strings)
            )
    schema = pa.schema(fields)
    if schema.names != list(EVIDENCE_COLUMNS) or len(schema) != 20:
        raise AssertionError("internal Phase 3 evidence schema error")
    return schema


def schema_with_metadata(schema: pa.Schema, metadata: Mapping[str, str]) -> pa.Schema:
    encoded = {key.encode(): value.encode() for key, value in metadata.items()}
    return schema.with_metadata(encoded)


def exact_core_schema_matches(observed: pa.Schema) -> bool:
    return cast(
        bool, observed.remove_metadata().equals(core_schema(), check_metadata=False)
    )


def exact_evidence_schema_matches(observed: pa.Schema) -> bool:
    return cast(
        bool, observed.remove_metadata().equals(evidence_schema(), check_metadata=False)
    )
