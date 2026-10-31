"""Invented runtime records only: no institutional, operator or workload authority."""

from pathlib import Path
from types import SimpleNamespace
import os
import socket

import pytest
from stage12_b2_synthetic import World, H, KEY, offline as offline
from test_stage12_b2_evidence import gate_fixture
from safe_geocoding_pipeline.preprocessing import stage12_development_cli as cli
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_b2_runtime as r,
    s12_b2_contract as b,
    s12_b2_evidence as e,
    s12_b2_operations as o,
    s12_storage as io,
    s12_transport as transport,
    s12_retrieval_contract as c,
)


class Grants:
    def __init__(self):
        self.items = []

    def require(self, purpose, digest, context):
        if purpose == "permission_current":
            context = {"permission": context["permission"], "until": context["until"]}
        value = {
            "purpose": purpose,
            "evidence_sha256": digest,
            "context_sha256": b.digest(context),
        }
        if value not in self.items:
            self.items.append(value)


def configuration(
    w, phase="plan-calibration", *, gate=None, mode="OFFLINE_ONLY", grants=None
):
    gate = gate or getattr(w, "_runtime_constructor_gate", None) or gate_fixture(w)[0]
    w._runtime_constructor_gate = gate
    source = w.root / "invented_runtime_source.py"
    if not source.exists():
        io.write(source, b"# SYNTHETIC TEST ONLY runtime source identity\n")
    grant_dir = w.root / ("grants_" + phase)
    if not grant_dir.exists():
        io.reserve(grant_dir)
    revoke = w.root / ("permission_current_" + phase + ".json")
    if not revoke.exists():
        io.write(
            revoke,
            b.canonical(
                {
                    "version": "stage12_permission_current_v1",
                    "permission_sha256": gate.permission_hash,
                    "state": "CURRENT",
                    "valid_from": "2025-01-01T00:00:00.000000Z",
                    "valid_until": "2027-01-01T00:00:00.000000Z",
                    "evidence_sha256": H,
                }
            ),
        )
    state = w.root / ("window_state_" + phase + ".json")
    if not state.exists():
        io.write(
            state,
            b.canonical(
                {
                    "version": "stage12_window_runtime_state_v1",
                    "window_plan_sha256": gate.window_hash,
                    "state": "OPEN",
                    "evidence_sha256": H,
                }
            ),
        )
    capability = w.put(
        {
            "version": "stage12_reviewed_size_capability_v1",
            "supported_size": 40,
            "complete_required_matrix": True,
            "source_evidence_sha256": H,
            "review_sha256": H,
        }
    )
    rules = w.put(
        {
            "version": "stage12_runtime_response_rules_v1",
            "layers": ["address", "locality", "street"],
            "sources": ["synthetic"],
            "echo_by_mode": {
                "FULL_TEXT": {"size": "RESULT_LIMIT"},
                "STRUCTURED": {"size": "RESULT_LIMIT"},
            },
            "country_echo": {"DE": "DEU"},
            "interpretation_sha256": gate.interpretation_hash,
        }
    )
    settings = {
        "version": r.VERSION,
        "population_scope": b.SYNTHETIC,
        "mode": mode,
        "phase": phase,
        "records_root": str(w.records.root),
        "authority_sha256": H,
        "source_root": str(w.root),
        "source_files": [
            {"path": source.name, "sha256": b.sha(source.read_bytes()).hex()}
        ],
        "output_parent": str(w.root),
        "scratch_parent": str(w.root),
        "phase_duration_ms": 1000000,
        "phase_until": "2026-01-02T00:00:00.000000Z",
        "phase_memory_bytes": 2**31,
        "phase_disk_capacity_bytes": 64 * 2**20,
        "phase_generation_bound_bytes": 32 * 2**20,
        "phase_generation_max_files": 10000,
        "phase_generation_check_ms": 1000,
        "temporary_root": str(w.root / ("temporary_" + phase)),
        "resource_evidence_sha256": H,
        "scientific_decision_sha256": gate.scientific_hash,
        "permission_sha256": gate.permission_hash,
        "permission_current_path": str(revoke),
        "gate": None
        if phase in r.PREPARATION
        else {name: getattr(gate, name) for name in r._GATE_FIELDS},
        "window_state_path": str(state),
        "response_rules_sha256": rules,
        "campaign": None,
        "transport": None,
        "postflight_bundle_path": None,
        "administration_owner_sha256": H,
    }
    config = {
        "runtime_port_sha256": H,
        "runtime": settings,
        "input_binding_sha256": w.put(w.catalog.binding),
        "catalog_path": str(w.catalog.path),
        "catalog_file_sha256": w.catalog.file_sha256,
        "C": 5,
        "T": 12,
        "capability_evidence_sha256": capability,
        "depth_decision_sha256": H,
        "lineage_binding_sha256": H,
    }
    return config, gate, grants or Grants()


