"""Bounded AP representations and exact canonical evidence; no service access."""

import json
import threading
import time

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_public_bounded as b
from safe_geocoding_pipeline.preprocessing.stages import s12_public_checkpoints as cp
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_public_sampling_contract as a,
)
from test_stage12_public_operations_v2 import offline  # noqa: F401


def timing_row(n=1, maximum=False):
    row = {k: None for k in a.ASYNC_FIELDS}
    row.update(
        row_kind="PERIODIC_ASYNC",
        phase_id=1,
        segment_id=1,
        epoch_id="a" * 64,
        acquisition_seq=n,
        role="REGULAR",
        future_used=False,
        outcome="FAILED",
        acquire_enter_ns=0,
        reserved_ns=0,
    )
    if maximum:
        row.update({key: b.UINT64 for key in b.NUMBERS})
        row.update({key: "f" * 64 for key in b.HASHES})
        row["future_finished_observed_ns"] = None
        row["outcome"] = "COMPLETE"
    return row


@pytest.mark.parametrize(
    "row",
    [
        timing_row(),
        timing_row(maximum=True),
        {
            "row_kind": "HARD_SYNC",
            "legacy_row": [b.UINT64, "START_RESERVE", "UNCERTAIN"]
            + [None, b.UINT64] * 12,
        },
    ],
)
def test_packed_rows_are_exact_private_and_fixed(row):
    expected = json.loads(json.dumps(row))
    raw = b.pack_timing(row)
    assert len(raw) == b.PACKED_ROW_BYTES == 512
    assert b.unpack_timing(raw) == expected
    if row["row_kind"] == "HARD_SYNC":
        row["legacy_row"][0] = 1
    else:
        row["acquisition_seq"] = 7
    assert b.unpack_timing(raw) == expected


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        False,
        b.UINT64,
        {"z": '\0\b\f\n\r\t"\\\x7fé𝄞\ud800', "a": [0, None, True]},
        {"é": "中" * 2000},
    ],
)
def test_canonical_bytes_and_exact_size_boundaries(value):
    raw = cp._canonical(value)
    assert b.canonical(value, len(raw)) == raw
    b.canonical_match(value, raw)
    with pytest.raises(b.EncodingLimit):
        b.canonical_match(value, raw + b" ")
    with pytest.raises(b.EncodingLimit):
        b.canonical(value, len(raw) - 1)
    counter = b.Canonical(len(raw), count_only=True)
    counter.value(value)
    counter.put(b"\n")
    assert counter.pos == len(raw) and counter.buffer is None


def test_ring_has_fixed_backing_and_evictions_are_not_hidden():
    ring = b.TimingRing(16)
    for n in range(1, 18):
        ring.append((n, b.pack_timing(timing_row(n))))
    assert len(ring.backing) == 16 * 512
    assert len(ring) == 16 and ring.get(1) is None
    assert b.unpack_timing(ring.get(17))["acquisition_seq"] == 17


def test_ap_full_retention_no_oversized_candidate_and_exact_reopen(
    tmp_path, monkeypatch
):
    seen = []
    original = cp._canonical

    def no_ap_candidate(value):
        assert not (type(value) is dict and value.get("schema") == cp.AP_SCHEMA)
        return original(value)

    monkeypatch.setattr(cp, "_canonical", no_ap_candidate)
    writer = cp.Checkpoints(
        tmp_path / "rows", row_schema=cp.AP_SCHEMA, interval_seconds=60
    )
    for n in range(1, 4097):
        writer.record(timing_row(n))
    assert len(writer._rows.backing) == 4096 * 512
    writer.close(timeout=10)
    result = cp.read_prefix(
        writer.root,
        record_consumer=lambda n, row: seen.append((n, row["acquisition_seq"])),
    )
    assert not result["incomplete"] and result["verified_rows"] == 4096
    assert seen == [(n, n) for n in range(1, 4097)]
    assert writer.snapshot()["dropped_unpersisted_rows"] == 0
    assert max(p.stat().st_size for p in writer.root.iterdir()) <= 32768


def test_ap_byte_limit_concurrent_eviction_watermarks_and_partial_failure(
    tmp_path, monkeypatch
):
    writer = cp.Checkpoints(
        tmp_path / "rows",
        row_schema=cp.AP_SCHEMA,
        ring_size=4,
        max_bytes=2048,
        interval_seconds=60,
    )
    for n in range(1, 8):
        writer.record(timing_row(n))
    writer.close(timeout=5)
    reopened = cp.read_prefix(writer.root)
    assert reopened["reason"] == "TELEMETRY_TRUNCATED"
    assert reopened["dropped_unpersisted_rows"] == 3
    assert reopened["last_watermark"] == 7

    partial = cp.Checkpoints(
        tmp_path / "partial", row_schema=cp.AP_SCHEMA, interval_seconds=60
    )
    write = cp.os.write
    calls = [0]

    def fail(fd, raw):
        calls[0] += 1
        if calls[0] == 1:
            return write(fd, raw[:8])
        raise OSError(28, "synthetic")

    monkeypatch.setattr(cp.os, "write", fail)
    partial.record(timing_row())
    with pytest.raises(cp.CheckpointError):
        partial.close(timeout=5)
    assert partial.snapshot()["persistence_uncertain"]
    assert partial.snapshot()["persisted_watermark"] == 0
    assert (partial.root / "chunk000001.json").stat().st_size == 8
    assert cp.read_prefix(partial.root)["incomplete"]


def test_ap_serialization_never_holds_producer_lock(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = b.unpack_timing

    def blocked(raw):
        entered.set()
        assert release.wait(2)
        return original(raw)

    monkeypatch.setattr(b, "unpack_timing", blocked)
    writer = cp.Checkpoints(
        tmp_path / "rows", row_schema=cp.AP_SCHEMA, interval_seconds=0.01
    )
    writer.record(timing_row(1))
    assert entered.wait(2)
    t = threading.Thread(target=lambda: writer.record(timing_row(2)))
    t.start()
    t.join(0.2)
    assert not t.is_alive()
    release.set()
    writer.close(timeout=5)
    assert cp.read_prefix(writer.root)["last_watermark"] == 2


def test_ap_timer_drains_byte_split_backlog_before_next_idle_interval(tmp_path):
    entered, release = threading.Event(), threading.Event()
    writer = cp.Checkpoints(
        tmp_path / "drain", row_schema=cp.AP_SCHEMA, interval_seconds=0.02
    )
    original = writer._persist
    calls = [0]

    def persist(raw, index):
        calls[0] += 1
        if calls[0] == 1:
            entered.set()
            assert release.wait(2)
            writer._interval = 1000
        original(raw, index)

    writer._persist = persist
    for n in range(1, 129):
        writer.record(timing_row(n))
    assert entered.wait(2)
    release.set()
    end = time.monotonic() + 2
    try:
        while writer.snapshot()["persisted_watermark"] < 128 and time.monotonic() < end:
            time.sleep(0.001)
        assert writer.snapshot()["persisted_watermark"] == 128
        assert calls[0] > 1
    finally:
        writer.close(timeout=5)
