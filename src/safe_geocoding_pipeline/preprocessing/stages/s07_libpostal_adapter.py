"""Strict, order-preserving adapter around the pinned pypostal parser call."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import NoReturn, Protocol


PARSED_NONEMPTY = "PARSED_NONEMPTY"
PARSED_EMPTY = "PARSED_EMPTY"


class Stage07ParserError(RuntimeError):
    """Privacy-safe parser or wrapper-contract failure."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class LibpostalComponent:
    label: str
    value: str


@dataclass(frozen=True, slots=True)
class ParsedAddress:
    status: str
    components: tuple[LibpostalComponent, ...]


class AddressParser(Protocol):
    initialization_seconds: float

    def parse(self, candidate: str) -> ParsedAddress: ...


ParserCallable = Callable[[str], object]


def _fail(code: str, detail: str) -> NoReturn:
    raise Stage07ParserError(code, detail)


def _strict_utf8_round_trip(value: str) -> bool:
    try:
        return (
            value.encode("utf-8", errors="strict").decode("utf-8", errors="strict")
            == value
        )
    except UnicodeError:
        return False


class PypostalParser:
    """Initialize once and preserve every ordered pypostal result tuple."""

    def __init__(self, parse_callable: ParserCallable | None = None) -> None:
        started = time.perf_counter()
        if parse_callable is None:
            try:
                from postal.parser import parse_address
            except Exception as error:
                raise Stage07ParserError(
                    "PARSER_INITIALIZATION_FAILURE",
                    "The pinned pypostal parser could not be initialized",
                ) from error
            self._parse_callable: ParserCallable = parse_address
        else:
            self._parse_callable = parse_callable
        self.initialization_seconds = time.perf_counter() - started

    def parse(self, candidate: str) -> ParsedAddress:
        if not isinstance(candidate, str):
            _fail("PARSER_INPUT_INVALID", "Parser input must be an exact string")
        if not _strict_utf8_round_trip(candidate):
            _fail("PARSER_INPUT_INVALID", "Parser input is not exact valid UTF-8")
        try:
            raw = self._parse_callable(candidate)
        except Exception as error:
            raise Stage07ParserError(
                "PARSER_EXCEPTION", "The pinned parser raised an exception"
            ) from error
        if not isinstance(raw, list):
            _fail(
                "PARSER_RESULT_MALFORMED",
                "Pypostal result must be an ordered list",
            )
        components: list[LibpostalComponent] = []
        for item in raw:
            if not isinstance(item, tuple) or len(item) != 2:
                _fail(
                    "PARSER_RESULT_MALFORMED",
                    "Every pypostal item must be an exact value/label tuple",
                )
            value, label = item
            if (
                not isinstance(value, str)
                or not isinstance(label, str)
                or not _strict_utf8_round_trip(value)
                or not _strict_utf8_round_trip(label)
            ):
                _fail(
                    "PARSER_RESULT_MALFORMED",
                    "Parser labels and values must be non-null exact UTF-8 strings",
                )
            components.append(LibpostalComponent(label=label, value=value))
        frozen = tuple(components)
        return ParsedAddress(
            status=PARSED_NONEMPTY if frozen else PARSED_EMPTY,
            components=frozen,
        )


def ordered_parse_sha256(result: ParsedAddress) -> str:
    """Return a transient exact ordered-result digest for equality checks."""
    digest = hashlib.sha256(b"SAFE_STAGE07_ORDERED_LIBPOSTAL_PARSE_V1")
    status = result.status.encode("utf-8")
    digest.update(len(status).to_bytes(8, "big"))
    digest.update(status)
    digest.update(len(result.components).to_bytes(8, "big"))
    for component in result.components:
        for value in (component.label, component.value):
            encoded = value.encode("utf-8", errors="strict")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
    return digest.hexdigest()


__all__ = [
    "AddressParser",
    "LibpostalComponent",
    "PARSED_EMPTY",
    "PARSED_NONEMPTY",
    "ParsedAddress",
    "PypostalParser",
    "Stage07ParserError",
    "ordered_parse_sha256",
]
