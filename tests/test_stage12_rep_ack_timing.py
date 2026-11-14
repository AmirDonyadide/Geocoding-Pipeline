"""Small real ACK-policy/T3 lifecycle; synthetic facts, no native readiness."""

from copy import deepcopy
import json
from pathlib import Path
import threading
import time

import pytest

from test_stage12_public_operations_v2 import FakeClock, H, offline  # noqa: F401
from test_stage12_rep_ack_queue import selected_inputs
from safe_geocoding_pipeline.preprocessing.stages import s12_public_checkpoints as cp
from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as journal
from safe_geocoding_pipeline.preprocessing.stages import s12_public_sampling as sampling
from safe_geocoding_pipeline.preprocessing.stages import s12_public_scheduler as scheduler
from safe_geocoding_pipeline.preprocessing.stages import s12_public_timing as timing
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_rep_ack_contract as rep
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_timing as compact


ROOT = Path(__file__).resolve().parents[1]
BINDING = dict(policy_sha256=rep.POLICY_SHA, source_sha256=H, task_sha256=H)


def observer_at(root, clock, *, policy=rep.POLICY_VERSION, binding=None, **limits):
    return timing.SamplingTiming(
        root,
        phase_count=1,
        timing_schema=cp.RA_SCHEMA,
        timing_policy_version=policy,
        timing_binding=BINDING if binding is None else binding,
        phase_windows=[dict(phase_id=1, selected_phase_ms=20000)],
        cumulative_deadline_ns=100_000_000_000,
        clock_ns=clock.now_ns,
        **limits,
    )


def test_closed_policy_constants_caps_and_legacy_descriptor_bytes():
    assert compact.RA_ACK_POLICY == rep.POLICY_VERSION
    assert compact.RA_ACK_POLICY_SHA256 == rep.POLICY_SHA
    assert rep.POLICY["maximum_unacknowledged_age_ms"] is None
    assert compact.selected_max_files(cp.RA_SCHEMA, rep.POLICY_VERSION) == 2980
    assert compact.selected_max_files(cp.RA_SCHEMA, compact.RA_POLICY) == 2980
    assert compact.selected_max_files(cp.RA_SCHEMA, compact.RA_PROTECTED_POLICY) == 1500
    assert compact.selected_max_files(cp.WF_SCHEMA, compact.POLICY_VERSION) == 1500
    assert (compact.HEADER_BYTES, compact.ROW_BYTES, compact.CHUNK_ROWS) == (4096, 512, 56)
    assert (compact.MAX_BYTES, compact.TIMER_NS) == (32768, 5_000_000_000)
    original = ROOT / "docs/scientific_assets/stage12_public_path_timing_v3.json"
    assert compact.descriptor() == json.loads(original.read_bytes())


@pytest.mark.parametrize(
    "schema,policy,digest",
    [
        (cp.RA_SCHEMA, rep.POLICY_VERSION, H),
        (cp.RA_SCHEMA, compact.RA_POLICY, rep.POLICY_SHA),
        (cp.RA_SCHEMA, compact.RA_PROTECTED_POLICY, rep.POLICY_SHA),
        (cp.WF_SCHEMA, rep.POLICY_VERSION, rep.POLICY_SHA),
        (cp.WF_SCHEMA, compact.POLICY_VERSION, rep.POLICY_SHA),
        (cp.RA_SCHEMA, "UNKNOWN_POLICY", rep.POLICY_SHA),
    ],
)
def test_mixed_family_or_hash_rejected_before_reservation_or_creation(
    tmp_path, schema, policy, digest
):
    charges = []
    binding = dict(BINDING, policy_sha256=digest)
    with pytest.raises(cp.CheckpointError, match="CHECKPOINT_BINDING_INVALID"):
        timing.SamplingTiming(
            tmp_path / "observer",
            phase_count=1,
            timing_schema=schema,
            timing_binding=binding,
            timing_policy_version=policy,
            phase_windows=[dict(phase_id=1, selected_phase_ms=20000)],
            cumulative_deadline_ns=100_000_000_000,
            budget_charge=charges.append,
        )
    assert not charges and not (tmp_path / "observer").exists()
    with pytest.raises(cp.CheckpointError, match="CHECKPOINT_BINDING_INVALID"):
        compact.Checkpoints(
            tmp_path / "writer",
            timing_schema=schema,
            timing_binding=binding,
            timing_policy_version=policy,
            phase_windows=[dict(phase_id=1, selected_phase_ms=20000)],
            cumulative_deadline_ns=100_000_000_000,
        )
    assert not (tmp_path / "writer").exists()


