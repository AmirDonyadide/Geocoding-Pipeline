"""One process's bounded, shared source read/check watermarks.

This module uses only the standard library so setup can install its monitor
before importing scientific/native backends. It grants no authority. Callers
validate the original selection/binding and freshly prove carried prefixes.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from threading import RLock
from typing import Any

SOURCE_KEYS = ("source_read_calls", "source_read_bytes", "identity_checks")
MAX_U = 2**64 - 1
SELECTION = "stage12_resource_selection_ra_g1_v1"
BOUND = "stage12_resource_assurance_binding_ra_g1_v1"


class SourceCounterError(RuntimeError):
    """A static, non-sensitive accounting failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _need(ok: bool, code: str) -> None:
    if not ok:
        raise SourceCounterError(code)


def _uint(value: Any, *, positive: bool = False) -> int:
    _need(type(value) is int and int(positive) <= value <= MAX_U, "RA_G1_READ_LIMIT")
    return int(value)


def _digest(value: Any) -> str:
    raw = (
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")
    _need(len(raw) <= 65536, "RA_G1_READ_LIMIT")
    return hashlib.sha256(raw).hexdigest()


class SourceCounterLedger:
    """Shared live counters; prefixes add to this process's existing deltas.

    Global limits sum the frozen selected stage caps and narrow to a supplied
    original binding. Stage caps apply only to this stage's actual deltas.
    Limits are frozen copies of compiled stage bounds, narrowed by any supplied
    original read binding and explicit global bounds. Neither this class nor
    ``add_verified_prefix`` verifies release, grants, native coverage or source
    provenance. The caller must perform those original checks separately.
    """

    def __init__(
        self,
        selection: dict[str, Any],
        *,
        phase_id: int = 13,
        binding: dict[str, Any] | None = None,
        maximum_identity_checks: int | None = None,
        maximum_original_read_calls: int | None = None,
        maximum_original_read_bytes: int | None = None,
        clock_ns: Any = time.monotonic_ns,
    ) -> None:
        _need(
            type(selection) is dict
            and selection.get("schema_version") == SELECTION
            and selection.get("scope") == "PUBLIC_SYNTHETIC_ONLY"
            and type(phase_id) is int
            and phase_id in (13, 14)
            and callable(clock_ns),
            "RA_G1_SELECTION_BINDING",
        )
        self._lock = RLock()
        self._pid = os.getpid()
        self._selection_sha256 = _digest(selection)
        self._source_git_sha = str(selection["source_git_sha"])
        self._phase_id = phase_id
        self._clock = clock_ns
        self._prefix_added = False
        rows = selection["limits"]["stages"]
        _need(
            type(rows) is list
            and len(rows) == 14
            and {row["id"] for row in rows} == set(range(1, 15)),
            "RA_G1_SELECTION_BINDING",
        )
        self._stages: dict[int, dict[str, int]] = {}
        self._durations: dict[int, int] = {}
        for stage in rows:
            stage_id = _uint(stage["id"], positive=True)
            _need(stage["phase"] == stage_id, "RA_G1_SELECTION_BINDING")
            self._stages[stage_id] = {
                "source_read_calls": _uint(stage["source_read_calls"], positive=True),
                "source_read_bytes": _uint(stage["source_read_bytes"], positive=True),
                "identity_checks": _uint(stage["check_calls"], positive=True),
            }
            self._durations[stage_id] = _uint(stage["deadline_ms"], positive=True)
        self._limits = {
            key: _uint(
                sum(stage[key] for stage in self._stages.values()), positive=True
            )
            for key in SOURCE_KEYS
        }
        self._values = dict.fromkeys(SOURCE_KEYS, 0)
        self._baseline = dict(self._values)
        self._entered_ns = _uint(self._clock())
        self._deadline_ns = _uint(self._entered_ns + self._durations[phase_id] * 10**6)
        global_caps = (
            maximum_original_read_calls,
            maximum_original_read_bytes,
            maximum_identity_checks,
        )
        for key, value in zip(SOURCE_KEYS, global_caps, strict=True):
            if value is not None:
                self._limits[key] = min(self._limits[key], _uint(value, positive=True))
        if binding is not None:
            self.constrain(binding)

    def _current(self) -> None:
        _need(os.getpid() == self._pid, "RA_G1_PROCESS_SCOPE")

    def _enforce(self) -> None:
        _need(self._clock() < self._deadline_ns, "RA_G1_DEADLINE")
        delta = {key: self._values[key] - self._baseline[key] for key in SOURCE_KEYS}
        stage = self._stages[self._phase_id]
        _need(
            self._values["identity_checks"] <= self._limits["identity_checks"]
            and delta["identity_checks"]
            <= min(stage["identity_checks"], self._limits["identity_checks"]),
            "RA_G1_CHECK_BUDGET",
        )
        _need(
            all(
                self._values[key] <= self._limits[key]
                and delta[key] <= min(stage[key], self._limits[key])
                for key in ("source_read_calls", "source_read_bytes")
            ),
            "RA_G1_READ_LIMIT",
        )

    def enter_stage(self, stage_id: int) -> None:
        """Source-owned setup13 -> phases1..11 -> whole12; no replay/reset."""
        _uint(stage_id, positive=True)
        with self._lock:
            self._current()
            self._enforce()
            expected = 1 if self._phase_id == 13 else self._phase_id + 1
            _need(
                self._phase_id != 14 and self._phase_id != 12 and stage_id == expected,
                "RA_G1_SOURCE_STAGE_ORDER",
            )
            self._phase_id = stage_id
            self._baseline = dict(self._values)
            self._entered_ns = _uint(self._clock())
            self._deadline_ns = _uint(
                self._entered_ns + self._durations[stage_id] * 10**6
            )

    def _add(self, delta: dict[str, int]) -> None:
        self._current()
        _need(
            all(self._values[key] + value <= MAX_U for key, value in delta.items()),
            "RA_G1_READ_LIMIT",
        )
        for key, value in delta.items():
            self._values[key] += value
        # Denied attempts remain charged; snapshots never issue success/authority.
        self._enforce()

    def read_charge(self, calls: int, size: int) -> None:
        """Charge each read attempt before I/O and actual bytes after I/O, incl EOF."""
        calls, size = _uint(calls), _uint(size)
        with self._lock:
            self._add(dict(source_read_calls=calls, source_read_bytes=size))

    def checkpoint(self) -> None:
        """Charge one actual source identity/enforcement check invocation."""
        with self._lock:
            self._add(dict(identity_checks=1))

    def add_verified_prefix(self, prefix: dict[str, int]) -> None:
        """Add a caller freshly verified original prefix; never replace deltas."""
        _need(type(prefix) is dict and set(prefix) == set(SOURCE_KEYS), "RA_G1_HANDOFF")
        copied = {key: _uint(prefix[key]) for key in SOURCE_KEYS}
        with self._lock:
            self._current()
            _need(self._phase_id == 14 and not self._prefix_added, "RA_G1_HANDOFF")
            _need(
                all(
                    self._values[key] + copied[key] <= MAX_U
                    and self._baseline[key] + copied[key] <= MAX_U
                    for key in SOURCE_KEYS
                ),
                "RA_G1_READ_LIMIT",
            )
            self._prefix_added = True
            for key in SOURCE_KEYS:
                self._values[key] += copied[key]
                self._baseline[key] += copied[key]
            self._enforce()

    def constrain(self, binding: dict[str, Any]) -> None:
        """Narrow to the genuine binding's bounds; no method can enlarge limits."""
        _need(
            type(binding) is dict
            and binding.get("schema_version") == BOUND
            and binding.get("selection_sha256") == self._selection_sha256
            and binding.get("source_git_sha") == self._source_git_sha
            and binding.get("scope") == "PUBLIC_SYNTHETIC_ONLY",
            "RA_G1_SELECTION_BINDING",
        )
        caps = {
            "source_read_calls": _uint(
                binding["maximum_original_read_calls"], positive=True
            ),
            "source_read_bytes": _uint(
                binding["maximum_original_read_bytes"], positive=True
            ),
            "identity_checks": _uint(binding["maximum_identity_checks"], positive=True),
        }
        with self._lock:
            self._current()
            for key in SOURCE_KEYS:
                self._limits[key] = min(self._limits[key], caps[key])
            self._enforce()

    def snapshot_source(self) -> dict[str, int]:
        """Immutable copy of actual charged watermarks, including failed attempts."""
        with self._lock:
            self._current()
            return dict(self._values)

    @property
    def source_read_calls(self) -> int:
        return self.snapshot_source()["source_read_calls"]

    @property
    def source_read_bytes(self) -> int:
        return self.snapshot_source()["source_read_bytes"]

    @property
    def identity_checks(self) -> int:
        return self.snapshot_source()["identity_checks"]

    @property
    def source_selection_sha256(self) -> str:
        return self._selection_sha256

    @property
    def process_pid(self) -> int:
        return self._pid

    def limit_basis(self) -> dict[str, Any]:
        """Fixed numeric basis only; this contains no proof or authority flags."""
        with self._lock:
            self._current()
            return dict(
                process_pid=self._pid,
                source_selection_sha256=self._selection_sha256,
                source_git_sha=self._source_git_sha,
                phase_id=self._phase_id,
                limits=dict(self._limits),
                stage_limits=dict(self._stages[self._phase_id]),
                stage_entry_source_prefix=dict(self._baseline),
                stage_entered_mono_ns=self._entered_ns,
                stage_deadline_mono_ns=self._deadline_ns,
            )
