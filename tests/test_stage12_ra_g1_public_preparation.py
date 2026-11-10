"""Public preparation uses invented originals and cannot issue live authority."""

from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

from test_stage12_public_operations_v2 import offline  # noqa:F401
from test_stage12_public_matrix import configuration
from test_s12_ra_g1_core import facts, capacity, H, G, FROM, UNTIL
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_contract as contract
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_ra_g1_assurance as assurance,
)
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_public_runtime as runtime
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_public_response as validation,
)

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "stage12_prepare_ra_g1_public", ROOT / "scripts/stage12_prepare_ra_g1_public.py"
)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def synthetic_inputs():
    template = configuration()
    template["public_validation_sha256"] = contract.digest(
        validation.descriptor(validation.CORPUS_VERSION)
    )
    allocation = dict(
        version=builder.SHARED_LEASE_ALLOCATION_VERSION,
        source_sha=G,
        task_id=H,
        valid_from=FROM,
        valid_until=UNTIL,
        paths={
            key: f"/SYNTHETIC/NOT_EXECUTABLE/{key}"
            for key in ("source", "input", "output", "evidence")
        },
        accounting=dict(
            identity_calls=100000,
            original_read_calls=1000000,
            original_read_bytes=2**40,
            check_calls=1000000,
        ),
    )
    allocation["paths"]["output"] = "/SYNTHETIC/NOT_EXECUTABLE/or2_" + H
    allocation["source_files"] = [
        dict(path="src/synthetic_only.py", bytes=19, sha256=H)
    ]
    allocation["accounting_inventory"], allocation["accounting"] = public_accounting(
        allocation["source_files"]
    )
    adoption = {"SYNTHETIC_ADOPTION_NOT_AUTHORITY": True}
    project = {"SYNTHETIC_PROJECT_APPROVAL_NOT_AUTHORITY": True}
    report = b"Synthetic independent source review, not a live release.\n"
    resource_review = dict(source_sha=G, disposition="PASS", SYNTHETIC=True)
    descriptors = builder.public_descriptor_inventory()
    policy = contract.descriptors()[assurance.POLICY]
    paths = dict(
        scope=builder.SCOPE,
        paths=allocation["paths"],
        source_git_sha=G,
        native_paths=[],
    )
    selected = builder.compile_selection(
        allocation,
        template,
        policy_sha256=builder.digest(policy),
        adoption_sha256=builder.digest(adoption),
        descriptor_inventory_sha256=builder.digest(descriptors),
        paths_sha256=builder.digest(paths),
        implementation_review_sha256=builder.raw_digest(report),
    )
    cap = capacity(selected)
    cap["owner_reported_approval_sha256"] = builder.digest(project)
    bootstrap = dict(
        source_sha=G,
        scope=builder.SCOPE,
        facts=facts(),
        manifest_sha256=H,
        resource_selection_sha256=builder.digest(selected),
        capacity=cap,
        runtime_inventory={"SYNTHETIC_ONLY": True},
        kernel_originals={"SYNTHETIC_ONLY": True},
        capacity_originals=dict(
            root=[["SYNTHETIC_ONLY"]], statvfs={"SYNTHETIC_ONLY": True}
        ),
        capacity_method={"SYNTHETIC_ONLY": True},
        capacity_restrictions={"SYNTHETIC_ONLY": True},
        resource_execution=dict(
            schema_version="stage12_resource_execution_request_ra_g1_v1",
            supervisor_context_path="/SYNTHETIC/NOT_EXECUTABLE/context.record",
            supervisor_context_sha256=H,
        ),
    )
    b_report = b"SYNTHETIC independent B outcome only.\n"
    b_manifest = b"SYNTHETIC complete artifact manifest only.\n"
    outcome = dict(
        schema_version=builder.OUTCOME,
        scope="REPRESENTATIVE_NO_SERVICE",
        source_git_sha=G,
        selection_sha256=H,
        input_sha256=H,
        artifact_manifest_sha256=builder.raw_digest(b_manifest),
        independent_report_sha256=builder.raw_digest(b_report),
        disposition="PASS_COMPLETE_REPRESENTATIVE",
        expected_attempts=106,
        maximum_attempts=107,
        scenarios_completed=4,
        actual_reopening=True,
        sampling_and_monitor_coverage="COMPLETE_SELECTED_SCOPE",
        authority_attribution="INDEPENDENT_AGENT_OUTCOME_NOT_HUMAN_OR_OPERATOR",
    )
    kwargs = dict(
        role_originals={
            role: f"SYNTHETIC ORIGINAL {role}\n".encode() for role in builder.ROLE_NAMES
        },
        source_files=[dict(path="src/synthetic_only.py", bytes=19, sha256=H)],
        implementation_report=report,
        adoption=adoption,
        project_approval=project,
        resource_review=resource_review,
        independent_bootstrap_review=dict(
            disposition="PASS", source_sha=G, bootstrap_manifest_sha256=H
        ),
        representative_outcome=outcome,
        representative_report=b_report,
        representative_manifest=b_manifest,
        test_only=True,
    )
    return template, allocation, bootstrap, kwargs


