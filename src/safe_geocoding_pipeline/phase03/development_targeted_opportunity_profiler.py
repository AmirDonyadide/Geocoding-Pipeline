from __future__ import annotations

import csv
import io
import os
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from ..execution_policy import require_goethe_nhr_slurm
from ..phase02.fingerprints import JsonValue, canonical_json_bytes, fingerprint
from .constants import (
    ADDRESS_FIELDS,
    CONFLICT_FLAGS,
    PARSER_VERSION_V2,
    RULE_REGISTRY_VERSION_V3,
)
from .development_pattern_profiler import (
    MAX_PATTERN_TOKENS,
    MAX_REPORTED_PATTERNS,
    MINIMUM_PATTERN_ROWS,
    _COMPONENT_FIELDS,
    _artifact_state,
    _country_group,
    _group_evidence,
    _pattern,
    _pattern_tokens,
    _read_inputs,
    _reject_locked_paths,
    _script_family,
    _segment_value,
)
from .pilot_runner import read_identity_set
from .references import ScriptReference
from .validation import (
    validate_core_evidence_relationship,
    validate_core_rows,
    validate_evidence_rows,
)


TARGETED_PROFILER_VERSION = (
    "phase03_development_targeted_opportunity_profiler_v1"
)
TARGETED_PROFILE_SCHEMA_VERSION = (
    "phase03_development_targeted_opportunity_profile_v1"
)
TARGET_PATTERN_FAMILIES = (
    "WORDS HOUSELIKE_NUM",
    "HOUSELIKE_NUM WORDS",
    "WORDS HOUSELIKE_NUM WORDS",
    "HOUSELIKE_NUM COMMA WORDS",
    "WORDS COMMA HOUSELIKE_NUM",
    "SLASH_NUMBER WORDS",
    "WORDS SLASH_NUMBER",
    "HYPHEN_NUMBER WORDS",
)
TARGET_RULE_IDS = (
    "HOUSE_NUMBER_EDGE_CANDIDATE_V1",
    "STREET_EXPLICIT_DESIGNATOR_V3",
    "STREET_GENERIC_SEGMENT_V3",
    "HOUSE_NUMBER_EXPLICIT_STREET_V3",
    "HOUSE_NUMBER_GENERIC_STREET_V3",
)
_NUMERIC_TOKENS = frozenset(
    {
        "HOUSELIKE_NUM",
        "NUM",
        "ALNUM",
        "LETTER_SUFFIX_NUMBER",
        "SLASH_NUMBER",
        "HYPHEN_NUMBER",
    }
)
_CANDIDATE_EVIDENCE_KINDS = frozenset(
    {
        "SELECTED_NONTRIVIAL_COMPONENT",
        "UNSELECTED_CANDIDATE",
        "COMPETING_CANDIDATE",
        "CONFLICTING_EVIDENCE",
    }
)


@dataclass(frozen=True, slots=True)
class TargetedProfileArtifacts:
    report_json: Path
    opportunities_csv: Path
    interpretation_markdown: Path
    profile_fingerprint: str
    rows: int


@dataclass(slots=True)
class _FamilyState:
    row_ids: set[bytes] = field(default_factory=set)
    segment_count: int = 0
    dimensions: dict[str, dict[str, set[bytes]]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(set))
    )

    def add(self, dimension: str, category: str, stable_id: bytes) -> None:
        self.dimensions[dimension][category].add(stable_id)


def _representation(fields: Sequence[str]) -> str:
    native = [field_name.endswith("_native") for field_name in fields]
    if native and all(native):
        return "NATIVE"
    if native and not any(native):
        return "NON_NATIVE"
    return "CROSS_REPRESENTATION"


def _source_line(fields: Sequence[str]) -> str:
    lines = {f"LINE_{ADDRESS_FIELDS.index(field_name) % 4 + 1}" for field_name in fields}
    return next(iter(lines)) if len(lines) == 1 else "MULTIPLE_LINES"


