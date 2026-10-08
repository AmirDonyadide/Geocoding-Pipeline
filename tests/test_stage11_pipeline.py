"""End-to-end synthetic determinism, checkpoint, map and publication faults."""

from __future__ import annotations

import dataclasses
import hashlib
import shutil
from pathlib import Path
from typing import Any

import duckdb
import pytest

from stage11_synthetic import fixture, write
from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_assets as assets
from safe_geocoding_pipeline.preprocessing.stages import (
    s11_semantic_checkpoints as checkpoints,
)
from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_input as source
from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_io as io
from safe_geocoding_pipeline.preprocessing.stages import (
    s11_semantic_pipeline as pipeline,
)
from safe_geocoding_pipeline.preprocessing.stages import (
    s11_semantic_publication as publication,
)

EXE = "1" * 40
ASSETS = assets.identifiers(Path(__file__).resolve().parents[1])


def run(root: Path, inputs: source.Inputs, **kwargs: Any) -> Any:
    root.mkdir(mode=0o700)
    for name in ("local", "durable"):
        (root / name).mkdir(mode=0o700)
    return pipeline.run(
        inputs,
        root / "candidate",
        root / "local",
        root / "durable",
        ASSETS,
        EXE,
        **kwargs,
    )


def test_complete_pipeline_global_map_and_cross_lineage(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    inputs = fixture(root / "input", contexts=52)
    result = run(root / "run", inputs, unit_rows=10)
    report = c.decode_json((result.path / io.SUMMARY_NAME).read_bytes())
    assert report["request_counts"]["unique_requests"] == 3
    assert report["request_counts"]["map_rows"] == 52
    assert report["multiplicity"]["maximum"] == 50
    assert report["reduction"]["hypotheses_saved"] == 49
    assert report["lineage_convergence"]["cross_context"] == 1
    assert report["lineage_convergence"]["cross_source"] == 1
    assert report["lineage_convergence"]["same_source_both_roles"] == 1
    assert all(value == 0 for value in report["integrity"].values())
    assert (result.path / "_COMMITTED").stat().st_size == 0
    record = c.decode_json((result.path / io.SUCCESS_NAME).read_bytes())
    assert (
        record["bindings"]["namespace"]
        == "STAGE11_DEVELOPMENT_SEMANTIC_REQUEST_CATALOG"
    )
    assert "stage11_input_binding_sha256" in record["bindings"]
    assert all("stage10" not in k for k in record["bindings"])
    # Every authoritative byte remains usable after complete job-local loss.
    shutil.rmtree(root / "run/local")
    pipeline.reopen(result.path, result.manifest_sha256, True, inputs, ASSETS, EXE)


def test_clean_reordered_partitioned_and_resumed_equality(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path.resolve()
    inputs = fixture(root / "input")
    reordered = fixture(root / "reordered", reverse=True)
    clean = run(root / "clean", inputs, unit_rows=3, partition_bytes=1, threads=1)
    varied = run(root / "varied", reordered, unit_rows=5, partition_bytes=2, threads=3)
    assert clean.manifest["logical_sha256"] == varied.manifest["logical_sha256"]
    calls = 0

    def interrupt(phase: str) -> None:
        nonlocal calls
        if phase == "input_unit_complete":
            calls += 1
            if calls == 2:
                raise RuntimeError("SYNTHETIC_POISON_DO_NOT_LOG")

    monkeypatch.setattr(checkpoints, "fault", interrupt)
    with pytest.raises(c.Stage11Error):
        run(root / "interrupted", inputs, unit_rows=3)
    assert not (root / "interrupted/candidate/_COMMITTED").exists()
    shutil.rmtree(root / "interrupted/local")
    monkeypatch.setattr(checkpoints, "fault", lambda phase: None)
    resumed = run(
        root / "resumed", inputs, unit_rows=3, resume=root / "interrupted/durable"
    )
    assert resumed.manifest["logical_sha256"] == clean.manifest["logical_sha256"]
    assert (
        resumed.manifest["operational_provenance"]["checkpoints"]["adopted_input_units"]
        == 2
    )
    assert [r["logical_sha256"] for r in clean.manifest["relations"]] == [
        r["logical_sha256"] for r in varied.manifest["relations"]
    ]
    assert (
        clean.manifest_sha256 != varied.manifest_sha256
    )  # Physical/operational identities are separate.


@pytest.mark.parametrize(
    "change",
    ["incomplete", "executable", "input", "profile", "coverage", "bytes", "overlap"],
)
def test_checkpoint_adoption_fails_closed(tmp_path: Path, change: str) -> None:
    root = tmp_path.resolve()
    result = run(root / "clean", fixture(root / "input"), unit_rows=3)
    unit = root / "clean/durable/input-00000000"
    record = c.decode_json((unit / checkpoints.DESCRIPTOR).read_bytes())
    expected = {k: record[k] for k in ("binding", "kind", "coverage")}
    if change == "incomplete":
        (unit / checkpoints.SEAL).unlink()
    elif change == "bytes":
        (unit / record["files"][0]["relative_path"]).write_bytes(b"interrupted copy")
    elif change in ("coverage", "overlap"):
        expected["coverage"] = {**expected["coverage"], "hypotheses": 999}
    else:
        key = {
            "executable": "execution_git_sha",
            "input": "input_binding_sha256",
            "profile": "profile_sha256",
        }[change]
        expected["binding"] = {
            **expected["binding"],
            key: "0" * len(expected["binding"][key]),
        }
    with pytest.raises(c.Stage11Error, match="S11_CHECKPOINT_INVALID"):
        checkpoints.validate_unit(unit, expected)
    assert result.path.exists()


def test_collision_is_fatal_before_seal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path.resolve()
    monkeypatch.setattr(c, "semantic_id", lambda value: bytes(32))
    errors = []
    with pytest.raises(c.Stage11Error):
        run(
            root / "collision",
            fixture(root / "input"),
            observer=lambda phase, error: errors.append(error) if error else None,
        )
    assert any(
        isinstance(e, c.Stage11Error) and str(e) == "S11_ID_COLLISION" for e in errors
    )
    assert not (root / "collision/candidate/_COMMITTED").exists()


@pytest.mark.parametrize(
    "fault_phase", ["reserved", "data", "manifest", "prepared_record", "before_commit"]
)
def test_interrupted_publication_cannot_seal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault_phase: str
) -> None:
    root = tmp_path.resolve()

    def fault(phase: str, _: Path) -> None:
        if phase == fault_phase:
            raise RuntimeError("POISON")

    monkeypatch.setattr(publication, "fault", fault)
    with pytest.raises(c.Stage11Error):
        run(root / "run", fixture(root / "input"))
    assert not (root / "run/candidate/_COMMITTED").exists()


def test_after_effect_seal_reconciliation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path.resolve()

    def fault(phase: str, _: Path) -> None:
        if phase == "after_commit":
            raise RuntimeError("synthetic after-effect error")

    monkeypatch.setattr(publication, "fault", fault)
    result = run(root / "run", fixture(root / "input"))
    assert result.disposition == "ADOPT_COMMITTED_AFTER_RECONCILIATION"


@pytest.mark.parametrize(
    "corruption",
    ["manifest", "registration", "payload", "seal", "permissions", "symlink"],
)
def test_reopen_rejects_corrupt_objects(tmp_path: Path, corruption: str) -> None:
    root = tmp_path.resolve()
    inputs = fixture(root / "input")
    result = run(root / "run", inputs)
    if corruption == "manifest":
        path = result.path / io.MANIFEST_NAME
        path.write_bytes(path.read_bytes() + b" ")
    elif corruption == "registration":
        (result.path / io.SUCCESS_NAME).write_bytes(b"{}\n")
    elif corruption == "payload":
        f = result.manifest["relations"][0]["files"][0]
        (result.path / f["relative_path"]).write_bytes(b"corruption")
    elif corruption == "seal":
        (result.path / publication.SEAL).unlink()
    elif corruption == "permissions":
        (result.path / io.SUMMARY_NAME).chmod(0o644)
    else:
        target = result.path / io.SUMMARY_NAME
        target.unlink()
        target.symlink_to(root / "input/h.parquet")
    with pytest.raises(Exception):
        pipeline.reopen(result.path, result.manifest_sha256, True, inputs, ASSETS, EXE)


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "extra", "orphan", "dangling", "swapped"]
)
def test_map_semantics_reject_equal_count_corruption(
    tmp_path: Path, mutation: str
) -> None:
    root = tmp_path.resolve()
    inputs = fixture(root / "input")
    result = run(root / "run", inputs)
    maps = list(
        io.parquet_rows(
            [
                result.path / f["relative_path"]
                for f in result.manifest["relations"][1]["files"]
            ]
        )
    )
    cores = list(
        io.parquet_rows(
            [
                result.path / f["relative_path"]
                for f in result.manifest["relations"][0]["files"]
            ]
        )
    )
    if mutation == "missing":
        maps.pop()
    elif mutation == "duplicate":
        maps[0] = dict(maps[1])
    elif mutation == "extra":
        maps.append(
            {
                "hypothesis_id": bytes(32),
                "query_semantic_id": maps[0]["query_semantic_id"],
            }
        )
    elif mutation == "orphan":
        cores.append({"query_semantic_id": bytes(32), "core": cores[0]["core"]})
    elif mutation == "dangling":
        maps[0]["query_semantic_id"] = bytes(32)
    else:
        j = next(
            i
            for i, m in enumerate(maps)
            if m["query_semantic_id"] != maps[0]["query_semantic_id"]
        )
        maps[0]["query_semantic_id"], maps[j]["query_semantic_id"] = (
            maps[j]["query_semantic_id"],
            maps[0]["query_semantic_id"],
        )
    write(root / "maps.parquet", maps, c.schema("hypothesis_request_map"))
    write(root / "cores.parquet", cores, c.schema("semantic_request"))
    with duckdb.connect() as connection:
        inputs.register(connection)
        connection.execute(
            f"CREATE VIEW m AS SELECT * FROM {io.parquet_sql([root / 'maps.parquet'])}"
        )
        connection.execute(
            f"CREATE VIEW s AS SELECT * FROM {io.parquet_sql([root / 'cores.parquet'])}"
        )
        with pytest.raises(c.Stage11Error):
            pipeline.check_map(connection, inputs)