def pin(w, config, grants):
    runtime = config["runtime"]
    grants.require(
        "resources",
        H,
        {
            k: runtime[k]
            for k in (
                "phase_duration_ms",
                "phase_memory_bytes",
                "phase_disk_capacity_bytes",
                "phase_generation_bound_bytes",
                "phase_generation_max_files",
                "phase_generation_check_ms",
                "temporary_root",
                "output_parent",
                "scratch_parent",
            )
        },
    )
    grants.require(
        "administrative_writer",
        H,
        {"phase": runtime["phase"], "configuration_scope_sha256": r.scope_hash(config)},
    )
    root = {
        "version": r.AUTHORITY_VERSION,
        "scope_sha256": r.scope_hash(config),
        "population_scope": b.SYNTHETIC,
        "owner_decision_sha256": H,
        "delegation_sha256": H,
        "review_sha256": H,
        "valid_from": "2025-01-01T00:00:00.000000Z",
        "valid_until": "2027-01-01T00:00:00.000000Z",
        "phase_authority_sha256": H,
        "phase_names": [runtime["phase"]],
        "grants": grants.items,
        "grant_directory": str(w.root / ("grants_" + runtime["phase"])),
        "dynamic_purposes": ["dispatch", "nonsecret_record"],
    }
    runtime["authority_sha256"] = w.put(root)
    return config


def prep_grants(w, config, gate, grants):
    decision = w.records.get(gate.scientific_hash, "scientific_decision")
    grants.require("scientific_decision", gate.scientific_hash, decision)
    e.privacy(
        w.records,
        gate.permission_hash,
        now=w.clock.utc(),
        until=config["runtime"]["phase_until"],
        authority=grants,
        revocation=lambda *_: H,
    )
    grants.require("protected_input", b.digest(w.catalog.binding), w.catalog.binding)
    cap = io.metadata(w.records.raw(config["capability_evidence_sha256"]))
    grants.require("supported_size", config["capability_evidence_sha256"], cap)
    grants.require(
        "calibration_depths",
        H,
        {"C": 5, "T": 12, "supported": 40, "binding": w.catalog.binding},
    )


def port(w, config):
    return r.RuntimePort(
        config,
        _test={
            "clock": w.clock,
            "key_provider": lambda: transport.Secret(KEY),
            "send": lambda *a, **k: (_ for _ in ()).throw(
                AssertionError("no dispatch fixture")
            ),
        },
    )


def test_preparation_core_real_entrypoint_needs_no_future_window(tmp_path):
    w = World(tmp_path, count=4)
    config, gate, grants = configuration(w)
    prep_grants(w, config, gate, grants)
    pin(w, config, grants)
    runtime = port(w, config)
    assert isinstance(runtime.gate, r.PreparationGate)
    result = cli.execute(
        "plan-calibration",
        cli.Session(
            runtime, config, tmp_path / "unused_output", tmp_path / "selected.sqlite", H
        ),
    )
    core = w.records.get(result["calibration_plan_sha256"], "calibration_plan")
    assert (
        core["C"] == 5 and core["T"] == 12 and core["population_scope"] == b.SYNTHETIC
    )
    assert "window_plan_sha256" not in core and result["scientific_N_selected"] is False
    assert runtime._closed
    assert len(runtime.authority.pending_nonsecret) == 0


def test_preparation_missing_privacy_still_blocks_before_catalog(tmp_path, monkeypatch):
    w = World(tmp_path)
    config, gate, grants = configuration(w)
    prep_grants(w, config, gate, grants)
    permission = w.records.get(gate.permission_hash, "privacy_permission")
    permission["decision"] = "UNRESOLVED"
    config["runtime"]["permission_sha256"] = w.put(permission)
    pin(w, config, grants)
    runtime = port(w, config)
    monkeypatch.setattr(
        runtime, "_catalog_for_verify", lambda: pytest.fail("protected input accessed")
    )
    with pytest.raises(c.Stage12Error, match="PERMISSION_UNRESOLVED"):
        cli.execute(
            "plan-calibration",
            cli.Session(
                runtime, config, tmp_path / "output", tmp_path / "selection.sqlite", H
            ),
        )
    assert runtime._closed


