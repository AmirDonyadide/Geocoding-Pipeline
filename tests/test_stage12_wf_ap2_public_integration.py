"""One bounded public AP2 author integration, invented transport and M2 only.

Each phase is submitted once. Missed timing/closure gates are test failures,
never a reason to loop for a favorable real-clock outcome. Bodies are <=64KiB;
the complete module permits at most12 attempted invented exchanges.
"""

from copy import deepcopy
import shutil

import pytest

from stage12_synthetic import body
from test_stage12_public_operations_v2 import H, KEY, offline  # noqa: F401
from test_stage12_public_operational_audit import Control, recipe
from test_stage12_public_sampling_contract import ap_inputs
from test_stage12_public_sampling_integration import RealClock
from test_stage12_wf_ap2_assurance import SyntheticAuthority, m2_inputs, repin
from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
from safe_geocoding_pipeline.preprocessing.stages import s12_public_checkpoints as cp
from safe_geocoding_pipeline.preprocessing.stages import s12_public_diagnostics as diag
from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as journal
from safe_geocoding_pipeline.preprocessing.stages import s12_public_matrix as matrix
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_public_response as validation,
)
from safe_geocoding_pipeline.preprocessing.stages import s12_public_runtime as runtime
from safe_geocoding_pipeline.preprocessing.stages import s12_public_timing as timing
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from safe_geocoding_pipeline.preprocessing.stages import s12_transport as transport
from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_assurance as m
from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_contract as a


_ATTEMPTS = 0


class IntegrationAuthority(SyntheticAuthority):
    """Exact finite synthetic workload extension, with no actual runtime grant."""

    def __init__(self, profile, plan, start, record, work, clock):
        super().__init__(profile, plan, start, record)
        self.clock, self.work = clock, deepcopy(work)
        block = plan["blocks"][0]
        self.expected.update(
            segment_open=(H, dict(start=start, block=block)),
            writer_exclusion=(H, dict(start=start, block=block)),
            runtime_preflight=(
                start["initial_workload_authority_sha256"],
                dict(profile=profile, plan=plan, start=start),
            ),
        )

    def require(self, purpose, digest, context):
        if purpose == "dispatch":
            c.require(
                self.record["evidence_origin"] == "SYNTHETIC_TEST_ONLY"
                and digest == self.start["initial_workload_authority_sha256"]
                and type(context) is dict
                and set(context) == {"work", "attempt", "state"}
                and context["work"] in self.work
                and context["attempt"] == 1
                and context["state"] == self.profile["states"][0],
                "SYNTHETIC_DISPATCH_SCOPE_DENIED",
            )
            self.calls.append(purpose)
        elif purpose == "writer_release":
            c.require(
                digest == H
                and context
                in [
                    dict(start=self.start, disposition=disposition)
                    for disposition in ("COMPLETED", "STOPPED")
                ],
                "SYNTHETIC_RELEASE_SCOPE_DENIED",
            )
            self.calls.append(purpose)
        else:
            super().require(purpose, digest, context)


def inputs(*, control):
    profile, plan, start, record, _ = m2_inputs()
    _, _, _, work, inventory, _ = ap_inputs()
    adapters = {}
    if control:
        adapters[1] = Control()
        plan["control_recipes"] = [recipe()]
        work.append(
            dict(
                work_id=3,
                block_id=1,
                kind="SERVICE_CONTROL",
                fixture_id=None,
                result_limit=None,
                repetition=None,
                recipe_id=1,
                retry_spacing_key=H,
            )
        )
        plan["blocks"][0]["observation_ids"].append(3)
        for budget in (plan["budgets"], plan["blocks"][0]["budget"]):
            budget["required_control_observations"] = 1
            budget["control_http_attempts"] = 5
    plan["work_manifest_sha256"] = a.manifest_digest(work)
    # A finite test record, selected before any producer starts. This is not a
    # native allocation proof or actual kernel-domain evidence.
    record["maximum_enforcement_checks"] = 4096
    repin(profile, plan, start, record)
    return profile, plan, start, record, work, inventory, adapters


