"""LP-1 invented authority only. No project/institutional permission fixtures."""

from pathlib import Path
import socket
import subprocess
from types import SimpleNamespace

import pytest
from stage12_b2_synthetic import World, H
from test_stage12_b2_runtime import configuration, pin
from safe_geocoding_pipeline.preprocessing import stage12_development_cli as cli
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_b2_local_preparation as local,
    s12_b2_runtime as runtime,
    s12_b2_contract as b,
    s12_storage as io,
    s12_transport as transport,
    s12_retrieval_contract as c,
)


def lp1_configuration(w, phase="plan-calibration", *, mutate=None):
    config, gate, grants = configuration(w, phase=phase)
    r = config["runtime"]
    r.update(
        version=local.RUNTIME_VERSION,
        local_preparation_authority_sha256=H,
        local_preparation_current_path=str(w.root / "local_current.json"),
    )
    for name in local.SERVICE_FIELDS:
        r[name] = None
    roots = {}
    for stage in ("stage06", "stage08", "stage09", "stage11"):
        config[stage + "_root"] = str(w.root / stage)
        roots[stage] = {
            "path": config[stage + "_root"],
            "manifest_sha256": w.catalog.binding["manifest_sha256"]
            if stage == "stage11"
            else H,
        }
    config["local_accepted_roots"] = roots
    config["local_workload_sha256"] = H
    if phase in ("build-workload", "offline-preflight"):
        core = w.records.get(
            w.records.get(w.window_hash, "window_plan")["calibration_plan_sha256"],
            "calibration_plan",
        )
        core["capability_evidence_sha256"] = config["capability_evidence_sha256"]
        config["calibration_plan_sha256"] = w.put(core)
    output = w.root / ("output_" + phase)
    scratch = w.root / ("scratch_" + phase + ".sqlite")
    work = {
        "schema_version": "stage12_local_preparation_workload_b2_v1",
        "phase": local.PHASES[phase],
        "input_binding_sha256": config["input_binding_sha256"],
        "parameters_sha256": local.workload_parameters_hash(config),
        "output_path": str(output),
        "scratch_path": str(scratch),
        "service_transfer_authority": "NOT_GRANTED",
        "scientific_publication": "NOT_GRANTED",
    }
    config["local_workload_sha256"] = w.put(work)
    a = {
        "schema_version": local.DESCRIPTOR,
        "scope": "DEVELOPMENT_LOCAL_PREPARATION",
        "population_scope": b.SYNTHETIC,
        **{k: H for k in local.REFERENCES},
        "configuration_scope_sha256": local.scope_hash(config),
        "source_inventory_sha256": b.digest(r["source_files"]),
        "stage11_input_binding_sha256": config["input_binding_sha256"],
        "workload_sha256": config["local_workload_sha256"],
        "phase": local.PHASES[phase],
        "accepted_roots": roots,
        "output_parent": r["output_parent"],
        "scratch_parent": r["scratch_parent"],
        "bounds": {k: r[k] for k in local.BOUNDS},
        "valid_from": "2025-01-01T00:00:00.000000Z",
        "valid_until": "2027-01-01T00:00:00.000000Z",
        "network": "DENIED",
        "dns": "DENIED",
        "subprocess": "DENIED",
        "credential_provider": "DENIED",
        "service_transfer_authority": "NOT_GRANTED",
        "scientific_publication": "NOT_GRANTED",
    }
    a["scientific_decision_sha256"] = gate.scientific_hash
    a["denial_policy_sha256"] = w.put(local.ASSET["denial_policy"])
    if mutate:
        mutate(a)
    r["local_preparation_authority_sha256"] = w.put(a)
    current = {
        "schema_version": "stage12_local_preparation_current_b2_v1",
        "authority_sha256": r["local_preparation_authority_sha256"],
        "state": "CURRENT",
        "valid_from": "2025-01-01T00:00:00.000000Z",
        "valid_until": "2027-01-01T00:00:00.000000Z",
        "evidence_sha256": H,
    }
    io.write(Path(r["local_preparation_current_path"]), b.canonical(current))
    grants.require("local_preparation", r["local_preparation_authority_sha256"], a)
    grants.require("local_preparation_current", b.digest(current), current)
    decision = w.records.get(gate.scientific_hash, "scientific_decision")
    grants.require("scientific_decision", gate.scientific_hash, decision)
    grants.require("protected_input", b.digest(w.catalog.binding), w.catalog.binding)
    cap = io.metadata(w.records.raw(config["capability_evidence_sha256"]))
    grants.require("supported_size", config["capability_evidence_sha256"], cap)
    grants.require(
        "calibration_depths",
        H,
        {"C": 5, "T": 12, "supported": 40, "binding": w.catalog.binding},
    )
    pin(w, config, grants)
    return config, output, scratch, a


