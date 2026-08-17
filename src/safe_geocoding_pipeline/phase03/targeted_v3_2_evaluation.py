from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, cast

import pyarrow.parquet as pq

from ..phase02.fingerprints import JsonValue, canonical_json_bytes
from .constants import (
    PARSER_VERSION_V2_1,
    PARSER_VERSION_V3_2,
    RULE_REGISTRY_VERSION_V3,
    RULE_REGISTRY_VERSION_V5,
)
from .pilot_runner import read_identity_set
from .targeted_experiment_review import (
    REVIEWER_IDS,
    TARGETED_REVIEW_SCHEMA_VERSION,
    _experimental_is_parse_a,
    _unblind_comparison,
    targeted_review_context_schema,
    targeted_review_label_schema,
)
from .targeted_orientation_analysis import (
    _EXPECTED_EXPERIMENT_ITERATION,
    _EXPECTED_INPUTS,
)
from .targeted_review_population import (
    SCIENTIFIC_CORE_FIELDS,
    file_sha256,
    read_core,
    read_evidence,
    reject_locked_path,
)
from .validation import validate_core_evidence_relationship

V3_2_REUSE_REPORT_VERSION: Final = (
    "phase03_parser_v3_2_targeted_label_reuse_verification_v1"
)
V3_2_SCORE_REPORT_VERSION: Final = (
    "phase03_parser_v3_2_targeted_single_reviewer_score_v1"
)
V3_2_EVALUATION_MANIFEST_VERSION: Final = (
    "phase03_parser_v3_2_targeted_evaluation_manifest_v1"
)
V4_RULE_IDS: Final = (
    "HOUSE_NUMBER_EMBEDDED_DESIGNATOR_EXPERIMENT_V4",
    "STREET_EMBEDDED_DESIGNATOR_EXPERIMENT_V4",
)
V5_RULE_IDS: Final = (
    "HOUSE_NUMBER_EMBEDDED_DESIGNATOR_EXPERIMENT_V5",
    "STREET_EMBEDDED_DESIGNATOR_EXPERIMENT_V5",
)
_RULE_ID_V5_TO_V4: Final = dict(zip(V5_RULE_IDS, V4_RULE_IDS, strict=True))


def targeted_v3_2_evaluation_implementation_fingerprint() -> str:
    digest = hashlib.sha256(
        b"safe_geocoding_pipeline:phase03_targeted_v3_2_evaluation_v1\0"
    )
    root = Path(__file__).resolve().parent
    for name in (
        "targeted_v3_2_evaluation.py",
        "targeted_experiment_review.py",
        "targeted_review_population.py",
    ):
        encoded = name.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(hashlib.sha256((root / name).read_bytes()).digest())
    return digest.hexdigest()


def _review_id(identity: bytes) -> str:
    encoded = _EXPECTED_EXPERIMENT_ITERATION.encode("utf-8")
    return hashlib.sha256(
        b"safe_geocoding_pipeline:phase03_parser_v3_targeted_review_id_v1\0"
        + len(encoded).to_bytes(8, "big")
        + encoded
        + identity
    ).hexdigest()


def _identity_digest(identities: Sequence[bytes], domain: bytes) -> str:
    digest = hashlib.sha256(domain)
    for identity in sorted(identities):
        digest.update(identity)
    digest.update(len(identities).to_bytes(8, "big"))
    return digest.hexdigest()


def _artifact(path: Path) -> dict[str, JsonValue]:
    return {"sha256": file_sha256(path), "size_bytes": path.stat().st_size}


def _require_input(path: Path) -> Path:
    reject_locked_path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError("v3.2 evaluation input must be a regular file")
    resolved = path.resolve(strict=True)
    reject_locked_path(resolved)
    if path.stat().st_mode & 0o077:
        raise ValueError("v3.2 evaluation input must be owner-only")
    return resolved


