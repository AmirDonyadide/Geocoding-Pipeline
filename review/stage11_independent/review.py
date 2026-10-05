"""Guarded read-only Stage 11 review. Only static checks and aggregates exported."""

import hashlib
import json
import os
import platform
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import duckdb
import pyarrow
import pyarrow.parquet as pq

import oracle as o
import operations as ops
import reconcile as r

EXE = "8dce0e1078e123748ae692fa824200fc3e646aa4"
REPORTING = "d49e9340ef3ae9cb3caaec65d5ccf0c490ecf366"
BASE = "125b3684a000ea79523f77049ae1a290b0da8109"
DESIGN = "ac96b033e2ba7201fbb99ea38cd363d13410c7c4"
PROJECT = Path("/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline")
KEY = "stage11_development_20261004T095201Z_8dce0e1078e1"
ARTIFACT = PROJECT / "derived/controlled/stage11/development" / KEY
ATTEMPT = ARTIFACT.parent / (KEY + "_attempt")
UPSTREAM = (
    PROJECT
    / "derived/controlled/stage10/development/stage10_development_20260928T081247Z_cf9e0fe4c12e"
)
MANIFEST = "9dc8e3853cc474c331d08740981b11d0b8128a7b11fd36d9f978cb883414b6cc"
UPSTREAM_MANIFEST = "558298d7260199cc24f994d7480def9ad268aca057347f86ca41fad675a5a860"
HYPOTHESIS = "c61ba899dbe4f714e2879995261b7d3a943e3b830ca69b4656e2d286230982e1"
ASSETS = {
    "contract_sha256": "e049305cfc100a7a84de01d395b4eceae5195e0730f50c91923cd5970c05885c",
    "profile_sha256": "e25952c294ce486eff4969eef0ff709d10de89b6cdaf7072140a272e49a940a4",
    "schema_bundle_sha256": "a5c918291cd29e1824dd54e6b4d43bd7090e2492a06be408592a1a36f2f4b528",
}
INPUT = "083830b8a8e696668f5956afc6405074dbec84e5bdb150994c2acb67d2897edf"
LOGICAL = "e110ff3eb2ad01ac6bf298c48f6c489b3b79bc067f28b41deab8d1bc1e46f337"
RELATION_HASHES = [
    "01b1c6f243e12c407d9df86b77d3068be46a11f3511e4d77170db39f73e83f5e",
    "ea23792566398856cba1372c914cec5c70e00412c80dac7f5fec259d663dfcc3",
]
DOCS = sorted(
    "docs/stages/" + n
    for n in [
        "STAGE11_SEMANTIC_REQUEST_DEDUPLICATION.md",
        "STAGE11_DATA_CONTRACT.md",
        "STAGE11_DEVELOPMENT_EVALUATION.md",
        "STAGE11_DESIGN_REVIEW.md",
    ]
)
REPORT = {
    "review_version": "stage11_independent_review_v1",
    "candidate_implementation_sha": EXE,
    "candidate_reporting_sha": REPORTING,
    "candidate_manifest_sha256": MANIFEST,
    "checks": {},
    "check_evaluations": {},
    "failed_evaluations": {},
    "completed_phases": [],
    "review_harness_failures": [],
    "aggregates": {},
}
DENY_ALL_LOCAL = False


def check(name, passed):
    if re.fullmatch("[A-Za-z0-9_]+", name) is None:
        raise ValueError("NONSTATIC_CHECK_NAME")
    REPORT["checks"][name] = REPORT["checks"].get(name, True) and bool(passed)
    REPORT["check_evaluations"][name] = REPORT["check_evaluations"].get(name, 0) + 1
    if not passed:
        REPORT["failed_evaluations"][name] = (
            REPORT["failed_evaluations"].get(name, 0) + 1
        )


def require(name, condition):
    check(name, condition)
    if not condition:
        raise ValueError("REVIEW_TRUST_BOUNDARY")


def git(repo, *args):
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, check=True
    )
    return result.stdout


