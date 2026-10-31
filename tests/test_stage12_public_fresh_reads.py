"""Disposable original-source stages; default shared I/O remains unchanged."""

import threading
import pytest
from safe_geocoding_pipeline.preprocessing.stages import s12_public_fresh_reads as f
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from test_stage12_public_operations_v2 import offline  # noqa: F401


def source(tmp_path):
    root = tmp_path / "root"
    io.reserve(root)
    io.write(root / "a", b"abc")
    io.write(root / "empty", b"")
    return root


def test_fresh_reads_limits_finish_and_independent_next_stage(tmp_path, monkeypatch):
    root = source(tmp_path)
    calls = []
    original = io.original_read

    def read(path, **kw):
        calls.append(path.name)
        return original(path, **kw)

    monkeypatch.setattr(io, "original_read", read)
    with f.FreshReads(root) as stage:
        assert calls == ["a", "empty"]
        assert io.read(root / "a") == b"abc"
        assert io.read(root / "empty", limit=0) == b""
        with pytest.raises(c.Stage12Error):
            io.read(root / "a", limit=0)
        assert calls == ["a", "empty"]
        stage.finish()
        assert stage.state == "VERIFIED" and not stage.cache and not io.has_read_view()
    assert calls == ["a", "empty", "a", "empty"]
    with f.FreshReads(root):
        assert io.read(root / "a") == b"abc"
    assert len(calls) == 8


@pytest.mark.parametrize(
    "change",
    [
        "same_size",
        "truncate",
        "missing",
        "extra",
        "extra_dir",
        "rename",
        "root",
        "mode",
        "symlink",
    ],
)
def test_midstage_source_changes_fail_and_unhook(tmp_path, change):
    root = source(tmp_path)
    with pytest.raises((c.Stage12Error, OSError)):
        with f.FreshReads(root) as stage:
            assert io.read(root / "a") == b"abc"
            if change == "same_size":
                (root / "a").write_bytes(b"def")
            elif change == "truncate":
                (root / "a").write_bytes(b"a")
            elif change == "missing":
                (root / "a").unlink()
            elif change == "extra":
                (root / "new").write_bytes(b"x")
            elif change == "extra_dir":
                (root / "new").mkdir(mode=0o700)
            elif change == "rename":
                (root / "a").rename(root / "b")
            elif change == "root":
                root.rename(tmp_path / "moved")
                root.mkdir(mode=0o700)
            elif change == "mode":
                (root / "a").chmod(0o644)
            else:
                (root / "a").unlink()
                (root / "a").symlink_to(root / "empty")
    assert stage.state == "INVALID" and not stage.cache and not io.has_read_view()


def test_output_binding_limit_streaming_fallback_and_cross_thread(
    tmp_path, monkeypatch
):
    root = source(tmp_path)
    monkeypatch.setattr(f, "MAX_BYTES", 2)
    with f.FreshReads(root, outputs={"ledger"}) as stage:
        assert "a" not in stage.cache
        assert io.read(root / "a") == b"abc"
        assert stage.cached_bytes <= 2 and "a" in stage.hashes
        io.write(root / "ledger", b"[]")
        io.record_read_output(root / "ledger", c.sha(b"[]").hex())
        assert io.read(root / "ledger") == b"[]"
        seen = []
        worker = threading.Thread(target=lambda: seen.append(io.has_read_view()))
        worker.start()
        worker.join()
        assert seen == [False]
        with pytest.raises(c.Stage12Error):
            with f.FreshReads(root):
                pass
        assert io.has_read_view()
    assert stage.state == "VERIFIED"


@pytest.mark.parametrize(
    "kind",
    ["wrong_digest", "unapproved", "output_mutation", "count", "names", "deadline"],
)
def test_rejected_output_or_resource_limit_never_finishes(tmp_path, monkeypatch, kind):
    root = source(tmp_path)
    expired = False

    def check():
        if expired:
            raise RuntimeError("TEST_CUMULATIVE_EXPIRY")

    if kind == "count":
        monkeypatch.setattr(f, "MAX_ENTRIES", 1)
    if kind == "names":
        monkeypatch.setattr(f, "MAX_PATH_BYTES", 1)
    with pytest.raises((c.Stage12Error, RuntimeError)):
        with f.FreshReads(root, outputs={"ledger"}, check=check):
            if kind == "deadline":
                expired = True
            else:
                io.write(root / "ledger", b"[]")
                if kind != "unapproved":
                    io.record_read_output(
                        root / "ledger",
                        "0" * 64 if kind == "wrong_digest" else c.sha(b"[]").hex(),
                    )
                if kind == "output_mutation":
                    (root / "ledger").write_bytes(b"{}")
    assert not io.has_read_view()


