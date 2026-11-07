"""Synthetic-only composed runtime binding; no issued native/capacity facts."""

from copy import deepcopy
from types import SimpleNamespace

from stage12_b2_synthetic import H
from test_stage12_b2_acceptance_graph import recalculate
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_b2_acceptance_graph as graph,
    s12_b2_allocation_limits as limits,
    s12_b2_calibration as calibration,
    s12_b2_contract as b,
    s12_b2_operations as operations,
    s12_b2_resources as resources,
    s12_b2_runtime as runtime,
    s12_storage as io,
)


def prepare_model(world, values, config):
    """Reserve the finite synthetic graph; caller then finalizes AP identities."""
    profile, plan, *_ = values
    # These large limits are labelled synthetic ceilings, never live facts.
    profile["resources"]["allocated_disk_bytes"] = 16 * 2**30
    plan["budgets"]["storage_bytes"] = 16 * 2**30
    plan["blocks"][0]["budget"] = plan["budgets"]
    model = deepcopy(profile["resource_retention_model"])
    first = model["slots"][0]
    run = next(x for x in model["slots"] if x["phase"] == "run-campaign")
    for field in ("phase", "member_role", "member_id", "condition"):
        first[field], run[field] = run[field], first[field]
    first["max_duration_ms"] = 180000
    for slot in model["slots"]:
        slot["max_memory_bytes"] = profile["resources"]["job_memory_bytes"]
    workload = resources.member_workload(plan)
    model["member_envelopes"][0] = {
        "member_id": 1,
        "workload_kind": plan["workload_kind"],
        "repetition": plan["repetition"],
        "permitted_result_limits": [plan["result_limit"]],
        **{name: workload[name] for name in graph.COUNTS},
    }
    model["limits"].update(
        {name: sum(x[name] for x in model["member_envelopes"]) for name in graph.COUNTS}
    )
    model["limits"].update(
        sqlite_invocations=500,
        duckdb_invocations=20,
        inventory_rows=200,
        max_candidates_per_work=max(
            max(x["permitted_result_limits"]) for x in model["member_envelopes"]
        ),
    )
    model["source_inventory_sha256"] = b.digest(config["runtime"]["source_files"])
    model["runtime_inventory_sha256"] = b.digest(
        runtime.RuntimePort._actual_runtime_inventory(
            SimpleNamespace(population_scope=b.SYNTHETIC, settings=config["runtime"]),
            successor=False,
        )
    )
    for component in model["components"]:
        name = component["component_id"]
        count = (
            model["ledger_record_limits"]["max_entries"]
            if name == "ACCOUNTING_LEDGER"
            else model["limits"][resources.COUNTS[name]]
        )
        component.update(count_bound=count, max_simultaneous_instances=count)
        component["per_instance_bytes_bound"] = (
            65536
            if name in ("ACCOUNTING_LEDGER", "INVENTORIES")
            else 8 * 2**20
            if name in ("SQLITE_INDEX", "SQLITE_JOURNAL")
            else 16 * 2**20
            if name in ("DUCKDB_DATABASE", "DUCKDB_SPILL", "DATA_RAW", "CONTROL_RAW")
            else 8192
            if name == "EVENTS"
            else 2**20
        )
        for slot in model["slots"]:
            slot["allocations"][name] = (
                1
                if resources.COUNTS[name] == "commands" and name != "ACCOUNTING_LEDGER"
                else count
                if slot["slot_id"] == 1
                else 0
            )
    selected = {
        "schema_version": limits.VERSION,
        "model_sha256": H,
        "command_id": 1,
        "review_sha256": H,
        "native_bound_evidence_sha256": H,
        "max_compressed_frame_bytes": 2**20,
        "max_candidate_buffer_bytes": 2**20,
        "max_arrow_batch_bytes": 2**20,
        "max_parquet_file_bytes": 2**20,
        "max_raw_pack_bytes": 2**20,
        "max_python_write_bytes": 128 * 2**20,
        "sqlite_main_bytes": 8 * 2**20,
        "duckdb_spill_bytes": 16 * 2**20,
        "invocations": dict.fromkeys(limits.ROLES, 0),
    }
    selected["invocations"].update(
        SQLITE=480,
        DUCKDB=20,
        EXCLUSIVE_FILE=1000,
        EVENT_FILE=1000,
        PREFIX_FILE=32,
        COMPARISON_FILE=100,
        ADMIN_FILE=100,
        CONTROL_BEGIN=plan["budgets"]["control_http_attempts"],
        CONTROL_FINISH=plan["budgets"]["control_http_attempts"],
        PARQUET_FILE=100,
        RAW_PACK_FILE=100,
        COMPRESSED_FRAME=first["allocations"]["DATA_RAW"]
        + first["allocations"]["CONTROL_RAW"]
        + first["allocations"]["RAW_PACKS"],
        CANDIDATE_BUFFER=plan["budgets"]["data_observations"],
    )
    ceiling = {
        name: deepcopy(value)
        for name, value in selected.items()
        if name
        not in (
            "model_sha256",
            "command_id",
            "review_sha256",
            "native_bound_evidence_sha256",
        )
    }
    ceiling["schema_version"] = graph.CEILING
    first["allocation_limit_ceiling_sha256"] = world.put(ceiling)
    recalculate(model)
    model["workload_sha256"] = graph.envelope_workload_hash(model)
    graph.validate_model(model)
    selected["model_sha256"] = world.put(model)
    profile["resource_retention_model"] = model
    plan["resource_retention_model_sha256"] = b.digest(model)
    plan["resource_workload_sha256"] = resources.workload_binding(plan)
    return model, selected


