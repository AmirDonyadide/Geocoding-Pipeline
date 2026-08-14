from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import pyarrow.parquet as pq

from ..phase02.fingerprints import JsonValue, canonical_json_bytes
from .constants import (
    CONFLICT_FLAGS,
    PARSE_STATUSES,
    PARSER_VERSION_V1,
    PARSER_VERSION_V2,
    RULE_REGISTRY_VERSION_V2,
    RULE_REGISTRY_VERSION_V3,
)
from .schema import exact_core_schema_matches
from .semantic import core_digest
from .validation import validate_core_rows

_COMPONENT_FIELDS = {
    "street": "street_clean",
    "house_number": "house_number_clean",
    "unit": "unit_clean",
    "floor": "floor_clean",
    "building": "building_clean",
    "organization": "organization_clean",
    "postcode": "postcode_clean",
    "locality": "locality_clean",
    "region": "region_clean",
    "country": "country_clean",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _identity_digest(rows: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256(
        b"safe_geocoding_pipeline:phase03_development_comparison_identity_v1\0"
    )
    for ordinal, row in enumerate(rows, start=1):
        identity = bytes(row["stable_source_row_id_v1"])
        digest.update(ordinal.to_bytes(8, "big"))
        digest.update(identity)
    digest.update(len(rows).to_bytes(8, "big"))
    return digest.hexdigest()


def _metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, JsonValue]:
    conflicts = Counter(
        flag for row in rows for flag in row["address_conflict_flags"]
    )
    unknown_conflicts = set(conflicts) - set(CONFLICT_FLAGS)
    if unknown_conflicts:
        raise ValueError("unregistered conflict in comparison input")
    parse_counts = Counter(str(row["address_parse_status"]) for row in rows)
    representation_counts: Counter[str] = Counter()
    for row in rows:
        for provenance in row["selected_component_provenance"]:
            representation_counts[str(provenance["representation"])] += 1
    return {
        "address_parse_status": {
            status: parse_counts[status] for status in PARSE_STATUSES
        },
        "selected_components": {
            name: sum(row[field] is not None for row in rows)
            for name, field in _COMPONENT_FIELDS.items()
        },
        "selected_provenance_by_representation": {
            representation: representation_counts[representation]
            for representation in ("NON_NATIVE", "NATIVE", "SHARED")
        },
        "native_non_native_text_different": sum(
            "NATIVE_NON_NATIVE_TEXT_DIFFERENT" in row["address_diagnostic_flags"]
            for row in rows
        ),
        "conflicts_by_type": {flag: conflicts[flag] for flag in CONFLICT_FLAGS},
        "unassigned_content_present": sum(
            "UNASSIGNED_CONTENT_PRESENT" in row["address_diagnostic_flags"]
            for row in rows
        ),
        "unsafe_or_skipped": sum(
            row["diagnostic_evaluation_status"] != "FULLY_EVALUATED"
            for row in rows
        ),
        "candidate_limit_exceeded": sum(
            "CANDIDATE_LIMIT_EXCEEDED" in row["address_diagnostic_flags"]
            for row in rows
        ),
    }


def _read_core(path: Path) -> list[dict[str, Any]]:
    parquet = pq.ParquetFile(
        path,
        page_checksum_verification=True,
        pre_buffer=True,
    )
    if not exact_core_schema_matches(parquet.schema_arrow):
        raise ValueError("development comparison core schema mismatch")
    rows = cast(list[dict[str, Any]], parquet.read(use_threads=False).to_pylist())
    validate_core_rows(rows)
    return rows


def _atomic_json(path: Path, payload: Mapping[str, JsonValue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.tmp")
    if path.exists() or temporary.exists():
        raise FileExistsError(path)
    with temporary.open("xb") as stream:
        os.chmod(temporary, 0o600)
        stream.write(canonical_json_bytes(dict(payload)) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    path.chmod(0o600)


def compare_development_parser_outputs(
    baseline_core: Path,
    revised_core: Path,
    output_path: Path,
    *,
    expected_rows: int = 8_000,
) -> dict[str, Any]:
    """Compare two controlled DEVELOPMENT cores without exporting row values."""
    if expected_rows < 1:
        raise ValueError("development comparison expected rows must be positive")
    baseline = _read_core(baseline_core)
    revised = _read_core(revised_core)
    if len(baseline) != expected_rows or len(revised) != expected_rows:
        raise ValueError("development comparison row count mismatch")
    baseline_ids = [bytes(row["stable_source_row_id_v1"]) for row in baseline]
    revised_ids = [bytes(row["stable_source_row_id_v1"]) for row in revised]
    if baseline_ids != revised_ids:
        raise ValueError("development comparison identity/order mismatch")
    provenance_columns = (
        "id",
        "source_file",
        "source_logical_record_number",
        "source_file_sha256",
    )
    if any(
        baseline_row[column] != revised_row[column]
        for baseline_row, revised_row in zip(baseline, revised, strict=True)
        for column in provenance_columns
    ):
        raise ValueError("development comparison source provenance mismatch")
    baseline_versions = {str(row["parser_version"]) for row in baseline}
    revised_versions = {str(row["parser_version"]) for row in revised}
    if baseline_versions != {PARSER_VERSION_V1} or revised_versions != {
        PARSER_VERSION_V2
    }:
        raise ValueError("development comparison parser-version mismatch")
    baseline_registries = {str(row["rule_registry_version"]) for row in baseline}
    revised_registries = {str(row["rule_registry_version"]) for row in revised}
    if baseline_registries != {RULE_REGISTRY_VERSION_V2} or revised_registries != {
        RULE_REGISTRY_VERSION_V3
    }:
        raise ValueError("development comparison rule-registry mismatch")
    if len({bytes(row["configuration_fingerprint"]) for row in baseline}) != 1 or len(
        {bytes(row["configuration_fingerprint"]) for row in revised}
    ) != 1:
        raise ValueError("development comparison configuration is not uniform")
    identity_digest = _identity_digest(baseline)
    payload: dict[str, JsonValue] = {
        "report_version": "phase03_development_parser_comparison_v1",
        "status": "COMPARISON_COMPLETE_NO_SCIENTIFIC_THRESHOLD_APPLIED",
        "rows": expected_rows,
        "identity_order_equal": True,
        "identity_digest": identity_digest,
        "page_checksums_verified": True,
        "portable_raw_values": False,
        "baseline": {
            "parser_version": PARSER_VERSION_V1,
            "rule_registry_version": str(baseline[0]["rule_registry_version"]),
            "configuration_fingerprint": bytes(
                baseline[0]["configuration_fingerprint"]
            ).hex(),
            "core_sha256": _sha256(baseline_core),
            "core_semantic_digest": core_digest(
                baseline, str(baseline[0]["component_schema_version"])
            ).hex(),
            **_metrics(baseline),
        },
        "revised": {
            "parser_version": PARSER_VERSION_V2,
            "rule_registry_version": str(revised[0]["rule_registry_version"]),
            "configuration_fingerprint": bytes(
                revised[0]["configuration_fingerprint"]
            ).hex(),
            "core_sha256": _sha256(revised_core),
            "core_semantic_digest": core_digest(
                revised, str(revised[0]["component_schema_version"])
            ).hex(),
            **_metrics(revised),
        },
    }
    _atomic_json(output_path, payload)
    # Return a JSON-shaped defensive copy, not references to mutable row state.
    return cast(dict[str, Any], json.loads(canonical_json_bytes(payload)))
