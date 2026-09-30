"""Exercise the complete post-publication audit with invented private artifacts."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from safe_geocoding_pipeline.preprocessing import stage10_remediation_audit as audit
from safe_geocoding_pipeline.preprocessing.stages import s10_query_storage as storage
from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s10_query_execution as ex
from safe_geocoding_pipeline.preprocessing.stages import s10_query_families as f
from safe_geocoding_pipeline.preprocessing.stages import s10_query_input as inputs
from safe_geocoding_pipeline.preprocessing.stages import s10_query_io as io
from safe_geocoding_pipeline.preprocessing.stages import s10_query_publication as pub
from test_stage10_query_families import SyntheticTransform, context
from test_stage10_review_remediation import prior_scientific_projection
from test_stage10_publication import build as publication_fixture


def artifact_fixture(
    tmp_path: Path, monkeypatch: Any, fault: str | None = None
) -> ex.Stage10Config:
    monkeypatch.setattr(audit, "require_goethe_nhr_slurm", lambda *a: None)
    monkeypatch.setattr(ex.Stage10Config, "preflight", lambda self, **kw: None)

    def synthetic_local(*args: Any, **kwargs: Any) -> Path:
        local = tmp_path / "synthetic-audit-local"
        local.mkdir(mode=0o700)
        return local

    monkeypatch.setattr(storage, "create_transient", synthetic_local)
    monkeypatch.setattr(inputs, "PROJECT_ALIAS", tmp_path)
    monkeypatch.setenv("SLURM_JOB_ID", "SYNTHETIC_ONLY")
    parent = tmp_path / "development"
    parent.mkdir(mode=0o700)
    (parent / "work").mkdir(mode=0o700)
    old, new = parent / audit.PRIOR_KEY, parent / "synthetic_new"
    old.mkdir(mode=0o700)
    ctx = context(
        tmp_path, components=[("city", "parser place"), ("postcode", "99999")]
    )
    pair = f.generate(ctx, SyntheticTransform())
    before = prior_scientific_projection(pair)
    after = list(copy.deepcopy(pair))
    if fault == "hypothesis":
        after[0][0]["intent"]["boundary_country"] = "US"
        after[0][0]["representation_fingerprint"] = c.intent_fingerprint(
            after[0][0]["intent"]
        )
    elif fault == "missing":
        after[1] = prior_scientific_projection(after)[1]
    elif fault == "duplicate":
        q4 = next(d for d in after[1] if d["family"] == "Q4")
        q4["field_decisions"].append(copy.deepcopy(q4["field_decisions"][-1]))
    elif fault == "context":
        next(d for d in after[1] if d["family"] == "Q4")["stable_source_row_id_v1"] = (
            b"x" * 32
        )
    stage8 = tmp_path / "synthetic_stage08"
    stage8.mkdir(mode=0o700)
    source = {
        "stable_source_row_id_v1": ctx.source_id,
        "stage03_clean_city": ctx.source_clean_locality,
        "stage03_clean_postcode": ctx.source_clean_postcode,
        "stage03_clean_region_in_country": "Example Region",
        "stage03_clean_country_iso_code": "DE",
    }
    stage8files = []
    for name, rows in [
        ("source_candidate_map", [source]),
        (
            "parser_component_evidence",
            [
                {
                    "stage06_exact_candidate_id": ctx.candidate_id,
                    "stage08_safe_parser_evidence_component": label,
                }
                for label in [
                    "PARSER_CITY",
                    "PARSER_POSTCODE",
                    "PARSER_STATE",
                    "PARSER_STATE",
                ]
            ],
        ),
    ]:
        folder = stage8 / name
        folder.mkdir(mode=0o700)
        path = folder / "invented.parquet"
        pq.write_table(pa.Table.from_pylist(rows), path)
        path.chmod(0o600)
        stage8files.append(
            {
                "relative_path": path.relative_to(stage8).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": c.sha256_file(path),
            }
        )
    binding = {"stage08": {"approved_anchor": str(stage8), "files": stage8files}}

    def build(root: Path, pair: Any) -> dict[str, Any]:
        manifest = publication_fixture(root)
        manifest["metadata_inventory"] = [manifest["relations"][0]["files"][0]]
        manifest["relations"] = []
        for name, rows in zip(c.RELATIONS, pair, strict=True):
            rows = sorted(rows, key=lambda r: tuple(r[k] for k in c.ORDER_KEYS[name]))
            folder = root / name
            writer = io.RelationWriter(folder, io.output_schema(name))
            for row in rows:
                writer.append(row)
            writer.close()
            paths = sorted(folder.glob("*.parquet"))
            manifest["relations"].append(
                {
                    "name": name,
                    "row_count": len(rows),
                    "schema_sha256": c.schema_fingerprint(name).hex(),
                    "logical_sha256": io.relation_fingerprint(
                        name, len(rows), rows
                    ).hex(),
                    "files": [
                        {
                            "relative_path": p.relative_to(root).as_posix(),
                            "bytes": p.stat().st_size,
                            "sha256": c.sha256_file(p),
                        }
                        for p in paths
                    ],
                }
            )
        manifest.update(
            input_binding=binding, design_package_sha256=c.DESIGN_PACKAGE_SHA256
        )
        return dict(manifest)

    prior = build(old, before)
    prior["kind"] = "STAGE10_DEVELOPMENT_QUERY_HYPOTHESES"
    io.write_json(old / io.MANIFEST_NAME, prior)
    io.write_exclusive(old / pub.SEAL, b"")
    monkeypatch.setattr(audit, "PRIOR_MANIFEST", c.sha256_file(old / io.MANIFEST_NAME))
    monkeypatch.setattr(audit, "PRIOR_LOGICAL", prior["logical_sha256"])
    pub.publish(new, lambda p: build(p, after), pub.validate_terminal)
    return ex.Stage10Config(tmp_path / "synthetic_stage06", new, "6" * 40)


def test_complete_audit_reads_real_parquet_and_reconciles_all_fields(
    tmp_path: Path, monkeypatch: Any
) -> None:
    config = artifact_fixture(tmp_path, monkeypatch)
    prior = config.output_directory.parent / audit.PRIOR_KEY
    before = {
        p.relative_to(prior): p.read_bytes() for p in prior.rglob("*") if p.is_file()
    }
    report = audit.audit(config)
    assert report["status"] == "REMEDIATION_AUDIT_PASS"
    assert (
        report["country_eligible_contexts"] == report["parser_geography_contexts"] == 1
    )
    assert report["required_field_decisions"] == 6
    assert report["parser_geography_omitted_field_slots"] == 2
    assert report["parser_only_field_exclusion_decisions"] == 3
    assert (
        report["missing_or_incorrect_required_field_decisions"]
        == report["duplicate_provenance_violations"]
        == 0
    )
    assert (
        report["relation_fingerprints"]["old"]["query_hypothesis"]
        == report["relation_fingerprints"]["new"]["query_hypothesis"]
    )
    assert (
        report["relation_fingerprints"]["old"]["query_family_decision"]
        != report["relation_fingerprints"]["new"]["query_family_decision"]
    )
    assert report["registration"]["namespace"] == "STAGE10_DEVELOPMENT_QUERY_PLAN"
    assert b"Exampleville" not in c.canonical(report)
    assert {
        p.relative_to(prior): p.read_bytes() for p in prior.rglob("*") if p.is_file()
    } == before


@pytest.mark.parametrize(
    "fault,code",
    [
        ("hypothesis", "SCIENTIFIC_DRIFT"),
        ("missing", "PROVENANCE_MISMATCH"),
        ("duplicate", "SCIENTIFIC_DRIFT"),
        ("context", "SCIENTIFIC_DRIFT"),
    ],
)
def test_audit_fails_closed_on_full_scope_drift(
    tmp_path: Path, monkeypatch: Any, fault: str, code: str
) -> None:
    config = artifact_fixture(tmp_path, monkeypatch, fault)
    with pytest.raises(c.Stage10Error, match=code):
        audit.audit(config)


def test_audit_guard_precedes_any_protected_path_access(
    tmp_path: Path, monkeypatch: Any
) -> None:
    from safe_geocoding_pipeline.execution_policy import ExecutionPolicyError

    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    with pytest.raises(ExecutionPolicyError):
        audit.audit(
            ex.Stage10Config(tmp_path / "absent", tmp_path / "absent", "0" * 40)
        )
