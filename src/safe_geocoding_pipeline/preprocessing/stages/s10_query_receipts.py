"""Atomic, immutable receipts in an exclusively owned private attempt directory."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from . import s09_reference_io as base
from . import s09_reference_pack as pack
from . import s10_query_contract as c
from . import s10_query_io as io


def write(path: Path, record: Any) -> None:
    # Single writer, new immutable name. This is operational evidence, not the
    # cross-attempt reservation/registration/_COMMITTED publication protocol.
    pack.regular_private(path.parent, directory=True)
    c.require(not os.path.lexists(path), "STAGE10_RECEIPT_ALREADY_EXISTS")
    partial = path.with_name(path.name + ".partial")
    io.write_json(partial, record)
    os.rename(partial, path)
    base.fsync_directory(path.parent)
