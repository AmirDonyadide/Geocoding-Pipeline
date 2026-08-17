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
    CORE_COLUMNS,
    EVIDENCE_SCHEMA_VERSION,
    PARSE_STATUSES,
    PARSER_VERSION_V1,
    PARSER_VERSION_V2,
    PARSER_VERSION_V2_1,
    PARSER_VERSION_V3,
    PARSER_VERSION_V3_1,
    PARSER_VERSION_V3_2,
    RULE_REGISTRY_VERSION_V2,
    RULE_REGISTRY_VERSION_V3,
    RULE_REGISTRY_VERSION_V4,
    RULE_REGISTRY_VERSION_V5,
)
from .schema import exact_core_schema_matches, exact_evidence_schema_matches
from .semantic import core_digest, evidence_digest
from .validation import (
    validate_core_evidence_relationship,
    validate_core_rows,
    validate_evidence_rows,
)

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
_NATIVE_COMPONENT_FIELDS = {
    "street": "street_native_clean",
    "house_number": "house_number_native_clean",
    "unit": "unit_native_clean",
    "floor": "floor_native_clean",
    "building": "building_native_clean",
    "organization": "organization_native_clean",
    "locality": "locality_native_clean",
    "region": "region_native_clean",
    "country": "country_native_clean",
}
_SCIENTIFIC_CORE_FIELDS = CORE_COLUMNS[5:41]


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
    conflicts = Counter(flag for row in rows for flag in row["address_conflict_flags"])
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
            row["diagnostic_evaluation_status"] != "FULLY_EVALUATED" for row in rows
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


def _read_evidence(path: Path) -> list[dict[str, Any]]:
    parquet = pq.ParquetFile(
        path,
        page_checksum_verification=True,
        pre_buffer=True,
    )
    if not exact_evidence_schema_matches(parquet.schema_arrow):
        raise ValueError("development comparison evidence schema mismatch")
    rows = cast(list[dict[str, Any]], parquet.read(use_threads=False).to_pylist())
    validate_evidence_rows(rows)
    return rows


def _change_metrics(
    baseline: Sequence[Mapping[str, Any]],
    revised: Sequence[Mapping[str, Any]],
) -> dict[str, JsonValue]:
    transitions = Counter(
        f"{before['address_parse_status']}->{after['address_parse_status']}"
        for before, after in zip(baseline, revised, strict=True)
    )
    newly_added_conflicts = Counter(
        flag
        for before, after in zip(baseline, revised, strict=True)
        for flag in set(after["address_conflict_flags"])
        - set(before["address_conflict_flags"])
    )

    def component_changes(fields: Mapping[str, str]) -> dict[str, JsonValue]:
        changes: dict[str, JsonValue] = {}
        for component, field in fields.items():
            changes[component] = {
                "newly_selected": sum(
                    before[field] is None and after[field] is not None
                    for before, after in zip(baseline, revised, strict=True)
                ),
                "lost_selection": sum(
                    before[field] is not None and after[field] is None
                    for before, after in zip(baseline, revised, strict=True)
                ),
                "changed_selection": sum(
                    before[field] is not None
                    and after[field] is not None
                    and before[field] != after[field]
                    for before, after in zip(baseline, revised, strict=True)
                ),
            }
        return changes

    return {
        "rows_with_scientific_output_change": sum(
            any(before[field] != after[field] for field in _SCIENTIFIC_CORE_FIELDS)
            for before, after in zip(baseline, revised, strict=True)
        ),
        "newly_parsed_rows": sum(
            before["address_parse_status"] != "PARSED"
            and after["address_parse_status"] == "PARSED"
            for before, after in zip(baseline, revised, strict=True)
        ),
        "newly_partial_rows": sum(
            before["address_parse_status"] != "PARTIAL"
            and after["address_parse_status"] == "PARTIAL"
            for before, after in zip(baseline, revised, strict=True)
        ),
        "status_transitions": {
            transition: transitions[transition] for transition in sorted(transitions)
        },
        "rows_with_new_conflicts": sum(
            bool(
                set(after["address_conflict_flags"])
                - set(before["address_conflict_flags"])
            )
            for before, after in zip(baseline, revised, strict=True)
        ),
        "new_conflicts_by_type": {
            flag: newly_added_conflicts[flag] for flag in CONFLICT_FLAGS
        },
        "component_selection_changes": component_changes(_COMPONENT_FIELDS),
        "native_component_selection_changes": component_changes(
            _NATIVE_COMPONENT_FIELDS
        ),
    }


