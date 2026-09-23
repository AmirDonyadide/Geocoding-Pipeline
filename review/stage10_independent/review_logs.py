"""Guarded R05 correction only: immutable log scan, no scientific regeneration."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import review
from common import file_sha
from operations import oracle as operations

PRIOR_SHA = "2f9ddf84f389eb9edc26880b091e6cd9b0ece15f"
PRIOR_JOB = "1780706"
PRIOR_EVIDENCE = "4ba802155b27390d8a33b88891abf0cbf19657c6fe9106ab145ae1a4627b0fcf"
COMPLETED = "6ffa7b7335c16ef48356009f527b617a2d01a131459477b4896f79682fa64462"
INPUT_PROGRESS = "f00fbdd5296c1578c88db71bdc473c21b314cff83470162c8a2d8e53b423e0bc"


def legacy_timers(report, completed):
    return all(
        set(report.get(k, {})) <= set(completed["progress"][k])
        and all(
            set(value) <= {"calls", "wall_ns", "cpu_ns"}
            and all(type(n) is int and n >= 0 for n in value.values())
            for value in report.get(k, {}).values()
        )
        for k in ("timings_inclusive", "sql_categories")
    )


def main():
    from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm

    require_goethe_nhr_slurm("stage10-independent-review-log-correction")
    from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as c
    from safe_geocoding_pipeline.preprocessing.stages import s10_query_input as inputs
    from safe_geocoding_pipeline.preprocessing.stages import (
        s10_query_execution as execution,
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s10_query_publication as publication,
    )

    c.require_runtime()
    anchor = inputs.PROJECT_ALIAS.resolve(strict=True)
    candidate = anchor / "integration_stage10" / review.KEY
    review.require(
        Path(c.__file__).resolve().is_relative_to(candidate),
        "candidate_import_exact_checkout",
    )
    out = Path(os.environ["STAGE10_REVIEW_OUTPUT"])
    review.require(
        out.parent == anchor / "derived/controlled/stage10/independent_review"
        and out.resolve() == out,
        "review_output_controlled_scope",
    )
    out.mkdir(mode=0o700)
    review.OUT = out
    review.REPORT.update(
        review_sha=os.environ["STAGE10_REVIEW_SHA"],
        review_job_id=os.environ["SLURM_JOB_ID"],
        review_kind="R05_LOG_ONLY_CORRECTION",
        prior_review_sha=PRIOR_SHA,
        prior_review_job=PRIOR_JOB,
        prior_evidence_sha256=PRIOR_EVIDENCE,
    )
    review.install_write_guard(out)
    with execution.offline_network():
        execution.verify_design(candidate)
        prior_path = (
            out.parent / f"review_{PRIOR_SHA[:12]}_{PRIOR_JOB}" / "complete.json"
        )
        review.require(
            operations.private(prior_path) and file_sha(prior_path) == PRIOR_EVIDENCE,
            "prior_evidence_immutable_binding",
        )
        prior = json.loads(prior_path.read_bytes())
        review.require(
            prior["review_sha"] == PRIOR_SHA
            and prior["review_job_id"] == PRIOR_JOB
            and prior["candidate_executable_sha"] == review.EXE
            and prior["candidate_manifest_sha256"] == review.MANIFEST
            and prior["status"] == "REVIEW_EVIDENCE_COMPLETE"
            and not prior["review_harness_failures"]
            and set(prior["failed_checks"])
            == {
                "operations_stdout_numeric_timers",
                "publication_frozen_input_binding_key",
                "publication_frozen_namespace",
                "q4_missing_visible_parser_geography_exclusion",
            },
            "prior_complete_review_identity",
        )
        root = anchor / "derived/controlled/stage10/development" / review.KEY
        manifest = publication.validate_terminal(root, review.MANIFEST, True)
        review.require(
            all(manifest[k] == v for k, v in review.FROZEN.items()),
            "all_frozen_manifest_bindings",
        )
        work = Path(manifest["operational_provenance"]["workspace"])
        completed_path = work / "completed.json"
        input_path = work / "input_progress/progress-000002.json"
        for path, digest in ((completed_path, COMPLETED), (input_path, INPUT_PROGRESS)):
            review.require(
                operations.private(path) and file_sha(path) == digest,
                "original_receipt_identity",
            )
        completed = json.loads(completed_path.read_bytes())
        input_record = json.loads(input_path.read_bytes())
        review.check(
            "r05_bound_input_scope_demonstration",
            not legacy_timers(input_record, completed)
            and operations.numeric_timers(input_record, completed["progress"]),
        )
        stdout = anchor / "logs/slurm/safe-stage10-development_1774362.out"
        stderr = anchor / "logs/slurm/safe-stage10-development_1774362.err"
        for path in (stdout, stderr):
            review.require(operations.private(path), "original_logs_private")
        initial = [file_sha(stdout), file_sha(stderr)]
        count = operations.audit_logs(
            stdout, stderr, manifest, completed, root.name, review.check
        )
        old_failures = input_only = other_failures = 0
        with stdout.open("rb") as stream:
            for raw in stream:
                record = json.loads(raw)
                if "operational_version" in record and not legacy_timers(
                    record, completed
                ):
                    old_failures += 1
                    attributable = (
                        record["phase"] == "input_validation"
                        and record["timings_inclusive"]
                        == input_record["timings_inclusive"]
                        and record["sql_categories"] == {}
                        and operations.numeric_timers(record, completed["progress"])
                    )
                    input_only += int(attributable)
                    other_failures += int(not attributable)
        review.check(
            "r05_original_failure_reproduced_exactly",
            old_failures == input_only == 1 and other_failures == 0,
        )
        review.check(
            "original_logs_unchanged", initial == [file_sha(stdout), file_sha(stderr)]
        )
        review.check("prior_evidence_unchanged", file_sha(prior_path) == PRIOR_EVIDENCE)
        review.check(
            "candidate_terminal_unchanged",
            publication.validate_terminal(root, review.MANIFEST, True) == manifest,
        )
        review.REPORT["aggregates"]["r05_log_correction"] = {
            "stdout_records": count,
            "legacy_failures": old_failures,
            "input_scope_only_failures": input_only,
            "other_legacy_failures": other_failures,
            "stdout_sha256": initial[0],
            "stderr_sha256": initial[1],
        }
        review.REPORT["completed_phases"] = ["r05_log_correction"]
        review.REPORT["status"] = "REVIEW_LOG_CORRECTION_COMPLETE"
        review.save("complete")


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        review.REPORT["review_harness_failures"].append(
            review.failure(error, "log_correction")
        )
        if review.OUT is not None:
            review.save("harness_failure")
        print("REVIEW_HARNESS_INCOMPLETE", flush=True)
        sys.exit(1)
