"""Corrected-behavior regressions derived from preserved independent triggers; no actual permission or service evidence."""

from copy import deepcopy
from pathlib import Path
import pytest
from stage12_b2_synthetic import World, H, KEY
from test_stage12_b2_evidence import gate_fixture
from test_stage12_b2_publication import publish_world
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_b2_contract as b,
    s12_b2_planning as planning,
    s12_b2_evidence as evidence,
    s12_b2_pipeline as pipe,
    s12_b2_operations as o,
    s12_storage as io,
    s12_response as response,
    s12_retrieval_contract as c,
)


def actual_gate_world(tmp_path):
    world = World(tmp_path)
    gate, pre, nonce, state = gate_fixture(world)
    world.gate = gate
    world.window_hash = gate.window_hash
    window = gate.records.get(gate.window_hash, "window_plan")
    world.selection_hash = planning.bind_window(
        world.records,
        window["calibration_plan_sha256"],
        gate.window_hash,
        owner=lambda: None,
        secret_guard=lambda raw: None,
    )
    gate.selection_hash = world.selection_hash
    return world


def test_R02_descriptor_mismatch_rejects_before_dispatch(tmp_path):
    world = actual_gate_world(tmp_path)
    profile, plan, start, science, admission, rows = world.inputs()
    actual = science["materialization_contract_sha256"]
    wrong = b.sha(b"NOT THE IMPLEMENTED MATERIALIZATION CONTRACT").hex()
    assert wrong != actual
    science["materialization_contract_sha256"] = wrong
    start["materialization_contract_sha256"] = wrong
    start["scientific_campaign_start_sha256"] = b.digest(science)
    admission["campaign_start_sha256"] = b.digest(science)
    admission["operations_campaign_sha256"] = b.digest(start)
    inputs = (profile, plan, start, science, admission, rows)
    with pytest.raises(c.Stage12Error, match="B2_EXECUTABLE_CONTRACT_MISMATCH"):
        world.run(inputs=inputs)
    assert not (tmp_path / "segment/attempts").exists()


def test_R01_changed_index_between_clean_segments_blocks(tmp_path):
    world = actual_gate_world(tmp_path)
    inputs = world.inputs()
    profile, plan, start, science, admission, rows = inputs
    pause = [False]

    def dispatch(work, target, hooks):
        pause[0] = True
        return world.dispatch(work, target, hooks)

    report, _ = world.run(
        "first", inputs=inputs, dispatch=dispatch, pause_requested=lambda: pause[0]
    )
    assert report["disposition"] == "PAUSED_CLEAN"
    assert report["counts"]["durable_valid_data"]["value"] == 1
    snap = b.parse(io.read(tmp_path / "first/snapshot.json"), o.SNAPSHOT)
    first = world.records.get(snap["segment_closure_sha256"], "segment_closure")
    old_post = world.records.get(first["postflight_sha256"], "window_observation")
    old_inventory = world.records.get(
        old_post["inventory_sha256"], "evidence_inventory"
    )
    previous_uuid = next(
        x["value"]["text"]
        for x in old_inventory["facts"]
        if x["subject"] == "index_uuid"
    )
    world.clock.advance(1_000_000_000)
    now = world.clock.utc()
    nonce = world.nonce()
    epoch = world.nonce()
    new_inventory = deepcopy(old_inventory)
    for fact in new_inventory["facts"]:
        fact["as_of_start"] = fact["as_of_end"] = now
        if fact["subject"] == "index_uuid":
            fact["value"]["text"] = "SYNTHETIC DISTINCT INDEX GENERATION"
    assert previous_uuid != "SYNTHETIC DISTINCT INDEX GENERATION"
    pre = world.put(
        {
            **old_post,
            "phase": "PREFLIGHT",
            "segment_nonce": nonce,
            "inventory_sha256": world.put(new_inventory),
            "observed_from": now,
            "observed_until": now,
            "acquired_utc": now,
        }
    )
    release = world.put(
        {
            "schema_version": "stage12_writer_release_authority_b2_v1",
            "campaign_id": start["campaign_id"],
            "segment_nonce": nonce,
            "issuer_delegation_sha256": H,
            "valid_from": "2025-01-01T00:00:00.000000Z",
            "valid_until": "2027-01-01T00:00:00.000000Z",
            "purpose": "WRITER_TERMINATION_AND_HANDOFF",
        }
    )
    bootstrap = pipe.prepare_bootstrap(
        tmp_path / "bootstrap_next",
        records=world.records,
        raw_factory=lambda: (lambda: world.records.raw(pre),),
        clock=world.clock,
        profile=profile,
        plan=plan,
        start=start,
        segment_nonce=nonce,
        epoch_id=epoch,
        authority=world.gate,
        authority_hash=H,
        writer_release_evidence=release,
        secret_guard=lambda raw: response.secret_guard(raw, KEY),
        previous_hash=snap["bootstrap_acquisition_sha256"],
    )
    second = {
        **admission,
        "segment_nonce": nonce,
        "epoch_id": epoch,
        "segment_id": 2,
        "predecessor_closure_sha256": snap["segment_closure_sha256"],
        "bootstrap_acquisition_sha256": bootstrap,
        "preflight_observation_sha256": pre,
        "admitted_utc": now,
    }
    world.releases[nonce] = release
    second_inputs = (profile, plan, start, science, second, rows)
    with pytest.raises(c.Stage12Error, match="RECORD_DISCREPANCY"):
        world.run("second", inputs=second_inputs, predecessor=tmp_path / "first")


