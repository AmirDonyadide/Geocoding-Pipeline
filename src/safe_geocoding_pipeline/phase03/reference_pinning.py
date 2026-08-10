from __future__ import annotations

import json
from html.parser import HTMLParser

from .errors import Phase03Error

_UN_M49_HEADER = (
    "Global Code",
    "Global Name",
    "Region Code",
    "Region Name",
    "Sub-region Code",
    "Sub-region Name",
    "Intermediate Region Code",
    "Intermediate Region Name",
    "Country or Area",
    "M49 Code",
    "ISO-alpha2 Code",
    "ISO-alpha3 Code",
    "Least Developed Countries (LDC)",
    "Land Locked Developing Countries (LLDC)",
    "Small Island Developing States (SIDS)",
)


class _UnM49EnglishTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_target = False
        self.in_row = False
        self.in_cell = False
        self.target_seen = False
        self.cell_parts: list[str] = []
        self.row: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "table" and attributes.get("id") == "downloadTableEN":
            if self.target_seen:
                raise Phase03Error("UN_M49_SOURCE_DUPLICATE_TARGET_TABLE")
            self.target_seen = True
            self.in_target = True
            return
        if not self.in_target:
            return
        if tag == "tr":
            self.in_row = True
            self.row = []
        elif tag in {"td", "th"} and self.in_row:
            self.in_cell = True
            self.cell_parts = []

    def handle_endtag(self, tag: str) -> None:
        if not self.in_target:
            return
        if tag in {"td", "th"} and self.in_cell:
            self.row.append("".join(self.cell_parts).strip())
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if self.row:
                self.rows.append(self.row)
            self.in_row = False
        elif tag == "table":
            self.in_target = False

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.cell_parts.append(data)


def extract_un_m49_country_area_json(source_html: bytes) -> bytes:
    try:
        text = source_html.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise Phase03Error("UN_M49_SOURCE_UTF8_INVALID") from error
    parser = _UnM49EnglishTableParser()
    try:
        parser.feed(text)
        parser.close()
    except Phase03Error:
        raise
    except Exception as error:
        raise Phase03Error(
            "UN_M49_SOURCE_HTML_INVALID", type(error).__name__
        ) from error
    if not parser.target_seen or not parser.rows:
        raise Phase03Error("UN_M49_SOURCE_TABLE_MISSING")
    header, *rows = parser.rows
    if tuple(header) != _UN_M49_HEADER:
        raise Phase03Error("UN_M49_SOURCE_SCHEMA_MISMATCH")
    output: list[dict[str, str]] = []
    for row in rows:
        if len(row) != len(_UN_M49_HEADER):
            raise Phase03Error("UN_M49_SOURCE_WRONG_COLUMN_COUNT")
        output.append(
            {
                "country_or_area_name": row[8],
                "m49_code": row[9],
                "iso_alpha2": row[10],
                "iso_alpha3": row[11],
            }
        )
    return (
        json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
