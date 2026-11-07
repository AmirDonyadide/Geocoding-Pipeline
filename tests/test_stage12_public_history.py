"""AP history packing, fresh private validation, and bounded failure evidence."""

import hashlib

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_public_history as h
from safe_geocoding_pipeline.preprocessing.stages import s12_public_recovery as recovery
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_public_sampling_contract as a,
)
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from test_stage12_public_operations_v2 import offline, H  # noqa: F401


def source(tmp_path):
    root = tmp_path / "root"
    io.reserve(root)
    for name in ["b", "a.json", "a", "work", "events"]:
        if name in ("a", "work", "events"):
            io.reserve(root / name)
        else:
            io.write(root / name, b"invented")
    io.write(root / "a" / "nested", b"child")
    io.write(root / "work" / "one", b"{}\n")
    io.write(root / "events" / "00000000000000000001.json", b"{}\n")
    return root


def test_packed_order_matches_path_order_and_membership(tmp_path):
    root = source(tmp_path)
    with_index = h.Index(root)
    try:
        actual = [p for _, p in with_index.files()]
        assert actual == [p for p in sorted(root.rglob("*")) if p.is_file()]
        assert len(with_index.entries) == with_index.capacity * h.ENTRY.size
        with_index.verify_membership()
        io.write(root / "extra", b"x")
        with pytest.raises(c.Stage12Error):
            with_index.verify_membership()
    finally:
        with_index.close()
    assert h._backing == 0


@pytest.mark.parametrize(
    "change",
    ["content", "missing", "extra", "type", "symlink", "mode", "directory", "ancestor"],
)
def test_fresh_changes_fail_and_release_all_buffers(tmp_path, change):
    root = source(tmp_path)
    with pytest.raises((c.Stage12Error, OSError)):
        with h.Fresh(root) as stage:
            assert io.read(root / "b") == b"invented"
            if change == "content":
                (root / "b").write_bytes(b"changed!")
            elif change == "missing":
                (root / "b").unlink()
            elif change == "extra":
                io.write(root / "extra", b"x")
            elif change == "type":
                (root / "b").unlink()
                (root / "b").mkdir(mode=0o700)
            elif change == "symlink":
                (root / "b").unlink()
                (root / "b").symlink_to(root / "a.json")
            elif change == "mode":
                (root / "b").chmod(0o644)
            elif change == "directory":
                (root / "a").rename(root / "old")
                (root / "a").mkdir(mode=0o700)
            else:
                root.rename(tmp_path / "moved")
                root.mkdir(mode=0o700)
    assert stage.state == "INVALID" and stage.index is None
    assert not io.has_read_view() and h._backing == 0


def test_fresh_independent_stages_outputs_cache_and_nested_ownership(tmp_path):
    root = source(tmp_path)
    with h.Fresh(root, outputs={"ledger"}) as stage:
        io.write(root / "ledger", b"[]\n")
        io.record_read_output(root / "ledger", c.sha(b"[]\n").hex())
        assert io.read(root / "ledger") == b"[]\n"
        with h.Fresh(root / "a") as nested:
            assert io.read(root / "a" / "nested") == b"child"
        assert nested.state == "VERIFIED" and io.has_read_view()
        assert io.read(root / "a" / "nested") == b"child"
        stage.finish()
        assert stage.state == "VERIFIED" and not io.has_read_view()
    assert h._backing == 0
    with h.Fresh(root):
        assert io.read(root / "b") == b"invented"


def test_preallocation_cap_below_at_above_and_no_uncounted_sorting(
    tmp_path, monkeypatch
):
    root = source(tmp_path)
    first = h.Index(root)
    needed = first._reserved
    first.close()
    monkeypatch.setattr(h, "MAX_BACKING", needed - 1)
    with pytest.raises(c.Stage12Error):
        h.Index(root)
    assert h._backing == 0
    monkeypatch.setattr(h, "MAX_BACKING", needed)
    index = h.Index(root)
    assert h._backing == needed
    with pytest.raises(c.Stage12Error):
        h.Index(root)
    index.close()
    monkeypatch.setattr(h, "MAX_BACKING", needed + 1)
    index = h.Index(root)
    index.close()
    assert h._backing == 0


def test_entry_path_boundary_and_population_has_no_per_file_maps(tmp_path, monkeypatch):
    root = tmp_path / "many"
    io.reserve(root)
    for i in range(1024):
        io.write(root / f"{i:020d}", b"x")
    index = h.Index(root)
    try:
        assert index.count == 1025
        assert not any(isinstance(v, dict) for v in vars(index).values())
        assert index._reserved < 128 * 1024
        index.verify_membership()
    finally:
        index.close()
    monkeypatch.setattr(h, "MAX_ENTRIES", 1024)
    with pytest.raises(c.Stage12Error):
        h.Index(root)
    assert h._backing == 0


