from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import pyarrow.parquet as pq

from ..phase02.fingerprints import JsonValue, canonical_json_bytes
from .targeted_experiment_review import (
    EXPERIMENTAL_RULE_IDS,
    REVIEWER_IDS,
    TARGETED_REVIEW_SCHEMA_VERSION,
    targeted_review_context_schema,
    targeted_review_label_schema,
)
from .targeted_review_population import file_sha256, reject_locked_path

ORIENTATION_REPORT_VERSION: Final = (
    "phase03_parser_v3_1_targeted_orientation_evidence_v1"
)
ORIENTATIONS: Final = (
    "STREET_NUMBER_RESIDUAL",
    "RESIDUAL_NUMBER_STREET",
    "OTHER_OR_UNCLASSIFIABLE",
)
_HOUSE_RULE: Final = "HOUSE_NUMBER_EMBEDDED_DESIGNATOR_EXPERIMENT_V4"
_STREET_RULE: Final = "STREET_EMBEDDED_DESIGNATOR_EXPERIMENT_V4"
_EXPECTED_INPUTS: Final = {
    "input_manifest": (
        "831b11b32a79a77449a8448c74650a8a73b096888d1d93c595f4ee55cfdaaacb",
        3_713,
    ),
    "protected_context": (
        "15bd217430ca1ed2162afdf1a0197a7a776c8d4f2996888b78d64e7c19b8343d",
        19_097,
    ),
    "controlled_r01_labels": (
        "52272f9778770865076cc1d565e6c5e19f566115d0aa33d769a34d105bd7b1ad",
        8_700,
    ),
}
_EXPECTED_EXPERIMENT_ITERATION: Final = (
    "phase03_development_country_method_repair_20260816T001155Z_1749448_e4a47253"
)


def orientation_analysis_implementation_fingerprint() -> str:
    digest = hashlib.sha256(
        b"safe_geocoding_pipeline:phase03_targeted_orientation_analysis_v1\0"
    )
    root = Path(__file__).resolve().parent
    for name in (
        "targeted_orientation_analysis.py",
        "targeted_experiment_review.py",
    ):
        encoded = name.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(hashlib.sha256((root / name).read_bytes()).digest())
    return digest.hexdigest()


def _require_owner_only_input(path: Path) -> Path:
    reject_locked_path(path)
    if not path.is_file():
        raise FileNotFoundError("targeted orientation input is missing")
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError(
            "targeted orientation input must be owner-only and non-symlink"
        )
    resolved = path.resolve(strict=True)
    reject_locked_path(resolved)
    return resolved


def _artifact_identity(path: Path) -> tuple[str, int]:
    return file_sha256(path), path.stat().st_size


def _material(value: str) -> bool:
    return bool(value.strip())


def _orientation(
    raw: str,
    house: Mapping[str, Any],
    street: Mapping[str, Any],
) -> str:
    house_start = int(house["start_character"])
    house_end = int(house["end_character_exclusive"])
    street_start = int(street["start_character"])
    street_end = int(street["end_character_exclusive"])
    if not (
        0 <= house_start < house_end <= len(raw)
        and 0 <= street_start < street_end <= len(raw)
    ):
        raise ValueError("targeted orientation evidence span is invalid")
    if street_end <= house_start:
        if (
            not _material(raw[:street_start])
            and not _material(raw[street_end:house_start])
            and _material(raw[house_end:])
        ):
            return ORIENTATIONS[0]
    elif house_end <= street_start:
        if (
            _material(raw[:house_start])
            and not _material(raw[house_end:street_start])
            and not _material(raw[street_end:])
        ):
            return ORIENTATIONS[1]
    return ORIENTATIONS[2]


def _classify_selected_case(row: Mapping[str, Any]) -> str:
    evidence = json.loads(str(row["experimental_evidence_json"]))
    selected = [
        item
        for item in evidence
        if item.get("rule_id") in EXPERIMENTAL_RULE_IDS and item.get("selected") is True
    ]
    house_rows = [item for item in selected if item.get("rule_id") == _HOUSE_RULE]
    street_rows = [item for item in selected if item.get("rule_id") == _STREET_RULE]
    if len(house_rows) != 1 or len(street_rows) != 1:
        return ORIENTATIONS[2]
    house = house_rows[0]
    street = street_rows[0]
    if house.get("source_field") != street.get("source_field") or house.get(
        "representation"
    ) != street.get("representation"):
        return ORIENTATIONS[2]
    source_field = str(house["source_field"])
    if source_field not in row or not isinstance(row[source_field], str):
        raise ValueError("targeted orientation source field is invalid")
    return _orientation(str(row[source_field]), house, street)


