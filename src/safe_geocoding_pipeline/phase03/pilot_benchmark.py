from __future__ import annotations

import argparse
import json
import platform
import resource
import time
from collections.abc import Iterator, Sequence
from pathlib import Path

from .models import PilotCandidate
from .pilot_runner import (
    PILOT_CANDIDATE_STATE_SCHEMA_VERSION,
    PILOT_RUNNER_VERSION,
    ProductionSamplingContract,
    SQLitePilotCandidateStore,
)
from .sampler import PilotSamplingConfig


def _peak_rss_bytes() -> int:
    observed = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return observed if platform.system() == "Darwin" else observed * 1024


def _candidates(rows: int) -> Iterator[PilotCandidate]:
    import hashlib

    for index in range(rows):
        identity = hashlib.sha256(f"fictional-pilot-benchmark:{index}".encode()).digest()
        yield PilotCandidate(
            identity,
            {
                "primary_country_group": f"ASSIGNED:F{index % 40:02d}",
                "country_cohort": ("LARGE", "MEDIUM")[index % 2],
                "postcode_lexical": f"POSTCODE_CLASS_{index % 10}",
                "script_category": f"SCRIPT_CLASS_{index % 5}",
                "marker_po_box": f"PO_BOX_{index % 2}",
            },
            targeted_safety_case=index < 13,
        )


def run_synthetic_pilot_benchmark(rows: int, output_directory: Path) -> dict[str, int | float | str]:
    if rows < 12_000:
        raise ValueError("benchmark requires at least 12,000 fictional rows")
    output_directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    output_directory.chmod(0o700)
    store_path = output_directory / "candidate_state.sqlite3"
    config = PilotSamplingConfig(
        development_count=8_000,
        locked_evaluation_count=4_000,
        minimum_per_stratum=50,
        maximum_primary_stratum=500,
        primary_stratum="primary_country_group",
    )
    started = time.perf_counter()
    store = SQLitePilotCandidateStore(store_path, config=config)
    try:
        ingest_started = time.perf_counter()
        ingested = store.ingest(_candidates(rows), batch_size=1_000)
        ingest_seconds = time.perf_counter() - ingest_started
        select_started = time.perf_counter()
        selection = store.select(
            input_phase02_manifest_identity="fictional-benchmark-manifest",
            selection_timestamp="2026-01-01T00:00:00Z",
        )
        selection_seconds = time.perf_counter() - select_started
    finally:
        store.close()
    total_seconds = time.perf_counter() - started
    state_bytes = store_path.stat().st_size
    return {
        "status": "PASS",
        "data_scope": "SYNTHETIC_ONLY",
        "runner_version": PILOT_RUNNER_VERSION,
        "sampling_contract_version": ProductionSamplingContract().contract_version,
        "sampling_contract_fingerprint": ProductionSamplingContract().fingerprint(),
        "candidate_state_schema_version": PILOT_CANDIDATE_STATE_SCHEMA_VERSION,
        "synthetic_rows": ingested,
        "development_count": len(selection.development_ids),
        "locked_evaluation_count": len(selection.locked_evaluation_ids),
        "ingest_seconds": round(ingest_seconds, 6),
        "selection_seconds": round(selection_seconds, 6),
        "total_seconds": round(total_seconds, 6),
        "rows_per_second": round(rows / total_seconds, 3),
        "peak_rss_bytes": _peak_rss_bytes(),
        "candidate_state_bytes": state_bytes,
        "selection_state_bytes_upper_bound": config.total_count * 64,
        "temporary_disk_bytes": state_bytes,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic-only Phase 3 pilot-store benchmark")
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args(argv)
    print(
        json.dumps(
            run_synthetic_pilot_benchmark(args.rows, args.output_directory),
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
