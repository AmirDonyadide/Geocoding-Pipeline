"""Invented 12A population/lineage cases; never a protected run or service call."""

from copy import deepcopy
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys

import pytest

from stage12_b2_synthetic import Authority, H
from safe_geocoding_pipeline.execution_policy import ExecutionPolicyError
from safe_geocoding_pipeline.preprocessing.stages import (
    s01_identity as identity,
    s10_query_contract as s10,
    s11_semantic_contract as s11,
    s12_b2_catalog as catalog,
    s12_b2_contract as b,
    s12_b2_runtime as runtime,
    s12_retrieval_contract as c,
    s12_storage as io,
    s12a_local_preparation as local,
)


@pytest.fixture
def population(tmp_path):
    tmp_path.chmod(0o700)
    sources = []
    for i in range(3):
        file_hash = b.sha(f"invented file {i}".encode())
        sources.append(
            {
                "id": "shared provider id",
                "source_file": f"invented{i}.csv",
                "source_logical_record_number": i + 1,
                "stable_source_row_id_v1": identity.stable_source_row_id_v1(
                    file_hash, i + 1
                ).hex(),
                "source_file_sha256": file_hash.hex(),
            }
        )
    contexts, hypotheses, mapping, families = [], [], [], []
    intent = s10.full_intent("Invented common passage", "DE")
    core = s11.project(intent, s10.MODE)
    q = s11.semantic_id(s11.core_bytes(core))
    semantics = [{"query_semantic_id": q, "core": core}]
    for i, (source, role) in enumerate(
        ((sources[0], "STANDARD"), (sources[0], "NATIVE"), (sources[1], "STANDARD"))
    ):
        u = b.sha(f"invented context {i}".encode())
        contexts.append(
            {
                "query_context_id": u.hex(),
                "stable_source_row_id_v1": source["stable_source_row_id_v1"],
                "country": "DE",
                "script": "Latin" if i == 0 else "Cyrillic",
                "capability": "INVENTED_UNAVAILABLE",
                "completeness": [True, False, False, False],
                "representation": role,
                "channels": [],
                "origin_sha256": H,
            }
        )
        h = b.sha(f"invented hypothesis {i}".encode()) if i < 2 else None
        families.append(
            {
                "query_context_id": u,
                "hypothesis_id": h,
                "family": "Q1" if i != 1 else "Q6",
            }
        )
        if h:
            hypotheses.append(
                {
                    "hypothesis_id": h,
                    "query_context_id": u,
                    "stable_source_row_id_v1": bytes.fromhex(
                        source["stable_source_row_id_v1"]
                    ),
                    "stage08_representation": role,
                    "intent": intent,
                    "selection_status": s10.MODE,
                }
            )
            mapping.append({"hypothesis_id": h, "query_semantic_id": q})
    mapping.sort(key=lambda row: row["hypothesis_id"])
    binding = {
        "schema_version": "stage12_stage11_input_binding_b2_v1",
        "population_scope": b.SYNTHETIC,
        "manifest_sha256": H,
        "dataset_sha256": H,
        "semantic_sha256": s11.relation_digest("semantic_request", 1, semantics).hex(),
        "map_sha256": s11.relation_digest("hypothesis_request_map", 2, mapping).hex(),
        "semantic_count": 1,
        "map_count": 2,
        "source_count": 3,
        "upstream_acceptance_sha256": H,
    }
    built = catalog.Catalog.build(
        tmp_path / "catalog.sqlite",
        binding,
        semantics=lambda: iter(semantics),
        mapping=lambda: iter(mapping),
        hypotheses=lambda: iter(hypotheses),
        contexts=lambda: iter(deepcopy(contexts)),
        families=lambda: iter(families),
        sources=lambda: iter(sources),
        authority=Authority(),
    )
    yield built, q, sources
    built.close()


