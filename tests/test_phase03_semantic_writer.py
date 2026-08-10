from __future__ import annotations

import os
import hashlib
from dataclasses import replace
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from safe_geocoding_pipeline.phase03.config import Phase03Config
from safe_geocoding_pipeline.phase03.errors import Phase03Error
from safe_geocoding_pipeline.phase03.phase02_input import (
    Phase02ShardIdentity,
    validate_phase02_shard_identity,
)
from safe_geocoding_pipeline.phase03.semantic import (
    DatasetShardDigest,
    core_digest,
    dataset_digest,
    encode_typed_value,
    evidence_digest,
)
from safe_geocoding_pipeline.phase03.validation import (
    privacy_safe_failure,
    validate_core_evidence_relationship,
    validate_core_rows,
    validate_evidence_rows,
)
from safe_geocoding_pipeline.phase03.writer import (
    atomic_promote_pair,
    revalidate_completed_pair,
    write_validate_and_promote_synthetic_shard,
)

from phase03_helpers import engine, phase02_row


def _result(tmp_path: Path):  # type: ignore[no-untyped-def]
    return engine(tmp_path).transform(
        phase02_row(
            street_address_line_1="Apt. 7B",
            postcode="00123",
            city="Exampleville",
            country_iso_code="XZ",
        )
    )


def test_semantic_digest_golden_vectors(tmp_path: Path) -> None:
    result = _result(tmp_path)
    core = core_digest([result.core_row], "phase03_component_core_v1").hex()
    evidence = evidence_digest(
        result.evidence_rows, "phase03_component_evidence_v1"
    ).hex()
    assert core == "d3d6564b7de680fade6197795bf125269b419b8b21bd1e189903dedceaf02b35"
    assert (
        evidence == "f5ce6d2f9379fd36b9a11bcc80bc6afd3dec888fae1f605d3821dcc11214e590"
    )
    combined = dataset_digest(
        phase03_version="phase03_v1",
        configuration_fingerprint=bytes.fromhex("44" * 32),
        shards=[
            DatasetShardDigest(
                "fictional_00001.parquet",
                bytes.fromhex(core),
                1,
                bytes.fromhex(evidence),
                len(result.evidence_rows),
            )
        ],
    ).hex()
    assert (
        combined == "e908c6941cf52363259ea262bf8689942c53f642fdcdf41e10b9bbfa8e90e124"
    )


def test_effective_configuration_fingerprint_binds_reference_artifacts(
    tmp_path: Path,
) -> None:
    with_references = engine(tmp_path)
    (tmp_path / "without").mkdir()
    without_references = engine(
        tmp_path / "without", with_country=False, with_scripts=False
    )
    assert with_references.configuration_fingerprint.hex() == (
        "4e883215d1051f7374d197ec62786c4178d1423014b31bf75cceabe62372eb5e"
    )
    assert (
        with_references.configuration_fingerprint
        != without_references.configuration_fingerprint
    )


def test_semantic_contract_distinguishes_null_empty_order_and_row_count(
    tmp_path: Path,
) -> None:
    result = _result(tmp_path)
    original = core_digest([result.core_row], "phase03_component_core_v1")
    changed = dict(result.core_row)
    changed["street_clean"] = ""
    assert core_digest([changed], "phase03_component_core_v1") != original
    changed = dict(result.core_row)
    changed["address_conflict_flags"] = ["POSTCODE_SOURCE_CONFLICT"]
    assert core_digest([changed], "phase03_component_core_v1") != original
    assert (
        core_digest([result.core_row, result.core_row], "phase03_component_core_v1")
        != original
    )
    if len(result.evidence_rows) > 1:
        reversed_rows = list(reversed(result.evidence_rows))
        assert evidence_digest(
            reversed_rows, "phase03_component_evidence_v1"
        ) == evidence_digest(result.evidence_rows, "phase03_component_evidence_v1")
    changed_evidence = [dict(row) for row in result.evidence_rows]
    changed_evidence[0]["evidence_id"] = 2
    assert evidence_digest(
        changed_evidence, "phase03_component_evidence_v1"
    ) != evidence_digest(result.evidence_rows, "phase03_component_evidence_v1")


def test_binary_type_tags_distinguish_false_zero_empty_and_null() -> None:
    import pyarrow as pa

    assert encode_typed_value(pa.bool_(), False) != encode_typed_value(pa.uint8(), 0)
    assert encode_typed_value(pa.string(), "") != encode_typed_value(pa.string(), None)
    assert encode_typed_value(pa.list_(pa.string()), []) != encode_typed_value(
        pa.list_(pa.string()), None
    )


