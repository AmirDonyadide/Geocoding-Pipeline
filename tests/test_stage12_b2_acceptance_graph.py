"""Invented acceptance envelopes. These tests issue no live resource model/N."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from stage12_b2_synthetic import World, H
from test_stage12_b2_resources import model as legacy_model
from test_stage12_b2_allocation_limits import selection
from test_stage12_b2_runtime import configuration, pin, port, prep_grants
from safe_geocoding_pipeline.preprocessing import stage12_development_cli as cli
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_b2_acceptance_graph as g,
    s12_b2_allocation_limits as limits,
    s12_b2_contract as b,
    s12_b2_resources as rs,
    s12_b2_runtime as runtime,
    s12_retrieval_contract as c,
    s12_storage as io,
)


class NoScientificOriginals:
    """Mechanics-only fixture that cannot manufacture a scientific binding."""

    def member(self, *args):
        raise AssertionError("this fixture cannot bind scientific members")

    branch = member
    skip = member

    def prerequisite(self, kind, digest, **kwargs):
        assert kind == "LOCAL_AUTHORITY" and len(digest) == 64


def envelope(world, *, first="plan-calibration", config=None):
    old = legacy_model()
    selected = selection(sqlite_main_bytes=65536, max_python_write_bytes=2**20)
    selected["invocations"] = dict.fromkeys(limits.ROLES, 0)
    selected["invocations"].update(SQLITE=20, EXCLUSIVE_FILE=40, PREFIX_FILE=3)
    ceiling = {
        k: deepcopy(v)
        for k, v in selected.items()
        if k
        not in (
            "model_sha256",
            "command_id",
            "review_sha256",
            "native_bound_evidence_sha256",
        )
    }
    ceiling["schema_version"] = g.CEILING
    ceiling_hash = world.put(ceiling)
    phases = [first, *[p for p in rs.ASSET["mandatory_command_phases"] if p != first]]
    direct_phases = [
        "build-workload",
        "offline-preflight",
        "prepare-bootstrap",
        "preflight",
        "run-direct-n",
        "close-campaign",
    ]
    checkpoint = phases.index("evaluate-calibration") + 1
    phases[checkpoint:checkpoint] = direct_phases
    phases.append("reopen")
    members = [
        {
            "member_id": 1,
            "workload_kind": "FULL_C",
            "repetition": 0,
            "permitted_result_limits": [5],
            **{key: old["limits"][key] for key in g.COUNTS},
        }
    ]
    members[0]["candidate_rows"] = 5 * members[0]["data_works"]
    members.append(
        {
            **members[0],
            "member_id": 2,
            "workload_kind": "DIRECT_N",
            "permitted_result_limits": [1, 3],
            "candidate_rows": 3 * members[0]["data_works"],
        }
    )
    model = {
        k: deepcopy(v)
        for k, v in old.items()
        if k not in ("member_workloads", "commands")
    }
    count = len(phases)
    ll = {
        "max_member_bindings": 2,
        "max_slot_bindings": count,
        "max_begins": count,
        "max_terminals": count,
        "max_branch_records": 1,
        "max_prerequisite_rows": 16,
        "max_prerequisite_bytes": 65536,
        "max_record_bytes": 65536,
        "max_entries": 9 + 3 * count,
    }
    ll["max_total_bytes"] = ll["max_entries"] * ll["max_record_bytes"]
    model.update(
        schema_version=g.MODEL,
        parent_descriptor_sha256=rs.DESCRIPTOR_SHA256,
        successor_descriptor_sha256=g.DESCRIPTOR_SHA256,
        adoption_sha256=H,
        window_policy="ONE_DECLARED_SP_B_R2_WINDOW",
        member_envelopes=members,
        ledger_record_limits=ll,
    )
    model["limits"]["sqlite_invocations"] = 20
    model["limits"].update(
        {key: sum(member[key] for member in members) for key in g.COUNTS}
    )
    model["limits"].update(commands=count, max_candidates_per_work=5)
    model["source_inventory_sha256"] = (
        b.digest(config["runtime"]["source_files"]) if config else b.digest([])
    )
    model["runtime_inventory_sha256"] = (
        b.digest(
            runtime.RuntimePort._actual_runtime_inventory(
                SimpleNamespace(
                    population_scope=b.SYNTHETIC, settings=config["runtime"]
                )
            )
        )
        if config
        else H
    )
    model["slots"] = []
    for index, phase in enumerate(phases, 1):
        role = (
            "NONE"
            if phase
            in (
                "build-catalog",
                "plan-calibration",
                "build-workload",
                "offline-preflight",
                "prepare-bootstrap",
                "evaluate-calibration",
                "close-window",
            )
            else "FIXED_MEMBER"
        )
        if phase in ("publish", "reopen"):
            role = "SELECTED_FINAL"
        direct = checkpoint < index <= checkpoint + len(direct_phases)
        model["slots"].append(
            {
                "slot_id": index,
                "phase": phase,
                "member_role": role,
                "member_id": (2 if direct else 1) if role == "FIXED_MEMBER" else None,
                "condition": "DIRECT_N_BRANCH" if direct else "REQUIRED",
                "predecessor_slot_id": index - 1,
                "max_duration_ms": 10000,
                "max_memory_bytes": 2**40,
                "max_generated_bytes": 1,
                "max_generated_inodes": 1,
                "allocations": dict.fromkeys(rs.COUNTS, 0),
                "allocation_limit_ceiling_sha256": ceiling_hash,
                "predicate_version": "RS1_ACCEPTANCE_GRAPH_V1",
            }
        )
    for component in model["components"]:
        name = component["component_id"]
        amount = (
            ll["max_entries"]
            if name == "ACCOUNTING_LEDGER"
            else model["limits"][rs.COUNTS[name]]
        )
        component.update(
            count_bound=amount,
            max_simultaneous_instances=amount,
            per_instance_bytes_bound=65536
            if name == "SQLITE_INDEX"
            else 65536
            if name in ("ACCOUNTING_LEDGER", "INVENTORIES")
            else 1,
        )
        if rs.COUNTS[name] == "commands" and name != "ACCOUNTING_LEDGER":
            for slot in model["slots"]:
                slot["allocations"][name] = 1
        else:
            model["slots"][0]["allocations"][name] = amount
    recalculate(model)
    model["workload_sha256"] = g.envelope_workload_hash(model)
    selected.update(model_sha256=b.digest(model))
    return model, selected


def recalculate(model):
    components = {x["component_id"]: x for x in model["components"]}
    amounts = [rs.component_bytes(x, model) for x in components.values()]
    model.update(
        physical_peak_bound_bytes=sum(x[0] for x in amounts),
        physical_inode_bound=sum(x[1] for x in amounts),
        retained_payload_bound_bytes=sum(x[2] for x in amounts),
    )
    model.update(
        capacity_bytes=model["physical_peak_bound_bytes"],
        capacity_inodes=model["physical_inode_bound"],
    )
    for slot in model["slots"]:
        amounts = [
            rs.component_bytes({**components[name], "count_bound": number}, model)
            for name, number in slot["allocations"].items()
        ]
        slot.update(
            max_generated_bytes=sum(x[0] for x in amounts),
            max_generated_inodes=sum(x[1] for x in amounts),
        )


def setup_ledger(world, config=None):
    model, selected = envelope(world, config=config)
    assert g.validate_model(model)["physical_bytes"] > 0
    world.put(model)
    root = world.root / ("rs1_acceptance_" + b.digest(model))
    ledger = g.AcceptanceLedger(
        root,
        model,
        records=world.records,
        authority=world.gate,
        originals=NoScientificOriginals(),
        check=lambda: None,
        now=world.clock.utc,
    )
    return ledger, model, selected


def bind_first(world, ledger, selected, config=None):
    config = (
        deepcopy(config)
        if config
        else {
            "runtime": {
                "phase": "plan-calibration",
                "source_files": [],
                "campaign": None,
                "authority_sha256": H,
            }
        }
    )
    pointer = {
        "model_sha256": b.digest(ledger.model),
        "command_id": 1,
        "allocation_limits_sha256": world.put(selected),
    }
    config["runtime"]["resource_retention"] = pointer
    config.setdefault(
        "command_paths",
        {
            "output_path": str(world.root / "actual_graph_output"),
            "scratch_path": str(world.root / "actual_graph.sqlite"),
        },
    )
    projection = g.configuration_scope_record(config)
    scope = world.put(projection)
    local_authority = world.put(
        {
            "version": "SYNTHETIC_TEST_ONLY_GRAPH_AUTHORITY",
            "population_scope": b.SYNTHETIC,
        }
    )
    proofs = world.put([{"record_kind": "LOCAL_AUTHORITY", "sha256": local_authority}])
    row = {
        "schema_version": g.BINDING,
        "envelope_sha256": b.digest(ledger.model),
        "slot_id": 1,
        "previous_ledger_sha256": ledger.head,
        "configuration_scope_sha256": scope,
        "command_scope_sha256": g.command_scope(config),
        "member_binding_sha256": None,
        "source_inventory_sha256": ledger.model["source_inventory_sha256"],
        "runtime_inventory_sha256": ledger.model["runtime_inventory_sha256"],
        "allocation_limits_sha256": pointer["allocation_limits_sha256"],
        "prerequisite_inventory_sha256": proofs,
        "bound_utc": world.clock.utc(),
    }
    binding = ledger.append_binding(row, config)
    pointer["slot_binding_sha256"] = binding
    return config, row


def test_closed_envelope_and_legacy_semantics_remain_separate(tmp_path):
    world = World(tmp_path)
    model, _ = envelope(world)
    assert rs.validate_model(model) == g.validate_model(model)
    assert rs.validate_model(legacy_model())["physical_bytes"] > 0
    for mutation in (
        lambda x: x.update(schema_version=rs.MODEL),
        lambda x: x.update(adoption_sha256="0" * 64),
        lambda x: x["slots"][0].update(predecessor_slot_id=1),
        lambda x: x["slots"][0].update(condition="OPTIONAL_INDEPENDENT_REOPEN"),
        lambda x: x["ledger_record_limits"].update(max_branch_records=0),
        lambda x: x["components"][0].update(per_instance_bytes_bound=0),
        lambda x: x.update(capacity_bytes=1),
        lambda x: x.update(unknown=True),
    ):
        changed = deepcopy(model)
        mutation(changed)
        with pytest.raises(c.Stage12Error):
            rs.validate_model(changed)


def test_exact_binding_begin_finish_and_original_reopen(tmp_path):
    world = World(tmp_path)
    ledger, model, selected = setup_ledger(world)
    config, row = bind_first(world, ledger, selected)
    assert ledger.next_slot == 1
    ledger.begin(config, b.digest(row))
    output = tmp_path / "generated"
    io.reserve(output)
    io.write(output / "one", b"original bytes")
    ledger.finish(roots=[output], max_entries=10)
    assert ledger.next_slot == 2
    assert ledger.accounting()["reserved_bytes"] == model["physical_peak_bound_bytes"]
    assert not (ledger.root / "ACTIVE.json").exists()
    (output / "one").write_bytes(b"changed bytes!")
    with pytest.raises(c.Stage12Error, match="INVENTORY_CHANGED"):
        ledger.reopen()


def test_unbegun_binding_only_identical_config_can_resume(tmp_path):
    world = World(tmp_path)
    ledger, _, selected = setup_ledger(world)
    config, row = bind_first(world, ledger, selected)
    changed = deepcopy(config)
    changed["new_top_level_field"] = True
    with pytest.raises(c.Stage12Error, match="CONFIGURATION_SCOPE"):
        ledger.begin(changed, b.digest(row))
    with pytest.raises(c.Stage12Error, match="BINDING_ORDER"):
        ledger.append_binding(row, config)
    ledger.begin(config, b.digest(row))
    with pytest.raises(c.Stage12Error, match="BLOCKED"):
        g.AcceptanceLedger(
            ledger.root,
            ledger.model,
            records=world.records,
            authority=world.gate,
            originals=NoScientificOriginals(),
            check=lambda: None,
            now=world.clock.utc,
            expected_head=ledger.head,
        )


@pytest.mark.parametrize(
    "change", ["extra", "missing", "mutated", "partial", "uncertain"]
)
def test_original_ledger_change_blocks(tmp_path, change):
    world = World(tmp_path)
    ledger, _, selected = setup_ledger(world)
    bind_first(world, ledger, selected)
    if change == "extra":
        io.write(ledger.root / "extra", b"x")
    elif change == "missing":
        (ledger.root / "000001.json").unlink()
    elif change == "mutated":
        (ledger.root / "000001.json").write_bytes(b"{}\n")
    elif change == "partial":
        io.write(ledger.root / "000002.json", b"{")
    else:
        io.write(ledger.root / "MUTATING.json", b"{}\n")
    with pytest.raises((c.Stage12Error, ValueError, KeyError)):
        ledger.reopen()


@pytest.mark.parametrize("name", ["000001.json", "model.json", "OWNER.json", "ACTIVE.json"])
def test_begin_rechecks_originals_after_semantic_callbacks(tmp_path, name):
    world = World(tmp_path, count=1)
    ledger, _, selected = setup_ledger(world)
    config, row = bind_first(world, ledger, selected)
    original_require = world.gate.authority.require
    injected = False

    def require(purpose, *args, **kwargs):
        nonlocal injected
        result = original_require(purpose, *args, **kwargs)
        if purpose == "resource_graph_binding" and (ledger.root / "ACTIVE.json").exists() and not injected:
            injected = True
            target = ledger.root / name
            raw = target.read_bytes()
            # Same pathname/inode/length: a directory-only fence is insufficient.
            target.write_bytes(b"x" + raw[1:])
        return result

    world.gate.authority.require = require
    with pytest.raises(c.Stage12Error):
        ledger.begin(config, b.digest(row))
    assert injected and ledger.poisoned
    assert (ledger.root / "MUTATING.json").exists()
    assert (ledger.root / "ACTIVE.json").exists()
    with pytest.raises(c.Stage12Error, match="BLOCKED"):
        ledger.reopen(allow_active=True)


def test_same_bytes_replacement_after_callback_is_not_accepted(tmp_path):
    world = World(tmp_path, count=1)
    ledger, _, selected = setup_ledger(world)
    config, row = bind_first(world, ledger, selected)
    original_require = world.gate.authority.require
    injected = False

    def require(purpose, *args, **kwargs):
        nonlocal injected
        result = original_require(purpose, *args, **kwargs)
        if purpose == "resource_graph_binding" and (ledger.root / "ACTIVE.json").exists() and not injected:
            injected = True
            target = ledger.root / "000001.json"
            raw = target.read_bytes()
            target.unlink()
            io.write(target, raw)
        return result

    world.gate.authority.require = require
    with pytest.raises(c.Stage12Error, match="LEDGER_CHANGED"):
        ledger.begin(config, b.digest(row))
    assert injected and ledger.poisoned
    assert (ledger.root / "ACTIVE.json").exists()


def test_configuration_cycle_exclusions_are_exact(tmp_path):
    world = World(tmp_path)
    ledger, _, selected = setup_ledger(world)
    config, _ = bind_first(world, ledger, selected)
    original = g.configuration_scope(config)
    for field in ("authority_sha256",):
        changed = deepcopy(config)
        changed["runtime"][field] = "f" * 64
        assert g.configuration_scope(changed) == original
    changed = deepcopy(config)
    changed["runtime"]["resource_retention"]["slot_binding_sha256"] = "f" * 64
    assert g.configuration_scope(changed) == original
    for field in ("model_sha256", "allocation_limits_sha256", "command_id"):
        changed = deepcopy(config)
        changed["runtime"]["resource_retention"][field] = (
            2 if field == "command_id" else "f" * 64
        )
        assert g.configuration_scope(changed) != original


def test_partial_binding_write_and_fsync_failure_preserve_claim(tmp_path, monkeypatch):
    world = World(tmp_path)
    ledger, _, selected = setup_ledger(world)
    real = io.write

    def fail(path, raw):
        if path.name == "000001.json":
            real(path, raw[:7])
            raise OSError("invented bounded failure")
        return real(path, raw)

    monkeypatch.setattr(io, "write", fail)
    with pytest.raises(OSError):
        bind_first(world, ledger, selected)
    assert (ledger.root / "MUTATING.json").exists()
    with pytest.raises(c.Stage12Error, match="BLOCKED"):
        ledger.reopen()


def test_selected_counter_crossing_does_not_refund(tmp_path):
    world = World(tmp_path)
    ledger, model, selected = setup_ledger(world)
    controls = limits.Controls(selected)
    for _ in range(selected["invocations"]["SQLITE"]):
        controls.claim("SQLITE")
    with pytest.raises(c.Stage12Error, match="INVOCATION_BUDGET"):
        controls.claim("SQLITE")
    assert controls.counts["SQLITE"] == selected["invocations"]["SQLITE"]
    assert ledger.accounting()["reserved_bytes"] == model["physical_peak_bound_bytes"]


def test_actual_runtime_entry_starts_graph_and_shared_allocation_counters(tmp_path):
    world = World(tmp_path, count=1)
    config, gate, grants = configuration(world)
    config["runtime"].update(
        phase_disk_capacity_bytes=2**32,
        phase_memory_bytes=2**40,
        phase_generation_bound_bytes=2**30,
        phase_generation_max_files=10000,
    )
    ledger, model, selected = setup_ledger(world, config)
    config, binding = bind_first(world, ledger, selected, config)
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
        grants.require(
            "resource_retention_" + field.removesuffix("_sha256"), model[field], model
        )
    for component in model["components"]:
        grants.require(
            "resource_retention_bound", component["evidence_sha256"], component
        )
    for slot in model["slots"]:
        ceiling = g.parse(
            world.records.raw(slot["allocation_limit_ceiling_sha256"]), g.CEILING
        )
        grants.require(
            "resource_retention_allocation_ceiling", b.digest(ceiling), ceiling
        )
    grants.require("resource_retention", b.digest(model), model)
    selected_hash = b.digest(selected)
    grants.require(
        "resource_retention_native_bound",
        selected["native_bound_evidence_sha256"],
        selected,
    )
    grants.require("resource_retention_allocation_limits", selected_hash, selected)
    local_hash = __import__("json").loads(
        world.records.raw(binding["prerequisite_inventory_sha256"])
    )[0]["sha256"]
    grants.require(
        "resource_graph_prerequisite_local_authority",
        local_hash,
        io.metadata(world.records.raw(local_hash)),
    )
    grants.require("resource_graph_binding", b.digest(binding), binding)
    grants.require(
        "resource_graph_begin",
        b.digest(binding),
        {
            "configuration_sha256": runtime.scope_hash(config),
            "slot_binding_sha256": b.digest(binding),
        },
    )
    prep_grants(world, config, gate, grants)
    pin(world, config, grants)
    candidate = port(world, config)
    result = cli.execute(
        "plan-calibration",
        cli.Session(
            candidate,
            config,
            tmp_path / "actual_graph_output",
            tmp_path / "actual_graph.sqlite",
            H,
        ),
    )
    assert result["scientific_N_selected"] is False
    assert isinstance(candidate.resource_ledger, g.AcceptanceLedger)
    assert candidate.resource_ledger.finished
    assert candidate.allocation_limits.counts["SQLITE"] >= 2
    assert (
        candidate.resource_ledger.accounting()["reserved_bytes"]
        == model["physical_peak_bound_bytes"]
    )


@pytest.mark.parametrize("before_admission", [False, True])
def test_actual_member_plan_workfile_membership_and_mutation(
    tmp_path, before_admission
):
    from test_stage12_b2_sampling_composition import ap_inputs
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_calibration as cal

    world = World(tmp_path, count=2)
    profile, plan, _, _, admission, rows = ap_inputs(world)
    model = profile["resource_retention_model"]
    target = next(x for x in model["slots"] if x["phase"] == "preflight")
    model["slots"][0]["phase"], target["phase"] = (
        target["phase"],
        model["slots"][0]["phase"],
    )
    model["slots"][0].update(member_role="FIXED_MEMBER", member_id=1)
    target.update(member_role="NONE", member_id=None)
    world.put(model)
    plan["resource_retention_model_sha256"] = b.digest(model)
    plan["operations_profile_sha256"] = b.digest(profile)
    path = tmp_path / "actual_member_work.jsonl"
    raw = b"".join(b.canonical(row) for row in rows)
    io.write(path, raw)
    work = runtime.WorkFile(path, b.sha(raw).hex(), plan, lambda: None)
    selection = cal.select(
        world.catalog,
        tmp_path / "member_selection.sqlite",
        C=5,
        T=12,
        supported=40,
        authority=world.gate,
        decision_hash=H,
    )
    originals = g.ScientificOriginals(
        world.records,
        world.gate,
        member_source=lambda row: (
            profile,
            plan,
            work,
            world.catalog,
            selection,
            None if before_admission else admission,
        ),
        calibration_source=lambda row: None,
        campaign_source=lambda row: None,
        publication_source=lambda row: None,
        check=lambda: None,
    )
    ledger = g.AcceptanceLedger(
        tmp_path / "actual_member_ledger",
        model,
        records=world.records,
        authority=world.gate,
        originals=originals,
        check=lambda: None,
        now=world.clock.utc,
    )
    row = {
        "schema_version": g.MEMBER,
        "envelope_sha256": b.digest(model),
        "member_id": 1,
        "previous_ledger_sha256": None,
        "plan_binding_sha256": rs.workload_binding(plan),
        "exact_plan_sha256": world.put(plan),
        "work_file_sha256": work.expected,
        "window_plan_sha256": world.window_hash,
        "calibration_selection_sha256": world.selection_hash,
        "N_decision_sha256": None,
        "bound_utc": world.clock.utc(),
    }
    ledger.append_member(row)
    assert ledger.members[1] == row
    with pytest.raises(c.Stage12Error, match="MEMBER_ORDER"):
        ledger.append_member(row)
    path.write_bytes(raw.replace(b"DATA", b"XXXX", 1))
    with pytest.raises(c.Stage12Error):
        ledger.reopen()


@pytest.mark.parametrize("N", [1, 5])
def test_actual_complete_publications_adequacy_and_later_owner_branch(tmp_path, N):
    from test_stage12_b2_publication import publish_world
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_calibration as cal
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_b2_publication as publication,
    )

    world = World(tmp_path, count=1)
    selection = cal.select(
        world.catalog,
        tmp_path / "branch_selection.sqlite",
        C=5,
        T=12,
        supported=40,
        authority=world.gate,
        decision_hash=H,
    )
    readers = []
    campaign_values = []
    try:
        for index, intent in enumerate(selection["intents"]):
            values = world.inputs(
                size=intent["size"],
                kind=intent["kind"],
                repetition=intent["repetition"],
                subset=intent["subset"],
            )
            segment = tmp_path / ("branch_segment_" + str(index))
            world.run(segment.name, inputs=values)
            root = tmp_path / ("branch_publication_" + str(index))
            expected, validate, _ = publish_world(world, values, segment, root)
            campaign_values.append(values)
            readers.append(
                publication.ArtifactReader(
                    root,
                    expected,
                    scratch=tmp_path / ("branch_reader_" + str(index) + ".sqlite"),
                    catalog=world.catalog,
                    rules=world.rules,
                    validate_artifact=validate,
                )
            )
        observations = [reader.observation for reader in readers]
        report = cal.evaluate(
            world.catalog,
            selection,
            observations,
            window_hash=world.window_hash,
            selection_hash=world.selection_hash,
            authority=world.gate,
            comparison_writer=lambda row: None,
        )
        inventory = sorted(
            [
                {
                    "workload_kind": x.kind,
                    "publication_sha256": x.publication_sha256,
                    "campaign_closure_sha256": x.campaign_closure_sha256,
                    "window_plan_sha256": x.window_plan_sha256,
                    "workload_sha256": x.workload_sha256,
                }
                for x in observations
            ],
            key=lambda x: (x["workload_kind"], x["publication_sha256"]),
        )
        world.put(inventory)
        decision = {
            "schema_version": "stage12_n_decision_b2_v1",
            "window_plan_sha256": world.window_hash,
            "calibration_inventory_sha256": b.digest(inventory),
            "adequacy_report_sha256": b.digest(report),
            "owner_delegation_sha256": H,
            "result_limit": N,
            "retrieval_policy_id": c.policy(N)["retrieval_policy_id"].hex(),
            "decision": "SELECTED",
            "decided_utc": world.clock.utc(),
        }
        row = {
            "schema_version": g.BRANCH,
            "envelope_sha256": H,
            "previous_ledger_sha256": H,
            "window_plan_sha256": world.window_hash,
            "calibration_selection_sha256": world.selection_hash,
            "calibration_inventory_sha256": b.digest(inventory),
            "adequacy_report_sha256": world.put(report),
            "N_decision_sha256": world.put(decision),
            "C": 5,
            "N": N,
            "branch": "REUSE_FULL_C" if N == 5 else "DIRECT_N",
            "recorded_utc": world.clock.utc(),
        }
        originals = g.ScientificOriginals(
            world.records,
            world.gate,
            member_source=lambda row: None,
            calibration_source=lambda row: (world.catalog, selection, observations),
            campaign_source=lambda row: None,
            publication_source=lambda row: None,
            check=lambda: None,
        )
        assert originals.branch(row, {"population_scope": b.SYNTHETIC}) == report
        if N == 5:
            prove_all_skips_and_final_reuse(
                world, selection, readers, campaign_values, row, inventory
            )
        for mutation in (
            lambda x: x.update(N=3),
            lambda x: x.update(adequacy_report_sha256=H),
            lambda x: x.update(branch="DIRECT_N" if N == 5 else "REUSE_FULL_C"),
        ):
            changed = deepcopy(row)
            mutation(changed)
            with pytest.raises(c.Stage12Error):
                originals.branch(changed, {"population_scope": b.SYNTHETIC})
        (readers[0].root / "campaign.json").write_bytes(b"mutated original")
        with pytest.raises(c.Stage12Error):
            originals.branch(row, {"population_scope": b.SYNTHETIC})
    finally:
        for reader in readers:
            reader.close()


def prove_all_skips_and_final_reuse(
    world, selection, readers, campaign_values, branch, inventory
):
    """Actual full-C final publication and two independently reopened originals."""
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_calibration as cal
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_phase_io as phase_io
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_b2_publication as publication,
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_b2_operations as operations,
    )

    model, _ = envelope(world)
    model_hash = world.put(model)
    branch["envelope_sha256"] = model_hash
    profile, plan, start, science, admission, works = campaign_values[0]
    segment = world.root / "branch_segment_0"
    snapshot = b.parse(io.read(segment / "snapshot.json"), operations.SNAPSHOT)
    full = next(x for x in inventory if x["workload_kind"] == "FULL_C")
    window = world.put(
        {
            "schema_version": "stage12_window_closure_b2_v1",
            "window_plan_sha256": world.window_hash,
            "ordered_campaign_closure_hashes": [
                x.observation.campaign_closure_sha256 for x in readers
            ],
            "operator_campaign_account_sha256": H,
            "account_status": "NO_KNOWN_INTERVENTION",
            "disposition": "CLOSED_OBSERVATIONAL",
            "reviewed_utc": world.clock.utc(),
            "review_decision_sha256": H,
        }
    )
    campaign = phase_io.CampaignReader(
        segment,
        catalog=world.catalog,
        rules=world.rules,
        gate=world.gate,
        closure_hash=full["campaign_closure_sha256"],
        scratch=world.root / "final_reuse_campaign_reader",
        control_adapters={},
    )

    def evaluate():
        return cal.evaluate(
            world.catalog,
            selection,
            [x.observation for x in readers],
            window_hash=world.window_hash,
            selection_hash=world.selection_hash,
            authority=world.gate,
            comparison_writer=lambda row: None,
        )

    root = world.root / "actual_reused_full_C_final"
    decision = world.records.get(branch["N_decision_sha256"], "n_decision")
    expected = publication.publish_campaign(
        root,
        world.root / "final_reuse_publication_work",
        segment=segment,
        start=start,
        scientific_start=science,
        profile=profile,
        plan=plan,
        catalog=world.catalog,
        rules=world.rules,
        gate=world.gate,
        campaign_closure_hash=full["campaign_closure_sha256"],
        verify_campaign=campaign.validate,
        memory_bytes=64 * 2**20,
        window_closure_hash=window,
        calibration_inventory=inventory,
        n_decision=decision,
        verify_calibration=evaluate,
        verify_final_retention=readers[0].validate,
    )

    def validate_final():
        return publication.validate_terminal(
            root,
            expected,
            committed=True,
            validate_science=lambda r, m: publication.scientific_reopen(
                r,
                m,
                catalog=world.catalog,
                rules=world.rules,
                scratch=world.root / ("independent_full_reuse_" + world.nonce()),
                memory_bytes=64 * 2**20,
                gate=world.gate,
                verify_campaign=campaign.validate,
                verify_calibration=evaluate,
                verify_final_retention=readers[0].validate,
            ),
        )

    actual = publication.ArtifactReader(
        root,
        expected,
        scratch=world.root / "actual_final_reuse_reader.sqlite",
        catalog=world.catalog,
        rules=world.rules,
        validate_artifact=validate_final,
    )
    try:
        actual.validate()
        work_raw = b"".join(b.canonical(x) for x in works)
        member = {
            "schema_version": g.MEMBER,
            "envelope_sha256": model_hash,
            "member_id": 1,
            "previous_ledger_sha256": H,
            "plan_binding_sha256": rs.workload_binding(plan),
            "exact_plan_sha256": world.put(plan),
            "work_file_sha256": b.sha(work_raw).hex(),
            "window_plan_sha256": world.window_hash,
            "calibration_selection_sha256": world.selection_hash,
            "N_decision_sha256": None,
            "bound_utc": world.clock.utc(),
        }
        original = g.ScientificOriginals(
            world.records,
            world.gate,
            member_source=lambda row: None,
            calibration_source=lambda row: None,
            campaign_source=lambda row: campaign,
            publication_source=lambda row: actual,
            check=lambda: None,
        )
        record = {
            "schema_version": g.SKIP,
            "envelope_sha256": model_hash,
            "slot_id": 1,
            "previous_ledger_sha256": H,
            "reason": "N_EQUALS_C",
            "proof_inventory_sha256": H,
            "branch_record_sha256": b.digest(branch),
            "recorded_utc": world.clock.utc(),
        }
        decision_proof = [
            {"record_kind": "N_DECISION", "sha256": branch["N_decision_sha256"]}
        ]
        original.skip(
            record, {"condition": "DIRECT_N_BRANCH"}, None, branch, decision_proof
        )
        with pytest.raises(c.Stage12Error):
            original.skip(
                record, {"condition": "REQUIRED"}, None, branch, decision_proof
            )
        record.update(reason="CAMPAIGN_ALREADY_COMPLETE", branch_record_sha256=None)
        segment_proof = [
            {
                "record_kind": "SEGMENT_CLOSURE",
                "sha256": snapshot["segment_closure_sha256"],
            }
        ]
        original.skip(
            record, {"condition": "CONTINUATION_CAPACITY"}, member, None, segment_proof
        )
        with pytest.raises(c.Stage12Error):
            original.skip(
                record,
                {"condition": "CONTINUATION_CAPACITY"},
                {**member, "exact_plan_sha256": H},
                None,
                segment_proof,
            )
        review = {
            "schema_version": "stage12_resource_independent_review_b2_rs1_acceptance_v1",
            "population_scope": b.SYNTHETIC,
            "envelope_sha256": model_hash,
            "member_binding_sha256": b.digest(member),
            "publication_manifest_sha256": expected.hex(),
            "N_decision_sha256": branch["N_decision_sha256"],
            "independent_authority_sha256": H,
            "result": "COMPLETE_NO_UNRESOLVED_DEFECTS",
            "completed_utc": world.clock.utc(),
        }
        record.update(
            reason="INDEPENDENT_REVIEW_ALREADY_COMPLETE",
            branch_record_sha256=b.digest(branch),
        )
        original.skip(
            record,
            {"condition": "OPTIONAL_INDEPENDENT_REOPEN"},
            member,
            branch,
            [{"record_kind": "REVIEW_COMPLETION", "sha256": world.put(review)}],
        )
        bad = {**review, "member_binding_sha256": H}
        with pytest.raises(c.Stage12Error):
            original.skip(
                record,
                {"condition": "OPTIONAL_INDEPENDENT_REOPEN"},
                member,
                branch,
                [{"record_kind": "REVIEW_COMPLETION", "sha256": world.put(bad)}],
            )
        assert (
            actual.manifest["raw_response_set_sha256"]
            == readers[0].manifest["raw_response_set_sha256"]
        )
        assert actual.manifest["planned"] == actual.manifest["completed"] == world.count
    finally:
        actual.close()
        campaign.close()


@pytest.mark.parametrize(
    "change", ["slot", "source", "runtime", "ceiling", "scope", "prerequisite", "time"]
)
def test_binding_near_misses_fail_before_begin(tmp_path, change):
    world = World(tmp_path)
    ledger, _, selected = setup_ledger(world)
    config, row = bind_first(world, ledger, selected)
    # The irreversible binding remains intact; a changed row/config cannot
    # acquire BEGIN or cause the existing binding to be overwritten.
    changed = deepcopy(config)
    if change == "slot":
        changed["runtime"]["resource_retention"]["command_id"] = 2
    elif change == "source":
        changed["runtime"]["source_files"] = [{"different": True}]
    elif change == "runtime":
        changed["runtime"]["version"] = "different"
    elif change == "ceiling":
        changed["runtime"]["resource_retention"]["allocation_limits_sha256"] = H
    elif change == "scope":
        changed["runtime"]["output_parent"] = str(tmp_path / "different")
    elif change == "prerequisite":
        changed["extra_prerequisite"] = H
    else:
        changed["runtime"]["phase_until"] = "2028-01-01T00:00:00.000000Z"
    with pytest.raises(c.Stage12Error):
        ledger.begin(changed, b.digest(row))
    assert not (ledger.root / "ACTIVE.json").exists()
    assert ledger.accounting()["terminal_slots"] == 0


def test_allocation_ceiling_native_and_physical_limits_remain_separate(tmp_path):
    world = World(tmp_path)
    model, selected = envelope(world)
    ceiling = g.parse(
        world.records.raw(model["slots"][0]["allocation_limit_ceiling_sha256"]),
        g.CEILING,
    )
    assert (
        g.validate_ceiling(selected, ceiling, model, model["slots"][0])["slot_id"] == 1
    )
    changed = deepcopy(selected)
    changed["max_candidate_buffer_bytes"] += 1
    with pytest.raises(c.Stage12Error, match="CEILING"):
        g.validate_ceiling(changed, ceiling, model, model["slots"][0])
    world.gate.authority.reject = "resource_retention_allocation_ceiling"
    with pytest.raises(c.Stage12Error, match="SYNTHETIC_AUTHORITY_REJECTED"):
        g.authority_check(
            model,
            world.records,
            world.gate,
            now=world.clock.utc(),
            source_hash=model["source_inventory_sha256"],
            runtime_hash=model["runtime_inventory_sha256"],
        )


def test_mandatory_and_bound_slots_cannot_be_skipped(tmp_path):
    world = World(tmp_path)
    ledger, model, selected = setup_ledger(world)
    proof = world.put([{"record_kind": "N_DECISION", "sha256": H}])
    row = {
        "schema_version": g.SKIP,
        "envelope_sha256": b.digest(model),
        "slot_id": 1,
        "previous_ledger_sha256": None,
        "reason": "N_EQUALS_C",
        "proof_inventory_sha256": proof,
        "branch_record_sha256": None,
        "recorded_utc": world.clock.utc(),
    }
    with pytest.raises(c.Stage12Error, match="SKIP_UNTOUCHED"):
        ledger.skip(row)
    bind_first(world, ledger, selected)
    row["previous_ledger_sha256"] = ledger.head
    with pytest.raises(c.Stage12Error, match="SKIP_UNTOUCHED"):
        ledger.skip(row)
    assert ledger.accounting()["reserved_bytes"] == model["physical_peak_bound_bytes"]


def test_finish_fsync_failure_keeps_active_and_blocks_recovery(tmp_path, monkeypatch):
    world = World(tmp_path)
    ledger, _, selected = setup_ledger(world)
    config, row = bind_first(world, ledger, selected)
    ledger.begin(config, b.digest(row))

    def fail():
        raise OSError("synthetic fsync uncertainty")

    monkeypatch.setattr(ledger, "_sync", fail)
    with pytest.raises(OSError):
        ledger.finish(roots=[tmp_path / "never_generated"], max_entries=10)
    assert (ledger.root / "ACTIVE.json").exists()
    assert (ledger.root / "MUTATING.json").exists()
    with pytest.raises(c.Stage12Error, match="BLOCKED"):
        ledger.reopen(allow_active=True)


def test_post_report_finalization_is_precharged_and_has_no_refund(tmp_path):
    world = World(tmp_path)
    _, _, value = setup_ledger(world)
    controls = limits.Controls(value)
    controls.claim("SQLITE")
    child = controls.reserve_remaining()
    assert controls.counts["SQLITE"] == value["invocations"]["SQLITE"]
    controls.claim("EXCLUSIVE_FILE", 65536)
    assert controls.python_bytes == value["max_python_write_bytes"]
    child.claim("SQLITE")
    assert controls.counts["SQLITE"] == value["invocations"]["SQLITE"]
    with pytest.raises(c.Stage12Error, match="INVOCATION_BUDGET"):
        controls.claim("SQLITE")


def test_complete_segment_skip_proof_needs_no_future_campaign_closure(tmp_path):
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_b2_operations as operations,
    )

    world = World(tmp_path, count=1)
    _, values = world.run()
    model, _ = envelope(world)
    model_hash = world.put(model)
    reader = g.CompletedCampaignOriginal(
        tmp_path / "segment",
        population_scope=b.SYNTHETIC,
        catalog=world.catalog,
        rules=world.rules,
        gate=world.gate,
        control_adapters={},
        scratch_factory=lambda: (
            tmp_path / ("complete_segment_" + world.nonce() + ".sqlite")
        ),
        max_validations=2,
        check=lambda: None,
    )
    snapshot = b.parse(io.read(tmp_path / "segment/snapshot.json"), operations.SNAPSHOT)
    member = {"exact_plan_sha256": b.digest(values[1])}
    original = g.ScientificOriginals(
        world.records,
        world.gate,
        member_source=lambda row: None,
        calibration_source=lambda row: None,
        campaign_source=lambda row: reader,
        publication_source=lambda row: None,
        check=lambda: None,
    )
    row = {"reason": "CAMPAIGN_ALREADY_COMPLETE", "envelope_sha256": model_hash}
    proofs = [
        {"record_kind": "SEGMENT_CLOSURE", "sha256": snapshot["segment_closure_sha256"]}
    ]
    original.skip(row, {"condition": "CONTINUATION_CAPACITY"}, member, None, proofs)
    with pytest.raises(c.Stage12Error, match="SKIP_PROOF"):
        original.skip(
            row,
            {"condition": "CONTINUATION_CAPACITY"},
            member,
            None,
            [{"record_kind": "SEGMENT_CLOSURE", "sha256": H}],
        )
    with pytest.raises(c.Stage12Error, match="REOPEN_BUDGET"):
        reader.validate()


def test_shared_generated_record_is_charged_and_reopened_even_when_unused(tmp_path):
    world = World(tmp_path)
    ledger, model, selected = setup_ledger(world)
    config, row = bind_first(world, ledger, selected)
    ledger.begin(config, b.digest(row))
    raw = b.canonical({"version": "SYNTHETIC_TEST_ONLY_EXTRA_EVIDENCE", "value": 1})
    digest = b.sha(raw).hex()
    path = world.records.root / (digest + ".json")
    ledger.reserve_record(path, digest, size=len(raw))
    io.write(path, raw)
    ledger.finish(roots=[tmp_path / "no_output"], max_entries=10)
    terminal = ledger.terminals[1]
    assert terminal["generated_records"] == [{"path": str(path), "sha256": digest}]
    assert terminal["observed_inodes"] == 1
    assert ledger.accounting()["reserved_bytes"] == model["physical_peak_bound_bytes"]
    path.write_bytes(raw.replace(b'"value":1', b'"value":2'))
    with pytest.raises(c.Stage12Error, match="EVIDENCE_CHANGED"):
        ledger.reopen()
