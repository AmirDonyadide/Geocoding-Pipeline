"""Public integration tests: invented bytes, fake authority and no live I/O."""

from pathlib import Path
import pytest
from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
from safe_geocoding_pipeline.preprocessing.stages import s12_public_runtime as r
from safe_geocoding_pipeline.preprocessing.stages import s12_public_response as v
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_public_operational_audit as oa,
)
from safe_geocoding_pipeline.preprocessing.stages import s12_public_audit as audit
from safe_geocoding_pipeline.preprocessing.stages import s12_public_operations as o
from safe_geocoding_pipeline.preprocessing.stages import s12_probe as probe
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_transport as t
from test_stage12_public_operations_v2 import (
    H,
    KEY,
    FakeClock,
    inputs,
    rebind,
    offline,  # noqa: F401 -- autouse offline denial fixture
)  # noqa: F401
from test_stage12_public_operational_audit import capture
from stage12_synthetic import body


@pytest.mark.parametrize("count", [4, 5, 9, 35, 131])
def test_1804272_repeat_join_batches_metadata_but_reopens_each_pair(
    tmp_path, monkeypatch, count
):
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as j
    from test_stage12_public_scheduler import run_offline

    active = False
    traversals = comparisons = payload_reads = 0
    stream = j.Journal.stream_array
    read_events = j.read_events
    read = io.read

    def counted_events(*a, **kw):
        nonlocal traversals
        if active:
            traversals += 1
        yield from read_events(*a, **kw)

    def counted_read(path, **kw):
        nonlocal payload_reads
        if active and path.suffix == ".zst":
            payload_reads += 1
        return read(path, **kw)

    def counted_stream(self, name, rows):
        nonlocal active, comparisons
        if name != "repeat_comparison.json":
            return stream(self, name, rows)

        def values():
            nonlocal comparisons
            for row in rows:
                comparisons += 1
                yield row

        active = True
        try:
            return stream(self, name, values())
        finally:
            active = False

    monkeypatch.setattr(j, "read_events", counted_events)
    monkeypatch.setattr(j.Journal, "stream_array", counted_stream)
    monkeypatch.setattr(io, "read", counted_read)
    campaign, root, (_, _, _, rows, _) = run_offline(tmp_path, count=count)
    expected = []
    for index, work in enumerate(rows):
        prior = next(
            (
                item
                for item in rows[:index]
                if (item["fixture_id"], item["result_limit"])
                == (work["fixture_id"], work["result_limit"])
            ),
            None,
        )
        if prior is not None:
            expected.append(
                {
                    "first_work_id": prior["work_id"],
                    "next_work_id": work["work_id"],
                    "equal": True,
                }
            )
    assert list(j.read_array(root / "repeat_comparison.json")) == expected
    assert comparisons == len(expected) > 0
    assert traversals == (comparisons + 127) // 128
    assert (
        payload_reads >= 2 * comparisons
    )  # Fresh raw bytes for both sides of every pair.
    assert campaign["report_complete"] and campaign["disposition"] == "COMPLETED"


def berlin_work():
    return dict(
        work_id=1,
        block_id=1,
        kind="DATA",
        fixture_id=next(
            f["fixture_id"]
            for f in probe.fixtures()
            if f["core"]["search_mode"] == "FULL_TEXT" and f["core"]["text"] == "Berlin"
        ),
        result_limit=1,
        repetition=0,
        recipe_id=None,
        retry_spacing_key=H,
    )


def warning_body():
    return dict(
        type="FeatureCollection",
        features=[],
        geocoding=dict(
            warnings=[v.WARNING],
            query={
                "text": "Berlin",
                "size": 1,
                "boundary.country": ["DEU"],
                "layers": ["locality"],
                "lang": {"name": "English"},
            },
        ),
    )


