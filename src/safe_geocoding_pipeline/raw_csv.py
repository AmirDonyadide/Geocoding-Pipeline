from __future__ import annotations

import csv
from contextlib import contextmanager
from typing import IO, Iterator, Protocol, cast

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
UTF8_BOM_BYTES = b"\xef\xbb\xbf"
CSV_NEWLINE = ""
CSV_DELIMITER = ","
CSV_QUOTE_CHARACTER = '"'
CSV_DOUBLEQUOTE = True
CSV_ESCAPE_CHARACTER: None = None
CSV_SKIP_INITIAL_SPACE = False
CSV_STRICT = True


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
