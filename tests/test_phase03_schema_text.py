from __future__ import annotations

import unicodedata

import pytest

from safe_geocoding_pipeline.phase03.constants import CORE_COLUMNS, EVIDENCE_COLUMNS
from safe_geocoding_pipeline.phase03.errors import Phase03Error
from safe_geocoding_pipeline.phase03.schema import core_schema, evidence_schema
from safe_geocoding_pipeline.phase03.text import (
    classify_placeholder,
    enforce_runtime_contract,
    normalize_derived_text,
    tokenize_with_spans,
)


def test_phase03_schemas_are_exact() -> None:
    core = core_schema()
    evidence = evidence_schema()
    assert core.names == list(CORE_COLUMNS)
    assert evidence.names == list(EVIDENCE_COLUMNS)
    assert len(core) == 52
    assert len(evidence) == 20
    assert core.field("street_clean").nullable
    assert not core.field("address_conflict_flags").nullable
    assert not core.field("selected_component_provenance").nullable
    assert evidence.field("candidate_value").nullable
    assert not evidence.field("stable_source_row_id_v1").nullable


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", "SEMANTIC_MISSING"),
        (".", "SEMANTIC_MISSING"),
        ("-", "SEMANTIC_MISSING"),
        ("Na", "AMBIGUOUS_PLACEHOLDER_LIKE"),
        ("Nan", "AMBIGUOUS_PLACEHOLDER_LIKE"),
        ("Null", "AMBIGUOUS_PLACEHOLDER_LIKE"),
        ("NA", "CONTENT"),
        ("null", "CONTENT"),
        (" Null ", "CONTENT"),
    ],
)
def test_placeholder_policy_is_exact_and_case_sensitive(
    value: str, expected: str
) -> None:
    assert classify_placeholder(value) == expected


def test_derived_normalization_order_without_raw_mutation() -> None:
    raw = " \tCafe\u0301\n\u2028  North\x00Wing  "
    assert normalize_derived_text(raw) == "Café North Wing"
    assert raw == " \tCafe\u0301\n\u2028  North\x00Wing  "
    assert normalize_derived_text("\t\n") is None
    assert unicodedata.normalize("NFKC", "①") != normalize_derived_text("①")


def test_runtime_contract_fails_closed() -> None:
    enforce_runtime_contract(observed_python=(3, 14, 3), observed_unicode="16.0.0")
    with pytest.raises(Phase03Error, match="PYTHON_RUNTIME_MISMATCH"):
        enforce_runtime_contract(observed_python=(3, 13, 9), observed_unicode="16.0.0")
    with pytest.raises(Phase03Error, match="UNICODE_RUNTIME_MISMATCH"):
        enforce_runtime_contract(observed_python=(3, 14, 3), observed_unicode="15.1.0")


def test_tokenizer_preserves_raw_codepoint_spans() -> None:
    raw = "  Apt.  7B\nCafé"
    tokens = tokenize_with_spans(raw)
    assert [token.raw for token in tokens] == ["Apt", ".", "7B", "Café"]
    assert [raw[token.start : token.end] for token in tokens] == [
        token.raw for token in tokens
    ]
