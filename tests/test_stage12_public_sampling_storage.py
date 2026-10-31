"""Public physical accounting while the existing periodic slot is serviced."""

import threading
import time
import pytest
from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as j
from safe_geocoding_pipeline.preprocessing.stages import s12_public_operations as o
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from test_stage12_public_scheduler import sampling_controller
from test_stage12_public_operations_v2 import offline  # noqa: F401


def test_storage_scan_services_one_sample_slot_with_exact_physical_bytes(
    tmp_path, monkeypatch
):
    ctl, clock, start = sampling_controller(tmp_path, lambda: 2**42)
    ctl.journal.enable_accounting()
    for i in range(30):
        ctl.writer.call(
            lambda i=i: io.write(ctl.writer.root / f"invented_{i}", b"invented")
        )
    original = j.tree_bytes
    producer = None

    def scan(root, exclude=frozenset(), *, check=lambda: None, **kw):
        if root != ctl.writer.root:
            return original(root, exclude, check=check, **kw)

        def step():
            nonlocal producer
            clock.advance(10_000_000)
            if clock.now_ns() >= ctl.last_sample_ns + 50_000_000 and (
                producer is None or not producer.is_alive()
            ):
                producer = threading.Thread(target=ctl.sample_if_due)
                producer.start()
                until = time.monotonic() + 1
                while (
                    ctl.writer.periodic.empty()
                    and producer.is_alive()
                    and time.monotonic() < until
                ):
                    time.sleep(0.001)
                assert not ctl.writer.periodic.empty()
            check()
            if producer is not None and ctl.writer.periodic.empty():
                producer.join(1)
                assert not producer.is_alive()

        return original(root, exclude, check=step, **kw)

    monkeypatch.setattr(j, "tree_bytes", scan)
    try:
        actual = ctl.writer.call(ctl.journal.verify_storage)
        if producer is not None:
            producer.join(1)
        monkeypatch.setattr(j, "tree_bytes", original)
        assert actual == ctl.journal.accounted_bytes == original(ctl.writer.root)
        ctl.resource("PERIODIC")
        events = list(j.read_events(ctl.writer.root, o.digest(start)))
        samples = [
            e["body"]["observed_mono_ns"]
            for e in events
            if e["kind"] == "RESOURCE" and e["body"]["cause"] == "PERIODIC"
        ]
        assert len(samples) >= 5
        assert max(b - a for a, b in zip([0] + samples, samples)) <= 100_000_000
        assert not ctl.writer.failed.is_set()
        assert ctl.writer.periodic.maxsize == 1
    finally:
        ctl.stop_sampling()
        ctl.writer.abort()


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_file",
        "old_truncated",
        "tail_changed",
        "tail_missing",
        "tail_not_periodic",
        "root_identity",
        "writer_failure",
    ],
)
def test_accounted_scan_rejects_interleaved_tampering(tmp_path, monkeypatch, mutation):
    ctl, clock, start = sampling_controller(tmp_path, lambda: 2**42)
    ctl.journal.enable_accounting()
    ctl.writer.call(lambda: io.write(ctl.writer.root / "known", b"invented"))
    original = ctl.writer.service_periodic
    changed = False
    scanning = False
    original_scan = j.tree_bytes

    def scan(*args, **kwargs):
        nonlocal scanning
        scanning = True
        return original_scan(*args, **kwargs)

    monkeypatch.setattr(j, "tree_bytes", scan)

    def service():
        nonlocal changed
        if changed or not scanning:
            return original()
        changed = True
        if mutation in ("tail_changed", "tail_missing", "tail_not_periodic"):
            # Fake only the submitted sample action; it still uses the real sole
            # writer event constructor, byte charge and original validation.
            thread = threading.Thread(target=lambda: ctl.resource("PERIODIC"))
            thread.start()
            until = time.monotonic() + 1
            while ctl.writer.periodic.empty() and time.monotonic() < until:
                time.sleep(0.001)
            assert not ctl.writer.periodic.empty()
            original()
            thread.join(1)
            assert not thread.is_alive()
            path = ctl.writer.root / "events" / f"{ctl.journal.seq:020d}.json"
            if mutation == "tail_missing":
                path.unlink()
            else:
                obj = o.parse(io.read(path), o.EVENT)
                if mutation == "tail_not_periodic":
                    obj["body"]["cause"] = "STATE_CHANGE"
                else:
                    obj["body"]["pending_bytes"] += 1
                path.write_bytes(c.canonical(obj))
        elif mutation == "unknown_file":
            (ctl.writer.root / "unknown").write_bytes(b"unaccounted")
        elif mutation == "old_truncated":
            (ctl.writer.root / "known").write_bytes(b"x")
        elif mutation == "root_identity":
            ctl.journal.root_identity = (-1, -1)
        elif mutation == "writer_failure":
            ctl.writer.failed.set()
        return original()

    monkeypatch.setattr(ctl.writer, "service_periodic", service)
    try:
        with pytest.raises((c.Stage12Error, OSError)):
            ctl.writer.call(ctl.journal.verify_storage)
        assert ctl.writer.failed.is_set()
        assert not (ctl.writer.root / "_SEGMENT_SEALED").exists()
    finally:
        ctl.stop_sampling()
        ctl.writer.abort()


def test_public_event_readback_has_exact_bound_and_rejects_extra_byte(
    tmp_path, monkeypatch
):
    from test_stage12_public_scheduler import controller

    ctl, _ = controller(tmp_path)
    old = io.read
    seen = []

    def read(path, **kw):
        if path.parent.name == "events":
            seen.append((path.stat().st_size, kw.get("limit")))
            # An extra byte is never hidden by a small read bound.
            with path.open("ab") as stream:
                stream.write(b"x")
        return old(path, **kw)

    monkeypatch.setattr(io, "read", read)
    try:
        with pytest.raises(Exception):
            ctl.resource("PERIODIC")
        assert seen and all(size == limit for size, limit in seen)
        assert ctl.writer.failed.is_set()
    finally:
        ctl.writer.abort()
