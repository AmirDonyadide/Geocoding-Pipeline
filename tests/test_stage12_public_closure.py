"""Staged public closure: invented observations, real validators, no service."""

import json
import shutil
import threading

import pytest

from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_public_journal as j,
    s12_public_operations as o,
    s12_public_recovery as rec,
    s12_public_response as validation,
    s12_public_runtime as runtime,
    s12_retrieval_contract as c,
    s12_storage as io,
)
from test_stage12_public_operations_v2 import (
    H,
    FakeClock,
    inputs,
    rebind,
    offline,  # noqa: F401
)
from test_stage12_public_scheduler import repair_common, synthetic_dispatch


def campaign(tmp_path, *, clock=None):
    p, plan, start, rows, inv = inputs(2)
    p["resources"]["writer_guard_ms"] = 5000
    rebind(p, plan, start, rows)
    clock = clock or FakeClock()
    root = tmp_path / "campaign"
    result = cli.run_operations_block(
        p,
        plan,
        start,
        output=root,
        clock=clock,
        epoch=H,
        dispatch=synthetic_dispatch(clock),
        public_validation=validation.Validation(validation.FAMILY_VERSION),
        **repair_common(rows, inv),
    )
    return root, result, (p, plan, start)


def reopen(root, data):
    return runtime.reopen_completed(
        root,
        *data,
        validation_sha256=o.digest(validation.descriptor(validation.FAMILY_VERSION)),
    )


def test_staged_closure_runs_expensive_validation_and_scan_off_writer(
    tmp_path, monkeypatch
):
    validations, scans, stages = [], [], []
    original_evidence = rec.snapshot_evidence
    original_tree = j.tree_bytes
    original_freeze = j.Writer.freeze_closure
    original_write = io.write
    writer = None

    def freeze(self):
        nonlocal writer
        result = original_freeze(self)
        writer = self
        return result

    def evidence(*a, **kw):
        validations.append(threading.current_thread().name)
        assert writer is not None and threading.current_thread() is not writer.thread
        return original_evidence(*a, **kw)

    def tree(root, *a, **kw):
        if writer is not None and root == writer.root:
            scans.append(1)
            assert threading.current_thread() is not writer.thread
        return original_tree(root, *a, **kw)

    def write(path, raw):
        if path.name in (
            "snapshot.json",
            "_SEGMENT_SEALED",
            "campaign_report.json",
            "_WRITER_RELEASED.json",
        ):
            stages.append(path.name)
            assert threading.current_thread() is writer.thread
        return original_write(path, raw)

    monkeypatch.setattr(j.Writer, "freeze_closure", freeze)
    monkeypatch.setattr(rec, "snapshot_evidence", evidence)
    monkeypatch.setattr(j, "tree_bytes", tree)
    monkeypatch.setattr(io, "write", write)
    root, report, data = campaign(tmp_path)
    assert report["disposition"] == "COMPLETED" and report["report_complete"]
    assert len(validations) == 2 and scans
    assert stages == [
        "snapshot.json",
        "_SEGMENT_SEALED",
        "campaign_report.json",
        "_WRITER_RELEASED.json",
    ]
    assert reopen(root, data) == report["blocks"][0]
    assert writer.closed and not writer.thread.is_alive() and not writer.failed.is_set()
    assert writer.guard_ms == 5000 and data[0]["resource_sample_period_ms"] == 100


def mutate(root, kind):
    if kind in ("event_change", "event_add", "event_drop", "event_reorder"):
        events = sorted((root / "events").iterdir())
        if kind == "event_add":
            (root / "events" / "99999999999999999999.json").write_bytes(
                events[-1].read_bytes()
            )
        elif kind == "event_drop":
            events[1].unlink()
        elif kind == "event_reorder":
            a, b = events[1].read_bytes(), events[2].read_bytes()
            events[1].write_bytes(b)
            events[2].write_bytes(a)
        else:
            value = json.loads(events[-1].read_bytes())
            value["mono_ns"] += 1
            events[-1].write_bytes(c.canonical(value))
    elif kind == "receipt":
        next((root / "attempts").rglob("*.zst")).write_bytes(b"invented corruption")
    elif kind == "root":
        prior = root.with_name("replaced_root")
        root.rename(prior)
        shutil.copytree(prior, root)
    else:
        names = {
            "inventory": "event_inventory.json",
            "attempt_inventory": "attempt_inventory.json",
            "ledger": "work_ledger.json",
            "remaining": "remaining_work_ledger.json",
            "report": "block_report.json",
            "comparison": "repeat_comparison.json",
            "projection": "measurement_event_prefix.json",
            "snapshot": "snapshot.json",
            "start": "campaign_start.json",
            "work": "work/00000000000000000001.json",
        }
        path = root / names[kind]
        value = json.loads(path.read_bytes())
        if isinstance(value, list):
            value.append({"scope": "INVENTED_CORRUPTION"})
        else:
            value["scope"] = "INVENTED_CORRUPTION"
        path.write_bytes(c.canonical(value))


