"""Source ledger author tests, with no live authority, grants or native claim."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
from types import SimpleNamespace

import pytest

from test_s12_ra_g1_core import selection, binding
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_ra_g1_assurance as assurance,
    s12_public_operations as operations,
    s12_ra_g1_source_counters as counters,
)


def inputs(*, reads=50, size=100000, checks=100):
    selected = selection()
    stage = selected["limits"]["stages"][0]
    selected["limits"]["stages"] = [
        {
            **stage,
            "id": i,
            "phase": i,
            "attempts": 0,
            "events": 0,
            "source_read_calls": reads,
            "source_read_bytes": size,
            "check_calls": checks,
        }
        for i in range(1, 15)
    ]
    record = binding(selected)
    record.update(
        maximum_original_read_calls=reads,
        maximum_original_read_bytes=size,
        maximum_identity_checks=checks,
    )
    return selected, record


def test_fixed_stage_binding_global_bounds_and_actual_snapshot():
    selected, bound = inputs()
    bound["maximum_original_read_calls"] = 30
    ledger = counters.SourceCounterLedger(
        selected,
        binding=bound,
        maximum_original_read_calls=40,
        maximum_original_read_bytes=20000,
        maximum_identity_checks=80,
    )
    assert ledger.source_selection_sha256 == operations.digest(selected)
    assert ledger.limit_basis()["limits"] == dict(
        source_read_calls=30, source_read_bytes=20000, identity_checks=80
    )
    ledger.read_charge(1, 0)
    ledger.read_charge(0, 4096)
    ledger.read_charge(1, 0)  # actual EOF attempt is a read call too.
    ledger.checkpoint()
    assert ledger.snapshot_source() == dict(
        source_read_calls=2, source_read_bytes=4096, identity_checks=1
    )


def test_mutating_inputs_or_returned_copies_cannot_enlarge_or_reset():
    selected, bound = inputs(reads=2, size=3, checks=2)
    ledger = counters.SourceCounterLedger(selected, binding=bound)
    selected["limits"]["stages"][12]["source_read_calls"] = 100000
    bound["maximum_original_read_calls"] = 100000
    ledger.limit_basis()["limits"]["source_read_calls"] = 100000
    ledger.snapshot_source()["source_read_calls"] = 100000
    ledger.read_charge(2, 3)
    with pytest.raises(counters.SourceCounterError, match="RA_G1_READ_LIMIT"):
        ledger.read_charge(1, 0)
    assert ledger.source_read_calls == 3  # denied attempts remain charged.
    assert ledger.limit_basis()["limits"]["source_read_calls"] == 2
    assert ledger.source_read_bytes == 3


def test_verified_prefix_adds_current_deltas_and_has_no_supported_flags():
    selected, _ = inputs()
    ledger = counters.SourceCounterLedger(selected, phase_id=14)
    ledger.read_charge(1, 4)
    ledger.checkpoint()
    prefix = dict(source_read_calls=3, source_read_bytes=9, identity_checks=2)
    ledger.add_verified_prefix(prefix)
    assert ledger.snapshot_source() == dict(
        source_read_calls=4, source_read_bytes=13, identity_checks=3
    )
    assert prefix == dict(source_read_calls=3, source_read_bytes=9, identity_checks=2)
    with pytest.raises(counters.SourceCounterError, match="RA_G1_HANDOFF"):
        ledger.add_verified_prefix({**prefix, "supported": True})
    for key in counters.SOURCE_KEYS:
        bad = {**prefix, key: True}
        with pytest.raises(counters.SourceCounterError):
            ledger.add_verified_prefix(bad)


def test_narrowing_after_bootstrap_never_zeroes_or_enlarges():
    selected, bound = inputs()
    ledger = counters.SourceCounterLedger(selected)
    ledger.read_charge(4, 9)
    narrow = {**bound, "maximum_original_read_calls": 5}
    ledger.constrain(narrow)
    ledger.constrain(bound)
    assert ledger.source_read_calls == 4
    assert ledger.limit_basis()["limits"]["source_read_calls"] == 5
    wrong = {**bound, "selection_sha256": "3" * 64}
    with pytest.raises(counters.SourceCounterError, match="RA_G1_SELECTION_BINDING"):
        ledger.constrain(wrong)
    with pytest.raises(counters.SourceCounterError, match="RA_G1_READ_LIMIT"):
        ledger.constrain({**bound, "maximum_original_read_calls": 3})
    assert ledger.source_read_calls == 4


def test_current_pid_fence_on_every_mutation_and_snapshot(monkeypatch):
    selected, _ = inputs()
    ledger = counters.SourceCounterLedger(selected)
    original_pid = ledger.process_pid
    monkeypatch.setattr(counters.os, "getpid", lambda: original_pid + 1)
    for operation in (
        lambda: ledger.read_charge(1, 0),
        ledger.checkpoint,
        lambda: ledger.add_verified_prefix(dict.fromkeys(counters.SOURCE_KEYS, 0)),
        ledger.snapshot_source,
        ledger.limit_basis,
    ):
        with pytest.raises(counters.SourceCounterError, match="RA_G1_PROCESS_SCOPE"):
            operation()


def test_check_limit_and_concurrent_updates_are_not_lost():
    selected, _ = inputs(reads=1000, checks=1000)
    ledger = counters.SourceCounterLedger(selected)

    def step(_):
        ledger.read_charge(1, 1)
        ledger.checkpoint()

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(step, range(200)))
    assert ledger.snapshot_source() == dict.fromkeys(counters.SOURCE_KEYS, 200)
    small, _ = inputs(checks=1)
    limited = counters.SourceCounterLedger(small)
    limited.checkpoint()
    with pytest.raises(counters.SourceCounterError, match="RA_G1_CHECK_BUDGET"):
        limited.checkpoint()
    assert limited.identity_checks == 2


def test_real_bounded_backend_reads_share_ledger_and_mutation_fails(
    tmp_path, monkeypatch
):
    selected, _ = inputs()
    ledger = counters.SourceCounterLedger(selected)
    path = tmp_path / "SYNTHETIC_ONLY_backend.so"
    path.write_bytes(b"x" * 9000)
    path.chmod(0o600)
    monkeypatch.setattr(
        "importlib.import_module", lambda name: SimpleNamespace(__file__=str(path))
    )
    reader = assurance.bounded_backend_reader(ledger.read_charge)
    assert (
        reader("_hashlib", path, ledger.checkpoint)
        == hashlib.sha256(b"x" * 9000).hexdigest()
    )
    assert ledger.source_read_calls == 4 and ledger.source_read_bytes == 9000
    before = ledger.snapshot_source()
    checks = [0]

    def mutate():
        ledger.checkpoint()
        checks[0] += 1
        if checks[0] == 3:
            with path.open("ab") as stream:
                stream.write(b"changed")

    with pytest.raises(operations.c.Stage12Error):
        reader("_hashlib", path, mutate)
    after = ledger.snapshot_source()
    assert after["source_read_calls"] > before["source_read_calls"]
    assert after["source_read_bytes"] >= before["source_read_bytes"]


def test_closed_source_only_state_and_lightweight_import_basis():
    import ast
    from pathlib import Path

    source = Path(counters.__file__).read_text()
    names = {
        node.module.split(".")[0]
        if isinstance(node, ast.ImportFrom)
        else alias.name.split(".")[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert names <= {"__future__", "hashlib", "json", "os", "threading", "typing", "time"}
    selected, _ = inputs()
    bad = deepcopy(selected)
    bad["scope"] = "REPRESENTATIVE_NO_SERVICE"
    with pytest.raises(counters.SourceCounterError):
        counters.SourceCounterLedger(bad)
    with pytest.raises(counters.SourceCounterError):
        counters.SourceCounterLedger(selected, phase_id=12)


def test_stage_transition_retains_globals_and_applies_entry_delta_only():
    selected, _ = inputs(reads=2, size=10, checks=3)
    ledger = counters.SourceCounterLedger(selected)
    ledger.read_charge(2, 8)
    ledger.checkpoint()
    before = ledger.snapshot_source()
    ledger.enter_stage(1)
    assert ledger.snapshot_source() == before
    ledger.read_charge(2, 8)
    assert ledger.source_read_calls == 4
    assert ledger.limit_basis()["stage_entry_source_prefix"] == before
    with pytest.raises(counters.SourceCounterError, match="RA_G1_READ_LIMIT"):
        ledger.read_charge(1, 0)
    assert ledger.source_read_calls == 5


def test_stage_order_once_only_and_stage_deadline_cannot_reset():
    selected, _ = inputs()
    now = [100]
    ledger = counters.SourceCounterLedger(selected, clock_ns=lambda: now[0])
    with pytest.raises(counters.SourceCounterError, match="RA_G1_SOURCE_STAGE_ORDER"):
        ledger.enter_stage(2)
    for phase in range(1, 13):
        ledger.enter_stage(phase)
    with pytest.raises(counters.SourceCounterError, match="RA_G1_SOURCE_STAGE_ORDER"):
        ledger.enter_stage(13)
    timed = counters.SourceCounterLedger(selected, clock_ns=lambda: now[0])
    now[0] = timed.limit_basis()["stage_deadline_mono_ns"]
    with pytest.raises(counters.SourceCounterError, match="RA_G1_DEADLINE"):
        timed.enter_stage(1)
    assert timed.limit_basis()["phase_id"] == 13


def test_verifier14_prefix_preserves_current_deltas_and_is_once_only():
    selected, _ = inputs(reads=5, size=100, checks=5)
    ledger = counters.SourceCounterLedger(selected, phase_id=14)
    ledger.read_charge(4, 9)
    ledger.checkpoint()
    prefix = dict(source_read_calls=6, source_read_bytes=40, identity_checks=8)
    ledger.add_verified_prefix(prefix)
    assert ledger.snapshot_source() == dict(
        source_read_calls=10, source_read_bytes=49, identity_checks=9
    )
    assert ledger.limit_basis()["stage_entry_source_prefix"] == prefix
    with pytest.raises(counters.SourceCounterError, match="RA_G1_HANDOFF"):
        ledger.add_verified_prefix(prefix)
    with pytest.raises(counters.SourceCounterError, match="RA_G1_SOURCE_STAGE_ORDER"):
        ledger.enter_stage(1)
    with pytest.raises(counters.SourceCounterError, match="RA_G1_READ_LIMIT"):
        ledger.read_charge(2, 0)


def test_binding_global_cap_stays_global_across_stage_changes():
    selected, bound = inputs(reads=5)
    bound["maximum_original_read_calls"] = 6
    ledger = counters.SourceCounterLedger(selected, binding=bound)
    ledger.read_charge(4, 0)
    ledger.enter_stage(1)
    ledger.read_charge(2, 0)
    with pytest.raises(counters.SourceCounterError, match="RA_G1_READ_LIMIT"):
        ledger.read_charge(1, 0)
    assert ledger.source_read_calls == 7
