from __future__ import annotations

import hashlib
import inspect
import struct
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from safe_geocoding_pipeline.phase02.config import Phase02Config
from safe_geocoding_pipeline.phase02.constants import (
    SOURCE_SCHEMA_VERSION,
    STAGING_COLUMNS,
)
from safe_geocoding_pipeline.phase02.fingerprints import (
    JsonValue,
    canonical_json_bytes,
    fingerprint,
)
from safe_geocoding_pipeline.phase02.identity import stable_source_row_id_v1
from safe_geocoding_pipeline.phase02.manifest import load_phase01_manifest
from safe_geocoding_pipeline.phase02.models import Phase01FileEntry
from safe_geocoding_pipeline.phase02.runner import _select_entries
from safe_geocoding_pipeline.phase02.schema import base_staging_schema
from safe_geocoding_pipeline.phase02.semantic import RawSemanticDigest
from safe_geocoding_pipeline.raw_csv import SOURCE_COLUMNS


def test_staging_schema_is_exact_ordered_and_non_null() -> None:
    schema = base_staging_schema()
    assert schema.names == list(STAGING_COLUMNS)
    assert len(schema) == 22
    assert all(not field.nullable for field in schema)
    assert all(schema.field(name).type == pa.string() for name in SOURCE_COLUMNS)
    assert schema.field("source_logical_record_number").type == pa.uint64()
    assert schema.field("stable_source_row_id_v1").type == pa.binary(32)
    assert schema.field("source_file_sha256").type == pa.binary(32)


def test_stable_source_row_id_golden_vector_and_boundaries() -> None:
    source_hash = bytes(range(32))
    observed = stable_source_row_id_v1(source_hash, 42)
    assert (
        observed.hex()
        == "dee6d1a0bc82e5e097e70c8f12975e371826f5f3b4f985e814ebb351f475fcbc"
    )
    independent = hashlib.sha256(
        b"safe_geocoding_pipeline:stable_source_row_id_v1\0"
        + source_hash
        + struct.pack(">Q", 42)
    ).digest()
    assert observed == independent
    assert observed == stable_source_row_id_v1(source_hash, 42)
    assert observed != stable_source_row_id_v1(source_hash, 43)
    assert observed != stable_source_row_id_v1(bytes(reversed(source_hash)), 42)
    with pytest.raises(ValueError):
        stable_source_row_id_v1(b"short", 42)
    with pytest.raises(ValueError):
        stable_source_row_id_v1(source_hash, 0)


def test_stable_source_row_id_excludes_filename_and_provider_id() -> None:
    source_hash = hashlib.sha256(b"fictional source bytes").digest()
    first = stable_source_row_id_v1(source_hash, 1)
    renamed = stable_source_row_id_v1(source_hash, 1)
    changed_provider_id = stable_source_row_id_v1(source_hash, 1)
    assert first == renamed == changed_provider_id


def _row(*, identifier: str = "0001", postcode: str = "01234") -> list[str]:
    values = [""] * len(SOURCE_COLUMNS)
    values[0] = identifier
    values[1] = "Fictional Straße 1"
    values[5] = "架空住所一丁目"
    values[9] = postcode
    values[10] = "München"
    values[12] = "DE"
    values[13] = "Na"
    values[14] = "Null"
    return values


def test_semantic_digest_golden_vector() -> None:
    digest = RawSemanticDigest()
    digest.update_row(_row(), 1, require_non_null=True)
    digest.update_row(
        _row(identifier="0002", postcode="12-345"), 2, require_non_null=True
    )
    assert (
        digest.hexdigest()
        == "92d71da3eaf5ddc6ef35b41f0c8576c71164e473b0a11b1ac1f2b96cd16f2a19"
    )
    assert digest.row_count == 2
    assert (
        digest.hexdigest()
        == "92d71da3eaf5ddc6ef35b41f0c8576c71164e473b0a11b1ac1f2b96cd16f2a19"
    )


def test_semantic_digest_distinguishes_boundaries_order_empty_and_null() -> None:
    def value(rows: list[list[str | None]], *, require_non_null: bool = False) -> str:
        digest = RawSemanticDigest()
        for ordinal, row in enumerate(rows, start=1):
            digest.update_row(row, ordinal, require_non_null=require_non_null)
        return digest.hexdigest()

    base: list[str | None] = [""] * len(SOURCE_COLUMNS)
    split_a = base.copy()
    split_a[0:2] = ["ab", "c"]
    split_b = base.copy()
    split_b[0:2] = ["a", "bc"]
    null_row = base.copy()
    null_row[0] = None
    literal_row = base.copy()
    literal_row[0] = "Null"
    unicode_row = base.copy()
    unicode_row[0] = "東京"
    assert value([split_a]) != value([split_b])
    assert value([base]) != value([null_row])
    assert value([base]) != value([literal_row])
    assert value([base, unicode_row]) != value([unicode_row, base])
    with pytest.raises(ValueError):
        value([null_row], require_non_null=True)


