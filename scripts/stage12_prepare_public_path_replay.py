"""Canonical TEST_ONLY public-adapter replay input; no provider or service."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path

from safe_geocoding_pipeline.preprocessing.stages import (
    s12_public_matrix as matrix,
    s12_public_operations as operations,
    s12_public_response as validation,
    s12_public_runtime as runtime,
    s12_response as response,
    s12_retrieval_contract as contract,
)

SCOPE = "TEST_ONLY_REAL_PUBLIC_ADAPTER_REPLAY_NO_SERVICE_AUTHORITY"
VERSION = "stage12_public_path_replay_input_v1"
LIMITS = {
    "seconds": 7200,
    "artifact_bytes": 256 * 2**20,
    "creations": 50000,
    "rss_bytes": 768 * 2**20,
    "attempts": 171,
    "response_bytes": 65536,
}
SCENARIOS = [
    {
        "name": "disabled_first64",
        "label": "size01_full_text",
        "observer": False,
        "minimum_periodic": 1817,
        "expected": "COMPLETE",
    },
    {
        "name": "enabled_first64",
        "label": "size01_full_text",
        "observer": True,
        "minimum_periodic": 1817,
        "expected": "COMPLETE",
    },
    {
        "name": "enabled_size40",
        "label": "size40_deep",
        "observer": True,
        "minimum_periodic": 1572,
        "expected": "COMPLETE",
    },
    {
        "name": "enabled_controls",
        "label": "additional_parameter_checks",
        "observer": True,
        "minimum_periodic": 200,
        "expected": "COMPLETE",
    },
    {
        "name": "enabled_validation_failure",
        "label": "size01_full_text",
        "observer": True,
        "minimum_periodic": 0,
        "expected": "INCOMPLETE_MALFORMED_WORK_2",
    },
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--template-sha256", required=True)
    parser.add_argument("--public-prefix", type=Path, required=True)
    parser.add_argument("--prior-replay-input", type=Path, required=True)
    parser.add_argument("--prior-input-sha256", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--review-report", type=Path, required=True)
    parser.add_argument("--source-inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    assert len(args.source_sha) == 40 and all(
        c in "0123456789abcdef" for c in args.source_sha
    )
    template_raw = args.template.read_bytes()
    assert hashlib.sha256(template_raw).hexdigest() == args.template_sha256
    old_raw = args.prior_replay_input.read_bytes()
    assert hashlib.sha256(old_raw).hexdigest() == args.prior_input_sha256
    config = json.loads(template_raw)
    records = {
        name: contract.canonical(
            {
                "scope": SCOPE,
                "role": name,
                "claim": "TEST_ONLY_NOT_AN_OPERATOR_OR_INSTITUTIONAL_ATTESTATION",
            }
        ).decode()
        for name in config["sources"]
    }
    config["sources"] = {
        name: contract.sha(raw.encode()).hex() for name, raw in records.items()
    }
    start = datetime.now(timezone.utc)
    config["window_start"] = start.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    config["window_end"] = (start + timedelta(hours=24)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    config["task_id"] = contract.sha((SCOPE + config["window_start"]).encode()).hex()
    config["output_directory"] = "/TEST_ONLY_NO_LIVE_OUTPUT"
    config["transport"]["approved_ip"] = "192.0.2.1"
    config["transport"]["configuration_evidence_sha256"] = config["sources"][
        "transport"
    ]
    profile = deepcopy(config["campaigns"][0]["profile"])
    profile["policy_freeze_record_sha256"] = config["sources"]["policy_freeze"]
    profile["operator_allowance"].update(
        record_sha256=config["sources"]["operator"],
        valid_from=config["window_start"],
        valid_until=config["window_end"],
    )
    profile["states"][0]["evidence_sha256"] = config["sources"]["selection"]
    assert profile["states"][0]["rate"] == {"num": 1, "den": 1}
    profile["monitoring"]["gaps_record_sha256"] = config["sources"]["selection"]
    profile["transport_profile_sha256"] = operations.digest(config["transport"])
    profile["resources"].update(
        capacity_basis_sha256=config["sources"]["selection"],
        resource_review_sha256=config["sources"]["selection"],
    )
    config["resources"] = deepcopy(profile["resources"])
    config["capability"] = matrix.binding(config["sources"]["size_allowance"])
    config["campaigns"] = matrix.build_campaigns(
        profile,
        window_start=config["window_start"],
        window_end=config["window_end"],
        selection_sha256=config["sources"]["selection"],
    )
    runtime.validate_config(config)
    cases = []
    for work in config["campaigns"][0]["work"]:
        name = f"call_{work['work_id']:04d}_attempt_1"
        directory = args.public_prefix / "size01_full_text/attempts" / name
        capture = json.loads((directory / (name + "_capture.json")).read_bytes())[
            "capture"
        ]
        frame = (directory / (name + ".zst")).read_bytes()
        raw = response.decompress(
            frame,
            length=capture["application_payload_bytes"],
            expected_hash=bytes.fromhex(capture["response_sha256"]),
        )
        validation.shapes(raw, work, version=validation.CORPUS_VERSION)
        assert len(raw) <= LIMITS["response_bytes"]
        cases.append(
            {
                "label": "size01_full_text",
                "work_id": work["work_id"],
                "raw_utf8": raw.decode(),
                "payload_sha256": contract.sha(raw).hex(),
                "compressed_source_sha256": contract.sha(frame).hex(),
                "origin": "RETAINED_JOB_1809257_EXACT_RESPONSE_REPLAY",
            }
        )
    prior = {(r["fixture_id"], r["size"]): r for r in json.loads(old_raw)["responses"]}
    deep = next(x for x in config["campaigns"] if x["label"] == "size40_deep")
    for work in deep["work"]:
        row = prior[(work["fixture_id"], work["result_limit"])]
        raw = row["raw_utf8"].encode()
        validation.shapes(raw, work, version=validation.CORPUS_VERSION)
        assert len(raw) <= LIMITS["response_bytes"]
        cases.append(
            {
                "label": "size40_deep",
                "work_id": work["work_id"],
                "raw_utf8": row["raw_utf8"],
                "payload_sha256": contract.sha(raw).hex(),
                "origin": "RETAINED_PUBLIC_TEMPLATE_REPEATED_SYNTHETICALLY_NOT_HISTORICAL_REPETITION",
            }
        )
    assert len(cases) == 96
    review_raw = args.review_report.read_bytes()
    assert 0 < len(review_raw) <= 2**20
    inventory = json.loads(args.source_inventory.read_bytes())
    names = sorted(
        {entry["path"] for entry in inventory["source_files"]}
        | {
            "src/safe_geocoding_pipeline/preprocessing/stages/s12_public_checkpoints.py",
            "src/safe_geocoding_pipeline/preprocessing/stages/s12_public_timing.py",
        }
    )
    assert all(
        not Path(name).is_absolute() and ".." not in Path(name).parts for name in names
    )
    value = {
        "scope": SCOPE,
        "version": VERSION,
        "source_sha": args.source_sha,
        "limits": LIMITS,
        "scenarios": SCENARIOS,
        "configuration": config,
        "test_only_authority_records": records,
        "response_cases": cases,
        "authority_source_files": names,
        "code_review_report_utf8": review_raw.decode(),
        "code_review_report_sha256": contract.sha(review_raw).hex(),
        "synthetic_delay_ms": {"ordinary": 5, "every_eighth_work": 20},
        "interpretation": "No live provider/authority claim. Actual public adapters read TEST_ONLY records; retained bytes, invented control/failure bodies and fake transport/key only.",
        "source_inputs": {
            "template_sha256": args.template_sha256,
            "prior_replay_input_sha256": args.prior_input_sha256,
        },
    }
    raw = contract.canonical(value)
    fd = os.open(
        args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    print(
        json.dumps(
            {"input_sha256": contract.sha(raw).hex(), "bytes": len(raw), "scope": SCOPE}
        )
    )


if __name__ == "__main__":
    main()