def _v2_v3_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, JsonValue]:
    metrics = _metrics(rows)
    metrics["selected_native_components"] = {
        component: sum(row[field] is not None for row in rows)
        for component, field in _NATIVE_COMPONENT_FIELDS.items()
    }
    metrics["selected_component_rows_any_representation"] = {
        component: sum(
            any(
                item["component"] == component.upper()
                for item in row["selected_component_provenance"]
            )
            for row in rows
        )
        for component in _COMPONENT_FIELDS
    }
    return metrics


def _rule_evidence_metrics(
    rows: Sequence[Mapping[str, Any]], rule_ids: Sequence[str]
) -> dict[str, JsonValue]:
    groups: dict[tuple[bytes, int], Mapping[str, Any]] = {}
    for row in rows:
        if row["rule_id"] in rule_ids:
            groups.setdefault(
                (bytes(row["stable_source_row_id_v1"]), int(row["evidence_id"])),
                row,
            )
    metrics: dict[str, JsonValue] = {}
    for rule_id in rule_ids:
        selected = [row for row in groups.values() if row["rule_id"] == rule_id]
        evidence_kinds = Counter(str(row["evidence_kind"]) for row in selected)
        metrics[rule_id] = {
            "candidate_count": len(selected),
            "selected_count": sum(bool(row["selected"]) for row in selected),
            "evidence_kind_counts": {
                kind: evidence_kinds[kind] for kind in sorted(evidence_kinds)
            },
        }
    return metrics


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
    if (
        len({bytes(row["configuration_fingerprint"]) for row in baseline}) != 1
        or len({bytes(row["configuration_fingerprint"]) for row in revised}) != 1
    ):
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


def compare_development_parser_v2_v3_outputs(
    baseline_core: Path,
    baseline_evidence: Path,
    revised_core: Path,
    revised_evidence: Path,
    output_path: Path,
    *,
    expected_rows: int = 8_000,
) -> dict[str, Any]:
    """Compare frozen v2 and experimental v3 DEVELOPMENT outputs safely."""
    return _compare_development_parser_v2_v3_outputs(
        baseline_core,
        baseline_evidence,
        revised_core,
        revised_evidence,
        output_path,
        expected_rows=expected_rows,
        baseline_parser_version=PARSER_VERSION_V2,
        revised_parser_version=PARSER_VERSION_V3,
        report_version="phase03_development_parser_v2_v3_comparison_v1",
    )


def compare_development_parser_v2_1_v3_1_outputs(
    baseline_core: Path,
    baseline_evidence: Path,
    revised_core: Path,
    revised_evidence: Path,
    output_path: Path,
    *,
    expected_rows: int = 8_000,
) -> dict[str, Any]:
    """Compare repaired v2.1 and experimental v3.1 DEVELOPMENT outputs safely."""
    return _compare_development_parser_v2_v3_outputs(
        baseline_core,
        baseline_evidence,
        revised_core,
        revised_evidence,
        output_path,
        expected_rows=expected_rows,
        baseline_parser_version=PARSER_VERSION_V2_1,
        revised_parser_version=PARSER_VERSION_V3_1,
        report_version="phase03_development_parser_v2_1_v3_1_comparison_v1",
        revised_rule_registry_version=RULE_REGISTRY_VERSION_V4,
        experimental_rule_ids=(
            "HOUSE_NUMBER_EMBEDDED_DESIGNATOR_EXPERIMENT_V4",
            "STREET_EMBEDDED_DESIGNATOR_EXPERIMENT_V4",
        ),
    )


def compare_development_parser_v2_1_v3_2_outputs(
    baseline_core: Path,
    baseline_evidence: Path,
    revised_core: Path,
    revised_evidence: Path,
    output_path: Path,
    *,
    expected_rows: int = 8_000,
) -> dict[str, Any]:
    """Compare repaired v2.1 and narrowed v3.2 DEVELOPMENT outputs safely."""
    return _compare_development_parser_v2_v3_outputs(
        baseline_core,
        baseline_evidence,
        revised_core,
        revised_evidence,
        output_path,
        expected_rows=expected_rows,
        baseline_parser_version=PARSER_VERSION_V2_1,
        revised_parser_version=PARSER_VERSION_V3_2,
        report_version="phase03_development_parser_v2_1_v3_2_comparison_v1",
        revised_rule_registry_version=RULE_REGISTRY_VERSION_V5,
        experimental_rule_ids=(
            "HOUSE_NUMBER_EMBEDDED_DESIGNATOR_EXPERIMENT_V5",
            "STREET_EMBEDDED_DESIGNATOR_EXPERIMENT_V5",
        ),
    )


