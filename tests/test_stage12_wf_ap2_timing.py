"""T3 bounded synthetic wire/lifecycle/failure tests; no live authority."""

import errno
import json
from pathlib import Path
import threading
import time

import pytest

from test_stage12_public_operations_v2 import FakeClock, H, offline  # noqa: F401
from safe_geocoding_pipeline.preprocessing.stages import s12_public_bounded as b
from safe_geocoding_pipeline.preprocessing.stages import s12_public_checkpoints as cp
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_public_sampling_contract as ap,
)
from safe_geocoding_pipeline.preprocessing.stages import s12_public_timing as timing
from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_timing as t


BINDING = dict(policy_sha256=H, source_sha256=H, task_sha256=H)


def row(number=1, *, nullable=False, hard=False):
    if hard:
        values = [1, "START_RESERVE", "UNCERTAIN" if nullable else "COMPLETE"] + [
            number
        ] * 24
        values[25] = None
        if nullable:
            values[3:] = [None] * 24
        return dict(row_kind="HARD_SYNC", legacy_row=values)
    value = {}
    for key, kind in ap.ASYNC_FIELDS.items():
        if nullable and kind.endswith("?"):
            value[key] = None
        elif kind.rstrip("?") in ("P", "ID", "U"):
            value[key] = number
        elif kind.rstrip("?") in ("D", "N32"):
            value[key] = H
    value.update(
        row_kind="PERIODIC_ASYNC",
        role="REGULAR",
        future_used=not nullable,
        outcome="UNCERTAIN" if nullable else "COMPLETE",
        phase_id=1,
    )
    return value


def writer(tmp_path, *, clock=None, **kwargs):
    clock = clock or FakeClock()
    return t.Checkpoints(
        tmp_path / "timing",
        timing_binding=BINDING,
        phase_windows=[dict(phase_id=1, selected_phase_ms=20000)],
        cumulative_deadline_ns=100_000_000_000,
        clock_ns=clock.now_ns,
        **kwargs,
    ), clock


def opened(tmp_path, **kwargs):
    value, clock = writer(tmp_path, **kwargs)
    value.phase_open(1, timeout_seconds=2)
    return value, clock


def finish(value):
    value.phase_close(1, timeout_seconds=2)
    return value.close(timeout_seconds=2)


def prefix(value, **kwargs):
    return cp.read_prefix(
        value.root,
        expected_binding=BINDING,
        expected_snapshot=value.snapshot(),
        **kwargs,
    )


def wait_until(predicate):
    end = time.monotonic() + 2
    while not predicate():
        assert time.monotonic() < end
        time.sleep(0.001)


@pytest.mark.parametrize("hard", [False, True])
@pytest.mark.parametrize("nullable", [False, True])
def test_exact_512_roundtrip_maximum_numbers_nulls_and_tags(hard, nullable):
    original = row(b.UINT64, hard=hard, nullable=nullable)
    raw = t.encode_row(original)
    assert len(raw) == 512 and raw == b.pack_timing(original)
    assert t.decode_row(raw) == original
    assert t.encode_row(t.decode_row(raw)) == raw


@pytest.mark.parametrize(
    "index,value", [(0, 2), (1, 4), (2, 2), (3, 2), (4, 1), (511, 1), (15, 128)]
)
def test_unknown_tags_flags_masks_and_reserved_bytes_reject(index, value):
    raw = bytearray(t.encode_row(row()))
    raw[index] = value
    with pytest.raises(cp.CheckpointError, match="CHECKPOINT_ROW_INVALID"):
        t.decode_row(raw)


def test_noncanonical_null_payload_invalid_lengths_and_unicode_reject():
    raw = bytearray(t.encode_row(row(nullable=True)))
    raw[16 + 8 * b.NUMBERS.index("observed_ns")] = 1
    for candidate in (raw, raw[:-1], raw + b"\0"):
        with pytest.raises(cp.CheckpointError):
            t.decode_row(candidate)
    invalid = row()
    invalid["role"] = "نامعتبر"
    with pytest.raises(cp.CheckpointError):
        t.encode_row(invalid)