def test_synthetic_parquet_roundtrip_checksums_stats_and_atomic_promotion(
    tmp_path: Path,
) -> None:
    result = _result(tmp_path)
    temporary_core = tmp_path / ".in_progress" / "core.tmp"
    temporary_evidence = tmp_path / ".in_progress" / "evidence.tmp"
    final_core = tmp_path / "core" / "fictional.parquet"
    final_evidence = tmp_path / "evidence" / "fictional.parquet"
    write_result = write_validate_and_promote_synthetic_shard(
        core_rows=[result.core_row],
        evidence_rows=result.evidence_rows,
        temporary_core=temporary_core,
        temporary_evidence=temporary_evidence,
        final_core=final_core,
        final_evidence=final_evidence,
        config=Phase03Config(batch_rows=1),
        metadata={"data_classification": "CONFIDENTIAL", "run_scope": "SYNTHETIC_TEST"},
    )
    assert write_result.page_checksums_verified
    assert final_core.exists() and final_evidence.exists()
    assert not temporary_core.exists() and not temporary_evidence.exists()
    for path in (final_core, final_evidence):
        parquet = pq.ParquetFile(path, page_checksum_verification=True)
        assert all(
            parquet.metadata.row_group(group).column(column).statistics is None
            for group in range(parquet.metadata.num_row_groups)
            for column in range(parquet.metadata.row_group(group).num_columns)
        )
    assert (
        revalidate_completed_pair(
            core_path=final_core,
            evidence_path=final_evidence,
            expected=write_result,
            config=Phase03Config(batch_rows=1),
        )
        == write_result
    )


def test_parquet_metadata_configuration_conflict_fails_closed(tmp_path: Path) -> None:
    result = _result(tmp_path)
    with pytest.raises(Phase03Error, match="PARQUET_METADATA_CONFIGURATION_CONFLICT"):
        write_validate_and_promote_synthetic_shard(
            core_rows=[result.core_row],
            evidence_rows=result.evidence_rows,
            temporary_core=tmp_path / "core.tmp",
            temporary_evidence=tmp_path / "evidence.tmp",
            final_core=tmp_path / "core.parquet",
            final_evidence=tmp_path / "evidence.parquet",
            config=Phase03Config(batch_rows=1),
            metadata={"unicode_runtime_version": "15.1.0"},
        )


