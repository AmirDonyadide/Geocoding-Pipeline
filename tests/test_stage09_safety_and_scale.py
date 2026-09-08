"""Synthetic scale, CLI, execution guard and static scientific-boundary gates."""

from __future__ import annotations

import socket
import subprocess
from pathlib import Path

import pytest

from safe_geocoding_pipeline.preprocessing import stage09_cli as cli
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_input as upstream
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_io as io
from safe_geocoding_pipeline.preprocessing.stages import (
    s09_reference_materializer as materializer,
)
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_questions as q


@pytest.mark.slow
def test_881338_component_candidate_streams_without_component_list():
    count = 881338
    candidate = {
        "stage06_exact_candidate_id": b"c" * 32,
        "stage07_trusted_country_iso_code": "de",
        "stage07_country_provenance_status": "COUNTRY_UNANIMOUS_VALID",
        "stage08_raw_component_count": count,
    }

    def components():
        for ordinal in range(count):
            yield {
                "stage06_exact_candidate_id": b"c" * 32,
                "stage08_component_ordinal": ordinal,
                "stage08_safe_parser_evidence_component": "PARSER_ROAD",
                "stage08_raw_libpostal_value": "synthetic",
            }

    road_questions = 0
    for question in q.parser_questions(candidate, components()):
        if question.question_id == "Q12":
            road_questions += 1
        if question.question_id == "Q13":
            assert question.observations[1].observed_role_count == count
            assert question.observations[1].value is None
            assert question.observations[1].origin_relation == "MISSING_OR_AMBIGUOUS"
    assert road_questions == count


def test_giant_scalar_is_not_truncated_by_tiny_batch_target(tmp_path):
    from safe_geocoding_pipeline.preprocessing.stages import (
        s09_reference_postal as postal,
    )

    # Scientific evidence schema contains pointers/digests, never this value.
    value = "é例0" * 400_000
    normalized = c.normalize(c.NAME_NORM, value)
    digest = c.identity("NORMALIZED_VALUE", (c.NAME_NORM, normalized))
    assert len(digest) == 32 and normalized == value
    import pyarrow as pa

    schema = pa.schema(
        [
            pa.field("lookup_identity", pa.binary(32), nullable=False),
            pa.field("key1", pa.large_string(), nullable=False),
        ]
    )
    writer = io.RelationWriter(
        tmp_path / "giant", schema, batch_rows=1, batch_bytes=16, target_file_bytes=32
    )
    writer.append({"lookup_identity": digest, "key1": normalized})
    writer.close()
    assert next(io.parquet_rows(writer.paths))["key1"] == value
    assert "key1" not in c.relation_schema("candidate_reference_evidence").names
    assert "key1" in postal.REQUEST_SCHEMA.names


def test_network_tripwire_blocks_even_dns_without_opening_any_socket():
    with materializer.offline_network():
        with pytest.raises(c.Stage09Error, match="NETWORK_ACCESS_PROHIBITED"):
            socket.getaddrinfo("synthetic.invalid", 443)
        with pytest.raises(c.Stage09Error, match="NETWORK_ACCESS_PROHIBITED"):
            socket.create_connection(("synthetic.invalid", 443))


