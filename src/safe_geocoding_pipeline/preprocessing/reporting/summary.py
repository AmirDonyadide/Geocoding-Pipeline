from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
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
    "CHANGE_RATE": frozenset(
        {
            "ROWS_CHANGED",
            "ROWS_UNCHANGED",
            "ROWS_CHANGED_PERCENT_BASIS_POINTS",
        }
    ),
    "FIELD_CHANGES": frozenset(
        {
            "TOTAL_CLEANED_FIELDS",
            "TOTAL_LOWERCASE_FIELDS",
            "CHANGED_FIELDS",
            "UNCHANGED_FIELDS",
        }
    ),
    "FIELD_CHANGED_FIELDS": frozenset(
        {
            "STREET_ADDRESS_LINE_1",
            "STREET_ADDRESS_LINE_2",
            "STREET_ADDRESS_LINE_3",
            "STREET_ADDRESS_LINE_4",
            "STREET_ADDRESS_LINE_1_NATIVE",
            "STREET_ADDRESS_LINE_2_NATIVE",
            "STREET_ADDRESS_LINE_3_NATIVE",
            "STREET_ADDRESS_LINE_4_NATIVE",
            "POSTCODE",
            "CITY",
            "REGION_IN_COUNTRY",
            "COUNTRY_ISO_CODE",
        }
    ),
    "REASON_AFFECTED_ROWS": frozenset(
        {
            "ENCODING_REPAIRED",
            "TERMINAL_ESCAPE_REMOVED",
            "BOM_REMOVED",
            "CONTROL_CHARACTER_REMOVED",
            "TAB_NORMALIZED",
            "LINEBREAK_NORMALIZED",
            "UNICODE_WHITESPACE_NORMALIZED",
            "WHITESPACE_COLLAPSED",
            "WHITESPACE_TRIMMED",
            "WHITESPACE_ONLY_TO_EMPTY",
            "UNICODE_NFC_NORMALIZED",
        }
    ),
    "REASON_AFFECTED_FIELDS": frozenset(
        {
            "ENCODING_REPAIRED",
            "TERMINAL_ESCAPE_REMOVED",
            "BOM_REMOVED",
            "CONTROL_CHARACTER_REMOVED",
            "TAB_NORMALIZED",
            "LINEBREAK_NORMALIZED",
            "UNICODE_WHITESPACE_NORMALIZED",
            "WHITESPACE_COLLAPSED",
            "WHITESPACE_TRIMMED",
            "WHITESPACE_ONLY_TO_EMPTY",
            "UNICODE_NFC_NORMALIZED",
        }
    ),
    "FIELD_GROUP_AFFECTED_ROWS": frozenset(
        {
            "STANDARD_ADDRESS_LINES",
            "NATIVE_ADDRESS_LINES",
            "POSTCODE",
            "CITY_LOCALITY",
            "REGION",
            "COUNTRY_SOURCE_GEOGRAPHY",
        }
    ),
    "FIELD_GROUP_CHANGED_FIELDS": frozenset(
        {
            "STANDARD_ADDRESS_LINES",
            "NATIVE_ADDRESS_LINES",
            "POSTCODE",
            "CITY_LOCALITY",
            "REGION",
            "COUNTRY_SOURCE_GEOGRAPHY",
        }
    ),
    "FIELD_GROUP_TOTAL_FIELDS": frozenset(
        {
            "STANDARD_ADDRESS_LINES",
            "NATIVE_ADDRESS_LINES",
            "POSTCODE",
            "CITY_LOCALITY",
            "REGION",
            "COUNTRY_SOURCE_GEOGRAPHY",
        }
    ),
    "WHITESPACE": frozenset(
        {
            "TAB_NORMALIZED_FIELDS",
            "LINEBREAK_NORMALIZED_FIELDS",
            "UNICODE_WHITESPACE_NORMALIZED_FIELDS",
            "WHITESPACE_COLLAPSED_FIELDS",
            "WHITESPACE_TRIMMED_FIELDS",
            "WHITESPACE_ONLY_TO_EMPTY_FIELDS",
        }
    ),
    "UNICODE_ENCODING": frozenset(
        {
            "UNICODE_NFC_NORMALIZED_FIELDS",
            "ENCODING_REPAIRED_FIELDS",
            "TERMINAL_ESCAPE_REMOVED_FIELDS",
            "BOM_REMOVED_FIELDS",
            "CONTROL_CHARACTER_REMOVED_FIELDS",
        }
    ),
    "PUNCTUATION": frozenset(
        {
            "PUNCTUATION_CHANGED_FIELDS",
            "SEMANTIC_PUNCTUATION_NORMALIZATION_FIELDS",
            "PUNCTUATION_CODEPOINT_CHANGED_FIELDS",
            "PUNCTUATION_CODEPOINT_CHANGED_IN_ENCODING_REPAIRED_FIELDS",
            "PUNCTUATION_CODEPOINT_CHANGED_WITHOUT_ENCODING_REPAIR_FIELDS",
        }
    ),
    "CLEANER_EFFICIENCY": frozenset(
        {
            "TOTAL_FIELD_VALUES",
            "ASCII_FAST_PATH_VALUES",
            "FULL_PROFILE_INVOCATIONS",
            "IDEMPOTENCE_RECHECK_INVOCATIONS",
            "READBACK_CLEANER_INVOCATIONS",
            "TERMINAL_VALIDATION_CLEANER_INVOCATIONS",
            "REPORTING_CLEANER_INVOCATIONS",
        }
    ),
    "OUTPUT_EFFECTS": frozenset(
        {
            "CLEAN_VALUES_BECAME_EMPTY",
            "CHARACTER_COUNT_INCREASE_FIELDS",
            "CHARACTER_COUNT_DECREASE_FIELDS",
            "TOTAL_CHARACTER_COUNT_INCREASE_CODEPOINTS",
            "TOTAL_CHARACTER_COUNT_DECREASE_CODEPOINTS",
            "MAX_LENGTH_INCREASE_CODEPOINTS",
            "MAX_LENGTH_DECREASE_CODEPOINTS",
            "EMPTY_TO_NONEMPTY_FIELDS",
            "NONEMPTY_TO_EMPTY_FIELDS",
            "UNICODE_LENGTH_CHANGED_FIELDS",
            "UNCASED_SCRIPT_UNCHANGED_VALUES",
            "IDEMPOTENCE_FAILURES",
        }
    ),
    "CASE_CHANGE_CLASSIFICATION": frozenset(
        {
            "UNCHANGED",
            "ASCII_CASE_CHANGED",
            "UNICODE_CASE_CHANGED",
            "UNICODE_LENGTH_CHANGED",
        }
    ),
    "SCRIPT_CLASS_TOTAL_VALUES": frozenset(
        {
            "EMPTY",
            "ASCII_ONLY",
            "LATIN_NON_ASCII",
            "CYRILLIC",
            "GREEK",
            "ARABIC_PERSIAN",
            "CJK_HANGUL",
            "MIXED",
            "OTHER",
        }
    ),
    "SCRIPT_CLASS_CHANGED_VALUES": frozenset(
        {
            "EMPTY",
            "ASCII_ONLY",
            "LATIN_NON_ASCII",
            "CYRILLIC",
            "GREEK",
            "ARABIC_PERSIAN",
            "CJK_HANGUL",
            "MIXED",
            "OTHER",
        }
    ),
    "SCRIPT_CLASS_UNCHANGED_VALUES": frozenset(
        {
            "EMPTY",
            "ASCII_ONLY",
            "LATIN_NON_ASCII",
            "CYRILLIC",
            "GREEK",
            "ARABIC_PERSIAN",
            "CJK_HANGUL",
            "MIXED",
            "OTHER",
        }
    ),
    "LOWERCASE_ENGINE": frozenset(
        {
            "ASCII_FAST_PATH_VALUES",
            "PYTHON_LOWER_VALUES",
            "ARROW_UTF8_LOWER_VALUES",
        }
    ),
    "QUALITATIVE_CLASSIFICATIONS": frozenset(
        {
            "EXPECTED_CASE_NORMALIZATION",
            "BENIGN_UNCHANGED_SCRIPT",
            "NO_CASE_CHANGE_REQUIRED",
            "QUESTIONABLE",
            "SEMANTIC_DAMAGE",
        }
    ),
    "PERFORMANCE": frozenset(
        {
            "ELAPSED_MILLISECONDS",
            "USER_CPU_MILLISECONDS",
            "SYSTEM_CPU_MILLISECONDS",
            "MAX_RSS_KIB",
            "ROWS_PER_SECOND_MILLI",
            "FIELDS_PER_SECOND_MILLI",
            "LINEAR_PROJECTED_141048582_ROWS_SECONDS",
            "V1_ELAPSED_MILLISECONDS",
            "CANDIDATE_VALUES_PER_SECOND_MILLI",
        }
    ),
    "REPRESENTATION_AVAILABILITY": frozenset(
        {
            "NO_REPRESENTATION",
            "STANDARD_ONLY",
            "NATIVE_ONLY",
            "BOTH",
            "STANDARD_AVAILABLE",
            "STANDARD_UNAVAILABLE",
            "NATIVE_AVAILABLE",
            "NATIVE_UNAVAILABLE",
        }
    ),
    "BOTH_CANDIDATE_RELATIONSHIP": frozenset({"EXACT_EQUAL_CANONICAL", "DIFFERENT"}),
    "BOTH_LINE_COUNT_RELATIONSHIP": frozenset(
        {"SAME_LINE_COUNT", "DIFFERENT_LINE_COUNT"}
    ),
    "STANDARD_LINE_COUNT": frozenset({"0", "1", "2", "3", "4"}),
    "NATIVE_LINE_COUNT": frozenset({"0", "1", "2", "3", "4"}),
    "STANDARD_OCCUPANCY_MASK": frozenset({f"{value:04b}" for value in range(16)}),
    "NATIVE_OCCUPANCY_MASK": frozenset({f"{value:04b}" for value in range(16)}),
    "GAP_FINDINGS": frozenset({"STANDARD_GAP_ROWS", "NATIVE_GAP_ROWS"}),
    "DUPLICATE_LINE_FINDINGS": frozenset(
        {
            "STANDARD_ROWS_WITH_EXACT_DUPLICATE_CLEAN_LINES",
            "NATIVE_ROWS_WITH_EXACT_DUPLICATE_CLEAN_LINES",
            "STANDARD_ROWS_WITH_EXACT_DUPLICATE_LOWER_LINES",
            "NATIVE_ROWS_WITH_EXACT_DUPLICATE_LOWER_LINES",
            "STANDARD_EXCESS_EXACT_DUPLICATE_CLEAN_VALUES",
            "NATIVE_EXCESS_EXACT_DUPLICATE_CLEAN_VALUES",
            "STANDARD_EXCESS_EXACT_DUPLICATE_LOWER_VALUES",
            "NATIVE_EXCESS_EXACT_DUPLICATE_LOWER_VALUES",
        }
    ),
    "SEPARATOR_BOUNDARIES": frozenset(
        {
            "STANDARD_INTERNAL_BOUNDARIES",
            "NATIVE_INTERNAL_BOUNDARIES",
            "STANDARD_PREDECESSOR_ENDS_COMMA",
            "NATIVE_PREDECESSOR_ENDS_COMMA",
            "STANDARD_SUCCESSOR_STARTS_PUNCTUATION",
            "NATIVE_SUCCESSOR_STARTS_PUNCTUATION",
            "STANDARD_SEPARATOR_OVERHEAD_CODEPOINTS",
            "NATIVE_SEPARATOR_OVERHEAD_CODEPOINTS",
        }
    ),
    "STANDARD_CANDIDATE_LENGTH_CODEPOINTS": frozenset(
        {
            "COUNT",
            "MIN",
            "MEDIAN",
            "MEAN_MILLI",
            "P95_NEAREST_RANK",
            "P99_NEAREST_RANK",
            "MAX",
        }
    ),
    "NATIVE_CANDIDATE_LENGTH_CODEPOINTS": frozenset(
        {
            "COUNT",
            "MIN",
            "MEDIAN",
            "MEAN_MILLI",
            "P95_NEAREST_RANK",
            "P99_NEAREST_RANK",
            "MAX",
        }
    ),
    "VERY_LARGE_CANDIDATES": frozenset(
        {
            "STANDARD_AT_LEAST_1024_CODEPOINTS",
            "STANDARD_AT_LEAST_65536_CODEPOINTS",
            "STANDARD_AT_LEAST_1000000_CODEPOINTS",
            "NATIVE_AT_LEAST_1024_CODEPOINTS",
            "NATIVE_AT_LEAST_65536_CODEPOINTS",
            "NATIVE_AT_LEAST_1000000_CODEPOINTS",
        }
    ),
    "RECONSTRUCTION_VALIDATION": frozenset(
        {
            "RECONSTRUCTION_MISMATCHES",
            "AUDIT_MISMATCHES",
            "CLEAN_LOWER_CONSISTENCY_MISMATCHES",
            "IDEMPOTENCE_FAILURES",
        }
    ),
    "STAGE05_QUALITATIVE_CLASSIFICATIONS": frozenset(
        {
            "CORRECT_RECONSTRUCTION",
            "VALID_BUT_REDUNDANT_SOURCE_CONTENT",
            "QUESTIONABLE_BOUNDARY",
            "QUESTIONABLE_ORDER",
            "SEMANTIC_DAMAGE",
        }
    ),
}

