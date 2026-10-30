import pytest
from stage12_b2_synthetic import World, offline
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c


def test_synthetic_coordinator_capture_report_reopen(tmp_path):
    world = World(tmp_path)
    report, _ = world.run()
    assert report["disposition"] == "COMPLETED"
    assert report["counts"]["durable_valid_data"]["value"] == 2
    assert report["continuous_service_state"] == "NOT_VERIFIED"
    assert report["resource_sampling_complete"]
    assert (tmp_path / "segment/_SEGMENT_SEALED").exists()


@pytest.mark.parametrize(
    "failure",
    [
        "malformed",
        "secret",
        "unknown_delivery",
        "missing_closure",
        "notice",
        "resource_gap",
    ],
)
def test_failures_preserve_evidence_without_clean_seal(tmp_path, failure):
    from stage12_b2_synthetic import KEY, H
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_storage as io,
        s12_b2_audit as audit,
        s12_b2_contract as b,
    )

    world = World(tmp_path)
    options = {}
    if failure in ("malformed", "secret"):
        payload = (
            b'{"invalid": true}'
            if failure == "malformed"
            else b'{"secret":"' + KEY + b'"}'
        )
        options["dispatch"] = lambda work, target, hooks: world.dispatch(
            work, target, hooks, raw=payload
        )
    elif failure == "unknown_delivery":

        def uncertain(work, target, hooks):
            hooks.started(world.clock.now_ns())
            hooks.emit(lambda: None, lambda: None)
            raise RuntimeError("invented uncertain delivery; no payload")

        options["dispatch"] = uncertain
    elif failure == "missing_closure":
        options["close_segment"] = lambda info: iter([world.records.raw(H)])
    elif failure == "notice":
        options["notice"] = lambda: H
    else:

        def stalled(work, target, hooks):
            world.clock.advance(101_000_000)
            return world.dispatch(work, target, hooks)

        options["dispatch"] = stalled
    with pytest.raises(c.Stage12Error):
        world.run(**options)
    assert not (tmp_path / "segment/_SEGMENT_SEALED").exists()
    if failure in ("malformed", "secret"):
        units = list((tmp_path / "segment/attempts").iterdir())
        assert units
        receipt, projection, raw = audit.reopen(units[0], **world.rules.kwargs())
        assert receipt["outcome"] == "CONTRACT_FAILURE" and projection is None
        assert (raw is None) == (failure == "secret")
        if failure == "secret":
            assert not (units[0] / "raw.zst").exists()
    if failure in ("unknown_delivery", "resource_gap"):
        measured = b.parse(io.read(tmp_path / "segment/measurement_report.json"))
        assert not measured["report_complete"]
        if failure == "unknown_delivery":
            assert measured["counts"]["durable_valid_data"]["value"] is None
            assert measured["rates"]["durable_data_per_s"] is None
        else:
            assert not measured["resource_sampling_complete"]


def test_clean_same_window_continuation_preserves_totality(tmp_path):
    from copy import deepcopy
    from stage12_b2_synthetic import H, KEY
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_b2_contract as b,
        s12_b2_pipeline as pipe,
        s12_b2_operations as o,
        s12_storage as io,
        s12_response as response,
    )

    world = World(tmp_path)
    inputs = world.inputs()
    profile, plan, start, science, admission, rows = inputs
    report, _ = world.run("first", inputs=inputs, pause_requested=lambda: True)
    assert (
        report["disposition"] == "PAUSED_CLEAN"
        and report["counts"]["durable_valid_data"]["value"] == 0
    )
    snap = b.parse(io.read(tmp_path / "first/snapshot.json"), o.SNAPSHOT)
    second = deepcopy(admission)
    second.update(
        segment_nonce=world.nonce(),
        epoch_id=world.nonce(),
        segment_id=2,
        predecessor_closure_sha256=snap["segment_closure_sha256"],
    )
    release = world.put(
        {
            "schema_version": "stage12_writer_release_authority_b2_v1",
            "campaign_id": start["campaign_id"],
            "segment_nonce": second["segment_nonce"],
            "issuer_delegation_sha256": H,
            "valid_from": "2025-01-01T00:00:00.000000Z",
            "valid_until": "2027-01-01T00:00:00.000000Z",
            "purpose": "WRITER_TERMINATION_AND_HANDOFF",
        }
    )
    second["bootstrap_acquisition_sha256"] = pipe.prepare_bootstrap(
        tmp_path / "bootstrap_next",
        records=world.records,
        raw_factory=lambda: (lambda: world.records.raw(H),),
        clock=world.clock,
        profile=profile,
        plan=plan,
        start=start,
        segment_nonce=second["segment_nonce"],
        epoch_id=second["epoch_id"],
        authority=world.gate,
        authority_hash=H,
        writer_release_evidence=release,
        secret_guard=lambda raw: response.secret_guard(raw, KEY),
        previous_hash=snap["bootstrap_acquisition_sha256"],
    )
    world.releases[second["segment_nonce"]] = release
    world.clock.advance(500_000_000)
    completed, _ = world.run(
        "second",
        inputs=(profile, plan, start, science, second, rows),
        predecessor=tmp_path / "first",
    )
    assert (
        completed["disposition"] == "COMPLETED"
        and completed["counts"]["durable_valid_data"]["value"] == 2
    )
    second_snapshot = b.parse(io.read(tmp_path / "second/snapshot.json"), o.SNAPSHOT)
    assert second_snapshot["controller"]["administrative_operations"] == 4
    assert completed["duration_ns"] is None  # no subtraction between epochs
