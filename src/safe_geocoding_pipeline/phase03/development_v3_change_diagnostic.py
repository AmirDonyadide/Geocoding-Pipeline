from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

import pyarrow.parquet as pq

from ..phase02.fingerprints import canonical_json_bytes, fingerprint
from .constants import (
    COMPLETENESS_CLASSES,
    CONFLICT_FLAGS,
    CORE_COLUMNS,
    DIAGNOSTIC_FLAGS,
    EVALUATION_STATUSES,
    PARSER_VERSION_V2,
    PARSER_VERSION_V3,
    POSTCODE_FLAGS,
    REPRESENTATIONS,
    RULE_REGISTRY_VERSION_V3,
    RULE_REGISTRY_VERSION_V4,
)
from .pilot_runner import read_identity_set
from .schema import exact_core_schema_matches, exact_evidence_schema_matches
from .validation import (
    validate_core_evidence_relationship,
    validate_core_rows,
    validate_evidence_rows,
)

DIAGNOSTIC_VERSION: Final = "phase03_parser_v3_change_diagnostic_v1"
REPORT_SCHEMA_VERSION: Final = "phase03_parser_v3_change_diagnostic_report_v1"
REPORT_STATUS: Final = "SANITIZED_DEVELOPMENT_V3_CHANGE_DIAGNOSTIC_ONLY"
EXPERIMENTAL_RULE_IDS: Final = (
    "HOUSE_NUMBER_EMBEDDED_DESIGNATOR_EXPERIMENT_V4",
    "STREET_EMBEDDED_DESIGNATOR_EXPERIMENT_V4",
)
SCIENTIFIC_CORE_FIELDS: Final = CORE_COLUMNS[5:41]
MINIMUM_REPORTABLE_COMBINATION_COUNT: Final = 5
MAX_REPORTED_COMBINATIONS: Final = 32
_COMMIT = re.compile(r"[0-9a-f]{40}")

_SELECTED_NON_NATIVE_FIELDS: Final = (
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
)
_SELECTED_NATIVE_FIELDS: Final = (
    "street_native_clean",
    "house_number_native_clean",
    "unit_native_clean",
    "floor_native_clean",
    "building_native_clean",
    "organization_native_clean",
    "locality_native_clean",
    "region_native_clean",
    "country_native_clean",
)
_SELECTED_VALUE_FIELDS: Final = (
    *_SELECTED_NON_NATIVE_FIELDS,
    *_SELECTED_NATIVE_FIELDS,
)
SCIENTIFIC_FIELD_FAMILIES: Final[dict[str, tuple[str, ...]]] = {
    "selected_non_native_components": _SELECTED_NON_NATIVE_FIELDS,
    "selected_native_components": _SELECTED_NATIVE_FIELDS,
    "parse_status_and_completeness": (
        "address_parse_status",
        "address_completeness_class",
    ),
    "country_classification": (
        "country_input_class",
        "country_parse_method",
        "country_parse_confidence",
    ),
    "conflicts": ("address_conflict_flags",),
    "diagnostics": (
        "address_diagnostic_flags",
        "postcode_diagnostic_flags",
    ),
    "selected_component_provenance": ("selected_component_provenance",),
    "native_non_native_relationships": ("native_non_native_relationships",),
    "evaluation_and_safety": (
        "diagnostic_evaluation_status",
        "skipped_oversized_fields",
    ),
    "address_role_indicators": (
        "is_po_box",
        "is_historical",
        "probable_non_physical_address",
        "possible_company_only",
    ),
    "input_size_metadata": ("input_max_field_utf8_bytes",),
}

_family_fields = tuple(
    field for fields in SCIENTIFIC_FIELD_FAMILIES.values() for field in fields
)
if len(_family_fields) != len(set(_family_fields)) or set(_family_fields) != set(
    SCIENTIFIC_CORE_FIELDS
):
    raise AssertionError("scientific field-family taxonomy is not an exact partition")


@dataclass(frozen=True, slots=True)
class PopulationExpectation:
    development_rows: int
    scientific_change_rows: int
    experimental_evidence_rows: int
    overlap_rows: int
    changed_only_rows: int
    evidence_only_rows: int
    union_rows: int