def _empty_metrics() -> Counter[str]:
    return Counter(
        {
            "selected_rows": 0,
            "review_identity_count": 0,
            "street_exact_correct_count": 0,
            "house_number_exact_correct_count": 0,
            "joint_street_house_correct_count": 0,
            "incorrect_or_overreach_count": 0,
            "overall_acceptable_count": 0,
        }
    )


def _write_report(output_path: Path, payload: dict[str, JsonValue]) -> None:
    if output_path.exists():
        raise FileExistsError("targeted orientation report already exists")
    output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if output_path.parent.is_symlink() or output_path.parent.stat().st_mode & 0o077:
        raise ValueError("targeted orientation output directory must be owner-only")
    temporary = output_path.with_name(f".{output_path.name}.tmp")
    with temporary.open("xb") as stream:
        os.chmod(temporary, 0o600)
        stream.write(canonical_json_bytes(payload) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, output_path)
    output_path.chmod(0o600)
    descriptor = os.open(output_path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def analyze_targeted_v3_1_orientations(
    *,
    input_manifest_path: Path,
    protected_context_path: Path,
    controlled_labels_path: Path,
    output_path: Path,
    implementation_commit: str,
    production: bool,
) -> dict[str, JsonValue]:
    """Aggregate v3.1 selected orientation evidence without portable identities."""
    if production:
        from ..execution_policy import require_goethe_nhr_slurm

        require_goethe_nhr_slurm("phase03-targeted-v3-1-orientation-analysis")
    reject_locked_path(output_path)
    paths = {
        "input_manifest": _require_owner_only_input(input_manifest_path),
        "protected_context": _require_owner_only_input(protected_context_path),
        "controlled_r01_labels": _require_owner_only_input(controlled_labels_path),
    }
    identities = {role: _artifact_identity(path) for role, path in paths.items()}
    if production and identities != _EXPECTED_INPUTS:
        raise ValueError("targeted orientation production input identity mismatch")

    manifest = json.loads(paths["input_manifest"].read_text(encoding="utf-8"))
    if (
        manifest.get("status") != "TARGETED_REVIEW_INPUT_PREPARED_NO_LABELS"
        or manifest.get("experiment_iteration") != _EXPECTED_EXPERIMENT_ITERATION
        or manifest.get("development_rows") != 8_000
        or manifest.get("targeted_review_population_rows") != 11
        or manifest.get("scientific_output_change_rows") != 9
        or manifest.get("experimental_rule_evidence_rows") != 11
        or manifest.get("locked_rows_read") != 0
        or manifest.get("output_artifacts", {})
        .get("protected_context", {})
        .get("sha256")
        != identities["protected_context"][0]
    ):
        raise ValueError("targeted orientation input manifest binding mismatch")

    context_file = pq.ParquetFile(
        paths["protected_context"], page_checksum_verification=True, pre_buffer=True
    )
    labels_file = pq.ParquetFile(
        paths["controlled_r01_labels"],
        page_checksum_verification=True,
        pre_buffer=True,
    )
    if not context_file.schema_arrow.remove_metadata().equals(
        targeted_review_context_schema(), check_metadata=False
    ) or not labels_file.schema_arrow.remove_metadata().equals(
        targeted_review_label_schema(), check_metadata=False
    ):
        raise ValueError("targeted orientation input schema mismatch")
    context = context_file.read(use_threads=False).to_pylist()
    labels = labels_file.read(use_threads=False).to_pylist()
    label_metadata = {
        key.decode("utf-8"): value.decode("utf-8")
        for key, value in (labels_file.schema_arrow.metadata or {}).items()
    }
    if (
        len(context) != 11
        or len(labels) != 11
        or label_metadata.get("review_design") != "SINGLE_REVIEWER"
        or label_metadata.get("primary_reviewer") != REVIEWER_IDS[0]
        or label_metadata.get("primary_review_complete") != "true"
        or label_metadata.get("primary_review_rows") != "11"
        or label_metadata.get("independent_second_review")
        != "SKIPPED_BY_EXPLICIT_DECISION"
        or label_metadata.get("locked_rows_read") != "0"
        or any(
            row["reviewer_id"] != REVIEWER_IDS[0]
            or row["assignment_role"] != "PRIMARY"
            or row["label_schema_version"] != TARGETED_REVIEW_SCHEMA_VERSION
            for row in labels
        )
    ):
        raise ValueError("targeted orientation controlled-label binding mismatch")

    context_by_review_id: dict[str, dict[str, Any]] = {}
    for row in context:
        metadata = json.loads(str(row["targeted_case_metadata_json"]))
        review_id = hashlib.sha256(
            b"safe_geocoding_pipeline:phase03_parser_v3_targeted_review_id_v1\0"
            + len(_EXPECTED_EXPERIMENT_ITERATION.encode("utf-8")).to_bytes(8, "big")
            + _EXPECTED_EXPERIMENT_ITERATION.encode("utf-8")
            + bytes(row["stable_source_row_id_v1"])
        ).hexdigest()
        if review_id in context_by_review_id:
            raise ValueError("targeted orientation context identity duplicate")
        context_by_review_id[review_id] = {**row, "_case_metadata": metadata}
    labels_by_review_id = {str(row["hashed_review_id"]): row for row in labels}
    if len(labels_by_review_id) != 11 or set(labels_by_review_id) != set(
        context_by_review_id
    ):
        raise ValueError("targeted orientation review identity mismatch")

    aggregates = {orientation: _empty_metrics() for orientation in ORIENTATIONS}
    analyzed = 0
    for review_id, context_row in context_by_review_id.items():
        case_metadata = context_row["_case_metadata"]
        if not (
            case_metadata.get("scientific_output_changed") is True
            and case_metadata.get("experimental_selected") is True
        ):
            continue
        analyzed += 1
        orientation = _classify_selected_case(context_row)
        label = labels_by_review_id[review_id]
        metrics = aggregates[orientation]
        metrics["selected_rows"] += 1
        metrics["review_identity_count"] += 1
        metrics["street_exact_correct_count"] += label["street_label"] == "CORRECT"
        metrics["house_number_exact_correct_count"] += (
            label["house_number_label"] == "CORRECT"
        )
        metrics["joint_street_house_correct_count"] += (
            label["joint_street_house_label"] == "CORRECT"
        )
        metrics["incorrect_or_overreach_count"] += (
            label["street_label"] == "INCORRECT"
            or label["house_number_label"] == "INCORRECT"
            or label["joint_street_house_label"] == "INCORRECT"
            or label["candidate_support_label"] == "NOT_SUPPORTED"
            or label["parser_overreach_label"] == "PRESENT"
        )
        metrics["overall_acceptable_count"] += (
            label["overall_parse_acceptability_label"] == "ACCEPTABLE"
        )
    if analyzed != 9 or sum(item["selected_rows"] for item in aggregates.values()) != 9:
        raise ValueError("targeted orientation selected population mismatch")

    hypothesis_confirmed = (
        aggregates[ORIENTATIONS[0]]["selected_rows"] == 4
        and aggregates[ORIENTATIONS[0]]["joint_street_house_correct_count"] == 4
        and aggregates[ORIENTATIONS[1]]["selected_rows"] == 5
        and aggregates[ORIENTATIONS[1]]["joint_street_house_correct_count"] == 1
        and aggregates[ORIENTATIONS[2]]["selected_rows"] == 0
    )
    payload: dict[str, JsonValue] = {
        "report_version": ORIENTATION_REPORT_VERSION,
        "status": (
            "PARSER_V3_1_ORIENTATION_HYPOTHESIS_CONFIRMED"
            if hypothesis_confirmed
            else "PARSER_V3_1_ORIENTATION_HYPOTHESIS_NOT_CONFIRMED"
        ),
        "implementation_commit": implementation_commit,
        "implementation_fingerprint": orientation_analysis_implementation_fingerprint(),
        "experiment_iteration": _EXPECTED_EXPERIMENT_ITERATION,
        "development_rows": 8_000,
        "targeted_review_population_rows": 11,
        "selected_identities_analyzed": analyzed,
        "all_analyzed_identities_in_frozen_development": True,
        "all_analyzed_identities_in_targeted_review_population": True,
        "orientation_definition": {
            ORIENTATIONS[
                0
            ]: "selected street span precedes selected number span; only trailing material remains residual",
            ORIENTATIONS[
                1
            ]: "leading material remains residual; selected number span precedes selected street span",
            ORIENTATIONS[
                2
            ]: "selected evidence does not satisfy exactly one registered orientation",
        },
        "orientation_aggregates": {
            key: dict(sorted(value.items())) for key, value in aggregates.items()
        },
        "hypothesis": {
            "expected_street_number_residual_selected": 4,
            "expected_street_number_residual_joint_correct": 4,
            "expected_residual_number_street_selected": 5,
            "expected_residual_number_street_joint_correct": 1,
            "confirmed": hypothesis_confirmed,
        },
        "input_artifacts": {
            role: {"sha256": identity[0], "size_bytes": identity[1]}
            for role, identity in sorted(identities.items())
        },
        "review_design": "SINGLE_REVIEWER",
        "primary_reviewer": REVIEWER_IDS[0],
        "locked_rows_read": 0,
        "scientific_scope": "DEVELOPMENT_ONLY",
        "raw_values_reported": False,
        "protected_notes_reported": False,
        "identities_reported": False,
        "paths_reported": False,
    }
    content_digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    payload["report_content_sha256"] = content_digest
    _write_report(output_path, payload)
    return payload
