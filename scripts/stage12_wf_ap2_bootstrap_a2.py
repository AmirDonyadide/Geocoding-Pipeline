"""A-BE1: bounded best-effort metadata bootstrap, never a B release path."""

from __future__ import annotations

import argparse
from concurrent.futures import Future, TimeoutError as FutureTimeout
import importlib.util
import os
from pathlib import Path
import queue
import resource
import stat
import sys
import threading
import time

STARTED_NS = time.monotonic_ns()
ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "a2_strict_original", ROOT / "scripts/stage12_wf_ap2_allocation.py"
)
s = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(s)

VERSION = "stage12_bootstrap_a2_selection_v1"
VERSION2 = "stage12_bootstrap_a2_selection_v2"
ACCOUNTING_ASSET = "docs/scientific_assets/stage12_a2_accounting_v1.json"
ACCOUNTING_SOURCE = "src/safe_geocoding_pipeline/preprocessing/stages/s12_a2_accounting.py"
_ACTIVE_LEDGER = None
OWNER = "stage12_bootstrap_a2_owner_reported_v1"
SCOPE = "WF_AP2_BOOTSTRAP_A_ONLY_NO_SERVICE"
COLLECTED = "A2_ORIGINAL_METADATA_COLLECTED_B_DISABLED"
FINALIZED = "A2_STRUCTURAL_CLOSURE_B_DISABLED"
ASSET = "docs/scientific_assets/stage12_wf_ap2_bootstrap_a2_policy_v1.json"
REQUIRED = s.REQUIRED_SOURCE_FILES | {
    "scripts/stage12_wf_ap2_bootstrap_a2.py",
    "cluster/goethe_nhr/stage12_wf_ap2_bootstrap_a2.sbatch",
    ASSET,
}
POLICY = {
    "version": "stage12_bootstrap_a_best_effort_policy_v1",
    "scope": SCOPE,
    "assurance": "OWNER_REPORTED_APPROVAL_BOUNDED_BEST_EFFORT",
    "manager_authority_independently_verified": "NOT_CLAIMED",
    "physical_capacity_or_entitlement": "NOT_GUARANTEED",
    "strict_capacity_policy": "PRESERVED_SEPARATELY",
    "B": "DISABLED",
    "limits": {
        "stages": {
            k: dict(zip(("seconds", "bytes", "creations"), v))
            for k, v in s.STAGES.items()
            if k != "B"
        },
        "logs_bytes": 16 * 2**20,
        "logs_creations": 8,
        "non_B_bytes": 240 * 2**20,
        "non_B_creations": 1544,
        "whole_seconds": 8160,
        "scheduler_seconds": 8400,
        "writer_guard_ms": 5000,
        "rss_bytes": 768 * 2**20,
        "native_threads": 256,
        "Python_invocations": 3,
        "utility_invocations": 256,
    },
    "filesystem_check": "FRESH_SHARED_SNAPSHOT_AND_EXACT_PRIVATE_PATH_ONLY",
    "unknown_physical_rounding": "BEST_EFFORT_RISK_NOT_A_BOUND",
    "stop": [
        "UNUSABLE_ACCOUNTING",
        "UNSAFE_PATH",
        "EXHAUSTED_BUDGET",
        "QUOTA_OR_SPACE_ERROR",
        "UNCERTAIN_IO",
        "INCOMPLETE_INVENTORY",
        "MISSING_OR_LATE_REVIEW",
        "DEADLINE",
    ],
}
POLICY_SHA = s.digest(POLICY)


def need(value, code="A2_INVALID"):
    s.need(value, code)


def selection_scope(value):
    copy = dict(value)
    copy.pop("owner_sha256")
    return s.digest(copy)


def validate_selection(value):
    s.fields(
        value,
        (
            "version",
            "scope",
            "policy_sha256",
            "source_sha",
            "source_files",
            "paths",
            "owner_sha256",
            "implementation_review_sha256",
            "valid_from",
            "valid_until",
            "limits",
            "B",
        ) + (("accounting_inventory",) if value.get("version") == VERSION2 else ()),
    )
    need(
        value["version"] in (VERSION, VERSION2)
        and value["scope"] == SCOPE
        and value["policy_sha256"] == POLICY_SHA
        and value["B"] == "DISABLED"
    )
    need(s.canonical(value["limits"]) == s.canonical(POLICY["limits"]))
    for key in ("owner_sha256", "implementation_review_sha256"):
        need(s.hash_value(value[key]))
    need(s.hash_value(value["source_sha"], 40))
    need(s.utc(value["valid_from"]) < s.utc(value["valid_until"]))
    paths = value["paths"]
    s.fields(
        paths,
        (
            "source",
            "records",
            "bootstrap",
            "review",
            "collector_ack",
            "final",
            "outcome",
        ),
    )
    need(len(set(paths.values())) == len(paths))
    import re

    for name, text in paths.items():
        need(type(text) is str and re.fullmatch(r"/[A-Za-z0-9_./-]+", text))
        path = Path(text)
        need(path.is_absolute() and ".." not in path.parts)
        expected = s.PROJECT / "integration_stage12" if name == "source" else s.PARENT
        if name in ("review", "collector_ack"):
            expected = Path(paths["records"])
        need(path.parent == expected, "A2_PATH")
    need(
        Path(paths["review"]).name == "a2_review.json"
        and Path(paths["collector_ack"]).name == "collector_ack.json"
    )
    rows = value["source_files"]
    need(type(rows) is list and 1 <= len(rows) <= 128)
    names = []
    for row in rows:
        s.fields(row, ("path", "sha256"))
        path = Path(row["path"])
        need(
            not path.is_absolute()
            and ".." not in path.parts
            and path.parts[0] in ("src", "scripts", "cluster", "docs")
            and s.hash_value(row["sha256"])
            and row["path"] != s.REPLAY
        )
        names.append(row["path"])
    need(names == sorted(set(names)) and REQUIRED <= set(names), "A2_SOURCE_SET")
    if value["version"] == VERSION2:
        from safe_geocoding_pipeline.preprocessing.stages import s12_a2_accounting as accounting
        need(accounting.ORIGINAL_READ_BYTES == s.MAX_READ, "A2_ACCOUNTING_READER_VERSION")
        need({ACCOUNTING_SOURCE, ACCOUNTING_ASSET} <= set(names), "A2_ACCOUNTING_SOURCE_SET")
        descriptor = s.parse(s.original(ROOT / ACCOUNTING_ASSET, private=False))
        need(descriptor["source_paths"] == names, "A2_ACCOUNTING_SOURCE_SET")
        accounting.validate(value["accounting_inventory"], rows)