"""Additional independent defect reproductions; synthetic-only, not acceptance."""
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_b2_audit as audit,
    s12_transport as transport,
    s12_public_journal as journal,
)


def test_R03_timeout_is_not_HTTP_completion(tmp_path):
    w = World(tmp_path, count=1)
    calls = []

    def dispatch(work, target, hooks):
        calls.append(work)
        if len(calls) > 1:
            return w.dispatch(work, target, hooks)
        hooks.started(w.clock.now_ns())
        hooks.emit(lambda: None, lambda: None)
        cap = transport.Capture(
            "TECHNICAL_FAILURE_RETRYABLE",
            "TIMEOUT",
            None,
            "ABSENT",
            "absent",
            None,
            None,
            0,
            1,
        )
        hooks.signal(None, cap.outcome, cap.reason, None)
        hooks.completed(cap)
        return cap

    report, _ = w.run(dispatch=dispatch)
    assert report["report_complete"]
    assert len(calls) == 2
    assert (
        report["counts"]["http_completions"]["value"] == 1
    )  # only final attempt has an HTTP response


def test_R03_duration_includes_final_durable_work(tmp_path, monkeypatch):
    w = World(tmp_path, count=1)
    original = audit.finish

    def delayed(*args, **kwargs):
        result = original(*args, **kwargs)
        w.clock.advance(20_000_000)
        return result

    monkeypatch.setattr(audit, "finish", delayed)
    report, inputs = w.run()
    events = list(
        journal.read_events(tmp_path / "segment", b.digest(inputs[2]), contract=o)
    )
    first = next(
        e["body"]["started_mono_ns"] for e in events if e["kind"] == "ATTEMPT_STARTED"
    )
    measured_end = max(
        e["body"]["observed_mono_ns"]
        for e in events
        if e["kind"] == "RESOURCE" and e["body"]["cause"] == "PERIODIC"
    )
    assert report["report_complete"]
    assert report["duration_ns"] == measured_end - first


from dataclasses import replace
from stage12_synthetic import body, feature
from test_stage12_b2_calibration import memory_observations
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_b2_calibration as cal,
)


def test_R05_within_T_novelty_rejects_despite_direct_C_membership(tmp_path):
    world = World(tmp_path, count=1)
    selection = world.selection
    observations = memory_observations(world, selection)

    def reader(obs):
        def read(q):
            a, z = feature(), feature()
            z["properties"]["name"] = "Synthetic alternative retained at C"
            features = (
                [a] * 5 + [z]
                if obs.kind == "TAIL"
                else [a]
                if obs.size == 1
                else [a, z]
            )
            raw = body(features)
            p = response.extract(
                raw,
                b.sha(q + obs.kind.encode() + str(obs.size).encode()),
                size=obs.size,
                layers=world.rules.layers,
                sources=world.rules.sources,
                expected_echo={},
                http_status=200,
                content_type="application/json",
                encoding="absent",
            )
            return p, raw

        return read

    observations = [replace(x, read=reader(x)) for x in observations]
    q = next(world.catalog.semantics())["query_semantic_id"]
    ctx = next(world.catalog.contexts(q))
    tail = next(x for x in observations if x.kind == "TAIL")
    tp, tr = tail.read(q)
    assert cal.witness(tp, tr, ctx, tail.size) - cal.witness(
        tp, tr, ctx, selection["C"]
    )  # prohibited within-T novelty at rank6
    result = cal.evaluate(
        world.catalog,
        selection,
        observations,
        window_hash=world.window_hash,
        selection_hash=world.selection_hash,
        authority=world.gate,
        comparison_writer=lambda row: None,
    )
    assert result["tail_adequate"] is False
    assert result["eligible_limits"] == []


