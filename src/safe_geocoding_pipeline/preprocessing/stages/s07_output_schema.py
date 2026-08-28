"""Frozen Stage 7 v1 ordered nested Arrow representation."""

from __future__ import annotations

import pyarrow as pa

from .s07_libpostal_adapter import LibpostalComponent


STAGE07_STATUS_FIELD = "stage07_parse_status"
STAGE07_COMPONENTS_FIELD = "stage07_libpostal_components"


def component_struct_type() -> pa.StructType:
    return pa.struct(
        (
            pa.field("label", pa.large_string(), nullable=False),
            pa.field("value", pa.large_string(), nullable=False),
        )
    )


def component_list_type() -> pa.LargeListType:
    # ``element`` is Parquet's canonical repeated-field name.  Declaring it here
    # makes the exact Arrow schema stable after a write/reopen round trip.
    return pa.large_list(pa.field("element", component_struct_type(), nullable=False))


def component_list_field(*, diagnostic_nullable: bool = False) -> pa.Field:
    """Return the v1 non-null field, or the historical diagnostic-only variant."""
    return pa.field(
        STAGE07_COMPONENTS_FIELD,
        component_list_type(),
        nullable=diagnostic_nullable,
    )


def one_component_list_array(
    components: tuple[LibpostalComponent, ...] | None,
) -> pa.LargeListArray:
    """Build one large-list row without a per-component dictionary list.

    ``None`` is retained only for reopening the pre-contract diagnostic.  The
    Stage 7 v1 materializer and schema never pass or permit it.
    """
    values = components or ()
    struct_type = component_struct_type()
    struct_values = pa.StructArray.from_arrays(
        (
            pa.array((component.label for component in values), type=pa.large_string()),
            pa.array((component.value for component in values), type=pa.large_string()),
        ),
        fields=list(struct_type),
    )
    return pa.LargeListArray.from_arrays(
        pa.array((0, len(values)), type=pa.int64()),
        struct_values,
        type=component_list_type(),
        mask=pa.array((components is None,), type=pa.bool_()),
    )


__all__ = [
    "STAGE07_COMPONENTS_FIELD",
    "STAGE07_STATUS_FIELD",
    "component_list_field",
    "component_list_type",
    "component_struct_type",
    "one_component_list_array",
]
