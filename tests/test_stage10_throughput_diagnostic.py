"""Public/invented diagnostic isolation, measurement and fidelity tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import duckdb
import pytest

from safe_geocoding_pipeline.preprocessing import stage10_throughput_diagnostic as d
from safe_geocoding_pipeline.preprocessing.stages import s10_query_contexts as cx
from safe_geocoding_pipeline.preprocessing.stages import s10_query_families as f
from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s10_query_execution as ex
from test_stage10_context_pipeline import synthetic_inputs as synthetic_inputs
from test_stage09_reference_evaluator import reference_view as reference_view
from test_stage10_query_families import SyntheticTransform


def test_copy_preserves_original_and_rejects_replacement(tmp_path: Path) -> None:
    source, target = tmp_path / "source", tmp_path / "copy"
    source.write_bytes(b"public database stand-in")
    source.chmod(0o600)
    before = source.stat()
    digest = d.copy_evidence(source, target)
    assert digest == hashlib.sha256(source.read_bytes()).hexdigest()
    assert target.read_bytes() == source.read_bytes()
    assert source.stat().st_mtime_ns == before.st_mtime_ns
    assert target.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        d.copy_evidence(source, target)


def test_copy_rejects_symlink(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"public")
    link = tmp_path / "link"
    link.symlink_to(source)
    with pytest.raises(ValueError, match="DIAGNOSTIC_SOURCE_TOPOLOGY"):
        d.copy_evidence(link, tmp_path / "copy")


def test_selection_is_id_only_order_independent_and_bounded() -> None:
    db = duckdb.connect()
    db.execute("CREATE TABLE stage10_context_keys(query_context_id BLOB)")
    ids = [bytes([i * 16 + j]) + bytes(31) for i in range(16) for j in (2, 1)]
    db.executemany("INSERT INTO stage10_context_keys VALUES (?)", [[v] for v in ids])
    chosen = d.select_contexts(db)
    assert len(chosen) == 16
    assert chosen == [bytes([i * 16 + 1]) + bytes(31) for i in range(16)]
    db.close()


def test_timing_and_plan_output_cannot_contain_parameters() -> None:
    metrics = d.Metrics()
    db = d.TimedDB(duckdb.connect(), metrics)
    db.execute("SELECT ? AS value", ["Fictional Secret Address"]).fetchone()
    plan = d.plan_operators(
        '[{"name":"SEQ_SCAN","extra_info":{"Filter":"Fictional Secret Address"},"children":[]}]'
    )
    encoded = json.dumps({"timings": metrics.values, "operators": plan})
    assert "Fictional Secret Address" not in encoded
    assert "SELECT" not in encoded
    assert plan == {"SEQ_SCAN": 1}
    assert metrics.values["sql_other"]["calls"] == 1
    assert "Fictional Secret Address" not in json.dumps(
        d.failure_metadata(ValueError("Fictional Secret Address"))
    )
    assert (
        d.failure_metadata(c.Stage10Error("DIAGNOSTIC_SELECTION_DRIFT"))["failure_code"]
        == "DIAGNOSTIC_SELECTION_DRIFT"
    )
    db.close()


def test_instrumented_generation_is_exact(
    synthetic_inputs: Any, tmp_path: Path
) -> None:
    runtime = SyntheticTransform()
    work = cx.ContextWorkspace(synthetic_inputs, tmp_path / "work", b"s" * 32)
    work.prepare()
    first = next(work.contexts(diagnostics=False))
    expected = f.generate(first, runtime)
    metrics = d.Metrics()
    with d.instrument(metrics):
        actual = f.generate(first, runtime)
    assert actual == expected
    assert all(metrics.values[family]["calls"] == 1 for family in c.FAMILIES)
    assert metrics.values["hash_identity"]["calls"] > 0
    work.close()


def test_guard_precedes_any_input_access(monkeypatch: Any) -> None:
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    with pytest.raises(Exception, match="Goethe|goethe|SLURM"):
        d.preflight("0" * 40, Path("/does-not-exist"))


def test_partial_footer_abstains_without_decoding(tmp_path: Path) -> None:
    path = tmp_path / "partial.parquet"
    path.write_bytes(b"PAR1public invented incomplete data")
    assert d.parquet_state(path) == {"footer_present": False, "rows": None}


def test_deadline_is_diagnostic_not_scientific_abstention() -> None:
    import time

    with pytest.raises(d.DiagnosticLimit):
        with d.deadline(0.02):
            time.sleep(0.1)


def test_recover_only_copied_wal_and_keep_original_bytes(tmp_path: Path) -> None:
    import subprocess
    import sys

    original = tmp_path / "original.duckdb"
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import duckdb,os,sys; os.umask(0o077); db=duckdb.connect(sys.argv[1]); db.execute('CREATE TABLE evidence(n INTEGER)'); db.execute('INSERT INTO evidence VALUES (7)'); os._exit(0)",
            str(original),
        ],
        check=True,
    )
    copied = tmp_path / "copied.duckdb"
    original_wal = Path(str(original) + ".wal")
    assert original_wal.is_file()
    before = {p: p.read_bytes() for p in (original, original_wal)}
    d.copy_evidence(original, copied)
    d.copy_evidence(original_wal, Path(str(copied) + ".wal"))
    db = d.open_snapshot(copied, tmp_path / "spill")
    assert db.execute("SELECT sum(n) FROM evidence").fetchone() == (7,)
    db.execute("INSERT INTO evidence VALUES (9)")
    db.close()
    assert all(p.read_bytes() == payload for p, payload in before.items())


def test_timed_connection_full_context_fidelity(
    synthetic_inputs: Any, tmp_path: Path
) -> None:
    runtime = SyntheticTransform()
    work = cx.ContextWorkspace(synthetic_inputs, tmp_path / "work", b"s" * 32)
    work.prepare()
    expected = [
        f.generate(context, runtime) for context in work.contexts(diagnostics=False)
    ]
    raw = work.db
    metrics = d.Metrics()
    work.db = d.TimedDB(raw, metrics)  # type: ignore[assignment]
    assert work.reference is not None
    work.reference.db = work.db
    work.reference.certificates = cx.ByteCache(1024 * 1024)
    work.reference.cache = cx.ByteCache()
    work.parser_certificates = cx.ByteCache(1024 * 1024)
    with d.instrument(metrics):
        actual = [
            f.generate(context, runtime) for context in work.contexts(diagnostics=False)
        ]
    assert actual == expected
    assert metrics.values["sql_selector_insert"]["calls"] > 0
    assert metrics.values["sql_components"]["calls"] > 0
    work.close()


def test_profile_retains_only_function_metadata() -> None:
    import cProfile

    profile = cProfile.Profile()
    profile.runcall(
        d.plan_operators,
        '[{"name":"SEQ_SCAN","extra_info":{"secret":"Fictional Secret Address"}}]',
    )
    result = d.profile_summary(profile)
    assert result
    assert "Fictional Secret Address" not in json.dumps(result)
    assert all(
        set(row)
        == {
            "file",
            "line",
            "function",
            "primitive_calls",
            "calls",
            "self_seconds",
            "cumulative_seconds",
        }
        for row in result
    )


def test_deadline_rolls_back_without_contaminating_later_work() -> None:
    import time

    db = duckdb.connect()
    db.execute("CREATE TABLE measurements(n INTEGER)")
    with pytest.raises(d.DiagnosticLimit):
        with d.deadline(0.02, db.interrupt):
            db.execute("BEGIN")
            try:
                db.execute("INSERT INTO measurements VALUES (1)")
                time.sleep(1.1)
            except BaseException:
                db.execute("ROLLBACK")
                raise
    assert db.execute("SELECT count(*) FROM measurements").fetchone() == (0,)
    db.execute("INSERT INTO measurements VALUES (2)")
    assert db.execute("SELECT sum(n) FROM measurements").fetchone() == (2,)
    db.close()


def test_launcher_and_entrypoint_do_not_materialize_or_publish() -> None:
    import inspect

    source = inspect.getsource(d)
    assert "pub.publish(" not in source
    assert "generate_catalog(" not in source
    assert "validate-published" not in source
    assert "read_only=False" not in source
    launcher = (
        ex.REPOSITORY / "cluster/goethe_nhr/stage10_throughput_diagnostic.sbatch"
    ).read_text()
    assert "--time=00:30:00" in launcher
    assert "--no-requeue" in launcher
    assert "SAFE_EXECUTION_SITE=goethe-nhr" in launcher
    assert "SLURM_JOB_ID:?" in launcher
    assert "stage10_cli" not in launcher


def test_long_duckdb_query_is_a_time_cap_and_connection_remains_usable() -> None:
    db = duckdb.connect(config={"threads": "4"})
    with pytest.raises(d.DiagnosticLimit):
        with d.deadline(0.03, db.interrupt):
            db.execute("SELECT sum(i) FROM range(1000000000000) t(i)").fetchone()
    assert db.execute("SELECT 42").fetchone() == (42,)
    db.close()


def test_deadline_interrupts_nested_cursor() -> None:
    db = d.TimedDB(duckdb.connect(config={"threads": "4"}), d.Metrics())
    child = db.cursor()
    with pytest.raises(d.DiagnosticLimit):
        with d.deadline(0.05, db.interrupt):
            child.execute("SELECT sum(i) FROM range(1000000000000) t(i)").fetchone()
    child.close()
    assert db.execute("SELECT 42").fetchone() == (42,)
    assert len(db.cursors) == 1
    db.close()


def test_bounded_input_reads_use_recovered_views(
    synthetic_inputs: Any, tmp_path: Path
) -> None:
    work = cx.ContextWorkspace(synthetic_inputs, tmp_path / "work", b"s" * 32)
    work.prepare()
    chosen = d.select_contexts(work.db)
    metrics = d.Metrics()
    result = d.bounded_upstream_reads(work.db, chosen, metrics)
    assert len(result) == 5
    assert all(item["decoded_rows"] > 0 for item in result.values())
    assert not any(item["diagnostic_limited"] for item in result.values())
    work.close()


def test_timeout_reconciliation_rolls_back_before_reuse(
    synthetic_inputs: Any, tmp_path: Path
) -> None:
    work = cx.ContextWorkspace(synthetic_inputs, tmp_path / "work", b"s" * 32)
    work.prepare()
    work.db.execute("BEGIN")
    work.db.execute("DELETE FROM stage10_context_keys")
    d.reconcile_limit(work)
    assert work.db.execute("SELECT count(*) FROM stage10_context_keys").fetchone() == (
        4,
    )
    d.reconcile_limit(work)
    assert work.reference is not None
    assert not work.reference.cache.items
    assert not work.reference.certificates.items
    work.close()
