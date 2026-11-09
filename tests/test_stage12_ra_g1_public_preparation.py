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
    descriptors = {
        name: builder.digest(value) for name, value in contract.descriptors().items()
    }
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


def public_accounting(sources):
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
    return ac.compile_inventory(sources, backends, "PUBLIC_SYNTHETIC_ONLY")


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