def bind_member_and_slot(world, values, config, model, selected):
    """Append real original bindings after the caller finalizes all AP records."""
    profile, plan, _, _, _, _ = values
    operations.validate_plan(plan, profile)
    spec = config["runtime"]["campaign"]
    work = runtime.WorkFile(
        runtime.absolute(spec["work_path"]),
        spec["work_file_sha256"],
        plan,
        lambda: None,
    )
    selection = calibration.select(
        world.catalog,
        world.root / "graph_binding_selection.sqlite",
        C=5,
        T=12,
        supported=40,
        authority=world.gate,
        decision_hash=H,
    )
    originals = graph.ScientificOriginals(
        world.records,
        world.gate,
        member_source=lambda row: (profile, plan, work, world.catalog, selection, None),
        calibration_source=lambda row: None,
        campaign_source=lambda row: None,
        publication_source=lambda row: None,
        check=lambda: None,
    )
    ledger = graph.AcceptanceLedger(
        world.root / ("rs1_acceptance_" + b.digest(model)),
        model,
        records=world.records,
        authority=world.gate,
        originals=originals,
        check=lambda: None,
        now=world.clock.utc,
    )
    member = {
        "schema_version": graph.MEMBER,
        "envelope_sha256": b.digest(model),
        "member_id": 1,
        "previous_ledger_sha256": None,
        "plan_binding_sha256": resources.workload_binding(plan),
        "exact_plan_sha256": world.put(plan),
        "work_file_sha256": spec["work_file_sha256"],
        "window_plan_sha256": world.window_hash,
        "calibration_selection_sha256": world.selection_hash,
        "N_decision_sha256": None,
        "bound_utc": world.clock.utc(),
    }
    ledger.append_member(member)
    selected_hash = world.put(selected)
    config["runtime"]["resource_retention"] = {
        "model_sha256": b.digest(model),
        "command_id": 1,
        "allocation_limits_sha256": selected_hash,
    }
    local_hash = world.put(
        {
            "version": "SYNTHETIC_TEST_ONLY_GRAPH_AUTHORITY",
            "population_scope": b.SYNTHETIC,
        }
    )
    prerequisites = sorted(
        [
            {"record_kind": "LOCAL_AUTHORITY", "sha256": local_hash},
            {"record_kind": "WINDOW_PLAN", "sha256": world.window_hash},
            {"record_kind": "CALIBRATION_SELECTION", "sha256": world.selection_hash},
        ],
        key=lambda row: (row["record_kind"], row["sha256"]),
    )
    binding = {
        "schema_version": graph.BINDING,
        "envelope_sha256": b.digest(model),
        "slot_id": 1,
        "previous_ledger_sha256": ledger.head,
        "configuration_scope_sha256": world.put(
            graph.configuration_scope_record(config)
        ),
        "command_scope_sha256": graph.command_scope(
            config, plan_binding=member["plan_binding_sha256"]
        ),
        "member_binding_sha256": b.digest(member),
        "source_inventory_sha256": model["source_inventory_sha256"],
        "runtime_inventory_sha256": model["runtime_inventory_sha256"],
        "allocation_limits_sha256": selected_hash,
        "prerequisite_inventory_sha256": world.put(prerequisites),
        "bound_utc": world.clock.utc(),
    }
    config["runtime"]["resource_retention"]["slot_binding_sha256"] = (
        ledger.append_binding(binding, config)
    )
    grants = []
    for field in (
        "adoption_sha256",
        "review_sha256",
        "retry_state_proof_sha256",
        "capacity_record_sha256",
        "capacity_owner_authority_sha256",
        "filesystem_accounting_sha256",
        "codec_inventory_sha256",
        "encoding_inventory_sha256",
    ):
        grants.append(
            ("resource_retention_" + field.removesuffix("_sha256"), model[field], model)
        )
    grants.extend(
        ("resource_retention_bound", item["evidence_sha256"], item)
        for item in model["components"]
    )
    for slot in model["slots"]:
        ceiling = graph.parse(
            world.records.raw(slot["allocation_limit_ceiling_sha256"]), graph.CEILING
        )
        grants.append(
            ("resource_retention_allocation_ceiling", b.digest(ceiling), ceiling)
        )
    grants.extend(
        [
            ("resource_retention", b.digest(model), model),
            ("resource_retention_native_bound", H, selected),
            ("resource_retention_allocation_limits", selected_hash, selected),
            ("resource_graph_binding", b.digest(member), member),
            ("resource_graph_binding", b.digest(binding), binding),
            (
                "resource_graph_begin",
                b.digest(binding),
                {
                    "configuration_sha256": runtime.scope_hash(config),
                    "slot_binding_sha256": b.digest(binding),
                },
            ),
        ]
    )
    for row in prerequisites:
        grants.append(
            (
                "resource_graph_prerequisite_" + row["record_kind"].lower(),
                row["sha256"],
                io.metadata(world.records.raw(row["sha256"])),
            )
        )
    return ledger, member, binding, grants
