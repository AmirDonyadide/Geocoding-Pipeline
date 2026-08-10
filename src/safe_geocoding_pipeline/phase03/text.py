from __future__ import annotations

import sys
import unicodedata
from dataclasses import dataclass

from .constants import EXPECTED_PYTHON_VERSION, EXPECTED_UNICODE_VERSION
from .errors import Phase03Error

SEMANTIC_MISSING = frozenset({"", ".", "-"})
AMBIGUOUS_PLACEHOLDERS = frozenset({"Na", "Nan", "Null"})


def enforce_runtime_contract(
    expected_python: tuple[int, int, int] = EXPECTED_PYTHON_VERSION,
    expected_unicode: str = EXPECTED_UNICODE_VERSION,
    *,
    observed_python: tuple[int, int, int] | None = None,
    observed_unicode: str | None = None,
) -> None:
    python_version = observed_python or sys.version_info[:3]
    unicode_version = observed_unicode or unicodedata.unidata_version
    if python_version != expected_python:
        raise Phase03Error(
            "PYTHON_RUNTIME_MISMATCH", "approved Python runtime is required"
        )
    if unicode_version != expected_unicode:
        raise Phase03Error(
            "UNICODE_RUNTIME_MISMATCH", "approved Unicode database is required"
        )


def classify_placeholder(raw_value: str) -> str:
    if raw_value in SEMANTIC_MISSING:
        return "SEMANTIC_MISSING"
    if raw_value in AMBIGUOUS_PLACEHOLDERS:
        return "AMBIGUOUS_PLACEHOLDER_LIKE"
    return "CONTENT"


def _mapped_to_space(character: str) -> bool:
    return unicodedata.category(character) in {"Cc", "Cf", "Zl", "Zp"}


def normalize_derived_text(raw_candidate: str) -> str | None:
    mapped = "".join(
        " " if _mapped_to_space(character) else character for character in raw_candidate
    )
    normalized = unicodedata.normalize("NFC", mapped)
    collapsed = " ".join(normalized.strip().split())
    return collapsed or None


@dataclass(frozen=True, slots=True)
class Token:
    raw: str
    comparison: str
    start: int
    end: int
    kind: str


def tokenize_with_spans(raw_value: str) -> tuple[Token, ...]:
    tokens: list[Token] = []
    index = 0
    while index < len(raw_value):
        character = raw_value[index]
        category = unicodedata.category(character)
        if character.isspace():
            index += 1
            continue
        start = index
        if category[0] in {"L", "M", "N"}:
            index += 1
            while index < len(raw_value) and unicodedata.category(raw_value[index])[
                0
            ] in {"L", "M", "N"}:
                index += 1
            kind = "WORD"
        else:
            index += 1
            kind = "PUNCT"
        raw = raw_value[start:index]
        normalized = unicodedata.normalize("NFC", raw)
        comparison = normalized.lower() if normalized.isascii() else normalized
        tokens.append(Token(raw, comparison, start, index, kind))
    return tuple(tokens)


def representation_for_field(field_name: str) -> str:
    if field_name.endswith("_native"):
        return "NATIVE"
    if field_name in {"postcode", "city", "region_in_country", "country_iso_code"}:
        return "SHARED"
    return "NON_NATIVE"
