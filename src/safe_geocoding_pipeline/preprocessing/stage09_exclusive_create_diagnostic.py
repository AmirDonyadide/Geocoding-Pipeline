"""One synthetic-only exclusive-create probe; not publication integration.

Independent spawned processes wait on parent-controlled anonymous pipes. Only
after every worker is ready does the parent release the barrier. No sockets,
reference/scientific inputs, fallback, cleanup of attempts or job submission.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import multiprocessing as mp
import os
import stat
import subprocess
import sys
import time
from collections.abc import Sequence
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any

from . import stage09_filesystem_diagnostic as previous
from .stages import s09_reference_contract as c
from .stages import s09_reference_io as io

VERSION = "stage09_exclusive_create_diagnostic_v1"
REPORT = "stage09_exclusive_create_diagnostic.json"
WORKERS = 4
TIMEOUT = 20
SENTINEL = b"invented exclusive-create sentinel\n"
METADATA = b'{"scope":"SYNTHETIC_ONLY","fixture":"commit-seal"}\n'


def error_record(number: int | None = 0) -> dict[str, Any]:
    return {
        "ok": number == 0,
        "errno": number,
        "errno_symbol": "NONE"
        if number == 0
        else errno.errorcode.get(number or 0, "UNKNOWN_ERRNO"),
    }


def native_create(path: Path, operation: str) -> dict[str, Any]:
    c.require(operation in ("OPEN", "MKDIR"), "DIAGNOSTIC_OPERATION_INVALID")
    library = ctypes.CDLL(None, use_errno=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    name = "open" if operation == "OPEN" else "mkdir"
    try:
        function = getattr(library, name)
    except AttributeError:
        return {
            "api": name,
            "flags": flags if operation == "OPEN" else None,
            "return_code": None,
            "errno": None,
            "errno_symbol": "SYMBOL_UNAVAILABLE",
        }
    function.restype = ctypes.c_int
    # open is variadic: declare only fixed arguments (required by Darwin
    # arm64's variadic ABI); explicitly type the creation mode at the call.
    function.argtypes = (
        [ctypes.c_char_p, ctypes.c_int]
        if operation == "OPEN"
        else [ctypes.c_char_p, ctypes.c_uint]
    )
    ctypes.set_errno(0)
    result = (
        function(os.fsencode(path), flags, ctypes.c_uint(0o600))
        if operation == "OPEN"
        else function(os.fsencode(path), 0o700)
    )
    number = ctypes.get_errno()  # Must precede any other native/filesystem call.
    return {
        "api": name,
        "flags": flags if operation == "OPEN" else None,
        "return_code": result,
        "errno": number,
        "errno_symbol": "NONE"
        if number == 0
        else errno.errorcode.get(number, "UNKNOWN_ERRNO"),
    }


def attempt(path: Path, operation: str, payload: bytes | None) -> dict[str, Any]:
    result = native_create(path, operation)
    result["post_create_io"] = error_record()
    rc = result["return_code"]
    result["won"] = rc is not None and (rc >= 0 if operation == "OPEN" else rc == 0)
    if not result["won"]:
        return result
    try:
        if operation == "OPEN":
            # A sequential collision probe passes None and never writes, even
            # if a broken primitive unexpectedly returns a usable descriptor.
            try:
                if payload is not None:
                    position = 0
                    while position < len(payload):
                        written = os.write(rc, payload[position:])
                        if written == 0:
                            raise OSError(errno.EIO, "SHORT_WRITE")
                        position += written
                os.fsync(rc)
            finally:
                os.close(rc)
        elif payload is not None:
            io.write_exclusive(path / "owner.txt", payload)
            io.fsync_directory(path)
    except OSError as error:
        result["post_create_io"] = error_record(error.errno)
    return result


def directory_sync(path: Path) -> dict[str, Any]:
    try:
        io.fsync_directory(path)
    except OSError as error:
        return error_record(error.errno)
    return error_record()


def verify_file(path: Path, expected: bytes) -> dict[str, Any]:
    observations = []
    details = []
    try:
        for _ in range(3):
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                info = os.fstat(fd)
                ok = (
                    stat.S_ISREG(info.st_mode)
                    and stat.S_IMODE(info.st_mode) == 0o600
                    and info.st_uid == os.geteuid()
                    and info.st_nlink == 1
                    and info.st_size == len(expected)
                )
                data = os.read(fd, len(expected) + 1) if ok else b"INVALID_TOPOLOGY"
                observations.append(ok and data == expected)
                details.append(
                    {
                        "bytes": info.st_size,
                        "mode": format(stat.S_IMODE(info.st_mode), "04o"),
                        "links": info.st_nlink,
                        "owner_matches": info.st_uid == os.geteuid(),
                        "bytes_match": ok and data == expected,
                    }
                )
            finally:
                os.close(fd)
    except OSError as error:
        return {
            "ok": False,
            "reopens": len(observations),
            "error": error_record(error.errno),
        }
    return {
        "ok": all(observations),
        "reopens": 3,
        "expected_sha256": hashlib.sha256(expected).hexdigest(),
        "observations": details,
    }


def same_identity(path: Path, identity: tuple[int, int]) -> bool:
    try:
        info = path.lstat()
        return (info.st_dev, info.st_ino) == identity
    except FileNotFoundError:
        return False


def sequential(
    root: Path, name: str, operation: str, seal: bool = False
) -> dict[str, Any]:
    parent = root / name
    parent.mkdir(mode=0o700)
    target = parent / (
        "_COMMITTED"
        if seal
        else "publication-run"
        if operation == "MKDIR"
        else "record.txt"
    )
    payload = b"" if seal else SENTINEL
    if seal:
        io.write_exclusive(parent / "_SUCCESS.json", METADATA)
        io.fsync_directory(parent)
    before = directory_sync(parent)
    fresh = attempt(target, operation, payload)
    between = directory_sync(parent)
    info = target.lstat() if os.path.lexists(target) else None
    owned = (info.st_dev, info.st_ino) if info is not None else (-1, -1)
    collision = attempt(target, operation, None)
    after = directory_sync(parent)
    observation = verify_file(
        target / "owner.txt" if operation == "MKDIR" else target, payload
    )
    preserved = same_identity(target, owned)
    ok = (
        fresh["won"]
        and fresh["errno"] == 0
        and fresh["post_create_io"]["ok"]
        and collision["return_code"] == -1
        and collision["errno"] == errno.EEXIST
        and observation["ok"]
        and preserved
        and all(r["ok"] for r in (before, between, after))
    )
    if seal:
        ok = ok and verify_file(parent / "_SUCCESS.json", METADATA)["ok"]
    return {
        "case": name,
        "fresh": fresh,
        "collision": collision,
        "directory_fsync": [before, between, after],
        "reopen": observation,
        "same_invocation_identity_preserved": preserved,
        "passed": bool(ok),
    }


def worker(
    target: str,
    operation: str,
    number: int,
    seal: bool,
    start: Connection,
    result: Connection,
) -> None:
    try:
        result.send({"ready": number, "pid": os.getpid()})
        if not start.poll(TIMEOUT) or start.recv() != "GO":
            raise RuntimeError("BARRIER_TIMEOUT")
        began = time.monotonic_ns()
        payload = b"" if seal else f"invented contender {number}\n".encode("ascii")
        outcome = attempt(Path(target), operation, payload)
        result.send(
            {"worker": number, "pid": os.getpid(), "started_ns": began, **outcome}
        )
    except BaseException:
        result.send(
            {"worker": number, "pid": os.getpid(), "worker_error": "INCOMPLETE"}
        )
    finally:
        start.close()
        result.close()


def concurrent(
    root: Path, name: str, operation: str, seal: bool = False
) -> dict[str, Any]:
    parent = root / name
    parent.mkdir(mode=0o700)
    target = parent / (
        "_COMMITTED"
        if seal
        else "publication-run"
        if operation == "MKDIR"
        else "record.txt"
    )
    if seal:
        io.write_exclusive(parent / "_SUCCESS.json", METADATA)
    before = directory_sync(parent)
    context = mp.get_context("spawn")
    processes = []
    pipes = []
    outcomes: list[dict[str, Any]] = []
    ready = []
    barrier_ok = False
    try:
        for number in range(WORKERS):
            start_read, start_write = context.Pipe(duplex=False)
            result_read, result_write = context.Pipe(duplex=False)
            process = context.Process(
                target=worker,
                args=(str(target), operation, number, seal, start_read, result_write),
            )
            process.start()
            start_read.close()
            result_write.close()
            processes.append(process)
            pipes.append((start_write, result_read))
        for _, result_pipe in pipes:
            c.require(result_pipe.poll(TIMEOUT), "DIAGNOSTIC_BARRIER_TIMEOUT")
            ready.append(result_pipe.recv())
        barrier_ok = {r.get("ready") for r in ready} == set(range(WORKERS)) and len(
            {r.get("pid") for r in ready}
        ) == WORKERS
        c.require(barrier_ok, "DIAGNOSTIC_BARRIER_INVALID")
        released = time.monotonic_ns()
        for start_pipe, _ in pipes:
            start_pipe.send("GO")
        for _, result_pipe in pipes:
            c.require(result_pipe.poll(TIMEOUT), "DIAGNOSTIC_WORKER_TIMEOUT")
            outcomes.append(result_pipe.recv())
        barrier_ok = (
            all(r.get("started_ns", 0) >= released for r in outcomes)
            and {r.get("worker") for r in outcomes} == set(range(WORKERS))
            and all(r.get("pid") == ready[r["worker"]]["pid"] for r in outcomes)
        )
        for process in processes:
            process.join(TIMEOUT)
        clean_exits = all(p.exitcode == 0 for p in processes)
    finally:
        # Only this probe's own stalled workers may be terminated; no SLURM
        # cancellation or deletion/cleanup of any diagnostic file is performed.
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(2)
        for pair in pipes:
            for pipe in pair:
                pipe.close()
    after = directory_sync(parent)
    winners = [r for r in outcomes if r.get("won")]
    losers = [r for r in outcomes if not r.get("won")]
    expected = (
        (
            b""
            if seal
            else f"invented contender {winners[0]['worker']}\n".encode("ascii")
        )
        if len(winners) == 1
        else b"INVALID_WINNER_COUNT"
    )
    observation = verify_file(
        target / "owner.txt" if operation == "MKDIR" else target, expected
    )
    ok = (
        barrier_ok
        and clean_exits
        and len(winners) == 1
        and len(losers) == WORKERS - 1
        and winners[0]["errno"] == 0
        and winners[0]["post_create_io"]["ok"]
        and all(
            r.get("return_code") == -1 and r.get("errno") == errno.EEXIST
            for r in losers
        )
        and before["ok"]
        and after["ok"]
        and observation["ok"]
    )
    if seal:
        ok = ok and verify_file(parent / "_SUCCESS.json", METADATA)["ok"]
    return {
        "case": name,
        "attempts": WORKERS,
        "winners": len(winners),
        "losers": len(losers),
        "barrier_all_ready_before_release": barrier_ok,
        "distinct_processes": len({r["pid"] for r in ready}),
        "workers": sorted(outcomes, key=lambda r: r["worker"]),
        "all_workers_exit_zero": clean_exits,
        "directory_fsync": [before, after],
        "reopen": observation,
        "passed": bool(ok),
    }


def symlink_case(root: Path, operation: str, dangling: bool) -> dict[str, Any]:
    name = f"symlink_{operation.lower()}_{'dangling' if dangling else 'existing'}"
    parent = root / name
    parent.mkdir(mode=0o700)
    target, link = parent / "referent.txt", parent / "_COMMITTED"
    if not dangling:
        io.write_exclusive(target, SENTINEL)
    link.symlink_to("referent.txt")
    info = link.lstat()
    before = directory_sync(parent)
    result = attempt(link, operation, None)
    after = directory_sync(parent)
    untouched = (
        same_identity(link, (info.st_dev, info.st_ino))
        and link.is_symlink()
        and os.readlink(link) == "referent.txt"
        and (
            not os.path.lexists(target)
            if dangling
            else verify_file(target, SENTINEL)["ok"]
        )
    )
    return {
        "case": name,
        "operation": result,
        "symlink_and_referent_unchanged": untouched,
        "directory_fsync": [before, after],
        "passed": bool(
            untouched
            and before["ok"]
            and after["ok"]
            and result["return_code"] == -1
            and result["errno"] == errno.EEXIST
        ),
    }


def private_topology(root: Path) -> None:
    allowed = {
        f"symlink_{op}_{kind}/_COMMITTED"
        for op in ("open", "mkdir")
        for kind in ("existing", "dangling")
    }
    seen = set()
    for directory, children, files in os.walk(root, followlinks=False):
        info = Path(directory).lstat()
        c.require(
            stat.S_ISDIR(info.st_mode)
            and stat.S_IMODE(info.st_mode) == 0o700
            and info.st_uid == os.geteuid(),
            "DIAGNOSTIC_DIRECTORY_TOPOLOGY",
        )
        for name in (*children, *files):
            path = Path(directory) / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                relative = path.relative_to(root).as_posix()
                c.require(
                    relative in allowed and os.readlink(path) == "referent.txt",
                    "DIAGNOSTIC_UNEXPECTED_SYMLINK",
                )
                seen.add(relative)
            elif not stat.S_ISDIR(info.st_mode):
                c.require(
                    stat.S_ISREG(info.st_mode)
                    and stat.S_IMODE(info.st_mode) == 0o600
                    and info.st_nlink == 1
                    and info.st_uid == os.geteuid(),
                    "DIAGNOSTIC_FILE_TOPOLOGY",
                )
    c.require(seen == allowed, "DIAGNOSTIC_SYMLINK_FIXTURE_INVENTORY")


def collect_synthetic(root: Path, execution_sha: str, job_id: str) -> dict[str, Any]:
    c.require(not os.path.lexists(root), "DIAGNOSTIC_TARGET_EXISTS")
    c.require(
        root.parent.is_dir()
        and not root.parent.is_symlink()
        and stat.S_IMODE(root.parent.stat().st_mode) == 0o700
        and root.parent.stat().st_uid == os.geteuid(),
        "DIAGNOSTIC_PARENT_INVALID",
    )
    root.mkdir(mode=0o700)
    cases = [
        sequential(root, "exclusive_record", "OPEN"),
        sequential(root, "commit_seal", "OPEN", True),
        sequential(root, "reservation", "MKDIR"),
        concurrent(root, "concurrent_record", "OPEN"),
        concurrent(root, "concurrent_seal", "OPEN", True),
        concurrent(root, "concurrent_reservation", "MKDIR"),
    ]
    cases.extend(
        symlink_case(root, op, dangling)
        for op in ("OPEN", "MKDIR")
        for dangling in (False, True)
    )
    private_topology(root)
    filesystem = (
        subprocess.check_output(
            ["stat", "-f", "-c", "%T", str(root)], text=True
        ).strip()
        if sys.platform == "linux"
        else "LOCAL_NON_LINUX"
    )
    report = {
        "diagnostic_version": VERSION,
        "scope": "SYNTHETIC_EXCLUSIVE_CREATE_ONLY",
        "execution_git_sha": execution_sha,
        "slurm_job_id": job_id,
        "platform": sys.platform,
        "kernel_release": os.uname().release,
        "filesystem_type": filesystem,
        "semantic_runtime": list(c.SEMANTIC_RUNTIME),
        "cases": cases,
        "required_semantics_passed": all(r["passed"] for r in cases),
        "private_topology_passed": True,
        "synthetic_symlinks_allowlisted": 4,
        "protected_payloads_opened": 0,
        "reference_payloads_opened": 0,
        "network_calls": 0,
        "materializer_invoked": False,
        "publication_protocol_integrated": False,
        "development_retry_submitted": False,
        "stage09_candidate": False,
    }
    io.write_json(root / REPORT, report)
    io.fsync_directory(root)
    private_topology(root)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Synthetic-only exclusive-create diagnostic; no scientific inputs."
    )
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--execution-git-sha", required=True)
    args = parser.parse_args(argv)
    try:
        previous.validate_cli_target(args.output_directory, args.execution_git_sha)
        report = collect_synthetic(
            args.output_directory, args.execution_git_sha, os.environ["SLURM_JOB_ID"]
        )
        c.require(report["filesystem_type"] == "panfs", "DIAGNOSTIC_PANFS_REQUIRED")
        digest = c.sha256_file(args.output_directory / REPORT)
    except BaseException:
        print("STAGE09_EXCLUSIVE_CREATE_DIAGNOSTIC_INCOMPLETE", file=sys.stderr)
        return 1
    print("status=STAGE09_EXCLUSIVE_CREATE_DIAGNOSTIC_COLLECTED_NOT_A_CANDIDATE")
    print("diagnostic_sha256=" + digest)
    print(
        "required_semantics_passed=" + str(report["required_semantics_passed"]).lower()
    )
    return 0 if report["required_semantics_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
