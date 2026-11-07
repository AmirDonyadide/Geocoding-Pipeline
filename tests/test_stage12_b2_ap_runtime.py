"""Actual graph/Authority/SP gate/AP CLI composition; all issuers are synthetic.

Only the clock, key, transport and kernel observations use RuntimePort's
explicit test port. The controller clock publishes actual outcome-bound local
postflight records and exact grants through the normal private file interface.
"""

from copy import deepcopy
import json
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from stage12_b2_synthetic import World, H, KEY
from stage12_b2_acceptance_runtime_fixture import prepare_model, bind_member_and_slot
from test_stage12_b2_sampling_composition import ap_inputs
from test_stage12_b2_evidence import gate_fixture
from test_stage12_b2_runtime import configuration, Grants, pin
from test_stage12_public_operations_v2 import offline  # noqa: F401
from test_stage12_public_sampling_integration import RealClock
from safe_geocoding_pipeline.preprocessing import stage12_development_cli as cli
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_b2_contract as b,
    s12_b2_runtime as runtime,
    s12_b2_sampling_contract as a,
    s12_b2_planning as planning,
    s12_b2_pipeline as pipeline,
    s12_b2_recovery as recovery,
    s12_b2_audit as audit,
    s12_wf_ap2_assurance as assurance,
    s12_transport as transport,
    s12_retrieval_contract as c,
    s12_storage as io,
)


class Issuer(Grants):
    def __init__(self, records):
        super().__init__()
        self.records = records

    def supported_size(self, digest):
        record = io.metadata(self.records.raw(digest))
        self.require("supported_size", digest, record)
        assert record["complete_required_matrix"] is True
        return record["supported_size"]


class ControllerClock(RealClock):
    def __init__(self):
        super().__init__()
        self.controller = None
        self.controller_ready = lambda: False
        self._controller_lock = threading.Lock()
        self.controller_done = False

    def now_ns(self):
        if (
            self.controller is not None
            and not self.controller_done
            and self.controller_ready()
            and self._controller_lock.acquire(blocking=False)
        ):
            try:
                self.controller_done = True
                result, errors = [], []

                def external_controller():
                    try:
                        result.append(bool(self.controller()))
                    except BaseException as error:
                        errors.append(error)

                thread = threading.Thread(
                    target=external_controller, name="SYNTHETIC_EXTERNAL_CONTROLLER"
                )
                thread.start()
                thread.join(timeout=2)
                assert not thread.is_alive(), (
                    "bounded synthetic controller did not finish"
                )
                if errors:
                    raise errors[0]
                self.controller_done = result[0]
            finally:
                self._controller_lock.release()
        return super().now_ns()


def exact_grants(world, config, issuer):
    directory = Path(config["runtime"]["source_root"]) / (
        "grants_" + config["runtime"]["phase"]
    )
    for subject in issuer.items:
        path = directory / (b.digest(subject) + ".json")
        value = {
            "version": "stage12_runtime_exact_grant_v1",
            "decision": "ISSUED",
            "subject": subject,
            "delegation_sha256": H,
            "review_record_sha256": H,
        }
        if not path.exists():
            io.write(path, b.canonical(value))


def actual_sp_world(tmp_path):
    world = World(tmp_path, count=2)
    issuer = Issuer(world.records)
    world.gate.authority = issuer
    old_window = world.records.get(world.window_hash, "window_plan")
    core = world.records.get(old_window["calibration_plan_sha256"], "calibration_plan")
    capability = world.put(
        {
            "version": "stage12_reviewed_size_capability_v1",
            "supported_size": 40,
            "complete_required_matrix": True,
            "source_evidence_sha256": H,
            "review_sha256": H,
        }
    )
    core["capability_evidence_sha256"] = capability
    core_hash = world.put(core)
    schedule = world.records.get(
        old_window["planned_segment_plan_sha256"], "window_segment_plan"
    )
    schedule["calibration_plan_sha256"] = core_hash
    old_window.update(
        calibration_plan_sha256=core_hash,
        planned_segment_plan_sha256=world.put(schedule),
    )
    world.window_hash = world.put(old_window)
    gate, _, _, _ = gate_fixture(world)
    world.gate = gate
    world.window_hash = gate.window_hash
    world.selection_hash = planning.bind_window(
        world.records,
        core_hash,
        world.window_hash,
        owner=lambda: None,
        secret_guard=lambda raw: None,
    )
    gate.selection_hash = world.selection_hash
    world._runtime_constructor_gate = gate
    return world, issuer