def test_full_rows_canonical_header_byte_bound_and_original_reader(tmp_path):
    value, _ = opened(tmp_path)
    expected = [row(n) for n in range(1, 114)]
    for item in expected:
        value.record(item)
    state = finish(value)
    sizes = [p.stat().st_size for p in sorted(value.root.iterdir())]
    assert sizes == [4096, 32768, 32768, 4608, 4096]
    actual = []
    report = prefix(value, record_consumer=lambda n, item: actual.append((n, item)))
    assert not report["incomplete"] and report["verified_rows"] == 113
    assert actual == list(enumerate(expected, 1))
    assert state["reserved_cuts"] == 3
    assert cp.read_prefix(value.root)["incomplete"]
    assert cp.read_prefix(value.root)["reason"] == "CHECKPOINT_ACK_UNVERIFIED"
    for file in value.root.iterdir():
        raw = file.read_bytes()
        header = t.decode_header(raw[:4096])
        assert len(raw) == 4096 + header["row_count"] * 512 <= 32768
        assert t.encode_header(header) == raw[:4096]
        reused = bytearray(b"\xff" * 4096)
        assert t.encode_header(header, reused) == raw[:4096]
        assert file.stat().st_mode & 0o777 == 0o600


def test_concurrent_arrivals_do_not_extend_cut_or_trigger_next_cut(
    tmp_path, monkeypatch
):
    value, clock = opened(tmp_path)
    for _ in range(112):
        value.record(row())
    entered, release = threading.Event(), threading.Event()
    original = value._persist

    def persist(raw, index):
        if index == 2:
            entered.set()
            assert release.wait(2)
        return original(raw, index)

    monkeypatch.setattr(value, "_persist", persist)
    clock.advance(t.TIMER_NS)
    with value._condition:
        value._condition.notify_all()
    assert entered.wait(2)
    for _ in range(10):
        value.record(row())
    release.set()
    wait_until(lambda: value.snapshot()["persisted_watermark"] == 112)
    assert value.snapshot()["persisted_files"] == 3
    assert value.snapshot()["buffered_rows"] == 10
    time.sleep(0.02)
    assert value.snapshot()["persisted_files"] == 3
    finish(value)
    assert prefix(value)["verified_rows"] == 122 and not prefix(value)["incomplete"]


def test_phase_gated_timer_setup_gaps_expiry_and_no_empty_idle(tmp_path):
    value, clock = writer(tmp_path)
    time.sleep(0.01)
    assert value.snapshot()["persisted_files"] == 0
    value.phase_open(1, timeout_seconds=2)
    clock.advance(t.TIMER_NS)
    with value._condition:
        value._condition.notify_all()
    wait_until(lambda: value.snapshot()["persisted_files"] == 2)
    value.phase_close(1, timeout_seconds=2)
    clock.advance(50_000_000_000)
    with value._condition:
        value._condition.notify_all()
    time.sleep(0.02)
    assert value.snapshot()["persisted_files"] == 3
    value.close(timeout_seconds=2)
    assert value.snapshot()["reserved_cuts"] == 4
    assert not prefix(value)["incomplete"]


def test_timer_stops_at_selected_end_without_catchup(tmp_path):
    value, clock = opened(tmp_path)
    clock.advance(20_000_000_000)
    with value._condition:
        value._condition.notify_all()
    time.sleep(0.02)
    assert value.snapshot()["persisted_files"] == 1
    finish(value)
    assert not prefix(value)["incomplete"]


@pytest.mark.parametrize("failure", ["overflow", "unquiescent", "late", "unclosed"])
def test_eviction_unresolved_and_late_rows_cannot_create_compliance(tmp_path, failure):
    value, clock = opened(tmp_path, ring_size=2)
    if failure == "overflow":
        for _ in range(5):
            value.record(row())
    else:
        value.record(row())
    if failure != "unclosed":
        value.phase_close(1, quiescent=failure != "unquiescent", timeout_seconds=2)
    if failure == "late":
        value.record(row())
    state = value.close(timeout_seconds=2)
    assert not state["final_coverage_complete"]
    assert prefix(value)["incomplete"]
    if failure == "overflow":
        assert state["dropped_unpersisted_rows"] == 3 and state["ring_evictions"] == 3
    else:
        assert state["uncertainty_count"] > 0