def verify_source(value, check=lambda: None, *, ledger=None, root=None):
    if ledger is not None:
        return ledger.sources(value, check, root)
    return s.verify_source(value, check)


def load_selection(path, token):
    raw = s.original(path)
    need(s.sha(raw) == token, "A2_SELECTION_CHANGED")
    value = s.parse(raw)
    validate_selection(value)
    return value


def owner(value, records, now):
    s.check_window(value, now)
    row = records.get(value["owner_sha256"])
    s.fields(
        row,
        (
            "version",
            "scope",
            "source_sha",
            "selection_scope_sha256",
            "approval_source_sha256",
            "approval_type",
            "manager_approval_reported",
            "administrator_attestation",
            "maximum_allocations",
            "B",
            "independent_reviewer",
            "valid_from",
            "valid_until",
        ),
    )
    need(row["version"] == OWNER and row["scope"] == SCOPE)
    need(
        row["source_sha"] == value["source_sha"]
        and row["selection_scope_sha256"] == selection_scope(value)
    )
    need(
        row["approval_type"] == "OWNER_REPORTED_MANAGER_APPROVAL"
        and row["manager_approval_reported"] is True
        and row["administrator_attestation"] is False
        and type(row["maximum_allocations"]) is int
        and row["maximum_allocations"] == 1
        and row["B"] == "DISABLED"
    )
    need(
        type(row["independent_reviewer"]) is str
        and 1 <= len(row["independent_reviewer"]) <= 128
    )
    need(
        s.utc(row["valid_from"])
        <= s.utc(value["valid_from"])
        <= s.utc(now)
        < s.utc(value["valid_until"])
        <= s.utc(row["valid_until"])
    )
    records.raw(row["approval_source_sha256"], structured=False)
    records.raw(value["implementation_review_sha256"], structured=False)
    return row


def directory_binding(path):
    s.private_directory(path)
    info = Path(path).stat(follow_symlinks=False)
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)


def mount_type(path):
    with Path("/proc/self/mountinfo").open("rb") as stream:
        raw = stream.read(65537)
    need(len(raw) <= 65536 and raw.count(b"\n") <= 2048, "A2_ACCOUNTING_UNKNOWN")
    matches = []
    for line in raw.decode("ascii").splitlines():
        before, sep, after = line.partition(" - ")
        cells = before.split()
        if sep and len(cells) >= 5 and path.is_relative_to(Path(cells[4])):
            matches.append((len(cells[4]), after.split()[0]))
    need(bool(matches), "A2_ACCOUNTING_UNKNOWN")
    return max(matches)[1]


def filesystem_probe(parent):
    """Shared snapshot rejection check, not physical entitlement or guarantee."""
    parent = Path(parent)
    before = directory_binding(parent)
    need(os.access(parent, os.W_OK | os.X_OK), "A2_PATH_NOT_WRITABLE")
    fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        need(
            (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid) == before
        )
        v = os.fstatvfs(fd)
        cells = {
            name: getattr(v, name)
            for name in (
                "f_frsize",
                "f_blocks",
                "f_bavail",
                "f_files",
                "f_favail",
                "f_flag",
            )
        }
        for number in cells.values():
            s.uint(number)
            need(number != 2**64 - 1, "A2_ACCOUNTING_UNKNOWN")
        need(
            512 <= v.f_frsize <= 2**20
            and 0 < v.f_bavail <= v.f_blocks
            and 0 < v.f_favail <= v.f_files
            and not v.f_flag & getattr(os, "ST_RDONLY", 1),
            "A2_ACCOUNTING_UNUSABLE",
        )
        reported = v.f_bavail * v.f_frsize
        need(reported < 2**64, "A2_ACCOUNTING_UNUSABLE")
        threshold = (
            POLICY["limits"]["non_B_bytes"]
            + POLICY["limits"]["non_B_creations"] * v.f_frsize
        )
        need(
            reported >= threshold and v.f_favail >= POLICY["limits"]["non_B_creations"],
            "A2_REPORTED_SPACE_INSUFFICIENT",
        )
        fs = mount_type(parent)
        need(fs == "panfs", "A2_WRONG_FILESYSTEM")
        need(directory_binding(parent) == before, "A2_PARENT_CHANGED")
        return {
            "version": "stage12_a2_filesystem_observation_v1",
            "parent": str(parent),
            "parent_identity": list(before),
            "filesystem_type": fs,
            "statvfs": cells,
            "reported_shared_available_bytes": reported,
            "coarse_rejection_threshold_bytes": threshold,
            "meaning": "SHARED_SNAPSHOT_NOT_ENTITLEMENT_OR_PHYSICAL_BOUND",
            "group_quota_and_reservation": "UNKNOWN_NOT_ASSUMED",
            "rounding_metadata_native_transients": "NOT_GUARANTEED",
            "observed_mono_ns": time.monotonic_ns(),
        }
    finally:
        os.close(fd)


