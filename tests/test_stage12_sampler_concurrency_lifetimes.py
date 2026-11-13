"""Bounded actual sampler/writer paths; invented authority, no provider work."""

import json
from pathlib import Path
import threading
import time

import pytest

from test_stage12_public_operations_v2 import FakeClock, H, offline  # noqa: F401
from test_stage12_public_sampling import component
from test_stage12_wf_ap2_public_integration import inputs, IntegrationAuthority
from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as journal
from safe_geocoding_pipeline.preprocessing.stages import s12_public_sampling as sampling
from safe_geocoding_pipeline.preprocessing.stages import s12_public_scheduler as scheduler
from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_contract as contract
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c


def retain(path, value):
    path.write_bytes(c.canonical(value))
    path.chmod(0o600)


def successor_inputs(family, clock):
    if family == "M2":
        profile, plan, start, record, work, _, _ = inputs(control=False)
        authority = IntegrationAuthority(profile, plan, start, record, work, clock)
        return profile, plan, start, authority, contract
    from test_stage12_ra_g1_integration import ra_inputs, SyntheticAuthority
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_contract
    assert family == "RA"
    profile, plan, start, record, selected, work, _ = ra_inputs()
    authority = SyntheticAuthority(profile, plan, start, record, selected, work, clock)
    return profile, plan, start, authority, s12_ra_g1_contract


def test_health_clock_read_is_serialized_with_acquisition_commit(tmp_path):
    sampler, co, _, _ = component()
    read_entered, allow_read_return = threading.Event(), threading.Event()
    committed = threading.Event()

    class InterleavingClock:
        value = 0
        paused = False

        def now_ns(self):
            result = self.value
            if threading.current_thread().name == "TEST_ONLY_HEALTH" and not self.paused:
                self.paused = True
                read_entered.set()
                assert allow_read_return.wait(1)
            return result

    clock = InterleavingClock()
    sampler.clock = co.clock = clock
    errors = []

    def health():
        try:
            sampler.health(caller_context="COORDINATOR_SNAPSHOT")
        except BaseException as error:
            errors.append(type(error).__name__)

    def acquire():
        sampler.owner_ident = threading.get_ident()
        clock.value = 1
        if sampler.acquire():
            committed.set()

    checking = threading.Thread(target=health, name="TEST_ONLY_HEALTH")
    acquiring = threading.Thread(target=acquire, name="TEST_ONLY_ACQUIRE")
    checking.start()
    assert read_entered.wait(1)
    acquiring.start()
    committed_during_paused_read = committed.wait(0.03)
    allow_read_return.set()
    for thread in (checking, acquiring):
        thread.join(1)
        assert not thread.is_alive()
    result = dict(scope="TEST_ONLY_ACTUAL_HEALTH_AND_ACQUIRE",
        clock_read_paused=True, committed_during_paused_read=committed_during_paused_read,
        acquired=sampler.acquired, failure=sampler.failure, first_fault=sampler.first_fault,
        thread_errors=errors, both_threads_joined=True, historical_cause="UNKNOWN")
    retain(tmp_path / "health-interleaving.json", result)
    assert not errors and committed.is_set()
    assert sampler.failure is None, result
    assert not committed_during_paused_read


@pytest.mark.parametrize("health_time,expected", [
    (-1, "CLOCK_INVALID"), (100_000_000, None), (100_000_001, "ACQUISITION_GAP")])
def test_genuine_clock_regression_and_inclusive_freshness_remain(health_time, expected):
    sampler, _, _, clock = component()
    clock.value = health_time
    sampler.health()
    assert sampler.failure == expected


