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


def campaign(tmp_path, *, clock=None, count=2, diagnostics=None):
    p, plan, start, rows, inv = inputs(count)
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
        diagnostics=diagnostics,
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


def test_closure_derives_original_ledger_once_and_reopens_it_exactly(
    tmp_path, monkeypatch
):
    ledger = rec.work_ledger
    calls = []

    def counted(*args, **kwargs):
        calls.append(1)
        yield from ledger(*args, **kwargs)

    monkeypatch.setattr(rec, "work_ledger", counted)
    root, report, data = campaign(tmp_path)
    assert report["disposition"] == "COMPLETED" and report["report_complete"]
    assert len(calls) == 1
    retained = list(j.read_array(root / "work_ledger.json"))
    assert len(retained) == 2
    assert all(row["state"] == "DURABLE_SUCCESS" for row in retained)
    assert list(j.read_array(root / "remaining_work_ledger.json")) == []
    assert reopen(root, data) == report["blocks"][0]
    assert len(calls) == 2  # Full opener still derives from original evidence.


@pytest.mark.parametrize("stage", ["totality", "remaining", "during_totality"])
def test_reused_ledger_content_is_validated_at_every_consumer(
    tmp_path, monkeypatch, stage
):
    totality, stream, read = (
        rec.required_work_complete,
        j.Journal.stream_array,
        j.read_array,
    )
    changed = False
    ledger_root = None

    def corrupt(root):
        nonlocal changed
        path = root / "work_ledger.json"
        value = json.loads(path.read_bytes())
        value[0]["selected_receipt_sha256"] = "0" * 64
        # Same-length, schema-valid metadata must not pass on stat/size alone.
        assert len(c.canonical(value)) == len(path.read_bytes())
        path.write_bytes(c.canonical(value))
        changed = True

    def capture(self, name, rows):
        nonlocal ledger_root
        ledger_root = self.writer.root
        if stage == "remaining" and name == "remaining_work_ledger.json":
            corrupt(ledger_root)
        return stream(self, name, rows)

    def check(*args, **kwargs):
        if stage == "totality":
            corrupt(ledger_root)
        return totality(*args, **kwargs)

    ledger_reads = 0

    def altered(path, **kwargs):
        nonlocal ledger_reads, changed
        if path.name == "work_ledger.json":
            ledger_reads += 1
        # On the consumer's second pass (after its prehash), alter a row in
        # the yielded stream. The consuming digest must reject it too.
        for row in read(path, **kwargs):
            if (
                stage == "during_totality"
                and path.name == "work_ledger.json"
                and ledger_reads == 2
                and not changed
            ):
                row["selected_receipt_sha256"] = "0" * 64
                changed = True
            yield row

    monkeypatch.setattr(j.Journal, "stream_array", capture)
    monkeypatch.setattr(rec, "required_work_complete", check)
    monkeypatch.setattr(j, "read_array", altered)
    root, report, _ = campaign(tmp_path)
    assert changed and report["disposition"] == "RECOVERY_BLOCKED"
    assert not report["report_complete"]
    assert not (root / "_SEGMENT_SEALED").exists()
    assert not (root / "_WRITER_RELEASED.json").exists()


@pytest.mark.parametrize("count", [2, 5, 6, 35, 131])
def test_reopening_comparison_join_is_bounded_and_revalidates_each_body(
    tmp_path, monkeypatch, count
):
    root, report, data = campaign(tmp_path, count=count)
    assert report["report_complete"]
    from safe_geocoding_pipeline.preprocessing.stages import s12_response as response

    events, shapes = j.MeasurementPrefix.events, validation.shapes
    in_comparison = False
    passes, bodies = [], []
    original_ledger, original_report = rec.work_ledger, runtime.reporting.block_report

    def after_ledger(*args, **kwargs):
        nonlocal in_comparison
        yield from original_ledger(*args, **kwargs)
        in_comparison = True

    def before_report(*args, **kwargs):
        nonlocal in_comparison
        in_comparison = False
        return original_report(*args, **kwargs)

    def counted(self, *args, **kwargs):
        if in_comparison:
            passes.append(1)
        yield from events(self, *args, **kwargs)

    def checked(raw, work, **kwargs):
        if in_comparison:
            bodies.append(work["work_id"])
        return shapes(raw, work, **kwargs)

    # Receipt reopening may also use shapes; count the direct raw-body call
    # via its preceding decompress rather than treating receipt checks as skips.
    decompress = response.decompress
    decompressions = []

    def decoded(*args, **kwargs):
        if in_comparison:
            decompressions.append(1)
        return decompress(*args, **kwargs)

    monkeypatch.setattr(rec, "work_ledger", after_ledger)
    monkeypatch.setattr(runtime.reporting, "block_report", before_report)
    monkeypatch.setattr(j.MeasurementPrefix, "events", counted)
    monkeypatch.setattr(validation, "shapes", checked)
    monkeypatch.setattr(response, "decompress", decoded)
    assert reopen(root, data) == report["blocks"][0]
    assert len(passes) == (count - 1 + 127) // 128
    assert len(decompressions) >= 2 * (count - 1)
    assert set(bodies) == set(range(1, count + 1))