def portable_failure(error, phase):
    locations = []
    tb = error.__traceback__
    while tb is not None:
        locations.append(
            {"file": Path(tb.tb_frame.f_code.co_filename).name, "line": tb.tb_lineno}
        )
        tb = tb.tb_next
    # No arbitrary exception message, class name, traceback text, locals or SQL.
    return {
        "phase": phase,
        "classification": "REVIEW_HARNESS_UNCLASSIFIED_PENDING_REVIEW",
        "locations": locations,
    }


def audit(event, args):
    if event.startswith("socket.") and event not in ("socket.__new__",):
        raise PermissionError("REVIEW_NETWORK_PROHIBITED")
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        path = os.fsdecode(args[0])
        absolute = os.path.abspath(path)
        if (
            absolute == "/local/1788751"
            or absolute.startswith("/local/1788751/")
            or (DENY_ALL_LOCAL and absolute.startswith("/local/"))
        ):
            raise PermissionError("REVIEW_LOCAL_PROHIBITED")
        if "/derived/controlled/" in absolute:
            p = Path(absolute)
            roots = (
                ARTIFACT,
                ATTEMPT,
                UPSTREAM,
                Path(os.environ["STAGE11_REVIEW_OUTPUT"]),
            )
            if not any(p.is_relative_to(root) for root in roots):
                raise PermissionError("REVIEW_INPUT_SCOPE")
            mode, flags = args[1], args[2]
            writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int)
                and flags
                & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            )
            if writing and not p.is_relative_to(roots[-1]):
                raise PermissionError("REVIEW_CANDIDATE_WRITE")
    if event in (
        "os.remove",
        "os.rename",
        "os.rmdir",
        "os.chmod",
        "os.mkdir",
        "os.link",
        "os.symlink",
        "os.truncate",
    ):
        for arg in (
            args[:2] if event in ("os.rename", "os.link", "os.symlink") else args[:1]
        ):
            if isinstance(arg, (str, bytes, os.PathLike)):
                p = Path(os.path.abspath(os.fsdecode(arg)))
                if any(
                    p.is_relative_to(root) for root in (ARTIFACT, ATTEMPT, UPSTREAM)
                ):
                    raise PermissionError("REVIEW_CANDIDATE_MUTATION")


def offline(*args, **kwargs):
    raise PermissionError("REVIEW_NETWORK_PROHIBITED")