def ready(value, records, now, *, probe=filesystem_probe, check=lambda: None, ledger=None):
    validate_selection(value)
    own = owner(value, records, now)
    verify_source(value, check, ledger=ledger)
    raw = s.original(Path(value["paths"]["source"]) / ASSET, private=False)
    need(raw == s.canonical(POLICY), "A2_POLICY_CHANGED")
    for name in ("bootstrap", "final", "review", "collector_ack", "outcome"):
        need(not os.path.lexists(value["paths"][name]), "A2_DESTINATION_USED")
    observed = probe(s.PARENT)
    validate_storage_observation(observed)
    return own, observed


class MetadataWriter:
    """One daemon owner, one outstanding call, no reuse after uncertain I/O."""

    def __init__(self, check, *, guard_seconds=5):
        self.check, self.guard = check, guard_seconds
        self.poisoned = threading.Event()
        self.queue = queue.Queue(maxsize=1)
        self.thread = threading.Thread(
            target=self.work, daemon=True, name="stage12-a2-writer"
        )
        self.thread.start()
        self.closed = False
        self.inflight = threading.Lock()

    def health(self):
        need(not self.poisoned.is_set() and not self.closed, "A2_UNCERTAIN_IO")
        self.check()

    def work(self):
        while True:
            item = self.queue.get()
            if item is None:
                return
            action, future = item
            try:
                self.health()
                result = action()
                self.health()
            except BaseException as error:
                self.poisoned.set()
                future.set_exception(error)
            else:
                future.set_result(result)

    def call(self, action):
        if not self.inflight.acquire(blocking=False):
            self.poisoned.set()
            need(False, "A2_WRITER_CONCURRENT_CALL")
        try:
            self.health()
            future = Future()
            self.queue.put_nowait((action, future))
            result = future.result(timeout=self.guard)
            self.health()
            return result
        except BaseException:
            self.poisoned.set()
            raise
        finally:
            self.inflight.release()

    def close(self):
        self.health()
        self.queue.put_nowait(None)
        self.thread.join(self.guard)
        need(not self.thread.is_alive(), "A2_UNCERTAIN_IO")
        self.health()
        self.closed = True

    def abandon(self):
        self.poisoned.set()
        try:
            self.queue.put_nowait(None)
        except queue.Full:
            pass


