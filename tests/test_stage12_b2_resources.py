"""B2-RS1 synthetic accounting only; no live capacity or authority fixture."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from stage12_b2_synthetic import World, H
from test_stage12_b2_runtime import configuration, pin, port, prep_grants
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_b2_contract as b,
    s12_b2_operations as operations,
    s12_b2_resources as resources,
    s12_b2_runtime as runtime,
    s12_storage as io,
    s12_retrieval_contract as contract,
)


def model(plan=None):
    plans = [] if plan is None else plan if isinstance(plan, list) else [plan]
    members = [resources.member_workload(item) for item in plans]
    limits = {name: 1 for name in set(resources.COUNTS.values())}
    phases = resources.ASSET["mandatory_command_phases"]
    limits.update(
        data_works=sum(x["data_works"] for x in members) if plans else 1,
        data_attempts=sum(x["data_attempts"] for x in members) if plans else 1,
        control_works=(sum(x["control_works"] for x in members) if plans else 1),
        control_attempts=(sum(x["control_attempts"] for x in members) if plans else 1),
        candidate_rows=(sum(x["candidate_rows"] for x in members) if plans else 1),
        ledger_rows=(sum(x["ledger_rows"] for x in members) if plans else 2),
        events=sum(x["events"] for x in members) if plans else 1,
        max_candidates_per_work=(
            max(x["result_limit"] for x in members) if plans else 1
        ),
        max_response_bytes=16 * 2**20,
        commands=len(phases),
    )
    components = []
    command_allocations = [dict.fromkeys(sorted(resources.COUNTS), 0) for _ in phases]
    for name in sorted(resources.COUNTS):
        predicate = (
            "TERMINAL_BODY_ONCE"
            if name in ("DATA_RAW", "CONTROL_RAW")
            else "EVERY_ATTEMPT"
            if name
            in (
                "DATA_ATTEMPT_METADATA",
                "CONTROL_ATTEMPT_METADATA",
                "CONTROL_VERIFICATION",
            )
            else "TRANSIENT_NO_RECLAIM"
            if name
            in (
                "SQLITE_JOURNAL",
                "DUCKDB_SPILL",
                "PARTIAL_WRITES",
                "CLOSURE_UNCERTAINTY",
            )
            else "DERIVED_RETAINED"
        )
        count = limits[resources.COUNTS[name]]
        if resources.COUNTS[name] == "commands":
            for allocations in command_allocations:
                allocations[name] = 1
        else:
            command_allocations[len(components) % len(phases)][name] = count
        components.append(
            {
                "component_id": name,
                "state_predicate": predicate,
                "count_bound": count,
                "per_instance_bytes_bound": 1,
                "per_instance_inodes_bound": 1,
                "max_simultaneous_instances": count,
                "retained_after_phase": True,
                "evidence_sha256": H,
            }
        )
    value = {
        "schema_version": resources.MODEL,
        "scope": "DEVELOPMENT_ONLY",
        "population_scope": "SYNTHETIC_TEST_ONLY",
        "adopted_clauses_sha256": resources.ASSET["adopted_source_sha256"],
        "source_inventory_sha256": H,
        "runtime_inventory_sha256": H,
        "codec_inventory_sha256": H,
        "encoding_inventory_sha256": H,
        "workload_sha256": H,
        "review_sha256": H,
        "retry_state_proof_sha256": H,
        "capacity_record_sha256": H,
        "capacity_owner_authority_sha256": H,
        "filesystem_accounting_sha256": H,
        "valid_from": "2025-01-01T00:00:00.000000Z",
        "valid_until": "2027-01-01T00:00:00.000000Z",
        "block_bytes": 4096,
        "inode_overhead_bytes": 128,
        "capacity_bytes": 1,
        "capacity_inodes": 1,
        "limits": limits,
        "member_workloads": sorted(
            members,
            key=lambda x: x["plan_binding_sha256"],
        )
        if plans
        else [
            {
                "plan_binding_sha256": H,
                "data_works": limits["data_works"],
                "data_attempts": limits["data_attempts"],
                "control_works": limits["control_works"],
                "control_attempts": limits["control_attempts"],
                "candidate_rows": limits["candidate_rows"],
                "events": limits["events"],
                "ledger_rows": limits["ledger_rows"],
                "result_limit": limits["max_candidates_per_work"],
            },
        ],
        "components": components,
        "commands": [
            {
                "command_id": index,
                "phase": phase,
                "scope_sha256": H if index == 1 else f"{index:064x}",
                "allocations": allocations,
                "max_generated_bytes": 1,
                "max_generated_inodes": 1,
                "max_memory_bytes": 2**20,
                "max_duration_ms": 1000,
                "bound_evidence_sha256": H,
            }
            for index, (phase, allocations) in enumerate(
                zip(phases, command_allocations, strict=True), 1
            )
        ],
        "retained_payload_bound_bytes": 1,
        "physical_peak_bound_bytes": 1,
        "physical_inode_bound": 1,
    }
    amounts = [resources.component_bytes(x, value) for x in components]
    value["retained_payload_bound_bytes"] = sum(x[2] for x in amounts)
    value["physical_peak_bound_bytes"] = sum(x[0] for x in amounts)
    value["physical_inode_bound"] = sum(x[1] for x in amounts)
    value["capacity_bytes"] = value["physical_peak_bound_bytes"]
    value["capacity_inodes"] = value["physical_inode_bound"]
    value["workload_sha256"] = resources.aggregate_workload_hash(value)
    by_id = {x["component_id"]: x for x in components}
    for command in value["commands"]:
        amounts = [
            resources.component_bytes({**by_id[name], "count_bound": count}, value)
            for name, count in command["allocations"].items()
        ]
        command["max_generated_bytes"] = sum(x[0] for x in amounts)
        command["max_generated_inodes"] = sum(x[1] for x in amounts)
    return value


def test_closed_model_derives_every_component_and_rejects_unknowns():
    value = model()
    assert resources.validate_model(value)["physical_bytes"] > 0
    for mutation in (
        lambda x: x["components"].pop(),
        lambda x: x["components"][0].update(count_bound=2),
        lambda x: x["components"][0].update(retained_after_phase=False),
        lambda x: x.update(capacity_bytes=None),
        lambda x: x["commands"][0]["allocations"].update(ACCOUNTING_LEDGER=0),
    ):
        changed = deepcopy(value)
        mutation(changed)
        with pytest.raises((contract.Stage12Error, TypeError)):
            resources.validate_model(changed)

    incomplete = deepcopy(value)
    incomplete["commands"][-1]["phase"] = "publish"
    with pytest.raises(contract.Stage12Error, match="B2_RS1_COMMAND_GRAPH"):
        resources.validate_model(incomplete)


def test_rs1_profile_plan_parse_without_reinterpreting_o1(tmp_path):
    world = World(tmp_path, count=1)
    profile, plan, *_ = world.inputs()
    operations.validate_plan(profile=profile, plan=plan)
    successor_plan = deepcopy(plan)
    successor_plan["schema_version"] = resources.PLAN
    successor_plan["resource_retention_model_sha256"] = H
    successor_plan["resource_workload_sha256"] = resources.workload_binding(
        successor_plan
    )
    successor_profile = deepcopy(profile)
    successor_profile["schema_version"] = resources.PROFILE
    successor_profile["resource_retention_model"] = model(successor_plan)
    successor_plan["operations_profile_sha256"] = operations.digest(successor_profile)
    successor_plan["resource_retention_model_sha256"] = operations.digest(
        successor_profile["resource_retention_model"]
    )
    operations.validate_plan(successor_plan, successor_profile)
    changed = deepcopy(successor_plan)
    changed["resource_retention_model_sha256"] = "1" * 64
    with pytest.raises(contract.Stage12Error, match="B2_RS1_PLAN_BINDING"):
        operations.validate_plan(changed, successor_profile)
    changed = deepcopy(successor_plan)
    changed["operations_profile_sha256"] = "1" * 64
    with pytest.raises(contract.Stage12Error, match="B2_RS1_PLAN_BINDING"):
        operations.validate_plan(changed, successor_profile)

    mismatched_plan = deepcopy(successor_plan)
    mismatched_plan["budgets"]["data_attempts"] -= 1
    mismatched_plan["blocks"][0]["budget"] = mismatched_plan["budgets"]
    mismatched_plan["resource_workload_sha256"] = resources.workload_binding(
        mismatched_plan
    )
    with pytest.raises(contract.Stage12Error, match="B2_RS1_WORKLOAD_DERIVATION"):
        operations.validate_plan(mismatched_plan, successor_profile)


def test_aggregate_model_binds_distinct_member_plans_without_reset(tmp_path):
    world = World(tmp_path, count=2)
    first_profile, first, *_ = world.inputs(size=5)
    _, second, *_ = world.inputs(size=40)
    members = []
    for plan in (first, second):
        item = deepcopy(plan)
        item["schema_version"] = resources.PLAN
        item["resource_retention_model_sha256"] = H
        item["resource_workload_sha256"] = resources.workload_binding(item)
        members.append(item)
    retained = model(members)
    profile = deepcopy(first_profile)
    profile["schema_version"] = resources.PROFILE
    profile["resource_retention_model"] = retained
    for plan in members:
        plan["operations_profile_sha256"] = operations.digest(profile)
        plan["resource_retention_model_sha256"] = operations.digest(retained)
        operations.validate_plan(plan, profile)
    assert retained["limits"]["data_works"] == 4
    assert len(retained["member_workloads"]) == 2


def test_command_ledger_blocks_unclean_claim_and_preserves_chain(tmp_path):
    value = model()
    artifact = tmp_path / "artifact"
    artifact.mkdir(mode=0o700)
    (artifact / "one").write_bytes(b"one")
    (artifact / "one").chmod(0o600)
    ledger = resources.CommandLedger(
        tmp_path / "ledger",
        value,
        command_id=1,
        phase="build-catalog",
        scope_hash=H,
        check=lambda: None,
    )
    with pytest.raises(contract.Stage12Error):
        resources.CommandLedger(
            tmp_path / "ledger",
            value,
            command_id=1,
            phase="build-catalog",
            scope_hash=H,
            check=lambda: None,
        )
    ledger.finish(roots=[artifact], max_entries=10)
    assert not (tmp_path / "ledger/ACTIVE.json").exists()


def test_command_ledger_reopens_cumulative_originals(tmp_path):
    value = model()
    artifact = tmp_path / "artifact"
    artifact.mkdir(mode=0o700)
    (artifact / "one").write_bytes(b"one")
    (artifact / "one").chmod(0o600)
    first = resources.CommandLedger(
        tmp_path / "ledger",
        value,
        command_id=1,
        phase="build-catalog",
        scope_hash=H,
        check=lambda: None,
    )
    first.finish(roots=[artifact], max_entries=10)
    (artifact / "one").unlink()
    with pytest.raises(contract.Stage12Error, match="CUMULATIVE_INVENTORY_CHANGED"):
        resources.CommandLedger(
            tmp_path / "ledger",
            value,
            command_id=2,
            phase="plan-calibration",
            scope_hash=f"{2:064x}",
            check=lambda: None,
        )


def test_active_command_deadline_memory_and_generation_envelopes(tmp_path):
    world = World(tmp_path)
    fake = SimpleNamespace(
        clock=world.clock,
        _closed=False,
        deadline=world.clock.now_ns() + 10_000_000_000,
        resource_command_deadline=world.clock.now_ns() + 1_000_000,
        phase_until="2027-01-01T00:00:00.000000Z",
        settings={
            "phase_memory_bytes": 2**63,
            "phase_generation_check_ms": 1000,
            "phase_generation_max_files": 100,
            "phase_generation_bound_bytes": 2**20,
        },
        resource_command={
            "max_memory_bytes": 2**63,
            "max_generated_bytes": 0,
            "max_generated_inodes": 0,
        },
        local_only=False,
        phase="run-campaign",
        _generation_roots=None,
        _checking_generation=False,
        _last_generation_check=world.clock.now_ns(),
    )
    runtime.RuntimePort.check_deadline(fake)
    world.clock.advance(2_000_000)
    with pytest.raises(contract.Stage12Error, match="B2_RUNTIME_DEADLINE"):
        runtime.RuntimePort.check_deadline(fake)

    root = tmp_path / "generated"
    root.mkdir(mode=0o700)
    fake.resource_command_deadline = world.clock.now_ns() + 1_000_000_000
    fake._generation_roots = (root,)
    fake._generation_paths = lambda: [root]
    fake._record_generated_bytes = fake._record_generated_files = 0
    fake.check_deadline = lambda: None
    with pytest.raises(contract.Stage12Error, match="B2_RS1_COMMAND_BOUND"):
        runtime.RuntimePort.reconcile_generation(fake)


def test_campaign_command_scope_is_acyclic_and_runtime_bound(tmp_path):
    world = World(tmp_path, count=1)
    values = world.inputs()
    legacy_profile, legacy_plan, start, science, admission, rows = values
    config, constructor_gate, grants = configuration(
        world,
        phase="run-campaign",
        mode="EXACT_AUTHORIZED_DISPATCH",
    )
    output = world.root / "runtime_segment"
    work_path = world.root / "rs1_work.jsonl"
    work_raw = b"".join(b.canonical(row) for row in rows)
    io.write(work_path, work_raw)
    inventory = {
        "version": "stage12_development_runtime_inventory_v1",
        "population_scope": b.SYNTHETIC,
        "python_version": runtime.platform.python_version(),
        "platform": runtime.platform.system(),
        "source_inventory_sha256": b.digest(config["runtime"]["source_files"]),
        "continuous_service_state": "NOT_VERIFIED",
        "resource_sampling_is_service_monitoring": False,
        "scientific_identity_verified": False,
    }
    plan = deepcopy(legacy_plan)
    plan["schema_version"] = resources.PLAN
    plan["resource_retention_model_sha256"] = H
    plan["resource_workload_sha256"] = resources.workload_binding(plan)
    config["runtime"].update(
        phase_memory_bytes=legacy_profile["resources"]["job_memory_bytes"],
        phase_disk_capacity_bytes=legacy_plan["budgets"]["storage_bytes"],
        campaign={
            "profile_sha256": H,
            "plan_sha256": H,
            "start_sha256": world.put(start),
            "scientific_start_sha256": world.put(science),
            "admission_sha256": world.put(admission),
            "work_path": str(work_path),
            "work_file_sha256": b.sha(work_raw).hex(),
            "segment_path": str(output),
            "predecessor_path": None,
            "runtime_inventory_sha256": world.put(inventory),
            "pause_after_ms": 900000,
            "control_adapters": {},
        },
        transport={
            "origin": "https://geocode.safe-frankfurt.de",
            "approved_ip": "192.0.2.1",
            "configuration_evidence_sha256": H,
            "target_limit": 65536,
            "header_limit": 65536,
        },
        postflight_bundle_path=str(world.root / "postflight.json"),
    )
    retained = model(plan)
    retained["source_inventory_sha256"] = b.digest(config["runtime"]["source_files"])
    retained["runtime_inventory_sha256"] = b.digest(inventory)
    run = next(x for x in retained["commands"] if x["phase"] == "run-campaign")
    others = [x for x in retained["commands"] if x is not run]
    retained["commands"] = [run, *others]
    for command_id, command in enumerate(retained["commands"], 1):
        command["command_id"] = command_id
        command["max_memory_bytes"] = config["runtime"]["phase_memory_bytes"]
        command["scope_sha256"] = f"{command_id:064x}"
    run = retained["commands"][0]
    run["scope_sha256"] = resources.command_scope(
        config, plan_binding=resources.workload_binding(plan)
    )
    resources.validate_model(retained)
    model_hash = world.put(retained)
    config["runtime"]["resource_retention"] = {
        "model_sha256": model_hash,
        "command_id": 1,
    }
    profile = deepcopy(legacy_profile)
    profile["schema_version"] = resources.PROFILE
    profile["resource_retention_model"] = retained
    plan["operations_profile_sha256"] = operations.digest(profile)
    plan["resource_retention_model_sha256"] = operations.digest(retained)
    config["runtime"]["campaign"]["profile_sha256"] = world.put(profile)
    config["runtime"]["campaign"]["plan_sha256"] = world.put(plan)
    assert run["scope_sha256"] == resources.command_scope(
        config, plan_binding=resources.workload_binding(plan)
    )
    ignored = deepcopy(config)
    for name in (
        "profile_sha256",
        "plan_sha256",
        "start_sha256",
        "scientific_start_sha256",
        "admission_sha256",
    ):
        ignored["runtime"]["campaign"][name] = "f" * 64
    ignored["runtime"]["authority_sha256"] = "e" * 64
    ignored["runtime"]["resource_retention"] = {
        "model_sha256": "d" * 64,
        "command_id": 2,
    }
    assert run["scope_sha256"] == resources.command_scope(
        ignored, plan_binding=resources.workload_binding(plan)
    )
    changed = deepcopy(config)
    changed["runtime"]["campaign"]["work_file_sha256"] = "c" * 64
    assert run["scope_sha256"] != resources.command_scope(
        changed, plan_binding=resources.workload_binding(plan)
    )
    projected = resources.command_scope_record(
        config, plan_binding=resources.workload_binding(plan)
    )

    def leaves(value, prefix=()):
        if isinstance(value, dict):
            for key, child in value.items():
                yield from leaves(child, (*prefix, key))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                yield from leaves(child, (*prefix, index))
        else:
            yield prefix

    for path in leaves(projected):
        mutated = deepcopy(projected)
        target = mutated
        for part in path[:-1]:
            target = target[part]
        old = target[path[-1]]
        target[path[-1]] = old + 1 if type(old) is int else "CHANGED"
        assert b.digest(mutated) != run["scope_sha256"]

    for field in (
        "review_sha256",
        "retry_state_proof_sha256",
        "capacity_record_sha256",
        "capacity_owner_authority_sha256",
        "filesystem_accounting_sha256",
        "codec_inventory_sha256",
        "encoding_inventory_sha256",
    ):
        grants.require(
            "resource_retention_" + field.removesuffix("_sha256"), H, retained
        )
    for item in (*retained["components"], *retained["commands"]):
        grants.require(
            "resource_retention_bound",
            item.get("evidence_sha256", item.get("bound_evidence_sha256")),
            item,
        )
    grants.require("resource_retention", b.digest(retained), retained)
    prep_grants(world, config, constructor_gate, grants)
    grants.require(
        "transport", profile["transport_profile_sha256"], config["runtime"]["transport"]
    )
    pin(world, config, grants)
    candidate = port(world, config)
    candidate.bind_session(
        "run-campaign", config, output, world.root / "scratch.sqlite", H
    )
    assert candidate.resource_ledger is not None
    assert candidate.resource_command["command_id"] == 1
    candidate.close()
