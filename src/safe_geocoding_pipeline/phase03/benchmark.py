from __future__ import annotations

import argparse
import hashlib
import json
import resource
import time
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from .config import Phase03Config
from .constants import ELIGIBLE_FIELDS
from .engine import Phase03Engine
from .references import load_production_references
from .rules import load_rule_registry
from .writer import (
    revalidate_completed_pair,
    write_validate_and_promote_synthetic_shard,
)

SCENARIOS = (
    "STRUCTURED_HEAVY",
    "CANDIDATE_HEAVY",
    "AMBIGUITY_CONFLICT_HEAVY",
    "UNICODE_NATIVE_HEAVY",
    "OVERSIZED_SAFETY",
)
BENCHMARK_VERSION = "phase03_synthetic_benchmark_v1"


def _stable_id(scenario: str, ordinal: int) -> bytes:
    return hashlib.sha256(
        b"safe_geocoding_pipeline:phase03_synthetic_benchmark_row_v1\0"
        + scenario.encode()
        + ordinal.to_bytes(8, "big")
    ).digest()


def _base_row(scenario: str, ordinal: int) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": f"fictional-{scenario.lower()}-{ordinal:08d}",
        "street_address_line_1": "",
        "street_address_line_2": "",
        "street_address_line_3": "",
        "street_address_line_4": "",
        "street_address_line_1_native": "",
        "street_address_line_2_native": "",
        "street_address_line_3_native": "",
        "street_address_line_4_native": "",
        "postcode": "",
        "city": "",
        "region_in_country": "",
        "country_iso_code": "",
        "source_file": f"fictional_{scenario.lower()}.parquet",
        "source_logical_record_number": ordinal,
        "stable_source_row_id_v1": _stable_id(scenario, ordinal),
        "source_file_sha256": hashlib.sha256(
            b"fictional-source\0" + scenario.encode()
        ).digest(),
    }
    return row


def synthetic_population(scenario: str, rows: int) -> Iterator[dict[str, Any]]:
    if scenario not in SCENARIOS:
        raise ValueError("unknown synthetic benchmark scenario")
    for ordinal in range(1, rows + 1):
        row = _base_row(scenario, ordinal)
        variant = ordinal % 6
        if scenario == "STRUCTURED_HEAVY":
            row.update(
                postcode=f"{ordinal % 100_000:05d}",
                city="Exampleville",
                region_in_country="Demo Region",
                country_iso_code="US",
            )
        elif scenario == "CANDIDATE_HEAVY":
            row.update(
                street_address_line_1="Apt 7B Level 4",
                street_address_line_2="Building North Tower",
                street_address_line_3="Fictional Research GmbH",
                street_address_line_4="PO Box 77",
                postcode="00123",
                city="Exampleville",
                country_iso_code="US",
            )
        elif scenario == "AMBIGUITY_CONFLICT_HEAVY":
            row.update(
                street_address_line_1="Building Fictional Research GmbH",
                street_address_line_2="Apt 7 Unit 8",
                street_address_line_3="Namibia",
                street_address_line_4="former address",
                postcode="Na" if variant % 2 else "00123",
                city="Null" if variant % 3 else "Exampleville",
                country_iso_code="US",
            )
        elif scenario == "UNICODE_NATIVE_HEAVY":
            row.update(
                street_address_line_1="Fictional Café Suite 8",
                street_address_line_1_native="架空カフェ 8号室",
                street_address_line_2="Demo Tower",
                street_address_line_2_native="برج تجريبي",
                city="Exampleville",
                country_iso_code="JP",
            )
        else:
            lengths = (65_535, 65_536, 65_537, 262_145, 1_048_576, 1_048_577)
            row.update(
                street_address_line_1="X" * lengths[variant],
                postcode="00123",
                city="Exampleville",
                country_iso_code="US",
            )
        yield row


def _rss_mib() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return usage / (1024 * 1024) if usage > 10_000_000 else usage / 1024


