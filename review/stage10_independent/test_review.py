"""Synthetic integration and fault checks for the independent review harness."""

from __future__ import annotations

import os
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pyarrow as pa
import pyarrow.parquet as pq

import pytest

import common
import relations
import lineage
import structured
import review
from family_safety import oracle as safety
from operations import oracle as operations
from test_stage10_materializer import catalog
from test_stage10_query_families import SyntheticTransform
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_contract as s9
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_questions as sq
from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s10_query_input as inputs
from safe_geocoding_pipeline.preprocessing.stages import (
    s10_query_execution as execution,
)
from safe_geocoding_pipeline.preprocessing.stages import s10_query_io as io
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_input as a8
from test_stage10_query_evidence import fixture_rows
from test_stage10_context_pipeline import complete


class Checks(dict):
    def __call__(self, name, good):
        self[name] = self.get(name, True) and bool(good)


def test_separate_input_and_workspace_timer_scope():
    workspace = {
        "timings_inclusive": {"workspace_preparation": {}},
        "sql_categories": {"SETUP_OR_OTHER": {}},
    }
    before = {
        "phase": "input_validation",
        "timings_inclusive": {},
        "sql_categories": {},
    }
    after = {
        "phase": "input_validation",
        "timings_inclusive": {
            "input_validation": {"calls": 1, "wall_ns": 7, "cpu_ns": 3}
        },
        "sql_categories": {},
    }
    assert operations.numeric_timers(before, workspace)
    assert operations.numeric_timers(after, workspace)
    assert not set(after["timings_inclusive"]) <= set(workspace["timings_inclusive"])
    assert operations.numeric_timers(
        {
            "phase": "initialization",
            "timings_inclusive": {"workspace_preparation": {"calls": 1}},
            "sql_categories": {"SETUP_OR_OTHER": {"wall_ns": 2}},
        },
        workspace,
    )
    assert not operations.numeric_timers(
        {**after, "phase": "initialization"}, workspace
    )
    assert not operations.numeric_timers(
        {**after, "timings_inclusive": {"unknown": {"calls": 1}}}, workspace
    )
    assert not operations.numeric_timers(
        {**after, "sql_categories": {"SETUP_OR_OTHER": {"calls": 1}}}, workspace
    )
    for value in (True, -1, "synthetic non-numeric", 1.5):
        assert not operations.numeric_timers(
            {**after, "timings_inclusive": {"input_validation": {"calls": value}}},
            workspace,
        )


def test_portable_registration_and_frozen_bindings():
    assets = Path(__file__).resolve().parents[2] / "docs/scientific_assets"
    manifest_path = assets / "stage10_development_manifest_1774362.json"
    manifest = json.loads(manifest_path.read_bytes())
    assert common.file_sha(manifest_path) == review.MANIFEST
    assert all(manifest[k] == value for k, value in review.FROZEN.items())
    body = review.registration_body(review.KEY, manifest, review.MANIFEST)
    expected = {
        **body,
        "commit_record_id": hashlib.sha256(
            b"SAFE:publication-commit:v2\0" + common.canonical(body)
        ).hexdigest(),
    }
    observed = json.loads(
        (assets / "stage10_development_registration_1774362.json").read_bytes()
    )
    assert observed == expected


def test_log_audit_with_independent_input_progress(tmp_path):
    assets = Path(__file__).resolve().parents[2] / "docs/scientific_assets"
    manifest = json.loads(
        (assets / "stage10_development_manifest_1774362.json").read_bytes()
    )
    completed = json.loads(
        (assets / "stage10_development_completed_1774362.json").read_bytes()
    )
    progress = {
        "operational_version": "stage10_progress_v2",
        "phase": "input_validation",
        "failed_phase": None,
        "event": "progress",
        "counts": {},
        "observations": {},
        "timings_inclusive": {
            "input_validation": {"calls": 1, "wall_ns": 7, "cpu_ns": 3}
        },
        "sql_categories": {},
    }
    terminal = {
        "status": "STAGE10_DEVELOPMENT_CANDIDATE_PUBLISHED_NOT_ACCEPTED",
        "manifest_sha256": review.MANIFEST,
        "logical_sha256": manifest["logical_sha256"],
        "profile_sha256": manifest["profile_sha256"],
        "publication_key": review.KEY,
        "publication_disposition": "PASS",
        "commit_record_id": "0" * 64,
        "registration_sha256": "0" * 64,
        "protocol": "exclusive_run_commit_seal_v2_candidate",
        "relation_counts": {r["name"]: r["row_count"] for r in manifest["relations"]},
        "operating_budget": None,
        "pelias_calls": 0,
        "external_address_calls": 0,
    }
    stdout, stderr = tmp_path / "stdout", tmp_path / "stderr"
    stdout.write_bytes(common.canonical(progress) + common.canonical(terminal))
    stderr.write_bytes(b"")
    checks = Checks()
    assert (
        operations.audit_logs(stdout, stderr, manifest, completed, review.KEY, checks)
        == 2
    )
    assert {k for k, v in checks.items() if not v} == {"operations_stdout_count"}
    progress["timings_inclusive"]["input_validation"]["wall_ns"] = (
        "synthetic malformed timer"
    )
    stdout.write_bytes(common.canonical(progress) + common.canonical(terminal))
    checks = Checks()
    operations.audit_logs(stdout, stderr, manifest, completed, review.KEY, checks)
    assert not checks["operations_stdout_numeric_timers"]