@pytest.mark.parametrize("family", ["M2", "RA"])
def test_real_successor_writer_200ms_persistence_does_not_block_acquisition(
    offline, tmp_path, monkeypatch, family
):
    # Clock advances are selected explicitly; the actual writer really blocks
    # in persistence for200ms. Neither fixture clock nor authority is native.
    clock = FakeClock()
    profile, plan, start, authority, wire = successor_inputs(family, clock)
    entered, persisted = threading.Event(), threading.Event()
    timing = {}
    original_write = journal.io.write

    def delayed_write(path, raw):
        if (not entered.is_set() and path.parent.name == "events"
                and b'"kind":"RESOURCE_SAMPLE"' in raw):
            timing["persist_enter_ns"] = clock.now_ns()
            timing["persist_enter_wall_ns"] = time.monotonic_ns()
            from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_scratch
            timing["writer_scratch_at_persistence"] = sorted(
                getattr(s12_wf_ap2_scratch._local, "occupied", ()))
            timing["sample_header"] = json.loads(raw)
            entered.set()
            time.sleep(0.2)
            result = original_write(path, raw)
            timing["persist_return_ns"] = clock.now_ns()
            timing["persist_return_wall_ns"] = time.monotonic_ns()
            persisted.set()
            return result
        return original_write(path, raw)

    monkeypatch.setattr(journal.io, "write", delayed_write)
    co = scheduler.Coordinator(profile, plan, start, authority=authority, clock=clock,
        root=tmp_path / "run", block_id=1, segment_authority=H,
        writer_exclusion_evidence=H, epoch=H, free_bytes=lambda: 2**42,
        contract=wire)
    sampler = co.ap_sampler
    closed = None
    released = False
    result = None
    try:
        clock.advance(50_000_000)
        assert entered.wait(1)
        with sampler.lock:
            before = sampler.acquired
            occupied_at_entry = sampler.occupied
            in_service = next(i for i, state in enumerate(sampler.states) if state == 3)
            offset = in_service * sampler.encoded_slot_bytes
            original_slot = bytes(sampler.arena[offset : offset + sampler.lengths[in_service]])
            original_ordinal = sampler.ordinals[in_service]
        queue_available = (not co.pending and not co.slots and co.writer.mailbox.empty()
                           and occupied_at_entry < 16)
        for target in (100_000_000, 150_000_000, 200_000_000):
            clock.advance(target - clock.now_ns())
            end = time.monotonic() + 0.025
            while co.last_sample_ns < target and time.monotonic() < end:
                time.sleep(0.001)
        with sampler.lock:
            progress_during_persistence = sampler.acquired - before
            observed_during_persistence = sampler.last_observed
            occupied_during_persistence = sampler.occupied
            assert sampler.states[in_service] == 3
            assert sampler.ordinals[in_service] == original_ordinal
            assert bytes(sampler.arena[offset : offset + len(original_slot)]) == original_slot
        clock.advance(250_000_000 - clock.now_ns())
        assert persisted.wait(1)
        time.sleep(0.03)
        if sampler.failure is None and not co.writer.failed.is_set():
            closed = sampler.close()
            co.writer.release({"scope": "TEST_ONLY_SAMPLER_WRITER", "scientific_pass": False})
            released = True
        result = dict(scope="TEST_ONLY_REAL_WF_AP2_SAMPLER_WRITER_NO_ATTEMPTS",
            assurance_family=family, clock="CONTROLLED_MONOTONIC_NOT_NATIVE",
            queue_available=queue_available,
            progress_during_persistence=progress_during_persistence,
            occupied_at_entry=occupied_at_entry,
            occupied_during_persistence=occupied_during_persistence,
            observed_during_persistence=observed_during_persistence,
            failure=sampler.failure, first_fault=sampler.first_fault,
            maximum_gap_ns=sampler.maximum_gap, maximum_ack_age_ns=sampler.maximum_age,
            acquired=sampler.acquired, acknowledged=sampler.acknowledged,
            witnessed=sampler.witnessed, released=released,
            sampling_closed=closed, timing=timing,
            historical_cause="UNKNOWN", workload_attempts=0)
    finally:
        if not released:
            co.writer.abort()
        if result is not None:
            result["writer_joined"] = not co.writer.thread.is_alive()
            result["sampler_joined"] = not sampler.thread.is_alive()
            retain(tmp_path / "writer-lifecycle.json", result)
    assert result is not None
    assert len(sampler.arena) == 16 * 2048
    assert queue_available
    assert progress_during_persistence >= 2, result
    assert timing["persist_return_wall_ns"] - timing["persist_enter_wall_ns"] >= 200_000_000
    assert "OBSERVATION" not in timing["writer_scratch_at_persistence"]
    assert sampler.failure is None and not co.writer.failed.is_set(), result
    assert sampler.maximum_gap <= 100_000_000
    assert 200_000_000 <= sampler.maximum_age <= 500_000_000
    assert closed["result"] == "COMPLETE" and released
    assert result["writer_joined"] and result["sampler_joined"]
    events = list(journal.read_events(tmp_path / "run", wire.digest(start), contract=wire))
    samples = {e["body"]["observation"]["acquisition_seq"]: e
               for e in events if e["kind"] == "RESOURCE_SAMPLE"}
    acks = [e for e in events if e["kind"] == "SAMPLE_ACK"]
    assert len(samples) == len(acks) == sampler.witnessed
    for ack in acks:
        body = ack["body"]
        sample = samples[body["acquisition_seq"]]
        observation = sample["body"]["observation"]
        assert sample["seq"] < ack["seq"]
        assert body["sample_event_sha256"] == wire.digest(sample)
        assert body["observation_sha256"] == wire.digest(observation)
        assert observation["observed_mono_ns"] <= body["event_ack_mono_ns"] <= ack["mono_ns"]
    assert not (tmp_path / "run" / "_SEGMENT_SEALED").exists()