@pytest.mark.parametrize("stage", ["prepare", "fresh_finish", "persist", "revalidate", "seal", "campaign", "release"])
def test_closure_first_static_substage_is_retained_before_defensive_poison(
    tmp_path, monkeypatch, stage
):
    from safe_geocoding_pipeline.preprocessing.stages.s12_public_diagnostics import Failures

    clock = FakeClock()
    owner = Failures(clock, closure=True)
    evidence, write, snapshot = rec.snapshot_evidence, io.write, rec.write_snapshot
    calls = 0
    initiating = rec.FinalizationExpired("INVENTED_PRIVATE_DETAILS")

    def fail_evidence(*args, **kwargs):
        nonlocal calls
        calls += 1
        if (stage == "prepare" and calls == 1) or (stage == "revalidate" and calls == 2):
            raise initiating
        return evidence(*args, **kwargs)

    def fail_write(path, raw):
        selected = {"persist": "snapshot.json", "seal": "_SEGMENT_SEALED",
                    "campaign": "campaign_report.json", "release": "_WRITER_RELEASED.json"}.get(stage)
        if path.name == selected:
            raise initiating
        return write(path, raw)

    def fail_finish(writer, value, **kwargs):
        if stage == "fresh_finish":
            def fail():
                raise initiating
            kwargs["read_stage"].finish = fail
        return snapshot(writer, value, **kwargs)

    monkeypatch.setattr(rec, "snapshot_evidence", fail_evidence)
    monkeypatch.setattr(io, "write", fail_write)
    monkeypatch.setattr(rec, "write_snapshot", fail_finish)
    root, report, data = campaign(tmp_path, clock=clock, diagnostics=owner)
    state = owner.snapshot()
    first = state["closure_boundary"]["first_failure"]
    expected = {"prepare": "PREPARE_EVIDENCE", "fresh_finish": "FRESH_FINISH",
                "persist": "SNAPSHOT_PERSIST", "revalidate": "REVALIDATE_EVIDENCE",
                "seal": "SNAPSHOT_SEAL", "campaign": "CAMPAIGN_PERSIST",
                "release": "WRITER_RELEASE"}[stage]
    assert first["last_entered"]["stage"] == expected
    assert first["failure"]["family"] == "CUMULATIVE_DEADLINE"
    assert first["failure"]["writer_failed"] is False
    assert type(first["last_entered"]["deadline_ns"]) is int
    assert first["last_entered"]["deadline_identity_unchanged"] is True
    assert report["disposition"] == "RECOVERY_BLOCKED" and not report["report_complete"]
    assert not (root / "_WRITER_RELEASED.json").exists()
    assert b"INVENTED_PRIVATE_DETAILS" not in c.canonical(state)
    with pytest.raises((c.Stage12Error, OSError, rec.FinalizationExpired)):
        reopen(root, data)


def test_closure_supplementary_boundary_failure_preserves_original_publication_error(
    tmp_path, monkeypatch
):
    from safe_geocoding_pipeline.preprocessing.stages.s12_public_diagnostics import Failures

    owner = Failures(FakeClock(), closure=True)
    initiating = rec.FinalizationExpired("INVENTED_PRIVATE_DETAILS")

    def broken(*args, **kwargs):
        raise RuntimeError("INVENTED_SUPPLEMENTARY_DETAILS")

    def fail_evidence(*args, **kwargs):
        raise initiating

    monkeypatch.setattr(owner, "closure_boundary", broken)
    monkeypatch.setattr(rec, "snapshot_evidence", fail_evidence)
    root, report, _ = campaign(tmp_path, diagnostics=owner)
    assert report["disposition"] == "RECOVERY_BLOCKED"
    assert owner.snapshot()["first_initiating_failure"]["family"] == "CUMULATIVE_DEADLINE"
    assert owner.snapshot()["closure_boundary"]["retention_uncertain"]
    assert not (root / "_SEGMENT_SEALED").exists()


def test_opt_in_closure_completes_original_reopening_without_acceptance_changes(tmp_path):
    from safe_geocoding_pipeline.preprocessing.stages.s12_public_diagnostics import Failures

    clock = FakeClock()
    owner = Failures(clock, closure=True)
    root, report, data = campaign(tmp_path, clock=clock, diagnostics=owner)
    assert report["disposition"] == "COMPLETED" and report["report_complete"]
    assert reopen(root, data) == report["blocks"][0]
    state = owner.snapshot()["closure_boundary"]
    assert state["first_failure"] is None and not state["retention_uncertain"]
    assert state["last_entered"]["stage"] == state["last_completed"]["stage"] == "WRITER_RELEASE"


def test_new_prepoison_record_failure_does_not_mask_original_exception(tmp_path, monkeypatch):
    from safe_geocoding_pipeline.preprocessing.stages.s12_public_diagnostics import Failures

    clock = FakeClock()
    owner = Failures(clock, closure=True)
    record = owner.record
    failed_new_record = []

    def one_shot(tag, error, **kwargs):
        if tag == "CLOSURE" and not failed_new_record:
            failed_new_record.append(True)
            raise RuntimeError("INVENTED_SUPPLEMENTARY_DETAILS")
        return record(tag, error, **kwargs)

    def fail_evidence(*args, **kwargs):
        raise rec.FinalizationExpired("INVENTED_ORIGINAL_DETAILS")

    monkeypatch.setattr(owner, "record", one_shot)
    monkeypatch.setattr(rec, "snapshot_evidence", fail_evidence)
    root, report, _ = campaign(tmp_path, clock=clock, diagnostics=owner)
    assert failed_new_record == [True]
    assert report["disposition"] == "RECOVERY_BLOCKED" and not report["report_complete"]
    state = owner.snapshot()
    assert state["first_initiating_failure"]["family"] == "CUMULATIVE_DEADLINE"
    assert state["closure_boundary"]["retention_uncertain"]
    assert not (root / "_SEGMENT_SEALED").exists()
    assert not (root / "_WRITER_RELEASED.json").exists()
    assert b"INVENTED_" not in c.canonical(state)
