"""Guarded immutable Stage 10 DEVELOPMENT review, aggregate output only.

Candidate validators decode established formats and validate accepted input
bindings. Independent oracles determine output correctness. No materialization,
publication/adoption, reference evaluation, workload, or service call occurs.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

from common import canonical, file_sha, identity

EXE = "63f3cd107e69c9ddc14b9b517b0c7ab3d5861e66"
REPORTING = "e7fe4878f585c0283e57edee16f64883b8f8f758"
KEY = "stage10_development_20260921T112356Z_63f3cd107e69"
MANIFEST = "085b05f6201831de6aa908c599bb5541a85cc185a48022d2d93d1e0a9afcc3fa"
FROZEN = {
    "logical_sha256": "70abebdaeee44cf0eae09eb89e4ed68ef087f1596bfa86ea1bef6aef57ceed92",
    "contract_sha256": "be0a865f5217a82497cc3324fa11557df06441ec67e08f1cd2014cbf0d9b246b",
    "profile_sha256": "6c42e00e7550edac184d6f8ba46e421e84f82a2df9b9234049ed3fca59a6798d",
    "schema_bundle_sha256": "659a98157951876b14078d0306b94f8f1e3e151fc92a7352243b3fce1b715070",
    "input_binding_sha256": "531d512f6c177fb5a9d6cd262e66846cdfd5cc66ba818c5aba8030165648878e",
    "science_sha256": "ac375a7160aac5961cb21badadfa9be2df3ac9b49558dd6677825dd6aaf45d1f",
    "budget_policy_sha256": "764f93ec775082efe3e44a1ad81e8b8a8690a4e91da3bc4b34fea0b44dc74af6",
}
REPORT = {
    "review_version": "stage10_independent_review_v1",
    "candidate_executable_sha": EXE,
    "candidate_reporting_sha": REPORTING,
    "candidate_manifest_sha256": MANIFEST,
    "checks": {},
    "check_evaluations": {},
    "failed_evaluations": {},
    "aggregates": {},
    "review_harness_failures": [],
    "completed_phases": [],
}
OUT = None
START = time.monotonic()


def check(name, value):
    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise ValueError("REVIEW_CHECK_NAME_NOT_STATIC")
    REPORT["checks"][name] = REPORT["checks"].get(name, True) and bool(value)
    REPORT["check_evaluations"][name] = REPORT["check_evaluations"].get(name, 0) + 1
    if not value:
        REPORT["failed_evaluations"][name] = (
            REPORT["failed_evaluations"].get(name, 0) + 1
        )


def require(value, code):
    check(code, value)
    if not value:
        raise RuntimeError(code)


def failure(error, phase):
    # Never serialize exception messages, SQL, locals, row keys or values.
    locations = []
    trace = error.__traceback__
    while trace is not None:
        locations.append(
            {
                "file": Path(trace.tb_frame.f_code.co_filename).name,
                "line": trace.tb_lineno,
            }
        )
        trace = trace.tb_next
    return {
        "classification": "REVIEW_HARNESS",
        "phase": phase,
        "exception_type": type(error).__name__,
        "locations": locations,
    }


def save(name):
    if OUT is None:
        return
    REPORT["elapsed_seconds"] = int(time.monotonic() - START)
    REPORT["failed_checks"] = sorted(k for k, v in REPORT["checks"].items() if not v)
    raw = canonical(REPORT)
    fd = os.open(OUT / (name + ".json"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    print("REVIEW_PHASE_COMPLETE " + name, flush=True)


def phase(name, action):
    try:
        REPORT["aggregates"][name] = action()
        REPORT["completed_phases"].append(name)
        success = True
    except Exception as error:
        REPORT["review_harness_failures"].append(failure(error, name))
        success = False
    save(name)
    return success


def registration_body(publication_key, manifest, manifest_sha):
    """Recompute the implemented adapter independently; frozen names checked apart."""
    inventory = sorted(
        [
            {
                "path": item["relative_path"],
                "bytes": item["bytes"],
                "sha256": item["sha256"],
            }
            for item in [
                *[
                    item
                    for relation in manifest["relations"]
                    for item in relation["files"]
                ],
                *manifest["metadata_inventory"],
            ]
        ],
        key=lambda item: item["path"].encode("utf-8"),
    )
    binding = {
        "namespace": manifest["kind"],
        "publication_key": publication_key,
        "manifest_sha256": manifest_sha,
        **{
            key: manifest[key]
            for key in (
                "logical_sha256",
                "contract_sha256",
                "profile_sha256",
                "schema_bundle_sha256",
            )
        },
        "executable_sha": manifest["operational_provenance"]["execution_git_sha"],
        "stage10_input_sha256": manifest["input_binding_sha256"],
        "stage10_science_sha256": manifest["science_sha256"],
        "stage10_budget_sha256": manifest["budget_policy_sha256"],
        "runtime_build_lock_sha256": manifest["runtime"]["lock_sha256"],
        "inventory_sha256": hashlib.sha256(canonical(inventory)).hexdigest(),
    }
    return {"protocol": "exclusive_run_commit_seal_v2_candidate", "bindings": binding}


def install_write_guard(out, allowed_processes=()):
    """Block Python-mediated mutations outside new review output, including inputs."""

    def writable(path):
        if isinstance(path, int):
            return  # Only file objects opened before/through this guard have FDs.
        if path is None:
            raise RuntimeError("REVIEW_WRITE_PATH_MISSING")
        selected = Path(os.fsdecode(path)).absolute()
        if (
            not selected.is_relative_to(out)
            or selected.resolve().is_relative_to(out) is False
        ):
            raise RuntimeError("REVIEW_IMMUTABLE_INPUT_WRITE_BLOCKED")

    def audit(event, args):
        if event == "open":
            path, mode, flags = args
            if (isinstance(mode, str) and any(c in mode for c in "wax+")) or flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
            ):
                writable(path)
        elif event in (
            "os.mkdir",
            "os.remove",
            "os.rmdir",
            "os.chmod",
            "os.chown",
            "os.truncate",
            "os.utime",
        ):
            writable(args[0])
        elif event in ("os.rename", "os.link", "os.symlink"):
            writable(args[0])
            writable(args[1])
        elif event == "subprocess.Popen" and tuple(args[1]) in allowed_processes:
            pass  # Exact public ELF inspection commands, before protected inputs.
        elif event in (
            "subprocess.Popen",
            "os.system",
            "socket.connect",
            "socket.getaddrinfo",
        ):
            raise RuntimeError("REVIEW_PROCESS_OR_NETWORK_BLOCKED")

    sys.addaudithook(audit)


def main():
    global OUT
    from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm

    require_goethe_nhr_slurm("stage10-independent-development-review")
    from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as c
    from safe_geocoding_pipeline.preprocessing.stages import s10_query_input as inputs
    from safe_geocoding_pipeline.preprocessing.stages import (
        s10_query_execution as execution,
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s10_query_publication as publication,
    )
    from safe_geocoding_pipeline.preprocessing.stages import s10_query_io as io
    from safe_geocoding_pipeline.preprocessing.stages import (
        s09_reference_io as generic_io,
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s09_reference_input as accepted8,
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s09_reference_publication as publication9,
    )
    import relations
    import structured
    import lineage
    from family_safety import oracle as family
    from operations import oracle as operations

    c.require_runtime()
    anchor = inputs.PROJECT_ALIAS.resolve(strict=True)
    repository = Path(os.environ["STAGE10_REVIEW_CHECKOUT"])
    candidate = anchor / "integration_stage10" / KEY
    require(
        Path(c.__file__).resolve().is_relative_to(candidate),
        "candidate_import_exact_checkout",
    )
    root = anchor / "derived/controlled/stage10/development" / KEY
    out = Path(os.environ["STAGE10_REVIEW_OUTPUT"])
    require(
        out.parent == anchor / "derived/controlled/stage10/independent_review"
        and out.resolve() == out,
        "review_output_controlled_scope",
    )
    out.mkdir(mode=0o700)
    OUT = out
    (out / "tmp").mkdir(mode=0o700)
    os.environ["TMPDIR"] = str(out / "tmp")
    import tempfile

    tempfile.tempdir = str(out / "tmp")
    REPORT["review_sha"] = os.environ["STAGE10_REVIEW_SHA"]
    REPORT["review_job_id"] = os.environ["SLURM_JOB_ID"]
    import shutil
    from safe_geocoding_pipeline.preprocessing.stages import s10_runtime_lock

    public_lock = json.loads(
        (
            candidate
            / "docs/scientific_assets/stage10_runtime_goethe_v1/runtime_build_lock.json"
        ).read_bytes()
    )
    bridge = next(
        a["relative_path"] for a in public_lock["artifacts"] if a["role"] == "BRIDGE"
    )
    allowed_processes = {
        (shutil.which("ldd"), str(path))
        for path in (
            anchor / execution.RUNTIME_RELATIVE / bridge,
            *s10_runtime_lock.python_assets().values(),
        )
        if path.suffix != ".a"
    }
    install_write_guard(out, allowed_processes)
    with execution.offline_network():
        execution.verify_design(candidate)
        manifest = publication.validate_terminal(root, MANIFEST, True)
        require(
            all(manifest[k] == v for k, v in FROZEN.items()),
            "all_frozen_manifest_bindings",
        )
        require(
            manifest["operational_provenance"]["execution_git_sha"] == EXE
            and manifest["operational_provenance"]["job_id"] == "1774362",
            "candidate_executable_job_binding",
        )
        require(
            manifest["split"] == "DEVELOPMENT"
            and manifest["input_binding"]["split"] == "DEVELOPMENT"
            and manifest["input_binding"]["benchmark_sha256"]
            == accepted8.BENCHMARK_SHA256,
            "benchmark_development_population_binding",
        )
        require(
            manifest["input_binding"]["stage08"]["manifest_sha256"]
            == accepted8.STAGE08_MANIFEST_SHA256
            and manifest["input_binding"]["stage09"]["manifest_sha256"]
            == inputs.STAGE09_MANIFEST
            and manifest["input_binding"]["stage06_row_map"]["manifest_sha256"]
            == inputs.STAGE06_MANIFEST,
            "accepted_upstream_manifest_bindings",
        )
        require(
            file_sha(
                repository
                / "docs/scientific_assets/stage10_development_manifest_1774362.json"
            )
            == MANIFEST,
            "reporting_manifest_exact",
        )
        require(
            manifest["runtime"]["semantic_fingerprint"] == execution.SEMANTIC_RUNTIME
            and manifest["runtime"]["lock_sha256"] == execution.RUNTIME_LOCK_SHA,
            "frozen_runtime_binding",
        )
        execution.publication_environment(root, anchor / execution.STAGE09_RELATIVE)
        runtime = execution.runtime_ready(
            anchor / execution.RUNTIME_RELATIVE, candidate
        )
        allowed_processes.clear()
        require(
            runtime.asset_binding.hex() == manifest["runtime"]["asset_binding"],
            "runtime_asset_binding",
        )
        require(
            (
                public_lock["icu_version"],
                public_lock["unicode_version"],
                public_lock["cldr_version"],
            )
            == ("77.1", "16.0.0", "47")
            and public_lock["specification_sha256"]
            == manifest["runtime"]["specification_sha256"]
            == "5d0a8f6906a8d93ac38d73a862d69e31e2e9e454e8d0518e0c13f9792256a916",
            "frozen_transliteration_versions_and_specification",
        )
        require(
            c.contract_fingerprint().hex() == FROZEN["contract_sha256"]
            and c.schema_bundle_fingerprint().hex() == FROZEN["schema_bundle_sha256"]
            and c.science_fingerprint(runtime.asset_binding).hex()
            == FROZEN["science_sha256"]
            and io.profile_fingerprint(bytes.fromhex(FROZEN["science_sha256"])).hex()
            == FROZEN["profile_sha256"],
            "code_contract_schema_profile_binding",
        )
        save("preflight")
        try:
            # Pins + physical inventory/accepted logical checks; no generation.
            accepted = inputs.consume_inputs(
                anchor / execution.STAGE08_RELATIVE,
                anchor / execution.STAGE09_RELATIVE,
                Path(manifest["input_binding"]["stage06_row_map"]["approved_anchor"]),
            )
            require(
                accepted.binding == manifest["input_binding"]
                and accepted.identifier.hex() == FROZEN["input_binding_sha256"],
                "full_accepted_input_binding",
            )
            require(
                identity("stage10-input:v1", canonical(manifest["input_binding"])).hex()
                == FROZEN["input_binding_sha256"],
                "independent_input_encoding",
            )
            upstream = identity(
                "stage10-context-input:v1",
                *[
                    bytes.fromhex(manifest["input_binding"][k]["manifest_sha256"])
                    for k in ("stage08", "stage06_row_map", "stage09")
                ],
            )
            require(
                upstream == accepted.context_binding,
                "independent_context_snapshot_binding",
            )
            for item in publication.inventory(manifest):
                path = operations.confined(root, item["path"])
                require(
                    operations.private(path)
                    and path.stat().st_size == item["bytes"]
                    and file_sha(path) == item["sha256"],
                    "immutable_artifact_physical_inventory",
                )
            require(
                operations.topology(
                    root,
                    {
                        "stage10_query_manifest.json",
                        "_SUCCESS.json",
                        "_COMMITTED",
                        *[x["path"] for x in publication.inventory(manifest)],
                    },
                ),
                "publication_exact_private_topology",
            )
            registration = json.loads((root / "_SUCCESS.json").read_bytes())
            # Frozen publication interface, independent of executable constants.
            # Record ordinary contract defects and continue the scientific audit.
            check(
                "publication_frozen_namespace",
                registration["bindings"]["namespace"]
                == "STAGE10_DEVELOPMENT_QUERY_PLAN",
            )
            check(
                "publication_frozen_input_binding_key",
                registration["bindings"].get("stage10_input_binding_sha256")
                == FROZEN["input_binding_sha256"],
            )
            body = registration_body(root.name, manifest, MANIFEST)
            check(
                "registration_independent_commit_hash",
                registration
                == {
                    **body,
                    "commit_record_id": hashlib.sha256(
                        b"SAFE:publication-commit:v2\0" + canonical(body)
                    ).hexdigest(),
                },
            )
            # Same source-tree primitive functions, no publication writer invoked.
            check(
                "accepted_stage9_publication_primitives",
                publication.create_seal is publication9.create_seal,
            )
            require(
                (root / "_COMMITTED").read_bytes() == b"", "exclusive_empty_commit_seal"
            )
            summary_sha = file_sha(root / "query_generation_summary.json")
            dataset = identity(
                "stage10-dataset:v1",
                bytes.fromhex(FROZEN["input_binding_sha256"]),
                bytes.fromhex(FROZEN["science_sha256"]),
                bytes.fromhex(FROZEN["budget_policy_sha256"]),
                bytes.fromhex(FROZEN["profile_sha256"]),
                bytes.fromhex(FROZEN["schema_bundle_sha256"]),
                tuple(
                    (r["name"], bytes.fromhex(r["logical_sha256"]), r["row_count"])
                    for r in manifest["relations"]
                ),
                bytes.fromhex(summary_sha),
            )
            check(
                "independent_dataset_fingerprint",
                dataset.hex() == FROZEN["logical_sha256"],
            )
            check(
                "unselected_operating_budget",
                manifest["operating_budget"] is None
                and manifest["plan_mode"] == "ALL_ELIGIBLE_CATALOG",
            )
            save("bindings")
            phase(
                "logical_identities",
                lambda: relations.logical_and_identifiers(
                    root, manifest, upstream, check
                ),
            )
            with generic_io.bounded_connection(
                out / "spill", database=out / "review.duckdb", memory="8GB", threads=4
            ) as db:
                accepted.register_views(db)
                for rec in manifest["relations"]:
                    db.execute(
                        "CREATE VIEW "
                        + rec["name"]
                        + " AS SELECT * FROM "
                        + io.parquet_sql(
                            [
                                operations.confined(root, f["relative_path"])
                                for f in rec["files"]
                            ]
                        )
                    )
                context_ok = phase(
                    "contexts", lambda: relations.derive_contexts(db, upstream, check)
                )
                if context_ok:
                    phase("relational", lambda: relations.relational(db, check))
                    policy_ok = phase("structured", lambda: structured.run(db, check))
                    if policy_ok:
                        expected = {
                            "country_unavailable_contexts": 1668,
                            "country_available_contexts": 68079,
                            "q4_expected_eligible": 33556,
                            "q4_expected_postcode_included": 6751,
                            "q4_expected_postcode_contradiction_omissions": 17529,
                            "q4_q04_negative_contexts": 17527,
                            "q4_q08_negative_contexts": 2,
                        }
                        for name, value in expected.items():
                            check(
                                "reported_" + name,
                                REPORT["aggregates"]["structured"][name] == value,
                            )
                        phase(
                            "baselines_q3",
                            lambda: relations.baselines_and_boundaries(db, check),
                        )
                        family_ok = phase(
                            "family_safety", lambda: family.run(db, runtime, check)
                        )
                        if family_ok:
                            for name, value in {
                                "contexts": 69747,
                                "q5_eligible": 50,
                                "q6_eligible": 2348,
                                "q6_greek": 157,
                                "q6_cyrillic": 2191,
                                "q6_attempted": 2349,
                                "q6_unsupported_output": 1,
                            }.items():
                                check(
                                    "reported_" + name,
                                    REPORT["aggregates"]["family_safety"][name]
                                    == value,
                                )
                    phase("lineage", lambda: lineage.run(db, check))
                    inventory = json.loads(
                        (
                            repository
                            / "docs/scientific_assets/stage10_development_review_inventory_1774362.json"
                        ).read_bytes()
                    )
                    for key, suffix in (
                        ("_review_stdout_path", "out"),
                        ("_review_stderr_path", "err"),
                    ):
                        inventory[key] = str(
                            anchor
                            / "logs/slurm"
                            / f"safe-stage10-development_1774362.{suffix}"
                        )
                    phase(
                        "operations",
                        lambda: operations.run(db, root, manifest, inventory, check),
                    )
            # Reopen and rehash immutable candidate after all review reads.
            require(
                publication.validate_terminal(root, MANIFEST, True) == manifest,
                "final_terminal_reopen",
            )
            for item in publication.inventory(manifest):
                require(
                    file_sha(root / item["path"]) == item["sha256"],
                    "final_candidate_bytes_unchanged",
                )
            REPORT["scope"] = {
                "holdout_accessed": False,
                "production_accessed": False,
                "pelias_accessed": False,
                "candidate_modified": False,
                "stage11_started": False,
                "owner_acceptance": False,
            }
            REPORT["status"] = (
                "REVIEW_EVIDENCE_COMPLETE"
                if not REPORT["review_harness_failures"]
                else "REVIEW_HARNESS_INCOMPLETE"
            )
            save("complete")
        finally:
            runtime.close()


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        REPORT["review_harness_failures"].append(failure(error, "entry_or_binding"))
        if OUT is not None:
            save("harness_failure")
        print("REVIEW_HARNESS_INCOMPLETE", flush=True)
        sys.exit(1)
