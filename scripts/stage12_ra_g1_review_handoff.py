"""Reviewed REP exact-input handoff plans; never issues PASS or executes commands.

The caller supplies the independent reviewer's sealed original bytes after all
substantive checks. Liveness observations are preconditions, not a lease: the
native binder and its original deadline remain authoritative across TOCTOU.
"""

from __future__ import annotations

import hashlib
import importlib.util
from datetime import datetime
from pathlib import Path
import re
import shlex


VERSION = "stage12_rep_exact_review_handoff_plan_v1"
RELEASE = "stage12_ra_g1_exact_input_release_v1"
TARGET_NS = 180_000_000_000
ORIGINAL_NAMES = frozenset({
    "input", "review_binding", "factual_review", "context", "resource_selection", "phase8_binding",
})
RELEASE_FIELDS = frozenset({
    "schema_version", "disposition", "selection_sha256", "source_sha", "input_sha256",
    "review_binding_sha256", "bootstrap_review_sha256", "resource_selection_sha256",
})


def need(value, code="RA_G1_HANDOFF_BINDING"):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _script(name):
    path = Path(__file__).resolve().parent / (name + ".py")
    spec = importlib.util.spec_from_file_location("review_handoff_" + name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def _selection(raw, expected_sha256, source_sha, job_id):
    controller = _script("stage12_ra_g1_allocation")
    need(type(raw) is bytes and len(raw) <= 4 * 2**20 and sha(raw) == expected_sha256)
    selected = controller.validate_selection(controller.parse(raw))
    need(selected["version"] == controller.REP_ADMIN_VERSION, "RA_G1_HANDOFF_POLICY")
    need(selected["source_sha"] == source_sha)
    need(type(job_id) is str and re.fullmatch(r"[1-9][0-9]{0,19}", job_id), "RA_G1_HANDOFF_JOB")
    for path in selected["paths"].values():
        need(not any(c in path for c in "\n\r\\\x00"), "RA_G1_HANDOFF_PATH")
    return controller, selected


def refusal_paths(selected):
    paths = selected["paths"]
    root = Path(paths["allocation_root"])
    return tuple(str(path) for path in (
        root / "binder.wait.record", root / "binder.handoff.record",
        root / "binder_resources/preopening.record",
        root / "binder_resources/monitor_terminal.record",
        root / "binder_resources/worker_validation.record",
        root / "binder_resources/supervisor_terminal.record",
        Path(paths["supervisor_state"]), Path(paths["worker_return"]),
        Path(paths["outcome"]), Path(paths["output"]), Path(paths["release"]),
    ))


def _eligibility_lines(selected, job_id):
    q = shlex.quote
    result = ["handoff_state=$(squeue -h -j " + q(job_id) + " -o '%i|%T')",
              'test "$handoff_state" = ' + q(job_id + "|RUNNING")]
    for path in refusal_paths(selected):
        result.extend(("test ! -e " + q(path), "test ! -L " + q(path)))
    return result


def preparation_plan(selection_raw, *, selection_sha256, source_sha, job_id):
    """Prepare this exact bounded retrieval before publishing the factual review."""
    _, selected = _selection(selection_raw, selection_sha256, source_sha, job_id)
    root = Path(selected["paths"]["allocation_root"])
    relative = [str(Path(selected["paths"][key]).relative_to(root))
                for key in ("input", "binding", "context", "review")]
    relative += ["review_resources/admin_binding.record", "binder_resources/admin_binding.record"]
    q = shlex.quote
    command = "\n".join([
        "set -e", *_eligibility_lines(selected, job_id),
        "test -f " + q(selected["paths"]["input"]),
        "test -f " + q(selected["paths"]["binding"] + "/integration_review.binding.json"),
        "tar -cf - -C " + q(str(root)) + " " + " ".join(map(q, relative)), "",
    ])
    return dict(schema_version=VERSION, operation="PREPARE_FETCH_BEFORE_FACTUAL_PUBLICATION",
                selection_sha256=selection_sha256, source_sha=source_sha, job_id=job_id,
                expected_relative_roots=relative, command=command, max_external_units=5,
                components=dict(ssh=1, shell=1, squeue=1, command_substitution=1, tar=1),
                maximum_archive_bytes=16 * 2**20, extraction="REGULAR_PRIVATE_FILES_ONLY_NO_LINKS",
                review="ALL_SUBSTANTIVE_CHECKS_BEFORE_SEALED_RELEASE_PUBLICATION",
                authority="NOT_ISSUED_BY_HELPER")


def publication_plan(
    selection_raw, release_raw, originals, *, selection_sha256, source_sha, job_id,
    reviewer_release_sha256, observed_utc, slurm_state, local_factual_command_start_ns,
    local_observed_ns, existing_paths=(),
):
    """Validate supplied sealed originals and return a selected-only command plan.

    The two local times use one reviewer's clock. They estimate progress from
    factual-publication command entry, and are never compared to native ticks.
    Login-host uptime cannot establish compute-host binder elapsed time. Local
    review completion is not remote acceptance; native expiry remains unknown.
    """
    controller, selected = _selection(selection_raw, selection_sha256, source_sha, job_id)
    need(type(release_raw) is bytes and len(release_raw) <= 8192
         and sha(release_raw) == reviewer_release_sha256, "RA_G1_HANDOFF_SEALED_BYTES")
    release = controller.parse(release_raw)
    need(type(release) is dict and set(release) == RELEASE_FIELDS
         and release["schema_version"] == RELEASE and release["disposition"] == "PASS")
    need(type(originals) is dict and set(originals) == ORIGINAL_NAMES)
    values = {}
    for name, raw in originals.items():
        limit = (4 * 2**20 if name in ("input", "review_binding")
                 else 8192 if name == "phase8_binding" else 65536)
        need(type(raw) is bytes and len(raw) <= limit, "RA_G1_HANDOFF_ORIGINAL")
        values[name] = controller.parse(raw)
    expected = dict(schema_version=RELEASE, disposition="PASS", selection_sha256=selection_sha256,
                    source_sha=source_sha, input_sha256=sha(originals["input"]),
                    review_binding_sha256=sha(originals["review_binding"]),
                    bootstrap_review_sha256=sha(originals["factual_review"]),
                    resource_selection_sha256=sha(originals["resource_selection"]))
    need(release == expected and release["resource_selection_sha256"] == selected["resource_selection_sha256"])

    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as assurance
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_execution as execution
    from safe_geocoding_pipeline.preprocessing.stages.s12_ra_g1_public import DIAGNOSTIC_REVIEW

    data, review, factual = (values[key] for key in ("input", "review_binding", "factual_review"))
    resource = assurance.validate_selection(values["resource_selection"])
    need(resource["schema_version"] == assurance.REP_ADMIN_SELECTION, "RA_G1_HANDOFF_POLICY")
    context = execution.validate_supervisor_context(values["context"])
    phase = values["phase8_binding"]
    assurance.shape(phase, execution.ADMIN_BINDING_SCHEMA)
    resource_sha, context_sha = sha(originals["resource_selection"]), sha(originals["context"])
    need(context["scope"] == selected["scope"] == resource["scope"] == phase["scope"]
         and context["source_git_sha"] == resource["source_git_sha"] == phase["source_git_sha"] == source_sha
         and context["selection_sha256"] == phase["selection_sha256"] == resource_sha
         and context["adoption_sha256"] == phase["adoption_sha256"] == resource["adoption_sha256"]
         and context["run_nonce"] == selected["intent_id"] and str(context["slurm_job_id"]) == job_id
         and context["private_paths"] == dict(allocation_root=selected["paths"]["allocation_root"],
             resource_evidence_root=selected["paths"]["output"], scratch_root=selected["paths"]["allocation_root"])
         and phase["role"] == "BINDER" and phase["phase_id"] == 8
         and phase["supervisor_context_sha256"] == context_sha
         and phase["process_uid"] == context["worker_uid"]
         and phase["process_pid"] != context["supervisor"]["pid"])
    stage = next(row for row in resource["limits"]["stages"] if row["id"] == 8)
    start, deadline = phase["scope_start_mono_ns"], phase["deadline_mono_ns"]
    need(stage["deadline_ms"] == 240000 and start < deadline <= start + 240_000_000_000,
         "RA_G1_HANDOFF_DEADLINE")
    diagnostic = _script("stage12_ra_g1_diagnostic")
    diagnostic.validate_envelope(data, source_sha, for_execution=True)
    diagnostic.validate_workloads(data)
    diagnostic.validate_resource_family(data["version"], resource)
    need(data["configuration"]["command_paths"] == {
        "source": selected["paths"]["source"], "input": selected["paths"]["input"],
        "output": selected["paths"]["output"], "evidence_bundle": selected["paths"]["binding"],
    })
    need(data["configuration"]["resource_execution"] == dict(
        schema_version=execution.EXECUTION_REQUEST, supervisor_context_path=selected["paths"]["context"],
        supervisor_context_sha256=context_sha))
    need(review.get("version") == DIAGNOSTIC_REVIEW and review.get("disposition") == "PASS"
         and review.get("configuration_sha256") == controller.digest(data["configuration"])
         and review.get("source_files") == selected["source_files"]
         and factual.get("disposition") == "PASS" and factual.get("source_sha") == source_sha
         and factual.get("selection_sha256") == selection_sha256)
    need(type(existing_paths) in (tuple, list)
         and len(existing_paths) <= len(refusal_paths(selected))
         and all(type(path) is str and path in refusal_paths(selected) for path in existing_paths))
    need(slurm_state == "RUNNING" and not existing_paths,
         "RA_G1_HANDOFF_INELIGIBLE")
    need(type(local_factual_command_start_ns) is int and type(local_observed_ns) is int
         and 0 <= local_factual_command_start_ns <= local_observed_ns, "RA_G1_HANDOFF_LOCAL_TIMELINE")
    need(type(observed_utc) is str, "RA_G1_HANDOFF_WINDOW")
    try:
        datetime.strptime(observed_utc, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        raise RuntimeError("RA_G1_HANDOFF_WINDOW") from None
    need(selected["valid_from"] <= observed_utc < selected["valid_until"], "RA_G1_HANDOFF_WINDOW")
    destination = selected["paths"]["release"]
    temporary = destination + ".publication-" + sha(release_raw)[:12] + ".tmp"
    parent, bundle = str(Path(destination).parent), Path(selected["paths"]["binding"])
    checksums = {
        selected["paths"]["input"]: sha(originals["input"]),
        str(bundle / "integration_review.binding.json"): sha(originals["review_binding"]),
        selected["paths"]["review"]: sha(originals["factual_review"]),
        selected["paths"]["context"]: context_sha,
        str(bundle / "resource_evidence" / (resource_sha + ".record")): resource_sha,
        str(Path(selected["paths"]["allocation_root"]) / "binder_resources/admin_binding.record"): sha(originals["phase8_binding"]),
    }
    checksum_text = "".join(digest + "  " + path + "\n" for path, digest in checksums.items())
    q = shlex.quote
    lines = ["set -e", "umask 077", "test -d " + q(parent), "test ! -L " + q(parent)]
    for path in (destination, temporary):
        lines.extend(("test ! -e " + q(path), "test ! -L " + q(path)))
    lines += _eligibility_lines(selected, job_id)
    lines += ["sha256sum --check --status <<'HANDOFF_PINNED_ORIGINALS'"]
    lines += [digest + "  " + path for path, digest in checksums.items()]
    lines += ["HANDOFF_PINNED_ORIGINALS",
              "set -o noclobber", "printf '%s\\n' " + q(release_raw.decode().removesuffix("\n")) + " > " + q(temporary),
              "set +o noclobber", "timeout --signal=TERM --kill-after=1s 5s sync -f " + q(temporary),
              "mv --no-clobber --no-target-directory -- " + q(temporary) + " " + q(destination),
              "test ! -e " + q(temporary),
              "timeout --signal=TERM --kill-after=1s 5s sync -f " + q(parent),
              "sha256sum -- " + q(destination), ""]
    local_elapsed = local_observed_ns - local_factual_command_start_ns
    return dict(schema_version=VERSION, operation="PUBLISH_REVIEWER_SEALED_RELEASE_ONLY",
                command="\n".join(lines), destination=destination, temporary=temporary,
                raw_sha256=sha(release_raw), raw_bytes=len(release_raw), original_sha256={
                    key: sha(raw) for key, raw in originals.items()}, source_sha=source_sha,
                selection_sha256=selection_sha256, job_id=job_id,
                original_binder_start_ns=start, original_binder_deadline_ns=deadline,
                operational_target_native_anchor_ns=start + TARGET_NS,
                local_factual_command_start_ns=local_factual_command_start_ns,
                local_observed_ns=local_observed_ns, local_elapsed_ns=local_elapsed,
                target_status="LOCAL_ESTIMATE_WITHIN_180S" if local_elapsed <= TARGET_NS
                else "LOCAL_ESTIMATE_EXCEEDS_180S_NATIVE_ELIGIBILITY_UNKNOWN",
                current_native_elapsed="NOT_OBSERVED_NO_CROSS_HOST_CLOCK_COMPARISON",
                eligibility_observation_scope="LOGIN_SLURM_AND_SHARED_FILESYSTEM_ONLY",
                max_external_units=11, components=dict(ssh=1, shell=1, squeue=1,
                    command_substitution=1, prehash_sha256sum=1, timeout_wrappers=2,
                    sync_children=2, mv=1, readback_sha256sum=1),
                creation_attempts_precharged=3,
                logical_write_bytes_precharged=len(release_raw) + len(checksum_text.encode("utf8")),
                possible_heredoc_storage=dict(creation_attempts=1, bytes=len(checksum_text.encode("utf8")),
                    physical_accounting="UNKNOWN_NATIVE_OR_UNLINKED_NOT_A_PROVEN_BOUND",
                    reservation="WITHIN_EXISTING_240MIB_1544_METADATA_NO_CAP_INCREASE_NO_CREDIT_IF_PIPE"),
                expected_stdout=[sha(release_raw), destination],
                expected_stdout_utf8=sha(release_raw) + "  " + destination + "\n",
                acceptance="ZERO_EXIT_AND_EXACT_READBACK_REQUIRED_NATIVE_BINDER_RECHECK_AUTHORITATIVE",
                toctou="RUNNING_AND_ABSENCE_CHECKS_ARE_OBSERVATIONS_NOT_A_LEASE",
                authority="NOT_ISSUED_BY_HELPER")


def validate_publication_result(plan, *, returncode, stdout):
    """An exact command readback still does not prove native binder acceptance."""
    need(type(returncode) is int and returncode == 0 and type(stdout) is bytes
         and stdout == plan["expected_stdout_utf8"].encode("utf8"), "RA_G1_HANDOFF_PUBLICATION_UNCERTAIN")
    return dict(status="PUBLISHED_EXACT_BYTES_NOT_NATIVE_ACCEPTANCE",
                release_sha256=plan["raw_sha256"], native_acceptance="NOT_OBSERVED")
