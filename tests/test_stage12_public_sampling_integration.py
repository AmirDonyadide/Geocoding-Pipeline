"""Real local clocks/storage and existing phase entry; TEST_ONLY transport/key."""

import time
import pytest
from datetime import datetime, timezone, timedelta
from test_stage12_public_operations_v2 import offline, H, KEY  # noqa: F401
from test_stage12_public_sampling_contract import ap_inputs, TestOnlyAuthority
from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
from safe_geocoding_pipeline.preprocessing.stages import s12_public_runtime as runtime
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_public_sampling_contract as a,
)
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from safe_geocoding_pipeline.preprocessing.stages import s12_transport as t
from stage12_synthetic import body


class RealClock:
    def __init__(self):
        self.zero = time.monotonic_ns()

    def now_ns(self):
        return time.monotonic_ns() - self.zero

    def utc(self):
        return (
            datetime(2026, 1, 1, tzinfo=timezone.utc)
            + timedelta(microseconds=self.now_ns() // 1000)
        ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def wait_until(self, ns):
        while self.now_ns() < ns:
            time.sleep(min(0.001, (ns - self.now_ns()) / 1e9))


def run_phase(
    tmp_path,
    *,
    observer=None,
    with_control=False,
    malformed=False,
    uncertain=False,
    phase_inputs=None,
    predecessor=None,
    pause=False,
):
    p, plan, start, rows, inventory, bound = phase_inputs or ap_inputs()
    adapters = {}
    if with_control:
        from test_stage12_public_operational_audit import Control, recipe

        adapters = {1: Control()}
        plan["control_recipes"] = [recipe()]
        rows.append(
            dict(
                work_id=3,
                block_id=1,
                kind="SERVICE_CONTROL",
                fixture_id=None,
                result_limit=None,
                repetition=None,
                recipe_id=1,
                retry_spacing_key=H,
            )
        )
        plan["blocks"][0]["observation_ids"].append(3)
        for budget in (plan["budgets"], plan["blocks"][0]["budget"]):
            budget["required_control_observations"] = 1
            budget["control_http_attempts"] = 5
        plan["work_manifest_sha256"] = a.manifest_digest(rows)
        start["plan_sha256"] = a.digest(plan)
    pause_flag = [False]
    clock = RealClock()
    from safe_geocoding_pipeline.preprocessing.stages.s12_public_diagnostics import (
        Failures,
    )

    class SafeTestFailures(Failures):
        def __init__(self):
            super().__init__(clock)
            self.sites = []

        def record(self, stage, error, **kwargs):
            super().record(stage, error, **kwargs)
            if len(self.sites) < 4:
                tb = error.__traceback__
                sites = []
                while tb is not None:
                    sites.append(
                        (tb.tb_frame.f_code.co_filename.split("/")[-1], tb.tb_lineno)
                    )
                    tb = tb.tb_next
                self.sites.append((stage, sites))

    diagnostics = SafeTestFailures()

    def dispatch(work, target, hooks):
        hooks.started(clock.now_ns())
        hooks.emit(lambda: None, lambda: None)
        raw = (
            a.c.canonical({"synthetic_index": "test"})
            if work["kind"] == "SERVICE_CONTROL"
            else b"{broken"
            if malformed
            else body([])
        )
        pause_flag[0] = pause
        result = t.Capture(
            "VALIDATION_REQUIRED",
            "OK",
            200,
            "application/json",
            "identity",
            None,
            raw,
            len(raw),
            1,
        )
        hooks.completed(result)
        return result

    from safe_geocoding_pipeline.preprocessing.stages.s12_public_response import (
        Validation,
    )

    result = cli.run_operations_block(
        p,
        plan,
        start,
        work_factory=lambda: iter(rows),
        output=tmp_path / "run",
        block_id=1,
        authority=TestOnlyAuthority(bound),
        clock=clock,
        dispatch=dispatch,
        runtime_inventory=inventory,
        runtime_key=KEY,
        control_adapters=adapters,
        monitor=None,
        free_bytes=lambda: 2**42,
        segment_authority=H,
        writer_exclusion_evidence=H,
        epoch="2" * 64 if predecessor else H,
        predecessor=predecessor,
        continuation_authority=H if predecessor else None,
        pause_requested=lambda: pause_flag[0],
        writer_release_evidence=H,
        task_deadline_ns=clock.now_ns() + 180_000_000_000,
        diagnostics=diagnostics,
        public_validation=Validation(),
        timing_observer=observer,
    )
    if not result["report_complete"]:
        io.write(
            tmp_path / "safe_failure_sites.json",
            a.c.canonical(
                {"snapshot": diagnostics.snapshot(), "sites": diagnostics.sites}
            ),
        )
    assert result["schema_version"] == a.REPORT
    if uncertain:
        assert not result["report_complete"]
        assert not (tmp_path / "run" / "_WRITER_RELEASED.json").exists()
        assert not (tmp_path / "run" / "_SEGMENT_SEALED").exists()
        return p, plan, start, result, tmp_path / "run"
    if malformed:
        assert not result["report_complete"] and result["disposition"] == "STOPPED"
        with pytest.raises(a.c.Stage12Error):
            runtime.reopen_completed(
                tmp_path / "run", p, plan, start, control_adapters=adapters
            )
        return p, plan, start, result, tmp_path / "run"
    if pause:
        assert result["disposition"] == "PAUSED_CLEAN"
        assert result["sampling_segments"][-1]["complete"]
        return p, plan, start, result, tmp_path / "run"
    if predecessor is not None:
        assert result["disposition"] == "COMPLETED"
        assert not result["report_complete"]
        assert (
            result["blocks"][0]["duration_ns"] is None
        )  # unchanged multi-epoch metric semantics
        assert result["blocks"][0]["resource_sampling_complete"]
        with pytest.raises(a.c.Stage12Error):
            runtime.reopen_completed(tmp_path / "run", p, plan, start)
        return p, plan, start, result, tmp_path / "run"
    assert result["report_complete"], (diagnostics.snapshot(), diagnostics.sites)
    reopened = runtime.reopen_completed(
        tmp_path / "run", p, plan, start, control_adapters=adapters
    )
    assert reopened == result["blocks"][0]
    return p, plan, start, result, tmp_path / "run"


def test_AP25_real_phase_and_actual_opener(tmp_path):
    run_phase(tmp_path)


@pytest.mark.parametrize("delay", [0.125, 0.300])
def test_AP02_append_delays_do_not_hold_acquisition(tmp_path, monkeypatch, delay):
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_journal as journal,
    )

    original = journal.io.write
    stalled = False

    def write(path, raw):
        nonlocal stalled
        if (
            not stalled
            and path.parent.name == "events"
            and b'"kind":"RESOURCE_SAMPLE"' in raw
        ):
            stalled = True
            time.sleep(delay)
        return original(path, raw)

    monkeypatch.setattr(journal.io, "write", write)
    p, plan, start, result, root = run_phase(tmp_path)
    assert stalled
    summary = result["sampling_segments"][0]
    assert summary["complete"] and summary["maximum_gap_ns"] <= 100_000_000
    assert summary["maximum_outstanding_count"] >= 2
    assert summary["maximum_ack_age_ns"] >= int(delay * 1e9)


def test_AP19_AP20_fresh_original_mutation_and_missing_terminal(tmp_path):
    from copy import deepcopy
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_journal as journal,
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_sampling as sampling,
    )

    p, plan, start, result, root = run_phase(tmp_path)
    events = list(journal.read_events(root, a.digest(start), contract=a))

    def scan(values):
        return sampling.inspect(lambda: iter(values), p, start, maximum_segments=1)[0]

    assert scan(events)["complete"]

    def rechain(values):
        previous = None
        for n, event in enumerate(values, 1):
            event["seq"] = n
            event["previous_event_sha256"] = previous
            previous = a.digest(event)
        return values

    sample_index = next(
        i for i, e in enumerate(events) if e["kind"] == "RESOURCE_SAMPLE"
    )
    half = scan(events[: sample_index + 1])
    assert not half["complete"] and half["acknowledged"] == {
        "value": None,
        "confirmed_min": 0,
    }
    assert half["missing_ack_count"]["confirmed_min"] == 1
    for field, value in [
        ("failure", "ACQUISITION_GAP"),
        ("close_requested_mono_ns", 0),
        ("last_reserved_seq", {"value": 1, "confirmed_min": 1}),
    ]:
        bad = deepcopy(events)
        row = next(e for e in bad if e["kind"] == "SAMPLING_CLOSE")
        row["body"][field] = value
        if field == "close_requested_mono_ns":
            row["mono_ns"] = 6_000_000_000
        with pytest.raises(a.c.Stage12Error):
            scan(rechain(bad))
    for change in ("duplicate", "missing", "reorder", "counter", "hash"):
        bad = deepcopy(events)
        if change == "duplicate":
            bad.insert(sample_index + 1, deepcopy(bad[sample_index]))
        if change == "missing":
            del bad[sample_index + 1]
        if change == "reorder":
            bad[sample_index], bad[sample_index + 1] = (
                bad[sample_index + 1],
                bad[sample_index],
            )
        if change == "counter":
            bad[sample_index]["body"]["observation"]["state"]["pending_count"] += 1
        if change == "hash":
            bad[sample_index]["body"]["observation_sha256"] = "0" * 64
        with pytest.raises(a.c.Stage12Error):
            scan(rechain(bad))
    # Real opener rereads bytes, not a previously computed sampling verdict.
    path = root / "events" / f"{events[sample_index]['seq']:020d}.json"
    with path.open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(a.c.Stage12Error):
        runtime.reopen_completed(root, p, plan, start)


