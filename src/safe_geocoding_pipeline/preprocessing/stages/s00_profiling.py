from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field

from .s00_config import InventoryConfig
from .s00_constants import (
    EXPECTED_COLUMNS,
    NATIVE_PAIRS,
    RAW_CATEGORICAL_FIELDS,
)
from .s00_models import FieldProfile, ValueProfileRow

_DECIMAL_RE = re.compile(r"^[+-]?\d+\.\d+$")
_ALPHANUMERIC_RE = re.compile(r"^[A-Za-z0-9]+$")
_ALPHA_RE = re.compile(r"^[A-Za-z]+$")
_DIGITS_RE = re.compile(r"^\d+$")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def postcode_lexical_category(value: str, placeholders: set[str]) -> str:
    if value == "":
        return "EMPTY"
    if value in placeholders:
        return "EXACT_PLACEHOLDER_CANDIDATE"
    if _DECIMAL_RE.fullmatch(value):
        return "DECIMAL_LOOKING"
    if any(character.isspace() for character in value):
        return "CONTAINS_WHITESPACE"
    if "-" in value:
        return "CONTAINS_HYPHEN"
    if _DIGITS_RE.fullmatch(value):
        return (
            "DIGITS_LEADING_ZERO"
            if len(value) > 1 and value.startswith("0")
            else "DIGITS_ONLY"
        )
    if _ALPHA_RE.fullmatch(value):
        return "ALPHABETIC_ONLY"
    if _ALPHANUMERIC_RE.fullmatch(value):
        return "ALPHANUMERIC"
    return "OTHER"


def native_pair_state(non_native: str, native: str) -> str:
    if non_native == "" and native == "":
        return "BOTH_EMPTY"
    if non_native == "":
        return "NATIVE_ONLY"
    if native == "":
        return "NON_NATIVE_ONLY"
    if non_native == native:
        return "EXACT_EQUAL"
    return "DIFFERENT"


def character_class(value: str) -> str:
    if value == "":
        return "EMPTY"
    return "ASCII_ONLY" if value.isascii() else "CONTAINS_NON_ASCII"


@dataclass(slots=True)
class SafeCategoryCounter:
    max_distinct: int
    max_value_chars: int
    counts: Counter[str] = field(default_factory=Counter)
    total_nonempty: int = 0
    suppressed: bool = False
    suppression_reason: str = ""

    def add(self, value: str) -> bool:
        if value == "":
            return False
        self.total_nonempty += 1
        if self.suppressed:
            return False
        if value[0] in {"=", "+", "@"} or (value[0] == "-" and len(value) > 1):
            self.counts.clear()
            self.suppressed = True
            self.suppression_reason = "UNSAFE_SPREADSHEET_VALUE"
            return True
        if len(value) > self.max_value_chars:
            self.counts.clear()
            self.suppressed = True
            self.suppression_reason = "VALUE_LENGTH_LIMIT_EXCEEDED"
            return True
        if value not in self.counts and len(self.counts) >= self.max_distinct:
            self.counts.clear()
            self.suppressed = True
            self.suppression_reason = "CARDINALITY_LIMIT_EXCEEDED"
            return True
        self.counts[value] += 1
        return False


class FileProfiler:
    def __init__(self, config: InventoryConfig) -> None:
        self.config = config
        self.placeholders = set(config.placeholder_candidates)
        self.field_profiles = [
            FieldProfile(column_position=index, column_name=name)
            for index, name in enumerate(EXPECTED_COLUMNS, start=1)
        ]
        self.placeholder_counts: dict[str, Counter[str]] = {
            name: Counter() for name in EXPECTED_COLUMNS
        }
        self.postcode_counts: Counter[str] = Counter()
        self.native_pair_counts: dict[str, Counter[str]] = {
            f"{left}__{right}": Counter() for left, right in NATIVE_PAIRS
        }
        self.native_character_counts: dict[str, Counter[str]] = {
            name: Counter() for pair in NATIVE_PAIRS for name in pair
        }
        self.categorical_counts = {
            name: SafeCategoryCounter(
                max_distinct=config.categorical_max_distinct,
                max_value_chars=config.categorical_max_value_chars,
            )
            for name in RAW_CATEGORICAL_FIELDS
        }

    def observe(
        self, row: list[str], logical_record_number: int
    ) -> list[tuple[str, str]]:
        values = dict(zip(EXPECTED_COLUMNS, row, strict=True))
        triggered_safeguards: list[tuple[str, str]] = []

        for profile, value in zip(self.field_profiles, row, strict=True):
            profile.records_eligible_for_profile += 1
            length = len(value)
            if value == "":
                profile.empty_count += 1
            else:
                profile.nonempty_count += 1
                if value.strip() == "":
                    profile.whitespace_only_count += 1
            if length > profile.max_length_chars:
                profile.max_length_chars = length
                profile.max_length_logical_record_number = logical_record_number
            if "\n" in value or "\r" in value:
                profile.contains_newline_count += 1
            if length > self.config.field_warning_chars:
                profile.oversized_field_count += 1
            if value in self.placeholders:
                profile.exact_placeholder_candidate_count += 1
                self.placeholder_counts[profile.column_name][value] += 1

        postcode = values["postcode"]
        self.postcode_counts[
            postcode_lexical_category(postcode, self.placeholders)
        ] += 1

        for non_native_name, native_name in NATIVE_PAIRS:
            pair_name = f"{non_native_name}__{native_name}"
            self.native_pair_counts[pair_name][
                native_pair_state(values[non_native_name], values[native_name])
            ] += 1
            self.native_character_counts[non_native_name][
                character_class(values[non_native_name])
            ] += 1
            self.native_character_counts[native_name][
                character_class(values[native_name])
            ] += 1

        for name, counter in self.categorical_counts.items():
            if counter.add(values[name]):
                triggered_safeguards.append((name, counter.suppression_reason))
        return triggered_safeguards

    def value_rows(self) -> list[ValueProfileRow]:
        rows: list[ValueProfileRow] = []
        denominator = self.field_profiles[0].records_eligible_for_profile

        for name, counts in self.placeholder_counts.items():
            for category, count in sorted(counts.items()):
                rows.append(
                    ValueProfileRow(
                        name, "PLACEHOLDER_EXACT", category, count, denominator
                    )
                )
        for category, count in sorted(self.postcode_counts.items()):
            rows.append(
                ValueProfileRow(
                    "postcode", "POSTCODE_LEXICAL_PATTERN", category, count, denominator
                )
            )
        for name, counts in self.native_pair_counts.items():
            for category, count in sorted(counts.items()):
                rows.append(
                    ValueProfileRow(
                        name, "NATIVE_PAIR_STATE", category, count, denominator
                    )
                )
        for name, counts in self.native_character_counts.items():
            for category, count in sorted(counts.items()):
                rows.append(
                    ValueProfileRow(
                        name, "NATIVE_SCRIPT_DIAGNOSTIC", category, count, denominator
                    )
                )
        for name, counter in self.categorical_counts.items():
            family = {
                "country_iso_code": "COUNTRY_CODE_VALUE",
                "batch_priority": "BATCH_PRIORITY_VALUE",
                "location_information": "LOCATION_INFORMATION_VALUE",
            }[name]
            if counter.suppressed:
                rows.append(
                    ValueProfileRow(
                        name,
                        family,
                        "__SUPPRESSED_BY_CARDINALITY_SAFEGUARD__",
                        counter.total_nonempty,
                        denominator,
                    )
                )
            else:
                for category, count in sorted(counter.counts.items()):
                    rows.append(
                        ValueProfileRow(name, family, category, count, denominator)
                    )
        return rows