def make_port(w, config):
    return runtime.RuntimePort(
        config,
        _test={
            "clock": w.clock,
            "key_provider": lambda: pytest.fail(
                "credential provider must not be called"
            ),
            "send": lambda *_a, **_k: pytest.fail("transport must not be called"),
        },
    )


def close_invalid(port):
    try:
        port.close()
    except c.Stage12Error:
        pass
    assert port._closed and port.offline_guard.closed


def test_local_selection_has_no_service_permission_or_window(tmp_path):
    w = World(tmp_path, count=4)
    config, out, scratch, _ = lp1_configuration(w)
    p = make_port(w, config)
    result = cli.execute("plan-calibration", cli.Session(p, config, out, scratch, H))
    assert result["scientific_N_selected"] is False
    assert (
        w.records.get(result["calibration_plan_sha256"], "calibration_plan")["C"] == 5
    )
    assert p._closed and p.offline_guard.closed
    assert all(config["runtime"][k] is None for k in local.SERVICE_FIELDS)


@pytest.mark.parametrize(
    "phase", ["prepare-bootstrap", "build-workload", "offline-preflight"]
)
def test_local_metadata_phases_are_finite_and_not_service_admission(tmp_path, phase):
    w = World(tmp_path, count=4)
    config, out, scratch, _ = lp1_configuration(w, phase)
    p = make_port(w, config)
    result = cli.execute(phase, cli.Session(p, config, out, scratch, H))
    assert (
        result["service_transfer_authority"]
        == result["scientific_publication"]
        == "NOT_GRANTED"
    )
    if phase != "prepare-bootstrap":
        assert (
            len(result["inventories"]) == 8
        )  # C=5 fixture: full + 2 tail + 5 paired/repeat
        assert all(x["rows"] == 4 for x in result["inventories"])
        assert result["ready_for_service"] is False
    assert p._closed


@pytest.mark.parametrize(
    "change",
    [
        lambda a: a.update(local_source_use_sha256=None),
        lambda a: a.update(local_controller_scope_sha256=None),
        lambda a: a.update(controlled_location_scope_sha256=None),
        lambda a: a.update(service_transfer_authority="GRANTED"),
        lambda a: a.update(network="ALLOWED"),
        lambda a: a.update(phase="BUILD_CATALOG"),
        lambda a: a.update(valid_until="2025-01-01T00:00:00.000000Z"),
        lambda a: a.update(workload_sha256=H),
        lambda a: a.update(unexpected=True),
        lambda a: a["bounds"].update(phase_generation_max_files=True),
    ],
)
def test_local_missing_or_wrong_authority_fails_before_reader(tmp_path, change):
    w = World(tmp_path)
    config, out, scratch, _ = lp1_configuration(w, mutate=change)
    p = make_port(w, config)
    try:
        with pytest.raises(c.Stage12Error):
            p.gate.check()
    finally:
        close_invalid(p)


@pytest.mark.parametrize(
    "phase",
    [
        "run-campaign",
        "run-direct-n",
        "publish",
        "reopen",
        "preflight",
        "close-campaign",
        "close-window",
        "evaluate-calibration",
    ],
)
def test_local_runtime_rejects_every_service_or_scientific_phase(tmp_path, phase):
    w = World(tmp_path)
    config, *_ = lp1_configuration(w)
    config["runtime"]["phase"] = phase
    with pytest.raises(c.Stage12Error, match="LP1_LOCAL_ONLY"):
        make_port(w, config)


@pytest.mark.parametrize(
    "purpose",
    [
        "dispatch",
        "emission",
        "segment_open",
        "publication",
        "permission_current",
        "positive_importer_lineage",
        "calibration_selection",
        "register_closed_window",
    ],
)
def test_even_registry_grant_cannot_extend_local_authority(tmp_path, purpose):
    w = World(tmp_path)
    config, *_ = lp1_configuration(w)
    p = make_port(w, config)
    try:
        with pytest.raises(c.Stage12Error, match="LP1_SERVICE_AUTHORITY_DENIED"):
            p.authority.require(purpose, H, {})
        with pytest.raises(c.Stage12Error):
            p.gate.before_dispatch()
        with pytest.raises(c.Stage12Error):
            p.runtime_key()
    finally:
        p.close()


def test_real_denial_is_installed_before_catalog_and_through_cleanup(tmp_path):
    w = World(tmp_path)
    config, *_ = lp1_configuration(w)
    p = make_port(w, config)
    try:
        for operation in (
            lambda: socket.socket(),
            lambda: socket.getaddrinfo("invalid.example", 80),
            lambda: subprocess.Popen(["must-not-run"]),
            lambda: transport.Secret.runtime(),
            lambda: transport.Secret.private_file("/unopened/not-a-key"),
        ):
            with pytest.raises(c.Stage12Error):
                operation()
        p.gate.check()
        p._stack.callback(lambda: transport.Secret.runtime())
        with pytest.raises(c.Stage12Error, match="LP1_CREDENTIAL_PROVIDER_DENIED"):
            p.close()
        assert p._closed and p.offline_guard.closed
    finally:
        close_invalid(p)