def test_public_exception_exact_and_legacy_still_rejects():
    row = berlin_work()
    raw = c.canonical(warning_body())
    assert v.shapes(raw, row) == ()
    with pytest.raises(c.Stage12Error):
        cli.public_shapes(raw)
    side = v.Validation().limitation(raw, row)
    assert side["exception_applied"] and not side["scientific_identity_verified"]
    assert side["raw_sha256"] == c.sha(raw).hex()


@pytest.mark.parametrize(
    "mutation",
    [
        "size",
        "other_fixture",
        "extra",
        "duplicate",
        "top",
        "error",
        "echo",
        "layers",
        "address",
        "country",
        "lang",
        "oversize",
        "malformed",
    ],
)
def test_exception_never_broadens(mutation):
    row = berlin_work()
    obj = warning_body()
    geo = obj["geocoding"]
    if mutation == "size":
        row["result_limit"] = 3
    if mutation == "other_fixture":
        row["fixture_id"] = next(
            f["fixture_id"]
            for f in probe.fixtures()
            if f["fixture_id"] != row["fixture_id"]
        )
    if mutation == "extra":
        geo["warnings"].append("other")
    if mutation == "duplicate":
        geo["warnings"] *= 2
    if mutation == "top":
        obj["warnings"] = geo.pop("warnings")
    if mutation == "error":
        geo["errors"] = ["failure"]
    if mutation == "echo":
        geo["query"]["text"] = "berlin"
    if mutation == "layers":
        geo["query"]["layers"] = ["locality", "locality"]
    if mutation == "address":
        geo["query"]["layers"] = ["address"]
    if mutation == "country":
        geo["query"]["boundary.country"] = ["DE"]
    if mutation == "lang":
        geo["query"]["lang"] = {}
    if mutation == "oversize":
        obj["features"] = [{}, {}]
    raw = b"{" if mutation == "malformed" else c.canonical(obj)
    with pytest.raises(c.Stage12Error):
        v.shapes(raw, row)


@pytest.mark.parametrize(
    "raw",
    [
        body([]),
        b'{"type":"FeatureCollection","features":[],"geocoding":{"warnings":[],"errors":[]}}',
    ],
)
def test_ordinary_public_validation_equivalent(raw):
    assert v.shapes(raw, berlin_work()) == cli.public_shapes(raw)


@pytest.mark.parametrize("secret", [False, True])
def test_versioned_capture_reopen_limitation_and_secret_guard(tmp_path, secret):
    profile, plan, start, rows, runtime = inputs(1)
    row = berlin_work()
    row["retry_spacing_key"] = row["fixture_id"]
    rows[:] = [row]
    rebind(profile, plan, start, rows)
    adapter = v.Validation()
    root = tmp_path / "attempt"
    oa.begin_data(root, profile, plan, start, row, 1, runtime, validation=adapter)
    raw = b'{"secret":"' + KEY + b'"}' if secret else c.canonical(warning_body())
    record = oa.transport_record(row, 1, capture(raw), FakeClock().utc())
    terminal, _ = oa.finish_data(
        root,
        row,
        record,
        raw,
        key=KEY,
        validator=adapter.validator(row, root),
        validation=adapter,
    )
    assert terminal["validation_version"] == v.VERSION
    assert (
        audit.reopen(
            root,
            audit.name_for(1, 1),
            validator=adapter.validator(row, root),
            context=oa.DataContext(adapter),
        )
        == terminal
    )
    side = r.read_object(root / "public_limitation.json")
    assert side["exception_applied"] is (not secret)
    if secret:
        assert (
            terminal["reason_code"] == "SECRET_ECHO_DETECTED"
            and side["raw_sha256"] is None
        )
        for path in root.iterdir():
            assert (
                KEY not in path.read_bytes()
                and c.sha(raw).hex().encode() not in path.read_bytes()
            )
    else:
        assert terminal["outcome"] in c.SUCCESS
        with pytest.raises(c.Stage12Error):
            audit.reopen(
                root,
                audit.name_for(1, 1),
                validator=cli.public_shapes,
                context=oa.DataContext(),
            )


