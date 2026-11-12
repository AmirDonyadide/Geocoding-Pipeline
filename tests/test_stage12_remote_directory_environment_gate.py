"""TEST_ONLY selected binding propagation; no live authority or native qualification."""
from copy import deepcopy
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from test_stage12_ra_g1_allocation_controller import world  # noqa: F401
from test_stage12_public_operations_v2 import offline  # noqa: F401
from test_stage12_ra_g1_environment_launch import setup_collection_gate, original, attach


def selected_case(world, *, legacy_qualification=False):
    gate, selected, binding, value, _, bundle = setup_collection_gate(world)
    if not legacy_qualification:
        from test_stage12_ra_g1_remote_directory_identity import remote_qualification
        bundle, expected = remote_qualification()
        selected["rep_admin_budget_adoption"]["qualification_bundle_sha256"] = gate.digest(bundle)
        selected["rep_admin_budget_adoption"]["qualification_review_sha256"] = expected["expected_qualification_review_sha256"]
        selected["rep_admin_budget_adoption_sha256"] = gate.digest(selected["rep_admin_budget_adoption"])
        binding["qualification_bundle_sha256"] = gate.digest(bundle)
        binding["qualification_review_sha256"] = expected["expected_qualification_review_sha256"]
    binding = dict(binding, version=gate.REMOTE_COLLECTION_BINDING,
        remote_directory_scope=gate.REMOTE_DIRECTORY_SCOPE,
        transport_evidence_version=gate.REMOTE_TRANSPORT_VERSION,
        remote_directory_adoption_sha256="d" * 64)
    binding["policy_sha256"] = gate.digest(gate.remote_collection_descriptor())
    review = world.m.parse((world.records / (selected["records"]["software_review"] + ".record")).read_bytes())
    review["environment_gate_binding"] = binding
    identity = world.m.digest(review)
    original(world.m, world.records / (identity + ".record"), review)
    selected["records"]["software_review"] = identity
    value = dict(value, version=gate.REMOTE_COLLECTION_VERSION,
        software_review_sha256=identity, selection_sha256=gate.digest(selected),
        **{key: binding[key] for key in (*gate.COLLECTION_BINDING_HASHES, *gate.REMOTE_COLLECTION_FIELDS)})
    if not legacy_qualification:
        original(world.m, gate.qualification_path(selected, binding), bundle)
    gate_hash = gate.digest(value)
    original(world.m, gate.gate_path(selected, gate_hash), value)
    return gate, selected, binding, value, gate_hash, bundle


def test_selected_binding_is_exact_and_legacy_descriptor_unchanged(world):
    gate, selected, binding, value, _, _ = selected_case(world)
    assert gate.validate_binding(binding, selected) is binding
    assert gate.remote_collection_descriptor()["remote_directory_scope"] == gate.REMOTE_DIRECTORY_SCOPE
    assert "remote_directory_scope" not in gate.collection_descriptor()
    assert gate.collection_descriptor()["budget"] == gate.remote_collection_descriptor()["budget"]
    assert gate.collection_descriptor()["outer_window_end"] == gate.remote_collection_descriptor()["outer_window_end"]
    assert gate.allowed_original_paths(selected, binding, gate.digest(value))[-1] == gate.qualification_path(selected, binding)


@pytest.mark.parametrize("key,value", [
    ("version", "stage12_collection_first_environment_binding_v1"),
    ("remote_directory_scope", "legacy"),
    ("transport_evidence_version", "stage12_same_session_transfer_v2"),
    ("remote_directory_adoption_sha256", "not-a-hash"),
    ("remote_directory_adoption_sha256", "0" * 64),
    ("policy_sha256", "a" * 64),
])
def test_binding_rejects_mixed_or_silent_downgrade(world, key, value):
    gate, selected, binding, _, _, _ = selected_case(world)
    binding = dict(binding); binding[key] = value
    with pytest.raises(RuntimeError): gate.validate_binding(binding, selected)


@pytest.mark.parametrize("key,value", [
    ("version", "stage12_collection_first_environment_launch_gate_v1"),
    ("remote_directory_scope", "legacy"),
    ("transport_evidence_version", "stage12_same_session_transfer_v2"),
    ("remote_directory_adoption_sha256", "e" * 64),
])
def test_gate_rejects_mixed_policy_before_qualification(world, key, value):
    gate, selected, binding, value_record, _, bundle = selected_case(world)
    chosen = deepcopy(value_record); chosen[key] = value
    def never(*args, **kwargs): raise AssertionError("mixed gate reached qualification")
    with pytest.raises(RuntimeError):
        gate.validate_gate(chosen, selected, binding,
            now_epoch_ns=gate.window_module().epoch_ns(gate.window_module().WINDOW_START),
            qualification=bundle, qualification_validator=never)


def test_actual_source_loaded_validator_rejects_legacy_bundle_under_new_policy(world, monkeypatch):
    gate, selected, _, _, identity, _ = selected_case(world, legacy_qualification=True)
    windows = gate.window_module()
    monkeypatch.setattr(world.m, "now", lambda: windows.WINDOW_START)
    monkeypatch.setattr(gate.time, "time_ns", lambda: windows.epoch_ns(windows.WINDOW_START) + 2000)
    run = world.m.Run(selected, stage="ready", stage_seconds=120)
    try:
        attach(run, gate, identity, world.m.parse)
        with pytest.raises(RuntimeError): gate.precheck(run)
        assert run.read_calls > 0
    finally: run.close()


def test_actual_native_selected_gate_ready_and_fresh_verifier_identity(world, monkeypatch):
    gate, selected, _, _, identity, _ = selected_case(world)
    windows = gate.window_module()
    monkeypatch.setattr(world.m, "now", lambda: windows.WINDOW_START)
    monkeypatch.setattr(gate.time, "time_ns", lambda: windows.epoch_ns(windows.WINDOW_START) + 2000)
    run = world.m.Run(selected, stage="ready", stage_seconds=120)
    try:
        attach(run, gate, identity, world.m.parse)
        proof = gate.precheck(run)
        assert proof["qualification_bundle_sha256"] == selected["rep_admin_budget_adoption"]["qualification_bundle_sha256"]
        assert world.m.ready(run)
        verifier = world.source / "scripts/stage12_ra_g1_terminal_verify.py"
        verifier.write_bytes(verifier.read_bytes() + b"# TEST_ONLY mutation\n")
        with pytest.raises(RuntimeError, match="RA_G1_SOURCE_CHANGED"): gate.after_ready(run)
    finally: run.close()
