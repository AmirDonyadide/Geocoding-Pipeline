"""Prepare v2 canonical replay input; retained public bodies, synthetic authority.

Prospective 7,200-second selection only. Historical v1 input and outcomes retain
exactly their original bytes and 600-second allowance.
"""

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

from safe_geocoding_pipeline.preprocessing.stages import (
    s12_public_matrix as matrix,
    s12_public_operations as operations,
    s12_public_response as validation,
    s12_retrieval_contract as contract,
    s12_response as response,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--retained", type=Path, required=True)
    parser.add_argument("--configuration", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert len(args.source_sha) == 40 and all(
        x in "0123456789abcdef" for x in args.source_sha
    )
    scope = "INVENTED_SYNTHETIC_MATRIX_REPLAY_NO_SERVICE_AUTHORITY"
    config = json.loads(args.configuration.read_bytes())
    assert config["version"] == matrix.VERSION
    synthetic = {
        role: contract.sha(contract.canonical({"scope": scope, "role": role})).hex()
        for role in config["sources"]
    }
    config["sources"] = synthetic
    config["window_start"] = "2026-01-01T00:00:00.000000Z"
    config["window_end"] = "2026-01-02T00:00:00.000000Z"
    config["task_id"] = contract.sha(scope.encode()).hex()
    config["output_directory"] = "/SYNTHETIC_NOT_SERVICE_OUTPUT"
    config["transport"]["approved_ip"] = "192.0.2.1"
    config["transport"]["configuration_evidence_sha256"] = synthetic["transport"]
    config["capability"] = matrix.binding(synthetic["size_allowance"])
    profile = deepcopy(config["campaigns"][0]["profile"])
    profile["policy_freeze_record_sha256"] = synthetic["policy_freeze"]
    profile["operator_allowance"].update(
        record_sha256=synthetic["operator"],
        valid_from=config["window_start"],
        valid_until=config["window_end"],
    )
    profile["states"][0].update(
        rate={"num": 20, "den": 1}, evidence_sha256=synthetic["selection"]
    )
    profile["monitoring"]["gaps_record_sha256"] = synthetic["selection"]
    profile["transport_profile_sha256"] = operations.digest(config["transport"])
    profile["resources"].update(
        capacity_basis_sha256=synthetic["selection"],
        resource_review_sha256=synthetic["selection"],
    )
    config["resources"] = deepcopy(profile["resources"])
    config["campaigns"] = matrix.build_campaigns(
        profile,
        window_start=config["window_start"],
        window_end=config["window_end"],
        selection_sha256=synthetic["selection"],
    )
    matrix.validate_matrix(config)
    responses = {}
    sources = []
    for item in config["campaigns"]:
        if item["plan"]["budgets"]["data_observations"] == 0:
            continue
        root = args.retained / item["label"]
        for work in item["work"]:
            key = (work["fixture_id"], work["result_limit"])
            name = f"call_{work['work_id']:04d}_attempt_1"
            raw_path = root / "attempts" / name / (name + ".zst")
            capture = json.loads(
                (root / "attempts" / name / (name + "_capture.json")).read_bytes()
            )["capture"]
            raw = response.decompress(
                raw_path.read_bytes(),
                length=capture["application_payload_bytes"],
                expected_hash=bytes.fromhex(capture["response_sha256"]),
            )
            assert 0 < len(raw) <= 65536
            if key in responses:
                # Retained response metadata may differ across repetitions;
                # replay explicitly uses repetition zero and preserves bytes.
                assert validation.shapes(
                    responses[key], work, version=validation.CORPUS_VERSION
                ) == validation.shapes(raw, work, version=validation.CORPUS_VERSION)
            else:
                responses[key] = raw
                sources.append(
                    {
                        "fixture_id": key[0],
                        "size": key[1],
                        "source_payload_sha256": hashlib.sha256(raw).hexdigest(),
                        "compressed_source_sha256": hashlib.sha256(
                            raw_path.read_bytes()
                        ).hexdigest(),
                        "source_relative": str(raw_path.relative_to(args.retained)),
                    }
                )
    assert len(responses) == 288
    value = {
        "scope": scope,
        "version": "stage12_complete_matrix_synthetic_input_v2",
        "source_sha": args.source_sha,
        "limits": {
            "seconds": 7200,
            "bytes": 256 * 2**20,
            "files": 50000,
            "rss_bytes": 768 * 2**20,
            "attempts": 584,
            "synthetic_rate": 20,
            "minimum_periodic_per_phase": 200,
            "minimum_periodic_size40": 900,
        },
        "checkpoints": {
            "interval_ms": 5000,
            "max_files": 1500,
            "max_file_bytes": 32768,
            "ring_records": 4096,
            "records_per_checkpoint": 128,
        },
        "configuration": config,
        "responses": [
            {"fixture_id": fixture, "size": size, "raw_utf8": raw.decode("utf-8")}
            for (fixture, size), raw in sorted(responses.items())
        ],
        "response_sources": sorted(
            sources, key=lambda row: (row["fixture_id"], row["size"])
        ),
        "interpretation": "Retained public bodies replayed by synthetic transport; controls invented; no historical evidence is modified or adopted as a new service campaign.",
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
            {
                "path": str(args.output),
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    )


if __name__ == "__main__":
    main()