def test_original_hash_is_streaming_and_detects_midread_mutation(tmp_path, monkeypatch):
    root = source(tmp_path)
    p = root / "large"
    raw = b"x" * 70000
    io.write(p, raw)
    assert h.hash_file(p) == hashlib.sha256(raw).hexdigest()
    read = h.os.read
    calls = []

    def changed(fd, size):
        assert size <= 4096
        result = read(fd, size)
        calls.append(size)
        if len(calls) == 2:
            p.write_bytes(b"y" * 70000)
        return result

    monkeypatch.setattr(h.os, "read", changed)
    with pytest.raises(c.Stage12Error):
        h.hash_file(p)
    assert len(calls) > 1


def test_fallback_retains_unknowns_sorted_fresh_rows_and_no_parallel_lists(tmp_path):
    root = source(tmp_path)
    io.reserve(root / "attempts")
    io.write(root / "attempts" / "invented_begin.json", c.canonical({"attempt": 1}))
    io.write(root / "attempts" / "broken_begin.json", b"{broken")
    known = recovery.unclean_reconciliation(root, H, contract=a)
    rows = known["known_files"]
    try:
        assert not isinstance(rows, list)
        assert known["begins_charged"] == {"value": None, "confirmed_min": 1}
        first = list(rows.rows("events/"))
        assert len(first) == 1
        io.write(root / "available_event_inventory.json", c.canonical(first))
        assert list(rows.rows("events/")) == first
        (root / "events" / "00000000000000000001.json").write_bytes(b"changed")
        with pytest.raises(c.Stage12Error):
            list(rows.rows("events/"))
    finally:
        rows.close()
    assert h._backing == 0


@pytest.mark.parametrize("change", ["missing", "extra", "symlink", "reordered"])
def test_event_names_enumerate_exact_numeric_members_and_originals(tmp_path, change):
    root = tmp_path / "events"
    io.reserve(root)
    for n in (2, 1, 3):
        io.write(root / f"{n:020d}.json", str(n).encode())
    assert [p.name for p in h.event_paths(root)] == [
        f"{n:020d}.json" for n in (1, 2, 3)
    ]
    if change == "missing":
        (root / f"{2:020d}.json").unlink()
    elif change == "extra":
        io.write(root / "extra", b"x")
    elif change == "symlink":
        (root / f"{2:020d}.json").unlink()
        (root / f"{2:020d}.json").symlink_to(root / f"{1:020d}.json")
    else:
        (root / f"{1:020d}.json").write_bytes(b"3")
    if change in ("missing", "extra"):
        with pytest.raises(c.Stage12Error):
            list(h.event_paths(root))
    elif change == "symlink":
        with pytest.raises(c.Stage12Error):
            h.hash_file(root / f"{2:020d}.json")
    else:
        # Ordering of filenames never certifies contents or associations.
        assert h.hash_file(root / f"{1:020d}.json") == hashlib.sha256(b"3").hexdigest()


# Regressions derived from the independent candidate01 findings.
@pytest.mark.parametrize("size", [65537, 2**20 + 1])
def test_generated_output_registration_uses_streaming_original_hash(
    tmp_path, monkeypatch, size
):
    root = tmp_path / "root"
    io.reserve(root)
    seen = []
    original = io.original_read

    def bounded(path, *, limit=64 * 2**20):
        raw = original(path, limit=limit)
        seen.append(len(raw))
        assert len(raw) <= 65536, "generated output materialized beyond64KiB scratch"
        return raw

    with h.Fresh(root, outputs={"event_inventory.json"}) as stage:
        path = root / "event_inventory.json"
        raw = b"x" * size
        io.write(path, raw)
        monkeypatch.setattr(io, "original_read", bounded)
        io.record_read_output(path, hashlib.sha256(raw).hexdigest())
    assert stage.state == "VERIFIED"
    assert h._backing == 0


def test_expiry_after_known_construction_releases_history_reservation(
    tmp_path, monkeypatch
):
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_recovery as recovery,
    )
    from test_stage12_public_sampling_integration import run_phase

    original_enter = h.Fresh.__enter__
    original_reconcile = recovery.unclean_reconciliation
    original_check = recovery.Deadline.check
    armed = [False]
    captured = []

    def failed_comparison(self):
        if self.root.name == "attempts":
            raise c.Stage12Error("S12_PUBLIC_SOURCE_CHANGED")
        return original_enter(self)

    def reconcile(*args, **kwargs):
        result = original_reconcile(*args, **kwargs)
        captured.append(result["known_files"])
        armed[0] = True
        return result

    def deadline_check(self):
        if armed[0]:
            armed[0] = False
            raise recovery.FinalizationExpired()
        return original_check(self)

    monkeypatch.setattr(h.Fresh, "__enter__", failed_comparison)
    monkeypatch.setattr(recovery, "unclean_reconciliation", reconcile)
    monkeypatch.setattr(recovery.Deadline, "check", deadline_check)
    try:
        run_phase(tmp_path, uncertain=True)
        assert len(captured) == 1
        assert h._backing == 0, (
            "expiry fallback abandoned a live Known/index reservation"
        )
    finally:
        for known in captured:
            known.close()
