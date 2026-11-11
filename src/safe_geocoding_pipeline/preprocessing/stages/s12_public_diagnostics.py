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


CLOSURE_GUARDS = frozenset(("CAPTURE_CUMULATIVE", "DIAGNOSTIC_PHASE", "GLOBAL_TASK", "WHOLE_TASK_RESOURCE"))

CLOSURE_STAGES = frozenset((
    "STORAGE_RECONCILE", "SAMPLING_VERIFY", "SNAPSHOT_PRECHECK",
    "PREPARE_ORIGINAL_VERIFY", "PREPARE_EVIDENCE", "PREPARE_STORAGE",
    "FRESH_FINISH", "SNAPSHOT_PERSIST", "REVALIDATE_FRESH",
    "REVALIDATE_ORIGINAL_VERIFY", "REVALIDATE_EVIDENCE", "REVALIDATE_STORAGE",
    "SNAPSHOT_SEAL", "ORIGINAL_WORK_VERIFY", "ORIGINAL_RECEIPT_VERIFY",
    "ORIGINAL_REPLAY", "CAMPAIGN_REPORT", "CAMPAIGN_PERSIST", "WRITER_RELEASE",
    "SAMPLING_INSPECTION", "T3_PHASE_CLOSE", "T3_CLOSE", "NORMAL_OPEN",
    "NEGATIVE_OPEN", "RUNTIME_RECHECK", "T3_REREAD", "WHOLE_OPEN",
))


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

    def __init__(self, clock, *, closure=False):
        self.clock = clock
        self.lock = threading.Lock()
        self.first = None
        self.secondary = None
        self.secondary_count = 0
        self.response_rejection = None
        # Opt-in supplementary successor: no historical/default snapshot change.
        self.closure_enabled = closure is True
        self.closure_entered = None
        self.closure_completed = None
        self.closure_first = None
        self.closure_faults = 0
        self.closure_ordinal = 0
        self.closure_deadline_ordinal = 0
        self._closure_deadline = None
        self._closure_deadline_ns = None

    def closure_fault(self):
        # A supplementary failure can never replace an original exception.
        try:
            with self.lock:
                self.closure_faults = min(2**64 - 1, self.closure_faults + 1)
        except BaseException:
            pass

    def closure_boundary(self, stage, *, completed=False, writer=None, deadline=None, deadline_ns=None, guard=None):
        """Last actual boundary facts, never a claim about the failing callee.

        No I/O, worker, callback replacement or deadline enforcement occurs here.
        A completed inner boundary is not labelled as an active outer operation.
        """
        if not self.closure_enabled:
            return
        try:
            if type(stage) is not str or stage not in CLOSURE_STAGES:
                self.closure_fault()
                return
            now = self.clock.now_ns()
            end = getattr(deadline, "end_ns", None) if deadline is not None else deadline_ns
            if guard is not None and (type(guard) is not str or guard not in CLOSURE_GUARDS):
                self.closure_fault()
                guard = None
            if type(now) is not int or not 0 <= now < 2**64:
                self.closure_fault()
                return
            if type(end) is not int or not 0 < end < 2**64:
                end = None
            failed = writer.failed.is_set() if writer is not None else None
            with self.lock:
                if deadline is not None and deadline is not self._closure_deadline:
                    self.closure_deadline_ordinal += 1
                    self._closure_deadline, self._closure_deadline_ns = deadline, end
                unchanged = deadline is self._closure_deadline and end == self._closure_deadline_ns
                if deadline is not None and not unchanged:
                    self.closure_faults = min(2**64 - 1, self.closure_faults + 1)
                self.closure_ordinal += 1
                row = {"stage": stage, "ordinal": self.closure_ordinal, "mono_ns": now,
                       "deadline_ns": end, "deadline_identity": self.closure_deadline_ordinal if deadline is not None else None,
                       "deadline_identity_unchanged": unchanged if deadline is not None else None,
                       "writer_failed": failed, "guard_kind": guard,
                       "deadline_unit": "MONOTONIC_NS" if end is not None else None,
                       "deadline_identity_source": "ACTUAL_BOUND_OBJECT" if deadline is not None else "ACTUAL_ORIGINAL_SCALAR" if end is not None else "UNAVAILABLE"}
                if completed:
                    self.closure_completed = row
                else:
                    self.closure_entered = row
        except BaseException:
            self.closure_fault()

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
            if (self.closure_enabled and tag != "CLEANUP"
                    and self.closure_entered is not None and self.closure_first is None):
                self.closure_first = {
                    "failure": row.copy(),
                    "last_entered": self.closure_entered.copy(),
                    "last_completed": self.closure_completed.copy() if self.closure_completed else None,
                }

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
            result = {
                "version": "stage12_public_failure_diagnostics_v1",
                "scope": "SUPPLEMENTARY_NOT_CLOSURE_EVIDENCE",
                "first_initiating_failure": self.first.copy() if self.first else None,
                "first_secondary_failure": self.secondary.copy()
                if self.secondary
                else None,
                "secondary_observations": self.secondary_count,
                "earlier_response_rejection": self.response_rejection,
            }
            if self.closure_enabled:
                result["closure_boundary"] = {
                    "version": "stage12_public_closure_boundary_diagnostics_v1",
                    "scope": "LAST_BOUNDARIES_NOT_CAUSE_OR_CLOSURE_PROOF",
                    "last_entered": self.closure_entered.copy() if self.closure_entered else None,
                    "last_completed": self.closure_completed.copy() if self.closure_completed else None,
                    "first_failure": {key: (value.copy() if value else None)
                                      for key, value in self.closure_first.items()} if self.closure_first else None,
                    "observation_faults": self.closure_faults,
                    "retention_uncertain": self.closure_faults != 0,
                    "persistence": "NOT_ESTABLISHED_BY_IN_MEMORY_SNAPSHOT",
                }
            return result
