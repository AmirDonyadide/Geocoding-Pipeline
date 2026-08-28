from __future__ import annotations

import pytest

from safe_geocoding_pipeline.preprocessing.stages.s07_libpostal_adapter import (
    LibpostalComponent,
    PARSED_EMPTY,
    PARSED_NONEMPTY,
    PypostalParser,
    Stage07ParserError,
    ordered_parse_sha256,
)


def test_adapter_preserves_order_duplicates_labels_and_values() -> None:
    raw = [
        ("10", "house_number"),
        ("example", "road"),
        ("street", "road"),
        ("example", "road"),
    ]
    parser = PypostalParser(lambda candidate: raw)
    result = parser.parse("10 example street")

    assert result.status == PARSED_NONEMPTY
    assert result.components == (
        LibpostalComponent(label="house_number", value="10"),
        LibpostalComponent(label="road", value="example"),
        LibpostalComponent(label="road", value="street"),
        LibpostalComponent(label="road", value="example"),
    )


def test_adapter_preserves_exact_unicode_and_empty_result() -> None:
    parser = PypostalParser(lambda candidate: [("أ مثال", "road"), ("é", "house")])
    result = parser.parse("synthetic")
    assert result.components[0].value == "أ مثال"
    assert result.components[1].value == "é"

    empty = PypostalParser(lambda candidate: []).parse("")
    assert empty.status == PARSED_EMPTY
    assert empty.components == ()


@pytest.mark.parametrize(
    "raw",
    [
        None,
        (),
        {},
        [["value", "label"]],
        [("only-one",)],
        [("one", "two", "three")],
        [(None, "road")],
        [("value", None)],
        [(b"value", "road")],
        [("value", b"road")],
    ],
)
def test_adapter_rejects_malformed_wrapper_results(raw: object) -> None:
    with pytest.raises(Stage07ParserError, match="PARSER_RESULT_MALFORMED"):
        PypostalParser(lambda candidate: raw).parse("synthetic")


def test_adapter_wraps_parser_exception_without_value() -> None:
    def fail(candidate: str) -> object:
        raise ValueError(f"must not escape: {candidate}")

    with pytest.raises(Stage07ParserError) as caught:
        PypostalParser(fail).parse("Fictional Protected-Looking Value")
    assert caught.value.code == "PARSER_EXCEPTION"
    assert "Fictional Protected-Looking Value" not in str(caught.value)


def test_ordered_parse_digest_is_order_value_and_label_sensitive() -> None:
    parser = PypostalParser(
        lambda candidate: [("10", "house_number"), ("example road", "road")]
    )
    original = parser.parse("synthetic")
    reordered = PypostalParser(
        lambda candidate: [("example road", "road"), ("10", "house_number")]
    ).parse("synthetic")
    changed_label = PypostalParser(
        lambda candidate: [("10", "road"), ("example road", "road")]
    ).parse("synthetic")
    changed_value = PypostalParser(
        lambda candidate: [("11", "house_number"), ("example road", "road")]
    ).parse("synthetic")

    digests = {
        ordered_parse_sha256(result)
        for result in (original, reordered, changed_label, changed_value)
    }
    assert len(digests) == 4


def test_adapter_does_not_accept_dict_semantics() -> None:
    with pytest.raises(Stage07ParserError, match="PARSER_RESULT_MALFORMED"):
        PypostalParser(
            lambda candidate: {"house_number": "10", "road": "example"}
        ).parse("synthetic")
