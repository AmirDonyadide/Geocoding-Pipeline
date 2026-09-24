"""Sanitized attempt-local publication evidence, independent of scientific output."""

from __future__ import annotations

import errno
import os
import re
import stat
import time
from pathlib import Path
from typing import Any

from . import s10_query_contract as c
from . import s10_query_io as io
from . import s10_query_receipts as receipts

RESERVE_BYTES = 64 * 1024
PHASES = frozenset(
    "reservation build manifest manifest_fsync initial_validation registration_build "
    "registration_write registration_fsync prepared_validation seal_validation "
    "seal_create reopen final_check initialization input_validation generation".split()
)


def exception_identity(error: BaseException) -> dict[str, Any]:
    # No exception message, repr, SQL, path or traceback locals. Closed labels
    # also prevent a user-defined exception class name from carrying values.
    label = "OTHER_EXCEPTION"
    for kind in (
        c.Stage10Error,
        OSError,
        MemoryError,
        TypeError,
        ValueError,
        RuntimeError,
    ):
        if isinstance(error, kind):
            label = kind.__name__
            break
    number = error.errno if isinstance(error, OSError) else None
    code = "STAGE10_OPERATIONAL_FAILURE"
    if isinstance(error, c.Stage10Error) and re.fullmatch(
        r"(?:STAGE10_|FAIL_CLOSED_)[A-Z0-9_]{1,110}", str(error)
    ):
        code = str(error)
    if number in (errno.EDQUOT, errno.ENOSPC):
        code = (
            "STAGE10_STORAGE_QUOTA_EXHAUSTED"
            if number == errno.EDQUOT
            else "STAGE10_STORAGE_SPACE_EXHAUSTED"
        )
    return {"exception_class": label, "errno": number, "operational_code": code}


class PublicationTrace:
    """One owner, immutable phase records and a preallocated failure-write slot.

    The reserved partial file is allocated before input/generation. A terminal
    record is written into those blocks, fsynced and atomically renamed. This
    avoids needing new data blocks/inodes after EDQUOT/ENOSPC. Rename/fsync can
    still fail on an unavailable filesystem: callers must still return failure.
    The reserve itself is explicitly NOT terminal evidence or a commit seal.
    """

    def __init__(self, root: Path, artifact: Path, executable: str) -> None:
        c.require(
            bool(re.fullmatch(r"[a-f0-9]{40}", executable)),
            "STAGE10_TRACE_EXECUTABLE_INVALID",
        )
        c.require(
            bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", artifact.name)),
            "STAGE10_TRACE_KEY_INVALID",
        )
        self.root, self.artifact, self.executable = root, artifact, executable
        self.phase, self.sequence = "initialization", 0
        self.counts: dict[str, int] = {}
        self.reserve = root / "failure.json.partial"
        io.write_exclusive(self.reserve, b" " * RESERVE_BYTES)
        allocated = self.reserve.lstat()
        self.reserve_identity = (allocated.st_dev, allocated.st_ino)
        io.fsync_directory(root)

    def state(self) -> dict[str, Any]:
        return {
            "record_version": "stage10_publication_trace_v1",
            "phase": self.phase,
            "monotonic_ns": time.monotonic_ns(),
            "publication_key": self.artifact.name,
            "execution_git_sha": self.executable,
            "manifest_present": os.path.lexists(self.artifact / io.MANIFEST_NAME),
            "registration_present": os.path.lexists(self.artifact / io.SUCCESS_NAME),
            "seal_present": os.path.lexists(self.artifact / "_COMMITTED"),
            "counts": dict(self.counts),
        }

    def __call__(self, phase: str, error: BaseException | None = None) -> None:
        c.require(phase in PHASES, "STAGE10_PUBLICATION_PHASE_INVALID")
        self.phase = phase
        if error is not None:
            self.failure(error)
            return
        receipts.write(self.root / f"publication-{self.sequence:06}.json", self.state())
        self.sequence += 1

    def failure(self, error: BaseException) -> None:
        destination = self.root / "failure.json"
        if os.path.lexists(destination):
            return  # The earliest recorded failure remains immutable.
        record = {
            **self.state(),
            **exception_identity(error),
            "status": "EXCEPTION_RECORDED_NOT_COMMIT_AUTHORITY",
        }
        chain: list[dict[str, Any]] = []
        seen: set[int] = set()
        current: BaseException | None = error
        while current is not None and id(current) not in seen and len(chain) < 8:
            seen.add(id(current))
            chain.append(exception_identity(current))
            current = current.__cause__ or current.__context__
        record["exception_chain"] = chain
        raw = c.canonical(record)
        c.require(len(raw) <= RESERVE_BYTES, "STAGE10_FAILURE_RECEIPT_BOUND")
        fd = os.open(self.reserve, os.O_WRONLY | os.O_NOFOLLOW)
        try:
            allocated = os.fstat(fd)
            c.require(
                (allocated.st_dev, allocated.st_ino) == self.reserve_identity
                and stat.S_ISREG(allocated.st_mode)
                and stat.S_IMODE(allocated.st_mode) == 0o600
                and allocated.st_nlink == 1
                and allocated.st_uid == os.geteuid()
                and allocated.st_size == RESERVE_BYTES,
                "STAGE10_FAILURE_RESERVE_INVALID",
            )
            # No append or expansion: data blocks were exclusively allocated at
            # attempt initialization. Short writes are handled explicitly.
            offset = 0
            while offset < len(raw):
                count = os.pwrite(fd, raw[offset:], offset)
                c.require(count > 0, "STAGE10_FAILURE_RECEIPT_SHORT_WRITE")
                offset += count
            os.ftruncate(fd, len(raw))
            os.fsync(fd)
        finally:
            os.close(fd)
        os.rename(self.reserve, destination)
        io.fsync_directory(self.root)
