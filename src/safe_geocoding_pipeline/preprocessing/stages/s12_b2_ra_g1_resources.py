"""RA-G1 checked logical retention and explicitly unproven native use."""

from __future__ import annotations
import hashlib
import json
import os
import stat
from pathlib import Path
from collections.abc import Sequence
from . import s12_storage as io

from . import s12_b2_contract as b
from . import s12_b2_resources as old

MAX_COMMANDS = 643
COMMAND_PHASES, MANDATORY_COMMAND_PHASES = (
    old.COMMAND_PHASES,
    old.MANDATORY_COMMAND_PHASES,
)
COUNTS = dict(
    old.COUNTS, NATIVE_AUXILIARY="native_invocations", MONITOR_EVIDENCE="monitor_rows"
)
add, mul = old.add, old.mul
generation_inventory = old.generation_inventory


def workload_binding(plan):
    """Retain every science/work field; only existing derived links are excluded."""
    value = dict(plan)
    for key in (
        "operations_profile_sha256",
        "resource_retention_model_sha256",
        "resource_workload_sha256",
    ):
        value.pop(key, None)
    value["schema_version"] = "stage12_development_workload_plan_b2_ap_ra_g1_v1"
    return b.digest(value)


def command_scope_record(config, *, plan_binding=None):
    # Start with the reviewed RS1 projection, then replace the deleted physical
    # fields by the successor's exact selected logical/observation fields.
    value = old.command_scope_record(config, plan_binding=plan_binding)
    value["schema_version"] = "stage12_resource_command_scope_b2_ra_g1_v1"
    runtime = value["runtime"]
    for key in (
        "phase_memory_bytes",
        "phase_disk_capacity_bytes",
        "phase_generation_bound_bytes",
    ):
        runtime.pop(key)
    for key in (
        "phase_monitor_selection_sha256",
        "phase_capacity_observation_sha256",
        "phase_logical_write_ceiling_bytes",
    ):
        runtime[key] = config["runtime"][key]
    value["configuration"]["schema_version"] = config.get("schema_version")
    value["configuration"]["resource_execution"] = config.get("resource_execution")
    value["configuration"]["resource_paths"] = config.get("resource_paths")
    return value


def validate_model(model):
    from . import s12_b2_ra_g1_graph as graph

    return graph.validate_model(model)


def validate_plan_model(model, plan):
    from . import s12_b2_ra_g1_graph as graph

    return graph.validate_plan_model(model, plan)


def member_workload(plan):
    value = old.member_workload(plan)
    value["plan_binding_sha256"] = workload_binding(plan)
    return value


# This narrow codec never changes s12_storage or historical metadata readers.
# FINISH path arrays are freshly streamed, not admitted as arbitrary big JSON.


class HistoryLease:
    """Compose with the existing process-wide checked 8MiB history backing."""

    def __init__(self, size):
        b.uint(size, True)
        self.size = size
        self.active = False

    def __enter__(self):
        from . import s12_public_history as history

        with history._backing_lock:
            b.require(
                self.size <= history.MAX_BACKING - history._backing,
                "S12_PUBLIC_HISTORY_LIMIT",
            )
            history._backing += self.size
            self.history = history
            self.active = True
        return self

    def close(self):
        if getattr(self, "active", False):
            history = self.history
            with history._backing_lock:
                history._backing -= self.size
                self.active = False

    def __exit__(self, *args):
        self.close()

    def __del__(self):
        self.close()


def _history_codec(function):
    from functools import wraps

    @wraps(function)
    def bounded(*args, **kwargs):
        with HistoryLease(65536):
            return function(*args, **kwargs)

    return bounded


MAX_FINISH_BYTES = 16 * 2**20
MAX_PATH_BYTES = 4096


def _signature(info):
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_uid,
        info.st_gid,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _private_file(path):
    io.private_directory(path.parent)
    info = path.stat(follow_symlinks=False)
    b.require(
        stat.S_ISREG(info.st_mode)
        and info.st_nlink == 1
        and info.st_uid == os.getuid()
        and info.st_mode & 0o077 == 0,
        "B2_RA_FINISH_PATH",
    )
    return _signature(info)


class _Tokens:
    """8192-byte read backing and one bounded scalar/path token."""

    def __init__(self, stream, check):
        self.stream, self.check = stream, check
        self.buffer, self.at, self.offset = b"", 0, stream.tell()
        self.hash = hashlib.sha256()

    def peek(self):
        if self.at == len(self.buffer):
            self.check()
            charge_original_read(self.check, 8192)
            self.buffer = self.stream.read(8192)
            self.hash.update(self.buffer)
            self.at = 0
        return self.buffer[self.at : self.at + 1]

    def take(self):
        value = self.peek()
        b.require(bool(value), "B2_RA_FINISH_TRUNCATED")
        self.at += 1
        self.offset += 1
        return value

    def expect(self, token):
        for value in token:
            b.require(self.take() == bytes([value]), "B2_RA_FINISH_ENCODING")

    def scalar(self):
        token = bytearray()
        quoted = self.peek() == b'"'
        if quoted:
            token.extend(self.take())
            escaped = False
            while True:
                byte = self.take()
                token.extend(byte)
                b.require(
                    len(token) <= 6 * MAX_PATH_BYTES + 128, "B2_RA_FINISH_TOKEN_BOUND"
                )
                if not escaped and byte == b'"':
                    break
                if byte == b"\\" and not escaped:
                    escaped = True
                else:
                    escaped = False
        else:
            while self.peek() not in (b",", b"}", b"]", b"", b"\n"):
                token.extend(self.take())
                b.require(len(token) <= 128, "B2_RA_FINISH_TOKEN_BOUND")
        try:
            value = json.loads(token)
        except (ValueError, UnicodeError):
            b.require(False, "B2_RA_FINISH_ENCODING")
        if type(value) is str:
            # Exact ensure_ascii canonical comparison with <=12-byte fragments;
            # no second full escaped path or whole-row reencode is created.
            position = 1
            for char in value:
                code = ord(char)
                short = {
                    8: b"\\b",
                    9: b"\\t",
                    10: b"\\n",
                    12: b"\\f",
                    13: b"\\r",
                    34: b'\\"',
                    92: b"\\\\",
                }
                if code in short:
                    fragment = short[code]
                elif code < 32 or 127 <= code <= 65535:
                    fragment = ("\\u%04x" % code).encode("ascii")
                elif code > 65535:
                    adjusted = code - 65536
                    fragment = (
                        "\\u%04x\\u%04x"
                        % (0xD800 + (adjusted >> 10), 0xDC00 + (adjusted & 1023))
                    ).encode("ascii")
                else:
                    fragment = bytes([code])
                b.require(
                    token[position : position + len(fragment)] == fragment,
                    "B2_RA_FINISH_ENCODING",
                )
                position += len(fragment)
            b.require(position == len(token) - 1, "B2_RA_FINISH_ENCODING")
        else:
            b.require(b.canonical(value)[:-1] == token, "B2_RA_FINISH_ENCODING")
        return value


def _path(value):
    b.require(
        type(value) is str
        and len(value) <= MAX_PATH_BYTES
        and len(value.encode("utf8")) <= MAX_PATH_BYTES,
        "B2_RA_FINISH_PATH_BOUND",
    )
    path = Path(value)
    b.require(
        path.is_absolute() and ".." not in path.parts and str(path) == value,
        "B2_RA_FINISH_PATH",
    )


def _array_item(tokens, generated):
    if not generated:
        value = tokens.scalar()
        _path(value)
        return value
    tokens.expect(b'{"path":')
    path = tokens.scalar()
    _path(path)
    tokens.expect(b',"sha256":')
    digest = tokens.scalar()
    b.validate_type(digest, "D")
    tokens.expect(b"}")
    return {"path": path, "sha256": digest}


def charge_original_read(check, size):
    """Charge bounded original I/O through the actual command authority."""
    owner = getattr(check, "__self__", None)
    charge = getattr(owner, "charge_ra_original_read", None)
    if not callable(charge):
        charge = getattr(getattr(owner, "port", None), "charge_ra_original_read", None)
    if callable(charge):
        charge(1, size)


