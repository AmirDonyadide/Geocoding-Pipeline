"""Finite synthetic codec/database observations; no capacity qualification.

Call characterize(new_private_root) inside the already denied diagnostic
process. No network, provider, subprocess, accepted inputs or source mutation.
Limits: <=60 seconds, <=128 MiB new files, <=64 files; a single 16 MiB codec
input is held at a time. Measurements are not worst-case format bounds.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path
import random
import sqlite3
import time


def characterize(root):
    import duckdb
    import pyarrow as pa
    import pyarrow.parquet as pq
    from safe_geocoding_pipeline.preprocessing.stages import s12_response as response
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_catalog as catalog
    from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_io as sqlio

    start = time.monotonic()
    root = Path(root)
    root.mkdir(mode=0o700, exist_ok=False)

    def check():
        if time.monotonic() - start >= 60:
            raise RuntimeError("RESOURCE_DIAGNOSTIC_DEADLINE")
        files = [p for p in root.rglob("*") if p.is_file()]
        if len(files) > 64 or sum(p.stat().st_size for p in files) > 128 * 2**20:
            raise RuntimeError("RESOURCE_DIAGNOSTIC_ARTIFACT_LIMIT")

    def identity(path):
        p = Path(path)
        h = hashlib.sha256()
        with p.open("rb") as f:
            while block := f.read(1024 * 1024):
                check()
                h.update(block)
        return {"file_name": p.name, "sha256": h.hexdigest()}

    report = {
        "schema_version": "stage12_resource_observation_synthetic_v1",
        "scope": "SYNTHETIC_TEST_ONLY",
        "capacity_qualified": False,
        "python_sqlite": sqlite3.sqlite_version,
        "pyarrow": pa.__version__,
        "duckdb": duckdb.__version__,
        "zstd": {"status": "UNAVAILABLE_SYMBOL"},
    }
    for library in sorted(Path(pa.__file__).parent.glob("libarrow*")):
        check()
        if not library.is_file() or library.suffix not in (".so", ".dylib") and ".so." not in library.name:
            continue
        try:
            lib = ctypes.CDLL(str(library))
            bound = lib.ZSTD_compressBound
            bound.argtypes = [ctypes.c_size_t]
            bound.restype = ctypes.c_size_t
            version = lib.ZSTD_versionNumber
            version.restype = ctypes.c_uint
            report["zstd"] = {
                "status": "EXPORTED_BOUND_OBSERVED",
                "version_number": version(),
                "library": identity(library),
                "input_limit_bytes": response.MAX_BODY,
                "compress_bound_bytes": bound(response.MAX_BODY),
            }
            break
        except (AttributeError, OSError):
            continue

    report["codec_samples"] = []
    for name, raw in (
        ("repeated_64k", b"Q" * 65536),
        ("seeded_binary_16m", random.Random(20261106).randbytes(response.MAX_BODY)),
    ):
        check()
        at = time.monotonic_ns()
        encoded = response.compress(raw)
        assert response.decompress(encoded, length=len(raw), expected_hash=hashlib.sha256(raw).digest()) == raw
        report["codec_samples"].append({"name": name, "input_bytes": len(raw), "encoded_bytes": len(encoded), "roundtrip_ns": time.monotonic_ns() - at})

    db = catalog.connect(root / "synthetic.sqlite")
    report["sqlite"] = {
        "page_size": db.execute("pragma page_size").fetchone()[0],
        "max_page_count_default": db.execute("pragma max_page_count").fetchone()[0],
        "journal_mode": db.execute("pragma journal_mode").fetchone()[0],
        "temp_store": db.execute("pragma temp_store").fetchone()[0],
        "compile_options": [x[0] for x in db.execute("pragma compile_options")],
    }
    db.execute("create table sample(k integer primary key, payload blob)")
    db.executemany("insert into sample values(?,?)", ((i, bytes([i % 251]) * 1024) for i in range(128)))
    report["sqlite"]["during_transaction"] = [{"name": p.name, "bytes": p.stat().st_size} for p in root.glob("synthetic.sqlite*")]
    db.commit()
    report["sqlite"]["page_count"] = db.execute("pragma page_count").fetchone()[0]
    db.close()

    workspace = root / "duckdb"
    workspace.mkdir(mode=0o700)
    con = sqlio.connect(workspace, memory="64MB", threads=1)
    names = ("memory_limit", "max_temp_directory_size", "checkpoint_threshold", "wal_autocheckpoint")
    report["duckdb_settings_before_diagnostic_cap"] = dict(con.execute("select name,value from duckdb_settings() where name in (?,?,?,?)", names).fetchall())
    con.execute("SET max_temp_directory_size='8MiB'")
    con.execute("create table sample as select i,repeat('synthetic',32) payload from range(256) t(i)")
    assert con.execute("select count(*) from sample").fetchone()[0] == 256
    con.execute("checkpoint")
    con.close()

    report["parquet_samples"] = []
    for rows in (1, 40):
        check()
        table = pa.table({"ordinal": list(range(rows)), "invented": [("invented synthetic Unicode Ω " + str(i)) * 128 for i in range(rows)]})
        p = root / f"synthetic_{rows}.parquet"
        pq.write_table(table, p, compression="zstd")
        p.chmod(0o600)
        assert pq.read_table(p).equals(table)
        report["parquet_samples"].append({"rows": rows, "arrow_bytes": table.nbytes, "physical_file_bytes": p.stat().st_size, "row_groups": pq.ParquetFile(p).num_row_groups})
    check()
    report["elapsed_ns"] = int((time.monotonic() - start) * 1e9)
    report["artifact_bytes_before_report"] = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
    report["artifact_files_before_report"] = sum(p.is_file() for p in root.rglob("*"))
    path = root / "RESOURCE_OBSERVATION.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write((json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())
    return report
