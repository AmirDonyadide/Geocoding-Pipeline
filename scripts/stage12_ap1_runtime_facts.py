#!/usr/bin/env python3
"""Standalone, denied AP representation facts. Never an AP invocation/bound record."""

from __future__ import annotations
import argparse
from collections import deque
import gc
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import resource
import struct
import sys
import sysconfig
import threading
import time

VERSION = "stage12_ap1_runtime_characterization_v1"
LIMITS = {
    "seconds": 600,
    "rss_bytes": 768 * 2**20,
    "file_data_bytes": 64 * 2**20,
    "creations": 2000,
    "diagnostic_processes": 1,
    "metadata_python_invocations": 3,
    "launcher_command_invocations_max": 24,
    "python_threads": 3,
    "observed_native_threads": 256,
    "ring_rows": 4096,
    "graph_nodes": 524288,
    "runtime_code_read_bytes": 512 * 2**20,
}
TIMES = (
    "acquire_enter_ns reserved_ns free_query_start_ns free_query_end_ns "
    "safety_wait_start_ns safety_acquired_ns observed_ns acquire_exit_ns "
    "enqueued_ns writer_entry_ns sample_header_ns append_complete_ns "
    "event_ack_publish_ns ack_witness_header_ns ack_witness_reopened_ns "
    "pair_action_return_ns pair_post_action_complete_ns credit_released_ns"
).split()


def canonical(value):
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")


def require(ok):
    if not ok:
        raise RuntimeError("AP_FACTS_INVALID")


def parse(raw):
    def pairs(rows):
        require(len({k for k, _ in rows}) == len(rows))
        return dict(rows)

    value = json.loads(raw, object_pairs_hook=pairs)
    require(canonical(value) == raw)
    require(
        set(value)
        == {
            "version",
            "scope",
            "source_sha",
            "limits",
            "synthetic_timing_associations",
            "output_name",
        }
    )
    require(
        value["version"] == VERSION
        and value["scope"] == "NO_SERVICE_CHARACTERIZATION_NOT_AP_WORKFLOW"
    )
    require(value["synthetic_timing_associations"] is True)
    require(
        type(value["source_sha"]) is str
        and len(value["source_sha"]) == 40
        and all(c in "0123456789abcdef" for c in value["source_sha"])
    )
    require(
        value["limits"] == LIMITS
        and all(type(v) is int for v in value["limits"].values())
    )
    require(
        type(value["output_name"]) is str
        and value["output_name"].startswith("ap1_runtime_facts_")
        and all(c.isalnum() or c == "_" for c in value["output_name"])
    )
    return value


