"""Read-only C01/C02 reconciliation after the one authorized candidate run.

No generation, replay, publication or repair occurs here. Only aggregate evidence
is written beside the new artifact. The failed-review artifact is never mutated.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
from typing import Any

from ..execution_policy import require_goethe_nhr_slurm
from .stages import s09_reference_io as generic
from .stages import s09_reference_pack as pack
from .stages import s10_query_contract as c
from .stages import s10_query_execution as execution
from .stages import s10_query_input as inputs
from .stages import s10_query_io as io
from .stages import s10_query_publication as pub
from .stages import s10_query_receipts as receipts
from .stages import s10_query_storage as storage
from .stages import s10_publication_trace as trace
from .stages import s10_query_operations as ops

PRIOR_KEY = "stage10_development_20260921T112356Z_63f3cd107e69"
PRIOR_MANIFEST = "085b05f6201831de6aa908c599bb5541a85cc185a48022d2d93d1e0a9afcc3fa"
PRIOR_LOGICAL = "70abebdaeee44cf0eae09eb89e4ed68ef087f1596bfa86ea1bef6aef57ceed92"
EXCLUSION = "PARSER_ONLY_FIELD_EXCLUDED"


def scalar(db: Any, query: str) -> int:
    return int(db.execute(query).fetchone()[0])


def reconcile(db: Any) -> dict[str, Any]:
    """Independent relational oracle; supplied views are manifest-bound inputs.

    Required views: old/new_query_hypothesis, old/new_query_family_decision,
    source_candidate_map and parser_component_evidence. No protected value is
    returned. The old operative source-field decisions were independently
    reconciled; exact equality below retains those gates and all their lineage.
    """

    def difference(left: str, right: str) -> int:
        return scalar(
            db,
            f"SELECT count(*) FROM (({left} EXCEPT ALL {right}) UNION ALL ({right} EXCEPT ALL {left}))",
        )

    hypothesis_difference = difference(
        "SELECT * FROM old_query_hypothesis", "SELECT * FROM new_query_hypothesis"
    )
    c.require(hypothesis_difference == 0, "STAGE10_C01_REMEDIATION_SCIENTIFIC_DRIFT")
    stripped = """SELECT * REPLACE(list_transform(field_decisions, f ->
        struct_update(f,reason_codes := list_filter(f.reason_codes,r -> r <> 'PARSER_ONLY_FIELD_EXCLUDED'))) AS field_decisions)
        FROM new_query_family_decision"""
    decision_difference = difference(
        "SELECT * FROM old_query_family_decision", stripped
    )
    c.require(decision_difference == 0, "STAGE10_C01_REMEDIATION_SCIENTIFIC_DRIFT")
    # Reconstruct exact field decisions from prior independently validated gates.
    # This oracle is independent of the repaired generator and never inspects
    # text to decide trust. Reasons describe excluded parser fallback per SLOT.
    expected = """SELECT * REPLACE(list_transform(field_decisions, f ->
      struct_update(f,reason_codes := CASE WHEN f.disposition='OMIT' AND f.field IN ('postalcode','locality','region','country')
      THEN list_append(f.reason_codes,'PARSER_ONLY_FIELD_EXCLUDED') ELSE f.reason_codes END)) AS field_decisions)
      FROM old_query_family_decision"""
    provenance_difference = difference(
        expected, "SELECT * FROM new_query_family_decision"
    )
    c.require(provenance_difference == 0, "STAGE10_C01_REQUIRED_PROVENANCE_MISMATCH")
    duplicates = scalar(
        db,
        """SELECT count(*) FROM new_query_family_decision
      WHERE family='Q4' AND (len(field_decisions)<>6 OR len(list_distinct(list_transform(field_decisions,f -> f.field)))<>6
      OR len(list_filter(field_decisions,f -> len(f.reason_codes)<>len(list_distinct(f.reason_codes))))<>0)""",
    )
    c.require(duplicates == 0, "STAGE10_C01_DUPLICATE_PROVENANCE")
    db.execute("""CREATE TEMP VIEW remediation_fields AS
      SELECT d.query_context_id,d.stage06_exact_candidate_id,d.stable_source_row_id_v1,f.field,f.disposition,f.reason_codes
      FROM new_query_family_decision d,unnest(d.field_decisions) u(f) WHERE d.family='Q4'""")
    db.execute("""CREATE TEMP VIEW remediation_parser_fields AS
      SELECT DISTINCT stage06_exact_candidate_id,CASE
      WHEN stage08_safe_parser_evidence_component='PARSER_POSTCODE' THEN 'postalcode'
      WHEN stage08_safe_parser_evidence_component IN ('PARSER_CITY','PARSER_SUBURB','PARSER_CITY_DISTRICT','PARSER_ISLAND') THEN 'locality'
      WHEN stage08_safe_parser_evidence_component='PARSER_COUNTRY' THEN 'country'
      ELSE 'region' END AS field
      FROM parser_component_evidence WHERE stage08_safe_parser_evidence_component IN
      ('PARSER_POSTCODE','PARSER_CITY','PARSER_SUBURB','PARSER_CITY_DISTRICT','PARSER_ISLAND',
       'PARSER_STATE_DISTRICT','PARSER_STATE','PARSER_COUNTRY_REGION','PARSER_COUNTRY')""")
    # Geography-to-slot association is only an aggregate diagnostic. In particular
    # a suburb/state label neither acquires the slot's semantic level nor trust.
    parser_slots = """FROM remediation_fields f JOIN remediation_parser_fields p
      USING(stage06_exact_candidate_id,field) WHERE f.disposition<>'NOT_APPLICABLE'"""
    payload_violations = scalar(
        db,
        """SELECT count(*) FROM new_query_family_decision d
      JOIN new_query_hypothesis h USING(query_context_id,hypothesis_id)
      JOIN source_candidate_map s ON s.stable_source_row_id_v1=d.stable_source_row_id_v1
      WHERE d.family='Q4' AND (h.intent.country IS NOT NULL OR h.intent.region IS NOT NULL
        OR (h.intent.postalcode IS NOT NULL AND h.intent.postalcode IS DISTINCT FROM s.stage03_clean_postcode)
        OR (h.intent.locality IS NOT NULL AND h.intent.locality IS DISTINCT FROM s.stage03_clean_city))""",
    )
    c.require(payload_violations == 0, "STAGE10_C01_SOURCE_ANCHOR_MISMATCH")
    matrix = db.execute("""SELECT field,disposition,reason_codes,count(*) FROM remediation_fields
      GROUP BY ALL ORDER BY field,disposition,reason_codes""").fetchall()
    anchor_matrix = db.execute("""SELECT field,disposition,
      CASE field WHEN 'postalcode' THEN coalesce(s.stage03_clean_postcode,'')<>''
        WHEN 'locality' THEN coalesce(s.stage03_clean_city,'')<>''
        WHEN 'region' THEN coalesce(s.stage03_clean_region_in_country,'')<>''
        WHEN 'country' THEN coalesce(s.stage03_clean_country_iso_code,'')<>'' END AS source_value_present,count(*)
      FROM remediation_fields f JOIN source_candidate_map s USING(stable_source_row_id_v1)
      WHERE field IN ('postalcode','locality','region','country') GROUP BY ALL ORDER BY ALL""").fetchall()
    result = {
        "query_hypothesis_logically_equal": True,
        "scientific_decision_projection_equal": True,
        "country_eligible_contexts": scalar(
            db,
            "SELECT count(*) FROM remediation_fields WHERE field='boundary_country' AND disposition='INCLUDE'",
        ),
        "parser_geography_contexts": scalar(
            db, "SELECT count(DISTINCT f.query_context_id) " + parser_slots
        ),
        "parser_geography_omitted_field_slots": scalar(
            db, "SELECT count(*) " + parser_slots + " AND f.disposition='OMIT'"
        ),
        "parser_geography_omitted_slots_missing_exclusion": scalar(
            db,
            "SELECT count(*) "
            + parser_slots
            + " AND f.disposition='OMIT' AND NOT list_contains(f.reason_codes,'PARSER_ONLY_FIELD_EXCLUDED')",
        ),
        "parser_only_field_exclusion_decisions": scalar(
            db,
            "SELECT count(*) FROM remediation_fields WHERE list_contains(reason_codes,'PARSER_ONLY_FIELD_EXCLUDED')",
        ),
        "included_source_fields_labelled_parser_only": scalar(
            db,
            "SELECT count(*) FROM remediation_fields WHERE disposition='INCLUDE' AND list_contains(reason_codes,'PARSER_ONLY_FIELD_EXCLUDED')",
        ),
        "required_field_decisions": scalar(
            db, "SELECT count(*) FROM remediation_fields"
        ),
        "missing_or_incorrect_required_field_decisions": provenance_difference,
        "duplicate_provenance_violations": duplicates,
        "payload_source_anchor_violations": payload_violations,
        "field_decision_counts": [
            dict(zip(("field", "disposition", "reason_codes", "count"), row))
            for row in matrix
        ],
        "source_presence_field_counts": [
            dict(zip(("field", "disposition", "source_value_present", "count"), row))
            for row in anchor_matrix
        ],
    }
    c.require(
        result["parser_geography_omitted_slots_missing_exclusion"]
        == result["included_source_fields_labelled_parser_only"]
        == 0,
        "STAGE10_C01_FIELD_SCOPE_MISMATCH",
    )
    db.execute("DROP VIEW remediation_fields")
    db.execute("DROP VIEW remediation_parser_fields")
    return result


def files(root: Path, records: list[dict[str, Any]]) -> list[Path]:
    result = []
    for item in records:
        path = pack.confined(root, item["relative_path"])
        pack.regular_private(path)
        c.require(
            path.stat().st_size == item["bytes"]
            and c.sha256_file(path) == item["sha256"],
            "STAGE10_REMEDIATION_FILE_MISMATCH",
        )
        result.append(path)
    return result


def audit(config: execution.Stage10Config) -> dict[str, Any]:
    require_goethe_nhr_slurm("stage10-remediation-audit")
    config.preflight(new_generation=False)
    new = inputs.controlled_path(config.output_directory)
    parent = new.parent / "work"
    pub.check_parent(parent / "reserved")
    root = parent / (new.name + "_remediation_audit")
    root.mkdir(mode=0o700)
    observer = trace.PublicationTrace(root, new, config.execution_git_sha)
    try:
        with ops.termination_guard(
            on_termination=lambda: observer.failure(
                c.Stage10Error("STAGE10_TERMINATED")
            )
        ):
            scratch = storage.create_transient("remediation_audit", reserve=0)
            observer.local_workspace = scratch
            observer("remediation_audit")
            report = _audit(config, scratch)
            receipts.write(new.with_name(new.name + "_remediation_audit.json"), report)
            receipts.write(root / "completed.json", report)
            return report
    except BaseException as error:
        try:
            observer.failure(error)
        except BaseException:
            pass  # Preserve primary failure even if the receipt cannot be persisted.
        raise


def _audit(config: execution.Stage10Config, scratch: Path) -> dict[str, Any]:
    new = inputs.controlled_path(config.output_directory)
    old = inputs.controlled_path(new.parent / PRIOR_KEY)
    c.require(old != new, "STAGE10_REMEDIATION_NEW_ARTIFACT_REQUIRED")
    old_raw = pub.read_private(old / io.MANIFEST_NAME)
    c.require(
        hashlib.sha256(old_raw).hexdigest() == PRIOR_MANIFEST,
        "STAGE10_REMEDIATION_PRIOR_PIN_MISMATCH",
    )
    prior = c.read_json(old / io.MANIFEST_NAME)
    c.require(
        prior["logical_sha256"] == PRIOR_LOGICAL
        and pub.read_private(old / pub.SEAL, limit=0) == b"",
        "STAGE10_REMEDIATION_PRIOR_IDENTITY_MISMATCH",
    )
    new_sha = c.sha256_file(new / io.MANIFEST_NAME)
    current = pub.validate_terminal(new, new_sha, True)
    c.require(
        current["operational_provenance"]["execution_git_sha"]
        == config.execution_git_sha,
        "STAGE10_REMEDIATION_EXECUTABLE_MISMATCH",
    )
    for key in (
        "input_binding",
        "input_binding_sha256",
        "design_package_sha256",
        "contract_sha256",
        "profile_sha256",
        "schema_bundle_sha256",
        "science_sha256",
        "budget_policy_sha256",
        "runtime",
    ):
        c.require(
            prior[key] == current[key], "STAGE10_REMEDIATION_FROZEN_BINDING_DRIFT"
        )
    report: dict[str, Any] = {
        "audit_version": "stage10_c01_c02_remediation_v1",
        "old_manifest_sha256": PRIOR_MANIFEST,
        "new_manifest_sha256": new_sha,
        "execution_git_sha": config.execution_git_sha,
        "job_id": os.environ["SLURM_JOB_ID"],
    }
    with (
        execution.offline_network(),
        generic.bounded_connection(
            scratch / "spill", database=scratch / "audit.duckdb"
        ) as db,
    ):
        fingerprints: dict[str, Any] = {}
        for prefix, root, manifest in [("old", old, prior), ("new", new, current)]:
            fingerprints[prefix] = {}
            for record in manifest["relations"]:
                name = record["name"]
                c.require(name in c.RELATIONS, "STAGE10_REMEDIATION_RELATION_INVALID")
                paths = files(root, record["files"])
                digest = io.relation_fingerprint(
                    name, record["row_count"], generic.parquet_rows(paths, batch_rows=1)
                ).hex()
                c.require(
                    digest == record["logical_sha256"],
                    "STAGE10_REMEDIATION_LOGICAL_MISMATCH",
                )
                fingerprints[prefix][name] = digest
                db.execute(
                    f"CREATE VIEW {prefix}_{name} AS SELECT * FROM {io.parquet_sql(paths)}"
                )
        anchor = inputs.controlled_path(
            Path(current["input_binding"]["stage08"]["approved_anchor"])
        )
        for name in ("source_candidate_map", "parser_component_evidence"):
            records = [
                r
                for r in current["input_binding"]["stage08"]["files"]
                if r["relative_path"].startswith(name + "/")
            ]
            c.require(bool(records), "STAGE10_REMEDIATION_STAGE08_RELATION_MISSING")
            paths = files(anchor, records)
            db.execute(f"CREATE VIEW {name} AS SELECT * FROM {io.parquet_sql(paths)}")
        report.update(reconcile(db))
        report["relation_fingerprints"] = fingerprints
    record = c.read_json(new / io.SUCCESS_NAME)
    binding = record["bindings"]
    c.require(
        binding["namespace"] == "STAGE10_DEVELOPMENT_QUERY_PLAN"
        and binding["stage10_input_binding_sha256"] == current["input_binding_sha256"],
        "STAGE10_C02_REGISTRATION_INVALID",
    )
    c.require(
        record["commit_record_id"]
        == hashlib.sha256(
            b"SAFE:publication-commit:v2\0"
            + pub.canonical({"protocol": record["protocol"], "bindings": binding})
        ).hexdigest(),
        "STAGE10_C02_REGISTRATION_HASH_INVALID",
    )
    report["registration"] = {
        "namespace": binding["namespace"],
        "input_binding_key": "stage10_input_binding_sha256",
        "portable_hash_valid": True,
        "commit_record_id": record["commit_record_id"],
    }
    report["status"] = "REMEDIATION_AUDIT_PASS"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage06-root", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--execution-git-sha", required=True)
    args = parser.parse_args()
    config = execution.Stage10Config(
        args.stage06_root, args.output_directory, args.execution_git_sha
    )
    try:
        audit(config)
    except Exception:
        # Never print engine diagnostics or arbitrary path/value contents.
        print("STAGE10_REMEDIATION_AUDIT_FAILED")
        return 1
    print("STAGE10_REMEDIATION_AUDIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
