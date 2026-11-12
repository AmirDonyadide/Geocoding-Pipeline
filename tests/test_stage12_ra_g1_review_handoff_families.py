"""Matched ADMIN and REP512 handoff policy paths; all fixtures synthetic/unissued."""
from copy import deepcopy
import hashlib
import os
import pytest

from test_stage12_ra_g1_review_handoff import (
    offline, private_source, production, narrow_process_guard,
)
import test_stage12_ra_g1_review_handoff as legacy
from test_stage12_ra_g1_rep_admin_budget import upgrade as admin_upgrade
from test_stage12_ra_g1_rep_first64_512 import upgrade as rep512_upgrade
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as assurance

@pytest.fixture(params=["ADMIN", "REP512"])
def matched(request, production, monkeypatch):
    # Reuse the real builder/control-schema fixture and exact original lifetimes.
    monkeypatch.setattr(legacy, "upgrade", admin_upgrade if request.param == "ADMIN" else rep512_upgrade)
    case = legacy.handoff.__wrapped__(production)
    case.family = request.param
    return case


def test_matched_preparation_exact_contract_and_publication(matched):
    case = matched
    expected = assurance.REP_ADMIN_SELECTION if case.family == "ADMIN" else assurance.REP512_SELECTION
    resource = case.controller.parse(case.originals["resource_selection"])
    assert resource["schema_version"] == expected
    # Actual production envelope, workload and resource-family consumers are used.
    data = case.controller.parse(case.originals["input"])
    case.diagnostic.validate_envelope(data, case.allocation["source_sha"], for_execution=True)
    case.diagnostic.validate_workloads(data)
    case.diagnostic.validate_resource_family(data["version"], resource)
    kwargs = {key:case.plan_kwargs[key] for key in ("selection_sha256", "source_sha", "job_id")}
    prepared = legacy.helper.preparation_plan(case.selection_raw, **kwargs)
    assert prepared["selection_sha256"] == case.plan_kwargs["selection_sha256"]
    assert prepared["max_external_units"] == 5
    assert "binder_resources/admin_binding.record" in prepared["expected_relative_roots"]
    plan = case.plan()
    assert plan["raw_sha256"] == hashlib.sha256(case.release).hexdigest()
    assert plan["original_binder_start_ns"] == 10**18
    assert plan["original_binder_deadline_ns"] == 10**18 + 240_000_000_000
    assert plan["operational_target_native_anchor_ns"] == 10**18 + 180_000_000_000
    assert plan["max_external_units"] == sum(plan["components"].values()) == 11
    assert plan["creation_attempts_precharged"] == 3
    assert legacy.helper.validate_publication_result(plan, returncode=0,
        stdout=plan["expected_stdout_utf8"].encode())["native_acceptance"] == "NOT_OBSERVED"


def test_resealed_cross_family_still_fails_exact_policy(matched):
    case = matched
    other = deepcopy(case.allocation)
    if case.family == "REP512":
        other.pop("rep_first64_512_adoption")
        other.pop("rep_first64_512_adoption_sha256")
        other = admin_upgrade(other)
    else:
        other = rep512_upgrade(other)
    _, objects = case.preparer.build(other, case.bootstrap, **case.kwargs)
    resource = objects["resource_selection"]
    assurance.validate_selection(resource)
    case.originals["resource_selection"] = case.controller.canonical(resource)
    selected = case.controller.parse(case.selection_raw)
    selected["resource_selection_sha256"] = case.controller.digest(resource)
    case.selection_raw = case.controller.canonical(selected)
    case.plan_kwargs["selection_sha256"] = legacy.helper.sha(case.selection_raw)
    release = case.controller.parse(case.release)
    release["selection_sha256"] = case.plan_kwargs["selection_sha256"]
    release["resource_selection_sha256"] = case.controller.digest(resource)
    case.release = case.controller.canonical(release)
    case.plan_kwargs["reviewer_release_sha256"] = legacy.helper.sha(case.release)
    with pytest.raises(RuntimeError, match="^RA_G1_HANDOFF_POLICY$"):
        case.plan()


@pytest.mark.parametrize("change", ["selection_hash", "source", "sealed_bytes", "input_original", "phase_deadline", "window", "terminal", "existing_release", "resource_hash", "input_family"])
def test_matched_families_preserve_required_rejections(matched, change):
    case = matched
    if change == "selection_hash":
        case.plan_kwargs["selection_sha256"] = "a"*64
    elif change == "source":
        case.plan_kwargs["source_sha"] = "a"*40
    elif change == "sealed_bytes":
        case.release += b" "
    elif change == "input_original":
        case.originals["input"] += b" "
    elif change == "phase_deadline":
        phase = case.controller.parse(case.originals["phase8_binding"])
        phase["deadline_mono_ns"] += 1
        case.originals["phase8_binding"] = case.controller.canonical(phase)
    elif change == "window":
        case.plan_kwargs["observed_utc"] = case.allocation["valid_until"]
    elif change == "terminal":
        case.plan_kwargs["slurm_state"] = "COMPLETED"
    elif change == "existing_release":
        case.plan_kwargs["existing_paths"] = [case.allocation["paths"]["release"]]
    elif change == "resource_hash":
        selected = case.controller.parse(case.selection_raw)
        selected["resource_selection_sha256"] = "a"*64
        case.selection_raw = case.controller.canonical(selected)
        case.plan_kwargs["selection_sha256"] = legacy.helper.sha(case.selection_raw)
    elif change == "input_family":
        data = case.controller.parse(case.originals["input"])
        data["version"] = case.diagnostic.REP512_VERSION if case.family == "ADMIN" else case.diagnostic.REP_ADMIN_VERSION
        case.originals["input"] = case.controller.canonical(data)
        release = case.controller.parse(case.release)
        release["input_sha256"] = legacy.helper.sha(case.originals["input"])
        case.release = case.controller.canonical(release)
        case.plan_kwargs["reviewer_release_sha256"] = legacy.helper.sha(case.release)
    with pytest.raises((RuntimeError, ValueError)):
        case.plan()