def public_accounting(sources, *, shared_lease_successor=True):
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as ac

    backends = [
        dict(
            ordinal=i,
            module=name,
            path=f"/SYNTHETIC_NOT_EXECUTABLE/{i}.so",
            identity={**dict.fromkeys(ac.IDENTITY, 1), "mode": 0o100600, "bytes": 4097},
            stat_scope="PREPARATION_HOST_SNAPSHOT",
            sha256=H,
        )
        for i, name in enumerate(ac.MODULES, 1)
    ]
    return ac.compile_inventory(
        sources, backends, "PUBLIC_SYNTHETIC_ONLY",
        shared_lease_successor=shared_lease_successor, bootstrap_successor=False,
    )


def prepared():
    template, allocation, bootstrap, kwargs = synthetic_inputs()
    return template, builder.prepare(
        c.canonical(template), allocation, bootstrap, **kwargs
    )


def review(value):
    return dict(
        schema_version="stage12_resource_bound_review_ra_g1_v1",
        scope=builder.SCOPE,
        disposition="PASS",
        bound_scope_sha256=value["bound_scope_sha256"],
        implementation_review_sha256=builder.raw_digest(value["implementation_report"]),
    )


def test_public_compiler_exact_complete_roster_and_no_native_claims():
    template = configuration()
    compiled = builder.compile_budget(template)
    assert compiled["totals"]["timing_chunks"] == 2980
    assert compiled["totals"]["creations"] == 791452
    assert compiled["totals"]["monitor_rows"] == 16352
    assert compiled["totals"]["logical_bytes"] < 512 * 2**30
    _, allocation, _, _ = synthetic_inputs()
    selected = builder.compile_selection(
        allocation,
        template,
        policy_sha256=H,
        adoption_sha256=H,
        descriptor_inventory_sha256=H,
        paths_sha256=H,
        implementation_review_sha256=H,
    )
    assert len(selected["limits"]["stages"]) == 14
    assert [row["deadline_ms"] for row in selected["limits"]["stages"]][-3:] == [
        2000000,
        840000,
        120000,
    ]
    assert sum(row["creations"] for row in selected["limits"]["stages"]) == 791452
    assert selected["limits"]["native_invocations"] == 0
    assurance.validate_selection(selected)


def test_public_prepare_preserves_every_work_and_ordinary_budget_acyclic():
    template, value = prepared()
    config = value["configuration"]
    assert value["status"] == "UNISSUED_REQUIRES_EXACT_TECHNICAL_REVIEW"
    assert len(config["campaigns"]) == 11
    assert (
        config["capability"]["additional_checks"]
        == template["capability"]["additional_checks"]
    )
    for old, new in zip(template["campaigns"], config["campaigns"], strict=True):
        assert old["work"] == new["work"]
        phase = builder.phase_budget(
            old["plan"]["budgets"]["active_duration_ms"],
            old["plan"]["budgets"]["data_attempts"]
            + old["plan"]["budgets"]["control_http_attempts"],
        )
        for key, ordinary in old["plan"]["budgets"].items():
            assert new["plan"]["budgets"][key] == (
                ordinary + phase["sample_bytes"]
                if key == "storage_bytes"
                else phase["events"]
                if key == "event_count"
                else ordinary
            )
        contract.validate_plan(new["plan"], new["profile"])
    assert value["bound_subject"][
        "configuration_scope_sha256"
    ] == assurance.configuration_scope(config)
    assert not value["resource_evidence"]["technical_reviews"]
    assert not value["resource_evidence"]["runtime_bounds"]
    assert value["bound_subject"]["native_component_guarantee"] == "NOT_CLAIMED"


