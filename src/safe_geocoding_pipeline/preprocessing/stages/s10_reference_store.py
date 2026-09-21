"""Private immutable, disk-indexed reference material; no per-witness SQL.

One restricted set-based closure and four ordered streams prepare the exact
canonical bytes. The fixed-width index is mapped read-only; payloads are read
one record at a time. Neither this cache nor its partitioning enters science.
"""

from __future__ import annotations

import mmap
import os
import struct
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pyarrow as pa

from . import s09_reference_contract as s9
from . import s09_reference_pack as pack
from . import s10_query_contract as c
from . import s10_query_io as io


def decode(payload: bytes, schema: Any) -> dict[str, Any]:
    """Inverse of the frozen typed framing, with closed-schema reconstruction."""
    position = 0

    def take(size: int) -> bytes:
        nonlocal position
        c.require(0 <= size <= len(payload) - position, "STAGE10_REFERENCE_CACHE_FRAME")
        value = payload[position : position + size]
        position += size
        return value

    def number() -> int:
        return int.from_bytes(take(8), "big")

    def value(depth: int = 0) -> Any:
        c.require(depth < 32, "STAGE10_REFERENCE_CACHE_DEPTH")
        kind = take(1)
        if kind == b"\x00":
            return None
        if kind == b"\x04":
            boolean = take(1)
            c.require(boolean in (b"\x00", b"\x01"), "STAGE10_REFERENCE_CACHE_FRAME")
            return boolean == b"\x01"
        if kind == b"\x03":
            return number()
        if kind in (b"\x01", b"\x02"):
            raw = take(number())
            return raw.decode("utf-8") if kind == b"\x01" else raw
        c.require(kind == b"\x05", "STAGE10_REFERENCE_CACHE_FRAME")
        count = number()
        c.require(count <= len(payload) - position, "STAGE10_REFERENCE_CACHE_FRAME")
        return tuple(value(depth + 1) for _ in range(count))

    def restore(values: Sequence[Any], fields: Any) -> dict[str, Any]:
        c.require(len(values) == len(fields), "STAGE10_REFERENCE_CACHE_SCHEMA")
        return {f.name: typed(v, f.type) for f, v in zip(fields, values, strict=True)}

    def typed(v: Any, kind: Any) -> Any:
        if v is None:
            return None
        if pa.types.is_struct(kind):
            return restore(v, kind)
        if pa.types.is_list(kind) or pa.types.is_large_list(kind):
            return [typed(item, kind.value_type) for item in v]
        return v

    c.require(number() == len(schema), "STAGE10_REFERENCE_CACHE_SCHEMA")
    result = restore(tuple(value() for _ in schema), schema)
    c.require(position == len(payload), "STAGE10_REFERENCE_CACHE_FRAME")
    return result


class Lookup:
    def __init__(self, root: Path, key_bytes: int, schema: Any) -> None:
        self.schema, self.key_bytes = schema, key_bytes
        self.width = key_bytes + 16
        for name in ("index", "payload"):
            pack.regular_private(root / name)
        self.index_file = (root / "index").open("rb")
        self.data = (root / "payload").open("rb")
        size = os.fstat(self.index_file.fileno()).st_size
        c.require(size % self.width == 0, "STAGE10_REFERENCE_CACHE_INDEX")
        self.count = size // self.width
        self.index = (
            mmap.mmap(self.index_file.fileno(), 0, access=mmap.ACCESS_READ)
            if size
            else None
        )
        self.data_size = os.fstat(self.data.fileno()).st_size

    def lower(self, key: bytes) -> int:
        lo, hi = 0, self.count
        while lo < hi:
            middle = (lo + hi) // 2
            if self.key(middle) < key:
                lo = middle + 1
            else:
                hi = middle
        return lo

    def key(self, ordinal: int) -> bytes:
        c.require(0 <= ordinal < self.count, "STAGE10_REFERENCE_CACHE_INDEX")
        assert self.index is not None
        start = ordinal * self.width
        return self.index[start : start + self.key_bytes]

    def material(self, ordinal: int) -> tuple[Mapping[str, Any], bytes]:
        self.key(ordinal)
        assert self.index is not None
        start = ordinal * self.width + self.key_bytes
        offset, size = struct.unpack(">QQ", self.index[start : start + 16])
        c.require(offset + size <= self.data_size, "STAGE10_REFERENCE_CACHE_INDEX")
        payload = os.pread(self.data.fileno(), size, offset)
        c.require(len(payload) == size, "STAGE10_REFERENCE_CACHE_TRUNCATED")
        return decode(payload, self.schema), payload

    def get(self, key: bytes) -> tuple[Mapping[str, Any], bytes]:
        ordinal = self.lower(key)
        c.require(
            ordinal < self.count and self.key(ordinal) == key,
            "STAGE10_EXACT_KEY_CARDINALITY_INVALID",
        )
        return self.material(ordinal)

    def members(self, identifier: bytes) -> Iterator[tuple[Mapping[str, Any], bytes]]:
        ordinal = self.lower(identifier + bytes(8))
        while ordinal < self.count and self.key(ordinal).startswith(identifier):
            yield self.material(ordinal)
            ordinal += 1

    def close(self) -> None:
        if self.index is not None:
            self.index.close()
        self.index_file.close()
        self.data.close()