def composed(tmp_path):
    world, issuer = actual_sp_world(tmp_path)
    values = ap_inputs(world)
    world.clock = ControllerClock()
    world.gate.clock = world.clock
    issuer.clock = world.clock
    profile, plan, start, science, admission, rows = values
    bound = issuer.sampling_bound(profile, start)
    config, _, _ = configuration(
        world,
        phase="run-campaign",
        mode="EXACT_AUTHORIZED_DISPATCH",
        gate=world.gate,
        grants=issuer,
    )
    output, scratch = (
        world.root / "runtime_ap_segment",
        world.root / "runtime_ap_preflight.sqlite",
    )
    config["command_paths"] = {"output_path": str(output), "scratch_path": str(scratch)}
    config["runtime"].update(
        phase_duration_ms=180000,
        phase_memory_bytes=profile["resources"]["job_memory_bytes"],
        phase_generation_max_files=100000,
        postflight_bundle_path=str(world.root / "runtime_ap_postflight.json"),
    )
    config["runtime"]["transport"] = {
        "origin": "https://geocode.safe-frankfurt.de",
        "approved_ip": "192.0.2.1",
        "configuration_evidence_sha256": H,
        "target_limit": 65536,
        "header_limit": 65536,
    }
    profile["transport_profile_sha256"] = world.put(config["runtime"]["transport"])
    control_body = b.canonical({"synthetic_index": "test"})
    control = {
        "recipe_id": 1,
        "recipe_sha256": H,
        "implementation_contract_sha256": H,
        "transport_profile_sha256": profile["transport_profile_sha256"],
        "purpose": "HEALTH_CHECK",
        "max_http_attempts_per_invocation": 5,
        "max_duration_ms": 10000,
    }
    plan["control_recipes"] = [control]
    rows.append(
        {
            "work_id": 3,
            "block_id": 1,
            "kind": "SERVICE_CONTROL",
            "query_semantic_id": None,
            "result_limit": None,
            "repetition": None,
            "recipe_id": 1,
            "retry_spacing_key": H,
        }
    )
    plan["budgets"].update(required_control_observations=1, control_http_attempts=5)
    plan["blocks"][0]["last_work_id"] = len(rows)
    plan["work_manifest_sha256"] = a.manifest_digest(rows)
    control_hash = world.put(
        {
            "version": "stage12_runtime_exact_control_v1",
            "recipe_sha256": H,
            "implementation_contract_sha256": H,
            "target_ascii": "/synthetic-control-only",
            "accepted_payload_sha256": [b.sha(control_body).hex()],
        }
    )
    model, selected = prepare_model(world, values, config)
    config["runtime"].update(
        phase_disk_capacity_bytes=plan["budgets"]["storage_bytes"],
        phase_generation_bound_bytes=model["slots"][0]["max_generated_bytes"],
        phase_generation_max_files=model["slots"][0]["max_generated_inodes"],
    )
    actual_inventory = runtime.RuntimePort._actual_runtime_inventory(
        SimpleNamespace(population_scope=b.SYNTHETIC, settings=config["runtime"]),
        successor=True,
    )
    world.runtime = actual_inventory
    work_path = world.root / "runtime_ap_work.jsonl"
    raw_work = b"".join(b.canonical(row) for row in rows)
    io.write(work_path, raw_work)
    config["runtime"]["campaign"] = {
        "profile_sha256": H,
        "plan_sha256": H,
        "start_sha256": H,
        "scientific_start_sha256": H,
        "admission_sha256": H,
        "work_path": str(work_path),
        "work_file_sha256": b.sha(raw_work).hex(),
        "segment_path": str(output),
        "predecessor_path": None,
        "runtime_inventory_sha256": world.put(actual_inventory),
        "pause_after_ms": 10000,
        "control_adapters": {"1": control_hash},
    }
    config.update(
        writer_release_authority_sha256=world.releases[admission["segment_nonce"]],
        campaign_closure_sha256=None,
        external_sort_memory_bytes=64 * 2**20,
        N_decision_sha256=None,
        window_closure_sha256=None,
        calibration_inventory=None,
    )
    bound.update(
        runtime_inventory_sha256=b.digest(actual_inventory),
        invocation_graph_sha256=b.digest(model),
        configuration_scope_sha256=assurance.configuration_scope(config, plan=plan),
    )
    issuer.configuration_scope_sha256 = bound["configuration_scope_sha256"]
    issuer.sampling_bound = lambda *_: deepcopy(bound)
    profile["sampling_runtime_bound_sha256"] = world.put(bound)
    plan["operations_profile_sha256"] = b.digest(profile)
    science.update(
        runtime_inventory_sha256=b.digest(actual_inventory),
        operations_policy_sha256=b.digest(profile),
        workload_sha256=b.digest(plan),
    )
    start.update(
        runtime_inventory_sha256=b.digest(actual_inventory),
        profile_sha256=b.digest(profile),
        plan_sha256=b.digest(plan),
        scientific_campaign_start_sha256=b.digest(science),
    )
    bootstrap = pipeline.prepare_bootstrap(
        world.root / "runtime_ap_bootstrap",
        records=world.records,
        raw_factory=lambda: (
            lambda: world.records.raw(admission["preflight_observation_sha256"]),
        ),
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
    admission.update(
        campaign_start_sha256=b.digest(science),
        operations_campaign_sha256=b.digest(start),
        bootstrap_acquisition_sha256=bootstrap,
    )
    for key, value in (
        ("profile_sha256", profile),
        ("plan_sha256", plan),
        ("start_sha256", start),
        ("scientific_start_sha256", science),
        ("admission_sha256", admission),
    ):
        config["runtime"]["campaign"][key] = world.put(value)
    ledger, member, binding, resource_grants = bind_member_and_slot(
        world, values, config, model, selected
    )
    for purpose, digest, context in resource_grants:
        issuer.require(purpose, digest, context)
    a.verify_authorities(profile, plan, start, world.gate)
    world.gate.validate_campaign(start, plan, admission)
    world.gate.validate_workload(
        world.catalog,
        profile,
        plan,
        lambda: iter(rows),
        admission,
        world.root / "runtime_grant_selection.sqlite",
    )
    world.gate.admit(
        admission["preflight_observation_sha256"], admission["segment_nonce"]
    )
    world.gate.before_dispatch()
    context = {"start": start, "block": plan["blocks"][0]}
    for purpose in ("segment_open", "writer_exclusion"):
        issuer.require(purpose, H, context)
    issuer.require(
        "runtime_preflight", H, {"profile": profile, "plan": plan, "start": start}
    )
    issuer.require("retrieval_limit", start["retrieval_policy_id"], plan)
    issuer.require(
        "protected_input", b.digest(world.catalog.binding), world.catalog.binding
    )
    issuer.require(
        "response_rules",
        config["runtime"]["response_rules_sha256"],
        {"interpretation": start["response_interpretation_sha256"]},
    )
    issuer.require(
        "transport", profile["transport_profile_sha256"], config["runtime"]["transport"]
    )
    pin(world, config, issuer)
    exact_grants(world, config, issuer)
    calls = []

    def send(target, _profile, _key, _operations, *, hooks):
        for row in rows:
            if row["kind"] == "SERVICE_CONTROL":
                if target == b"/synthetic-control-only":
                    calls.append(row["work_id"])
                    hooks.started(world.clock.now_ns())
                    hooks.emit(lambda: None, lambda: None)
                    capture = transport.Capture(
                        "VALIDATION_REQUIRED",
                        "OK",
                        200,
                        "application/json",
                        "absent",
                        None,
                        control_body,
                        len(control_body),
                        1,
                    )
                    hooks.completed(capture)
                    return capture
                continue
            candidate = c.materialize(
                world.catalog.core(row["query_semantic_id"]),
                bytes.fromhex(row["query_semantic_id"]),
                c.policy(row["result_limit"]),
                target_limit=65536,
            )[0]
            if candidate == target:
                calls.append(row["work_id"])
                return world.dispatch(row, target, hooks)
        raise AssertionError("synthetic transport received an unselected target")

    port = runtime.RuntimePort(
        config,
        _test={
            "clock": world.clock,
            "key_provider": lambda: transport.Secret(KEY),
            "send": send,
            "enforcement_facts": issuer.enforcement_facts,
        },
    )

    controller_state = {"postflight": False}

    def publish_controller():
        if controller_state["postflight"]:
            if not (output / "snapshot.json").exists():
                return False
            snapshot = a.parse(io.read(output / "snapshot.json"), a.SNAPSHOT)
            world.gate.require(
                "prior_segment_closure", snapshot["segment_closure_sha256"], snapshot
            )
            exact_grants(world, config, issuer)
            return True
        if not (output / "remaining_work_ledger.json").exists():
            return False
        try:
            measured = a.parse(
                io.read(output / "measurement_report.json"), a.MEASUREMENT
            )
            ledger_rows = json.loads(io.read(output / "work_ledger.json"))
            json.loads(io.read(output / "remaining_work_ledger.json"))
        except (c.Stage12Error, ValueError, OSError):
            return False
        last_response = max(
            io.metadata(
                io.read(
                    output
                    / "attempts"
                    / f"{row['work_id']:020d}_{row['charged_ordinals'][-1]:02d}"
                    / "transport.json"
                )
            )["finished_utc"]
            for row in ledger_rows
        )
        info = {
            "scientific_start_sha256": b.digest(science),
            "admission": admission,
            "measurement_report_sha256": b.digest(measured),
            "attempt_inventory_sha256": measured["attempt_inventory_sha256"],
            "controller_reconciliation_sha256": b.sha(
                io.read(output / "work_ledger.json")
            ).hex(),
            "last_response_utc": last_response,
        }
        record_list = []
        closure_hash = None
        for i, raw in enumerate(world._close_records(info)):
            path = world.root / ("synthetic_controller_record_" + str(i) + ".json")
            io.write(path, raw)
            record_list.append(
                {"path": str(path), "sha256": b.sha(raw).hex(), "bytes": len(raw)}
            )
            world.records.put(raw, owner=lambda: None, secret_guard=lambda raw: None)
            issuer.require(
                "administrative_record", b.sha(raw).hex(), {"bytes": len(raw)}
            )
            if (
                raw.startswith(b"{")
                and io.metadata(raw).get("schema_version")
                == "stage12_segment_closure_b2_v1"
            ):
                closure_hash = b.sha(raw).hex()
        assert closure_hash is not None
        world.gate.segment_closure(
            closure_hash,
            start_hash=b.digest(science),
            attempt_inventory=info["attempt_inventory_sha256"],
            controller_reconciliation=info["controller_reconciliation_sha256"],
            resource_report=info["measurement_report_sha256"],
            last_response_utc=last_response,
            predecessor=None,
        )
        bundle = {
            "version": "stage12_runtime_postflight_bundle_v1",
            "close_info_sha256": b.digest(info),
            "records": record_list,
            "authority_sha256": H,
        }
        issuer.require("postflight_bundle", H, bundle)
        exact_grants(world, config, issuer)
        io.write(Path(config["runtime"]["postflight_bundle_path"]), b.canonical(bundle))
        controller_state["postflight"] = True
        return False

    world.clock.controller = publish_controller
    world.clock.controller_ready = lambda: (
        output
        / (
            "snapshot.json"
            if controller_state["postflight"]
            else "remaining_work_ledger.json"
        )
    ).exists()
    return world, values, config, port, calls, ledger, binding


def test_actual_graph_bound_ap_cli_capture_close_and_original_reopen(tmp_path):
    world, values, config, port, calls, ledger, binding = composed(tmp_path)
    result = cli.execute(
        "run-campaign",
        cli.Session(
            port,
            config,
            Path(config["command_paths"]["output_path"]),
            Path(config["command_paths"]["scratch_path"]),
            H,
        ),
    )
    assert result["report_complete"] and result["sampling_segments"][-1]["complete"]
    assert calls == [1, 2, 3]
    assert result["counts"]["control_attempt_starts"]["value"] == 1
    assert port.authority._runtime_inventory_checks >= 3
    assert port.authority._enforcement_checks >= 2 * len(calls)
    assert world.clock.controller_done
    root = Path(config["command_paths"]["output_path"])
    assert (root / "_SEGMENT_SEALED").read_bytes() == b""
    assert port.resource_ledger.finished
    profile, plan, start, _, _, rows = values
    reopened = recovery.reopen(
        root,
        start,
        profile,
        plan,
        works=lambda: iter(rows),
        verify_receipt=lambda work, event: (
            audit.reopen(
                root / "attempts" / f"{work['work_id']:020d}_{event['attempt']:02d}",
                **world.rules.kwargs(),
            )[0]
            if work["kind"] == "DATA"
            else audit.report_control(
                root / "attempts" / f"{work['work_id']:020d}_{event['attempt']:02d}",
                plan["control_recipes"][0],
                port.control_adapters[1],
            )
        ),
        scratch=world.root / "actual_independent.sqlite",
        authority=world.gate,
    )
    assert reopened["snapshot"]["sampling"]["complete"]


@pytest.mark.parametrize(
    "failure",
    ["missing_m2_facts", "changed_source", "changed_graph", "wrong_command_paths"],
)
def test_composed_guards_reject_before_workfile_catalog_or_send(
    tmp_path, monkeypatch, failure
):
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_catalog as catalogs

    world, values, config, port, calls, ledger, binding = composed(tmp_path)
    reads = {"workfile": 0, "catalog": 0}
    old_work, old_catalog = runtime.WorkFile.__init__, catalogs.Catalog.__init__

    def work(self, *args, **kwargs):
        reads["workfile"] += 1
        return old_work(self, *args, **kwargs)

    def catalog(self, *args, **kwargs):
        reads["catalog"] += 1
        return old_catalog(self, *args, **kwargs)

    monkeypatch.setattr(runtime.WorkFile, "__init__", work)
    monkeypatch.setattr(catalogs.Catalog, "__init__", catalog)
    output = Path(config["command_paths"]["output_path"])
    actual_output = output
    if failure == "missing_m2_facts":
        port._test["enforcement_facts"] = lambda _: {}
    elif failure == "changed_source":
        source = (
            Path(config["runtime"]["source_root"])
            / config["runtime"]["source_files"][0]["path"]
        )
        source.write_bytes(b"SYNTHETIC source mutation")
    elif failure == "changed_graph":
        (
            world.records.root
            / (config["runtime"]["resource_retention"]["model_sha256"] + ".json")
        ).write_bytes(b"SYNTHETIC graph mutation")
    else:
        actual_output = world.root / "unbound_output"
    with pytest.raises(c.Stage12Error):
        cli.execute(
            "run-campaign",
            cli.Session(
                port,
                config,
                actual_output,
                Path(config["command_paths"]["scratch_path"]),
                H,
            ),
        )
    assert reads == {"workfile": 0, "catalog": 0}
    assert calls == [] and port.resource_ledger is None
    assert not output.exists() and not actual_output.exists()
