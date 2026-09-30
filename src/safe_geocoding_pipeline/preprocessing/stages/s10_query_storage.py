"""Operational split storage; no workspace path participates in science identity."""

from __future__ import annotations

import os
import pwd
import re
import shutil
import stat
import tempfile
from pathlib import Path

from ...execution_policy import require_goethe_nhr_slurm
from . import s10_query_contract as c
from . import s10_query_io as io

LOCAL_BASE = Path("/local")
LOCAL_RESERVE = 9 * 1024**3
PANFS_RESERVE = 2 * 1024**3
PANFS_PLANNING_MINIMUM = 1184359936


def private_directory(path: Path) -> None:
    try:
        value = path.lstat()
        valid = (
            stat.S_ISDIR(value.st_mode)
            and value.st_uid == os.geteuid()
            and stat.S_IMODE(value.st_mode) == 0o700
            and path.resolve(strict=True) == path.absolute()
            and os.access(path, os.W_OK | os.X_OK)
        )
    except OSError:
        valid = False
    c.require(valid, "STAGE10_LOCAL_DIRECTORY_INVALID")


def local_root(*, reserve: int = LOCAL_RESERVE) -> Path:
    require_goethe_nhr_slurm("stage10-local-workspace")
    job = os.environ.get("SLURM_JOB_ID", "")
    c.require(bool(re.fullmatch(r"[0-9]+", job)), "STAGE10_LOCAL_JOB_ID_INVALID")
    c.require(
        pwd.getpwuid(os.geteuid()).pw_name == "donyadidegan",
        "STAGE10_LOCAL_OWNER_INVALID",
    )
    root = LOCAL_BASE / job
    private_directory(root)
    c.require(
        shutil.disk_usage(root).free >= reserve, "STAGE10_LOCAL_RESERVE_INSUFFICIENT"
    )
    return root


def create_transient(purpose: str, *, reserve: int = LOCAL_RESERVE) -> Path:
    c.require(
        purpose in ("generation", "validation", "remediation_audit"),
        "STAGE10_LOCAL_PURPOSE_INVALID",
    )
    parent = local_root(reserve=reserve)
    for name in ("safe_geocoding_pipeline", "stage10"):
        child = parent / name
        if not os.path.lexists(child):
            child.mkdir(mode=0o700)
            io.fsync_directory(parent)
        private_directory(child)
        parent = child
    root = Path(tempfile.mkdtemp(prefix=purpose + "_", dir=parent))
    private_directory(root)
    io.fsync_directory(parent)
    return root
