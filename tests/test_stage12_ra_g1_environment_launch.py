# ruff: noqa: F811 -- imported pytest fixtures are used by their parameter names.
"""Focused companion gate tests; every authority/kernel/window fact is INVENTED.

The connected case runs actual ready(), actual controller readers/source fence,
and the installed production Python audit. Only native seccomp/cgroup and wall
clock are explicit fixtures. This is not timing or Goethe qualification.
"""

from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path
import socket

import pytest

from test_stage12_ra_g1_allocation_controller import world  # noqa: F401
from test_stage12_ra_g1_production_binding import (  # noqa: F401
    private_source,
    production,
    installed_production_audit,
)
from test_stage12_ra_g1_rep_first64_512 import upgrade
from test_s12_ra_g1_bootstrap30 import bootstrap_inputs
from test_stage12_public_operations_v2 import offline  # noqa: F401
from safe_geocoding_pipeline.preprocessing.stages import s12_transport

ROOT = Path(__file__).resolve().parents[1]
H = "b" * 64
G = "a" * 40


def load_gate():
    spec = importlib.util.spec_from_file_location(
        "actual_environment_gate", ROOT / "scripts/stage12_ra_g1_environment_launch.py"
    )
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def original(controller, path, value):
    raw = controller.canonical(value)
    path.write_bytes(raw)
    path.chmod(0o600)
    return hashlib.sha256(raw).hexdigest()


def setup_gate(controller, selected, source, records):
    gate = load_gate()
    rows = selected["source_files"]
    for required in gate.REQUIRED_SOURCE:
        path = source / required
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        raw = (ROOT / required).read_bytes()
        if not any(row["path"] == required for row in rows):
            path.write_bytes(raw)
            path.chmod(0o600)
            rows.append(
                dict(
                    path=required,
                    bytes=len(raw),
                    sha256=hashlib.sha256(raw).hexdigest(),
                )
            )
    rows.sort(key=lambda row: row["path"])
    raw = (ROOT / gate.DOCUMENT).read_bytes()
    if "bootstrap_prefix_adoption" not in selected:
        _, prefix, _ = bootstrap_inputs()
        selected["bootstrap_prefix_adoption"] = prefix
        selected["bootstrap_prefix_adoption_sha256"] = controller.digest(prefix)
    selected = upgrade(selected)
    binding = dict(
        version=gate.BINDING, source_tree=G, **{key: H for key in gate.BINDING_HASHES}
    )
    binding["policy_sha256"] = gate.digest(gate.descriptor())
    binding["amendment_sha256"] = hashlib.sha256(raw).hexdigest()
    prior = controller.parse(
        (records / (selected["records"]["software_review"] + ".record")).read_bytes()
    )
    prior["environment_gate_binding"] = binding
    review_hash = controller.digest(prior)
    original(controller, records / (review_hash + ".record"), prior)
    selected["records"]["software_review"] = review_hash
    value = dict(
        version=gate.VERSION,
        scope=gate.SCOPE,
        state="ISSUED_FOR_EXISTING_SINGLE_SYNTHETIC_GRANT",
        source_git_sha=selected["source_sha"],
        source_tree=G,
        **{key: binding[key] for key in gate.BINDING_HASHES},
        selection_sha256=controller.digest(selected),
        resource_selection_sha256=selected["resource_selection_sha256"],
        software_review_sha256=review_hash,
        resource_review_sha256=selected["records"]["resource_review"],
        source_inventory_sha256=selected["accounting_inventory"][
            "source_inventory_sha256"
        ],
        valid_from=selected["valid_from"],
        valid_until=selected["valid_until"],
        outer_window_end=gate.WINDOW_END,
        grant_kind="EXISTING_SINGLE_UNUSED_NATIVE_SYNTHETIC_GRANT",
        maximum_submissions=1,
        task_profiling="DISABLED",
        budget=deepcopy(gate.BUDGET),
        history=deepcopy(gate.HISTORY),
    )
    identity = gate.digest(value)
    original(controller, gate.gate_path(selected, identity), value)
    controller.validate_selection(selected)
    return gate, selected, binding, value, identity