def test_outside_authority_inputs_are_never_cached(tmp_path):
    root = source(tmp_path)
    other = tmp_path / "authority"
    io.write(other, b"TEST_ONLY")
    with f.FreshReads(root):
        assert io.read(other) == b"TEST_ONLY"
        other.write_bytes(b"UPDATED_TEST_ONLY")
        assert io.read(other) == b"UPDATED_TEST_ONLY"


@pytest.mark.parametrize("stage", ["initial", "post_persist", "opener"])
@pytest.mark.parametrize(
    "kind",
    [
        "event_change",
        "event_add",
        "event_drop",
        "event_reorder",
        "receipt",
        "work",
        "inventory",
        "ledger",
        "report",
    ],
)
def test_mutation_after_stage_validation_cannot_be_accepted(
    tmp_path, monkeypatch, stage, kind
):
    from test_stage12_public_closure import campaign, reopen, mutate
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_recovery as rec
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_runtime as runtime,
    )

    calls = 0
    evidence = rec.snapshot_evidence

    def changed(*args, **kwargs):
        nonlocal calls
        result = evidence(*args, **kwargs)
        calls += 1
        if (stage == "initial" and calls == 1) or (
            stage == "post_persist" and calls == 2
        ):
            mutate(args[0], kind)
        return result

    monkeypatch.setattr(rec, "snapshot_evidence", changed)
    root, report, data = campaign(tmp_path)
    if stage == "opener":
        assert report["report_complete"]
        original = runtime._reopen_completed

        def changed_open(*args, **kwargs):
            result = original(*args, **kwargs)
            mutate(args[0], kind)
            return result

        monkeypatch.setattr(runtime, "_reopen_completed", changed_open)
        with pytest.raises((c.Stage12Error, OSError)):
            reopen(root, data)
    else:
        assert report["disposition"] == "RECOVERY_BLOCKED"
        assert not report["report_complete"]
        assert not (root / "_SEGMENT_SEALED").exists()
        assert not (root / "_WRITER_RELEASED.json").exists()
        assert (root / "snapshot.json").exists() == (stage == "post_persist")
    assert not io.has_read_view()


def test_each_stage_reads_original_event_twice_with_no_cross_stage_cache(
    tmp_path, monkeypatch
):
    from test_stage12_public_closure import campaign, reopen

    entered, finished, reads = [], [], {}
    enter, finish, original = (
        f.FreshReads.__enter__,
        f.FreshReads.finish,
        io.original_read,
    )
    active = None

    def begin(self):
        nonlocal active
        active = len(entered)
        entered.append(self)
        return enter(self)

    def end(self):
        nonlocal active
        finish(self)
        assert self.state == "VERIFIED" and not self.cache and not self.hashes
        finished.append(self)
        active = None

    def read(path, **kwargs):
        if (
            active is not None
            and path.name == "00000000000000000001.json"
            and path.parent.name == "events"
        ):
            reads[active] = reads.get(active, 0) + 1
        return original(path, **kwargs)

    monkeypatch.setattr(f.FreshReads, "__enter__", begin)
    monkeypatch.setattr(f.FreshReads, "finish", end)
    monkeypatch.setattr(io, "original_read", read)
    root, report, data = campaign(tmp_path)
    assert report["report_complete"]
    assert reopen(root, data) == report["blocks"][0]
    assert len(entered) == len(finished) == 4
    assert len({id(value) for value in entered}) == 4
    assert entered[0].root == root / "attempts"
    # The comparison view excludes events: its pinned prefix still reads
    # this original event once; each later whole-campaign stage reads twice.
    assert reads == {0: 1, 1: 2, 2: 2, 3: 2}


