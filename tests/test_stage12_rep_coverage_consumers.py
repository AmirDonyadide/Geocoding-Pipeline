"""Closed successor bindings; invented outcomes confer no live authority."""

from copy import deepcopy
from pathlib import Path

import pytest

import stage12_prepare_ra_g1_public as public_preparer
import stage12_ra_g1_terminal_verify as terminal
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as assurance
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_rep_coverage_contract as coverage
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_rep_fair_contract as fair
from safe_geocoding_pipeline.preprocessing.stages import s12_public_runtime as runtime
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_timing as timing


REPO = Path(__file__).resolve().parents[1]
H = "7" * 64
G = "8" * 40


def outcome():
    report, manifest = b"TEST_ONLY independent report\n", b"TEST_ONLY exact manifest\n"
    return dict(schema_version=assurance.REP_COVERAGE_OUTCOME,
        scope="REPRESENTATIVE_NO_SERVICE", source_git_sha=G,
        selection_sha256=H, input_sha256=H,
        artifact_manifest_sha256=c.sha(manifest).hex(),
        independent_report_sha256=c.sha(report).hex(),
        disposition="PASS_COMPLETE_REPRESENTATIVE_WORKLOAD",
        expected_attempts=106, maximum_attempts=107, scenarios_completed=4,
        actual_reopening=True, workload_evidence_complete=True,
        ap_coverage_status="INCOMPLETE", administrative_monitor_coverage="COMPLETE_SELECTED_SCOPE",
        sampling_policy_version=coverage.POLICY_VERSION,
        sampling_policy_sha256=coverage.POLICY_SHA,
        authority_attribution="INDEPENDENT_AGENT_OUTCOME_NOT_HUMAN_OR_OPERATOR"), report, manifest


def test_all_current_assets_match_without_changing_legacy_assets():
    runtime.verify_successor_assets(REPO, contract=coverage,
        rep_admin_successor=True, first64_512_successor=True, foreground_successor=True,
        fair_service_successor=True, coverage_successor=True)
    assert coverage.POLICY["maximum_acquisition_gap_ms"] == 100
    assert coverage.POLICY["maximum_outstanding_observations"] == 16
    assert coverage.POLICY["positive_acquisition_gap_action"] == "REPORT_COVERAGE_FAILURE"
    assert "positive_acquisition_gap_action" not in fair.POLICY


def test_exact_runtime_and_original_workload_family_selection():
    assert runtime.sampling_contract({"schema_version": coverage.PROFILE}) is coverage
    assert runtime.sampling_contract(config={"version": coverage.CONFIG}) is coverage
    assert terminal.workload_contract(dict(scope="REPRESENTATIVE_NO_SERVICE",
        version="stage12_ra_g1_rep_coverage_allocation_selection_v1")) is coverage
    assert terminal.workload_contract(dict(scope="REPRESENTATIVE_NO_SERVICE",
        version="stage12_ra_g1_rep_fair_service_allocation_selection_v1")) is fair
    with pytest.raises(c.Stage12Error):
        runtime.sampling_contract({"schema_version": fair.PROFILE}, {"version": coverage.CONFIG})
    with pytest.raises(c.Stage12Error):
        runtime.sampling_contract({"schema_version": coverage.PROFILE}, {"version": fair.CONFIG})


def test_timing_version_and_policy_hash_are_matched():
    binding = dict(policy_sha256=coverage.POLICY_SHA, source_sha256=H, task_sha256=H)
    assert timing.validate_policy_binding(coverage.POLICY_VERSION, binding,
        schema=timing.RA_SCHEMA) == coverage.POLICY_VERSION
    for version, policy in ((fair.POLICY_VERSION, coverage.POLICY_SHA),
                            (coverage.POLICY_VERSION, fair.POLICY_SHA)):
        with pytest.raises(timing.cp.CheckpointError):
            timing.validate_policy_binding(version, dict(binding, policy_sha256=policy), schema=timing.RA_SCHEMA)


def test_conditional_public_consumer_keeps_workload_admin_and_ap_separate():
    value, report, manifest = outcome()
    public_preparer.verify_representative(value, report, manifest, G)
    assert assurance.validate_rep_coverage_outcome(value)["ap_coverage_status"] == "INCOMPLETE"
    value["ap_coverage_status"] = "COMPLETE"
    public_preparer.verify_representative(value, report, manifest, G)


@pytest.mark.parametrize("mutation", ["legacy_combined", "wrong_policy", "missing_records",
    "admin_gap", "false_reopening", "wrong_source", "changed_report", "wrong_version"])
def test_conditional_public_rejects_mixed_or_ineligible_outcomes(mutation):
    value, report, manifest = outcome()
    value = deepcopy(value)
    if mutation == "legacy_combined": value["sampling_and_monitor_coverage"] = "COMPLETE_SELECTED_SCOPE"
    elif mutation == "wrong_policy": value["sampling_policy_sha256"] = fair.POLICY_SHA
    elif mutation == "missing_records": value["workload_evidence_complete"] = False
    elif mutation == "admin_gap": value["administrative_monitor_coverage"] = "INCOMPLETE"
    elif mutation == "false_reopening": value["actual_reopening"] = False
    elif mutation == "wrong_source": value["source_git_sha"] = "9" * 40
    elif mutation == "changed_report": report += b"changed"
    else: value["schema_version"] = "stage12_ra_g1_representative_independent_outcome_v1"
    with pytest.raises(c.Stage12Error):
        public_preparer.verify_representative(value, report, manifest, G)