def test_envelope_shared_counter_and_both_transport_deadlines():
    clock = FakeClock()
    e = r.Envelope(clock, 2, 3)
    writes = []

    class Hooks:
        def started(self, ns):
            pass

        def signal(self, *a):
            pass

        def completed(self, x):
            pass

        def emit(self, write, check):
            check()
            write()

    h = e.wrap(Hooks())
    e.charge()
    e.charge()
    assert h.attempt_deadline_ns(0, 60 * 10**9) == 3 * 10**9
    with pytest.raises(c.Stage12Error):
        e.charge()
    h.emit(lambda: writes.append(1), lambda: None)
    clock.advance(3 * 10**9)
    with pytest.raises(c.Stage12Error):
        h.emit(lambda: writes.append(2), lambda: None)
    assert writes == [1] and e.attempts == 2


def test_progression_requires_exact_actual_report_and_fails_closed(tmp_path):
    clock = FakeClock()
    e = r.Envelope(clock, 2, 5)
    root = tmp_path / "gate"
    io.reserve(root)
    with pytest.raises(c.Stage12Error, match="UNAVAILABLE"):
        r.progression(root, "capability_subset", {"test_only": True}, clock, e, 1)
    assert clock.now_ns() == 10**9 and e.attempts == 0
    expected = r.read_object(root / "capability_subset_AWAITING_REVIEW.json")
    report = b"SYNTHETIC TEST ONLY review"
    io.write(root / "capability_subset_review.md", report)
    io.write(
        root / "capability_subset_review.json",
        c.canonical({**expected, "review_report_sha256": c.sha(report).hex()}),
    )
    # A fresh gate gets its own root. Existing reservation cannot be reused.
    with pytest.raises(FileExistsError):
        r.progression(root, "capability_subset", {"test_only": True}, clock, e, 1)


def config_test_only():
    route = {
        "origin": "https://geocode.safe-frankfurt.de",
        "approved_ip": "159.69.61.56",
        "configuration_evidence_sha256": H,
        "target_limit": 4096,
        "header_limit": 16384,
    }
    items = []
    for label, rate in [("capability_subset", 1), ("rate20", 20), ("rate40", 40)]:
        p, plan, start, rows, inventory = inputs(2, rate)
        p["states"][0]["connections"] = 2
        p["transport_profile_sha256"] = o.digest(route)
        p["operator_allowance"]["valid_from"] = "2026-01-01T00:00:00.000000Z"
        p["operator_allowance"]["valid_until"] = "2027-01-01T00:00:00.000000Z"
        plan["window_start"] = p["operator_allowance"]["valid_from"]
        plan["window_end"] = p["operator_allowance"]["valid_until"]
        for n, row in enumerate(rows):
            row.update(berlin_work())
            row["work_id"] = n + 1
            row["repetition"] = n
            row["retry_spacing_key"] = row["fixture_id"]
        rebind(p, plan, start, rows)
        if rate > 1:
            plan["blocks"][0]["evaluation"] = (
                "CONFIRMATORY"  # never dispatched in these two-observation failure tests
            )
            plan["blocks"][0]["criteria"] = dict(
                min_valid_data=2,
                min_duration_ms=1,
                max_duration_ms=1000,
                min_attempt_rate={"num": 1, "den": 1},
                min_durable_data_rate={"num": 1, "den": 1},
                max_http_p95_ms=100,
                max_http_p99_ms=100,
                max_slot_p95_ms=100,
                max_slot_p99_ms=100,
                max_retry_fraction={"num": 0, "den": 1},
                max_pending_count=4,
                max_pending_bytes=2**20,
                max_reserved_bytes=o.MEMORY,
                max_writer_wait_ms=100,
                required_cells=[{"mode": "FULL_TEXT", "size": 1}],
                min_per_cell=2,
            )
        items.append(
            {
                "label": label,
                "profile": p,
                "plan": plan,
                "work": rows,
                "ascending_sizes": rate == 1,
            }
        )
    return dict(
        version=r.VERSION,
        scope=o.SCOPE,
        task_id=H,
        output_directory=str(r.OUTPUT_PARENT / ("or2_" + H)),
        window_start=plan["window_start"],
        window_end=plan["window_end"],
        maximum_attempts=400,
        active_seconds=1680,
        review_wait_seconds=1,
        transport=route,
        resources=p["resources"],
        sources={
            x: H
            for x in ("owner", "operator", "selection", "transport", "policy_freeze")
        },
        campaigns=items,
        public_validation_sha256=o.digest(v.descriptor()),
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "bool_budget",
        "rate60",
        "connections",
        "protected",
        "control",
        "identity",
        "first_rate",
        "missing_criteria",
        "invalid_cell_coverage",
    ],
)
def test_configuration_rejects_scope_and_budget_changes(mutation):
    x = config_test_only()
    if mutation == "bool_budget":
        x["active_seconds"] = True
    if mutation == "rate60":
        x["campaigns"][2]["profile"]["states"][0]["rate"]["num"] = 60
    if mutation == "connections":
        x["campaigns"][0]["profile"]["states"][0]["connections"] = 4
    if mutation == "protected":
        x["scope"] = "DEVELOPMENT"
    if mutation == "control":
        x["campaigns"][0]["work"][0]["kind"] = "SERVICE_CONTROL"
    if mutation == "identity":
        x["public_validation_sha256"] = "0" * 64
    if mutation == "first_rate":
        x["campaigns"][0]["profile"]["states"][0]["rate"]["num"] = 20
    if mutation == "missing_criteria":
        x["campaigns"][2]["plan"]["blocks"][0]["criteria"] = None
    if mutation == "invalid_cell_coverage":
        x["campaigns"][2]["plan"]["blocks"][0]["criteria"]["min_per_cell"] = 3
    with pytest.raises((c.Stage12Error, KeyError)):
        r.validate_config(x)