def _numeric_position(tokens: Sequence[str]) -> str:
    positions = [index for index, token in enumerate(tokens) if token in _NUMERIC_TOKENS]
    if not positions:
        return "NO_NUMERIC_TOKEN"
    leading = positions[0] == 0
    trailing = positions[-1] == len(tokens) - 1
    if leading and trailing:
        return "NUMERIC_ONLY"
    if leading:
        return "LEADING_NUMBER"
    if trailing:
        return "TRAILING_NUMBER"
    return "EMBEDDED_NUMBER"


def _selected(core: Mapping[str, Any], component: str) -> bool:
    field_name, native_field = _COMPONENT_FIELDS[component]
    return core[field_name] is not None or (
        native_field is not None and core[native_field] is not None
    )


def _adjacent_structures(
    payload: Mapping[str, Any], core: Mapping[str, Any], fields: Sequence[str]
) -> tuple[str, ...]:
    skipped = set(core["skipped_oversized_fields"])
    categories: set[str] = set()
    for field_name in fields:
        index = ADDRESS_FIELDS.index(field_name)
        representation_start = 0 if index < 4 else 4
        line = index % 4
        for offset, label in ((-1, "PREVIOUS"), (1, "NEXT")):
            adjacent_line = line + offset
            if not 0 <= adjacent_line < 4:
                continue
            adjacent_field = ADDRESS_FIELDS[representation_start + adjacent_line]
            if adjacent_field in skipped:
                categories.add(f"{label}_LINE_OVERSIZED_SKIPPED")
                continue
            value = str(payload[adjacent_field])
            if value:
                categories.add(f"{label}_LINE:{_pattern(value)}")
    return tuple(sorted(categories or {"NO_NONEMPTY_ADJACENT_LINE"}))


def _native_relationships(
    payload: Mapping[str, Any],
    core: Mapping[str, Any],
    fields: Sequence[str],
    script_reference: ScriptReference,
) -> tuple[set[str], set[str]]:
    skipped = set(core["skipped_oversized_fields"])
    structure: set[str] = set()
    scripts: set[str] = set()
    for field_name in fields:
        index = ADDRESS_FIELDS.index(field_name)
        line = index % 4
        non_native_field = ADDRESS_FIELDS[line]
        native_field = ADDRESS_FIELDS[line + 4]
        non_native = str(payload[non_native_field])
        native = str(payload[native_field])
        if non_native_field in skipped or native_field in skipped:
            structure.add("OVERSIZED_SKIPPED")
            scripts.add("OVERSIZED_SKIPPED")
        elif not non_native and not native:
            structure.add("BOTH_MISSING")
            scripts.add("BOTH_MISSING")
        elif not native:
            structure.add("NATIVE_MISSING")
            scripts.add("NATIVE_MISSING")
        elif not non_native:
            structure.add("NON_NATIVE_MISSING")
            scripts.add("NON_NATIVE_MISSING")
        else:
            structure.add(
                "SAME_STRUCTURAL_PATTERN"
                if _pattern(non_native) == _pattern(native)
                else "DIFFERENT_STRUCTURAL_PATTERN"
            )
            scripts.add(
                "SAME_SCRIPT_FAMILY"
                if _script_family(non_native, script_reference)
                == _script_family(native, script_reference)
                else "DIFFERENT_SCRIPT_FAMILY"
            )
    return structure, scripts


def _privacy_profile(
    categories: Mapping[str, set[bytes]], *, minimum_rows: int, maximum: int
) -> dict[str, Any]:
    named = {
        category: len(row_ids)
        for category, row_ids in categories.items()
        if len(row_ids) >= minimum_rows
    }
    suppressed = {
        category: len(row_ids)
        for category, row_ids in categories.items()
        if len(row_ids) < minimum_rows
    }
    ordered = sorted(named.items(), key=lambda item: (-item[1], item[0]))
    return {
        "minimum_rows_for_named_category": minimum_rows,
        "maximum_named_categories": maximum,
        "named_categories": dict(ordered[:maximum]),
        "suppressed_distinct_categories": len(suppressed),
        "suppressed_row_memberships": sum(suppressed.values()),
        "truncated_named_category_count": max(0, len(ordered) - maximum),
    }


