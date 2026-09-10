"""Bounded synthetic-only filesystem probe; never a materializer or fallback.

The guarded CLI creates a new private directory containing only fixed invented
sentinels. No scientific inputs are accepted. A completed diagnostic may report
an unavailable primitive; it does not authorize publication or a protected run.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import os
import re
import stat
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..execution_policy import require_goethe_nhr_slurm
from .stages import s09_reference_contract as c
from .stages import s09_reference_io as io


DIAGNOSTIC_VERSION = "stage09_synthetic_filesystem_diagnostic_v1"
DIAGNOSTIC_PARENT = Path(
    "/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/"
    "stage09/filesystem_diagnostics"
)
REPORT_NAME = "stage09_filesystem_diagnostic.json"
SOURCE_SENTINEL = b"invented filesystem source sentinel\n"
TARGET_SENTINEL = b"invented filesystem target sentinel\n"


def native_call(source: Path, target: Path, operation: str) -> dict[str, Any]:
    """Capture errno immediately, before another native/Python filesystem call."""
    c.require(
        operation in ("NOREPLACE", "ZERO_FLAGS", "POSIX_BASELINE"),
        "PROBE_OPERATION_INVALID",
    )
    library = ctypes.CDLL(None, use_errno=True)
    arguments: list[Any]
    signature: list[Any]
    if operation == "POSIX_BASELINE":
        name, flags = "rename", None
        arguments = [os.fsencode(source), os.fsencode(target)]
        signature = [ctypes.c_char_p, ctypes.c_char_p]
    elif sys.platform == "linux":
        name, flags = "renameat2", 1 if operation == "NOREPLACE" else 0
        arguments = [-100, os.fsencode(source), -100, os.fsencode(target), flags]
        signature = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
    elif sys.platform == "darwin":
        name, flags = "renamex_np", 4 if operation == "NOREPLACE" else 0
        arguments = [os.fsencode(source), os.fsencode(target), flags]
        signature = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    else:
        return {
            "api": "UNSUPPORTED_PLATFORM",
            "flags": None,
            "return_code": None,
            "errno": None,
            "errno_symbol": "UNAVAILABLE",
        }
    try:
        function = getattr(library, name)
    except AttributeError:
        return {
            "api": name,
            "flags": flags,
            "return_code": None,
            "errno": None,
            "errno_symbol": "SYMBOL_UNAVAILABLE",
        }
    function.argtypes, function.restype = signature, ctypes.c_int
    ctypes.set_errno(0)
    result = function(*arguments)
    error_number = ctypes.get_errno()
    return {
        "api": name,
        "flags": flags,
        "return_code": result,
        "errno": error_number,
        "errno_symbol": "NONE"
        if error_number == 0
        else errno.errorcode.get(error_number, "UNKNOWN_ERRNO"),
    }


def _identity(path: Path) -> tuple[int, int] | None:
    try:
        info = path.lstat()
        return info.st_dev, info.st_ino
    except FileNotFoundError:
        return None


def _fsync_probe(path: Path) -> dict[str, Any]:
    try:
        io.fsync_directory(path)
    except OSError as error:
        return {
            "ok": False,
            "errno": error.errno,
            "errno_symbol": errno.errorcode.get(error.errno or 0, "UNKNOWN_ERRNO"),
        }
    return {"ok": True, "errno": 0, "errno_symbol": "NONE"}


def probe_case(
    root: Path, case: str, operation: str, target_kind: str
) -> dict[str, Any]:
    c.require(
        target_kind in ("ABSENT", "EMPTY_DIRECTORY", "NONEMPTY_DIRECTORY", "FILE"),
        "PROBE_TARGET_KIND_INVALID",
    )
    # Never test ordinary replacing rename against an existing target, even a
    # synthetic one. Baselines are observations, not an enabled fallback.
    c.require(
        operation == "NOREPLACE" or target_kind == "ABSENT",
        "BASELINE_COLLISION_PROHIBITED",
    )
    parent = root / case
    parent.mkdir(mode=0o700)
    source, target = parent / "source", parent / "target"
    source.mkdir(mode=0o700)
    io.write_exclusive(source / "sentinel.txt", SOURCE_SENTINEL)
    if target_kind.endswith("DIRECTORY"):
        target.mkdir(mode=0o700)
        if target_kind == "NONEMPTY_DIRECTORY":
            io.write_exclusive(target / "sentinel.txt", TARGET_SENTINEL)
    elif target_kind == "FILE":
        io.write_exclusive(target, TARGET_SENTINEL)
    source_identity, target_identity = _identity(source), _identity(target)
    same_device = source.stat().st_dev == parent.stat().st_dev
    before_sync = _fsync_probe(parent)
    result = native_call(source, target, operation)
    after_sync = _fsync_probe(parent)
    source_after, target_after = _identity(source), _identity(target)
    source_intact = (
        source_after == source_identity
        and (source / "sentinel.txt").is_file()
        and (source / "sentinel.txt").read_bytes() == SOURCE_SENTINEL
    )
    moved_intact = (
        source_after is None
        and target_after == source_identity
        and target.is_dir()
        and (target / "sentinel.txt").is_file()
        and (target / "sentinel.txt").read_bytes() == SOURCE_SENTINEL
    )
    target_unchanged = target_after == target_identity
    if target_kind == "NONEMPTY_DIRECTORY":
        target_unchanged = (
            target_unchanged
            and (target / "sentinel.txt").is_file()
            and (target / "sentinel.txt").read_bytes() == TARGET_SENTINEL
        )
    elif target_kind == "EMPTY_DIRECTORY":
        target_unchanged = (
            target_unchanged and target.is_dir() and not any(target.iterdir())
        )
    elif target_kind == "FILE":
        target_unchanged = (
            target_unchanged
            and target.is_file()
            and target.read_bytes() == TARGET_SENTINEL
        )
    # Return code and observed filesystem effect must agree. Failed or
    # unavailable primitives are useful diagnostic results, not hidden errors.
    effect_consistent = (
        moved_intact
        if result["return_code"] == 0 and target_kind == "ABSENT"
        else source_intact and target_unchanged
        if result["return_code"] != 0
        else False
    )
    return {
        "case": case,
        "operation": operation,
        "target_kind_before": target_kind,
        **result,
        "same_filesystem": same_device,
        "source_retained_intact": source_intact,
        "source_moved_intact_same_invocation_identity": moved_intact,
        "original_target_unchanged": target_unchanged,
        "effect_consistent": effect_consistent,
        "directory_fsync_before": before_sync,
        "directory_fsync_after": after_sync,
    }


def collect_synthetic(root: Path, execution_sha: str, job_id: str) -> dict[str, Any]:
    """Lower-level synthetic test seam; has no data-input arguments or reads."""
    c.require(not os.path.lexists(root), "DIAGNOSTIC_TARGET_EXISTS")
    c.require(
        root.parent.is_dir() and not root.parent.is_symlink(),
        "DIAGNOSTIC_PARENT_INVALID",
    )
    c.require(
        stat.S_IMODE(root.parent.stat().st_mode) == 0o700,
        "DIAGNOSTIC_PARENT_NOT_PRIVATE",
    )
    root.mkdir(mode=0o700)
    cases = [
        ("noreplace_fresh", "NOREPLACE", "ABSENT"),
        ("noreplace_empty_collision", "NOREPLACE", "EMPTY_DIRECTORY"),
        ("noreplace_nonempty_collision", "NOREPLACE", "NONEMPTY_DIRECTORY"),
        ("noreplace_file_collision", "NOREPLACE", "FILE"),
        ("zero_flags_fresh", "ZERO_FLAGS", "ABSENT"),
        ("posix_baseline_fresh", "POSIX_BASELINE", "ABSENT"),
    ]
    records = [probe_case(root, *case) for case in cases]
    no_replace_supported = (
        records[0]["return_code"] == 0
        and all(row["return_code"] not in (0, None) for row in records[1:4])
        and all(
            row["effect_consistent"] and row["same_filesystem"] for row in records[:4]
        )
        and all(
            row["directory_fsync_before"]["ok"] and row["directory_fsync_after"]["ok"]
            for row in records[:4]
        )
    )
    payload = {
        "diagnostic_version": DIAGNOSTIC_VERSION,
        "scope": "SYNTHETIC_FILESYSTEM_ONLY",
        "execution_git_sha": execution_sha,
        "slurm_job_id": job_id,
        "platform": sys.platform,
        "kernel_release": os.uname().release,
        "semantic_runtime": list(c.SEMANTIC_RUNTIME),
        "cases": records,
        "noreplace_supported_in_this_probe": no_replace_supported,
        "all_observed_effects_consistent": all(
            row["effect_consistent"] for row in records
        ),
        "protected_payloads_opened": 0,
        "reference_payloads_opened": 0,
        "network_calls": 0,
        "materializer_invoked": False,
        "publication_fallback_enabled": False,
        "stage09_candidate": False,
    }
    io.write_json(root / REPORT_NAME, payload)
    io.fsync_directory(root)
    io.topology(root)
    return payload


def validate_cli_target(root: Path, execution_sha: str) -> None:
    require_goethe_nhr_slurm("stage09-synthetic-filesystem-diagnostic")
    c.require_runtime()
    c.require(
        bool(re.fullmatch("[0-9a-f]{40}", execution_sha)),
        "DIAGNOSTIC_EXECUTABLE_SHA_INVALID",
    )
    c.require(
        not root.is_symlink() and root.parent.resolve() == DIAGNOSTIC_PARENT.resolve(),
        "DIAGNOSTIC_SCOPE_PATH_REQUIRED",
    )
    c.require(
        bool(
            re.fullmatch(r"stage09_fsdiag_[0-9]{8}T[0-9]{6}Z_[0-9a-f]{12}", root.name)
        ),
        "DIAGNOSTIC_RUN_NAME_INVALID",
    )
    repository = Path(__file__).resolve().parents[3]
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository, text=True
    ).strip()
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=repository, text=True
    )
    branch = subprocess.run(
        ["git", "symbolic-ref", "-q", "HEAD"], cwd=repository, capture_output=True
    )
    c.require(
        head == execution_sha and not dirty and branch.returncode == 1,
        "DIAGNOSTIC_CLEAN_DETACHED_EXECUTABLE_REQUIRED",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Synthetic-only Stage 9 filesystem probe; no materialization or input data."
    )
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--execution-git-sha", required=True)
    args = parser.parse_args(argv)
    try:
        validate_cli_target(args.output_directory, args.execution_git_sha)
        payload = collect_synthetic(
            args.output_directory, args.execution_git_sha, os.environ["SLURM_JOB_ID"]
        )
        digest = c.sha256_file(args.output_directory / REPORT_NAME)
    except BaseException:
        # No arbitrary exception payload or supplied path is printed.
        print("STAGE09_SYNTHETIC_FILESYSTEM_DIAGNOSTIC_INCOMPLETE", file=sys.stderr)
        return 1
    print("status=STAGE09_SYNTHETIC_FILESYSTEM_DIAGNOSTIC_COLLECTED_NOT_A_CANDIDATE")
    print("diagnostic_sha256=" + digest)
    print(
        "noreplace_supported="
        + str(payload["noreplace_supported_in_this_probe"]).lower()
    )
    for row in payload["cases"]:
        print(
            f"case={row['case']} return_code={row['return_code']} errno={row['errno']} errno_symbol={row['errno_symbol']} effect_consistent={str(row['effect_consistent']).lower()}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