def _compare_development_parser_v2_v3_outputs(
    baseline_core: Path,
    baseline_evidence: Path,
    revised_core: Path,
    revised_evidence: Path,
    output_path: Path,
    *,
    expected_rows: int,
    baseline_parser_version: str,
    revised_parser_version: str,
    report_version: str,
    revised_rule_registry_version: str = RULE_REGISTRY_VERSION_V4,
    experimental_rule_ids: Sequence[str] = (
        "HOUSE_NUMBER_EMBEDDED_DESIGNATOR_EXPERIMENT_V4",
        "STREET_EMBEDDED_DESIGNATOR_EXPERIMENT_V4",
    ),
) -> dict[str, Any]:
    if expected_rows < 1:
        raise ValueError("development comparison expected rows must be positive")
    baseline = _read_core(baseline_core)
    baseline_evidence_rows = _read_evidence(baseline_evidence)
    revised = _read_core(revised_core)
    revised_evidence_rows = _read_evidence(revised_evidence)
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
    if {str(row["parser_version"]) for row in baseline} != {
        baseline_parser_version
    } or {str(row["parser_version"]) for row in revised} != {revised_parser_version}:
        raise ValueError("development comparison parser-version mismatch")
    if {str(row["rule_registry_version"]) for row in baseline} != {
        RULE_REGISTRY_VERSION_V3
    } or {str(row["rule_registry_version"]) for row in revised} != {
        revised_rule_registry_version
    }:
        raise ValueError("development comparison rule-registry mismatch")
    if (
        len({bytes(row["configuration_fingerprint"]) for row in baseline}) != 1
        or len({bytes(row["configuration_fingerprint"]) for row in revised}) != 1
    ):
        raise ValueError("development comparison configuration is not uniform")
    validate_core_evidence_relationship(baseline, baseline_evidence_rows)
    validate_core_evidence_relationship(revised, revised_evidence_rows)
    baseline_identity_set = set(baseline_ids)
    if {
        bytes(row["stable_source_row_id_v1"]) for row in baseline_evidence_rows
    } - baseline_identity_set or {
        bytes(row["stable_source_row_id_v1"]) for row in revised_evidence_rows
    } - baseline_identity_set:
        raise ValueError("development comparison evidence identity mismatch")

    identity_digest = _identity_digest(baseline)
    payload: dict[str, JsonValue] = {
        "report_version": report_version,
        "status": "EXPERIMENTAL_COMPARISON_COMPLETE_NO_PROMOTION_DECISION",
        "rows": expected_rows,
        "identity_order_equal": True,
        "identity_digest": identity_digest,
        "page_checksums_verified": True,
        "portable_raw_values": False,
        "scientific_threshold_applied": False,
        "baseline": {
            "parser_version": baseline_parser_version,
            "rule_registry_version": RULE_REGISTRY_VERSION_V3,
            "configuration_fingerprint": bytes(
                baseline[0]["configuration_fingerprint"]
            ).hex(),
            "core_sha256": _sha256(baseline_core),
            "evidence_sha256": _sha256(baseline_evidence),
            "core_semantic_digest": core_digest(
                baseline, str(baseline[0]["component_schema_version"])
            ).hex(),
            "evidence_semantic_digest": evidence_digest(
                baseline_evidence_rows, EVIDENCE_SCHEMA_VERSION
            ).hex(),
            "evidence_rows": len(baseline_evidence_rows),
            **_v2_v3_metrics(baseline),
        },
        "experimental": {
            "parser_version": revised_parser_version,
            "rule_registry_version": revised_rule_registry_version,
            "configuration_fingerprint": bytes(
                revised[0]["configuration_fingerprint"]
            ).hex(),
            "core_sha256": _sha256(revised_core),
            "evidence_sha256": _sha256(revised_evidence),
            "core_semantic_digest": core_digest(
                revised, str(revised[0]["component_schema_version"])
            ).hex(),
            "evidence_semantic_digest": evidence_digest(
                revised_evidence_rows, EVIDENCE_SCHEMA_VERSION
            ).hex(),
            "evidence_rows": len(revised_evidence_rows),
            "experimental_rule_evidence": _rule_evidence_metrics(
                revised_evidence_rows, experimental_rule_ids
            ),
            **_v2_v3_metrics(revised),
        },
        "changes": _change_metrics(baseline, revised),
    }
    _atomic_json(output_path, payload)
    return cast(dict[str, Any], json.loads(canonical_json_bytes(payload)))