def _public_count(value: int, minimum_rows: int) -> int | str:
    return value if value == 0 or value >= minimum_rows else "SUPPRESSED"


def _family_report(
    family: str,
    state: _FamilyState,
    *,
    minimum_rows: int,
    maximum_categories: int,
) -> dict[str, Any]:
    dimensions = {
        dimension: _privacy_profile(
            categories, minimum_rows=minimum_rows, maximum=maximum_categories
        )
        for dimension, categories in sorted(state.dimensions.items())
    }
    return {
        "pattern_family": family,
        "affected_development_rows": len(state.row_ids),
        "unresolved_segment_count": state.segment_count,
        "cross_tabs": dimensions,
    }


def _opportunity_rows(
    family_reports: Sequence[Mapping[str, Any]],
    family_states: Mapping[str, _FamilyState],
    minimum_rows: int,
) -> list[dict[str, int | str]]:
    rows: list[dict[str, int | str]] = []
    for report in family_reports:
        def count(dimension: str, category: str) -> int:
            state = family_states[str(report["pattern_family"])]
            return len(state.dimensions.get(dimension, {}).get(category, set()))

        rows.append(
            {
                "pattern_class": str(report["pattern_family"]),
                "affected_development_rows": int(report["affected_development_rows"]),
                "unresolved_segment_count": int(report["unresolved_segment_count"]),
                "street_selected_rows": _public_count(
                    count("selected_components", "STREET_SELECTED"), minimum_rows
                ),
                "house_number_selected_rows": _public_count(
                    count("selected_components", "HOUSE_NUMBER_SELECTED"),
                    minimum_rows,
                ),
                "unselected_street_candidate_rows": _public_count(
                    count("candidate_state", "UNSELECTED_STREET_CANDIDATE"),
                    minimum_rows,
                ),
                "unselected_house_candidate_rows": _public_count(
                    count("candidate_state", "UNSELECTED_HOUSE_NUMBER_CANDIDATE"),
                    minimum_rows,
                ),
                "conflict_rows": _public_count(
                    count("conflict_state", "ANY_CONFLICT"), minimum_rows
                ),
                "unsafe_or_skipped_rows": _public_count(
                    count("diagnostic_support", "UNSAFE_OR_SKIPPED"), minimum_rows
                ),
            }
        )
    return rows


def _csv_bytes(rows: Sequence[Mapping[str, int | str]]) -> bytes:
    columns = (
        "pattern_class",
        "affected_development_rows",
        "unresolved_segment_count",
        "street_selected_rows",
        "house_number_selected_rows",
        "unselected_street_candidate_rows",
        "unselected_house_candidate_rows",
        "conflict_rows",
        "unsafe_or_skipped_rows",
    )
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row[column] for column in columns})
    return buffer.getvalue().encode("utf-8")


def _markdown_bytes(report: Mapping[str, Any]) -> bytes:
    families = cast(Sequence[Mapping[str, Any]], report["pattern_families"])
    sections = (
        ("Higher-support structures", "HIGHER_SUPPORT"),
        ("Ambiguous structures", "AMBIGUOUS"),
        ("Conflict-heavy structures", "CONFLICT_HEAVY"),
        ("Unsafe or skipped structures", "UNSAFE_OR_SKIPPED"),
        ("Possible rule-design hypotheses", "POSSIBLE_HYPOTHESIS"),
    )
    lines = [
        "# Phase 3 DEVELOPMENT targeted opportunity profile",
        "",
        "Status: `SANITIZED_DEVELOPMENT_DIAGNOSTIC_ONLY`.",
        "",
        "These aggregates describe structural opportunities in the fixed DEVELOPMENT corpus. They do not approve Parser v3 rules, and frequency is not evidence of correctness.",
        "",
    ]
    for title, category in sections:
        lines.extend((f"## {title}", ""))
        emitted = False
        for family in families:
            named = family["cross_tabs"]["diagnostic_support"]["named_categories"]
            if category in named:
                lines.append(
                    f"- `{family['pattern_family']}`: {named[category]} DEVELOPMENT rows."
                )
                emitted = True
        if not emitted:
            lines.append("No category met the privacy threshold.")
        lines.append("")
    lines.extend(
        (
            "## False-positive boundaries",
            "",
            "Numeric structure may represent dates, postcodes, units, floors, organization identifiers, or other non-address roles. Country, script, line position, and frequency are diagnostic context only.",
            "",
            "No raw values, identities, paths, evidence spans, or production examples are included.",
            "",
        )
    )
    return "\n".join(lines).encode("utf-8")


