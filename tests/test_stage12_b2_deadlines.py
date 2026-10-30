"""Corrected R09 acceptance tests; original defect reproduction is preserved externally."""

import pytest
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_retrieval_contract as c,
    s12_storage as io,
    s12_b2_audit as audit,
)
from stage12_b2_synthetic import World, H, KEY
from test_stage12_b2_controls import Control
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_b2_contract as b,
    s12_b2_operations as o,
    s12_b2_pipeline as pipe,
    s12_response as response,
    s12_transport as transport,
)


@pytest.mark.parametrize(
    "delay_ms,reported_ms,accepted", [(5, 5, False), (5, 1, False), (1, 1, True)]
)
def test_R09_control_deadline_enforced_and_reopened(
    tmp_path, delay_ms, reported_ms, accepted
):
    w = World(tmp_path, count=1)
    profile, plan, start, science, admission, rows = w.inputs()
    recipe = {
        "recipe_id": 1,
        "recipe_sha256": H,
        "implementation_contract_sha256": H,
        "transport_profile_sha256": profile["transport_profile_sha256"],
        "purpose": "HEALTH_CHECK",
        "max_http_attempts_per_invocation": 1,
        "max_duration_ms": 1,
    }
    plan["control_recipes"] = [recipe]
    plan["budgets"].update(required_control_observations=1, control_http_attempts=1)
    plan["blocks"][0]["budget"].update(
        required_control_observations=1, control_http_attempts=1
    )
    rows.append(
        {
            "work_id": 2,
            "block_id": 1,
            "kind": "SERVICE_CONTROL",
            "query_semantic_id": None,
            "result_limit": None,
            "repetition": None,
            "recipe_id": 1,
            "retry_spacing_key": H,
        }
    )
    plan["blocks"][0]["last_work_id"] = 2
    plan["work_manifest_sha256"] = o.manifest_digest(rows)
    science["workload_sha256"] = b.digest(plan)
    start["plan_sha256"] = b.digest(plan)
    start["scientific_campaign_start_sha256"] = b.digest(science)
    admission["campaign_start_sha256"] = b.digest(science)
    admission["operations_campaign_sha256"] = b.digest(start)
    admission["bootstrap_acquisition_sha256"] = pipe.prepare_bootstrap(
        tmp_path / "control_bootstrap",
        records=w.records,
        raw_factory=lambda: (lambda: w.records.raw(H),),
        clock=w.clock,
        profile=profile,
        plan=plan,
        start=start,
        segment_nonce=admission["segment_nonce"],
        epoch_id=admission["epoch_id"],
        authority=w.gate,
        authority_hash=H,
        writer_release_evidence=w.releases[admission["segment_nonce"]],
        secret_guard=lambda raw: response.secret_guard(raw, KEY),
    )

    def dispatch(work, target, hooks):
        if work["kind"] == "DATA":
            return w.dispatch(work, target, hooks)
        hooks.started(w.clock.now_ns())
        hooks.emit(lambda: None, lambda: None)
        w.clock.advance(delay_ms * 1_000_000)
        raw = b'{"synthetic_health":"ok"}'
        cap = transport.Capture(
            "VALIDATION_REQUIRED",
            "OK",
            200,
            "application/json",
            "absent",
            None,
            raw,
            len(raw),
            reported_ms,
        )
        hooks.completed(cap)
        return cap

    def run():
        return pipe.run_segment(
            tmp_path / "segment",
            profile,
            plan,
            start,
            science,
            admission,
            catalog=w.catalog,
            work_factory=lambda: iter(rows),
            gate=w.gate,
            clock=w.clock,
            dispatch=dispatch,
            runtime_inventory=w.runtime,
            key=KEY,
            rules=w.rules,
            control_adapters={1: Control()},
            free_bytes=lambda: 2**40,
            writer_release_evidence=w.releases[admission["segment_nonce"]],
            close_segment=w.close_segment,
        )

    if accepted:
        report = run()
        assert report["report_complete"]
        assert report["counts"]["control_attempt_starts"]["value"] == 1
    else:
        with pytest.raises(c.Stage12Error, match="B2_CAMPAIGN_INCOMPLETE"):
            run()
        assert not (tmp_path / "segment/_SEGMENT_SEALED").exists()
    unit = tmp_path / "segment/attempts/00000000000000000002_01"
    terminal = audit.reopen_control(unit, recipe, Control())
    assert terminal["outcome"] == (
        "CONTROL_SUCCESS" if accepted else "CONTRACT_FAILURE"
    )
    assert terminal["reason"] == ("OK" if accepted else "TIMEOUT")
    timing = io.metadata(io.read(unit / "control_timing.json"))
    assert (
        timing["completed_mono_ns"] - timing["started_mono_ns"] == delay_ms * 1_000_000
    )
    assert (unit / "raw.zst").exists()
    assert (unit / "verification.json").exists() == accepted
    if accepted:
        from safe_geocoding_pipeline.preprocessing.stages import s12_b2_diagnostics as d

        summary = d.attempt_summary(tmp_path / "segment", b.digest(start))["by_kind"]
        assert (
            summary["DATA"]["charged_attempts"]
            == summary["SERVICE_CONTROL"]["charged_attempts"]
            == 1
        )
        control = summary["SERVICE_CONTROL"]
        assert control["category_totals_exact"] and control[
            "application_bytes_observed"
        ]["value"] == len(b'{"synthetic_health":"ok"}')
        assert control["categories"][0]["attempts"]["value"] == 1


