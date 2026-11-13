"""One invented pair; real canonical driver/probes plus full receipt/ACK/reopen.

Only the existing offline validators' scope arguments and the platform SSH
delivery are represented. No native result, job identity or validator result is
rewritten. The real driver's strict TEST-vs-NATIVE rejection remains a failure.
"""
import base64
import copy
import datetime as dt
import os
from pathlib import Path
import stat
import subprocess
import sys
import threading
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import stage12_ra_g1_collection_driver as driver
import stage12_ra_g1_nonwaiting_submit as terminal
import stage12_ra_g1_one_shot_controls as observer
import stage12_ra_g1_terminal_parent as pair
import stage12_ra_g1_terminal_transport as transport
import stage12_ra_g1_terminal_verify as verify
from test_stage12_ra_g1_terminal_parent import put
from test_stage12_ra_g1_terminal_transport import framed_fixture

tc = pair.tc


def driver_fixture_plan(binding):
    root = Path(binding["output_path"]).parent
    logs = root / "driver-final-logs"
    logs.mkdir(mode=0o700)
    return dict(remote_pair=binding["output_path"],
        window_end_epoch_ns=binding["valid_until_epoch_ns"],
        source_git_sha=binding["source_git_sha"],
        original_source_git_sha=binding["original_source_git_sha"],
        original_source_root=binding["original_source_root"],
        original_producer_path=binding["original_producer_path"],
        allocation_producer_sha256=binding["allocation_producer_sha256"],
        source_uid=os.geteuid(), source_gid=os.getegid(),
        local_directory_scope=transport.TASK_LOCAL_DIRECTORY_SCOPE,
        remote_directory_scope=transport.REMOTE_DIRECTORY_SCOPE,
        transport_evidence_version=transport.REMOTE_TRANSPORT_VERSION,
        local_final_logs=str(logs), collection_logs=binding["collection_external_logs"],
        window=binding["window"])


