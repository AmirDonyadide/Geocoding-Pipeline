"""TEST_ONLY invented scheduler rows through real local children/EOF/owners."""
import copy
import importlib.util
from pathlib import Path
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import stage12_ra_g1_nonwaiting_submit as shared

spec = importlib.util.spec_from_file_location(
    "first_terminal_commands", ROOT / "scripts/stage12_ra_g1_task_assets/b_nonwaiting_commands.py"
)
commands = importlib.util.module_from_spec(spec)
spec.loader.exec_module(commands)

JOB = 70000000001001
NONCE = "a" * 32
SOURCE = "b" * 40
SELECTION = "c" * 64


@pytest.fixture(autouse=True)
def test_only_window(monkeypatch):
    # A synthetic future authority window; production's immutable cutoff is not
    # changed. Real process/monotonic clocks and the selected envelopes remain.
    monkeypatch.setattr(commands, "WINDOW_END_NS", time.time_ns() + 86_400 * 10**9)


def query_original(tmp_path, *, state="COMPLETED", code="0:0", partial=False):
    root = tmp_path / ("job_" + str(JOB))
    root.mkdir(mode=0o700)
    schedule = commands.terminal_schedule(
        entry_mono_ns=time.monotonic_ns(), entry_epoch_ns=time.time_ns(),
        absolute_window_end_epoch_ns=commands.WINDOW_END_NS,
    )
    owner = commands.ObservationOwner(
        schedule=schedule, directory=root / "terminal_observations", shared=shared,
        job_id=JOB, nonce=NONCE, source_sha=SOURCE, selection_sha256=SELECTION,
        service=lambda: None,
    )
    ids = ("",) if partial else ("", ".batch", ".extern")
    raw = ("S12TERM1|BEGIN|" + NONCE + "|" + str(JOB) + "|1794650000.123456\n"
        + "".join(str(JOB) + suffix + "|" + state + "|" + code
            + "|2026-11-14T10:00:00|2026-11-14T10:00:01|"
            + ("60099" if not suffix else "") + "|footprint|"
            + ("general1" if not suffix else "") + "\n" for suffix in ids)).encode()
    child = [sys.executable, "-c", "import os;os.write(1," + repr(raw) + ")"]
    result = shared.run_query(
        child, shared.QueryParser(JOB, NONCE, 60099), owner, owner.record,
        "TERMINAL_QUERY_01", lambda *args: None, bank=owner.bank,
    )
    op = __import__("json").loads((owner._directory / "TERMINAL_QUERY_01.record").read_bytes())
    bound = __import__("json").loads((owner._directory / "OBSERVER_BINDING.record").read_bytes())
    return result, op, bound, schedule


def validate(op, bound):
    return shared.validate_first_terminal_original(
        op, bound, job_id=JOB, nonce=NONCE, source_sha=SOURCE,
        selection_sha256=SELECTION, uid=60099,
    )


@pytest.mark.parametrize("state,code,successful", [("COMPLETED", "0:0", True), ("FAILED", "1:0", False)])
def test_first_real_query_qualifies_success_and_failure(tmp_path, state, code, successful):
    facts, op, bound, schedule = query_original(tmp_path, state=state, code=code)
    checked = validate(op, bound)
    assert checked["operation"] == "TERMINAL_QUERY_01"
    assert checked["semantic_role"] == shared.QUALIFYING_TERMINAL_ROLE
    assert checked["driver_closure"] == "SEPARATELY_REQUIRED"
    assert checked["scientific_acceptance"] is False
    assert facts["all_completed_zero"] is successful
    assert commands.first_terminal_disposition(facts, job_id=JOB, nonce=NONCE) != "INCOMPLETE"
    assert schedule["fixed_confirmation_wait"] is False
    assert "final_authoritative_slots" not in schedule
    assert op["actual_client_exit"] == 0 and op["joined"]
    assert op["stdout_eof"] and op["stderr_eof"] and not op["cleanup_uncertain"]


@pytest.mark.parametrize("kind", ["partial", "nonterminal"])
def test_partial_and_nonterminal_do_not_qualify(tmp_path, kind):
    facts, op, bound, _ = query_original(tmp_path, partial=kind == "partial",
                                        state="RUNNING" if kind == "nonterminal" else "COMPLETED")
    assert commands.first_terminal_disposition(facts, job_id=JOB, nonce=NONCE) == "INCOMPLETE"
    with pytest.raises(shared.Stop, match="NONTERMINAL"):
        validate(op, bound)


@pytest.mark.parametrize("mutation", ["nonce", "rows", "raw", "exit", "EOF", "join", "truncation", "cleanup", "legacy", "mixed", "label"])
def test_changed_original_or_mixed_contract_rejected(tmp_path, mutation):
    _, original, binding, _ = query_original(tmp_path)
    op, bound = copy.deepcopy(original), copy.deepcopy(binding)
    if mutation == "nonce": bound["nonce"] = "d" * 32
    elif mutation == "rows": op["facts"]["rows"][1]["exit_code"] = "7:0"
    elif mutation == "raw": op["stdout_b64"] = op["stdout_b64"][:-4]
    elif mutation == "exit": op["actual_client_exit"] = 7
    elif mutation == "EOF": op["stderr_eof"] = False
    elif mutation == "join": op["joined"] = False
    elif mutation == "truncation": op["stdout_truncated"] = True
    elif mutation == "cleanup": op["cleanup_uncertain"] = True
    elif mutation == "legacy": bound["version"] = "stage12_b_terminal_observer_owner_v1"
    elif mutation == "mixed": bound["schedule"]["final_authoritative_slots"] = [14, 15]
    elif mutation == "label": op["operation"] = "TERMINAL_QUERY_16"
    with pytest.raises(shared.Stop): validate(op, bound)


def test_same_regular_poll_schedule_and_old_policy_distinction():
    schedule = commands.terminal_schedule(entry_mono_ns=1, entry_epoch_ns=1,
        absolute_window_end_epoch_ns=commands.WINDOW_END_NS)
    assert schedule["offset_seconds"] == list(range(0, 7801, 600)) + [8260, 8380]
    assert commands.slot_bounds(schedule, 0) == (1, 585_000_000_001)
    assert commands.slot_bounds(schedule, 15) == (8_380_000_000_001, 8_385_000_000_001)
    with pytest.raises(RuntimeError, match="B_LEGACY_CONFIRMATION_POLICY"):
        commands.final_not_before(schedule)
    old = commands.legacy_terminal_schedule(entry_mono_ns=1, entry_epoch_ns=1,
        absolute_window_end_epoch_ns=commands.WINDOW_END_NS)
    assert old["final_authoritative_slots"] == [14, 15]
    assert commands.final_not_before(old) == (8_260_000_000_001, 8_380_000_000_001)
