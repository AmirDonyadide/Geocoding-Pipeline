"""Independent RA-G1 monitoring and acyclic opener/terminal evidence.

A monitor thread and its separate sole writer never acquire the AP safety lock
or campaign writer. Coverage timestamps are actual acquisition, never ACK time.
The final guarded administrative suffix is explicitly outside periodic coverage.
"""

from __future__ import annotations

from typing import Any

import hashlib
import os
from pathlib import Path
import stat
import struct
import threading
import time
from collections import deque

from . import s12_ra_g1_assurance as a
from . import s12_public_operations as old
from . import s12_public_bounded as bounded
from . import s12_public_diagnostics as diagnostics
from . import s12_public_recovery as recovery
from . import s12_retrieval_contract as c
from . import s12_wf_ap2_scratch as scratch

OBSERVATION = "stage12_resource_observation_ra_g1_v1"
CLOSURE = "stage12_resource_closure_ra_g1_v1"
OPENER = "stage12_resource_opener_return_ra_g1_v1"
MONITOR_TERMINAL = "stage12_resource_monitor_terminal_ra_g1_v1"
PHASE_TERMINAL = "stage12_resource_phase_terminal_ra_g1_v1"
PERIOD_NS, MAX_GAP_NS, GUARD_NS = 500_000_000, 1_000_000_000, 5_000_000_000
CODEC_BYTES, MAX_RECORD_BYTES, MAX_NAMES = 1024, 8192, 64
ORIGINAL_OBSERVATION = "stage12_resource_observation_original_ra_g1_v1"
MAX_ORIGINAL_BYTES = 15360
ROLES: tuple[str, ...] = tuple(a.LIMITS["application_counters"])
COUNTERS = ROLES + tuple(
    "application_write_reserved_bytes application_creations_charged monitor_observations_charged monitor_write_bytes_charged source_read_calls source_read_bytes identity_checks segment_attempts root_attempts".split()
)
READINGS = tuple(
    "self_rss_peak_bytes registered_visible_rss_bytes visible_native_threads visible_processes shared_bavail_bytes shared_favail visible_native_file_bytes".split()
)
NATIVE_SCHEMA = {
    **old.fields(
        "registered_paths_checked:U visible_linked_files:U discovered_names:U"
    ),
    "maximum_discovered_names": "=64",
    "discovery_status": old.enum("COMPLETE_KNOWN_NAMESPACE", "OVERFLOW", "FAILED"),
    "visible_allocated_bytes": a.READING,
    "unknown_native_file_count": "=NOT_PROVEN",
    "deleted_open_bytes": "=NOT_MEASURED",
}
FAILURE_CODES = sorted(
    diagnostics.CODES
    | {
        "RA_G1_MONITOR_GAP",
        "RA_G1_MONITOR_THRESHOLD",
        "RA_G1_REQUIRED_READING",
        "RA_G1_DEADLINE",
        "RA_G1_WRITE_UNCERTAIN",
        "RA_G1_ORIGINAL_CHANGED",
        "RA_G1_NATIVE_DISCOVERY",
        "RA_G1_PROTOCOL",
        "RA_G1_PROCESS_SCOPE",
        "RA_G1_READ_LIMIT",
        "RA_G1_COUNTER_LIMIT",
        "RA_G1_MONITOR_INCOMPLETE",
    }
)
DIAGNOSTIC_STAGES = (
    "IDLE", "CHECK", "OBSERVER", "COVERAGE", "PACK", "APPEND", "WAIT_ACK",
    "POST_ACK_CHECK", "PUBLISH", "ORIGINAL_WRITE", "ORIGINAL_FSYNC",
    "ORIGINAL_READBACK", "CODEC_WRITE", "CODEC_FSYNC", "CODEC_READBACK",
    "ACK", "CLOSED", "BARRIER",
)
DIAGNOSTIC_CODES = tuple(sorted(set(FAILURE_CODES) | {
    "UNKNOWN", "WF_AP2_SCRATCH_LIMIT", "WF_AP2_SCRATCH_REENTRANT",
}))
DIAGNOSTIC_FAMILIES = ("STAGE12_ERROR", "OS_ERROR", "UNKNOWN")
DIAGNOSTIC_SOURCES = ("WRITER", "MONITOR")
DIAGNOSTIC_KINDS = ("START", "PERIODIC", "FINAL")


def _diagnostic_fault(error: Any, *, source: str, stage: str, clock: Any) -> dict[str, Any]:
    """Retain only bounded static classifications; never retain the exception."""
    code, family, number = "UNKNOWN", "UNKNOWN", None
    if type(error) is c.Stage12Error:
        family = "STAGE12_ERROR"
        if error.args and type(error.args[0]) is str and error.args[0] in DIAGNOSTIC_CODES:
            code = error.args[0]
    elif isinstance(error, OSError):
        family = "OS_ERROR"
        if type(error.errno) is int and 0 <= error.errno <= 4095:
            number = error.errno
    try:
        observed = clock()
        if type(observed) is not int or not 0 <= observed <= 2**64 - 1:
            observed = None
    except BaseException:
        observed = None
    return dict(family=family, code=code, errno=number, mono_ns=observed,
                source=source, stage=stage)


FAILURE = {
    "stage": old.enum(
        "PREFLIGHT",
        "PHASE",
        "MONITOR",
        "NATIVE",
        "ADMISSION",
        "CLOSURE",
        "OPENER",
        "TAIL",
        "TERMINAL",
        "CLEANUP",
    ),
    "operation": old.enum(
        *sorted(
            diagnostics.TAGS
            | {"READ", "ACQUIRE", "ACK", "WRITE", "OPEN", "WAIT", "VERIFY", "RELEASE"}
        )
    ),
    "family": old.enum(
        "UNCLASSIFIED",
        "STAGE12",
        "TIMEOUT",
        "OS_ERROR",
        "INTERRUPTED",
        "CUMULATIVE_DEADLINE",
    ),
    "code": old.enum(*FAILURE_CODES),
    **old.fields("errno:U? at_mono_ns:U work_id:ID? attempt:U?"),
    "writer": old.enum("HEALTHY", "POISONED", "UNKNOWN"),
    "deadline_remaining_ns": "U",
}
SCHEMAS: dict[str, Any] = {
    OBSERVATION: {
        "schema_version": "=" + OBSERVATION,
        **old.fields(
            "binding_sha256:D selection_sha256:D phase_id:ID seq:ID previous_sha256:D"
        ),
        "kind": old.enum("START", "PERIODIC", "FINAL"),
        **old.fields("enter_mono_ns:U exit_mono_ns:U"),
        "readings": {key: a.READING for key in READINGS},
        "counters": {key: "U" for key in COUNTERS},
        "native_visibility": NATIVE_SCHEMA,
        "visible_identity_inventory_sha256": "D",
    },
    CLOSURE: {
        "schema_version": "=" + CLOSURE,
        **old.fields(
            "binding_sha256:D selection_sha256:D phase_id:ID original_observation_prefix_sha256:D last_seq:U"
        ),
        "monitor_coverage": old.enum("COMPLETE_SELECTED_SCOPE", "INCOMPLETE"),
        "max_observed_gap_ns": "U?",
        **old.fields("counter_totals_sha256:D original_inventory_sha256:D"),
        "first_failure": None,
        "cleanup_failure": None,
        "outcome": old.enum(
            "PENDING_OPEN",
            "COMPLIANT_SELECTED_SCOPE",
            "STOPPED",
            "INCOMPLETE",
            "QUARANTINED",
            "UNCERTAIN",
        ),
        "native_maximum": "=NOT_PROVEN",
        "physical_maximum": "=NOT_PROVEN",
        "accepted_risk_inventory_sha256": "D",
        "actual_opener_record_sha256": "D?",
    },
    OPENER: {
        "schema_version": "=" + OPENER,
        **old.fields(
            "binding_sha256:D selection_sha256:D phase_id:ID preopening_closure_sha256:D frozen_data_inventory_sha256:D validated_monitor_prefix_sha256:D actual_opener_start_ns:U actual_opener_return_ns:U"
        ),
        "opener_disposition": old.enum(
            "DATA_OPENED", "EXPECTED_NEGATIVE_REJECTED", "FAILED"
        ),
        "expected_negative_spec_sha256": "D?",
        "failure": None,
    },
    MONITOR_TERMINAL: {
        "schema_version": "=" + MONITOR_TERMINAL,
        **old.fields(
            "binding_sha256:D phase_id:ID opener_return_sha256:D prefix_H0_sha256:D full_monitor_inventory_sha256:D final_observation_sha256:D final_observation_ns:U last_ack_ns:U last_seq:U coverage_start_ns:U coverage_end_ns:U max_gap_ns:U?"
        ),
        "disposition": old.enum("CLOSED_SELECTED_SCOPE", "INCOMPLETE", "UNCERTAIN"),
        "writer_state": old.enum("HEALTHY_RELEASED", "POISONED", "UNKNOWN"),
    },
    PHASE_TERMINAL: {
        "schema_version": "=" + PHASE_TERMINAL,
        **old.fields(
            "binding_sha256:D selection_sha256:D phase_id:ID opener_return_sha256:D monitor_terminal_sha256:D child_result_original_sha256:D child_exit_code:U? child_signal:U? tail_check_start_ns:U tail_check_end_ns:U terminal_prewrite_ns:U root_counter_watermarks_sha256:D"
        ),
        "disposition": old.enum(
            "COMPLETE_SELECTED_SCOPE",
            "EXPECTED_NEGATIVE_VERIFIED",
            "STOPPED",
            "INCOMPLETE",
            "UNCERTAIN",
        ),
        "first_failure": None,
        "cleanup_failure": None,
    },
}
for _schema in SCHEMAS.values():
    for _key in ("first_failure", "cleanup_failure", "failure"):
        if _key in _schema:
            _schema[_key] = {"nullable": FAILURE}


def _shape(value: Any, spec: Any) -> Any:
    if type(spec) is dict and "nullable" in spec:
        if value is not None:
            a.shape(value, spec["nullable"])
    elif type(spec) is dict and not ("tag" in spec or "enum" in spec):
        c.require(type(value) is dict and set(value) == set(spec), "RA_G1_FIELDS")
        for key, child in spec.items():
            _shape(value[key], child)
    else:
        a.shape(value, spec)