@pytest.mark.parametrize(
    "fault", ["partial", "fsync", "readback", "creation", "precharge"]
)
def test_persistence_failure_is_precharged_preserved_and_never_retried(
    tmp_path, monkeypatch, fault
):
    charges = []
    value, _ = opened(tmp_path, budget_charge=charges.append)
    value.record(row())
    original_write, count = t.os.write, 0

    def broken_write(fd, raw):
        nonlocal count
        count += 1
        if count == 1:
            return original_write(fd, raw[:17])
        raise OSError(errno.ENOSPC, "SYNTHETIC_PRIVATE_CANARY")

    if fault == "partial":
        monkeypatch.setattr(t.os, "write", broken_write)
    elif fault == "fsync":
        monkeypatch.setattr(
            t.os, "fsync", lambda *_: (_ for _ in ()).throw(OSError("CANARY"))
        )
    elif fault == "readback":
        monkeypatch.setattr(
            value,
            "_readback",
            lambda *_: (_ for _ in ()).throw(
                cp.CheckpointError("CHECKPOINT_READBACK_FAILED")
            ),
        )
    elif fault == "creation":
        (value.root / "chunk000002.bin").write_bytes(b"existing")
    else:
        value._charge = lambda n: (
            charges.append(n) or (_ for _ in ()).throw(OSError("CANARY"))
        )
    with pytest.raises(cp.CheckpointError):
        value.phase_close(1, timeout_seconds=2)
    state = value.snapshot()
    assert state["reserved_files"] == 2 and state["persisted_files"] == 1
    assert state["reserved_bytes"] == 4096 + 4608 and len(charges) == 2
    assert state["persistence_uncertain"] and not state["final_coverage_complete"]
    assert "CANARY" not in state["failure_code"]
    with pytest.raises(cp.CheckpointError):
        value.close(timeout_seconds=2)
    assert len(charges) == 2 and prefix(value)["incomplete"]
    if fault == "partial":
        assert (value.root / "chunk000002.bin").stat().st_size == 17


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "duplicate",
        "reordered_files",
        "reordered_rows",
        "trailing",
        "reserved",
        "hardlink",
        "binding",
    ],
)
def test_reopening_rejects_changed_exact_source_membership_order_and_bytes(
    tmp_path, mutation
):
    value, _ = opened(tmp_path)
    for n in range(1, 58):
        value.record(row(n))
    finish(value)
    files = sorted(value.root.iterdir())
    if mutation == "missing":
        files[1].unlink()
    elif mutation == "extra":
        (value.root / "unknown").write_bytes(b"x")
    elif mutation == "duplicate":
        (value.root / "chunk000099.bin").write_bytes(files[1].read_bytes())
    elif mutation == "reordered_files":
        a, z = files[1].read_bytes(), files[2].read_bytes()
        files[1].write_bytes(z)
        files[2].write_bytes(a)
    elif mutation == "reordered_rows":
        raw = bytearray(files[1].read_bytes())
        a, z = bytes(raw[4096:4608]), bytes(raw[4608:5120])
        raw[4096:4608], raw[4608:5120] = z, a
        files[1].write_bytes(raw)
    elif mutation == "trailing":
        with files[-1].open("ab") as stream:
            stream.write(b"x")
    elif mutation == "reserved":
        raw = bytearray(files[-1].read_bytes())
        raw[4095] = 1
        files[-1].write_bytes(raw)
    elif mutation == "hardlink":
        files[1].unlink()
        files[1].hardlink_to(files[0])
    else:
        wrong = {**BINDING, "source_sha256": "f" * 64}
        assert cp.read_prefix(
            value.root, expected_binding=wrong, expected_snapshot=value.snapshot()
        )["incomplete"]
        return
    assert prefix(value)["incomplete"]


