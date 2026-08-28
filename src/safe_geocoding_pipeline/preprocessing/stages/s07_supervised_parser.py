"""Crash-contained, exact-input supervision for the pinned Stage 7 parser."""

from __future__ import annotations

import hashlib
import multiprocessing
import os
import resource
import signal
import time
from collections.abc import Callable
from dataclasses import dataclass
from multiprocessing.connection import Connection, wait
from pathlib import Path
from typing import Any, NoReturn, Protocol, cast

from .s07_libpostal_adapter import (
    PARSED_EMPTY,
    PARSED_NONEMPTY,
    LibpostalComponent,
    ParsedAddress,
    PypostalParser,
    Stage07ParserError,
)


PARSER_PROCESS_CRASH = "PARSER_PROCESS_CRASH"
NATIVE_PROCESS_CRASH = "NATIVE_PROCESS_CRASH"
_RESULT = "RESULT"
_STARTED = "STARTED"
_TECHNICAL_FAILURE = "TECHNICAL_FAILURE"
_READY = "READY"
_STOP = "STOP"
_STOPPED = "STOPPED"
_REQUEST = "REQUEST"
_MONITOR_INTERVAL_SECONDS = 0.05


class Stage07SupervisorError(RuntimeError):
    """Privacy-safe supervisor failure with a stable public code."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> NoReturn:
    raise Stage07SupervisorError(code, detail)


@dataclass(frozen=True, slots=True)
class ProcessFailureSignature:
    """Public technical identity for one unexpected worker termination."""

    exit_category: str
    exit_code: int | None
    signal_number: int | None
    signal_name: str | None
    result_framing_completed: bool


@dataclass(frozen=True, slots=True)
class ParseAttempt:
    """One exact parser attempt without candidate content or identity."""

    outcome: str
    parsed: ParsedAddress | None
    technical_code: str | None
    failure_signature: ProcessFailureSignature | None
    wall_seconds: float
    child_max_rss_kib: int | None
    input_codepoints_verified: bool
    input_sha256_verified: bool
    result_framing_completed: bool


@dataclass(frozen=True, slots=True)
class SupervisedParseOutcome:
    """One total Stage 7 result produced by the approved retry contract."""

    status: str
    components: tuple[LibpostalComponent, ...] | None
    failure_code: str | None
    attempts: tuple[ParseAttempt, ...]

    def validate(self) -> None:
        if self.status == PARSED_NONEMPTY:
            if not self.components or self.failure_code is not None:
                _fail("SUPERVISED_RESULT_INVALID", "Nonempty result is inconsistent")
        elif self.status == PARSED_EMPTY:
            if self.components != () or self.failure_code is not None:
                _fail("SUPERVISED_RESULT_INVALID", "Empty result is inconsistent")
        elif self.status == PARSER_PROCESS_CRASH:
            if self.components is not None or self.failure_code != NATIVE_PROCESS_CRASH:
                _fail("SUPERVISED_RESULT_INVALID", "Crash result is inconsistent")
            if len(self.attempts) != 2 or any(
                attempt.outcome != "PROCESS_CRASH" for attempt in self.attempts
            ):
                _fail("SUPERVISED_RESULT_INVALID", "Crash confirmation is absent")
        else:
            _fail("SUPERVISED_RESULT_INVALID", "Status is not approved")

        if self.status in {PARSED_NONEMPTY, PARSED_EMPTY}:
            if len(self.attempts) != 1:
                _fail("SUPERVISED_RESULT_INVALID", "Successful attempt count differs")
            attempt = self.attempts[0]
            if (
                attempt.outcome != "SUCCESS"
                or attempt.parsed is None
                or attempt.parsed.status != self.status
                or attempt.parsed.components != self.components
                or attempt.technical_code is not None
                or attempt.failure_signature is not None
                or not attempt.input_codepoints_verified
                or not attempt.input_sha256_verified
                or not attempt.result_framing_completed
            ):
                _fail("SUPERVISED_RESULT_INVALID", "Successful attempt is inconsistent")
        else:
            first, second = self.attempts
            if (
                first.failure_signature is None
                or second.failure_signature is None
                or first.failure_signature != second.failure_signature
                or first.parsed is not None
                or second.parsed is not None
                or first.technical_code is not None
                or second.technical_code is not None
                or not first.input_codepoints_verified
                or not second.input_codepoints_verified
                or not first.input_sha256_verified
                or not second.input_sha256_verified
                or first.result_framing_completed
                or second.result_framing_completed
            ):
                _fail("SUPERVISED_RESULT_INVALID", "Crash attempts are inconsistent")


class ParserWorker(Protocol):
    initialization_seconds: float

    def attempt(self, candidate: str) -> ParseAttempt: ...

    def close(self) -> None: ...


WorkerFactory = Callable[[], ParserWorker]


def _strict_input_sha256(candidate: str) -> str:
    try:
        encoded = candidate.encode("utf-8", errors="strict")
    except UnicodeError as error:
        raise Stage07SupervisorError(
            "PARSER_INPUT_INVALID", "Parser input is not exact valid UTF-8"
        ) from error
    if encoded.decode("utf-8", errors="strict") != candidate:
        _fail("PARSER_INPUT_INVALID", "Parser input UTF-8 round-trip differs")
    return hashlib.sha256(encoded).hexdigest()


def _is_exact_utf8(value: str) -> bool:
    try:
        return (
            value.encode("utf-8", errors="strict").decode("utf-8", errors="strict")
            == value
        )
    except UnicodeError:
        return False


def _redirect_standard_streams() -> None:
    descriptor = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(descriptor, 1)
        os.dup2(descriptor, 2)
    finally:
        os.close(descriptor)


def _worker_main(connection: Connection) -> None:
    """Initialize libpostal once and process one framed request at a time."""
    _redirect_standard_streams()
    active_sequence = -1
    try:
        parser = PypostalParser()
        connection.send(
            {
                "kind": _READY,
                "initialization_seconds": parser.initialization_seconds,
                "child_max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            }
        )
        while True:
            request = connection.recv()
            if not isinstance(request, dict):
                raise ValueError("Malformed internal request")
            kind = request.get("kind")
            if kind == _STOP:
                connection.send({"kind": _STOPPED})
                return
            if kind != _REQUEST:
                raise ValueError("Unknown internal request")
            sequence = request.get("sequence")
            candidate = request.get("candidate")
            if not isinstance(sequence, int) or not isinstance(candidate, str):
                raise ValueError("Malformed internal request fields")
            active_sequence = sequence
            input_sha256 = _strict_input_sha256(candidate)
            connection.send(
                {
                    "kind": _STARTED,
                    "sequence": sequence,
                    "input_codepoints": len(candidate),
                    "input_sha256": input_sha256,
                    "child_max_rss_kib": resource.getrusage(
                        resource.RUSAGE_SELF
                    ).ru_maxrss,
                }
            )
            try:
                parsed = parser.parse(candidate)
            except Stage07ParserError as error:
                connection.send(
                    {
                        "kind": _TECHNICAL_FAILURE,
                        "sequence": sequence,
                        "technical_code": error.code,
                        "input_codepoints": len(candidate),
                        "input_sha256": input_sha256,
                        "child_max_rss_kib": resource.getrusage(
                            resource.RUSAGE_SELF
                        ).ru_maxrss,
                    }
                )
                continue
            connection.send(
                {
                    "kind": _RESULT,
                    "sequence": sequence,
                    "status": parsed.status,
                    "components": tuple(
                        (component.label, component.value)
                        for component in parsed.components
                    ),
                    "input_codepoints": len(candidate),
                    "input_sha256": input_sha256,
                    "child_max_rss_kib": resource.getrusage(
                        resource.RUSAGE_SELF
                    ).ru_maxrss,
                }
            )
    except (BrokenPipeError, EOFError, OSError):
        return
    except BaseException:
        # No arbitrary error text crosses the controlled worker boundary.
        try:
            connection.send(
                {
                    "kind": _TECHNICAL_FAILURE,
                    "sequence": active_sequence,
                    "technical_code": "PYTHON_WORKER_FAILURE",
                    "input_codepoints": 0,
                    "input_sha256": "",
                    "child_max_rss_kib": resource.getrusage(
                        resource.RUSAGE_SELF
                    ).ru_maxrss,
                }
            )
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        connection.close()


def _proc_peak_rss_kib(process_id: int) -> int | None:
    """Read Linux VmHWM while the worker exists; absence is explicitly allowed."""
    try:
        for line in (
            Path(f"/proc/{process_id}/status").read_text(encoding="ascii").splitlines()
        ):
            if line.startswith("VmHWM:"):
                parts = line.split()
                if len(parts) >= 2:
                    return int(parts[1])
    except (OSError, UnicodeError, ValueError):
        return None
    return None


def _failure_signature(exitcode: int | None) -> ProcessFailureSignature:
    if exitcode is None:
        return ProcessFailureSignature(
            exit_category="EXIT_STATUS_UNAVAILABLE",
            exit_code=None,
            signal_number=None,
            signal_name=None,
            result_framing_completed=False,
        )
    if exitcode < 0:
        signal_number = -exitcode
        try:
            signal_name = signal.Signals(signal_number).name
        except ValueError:
            signal_name = "UNKNOWN_SIGNAL"
        return ProcessFailureSignature(
            exit_category="SIGNAL",
            exit_code=None,
            signal_number=signal_number,
            signal_name=signal_name,
            result_framing_completed=False,
        )
    return ProcessFailureSignature(
        exit_category="EXIT_CODE",
        exit_code=exitcode,
        signal_number=None,
        signal_name=None,
        result_framing_completed=False,
    )


def _receive_dict(connection: Connection) -> dict[str, Any] | None:
    try:
        value = connection.recv()
    except (EOFError, OSError):
        return None
    return cast(dict[str, Any], value) if isinstance(value, dict) else None


class SpawnedParserWorker:
    """A long-lived libpostal child with exact synchronous request framing."""

    def __init__(self) -> None:
        self._sequence = 0
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe(duplex=True)
        self._connection = parent
        self._process = context.Process(target=_worker_main, args=(child,))
        self._process.start()
        if self._process.pid is None:
            _fail("PARSER_WORKER_INITIALIZATION_FAILURE", "Worker PID is absent")
        self._process_id = self._process.pid
        child.close()
        ready, observed_rss = self._wait_for_message()
        if ready is None or ready.get("kind") != _READY:
            self._join_after_exit()
            _fail(
                "PARSER_WORKER_INITIALIZATION_FAILURE",
                "Pinned parser child did not initialize cleanly",
            )
        initialization = ready.get("initialization_seconds")
        if not isinstance(initialization, (int, float)) or initialization < 0:
            self.close()
            _fail(
                "PARSER_WORKER_INITIALIZATION_FAILURE",
                "Pinned parser child readiness was malformed",
            )
        self.initialization_seconds = float(initialization)
        self.initialization_max_rss_kib = max(
            observed_rss or 0,
            int(ready.get("child_max_rss_kib", 0)),
        )

    def _wait_for_message(self) -> tuple[dict[str, Any] | None, int | None]:
        peak_rss: int | None = None
        while True:
            observed = _proc_peak_rss_kib(self._process_id)
            if observed is not None:
                peak_rss = max(peak_rss or 0, observed)
            ready = wait(
                (self._connection, self._process.sentinel),
                timeout=_MONITOR_INTERVAL_SECONDS,
            )
            if self._connection in ready:
                return _receive_dict(self._connection), peak_rss
            if self._process.sentinel in ready:
                return None, peak_rss

    def _join_after_exit(self) -> None:
        # A ready sentinel or closed pipe can precede multiprocessing's cached
        # is_alive state update by a short race. Join reaps that already-closing
        # process; it is not a candidate timeout.
        self._process.join()

    def attempt(self, candidate: str) -> ParseAttempt:
        expected_sha = _strict_input_sha256(candidate)
        if not self._process.is_alive():
            self._join_after_exit()
            _fail("PARSER_WORKER_STATE_INVALID", "Dead worker received a candidate")
        self._sequence += 1
        sequence = self._sequence
        started = time.perf_counter()
        try:
            self._connection.send(
                {"kind": _REQUEST, "sequence": sequence, "candidate": candidate}
            )
        except (BrokenPipeError, EOFError, OSError):
            self._process.join()
            wall = time.perf_counter() - started
            return ParseAttempt(
                outcome="PROCESS_CRASH",
                parsed=None,
                technical_code=None,
                failure_signature=_failure_signature(self._process.exitcode),
                wall_seconds=wall,
                child_max_rss_kib=None,
                input_codepoints_verified=False,
                input_sha256_verified=False,
                result_framing_completed=False,
            )
        acknowledged, acknowledged_rss = self._wait_for_message()
        if acknowledged is None:
            self._join_after_exit()
            wall = time.perf_counter() - started
            return ParseAttempt(
                outcome="PROCESS_CRASH",
                parsed=None,
                technical_code=None,
                failure_signature=_failure_signature(self._process.exitcode),
                wall_seconds=wall,
                child_max_rss_kib=acknowledged_rss,
                input_codepoints_verified=False,
                input_sha256_verified=False,
                result_framing_completed=False,
            )
        if (
            acknowledged.get("kind") != _STARTED
            or acknowledged.get("sequence") != sequence
            or acknowledged.get("input_codepoints") != len(candidate)
            or acknowledged.get("input_sha256") != expected_sha
        ):
            _fail(
                "PARSER_INPUT_ACKNOWLEDGEMENT_INVALID",
                "Worker did not acknowledge the exact active input",
            )
        acknowledged_child_rss = acknowledged.get("child_max_rss_kib")
        acknowledged_peak = max(
            acknowledged_rss or 0,
            (
                int(acknowledged_child_rss)
                if isinstance(acknowledged_child_rss, int)
                else 0
            ),
        )
        payload, observed_rss = self._wait_for_message()
        wall = time.perf_counter() - started
        if payload is None:
            self._join_after_exit()
            return ParseAttempt(
                outcome="PROCESS_CRASH",
                parsed=None,
                technical_code=None,
                failure_signature=_failure_signature(self._process.exitcode),
                wall_seconds=wall,
                child_max_rss_kib=max(acknowledged_peak, observed_rss or 0),
                input_codepoints_verified=True,
                input_sha256_verified=True,
                result_framing_completed=False,
            )
        if payload.get("sequence") != sequence:
            _fail("PARSER_RESULT_CROSS_WIRED", "Worker response sequence differs")
        if not self._process.is_alive():
            _fail(
                "PARSER_WORKER_POST_RESULT_EXIT",
                "Worker exited unexpectedly after sending a result frame",
            )
        child_rss = payload.get("child_max_rss_kib")
        max_rss = max(
            acknowledged_peak,
            observed_rss or 0,
            int(child_rss) if isinstance(child_rss, int) else 0,
        )
        codepoints_verified = payload.get("input_codepoints") == len(candidate)
        sha_verified = payload.get("input_sha256") == expected_sha
        if not codepoints_verified or not sha_verified:
            _fail("PARSER_INPUT_CROSS_WIRED", "Worker parsed a different input")
        kind = payload.get("kind")
        if kind == _TECHNICAL_FAILURE:
            technical = payload.get("technical_code")
            if not isinstance(technical, str) or not technical:
                technical = "MALFORMED_TECHNICAL_FAILURE"
            return ParseAttempt(
                outcome="TECHNICAL_FAILURE",
                parsed=None,
                technical_code=technical,
                failure_signature=None,
                wall_seconds=wall,
                child_max_rss_kib=max_rss,
                input_codepoints_verified=True,
                input_sha256_verified=True,
                result_framing_completed=True,
            )
        if kind != _RESULT:
            _fail("PARSER_RESULT_FRAMING_INVALID", "Worker response kind differs")
        raw_status = payload.get("status")
        raw_components = payload.get("components")
        if raw_status not in {PARSED_NONEMPTY, PARSED_EMPTY} or not isinstance(
            raw_components, tuple
        ):
            _fail("PARSER_RESULT_FRAMING_INVALID", "Worker parse payload is malformed")
        components: list[LibpostalComponent] = []
        for item in raw_components:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
                or not isinstance(item[0], str)
                or not isinstance(item[1], str)
                or not _is_exact_utf8(item[0])
                or not _is_exact_utf8(item[1])
            ):
                _fail(
                    "PARSER_RESULT_FRAMING_INVALID",
                    "Worker component framing is malformed",
                )
            components.append(LibpostalComponent(label=item[0], value=item[1]))
        parsed = ParsedAddress(status=raw_status, components=tuple(components))
        if (parsed.status == PARSED_NONEMPTY) != bool(parsed.components):
            _fail("PARSER_RESULT_FRAMING_INVALID", "Worker status/list differ")
        return ParseAttempt(
            outcome="SUCCESS",
            parsed=parsed,
            technical_code=None,
            failure_signature=None,
            wall_seconds=wall,
            child_max_rss_kib=max_rss,
            input_codepoints_verified=True,
            input_sha256_verified=True,
            result_framing_completed=True,
        )

    def close(self) -> None:
        if self._process.is_alive():
            try:
                self._connection.send({"kind": _STOP})
                payload, _ = self._wait_for_message()
                if payload is None or payload.get("kind") != _STOPPED:
                    _fail(
                        "PARSER_WORKER_SHUTDOWN_FAILURE", "Worker did not stop cleanly"
                    )
                self._process.join()
            finally:
                self._connection.close()
        else:
            self._process.join()
            self._connection.close()


class SupervisedParser:
    """Contain native crashes and fail closed after one exact fresh retry.

    ``diagnostic_crash_status`` exists only to reproduce the targeted diagnostic
    written before the Stage 7 v1 contract was frozen.  Authoritative parsing
    must use the default, which never returns a crash as a publishable row.
    """

    def __init__(
        self,
        worker_factory: WorkerFactory = SpawnedParserWorker,
        *,
        diagnostic_crash_status: bool = False,
    ) -> None:
        self._worker_factory = worker_factory
        self._diagnostic_crash_status = diagnostic_crash_status
        self._worker: ParserWorker | None = None
        self.workers_started = 0
        self.worker_restarts = 0
        self.worker_initialization_seconds: list[float] = []
        self.first_attempt_crashes = 0
        self.confirmed_repeated_crashes = 0
        self.crash_success_inconsistencies = 0
        self.changed_failure_inconsistencies = 0
        self.last_failed_attempts: tuple[ParseAttempt, ...] = ()

    def _start_worker(self) -> ParserWorker:
        worker = self._worker_factory()
        if self.workers_started:
            self.worker_restarts += 1
        self.workers_started += 1
        self.worker_initialization_seconds.append(worker.initialization_seconds)
        self._worker = worker
        return worker

    def _current_worker(self) -> ParserWorker:
        return self._worker if self._worker is not None else self._start_worker()

    def _discard_crashed_worker(self) -> None:
        if self._worker is not None:
            self._worker.close()
        self._worker = None

    def attempt_once(self, candidate: str) -> ParseAttempt:
        """Run one exact attempt; diagnostic callers must not publish it directly."""
        attempt = self._current_worker().attempt(candidate)
        if attempt.outcome == "PROCESS_CRASH":
            self._discard_crashed_worker()
        return attempt

    def parse(self, candidate: str) -> SupervisedParseOutcome:
        """Parse normally, or confirm one native crash with one exact fresh retry."""
        self.last_failed_attempts = ()
        first = self.attempt_once(candidate)
        if first.outcome == "SUCCESS":
            assert first.parsed is not None
            outcome = SupervisedParseOutcome(
                status=first.parsed.status,
                components=first.parsed.components,
                failure_code=None,
                attempts=(first,),
            )
            outcome.validate()
            return outcome
        if first.outcome != "PROCESS_CRASH" or first.failure_signature is None:
            self.last_failed_attempts = (first,)
            _fail(
                first.technical_code or "UNHANDLED_PARSER_FAILURE",
                "A non-native parser failure aborts Stage 7",
            )
        if not first.input_codepoints_verified or not first.input_sha256_verified:
            self.last_failed_attempts = (first,)
            _fail(
                "PARSER_CRASH_INPUT_UNVERIFIED",
                "Worker exited before exact parser input acknowledgement",
            )

        self.first_attempt_crashes += 1
        second = self.attempt_once(candidate)
        if second.outcome == "SUCCESS":
            self.last_failed_attempts = (first, second)
            self.crash_success_inconsistencies += 1
            _fail(
                "PARSER_CRASH_SUCCESS_NONDETERMINISM",
                "A fresh retry succeeded after a native crash",
            )
        if second.outcome != "PROCESS_CRASH" or second.failure_signature is None:
            self.last_failed_attempts = (first, second)
            self.changed_failure_inconsistencies += 1
            _fail(
                "PARSER_CRASH_FAILURE_NONDETERMINISM",
                "A fresh retry produced a different technical failure",
            )
        if not second.input_codepoints_verified or not second.input_sha256_verified:
            self.last_failed_attempts = (first, second)
            self.changed_failure_inconsistencies += 1
            _fail(
                "PARSER_CRASH_INPUT_UNVERIFIED",
                "Fresh worker exited before exact parser input acknowledgement",
            )
        if second.failure_signature != first.failure_signature:
            self.last_failed_attempts = (first, second)
            self.changed_failure_inconsistencies += 1
            _fail(
                "PARSER_CRASH_SIGNATURE_NONDETERMINISM",
                "Fresh retry process termination differs",
            )
        self.confirmed_repeated_crashes += 1
        self.last_failed_attempts = (first, second)
        if not self._diagnostic_crash_status:
            _fail(
                "PARSER_RESOURCE_SUFFICIENT_CRASH_UNSUPPORTED",
                "The exact fresh retry repeated a native parser crash",
            )
        outcome = SupervisedParseOutcome(
            status=PARSER_PROCESS_CRASH,
            components=None,
            failure_code=NATIVE_PROCESS_CRASH,
            attempts=(first, second),
        )
        outcome.validate()
        return outcome

    def close(self) -> None:
        if self._worker is not None:
            self._worker.close()
            self._worker = None

    def __enter__(self) -> SupervisedParser:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


__all__ = [
    "NATIVE_PROCESS_CRASH",
    "PARSER_PROCESS_CRASH",
    "ParseAttempt",
    "ParserWorker",
    "ProcessFailureSignature",
    "SpawnedParserWorker",
    "Stage07SupervisorError",
    "SupervisedParseOutcome",
    "SupervisedParser",
]