def _original_path_chars(path, offset, generated, check):
    """Compare a prior original token one Unicode scalar at a time."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        stream.seek(offset + (8 if generated else 0))
        tokens = _Tokens(stream, check)
        b.require(tokens.take() == b'"', "B2_RA_FINISH_ENCODING")
        while True:
            char = tokens.take()
            b.require(bool(char), "B2_RA_FINISH_TRUNCATED")
            if char == b'"':
                return
            if char != b"\\":
                b.require(char[0] < 128, "B2_RA_FINISH_ENCODING")
                yield chr(char[0])
                continue
            escape = tokens.take()
            if escape == b"u":
                code = int(b"".join(tokens.take() for _ in range(4)), 16)
                if 0xD800 <= code <= 0xDBFF:
                    tokens.expect(b"\\u")
                    low = int(b"".join(tokens.take() for _ in range(4)), 16)
                    b.require(0xDC00 <= low <= 0xDFFF, "B2_RA_FINISH_ENCODING")
                    code = 0x10000 + ((code - 0xD800) << 10) + low - 0xDC00
                yield chr(code)
            else:
                values = {
                    b'"': '"',
                    b"\\": "\\",
                    b"b": "\b",
                    b"f": "\f",
                    b"n": "\n",
                    b"r": "\r",
                    b"t": "\t",
                }
                b.require(escape in values, "B2_RA_FINISH_ENCODING")
                yield values[escape]


def _original_path_before(path, offset, current, generated, check):
    previous = _original_path_chars(path, offset, generated, check)
    try:
        for index, char in enumerate(previous):
            if index >= len(current):
                return False
            if char != current[index]:
                return char < current[index]
        return index + 1 < len(current)
    finally:
        previous.close()


class PathArray(Sequence):
    """An original path array; iteration materializes one path, then discards it."""

    def __init__(self, path, start, count, generated, signature, check):
        self.path, self.start, self.count = path, start, count
        self.generated, self.signature, self.check = generated, signature, check

    def __len__(self):
        return self.count

    def __iter__(self):
        with HistoryLease(65536):
            yield from self._items()

    def _items(self):
        b.require(_private_file(self.path) == self.signature, "B2_RA_FINISH_CHANGED")
        fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            b.require(
                _signature(os.fstat(stream.fileno())) == self.signature,
                "B2_RA_FINISH_CHANGED",
            )
            stream.seek(self.start)
            tokens = _Tokens(stream, self.check)
            tokens.expect(b"[")
            for index in range(self.count):
                if index:
                    tokens.expect(b",")
                yield _array_item(tokens, self.generated)
            tokens.expect(b"]")
            b.require(
                _signature(os.fstat(stream.fileno())) == self.signature,
                "B2_RA_FINISH_CHANGED",
            )
        b.require(_private_file(self.path) == self.signature, "B2_RA_FINISH_CHANGED")

    def __getitem__(self, index):
        b.require(type(index) is int and 0 <= index < self.count, "B2_RA_FINISH_INDEX")
        for current, value in enumerate(self):
            if current == index:
                b.require(
                    _private_file(self.path) == self.signature, "B2_RA_FINISH_CHANGED"
                )
                return value
        raise IndexError(index)


class GeneratedRecords(Sequence):
    """512 fixed digest slots; construct one shared-store path per iteration."""

    def __init__(self, root):
        self.lease = HistoryLease(32768)
        self.lease.__enter__()
        self.root = Path(root)
        self.backing = bytearray(512 * 32)
        self.count = 0

    def __len__(self):
        return self.count

    def reserve(self, digest, maximum):
        raw = bytes.fromhex(digest)
        b.require(
            len(raw) == 32 and self.count < min(512, maximum),
            "B2_GRAPH_GENERATED_RECORD_BOUND",
        )
        index = 0
        while index < self.count:
            current = self.backing[index * 32 : (index + 1) * 32]
            b.require(current != raw, "B2_GRAPH_GENERATED_RECORD_BOUND")
            if current > raw:
                break
            index += 1
        # Fixed backing and one fixed32-byte move; no population path list.
        for position in range(self.count, index, -1):
            self.backing[position * 32 : (position + 1) * 32] = self.backing[
                (position - 1) * 32 : position * 32
            ]
        self.backing[index * 32 : (index + 1) * 32] = raw
        self.count += 1

    def __getitem__(self, index):
        b.require(type(index) is int and 0 <= index < self.count, "B2_RA_FINISH_INDEX")
        digest = self.backing[index * 32 : (index + 1) * 32].hex()
        return {"path": str(self.root / (digest + ".json")), "sha256": digest}

    def __iter__(self):
        for index in range(self.count):
            yield self[index]

    def close(self):
        if hasattr(self, "lease"):
            self.lease.close()

    def __del__(self):
        self.close()


class RootStrings(Sequence):
    """At most16 selected root objects; serialize a single path at a time."""

    def __init__(self, roots):
        self.lease = HistoryLease(131072)
        self.lease.__enter__()
        b.require(type(roots) is list and 0 < len(roots) <= 16, "B2_RA_FINISH_ROOTS")
        self.roots = sorted(roots)

    def __len__(self):
        return len(self.roots)

    def __getitem__(self, index):
        return str(self.roots[index])

    def __iter__(self):
        for index in range(len(self)):
            yield self[index]

    def __del__(self):
        if hasattr(self, "lease"):
            self.lease.close()


class StreamRecord(dict):
    """Closed scalar header plus bounded original array views, never whole bytes."""

    pass


@_history_codec
def read_finish(path, *, check=lambda: None):
    path = Path(path)
    signature = _private_file(path)
    b.require(signature[6] <= MAX_FINISH_BYTES, "B2_RA_FINISH_SIZE")
    fields = {
        "schema_version",
        "envelope_sha256",
        "slot_id",
        "previous_ledger_sha256",
        "slot_binding_sha256",
        "disposition",
        "observed_bytes",
        "observed_inodes",
        "inventory_sha256",
        "inventory_roots",
        "inventory_max_entries",
        "generated_records",
        "completed_utc",
    }
    row = StreamRecord()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        b.require(
            _signature(os.fstat(stream.fileno())) == signature, "B2_RA_FINISH_CHANGED"
        )
        tokens = _Tokens(stream, check)
        tokens.expect(b"{")
        for ordinal, expected in enumerate(sorted(fields)):
            if ordinal:
                tokens.expect(b",")
            b.require(tokens.scalar() == expected, "B2_RA_FINISH_FIELDS")
            tokens.expect(b":")
            if expected in ("generated_records", "inventory_roots"):
                generated = expected == "generated_records"
                start, count, previous_offset = tokens.offset, 0, None
                tokens.expect(b"[")
                while tokens.peek() != b"]":
                    if count:
                        tokens.expect(b",")
                    item_offset = tokens.offset
                    value = _array_item(tokens, generated)
                    path_value = value["path"] if generated else value
                    b.require(
                        previous_offset is None
                        or _original_path_before(
                            path, previous_offset, path_value, generated, check
                        ),
                        "B2_RA_FINISH_ORDER",
                    )
                    previous_offset = item_offset
                    del value, path_value
                    count += 1
                    b.require(
                        count <= (512 if generated else 16), "B2_RA_FINISH_PATH_COUNT"
                    )
                tokens.expect(b"]")
                b.require(generated or count > 0, "B2_RA_FINISH_ROOTS")
                row[expected] = PathArray(
                    path, start, count, generated, signature, check
                )
            else:
                row[expected] = tokens.scalar()
        tokens.expect(b"}\n")
        b.require(tokens.peek() == b"", "B2_RA_FINISH_TRAILING")
        b.require(
            _signature(os.fstat(stream.fileno())) == signature, "B2_RA_FINISH_CHANGED"
        )
        row.original_sha256 = tokens.hash.hexdigest()
    b.require(_private_file(path) == signature, "B2_RA_FINISH_CHANGED")
    row.original_size, row.original_signature = signature[6], signature
    # Complete canonical checking is structural above, including scalar reencode;
    # independently hash the exact complete original, including all escaped paths.
    b.require(digest_stream(row) == row.original_sha256, "B2_RA_FINISH_ENCODING")
    return row


def canonical_parts(value):
    if isinstance(value, dict):
        yield b"{"
        for index, key in enumerate(sorted(value)):
            if index:
                yield b","
            yield b.canonical(key)[:-1]
            yield b":"
            yield from canonical_parts(value[key])
        yield b"}"
    elif isinstance(value, (list, tuple, PathArray, GeneratedRecords, RootStrings)):
        yield b"["
        for index, item in enumerate(value):
            if index:
                yield b","
            yield from canonical_parts(item)
            del item
        yield b"]"
    else:
        yield b.canonical(value)[:-1]


def encoded_parts(value):
    yield from canonical_parts(value)
    yield b"\n"


@_history_codec
def digest_stream(value):
    h = hashlib.sha256()
    for block in encoded_parts(value):
        h.update(block)
    return h.hexdigest()


@_history_codec
def write_finish(path, row, *, check=lambda: None):
    """Preflight the complete encoding before exclusive write; keep failed bytes."""
    from . import s12_b2_ra_g1_graph as graph

    b.require(
        isinstance(row, dict)
        and isinstance(
            row.get("generated_records"), (list, PathArray, GeneratedRecords)
        )
        and len(row["generated_records"]) <= 512
        and isinstance(row.get("inventory_roots"), (list, PathArray, RootStrings))
        and 0 < len(row["inventory_roots"]) <= 16,
        "B2_RA_FINISH_PATH_COUNT",
    )
    for root_path in row["inventory_roots"]:
        _path(root_path)
    previous_digest = None
    for index, item in enumerate(row["generated_records"]):
        b.require(
            type(item) is dict and set(item) == {"path", "sha256"},
            "B2_RA_FINISH_FIELDS",
        )
        _path(item["path"])
        if isinstance(row["generated_records"], GeneratedRecords):
            b.require(
                previous_digest is None or previous_digest < item["sha256"],
                "B2_RA_FINISH_ORDER",
            )
            previous_digest = item["sha256"]
        elif isinstance(row["generated_records"], list):
            b.require(
                index == 0
                or row["generated_records"][index - 1]["path"] < item["path"],
                "B2_RA_FINISH_ORDER",
            )
        del item
    graph.shape(row, graph.FINISH_SCHEMA)
    size = 0
    for block in encoded_parts(row):
        check()
        size = add(size, len(block))
        b.require(size <= MAX_FINISH_BYTES, "B2_RA_FINISH_SIZE")
    controls = io.current_allocation_controls()
    if controls is not None:
        controls.claim("EXCLUSIVE_FILE", size)
    io.private_directory(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        for block in encoded_parts(row):
            check()
            view = memoryview(block)
            while view:
                check()
                n = os.write(fd, view)
                b.require(n > 0, "B2_RA_FINISH_WRITE")
                view = view[n:]
        os.fsync(fd)
    finally:
        os.close(fd)
    io.fsync_directory(path.parent)
    result = read_finish(path, check=check)
    b.require(result.original_sha256 == digest_stream(row), "B2_RA_FINISH_CHANGED")
    return result.original_sha256


def configuration_scope(config, *, plan=None):
    selected = command_scope_record(
        config,
        plan_binding=workload_binding(plan)
        if plan is not None and config["runtime"]["campaign"] is not None
        else None,
    )
    paths = config.get("command_paths")
    b.require(
        type(paths) is dict and set(paths) == {"output_path", "scratch_path"},
        "B2_RA_CONFIGURATION_SCOPE",
    )
    selected["command_paths"] = dict(paths)
    selected["member_plan_binding_sha256"] = (
        None if plan is None else workload_binding(plan)
    )
    if "bootstrap_work_file" in config:
        selected["bootstrap_work_file"] = config["bootstrap_work_file"]
    return b.digest(selected)


def prepare_runtime(port):
    """Read genuine successor control metadata; create no service authority."""
    from . import s12_ra_g1_assurance as assurance
    from . import s12_b2_ra_g1_contract as contract

    runtime = port.settings
    spec = runtime.get("campaign") or port.config.get("bootstrap")
    profile = plan = start = None
    if port.local_only:
        authority = io.metadata(
            port.records.raw(runtime["local_preparation_authority_sha256"])
        )
        digest = authority["resource_assurance_binding_sha256"]
    else:
        b.require(type(spec) is dict, "B2_RA_ASSURANCE_REQUIRED")
        profile, plan = port._profile_plan(spec)
        b.require(profile["schema_version"] == contract.PROFILE, "B2_RA_MIXED_METHOD")
        digest = profile["sampling_runtime_bound_sha256"]
        start = contract.parse(port.records.raw(spec["start_sha256"]), contract.START)
    binding_raw = port.records.raw(digest)
    path = Path(port.config["resource_paths"]["bindings_path"])
    port.charge_ra_original_read(1, path.stat(follow_symlinks=False).st_size + 1)
    b.require(io.read(path, limit=65536) == binding_raw, "B2_RA_BINDING_PATH_CHANGED")
    binding = io.metadata(binding_raw)
    assurance.shape(binding, assurance.SCHEMA)
    expected_scope = (
        "DEVELOPMENT_LOCAL_PREPARATION" if port.local_only else "DEVELOPMENT_ONLY"
    )
    b.require(
        binding["scope"] == expected_scope
        and binding["source_inventory_sha256"] == b.digest(runtime["source_files"]),
        "B2_RA_ASSURANCE_SCOPE",
    )
    port.ra_binding_sha256, port.ra_binding = digest, binding
    port.charge_ra_original_read(0, 0)
    port.authority.configuration_scope_sha256 = configuration_scope(
        port.config, plan=plan
    )
    port.authority.test_only = port.test_only
    if port.local_only:
        from . import s12_wf_ap2_scratch as scratch

        allocations = binding["logical_allocations"]
        b.require(
            [row["name"] for row in allocations] == list(assurance.ARENAS),
            "B2_RA_LOGICAL_ALLOCATION",
        )
        amounts = {row["name"]: row["bytes"] for row in allocations}
        b.require(
            add(*amounts.values()) == binding["total_logical_bytes"] <= 16777216
            and amounts["SAMPLE_SLOTS"] >= 65536
            and amounts["HISTORY_PAGES"] == 8388608
            and amounts["TELEMETRY_RING"] >= 2097152
            and amounts["SERIALIZATION_SCRATCH"] == binding["logical_scratch_bytes"]
            and sum(scratch.RA_G1_CAPS.values())
            <= binding["logical_scratch_bytes"]
            <= 65536
            and amounts["TRACE_METADATA"] >= 32768
            and amounts["CONTROLLER_METADATA"] >= 16384
            and amounts["OTHER_LOGICAL"] >= 393216,
            "B2_RA_LOGICAL_ALLOCATION",
        )
        port.authority._sampling_bound_record_sha256 = digest
    if profile is not None:
        assurance.validate_record(
            binding,
            profile,
            start,
            contract=contract,
            configuration_scope_sha256=port.authority.configuration_scope_sha256,
        )
    else:
        b.require(
            binding["configuration_scope_sha256"]
            == port.authority.configuration_scope_sha256,
            "B2_RA_CONFIGURATION_SCOPE",
        )
    selected = assurance.validate_selection(
        io.metadata(port.records.raw(binding["selection_sha256"]))
    )
    b.require(
        binding["selection_sha256"] == runtime["phase_monitor_selection_sha256"]
        and b.digest(selected) == binding["selection_sha256"]
        and selected["limits"]["processing_ms"] <= runtime["phase_duration_ms"]
        and selected["limits"]["logical_write_bytes"]
        <= runtime["phase_logical_write_ceiling_bytes"],
        "B2_RA_SELECTION_BINDING",
    )
    port.ra_selection = selected
    port.ra_monitor_write_bytes = port.ra_monitor_creations = 0
    port.ra_monitor_rows_prior = 0
    if port.phase in ("run-campaign", "run-direct-n"):
        limits = selected["limits"]
        b.require(
            limits["processing_ms"] <= 2500000
            and limits["scheduler_s"] <= 2740
            and limits["monitor_rows"] <= 5010
            and limits["monitor_bytes"] <= 82313216
            and limits["monitor_creations"] <= 10048
            and all(
                stage["deadline_ms"] <= 2500000 and stage["attempts"] <= 1840
                for stage in limits["stages"]
            ),
            "B2_RA_NETWORK_SELECTION_BOUND",
        )
    initial = port.authority.capacity_observation(binding)
    b.require(
        b.digest(initial) == runtime["phase_capacity_observation_sha256"],
        "B2_RA_CAPACITY_BINDING",
    )
    port.ra_initial_capacity = initial
    port.ra_runtime_subject = (profile, plan, start)
    start_protected_setup(port)
    verify_prepared_runtime(port)


def verify_prepared_runtime(port):
    from . import s12_ra_g1_assurance as assurance

    profile, plan, start = port.ra_runtime_subject
    binding = port.ra_binding
    assurance.verify_runtime(
        binding,
        port.authority,
        {"configuration_scope_sha256": authority_scope(port.config)}
        if profile is None
        else {"profile": profile, "plan": plan, "start": start},
    )
    if port.local_only:
        verify_local_assurance(port, verify_inventory=True)
    port.ra_prior_root_attempts = prior_root_attempts(port)
    b.require(
        port.ra_prior_root_attempts == port.ra_setup_counter_prefix,
        "B2_RA_SETUP_COUNTER_PREFIX_CHANGED",
    )


SETUP_COUNTER_PREFIX = "stage12_resource_setup_counter_prefix_b2_ra_g1_v1"
SETUP_COUNTER_PREFIX_SCHEMA = dict(
    schema_version="=" + SETUP_COUNTER_PREFIX,
    model_sha256="D",
    prior_slot_id="P",
    source_success_sha256="D",
    counter_snapshot_sha256="D",
    root_attempts="U",
)


def monitor_charge(port, size, creations):
    port.check_resource_deadline()
    b.uint(size)
    b.uint(creations)
    next_bytes = add(port.ra_monitor_write_bytes, size)
    next_creations = add(port.ra_monitor_creations, creations)
    b.require(
        next_bytes <= port.ra_selection["limits"]["monitor_bytes"]
        and next_creations <= port.ra_selection["limits"]["monitor_creations"],
        "B2_RA_MONITOR_PRECHARGE",
    )
    port.ra_monitor_write_bytes, port.ra_monitor_creations = next_bytes, next_creations
    current_capacity(port, next_write_bytes=size, next_creations=creations)


def start_protected_setup(port):
    """Start the resource-only role before source/native/history verification."""
    from . import s12_ra_g1_execution as execution
    from . import s12_ra_g1_assurance as assurance
    from . import s12_ra_g1_monitor as monitor

    pointer = port.resource_binding
    prefix = port.config["resource_paths"]["setup_counter_prefix_sha256"]
    if pointer["command_id"] == 1:
        b.require(prefix is None, "B2_RA_SETUP_COUNTER_PREFIX_REQUIRED")
        port.ra_setup_counter_prefix = 0
    else:
        b.validate_type(prefix, "D")
        value = io.metadata(port.records.raw(prefix))
        assurance.shape(value, SETUP_COUNTER_PREFIX_SCHEMA)
        prior = io.metadata(
            io.read(
                completion_root(port.settings["output_parent"], pointer["model_sha256"])
                / f"{pointer['command_id'] - 1:06d}.success.json",
                limit=8192,
            )
        )
        b.require(
            value["model_sha256"] == pointer["model_sha256"]
            and value["prior_slot_id"] == pointer["command_id"] - 1
            and value["source_success_sha256"] == b.digest(prior),
            "B2_RA_SETUP_COUNTER_PREFIX_REQUIRED",
        )
        terminal = io.metadata(io.read(Path(prior["phase_terminal_path"]), limit=8192))
        monitor.validate(terminal, monitor.PHASE_TERMINAL)
        counters = io.metadata(port.records.raw(value["counter_snapshot_sha256"]))
        assurance.shape(counters, {name: "U" for name in monitor.COUNTERS})
        b.require(
            b.digest(terminal) == prior["phase_terminal_sha256"]
            and b.digest(counters) == terminal["root_counter_watermarks_sha256"]
            and counters["root_attempts"] == value["root_attempts"],
            "B2_RA_SETUP_COUNTER_PREFIX_REQUIRED",
        )
        port.authority.require(
            "resource_setup_counter_prefix",
            prefix,
            {"configuration_scope_sha256": authority_scope(port.config)},
        )
        port.ra_setup_counter_prefix = value["root_attempts"]
    stages = port.ra_selection["limits"]["stages"]
    b.require(
        len(stages) == 3
        and [row["phase"] for row in stages] == [1, 2, 3]
        and stages[0]["attempts"] == stages[0]["events"] == 0
        and stages[2]["attempts"] == stages[2]["events"] == 0,
        "B2_RA_PROTECTED_SCOPE_ROSTER",
    )
    port.ra_setup_running = True
    port.ra_phase_charge = lambda size, creates: monitor_charge(port, size, creates)
    root = Path(port.config["resource_paths"]["resource_evidence_root"])
    setup_root = root.with_name(root.name + "_setup")
    deadline = min(port.deadline, port.started_ns + stages[0]["deadline_ms"] * 1000000)
    port.ra_active_scope_deadline = deadline
    factory = (
        port._test.get("resource_setup_factory")
        if port.test_only and port._test is not None
        else None
    )
    if factory is not None:
        b.require(
            callable(factory) and port.population_scope == b.SYNTHETIC,
            "B2_RA_TEST_CONTEXT",
        )
        setup = factory(port, port.ra_phase_charge, setup_root, deadline)
        b.require(
            isinstance(setup, execution.AdministrativePhaseSession) and setup.test_only,
            "B2_RA_TEST_CONTEXT",
        )
        setup.start()
    else:
        context = execution.read_supervisor_context(
            port.config["resource_execution"],
            check=port.check_resource_deadline,
            read_charge=port.charge_ra_original_read,
        )
        actual = execution.validate_current_supervisor(
            context,
            binding=port.ra_binding,
            selection=port.ra_selection,
            evidence_root=root,
            check=port.check_resource_deadline,
            read_charge=port.charge_ra_original_read,
            clock_ns=port.clock.now_ns,
        )
        process, _ = execution._process_identity(
            os.getpid(),
            check=port.check_resource_deadline,
            read_charge=port.charge_ra_original_read,
        )
        binding = dict(
            schema_version=execution.ADMIN_BINDING,
            scope=port.ra_binding["scope"],
            method=assurance.METHOD,
            role="PROTECTED_SETUP",
            phase_id=1,
            source_git_sha=port.ra_binding["source_git_sha"],
            selection_sha256=port.ra_binding["selection_sha256"],
            adoption_sha256=port.ra_binding["adoption_sha256"],
            supervisor_context_sha256=port.config["resource_execution"][
                "supervisor_context_sha256"
            ],
            risk_inventory_sha256=port.ra_binding["risk_inventory_sha256"],
            process_pid=process["pid"],
            process_start_ticks=process["start_ticks"],
            process_uid=process["uid"],
            scope_start_mono_ns=port.started_ns,
            deadline_mono_ns=deadline,
            service_authority="DENIED",
            protected_input_authority="DENIED",
            ap_dispatch_authority="DENIED",
        )
        setup = execution.start_administrative_session(
            binding=binding,
            selection=port.ra_selection,
            evidence_root=setup_root,
            pids=actual["pids"],
            cgroup_path=actual["cgroup_path"],
            counters=port.resource_monitor_counters,
            charge=port.ra_phase_charge,
            check=port.check_resource_deadline,
            read_charge=port.charge_ra_original_read,
            scope_start_ns=port.started_ns,
            deadline_ns=deadline,
        )
    port.ra_monitor = setup.monitor
    port.ra_setup_session = setup
    port.ra_phase_charge(8192, 1)
    io.write(setup.root / "binding.record", b.canonical(setup.binding))


def finish_protected_setup(port):
    setup = port.ra_setup_session
    frozen = b.digest(
        dict(
            configuration_scope_sha256=port.authority.configuration_scope_sha256,
            source_inventory_sha256=b.digest(port.settings["source_files"]),
            prior_root_attempts=port.ra_prior_root_attempts,
        )
    )

    def open_setup():
        port._source_check()
        verify_prepared_runtime(port)
        return frozen

    setup.freeze_and_open(frozen_data_inventory_sha256=frozen, actual_opener=open_setup)
    port.ra_monitor_rows_prior = setup.writer.rows
    port.ra_setup_running = False
    port.ra_monitor = None
    port.ra_active_scope_deadline = None


def current_capacity(port, *, next_write_bytes, next_creations):
    from . import s12_ra_g1_assurance as assurance

    port.check_resource_deadline()
    b.uint(next_write_bytes)
    b.uint(next_creations)
    initial = port.ra_initial_capacity
    current, originals = assurance.observe_capacity(
        Path(port.settings["output_parent"]),
        scope=port.ra_binding["scope"],
        selection_sha256=port.ra_binding["selection_sha256"],
        owner_reported_approval_sha256=initial["owner_reported_approval_sha256"],
        accounting_method_sha256=initial["accounting_method_sha256"],
        restrictions_inventory_sha256=initial["restrictions_inventory_sha256"],
        observed_utc=port.clock.utc(),
        clock_ns=port.clock.now_ns,
    )
    b.require(
        current["root_identity_inventory_sha256"]
        == initial["root_identity_inventory_sha256"],
        "B2_RA_CAPACITY_ROOT_CHANGED",
    )
    assurance.check_capacity(
        current, next_write_bytes=next_write_bytes, next_creations=next_creations
    )
    port.check_resource_deadline()
    return current


def runtime_prewrite(port, *, next_write_bytes, next_creations):
    """Fresh actual shared snapshot and prior acknowledged resource barrier."""
    port.check_deadline()
    b.require(port.ra_monitor is not None, "B2_RA_MONITOR_REQUIRED")
    port.ra_monitor.barrier(
        next_write_bytes=next_write_bytes, next_creations=next_creations
    )
    return current_capacity(
        port, next_write_bytes=next_write_bytes, next_creations=next_creations
    )


def inventory_roots(values):
    b.require(
        isinstance(values, (list, PathArray)) and 0 < len(values) <= 16,
        "B2_RA_INVENTORY_BOUND",
    )
    return old.inventory_roots(list(values))


def prior_root_attempts(port):
    """Derive prior charges from original per-member terminal snapshots.

    This metadata pass does not authorize a protected read. The graph performs
    its complete independent inventory/science reopen under the running monitor
    before BEGIN. A changed original cannot qualify using these scalar totals.
    """
    from . import s12_b2_ra_g1_graph as graph
    from . import s12_b2_ra_g1_contract as contract

    pointer = port.resource_binding
    b.require(type(pointer) is dict, "B2_RA_GRAPH_REQUIRED")
    model = graph.parse(port.records.raw(pointer["model_sha256"]), graph.MODEL)
    root = Path(port.settings["output_parent"]) / (
        "ra_g1_acceptance_" + pointer["model_sha256"]
    )
    io.private_directory(root)
    b.require(
        not (root / "ACTIVE.json").exists() and not (root / "MUTATING.json").exists(),
        "B2_GRAPH_BLOCKED",
    )
    total_records = model["ledger_record_limits"]["max_entries"]
    previous = None
    current_binding = None
    counts = {}
    for index in range(1, total_records + 1):
        path = root / f"{index:06d}.json"
        if not path.exists():
            break
        port.check_deadline()
        raw = graph._read_original(path, 65536, port.check_deadline)
        row = graph._row(raw)
        b.require(
            row["envelope_sha256"] == pointer["model_sha256"]
            and row["previous_ledger_sha256"] == previous,
            "B2_GRAPH_CHAIN",
        )
        graph.shape(row, graph.SCHEMAS[row["schema_version"]])
        if row["schema_version"] == graph.BINDING:
            current_binding = row
        elif row["schema_version"] == graph.FINISH:
            require_worker_success(port, row["slot_id"])
            slot = model["slots"][row["slot_id"] - 1]
            if slot["phase"] in ("run-campaign", "run-direct-n"):
                b.require(
                    current_binding is not None
                    and current_binding["slot_id"] == row["slot_id"],
                    "B2_RA_COUNTER_ORIGINAL_REQUIRED",
                )
                config = io.metadata(
                    port.records.raw(current_binding["configuration_scope_sha256"])
                )
                spec = config["runtime"]["campaign"]
                snap = contract.parse(
                    io.read(Path(spec["segment_path"]) / "snapshot.json", limit=65536),
                    contract.SNAPSHOT,
                )
                b.require(
                    snap["campaign_start_sha256"] == spec["start_sha256"],
                    "B2_RA_COUNTER_ORIGINAL_REQUIRED",
                )
                attempts = add(
                    snap["controller"]["charged_data_attempts"],
                    snap["controller"]["charged_control_attempts"],
                )
                member = slot["member_id"]
                b.require(
                    member is not None
                    and len(counts) <= 11
                    and attempts >= counts.get(member, 0),
                    "B2_RA_COUNTER_ORIGINAL_REQUIRED",
                )
                counts[member] = attempts
        previous = graph._raw_hash(raw)
    b.require(previous == pointer["slot_binding_sha256"], "B2_GRAPH_HEAD_CHANGED")
    slot = model["slots"][pointer["command_id"] - 1]
    port.ra_current_member_id = slot["member_id"]
    port.ra_prior_member_attempts = counts
    return add(*counts.values())


def monitor_counters(port):
    """Real immutable scheduler tuple; no sampler/writer safety lock or I/O."""
    from . import s12_ra_g1_monitor as monitor

    selected = port.allocation_limits
    if selected is None:
        b.require(
            port.resource_command is None
            and port.resource_ledger is None
            and port._generation_roots is None,
            "B2_RA_COUNTER_ORIGINAL_REQUIRED",
        )
        # This source-owned prefix has opened no application sink or native
        # engine. Monitor bootstrap has its separately charged writer counters.
        from . import s12_b2_ra_g1_allocation as allocations

        usage = {
            "invocations": dict.fromkeys(allocations.ROLES, 0),
            "python_reserved_bytes": 0,
        }
    else:
        usage = selected.usage()
    coordinator = getattr(port, "ra_coordinator", None)
    base = getattr(port, "ra_prior_root_attempts", None)
    if base is None:
        b.require(
            getattr(port, "ra_setup_running", False) and coordinator is None,
            "B2_RA_COUNTER_ORIGINAL_REQUIRED",
        )
        base = port.ra_setup_counter_prefix
        current_prior = 0
    else:
        current_prior = port.ra_prior_member_attempts.get(port.ra_current_member_id, 0)
    if coordinator is None:
        segment, current = 0, current_prior
    else:
        snapshot = coordinator.ra_charged_snapshot
        current = add(*snapshot)
        entry = port.ra_coordinator_entry_attempts
        b.require(current >= entry >= current_prior, "B2_RA_COUNTER_ORIGINAL_REQUIRED")
        segment = current - entry
    counts = dict(usage["invocations"])
    files = (
        "PARQUET_FILE",
        "RAW_PACK_FILE",
        "EXCLUSIVE_FILE",
        "EVENT_FILE",
        "PREFIX_FILE",
        "COMPARISON_FILE",
        "ADMIN_FILE",
    )
    writer = getattr(getattr(port, "ra_monitor", None), "writer", None)
    counts.update(
        application_write_reserved_bytes=add(
            usage["python_reserved_bytes"], getattr(port, "ra_monitor_write_bytes", 0)
        ),
        application_creations_charged=add(
            sum(usage["invocations"][key] for key in files),
            getattr(port, "ra_monitor_creations", 0),
        ),
        monitor_observations_charged=add(
            getattr(port, "ra_monitor_rows_prior", 0),
            0 if writer is None else writer.rows,
        ),
        monitor_write_bytes_charged=getattr(port, "ra_monitor_write_bytes", 0),
        source_read_calls=port.ra_original_read_calls,
        source_read_bytes=port.ra_original_read_bytes,
        identity_checks=port.authority._ra_identity_checks,
        segment_attempts=segment,
        root_attempts=add(base - current_prior, current),
    )
    b.require(set(counts) == set(monitor.COUNTERS), "B2_RA_COUNTER_ORIGINAL_REQUIRED")
    return counts


def validate_capacity_originals(value, records):
    """Reopen original units, filesystem counters and root identity."""
    from . import s12_ra_g1_assurance as assurance

    assurance.validate_capacity(value)
    original = io.metadata(records.raw(value["filesystem_originals_sha256"]))
    fields = {
        "f_bsize",
        "f_frsize",
        "f_blocks",
        "f_bfree",
        "f_bavail",
        "f_files",
        "f_ffree",
        "f_favail",
        "f_flag",
        "f_namemax",
    }
    b.require(set(original) == fields, "B2_RA_CAPACITY_ORIGINALS")
    for number in original.values():
        b.uint(number)
    b.require(
        original["f_frsize"] > 0
        and original["f_bsize"] > 0
        and original["f_bavail"] <= original["f_bfree"] <= original["f_blocks"]
        and original["f_favail"] <= original["f_ffree"] <= original["f_files"]
        and value["bavail_bytes"]["value"]
        == mul(original["f_bavail"], original["f_frsize"])
        and value["favail"]["value"] == original["f_favail"],
        "B2_RA_CAPACITY_ORIGINALS",
    )
    raw = records.raw(value["root_identity_inventory_sha256"])
    roots = json.loads(raw, object_pairs_hook=io.pairs)
    b.require(
        b.canonical(roots) == raw and type(roots) is list and 1 <= len(roots) <= 64,
        "B2_RA_CAPACITY_ORIGINALS",
    )
    for root in roots:
        b.require(type(root) is list and len(root) == 5, "B2_RA_CAPACITY_ORIGINALS")
        _path(root[0])
        for number in root[1:]:
            b.uint(number)
    for field in (
        "owner_reported_approval_sha256",
        "accounting_method_sha256",
        "restrictions_inventory_sha256",
    ):
        records.raw(value[field])
    return value


def result_digest(result):
    if type(result) is bytes:
        b.require(len(result) == 32, "B2_RA_RESULT_IDENTITY")
        return result.hex()
    return b.digest(result)


def phase_source_inventory(phase, session, result, *, persist=False):
    """Actual immutable scientific outputs, distinct from charged scratch/tail."""
    p = session.port
    roots = []
    if session.output.exists():
        roots.append(session.output)
    identity = session.output.with_name(session.output.name + ".identity.json")
    if identity.exists():
        roots.append(identity)
    records = []
    if type(result) is dict:
        for key in ("calibration_plan_sha256", "bootstrap_acquisition_sha256"):
            if key in result:
                raw = p.records.raw(result[key])
                records.append({"role": key, "sha256": b.sha(raw).hex()})
    observed = old.generation_inventory(
        roots,
        max_entries=p.settings["phase_generation_max_files"],
        check=p.check_deadline,
    )
    value = {
        "schema_version": "stage12_phase_frozen_sources_b2_ra_g1_v1",
        "phase": phase,
        "configuration_sha256": b.digest(session.configuration),
        "result_sha256": result_digest(result),
        "generated_scientific_sources": observed,
        "original_records": records,
    }
    digest = b.digest(value)
    raw = b.canonical(value)
    if persist:
        b.require(
            p.records.put(
                raw, owner=p.assert_administrative_owner, secret_guard=p.secret_guard
            )
            == digest,
            "B2_RA_FROZEN_SOURCE_RECORD",
        )
    else:
        b.require(p.records.raw(digest) == raw, "B2_RA_FROZEN_SOURCE_RECORD")
    return digest


def _readonly_records(port):
    """Existing scientific constructors may compare originals, never recreate one."""

    class Originals:
        raw = port.records.raw
        get = port.records.get

        def put(self, raw, *, owner, secret_guard):
            owner()
            secret_guard(raw)
            digest = b.sha(raw).hex()
            b.require(port.records.raw(digest) == raw, "B2_RA_OPENER_ORIGINAL_CHANGED")
            return digest

    return Originals()


def actual_phase_opener(phase, session, result):
    """Invoke original complete readers/algorithms under the current phase gate."""
    from contextlib import ExitStack
    from .. import stage12_development_cli as cli
    from . import s12_b2_planning as planning
    from . import s12_b2_phase_io as phase_io
    from . import s12_b2_calibration as calibration
    from . import s12_b2_catalog as catalogs
    from . import s12_b2_recovery as recovery
    from . import s12_b2_publication as publication
    from . import s12_b2_evidence as evidence
    from . import s12_b2_operations as operations

    p, config = session.port, session.configuration
    p.check_deadline()
    p.gate.check()
    p._source_check()
    reader_parent = session.scratch.with_name(session.scratch.name + "_readers")
    if not reader_parent.exists():
        io.reserve(reader_parent)
    opener_root = reader_parent / "actual_resource_opener"
    io.reserve(opener_root)
    opened_session = cli.Session(
        p,
        config,
        session.output,
        opener_root / "validation",
        session.authorization_sha256,
    )
    with ExitStack() as resources:
        if p.local_only and phase in (
            "prepare-bootstrap",
            "build-workload",
            "offline-preflight",
        ):
            p.local_contract.reopen_metadata(
                p,
                config,
                session.output,
                result,
                opener_root / "local",
                lambda: cli.catalog_for(session, resources),
            )
        elif phase == "build-catalog":
            binding = p.records.get(
                config["input_binding_sha256"], "stage11_input_binding"
            )
            p.authority.require("protected_input", b.digest(binding), binding)
            b.require(
                io.metadata(
                    io.read(
                        session.output.with_name(session.output.name + ".identity.json")
                    )
                )
                == result,
                "B2_RA_OPENER_RESULT",
            )
            catalog = catalogs.Catalog(
                session.output,
                binding,
                expected_file_sha256=result["catalog_file_sha256"],
            )
            resources.callback(catalog.close)
            catalog.verify()
        elif phase == "plan-calibration":
            catalog = cli.catalog_for(session, resources)
            selected = calibration.select(
                catalog,
                opener_root / "selection.sqlite",
                C=config["C"],
                T=config["T"],
                supported=p.authority.supported_size(
                    config["capability_evidence_sha256"]
                ),
                authority=p.authority,
                decision_hash=config["depth_decision_sha256"],
            )
            reproduced = planning.seal_core(
                _readonly_records(p),
                selected,
                catalog,
                lineage_hash=config["lineage_binding_sha256"],
                capability_hash=config["capability_evidence_sha256"],
                decision_hash=config["depth_decision_sha256"],
                owner=p.assert_administrative_owner,
                secret_guard=p.secret_guard,
            )
            b.require(
                reproduced == result["calibration_plan_sha256"]
                and result["scientific_N_selected"] is False,
                "B2_RA_OPENER_RESULT",
            )
            catalog.verify()
        elif phase == "prepare-bootstrap":
            profile, plan = p._profile_plan(config["bootstrap"])
            start = operations.parse_selected(
                p.records.raw(config["bootstrap"]["start_sha256"])
            )
            from . import s12_b2_pipeline as pipeline

            pipeline.bootstrap_spent(
                p.records, result["bootstrap_acquisition_sha256"], plan, profile, start
            )
            b.require(
                result["admission_issued"] is result["dispatch_authorized"] is False,
                "B2_RA_OPENER_RESULT",
            )
        elif phase == "preflight":
            profile, plan, start, science, admission, works = p.campaign_inputs()
            catalog = cli.catalog_for(session, resources)
            catalog.verify()
            p.gate.validate_campaign(start, plan, admission)
            p.gate.validate_workload(
                catalog,
                profile,
                plan,
                works,
                admission,
                opener_root / "workload.sqlite",
            )
            b.require(
                result["profile_sha256"] == b.digest(profile)
                and result["plan_sha256"] == b.digest(plan)
                and result["admission_sha256"] == b.digest(admission),
                "B2_RA_OPENER_RESULT",
            )
        elif phase in ("run-campaign", "run-direct-n"):
            profile, plan, start, science, admission, works = p.campaign_inputs()

            class Receipts:
                # The original receipt and predecessor-location algorithms are
                # reused without constructing a complete-only campaign index.
                locate = phase_io.CampaignReader.locate
                receipt = phase_io.CampaignReader.receipt

            reader = Receipts()
            reader.segment = session.output
            reader.plan = plan
            reader.rules = p.response_rules
            reader.control_adapters = p.control_adapters
            opened = recovery.reopen(
                session.output,
                start,
                profile,
                plan,
                works=works,
                verify_receipt=reader.receipt,
                scratch=opener_root / "segment.sqlite",
                authority=p.gate,
            )
            b.require(
                opened["snapshot"]["operations_report_sha256"] == b.digest(result),
                "B2_RA_OPENER_RESULT",
            )
        elif phase == "close-campaign":
            p.verify_campaign()
            profile, plan, start, science, admission, works = p.campaign_inputs()
            closures = []
            from . import s12_public_journal as journal

            node = p.segment
            while node is not None:
                p.check_deadline()
                b.require(len(closures) < 110, "B2_RA_LINEAGE_BOUND")
                closures.append(
                    operations.parse_selected(io.read(node / "snapshot.json"))[
                        "segment_closure_sha256"
                    ]
                )
                node = journal.predecessor_root(node)
            opened = evidence.campaign_closure(
                p.records,
                config["campaign_closure_sha256"],
                plan=plan,
                start=science,
                segments=list(reversed(closures)),
                authority=p.gate,
                population_scope=p.population_scope,
            )
            b.require(opened == result, "B2_RA_OPENER_RESULT")
        elif phase == "evaluate-calibration":
            manifest = io.read(session.output / "manifest.json")
            opened = phase_io.reopen_phase(session.output, b.sha(manifest).hex())
            b.require(opened == result, "B2_RA_OPENER_RESULT")
            catalog = cli.catalog_for(session, resources)
            selection, _ = planning.load_selection(
                p.records,
                config["selection_sha256"],
                catalog,
                authority=p.authority,
                scratch=opener_root / "selection.sqlite",
            )
            io.reserve(opened_session.scratch)
            observations = cli.open_observations(opened_session, catalog, resources)
            repeated = calibration.evaluate(
                catalog,
                selection,
                observations,
                window_hash=config["window_plan_sha256"],
                selection_hash=config["selection_sha256"],
                authority=p.authority,
                comparison_writer=lambda row: None,
            )
            b.require(repeated == result, "B2_RA_OPENER_RESULT")
        elif phase == "close-window":
            opened = evidence.window_closure(
                p.records,
                config["window_closure_sha256"],
                window_hash=config["window_plan_sha256"],
                campaigns=config["ordered_campaign_closure_hashes"],
                authority=p.gate,
            )
            b.require(opened == result, "B2_RA_OPENER_RESULT")
            p.window_state(config["window_plan_sha256"])
        elif phase in ("publish", "reopen"):
            catalog = cli.catalog_for(session, resources)
            p.verify_campaign()
            root = (
                session.output
                if phase == "publish"
                else Path(config["publication_path"])
            )
            expected = (
                bytes.fromhex(result_digest(result))
                if phase == "publish"
                else bytes.fromhex(config["manifest_sha256"])
            )
            retained = io.metadata(io.read(root / "campaign.json"))
            n, adequacy, retention = cli.calibration_checks(
                opened_session, catalog, resources, retained["plan"]
            )
            opened = publication.validate_terminal(
                root,
                expected,
                committed=True,
                validate_science=lambda r, m: publication.scientific_reopen(
                    r,
                    m,
                    catalog=catalog,
                    rules=p.response_rules,
                    scratch=opener_root / "publication",
                    memory_bytes=config["external_sort_memory_bytes"],
                    gate=p.gate,
                    verify_campaign=p.verify_campaign,
                    verify_calibration=adequacy,
                    verify_final_retention=retention,
                ),
            )
            if phase == "reopen":
                b.require(opened == result, "B2_RA_OPENER_RESULT")
        else:
            b.require(False, "B2_RA_OPENER_PHASE")
    p.gate.check()
    p._source_check()
    p.check_deadline()
    return result


PENDING = "stage12_resource_phase_pending_b2_ra_g1_v1"
SUCCESS = "stage12_resource_phase_success_b2_ra_g1_v1"
PENDING_SCHEMA = {
    "schema_version": "=" + PENDING,
    "model_sha256": "D",
    "slot_id": "P",
    "slot_binding_sha256": "D",
    "phase_id": "P",
    "configuration_sha256": "D",
    "binding_sha256": "D",
    "selection_sha256": "D",
    "supervisor_context_sha256": "D",
    "resource_evidence_root": {"primitive": "absolute_path"},
    "setup_evidence_root": {"primitive": "absolute_path"},
    "setup_binding_sha256": "D",
    "selection_record_path": {"primitive": "absolute_path"},
    "started_mono_ns": "U",
    "phase_deadline_ns": "U",
    "phase_until": "Z",
}
SUCCESS_SCHEMA = {
    "schema_version": "=" + SUCCESS,
    "model_sha256": "D",
    "slot_id": "P",
    "pending_sha256": "D",
    "phase_terminal_sha256": "D",
    "setup_terminal_sha256": "D",
    "child_result_sha256": "D",
    "supervisor_return_sha256": "D",
    "phase_terminal_path": {"primitive": "absolute_path"},
    "child_result_path": {"primitive": "absolute_path"},
    "supervisor_return_path": {"primitive": "absolute_path"},
    "native_maximum": "=NOT_PROVEN",
    "physical_maximum": "=NOT_PROVEN",
    "disposition": "=COMPLETE_SELECTED_SCOPE",
}


CHILD_RETURN_SCHEMA = {"pid": "P", "wait_status": "U", "acquired_mono_ns": "U"}
SUPERVISOR_RETURN_SCHEMA = {
    "pid": "P",
    "returncode": "U",
    "acquired_mono_ns": "U",
    "phase_terminal_sha256": "D",
}


def completion_root(output_parent, model_hash):
    b.validate_type(model_hash, "D")
    return Path(output_parent) / ("ra_g1_completion_" + model_hash)


def begin_worker_pending(port):
    from . import s12_b2_ra_g1_graph as graph

    pointer = port.resource_binding
    root = completion_root(port.settings["output_parent"], pointer["model_sha256"])
    if not root.exists():
        b.require(pointer["command_id"] == 1, "B2_RA_PRIOR_RESOURCE_TERMINAL_MISSING")
        port.ra_phase_charge(0, 1)
        io.reserve(root)
    io.private_directory(root)
    path = root / f"{pointer['command_id']:06d}.pending.json"
    b.require(not path.exists(), "B2_RA_RESOURCE_PHASE_ALREADY_ATTEMPTED")
    row = dict(
        schema_version=PENDING,
        model_sha256=pointer["model_sha256"],
        slot_id=pointer["command_id"],
        slot_binding_sha256=pointer["slot_binding_sha256"],
        phase_id=port.ra_resource_session.phase,
        configuration_sha256=b.digest(port.config),
        binding_sha256=port.ra_binding_sha256,
        selection_sha256=port.ra_binding["selection_sha256"],
        supervisor_context_sha256=port.config["resource_execution"][
            "supervisor_context_sha256"
        ],
        resource_evidence_root=port.config["resource_paths"]["resource_evidence_root"],
        setup_evidence_root=str(port.ra_setup_session.root),
        setup_binding_sha256=b.digest(port.ra_setup_session.binding),
        selection_record_path=str(
            port.records.root / (port.ra_binding["selection_sha256"] + ".json")
        ),
        started_mono_ns=port.clock.now_ns(),
        phase_deadline_ns=port.deadline,
        phase_until=port.phase_until,
    )
    graph.shape(row, PENDING_SCHEMA)
    port.ra_phase_charge(8192, 1)
    io.write(path, b.canonical(row))
    b.require(io.metadata(io.read(path, limit=8192)) == row, "B2_RA_PENDING_CHANGED")
    port.ra_pending_record = row
    return row


def require_worker_success(port, slot_id):
    """FINISH alone is never RA closure or permission for the next command."""
    from . import s12_b2_ra_g1_graph as graph
    from . import s12_ra_g1_monitor as monitor

    root = completion_root(
        port.settings["output_parent"], port.resource_binding["model_sha256"]
    )
    pending = io.metadata(io.read(root / f"{slot_id:06d}.pending.json", limit=8192))
    value = io.metadata(io.read(root / f"{slot_id:06d}.success.json", limit=8192))
    graph.shape(pending, PENDING_SCHEMA)
    graph.shape(value, SUCCESS_SCHEMA)
    b.require(
        value["model_sha256"]
        == pending["model_sha256"]
        == port.resource_binding["model_sha256"]
        and value["slot_id"] == pending["slot_id"] == slot_id
        and value["pending_sha256"] == b.digest(pending),
        "B2_RA_RESOURCE_TERMINAL_BINDING",
    )
    terminal = io.metadata(io.read(Path(value["phase_terminal_path"]), limit=8192))
    monitor.validate(terminal, monitor.PHASE_TERMINAL)
    child = io.metadata(io.read(Path(value["child_result_path"]), limit=8192))
    returned = io.metadata(io.read(Path(value["supervisor_return_path"]), limit=8192))
    graph.shape(child, CHILD_RETURN_SCHEMA)
    graph.shape(returned, SUPERVISOR_RETURN_SCHEMA)
    b.require(
        b.digest(terminal) == value["phase_terminal_sha256"]
        and b.digest(child)
        == value["child_result_sha256"]
        == terminal["child_result_original_sha256"]
        and b.digest(returned) == value["supervisor_return_sha256"]
        and terminal["binding_sha256"] == pending["binding_sha256"]
        and terminal["selection_sha256"] == pending["selection_sha256"]
        and terminal["phase_id"] == pending["phase_id"]
        and terminal["disposition"] == "COMPLETE_SELECTED_SCOPE"
        and terminal["child_exit_code"] == 0
        and terminal["child_signal"] is None
        and returned.get("returncode") == 0
        and returned.get("phase_terminal_sha256") == b.digest(terminal)
        and terminal["terminal_prewrite_ns"]
        <= returned.get("acquired_mono_ns", -1)
        < pending["phase_deadline_ns"],
        "B2_RA_RESOURCE_TERMINAL_BINDING",
    )
    reopen_prior_resource_stream(port, pending, terminal, child, returned)
    setup_pending = dict(
        pending,
        binding_sha256=pending["setup_binding_sha256"],
        resource_evidence_root=pending["setup_evidence_root"],
        phase_id=1,
    )
    setup_terminal = io.metadata(
        io.read(
            Path(pending["setup_evidence_root"]) / "phase_terminal.record", limit=8192
        )
    )
    b.require(
        b.digest(setup_terminal) == value["setup_terminal_sha256"],
        "B2_RA_SETUP_TERMINAL_REQUIRED",
    )
    reopen_prior_resource_stream(
        port, setup_pending, setup_terminal, child, returned, administrative=True
    )
    port.authority.require("resource_phase_terminal", b.digest(value), pending)
    return value


def finalize_worker_pending(
    *,
    output_parent,
    pending_record,
    phase_terminal_path,
    child_result_path,
    supervisor_return_path,
    actual_supervisor_returncode,
    expected_supervisor_pid,
    check,
    clock_ns,
    clock_utc,
    charge,
    read_charge,
):
    """Seal only freshly verified source-owned supervisor return/tail originals.

    The reviewed parent calls this after its genuine wait. This function cannot
    produce a child wait status or authorize source/controller/service access.
    Uncertain or late paths retain the permanent pending original without success.
    """
    from . import s12_b2_ra_g1_graph as graph
    from . import s12_ra_g1_monitor as monitor

    check()
    graph.shape(pending_record, PENDING_SCHEMA)
    b.require(
        callable(charge)
        and callable(clock_utc)
        and clock_utc() < pending_record["phase_until"],
        "B2_RA_SUPERVISOR_RETURN_REQUIRED",
    )
    b.require(
        type(actual_supervisor_returncode) is int
        and actual_supervisor_returncode == 0
        and type(expected_supervisor_pid) is int
        and expected_supervisor_pid > 0
        and clock_ns() < pending_record["phase_deadline_ns"],
        "B2_RA_SUPERVISOR_RETURN_REQUIRED",
    )
    root = completion_root(output_parent, pending_record["model_sha256"])
    pending_path = root / f"{pending_record['slot_id']:06d}.pending.json"

    def read_original(path, limit=8192):
        check()
        read_charge(1, limit + 1)
        return io.metadata(io.read(Path(path), limit=limit))

    b.require(
        read_original(pending_path) == pending_record,
        "B2_RA_PENDING_CHANGED",
    )
    terminal = read_original(phase_terminal_path)
    monitor.validate(terminal, monitor.PHASE_TERMINAL)
    child = read_original(child_result_path)
    returned = read_original(supervisor_return_path)
    graph.shape(child, CHILD_RETURN_SCHEMA)
    graph.shape(returned, SUPERVISOR_RETURN_SCHEMA)
    selected = read_original(pending_record["selection_record_path"], 65536)
    b.require(
        b.digest(selected) == pending_record["selection_sha256"],
        "B2_RA_SELECTION_BINDING",
    )
    check = _terminal_guard(pending_record, selected, child, check, clock_ns)
    check()
    b.require(
        set(returned)
        == {"pid", "returncode", "acquired_mono_ns", "phase_terminal_sha256"}
        and returned["pid"] == expected_supervisor_pid
        and returned["returncode"] == actual_supervisor_returncode
        and returned["phase_terminal_sha256"] == b.digest(terminal)
        and terminal["binding_sha256"] == pending_record["binding_sha256"]
        and terminal["selection_sha256"] == pending_record["selection_sha256"]
        and terminal["phase_id"] == pending_record["phase_id"]
        and terminal["disposition"] == "COMPLETE_SELECTED_SCOPE"
        and terminal["child_exit_code"] == 0
        and terminal["child_signal"] is None
        and b.digest(child) == terminal["child_result_original_sha256"]
        and terminal["terminal_prewrite_ns"]
        <= returned["acquired_mono_ns"]
        <= clock_ns()
        < pending_record["phase_deadline_ns"],
        "B2_RA_SUPERVISOR_RETURN_REQUIRED",
    )
    check()
    setup_terminal = read_original(
        Path(pending_record["setup_evidence_root"]) / "phase_terminal.record"
    )
    monitor.validate(setup_terminal, monitor.PHASE_TERMINAL)
    b.require(
        setup_terminal["binding_sha256"] == pending_record["setup_binding_sha256"]
        and setup_terminal["selection_sha256"] == pending_record["selection_sha256"]
        and setup_terminal["phase_id"] == 1
        and setup_terminal["disposition"] == "COMPLETE_SELECTED_SCOPE"
        and setup_terminal["child_exit_code"] == 0
        and setup_terminal["child_signal"] is None
        and setup_terminal["child_result_original_sha256"] == b.digest(child)
        and setup_terminal["terminal_prewrite_ns"] <= returned["acquired_mono_ns"],
        "B2_RA_SETUP_TERMINAL_REQUIRED",
    )
    row = dict(
        schema_version=SUCCESS,
        model_sha256=pending_record["model_sha256"],
        slot_id=pending_record["slot_id"],
        pending_sha256=b.digest(pending_record),
        phase_terminal_sha256=b.digest(terminal),
        setup_terminal_sha256=b.digest(setup_terminal),
        child_result_sha256=b.digest(child),
        supervisor_return_sha256=b.digest(returned),
        phase_terminal_path=str(Path(phase_terminal_path)),
        child_result_path=str(Path(child_result_path)),
        supervisor_return_path=str(Path(supervisor_return_path)),
        native_maximum="NOT_PROVEN",
        physical_maximum="NOT_PROVEN",
        disposition="COMPLETE_SELECTED_SCOPE",
    )
    graph.shape(row, SUCCESS_SCHEMA)
    target = root / f"{row['slot_id']:06d}.success.json"
    charge(8192, 1)
    io.write(target, b.canonical(row))
    check()
    b.require(
        clock_ns() < pending_record["phase_deadline_ns"]
        and read_original(target) == row,
        "B2_RA_LATE_OR_UNCERTAIN_SUCCESS",
    )
    check()
    return b.digest(row)


REGISTERED_PATHS = "stage12_resource_registered_paths_b2_ra_g1_v1"
REGISTERED_PATHS_SCHEMA = {
    "schema_version": "=" + REGISTERED_PATHS,
    "scope": {"enum": ["DEVELOPMENT_LOCAL_PREPARATION", "DEVELOPMENT_ONLY"]},
    "native_roots": [{"primitive": "absolute_path"}],
    "native_paths": [{"primitive": "absolute_path"}],
    "review_sha256": "D",
    "native_role_inventory_sha256": "D",
}


def registered_paths(port):
    from . import s12_b2_ra_g1_graph as graph

    spec = port.config["resource_paths"]
    row = io.metadata(port.records.raw(spec["registered_paths_record_sha256"]))
    graph.shape(row, REGISTERED_PATHS_SCHEMA)
    b.require(
        row["scope"] == port.ra_binding["scope"]
        and 1 <= len(row["native_roots"]) <= 16
        and len(row["native_roots"]) + len(row["native_paths"]) <= 64
        and len(set(row["native_roots"])) == len(row["native_roots"])
        and len(set(row["native_paths"])) == len(row["native_paths"]),
        "B2_RA_NATIVE_PATHS",
    )
    for value in (*row["native_roots"], *row["native_paths"]):
        _path(value)
        b.require(len(value.encode("utf8")) <= 512, "B2_RA_NATIVE_PATHS")
    port.records.raw(row["review_sha256"])
    port.records.raw(row["native_role_inventory_sha256"])
    port.authority.require(
        "resource_registered_paths", spec["registered_paths_record_sha256"], row
    )
    return tuple(Path(x) for x in row["native_roots"]), tuple(
        Path(x) for x in row["native_paths"]
    )


def execute_phase(phase, session):
    """RA worker lifecycle: original phase, real opener, FINAL, no fake wait0."""
    command_entry_ns = session.port.clock.now_ns()
    from contextlib import ExitStack
    from .. import stage12_development_cli as cli
    from . import s12_ra_g1_execution as execution

    p = session.port
    p.ra_command_entry_ns = command_entry_ns
    p.ra_active_scope_deadline = min(
        p.deadline,
        command_entry_ns
        + p.ra_selection["limits"]["stages"][1]["deadline_ms"] * 1000000,
    )
    p.check_resource_deadline()
    b.require(
        p.ra_binding is not None and p.ra_selection is not None,
        "B2_RA_ASSURANCE_REQUIRED",
    )

    def charge(size, creations):
        monitor_charge(p, size, creations)

    p.ra_phase_charge = charge
    monitor_session = None
    try:
        factory = (
            p._test.get("resource_session_factory")
            if p.test_only and p._test is not None
            else None
        )
        if factory is not None:
            b.require(
                callable(factory) and p.population_scope == b.SYNTHETIC,
                "B2_RA_TEST_CONTEXT",
            )
            monitor_session = factory(p, charge)
            b.require(
                isinstance(monitor_session, execution.PhaseSession)
                and monitor_session.test_only
                and monitor_session.binding == p.ra_binding
                and monitor_session.selection == p.ra_selection,
                "B2_RA_TEST_CONTEXT",
            )
            monitor_session.start()
        else:
            roots, paths = registered_paths(p)
            monitor_session = execution.start_session(
                p.authority,
                p.config,
                p.ra_binding,
                p.ra_selection,
                Path(p.config["resource_paths"]["resource_evidence_root"]),
                p.ra_active_scope_deadline,
                2,
                p.check_resource_deadline,
                p.resource_monitor_counters,
                charge,
                p.charge_ra_original_read,
                clock_ns=p.clock.now_ns,
                native_roots=roots,
                native_paths=paths,
                scope_start_ns=command_entry_ns,
            )
        p.ra_monitor = monitor_session.monitor
        p.ra_active_scope_deadline = monitor_session.deadline
        p.ra_resource_session = monitor_session
        begin_worker_pending(p)
        with ExitStack() as resources:
            result = cli._execute(phase, session, resources)
        frozen = phase_source_inventory(phase, session, result, persist=True)

        def actual_open():
            actual_phase_opener(phase, session, result)
            b.require(
                phase_source_inventory(phase, session, result) == frozen,
                "B2_RA_FROZEN_SOURCES_CHANGED",
            )
            # All native readers, original graph validation and FINISH stay
            # inside actual opening while the resource monitor remains alive.
            p.close()
            return result

        opened, _ = monitor_session.freeze_and_open(
            frozen_data_inventory_sha256=frozen, actual_opener=actual_open
        )
        p.check_resource_deadline()
        p.ra_resource_finalized = True
        return opened
    except BaseException:
        # The permanent pending original blocks this root even if an artifact
        # or graph FINISH exists. Cleanup cannot issue a supervisor success.
        if monitor_session is not None:
            monitor_session.abort()
        try:
            p.close()
        except BaseException:
            pass
        raise


def _terminal_guard(pending, selected, child, check, clock_ns):
    from . import s12_ra_g1_assurance as assurance

    assurance.validate_selection(selected)
    b.require(
        len(selected["limits"]["stages"]) == 3
        and selected["limits"]["stages"][2]["phase"] == 3,
        "B2_RA_PROTECTED_SCOPE_ROSTER",
    )
    deadline = min(
        pending["phase_deadline_ns"],
        child["acquired_mono_ns"]
        + selected["limits"]["stages"][2]["deadline_ms"] * 1000000,
    )

    def guard():
        check()
        b.require(clock_ns() < deadline, "B2_RA_TERMINAL_DEADLINE")

    return guard


def verify_setup_tail(
    pending,
    child,
    *,
    check,
    clock_ns,
    charge,
    read_charge,
    current_counter_sha256,
    genuine_wait_status,
    expected_child_pid,
    test_only=False,
):
    """The same genuine worker return closes its earlier resource-only prefix."""
    from . import s12_ra_g1_assurance as assurance
    from . import s12_ra_g1_execution as execution
    from . import s12_ra_g1_monitor as monitor

    root = Path(pending["setup_evidence_root"])

    def read(name):
        read_charge(1, 8193)
        return io.metadata(io.read(root / (name + ".record"), limit=8192))

    binding = read("binding")
    assurance.shape(binding, execution.ADMIN_BINDING_SCHEMA)
    b.require(
        b.digest(binding) == pending["setup_binding_sha256"]
        and binding["role"] == "PROTECTED_SETUP"
        and binding["phase_id"] == 1,
        "B2_RA_SETUP_TERMINAL_REQUIRED",
    )
    read_charge(1, 65537)
    selected = io.metadata(io.read(Path(pending["selection_record_path"]), limit=65536))
    assurance.validate_selection(selected)
    b.require(
        b.digest(selected) == pending["selection_sha256"], "B2_RA_SELECTION_BINDING"
    )
    check = _terminal_guard(pending, selected, child, check, clock_ns)
    check()
    closure, opener, terminal = (
        read("preopening"),
        read("opener_return"),
        read("monitor_terminal"),
    )
    b.require(
        opener["actual_opener_return_ns"] < binding["deadline_mono_ns"],
        "B2_RA_SETUP_TERMINAL_REQUIRED",
    )
    protocol = monitor.reopen_phase_protocol(
        binding_sha256=pending["setup_binding_sha256"],
        selection_sha256=pending["selection_sha256"],
        phase_id=1,
        closure=closure,
        opener_return=opener,
        monitor_terminal=terminal,
        deadline_ns=pending["phase_deadline_ns"],
        check=check,
        clock_ns=clock_ns,
    )

    def persist(value, guard):
        guard()
        charge(8192, 1)
        path = root / "phase_terminal.record"
        io.write(path, b.canonical(value))
        guard()
        return io.metadata(io.read(path, limit=8192))

    seed = b.digest(
        dict(
            schema_version="stage12_resource_monitor_seed_ra_g1_v1",
            binding_sha256=pending["setup_binding_sha256"],
            selection_sha256=pending["selection_sha256"],
            phase_id=1,
        )
    )
    return monitor.verify_tail(
        protocol=protocol,
        monitor_path=root / "observations.bin",
        selected=selected,
        seed_sha256=seed,
        child_result=child,
        genuine_wait_status=genuine_wait_status,
        expected_child_pid=expected_child_pid,
        current_counter_sha256=current_counter_sha256,
        persist_terminal=persist,
        original_observation_reader=lambda digest: monitor.read_original_observation(
            root / "originals" / (digest + ".record"),
            expected_sha256=digest,
            check=check,
            charge_read=read_charge,
            test_only=test_only,
        ),
        test_only=test_only,
        worker_validation=read("worker_validation"),
        charge_read=read_charge,
    )


def _monitor_history(function):
    from functools import wraps

    @wraps(function)
    def bounded(*args, **kwargs):
        with HistoryLease(4 * 2**20):
            return function(*args, **kwargs)

    return bounded


@_monitor_history
def reopen_prior_resource_stream(
    port, pending, phase_terminal, child, returned, administrative=False
):
    """Fresh historical originals, charged to this entry's current deadline.

    Historical acquisition times are checked against their original deadline;
    this read never recreates or claims a new historical wait/closure event.
    """
    from . import s12_ra_g1_assurance as assurance
    from . import s12_ra_g1_execution as execution
    from . import s12_ra_g1_monitor as monitor

    root = Path(pending["resource_evidence_root"])
    if administrative:
        binding = io.metadata(io.read(root / "binding.record", limit=8192))
        assurance.shape(binding, execution.ADMIN_BINDING_SCHEMA)
        b.require(
            b.digest(binding) == pending["binding_sha256"],
            "B2_RA_SETUP_TERMINAL_REQUIRED",
        )
    else:
        binding = io.metadata(port.records.raw(pending["binding_sha256"]))
        assurance.shape(binding, assurance.SCHEMA)
    selected = assurance.validate_selection(
        io.metadata(port.records.raw(pending["selection_sha256"]))
    )
    b.require(
        selected["scope"] == binding["scope"]
        and binding["selection_sha256"] == pending["selection_sha256"],
        "B2_RA_RESOURCE_TERMINAL_BINDING",
    )

    def read_record(name):
        path = root / (name + ".record")
        port.charge_ra_original_read(1, 8193)
        return io.metadata(io.read(path, limit=8192))

    closure = read_record("preopening")
    opener = read_record("opener_return")
    terminal = read_record("monitor_terminal")
    worker = read_record("worker_validation")
    monitor.validate(closure, monitor.CLOSURE)
    monitor.validate(opener, monitor.OPENER)
    monitor.validate(terminal, monitor.MONITOR_TERMINAL)
    execution.validate_worker_validation(worker)
    b.require(
        closure["binding_sha256"]
        == opener["binding_sha256"]
        == terminal["binding_sha256"]
        == pending["binding_sha256"]
        and closure["phase_id"]
        == opener["phase_id"]
        == terminal["phase_id"]
        == pending["phase_id"]
        and opener["preopening_closure_sha256"] == b.digest(closure)
        and terminal["opener_return_sha256"]
        == b.digest(opener)
        == phase_terminal["opener_return_sha256"]
        and phase_terminal["monitor_terminal_sha256"] == b.digest(terminal)
        and opener["actual_opener_return_ns"]
        <= terminal["final_observation_ns"]
        <= child["acquired_mono_ns"]
        <= phase_terminal["tail_check_start_ns"]
        <= phase_terminal["tail_check_end_ns"]
        <= phase_terminal["terminal_prewrite_ns"]
        <= returned["acquired_mono_ns"]
        < pending["phase_deadline_ns"]
        and terminal["disposition"] == "CLOSED_SELECTED_SCOPE"
        and terminal["writer_state"] == "HEALTHY_RELEASED"
        and opener["opener_disposition"] == "DATA_OPENED"
        and closure["outcome"] == "PENDING_OPEN"
        and closure["actual_opener_record_sha256"] is None
        and worker["monitor_terminal_sha256"] == b.digest(terminal)
        and worker["opener_return_sha256"] == b.digest(opener),
        "B2_RA_RESOURCE_TERMINAL_BINDING",
    )
    seed = b.digest(
        dict(
            schema_version="stage12_resource_monitor_seed_ra_g1_v1",
            binding_sha256=pending["binding_sha256"],
            selection_sha256=pending["selection_sha256"],
            phase_id=pending["phase_id"],
        )
    )
    coverage = monitor.Coverage(
        binding_sha256=pending["binding_sha256"],
        selection_sha256=pending["selection_sha256"],
        phase_id=pending["phase_id"],
        seed_sha256=seed,
        selected=selected,
        scope_start_ns=terminal["coverage_start_ns"],
    )
    # Bounded digest/name membership fits the selected 8MiB history allowance;
    # no observation or original JSON row is retained beyond its own read.
    allowed = set()
    for row in monitor.read_observations(
        root / "observations.bin",
        maximum_rows=selected["limits"]["monitor_rows"],
        check=port.check_deadline,
        charge_read=port.charge_ra_original_read,
    ):
        digest = row["visible_identity_inventory_sha256"]
        b.require(
            digest in allowed or len(allowed) < selected["limits"]["monitor_rows"],
            "B2_RA_MONITOR_MEMBERSHIP_BOUND",
        )
        allowed.add(digest)
        original = monitor.read_original_observation(
            root / "originals" / (digest + ".record"),
            expected_sha256=digest,
            check=port.check_deadline,
            charge_read=port.charge_ra_original_read,
            test_only=port.test_only,
        )
        monitor.validate_original_observation(
            original, observation=row, allow_synthetic=port.test_only
        )
        coverage.add(row)
        if coverage.seq == closure["last_seq"]:
            b.require(
                coverage.inventory_sha256()
                == closure["original_observation_prefix_sha256"]
                and b.digest(row["counters"]) == closure["counter_totals_sha256"],
                "B2_RA_MONITOR_PREFIX_CHANGED",
            )
        del row, original
    coverage.require_complete(
        opener_return_ns=opener["actual_opener_return_ns"],
        last_ack_ns=terminal["last_ack_ns"],
    )
    b.require(
        coverage.seq == terminal["last_seq"]
        and coverage.head == terminal["final_observation_sha256"]
        and coverage.inventory_sha256() == terminal["full_monitor_inventory_sha256"]
        and coverage.max_gap == terminal["max_gap_ns"],
        "B2_RA_MONITOR_PREFIX_CHANGED",
    )
    before = _signature((root / "originals").stat(follow_symlinks=False))
    entries = 0
    with os.scandir(root / "originals") as directory:
        for entry in directory:
            port.check_deadline()
            entries += 1
            b.require(
                entries <= selected["limits"]["monitor_rows"]
                and entry.name.endswith(".record")
                and entry.name[:-7] in allowed,
                "B2_RA_MONITOR_MEMBERSHIP_CHANGED",
            )
            digest = entry.name[:-7]
            monitor.read_original_observation(
                Path(entry.path),
                expected_sha256=digest,
                check=port.check_deadline,
                charge_read=port.charge_ra_original_read,
                test_only=port.test_only,
            )
            allowed.remove(digest)
    b.require(
        not allowed
        and _signature((root / "originals").stat(follow_symlinks=False)) == before,
        "B2_RA_MONITOR_MEMBERSHIP_CHANGED",
    )
    return phase_terminal


def verify_local_assurance(port, *, verify_inventory):
    from . import s12_ra_g1_assurance as assurance

    assurance.verify_runtime(
        port.ra_binding,
        port.authority,
        {"configuration_scope_sha256": authority_scope(port.config)},
    )
    if verify_inventory:
        actual = b.digest(port._actual_runtime_inventory(successor=True))
        b.require(
            actual == port.ra_binding["runtime_inventory_sha256"],
            "B2_RA_RUNTIME_INVENTORY",
        )
        previous = getattr(port, "ra_local_runtime_inventory_sha256", None)
        b.require(previous in (None, actual), "B2_RA_RUNTIME_INVENTORY")
        port.ra_local_runtime_inventory_sha256 = actual


def authority_scope(config):
    from . import s12_b2_runtime as runtime

    return runtime.scope_hash(config)


def bounded_source_digest(port, path, check):
    """4096-byte shared hash lease, all reads/EOF/failures charged before I/O."""
    from . import s12_wf_ap2_scratch as scratch

    path = Path(path)
    check()
    original = path.stat(follow_symlinks=False)
    b.require(
        stat.S_ISREG(original.st_mode) and not path.is_symlink(), "B2_RA_SOURCE_PATH"
    )
    h = hashlib.sha256()
    with scratch.ra_g1_lease("HASH"):
        buffer = bytearray(4096)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb", buffering=0) as stream:
            b.require(
                _signature(os.fstat(stream.fileno())) == _signature(original),
                "B2_RA_SOURCE_CHANGED",
            )
            while True:
                check()
                port.charge_ra_original_read(1, 4096)
                amount = stream.readinto(buffer)
                if not amount:
                    break
                h.update(memoryview(buffer)[:amount])
            b.require(
                _signature(os.fstat(stream.fileno()))
                == _signature(original)
                == _signature(path.stat(follow_symlinks=False)),
                "B2_RA_SOURCE_CHANGED",
            )
    check()
    return h.hexdigest()