_REQUIRED_CHECKS = frozenset(
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
_OPTIONAL_CHECKS = frozenset(
    {
        "IDEMPOTENCE_VERIFIED",
        "SAME_FIXED_REVIEW_IDENTITIES",
        "SOURCE_PROVENANCE_UNCHANGED",
        "PUNCTUATION_UNCHANGED",
        "NO_SEMANTIC_PUNCTUATION_NORMALIZATION",
        "PUNCTUATION_CODEPOINT_CHANGES_ACCOUNTED",
        "BOUNDED_MEMORY_VALIDATION",
        "NO_TOTAL_ROW_PYTHON_IDENTITY_SET",
        "V1_V2_SCIENTIFIC_OUTPUT_EQUAL",
        "V1_V2_REASON_CODES_EQUAL",
        "STANDARD_NATIVE_INDEPENDENT",
        "ALL_STAGE03_FIELDS_UNCHANGED",
        "EXACT_PYTHON_LOWER_SEMANTICS",
        "CASEFOLD_NOT_USED",
        "LOCALE_SPECIFIC_CASING_NOT_USED",
        "NORMALIZATION_AFTER_LOWER_NOT_USED",
        "ARROW_UTF8_LOWER_NOT_USED",
        "ASCII_FAST_PATH_EQUIVALENT",
        "NO_UNEXPECTED_EMPTY_TRANSITIONS",
        "FIXED_500_QUALITATIVE_REVIEW_COMPLETE",
        "ZERO_QUESTIONABLE",
        "ZERO_SEMANTIC_DAMAGE",
        "ALL_STAGE04_FIELDS_UNCHANGED",
        "LINE_ONLY_RECONSTRUCTION",
        "GEOGRAPHIC_FIELDS_EXCLUDED",
        "DUPLICATE_LINES_PRESERVED",
        "GAPS_PRESERVE_RELATIVE_ORDER",
        "NO_STAGE06_DEDUPLICATION",
        "NO_STAGE07_PARSING",
        "ZERO_QUESTIONABLE_BOUNDARY",
        "ZERO_QUESTIONABLE_ORDER",
    }
)

_ALLOWED_EXTRA_FINGERPRINTS = frozenset(
    {
        "input_binding",
        "manifest",
        "input_stage02_manifest",
        "input_stage03_manifest",
        "input_stage04_manifest",
        "review_subset",
        "review_artifact",
        "ordered_stable_identity",
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
    "STAGE03_CONSERVATIVE_CLEANING_CANDIDATE": (
        "Stage 3 created conservative derived clean text for the complete "
        "35,000-row DEVELOPMENT set while preserving every Stage 2 field; it "
        "remains a candidate pending independent scientific review."
    ),
    "STAGE04_LOWERCASE_CANONICAL_CANDIDATE": (
        "Stage 4 created exact Python Unicode lowercase derived text for the "
        "complete 35,000-row DEVELOPMENT set while preserving every Stage 3 "
        "field; it remains a candidate pending independent scientific review."
    ),
    "STAGE05_ADDRESS_RECONSTRUCTION_CANDIDATE": (
        "Stage 5 reconstructed separate standard and native address-line bodies "
        "for the complete 35,000-row DEVELOPMENT set from exact nonempty source "
        "line order, while preserving every Stage 4 field; it remains a candidate "
        "pending independent scientific review."
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
    extra_fingerprints: Mapping[str, str] = field(default_factory=dict)

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
        if set(self.extra_fingerprints) - _ALLOWED_EXTRA_FINGERPRINTS:
            raise ReviewSubsetError(
                "UNSAFE_SUMMARY", "Additional fingerprint is not allowlisted"
            )
        if any(
            _SHA256_RE.fullmatch(value) is None
            for value in self.extra_fingerprints.values()
        ):
            raise ReviewSubsetError(
                "UNSAFE_SUMMARY", "Additional fingerprint is malformed"
            )
        if set(self.metric_groups) - set(_ALLOWED_METRICS):
            raise ReviewSubsetError("UNSAFE_SUMMARY", "Metric group is not allowlisted")
        for group, metrics in self.metric_groups.items():
            if not metrics or set(metrics) - _ALLOWED_METRICS[group]:
                raise ReviewSubsetError(
                    "UNSAFE_SUMMARY", "Metric category is not allowlisted"
                )
            if any(isinstance(value, bool) or value < 0 for value in metrics.values()):
                raise ReviewSubsetError("UNSAFE_SUMMARY", "Metric value is invalid")
        if (
            not _REQUIRED_CHECKS <= set(self.checks)
            or set(self.checks) - (_REQUIRED_CHECKS | _OPTIONAL_CHECKS)
            or any(not isinstance(value, bool) for value in self.checks.values())
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
                **dict(sorted(self.extra_fingerprints.items())),
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
    for name, digest in sorted(summary.extra_fingerprints.items()):
        lines.append(f"- {name.replace('_', ' ').title()}: `{digest}`")
    for group, values in metrics.items():
        assert isinstance(group, str) and isinstance(values, dict)
        lines.extend(("", f"## {group.replace('_', ' ').title()}", ""))
        for name, count in values.items():
            label = str(name).replace("_", " ").lower()
            if str(name).endswith("PERCENT_BASIS_POINTS"):
                lines.append(f"- {label}: {count / 100:.2f}% ({count} basis points)")
            else:
                lines.append(f"- {label}: {count}")
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
        extra_fingerprints = {
            str(name): str(digest)
            for name, digest in fingerprints.items()
            if name not in {"logical", "schema"}
        }
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
            extra_fingerprints=extra_fingerprints,
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
