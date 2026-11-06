"""Selected RS1 controls with invented records, small local files and denial."""

from copy import deepcopy
from array import array
import errno
import os
import sqlite3
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from stage12_b2_synthetic import World, H, offline  # noqa: F401
from test_stage12_b2_publication import publish_world
from test_stage12_b2_resources import model as resource_model
from test_stage12_b2_runtime import configuration, pin, port, prep_grants
from safe_geocoding_pipeline.preprocessing import stage12_development_cli as cli
from safe_geocoding_pipeline.preprocessing.stages import (
    s11_semantic_io as upstream,
    s12_b2_allocation_limits as limits,
    s12_b2_catalog as catalog,
    s12_b2_contract as b,
    s12_b2_resources as resources,
    s12_b2_runtime as runtime,
    s12_public_journal as journal,
    s12_retrieval_contract as contract,
    s12_raw_packs as packs,
    s12_response as response,
    s12_storage as storage,
)


def selection(**changes):
    value = {
        "schema_version": limits.VERSION,
        "model_sha256": H,
        "command_id": 1,
        "review_sha256": H,
        "native_bound_evidence_sha256": H,
        "max_compressed_frame_bytes": 2**20,
        "max_candidate_buffer_bytes": 2**20,
        "max_arrow_batch_bytes": 2**20,
        "max_parquet_file_bytes": 2**20,
        "max_raw_pack_bytes": 2**20,
        "max_python_write_bytes": 128 * 2**20,
        "sqlite_main_bytes": 2**20,
        "duckdb_spill_bytes": 8 * 2**20,
        "invocations": dict.fromkeys(limits.ROLES, 2000),
    }
    value.update(changes)
    return value


def test_strict_selection_missing_unknown_and_bad_values():
    base = selection()
    assert limits.parse(b.canonical(base)) == base
    for mutate in (
        lambda v: v.pop("sqlite_main_bytes"),
        lambda v: v.update(duckdb_spill_bytes=None),
        lambda v: v.update(max_python_write_bytes=0),
        lambda v: v.update(unselected=True),
        lambda v: v["invocations"].pop("SQLITE"),
        lambda v: v["invocations"].update(SQLITE=True),
    ):
        value = deepcopy(base)
        mutate(value)
        with pytest.raises(contract.Stage12Error):
            limits.parse(b.canonical(value))


def test_materialized_limits_enforced_before_persistence(tmp_path):
    controls = limits.Controls(selection(max_compressed_frame_bytes=3))
    with storage.allocation_controls(controls):
        assert limits.compressed(b"invented", lambda _: b"123") == b"123"
        with pytest.raises(contract.Stage12Error, match="COMPRESSED_FRAME_LIMIT"):
            limits.compressed(b"invented", lambda _: b"1234")
        assert not list(tmp_path.iterdir())
        assert controls.counts["COMPRESSED_FRAME"] == 2
    with limits.CappedBuffer(3) as buffer:
        assert buffer.write(b"123") == 3
        with pytest.raises(contract.Stage12Error, match="MATERIALIZED_BUFFER_LIMIT"):
            buffer.write(b"4")
        assert buffer.getvalue() == b"123"
    table = pa.table({"x": ["invented"]})
    baseline = limits.candidate_bytes(table)
    with storage.allocation_controls(limits.Controls(selection())):
        assert limits.candidate_bytes(table) == baseline
    controls = limits.Controls(selection(max_candidate_buffer_bytes=8))
    with storage.allocation_controls(controls):
        with pytest.raises(Exception):
            limits.candidate_bytes(table)
        assert controls.counts["CANDIDATE_BUFFER"] == 1


def test_physical_boundary_and_failed_allocation_never_refunded(tmp_path):
    tmp_path.chmod(0o700)
    controls = limits.Controls(selection())
    with storage.allocation_controls(controls):
        sink = limits.PhysicalSink(tmp_path / "exact", 3, "PARQUET_FILE")
        assert sink.write(b"123") == 3
        assert sink.tell() == 3
        with pytest.raises(contract.Stage12Error, match="PARQUET_PHYSICAL_LIMIT"):
            sink.write(b"4")
        with pytest.raises(contract.Stage12Error, match="SINK_FAILED"):
            sink.write(b"")
        sink.close()
        assert (tmp_path / "exact").read_bytes() == b"123"
        assert controls.python_bytes == 3
        with pytest.raises(FileExistsError):
            limits.PhysicalSink(tmp_path / "exact", 3, "PARQUET_FILE")
        assert controls.python_bytes == 6
        assert controls.counts["PARQUET_FILE"] == 2