def test_public_finalize_actual_new_parser_and_exact_independent_review():
    _, value = prepared()
    result = builder.finalize(value, review(value))
    assert result["status"] == "UNISSUED"
    assert len(result["integration_review"]["resource_evidence"]) == 12
    runtime.validate_config(result["configuration"])
    assert result["binding"][
        "configuration_scope_sha256"
    ] == assurance.configuration_scope(result["configuration"])
    for item in result["configuration"]["campaigns"]:
        assert item["profile"]["sampling_runtime_bound_sha256"] == builder.digest(
            result["binding"]
        )
    with pytest.raises(c.Stage12Error):
        builder.finalize(value, review(value), issued=True)
    wrong = review(value)
    wrong["bound_scope_sha256"] = H
    with pytest.raises(c.Stage12Error):
        builder.finalize(value, wrong)
    changed = deepcopy(value)
    changed["configuration"]["resource_execution"]["supervisor_context_sha256"] = (
        "3" * 64
    )
    with pytest.raises(c.Stage12Error):
        builder.finalize(changed, review(value))


@pytest.mark.parametrize(
    "mutation",
    [
        "source",
        "not_complete",
        "not_opened",
        "report",
        "manifest",
        "selection",
        "bootstrap",
    ],
)
def test_public_missing_real_bindings_cannot_prepare(mutation):
    template, allocation, bootstrap, kwargs = synthetic_inputs()
    if mutation == "source":
        kwargs["representative_outcome"]["source_git_sha"] = "3" * 40
    elif mutation == "not_complete":
        kwargs["representative_outcome"]["scenarios_completed"] = 3
    elif mutation == "not_opened":
        kwargs["representative_outcome"]["actual_reopening"] = False
    elif mutation == "report":
        kwargs["representative_report"] += b"changed"
    elif mutation == "manifest":
        kwargs["representative_manifest"] += b"changed"
    elif mutation == "selection":
        bootstrap["resource_selection_sha256"] = H
    else:
        kwargs["independent_bootstrap_review"]["disposition"] = "FAIL"
    with pytest.raises(c.Stage12Error):
        builder.prepare(c.canonical(template), allocation, bootstrap, **kwargs)


@pytest.mark.parametrize("mutation", ["bytes", "work", "ordinary", "warning"])
def test_public_historical_template_mutations_reject(mutation):
    template = configuration()
    if mutation == "work":
        template["campaigns"][0]["work"].pop()
    elif mutation == "ordinary":
        template["campaigns"][0]["plan"]["budgets"]["data_attempts"] -= 1
    elif mutation == "warning":
        template["public_validation_sha256"] = H
    raw = c.canonical(template)
    if mutation == "bytes":
        raw = raw.replace(b'"active_seconds":7200', b'"active_seconds": 7200')
    with pytest.raises(c.Stage12Error):
        builder.read_template(raw, test_only=True)
    with pytest.raises(c.Stage12Error):
        builder.read_template(c.canonical(configuration()))