def test_offline_provider_network_and_process_denied_and_cleanup(tmp_path):
    w = World(tmp_path)
    config, gate, grants = configuration(w)
    pin(w, config, grants)
    runtime = port(w, config)
    try:
        with pytest.raises(c.Stage12Error, match="PROVIDER_UNAUTHORIZED"):
            runtime.runtime_key()
        with pytest.raises(c.Stage12Error, match="OFFLINE_NETWORK_PROCESS_DENIED"):
            socket.socket()
        with pytest.raises(c.Stage12Error, match="OFFLINE_PROTECTED_BOUNDARY"):
            open(tmp_path / "pelias_api_key", "rb")
        with pytest.raises(c.Stage12Error, match="OFFLINE_NETWORK_PROCESS_DENIED"):
            os.system("false")
    finally:
        runtime.close()
    assert r._AUDIT_ACTIVE == 0


@pytest.mark.parametrize("change", ["scope", "grant", "record", "phase", "expiry"])
def test_exact_registry_failures(tmp_path, change):
    w = World(tmp_path)
    config, gate, grants = configuration(w)
    prep_grants(w, config, gate, grants)
    pin(w, config, grants)
    if change == "scope":
        config["C"] = 10
    if change == "record":
        (
            w.records.root / (config["runtime"]["authority_sha256"] + ".json")
        ).write_bytes(b"changed")
    if change == "expiry":
        w.clock.advance(400 * 86400 * 10**9)
    if change in ("scope", "record", "expiry"):
        with pytest.raises(c.Stage12Error):
            port(w, config)
        return
    runtime = port(w, config)
    try:
        with pytest.raises((c.Stage12Error, FileNotFoundError)):
            if change == "grant":
                runtime.authority.require("privacy_permission", H, {})
            else:
                runtime.authority.require(
                    "phase_run-campaign",
                    H,
                    {
                        "configuration_sha256": b.digest(config),
                        "population_scope": b.SYNTHETIC,
                    },
                )
    finally:
        runtime.close()


def test_installed_factory_rejects_test_population(tmp_path):
    w = World(tmp_path)
    config, _, grants = configuration(w)
    pin(w, config, grants)
    with pytest.raises(c.Stage12Error, match="B2_POPULATION_SCOPE"):
        r.create_port(config)


def workfile(w, count=None):
    values = w.inputs()
    rows = values[-1]
    path = w.root / "works.jsonl"
    raw = b"".join(b.canonical(row) for row in rows)
    io.write(path, raw)
    return r.WorkFile(path, b.sha(raw).hex(), values[1]), rows


def test_workfile_original_rows_and_exact_manifest(tmp_path):
    w = World(tmp_path, count=80)
    index, rows = workfile(w)
    assert (
        list(index.rows()) == rows
        and [index.row(i + 1) for i in range(len(rows))] == rows
    )
    assert (
        index.offsets.buffer_info()[1] * index.offsets.itemsize + len(index.hashes)
        == 80 * 40
    )
    index.verify()


@pytest.mark.parametrize(
    "change", ["content", "append", "truncate", "reorder", "symlink", "replace", "mode"]
)
def test_workfile_rejects_changed_originals(tmp_path, change):
    w = World(tmp_path, count=3)
    index, rows = workfile(w)
    p = index.path
    raw = p.read_bytes()
    if change == "content":
        p.write_bytes(raw.replace(b'"result_limit":5', b'"result_limit":3'))
    if change == "append":
        p.write_bytes(raw + b.canonical(rows[0]))
    if change == "truncate":
        p.write_bytes(raw[:-1])
    if change == "reorder":
        p.write_bytes(b"".join(b.canonical(x) for x in reversed(rows)))
    if change in ("symlink", "replace"):
        q = p.with_name("replacement")
        io.write(q, raw)
        p.unlink()
        if change == "symlink":
            p.symlink_to(q)
        else:
            q.rename(p)
    if change == "mode":
        p.chmod(0o644)
    with pytest.raises((c.Stage12Error, OSError)):
        index.verify()


def test_close_preserves_primary_and_cannot_turn_cleanup_failure_into_success(
    monkeypatch, tmp_path
):
    p = SimpleNamespace(
        close=lambda: (_ for _ in ()).throw(RuntimeError("cleanup fixture"))
    )
    session = cli.Session(p, {}, tmp_path / "out", tmp_path / "scratch", H)
    monkeypatch.setattr(
        cli,
        "_execute",
        lambda *_: (_ for _ in ()).throw(c.Stage12Error("PRIMARY_FIXTURE")),
    )
    with pytest.raises(c.Stage12Error, match="PRIMARY_FIXTURE"):
        cli.execute("preflight", session)
    monkeypatch.setattr(cli, "_execute", lambda *_: {"ok": True})
    with pytest.raises(RuntimeError, match="cleanup fixture"):
        cli.execute("preflight", session)