def validate(record: Any, version: Any = None) -> Any:
    version = (
        record.get("schema_version")
        if version is None and type(record) is dict
        else version
    )
    c.require(version in SCHEMAS, "RA_G1_FIELDS")
    _shape(record, SCHEMAS[version])
    # Count first: a malicious large input never creates an oversized encoding.
    counter = bounded.Canonical(MAX_RECORD_BYTES, count_only=True)
    counter.value(record)
    counter.put(b"\n")
    if version == OBSERVATION:
        enter, exit_ns = record["enter_mono_ns"], record["exit_mono_ns"]
        c.require(enter <= exit_ns, "RA_G1_MONITOR_GAP")
        meanings = {
            "self_rss_peak_bytes": ("PROCESS", "SELF"),
            "registered_visible_rss_bytes": ("PROCESS", "REGISTERED_VISIBLE"),
            "visible_native_threads": ("PROCESS", "REGISTERED_VISIBLE"),
            "visible_processes": ("PROCESS", "REGISTERED_VISIBLE"),
            "shared_bavail_bytes": ("FILESYSTEM", "FILESYSTEM_SHARED"),
            "shared_favail": ("FILESYSTEM", "FILESYSTEM_SHARED"),
            "visible_native_file_bytes": ("FILESYSTEM", "REGISTERED_VISIBLE"),
        }
        for key, reading in record["readings"].items():
            c.require(
                (reading.get("origin"), reading.get("scope")) == meanings[key],
                "RA_G1_REQUIRED_READING",
            )
            c.require(
                reading["status"] == "KNOWN"
                and enter <= reading["acquired_mono_ns"] <= exit_ns,
                "RA_G1_REQUIRED_READING",
            )
        native = record["native_visibility"]
        c.require(
            native["registered_paths_checked"] <= 64
            and native["discovered_names"] <= 64
            and native["visible_linked_files"] <= 64
            and native["discovery_status"] == "COMPLETE_KNOWN_NAMESPACE",
            "RA_G1_NATIVE_DISCOVERY",
        )
        c.require(
            native["visible_allocated_bytes"]
            == record["readings"]["visible_native_file_bytes"],
            "RA_G1_REQUIRED_READING",
        )
        c.require(
            record["readings"]["visible_processes"]["value"] <= 4, "RA_G1_PROCESS_SCOPE"
        )
    elif version == CLOSURE:
        if record["outcome"] == "PENDING_OPEN":
            c.require(record["actual_opener_record_sha256"] is None, "RA_G1_PROTOCOL")
        if record["monitor_coverage"] == "COMPLETE_SELECTED_SCOPE":
            c.require(
                record["max_observed_gap_ns"] is not None
                and record["last_seq"] >= 1
                and record["max_observed_gap_ns"] <= MAX_GAP_NS
                and record["first_failure"] is None
                and record["cleanup_failure"] is None,
                "RA_G1_MONITOR_INCOMPLETE",
            )
    elif version == OPENER:
        c.require(
            record["actual_opener_start_ns"] <= record["actual_opener_return_ns"],
            "RA_G1_PROTOCOL",
        )
        c.require(
            (record["expected_negative_spec_sha256"] is not None)
            == (record["opener_disposition"] == "EXPECTED_NEGATIVE_REJECTED"),
            "RA_G1_PROTOCOL",
        )
    elif version == MONITOR_TERMINAL:
        c.require(
            record["coverage_start_ns"]
            <= record["coverage_end_ns"]
            == record["final_observation_ns"]
            <= record["last_ack_ns"],
            "RA_G1_PROTOCOL",
        )
        if record["disposition"] == "CLOSED_SELECTED_SCOPE":
            c.require(
                record["max_gap_ns"] is not None
                and record["max_gap_ns"] <= MAX_GAP_NS
                and record["writer_state"] == "HEALTHY_RELEASED",
                "RA_G1_MONITOR_INCOMPLETE",
            )
    elif version == PHASE_TERMINAL:
        c.require(
            record["child_exit_code"] is None or record["child_signal"] is None,
            "RA_G1_PROTOCOL",
        )
        c.require(
            record["tail_check_start_ns"]
            <= record["tail_check_end_ns"]
            <= record["terminal_prewrite_ns"],
            "RA_G1_PROTOCOL",
        )
        if record["disposition"] in (
            "COMPLETE_SELECTED_SCOPE",
            "EXPECTED_NEGATIVE_VERIFIED",
        ):
            c.require(
                record["child_exit_code"] == 0
                and record["child_signal"] is None
                and record["first_failure"] is None
                and record["cleanup_failure"] is None,
                "RA_G1_PROTOCOL",
            )
    return record


_ORIGINS = ("KERNEL", "PROCESS", "FILESYSTEM")
_SCOPES = ("SELF", "REGISTERED_VISIBLE", "VISIBLE_CGROUP", "FILESYSTEM_SHARED")
_KINDS = ("START", "PERIODIC", "FINAL")


def pack_observation(record: Any) -> Any:
    validate(record, OBSERVATION)
    with scratch.ra_g1_lease("MONITOR_CODEC"):
        block = bytearray(CODEC_BYTES)
        block[:8] = b"S12RAG1\n"
        offset = 8

        def number(value: Any) -> Any:
            nonlocal offset
            struct.pack_into("<Q", block, offset, value)
            offset += 8

        for key in ("phase_id", "seq", "enter_mono_ns", "exit_mono_ns"):
            number(record[key])
        number(_KINDS.index(record["kind"]))
        for key in (
            "binding_sha256",
            "selection_sha256",
            "previous_sha256",
            "visible_identity_inventory_sha256",
        ):
            block[offset : offset + 32] = bytes.fromhex(record[key])
            offset += 32
        for key in COUNTERS:
            number(record["counters"][key])

        def reading(value: Any) -> Any:
            number(value["value"])
            number(value["acquired_mono_ns"])
            number(
                _ORIGINS.index(value["origin"]) | (_SCOPES.index(value["scope"]) << 8)
            )

        for key in READINGS:
            reading(record["readings"][key])
        native = record["native_visibility"]
        for key in (
            "registered_paths_checked",
            "visible_linked_files",
            "discovered_names",
        ):
            number(native[key])
        reading(native["visible_allocated_bytes"])
        c.require(offset <= CODEC_BYTES, "RA_G1_RECORD_LIMIT")
        return bytes(block)


def unpack_observation(raw: Any) -> Any:
    c.require(
        type(raw) is bytes and len(raw) == CODEC_BYTES and raw[:8] == b"S12RAG1\n",
        "RA_G1_CODEC",
    )
    offset = 8

    def number() -> Any:
        nonlocal offset
        value = struct.unpack_from("<Q", raw, offset)[0]
        offset += 8
        return value

    record: dict[str, Any] = {"schema_version": OBSERVATION}
    for key in ("phase_id", "seq", "enter_mono_ns", "exit_mono_ns"):
        record[key] = number()
    kind = number()
    c.require(kind < len(_KINDS), "RA_G1_CODEC")
    record["kind"] = _KINDS[kind]
    for key in (
        "binding_sha256",
        "selection_sha256",
        "previous_sha256",
        "visible_identity_inventory_sha256",
    ):
        record[key] = raw[offset : offset + 32].hex()
        offset += 32
    record["counters"] = {key: number() for key in COUNTERS}

    def reading() -> Any:
        value, at, tag = number(), number(), number()
        c.require(tag & 255 < len(_ORIGINS) and tag >> 8 < len(_SCOPES), "RA_G1_CODEC")
        return a.known(value, _ORIGINS[tag & 255], _SCOPES[tag >> 8], at)

    record["readings"] = {key: reading() for key in READINGS}
    record["native_visibility"] = {
        key: number()
        for key in (
            "registered_paths_checked",
            "visible_linked_files",
            "discovered_names",
        )
    }
    record["native_visibility"].update(
        maximum_discovered_names=64,
        discovery_status="COMPLETE_KNOWN_NAMESPACE",
        visible_allocated_bytes=reading(),
        unknown_native_file_count="NOT_PROVEN",
        deleted_open_bytes="NOT_MEASURED",
    )
    c.require(not any(raw[offset:]), "RA_G1_CODEC")
    validate(record)
    return record


def export_observation(record: Any) -> Any:
    """Opt-in export: caller must separately charge its <=8192-byte output."""
    validate(record, OBSERVATION)
    return bytes(bounded.canonical(record, MAX_RECORD_BYTES))


def thresholds(
    record: Any, selected: Any, *, next_write_bytes: Any = 0, next_creations: Any = 0
) -> Any:
    validate(record, OBSERVATION)
    r = record["readings"]
    m = selected["monitor"]
    for key, limit in (
        ("self_rss_peak_bytes", m["self_rss_stop_bytes"]),
        ("registered_visible_rss_bytes", m["aggregate_rss_stop_bytes"]),
        ("visible_native_threads", 256),
        ("visible_native_file_bytes", 8589934592),
    ):
        c.require(r[key]["value"] <= limit, "RA_G1_MONITOR_THRESHOLD")
    c.require(
        r["shared_bavail_bytes"]["value"]
        >= old.checked(next_write_bytes + m["shared_free_margin_bytes"])
        and r["shared_favail"]["value"]
        >= old.checked(next_creations + m["free_inode_margin"]),
        "RA_G1_SHARED_MARGIN",
    )
    c.require(
        record["exit_mono_ns"] - record["enter_mono_ns"] <= MAX_GAP_NS,
        "RA_G1_MONITOR_GAP",
    )
    counters, limits = record["counters"], selected["limits"]
    for role in ROLES:
        c.require(
            counters[role] <= limits["application_counters"][role],
            "RA_G1_COUNTER_LIMIT",
        )
    for counter, limit in (
        ("application_write_reserved_bytes", "logical_write_bytes"),
        ("application_creations_charged", "creations"),
        ("monitor_observations_charged", "monitor_rows"),
        ("monitor_write_bytes_charged", "monitor_bytes"),
        ("root_attempts", "attempts"),
    ):
        c.require(counters[counter] <= limits[limit], "RA_G1_COUNTER_LIMIT")
    for counter, field in (
        ("source_read_calls", "source_read_calls"),
        ("source_read_bytes", "source_read_bytes"),
        ("identity_checks", "check_calls"),
    ):
        c.require(
            counters[counter]
            <= old.checked(sum(stage[field] for stage in limits["stages"])),
            "RA_G1_COUNTER_LIMIT",
        )
    phase = next(
        (stage for stage in limits["stages"] if stage["id"] == record["phase_id"]), None
    )
    c.require(
        phase is not None and counters["segment_attempts"] <= phase["attempts"],
        "RA_G1_COUNTER_LIMIT",
    )


class Coverage:
    """Constant-state fresh original validation, without coverage repair."""

    def __init__(
        self: Any,
        *,
        binding_sha256: Any,
        selection_sha256: Any,
        phase_id: Any,
        seed_sha256: Any,
        selected: Any,
        scope_start_ns: Any,
    ) -> None:
        self.binding, self.selection, self.phase = (
            binding_sha256,
            selection_sha256,
            phase_id,
        )
        self.head, self.selected, self.scope_start = (
            seed_sha256,
            selected,
            scope_start_ns,
        )
        self.seq, self.last_enter, self.last_exit, self.max_gap = 0, None, None, 0
        self.first, self.final, self.counters = None, None, None

    def add(self: Any, record: Any) -> Any:
        validate(record)
        c.require(
            record["binding_sha256"] == self.binding
            and record["selection_sha256"] == self.selection
            and record["phase_id"] == self.phase
            and record["seq"] == self.seq + 1
            and record["previous_sha256"] == self.head
            and self.final is None,
            "RA_G1_PROTOCOL",
        )
        enter, exit_ns = record["enter_mono_ns"], record["exit_mono_ns"]
        if self.seq == 0:
            c.require(
                record["kind"] == "START" and self.scope_start <= enter,
                "RA_G1_PROTOCOL",
            )
            gap = enter - self.scope_start
            self.first = enter
        else:
            c.require(
                record["kind"] != "START" and enter >= self.last_exit, "RA_G1_PROTOCOL"
            )
            gap = enter - self.last_enter
        self.max_gap = max(self.max_gap, gap, exit_ns - enter)
        c.require(self.max_gap <= MAX_GAP_NS, "RA_G1_MONITOR_GAP")
        thresholds(record, self.selected)
        if self.counters is not None:
            c.require(
                all(record["counters"][key] >= self.counters[key] for key in COUNTERS),
                "RA_G1_COUNTER_LIMIT",
            )
        self.counters = dict(record["counters"])
        self.seq, self.last_enter, self.last_exit = record["seq"], enter, exit_ns
        self.head = hashlib.sha256(pack_observation(record)).hexdigest()
        if record["kind"] == "FINAL":
            self.final = record
        return self.head

    def inventory_sha256(self: Any) -> Any:
        return old.digest(
            {
                "schema_version": "stage12_resource_monitor_inventory_ra_g1_v1",
                "binding_sha256": self.binding,
                "selection_sha256": self.selection,
                "phase_id": self.phase,
                "last_seq": self.seq,
                "head_sha256": self.head,
                "bytes": self.seq * CODEC_BYTES,
            }
        )

    def require_complete(self: Any, *, opener_return_ns: Any, last_ack_ns: Any) -> Any:
        c.require(
            self.final is not None
            and self.seq >= 2
            and self.final["enter_mono_ns"] >= opener_return_ns
            and last_ack_ns >= self.last_exit
            and last_ack_ns - self.last_enter <= MAX_GAP_NS,
            "RA_G1_MONITOR_INCOMPLETE",
        )
        return self.max_gap


def _same_directory_leaf(path: Any, original: Any) -> bool:
    info = Path(path).stat(follow_symlinks=False)
    return tuple(original[1:]) == (info.st_dev, info.st_ino, info.st_mode, info.st_uid)


def charged_read(fd: Any, size: Any, charge_read: Any, *, offset: Any = None) -> bytes:
    """One actual read/pread: reserve the call, then charge only returned bytes."""
    charge_read(1, 0)
    raw = os.read(fd, size) if offset is None else os.pread(fd, size, offset)
    try:
        charge_read(0, len(raw))
        return raw
    finally:
        del raw


def emit_startup_trace(trace: Any, event: Any, *args: Any, **kwargs: Any) -> None:
    """Supplementary instrumentation cannot replace a core guard or poison."""
    if trace is None:
        return
    try:
        trace(event, *args, **kwargs)
    except BaseException:
        try:
            trace.note_instrumentation_fault()
        except BaseException:
            pass  # Missing diagnostics are unknown; no receipt/closure is invented.


