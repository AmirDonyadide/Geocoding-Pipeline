from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, cast

from .contracts import DEVELOPMENT_REPORTING_CONTRACT_VERSION, ReviewSubsetError

SANITIZED_SUMMARY_CONTRACT_VERSION = "development_sanitized_summary_v1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SAFE_TOKEN_RE = re.compile(r"^[A-Z0-9_]+$")
_SAFE_VERSION_RE = re.compile(r"^[a-z0-9_]+$")

_ALLOWED_METRICS: Mapping[str, frozenset[str]] = {
    "ROW_INTEGRITY": frozenset(
        {
            "INPUT_ROWS",
            "OUTPUT_ROWS",
            "DROPPED_ROWS",
            "ADDED_ROWS",
            "DUPLICATE_IDENTITIES",
        }
    ),
    "STANDARD_NATIVE_AVAILABILITY": frozenset(
        {"STANDARD_ONLY", "NATIVE_ONLY", "BOTH", "NEITHER"}
    ),
    "STANDARD_LINE_COUNTS": frozenset({"0", "1", "2", "3", "4"}),
    "NATIVE_LINE_COUNTS": frozenset({"0", "1", "2", "3", "4"}),
    "ANOMALIES": frozenset(
        {
            "UNEXPECTED_NULLS",
            "SCHEMA_ANOMALIES",
            "IMPOSSIBLE_STRUCTURAL_VALUES",
            "INVARIANT_VIOLATIONS",
        }
    ),
    "REVIEW_ROW_INTEGRITY": frozenset(
        {"SELECTED_ROWS", "DUPLICATE_IDENTITIES", "HOLDOUT_ROWS"}
    ),
    "SOURCE_FILE_COVERAGE": frozenset(
        {"DEVELOPMENT_SOURCE_FILES", "REVIEW_SOURCE_FILES"}
    ),
    "LOCATION_INFORMATION": frozenset(
        {
            "NO_GEOCODING_INFORMATION",
            "PREVIOUS_GEOCODING_FAILURE",
            "POSTCODE_INTERPOLATED",
            "REGION_INTERPOLATED",
            "EMPTY",
            "OTHER",
        }
    ),
    "BATCH_PRIORITY": frozenset({"0", "1", "2", "3", "EMPTY", "OTHER"}),
    "STANDARD_NATIVE_EQUALITY": frozenset(
        {
            "EXACTLY_EQUAL",
            "CASE_ONLY_OR_TRIVIALLY_EQUAL",
            "MATERIALLY_DIFFERENT",
            "NOT_BOTH_PRESENT",
        }
    ),
    "MISSINGNESS": frozenset(
        {"POSTCODE_MISSING", "CITY_MISSING", "REGION_MISSING", "COUNTRY_MISSING"}
    ),
    "SCRIPT_CLASSES": frozenset(
        {
            "LATIN_ONLY",
            "NON_LATIN_PRESENT",
            "MIXED_SCRIPT",
            "EMPTY",
            "COMMON_OR_UNKNOWN_ONLY",
        }
    ),
    "CHALLENGE_REASONS": frozenset(
        {
            "STANDARD_MISSING_NATIVE_PRESENT",
            "STANDARD_NATIVE_MATERIALLY_DIFFERENT",
            "POSTCODE_MISSING",
            "CITY_MISSING",
            "REGION_MISSING",
            "COUNTRY_MISSING",
            "MULTIPLE_ADDRESS_LINES",
            "NON_LATIN_SCRIPT",
            "MIXED_SCRIPT",
            "VERY_LONG_ADDRESS_FIELD",
            "PREVIOUS_GEOCODING_FAILURE",
            "NO_GEOCODING_INFORMATION",
        }
    ),
    "COUNTRY_COVERAGE": frozenset({"AVAILABLE_COUNTRIES", "REPRESENTED_COUNTRIES"}),
    "QUOTA_SHORTFALLS": frozenset({"SHORTFALL_CATEGORY_COUNT", "SHORTFALL_TOTAL"}),
}

_ALLOWED_CHECKS = frozenset(
    {
        "STABLE_IDENTITIES_PRESERVED",
        "RAW_FIELDS_UNCHANGED",
        "HOLDOUT_UNTOUCHED",
        "OWNER_ONLY_PERMISSIONS",
        "PROTECTED_REVIEW_ARTIFACT",
        "ATOMIC_PUBLICATION",
        "INPUT_IDENTITY_BOUND",
    }
)

_INTERPRETATIONS = {
    "STAGE02_LOSSLESS_HARMONIZATION": (
        "Stage 2 introduced the stable internal schema and standard/native "
        "structural metadata while preserving all 35,000 DEVELOPMENT records "
        "and every incoming field exactly."
    ),
    "REVIEW_SUBSET_FIXED": (
        "The fixed DEVELOPMENT review subset provides protected qualitative "
        "follow-through on the same source rows; full 35,000-row metrics remain "
        "the quantitative development evidence."
    ),
}