def test_no_unpinned_reservation_adoption(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    inputs = fixture(root / "input")
    result = run(root / "run", inputs)
    with pytest.raises(c.Stage11Error):
        publication.publish(
            result.path, lambda _: {}, lambda *_: {}, expected_manifest=None
        )


def test_changed_input_fingerprint_rejected(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    inputs = dataclasses.replace(fixture(root / "input"), hypothesis_sha="0" * 64)
    with pytest.raises(c.Stage11Error, match="S11_INPUT_BINDING_INVALID"):
        run(root / "run", inputs)
    assert not (root / "run/candidate").exists()


def test_claimed_id_recompute_rejected() -> None:
    from test_stage11_semantic_contract import full

    with pytest.raises(c.Stage11Error, match="S11_ID_RECOMPUTE_MISMATCH"):
        c.relation_digest(
            "semantic_request", 1, [{"query_semantic_id": bytes(32), "core": full()}]
        )
    assert hashlib.sha256(b"synthetic").digest() != bytes(32)


@pytest.mark.parametrize("n", [1, 50])
def test_one_and_many_hypotheses_to_one_request(tmp_path: Path, n: int) -> None:
    root = tmp_path.resolve()
    inputs = fixture(
        root / "input",
        contexts=n,
        structured=False,
        empty_context=False,
        varied_boundary=False,
    )
    result = run(root / "run", inputs)
    assert [r["row_count"] for r in result.manifest["relations"]] == [1, n]


def test_incomplete_unit_is_preserved_and_rebuilt_in_new_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path.resolve()
    inputs = fixture(root / "input")
    clean = run(root / "clean", inputs)

    def interrupt(phase: str) -> None:
        if phase == "before_unit_seal":
            raise c.Stage11Error("S11_RESOURCE_FAILURE")

    monkeypatch.setattr(checkpoints, "fault", interrupt)
    with pytest.raises(c.Stage11Error):
        run(root / "partial", inputs)
    partial = root / "partial/durable/input-00000000"
    assert (partial / "unit.json").exists() and not (partial / "_COMPLETE").exists()
    monkeypatch.setattr(checkpoints, "fault", lambda _: None)
    resumed = run(root / "resume", inputs, resume=root / "partial/durable")
    assert resumed.manifest["logical_sha256"] == clean.manifest["logical_sha256"]
    assert (partial / "unit.json").exists() and not (partial / "_COMPLETE").exists()


def test_cross_context_family_link_fails(tmp_path: Path) -> None:
    import pyarrow.parquet as pq

    root = tmp_path.resolve()
    inputs = fixture(root / "input")
    rows = list(io.parquet_rows(inputs.decisions))
    eligible = [r for r in rows if r["hypothesis_id"] is not None]
    other = next(
        r for r in eligible if r["query_context_id"] != eligible[0]["query_context_id"]
    )
    eligible[0]["hypothesis_id"] = other["hypothesis_id"]
    schema = pq.read_schema(inputs.decisions[0])
    write(inputs.decisions[0], rows, schema)
    with pytest.raises(c.Stage11Error, match="S11_UPSTREAM_ID_INVALID"):
        run(root / "run", inputs)
