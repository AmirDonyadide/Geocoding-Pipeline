"""Focused denied RA-G1 DATA-path integration, not Goethe qualification."""

from copy import deepcopy

import pytest
from test_stage12_public_operations_v2 import H, KEY, offline  # noqa: F401
from test_stage12_public_sampling_contract import ap_inputs
from test_stage12_public_sampling_integration import RealClock
from test_s12_ra_g1_core import selection, binding, facts, capacity
from stage12_synthetic import body, feature
from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_contract as a
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_transport as t
from safe_geocoding_pipeline.preprocessing.stages import s12_public_runtime as runtime
from safe_geocoding_pipeline.preprocessing.stages.s12_public_response import Validation
from safe_geocoding_pipeline.preprocessing.stages.s12_ra_g1_public import (
    ApplicationControls,
    Authority,
)


def synthetic_previous_terminal():
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_ra_g1_monitor as monitor,
    )

    return dict(
        schema_version=monitor.MONITOR_TERMINAL,
        binding_sha256=H,
        phase_id=13,
        opener_return_sha256=H,
        prefix_H0_sha256=H,
        full_monitor_inventory_sha256=H,
        final_observation_sha256=H,
        final_observation_ns=1000,
        last_ack_ns=1100,
        last_seq=2,
        coverage_start_ns=100,
        coverage_end_ns=1000,
        max_gap_ns=900,
        disposition="CLOSED_SELECTED_SCOPE",
        writer_state="HEALTHY_RELEASED",
    )


@pytest.mark.parametrize("gap", [999999999, 1000000000, 1000000001])
@pytest.mark.parametrize("duration", [500000, 180000, 2000000])
def test_actual_transition_window_exposes_delayed_next_start_to_coverage(gap, duration):
    from types import SimpleNamespace
    from test_s12_ra_g1_core import observation
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_ra_g1_monitor as monitor,
    )

    selected = selection()
    # Invented clock: time spent in setup/proof/transport/plan construction is
    # already elapsed before the next scope is started. No runtime claim.
    now = 1000 + gap
    clock = SimpleNamespace(now_ns=lambda: now)
    start, deadline = runtime.resource_transition_window(
        clock, {"monitor_terminal": synthetic_previous_terminal()}, duration, 10**15
    )
    assert start == 1000
    assert deadline.end_ns == 1000 + duration * 10**6
    scope = monitor.Coverage(
        binding_sha256=H,
        selection_sha256=a.digest(selected),
        phase_id=1,
        seed_sha256=H,
        selected=selected,
        scope_start_ns=start,
    )
    actual = observation(selected, enter=now)
    actual["binding_sha256"] = actual["previous_sha256"] = H
    if gap <= 1000000000:
        scope.add(actual)
    else:
        with pytest.raises(c.Stage12Error):
            scope.add(actual)


def test_transition_does_not_reset_expired_task_or_accept_unclosed_predecessor():
    from types import SimpleNamespace

    previous = {"monitor_terminal": synthetic_previous_terminal()}
    with pytest.raises(runtime.recovery.FinalizationExpired):
        runtime.resource_transition_window(
            SimpleNamespace(now_ns=lambda: 3000000), previous, 1, 10**15
        )
    with pytest.raises(runtime.recovery.FinalizationExpired):
        runtime.resource_transition_window(
            SimpleNamespace(now_ns=lambda: 2000), previous, 500000, 1500
        )
    previous["monitor_terminal"]["disposition"] = "INCOMPLETE"
    with pytest.raises(c.Stage12Error):
        runtime.resource_transition_window(
            SimpleNamespace(now_ns=lambda: 2000), previous, 500000, 10**15
        )


