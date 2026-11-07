"""AP-only bounded canonical encoding and fixed timing representations.

No output-sized Unicode string or oversized candidate is constructed. Native
allocator/encoder/decoder overhead remains a separate runtime-bound obligation.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

import struct
import re


UINT64 = 2**64 - 1
PACKED_ROW_BYTES = 512
ENVELOPE_BYTES = 4096
_ESCAPE = re.compile(r'[\x00-\x1f\x7f"\\]')


class EncodingLimit(ValueError):
    """Static limit failure, without caller text."""


class Canonical:
    """A fixed byte arena, or a count-only pass with the same byte grammar."""

    def __init__(
        self, limit: Any, *, count_only: Any = False, compare: Any = None
    ) -> None:
        if type(limit) is not int or not 0 <= limit <= 65536:
            raise EncodingLimit("AP_ENCODING_LIMIT")
        self.limit, self.pos = limit, 0
        self.buffer = None if count_only or compare is not None else bytearray(limit)
        self.expected = None if compare is None else memoryview(compare)

    def put(self, raw: Any) -> Any:
        end = self.pos + len(raw)
        if end > self.limit:
            raise EncodingLimit("AP_ENCODING_LIMIT")
        if self.expected is not None and self.expected[self.pos : end] != raw:
            raise EncodingLimit("AP_ENCODING_CANONICAL")
        if self.buffer is not None:
            self.buffer[self.pos : end] = raw
        self.pos = end

    def string(self, value: Any) -> Any:
        if type(value) is not str or len(value) > 32768:
            raise EncodingLimit("AP_ENCODING_VALUE")
        if value.isascii() and _ESCAPE.search(value) is None:
            if self.pos + len(value) + 2 > self.limit:
                raise EncodingLimit("AP_ENCODING_LIMIT")
            self.put(b'"')
            if self.buffer is None and self.expected is None:
                self.pos += len(value)
            else:
                for start in range(0, len(value), 256):
                    self.put(value[start : start + 256].encode("ascii"))
            self.put(b'"')
            return
        self.put(b'"')
        for char in value:
            n = ord(char)
            if char in ('"', "\\"):
                self.put(b"\\" + char.encode("ascii"))
            elif char in "\b\f\n\r\t":
                self.put(
                    {
                        "\b": b"\\b",
                        "\f": b"\\f",
                        "\n": b"\\n",
                        "\r": b"\\r",
                        "\t": b"\\t",
                    }[char]
                )
            elif 32 <= n < 127:
                self.put(bytes((n,)))
            elif n <= 65535:
                self.put(("\\u%04x" % n).encode("ascii"))
            else:
                n -= 65536
                self.put(
                    ("\\u%04x\\u%04x" % (55296 + (n >> 10), 56320 + (n & 1023))).encode(
                        "ascii"
                    )
                )
        self.put(b'"')

    def value(self, value: Any, depth: Any = 0) -> Any:
        if depth > 16:
            raise EncodingLimit("AP_ENCODING_DEPTH")
        if value is None:
            self.put(b"null")
        elif type(value) is bool:
            self.put(b"true" if value else b"false")
        elif type(value) is int and -UINT64 <= value <= UINT64:
            self.put(str(value).encode("ascii"))
        elif type(value) is str:
            self.string(value)
        elif type(value) in (list, tuple):
            if len(value) > 128:
                raise EncodingLimit("AP_ENCODING_ITEMS")
            self.put(b"[")
            for i, item in enumerate(value):
                if i:
                    self.put(b",")
                self.value(item, depth + 1)
            self.put(b"]")
        elif type(value) is dict:
            if len(value) > 64 or any(type(k) is not str for k in value):
                raise EncodingLimit("AP_ENCODING_KEYS")
            self.put(b"{")
            for i, key in enumerate(sorted(value)):
                if i:
                    self.put(b",")
                self.string(key)
                self.put(b":")
                self.value(value[key], depth + 1)
            self.put(b"}")
        else:
            raise EncodingLimit("AP_ENCODING_VALUE")

    def view(self) -> Any:
        assert self.buffer is not None
        return memoryview(self.buffer)[: self.pos].toreadonly()


def canonical(value: Any, limit: Any) -> Any:
    writer = Canonical(limit)
    writer.value(value)
    writer.put(b"\n")
    return writer.view()


def canonical_match(value: Any, raw: Any) -> None:
    """Compare exact canonical bytes without a second full-size output arena."""
    writer = Canonical(len(raw), compare=raw)
    writer.value(value)
    writer.put(b"\n")
    if writer.pos != len(raw):
        raise EncodingLimit("AP_ENCODING_CANONICAL")


def envelope(payload: Any, *, count_only: Any = False) -> Any:
    """Canonical object with exactly one hole, occupied by an array document."""
    out = Canonical(ENVELOPE_BYTES, count_only=count_only)
    split = None
    out.put(b"{")
    for i, key in enumerate(sorted(payload)):
        if i:
            out.put(b",")
        out.string(key)
        out.put(b":")
        if key == "records":
            split = out.pos
        else:
            out.value(payload[key])
    if split is None:
        raise EncodingLimit("AP_ENCODING_HOLE")
    out.put(b"}\n")
    return out, split


class Document:
    """At most32KiB records plus4KiB envelope, no combined-byte copy."""

    def __init__(self, payload: Any, records: Any) -> None:
        head, split = envelope(payload)
        view = head.view()
        self.parts = (view[:split], records.view(), view[split:])

    def __len__(self) -> int:
        return sum(map(len, self.parts))

    def digest(self) -> Any:
        import hashlib

        out = hashlib.sha256()
        for part in self.parts:
            out.update(part)
        return out.hexdigest()


def _number_fields() -> Any:
    from .s12_public_sampling_contract import ASYNC_FIELDS

    return tuple(
        k for k, spec in ASYNC_FIELDS.items() if spec in ("P", "ID", "ID?", "U", "U?")
    )


NUMBERS = _number_fields()
HASHES = ("epoch_id", "observation_sha256", "sample_event_sha256", "ack_event_sha256")
OUTCOMES = ("COMPLETE", "FAILED", "CANCELLED", "UNCERTAIN")


def pack_timing(row: Any) -> Any:
    from .s12_public_sampling_contract import validate_timing

    validator: Callable[[Any], None] = validate_timing
    validator(row)
    out = bytearray(PACKED_ROW_BYTES)
    numbers: Iterable[Any]
    if row["row_kind"] == "HARD_SYNC":
        values = row["legacy_row"]
        out[0], out[1] = 1, OUTCOMES.index(values[2])
        numbers = (values[0], *values[3:])
    else:
        out[1] = OUTCOMES.index(row["outcome"])
        out[2] = ("REGULAR", "FINAL").index(row["role"])
        out[3] = row["future_used"]
        numbers = (row[k] for k in NUMBERS)
    mask = 0
    for i, n in enumerate(numbers):
        if n is None:
            mask |= 1 << i
        else:
            struct.pack_into("<Q", out, 16 + 8 * i, n)
    if not out[0]:
        offset = 16 + 8 * len(NUMBERS)
        for i, key in enumerate(HASHES):
            value = row[key]
            size = 32
            if value is None:
                mask |= 1 << (32 + i)
            else:
                out[offset : offset + size] = bytes.fromhex(value)
            offset += size
        assert offset <= PACKED_ROW_BYTES
    struct.pack_into("<Q", out, 8, mask)
    return bytes(out)


def unpack_timing(raw: Any) -> Any:
    mask = struct.unpack_from("<Q", raw, 8)[0]

    def number(i: Any) -> Any:
        return None if mask & (1 << i) else struct.unpack_from("<Q", raw, 16 + 8 * i)[0]

    if raw[0]:
        return dict(
            row_kind="HARD_SYNC",
            legacy_row=[
                number(0),
                "START_RESERVE",
                OUTCOMES[raw[1]],
                *(number(i) for i in range(1, 25)),
            ],
        )
    row: dict[str, Any] = dict(
        row_kind="PERIODIC_ASYNC",
        outcome=OUTCOMES[raw[1]],
        role=("REGULAR", "FINAL")[raw[2]],
        future_used=bool(raw[3]),
    )
    for i, key in enumerate(NUMBERS):
        row[key] = number(i)
    offset = 16 + 8 * len(NUMBERS)
    for i, key in enumerate(HASHES):
        size = 32
        row[key] = None if mask & (1 << (32 + i)) else raw[offset : offset + size].hex()
        offset += size
    return row


class TimingRing:
    """Fixed backing; only one selected immutable512-byte row is copied out."""

    def __init__(self, size: Any) -> None:
        self.maxlen: int = size
        self.backing = bytearray(size * PACKED_ROW_BYTES)
        self.last = 0

    def __len__(self) -> int:
        return min(self.last, self.maxlen)

    def append(self, pair: Any) -> Any:
        ordinal, raw = pair
        if ordinal != self.last + 1 or len(raw) != PACKED_ROW_BYTES:
            raise EncodingLimit("AP_RING_ORDER")
        offset = ((ordinal - 1) % self.maxlen) * PACKED_ROW_BYTES
        self.backing[offset : offset + PACKED_ROW_BYTES] = raw
        self.last = ordinal

    def get(self, ordinal: Any) -> Any:
        if not self.last - len(self) < ordinal <= self.last:
            return None
        offset = ((ordinal - 1) % self.maxlen) * PACKED_ROW_BYTES
        return bytes(memoryview(self.backing)[offset : offset + PACKED_ROW_BYTES])