def test_initial_source_stage_failure_is_report_preparation_not_comparison(
    tmp_path, monkeypatch
):
    from test_stage12_public_closure import campaign
    from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
    from safe_geocoding_pipeline.preprocessing.stages.s12_public_diagnostics import (
        Failures,
    )
    from test_stage12_public_operations_v2 import FakeClock

    clock = FakeClock()
    failures = Failures(clock)
    run = cli.run_operations_block

    def diagnose(*args, **kwargs):
        return run(*args, diagnostics=failures, **kwargs)

    enter = f.FreshReads.__enter__

    def fail(self):
        if self.root.name == "attempts":
            return enter(self)
        raise RuntimeError("UNSAFE_TEXT_MUST_NOT_BE_RETAINED")

    monkeypatch.setattr(cli, "run_operations_block", diagnose)
    monkeypatch.setattr(f.FreshReads, "__enter__", fail)
    root, report, _ = campaign(tmp_path, clock=clock)
    assert report["disposition"] == "RECOVERY_BLOCKED"
    assert failures.first["operation"] == "REPORT"
    assert failures.first["family"] == "UNCLASSIFIED"
    assert "UNSAFE_TEXT" not in str(failures.snapshot())
    assert not (root / "snapshot.json").exists()


def work_source(tmp_path, count=3):
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_operations as o

    root = tmp_path / "work"
    io.reserve(root)
    rows = [{"key": key} for key in range(1, count + 1)]
    for key, row in enumerate(rows, 1):
        io.write(root / f"{key:020d}.json", c.canonical(row))
    return root, o.manifest_digest(rows)


@pytest.mark.parametrize("count", [0, 1, 3, 120])
def test_work_pass_exact_manifest_no_cross_attempt_state(tmp_path, count, monkeypatch):
    root, expected = work_source(tmp_path, count)
    original = f._work_read
    reads = []

    def read(path):
        reads.append(path.name)
        return original(path)

    monkeypatch.setattr(f, "_work_read", read)
    assert f.work_manifest_digest(root, count) == expected
    assert len(reads) == 2 * count
    assert f.work_manifest_digest(root, count) == expected
    assert len(reads) == 4 * count
    if count:
        io.write(root / "extra", b"extra")
        with pytest.raises(c.Stage12Error):
            f.work_manifest_digest(root, count)


@pytest.mark.parametrize(
    "kind",
    [
        "changed",
        "truncated",
        "extra",
        "missing",
        "reordered",
        "root_mode",
        "root_replace",
    ],
)
def test_work_pass_detects_mutation_before_return(tmp_path, monkeypatch, kind):
    root, _ = work_source(tmp_path)
    original = f._work_read
    calls = 0

    def read(path):
        nonlocal calls
        raw = original(path)
        calls += 1
        if calls == 3:
            first, second = root / f"{1:020d}.json", root / f"{2:020d}.json"
            if kind == "changed":
                first.write_bytes(c.canonical({"key": 9}))
            elif kind == "truncated":
                first.write_bytes(b"{")
            elif kind == "extra":
                io.write(root / "unexpected", b"x")
            elif kind == "missing":
                first.unlink()
            elif kind == "reordered":
                a, b = first.read_bytes(), second.read_bytes()
                first.write_bytes(b)
                second.write_bytes(a)
            elif kind == "root_mode":
                root.chmod(0o755)
            else:
                root.rename(root.with_name("replaced"))
                root.mkdir(mode=0o700)
        return raw

    monkeypatch.setattr(f, "_work_read", read)
    with pytest.raises((c.Stage12Error, OSError)):
        f.work_manifest_digest(root, 3)
    assert calls <= 4


@pytest.mark.parametrize(
    "kind",
    [
        "noncanonical",
        "nondict",
        "symlink",
        "hardlink",
        "file_mode",
        "count_bound",
        "deadline",
    ],
)
def test_work_pass_preserves_guards_and_bounds(tmp_path, monkeypatch, kind):
    root, _ = work_source(tmp_path)
    first = root / f"{1:020d}.json"
    if kind == "noncanonical":
        first.write_bytes(b'{"key": 1}\n')
    elif kind == "nondict":
        first.write_bytes(b"[]\n")
    elif kind == "symlink":
        first.unlink()
        first.symlink_to(root / f"{2:020d}.json")
    elif kind == "hardlink":
        import os

        os.link(first, tmp_path / "linked")
    elif kind == "file_mode":
        first.chmod(0o644)
    elif kind == "deadline":
        from safe_geocoding_pipeline.preprocessing.stages import (
            s12_public_recovery as rec,
        )

        def expire():
            raise rec.FinalizationExpired()

        monkeypatch.setattr(io, "_checkpoint", expire)
    with pytest.raises((c.Stage12Error, RuntimeError, OSError)):
        f.work_manifest_digest(
            root, f.WORK_ROWS_BOUND + 1 if kind == "count_bound" else 3
        )


