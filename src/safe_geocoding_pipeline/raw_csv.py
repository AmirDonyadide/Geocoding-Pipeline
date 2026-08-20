from __future__ import annotations

import csv
import hashlib
from contextlib import contextmanager
from typing import IO, Iterator, Protocol, Sequence, cast

SOURCE_COLUMNS = (
    "id",
    "street_address_line_1",
    "street_address_line_2",
    "street_address_line_3",
    "street_address_line_4",
    "street_address_line_1_native",
    "street_address_line_2_native",
    "street_address_line_3_native",
    "street_address_line_4_native",
    "postcode",
    "city",
    "region_in_country",
    "country_iso_code",
    "batch_priority",
    "location_information",
)

SOURCE_ENCODING_POLICY = "strict UTF-8 with optional UTF-8 BOM"
SOURCE_TEXT_ENCODING = "utf-8"
SOURCE_TEXT_ENCODING_WITH_BOM = "utf-8-sig"
SOURCE_TEXT_ERRORS = "strict"
UTF8_BOM_BYTES = b"\xef\xbb\xbf"
SOURCE_SCHEMA_FINGERPRINT_VERSION = "sha256_utf8_unit_separator_v1"
SOURCE_SCHEMA_FINGERPRINT_SEPARATOR = "\x1f"
CSV_NEWLINE = ""
CSV_DELIMITER = ","
CSV_QUOTE_CHARACTER = '"'
CSV_DOUBLEQUOTE = True
CSV_ESCAPE_CHARACTER: None = None
CSV_SKIP_INITIAL_SPACE = False
CSV_STRICT = True


def source_schema_fingerprint(columns: Sequence[str]) -> str:
    """Return the authoritative Phase 1 ordered-schema fingerprint."""
    payload = SOURCE_SCHEMA_FINGERPRINT_SEPARATOR.join(columns).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class StrictCsvReader(Protocol, Iterator[list[str]]):
    line_num: int


def strict_csv_reader(stream: IO[str]) -> StrictCsvReader:
    """Return the single approved logical CSV interpretation."""
    return cast(
        StrictCsvReader,
        csv.reader(
            stream,
            delimiter=CSV_DELIMITER,
            quotechar=CSV_QUOTE_CHARACTER,
            doublequote=CSV_DOUBLEQUOTE,
            escapechar=CSV_ESCAPE_CHARACTER,
            skipinitialspace=CSV_SKIP_INITIAL_SPACE,
            strict=CSV_STRICT,
        ),
    )


@contextmanager
def csv_field_limit(limit_chars: int) -> Iterator[None]:
    """Temporarily apply the approved parser safety ceiling."""
    previous = csv.field_size_limit()
    csv.field_size_limit(limit_chars)
    try:
        yield
    finally:
        csv.field_size_limit(previous)