@pytest.mark.parametrize(
    "value",
    [None, False, True, 0, 2**64 - 1, "α\nΩ", b"\x00\xff", ("a", [None, True, 3])],
)
def test_spec_encoder(value):
    assert common.identity("review-test:v1", value) == c.identity(
        "review-test:v1", value
    )
    assert safety.value_digest(value) == common.identity(
        "stage10-transform-value:v1", value
    )


@pytest.mark.parametrize("country", ["US", "JP", None, ""])
def test_source_argument_oracle(country):
    source = {
        "stable_source_row_id_v1": b"s" * 32,
        "stage06_standard_exact_candidate_id": b"c" * 32,
        "stage06_native_exact_candidate_id": None,
        "stage03_clean_country_iso_code": country,
        "stage03_clean_city": "Example City",
        "stage03_clean_postcode": "001-2345",
        "stage03_clean_region_in_country": "US-EX",
    }
    for trusted, status in [
        (None, "COUNTRY_CONFLICT"),
        (country, "COUNTRY_UNANIMOUS_VALID"),
    ]:
        candidate = {
            "stage06_exact_candidate_id": b"c" * 32,
            "stage07_trusted_country_iso_code": trusted,
            "stage07_country_provenance_status": status,
        }
        for question in sq.source_questions(source, candidate):
            for reference in s9.QUESTIONS[question.question_id].references:
                expected = [
                    o.argument(question.question_id, reference, question.country)[0]
                    for o in question.observations
                ]
                actual = structured.expected_arguments(
                    question.question_id,
                    reference,
                    country,
                    source["stage03_clean_postcode"],
                    source["stage03_clean_city"],
                    source["stage03_clean_region_in_country"],
                    trusted,
                    status,
                )
                assert actual == expected


@pytest.mark.parametrize("synthetic_inputs", [True, False], indirect=True)
def test_whole_synthetic_scientific_review(synthetic_inputs, tmp_path):
    work, artifact = catalog(synthetic_inputs, tmp_path / "workspace")
    checks = Checks()
    try:
        relations.derive_contexts(work.db, synthetic_inputs.context_binding, checks)
        aggregate = structured.run(work.db, checks)
        assert aggregate["country_available_contexts"] == 4
        assert aggregate["q4_missing_visible_parser_geography_exclusion"] == 0
        result = relations.baselines_and_boundaries(work.db, checks)
        assert not any(result["defect_counts"].values())
        result = safety.run(work.db, SyntheticTransform(), checks)
        assert (
            result["contexts"] == 4
            and result["q5_eligible"] == 4
            and result["q6_greek"] == 2
        )
        assert not any(v for k, v in result.items() if k.endswith("_mismatches"))
        selector_result = lineage.run(work.db, checks)
        assert not any(selector_result["certificate_mismatches"].values())
        # Expected population differences are distinct from invariant checks.
        allowed = {
            "source_context_distribution",
            "occurrence_counts",
            "all_baseline_q3_slots_reviewed",
            "q4_missing_visible_parser_geography_exclusion",
        }
        assert {k for k, v in checks.items() if not v} <= allowed
        relational_checks = Checks()
        relations.relational(work.db, relational_checks)
        for name in (
            "hypothesis_pk",
            "decision_pk",
            "six_decisions",
            "membership_fk",
            "rank_and_intent_unique",
            "family_ownership_order",
            "generation_rank_family_order",
            "role_family",
            "context_ceiling",
            "row_ceiling",
            "all_catalog",
            "budget_suppression",
        ):
            assert relational_checks[name]
        final = tmp_path / "final"
        final.mkdir(mode=0o700)
        manifest = artifact.build(final)
        result = relations.logical_and_identifiers(
            final, manifest, synthetic_inputs.context_binding, checks
        )
        assert all(not any(v["defect_counts"].values()) for v in result.values())
        # A real corruption must be found independently of the candidate validator.
        work.db.execute("CREATE TABLE corrupt_h AS SELECT * FROM query_hypothesis")
        work.db.execute("DROP VIEW query_hypothesis")
        work.db.execute("ALTER TABLE corrupt_h RENAME TO query_hypothesis")
        work.db.execute(
            "UPDATE query_hypothesis SET intent=struct_update(intent,text:='invented corruption') WHERE intent.search_mode='FULL_TEXT'"
        )
        mutation = Checks()
        result = relations.baselines_and_boundaries(work.db, mutation)
        assert not mutation["baseline_content"] and not mutation["q3_complete_intent"]
    finally:
        work.close()