class GuardedBudget(s.Budget):
    """Same precharge/exclusive grammar, with poison checks at every I/O edge."""

    def sync(self, path):
        self.check()
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            self.check()
            os.fsync(fd)
            self.check()
        finally:
            os.close(fd)

    def write_raw(self, name, raw):
        path = self.path(name)
        s.private_directory(path.parent)
        need(type(raw) is bytes and len(raw) <= s.MAX_READ, "A2_WRITE_BOUND")
        self.charge(len(raw))
        try:
            self.check()
            fd = os.open(
                path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            try:
                view = memoryview(raw)
                while view:
                    self.check()
                    count = os.write(fd, view)
                    need(count > 0, "A2_WRITE_FAILED")
                    view = view[count:]
                self.check()
                os.fsync(fd)
                self.check()
            finally:
                os.close(fd)
            self.sync(path.parent)
            self.check()
            need(s.original(path) == raw, "A2_READBACK_FAILED")
            self.check()
        except BaseException:
            self.poisoned = True
            raise
        self.inventory.append(dict(name=name, bytes=len(raw), sha256=s.sha(raw)))
        return s.sha(raw)


def global_deadline():
    """The carried original boot epoch applies during all original rereads too."""
    epoch, boot = (
        os.environ.get("STAGE12_EPOCH_START", ""),
        os.environ.get("STAGE12_EPOCH_BOOT", ""),
    )
    need(
        epoch.isdecimal() and len(epoch) <= 20 and bool(boot),
        "A2_GLOBAL_EPOCH_REQUIRED",
    )
    with Path("/proc/sys/kernel/random/boot_id").open("rb") as stream:
        raw = stream.read(65)
    need(len(raw) <= 64, "A2_BOOT_CHANGED")
    current_boot = raw.decode("ascii").strip()
    need(current_boot == boot, "A2_BOOT_CHANGED")
    need(hasattr(time, "CLOCK_BOOTTIME"), "A2_BOOT_CLOCK_REQUIRED")
    now = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
    start = int(epoch) * 10**7
    need(start <= now < start + 8160 * 10**9, "A2_GLOBAL_DEADLINE")
    stage_end = os.environ.get("STAGE12_A2_STAGE_END_CS", "")
    need(
        stage_end.isdecimal() and len(stage_end) <= 20 and now < int(stage_end) * 10**7,
        "A2_STAGE_DEADLINE",
    )


def phase_checks(
    value, start, seconds, clock=time.monotonic_ns, thread_reader=s.native_threads, *, stage="collect"
):
    global _ACTIVE_LEDGER
    if value["version"] == VERSION2:
        from safe_geocoding_pipeline.preprocessing.stages import s12_a2_accounting as accounting
        # Both phase envelopes are derived from the same immutable inventory.
        # Final never refunds/resets the entire consumed collection envelope.
        _ACTIVE_LEDGER = accounting.Ledger(value["accounting_inventory"], stage)
    else:
        _ACTIVE_LEDGER = None
    ledger = _ACTIVE_LEDGER
    end = start + seconds * 10**9
    lock = threading.Lock()
    marks = dict(
        checks=0, maximum_observed_rss_bytes=0, maximum_observed_native_threads=0
    )

    def check():
        global_deadline()
        need(clock() < end, "A2_PHASE_DEADLINE")
        s.check_window(value, s.now_utc())
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (
            1 if sys.platform == "darwin" else 1024
        )
        threads = thread_reader()
        with lock:
            marks["checks"] += 1
            if ledger is None:
                need(marks["checks"] <= 4096, "A2_CHECK_LIMIT")
            else:
                ledger.tick()
            marks["maximum_observed_rss_bytes"] = max(
                marks["maximum_observed_rss_bytes"], rss
            )
            marks["maximum_observed_native_threads"] = max(
                marks["maximum_observed_native_threads"], threads
            )
        need(
            rss <= value["limits"]["rss_bytes"]
            and 0 < threads <= value["limits"]["native_threads"],
            "A2_OBSERVED_RESOURCE_LIMIT",
        )

    return check, marks, end


def write_budget(value, stage, check, end, writer):
    if value["version"] == VERSION2: _ACTIVE_LEDGER.op(6)
    selected = value["limits"]["stages"][stage]
    path = value["paths"]["bootstrap" if stage == "A" else "final"]
    return writer.call(
        lambda: GuardedBudget(
            path,
            max_bytes=selected["bytes"],
            max_creations=selected["creations"],
            deadline=end,
            check=writer.health,
        )
    )


def verify_bootstrap(root, value, token, *, check=lambda: None):
    if value["version"] == VERSION2 and _ACTIVE_LEDGER is not None and check is getattr(_ACTIVE_LEDGER, "guard", None): _ACTIVE_LEDGER.op(7)
    check()
    manifest = s.verify_stage(root, expected_status=COLLECTED)
    need(
        {row["name"] for row in manifest["inventory"]}
        == {
            "storage_before.json",
            "storage_after.json",
            "kernel.json",
            "kernel_after.json",
            "runtime.json",
            "facts.json",
        },
        "A2_INCOMPLETE_INVENTORY",
    )
    before = s.parse(s.original(Path(root) / "storage_before.json"))
    after = s.parse(s.original(Path(root) / "storage_after.json"))
    validate_storage_observation(before)
    validate_storage_observation(after)
    validate_stage_counters(root, manifest, value["limits"]["stages"]["A"])
    need(
        before["parent"] == after["parent"] == str(s.PARENT)
        and before["parent_identity"] == after["parent_identity"],
        "A2_PARENT_CHANGED",
    )
    facts = s.parse(s.original(Path(root) / "facts.json"))
    s.fields(
        facts,
        (
            "version",
            "scope",
            "source_sha",
            "selection_sha256",
            "policy_sha256",
            "job_id",
            "created_utc",
            "started_mono_ns",
            "preclosure_end_mono_ns",
            "kernel_sha256",
            "kernel_after_sha256",
            "runtime_sha256",
            "resource_watermarks",
            "M2",
            "B",
            "capacity_assurance",
        ) + (("accounting",) if value["version"] == VERSION2 else ()),
    )
    need(
        facts["version"] == ("stage12_a2_bootstrap_facts_v2" if value["version"] == VERSION2 else "stage12_a2_bootstrap_facts_v1")
        and facts["scope"] == SCOPE
        and facts["B"] == "DISABLED"
        and facts["source_sha"] == value["source_sha"]
        and facts["selection_sha256"] == token
        and facts["policy_sha256"] == POLICY_SHA
        and facts["M2"] == "NOT_QUALIFIED_BY_BOOTSTRAP"
        and facts["capacity_assurance"] == "OWNER_REPORTED_BEST_EFFORT_NOT_RESERVED",
        "A2_FACT_BINDING",
    )
    if value["version"] == VERSION2:
        from safe_geocoding_pipeline.preprocessing.stages import s12_a2_accounting as accounting
        bounds = accounting.bounds(value["accounting_inventory"])
        row = facts["accounting"]
        accounting.validate_prefix(row, value["accounting_inventory"], "capture")
        need(row["backend_calls"] == 5 and row["source_calls"] == 2
             and row["phase_ordinal"] == accounting.PHASES.index("CAPTURE_CLOSE")
             and row["checks"] == facts["resource_watermarks"]["checks"]
             and row["completed_bytes"] == bounds["backend_bytes_per_pass"] + 2 * bounds["source_bytes_per_pass"]
             and row["collect_checks_reserved"] == row["cumulative_checks_reserved"] == bounds["collect_checks"], "A2_INCOMPLETE_HASH_ACCOUNTING")
    for name, field in (
        ("kernel.json", "kernel_sha256"),
        ("kernel_after.json", "kernel_after_sha256"),
        ("runtime.json", "runtime_sha256"),
    ):
        check()
        need(
            s.sha(s.original(Path(root) / name)) == facts[field], "A2_ORIGINAL_CHANGED"
        )
    check()
    return manifest, facts


def collect(
    value,
    selection_path,
    token,
    *,
    clock=time.monotonic_ns,
    kernel_reader=s.observe_kernel,
    inventory_reader=None,
    probe=filesystem_probe,
    thread_reader=s.native_threads,
    install_guard=True,
):
    from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm

    require_goethe_nhr_slurm("A2 best-effort metadata bootstrap")
    start = clock()
    check, marks, end = phase_checks(value, start, 120, clock, thread_reader)
    ledger = _ACTIVE_LEDGER
    records = s.Records(value["paths"]["records"])
    _, before = ready(value, records, s.now_utc(), probe=probe, check=check, ledger=ledger)
    initial_check = check

    def check():
        initial_check()
        need(
            list(directory_binding(s.PARENT)) == before["parent_identity"],
            "A2_PARENT_CHANGED",
        )

    if ledger: ledger.guard = check

    def bound_probe():
        row = probe(s.PARENT)
        need(row["parent_identity"] == before["parent_identity"], "A2_PARENT_CHANGED")
        return row

    if install_guard:
        s.collection_guard(
            Path(value["paths"]["source"]),
            Path(value["paths"]["bootstrap"]),
            records.root,
            selection_path,
        )
    writer = MetadataWriter(check)
    try:
        budget = write_budget(value, "A", check, end, writer)

        def persist(name, obj):
            if ledger: ledger.op(6)
            check()
            bound_probe()
            return writer.call(lambda: budget.write(name, obj))

        persist("storage_before.json", before)
        if ledger: ledger.enter("KERNEL_PRE")
        if ledger: ledger.op(5)
        kernel = kernel_reader(check=check)
        persist("kernel.json", kernel)
        if ledger: ledger.enter("RUNTIME")
        if inventory_reader is None:
            from safe_geocoding_pipeline.preprocessing.stages import s12_public_runtime

            inventory_reader = s12_public_runtime.runtime_inventory
        options = dict(successor=True, check=check)
        if ledger: options["backend_reader"] = ledger.backend
        runtime = inventory_reader(s.PUBLIC_VALIDATOR, **options)
        persist("runtime.json", runtime)
        if ledger: ledger.enter("KERNEL_POST")
        if ledger: ledger.op(5)
        after = kernel_reader(check=check)
        for key in ("boot_id", "namespaces", "membership", "leaf_identity", "leaf"):
            need(kernel[key] == after[key], "A2_DOMAIN_CHANGED")
        persist("kernel_after.json", after)
        if ledger: ledger.enter("SOURCE")
        verify_source(value, check, ledger=ledger)
        persist("storage_after.json", bound_probe())
        if ledger: ledger.enter("CAPTURE_CLOSE")
        persist(
            "facts.json",
            dict(
                version="stage12_a2_bootstrap_facts_v2" if ledger else "stage12_a2_bootstrap_facts_v1",
                scope=SCOPE,
                source_sha=value["source_sha"],
                selection_sha256=token,
                policy_sha256=POLICY_SHA,
                job_id=os.environ["SLURM_JOB_ID"],
                created_utc=s.now_utc(),
                started_mono_ns=start,
                preclosure_end_mono_ns=clock(),
                kernel_sha256=s.digest(kernel),
                kernel_after_sha256=s.digest(after),
                runtime_sha256=s.digest(runtime),
                resource_watermarks=marks.copy(),
                M2="NOT_QUALIFIED_BY_BOOTSTRAP",
                B="DISABLED",
                capacity_assurance="OWNER_REPORTED_BEST_EFFORT_NOT_RESERVED",
                **({"accounting": ledger.snapshot()} if ledger else {}),
            ),
        )
        writer.call(lambda: budget.close(COLLECTED))
        if ledger: ledger.enter("CAPTURE_OPEN")
        verify_bootstrap(budget.root, value, token, check=check)
        if ledger: ledger.op(8)
        writer.close()
        check()
        if ledger: ledger.enter("FINISHED")
        if ledger: ledger.op(9)
        return dict(
            status=COLLECTED,
            manifest_sha256=s.sha(s.original(budget.root / "manifest.json")),
            B="DISABLED",
            **({"accounting": ledger.snapshot()} if ledger else {}),
        )
    except BaseException:
        writer.abandon()
        raise


def verify_review(
    value,
    token,
    *,
    bootstrap_root=None,
    records_root=None,
    acceptance_centiseconds=None,
    check=lambda: None,
):
    paths = value["paths"]
    root = Path(bootstrap_root or paths["bootstrap"])
    records_path = Path(records_root or paths["records"])
    own = owner(value, s.Records(records_path), s.now_utc())
    _, facts = verify_bootstrap(root, value, token, check=check)
    ack_raw = s.original(records_path / "collector_ack.json", limit=4096)
    ack = s.parse(ack_raw)
    s.fields(
        ack,
        (
            "version",
            "source_sha",
            "selection_sha256",
            "manifest_sha256",
            "job_id",
            "collector_exit",
            "completed_centiseconds",
            "capture_started_centiseconds",
            "epoch_centiseconds",
            "B",
        ),
    )
    need(
        ack["version"] == "stage12_a2_collector_ack_v1"
        and ack["collector_exit"] == 0
        and type(ack["collector_exit"]) is int
        and ack["B"] == "DISABLED"
    )
    need(
        ack["source_sha"] == value["source_sha"]
        and ack["selection_sha256"] == token
        and ack["manifest_sha256"] == s.sha(s.original(root / "manifest.json"))
        and ack["job_id"] == facts["job_id"],
        "A2_COLLECTOR_NOT_ACKNOWLEDGED",
    )
    for name in (
        "completed_centiseconds",
        "capture_started_centiseconds",
        "epoch_centiseconds",
    ):
        s.uint(ack[name], True)
    need(
        ack["epoch_centiseconds"]
        <= ack["capture_started_centiseconds"]
        <= ack["completed_centiseconds"]
        and ack["completed_centiseconds"] - ack["capture_started_centiseconds"] < 12000
        and ack["completed_centiseconds"] - ack["epoch_centiseconds"] < 816000,
        "A2_COLLECTOR_TIME",
    )
    review_raw = s.original(records_path / "a2_review.json", limit=65536)
    review = s.parse(review_raw)
    s.fields(
        review,
        (
            "version",
            "scope",
            "source_sha",
            "selection_sha256",
            "manifest_sha256",
            "collector_ack_sha256",
            "reviewer",
            "reviewed_utc",
            "disposition",
            "B",
        ),
    )
    need(
        review["version"] == "stage12_a2_independent_outcome_v1"
        and review["scope"] == SCOPE
        and review["source_sha"] == value["source_sha"]
        and review["selection_sha256"] == token
        and review["manifest_sha256"] == ack["manifest_sha256"]
        and review["collector_ack_sha256"] == s.sha(ack_raw)
        and review["reviewer"] == own["independent_reviewer"]
        and review["disposition"] == "A_ORIGINALS_VERIFIED_B_DISABLED"
        and review["B"] == "DISABLED",
        "A2_REVIEW_REJECTED",
    )
    need(
        s.utc(facts["created_utc"])
        <= s.utc(review["reviewed_utc"])
        <= s.utc(s.now_utc())
        < s.utc(value["valid_until"]),
        "A2_REVIEW_TIME",
    )
    accepted = acceptance_centiseconds
    if accepted is None:
        accepted = boot_centiseconds()
    s.uint(accepted, True)
    need(
        ack["completed_centiseconds"]
        <= accepted
        < ack["completed_centiseconds"] + 60000
        and accepted - ack["epoch_centiseconds"] < 816000,
        "A2_REVIEW_DEADLINE",
    )
    check()
    return review, facts, accepted


def open_completed(
    value,
    token,
    *,
    bootstrap_root=None,
    records_root=None,
    final_root=None,
    probe=filesystem_probe,
    check=lambda: None,
    ledger=None,
    source_root=None,
    mirror_only=False,
):
    if value["version"] == VERSION2:
        from safe_geocoding_pipeline.preprocessing.stages import s12_a2_accounting as accounting
        if ledger is None:
            need(mirror_only and all(x is not None for x in (bootstrap_root, records_root, final_root)), "A2_REOPEN_ACCOUNTING_REQUIRED")
        else:
            need(not mirror_only and isinstance(ledger, accounting.Ledger)
                 and ledger.stage == "final" and ledger.phase == accounting.PHASES.index("FINAL_OPEN")
                 and check is getattr(ledger, "guard", None)
                 and s.canonical(ledger.inventory) == s.canonical(value["accounting_inventory"]), "A2_REOPEN_ACCOUNTING_REQUIRED")
    check()
    if ledger is not None:
        verify_source(value, check, ledger=ledger, root=source_root)
    if bootstrap_root is None and records_root is None and final_root is None:
        before = s.parse(
            s.original(Path(value["paths"]["bootstrap"]) / "storage_before.json")
        )
        need(
            probe(s.PARENT)["parent_identity"] == before["parent_identity"],
            "A2_PARENT_CHANGED",
        )
    root = Path(final_root or value["paths"]["final"])
    manifest = s.verify_stage(root, expected_status=FINALIZED)
    need(
        {row["name"] for row in manifest["inventory"]} == {"result.json"},
        "A2_INCOMPLETE_INVENTORY",
    )
    validate_stage_counters(root, manifest, value["limits"]["stages"]["final"])
    result = s.parse(s.original(root / "result.json"))
    s.fields(
        result,
        (
            "version",
            "source_sha",
            "selection_sha256",
            "policy_sha256",
            "review_sha256",
            "job_id",
            "B",
            "review_accepted_centiseconds",
            "capacity_assurance",
            "M2",
        ) + (("accounting",) if value["version"] == VERSION2 else ()),
    )
    review, facts, _ = verify_review(
        value,
        token,
        bootstrap_root=bootstrap_root,
        records_root=records_root,
        acceptance_centiseconds=result["review_accepted_centiseconds"],
        check=check,
    )
    if ledger is not None:
        runtime = s.parse(s.original(Path(bootstrap_root or value["paths"]["bootstrap"]) / "runtime.json"))
        ledger.verify_backends(runtime, check)
    need(
        result["version"] == ("stage12_a2_closure_v2" if value["version"] == VERSION2 else "stage12_a2_closure_v1")
        and result["selection_sha256"] == token
        and result["source_sha"] == value["source_sha"]
        and result["policy_sha256"] == POLICY_SHA
        and result["review_sha256"] == s.digest(review)
        and result["job_id"] == facts["job_id"]
        and result["B"] == "DISABLED"
        and result["M2"] == "NOT_QUALIFIED_BY_BOOTSTRAP"
        and result["capacity_assurance"]
        == "BEST_EFFORT_NO_RESERVED_OR_ATTRIBUTABLE_GUARANTEE",
        "A2_CLOSURE_CHANGED",
    )
    if value["version"] == VERSION2:
        from safe_geocoding_pipeline.preprocessing.stages import s12_a2_accounting as accounting
        accounting.validate_prefix(result["accounting"], value["accounting_inventory"], "final_write")
        need(result["accounting"]["phase_ordinal"] == accounting.PHASES.index("FINAL_WRITE"), "A2_FINAL_ACCOUNTING_CHANGED")
    check()
    if mirror_only:
        return dict(result, verification_scope="STRUCTURAL_MIRROR_ONLY_NOT_EXECUTION_QUALIFICATION")
    return result


def finalize(
    value,
    selection_path,
    token,
    *,
    thread_reader=s.native_threads,
    install_guard=True,
    probe=filesystem_probe,
):
    from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm

    require_goethe_nhr_slurm("A2 original metadata closure")
    check, _, end = phase_checks(
        value, time.monotonic_ns(), 120, thread_reader=thread_reader, stage="final"
    )
    ledger = _ACTIVE_LEDGER
    records = s.Records(value["paths"]["records"])
    owner(value, records, s.now_utc())
    before = s.parse(
        s.original(Path(value["paths"]["bootstrap"]) / "storage_before.json")
    )
    need(
        probe(s.PARENT)["parent_identity"] == before["parent_identity"],
        "A2_PARENT_CHANGED",
    )
    initial_check = check

    def check():
        initial_check()
        need(
            list(directory_binding(s.PARENT)) == before["parent_identity"],
            "A2_PARENT_CHANGED",
        )

    if ledger: ledger.guard = check

    verify_source(value, check, ledger=ledger)
    if install_guard:
        s.collection_guard(
            Path(value["paths"]["source"]),
            Path(value["paths"]["final"]),
            records.root,
            selection_path,
            extra_reads=(Path(value["paths"]["bootstrap"]),),
        )
    review, facts, accepted = verify_review(value, token, check=check)
    if ledger:
        runtime = s.parse(s.original(Path(value["paths"]["bootstrap"]) / "runtime.json"))
        ledger.verify_backends(runtime, check)
    need(facts["job_id"] == os.environ["SLURM_JOB_ID"], "A2_JOB_CHANGED")
    writer = MetadataWriter(check)
    try:
        budget = write_budget(value, "final", check, end, writer)
        if ledger: ledger.enter("FINAL_WRITE")
        if ledger: ledger.op(6)
        writer.call(
            lambda: budget.write(
                "result.json",
                dict(
                    version="stage12_a2_closure_v2" if ledger else "stage12_a2_closure_v1",
                    source_sha=value["source_sha"],
                    selection_sha256=token,
                    policy_sha256=POLICY_SHA,
                    review_sha256=s.digest(review),
                    job_id=facts["job_id"],
                    B="DISABLED",
                    review_accepted_centiseconds=accepted,
                    capacity_assurance="BEST_EFFORT_NO_RESERVED_OR_ATTRIBUTABLE_GUARANTEE",
                    M2="NOT_QUALIFIED_BY_BOOTSTRAP",
                    **({"accounting": ledger.snapshot()} if ledger else {}),
                ),
            )
        )
        if ledger: ledger.enter("FINAL_RECHECK")
        fresh, _, _ = verify_review(
            value, token, acceptance_centiseconds=accepted, check=check
        )
        if ledger:
            ledger.verify_backends(runtime, check)
        need(s.digest(fresh) == s.digest(review), "A2_REVIEW_CHANGED")
        need(
            probe(s.PARENT)["parent_identity"] == before["parent_identity"],
            "A2_PARENT_CHANGED",
        )
        verify_source(value, check, ledger=ledger)
        if ledger: ledger.enter("FINAL_CLOSE")
        if ledger: ledger.op(6)
        writer.call(lambda: budget.close(FINALIZED))
        if ledger: ledger.op(8)
        writer.close()
        if ledger: ledger.enter("FINAL_OPEN")
        result = open_completed(value, token, check=check, probe=probe, ledger=ledger)
        check()
        if ledger: ledger.enter("FINISHED")
        if ledger: ledger.op(9)
        return dict(
            status="A2_ACTUAL_STRUCTURAL_REOPEN_PASS_PENDING_TERMINAL", result=result,
            **({"accounting": ledger.snapshot()} if ledger else {}),
        )
    except BaseException:
        writer.abandon()
        raise


def validate_storage_observation(row):
    s.fields(
        row,
        (
            "version",
            "parent",
            "parent_identity",
            "filesystem_type",
            "statvfs",
            "reported_shared_available_bytes",
            "coarse_rejection_threshold_bytes",
            "meaning",
            "group_quota_and_reservation",
            "rounding_metadata_native_transients",
            "observed_mono_ns",
        ),
    )
    need(
        row["version"] == "stage12_a2_filesystem_observation_v1"
        and row["parent"] == str(s.PARENT)
        and row["filesystem_type"] == "panfs"
        and row["meaning"] == "SHARED_SNAPSHOT_NOT_ENTITLEMENT_OR_PHYSICAL_BOUND"
        and row["group_quota_and_reservation"] == "UNKNOWN_NOT_ASSUMED"
        and row["rounding_metadata_native_transients"] == "NOT_GUARANTEED"
    )
    binding = row["parent_identity"]
    need(type(binding) is list and len(binding) == 5)
    for cell in binding:
        s.uint(cell)
    need(stat.S_ISDIR(binding[2]) and stat.S_IMODE(binding[2]) == 0o700)
    cells = row["statvfs"]
    s.fields(
        cells, ("f_frsize", "f_blocks", "f_bavail", "f_files", "f_favail", "f_flag")
    )
    for cell in cells.values():
        s.uint(cell)
        need(cell != 2**64 - 1, "A2_ACCOUNTING_UNKNOWN")
    need(
        512 <= cells["f_frsize"] <= 2**20
        and 0 < cells["f_bavail"] <= cells["f_blocks"]
        and 0 < cells["f_favail"] <= cells["f_files"]
        and not cells["f_flag"] & 1
    )
    reported = cells["f_bavail"] * cells["f_frsize"]
    threshold = (
        POLICY["limits"]["non_B_bytes"]
        + POLICY["limits"]["non_B_creations"] * cells["f_frsize"]
    )
    need(
        reported < 2**64
        and row["reported_shared_available_bytes"] == reported
        and row["coarse_rejection_threshold_bytes"] == threshold
        and reported >= threshold
        and cells["f_favail"] >= POLICY["limits"]["non_B_creations"]
    )
    s.uint(row["observed_mono_ns"], True)


def validate_stage_counters(root, manifest, limits):
    need(manifest["directories"] == [], "A2_SURPLUS_DIRECTORY")
    size = sum(row["bytes"] for row in manifest["inventory"])
    entries = 1 + len(manifest["inventory"])
    need(
        type(manifest["charged_bytes_before_manifest"]) is int
        and type(manifest["charged_creations_before_manifest"]) is int
        and manifest["charged_bytes_before_manifest"] == size
        and manifest["charged_creations_before_manifest"] == entries,
        "A2_ACCOUNTING_CHANGED",
    )
    need(
        size + len(s.original(Path(root) / "manifest.json")) <= limits["bytes"]
        and entries + 1 <= limits["creations"],
        "A2_STAGE_BUDGET",
    )


def boot_centiseconds():
    need(hasattr(time, "CLOCK_BOOTTIME"), "A2_BOOT_CLOCK_REQUIRED")
    return time.clock_gettime_ns(time.CLOCK_BOOTTIME) // 10**7 + 1


def validate_environment(value, selection_path, selection_hash):
    need(Path(value["paths"]["source"]) == ROOT, "A2_EXECUTED_SOURCE_ROOT")
    environment = {
        "source": "STAGE12_AP2_SOURCE",
        "bootstrap": "STAGE12_AP2_BOOTSTRAP",
        "records": "STAGE12_A2_RECORDS",
        "final": "STAGE12_A2_FINAL",
        "outcome": "STAGE12_AP2_OUTCOME",
    }
    for path, name in environment.items():
        need(os.environ.get(name) == value["paths"][path], "A2_ENVIRONMENT_BINDING")
    need(
        os.environ.get("STAGE12_AP2_SOURCE_SHA") == value["source_sha"]
        and os.environ.get("STAGE12_AP2_SELECTION") == str(selection_path)
        and os.environ.get("STAGE12_AP2_SELECTION_SHA256") == selection_hash,
        "A2_ENVIRONMENT_BINDING",
    )


def main():
    global _ACTIVE_LEDGER
    _ACTIVE_LEDGER = None
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("collect", "finalize"))
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--selection-sha256", required=True)
    args = parser.parse_args()
    try:
        value = load_selection(args.selection, args.selection_sha256)
        validate_environment(value, args.selection, args.selection_sha256)
        sys.path.insert(0, str(Path(value["paths"]["source"]) / "src"))
        result = (collect if args.operation == "collect" else finalize)(
            value, args.selection, args.selection_sha256
        )
        print(s.canonical(result).decode("ascii"), end="")
        return 0
    except BaseException as error:
        code = "A2_UNKNOWN_FAILURE"
        accounting = sys.modules.get("safe_geocoding_pipeline.preprocessing.stages.s12_a2_accounting")
        types = (s.AllocationError,) + ((accounting.AccountingError,) if accounting else ())
        if isinstance(error, types) and len(error.args) == 1:
            import re

            if type(error.args[0]) is str and re.fullmatch(
                r"[A-Z0-9_]{1,128}", error.args[0]
            ) and (not accounting or not isinstance(error, accounting.AccountingError) or error.args[0] in accounting.ERROR_CODES):
                code = error.args[0]
        if isinstance(error, (FutureTimeout, TimeoutError)):
            code = "A2_UNCERTAIN_IO_OR_DEADLINE"
        print(
            s.canonical(
                dict(
                    status="INCOMPLETE",
                    code=code,
                    errno=error.errno
                    if isinstance(error, OSError)
                    and type(error.errno) is int
                    and 0 <= error.errno <= 4096
                    else None,
                    B="DISABLED",
                    **({"accounting": _ACTIVE_LEDGER.snapshot()} if _ACTIVE_LEDGER is not None else {}),
                )
            ).decode("ascii"),
            file=sys.stderr,
            end="",
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