def run_once(tmp_path, *, control=False):
    profile, plan, start, record, work, inventory, adapters = inputs(control=control)
    clock = RealClock()
    deadline = clock.now_ns() + 180_000_000_000
    binding = dict(
        policy_sha256=a.POLICY_SHA, source_sha256=H, task_sha256=a.digest(plan)
    )
    observer = timing.SamplingTiming(
        tmp_path / "timing",
        phase_count=1,
        timing_schema=cp.WF_SCHEMA,
        timing_binding=binding,
        timing_policy_version=a.POLICY_VERSION,
        phase_windows=[
            dict(phase_id=1, selected_phase_ms=plan["budgets"]["active_duration_ms"])
        ],
        cumulative_deadline_ns=deadline,
        clock_ns=clock.now_ns,
    )
    authority = IntegrationAuthority(profile, plan, start, record, work, clock)

    class FailureSites(diag.Failures):
        def __init__(self):
            super().__init__(clock)
            self.sites = []

        def record(self, stage, error, **kwargs):
            super().record(stage, error, **kwargs)
            with self.lock:
                if len(self.sites) < 4:
                    sites, tb = [], error.__traceback__
                    while tb is not None and len(sites) < 16:
                        sites.append(
                            (
                                tb.tb_frame.f_code.co_filename.rsplit("/", 1)[-1],
                                tb.tb_lineno,
                            )
                        )
                        tb = tb.tb_next
                    self.sites.append((stage, sites))

    diagnostics = FailureSites()
    attempted = []

    def dispatch(selected, target, hooks):
        global _ATTEMPTS
        _ATTEMPTS += 1
        assert _ATTEMPTS <= 12
        assert selected in work and type(target) is bytes
        attempted.append((selected["work_id"], selected["kind"]))
        hooks.started(clock.now_ns())
        hooks.emit(lambda: None, lambda: None)
        raw = (
            c.canonical({"synthetic_index": "test"})
            if selected["kind"] == "SERVICE_CONTROL"
            else body([])
        )
        assert len(raw) <= 65536
        capture = transport.Capture(
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

    observer.phase_open(1, phase_deadline_ns=deadline, timeout_seconds=5)
    result = cli.run_operations_block(
        profile,
        plan,
        start,
        work_factory=lambda: iter(work),
        output=tmp_path / "run",
        block_id=1,
        authority=authority,
        clock=clock,
        dispatch=dispatch,
        runtime_inventory=inventory,
        runtime_key=KEY,
        control_adapters=adapters,
        monitor=None,
        free_bytes=lambda: 2**42,
        segment_authority=H,
        writer_exclusion_evidence=H,
        epoch=H,
        writer_release_evidence=H,
        task_deadline_ns=deadline,
        diagnostics=diagnostics,
        public_validation=validation.Validation(),
        timing_observer=observer,
    )
    quiescent = bool(
        result.get("sampling_segments")
        and all(row["complete"] for row in result["sampling_segments"])
    )
    observer.phase_close(1, quiescent=quiescent, timeout_seconds=5)
    timing_summary = observer.close(timeout_seconds=5)
    io.write(
        tmp_path / "author_diagnostics.json",
        c.canonical(
            dict(
                result=result,
                timing=timing_summary,
                diagnostic=diagnostics.snapshot(),
                safe_failure_sites=diagnostics.sites,
                attempted=attempted,
            )
        ),
    )
    return dict(
        profile=profile,
        plan=plan,
        start=start,
        record=record,
        result=result,
        root=tmp_path / "run",
        observer=observer,
        timing_summary=timing_summary,
        binding=binding,
        attempted=attempted,
        adapters=adapters,
        authority=authority,
    )


def test_real_public_ap2_capture_reopen_t3_and_rejected_source_mutations(tmp_path):
    value = run_once(tmp_path, control=True)
    verify_completed_capture(tmp_path, value)


def verify_completed_capture(tmp_path, value):
    """Read-only original verification plus mutations of separate synthetic copies.

    This also permits the author to reuse a completed immutable phase after an
    opener-only source repair, without another invented provider attempt.
    """
    profile, plan, start, result, root = (
        value[key] for key in ("profile", "plan", "start", "result", "root")
    )
    assert result["schema_version"] == a.REPORT
    assert result["sampling_assurance_method"] == m.METHOD
    failure = io.metadata(io.read(tmp_path / "author_diagnostics.json"))
    assert result["report_complete"], {
        key: failure[key] for key in ("diagnostic", "safe_failure_sites", "attempted")
    }
    assert sorted(value["attempted"]) == [
        (1, "DATA"),
        (2, "DATA"),
        (3, "SERVICE_CONTROL"),
    ]
    assert result["disposition"] == "COMPLETED"
    assert (
        runtime.reopen_completed(
            root, profile, plan, start, control_adapters=value["adapters"]
        )
        == result["blocks"][0]
    )
    snapshot = a.parse(io.read(root / "snapshot.json"), a.SNAPSHOT)
    assert snapshot["sampling_assurance_method"] == m.METHOD
    assert (root / "_SEGMENT_SEALED").exists() and (
        root / "_WRITER_RELEASED.json"
    ).exists()
    assert result["campaign_counts"]["durable_valid_data"]["value"] == 2
    assert result["campaign_counts"]["control_attempt_starts"]["value"] == 1
    assert len(list(journal.read_array(root / "repeat_comparison.json"))) == 1

    selected = []
    prefix = cp.read_prefix(
        tmp_path / "timing",
        expected_binding=value["binding"],
        expected_snapshot=value["timing_summary"]["checkpoint"],
        record_consumer=lambda ordinal, row: selected.append(row),
    )
    assert not prefix["incomplete"] and selected
    assert value["timing_summary"]["persistence_complete"]
    assert value["timing_summary"]["final_timing_coverage_complete"]
    # This tiny fixture has bounded source membership; each original lookup
    # still reopens and parses the source directly, never trusts a cached event.
    seen = set()
    for row in selected:
        if row["row_kind"] == "PERIODIC_ASYNC":
            event = a.parse(
                io.read(root / "events" / f"{row['sample_event_seq']:020d}.json"),
                a.EVENT,
            )
            ack = a.parse(
                io.read(root / "events" / f"{row['ack_event_seq']:020d}.json"), a.EVENT
            )
            timing.verify_sampling_association(
                row, event, phase_id=1, ack_event=ack, contract=a
            )
        else:
            seq = row["legacy_row"][4]
            event = a.parse(io.read(root / "events" / f"{seq:020d}.json"), a.EVENT)
            timing.verify_sampling_association(row, event, phase_id=1, contract=a)
        seen.add(row["row_kind"])
    assert seen == {"PERIODIC_ASYNC", "HARD_SYNC"}
    assert all(
        event["schema_version"] == a.EVENT for event in matrix._events(root, start)
    )

    for mutation in (
        "source_bytes",
        "missing_closure",
        "missing_method",
        "wrong_event_family",
    ):
        copied = tmp_path / mutation
        shutil.copytree(root, copied)
        if mutation == "source_bytes":
            path = next((copied / "events").iterdir())
            with path.open("ab") as stream:
                stream.write(b" ")
        elif mutation == "missing_closure":
            closed = next(
                event
                for event in journal.read_events(copied, a.digest(start), contract=a)
                if event["kind"] == "SAMPLING_CLOSE"
            )
            (copied / "events" / f"{closed['seq']:020d}.json").unlink()
        elif mutation == "missing_method":
            changed = io.metadata(io.read(copied / "snapshot.json"))
            changed.pop("sampling_assurance_method")
            (copied / "snapshot.json").write_bytes(c.canonical(changed))
        else:
            path = next((copied / "events").iterdir())
            changed = io.metadata(io.read(path))
            changed["schema_version"] = "stage12_public_controller_event_v2"
            path.write_bytes(c.canonical(changed))
            with pytest.raises(c.Stage12Error):
                list(matrix._events(copied, start))
        with pytest.raises(c.Stage12Error):
            runtime.reopen_completed(
                copied, profile, plan, start, control_adapters=value["adapters"]
            )


def test_uncertain_public_ap2_writer_retains_failed_closure_and_timing(
    tmp_path, monkeypatch
):
    original = journal.Journal._readback
    fired = []

    def readback(self, path, raw):
        if not fired and path.parent.name == "events" and b'"kind":"SAMPLE_ACK"' in raw:
            fired.append(True)
            raise OSError(5, "SYNTHETIC_TEST_ONLY")
        return original(self, path, raw)

    monkeypatch.setattr(journal.Journal, "_readback", readback)
    value = run_once(tmp_path)
    assert fired
    assert len(value["attempted"]) <= 2
    assert not value["result"]["report_complete"]
    assert not (value["root"] / "_WRITER_RELEASED.json").exists()
    assert not (value["root"] / "_SEGMENT_SEALED").exists()
    assert not value["timing_summary"]["final_timing_coverage_complete"]
    assert value["timing_summary"]["partial_timing_rows"] > 0
    with pytest.raises(c.Stage12Error):
        runtime.reopen_completed(
            value["root"], value["profile"], value["plan"], value["start"]
        )


def test_genuine_public_runtime_authority_rejects_test_record_before_provider(
    tmp_path, monkeypatch
):
    profile, plan, start, record, work, inventory, adapters = inputs(control=False)
    clock = RealClock()
    bundle = tmp_path / "bundle"
    io.reserve(bundle)
    io.reserve(bundle / "sampling_evidence")
    records = {}

    def add(value):
        digest = a.digest(value)
        records[digest] = value
        return digest

    roles = {
        name: add({"synthetic_test_only": name})
        for name in ("methods", "logical", "enforcement", "coverage", "graphs")
    }
    record.update(
        method_evidence_sha256=[roles["methods"]],
        enforcement_evidence_sha256=roles["enforcement"],
        domain_coverage_evidence_sha256=roles["coverage"],
        invocation_graph_sha256=roles["graphs"],
    )
    for allocation in record["logical_allocations"]:
        allocation["evidence_sha256"] = roles["logical"]
    config = dict(
        version=runtime.AP2_CONFIG,
        window_start=plan["window_start"],
        window_end=plan["window_end"],
        sources={},
        campaigns=[dict(profile=profile, plan=plan, work=work)],
    )
    record["configuration_scope_sha256"] = m.configuration_scope(config)
    subject = dict(record)
    subject.pop("technical_review_record_sha256")
    review_record = dict(
        version="stage12_wf_ap2_bound_review_v1",
        scope=a.SCOPE,
        disposition="PASS",
        bound_scope_sha256=a.digest(subject),
        reviewer_role_evidence_sha256=roles["methods"],
    )
    review_digest = add(review_record)
    record["technical_review_record_sha256"] = review_digest
    repin(profile, plan, start, record)
    bound_digest = add(record)
    assert bound_digest == profile["sampling_runtime_bound_sha256"]
    assert record["configuration_scope_sha256"] == m.configuration_scope(config)
    for digest, value in records.items():
        io.write(
            bundle / "sampling_evidence" / (digest + ".record"), c.canonical(value)
        )
    report = b"SYNTHETIC TEST ONLY - DOES NOT ISSUE LIVE AUTHORITY"
    io.write(bundle / "integration_review.md", report)
    source = tmp_path / "synthetic_source.py"
    source.write_bytes(b"# SYNTHETIC_TEST_ONLY\n")
    review = dict(
        version="stage12_wf_ap2_public_review_binding_v1",
        scope=a.SCOPE,
        disposition="PASS",
        configuration_sha256=a.digest(config),
        report_sha256=c.sha(report).hex(),
        source_files=[dict(path=source.name, sha256=c.sha(source.read_bytes()).hex())],
        sampling_evidence={
            **{name: [digest] for name, digest in roles.items()},
            "runtime_bounds": [bound_digest],
            "technical_reviews": [review_digest],
        },
    )
    authority = runtime.Authority(
        config, bundle, review, H, tmp_path, start["client_git_sha"], clock
    )
    assert authority.test_only is False
    reached = []

    def denied(*args, **kwargs):
        reached.append(True)
        raise AssertionError("TEST_ONLY_RECORD_REACHED_PROVIDER")

    monkeypatch.setattr(m, "observe_linux_domain", denied)
    with pytest.raises(c.Stage12Error, match="WF_AP2_TEST_AUTHORITY_DENIED"):
        cli.run_operations_block(
            profile,
            plan,
            start,
            work_factory=denied,
            output=tmp_path / "never_created",
            block_id=1,
            authority=authority,
            clock=clock,
            dispatch=denied,
            runtime_inventory=inventory,
            runtime_key=KEY,
            control_adapters=adapters,
            monitor=None,
            free_bytes=denied,
            segment_authority=H,
            writer_exclusion_evidence=H,
            epoch=H,
            writer_release_evidence=H,
        )
    assert not reached and not (tmp_path / "never_created").exists()


def test_public_ap2_matrix_metadata_projection_preserves_exact_families_and_limits():
    from test_stage12_public_matrix import configuration

    config = configuration()
    config["version"] = a.CONFIG
    for item in config["campaigns"]:
        profile, plan = item["profile"], item["plan"]
        profile.pop("resource_sample_period_ms")
        profile.update(
            schema_version=a.PROFILE,
            rule_bundle_sha256=a.RULE_BUNDLE,
            sampling_policy_sha256=a.POLICY_SHA,
            sampling_runtime_bound_sha256=H,
            **a.assurance_fields(),
        )
        duration = 300000 if plan["budgets"]["data_observations"] else 180000
        # Explicit synthetic metadata selection, no execution/throughput claim.
        for budget in (plan["budgets"], plan["blocks"][0]["budget"]):
            budget.update(active_duration_ms=duration, event_count=20000)
        observations = (duration + 49) // 50 + 2
        members = 4 * observations + 8
        plan.update(
            schema_version=a.PLAN,
            operations_profile_sha256=a.digest(profile),
            history_limits=dict(
                maximum_entries=100000,
                maximum_name_bytes=256,
                maximum_total_name_bytes=25600000,
                page_entries=8,
                maximum_depth=8,
                maximum_file_bytes=2**26,
            ),
            sampling_budget=dict(
                maximum_segments=1,
                maximum_observations=observations,
                maximum_inventory_versions_per_segment=8,
                additional_event_tokens=2 * observations + 4,
                additional_file_data_bytes=4096 * members + 8 * (512 * members + 4096),
                additional_file_entries=members + 8,
            ),
        )
    result = matrix.validate_matrix(config)
    assert result["attempts"] == 2920 and result["events"] == 220000
    for mutation in ("old_profile", "method", "history"):
        changed = deepcopy(config)
        item = changed["campaigns"][0]
        if mutation == "old_profile":
            item["profile"]["schema_version"] = "stage12_transport_operations_v3"
        elif mutation == "method":
            item["profile"]["sampling_assurance_method"] = "CLOSED_ALLOCATION_INVENTORY"
        else:
            item["plan"]["history_limits"]["page_entries"] = 513
        with pytest.raises(c.Stage12Error):
            matrix.validate_matrix(changed)
