"""Prospective warning-family and cumulative-finalization regressions; no network."""

from pathlib import Path
import pytest
from safe_geocoding_pipeline.preprocessing.stages import s12_public_response as v
from safe_geocoding_pipeline.preprocessing.stages import s12_public_runtime as r
from safe_geocoding_pipeline.preprocessing.stages import s12_public_recovery as recovery
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_public_reporting as reporting,
)
from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as journal
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_public_operational_audit as oa,
)
from safe_geocoding_pipeline.preprocessing.stages import s12_public_audit as audit
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from test_stage12_public_runtime import (
    berlin_work,
    warning_body,
    failed_public_pair,
    config_test_only,
)
from test_stage12_public_operations_v2 import H, KEY, FakeClock, inputs, rebind, offline  # noqa: F401
from test_stage12_public_operational_audit import capture


@pytest.mark.parametrize("size", v.FAMILY_SIZES)
def test_family_exact_prospective_capture_and_reopen(tmp_path, size):
    p, plan, start, rows, runtime = inputs(1)
    row = berlin_work()
    row.update(result_limit=size, retry_spacing_key=row["fixture_id"])
    rows[:] = [row]
    rebind(p, plan, start, rows)
    obj = warning_body()
    obj["geocoding"]["query"]["size"] = size
    raw = c.canonical(obj)
    adapter = v.Validation(v.FAMILY_VERSION)
    assert v.shapes(raw, row, version=v.FAMILY_VERSION) == ()
    if size != 1:
        with pytest.raises(c.Stage12Error):
            v.shapes(raw, row)
    root = tmp_path / "attempt"
    oa.begin_data(root, p, plan, start, row, 1, runtime, validation=adapter)
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
    assert terminal["outcome"] == "SUCCESS_ZERO_CANDIDATES"
    assert (
        audit.reopen(
            root,
            audit.name_for(1, 1),
            validator=adapter.validator(row, root),
            context=oa.DataContext(adapter),
        )
        == terminal
    )
    side = io.metadata(io.read(root / "public_limitation.json"))
    assert side["raw_sha256"] == c.sha(raw).hex() and side["exception_applied"]
    assert side["continuous_service_state"] == "NOT_VERIFIED"
    assert not side["scientific_publication_authorized"]
    assert not side["scientific_identity_verified"]
    with pytest.raises(c.Stage12Error):
        audit.reopen(
            root,
            audit.name_for(1, 1),
            validator=v.Validation().validator(row, root),
            context=oa.DataContext(v.Validation()),
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "size2",
        "size41",
        "structured",
        "other_fixture",
        "echo1",
        "float",
        "exponent",
        "bool",
        "string",
        "negative",
        "extra",
        "duplicate",
        "top",
        "error",
        "text",
        "country",
        "layers",
        "address",
        "lang",
        "shape",
        "returned_layer",
        "empty_layers",
    ],
)
def test_family_near_misses_fail(mutation):
    row = berlin_work()
    row["result_limit"] = 3
    obj = warning_body()
    q = obj["geocoding"]["query"]
    q["size"] = 3
    if mutation.startswith("size"):
        row["result_limit"] = q["size"] = int(mutation[4:])
    if mutation in ("structured", "other_fixture"):
        row["fixture_id"] = next(
            f["fixture_id"]
            for f in v.probe.fixtures()
            if f["core"]["search_mode"]
            == ("STRUCTURED" if mutation == "structured" else "FULL_TEXT")
            and f["fixture_id"] != row["fixture_id"]
        )
    if mutation == "echo1":
        q["size"] = 1
    if mutation == "float":
        q["size"] = 3
    if mutation == "bool":
        q["size"] = True
    if mutation == "string":
        q["size"] = "3"
    if mutation == "negative":
        q["size"] = -3
    if mutation == "extra":
        obj["geocoding"]["warnings"].append("other")
    if mutation == "duplicate":
        obj["geocoding"]["warnings"] *= 2
    if mutation == "top":
        obj["warnings"] = obj["geocoding"].pop("warnings")
    if mutation == "error":
        obj["geocoding"]["errors"] = ["failure"]
    if mutation == "text":
        q["text"] = "berlin"
    if mutation == "country":
        q["boundary.country"] = ["DE"]
    if mutation == "layers":
        q["layers"] *= 2
    if mutation == "address":
        q["layers"] = ["address"]
    if mutation == "empty_layers":
        q["layers"] = []
    if mutation == "lang":
        q["lang"] = {}
    if mutation == "shape":
        obj["features"] = [{}]
    if mutation == "returned_layer":
        obj["features"] = [
            {
                "type": "Feature",
                "properties": {"source": "test", "layer": "region"},
                "geometry": {"type": "Point", "coordinates": [1, 2]},
            }
        ]
    raw = c.canonical(obj)
    if mutation == "float":
        raw = raw.replace(b'"size":3', b'"size":3.0')
    if mutation == "exponent":
        raw = raw.replace(b'"size":3', b'"size":3e0')
    with pytest.raises(c.Stage12Error):
        v.shapes(raw, row, version=v.FAMILY_VERSION)


