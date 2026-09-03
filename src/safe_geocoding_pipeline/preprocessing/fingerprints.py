from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TypeAlias

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


def canonical_json_bytes(value: JsonValue) -> bytes:
    """Serialize fingerprint inputs without relying on repr or insertion order."""
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def fingerprint(value: JsonValue) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def source_tree_fingerprint(paths: Sequence[Path]) -> str:
    digest = hashlib.sha256()
    files: list[tuple[str, Path]] = []
    for root in paths:
        if root.is_file():
            files.append((root.name, root))
        elif root.is_dir():
            files.extend(
                (path.relative_to(root).as_posix(), path)
                for path in root.rglob("*.py")
                if path.is_file()
            )
    for relative, path in sorted(files):
        encoded = relative.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        data = path.read_bytes()
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def mapping_as_json(value: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    return dict(value)
