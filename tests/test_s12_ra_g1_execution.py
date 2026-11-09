"""Author integration of the growing worker pass and independent parent pass."""

from copy import deepcopy
import time

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_execution as e
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_monitor as m
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as base
from test_s12_ra_g1_core import (
    H,
    Authority,
    binding,
    observation,
    original_observation,
    selection,
)


def session(tmp_path, *, mutate_original=False):
    selected = selection()
    authority = Authority(selected)
    charges, reads = [], []

    def factory(retain):
        def observer(kind):
            row = observation(selected, enter=time.monotonic_ns(), kind=kind)
            original = original_observation(row)
            if mutate_original:
                original["counters"]["SQLITE"] = 1
            row["visible_identity_inventory_sha256"] = retain(original)
            return {
                key: row[key]
                for key in (
                    "readings",
                    "counters",
                    "native_visibility",
                    "visible_identity_inventory_sha256",
                )
            }

        return observer

    value = e.PhaseSession(
        authority=authority,
        binding=binding(selected),
        selection=selected,
        resource_evidence_root=tmp_path / "resource",
        pids=(123,),
        counter_provider=lambda: {key: 0 for key in m.COUNTERS},
        charge=lambda n, k: charges.append((n, k)),
        check=lambda: None,
        deadline_ns=time.monotonic_ns() + 5_000_000_000,
        admitted_process_provider=lambda: (123,),
        read_charge=lambda n, k: reads.append((n, k)),
        observer_factory=factory,
    )
    return value, charges, reads


def test_actual_opener_once_growing_first_pass_then_independent_parent_pass(tmp_path):
    value, charges, reads = session(tmp_path)
    value.start()
    called, worker_original_reads = [], []
    actual_reader = value.original_reader

    def worker_read(digest):
        worker_original_reads.append(digest)
        return actual_reader(digest)

    value.original_reader = worker_read

    def opener():
        called.append(value.cursor.coverage.seq)
        assert value.protocol.state == "OPENING"
        return "opened-existing-data"

    result, records = value.freeze_and_open(
        frozen_data_inventory_sha256=H, actual_opener=opener
    )
    assert result == "opened-existing-data" and len(called) == 1 and called[0] >= 1
    rows = records["monitor_terminal"]["last_seq"]
    assert (
        value.completed and value.writer.released and len(worker_original_reads) == rows
    )
    assert sum(n for n, _ in charges) <= rows * 16384 + 4 * 8192
    parent_reads = []

    def fresh_parent_read(digest):
        parent_reads.append(digest)
        return actual_reader(digest)

    # Genuine worker return is provided by the outer supervisor in production.
    child = dict(pid=123, wait_status=0, acquired_mono_ns=time.monotonic_ns())
    restored = m.reopen_phase_protocol(
        binding_sha256=c.digest(value.binding),
        selection_sha256=c.digest(value.selection),
        phase_id=1,
        closure=records["preopening"],
        opener_return=records["opener_return"],
        monitor_terminal=records["monitor_terminal"],
        deadline_ns=value.deadline,
        check=lambda: None,
    )
    terminal = m.verify_tail(
        protocol=restored,
        monitor_path=value.writer.path,
        selected=value.selection,
        seed_sha256=value.seed,
        child_result=child,
        genuine_wait_status=0,
        expected_child_pid=123,
        current_counter_sha256=H,
        persist_terminal=lambda record, guard: record,
        original_observation_reader=fresh_parent_read,
        test_only=True,
        worker_validation=records["worker_validation"],
    )
    assert len(parent_reads) == rows
    assert len(worker_original_reads) + len(parent_reads) == 2 * rows
    assert terminal["disposition"] == "COMPLETE_SELECTED_SCOPE"
    assert len(list(value.original_root.iterdir())) == rows


def test_original_and_codec_mismatch_stops_inside_real_opener_stage(tmp_path):
    value, _, _ = session(tmp_path, mutate_original=True)
    value.start()
    called = []
    with pytest.raises(base.Stage12Error):
        value.freeze_and_open(
            frozen_data_inventory_sha256=H,
            actual_opener=lambda: called.append("must-not-open"),
        )
    assert not called and not value.completed and value.failed
    value.monitor.stop_event.set()
    with value.writer.condition:
        value.writer.closing = True
        value.writer.condition.notify_all()
    value.monitor.thread.join(1)
    value.writer.thread.join(1)


def test_worker_proof_cannot_hide_changed_original_from_parent(tmp_path):
    value, _, _ = session(tmp_path)
    value.start()
    _, records = value.freeze_and_open(
        frozen_data_inventory_sha256=H, actual_opener=lambda: True
    )
    original = next(value.original_root.iterdir())
    original.write_bytes(
        original.read_bytes().replace(b'"f_favail":100000', b'"f_favail":100001')
    )
    restored = m.reopen_phase_protocol(
        binding_sha256=c.digest(value.binding),
        selection_sha256=c.digest(value.selection),
        phase_id=1,
        closure=records["preopening"],
        opener_return=records["opener_return"],
        monitor_terminal=records["monitor_terminal"],
        deadline_ns=value.deadline,
        check=lambda: None,
    )
    with pytest.raises(base.Stage12Error):
        m.verify_tail(
            protocol=restored,
            monitor_path=value.writer.path,
            selected=value.selection,
            seed_sha256=value.seed,
            child_result=dict(
                pid=123, wait_status=0, acquired_mono_ns=time.monotonic_ns()
            ),
            genuine_wait_status=0,
            expected_child_pid=123,
            current_counter_sha256=H,
            persist_terminal=lambda record, guard: record,
            original_observation_reader=value.original_reader,
            test_only=True,
            worker_validation=records["worker_validation"],
        )


def test_worker_validation_hash_or_timestamps_cannot_replace_actual_history(tmp_path):
    value, _, _ = session(tmp_path)
    value.start()
    _, records = value.freeze_and_open(
        frozen_data_inventory_sha256=H, actual_opener=lambda: True
    )
    forged = deepcopy(records["worker_validation"])
    forged["prefix_validated_ns"] = forged["first_pass_end_ns"] + 1
    with pytest.raises(base.Stage12Error):
        e.validate_worker_validation(forged, protocol=value.protocol)


def test_exact_expected_negative_semantic_rejection_retains_monitor_completion(
    tmp_path,
):
    value, _, _ = session(tmp_path)
    value.start()

    def negative():
        raise base.Stage12Error("S12_PUBLIC_OPERATIONS_INVALID")

    result, records = value.freeze_and_open(
        frozen_data_inventory_sha256=H,
        actual_opener=negative,
        expected_negative_sha256=H,
        is_expected_negative=lambda error: (
            type(error) is base.Stage12Error
            and error.args == ("S12_PUBLIC_OPERATIONS_INVALID",)
        ),
    )
    assert result is None
    assert (
        records["opener_return"]["opener_disposition"] == "EXPECTED_NEGATIVE_REJECTED"
    )
    assert records["monitor_terminal"]["disposition"] == "CLOSED_SELECTED_SCOPE"
    assert value.completed


def test_expected_negative_callback_cannot_accept_timeout(tmp_path):
    value, _, _ = session(tmp_path)
    value.start()

    def timeout():
        raise TimeoutError("unsafe exception detail")

    with pytest.raises(TimeoutError):
        value.freeze_and_open(
            frozen_data_inventory_sha256=H,
            actual_opener=timeout,
            expected_negative_sha256=H,
            is_expected_negative=lambda error: True,
        )
    assert value.failed and not value.completed
    assert not value.monitor.thread.is_alive() and not value.writer.thread.is_alive()
    assert "worker_validation" not in value.records
