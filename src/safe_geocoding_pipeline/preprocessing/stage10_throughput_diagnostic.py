"""One compute-only performance experiment; never a Stage 10 materializer.

Recover only a verified private copy of the failed database/WAL. Instrument
unchanged functions; only fixed aggregate keys reach reports. No candidate seal.
"""

from __future__ import annotations

import argparse
import cProfile
import hashlib
import json
import os
import re
import resource
import signal
import stat
import subprocess
import threading
import time
from collections import Counter
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Iterator, cast
from unittest.mock import patch

import duckdb
import pyarrow.parquet as pq

from ..execution_policy import require_goethe_nhr_slurm
from .stages import s08_address_evidence as s8
from .stages import s09_reference_input as a8
from .stages import s09_reference_io as base_io
from .stages import s10_query_contexts as cx
from .stages import s10_query_contract as c
from .stages import s10_query_execution as ex
from .stages import s10_query_families as families
from .stages import s10_query_input as inputs
from .stages import s10_query_io as io
from .stages import s10_query_publication as publication
from .stages import s10_query_transliteration as tr

ORIGINAL = "f83480d60449bcc904c0c622e394e12df3c3f2d9"
FAILED = "stage10_development_20260915T142128Z_f83480d60449_4v1m114k"
ATTEMPT_SHA = "fe5451fabd7bb942ba96aa51e46d11299341679acdcc2eb45ea6d7fdabce9504"
INPUT_SHA = "531d512f6c177fb5a9d6cd262e66846cdfd5cc66ba818c5aba8030165648878e"
CONTEXT_SECONDS = 45
TOTAL_SECONDS = 1500


def open_snapshot(path: Path, spill: Path) -> Any:
    spill.mkdir(mode=0o700)
    db = duckdb.connect(
        str(path),
        config={
            "memory_limit": "8GB",
            "threads": "4",
            "autoinstall_known_extensions": "false",
            "autoload_known_extensions": "false",
            "preserve_insertion_order": "false",
            "temp_directory": str(spill),
        },
    )
    db.execute("SET disabled_filesystems='HTTPFileSystem'")
    db.execute("SET temp_directory=" + io.sql_literal(str(spill)))
    return db


class DiagnosticLimit(Exception):
    """A measurement time cap, never a scientific reason code."""


@contextmanager
def deadline(seconds: float, interrupt: Any = None) -> Iterator[None]:
    hit = threading.Event()
    stopped = threading.Event()

    def expired(signum: int, frame: Any) -> None:
        hit.set()
        raise DiagnosticLimit("DIAGNOSTIC_TIME_CAP")

    def stop_query() -> None:
        if stopped.wait(seconds):
            return
        hit.set()
        # An interrupt racing query startup can be cleared by the engine.
        # Repeat only after this local diagnostic deadline until the owner
        # thread leaves the scope. This never polls or controls SLURM jobs.
        while not stopped.is_set():
            interrupt()
            if stopped.wait(0.1):
                return

    prior = signal.signal(signal.SIGALRM, expired)
    timer = threading.Thread(target=stop_query) if interrupt is not None else None
    if timer is not None:
        timer.daemon = True
        timer.start()
    # Let native cancellation finish before delivering a Python exception.
    # Simultaneous SIGALRM/Interrupt calls can race engine signal handling.
    # The one-second grace also caps Python-only loops after a native deadline.
    signal.setitimer(signal.ITIMER_REAL, seconds + (1 if interrupt is not None else 0))
    try:
        yield
        if hit.is_set():
            raise DiagnosticLimit("DIAGNOSTIC_TIME_CAP")
    except BaseException:
        # DuckDB can translate a pending Python alarm into RuntimeError rather
        # than InterruptException. The private deadline event is the authority.
        if hit.is_set():
            raise DiagnosticLimit("DIAGNOSTIC_TIME_CAP") from None
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        if timer is not None:
            stopped.set()
            timer.join()
        signal.signal(signal.SIGALRM, prior)