def test_authority_binds_actual_bytes_and_context(tmp_path):
    cfg = config_test_only()
    r.validate_config(cfg)
    bundle = tmp_path / "bundle"
    io.reserve(bundle)
    for role in cfg["sources"]:
        io.write(
            bundle / (role + ".record"),
            b"SYNTHETIC TEST ONLY - NOT AN AUTHORITY RECORD",
        )
    report = b"SYNTHETIC INDEPENDENT TEST DOUBLE"
    io.write(bundle / "integration_review.md", report)
    source = tmp_path / "source.py"
    source.write_bytes(b"# invented test source")
    review = dict(
        version="stage12_public_integration_review_binding_v1",
        scope=o.SCOPE,
        disposition="PASS",
        configuration_sha256=o.digest(cfg),
        report_sha256=c.sha(report).hex(),
        source_files=[
            {"path": "source.py", "sha256": c.sha(source.read_bytes()).hex()}
        ],
    )
    a = r.Authority(cfg, bundle, review, H, tmp_path, "a" * 40, FakeClock())
    with pytest.raises(c.Stage12Error):
        a.require("resources", H, {})
    item = cfg["campaigns"][0]
    start = dict(
        client_git_sha="a" * 40,
        profile_sha256=o.digest(item["profile"]),
        plan_sha256=o.digest(item["plan"]),
    )
    a.bind(item, item["plan"], start)
    a.require("resources", H, cfg["resources"])
    with pytest.raises(c.Stage12Error):
        a.require("resources", H, {})
    with pytest.raises(c.Stage12Error):
        a.require("protected_dispatch", H, {})
    (bundle / "owner.record").write_bytes(b"changed")
    with pytest.raises(c.Stage12Error):
        a.recheck()