@pytest.mark.parametrize("bound", ["count", "bytes", "duration"])
def test_R04_refuse_before_factory_and_begin_when_closure_reserve_insufficient(
    tmp_path, bound
):
    w = World(tmp_path)
    profile, plan, start, science, admission, rows = w.inputs()
    if bound == "count":
        plan["budgets"]["administrative_operations"] = plan["blocks"][0]["budget"][
            "administrative_operations"
        ] = 1
    if bound == "bytes":
        profile["administrative"]["max_total_bytes"] = 262144
    if bound == "duration":
        plan["budgets"]["administrative_duration_ms"] = plan["blocks"][0]["budget"][
            "administrative_duration_ms"
        ] = 1999
    plan["operations_profile_sha256"] = b.digest(profile)
    invoked = []

    def factory():
        invoked.append(True)
        return (lambda: w.records.raw(H),)

    with pytest.raises(c.Stage12Error, match="B2_ADMIN_CLOSURE_RESERVE"):
        pipe.prepare_bootstrap(
            tmp_path / "refused",
            records=w.records,
            raw_factory=factory,
            clock=w.clock,
            profile=profile,
            plan=plan,
            start=start,
            segment_nonce=admission["segment_nonce"],
            epoch_id=admission["epoch_id"],
            authority=w.gate,
            authority_hash=H,
            writer_release_evidence=w.releases[admission["segment_nonce"]],
            secret_guard=lambda raw: None,
        )
    assert not invoked and not (tmp_path / "refused").exists()


def test_R04_exact_cap_finite_bundle_no_lookahead(tmp_path):
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as j

    w = World(tmp_path)
    raw = w.records.raw(H)
    calls = []
    bounds = {
        "max_records": 1,
        "max_record_bytes": len(raw),
        "max_total_bytes": len(raw),
        "max_duration_ms": 1,
        "acquisition_contract_sha256": w.acquisition_hash,
    }
    writer = j.Writer(tmp_path / "acquire", 1, 1000, lambda: None)

    def load():
        calls.append(1)
        w.clock.advance(1_000_000)
        return raw

    try:
        begin, end = evidence.acquire(
            w.records,
            lambda: (load,),
            writer=writer,
            clock=w.clock,
            campaign_id=H,
            segment_nonce=w.nonce(),
            epoch_id=w.nonce(),
            bounds=bounds,
            authority=w.gate,
            authority_hash=H,
            ordinal=1,
            secret_guard=lambda raw: response.secret_guard(raw, KEY),
        )
        assert (
            calls == [1]
            and end["outcome"] == "ACQUIRED"
            and end["total_bytes"] == len(raw)
            and end["elapsed_ms"] == 1
        )
    finally:
        writer.abort()


def test_R08_recomputed_scientific_id_rejects_inconsistent_binding(tmp_path):
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_publication as pub

    w = World(tmp_path)
    _, inputs = w.run()
    root = tmp_path / "published"
    expected, validate, _ = publish_world(w, inputs, tmp_path / "segment", root)
    m = validate()
    m["publication_bindings"]["scientific_result_sha256"] = H
    with pytest.raises(c.Stage12Error, match="B2_SCIENTIFIC_HASH"):
        pub.scientific_reopen(
            root,
            m,
            catalog=w.catalog,
            rules=w.rules,
            scratch=tmp_path / "rejected",
            memory_bytes=64 * 1024 * 1024,
            gate=w.gate,
            verify_campaign=lambda: None,
        )