def source_only_authority(root, raw):
    """The actual source fence alone; this fixture grants no execution authority."""
    import hashlib
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance

    result = Authority.__new__(Authority)
    result.repository = root
    result.review = {
        "source_files": [
            dict(
                path="src/invented.py",
                bytes=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(),
            )
        ]
    }
    result._deadline_check = lambda: None
    result._source_root_identity = s12_ra_g1_assurance.private_root_identity(root)
    result.charge_original = lambda calls, size: None
    result._source_verified = False
    return result


def test_real_source_fence_rejects_equal_content_internal_directory_alias(tmp_path):
    repo, outside = tmp_path / "repo", tmp_path / "outside"
    repo.mkdir(mode=0o700)
    outside.mkdir(mode=0o700)
    raw = b"# invented public source\n"
    (outside / "invented.py").write_bytes(raw)
    (repo / "src").symlink_to(outside, target_is_directory=True)
    authority = source_only_authority(repo, raw)
    with pytest.raises(c.Stage12Error, match="RA_G1_SOURCE_CHANGED"):
        authority.source_fence()
    assert not authority._source_verified


def test_real_source_fence_detects_midread_directory_alias_even_same_file_inode(
    tmp_path, monkeypatch
):
    import os
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_public

    repo, outside = tmp_path / "repo", tmp_path / "outside"
    repo.mkdir(mode=0o700)
    outside.mkdir(mode=0o700)
    inside = repo / "src"
    inside.mkdir(mode=0o700)
    raw = b"# invented public source\n"
    (inside / "invented.py").write_bytes(raw)
    os.link(inside / "invented.py", outside / "invented.py")
    authority = source_only_authority(repo, raw)
    authority.source_fence()
    old_read = os.read
    changed = []

    def replace_parent(fd, size):
        data = old_read(fd, size)
        if not changed:
            changed.append(True)
            inside.rename(repo / "original_src")
            inside.symlink_to(outside, target_is_directory=True)
        return data

    monkeypatch.setattr(s12_ra_g1_public.os, "read", replace_parent)
    with pytest.raises(c.Stage12Error, match="RA_G1_SOURCE_CHANGED"):
        authority.source_fence()
    assert not authority._source_verified