def test_current_public_uses_shared512_model_and_all_exact_liabilities():
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as ac
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_public as public

    template, allocation, bootstrap, kwargs = synthetic_inputs()
    inv = allocation["accounting_inventory"]
    expected, totals = ac.compile_inventory(
        inv["sources"], inv["backends"], builder.SCOPE,
        shared_lease_successor=True, bootstrap_successor=False,
    )
    assert inv == expected and allocation["accounting"] == totals
    assert inv["schema_version"] == ac.SHARED_LEASE_VERSION
    assert inv["bootstrap_proof_record_count"] == 0
    forbidden = {"BOOTSTRAP_ORIGINAL_WRITE_READBACK", "BOOTSTRAP_ADOPTION_AND_READINESS_ORIGINALS",
                 "BOOTSTRAP_PARENT_FRESH_ORIGINALS"}
    assert not any(row["component"] in forbidden for row in inv["cost_rows"])
    assert "_BOOTSTRAP30" not in inv["graph_id"]
    writers = [row for row in inv["cost_rows"]
               if row["component"] == "MONITOR_WRITER_ORIGINAL_AND_CODEC_READBACK"]
    assert writers and {row["per_invocation_read_calls"] for row in writers} == {31}
    old, old_totals = public_accounting(allocation["source_files"], shared_lease_successor=False)
    assert ac.validate_inventory(old) == old
    writer_calls = sum(row["invocations"] for row in writers)
    assert totals["original_read_calls"] - old_totals["original_read_calls"] == 26 * writer_calls
    assert totals["check_calls"] - old_totals["check_calls"] == 26 * writer_calls
    assert totals["original_read_bytes"] == old_totals["original_read_bytes"]

    prepared_value = builder.prepare(c.canonical(template), allocation, bootstrap, **kwargs)
    finalized = builder.finalize(prepared_value, review(prepared_value))
    bound = finalized["binding"]
    assert bound["logical_scratch_bytes"] == 65152
    assert dict((row["name"], row["bytes"]) for row in bound["logical_allocations"])[
        "SERIALIZATION_SCRATCH"] == 65152
    assert bound["total_logical_bytes"] == 15908480 <= 16 * 2**20
    assert bound["maximum_identity_checks"] == totals["identity_calls"]
    assert bound["maximum_original_read_calls"] == totals["original_read_calls"]
    assert bound["maximum_original_read_bytes"] == totals["original_read_bytes"]
    for stage in finalized["resource_selection"]["limits"]["stages"]:
        actual = ac.stage_accounting(inv, stage["id"])
        assert {key: stage[key] for key in actual} == actual
    descriptor = public.shared_allocation_descriptor()
    assert descriptor["bootstrap_proof_record_count"] == 0
    assert descriptor["bootstrap_prefix_authority"] == "DENIED"
    assert descriptor["monitor_writer_readback_bytes"] == 512
    assert descriptor["monitor_writer_max_read_calls"] == 31
    assert prepared_value["descriptor_inventory"][public.SHARED_ALLOCATION_DESCRIPTOR] == builder.digest(descriptor)
    assert finalized["resource_selection"]["descriptor_inventory_sha256"] == builder.digest(
        prepared_value["descriptor_inventory"])


def test_real_current_scratch_guard_reaches_closed_fact_gate_without_issuing_authority():
    _, value = prepared()
    finalized = builder.finalize(value, review(value))

    class CurrentFactsRemainClosed(Exception):
        pass

    class Probe:
        calls = 0

        def charge_identity_check(self, record):
            self.calls += 1
            raise CurrentFactsRemainClosed("SYNTHETIC_CURRENT_FACTS_NOT_SUPPLIED")

        def resource_facts(self, record):
            raise AssertionError("no kernel fact or permission may be fabricated")

    probe = Probe()
    with pytest.raises(CurrentFactsRemainClosed):
        assurance.verify_runtime(finalized["binding"], probe, {})
    assert probe.calls == 1
    # Historical bounded records remain readable, but cannot execute this source.
    historical = deepcopy(finalized["binding"])
    historical["logical_scratch_bytes"] = 64640
    for arena in historical["logical_allocations"]:
        if arena["name"] == "SERIALIZATION_SCRATCH":
            arena["bytes"] = 64640
    historical["total_logical_bytes"] = sum(row["bytes"] for row in historical["logical_allocations"])
    profile = deepcopy(finalized["configuration"]["campaigns"][0]["profile"])
    profile["sampling_runtime_bound_sha256"] = builder.digest(historical)
    synthetic_original_identities = {
        "client_git_sha": historical["source_git_sha"],
        "runtime_inventory_sha256": historical["runtime_inventory_sha256"],
    }
    assert assurance.validate_record(historical, profile, synthetic_original_identities, contract) == historical
    old_probe = Probe()
    with pytest.raises(c.Stage12Error, match="RA_G1_LOGICAL_LIMIT"):
        assurance.verify_runtime(historical, old_probe, {})
    assert old_probe.calls == 0


