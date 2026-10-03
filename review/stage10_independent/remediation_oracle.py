"""Independent C01 regression, full old/new equality and durable-only audit.

No candidate remediation-audit implementation is used. All row processing stays
inside the guarded reviewer database. Returned values are fixed aggregates only.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from common import canonical, file_sha, scalar
from operations import oracle as ops

OLD_KEY = "stage10_development_20260921T112356Z_63f3cd107e69"
OLD_MANIFEST = "085b05f6201831de6aa908c599bb5541a85cc185a48022d2d93d1e0a9afcc3fa"
OLD_DATASET = "70abebdaeee44cf0eae09eb89e4ed68ef087f1596bfa86ea1bef6aef57ceed92"
NEW_EXE = "cf9e0fe4c12eb85f78051904c636ad084d87a541"
EXCLUSION = "PARSER_ONLY_FIELD_EXCLUDED"
PHASES = (
    "input_validation",
    "workspace_preparation",
    "generation",
    "reservation",
    "build",
    "manifest",
    "manifest_fsync",
    "initial_validation",
    "registration_build",
    "registration_write",
    "registration_fsync",
    "prepared_validation",
    "seal_validation",
    "seal_create",
    "reopen",
    "final_check",
)


def c01(db, check):
    # The independent structured oracle derived these field values/reasons from
    # accepted SOURCE_ROW evidence, exact capabilities and complete witnesses.
    # Neither observed decision dispositions nor token multiplicity set policy.
    db.execute("""CREATE OR REPLACE TABLE rereview_expected_fields AS
        SELECT p.query_context_id,f.field,f.ordinal,
          p.boundary_country IS NOT NULL AND
          (f.field IN ('region','country') OR f.field='postalcode' AND p.postalcode IS NULL
           OR f.field='locality' AND p.locality IS NULL) should_exclude,
          CASE WHEN p.boundary_country IS NULL THEN 'NOT_APPLICABLE'
               WHEN f.field IN ('address','boundary_country') OR f.field='postalcode' AND p.postalcode IS NOT NULL
                 OR f.field='locality' AND p.locality IS NOT NULL THEN 'INCLUDE' ELSE 'OMIT' END disposition,
          CASE WHEN p.boundary_country IS NULL THEN [] WHEN f.field='region' THEN ['ADMIN_LEVEL_NOT_ESTABLISHED']
               WHEN f.field='postalcode' AND p.postcode_reason IS NOT NULL THEN [p.postcode_reason]
               WHEN f.field='locality' AND p.locality_reason IS NOT NULL THEN [p.locality_reason] ELSE [] END base_reasons
        FROM review_struct_policy p CROSS JOIN review_struct_field_names f""")
    db.execute("""CREATE OR REPLACE TABLE rereview_actual_fields AS
        SELECT d.query_context_id,d.family,d.stable_source_row_id_v1,d.stage06_exact_candidate_id,
          d.stage08_representation,u.ordinal,f.field,f.disposition,f.reason_codes,
          len(list_filter(f.reason_codes,r -> r='PARSER_ONLY_FIELD_EXCLUDED')) exclusions
        FROM query_family_decision d,unnest(d.field_decisions) WITH ORDINALITY u(f,ordinal)""")
    queries = {
        "missing": """SELECT count(*) FROM rereview_expected_fields e LEFT JOIN rereview_actual_fields a
            ON a.query_context_id=e.query_context_id AND a.ordinal=e.ordinal AND a.family='Q4'
            WHERE e.should_exclude AND (a.field IS DISTINCT FROM e.field OR coalesce(a.exclusions,0)=0)""",
        "duplicates": "SELECT count(*) FROM rereview_actual_fields WHERE exclusions>1 OR len(reason_codes)<>len(list_distinct(reason_codes))",
        "wrong_context": """SELECT count(*) FROM rereview_actual_fields a LEFT JOIN contexts k USING(query_context_id)
            LEFT JOIN review_country_context c USING(query_context_id) WHERE exclusions>0 AND
            (a.family<>'Q4' OR k.query_context_id IS NULL OR c.boundary_country IS NULL
             OR a.stable_source_row_id_v1 IS DISTINCT FROM k.stable_source_row_id_v1
             OR a.stage06_exact_candidate_id IS DISTINCT FROM k.stage06_exact_candidate_id
             OR a.stage08_representation IS DISTINCT FROM k.stage08_representation)""",
        "wrong_field": """SELECT count(*) FROM rereview_actual_fields a LEFT JOIN rereview_expected_fields e
             ON a.query_context_id=e.query_context_id AND a.ordinal=e.ordinal
             WHERE a.exclusions>0 AND (a.field IS DISTINCT FROM e.field OR e.should_exclude IS DISTINCT FROM true)""",
        "included_source_marked_parser_only": "SELECT count(*) FROM rereview_actual_fields WHERE disposition='INCLUDE' AND exclusions>0",
        "full_field_decision": """SELECT count(*) FROM rereview_expected_fields e FULL OUTER JOIN
            (SELECT * FROM rereview_actual_fields WHERE family='Q4') a
              ON a.query_context_id=e.query_context_id AND a.ordinal=e.ordinal
            WHERE a.field IS DISTINCT FROM e.field OR a.disposition IS DISTINCT FROM e.disposition
              OR a.reason_codes IS DISTINCT FROM list_concat(e.base_reasons,
                   CASE WHEN e.should_exclude THEN ['PARSER_ONLY_FIELD_EXCLUDED'] ELSE [] END)""",
        "non_q4_field_decisions": "SELECT count(*) FROM rereview_actual_fields WHERE family<>'Q4'",
        "source_anchor": """SELECT count(*) FROM query_family_decision d JOIN query_hypothesis h USING(hypothesis_id)
            JOIN contexts k ON k.query_context_id=d.query_context_id
            JOIN candidate_evidence c ON c.stage06_exact_candidate_id=k.stage06_exact_candidate_id
            JOIN source_candidate_map s ON s.stable_source_row_id_v1=k.stable_source_row_id_v1
            JOIN review_struct_policy p ON p.query_context_id=k.query_context_id
            WHERE d.family='Q4' AND (h.intent.address IS DISTINCT FROM c.stage06_candidate_lower
              OR h.intent.boundary_country IS DISTINCT FROM p.boundary_country
              OR h.intent.locality IS NOT NULL AND h.intent.locality IS DISTINCT FROM s.stage03_clean_city
              OR h.intent.postalcode IS NOT NULL AND h.intent.postalcode IS DISTINCT FROM s.stage03_clean_postcode)""",
        "parser_only_payload": """SELECT count(*) FROM query_family_decision d JOIN query_hypothesis h USING(hypothesis_id)
            JOIN rereview_expected_fields e ON e.query_context_id=d.query_context_id
            WHERE d.family='Q4' AND e.should_exclude AND CASE e.field
               WHEN 'postalcode' THEN h.intent.postalcode IS NOT NULL WHEN 'locality' THEN h.intent.locality IS NOT NULL
               WHEN 'region' THEN h.intent.region IS NOT NULL WHEN 'country' THEN h.intent.country IS NOT NULL ELSE true END""",
    }
    defects = {}
    for name, query in queries.items():
        defects[name] = scalar(db, query)
        check("c01_" + name, defects[name] == 0)
    expected = scalar(
        db, "SELECT count(*) FROM rereview_expected_fields WHERE should_exclude"
    )
    actual = scalar(
        db, "SELECT coalesce(sum(exclusions),0) FROM rereview_actual_fields"
    )
    check("c01_expected_equals_actual", expected == actual)
    counts = {}
    for field in ("postalcode", "locality", "region", "country"):
        counts[field] = [
            scalar(
                db,
                "SELECT count(*) FROM rereview_expected_fields WHERE should_exclude AND field=?",
                [field],
            ),
            scalar(
                db,
                "SELECT coalesce(sum(exclusions),0) FROM rereview_actual_fields WHERE field=?",
                [field],
            ),
        ]
    return {
        "expected": expected,
        "actual": actual,
        "field_counts": counts,
        "violations": defects,
    }


def compare_relations(db, check):
    # EXCEPT ALL preserves multiplicity. Every column participates. Only the
    # named reason is removed from the NEW field arrays for decision projection.
    projection = """SELECT * REPLACE(list_transform(field_decisions,f ->
        struct_update(f,reason_codes := list_filter(f.reason_codes,r -> r<>'PARSER_ONLY_FIELD_EXCLUDED')))
        AS field_decisions) FROM query_family_decision"""
    queries = {
        "hypotheses": (
            "SELECT * FROM query_hypothesis",
            "SELECT * FROM previous_query_hypothesis",
        ),
        "scientific_decisions": (
            projection,
            "SELECT * FROM previous_query_family_decision",
        ),
        "complete_decisions": (
            "SELECT * FROM query_family_decision",
            "SELECT * FROM previous_query_family_decision",
        ),
    }
    result = {}
    for name, (new, old) in queries.items():
        result[name + "_symmetric_difference"] = scalar(
            db,
            f"SELECT count(*) FROM (({new} EXCEPT ALL {old}) UNION ALL ({old} EXCEPT ALL {new}))",
        )
    for name in ("hypotheses", "scientific_decisions"):
        check("old_new_" + name + "_exact", result[name + "_symmetric_difference"] == 0)
    return result


def old_new(db, root, upstream, check):
    import relations
    import review as original
    from safe_geocoding_pipeline.preprocessing.stages import s10_query_io as io

    old = root.parent / OLD_KEY
    path = ops.confined(old, "stage10_query_manifest.json")
    if not ops.private(path) or file_sha(path) != OLD_MANIFEST:
        raise RuntimeError("REREVIEW_PREVIOUS_MANIFEST_BINDING")
    prior = ops.load(path)
    current = ops.load(root / "stage10_query_manifest.json")
    if prior["logical_sha256"] != OLD_DATASET:
        raise RuntimeError("REREVIEW_PREVIOUS_DATASET_BINDING")
    for key in (
        "input_binding",
        "input_binding_sha256",
        "contract_sha256",
        "profile_sha256",
        "schema_bundle_sha256",
        "science_sha256",
        "budget_policy_sha256",
        "runtime",
    ):
        if prior[key] != current[key]:
            raise RuntimeError("REREVIEW_INPUT_SCIENCE_BINDING_DRIFT")
    files = []
    for rec in [*prior["relations"], {"files": prior["metadata_inventory"]}]:
        for item in rec["files"]:
            p = ops.confined(old, item["relative_path"])
            if (
                not ops.private(p)
                or p.stat().st_size != item["bytes"]
                or file_sha(p) != item["sha256"]
            ):
                raise RuntimeError("REREVIEW_PREVIOUS_IMMUTABLE_INVENTORY")
            files.append(item["relative_path"])
    check(
        "old_artifact_private_exact_topology",
        ops.topology(
            old,
            set(files) | {"stage10_query_manifest.json", "_COMMITTED", "_SUCCESS.json"},
        ),
    )
    body = original.registration_body(old.name, prior, OLD_MANIFEST)
    import hashlib

    check(
        "old_registration_hash_unchanged",
        ops.load(old / "_SUCCESS.json")
        == {
            **body,
            "commit_record_id": hashlib.sha256(
                b"SAFE:publication-commit:v2\0" + canonical(body)
            ).hexdigest(),
        },
    )
    check("old_commit_seal_unchanged", (old / "_COMMITTED").read_bytes() == b"")

    # Independently rehash all old rows and IDs, using the already-corrected oracle.
    def prior_check(name, value):
        check("old_" + name, value)

    prior_hashes = relations.logical_and_identifiers(old, prior, upstream, prior_check)
    for rec in prior["relations"]:
        paths = [ops.confined(old, item["relative_path"]) for item in rec["files"]]
        db.execute(
            "CREATE VIEW previous_"
            + rec["name"]
            + " AS SELECT * FROM "
            + io.parquet_sql(paths)
        )
    result = compare_relations(db, check)
    result["old_relation_fingerprints"] = {
        k: v["logical_sha256"] for k, v in prior_hashes.items()
    }
    check(
        "old_new_hypothesis_logical_identity",
        prior["relations"][0]["logical_sha256"]
        == current["relations"][0]["logical_sha256"],
    )
    check(
        "old_new_only_expected_changed_decisions",
        result["complete_decisions_symmetric_difference"] == 2 * 68079,
    )
    for name in files:
        p = old / name
        expected = next(
            v["sha256"]
            for r in [*prior["relations"], {"files": prior["metadata_inventory"]}]
            for v in r["files"]
            if v["relative_path"] == name
        )
        check("old_artifact_after_reads_unchanged", file_sha(p) == expected)
    return result


def adapt_inventory(inventory):
    if (
        inventory["inventory_version"]
        != "stage10_remediated_candidate_review_inventory_v1"
        or inventory["job_id"] != "1785683"
    ):
        raise RuntimeError("REREVIEW_INVENTORY_VERSION")
    normalized = []
    for item in inventory["receipt_inventory"]:
        scope, name = item["path"].split("/", 1)
        if scope not in ("artifact", "execution") or (scope == "artifact") != (
            name in ops.FINAL_FILES
        ):
            raise RuntimeError("REREVIEW_RECEIPT_SCOPE")
        normalized.append({**item, "path": name})
    return {
        "receipts": normalized,
        "receipt_count": inventory["metadata_receipt_count"],
        "expected_receipt_count": 1133,
        "terminal_marker": "STAGE10_REMEDIATION_AUDIT_PASS",
        "stdout_sha256": inventory["stdout_sha256"],
    }


def deny_local_reads():
    """Demonstrate reopening never consults vanished job-local files."""

    def audit(event, args):
        if event == "open" and not isinstance(args[0], int):
            path = Path(os.fsdecode(args[0])).absolute()
            if path.is_relative_to("/local"):
                raise RuntimeError("REREVIEW_FORBIDDEN_EPHEMERAL_READ")

    sys.addaudithook(audit)


def durability(root, manifest, repository, check):
    """Inspect only PanFS paths; never stat/open the prior ephemeral path."""
    work = Path(manifest["operational_provenance"]["workspace"])
    provenance = manifest["operational_provenance"]
    check(
        "durable_attempt_scope",
        work.parent == root.parent / "work"
        and work.resolve() == work
        and ops.private(work, True),
    )
    check(
        "split_storage_class",
        provenance["storage_class"] == "SPLIT_LOCAL_TRANSIENT_PANFS_DURABLE",
    )
    local = provenance["transient_workspace"]
    check(
        "transient_operational_path",
        bool(
            re.fullmatch(
                r"/local/1785683/safe_geocoding_pipeline/stage10/generation_[A-Za-z0-9_]+/workspace",
                local,
            )
        ),
    )
    scientific = {k: v for k, v in manifest.items() if k != "operational_provenance"}
    check(
        "no_ephemeral_path_in_scientific_manifest",
        b"/local/" not in canonical(scientific),
    )
    check(
        "all_authoritative_files_panfs",
        all(not (work / x).is_symlink() for x in ("workspace", "workspace/shards"))
        and root.stat().st_dev == work.stat().st_dev,
    )
    transient_files = 0
    private = True
    metadata_local = 0
    for parent, directories, files in os.walk(work, followlinks=False):
        for name in directories:
            private &= ops.private(Path(parent) / name, True)
        for name in files:
            p = Path(parent) / name
            private &= ops.private(p)
            transient_files += int(
                name.endswith((".duckdb", ".wal")) or name in ("index", "payload")
            )
            if name == "checkpoint.json":
                metadata_local += int(b"/local/" in p.read_bytes())
    check("durable_attempt_private_topology", private)
    check("no_transient_database_on_panfs", transient_files == 0)
    check("no_local_checkpoint_dependency", metadata_local == 0)
    check("no_candidate_failure_receipt", not (work / "failure.json").exists())
    reserved = work / "failure.json.partial"
    check(
        "durable_failure_reserve",
        ops.private(reserved) and reserved.read_bytes() == b" " * 65536,
    )
    records = sorted(work.glob("publication-*.json"))
    observed = []
    last_time = -1
    for i, p in enumerate(records):
        record = ops.load(p)
        observed.append(record["phase"])
        check(
            "publication_trace_private_canonical",
            ops.private(p) and p.read_bytes() == canonical(record),
        )
        check(
            "publication_trace_identity",
            record["execution_git_sha"] == NEW_EXE
            and record["publication_key"] == root.name,
        )
        check(
            "publication_trace_monotonic",
            type(record["monotonic_ns"]) is int and record["monotonic_ns"] > last_time,
        )
        last_time = record["monotonic_ns"]
        check(
            "publication_trace_preallocation_order",
            p.name == f"publication-{i:06}.json",
        )
        if record["phase"] in PHASES:
            position = PHASES.index(record["phase"])
            check(
                "publication_trace_state",
                (
                    record["manifest_present"],
                    record["registration_present"],
                    record["seal_present"],
                )
                == (
                    position >= PHASES.index("manifest_fsync"),
                    position >= PHASES.index("registration_fsync"),
                    position >= PHASES.index("reopen"),
                ),
            )
        check(
            "publication_trace_local_operational_only",
            record["local_workspace"] == str(Path(local).parent)
            and record["local_workspace_class"] == "JOB_LOCAL_EPHEMERAL",
        )
    check("complete_p11_phase_sequence", tuple(observed) == PHASES)
    progress = sorted((work / "workspace/progress").glob("progress-*.json"))
    check(
        "durable_terminal_success",
        bool(progress) and ops.load(progress[-1])["event"] == "terminal_success",
    )
    # Candidate's audit is evidence, not our C01 oracle. Bind its durable result
    # and trace; only fixed metadata leaves the controlled reviewer output.
    audit_root = work.parent / (root.name + "_remediation_audit")
    external = root.with_name(root.name + "_remediation_audit.json")
    saved = audit_root / "completed.json"
    portable = (
        repository / "docs/scientific_assets/stage10_remediated_audit_1785683.json"
    )
    check(
        "durable_postpublication_audit_binding",
        ops.private(saved)
        and ops.private(external)
        and file_sha(saved) == file_sha(external) == file_sha(portable),
    )
    audit = ops.load(saved)
    check(
        "durable_audit_candidate_identity",
        audit["execution_git_sha"] == NEW_EXE
        and audit["job_id"] == "1785683"
        and audit["new_manifest_sha256"]
        == file_sha(root / "stage10_query_manifest.json")
        and audit["status"] == "REMEDIATION_AUDIT_PASS",
    )
    check(
        "durable_audit_private_topology",
        ops.topology(
            audit_root,
            {"completed.json", "publication-000000.json", "failure.json.partial"},
        ),
    )
    check(
        "durable_audit_failure_reserve",
        (audit_root / "failure.json.partial").read_bytes() == b" " * 65536,
    )
    check(
        "durable_audit_phase",
        ops.load(audit_root / "publication-000000.json")["phase"]
        == "remediation_audit",
    )
    return {
        "publication_phase_records": len(records),
        "transient_database_files_on_panfs": transient_files,
        "checkpoint_metadata_with_local_path": metadata_local,
        "local_path_reading_prohibited": True,
        "durable_postpublication_audit": True,
    }