def test_typed_and_noncontiguous_views_obey_byte_not_element_limits(tmp_path):
    tmp_path.chmod(0o700)
    view = memoryview(array("I", [1]))
    assert view.nbytes == 4 > len(view)
    with limits.CappedBuffer(1) as sink:
        with pytest.raises(contract.Stage12Error, match="MATERIALIZED_BUFFER_LIMIT"):
            sink.write(view)
        assert len(sink._data) == 1 and sink.tell() == 0
    with limits.CappedBuffer(view.nbytes) as sink:
        assert sink.write(memoryview(array("I"))) == 0
        assert sink.write(view.toreadonly()) == view.nbytes
        assert sink.getvalue() == view.cast("B").tobytes()
    noncontiguous = memoryview(b"1234")[::2]
    with limits.CappedBuffer(4) as sink:
        with pytest.raises(contract.Stage12Error, match="NONCONTIGUOUS_BUFFER"):
            sink.write(noncontiguous)
        assert sink.tell() == 0 and len(sink._data) == 4
    controls = limits.Controls(selection())
    with storage.allocation_controls(controls):
        sink = limits.PhysicalSink(tmp_path / "too_small", 1, "PARQUET_FILE")
        with pytest.raises(contract.Stage12Error, match="PARQUET_PHYSICAL_LIMIT"):
            sink.write(view)
        sink.close()
        assert (tmp_path / "too_small").stat().st_size == 0
        sink = limits.PhysicalSink(tmp_path / "exact", view.nbytes, "PARQUET_FILE")
        assert sink.write(memoryview(array("I"))) == 0
        assert sink.write(view.toreadonly()) == view.nbytes
        sink.close()
        assert (tmp_path / "exact").read_bytes() == view.cast("B").tobytes()
        sink = limits.PhysicalSink(tmp_path / "strided", 4, "PARQUET_FILE")
        with pytest.raises(contract.Stage12Error, match="NONCONTIGUOUS_BUFFER"):
            sink.write(noncontiguous)
        assert sink.failed
        sink.close()
        assert (tmp_path / "strided").stat().st_size == 0


def test_footer_overflow_retains_partial_and_no_later_footer(tmp_path):
    tmp_path.chmod(0o700)
    controls = limits.Controls(selection())
    path = tmp_path / "partial.parquet"
    with storage.allocation_controls(controls):
        sink = limits.PhysicalSink(path, 256, "PARQUET_FILE")
        writer = pq.ParquetWriter(
            sink, pa.schema([("x", pa.int64())]), compression="zstd"
        )
        writer.write_table(pa.table({"x": [1, 2, 3]}))
        before = path.stat().st_size
        assert 4 < before < 256
        with pytest.raises(Exception):
            writer.close()
        assert sink.failed
        failed = path.read_bytes()
        assert len(failed) <= 256
        sink.close()
        assert path.read_bytes() == failed
        assert controls.python_bytes == 256