def test_all_contexts_zero_query_and_contextless_source_survive_reopen(population):
    built, q, sources = population
    counts = built.validate_relations()
    assert {
        k: counts[k]
        for k in (
            "sources",
            "contexts",
            "hypothesis_links",
            "zero_query_contexts",
            "sources_without_context",
            "mapback_rows",
            "population_mapback_rows",
        )
    } == {
        "sources": 3,
        "contexts": 3,
        "hypothesis_links": 2,
        "zero_query_contexts": 1,
        "sources_without_context": 1,
        "mapback_rows": 3,
        "population_mapback_rows": 4,
    }
    contexts = list(built.contexts(q))
    assert len(contexts) == 2 and {r["representation"] for r in contexts} == {
        "STANDARD",
        "NATIVE",
    }
    rows = list(built.population_mapback())
    assert {r["stable_source_row_id_v1"] for r in rows} == {
        r["stable_source_row_id_v1"] for r in sources
    }
    assert all(r["id"] == "shared provider id" for r in rows)
    assert sum(r["query_context_id"] is None for r in rows) == 1
    assert (
        sum(
            r["query_context_id"] is not None and r["query_semantic_id"] is None
            for r in rows
        )
        == 1
    )
    reopened = catalog.Catalog(
        built.path,
        built.binding,
        expected_file_sha256=built.file_sha256,
        read_only=True,
    )
    try:
        assert reopened.validate_relations() == counts
        assert reopened.core(q) == built.core(q)
        assert list(reopened.population_mapback()) == rows
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            reopened.db.execute("delete from mapping")
    finally:
        reopened.close()
    built.verify()


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_mapping",
        "extra_hypothesis",
        "orphan_context",
        "duplicate_role",
        "missing_membership",
        "extra_membership",
        "missing_source",
        "metadata_identity",
    ],
)
def test_relational_corruption_cannot_pass_with_new_file_hash(population, mutation):
    built, q, sources = population
    db = built.db
    if mutation == "missing_mapping":
        db.execute("delete from mapping where h=(select min(h) from mapping)")
    elif mutation == "extra_hypothesis":
        db.execute(
            "insert into hypothesis select ?,q,u from hypothesis limit 1",
            (b.sha(b"extra invented hypothesis"),),
        )
    elif mutation == "orphan_context":
        db.execute("pragma foreign_keys=OFF")
        db.execute("update hypothesis set u=?", (b.sha(b"absent context"),))
    elif mutation == "duplicate_role":
        row = db.execute(
            "select u,metadata from context where json_extract(metadata,'$.representation')='NATIVE'"
        ).fetchone()
        value = json.loads(row[1])
        value["representation"] = "STANDARD"
        db.execute(
            "update context set metadata=? where u=?", (b.canonical(value), row[0])
        )
    elif mutation == "missing_membership":
        db.execute(
            "delete from membership where cell=(select min(cell) from membership)"
        )
    elif mutation == "extra_membership":
        db.execute(
            "insert into membership values(?,?,?)",
            (
                q,
                b.canonical(["script", "Invented extra", "FULL_TEXT"]),
                bytes.fromhex(sources[0]["stable_source_row_id_v1"]),
            ),
        )
    elif mutation == "missing_source":
        db.execute(
            "delete from source_lineage where source=?",
            (bytes.fromhex(sources[2]["stable_source_row_id_v1"]),),
        )
    else:
        row = db.execute("select u,metadata from context limit 1").fetchone()
        value = json.loads(row[1])
        value["query_context_id"] = H
        db.execute(
            "update context set metadata=? where u=?", (b.canonical(value), row[0])
        )
    db.commit()
    built.seal()
    with pytest.raises(c.Stage12Error):
        built.validate_relations()


def test_duplicate_links_and_sources_fail_at_storage_boundary(population):
    built, _, _ = population
    for query in (
        "insert into source_lineage select * from source_lineage limit 1",
        "insert into hypothesis select * from hypothesis limit 1",
        "insert into mapping select * from mapping limit 1",
    ):
        with pytest.raises(sqlite3.IntegrityError):
            built.db.execute(query)


def test_shared_request_retains_membership_for_every_distinct_source(population):
    built, q, _ = population
    u = built.db.execute(
        "select u from context c where not exists(select 1 from hypothesis h where h.u=c.u)"
    ).fetchone()[0]
    h = b.sha(b"new invented source hypothesis")
    built.db.execute("insert into hypothesis values(?,?,?)", (h, q, u))
    built.db.execute("insert into mapping values(?,?)", (h, q))
    built.db.execute("update family set h=? where u=?", (h, u))
    rows = [
        {"hypothesis_id": h, "query_semantic_id": q}
        for h, q in built.db.execute("select h,q from mapping order by h")
    ]
    built.binding = {
        **built.binding,
        "map_count": 3,
        "map_sha256": s11.relation_digest("hypothesis_request_map", 3, rows).hex(),
    }
    built.db.executescript(
        "delete from membership; delete from occurrence_tuple; delete from stratum;"
    )
    built.make_memberships()
    counts = built.validate_relations()
    assert (
        counts["shared_requests_multiple_contexts"]
        == counts["shared_requests_multiple_sources"]
        == 1
    )
    assert (
        counts["max_hypothesis_multiplicity"]
        == counts["sum_hypothesis_multiplicity"]
        == 3
    )
    assert len(list(built.contexts(q))) == 3
    assert built.db.execute(
        "select count(distinct source) from membership"
    ).fetchone() == (2,)


