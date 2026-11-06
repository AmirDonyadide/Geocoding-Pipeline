"""Invented diagnostic orchestration; real source validators and audit-hook child."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest
from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_public_checkpoints as checkpoints,
    s12_public_diagnostics as diagnostics,
    s12_public_matrix as matrix,
    s12_public_operations as o,
    s12_public_response as validation,
    s12_public_runtime as runtime,
    s12_public_scheduler as scheduler,
    s12_public_timing as timing,
    s12_retrieval_contract as c,
    s12_storage as io,
    s12_transport as transport,
)
from stage12_synthetic import body
from test_stage12_public_operations_v2 import (
    FakeAuthority,
    FakeClock,
    H,
    KEY,
    inputs,
    rebind,
)
from test_stage12_public_matrix import configuration
from test_stage12_public_operational_audit import capture

spec = importlib.util.spec_from_file_location(
    "replay_scenario_test",
    Path(__file__).resolve().parents[1] / "scripts/stage12_replay_scenario.py",
)
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


@pytest.fixture(autouse=True)
def deny(monkeypatch, request):
    def blocked(*a, **kw):
        raise AssertionError("TEST_NETWORK_PROVIDER_PROCESS_DENIED")

    for name in ("create_connection", "getaddrinfo", "gethostbyname"):
        monkeypatch.setattr(socket, name, blocked)
    for name in ("connect", "connect_ex", "bind", "sendto"):
        monkeypatch.setattr(socket.socket, name, blocked)
    monkeypatch.setattr(transport.Secret, "runtime", blocked)
    monkeypatch.setattr(transport.Secret, "private_file", blocked)
    # Only the fixed child below may spawn; it installs the actual audit policy.
    if request.node.name != "test_actual_installed_audit_and_reservation":
        for name in ("Popen", "run", "call", "check_call", "check_output"):
            monkeypatch.setattr(subprocess, name, blocked)


def closed(tmp_path, monkeypatch, *, late=False, negative=False, control=False):
    profile, plan, start, work, inventory = inputs(64 if negative else 2)
    if negative:
        work = deepcopy(configuration()["campaigns"][0]["work"])
        rebind(profile, plan, start, work)
    clock = FakeClock()
    authority = FakeAuthority()
    control_adapters = {}
    if control:
        item = configuration()["campaigns"][-1]
        profile, plan, work = item["profile"], item["plan"], item["work"]
        clock = runtime.Clock()
        now = datetime.now(timezone.utc)
        lo = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        hi = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        profile["operator_allowance"].update(valid_from=lo, valid_until=hi)
        plan.update(window_start=lo, window_end=hi)
        start["created_utc"] = clock.utc()
        rebind(profile, plan, start, work)

        class ControlAuthority(FakeAuthority):
            def require(self, purpose, evidence, context):
                if purpose == "control_recipe":
                    assert (
                        evidence == o.digest(matrix.check_descriptor())
                        and context in plan["control_recipes"]
                    )
                elif purpose == "transport_profile":
                    assert (
                        evidence == profile["transport_profile_sha256"]
                        and context == profile
                    )
                else:
                    super().require(purpose, evidence, context)

        authority = ControlAuthority()
        control_adapters = matrix.adapters(plan)
    box = {}
    old = scheduler.Coordinator.__init__

    def init(self, *a, **kw):
        old(self, *a, **kw)
        box["ctl"] = self

    monkeypatch.setattr(scheduler.Coordinator, "__init__", init)
    observer = timing.PublicTiming(tmp_path / "timing", phase_count=1)
    root = tmp_path / "phase"

    def payload(w):
        return b"{" if negative and w["work_id"] == 2 else body([])

    def dispatch(w, target, hooks):
        hooks.started(clock.now_ns())
        hooks.emit(lambda: None if control else clock.advance(1_000_000), lambda: None)
        if late and w["work_id"] == 1:
            clock.advance(201_000_000)
        value = capture(payload(w))
        hooks.signal(
            value.status, value.outcome, value.reason, value.retry_after_seconds
        )
        if not control:
            clock.advance(1_000_000)
        hooks.completed(value)
        return value

    report = cli.run_operations_block(
        profile,
        plan,
        start,
        work_factory=lambda: iter(work),
        output=root,
        block_id=1,
        authority=authority,
        clock=clock,
        dispatch=dispatch,
        runtime_inventory=inventory,
        runtime_key=KEY,
        control_adapters=control_adapters,
        monitor=None,
        free_bytes=lambda: 2**42,
        segment_authority=H,
        writer_exclusion_evidence=H,
        epoch=H,
        writer_release_evidence=H,
        timing_observer=observer,
        public_validation=validation.Validation(),
    )
    item = {"plan": plan, "profile": profile, "work": work}
    return dict(
        root=root,
        item=item,
        start=start,
        report=report,
        ctl=box["ctl"],
        clock=clock,
        observer=observer,
        payload=payload,
        negative=negative,
        controls=control_adapters,
    )


def finish(case, *, opener=None, persist_error=False, first=None):
    root = case["root"]
    facts = {}
    records = {}
    first = [] if first is None else first

    def note(x):
        if not first:
            first.append(x)

    def classify(e):
        family, code, errno = diagnostics.classify(e)
        return dict(family=family, code=code, errno=errno)

    def safety():
        h.live_safety(
            case["ctl"], root=case["root"], isolation=True, check=lambda: None
        )

    def verify():
        facts.update(
            h.verify_closed(
                root,
                case["item"],
                case["start"],
                validation_sha256=o.digest(validation.descriptor()),
                check=lambda: None,
                expected_payload=case["payload"],
            )
        )
        return h.assess(
            facts,
            negative=case["negative"],
            attempts=case["report"]["campaign_counts"]["attempt_starts"]["value"],
            item=case["item"],
            selection=matrix.binding(H),
        )

    def checkpoint():
        case["observer"].boundary()
        state = case["observer"].snapshot()
        io.write(root.parent / "TIMING.json", c.canonical(state))
        return state

    def persist(kind, row):
        if persist_error:
            raise OSError("TEST_ONLY_WRITE_FAILURE")
        records[kind] = deepcopy(row)
        io.write(root.parent / (kind + ".json"), c.canonical(row))

    def real_open():
        assert (root.parent / "RESULT.json").exists() and (
            root.parent / "TIMING.json"
        ).exists()
        runtime.reopen_completed(
            root,
            case["item"]["profile"],
            case["item"]["plan"],
            case["start"],
            control_adapters=case["controls"],
        )
        return True

    result = h.conclude(
        row={
            "expected": "INCOMPLETE_MALFORMED_WORK_2"
            if case["negative"]
            else "COMPLETE",
            "report_complete": case["report"]["report_complete"],
        },
        safety=safety,
        verify=verify,
        opener=opener or real_open,
        revalidate=lambda: c.require(
            h.fresh_binding(root, check=lambda: None) == facts["source_binding"]
        ),
        checkpoint=checkpoint,
        persist=persist,
        classify=classify,
        on_failure=note,
    )
    case["observer"].close()
    return result, records, first


def test_normal_pass_and_preopener_timing_associations(tmp_path, monkeypatch):
    case = closed(tmp_path, monkeypatch)
    row, records, first = finish(case)
    assert row["verdict"] == "PASS" and row["safe_to_continue"] and not first
    assert records["RESULT"]["actual_opener_rejected"] is None
    assert records["RESULT"]["verdict"] == "PENDING_OPENER"
    assert records["RESULT"]["candidate_verdict"] == "PASS"
    assert row["actual_opener_rejected"] is False
    linked = []

    def associate(n, row):
        fields = dict(zip(checkpoints.PUBLIC_FIELDS, row, strict=True))
        event = json.loads(
            (case["root"] / "events" / f"{fields['event_seq']:020d}.json").read_bytes()
        )
        timing.verify_association(row, event, phase_id=1)
        linked.append(n)

    prefix = checkpoints.read_prefix(tmp_path / "timing", record_consumer=associate)
    assert linked and not prefix["incomplete"]


def test_sampling_incomplete_then_independent_pass_preserves_first(
    tmp_path, monkeypatch
):
    one = tmp_path / "one"
    one.mkdir(mode=0o700)
    case = closed(one, monkeypatch, late=True)
    row, records, first = finish(case)
    assert row["verdict"] == "SAMPLING_INCOMPLETE" and row["safe_to_continue"]
    assert (
        row["actual_opener_rejected"] is True
        and records["RESULT"]["report_complete"] is False
    )
    assert first[0]["family"] == "SAMPLING_INCOMPLETE"
    two = tmp_path / "two"
    two.mkdir(mode=0o700)
    case2 = closed(two, monkeypatch)
    row2, _, retained = finish(case2, first=first)
    assert (
        row2["verdict"] == "PASS"
        and retained is first
        and first[0]["family"] == "SAMPLING_INCOMPLETE"
    )


@pytest.mark.parametrize(
    "unsafe", ["writer", "slot", "sampler", "isolation", "deadline", "fence"]
)
def test_unsafe_stops_before_original_validation(tmp_path, monkeypatch, unsafe):
    case = closed(tmp_path, monkeypatch)
    ctl = case["ctl"]
    if unsafe == "writer":
        ctl.writer.failed.set()
    elif unsafe == "slot":
        ctl.slots[("TEST", 1)] = object()
    elif unsafe == "sampler":
        ctl.sample_busy = True
    elif unsafe == "fence":
        ctl.writer.closure_fence.identity = (-1, -1)

    def safety():
        h.live_safety(
            ctl,
            root=case["root"],
            isolation=unsafe != "isolation",
            check=lambda: c.require(unsafe != "deadline", "REPLAY_DEADLINE"),
        )

    saved = []
    row = h.conclude(
        row={"expected": "COMPLETE"},
        safety=safety,
        verify=lambda: pytest.fail("UNSAFE_VERIFICATION_REACHED"),
        opener=lambda: pytest.fail("UNSAFE_OPENER_REACHED"),
        revalidate=lambda: None,
        checkpoint=lambda: {"persistence_complete": False},
        persist=lambda k, v: saved.append(k),
        classify=lambda e: {"family": "SAFE_STATIC_TEST_FAILURE"},
    )
    case["observer"].close()
    assert (
        not row["safe_to_continue"]
        and row["verdict"] == "UNSAFE"
        and saved == ["RESULT", "OUTCOME"]
    )


def test_sampling_first_failure_survives_result_write_error(tmp_path, monkeypatch):
    case = closed(tmp_path, monkeypatch, late=True)
    first = []
    with pytest.raises(OSError):
        finish(case, persist_error=True, first=first)
    case["observer"].close()
    assert first[0]["family"] == "SAMPLING_INCOMPLETE"


@pytest.mark.parametrize("late", [False, True])
def test_exact_negative_requires_sampling_and_specific_opener_gate(
    tmp_path, monkeypatch, late
):
    case = closed(tmp_path, monkeypatch, negative=True, late=late)
    row, records, first = finish(case)
    assert row["actual_opener_rejected"] is True
    assert row["verdict"] == (
        "NEGATIVE_SAMPLING_INCOMPLETE" if late else "EXPECTED_NEGATIVE_PASS"
    )
    assert bool(first) == late and records["RESULT"]["originals_validated"]
    assert records["RESULT"]["verdict"] == "PENDING_OPENER"
    assert records["RESULT"]["candidate_verdict"] == (
        "NEGATIVE_SAMPLING_INCOMPLETE" if late else "EXPECTED_NEGATIVE_PASS"
    )


def test_same_code_arbitrary_exception_is_not_expected_negative(tmp_path, monkeypatch):
    case = closed(tmp_path, monkeypatch, negative=True)

    def wrong():
        raise c.Stage12Error("S12_PUBLIC_OPERATIONS_INVALID")

    row, _, first = finish(case, opener=wrong)
    assert row["verdict"] == "UNSAFE" and not row["safe_to_continue"] and first


def test_changed_original_cannot_be_sampling_only(tmp_path, monkeypatch):
    case = closed(tmp_path, monkeypatch, late=True)
    path = case["root"] / "repeat_comparison.json"
    path.write_bytes(b"[]\nchanged")
    row, _, first = finish(case)
    assert row["verdict"] == "UNSAFE" and not row["originals_validated"] and first


def test_actual_installed_audit_and_reservation(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    child = r"""
import importlib.util,json,os,socket,sys
from pathlib import Path
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io,s12_transport as transport
repo,parent=map(Path,sys.argv[1:]);spec=importlib.util.spec_from_file_location('guard',repo/'scripts/stage12_replay_scenario.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
out=parent/'new';secret=parent/'TEST_ONLY_WITHHELD';secret.write_bytes(b'INVENTED_NOT_PROTECTED')
g=h.AccessGuard(allowed=(repo,out,Path(sys.prefix),Path(sys.base_prefix)),output=out,proc_self=Path('/proc/self'),cgroup_root=Path('/sys/fs/cgroup'),proc_names=(),cgroup_names=(),maximum_creations=50000)
sys.addaudithook(g.audit);transport.Secret.runtime=transport.Secret.private_file=g.denied
io.reserve(out)
fd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);os.fsync(fd);os.close(fd)
def denied(call):
 try:call()
 except PermissionError:return
 raise AssertionError('ACCESS_NOT_DENIED')
