"""One explicitly authorized, bounded PUBLIC/SYNTHETIC SAFE capability job.

No accepted Stage 11 artifact path, protected payload reader, DEVELOPMENT
execution command, automatic resubmission or protected-policy selection exists.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import platform
import ssl
import os
import resource
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm

from .stages import s12_assets as assets
from .stages import s12_deployment as deployment
from .stages import s12_operations as ops
from .stages import s12_probe as probe
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
        config["secret_source_category"] == "APPROVED_RUNTIME_ENVIRONMENT"
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
    operations = ops.Operations()
    operations.validate(initial_probe=True)
    admission = ops.Admission(operations)
    start_ms = time.monotonic_ns() // 1_000_000
    observed: dict[tuple[int, int, str], tuple[Path, int, bytes]] = {}
    sizes: dict[str, dict[str, Any]] = {}
    prefix_pairs: dict[str, dict[str, int]] = {}
    endpoint_counts = {"FULL_TEXT": 0, "STRUCTURED": 0}
    dispatch_started = 0
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
            "source_category": "APPROVED_RUNTIME_ENVIRONMENT",
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
                io.write(output / (name + "_begin.json"), c.canonical(begin))
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
                    "payload_bytes": len(capture.payload)
                    if capture.payload is not None
                    else None,
                    "retry_after_seconds": capture.retry_after_seconds,
                    "retry_clock": capture.retry_after_audit.audit()
                    if capture.retry_after_audit
                    else None,
                }
                io.write(output / (name + "_finish.json"), c.canonical(finish))
                size_row["latency_ms"].append(capture.elapsed_ms)
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
                if capture.status != 200 or capture.payload is None:
                    raise c.Stage12Error(capture.reason)
                raw = capture.payload
                response.secret_guard(raw, key.value)
                raw_path = output / (name + ".zst")
                io.write(raw_path, response.compress(raw))
                decoded = response.decompress(
                    io.read(raw_path), length=len(raw), expected_hash=c.sha(raw)
                )
                report["failure_phase"] = "response_contract"
                features = public_shapes(decoded)
                c.require(
                    len(features) <= size
                    and capture.content_type in response.MEDIA
                    and capture.content_encoding in ("absent", "identity"),
                    "RESPONSE_CONTRACT_INVALID",
                )
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
    finally:
        for row in sizes.values():
            for field in ("latency_ms", "payload_bytes", "candidate_counts"):
                row[field] = aggregate(row[field])
        report.update(
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
    except Exception:
        print(
            '{"status":"FAILED","failure_phase":"startup","failure_code":"PUBLIC_PROBE_PREFLIGHT_FAILED"}'
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