def test_R03_DATA_retry_denominator_excludes_controls_and_unknown_epochs(tmp_path):
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_b2_reporting as reporting,
    )

    w = World(tmp_path, count=1)
    calls = []

    def dispatch(work, target, hooks):
        calls.append(1)
        if len(calls) > 1:
            return w.dispatch(work, target, hooks)
        hooks.started(w.clock.now_ns())
        hooks.emit(lambda: None, lambda: None)
        cap = transport.Capture(
            "TECHNICAL_FAILURE_RETRYABLE",
            "TIMEOUT",
            None,
            "ABSENT",
            "absent",
            None,
            None,
            0,
            1,
        )
        hooks.signal(None, cap.outcome, cap.reason, None)
        hooks.completed(cap)
        return cap

    report, inputs = w.run(dispatch=dispatch)
    assert report["rates"]["retry_fraction"] == {"num": 1, "den": 2}
    # Add a verified control start to the same validated report prefix. This is a
    # report-unit fixture, not a valid campaign/recovery artifact.
    profile, plan, start, science, admission, rows = inputs
    events = list(
        journal.read_events(tmp_path / "segment", b.digest(start), contract=o)
    )
    sample = next(x for x in events if x["kind"] == "ATTEMPT_STARTED")
    extra = deepcopy(sample)
    extra["body"]["work_id"] = 2
    extra["body"]["attempt"] = 1
    extra["seq"] = max(x["seq"] for x in events) + 1
    control = {
        **rows[0],
        "kind": "SERVICE_CONTROL",
        "work_id": 2,
        "query_semantic_id": None,
        "result_limit": None,
        "repetition": None,
        "recipe_id": 1,
        "retry_spacing_key": H,
    }

    def receipts(work, event):
        return audit.reopen(
            tmp_path
            / "segment/attempts"
            / f"{work['work_id']:020d}_{event['attempt']:02d}",
            **w.rules.kwargs(),
        )[0]

    index = reporting.Index(
        tmp_path / "mixed.sqlite",
        lambda: iter([*events, extra]),
        lambda: iter([*rows, control]),
        receipts,
        max_bytes=4 * 1024 * 1024,
    )
    try:
        measured = reporting.measurement(
            index,
            profile,
            plan,
            start,
            attempt_inventory=H,
            administrative_spent={"operations": 2, "duration_ms": 0, "bytes": 0},
            disposition="COMPLETED",
        )
        assert measured["rates"]["retry_fraction"] == {"num": 1, "den": 2}
        assert measured["counts"]["control_attempt_starts"]["value"] == 1
        assert not measured["report_complete"]
    finally:
        index.close()


def test_R06_finite_category_and_response_byte_summary(tmp_path):
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_diagnostics as d

    w = World(tmp_path, count=1)
    calls = []

    def dispatch(work, target, hooks):
        calls.append(work)
        if len(calls) > 1:
            return w.dispatch(work, target, hooks)
        hooks.started(w.clock.now_ns())
        hooks.emit(lambda: None, lambda: None)
        cap = transport.Capture(
            "TECHNICAL_FAILURE_RETRYABLE",
            "TIMEOUT",
            None,
            "ABSENT",
            "absent",
            None,
            None,
            0,
            1,
        )
        hooks.signal(None, cap.outcome, cap.reason, None)
        hooks.completed(cap)
        return cap

    _, inputs = w.run(dispatch=dispatch)
    _, validate, _ = publish_world(w, inputs, tmp_path / "segment", tmp_path / "pub")
    validate()
    summary = io.metadata(io.read(tmp_path / "pub/summary.json"))["operational"]
    attempts = summary["attempt_categories_and_bytes"]["by_kind"]["DATA"]
    assert attempts["charged_attempts"] == 2 and attempts["category_totals_exact"]
    categories = {x["http_category"]: x for x in attempts["categories"]}
    assert categories["NO_HTTP_RESPONSE"]["attempts"]["value"] == 1
    assert categories["NO_HTTP_RESPONSE"]["final_failures"]["value"] == 0
    assert categories["HTTP_200"]["retries"]["value"] == 1
    published = summary["published_successful_response_bytes"]
    assert (
        attempts["retained_raw_bytes"]["value"]
        == published["uncompressed_application_bytes"]
        > 0
    )
    assert (
        attempts["retained_compressed_bytes"]["value"] > 0
        and published["physical_compressed_bytes"] > 0
    )
    # Mixed valid/unavailable receipts must preserve known lower bounds, not zero.
    (tmp_path / "segment/attempts/00000000000000000001_01/receipt.json").unlink()
    unknown = d.attempt_summary(tmp_path / "segment", b.digest(inputs[2]))["by_kind"][
        "DATA"
    ]
    assert not unknown["category_totals_exact"] and unknown["unverified_attempts"] == 1
    assert unknown["retained_raw_bytes"]["value"] is None
    assert (
        unknown["retained_raw_bytes"]["confirmed_min"]
        == published["uncompressed_application_bytes"]
    )