def test_protected_cli_guard_fails_before_path_access(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setattr(
        materializer.pack,
        "verify_lock",
        lambda *args: pytest.fail("Input opened before guard"),
    )
    args = ["materialize"]
    for name in (
        "stage08-root",
        "reference-raw-root",
        "reference-lock",
        "reference-pack-root",
        "output-directory",
    ):
        args.extend(["--" + name, str(tmp_path / "synthetic-canary")])
    args.extend(["--execution-git-sha", "f" * 40])
    assert cli.main(args) == 1
    assert "synthetic-canary" not in capsys.readouterr().err


def test_protected_consumer_has_no_local_bypass(monkeypatch, tmp_path):
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    from safe_geocoding_pipeline.execution_policy import ExecutionPolicyError

    with pytest.raises(ExecutionPolicyError):
        upstream.consume_accepted_stage08(tmp_path / "nonexistent")


def test_post_success_presentation_failure_cannot_change_success(monkeypatch, tmp_path):
    class Broken:
        def write(self, value):
            raise OSError("synthetic broken stdout")

        def flush(self):
            raise OSError("synthetic broken flush")

    marker = tmp_path / io.SUCCESS_NAME
    marker.write_bytes(b"published synthetic sentinel")
    monkeypatch.setattr(cli.sys, "stdout", Broken())
    outcome = io.PublicationResult(
        tmp_path,
        "f" * 64,
        {
            "development_metrics": {"total_stage06_candidates": 1, "evidence_rows": 1},
            "logical_sha256": "a" * 64,
            "profile_sha256": "b" * 64,
        },
    )
    cli._present(outcome)
    assert marker.read_bytes() == b"published synthetic sentinel"


def test_stage09_launcher_is_guarded_offline_and_syntax_valid():
    root = Path(__file__).resolve().parents[1]
    path = root / "cluster/goethe_nhr/stage09_offline_reference_evidence.sbatch"
    text = path.read_text()
    subprocess.run(["bash", "-n", str(path)], check=True)
    for required in (
        "SAFE_EXECUTION_SITE=goethe-nhr",
        "SLURM_JOB_ID",
        "--stage08-root",
        "--reference-lock",
        "git rev-parse HEAD",
        "git status --porcelain",
        "umask 077",
    ):
        assert required in text
    for prohibited in (
        "curl ",
        "wget ",
        "pip install",
        "git pull",
        "--force",
        "srun ",
        "/scratch",
    ):
        assert prohibited not in text


def test_source_runtime_guard_accepts_only_unchanged_stage08_fingerprints():
    from safe_geocoding_pipeline.preprocessing.stages import s08_address_evidence as s08

    assert (
        s08.stage08_contract_fingerprint(s08.accepted_stage08_input_binding())
        == upstream.STAGE08_CONTRACT_SHA256
    )
    assert s08.stage08_schema_bundle_fingerprint() == upstream.STAGE08_SCHEMA_SHA256


def test_extra_output_columns_fail_instead_of_being_silently_ignored(tmp_path):
    writer = io.RelationWriter(
        tmp_path / "invalid", c.relation_schema("reference_match_member")
    )
    with pytest.raises(c.Stage09Error, match="COLUMN_ALLOWLIST"):
        writer.append({"corrected_postcode": "synthetic"})


def test_stage08_consumer_uses_accepted_marker_and_inventory_contract(
    tmp_path, monkeypatch
):
    import pyarrow as pa
    import pyarrow.parquet as pq
    from safe_geocoding_pipeline.preprocessing.stages import s08_address_evidence as s08

    # Invented empty physical fixture: only exercise the existing consumer
    # contract, never the guarded materializer or real accepted input paths.
    monkeypatch.setattr(upstream, "require_goethe_nhr_slurm", lambda *_: None)
    physical = {"metadata_artifacts": []}
    for name, schema in (
        ("candidate_evidence", s08.candidate_evidence_schema()),
        ("parser_component_evidence", s08.parser_component_evidence_schema()),
        ("source_candidate_map", s08.source_candidate_map_schema()),
    ):
        path = tmp_path / (name + ".parquet")
        pq.write_table(pa.Table.from_pylist([], schema=schema), path)
        path.chmod(0o600)
        physical[name + "_artifacts"] = [
            {
                "relative_path": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": c.sha256_file(path),
                "row_count": 0,
            }
        ]
    monkeypatch.setattr(upstream, "COUNTS", {name: 0 for name in upstream.COUNTS})
    manifest = {
        "scientific_identity": {
            "contract_fingerprint": upstream.STAGE08_CONTRACT_SHA256,
            "schema_bundle_fingerprint": upstream.STAGE08_SCHEMA_SHA256,
            "schema_fingerprints": s08.stage08_schema_fingerprints(),
            "label_mapping_fingerprint": s08.stage08_label_mapping_fingerprint(),
            "logical_dataset_sha256": upstream.STAGE08_LOGICAL_SHA256,
            "relation_logical_fingerprints": upstream.STAGE08_RELATIONS,
            "input_binding": s08.accepted_stage08_input_binding().to_dict(),
            "representation_occurrence_view": {
                "materialized": False,
                "canonical_sql": s08.REPRESENTATION_OCCURRENCE_SQL,
                "row_count": 69747,
            },
        },
        "physical_identity": physical,
    }
    io.write_json(tmp_path / s08.STAGE08_MANIFEST_NAME, manifest)
    digest = c.sha256_file(tmp_path / s08.STAGE08_MANIFEST_NAME)
    monkeypatch.setattr(upstream, "STAGE08_MANIFEST_SHA256", digest)
    io.write_json(
        tmp_path / s08.STAGE08_SUCCESS_NAME,
        {
            "manifest_sha256": digest,
            "logical_dataset_sha256": upstream.STAGE08_LOGICAL_SHA256,
        },
    )
    assert set(upstream.consume_accepted_stage08(tmp_path).paths) == {
        "candidate_evidence",
        "parser_component_evidence",
        "source_candidate_map",
    }


def test_full_lookup_collision_guard_spans_separate_shards(tmp_path):
    import pyarrow as pa
    from safe_geocoding_pipeline.preprocessing.stages import (
        s09_reference_postal as postal,
    )

    schema = pa.schema(
        [
            postal.REQUEST_SCHEMA.field(name)
            for name in ("lookup_identity", "country", "question", "key1", "key2")
        ]
    )
    paths = []
    for n, value in enumerate(("00001", "00002")):
        writer = io.RelationWriter(tmp_path / str(n), schema)
        writer.append(
            {
                "lookup_identity": b"x" * 32,
                "country": "US",
                "question": "Q05",
                "key1": value,
                "key2": None,
            }
        )
        writer.close()
        paths.extend(writer.paths)
    with io.bounded_connection(tmp_path / "spill", memory="128MB", threads=1) as db:
        for path in paths:
            postal.validate_full_lookup_keys(db, [path])
        with pytest.raises(c.Stage09Error, match="FULL_KEY_MISMATCH"):
            postal.validate_full_lookup_keys(db, paths)