@pytest.mark.parametrize("family", ["M2", "RA"])
def test_partial_ack_write_never_releases_credit_or_manufactures_closure(
    offline, tmp_path, monkeypatch, family
):
    clock = FakeClock()
    profile, plan, start, authority, wire = successor_inputs(family, clock)
    broken = threading.Event()
    original_write = journal.io.write

    def partial_ack(path, raw):
        if path.parent.name == "events" and b'"kind":"SAMPLE_ACK"' in raw:
            original_write(path, raw[: len(raw) // 2])
            broken.set()
            raise OSError(5)
        return original_write(path, raw)

    monkeypatch.setattr(journal.io, "write", partial_ack)
    co = scheduler.Coordinator(profile, plan, start, authority=authority, clock=clock,
        root=tmp_path / "run", block_id=1, segment_authority=H,
        writer_exclusion_evidence=H, epoch=H, free_bytes=lambda: 2**42, contract=wire)
    sampler = co.ap_sampler
    try:
        clock.advance(50_000_000)
        assert broken.wait(1)
        assert co.writer.failed.wait(1)
        with sampler.condition:
            assert sampler.condition.wait_for(lambda: sampler.failure is not None, timeout=1)
        assert sampler.failure == "WRITE_UNCERTAIN"
        assert sampler.occupied == 1 and sampler.states[0] == 4
        assert sampler.appended == sampler.acknowledged == 1
        assert sampler.witnessed == 0 and sampler.pending_release is None
        assert sampler.association == sampler.seed
        assert not sampler.closed and sampler.final_ack is None
        with pytest.raises(sampling.SamplingFailure):
            sampler.close()
        with pytest.raises((ValueError, c.Stage12Error)):
            list(journal.read_events(tmp_path / "run", wire.digest(start), contract=wire))
        assert not (tmp_path / "run" / "_WRITER_RELEASED.json").exists()
        assert not (tmp_path / "run" / "_SEGMENT_SEALED").exists()
    finally:
        co.writer.abort()
    assert not co.writer.thread.is_alive() and not sampler.thread.is_alive()


def test_legacy_arena_and_successor_outstanding_credit_are_preserved():
    legacy, co, _, _ = component()
    assert len(legacy.arena) == 65536 and legacy.encoded_slot_bytes == 4096
    co.contract = contract
    sampler = sampling.Sampler(co)
    assert len(sampler.arena) == 32768 and sampler.encoded_slot_bytes == 2048
    for i in range(16):
        assert sampler._reserve() == (i, i + 1)
        sampler.owner_busy = False
        sampler.states[i] = 2
    assert sampler.occupied == 16
    assert sampler._reserve() is None
    assert sampler.failure == "OBSERVATION_COUNT_LIMIT"
    assert sampler.occupied == 16


def test_real_writer_exclusion_precedes_prepared_body_access(offline, tmp_path):
    clock = FakeClock()
    profile, plan, start, authority, wire = successor_inputs("M2", clock)
    co = scheduler.Coordinator(profile, plan, start, authority=authority, clock=clock,
        root=tmp_path / "run", block_id=1, segment_authority=H,
        writer_exclusion_evidence=H, epoch=H, free_bytes=lambda: 2**42, contract=wire)
    try:
        before = co.journal.seq
        with pytest.raises(c.Stage12Error):
            co.ap_sampler.service()
        assert co.journal.seq == before
        assert co.ap_sampler.reserved == 0 and not co.writer.failed.is_set()
    finally:
        co.writer.abort()
    assert not co.writer.thread.is_alive() and not co.ap_sampler.thread.is_alive()