def test_versioned_descriptor_binding_and_no_feature_pin():
    cfg = config_test_only()
    cfg["public_validation_sha256"] = c.sha(
        c.canonical(v.descriptor(v.FAMILY_VERSION))
    ).hex()
    r.validate_config(cfg)
    assert r.validation_for(cfg["public_validation_sha256"]).VERSION == v.FAMILY_VERSION
    assert v.descriptor() == io.metadata(
        Path(
            "docs/scientific_assets/stage12_public_observation_validation_v1.json"
        ).read_bytes()
    )
    assert v.descriptor(v.FAMILY_VERSION) == io.metadata(
        Path(
            "docs/scientific_assets/stage12_public_observation_validation_v2.json"
        ).read_bytes()
    )
    row = berlin_work()
    row["result_limit"] = 5
    obj = warning_body()
    obj["geocoding"]["query"]["size"] = 5
    obj["features"] = [
        {
            "type": "Feature",
            "properties": {"source": "invented", "layer": "locality"},
            "geometry": {"type": "Point", "coordinates": [17, 23]},
        }
    ]
    assert len(v.shapes(c.canonical(obj), row, version=v.FAMILY_VERSION)) == 1


def test_deadline_exception_not_receipt_or_contract_error():
    clock = FakeClock()
    d = recovery.Deadline(clock, 100)
    d.check()
    clock.advance(100)
    with pytest.raises(recovery.FinalizationExpired):
        d.check()
    assert not issubclass(recovery.FinalizationExpired, (OSError, c.Stage12Error))
    assert d.remaining_seconds() == 0


@pytest.mark.parametrize(
    "phase", ["comparison", "report", "totality", "ledger", "inventory", "snapshot"]
)
def test_cumulative_finalization_expiry_never_completes(monkeypatch, tmp_path, phase):
    clock = FakeClock()
    monkeypatch.setattr("test_stage12_public_runtime.FakeClock", lambda: clock)

    def expire():
        clock.advance(700 * 10**9)

    if phase in ("comparison", "ledger", "inventory"):
        old = journal.Journal.stream_array
        name = {
            "comparison": "repeat_comparison.json",
            "ledger": "work_ledger.json",
            "inventory": "event_inventory.json",
        }[phase]

        def stream(self, n, rows):
            if n == name:
                expire()
            return old(self, n, rows)

        monkeypatch.setattr(journal.Journal, "stream_array", stream)
    elif phase == "report":
        old = reporting.block_report

        def report(*a, **kw):
            expire()
            return old(*a, **kw)

        monkeypatch.setattr(reporting, "block_report", report)
    elif phase == "totality":
        old = recovery.required_work_complete

        def total(*a, **kw):
            expire()
            return old(*a, **kw)

        monkeypatch.setattr(recovery, "required_work_complete", total)
    else:
        old = recovery.write_snapshot

        def snapshot(*a, **kw):
            expire()
            return old(*a, **kw)

        monkeypatch.setattr(recovery, "write_snapshot", snapshot)

    # Fallback must not continue filesystem traversal after selected budget.
    def forbidden(*a, **kw):
        raise AssertionError("unbounded reconciliation after deadline")

    monkeypatch.setattr(recovery, "unclean_reconciliation", forbidden)
    root, result, calls, start = failed_public_pair(tmp_path, monkeypatch)
    assert calls == [1, 2, 3]
    assert result["disposition"] == "RECOVERY_BLOCKED" and not result["report_complete"]
    assert result["campaign_counts"]["begins_charged"]["value"] is None
    assert not (root / "_WRITER_RELEASED.json").exists()
    assert not (root / "_SEGMENT_SEALED").exists()
    assert (root / "attempts/call_0001_attempt_1/call_0001_attempt_1_SEALED").exists()


