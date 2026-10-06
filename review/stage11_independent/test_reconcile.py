"""Exercise independent scientific/operational oracles against synthetic artifacts."""

import shutil
from pathlib import Path

import duckdb
import pytest
import pyarrow.parquet as pq

import oracle as o
import operations as ops
import reconcile as r
import review
from stage11_synthetic import fixture
from safe_geocoding_pipeline.preprocessing.stages import s10_query_io as upstream
from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_assets as assets
from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_checkpoints as cp
from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_contract as c
from safe_geocoding_pipeline.preprocessing.stages import (
    s11_semantic_pipeline as candidate,
)
from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_publication as pub
from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_trace as trace

EXE = "e" * 40
ASSETS = assets.identifiers(Path(c.__file__).resolve().parents[4])


def run(root, inputs, **kwargs):
    root.mkdir(mode=0o700)
    for p in (root / "local", root / "checkpoints"):
        p.mkdir(mode=0o700)
    return candidate.run(
        inputs,
        root / "artifact",
        root / "local",
        root / "checkpoints",
        ASSETS,
        EXE,
        **kwargs,
    )


def review_synthetic(root, inputs, result):
    checks = {}

    def check(name, ok):
        checks[name] = checks.get(name, True) and bool(ok)

    with review.review_connection() as db:
        inputs.register(db)
        for rel, view in zip(result.manifest["relations"], ("s", "m")):
            paths = [result.path / f["relative_path"] for f in rel["files"]]
            db.execute(f"CREATE VIEW {view} AS SELECT * FROM {ops.parquet_sql(paths)}")
        summary = r.scientific(db, check)
        assert summary == ops.read_json(result.path / "semantic_request_summary.json")
        assert (
            r.hypothesis_digest(
                db,
                upstream.output_schema("query_hypothesis"),
                upstream.c.schema_fingerprint("query_hypothesis").hex(),
                inputs.population["hypotheses"],
            )
            == inputs.hypothesis_sha
        )
        for rel, view, pk in zip(
            result.manifest["relations"],
            ("s", "m"),
            ("query_semantic_id", "hypothesis_id"),
        ):
            assert (
                o.relation_hash(
                    rel["name"],
                    rel["schema_sha256"],
                    rel["row_count"],
                    r.rows(db, f"SELECT * FROM {view} ORDER BY {pk}"),
                )
                == rel["logical_sha256"]
            )
        cp_counts = ops.checkpoints(root / "checkpoints", result.manifest, db, check)
        assert cp_counts["incomplete_units"] == 0
    ops.registration(result.path, result.manifest, result.manifest_sha256, check)
    assert all(checks.values()), [k for k, v in checks.items() if not v]
    return summary