class SyntheticAuthority:
    test_only = True
    configuration_scope_sha256 = H

    def __init__(
        self, profile, plan, start, record, selected, rows, clock, *, reject=None
    ):
        self.profile, self.plan, self.start = deepcopy((profile, plan, start))
        self.record, self.selected = deepcopy(record), deepcopy(selected)
        self.configuration_scope_sha256 = record["configuration_scope_sha256"]
        self.rows, self.clock, self.reject = rows, clock, reject
        self.coordinator = None
        self.controls = ApplicationControls(selected, check=lambda: None)
        self.charges = 0

    def sampling_bound(self, profile, start):
        c.require(profile == self.profile and start == self.start)
        return deepcopy(self.record)

    def resource_facts(self, record):
        return facts()

    def initial_resource_facts(self, record):
        return facts()

    def resource_selection(self, record):
        return self.selected

    def capacity_observation(self, record):
        return capacity(self.selected)

    def charge_identity_check(self, record):
        self.charges += 1
        c.require(self.charges <= record["maximum_identity_checks"])

    def register_coordinator(self, coordinator):
        self.coordinator = coordinator
        coordinator.writer.allocation_controls = self.controls

    def resource_prewrite(self, *, next_write_bytes, next_creations):
        c.require(self.reject != "resource_prewrite", "SYNTHETIC_RESOURCE_DENIED")
        c.require(next_write_bytes > 0 and next_creations == 1)

    def require(self, purpose, identity, context):
        c.require(purpose != self.reject, "SYNTHETIC_SCOPE_DENIED")
        ctx = {"profile": self.profile, "plan": self.plan, "start": self.start}
        block_ctx = {"start": self.start, "block": self.plan["blocks"][0]}
        keys = {
            "resource_policy": "policy_sha256",
            "resource_adoption": "adoption_sha256",
            "resource_selection": "selection_sha256",
            "resource_technical_review": "technical_review_sha256",
            "resource_invocation_graph": "invocation_graph_sha256",
            "resource_risk_inventory": "risk_inventory_sha256",
            "owner_reported_project_approval": "owner_reported_project_approval_sha256",
        }
        if purpose in keys:
            c.require(identity == self.record[keys[purpose]] and context == ctx)
        elif purpose == "sampling_runtime_bound":
            c.require(identity == a.digest(self.record) and context == ctx)
        elif purpose == "sampling_bound_review":
            c.require(
                identity == self.record["technical_review_sha256"]
                and context == self.record
            )
        elif purpose in (
            "policy_freeze_record_sha256",
            "implementation_authorization_sha256",
            "implementation_review_sha256",
            "initial_workload_authority_sha256",
        ):
            c.require(identity == self.start[purpose] and context == ctx)
        elif purpose in ("segment_open", "writer_exclusion"):
            c.require(identity == H and context == block_ctx)
        elif purpose == "runtime_preflight":
            c.require(identity == H and context == ctx)
        elif purpose == "dispatch":
            c.require(
                identity == H
                and context["work"] in self.rows
                and context["attempt"] == 1
                and context["state"] in self.profile["states"]
            )
        elif purpose == "writer_release":
            c.require(
                identity == H
                and context["start"] == self.start
                and context["disposition"] in ("COMPLETED", "STOPPED")
            )
        elif purpose in ("operator_allowance", "transport_profile"):
            c.require(
                identity
                == (
                    self.profile["operator_allowance"]["record_sha256"]
                    if purpose == "operator_allowance"
                    else self.profile["transport_profile_sha256"]
                )
                and context == self.profile
            )
        elif purpose == "plan_selection":
            c.require(
                identity == self.plan["selection_basis_sha256"] and context == self.plan
            )
        elif purpose == "resources":
            c.require(
                identity == self.profile["resources"]["resource_review_sha256"]
                and context == self.profile["resources"]
            )
        elif purpose == "monitoring":
            c.require(
                identity == self.profile["monitoring"]["gaps_record_sha256"]
                and context == self.profile["monitoring"]
            )
        elif purpose == "rate_state":
            c.require(
                context in self.profile["states"]
                and identity == context["evidence_sha256"]
            )
        else:
            raise c.Stage12Error("SYNTHETIC_UNKNOWN_SCOPE")


def ra_inputs():
    p, pl, s, rows, inventory, _ = ap_inputs()
    selected = selection()
    selected["source_git_sha"] = s["client_git_sha"]
    selected["limits"].update(logical_write_bytes=2**30, creations=10000, attempts=10)
    selected["limits"]["stages"][0].update(logical_write_bytes=2**30, creations=10000)
    selected["limits"]["application_counters"] = {
        role: 10000 for role in selected["limits"]["application_counters"]
    }
    record = binding(selected)
    record.update(
        source_git_sha=s["client_git_sha"],
        runtime_inventory_sha256=a.digest(inventory),
        maximum_identity_checks=100000,
    )
    old = p["resources"]
    p["resources"] = dict(
        application_admission_memory_bytes=old["admission_memory_bytes"],
        requested_memory_bytes=6 * 2**30,
        logical_process_overhead_bytes=old["process_overhead_bytes"],
        logical_pending_request_bytes=old["pending_request_bytes"],
        per_attempt_logical_write_ceiling_bytes=old["per_attempt_disk_bound_bytes"],
        fixed_campaign_logical_write_ceiling_bytes=old[
            "fixed_campaign_disk_bound_bytes"
        ],
        task_logical_write_ceiling_bytes=old["allocated_disk_bytes"],
        resource_selection_sha256=a.digest(selected),
        initial_capacity_observation_sha256=a.digest(capacity(selected)),
        resource_review_sha256=old["resource_review_sha256"],
        scheduler_guard_ms=old["scheduler_guard_ms"],
        writer_guard_ms=5000,
    )
    p.update(
        schema_version=a.PROFILE,
        rule_bundle_sha256=a.RULE_BUNDLE,
        sampling_policy_sha256=a.POLICY_SHA,
        sampling_runtime_bound_sha256=a.digest(record),
        **a.assurance_fields(),
    )
    pl.update(
        schema_version=a.PLAN,
        operations_profile_sha256=a.digest(p),
        history_limits=dict(
            maximum_entries=100000,
            maximum_name_bytes=256,
            maximum_total_name_bytes=25600000,
            page_entries=8,
            maximum_depth=8,
            maximum_file_bytes=2**26,
        ),
    )
    s.update(
        schema_version=a.START,
        profile_sha256=a.digest(p),
        plan_sha256=a.digest(pl),
        rule_bundle_sha256=a.RULE_BUNDLE,
        sampling_policy_sha256=a.POLICY_SHA,
        **a.assurance_fields(),
    )
    return p, pl, s, record, selected, rows, inventory