def _write_outputs(
    output_directory: Path,
    *,
    report: bytes,
    opportunities: bytes,
    markdown: bytes,
) -> None:
    output_directory.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = output_directory.parent / f".{output_directory.name}.in_progress"
    if output_directory.exists() or temporary.exists():
        raise FileExistsError("targeted development profile output already exists")
    temporary.mkdir(mode=0o700)
    files = {
        "phase03_development_targeted_opportunity_profile.json": report,
        "phase03_development_targeted_opportunities.csv": opportunities,
        "phase03_development_targeted_opportunity_profile.md": markdown,
    }
    try:
        for name, data in files.items():
            path = temporary / name
            with path.open("xb") as stream:
                os.chmod(path, 0o600)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        os.replace(temporary, output_directory)
        output_directory.chmod(0o700)
        directory_fd = os.open(output_directory.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        if temporary.exists():
            for path in temporary.iterdir():
                path.unlink()
            temporary.rmdir()
        raise


def profile_targeted_development_opportunities(
    *,
    development_payload_path: Path,
    core_path: Path,
    evidence_path: Path,
    development_identities_path: Path,
    output_directory: Path,
    script_reference: ScriptReference,
    rule_registry_fingerprint: str,
    expected_rows: int = 8_000,
    production: bool,
    minimum_pattern_rows: int = MINIMUM_PATTERN_ROWS,
    maximum_categories: int = MAX_REPORTED_PATTERNS,
) -> TargetedProfileArtifacts:
    """Create privacy-thresholded diagnostics for approved unresolved patterns."""
    if production:
        require_goethe_nhr_slurm(
            "phase03.development-targeted-opportunity-profile"
        )
    if (
        expected_rows < 1
        or minimum_pattern_rows < 2
        or maximum_categories < 1
        or maximum_categories > MAX_REPORTED_PATTERNS
    ):
        raise ValueError("targeted development profile configuration invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", rule_registry_fingerprint):
        raise ValueError("targeted development profile registry identity invalid")
    inputs = (
        development_payload_path,
        core_path,
        evidence_path,
        development_identities_path,
    )
    _reject_locked_paths((*inputs, output_directory))
    before = {
        role: _artifact_state(path)
        for role, path in zip(
            (
                "development_payload",
                "parser_v2_core",
                "parser_v2_evidence",
                "development_identity_set",
            ),
            inputs,
            strict=True,
        )
    }
    identity_metadata, identities = read_identity_set(development_identities_path)
    if identity_metadata.get("partition") != "DEVELOPMENT":
        raise ValueError("TARGETED_PROFILE_IDENTITY_PARTITION_MISMATCH")
    if len(identities) != expected_rows:
        raise ValueError("TARGETED_PROFILE_IDENTITY_COUNT_MISMATCH")
    payload_rows, core_rows, evidence_rows = _read_inputs(
        development_payload_path, core_path, evidence_path
    )
    if len(payload_rows) != expected_rows or len(core_rows) != expected_rows:
        raise ValueError("TARGETED_PROFILE_ROW_COUNT_MISMATCH")
    payload_by_id = {bytes(row["stable_source_row_id_v1"]): row for row in payload_rows}
    core_by_id = {bytes(row["stable_source_row_id_v1"]): row for row in core_rows}
    identity_set = set(identities)
    if (
        len(payload_by_id) != expected_rows
        or len(core_by_id) != expected_rows
        or set(payload_by_id) != identity_set
        or set(core_by_id) != identity_set
    ):
        raise ValueError("TARGETED_PROFILE_IDENTITY_RECONCILIATION_MISMATCH")
    validate_core_rows(core_rows)
    raw_by_id = {
        identity: {
            field_name: str(row[field_name])
            for field_name in (
                *ADDRESS_FIELDS,
                "postcode",
                "city",
                "region_in_country",
                "country_iso_code",
            )
        }
        for identity, row in payload_by_id.items()
    }
    validate_evidence_rows(evidence_rows, raw_values_by_id=raw_by_id)
    validate_core_evidence_relationship(core_rows, evidence_rows)
    if {str(row["parser_version"]) for row in core_rows} != {PARSER_VERSION_V2}:
        raise ValueError("TARGETED_PROFILE_PARSER_VERSION_MISMATCH")
    if any(
        bytes(row["stable_source_row_id_v1"]) not in identity_set
        for row in evidence_rows
    ):
        raise ValueError("LOCKED_OR_UNKNOWN_EVIDENCE_IDENTITY")
    parser_configuration_fingerprints = {
        bytes(row["configuration_fingerprint"]).hex() for row in core_rows
    }
    implementation_fingerprints = {
        bytes(row["implementation_fingerprint"]).hex() for row in core_rows
    }
    rule_registry_versions = {str(row["rule_registry_version"]) for row in core_rows}
    if (
        len(parser_configuration_fingerprints) != 1
        or len(implementation_fingerprints) != 1
        or len(rule_registry_versions) != 1
    ):
        raise ValueError("TARGETED_PROFILE_CONFIGURATION_NOT_UNIFORM")
    if rule_registry_versions != {RULE_REGISTRY_VERSION_V3}:
        raise ValueError("TARGETED_PROFILE_RULE_REGISTRY_MISMATCH")

    groups = _group_evidence(evidence_rows)
    groups_by_id: dict[bytes, list[Any]] = defaultdict(list)
    for group in groups:
        groups_by_id[group.stable_id].append(group)
    family_states = {family: _FamilyState() for family in TARGET_PATTERN_FAMILIES}
    suppressed_family_rows: set[bytes] = set()
    for group in groups:
        if not (
            group.evidence_kind == "UNASSIGNED_MATERIAL_CONTENT"
            and group.diagnostic_flag == "UNASSIGNED_CONTENT_PRESENT"
        ):
            continue
        payload = payload_by_id[group.stable_id]
        core = core_by_id[group.stable_id]
        value = _segment_value(payload, group.spans)
        family = " ".join(_pattern_tokens(value))
        if family not in family_states:
            suppressed_family_rows.add(group.stable_id)
            continue
        state = family_states[family]
        state.row_ids.add(group.stable_id)
        state.segment_count += 1
        fields = tuple(dict.fromkeys(span[0] for span in group.spans))
        state.add("source_line", _source_line(fields), group.stable_id)
        state.add("representation", _representation(fields), group.stable_id)
        state.add("numeric_position", _numeric_position(_pattern_tokens(value)), group.stable_id)
        state.add(
            "segment_scope",
            "SAME_LINE" if len(fields) == 1 else "CROSS_LINE",
            group.stable_id,
        )
        for category in _adjacent_structures(payload, core, fields):
            state.add("adjacent_line_structure", category, group.stable_id)
        for component in ("street", "house_number"):
            category = f"{component.upper()}_{'SELECTED' if _selected(core, component) else 'NOT_SELECTED'}"
            state.add("selected_components", category, group.stable_id)
        for component in ("postcode", "locality", "region", "country", "building", "unit", "floor"):
            category = f"{component.upper()}_{'SELECTED' if _selected(core, component) else 'NOT_SELECTED'}"
            state.add("corroborating_components", category, group.stable_id)

        row_candidates = [
            candidate
            for candidate in groups_by_id[group.stable_id]
            if candidate.evidence_kind in _CANDIDATE_EVIDENCE_KINDS
        ]
        for rule_id in TARGET_RULE_IDS:
            state.add(
                "target_rule_presence",
                f"{rule_id}:{'PRESENT' if any(candidate.rule_id == rule_id for candidate in row_candidates) else 'ABSENT'}",
                group.stable_id,
            )
        street_candidates = [
            candidate for candidate in row_candidates if candidate.component == "STREET"
        ]
        house_candidates = [
            candidate
            for candidate in row_candidates
            if candidate.component == "HOUSE_NUMBER"
        ]
        if any(not candidate.selected for candidate in street_candidates):
            state.add("candidate_state", "UNSELECTED_STREET_CANDIDATE", group.stable_id)
        if any(not candidate.selected for candidate in house_candidates):
            state.add(
                "candidate_state",
                "UNSELECTED_HOUSE_NUMBER_CANDIDATE",
                group.stable_id,
            )
        if not street_candidates and not house_candidates:
            state.add(
                "candidate_state", "NO_STREET_OR_HOUSE_CANDIDATE", group.stable_id
            )
        competing = any(
            candidate.evidence_kind
            in {"COMPETING_CANDIDATE", "CONFLICTING_EVIDENCE"}
            for candidate in (*street_candidates, *house_candidates)
        )
        state.add(
            "candidate_state",
            "COMPETING_CANDIDATE_PRESENT"
            if competing
            else "NO_COMPETING_CANDIDATE",
            group.stable_id,
        )
        state.add(
            "candidate_multiplicity",
            "MULTIPLE_STREET_CANDIDATES"
            if len(street_candidates) > 1
            else "ONE_STREET_CANDIDATE"
            if street_candidates
            else "NO_STREET_CANDIDATE",
            group.stable_id,
        )
        state.add(
            "candidate_multiplicity",
            "MULTIPLE_HOUSE_NUMBER_CANDIDATES"
            if len(house_candidates) > 1
            else "ONE_HOUSE_NUMBER_CANDIDATE"
            if house_candidates
            else "NO_HOUSE_NUMBER_CANDIDATE",
            group.stable_id,
        )
        conflicts = {str(flag) for flag in core["address_conflict_flags"]}
        state.add(
            "conflict_state",
            "ANY_CONFLICT" if conflicts else "NO_CONFLICT",
            group.stable_id,
        )
        for conflict in sorted(conflicts):
            if conflict not in CONFLICT_FLAGS:
                raise ValueError("TARGETED_PROFILE_UNKNOWN_CONFLICT_FLAG")
            state.add("conflict_type", conflict, group.stable_id)

        structures, scripts = _native_relationships(
            payload, core, fields, script_reference
        )
        for category in structures:
            state.add("native_structural_relationship", category, group.stable_id)
        for category in scripts:
            state.add("native_script_relationship", category, group.stable_id)
        state.add("country_group", _country_group(payload, core), group.stable_id)
        state.add("script_family", _script_family(value, script_reference), group.stable_id)

        unsafe = bool(core["skipped_oversized_fields"]) or str(
            core["diagnostic_evaluation_status"]
        ).startswith("SKIPPED")
        multiple = len(street_candidates) > 1 or len(house_candidates) > 1
        corroborating = sum(
            _selected(core, component)
            for component in ("postcode", "locality", "region", "country")
        )
        diagnostic = (
            "UNSAFE_OR_SKIPPED"
            if unsafe
            else "CONFLICT_HEAVY"
            if conflicts
            else "AMBIGUOUS"
            if multiple or str(core["address_parse_status"]) == "AMBIGUOUS"
            else "HIGHER_SUPPORT"
            if corroborating >= 2
            else "POSSIBLE_HYPOTHESIS"
        )
        state.add("diagnostic_support", diagnostic, group.stable_id)

    retained = [
        _family_report(
            family,
            family_states[family],
            minimum_rows=minimum_pattern_rows,
            maximum_categories=maximum_categories,
        )
        for family in TARGET_PATTERN_FAMILIES
        if len(family_states[family].row_ids) >= minimum_pattern_rows
    ]
    configuration: dict[str, JsonValue] = {
        "profiler_version": TARGETED_PROFILER_VERSION,
        "profile_schema_version": TARGETED_PROFILE_SCHEMA_VERSION,
        "target_pattern_families": list(TARGET_PATTERN_FAMILIES),
        "target_rule_ids": list(TARGET_RULE_IDS),
        "minimum_pattern_rows": minimum_pattern_rows,
        "maximum_categories": maximum_categories,
        "maximum_pattern_tokens": MAX_PATTERN_TOKENS,
    }
    report_body: dict[str, Any] = {
        "profile_schema_version": TARGETED_PROFILE_SCHEMA_VERSION,
        "profiler_version": TARGETED_PROFILER_VERSION,
        "status": "SANITIZED_DEVELOPMENT_DIAGNOSTIC_ONLY",
        "scientific_rule_change": False,
        "rows": expected_rows,
        "input_artifacts": {
            role: {"artifact_role": role, "size_bytes": state[0], "sha256": state[1]}
            for role, state in before.items()
        },
        "input_contract": {
            "identity_partition": "DEVELOPMENT",
            "parser_version": PARSER_VERSION_V2,
            "rule_registry_version": next(iter(rule_registry_versions)),
            "rule_registry_sha256": rule_registry_fingerprint,
            "parser_configuration_fingerprint": next(
                iter(parser_configuration_fingerprints)
            ),
            "implementation_fingerprint": next(iter(implementation_fingerprints)),
            "unicode_script_reference_version": script_reference.version,
            "page_checksums_verified": True,
            "locked_rows_read": 0,
        },
        "profiler_configuration": configuration,
        "profiler_configuration_fingerprint": fingerprint(configuration),
        "privacy_configuration": {
            "minimum_rows_for_named_category": minimum_pattern_rows,
            "maximum_named_categories": maximum_categories,
            "maximum_pattern_tokens": MAX_PATTERN_TOKENS,
            "raw_values_reported": False,
            "identities_reported": False,
            "paths_reported": False,
            "source_spans_reported": False,
        },
        "target_pattern_families": list(TARGET_PATTERN_FAMILIES),
        "pattern_families": retained,
        "suppression_summary": {
            "target_families_below_threshold": sum(
                0 < len(state.row_ids) < minimum_pattern_rows
                for state in family_states.values()
            ),
            "non_target_unassigned_rows": len(suppressed_family_rows),
        },
        "interpretation_guardrails": {
            "parser_v3_rule_creation_authorized": False,
            "frequency_implies_correctness": False,
            "human_labels_used": False,
            "geocoding_used": False,
        },
    }
    profile_fingerprint = fingerprint(cast(JsonValue, report_body))
    report_body["profile_fingerprint"] = profile_fingerprint
    json_bytes = canonical_json_bytes(cast(JsonValue, report_body)) + b"\n"
    opportunity_rows = _opportunity_rows(
        retained, family_states, minimum_pattern_rows
    )
    csv_bytes = _csv_bytes(opportunity_rows)
    markdown_bytes = _markdown_bytes(report_body)
    after = {
        role: _artifact_state(path) for role, path in zip(before, inputs, strict=True)
    }
    if before != after:
        raise ValueError("TARGETED_PROFILE_INPUT_CHANGED_DURING_RUN")
    _write_outputs(
        output_directory,
        report=json_bytes,
        opportunities=csv_bytes,
        markdown=markdown_bytes,
    )
    return TargetedProfileArtifacts(
        report_json=output_directory
        / "phase03_development_targeted_opportunity_profile.json",
        opportunities_csv=output_directory
        / "phase03_development_targeted_opportunities.csv",
        interpretation_markdown=output_directory
        / "phase03_development_targeted_opportunity_profile.md",
        profile_fingerprint=profile_fingerprint,
        rows=expected_rows,
    )