from test_stage12_public_scheduler import FakeClock
from stage12_synthetic import body
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_transport as t,
    s12_operations as v1,
)


@pytest.mark.parametrize("expire_before_emit", [False, True])
def test_R09_fake_socket_narrows_timeout_and_blocks_late_emit(
    monkeypatch, expire_before_emit
):
    status = 200
    from email.message import Message

    clock = FakeClock()
    calls = []
    raw = body([])

    class Socket:
        def settimeout(self, timeout):
            calls.append(("timeout", timeout))

        def shutdown(self, *_):
            calls.append(("shutdown",))

    class Reply:
        length = 0

        def __init__(self):
            self.status = status
            self.headers = Message()
            self.headers["Content-Type"] = "application/json"
            self.headers["Content-Length"] = str(len(raw))
            self.headers["Retry-After"] = "31"
            self.done = False

        def getheader(self, key):
            return self.headers.get(key)

        def read1(self, maximum):
            assert status == 200
            if self.done:
                return b""
            self.done = True
            return raw

    class Connection:
        sock = Socket()

        def __init__(self, *_a):
            pass

        def connect(self):
            calls.append(("connect",))

        def putrequest(self, method, target, **kwargs):
            calls.append((method, target, kwargs))

        def putheader(self, name, value):
            calls.append((name, value))

        def endheaders(self):
            calls.append(("write",))

        def getresponse(self):
            return Reply()

        def close(self):
            calls.append(("close",))

    class Timer:
        def __init__(self, timeout, callback):
            assert timeout == 0.001

        def start(self):
            pass

        def cancel(self):
            pass

    class Hooks:
        def attempt_deadline_ns(self, started, maximum):
            assert maximum == 60_000_000_000
            return started + 1_000_000

        def started(self, ns):
            calls.append(("started", ns))

        def emit(self, write, check):
            calls.append(("commit",))
            if expire_before_emit:
                clock.advance(2_000_000)
            check()
            write()

        def signal(self, status, outcome, reason, retry):
            calls.append(("signal", status, retry))

        def completed(self, result):
            calls.append(("completed", result.status))

    monkeypatch.setattr(t, "require_goethe_nhr_slurm", lambda _: None)
    monkeypatch.setattr(t, "_Connection", Connection)
    monkeypatch.setattr(t.threading, "Timer", Timer)
    monkeypatch.setattr(t.time, "monotonic_ns", clock.now_ns)
    profile = t.TransportProfile(
        "https://synthetic.invalid", "127.0.0.1", bytes.fromhex(H), 8192, 16384
    )
    result = t.send(
        b"/v1/search?size=1&text=Berlin",
        profile,
        t.Secret.checked(KEY),
        v1.Operations(),
        hooks=Hooks(),
    )

    if expire_before_emit:
        assert result.status is None and result.reason == "TIMEOUT"
        assert ("write",) not in calls
    else:
        assert result.status == 200 and ("write",) in calls
    assert all(0 <= entry[1] <= 0.001 for entry in calls if entry[0] == "timeout")


@pytest.mark.parametrize("bad", [True, 0, 60_000_000_001])
def test_R09_deadline_cannot_widen_or_use_invalid_type(bad):
    class Hooks:
        def attempt_deadline_ns(self, *_):
            return bad

    with pytest.raises(c.Stage12Error):
        t.attempt_deadline_ns(0, v1.Operations(), Hooks())