def provenance(candidate, review):
    require(
        "A_exact_candidate_checkout",
        git(candidate, "rev-parse", "HEAD").strip().decode() == EXE
        and not git(candidate, "status", "--porcelain").strip(),
    )
    require(
        "A_exact_review_checkout",
        git(review, "rev-parse", "HEAD").strip().decode()
        == os.environ["STAGE11_REVIEW_SHA"]
        and not git(review, "status", "--porcelain").strip(),
    )
    require(
        "A_frozen_tag",
        git(review, "rev-parse", "stage11-semantic-request-deduplication-design-v1^{}")
        .strip()
        .decode()
        == BASE,
    )
    for left, right in ((DESIGN, BASE), (BASE, EXE), (EXE, REPORTING), (BASE, "HEAD")):
        git(review, "merge-base", "--is-ancestor", left, right)
    check("A_frozen_ancestry", True)
    changed = git(review, "diff", "--name-only", BASE, "HEAD").decode().splitlines()
    require(
        "A_review_branch_isolation",
        all(p.startswith("review/stage11_independent/") for p in changed),
    )
    documents = []
    for path in DOCS:
        frozen = git(review, "show", BASE + ":" + path)
        require(
            "A_design_exact_bytes",
            (candidate / path).read_bytes()
            == frozen
            == git(review, "show", DESIGN + ":" + path),
        )
        documents.append({"path": path, "sha256": hashlib.sha256(frozen).hexdigest()})
    contract = {
        "contract_version": o.CONSTANTS["contract_version"],
        "design_documents": documents,
    }
    contract_sha = hashlib.sha256(o.canonical(contract)).hexdigest()
    require("A_contract_hash", contract_sha == ASSETS["contract_sha256"])
    profile = {
        "profile_version": o.CONSTANTS["semantic_policy_version"],
        "contract_sha256": contract_sha,
        "input_policy": "ALL_ACCEPTED_HYPOTHESES",
        "stage10_policy_slot": "SAFE_PELIAS_COMMON_RETRIEVAL_V1",
        "core_constants": o.CONSTANTS,
    }
    require(
        "A_profile_hash",
        hashlib.sha256(o.canonical(profile)).hexdigest() == ASSETS["profile_sha256"],
    )
    asset_dir = candidate / "docs/scientific_assets"
    for name, value in (
        (o.CONSTANTS["contract_version"], contract),
        (o.CONSTANTS["semantic_policy_version"], profile),
    ):
        require(
            "A_machine_asset_exact",
            (asset_dir / (name + ".json")).read_bytes() == o.canonical(value),
        )
    descriptor_hashes = []
    for stem in (
        "semantic_request",
        "hypothesis_request_map",
        "semantic_request_summary",
    ):
        path = asset_dir / ("stage11_" + stem + "_descriptor_v1.json")
        descriptor = ops.read_json(path)
        descriptor_hashes.append(bytes.fromhex(ops.file_sha(path)))
        if stem != "semantic_request_summary":
            require(
                "C_descriptor_field_names",
                [f["name"] for f in descriptor["fields"]] == o.schema(stem).names,
            )
            require("C_descriptor_constants", descriptor["constants"] == o.CONSTANTS)
            require(
                "C_descriptor_modes",
                descriptor["endpoint_mode_pairs"]
                == [
                    ["/v1/search", "FULL_TEXT"],
                    ["/v1/search/structured", "STRUCTURED"],
                ],
            )
            if stem == "semantic_request":
                require(
                    "C_descriptor_core_order_types_nullability",
                    descriptor["fields"][1]["fields"]
                    == [
                        {"name": k, "type": "large_string", "nullable": k in o.PAYLOAD}
                        for k in o.FIELDS
                    ],
                )
    require(
        "A_schema_bundle_hash",
        o.identity("stage11-schema-bundle:v1", *descriptor_hashes).hex()
        == ASSETS["schema_bundle_sha256"],
    )
    require(
        "A_reporting_introduction",
        git(
            review,
            "log",
            REPORTING,
            "--diff-filter=A",
            "--format=%H",
            "--",
            "reports/development/stage11.md",
        )
        .strip()
        .decode()
        == REPORTING,
    )
    require(
        "A_reporting_code_unchanged",
        not git(
            review, "diff", EXE, REPORTING, "--", "src", "tests", "cluster"
        ).strip(),
    )