@pytest.fixture
def case(world):  # noqa: F811  # noqa: F811
    gate, selected, binding, value, identity = setup_gate(
        world.m, deepcopy(world.s), world.source, world.records
    )
    return world, gate, selected, binding, value, identity


def test_closed_gate_at_inclusive_declared_window_boundary(case):
    _, gate, selected, binding, value, _ = case
    exact = (
        gate.epoch_ns(value["valid_until"]) - gate.REQUIRED_REMAINING_SECONDS * 10**9
    )
    result = gate.validate_gate(value, selected, binding, now_epoch_ns=exact)
    assert result["remaining_ns"] == result["required_remaining_ns"]
    assert not result["native_timing_PASS"]
    with pytest.raises(RuntimeError, match="RA_G1_DEADLINE"):
        gate.validate_gate(value, selected, binding, now_epoch_ns=exact + 1)


@pytest.mark.parametrize(
    "field,value",
    [
        ("scope", "PUBLIC_SYNTHETIC_ONLY"),
        ("scope", "DEVELOPMENT_LOCAL_PREPARATION"),
        ("grant_kind", "NEW_REPRESENTATIVE_GRANT"),
        ("maximum_submissions", 2),
        ("maximum_submissions", True),
        ("task_profiling", "ENABLED"),
        ("version", "historical_legacy_family"),
        ("grant_nonce", "c" * 64),
        ("selection_sha256", "c" * 64),
        ("source_git_sha", "c" * 40),
        ("amendment_sha256", "c" * 64),
        ("collection_plan_sha256", "c" * 64),
        ("outer_window_end", "2026-11-12T19:13:21.620987Z"),
    ],
)
def test_mixed_stale_wrong_grant_or_scope_rejected(case, field, value):
    _, gate, selected, binding, chosen, _ = case
    chosen = deepcopy(chosen)
    chosen[field] = value
    with pytest.raises(RuntimeError):
        gate.validate_gate(
            chosen,
            selected,
            binding,
            now_epoch_ns=gate.epoch_ns("2026-01-01T12:00:00.000000Z"),
        )


def test_no_unknown_or_missing_fields_or_relaxed_history(case):
    _, gate, selected, binding, chosen, _ = case
    for change in ("extra", "missing", "history", "budget"):
        value = deepcopy(chosen)
        if change == "extra":
            value["unchecked_permission"] = True
        elif change == "missing":
            del value["gate_review_sha256"]
        elif change == "history":
            value["history"]["rejected_AP_interval"] = 100000000
        else:
            value["budget"]["AP_acquisition_gap_ms"] = 101
        with pytest.raises(RuntimeError):
            gate.validate_gate(
                value,
                selected,
                binding,
                now_epoch_ns=gate.epoch_ns("2026-01-01T12:00:00.000000Z"),
            )


def attach(run, gate, identity, parser):
    run.environment_gate_sha256 = identity
    run.environment_gate_module = gate
    # The caller supplies the actual source-owned production parser.
    run.environment_gate_parser = parser


def test_actual_ready_fresh_originals_and_gate_recheck(case, monkeypatch):
    world, gate, selected, _, _, identity = case
    monkeypatch.setattr(
        gate.time, "time_ns", lambda: gate.epoch_ns("2026-01-01T12:00:00.000000Z")
    )
    run = world.m.Run(selected, stage="ready", stage_seconds=30)
    try:
        attach(run, gate, identity, world.m.parse)
        proof = gate.precheck(run)
        assert world.m.ready(run)
        assert proof["gate_sha256"] == identity
        assert run.read_calls > 4 and run.write_bytes == run.creations == 0
        source = world.source / "synthetic_only.py"
        source.write_bytes(b"CHANGED_INVENTED_SOURCE")
        with pytest.raises(RuntimeError, match="RA_G1_SOURCE_CHANGED"):
            world.m.ready(run)
    finally:
        run.close()


