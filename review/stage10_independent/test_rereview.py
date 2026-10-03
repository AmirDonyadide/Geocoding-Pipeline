"""Invented-data fault injection and portable bindings for the final rereview."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

import common
import relations
import remediation_oracle as remediation
import rereview
import structured
from operations import oracle as operations
from test_review import Checks
from test_stage10_materializer import catalog

ASSETS = Path(__file__).resolve().parents[2] / "docs/scientific_assets"


@pytest.mark.parametrize("synthetic_inputs", [True, False], indirect=True)
def test_independent_c01_exact_fields_and_faults(synthetic_inputs, tmp_path):
    work, _ = catalog(synthetic_inputs, tmp_path / "work")
    try:
        db = work.db
        relations.derive_contexts(db, synthetic_inputs.context_binding, Checks())
        structured.run(db, Checks())
        checks = Checks()
        good = remediation.c01(db, checks)
        assert good["expected"] == good["actual"] > 0
        assert all(checks.values())
        for name in ("query_family_decision", "query_hypothesis"):
            db.execute(f"CREATE TABLE saved_{name} AS SELECT * FROM {name}")
            db.execute(f"DROP VIEW {name}")
            db.execute(f"CREATE TABLE {name} AS SELECT * FROM saved_{name}")
        faults = [
            (
                "missing",
                "UPDATE query_family_decision SET field_decisions=list_transform(field_decisions,f -> struct_update(f,reason_codes:=list_filter(f.reason_codes,r -> r<>'PARSER_ONLY_FIELD_EXCLUDED'))) WHERE family='Q4'",
            ),
            (
                "duplicates",
                "UPDATE query_family_decision SET field_decisions=list_transform(field_decisions,f -> CASE WHEN f.field='region' THEN struct_update(f,reason_codes:=list_append(f.reason_codes,'PARSER_ONLY_FIELD_EXCLUDED')) ELSE f END) WHERE family='Q4'",
            ),
            (
                "wrong_field",
                "UPDATE query_family_decision SET field_decisions=list_transform(field_decisions,f -> CASE WHEN f.field='region' THEN struct_update(f,field:='country') ELSE f END) WHERE family='Q4'",
            ),
            (
                "wrong_context",
                "UPDATE query_family_decision SET stage08_representation='SYNTHETIC_WRONG_ROLE' WHERE family='Q4'",
            ),
            (
                "included_source_marked_parser_only",
                "UPDATE query_family_decision SET field_decisions=list_transform(field_decisions,f -> CASE WHEN f.field='address' THEN struct_update(f,reason_codes:=list_append(f.reason_codes,'PARSER_ONLY_FIELD_EXCLUDED')) ELSE f END) WHERE family='Q4'",
            ),
            (
                "parser_only_payload",
                "UPDATE query_hypothesis SET intent=struct_update(intent,region:='invented parser geography') WHERE intent.search_mode='STRUCTURED'",
            ),
            (
                "source_anchor",
                "UPDATE query_hypothesis SET intent=struct_update(intent,address:='invented unanchored value') WHERE intent.search_mode='STRUCTURED'",
            ),
        ]
        for expected, sql in faults:
            if (
                expected in ("parser_only_payload", "source_anchor")
                and not db.execute(
                    "SELECT count(*) FROM query_hypothesis WHERE intent.search_mode='STRUCTURED'"
                ).fetchone()[0]
            ):
                continue  # The deliberately ineligible fixture emits no Q4.
            db.execute("BEGIN")
            try:
                db.execute(sql)
                checks = Checks()
                result = remediation.c01(db, checks)
                assert result["violations"][expected] > 0, expected
                assert not checks["c01_" + expected]
            finally:
                db.execute("ROLLBACK")
    finally:
        work.close()


@pytest.mark.parametrize("synthetic_inputs", [True], indirect=True)
def test_complete_old_new_comparison_detects_scientific_drift(
    synthetic_inputs, tmp_path
):
    work, _ = catalog(synthetic_inputs, tmp_path / "work")
    try:
        db = work.db
        # Historical projection intentionally removes only the repaired field
        # reason. All other columns, nulls, ordering and multiplicity remain.
        db.execute(
            "CREATE TABLE previous_query_hypothesis AS SELECT * FROM query_hypothesis"
        )
        db.execute("""CREATE TABLE previous_query_family_decision AS SELECT * REPLACE(
            list_transform(field_decisions,f -> struct_update(f,reason_codes:=
              list_filter(f.reason_codes,r -> r<>'PARSER_ONLY_FIELD_EXCLUDED')))
            AS field_decisions) FROM query_family_decision""")
        checks = Checks()
        result = remediation.compare_relations(db, checks)
        assert all(checks.values())
        assert result["complete_decisions_symmetric_difference"] == 8
        for sql, rejected in [
            (
                "UPDATE previous_query_hypothesis SET intent=struct_update(intent,text:='invented changed payload') WHERE intent.search_mode='FULL_TEXT'",
                "hypotheses",
            ),
            (
                "INSERT INTO previous_query_hypothesis SELECT * FROM previous_query_hypothesis LIMIT 1",
                "hypotheses",
            ),
            (
                "UPDATE previous_query_family_decision SET primary_reason='FAMILY_INELIGIBLE' WHERE family='Q1'",
                "scientific_decisions",
            ),
            (
                "UPDATE previous_query_family_decision SET field_decisions=list_transform(field_decisions,f -> CASE WHEN f.field='region' THEN struct_update(f,reason_codes:=[]) ELSE f END) WHERE family='Q4'",
                "scientific_decisions",
            ),
        ]:
            db.execute("BEGIN")
            try:
                db.execute(sql)
                checks = Checks()
                remediation.compare_relations(db, checks)
                assert not checks["old_new_" + rejected + "_exact"]
            finally:
                db.execute("ROLLBACK")
    finally:
        work.close()


def test_remediated_registration_and_inventory_bindings():
    manifest_path = ASSETS / "stage10_remediated_manifest_1785683.json"
    manifest = json.loads(manifest_path.read_bytes())
    assert common.file_sha(manifest_path) == rereview.MANIFEST
    assert all(manifest[k] == value for k, value in rereview.FROZEN.items())
    body = rereview.registration_body(rereview.KEY, manifest, rereview.MANIFEST)
    assert body["bindings"]["namespace"] == "STAGE10_DEVELOPMENT_QUERY_PLAN"
    assert (
        body["bindings"]["stage10_input_binding_sha256"]
        == manifest["input_binding_sha256"]
    )
    assert "stage10_input_sha256" not in body["bindings"]
    expected = {
        **body,
        "commit_record_id": hashlib.sha256(
            b"SAFE:publication-commit:v2\0" + common.canonical(body)
        ).hexdigest(),
    }
    assert (
        json.loads(
            (ASSETS / "stage10_remediated_registration_1785683.json").read_bytes()
        )
        == expected
    )
    inventory = json.loads(
        (ASSETS / "stage10_remediated_review_inventory_1785683.json").read_bytes()
    )
    normalized = remediation.adapt_inventory(inventory)
    assert len(normalized["receipts"]) == normalized["receipt_count"] == 1133
    for key, value in (("job_id", "1774362"), ("inventory_version", "wrong")):
        bad = {**inventory, key: value}
        with pytest.raises(RuntimeError, match="REREVIEW_INVENTORY_VERSION"):
            remediation.adapt_inventory(bad)
    bad = copy.deepcopy(inventory)
    bad["receipt_inventory"][0]["path"] = "execution/_COMMITTED"
    with pytest.raises(RuntimeError, match="REREVIEW_RECEIPT_SCOPE"):
        remediation.adapt_inventory(bad)


def test_log_marker_is_exact_unique_terminal(tmp_path):
    manifest = json.loads(
        (ASSETS / "stage10_remediated_manifest_1785683.json").read_bytes()
    )
    completed = json.loads(
        (ASSETS / "stage10_remediated_completed_1785683.json").read_bytes()
    )
    progress = {
        "operational_version": "stage10_progress_v2",
        "phase": "input_validation",
        "event": "progress",
    }
    stdout = tmp_path / "stdout"
    marker = "STAGE10_REMEDIATION_AUDIT_PASS"
    raw = common.canonical(progress)
    for payload, failures in (
        (raw + marker.encode() + b"\n", set()),
        (raw, {"operations_stdout_audit_marker"}),
        (raw + (marker.encode() + b"\n") * 2, {"operations_stdout_audit_marker"}),
        (marker.encode() + b"\n" + raw, {"operations_stdout_marker_is_last"}),
    ):
        stdout.write_bytes(payload)
        checks = Checks()
        assert (
            operations.audit_logs(
                stdout,
                None,
                manifest,
                completed,
                rereview.KEY,
                checks,
                terminal_marker=marker,
            )
            == 1
        )
        assert {k for k, v in checks.items() if not v} == failures | {
            "operations_stdout_count"
        }
    stdout.write_bytes(raw + b"UNKNOWN_MARKER\n")
    with pytest.raises(json.JSONDecodeError):
        operations.audit_logs(
            stdout,
            None,
            manifest,
            completed,
            rereview.KEY,
            Checks(),
            terminal_marker=marker,
        )


def test_ephemeral_read_guard_is_fail_closed():
    source = """