def test_AP24_additive_timing_persists_and_joins_actual_events(tmp_path):
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_timing as timing
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_checkpoints as cp,
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_journal as journal,
    )

    observer = timing.SamplingTiming(
        tmp_path / "telemetry", phase_count=1, interval_seconds=0.05
    )
    p, plan, start, result, root = run_phase(tmp_path, observer=observer)
    observer.close()
    rows = []
    prefix = cp.read_prefix(
        tmp_path / "telemetry", record_consumer=lambda n, row: rows.append(row)
    )
    assert not prefix["incomplete"] and rows
    original = {
        e["seq"]: e for e in journal.read_events(root, a.digest(start), contract=a)
    }
    async_rows = [r for r in rows if r["row_kind"] == "PERIODIC_ASYNC"]
    assert len(async_rows) == result["sampling_segments"][0]["witnessed"]["value"]
    for row in async_rows:
        timing.verify_sampling_association(
            row,
            original[row["sample_event_seq"]],
            phase_id=1,
            ack_event=original[row["ack_event_seq"]],
        )
        assert (
            row["future_used"] is False and row["future_finished_observed_ns"] is None
        )
        assert (
            row["observed_ns"]
            <= row["enqueued_ns"]
            <= row["writer_entry_ns"]
            <= row["sample_header_ns"]
            <= row["append_complete_ns"]
            <= row["event_ack_publish_ns"]
            <= row["ack_witness_header_ns"]
            <= row["ack_witness_reopened_ns"]
            <= row["pair_action_return_ns"]
            <= row["pair_post_action_complete_ns"]
            <= row["credit_released_ns"]
        )


