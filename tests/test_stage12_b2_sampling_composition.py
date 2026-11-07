"""Real protected pipeline with invented inputs, test authority and transport."""

from copy import deepcopy

import pytest

from stage12_b2_synthetic import World, H
from test_stage12_b2_acceptance_graph import envelope, recalculate
from test_stage12_public_operations_v2 import offline  # noqa: F401
from test_stage12_public_sampling_integration import RealClock
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_b2_sampling_contract as a,
    s12_b2_contract as b,
    s12_b2_operations as operations,
    s12_b2_resources as rs,
    s12_b2_acceptance_graph as graph,
    s12_b2_pipeline as pipeline,
    s12_b2_recovery as recovery,
    s12_wf_ap2_assurance as assurance,
    s12_retrieval_contract as c,
)


def selected_model(world, plan):
    value, _ = envelope(world)
    member = rs.member_workload(plan)
    value["member_envelopes"] = [
        {
            "member_id": 1,
            "workload_kind": plan["workload_kind"],
            "repetition": plan["repetition"],
            "permitted_result_limits": [plan["result_limit"]],
            **{name: member[name] for name in graph.COUNTS},
        },
        value["member_envelopes"][1],
    ]
    value["limits"].update(
        {
            name: sum(row[name] for row in value["member_envelopes"])
            for name in graph.COUNTS
        }
    )
    value["limits"]["max_candidates_per_work"] = plan["result_limit"]
    for component in value["components"]:
        name = component["component_id"]
        amount = (
            value["ledger_record_limits"]["max_entries"]
            if name == "ACCOUNTING_LEDGER"
            else value["limits"][rs.COUNTS[name]]
        )
        component.update(count_bound=amount, max_simultaneous_instances=amount)
        for slot in value["slots"]:
            slot["allocations"][name] = (
                1
                if rs.COUNTS[name] == "commands" and name != "ACCOUNTING_LEDGER"
                else amount
                if slot["slot_id"] == 1
                else 0
            )
    recalculate(value)
    value["workload_sha256"] = graph.envelope_workload_hash(value)
    graph.validate_model(value)
    return value


