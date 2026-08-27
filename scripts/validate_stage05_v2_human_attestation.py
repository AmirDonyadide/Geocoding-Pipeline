#!/usr/bin/env python3
"""Validate a protected Stage 5 v2 human-review attestation without row output."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections import Counter
from pathlib import Path
from typing import Any, NoReturn, cast


TARGET_CANDIDATE_SHA = "97bd7fa74da358e81133ac4d38232931762d3e78"
IMPLEMENTATION_SHA = "cd0a5ae91c3602ec20e34f7c419f1ac76f0b9160"
EXPECTED_REVIEW_SUBSET = (
    "014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52"
)
STAGE05_REVIEW_ARTIFACT_SHA = (
    "be074cc2d3f188931eda9f60e51dc66117acee21ee45d24119044104f5c8e1e7"
)
CLASSIFICATIONS = frozenset(
    {
        "CORRECT_RECONSTRUCTION",
        "VALID_BUT_REDUNDANT_SOURCE_CONTENT",
        "QUESTIONABLE_BOUNDARY",
        "QUESTIONABLE_ORDER",
        "SEMANTIC_DAMAGE",
    }
)
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_RE = re.compile(r"^[0-9a-f]{40}$")


class AttestationFailure(RuntimeError):
    """A privacy-safe attestation validation failure."""


def fail(code: str) -> NoReturn:
    raise AttestationFailure(code)


def load_json(path: Path) -> dict[str, Any]:
    observed = path.stat(follow_symlinks=False)
    if path.is_symlink() or not stat.S_ISREG(observed.st_mode):
        fail("REGULAR_FILE_REQUIRED")
    if stat.S_IMODE(observed.st_mode) != 0o600:
        fail("OWNER_ONLY_FILE_REQUIRED")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail("JSON_OBJECT_REQUIRED")
    return cast(dict[str, Any], value)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def validate(template: dict[str, Any], attestation: dict[str, Any]) -> dict[str, Any]:
    expected_template_keys = {
        "attestation_version",
        "candidate_sha",
        "implementation_sha",
        "review_harness_sha",
        "fixed_500_fingerprint",
        "stage05_review_artifact_sha256",
        "qualitative_scope_fingerprint",
        "selected_row_count",
        "review_orders",
    }
    if set(template) != expected_template_keys:
        fail("ATTESTATION_TEMPLATE_FIELDS_INVALID")
    orders = template.get("review_orders")
    selected_count = template.get("selected_row_count")
    if (
        template.get("attestation_version") != "stage05_v2_human_review_attestation_v1"
        or template.get("candidate_sha") != TARGET_CANDIDATE_SHA
        or template.get("implementation_sha") != IMPLEMENTATION_SHA
        or template.get("fixed_500_fingerprint") != EXPECTED_REVIEW_SUBSET
        or template.get("stage05_review_artifact_sha256") != STAGE05_REVIEW_ARTIFACT_SHA
        or not isinstance(template.get("review_harness_sha"), str)
        or GIT_RE.fullmatch(cast(str, template["review_harness_sha"])) is None
        or not isinstance(template.get("qualitative_scope_fingerprint"), str)
        or SHA_RE.fullmatch(cast(str, template["qualitative_scope_fingerprint"]))
        is None
        or isinstance(selected_count, bool)
        or not isinstance(selected_count, int)
        or selected_count < 1
        or not isinstance(orders, list)
        or len(orders) != selected_count
        or len(set(orders)) != selected_count
        or any(
            isinstance(order, bool) or not isinstance(order, int) for order in orders
        )
    ):
        fail("ATTESTATION_TEMPLATE_INVALID")
    expected_attestation_keys = expected_template_keys - {"review_orders"} | {
        "attested_complete",
        "completed_at_utc",
        "classifications",
    }
    if set(attestation) != expected_attestation_keys:
        fail("ATTESTATION_FIELDS_INVALID")
    for name in expected_template_keys - {"review_orders"}:
        if attestation.get(name) != template.get(name):
            fail("ATTESTATION_BINDING_MISMATCH")
    classifications = attestation.get("classifications")
    if (
        attestation.get("attested_complete") is not True
        or not isinstance(attestation.get("completed_at_utc"), str)
        or not cast(str, attestation["completed_at_utc"]).endswith("Z")
        or not isinstance(classifications, list)
        or len(classifications) != selected_count
    ):
        fail("ATTESTATION_INCOMPLETE")
    observed: dict[int, str] = {}
    for raw in classifications:
        if not isinstance(raw, dict) or set(raw) != {"review_order", "classification"}:
            fail("ATTESTATION_CLASSIFICATION_INVALID")
        order = raw.get("review_order")
        classification = raw.get("classification")
        if (
            isinstance(order, bool)
            or not isinstance(order, int)
            or order in observed
            or not isinstance(classification, str)
            or classification not in CLASSIFICATIONS
        ):
            fail("ATTESTATION_CLASSIFICATION_INVALID")
        observed[order] = classification
    if set(observed) != set(cast(list[int], orders)):
        fail("ATTESTATION_SCOPE_INCOMPLETE")
    counts = Counter({name: 0 for name in CLASSIFICATIONS})
    counts.update(observed.values())
    return {
        "status": "STAGE_5_V2_HUMAN_REVIEW_ATTESTATION_VALID",
        "candidate_sha": TARGET_CANDIDATE_SHA,
        "implementation_sha": IMPLEMENTATION_SHA,
        "review_harness_sha": template["review_harness_sha"],
        "qualitative_scope_fingerprint": template["qualitative_scope_fingerprint"],
        "selected_row_count": selected_count,
        "classification_counts": dict(sorted(counts.items())),
        "questionable_boundary_count": counts["QUESTIONABLE_BOUNDARY"],
        "questionable_order_count": counts["QUESTIONABLE_ORDER"],
        "semantic_damage_count": counts["SEMANTIC_DAMAGE"],
    }


def write_result(path: Path, result: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        fail("OUTPUT_COLLISION")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(
            json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
        )
        stream.flush()
        os.fsync(stream.fileno())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--attestation", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        template = load_json(args.template)
        attestation = load_json(args.attestation)
        result = validate(template, attestation)
        result["template_sha256"] = sha256_file(args.template)
        result["attestation_sha256"] = sha256_file(args.attestation)
        write_result(args.output, result)
    except (AttestationFailure, OSError, UnicodeError, json.JSONDecodeError) as error:
        code = (
            str(error)
            if isinstance(error, AttestationFailure)
            else type(error).__name__
        )
        print(f"attestation_error={code}", file=sys.stderr)
        return 1
    print("status=STAGE_5_V2_HUMAN_REVIEW_ATTESTATION_VALID")
    print(f"selected_row_count={result['selected_row_count']}")
    counts = result["classification_counts"]
    for name in sorted(CLASSIFICATIONS):
        print(f"{name.lower()}={counts[name]}")
    print(f"attestation_sha256={result['attestation_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