def test_independent_end_to_end_and_resume(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    inputs = fixture(root / "input", contexts=18, varied=True)
    clean = run(root / "clean", inputs, unit_rows=4)
    clean_summary = review_synthetic(root / "clean", inputs, clean)

    def interrupt(phase):
        if phase == "reduction_unit_complete":
            raise RuntimeError("invented interruption")

    monkeypatch.setattr(cp, "fault", interrupt)
    with pytest.raises(c.Stage11Error):
        run(root / "interrupted", inputs, unit_rows=4)
    assert not (root / "interrupted/artifact/_COMMITTED").exists()
    shutil.rmtree(root / "interrupted/local")
    monkeypatch.setattr(cp, "fault", lambda _: None)
    resumed = run(
        root / "resumed", inputs, unit_rows=4, resume=root / "interrupted/checkpoints"
    )
    assert review_synthetic(root / "resumed", inputs, resumed) == clean_summary
    assert resumed.manifest["logical_sha256"] == clean.manifest["logical_sha256"]
    assert (
        resumed.manifest["operational_provenance"]["checkpoints"][
            "adopted_reduction_units"
        ]
        == 1
    )
    reversed_inputs = fixture(root / "reversed", contexts=18, varied=True, reverse=True)
    varied = run(
        root / "varied", reversed_inputs, unit_rows=7, partition_bytes=2, threads=3
    )
    assert review_synthetic(root / "varied", reversed_inputs, varied) == clean_summary
    assert varied.manifest["logical_sha256"] == clean.manifest["logical_sha256"]
    # Re-shard, reverse physical row order, change codec and path; same oracle hash.
    rel = clean.manifest["relations"][0]
    paths = [clean.path / f["relative_path"] for f in rel["files"]]
    table = pq.read_table(paths)
    shuffled = table.take(list(reversed(range(table.num_rows))))
    pq.write_table(
        shuffled, root / "resharded.parquet", compression="snappy", row_group_size=2
    )
    with duckdb.connect() as db:
        assert (
            o.relation_hash(
                rel["name"],
                rel["schema_sha256"],
                rel["row_count"],
                r.rows(
                    db,
                    f"SELECT * FROM {ops.parquet_sql([root / 'resharded.parquet'])} ORDER BY query_semantic_id",
                ),
            )
            == rel["logical_sha256"]
        )
    shutil.rmtree(root / "clean/local")
    candidate.reopen(clean.path, clean.manifest_sha256, True, inputs, ASSETS, EXE)


@pytest.mark.parametrize("kind", ["collision", "registration", "manifest", "contract"])
def test_failure_blocks_publication_independently(tmp_path, monkeypatch, kind):
    root = tmp_path.resolve()
    inputs = fixture(root / "input")
    errors = []
    if kind == "collision":
        monkeypatch.setattr(c, "semantic_id", lambda raw: bytes(32))
    elif kind in ("registration", "manifest"):

        def fault(phase, path):
            if phase == ("prepared_record" if kind == "registration" else "manifest"):
                (
                    path
                    / (
                        "_SUCCESS.json"
                        if kind == "registration"
                        else "stage11_semantic_request_manifest.json"
                    )
                ).write_bytes(b"{}\n")

        monkeypatch.setattr(pub, "fault", fault)
    else:
        table = pq.read_table(inputs.hypotheses[0])
        data = table.to_pylist()
        data[0]["intent"]["boundary_country"] = ""
        pq.write_table(
            __import__("pyarrow").Table.from_pylist(data, schema=table.schema),
            inputs.hypotheses[0],
        )
    with pytest.raises(Exception):
        run(
            root / "bad",
            inputs,
            observer=lambda phase, error: errors.append(error) if error else None,
        )
    assert not (root / "bad/artifact/_COMMITTED").exists()
    if kind == "collision":
        assert any(str(e) == "S11_ID_COLLISION" for e in errors)


def test_first_failure_with_secondary_receipt_failure(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    inputs = fixture(root / "input")
    receipts = root / "receipts"
    receipts.mkdir(mode=0o700)
    recorder = trace.PublicationTrace(receipts, root / "run/artifact", EXE)

    def fault(phase):
        if phase == "input_unit_complete":
            raise c.Stage11Error("S11_RESOURCE_FAILURE")

    monkeypatch.setattr(cp, "fault", fault)

    def observe(phase, error):
        if error:
            recorder.failure(error)
            raise RuntimeError("INVENTED_SECONDARY_POISON")

    with pytest.raises(c.Stage11Error):
        run(root / "run", inputs, observer=observe)
    raw = (receipts / "failure.json").read_bytes()
    assert (
        ops.read_json(receipts / "failure.json")["operational_code"]
        == "S11_RESOURCE_FAILURE"
    )
    assert b"POISON" not in raw
    recorder.failure(RuntimeError("INVENTED_LATER_POISON"))
    assert (receipts / "failure.json").read_bytes() == raw
    assert not (root / "run/artifact/_COMMITTED").exists()


def test_oracle_collects_multiple_ordinary_defects(tmp_path):
    root = tmp_path.resolve()
    inputs = fixture(root / "input")
    result = run(root / "run", inputs)
    checks = {}
    with duckdb.connect() as db:
        inputs.register(db)
        for rel, view in zip(result.manifest["relations"], ("s", "m")):
            paths = [result.path / f["relative_path"] for f in rel["files"]]
            db.execute(f"CREATE TABLE {view} AS SELECT * FROM {ops.parquet_sql(paths)}")
        db.execute(
            "DELETE FROM m WHERE hypothesis_id=(SELECT min(hypothesis_id) FROM m)"
        )
        db.execute(
            "UPDATE s SET core=struct_update(core,boundary_country := 'FR') WHERE core.boundary_country='DE'"
        )
        summary = r.scientific(db, lambda name, ok: checks.update({name: bool(ok)}))
    assert not checks["B_C_missing_mappings"]
    assert not checks["E_full_sha256_recomputation"]
    assert not checks["F_H_every_hypothesis_complete_core_exact_bytes"]
    assert summary["integrity"]["missing_mappings"] == 1
    assert "M_histogram_arithmetic" in checks  # Review continues after defects.
