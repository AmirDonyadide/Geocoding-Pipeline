"""Local, bounded supplementary-checkpoint tests; no service adapters or keys."""

import errno
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest


MODULE = (
    Path(__file__).resolve().parents[1] / "scripts/stage12_diagnostic_checkpoints.py"
)
SPEC = importlib.util.spec_from_file_location("diagnostic_checkpoints", MODULE)
cp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cp)


def row(n=1):
    return [
        "size40_deep",
        "COMPARISON_STORAGE_AND_SOURCE_SETUP",
        None,
        n,
        n + 1,
        n + 2,
        n + 3,
        n + 4,
        None,
    ]


def test_private_canonical_chain_watermarks_and_final_marker(tmp_path):
    charges = []
    writer = cp.Checkpoints(
        tmp_path / "checkpoints", budget_charge=charges.append, interval_seconds=60
    )
    writer.set_phase("size40_deep", "COMPARISON_STORAGE_AND_SOURCE_SETUP")
    writer.record(row())
    writer.flush(timeout=2)
    prefix = cp.read_prefix(writer.root)
    assert prefix["verified_files"] == 1
    assert prefix["incomplete"] and prefix["reason"] == "NO_FINAL_CHECKPOINT"
    writer.record(row(10))
    writer.close(timeout=2)
    prefix = cp.read_prefix(writer.root)
    assert not prefix["incomplete"]
    assert prefix["verified_rows"] == 2 and prefix["last_watermark"] == 2
    assert prefix["sampling_coverage_proof"] is False
    assert sum(charges) == sum(p.stat().st_size for p in writer.root.iterdir())
    assert writer.snapshot()["reserved_bytes"] == sum(charges)
    assert writer.root.stat().st_mode & 0o777 == 0o700
    for file in writer.root.iterdir():
        assert file.stat().st_mode & 0o777 == 0o600


def test_ring_and_chunk_loss_explicit_and_bounded(tmp_path):
    writer = cp.Checkpoints(
        tmp_path / "checkpoints", ring_size=4, chunk_records=2, interval_seconds=60
    )
    for n in range(10):
        writer.record(row(n))
    writer.close(timeout=2)
    prefix = cp.read_prefix(writer.root)
    assert prefix["incomplete"] and prefix["reason"] == "TELEMETRY_TRUNCATED"
    assert prefix["verified_rows"] == 2
    assert prefix["last_watermark"] == 10
    assert prefix["dropped_unpersisted_rows"] == 8
    assert prefix["last_payload"]["ring_evictions"] == 6
    assert [pair[0] for pair in prefix["last_payload"]["records"]] == [9, 10]
    assert writer.snapshot()["buffered_rows"] == 4


def test_small_byte_limit_truncates_only_supplementary_rows(tmp_path):
    writer = cp.Checkpoints(
        tmp_path / "checkpoints", max_bytes=1024, interval_seconds=60
    )
    for n in range(128):
        writer.record(row(10**18 + n))
    writer.close(timeout=2)
    prefix = cp.read_prefix(writer.root, max_bytes=1024)
    assert prefix["incomplete"] and prefix["reason"] == "TELEMETRY_TRUNCATED"
    assert prefix["last_watermark"] == 128
    assert prefix["dropped_unpersisted_rows"] > 0
    assert prefix["verified_rows"] + prefix["dropped_unpersisted_rows"] == 128
    assert all(p.stat().st_size <= 1024 for p in writer.root.iterdir())


def test_periodic_checkpoint_survives_without_finally(tmp_path):
    writer = cp.Checkpoints(tmp_path / "checkpoints", interval_seconds=0.02)
    writer.record(row())
    deadline = time.monotonic() + 2
    while writer.snapshot()["persisted_watermark"] != 1:
        assert time.monotonic() < deadline
        time.sleep(0.005)
    writer.close(timeout=2)
    assert not cp.read_prefix(writer.root)["incomplete"]


@pytest.mark.parametrize("termination", ["os._exit(23)", "raise KeyboardInterrupt"])
def test_child_hard_exit_or_interruption_preserves_flushed_prefix(
    tmp_path, termination
):
    root = tmp_path / "checkpoints"
    code = f"""
import importlib.util, os, socket
def deny(*args, **kwargs): raise AssertionError('OFFLINE_DENIED')
socket.socket = socket.getaddrinfo = deny
spec=importlib.util.spec_from_file_location('cp', {str(MODULE)!r})
cp=importlib.util.module_from_spec(spec); spec.loader.exec_module(cp)
writer=cp.Checkpoints({str(root)!r}, interval_seconds=60)
writer.record({row()!r}); writer.flush(timeout=2)
writer.record({row(20)!r})
{termination}
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, timeout=5
    )
    assert result.returncode != 0
    prefix = cp.read_prefix(root)
    assert prefix["verified_files"] == 1 and prefix["verified_rows"] == 1
    assert prefix["incomplete"] and prefix["last_payload"]["final"] is False


@pytest.mark.parametrize("partial_next", [False, True])
def test_real_hard_exit_preserves_periodic_prefix_and_marks_partial_tail(
    tmp_path, partial_next
):
    root = tmp_path / "checkpoints"
    code = f"""