def ap_inputs(world):
    world.runtime = {
        "version": "SYNTHETIC_TEST_ONLY_AP_RUNTIME",
        "scope": b.SYNTHETIC,
        "wf_ap2_runtime_facts": assurance.runtime_facts(),
    }
    profile, plan, start, science, admission, rows = world.inputs()
    world.clock = RealClock()
    world.gate.clock = world.clock
    profile.update(
        schema_version=a.PROFILE,
        rule_bundle_sha256=a.RULE_BUNDLE,
        sampling_policy_sha256=a.POLICY_SHA,
        sampling_runtime_bound_sha256=H,
        **a.extra_binding_fields(),
    )
    profile.pop("resource_sample_period_ms")
    profile["resources"]["writer_guard_ms"] = 5000
    profile["resources"]["process_overhead_bytes"] = max(
        profile["resources"]["process_overhead_bytes"], 16 * 2**20
    )
    plan.update(
        schema_version=a.PLAN,
        resource_retention_model_sha256=H,
        resource_workload_sha256=H,
        history_limits={
            "maximum_entries": 50000,
            "maximum_name_bytes": 1024,
            "maximum_total_name_bytes": 32 * 2**20,
            "page_entries": 4,
            "maximum_depth": 8,
            "maximum_file_bytes": 2**30,
        },
    )
    plan["budgets"]["active_duration_ms"] = 100000
    plan["blocks"][0]["budget"] = plan["budgets"]
    observations = 2002
    files = 4 * observations + 8
    plan["sampling_budget"] = {
        "maximum_segments": 1,
        "maximum_observations": observations,
        "maximum_inventory_versions_per_segment": 8,
        "additional_event_tokens": 2 * observations + 4,
        "additional_file_entries": files + 8 + 1502,
        "additional_file_data_bytes": 4096 * files
        + 8 * (512 * files + 4096)
        + 50200576,
    }
    plan["resource_workload_sha256"] = rs.workload_binding(plan)
    model = selected_model(world, plan)
    profile["resource_retention_model"] = model
    plan["resource_retention_model_sha256"] = b.digest(model)
    amounts = dict.fromkeys(assurance.ARENAS, 0)
    amounts.update(
        SAMPLE_SLOTS=65536,
        HISTORY_PAGES=8 * 2**20,
        TELEMETRY_RING=4096 * 512,
        SERIALIZATION_SCRATCH=63616,
        TRACE_METADATA=65536,
        CONTROLLER_METADATA=65536,
    )
    domain = {
        "path": "/sys/fs/cgroup/synthetic",
        "device": 1,
        "inode": 2,
        "cgroup_namespace_inode": 3,
        "mount_namespace_inode": 4,
        "boot_id": H[:32],
        "memory_max_bytes": 6 * 2**30,
        "swap_max_bytes": 0,
        "pids_max": 128,
    }
    bound = {
        "schema_version": assurance.BOUND,
        "scope": a.SCOPE,
        "method": assurance.METHOD,
        "sampling_policy_sha256": a.POLICY_SHA,
        "client_git_sha": start["client_git_sha"],
        "runtime_inventory_sha256": start["runtime_inventory_sha256"],
        "configuration_scope_sha256": H,
        "invocation_graph_sha256": b.digest(model),
        "technical_review_record_sha256": H,
        "enforcement_evidence_sha256": H,
        "domain_coverage_evidence_sha256": H,
        "method_evidence_sha256": [H],
        "evidence_origin": "SYNTHETIC_TEST_ONLY",
        "maximum_enforcement_checks": 1000,
        "maximum_runtime_inventory_checks": 64,
        "valid_from": "2025-01-01T00:00:00.000000Z",
        "valid_until": "2027-01-01T00:00:00.000000Z",
        "logical_allocations": [
            {"name": name, "bytes": amounts[name], "evidence_sha256": H}
            for name in assurance.ARENAS
        ],
        "total_logical_bytes": sum(amounts.values()),
        "logical_scratch_bytes": amounts["SERIALIZATION_SCRATCH"],
        "native_component_guarantee": "NOT_CLAIMED",
        "native_scratch_guarantee": "NOT_CLAIMED",
        "domain": domain,
    }
    profile["sampling_runtime_bound_sha256"] = b.digest(bound)
    plan["operations_profile_sha256"] = b.digest(profile)
    science.update(
        operations_policy_sha256=b.digest(profile), workload_sha256=b.digest(plan)
    )
    start.update(
        schema_version=a.START,
        profile_sha256=b.digest(profile),
        plan_sha256=b.digest(plan),
        rule_bundle_sha256=a.RULE_BUNDLE,
        sampling_policy_sha256=a.POLICY_SHA,
        scientific_campaign_start_sha256=b.digest(science),
        **a.extra_binding_fields(),
    )
    authority = world.gate.authority
    authority.clock = world.clock
    authority.test_only = True
    authority.configuration_scope_sha256 = H
    authority.charge_enforcement_check = lambda record: None
    authority.sampling_bound = lambda profile, start: deepcopy(bound)
    authority.enforcement_facts = lambda record: {
        **record["domain"],
        "membership_matches": True,
        "nondelegated": True,
        "no_capabilities": True,
        "descendants_share_domain": True,
        "no_new_privileges": True,
        "pids_current": 4,
        "observation_origin": "KERNEL_CGROUP_V2",
    }
    admission.update(
        campaign_start_sha256=b.digest(science),
        operations_campaign_sha256=b.digest(start),
    )
    bootstrap = pipeline.prepare_bootstrap(
        world.root / "ap_bootstrap",
        records=world.records,
        raw_factory=lambda: (lambda: world.records.raw(H),),
        clock=world.clock,
        profile=profile,
        plan=plan,
        start=start,
        segment_nonce=admission["segment_nonce"],
        epoch_id=admission["epoch_id"],
        authority=world.gate,
        authority_hash=H,
        writer_release_evidence=world.releases[admission["segment_nonce"]],
        secret_guard=lambda raw: None,
    )
    admission["bootstrap_acquisition_sha256"] = bootstrap
    return profile, plan, start, science, admission, rows


def test_exact_opt_in_and_strict_protected_contract(tmp_path):
    world = World(tmp_path, count=1)
    profile, plan, start, *_ = ap_inputs(world)
    assert operations.for_profile(profile) is a
    assert operations.for_start(start) is a
    operations.validate_plan(plan, profile)
    a.verify_authorities(profile, plan, start, world.gate)
    for change in (
        lambda p: p["monitoring"].update(mode="PUBLIC_GAPS_ONLY"),
        lambda p: p.update(sampling_policy_sha256=H),
        lambda p: p.update(sampling_assurance_method="CLOSED_ALLOCATION_INVENTORY"),
    ):
        changed = deepcopy(profile)
        change(changed)
        with pytest.raises(c.Stage12Error):
            operations.validate_plan(plan, changed)
    world.gate.authority.test_only = False
    with pytest.raises(c.Stage12Error, match="WF_AP2_TEST_AUTHORITY_DENIED"):
        a.verify_authorities(profile, plan, start, world.gate)