def test_reader_reopens_originals_after_consumer_and_does_not_keep_history(tmp_path):
    value, _ = opened(tmp_path)
    value.record(row())
    finish(value)
    changed = False

    def consume(n, item):
        nonlocal changed
        if not changed:
            changed = True
            path = value.root / "chunk000001.bin"
            path.write_bytes(path.read_bytes())

    report = prefix(value, record_consumer=consume)
    assert report["incomplete"] and report["reason"] == "CHECKPOINT_FILE_CHANGED"


def test_observer_successor_is_explicit_and_legacy_ap_parser_remains(tmp_path):
    clock = FakeClock()
    observer = timing.SamplingTiming(
        tmp_path / "new",
        phase_count=1,
        timing_schema=cp.WF_SCHEMA,
        timing_binding=BINDING,
        phase_windows=[dict(phase_id=1, selected_phase_ms=20000)],
        cumulative_deadline_ns=100_000_000_000,
        clock_ns=clock.now_ns,
    )
    observer.phase_open(1, timeout_seconds=2)
    observer.periodic(row())
    observer.phase_close(1, timeout_seconds=2)
    result = observer.close(timeout_seconds=2)
    assert result["schema"] == "stage12_public_path_timing_summary_v3"
    assert result["persistence_complete"]
    assert not cp.read_prefix(
        observer.checkpoints.root,
        expected_binding=BINDING,
        expected_snapshot=result["checkpoint"],
    )["incomplete"]
    old = timing.SamplingTiming(tmp_path / "old", phase_count=1, interval_seconds=60)
    old.periodic(row())
    assert old.close()["persistence_complete"]
    assert not cp.read_prefix(old.checkpoints.root)["incomplete"]
    assert all(path.suffix == ".json" for path in old.checkpoints.root.iterdir())
    with pytest.raises(cp.CheckpointError):
        timing.PublicTiming(
            tmp_path / "wrong", phase_count=1, timing_schema=cp.WF_SCHEMA
        )
    with pytest.raises(cp.CheckpointError):
        timing.SamplingTiming(
            tmp_path / "wrong2", phase_count=1, timing_binding=BINDING
        )
    with pytest.raises(cp.CheckpointError):
        timing.SamplingTiming(
            tmp_path / "wrong3",
            phase_count=1,
            timing_schema=cp.WF_SCHEMA,
            timing_binding={**BINDING, "source_sha256": "0" * 64},
        )


def test_descriptor_is_exact_and_no_native_bound_is_claimed():
    root = Path(__file__).resolve().parents[1]
    descriptor = json.loads(
        (
            root / "docs/scientific_assets/stage12_public_path_timing_v3.json"
        ).read_bytes()
    )
    assert descriptor == t.descriptor()
    assert descriptor["accounting"]["maximum_files"] == 1500
    assert descriptor["accounting"]["summary_reserve_bytes"] == 2**20
    assert descriptor["accounting"]["native_component_bound_claim"] is False


def test_unselected_flush_cannot_create_an_extra_cut(tmp_path):
    value, _ = opened(tmp_path)
    count = value.snapshot()["reserved_cuts"]
    with pytest.raises(cp.CheckpointError, match="CHECKPOINT_CUT_INVALID"):
        value.flush()
    assert value.snapshot()["reserved_cuts"] == count
    finish(value)


def test_byte_valid_final_after_fsync_failure_requires_failed_original_disposition(
    tmp_path, monkeypatch
):
    value, _ = opened(tmp_path)
    value.record(row())
    value.phase_close(1, timeout_seconds=2)
    monkeypatch.setattr(
        t.os, "fsync", lambda *_: (_ for _ in ()).throw(OSError("PRIVATE"))
    )
    with pytest.raises(cp.CheckpointError):
        value.close(timeout_seconds=2)
    retained = cp.read_prefix(value.root)
    assert retained["last_payload"]["final"]
    assert retained["reason"] == "CHECKPOINT_ACK_UNVERIFIED" and retained["incomplete"]
    assert (
        prefix(value)["incomplete"] and not value.snapshot()["final_coverage_complete"]
    )


