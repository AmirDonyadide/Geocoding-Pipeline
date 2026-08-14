from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pyarrow.parquet as pq

from ..execution_policy import require_goethe_nhr_slurm
from ..phase02.fingerprints import JsonValue, canonical_json_bytes, fingerprint
from ..phase02.schema import exact_schema_matches
from .constants import (
    ADDRESS_FIELDS,
    CONFLICT_FLAGS,
    NATIVE_RELATIONSHIPS,
    PARSE_STATUSES,
    PARSER_VERSION_V2,
    RULE_REGISTRY_VERSION_V3,
)
from .pilot_runner import read_identity_set
from .references import ScriptReference
from .schema import exact_core_schema_matches, exact_evidence_schema_matches
from .validation import (
    validate_core_evidence_relationship,
    validate_core_rows,
    validate_evidence_rows,
)


PROFILER_VERSION = "phase03_development_pattern_profiler_v1"
PROFILE_SCHEMA_VERSION = "phase03_development_pattern_profile_v1"
MINIMUM_PATTERN_ROWS = 5
MAX_REPORTED_PATTERNS = 100
MAX_PATTERN_TOKENS = 16
_CANDIDATE_EVIDENCE_KINDS = frozenset(
    {
        "SELECTED_NONTRIVIAL_COMPONENT",
        "UNSELECTED_CANDIDATE",
        "COMPETING_CANDIDATE",
        "CONFLICTING_EVIDENCE",
    }
)
_COMPONENT_FIELDS = {
    "street": ("street_clean", "street_native_clean"),
    "house_number": ("house_number_clean", "house_number_native_clean"),
    "unit": ("unit_clean", "unit_native_clean"),
    "floor": ("floor_clean", "floor_native_clean"),
    "building": ("building_clean", "building_native_clean"),
    "organization": ("organization_clean", "organization_native_clean"),
    "postcode": ("postcode_clean", None),
    "locality": ("locality_clean", "locality_native_clean"),
    "region": ("region_clean", "region_native_clean"),
    "country": ("country_clean", "country_native_clean"),
}
_PUNCTUATION = {
    "/": "SLASH",
    "-": "HYPHEN",
    "‐": "HYPHEN",
    "‑": "HYPHEN",
    "‒": "HYPHEN",
    "–": "HYPHEN",
    "—": "HYPHEN",
    ",": "COMMA",
    ";": "SEMICOLON",
    "#": "HASH",
    "(": "PAREN",
    ")": "PAREN",
}
_TOKEN_VOCABULARY = frozenset(
    {
        "HOUSELIKE_NUM",
        "NUM",
        "WORDS",
        "ALNUM",
        "LOCAL_SCRIPT",
        "ROMAN_NUMERAL",
        "SLASH",
        "HYPHEN",
        "COMMA",
        "SEMICOLON",
        "HASH",
        "PAREN",
        "OTHER",
        "NEWLINE",
        "LETTER_SUFFIX_NUMBER",
        "SLASH_NUMBER",
        "HYPHEN_NUMBER",
        "LONG_PATTERN_17_PLUS",
    }
)
_ROMAN = re.compile(r"[IVXLCDM]{1,8}")
_LETTER_SUFFIX_NUMBER = re.compile(r"[0-9]+[A-Za-z]")
_ASCII_ALPHA = re.compile(r"[A-Za-z]+")
_ASCII_ALNUM = re.compile(r"(?=.*[A-Za-z])(?=.*[0-9])[A-Za-z0-9]+")


@dataclass(frozen=True, slots=True)
class ProfileArtifacts:
    report_json: Path
    opportunities_csv: Path
    interpretation_markdown: Path
    profile_fingerprint: str
    rows: int


@dataclass(frozen=True, slots=True)
class _EvidenceGroup:
    stable_id: bytes
    evidence_id: int
    evidence_kind: str
    component: str | None
    selected: bool
    rule_id: str | None
    conflict_flag: str | None
    diagnostic_flag: str | None
    spans: tuple[tuple[str, int, int], ...]


@dataclass(slots=True)
class _Opportunity:
    row_ids: set[bytes] = field(default_factory=set)
    street_selected_ids: set[bytes] = field(default_factory=set)
    house_selected_ids: set[bytes] = field(default_factory=set)
    segment_count: int = 0
    countries: set[str] = field(default_factory=set)
    scripts: set[str] = field(default_factory=set)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_state(path: Path) -> tuple[int, str]:
    return path.stat().st_size, _sha256(path)


def _reject_locked_paths(paths: Iterable[Path]) -> None:
    for path in paths:
        resolved = str(path.resolve(strict=False)).casefold()
        if "locked" in resolved:
            raise ValueError("LOCKED_INPUT_PROHIBITED")