import importlib.util, os, socket, time
def deny(*args, **kwargs): raise AssertionError('OFFLINE_DENIED')
socket.socket = socket.getaddrinfo = deny
spec=importlib.util.spec_from_file_location('cp', {str(MODULE)!r})
cp=importlib.util.module_from_spec(spec); spec.loader.exec_module(cp)
writer=cp.Checkpoints({str(root)!r}, interval_seconds=0.02)
writer.record({row()!r})
deadline=time.monotonic()+2
while writer.snapshot()['persisted_watermark'] != 1:
    if time.monotonic() > deadline: os._exit(98)
    time.sleep(0.001)
if {partial_next!r}:
    original=cp.os.write
    def partial(fd, data):
        original(fd, data[:17]); os._exit(23)
    cp.os.write=partial
    writer.record({row(20)!r}); writer.flush(timeout=2)
os._exit(23)
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, timeout=5
    )
    assert result.returncode == 23
    prefix = cp.read_prefix(root)
    assert prefix["incomplete"] and prefix["verified_files"] >= 1
    assert prefix["last_watermark"] == 1
    if partial_next:
        assert prefix["reason"] == "CHECKPOINT_PREFIX_INVALID"
        filename = root / f"chunk{prefix['verified_files'] + 1:06d}.json"
        assert filename.stat().st_size == 17
    else:
        assert prefix["reason"] == "NO_FINAL_CHECKPOINT"