def test_deadline_source_mutation_and_no_credential_echo(tmp_path):
    w = World(tmp_path)
    config, _, grants = configuration(w)
    pin(w, config, grants)
    runtime = port(w, config)
    with pytest.raises(c.Stage12Error, match="SECRET_ECHO_DETECTED"):
        runtime.secret_guard(b'{"x-api-key":"test"}')
    runtime._key = transport.Secret(KEY)
    with pytest.raises(c.Stage12Error, match="SECRET_ECHO_DETECTED"):
        runtime.secret_guard(KEY)
    (tmp_path / "invented_runtime_source.py").write_bytes(b"changed")
    with pytest.raises(c.Stage12Error, match="INPUT_CHANGED"):
        runtime.close()
    assert runtime._closed and r._AUDIT_ACTIVE == 0


def test_window_closure_marker_blocks_future_dispatch_state(tmp_path):
    w = World(tmp_path)
    config, gate, grants = configuration(w, phase="close-window")
    grants.require(
        "register_closed_window", H, {"window_plan_sha256": gate.window_hash}
    )
    pin(w, config, grants)
    runtime = port(w, config)
    try:
        assert runtime.window_state(gate.window_hash)["state"] == "OPEN"
        runtime.register_closed_window(H)
        assert (
            runtime._record_generated_files == 1 and runtime._record_generated_bytes > 0
        )
        assert runtime.window_state(gate.window_hash) == {
            "state": "CLOSED",
            "evidence_sha256": H,
        }
        with pytest.raises(FileExistsError):
            runtime.register_closed_window(H)
    finally:
        runtime.close()


def test_control_adapter_exact_separation_and_payload_hash():
    recipe = {"recipe_sha256": H, "implementation_contract_sha256": H}
    value = {
        "version": "stage12_runtime_exact_control_v1",
        "recipe_sha256": H,
        "implementation_contract_sha256": H,
        "target_ascii": "/public-test",
        "accepted_payload_sha256": [b.sha(b"{}").hex()],
    }
    adapter = r.ExactControl(value, recipe)
    assert adapter.target(recipe) == b"/public-test"
    assert (
        io.metadata(adapter.validate(recipe, b"{}"))["service_state_verified"] is False
    )
    with pytest.raises(c.Stage12Error):
        adapter.validate(recipe, b'{"changed":1}')
    for target in ("//host/", "/x\r\ny", "/x y", "/x\x00"):
        with pytest.raises(c.Stage12Error):
            r.ExactControl({**value, "target_ascii": target}, recipe)