def test_begin_still_rejects_changed_full_work_source_before_dispatch(
    tmp_path, monkeypatch
):
    from test_stage12_public_closure import campaign
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_scheduler as sched,
    )

    oldadmit = sched.Coordinator.admit
    changed = False

    def admit(self, begin):
        nonlocal changed
        if not changed:
            work = self.writer.root / "work" / f"{2:020d}.json"
            value = io.metadata(io.read(work))
            value["repetition"] += 1
            work.write_bytes(c.canonical(value))
            changed = True
        return oldadmit(self, begin)

    monkeypatch.setattr(sched.Coordinator, "admit", admit)
    root, report, _ = campaign(tmp_path)
    assert changed and not report["report_complete"]
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_journal as journal,
    )

    start = io.metadata(io.read(root / "campaign_start.json"))
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_operations as o

    assert all(
        e["kind"] != "ATTEMPT_STARTED"
        for e in journal.read_events(root, o.digest(start))
    )


def test_work_reader_bound_keeps_original_streaming_fallback(tmp_path, monkeypatch):
    from test_stage12_public_closure import campaign, reopen

    monkeypatch.setattr(f, "WORK_ROWS_BOUND", 1)

    def forbidden(*_args):
        pytest.fail("bounded work reader used beyond its row bound")

    monkeypatch.setattr(f, "work_manifest_digest", forbidden)
    root, report, data = campaign(tmp_path)
    assert report["report_complete"]
    assert reopen(root, data) == report["blocks"][0]


def test_comparison_attempt_stage_rechecks_mutated_original_before_accepting(
    tmp_path, monkeypatch
):
    from test_stage12_public_closure import campaign

    old = f.FreshReads.finish
    changed = False

    def finish(self):
        nonlocal changed
        if self.root.name == "attempts":
            assert not changed
            next(self.root.rglob("*.zst")).write_bytes(b"synthetic mutation")
            changed = True
        return old(self)

    monkeypatch.setattr(f.FreshReads, "finish", finish)
    root, report, _ = campaign(tmp_path)
    assert changed and not report["report_complete"]
    assert not (root / "snapshot.json").exists()
    assert not (root / "_WRITER_RELEASED.json").exists()
    assert not io.has_read_view()


def test_comparison_attempt_stage_does_not_hide_late_actual_sample(
    tmp_path, monkeypatch
):
    from test_stage12_public_closure import campaign
    from test_stage12_public_operations_v2 import FakeClock

    clock = FakeClock()
    finish = f.FreshReads.finish

    def late(self):
        finish(self)
        if self.root.name == "attempts":
            clock.advance(101_000_000)

    monkeypatch.setattr(f.FreshReads, "finish", late)
    root, report, _ = campaign(tmp_path, clock=clock)
    assert not report["blocks"][0]["resource_sampling_complete"]
    assert not report["report_complete"]
    assert not io.has_read_view()


def test_comparison_view_allows_actual_sampler_persistence_without_owning_events(
    tmp_path, monkeypatch
):
    from test_stage12_public_closure import campaign, reopen
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_scheduler as scheduler,
    )

    init = scheduler.Coordinator.__init__
    enter = f.FreshReads.__enter__
    captured = []
    observations = []

    def initialize(self, *args, **kwargs):
        init(self, *args, **kwargs)
        captured.append(self)

    def sample(self):
        result = enter(self)
        if self.root.name == "attempts":
            coordinator = captured[0]
            before = coordinator.journal.seq
            errors = []

            def observe():
                try:
                    assert not io.has_read_view()
                    coordinator.resource("PERIODIC")
                except BaseException as error:
                    errors.append(error)

            thread = threading.Thread(target=observe)
            thread.start()
            thread.join(2)
            assert not thread.is_alive() and not errors
            assert coordinator.journal.seq > before
            assert all(not name.startswith("events/") for name in self.hashes)
            observations.append(1)
        return result

    monkeypatch.setattr(scheduler.Coordinator, "__init__", initialize)
    monkeypatch.setattr(f.FreshReads, "__enter__", sample)
    root, report, data = campaign(tmp_path)
    assert observations == [1] and report["report_complete"]
    assert reopen(root, data) == report["blocks"][0]