class Metrics:
    def __init__(self) -> None:
        self.values: dict[str, dict[str, int | float]] = {}

    @contextmanager
    def measure(self, name: str) -> Iterator[None]:
        start, cpu = time.perf_counter(), time.process_time()
        try:
            yield
        finally:
            item = self.values.setdefault(
                name, {"calls": 0, "wall_seconds": 0.0, "cpu_seconds": 0.0}
            )
            item["calls"] += 1
            item["wall_seconds"] += time.perf_counter() - start
            item["cpu_seconds"] += time.process_time() - cpu


def query_class(sql: str) -> str:
    # Labels, never SQL text or parameters, enter metrics.
    if sql in ("BEGIN TRANSACTION", "COMMIT", "ROLLBACK"):
        return "sql_" + sql.lower().replace(" ", "_")
    if sql.startswith("INSERT INTO selector_selection"):
        return "sql_selector_insert"
    if sql.startswith("DELETE FROM selector_selection"):
        return "sql_selector_clear"
    if sql.startswith("INSERT INTO stage10_context_diagnostics"):
        return "sql_context_diagnostic_insert"
    for token, name in (
        ("FROM stage10_components", "components"),
        ("FROM stage10_source_reference", "source_reference"),
        ("FROM stage10_members", "members"),
        ("FROM selector_selection", "selector_sort"),
        ("FROM stage10_context_keys k JOIN", "context_join"),
        ("FROM stage10_objects", "object"),
        ("FROM stage10_capabilities", "capability"),
        ("FROM stage10_registry", "registry"),
    ):
        if token in sql:
            return "sql_" + name
    return "sql_other"


class TimedDB:
    def __init__(self, db: Any, metrics: Metrics, cursors: Any = None) -> None:
        self.raw, self.metrics = db, metrics
        self.cursors = {} if cursors is None else cursors
        self.cursors[id(self.raw)] = self.raw

    def cursor(self) -> TimedDB:
        with self.metrics.measure("cursor_create"):
            return TimedDB(self.raw.cursor(), self.metrics, self.cursors)

    def interrupt(self) -> None:
        # DuckDB cursor() returns a separate connection/query context.
        for cursor in tuple(self.cursors.values()):
            cursor.interrupt()

    def execute(self, sql: str, parameters: Any = None) -> TimedDB:
        with self.metrics.measure(query_class(sql)):
            if parameters is None:
                self.raw.execute(sql)
            else:
                self.raw.execute(sql, parameters)
        return self

    def fetchone(self) -> Any:
        with self.metrics.measure("fetchone"):
            return self.raw.fetchone()

    def to_arrow_reader(self, **kwargs: Any) -> Any:
        with self.metrics.measure("arrow_reader_create"):
            return self.raw.to_arrow_reader(**kwargs)

    def close(self) -> None:
        with self.metrics.measure("cursor_close"):
            self.cursors.pop(id(self.raw), None)
            self.raw.close()


@contextmanager
def instrument(metrics: Metrics) -> Iterator[None]:
    def wrapped(function: Any, label: str) -> Any:
        def call(*args: Any, **kwargs: Any) -> Any:
            name = args[1] if label == "family" else label
            with metrics.measure(name):
                result = function(*args, **kwargs)
            if label == "cache_lookup":
                with metrics.measure("cache_miss" if result is None else "cache_hit"):
                    pass
            return result

        return call

    targets = (
        (families, "_family", "family"),
        (families, "strip_units", "q5_alignment"),
        (tr.ICUTransliterator, "transform", "icu_transform"),
        (cx.ReferenceAccess, "witness_certificate", "witness_certificate"),
        (cx.ContextWorkspace, "parser_certificate", "parser_certificate"),
        (cx.ByteCache, "get", "cache_lookup"),
        (c, "identity", "hash_identity"),
        (c, "canonical", "canonical_json"),
        (c, "ordered_values", "ordered_values"),
        (s8, "parser_component_evidence_schema", "parser_schema"),
        (io, "validate_values", "validate_values"),
        (io, "check_identity", "check_identity"),
        (base_io.RelationWriter, "append", "writer_append"),
        (base_io.RelationWriter, "flush", "writer_flush"),
        (base_io.RelationWriter, "close", "writer_close"),
        (base_io, "fsync_directory", "fsync_directory"),
    )
    with ExitStack() as stack:
        for owner, name, label in targets:
            stack.enter_context(
                patch.object(owner, name, wrapped(getattr(owner, name), label))
            )
        yield


