from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import pyarrow.parquet as pq

from ..phase02.fingerprints import JsonValue, canonical_json_bytes
from .config import Phase03Config
from .pilot_runner import read_identity_set
from .review import manual_review_schema
from .schema import exact_core_schema_matches, exact_evidence_schema_matches
from .semantic import core_digest, evidence_digest
from .validation import (
    validate_core_evidence_relationship,
    validate_core_rows,
    validate_evidence_rows,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _counter(values: Sequence[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _flatten(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, int]:
    return _counter([str(value) for row in rows for value in row[field]])


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.tmp")
    if path.exists() or temporary.exists():
        raise FileExistsError(path)
    with temporary.open("xb") as stream:
        os.chmod(temporary, 0o600)
        stream.write(canonical_json_bytes(cast(JsonValue, dict(payload))) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    path.chmod(0o600)


def validate_and_report_development_pilot(
    *,
    run_id: str,
    git_commit: str,
    development_identity_path: Path,
    locked_identity_path: Path,
    core_path: Path,
    evidence_path: Path,
    review_context_path: Path,
    portable_labels_path: Path,
    transform_result_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    config = Phase03Config()
    development_metadata, development_values = read_identity_set(
        development_identity_path
    )
    locked_metadata, locked_values = read_identity_set(locked_identity_path)
    development = set(development_values)
    locked = set(locked_values)
    if (
        development_metadata["partition"] != "DEVELOPMENT"
        or locked_metadata["partition"] != "LOCKED_EVALUATION"
        or len(development) != 8_000
        or len(locked) != 4_000
        or development & locked
    ):
        raise ValueError("development/locked identity validation failed")

    core_file = pq.ParquetFile(
        core_path, page_checksum_verification=True, pre_buffer=True
    )
    evidence_file = pq.ParquetFile(
        evidence_path, page_checksum_verification=True, pre_buffer=True
    )
    if not exact_core_schema_matches(core_file.schema_arrow):
        raise ValueError("development core schema mismatch")
    if not exact_evidence_schema_matches(evidence_file.schema_arrow):
        raise ValueError("development evidence schema mismatch")
    core_rows = cast(list[dict[str, Any]], core_file.read(use_threads=False).to_pylist())
    evidence_rows = cast(
        list[dict[str, Any]], evidence_file.read(use_threads=False).to_pylist()
    )
    validate_core_rows(core_rows)
    validate_evidence_rows(evidence_rows)
    validate_core_evidence_relationship(core_rows, evidence_rows)
    core_ids = {bytes(row["stable_source_row_id_v1"]) for row in core_rows}
    evidence_ids = {bytes(row["stable_source_row_id_v1"]) for row in evidence_rows}
    if len(core_rows) != 8_000 or core_ids != development:
        raise ValueError("development core identity mismatch")
    if not evidence_ids.issubset(development) or evidence_ids & locked:
        raise ValueError("locked or unknown identity in evidence")

    transform_result = json.loads(transform_result_path.read_text(encoding="utf-8"))
    observed_core_digest = core_digest(
        core_rows, config.component_schema_version
    ).hex()
    observed_evidence_digest = evidence_digest(
        evidence_rows, config.evidence_schema_version
    ).hex()
    if (
        transform_result.get("status") != "PASS"
        or transform_result.get("core_rows") != 8_000
        or transform_result.get("core_semantic_digest") != observed_core_digest
        or transform_result.get("evidence_semantic_digest")
        != observed_evidence_digest
        or transform_result.get("page_checksums_verified") is not True
    ):
        raise ValueError("development transform read-back validation mismatch")

    context_file = pq.ParquetFile(
        review_context_path, page_checksum_verification=True, pre_buffer=True
    )
    labels_file = pq.ParquetFile(
        portable_labels_path, page_checksum_verification=True, pre_buffer=True
    )
    if labels_file.schema_arrow.remove_metadata() != manual_review_schema().remove_metadata():
        raise ValueError("portable review-label schema mismatch")
    context_table = context_file.read(use_threads=False)
    context_ids = {
        bytes(value)
        for value in context_table["stable_source_row_id_v1"].to_pylist()
    }
    labels = labels_file.read(use_threads=False).to_pylist()
    if (
        context_file.metadata.num_rows != 800
        or len(context_ids) != 800
        or not context_ids.issubset(development)
        or context_ids & locked
        or len(labels) != 800
        or sum(bool(row["is_independent_review"]) for row in labels) != 200
    ):
        raise ValueError("development review sample validation failed")
    prohibited_label_columns = {
        "stable_source_row_id_v1",
        "id",
        "source_file",
        "street_address_line_1",
        "city",
        "postcode",
        "candidate_value",
    }
    if prohibited_label_columns & set(labels_file.schema_arrow.names):
        raise ValueError("portable review labels contain a prohibited column")
    for confidential_path in (
        development_identity_path,
        locked_identity_path,
        core_path,
        evidence_path,
        review_context_path,
        portable_labels_path,
    ):
        if confidential_path.stat().st_mode & 0o777 != 0o600:
            raise ValueError("controlled file permissions are not owner-only")
        if confidential_path.parent.stat().st_mode & 0o077:
            raise ValueError("controlled parent permissions are not owner-only")

    component_fields = {
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
    evidence_rules = _counter(
        [str(row["rule_id"]) for row in evidence_rows if row["rule_id"] is not None]
    )
    shadow_rows = {
        bytes(row["stable_source_row_id_v1"])
        for row in evidence_rows
        if row["rule_id"] == "HOUSE_NUMBER_EDGE_CANDIDATE_V1"
    }
    payload: dict[str, Any] = {
        "gate": "DEVELOPMENT_PILOT_PASS",
        "run_id": run_id,
        "git_commit": git_commit,
        "development_count": len(development),
        "locked_evaluation_count": len(locked),
        "development_locked_intersection": 0,
        "locked_payload_rows_read": 0,
        "core_rows": len(core_rows),
        "evidence_rows": len(evidence_rows),
        "review_rows": len(labels),
        "double_review_rows": sum(
            bool(row["is_independent_review"]) for row in labels
        ),
        "core_semantic_digest": observed_core_digest,
        "evidence_semantic_digest": observed_evidence_digest,
        "page_checksums_verified": True,
        "core_sha256": _sha256(core_path),
        "evidence_sha256": _sha256(evidence_path),
        "parse_status": _counter(
            [str(row["address_parse_status"]) for row in core_rows]
        ),
        "completeness": _counter(
            [str(row["address_completeness_class"]) for row in core_rows]
        ),
        "diagnostic_evaluation_status": _counter(
            [str(row["diagnostic_evaluation_status"]) for row in core_rows]
        ),
        "component_presence": {
            name: sum(row[field] is not None for row in core_rows)
            for name, field in component_fields.items()
        },
        "conflict_flags": _flatten(core_rows, "address_conflict_flags"),
        "diagnostic_flags": _flatten(core_rows, "address_diagnostic_flags"),
        "postcode_diagnostic_flags": _flatten(
            core_rows, "postcode_diagnostic_flags"
        ),
        "country_parse_method": _counter(
            [str(row["country_parse_method"]) for row in core_rows]
        ),
        "evidence_by_rule": evidence_rules,
        "evidence_by_component": _counter(
            [
                str(row["component"])
                for row in evidence_rows
                if row["component"] is not None
            ]
        ),
        "evidence_by_kind": _counter(
            [str(row["evidence_kind"]) for row in evidence_rows]
        ),
        "shadow_house_number": {
            "rows_fired": len(shadow_rows),
            "candidate_count": evidence_rules.get(
                "HOUSE_NUMBER_EDGE_CANDIDATE_V1", 0
            ),
            "core_effect": 0,
        },
        "privacy": {
            "portable_raw_values": False,
            "portable_stable_identities": False,
            "locked_identity_in_development_artifacts": False,
            "locked_payload_processed": False,
        },
    }
    _atomic_json(output_path, payload)
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--development-identities", type=Path, required=True)
    parser.add_argument("--locked-identities", type=Path, required=True)
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--review-context", type=Path, required=True)
    parser.add_argument("--portable-labels", type=Path, required=True)
    parser.add_argument("--transform-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    payload = validate_and_report_development_pilot(
        run_id=args.run_id,
        git_commit=args.git_commit,
        development_identity_path=args.development_identities,
        locked_identity_path=args.locked_identities,
        core_path=args.core,
        evidence_path=args.evidence,
        review_context_path=args.review_context,
        portable_labels_path=args.portable_labels,
        transform_result_path=args.transform_result,
        output_path=args.output,
    )
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
