"""Guarded read-only validation of the pinned failed Stage 10 generation.

No generation, replay, checkpoint adoption, publication or mutation of failed
state. New private temporary SQL state and sanitized receipts are separate.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from ..execution_policy import require_goethe_nhr_slurm
from . import stage10_remediation_audit as audit
from .stages import s09_reference_input as a8
from .stages import s09_reference_io as base
from .stages import s10_query_contract as c
from .stages import s10_query_execution as ex
from .stages import s10_query_input as inputs
from .stages import s10_query_io as io
from .stages import s10_query_materializer as materializer
from .stages import s10_query_publication as pub
from .stages import s10_query_checkpoints as units
from .stages import s10_query_summary as summary
from .stages import s10_publication_trace as trace
from .stages import s10_query_receipts as receipts

FAILED_KEY = "stage10_development_20260924T092129Z_1b4c076c85ec"
FAILED_EXECUTABLE = "1b4c076c85ecb48c0a4e28668b69b99e0be128ad"
FAILED_MANIFEST = "56496ce7e5b23d8ce35141204173cea1fe9ac3a98f0c03b4dcb6e222a99baf74"
FAILED_WORK = FAILED_KEY + "_rlu4u7c1"


def compare_rows(db: Any, left: str, right: str) -> int:
    return audit.scalar(
        db,
        f"SELECT count(*) FROM (({left} EXCEPT ALL {right}) UNION ALL ({right} EXCEPT ALL {left}))",
    )


def inspect(root: Path, failed: Path, prior: Path, work: Path) -> dict[str, Any]:
    """Mechanics accept synthetic paths; the sole CLI pins controlled originals."""
    current = pub.validate_terminal(failed, FAILED_MANIFEST, False)
    before = c.read_json(prior / io.MANIFEST_NAME)
    c.require(
        c.sha256_file(prior / io.MANIFEST_NAME) == audit.PRIOR_MANIFEST,
        "STAGE10_FORENSIC_PRIOR_PIN",
    )
    c.require(
        pub.read_private(prior / pub.SEAL, limit=0) == b"",
        "STAGE10_FORENSIC_PRIOR_SEAL",
    )
    for key in (
        "input_binding",
        "input_binding_sha256",
        "science_sha256",
        "contract_sha256",
        "profile_sha256",
        "schema_bundle_sha256",
        "runtime",
        "budget_policy_sha256",
        "design_package_sha256",
    ):
        c.require(current[key] == before[key], "STAGE10_FORENSIC_BINDING_MISMATCH")
    c.require(
        current["operational_provenance"]["execution_git_sha"] == FAILED_EXECUTABLE,
        "STAGE10_FORENSIC_EXECUTABLE_MISMATCH",
    )
    binding = current["input_binding"]
    context_binding = c.identity(
        "stage10-context-input:v1",
        bytes.fromhex(a8.STAGE08_MANIFEST_SHA256),
        bytes.fromhex(inputs.STAGE06_MANIFEST),
        bytes.fromhex(inputs.STAGE09_MANIFEST),
    )
    input_id = c.identity("stage10-input:v1", c.canonical(binding))
    c.require(
        input_id.hex() == current["input_binding_sha256"],
        "STAGE10_FORENSIC_INPUT_BINDING_MISMATCH",
    )
    expected = materializer.checkpoint_binding(
        cast(
            Any,
            SimpleNamespace(
                science=bytes.fromhex(current["science_sha256"]),
                accepted=SimpleNamespace(
                    context_binding=context_binding, identifier=input_id
                ),
            ),
        ),
        FAILED_EXECUTABLE,
    )
    checkpoint_count = context_count = 0
    diagnostic_paths: list[Path] = []
    keys: set[bytes] = set()
    for prefix in materializer.SHARDS:
        folder = work / "workspace/shards" / prefix
        record = units.validate_prefix(folder, expected, prefix)
        checkpoint_count += record["unit_count"]
        context_count += record["context_count"]
        for entry in units.index_rows(folder):
            unit = folder / "units" / f"{entry['ordinal']:06}"
            saved = c.read_json(unit / "checkpoint.json")
            for key in saved["context_ids"]:
                value = bytes.fromhex(key)
                c.require(
                    value not in keys, "STAGE10_FORENSIC_DUPLICATE_CHECKPOINT_CONTEXT"
                )
                keys.add(value)
            diagnostic_paths.extend(
                unit / item["relative_path"] for item in saved["diagnostics"]["files"]
            )
        receipts.write(
            root / f"checkpoints-{prefix}.json",
            {
                "prefix": prefix,
                "units": record["unit_count"],
                "contexts": record["context_count"],
            },
        )
    c.require(context_count == len(keys), "STAGE10_FORENSIC_CHECKPOINT_CONTEXT_COUNT")
    with base.bounded_connection(root / "spill", memory="16GB") as db:
        db.execute("SET max_temp_directory_size='256MB'")
        fingerprints: dict[str, Any] = {}
        for label, directory, manifest in (
            ("old", prior, before),
            ("new", failed, current),
        ):
            fingerprints[label] = {}
            observed_keys: set[bytes] = set()
            for record in manifest["relations"]:
                paths = io.validate_relation(directory, record)
                name = record["name"]
                for row in base.parquet_rows(paths, batch_rows=1):
                    c.require(
                        row["query_context_id"] in keys,
                        "STAGE10_FORENSIC_UNEXPECTED_CONTEXT",
                    )
                    observed_keys.add(row["query_context_id"])
                    io.check_identity(
                        row,
                        name,
                        context_binding,
                        input_id,
                        bytes.fromhex(current["science_sha256"]),
                    )
                fingerprints[label][name] = record["logical_sha256"]
                db.execute(
                    f"CREATE VIEW {label}_{name} AS SELECT * FROM {io.parquet_sql(paths)}"
                )
                if label == "new":
                    db.execute(f"CREATE VIEW {name} AS SELECT * FROM new_{name}")
            c.require(observed_keys == keys, "STAGE10_FORENSIC_MISSING_CONTEXT")
        for stage, names in (
            (
                "stage08",
                (
                    "source_candidate_map",
                    "parser_component_evidence",
                    "candidate_evidence",
                ),
            ),
            ("stage09", ("candidate_reference_evidence",)),
        ):
            authority = binding[stage]
            anchor = inputs.controlled_path(Path(authority["approved_anchor"]))
            for name in names:
                records = [
                    r
                    for r in authority["files"]
                    if r["relative_path"].startswith(name + "/")
                ]
                c.require(bool(records), "STAGE10_FORENSIC_INPUT_RELATION_MISSING")
                selected_paths = audit.files(anchor, records)
                db.execute(
                    f"CREATE VIEW {name} AS SELECT * FROM {io.parquet_sql(selected_paths)}"
                )
        db.execute("CREATE VIEW stage10_sources AS SELECT * FROM source_candidate_map")
        db.execute("CREATE VIEW stage10_candidates AS SELECT * FROM candidate_evidence")
        db.execute(
            "CREATE VIEW stage10_components AS SELECT * FROM parser_component_evidence"
        )
        db.execute(
            "CREATE VIEW stage10_context_diagnostics AS SELECT * FROM "
            + io.parquet_sql(diagnostic_paths)
        )
        db.execute(
            "CREATE VIEW stage10_context_keys AS SELECT DISTINCT query_context_id,stable_source_row_id_v1,stage06_exact_candidate_id,stage08_representation FROM query_family_decision"
        )
        source_rows = base.sorted_rows(
            db,
            "SELECT stable_source_row_id_v1,stage06_standard_exact_candidate_id,stage06_native_exact_candidate_id FROM source_candidate_map",
            batch_rows=1024,
        )
        expected_keys = set()
        for row in source_rows:
            for role in c.ROLES:
                if row[f"stage06_{role.lower()}_exact_candidate_id"] is not None:
                    expected_keys.add(
                        c.context_id(
                            context_binding, row["stable_source_row_id_v1"], role
                        )
                    )
        c.require(
            keys == expected_keys, "STAGE10_FORENSIC_OCCURRENCE_POPULATION_MISMATCH"
        )
        summary.zero(
            db,
            """SELECT count(*) FROM stage10_context_keys k JOIN source_candidate_map s USING(stable_source_row_id_v1)
          WHERE k.stage06_exact_candidate_id IS DISTINCT FROM CASE k.stage08_representation
          WHEN 'STANDARD' THEN s.stage06_standard_exact_candidate_id ELSE s.stage06_native_exact_candidate_id END""",
            "STAGE10_FORENSIC_CANDIDATE_MAP_BACK",
        )
        result = audit.reconcile(db)
        regenerated_summary = summary.build_summary(
            db, input_id, bytes.fromhex(current["science_sha256"])
        )
        summary.reconcile_summary(
            c.read_json(failed / io.SUMMARY_NAME), regenerated_summary
        )
        result.update(
            {
                "source_rows": regenerated_summary["input_counts"]["source_rows"][
                    "count"
                ],
                "relation_counts": {
                    r["name"]: r["row_count"] for r in current["relations"]
                },
                "checkpoints_validated": checkpoint_count,
                "contexts_validated": context_count,
                "relation_fingerprints": fingerprints,
                "summary_reconciled": True,
                "scientific_contexts_regenerated": 0,
                "certificates_generated": 0,
                "checkpoints_adopted": 0,
                "publication_performed": False,
            }
        )
    registration = pub.registration(pub.bindings(failed, current, FAILED_MANIFEST))
    body = {"protocol": registration["protocol"], "bindings": registration["bindings"]}
    c.require(
        registration["commit_record_id"]
        == hashlib.sha256(
            b"SAFE:publication-commit:v2\0" + pub.canonical(body)
        ).hexdigest(),
        "STAGE10_FORENSIC_REGISTRATION_HASH",
    )
    result["registration_construction_hash_valid"] = True
    result["status"] = "STAGE10_PRESERVED_GENERATION_FORENSICS_PASS"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", required=True)
    parser.add_argument("--report-root", type=Path, required=True)
    args = parser.parse_args()
    require_goethe_nhr_slurm("stage10-publication-forensics")
    c.require_runtime()
    ex.verify_design(ex.REPOSITORY)

    def git(*values: str) -> str:
        return subprocess.check_output(
            ["git", *values], cwd=ex.REPOSITORY, text=True
        ).strip()

    c.require(
        git("rev-parse", "HEAD") == args.executable
        and not git("status", "--porcelain"),
        "STAGE10_FORENSIC_CLEAN_EXECUTABLE_REQUIRED",
    )
    c.require(
        subprocess.run(
            ["git", "symbolic-ref", "-q", "HEAD"],
            cwd=ex.REPOSITORY,
            capture_output=True,
        ).returncode
        == 1,
        "STAGE10_FORENSIC_DETACHED_REQUIRED",
    )
    c.require(
        os.environ.get("SLURM_RESTART_COUNT", "0") == "0",
        "STAGE10_AUTOMATIC_RESTART_PROHIBITED",
    )
    c.require(
        ex.project_quota_available() >= 512 * 1024**2,
        "STAGE10_FORENSIC_QUOTA_RESERVE_INSUFFICIENT",
    )
    project = inputs.PROJECT_ALIAS.resolve(strict=True)
    parent = project / ex.PUBLISH_RELATIVE
    root = args.report_root
    c.require(
        root.parent == parent / "work" and root.name.startswith("forensics_1781277_"),
        "STAGE10_FORENSIC_REPORT_SCOPE",
    )
    pub.check_parent(root)
    root.mkdir(mode=0o700)
    reporter = trace.PublicationTrace(root, parent / FAILED_KEY, args.executable)
    try:
        with ex.offline_network():
            runtime = ex.runtime_ready(project / ex.RUNTIME_RELATIVE, ex.REPOSITORY)
            runtime.close()
            result = inspect(
                root,
                parent / FAILED_KEY,
                parent / audit.PRIOR_KEY,
                parent / "work" / FAILED_WORK,
            )
        result.update(
            {
                "forensic_executable": args.executable,
                "job_id": os.environ["SLURM_JOB_ID"],
                "failed_manifest": FAILED_MANIFEST,
            }
        )
        receipts.write(root / "result.json", result)
    except BaseException as error:
        reporter.failure(error)
        print("STAGE10_PRESERVED_GENERATION_FORENSICS_FAILED")
        return 1
    print("STAGE10_PRESERVED_GENERATION_FORENSICS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