def configuration(tmp_path):
    return {
        "schema_version": local.VERSION,
        "operation": local.OPERATION,
        "population_scope": b.DEVELOPMENT,
        "network": "DENY_ALL",
        "holdout": "EXCLUDED",
        "source_git_sha": "a" * 40,
        "authorization_record_path": str(
            local.CONTROLLED_ROOT / "controls/test/authorization.json"
        ),
        "authorization_record_sha256": H,
        "owner_instruction_record_path": str(
            local.CONTROLLED_ROOT / "controls/test/owner.json"
        ),
        "owner_instruction_record_sha256": local.OWNER_INSTRUCTION_SHA256,
        "input_binding": {
            "schema_version": "stage12_stage11_input_binding_b2_v1",
            "population_scope": b.DEVELOPMENT,
            **catalog.ACCEPTED,
            "upstream_acceptance_sha256": H,
        },
        "accepted_roots": {
            k: str(tmp_path / k) for k in ("stage06", "stage08", "stage09", "stage11")
        },
        "output_path": str(local.CONTROLLED_ROOT / "artifacts/test"),
        "scratch_path": str(local.CONTROLLED_ROOT / "scratch/test"),
        "resources": {
            "duckdb_memory_bytes": 4 * 2**30,
            "max_duration_seconds": 60,
            "max_generated_disk_bytes": 64 * 2**30,
            "minimum_free_bytes": 128 * 2**30,
        },
    }


@pytest.mark.parametrize(
    "purpose",
    [
        "supported_size",
        "calibration_depths",
        "before_dispatch",
        "public_probe",
        "protected_dispatch",
        "transfer",
        "stage12b",
        "stage13",
        "positive_importer_lineage",
    ],
)
def test_12a_authority_rejects_service_calibration_transfer_and_later_stages(
    tmp_path, purpose
):
    guard = runtime.OfflineGuard()
    try:
        authority = local.Authority(configuration(tmp_path), guard, lambda: None)
        with pytest.raises(c.Stage12Error, match="S12A_OPERATION_DENIED"):
            authority.require(purpose, H, {})
    finally:
        guard.close()


def test_12a_denial_is_real_process_wide_and_unknown_interpretation_is_fixed(tmp_path):
    guard = runtime.OfflineGuard()
    try:
        authority = local.Authority(configuration(tmp_path), guard, lambda: None)
        authority.require(
            "witness_interpretation",
            b.digest(local.INTERPRETATION),
            local.INTERPRETATION,
        )
        with pytest.raises(c.Stage12Error, match="DENIED"):
            socket.socket()
        with pytest.raises(c.Stage12Error, match="DENIED"):
            subprocess.run(["true"], check=True)
        with pytest.raises(c.Stage12Error, match="S12A_INTERPRETATION"):
            authority.require(
                "witness_interpretation",
                H,
                {**local.INTERPRETATION, "country_namespace": "ISO_ALPHA2"},
            )
        with pytest.raises(c.Stage12Error, match="S12A_LINEAGE_BINDING"):
            authority.require("lineage_context", H, {})
    finally:
        guard.close()


@pytest.mark.parametrize(
    "change",
    [
        {"operation": "PUBLIC_PROBE"},
        {"C": 10},
        {"network": "ALLOW"},
        {"holdout": "INCLUDED"},
    ],
)
def test_closed_12a_configuration_rejects_scope_expansion(tmp_path, change):
    with pytest.raises(c.Stage12Error, match="S12A_LOCAL_SCOPE"):
        local.validate_config({**configuration(tmp_path), **change})


def test_site_guard_precedes_protected_and_git_access(tmp_path, monkeypatch):
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setattr(
        local.subprocess,
        "check_output",
        lambda *a, **k: pytest.fail("Git must not run before site guard"),
    )
    with pytest.raises(ExecutionPolicyError):
        local.run(configuration(tmp_path), repository=tmp_path)