@pytest.mark.parametrize("mutation", [
    "old_model", "read_calls", "check_calls", "stage_reads", "stage_checks",
    "bootstrap_proof", "representative_model", "old_outer",
])
def test_current_public_rejects_mixed_or_underfunded_accounting(mutation):
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as ac

    template, allocation, bootstrap, kwargs = synthetic_inputs()
    inv = allocation["accounting_inventory"]
    if mutation == "old_model":
        allocation["accounting_inventory"], allocation["accounting"] = public_accounting(
            allocation["source_files"], shared_lease_successor=False)
    elif mutation == "read_calls":
        allocation["accounting"]["original_read_calls"] -= 1
    elif mutation == "check_calls":
        allocation["accounting"]["check_calls"] -= 1
    elif mutation == "stage_reads":
        inv["stage_accounting"][0]["original_read_calls"] -= 1
    elif mutation == "stage_checks":
        inv["stage_accounting"][0]["check_calls"] -= 1
    elif mutation == "bootstrap_proof":
        inv["bootstrap_proof_record_count"] = 3
    elif mutation == "representative_model":
        allocation["accounting_inventory"], allocation["accounting"] = ac.compile_inventory(
            inv["sources"], inv["backends"], "REPRESENTATIVE_NO_SERVICE",
            shared_lease_successor=True, bootstrap_successor=True)
    else:
        allocation["version"] = builder.LEGACY_ALLOCATION_VERSION
    with pytest.raises((c.Stage12Error, ac.AccountingError)) as caught:
        builder.prepare(c.canonical(template), allocation, bootstrap, **kwargs)
    assert caught.value.args[0] in {"RA_G1_ACCOUNTING_CHANGED", "RA_G1_ACCOUNTING_SCOPE",
                                   "RA_G1_PUBLIC_CURRENT_MODEL_REQUIRED", "RA_G1_PUBLIC_BOOTSTRAP_DENIED"}


@pytest.mark.parametrize("mutation", ["scratch", "arena", "total"])
def test_current_public_finalize_rejects_rebound_underfunded_subject(mutation):
    _, value = prepared()
    changed = deepcopy(value)
    bound = changed["bound_subject"]
    if mutation == "scratch":
        bound["logical_scratch_bytes"] = 64640
        for arena in bound["logical_allocations"]:
            if arena["name"] == "SERIALIZATION_SCRATCH":
                arena["bytes"] = 64640
        bound["total_logical_bytes"] = sum(row["bytes"] for row in bound["logical_allocations"])
    elif mutation == "arena":
        for arena in bound["logical_allocations"]:
            if arena["name"] == "SERIALIZATION_SCRATCH":
                arena["bytes"] -= 1
        bound["total_logical_bytes"] -= 1
    else:
        bound["total_logical_bytes"] -= 1
    changed["bound_scope_sha256"] = builder.digest(bound)
    with pytest.raises(c.Stage12Error, match="RA_G1_LOGICAL_LIMIT"):
        builder.finalize(changed, review(changed))


def test_current_public_descriptor_registration_is_idempotent_and_exact(monkeypatch):
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_public as public

    before = builder.public_descriptor_inventory()
    registered = dict(contract.descriptors())
    registered[public.SHARED_ALLOCATION_DESCRIPTOR] = public.shared_allocation_descriptor()
    monkeypatch.setattr(contract, "descriptors", lambda: deepcopy(registered))
    assert builder.public_descriptor_inventory() == before
    registered[public.SHARED_ALLOCATION_DESCRIPTOR]["bootstrap_prefix_authority"] = "UNEXPECTED"
    with pytest.raises(c.Stage12Error, match="RA_G1_PUBLIC_DESCRIPTOR_CHANGED"):
        builder.public_descriptor_inventory()