def test_existing_ra_numerical_ceiling_cannot_be_enlarged(tmp_path):
    clock = FakeClock()
    observer = observer_at(tmp_path / "at_cap", clock, max_files=2980)
    assert observer.checkpoints is not None
    assert observer.close(timeout_seconds=2)["persistence_complete"]
    with pytest.raises(cp.CheckpointError, match="CHECKPOINT_LIMIT_INVALID"):
        compact.Checkpoints(
            tmp_path / "over_cap",
            timing_schema=cp.RA_SCHEMA,
            timing_binding=BINDING,
            timing_policy_version=rep.POLICY_VERSION,
            phase_windows=[dict(phase_id=1, selected_phase_ms=20000)],
            cumulative_deadline_ns=100_000_000_000,
            max_files=2981,
        )
    assert not (tmp_path / "over_cap").exists()


def test_real_sampler_delayed_ack_t3_durability_association_and_fresh_reopening(
    offline, tmp_path, monkeypatch
):
    clock = FakeClock()
    p, plan, start, authority = selected_inputs(rep, clock)
    observer = observer_at(tmp_path / "timing", clock, max_files=2980)
    observer.phase_open(1, phase_deadline_ns=20_000_000_000, timeout_seconds=2)
    entered, returned = threading.Event(), threading.Event()
    persistence = {}
    original_write = journal.io.write

    def delayed(path, raw):
        if (
            not entered.is_set()
            and path.parent.name == "events"
            and b'"kind":"RESOURCE_SAMPLE"' in raw
        ):
            persistence["enter_wall_ns"] = time.monotonic_ns()
            entered.set()
            time.sleep(0.7)
            value = original_write(path, raw)
            persistence["return_wall_ns"] = time.monotonic_ns()
            returned.set()
            return value
        return original_write(path, raw)

    monkeypatch.setattr(journal.io, "write", delayed)
    co = None
    released = False
    try:
        co = scheduler.Coordinator(
            p, plan, start, authority=authority, clock=clock,
            root=tmp_path / "run", block_id=1, segment_authority=H,
            writer_exclusion_evidence=H, epoch=H, free_bytes=lambda: 2**42,
            contract=rep, timing_observer=observer,
        )
        sampler = co.ap_sampler
        clock.advance(50_000_000)
        assert entered.wait(1)
        for target in range(100_000_000, 701_000_000, 50_000_000):
            clock.advance(target - clock.now_ns())
            end = time.monotonic() + 0.025
            while (
                co.last_sample_ns < target and sampler.failure is None
                and time.monotonic() < end
            ):
                time.sleep(0.001)
        assert sampler.failure is None and co._sampling_gate() is True
        assert sampler.occupied <= 16 and sampler.maximum_gap <= 100_000_000
        assert returned.wait(1)
        with sampler.condition:
            assert sampler.condition.wait_for(
                lambda: sampler.witnessed == sampler.acquired and sampler.occupied == 0,
                timeout=1,
            )
        clock.advance(1)
        closed = sampler.close()
        assert closed["result"] == "COMPLETE" and sampler.maximum_age > 500_000_000
        co.writer.release(dict(scope="TEST_ONLY_T3_CONNECTED", scientific_pass=False))
        released = True
        observer.phase_close(1, timeout_seconds=2)
        snapshot = observer.close(timeout_seconds=2)
        assert snapshot["persistence_complete"] and snapshot["observer_failure_count"] == 0
        assert not co.writer.thread.is_alive() and not sampler.thread.is_alive()
        assert not observer.checkpoints._thread.is_alive()

        events = list(journal.read_events(tmp_path / "run", rep.digest(start), contract=rep))
        segments = sampling.inspect(lambda: iter(events), p, start, maximum_segments=1, contract=rep)
        assert len(segments) == 1 and segments[0]["complete"]
        by_seq = {event["seq"]: event for event in events}
        rows = []

        def associate(_ordinal, row):
            if row["row_kind"] == "PERIODIC_ASYNC":
                event = by_seq[row["sample_event_seq"]]
                ack = by_seq[row["ack_event_seq"]]
            else:
                hard = dict(zip(cp.PUBLIC_FIELDS, row["legacy_row"], strict=True))
                event, ack = by_seq[hard["event_seq"]], None
            timing.verify_sampling_association(
                row, event, phase_id=1, ack_event=ack, contract=rep
            )
            rows.append(row)

        reopened = cp.read_prefix(
            observer.checkpoints.root, timing_schema=cp.RA_SCHEMA, max_files=2980,
            expected_binding=BINDING, expected_snapshot=snapshot["checkpoint"],
            record_consumer=associate,
        )
        assert not reopened["incomplete"]
        assert reopened["last_payload"]["policy_version"] == rep.POLICY_VERSION
        assert reopened["last_payload"]["policy_sha256"] == rep.POLICY_SHA
        asynchronous = [row for row in rows if row["row_kind"] == "PERIODIC_ASYNC"]
        assert len(asynchronous) == sampler.witnessed
        assert max(row["event_ack_publish_ns"] - row["observed_ns"] for row in asynchronous) > 500_000_000
        assert reopened["verified_rows"] == snapshot["checkpoint"]["observed_rows"] == len(rows)
        assert reopened["sampling_coverage_proof"] is False

        # Both metadata and substantive association remain required at reopening.
        for key in ("policy_sha256", "source_sha256", "task_sha256"):
            bad = dict(BINDING, **{key: "1" * 64})
            assert cp.read_prefix(
                observer.checkpoints.root, timing_schema=cp.RA_SCHEMA, max_files=2980,
                expected_binding=bad, expected_snapshot=snapshot["checkpoint"],
            )["incomplete"]
        assert cp.read_prefix(
            observer.checkpoints.root, timing_schema=cp.WF_SCHEMA,
            expected_binding=BINDING, expected_snapshot=snapshot["checkpoint"],
        )["incomplete"]
        assert cp.read_prefix(
            observer.checkpoints.root, timing_schema=cp.RA_SCHEMA, max_files=2980,
            expected_binding=BINDING,
        )["incomplete"]  # A final byte marker alone is not durable acceptance.
        row = asynchronous[0]
        bad_ack = deepcopy(by_seq[row["ack_event_seq"]])
        bad_ack["body"]["sample_event_sha256"] = H
        with pytest.raises(c.Stage12Error):
            timing.verify_sampling_association(
                row, by_seq[row["sample_event_seq"]], phase_id=1,
                ack_event=bad_ack, contract=rep,
            )

        header = reopened["last_payload"]
        for changes in (
            {"policy_sha256": H}, {"policy_version": compact.RA_POLICY},
            {"policy_version": compact.RA_PROTECTED_POLICY},
        ):
            changed = dict(header, **changes)
            with pytest.raises(cp.CheckpointError, match="CHECKPOINT_BINDING_INVALID"):
                compact.validate_policy_binding(
                    changed["policy_version"],
                    {key: changed[key] for key in compact._BINDING},
                    schema=cp.RA_SCHEMA,
                )
            # The existing wire decoder deliberately maps validation faults to
            # CHECKPOINT_CANONICAL_INVALID; preserve that original precedence.
            with pytest.raises(cp.CheckpointError, match="CHECKPOINT_CANONICAL_INVALID"):
                compact.decode_header(compact.encode_header(changed), schema=cp.RA_SCHEMA)
        observed = dict(
            scope="TEST_ONLY_REAL_SAMPLER_AND_T3", policy_version=rep.POLICY_VERSION,
            policy_sha256=rep.POLICY_SHA, timing_schema=cp.RA_SCHEMA,
            maximum_ack_age_ns=sampler.maximum_age, maximum_entry_gap_ns=sampler.maximum_gap,
            acquired=sampler.acquired, witnessed=sampler.witnessed,
            sampling_close=closed, snapshot=snapshot, reopened=reopened,
            full_t3_row_associations=len(rows), persistence=persistence,
            native_readiness=False, scientific_pass=False, full_selected_fixture=False,
        )
        path = tmp_path / "CONNECTED_OBSERVATIONS.record"
        path.write_bytes(c.canonical(observed))
        path.chmod(0o600)
    finally:
        if co is not None and not released:
            co.writer.abort()
        if not observer.closed:
            observer.close(timeout_seconds=2)
    assert persistence["return_wall_ns"] - persistence["enter_wall_ns"] >= 700_000_000