def campaign_port(w, phase, values, *, output, closure=None, publication=None):
    """Runtime adapters are real; external issuer/clock/service are invented here."""
    config, constructor_gate, grants = configuration(
        w,
        phase=phase,
        mode="EXACT_AUTHORIZED_DISPATCH" if phase in r.DISPATCH else "OFFLINE_ONLY",
    )
    profile, plan, start, science, admission, rows = values
    work_path = w.root / ("work_" + phase + ".jsonl")
    raw = b"".join(b.canonical(row) for row in rows)
    io.write(work_path, raw)
    inv = {
        "version": "stage12_development_runtime_inventory_v1",
        "population_scope": b.SYNTHETIC,
        "python_version": r.platform.python_version(),
        "platform": r.platform.system(),
        "source_inventory_sha256": b.digest(config["runtime"]["source_files"]),
        "continuous_service_state": "NOT_VERIFIED",
        "resource_sampling_is_service_monitoring": False,
        "scientific_identity_verified": False,
    }
    # Exact synthetic campaign identity must use the actual adapter inventory.
    assert b.digest(inv) == start["runtime_inventory_sha256"]
    config["runtime"]["phase_memory_bytes"] = profile["resources"]["job_memory_bytes"]
    config["runtime"]["phase_disk_capacity_bytes"] = plan["budgets"]["storage_bytes"]
    config["runtime"]["campaign"] = {
        "profile_sha256": w.put(profile),
        "plan_sha256": w.put(plan),
        "start_sha256": w.put(start),
        "scientific_start_sha256": w.put(science),
        "admission_sha256": w.put(admission),
        "work_path": str(work_path),
        "work_file_sha256": b.sha(raw).hex(),
        "segment_path": str(w.root / "runtime_segment"),
        "predecessor_path": None,
        "runtime_inventory_sha256": w.put(inv),
        "pause_after_ms": 900000,
        "control_adapters": {},
    }
    config["runtime"]["transport"] = {
        "origin": "https://geocode.safe-frankfurt.de",
        "approved_ip": "192.0.2.1",
        "configuration_evidence_sha256": H,
        "target_limit": 65536,
        "header_limit": 65536,
    }
    config["runtime"]["postflight_bundle_path"] = str(
        w.root / ("postflight_" + phase + ".json")
    )
    config.update(
        writer_release_authority_sha256=w.releases[admission["segment_nonce"]],
        campaign_closure_sha256=closure,
        external_sort_memory_bytes=64 * 1024 * 1024,
        N_decision_sha256=None,
        window_closure_sha256=None,
        calibration_inventory=None,
    )
    if publication:
        config.update(
            publication_path=str(publication[0]), manifest_sha256=publication[1]
        )
    grants.require("protected_input", b.digest(w.catalog.binding), w.catalog.binding)
    grants.require(
        "transport", profile["transport_profile_sha256"], config["runtime"]["transport"]
    )
    pin(w, config, grants)
    runtime = port(w, config)
    # Existing synthetic issuer fixture is explicitly separate from the real
    # privacy/registry tests above. Never installed by create_port.
    runtime.gate = w.gate
    runtime.notice = lambda: None  # explicit synthetic external-notice adapter
    original_postflight = runtime.postflight_records

    def postflight(info):
        record_list = []
        for i, raw in enumerate(w._close_records(info)):
            path = w.root / ("postflight_record_" + str(i) + ".json")
            io.write(path, raw)
            record_list.append(
                {"path": str(path), "sha256": b.sha(raw).hex(), "bytes": len(raw)}
            )
        bundle = {
            "version": "stage12_runtime_postflight_bundle_v1",
            "close_info_sha256": b.digest(info),
            "records": record_list,
            "authority_sha256": H,
        }
        io.write(Path(config["runtime"]["postflight_bundle_path"]), b.canonical(bundle))
        subject = {
            "purpose": "postflight_bundle",
            "evidence_sha256": H,
            "context_sha256": b.digest(bundle),
        }
        grant = {
            "version": "stage12_runtime_exact_grant_v1",
            "decision": "ISSUED",
            "subject": subject,
            "delegation_sha256": H,
            "review_record_sha256": H,
        }
        io.write(
            w.root / ("grants_" + phase) / (b.digest(subject) + ".json"),
            b.canonical(grant),
        )
        return original_postflight(info)

    runtime.postflight_records = postflight

    def send(target, profile, key, operations, *, hooks):
        row = next(
            row
            for row in rows
            if c.materialize(
                w.catalog.core(row["query_semantic_id"]),
                bytes.fromhex(row["query_semantic_id"]),
                c.policy(row["result_limit"]),
                target_limit=65536,
            )[0]
            == target
        )
        return w.dispatch(row, target, hooks)

    runtime._test["send"] = send
    return runtime, config