def test_wait_timeout_poison_cannot_ack_late_writer_completion(tmp_path, monkeypatch):
    value, _ = opened(tmp_path)
    value.record(row())
    entered, release = threading.Event(), threading.Event()
    original = value._persist

    def persist(raw, index):
        entered.set()
        assert release.wait(2)
        return original(raw, index)

    monkeypatch.setattr(value, "_persist", persist)
    try:
        with pytest.raises(cp.CheckpointError, match="CHECKPOINT_WAIT_EXPIRED"):
            value.phase_close(1, timeout_seconds=0.02)
        assert entered.is_set()
        before = value.snapshot()
        release.set()
        value._thread.join(2)
        after = value.snapshot()
        assert (
            after["failure_code"] == before["failure_code"] == "CHECKPOINT_WAIT_EXPIRED"
        )
        assert after["persisted_files"] == before["persisted_files"] == 1
        assert after["reserved_files"] == 2
        with pytest.raises(cp.CheckpointError):
            value.close(timeout_seconds=2)
    finally:
        release.set()
        value._thread.join(2)


def test_existing_cumulative_deadline_is_not_renewed_for_boundary_drain(tmp_path):
    value, clock = opened(tmp_path)
    clock.advance(100_000_000_000)
    with pytest.raises(cp.CheckpointError, match="CHECKPOINT_WAIT_EXPIRED"):
        value.phase_close(1, timeout_seconds=5)
    assert not value.snapshot()["final_coverage_complete"]
    assert value.snapshot()["failure_code"] == "CHECKPOINT_WAIT_EXPIRED"


def test_noncanonical_header_keys_padding_and_row_ordinals_reject(tmp_path):
    value, _ = opened(tmp_path)
    value.record(row())
    finish(value)
    raw = (value.root / "chunk000002.bin").read_bytes()
    header = t.decode_header(raw[:4096])
    for mutation in ("extra", "row_ordinal", "bad_bool", "policy"):
        changed = dict(header)
        if mutation == "extra":
            changed["unknown"] = None
        elif mutation == "row_ordinal":
            changed["first_row_ordinal"] += 1
        elif mutation == "bad_bool":
            changed["cut_complete"] = 1
        else:
            changed["policy_version"] = "stage12_public_sampling_policy_v1"
        with pytest.raises(cp.CheckpointError):
            t.decode_header(t.encode_header(changed))


def test_supplementary_reader_and_writer_share_one_timing_arena_lease(tmp_path):
    value, _ = opened(tmp_path)
    value.record(row())
    finish(value)
    nested = []

    def consumer(*_):
        try:
            prefix(value)
        except Exception as error:
            nested.append(error.args[0])

    assert not prefix(value, record_consumer=consumer)["incomplete"]
    assert nested == ["WF_AP2_SCRATCH_REENTRANT"]


def test_explicit_successor_binding_cannot_adopt_legacy_json_final(tmp_path):
    old = timing.SamplingTiming(tmp_path / "old", phase_count=1, interval_seconds=60)
    old.periodic(row())
    old.close()
    assert not cp.read_prefix(old.checkpoints.root)["incomplete"]
    assert cp.read_prefix(old.checkpoints.root, expected_binding=BINDING)["incomplete"]


def test_fresh_reader_rejects_symlink_parent_path(tmp_path):
    value, _ = opened(tmp_path)
    value.record(row())
    finish(value)
    alias = tmp_path / "alias"
    alias.symlink_to(value.root, target_is_directory=True)
    assert cp.read_prefix(
        alias, expected_binding=BINDING, expected_snapshot=value.snapshot()
    )["incomplete"]


def test_closed_ack_snapshot_requires_original_field_types(tmp_path):
    value, _ = opened(tmp_path)
    finish(value)
    for key in ("closed", "persisted_files", "failure_code"):
        wrong = value.snapshot()
        if key == "closed":
            wrong[key] = 1
        elif key == "persisted_files":
            wrong[key] = float(wrong[key])
        else:
            wrong.pop(key)
        assert cp.read_prefix(
            value.root, expected_binding=BINDING, expected_snapshot=wrong
        )["incomplete"]