def test_AP25_controls_and_required_comparison_through_opener(tmp_path):
    p, plan, start, result, root = run_phase(tmp_path, with_control=True)
    assert result["campaign_counts"]["durable_valid_data"]["value"] == 2
    assert result["campaign_counts"]["control_attempt_starts"]["value"] == 1
    assert (
        len(
            list(
                __import__(
                    "safe_geocoding_pipeline.preprocessing.stages.s12_public_journal",
                    fromlist=["read_array"],
                ).read_array(root / "repeat_comparison.json")
            )
        )
        == 1
    )


def test_AP25_negative_is_rejection_not_sampling_failure(tmp_path):
    p, plan, start, result, root = run_phase(tmp_path, malformed=True)
    assert result["sampling_segments"][-1]["complete"]
    assert result["campaign_counts"]["durable_terminal_failure"]["value"] >= 1
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as j

    finals = [
        e["body"]
        for e in j.read_events(root, a.digest(start), contract=a)
        if e["kind"] == "ATTEMPT_FINALIZED"
    ]
    assert finals and all(e["outcome"]["value"] == "CONTRACT_FAILURE" for e in finals)
    from safe_geocoding_pipeline.preprocessing.stages import s12_response as response

    originals = list((root / "attempts").rglob("*.zst"))
    assert originals
    for path in originals:
        assert (
            response.decompress(
                io.read(path), length=7, expected_hash=a.c.sha(b"{broken")
            )
            == b"{broken"
        )
    validations = [
        io.metadata(io.read(f))
        for f in (root / "attempts").rglob("call_*_validation.json")
    ]
    assert validations and all(
        v["reason_code"] == "RESPONSE_CONTRACT_INVALID" for v in validations
    )
    ledgers = list(j.read_array(root / "work_ledger.json"))
    assert all(row["state"] in ("TERMINAL", "UNBEGUN") for row in ledgers)
    assert (root / "_WRITER_RELEASED.json").exists()
    assert (root / "_SEGMENT_SEALED").exists()


