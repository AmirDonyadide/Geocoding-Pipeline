"""Offline invented-only tests for the terminal stream entry point.

No subprocess/network/native artifact is used by pytest. Root separately runs
the actual script export/receive entry points on one emitted tiny fixture.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import struct
import sys
import time

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/stage12_ra_g1_terminal_collect.py"
SPEC = importlib.util.spec_from_file_location("stage12_terminal_collect_tested", SCRIPT)
tc = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tc
SPEC.loader.exec_module(tc)


def put(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(raw)
        while view:
            n = os.write(fd, view)
            assert n > 0
            view = view[n:]
    finally:
        os.close(fd)


def make_case(root, changes=None):
    root = Path(root).absolute()
    root.mkdir(mode=0o700)
    alloc, records = root/"allocation", root/"records"
    alloc.mkdir(mode=0o700)
    records.mkdir(mode=0o700)
    (alloc/"sub").mkdir(mode=0o700)
    put(alloc/"one.bin", b"INVENTED PUBLIC TERMINAL PAYLOAD\0" * 8)
    put(alloc/"sub/two.bin", b"\x00\xffINVENTED\x01")
    put(records/"slurm.log", b"TEST_ONLY scheduler log\n")
    put(root/"external.log", b"TEST_ONLY external stderr\n")
    limits = dict(members=64, payload_bytes=1048576, manifest_bytes=262144,
                  record_bytes=4096, path_bytes=512, name_bytes=255, depth=16,
                  sort_records=2, sort_buffer_bytes=16384, merge_fan_in=2,
                  chunk_bytes=4096, wire_bytes=2097152, read_bytes=33554432,
                  write_bytes=33554432, creations=512, operations=100000,
                  scanned_entries=2048, seconds=30)
    if changes:
        limits.update(changes)
    value = dict(version=tc.VERSION, scope="TEST_ONLY_INVENTED", state="TEST_ONLY",
                 approval_sha256=None, job_id=0, source_git_sha="0"*40, source_uid=os.geteuid(), source_gid=os.getegid(),
                 roots=[dict(label="allocation", path=str(alloc)),
                        dict(label="records", path=str(records))],
                 external_files=[dict(label="slurm_stderr", path=str(root/"external.log"))],
                 required_logs=["records/slurm.log", "slurm_stderr"], limits=limits,
                 valid_until_epoch_ns=time.time_ns()+300_000_000_000)
    config = root/"selection.json"
    raw = tc.canonical(value)
    put(config, raw)
    return root, config, hashlib.sha256(raw).hexdigest(), value


def args(case, action, output):
    root, config, digest, _ = case
    return [action, "--selection", str(config), "--selection-sha256", digest,
            "--output", str(output), "--offline-invented", "--test-root", str(root)]


def exported(case, suffix="sender", sink=None):
    sink = io.BytesIO() if sink is None else sink
    stderr = io.StringIO()
    code = tc.main(args(case, "export", case[0]/suffix), stdout=sink, stderr=stderr)
    return code, sink.getvalue(), stderr.getvalue()


def received(case, raw, suffix="receiver"):
    stderr = io.StringIO()
    code = tc.main(args(case, "receive", case[0]/suffix),
                   stdin=io.BytesIO(raw), stdout=io.BytesIO(), stderr=stderr)
    return code, stderr.getvalue()


def decode_wire(raw):
    """Bounded tiny test fixture decoder, never used by production code."""
    assert len(raw) <= 1048576
    assert raw.startswith(tc.MAGIC)
    offset, result, data = len(tc.MAGIC), [], False
    while offset < len(raw):
        length = struct.unpack(">I", raw[offset:offset+4])[0]
        offset += 4
        frame = json.loads(raw[offset:offset+length])
        offset += length
        payload = b""
        if frame["kind"] == "DATA":
            data = True
        elif frame["kind"] == "AFTER":
            data = False
        elif data and frame["kind"] == "ENTRY" and frame["entry"]["kind"] == "FILE":
            size = frame["entry"]["size"]
            payload = raw[offset:offset+size]
            offset += size
        result.append([frame, payload])
    assert offset == len(raw)
    return result


def encode_wire(frames):
    result = bytearray(tc.MAGIC)
    for frame, payload in frames:
        raw = tc.canonical(frame)
        result.extend(struct.pack(">I", len(raw)))
        result.extend(raw)
        result.extend(payload)
    return bytes(result)


def test_round_trip_actual_entry_and_retained_merge_generations(tmp_path, monkeypatch):
    case = make_case(tmp_path/"case")
    monkeypatch.setattr(os, "listdir", lambda *_: pytest.fail("unbounded listdir"))
    code, wire, _ = exported(case)
    assert code == 0
    assert received(case, wire)[0] == 0
    root = case[0]
    for rel in ("allocation/one.bin", "allocation/sub/two.bin", "records/slurm.log"):
        assert (root/"receiver/originals"/rel).read_bytes() == (root/rel).read_bytes()
    assert (root/"receiver/originals/slurm_stderr").read_bytes() == (root/"external.log").read_bytes()
    assert (root/"receiver/terminal.s12c").read_bytes() == wire
    assert (root/"receiver/before.jsonl").read_bytes() == (root/"receiver/after.jsonl").read_bytes()
    status = json.loads((root/"receiver/COLLECTION_COMPLETE.record").read_bytes())
    assert status["native_or_scientific_acceptance"] is False
    assert status["independently_rehashed"] is True
    assert status["completion_requires_zero_sender_and_receiver_exits_and_parent_envelopes"] is True
    assert len(list((root/"sender").glob("before.g*.jsonl"))) == 7
    assert len(list((root/"sender").glob("after.g*.jsonl"))) == 7
    assert len(list((root/"receiver/verify-spills").glob("verify.g*.jsonl"))) == 7
    assert stat.S_IMODE((root/"receiver/originals/allocation/one.bin").stat().st_mode) == 0o600


def test_many_small_files_cross_multiple_merge_generations(tmp_path):
    case = make_case(tmp_path/"case")
    for i in range(40):
        put(case[0]/"allocation"/f"extra_{i:03d}.bin", bytes([i])*2048)
    code, raw, _ = exported(case)
    assert code == 0 and received(case, raw)[0] == 0
    assert len(list((case[0]/"sender").glob("before.g*.jsonl"))) == 48
    assert len(list((case[0]/"receiver/verify-spills").glob("verify.g*.jsonl"))) == 48


@pytest.mark.parametrize("cut", [1, 12, -1])
def test_truncation_retains_prefix_and_never_completes(tmp_path, cut):
    case = make_case(tmp_path/"case")
    code, raw, _ = exported(case)
    assert code == 0
    prefix = raw[:cut] if cut >= 0 else raw[:cut]
    code, stderr = received(case, prefix)
    assert code == 2 and "INCOMPLETE" in stderr
    assert not (case[0]/"receiver/COLLECTION_COMPLETE.record").exists()
    assert (case[0]/"receiver/terminal.s12c").exists()
    assert (case[0]/"receiver/COLLECTION_INCOMPLETE.record").exists()


@pytest.mark.parametrize("change", ["duplicate", "traversal", "absolute", "link", "after_identity"])
def test_closed_membership_path_type_and_identity_rejections(tmp_path, change):
    case = make_case(tmp_path/"case")
    code, raw, _ = exported(case)
    assert code == 0
    frames = decode_wire(raw)
    before = [item for item in frames if item[0]["kind"] == "MEMBER"]
    if change == "duplicate":
        before[1][0]["entry"] = dict(before[0][0]["entry"])
    elif change == "traversal":
        before[0][0]["entry"]["path"] = "../escaped"
    elif change == "absolute":
        before[0][0]["entry"]["path"] = "/escaped"
    elif change == "link":
        before[0][0]["entry"]["kind"] = "SYMLINK"
    else:
        before[-1][0]["entry"]["identity"][8] += 1
    code, stderr = received(case, encode_wire(frames))
    assert code == 2 and "INCOMPLETE" in stderr
    assert not (case[0]/"receiver/COLLECTION_COMPLETE.record").exists()
    assert not (case[0]/"escaped").exists()


def test_payload_corruption_and_trailing_bytes_rejected(tmp_path):
    case = make_case(tmp_path/"case")
    code, raw, _ = exported(case)
    assert code == 0
    frames = decode_wire(raw)
    item = next(item for item in frames if item[1])
    item[1] = bytes([item[1][0]^1]) + item[1][1:]
    assert received(case, encode_wire(frames), "corrupt")[0] == 2
    assert "PAYLOAD_HASH" in (case[0]/"corrupt/COLLECTION_INCOMPLETE.record").read_text()
    assert received(case, raw+b"x", "trailing")[0] == 2


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo"])
def test_source_links_and_specials_rejected_without_opening_them(tmp_path, kind):
    case = make_case(tmp_path/"case")
    target = case[0]/"allocation/bad"
    if kind == "symlink":
        target.symlink_to(case[0]/"allocation/one.bin")
    elif kind == "hardlink":
        os.link(case[0]/"allocation/one.bin", target)
    else:
        os.mkfifo(target, 0o600)
    code, _, stderr = exported(case)
    assert code == 2 and "INCOMPLETE" in stderr
    assert not (case[0]/"sender/COLLECTION_COMPLETE.record").exists()


@pytest.mark.parametrize("changes", [
    {"members": 2}, {"payload_bytes": 1}, {"wire_bytes": 32},
    {"creations": 5}, {"read_bytes": 64}, {"write_bytes": 65536},
    {"scanned_entries": 1}, {"operations": 1},
])
def test_budgets_stop_with_preserved_partial_outputs(tmp_path, changes):
    case = make_case(tmp_path/"case", changes)
    if "write_bytes" in changes:
        (case[0]/"allocation/one.bin").write_bytes(b"W"*32768)
    expected = (case[0]/"allocation/one.bin").read_bytes()
    code, _, stderr = exported(case)
    assert code == 2 and "INCOMPLETE" in stderr
    assert not (case[0]/"sender/COLLECTION_COMPLETE.record").exists()
    assert (case[0]/"allocation/one.bin").read_bytes() == expected


def test_required_external_log_not_omitted(tmp_path):
    case = make_case(tmp_path/"case")
    (case[0]/"external.log").unlink()
    code, _, stderr = exported(case)
    assert code == 2 and "INCOMPLETE" in stderr


def test_source_mutation_between_before_and_data_rejected(tmp_path):
    case = make_case(tmp_path/"case")

    class Mutating(io.BytesIO):
        changed = False

        def write(self, raw):
            if not self.changed and b'"kind":"DATA"' in bytes(raw):
                self.changed = True
                path = case[0]/"allocation/one.bin"
                path.write_bytes(b"x"*path.stat().st_size)
            return super().write(raw)

    code, _, stderr = exported(case, sink=Mutating())
    assert code == 2 and "SOURCE_CHANGED" in stderr


@pytest.mark.parametrize("mutation", ["bytes", "membership"])
def test_source_mutation_after_payload_before_after_pass_rejected(tmp_path, monkeypatch, mutation):
    case = make_case(tmp_path/"case")
    original = tc.make_manifest

    def changed(root, phase, source, selected, budget, project=False):
        if phase == "after":
            if mutation == "bytes":
                path = case[0]/"allocation/one.bin"
                path.write_bytes(b"y"*path.stat().st_size)
            else:
                put(case[0]/"allocation/new_member", b"NEW")
        return original(root, phase, source, selected, budget, project)

    monkeypatch.setattr(tc, "make_manifest", changed)
    code, _, stderr = exported(case)
    assert code == 2 and "SOURCE_CHANGED" in stderr


def test_independent_receiver_membership_rehash_detects_unexpected_file(tmp_path, monkeypatch):
    case = make_case(tmp_path/"case")
    code, raw, _ = exported(case)
    assert code == 0
    original = tc.make_manifest

    def changed(root, phase, source, selected, budget, project=False):
        if phase == "verify":
            put(case[0]/"receiver/originals/allocation/rogue", b"UNEXPECTED")
        return original(root, phase, source, selected, budget, project)

    monkeypatch.setattr(tc, "make_manifest", changed)
    code, _ = received(case, raw)
    assert code == 2
    assert (case[0]/"receiver/originals/allocation/rogue").read_bytes() == b"UNEXPECTED"
    assert not (case[0]/"receiver/COLLECTION_COMPLETE.record").exists()


def test_existing_output_not_modified_and_selection_hash_is_required(tmp_path):
    case = make_case(tmp_path/"case")
    existing = case[0]/"existing"
    existing.mkdir(mode=0o700)
    put(existing/"original", b"KEEP")
    before = list(existing.iterdir())
    code = tc.main(args(case, "export", existing), stdout=io.BytesIO(), stderr=io.StringIO())
    assert code == 2 and list(existing.iterdir()) == before
    argv = args(case, "export", case[0]/"wrong")
    argv[argv.index("--selection-sha256")+1] = "0"*64
    assert tc.main(argv, stdout=io.BytesIO(), stderr=io.StringIO()) == 2
    assert not (case[0]/"wrong").exists()


def test_expired_original_cumulative_window_and_native_guard(tmp_path, monkeypatch):
    case = make_case(tmp_path/"case")
    value = case[3]
    value["valid_until_epoch_ns"] = 1
    raw = tc.canonical(value)
    config = case[0]/"expired.json"
    put(config, raw)
    expired = (case[0], config, hashlib.sha256(raw).hexdigest(), value)
    assert exported(expired)[0] == 2
    called = []

    def should_not_read(*_):
        called.append(True)
        pytest.fail("native guard must precede selection input")

    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setattr(tc, "selection_read", should_not_read)
    assert tc.main(["export", "--selection", str(config),
                    "--selection-sha256", hashlib.sha256(raw).hexdigest(),
                    "--output", str(case[0]/"native")],
                   stdout=io.BytesIO(), stderr=io.StringIO()) == 2
    assert not called


def test_plan_accounts_all_retained_generations_and_no_children(tmp_path):
    case = make_case(tmp_path/"case")
    selected = tc.Selection(case[3], True, case[0])
    plan = tc.plan(selected)
    assert plan["retained_generations"] == 6
    assert plan["per_manifest_run_files"] == 63
    assert plan["exporter_scratch_bytes"] == 2*6*262144+32768
    assert plan["total_creation_bound"] == 64+3*63+12
    assert plan["child_processes"] == plan["worker_threads"] == 0
    assert plan["spill_deletion_or_refund"] is False
    assert plan["placement_or_pool_approval"] is False


def test_duplicate_json_keys_and_unicode_names(tmp_path):
    case = make_case(tmp_path/"case")
    put(case[0]/"allocation"/"\u03b1.bin", b"INVENTED UNICODE NAME")
    code, raw, _ = exported(case)
    assert code == 0 and received(case, raw)[0] == 0
    assert (case[0]/"receiver/originals/allocation"/"\u03b1.bin").read_bytes() == b"INVENTED UNICODE NAME"
    bad = b'{"kind":"BEGIN","kind":"BEGIN"}\n'
    code, stderr = received(case, tc.MAGIC+struct.pack(">I", len(bad))+bad, "duplicate_key")
    assert code == 2 and "DUPLICATE_KEY" in stderr


@pytest.mark.parametrize("operation", ["rows", "member", "output_parent"])
def test_ancestor_rejection_closes_newly_opened_descriptors(tmp_path, monkeypatch, operation):
    case = make_case(tmp_path/"case")
    selected = tc.Selection(case[3], True, case[0])
    budget = tc.Budget(selected, time.monotonic_ns())
    source = tc.Source(selected, budget)
    path = case[0]/"allocation/one.bin"
    row = tc.row_for("allocation/one.bin", "FILE", path.stat(),
                     hashlib.sha256(path.read_bytes()).hexdigest())
    real_open, real_close = os.open, os.close
    opened = set()

    def tracked_open(*a, **kw):
        fd = real_open(*a, **kw)
        opened.add(fd)
        return fd

    def tracked_close(fd):
        real_close(fd)
        opened.discard(fd)

    def changed_ancestor(_):
        raise tc.Stop("ANCESTOR_CHANGED")

    monkeypatch.setattr(tc.os, "open", tracked_open)
    monkeypatch.setattr(tc.os, "close", tracked_close)
    monkeypatch.setattr(tc, "check_ancestors", changed_ancestor)
    with pytest.raises(tc.Stop, match="ANCESTOR_CHANGED"):
        if operation == "rows":
            next(source.rows())
        elif operation == "member":
            source.open_member(row)
        else:
            tc.output_parent(case[0]/"allocation", "one.bin", budget)
    assert not opened


def test_short_wire_and_storage_writes_preserve_exact_stream(tmp_path, monkeypatch):
    case = make_case(tmp_path/"case")
    real_write = os.write

    def short_file(fd, raw):
        return real_write(fd, raw[:64])

    class ShortWire(io.BytesIO):
        def write(self, raw):
            return super().write(raw[:7])

    monkeypatch.setattr(tc.os, "write", short_file)
    code, raw, _ = exported(case, sink=ShortWire())
    assert code == 0 and received(case, raw)[0] == 0
    assert (case[0]/"receiver/originals/allocation/one.bin").read_bytes() == (
        case[0]/"allocation/one.bin").read_bytes()


def test_uncertain_storage_write_preserves_partial_and_original(tmp_path, monkeypatch):
    case = make_case(tmp_path/"case")
    expected = (case[0]/"allocation/one.bin").read_bytes()
    real_write = os.write
    calls = 0

    def uncertain(fd, raw):
        nonlocal calls
        calls += 1
        if calls == 2:
            real_write(fd, raw[:7])
            raise OSError("TEST_ONLY uncertain write")
        return real_write(fd, raw)

    monkeypatch.setattr(tc.os, "write", uncertain)
    code, _, stderr = exported(case)
    assert code == 2 and "INCOMPLETE" in stderr
    assert not (case[0]/"sender/COLLECTION_COMPLETE.record").exists()
    assert any(path.stat().st_size > 0 for path in (case[0]/"sender").glob("before.g*.jsonl"))
    assert (case[0]/"allocation/one.bin").read_bytes() == expected


def test_completion_crossing_deadline_cannot_return_success(tmp_path, monkeypatch):
    case = make_case(tmp_path/"case")
    original = tc.status_write

    def crossing(output, value, budget, success):
        original(output, value, budget, success)
        if success:
            budget.end = 0

    monkeypatch.setattr(tc, "status_write", crossing)
    code, _, stderr = exported(case)
    assert code == 2 and "DEADLINE" in stderr
    # The late immutable complete marker stays retained; zero exits are mandatory.
    assert (case[0]/"sender/COLLECTION_COMPLETE.record").exists()
    assert "incomplete_record_uncertain" in stderr


def test_callback_stop_message_is_not_disclosed(tmp_path):
    case = make_case(tmp_path/"case")
    private_message = "TEST_ONLY unreviewed callback text"

    class FailedWire(io.BytesIO):
        def write(self, _):
            raise tc.Stop(private_message)

    code, _, stderr = exported(case, sink=FailedWire())
    status = (case[0]/"sender/COLLECTION_INCOMPLETE.record").read_text()
    assert code == 2 and "UNCLASSIFIED" in stderr
    assert private_message not in stderr and private_message not in status


def test_close_failure_attempts_all_descriptors_and_preserves_primary(tmp_path, monkeypatch):
    case = make_case(tmp_path/"case")
    selected = tc.Selection(case[3], True, case[0])
    budget = tc.Budget(selected, time.monotonic_ns())
    fds = [os.open(case[0]/"allocation/one.bin", os.O_RDONLY) for _ in range(2)]
    real_close = os.close
    attempted = []

    def uncertain_close(fd):
        attempted.append(fd)
        real_close(fd)
        if len(attempted) == 1:
            raise OSError("TEST_ONLY uncertain close")

    monkeypatch.setattr(tc.os, "close", uncertain_close)
    with pytest.raises(tc.Stop, match="SOURCE_CHANGED") as retained:
        try:
            raise tc.Stop("SOURCE_CHANGED")
        finally:
            tc.close_owned(budget, fds)
    assert attempted == fds and budget.cleanup_uncertain
    assert retained.value.cleanup_uncertain is True




def test_create_file_parent_close_uncertainty_keeps_child_owned(tmp_path, monkeypatch):
    case = make_case(tmp_path/"case")
    selected = tc.Selection(case[3], True, case[0])
    budget = tc.Budget(selected, time.monotonic_ns())
    output = case[0]/"owned-output"
    tc.mkdir(output, budget)
    target = output/"retained-partial"
    real_open, real_close = os.open, os.close
    opened, attempted = [], []

    def tracked_open(*a, **kw):
        fd = real_open(*a, **kw)
        opened.append(fd)
        return fd

    def uncertain_parent_close(fd):
        is_directory = stat.S_ISDIR(os.fstat(fd).st_mode)
        attempted.append(fd)
        real_close(fd)
        if is_directory:
            raise OSError("TEST_ONLY parent close uncertainty")

    monkeypatch.setattr(tc.os, "open", tracked_open)
    monkeypatch.setattr(tc.os, "close", uncertain_parent_close)
    with pytest.raises(tc.Stop, match="CLOSE_UNCERTAIN") as retained:
        tc.create_file(target, budget)
    assert len(opened) == 2 and attempted == opened
    assert target.exists() and target.stat().st_size == 0
    assert budget.cleanup_uncertain and retained.value.args == ("CLOSE_UNCERTAIN",)


if __name__ == "__main__":
    case = make_case(Path(sys.argv[1]))
    print(json.dumps({"scope": "TEST_ONLY_INVENTED", "selection": str(case[1]),
                      "sha256": case[2], "test_root": str(case[0])}, sort_keys=True))