def test_runtime_entrypoints_capture_publish_reopen_exact_originals(
    tmp_path, monkeypatch
):
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_publication as pub

    w = World(tmp_path, count=2)
    config, _, _ = configuration(
        w, phase="run-campaign", mode="EXACT_AUTHORIZED_DISPATCH"
    )
    w.runtime = {
        "version": "stage12_development_runtime_inventory_v1",
        "population_scope": b.SYNTHETIC,
        "python_version": r.platform.python_version(),
        "platform": r.platform.system(),
        "source_inventory_sha256": b.digest(config["runtime"]["source_files"]),
        "continuous_service_state": "NOT_VERIFIED",
        "resource_sampling_is_service_monitoring": False,
        "scientific_identity_verified": False,
    }
    import stage12_b2_synthetic as fixture_module

    original_public_inputs = fixture_module.public_inputs
    transport_hash = w.put(
        {
            "origin": "https://geocode.safe-frankfurt.de",
            "approved_ip": "192.0.2.1",
            "configuration_evidence_sha256": H,
            "target_limit": 65536,
            "header_limit": 65536,
        }
    )

    def exact_transport_inputs(count):
        result = original_public_inputs(count)
        result[0]["transport_profile_sha256"] = transport_hash
        return result

    monkeypatch.setattr(fixture_module, "public_inputs", exact_transport_inputs)
    values = w.inputs()
    run, config = campaign_port(
        w, "run-campaign", values, output=tmp_path / "runtime_segment"
    )
    result = cli.execute(
        "run-campaign",
        cli.Session(
            run,
            config,
            tmp_path / "runtime_segment",
            tmp_path / "run_preflight.sqlite",
            H,
        ),
    )
    assert (
        result["report_complete"]
        and result["counts"]["durable_valid_data"]["value"] == 2
    )
    snapshot = b.parse(io.read(tmp_path / "runtime_segment/snapshot.json"), o.SNAPSHOT)
    closure = w.put(
        {
            "schema_version": "stage12_campaign_closure_b2_v1",
            "window_plan_sha256": w.window_hash,
            "campaign_start_sha256": b.digest(values[3]),
            "ordered_segment_closure_hashes": [snapshot["segment_closure_sha256"]],
            "workload_sha256": b.digest(values[1]),
            "workload_kind": values[1]["workload_kind"],
            "operator_campaign_account_sha256": H,
            "account_status": "NO_KNOWN_INTERVENTION",
            "disposition": "CLOSED_OBSERVATIONAL",
            "reviewed_utc": w.clock.utc(),
            "review_decision_sha256": H,
        }
    )
    close, config = campaign_port(
        w, "close-campaign", values, output=tmp_path / "close_unused", closure=closure
    )
    assert (
        cli.execute(
            "close-campaign",
            cli.Session(
                close, config, tmp_path / "close_unused", tmp_path / "close_work", H
            ),
        )["disposition"]
        == "CLOSED_OBSERVATIONAL"
    )
    publish, config = campaign_port(
        w, "publish", values, output=tmp_path / "published", closure=closure
    )
    mh = cli.execute(
        "publish",
        cli.Session(
            publish, config, tmp_path / "published", tmp_path / "publication_work", H
        ),
    )
    reopen, config = campaign_port(
        w,
        "reopen",
        values,
        output=tmp_path / "reopen_unused",
        closure=closure,
        publication=(tmp_path / "published", mh.hex()),
    )
    manifest = cli.execute(
        "reopen",
        cli.Session(
            reopen, config, tmp_path / "reopen_unused", tmp_path / "reopening_work", H
        ),
    )
    assert manifest["kind"] == b.SYNTHETIC + "_" + pub.CALIBRATION
    assert (
        len(list(pub.relation_rows(tmp_path / "published", "request_execution"))) == 2
    )
    assert (tmp_path / "published/_COMMITTED").exists()


def test_generation_bound_rejects_success_and_keeps_partial_files(
    tmp_path, monkeypatch
):
    w = World(tmp_path)
    config, gate, grants = configuration(w)
    config["runtime"]["phase_generation_bound_bytes"] = 8192
    pin(w, config, grants)
    runtime = port(w, config)

    def create_too_much(phase, session, resources):
        session.require(phase)
        io.write(session.output, b"invented" * 2048)
        return {"would_be_success": True}

    monkeypatch.setattr(cli, "_execute", create_too_much)
    with pytest.raises(c.Stage12Error, match="B2_RUNTIME_GENERATION_BOUND"):
        cli.execute(
            "plan-calibration",
            cli.Session(runtime, config, tmp_path / "output", tmp_path / "scratch", H),
        )
    assert (tmp_path / "output").stat().st_size == 16384 and runtime._closed


def test_generation_checkpoint_and_temporary_directory_are_bounded(tmp_path):
    w = World(tmp_path)
    config, gate, grants = configuration(w)
    config["runtime"]["phase_generation_bound_bytes"] = 8192
    pin(w, config, grants)
    runtime = port(w, config)
    runtime.bind_session(
        "plan-calibration", config, tmp_path / "output", tmp_path / "scratch", H
    )
    import tempfile

    with tempfile.TemporaryFile():
        assert r.sqlite3.connect(":memory:").execute(
            "pragma temp_store_directory"
        ).fetchone() == (config["runtime"]["temporary_root"],)
    io.write(tmp_path / "output", b"x" * 16384)
    w.clock.advance(1001000000)
    with pytest.raises(c.Stage12Error, match="B2_RUNTIME_GENERATION_BOUND"):
        runtime.check_deadline()
    with pytest.raises(c.Stage12Error, match="B2_RUNTIME_GENERATION_BOUND"):
        runtime.close()
    assert runtime._closed and r._AUDIT_ACTIVE == 0


def test_catalog_opening_boundary_checks_permission_before_bytes(tmp_path, monkeypatch):
    w = World(tmp_path)
    config, gate, grants = configuration(w, phase="close-campaign")
    pin(w, config, grants)
    runtime = port(w, config)
    monkeypatch.setattr(
        r.catalogs,
        "Catalog",
        lambda *a, **k: pytest.fail("catalog opened before permission/authority"),
    )
    try:
        with pytest.raises((c.Stage12Error, FileNotFoundError)):
            runtime._catalog_for_verify()
        runtime._rules()
        with pytest.raises((c.Stage12Error, FileNotFoundError)):
            runtime.response_rules.expected_echo(
                {"query_semantic_id": H, "result_limit": 5}
            )
    finally:
        runtime.close()


