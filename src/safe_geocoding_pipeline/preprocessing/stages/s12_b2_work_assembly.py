"""Bounded LP-1 intent -> WorkFile assembly, with no service authority.

The caller's LP-1 gate and write-accounting contexts remain active. The small
verification view below is not a workload plan; a later live preflight must
bind the actual plan, control implementations, permissions and window.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat

from . import s12_b2_contract as b
from . import s12_b2_operations as operations
from . import s12_b2_allocation_limits as limits
from . import s12_storage as io

VERSION = "stage12_local_dispatch_layout_v1"
MAX_ROWS = 150000
MAX_ROW_BYTES = 8192
MAX_CONTROLS = 256
INTENT_KEYS = frozenset(
    ("ordinal", "query_semantic_id", "result_limit", "repetition", "workload_kind")
)


def validate_layout(layout):
    b.require(
        type(layout) is dict
        and set(layout)
        == {
            "version",
            "intent_ordinal",
            "result_limit",
            "repetition",
            "max_output_bytes",
            "controls",
        }
        and layout["version"] == VERSION,
        "LP1_DISPATCH_LAYOUT",
    )
    for key, maximum in (
        ("intent_ordinal", 10),
        ("result_limit", 40),
        ("max_output_bytes", MAX_ROWS * MAX_ROW_BYTES),
    ):
        b.require(
            type(layout[key]) is int and 1 <= layout[key] <= maximum,
            "LP1_DISPATCH_LAYOUT",
        )
    b.validate_type(layout["repetition"], "U")
    controls = layout["controls"]
    b.require(
        type(controls) is list and len(controls) <= MAX_CONTROLS, "LP1_DISPATCH_LAYOUT"
    )
    last = 0
    recipes = {}
    for row in controls:
        b.require(
            type(row) is dict
            and set(row) == {"position", "recipe_id", "recipe_sha256"}
            and type(row["position"]) is int
            and last < row["position"] <= MAX_ROWS,
            "LP1_DISPATCH_LAYOUT",
        )
        b.validate_type(row["recipe_id"], "ID")
        b.validate_type(row["recipe_sha256"], "D")
        b.require(
            recipes.get(row["recipe_id"], row["recipe_sha256"]) == row["recipe_sha256"],
            "LP1_DISPATCH_LAYOUT",
        )
        recipes[row["recipe_id"]] = row["recipe_sha256"]
        last = row["position"]


def intent_rows(path, inventory, intent, check):
    """Fresh bounded original read; detect replacement, partial and changed input."""
    check()
    io.private_directory(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        identity = (info.st_dev, info.st_ino, info.st_size)

        def unchanged():
            io.private_directory(path.parent)
            current = path.stat(follow_symlinks=False)
            b.require(
                stat.S_ISREG(current.st_mode)
                and current.st_uid == os.getuid()
                and current.st_mode & 0o077 == 0
                and current.st_nlink == 1
                and (current.st_dev, current.st_ino, current.st_size) == identity,
                "LP1_INTENT_CHANGED",
            )

        unchanged()
        h, count, previous = hashlib.sha256(), 0, ""
        with os.fdopen(fd, "rb", closefd=False) as stream:
            while True:
                check()
                raw = stream.readline(MAX_ROW_BYTES + 1)
                if not raw:
                    break
                b.require(len(raw) <= MAX_ROW_BYTES, "LP1_INTENT_BOUND")
                row = io.metadata(raw)
                count += 1
                b.require(
                    set(row) == INTENT_KEYS
                    and type(row["ordinal"]) is int
                    and row["ordinal"] == count
                    and type(row["result_limit"]) is int
                    and row["result_limit"] == intent["size"]
                    and type(row["repetition"]) is int
                    and row["repetition"] == intent["repetition"]
                    and row["workload_kind"] == intent["kind"]
                    and count <= inventory["rows"] <= MAX_ROWS,
                    "LP1_INTENT_BINDING",
                )
                b.validate_type(row["query_semantic_id"], "D")
                b.require(row["query_semantic_id"] > previous, "LP1_INTENT_ORDER")
                previous = row["query_semantic_id"]
                h.update(raw)
                yield previous
        check()
        unchanged()
        b.require(
            count == inventory["rows"] == intent["count"]
            and h.hexdigest() == inventory["sha256"],
            "LP1_INTENT_CHANGED",
        )
    finally:
        os.close(fd)


def assemble(source: Path, output: Path, inventory, intent, layout, *, check):
    """Exclusive deterministic compiler; any failure leaves an unaccepted partial."""
    validate_layout(layout)
    b.validate_type(inventory["sha256"], "D")
    b.require(
        layout["result_limit"] == intent["size"]
        and layout["repetition"] == intent["repetition"]
        and type(inventory["rows"]) is int
        and 1 <= inventory["rows"] == intent["count"] <= MAX_ROWS,
        "LP1_DISPATCH_BINDING",
    )
    controls = layout["controls"]
    total = inventory["rows"] + len(controls)
    b.require(
        total <= MAX_ROWS and (not controls or controls[-1]["position"] <= total),
        "LP1_DISPATCH_BOUND",
    )
    check()
    io.private_directory(output.parent)
    limits.claim("PREFIX_FILE")
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    file_hash, used = hashlib.sha256(), 0
    try:
        with os.fdopen(fd, "wb", closefd=False) as stream:

            def rows():
                nonlocal used
                data = iter(intent_rows(source, inventory, intent, check))
                ci = 0
                try:
                    for work_id in range(1, total + 1):
                        check()
                        control = controls[ci] if ci < len(controls) else None
                        if control is not None and control["position"] == work_id:
                            row = dict(
                                kind="SERVICE_CONTROL",
                                query_semantic_id=None,
                                recipe_id=control["recipe_id"],
                                repetition=None,
                                result_limit=None,
                                retry_spacing_key=control["recipe_sha256"],
                            )
                            ci += 1
                        else:
                            q = next(data)
                            row = dict(
                                kind="DATA",
                                query_semantic_id=q,
                                recipe_id=None,
                                repetition=intent["repetition"],
                                result_limit=intent["size"],
                                retry_spacing_key=q,
                            )
                        row.update(block_id=1, work_id=work_id)
                        operations.validate_type(row, "Work")
                        raw = b.canonical(row)
                        b.require(
                            len(raw) <= MAX_ROW_BYTES
                            and used + len(raw) <= layout["max_output_bytes"],
                            "LP1_DISPATCH_BYTE_LIMIT",
                        )
                        io.charge_write(output, len(raw))
                        stream.write(raw)
                        used += len(raw)
                        file_hash.update(raw)
                        yield row
                    b.require(next(data, None) is None, "LP1_WORK_TOTALITY")
                finally:
                    data.close()

            manifest_hash = operations.manifest_digest(rows())
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)
    io.fsync_directory(output.parent)
    check()
    receipt = {
        "version": "stage12_local_dispatch_receipt_v1",
        "name": output.name,
        "source_intent_sha256": inventory["sha256"],
        "layout_sha256": b.digest(layout),
        "file_sha256": file_hash.hexdigest(),
        "work_manifest_sha256": manifest_hash,
        "rows": total,
        "data_rows": inventory["rows"],
        "control_rows": len(controls),
        "bytes": used,
        "service_transfer_authority": "NOT_GRANTED",
        "scientific_publication": "NOT_GRANTED",
    }
    reopen(output, inventory, intent, layout, receipt, check=check)
    # Original intent is independently re-read after output reopening too.
    for _ in intent_rows(source, inventory, intent, check):
        pass
    return receipt


def reopen(output, inventory, intent, layout, receipt, *, check):
    """Validate original Work bytes again; never an acceptance-token shortcut."""
    check()
    validate_layout(layout)
    controls = layout["controls"]
    total = inventory["rows"] + len(controls)
    b.require(
        receipt["source_intent_sha256"] == inventory["sha256"]
        and receipt["layout_sha256"] == b.digest(layout)
        and receipt["rows"] == total
        and receipt["data_rows"] == inventory["rows"]
        and receipt["control_rows"] == len(controls)
        and receipt["bytes"] <= layout["max_output_bytes"],
        "LP1_DISPATCH_BINDING",
    )
    # A verification view, not an issued or schema-valid scientific workload plan.
    recipes = {x["recipe_id"]: x["recipe_sha256"] for x in controls}
    view = {
        "control_recipes": [
            dict(recipe_id=k, recipe_sha256=v) for k, v in recipes.items()
        ],
        "blocks": [dict(last_work_id=total)],
        "budgets": dict(
            data_observations=inventory["rows"],
            required_control_observations=len(controls),
        ),
        "result_limit": intent["size"],
        "repetition": intent["repetition"],
        "work_manifest_sha256": receipt["work_manifest_sha256"],
    }
    from .s12_b2_runtime import WorkFile

    reader = WorkFile(output, receipt["file_sha256"], view, check=check)
    b.require(reader.identity[2] == receipt["bytes"], "LP1_DISPATCH_BINDING")
