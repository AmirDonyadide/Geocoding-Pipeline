"""Finite RA-G1 control-source/read/check compiler; never an authority issuer.

Inputs are complete original source/backend inventories. Backend stat identities
are preparation-host provenance, never a compute-host identity claim. Scientific
input/artifact readers and native internal I/O require their own phase bounds.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
import stat
from typing import Any

VERSION = "stage12_ra_g1_accounting_inventory_v1"
BOOTSTRAP_VERSION = "stage12_ra_g1_bootstrap30_accounting_inventory_v1"
SHARED_LEASE_VERSION = "stage12_ra_g1_shared_lease_accounting_inventory_v1"
REP_ADMIN_VERSION = "stage12_ra_g1_rep_admin_budget_accounting_inventory_v1"
REP512_VERSION = "stage12_ra_g1_rep_first64_512_accounting_inventory_v1"
REP_FOREGROUND_VERSION = "stage12_ra_g1_rep_foreground_accounting_inventory_v1"
REP_ACK_VERSION = "stage12_ra_g1_rep_ack_queue_accounting_inventory_v1"
REP_FAIR_VERSION = "stage12_ra_g1_rep_fair_service_accounting_inventory_v1"
FOREGROUND_MAX_BYTES = 2**20
FOREGROUND_EXTRA_SNAPSHOT_BYTES = 4096
FOREGROUND_MEMBERS = (
    ('DIAGNOSTIC', 'scripts/stage12_ra_g1_diagnostic.py'),
    ('PUBLIC_RESPONSE', 'src/safe_geocoding_pipeline/preprocessing/stages/s12_public_response.py'),
    ('PUBLIC_RUNTIME', 'src/safe_geocoding_pipeline/preprocessing/stages/s12_public_runtime.py'),
    ('PUBLIC_AUTHORITY', 'src/safe_geocoding_pipeline/preprocessing/stages/s12_ra_g1_public.py'),
    ('PUBLIC_SAMPLING', 'src/safe_geocoding_pipeline/preprocessing/stages/s12_public_sampling.py'),
    ('PUBLIC_SCHEDULER', 'src/safe_geocoding_pipeline/preprocessing/stages/s12_public_scheduler.py'),
    ('PUBLIC_OPERATIONS', 'src/safe_geocoding_pipeline/preprocessing/stages/s12_public_operations.py'),
    ('PUBLIC_RECOVERY', 'src/safe_geocoding_pipeline/preprocessing/stages/s12_public_recovery.py'),
    ('RETRIEVAL_GUARD', 'src/safe_geocoding_pipeline/preprocessing/stages/s12_retrieval_contract.py'),
    ('RESPONSE_GUARD', 'src/safe_geocoding_pipeline/preprocessing/stages/s12_response.py'),
    ('RA_ASSURANCE', 'src/safe_geocoding_pipeline/preprocessing/stages/s12_ra_g1_assurance.py'),
    ('RA_CONTRACT', 'src/safe_geocoding_pipeline/preprocessing/stages/s12_ra_g1_contract.py'),
    ('PROBE_CLI', 'src/safe_geocoding_pipeline/preprocessing/stage12_probe_cli.py'),
    ('RA_EXECUTION', 'src/safe_geocoding_pipeline/preprocessing/stages/s12_ra_g1_execution.py'),
)

REP_ACK_FOREGROUND_MEMBERS = tuple(
    (module, "src/safe_geocoding_pipeline/preprocessing/stages/s12_ra_g1_rep_ack_contract.py"
     if module == "RA_CONTRACT" else relative)
    for module, relative in FOREGROUND_MEMBERS
)
REP_FAIR_FOREGROUND_MEMBERS = tuple(
    (module, "src/safe_geocoding_pipeline/preprocessing/stages/s12_ra_g1_rep_fair_contract.py"
     if module == "RA_CONTRACT" else relative)
    for module, relative in FOREGROUND_MEMBERS
)


MAX_U = 2**64 - 1
SOURCE_MAX = 64 * 2**20
METADATA_MAX = 4 * 2**20
CONTROL_MAX = 65536
KERNEL_MAX = 8192
RAW_MAX = 15360
CODEC = 1024
MODULES = ("_hashlib", "_ssl", "_sqlite3", "_duckdb", "pyarrow.lib")
IDENTITY = (
    "device",
    "inode",
    "mode",
    "uid",
    "gid",
    "nlink",
    "bytes",
    "mtime_ns",
    "ctime_ns",
)
SCOPES = (
    "REPRESENTATIVE_NO_SERVICE",
    "PUBLIC_SYNTHETIC_ONLY",
    "DEVELOPMENT_ONLY",
    "DEVELOPMENT_LOCAL_PREPARATION",
)
# Actual builder durations, not enlarged parser maxima. Any selected longer
# scope requires a newly compiled graph/source review; unspent rows stay charged.
GRAPHS: dict[str, dict[str, Any]] = {
    "REPRESENTATIVE_NO_SERVICE": dict(
        graph="REPRESENTATIVE_EIGHT_STREAMS_V1",
        monitor_liability=16342,
        stages=[
            (1, 346000, 2),
            (2, 300000, 2),
            (3, 180000, 2),
            (4, 180000, 2),
            (5, 120000, 2),
            (6, 120000, 3),
            (7, 600000, 3),
            (8, 120000, 3),
        ],
        sources=[
            ("COLLECTOR_READY_AND_ACTUAL_OPEN", 2),
            ("BINDER_ENTRY_BUILD_AND_ACTUAL_OPEN", 3),
            ("WORKER_ENTRY_FOUR_ACTUAL_OPENERS_AND_WHOLE_OPEN", 6),
            ("FINAL_VERIFIER", 1),
        ],
        backends=[("COLLECTOR", 1), ("WORKER_INITIAL_AND_FOUR_ACTUAL_OPENERS", 5)],
        phases=4,
        attempts=535,
        events=50597,
        creations=184184,
        logical_bytes=72 * 2**30,
        role_records=11,
        recipes=8,
        monitor_scopes=9,
    ),
    "PUBLIC_SYNTHETIC_ONLY": dict(
        graph="PUBLIC_THIRTEEN_STREAMS_V1",
        monitor_liability=16352,
        stages=[
            *[(i, 500000, 2) for i in range(1, 11)],
            (11, 180000, 2),
            (12, 2000000, 2),
            (13, 840000, 2),
        ],
        sources=[
            ("SETUP_COLLECT_AND_ACTUAL_OPEN", 2),
            ("AUTHORITY_CONSTRUCTOR", 1),
            ("ELEVEN_PHASE_FENCES_AND_WHOLE_ACTUAL_OPEN", 12),
            ("FINAL_VERIFIER", 1),
        ],
        backends=[
            ("SETUP_COLLECT", 1),
            ("RUNTIME_INITIAL_AND_ELEVEN_REOPEN_CHECKS", 12),
        ],
        phases=11,
        attempts=2960,
        events=262220,
        creations=791452,
        logical_bytes=512 * 2**30,
        role_records=11,
        recipes=8,
        monitor_scopes=14,
    ),
}
ACCOUNTING_KEYS = (
    "identity_calls",
    "original_read_calls",
    "original_read_bytes",
    "check_calls",
)


class AccountingError(RuntimeError):
    pass


def need(condition: bool, code: str = "RA_G1_ACCOUNTING_INVALID") -> None:
    if not condition:
        raise AccountingError(code)


def uint(value: Any, *, positive: bool = False) -> int:
    need(
        type(value) is int and int(positive) <= value <= MAX_U,
        "RA_G1_ACCOUNTING_OVERFLOW",
    )
    return int(value)


def add(*values: int) -> int:
    return uint(sum(uint(value) for value in values))


def mul(*values: int) -> int:
    result = 1
    for value in values:
        result = uint(result * uint(value))
    return result


def canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def sha(value: Any) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and set(value) <= set("0123456789abcdef")
        and set(value) != {"0"}
    )


def validate_sources(rows: Any) -> list[dict[str, Any]]:
    need(type(rows) is list and 1 <= len(rows) <= 2048, "RA_G1_ACCOUNTING_SOURCES")
    copied = []
    for row in rows:
        need(
            type(row) is dict and set(row) == {"path", "bytes", "sha256"},
            "RA_G1_ACCOUNTING_SOURCES",
        )
        path = row["path"]
        need(
            type(path) is str
            and 0 < len(path.encode("utf8")) <= 512
            and not PurePosixPath(path).is_absolute()
            and str(PurePosixPath(path)) == path
            and ".." not in PurePosixPath(path).parts
            and sha(row["sha256"]),
            "RA_G1_ACCOUNTING_SOURCES",
        )
        copied.append(dict(path=path, bytes=uint(row["bytes"]), sha256=row["sha256"]))
    need(
        [r["path"] for r in copied] == sorted({r["path"] for r in copied})
        and add(*(r["bytes"] for r in copied)) <= SOURCE_MAX,
        "RA_G1_ACCOUNTING_SOURCES",
    )
    return copied


def validate_backends(rows: Any) -> list[dict[str, Any]]:
    """Reuse genuine A2 preparation rows; dev/ino are explicitly host-local."""
    need(type(rows) is list and len(rows) == 5, "RA_G1_ACCOUNTING_BACKENDS_UNAVAILABLE")
    copied = []
    for ordinal, (row, name) in enumerate(zip(rows, MODULES, strict=True), 1):
        need(
            type(row) is dict
            and set(row)
            == {"ordinal", "module", "path", "identity", "stat_scope", "sha256"}
            and row["ordinal"] == ordinal
            and type(row["ordinal"]) is int
            and row["module"] == name
            and row["stat_scope"] == "PREPARATION_HOST_SNAPSHOT"
            and sha(row["sha256"]),
            "RA_G1_ACCOUNTING_BACKENDS_UNAVAILABLE",
        )
        path = row["path"]
        need(
            type(path) is str
            and PurePosixPath(path).is_absolute()
            and str(PurePosixPath(path)) == path
            and ".." not in PurePosixPath(path).parts
            and len(path.encode("utf8")) <= 4096,
            "RA_G1_ACCOUNTING_BACKENDS_UNAVAILABLE",
        )
        ident = row["identity"]
        need(
            type(ident) is dict and set(ident) == set(IDENTITY),
            "RA_G1_ACCOUNTING_BACKENDS_UNAVAILABLE",
        )
        identity = {key: uint(ident[key]) for key in IDENTITY}
        need(
            stat.S_ISREG(identity["mode"])
            and identity["nlink"] >= 1
            and identity["bytes"] > 0,
            "RA_G1_ACCOUNTING_BACKENDS_UNAVAILABLE",
        )
        copied.append(
            dict(
                ordinal=ordinal,
                module=name,
                path=path,
                identity=identity,
                stat_scope=row["stat_scope"],
                sha256=row["sha256"],
            )
        )
    need(len({r["path"] for r in copied}) == 5, "RA_G1_ACCOUNTING_BACKENDS_UNAVAILABLE")
    return copied


def stream_bound(size: int, *, failure_byte: bool = True) -> dict[str, int]:
    """A2 byte-short stream: one call/byte plus EOF, optional growth byte."""
    size = uint(size)
    return dict(read_calls=add(size, 1), read_bytes=add(size, int(failure_byte)))


def _compile_strict_inventory(
    sources: Any, backends: Any, scope: str, *, rep_admin_successor: bool = False,
    first64_512_successor: bool = False
) -> tuple[dict[str, Any], dict[str, int] | None]:
    sources, backends = validate_sources(sources), validate_backends(backends)
    need(scope in SCOPES, "RA_G1_ACCOUNTING_SCOPE")
    inventory: dict[str, Any] = dict(
        schema_version=VERSION,
        scope=scope,
        sources=sources,
        backends=backends,
        source_inventory_sha256=digest(sources),
        backend_inventory_sha256=digest(backends),
        backend_identity_scope="PREPARATION_ONLY_NOT_COMPUTE_IDENTITY",
        supported_scope="FIXED_APPLICATION_CONTROL_SOURCE_AND_EXPLICIT_MONITOR_IO",
        excluded_io="SCIENTIFIC_ORIGINAL_READERS_REQUIRE_SEPARATE_PHASE_BOUNDS_NATIVE_INTERNAL_IO_NOT_PROVEN",
        execution_permission="NOT_ISSUED",
        cost_rows=[],
        monitor_streams=[],
        accounting=None,
        stage_accounting=[],
        graph_id="UNISSUED",
        status="UNISSUED_SELECTED_PROTECTED_COMMAND_HISTORY_GRAPH_REQUIRED",
        proof_count={},
    )
    if scope not in GRAPHS:
        return inventory, None
    graph = GRAPHS[scope]
    if rep_admin_successor:
        need(scope == "REPRESENTATIVE_NO_SERVICE", "RA_G1_ACCOUNTING_SCOPE")
        graph = {**graph, "stages": [
            (phase, 480000 if phase == 7 else 240000 if phase == 8 else duration, passes)
            for phase, duration, passes in graph["stages"]]}
    if first64_512_successor:
        need(rep_admin_successor and scope == "REPRESENTATIVE_NO_SERVICE", "RA_G1_ACCOUNTING_SCOPE")
        graph = {**graph, "stages": [
            (phase, 512000 if phase == 1 else duration, passes)
            for phase, duration, passes in graph["stages"]],
            "events": 57237, "creations": 204860}
    inventory["status"] = "DERIVED_NUMERIC_ENVELOPE_REQUIRES_ORIGINAL_SOURCE_REVIEW"
    inventory["graph_id"] = graph["graph"]
    rows: list[dict[str, Any]] = inventory["cost_rows"]
    rep = scope == "REPRESENTATIVE_NO_SERVICE"
    phase_count = 4 if rep else 11
    tail = 9 if rep else 14
    setup = 6 if rep else 13
    stage_ids = list(range(1, tail + 1))

    def cost(
        stage: int,
        name: str,
        count: int,
        reads: int,
        size: int,
        checks: int,
        basis: str,
    ) -> None:
        count, reads, size, checks = (uint(x) for x in (count, reads, size, checks))
        rows.append(
            dict(
                stage_id=stage,
                component=name,
                invocations=count,
                per_invocation_read_calls=reads,
                per_invocation_read_bytes=size,
                per_invocation_checks=checks,
                basis=basis,
                original_read_calls=mul(count, reads),
                original_read_bytes=mul(count, size),
                check_calls=mul(count, checks),
            )
        )

    source_size = add(*(r["bytes"] for r in sources))
    internal_parents = add(*(len(PurePosixPath(r["path"]).parts) - 1 for r in sources))
    # Each internal parent is checked before and after the full read. Each
    # visit has one deadline checkpoint and one require predicate; one final
    # parent-list equality predicate follows per source file. Existing six
    # per-file entry/fd/path/stat guards remain independently reserved.
    parent_checks_per_sweep = add(mul(4, internal_parents), len(sources))
    backend_size = add(*(r["identity"]["bytes"] for r in backends))
    source_passes = (
        {6: 2, 7: 1, 8: 2, 1: 2, 2: 1, 3: 1, 4: 1, 5: 1, 9: 1}
        if rep
        else {13: 2, 1: 2, **{i: 1 for i in range(2, 13)}, 14: 1}
    )
    backend_passes = (
        {6: 1, 1: 2, 2: 1, 3: 1, 4: 1}
        if rep
        else {13: 1, 1: 2, **{i: 1 for i in range(2, 12)}}
    )
    for stage, count in source_passes.items():
        calls = add(source_size, len(sources))
        cost(
            stage,
            "EXACT_FULL_SOURCE_SWEEPS",
            count,
            calls,
            add(source_size, len(sources)),
            add(mul(3, calls), mul(6, len(sources)), parent_checks_per_sweep),
            "RUN_SOURCES_AUTHORITY_FENCE_BYTE_SHORT_EOF_AND_EXACT_PRE_POST_INTERNAL_PARENT_GUARDS",
        )
    for stage, count in backend_passes.items():
        calls = add(backend_size, 5)
        cost(
            stage,
            "EXACT_FULL_BACKEND_SWEEPS",
            count,
            calls,
            add(backend_size, 5),
            add(mul(3, calls), 30),
            "FIVE_IMPORTED_BACKEND_FULL_HASH_PASSES_INITIAL_AND_REAL_REOPEN_FD_PATH_POSTSTAT",
        )

    kernel = stream_bound(KERNEL_MAX)
    record = stream_bound(8192)
    control = stream_bound(CONTROL_MAX)
    metadata = stream_bound(METADATA_MAX)
    monitor_rows = validation_rows = 0
    for phase, duration, passes in graph["stages"]:
        count = add((duration + 499) // 500, 2)
        parents = (
            ([7, 9] if phase == 6 else [1, 9] if phase in (7, 8) else [9])
            if rep
            else [14]
        )
        need(passes == 1 + len(parents), "RA_G1_ACCOUNTING_GRAPH_CHANGED")
        inventory["monitor_streams"].append(
            dict(
                phase_id=phase,
                deadline_ms=duration,
                maximum_rows=count,
                full_original_validation_passes=passes,
                parent_stage_ids=parents,
            )
        )
        monitor_rows = add(monitor_rows, count)
        validation_rows = add(validation_rows, mul(count, passes))
        cost(
            phase,
            "MONITOR_KERNEL_PROC_ORIGINALS",
            mul(count + 1, 12),
            kernel["read_calls"],
            kernel["read_bytes"],
            add(mul(3, kernel["read_calls"]), 2),
            "TWELVE_8192_CAPPED_ORIGINALS_PER_ROW_PLUS_FIRST_REJECTED_ACQUISITION_EOF_INCLUDED",
        )
        cost(
            phase,
            "MONITOR_NATIVE_VISIBLE_STATS",
            count + 1,
            0,
            0,
            64,
            "AT_MOST_64_SELECTED_VISIBLE_STAT_CALLBACKS_NOT_NATIVE_COMPLETENESS",
        )
        cost(
            phase,
            "MONITOR_WRITER_ORIGINAL_AND_CODEC_READBACK",
            count,
            5,
            RAW_MAX + CODEC,
            RAW_MAX + CODEC + 14,
            "FOUR_FIXED_ORIGINAL_PREADS_ONE_CODEC_PREAD_AND_BYTE_SHORT_WRITES",
        )
        cost(
            phase,
            "MONITOR_FIRST_GROWING_VALIDATION",
            count,
            3,
            RAW_MAX + CODEC,
            6,
            "ORIGINAL_FULL_READ_EOF_AND_SCALAR_CODEC_FRESH_WORKER_PASS",
        )
        cost(
            phase, "MONITOR_FIRST_GROWING_EOF", 1, 1, 1, 2, "ONE_ACTUAL_FULL_STREAM_EOF"
        )
        cost(
            phase,
            "PHASE_FOUR_IMMUTABLE_DAG_WRITES",
            4,
            record["read_calls"],
            record["read_bytes"],
            8192 + 3 * record["read_calls"] + 14,
            "PREOPEN_OPENER_MONITOR_TERMINAL_WORKER_PROOF_WRITE_READBACK",
        )
        cost(
            phase,
            "PHASE_FIXED_OPERATIONS",
            1,
            0,
            0,
            64,
            "R8A_64_FINITE_ADMIN_OPERATIONS",
        )
        cost(
            phase,
            "CURRENT_SUPERVISOR_ENTRY",
            12,
            kernel["read_calls"],
            kernel["read_bytes"],
            3 * kernel["read_calls"] + 2,
            "CURRENT_DOMAIN_AND_REGISTERED_STAT_STATUS_CGROUP_ROSTER",
        )
        cost(
            phase,
            "ORIGINAL_CONTEXT_ENTRY",
            1,
            control["read_calls"],
            control["read_bytes"],
            3 * control["read_calls"] + 2,
            "ONE_EXACT_SUPERVISOR_CONTEXT_ORIGINAL",
        )
        for parent in parents:
            cost(
                parent,
                "FRESH_MONITOR_VALIDATION_PHASE_" + str(phase),
                count,
                3,
                RAW_MAX + CODEC,
                6,
                "INDEPENDENT_PARENT_RAW_ORIGINAL_AND_CODEC_REOPEN_ADMIN_THIRD_SCAN_EXPLICIT",
            )
            cost(
                parent,
                "FRESH_MONITOR_EOF_PHASE_" + str(phase),
                1,
                1,
                1,
                2,
                "ACTUAL_FRESH_STREAM_EOF",
            )
            cost(
                parent,
                "ORIGINAL_DAG_REOPEN_PHASE_" + str(phase),
                4,
                record["read_calls"],
                record["read_bytes"],
                3 * record["read_calls"] + 2,
                "FOUR_PHASE_PROTOCOL_ORIGINALS_NOT_CACHED_BOOLEAN",
            )
            cost(
                parent,
                "PARENT_TERMINAL_PHASE_" + str(phase),
                1,
                record["read_calls"],
                record["read_bytes"],
                8192 + 3 * record["read_calls"] + 14,
                "EXCLUSIVE_TERMINAL_FSYNC_READBACK",
            )
            cost(
                parent,
                "PARENT_CURRENT_SUPERVISOR_PHASE_" + str(phase),
                12,
                kernel["read_calls"],
                kernel["read_bytes"],
                3 * kernel["read_calls"] + 2,
                "CURRENT_SOURCE_SUPERVISOR_NOT_DEAD_CHILD_PROC_ALIAS",
            )
            cost(
                parent,
                "PARENT_FIXED_OPERATIONS_PHASE_" + str(phase),
                1,
                0,
                0,
                64,
                "R8A_FINITE_SUFFIX_OPERATIONS",
            )
    need(
        monitor_rows <= graph["monitor_liability"]
        and validation_rows
        <= 2 * (graph["monitor_liability"] + 4 * graph["monitor_scopes"] + 16),
        "RA_G1_ACCOUNTING_MONITOR_LIABILITY",
    )

    attempts = [320, 160, 40, 15] if rep else [320] * 8 + [160, 160, 40]
    creations: dict[int, int] = {}
    logical: dict[int, int] = {}
    if rep:
        creations.update(
            dict(enumerate([57091, 44478, 24369, 23293, 30177, 760, 2488, 1528], 1))
        )
        if rep_admin_successor:
            creations[7] -= 480
            creations[8] += 480
        if first64_512_successor:
            creations[1] = 77767
        durations = [512000 if first64_512_successor else 346000, 300000, 180000, 180000]
    else:
        durations = [500000] * 10 + [180000]
    for phase, (duration, q) in enumerate(zip(durations, attempts, strict=True), 1):
        observations = (duration + 49) // 50 + 2
        files = 4 * observations + 8
        sample = 4096 * files + 8 * (512 * files + 4096)
        logical[phase] = (
            (q + 1) * 2**27
            if rep
            else (52 if phase <= 8 else 28 if phase <= 10 else 8) * 2**30
        ) + sample
        if not rep:
            timing = (observations + q + 16 + 55) // 56 + (duration + 4999) // 5000 + 3
            events = 19 * q + 40 + 2 * observations + 4
            creations[phase] = (
                files
                + 8
                + events
                + 24 * q
                + 128
                + timing
                + 2 * ((duration + 499) // 500 + 2)
                + 4
            )
    if rep:
        logical.update({5: 16 * 2**20, 6: 16 * 2**20, 7: 32 * 2**20, 8: 16 * 2**20})
    else:
        for phase, duration, reserved, extra in (
            (12, 2000000, 64 * 2**20, 128),
            (13, 840000, 160 * 2**20, 2048),
            (14, 120000, 256 * 2**20, 4096),
        ):
            logical[phase] = reserved
            creations[phase] = 2 * ((duration + 499) // 500 + 2) + 4 + extra
        residual = 791452 - sum(creations.values())
        need(residual >= 0, "RA_G1_ACCOUNTING_GRAPH_CHANGED")
        creations[12] += residual
    role_n = 5 if rep else 6
    for phase, q in enumerate(attempts, 1):
        runtime_calls = phase_count + 1 if phase == 1 else 1
        runtime_records = 4 + 7 * (role_n + 3) + 1 + 5
        records = (
            runtime_calls * runtime_records
            + q * (role_n + 2 + 4)
            + 12 * (role_n + 1)
            + 3 * role_n
        )
        if (rep and phase == 3) or (not rep and phase == 11):
            records += 8 * role_n
        if rep:
            records += 4  # independent current-facts initial pair at actual opener.
        cost(
            phase,
            "AUTHORITY_RUNTIME_START_DISPATCH_RECORDS",
            records,
            control["read_calls"],
            control["read_bytes"],
            3 * control["read_calls"] + 2,
            "SEVEN_RUNTIME_GRANTS_FIVE_B_OR_SIX_PUBLIC_SOURCE_ROLES_BOUND_REVIEW_CURRENT_FACTS_FIXED_START_PATHS",
        )
        facts = runtime_calls + q + int(rep)
        cost(
            phase,
            "CURRENT_ENVIRONMENT_KERNEL_ORIGINALS",
            facts * 6,
            kernel["read_calls"],
            kernel["read_bytes"],
            3 * kernel["read_calls"] + 2,
            "SIX_CANONICAL_BOOT_MEMBERSHIP_MEMORY_SWAP_PID_PATHS_PER_CURRENT_FACT_CHECK",
        )
    for phase, maximum in creations.items():
        # One capacity prewrite path: sampling bound/review2 + capacity5.
        # Dispatch's zero-creation prewrite is a separate, actual call site.
        q = attempts[phase - 1] if phase <= phase_count else 0
        cost(
            phase,
            "PREWRITE_ORIGINAL_RESOURCE_BINDINGS",
            7 * (maximum + q),
            control["read_calls"],
            control["read_bytes"],
            3 * control["read_calls"] + 2,
            "SEVEN_ORIGINALS_PER_CREATION_GUARD_PLUS_DISPATCH_ZERO_CREATION_BARRIER",
        )
    for phase, size in logical.items():
        cost(
            phase,
            "APPLICATION_BYTE_SHORT_WRITE_GUARDS",
            1,
            0,
            0,
            size,
            "ONE_CHECK_PER_CHARGED_APPLICATION_WRITE_BYTE_NO_NATIVE_INTERNAL_WRITE_BOUND",
        )
    metadata_partitions = (
        {6: (32 * 2**20, 256), 8: (160 * 2**20, 1024), 9: (32 * 2**20, 128)}
        if rep
        else {13: (128 * 2**20, 1400), 14: (96 * 2**20, 128)}
    )
    fresh_metadata = (
        {6: 2 * 256, 7: 256, 8: 2 * 1024, 9: 1408} if rep else {13: 2 * 1400, 14: 1400}
    )
    for phase, (size, files) in metadata_partitions.items():
        cost(
            phase,
            "NON_B_METADATA_WRITE_READBACK",
            1,
            size + files,
            size,
            4 * size + 14 * files,
            "A2_EXACT_NON_B_STAGE_PARTITION_BYTE_SHORT_WRITES_AND_FULL_READBACK",
        )
    for phase, count in fresh_metadata.items():
        cost(
            phase,
            "NON_B_ORIGINAL_METADATA_OPENERS",
            count,
            metadata["read_calls"],
            metadata["read_bytes"],
            3 * metadata["read_calls"] + 2,
            "FREEZE_REAL_OPENER_PREDECESSOR_AND_FINAL_OPEN_FILE_PARTITIONS",
        )
    external = {6: 14, 7: 4, 8: 8, 9: 6} if rep else {13: 28, 14: 4}
    for phase, count in external.items():
        cost(
            phase,
            "SELECTION_REVIEW_RELEASE_AND_SUPERVISOR_ORIGINALS",
            count,
            metadata["read_calls"],
            metadata["read_bytes"],
            3 * metadata["read_calls"] + 2,
            "FIXED_SOURCE_SELECTION_REVIEW_RELEASE_LAUNCH_AND_RETURN_PATHS",
        )
    cost(
        setup,
        "BOOTSTRAP_KERNEL_AND_CONTEXT_CAPTURE",
        16,
        kernel["read_calls"],
        kernel["read_bytes"],
        3 * kernel["read_calls"] + 2,
        "TWO_SIX_RECORD_CURRENT_FACTS_READS_PLUS_BOOTSTRAP_FOUR_ROLE_CONTEXT_RECORDS",
    )
    if rep_admin_successor:
        for phase, duration, component in (
            (7, 480000, "REVIEW_WAIT_CHECKPOINTS"),
            (8, 240000, "BINDER_RELEASE_WAIT_CHECKPOINTS"),
        ):
            cost(phase, component, 1, 0, 0, duration // 250 + 2,
                 "ACTUAL_250MS_SOURCE_SLEEP_WITH_FIRST_REJECTED_POLL_NONRESETTING_SCOPE")
    else:
        cost(
            7 if rep else 13,
            "REVIEW_WAIT_CHECKPOINTS",
            1,
            0,
            0,
            600000 // (50 if rep else 100) + 2,
            "DECLARED_600S_WAIT_MINIMUM_SOURCE_SLEEP_AND_FIRST_REJECTION",
        )
    for phase in [6, 8] if rep else [12]:
        cost(
            phase,
            "SOURCE_OWNED_FINAL_HANDOFF_SUFFIX",
            1,
            2,
            65536 if rep else 8192,
            7 if rep else 3,
            "EXCLUSIVE_FULL_WRITE_FSYNC_FULL_READ_EOF_AND_GENUINE_SUCCESSFUL_SOURCE_EXIT_SUFFIX",
        )
    stage_rows = []
    for phase in stage_ids:
        own = [r for r in rows if r["stage_id"] == phase]
        checks = add(*(r["check_calls"] for r in own), 2)
        stage_rows.append(
            dict(
                stage_id=phase,
                identity_calls=checks,
                original_read_calls=add(*(r["original_read_calls"] for r in own)),
                original_read_bytes=add(*(r["original_read_bytes"] for r in own)),
                check_calls=checks,
            )
        )
    accounting = {key: add(*(r[key] for r in stage_rows)) for key in ACCOUNTING_KEYS}
    inventory["stage_accounting"] = stage_rows
    inventory["accounting"] = accounting
    inventory["proof_count"] = dict(
        source_files=len(sources),
        backend_files=5,
        cost_rows=len(rows),
        actual_monitor_streams=len(graph["stages"]),
        actual_monitor_rows=monitor_rows,
        selected_monitor_row_liability=graph["monitor_liability"],
        fresh_monitor_row_validations=validation_rows,
        full_source_sweeps=sum(source_passes.values()),
        source_internal_parent_entries=internal_parents,
        source_parent_guard_checks_per_full_sweep=parent_checks_per_sweep,
        full_backend_sweeps=sum(backend_passes.values()),
    )
    need(len(canonical(inventory)) <= METADATA_MAX, "RA_G1_ACCOUNTING_METADATA_LIMIT")
    return inventory, accounting


def stage_accounting(inventory: Any, stage_id: int) -> dict[str, int]:
    """Return exactly the selected stage's three positive numeric reader caps."""
    validate_inventory(inventory)
    need(inventory["accounting"] is not None, "RA_G1_ACCOUNTING_GRAPH_UNISSUED")
    matches = [r for r in inventory["stage_accounting"] if r["stage_id"] == stage_id]
    need(len(matches) == 1, "RA_G1_ACCOUNTING_STAGE")
    row = matches[0]
    return dict(
        source_read_calls=uint(row["original_read_calls"], positive=True),
        source_read_bytes=uint(row["original_read_bytes"], positive=True),
        check_calls=uint(row["check_calls"], positive=True),
    )


