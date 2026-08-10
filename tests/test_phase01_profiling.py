from __future__ import annotations

import pytest

from safe_geocoding_pipeline.phase01.profiling import (
    SafeCategoryCounter,
    character_class,
    native_pair_state,
    postcode_lexical_category,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", "EMPTY"),
        ("Null", "EXACT_PLACEHOLDER_CANDIDATE"),
        ("01234", "DIGITS_LEADING_ZERO"),
        ("12345", "DIGITS_ONLY"),
        ("SW1A2AA", "ALPHANUMERIC"),
        ("ABC", "ALPHABETIC_ONLY"),
        ("12 345", "CONTAINS_WHITESPACE"),
        ("12-345", "CONTAINS_HYPHEN"),
        ("123.0", "DECIMAL_LOOKING"),
        ("١٢٣", "DIGITS_ONLY"),
    ],
)
def test_postcode_lexical_categories(value: str, expected: str) -> None:
    assert postcode_lexical_category(value, {".", "-", "Na", "Nan", "Null"}) == expected


@pytest.mark.parametrize(
    ("non_native", "native", "expected"),
    [
        ("", "", "BOTH_EMPTY"),
        ("", "住所", "NATIVE_ONLY"),
        ("Address", "", "NON_NATIVE_ONLY"),
        ("Same", "Same", "EXACT_EQUAL"),
        ("Address", "住所", "DIFFERENT"),
    ],
)
def test_native_pair_states(non_native: str, native: str, expected: str) -> None:
    assert native_pair_state(non_native, native) == expected


def test_character_diagnostics_are_simple() -> None:
    assert character_class("") == "EMPTY"
    assert character_class("ASCII") == "ASCII_ONLY"
    assert character_class("Straße") == "CONTAINS_NON_ASCII"


def test_categorical_counter_discards_raw_values_after_cardinality_limit() -> None:
    counter = SafeCategoryCounter(max_distinct=2, max_value_chars=10)
    assert counter.add("a") is False
    assert counter.add("b") is False
    assert counter.add("c") is True
    assert counter.suppressed is True
    assert counter.suppression_reason == "CARDINALITY_LIMIT_EXCEEDED"
    assert counter.counts == {}


def test_categorical_counter_discards_raw_values_after_length_limit() -> None:
    counter = SafeCategoryCounter(max_distinct=10, max_value_chars=2)
    counter.add("ok")
    assert counter.add("long") is True
    assert counter.suppressed is True
    assert counter.counts == {}


def test_categorical_counter_suppresses_spreadsheet_formulas() -> None:
    counter = SafeCategoryCounter(max_distinct=10, max_value_chars=100)
    assert counter.add("=HYPERLINK(\"https://invalid.example\")") is True
    assert counter.suppression_reason == "UNSAFE_SPREADSHEET_VALUE"
    assert counter.counts == {}