denied(lambda:secret.read_bytes());denied(lambda:os.open(parent,os.O_RDONLY));denied(lambda:os.open(parent,os.O_RDONLY|os.O_DIRECTORY));denied(lambda:os.open(parent,os.O_RDWR|os.O_DIRECTORY|os.O_NOFOLLOW));denied(lambda:os.open(parent.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW));denied(lambda:socket.getaddrinfo('INVALID_TEST_ONLY',443));denied(lambda:transport.Secret.runtime())
print(json.dumps({'actual_storage_reserve_fsync':True,'near_misses_denied':7}))
"""
    env = dict(os.environ, PYTHONPATH=str(repo / "src"), PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        [sys.executable, "-B", "-c", child, str(repo), str(tmp_path)],
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "actual_storage_reserve_fsync": True,
        "near_misses_denied": 7,
    }


def test_real_control_receipts_pairs_and_opener(tmp_path, monkeypatch):
    case = closed(tmp_path, monkeypatch, control=True)
    row, records, first = finish(case)
    assert row["originals_validated"] and row["safe_to_continue"]
    assert row["verdict"] in ("PASS", "SAMPLING_INCOMPLETE")
    assert case["report"]["campaign_counts"]["control_attempt_starts"]["value"] == 8
    assert records["RESULT"]["originals_validated"]
    verified = h.verify_closed(
        case["root"],
        case["item"],
        case["start"],
        validation_sha256=o.digest(validation.descriptor()),
        check=lambda: None,
        expected_payload=case["payload"],
    )
    assert len(verified["control_pairs"]) == 4 and all(
        x["equal"] for x in verified["control_pairs"]
    )
    assert bool(first) == (row["verdict"] == "SAMPLING_INCOMPLETE")


def test_other_latency_defect_not_sampling_only(tmp_path, monkeypatch):
    case = closed(tmp_path, monkeypatch, late=True)
    f = h.verify_closed(
        case["root"],
        case["item"],
        case["start"],
        validation_sha256=o.digest(validation.descriptor()),
        check=lambda: None,
        expected_payload=case["payload"],
    )
    selection = matrix.binding(H)
    f["block"]["peaks"]["writer_wait_ms"] = selection["max_writer_wait_ms"] + 1
    with pytest.raises(c.Stage12Error, match="REPLAY_WRITER_GATE_FAILED"):
        h.assess(f, negative=False, attempts=2, item=case["item"], selection=selection)
    case["observer"].close()


def test_row_bound_stops_before_materializing_extra_history():
    consumed = []

    def rows():
        for i in range(1000000000):
            consumed.append(i)
            yield {"i": i}

    with pytest.raises(c.Stage12Error, match="REPLAY_ROW_BOUND_EXCEEDED"):
        h.bounded_rows(rows(), 64)
    assert consumed == list(range(65))


def test_rejected_opener_does_not_hide_between_stage_mutation(tmp_path, monkeypatch):
    case = closed(tmp_path, monkeypatch, late=True)

    def changed():
        try:
            runtime.reopen_completed(
                case["root"],
                case["item"]["profile"],
                case["item"]["plan"],
                case["start"],
            )
        except c.Stage12Error:
            path = case["root"] / "repeat_comparison.json"
            path.write_bytes(path.read_bytes() + b" ")
            raise

    row, _, first = finish(case, opener=changed)
    assert row["verdict"] == "UNSAFE" and not row["safe_to_continue"]
    assert first[0]["family"] == "SAMPLING_INCOMPLETE"


def test_real_sequence_does_not_erase_first_or_advance_unsafe():
    sequence = h.ScenarioSequence([{"name": "one"}, {"name": "two"}, {"name": "three"}])
    reached = []
    for index, scenario in sequence.pending():
        reached.append(scenario["name"])
        failure = (
            {"family": "SAMPLING_INCOMPLETE"}
            if index == 1
            else {"family": "WRITER_UNSAFE"}
        )
        sequence.note(failure)
        sequence.record(
            {
                "name": scenario["name"],
                "unexpected_failure": failure,
                "safe_to_continue": index == 1,
            }
        )
    assert reached == ["one", "two"] and sequence.first_failure == {
        "family": "SAMPLING_INCOMPLETE"
    }


def test_raw_exception_text_never_retained():
    canary = "INVENTED_SECRET_MUST_NOT_ECHO"

    def classify(e):
        family, code, errno = diagnostics.classify(e)
        return dict(family=family, code=code, errno=errno)

    records = []
    row = h.conclude(
        row={"expected": "COMPLETE"},
        safety=lambda: None,
        verify=lambda: pytest.fail("RUN_ERROR_VERIFIED"),
        opener=lambda: pytest.fail("RUN_ERROR_OPENED"),
        revalidate=lambda: None,
        checkpoint=lambda: {"persistence_complete": False},
        persist=lambda k, v: records.append(deepcopy(v)),
        classify=classify,
        run_error=RuntimeError(canary),
    )
    assert not row["safe_to_continue"] and canary not in json.dumps(records)


def test_missing_hard_resource_row_not_sampling_only(tmp_path, monkeypatch):
    case = closed(tmp_path, monkeypatch, late=True)
    events = list(h.journal.read_events(case["root"], o.digest(case["start"])))
    prefix = [
        e
        for e in events
        if e["seq"]
        <= json.loads((case["root"] / "block_report.json").read_bytes())[
            "input_last_event_seq"
        ]
    ]
    valid = h.measurement(
        lambda: iter(prefix),
        maximum_events=case["item"]["plan"]["budgets"]["event_count"],
        period_ns=100000000,
    )
    assert valid["schedule_gap_count"] > 0
    with pytest.raises(c.Stage12Error, match="REPLAY_HARD_RESOURCE_ROWS_INVALID"):
        h.measurement(
            lambda: (
                e
                for e in prefix
                if not (
                    e["kind"] == "RESOURCE" and e["body"]["cause"] == "START_RESERVE"
                )
            ),
            maximum_events=case["item"]["plan"]["budgets"]["event_count"],
            period_ns=100000000,
        )
    case["observer"].close()


@pytest.mark.parametrize(
    "validate", [h.comparison_row, lambda row: o.validate_type(row, "WorkLedgerRow")]
)
def test_malformed_rows_rejected_before_population_retention(validate):
    consumed = []

    def rows():
        for i in range(64):
            consumed.append(i)
            yield {"unrecognized": "INVENTED" * 1024}

    with pytest.raises(c.Stage12Error):
        h.bounded_rows(rows(), 64, validate=validate)
    assert consumed == [0]


def test_same_bytes_inode_replacement_after_opener_is_not_adopted(
    tmp_path, monkeypatch
):
    case = closed(tmp_path, monkeypatch, late=True)

    def replaced():
        try:
            runtime.reopen_completed(
                case["root"],
                case["item"]["profile"],
                case["item"]["plan"],
                case["start"],
            )
        except c.Stage12Error:
            original = case["root"] / "repeat_comparison.json"
            replacement = case["root"] / "TEST_ONLY_REPLACEMENT"
            replacement.write_bytes(original.read_bytes())
            replacement.chmod(0o600)
            assert replacement.stat().st_ino != original.stat().st_ino
            os.replace(replacement, original)
            raise

    row, _, first = finish(case, opener=replaced)
    assert row["verdict"] == "UNSAFE" and not row["safe_to_continue"]
    assert first[0]["family"] == "SAMPLING_INCOMPLETE"