@dataclass(frozen=True, slots=True)
class SanitizedStageSummary:
    status: str
    stage: str
    stage_contract_version: str
    execution_git_sha: str
    slurm_job_id: str
    development_dataset: str
    development_fingerprint: str
    input_benchmark_fingerprint: str
    logical_fingerprint: str
    schema_fingerprint: str
    metric_groups: Mapping[str, Mapping[str, int]]
    checks: Mapping[str, bool]
    interpretation_code: str

    def validate(self) -> None:
        if _SAFE_TOKEN_RE.fullmatch(self.status) is None:
            raise ReviewSubsetError(
                "UNSAFE_SUMMARY", "Summary status is not allowlisted"
            )
        if _SAFE_TOKEN_RE.fullmatch(self.stage) is None:
            raise ReviewSubsetError(
                "UNSAFE_SUMMARY", "Summary stage is not allowlisted"
            )
        if _SAFE_VERSION_RE.fullmatch(self.stage_contract_version) is None:
            raise ReviewSubsetError("UNSAFE_SUMMARY", "Stage contract text is unsafe")
        if _GIT_SHA_RE.fullmatch(self.execution_git_sha) is None:
            raise ReviewSubsetError("UNSAFE_SUMMARY", "Execution Git SHA is malformed")
        if not self.slurm_job_id.isdecimal() or len(self.slurm_job_id) > 32:
            raise ReviewSubsetError("UNSAFE_SUMMARY", "SLURM identity is malformed")
        if _SAFE_TOKEN_RE.fullmatch(self.development_dataset) is None:
            raise ReviewSubsetError(
                "UNSAFE_SUMMARY", "Dataset label is not allowlisted"
            )
        for digest in (
            self.development_fingerprint,
            self.input_benchmark_fingerprint,
            self.logical_fingerprint,
            self.schema_fingerprint,
        ):
            if _SHA256_RE.fullmatch(digest) is None:
                raise ReviewSubsetError("UNSAFE_SUMMARY", "Summary digest is malformed")
        if set(self.metric_groups) - set(_ALLOWED_METRICS):
            raise ReviewSubsetError("UNSAFE_SUMMARY", "Metric group is not allowlisted")
        for group, metrics in self.metric_groups.items():
            if not metrics or set(metrics) - _ALLOWED_METRICS[group]:
                raise ReviewSubsetError(
                    "UNSAFE_SUMMARY", "Metric category is not allowlisted"
                )
            if any(isinstance(value, bool) or value < 0 for value in metrics.values()):
                raise ReviewSubsetError("UNSAFE_SUMMARY", "Metric value is invalid")
        if set(self.checks) != _ALLOWED_CHECKS or any(
            not isinstance(value, bool) for value in self.checks.values()
        ):
            raise ReviewSubsetError("UNSAFE_SUMMARY", "Summary checks are incomplete")
        if self.interpretation_code not in _INTERPRETATIONS:
            raise ReviewSubsetError(
                "UNSAFE_SUMMARY", "Interpretation is not a reviewed fixed statement"
            )

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "development_reporting_contract_version": (
                DEVELOPMENT_REPORTING_CONTRACT_VERSION
            ),
            "sanitized_summary_contract_version": SANITIZED_SUMMARY_CONTRACT_VERSION,
            "status": self.status,
            "stage": self.stage,
            "stage_contract_version": self.stage_contract_version,
            "execution": {
                "git_sha": self.execution_git_sha,
                "slurm_job_id": self.slurm_job_id,
            },
            "dataset": {
                "name": self.development_dataset,
                "development_fingerprint": self.development_fingerprint,
                "input_benchmark_fingerprint": self.input_benchmark_fingerprint,
            },
            "fingerprints": {
                "logical": self.logical_fingerprint,
                "schema": self.schema_fingerprint,
            },
            "metrics": {
                group: dict(sorted(values.items()))
                for group, values in sorted(self.metric_groups.items())
            },
            "checks": dict(sorted(self.checks.items())),
            "interpretation_code": self.interpretation_code,
            "interpretation": _INTERPRETATIONS[self.interpretation_code],
        }


