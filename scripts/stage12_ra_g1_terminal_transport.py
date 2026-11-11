"""Bounded task-specific raw transfer of already verified synthetic originals.

SSH serves exact immutable files without Python, hashing, unpacking or data
transformation on the login node. Source FD identity inside that tunnel is
unobserved: parent original identity/full-hash checks before READY and after
receipt enclose this transfer. This adds no native or scientific acceptance.
"""

from __future__ import annotations
import argparse
import hashlib
import os
from pathlib import Path
import selectors
import shlex
import signal
import subprocess
import sys
import time
import stage12_ra_g1_terminal_collect as tc
import stage12_ra_g1_terminal_parent as pair

CHUNK = 65536
MAX_STDERR = 65536
HOST = "goethe"


def need(value, code="RETENTION"):
    if not value:
        raise tc.Stop(code)


def remote_argv(host, path):
    need(host == HOST, "PATH")
    path = tc.absolute(str(path))
    # Fixed raw transfer only. Never interpolate a path without shell quoting.
    command = (
        "exec dd if=" + shlex.quote(str(path)) + " iflag=nofollow bs=65536 status=none"
    )
    return [
        "ssh",
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
        host,
        command,
    ]


def copy_process(argv, target, expected, control):
    """One exact framed artifact, no retry and no unbounded stdout/stderr list."""
    need(
        type(expected) is dict
        and type(expected["bytes"]) is int
        and expected["bytes"] >= 0
    )
    target = tc.absolute(str(target))
    tc.ancestors(target, links=False)
    tc.private(target.parent.lstat(), "DIR", os.geteuid())
    chain = tc.ancestors(target, links=False)
    root_identity = tc.ident(target.parent.lstat())[:5]
    control.check()
    need(control.creations < 128, "CREATIONS")
    control.creations += 1
    end = min(
        control.end, time.monotonic_ns() + max(0, control.epoch_end - time.time_ns())
    )
    kill_at = end - 2_000_000_000
    need(time.monotonic_ns() < kill_at, "DEADLINE")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    proc = None
    selector = None
    primary = None
    cleanup = False
    digest = hashlib.sha256()
    count = 0
    reserved = 0
    stderr_bytes = 0
    streams = set()
    joined = False
    try:
        control.check()
        origin = time.monotonic_ns()
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        need(proc.stdout is not None and proc.stderr is not None, "CHILD_LIFECYCLE")
        selector = selectors.DefaultSelector()
        for label, stream in (("stdout", proc.stdout), ("stderr", proc.stderr)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, label)
            streams.add(label)
        while streams or proc.poll() is None:
            control.check()
            need(time.monotonic_ns() < kill_at, "DEADLINE")
            for key, _ in selector.select(
                timeout=min(0.05, max(0, (kill_at - time.monotonic_ns()) / 1e9))
            ):
                n = (
                    min(CHUNK, expected["bytes"] - count + 1)
                    if key.data == "stdout"
                    else CHUNK
                )
                raw = control.read(key.fileobj.fileno(), max(1, n))
                if not raw:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                    streams.remove(key.data)
                    continue
                if key.data == "stderr":
                    stderr_bytes += len(raw)
                    need(stderr_bytes <= MAX_STDERR, "STDERR")
                    continue
                need(count + len(raw) <= expected["bytes"], "WRITE_BYTES")
                reserved += len(raw)
                need(reserved <= expected["bytes"], "WRITE_BYTES")
                digest.update(raw)
                count += len(raw)
                view = memoryview(raw)
                while view:
                    control.check()
                    wrote = os.write(fd, view)
                    need(wrote > 0, "WRITE_BYTES")
                    view = view[wrote:]
        code = proc.wait(timeout=0)
        joined = True
        control.check()
        need(
            code == 0
            and count == expected["bytes"]
            and digest.hexdigest() == expected["sha256"],
            "RETENTION",
        )
        os.fsync(fd)
        info = os.fstat(fd)
        tc.private(info, "FILE", os.geteuid())
        need(
            info.st_size == count and tc.ident(target.lstat()) == tc.ident(info),
            "SOURCE_CHANGED",
        )
        tc.check_ancestors(chain)
        need(tc.ident(target.parent.lstat())[:5] == root_identity, "SOURCE_CHANGED")
        dfd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(dfd)
        finally:
            tc.close_owned(control, (dfd,))
        control.check()
        return dict(
            bytes=count,
            sha256=digest.hexdigest(),
            exit_code=code,
            observed_joined=True,
            start_mono_ns=origin,
            end_mono_ns=time.monotonic_ns(),
            stderr_bytes=stderr_bytes,
            stderr_contents_retained=False,
            opaque_remote_fd_identity="UNOBSERVED",
        )
    except BaseException as error:
        primary = error
        raise
    finally:
        if proc is not None and proc.poll() is None:
            try:
                proc.send_signal(signal.SIGTERM)
                proc.wait(timeout=max(0, min(0.5, (end - time.monotonic_ns()) / 1e9)))
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(
                        timeout=max(0, min(0.5, (end - time.monotonic_ns()) / 1e9))
                    )
                except BaseException:
                    cleanup = True
            except BaseException:
                cleanup = True
        if proc is not None:
            joined = proc.poll() is not None
            for stream in (proc.stdout, proc.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except BaseException:
                        cleanup = True
        if selector is not None:
            try:
                selector.close()
            except BaseException:
                cleanup = True
        try:
            os.close(fd)
        except BaseException:
            cleanup = True
        if cleanup or (proc is not None and not joined):
            control.cleanup_uncertain = True
            if primary is None:
                raise tc.Stop("CLOSE_UNCERTAIN")
        if primary is None:
            control.check()


def fetch_ready(
    ready,
    ready_sha,
    local_root,
    control_root,
    *,
    host=HOST,
    testing_command_factory=None,
    control=None,
):
    entered = time.monotonic_ns()
    epoch = time.time_ns()
    pair.validate_ready(ready)
    need(pair.digest(tc.canonical(ready)) == ready_sha)
    if testing_command_factory is not None:
        need(ready["scope"] == pair.TEST, "SCOPE")
    else:
        need(ready["scope"] == pair.NATIVE and host == HOST, "SCOPE")
    if control is None:
        control = pair.Control(
            entered, ready["context"]["parent_deadline_epoch_ns"], 900
        )
    else:
        control.epoch_end = min(
            control.epoch_end, ready["context"]["parent_deadline_epoch_ns"]
        )
        control.check()
    local_root = tc.absolute(str(local_root))
    control_root = tc.absolute(str(control_root))
    need(
        local_root != control_root
        and not tc.contained(local_root, control_root)
        and not tc.contained(control_root, local_root),
        "PATH",
    )
    for directory in (local_root, control_root):
        tc.ancestors(directory)
        tc.private(directory.lstat(), "DIR", os.geteuid())
    with os.scandir(local_root) as entries:
        need(next(entries, None) is None, "OUTPUT")
    need(
        sum(row["bytes"] for row in ready["artifacts"])
        <= ready["local_retention_byte_limit"],
        "WRITE_BYTES",
    )
    reports = []
    for row in ready["artifacts"]:
        control.check()
        argv = (
            testing_command_factory(row)
            if testing_command_factory is not None
            else remote_argv(host, row["path"])
        )
        reports.append(
            dict(
                label=row["label"],
                **copy_process(
                    argv, local_root / (row["label"] + ".original"), row, control
                ),
            )
        )
    receipt_path = local_root / "RETENTION_RECEIPT.record"
    receipt = pair.verify_retention(
        ready, ready_sha, local_root, receipt_path, entered, epoch, control=control
    )
    control.check()
    result = dict(
        version="stage12_terminal_bounded_transport_v1",
        status="LOCAL_STREAMS_HASHED_AWAITING_NATIVE_ACK",
        ready_sha256=ready_sha,
        receipt_sha256=pair.digest(tc.canonical(receipt)),
        original_job_id=ready["context"]["original_job_id"],
        collection_job_id=ready["context"]["collection_job_id"],
        actual_read_bytes=control.read_bytes,
        actual_read_calls=control.read_calls,
        artifacts=reports,
        fetch_entered_mono_ns=entered,
        completed_mono_ns=time.monotonic_ns(),
        native_or_scientific_acceptance=False,
    )
    control.record(control_root / "LOCAL_TRANSPORT_RESULT.record", result)
    return receipt, result


def main(argv=None):
    entered = time.monotonic_ns()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ready", type=Path, required=True)
    parser.add_argument("--ready-sha256", required=True)
    parser.add_argument("--local-root", type=Path, required=True)
    parser.add_argument("--control-root", type=Path, required=True)
    args = parser.parse_args(argv)
    os.umask(0o077)
    bootstrap = pair.Control(entered, pair.WINDOW_END_NS, 900)
    try:
        ready = pair.load_control(args.ready, args.ready_sha256, bootstrap)
        _, result = fetch_ready(
            ready,
            args.ready_sha256,
            args.local_root,
            args.control_root,
            control=bootstrap,
        )
        sys.stdout.write(tc.canonical(result).decode())
        return 0
    except BaseException as error:
        sys.stderr.write(
            tc.canonical(
                dict(
                    version="stage12_terminal_bounded_transport_v1",
                    status="INCOMPLETE",
                    code=pair.safe_code(error),
                    cleanup_uncertain=bootstrap.cleanup_uncertain,
                    native_or_scientific_acceptance=False,
                )
            ).decode()
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