@pytest.mark.parametrize("broken_reopen", [False, True])
def test_actual_coordinator_capture_report_reopen_and_failure_honesty(
    monkeypatch, tmp_path, broken_reopen
):
    cfg = config_test_only()
    cfg["resources"]["allocated_disk_bytes"] = 2**40

    # Use real monotonic and UTC, sole writer and sampler; synthetic transport only.
    monkeypatch.setattr(r, "require_goethe_nhr_slurm", lambda _: None)
    monkeypatch.setattr(r.assets, "verify", lambda _: None)
    monkeypatch.setattr(
        r.subprocess,
        "check_output",
        lambda args, **kw: "a" * 40 if "rev-parse" in args else b"",
    )
    monkeypatch.setattr(r, "runtime_inventory", lambda *a: {"scope": "SYNTHETIC_ONLY"})
    monkeypatch.setattr(r.resource, "setrlimit", lambda *a: None)
    monkeypatch.setattr(
        r.os,
        "statvfs",
        lambda _: type("Stat", (), {"f_bavail": 2**50, "f_frsize": 1})(),
    )
    monkeypatch.setattr(r, "OUTPUT_PARENT", tmp_path)
    cfg["output_directory"] = str(tmp_path / ("or2_" + H))
    monkeypatch.setenv("SLURM_JOB_ID", "SYNTHETIC_ONLY")
    monkeypatch.setenv("SLURM_MEM_PER_NODE", "6144")
    monkeypatch.setenv(
        "SAFE_PELIAS_API_KEY_FILE",
        str(Path.home() / ".config/safe-geocoding/pelias_api_key"),
    )
    monkeypatch.delenv("SAFE_PELIAS_API_KEY", raising=False)
    calls = []

    def send(target, profile, key, ops, hooks):
        hooks.started(r.time.monotonic_ns())
        hooks.emit(lambda: calls.append(target), lambda: None)
        result = capture(c.canonical(warning_body()))
        hooks.signal(200, result.outcome, result.reason, None)
        hooks.completed(result)
        return result

    monkeypatch.setattr(t, "send", send)

    def stop(*a):
        raise c.Stage12Error("S12_PUBLIC_PROGRESSION_REVIEW_UNAVAILABLE")

    monkeypatch.setattr(r, "progression", stop)
    if broken_reopen:

        def fail(*a, **kw):
            raise c.Stage12Error("S12_TEST_REOPEN_FAILURE")

        monkeypatch.setattr(r, "reopen_completed", fail)
    bundle = tmp_path / "bundle"
    io.reserve(bundle)
    for role in cfg["sources"]:
        io.write(
            bundle / (role + ".record"),
            b"SYNTHETIC TEST ONLY - NOT AN AUTHORITY RECORD",
        )
    review_text = b"SYNTHETIC TEST ONLY REVIEW DOUBLE"
    io.write(bundle / "integration_review.md", review_text)
    review = dict(
        version="stage12_public_integration_review_binding_v1",
        scope=o.SCOPE,
        disposition="PASS",
        configuration_sha256=o.digest(cfg),
        report_sha256=c.sha(review_text).hex(),
        source_files=[
            {"path": "bundle/integration_review.md", "sha256": c.sha(review_text).hex()}
        ],
    )
    result = r.execute(
        cfg,
        bundle=bundle,
        review=review,
        review_hash=H,
        repository=tmp_path,
        git_sha="a" * 40,
        key_provider=lambda: t.Secret.checked(KEY),
    )
    assert len(calls) == 2 and result["attempts_dispatched_or_uncertain"] == 2
    assert result["qualified_public_rates"] == []
    assert result["completed_phases"] == (
        [] if broken_reopen else ["capability_subset"]
    )
    assert result["attempted_phases"] == ["capability_subset"]
    assert not result["scientific_identity_verified"]
    assert not (Path(cfg["output_directory"]) / "rate20").exists()


def test_low_check_repeat_disagreement_never_authorizes_progression():
    block = dict(
        status="EXPLORATORY_ONLY",
        reasons=["EXPLORATORY_NO_QUALIFICATION", "REPEAT_DISAGREEMENT"],
    )
    assert not r.qualifies(block, smoke=True)