@pytest.mark.parametrize("entry", ["review.py", "review_logs.py", "rereview.py"])
def test_entry_fails_closed_without_slurm(entry):
    env = dict(os.environ)
    env.pop("SLURM_JOB_ID", None)
    env.pop("SAFE_EXECUTION_SITE", None)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    result = subprocess.run(
        [sys.executable, "-B", str(Path(__file__).with_name(entry))],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert result.stdout == "REVIEW_HARNESS_INCOMPLETE\n"
    assert result.stderr == ""


def test_write_and_network_guard_in_isolated_process(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    source = """
import pathlib, socket, subprocess, sys
sys.path.insert(0, sys.argv[1])
import review
out = pathlib.Path(sys.argv[2])
allowed = {("/usr/bin/true",)}
review.install_write_guard(out, allowed)
(out / "permitted").write_text("synthetic")
for action in (
    lambda: (out.parent / "forbidden").write_text("synthetic"),
    lambda: socket.create_connection(("127.0.0.1", 1)),
    lambda: subprocess.run(["/usr/bin/false"]),
):
    try:
        action()
    except RuntimeError:
        pass
    else:
        raise AssertionError("guard did not reject")
assert subprocess.run(["/usr/bin/true"]).returncode == 0
allowed.clear()
try:
    subprocess.run(["/usr/bin/true"])
except RuntimeError:
    pass
else:
    raise AssertionError("expired process allowance")
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", source, str(Path(__file__).parent), str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert not (tmp_path / "forbidden").exists()


def test_q5_unique_boundary_safe_and_ambiguous():
    values = [(0, "house_number", "12"), (1, "road", "α road"), (2, "unit", "unit 5")]

    def reader(reverse):
        return iter(reversed(values) if reverse else values)

    safe = safety.q5(
        ("12 α road", "unit 5", "", ""), "PARSED_NONEMPTY", 3, reader, ("", "", "", "")
    )
    assert safe.text == "12 α road" and safe.removed[0]["source_slot"] == 2
    veto = safety.q5(
        ("12 α road", "unit 5", "", ""), "PARSED_NONEMPTY", 3, reader, ("5", "", "", "")
    )
    assert veto.reason == "UNIT_SOURCE_FIELD_CONFLICT"
    mixed = safety.q5(
        ("12 α road", "unit 5 street", "", ""),
        "PARSED_NONEMPTY",
        3,
        reader,
        ("", "", "", ""),
    )
    assert mixed.reason == "FAMILY_INELIGIBLE"


def test_script_oracle_and_runtime_error():
    scripts = safety.ScriptTable()
    assert scripts.eligible("12 α road", True) == "Greek"
    assert scripts.eligible("12 я road", True) == "Cyrillic"
    assert scripts.eligible("α я", True) is None
    assert scripts.eligible("x\u0301 α", True) is None
    assert scripts.eligible("\u0301 α", True) is None
    assert scripts.eligible("汉 α", True) is None

    class Broken:
        asset_binding = b"a" * 32

        def transform(self, *args):
            raise RuntimeError("SYNTHETIC_RUNTIME_FAILURE")

    with pytest.raises(RuntimeError, match="SYNTHETIC_RUNTIME_FAILURE"):
        safety.q6("12 α road", scripts, Broken())


def test_checkpoint_oracle_all_paths(synthetic_inputs, tmp_path):
    attempt = tmp_path / "attempt"
    attempt.mkdir(mode=0o700)
    work, artifact = catalog(synthetic_inputs, attempt / "workspace")
    final = tmp_path / "final"
    final.mkdir(mode=0o700)
    artifact.provenance["workspace"] = str(attempt)
    artifact.runtime_identity.update(
        lock_sha256=execution.RUNTIME_LOCK_SHA,
        specification_sha256="5d0a8f6906a8d93ac38d73a862d69e31e2e9e454e8d0518e0c13f9792256a916",
    )
    checks = Checks()
    try:
        relations.derive_contexts(work.db, synthetic_inputs.context_binding, Checks())
        manifest = artifact.build(final)
        manifest["input_binding"] = {
            "stage08": {"manifest_sha256": a8.STAGE08_MANIFEST_SHA256},
            "stage09": {"manifest_sha256": inputs.STAGE09_MANIFEST},
            "stage06_row_map": {"manifest_sha256": inputs.STAGE06_MANIFEST},
        }
        io.write_json(final / io.MANIFEST_NAME, manifest)
        completed = {
            "manifest_sha256": common.file_sha(final / io.MANIFEST_NAME),
            "logical_sha256": manifest["logical_sha256"],
            "progress": work.progress.snapshot(),
        }
        completed["progress"]["timings_inclusive"]["publication_scientific_replay"] = {
            "calls": 0
        }
        io.write_json(attempt / "completed.json", completed)
        inventory = {
            "receipts": [
                {
                    "path": "completed.json",
                    "bytes": (attempt / "completed.json").stat().st_size,
                    "sha256": common.file_sha(attempt / "completed.json"),
                }
            ],
            "receipt_count": 1,
        }
        result = operations.run(work.db, final, manifest, inventory, checks)
        assert result["context_count"] == 4
        assert (
            result["unit_final_hypothesis_differences"]
            == result["unit_final_decision_differences"]
            == 0
        )
        allowed = {
            "operations_receipt_count",
            "operations_three_replays",
            "operations_four_population_passes",
            "operations_candidate_population",
        }
        assert {k for k, v in checks.items() if not v} <= allowed
    finally:
        work.close()


@pytest.mark.parametrize("synthetic_inputs", [True], indirect=True)
@pytest.mark.parametrize(
    "postcode,country,gate,postal_state",
    [
        ("BAD", "US", "Q04", "SUPPORTED"),
        ("99123", "US", "Q08", "SUPPORTED"),
        ("00777", "US", None, "NOT_FOUND"),
        ("00777", "US", None, "NOT_EVALUABLE"),
        ("00123", "US ", "COUNTRY", "SUPPORTED"),
    ],
)
def test_structured_negative_and_absence_oracles(
    synthetic_inputs, reference_view, tmp_path, postcode, country, gate, postal_state
):
    candidate = next(common.parquet_rows(synthetic_inputs.paths["candidate_evidence"]))
    sources = list(common.parquet_rows(synthetic_inputs.paths["source_candidate_map"]))
    evidence = []
    objects = dict(reference_view.objects)
    members = {}
    for source in sources:
        source["stage03_clean_postcode"] = postcode
        source["stage03_clean_country_iso_code"] = country
        source["stage04_lower_postcode"] = postcode.lower()
        source["stage04_lower_country_iso_code"] = country.lower()
        if source["stage06_standard_exact_candidate_id"] is not None:
            _, _, checks, access = fixture_rows(
                reference_view,
                row=source,
                cand=candidate,
                postal_state=postal_state,
                pair_state=postal_state,
            )
            evidence.extend(checks)
            objects.update(access.objects)
            for identifier, witnesses in access.members.items():
                for ordinal, witness in enumerate(witnesses):
                    members[(identifier, ordinal)] = {
                        "match_set_id": identifier,
                        "member_ordinal": ordinal,
                        "witness": witness,
                    }
    for name, values in [
        ("source_candidate_map", sources),
        ("candidate_reference_evidence", evidence),
        ("reference_object", list(objects.values())),
        ("reference_match_member", list(members.values())),
    ]:
        path = synthetic_inputs.paths[name][0]
        schema = pq.read_schema(path)
        pq.write_table(
            pa.Table.from_pylist(
                [complete(schema, row) for row in values], schema=schema
            ),
            path,
        )
    work, artifact = catalog(synthetic_inputs, tmp_path / "workspace")
    checks = Checks()
    try:
        relations.derive_contexts(work.db, synthetic_inputs.context_binding, Checks())
        result = structured.run(work.db, checks)
        assert {k for k, v in checks.items() if not v} <= {
            "q4_missing_visible_parser_geography_exclusion"
        }
        assert result["q4_q04_negative_contexts"] == (4 if gate == "Q04" else 0)
        assert result["q4_q08_negative_contexts"] == (4 if gate == "Q08" else 0)
        assert result["country_unavailable_contexts"] == (4 if gate == "COUNTRY" else 0)
        if gate is None:
            assert result["q4_expected_postcode_contradiction_omissions"] == 0
    finally:
        work.close()
