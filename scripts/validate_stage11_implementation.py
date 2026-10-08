#!/usr/bin/env python3
"""Read-only design/schema/privacy checks; optional bounded invented benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from safe_geocoding_pipeline.preprocessing import stage11_cli as cli
from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_assets as assets
from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_io as io
from safe_geocoding_pipeline.preprocessing.stages import (
    s11_semantic_pipeline as pipeline,
)

ROOT = Path(__file__).resolve().parents[1]


def validate() -> dict[str, Any]:
    bindings = assets.verify(ROOT)
    assets.verify_implementation(ROOT)
    for path in c.DESIGN_DOCUMENTS:
        raw = subprocess.run(
            ["git", "show", c.DESIGN_SHA + ":" + path],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
        c.require((ROOT / path).read_bytes() == raw, "S11_INPUT_BINDING_INVALID")
    manifest = ROOT / "docs/scientific_assets/stage10_remediated_manifest_1785683.json"
    c.require(
        c.sha256_file(manifest)
        == "558298d7260199cc24f994d7480def9ad268aca057347f86ca41fad675a5a860",
        "S11_INPUT_BINDING_INVALID",
    )
    files = sorted(
        [
            *ROOT.glob("src/safe_geocoding_pipeline/preprocessing/stages/s11*.py"),
            ROOT / "src/safe_geocoding_pipeline/preprocessing/stage11_cli.py",
        ]
    )
    for path in files:
        content = path.read_text()
        c.require(
            not any(
                re.search(pattern, content)
                for pattern in (
                    r"\bimport pandas\b",
                    r"\bimport requests\b",
                    r"\bimport httpx\b",
                    r"\blist_agg\s*\(",
                    r"\.casefold\(",
                    r"\.strip\(\).*core",
                )
            ),
            "S11_PRIVACY_GUARD_FAILURE",
        )
    subprocess.run(
        ["bash", "-n", str(ROOT / "cluster/goethe_nhr/stage11_development.sbatch")],
        check=True,
    )
    vectors = json.loads(
        (ROOT / "tests/fixtures/stage11_canonical_vectors.json").read_bytes()
    )
    for row in vectors:
        raw = c.core_bytes(row["core"])
        c.require(
            raw.hex() == row["hex"]
            and hashlib.sha256(raw).hexdigest() == row["sha256"],
            "S11_ENCODING_INVALID",
        )
    return {
        "status": "PASS",
        "bindings": bindings,
        "frozen_design_documents": 4,
        "core_fields": len(c.FIELDS),
        "relations": list(c.RELATIONS),
        "byte_vectors": len(vectors),
    }


def measure() -> dict[str, Any]:
    # This helper imports only invented fixture construction. There is no CLI
    # parameter accepting a protected artifact or alternate source directory.
    sys.path.insert(0, str(ROOT / "tests"))
    from stage11_synthetic import fixture

    with tempfile.TemporaryDirectory(prefix="stage11-synthetic-") as name:
        root = Path(name).resolve()
        started = time.monotonic_ns()
        inputs = fixture(root / "input", contexts=8192, varied=True)
        for directory in ("local", "durable"):
            (root / directory).mkdir(mode=0o700)
        monitor = cli.StorageMonitor(root / "local")
        monitor.thread.start()
        generation_start = time.monotonic_ns()
        try:
            result = pipeline.run(
                inputs,
                root / "candidate",
                root / "local",
                root / "durable",
                assets.identifiers(ROOT),
                "1" * 40,
                unit_rows=2048,
            )
        finally:
            monitor.close()
        report = c.decode_json((result.path / io.SUMMARY_NAME).read_bytes())
        return {
            "record_version": "stage11_synthetic_resource_measurement_v1",
            "input_kind": "INVENTED_ONLY",
            "runtime": pipeline.runtime(),
            "hypotheses": inputs.population["hypotheses"],
            "unique_requests": report["request_counts"]["unique_requests"],
            "total_elapsed_ns": time.monotonic_ns() - started,
            "pipeline_elapsed_ns": time.monotonic_ns() - generation_start,
            "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            * (1 if sys.platform == "darwin" else 1024),
            "local_terminal_bytes": cli.tree_bytes(root / "local"),
            "local_sampled_high_water_bytes": monitor.maximum,
            "local_storage_samples": monitor.samples,
            "input_bytes": cli.tree_bytes(root / "input"),
            "durable_checkpoint_bytes": cli.tree_bytes(root / "durable"),
            "artifact_bytes": cli.tree_bytes(result.path),
            "checkpoints": result.manifest["operational_provenance"]["checkpoints"],
            "logical_sha256": result.manifest["logical_sha256"],
            "status": "PASS",
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--measure-synthetic", action="store_true")
    args = parser.parse_args()
    print(
        c.canonical(measure() if args.measure_synthetic else validate()).decode(
            "ascii"
        ),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