def _read_inputs(
    payload_path: Path,
    core_path: Path,
    evidence_path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    payload_file = pq.ParquetFile(
        payload_path, page_checksum_verification=True, pre_buffer=True
    )
    core_file = pq.ParquetFile(
        core_path, page_checksum_verification=True, pre_buffer=True
    )
    evidence_file = pq.ParquetFile(
        evidence_path, page_checksum_verification=True, pre_buffer=True
    )
    if not exact_schema_matches(payload_file.schema_arrow):
        raise ValueError("DEVELOPMENT_PROFILE_PAYLOAD_SCHEMA_MISMATCH")
    if not exact_core_schema_matches(core_file.schema_arrow):
        raise ValueError("DEVELOPMENT_PROFILE_CORE_SCHEMA_MISMATCH")
    if not exact_evidence_schema_matches(evidence_file.schema_arrow):
        raise ValueError("DEVELOPMENT_PROFILE_EVIDENCE_SCHEMA_MISMATCH")
    payload_rows = cast(
        list[dict[str, Any]], payload_file.read(use_threads=False).to_pylist()
    )
    core_rows = cast(
        list[dict[str, Any]], core_file.read(use_threads=False).to_pylist()
    )
    evidence_rows = cast(
        list[dict[str, Any]], evidence_file.read(use_threads=False).to_pylist()
    )
    return payload_rows, core_rows, evidence_rows


def _group_evidence(rows: Sequence[Mapping[str, Any]]) -> tuple[_EvidenceGroup, ...]:
    grouped: dict[tuple[bytes, int], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[
            (bytes(row["stable_source_row_id_v1"]), int(row["evidence_id"]))
        ].append(row)
    result: list[_EvidenceGroup] = []
    for (stable_id, evidence_id), spans in sorted(
        grouped.items(), key=lambda item: (item[0][0], item[0][1])
    ):
        first = spans[0]
        result.append(
            _EvidenceGroup(
                stable_id=stable_id,
                evidence_id=evidence_id,
                evidence_kind=str(first["evidence_kind"]),
                component=cast(str | None, first["component"]),
                selected=bool(first["selected"]),
                rule_id=cast(str | None, first["rule_id"]),
                conflict_flag=cast(str | None, first["conflict_flag"]),
                diagnostic_flag=cast(str | None, first["diagnostic_flag"]),
                spans=tuple(
                    (
                        str(span["source_field"]),
                        int(span["start_character"]),
                        int(span["end_character_exclusive"]),
                    )
                    for span in spans
                ),
            )
        )
    return tuple(result)


def _raw_token_classes(value: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    while index < len(value):
        character = value[index]
        if character in "\r\n":
            if not tokens or tokens[-1] != "NEWLINE":
                tokens.append("NEWLINE")
            if (
                character == "\r"
                and index + 1 < len(value)
                and value[index + 1] == "\n"
            ):
                index += 1
            index += 1
            continue
        if character.isspace():
            index += 1
            continue
        punctuation = _PUNCTUATION.get(character)
        if punctuation is not None:
            tokens.append(punctuation)
            index += 1
            continue
        category = unicodedata.category(character)
        if category[0] in {"L", "M", "N"}:
            end = index + 1
            while end < len(value) and unicodedata.category(value[end])[0] in {
                "L",
                "M",
                "N",
            }:
                end += 1
            token = value[index:end]
            if token.isdecimal():
                token_class = "HOUSELIKE_NUM" if len(token) <= 4 else "NUM"
            elif _LETTER_SUFFIX_NUMBER.fullmatch(token):
                token_class = "LETTER_SUFFIX_NUMBER"
            elif _ROMAN.fullmatch(token):
                token_class = "ROMAN_NUMERAL"
            elif _ASCII_ALPHA.fullmatch(token):
                token_class = "WORDS"
            elif _ASCII_ALNUM.fullmatch(token):
                token_class = "ALNUM"
            elif any(unicodedata.category(item)[0] in {"L", "M"} for item in token):
                token_class = "LOCAL_SCRIPT"
            else:
                token_class = "OTHER"
            tokens.append(token_class)
            index = end
            continue
        tokens.append("OTHER")
        index += 1
    return tokens


def _pattern_tokens(value: str) -> tuple[str, ...]:
    source = _raw_token_classes(value)
    combined: list[str] = []
    index = 0
    while index < len(source):
        if (
            index + 2 < len(source)
            and source[index] in {"HOUSELIKE_NUM", "NUM"}
            and source[index + 1] in {"SLASH", "HYPHEN"}
            and source[index + 2] in {"HOUSELIKE_NUM", "NUM"}
        ):
            combined.append(
                "SLASH_NUMBER" if source[index + 1] == "SLASH" else "HYPHEN_NUMBER"
            )
            index += 3
            continue
        token = source[index]
        if token == "WORDS" and combined and combined[-1] == "WORDS":
            index += 1
            continue
        if token == "LOCAL_SCRIPT" and combined and combined[-1] == "LOCAL_SCRIPT":
            index += 1
            continue
        combined.append(token)
        index += 1
    if len(combined) > MAX_PATTERN_TOKENS:
        return ("LONG_PATTERN_17_PLUS",)
    if any(token not in _TOKEN_VOCABULARY for token in combined):
        raise AssertionError("unregistered sanitized token class")
    return tuple(combined or ("OTHER",))


def _pattern(value: str) -> str:
    return " ".join(_pattern_tokens(value))


def _segment_value(
    payload: Mapping[str, Any], spans: Sequence[tuple[str, int, int]]
) -> str:
    values: list[str] = []
    for field_name, start, end in spans:
        raw = str(payload[field_name])
        if start < 0 or end > len(raw) or start >= end:
            raise ValueError("DEVELOPMENT_PROFILE_EVIDENCE_SPAN_INVALID")
        values.append(raw[start:end])
    return "\n".join(values)


def _script_family(value: str, reference: ScriptReference) -> str:
    scripts = reference.distinctive_scripts(value)
    if not scripts:
        return "NO_DISTINCTIVE_SCRIPT"
    if len(scripts) > 1:
        return "MIXED_SCRIPT"
    script = next(iter(scripts))
    return "LATIN" if script == "Latin" else f"SCRIPT_{script.upper()}"


def _row_script_family(
    row: Mapping[str, Any],
    reference: ScriptReference,
    skipped_fields: set[str],
) -> str:
    families = {
        _script_family(str(row[field_name]), reference)
        for field_name in ADDRESS_FIELDS
        if str(row[field_name]) and field_name not in skipped_fields
    }
    families.discard("NO_DISTINCTIVE_SCRIPT")
    if not families:
        return "NO_DISTINCTIVE_SCRIPT"
    if len(families) > 1:
        return "MIXED_SCRIPT"
    return next(iter(families))


def _country_group(payload: Mapping[str, Any], core: Mapping[str, Any]) -> str:
    raw_value = str(payload["country_iso_code"])
    if core["country_input_class"] == "ALPHA2_ASSIGNED_EXACT" and re.fullmatch(
        r"[A-Z]{2}", raw_value
    ):
        return raw_value
    return f"INPUT_CLASS_{core['country_input_class']}"


def _numeric_morphologies(tokens: Sequence[str]) -> tuple[str, ...]:
    result: set[str] = set()
    numeric = {
        "HOUSELIKE_NUM",
        "NUM",
        "LETTER_SUFFIX_NUMBER",
        "SLASH_NUMBER",
        "HYPHEN_NUMBER",
        "ALNUM",
    }
    numeric_positions = [
        index for index, token in enumerate(tokens) if token in numeric
    ]
    if not numeric_positions:
        return ("NO_NUMERIC_FORM",)
    if "LETTER_SUFFIX_NUMBER" in tokens:
        result.add("INTEGER_PLUS_LETTER")
    if "SLASH_NUMBER" in tokens:
        result.add("INTEGER_SLASH_INTEGER")
    if "HYPHEN_NUMBER" in tokens:
        result.add("INTEGER_HYPHEN_INTEGER")
    if any(token in {"HOUSELIKE_NUM", "NUM"} for token in tokens):
        result.add("PLAIN_INTEGER")
    if len(numeric_positions) > 1:
        result.add("MULTIPLE_CANDIDATE_NUMBERS")
    if numeric_positions[0] == 0:
        result.add("LEADING_NUMBER")
    if numeric_positions[-1] == len(tokens) - 1:
        result.add("TRAILING_NUMBER")
    if any(0 < position < len(tokens) - 1 for position in numeric_positions):
        result.add("EMBEDDED_NUMBER")
    return tuple(sorted(result))


def _field_shape(value: str) -> str:
    if not value:
        return "EMPTY"
    tokens = _pattern_tokens(value)
    number_tokens = {
        "HOUSELIKE_NUM",
        "NUM",
        "LETTER_SUFFIX_NUMBER",
        "SLASH_NUMBER",
        "HYPHEN_NUMBER",
        "ALNUM",
    }
    text_tokens = {"WORDS", "LOCAL_SCRIPT", "ROMAN_NUMERAL"}
    number_positions = [
        index for index, token in enumerate(tokens) if token in number_tokens
    ]
    has_text = any(token in text_tokens for token in tokens)
    if (
        number_positions
        and not has_text
        and all(
            token in number_tokens | {"SLASH", "HYPHEN", "PAREN", "HASH"}
            for token in tokens
        )
    ):
        return "NUMBER_ONLY"
    if has_text and not number_positions:
        return "TEXT_ONLY"
    if number_positions and has_text:
        if number_positions[0] == 0:
            return "NUMBER_THEN_TEXT"
        if number_positions[-1] == len(tokens) - 1:
            return "TEXT_THEN_NUMBER"
        return "MIXED_NUMBER_TEXT"
    return "OTHER"


def _line_relationships(
    payload: Mapping[str, Any], core: Mapping[str, Any]
) -> set[str]:
    relationships: set[str] = set()
    skipped_fields = set(core["skipped_oversized_fields"])
    for prefix, fields in (
        ("NON_NATIVE", ADDRESS_FIELDS[:4]),
        ("NATIVE", ADDRESS_FIELDS[4:]),
    ):
        shapes = [
            "OVERSIZED_SKIPPED"
            if field_name in skipped_fields
            else _field_shape(str(payload[field_name]))
            for field_name in fields
        ]
        for left in range(3):
            if shapes[left] != "EMPTY" and shapes[left + 1] != "EMPTY":
                relationships.add(
                    f"{prefix}_L{left + 1}_{shapes[left]}_THEN_L{left + 2}_{shapes[left + 1]}"
                )
    for line_number in range(4):
        non_native_field = ADDRESS_FIELDS[line_number]
        native_field = ADDRESS_FIELDS[line_number + 4]
        non_native_empty = not str(payload[non_native_field])
        native_empty = not str(payload[native_field])
        if non_native_field in skipped_fields or native_field in skipped_fields:
            relation = "OVERSIZED_SKIPPED"
        elif non_native_empty and native_empty:
            relation = "BOTH_EMPTY"
        elif non_native_empty or native_empty:
            relation = "ONE_REPRESENTATION_EMPTY"
        elif _pattern(str(payload[non_native_field])) == _pattern(
            str(payload[native_field])
        ):
            relation = "SAME_STRUCTURAL_PATTERN"
        else:
            relation = "DIFFERENT_STRUCTURAL_PATTERN"
        relationships.add(f"LINE_{line_number + 1}_{relation}")
    provenance: dict[str, set[str]] = defaultdict(set)
    for item in core["selected_component_provenance"]:
        provenance[str(item["component"])].update(
            str(value) for value in item["source_fields"]
        )
    for later_component in ("BUILDING", "ORGANIZATION"):
        for street_field in provenance.get("STREET", ()):
            for later_field in provenance.get(later_component, ()):
                if street_field in ADDRESS_FIELDS and later_field in ADDRESS_FIELDS:
                    street_index = ADDRESS_FIELDS.index(street_field)
                    later_index = ADDRESS_FIELDS.index(later_field)
                    if (
                        street_index // 4 == later_index // 4
                        and later_index == street_index + 1
                    ):
                        relationships.add(f"STREET_THEN_{later_component}")
    return relationships


def _bounded_histogram(values: Counter[str], *, maximum: int) -> dict[str, int]:
    ordered = sorted(values.items(), key=lambda item: (-item[1], item[0]))
    return dict(ordered[:maximum])


def _suppressed_pattern_profile(
    counts: Counter[str],
    *,
    minimum_rows: int,
    maximum: int,
    distinct_row_counts: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    disclosure_counts = distinct_row_counts or counts
    retained = Counter(
        {
            key: count
            for key, count in counts.items()
            if disclosure_counts.get(key, 0) >= minimum_rows
        }
    )
    suppressed = {
        key: count
        for key, count in counts.items()
        if disclosure_counts.get(key, 0) < minimum_rows
    }
    return {
        "minimum_rows_for_named_pattern": minimum_rows,
        "maximum_named_patterns": maximum,
        "named_patterns": _bounded_histogram(retained, maximum=maximum),
        "suppressed_distinct_patterns": len(suppressed),
        "suppressed_segment_count": sum(suppressed.values()),
        "truncated_named_pattern_count": max(0, len(retained) - maximum),
    }


def _atomic_output_directory(
    output_directory: Path,
    *,
    json_bytes: bytes,
    csv_bytes: bytes,
    markdown_bytes: bytes,
) -> None:
    parent = output_directory.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = parent / f".{output_directory.name}.in_progress"
    if output_directory.exists() or temporary.exists():
        raise FileExistsError("development profile output already exists")
    temporary.mkdir(mode=0o700)
    files = {
        "phase03_development_pattern_profile.json": json_bytes,
        "phase03_development_pattern_opportunities.csv": csv_bytes,
        "phase03_development_pattern_profile.md": markdown_bytes,
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
        descriptor = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except BaseException:
        if temporary.exists():
            for path in temporary.iterdir():
                path.unlink()
            temporary.rmdir()
        raise


def _opportunity_rows(
    opportunities: Mapping[str, _Opportunity],
    *,
    minimum_rows: int,
    maximum: int,
) -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    for pattern, item in opportunities.items():
        if len(item.row_ids) < minimum_rows:
            continue
        rows.append(
            {
                "pattern_class": pattern,
                "affected_development_rows": len(item.row_ids),
                "unresolved_segment_count": item.segment_count,
                "current_street_selected_rows": len(item.street_selected_ids),
                "current_house_selected_rows": len(item.house_selected_ids),
                "unassigned_rows": len(item.row_ids),
                "country_groups_count": len(item.countries),
                "script_families_count": len(item.scripts),
            }
        )
    rows.sort(
        key=lambda row: (
            -cast(int, row["affected_development_rows"]),
            cast(str, row["pattern_class"]),
        )
    )
    return rows[:maximum]


def _opportunities_csv(rows: Sequence[Mapping[str, str | int]]) -> bytes:
    columns = (
        "pattern_class",
        "affected_development_rows",
        "unresolved_segment_count",
        "current_street_selected_rows",
        "current_house_selected_rows",
        "unassigned_rows",
        "country_groups_count",
        "script_families_count",
    )
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row[column] for column in columns})
    return buffer.getvalue().encode("utf-8")


def _interpretation_markdown(report: Mapping[str, Any]) -> bytes:
    opportunities = cast(
        list[Mapping[str, Any]], report["potential_rule_opportunities"]
    )
    top = opportunities[:10]
    lines = [
        "# Phase 3 DEVELOPMENT pattern profile",
        "",
        "Status: `SANITIZED_DEVELOPMENT_DIAGNOSTIC_ONLY`.",
        "",
        "This report describes aggregate structural patterns in the fixed DEVELOPMENT corpus. Frequency is not evidence that a proposed parser rule is correct.",
        "",
        "## Remaining structural gaps",
        "",
        f"Rows with unassigned content: {report['unassigned_content']['rows']} of {report['rows']}.",
        f"Rows with unresolved street-line content but no street/house candidate: {report['existing_rule_coverage']['rows_without_street_or_house_rule']}.",
        "",
        "## Highest-coverage opportunity families",
        "",
    ]
    if top:
        lines.extend(
            f"- `{row['pattern_class']}`: {row['affected_development_rows']} rows; "
            f"{row['unresolved_segment_count']} unresolved segments."
            for row in top
        )
    else:
        lines.append("No pattern met the configured privacy threshold.")
    lines.extend(
        [
            "",
            "## Parser-v3 research opportunities",
            "",
            "The named pattern families are candidates for synthetic rule-design experiments only. Any future rule requires an explicit version, positive and false-positive boundary tests, and protected DEVELOPMENT review before promotion.",
            "",
            "## False-positive risks",
            "",
            "Numeric morphology can overlap dates, postcodes, floors, units, organization identifiers, and non-address numbers. Line position and frequency alone are not sufficient semantic evidence.",
            "",
            "## Formats that remain unsafe for deterministic assignment",
            "",
            "Rare or long structural patterns, ambiguous numeric-only segments, mixed-role segments, and representations without corroborating component evidence remain unresolved by this diagnostic.",
            "",
            "No raw values, identities, source spans, or production examples are included.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def profile_development_patterns(
    *,
    development_payload_path: Path,
    core_path: Path,
    evidence_path: Path,
    development_identities_path: Path,
    output_directory: Path,
    script_reference: ScriptReference,
    rule_ids: Sequence[str],
    rule_registry_fingerprint: str,
    expected_rows: int = 8_000,
    production: bool,
    minimum_pattern_rows: int = MINIMUM_PATTERN_ROWS,
    maximum_reported_patterns: int = MAX_REPORTED_PATTERNS,
) -> ProfileArtifacts:
    """Profile protected DEVELOPMENT structure into bounded aggregate outputs."""
    if production:
        require_goethe_nhr_slurm("phase03.development-pattern-profile")
    if expected_rows < 1 or minimum_pattern_rows < 2 or maximum_reported_patterns < 1:
        raise ValueError("development profile configuration invalid")
    if (
        not rule_ids
        or len(rule_ids) != len(set(rule_ids))
        or not re.fullmatch(r"[0-9a-f]{64}", rule_registry_fingerprint)
    ):
        raise ValueError("development profile registry identity invalid")
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
        raise ValueError("DEVELOPMENT_PROFILE_IDENTITY_PARTITION_MISMATCH")
    if len(identities) != expected_rows:
        raise ValueError("DEVELOPMENT_PROFILE_IDENTITY_COUNT_MISMATCH")
    payload_rows, core_rows, evidence_rows = _read_inputs(
        development_payload_path, core_path, evidence_path
    )
    if len(payload_rows) != expected_rows or len(core_rows) != expected_rows:
        raise ValueError("DEVELOPMENT_PROFILE_ROW_COUNT_MISMATCH")
    payload_by_id = {bytes(row["stable_source_row_id_v1"]): row for row in payload_rows}
    core_by_id = {bytes(row["stable_source_row_id_v1"]): row for row in core_rows}
    identity_set = set(identities)
    if (
        len(payload_by_id) != expected_rows
        or len(core_by_id) != expected_rows
        or set(payload_by_id) != identity_set
        or set(core_by_id) != identity_set
    ):
        raise ValueError("DEVELOPMENT_PROFILE_IDENTITY_RECONCILIATION_MISMATCH")
    validate_core_rows(core_rows)
    raw_by_id = {
        identity: {field_name: str(row[field_name]) for field_name in ADDRESS_FIELDS}
        | {
            field_name: str(row[field_name])
            for field_name in (
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
        raise ValueError("DEVELOPMENT_PROFILE_PARSER_VERSION_MISMATCH")
    if {str(row["rule_registry_version"]) for row in core_rows} != {
        RULE_REGISTRY_VERSION_V3
    }:
        raise ValueError("DEVELOPMENT_PROFILE_RULE_REGISTRY_MISMATCH")
    parser_configuration_fingerprints = {
        bytes(row["configuration_fingerprint"]).hex() for row in core_rows
    }
    implementation_fingerprints = {
        bytes(row["implementation_fingerprint"]).hex() for row in core_rows
    }
    if (
        len(parser_configuration_fingerprints) != 1
        or len(implementation_fingerprints) != 1
    ):
        raise ValueError("DEVELOPMENT_PROFILE_CONFIGURATION_NOT_UNIFORM")
    if any(
        bytes(row["stable_source_row_id_v1"]) not in identity_set
        for row in evidence_rows
    ):
        raise ValueError("LOCKED_OR_UNKNOWN_EVIDENCE_IDENTITY")

    parse_statuses = Counter(str(row["address_parse_status"]) for row in core_rows)
    components: dict[str, dict[str, int]] = {}
    for component, (field_name, native_field) in _COMPONENT_FIELDS.items():
        selected = sum(row[field_name] is not None for row in core_rows)
        native = (
            sum(row[native_field] is not None for row in core_rows)
            if native_field is not None
            else 0
        )
        components[component] = {
            "selected_rows": selected,
            "selected_native_rows": native,
            "selected_any_representation_rows": sum(
                row[field_name] is not None
                or (native_field is not None and row[native_field] is not None)
                for row in core_rows
            ),
        }

    groups = _group_evidence(evidence_rows)
    unassigned = [
        group
        for group in groups
        if group.evidence_kind == "UNASSIGNED_MATERIAL_CONTENT"
        and group.diagnostic_flag == "UNASSIGNED_CONTENT_PRESENT"
    ]
    unassigned_by_row = Counter(group.stable_id for group in unassigned)
    unassigned_fields = Counter(span[0] for group in unassigned for span in group.spans)
    unassigned_representations = Counter(
        "NATIVE"
        if all(span[0].endswith("_native") for span in group.spans)
        else "NON_NATIVE"
        for group in unassigned
    )
    segments_per_row: Counter[str] = Counter(
        "8_PLUS" if count >= 8 else str(count) for count in unassigned_by_row.values()
    )
    segments_per_row["0"] = expected_rows - len(unassigned_by_row)
    pattern_counts: Counter[str] = Counter()
    pattern_row_ids: dict[str, set[bytes]] = defaultdict(set)
    token_counts: Counter[str] = Counter()
    numeric_counts: Counter[str] = Counter()
    opportunity_state: dict[str, _Opportunity] = defaultdict(_Opportunity)
    row_scripts = {
        identity: _row_script_family(
            payload,
            script_reference,
            set(core_by_id[identity]["skipped_oversized_fields"]),
        )
        for identity, payload in payload_by_id.items()
    }
    for group in unassigned:
        raw_segment = _segment_value(payload_by_id[group.stable_id], group.spans)
        tokens = _pattern_tokens(raw_segment)
        pattern = " ".join(tokens)
        pattern_counts[pattern] += 1
        pattern_row_ids[pattern].add(group.stable_id)
        token_counts.update(tokens)
        numeric_counts.update(_numeric_morphologies(tokens))
        opportunity = opportunity_state[pattern]
        opportunity.row_ids.add(group.stable_id)
        opportunity.segment_count += 1
        core = core_by_id[group.stable_id]
        if core["street_clean"] is not None or core["street_native_clean"] is not None:
            opportunity.street_selected_ids.add(group.stable_id)
        if (
            core["house_number_clean"] is not None
            or core["house_number_native_clean"] is not None
        ):
            opportunity.house_selected_ids.add(group.stable_id)
        opportunity.countries.add(_country_group(payload_by_id[group.stable_id], core))
        opportunity.scripts.add(row_scripts[group.stable_id])

    relationship_counts: Counter[str] = Counter()
    for identity in identities:
        relationship_counts.update(
            _line_relationships(payload_by_id[identity], core_by_id[identity])
        )
    native_relationship_counts = Counter(
        str(item["relationship"])
        for row in core_rows
        for item in row["native_non_native_relationships"]
    )
    conflict_counts = Counter(
        str(flag) for row in core_rows for flag in row["address_conflict_flags"]
    )
    evaluation_status_counts = Counter(
        str(row["diagnostic_evaluation_status"]) for row in core_rows
    )
    skipped_field_counts = Counter(
        str(field_name)
        for row in core_rows
        for field_name in row["skipped_oversized_fields"]
    )

    candidate_groups = [
        group for group in groups if group.evidence_kind in _CANDIDATE_EVIDENCE_KINDS
    ]
    rule_coverage: dict[str, dict[str, int]] = {
        rule_id: {
            "candidate_count": 0,
            "selected_count": 0,
            "unselected_count": 0,
            "conflicting_count": 0,
        }
        for rule_id in rule_ids
    }
    candidate_components_by_row: dict[bytes, set[str]] = defaultdict(set)
    for group in candidate_groups:
        if group.rule_id not in rule_coverage:
            raise ValueError("DEVELOPMENT_PROFILE_UNKNOWN_RULE_ID")
        metrics = rule_coverage[group.rule_id]
        metrics["candidate_count"] += 1
        metrics["selected_count" if group.selected else "unselected_count"] += 1
        metrics["conflicting_count"] += group.conflict_flag is not None
        if group.component is not None:
            candidate_components_by_row[group.stable_id].add(group.component)
    rows_without_street_or_house_rule = sum(
        identity not in candidate_components_by_row
        or not ({"STREET", "HOUSE_NUMBER"} & candidate_components_by_row[identity])
        for identity in unassigned_by_row
    )

    country_counts = Counter(
        _country_group(payload_by_id[identity], core_by_id[identity])
        for identity in identities
    )
    script_counts = Counter(row_scripts.values())
    native_availability: Counter[str] = Counter()
    country_script: Counter[str] = Counter()
    for identity in identities:
        payload = payload_by_id[identity]
        non_native = any(str(payload[field_name]) for field_name in ADDRESS_FIELDS[:4])
        native = any(str(payload[field_name]) for field_name in ADDRESS_FIELDS[4:])
        availability = (
            "BOTH"
            if native and non_native
            else "NATIVE_ONLY"
            if native
            else "NON_NATIVE_ONLY"
            if non_native
            else "NEITHER"
        )
        native_availability[availability] += 1
        if identity in unassigned_by_row:
            country_script[
                f"{_country_group(payload, core_by_id[identity])}|{row_scripts[identity]}|{availability}"
            ] += 1

    opportunities = _opportunity_rows(
        opportunity_state,
        minimum_rows=minimum_pattern_rows,
        maximum=maximum_reported_patterns,
    )
    profiler_configuration: dict[str, JsonValue] = {
        "profiler_version": PROFILER_VERSION,
        "profile_schema_version": PROFILE_SCHEMA_VERSION,
        "minimum_pattern_rows": minimum_pattern_rows,
        "maximum_reported_patterns": maximum_reported_patterns,
        "maximum_pattern_tokens": MAX_PATTERN_TOKENS,
        "token_vocabulary": [
            cast(JsonValue, token) for token in sorted(_TOKEN_VOCABULARY)
        ],
    }
    report_body: dict[str, Any] = {
        "profile_schema_version": PROFILE_SCHEMA_VERSION,
        "profiler_version": PROFILER_VERSION,
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
            "rule_registry_version": RULE_REGISTRY_VERSION_V3,
            "rule_registry_sha256": rule_registry_fingerprint,
            "parser_configuration_fingerprint": next(
                iter(parser_configuration_fingerprints)
            ),
            "implementation_fingerprint": next(iter(implementation_fingerprints)),
            "unicode_script_reference_version": script_reference.version,
            "page_checksums_verified": True,
            "locked_rows_read": 0,
        },
        "profiler_configuration": profiler_configuration,
        "profiler_configuration_fingerprint": fingerprint(profiler_configuration),
        "privacy_configuration": {
            "minimum_pattern_rows": minimum_pattern_rows,
            "maximum_reported_patterns": maximum_reported_patterns,
            "maximum_pattern_tokens": MAX_PATTERN_TOKENS,
            "raw_values_reported": False,
            "identities_reported": False,
            "source_spans_reported": False,
        },
        "parser_v2_status": {
            status: parse_statuses[status] for status in PARSE_STATUSES
        },
        "selected_components": components,
        "unassigned_content": {
            "rows": len(unassigned_by_row),
            "segments": len(unassigned),
            "source_fields": dict(sorted(unassigned_fields.items())),
            "representations": dict(sorted(unassigned_representations.items())),
            "segments_per_affected_row": dict(sorted(segments_per_row.items())),
        },
        "abstract_token_morphology": _bounded_histogram(
            token_counts, maximum=len(_TOKEN_VOCABULARY)
        ),
        "segment_structural_patterns": _suppressed_pattern_profile(
            pattern_counts,
            minimum_rows=minimum_pattern_rows,
            maximum=maximum_reported_patterns,
            distinct_row_counts={
                pattern: len(row_ids) for pattern, row_ids in pattern_row_ids.items()
            },
        ),
        "address_line_relationships": {
            "structural_relationships": _suppressed_pattern_profile(
                relationship_counts,
                minimum_rows=minimum_pattern_rows,
                maximum=maximum_reported_patterns,
            ),
            "parser_v2_native_non_native_relationships": {
                relationship: native_relationship_counts[relationship]
                for relationship in NATIVE_RELATIONSHIPS
            },
        },
        "numeric_morphology": dict(sorted(numeric_counts.items())),
        "conflicts_by_type": {
            conflict: conflict_counts[conflict] for conflict in CONFLICT_FLAGS
        },
        "safety_coverage": {
            "diagnostic_evaluation_status": dict(
                sorted(evaluation_status_counts.items())
            ),
            "skipped_oversized_fields": dict(sorted(skipped_field_counts.items())),
            "oversized_raw_values_tokenized": False,
        },
        "existing_rule_coverage": {
            "rules": rule_coverage,
            "rows_without_street_or_house_rule": rows_without_street_or_house_rule,
        },
        "country_script_stratification": {
            "country_iso_code": dict(sorted(country_counts.items())),
            "script_family": dict(sorted(script_counts.items())),
            "raw_nonempty_native_non_native_availability": dict(
                sorted(native_availability.items())
            ),
            "unassigned_country_script_availability": _suppressed_pattern_profile(
                country_script,
                minimum_rows=minimum_pattern_rows,
                maximum=maximum_reported_patterns,
            ),
        },
        "potential_rule_opportunities": opportunities,
        "interpretation_guardrails": {
            "frequency_implies_correctness": False,
            "rule_creation_authorized": False,
            "human_labels_used": False,
            "geocoding_used": False,
        },
    }
    profile_fingerprint = fingerprint(cast(JsonValue, report_body))
    report_body["profile_fingerprint"] = profile_fingerprint
    json_bytes = canonical_json_bytes(cast(JsonValue, report_body)) + b"\n"
    csv_bytes = _opportunities_csv(opportunities)
    markdown_bytes = _interpretation_markdown(report_body)

    after = {
        role: _artifact_state(path) for role, path in zip(before, inputs, strict=True)
    }
    if before != after:
        raise ValueError("DEVELOPMENT_PROFILE_INPUT_CHANGED_DURING_RUN")
    _atomic_output_directory(
        output_directory,
        json_bytes=json_bytes,
        csv_bytes=csv_bytes,
        markdown_bytes=markdown_bytes,
    )
    return ProfileArtifacts(
        report_json=output_directory / "phase03_development_pattern_profile.json",
        opportunities_csv=output_directory
        / "phase03_development_pattern_opportunities.csv",
        interpretation_markdown=output_directory
        / "phase03_development_pattern_profile.md",
        profile_fingerprint=profile_fingerprint,
        rows=expected_rows,
    )
