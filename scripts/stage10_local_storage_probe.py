"""Public-only Goethe job-local filesystem probe; no scientific input access."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pwd
import socket
import sqlite3
import stat
import subprocess
from pathlib import Path
from typing import Any

from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm


def sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def exclusive_write(path: Path, content: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    sync_directory(path.parent)


def capacity(path: Path) -> dict[str, int]:
    value = os.statvfs(path)
    return {
        "total_bytes": value.f_blocks * value.f_frsize,
        "available_bytes": value.f_bavail * value.f_frsize,
        "available_inodes": value.f_favail,
        "device": path.stat().st_dev,
    }


def main() -> int:
    require_goethe_nhr_slurm("stage10-public-local-storage-probe")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt-directory", type=Path, required=True)
    parser.add_argument("--panfs-copy-directory", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    job = os.environ["SLURM_JOB_ID"]
    if not job.isdecimal() or pwd.getpwuid(os.getuid()).pw_name != "donyadidegan":
        raise RuntimeError("PROBE_EXECUTION_IDENTITY_INVALID")
    local = Path("/local") / job
    if not local.is_dir() or local.is_symlink():
        raise RuntimeError("JOB_LOCAL_ROOT_ABSENT_OR_SYMLINK")
    if local.stat().st_uid != os.getuid():
        raise RuntimeError("JOB_LOCAL_ROOT_NOT_USER_OWNED")
    for root in (args.receipt_directory, args.panfs_copy_directory):
        if root.is_symlink() or root.stat().st_uid != os.getuid():
            raise RuntimeError("PROBE_DESTINATION_IDENTITY_INVALID")
        if stat.S_IMODE(root.stat().st_mode) != 0o700:
            raise RuntimeError("PROBE_DESTINATION_NOT_PRIVATE")
    result: dict[str, Any] = {
        "kind": "STAGE10_PUBLIC_LOCAL_STORAGE_PROBE",
        "job_id": job,
        "hostname": socket.gethostname(),
        "execution_git_sha": os.environ["STAGE10_PROBE_GIT_SHA"],
        "requested_tmp_mib": 1024,
        "protected_payloads_accessed": 0,
        "scientific_candidate_publication": False,
        "local_root": str(local),
        "local_root_uid": local.stat().st_uid,
        "local_root_mode": oct(stat.S_IMODE(local.stat().st_mode)),
        "local_before": capacity(local),
    }
    work = local / "safe-stage10-public-storage-probe"
    work.mkdir(mode=0o700)
    # Deterministic invented bytes, 16 MiB. No source/project payload is opened.
    block = b"".join(
        hashlib.sha256(str(i).encode("ascii")).digest() for i in range(32768)
    )
    payload = block * 16
    expected = hashlib.sha256(payload).hexdigest()
    original = work / "synthetic.bin"
    exclusive_write(original, payload)
    renamed = work / "synthetic-renamed.bin"
    original.rename(renamed)
    sync_directory(work)
    if hashlib.sha256(renamed.read_bytes()).hexdigest() != expected:
        raise RuntimeError("LOCAL_READBACK_HASH_MISMATCH")
    db = work / "synthetic.sqlite3"
    with sqlite3.connect(db) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(
            "CREATE TABLE synthetic (id INTEGER PRIMARY KEY, value BLOB)"
        )
        connection.executemany(
            "INSERT INTO synthetic VALUES (?, ?)",
            ((i, hashlib.sha256(str(i).encode("ascii")).digest()) for i in range(1000)),
        )
        connection.commit()
        if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise RuntimeError("SQLITE_INTEGRITY_FAILED")
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    connection.close()
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as readback:
        if readback.execute("SELECT count(*) FROM synthetic").fetchone() != (1000,):
            raise RuntimeError("SQLITE_REOPEN_FAILED")
    readback.close()
    sync_directory(work)
    # Small synthetic copy verifies cross-filesystem write/fsync/hash only.
    # It is never a scientific artifact, registration or _COMMITTED seal.
    copy_path = args.panfs_copy_directory / f"synthetic-copy-{job}.bin"
    copied = payload[:65536]
    exclusive_write(copy_path, copied)
    if copy_path.stat().st_dev == work.stat().st_dev:
        raise RuntimeError("CROSS_FILESYSTEM_TEST_NOT_DISTINCT")
    if (
        hashlib.sha256(copy_path.read_bytes()).digest()
        != hashlib.sha256(copied).digest()
    ):
        raise RuntimeError("PANFS_COPY_HASH_MISMATCH")
    modes = {p.name: oct(stat.S_IMODE(p.stat().st_mode)) for p in work.iterdir()}
    if any(value != "0o600" for value in modes.values()):
        raise RuntimeError("SYNTHETIC_FILE_PERMISSION_MISMATCH")
    result.update(
        status="PASS",
        local_after=capacity(local),
        private_directory_mode=oct(stat.S_IMODE(work.stat().st_mode)),
        synthetic_file_modes=modes,
        synthetic_sha256=expected,
        synthetic_bytes=len(payload),
        sqlite_rows=1000,
        sqlite_integrity="PASS",
        local_fsync="PASS",
        directory_fsync="PASS",
        cross_filesystem_copy_hash="PASS",
        panfs_copy_bytes=len(copied),
        cleanup_marker=str(renamed),
        cleanup_observed=False,
        filesystem=subprocess.check_output(
            ["findmnt", "-n", "-T", str(local), "-o", "FSTYPE,TARGET,OPTIONS"],
            text=True,
        ).strip(),
    )
    raw = (json.dumps(result, sort_keys=True) + "\n").encode("utf-8")
    exclusive_write(args.receipt_directory / f"result-{job}.json", raw)
    print(raw.decode("utf-8"), end="", flush=True)
    # Leave only our invented test data for the scheduler epilog; never assume
    # successful cleanup until separately observed or label it documentation-only.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