def copy_evidence(source: Path, target: Path) -> str:
    info = source.lstat()
    c.require(
        stat.S_ISREG(info.st_mode)
        and info.st_nlink == 1
        and info.st_uid == os.geteuid()
        and stat.S_IMODE(info.st_mode) == 0o600,
        "DIAGNOSTIC_SOURCE_TOPOLOGY",
    )
    digest = hashlib.sha256()
    descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as incoming:
        c.require(os.fstat(incoming.fileno()) == info, "DIAGNOSTIC_SOURCE_CHANGED")
        fd = os.open(
            target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(fd, "wb") as outgoing:
            for block in iter(lambda: incoming.read(8 * 1024 * 1024), b""):
                outgoing.write(block)
                digest.update(block)
            outgoing.flush()
            os.fsync(outgoing.fileno())
    after = source.lstat()
    c.require(
        (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        == (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ),
        "DIAGNOSTIC_SOURCE_CHANGED",
    )
    result = digest.hexdigest()
    c.require(c.sha256_file(target) == result, "DIAGNOSTIC_COPY_HASH_MISMATCH")
    return result


def select_contexts(db: Any) -> list[bytes]:
    return [
        r[0]
        for r in db.execute(
            "SELECT min(query_context_id) FROM stage10_context_keys GROUP BY substr(hex(query_context_id),1,1) ORDER BY min(query_context_id)"
        ).fetchall()
    ]


def parquet_state(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        stream.seek(-4, os.SEEK_END)
        footer = stream.read(4) == b"PAR1"
    if not footer:
        return {"footer_present": False, "rows": None}
    try:
        return {"footer_present": True, "rows": pq.ParquetFile(path).metadata.num_rows}
    except Exception:
        return {"footer_present": True, "rows": None}


def plan_operators(raw: str) -> dict[str, int]:
    counts: Counter[str] = Counter()

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for member in node:
                walk(member)
        elif isinstance(node, dict):
            name = node.get("name", "").strip()
            if re.fullmatch(r"[A-Z_ ]{1,80}", name):
                counts[name] += 1
            walk(node.get("children", []))

    walk(json.loads(raw))
    return dict(counts)


def profile_summary(profile: cProfile.Profile) -> list[dict[str, Any]]:
    import pstats

    rows = []
    stats: Any = pstats.Stats(profile)
    for (filename, line, function), values in stats.stats.items():
        # Only public repository function names. Never retain callers/arguments.
        if not filename.startswith(str(ex.REPOSITORY / "src")) or not re.fullmatch(
            r"[A-Za-z_<>][A-Za-z_0-9<>]*", function
        ):
            continue
        cc, nc, own, total, _ = values
        rows.append(
            {
                "file": Path(filename).name,
                "line": line,
                "function": function,
                "primitive_calls": cc,
                "calls": nc,
                "self_seconds": own,
                "cumulative_seconds": total,
            }
        )
    return sorted(rows, key=lambda r: r["cumulative_seconds"], reverse=True)[:60]


def preflight(executable: str, output: Path) -> Path:
    require_goethe_nhr_slurm("stage10-throughput-diagnostic")
    c.require_runtime()
    root = inputs.PROJECT_ALIAS.resolve(strict=True)
    c.require(
        re.fullmatch(r"[0-9a-f]{40}", executable) is not None,
        "DIAGNOSTIC_EXECUTABLE_INVALID",
    )
    for args, expected in (
        (["rev-parse", "HEAD"], executable),
        (["status", "--porcelain"], ""),
    ):
        result = subprocess.run(
            ["git", *args],
            cwd=ex.REPOSITORY,
            capture_output=True,
            text=True,
            check=True,
        )
        c.require(
            result.stdout.strip() == expected,
            "DIAGNOSTIC_CLEAN_EXACT_CHECKOUT_REQUIRED",
        )
    branch = subprocess.run(
        ["git", "symbolic-ref", "-q", "HEAD"], cwd=ex.REPOSITORY, capture_output=True
    )
    c.require(
        branch.returncode == 1 and os.environ.get("SLURM_RESTART_COUNT", "0") == "0",
        "DIAGNOSTIC_DETACHED_NO_RESTART_REQUIRED",
    )
    ex.verify_design(ex.REPOSITORY)
    inventory = c.read_json(
        ex.REPOSITORY
        / "docs/scientific_assets/stage10_implementation_inventory_v1.json"
    )
    for item in inventory["files"]:
        c.require(
            c.sha256_file(ex.REPOSITORY / item["path"]) == item["sha256"],
            "DIAGNOSTIC_ORIGINAL_EXECUTABLE_CHANGED",
        )
    c.require(
        output.parent == root / "derived/controlled/stage10/diagnostics"
        and re.fullmatch(r"stage10_throughput_[0-9TZ_a-f]+", output.name) is not None,
        "DIAGNOSTIC_OUTPUT_SCOPE_INVALID",
    )
    publication.check_parent(output)
    c.require(not os.path.lexists(output), "DIAGNOSTIC_OUTPUT_EXISTS")
    c.require(
        ex.mount_signature(output.parent)
        == ex.mount_signature(root / ex.STAGE09_RELATIVE),
        "DIAGNOSTIC_TOPOLOGY_CHANGED",
    )
    return root


def inspect_snapshot(db: Any, partial: Path) -> dict[str, Any]:
    def scalar(sql: str) -> int:
        return int(db.execute(sql).fetchone()[0])

    total = scalar("SELECT count(*) FROM stage10_context_keys")
    first = scalar(
        "SELECT count(*) FROM stage10_context_keys WHERE starts_with(hex(query_context_id),'0')"
    )
    seen = scalar("SELECT count(*) FROM stage10_context_diagnostics")
    distinct = scalar(
        "SELECT count(DISTINCT query_context_id) FROM stage10_context_diagnostics"
    )
    outside = scalar(
        "SELECT count(*) FROM stage10_context_diagnostics WHERE NOT starts_with(hex(query_context_id),'0')"
    )
    c.require(
        total == 69747 and seen == distinct and outside == 0,
        "DIAGNOSTIC_SNAPSHOT_CONTEXT_MISMATCH",
    )
    return {
        "total_contexts": total,
        "first_shard_contexts": first,
        "context_diagnostic_rows": seen,
        "completed_generation_lower_bound": max(0, seen - 1),
        "completed_generation_upper_bound": seen,
        "generated_decision_lower_bound": 6 * max(0, seen - 1),
        "generated_decision_upper_bound": 6 * seen,
        "hypotheses_produced": None,
        "hypotheses_produced_upper_bound": 5 * seen,
        "partial_decisions": parquet_state(partial),
        "selector_rows_after_recovery": scalar(
            "SELECT count(*) FROM selector_selection"
        ),
        "role_counts": dict(
            db.execute(
                "SELECT stage08_representation,count(*) FROM stage10_context_keys GROUP BY 1"
            ).fetchall()
        ),
        "snapshot_tables": {
            table: scalar("SELECT count(*) FROM " + table)
            for table in (
                "stage10_components",
                "stage10_source_reference",
                "stage10_members",
                "stage10_objects",
            )
        },
    }


def process_io() -> dict[str, int]:
    path = Path("/proc/self/io")
    if not path.exists():
        return {}
    return {
        key: int(value)
        for line in path.read_text().splitlines()
        for key, value in [line.split(":")]
        if key in ("rchar", "wchar", "read_bytes", "write_bytes", "syscr", "syscw")
    }


def failure_metadata(error: BaseException) -> dict[str, Any]:
    frames = []
    trace = error.__traceback__
    while trace is not None:
        filename = Path(trace.tb_frame.f_code.co_filename)
        if filename.is_relative_to(ex.REPOSITORY / "src"):
            frames.append({"file": filename.name, "line": trace.tb_lineno})
        trace = trace.tb_next
    code = (
        "DIAGNOSTIC_TIME_CAP"
        if isinstance(error, DiagnosticLimit)
        else str(error)
        if isinstance(error, c.Stage10Error) and re.fullmatch("[A-Z0-9_]+", str(error))
        else "DIAGNOSTIC_OPERATIONAL_FAILURE"
    )
    return {
        "failure_code": code,
        "failure_class": type(error).__name__,
        "failure_frames": frames,
    }


def bounded_upstream_reads(
    db: Any, chosen: list[bytes], metrics: Metrics
) -> dict[str, Any]:
    db.execute("CREATE TABLE diagnostic_selected(query_context_id BLOB PRIMARY KEY)")
    db.executemany("INSERT INTO diagnostic_selected VALUES (?)", [[v] for v in chosen])
    db.execute(
        "CREATE VIEW diagnostic_selected_keys AS SELECT k.* FROM stage10_context_keys k JOIN diagnostic_selected USING(query_context_id)"
    )
    result = {}
    for view, key, columns in (
        (
            "candidate_evidence",
            "stage06_exact_candidate_id",
            "* EXCLUDE(stage07_libpostal_components)",
        ),
        ("parser_component_evidence", "stage06_exact_candidate_id", "*"),
        ("source_candidate_map", "stable_source_row_id_v1", "*"),
        (
            "stage06_row_map",
            "stable_source_row_id_v1",
            ",".join(inputs.row_projection_schema().names),
        ),
        ("candidate_reference_evidence", "stable_source_row_id_v1", "*"),
    ):
        rows = size = 0
        limited = False
        cursor = db.cursor()
        try:
            with metrics.measure("input_read_" + view), deadline(60, cursor.interrupt):
                reader = cursor.execute(
                    f"SELECT {columns} FROM {view} WHERE {key} IN (SELECT {key} FROM diagnostic_selected_keys)"
                ).to_arrow_reader(batch_size=1)
                for batch in reader:
                    rows += batch.num_rows
                    size += batch.nbytes
                    if rows >= 100000 or size >= 64 * 1024 * 1024:
                        limited = True
                        break
        except DiagnosticLimit:
            limited = True
        finally:
            cursor.close()
        result[view] = {
            "decoded_rows": rows,
            "decoded_bytes": size,
            "diagnostic_limited": limited,
        }
    return result


def reconcile_limit(work: cx.ContextWorkspace) -> None:
    try:
        work.db.execute("ROLLBACK")
    except duckdb.TransactionException:
        pass  # No active transaction is expected after normal witness rollback.
    # Prove transaction ownership is clear before another measured context.
    work.db.execute("BEGIN TRANSACTION")
    work.db.execute("ROLLBACK")
    assert work.reference is not None
    work.reference.cache = cx.ByteCache()
    work.reference.certificates = cx.ByteCache(1024 * 1024)
    work.parser_certificates = cx.ByteCache(1024 * 1024)


def run(executable: str, output: Path) -> dict[str, Any]:
    root = preflight(executable, output)
    output.mkdir(mode=0o700)
    metrics = Metrics()
    start = time.monotonic()
    report: dict[str, Any] = {
        "status": "DIAGNOSTIC_INCOMPLETE",
        "original_executable": ORIGINAL,
        "diagnostic_executable": executable,
        "job_id": os.environ["SLURM_JOB_ID"],
        "selection": "MIN_CONTEXT_ID_PER_EXISTING_HEX_PREFIX_V1",
        "context_target": 16,
        "context_seconds_limit": CONTEXT_SECONDS,
        "phase": "preflight",
        "candidate_publication": False,
        "operating_budget": None,
        "timings_are_inclusive": True,
    }
    db = runtime = None
    profile = cProfile.Profile()

    def terminated(signum: int, frame: Any) -> None:
        raise DiagnosticLimit("DIAGNOSTIC_TERMINATED")

    previous_term = signal.signal(signal.SIGTERM, terminated)
    before_io = process_io()

    def record(name: str) -> None:
        report["elapsed_seconds"] = time.monotonic() - start
        report["timings"] = metrics.values
        report["max_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        now = process_io()
        report["process_io_delta"] = {k: now[k] - v for k, v in before_io.items()}
        io.write_json(output / name, report)

    try:
        with ex.offline_network():
            failed = inputs.controlled_path(
                root / ex.PUBLISH_RELATIVE / "work" / FAILED
            )
            c.require(
                c.sha256_file(failed / "attempt.json") == ATTEMPT_SHA,
                "DIAGNOSTIC_ATTEMPT_CHANGED",
            )
            attempt = c.read_json(failed / "attempt.json")
            c.require(
                attempt["execution_git_sha"] == ORIGINAL
                and attempt["job_id"] == "1772639"
                and attempt["input_binding_sha256"] == INPUT_SHA,
                "DIAGNOSTIC_ATTEMPT_BINDING_INVALID",
            )
            for rel, name, digest in (
                (
                    ex.STAGE08_RELATIVE,
                    "stage08_address_evidence_manifest.json",
                    a8.STAGE08_MANIFEST_SHA256,
                ),
                (
                    ex.STAGE09_RELATIVE,
                    "stage09_reference_manifest.json",
                    inputs.STAGE09_MANIFEST,
                ),
            ):
                c.require(
                    c.sha256_file(root / rel / name) == digest,
                    "DIAGNOSTIC_UPSTREAM_MANIFEST_CHANGED",
                )
            stage06 = (
                root
                / "derived/controlled/stage06/development/stage06_development_20260828T223804Z_f39047cc825d"
            )
            c.require(
                c.sha256_file(stage06 / "stage06_manifest.json")
                == inputs.STAGE06_MANIFEST,
                "DIAGNOSTIC_UPSTREAM_MANIFEST_CHANGED",
            )
            with metrics.measure("exact_runtime"):
                runtime = ex.runtime_ready(root / ex.RUNTIME_RELATIVE, ex.REPOSITORY)
                for script, value, expected in tr.SYNTHETIC_VECTORS:
                    c.require(
                        runtime.transform(script, value) == expected,
                        "DIAGNOSTIC_PUBLIC_RUNTIME_VECTOR_MISMATCH",
                    )
            report["public_icu_vectors_passed"] = len(tr.SYNTHETIC_VECTORS)
            work_root = output / "workspace"
            work_root.mkdir(mode=0o700)
            report["phase"] = "snapshot_copy"
            with metrics.measure("snapshot_copy"):
                report["snapshot_hashes"] = {
                    name: copy_evidence(failed / "workspace" / name, work_root / name)
                    for name in ("context.duckdb", "context.duckdb.wal")
                }
            record("after_copy.json")
            report["phase"] = "snapshot_recovery"
            with metrics.measure("snapshot_recovery"), deadline(300):
                db = open_snapshot(work_root / "context.duckdb", work_root / "spill")
            with metrics.measure("preserved_inspection"), deadline(120, db.interrupt):
                report["preserved"] = inspect_snapshot(
                    db,
                    failed
                    / "workspace/shards/0/query_family_decision/part-000000.parquet",
                )
                chosen = select_contexts(db)
                c.require(len(chosen) == 16, "DIAGNOSTIC_SELECTION_COUNT_INVALID")
                report["selection_sha256"] = c.identity(
                    "stage10-diagnostic-selection:v1", tuple(chosen)
                ).hex()
                # IDs remain inside controlled diagnostic artifacts only.
                io.write_json(
                    output / "protected_selection.json",
                    {"context_ids": [v.hex() for v in chosen]},
                )
            record("preserved_evidence.json")
            report["phase"] = "bounded_input_reads"
            report["input_reads"] = bounded_upstream_reads(db, chosen, metrics)
            # Read plans with private parameters; retain operators only.
            example = db.execute(
                "SELECT stable_source_row_id_v1,stage06_exact_candidate_id FROM stage10_context_keys WHERE query_context_id=?",
                [chosen[0]],
            ).fetchone()
            c.require(example is not None, "DIAGNOSTIC_SELECTION_MISSING")
            assert example is not None
            report["plans"] = {}
            for label, query, args in (
                (
                    "source_reference",
                    "SELECT * FROM stage10_source_reference WHERE stable_source_row_id_v1=? AND stage06_exact_candidate_id=? ORDER BY evidence_id",
                    list(example),
                ),
                (
                    "components",
                    "SELECT * FROM stage10_components WHERE stage06_exact_candidate_id=? ORDER BY stage08_component_ordinal",
                    [example[1]],
                ),
            ):
                plan_row = db.execute("EXPLAIN (FORMAT JSON) " + query, args).fetchone()
                c.require(plan_row is not None, "DIAGNOSTIC_PLAN_MISSING")
                assert plan_row is not None
                plan = plan_row[1]
                report["plans"][label] = plan_operators(plan)
            db.execute("DROP TABLE selector_selection")
            db.execute("DELETE FROM stage10_context_diagnostics")
            work = object.__new__(cx.ContextWorkspace)

            class Binding:
                identifier = bytes.fromhex(INPUT_SHA)
                context_binding = c.identity(
                    "stage10-context-input:v1",
                    bytes.fromhex(a8.STAGE08_MANIFEST_SHA256),
                    bytes.fromhex(inputs.STAGE06_MANIFEST),
                    bytes.fromhex(inputs.STAGE09_MANIFEST),
                )

            work.accepted = cast(Any, Binding())
            work.root, work.science = (
                work_root,
                c.science_fingerprint(runtime.asset_binding),
            )
            work.db = cast(Any, TimedDB(db, metrics))
            work.reference = cx.ReferenceAccess(work.db)
            work.parser_certificates = cx.ByteCache(1024 * 1024)
            report.update(
                phase="generation",
                completed_contexts=0,
                limited_contexts=0,
                hypotheses=0,
                family_decisions=0,
                family_eligible={q: 0 for q in c.FAMILIES},
                family_calls={q: 0 for q in c.FAMILIES},
            )
            serial = output / "serializations"
            serial.mkdir(mode=0o700)
            profile.enable()
            with instrument(metrics):
                for ordinal, selected in enumerate(chosen):
                    if time.monotonic() - start > TOTAL_SECONDS:
                        break
                    stream: Any = work.contexts(selected.hex()[0])
                    try:
                        with deadline(
                            min(
                                CONTEXT_SECONDS,
                                max(1, TOTAL_SECONDS - (time.monotonic() - start)),
                            ),
                            work.db.interrupt,
                        ):
                            with metrics.measure("context_construction"):
                                context = next(stream)
                            c.require(
                                context.identifier == selected,
                                "DIAGNOSTIC_SELECTION_DRIFT",
                            )
                            with metrics.measure("family_generation"):
                                hypotheses, decisions = families.generate(
                                    context, runtime
                                )
                            with metrics.measure("serialization_and_close"):
                                unit = serial / f"context-{ordinal:02}"
                                unit.mkdir(mode=0o700)
                                for name, rows in zip(
                                    c.RELATIONS, (hypotheses, decisions), strict=True
                                ):
                                    writer = io.RelationWriter(
                                        unit / name, io.output_schema(name)
                                    )
                                    for row in rows:
                                        io.validate_values(row, name)
                                        io.check_identity(
                                            row,
                                            name,
                                            work.accepted.context_binding,
                                            work.accepted.identifier,
                                            work.science,
                                        )
                                        writer.append(row)
                                    writer.close()
                            report["completed_contexts"] += 1
                            report["hypotheses"] += len(hypotheses)
                            report["family_decisions"] += len(decisions)
                            for decision in decisions:
                                report["family_calls"][decision["family"]] += 1
                                report["family_eligible"][decision["family"]] += (
                                    decision["eligibility_state"] == "ELIGIBLE"
                                )
                    except DiagnosticLimit:
                        report["limited_contexts"] += 1
                        stream.close()
                        reconcile_limit(work)
                    finally:
                        stream.close()
                    record(f"progress-{ordinal:02}.json")
            profile.disable()
            report["profile"] = profile_summary(profile)
            report["status"] = (
                "DIAGNOSTIC_COMPLETE"
                if report["completed_contexts"] == 16
                else "DIAGNOSTIC_COMPLETE_WITH_LIMITS"
            )
    except BaseException as error:
        profile.disable()
        report["status"] = (
            "DIAGNOSTIC_LIMITED"
            if isinstance(error, DiagnosticLimit)
            else "DIAGNOSTIC_FAILED"
        )
        report.update(failure_metadata(error))
        report["profile"] = profile_summary(profile) if profile.getstats() else []
    finally:
        record("diagnostic_result.json")
        if db is not None:
            db.close()
        if runtime is not None:
            runtime.close()
        signal.signal(signal.SIGTERM, previous_term)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-git-sha", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = run(args.execution_git_sha, args.output)
    except BaseException:
        print("STAGE10_DIAGNOSTIC_PREFLIGHT_FAILED")
        return 1
    print(report["status"])
    return 0 if report["status"].startswith("DIAGNOSTIC_COMPLETE") else 1


if __name__ == "__main__":
    raise SystemExit(main())
