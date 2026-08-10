from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from ..phase02.schema import exact_schema_matches
from .errors import Phase03Error


@dataclass(frozen=True, slots=True)
class Phase02ShardIdentity:
    phase02_run_id: str
    relative_source_path: str
    phase02_output_sha256: str
    row_count: int
    phase02_configuration_fingerprint: str
    phase02_implementation_fingerprint: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_phase02_shard_identity(
    path: Path,
    identity: Phase02ShardIdentity,
    *,
    approved_run_id: str,
) -> dict[str, str | int]:
    """Validate file/metadata identity without reading Phase 2 address columns."""
    if identity.phase02_run_id != approved_run_id:
        raise Phase03Error("PHASE02_RUN_IDENTITY_MISMATCH")
    try:
        observed_hash = _sha256(path)
        parquet = pq.ParquetFile(path)
    except (OSError, pa.ArrowException) as error:
        raise Phase03Error(
            "PHASE02_INPUT_READ_FAILURE", type(error).__name__
        ) from error
    if observed_hash != identity.phase02_output_sha256:
        raise Phase03Error("PHASE02_OUTPUT_HASH_MISMATCH")
    if not exact_schema_matches(parquet.schema_arrow):
        raise Phase03Error("PHASE02_SCHEMA_MISMATCH")
    if parquet.metadata.num_rows != identity.row_count:
        raise Phase03Error("PHASE02_ROW_COUNT_MISMATCH")
    metadata = {
        key.decode(): value.decode()
        for key, value in (parquet.schema_arrow.metadata or {}).items()
    }
    expected = {
        "phase02_run_id": identity.phase02_run_id,
        "source_file": identity.relative_source_path,
        "configuration_fingerprint": identity.phase02_configuration_fingerprint,
        "implementation_fingerprint": identity.phase02_implementation_fingerprint,
    }
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise Phase03Error("PHASE02_METADATA_MISMATCH")
    return {
        "phase02_run_id": identity.phase02_run_id,
        "relative_source_path": identity.relative_source_path,
        "row_count": identity.row_count,
        "phase02_output_sha256": observed_hash,
    }