@pytest.mark.parametrize("secret", [False, True])
def test_successor_capture_rejects_secret_and_binds_exact_bytes(tmp_path, secret):
    p, plan, start, rows, runtime = inputs(1)
    row = berlin_work()
    row.update(result_limit=40, retry_spacing_key=row["fixture_id"])
    rows[:] = [row]
    rebind(p, plan, start, rows)
    obj = warning_body()
    obj["geocoding"]["query"]["size"] = 40
    raw = b'{"secret":"' + KEY + b'"}' if secret else c.canonical(obj)
    adapter = v.Validation(v.FAMILY_VERSION)
    root = tmp_path / "attempt"
    oa.begin_data(root, p, plan, start, row, 1, runtime, validation=adapter)
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
    assert (
        audit.reopen(
            root,
            audit.name_for(1, 1),
            validator=adapter.validator(row, root),
            context=oa.DataContext(adapter),
        )
        == terminal
    )
    if secret:
        assert terminal["reason_code"] == "SECRET_ECHO_DETECTED"
        for path in root.iterdir():
            assert KEY not in path.read_bytes()
    else:
        (root / "public_limitation.json").write_bytes(b"{}\n")
        with pytest.raises(c.Stage12Error):
            audit.reopen(
                root,
                audit.name_for(1, 1),
                validator=adapter.validator(row, root),
                context=oa.DataContext(adapter),
            )


def test_successor_full_six_size_pairs_complete_without_feature_pin(
    monkeypatch, tmp_path
):
    from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
    from test_stage12_public_scheduler import repair_common

    p, plan, start, rows, runtime = inputs(12, 20)
    p["states"][0].update(connections=1, admitted_operations=1)
    fixture = berlin_work()["fixture_id"]
    for row, size in zip(rows, [s for s in v.FAMILY_SIZES for _ in range(2)]):
        row.update(
            fixture_id=fixture,
            retry_spacing_key=fixture,
            result_limit=size,
            repetition=(row["work_id"] - 1) % 2,
        )
    rebind(p, plan, start, rows)
    clock = FakeClock()
    calls = []

    def send(row, target, hooks):
        calls.append(row["work_id"])
        hooks.started(clock.now_ns())
        hooks.emit(lambda: None, lambda: None)
        obj = warning_body()
        obj["geocoding"]["query"]["size"] = row["result_limit"]
        result = capture(c.canonical(obj))
        hooks.completed(result)
        return result

    root = tmp_path / "six_size"
    result = cli.run_operations_block(
        p,
        plan,
        start,
        clock=clock,
        dispatch=send,
        output=root,
        epoch=H,
        public_validation=v.Validation(v.FAMILY_VERSION),
        ascending_sizes=True,
        **repair_common(rows, runtime),
    )
    assert calls == list(range(1, 13))
    assert result["disposition"] == "COMPLETED"
    assert result["campaign_counts"]["durable_valid_data"]["value"] == 12
    assert all(x["equal"] for x in journal.read_array(root / "repeat_comparison.json"))
    assert (root / "_WRITER_RELEASED.json").exists() and (
        root / "_SEGMENT_SEALED"
    ).exists()