def test_AP18_AP21_clean_same_block_epochs_preserve_cumulative_evidence(tmp_path):
    data = ap_inputs()
    p, plan, start, rows, inventory, bound = data
    budget = plan["sampling_budget"]
    budget["maximum_segments"] = 2
    A = (plan["budgets"]["active_duration_ms"] + 49) // 50 + 4
    F = 4 * A + 16
    inventory_count = 16
    budget.update(
        maximum_observations=A,
        additional_event_tokens=2 * A + 8,
        additional_file_data_bytes=4096 * F + inventory_count * (512 * F + 4096),
        additional_file_entries=F + inventory_count,
    )
    start["plan_sha256"] = a.digest(plan)
    first = tmp_path / "first"
    first.mkdir(mode=0o700)
    *_, root = run_phase(first, phase_inputs=data, pause=True)
    second = tmp_path / "second"
    second.mkdir(mode=0o700)
    p, plan, start, result, newroot = run_phase(
        second, phase_inputs=data, predecessor=root
    )
    assert len(result["sampling_segments"]) == 2
    assert all(v["complete"] for v in result["sampling_segments"])
    assert result["campaign_counts"]["durable_valid_data"]["value"] == 2
    assert len(result["segment_snapshot_hashes"]) == 2
    assert (root / "measurement_event_prefix.json").exists()
    assert not (newroot / "measurement_event_prefix.json").exists()