PRODUCTION_EXPECTATION: Final = PopulationExpectation(
    development_rows=8_000,
    scientific_change_rows=26,
    experimental_evidence_rows=11,
    overlap_rows=9,
    changed_only_rows=17,
    evidence_only_rows=2,
    union_rows=28,
)


@dataclass(frozen=True, slots=True)
class DevelopmentV3ChangeDiagnosticResult:
    report_json: Path
    report_markdown: Path
    rows: int
    report_fingerprint: str


def _artifact_state(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _reject_locked_path(path: Path) -> None:
    if any("locked" in part.casefold() for part in path.parts):
        raise ValueError("LOCKED paths are prohibited in DEVELOPMENT diagnostics")


def _require_controlled_input(path: Path, controlled_root: Path) -> Path:
    _reject_locked_path(path)
    if not path.is_file() or not os.access(path, os.R_OK):
        raise FileNotFoundError("required DEVELOPMENT diagnostic input is unavailable")
    if path.is_symlink():
        raise ValueError("DEVELOPMENT diagnostic inputs may not be symbolic links")
    resolved = path.resolve(strict=True)
    _reject_locked_path(resolved)
    try:
        resolved.relative_to(controlled_root)
    except ValueError as error:
        raise ValueError(
            "DEVELOPMENT diagnostic input is outside controlled root"
        ) from error
    return resolved


def _require_controlled_output(path: Path, controlled_root: Path) -> Path:
    _reject_locked_path(path)
    resolved = path.resolve(strict=False)
    _reject_locked_path(resolved)
    try:
        resolved.relative_to(controlled_root)
    except ValueError as error:
        raise ValueError(
            "DEVELOPMENT diagnostic output is outside controlled root"
        ) from error
    if path.exists():
        raise FileExistsError("DEVELOPMENT diagnostic output already exists")
    return resolved


def _read_core(path: Path) -> list[dict[str, Any]]:
    parquet = pq.ParquetFile(
        path,
        page_checksum_verification=True,
        pre_buffer=True,
    )
    if not exact_core_schema_matches(parquet.schema_arrow):
        raise ValueError("DEVELOPMENT diagnostic core schema mismatch")
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
        raise ValueError("DEVELOPMENT diagnostic evidence schema mismatch")
    rows = cast(list[dict[str, Any]], parquet.read(use_threads=False).to_pylist())
    validate_evidence_rows(rows)
    return rows


def _changed_fields(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> tuple[str, ...]:
    return tuple(
        field for field in SCIENTIFIC_CORE_FIELDS if before[field] != after[field]
    )


def _field_change_counts(
    identities: set[bytes],
    baseline_by_id: Mapping[bytes, Mapping[str, Any]],
    experimental_by_id: Mapping[bytes, Mapping[str, Any]],
) -> dict[str, int]:
    return {
        field: sum(
            baseline_by_id[identity][field] != experimental_by_id[identity][field]
            for identity in identities
        )
        for field in SCIENTIFIC_CORE_FIELDS
    }


def _family_change_counts(
    identities: set[bytes],
    baseline_by_id: Mapping[bytes, Mapping[str, Any]],
    experimental_by_id: Mapping[bytes, Mapping[str, Any]],
) -> dict[str, int]:
    return {
        family: sum(
            any(
                baseline_by_id[identity][field] != experimental_by_id[identity][field]
                for field in fields
            )
            for identity in identities
        )
        for family, fields in SCIENTIFIC_FIELD_FAMILIES.items()
    }


def _combination_summary(
    identities: set[bytes],
    baseline_by_id: Mapping[bytes, Mapping[str, Any]],
    experimental_by_id: Mapping[bytes, Mapping[str, Any]],
) -> dict[str, Any]:
    combinations = Counter(
        _changed_fields(baseline_by_id[identity], experimental_by_id[identity])
        for identity in identities
    )
    reportable = sorted(
        (
            (fields, count)
            for fields, count in combinations.items()
            if count >= MINIMUM_REPORTABLE_COMBINATION_COUNT
        ),
        key=lambda item: (-item[1], item[0]),
    )
    retained = reportable[:MAX_REPORTED_COMBINATIONS]
    retained_keys = {fields for fields, _ in retained}
    suppressed = [
        (fields, count)
        for fields, count in combinations.items()
        if fields not in retained_keys
    ]
    return {
        "minimum_reportable_count": MINIMUM_REPORTABLE_COMBINATION_COUNT,
        "maximum_reported_combinations": MAX_REPORTED_COMBINATIONS,
        "reported": [
            {"fields": list(fields), "rows": count} for fields, count in retained
        ],
        "reported_rows": sum(count for _, count in retained),
        "suppressed_combination_count": len(suppressed),
        "suppressed_rows": sum(count for _, count in suppressed),
        "total_combinations": len(combinations),
        "total_rows": sum(combinations.values()),
    }


def _provenance_map(
    row: Mapping[str, Any],
) -> dict[tuple[str, str], Mapping[str, Any]]:
    return {
        (str(item["component"]), str(item["representation"])): cast(
            Mapping[str, Any], item
        )
        for item in row["selected_component_provenance"]
    }


def _provenance_summary(
    identities: set[bytes],
    baseline_by_id: Mapping[bytes, Mapping[str, Any]],
    experimental_by_id: Mapping[bytes, Mapping[str, Any]],
) -> dict[str, Any]:
    metrics: Counter[str] = Counter()
    representation_changes: Counter[str] = Counter()
    for identity in identities:
        before = baseline_by_id[identity]
        after = experimental_by_id[identity]
        before_provenance = before["selected_component_provenance"]
        after_provenance = after["selected_component_provenance"]
        values_same = all(
            before[field] == after[field] for field in _SELECTED_VALUE_FIELDS
        )
        if before_provenance == after_provenance:
            continue
        metrics["selected_component_provenance_changed"] += 1
        if values_same:
            metrics["provenance_changed_selected_values_same"] += 1
        before_map = _provenance_map(before)
        after_map = _provenance_map(after)
        before_representations: dict[str, set[str]] = defaultdict(set)
        after_representations: dict[str, set[str]] = defaultdict(set)
        for component, representation in before_map:
            before_representations[component].add(representation)
        for component, representation in after_map:
            after_representations[component].add(representation)
        representation_changed = before_representations != after_representations
        for key in set(before_map) ^ set(after_map):
            representation_changes[key[1]] += 1

        def attribute_by_component(
            items: Sequence[Mapping[str, Any]], attribute: str
        ) -> dict[str, tuple[Any, ...]]:
            grouped: dict[str, list[Any]] = defaultdict(list)
            for item in items:
                value = item[attribute]
                grouped[str(item["component"])].append(
                    tuple(value) if isinstance(value, list) else value
                )
            return {
                component: tuple(sorted(values, key=repr))
                for component, values in grouped.items()
            }

        source_fields_changed = attribute_by_component(
            before_provenance, "source_fields"
        ) != attribute_by_component(after_provenance, "source_fields")
        rule_ids_changed = attribute_by_component(
            before_provenance, "rule_ids"
        ) != attribute_by_component(after_provenance, "rule_ids")
        confidence_changed = attribute_by_component(
            before_provenance, "confidence"
        ) != attribute_by_component(after_provenance, "confidence")
        if representation_changed:
            metrics["representation_changed"] += 1
            if values_same:
                metrics["representation_changed_selected_values_same"] += 1
        metrics["source_fields_changed"] += int(source_fields_changed)
        metrics["rule_ids_changed"] += int(rule_ids_changed)
        metrics["confidence_changed"] += int(confidence_changed)
        metrics["component_membership_changed"] += int(
            set(before_representations) != set(after_representations)
        )
    return {
        "rows": {key: metrics[key] for key in sorted(metrics)},
        "representation_entry_changes": {
            representation: representation_changes[representation]
            for representation in REPRESENTATIONS
        },
    }


def _set_change_counts(
    identities: set[bytes],
    baseline_by_id: Mapping[bytes, Mapping[str, Any]],
    experimental_by_id: Mapping[bytes, Mapping[str, Any]],
    field: str,
    vocabulary: Sequence[str],
) -> dict[str, Any]:
    added: Counter[str] = Counter()
    removed: Counter[str] = Counter()
    rows_with_additions = 0
    rows_with_removals = 0
    for identity in identities:
        before = set(cast(Sequence[str], baseline_by_id[identity][field]))
        after = set(cast(Sequence[str], experimental_by_id[identity][field]))
        additions = after - before
        removals = before - after
        rows_with_additions += bool(additions)
        rows_with_removals += bool(removals)
        added.update(additions)
        removed.update(removals)
    return {
        "rows_with_additions": rows_with_additions,
        "rows_with_removals": rows_with_removals,
        "added": {item: added[item] for item in vocabulary},
        "removed": {item: removed[item] for item in vocabulary},
    }


def _transition_counts(
    identities: set[bytes],
    baseline_by_id: Mapping[bytes, Mapping[str, Any]],
    experimental_by_id: Mapping[bytes, Mapping[str, Any]],
    field: str,
    vocabulary: Sequence[str],
) -> dict[str, int]:
    transitions = Counter(
        f"{baseline_by_id[identity][field]}->{experimental_by_id[identity][field]}"
        for identity in identities
        if baseline_by_id[identity][field] != experimental_by_id[identity][field]
    )
    return {
        f"{before}->{after}": transitions[f"{before}->{after}"]
        for before in vocabulary
        for after in vocabulary
        if before != after
    }


def _evidence_population_summary(
    evidence_rows: Sequence[Mapping[str, Any]],
    *,
    changed_ids: set[bytes],
) -> tuple[set[bytes], dict[str, Any]]:
    by_identity: dict[bytes, dict[tuple[int, str], bool]] = defaultdict(dict)
    for row in evidence_rows:
        rule_id = str(row["rule_id"])
        if rule_id not in EXPERIMENTAL_RULE_IDS:
            continue
        identity = bytes(row["stable_source_row_id_v1"])
        key = (int(row["evidence_id"]), rule_id)
        selected = bool(row["selected"])
        previous = by_identity[identity].get(key)
        if previous is not None and previous != selected:
            raise ValueError("experimental evidence group selection is inconsistent")
        by_identity[identity][key] = selected

    presence: Counter[str] = Counter()
    selection: Counter[str] = Counter()
    population_role: Counter[str] = Counter()
    selected_rule_counts: Counter[str] = Counter()
    selection_by_population: dict[str, Counter[str]] = {
        "overlap": Counter(),
        "evidence_only": Counter(),
    }
    for identity, groups in by_identity.items():
        rules = {rule_id for _, rule_id in groups}
        presence[
            "both_rules"
            if rules == set(EXPERIMENTAL_RULE_IDS)
            else "house_number_only"
            if rules == {EXPERIMENTAL_RULE_IDS[0]}
            else "street_only"
        ] += 1
        states = set(groups.values())
        outcome = (
            "selected"
            if states == {True}
            else "unselected"
            if states == {False}
            else "mixed"
        )
        selection[outcome] += 1
        role = "overlap" if identity in changed_ids else "evidence_only"
        population_role[role] += 1
        selection_by_population[role][outcome] += 1
        if role == "overlap" and (
            rules != set(EXPERIMENTAL_RULE_IDS) or outcome != "selected"
        ):
            raise ValueError("OVERLAP_EXPERIMENTAL_EVIDENCE_NOT_PAIRED_AND_SELECTED")
        for (_, rule_id), selected in groups.items():
            if selected:
                selected_rule_counts[rule_id] += 1
    return set(by_identity), {
        "rule_presence": {
            key: presence[key]
            for key in ("both_rules", "house_number_only", "street_only")
        },
        "selection_outcome": {
            key: selection[key] for key in ("selected", "unselected", "mixed")
        },
        "population_role": {
            key: population_role[key] for key in ("overlap", "evidence_only")
        },
        "selection_outcome_by_population": {
            role: {
                outcome: selection_by_population[role][outcome]
                for outcome in ("selected", "unselected", "mixed")
            }
            for role in ("overlap", "evidence_only")
        },
        "overlap_all_have_both_rules_selected": True,
        "selected_candidate_groups_by_rule": {
            rule_id: selected_rule_counts[rule_id] for rule_id in EXPERIMENTAL_RULE_IDS
        },
    }


def _root_cause_assessment(
    changed_only_ids: set[bytes],
    field_counts: Mapping[str, int],
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    changed_fields = {field for field, count in field_counts.items() if count}
    selected_fields = set(_SELECTED_VALUE_FIELDS)
    status_fields = {"address_parse_status", "address_completeness_class"}
    if not changed_only_ids:
        classification = "UNKNOWN_REQUIRES_AGGREGATE_FOLLOW_UP"
        sufficient = False
        explanation = "NO_CHANGED_ONLY_ROWS_TO_CLASSIFY"
    elif changed_fields & (
        selected_fields | status_fields | {"address_conflict_flags"}
    ):
        classification = "E_ANOTHER_IMPLEMENTATION_DEFECT_EXISTS"
        sufficient = True
        explanation = (
            "SCIENTIFIC_SELECTION_STATUS_OR_CONFLICT_CHANGED_WITHOUT_V4_EVIDENCE"
        )
    elif changed_fields <= {"selected_component_provenance"}:
        classification = "D_PROVENANCE_OR_ARBITRATION_SIDE_EFFECT"
        sufficient = True
        explanation = "CHANGED_ONLY_ROWS_ARE_PROVENANCE_ONLY"
    elif changed_fields <= {
        "address_diagnostic_flags",
        "postcode_diagnostic_flags",
        "diagnostic_evaluation_status",
        "skipped_oversized_fields",
        "input_max_field_utf8_bytes",
        "is_po_box",
        "is_historical",
        "probable_non_physical_address",
        "possible_company_only",
        "native_non_native_relationships",
        "selected_component_provenance",
    }:
        classification = "B_V3_PATH_CHANGED_SCIENTIFIC_METADATA_WITHOUT_V4_EVIDENCE"
        sufficient = True
        explanation = "CHANGED_ONLY_ROWS_ARE_DIAGNOSTIC_METADATA_OR_PROVENANCE"
    else:
        classification = "UNKNOWN_REQUIRES_AGGREGATE_FOLLOW_UP"
        sufficient = False
        explanation = "AGGREGATES_DO_NOT_SUPPORT_ONE_UNIQUE_CLASSIFICATION"
    provenance_rows = cast(Mapping[str, int], provenance["rows"])
    return {
        "classification": classification,
        "aggregate_evidence_sufficient": sufficient,
        "explanation_code": explanation,
        "changed_field_names": sorted(changed_fields),
        "provenance_changed_rows": provenance_rows.get(
            "selected_component_provenance_changed", 0
        ),
        "scientific_rule_change_recommended_automatically": False,
        "targeted_review_expected_count_change_recommended_automatically": False,
    }


def _validate_shared_change_definition() -> dict[str, Any]:
    from .development_comparison import (
        _SCIENTIFIC_CORE_FIELDS as comparison_fields,
    )
    from .targeted_experiment_review import (
        _SCIENTIFIC_CORE_FIELDS as targeted_review_fields,
    )

    if (
        tuple(comparison_fields) != SCIENTIFIC_CORE_FIELDS
        or tuple(targeted_review_fields) != SCIENTIFIC_CORE_FIELDS
    ):
        raise ValueError("SCIENTIFIC_CHANGE_DEFINITION_MISMATCH")
    return {
        "definition": "CORE_COLUMNS[5:41]",
        "field_count": len(SCIENTIFIC_CORE_FIELDS),
        "comparison_matches": True,
        "targeted_review_matches": True,
    }


def _assert_expectation(
    expectation: PopulationExpectation,
    *,
    development_rows: int,
    changed_ids: set[bytes],
    evidence_ids: set[bytes],
) -> dict[str, int]:
    overlap = changed_ids & evidence_ids
    changed_only = changed_ids - evidence_ids
    evidence_only = evidence_ids - changed_ids
    union = changed_ids | evidence_ids
    counts = {
        "development": development_rows,
        "scientific_change": len(changed_ids),
        "experimental_evidence": len(evidence_ids),
        "overlap": len(overlap),
        "changed_only": len(changed_only),
        "evidence_only": len(evidence_only),
        "union": len(union),
        "neither": development_rows - len(union),
    }
    expected = {
        "development": expectation.development_rows,
        "scientific_change": expectation.scientific_change_rows,
        "experimental_evidence": expectation.experimental_evidence_rows,
        "overlap": expectation.overlap_rows,
        "changed_only": expectation.changed_only_rows,
        "evidence_only": expectation.evidence_only_rows,
        "union": expectation.union_rows,
    }
    if any(counts[key] != value for key, value in expected.items()):
        raise ValueError("DEVELOPMENT_V3_DIAGNOSTIC_POPULATION_MISMATCH")
    if counts["neither"] < 0:
        raise ValueError("DEVELOPMENT_V3_DIAGNOSTIC_POPULATION_INVALID")
    return counts


def _render_markdown(payload: Mapping[str, Any]) -> str:
    counts = cast(Mapping[str, int], payload["population"])
    assessment = cast(Mapping[str, Any], payload["root_cause_assessment"])
    field_counts = cast(Mapping[str, Mapping[str, int]], payload["field_change_counts"])
    lines = [
        "# Phase 3 Parser-v3 DEVELOPMENT change diagnostic",
        "",
        f"Status: `{payload['status']}`",
        "",
        "This report is an aggregate, sanitized diagnostic. It contains no raw values, identities, spans, or human labels.",
        "",
        "## Population decomposition",
        "",
        f"- DEVELOPMENT rows: {counts['development']}",
        f"- Scientific core changes (A): {counts['scientific_change']}",
        f"- Experimental V4 evidence (B): {counts['experimental_evidence']}",
        f"- A and B: {counts['overlap']}",
        f"- A only: {counts['changed_only']}",
        f"- B only: {counts['evidence_only']}",
        f"- A or B: {counts['union']}",
        f"- Neither: {counts['neither']}",
        "",
        "## Root-cause assessment",
        "",
        f"- Classification: `{assessment['classification']}`",
        f"- Aggregate evidence sufficient: `{str(assessment['aggregate_evidence_sufficient']).lower()}`",
        f"- Explanation: `{assessment['explanation_code']}`",
        "",
        "## Changed-only scientific fields",
        "",
    ]
    changed_only = field_counts["changed_only"]
    nonzero = [(field, count) for field, count in changed_only.items() if count]
    lines.extend(f"- `{field}`: {count}" for field, count in nonzero)
    if not nonzero:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "Frequency does not establish correctness. This diagnostic does not change parser rules, review membership, or the frozen expected-count gate.",
            "",
        ]
    )
    return "\n".join(lines)


def _implementation_fingerprint(implementation_commit: str) -> str:
    return fingerprint(
        {
            "diagnostic_version": DIAGNOSTIC_VERSION,
            "implementation_commit": implementation_commit,
            "module_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "scientific_core_fields": list(SCIENTIFIC_CORE_FIELDS),
            "experimental_rule_ids": list(EXPERIMENTAL_RULE_IDS),
            "field_families": {
                key: list(value) for key, value in SCIENTIFIC_FIELD_FAMILIES.items()
            },
            "minimum_reportable_combination_count": (
                MINIMUM_REPORTABLE_COMBINATION_COUNT
            ),
            "maximum_reported_combinations": MAX_REPORTED_COMBINATIONS,
        }
    )


def diagnose_development_v3_changes(
    *,
    baseline_core_path: Path,
    baseline_evidence_path: Path,
    experimental_core_path: Path,
    experimental_evidence_path: Path,
    development_identities_path: Path,
    output_directory: Path,
    controlled_root: Path,
    report_root: Path,
    implementation_commit: str,
    production: bool,
    expectation: PopulationExpectation = PRODUCTION_EXPECTATION,
) -> DevelopmentV3ChangeDiagnosticResult:
    """Explain v2/v3 population membership using sanitized aggregates only."""
    if production:
        from ..execution_policy import require_goethe_nhr_slurm

        # This must precede every filesystem query or production input open.
        require_goethe_nhr_slurm("phase03-parser-v3-change-diagnostic")
    if not _COMMIT.fullmatch(implementation_commit):
        raise ValueError("diagnostic implementation commit is invalid")
    change_definition_consistency = _validate_shared_change_definition()

    input_paths = {
        "baseline_core": baseline_core_path,
        "baseline_evidence": baseline_evidence_path,
        "experimental_core": experimental_core_path,
        "experimental_evidence": experimental_evidence_path,
        "development_identities": development_identities_path,
    }
    for path in (
        *input_paths.values(),
        output_directory,
        controlled_root,
        report_root,
    ):
        _reject_locked_path(path)
    root = controlled_root.resolve(strict=True)
    resolved_report_root = report_root.resolve(strict=True)
    _reject_locked_path(root)
    _reject_locked_path(resolved_report_root)
    resolved_inputs = {
        role: _require_controlled_input(path, root)
        for role, path in input_paths.items()
    }
    output = _require_controlled_output(output_directory, resolved_report_root)
    before = {role: _artifact_state(path) for role, path in resolved_inputs.items()}

    identity_metadata, identities = read_identity_set(
        resolved_inputs["development_identities"]
    )
    if identity_metadata.get("partition") != "DEVELOPMENT":
        raise ValueError("diagnostic identity set is not DEVELOPMENT")
    if len(identities) != expectation.development_rows or len(set(identities)) != len(
        identities
    ):
        raise ValueError("diagnostic DEVELOPMENT identity count mismatch")
    identity_set = set(identities)

    baseline = _read_core(resolved_inputs["baseline_core"])
    baseline_evidence = _read_evidence(resolved_inputs["baseline_evidence"])
    experimental = _read_core(resolved_inputs["experimental_core"])
    experimental_evidence = _read_evidence(resolved_inputs["experimental_evidence"])
    if len(baseline) != len(experimental) or len(baseline) != len(identities):
        raise ValueError("diagnostic core row count mismatch")
    baseline_ids = [bytes(row["stable_source_row_id_v1"]) for row in baseline]
    experimental_ids = [bytes(row["stable_source_row_id_v1"]) for row in experimental]
    if baseline_ids != experimental_ids or set(baseline_ids) != identity_set:
        raise ValueError("diagnostic core identity/order mismatch")
    provenance_fields = (
        "id",
        "source_file",
        "source_logical_record_number",
        "source_file_sha256",
    )
    if any(
        before_row[field] != after_row[field]
        for before_row, after_row in zip(baseline, experimental, strict=True)
        for field in provenance_fields
    ):
        raise ValueError("diagnostic source provenance mismatch")
    if {row["parser_version"] for row in baseline} != {PARSER_VERSION_V2} or {
        row["parser_version"] for row in experimental
    } != {PARSER_VERSION_V3}:
        raise ValueError("diagnostic parser role mismatch")
    if {row["rule_registry_version"] for row in baseline} != {
        RULE_REGISTRY_VERSION_V3
    } or {row["rule_registry_version"] for row in experimental} != {
        RULE_REGISTRY_VERSION_V4
    }:
        raise ValueError("diagnostic rule-registry role mismatch")
    if (
        len({bytes(row["configuration_fingerprint"]) for row in baseline}) != 1
        or len({bytes(row["configuration_fingerprint"]) for row in experimental}) != 1
    ):
        raise ValueError("diagnostic configuration fingerprint is not uniform")
    validate_core_evidence_relationship(baseline, baseline_evidence)
    validate_core_evidence_relationship(experimental, experimental_evidence)
    if {
        bytes(row["stable_source_row_id_v1"]) for row in baseline_evidence
    } - identity_set or {
        bytes(row["stable_source_row_id_v1"]) for row in experimental_evidence
    } - identity_set:
        raise ValueError("diagnostic evidence identity mismatch")

    baseline_by_id = {bytes(row["stable_source_row_id_v1"]): row for row in baseline}
    experimental_by_id = {
        bytes(row["stable_source_row_id_v1"]): row for row in experimental
    }
    changed_ids = {
        identity
        for identity in identity_set
        if _changed_fields(baseline_by_id[identity], experimental_by_id[identity])
    }
    evidence_ids, evidence_summary = _evidence_population_summary(
        experimental_evidence,
        changed_ids=changed_ids,
    )
    counts = _assert_expectation(
        expectation,
        development_rows=len(identities),
        changed_ids=changed_ids,
        evidence_ids=evidence_ids,
    )
    populations = {
        "overlap": changed_ids & evidence_ids,
        "changed_only": changed_ids - evidence_ids,
        "evidence_only": evidence_ids - changed_ids,
    }
    field_change_counts = {
        name: _field_change_counts(values, baseline_by_id, experimental_by_id)
        for name, values in populations.items()
    }
    family_change_counts = {
        name: _family_change_counts(values, baseline_by_id, experimental_by_id)
        for name, values in populations.items()
    }
    provenance = {
        name: _provenance_summary(values, baseline_by_id, experimental_by_id)
        for name, values in populations.items()
    }
    diagnostic_changes = {
        name: {
            "address_diagnostic_flags": _set_change_counts(
                values,
                baseline_by_id,
                experimental_by_id,
                "address_diagnostic_flags",
                DIAGNOSTIC_FLAGS,
            ),
            "postcode_diagnostic_flags": _set_change_counts(
                values,
                baseline_by_id,
                experimental_by_id,
                "postcode_diagnostic_flags",
                POSTCODE_FLAGS,
            ),
            "address_conflict_flags": _set_change_counts(
                values,
                baseline_by_id,
                experimental_by_id,
                "address_conflict_flags",
                CONFLICT_FLAGS,
            ),
            "completeness_transitions": _transition_counts(
                values,
                baseline_by_id,
                experimental_by_id,
                "address_completeness_class",
                COMPLETENESS_CLASSES,
            ),
            "evaluation_transitions": _transition_counts(
                values,
                baseline_by_id,
                experimental_by_id,
                "diagnostic_evaluation_status",
                EVALUATION_STATUSES,
            ),
        }
        for name, values in populations.items()
    }

    after = {role: _artifact_state(path) for role, path in resolved_inputs.items()}
    if after != before:
        raise ValueError("DEVELOPMENT_DIAGNOSTIC_INPUT_CHANGED_DURING_READ")
    artifacts: dict[str, Any] = {
        role: {"size_bytes": size, "sha256": digest}
        for role, (size, digest) in before.items()
    }
    implementation_fingerprint = _implementation_fingerprint(implementation_commit)
    payload: dict[str, Any] = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "diagnostic_version": DIAGNOSTIC_VERSION,
        "status": REPORT_STATUS,
        "rows": len(identities),
        "scientific_core_field_definition": "CORE_COLUMNS[5:41]",
        "scientific_core_fields": list(SCIENTIFIC_CORE_FIELDS),
        "change_definition_consistency": change_definition_consistency,
        "experimental_rule_ids": list(EXPERIMENTAL_RULE_IDS),
        "population": counts,
        "field_change_counts": field_change_counts,
        "family_change_counts": family_change_counts,
        "changed_only_field_combinations": _combination_summary(
            populations["changed_only"], baseline_by_id, experimental_by_id
        ),
        "provenance_change_metrics": provenance,
        "diagnostic_conflict_status_changes": diagnostic_changes,
        "experimental_evidence_metrics": evidence_summary,
        "root_cause_assessment": _root_cause_assessment(
            populations["changed_only"],
            field_change_counts["changed_only"],
            provenance["changed_only"],
        ),
        "privacy": {
            "aggregate_only": True,
            "raw_values_reported": False,
            "identities_reported": False,
            "source_spans_reported": False,
            "paths_reported": False,
            "human_labels_read": False,
            "locked_rows_read": 0,
            "rare_field_combination_suppression_threshold": (
                MINIMUM_REPORTABLE_COMBINATION_COUNT
            ),
        },
        "inputs": artifacts,
        "input_hashes_stable_during_read": True,
        "page_checksums_verified": True,
        "implementation_commit": implementation_commit,
        "implementation_fingerprint": implementation_fingerprint,
        "scientific_rule_change": False,
        "human_labels": False,
        "locked_rows_read": 0,
    }
    report_fingerprint = fingerprint(payload)
    payload["report_fingerprint"] = report_fingerprint
    report_bytes = canonical_json_bytes(payload) + b"\n"
    markdown_bytes = _render_markdown(payload).encode("utf-8")

    temporary = output.with_name(f".{output.name}.in_progress.{os.getpid()}")
    if temporary.exists():
        raise FileExistsError("DEVELOPMENT diagnostic temporary output already exists")
    temporary.mkdir(parents=True, mode=0o700)
    temporary.chmod(0o700)
    try:
        json_path = temporary / "phase03_parser_v3_change_diagnostic.json"
        markdown_path = temporary / "phase03_parser_v3_change_diagnostic.md"
        for path, data in (
            (json_path, report_bytes),
            (markdown_path, markdown_bytes),
        ):
            with path.open("xb") as stream:
                os.chmod(path, 0o600)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        if json.loads(json_path.read_bytes()) != payload:
            raise ValueError("DEVELOPMENT diagnostic JSON read-back mismatch")
        os.replace(temporary, output)
        output.chmod(0o700)
        directory_fd = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return DevelopmentV3ChangeDiagnosticResult(
        report_json=output / "phase03_parser_v3_change_diagnostic.json",
        report_markdown=output / "phase03_parser_v3_change_diagnostic.md",
        rows=len(identities),
        report_fingerprint=report_fingerprint,
    )