def test_actual_phase_deadline_clamps_window_before_any_timer(tmp_path):
    value, clock = writer(tmp_path)
    value.phase_open(1, phase_deadline_ns=5_000_000_000, timeout_seconds=2)
    header = t.decode_header((value.root / "chunk000001.bin").read_bytes())
    assert header["phase_end_mono_ns"] == header["phase_deadline_ns"] == 5_000_000_000
    clock.advance(5_000_000_000)
    with value._condition:
        value._condition.notify_all()
    time.sleep(0.02)
    assert value.snapshot()["persisted_files"] == 1
    finish(value)
    assert not prefix(value)["incomplete"]


def test_protected_policy_wire_identity_is_explicit_and_preserved(tmp_path):
    clock = FakeClock()
    protected = "stage12_development_sampling_policy_b2_ap_v1"
    observer = timing.SamplingTiming(
        tmp_path / "timing",
        phase_count=1,
        timing_schema=cp.WF_SCHEMA,
        timing_binding=BINDING,
        timing_policy_version=protected,
        phase_windows=[dict(phase_id=1, selected_phase_ms=20000)],
        cumulative_deadline_ns=100_000_000_000,
        clock_ns=clock.now_ns,
    )
    observer.phase_open(1, phase_deadline_ns=20_000_000_000, timeout_seconds=2)
    observer.periodic(row())
    observer.phase_close(1, timeout_seconds=2)
    snapshot = observer.close(timeout_seconds=2)
    report = cp.read_prefix(
        observer.checkpoints.root,
        expected_binding=BINDING,
        expected_snapshot=snapshot["checkpoint"],
    )
    assert not report["incomplete"]
    assert report["last_payload"]["policy_version"] == protected
    with pytest.raises(cp.CheckpointError):
        timing.SamplingTiming(
            tmp_path / "wrong", phase_count=1, timing_policy_version=protected
        )


def test_multiple_selected_roots_keep_one_global_chain_and_finite_boundaries(tmp_path):
    clock = FakeClock()
    value = t.Checkpoints(
        tmp_path / "timing",
        timing_binding=BINDING,
        phase_windows=[dict(phase_id=n, selected_phase_ms=20000) for n in (1, 2)],
        cumulative_deadline_ns=100_000_000_000,
        clock_ns=clock.now_ns,
    )
    for phase in (1, 2):
        value.phase_open(
            phase, phase_deadline_ns=clock.now_ns() + 20_000_000_000, timeout_seconds=2
        )
        item = row()
        item["phase_id"] = phase
        value.record(item)
        value.phase_close(phase, timeout_seconds=2)
        clock.advance(30_000_000_000)
    state = value.close(timeout_seconds=2)
    assert state["reserved_cuts"] == 5 and state["persisted_files"] == 5
    assert not prefix(value)["incomplete"]


def test_nonmonotonic_observation_clock_cannot_complete(tmp_path):
    value, clock = opened(tmp_path)
    clock.advance(1)
    value.record(row())
    clock.advance(-1)
    with pytest.raises(cp.CheckpointError, match="CHECKPOINT_CLOCK_INVALID"):
        value.phase_close(1, timeout_seconds=2)
    assert value.snapshot()["failure_code"] == "CHECKPOINT_CLOCK_INVALID"
    with pytest.raises(cp.CheckpointError):
        value.close(timeout_seconds=2)


def test_untrusted_callback_exception_never_becomes_failure_text(tmp_path):
    value, _ = opened(tmp_path)
    value.record(row())
    finish(value)

    def consumer(*_):
        raise cp.CheckpointError(["SYNTHETIC_PRIVATE_CANARY"])

    result = prefix(value, record_consumer=consumer)
    assert result["incomplete"] and result["reason"] == "CHECKPOINT_PERSISTENCE_FAILED"