class ObservationWriter:
    """One bounded supplementary writer, distinct from the campaign writer.

    Queue <=8 fixed codec blocks. Charges happen before queue admission and are
    never refunded. A timeout permanently poisons this owner; it cannot seal.
    """

    def __init__(
        self: Any,
        path: Any,
        *,
        maximum_rows: Any,
        charge: Any,
        check: Any,
        clock_ns: Any = time.monotonic_ns,
        original_root: Any = None,
        prewrite: Any = None,
        charge_read: Any = lambda calls, size: None,
        startup_trace: Any = None,
    ) -> None:
        c.require(
            type(maximum_rows) is int
            and maximum_rows >= 2
            and callable(charge)
            and callable(check),
            "RA_G1_PRECHARGE",
        )
        self.prewrite = prewrite
        self.startup_trace = startup_trace
        c.require(callable(charge_read), "RA_G1_PRECHARGE")
        self.charge_read = charge_read
        c.require(prewrite is None or callable(prewrite), "RA_G1_PRECHARGE")
        self.original_root = None if original_root is None else Path(original_root)
        self.original_ancestors: Any = None
        if self.original_root is not None:
            self.original_ancestors = a.private_root_identity(self.original_root)
        self._staged_original: tuple[str, bytes] | None = None
        self.path, self.maximum, self.charge, self.check, self.clock = (
            Path(path),
            maximum_rows,
            charge,
            check,
            clock_ns,
        )
        self.ancestors = a.private_root_identity(self.path.parent)
        self.root_fd = os.open(
            self.path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        self.original_root_fd: Any = (
            None
            if self.original_root is None
            else os.open(
                self.original_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            )
        )
        try:
            c.require(
                _same_directory_leaf(self.path.parent, self.ancestors[0])
                and a.kernel_identity(os.fstat(self.root_fd))
                == a.kernel_identity(self.path.parent.stat(follow_symlinks=False)),
                "RA_G1_ORIGINAL_CHANGED",
            )
            self.charge(0, 1)
            if self.prewrite is not None:
                self.prewrite(0, 1)
            self.fd = os.open(
                self.path.name,
                os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=self.root_fd,
            )
        except BaseException:
            os.close(self.root_fd)
            if self.original_root_fd is not None:
                os.close(self.original_root_fd)
            raise
        self.identity = os.fstat(self.fd)
        self.condition = threading.Condition()
        self.queue: deque[tuple[int, bytes, int, tuple[str, bytes] | None]] = deque()
        self.rows, self.acked = 0, 0
        self.first_failure = None
        self.stage, self.current_seq = "IDLE", 0
        self.ack_ns, self.poisoned, self.closing, self.released = 0, False, False, False
        self.thread = threading.Thread(
            target=self._run, name="ra-g1-evidence-writer", daemon=True
        )
        self.thread.start()

    def _progress(self, stage: str, seq: Any = None) -> None:
        with self.condition:
            self.stage = stage
            if seq is not None:
                self.current_seq = seq

    def diagnostic_snapshot(self) -> dict[str, Any]:
        """Fixed scalar state, copied under a short lock without I/O."""
        with self.condition:
            return dict(rows=self.rows, acked=self.acked, ack_ns=self.ack_ns,
                        poisoned=self.poisoned, closing=self.closing,
                        released=self.released, thread_alive=self.thread.is_alive(),
                        current_seq=self.current_seq, stage=self.stage,
                        first_failure=deepcopy_record(self.first_failure))

    def stage_original(self, raw: Any) -> str:
        c.require(
            type(raw) is bytes
            and 0 < len(raw) <= MAX_ORIGINAL_BYTES
            and self.original_root is not None,
            "RA_G1_RECORD_LIMIT",
        )
        digest = hashlib.sha256(raw).hexdigest()
        self.check()
        with self.condition:
            c.require(
                not self.poisoned
                and not self.closing
                and self._staged_original is None,
                "RA_G1_WRITE_UNCERTAIN",
            )
            self.charge(MAX_ORIGINAL_BYTES, 1)
            self._staged_original = (digest, raw)
        return digest

    def _persist_original(self, original: Any, deadline: Any, *, first_start: bool = False) -> None:
        trace = self.startup_trace if first_start else None
        if trace is not None:
            emit_startup_trace(trace, "ORIGINAL_PERSIST_ENTER", writer=self)
        digest, raw = original
        self.check()
        c.require(self.clock() < deadline, "RA_G1_DEADLINE")
        path = self.original_root / (digest + ".record")
        if self.prewrite is not None:
            self.prewrite(MAX_ORIGINAL_BYTES, 1)
        c.require(
            _same_directory_leaf(path.parent, self.original_ancestors[0])
            and a.kernel_identity(os.fstat(self.original_root_fd))
            == a.kernel_identity(path.parent.stat(follow_symlinks=False)),
            "RA_G1_ORIGINAL_CHANGED",
        )
        fd = os.open(
            path.name,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=self.original_root_fd,
        )
        try:
            identity = os.fstat(fd)
            self._progress("ORIGINAL_WRITE")
            offset = 0
            while offset < len(raw):
                self.check()
                c.require(self.clock() < deadline, "RA_G1_DEADLINE")
                n = os.write(fd, memoryview(raw)[offset:])
                c.require(n > 0, "RA_G1_WRITE_UNCERTAIN")
                offset += n
            if trace is not None:
                emit_startup_trace(trace, "ORIGINAL_FSYNC_BEFORE")
            self._progress("ORIGINAL_FSYNC")
            os.fsync(fd)
            if trace is not None:
                emit_startup_trace(trace, "ORIGINAL_FSYNC_AFTER")
                emit_startup_trace(trace, "ORIGINAL_READBACK_BEFORE")
            self._progress("ORIGINAL_READBACK")
            observed = hashlib.sha256()
            with scratch.ra_g1_lease("MONITOR_READBACK") as readback_bytes:
                for offset in range(0, len(raw), readback_bytes):
                    self.check()
                    c.require(self.clock() < deadline, "RA_G1_DEADLINE")
                    part = charged_read(
                        fd,
                        min(readback_bytes, len(raw) - offset),
                        self.charge_read,
                        offset=offset,
                    )
                    try:
                        c.require(
                            len(part) == min(readback_bytes, len(raw) - offset),
                            "RA_G1_WRITE_UNCERTAIN",
                        )
                        observed.update(part)
                    finally:
                        del part
            c.require(
                observed.hexdigest() == digest
                and a.kernel_identity(identity)
                == a.kernel_identity(os.fstat(fd))
                == a.kernel_identity(path.stat(follow_symlinks=False))
                and _same_directory_leaf(path.parent, self.original_ancestors[0]),
                "RA_G1_ORIGINAL_CHANGED",
            )
            self.check()
            c.require(self.clock() < deadline, "RA_G1_DEADLINE")
            if trace is not None:
                emit_startup_trace(trace, "ORIGINAL_READBACK_AFTER")
                emit_startup_trace(trace, "ORIGINAL_PERSIST_EXIT")
        finally:
            os.close(fd)

    def append(self: Any, block: Any, seq: Any, deadline_ns: Any) -> Any:
        c.require(type(block) is bytes and len(block) == CODEC_BYTES, "RA_G1_CODEC")
        self.check()
        with self.condition:
            c.require(
                not self.poisoned
                and not self.closing
                and seq == self.rows + 1
                and seq <= self.maximum
                and len(self.queue) < 8,
                "RA_G1_WRITE_UNCERTAIN",
            )
            self.charge(CODEC_BYTES, 0)
            self.rows += 1
            c.require(
                self.original_root is None or self._staged_original is not None,
                "RA_G1_ORIGINAL_CHANGED",
            )
            self.queue.append(
                (
                    seq,
                    block,
                    min(deadline_ns, self.clock() + GUARD_NS),
                    self._staged_original,
                )
            )
            self._staged_original = None
            self.condition.notify_all()

    def _run(self: Any) -> Any:
        try:
            while True:
                with self.condition:
                    while not self.queue and not self.closing:
                        self.condition.wait(0.1)
                    if not self.queue:
                        break
                    seq, block, deadline, original = self.queue.popleft()
                self._progress("CHECK", seq)
                trace = self.startup_trace if seq == 1 else None
                if trace is not None:
                    emit_startup_trace(trace, "WRITER_ENTER", writer=self)
                self.check()
                c.require(self.clock() < deadline, "RA_G1_DEADLINE")
                current = self.path.stat(follow_symlinks=False)
                c.require(
                    a.kernel_identity(current)
                    == a.kernel_identity(self.identity)
                    == a.kernel_identity(os.fstat(self.fd))
                    and current.st_nlink == 1
                    and current.st_size == (seq - 1) * CODEC_BYTES
                    and _same_directory_leaf(self.path.parent, self.ancestors[0]),
                    "RA_G1_ORIGINAL_CHANGED",
                )
                if original is not None:
                    self._persist_original(original, deadline, first_start=seq == 1)
                if self.prewrite is not None:
                    self.prewrite(CODEC_BYTES, 0)
                if trace is not None:
                    emit_startup_trace(trace, "CODEC_APPEND_ENTER")
                self._progress("CODEC_WRITE")
                offset = 0
                while offset < len(block):
                    self.check()
                    c.require(self.clock() < deadline, "RA_G1_DEADLINE")
                    n = os.write(self.fd, memoryview(block)[offset:])
                    c.require(n > 0, "RA_G1_WRITE_UNCERTAIN")
                    offset += n
                if trace is not None:
                    emit_startup_trace(trace, "CODEC_FSYNC_BEFORE")
                self._progress("CODEC_FSYNC")
                os.fsync(self.fd)
                if trace is not None:
                    emit_startup_trace(trace, "CODEC_FSYNC_AFTER")
                    emit_startup_trace(trace, "CODEC_READBACK_BEFORE")
                self._progress("CODEC_READBACK")
                c.require(
                    charged_read(
                        self.fd,
                        CODEC_BYTES,
                        self.charge_read,
                        offset=(seq - 1) * CODEC_BYTES,
                    )
                    == block,
                    "RA_G1_WRITE_UNCERTAIN",
                )
                self.check()
                c.require(self.clock() < deadline, "RA_G1_DEADLINE")
                if trace is not None:
                    emit_startup_trace(trace, "CODEC_READBACK_AFTER")
                with self.condition:
                    self.acked, self.ack_ns = seq, self.clock()
                    self.stage = "ACK"
                    self.condition.notify_all()
                if trace is not None:
                    emit_startup_trace(trace, "ACK_PUBLISHED", self.ack_ns)
        except BaseException as error:
            with self.condition:
                self.poisoned = True
                try:
                    if self.first_failure is None:
                        self.first_failure = _diagnostic_fault(
                            error, source="WRITER", stage=self.stage, clock=self.clock)
                except BaseException:
                    pass  # Diagnostics cannot suppress the uncertainty latch.
                finally:
                    self.condition.notify_all()
            if self.startup_trace is not None and self.rows <= 1:
                emit_startup_trace(self.startup_trace, "WRITER_FAILURE", writer=self, error=error)
        finally:
            os.close(self.fd)
            os.close(self.root_fd)
            if self.original_root_fd is not None:
                os.close(self.original_root_fd)
            with self.condition:
                self.released = not self.poisoned
                self.stage = "CLOSED"
                self.condition.notify_all()

    def wait(self: Any, seq: Any, deadline_ns: Any) -> Any:
        stop = min(deadline_ns, self.clock() + GUARD_NS)
        with self.condition:
            while self.acked < seq and not self.poisoned:
                remaining = stop - self.clock()
                if remaining <= 0:
                    self.poisoned = True
                    try:
                        if self.first_failure is None:
                            self.first_failure = _diagnostic_fault(
                                c.Stage12Error("RA_G1_WRITE_UNCERTAIN"),
                                source="WRITER", stage="WAIT_ACK", clock=self.clock)
                    except BaseException:
                        pass
                    finally:
                        self.condition.notify_all()
                    break
                self.condition.wait(min(remaining / 1e9, 0.1))
            c.require(not self.poisoned and self.acked >= seq, "RA_G1_WRITE_UNCERTAIN")
            return self.ack_ns

    def close(self: Any, deadline_ns: Any) -> Any:
        self.wait(self.rows, deadline_ns)
        with self.condition:
            self.closing = True
            self.condition.notify_all()
        self.thread.join(max(0, min(GUARD_NS, deadline_ns - self.clock())) / 1e9)
        c.require(
            not self.thread.is_alive()
            and self.released
            and not self.poisoned
            and self.clock() < deadline_ns,
            "RA_G1_WRITE_UNCERTAIN",
        )
        c.require(
            self.ancestors == a.private_root_identity(self.path.parent)
            and (
                self.original_root is None
                or self.original_ancestors
                == a.private_root_identity(self.original_root)
            ),
            "RA_G1_ORIGINAL_CHANGED",
        )
        self.check()


class ResourceMonitor:
    """Single acquisition owner attempts a real poll each 500ms.

    observer(kind) returns only {readings,counters,native_visibility,
    visible_identity_inventory_sha256}; all timestamps originate in that read.
    It must not acquire campaign/sampler locks. Late observations latch failure.
    """

    def __init__(
        self: Any,
        *,
        observer: Any,
        writer: Any,
        selected: Any,
        binding_sha256: Any,
        phase_id: Any,
        seed_sha256: Any,
        deadline_ns: Any,
        check: Any,
        clock_ns: Any = time.monotonic_ns,
        scope_start_ns: Any = None,
        startup_trace: Any = None,
        start_to_start: bool = False,
    ) -> None:
        c.require(type(start_to_start) is bool, "RA_G1_PROTOCOL")
        self.start_to_start = start_to_start
        self.observer, self.writer, self.selected, self.check, self.clock = (
            observer,
            writer,
            selected,
            check,
            clock_ns,
        )
        self.binding, self.selection, self.phase, self.seed = (
            binding_sha256,
            old.digest(selected),
            phase_id,
            seed_sha256,
        )
        self.deadline, self.stop_event, self.lock = (
            deadline_ns,
            threading.Event(),
            threading.Lock(),
        )
        self._cadence_condition = (
            threading.Condition(self.lock) if start_to_start else None
        )
        self.startup_trace = startup_trace
        self.seq, self.head, self.last, self.failure = 0, seed_sha256, None, None
        self.first_primary = None
        self.acquisition_kind, self.acquisition_stage = None, "IDLE"
        self.acquisition_enter, self.acquisition_exit = None, None
        self._diagnostic_published = False
        self._published_prefix: dict[str, Any] | None = None
        self.scope_start = self.clock() if scope_start_ns is None else scope_start_ns
        a.shape(self.scope_start, "U")
        c.require(self.scope_start <= self.clock(), "RA_G1_PROTOCOL")
        self.coverage = Coverage(
            binding_sha256=self.binding,
            selection_sha256=self.selection,
            phase_id=phase_id,
            seed_sha256=seed_sha256,
            selected=selected,
            scope_start_ns=self.scope_start,
        )
        self.thread = threading.Thread(
            target=self._run, name="ra-g1-resource-monitor", daemon=True
        )

    def diagnostic_snapshot(self) -> dict[str, Any]:
        """Bounded failure evidence, independent of the observation writer."""
        with self.lock:
            row = self.last
            published = None if row is None else dict(
                seq=row["seq"], enter_mono_ns=row["enter_mono_ns"],
                exit_mono_ns=row["exit_mono_ns"],
                ack_mono_ns=self._published_prefix["last_ack_ns"])
            snapshot = dict(
                phase_id=self.phase, monitor_failure=self.failure,
                first_primary=deepcopy_record(self.first_primary),
                acquisition=dict(kind=self.acquisition_kind, stage=self.acquisition_stage,
                                 enter_mono_ns=self.acquisition_enter,
                                 exit_mono_ns=self.acquisition_exit),
                published=published)
        reader = getattr(self.writer, "diagnostic_snapshot", None)
        snapshot["writer"] = reader() if callable(reader) else None
        if snapshot["first_primary"] is None:
            with self.lock:
                if self.failure is not None:
                    snapshot["monitor_failure"] = self.failure
                    snapshot["first_primary"] = deepcopy_record(self.first_primary)
                elif snapshot["writer"] is not None:
                    snapshot["first_primary"] = deepcopy_record(
                        snapshot["writer"]["first_failure"])
        return snapshot

    def _latch_failure(self, error: Any) -> None:
        claimed_ns = None
        try:
            with self.lock:
                first = self.failure is None
                if first:
                    self.failure = "RA_G1_MONITOR_INCOMPLETE"
                    try:
                        claimed_ns = self.clock()
                        if type(claimed_ns) is not int or not 0 <= claimed_ns <= 2**64 - 1:
                            claimed_ns = None
                    except BaseException:
                        pass
                if self._cadence_condition is not None:
                    self._cadence_condition.notify_all()
                publish = first and not self._diagnostic_published
                if first:
                    self._diagnostic_published = True
        finally:
            self.stop_event.set()
        if not first:
            return  # Only the first latch owner may install or publish its cause.
        try:
            code = (error.args[0] if type(error) is c.Stage12Error and error.args
                    and error.args[0] in FAILURE_CODES else "RA_G1_MONITOR_INCOMPLETE")
            with self.lock:
                if first:
                    self.failure = code
        except BaseException:
            pass  # The fallback failure and stop are already latched.
        fault = None
        try:
            fault = _diagnostic_fault(
                error, source="MONITOR", stage=self.acquisition_stage, clock=lambda: claimed_ns)
        except BaseException:
            pass
        try:
            reader = getattr(self.writer, "diagnostic_snapshot", None)
            writer = reader() if callable(reader) else None
            underlying = None if writer is None else writer["first_failure"]
            if (fault is not None and underlying is not None
                and type(fault["mono_ns"]) is int
                and type(underlying["mono_ns"]) is int
                and underlying["mono_ns"] < fault["mono_ns"]
            ):
                fault = underlying
        except BaseException:
            pass
        if fault is not None:
            try:
                with self.lock:
                    if self.first_primary is None:
                        self.first_primary = deepcopy_record(fault)
            except BaseException:
                pass
        if publish and self.startup_trace is not None:
            try:
                callback = getattr(self.startup_trace, "monitor_failure", None)
                if callable(callback):
                    callback(self.diagnostic_snapshot())
            except BaseException:
                try:
                    self.startup_trace.note_instrumentation_fault()
                except BaseException:
                    pass

    def _acquisition_progress(self, stage: str, *, enter: Any = None, exit_ns: Any = None) -> None:
        with self.lock:
            self.acquisition_stage = stage
            if enter is not None:
                self.acquisition_enter, self.acquisition_exit = enter, None
            if exit_ns is not None:
                self.acquisition_exit = exit_ns

    def _acquire(self: Any, kind: Any) -> Any:
        with self.lock:
            self.acquisition_kind, self.acquisition_stage = kind, "CHECK"
            self.acquisition_enter, self.acquisition_exit = None, None
        try:
            return self._acquire_once(kind)
        except BaseException as error:
            self._latch_failure(error)
            raise

    def _acquire_once(self: Any, kind: Any) -> Any:
        self.check()
        enter = self.clock()
        trace = self.startup_trace if kind == "START" else None
        if trace is not None:
            emit_startup_trace(trace, "FIRST_ACQUIRE_ENTER", enter)
        c.require(enter < self.deadline, "RA_G1_DEADLINE")
        self._acquisition_progress("OBSERVER", enter=enter)
        data = self.observer(kind)
        c.require(
            type(data) is dict
            and set(data)
            == {
                "readings",
                "counters",
                "native_visibility",
                "visible_identity_inventory_sha256",
            },
            "RA_G1_FIELDS",
        )
        exit_ns = self.clock()
        self._acquisition_progress("COVERAGE", exit_ns=exit_ns)
        if trace is not None:
            emit_startup_trace(trace, "FIRST_ACQUIRE_EXIT", exit_ns)
        record = dict(
            schema_version=OBSERVATION,
            binding_sha256=self.binding,
            selection_sha256=self.selection,
            phase_id=self.phase,
            seq=self.seq + 1,
            previous_sha256=self.head,
            kind=kind,
            enter_mono_ns=enter,
            exit_mono_ns=exit_ns,
            **data,
        )
        if trace is not None:
            emit_startup_trace(trace, "COVERAGE_BEFORE")
        head = self.coverage.add(record)
        if trace is not None:
            emit_startup_trace(trace, "COVERAGE_AFTER")
            emit_startup_trace(trace, "PACK_BEFORE")
        self._acquisition_progress("PACK")
        block = pack_observation(record)
        if trace is not None:
            emit_startup_trace(trace, "PACK_AFTER")
            emit_startup_trace(trace, "APPEND_BEFORE")
        self._acquisition_progress("APPEND")
        self.writer.append(block, record["seq"], self.deadline)
        if trace is not None:
            emit_startup_trace(trace, "APPEND_AFTER")
        self._acquisition_progress("WAIT_ACK")
        durable_ack_ns = self.writer.wait(record["seq"], self.deadline)
        if kind == "START":
            self.first_start_receipt = dict(row=deepcopy_record(record), ack_ns=durable_ack_ns)
        if trace is not None:
            emit_startup_trace(trace, "START_ACK", self.writer.ack_ns)
        self._acquisition_progress("POST_ACK_CHECK")
        self.check()
        with self.lock:
            self.acquisition_stage = "PUBLISH"
            self.seq, self.head, self.last = (
                record["seq"],
                head,
                deepcopy_record(record),
            )
            self._published_prefix = dict(
                last_seq=self.seq,
                head_sha256=head,
                inventory_sha256=self.coverage.inventory_sha256(),
                max_gap_ns=self.coverage.max_gap,
                last_enter_ns=record["enter_mono_ns"],
                last_exit_ns=record["exit_mono_ns"],
                last_ack_ns=self.writer.ack_ns,
                counters=dict(record["counters"]),
                scope_start_ns=self.scope_start,
            )
            if self._cadence_condition is not None:
                self._cadence_condition.notify_all()
        return record

    def start(self: Any) -> Any:
        self._acquire("START")
        self.thread.start()
        return self

    def _run(self: Any) -> Any:
        try:
            if not self.start_to_start:
                while not self.stop_event.wait(PERIOD_NS / 1e9):
                    self._acquire("PERIODIC")
            else:
                while True:
                    with self.lock:
                        entered = self.last["enter_mono_ns"]
                    remaining = max(0, entered + PERIOD_NS - self.clock())
                    if self.stop_event.wait(remaining / 1e9):
                        break
                    if self.clock() < entered + PERIOD_NS:
                        continue
                    # One owner, one new actual-enter anchor. Missed time never
                    # creates queued or catch-up acquisitions.
                    self._acquire("PERIODIC")
        except BaseException as error:
            self._latch_failure(error)

    def prefix(self) -> Any:
        """Atomic last ACKed H0 state; no campaign/acquisition lock or I/O."""
        self.check()
        with self.lock:
            c.require(
                self.failure is None
                and self._published_prefix is not None
                and not self.writer.poisoned,
                "RA_G1_MONITOR_INCOMPLETE",
            )
            return deepcopy_record(self._published_prefix)

    def barrier(
        self: Any, *, next_write_bytes: Any = 0, next_creations: Any = 0
    ) -> Any:
        try:
            if not self.start_to_start:
                self.check()
            if self._cadence_condition is not None:
                with self._cadence_condition:
                    row = self.last
                    now = self.clock()
                    c.require(now < self.deadline, "RA_G1_DEADLINE")
                    incoming = self.acquisition_enter
                    if (
                        self.failure is None
                        and row is not None
                        and not self.writer.poisoned
                        and self.writer.acked >= row["seq"]
                        and now - row["enter_mono_ns"] > MAX_GAP_NS
                        and self.acquisition_kind == "PERIODIC"
                        and self.acquisition_stage != "PUBLISH"
                        and type(incoming) is int
                        and row["enter_mono_ns"] < incoming <= now
                        and incoming - row["enter_mono_ns"] <= MAX_GAP_NS
                        and now < min(self.deadline, incoming + MAX_GAP_NS)
                    ):
                        # Only an already-running next acquisition can help.
                        # A single wait is bounded by that row's unchanged
                        # freshness horizon and the original phase deadline.
                        end = min(self.deadline, incoming + MAX_GAP_NS)
                        self._cadence_condition.wait((end - now) / 1e9)
                # One external check, as before. Waiting performs only bounded
                # state/clock inspection; no evidence I/O or application write.
                self.check()
            with self.lock:
                row, failure = self.last, self.failure
            c.require(failure is None, failure or "RA_G1_MONITOR_INCOMPLETE")
            c.require(row is not None, "RA_G1_MONITOR_INCOMPLETE")
            c.require(not self.writer.poisoned and self.writer.acked >= row["seq"],
                      "RA_G1_WRITE_UNCERTAIN")
            c.require(0 <= self.clock() - row["enter_mono_ns"] <= MAX_GAP_NS,
                      "RA_G1_MONITOR_GAP")
            c.require(self.clock() < self.deadline, "RA_G1_DEADLINE")
            thresholds(row, self.selected, next_write_bytes=next_write_bytes,
                       next_creations=next_creations)
            return deepcopy_record(row)
        except BaseException as error:
            self._latch_failure(error)
            raise

    def finish(self: Any, *, opener_return_ns: Any) -> Any:
        c.require(self.failure is None, "RA_G1_MONITOR_INCOMPLETE")
        self.stop_event.set()
        self.thread.join(max(0, min(GUARD_NS, self.deadline - self.clock())) / 1e9)
        c.require(not self.thread.is_alive(), "RA_G1_MONITOR_INCOMPLETE")
        final = self._acquire("FINAL")
        self.coverage.require_complete(
            opener_return_ns=opener_return_ns, last_ack_ns=self.writer.ack_ns
        )
        self.writer.close(self.deadline)
        return final


def read_observations(
    path: Any,
    *,
    maximum_rows: Any,
    check: Any = lambda: None,
    charge_read: Any = lambda calls, size: None,
) -> Any:
    """Fresh bounded stream; EOF, failed reads and mutation are charged."""
    path = Path(path)
    before_root = a.private_root_identity(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        c.require(
            stat.S_ISREG(before.st_mode)
            and before.st_uid == os.geteuid()
            and stat.S_IMODE(before.st_mode) == 0o600
            and before.st_nlink == 1
            and before.st_size <= maximum_rows * CODEC_BYTES,
            "RA_G1_ORIGINAL_CHANGED",
        )
        for _ in range(maximum_rows + 1):
            check()
            raw = charged_read(fd, CODEC_BYTES, charge_read)
            if not raw:
                break
            c.require(len(raw) == CODEC_BYTES, "RA_G1_ORIGINAL_CHANGED")
            yield unpack_observation(raw)
        else:
            raise c.Stage12Error("RA_G1_READ_LIMIT")
        after, current = os.fstat(fd), path.stat(follow_symlinks=False)
        attrs = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_uid",
            "st_gid",
            "st_nlink",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        c.require(
            all(
                getattr(before, key) == getattr(after, key) == getattr(current, key)
                for key in attrs
            )
            and before_root == a.private_root_identity(path.parent),
            "RA_G1_ORIGINAL_CHANGED",
        )
        check()
    finally:
        os.close(fd)


STATES = (
    "RUNNING",
    "DATA_FROZEN",
    "PREOPEN_READY",
    "OPENING",
    "OPEN_RETURNED",
    "MONITOR_CLOSED",
    "CHILD_EXITED",
    "TAIL_VERIFIED",
    "TERMINAL_SUCCESS",
)
ABSORBING = ("STOPPED", "INCOMPLETE", "UNCERTAIN")


class PhaseProtocol:
    """Only an actual callback return can create the acyclic opener record."""

    def __init__(
        self: Any,
        *,
        binding_sha256: Any,
        selection_sha256: Any,
        phase_id: Any,
        deadline_ns: Any,
        check: Any,
        clock_ns: Any = time.monotonic_ns,
    ) -> None:
        self.binding, self.selection, self.phase = (
            binding_sha256,
            selection_sha256,
            phase_id,
        )
        self.deadline, self.check, self.clock, self.state = (
            deadline_ns,
            check,
            clock_ns,
            "RUNNING",
        )
        self.closure, self.opener, self.terminal = None, None, None
        self.bootstrap_evidence_sha256 = None

    def guard(self: Any) -> Any:
        self.check()
        c.require(
            self.clock() < self.deadline and self.state not in ABSORBING,
            "RA_G1_DEADLINE",
        )

    def advance(self: Any, state: Any) -> Any:
        self.guard()
        c.require(
            state in STATES and STATES.index(state) == STATES.index(self.state) + 1,
            "RA_G1_PROTOCOL",
        )
        self.state = state

    def freeze(self: Any, inventory_sha256: Any) -> Any:
        a.shape(inventory_sha256, "D")
        self.inventory = inventory_sha256
        self.advance("DATA_FROZEN")

    def preopen(self: Any, closure: Any) -> Any:
        validate(closure, BOOTSTRAP_PROTOCOL_IDS[CLOSURE] if self.bootstrap_evidence_sha256 is not None else CLOSURE)
        c.require(closure.get("bootstrap_evidence_sha256") == self.bootstrap_evidence_sha256, "RA_G1_BOOTSTRAP_REQUIRED")
        c.require(
            closure["outcome"] == "PENDING_OPEN"
            and closure["monitor_coverage"] == "COMPLETE_SELECTED_SCOPE"
            and closure["binding_sha256"] == self.binding
            and closure["selection_sha256"] == self.selection
            and closure["phase_id"] == self.phase,
            "RA_G1_PROTOCOL",
        )
        self.closure = deepcopy_record(closure)
        self.advance("PREOPEN_READY")

    def open(
        self: Any,
        actual_opener: Any,
        *,
        expected_negative_sha256: Any = None,
        is_expected_negative: Any = None,
    ) -> Any:
        self.advance("OPENING")
        started = self.clock()
        disposition, failure = "DATA_OPENED", None
        try:
            result = actual_opener()
        except BaseException as error:
            if isinstance(
                error, (TimeoutError, OSError, recovery.FinalizationExpired)
            ) or (
                type(error) is c.Stage12Error
                and error.args
                and type(error.args[0]) is str
                and (
                    error.args[0].startswith(("RA_G1_", "CHECKPOINT_", "WF_AP2_"))
                    or "SAMPLING" in error.args[0]
                    or error.args[0]
                    in (
                        "S12_PUBLIC_WINDOW_CLOSED",
                        "S12_PUBLIC_STORAGE_ACCOUNTING_MISMATCH",
                        "PUBLIC_PROBE_EVIDENCE_WRITE_FAILED",
                        "S12_PRIVATE_FILE_INVALID",
                    )
                )
            ):
                self.state = "INCOMPLETE"
                raise
            if (
                expected_negative_sha256 is None
                or not callable(is_expected_negative)
                or not is_expected_negative(error)
            ):
                self.state = "INCOMPLETE"
                raise
            disposition, result = "EXPECTED_NEGATIVE_REJECTED", None
        ended = self.clock()
        self.guard()
        record = dict(
            schema_version=OPENER,
            binding_sha256=self.binding,
            selection_sha256=self.selection,
            phase_id=self.phase,
            preopening_closure_sha256=old.digest(self.closure),
            frozen_data_inventory_sha256=self.inventory,
            validated_monitor_prefix_sha256=self.closure[
                "original_observation_prefix_sha256"
            ],
            actual_opener_start_ns=started,
            actual_opener_return_ns=ended,
            opener_disposition=disposition,
            expected_negative_spec_sha256=expected_negative_sha256
            if disposition == "EXPECTED_NEGATIVE_REJECTED"
            else None,
            failure=failure,
        )
        record = bootstrap_protocol_record(record, self.bootstrap_evidence_sha256)
        validate(record)
        self.opener = record
        self.advance("OPEN_RETURNED")
        return result, record

    def monitor_closed(self: Any, record: Any) -> Any:
        validate(record, BOOTSTRAP_PROTOCOL_IDS[MONITOR_TERMINAL] if self.bootstrap_evidence_sha256 is not None else MONITOR_TERMINAL)
        c.require(record.get("bootstrap_evidence_sha256") == self.bootstrap_evidence_sha256, "RA_G1_BOOTSTRAP_REQUIRED")
        c.require(
            record["binding_sha256"] == self.binding
            and record["phase_id"] == self.phase
            and record["opener_return_sha256"] == old.digest(self.opener)
            and record["prefix_H0_sha256"]
            == self.closure["original_observation_prefix_sha256"]
            and record["final_observation_ns"] >= self.opener["actual_opener_return_ns"]
            and record["disposition"] == "CLOSED_SELECTED_SCOPE",
            "RA_G1_PROTOCOL",
        )
        self.terminal = deepcopy_record(record)
        self.advance("MONITOR_CLOSED")


def deepcopy_record(record: Any) -> Any:
    from copy import deepcopy

    return deepcopy(record)


def verify_tail(
    *,
    protocol: Any,
    monitor_path: Any,
    selected: Any,
    seed_sha256: Any,
    child_result: Any,
    genuine_wait_status: Any,
    expected_child_pid: Any,
    current_counter_sha256: Any,
    persist_terminal: Any,
    original_observation_reader: Any,
    test_only: Any = False,
    worker_validation: Any = None,
    charge_read: Any = lambda calls, size: None,
) -> Any:
    """Finite supervisor suffix, using genuine os.waitpid status.

    child_result must be the caller's original {pid,wait_status,acquired_mono_ns};
    an arbitrary child-produced file cannot substitute for waitpid's return.
    persist_terminal must exclusively write+fsync+fresh-readback under guards.
    The caller separately retains the successful supervisor return original.
    """
    protocol.guard()
    bootstrap = None
    need_bootstrap = a.bootstrap_role(selected, protocol.phase) is not None
    c.require(need_bootstrap == (protocol.bootstrap_evidence_sha256 is not None), "RA_G1_BOOTSTRAP_REQUIRED")
    if need_bootstrap:
        bootstrap = read_record(Path(monitor_path).parent / "bootstrap_prefix.record",
            expected_sha256=protocol.bootstrap_evidence_sha256, check=protocol.guard, charge_read=charge_read)
        a.validate_bootstrap_evidence(bootstrap, selected, binding_sha256=protocol.binding, root=Path(monitor_path).parent)
        c.require(protocol.terminal["coverage_start_ns"] == bootstrap["bootstrap_end_mono_ns"]
                  and protocol.opener["actual_opener_return_ns"] < bootstrap["phase_deadline_mono_ns"]
                  and protocol.terminal["last_ack_ns"] < bootstrap["phase_deadline_mono_ns"], "RA_G1_BOOTSTRAP_LIMIT")
        if worker_validation is not None:
            c.require(worker_validation["first_pass_end_ns"] < bootstrap["phase_deadline_mono_ns"], "RA_G1_BOOTSTRAP_LIMIT")
    c.require(callable(original_observation_reader), "RA_G1_ORIGINAL_CHANGED")
    c.require(
        protocol.state == "MONITOR_CLOSED"
        and type(genuine_wait_status) is int
        and type(expected_child_pid) is int
        and expected_child_pid > 0
        and type(child_result) is dict
        and set(child_result) == {"pid", "wait_status", "acquired_mono_ns"}
        and child_result["pid"] == expected_child_pid
        and child_result["wait_status"] == genuine_wait_status,
        "RA_G1_PROTOCOL",
    )
    c.require(
        os.WIFEXITED(genuine_wait_status) and os.WEXITSTATUS(genuine_wait_status) == 0,
        "RA_G1_PROTOCOL",
    )
    a.shape(child_result["acquired_mono_ns"], "U")
    c.require(
        protocol.terminal["last_ack_ns"]
        <= child_result["acquired_mono_ns"]
        <= protocol.clock(),
        "RA_G1_PROTOCOL",
    )
    if worker_validation is not None:
        from .s12_ra_g1_execution import validate_worker_validation

        validate_worker_validation(worker_validation, protocol=protocol)
        c.require(
            worker_validation["first_pass_end_ns"] <= child_result["acquired_mono_ns"],
            "RA_G1_PROTOCOL",
        )
    protocol.advance("CHILD_EXITED")
    started = protocol.clock()
    terminal = protocol.terminal
    scope = Coverage(
        binding_sha256=protocol.binding,
        selection_sha256=protocol.selection,
        phase_id=protocol.phase,
        seed_sha256=seed_sha256,
        selected=selected,
        scope_start_ns=terminal["coverage_start_ns"],
    )
    full_stream_digest = hashlib.sha256()
    for row in read_observations(
        monitor_path,
        maximum_rows=selected["limits"]["monitor_rows"],
        check=protocol.guard,
        charge_read=charge_read,
    ):
        validate_original_observation(
            original_observation_reader(row["visible_identity_inventory_sha256"]),
            observation=row,
            allow_synthetic=test_only,
        )
        if bootstrap is not None and row["seq"] == 1:
            a.validate_bootstrap_evidence(bootstrap, selected, binding_sha256=protocol.binding, root=Path(monitor_path).parent, first=row)
        scope.add(row)
        full_stream_digest.update(pack_observation(row))
        if scope.seq == protocol.closure["last_seq"]:
            c.require(
                old.digest(row["counters"]) == protocol.closure["counter_totals_sha256"]
                and scope.max_gap == protocol.closure["max_observed_gap_ns"],
                "RA_G1_ORIGINAL_CHANGED",
            )
            c.require(
                scope.inventory_sha256()
                == protocol.closure["original_observation_prefix_sha256"],
                "RA_G1_ORIGINAL_CHANGED",
            )
    c.require(
        scope.inventory_sha256() == terminal["full_monitor_inventory_sha256"],
        "RA_G1_ORIGINAL_CHANGED",
    )
    scope.require_complete(
        opener_return_ns=protocol.opener["actual_opener_return_ns"],
        last_ack_ns=terminal["last_ack_ns"],
    )
    c.require(
        scope.seq == terminal["last_seq"]
        and scope.head == terminal["final_observation_sha256"]
        and scope.last_exit == terminal["final_observation_ns"]
        and scope.max_gap == terminal["max_gap_ns"],
        "RA_G1_ORIGINAL_CHANGED",
    )
    if worker_validation is None:
        # Independent second original reread detects changes during first validation.
        second = Coverage(
            binding_sha256=protocol.binding,
            selection_sha256=protocol.selection,
            phase_id=protocol.phase,
            seed_sha256=seed_sha256,
            selected=selected,
            scope_start_ns=terminal["coverage_start_ns"],
        )
        for row in read_observations(
            monitor_path,
            maximum_rows=selected["limits"]["monitor_rows"],
            check=protocol.guard,
            charge_read=charge_read,
        ):
            validate_original_observation(
                original_observation_reader(row["visible_identity_inventory_sha256"]),
                observation=row,
                allow_synthetic=test_only,
            )
            second.add(row)
        c.require(
            second.head == scope.head and second.seq == scope.seq,
            "RA_G1_ORIGINAL_CHANGED",
        )
    else:
        info = Path(monitor_path).stat(follow_symlinks=False)
        actual_source = dict(
            device=info.st_dev,
            inode=info.st_ino,
            mode=info.st_mode,
            uid=info.st_uid,
            gid=info.st_gid,
            nlink=info.st_nlink,
            bytes=info.st_size,
            mtime_ns=info.st_mtime_ns,
            ctime_ns=info.st_ctime_ns,
            sha256=full_stream_digest.hexdigest(),
        )
        c.require(
            old.digest(actual_source)
            == worker_validation["monitor_source_identity_sha256"],
            "RA_G1_ORIGINAL_CHANGED",
        )
    protocol.advance("TAIL_VERIFIED")
    ended = protocol.clock()
    record = dict(
        schema_version=PHASE_TERMINAL,
        binding_sha256=protocol.binding,
        selection_sha256=protocol.selection,
        phase_id=protocol.phase,
        opener_return_sha256=old.digest(protocol.opener),
        monitor_terminal_sha256=old.digest(terminal),
        child_result_original_sha256=old.digest(child_result),
        child_exit_code=0,
        child_signal=None,
        tail_check_start_ns=started,
        tail_check_end_ns=ended,
        terminal_prewrite_ns=protocol.clock(),
        root_counter_watermarks_sha256=current_counter_sha256()
        if callable(current_counter_sha256)
        else current_counter_sha256,
        disposition="EXPECTED_NEGATIVE_VERIFIED"
        if protocol.opener["opener_disposition"] == "EXPECTED_NEGATIVE_REJECTED"
        else "COMPLETE_SELECTED_SCOPE",
        first_failure=None,
        cleanup_failure=None,
    )
    record = bootstrap_protocol_record(record, protocol.bootstrap_evidence_sha256)
    validate(record)
    protocol.guard()
    # Guarded readback equality and post-write deadline are part of success.
    write_started = protocol.clock()
    actual = persist_terminal(record, protocol.guard)
    c.require(
        actual == record and protocol.clock() - write_started <= GUARD_NS,
        "RA_G1_WRITE_UNCERTAIN",
    )
    protocol.guard()
    protocol.advance("TERMINAL_SUCCESS")
    return record


class LinuxObserver:
    """Bounded Linux registered-visible reader; hidden descendants stay unknown.

    At most twelve proc records/poll (cgroup/status/stat per registered PID;
    cgroup.procs is additionally attempted only for rosters of at most three),
    <=64 selected native lstat calls and one statvfs. Full ancestor/source/backend
    inventories belong to phase boundaries. retain_originals must persist this
    finite original metadata through the selected separate evidence owner.
    """

    def __init__(
        self: Any,
        *,
        pids: Any,
        cgroup_path: Any,
        root: Any,
        native_paths: Any,
        native_roots: Any = None,
        counter_provider: Any,
        retain_originals: Any,
        admitted_process_provider: Any = None,
        read_charge: Any = None,
        check: Any = lambda: None,
        clock_ns: Any = time.monotonic_ns,
    ) -> None:
        c.require(
            type(pids) is tuple
            and 1 <= len(pids) <= 4
            and len(set(pids)) == len(pids)
            and all(type(pid) is int and pid > 0 for pid in pids)
            and os.getpid() in pids,
            "RA_G1_PROCESS_SCOPE",
        )
        c.require(
            type(native_paths) is tuple
            and len(native_paths) <= MAX_NAMES
            and callable(counter_provider)
            and callable(retain_originals),
            "RA_G1_NATIVE_DISCOVERY",
        )
        self.pids, self.domain, self.root, self.paths = (
            pids,
            Path(cgroup_path),
            Path(root),
            native_paths,
        )
        c.require(
            self.domain.is_absolute()
            and str(self.domain).startswith("/sys/fs/cgroup")
            and self.domain.resolve(strict=True) == self.domain,
            "RA_G1_PROCESS_SCOPE",
        )
        self.root_identity = a.private_root_identity(self.root)
        self.native_roots = (self.root,) if native_roots is None else native_roots
        c.require(
            type(self.native_roots) is tuple
            and 1 <= len(self.native_roots) <= 16
            and len(set(self.native_roots)) == len(self.native_roots)
            and len(native_paths) + len(self.native_roots) <= 64,
            "RA_G1_NATIVE_DISCOVERY",
        )
        self.native_root_identities: dict[Path, Any] = {}
        filesystem_device = self.root.stat(follow_symlinks=False).st_dev
        for native_root in self.native_roots:
            c.require(isinstance(native_root, Path), "RA_G1_NATIVE_DISCOVERY")
            self.native_root_identities[native_root] = a.private_root_identity(
                native_root
            )
            c.require(
                native_root.stat(follow_symlinks=False).st_dev == filesystem_device,
                "RA_G1_NATIVE_FILESYSTEM_SCOPE",
            )
        self.counter_provider, self.retain, self.check, self.clock = (
            counter_provider,
            retain_originals,
            check,
            clock_ns,
        )
        c.require(
            callable(admitted_process_provider) and callable(read_charge),
            "RA_G1_PROCESS_SCOPE",
        )
        self.admitted_process_provider = admitted_process_provider
        self.read_charge = read_charge
        self.identities: dict[int, int] = {}
        self.read_calls, self.read_bytes, self.stat_calls = 0, 0, 0
        for path in native_paths:
            c.require(
                isinstance(path, Path)
                and path.is_absolute()
                and len(path.name.encode("utf-8")) <= 512
                and path.parent in self.native_roots,
                "RA_G1_NATIVE_DISCOVERY",
            )

    def __call__(self: Any, kind: Any) -> Any:
        c.require(kind in _KINDS, "RA_G1_FIELDS")
        originals: dict[str, Any] = {
            "schema_version": ORIGINAL_OBSERVATION,
            "origin": "LIVE_KERNEL_OBSERVATION",
            "kernel_records": [],
            "self_pid": os.getpid(),
        }
        readings: dict[str, Any] = {}
        rss, threads = 0, 0
        starts: dict[int, int] = {}
        calls, read_bytes = 0, 0
        call_start = self.read_calls

        def read(path: Any, source: Any, pid: Any = 0) -> Any:
            nonlocal calls, read_bytes
            self.check()
            calls += 1
            c.require(calls <= 12, "RA_G1_READ_LIMIT")
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                before = os.fstat(fd)
                block = bytearray(8192)
                used = 0
                while used < 8192:
                    self.check()
                    self.read_calls += 1
                    self.read_charge(1, 0)
                    size = os.readv(fd, [memoryview(block)[used:]])
                    self.read_charge(0, size)
                    if not size:
                        break
                    used += size
                self.read_bytes += used
                read_bytes += used
                c.require(
                    used < 8192
                    and a.kernel_identity(before)
                    == a.kernel_identity(os.fstat(fd))
                    == a.kernel_identity(Path(path).stat(follow_symlinks=False)),
                    "RA_G1_ORIGINAL_CHANGED",
                )
                text = memoryview(block)[:used].tobytes().decode("ascii")
                originals["kernel_records"].append(
                    {
                        "source": source,
                        "pid": pid,
                        "text": text,
                        "acquired_mono_ns": self.clock(),
                        "identity": list(a.kernel_identity(before)),
                    }
                )
                return text
            finally:
                os.close(fd)

        with scratch.lease("KERNEL"):
            if self.admitted_process_provider is not None:
                admitted = self.admitted_process_provider()
                c.require(
                    type(admitted) is tuple and set(admitted).issubset(set(self.pids)),
                    "RA_G1_PROCESS_SCOPE",
                )
            if len(self.pids) <= 3:
                try:
                    members = read(self.domain / "cgroup.procs", "CGROUP_PROCS").split()
                    originals["cgroup_visible_members"] = "ORIGINAL_RETAINED"
                    c.require(
                        all(value.isdecimal() for value in members)
                        and set(self.pids).issubset(set(map(int, members))),
                        "RA_G1_PROCESS_SCOPE",
                    )
                except (FileNotFoundError, PermissionError):
                    originals["cgroup_visible_members"] = "UNAVAILABLE"
            else:
                originals["cgroup_visible_members"] = (
                    "UNSELECTED_FOR_FOUR_PROCESS_ROSTER"
                )
            for pid in self.pids:
                membership = read(
                    Path(f"/proc/{pid}/cgroup"), "PID_CGROUP", pid
                ).strip()
                expected_membership = "0::" + (
                    "/" + str(self.domain.relative_to("/sys/fs/cgroup"))
                    if self.domain != Path("/sys/fs/cgroup")
                    else "/"
                )
                c.require(membership == expected_membership, "RA_G1_PROCESS_SCOPE")
                status = read(Path(f"/proc/{pid}/status"), "PID_STATUS", pid)
                fields = {}
                for line in status.splitlines():
                    name, separator, value = line.partition(":")
                    if separator and name in (
                        "VmRSS",
                        "VmHWM",
                        "Threads",
                        "Pid",
                        "Uid",
                    ):
                        c.require(name not in fields, "RA_G1_REQUIRED_READING")
                        fields[name] = value.strip()
                c.require(
                    set(fields) == {"VmRSS", "VmHWM", "Threads", "Pid", "Uid"}
                    and fields["Pid"] == str(pid)
                    and fields["Uid"].split() == [str(os.geteuid())] * 4,
                    "RA_G1_REQUIRED_READING",
                )

                def kib(key: Any) -> Any:
                    values = fields[key].split()
                    c.require(
                        len(values) == 2
                        and values[0].isdecimal()
                        and values[1] == "kB",
                        "RA_G1_REQUIRED_READING",
                    )
                    return old.checked(int(values[0]) * 1024)

                rss = old.checked(rss + kib("VmRSS"))
                c.require(fields["Threads"].isdecimal(), "RA_G1_REQUIRED_READING")
                threads = old.checked(threads + int(fields["Threads"]))
                if pid == os.getpid():
                    readings["self_rss_peak_bytes"] = a.known(
                        kib("VmHWM"), "PROCESS", "SELF", self.clock()
                    )
                process_stat = read(Path(f"/proc/{pid}/stat"), "PID_STAT", pid)
                suffix = process_stat.rpartition(") ")[2].split()
                c.require(
                    len(suffix) >= 20 and suffix[19].isdecimal(),
                    "RA_G1_REQUIRED_READING",
                )
                starts[pid] = int(suffix[19])
            if self.identities:
                c.require(starts == self.identities, "RA_G1_PROCESS_SCOPE")
            else:
                self.identities = dict(starts)
            readings["registered_visible_rss_bytes"] = a.known(
                rss, "PROCESS", "REGISTERED_VISIBLE", self.clock()
            )
            readings["visible_native_threads"] = a.known(
                threads, "PROCESS", "REGISTERED_VISIBLE", self.clock()
            )
            readings["visible_processes"] = a.known(
                len(self.pids), "PROCESS", "REGISTERED_VISIBLE", self.clock()
            )
            allocated, linked = 0, 0
            native_originals: list[dict[str, Any]] = []
            for native_root, identity in self.native_root_identities.items():
                info = native_root.stat(follow_symlinks=False)
                self.stat_calls += 1
                c.require(
                    tuple(identity[0][1:])
                    == (info.st_dev, info.st_ino, info.st_mode, info.st_uid),
                    "RA_G1_ORIGINAL_CHANGED",
                )
            for path in self.paths:
                self.check()
                self.stat_calls += 1
                try:
                    info = path.lstat()
                except FileNotFoundError:
                    native_originals.append(
                        {"role_id": len(native_originals) + 1, "status": "ABSENT"}
                    )
                    continue
                c.require(
                    stat.S_ISREG(info.st_mode)
                    and info.st_uid == os.geteuid()
                    and info.st_nlink == 1
                    and stat.S_IMODE(info.st_mode) == 0o600
                    and info.st_blocks >= 0,
                    "RA_G1_NATIVE_DISCOVERY",
                )
                allocated = old.checked(allocated + info.st_blocks * 512)
                linked += 1
                native_originals.append(
                    {
                        "role_id": len(native_originals) + 1,
                        "status": "VISIBLE_LINKED",
                        "device": info.st_dev,
                        "inode": info.st_ino,
                        "blocks_512_bytes": info.st_blocks,
                        "logical_bytes": info.st_size,
                    }
                )
            native_reading = a.known(
                allocated, "FILESYSTEM", "REGISTERED_VISIBLE", self.clock()
            )
            readings["visible_native_file_bytes"] = native_reading
            self.check()
            filesystem = os.statvfs(self.root)
            root_info = self.root.stat(follow_symlinks=False)
            self.stat_calls += 1
            at = self.clock()
            c.require(
                filesystem.f_frsize > 0
                and 0 <= filesystem.f_bavail <= filesystem.f_blocks
                and 0 <= filesystem.f_favail <= filesystem.f_files
                and tuple(self.root_identity[0][1:])
                == (
                    root_info.st_dev,
                    root_info.st_ino,
                    root_info.st_mode,
                    root_info.st_uid,
                ),
                "RA_G1_REQUIRED_READING",
            )
            readings["shared_bavail_bytes"] = a.known(
                old.checked(filesystem.f_bavail * filesystem.f_frsize),
                "FILESYSTEM",
                "FILESYSTEM_SHARED",
                at,
            )
            readings["shared_favail"] = a.known(
                filesystem.f_favail, "FILESYSTEM", "FILESYSTEM_SHARED", at
            )
            originals["filesystem"] = {
                key: getattr(filesystem, key)
                for key in ("f_frsize", "f_bavail", "f_favail", "f_blocks", "f_files")
            }
            originals["native"] = native_originals
            originals["registered_process_start_ticks"] = [
                [pid, starts[pid]] for pid in self.pids
            ]
            (
                originals["proc_records"],
                originals["read_calls"],
                originals["read_bytes"],
            ) = calls, self.read_calls - call_start, read_bytes
            counters = dict(self.counter_provider())
            a.shape(counters, {key: "U" for key in COUNTERS})
            originals["counters"] = counters
            validate_original_observation(originals)
            retained = self.retain(originals)
            a.shape(retained, "D")
            c.require(retained == old.digest(originals), "RA_G1_ORIGINAL_CHANGED")
        return dict(
            readings=readings,
            counters=counters,
            native_visibility=dict(
                registered_paths_checked=len(self.paths),
                visible_linked_files=linked,
                discovered_names=len(self.paths),
                maximum_discovered_names=64,
                discovery_status="COMPLETE_KNOWN_NAMESPACE",
                visible_allocated_bytes=native_reading,
                unknown_native_file_count="NOT_PROVEN",
                deleted_open_bytes="NOT_MEASURED",
            ),
            visible_identity_inventory_sha256=retained,
        )


def read_record(
    path: Any,
    *,
    expected_sha256: Any,
    check: Any = lambda: None,
    charge_read: Any = lambda calls, size: None,
) -> Any:
    """Fresh canonical original, private identity checked before and after read."""
    import json

    path = Path(path)
    ancestors = a.private_root_identity(path.parent)
    check()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        c.require(
            stat.S_ISREG(before.st_mode)
            and before.st_uid == os.geteuid()
            and before.st_nlink == 1
            and stat.S_IMODE(before.st_mode) == 0o600
            and 0 < before.st_size <= MAX_RECORD_BYTES,
            "RA_G1_ORIGINAL_CHANGED",
        )
        raw = charged_read(fd, MAX_RECORD_BYTES, charge_read)
        c.require(not charged_read(fd, 1, charge_read), "RA_G1_ORIGINAL_CHANGED")
        c.require(
            len(raw) == before.st_size
            and hashlib.sha256(raw).hexdigest() == expected_sha256,
            "RA_G1_ORIGINAL_CHANGED",
        )

        def pairs(items: Any) -> Any:
            c.require(len({key for key, _ in items}) == len(items), "RA_G1_FIELDS")
            return dict(items)

        record = json.loads(raw, object_pairs_hook=pairs)
        validate(record)
        bounded.canonical_match(record, raw)
        current, after = path.stat(follow_symlinks=False), os.fstat(fd)
        attrs = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_uid",
            "st_gid",
            "st_nlink",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        c.require(
            all(
                getattr(before, key) == getattr(after, key) == getattr(current, key)
                for key in attrs
            )
            and ancestors == a.private_root_identity(path.parent),
            "RA_G1_ORIGINAL_CHANGED",
        )
        check()
        return record
    finally:
        os.close(fd)


def reopen_phase_protocol(
    *,
    binding_sha256: Any,
    selection_sha256: Any,
    phase_id: Any,
    closure: Any,
    opener_return: Any,
    monitor_terminal: Any,
    deadline_ns: Any,
    check: Any,
    clock_ns: Any = time.monotonic_ns,
) -> Any:
    """Reconstruct retained history for the supervisor's bounded tail verifier.

    Inputs must be freshly obtained with read_record and their separately bound
    hashes. This validates an existing opener original; it invokes no opener and
    does not turn future intent or a late local read into actual execution.
    """
    for record, version in (
        (closure, CLOSURE),
        (opener_return, OPENER),
        (monitor_terminal, MONITOR_TERMINAL),
    ):
        validate(record, BOOTSTRAP_PROTOCOL_IDS[version] if closure.get("bootstrap_evidence_sha256") is not None else version)
        c.require(
            record["binding_sha256"] == binding_sha256
            and record["phase_id"] == phase_id,
            "RA_G1_PROTOCOL",
        )
    c.require(
        closure["selection_sha256"]
        == selection_sha256
        == opener_return["selection_sha256"]
        and closure["outcome"] == "PENDING_OPEN"
        and closure["actual_opener_record_sha256"] is None
        and closure["monitor_coverage"] == "COMPLETE_SELECTED_SCOPE",
        "RA_G1_PROTOCOL",
    )
    c.require(
        opener_return["preopening_closure_sha256"] == old.digest(closure)
        and opener_return["validated_monitor_prefix_sha256"]
        == closure["original_observation_prefix_sha256"]
        and opener_return["opener_disposition"]
        in ("DATA_OPENED", "EXPECTED_NEGATIVE_REJECTED"),
        "RA_G1_PROTOCOL",
    )
    c.require(
        monitor_terminal["opener_return_sha256"] == old.digest(opener_return)
        and monitor_terminal["prefix_H0_sha256"]
        == closure["original_observation_prefix_sha256"]
        and monitor_terminal["disposition"] == "CLOSED_SELECTED_SCOPE"
        and monitor_terminal["coverage_end_ns"]
        >= opener_return["actual_opener_return_ns"]
        and monitor_terminal["coverage_start_ns"]
        <= opener_return["actual_opener_start_ns"]
        and monitor_terminal["last_ack_ns"] < deadline_ns
        and opener_return["actual_opener_return_ns"] < deadline_ns,
        "RA_G1_PROTOCOL",
    )
    protocol = PhaseProtocol(
        binding_sha256=binding_sha256,
        selection_sha256=selection_sha256,
        phase_id=phase_id,
        deadline_ns=deadline_ns,
        check=check,
        clock_ns=clock_ns,
    )
    protocol.bootstrap_evidence_sha256 = closure.get("bootstrap_evidence_sha256")
    c.require(all(record.get("bootstrap_evidence_sha256") == protocol.bootstrap_evidence_sha256
                  for record in (closure, opener_return, monitor_terminal)), "RA_G1_BOOTSTRAP_REQUIRED")
    protocol.guard()
    protocol.closure, protocol.opener, protocol.terminal = (
        deepcopy_record(closure),
        deepcopy_record(opener_return),
        deepcopy_record(monitor_terminal),
    )
    protocol.inventory = opener_return["frozen_data_inventory_sha256"]
    protocol.state = "MONITOR_CLOSED"
    return protocol


def monitor_terminal_record(
    monitor: Any, *, opener_return: Any, prefix_H0_sha256: Any
) -> Any:
    """Build only after FINAL was acknowledged and its writer released."""
    bootstrap_sha = getattr(monitor, "bootstrap_evidence_sha256", None)
    validate(opener_return, BOOTSTRAP_PROTOCOL_IDS[OPENER] if bootstrap_sha is not None else OPENER)
    c.require(opener_return.get("bootstrap_evidence_sha256") == bootstrap_sha, "RA_G1_BOOTSTRAP_REQUIRED")
    c.require(
        monitor.writer.released
        and not monitor.writer.poisoned
        and monitor.failure is None,
        "RA_G1_WRITE_UNCERTAIN",
    )
    scope = monitor.coverage
    scope.require_complete(
        opener_return_ns=opener_return["actual_opener_return_ns"],
        last_ack_ns=monitor.writer.ack_ns,
    )
    record = dict(
        schema_version=MONITOR_TERMINAL,
        binding_sha256=monitor.binding,
        phase_id=monitor.phase,
        opener_return_sha256=old.digest(opener_return),
        prefix_H0_sha256=prefix_H0_sha256,
        full_monitor_inventory_sha256=scope.inventory_sha256(),
        final_observation_sha256=scope.head,
        final_observation_ns=scope.last_exit,
        last_ack_ns=monitor.writer.ack_ns,
        last_seq=scope.seq,
        coverage_start_ns=monitor.scope_start,
        coverage_end_ns=scope.last_exit,
        max_gap_ns=scope.max_gap,
        disposition="CLOSED_SELECTED_SCOPE",
        writer_state="HEALTHY_RELEASED",
    )
    validate(record)
    return record


def discover_native_paths(
    root: Any, *, registered_names: Any, check: Any = lambda: None
) -> tuple[Path, ...]:
    """One bounded discovery at native invocation entry, never a recursive poll.

    Raw names live only in this selected private namespace table. Missing known
    main/WAL/journal names stay registered for later stat calls. No public name
    list or claim about deleted-open/unregistered files is produced.
    """
    root = Path(root)
    before = a.private_root_identity(root)
    c.require(
        type(registered_names) is tuple and len(registered_names) <= MAX_NAMES,
        "RA_G1_NATIVE_DISCOVERY",
    )
    names: set[str] = set()

    def add(name: Any) -> None:
        c.require(
            type(name) is str
            and name not in ("", ".", "..")
            and Path(name).name == name
            and len(name.encode("utf-8")) <= 512
            and len(names) + (name not in names) <= MAX_NAMES,
            "RA_G1_NATIVE_DISCOVERY",
        )
        names.add(name)

    for name in registered_names:
        add(name)
    with os.scandir(root) as entries:
        for entry in entries:
            check()
            add(entry.name)
            c.require(entry.is_file(follow_symlinks=False), "RA_G1_NATIVE_DISCOVERY")
    c.require(before == a.private_root_identity(root), "RA_G1_ORIGINAL_CHANGED")
    return tuple(root / name for name in sorted(names))


ORIGINAL_FIELDS = frozenset(
    "schema_version origin kernel_records self_pid cgroup_visible_members filesystem native registered_process_start_ticks proc_records read_calls read_bytes counters".split()
)


def validate_original_observation(
    original: Any, *, observation: Any = None, allow_synthetic: Any = False
) -> Any:
    """Recompute codec values from fresh retained allowlisted originals.

    Count-only encoding first proves the selected 15360-byte maximum; no JSON
    candidate larger than that is created. Arbitrary paths, stack/exception text,
    environment and free-form counter fields are excluded from this record.
    """
    c.require(
        type(original) is dict
        and set(original) == ORIGINAL_FIELDS
        and original["schema_version"] == ORIGINAL_OBSERVATION,
        "RA_G1_FIELDS",
    )
    c.require(
        original["origin"] == "LIVE_KERNEL_OBSERVATION"
        or original["origin"] == "SYNTHETIC_TEST_ONLY"
        and allow_synthetic is True,
        "RA_G1_SYNTHETIC_DENIED",
    )
    counter = bounded.Canonical(MAX_ORIGINAL_BYTES, count_only=True)
    counter.value(original)
    counter.put(b"\n")
    c.require(
        original["cgroup_visible_members"]
        in ("ORIGINAL_RETAINED", "UNAVAILABLE", "UNSELECTED_FOR_FOUR_PROCESS_ROSTER"),
        "RA_G1_FIELDS",
    )
    for key in ("self_pid", "proc_records", "read_calls", "read_bytes"):
        a.shape(original[key], "P" if key == "self_pid" else "U")
    c.require(
        original["proc_records"] <= 12
        and original["read_bytes"] <= 12 * 8192
        and original["read_calls"] <= 12 * 8193,
        "RA_G1_READ_LIMIT",
    )
    a.shape(original["counters"], {key: "U" for key in COUNTERS})
    kernel = original["kernel_records"]
    c.require(type(kernel) is list and len(kernel) <= 12, "RA_G1_FIELDS")
    parsed: dict[int, dict[str, Any]] = {}
    seen: set[tuple[str, int]] = set()
    for row in kernel:
        c.require(
            type(row) is dict
            and set(row) == {"source", "pid", "text", "acquired_mono_ns", "identity"},
            "RA_G1_FIELDS",
        )
        c.require(
            row["source"] in ("CGROUP_PROCS", "PID_CGROUP", "PID_STATUS", "PID_STAT"),
            "RA_G1_FIELDS",
        )
        a.shape(row["pid"], "U")
        a.shape(row["acquired_mono_ns"], "U")
        c.require(
            type(row["identity"]) is list and len(row["identity"]) == 5, "RA_G1_FIELDS"
        )
        for number in row["identity"]:
            a.shape(number, "U")
        c.require(stat.S_ISREG(row["identity"][2]), "RA_G1_FIELDS")
        text = row["text"]
        c.require(
            type(text) is str and text.isascii() and len(text) <= 8192, "RA_G1_FIELDS"
        )
        source_key = row["source"], row["pid"]
        c.require(source_key not in seen, "RA_G1_FIELDS")
        seen.add(source_key)
        if row["source"] == "CGROUP_PROCS":
            c.require(
                row["pid"] == 0 and all(value.isdecimal() for value in text.split()),
                "RA_G1_FIELDS",
            )
            continue
        c.require(row["pid"] > 0, "RA_G1_FIELDS")
        process = parsed.setdefault(row["pid"], {})
        if row["source"] == "PID_CGROUP":
            c.require(text.strip().startswith("0::/"), "RA_G1_FIELDS")
            process["cgroup"] = text.strip()
        elif row["source"] == "PID_STAT":
            suffix = text.rpartition(") ")[2].split()
            c.require(
                text.partition(" (")[0] == str(row["pid"])
                and len(suffix) >= 20
                and suffix[19].isdecimal(),
                "RA_G1_FIELDS",
            )
            process["start_ticks"] = int(suffix[19])
        else:
            values: dict[str, str] = {}
            for line in text.splitlines():
                name, separator, value = line.partition(":")
                if separator and name in ("Pid", "VmRSS", "VmHWM", "Threads", "Uid"):
                    c.require(name not in values, "RA_G1_FIELDS")
                    values[name] = value.strip()
            c.require(
                set(values) == {"Pid", "VmRSS", "VmHWM", "Threads", "Uid"}
                and values["Pid"] == str(row["pid"])
                and values["Threads"].isdecimal(),
                "RA_G1_FIELDS",
            )
            uids = values["Uid"].split()
            c.require(
                len(uids) == 4 and len(set(uids)) == 1 and uids[0].isdecimal(),
                "RA_G1_FIELDS",
            )
            process["uid"] = int(uids[0])
            process["threads"] = int(values["Threads"])
            for source, target in (("VmRSS", "rss"), ("VmHWM", "peak")):
                parts = values[source].split()
                c.require(
                    len(parts) == 2 and parts[0].isdecimal() and parts[1] == "kB",
                    "RA_G1_FIELDS",
                )
                process[target] = old.checked(int(parts[0]) * 1024)
    c.require(
        original["read_bytes"] == sum(len(row["text"]) for row in kernel),
        "RA_G1_ORIGINAL_CHANGED",
    )
    c.require(
        1 <= len(parsed) <= 4
        and original["self_pid"] in parsed
        and all(
            set(row) == {"cgroup", "start_ticks", "uid", "threads", "rss", "peak"}
            for row in parsed.values()
        ),
        "RA_G1_PROCESS_SCOPE",
    )
    c.require(
        len({row["uid"] for row in parsed.values()}) == 1
        and len({row["cgroup"] for row in parsed.values()}) == 1,
        "RA_G1_PROCESS_SCOPE",
    )
    c.require(
        original["registered_process_start_ticks"]
        == [[pid, row["start_ticks"]] for pid, row in parsed.items()],
        "RA_G1_PROCESS_SCOPE",
    )
    filesystem = original["filesystem"]
    a.shape(
        filesystem,
        {
            key: "U"
            for key in ("f_frsize", "f_bavail", "f_favail", "f_blocks", "f_files")
        },
    )
    c.require(
        filesystem["f_frsize"] > 0
        and filesystem["f_bavail"] <= filesystem["f_blocks"]
        and filesystem["f_favail"] <= filesystem["f_files"],
        "RA_G1_REQUIRED_READING",
    )
    native = original["native"]
    c.require(
        type(native) is list and len(native) <= MAX_NAMES, "RA_G1_NATIVE_DISCOVERY"
    )
    allocated, linked = 0, 0
    for ordinal, row in enumerate(native, 1):
        c.require(
            type(row) is dict and row.get("role_id") == ordinal,
            "RA_G1_NATIVE_DISCOVERY",
        )
        if row.get("status") == "ABSENT":
            c.require(set(row) == {"role_id", "status"}, "RA_G1_NATIVE_DISCOVERY")
        else:
            a.shape(
                row,
                {
                    "role_id": "P",
                    "status": "=VISIBLE_LINKED",
                    "device": "U",
                    "inode": "U",
                    "blocks_512_bytes": "U",
                    "logical_bytes": "U",
                },
            )
            allocated = old.checked(allocated + row["blocks_512_bytes"] * 512)
            linked += 1
    if observation is not None:
        validate(observation, OBSERVATION)
        c.require(
            old.digest(original) == observation["visible_identity_inventory_sha256"]
            and original["counters"] == observation["counters"],
            "RA_G1_ORIGINAL_CHANGED",
        )
        observed_values: dict[str, Any] = dict(
            self_rss_peak_bytes=parsed[original["self_pid"]]["peak"],
            registered_visible_rss_bytes=old.checked(
                sum(row["rss"] for row in parsed.values())
            ),
            visible_native_threads=old.checked(
                sum(row["threads"] for row in parsed.values())
            ),
            visible_processes=len(parsed),
            shared_bavail_bytes=old.checked(
                filesystem["f_frsize"] * filesystem["f_bavail"]
            ),
            shared_favail=filesystem["f_favail"],
            visible_native_file_bytes=allocated,
        )
        c.require(
            all(
                observation["readings"][key]["value"] == value
                for key, value in observed_values.items()
            )
            and observation["native_visibility"]["registered_paths_checked"]
            == len(native)
            and observation["native_visibility"]["visible_linked_files"] == linked
            and all(
                observation["enter_mono_ns"]
                <= row["acquired_mono_ns"]
                <= observation["exit_mono_ns"]
                for row in kernel
            ),
            "RA_G1_ORIGINAL_CHANGED",
        )
    return original


def export_original_observation(
    original: Any, *, allow_synthetic: Any = False
) -> bytes:
    validate_original_observation(original, allow_synthetic=allow_synthetic)
    return bytes(bounded.canonical(original, MAX_ORIGINAL_BYTES))


def read_original_observation(
    path: Any,
    *,
    expected_sha256: Any,
    check: Any = lambda: None,
    charge_read: Any = lambda calls, size: None,
    test_only: Any = False,
) -> Any:
    """Fresh separately charged 15360-byte original; codec export is unselected."""
    import json

    path = Path(path)
    ancestors = a.private_root_identity(path.parent)
    check()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        c.require(
            stat.S_ISREG(before.st_mode)
            and before.st_uid == os.geteuid()
            and before.st_nlink == 1
            and stat.S_IMODE(before.st_mode) == 0o600
            and 0 < before.st_size <= MAX_ORIGINAL_BYTES,
            "RA_G1_ORIGINAL_CHANGED",
        )
        raw = charged_read(fd, MAX_ORIGINAL_BYTES, charge_read)
        c.require(
            len(raw) == before.st_size
            and not charged_read(fd, 1, charge_read)
            and hashlib.sha256(raw).hexdigest() == expected_sha256,
            "RA_G1_ORIGINAL_CHANGED",
        )

        def pairs(items: Any) -> Any:
            c.require(len({key for key, _ in items}) == len(items), "RA_G1_FIELDS")
            return dict(items)

        original = json.loads(raw, object_pairs_hook=pairs)
        validate_original_observation(original, allow_synthetic=test_only)
        bounded.canonical_match(original, raw)
        after, current = os.fstat(fd), path.stat(follow_symlinks=False)
        attrs = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_uid",
            "st_gid",
            "st_nlink",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        c.require(
            all(
                getattr(before, key) == getattr(after, key) == getattr(current, key)
                for key in attrs
            )
            and ancestors == a.private_root_identity(path.parent),
            "RA_G1_ORIGINAL_CHANGED",
        )
        check()
        return original
    finally:
        os.close(fd)


# Explicit additional families; old schema objects and expected-version readers
# are untouched. Common scalar semantics are reused only after new closed shape
# and exact family checks, never by relabelling a retained historical original.
BOOTSTRAP_PROTOCOL_IDS = {name: name.replace("_ra_g1_v1", "_bootstrap30_ra_g1_v1")
    for name in (CLOSURE, OPENER, MONITOR_TERMINAL, PHASE_TERMINAL,
                 "stage12_resource_monitor_worker_validation_ra_g1_v1")}


def register_bootstrap_protocol_schema(base: Any, spec: Any) -> None:
    SCHEMAS[BOOTSTRAP_PROTOCOL_IDS[base]] = {**spec,
        "schema_version": "=" + BOOTSTRAP_PROTOCOL_IDS[base], "bootstrap_evidence_sha256": "D"}


for _base in (CLOSURE, OPENER, MONITOR_TERMINAL, PHASE_TERMINAL):
    register_bootstrap_protocol_schema(_base, SCHEMAS[_base])
SCHEMAS[a.BOOTSTRAP_EVIDENCE] = a.BOOTSTRAP_EVIDENCE_SCHEMA
_strict_validate_original_family = validate


def validate(record: Any, expected: Any = None) -> Any:
    version = record.get("schema_version") if type(record) is dict else None
    reverse = {value:key for key,value in BOOTSTRAP_PROTOCOL_IDS.items()}
    if version == a.BOOTSTRAP_EVIDENCE:
        c.require(expected is None or expected == version, "RA_G1_FIELDS")
        _shape(record, SCHEMAS[version])
        counter = bounded.Canonical(MAX_RECORD_BYTES, count_only=True)
        counter.value(record)
        counter.put(b"\n")
        return record
    if version not in reverse:
        return _strict_validate_original_family(record, expected)
    c.require(expected is None or expected == version, "RA_G1_FIELDS")
    _shape(record, SCHEMAS[version])
    counter = bounded.Canonical(MAX_RECORD_BYTES, count_only=True)
    counter.value(record)
    counter.put(b"\n")
    fields = {key:value for key,value in record.items() if key != "bootstrap_evidence_sha256"}
    fields["schema_version"] = reverse[version]
    _strict_validate_original_family(fields, reverse[version])
    return record


def bootstrap_protocol_record(record: Any, evidence_sha256: Any) -> Any:
    if evidence_sha256 is None:
        return record
    a.shape(evidence_sha256, "D")
    return {**record, "schema_version": BOOTSTRAP_PROTOCOL_IDS[record["schema_version"]],
            "bootstrap_evidence_sha256": evidence_sha256}
