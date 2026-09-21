"""Private checkpoint state: sealed scientific bytes plus saved diagnostics.

Only the two frozen relations are candidate outputs. This work-state snapshot
restores aggregate diagnostics without rebuilding any scientific derivation.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from . import s09_reference_io as base
from . import s09_reference_pack as pack
from . import s10_query_contract as c
from . import s10_query_io as io
from . import s10_query_receipts as receipts

SEAL = "_VALIDATED.json"


def diagnostic_schema() -> Any:
    return pa.schema(
        [
            pa.field("query_context_id", pa.binary(), nullable=True),
            pa.field("stable_source_row_id_v1", pa.binary(), nullable=True),
            pa.field("stage06_exact_candidate_id", pa.binary(), nullable=True),
            pa.field("role", pa.string(), nullable=True),
            pa.field("country", pa.string(), nullable=True),
            pa.field("boundary_fingerprint", pa.binary(), nullable=True),
            pa.field("boundary_value", pa.binary(), nullable=True),
            pa.field("country_state", pa.string(), nullable=True),
            pa.field("q04_postcode_gate", pa.bool_(), nullable=True),
            pa.field("q08_postcode_gate", pa.bool_(), nullable=True),
        ]
    )


class DiagnosticWriter(base.RelationWriter):
    def append(self, row: Mapping[str, Any]) -> None:
        size = 1024 + 8 * len(row["boundary_value"])
        if self.buffer and (
            len(self.buffer) >= self.batch_rows
            or self.buffer_bytes + size > self.batch_bytes
        ):
            self.flush()
        self.buffer.append(row)
        self.buffer_bytes += size
        self.rows += 1
        if self.buffer_bytes >= self.batch_bytes:
            self.flush()


def save_diagnostics(work: Any, root: Path, keys: Sequence[bytes]) -> dict[str, Any]:
    from . import s10_query_contexts as cx
    from . import s10_query_materializer as m

    writer = DiagnosticWriter(root / "diagnostics", diagnostic_schema())
    # One bounded keyed lookup; at most PAGE_CONTEXTS keys. Empty checkpoints
    # still have a valid zero-row private snapshot.
    query = "SELECT * FROM stage10_context_diagnostics WHERE query_context_id IN (SELECT UNNEST(?)) ORDER BY query_context_id"
    seen = []
    for row in cx.sql_rows(work.db, query, [list(keys)]):
        seen.append(row["query_context_id"])
        writer.append(row)
    c.require(seen == list(keys), "STAGE10_CHECKPOINT_DIAGNOSTICS_KEYS")
    writer.close()
    return {
        "name": "context_diagnostics",
        "row_count": writer.rows,
        "schema_sha256": hashlib.sha256(
            diagnostic_schema().serialize().to_pybytes()
        ).hexdigest(),
        "files": [m.file_record(p, root) for p in writer.paths],
    }


def physical(root: Path, record: Mapping[str, Any], schema: Any) -> tuple[Path, ...]:
    paths, count = [], 0
    for item in record["files"]:
        path = pack.confined(root, item["relative_path"])
        pack.regular_private(path)
        c.require(
            path not in paths
            and path.stat().st_size == item["bytes"]
            and c.sha256_file(path) == item["sha256"],
            "STAGE10_CHECKPOINT_FILE_INVALID",
        )
        with pq.ParquetFile(path, page_checksum_verification=True) as parquet:
            c.require(
                parquet.schema_arrow.equals(schema, check_metadata=True),
                "STAGE10_CHECKPOINT_SCHEMA_INVALID",
            )
            count += parquet.metadata.num_rows
        paths.append(path)
    c.require(count == record["row_count"], "STAGE10_CHECKPOINT_COUNT_INVALID")
    return tuple(paths)


def files(record: Mapping[str, Any]) -> list[str]:
    return [
        "checkpoint.json",
        SEAL,
        *[
            f["relative_path"]
            for r in [*record["relations"], record["diagnostics"]]
            for f in r["files"]
        ],
    ]


def seal(root: Path) -> None:
    receipts.write(
        root / SEAL,
        {
            "version": "stage10_validated_unit_v3",
            "checkpoint_sha256": c.sha256_file(root / "checkpoint.json"),
        },
    )


def validate_seal(
    root: Path, record: Mapping[str, Any], *, sealed: bool = True
) -> None:
    if sealed:
        pack.regular_private(root / SEAL)
    expected = {
        "version": "stage10_validated_unit_v3",
        "checkpoint_sha256": c.sha256_file(root / "checkpoint.json"),
    }
    c.require(
        (root / "checkpoint.json").read_bytes() == c.canonical(record),
        "STAGE10_CHECKPOINT_COPY_CHANGED",
    )
    if sealed:
        c.require(
            (root / SEAL).read_bytes() == c.canonical(expected),
            "STAGE10_CHECKPOINT_SEAL_INVALID",
        )
    for relation in record["relations"]:
        c.require(
            relation["schema_sha256"] == c.schema_fingerprint(relation["name"]).hex(),
            "STAGE10_CHECKPOINT_SCHEMA_INVALID",
        )
        physical(root, relation, io.output_schema(relation["name"]))
    physical(root, record["diagnostics"], diagnostic_schema())
    base.topology(root, [f for f in files(record) if sealed or f != SEAL])


def restore_diagnostics(work: Any, root: Path, record: Mapping[str, Any]) -> None:
    paths = [
        pack.confined(root, f["relative_path"]) for f in record["diagnostics"]["files"]
    ]
    if paths:
        work.db.execute(
            "INSERT INTO stage10_context_diagnostics SELECT * FROM "
            + io.parquet_sql(paths)
        )
    work.checkpoint_database()