def validate_inventory(inventory: Any) -> dict[str, Any]:
    need(type(inventory) is dict, "RA_G1_ACCOUNTING_INVALID")
    expected, _ = compile_inventory(
        inventory["sources"], inventory["backends"], inventory["scope"],
        bootstrap_successor=(inventory.get("schema_version") == BOOTSTRAP_VERSION
            or inventory.get("schema_version") in (SHARED_LEASE_VERSION, REP_ADMIN_VERSION, REP512_VERSION, REP_FOREGROUND_VERSION, REP_ACK_VERSION, REP_FAIR_VERSION)
            and inventory.get("bootstrap_proof_record_count") == 3),
        shared_lease_successor=inventory.get("schema_version") in (SHARED_LEASE_VERSION, REP_ADMIN_VERSION, REP512_VERSION, REP_FOREGROUND_VERSION, REP_ACK_VERSION, REP_FAIR_VERSION),
        rep_admin_successor=inventory.get("schema_version") in (REP_ADMIN_VERSION, REP512_VERSION, REP_FOREGROUND_VERSION, REP_ACK_VERSION, REP_FAIR_VERSION),
        first64_512_successor=inventory.get("schema_version") in (REP512_VERSION, REP_FOREGROUND_VERSION, REP_ACK_VERSION, REP_FAIR_VERSION),
        foreground_successor=inventory.get("schema_version") in (REP_FOREGROUND_VERSION, REP_ACK_VERSION, REP_FAIR_VERSION),
        ack_queue_successor=inventory.get("schema_version") == REP_ACK_VERSION,
        fair_service_successor=inventory.get("schema_version") == REP_FAIR_VERSION,
    )
    need(inventory == expected, "RA_G1_ACCOUNTING_CHANGED")
    return dict(inventory)