def test_runtime_guard_precedes_input_and_key_access(monkeypatch, tmp_path):
    called = []

    def denied(_):
        raise c.Stage12Error("S12_TEST_SITE_REJECTED")

    monkeypatch.setattr(r, "require_goethe_nhr_slurm", denied)
    with pytest.raises(c.Stage12Error, match="SITE_REJECTED"):
        r.execute(
            {},
            bundle=tmp_path,
            review={},
            review_hash=H,
            repository=tmp_path,
            git_sha="a" * 40,
            key_provider=lambda: called.append("KEY"),
        )
    assert not called and list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "mismatch",
    [
        None,
        "prior_block_report_sha256",
        "next_rate",
        "review_report_sha256",
        "reviewer",
    ],
)
def test_progression_validates_actual_report_bound_gate(tmp_path, mismatch):
    clock = FakeClock()
    root = tmp_path / "gate"
    io.reserve(root)
    block = {"test_only": True}
    report = b"TEST ONLY independent review double"
    expected = dict(
        version="stage12_public_progression_review_v1",
        scope=o.SCOPE,
        task_root=str(root),
        prior_label="capability_subset",
        prior_block_report_sha256=o.digest(block),
        next_rate=20,
        reviewer="/root/public_followup_review",
        disposition="PASS",
        review_report_sha256=c.sha(report).hex(),
    )
    if mismatch:
        expected[mismatch] = 40 if mismatch == "next_rate" else "0" * 64
    io.write(root / "capability_subset_review.md", report)
    io.write(root / "capability_subset_review.json", c.canonical(expected))
    envelope = r.Envelope(clock, 2, 3)
    if mismatch:
        with pytest.raises(c.Stage12Error, match="INVALID"):
            r.progression(root, "capability_subset", block, clock, envelope, 1)
    else:
        assert (
            r.progression(root, "capability_subset", block, clock, envelope, 1)
            == expected
        )


@pytest.mark.parametrize("status", [200, 429, 403])
def test_envelope_integrated_real_transport_fake_socket(monkeypatch, status):
    from email.message import Message
    from safe_geocoding_pipeline.preprocessing.stages import s12_operations as v1

    clock = FakeClock()
    calls = []
    raw = body([])

    class Socket:
        def settimeout(self, n):
            pass

        def shutdown(self, *a):
            pass

    class Reply:
        length = 0

        def __init__(self):
            self.status = status
            self.done = False
            self.headers = Message()
            self.headers["Content-Type"] = "application/json"
            self.headers["Content-Length"] = str(len(raw))
            self.headers["Retry-After"] = "31"

        def getheader(self, key):
            return self.headers.get(key)

        def read1(self, n):
            if self.done:
                return b""
            self.done = True
            return raw

    class Connection:
        sock = Socket()

        def __init__(self, *a):
            pass

        def connect(self):
            calls.append("connect")

        def putrequest(self, *a, **kw):
            pass

        def putheader(self, *a):
            pass

        def endheaders(self):
            calls.append("emit")

        def getresponse(self):
            return Reply()

        def close(self):
            calls.append("close")

    class Timer:
        def __init__(self, n, cb):
            assert n == 3

        def start(self):
            pass

        def cancel(self):
            pass

    class Hooks:
        def started(self, n):
            calls.append("start")

        def emit(self, write, check):
            check()
            write()

        def signal(self, *args):
            calls.append(("signal", args[0]))

        def completed(self, result):
            calls.append("complete")

    monkeypatch.setattr(t, "require_goethe_nhr_slurm", lambda _: None)
    monkeypatch.setattr(t, "_Connection", Connection)
    monkeypatch.setattr(t.threading, "Timer", Timer)
    monkeypatch.setattr(t.time, "monotonic_ns", clock.now_ns)
    e = r.Envelope(clock, 1, 3)
    e.charge()
    result = t.send(
        b"/v1/search?size=1&text=Berlin",
        t.TransportProfile(
            "https://synthetic.invalid", "127.0.0.1", bytes.fromhex(H), 4096, 16384
        ),
        t.Secret.checked(KEY),
        v1.Operations(),
        hooks=e.wrap(Hooks()),
    )
    assert result.status == status and e.attempts == 1
    assert calls == [
        "start",
        "connect",
        "emit",
        ("signal", status),
        "close",
        "complete",
    ]
    assert result.payload == (raw if status == 200 else None)