def test_transport_original_binding_checked_before_provider(tmp_path):
    w = World(tmp_path)
    config, gate, grants = configuration(
        w, phase="run-campaign", mode="EXACT_AUTHORIZED_DISPATCH"
    )
    configured = {
        "origin": "https://geocode.safe-frankfurt.de",
        "approved_ip": "192.0.2.1",
        "configuration_evidence_sha256": H,
        "target_limit": 65536,
        "header_limit": 65536,
    }
    retained = {**configured, "approved_ip": "192.0.2.2"}
    config["runtime"]["transport"] = configured
    pin(w, config, grants)
    runtime = port(w, config)
    runtime.gate = w.gate
    runtime._campaign = ({"transport_profile_sha256": w.put(retained)},)
    runtime._test["key_provider"] = lambda: pytest.fail(
        "provider accessed before transport binding"
    )
    try:
        with pytest.raises(c.Stage12Error, match="B2_RUNTIME_TRANSPORT_BINDING"):
            runtime.runtime_key()
    finally:
        runtime.close()


def test_phase_expiry_and_low_memory_fail_closed(tmp_path):
    w = World(tmp_path)
    config, gate, grants = configuration(w)
    pin(w, config, grants)
    runtime = port(w, config)
    w.clock.advance(config["runtime"]["phase_duration_ms"] * 1000000)
    with pytest.raises(c.Stage12Error, match="B2_RUNTIME_DEADLINE"):
        runtime.close()
    assert runtime._closed
    config["runtime"]["phase_memory_bytes"] = 1
    pin(w, config, grants)
    with pytest.raises(c.Stage12Error, match="B2_RUNTIME_MEMORY_LIMIT"):
        port(w, config)


def test_catalog_indexes_preserve_results_and_reduce_actual_sqlite_steps(tmp_path):
    """Bounded128-row same bytes; VM work measured, no population timing claim."""
    import sqlite3

    w = World(tmp_path, count=128)
    clone = tmp_path / "diagnostic.sqlite"
    db = sqlite3.connect(clone)
    clone.chmod(0o600)
    w.catalog.db.backup(db)
    query = "select distinct c.metadata from context c join hypothesis h on h.u=c.u join mapping m on m.h=h.h where m.q=? order by c.u"
    ids = [row["query_semantic_id"] for row in w.catalog.semantics()]

    def measure():
        steps = [0]

        def tick():
            steps[0] += 1
            return 0

        db.set_progress_handler(tick, 1)
        result = [db.execute(query, (q,)).fetchall() for q in ids]
        db.set_progress_handler(None, 0)
        return steps[0], result

    fast, expected = measure()
    db.executescript("drop index mapping_query;drop index hypothesis_context;")
    slow, actual = measure()
    assert actual == expected and fast < slow // 4
    db.close()
    w.catalog.verify()


def test_live_unlinked_spill_and_sqlite_sibling_count_toward_generation(tmp_path):
    import tempfile

    w = World(tmp_path)
    config, _, grants = configuration(w)
    config["runtime"]["phase_generation_bound_bytes"] = 8192
    pin(w, config, grants)
    runtime = port(w, config)
    runtime.bind_session(
        "plan-calibration", config, tmp_path / "output", tmp_path / "scratch.sqlite", H
    )
    try:
        with tempfile.TemporaryFile() as spill:
            spill.write(b"x" * 16384)
            spill.flush()
            with pytest.raises(c.Stage12Error, match="B2_RUNTIME_GENERATION_BOUND"):
                runtime.reconcile_generation()
        io.write(tmp_path / "scratch.sqlite-journal", b"x" * 16384)
        with pytest.raises(c.Stage12Error, match="B2_RUNTIME_GENERATION_BOUND"):
            runtime.reconcile_generation()
    finally:
        with pytest.raises(c.Stage12Error, match="B2_RUNTIME_GENERATION_BOUND"):
            runtime.close()


def test_sqlite_phase_callback_interrupts_long_query(tmp_path):
    tmp_path.chmod(0o700)
    db = r.catalogs.connect(tmp_path / "bounded.sqlite")
    seen = []

    def stop():
        seen.append(True)
        raise c.Stage12Error("B2_RUNTIME_DEADLINE")

    try:
        with io.cooperative_io(stop), pytest.raises(r.sqlite3.OperationalError):
            db.execute(
                "with recursive n(x) as(select 1 union all select x+1 from n where x<100000) select sum(x) from n"
            ).fetchone()
        assert seen
    finally:
        db.close()