def stat_line(info):
    def stamp(n):
        seconds, sub = divmod(n, 10**9)
        return dt.datetime.fromtimestamp(seconds, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S") + f".{sub:09d} +0000"
    kind = "directory" if stat.S_ISDIR(info[2]) else "regular file" if info[6] else "regular empty file"
    return ("|".join([str(info[0]), str(info[1]), format(info[2], "x"),
        *map(str, info[3:7]), stamp(info[7]), stamp(info[8]), kind]) + "\n").encode()


def pending_frame(rows, nonce):
    paths, extra, ancestors = transport.batch_paths(rows)
    assert not extra and len(paths) == 3
    snapshot = paths + ancestors
    infos, errors = [], []
    for path in snapshot:
        try:
            infos.append(list(tc.ident(path.lstat())))
        except FileNotFoundError:
            infos.append(None)
            errors.append(f"stat: cannot statx '{path}': No such file or directory\n".encode())
    def block(stage):
        raw = f"{stage}_STATUS|{int(bool(errors))}\n".encode()
        raw += b"".join(os.fsencode(path) + b"|" + stat_line(info)
                        for path, info in zip(snapshot, infos, strict=True) if info is not None)
        return raw + f"END_{stage}\n".encode()
    domain = f"DOMAIN|TEST_ONLY_local_kernel|11111111-1111-1111-1111-111111111111|mnt:[11]|{nonce}|11\n".encode()
    raw = f"S12B3|{nonce}|3|0|{len(ancestors)}\n".encode() + domain + block("BEFORE")
    for i, path in enumerate(paths):
        if infos[i] is None:
            raw += f"ABSENT_DATA|{i}\n".encode()
        else:
            body = path.read_bytes()
            raw += f"DATA|{i}|{len(body)}\n".encode() + body + f"\nEND_DATA|{i}\n".encode()
    raw += block("AFTER") + domain + f"END|{nonce}\n".encode()
    assert len(raw) + 2 * sum(map(len, errors)) < 65536
    return raw, b"".join(errors) * 2


def run_connected_driver(root, binding, admission, plan, monkeypatch):
    """Called while the real pair waits for its receipt; no premature ACK."""
    policy = admission["one_shot_control_policy"]
    command = dict(version="stage12_selected_pair_remote_directory_exact_commands_v3",
        local_binding_path=str(root / "binding.record"),
        local_authority_path=str(root / "authority.record"),
        local_admission_path=binding["collection_admission_path"],
        binding_sha256=pair.digest((root / "binding.record").read_bytes()),
        authority_sha256=binding["authority_sha256"],
        admission_sha256=pair.digest(Path(binding["collection_admission_path"]).read_bytes()),
        original_selection_sha256=binding["original_selection_sha256"],
        plan_sha256=admission["collection_plan_sha256"],
        graph_sha256=admission["process_graph_sha256"],
        remote_directory_scope=transport.REMOTE_DIRECTORY_SCOPE,
        transport_evidence_version=transport.REMOTE_TRANSPORT_VERSION,
        task_control_selection={key: policy[key] for key in (
            "version", "maximum_probes", "probe_seconds", "minimum_start_spacing_seconds",
            "spacing_anchor", "directory_readiness", "selected_remote_pair")},
        nonce=binding["grant_nonce"], submission_protocol=terminal.VERSION,
        selected_original_submission_epoch_ceiling=binding["valid_until_epoch_ns"],
        canonical_preflight_prefix=": TEST_ONLY_PLATFORM_FRAMED_METADATA",
        submit_sbatch_argv=["sbatch", "--parsable", "--no-requeue", "/TEST_ONLY/invented.sbatch"])
    command["submit_argv"] = terminal.submission_argv(command["canonical_preflight_prefix"],
        command["submit_sbatch_argv"], command["nonce"], command["selected_original_submission_epoch_ceiling"], 1800)
    put(root / "TEST_ONLY_DRIVER_COMMAND.record", command)
    paths = [Path(command[key]) for key in ("local_binding_path", "local_authority_path", "local_admission_path")]
    rows = [dict(label=f"control{i}", path=str(path), bytes=path.stat().st_size)
            for i, path in enumerate(paths)]
    ancestors = transport.batch_paths(rows)[2]
    ids = [list(tc.ident(path.lstat())) for path in paths + ancestors]
    prelude = b"BEFORE\n" + b"".join(map(stat_line, ids))
    prelude += b"".join((row["path"] + ": OK\n").encode() for row in rows)
    prelude += b"AFTER\n" + b"".join(map(stat_line, ids))
    prelude += ("REMOTE_DIRECTORY_POLICY|" + transport.REMOTE_DIRECTORY_SCOPE + "\n").encode()
    prelude += b"S12_CANONICAL_BINDINGS_AND_SOURCE_VERIFIED\n"
    driver.validate_prelude(prelude, rows, ancestors, transport, os.geteuid(), os.getegid(),
                            remote_directory_scope=transport.REMOTE_DIRECTORY_SCOPE)
    submit_raw = prelude + f"S12SUB3|BEGIN|{command['nonce']}|{command['selected_original_submission_epoch_ceiling']}|1800|5.2.0\n3001\n".encode()
    tls = threading.local()
    real_popen, real_batch, real_poll = subprocess.Popen, transport.fetch_batch, observer.poll
    original_binding, original_authority = pair.validate_binding, pair.validate_authority
    original_admission = pair.validate_collection_admission
    children, batch_count, outputs = [], [0], []
    def offline_binding(value, offline, test_root):
        return original_binding(value, True, root) if getattr(tls, "active", False) else original_binding(value, offline, test_root)
    def offline_authority(authority, value, offline):
        return original_authority(authority, value, True) if getattr(tls, "active", False) else original_authority(authority, value, offline)
    def offline_admission(value, bound, authority, offline):
        return original_admission(value, bound, authority, True) if getattr(tls, "active", False) else original_admission(value, bound, authority, offline)
    def launch(argv, **kwargs):
        if getattr(tls, "active", False) and argv == command["submit_argv"]:
            script = "import os,time,base64;os.write(1,base64.b64decode(" + repr(base64.b64encode(submit_raw)) + "));time.sleep(.05)"
            child = real_popen([sys.executable, "-c", script], **kwargs)
        else:
            child = real_popen(argv, **kwargs)
        if getattr(tls, "active", False):
            children.append(child)
        return child
    def batch(rows, output, control, **kwargs):
        if getattr(tls, "active", False):
            frame_root = root / ("driver-frame-" + str(batch_count[0]))
            batch_count[0] += 1
            frame_root.mkdir(mode=0o700)
            nonce = kwargs.get("nonce") or "1" * 32
            kwargs["nonce"] = nonce
            if kwargs.get("pending_labels"):
                stdout, stderr = pending_frame(rows, nonce)
                script = "import os,base64;os.write(1,base64.b64decode(" + repr(base64.b64encode(stdout)) + "));os.write(2,base64.b64decode(" + repr(base64.b64encode(stderr)) + "))"
                kwargs["testing_argv"] = [sys.executable, "-c", script]
            else:
                kwargs["testing_argv"] = framed_fixture(frame_root, rows, nonce=nonce)
        return real_batch(rows, output, control, **kwargs)
    def poll(*args, **kwargs):
        result = real_poll(*args, **kwargs)
        if getattr(tls, "inject", False):
            raise TypeError("TEST_ONLY_SECRET_INJECTED_AFTER_REAL_PROBE")
        return result
    with monkeypatch.context() as m:
        m.setattr(pair, "validate_binding", offline_binding)
        m.setattr(pair, "validate_authority", offline_authority)
        m.setattr(pair, "validate_collection_admission", offline_admission)
        m.setattr(subprocess, "Popen", launch)
        m.setattr(transport, "fetch_batch", batch)
        m.setattr(observer, "poll", poll)
        tls.active = True
        try:
            # Actual closed wire/admission validators reject stale producer data.
            owner = pair.Control(time.monotonic_ns(), binding["valid_until_epoch_ns"], 10)
            stale = dict(command, version="stage12_selected_pair_discriminator_window_exact_commands_v4")
            with pytest.raises(tc.Stop):
                driver.load_verified_admission(plan, stale, owner, pair, transport, observer,
                                               nonwaiting_module=terminal)
            for inject in (False, True):
                tls.inject = inject
                base = root / ("driver-injected" if inject else "driver-strict-scope")
                base.mkdir(mode=0o700)
                records = []
                out = driver.execute_nonwaiting(plan, command, rows, ancestors, base,
                    (tc, pair, transport, verify), observer, terminal, None,
                    lambda *args: None, lambda: None,
                    lambda name, value: records.append((name, copy.deepcopy(value))), {})
                assert out["status"] == "INCOMPLETE"
                assert out["actual_client_exit"] == 0 and out["client_joined"]
                first = out["first_failure"]
                assert first["stage"] == ("OBSERVE" if inject else "READY"), first
                assert first["first_failure_descriptor"]["exception_class"] == ("TYPE_ERROR" if inject else "ASSERTION_ERROR")
                assert not first["first_failure_descriptor"]["retention_uncertain"]
                assert "TEST_ONLY_SECRET" not in str(out)
                assert any(name == "SUBMISSION_CLIENT_FACTS.record" for name, _ in records)
                entry = next(value for name, value in records if name == "EXECUTION_ENTRY.record")
                assert entry["actual_admission_process_cap"] is None
                assert entry["task_administrative_process_cap_retired"] is True
                put(base / "TEST_ONLY_RESULT.record", out)
                outputs.append(out)
        finally:
            tls.active = False
    assert len(outputs) == 2 and children and all(child.poll() is not None for child in children)
    assert all(child.wait(timeout=0) == 0 for child in children)
    assert all(child.stdout is None or child.stdout.closed for child in children)
    assert all(child.stderr is None or child.stderr.closed for child in children)


def test_actual_driver_canonical_probe_and_pair_receipt_ack_reopen(tmp_path, monkeypatch):
    from test_stage12_ra_g1_terminal_parent import test_actual_pair_fifo_transport_receipt_and_final_log_boundary
    test_actual_pair_fifo_transport_receipt_and_final_log_boundary(
        tmp_path, monkeypatch, "driver_connected")