def test_truncated_parquet_is_rejected_by_checksum_enabled_reader(
    tmp_path: Path,
) -> None:
    result = _result(tmp_path)
    temp_core = tmp_path / "temp_core.parquet"
    temp_evidence = tmp_path / "temp_evidence.parquet"
    final_core = tmp_path / "core.parquet"
    final_evidence = tmp_path / "evidence.parquet"
    write_validate_and_promote_synthetic_shard(
        core_rows=[result.core_row],
        evidence_rows=result.evidence_rows,
        temporary_core=temp_core,
        temporary_evidence=temp_evidence,
        final_core=final_core,
        final_evidence=final_evidence,
        config=Phase03Config(batch_rows=1),
        metadata={"run_scope": "SYNTHETIC_TEST"},
    )
    disposable = tmp_path / "corrupt.parquet"
    data = final_core.read_bytes()
    disposable.write_bytes(data[: len(data) // 2])
    with pytest.raises(Exception):
        pq.ParquetFile(disposable, page_checksum_verification=True).read()


def test_atomic_pair_rolls_back_if_second_promotion_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    temporary_core = tmp_path / "core.tmp"
    temporary_evidence = tmp_path / "evidence.tmp"
    final_core = tmp_path / "core.parquet"
    final_evidence = tmp_path / "evidence.parquet"
    temporary_core.write_bytes(b"core")
    temporary_evidence.write_bytes(b"evidence")
    real_replace = os.replace
    calls = 0

    def failing_replace(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic interruption")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(Phase03Error, match="ATOMIC_PAIR_PROMOTION_FAILURE"):
        atomic_promote_pair(
            temporary_core, temporary_evidence, final_core, final_evidence
        )
    assert temporary_core.exists()
    assert temporary_evidence.exists()
    assert not final_core.exists() and not final_evidence.exists()


def test_validation_detects_identity_empty_selected_and_multiple_spans(
    tmp_path: Path,
) -> None:
    result = _result(tmp_path)
    validate_core_rows([result.core_row])
    damaged = dict(result.core_row)
    damaged["unit_clean"] = ""
    with pytest.raises(Phase03Error, match="EMPTY_SELECTED_COMPONENT"):
        validate_core_rows([damaged])
    damaged = dict(result.core_row)
    damaged["unit_clean"] = None
    with pytest.raises(Phase03Error, match="SELECTED_PROVENANCE_WITHOUT_VALUE"):
        validate_core_rows([damaged])
    evidence = dict(result.evidence_rows[0])
    second = dict(evidence)
    second["span_ordinal"] = 2
    second["start_character"] = evidence["start_character"] + 1
    validate_evidence_rows([evidence, second])
    validate_core_evidence_relationship([result.core_row], [evidence, second])
    orphan = dict(evidence)
    orphan["stable_source_row_id_v1"] = bytes.fromhex("99" * 32)
    with pytest.raises(Phase03Error, match="EVIDENCE_ORPHAN_IDENTITY"):
        validate_core_evidence_relationship([result.core_row], [orphan])


def test_core_validation_proves_provider_identity_and_row_order(tmp_path: Path) -> None:
    first = _result(tmp_path).core_row
    second_input = phase02_row(
        id="fictional-provider-0002",
        source_logical_record_number=2,
        stable_source_row_id_v1=bytes.fromhex("12" * 32),
        street_address_line_1="Unit 9",
    )
    (tmp_path / "second").mkdir()
    second = engine(tmp_path / "second").transform(second_input).core_row
    expected = [
        (first["stable_source_row_id_v1"], first["id"], 1),
        (second["stable_source_row_id_v1"], second["id"], 2),
    ]
    validate_core_rows([first, second], expected_ids=expected)
    with pytest.raises(Phase03Error, match="CORE_SOURCE_IDENTITY_MISMATCH"):
        validate_core_rows([second, first], expected_ids=expected)


def test_failure_reports_are_privacy_safe() -> None:
    report = privacy_safe_failure("SYNTHETIC_FAILURE", "ValueError")
    assert report == {
        "failure_code": "SYNTHETIC_FAILURE",
        "failure_detail_type": "ValueError",
    }
    assert "address" not in str(report).lower()
    redacted = privacy_safe_failure("SYNTHETIC_FAILURE", "Apt 7B, Exampleville")
    assert redacted["failure_detail_type"] == "REDACTED"
    assert "Exampleville" not in str(redacted)


def test_phase02_input_identity_validation_uses_metadata_not_address_scan(
    tmp_path: Path,
) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    from safe_geocoding_pipeline.phase02.schema import schema_with_metadata
    from safe_geocoding_pipeline.raw_csv import SOURCE_COLUMNS

    phase02_path = tmp_path / "fictional_phase02.parquet"
    metadata = {
        "phase02_run_id": "fictional_phase02_run",
        "source_file": "fictional.csv",
        "configuration_fingerprint": "11" * 32,
        "implementation_fingerprint": "22" * 32,
    }
    row = ["fictional"] + [""] * (len(SOURCE_COLUMNS) - 1)
    values = row + [
        "fictional.csv",
        1,
        bytes.fromhex("33" * 32),
        bytes.fromhex("44" * 32),
        "source_csv_15col_v1",
        "phase01_csv_parser_v1",
        "phase02_v1",
    ]
    schema = schema_with_metadata(metadata)
    table = pa.Table.from_arrays(
        [
            pa.array([value], type=field.type)
            for field, value in zip(schema, values, strict=True)
        ],
        schema=schema,
    )
    pq.write_table(table, phase02_path)
    output_hash = hashlib.sha256(phase02_path.read_bytes()).hexdigest()
    identity = Phase02ShardIdentity(
        phase02_run_id="fictional_phase02_run",
        relative_source_path="fictional.csv",
        phase02_output_sha256=output_hash,
        row_count=1,
        phase02_configuration_fingerprint="11" * 32,
        phase02_implementation_fingerprint="22" * 32,
    )
    result = validate_phase02_shard_identity(
        phase02_path, identity, approved_run_id="fictional_phase02_run"
    )
    assert result["row_count"] == 1
    damaged = replace(identity, phase02_output_sha256="00" * 32)
    with pytest.raises(Phase03Error, match="PHASE02_OUTPUT_HASH_MISMATCH"):
        validate_phase02_shard_identity(
            phase02_path, damaged, approved_run_id="fictional_phase02_run"
        )