def failed_public_pair(tmp_path, monkeypatch, fault=None):
    """Invented empty features; exact warning text, no retained service replay."""
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as j
    from test_stage12_public_scheduler import repair_common

    p, plan, start, rows, runtime = inputs(6, 20)
    p["states"][0].update(connections=1, admitted_operations=1)
    fixture = berlin_work()["fixture_id"]
    for row, size in zip(rows, (1, 1, 3, 3, 5, 5)):
        row.update(
            fixture_id=fixture,
            retry_spacing_key=fixture,
            result_limit=size,
            repetition=(row["work_id"] - 1) % 2,
        )
    rebind(p, plan, start, rows)
    clock = FakeClock()
    calls = []
    root = tmp_path / "failed_public"

    def send(row, target, hooks):
        calls.append(row["work_id"])
        hooks.started(clock.now_ns())
        hooks.emit(lambda: None, lambda: None)
        obj = warning_body()
        obj["geocoding"]["query"]["size"] = row["result_limit"]
        value = capture(c.canonical(obj))
        hooks.completed(value)
        return value

    original_stream = j.Journal.stream_array

    def stream(self, name, source):
        if name == "repeat_comparison.json":
            if fault == "invalid_pair":
                # Change a successful synthetic receipt's raw evidence just
                # before comparison. Full reopen must reject, never compare [].
                path = root / "attempts/call_0001_attempt_1/call_0001_attempt_1.zst"
                path.write_bytes(b"synthetic corruption")
            if fault == "cleanup":

                def failed_write(*a, **kw):
                    raise OSError("SECONDARY_CLEANUP")

                monkeypatch.setattr(io, "write", failed_write)
                raise ValueError("PRIMARY_COMPARISON")
        return original_stream(self, name, source)

    monkeypatch.setattr(j.Journal, "stream_array", stream)
    report = cli.run_operations_block(
        p,
        plan,
        start,
        clock=clock,
        dispatch=send,
        output=root,
        epoch=H,
        public_validation=v.Validation(),
        ascending_sizes=True,
        **repair_common(rows, runtime),
    )
    return root, report, calls, start


def test_1804093_rejected_pair_is_false_and_failure_closes_truthfully(
    monkeypatch, tmp_path
):
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as j
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_recovery as recovery,
    )

    root, report, calls, start = failed_public_pair(tmp_path, monkeypatch)
    assert calls == [1, 2, 3]
    assert report["disposition"] == "STOPPED" and not report["report_complete"]
    assert report["campaign_counts"]["durable_valid_data"]["value"] == 2
    assert report["campaign_counts"]["durable_terminal_failure"]["value"] == 1
    # Scientific processed-work counts accepted observations, not HTTP 200s:
    # one rejected plus three unbegun observations remain unprocessed.
    assert report["campaign_counts"]["unprocessed_data"]["value"] == 4
    assert list(j.read_array(root / "repeat_comparison.json")) == [
        {"first_work_id": 1, "next_work_id": 2, "equal": True},
        {"first_work_id": 3, "next_work_id": 4, "equal": False},
        {"first_work_id": 5, "next_work_id": 6, "equal": False},
    ]
    assert (root / "_SEGMENT_SEALED").exists()
    state = recovery.replay(j.read_events(root, o.digest(start)))
    assert state["closed"] and state["breaker_reason"] == "TERMINAL_FAILURE"
    block = io.metadata(io.read(root / "block_report.json"))
    assert not r.qualifies(block, smoke=True)
    for n in calls:
        path = root / "attempts" / audit.name_for(n, 1)
        row = io.metadata(io.read(path / "work.json"))
        terminal = audit.reopen(
            path,
            path.name,
            validator=v.Validation().validator(row, path),
            context=oa.DataContext(v.Validation()),
        )
        assert terminal["outcome"] == (
            "SUCCESS_ZERO_CANDIDATES" if n < 3 else "CONTRACT_FAILURE"
        )
        assert (
            io.metadata(io.read(path / (path.name + "_finish.json")))["status"] == 200
        )