def test_configuration_forbids_writing_outside_exact_controlled_namespace(tmp_path):
    for path in (
        "/tmp/invented",
        str(local.CONTROLLED_ROOT / "artifacts/../controls/invented"),
        "/work/footprint/public/invented",
    ):
        with pytest.raises(c.Stage12Error, match="S12A_CONTROLLED_LOCATION"):
            local.validate_config({**configuration(tmp_path), "output_path": path})


def test_primary_failure_survives_cleanup_and_failure_output_has_no_exception_text():
    class Broken:
        def close(self):
            raise ValueError("INVENTED_PROTECTED_CLEANUP_CANARY")

    old = os.umask(0o077)
    try:
        with pytest.raises(ValueError, match="INVENTED_PRIMARY_CANARY"):
            try:
                raise ValueError("INVENTED_PRIMARY_CANARY")
            finally:
                local.finish((Broken(),), Broken(), old, sys.exc_info()[1])
    finally:
        os.umask(old)
    result = local.safe_failure(
        ValueError("INVENTED_PROTECTED_CANARY"), "CATALOG_BUILD"
    )
    assert result["stage"] == "CATALOG_BUILD"
    assert "CANARY" not in json.dumps(result)


def test_genuine_accepted_metadata_graph_and_provenance_fit_bounded_opener(tmp_path):
    repository = Path(__file__).resolve().parents[1]
    root = repository / "docs/scientific_assets"
    m11 = json.loads((root / "stage11_development_manifest_1788751.json").read_bytes())
    m10 = json.loads((root / "stage10_remediated_manifest_1785683.json").read_bytes())
    p = {
        "stage11_manifest": m11,
        "stage10_binding": m11["input_binding"],
        "lineage_binding": m10["input_binding"],
    }
    accepted_identifier = local.lineage.s10.identity(
        "stage10-input:v1", local.lineage.s10.canonical(p["lineage_binding"])
    ).hex()
    p["lineage_projection_sha256"] = b.digest(
        {
            "accepted_input_sha256": accepted_identifier,
            "interpretation_sha256": b.digest(local.INTERPRETATION),
            "algorithm": "stage12_accepted_lineage_projection_b2_v1",
        }
    )
    local.validate_provenance(p, configuration(tmp_path))
    assert len(b.canonical(p)) == 143738 < 16 * 2**20
    graph = local.input_graph(p)
    assert (
        len(graph) == 368
        and sum(x["bytes"] for x in graph) == local.VALIDATED_PAYLOAD_BYTES
    )


@pytest.mark.parametrize(
    "mutation", [None, "binding", "seal", "extra", "missing", "catalog"]
)
def test_actual_artifact_reopen_reads_all_originals(population, tmp_path, mutation):
    built, _, _ = population
    config = {"input_binding": built.binding, "source_git_sha": "a" * 40}
    artifact = tmp_path / "artifact"
    io.reserve(artifact)
    target = artifact / "catalog.sqlite"
    target.write_bytes(built.path.read_bytes())
    target.chmod(0o600)
    io.write(artifact / "binding.json", b.canonical(built.binding))
    provenance_raw = b.canonical({"SYNTHETIC_ONLY": True})
    io.write(artifact / "accepted_inputs.json", provenance_raw)
    io.write(
        artifact / "_COMMITTED",
        b.canonical(
            local.artifact_seal(config, built.file_sha256, b.sha(provenance_raw).hex())
        ),
    )
    if mutation == "binding":
        (artifact / "binding.json").write_bytes(
            b.canonical({**built.binding, "source_count": 4})
        )
    elif mutation == "seal":
        (artifact / "_COMMITTED").write_bytes(
            b.canonical(
                local.artifact_seal(
                    {**config, "source_git_sha": "b" * 40},
                    built.file_sha256,
                    b.sha(provenance_raw).hex(),
                )
            )
        )
    elif mutation == "extra":
        io.write(artifact / "extra", b"invented")
    elif mutation == "missing":
        (artifact / "_COMMITTED").unlink()
    elif mutation == "catalog":
        with target.open("ab") as stream:
            stream.write(b"invented corruption")
    if mutation:
        with pytest.raises(c.Stage12Error):
            local.reopen_artifact(artifact, config, expected_counts=None)
    else:
        assert local.reopen_artifact(artifact, config, expected_counts=None) == {
            "catalog_sha256": built.file_sha256,
            "counts": built.validate_relations(),
        }
