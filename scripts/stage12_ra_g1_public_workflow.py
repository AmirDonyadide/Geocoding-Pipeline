"""Persistent source-owned RA-G1 public setup, execution and terminal opening.

No submission, protected input, permission issuance or inferred review PASS.
The scheduled shell and this exact source share one non-reset processing epoch.
"""

from __future__ import annotations

# ruff: noqa: E402 -- record role entry before scientific/native imports.
import time

ROLE_ENTRY_NS = time.monotonic_ns()

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import stat
import sys
import threading

VERSION = "stage12_ra_g1_public_allocation_selection_v1"
SCOPE = "PUBLIC_SYNTHETIC_ONLY"
SOURCE_PROJECT_VERSION = "0.2.0"  # Exact reviewed pyproject.toml, not a fallback.
BOOTSTRAP = "stage12_ra_g1_public_bootstrap_v1"
MANIFEST = "stage12_ra_g1_public_bootstrap_manifest_v1"
WAIT = "stage12_ra_g1_public_supervisor_wait_v1"
EXACT = "stage12_ra_g1_public_exact_input_release_v1"
OUTCOME = "stage12_ra_g1_public_allocation_terminal_v1"
HANDOFF = "stage12_ra_g1_public_worker_final_prefix_v1"
HANDOFF_SUFFIX = dict(
    source_read_calls=2,
    source_read_bytes="ACTUAL_CANONICAL_HANDOFF_BYTES",
    identity_checks=3,
    write="ONE_EXCLUSIVE_8192_PRECHARGED_FULL_WRITE_READ_EOF_FSYNC",
    qualification="PENDING_GENUINE_WORKER_RETURN_AND_FRESH_VERIFIER_OPEN",
)
PATHS = set(
    "source records allocation_root output bootstrap binding configuration context review technical_review exact_release worker_return state outcome".split()
)
ROLES = (
    "owner",
    "operator",
    "policy_freeze",
    "selection",
    "transport",
    "size_allowance",
)
RECORDS = set(ROLES) | set(
    "adoption project_approval software_review resource_review representative_outcome representative_report representative_manifest template".split()
)
LIMITS = dict(
    processing_seconds=8160,
    scheduler_seconds=8400,
    active_seconds=7200,
    setup_seconds=840,
    review_seconds=600,
    binding_seconds=120,
    terminal_seconds=120,
    non_b_bytes=240 * 2**20,
    non_b_creations=1544,
    metadata_bytes=128 * 2**20,
    metadata_creations=1400,
    tail_bytes=96 * 2**20,
    tail_creations=128,
    log_bytes=16 * 2**20,
    log_creations=16,
    maximum_processes=4,
    maximum_utilities=256,
    maximum_python_invocations=5,
)


def need(value, code="RA_G1_PUBLIC_WORKFLOW_INVALID"):
    if not value:
        raise RuntimeError(code)


def canonical(value):
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def hashed(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    def pairs(items):
        need(len({key for key, _ in items}) == len(items), "RA_G1_FIELDS")
        return dict(items)

    value = json.loads(raw, object_pairs_hook=pairs)
    need(canonical(value) == raw, "RA_G1_CANONICAL_REQUIRED")
    return value


def identity(info):
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


def private(path):
    path = Path(path)
    need(path.is_absolute() and str(path) == os.path.abspath(path), "RA_G1_PATH")
    first = True
    for node in (path, *path.parents):
        info = node.lstat()
        need(
            stat.S_ISDIR(info.st_mode)
            and (
                not first
                or info.st_uid == os.geteuid()
                and stat.S_IMODE(info.st_mode) == 0o700
            ),
            "RA_G1_PATH",
        )
        first = False
    return identity(path.lstat())[:6]


def original(
    path, *, limit=4 * 2**20, check=lambda: None, charge=lambda calls, size: None
):
    path = Path(path)
    ancestors = private(path.parent)
    check()
    before = path.lstat()
    need(
        stat.S_ISREG(before.st_mode)
        and before.st_uid == os.geteuid()
        and stat.S_IMODE(before.st_mode) == 0o600
        and before.st_nlink == 1
        and 0 <= before.st_size <= limit,
        "RA_G1_ORIGINAL_CHANGED",
    )
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        need(identity(os.fstat(fd)) == identity(before), "RA_G1_ORIGINAL_CHANGED")
        data = bytearray()
        while True:
            check()
            charge(1, 0)
            block = os.read(fd, min(4096, limit + 1 - len(data)))
            charge(0, len(block))
            need(len(data) + len(block) <= limit, "RA_G1_READ_LIMIT")
            data.extend(block)
            if not block:
                break
        need(
            identity(before) == identity(os.fstat(fd)) == identity(path.lstat())
            and ancestors == private(path.parent),
            "RA_G1_ORIGINAL_CHANGED",
        )
        check()
        return bytes(data)
    finally:
        os.close(fd)


def ishash(value, size=64):
    return (
        type(value) is str
        and len(value) == size
        and set(value) <= set("0123456789abcdef")
        and set(value) != {"0"}
    )


def validate_selection(value):
    need(
        type(value) is dict
        and set(value)
        == set(
            "version scope source_sha intent_id task_id valid_from valid_until paths records source_files accounting accounting_inventory limits resource_selection_sha256".split()
        ),
        "RA_G1_FIELDS",
    )
    need(
        value["version"] == VERSION
        and value["scope"] == SCOPE
        and ishash(value["source_sha"], 40)
        and all(
            ishash(value[key])
            for key in ("intent_id", "task_id", "resource_selection_sha256")
        )
        and value["limits"] == LIMITS,
        "RA_G1_SELECTION_BINDING",
    )
    need(
        set(value["records"]) == RECORDS
        and all(ishash(v) for v in value["records"].values()),
        "RA_G1_AUTHORITY_REQUIRED",
    )
    need(
        set(value["accounting"])
        == set(
            "identity_calls original_read_calls original_read_bytes check_calls".split()
        )
        and all(type(v) is int and 0 < v < 2**64 for v in value["accounting"].values()),
        "RA_G1_ACCOUNTING",
    )
    paths = value["paths"]
    need(
        set(paths) == PATHS
        and len(set(paths.values())) == len(paths)
        and all(
            type(v) is str
            and Path(v).is_absolute()
            and str(Path(v)) == os.path.abspath(v)
            and len(v.encode()) <= 4096
            for v in paths.values()
        ),
        "RA_G1_PATH",
    )
    allocation, output = Path(paths["allocation_root"]), Path(paths["output"])
    need(
        output.name == "or2_" + value["task_id"]
        and output.parent == allocation.parent
        and not output.is_relative_to(allocation),
        "RA_G1_PATH",
    )
    for key in PATHS - {"source", "records", "allocation_root", "output"}:
        need(Path(paths[key]).is_relative_to(allocation), "RA_G1_PATH")
    need(
        type(value["source_files"]) is list
        and 1 <= len(value["source_files"]) <= 2048
        and [r["path"] for r in value["source_files"]]
        == sorted({r["path"] for r in value["source_files"]})
        and sum(r["bytes"] for r in value["source_files"]) <= 64 * 2**20,
        "RA_G1_SOURCE_INVENTORY",
    )
    for row in value["source_files"]:
        path = Path(row["path"])
        need(
            set(row) == {"path", "bytes", "sha256"}
            and not path.is_absolute()
            and ".." not in path.parts
            and 0 <= row["bytes"] <= 4 * 2**20
            and ishash(row["sha256"]),
            "RA_G1_SOURCE_INVENTORY",
        )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_ra_g1_accounting as accounting,
    )

    inv = accounting.validate_inventory(value["accounting_inventory"])
    need(
        inv["scope"] == SCOPE
        and inv["sources"] == value["source_files"]
        and inv["accounting"] == value["accounting"],
        "RA_G1_ACCOUNTING_CHANGED",
    )
    need(
        type(value["valid_from"]) is str
        and type(value["valid_until"]) is str
        and value["valid_from"] < value["valid_until"],
        "RA_G1_WINDOW",
    )
    return value


