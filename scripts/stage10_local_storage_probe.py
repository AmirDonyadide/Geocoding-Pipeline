"""Public-only Goethe job-local filesystem probe; no scientific input access."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import pwd
import re
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm

EXPECTED_PYTHON = Path(
    "/work/footprint/donyadidegan/safe_geocoding_pipeline/runtimes/stage06/"
    "stage06_development_20260828T223804Z_f39047cc825d/venv/bin/python"
)
LAUNCHER_BASE_SHA = "44154e5aeced9863132095eb4821d2a303dd56f6"
REQUESTED_TMP_MIB = 9216


def sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def exclusive_write(path: Path, content: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
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


def runtime_identity(expected_python: Path, checkout: Path) -> dict[str, Any]:
    # Checking prefix distinguishes the venv from the same underlying system binary.
    if (
        Path(sys.executable).absolute() != expected_python.absolute()
        or Path(sys.prefix).resolve() != expected_python.parent.parent.resolve()
    ):
        raise RuntimeError("PROBE_PYTHON_ENVIRONMENT_MISMATCH")
    import duckdb
    import safe_geocoding_pipeline as safe

    location = Path(str(safe.__file__)).resolve()
    if not location.is_relative_to(checkout.resolve() / "src"):
        raise RuntimeError("PROBE_SAFE_SOURCE_LOCATION_MISMATCH")
    distribution = importlib.metadata.distribution("safe-geocoding-pipeline")
    if distribution.version != "0.2.0" or duckdb.__version__ != "1.5.5":
        raise RuntimeError("PROBE_PACKAGE_VERSION_MISMATCH")
    return {
        "python_executable": sys.executable,
        "python_version": sys.version,
        "python_prefix": sys.prefix,
        "python_binary_realpath": str(Path(sys.executable).resolve()),
        "safe_package_version": distribution.version,
        "safe_package_location": str(location),
        "safe_distribution_location": str(distribution.locate_file("")),
        "duckdb_version": duckdb.__version__,
        "duckdb_location": str(Path(duckdb.__file__).resolve()),
    }


def remove_owned_file(path: Path, before: os.stat_result, *, expected_uid: int) -> None:
    current = path.lstat()
    if (
        not stat.S_ISREG(current.st_mode)
        or current.st_uid != expected_uid
        or before.st_uid != expected_uid
        or (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino)
        or current.st_nlink != 1
    ):
        raise RuntimeError("PROBE_CLEANUP_OWNERSHIP_OR_IDENTITY_MISMATCH")
    path.unlink()
    sync_directory(path.parent)


def copy_probe(source: Path, target: Path) -> dict[str, Any]:
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as dst, source.open("rb") as src:
        shutil.copyfileobj(src, dst, 65536)
        dst.flush()
        os.fsync(dst.fileno())
    sync_directory(target.parent)
    before = target.lstat()
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual != expected or stat.S_IMODE(before.st_mode) != 0o600:
        raise RuntimeError("PANFS_COPY_HASH_OR_MODE_MISMATCH")
    remove_owned_file(target, before, expected_uid=os.getuid())
    if target.exists():
        raise RuntimeError("PANFS_SYNTHETIC_CLEANUP_FAILED")
    return {
        "sha256_equal": True,
        "sha256": actual,
        "bytes": before.st_size,
        "allocated_bytes_used": before.st_blocks * 512,
        "allocated_bytes_released": before.st_blocks * 512,
        "mode": "0o600",
        "uid": before.st_uid,
        "fsync": "PASS",
        "cleanup": "PASS",
    }


def duckdb_probe(work: Path) -> dict[str, Any]:
    import duckdb

    database = work / "synthetic.duckdb"
    wal = work / "synthetic.duckdb.wal"
    spill = work / "duck-spill"
    spill.mkdir(mode=0o700)
    expected_rows = [
        (i, hashlib.sha256(str(i).encode("ascii")).digest()) for i in range(2048)
    ]
    digest = hashlib.sha256(b"".join(value for _, value in expected_rows)).hexdigest()
    db = duckdb.connect(str(database))
    try:
        db.execute("SET threads=1")
        db.execute("SET memory_limit='128MB'")
        db.execute("SET temp_directory=?", [str(spill)])
        db.execute("SET checkpoint_threshold='64MB'")
        db.execute("CREATE TABLE synthetic (id INTEGER PRIMARY KEY, value BLOB)")
        db.execute("BEGIN TRANSACTION")
        db.executemany("INSERT INTO synthetic VALUES (?, ?)", expected_rows)
        db.execute("COMMIT")
        wal_before = wal.stat().st_size if wal.exists() else 0
        if wal_before == 0:
            raise RuntimeError("DUCKDB_WAL_CYCLE_NOT_OBSERVED")
        db.execute(
            "CREATE TEMPORARY TABLE temporary_rows AS SELECT * FROM synthetic WHERE id<32"
        )
        temporary_rows = db.execute("SELECT count(*) FROM temporary_rows").fetchone()
        db.execute("BEGIN TRANSACTION")
        db.execute("INSERT INTO synthetic VALUES (9999, 'invented')")
        db.execute("ROLLBACK")
        rollback_rows = db.execute("SELECT count(*) FROM synthetic").fetchone()
        db.execute("CHECKPOINT")
        wal_after = wal.stat().st_size if wal.exists() else 0
    finally:
        db.close()
    with database.open("rb") as stream:
        os.fsync(stream.fileno())
    sync_directory(work)
    db = duckdb.connect(str(database), read_only=True)
    try:
        rows = db.execute("SELECT id, value FROM synthetic ORDER BY id").fetchall()
    finally:
        db.close()
    actual = hashlib.sha256(b"".join(bytes(row[1]) for row in rows)).hexdigest()
    if rows != expected_rows or actual != digest or wal_after != 0:
        raise RuntimeError("DUCKDB_CHECKPOINT_REOPEN_MISMATCH")
    if temporary_rows != (32,) or rollback_rows != (2048,):
        raise RuntimeError("DUCKDB_TEMPORARY_OR_ROLLBACK_MISMATCH")
    return {
        "rows": len(rows),
        "expected_hash": digest,
        "reopen_hash": actual,
        "wal_before_checkpoint_bytes": wal_before,
        "wal_after_checkpoint_bytes": wal_after,
        "temporary_table_rows": temporary_rows[0],
        "rollback_rows": rollback_rows[0],
        "checkpoint": "PASS",
        "close_reopen": "PASS",
        "fsync": "PASS",
    }


def local_probe(work: Path) -> dict[str, Any]:
    block = b"".join(
        hashlib.sha256(str(i).encode("ascii")).digest() for i in range(32768)
    )
    payload = block * 16
    expected = hashlib.sha256(payload).hexdigest()
    original = work / "synthetic.bin"
    exclusive_write(original, payload)
    if hashlib.sha256(original.read_bytes()).hexdigest() != expected:
        raise RuntimeError("LOCAL_READBACK_HASH_MISMATCH")
    renamed = work / "synthetic-renamed.bin"
    original.rename(renamed)
    sync_directory(work)
    if hashlib.sha256(renamed.read_bytes()).hexdigest() != expected:
        raise RuntimeError("LOCAL_RENAME_HASH_MISMATCH")
    temporary = work / "temporary.bin"
    exclusive_write(temporary, b"invented disposable local file")
    remove_owned_file(temporary, temporary.lstat(), expected_uid=os.getuid())
    db = work / "synthetic.sqlite3"
    expected_rows = [
        (i, hashlib.sha256(str(i).encode("ascii")).digest()) for i in range(1000)
    ]
    connection = sqlite3.connect(db)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(
            "CREATE TABLE synthetic (id INTEGER PRIMARY KEY, value BLOB)"
        )
        connection.executemany("INSERT INTO synthetic VALUES (?, ?)", expected_rows)
        connection.commit()
        if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise RuntimeError("SQLITE_INTEGRITY_FAILED")
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        connection.close()
    readback = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        if (
            readback.execute("SELECT id, value FROM synthetic ORDER BY id").fetchall()
            != expected_rows
        ):
            raise RuntimeError("SQLITE_REOPEN_FAILED")
    finally:
        readback.close()
    duck = duckdb_probe(work)
    exclusive_write(work / "copy-source.bin", payload[:65536])
    modes = {
        p.name: oct(stat.S_IMODE(p.stat().st_mode))
        for p in work.iterdir()
        if p.is_file()
    }
    if any(value != "0o600" for value in modes.values()):
        raise RuntimeError("SYNTHETIC_FILE_PERMISSION_MISMATCH")
    return {
        "synthetic_bytes": len(payload),
        "synthetic_sha256": expected,
        "write_read_fsync_close_reopen_hash": "PASS",
        "rename": "PASS",
        "temporary_file_cleanup": "PASS",
        "sqlite_rows": 1000,
        "sqlite_integrity_checkpoint_reopen": "PASS",
        "duckdb": duck,
        "file_modes": modes,
    }


def cleanup_local_files(work: Path) -> None:
    allowed = {
        "synthetic-renamed.bin",
        "synthetic.sqlite3",
        "synthetic.sqlite3-wal",
        "synthetic.sqlite3-shm",
        "synthetic.duckdb",
        "synthetic.duckdb.wal",
        "copy-source.bin",
    }
    children = list(work.iterdir())
    for path in children:
        value = path.lstat()
        if value.st_uid != os.getuid() or path.is_symlink():
            raise RuntimeError("LOCAL_CLEANUP_OWNERSHIP_MISMATCH")
        if path.name == "duck-spill":
            if not path.is_dir() or any(path.iterdir()):
                raise RuntimeError("LOCAL_SPILL_NOT_EMPTY")
        elif path.name not in allowed or not path.is_file():
            raise RuntimeError("LOCAL_CLEANUP_UNEXPECTED_OBJECT")
    for path in children:
        if path.name == "duck-spill":
            path.rmdir()
        else:
            remove_owned_file(path, path.lstat(), expected_uid=os.getuid())
    work.rmdir()
    sync_directory(work.parent)


def panfs_quota() -> dict[str, Any]:
    raw = subprocess.check_output(["pan_df", "-k", "/work/footprint"], text=True)
    match = re.search(
        r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+\d+%\s+/work/footprint\s*$", raw, re.MULTILINE
    )
    if match is None:
        raise RuntimeError("PANFS_QUOTA_OUTPUT_UNRECOGNIZED")
    return dict(
        zip(
            ("limit_kib", "used_kib", "available_kib"),
            map(int, match.groups()),
            strict=True,
        )
    )


def main() -> int:
    require_goethe_nhr_slurm("stage10-public-local-storage-probe")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt-directory", type=Path, required=True)
    parser.add_argument("--panfs-copy-directory", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    result: dict[str, Any] = {
        "kind": "STAGE10_PUBLIC_LOCAL_STORAGE_REPLACEMENT_PROBE",
        "phase": "runtime_identity",
    }
    try:
        checkout = Path(os.environ["STAGE10_PROBE_CHECKOUT"])
        result["environment"] = runtime_identity(EXPECTED_PYTHON, checkout)
        print(
            json.dumps({"runtime_identity": result["environment"]}, sort_keys=True),
            flush=True,
        )
        job = os.environ["SLURM_JOB_ID"]
        if not job.isdecimal() or pwd.getpwuid(os.getuid()).pw_name != "donyadidegan":
            raise RuntimeError("PROBE_EXECUTION_IDENTITY_INVALID")
        result.update(
            job_id=job,
            hostname=socket.gethostname(),
            execution_git_sha=os.environ["STAGE10_PROBE_GIT_SHA"],
            launcher_base_sha=LAUNCHER_BASE_SHA,
            requested_tmp_mib=REQUESTED_TMP_MIB,
            protected_payloads_accessed=0,
            scientific_candidate_publication=False,
        )
        result["phase"] = "scheduler_tmp_verification"
        scheduler = subprocess.check_output(
            ["scontrol", "show", "job", job, "-o"], text=True
        )
        match = re.search(r"\bMinTmpDiskNode=(\d+)([KMGT]?)\b", scheduler)
        if match is None:
            raise RuntimeError("SCHEDULER_TMP_IDENTITY_MISSING")
        amount = (
            int(match[1])
            * {"": 1024**2, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}[
                match[2]
            ]
        )
        if amount != REQUESTED_TMP_MIB * 1024**2:
            raise RuntimeError("SCHEDULER_TMP_REQUEST_MISMATCH")
        result["scheduler_tmp_bytes"] = amount
        local = Path("/local") / job
        result["phase"] = "local_root_validation"
        for root in (local, args.receipt_directory, args.panfs_copy_directory):
            value = root.lstat()
            if (
                root.is_symlink()
                or not root.is_dir()
                or value.st_uid != os.getuid()
                or stat.S_IMODE(value.st_mode) != 0o700
            ):
                raise RuntimeError("PROBE_ROOT_NOT_PRIVATE_AND_OWNED")
        result.update(
            local_root=str(local),
            local_root_uid=local.stat().st_uid,
            local_root_mode="0o700",
            local_before=capacity(local),
        )
        if capacity(local)["available_bytes"] < amount:
            raise RuntimeError("LOCAL_AVAILABLE_CAPACITY_BELOW_REQUEST")
        if local.stat().st_dev == args.panfs_copy_directory.stat().st_dev:
            raise RuntimeError("CROSS_FILESYSTEM_TEST_NOT_DISTINCT")
        work = local / "safe-stage10-public-storage-probe"
        work.mkdir(mode=0o700)
        result["phase"] = "local_file_sqlite_duckdb_io"
        result["local_io"] = local_probe(work)
        result["phase"] = "cross_filesystem_copy"
        result["panfs_quota_before_copy"] = panfs_quota()
        result["panfs_copy"] = copy_probe(
            work / "copy-source.bin",
            args.panfs_copy_directory / f"synthetic-copy-{job}.bin",
        )
        result["panfs_quota_after_cleanup"] = panfs_quota()
        result["phase"] = "local_cleanup"
        cleanup_local_files(work)
        result.update(
            local_cleanup="PASS",
            local_after=capacity(local),
            status="PASS",
            phase="complete",
        )
        raw = (json.dumps(result, sort_keys=True) + "\n").encode()
        exclusive_write(args.receipt_directory / f"result-{job}.json", raw)
        print(raw.decode(), end="", flush=True)
        return 0
    except BaseException as error:
        # Every input is invented/public; no protected strings exist in this probe.
        result.update(
            status="FAIL", exception_class=type(error).__name__, error=str(error)
        )
        raw = (json.dumps(result, sort_keys=True) + "\n").encode()
        try:
            exclusive_write(
                args.receipt_directory
                / f"failure-{os.environ.get('SLURM_JOB_ID', 'unknown')}.json",
                raw,
            )
        except OSError:
            pass
        print(raw.decode(), end="", flush=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