@pytest.mark.parametrize("fault", ["invalid_pair", "cleanup"])
def test_1804093_comparison_or_cleanup_failure_never_erases_terminal(
    monkeypatch, tmp_path, fault
):
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as j

    root, report, calls, start = failed_public_pair(tmp_path, monkeypatch, fault)
    assert calls == [1, 2, 3]
    assert report["disposition"] == "RECOVERY_BLOCKED"
    assert not report["report_complete"]
    assert not (root / "_SEGMENT_SEALED").exists()
    events = list(j.read_events(root, o.digest(start)))
    stop = next(e for e in events if e["kind"] == "STOP")
    assert stop["body"]["why"] == "TERMINAL"
    assert stop["body"]["primary_reason"] == "TERMINAL_FAILURE"
    assert sum(e["kind"] == "ATTEMPT_FINALIZED" for e in events) == 3
    assert not any(e["kind"] == "SEGMENT_CLOSE" for e in events)


@pytest.mark.parametrize(
    "mutation",
    [
        None,
        "rate2",
        "ascending",
        "exploratory",
        "rate20",
        "legacy_labels",
        "missing_criteria",
    ],
)
def test_scale120_lower_wrapper_is_explicit_same_rate_and_preserves_legacy(mutation):
    cfg = config_test_only()
    r.validate_config(cfg)
    cfg["version"] = r.LOWER_VERSION
    cfg["campaigns"] = cfg["campaigns"][:2]
    item = cfg["campaigns"][1]
    item["label"] = "confirmatory1"
    item["profile"]["states"][0]["rate"] = {"num": 1, "den": 1}
    item["plan"]["operations_profile_sha256"] = o.digest(item["profile"])
    r.validate_config(cfg)
    if mutation == "rate2":
        item["profile"]["states"][0]["rate"]["num"] = 2
    elif mutation == "ascending":
        item["ascending_sizes"] = True
    elif mutation == "exploratory":
        item["plan"]["blocks"][0]["evaluation"] = "EXPLORATORY"
    elif mutation == "rate20":
        item["label"] = "rate20"
    elif mutation == "legacy_labels":
        cfg["version"] = r.VERSION
    elif mutation == "missing_criteria":
        item["plan"]["blocks"][0]["criteria"] = None
    if mutation:
        with pytest.raises(c.Stage12Error):
            r.validate_config(cfg)


@pytest.mark.parametrize(
    "completed,rates,status",
    [
        (["capability_subset", "confirmatory1"], [1], 0),
        ([], [], 1),
        (["capability_subset"], [], 1),
        (["capability_subset", "confirmatory1"], [], 1),
        (["capability_subset", "confirmatory1"], [2], 1),
        (["capability_subset", "confirmatory1"], [1, 20], 1),
        (["capability_subset", "rate20", "rate40"], [20, 40], 1),
    ],
)
def test_scale120_lower_cli_exit_requires_both_reopened_phases(
    completed, rates, status
):
    from safe_geocoding_pipeline.preprocessing import stage12_operations_cli as entry

    assert (
        entry.result_exit_status(
            {"version": r.LOWER_VERSION},
            {"completed_phases": completed, "qualified_public_rates": rates},
        )
        == status
    )


def test_scale120_legacy_cli_exit_is_preserved():
    from safe_geocoding_pipeline.preprocessing import stage12_operations_cli as entry

    assert (
        entry.result_exit_status(
            {"version": r.VERSION},
            {
                "completed_phases": ["capability_subset", "rate20", "rate40"],
                "qualified_public_rates": [20, 40],
            },
        )
        == 0
    )
    assert (
        entry.result_exit_status(
            {"version": r.VERSION},
            {
                "completed_phases": ["capability_subset", "confirmatory1"],
                "qualified_public_rates": [1],
            },
        )
        == 1
    )