def test_tiny_true_protected_synthetic_phase_closes_and_reopens(tmp_path, monkeypatch):
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_history

    world = World(tmp_path, count=1)
    inputs = ap_inputs(world)
    # The real protected opener must use its selected paged bounds, even when
    # the unchanged historical reader's cap is too small for this tiny trace.
    monkeypatch.setattr(s12_public_history, "MAX_ENTRIES", 8)
    report, _ = world.run(inputs=inputs)
    profile, plan, start, *_ = inputs
    assert report["schema_version"] == a.REPORT
    assert report["continuous_service_state"] == "NOT_VERIFIED"
    assert report["sampling_segments"][-1]["complete"]
    assert report["counts"]["durable_valid_data"]["value"] == 1
    root = world.root / "segment"
    reopened = recovery.reopen(
        root,
        start,
        profile,
        plan,
        works=lambda: iter(inputs[-1]),
        verify_receipt=lambda work, event: __import__(
            "safe_geocoding_pipeline.preprocessing.stages.s12_b2_audit",
            fromlist=["reopen"],
        ).reopen(
            root / "attempts" / f"{work['work_id']:020d}_{event['attempt']:02d}",
            **world.rules.kwargs(),
        )[0],
        scratch=world.root / "independent.sqlite",
        authority=world.gate,
    )
    assert reopened["snapshot"]["sampling"]["complete"]
    event = next((root / "events").iterdir())
    event.write_bytes(b"mutated original")
    with pytest.raises((c.Stage12Error, ValueError)):
        recovery.reopen(
            root,
            start,
            profile,
            plan,
            works=lambda: iter(inputs[-1]),
            verify_receipt=lambda *_: None,
            scratch=world.root / "failed.sqlite",
            authority=world.gate,
        )


def test_actual_ap_calibration_publication_and_full_scientific_reopen(
    tmp_path, monkeypatch
):
    import test_stage12_b2_publication as fixture
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_b2_publication as publication,
    )

    world = World(tmp_path, count=1)
    inputs = ap_inputs(world)
    world.run(inputs=inputs)
    monkeypatch.setattr(fixture, "o", a)
    expected, validate, closure = fixture.publish_world(
        world, inputs, tmp_path / "segment", tmp_path / "published"
    )
    manifest = validate()
    assert manifest["completed"] == manifest["planned"] == 1
    assert manifest["failures"] == manifest["unprocessed"] == 0
    assert (
        len(
            list(publication.relation_rows(tmp_path / "published", "request_execution"))
        )
        == 1
    )
    assert (tmp_path / "published" / "_COMMITTED").read_bytes() == b""


@pytest.mark.parametrize("failure", ["strict_warning", "unknown_delivery"])
def test_ap_protected_failures_preserve_evidence_and_cannot_seal(tmp_path, failure):
    import json
    from stage12_synthetic import body

    world = World(tmp_path, count=1)
    inputs = ap_inputs(world)
    calls = []

    def dispatch(work, target, hooks):
        calls.append(work["work_id"])
        if failure == "unknown_delivery":
            hooks.started(world.clock.now_ns())
            hooks.emit(lambda: None, lambda: None)
            raise RuntimeError("SYNTHETIC uncertain writer/provider return")
        raw = json.loads(body([]))
        raw["geocoding"]["warnings"] = [
            "SYNTHETIC warning is forbidden on protected B2"
        ]
        return world.dispatch(work, target, hooks, raw=b.canonical(raw))

    with pytest.raises(c.Stage12Error):
        world.run(inputs=inputs, dispatch=dispatch)
    assert calls == [1]
    assert not (world.root / "segment" / "_SEGMENT_SEALED").exists()
    assert list((world.root / "segment" / "attempts").rglob("begin.json"))
    assert (world.root / "segment_telemetry").exists()


def test_canonical_new_protected_assets_and_historical_opt_in(tmp_path):
    from pathlib import Path

    for name, descriptor in a.descriptors().items():
        assert (
            Path("docs/scientific_assets") / (name + ".json")
        ).read_bytes() == c.canonical(descriptor)
    world = World(tmp_path, count=1)
    historical = world.inputs()[0]
    assert operations.for_profile(historical) is operations
    assert "incremental_component_memory_bytes" not in a.POLICY
    assert a.POLICY["monitoring_mode"] == "OBSERVED_PREPOST_WINDOW"


def test_runtime_descriptor_guard_rejects_changed_original_asset(tmp_path):
    root = tmp_path / "invented_repository"
    assets = root / "docs" / "scientific_assets"
    assets.mkdir(parents=True)
    for name, descriptor in a.descriptors().items():
        (assets / (name + ".json")).write_bytes(c.canonical(descriptor))
    a.verify_descriptors(root)
    (assets / (a.POLICY_VERSION + ".json")).write_bytes(b'{"synthetic_changed":true}\n')
    with pytest.raises(c.Stage12Error, match="B2_AP_DESCRIPTOR_MISMATCH"):
        a.verify_descriptors(root)


def test_successor_preserves_frozen_types_and_base_count_rate_semantics():
    assert b.TYPES == b.registry()["named_types"]
    with pytest.raises(c.Stage12Error, match="B2_COUNT_INVALID"):
        a.validate_type({"value": 1, "confirmed_min": 0}, "Count")
    with pytest.raises(c.Stage12Error, match="B2_RATE_INVALID"):
        a.validate_type({"num": 2, "den": 2}, "Rate")