def load_builder(source):
    name = "stage12_prepare_ra_g1_public"
    spec = importlib.util.spec_from_file_location(
        name, Path(source) / "scripts" / (name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_launch_gate(selection, read):
    """Fresh prerequisite originals; callable before submission and again live."""
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as a

    root = Path(selection["paths"]["records"])

    def raw(role, suffix=".record"):
        value = read(root / (selection["records"][role] + suffix))
        need(hashed(value) == selection["records"][role], "RA_G1_AUTHORITY_CHANGED")
        return value

    outcome = parse(raw("representative_outcome"))
    a.shape(
        outcome,
        dict(
            schema_version="=stage12_ra_g1_representative_independent_outcome_v1",
            scope="=REPRESENTATIVE_NO_SERVICE",
            source_git_sha="G",
            selection_sha256="D",
            input_sha256="D",
            artifact_manifest_sha256="D",
            independent_report_sha256="D",
            disposition="=PASS_COMPLETE_REPRESENTATIVE",
            expected_attempts="=106",
            maximum_attempts="=107",
            scenarios_completed="=4",
            actual_reopening="B",
            sampling_and_monitor_coverage="=COMPLETE_SELECTED_SCOPE",
            authority_attribution="=INDEPENDENT_AGENT_OUTCOME_NOT_HUMAN_OR_OPERATOR",
        ),
    )
    report, manifest = (
        raw("representative_report", ".md"),
        raw("representative_manifest", ".manifest"),
    )
    need(
        outcome["source_git_sha"] == selection["source_sha"]
        and outcome["actual_reopening"] is True
        and outcome["independent_report_sha256"] == hashed(report)
        and outcome["artifact_manifest_sha256"] == hashed(manifest),
        "RA_G1_REPRESENTATIVE_RELEASE_REQUIRED",
    )
    return outcome, report, manifest


class ProviderGuard:
    """Reversible process-local provider/network gate; no kernel sandbox claim."""

    def __init__(self, source):
        self.source = str(source)
        self.opened = False
        self.closed = False
        self.utilities = 0

        def audit(event, args):
            if self.closed:
                return
            if event.startswith("socket.") and not self.opened:
                raise RuntimeError("RA_G1_PROVIDER_CLOSED")
            if event == "subprocess.Popen":
                argv = args[1]
                allowed = (
                    list(argv) == ["uname", "-p"]
                    or list(argv)
                    in (["git", "rev-parse", "HEAD"], ["git", "status", "--porcelain"])
                    and str(args[2]) == self.source
                )
                need(allowed, "RA_G1_PROCESS_DENIED")
                self.utilities += 1
                need(self.utilities <= 32, "RA_G1_UTILITY_LIMIT")
            elif event.startswith(("os.system", "os.exec", "os.spawn")):
                raise RuntimeError("RA_G1_PROCESS_DENIED")

        sys.addaudithook(audit)

    def provider(self, provider, *, released):
        need(released() is True and not self.opened, "RA_G1_PROVIDER_CLOSED")
        result = provider()
        self.opened = True
        return result

    def close(self):
        self.closed = True


class Run:
    def __init__(
        self,
        selection,
        selected,
        *,
        epoch_ns,
        role_entry_ns=ROLE_ENTRY_NS,
        terminal=False,
    ):
        from safe_geocoding_pipeline.preprocessing.stages.s12_ra_g1_source_counters import (
            SourceCounterLedger,
        )

        self.s = validate_selection(selection)
        self.selected = selected
        self.entry = role_entry_ns
        self.epoch = epoch_ns
        need(
            type(epoch_ns) is int
            and 0 <= epoch_ns <= role_entry_ns <= time.monotonic_ns(),
            "RA_G1_DEADLINE",
        )
        self.end = epoch_ns + 8160 * 10**9
        self.role_end = min(
            self.end, role_entry_ns + (120 if terminal else 840) * 10**9
        )
        self.ledger = SourceCounterLedger(
            selected,
            phase_id=14 if terminal else 13,
            maximum_identity_checks=selection["accounting"]["identity_calls"],
            maximum_original_read_calls=selection["accounting"]["original_read_calls"],
            maximum_original_read_bytes=selection["accounting"]["original_read_bytes"],
        )
        self.lock = threading.RLock()
        self.poisoned = False
        self.controls = None
        self.session = None
        self.non_b_bytes = self.non_b_creations = 0
        self.terminal = terminal
        self.released = False
        self.metadata_bytes = self.metadata_creations = 0
        self.log_bytes = self.log_creations = 0
        self.metadata_limit = (96 if terminal else 128) * 2**20
        self.creation_limit = 128 if terminal else 1400
        self.pool = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="ra-g1-public-metadata"
        )
        self.guard = ProviderGuard(selection["paths"]["source"])

    def check(self):
        self.ledger.checkpoint()
        need(
            not self.poisoned
            and time.monotonic_ns() < min(self.end, self.role_end)
            and self.s["valid_from"]
            <= datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            < self.s["valid_until"],
            "RA_G1_DEADLINE",
        )
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (
            1 if sys.platform == "darwin" else 1024
        )
        need(peak <= 768 * 2**20, "RA_G1_MONITOR_THRESHOLD")

    def read(self, path, limit=4 * 2**20):
        return original(
            path, limit=limit, check=self.check, charge=self.ledger.read_charge
        )

    def record_raw(self, role, suffix=".record"):
        raw = self.read(
            Path(self.s["paths"]["records"]) / (self.s["records"][role] + suffix)
        )
        need(hashed(raw) == self.s["records"][role], "RA_G1_AUTHORITY_CHANGED")
        return raw

    def record(self, role):
        return parse(self.record_raw(role))

    def capacity(self, size, creates):
        self.check()
        parent = Path(self.s["paths"]["allocation_root"])
        if not parent.exists():
            parent = parent.parent
        private(parent)
        v = os.statvfs(parent)
        need(
            v.f_frsize > 0
            and v.f_bavail * v.f_frsize >= 1342177280 + size
            and v.f_favail >= 4096 + creates,
            "RA_G1_SHARED_MARGIN",
        )

    def charge(self, size, creates=1):
        self.check()
        with self.lock:
            self.non_b_bytes += size
            self.non_b_creations += creates
            self.metadata_bytes += size
            self.metadata_creations += creates
            need(
                self.metadata_bytes <= self.metadata_limit
                and self.metadata_creations <= self.creation_limit
                and self.non_b_bytes <= 240 * 2**20
                and self.non_b_creations <= 1544,
                "RA_G1_METADATA_LIMIT",
            )
        if self.controls is not None:
            self.controls.reserve_components(size, creates)
        self.capacity(size, creates)

    def write(self, path, value):
        return self.write_raw(path, canonical(value))

    def write_raw(self, path, raw):
        need(type(raw) is bytes and len(raw) <= 4 * 2**20, "RA_G1_WRITE_LIMIT")
        path = Path(path)
        private(path.parent)
        self.charge(len(raw))

        def action():
            fd = os.open(
                path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            try:
                view = memoryview(raw)
                while view:
                    self.check()
                    n = os.write(fd, view)
                    need(n > 0, "RA_G1_WRITE_UNCERTAIN")
                    view = view[n:]
                os.fsync(fd)
            finally:
                os.close(fd)
            parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
            need(self.read(path) == raw, "RA_G1_WRITE_UNCERTAIN")

        try:
            self.pool.submit(action).result(
                timeout=min(
                    5,
                    max(0, (min(self.end, self.role_end) - time.monotonic_ns()) / 1e9),
                )
            )
        except BaseException:
            self.poisoned = True
            raise
        self.check()
        return hashed(raw)

    def mkdir(self, path):
        self.charge(0)
        Path(path).mkdir(mode=0o700)
        private(path)

    def sources(self):
        root = Path(self.s["paths"]["source"])
        private(root)
        for row in self.s["source_files"]:
            path = root / row["path"]
            for parent in (path.parent, *path.parent.parents):
                info = parent.lstat()
                need(
                    stat.S_ISDIR(info.st_mode) and not info.st_mode & 0o022,
                    "RA_G1_SOURCE_CHANGED",
                )
                if parent == root:
                    break
            self.check()
            before = path.lstat()
            need(
                stat.S_ISREG(before.st_mode)
                and not before.st_mode & 0o022
                and before.st_nlink == 1
                and before.st_size == row["bytes"],
                "RA_G1_SOURCE_CHANGED",
            )
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                need(identity(os.fstat(fd)) == identity(before), "RA_G1_SOURCE_CHANGED")
                h = hashlib.sha256()
                size = 0
                while True:
                    self.check()
                    self.ledger.read_charge(1, 0)
                    block = os.read(
                        fd, min(4096, row["bytes"] - size) if size < row["bytes"] else 1
                    )
                    self.ledger.read_charge(0, len(block))
                    size += len(block)
                    need(size <= row["bytes"], "RA_G1_SOURCE_CHANGED")
                    h.update(block)
                    if not block:
                        break
                need(
                    size == row["bytes"]
                    and h.hexdigest() == row["sha256"]
                    and identity(before)
                    == identity(os.fstat(fd))
                    == identity(path.lstat()),
                    "RA_G1_SOURCE_CHANGED",
                )
            finally:
                os.close(fd)

    def counters(self):
        from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_monitor as m

        need(self.controls is not None, "RA_G1_COUNTER_SOURCE_REQUIRED")
        usage = self.controls.snapshot()
        value = {role: usage["invocations"][role] for role in m.ROLES}
        value.update(
            self.ledger.snapshot_source(),
            application_write_reserved_bytes=usage["bytes"],
            application_creations_charged=usage["creations"],
            monitor_observations_charged=usage["monitor_rows"],
            monitor_write_bytes_charged=usage["monitor_bytes"],
            segment_attempts=0,
            root_attempts=0,
        )
        return value

    def monitor_charge(self, size, creates):
        self.check()
        self.controls.monitor_charge(size, creates)
        self.capacity(size, creates)

    def close(self):
        if self.session is not None and not self.session.completed:
            self.session.abort()
        self.guard.close()
        self.pool.shutdown(wait=False, cancel_futures=True)

    def reserve_logs(self):
        self.check()
        self.log_bytes, self.log_creations = 16 * 2**20, 16
        self.non_b_bytes += self.log_bytes
        self.non_b_creations += self.log_creations
        if self.controls is not None:
            self.controls.reserve_components(self.log_bytes, self.log_creations)
        self.capacity(self.log_bytes, self.log_creations)

    def final_handoff(self, config, summary):
        """Last worker source I/O; a successful suffix has exactly2reads/3checks."""
        self.charge(8192, 1)
        value = dict(
            schema_version=HANDOFF,
            scope=SCOPE,
            source_sha=self.s["source_sha"],
            selection_sha256=digest(self.s),
            intent_id=self.s["intent_id"],
            configuration_sha256=digest(config),
            summary_sha256=digest(summary),
            source_counter_prefix=self.ledger.snapshot_source(),
            application_usage=self.controls.snapshot(),
            non_b_bytes=self.non_b_bytes,
            non_b_creations=self.non_b_creations,
            post_prefix_contract=HANDOFF_SUFFIX,
        )
        raw = canonical(value)
        need(len(raw) <= 8192, "RA_G1_HANDOFF")
        path = Path(self.s["paths"]["allocation_root"]) / "worker_handoff.record"

        def action():
            self.check()
            fd = os.open(
                path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            try:
                need(os.write(fd, raw) == len(raw), "RA_G1_WRITE_UNCERTAIN")
                os.fsync(fd)
                self.check()
                os.lseek(fd, 0, os.SEEK_SET)
                self.ledger.read_charge(1, 0)
                actual = os.read(fd, 8192)
                self.ledger.read_charge(0, len(actual))
                need(actual == raw, "RA_G1_WRITE_UNCERTAIN")
                self.ledger.read_charge(1, 0)
                extra = os.read(fd, 1)
                self.ledger.read_charge(0, len(extra))
                need(
                    not extra and identity(os.fstat(fd)) == identity(path.lstat()),
                    "RA_G1_WRITE_UNCERTAIN",
                )
            finally:
                os.close(fd)
            parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
            self.check()

        try:
            self.pool.submit(action).result(
                timeout=min(5, max(0, (self.end - time.monotonic_ns()) / 1e9))
            )
        except BaseException:
            self.poisoned = True
            raise
        expected = derive_worker_prefix(value, len(raw))
        need(self.ledger.snapshot_source() == expected, "RA_G1_HANDOFF")
        return value


def derive_worker_prefix(handoff, raw_length):
    need(
        handoff["schema_version"] == HANDOFF
        and handoff["scope"] == SCOPE
        and handoff["post_prefix_contract"] == HANDOFF_SUFFIX
        and 0 < raw_length <= 8192,
        "RA_G1_HANDOFF",
    )
    prefix = handoff["source_counter_prefix"]
    need(
        set(prefix) == {"source_read_calls", "source_read_bytes", "identity_checks"}
        and all(type(v) is int and 0 <= v < 2**64 for v in prefix.values()),
        "RA_G1_HANDOFF",
    )
    return dict(
        source_read_calls=prefix["source_read_calls"] + 2,
        source_read_bytes=prefix["source_read_bytes"] + raw_length,
        identity_checks=prefix["identity_checks"] + 3,
    )


def wait_record(run, path, deadline):
    while not Path(path).exists():
        run.check()
        need(time.monotonic_ns() < deadline, "RA_G1_REVIEW_TIMEOUT")
        time.sleep(0.1)
    run.check()
    need(time.monotonic_ns() < deadline, "RA_G1_REVIEW_TIMEOUT")
    return parse(run.read(path))


def begin_setup(run):
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_execution as e
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as a
    from safe_geocoding_pipeline.preprocessing.stages.s12_ra_g1_public import (
        ApplicationControls,
    )

    run.controls = ApplicationControls(run.selected, check=run.check)
    # Every initial attempt remains charged to both finite ledgers.
    run.controls.reserve_components(run.non_b_bytes, run.non_b_creations)
    context = e.capture_supervisor_context(
        scope=SCOPE,
        source_git_sha=run.s["source_sha"],
        selection=run.selected,
        run_nonce=run.s["intent_id"],
        private_paths=dict(
            allocation_root=run.s["paths"]["allocation_root"],
            resource_evidence_root=run.s["paths"]["output"],
            scratch_root=run.s["paths"]["allocation_root"],
        ),
        supervisor_pid=os.getppid(),
        check=run.check,
        read_charge=run.ledger.read_charge,
    )
    process, parent = e._process_identity(
        os.getpid(), check=run.check, read_charge=run.ledger.read_charge
    )
    need(parent == context["supervisor"]["pid"], "RA_G1_PROCESS_SCOPE")
    risk = dict(
        schema_version=a.RISK,
        scope=SCOPE,
        method=a.METHOD,
        policy_sha256=run.selected["policy_sha256"],
        adoption_sha256=run.selected["adoption_sha256"],
        entries=[
            dict(
                risk=kind,
                observation_scope="GUARDED_ADMINISTRATIVE_SUFFIX"
                if kind == "UNMONITORED_ADMINISTRATIVE_SUFFIX"
                else "NOT_OBSERVABLE",
                control="FINITE_GUARDED_SUFFIX"
                if kind == "UNMONITORED_ADMINISTRATIVE_SUFFIX"
                else "EXPLICIT_ACCEPTED_UNKNOWN",
                maximum="NOT_PROVEN",
                evidence_sha256=run.selected["adoption_sha256"],
            )
            for kind in a.RISKS
        ],
        native_maximum="NOT_PROVEN",
        physical_maximum="NOT_PROVEN",
        complete_descendant_coverage="NOT_ESTABLISHED",
    )
    a.validate_risk_inventory(risk)
    binding = dict(
        schema_version=e.ADMIN_BINDING,
        scope=SCOPE,
        method=a.METHOD,
        role="PUBLIC_SETUP",
        phase_id=13,
        source_git_sha=run.s["source_sha"],
        selection_sha256=digest(run.selected),
        adoption_sha256=run.selected["adoption_sha256"],
        supervisor_context_sha256=digest(context),
        risk_inventory_sha256=digest(risk),
        process_pid=process["pid"],
        process_start_ticks=process["start_ticks"],
        process_uid=process["uid"],
        scope_start_mono_ns=run.entry,
        deadline_mono_ns=run.role_end,
        service_authority="DENIED",
        protected_input_authority="DENIED",
        ap_dispatch_authority="DENIED",
    )
    run.session = e.start_administrative_session(
        binding=binding,
        selection=run.selected,
        evidence_root=Path(run.s["paths"]["allocation_root"])
        / "public_setup_resources",
        pids=(os.getpid(), parent),
        cgroup_path=Path(context["visible_cgroup_path"]),
        counters=run.counters,
        charge=run.monitor_charge,
        check=run.check,
        read_charge=run.ledger.read_charge,
        scope_start_ns=run.entry,
        deadline_ns=run.role_end,
    )
    run.write(run.s["paths"]["context"], context)
    run.write(run.session.root / "admin_binding.record", binding)
    run.write(run.session.root / "administrative_risk.record", risk)
    return context


def collect_bootstrap(run, context):
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as a
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_runtime as runtime,
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_response as response,
    )

    run.sources()
    outcome, report, manifest = verify_launch_gate(run.s, run.read)
    facts, kernel = a.observe_current_facts(
        check=run.check, read_charge=run.ledger.read_charge
    )
    a.validate_environment_originals(facts, kernel)
    method = dict(method="CURRENT_STATVFS_SHARED_SNAPSHOT_NOT_RESERVATION")
    restrictions = dict(known="SITE_PROJECT_RULES_PRESERVED", unknown="NOT_ESTABLISHED")
    cap, raw = a.observe_capacity(
        run.s["paths"]["allocation_root"],
        scope=SCOPE,
        selection_sha256=digest(run.selected),
        owner_reported_approval_sha256=run.s["records"]["project_approval"],
        accounting_method_sha256=digest(method),
        restrictions_inventory_sha256=digest(restrictions),
        observed_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    )
    a.check_capacity(cap, next_write_bytes=240 * 2**20, next_creations=1544)
    inventory = runtime.runtime_inventory(
        digest(response.descriptor(response.CORPUS_VERSION)),
        successor=True,
        resource_assurance="RA-G1-r1",
        environment_observation_sha256=digest(facts),
        backend_reader=a.bounded_backend_reader(run.ledger.read_charge),
        check=run.check,
    )
    payload = dict(
        schema_version=BOOTSTRAP,
        source_sha=run.s["source_sha"],
        scope=SCOPE,
        job_id=os.environ["SLURM_JOB_ID"],
        created_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        resource_selection_sha256=digest(run.selected),
        facts=facts,
        kernel_originals=kernel,
        capacity=cap,
        capacity_originals=raw,
        capacity_method=method,
        capacity_restrictions=restrictions,
        runtime_inventory=inventory,
        resource_execution=dict(
            schema_version="stage12_resource_execution_request_ra_g1_v1",
            supervisor_context_path=run.s["paths"]["context"],
            supervisor_context_sha256=digest(context),
        ),
    )
    run.mkdir(run.s["paths"]["bootstrap"])
    root = Path(run.s["paths"]["bootstrap"])
    sha = run.write(root / "bootstrap.record", payload)
    retained = dict(
        schema_version=MANIFEST,
        scope=SCOPE,
        source_sha=run.s["source_sha"],
        bootstrap_sha256=sha,
        representative_outcome_sha256=digest(outcome),
        source_counter_prefix=run.ledger.snapshot_source(),
    )
    run.write(root / "manifest.record", retained)
    payload["manifest_sha256"] = digest(retained)
    return payload, (outcome, report, manifest)


def worker(run):
    from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm

    require_goethe_nhr_slurm("stage12 reviewed RA-G1 public persistent workflow")
    need(sys.platform == "linux", "RA_G1_EXECUTION_SITE")
    run.capacity(240 * 2**20, 1544)
    run.mkdir(run.s["paths"]["allocation_root"])
    run.reserve_logs()
    run.charge(0)
    os.mkfifo(
        Path(run.s["paths"]["allocation_root"]) / "supervisor_wait.fifo", mode=0o600
    )
    context = begin_setup(run)
    bootstrap, representative = collect_bootstrap(run, context)
    builder = load_builder(run.s["paths"]["source"])
    review_deadline = min(run.role_end, time.monotonic_ns() + 600 * 10**9)
    bootstrap_review = wait_record(run, run.s["paths"]["review"], review_deadline)
    need(
        bootstrap_review.get("selection_sha256") == digest(run.s),
        "RA_G1_BOOTSTRAP_REVIEW_REQUIRED",
    )
    software = run.record("software_review")
    implementation_report = run.read(
        Path(run.s["paths"]["records"]) / (software["report_sha256"] + ".md")
    )
    need(
        hashed(implementation_report) == software["report_sha256"]
        and software["source_sha"] == run.s["source_sha"]
        and software["disposition"] == "PASS",
        "RA_G1_SOFTWARE_REVIEW_REQUIRED",
    )
    prepared = builder.prepare(
        run.record_raw("template", ".json"),
        run.s,
        bootstrap,
        role_originals={role: run.record_raw(role) for role in ROLES},
        source_files=[dict(row) for row in run.s["source_files"]],
        implementation_report=implementation_report,
        adoption=run.record("adoption"),
        project_approval=run.record("project_approval"),
        resource_review=run.record("resource_review"),
        independent_bootstrap_review=bootstrap_review,
        representative_outcome=representative[0],
        representative_report=representative[1],
        representative_manifest=representative[2],
    )
    need(
        digest(prepared["resource_selection"]) == run.s["resource_selection_sha256"],
        "RA_G1_SELECTION_BINDING",
    )
    run.write(
        Path(run.s["paths"]["bootstrap"]) / "bound_subject.record",
        prepared["bound_subject"],
    )
    technical = wait_record(run, run.s["paths"]["technical_review"], review_deadline)
    binding_deadline = min(run.role_end, time.monotonic_ns() + 120 * 10**9)
    result = builder.finalize(prepared, technical, issued=True)
    run.ledger.constrain(result["binding"])
    bundle = Path(run.s["paths"]["binding"])
    run.mkdir(bundle)
    run.mkdir(bundle / "resource_evidence")
    for values in result["resource_evidence"].values():
        for identity_value, value in values.items():
            path = bundle / "resource_evidence" / (identity_value + ".record")
            if path.exists():
                need(run.read(path) == canonical(value), "RA_G1_ORIGINAL_CHANGED")
            else:
                run.write(path, value)
    for name, raw in result["representative_originals"].items():
        run.write_raw(bundle / "resource_evidence" / name, raw)
    for role, raw in result["role_originals"].items():
        run.write_raw(bundle / (role + ".record"), raw)
    run.write_raw(bundle / "integration_review.md", result["integration_report"])
    run.write(bundle / "integration_review.binding.json", result["integration_review"])
    run.write(run.s["paths"]["configuration"], result["configuration"])
    release = wait_record(
        run, run.s["paths"]["exact_release"], min(review_deadline, binding_deadline)
    )
    validate_release(release, run.s, result, bootstrap_review)
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_runtime as runtime,
    )
    from safe_geocoding_pipeline.preprocessing.stages import s12_transport as transport

    runtime.validate_config(result["configuration"])

    def setup_opener():
        run.sources()
        retained_bootstrap = dict(bootstrap)
        retained_bootstrap.pop("manifest_sha256")
        need(
            parse(run.read(Path(run.s["paths"]["bootstrap"]) / "bootstrap.record"))
            == retained_bootstrap
            and digest(
                parse(run.read(Path(run.s["paths"]["bootstrap"]) / "manifest.record"))
            )
            == bootstrap["manifest_sha256"],
            "RA_G1_ORIGINAL_CHANGED",
        )
        need(
            parse(run.read(run.s["paths"]["review"])) == bootstrap_review
            and parse(run.read(run.s["paths"]["technical_review"])) == technical,
            "RA_G1_EXACT_INPUT_REVIEW_REQUIRED",
        )
        need(
            parse(run.read(run.s["paths"]["configuration"])) == result["configuration"],
            "RA_G1_ORIGINAL_CHANGED",
        )
        need(
            parse(run.read(run.s["paths"]["exact_release"])) == release,
            "RA_G1_EXACT_INPUT_REVIEW_REQUIRED",
        )
        verify_launch_gate(run.s, run.read)
        for values in result["resource_evidence"].values():
            for identity_value, value in values.items():
                need(
                    parse(
                        run.read(
                            bundle / "resource_evidence" / (identity_value + ".record")
                        )
                    )
                    == value,
                    "RA_G1_ORIGINAL_CHANGED",
                )
        runtime.validate_config(parse(run.read(run.s["paths"]["configuration"])))
        return result["configuration"]

    run.released = True

    def key_provider():
        run.check()
        return run.guard.provider(
            transport.Secret.runtime,
            released=lambda: run.released and run.session.protocol.state == "OPENING",
        )

    run.role_end = run.end
    summary = runtime.execute(
        result["configuration"],
        bundle=bundle,
        review=result["integration_review"],
        review_hash=digest(result["integration_review"]),
        repository=Path(run.s["paths"]["source"]),
        git_sha=run.s["source_sha"],
        key_provider=key_provider,
        source_counter_ledger=run.ledger,
        allocation_controls=run.controls,
        setup_session=run.session,
        setup_opener=setup_opener,
        processing_deadline_ns=run.end,
    )
    need(
        summary["full_frozen_capability_matrix_completed"] is True
        and summary["diagnostic_persistence_complete"] is True,
        "RA_G1_PUBLIC_INCOMPLETE",
    )
    run.final_handoff(result["configuration"], summary)
    return summary


def validate_release(release, selection, result, bootstrap_review):
    need(
        set(release)
        == set(
            "schema_version disposition selection_sha256 source_sha configuration_sha256 review_binding_sha256 bootstrap_review_sha256 technical_review_sha256 resource_selection_sha256".split()
        )
        and release["schema_version"] == EXACT
        and release["disposition"] == "PASS"
        and release["selection_sha256"] == digest(selection)
        and release["source_sha"] == selection["source_sha"]
        and release["configuration_sha256"] == digest(result["configuration"])
        and release["review_binding_sha256"] == digest(result["integration_review"])
        and release["bootstrap_review_sha256"] == digest(bootstrap_review)
        and release["technical_review_sha256"]
        == result["binding"]["technical_review_sha256"]
        and release["resource_selection_sha256"]
        == selection["resource_selection_sha256"],
        "RA_G1_EXACT_INPUT_REVIEW_REQUIRED",
    )


def validate_wait(value, selection, context, expected_worker_pid):
    need(
        set(value)
        == set(
            "version source_sha selection_sha256 supervisor_pid pid exit_code wait_status observed_mono_ns_lower".split()
        )
        and value["version"] == WAIT
        and value["source_sha"] == selection["source_sha"]
        and value["selection_sha256"] == digest(selection)
        and value["supervisor_pid"] == context["supervisor"]["pid"]
        and type(value["pid"]) is int
        and value["pid"] == expected_worker_pid
        and type(value["exit_code"]) is int
        and value["exit_code"] == 0
        and type(value["wait_status"]) is int
        and value["wait_status"] == 0
        and type(value["observed_mono_ns_lower"]) is int,
        "RA_G1_GENUINE_PUBLIC_RETURN_REQUIRED",
    )


def verifier(run):
    from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm

    require_goethe_nhr_slurm("stage12 RA-G1 public guarded terminal verifier")
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_execution as e
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_monitor as m
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as a

    run.sources()
    verify_launch_gate(run.s, run.read)
    context = parse(run.read(run.s["paths"]["context"]))
    waited = parse(run.read(run.s["paths"]["worker_return"]))
    setup_binding = parse(
        run.read(
            Path(run.s["paths"]["allocation_root"])
            / "public_setup_resources"
            / "admin_binding.record"
        )
    )
    a.shape(setup_binding, e.ADMIN_BINDING_SCHEMA)
    validate_wait(waited, run.s, context, setup_binding["process_pid"])
    child = dict(
        pid=waited["pid"],
        wait_status=waited["wait_status"],
        acquired_mono_ns=time.monotonic_ns(),
    )
    need(
        run.epoch <= waited["observed_mono_ns_lower"] <= child["acquired_mono_ns"],
        "RA_G1_GENUINE_PUBLIC_RETURN_REQUIRED",
    )
    config = parse(run.read(run.s["paths"]["configuration"]))
    output = Path(run.s["paths"]["output"])
    summary = parse(run.read(output / "diagnostic_summary.json"))
    reconciliation = parse(run.read(output / "matrix_reconciliation.json"))
    need(
        summary["full_frozen_capability_matrix_completed"] is True
        and summary["diagnostic_persistence_complete"] is True
        and reconciliation["data_observations"] == 576
        and reconciliation["control_exchanges"] == 8
        and reconciliation["same_size_comparisons"] == 288
        and reconciliation["cross_size_comparisons"] == 1024
        and summary["completed_phases"]
        == [item["label"] for item in config["campaigns"]]
        and reconciliation["actual_attempts"]
        == summary["attempts_dispatched_or_uncertain"]
        and 584 <= summary["attempts_dispatched_or_uncertain"] <= 2960,
        "RA_G1_PUBLIC_INCOMPLETE",
    )
    rows = summary["resource_sessions"]
    need(
        len(rows) == 13 and {r["phase_id"] for r in rows} == set(range(1, 14)),
        "RA_G1_PUBLIC_MONITOR_COVERAGE",
    )
    counters = summary["resource_counters"]
    a.shape(counters, {key: "U" for key in m.COUNTERS})
    handoff_raw = run.read(
        Path(run.s["paths"]["allocation_root"]) / "worker_handoff.record", 8192
    )
    handoff = parse(handoff_raw)
    need(
        set(handoff)
        == set(
            "schema_version scope source_sha selection_sha256 intent_id configuration_sha256 summary_sha256 source_counter_prefix application_usage non_b_bytes non_b_creations post_prefix_contract".split()
        )
        and handoff["source_sha"] == run.s["source_sha"]
        and handoff["selection_sha256"] == digest(run.s)
        and handoff["intent_id"] == run.s["intent_id"]
        and handoff["configuration_sha256"] == digest(config)
        and handoff["summary_sha256"] == digest(summary),
        "RA_G1_HANDOFF",
    )
    worker_prefix = derive_worker_prefix(handoff, len(handoff_raw))
    need(
        all(worker_prefix[key] >= counters[key] for key in worker_prefix),
        "RA_G1_HANDOFF",
    )
    run.ledger.add_verified_prefix(worker_prefix)
    from safe_geocoding_pipeline.preprocessing.stages.s12_ra_g1_public import (
        ApplicationControls,
    )

    run.controls = ApplicationControls(
        run.selected, check=run.check, initial_usage=handoff["application_usage"]
    )
    need(
        type(handoff["non_b_bytes"]) is int
        and 0 <= handoff["non_b_bytes"] <= 144 * 2**20
        and type(handoff["non_b_creations"]) is int
        and 0 <= handoff["non_b_creations"] <= 1416,
        "RA_G1_HANDOFF",
    )
    run.non_b_bytes += handoff["non_b_bytes"]
    run.non_b_creations += handoff["non_b_creations"]
    run.write(Path(run.s["paths"]["allocation_root"]) / "child_result.record", child)
    bundle = Path(run.s["paths"]["binding"])
    evidence = bundle / "resource_evidence"
    bound = parse(
        run.read(
            evidence
            / (
                config["campaigns"][0]["profile"]["sampling_runtime_bound_sha256"]
                + ".record"
            )
        )
    )
    need(
        digest(bound)
        == config["campaigns"][0]["profile"]["sampling_runtime_bound_sha256"],
        "RA_G1_BOUND_CHANGED",
    )
    run.ledger.constrain(bound)
    e.validate_current_supervisor(
        context,
        binding=bound,
        selection=run.selected,
        evidence_root=output,
        check=run.check,
        read_charge=run.ledger.read_charge,
    )
    reports = []
    for row in rows:
        run.check()
        root = Path(row["root"])
        expected = (
            Path(run.s["paths"]["allocation_root"]) / "public_setup_resources"
            if row["phase_id"] == 13
            else output
            / (config["campaigns"][row["phase_id"] - 1]["label"] + "_resources")
            if row["phase_id"] <= 11
            else output / "whole_task_resources"
        )
        need(root == expected, "RA_G1_PATH")
        binding = (
            parse(run.read(root / "admin_binding.record"))
            if row["phase_id"] == 13
            else bound
        )
        if row["phase_id"] == 13:
            a.shape(binding, e.ADMIN_BINDING_SCHEMA)
        else:
            a.shape(binding, a.SCHEMA)
        need(
            binding["selection_sha256"] == digest(run.selected)
            and binding["source_git_sha"] == run.s["source_sha"],
            "RA_G1_SELECTION_BINDING",
        )
        originals = {
            name: parse(run.read(root / (name + ".record")))
            for name in (
                "preopening",
                "opener_return",
                "monitor_terminal",
                "worker_validation",
            )
        }
        need(
            all(originals[name] == row["records"][name] for name in originals),
            "RA_G1_ORIGINAL_CHANGED",
        )
        if row["phase_id"] == 12:
            need(
                originals["opener_return"]["frozen_data_inventory_sha256"]
                == digest(
                    dict(
                        reconciliation=reconciliation,
                        timing=summary["public_path_timing"],
                    )
                ),
                "RA_G1_ORIGINAL_CHANGED",
            )
        start, end = row["phase_start_ns"], row["phase_deadline_ns"]
        selected_stage = next(
            x for x in run.selected["limits"]["stages"] if x["id"] == row["phase_id"]
        )
        need(
            run.epoch <= start < end <= run.end
            and end <= start + selected_stage["deadline_ms"] * 10**6
            and originals["worker_validation"]["first_pass_end_ns"] < end,
            "RA_G1_DEADLINE",
        )
        protocol = m.reopen_phase_protocol(
            binding_sha256=digest(binding),
            selection_sha256=digest(run.selected),
            phase_id=row["phase_id"],
            closure=originals["preopening"],
            opener_return=originals["opener_return"],
            monitor_terminal=originals["monitor_terminal"],
            deadline_ns=run.role_end,
            check=run.check,
        )
        seed = digest(
            dict(
                schema_version="stage12_resource_monitor_seed_ra_g1_v1",
                binding_sha256=digest(binding),
                selection_sha256=digest(run.selected),
                phase_id=row["phase_id"],
            )
        )

        def persist(value, check):
            check()
            path = root / "supervisor_terminal.record"
            run.write(path, value)
            return parse(run.read(path))

        reports.append(
            m.verify_tail(
                protocol=protocol,
                monitor_path=root / "observations.bin",
                selected=run.selected,
                seed_sha256=seed,
                child_result={
                    key: child[key]
                    for key in ("pid", "wait_status", "acquired_mono_ns")
                },
                genuine_wait_status=child["wait_status"],
                expected_child_pid=child["pid"],
                current_counter_sha256=lambda: digest(
                    dict(worker=counters, verifier=run.ledger.snapshot_source())
                ),
                persist_terminal=persist,
                original_observation_reader=lambda identity_value: (
                    m.read_original_observation(
                        root / "originals" / (identity_value + ".record"),
                        expected_sha256=identity_value,
                        check=run.check,
                        charge_read=run.ledger.read_charge,
                    )
                ),
                worker_validation=originals["worker_validation"],
                charge_read=run.ledger.read_charge,
            )
        )
    run.check()
    outcome = dict(
        schema_version=OUTCOME,
        scope=SCOPE,
        source_sha=run.s["source_sha"],
        selection_sha256=digest(run.s),
        configuration_sha256=digest(config),
        summary_sha256=digest(summary),
        reconciliation_sha256=digest(reconciliation),
        supervisor_wait_sha256=digest(waited),
        child_result_sha256=digest(child),
        phase_terminal_sha256=[digest(r) for r in reports],
        source_counter_prefix=run.ledger.snapshot_source(),
        worker_handoff_sha256=hashed(handoff_raw),
        derived_worker_final_source_counters=worker_prefix,
        cumulative_application_usage=run.controls.snapshot(),
        status="COMPLETE_PUBLIC_SELECTED_SCOPE",
        native_maximum="NOT_PROVEN",
        physical_maximum="NOT_PROVEN",
        scientific_N="UNSELECTED",
        actual_python_roles=dict(
            PHASE_RUNNER=1, TERMINAL_VERIFIER=1, COLLECTOR=0, BINDER=0, MONITOR=0
        ),
        post_prefix_contract="OWN_EXCLUSIVE_WRITE_FULL_READBACK_EOF_AND_GUARDS_REQUIRE_GENUINE_VERIFIER_ZERO_RETURN",
    )
    run.write(run.s["paths"]["outcome"], outcome)
    run.check()
    return outcome


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("worker", "verify"))
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--selection-sha256", required=True)
    parser.add_argument("--resource-selection", type=Path, required=True)
    args = parser.parse_args(argv)
    run = None
    try:
        early = {"source_read_calls": 0, "source_read_bytes": 0, "identity_checks": 0}

        def early_check():
            early["identity_checks"] += 1
            need(
                time.monotonic_ns() - ROLE_ENTRY_NS
                < (120 if args.command == "verify" else 840) * 10**9,
                "RA_G1_DEADLINE",
            )

        def charge(calls, size):
            early["source_read_calls"] += calls
            early["source_read_bytes"] += size

        raw = original(args.selection, check=early_check, charge=charge)
        need(hashed(raw) == args.selection_sha256, "RA_G1_SELECTION_CHANGED")
        parsed = parse(raw)
        early_check()
        own_checkout = Path(__file__).resolve().parents[1]
        need(
            parsed.get("paths", {}).get("source") == str(own_checkout),
            "RA_G1_SOURCE_CHANGED",
        )
        sys.path.insert(0, str(own_checkout / "src"))
        early_check()
        from importlib.metadata import PackageNotFoundError

        try:
            import safe_geocoding_pipeline as project
        except PackageNotFoundError:
            raise RuntimeError("RA_G1_PROJECT_DISTRIBUTION_REQUIRED") from None

        own_package = own_checkout / "src" / "safe_geocoding_pipeline"
        need(
            project.__version__ == SOURCE_PROJECT_VERSION
            and project.DISTRIBUTION_NAME == "safe-geocoding-pipeline"
            and Path(project.__file__).resolve(strict=True)
            == own_package / "__init__.py"
            and [Path(path).resolve(strict=True) for path in project.__path__]
            == [own_package],
            "RA_G1_PROJECT_DISTRIBUTION_INCOMPATIBLE",
        )
        early_check()
        s = validate_selection(parsed)
        selected = parse(
            original(
                args.resource_selection, limit=65536, check=early_check, charge=charge
            )
        )
        need(
            digest(selected) == s["resource_selection_sha256"],
            "RA_G1_SELECTION_BINDING",
        )
        epoch = os.environ.get("STAGE12_RA_EPOCH_NS")
        need(epoch is not None and epoch.isdecimal(), "RA_G1_EPOCH_REQUIRED")
        run = Run(s, selected, epoch_ns=int(epoch), terminal=args.command == "verify")
        run.ledger.read_charge(early["source_read_calls"], early["source_read_bytes"])
        for _ in range(early["identity_checks"]):
            run.ledger.checkpoint()
        result = worker(run) if args.command == "worker" else verifier(run)
        print(
            canonical(
                dict(
                    status="PUBLIC_WORKER_RETURNED_PENDING_GENUINE_WAIT"
                    if args.command == "worker"
                    else result["status"],
                    source_sha=s["source_sha"],
                    scope=SCOPE,
                )
            ).decode(),
            end="",
        )
        return 0
    except BaseException as error:
        if (
            type(error) is RuntimeError
            and len(error.args) == 1
            and type(error.args[0]) is str
            and error.args[0]
            in (
                "RA_G1_PROJECT_DISTRIBUTION_REQUIRED",
                "RA_G1_PROJECT_DISTRIBUTION_INCOMPATIBLE",
            )
        ):
            print(error.args[0])
        print(
            "STAGE12_RA_G1_PUBLIC_WORKFLOW_FAILED; immutable controlled evidence retained"
        )
        return 2
    finally:
        if run is not None:
            run.close()


if __name__ == "__main__":
    raise SystemExit(main())