import pathlib, sys
sys.path.insert(0, sys.argv[1])
import remediation_oracle
remediation_oracle.deny_local_reads()
try:
    pathlib.Path('/local/1785683/nonexistent-synthetic-test').read_bytes()
except RuntimeError as error:
    assert str(error) == 'REREVIEW_FORBIDDEN_EPHEMERAL_READ'
else:
    raise AssertionError('ephemeral read was attempted')
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", source, str(Path(__file__).parent)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_durable_trace_oracle_and_missing_state(tmp_path):
    """A tiny invented durable receipt tree; no real controlled path is read."""
    root = tmp_path / "development" / rereview.KEY
    work = root.parent / "work" / (root.name + "_synthetic")
    progress = work / "workspace/progress"
    audit_root = work.parent / (root.name + "_remediation_audit")
    repository = tmp_path / "repository"
    portable = (
        repository / "docs/scientific_assets/stage10_remediated_audit_1785683.json"
    )
    for p in (root, progress, audit_root, portable.parent):
        p.mkdir(parents=True, mode=0o700)
    for p in tmp_path.rglob("*"):
        if p.is_dir():
            p.chmod(0o700)

    def save(path, data):
        path.write_bytes(data if isinstance(data, bytes) else common.canonical(data))
        path.chmod(0o600)

    local = (
        "/local/1785683/safe_geocoding_pipeline/stage10/generation_synthetic/workspace"
    )
    manifest = {
        "operational_provenance": {
            "workspace": str(work),
            "transient_workspace": local,
            "storage_class": "SPLIT_LOCAL_TRANSIENT_PANFS_DURABLE",
        },
        "scientific_synthetic": True,
    }
    save(root / "stage10_query_manifest.json", manifest)
    for i, name in enumerate(remediation.PHASES):
        save(
            work / f"publication-{i:06}.json",
            {
                "phase": name,
                "execution_git_sha": rereview.EXE,
                "publication_key": root.name,
                "monotonic_ns": i + 1,
                "manifest_present": i >= 6,
                "registration_present": i >= 10,
                "seal_present": i >= 14,
                "local_workspace": str(Path(local).parent),
                "local_workspace_class": "JOB_LOCAL_EPHEMERAL",
            },
        )
    save(work / "failure.json.partial", b" " * 65536)
    save(progress / "progress-000001.json", {"event": "terminal_success"})
    audit = {
        "execution_git_sha": rereview.EXE,
        "job_id": "1785683",
        "new_manifest_sha256": common.file_sha(root / "stage10_query_manifest.json"),
        "status": "REMEDIATION_AUDIT_PASS",
    }
    for p in (
        audit_root / "completed.json",
        root.with_name(root.name + "_remediation_audit.json"),
        portable,
    ):
        save(p, audit)
    save(audit_root / "publication-000000.json", {"phase": "remediation_audit"})
    save(audit_root / "failure.json.partial", b" " * 65536)
    checks = Checks()
    remediation.durability(root, manifest, repository, checks)
    assert all(checks.values()), [k for k, v in checks.items() if not v]
    first = work / "publication-000000.json"
    record = json.loads(first.read_bytes())
    save(first, {**record, "seal_present": True})
    checks = Checks()
    remediation.durability(root, manifest, repository, checks)
    assert not checks["publication_trace_state"]
    save(first, record)
    save(work / "workspace/checkpoint.json", {"path": local})
    checks = Checks()
    remediation.durability(root, manifest, repository, checks)
    assert not checks["no_local_checkpoint_dependency"]
    (work / "publication-000015.json").unlink()
    checks = Checks()
    remediation.durability(root, manifest, repository, checks)
    assert not checks["complete_p11_phase_sequence"]