@pytest.mark.parametrize("change", ["gate", "review", "expired", "poisoned"])
def test_between_stage_changes_and_uncertainty_never_late_pass(
    case, monkeypatch, change
):
    world, gate, selected, _, _, identity = case
    clock = [gate.epoch_ns("2026-01-01T12:00:00.000000Z")]
    monkeypatch.setattr(gate.time, "time_ns", lambda: clock[0])
    run = world.m.Run(selected, stage="ready", stage_seconds=30)
    try:
        attach(run, gate, identity, world.m.parse)
        gate.precheck(run)
        if change == "gate":
            gate.gate_path(selected, identity).write_bytes(b"{}\n")
        elif change == "review":
            (
                world.records / (selected["records"]["software_review"] + ".record")
            ).write_bytes(b"{}\n")
        elif change == "expired":
            clock[0] = (
                gate.epoch_ns(selected["valid_until"])
                - gate.REQUIRED_REMAINING_SECONDS * 10**9
                + 1
            )
        else:
            run.poisoned = True
        with pytest.raises(RuntimeError):
            world.m.ready(run)
    finally:
        run.close()


def test_selection_hash_is_exact_and_bounded_before_encoder_materialization(
    monkeypatch,
):
    gate = load_gate()
    value = {
        "Unicode": ["😀", 'quote"\\', None, False, 18446744073709551615],
        "x": {"y": 42},
    }
    assert gate.selection_digest(value) == gate.digest(value)

    class NeverEncode:
        def __init__(self, **kwargs):
            raise AssertionError("oversized input reached encoder")

    monkeypatch.setattr(gate.json, "JSONEncoder", NeverEncode)
    with pytest.raises(RuntimeError, match="RA_G1_READ_LIMIT"):
        gate.selection_digest({"oversized": "x" * 1025})


def test_legacy_ready_without_gate_remains_supported(world):  # noqa: F811
    with world.run("ready") as run:
        assert world.m.ready(run)
        assert not hasattr(run, "environment_gate_initial")


def test_real_installed_audit_exact_companion_and_connected_ready(
    production, monkeypatch
):  # noqa: F811
    case = production
    # The existing production fixture's old placeholders are explicitly upgraded
    # to satisfy actual ready(), never presented as genuine human authority.
    for name, patch in {
        "adoption": {
            "decision": "ADOPTED_PROSPECTIVELY_WITH_EXPLICIT_LOCAL_REPAIR_OVERRIDE"
        },
        "project_approval": {
            "attribution": "OWNER_REPORTED_PROJECT_APPROVAL_NOT_ADMIN_ATTESTATION",
            "scope": case.controller.SCOPE,
        },
    }.items():
        old = case.controller.parse(
            (case.records / (case.allocation["records"][name] + ".record")).read_bytes()
        )
        old.update(patch)
        sha = case.controller.digest(old)
        original(case.controller, case.records / (sha + ".record"), old)
        case.allocation["records"][name] = sha
    gate, selected, _, _, identity = setup_gate(
        case.controller, case.allocation, case.source, case.records
    )
    case.allocation = selected
    monkeypatch.setattr(
        gate.time, "time_ns", lambda: gate.epoch_ns("2026-01-01T12:00:00.000000Z")
    )
    target = gate.gate_path(selected, identity)
    wrong = gate.gate_path(selected, "c" * 64)
    wrong.write_bytes(b"{}\n")
    wrong.chmod(0o600)
    alias = case.records / "invented-alias.record"
    alias.symlink_to(target)
    secret = case.records / ".env-invented"
    secret.write_bytes(b"INVENTED_NOT_CREDENTIAL")
    secret.chmod(0o600)
    native_install = case.controller.install_denials

    def selected_install(s, **kwargs):
        return native_install(s, **kwargs, environment_gate_sha256=identity)

    monkeypatch.setattr(case.controller, "install_denials", selected_install)
    run = case.controller.Run(selected, stage="ready", stage_seconds=120)
    try:
        attach(run, gate, identity, case.controller.parse)
        with installed_production_audit(case, run, monkeypatch) as state:
            assert gate.precheck(run)["gate_sha256"] == identity
            assert case.controller.ready(run)
            assert state["armed"] and state["events"] > 0
            for path, mode in [
                (wrong, "rb"),
                (alias, "rb"),
                (secret, "rb"),
                (target, "wb"),
            ]:
                with pytest.raises((PermissionError, RuntimeError)):
                    path.open(mode)
            with pytest.raises((PermissionError, RuntimeError)):
                s12_transport.Secret.runtime()
            with pytest.raises((PermissionError, RuntimeError)):
                socket.create_connection(("127.0.0.1", 1))
    finally:
        run.close()