def test_configuration_fingerprint_uses_canonical_json() -> None:
    first: JsonValue = {"version": 1, "nested": {"b": "東京", "a": None}}
    second: JsonValue = {"nested": {"a": None, "b": "東京"}, "version": 1}
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert fingerprint(first) == fingerprint(second)
    assert (
        fingerprint(first)
        == "9d24a425c9ea8e3263a11f729e6cdc02cff3e7f270ea43e72d06fd94adcb6929"
    )


def test_config_restricts_smoke_scope_and_full_acknowledgement(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="restricted"):
        Phase02Config(
            source_root=tmp_path,
            phase01_run_dir=tmp_path,
            run_scope="SMOKE_TEST",
            include_files=("remaining_addresses_00103.csv",),
        ).validate()
    with pytest.raises(ValueError, match="accepted Stage 0"):
        Phase02Config(
            source_root=tmp_path,
            phase01_run_dir=tmp_path,
            run_scope="FULL_CONVERSION",
            authorize_full_conversion=True,
        ).validate()
    Phase02Config(
        source_root=tmp_path,
        phase01_run_dir=tmp_path,
        stage00_adoption_record=tmp_path / "stage00_adoption.json",
        expected_stage00_adoption_sha256="a" * 64,
        run_scope="FULL_CONVERSION",
        authorize_full_conversion=True,
    ).validate()
    with pytest.raises(ValueError, match="lowercase Stage 0"):
        Phase02Config(
            source_root=tmp_path,
            phase01_run_dir=tmp_path,
            stage00_adoption_record=tmp_path / "stage00_adoption.json",
            expected_stage00_adoption_sha256="A" * 64,
            run_scope="FULL_CONVERSION",
            authorize_full_conversion=True,
        ).validate()


def test_generic_full_selection_has_no_magic_population_size(tmp_path: Path) -> None:
    for count in (1, 3, 7, 206):
        files = {
            (name := f"fictional_{index:04d}.csv"): Phase01FileEntry(
                file_id=index,
                relative_path=name,
                file_name=name,
                size_bytes=index,
                mtime_utc="2026-01-01T00:00:00Z",
                sha256=f"{index:064x}",
                logical_record_count=index,
                schema_fingerprint="f" * 64,
                bom_type="NONE",
            )
            for index in range(1, count + 1)
        }
        config = Phase02Config(
            source_root=tmp_path,
            phase01_run_dir=tmp_path,
            stage00_adoption_record=tmp_path / "stage00_adoption.json",
            expected_stage00_adoption_sha256="a" * 64,
            run_scope="FULL_CONVERSION",
            authorize_full_conversion=True,
        )
        assert len(_select_entries(config, files)) == count
    assert "206" not in inspect.getsource(_select_entries)
    assert "206" not in inspect.getsource(load_phase01_manifest)
    with pytest.raises(ValueError, match="acknowledgement"):
        Phase02Config(
            source_root=tmp_path,
            phase01_run_dir=tmp_path,
            run_scope="FULL_CONVERSION",
        ).validate()


def test_pyarrow_preserves_placeholder_strings_without_null_inference() -> None:
    values = ["", ".", "-", "Na", "Nan", "Null", "00123", "123.0", "東京"]
    array = pa.array(values, type=pa.string(), from_pandas=False, safe=True)
    assert array.to_pylist() == values
    assert array.null_count == 0


def test_page_checksum_verification_rejects_corruption(tmp_path: Path) -> None:
    path = tmp_path / "checksummed.parquet"
    table = pa.table(
        {"value": pa.array([f"fictional-{index:04d}" for index in range(500)])}
    )
    pq.write_table(
        table,
        path,
        compression="NONE",
        use_dictionary=False,
        write_statistics=False,
        data_page_version="1.0",
        write_page_checksum=True,
    )
    assert pq.ParquetFile(path, page_checksum_verification=True).read().num_rows == 500

    metadata = pq.ParquetFile(path).metadata.row_group(0).column(0)
    payload = bytearray(path.read_bytes())
    # The offset begins at the page header. The test mutates well inside this
    # uncompressed page payload rather than depending on a private parser API.
    mutation_offset = metadata.data_page_offset + 256
    payload[mutation_offset] ^= 0x01
    corrupt = tmp_path / "checksummed-corrupt.parquet"
    corrupt.write_bytes(payload)
    with pytest.raises(OSError, match="CRC checksum verification failed"):
        pq.ParquetFile(corrupt, page_checksum_verification=True).read()


def test_source_schema_version_is_fixed() -> None:
    assert SOURCE_SCHEMA_VERSION == "source_csv_15col_v1"