def read_input(path, expected_sha):
    import stat

    before = path.lstat()
    require(
        stat.S_ISREG(before.st_mode)
        and stat.S_IMODE(before.st_mode) == 0o600
        and before.st_uid == os.getuid()
        and before.st_nlink == 1
        and before.st_size <= 16384
    )

    def identity(info):
        return tuple(
            getattr(info, k)
            for k in (
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
        )

    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        opened = os.fstat(fd)
        require(identity(before) == identity(opened))
        raw = os.read(fd, 16385)
        after = os.fstat(fd)
        require(
            len(raw) <= 16384
            and identity(opened) == identity(after) == identity(path.lstat())
        )
    finally:
        os.close(fd)
    require(hashlib.sha256(raw).hexdigest() == expected_sha)
    return parse(raw)


class Budget:
    def __init__(self):
        self.lock = threading.Lock()
        self.bytes = self.creations = 0

    def charge(self, size):
        with self.lock:
            require(type(size) is int and size >= 0)
            require(
                self.bytes + size <= LIMITS["file_data_bytes"]
                and self.creations < LIMITS["creations"]
            )
            self.bytes += size
            self.creations += 1


def owned_graph(roots, maximum=LIMITS["graph_nodes"]):
    """Deduplicated built-in graph sizes: observation/lower accounting, NOT upper proof."""
    todo = [roots]
    seen = set()
    sizes = {}
    counts = {}
    while todo:
        obj = todo.pop()
        identity = id(obj)
        if identity in seen:
            continue
        require(len(seen) < maximum)
        seen.add(identity)
        name = type(obj).__name__
        amount = sys.getsizeof(obj)
        sizes[name] = sizes.get(name, 0) + amount
        counts[name] = counts.get(name, 0) + 1
        if type(obj) is dict:
            for k, v in obj.items():
                todo.extend((k, v))
        elif type(obj) in (list, tuple, deque):
            todo.extend(obj)
        else:
            require(type(obj) in (str, bytes, bytearray, int, bool, type(None)))
    return {
        "reported_owned_graph_bytes": sum(sizes.values()),
        "objects": len(seen),
        "sizes_by_type": sizes,
        "counts_by_type": counts,
        "interpretation": "OBSERVED_BUILTIN_GRAPH_SIZE_NOT_NATIVE_UPPER_BOUND_OR_ENFORCEMENT",
    }


def timing_row(contract, n):
    row = dict.fromkeys(contract.ASYNC_FIELDS)
    row.update(
        row_kind="PERIODIC_ASYNC",
        phase_id=1,
        segment_id=1,
        epoch_id="0" * 64,
        acquisition_seq=n,
        observation_sha256="1" * 64,
        role="REGULAR",
        resource_revision=n,
        future_used=False,
        outcome="COMPLETE",
        sample_event_seq=2 * n,
        sample_event_sha256="2" * 64,
        ack_event_seq=2 * n + 1,
        ack_event_sha256="3" * 64,
    )
    for offset, name in enumerate(TIMES):
        row[name] = n * 50_000_000 + offset
    return row


def denial(read_roots, output, input_path):
    """Python audit boundary, not a native/OS sandbox or memory containment proof."""
    allowed = tuple({str(q) for p in read_roots for q in (p.absolute(), p.resolve())})
    output = str(output.absolute())
    input_path = str(input_path.absolute())
    creates = [0]

    def inside(path, root):
        return path == root or path.startswith(root + "/")

    def hook(event, args):
        if event.startswith(
            ("socket.", "subprocess.", "os.exec", "os.spawn")
        ) or event in (
            "os.system",
            "os.fork",
            "os.forkpty",
            "os.posix_spawn",
            "pty.spawn",
        ):
            raise PermissionError("AP_FACTS_DENIED")
        if event in ("os.remove", "os.rename", "os.rmdir", "os.link", "os.symlink"):
            raise PermissionError("AP_FACTS_DENIED")
        if event in (
            "open",
            "os.mkdir",
            "os.remove",
            "os.rename",
            "os.rmdir",
            "os.link",
            "os.symlink",
        ):
            value = args[0]
            if type(value) is int:
                return
            path = os.path.abspath(os.fsdecode(value))
            writing = (
                event != "open"
                or (isinstance(args[1], str) and any(c in args[1] for c in "wax+"))
                or (
                    type(args[2]) is int
                    and bool(
                        args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
                    )
                )
            )
            if writing:
                if not inside(path, output):
                    raise PermissionError("AP_FACTS_DENIED")
                if event == "os.mkdir" or (
                    event == "open" and type(args[2]) is int and args[2] & os.O_CREAT
                ):
                    require(creates[0] < LIMITS["creations"])
                    creates[0] += 1
            elif not (
                inside(path, output)
                or path == input_path
                or any(inside(path, root) for root in allowed)
            ):
                raise PermissionError("AP_FACTS_DENIED")
        elif event in ("os.listdir", "os.scandir"):
            if type(args[0]) is int:
                return
            path = os.path.abspath(os.fsdecode(args[0]))
            if not (
                inside(path, output) or any(inside(path, root) for root in allowed)
            ):
                raise PermissionError("AP_FACTS_DENIED")

    sys.addaudithook(hook)
    return creates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "input",
        "input-sha256",
        "source",
        "source-sha",
        "output",
        "started-ns",
    ):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm

    require_goethe_nhr_slurm(
        "standalone AP runtime facts, no service or protected input"
    )
    started = int(args.started_ns)
    deadline = started + LIMITS["seconds"] * 10**9
    require(time.monotonic_ns() < deadline)
    source = Path(args.source)
    output = Path(args.output)
    inp = Path(args.input)
    project = Path("/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline")
    require(output.parent == project / "derived/controlled/stage12/client_diagnostics")
    require(
        source.parent == project / "integration_stage12" and source.resolve() == source
    )
    require(
        inp.parent == project / "derived/controlled/stage12/client_diagnostics"
        and inp.name.startswith("ap1_runtime_facts_")
        and inp.suffix == ".json"
        and inp.resolve() == inp
    )
    selected = read_input(inp, args.input_sha256)
    require(
        selected["source_sha"] == args.source_sha
        and selected["output_name"] == output.name
    )
    require(not output.exists())
    budget = Budget()
    budget.charge(0)
    output.mkdir(mode=0o700)
    roots = [
        source,
        Path(sys.prefix),
        Path(sys.base_prefix),
        Path("/usr"),
        Path("/lib"),
        Path("/lib64"),
        Path("/proc/self"),
        Path("/proc/cpuinfo"),
        Path("/sys/devices/system/cpu"),
        Path("/etc/ld.so.cache"),
        Path("/etc/localtime"),
    ]
    audit_creates = denial(roots, output, inp)
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    stop = threading.Event()
    peaks = {"rss_bytes": 0, "native_threads": 0, "python_threads": 0}
    monitor_fault = []

    def check():
        require(time.monotonic_ns() < deadline)
        require(not monitor_fault)

    def write(name, value):
        check()
        data = canonical(value)
        require(len(data) <= 2**20)
        budget.charge(len(data))
        path = output / name
        with path.open("xb") as sink:
            sink.write(data)
            sink.flush()
            os.fsync(sink.fileno())
        check()

    def monitor():
        try:
            while not stop.is_set():
                with open("/proc/self/status", "r", encoding="ascii") as f:
                    status = f.read(16384)
                fields = dict(
                    line.split(":", 1) for line in status.splitlines() if ":" in line
                )
                rss = int(fields["VmRSS"].split()[0]) * 1024
                threads = int(fields["Threads"].strip())
                peaks["rss_bytes"] = max(peaks["rss_bytes"], rss)
                peaks["native_threads"] = max(peaks["native_threads"], threads)
                peaks["python_threads"] = max(
                    peaks["python_threads"], threading.active_count()
                )
                if (
                    time.monotonic_ns() >= deadline
                    or rss > LIMITS["rss_bytes"]
                    or threads > LIMITS["observed_native_threads"]
                    or threading.active_count() > LIMITS["python_threads"]
                ):
                    monitor_fault.append("OBSERVED_LIMIT")
                    os._exit(93)
                stop.wait(0.05)
        except BaseException:
            os._exit(94)

    watcher = threading.Thread(target=monitor, name="AP-facts-watchdog", daemon=True)
    watcher.start()
    code_read = 0

    def code_hash(path):
        nonlocal code_read
        path = Path(path).resolve()
        digest = hashlib.sha256()
        length = 0
        with path.open("rb") as stream:
            while data := stream.read(65536):
                check()
                length += len(data)
                code_read += len(data)
                require(code_read <= LIMITS["runtime_code_read_bytes"])
                digest.update(data)
        return {"path": str(path), "sha256": digest.hexdigest(), "bytes": length}

    try:
        config_names = (
            "SOABI",
            "MULTIARCH",
            "Py_GIL_DISABLED",
            "Py_DEBUG",
            "WITH_PYMALLOC",
            "WITH_MIMALLOC",
            "SIZEOF_VOID_P",
            "SIZEOF_LONG",
            "SIZEOF_SIZE_T",
            "CC",
            "CFLAGS",
            "CONFIG_ARGS",
        )
        build = {
            k: sysconfig.get_config_var(k) for k in config_names if k != "CONFIG_ARGS"
        }
        facts = {
            "scope": selected["scope"],
            "source_sha": args.source_sha,
            "job_id": os.environ["SLURM_JOB_ID"],
            "python_version": sys.version,
            "implementation": platform.python_implementation(),
            "abiflags": sys.abiflags,
            "cache_tag": sys.implementation.cache_tag,
            "pointer_bytes": struct.calcsize("P"),
            "byteorder": sys.byteorder,
            "gil_enabled": sys._is_gil_enabled()
            if hasattr(sys, "_is_gil_enabled")
            else None,
            "flags": {
                k: getattr(sys.flags, k)
                for k in (
                    "debug",
                    "optimize",
                    "no_user_site",
                    "utf8_mode",
                    "hash_randomization",
                    "isolated",
                )
            },
            "build": build,
            "executable": code_hash(sys.executable),
            "platform": list(os.uname()),
            "gc": {
                "enabled": gc.isenabled(),
                "threshold": gc.get_threshold(),
                "stats": gc.get_stats(),
            },
            "selected_environment": {
                k: os.environ.get(k)
                for k in (
                    "PYTHONMALLOC",
                    "PYTHON_GIL",
                    "PYTHONHASHSEED",
                    "PYTHONNOUSERSITE",
                    "OMP_NUM_THREADS",
                    "OPENBLAS_NUM_THREADS",
                    "ARROW_IO_THREADS",
                )
            },
            "effective_allocator": "UNKNOWN_BUILD_ENV_NOT_EFFECTIVE_ALLOCATOR_PROOF",
            "native_allocation_upper_bound": None,
        }
        write("RUNTIME_BOOTSTRAP_FACTS.json", facts)
        modules = {}
        for name in (
            "ssl",
            "_hashlib",
            "pyarrow",
            "pyarrow.lib",
            "duckdb",
            "_duckdb",
            "sqlite3",
            "_sqlite3",
        ):
            check()
            module = importlib.import_module(name)
            modules[name] = {
                "version": getattr(module, "__version__", None),
                "code": code_hash(module.__file__)
                if getattr(module, "__file__", None)
                else None,
            }
            if name == "ssl":
                modules[name]["openssl"] = module.OPENSSL_VERSION
            if name == "pyarrow":
                module.set_cpu_count(1)
                module.set_io_thread_count(1)
                modules[name].update(
                    cpu_count=module.cpu_count(),
                    io_thread_count=module.io_thread_count(),
                    codec_zstd_available=module.Codec.is_available("zstd"),
                    cpp_version=module.cpp_version,
                )
            if name == "sqlite3":
                modules[name].update(
                    sqlite_version=module.sqlite_version,
                    threadsafety=module.threadsafety,
                )
            write("NATIVE_" + str(len(modules)) + ".json", {name: modules[name]})
        facts["gc_after_native_imports"] = {
            "enabled": gc.isenabled(),
            "threshold": gc.get_threshold(),
            "stats": gc.get_stats(),
        }
        facts["modules"] = modules
        facts["sha256_backend_module"] = type(hashlib.sha256()).__module__
        write("RUNTIME_FACTS.json", facts)
        from safe_geocoding_pipeline.preprocessing.stages import (
            s12_public_checkpoints as cp,
            s12_public_sampling_contract as contract,
        )
        from safe_geocoding_pipeline.preprocessing.stages import (
            s12_transport as transport,
        )

        def deny(*_args, **_kwargs):
            raise PermissionError("AP_FACTS_DENIED")

        transport.Secret.runtime = deny
        transport.Secret.private_file = deny
        transport.send = deny

        def ring(schema):
            budget.charge(0)  # reserve the checkpoint directory before its mkdir
            checkpoint = cp.Checkpoints(
                output / schema,
                row_schema=cp.AP_SCHEMA if schema == "ap" else cp.PUBLIC_SCHEMA,
                interval_seconds=600,
                budget_charge=budget.charge,
            )
            try:
                for n in range(1, LIMITS["ring_rows"] + 1):
                    check()
                    if schema == "ap":
                        row = timing_row(contract, n)
                    else:
                        row = [1, "PERIODIC", "COMPLETE", 1, n] + [
                            n * 50_000_000 + i for i in range(22)
                        ]
                    checkpoint.record(row)
                    if n % 64 == 0:
                        checkpoint.flush(timeout_seconds=120)
                with checkpoint._condition:
                    result = owned_graph(checkpoint._rows)
                    result.update(
                        retained_rows=len(checkpoint._rows),
                        observed_rows=checkpoint._observed,
                        note="SYNTHETIC_TIMING_ASSOCIATIONS_NO_ORIGINAL_EVENTS_NOT_AP_WORKFLOW",
                    )
                # Same128-row first encoding shape that CP byte-splitting
                # checks AFTER encoding, recorded separately from saved32KiB.
                with checkpoint._condition:
                    chunk = [[n, row] for n, row in list(checkpoint._rows)[-128:]]
                result["untrimmed128row_encoding_bytes"] = len(canonical(chunk))
                write(schema.upper() + "_RING_GRAPH.json", result)
                checkpoint.close(timeout_seconds=120)
                checkpoint._thread.join(timeout=1)
                require(not checkpoint._thread.is_alive())
                prefix = cp.read_prefix(output / schema)
                write(schema.upper() + "_CHECKPOINT_PREFIX.json", prefix)
                require(not prefix["incomplete"])
                return result
            finally:
                check()

        old = ring("legacy")
        gc.collect()
        new = ring("ap")
        write(
            "REPRESENTATION_COMPARISON.json",
            {
                "legacy": old["reported_owned_graph_bytes"],
                "ap": new["reported_owned_graph_bytes"],
                "difference": new["reported_owned_graph_bytes"]
                - old["reported_owned_graph_bytes"],
                "component_reservation_bytes": 16 * 2**20,
                "interpretation": "OBSERVED_RETAINED_OBJECT_GRAPH_ONLY_NOT_UPPER_BOUND_NOT_MATCHED_WORKFLOW_PERFORMANCE",
                "allocation_inventory_record_issued": False,
            },
        )
        write(
            "OUTCOME.json",
            {
                "status": "CHARACTERIZATION_COMPLETION_INTENT_REQUIRE_JOB_EXIT_ZERO",
                "elapsed_ns": time.monotonic_ns() - started,
                "limits": LIMITS,
                "peaks_observed_until_pre_outcome_watermark": dict(peaks),
                "pre_outcome_charged_file_data_bytes": budget.bytes,
                "pre_outcome_charged_creations": budget.creations,
                "audit_creation_attempts": audit_creates[0],
                "runtime_code_read_bytes": code_read,
                "ap_invocations": 0,
                "service_attempts": 0,
                "bounds_proved": False,
                "diagnostic_processes": 1,
                "metadata_python_invocations": 3,
                "launcher_command_invocations_max": 24,
            },
        )
        return 0
    except BaseException:
        try:
            write(
                "FAILED.json",
                {
                    "status": "FAILED_OR_INCOMPLETE",
                    "elapsed_ns": time.monotonic_ns() - started,
                    "cause": "UNCLASSIFIED_STATIC_NO_EXCEPTION_TEXT",
                    "peaks": peaks,
                },
            )
        except BaseException:
            pass
        return 1
    finally:
        stop.set()
        watcher.join(timeout=1)
        if watcher.is_alive() or time.monotonic_ns() >= deadline:
            raise SystemExit(95)


if __name__ == "__main__":
    raise SystemExit(main())