def test_AP13_hard_exit_child(tmp_path, monkeypatch):
    """Invoked only by the frozen external crash controller; guards autouse."""
    import os

    stage = os.environ.get("AP1_TEST_CRASH_STAGE")
    if stage is None:
        pytest.skip("external bounded crash controller only")
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_sampling as sm
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as j
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_recovery as recovery,
    )

    def exit_now():
        os._exit(86)

    if stage in ("RESERVE", "BEFORE_QUERY"):
        original = sm.Sampler._reserve

        def reserve(self, *args, **kwargs):
            value = original(self, *args, **kwargs)
            if value is not None:
                exit_now()
            return value

        monkeypatch.setattr(sm.Sampler, "_reserve", reserve)
    elif stage in ("IMMUTABLE_ENQUEUED", "FINAL_ENQUEUED"):
        original = sm.Sampler.acquire

        def acquire(self, final=False):
            value = original(self, final)
            if value and (stage == "IMMUTABLE_ENQUEUED" or final):
                exit_now()
            return value

        monkeypatch.setattr(sm.Sampler, "acquire", acquire)
    elif stage in (
        "WRITER_HELD",
        "SAMPLE_READBACK",
        "ACK_READY",
        "WITNESS_READBACK",
        "CLOSE_READBACK",
    ):
        original = j.Journal.event

        def event(self, kind, *args, **kwargs):
            if (stage == "WRITER_HELD" and kind == "RESOURCE_SAMPLE") or (
                stage == "ACK_READY" and kind == "SAMPLE_ACK"
            ):
                exit_now()
            value = original(self, kind, *args, **kwargs)
            if (
                (stage == "SAMPLE_READBACK" and kind == "RESOURCE_SAMPLE")
                or (stage == "WITNESS_READBACK" and kind == "SAMPLE_ACK")
                or (stage == "CLOSE_READBACK" and kind == "SAMPLING_CLOSE")
            ):
                exit_now()
            return value

        monkeypatch.setattr(j.Journal, "event", event)
    elif stage == "CREDIT_RELEASED":
        original = sm.Sampler.after_turn

        def after(self):
            pending = self.pending_release is not None
            value = original(self)
            if pending:
                exit_now()
            return value

        monkeypatch.setattr(sm.Sampler, "after_turn", after)
    elif stage == "CUT":
        original = sm.Sampler.probe_cut

        def cut(self):
            value = original(self)
            if self.cut is not None:
                exit_now()
            return value

        monkeypatch.setattr(sm.Sampler, "probe_cut", cut)
    elif stage == "SNAPSHOT_SEALED":
        original = recovery.write_snapshot

        def snapshot(*args, **kwargs):
            value = original(*args, **kwargs)
            exit_now()
            return value

        monkeypatch.setattr(recovery, "write_snapshot", snapshot)
    elif stage == "REPORT_PERSISTED":
        original = j.Journal.write

        def write(self, name, *args, **kwargs):
            value = original(self, name, *args, **kwargs)
            if name == "campaign_report.json":
                exit_now()
            return value

        monkeypatch.setattr(j.Journal, "write", write)
    elif stage == "BEFORE_RELEASE":
        monkeypatch.setattr(j.Writer, "release", lambda *a, **k: exit_now())
    else:
        pytest.fail("unknown static crash selection")
    run_phase(tmp_path)
    pytest.fail("selected crash boundary not reached")


@pytest.mark.parametrize("kind", ["RESOURCE_SAMPLE", "SAMPLE_ACK"])
def test_AP11_AP24_uncertain_readback_retains_partial_timing(
    tmp_path, monkeypatch, kind
):
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_journal as journal,
    )
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_timing as timing
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_checkpoints as cp,
    )

    observer = timing.SamplingTiming(
        tmp_path / "telemetry", phase_count=1, interval_seconds=0.05
    )
    original = journal.Journal._readback
    fired = [False]

    def readback(self, path, raw):
        if (
            not fired[0]
            and path.parent.name == "events"
            and (b'"kind":"' + kind.encode() + b'"') in raw
        ):
            fired[0] = True
            raise OSError(5)
        return original(self, path, raw)

    monkeypatch.setattr(journal.Journal, "_readback", readback)
    run_phase(tmp_path, observer=observer, uncertain=True)
    summary = observer.close()
    rows = []
    prefix = cp.read_prefix(
        tmp_path / "telemetry", record_consumer=lambda n, row: rows.append(row)
    )
    assert fired[0] and not prefix["incomplete"]
    partial = [
        r
        for r in rows
        if r["row_kind"] == "PERIODIC_ASYNC" and r["outcome"] == "UNCERTAIN"
    ]
    assert partial and summary["partial_timing_rows"] >= 1
    assert not summary["final_timing_coverage_complete"]
    assert all(r["credit_released_ns"] is None for r in partial)


def test_AP21_selected_last_segment_cannot_authorize_another_open(tmp_path):
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_recovery as recovery,
    )

    data = ap_inputs()
    p, plan, start, rows, inventory, bound = data
    p, plan, start, result, root = run_phase(tmp_path, phase_inputs=data, pause=True)
    assert plan["sampling_budget"]["maximum_segments"] == 1

    def denied(*args):
        raise AssertionError("segment bound must reject before receipt iteration")

    with pytest.raises(a.c.Stage12Error):
        recovery.clean_continuation(
            root,
            start,
            p,
            plan,
            authority=TestOnlyAuthority(bound),
            new_segment_authority=H,
            now_ns=0,
            work_factory=lambda: iter(rows),
            verify_receipt=denied,
        )