def test_prepare_bootstrap_entrypoint_returns_actual_hash_without_admission(tmp_path):
    w = World(tmp_path)
    values = w.inputs()
    profile, plan, start, _, admission, _ = values
    config, gate, grants = configuration(w, phase="prepare-bootstrap")
    prepath = w.records.root / (H + ".json")
    config["bootstrap"] = {
        "profile_sha256": w.put(profile),
        "plan_sha256": w.put(plan),
        "start_sha256": w.put(start),
        "segment_nonce": admission["segment_nonce"],
        "epoch_id": admission["epoch_id"],
        "records": [
            {"path": str(prepath), "sha256": H, "bytes": prepath.stat().st_size}
        ],
        "authority_sha256": H,
        "writer_release_evidence_sha256": w.releases[admission["segment_nonce"]],
        "previous_hash": None,
    }
    grants.require("bootstrap_inputs", H, config["bootstrap"])
    pin(w, config, grants)
    runtime = port(w, config)
    runtime.gate = w.gate
    runtime.gate.window_hash = w.window_hash
    result = cli.execute(
        "prepare-bootstrap",
        cli.Session(
            runtime,
            config,
            tmp_path / "new_bootstrap",
            tmp_path / "bootstrap_scratch",
            H,
        ),
    )
    assert (
        result["admission_issued"] is False and result["dispatch_authorized"] is False
    )
    actual = io.metadata(io.read(tmp_path / "new_bootstrap/_WRITER_RELEASED.json"))
    assert actual["bootstrap_sha256"] == result["bootstrap_acquisition_sha256"]
    assert runtime._key is None and runtime._closed


def test_temp_directory_assertion_failure_restores_global_state(tmp_path, monkeypatch):
    w = World(tmp_path)
    config, _, grants = configuration(w)
    pin(w, config, grants)
    runtime = port(w, config)
    original = r.sqlite3.connect
    probe = original(":memory:")
    before = probe.execute("pragma temp_store_directory").fetchone()
    probe.close()
    closed = []

    class FaultingConnection:
        def __init__(self):
            self.db = original(":memory:")
            self.queries = 0

        def execute(self, query):
            cursor = self.db.execute(query)
            if query == "pragma temp_store_directory":
                self.queries += 1
                if self.queries == 2:
                    return SimpleNamespace(fetchone=lambda: ("invented mismatch",))
            return cursor

        def close(self):
            self.db.close()
            closed.append(True)

    monkeypatch.setattr(r.sqlite3, "connect", lambda *_: FaultingConnection())
    try:
        with pytest.raises(c.Stage12Error, match="B2_RUNTIME_TEMP_DIRECTORY"):
            runtime.bind_session(
                "plan-calibration", config, tmp_path / "output", tmp_path / "scratch", H
            )
    finally:
        runtime.close()
    probe = original(":memory:")
    assert probe.execute("pragma temp_store_directory").fetchone() == before and closed
    probe.close()


def test_failed_sqlite_restore_still_restores_python_tempdir(tmp_path, monkeypatch):
    import tempfile

    w = World(tmp_path)
    config, _, grants = configuration(w)
    pin(w, config, grants)
    runtime = port(w, config)
    original = r.sqlite3.connect
    probe = original(":memory:")
    previous = probe.execute("pragma temp_store_directory").fetchone()
    probe.close()
    python_before = tempfile.tempdir

    class RestoreFault:
        def __init__(self):
            self.db = original(":memory:")
            self.sets = 0

        def execute(self, query):
            if query.startswith("pragma temp_store_directory="):
                self.sets += 1
                if self.sets == 2:
                    raise r.sqlite3.OperationalError("invented cleanup failure")
            return self.db.execute(query)

        def close(self):
            self.db.close()

    monkeypatch.setattr(r.sqlite3, "connect", lambda *_: RestoreFault())
    try:
        runtime.bind_session(
            "plan-calibration", config, tmp_path / "output", tmp_path / "scratch", H
        )
        with pytest.raises(r.sqlite3.OperationalError):
            runtime.close()
        assert tempfile.tempdir == python_before and runtime._closed
    finally:
        cleanup = original(":memory:")
        cleanup.execute(
            "pragma temp_store_directory='"
            + str(previous[0] if previous else "").replace("'", "''")
            + "'"
        )
        cleanup.close()
