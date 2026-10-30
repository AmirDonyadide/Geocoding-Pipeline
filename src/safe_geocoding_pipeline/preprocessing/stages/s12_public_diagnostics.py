"""Bounded, secret-safe supplementary public failure diagnostics.

Not controller evidence or authority. A caller may persist this outside the
campaign after an uncertain writer; it cannot repair closure or exact counts.
"""

from __future__ import annotations

import threading
from . import s12_retrieval_contract as c
from . import s12_public_recovery as recovery

TAGS = frozenset(
    (
        "UNCLASSIFIED",
        "PREFLIGHT",
        "READINESS",
        "ADMISSION",
        "DISPATCH",
        "CAPTURE_FINALIZE",
        "WRITER_ACTION",
        "WRITER_WAIT",
        "SAMPLER",
        "COMPARISON",
        "REPORT",
        "RECONCILIATION",
        "CLOSURE",
        "CLEANUP",
        "RUNTIME_REOPEN",
        "RUNTIME",
    )
)
CODES = frozenset(
    (
        "S12_PUBLIC_WINDOW_CLOSED",
        "PUBLIC_PROBE_EVIDENCE_WRITE_FAILED",
        "S12_PUBLIC_OPERATIONS_INVALID",
        "S12_PRIVATE_FILE_INVALID",
        "S12_CAPTURE_INCOMPLETE",
        "RESPONSE_CONTRACT_INVALID",
        "S12_METADATA_INVALID",
        "RETRY_BUDGET_EXHAUSTED",
        "SECRET_ECHO_DETECTED",
        "S12_PUBLIC_AUTHORITY_CHANGED",
        "S12_PUBLIC_AUTHORITY_SCOPE",
        "PUBLIC_PROBE_EXECUTABLE_MISMATCH",
        "S12_PUBLIC_STORAGE_ACCOUNTING_MISMATCH",
    )
)


def classify(error):
    # Never stringify arbitrary objects, subclasses, messages or unsafe content.
    family, code, number = "UNCLASSIFIED", None, None
    if isinstance(error, recovery.FinalizationExpired):
        family = "CUMULATIVE_DEADLINE"
    elif type(error) is c.Stage12Error:
        family = "STAGE12"
        if (
            len(error.args) == 1
            and type(error.args[0]) is str
            and error.args[0] in CODES
        ):
            code = error.args[0]
    elif isinstance(error, TimeoutError):
        family = "TIMEOUT"
    elif isinstance(error, OSError):
        family = "OS_ERROR"
        if type(error.errno) is int and 0 <= error.errno <= 4095:
            number = error.errno
    elif type(error) is KeyboardInterrupt:
        family = "INTERRUPTED"
    return family, code, number


class Failures:
    """Two fixed records plus counters; first initiating failure never replaced."""

    def __init__(self, clock):
        self.clock = clock
        self.lock = threading.Lock()
        self.first = None
        self.secondary = None
        self.secondary_count = 0
        self.response_rejection = None

    def record(
        self, tag, error, *, work_id=None, attempt=None, writer=None, deadline=None
    ):
        family, code, number = classify(error)
        row = {
            "operation": tag if tag in TAGS else "UNCLASSIFIED",
            "family": family,
            "code": code,
            "errno": number,
            "mono_ns": self.clock.now_ns(),
            "work_id": work_id
            if type(work_id) is int and 0 < work_id < 2**64
            else None,
            "attempt": attempt if type(attempt) is int and 1 <= attempt <= 5 else None,
            "writer_failed": writer.failed.is_set() if writer is not None else None,
            "deadline_expired": deadline.remaining_seconds() <= 0 if deadline else None,
        }
        with self.lock:
            if self.first is None:
                self.first = row
            else:
                self.secondary_count += 1
                if self.secondary is None:
                    self.secondary = row

    def rejected(self, reason):
        with self.lock:
            if self.response_rejection is None:
                self.response_rejection = (
                    reason
                    if type(reason) is str and reason in CODES
                    else "UNCLASSIFIED"
                )

    def snapshot(self):
        with self.lock:
            return {
                "version": "stage12_public_failure_diagnostics_v1",
                "scope": "SUPPLEMENTARY_NOT_CLOSURE_EVIDENCE",
                "first_initiating_failure": self.first.copy() if self.first else None,
                "first_secondary_failure": self.secondary.copy()
                if self.secondary
                else None,
                "secondary_observations": self.secondary_count,
                "earlier_response_rejection": self.response_rejection,
            }