def test_partial_disk_full_is_poisoned_and_fully_charged(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    real_write = os.write
    calls = 0

    def disk_full(fd, data):
        nonlocal calls
        calls += 1
        if calls == 1:
            return real_write(fd, data[:2])
        raise OSError(errno.ENOSPC, "synthetic disk full")

    controls = limits.Controls(selection())
    with storage.allocation_controls(controls):
        sink = limits.PhysicalSink(tmp_path / "partial", 32, "RAW_PACK_FILE")
        monkeypatch.setattr(limits.os, "write", disk_full)
        with pytest.raises(OSError) as failure:
            sink.write(b"12345")
        assert failure.value.errno == errno.ENOSPC and sink.failed
        sink.close()
        assert (tmp_path / "partial").read_bytes() == b"12"
        assert controls.python_bytes == 32


def test_invocations_and_chunks_are_bounded_without_path_cache(tmp_path):
    tmp_path.chmod(0o700)
    value = selection(max_python_write_bytes=3)
    value["invocations"]["EXCLUSIVE_FILE"] = 1
    controls = limits.Controls(value)
    with storage.allocation_controls(controls):
        storage.write(tmp_path / "first", b"123")
        with pytest.raises(contract.Stage12Error, match="INVOCATION_BUDGET"):
            storage.write(tmp_path / "second", b"")
        with pytest.raises(contract.Stage12Error, match="WRITE_BUDGET"):
            storage.charge_write(tmp_path / "first", 1)
        assert not (tmp_path / "second").exists()
    assert controls.python_bytes == 3
    assert set(controls.counts) == set(limits.ROLES)


def test_materialized_and_arrow_batch_memory_have_separate_limits(tmp_path):
    tmp_path.chmod(0o700)
    controls = limits.Controls(selection(max_arrow_batch_bytes=64))
    with storage.allocation_controls(controls):
        with pytest.raises(contract.Stage12Error, match="ARROW_BATCH_LIMIT"):
            limits.candidate_bytes(pa.table({"x": ["x" * 65]}))
        writer = limits.relation_writer(
            tmp_path / "rows", pa.schema([("x", pa.string())])
        )
        with pytest.raises(contract.Stage12Error, match="ARROW_BATCH_LIMIT"):
            writer.append({"x": "x" * 65})
        assert not writer.buffer and not writer.paths


def test_relation_writer_failure_cannot_retry_or_emit_another_file(tmp_path):
    tmp_path.chmod(0o700)
    controls = limits.Controls(selection(max_parquet_file_bytes=8))
    with storage.allocation_controls(controls):
        writer = limits.relation_writer(
            tmp_path / "rows", pa.schema([("x", pa.int64())])
        )
        writer.append({"x": 1})
        with pytest.raises(Exception):
            writer.flush()
        assert writer.failed
        with pytest.raises(contract.Stage12Error, match="SINK_FAILED"):
            writer.flush()
        with pytest.raises(contract.Stage12Error, match="SINK_FAILED"):
            writer.append({"x": 2})
        assert len(writer.paths) == 1
        assert writer.paths[0].stat().st_size <= 8
        assert controls.counts["PARQUET_FILE"] == 1


def test_relation_fsync_uncertainty_poison_is_sticky(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    controls = limits.Controls(selection())
    with storage.allocation_controls(controls):
        writer = limits.relation_writer(
            tmp_path / "rows", pa.schema([("x", pa.int64())])
        )
        writer.append({"x": 1})
        writer.flush()
        with monkeypatch.context() as fault:
            fault.setattr(
                limits.os,
                "fsync",
                lambda _: (_ for _ in ()).throw(
                    OSError(errno.EIO, "synthetic uncertain fsync")
                ),
            )
            with pytest.raises(OSError) as failure:
                writer.close()
            assert failure.value.errno == errno.EIO
        assert writer.failed and writer._physical.failed
        assert writer._physical.closed and writer._physical.fd is None
        for operation in (lambda: writer.append({"x": 2}), writer.flush, writer.close):
            with pytest.raises(contract.Stage12Error, match="SINK_FAILED"):
                operation()
        assert len(writer.paths) == controls.counts["PARQUET_FILE"] == 1


def test_header_failure_preserves_primary_despite_cleanup_fault(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    controls = limits.Controls(selection())

    def partial_header(sink, *_args, **_kwargs):
        sink.write(b"PAR1")
        raise RuntimeError("SYNTHETIC_HEADER_PRIMARY")

    with storage.allocation_controls(controls):
        writer = limits.relation_writer(
            tmp_path / "rows", pa.schema([("x", pa.int64())])
        )
        writer.append({"x": 1})
        with monkeypatch.context() as fault:
            fault.setattr(limits.pq, "ParquetWriter", partial_header)
            fault.setattr(
                limits.os,
                "fsync",
                lambda _: (_ for _ in ()).throw(
                    OSError(errno.EIO, "synthetic secondary cleanup")
                ),
            )
            with pytest.raises(RuntimeError, match="SYNTHETIC_HEADER_PRIMARY"):
                writer.flush()
        assert writer.failed and writer._physical.failed
        assert writer._physical.closed and writer._physical.fd is None
        assert writer.paths[0].read_bytes() == b"PAR1"
        for operation in (lambda: writer.append({"x": 2}), writer.flush, writer.close):
            with pytest.raises(contract.Stage12Error, match="SINK_FAILED"):
                operation()
        assert controls.counts["PARQUET_FILE"] == 1


def test_native_close_primary_survives_fsync_secondary(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    controls = limits.Controls(selection())

    class Native:
        def __init__(self, sink, *_args, **_kwargs):
            sink.write(b"PAR1")

        def write_table(self, table):
            pass

        def close(self):
            raise RuntimeError("SYNTHETIC_NATIVE_CLOSE_PRIMARY")

    with storage.allocation_controls(controls):
        writer = limits.relation_writer(
            tmp_path / "rows", pa.schema([("x", pa.int64())])
        )
        writer.append({"x": 1})
        with monkeypatch.context() as fault:
            fault.setattr(limits.pq, "ParquetWriter", Native)
            writer.flush()
            fault.setattr(
                limits.os,
                "fsync",
                lambda _: (_ for _ in ()).throw(
                    OSError(errno.EIO, "synthetic fsync secondary")
                ),
            )
            with pytest.raises(RuntimeError, match="SYNTHETIC_NATIVE_CLOSE_PRIMARY"):
                writer.close()
        assert writer.failed and writer._physical.failed
        assert writer._physical.closed and writer._physical.fd is None


def test_sink_checks_cumulative_deadline_before_write_and_closes_fd(tmp_path):
    tmp_path.chmod(0o700)
    expired = False

    def check():
        if expired:
            raise contract.Stage12Error("B2_RUNTIME_DEADLINE")

    controls = limits.Controls(selection(), check=check)
    with storage.allocation_controls(controls):
        sink = limits.PhysicalSink(tmp_path / "partial", 64, "PARQUET_FILE")
        expired = True
        with pytest.raises(contract.Stage12Error, match="RUNTIME_DEADLINE"):
            sink.write(b"no write after expiry")
        assert sink.failed
        with pytest.raises(contract.Stage12Error, match="RUNTIME_DEADLINE"):
            sink.close()
        assert sink.closed and sink.fd is None
        assert (tmp_path / "partial").read_bytes() == b""
        assert controls.python_bytes == 64


def test_raw_pack_primary_survives_uncertain_cleanup(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    first = b"one invented public response"
    second = bytes(range(256)) * 8
    first_frame = response.compress(first)
    assert len(response.compress(second)) > len(first_frame)
    for name, payload in (("first.zst", first), ("second.zst", second)):
        storage.write(tmp_path / name, response.compress(payload))
    value = selection(max_compressed_frame_bytes=len(first_frame))
    controls = limits.Controls(value)

    def fragments():
        yield b"1" * 32, tmp_path / "first.zst", len(first), b.sha(first)
        monkeypatch.setattr(
            limits.os,
            "fsync",
            lambda _: (_ for _ in ()).throw(
                OSError(errno.EIO, "synthetic pack cleanup secondary")
            ),
        )
        yield b"2" * 32, tmp_path / "second.zst", len(second), b.sha(second)

    with storage.allocation_controls(controls):
        with pytest.raises(contract.Stage12Error, match="COMPRESSED_FRAME_LIMIT"):
            list(packs.pack(tmp_path / "packs", fragments()))
    assert controls.counts["RAW_PACK_FILE"] == 1
    assert not list((tmp_path / "packs").glob("*/_SEALED"))


def test_canonical_event_admin_and_control_roles_remain_distinct(tmp_path):
    tmp_path.chmod(0o700)
    (tmp_path / "events").mkdir(mode=0o700)
    controls = limits.Controls(selection())
    with storage.allocation_controls(controls):
        storage.write(tmp_path / "events/00000000000000000001.json", b"{}\n")
        storage.write(tmp_path / "admin_00000000000000000001_begin.json", b"{}\n")
        limits.claim("CONTROL_BEGIN")
        limits.claim("CONTROL_FINISH")
        assert controls.counts["EVENT_FILE"] == controls.counts["ADMIN_FILE"] == 1
        assert controls.counts["EXCLUSIVE_FILE"] == 0
        assert (
            controls.counts["CONTROL_BEGIN"] == controls.counts["CONTROL_FINISH"] == 1
        )


def test_sqlite_selected_main_limit_and_surplus_invocation(tmp_path):
    tmp_path.chmod(0o700)
    value = selection(sqlite_main_bytes=65536)
    value["invocations"]["SQLITE"] = 1
    controls = limits.Controls(value)
    path = tmp_path / "index.sqlite"
    with storage.allocation_controls(controls):
        db = catalog.connect(path)
        assert db.execute("pragma max_page_count").fetchone()[0] * 4096 == 65536
        assert limits.sqlite_cap(db, 2**20) == 65536
        db.execute("create table data(value blob)")
        with pytest.raises(sqlite3.OperationalError, match="full"):
            db.execute("insert into data values(?)", (b"x" * 65536,))
        db.close()
        assert path.stat().st_size <= 65536
        with pytest.raises(contract.Stage12Error, match="INVOCATION_BUDGET"):
            catalog.connect(tmp_path / "surplus.sqlite")
        assert not (tmp_path / "surplus.sqlite").exists()


def test_duckdb_selected_spill_and_surplus_invocation(tmp_path):
    tmp_path.chmod(0o700)
    value = selection()
    value["invocations"]["DUCKDB"] = 1
    controls = limits.Controls(value)
    root = tmp_path / "duck"
    root.mkdir(mode=0o700)
    with storage.allocation_controls(controls):
        db = limits.duck_connect(upstream.connect, root, memory="64MB", threads=1)
        assert (
            db.execute("select current_setting('max_temp_directory_size')").fetchone()[
                0
            ]
            == "8.0 MiB"
        )
        assert db.execute("select 42").fetchone() == (42,)
        db.close()
        with pytest.raises(contract.Stage12Error, match="INVOCATION_BUDGET"):
            limits.duck_connect(upstream.connect, tmp_path / "surplus")
        assert not (tmp_path / "surplus").exists()


def test_selected_scope_inherited_by_actual_single_writer(tmp_path):
    tmp_path.chmod(0o700)
    controls = limits.Controls(selection())
    with storage.allocation_controls(controls):
        writer = journal.Writer(tmp_path / "writer", 1, 1000, lambda: None)
        writer.call(lambda: storage.write(writer.root / "inside.json", b"{}\n"))
        writer.release({"scope": "SYNTHETIC_TEST_ONLY"})
    assert controls.counts["EXCLUSIVE_FILE"] >= 3
    assert storage.current_allocation_controls() is None


def test_selected_actual_b2_capture_publication_and_reopening(tmp_path):
    world = World(tmp_path)
    controls = limits.Controls(selection())
    with storage.allocation_controls(controls):
        report, inputs = world.run()
        assert report["disposition"] == "COMPLETED"
        expected, validate, _ = publish_world(
            world, inputs, tmp_path / "segment", tmp_path / "published"
        )
        reopened = validate()
        assert reopened["completed"] == reopened["planned"] == 2
        assert b.sha(storage.read(tmp_path / "published/manifest.json")) == expected
        assert (tmp_path / "published/_COMMITTED").exists()
        assert controls.counts["COMPRESSED_FRAME"] == 4
        assert controls.counts["CANDIDATE_BUFFER"] == 2
        assert controls.counts["PARQUET_FILE"] > 0
        assert controls.counts["RAW_PACK_FILE"] == 1
        assert controls.counts["SQLITE"] > 0 and controls.counts["DUCKDB"] > 0
        assert controls.counts["EVENT_FILE"] > 0
        assert controls.counts["PREFIX_FILE"] > 0
        controls.persist_usage(tmp_path / "usage.json")
    usage = storage.metadata(storage.read(tmp_path / "usage.json"))
    assert usage["python_reserved_bytes"] == controls.python_bytes
    assert usage["native_aggregate_prewrite_bound"] == "EXTERNAL_EVIDENCE_REQUIRED"


def test_legacy_scope_does_not_install_or_use_selected_controls(tmp_path):
    tmp_path.chmod(0o700)
    assert storage.current_allocation_controls() is None
    storage.write(tmp_path / "legacy", b"unchanged")
    assert limits.relation_writer is not None
    assert (
        limits.compressed(b"x", lambda _: b"unrestricted old bytes")
        == b"unrestricted old bytes"
    )
    writer = limits.relation_writer(
        tmp_path / "legacy_parquet", pa.schema([("x", pa.int64())])
    )
    assert type(writer) is upstream.RelationWriter
    writer.append({"x": 1})
    writer.close()


def test_limits_bind_real_runtime_command_and_lifetime(tmp_path):
    """Invented model/authority only; real port binding and phase entrypoint."""
    world = World(tmp_path)
    config, gate, grants = configuration(world)
    retained = resource_model()
    retained["limits"]["sqlite_invocations"] = 20
    target = next(x for x in retained["commands"] if x["phase"] == "plan-calibration")
    retained["commands"] = [
        target,
        *(x for x in retained["commands"] if x is not target),
    ]
    for ordinal, command in enumerate(retained["commands"], 1):
        command["command_id"] = ordinal
    for component in retained["components"]:
        component["count_bound"] = retained["limits"][
            resources.COUNTS[component["component_id"]]
        ]
        component["max_simultaneous_instances"] = component["count_bound"]
        if component["component_id"] in ("SQLITE_INDEX", "SQLITE_JOURNAL"):
            component["per_instance_bytes_bound"] = 65536
    for command in retained["commands"]:
        command["max_memory_bytes"] = config["runtime"]["phase_memory_bytes"]
        command["allocations"] = {
            component["component_id"]: (
                1
                if resources.COUNTS[component["component_id"]] == "commands"
                else component["count_bound"]
                if command is target
                else 0
            )
            for component in retained["components"]
        }
        amounts = [
            resources.component_bytes(
                {
                    **component,
                    "count_bound": command["allocations"][component["component_id"]],
                },
                retained,
            )
            for component in retained["components"]
        ]
        command["max_generated_bytes"] = sum(x[0] for x in amounts)
        command["max_generated_inodes"] = sum(x[1] for x in amounts)
    amounts = [resources.component_bytes(x, retained) for x in retained["components"]]
    for name, index in (
        ("physical_peak_bound_bytes", 0),
        ("physical_inode_bound", 1),
        ("retained_payload_bound_bytes", 2),
    ):
        retained[name] = sum(x[index] for x in amounts)
    retained["capacity_bytes"] = retained["physical_peak_bound_bytes"]
    retained["capacity_inodes"] = retained["physical_inode_bound"]
    retained["source_inventory_sha256"] = b.digest(config["runtime"]["source_files"])
    inventory = runtime.RuntimePort._actual_runtime_inventory(
        SimpleNamespace(population_scope=b.SYNTHETIC, settings=config["runtime"])
    )
    retained["runtime_inventory_sha256"] = b.digest(inventory)
    target["scope_sha256"] = resources.command_scope(config)
    resources.validate_model(retained)
    model_hash = world.put(retained)
    value = selection(
        model_sha256=model_hash,
        command_id=target["command_id"],
        sqlite_main_bytes=65536,
        max_python_write_bytes=2**20,
    )
    value["invocations"] = dict.fromkeys(limits.ROLES, 0)
    value["invocations"].update(SQLITE=20, EXCLUSIVE_FILE=20, PREFIX_FILE=2)
    limits.validate_binding(value, retained, target)
    for change in (
        dict(command_id=999),
        dict(model_sha256="f" * 64),
        dict(native_bound_evidence_sha256="f" * 64),
        dict(max_python_write_bytes=2**63),
    ):
        with pytest.raises(contract.Stage12Error, match="LIMIT_BINDING"):
            limits.validate_binding({**value, **change}, retained, target)
    selected_hash = world.put(value)
    config["runtime"]["resource_retention"] = {
        "model_sha256": model_hash,
        "command_id": target["command_id"],
        "allocation_limits_sha256": selected_hash,
    }
    for field in (
        "review_sha256",
        "retry_state_proof_sha256",
        "capacity_record_sha256",
        "capacity_owner_authority_sha256",
        "filesystem_accounting_sha256",
        "codec_inventory_sha256",
        "encoding_inventory_sha256",
    ):
        grants.require(
            "resource_retention_" + field.removesuffix("_sha256"), H, retained
        )
    for item in (*retained["components"], *retained["commands"]):
        grants.require(
            "resource_retention_bound",
            item.get("evidence_sha256", item.get("bound_evidence_sha256")),
            item,
        )
    grants.require("resource_retention", model_hash, retained)
    grants.require("resource_retention_allocation_limits", selected_hash, value)
    prep_grants(world, config, gate, grants)
    pin(world, config, grants)
    candidate = port(world, config)
    result = cli.execute(
        "plan-calibration",
        cli.Session(
            candidate,
            config,
            tmp_path / "unused_output",
            tmp_path / "selected.sqlite",
            H,
        ),
    )
    assert result["scientific_N_selected"] is False
    assert candidate._closed
    assert candidate.allocation_limits.value == value
    usage = storage.metadata(
        storage.read(tmp_path / "temporary_plan-calibration/allocation_usage.json")
    )
    assert usage["invocations"]["SQLITE"] >= 2
    assert usage["selection_sha256"] == selected_hash
    assert storage.current_allocation_controls() is None