def _strict_descriptor() -> dict[str, Any]:
    return dict(
        descriptor_version=VERSION,
        closed=True,
        live_instance=False,
        maximum_canonical_bytes=METADATA_MAX,
        outer_fields=[
            "schema_version",
            "scope",
            "sources",
            "backends",
            "source_inventory_sha256",
            "backend_inventory_sha256",
            "backend_identity_scope",
            "supported_scope",
            "excluded_io",
            "execution_permission",
            "cost_rows",
            "monitor_streams",
            "accounting",
            "stage_accounting",
            "status",
            "proof_count",
            "graph_id",
        ],
        source_row_fields=["path", "bytes", "sha256"],
        maximum_source_files=2048,
        maximum_source_bytes=SOURCE_MAX,
        backend_modules=list(MODULES),
        backend_row_fields=[
            "ordinal",
            "module",
            "path",
            "identity",
            "stat_scope",
            "sha256",
        ],
        backend_identity_fields=list(IDENTITY),
        backend_identity_scope="PREPARATION_ONLY_NOT_COMPUTE_IDENTITY",
        accounting_fields=list(ACCOUNTING_KEYS),
        proof_count_fields=[
            "source_files",
            "backend_files",
            "cost_rows",
            "actual_monitor_streams",
            "actual_monitor_rows",
            "selected_monitor_row_liability",
            "fresh_monitor_row_validations",
            "full_source_sweeps",
            "full_backend_sweeps",
            "source_internal_parent_entries",
            "source_parent_guard_checks_per_full_sweep",
        ],
        stage_cap_fields=["source_read_calls", "source_read_bytes", "check_calls"],
        stage_row_fields=["stage_id", *ACCOUNTING_KEYS],
        cost_row_fields=[
            "stage_id",
            "component",
            "invocations",
            "per_invocation_read_calls",
            "per_invocation_read_bytes",
            "per_invocation_checks",
            "basis",
            "original_read_calls",
            "original_read_bytes",
            "check_calls",
        ],
        monitor_stream_fields=[
            "phase_id",
            "deadline_ms",
            "maximum_rows",
            "full_original_validation_passes",
            "parent_stage_ids",
        ],
        formula="CHECKED_UINT64_A2_ONE_BYTE_SHORT_READ_PLUS_EOF_AND_BYTE_SHORT_WRITE_GUARDS",
        monitor_original_maximum_bytes=RAW_MAX,
        monitor_codec_bytes=CODEC,
        monitor_kernel_records_per_row=12,
        monitor_kernel_record_maximum_bytes=KERNEL_MAX,
        monitor_visible_stat_callbacks_per_row=64,
        unsupported_protected_graph="UNISSUED_SELECTED_PROTECTED_COMMAND_HISTORY_GRAPH_REQUIRED",
        execution_permission="NOT_ISSUED",
    )