def test_record_does_not_wait_for_writer_io_or_serialization(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = cp.Checkpoints._persist

    def blocked(self, raw, index):
        entered.set()
        assert release.wait(2)
        return original(self, raw, index)

    monkeypatch.setattr(cp.Checkpoints, "_persist", blocked)
    writer = cp.Checkpoints(tmp_path / "checkpoints", interval_seconds=0.02)
    writer.record(row())
    assert entered.wait(2)
    begin = time.monotonic()
    writer.record(row(10))
    assert time.monotonic() - begin < 0.1
    release.set()
    writer.close(timeout=2)
    assert cp.read_prefix(writer.root)["last_watermark"] == 2


def test_partial_disk_full_preserved_and_no_refund_or_retry(tmp_path, monkeypatch):
    charges = []
    writer = cp.Checkpoints(
        tmp_path / "checkpoints", budget_charge=charges.append, interval_seconds=60
    )
    writer.record(row())
    writer.flush(timeout=2)
    original = cp.os.write
    count = 0

    def disk_full(fd, raw):
        nonlocal count
        count += 1
        if count == 1:
            return original(fd, raw[:17])
        raise OSError(errno.ENOSPC, "unsafe secret must not be copied")

    monkeypatch.setattr(cp.os, "write", disk_full)
    writer.record(row(20))
    with pytest.raises(cp.CheckpointError, match="^CHECKPOINT_PERSISTENCE_FAILED$"):
        writer.flush(timeout=2)
    assert len(charges) == 2
    assert (writer.root / "chunk000002.json").stat().st_size == 17
    prefix = cp.read_prefix(writer.root)
    assert prefix["incomplete"] and prefix["verified_files"] == 1
    assert prefix["reason"] == "CHECKPOINT_PREFIX_INVALID"
    assert writer.snapshot()["reserved_files"] == 2
    assert writer.snapshot()["persisted_files"] == 1
    with pytest.raises(cp.CheckpointError):
        writer.close(timeout=2)
    assert count == 2


def test_budget_precharge_before_open_and_file_limit(tmp_path):
    def exhausted(_):
        raise RuntimeError("private error must not appear")

    writer = cp.Checkpoints(
        tmp_path / "exhausted", budget_charge=exhausted, interval_seconds=60
    )
    with pytest.raises(cp.CheckpointError, match="^CHECKPOINT_PERSISTENCE_FAILED$"):
        writer.flush(timeout=2)
    assert list(writer.root.iterdir()) == []
    writer = cp.Checkpoints(tmp_path / "file_limit", max_files=1, interval_seconds=60)
    writer.flush(timeout=2)
    with pytest.raises(cp.CheckpointError, match="^CHECKPOINT_FILE_LIMIT$"):
        writer.close(timeout=2)
    assert len(list(writer.root.iterdir())) == 1
    assert cp.read_prefix(writer.root)["incomplete"]


@pytest.mark.parametrize("change", ["tamper", "extra", "missing", "symlink", "mode"])
def test_reader_rejects_tampering_and_membership_changes(tmp_path, change):
    writer = cp.Checkpoints(tmp_path / "checkpoints", interval_seconds=60)
    writer.record(row())
    writer.flush(timeout=2)
    writer.close(timeout=2)
    first = writer.root / "chunk000001.json"
    if change == "tamper":
        payload = json.loads(first.read_bytes())
        payload["watermark"] = 99
        first.write_bytes(cp._canonical(payload))
    elif change == "extra":
        (writer.root / "extra.json").write_text("{}")
    elif change == "missing":
        first.unlink()
    elif change == "symlink":
        first.unlink()
        first.symlink_to(writer.root / "chunk000002.json")
    elif change == "mode":
        first.chmod(0o644)
    assert cp.read_prefix(writer.root)["incomplete"]


def test_schema_rejects_unsafe_rows_and_unbounded_selections(tmp_path):
    writer = cp.Checkpoints(tmp_path / "checkpoints", interval_seconds=60)
    for value in (
        ["query with spaces"] + row()[1:],
        row()[:-1],
        row()[:2] + [True] * 7,
    ):
        with pytest.raises(cp.CheckpointError):
            writer.record(value)
    writer.close(timeout=2)
    for kwargs in (
        {"max_files": 1501},
        {"ring_size": 4097},
        {"max_bytes": 32769},
        {"interval_seconds": float("nan")},
    ):
        with pytest.raises(cp.CheckpointError):
            cp.Checkpoints(tmp_path / "invalid", **kwargs)


def test_reader_bounds_and_within_chunk_missing_ordinal_rejected(tmp_path):
    writer = cp.Checkpoints(tmp_path / "checkpoints", interval_seconds=60)
    for n in range(3):
        writer.record(row(n))
    writer.close(timeout=2)
    assert (
        cp.read_prefix(writer.root, max_files=1501)["reason"]
        == "CHECKPOINT_LIMIT_INVALID"
    )
    assert (
        cp.read_prefix(writer.root, max_bytes=32769)["reason"]
        == "CHECKPOINT_LIMIT_INVALID"
    )
    filename = writer.root / "chunk000001.json"
    payload = json.loads(filename.read_bytes())
    payload["records"][0][0] = 0
    filename.write_bytes(cp._canonical(payload))
    assert cp.read_prefix(writer.root)["reason"] == "CHECKPOINT_RECORD_ORDER_INVALID"


def test_untrusted_exception_cannot_become_persisted_failure_code(tmp_path):
    def exhausted(_):
        raise cp.CheckpointError("PRIVATE_SECRET_EXCEPTION")

    writer = cp.Checkpoints(
        tmp_path / "checkpoints", budget_charge=exhausted, interval_seconds=60
    )
    with pytest.raises(cp.CheckpointError, match="^CHECKPOINT_PERSISTENCE_FAILED$"):
        writer.flush(timeout=2)
    assert "PRIVATE" not in repr(writer.snapshot())


def test_serialization_is_also_outside_ring_lock(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = cp._canonical

    def blocked(payload):
        entered.set()
        assert release.wait(2)
        return original(payload)

    from safe_geocoding_pipeline.preprocessing.stages import s12_public_checkpoints

    monkeypatch.setattr(s12_public_checkpoints, "_canonical", blocked)
    writer = cp.Checkpoints(tmp_path / "checkpoints", interval_seconds=0.02)
    writer.record(row())
    assert entered.wait(2)
    begin = time.monotonic()
    writer.record(row(10))
    assert time.monotonic() - begin < 0.1
    release.set()
    writer.close(timeout=2)
    assert cp.read_prefix(writer.root)["last_watermark"] == 2


def test_public_lossless_checkpoint_survives_hard_exit_without_final_claim(tmp_path):
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_checkpoints as cp,
    )
    import subprocess
    import sys

    root = tmp_path / "hard-exit"
    code = f"""
import os, socket, time
from safe_geocoding_pipeline.preprocessing.stages import s12_public_checkpoints as cp
def denied(*a, **k): raise AssertionError('OFFLINE_DENIED')
socket.socket = socket.getaddrinfo = denied
writer=cp.Checkpoints({str(root)!r}, row_schema=cp.PUBLIC_SCHEMA, interval_seconds=.02)
writer.record([1, 'PERIODIC', 'UNCERTAIN', 1, 2] + [9876543210000000 + n for n in range(22)])
deadline=time.monotonic()+2
while writer.snapshot()['persisted_watermark'] != 1:
    if time.monotonic()>deadline: os._exit(98)
    time.sleep(.001)
os._exit(23)
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, timeout=5
    )
    assert result.returncode == 23
    actual = []
    prefix = cp.read_prefix(root, record_consumer=lambda n, row: actual.append(row))
    assert prefix["incomplete"] and prefix["reason"] == "NO_FINAL_CHECKPOINT"
    assert prefix["last_watermark"] == 1
    assert actual[0][5:] == tuple(9876543210000000 + n for n in range(22))
    assert prefix["sampling_coverage_proof"] is False


def test_legacy_standalone_import_before_src_is_available(tmp_path):
    root = tmp_path / "standalone"
    code = f"""
import importlib.util, socket
def deny(*a, **k): raise AssertionError('OFFLINE_DENIED')
socket.socket = socket.getaddrinfo = deny
spec=importlib.util.spec_from_file_location('cp', {str(MODULE)!r})
cp=importlib.util.module_from_spec(spec); spec.loader.exec_module(cp)
writer=cp.Checkpoints({str(root)!r}, interval_seconds=60)
writer.record({row()!r}); writer.close(timeout=2)
assert not cp.read_prefix(writer.root)['incomplete']
"""
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-c", code], capture_output=True, timeout=5
    )
    assert result.returncode == 0, result.stderr
