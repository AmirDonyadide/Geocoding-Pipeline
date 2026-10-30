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
    assert len(entered) == len(finished) == 3
    assert len({id(value) for value in entered}) == 3
    assert reads == {0: 2, 1: 2, 2: 2}


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

    def fail(self):
        raise RuntimeError("UNSAFE_TEXT_MUST_NOT_BE_RETAINED")

    monkeypatch.setattr(cli, "run_operations_block", diagnose)
    monkeypatch.setattr(f.FreshReads, "__enter__", fail)
    root, report, _ = campaign(tmp_path, clock=clock)
    assert report["disposition"] == "RECOVERY_BLOCKED"
    assert failures.first["operation"] == "REPORT"
    assert failures.first["family"] == "UNCLASSIFIED"
    assert "UNSAFE_TEXT" not in str(failures.snapshot())
    assert not (root / "snapshot.json").exists()