def test_install_rejects_changed_review_before_any_companion_permission(
    production, monkeypatch
):  # noqa: F811
    case = production
    _, selected, _, _, identity = setup_gate(
        case.controller, case.allocation, case.source, case.records
    )
    case.allocation = selected
    path = case.records / (selected["records"]["software_review"] + ".record")
    path.write_bytes(path.read_bytes() + b" ")
    native_install = case.controller.install_denials

    def selected_install(s, **kwargs):
        return native_install(s, **kwargs, environment_gate_sha256=identity)

    monkeypatch.setattr(case.controller, "install_denials", selected_install)
    run = case.controller.Run(selected, stage="ready", stage_seconds=120)
    try:
        with pytest.raises(RuntimeError, match="RA_G1_ORIGINAL_CHANGED"):
            with installed_production_audit(case, run, monkeypatch):
                raise AssertionError("changed review admitted a companion read")
    finally:
        run.close()


def setup_collection_gate(world):
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_windows as windows
    from test_stage12_ra_g1_terminal_verify import invented_qualification
    bundle, expected = invented_qualification()
    selected = deepcopy(world.s)
    selected["source_sha"] = expected["expected_collector_source_git_sha"]
    for name in ("software_review", "resource_review"):
        old = world.m.parse((world.records/(selected["records"][name]+".record")).read_bytes())
        old["source_sha"] = selected["source_sha"]
        identity = world.m.digest(old)
        original(world.m,world.records/(identity+".record"),old)
        selected["records"][name] = identity
    gate, selected, _, _, _ = setup_gate(world.m,selected,world.source,world.records)
    for name in (gate.COLLECTION_DOCUMENT,"src/safe_geocoding_pipeline/preprocessing/stages/s12_ra_g1_windows.py","scripts/stage12_ra_g1_terminal_verify.py"):
        path = world.source/name;path.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
        raw=(ROOT/name).read_bytes();path.write_bytes(raw);path.chmod(0o644)
        selected["source_files"] = [row for row in selected["source_files"] if row["path"] != name]
        selected["source_files"].append(dict(path=name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
    selected["source_files"].sort(key=lambda row:row["path"])
    selected=upgrade(selected)
    selected.update(valid_from=windows.WINDOW_START,valid_until=windows.WINDOW_END)
    window=dict(bundle["window"],scope=gate.SCOPE)
    prior=selected["rep_admin_budget_adoption"]
    wrapped=dict(schema_version=windows.WINDOW_ADOPTION,scope=gate.SCOPE,window=window,
        original_adoption=prior,original_adoption_sha256=gate.digest(prior),grant_kind=windows.REP_GRANT,
        maximum_submissions=1,qualification_bundle_sha256=gate.digest(bundle),
        qualification_review_sha256=expected["expected_qualification_review_sha256"],
        historical_grant_consumed=True,original_budget_terms_unchanged=True)
    selected["rep_admin_budget_adoption"]=wrapped
    selected["rep_admin_budget_adoption_sha256"]=gate.digest(wrapped)
    binding=dict(version=gate.COLLECTION_BINDING,source_tree=G,
        **{key:H for key in gate.COLLECTION_BINDING_HASHES})
    binding.update(policy_sha256=gate.digest(gate.collection_descriptor()),
        window_policy_sha256=windows.digest(windows.descriptor()),owner_authority_sha256=window["owner_authority_sha256"],
        grant_nonce=window["grant_nonce"],qualification_bundle_sha256=gate.digest(bundle),
        qualification_review_sha256=expected["expected_qualification_review_sha256"],
        amendment_sha256=hashlib.sha256((ROOT/gate.COLLECTION_DOCUMENT).read_bytes()).hexdigest())
    review=world.m.parse((world.records/(selected["records"]["software_review"]+".record")).read_bytes())
    review["environment_gate_binding"]=binding
    identity=world.m.digest(review);original(world.m,world.records/(identity+".record"),review)
    selected["records"]["software_review"]=identity
    value=dict(version=gate.COLLECTION_VERSION,scope=gate.SCOPE,state="ISSUED_FOR_COLLECTION_QUALIFIED_ONE_FRESH_REP",
        source_git_sha=selected["source_sha"],source_tree=G,**{key:binding[key] for key in gate.COLLECTION_BINDING_HASHES},
        selection_sha256=gate.digest(selected),resource_selection_sha256=selected["resource_selection_sha256"],
        software_review_sha256=selected["records"]["software_review"],resource_review_sha256=selected["records"]["resource_review"],
        source_inventory_sha256=selected["accounting_inventory"]["source_inventory_sha256"],valid_from=windows.WINDOW_START,
        valid_until=windows.WINDOW_END,outer_window_end=windows.WINDOW_END,grant_kind=windows.REP_GRANT,maximum_submissions=1,
        task_profiling="DISABLED",budget=deepcopy(gate.BUDGET),history=deepcopy(gate.COLLECTION_HISTORY),window=window)
    identity=gate.digest(value)
    original(world.m,gate.gate_path(selected,identity),value)
    original(world.m,gate.qualification_path(selected,binding),bundle)
    world.m.validate_selection(selected)
    return gate,selected,binding,value,identity,bundle


def test_collection_first_actual_ready_and_fresh_0644_verifier(world,monkeypatch):
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_windows as windows
    gate,selected,_,_,identity,_=setup_collection_gate(world)
    (world.source/"scripts").chmod(0o755)
    verifier=world.source/"scripts/stage12_ra_g1_terminal_verify.py"
    assert verifier.stat().st_mode & 0o777 == 0o644
    monkeypatch.setattr(world.m,"now",lambda:windows.WINDOW_START)
    monkeypatch.setattr(gate.time,"time_ns",lambda:windows.epoch_ns(windows.WINDOW_START)+2000)
    run=world.m.Run(selected,stage="ready",stage_seconds=120)
    try:
        attach(run,gate,identity,world.m.parse)
        proof=gate.precheck(run)
        assert proof["qualification_bundle_sha256"]==selected["rep_admin_budget_adoption"]["qualification_bundle_sha256"]
        assert world.m.ready(run)
        verifier.write_bytes(verifier.read_bytes()+b"# INVENTED MUTATION\n")
        with pytest.raises(RuntimeError,match="RA_G1_SOURCE_CHANGED"):
            gate.after_ready(run)
    finally:run.close()


def test_collection_first_requires_gate_and_rejects_historical_grant(world,monkeypatch):
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_windows as windows
    gate,selected,binding,value,_,bundle=setup_collection_gate(world)
    monkeypatch.setattr(world.m,"now",lambda:windows.WINDOW_START)
    run=world.m.Run(selected,stage="ready",stage_seconds=120)
    try:
        with pytest.raises(RuntimeError,match="RA_G1_COLLECTION_QUALIFICATION_REQUIRED"):
            world.m.ready(run)
    finally:run.close()
    value["grant_kind"]="EXISTING_SINGLE_UNUSED_NATIVE_SYNTHETIC_GRANT"
    import stage12_ra_g1_terminal_verify as verifier
    with pytest.raises(RuntimeError,match="RA_G1_AUTHORITY_REQUIRED"):
        gate.validate_gate(value,selected,binding,now_epoch_ns=windows.epoch_ns(windows.WINDOW_START),
            qualification=bundle,qualification_validator=verifier.validate_qualification)