@pytest.mark.parametrize(
    "kind",
    [
        "event_change",
        "event_add",
        "event_drop",
        "event_reorder",
        "receipt",
        "inventory",
        "attempt_inventory",
        "ledger",
        "remaining",
        "report",
        "comparison",
        "projection",
        "snapshot",
        "start",
        "work",
        "root",
    ],
)
def test_mutation_after_prepare_or_persist_never_commits(tmp_path, monkeypatch, kind):
    write = io.write
    changed = False

    def tamper(path, raw):
        nonlocal changed
        write(path, raw)
        if path.name == "snapshot.json" and not changed:
            changed = True
            mutate(path.parent, kind)

    monkeypatch.setattr(io, "write", tamper)
    root, report, data = campaign(tmp_path)
    assert changed
    assert report["disposition"] == "RECOVERY_BLOCKED" and not report["report_complete"]
    assert not (root / "_SEGMENT_SEALED").exists()
    assert not (root / "_WRITER_RELEASED.json").exists()
    with pytest.raises((c.Stage12Error, OSError)):
        reopen(root, data)


@pytest.mark.parametrize("kind", ["epoch", "head", "state", "fence"])
def test_stale_prepared_bindings_cannot_seal(tmp_path, monkeypatch, kind):
    snapshot = rec.write_snapshot
    write = io.write
    context = {}

    def capture(writer, value, **kw):
        context.update(writer=writer, value=value, **kw)
        return snapshot(writer, value, **kw)

    def stale(path, raw):
        write(path, raw)
        if path.name != "snapshot.json":
            return
        if kind == "epoch":
            context["log"].epoch = "0" * 64
        elif kind == "head":
            context["log"].last_hash = "0" * 64
        elif kind == "state":
            context["value"]["disposition"] = "STOPPED"
        else:
            context["writer"].closure_fence = None

    monkeypatch.setattr(rec, "write_snapshot", capture)
    monkeypatch.setattr(io, "write", stale)
    root, report, _ = campaign(tmp_path)
    assert report["disposition"] == "RECOVERY_BLOCKED"
    assert not (root / "_SEGMENT_SEALED").exists()
    assert not (root / "_WRITER_RELEASED.json").exists()


@pytest.mark.parametrize("stage", ["prepare", "persisted", "commit"])
def test_cumulative_expiry_between_snapshot_stages_stops_publication(
    tmp_path, monkeypatch, stage
):
    clock = FakeClock()
    evidence = rec.snapshot_evidence
    read = io.read
    calls = 0

    def expire_evidence(*a, **kw):
        nonlocal calls
        result = evidence(*a, **kw)
        calls += 1
        if (stage == "prepare" and calls == 1) or (stage == "persisted" and calls == 2):
            clock.advance(700 * 10**9)
        return result

    def expire_read(path, **kw):
        result = read(path, **kw)
        if stage == "commit" and path.name == "snapshot.json" and calls == 2:
            clock.advance(700 * 10**9)
        return result

    monkeypatch.setattr(rec, "snapshot_evidence", expire_evidence)
    monkeypatch.setattr(io, "read", expire_read)
    root, report, _ = campaign(tmp_path, clock=clock)
    assert report["disposition"] == "RECOVERY_BLOCKED" and not report["report_complete"]
    assert not (root / "_SEGMENT_SEALED").exists()
    assert not (root / "_WRITER_RELEASED.json").exists()