def _compile_bootstrap_inventory(sources: Any, backends: Any, scope: str, *, bootstrap_successor: bool = False, rep_admin_successor: bool = False, first64_512_successor: bool = False) -> tuple[dict[str, Any], Any]:
    inventory, accounting = _compile_strict_inventory(sources, backends, scope, rep_admin_successor=rep_admin_successor,
        first64_512_successor=first64_512_successor)
    if not bootstrap_successor:
        return inventory, accounting
    need(scope == "REPRESENTATIVE_NO_SERVICE" and accounting is not None, "RA_G1_ACCOUNTING_SCOPE")
    inventory["schema_version"] = BOOTSTRAP_VERSION
    inventory["graph_id"] += "_BOOTSTRAP30"
    def extra(stage, component, count, reads, size, checks, basis):
        inventory["cost_rows"].append(dict(stage_id=stage, component=component, invocations=count,
            per_invocation_read_calls=reads, per_invocation_read_bytes=size, per_invocation_checks=checks,
            basis=basis, original_read_calls=mul(count,reads), original_read_bytes=mul(count,size), check_calls=mul(count,checks)))
    record = stream_bound(8192)
    for stage in (6,7,1):
        extra(stage,"BOOTSTRAP_ORIGINAL_WRITE_READBACK",1,record["read_calls"],record["read_bytes"],
              8192+3*record["read_calls"]+14,"ONE_8192_PRECHARGED_ORIGINAL_WITHIN_EXISTING_ADMIN_RESERVE")
        extra(stage,"BOOTSTRAP_ADOPTION_AND_READINESS_ORIGINALS",17,record["read_calls"],record["read_bytes"],
              3*record["read_calls"]+2,"ONE_ADOPTION_CREATION_READ_PLUS_EIGHT_CAPPED_TWO_ORIGINAL_READINESS_CALLS")
    for stage,count in ((7,1),(1,1),(9,3)):
        extra(stage,"BOOTSTRAP_PARENT_FRESH_ORIGINALS",count,record["read_calls"],record["read_bytes"],
              3*record["read_calls"]+2,"ACTUAL_PARENT_AND_FINAL_VERIFIER_BOOTSTRAP_REOPENS")
    for stage in inventory["stage_accounting"]:
        own=[r for r in inventory["cost_rows"] if r["stage_id"]==stage["stage_id"]]
        stage.update(original_read_calls=add(*(r["original_read_calls"] for r in own)),
            original_read_bytes=add(*(r["original_read_bytes"] for r in own)),
            check_calls=add(*(r["check_calls"] for r in own),2))
        stage["identity_calls"]=stage["check_calls"]
    accounting={key:add(*(r[key] for r in inventory["stage_accounting"])) for key in ACCOUNTING_KEYS}
    inventory["accounting"]=accounting
    inventory["proof_count"]["cost_rows"]=len(inventory["cost_rows"])
    inventory["bootstrap_proof_record_count"]=3
    need(len(canonical(inventory))<=METADATA_MAX,"RA_G1_ACCOUNTING_METADATA_LIMIT")
    return inventory,accounting