def test_outside_comparison_output_keeps_exact_writer_reopening(tmp_path, monkeypatch):
    from test_stage12_public_closure import campaign
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_journal as journal,
    )

    read = journal.read_array
    intercepted = False

    def corrupted(path, **kwargs):
        nonlocal intercepted
        for row in read(path, **kwargs):
            if path.name == "repeat_comparison.json" and io.has_read_view():
                intercepted = True
                row = {**row, "equal": not row["equal"]}
            yield row

    monkeypatch.setattr(journal, "read_array", corrupted)
    root, report, _ = campaign(tmp_path)
    assert intercepted and not report["report_complete"]
    assert not (root / "snapshot.json").exists()
    assert not io.has_read_view()


def test_outside_output_does_not_enter_source_bindings(tmp_path):
    root = source(tmp_path)
    outside = tmp_path / "outside"
    io.write(outside, b"generated elsewhere")
    with f.FreshReads(root) as stage:
        before = stage.hashes.copy()
        io.record_read_output(outside, "0" * 64)
        assert stage.hashes == before
        inner = root / "unapproved"
        io.write(inner, b"unexpected")
        with pytest.raises(c.Stage12Error):
            stage.output(inner, c.sha(b"unexpected").hex())
        inner.unlink()


def _closure_fence(root):
    from types import SimpleNamespace
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as j

    writer = SimpleNamespace(
        root=root,
        check_deadline=lambda: None,
        closed=False,
        failed=threading.Event(),
        thread=SimpleNamespace(ident=-1),
    )
    fence = j.ClosureFence(writer)
    writer.closure_fence = fence
    return fence


def test_fence_full_checks_bracket_fresh_stage_and_live_checks_remain(
    tmp_path, monkeypatch
):
    root = source(tmp_path)
    fence = _closure_fence(root)
    counts = {"boundary": 0, "live": 0}
    full, live = fence.check, fence.check_live

    def boundary():
        counts["boundary"] += 1
        full()

    def checked():
        counts["live"] += 1
        live()

    with f.FreshReads(root, check=checked, boundary=boundary):
        for _ in range(1000):
            assert io.read(root / "a") == b"abc"
        assert counts["boundary"] == 2
    assert counts["boundary"] == 4 and counts["live"] >= 1000


@pytest.mark.parametrize("stage", ["entry", "loaded", "finish_entry", "finish_exit"])
def test_fresh_boundary_failure_unhooks_and_invalidates(tmp_path, stage):
    root = source(tmp_path)
    expected = ["entry", "loaded", "finish_entry", "finish_exit"].index(stage) + 1
    calls = 0

    def boundary():
        nonlocal calls
        calls += 1
        if calls == expected:
            raise c.Stage12Error("S12_PUBLIC_CUMULATIVE_DEADLINE")

    view = f.FreshReads(root, boundary=boundary)
    with pytest.raises(c.Stage12Error):
        with view:
            assert io.read(root / "a") == b"abc"
    assert view.state == "INVALID" and not view.cache and not io.has_read_view()


@pytest.mark.parametrize(
    "change", ["poison", "closed", "ownership", "root", "mode", "deadline"]
)
def test_fence_live_rejects_state_changes_during_cached_reads(tmp_path, change):
    root = source(tmp_path)
    fence = _closure_fence(root)
    with pytest.raises((c.Stage12Error, OSError)):
        with f.FreshReads(root, check=fence.check_live, boundary=fence.check):
            if change == "poison":
                fence.writer.failed.set()
            elif change == "closed":
                fence.writer.closed = True
            elif change == "ownership":
                fence.writer.closure_fence = None
            elif change == "root":
                root.rename(tmp_path / "moved")
                root.mkdir(mode=0o700)
            elif change == "mode":
                root.chmod(0o755)
            else:

                def expired():
                    raise c.Stage12Error("S12_PUBLIC_CUMULATIVE_DEADLINE")

                fence.writer.check_deadline = expired
            io.read(root / "a")
    assert not io.has_read_view()


def test_full_boundary_detects_ancestor_symlink_with_same_root_inode(tmp_path):
    from safe_geocoding_pipeline.preprocessing.stages.s09_reference_contract import (
        Stage09Error,
    )

    parent = tmp_path / "parent"
    parent.mkdir(mode=0o700)
    root = source(parent)
    fence = _closure_fence(root)
    with pytest.raises(Stage09Error, match="PUBLICATION_ANCESTOR_INVALID"):
        with f.FreshReads(root, check=fence.check_live, boundary=fence.check):
            moved = tmp_path / "moved"
            parent.rename(moved)
            parent.symlink_to(moved, target_is_directory=True)
            # Inode check alone cannot certify ancestors. Full finish boundary
            # must reject before any result or publication can be accepted.
            fence.check_live()
    assert not io.has_read_view()