@pytest.mark.parametrize("candidate_features", [[], [feature()]])
def test_actual_ra_data_path_reopens_without_strict_memory_claim(
    tmp_path, candidate_features
):
    p, pl, s, record, selected, rows, inventory = ra_inputs()
    clock = RealClock()
    authority = SyntheticAuthority(p, pl, s, record, selected, rows, clock)
    calls = []

    def dispatch(work, target, hooks):
        hooks.started(clock.now_ns())
        hooks.emit(lambda: None, lambda: None)
        calls.append(work["work_id"])
        raw = body(candidate_features)
        capture = t.Capture(
            "VALIDATION_REQUIRED",
            "OK",
            200,
            "application/json",
            "identity",
            None,
            raw,
            len(raw),
            1,
        )
        hooks.completed(capture)
        return capture

    report = cli.run_operations_block(
        p,
        pl,
        s,
        work_factory=lambda: iter(rows),
        output=tmp_path / "phase",
        block_id=1,
        authority=authority,
        clock=clock,
        dispatch=dispatch,
        runtime_inventory=inventory,
        runtime_key=KEY,
        control_adapters={},
        monitor=None,
        free_bytes=lambda: 2**40,
        segment_authority=H,
        writer_exclusion_evidence=H,
        epoch="1" * 64,
        writer_release_evidence=H,
        public_validation=Validation(),
        task_deadline_ns=clock.now_ns() + 180 * 10**9,
    )
    assert calls == [1, 2]
    assert report["report_complete"] and report["disposition"] == "COMPLETED"
    assert report["sampling_assurance_method"] == "LOGICAL_LIMITS_AND_SCOPED_MONITORING"
    assert (
        runtime.reopen_completed(
            tmp_path / "phase",
            p,
            pl,
            s,
            validation_sha256=a.digest(Validation().descriptor()),
        )
        == report["blocks"][0]
    )
    assert authority.coordinator.ra_charged_snapshot == (2, 0)


def test_ra_resource_barrier_refuses_before_dispatch(tmp_path):
    p, pl, s, record, selected, rows, inventory = ra_inputs()
    clock = RealClock()
    authority = SyntheticAuthority(
        p, pl, s, record, selected, rows, clock, reject="resource_prewrite"
    )
    calls = []
    report = cli.run_operations_block(
        p,
        pl,
        s,
        work_factory=lambda: iter(rows),
        output=tmp_path / "denied",
        block_id=1,
        authority=authority,
        clock=clock,
        dispatch=lambda *x: calls.append(x),
        runtime_inventory=inventory,
        runtime_key=KEY,
        control_adapters={},
        monitor=None,
        free_bytes=lambda: 2**40,
        segment_authority=H,
        writer_exclusion_evidence=H,
        epoch="1" * 64,
        writer_release_evidence=H,
        public_validation=Validation(),
        task_deadline_ns=clock.now_ns() + 180 * 10**9,
    )
    assert not calls and not report["report_complete"]