def _bootstrap_descriptor(*, bootstrap_successor: bool = False) -> dict[str,Any]:
    value = _strict_descriptor()
    if bootstrap_successor:
        value = {**value, "descriptor_version": BOOTSTRAP_VERSION,
            "outer_fields": [*value["outer_fields"], "bootstrap_proof_record_count"],
            "bootstrap_proof_record_count": 3, "bootstrap_readiness_calls_per_phase": 8,
            "existing_admin_reserve": "THREE_ADDITIONAL_8192_RECORDS_NO_CAP_INCREASE"}
    return value



def compile_inventory(sources: Any, backends: Any, scope: str, *,
                      bootstrap_successor: bool = False,
                      shared_lease_successor: bool = False,
                      rep_admin_successor: bool = False,
                       first64_512_successor: bool = False,
                      foreground_successor: bool = False,
                      ack_queue_successor: bool = False,
                      fair_service_successor: bool = False) -> tuple[dict[str, Any], Any]:
    """Explicit current writer primitive; historical grammars remain unchanged."""
    need(not (ack_queue_successor and fair_service_successor), "RA_G1_ACCOUNTING_SCOPE")
    need(not (ack_queue_successor or fair_service_successor) or foreground_successor, "RA_G1_ACCOUNTING_SCOPE")
    need(not first64_512_successor or rep_admin_successor, "RA_G1_ACCOUNTING_SCOPE")
    need(not foreground_successor or (first64_512_successor and scope == "REPRESENTATIVE_NO_SERVICE"), "RA_G1_ACCOUNTING_SCOPE")
    need(not rep_admin_successor or (scope == "REPRESENTATIVE_NO_SERVICE"
        and bootstrap_successor and shared_lease_successor), "RA_G1_ACCOUNTING_SCOPE")
    inventory, accounting = _compile_bootstrap_inventory(
        sources, backends, scope, bootstrap_successor=bootstrap_successor,
        rep_admin_successor=rep_admin_successor, first64_512_successor=first64_512_successor)
    if not shared_lease_successor:
        return inventory, accounting
    need(scope in GRAPHS and accounting is not None, "RA_G1_ACCOUNTING_SCOPE")
    inventory["schema_version"] = SHARED_LEASE_VERSION
    inventory["graph_id"] += "_SHARED_READBACK512"
    inventory.setdefault("bootstrap_proof_record_count", 0)
    chunks = (RAW_MAX + 511) // 512
    for row in inventory["cost_rows"]:
        if row["component"] == "MONITOR_WRITER_ORIGINAL_AND_CODEC_READBACK":
            row["per_invocation_read_calls"] = chunks + 1
            row["per_invocation_checks"] = RAW_MAX + CODEC + 10 + chunks
            row["basis"] = "THIRTY_512_ORIGINAL_PREADS_ONE_CODEC_PREAD_BYTE_SHORT_WRITES_NO_NEW_EOF"
            row["original_read_calls"] = mul(row["invocations"], chunks + 1)
            row["check_calls"] = mul(row["invocations"], row["per_invocation_checks"])
    if rep_admin_successor:
        inventory["schema_version"] = REP_ADMIN_VERSION
        inventory["graph_id"] += "_REP_ADMIN_480_240"
        inventory["rep_admin_budget"] = dict(
            collector_seconds=120, review_seconds=480, binder_seconds=240,
            binder_process_seconds=720, poll_sleep_ms=250,
            adoption_metadata=dict(stage_id=8, maximum_bytes=8192, creations=1,
                reservation="SUBALLOCATED_EXISTING_160MIB_1024FILE_NON_B_STAGE8"))
        control = stream_bound(CONTROL_MAX)
        for phase in range(1, 9):
            inventory["cost_rows"].append(dict(stage_id=phase,
                component="REP_ADMIN_ADOPTION_START_AND_ACTUAL_OPENER",
                invocations=2, per_invocation_read_calls=control["read_calls"],
                per_invocation_read_bytes=control["read_bytes"],
                per_invocation_checks=3 * control["read_calls"] + 2,
                basis="TWO_FRESH_ORIGINALS_VIA_EXISTING_BOUNDED_ADOPTION_READER",
                original_read_calls=mul(2, control["read_calls"]),
                original_read_bytes=mul(2, control["read_bytes"]),
                check_calls=mul(2, 3 * control["read_calls"] + 2)))
        inventory["cost_rows"].append(dict(stage_id=8,
            component="REP_ADMIN_ADOPTION_BINDER_DAG_REOPEN", invocations=1,
            per_invocation_read_calls=METADATA_MAX + 1,
            per_invocation_read_bytes=METADATA_MAX + 1,
            per_invocation_checks=3 * (METADATA_MAX + 1) + 2,
            basis="ONE_ADDITIONAL_RETAINED_ADOPTION_IN_ACTUAL_BINDER_DAG_OPEN",
            original_read_calls=METADATA_MAX + 1, original_read_bytes=METADATA_MAX + 1,
            check_calls=3 * (METADATA_MAX + 1) + 2))
        inventory["proof_count"]["cost_rows"] = len(inventory["cost_rows"])
    if first64_512_successor:
        inventory["schema_version"] = REP512_VERSION
        inventory["graph_id"] += "_FIRST64_512_EVENTS57237_CREATIONS204860"
        inventory["rep_first64_512"] = dict(first64_ms=512000,
            maximum_observations=10242, sampling_event_tokens=20488,
            phase1_events=26608, phase1_creations=77767,
            global_events=57237, global_creations=204860,
            other_stage_caps="UNCHANGED_INCLUDING_WHOLE_TASK_30177",
            adoption_metadata="ONE_ORIGINAL_WITHIN_EXISTING_METADATA_PARTITION")
        for row in list(inventory["cost_rows"]):
            if row["component"] in ("REP_ADMIN_ADOPTION_START_AND_ACTUAL_OPENER", "REP_ADMIN_ADOPTION_BINDER_DAG_REOPEN"):
                extra = dict(row)
                extra["component"] = row["component"].replace("REP_ADMIN_ADOPTION", "REP512_ADOPTION")
                inventory["cost_rows"].append(extra)
        inventory["proof_count"]["cost_rows"] = len(inventory["cost_rows"])
    if foreground_successor:
        selected = {row["path"]: row for row in inventory["sources"]}
        source_members = REP_FAIR_FOREGROUND_MEMBERS if fair_service_successor else REP_ACK_FOREGROUND_MEMBERS if ack_queue_successor else FOREGROUND_MEMBERS
        need(all(path in selected for _, path in source_members), "RA_G1_ACCOUNTING_FOREGROUND_SOURCES")
        members = [dict(module_id=module, **selected[path]) for module, path in source_members]
        size = add(*(row["bytes"] for row in members))
        need(size <= FOREGROUND_MAX_BYTES, "RA_G1_ACCOUNTING_FOREGROUND_SOURCES")
        count = len(members)
        parents = add(*(len(PurePosixPath(row["path"]).parts) - 1 for row in members))
        calls = add(size, count)
        # Each positive-one-byte/EOF read has one deadline, two charged read
        # guards (three predicates each), and its data/EOF predicate. Root walks
        # allow 64 ancestors plus the first rejected 65th attempt:132 checks per
        # walk; two walks and eight fixed entry/path/file/equality checks/file.
        checks = add(mul(8, calls), mul(4, parents), mul(272, count))
        inventory["cost_rows"].append(dict(stage_id=1,
            component="REP_FOREGROUND_ONCE_SELECTED_SOURCE_MAP", invocations=1,
            per_invocation_read_calls=calls, per_invocation_read_bytes=calls,
            per_invocation_checks=checks, original_read_calls=calls,
            original_read_bytes=calls, check_calls=checks,
            basis="ONCE_PRE_SESSION_PREFIX_TO_STAGE1_POSITIVE_ONE_BYTE_EOF_GROWTH_ROOT_PARENT_AND_DEADLINE_GUARDS"))
        inventory["schema_version"] = REP_FOREGROUND_VERSION
        inventory["graph_id"] += "_FOREGROUND_ONCE14_1MIB"
        inventory["rep_foreground"] = dict(stage_id=1, maximum_passes_per_process=1,
            maximum_members=14, maximum_source_bytes=FOREGROUND_MAX_BYTES,
            selected_members=members, selected_source_bytes=size,
            selected_internal_parent_entries=parents, source_root_ancestor_limit=64,
            first_rejected_root_ancestor_attempt=65,
            maximum_extra_snapshot_bytes=FOREGROUND_EXTRA_SNAPSHOT_BYTES,
            existing_summary_reservation_bytes=2**20,
            summary_original_passes="EXISTING_FULL_1MIB_PASSES_NO_ADDITIONAL_PASS_OR_CAP",
            native_memory_assurance="EXISTING_RA_G1_SCOPED_MONITORING_NOT_HARD_CONTAINMENT")
        inventory["proof_count"]["cost_rows"] = len(inventory["cost_rows"])
    if ack_queue_successor or fair_service_successor:
        if fair_service_successor:
            from . import s12_ra_g1_rep_fair_contract as contract
        else:
            from . import s12_ra_g1_rep_ack_contract as contract
        inventory["schema_version"] = REP_FAIR_VERSION if fair_service_successor else REP_ACK_VERSION
        inventory["graph_id"] += "_FAIR_OUTER_CHECKPOINT_SERVICE" if fair_service_successor else "_ACK_QUEUE_NO500MS_ACCEPTANCE"
        inventory["rep_fair_policy_sha256" if fair_service_successor else "rep_ack_policy_sha256"] = contract.POLICY_SHA
        adoption_component = "REP_FAIR_ADOPTION" if fair_service_successor else "REP_ACK_ADOPTION"
        # One additional exact adoption original follows every unchanged
        # REP512 adoption start/reopening pass, inside existing stage reserves.
        for row in list(inventory["cost_rows"]):
            if row["component"].startswith("REP512_ADOPTION"):
                inventory["cost_rows"].append({**row,"component":row["component"].replace("REP512_ADOPTION",adoption_component)})
        # Two actual native environment checks (precheck and after ready) read
        # one <=1MiB recovery proof, one <=64KiB review, and one <=128KiB
        # exact-source validator. Positive-one-byte progress and all3 EOF/growth
        # calls are bounded; no current paired outcome is substituted.
        direct_calls=add(2**20,65536,131072,3)
        inventory["cost_rows"].append(dict(stage_id=6,
            component=("REP_FAIR_DIRECT_GATE_FRESH_PROOF_REVIEW_AND_VALIDATOR" if fair_service_successor else "REP_ACK_DIRECT_GATE_FRESH_PROOF_REVIEW_AND_VALIDATOR"),invocations=2,
            per_invocation_read_calls=direct_calls,per_invocation_read_bytes=direct_calls,
            per_invocation_checks=add(mul(8,direct_calls),mul(272,3),1024),
            original_read_calls=mul(2,direct_calls),original_read_bytes=mul(2,direct_calls),
            check_calls=mul(2,add(mul(8,direct_calls),mul(272,3),1024)),
            basis="PRECHECK_AND_AFTER_READY_FULL_ORIGINALS_SOURCE_HASH_IDENTITY_EOF_PRIVATE_PARENT_NO_NEW_PASS_OR_CAP"))
        inventory["proof_count"]["cost_rows"] = len(inventory["cost_rows"])
    if fair_service_successor:
        # Each eligible outer boundary follows an existing charged I/O/deadline
        # check, or a precharged zero-byte creation/fsync. This deliberately
        # overbounds positive-one-byte reads and the fixed namespace scans.
        # New pair scheduling adds no observation/event/file beyond the already
        # selected cadence inventory. Deadline.check is the original clock-only
        # guard, not the charged source ledger; all existing pair I/O/postchecks
        # remain counted exactly once. Bound pure predicate work separately.
        eligible_caps = (77767, 44478, 24369, 23293)
        selected_durations = (512000, 300000, 180000, 180000)
        selected_attempt_liabilities = (320, 160, 40, 15)
        checkpoint_bounds = []
        for stage, (creations, duration, attempts) in enumerate(zip(eligible_caps, selected_durations, selected_attempt_liabilities), 1):
            existing = [row for row in inventory["cost_rows"] if row["stage_id"] == stage]
            source_reads = add(*(row["original_read_calls"] for row in existing))
            # Admission scans follow resource_prewrite -> sampling_bound ->
            # _resource_evidence, which charges at least one source-original
            # read. One final scan is outside that admission count. A scan
            # has root plus directory-entry callbacks over precharged entries.
            scans = add(source_reads, 1)
            scan_boundaries = mul(scans, add(mul(2, creations), 1))
            # Actual DATA complete/reopen: at most119 original invocations,
            # rounded to128; begin/finish writes/reserves at most32. Validators
            # visit bounded wire nodes in three passes; sixteen per wire byte
            # also covers fixed target/context checkpoints. Inherited64MiB
            # reader limits deliberately overbound the selected smaller inputs.
            per_attempt_boundaries = add(mul(128, 64 * 2**20 + 1), 32,
                                         mul(16, 64 * 2**20 + 1))
            action_boundaries = add(mul(attempts, per_attempt_boundaries), creations)
            boundaries = add(scan_boundaries, action_boundaries)
            observations = add((duration + 49) // 50, 2)
            checks = add(mul(128, boundaries), mul(64, observations))
            checkpoint_bounds.append(dict(stage_id=stage, maximum_outer_boundaries=boundaries,
                control_barrier_bounded_storage_scans=scans,
                scan_outer_boundaries=scan_boundaries,
                scientific_action_outer_boundaries=action_boundaries,
                DATA_original_read_invocations_per_attempt=128,
                DATA_inherited_reader_bytes=64 * 2**20,
                DATA_write_reserve_callbacks_per_attempt=32,
                DATA_validator_node_checks_per_wire_byte=16,
                maximum_pairs=observations, maximum_extra_pure_predicates=checks,
                charged_source_original_read_call_delta=0, charged_source_check_call_delta=0,
                scientific_tail_originals=mul(2, observations),
                scientific_tail_valid_original_bytes=mul(2, observations, 4096),
                scientific_tail_failure_inclusive_returned_bytes=mul(2, observations, 4097),
                scientific_tail_positive_one_byte_EOF_reads=mul(2, observations, 4097),
                scientific_tail_file_opens=mul(2, observations),
                scientific_tail_identity_predicates=mul(2, observations, 272),
                scientific_tail_clock_checks=mul(2, observations, 4129)))
        inventory["proof_count"]["cost_rows"] = len(inventory["cost_rows"])
        inventory["rep_fair_service"] = dict(
            checkpoint_guard_bounds=checkpoint_bounds,
            maximum_pairs_per_eligible_outer_checkpoint=1,
            maximum_serviced_pairs="UNCHANGED_SELECTED_MAXIMUM_OBSERVATIONS_PER_PHASE",
            extra_source_original_reads=0, extra_writes=0, extra_creations=0,
            scientific_tail_original_reads="AT_MOST_TWO_FULL_EVENT_READS_PER_SELECTED_OBSERVATION_SEPARATE_PHASE_QUOTE",
            scientific_tail_source_ledger_scope="EXCLUDED_IO_AS_DECLARED_SEPARATE_FINITE_SCIENTIFIC_PHASE_BOUNDS",
            scientific_tail_multiplicity="ONE_PINNED_TAIL_PER_EVENT_MONOTONE_SEQ_SINGLE_WRITER_FAILED_ACTION_NOT_RETRIED",
            scientific_tail_fixed_caps="UNCHANGED_EVENT_CREATION_BYTES_SCRATCH_ACTION_PHASE_AND_ORIGINAL_VALIDATION_GUARDS",
            pair_guards="OWNER_ACTIVE_THROUGH_RETURN_POST_GUARDS_AND_CREDIT_RETIREMENT",
            checkpoint_guards="ORIGINAL_CLOCK_ONLY_DEADLINE_AND_HEALTH_CALLS_UNCHANGED_EXTRA_PURE_SCRATCH_PAIR_OWNERSHIP",
            charged_source_and_check_ledger_delta=0,
            ordinary_progress="ONLY_EXISTING_EXPLICIT_COOPERATIVE_IO_OR_STORAGE_SCAN_BOUNDARIES",
            time_charge="ORIGINAL_OUTER_ACTION_OR_ORIGINAL_STANDALONE_PAIR_NO_CLOCK_RESET",
            logical_pair_active_scalar_bytes=8,
            temporary_object_native_overhead="RA_G1_SCOPED_ASSURANCE_NOT_PROVEN_NATIVE_BOUND",
            sample_ACK_witness_and_retirement="EXISTING_PER_OBSERVATION_COST_ROWS_NO_DUPLICATE_IO_CHARGE")
    for stage in inventory["stage_accounting"]:
        own = [r for r in inventory["cost_rows"] if r["stage_id"] == stage["stage_id"]]
        stage.update(
            original_read_calls=add(*(r["original_read_calls"] for r in own)),
            original_read_bytes=add(*(r["original_read_bytes"] for r in own)),
            check_calls=add(*(r["check_calls"] for r in own), 2))
        stage["identity_calls"] = stage["check_calls"]
    accounting = {
        key: add(*(r[key] for r in inventory["stage_accounting"]))
        for key in ACCOUNTING_KEYS}
    inventory["accounting"] = accounting
    need(len(canonical(inventory)) <= METADATA_MAX, "RA_G1_ACCOUNTING_METADATA_LIMIT")
    return inventory, accounting


def descriptor(*, bootstrap_successor: bool = False,
               shared_lease_successor: bool = False,
               rep_admin_successor: bool = False,
               first64_512_successor: bool = False,
               foreground_successor: bool = False,
               ack_queue_successor: bool = False,
                      fair_service_successor: bool = False) -> dict[str, Any]:
    if fair_service_successor:
        need(not ack_queue_successor and foreground_successor and first64_512_successor, "RA_G1_ACCOUNTING_SCOPE")
        from . import s12_ra_g1_rep_fair_contract as contract
        value = descriptor(first64_512_successor=True, foreground_successor=True)
        return {**value, "descriptor_version": REP_FAIR_VERSION,
            "outer_fields": [*value["outer_fields"], "rep_fair_policy_sha256", "rep_fair_service"],
            "source_map_members": [dict(module_id=m,path=p) for m,p in REP_FAIR_FOREGROUND_MEMBERS],
            "sampling_policy_sha256": contract.POLICY_SHA,
            "fair_service": "ONE_PAIR_PER_EXPLICIT_OUTER_SCRATCH_SAFE_CHECKPOINT_ORIGINAL_ACTION_DEADLINE",
            "extra_pair_IO": "SAMPLE_ACK_PAIR_COUNT_UNCHANGED_ADDITIONAL_PINNED_TAIL_ORIGINAL_READS_QUOTED_SEPARATELY",
            "scientific_tail_read_bound": "2_SELECTED_OBSERVATIONS_FULL4096_BYTES_WITH4097_ONE_BYTE_EOF_CALLS_EACH_SINGLE_MONOTONE_TAIL",
            "scientific_tail_checks": "272_IDENTITY_PREDICATES_AND4129_CLOCK_CHECKS_PER_FULL_EVENT_READ",
            "scientific_tail_source_ledger": "EXCLUDED_SCIENTIFIC_IO_NO_SOURCE_COUNTER_STOP_ENLARGEMENT",
            "additional_adoption_originals": "SAME_FINITE_REP512_START_OPEN_AND_BINDER_DAG_PASSES",
            "direct_gate_fresh_originals": {"passes":2,"stage_id":6,"proof_bytes":2**20,"review_bytes":65536,"validator_bytes":131072,"positive_one_byte_EOF_and_growth":True}}
    if ack_queue_successor:
        need(foreground_successor and first64_512_successor, "RA_G1_ACCOUNTING_SCOPE")
        from . import s12_ra_g1_rep_ack_contract as contract
        value = descriptor(first64_512_successor=True, foreground_successor=True)
        return {**value, "descriptor_version": REP_ACK_VERSION,
            "outer_fields": [*value["outer_fields"], "rep_ack_policy_sha256"],
            "source_map_members": [dict(module_id=m,path=p) for m,p in REP_ACK_FOREGROUND_MEMBERS],
            "sampling_policy_sha256": contract.POLICY_SHA,
            "ack_acceptance": "COMPLETE_DURABLE_PAIRS_WITHIN_UNCHANGED_ACTION_CLOSE_AND_CUMULATIVE_DEADLINES",
            "additional_adoption_originals": "SAME_FINITE_REP512_START_OPEN_AND_BINDER_DAG_PASSES",
            "direct_gate_fresh_originals": {"passes":2,"stage_id":6,"proof_bytes":2**20,"review_bytes":65536,"validator_bytes":131072,"positive_one_byte_EOF_and_growth":True}}
    if foreground_successor:
        need(first64_512_successor, "RA_G1_ACCOUNTING_SCOPE")
        value = descriptor(first64_512_successor=True)
        return {**value, "descriptor_version": REP_FOREGROUND_VERSION,
            "outer_fields": [*value["outer_fields"], "rep_foreground"],
            "maximum_source_map_passes_per_process":1, "source_map_stage_id":1,
            "source_map_members":[dict(module_id=m,path=p) for m,p in FOREGROUND_MEMBERS],
            "source_map_maximum_source_bytes":FOREGROUND_MAX_BYTES,
            "source_map_read_bound":"SELECTED_BYTES_PLUS_MEMBER_EOFS_AND_GROWTH_BYTES",
            "source_map_check_bound":"8_READ_CALLS+4_INTERNAL_PARENTS+272_MEMBERS",
            "source_root_ancestor_limit":64, "first_rejected_root_ancestor_attempt":65,
            "maximum_extra_snapshot_bytes":FOREGROUND_EXTRA_SNAPSHOT_BYTES,
            "existing_summary_reservation_bytes":2**20,
            "summary_original_passes":"UNCHANGED_FULL_1MIB_PASSES_NO_ADDITIONAL_PASS_OR_CAP"}
    if first64_512_successor:
        value = descriptor(rep_admin_successor=True)
        return {**value, "descriptor_version": REP512_VERSION,
            "outer_fields": [*value["outer_fields"], "rep_first64_512"],
            "first64_ms":512000, "phase1_observations":10242, "phase1_events":26608,
            "phase1_creations":77767, "global_event_files":57237, "global_creations":204860,
            "other_stage_caps":"UNCHANGED_INCLUDING_WHOLE_TASK_30177"}
    if rep_admin_successor:
        value = descriptor(shared_lease_successor=True)
        return {**value, "descriptor_version": REP_ADMIN_VERSION,
            "outer_fields": [*value["outer_fields"], "rep_admin_budget"],
            "scope": "REPRESENTATIVE_NO_SERVICE", "bootstrap_proof_record_count_allowed": [3],
            "representative_admin_seconds": {"collector":120, "review":480, "binder":240, "binder_process":720},
            "wait_sleep_ms":250, "new_adoption_metadata":"ONE_8192_ORIGINAL_WITHIN_EXISTING_NON_B_PARTITION"}
    if not shared_lease_successor:
        return _bootstrap_descriptor(bootstrap_successor=bootstrap_successor)
    value = _strict_descriptor()
    return {
        **value,
        "descriptor_version": SHARED_LEASE_VERSION,
        "outer_fields": [*value["outer_fields"], "bootstrap_proof_record_count"],
        "bootstrap_proof_record_count_allowed": [0, 3],
        "bootstrap_readiness_calls_per_phase": 8,
        "monitor_writer_readback_bytes": 512,
        "monitor_writer_original_readback_calls": 30,
        "monitor_writer_codec_readback_calls": 1,
        "monitor_writer_original_readback_eof": "UNCHANGED_NONE",
    }