def _evidence_semantics(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        str(row["component"]),
        str(row["representation"]),
        str(row["candidate_value"]),
        str(row["source_field"]),
        int(row["start_character"]),
        int(row["end_character_exclusive"]),
        str(row["confidence"]),
    )


def _core_science(
    row: Mapping[str, Any], *, normalize_v5_rules: bool
) -> tuple[Any, ...]:
    values: list[Any] = []
    for field in SCIENTIFIC_CORE_FIELDS:
        value = row[field]
        if field == "selected_component_provenance" and normalize_v5_rules:
            value = [
                {
                    **item,
                    "rule_ids": [
                        _RULE_ID_V5_TO_V4.get(str(rule_id), str(rule_id))
                        for rule_id in item["rule_ids"]
                    ],
                }
                for item in value
            ]
        values.append(value)
    return tuple(values)


def _write_json(path: Path, payload: Mapping[str, JsonValue]) -> None:
    with path.open("xb") as stream:
        os.chmod(path, 0o600)
        stream.write(canonical_json_bytes(dict(payload)) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def evaluate_targeted_v3_2_label_reuse(
    *,
    input_manifest_path: Path,
    protected_context_path: Path,
    controlled_labels_path: Path,
    development_identities_path: Path,
    baseline_core_path: Path,
    baseline_evidence_path: Path,
    v3_2_core_path: Path,
    v3_2_evidence_path: Path,
    comparison_report_path: Path,
    output_directory: Path,
    implementation_commit: str,
    production: bool,
    expected_development_rows: int = 8_000,
    expected_review_rows: int = 11,
    expected_changed_rows: int = 4,
) -> dict[str, Path]:
    """Prove v3.1 label reuse and score narrowed v3.2 without raw output."""
    if production:
        from ..execution_policy import require_goethe_nhr_slurm

        require_goethe_nhr_slurm("phase03-targeted-v3-2-label-reuse-evaluation")
    reject_locked_path(output_directory)
    if output_directory.exists():
        raise FileExistsError("v3.2 evaluation output already exists")
    inputs = {
        "input_manifest": _require_input(input_manifest_path),
        "protected_context": _require_input(protected_context_path),
        "controlled_r01_labels": _require_input(controlled_labels_path),
        "development_identities": _require_input(development_identities_path),
        "baseline_core": _require_input(baseline_core_path),
        "baseline_evidence": _require_input(baseline_evidence_path),
        "v3_2_core": _require_input(v3_2_core_path),
        "v3_2_evidence": _require_input(v3_2_evidence_path),
        "comparison_report": _require_input(comparison_report_path),
    }
    artifacts = {role: _artifact(path) for role, path in inputs.items()}
    if (
        production
        and {
            role: (
                str(artifacts[role]["sha256"]),
                cast(int, artifacts[role]["size_bytes"]),
            )
            for role in ("input_manifest", "protected_context", "controlled_r01_labels")
        }
        != _EXPECTED_INPUTS
    ):
        raise ValueError("v3.2 evaluation review input identity mismatch")

    identity_metadata, development_identities = read_identity_set(
        inputs["development_identities"]
    )
    if (
        identity_metadata.get("partition") != "DEVELOPMENT"
        or len(development_identities) != expected_development_rows
        or len(set(development_identities)) != expected_development_rows
    ):
        raise ValueError("v3.2 evaluation DEVELOPMENT identity mismatch")
    development_set = set(development_identities)

    baseline = read_core(inputs["baseline_core"])
    baseline_evidence = read_evidence(inputs["baseline_evidence"])
    v3_2 = read_core(inputs["v3_2_core"])
    v3_2_evidence = read_evidence(inputs["v3_2_evidence"])
    if (
        len(baseline) != expected_development_rows
        or len(v3_2) != expected_development_rows
    ):
        raise ValueError("v3.2 evaluation core row count mismatch")
    baseline_ids = [bytes(row["stable_source_row_id_v1"]) for row in baseline]
    v3_2_ids = [bytes(row["stable_source_row_id_v1"]) for row in v3_2]
    if baseline_ids != v3_2_ids or set(baseline_ids) != development_set:
        raise ValueError("v3.2 evaluation identity/order mismatch")
    if (
        {str(row["parser_version"]) for row in baseline} != {PARSER_VERSION_V2_1}
        or {str(row["rule_registry_version"]) for row in baseline}
        != {RULE_REGISTRY_VERSION_V3}
        or {str(row["parser_version"]) for row in v3_2} != {PARSER_VERSION_V3_2}
        or {str(row["rule_registry_version"]) for row in v3_2}
        != {RULE_REGISTRY_VERSION_V5}
    ):
        raise ValueError("v3.2 evaluation parser/registry role mismatch")
    validate_core_evidence_relationship(baseline, baseline_evidence)
    validate_core_evidence_relationship(v3_2, v3_2_evidence)
    if {
        bytes(row["stable_source_row_id_v1"])
        for row in (*baseline_evidence, *v3_2_evidence)
    } - development_set:
        raise ValueError("v3.2 evaluation evidence identity mismatch")

    comparison = json.loads(inputs["comparison_report"].read_text(encoding="utf-8"))
    if (
        comparison.get("report_version")
        != "phase03_development_parser_v2_1_v3_2_comparison_v1"
        or comparison.get("rows") != expected_development_rows
        or comparison.get("identity_order_equal") is not True
        or comparison.get("baseline", {}).get("core_sha256")
        != artifacts["baseline_core"]["sha256"]
        or comparison.get("baseline", {}).get("evidence_sha256")
        != artifacts["baseline_evidence"]["sha256"]
        or comparison.get("experimental", {}).get("core_sha256")
        != artifacts["v3_2_core"]["sha256"]
        or comparison.get("experimental", {}).get("evidence_sha256")
        != artifacts["v3_2_evidence"]["sha256"]
        or comparison.get("changes", {}).get("rows_with_scientific_output_change")
        != expected_changed_rows
    ):
        raise ValueError("v3.2 evaluation comparison binding mismatch")

    manifest = json.loads(inputs["input_manifest"].read_text(encoding="utf-8"))
    context_file = pq.ParquetFile(
        inputs["protected_context"], page_checksum_verification=True, pre_buffer=True
    )
    labels_file = pq.ParquetFile(
        inputs["controlled_r01_labels"],
        page_checksum_verification=True,
        pre_buffer=True,
    )
    if (
        manifest.get("experiment_iteration") != _EXPECTED_EXPERIMENT_ITERATION
        or manifest.get("targeted_review_population_rows") != expected_review_rows
        or manifest.get("locked_rows_read") != 0
        or not context_file.schema_arrow.remove_metadata().equals(
            targeted_review_context_schema(), check_metadata=False
        )
        or not labels_file.schema_arrow.remove_metadata().equals(
            targeted_review_label_schema(), check_metadata=False
        )
    ):
        raise ValueError("v3.2 evaluation historical review binding mismatch")
    context = context_file.read(use_threads=False).to_pylist()
    labels = labels_file.read(use_threads=False).to_pylist()
    labels_metadata = {
        key.decode(): value.decode()
        for key, value in (labels_file.schema_arrow.metadata or {}).items()
    }
    if (
        len(context) != expected_review_rows
        or len(labels) != expected_review_rows
        or labels_metadata.get("review_design") != "SINGLE_REVIEWER"
        or labels_metadata.get("primary_reviewer") != REVIEWER_IDS[0]
        or labels_metadata.get("primary_review_complete") != "true"
        or labels_metadata.get("primary_review_rows") != str(expected_review_rows)
        or labels_metadata.get("independent_second_review")
        != "SKIPPED_BY_EXPLICIT_DECISION"
        or labels_metadata.get("locked_rows_read") != "0"
        or any(
            row["reviewer_id"] != REVIEWER_IDS[0]
            or row["assignment_role"] != "PRIMARY"
            or row["label_schema_version"] != TARGETED_REVIEW_SCHEMA_VERSION
            for row in labels
        )
    ):
        raise ValueError("v3.2 evaluation R01 label binding mismatch")

    context_by_id = {bytes(row["stable_source_row_id_v1"]): row for row in context}
    labels_by_review_id = {str(row["hashed_review_id"]): row for row in labels}
    if len(context_by_id) != expected_review_rows or set(labels_by_review_id) != {
        _review_id(identity) for identity in context_by_id
    }:
        raise ValueError("v3.2 evaluation reviewed identity mismatch")

    baseline_by_id = dict(zip(baseline_ids, baseline, strict=True))
    v3_2_by_id = dict(zip(v3_2_ids, v3_2, strict=True))
    changed_ids = {
        identity
        for identity in baseline_ids
        if _core_science(baseline_by_id[identity], normalize_v5_rules=False)
        != _core_science(v3_2_by_id[identity], normalize_v5_rules=False)
    }
    v5_rows = [row for row in v3_2_evidence if row["rule_id"] in V5_RULE_IDS]
    v5_evidence_ids = {bytes(row["stable_source_row_id_v1"]) for row in v5_rows}
    v5_selected_ids = {
        bytes(row["stable_source_row_id_v1"])
        for row in v5_rows
        if bool(row["selected"])
    }
    if (
        len(changed_ids) != expected_changed_rows
        or changed_ids != v5_selected_ids
        or not changed_ids.issubset(context_by_id)
        or not v5_evidence_ids.issubset(context_by_id)
    ):
        raise ValueError("v3.2 evaluation affected population is not review-covered")

    matched_semantics = 0
    for identity, context_row in context_by_id.items():
        baseline_context = cast(
            dict[str, Any], json.loads(str(context_row["baseline_core_json"]))
        )
        v3_1_context = cast(
            dict[str, Any], json.loads(str(context_row["experimental_core_json"]))
        )
        v4_rows = [
            row
            for row in json.loads(str(context_row["experimental_evidence_json"]))
            if row.get("rule_id") in V4_RULE_IDS
        ]
        current_v5 = [
            row for row in v5_rows if bytes(row["stable_source_row_id_v1"]) == identity
        ]
        v4_semantics = {_evidence_semantics(row) for row in v4_rows}
        v5_semantics = {_evidence_semantics(row) for row in current_v5}
        if not v5_semantics.issubset(v4_semantics):
            raise ValueError("v3.2 introduces unseen candidate semantics")
        matched_semantics += len(v5_semantics)
        current = v3_2_by_id[identity]
        if identity in changed_ids:
            if _core_science(current, normalize_v5_rules=True) != _core_science(
                v3_1_context, normalize_v5_rules=False
            ):
                raise ValueError("v3.2 retained selection differs from reviewed v3.1")
        elif _core_science(current, normalize_v5_rules=False) != _core_science(
            baseline_context, normalize_v5_rules=False
        ):
            raise ValueError("v3.2 rejected case does not restore repaired baseline")
    if any(
        identity not in context_by_id
        and _core_science(baseline_by_id[identity], normalize_v5_rules=False)
        != _core_science(v3_2_by_id[identity], normalize_v5_rules=False)
        for identity in baseline_ids
    ):
        raise ValueError("v3.2 changes an unreviewed DEVELOPMENT identity")

    selected_metrics: Counter[str] = Counter()
    rejected_metrics: Counter[str] = Counter()
    comparison_metrics: Counter[str] = Counter()
    for identity, context_row in context_by_id.items():
        label = labels_by_review_id[_review_id(identity)]
        if identity in v5_selected_ids:
            selected_metrics["selected_rows"] += 1
            selected_metrics["street_exact_correct"] += (
                label["street_label"] == "CORRECT"
            )
            selected_metrics["house_number_exact_correct"] += (
                label["house_number_label"] == "CORRECT"
            )
            selected_metrics["joint_street_house_exact_correct"] += (
                label["joint_street_house_label"] == "CORRECT"
            )
            selected_metrics["incorrect"] += (
                label["street_label"] == "INCORRECT"
                or label["house_number_label"] == "INCORRECT"
                or label["joint_street_house_label"] == "INCORRECT"
                or label["candidate_support_label"] == "NOT_SUPPORTED"
            )
            selected_metrics["uncertain"] += (
                label["street_label"] == "CANNOT_ASSESS"
                or label["house_number_label"] == "CANNOT_ASSESS"
                or label["joint_street_house_label"] == "CANNOT_ASSESS"
                or label["candidate_support_label"] == "CANNOT_ASSESS"
            )
        else:
            support = str(label["candidate_support_label"])
            rejected_metrics["would_have_been_correct_if_selected"] += (
                support == "SUPPORTED"
            )
            rejected_metrics["correctly_not_selected"] += support == "NOT_SUPPORTED"
            rejected_metrics["uncertain"] += support == "CANNOT_ASSESS"
        v3_1_comparison = _unblind_comparison(
            str(label["blind_parse_comparison_label"]),
            experimental_is_a=_experimental_is_parse_a(identity, REVIEWER_IDS[0]),
        )
        if identity in v5_selected_ids:
            v3_2_comparison = v3_1_comparison
        else:
            v3_2_comparison = {
                "V2_INCORRECT_V3_CORRECT": "BOTH_INCORRECT",
                "V2_CORRECT_V3_INCORRECT": "BOTH_CORRECT",
            }.get(v3_1_comparison, v3_1_comparison)
        comparison_metrics[v3_2_comparison] += 1

    input_artifacts: dict[str, JsonValue] = {
        role: value for role, value in sorted(artifacts.items())
    }
    common: dict[str, JsonValue] = {
        "implementation_commit": implementation_commit,
        "implementation_fingerprint": (
            targeted_v3_2_evaluation_implementation_fingerprint()
        ),
        "review_design": "SINGLE_REVIEWER",
        "primary_reviewer": REVIEWER_IDS[0],
        "primary_review_complete": True,
        "primary_review_rows": expected_review_rows,
        "independent_second_review": "SKIPPED_BY_EXPLICIT_DECISION",
        "independent_second_review_rows": 0,
        "inter_reviewer_agreement": "NOT_EVALUATED",
        "scientific_scope": "DEVELOPMENT_ONLY",
        "locked_rows_read": 0,
        "raw_values_reported": False,
        "identities_reported": False,
    }
    reuse: dict[str, JsonValue] = {
        "report_version": V3_2_REUSE_REPORT_VERSION,
        "status": "V3_2_EXISTING_R01_LABEL_REUSE_PROVEN_SAFE",
        "development_rows": expected_development_rows,
        "reviewed_population_rows": expected_review_rows,
        "v3_2_scientific_change_rows": len(changed_ids),
        "v3_2_experimental_evidence_identity_count": len(v5_evidence_ids),
        "v3_2_selected_identity_count": len(v5_selected_ids),
        "unreviewed_changed_identity_count": 0,
        "unseen_selected_identity_count": 0,
        "unseen_candidate_semantic_count": 0,
        "matched_candidate_semantic_count": matched_semantics,
        "candidate_semantics_compared": [
            "component",
            "representation",
            "candidate_value",
            "source_field",
            "start_character",
            "end_character_exclusive",
            "confidence",
        ],
        "reviewed_population_digest": _identity_digest(
            tuple(context_by_id),
            b"safe_geocoding_pipeline:phase03_v3_2_reviewed_population_v1\0",
        ),
        "v3_2_selected_identity_digest": _identity_digest(
            tuple(v5_selected_ids),
            b"safe_geocoding_pipeline:phase03_v3_2_selected_population_v1\0",
        ),
        "parser_versions": {
            "baseline": PARSER_VERSION_V2_1,
            "historical_reviewed_experiment": "conservative_address_parser_v3_1_experimental",
            "narrowed_experiment": PARSER_VERSION_V3_2,
        },
        "configuration_fingerprint": bytes(v3_2[0]["configuration_fingerprint"]).hex(),
        "input_artifacts": input_artifacts,
        **common,
    }
    selected_rows = selected_metrics["selected_rows"]
    score: dict[str, JsonValue] = {
        "report_version": V3_2_SCORE_REPORT_VERSION,
        "status": "TARGETED_SINGLE_REVIEWER_V3_2_SCORED_NO_PROMOTION_DECISION",
        "number_reviewed": expected_review_rows,
        "relevant_reviewed_identities": expected_review_rows,
        "selected_experimental_rows": {
            key: selected_metrics[key]
            for key in (
                "selected_rows",
                "street_exact_correct",
                "house_number_exact_correct",
                "joint_street_house_exact_correct",
                "incorrect",
                "uncertain",
            )
        },
        "rejected_experimental_opportunities": {
            key: rejected_metrics[key]
            for key in (
                "would_have_been_correct_if_selected",
                "correctly_not_selected",
                "uncertain",
            )
        },
        "new_selection_precision": {
            "numerator": selected_metrics["street_exact_correct"]
            + selected_metrics["house_number_exact_correct"],
            "denominator": selected_rows * 2,
        },
        "joint_street_house_precision": {
            "numerator": selected_metrics["joint_street_house_exact_correct"],
            "denominator": selected_rows,
        },
        "false_positive_count": selected_metrics["incorrect"],
        "false_negative_opportunity_count": rejected_metrics[
            "would_have_been_correct_if_selected"
        ],
        "parser_comparison": {
            key: comparison_metrics[key]
            for key in (
                "BOTH_CORRECT",
                "V2_INCORRECT_V3_CORRECT",
                "V2_CORRECT_V3_INCORRECT",
                "BOTH_INCORRECT",
                "CANNOT_ASSESS",
            )
        },
        "scientific_promotion_threshold_applied": False,
        "scientific_promotion_decision": "NOT_EVALUATED",
        "reuse_verification_status": reuse["status"],
        **common,
    }

    temporary = output_directory.with_name(
        f".{output_directory.name}.tmp.{os.getpid()}"
    )
    temporary.mkdir(parents=True, mode=0o700)
    temporary.chmod(0o700)
    try:
        reuse_path = temporary / "v3_2_label_reuse_verification.json"
        score_path = temporary / "v3_2_single_reviewer_score.json"
        manifest_path = temporary / "v3_2_targeted_evaluation_manifest.json"
        _write_json(reuse_path, reuse)
        _write_json(score_path, score)
        output_artifacts: dict[str, JsonValue] = {
            path.name: _artifact(path) for path in (reuse_path, score_path)
        }
        evaluation_manifest: dict[str, JsonValue] = {
            "manifest_version": V3_2_EVALUATION_MANIFEST_VERSION,
            "status": "V3_2_TARGETED_EVALUATION_COMPLETE_NO_PROMOTION_DECISION",
            "implementation_commit": implementation_commit,
            "implementation_fingerprint": (
                targeted_v3_2_evaluation_implementation_fingerprint()
            ),
            "output_artifacts": output_artifacts,
            "input_artifacts": input_artifacts,
            **{
                key: common[key]
                for key in (
                    "review_design",
                    "primary_reviewer",
                    "independent_second_review",
                    "inter_reviewer_agreement",
                    "scientific_scope",
                    "locked_rows_read",
                    "raw_values_reported",
                    "identities_reported",
                )
            },
        }
        _write_json(manifest_path, evaluation_manifest)
        os.replace(temporary, output_directory)
        output_directory.chmod(0o700)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return {
        "reuse_verification": output_directory / "v3_2_label_reuse_verification.json",
        "score": output_directory / "v3_2_single_reviewer_score.json",
        "manifest": output_directory / "v3_2_targeted_evaluation_manifest.json",
    }