def render_summary_json(summary: SanitizedStageSummary) -> str:
    return (
        json.dumps(
            summary.to_dict(),
            ensure_ascii=True,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def render_summary_markdown(summary: SanitizedStageSummary) -> str:
    value = summary.to_dict()
    metrics = value["metrics"]
    assert isinstance(metrics, dict)
    lines = [
        f"# {summary.stage} — sanitized DEVELOPMENT summary",
        "",
        f"Status: `{summary.status}`",
        "",
        str(value["interpretation"]),
        "",
        "This Git-safe report contains aggregate counts and contract identities only. "
        "It contains no source row, address value, selected identity, or HOLDOUT value.",
        "",
        "## Identity",
        "",
        f"- Stage contract: `{summary.stage_contract_version}`",
        f"- Execution Git SHA: `{summary.execution_git_sha}`",
        f"- SLURM job: `{summary.slurm_job_id}`",
        f"- DEVELOPMENT fingerprint: `{summary.development_fingerprint}`",
        f"- Input benchmark fingerprint: `{summary.input_benchmark_fingerprint}`",
        f"- Logical fingerprint: `{summary.logical_fingerprint}`",
        f"- Schema fingerprint: `{summary.schema_fingerprint}`",
    ]
    for group, values in metrics.items():
        assert isinstance(group, str) and isinstance(values, dict)
        lines.extend(("", f"## {group.replace('_', ' ').title()}", ""))
        for name, count in values.items():
            lines.append(f"- {str(name).replace('_', ' ').lower()}: {count}")
    lines.extend(("", "## Provenance and privacy", ""))
    for name, passed in sorted(summary.checks.items()):
        lines.append(
            f"- {name.replace('_', ' ').lower()}: {'PASS' if passed else 'FAIL'}"
        )
    lines.append("")
    return "\n".join(lines)


def validate_sanitized_summary_payload(
    value: Mapping[str, Any],
) -> SanitizedStageSummary:
    """Reconstruct and exactly validate a serialized allowlist-only summary."""
    expected_keys = {
        "development_reporting_contract_version",
        "sanitized_summary_contract_version",
        "status",
        "stage",
        "stage_contract_version",
        "execution",
        "dataset",
        "fingerprints",
        "metrics",
        "checks",
        "interpretation_code",
        "interpretation",
    }
    if set(value) != expected_keys:
        raise ReviewSubsetError("UNSAFE_SUMMARY", "Summary fields are not exact")
    execution = value.get("execution")
    dataset = value.get("dataset")
    fingerprints = value.get("fingerprints")
    metrics = value.get("metrics")
    checks = value.get("checks")
    if not all(
        isinstance(item, dict)
        for item in (execution, dataset, fingerprints, metrics, checks)
    ):
        raise ReviewSubsetError("UNSAFE_SUMMARY", "Summary structure is malformed")
    assert isinstance(execution, dict)
    assert isinstance(dataset, dict)
    assert isinstance(fingerprints, dict)
    assert isinstance(metrics, dict)
    assert isinstance(checks, dict)
    try:
        summary = SanitizedStageSummary(
            status=str(value["status"]),
            stage=str(value["stage"]),
            stage_contract_version=str(value["stage_contract_version"]),
            execution_git_sha=str(execution["git_sha"]),
            slurm_job_id=str(execution["slurm_job_id"]),
            development_dataset=str(dataset["name"]),
            development_fingerprint=str(dataset["development_fingerprint"]),
            input_benchmark_fingerprint=str(dataset["input_benchmark_fingerprint"]),
            logical_fingerprint=str(fingerprints["logical"]),
            schema_fingerprint=str(fingerprints["schema"]),
            metric_groups=cast(Mapping[str, Mapping[str, int]], metrics),
            checks=cast(Mapping[str, bool], checks),
            interpretation_code=str(value["interpretation_code"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ReviewSubsetError(
            "UNSAFE_SUMMARY", "Summary structure is malformed"
        ) from error
    if summary.to_dict() != dict(value):
        raise ReviewSubsetError(
            "UNSAFE_SUMMARY", "Summary serialization is not canonical"
        )
    return summary


def write_sanitized_summary(
    summary: SanitizedStageSummary, *, json_path: Path, markdown_path: Path
) -> None:
    if (
        json_path.exists()
        or json_path.is_symlink()
        or markdown_path.exists()
        or markdown_path.is_symlink()
    ):
        raise ReviewSubsetError("OUTPUT_COLLISION", "Sanitized report already exists")
    if json_path.parent != markdown_path.parent:
        raise ReviewSubsetError(
            "INVALID_REPORT_PATH", "Report paths must share a parent"
        )
    json_path.parent.mkdir(parents=True, exist_ok=True)
    for path, payload in (
        (json_path, render_summary_json(summary)),
        (markdown_path, render_summary_markdown(summary)),
    ):
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)


__all__ = [
    "SANITIZED_SUMMARY_CONTRACT_VERSION",
    "SanitizedStageSummary",
    "render_summary_json",
    "render_summary_markdown",
    "validate_sanitized_summary_payload",
    "write_sanitized_summary",
]
