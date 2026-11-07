"""One explicitly authorized, bounded PUBLIC/SYNTHETIC SAFE capability job.

No accepted Stage 11 artifact path, protected payload reader, DEVELOPMENT
execution command, automatic resubmission or protected-policy selection exists.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import platform
import ssl
import os
import resource
import subprocess
import time
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path
from typing import Any, Iterator

from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm

from .stages import s12_assets as assets
from .stages import s12_deployment as deployment
from .stages import s12_operations as ops
from .stages import s12_probe as probe
from .stages import s12_public_audit as audit
from .stages import s12_response as response
from .stages import s12_retrieval_contract as c
from .stages import s12_storage as io
from .stages import s12_transport as transport

IMPLEMENTATION_CLEARED_FOR_PROBE = True

CONFIG_KEYS = frozenset(
    """
scope origin approved_ip configuration_evidence_sha256 target_limit header_limit
operator_max_size deeper_sizes operator_size_evidence_sha256 workload_authorization_sha256
secret_source_category authentication_mechanism walltime_seconds output_directory
""".split()
)


def validate_config(
    config: dict[str, Any],
) -> tuple[transport.TransportProfile, dict[str, Any]]:
    c.require(
        set(config) == CONFIG_KEYS and config["scope"] == "PUBLIC_SYNTHETIC_ONLY",
        "PUBLIC_PROBE_CONFIGURATION_INVALID",
    )
    c.require(
        config["secret_source_category"]
        in ("APPROVED_RUNTIME_ENVIRONMENT", "APPROVED_PRIVATE_FILE")
        and config["authentication_mechanism"] == "X-API-Key",
        "PUBLIC_PROBE_AUTH_SOURCE_UNVERIFIED",
    )
    c.require(
        type(config["walltime_seconds"]) is int
        and 60 <= config["walltime_seconds"] <= 1740,
        "PUBLIC_PROBE_BUDGET_INVALID",
    )
    profile = transport.TransportProfile(
        config["origin"],
        config["approved_ip"],
        bytes.fromhex(config["configuration_evidence_sha256"]),
        config["target_limit"],
        config["header_limit"],
    )
    profile.validate()
    plan = probe.workload(
        config["deeper_sizes"],
        operator_max_size=config["operator_max_size"],
        operator_size_evidence_sha256=bytes.fromhex(
            config["operator_size_evidence_sha256"]
        )
        if config["operator_size_evidence_sha256"] is not None
        else None,
        workload_authorization_sha256=bytes.fromhex(
            config["workload_authorization_sha256"]
        ),
    )
    return profile, plan


def public_shapes(raw: bytes) -> tuple[Any, ...]:
    """Capability observation only; no invented deployment-bound execution ID.

    Frozen scientific validation/extraction remains gated by verified deployment
    vocabularies and echo behavior. Raw responses permit later authorized replay.
    """
    parsed = response.Parser(raw).parse()
    obj = parsed.value
    response.envelope(obj)
    c.require(
        obj.get("type") == "FeatureCollection" and type(obj.get("features")) is list,
        "RESPONSE_CONTRACT_INVALID",
    )
    features = obj["features"]
    if "geocoding" in obj:
        geo = obj["geocoding"]
        c.require(type(geo) is dict, "RESPONSE_CONTRACT_INVALID")
        response.envelope(geo, bbox=False)
        for key in ("version", "attribution"):
            if key in geo:
                c.require(type(geo[key]) is str, "RESPONSE_CONTRACT_INVALID")
        if "query" in geo:
            c.require(type(geo["query"]) is dict, "RESPONSE_CONTRACT_INVALID")
        if "timestamp" in geo:
            timestamp = geo["timestamp"]
            c.require(
                type(timestamp) is response.Number
                and response.NUMBER.fullmatch(timestamp.token.encode()) is not None
                and all(ch not in timestamp.token for ch in ".eE"),
                "RESPONSE_CONTRACT_INVALID",
            )
    for feature in features:
        c.require(
            type(feature) is dict
            and feature.get("type") == "Feature"
            and type(feature.get("properties")) is dict
            and type(feature.get("geometry")) is dict,
            "RESPONSE_CONTRACT_INVALID",
        )
        geometry = feature["geometry"]
        response.envelope(feature, messages=False)
        c.require("crs" not in geometry, "RESPONSE_CONTRACT_INVALID")
        coordinates = geometry.get("coordinates")
        c.require(
            geometry.get("type") == "Point"
            and type(coordinates) is list
            and len(coordinates) == 2,
            "RESPONSE_CONTRACT_INVALID",
        )
        response.numeric(coordinates[0], -180, 180)
        response.numeric(coordinates[1], -90, 90)
        for name in ("source", "layer"):
            c.require(
                type(feature["properties"].get(name)) is str
                and feature["properties"][name] != "",
                "RESPONSE_CONTRACT_INVALID",
            )
        for name in response.STRINGS:
            response.optional_string(feature["properties"].get(name))
        response.optional_string(feature.get("id"))
        confidence = feature["properties"].get("confidence")
        if confidence is not None:
            response.numeric(confidence, 0, 1)
    return tuple(response.structural(feature) for feature in features)


def validate_output_scope(output: Path) -> None:
    c.require(
        output.is_absolute()
        and output.parent
        == Path(
            "/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage12/public_probe"
        ),
        "PUBLIC_PROBE_OUTPUT_SCOPE_INVALID",
    )


def aggregate(values: list[int]) -> dict[str, int | None]:
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "min": ordered[0] if ordered else None,
        "max": ordered[-1] if ordered else None,
        "p50": ordered[(len(ordered) - 1) * 50 // 100] if ordered else None,
        "p95": ordered[(len(ordered) - 1) * 95 // 100] if ordered else None,
        "sum": sum(ordered),
    }


def run(
    config: dict[str, Any], implementation_sha: str, repository: Path
) -> dict[str, Any]:
    require_goethe_nhr_slurm("stage12 public synthetic SAFE Pelias probe")
    c.require(
        IMPLEMENTATION_CLEARED_FOR_PROBE, "PUBLIC_PROBE_IMPLEMENTATION_NOT_CLEARED"
    )
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    profile, plan = validate_config(config)
    assets.verify(repository)
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository, text=True
    ).strip()
    c.require(
        actual == implementation_sha and len(actual) == 40,
        "PUBLIC_PROBE_EXECUTABLE_MISMATCH",
    )
    c.require(
        not subprocess.check_output(["git", "status", "--porcelain"], cwd=repository),
        "PUBLIC_PROBE_EXECUTABLE_DIRTY",
    )
    key = transport.Secret.runtime()
    c.require(
        (config["secret_source_category"] == "APPROVED_PRIVATE_FILE")
        == bool(os.environ.get("SAFE_PELIAS_API_KEY_FILE")),
        "PUBLIC_PROBE_AUTH_SOURCE_UNVERIFIED",
    )
    output = Path(config["output_directory"])
    validate_output_scope(output)
    io.reserve(output)
    runtime_inventory = {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "openssl": ssl.OPENSSL_VERSION,
        "packages": sorted(
            (dist.metadata["Name"], dist.version)
            for dist in importlib.metadata.distributions()
        ),
    }
    io.write(output / "runtime_inventory.json", c.canonical(runtime_inventory))
    io.write(output / "workload.json", c.canonical(plan))
    io.write(
        output / "provenance.json",
        c.canonical(
            {
                "implementation_sha": implementation_sha,
                "job_id": os.environ["SLURM_JOB_ID"],
                "submission_scope": "PUBLIC_SYNTHETIC_ONLY",
                "started_utc": datetime.now(timezone.utc).isoformat(),
                "configuration_sha256": c.sha(c.canonical(config)).hex(),
                "runtime_inventory_sha256": c.sha(c.canonical(runtime_inventory)).hex(),
                "operations_policy_sha256": ops.Operations().fingerprint().hex(),
            }
        ),
    )
    audit.initialize(output)
    operations = ops.Operations()
    operations.validate(initial_probe=True)
    admission = ops.Admission(operations)
    start_ms = time.monotonic_ns() // 1_000_000
    observed: dict[tuple[int, int, str], tuple[Path, int, bytes]] = {}
    sizes: dict[str, dict[str, Any]] = {}
    prefix_pairs: dict[str, dict[str, int]] = {}
    endpoint_counts = {"FULL_TEXT": 0, "STRUCTURED": 0}
    dispatch_started = 0
    audit_started = audit_completed = 0
    http_errors = network_errors = retry_after_observed = 0
    sent = retries = same_agree = same_disagree = prefix_agree = prefix_disagree = 0
    report: dict[str, Any] = {
        "summary_version": "stage12_pelias_retrieval_summary_v1",
        "scope": "PUBLIC_SYNTHETIC_CAPABILITY_ONLY",
        "implementation_sha": implementation_sha,
        "status": "FAILED",
        "failure_phase": "preflight",
        "failure_code": "UNCLASSIFIED_STATIC_FAILURE",
        "authentication": {
            "mechanism": "X-API-Key",
            "present": True,
            "accepted": False,
            "source_category": config["secret_source_category"],
            "provider_preflight": "PASS",
        },
        "deployment_observability": {
            kind: {name: "UNKNOWN" for name in names}
            for kind, names in deployment.CORE_KEYS.items()
        },
        "scientific_extraction": "BLOCKED_PENDING_VERIFIED_DEPLOYMENT_VOCABULARY_AND_ECHO_ADAPTER",
        "drift_guard": "BLOCKED_PENDING_OPERATOR_EVIDENCE",
        "C": "UNSELECTED",
        "T": "UNSELECTED",
        "N": "UNSELECTED",
        "privacy": {
            "protected_network_requests": 0,
            "holdout_access": 0,
            "production_access": 0,
            "secret_leakage": 0,
            "external_non_safe_calls": 0,
        },
    }
    try:
        for call_number, (size, repetition, case) in enumerate(
            probe.planned_calls(plan), 1
        ):
            c.require(
                time.monotonic_ns() // 1_000_000
                - start_ms
                + operations.attempt_timeout_ms
                < config["walltime_seconds"] * 1000,
                "PUBLIC_PROBE_WALLTIME_BUDGET_EXHAUSTED",
            )
            target, target_hash = c.materialize(
                case["core"],
                bytes.fromhex(case["fixture_id"]),
                c.policy(size),
                target_limit=profile.target_limit,
            )
            size_row = sizes.setdefault(
                str(size),
                {
                    "attempts": 0,
                    "accepted": 0,
                    "failures": 0,
                    "candidate_counts": [],
                    "latency_ms": [],
                    "payload_bytes": [],
                },
            )
            report["failure_phase"] = "dispatch"
            for attempt in range(1, operations.max_attempts + 1):
                c.require(admission.open_reason is None, "CIRCUIT_BREAKER_OPEN")
                now = time.monotonic_ns() // 1_000_000
                time.sleep(max(0, admission.next_admission_ms - now) / 1000)
                c.require(
                    time.monotonic_ns() // 1_000_000
                    - start_ms
                    + operations.attempt_timeout_ms
                    < config["walltime_seconds"] * 1000,
                    "PUBLIC_PROBE_WALLTIME_BUDGET_EXHAUSTED",
                )
                begin = {
                    "call": call_number,
                    "attempt": attempt,
                    "fixture_id": case["fixture_id"],
                    "size": size,
                    "repetition": repetition,
                    "request_target_sha256": target_hash.hex(),
                    "outcome": "UNKNOWN_DELIVERY",
                }
                name = f"call_{call_number:04d}_attempt_{attempt}"
                audit.begin(output, begin)
                audit_started += 1
                admission.admit(time.monotonic_ns() // 1_000_000)
                dispatch_started += 1
                capture = transport.send(target, profile, key, operations)
                http_errors += int(capture.status is not None and capture.status != 200)
                network_errors += int(capture.status is None)
                retry_after_observed += int(capture.retry_after_seconds is not None)
                sent += 1
                size_row["attempts"] += 1
                retries += int(attempt > 1)
                finish = {
                    "call": call_number,
                    "attempt": attempt,
                    "status": capture.status,
                    "outcome": capture.outcome,
                    "reason": capture.reason,
                    "content_type": capture.content_type,
                    "content_encoding": capture.content_encoding,
                    "elapsed_ms": capture.elapsed_ms,
                    "finished_utc": datetime.now(timezone.utc).isoformat(),
                    "received_body_bytes": capture.received_body_bytes,
                    "payload_bytes": len(capture.payload)
                    if capture.payload is not None
                    else None,
                    "retry_after_seconds": capture.retry_after_seconds,
                    "retry_clock": capture.retry_after_audit.audit()
                    if capture.retry_after_audit
                    else None,
                }
                try:
                    io.write(output / (name + "_finish.json"), c.canonical(finish))
                except Exception:
                    raise audit.AuditWriteError(
                        capture.reason
                        if capture.outcome in c.OUTCOMES
                        and capture.outcome not in (*c.SUCCESS, "UNKNOWN_DELIVERY")
                        else "PUBLIC_PROBE_EVIDENCE_WRITE_FAILED"
                    ) from None
                size_row["latency_ms"].append(capture.elapsed_ms)
                raw = capture.payload
                privacy_rejected = False
                if raw is not None:
                    try:
                        response.secret_guard(raw, key.value)
                    except c.Stage12Error:
                        raw = None
                        privacy_rejected = True
                report["failure_phase"] = (
                    "response_contract" if raw is not None else "dispatch"
                )
                terminal, features = audit.complete(
                    output,
                    name,
                    raw,
                    validator=public_shapes,
                    privacy_rejected=privacy_rejected,
                    primary_failure_reason=capture.reason
                    if capture.outcome in c.OUTCOMES
                    and capture.outcome not in (*c.SUCCESS, "UNKNOWN_DELIVERY")
                    else None,
                )
                audit_completed += 1
                if capture.outcome == "TECHNICAL_FAILURE_RETRYABLE":
                    admission.finish(
                        time.monotonic_ns() // 1_000_000,
                        capture.outcome,
                        capture.elapsed_ms,
                        status=capture.status,
                        parsed_after=capture.retry_after_seconds,
                    )
                    c.require(admission.open_reason is None, "CIRCUIT_BREAKER_OPEN")
                    time.sleep(
                        ops.retry_delay(
                            bytes.fromhex(case["fixture_id"]),
                            attempt + 1,
                            capture.retry_after_seconds,
                            operations,
                        )
                        / 1000
                    )
                    continue
                if terminal["outcome"] not in c.SUCCESS:
                    raise c.Stage12Error(terminal["reason_code"])
                assert raw is not None and features is not None
                raw_path = output / (name + ".zst")
                observed[(size, repetition, case["fixture_id"])] = (
                    raw_path,
                    len(raw),
                    c.sha(raw),
                )
                if repetition == 1:
                    first_path, length, fingerprint = observed[
                        (size, 0, case["fixture_id"])
                    ]
                    same = features == public_shapes(
                        response.decompress(
                            io.read(first_path),
                            length=length,
                            expected_hash=fingerprint,
                        )
                    )
                    same_agree += int(same)
                    same_disagree += int(not same)
                    c.require(same, "PUBLIC_PROBE_SAME_SIZE_INSTABILITY")
                for smaller in (1, 3, 5, 10):
                    previous = observed.get((smaller, repetition, case["fixture_id"]))
                    if smaller >= size or previous is None:
                        continue
                    path, length, fingerprint = previous
                    prefix_same = features[:smaller] == public_shapes(
                        response.decompress(
                            io.read(path), length=length, expected_hash=fingerprint
                        )
                    )
                    prefix_agree += int(prefix_same)
                    prefix_disagree += int(not prefix_same)
                    pair = prefix_pairs.setdefault(
                        f"{smaller}:{size}", {"agreement": 0, "disagreement": 0}
                    )
                    pair["agreement"] += int(prefix_same)
                    pair["disagreement"] += int(not prefix_same)
                size_row["accepted"] += 1
                size_row["candidate_counts"].append(len(features))
                size_row["payload_bytes"].append(len(raw))
                report["authentication"]["accepted"] = True
                endpoint_counts[case["core"]["search_mode"]] += 1
                admission.finish(
                    time.monotonic_ns() // 1_000_000,
                    "SUCCESS_WITH_CANDIDATES"
                    if features
                    else "SUCCESS_ZERO_CANDIDATES",
                    capture.elapsed_ms,
                    status=200,
                )
                break
        report.update(status="COMPLETED", failure_phase=None, failure_code=None)
    except Exception as error:
        if sizes:
            sizes[str(size)]["failures"] += 1
        report["failure_code"] = (
            str(error)
            if isinstance(error, c.Stage12Error)
            else "PUBLIC_PROBE_HARNESS_FAILURE"
        )
        if isinstance(error, audit.AuditWriteError):
            report["evidence_write_status"] = "FAILED"
    finally:
        for row in sizes.values():
            for field in ("latency_ms", "payload_bytes", "candidate_counts"):
                row[field] = aggregate(row[field])
        report.update(
            public_audit_attempts_started=audit_started,
            public_audit_attempts_completed=audit_completed,
            public_audit_attempts_incomplete=audit_started - audit_completed,
            public_audit_scope=audit.SCOPE,
            public_synthetic_requests_sent=sent if dispatch_started == sent else None,
            dispatch_attempts_started=dispatch_started,
            uncertain_dispatches=dispatch_started - sent,
            http_errors=http_errors,
            network_errors=network_errors,
            retry_after_observed=retry_after_observed,
            above10_capability=plan["above10_capability"],
            protected_calibration="BLOCKED_PENDING_OWNER_GATES"
            if plan["deeper_sizes"]
            else "PROTECTED CALIBRATION BLOCKED PENDING SAFE T>10 CAPABILITY",
            retry_count=retries,
            same_size_agreement=same_agree,
            same_size_disagreement=same_disagree,
            prefix_agreement=prefix_agree,
            prefix_disagreement=prefix_disagree,
            tested_rate_per_second=1,
            connection_bound=2,
            actual_dispatch_parallelism=1,
            elapsed_ms=time.monotonic_ns() // 1_000_000 - start_ms,
            sizes=sizes,
        )
        report.update(
            prefix_pairs=prefix_pairs,
            endpoint_valid_responses=endpoint_counts,
            circuit_breaker=admission.open_reason,
        )
        try:
            io.write(output / "sanitized_report.json", c.canonical(report))
        except Exception:
            report["evidence_write_status"] = "FAILED"
            if report["status"] == "COMPLETED":
                report.update(
                    status="FAILED",
                    failure_phase="evidence_write",
                    failure_code="PUBLIC_PROBE_EVIDENCE_WRITE_FAILED",
                )
    return report


def _run_operations_block(
    profile: dict[str, Any],
    plan: dict[str, Any],
    start: dict[str, Any],
    *,
    work_factory: Any,
    output: Path,
    block_id: int,
    authority: Any,
    clock: Any,
    dispatch: Any,
    runtime_inventory: dict[str, Any],
    runtime_key: bytes,
    control_adapters: dict[int, Any],
    monitor: Any,
    free_bytes: Any,
    segment_authority: str,
    writer_exclusion_evidence: str,
    epoch: str,
    writer_release_evidence: str,
    pause_requested: Any = None,
    predecessor: Path | None = None,
    continuation_authority: str | None = None,
    public_validation: Any = None,
    ascending_sizes: bool = False,
    task_deadline_ns: int | None = None,
    diagnostics: Any = None,
    timing_observer: Any = None,
) -> dict[str, Any]:
    """Explicit O-r2 programmatic boundary; no real adapter or secret provider.

    All dependencies and actual authority are mandatory. The existing CLI and
    v1 path remain unchanged. D3 exercises this path solely with synthetic
    gates/transports; a real-service adapter requires separate integration.
    One predeclared block is executed; an upward next block is a separate call
    requiring reviewed evidence and fresh explicit authority.
    """
    from concurrent.futures import ThreadPoolExecutor
    from .stages import s12_public_operations as po

    if profile.get("schema_version") == "stage12_transport_operations_v3":
        from .stages import s12_public_sampling_contract as po
    elif profile.get("schema_version") == "stage12_transport_operations_v4":
        from .stages import s12_wf_ap2_contract as po
    from .stages import s12_public_operational_audit as oa
    from .stages import s12_public_journal as pj
    from .stages import s12_public_scheduler as ps
    from .stages import s12_public_reporting as pr
    from .stages import s12_public_recovery as recovery

    from .stages.s12_public_diagnostics import Failures

    diagnostics = diagnostics or Failures(clock)
    operation = "PREFLIGHT"
    po.verify_authorities(profile, plan, start, authority)
    po.verify_work_manifest(work_factory, plan)
    po.require(po.digest(runtime_inventory) == start["runtime_inventory_sha256"])
    recipes = {r["recipe_id"]: r for r in plan["control_recipes"]}
    fixtures = {f["fixture_id"]: f for f in probe.fixtures()}
    block = plan["blocks"][block_id - 1]
    monitored = profile["monitoring"]["mode"] == "FROZEN_V1"

    def queue_role(row):
        if row["work_id"] in block["reserved_control_ids"]:
            return (
                "REFRESH"
                if monitored
                and row["kind"] == "SERVICE_CONTROL"
                and row["recipe_id"] == profile["monitoring"]["refresh_recipe_id"]
                else "RESERVED"
            )
        if (
            monitored
            and row["kind"] == "SERVICE_CONTROL"
            and recipes[row["recipe_id"]]["purpose"] == "IDENTITY_CLOSURE"
        ):
            return "CLOSURE"
        return "ORDINARY"

    def target_for(row):
        if row["kind"] == "DATA":
            fixture = fixtures[row["fixture_id"]]
            return c.materialize(
                fixture["core"],
                bytes.fromhex(row["fixture_id"]),
                c.policy(row["result_limit"]),
                target_limit=2**32,
            )[0]
        # The typed reviewed adapter owns exact bytes, never configuration URLs.
        return control_adapters[row["recipe_id"]].target(recipes[row["recipe_id"]])

    # Derive finite-work bounds with ONE target resident, before there is a
    # queue or any slot. No speculative lookahead request is kept outside the
    # byte budget. Only ordinary work coexists with the reserved refresh.
    # Closure starts after draining and releasing queued materializations.
    target_bound = 0
    role_bounds = dict.fromkeys(("ORDINARY", "REFRESH", "CLOSURE", "RESERVED"), 0)
    for row in work_factory():
        target = target_for(row)
        po.require(type(target) is bytes and len(target) > 0)
        target_size = len(target)
        po.require(
            target_size <= profile["resources"]["pending_request_bytes"],
            "S12_PUBLIC_SINGLE_REQUEST_TOO_LARGE",
        )
        target_bound = max(target_bound, target_size)
        if row["block_id"] == block_id:
            role = queue_role(row)
            role_bounds[role] = max(role_bounds[role], target_size)
        del target
    ordinary_bound, monitor_reserve = role_bounds["ORDINARY"], role_bounds["REFRESH"]
    po.require(
        ordinary_bound + monitor_reserve
        <= profile["resources"]["pending_request_bytes"],
        "S12_PUBLIC_MONITOR_QUEUE_HEADROOM_REQUIRED",
    )

    def locate_attempt(base, work_id, attempt):
        seen = set()
        while base is not None:
            po.require(str(base) not in seen)
            seen.add(str(base))
            candidate = base / "attempts" / audit.name_for(work_id, attempt)
            if candidate.exists():
                return candidate
            base = pj.predecessor_root(base)
        raise c.Stage12Error("S12_CAPTURE_INCOMPLETE")

    def verify_at(base, row, event_body):
        root = locate_attempt(base, row["work_id"], event_body["attempt"])
        if row["kind"] == "DATA":
            po.require(io.metadata(io.read(root / "work.json")) == row)
            terminal = audit.reopen(
                root,
                audit.name_for(row["work_id"], event_body["attempt"]),
                validator=public_shapes
                if public_validation is None
                else public_validation.validator(row, root),
                context=oa.DataContext(public_validation),
            )
            receipt_path = root / (
                audit.name_for(row["work_id"], event_body["attempt"]) + "_receipt.json"
            )
        else:
            control_begin = po.parse(io.read(root / "begin.json"), po.CONTROL_BEGIN)
            po.require(
                control_begin["campaign_start_sha256"] == po.digest(start)
                and control_begin["profile_sha256"] == po.digest(profile)
                and control_begin["plan_sha256"] == po.digest(plan)
                and control_begin["work_id"] == row["work_id"]
                and control_begin["attempt"] == event_body["attempt"]
            )
            po.require(
                io.metadata(io.read(root / "recipe.json")) == recipes[row["recipe_id"]]
            )
            terminal = oa.reopen_control(
                root, control_adapters[row["recipe_id"]], key=runtime_key
            )
            receipt_path = root / "inventory.json"
        po.require(
            c.sha(io.read(receipt_path)).hex() == event_body["receipt_inventory_sha256"]
        )
        return terminal

    rebased = None
    if predecessor is not None:
        po.require(
            not output.is_relative_to(predecessor)
            and not predecessor.is_relative_to(output)
        )
        po.validate_type(continuation_authority, "D")
        authority.require(
            "predecessor_input",
            continuation_authority,
            {"path": str(predecessor), "scope": po.SCOPE},
        )
        rebased = recovery.clean_continuation(
            predecessor,
            start,
            profile,
            plan,
            authority=authority,
            new_segment_authority=continuation_authority,
            now_ns=clock.now_ns(),
            work_factory=work_factory,
            verify_receipt=lambda row, event: verify_at(predecessor, row, event),
        )
        previous_block = rebased["snapshot"]["controller"]["block_id"]
        po.require(block_id in (previous_block, previous_block + 1))
        previous_events = pj.read_events(predecessor, po.digest(start), contract=po)
        last_epoch = None
        for event in previous_events:
            last_epoch = event["epoch_id"]
        po.require(epoch != last_epoch)
        if block_id != previous_block:
            po.require(
                recovery.required_work_complete(
                    plan, work_factory, rebased["ledger"], through_block=previous_block
                )
            )
            previous_report = io.metadata(io.read(predecessor / "block_report.json"))
            closed_hash = None
            for event in pj.read_events(predecessor, po.digest(start), contract=po):
                if (
                    event["kind"] == "BLOCK_CLOSED"
                    and event["body"]["block_id"] == previous_block
                ):
                    closed_hash = event["body"]["report_sha256"]
            po.require(
                po.digest(previous_report) == closed_hash
                and previous_report["counts"]["unprocessed_data"]["value"] == 0
            )
            new_state = profile["states"][plan["blocks"][block_id - 1]["state_id"] - 1]
            old_state = profile["states"][rebased["state_id"] - 1]
            if not po.rate_le(new_state["rate"], old_state["rate"]):
                po.require(previous_report["status"] == "PASS")
    else:
        po.require(continuation_authority is None and block_id == 1)
    if block_id > 1:
        authority.require(
            "reviewed_public_progression",
            segment_authority,
            {"plan": plan, "block_id": block_id},
        )
    coordinator = ps.Coordinator(
        profile,
        plan,
        start,
        authority=authority,
        clock=clock,
        root=output,
        block_id=block_id,
        segment_authority=segment_authority,
        writer_exclusion_evidence=writer_exclusion_evidence,
        epoch=epoch,
        free_bytes=free_bytes,
        monitor=monitor,
        predecessor=predecessor,
        rebase=rebased,
        diagnostics=diagnostics,
        timing_observer=timing_observer,
        contract=po,
    )
    writer, log = coordinator.writer, coordinator.journal
    if log.accounted_bytes is None:
        log.enable_accounting()
    # One absolute cumulative bound, including derivation, reconciliation and
    # final reopening. The shutdown reserve is already inside these budgets.
    from datetime import datetime

    window_left = max(
        0,
        (
            datetime.fromisoformat(plan["window_end"])
            - datetime.fromisoformat(clock.utc())
        ).total_seconds(),
    )
    ends = [
        coordinator.opened_ns
        + (plan["budgets"]["active_duration_ms"] - coordinator.prior_active_ms)
        * 1_000_000,
        coordinator.opened_ns
        + (block["budget"]["active_duration_ms"] - coordinator.prior_block_ms)
        * 1_000_000,
        clock.now_ns() + int(window_left * 1_000_000_000),
    ]
    if task_deadline_ns is not None:
        po.uint(task_deadline_ns, True)
        ends.append(task_deadline_ns)
    finalization_deadline = recovery.Deadline(clock, min(ends))
    writer.check_deadline = finalization_deadline.check
    writer.remaining_seconds = finalization_deadline.remaining_seconds

    def incomplete():
        coordinator.stop_sampling()

        # An uncertain writer is never reused. If it is still healthy, it may
        # persist the read-only reconciliation report without a clean seal.
        def verify_known(root, begin):
            work_id = begin.get("work_id", begin.get("call"))
            row = next((r for r in work_factory() if r["work_id"] == work_id), None)
            po.require(row is not None)
            name = audit.name_for(work_id, begin["attempt"])
            seal = root / (
                name + "_SEALED" if row["kind"] == "DATA" else "_CONTROL_SEALED"
            )
            if not seal.exists():
                return False
            receipt = root / (
                name + "_receipt.json" if row["kind"] == "DATA" else "inventory.json"
            )
            verify_at(
                output,
                row,
                {
                    "attempt": begin["attempt"],
                    "receipt_inventory_sha256": c.sha(io.read(receipt)).hex(),
                },
            )
            return True

        known = None
        try:
            finalization_deadline.check()
            with io.cooperative_io(finalization_deadline.check):
                known = recovery.unclean_reconciliation(
                    output, po.digest(start), verify_known=verify_known, contract=po
                )
            finalization_deadline.check()
        except recovery.FinalizationExpired:
            if known is not None and hasattr(known["known_files"], "close"):
                known["known_files"].close()
            # Empty *available* inventory and zero lower bound do not assert no
            # attempts. Exact totals stay null; preserved files remain reopenable.
            known = {"known_files": [], "begins_charged": {"confirmed_min": 0}}
        except BaseException:
            if known is not None and hasattr(known["known_files"], "close"):
                known["known_files"].close()
            raise

        known_files = known["known_files"]
        ap_known = (
            getattr(po, "AP_ENABLED", False)
            or po.PROFILE == "stage12_transport_operations_v3"
        ) and hasattr(known_files, "rows")
        try:
            if ap_known:

                def event_rows():
                    return known_files.rows("events/")

                def attempt_rows():
                    return known_files.rows("attempts/")
            else:
                available_events = [
                    r for r in known_files if r["path"].startswith("events/")
                ]
                available_attempts = [
                    r for r in known_files if r["path"].startswith("attempts/")
                ]

                def event_rows():
                    return iter(available_events)

                def attempt_rows():
                    return iter(available_attempts)

            report = pr.incomplete_report(
                start,
                plan,
                event_inventory_sha256=po.manifest_digest(event_rows()),
                attempt_inventory_sha256=po.manifest_digest(attempt_rows()),
                begins_lower_bound=known["begins_charged"]["confirmed_min"],
                contract=po,
            )
            if (
                not writer.failed.is_set()
                and finalization_deadline.remaining_seconds() > 0
            ):
                try:
                    if ap_known:
                        log.stream_array("available_event_inventory.json", event_rows())
                        log.stream_array(
                            "available_attempt_inventory.json", attempt_rows()
                        )
                    else:
                        writer.call(
                            lambda: log.write_array(
                                "available_event_inventory.json", event_rows()
                            )
                        )
                        writer.call(
                            lambda: log.write_array(
                                "available_attempt_inventory.json", attempt_rows()
                            )
                        )
                    writer.call(
                        lambda: log.write("incomplete_campaign_report.json", report)
                    )
                except Exception:
                    coordinator.audit_failed()
            return report
        finally:
            if ap_known:
                known_files.close()
            writer.abort()

    try:
        coordinator.start_sampling()
        records: dict[tuple[int, int], dict[str, Any]] = {}
        block = plan["blocks"][block_id - 1]
        total_rows = sum(
            plan["budgets"][k]
            for k in (
                "data_observations",
                "required_control_observations",
                "reserved_control_observations",
            )
        )

        def store_work() -> None:
            if coordinator.ap_enabled:
                log.write("operations_profile.json", profile)
                log.write("workload.json", plan)
            io.reserve(output / "work")
            io.reserve(output / "attempts")
            for row in po.work_rows(work_factory(), plan):
                io.write(
                    output / "work" / f"{row['work_id']:020d}.json", c.canonical(row)
                )

        writer.cooperative(store_work)

        def works():
            for i in range(1, total_rows + 1):
                yield io.metadata(io.read(output / "work" / f"{i:020d}.json"))

        po.verify_work_manifest(works, plan)

        def size_ready(pending):
            if (
                plan["experiment_kind"] != "CAPABILITY" and not ascending_sizes
            ) or pending.work["kind"] != "DATA":
                return True
            # One exact full work-manifest validation and one pinned event-prefix
            # traversal, rather than one growing traversal per earlier work item.
            # Fixed <=4096 integer IDs (<1 MiB conservative Python metadata bound),
            # discarded before returning; larger plans retain streaming fallback.
            po.verify_work_manifest(works, plan)
            if total_rows <= 4096:
                needed = {
                    r["work_id"]
                    for r in works()
                    if r["kind"] == "DATA"
                    and r["result_limit"] < pending.work["result_limit"]
                }
                if not needed:
                    return True
                seq, head = writer.call(lambda: (log.seq, log.last_hash))
                for event in pj.read_events(output, po.digest(start), contract=po):
                    if (
                        event["kind"] == "ATTEMPT_FINALIZED"
                        and event["body"]["outcome"]["value"] in c.SUCCESS
                    ):
                        needed.discard(event["body"]["work_id"])
                    if event["seq"] == seq:
                        po.require(po.digest(event) == head)
                        return not needed
                po.require(False, "PUBLIC_PROBE_EVIDENCE_WRITE_FAILED")
            for earlier in works():
                if (
                    earlier["kind"] != "DATA"
                    or earlier["result_limit"] >= pending.work["result_limit"]
                ):
                    continue
                if not any(
                    e["kind"] == "ATTEMPT_FINALIZED"
                    and e["body"]["work_id"] == earlier["work_id"]
                    and e["body"]["outcome"]["value"] in c.SUCCESS
                    for e in pj.read_events(output, po.digest(start), contract=po)
                ):
                    return False
            return True

        coordinator.size_ready = size_ready

        def attempt_root(work_id, attempt):
            return output / "attempts" / audit.name_for(work_id, attempt)

        def begin(pending):
            row, attempt = pending.work, pending.attempt
            from .stages.s12_public_fresh_reads import (
                WORK_ROWS_BOUND,
                work_manifest_digest,
            )

            current_work_digest = (
                work_manifest_digest(output / "work", total_rows)
                if total_rows <= WORK_ROWS_BOUND
                else po.manifest_digest(works())
            )
            po.require(current_work_digest == plan["work_manifest_sha256"])
            root = attempt_root(row["work_id"], attempt)
            if row["kind"] == "DATA":
                return oa.begin_data(
                    root,
                    profile,
                    plan,
                    start,
                    row,
                    attempt,
                    runtime_inventory,
                    validation=public_validation,
                )
            recipe = recipes[row["recipe_id"]]
            value = {
                "schema_version": po.CONTROL_BEGIN,
                "campaign_start_sha256": po.digest(start),
                "profile_sha256": po.digest(profile),
                "plan_sha256": po.digest(plan),
                "segment_id": log.segment,
                "work_id": row["work_id"],
                "attempt": attempt,
                "recipe_sha256": recipe["recipe_sha256"],
                "request_target_sha256": c.sha(pending.target).hex(),
                "started_utc": clock.utc(),
            }
            return oa.begin_control(root, value)

        def worker(slot):
            def record_hash(capture):
                record = oa.transport_record(
                    slot.pending.work, slot.key[1], capture, clock.utc()
                )
                oa.validate_transport(record)
                records[slot.key] = record
                return po.digest(record)

            def persist():
                root = attempt_root(*slot.key)
                name = (
                    audit.name_for(*slot.key) + "_finish.json"
                    if slot.pending.work["kind"] == "DATA"
                    else "transport.json"
                )
                io.write(root / name, c.canonical(records[slot.key]))

            try:
                result = dispatch(
                    slot.pending.work,
                    slot.pending.target,
                    coordinator.hooks(slot, record_hash, persist),
                )
                po.require(slot.capture == result and slot.ticket is not None)
            except BaseException as error:
                diagnostics.record(
                    "DISPATCH",
                    error,
                    work_id=slot.key[0],
                    attempt=slot.key[1],
                    writer=writer,
                    deadline=finalization_deadline,
                )
                with coordinator.safety:
                    coordinator.state, coordinator.stop_reason = (
                        "RECOVERY_BLOCKED",
                        "UNACCOUNTED_DELIVERY",
                    )
                    slot.connection = False
                    coordinator.wake.set()
                try:
                    coordinator.journal.event(
                        "STOP",
                        {
                            "why": "UNACCOUNTED_DELIVERY",
                            "primary_reason": None,
                            "trigger_event_seq": None,
                        },
                        closure=True,
                    )
                    coordinator.resource("CONNECTION_RELEASE")
                except BaseException as error:
                    diagnostics.record(
                        "CLEANUP", error, writer=writer, deadline=finalization_deadline
                    )
                    coordinator.audit_failed()
                raise

        def finish(slot):
            row, root = slot.pending.work, attempt_root(*slot.key)
            record = records[slot.key]
            if row["kind"] == "DATA":
                from .stages.s12_public_reader import PublicReader

                with PublicReader(root) as reader, io.public_originals(reader):
                    return oa.finish_data(
                        root,
                        row,
                        record,
                        slot.capture.payload,
                        key=runtime_key,
                        validator=public_shapes
                        if public_validation is None
                        else public_validation.validator(row, root),
                        validation=public_validation,
                    )
            recipe = recipes[row["recipe_id"]]
            return oa.finish_control(
                root,
                record,
                slot.capture.payload,
                recipe,
                control_adapters[row["recipe_id"]],
                key=runtime_key,
            )

        def old_ledger(row):
            return (
                next(
                    (x for x in rebased["ledger"]() if x["work_id"] == row["work_id"]),
                    None,
                )
                if rebased
                else None
            )

        def unfinished(row):
            previous = old_ledger(row)
            return previous is None or previous["state"] in ("UNBEGUN", "RETRY_DUE")

        def pending_for(row, *, monitoring=False):
            previous = old_ledger(row)
            target = target_for(row)
            po.require(
                type(target) is bytes
                and 0 < len(target) <= target_bound
                and len(target) <= role_bounds[queue_role(row)]
            )
            if previous is not None and previous["state"] == "RETRY_DUE":
                return ps.Pending(
                    row,
                    target,
                    previous["charged_ordinals"][-1] + 1,
                    po.checked(
                        coordinator.opened_ns + previous["retry_delay_ms"] * 1_000_000
                    ),
                    monitoring,
                )
            return ps.Pending(row, target, 1, clock.now_ns(), monitoring)

        ordinary = iter(
            r
            for r in works()
            if r["block_id"] == block_id
            and queue_role(r) == "ORDINARY"
            and unfinished(r)
        )
        exhausted = ordinary_bound == 0
        reserved_cursor = 0
        futures = {}
        with ThreadPoolExecutor(
            max_workers=coordinator.capacity, thread_name_prefix="stage12-public-http"
        ) as pool:
            while True:
                operation = "ADMISSION"
                coordinator.tick()
                if pause_requested is not None and pause_requested():
                    coordinator.pause_pending = True
                if coordinator.stop_reason is None:
                    if (
                        not coordinator.pause_pending
                        and coordinator.monitored
                        and coordinator.monitoring_due()
                        and not any(
                            s.pending.monitor for s in coordinator.slots.values()
                        )
                        and not any(p.monitor for p in coordinator.pending)
                        and (
                            monitor_reserve == 0
                            or coordinator.can_refill(monitor_reserve)
                        )
                    ):
                        row = next(
                            (
                                r
                                for r in works()
                                if r["block_id"] == block_id
                                and r["work_id"] in block["reserved_control_ids"]
                                and r["work_id"] > reserved_cursor
                                and r["recipe_id"]
                                == profile["monitoring"]["refresh_recipe_id"]
                                and unfinished(r)
                            ),
                            None,
                        )
                        if row is None:
                            coordinator.terminal(
                                "IDENTITY_STALE", "IDENTITY_UNVERIFIABLE"
                            )
                        else:
                            reserved_cursor = row["work_id"]
                            coordinator.queue(pending_for(row, monitoring=True))
                    # Each active slot can return one retry. Keep that queue
                    # headroom, plus the priority monitoring entry, unoccupied.
                    while (
                        not coordinator.pause_pending
                        and not exhausted
                        and coordinator.can_refill(
                            ordinary_bound, monitor_reserve=monitor_reserve
                        )
                    ):
                        row = next(ordinary, None)
                        if row is None:
                            exhausted = True
                            break
                        coordinator.queue(pending_for(row))
                    slot = coordinator.admit(begin)
                    if slot is not None:
                        futures[slot.key] = pool.submit(worker, slot)
                    slot = None  # The coordinator/worker now own the reservation.
                next_slot = next(
                    (
                        s
                        for s in coordinator.slots.values()
                        if s.ticket == coordinator.finalized_ticket + 1
                        and s.key in futures
                        and futures[s.key].done()
                    ),
                    None,
                )
                if next_slot is not None:
                    try:
                        futures.pop(next_slot.key).result()
                        retry = coordinator.finalize(
                            next_slot, lambda slot=next_slot: finish(slot)
                        )
                        records.pop(next_slot.key, None)
                        if retry is not None:
                            coordinator.queue(retry)
                    except BaseException as error:
                        diagnostics.record(
                            "CAPTURE_FINALIZE",
                            error,
                            work_id=next_slot.key[0],
                            attempt=next_slot.key[1],
                            writer=writer,
                            deadline=finalization_deadline,
                        )
                        coordinator.audit_failed()
                    finally:
                        # The queue owns any returned retry. Keeping a local
                        # Pending/Slot would retain target bytes after closure
                        # preparation releases the coordinator's request caches.
                        retry = next_slot = None
                    continue
                failed = [
                    key
                    for key, future in futures.items()
                    if future.done() and future.exception() is not None
                ]
                for key in failed:
                    futures.pop(key)
                if coordinator.stop_reason:
                    if all(f.done() for f in futures.values()):
                        break
                elif (
                    exhausted and not coordinator.pending or coordinator.pause_pending
                ) and not coordinator.slots:
                    break
                if futures:
                    coordinator.wake.wait(
                        max(
                            0,
                            coordinator.next_wakeup_ns(coordinator.next_start_ns)
                            - clock.now_ns(),
                        )
                        / 1e9
                    )
                    coordinator.wake.clear()
                elif coordinator.pending:
                    waits = [
                        coordinator.next_start_ns,
                        coordinator.cooldown_until,
                        *(p.due_ns for p in coordinator.pending),
                    ]
                    clock.wait_until(coordinator.next_wakeup_ns(*waits))

        # Closure checks are explicit rows, globally paced, and use the same writer.
        if not coordinator.stop_reason and coordinator.monitored:
            coordinator.prepare_closure()
            row = next(
                (
                    r
                    for r in works()
                    if r["block_id"] == block_id
                    and r["kind"] == "SERVICE_CONTROL"
                    and r["recipe_id"] == profile["monitoring"]["closure_recipe_id"]
                    and unfinished(r)
                ),
                None,
            )
            if row is None:
                coordinator.terminal("IDENTITY_STALE", "IDENTITY_INTERVAL_NOT_CLOSED")
            else:
                coordinator.queue(pending_for(row, monitoring=True))
                closure_due = max(
                    clock.now_ns(),
                    coordinator.next_start_ns,
                    coordinator.cooldown_until,
                )
                while clock.now_ns() < closure_due:
                    clock.wait_until(min(closure_due, coordinator.next_wakeup_ns()))
                    coordinator.tick()
                    if coordinator.stop_reason:
                        break
                coordinator.tick()
                slot = coordinator.admit(begin)
                if slot is None:
                    coordinator.terminal(
                        "IDENTITY_STALE", "IDENTITY_INTERVAL_NOT_CLOSED"
                    )
                else:
                    worker(slot)
                    coordinator.finalize(slot, lambda: finish(slot))
                    records.pop(slot.key, None)
                    slot = None

        measurement_prefix = None

        def events():
            return (
                measurement_prefix.events()
                if measurement_prefix is not None
                else pj.read_events(output, po.digest(start), contract=po)
            )

        def verify_receipt(row, event_body):
            return verify_at(output, row, event_body)

        if coordinator.writer.failed.is_set() or any(
            s.ticket is None for s in coordinator.slots.values()
        ):
            # No false seal or invented controller state. Read-only recovery evidence.
            return incomplete()

        operation = "COMPARISON"

        def comparison_checkpoint():
            coordinator.yield_to_sample(finalization_deadline.check)

        with io.cooperative_io(comparison_checkpoint):
            finalization_deadline.check()
            writer.call(log.verify_storage)
            comparison_last_seq, comparison_head = writer.call(
                lambda: (log.seq, log.last_hash)
            )

            def comparison_events() -> Iterator[dict[str, Any]]:
                # Attempts are drained. Concurrent periodic records add no outcomes;
                # validate a pinned prefix, not an ever-growing chain on each pair.
                for event in events():
                    yield event
                    if event["seq"] == comparison_last_seq:
                        po.require(po.digest(event) == comparison_head)
                        return
                po.require(False, "PUBLIC_PROBE_EVIDENCE_WRITE_FAILED")

            from .stages.s12_public_work_index import WorkIndex

            work_index = WorkIndex(
                works,
                lambda key: io.metadata(io.read(output / "work" / f"{key:020d}.json")),
                plan,
            )

            def comparison_pairs():
                yield from work_index.pairs(block_id)

            def comparisons():
                pairs = iter(comparison_pairs())
                while batch := list(islice(pairs, 128)):
                    # Fixed metadata only: <=128 pairs / <=256 work IDs. Raw payloads
                    # and structural tuples are still verified one pair at a time.
                    ids = {r["work_id"] for pair in batch for r in pair}
                    finals = {}
                    for event in comparison_events():
                        b = event["body"]
                        if (
                            event["kind"] == "ATTEMPT_FINALIZED"
                            and b["work_id"] in ids
                            and b["outcome"]["value"] in c.SUCCESS
                        ):
                            po.require(b["work_id"] not in finals)
                            finals[b["work_id"]] = b
                    for predecessor, row in batch:
                        shapes = []
                        for current in (predecessor, row):
                            final = finals.get(current["work_id"])
                            if final is None:
                                shapes.append(None)
                                continue
                            terminal = verify_receipt(current, final)
                            root = locate_attempt(
                                output, current["work_id"], final["attempt"]
                            )
                            raw = response.decompress(
                                io.read(
                                    root
                                    / (
                                        audit.name_for(
                                            current["work_id"], final["attempt"]
                                        )
                                        + ".zst"
                                    )
                                ),
                                length=terminal["application_payload_bytes"],
                                expected_hash=bytes.fromhex(
                                    terminal["response_sha256"]
                                ),
                            )
                            shapes.append(
                                public_shapes(raw)
                                if public_validation is None
                                else public_validation.validator(current, root)(raw)
                            )
                        yield {
                            "first_work_id": predecessor["work_id"],
                            "next_work_id": row["work_id"],
                            "equal": shapes[0] is not None and shapes[0] == shapes[1],
                        }

            from .stages.s12_public_fresh_reads import FreshReads

            if coordinator.ap_enabled:
                from .stages.s12_public_history import Fresh as FreshReads

                if getattr(po, "PAGED_HISTORY", False):
                    from functools import partial
                    from .stages.s12_paged_history import Fresh

                    FreshReads = partial(Fresh, limits=plan["history_limits"])

            # Attempts are drained; the independent sampler writes only events.
            # Reuse checked original attempt bytes within this comparison stage,
            # then freshly re-read the entire exact attempt source set before
            # accepting its output identity. No stage survives into closure.
            with coordinator.safety:
                po.require(not coordinator.slots)
            with FreshReads(
                output / "attempts", check=comparison_checkpoint, reader_root=output
            ):
                comparison_hash = log.stream_array(
                    "repeat_comparison.json", comparisons()
                )
            # Drain/join the independent bounded sample slot before recording the
            # last sample. No sample may race report-prefix capture or writer release.
            po.require(
                coordinator.stop_sampling(), "PUBLIC_PROBE_EVIDENCE_WRITE_FAILED"
            )
            if not coordinator.ap_enabled:
                coordinator.resource("PERIODIC")

            # The final actual observation retains its existing ordering/window.
            # Freeze producer admission only after operations and sampler drain.
            def closure_state():
                with coordinator.safety:
                    po.require(
                        not coordinator.slots
                        and not coordinator.safety_barriers
                        and coordinator.sample_stop.is_set()
                        and (
                            coordinator.sample_thread is None
                            or not coordinator.sample_thread.is_alive()
                        )
                    )
                    return (
                        coordinator.state,
                        coordinator.state_id,
                        coordinator.last_ticket,
                        coordinator.stop_reason,
                        coordinator.pause_pending,
                    )

            closure_state()
            writer.freeze_closure()
            from .stages.s12_public_fresh_reads import FreshReads

            if coordinator.ap_enabled:
                from .stages.s12_public_history import Fresh as FreshReads

                if getattr(po, "PAGED_HISTORY", False):
                    from functools import partial
                    from .stages.s12_paged_history import Fresh

                    FreshReads = partial(Fresh, limits=plan["history_limits"])

            operation = "REPORT"
            with FreshReads(
                output,
                check=writer.closure_fence.check_live,
                boundary=writer.closure_fence.check,
                outputs={
                    "measurement_event_prefix.json",
                    "block_report.json",
                    "work_ledger.json",
                    "remaining_work_ledger.json",
                    "event_inventory.json",
                    "attempt_inventory.json",
                },
                events={f"events/{log.seq + ordinal:020d}.json" for ordinal in (1, 2)},
            ) as read_stage:
                closed_monitor = not coordinator.monitored or any(
                    e["kind"] == "MONITOR_RESULT" and e["body"]["interval_closed"]
                    for e in events()
                )
                operation = "REPORT"
                prefix = pj.MeasurementPrefix(log)
                if prefix.build(
                    closure_reserve=profile["resources"][
                        "fixed_campaign_disk_bound_bytes"
                    ]
                ):
                    measurement_prefix = prefix
                report = pr.block_report(
                    plan,
                    profile,
                    block_id,
                    events=events,
                    works=works,
                    verified_receipt=verify_receipt,
                    repeat_evidence=lambda: (
                        comparison_hash,
                        all(
                            r["equal"]
                            for r in pj.read_array(output / "repeat_comparison.json")
                        ),
                    ),
                    monitoring_closed=lambda: closed_monitor,
                    work_index=work_index,
                    contract=po,
                    campaign_start=start,
                )
                if measurement_prefix is not None:
                    measurement_prefix.verify_original()
                block_hash = writer.call(lambda: log.write("block_report.json", report))
                io.record_read_output(output / "block_report.json", block_hash)
                log.event(
                    "BLOCK_CLOSED",
                    {
                        "block_id": block_id,
                        "report_sha256": block_hash,
                        "result": report["status"],
                    },
                    closure=True,
                )
                operation = "RECONCILIATION"

                def ledger():
                    for row in recovery.work_ledger(
                        works, events, verify_receipt, batch_size=128, contract=po
                    ):
                        if (
                            report["counts"]["unprocessed_data"]["value"] == 0
                            and row["work_id"] in block["reserved_control_ids"]
                            and not row["charged_ordinals"]
                        ):
                            row["state"] = "UNUSED_RESERVED_CONTROL"
                        yield row

                ledger_hash = log.stream_array("work_ledger.json", ledger())

                def verified_ledger():
                    # This is a freshly derived, fsynced and reopened stream, never
                    # an authority token or an unbounded in-memory ledger cache.
                    # Each reuse checks every actual canonical byte before yielding
                    # and again while consuming; mutations cannot produce totality.
                    path = output / "work_ledger.json"
                    po.require(
                        po.manifest_digest(
                            pj.read_array(path, check=writer.check_deadline)
                        )
                        == ledger_hash
                    )
                    fingerprint = hashlib.sha256(b"[")
                    for i, row in enumerate(
                        pj.read_array(path, check=writer.check_deadline)
                    ):
                        po.validate_type(row, "WorkLedgerRow")
                        if i:
                            fingerprint.update(b",")
                        fingerprint.update(c.canonical(row)[:-1])
                        yield row
                    fingerprint.update(b"]\n")
                    po.require(fingerprint.hexdigest() == ledger_hash)

                total = recovery.required_work_complete(plan, works, verified_ledger)
                if (
                    not total
                    and not coordinator.stop_reason
                    and not coordinator.pause_pending
                    and block_id == len(plan["blocks"])
                ):
                    coordinator.terminal("BUDGET")
                disposition = (
                    coordinator.state
                    if coordinator.state
                    in ("STOPPED", "QUARANTINED", "RECOVERY_BLOCKED")
                    else "PAUSED_CLEAN"
                    if coordinator.pause_pending or block_id < len(plan["blocks"])
                    else "COMPLETED"
                )
                log.event(
                    "SEGMENT_CLOSE",
                    {
                        "disposition": disposition,
                        "closure_evidence_sha256": comparison_hash
                        if closed_monitor
                        else None,
                        "last_ticket": coordinator.last_ticket,
                    },
                    closure=True,
                )
                state = recovery.replay(events(), contract=po)

                remaining_hash = log.stream_array(
                    "remaining_work_ledger.json",
                    (
                        r
                        for r in verified_ledger()
                        if r["state"]
                        in ("UNBEGUN", "RETRY_DUE", "UNUSED_RESERVED_CONTROL")
                    ),
                )
                event_hash = log.stream_array(
                    "event_inventory.json",
                    pj.evidence_inventory(output, "events", contract=po),
                )
                attempt_hash = log.stream_array(
                    "attempt_inventory.json",
                    pj.evidence_inventory(output, "attempts", contract=po),
                )
                authority.require(
                    "writer_release",
                    writer_release_evidence,
                    {"start": start, "disposition": disposition},
                )
                operation = "CLOSURE"
                stored_bytes = log.prior_bytes + log.reconcile_storage()
                snapshot = {
                    "schema_version": po.SNAPSHOT,
                    "campaign_start_sha256": po.digest(start),
                    "segment_id": log.segment,
                    "last_event_seq": log.seq,
                    "last_event_sha256": log.last_hash,
                    "event_inventory_sha256": event_hash,
                    "attempt_inventory_sha256": attempt_hash,
                    "work_ledger_sha256": ledger_hash,
                    "controller": {
                        "state_id": coordinator.state_id,
                        "block_id": block_id,
                        "charged_data_attempts": coordinator.charged["DATA"],
                        "charged_control_attempts": coordinator.charged[
                            "SERVICE_CONTROL"
                        ],
                        "administrative_operations": 0,
                        "active_duration_ms": state["active_duration_ms"],
                        "stored_bytes": stored_bytes,
                        "event_count": log.seq,
                        "last_ticket": state["last_ticket"],
                        "consecutive_retryable": state["consecutive_retryable"],
                        "recent": state["recent"],
                        "overload_carry": state["overload_carry"],
                        "breaker_reason": state["breaker_reason"],
                        "cooldown_delay_ms": state["cooldown_delay_ms"],
                        "remaining_work_ledger_sha256": remaining_hash,
                        "monitoring_state": "CLOSED_VERIFIED"
                        if coordinator.monitored and closed_monitor
                        else "PUBLIC_GAPS_ONLY"
                        if not coordinator.monitored
                        else "UNVERIFIED",
                        "resume_eligible": disposition == "PAUSED_CLEAN",
                    },
                    "closure_evidence_sha256": comparison_hash
                    if closed_monitor
                    else None,
                    "writer_release_evidence_sha256": writer_release_evidence,
                    "sealed_utc": clock.utc(),
                    "disposition": disposition,
                }

                if coordinator.ap_enabled:
                    from .stages.s12_public_sampling import inspect

                    summary = inspect(
                        events,
                        profile,
                        start,
                        maximum_segments=plan["sampling_budget"]["maximum_segments"],
                        contract=po,
                    )[-1]
                    close_head = next(
                        po.digest(e)
                        for e in events()
                        if e["kind"] == "SAMPLING_CLOSE"
                        and e["seq"] == summary["close_event_seq"]
                    )
                    snapshot.update(
                        sampling_policy_sha256=po.POLICY_SHA,
                        sampling_close_event_sha256=close_head,
                        sampling=summary,
                        **(
                            po.assurance_fields()
                            if callable(getattr(po, "assurance_fields", None))
                            else {}
                        ),
                    )

                def original_closure_evidence():
                    # Fresh original event and receipt validation in each stage;
                    # no projection/cache is authority for snapshot publication.
                    po.verify_work_manifest(works, plan)
                    report_head = None

                    def original_events():
                        nonlocal report_head
                        for event in pj.read_events(
                            output, po.digest(start), contract=po
                        ):
                            body = event["body"]
                            if (
                                event["kind"] == "BLOCK_CLOSED"
                                and body["block_id"] == block_id
                            ):
                                report_head = body["report_sha256"]
                            if event["kind"] == "ATTEMPT_FINALIZED":
                                row = io.metadata(
                                    io.read(
                                        output / "work" / f"{body['work_id']:020d}.json"
                                    )
                                )
                                po.require(row["work_id"] == body["work_id"])
                                verify_receipt(row, body)
                            yield event

                    original = recovery.replay(original_events(), contract=po)
                    po.require(report_head is not None)
                    return original, report_head

                snap_hash = recovery.write_snapshot(
                    writer,
                    snapshot,
                    verify=original_closure_evidence,
                    log=log,
                    state_binding=closure_state,
                    read_stage=read_stage,
                )
                reports = {block_id: report}
                snapshots = [snap_hash]
                node = predecessor
                while node is not None:
                    previous = po.parse(io.read(node / "snapshot.json"), po.SNAPSHOT)
                    prior_report = io.metadata(io.read(node / "block_report.json"))
                    po.validate_type(prior_report, "BlockReport")
                    reports.setdefault(prior_report["block_id"], prior_report)
                    snapshots.append(po.digest(previous))
                    node = pj.predecessor_root(node)
                campaign = pr.campaign_report(
                    start,
                    event_inventory_sha256=event_hash,
                    attempt_inventory_sha256=attempt_hash,
                    snapshots=list(reversed(snapshots)),
                    blocks=[reports[k] for k in sorted(reports)],
                    sampling_segments=(
                        __import__(
                            po.__package__ + ".s12_public_sampling",
                            fromlist=["inspect"],
                        ).inspect(
                            lambda: pj.read_events(
                                output, po.digest(start), contract=po
                            ),
                            profile,
                            start,
                            maximum_segments=plan["sampling_budget"][
                                "maximum_segments"
                            ],
                            contract=po,
                        )
                        if coordinator.ap_enabled
                        else None
                    ),
                    disposition=disposition,
                    scientific_identity_verified=coordinator.monitored
                    and closed_monitor
                    and not coordinator.stop_reason,
                    reconciliation_reasons=[]
                    if disposition == "COMPLETED"
                    and len(reports) == len(plan["blocks"])
                    else ["INCOMPLETE_WORK"],
                    plan=plan,
                    contract=po,
                )
                writer.call(lambda: log.write("campaign_report.json", campaign))
                writer.release(
                    {
                        "writer_release_evidence_sha256": writer_release_evidence,
                        "snapshot_sha256": snap_hash,
                    }
                )
                return campaign
    except (Exception, KeyboardInterrupt) as error:
        diagnostics.record(
            operation, error, writer=writer, deadline=finalization_deadline
        )
        # Preserve the primary terminal reason if read-only derivation or later
        # cleanup also fails. An uncertain writer is never reused for a seal.
        if (
            not writer.failed.is_set()
            and not log.segment_closed
            and finalization_deadline.remaining_seconds() > 0
        ):
            try:
                log.event(
                    "STOP",
                    {
                        "why": "AUDIT_IO",
                        "primary_reason": coordinator.primary_reason,
                        "trigger_event_seq": None,
                    },
                    closure=True,
                )
            except BaseException as error:
                diagnostics.record(
                    "CLEANUP", error, writer=writer, deadline=finalization_deadline
                )
        coordinator.audit_failed()
        try:
            return incomplete()
        except BaseException as error:
            diagnostics.record(
                "RECONCILIATION", error, writer=writer, deadline=finalization_deadline
            )
            writer.abort()
            return pr.incomplete_report(
                start,
                plan,
                event_inventory_sha256=po.manifest_digest([]),
                attempt_inventory_sha256=po.manifest_digest([]),
                begins_lower_bound=0,
                contract=po,
            )
    finally:
        try:
            coordinator.stop_sampling()
        finally:
            from .stages.s12_public_timing import safe_call

            safe_call(timing_observer, "sampling", coordinator.sampling_snapshot())


def run_operations_block(profile, plan, start, **kwargs):
    if profile.get("schema_version") == "stage12_transport_operations_v4":
        from .stages import s12_paged_history as history

        with history.selected(plan["history_limits"]):
            return _run_operations_block(profile, plan, start, **kwargs)
    return _run_operations_block(profile, plan, start, **kwargs)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configuration", type=Path, required=True)
    parser.add_argument("--implementation-sha", required=True)
    args = parser.parse_args()
    try:
        require_goethe_nhr_slurm("stage12 public synthetic probe startup")
        config = io.metadata(io.read(args.configuration))
        result = run(
            config, args.implementation_sha, Path(__file__).resolve().parents[3]
        )
        print(c.canonical(result).decode("ascii"), end="")
        return 0 if result["status"] == "COMPLETED" else 1
    except c.Stage12Error as error:
        print(
            c.canonical(
                {
                    "status": "FAILED",
                    "failure_phase": "startup",
                    "failure_code": str(error),
                }
            ).decode("ascii"),
            end="",
        )
        return 1
    except Exception:
        print(
            '{"status":"FAILED","failure_phase":"startup","failure_code":"PUBLIC_PROBE_PREFLIGHT_FAILED"}'
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