@pytest.mark.parametrize("stage", ["persist", "seal", "campaign", "release"])
def test_uncertain_persist_timeout_poison_prevents_later_seal_or_cleanup(
    tmp_path, monkeypatch, stage
):
    submit, result, read, write = j.Writer.submit, j.Future.result, io.read, io.write
    reached, allow = threading.Event(), threading.Event()
    captured = []

    def marked(self, action, **kw):
        future = submit(self, action, **kw)
        selected = {
            "persist": "write_snapshot.<locals>.persist",
            "seal": "write_snapshot.<locals>.commit",
            "release": "Writer.release.<locals>.write",
        }.get(stage)
        if action.__qualname__ == selected or (
            stage == "campaign" and "campaign_report.json" in action.__code__.co_consts
        ):
            future.snapshot_persist = True
            captured.append(self)
        return future

    def controlled_result(self, timeout=None):
        if getattr(self, "snapshot_persist", False):
            assert timeout == 5.0
            assert reached.wait(2)
            # Deterministically model guard expiry while I/O is outstanding;
            # no actual five-second sleep or selected-guard alteration.
            threading.Timer(0.02, allow.set).start()
            raise TimeoutError("INVENTED_TIMEOUT")
        return result(self, timeout=timeout)

    def delayed_read(path, **kw):
        if (
            stage == "persist"
            and path.name == "snapshot.json"
            and threading.current_thread().name == "stage12-public-writer"
        ):
            reached.set()
            assert allow.wait(2)
        return read(path, **kw)

    def delayed_write(path, raw):
        name = {
            "seal": "_SEGMENT_SEALED",
            "campaign": "campaign_report.json",
            "release": "_WRITER_RELEASED.json",
        }.get(stage)
        if path.name == name:
            reached.set()
            assert allow.wait(2)
        return write(path, raw)

    monkeypatch.setattr(io, "write", delayed_write)
    monkeypatch.setattr(j.Writer, "submit", marked)
    monkeypatch.setattr(j.Future, "result", controlled_result)
    monkeypatch.setattr(io, "read", delayed_read)
    root, report, data = campaign(tmp_path)
    assert report["disposition"] == "RECOVERY_BLOCKED" and not report["report_complete"]
    assert captured[0].failed.is_set() and not captured[0].thread.is_alive()
    assert (root / "snapshot.json").exists()
    assert (root / "_SEGMENT_SEALED").exists() == (stage in ("campaign", "release"))
    assert not (root / "_WRITER_RELEASED.json").exists()
    with pytest.raises(c.Stage12Error):
        reopen(root, data)


def test_closure_fence_rejects_other_producer_without_waiting_for_disk(tmp_path):
    writer = j.Writer(tmp_path / "writer", 1, 5000, lambda: None)
    writer.freeze_closure()
    errors = []

    def other():
        try:
            writer.call(lambda: pytest.fail("another producer executed"))
        except c.Stage12Error:
            errors.append(1)

    thread = threading.Thread(target=other)
    thread.start()
    thread.join(1)
    assert not thread.is_alive() and errors == [1] and writer.failed.is_set()
    writer.abort()


@pytest.mark.parametrize(
    "name",
    [
        "campaign_report.json",
        "remaining_work_ledger.json",
        "work_ledger.json",
        "block_report.json",
        "snapshot.json",
    ],
)
def test_real_opener_rejects_changed_publication_artifact(tmp_path, name):
    root, report, data = campaign(tmp_path)
    assert report["disposition"] == "COMPLETED"
    assert reopen(root, data) == report["blocks"][0]
    (root / name).write_bytes(b"{}\n")
    with pytest.raises(c.Stage12Error):
        reopen(root, data)


def test_actual_reopening_keeps_cumulative_deadline(tmp_path, monkeypatch):
    root, report, data = campaign(tmp_path)
    assert report["report_complete"]
    clock = FakeClock()
    deadline = rec.Deadline(clock, 10)
    read = io.read
    calls = 0

    def expire(path, **kw):
        nonlocal calls
        raw = read(path, **kw)
        calls += 1
        if calls == 4:
            clock.advance(11)
        return raw

    monkeypatch.setattr(io, "read", expire)
    with io.cooperative_io(deadline.check), pytest.raises(rec.FinalizationExpired):
        reopen(root, data)
    assert calls < 10


def test_mutation_before_unsealed_snapshot_write_is_detected(tmp_path, monkeypatch):
    write = io.write

    def change(path, raw):
        if path.name == "snapshot.json":
            mutate(path.parent, "ledger")
        return write(path, raw)

    monkeypatch.setattr(io, "write", change)
    root, report, _ = campaign(tmp_path)
    assert not report["report_complete"] and report["disposition"] == "RECOVERY_BLOCKED"
    assert not (root / "_SEGMENT_SEALED").exists()


def test_storage_scan_rejects_changed_accounting_binding(tmp_path, monkeypatch):
    tree = j.tree_bytes
    freeze = j.Writer.freeze_closure
    writer = None
    log = None
    enable = j.Journal.enable_accounting
    changed = False

    def capture(self):
        nonlocal log
        enable(self)
        log = self

    def frozen(self):
        nonlocal writer
        fence = freeze(self)
        writer = self
        return fence

    def stale(root, *a, **kw):
        nonlocal changed
        size = tree(root, *a, **kw)
        if writer is not None and root == writer.root and not changed:
            changed = True
            log.accounted_bytes += 1
        return size

    monkeypatch.setattr(j.Journal, "enable_accounting", capture)
    monkeypatch.setattr(j.Writer, "freeze_closure", frozen)
    monkeypatch.setattr(j, "tree_bytes", stale)
    root, report, _ = campaign(tmp_path)
    assert changed and not report["report_complete"]
    assert not (root / "_SEGMENT_SEALED").exists()