@pytest.mark.parametrize(
    "mutation", ["revoked", "source", "workload", "grant", "denial"]
)
def test_local_changed_gate_evidence_fails(tmp_path, mutation):
    w = World(tmp_path)
    config, *_ = lp1_configuration(w)
    p = make_port(w, config)
    p.gate.check()
    if mutation == "revoked":
        path = Path(config["runtime"]["local_preparation_current_path"])
        x = io.metadata(path.read_bytes())
        x["state"] = "REVOKED"
        path.write_bytes(b.canonical(x))
    elif mutation == "source":
        (w.root / config["runtime"]["source_files"][0]["path"]).write_bytes(
            b"changed source"
        )
    elif mutation == "workload":
        (w.records.root / (config["local_workload_sha256"] + ".json")).write_bytes(
            b"changed"
        )
    elif mutation == "grant":
        (
            w.records.root / (config["runtime"]["authority_sha256"] + ".json")
        ).write_bytes(b"changed")
    else:
        p.offline_guard.close()
    try:
        with pytest.raises(c.Stage12Error):
            p.gate.check()
    finally:
        close_invalid(p)


def test_local_output_paths_are_exact_not_only_parent_scoped(tmp_path):
    w = World(tmp_path)
    config, out, scratch, _ = lp1_configuration(w)
    p = make_port(w, config)
    with pytest.raises(c.Stage12Error, match="LP1_WORKLOAD_SCOPE"):
        cli.execute(
            "plan-calibration",
            cli.Session(p, config, out.with_name("wrong"), scratch, H),
        )
    assert not scratch.exists() and p._closed


def test_lineage_authority_is_only_the_current_exact_producer_row(tmp_path):
    w = World(tmp_path)
    config, *_ = lp1_configuration(w, phase="build-catalog")
    p = make_port(w, config)
    row = {"origin_sha256": H, "query_context_id": H, "channels": iter(())}
    projection = SimpleNamespace(rows=lambda: iter([row]))
    try:
        with pytest.raises(c.Stage12Error, match="LP1_LINEAGE_SCOPE"):
            p.authority.require("lineage_context", H, {**row, "channels": []})
        with local.lineage_scope(p, projection):
            for actual in projection.rows():
                p.authority.require("lineage_context", H, {**actual, "channels": []})
                with pytest.raises(c.Stage12Error):
                    p.authority.require("lineage_context", H, {"channels": []})
        assert p._local_context is None
    finally:
        p.close()


def test_generated_entry_bound_counts_directories_and_files(tmp_path):
    w = World(tmp_path)
    config, out, scratch, a = lp1_configuration(w)
    p = make_port(w, config)
    try:
        p.bind_session("plan-calibration", config, out, scratch, H)
        io.reserve(out)
        io.reserve(out / "nested")
        io.write(out / "nested/file", b"x")
        actual = p.reconcile_generation()
        assert actual["entries"] >= 4  # temporary root + output + nested + file
        p.settings["phase_generation_max_files"] = actual["entries"] - 1
        with pytest.raises(c.Stage12Error, match="B2_RUNTIME_GENERATION_BOUND"):
            p.reconcile_generation()
    finally:
        close_invalid(p)


def test_manifest_constants_bind_the_actual_accepted_readers():
    from safe_geocoding_pipeline.preprocessing.stages import s10_query_input as accepted
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_catalog as catalog

    assert local.accepted_manifest_hashes() == {
        "stage06": accepted.STAGE06_MANIFEST,
        "stage08": accepted.accepted8.STAGE08_MANIFEST_SHA256,
        "stage09": accepted.STAGE09_MANIFEST,
        "stage11": catalog.ACCEPTED["manifest_sha256"],
    }


def test_phase_executable_closure_rejects_each_missing_critical_module():
    complete = [{"path": path, "sha256": H} for path in local.required_source_paths()]
    local.validate_source_closure(complete)
    for omitted in local.required_source_paths():
        with pytest.raises(c.Stage12Error, match="LP1_EXECUTABLE_BINDING"):
            local.validate_source_closure(
                [item for item in complete if item["path"] != omitted]
            )


def test_missing_capability_cannot_seal_local_selections(tmp_path):
    w = World(tmp_path)
    config, out, scratch, _ = lp1_configuration(w)
    p = make_port(w, config)
    path = w.records.root / (config["capability_evidence_sha256"] + ".json")
    path.unlink()
    with pytest.raises(c.Stage12Error):
        cli.execute("plan-calibration", cli.Session(p, config, out, scratch, H))
    assert not out.exists()
    assert p._closed