def main():
    global DENY_ALL_LOCAL
    from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm

    require_goethe_nhr_slurm(
        "stage11-independent-review"
    )  # Before any protected stat/read.
    from safe_geocoding_pipeline.preprocessing.stages import s10_query_io as s10io

    review = Path(__file__).resolve().parents[2]
    candidate = Path(os.environ["STAGE11_CANDIDATE_CHECKOUT"])
    out = Path(os.environ["STAGE11_REVIEW_OUTPUT"])
    require(
        "U_review_output_scope",
        out.parent == PROJECT / "derived/controlled/stage11/independent_review"
        and not out.exists(),
    )
    out.mkdir(mode=0o700)
    os.umask(0o077)
    sys.addaudithook(audit)
    started = time.monotonic()
    REPORT.update(
        review_sha=os.environ["STAGE11_REVIEW_SHA"], job_id=os.environ["SLURM_JOB_ID"]
    )
    phase = "provenance"
    db = None
    try:
        provenance(candidate, review)
        require(
            "A_exact_review_runtime",
            (platform.python_version(), pyarrow.__version__, duckdb.__version__)
            == ("3.14.3", "25.0.0", "1.5.5"),
        )
        # No local workspace from job 1788751 may be probed, even for existence.
        manifest_path = ARTIFACT / "stage11_semantic_request_manifest.json"
        require("A_candidate_manifest", ops.file_sha(manifest_path) == MANIFEST)
        require(
            "A_upstream_manifest",
            ops.file_sha(UPSTREAM / "stage10_query_manifest.json") == UPSTREAM_MANIFEST,
        )
        manifest = ops.read_json(manifest_path)
        upstream = ops.read_json(UPSTREAM / "stage10_query_manifest.json")
        require(
            "A_candidate_reporting_manifest",
            manifest_path.read_bytes()
            == git(
                review,
                "show",
                REPORTING
                + ":docs/scientific_assets/stage11_development_manifest_1788751.json",
            ),
        )
        require(
            "A_input_binding_hash",
            o.identity("stage11-input:v1", o.canonical(manifest["input_binding"])).hex()
            == manifest["input_binding_sha256"]
            == INPUT,
        )
        require(
            "A_binding_asset",
            manifest["input_binding"]
            == ops.read_json(
                candidate / "docs/scientific_assets/stage11_input_binding_v1.json"
            ),
        )
        require(
            "A_frozen_asset_bindings", all(manifest[k] == v for k, v in ASSETS.items())
        )
        require(
            "A_bound_upstream_inventory",
            manifest["input_binding"]["stage10"]["relations"] == upstream["relations"]
            and manifest["input_binding"]["stage10"]["transitive_input_binding"]
            == upstream["input_binding"],
        )
        require(
            "A_development_population",
            manifest["split"] == upstream["split"] == "DEVELOPMENT"
            and upstream["plan_mode"] == "ALL_ELIGIBLE_CATALOG"
            and upstream["operating_budget"] is None,
        )
        require(
            "A_executable_manifest_binding",
            manifest["operational_provenance"]["execution_git_sha"] == EXE
            and manifest["design_sha"] == DESIGN,
        )
        cb = manifest["operational_provenance"]["checkpoint_binding"]
        require(
            "Q_exact_checkpoint_binding",
            cb
            == {
                "execution_git_sha": EXE,
                "input_binding_sha256": INPUT,
                **ASSETS,
                "design_sha": DESIGN,
                "encoding_version": o.CONSTANTS["encoding_version"],
                "runtime": {"python": "3.14.3", "pyarrow": "25.0.0", "duckdb": "1.5.5"},
                "input_unit_rows": 8192,
                "partition_bytes": 1,
                "input_order": "HYPOTHESIS_ID_UNSIGNED_ASCENDING",
            },
        )
        REPORT["completed_phases"].append(phase)
        phase = "durable_inventory"
        before_artifact = ops.tree_inventory(ARTIFACT, check, "R_U_artifact")
        before_attempt = ops.tree_inventory(ATTEMPT, check, "Q_U_attempt")
        listed = {
            "stage11_semantic_request_manifest.json",
            "_SUCCESS.json",
            "_COMMITTED",
            *(
                f["relative_path"]
                for rel in manifest["relations"]
                for f in rel["files"]
            ),
            *(f["relative_path"] for f in manifest["metadata_inventory"]),
        }
        require("R_exact_artifact_inventory", set(before_artifact) == listed)
        # Review scratch is separate from all candidate and checkpoint objects.
        scratch = (
            Path("/local") / os.environ["SLURM_JOB_ID"] / "stage11-independent-review"
        )
        scratch.mkdir(mode=0o700)
        db = duckdb.connect(str(scratch / "review.duckdb"))
        db.execute("SET memory_limit='2GB'")
        db.execute("SET threads=2")
        db.execute("SET temp_directory='" + str(scratch / "spill") + "'")
        db.execute("SET autoinstall_known_extensions=false")
        db.execute("SET autoload_known_extensions=false")
        db.execute("SET disabled_filesystems='HTTPFileSystem'")
        decision_columns = "query_context_id,hypothesis_id,family,eligibility_state,membership_state,stable_source_row_id_v1,stage08_representation,stage06_exact_candidate_id"
        for rel, view in zip(upstream["relations"], ("h", "d"), strict=True):
            paths = ops.files(UPSTREAM, rel["files"], check, "A_upstream")
            require(
                "A_upstream_physical_valid",
                REPORT["checks"]["A_upstream_physical_hash"],
            )
            for path in paths:
                require(
                    "A_upstream_schema",
                    pq.read_schema(path).equals(
                        s10io.output_schema(rel["name"]), check_metadata=True
                    ),
                )
            projection = "*" if view == "h" else decision_columns
            db.execute(
                f"CREATE VIEW {view} AS SELECT {projection} FROM {ops.parquet_sql(paths)}"
            )
        ops.files(
            UPSTREAM, upstream["metadata_inventory"], check, "A_upstream_metadata"
        )
        for rel, view in zip(manifest["relations"], ("s", "m"), strict=True):
            paths = ops.files(ARTIFACT, rel["files"], check, "C_candidate")
            for path in paths:
                check(
                    "C_exact_arrow_schema",
                    pq.read_schema(path).equals(
                        o.schema(rel["name"]), check_metadata=False
                    ),
                )
                descriptor = (
                    candidate
                    / "docs/scientific_assets"
                    / ("stage11_" + rel["name"] + "_descriptor_v1.json")
                ).read_bytes()
                check(
                    "C_exact_schema_metadata",
                    pq.read_schema(path).metadata
                    == {b"stage11_descriptor": descriptor, b"protected": b"true"},
                )
            db.execute(f"CREATE VIEW {view} AS SELECT * FROM {ops.parquet_sql(paths)}")
        REPORT["completed_phases"].append(phase)
        phase = "scientific_relations"
        hypothesis = r.hypothesis_digest(
            db,
            s10io.output_schema("query_hypothesis"),
            upstream["relations"][0]["schema_sha256"],
            142677,
        )
        require("A_B_independent_hypothesis_fingerprint", hypothesis == HYPOTHESIS)
        summary = r.scientific(db, check)
        REPORT["aggregates"]["independent_summary"] = summary
        check(
            "B_C_expected_counts",
            (
                summary["input_population"]["hypotheses"],
                summary["request_counts"]["unique_requests"],
                summary["request_counts"]["map_rows"],
            )
            == (142677, 105805, 142677),
        )
        observed_summary = ops.read_json(ARTIFACT / "semantic_request_summary.json")
        check("M_N_O_complete_independent_summary", summary == observed_summary)
        check("M_rounded_reduction", f"{100 * 36872 / 142677:.6f}" == "25.842988")
        fingerprints = []
        for rel, view, pk in zip(
            manifest["relations"],
            ("s", "m"),
            ("query_semantic_id", "hypothesis_id"),
            strict=True,
        ):
            actual = o.relation_hash(
                rel["name"],
                rel["schema_sha256"],
                rel["row_count"],
                r.rows(db, f"SELECT * FROM {view} ORDER BY {pk}"),
                validate=False,  # Earlier full scan records defects; keep reviewing.
            )
            fingerprints.append(actual)
            check("P_independent_relation_hash", actual == rel["logical_sha256"])
        check("P_expected_relation_hashes", fingerprints == RELATION_HASHES)
        summary_sha = hashlib.sha256(o.canonical(summary)).digest()
        dataset = o.identity(
            "stage11-dataset:v1",
            bytes.fromhex(INPUT),
            *(
                bytes.fromhex(ASSETS[k])
                for k in ("contract_sha256", "profile_sha256", "schema_bundle_sha256")
            ),
            o.CONSTANTS["encoding_version"],
            bytes.fromhex(fingerprints[0]),
            105805,
            bytes.fromhex(fingerprints[1]),
            142677,
            summary_sha,
        ).hex()
        check(
            "P_independent_dataset_hash",
            dataset == manifest["logical_sha256"] == LOGICAL,
        )
        REPORT["aggregates"]["fingerprints"] = {
            "query_hypothesis": hypothesis,
            "semantic_request": fingerprints[0],
            "hypothesis_request_map": fingerprints[1],
            "logical_dataset": dataset,
        }
        REPORT["completed_phases"].append(phase)
        phase = "checkpoints"
        REPORT["aggregates"]["checkpoints"] = ops.checkpoints(
            ATTEMPT / "checkpoints", manifest, db, check
        )
        REPORT["completed_phases"].append(phase)
        phase = "publication"
        reg = ops.registration(ARTIFACT, manifest, MANIFEST, check)
        check(
            "R_registration_hash",
            ops.file_sha(ARTIFACT / "_SUCCESS.json")
            == "830e7632c4079cde548e4a3c7886749d39332fbb54c748bc0f54cd0bd5069964",
        )
        check(
            "R_registration_record_id",
            reg["commit_record_id"]
            == "62e042caa91e6229bcf422b2c04f5fa78d99356be9cee390d40ce81d0f02d01e",
        )
        phases = [ops.read_json(p) for p in sorted(ATTEMPT.glob("publication-*.json"))]
        expected_phases = "initialization input_validation reservation build manifest manifest_fsync initial_validation registration_build registration_write registration_fsync prepared_validation seal_validation seal_create reopen final_check".split()
        check(
            "R_publication_order",
            [p["phase"] for p in phases] == expected_phases
            and all(
                a["monotonic_ns"] < b["monotonic_ns"]
                for a, b in zip(phases, phases[1:])
            ),
        )
        for p in phases:
            check(
                "R_phase_executable",
                p["execution_git_sha"] == EXE and p["publication_key"] == KEY,
            )
            check(
                "R_no_premature_seal",
                p["seal_present"] == (p["phase"] in ("reopen", "final_check")),
            )
        check("T_no_candidate_failure", not (ATTEMPT / "failure.json").exists())
        complete = ops.read_json(ATTEMPT / "completed.json")
        check(
            "U_stdout_sanitized_exact",
            (PROJECT / "logs/slurm/safe-stage11-development_1788751.out").read_bytes()
            == o.canonical(complete),
        )
        check(
            "U_stderr_empty",
            (PROJECT / "logs/slurm/safe-stage11-development_1788751.err").stat().st_size
            == 0,
        )
        check(
            "U_completion_matches_report",
            complete
            == json.loads(
                git(
                    review,
                    "show",
                    REPORTING
                    + ":docs/scientific_assets/stage11_development_evidence_1788751.json",
                )
            )["execution"],
        )
        REPORT["completed_phases"].append(phase)
        phase = "reopen_without_local"
        db.close()
        db = None
        DENY_ALL_LOCAL = True
        # Supplemental candidate reopen is explicitly separate from our oracle.
        from safe_geocoding_pipeline.preprocessing.stages import (
            s11_semantic_input as source,
        )
        from safe_geocoding_pipeline.preprocessing.stages import (
            s11_semantic_pipeline as pipeline,
        )

        with (
            patch.object(socket, "create_connection", offline),
            patch.object(socket.socket, "connect", offline),
            patch.object(socket.socket, "connect_ex", offline),
        ):
            inputs = source.load_accepted(candidate, ASSETS)
            reopened = pipeline.reopen(ARTIFACT, MANIFEST, True, inputs, ASSETS, EXE)
        check("S_supplemental_full_reopen_local_prohibited", reopened == manifest)
        check(
            "R_U_candidate_unchanged",
            ops.tree_inventory(ARTIFACT, check, "R_U_artifact_after")
            == before_artifact,
        )
        check(
            "Q_U_attempt_unchanged",
            ops.tree_inventory(ATTEMPT, check, "Q_U_attempt_after") == before_attempt,
        )
        REPORT["completed_phases"].append(phase)
    except BaseException as error:
        REPORT["review_harness_failures"].append(portable_failure(error, phase))
    finally:
        if db is not None:
            try:
                db.close()
            except BaseException as error:
                REPORT["review_harness_failures"].append(
                    portable_failure(error, "teardown")
                )
        REPORT["elapsed_seconds"] = int(time.monotonic() - started)
        REPORT["failed_checks"] = sorted(
            k for k, v in REPORT["checks"].items() if not v
        )
        REPORT["status"] = (
            "REVIEW_JOB_COMPLETE"
            if not REPORT["review_harness_failures"]
            else "REVIEW_JOB_INCOMPLETE"
        )
        raw = o.canonical(REPORT)
        fd = os.open(out / "evidence.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        print(
            o.canonical(
                {
                    "status": REPORT["status"],
                    "checks": len(REPORT["checks"]),
                    "failed_checks": len(REPORT["failed_checks"]),
                    "harness_failures": len(REPORT["review_harness_failures"]),
                }
            ).decode(),
            end="",
        )
    return int(bool(REPORT["review_harness_failures"]))


if __name__ == "__main__":
    raise SystemExit(main())