class ReferenceStore:
    """Complete immutable identities; no source/context eligibility cache."""

    def __init__(self, db: Any, root: Path, progress: Any) -> None:
        self.db, self.root, self.progress = db, root, progress
        self.lookups: dict[str, Lookup] = {}
        self.revision: int | None = None

    def prepare(self) -> None:
        from .s10_query_contexts import encoded, sql_rows

        revision = self.db.reference_revision
        if revision == self.revision:
            return
        self.close()
        root = self.root / f"reference_store_{revision:08}"
        root.mkdir(mode=0o700)
        with self.progress.measure("reference_material_preparation"):
            # Only source-row evidence is consumed by Stage 10. Resolve its
            # direct/pointer objects and transitive parents in one set operation.
            self.db.execute("""CREATE OR REPLACE TABLE stage10_needed_objects AS
WITH RECURSIVE seeds(id) AS (
 SELECT single_witness.reference_object_id FROM stage10_source_reference WHERE single_witness IS NOT NULL
 UNION SELECT p.reference_object_id FROM stage10_source_reference, UNNEST(single_witness.fields) f(p)
 UNION SELECT witness.reference_object_id FROM stage10_members
 UNION SELECT p.reference_object_id FROM stage10_members, UNNEST(witness.fields) f(p)
), closure(id) AS (
 SELECT id FROM seeds WHERE id IS NOT NULL
 UNION SELECT o.explicit_parent_id FROM closure a JOIN stage10_objects o ON a.id=o.reference_object_id WHERE o.explicit_parent_id IS NOT NULL
) SELECT id FROM closure""")
            inventory = []
            for name, relation, keys in (
                ("registry", "reference_registry", ("reference_version_id",)),
                ("capabilities", "reference_capability", ("capability_id",)),
                ("objects", "reference_object", ("reference_object_id",)),
                (
                    "members",
                    "reference_match_member",
                    ("match_set_id", "member_ordinal"),
                ),
            ):
                schema = s9.relation_schema(relation)
                folder = root / name
                folder.mkdir(mode=0o700)
                where = (
                    " WHERE reference_object_id IN (SELECT id FROM stage10_needed_objects)"
                    if name == "objects"
                    else ""
                )
                query = (
                    "SELECT * FROM stage10_"
                    + name
                    + where
                    + " ORDER BY "
                    + ",".join(keys)
                )
                previous: bytes | None = None
                count = offset = 0
                with (
                    (folder / "index").open("xb") as index,
                    (folder / "payload").open("xb") as data,
                ):
                    (folder / "index").chmod(0o600)
                    (folder / "payload").chmod(0o600)
                    for row in sql_rows(self.db, query):
                        key = row[keys[0]]
                        if len(keys) == 2:
                            key += int(row[keys[1]]).to_bytes(8, "big")
                        c.require(
                            previous is None or previous < key,
                            "STAGE10_REFERENCE_CACHE_KEY_COLLISION",
                        )
                        payload = encoded(c.ordered_values(row, schema))
                        data.write(payload)
                        index.write(key + struct.pack(">QQ", offset, len(payload)))
                        offset += len(payload)
                        count += 1
                        previous = key
                    for stream in (index, data):
                        stream.flush()
                        os.fsync(stream.fileno())
                self.progress.counts["reference_" + name + "_encodes"] = (
                    self.progress.counts.get("reference_" + name + "_encodes", 0)
                    + count
                )
                inventory.append(
                    {
                        "name": name,
                        "rows": count,
                        "index_sha256": c.sha256_file(folder / "index"),
                        "payload_sha256": c.sha256_file(folder / "payload"),
                    }
                )
                self.lookups[name] = Lookup(
                    folder, 40 if len(keys) == 2 else 32, schema
                )
            io.write_json(
                root / "_READY.json",
                {
                    "version": "stage10_reference_store_v1",
                    "revision": revision,
                    "files": inventory,
                },
            )
            io.fsync_directory(root)
        self.revision = revision

    def close(self) -> None:
        for lookup in self.lookups.values():
            lookup.close()
        self.lookups.clear()
