#!/usr/bin/env python3
"""Network-free Stage 12 contracts, privacy surface and synthetic memory check."""

from __future__ import annotations

import argparse
import gc
import math
import platform
import subprocess
import tracemalloc
from pathlib import Path
from typing import Any

from safe_geocoding_pipeline.preprocessing.stages import s12_assets as assets
from safe_geocoding_pipeline.preprocessing.stages import s12_probe as probe
from safe_geocoding_pipeline.preprocessing.stages import s12_response as response
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "7543b8bac4f2953aab311fb58f73dbcb62ba401b"


def validate_public_operations() -> dict[str, str]:
    """Opt-in O-r2 descriptor check only; no benchmark or execution authority."""
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_operations

    hashes = assets.verify(ROOT, public_operations=True)
    return {name: hashes[name] for name in s12_public_operations.SCHEMAS}


def validate() -> dict[str, Any]:
    hashes = assets.verify(ROOT)
    for relation in c.RELATIONS:
        c.require(
            tuple(c.schema(relation).names) == c.columns(relation), "S12_SCHEMA_INVALID"
        )
    diff = subprocess.check_output(
        ["git", "diff", "--name-status", BASELINE], cwd=ROOT, text=True
    )
    c.require(
        all(line.startswith("A\t") for line in diff.splitlines()),
        "S12_ACCEPTED_HISTORY_CHANGED",
    )
    paths = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT,
        )
        .decode()
        .split("\0")
    )
    candidates = sorted(
        set(path for path in paths if "stage12" in path or "/s12_" in path)
    )
    for name in candidates:
        path = ROOT / name
        c.require(
            path.suffix in (".py", ".md", ".json", ".sbatch") and not path.is_symlink(),
            "S12_TRACKED_DATA_INVALID",
        )
        c.require(path.stat().st_size < 1024 * 1024, "S12_TRACKED_DATA_INVALID")
    fixtures = probe.fixtures()
    c.require(
        len(fixtures) == 64 and len({row["fixture_id"] for row in fixtures}) == 64,
        "S12_FIXTURE_INVALID",
    )
    for launcher in (ROOT / "cluster/goethe_nhr").iterdir():
        if launcher.suffix in (".sh", ".sbatch"):
            subprocess.run(["bash", "-n", str(launcher)], check=True)
    return dict(
        status="PASS",
        contracts=len(hashes),
        relations=len(c.RELATIONS),
        frozen_documents=len(c.DESIGN_HASHES),
        public_synthetic_cases=len(fixtures),
        stage12_reviewed_text_files=len(candidates),
        C="UNSELECTED",
        T="UNSELECTED",
        N="UNSELECTED",
    )


def measure() -> dict[str, Any]:
    rows = []
    fixtures = (
        ("numbers", b'{"features":[],"x":[' + b"0," * 32767 + b"0]}"),
        ("objects", b'{"features":[],"x":[' + b"{}," * 32767 + b"{}]}"),
        ("strings", b'{"features":[],"x":[' + b'"abc",' * 32767 + b'"abc"]}'),
        ("keys", c.canonical({"features": [], **{str(i): i for i in range(16000)}})),
        ("unicode", ('{"features":[],"x":"' + "東京" * 65536 + '"}').encode()),
    )
    for name, raw in fixtures:
        gc.collect()
        tracemalloc.start()
        parsed = response.Parser(raw).parse()
        tree = response.structural(parsed.value)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        expansion = math.ceil(peak / len(raw))
        c.require(expansion <= 128, "S12_PARSER_RESERVATION_INSUFFICIENT")
        rows.append(
            dict(
                fixture=name,
                application_bytes=len(raw),
                peak_traced_bytes=peak,
                ceil_expansion=expansion,
            )
        )
        del parsed, tree
    return dict(
        scope="SYNTHETIC_PARSER_AND_STRUCTURAL_REPLAY",
        python=platform.python_version(),
        reservation_multiplier=128,
        measurements=rows,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--measure-synthetic", action="store_true")
    args = parser.parse_args()
    print(
        c.canonical(measure() if args.measure_synthetic else validate()).decode(),
        end="",
    )