def run_scenario(
    *,
    scenario: str,
    row_count: int,
    country_artifact: Path,
    output_directory: Path,
) -> dict[str, Any]:
    config = Phase03Config()
    country, scripts = load_production_references(
        country_artifact,
        expected_country_reference_id=config.country_reference_version,
        expected_unicode_reference_id=config.unicode_reference_version,
    )
    engine = Phase03Engine(
        config,
        load_rule_registry(),
        country_reference=country,
        script_reference=scripts,
        implementation_fingerprint=hashlib.sha256(BENCHMARK_VERSION.encode()).digest(),
        execution_scope="DEVELOPMENT",
    )
    core_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    candidate_count = 0
    input_utf8_bytes = 0
    started = time.perf_counter()
    for row in synthetic_population(scenario, row_count):
        input_utf8_bytes += sum(len(row[field].encode()) for field in ELIGIBLE_FIELDS)
        transformed = engine.transform(row)
        core_rows.append(transformed.core_row)
        evidence_rows.extend(transformed.evidence_rows)
        candidate_count += len(transformed.candidates)
    transform_seconds = time.perf_counter() - started

    scenario_dir = output_directory / scenario.lower()
    temporary = scenario_dir / ".in_progress"
    temporary.mkdir(parents=True, exist_ok=True, mode=0o700)
    core_path = scenario_dir / "core.parquet"
    evidence_path = scenario_dir / "evidence.parquet"
    write_started = time.perf_counter()
    result = write_validate_and_promote_synthetic_shard(
        core_rows=core_rows,
        evidence_rows=evidence_rows,
        temporary_core=temporary / "core.parquet.tmp",
        temporary_evidence=temporary / "evidence.parquet.tmp",
        final_core=core_path,
        final_evidence=evidence_path,
        config=config,
        metadata={
            "benchmark_version": BENCHMARK_VERSION,
            "benchmark_scenario": scenario,
            "data_classification": "FICTIONAL_SYNTHETIC_ONLY",
        },
    )
    write_validate_seconds = time.perf_counter() - write_started
    readback_started = time.perf_counter()
    revalidate_completed_pair(
        core_path=core_path,
        evidence_path=evidence_path,
        expected=result,
        config=config,
    )
    readback_seconds = time.perf_counter() - readback_started
    core_meta = pq.ParquetFile(core_path, page_checksum_verification=True).metadata
    evidence_meta = pq.ParquetFile(
        evidence_path, page_checksum_verification=True
    ).metadata
    total_seconds = transform_seconds + write_validate_seconds + readback_seconds
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "scenario": scenario,
        "synthetic_rows": row_count,
        "synthetic_input_utf8_bytes": input_utf8_bytes,
        "core_parquet_bytes": result.core_bytes,
        "evidence_rows": result.evidence_rows,
        "evidence_parquet_bytes": result.evidence_bytes,
        "evidence_rows_per_source_row": result.evidence_rows / row_count,
        "candidates_per_source_row": candidate_count / row_count,
        "transform_seconds": transform_seconds,
        "write_and_validation_seconds": write_validate_seconds,
        "independent_readback_seconds": readback_seconds,
        "total_seconds": total_seconds,
        "rows_per_second": row_count / total_seconds,
        "peak_rss_mib": _rss_mib(),
        "core_row_groups": core_meta.num_row_groups,
        "core_row_group_rows": [
            core_meta.row_group(index).num_rows
            for index in range(core_meta.num_row_groups)
        ],
        "evidence_row_groups": evidence_meta.num_row_groups,
        "evidence_row_group_rows": [
            evidence_meta.row_group(index).num_rows
            for index in range(evidence_meta.num_row_groups)
        ],
        "core_semantic_digest": result.core_semantic_digest,
        "evidence_semantic_digest": result.evidence_semantic_digest,
        "semantic_digest_validation": "PASS",
        "page_checksum_validation": "PASS",
        "temporary_peak_bytes_upper_bound": result.core_bytes + result.evidence_bytes,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run fictional-only Phase 3 performance scenarios"
    )
    parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    parser.add_argument("--rows", type=int, required=True)
    parser.add_argument("--country-artifact", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--metrics-path", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.rows < 1:
        raise ValueError("synthetic row count must be positive")
    metrics = run_scenario(
        scenario=args.scenario,
        row_count=args.rows,
        country_artifact=args.country_artifact,
        output_directory=args.output_directory,
    )
    if args.metrics_path is not None:
        args.metrics_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        args.metrics_path.write_text(
            json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        args.metrics_path.chmod(0o600)
    print(json.dumps(metrics, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
