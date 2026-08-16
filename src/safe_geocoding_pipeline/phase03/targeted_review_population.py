from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

import pyarrow.parquet as pq

from ..phase02.fingerprints import JsonValue, canonical_json_bytes
from .constants import (
    CORE_COLUMNS,
    PARSER_VERSION_V2_1,
    PARSER_VERSION_V3_1,
    RULE_REGISTRY_VERSION_V3,
    RULE_REGISTRY_VERSION_V4,
)
from .pilot_runner import read_identity_set
from .schema import exact_core_schema_matches, exact_evidence_schema_matches
from .validation import (
    validate_core_evidence_relationship,
    validate_core_rows,
    validate_evidence_rows,
)


REPAIRED_TARGETED_REVIEW_POPULATION_VERSION: Final = (
    "phase03_parser_v3_targeted_review_population_v2_repaired"
)
REPAIRED_ITERATION_ID: Final = (
    "phase03_development_country_method_repair_20260816T001155Z_1749448_e4a47253"
)
REPAIRED_JOB_ID: Final = "1749448"
REPAIRED_EXECUTION_COMMIT: Final = "e4a4725399a635476e7d97adcc8e446a592404cd"
REPAIRED_BASELINE_CONFIGURATION_FINGERPRINT: Final = (
    "25962a126cd5d30c13607bd564aa250e91096e6961745670772a1ce31b76ac4d"
)
REPAIRED_EXPERIMENTAL_CONFIGURATION_FINGERPRINT: Final = (
    "50e06ad6d7ad428811bdefe30ed6ef7e0d6b9eacbbbdce9a53c6809fd812333a"
)
REPAIRED_DEVELOPMENT_IDENTITY_ORDER_DIGEST: Final = (
    "4c3d34efd77b1af0774bd7eab0893c1e826ffd672d4fc13fc943bff1c4da1666"
)
EXPERIMENTAL_RULE_IDS: Final = (
    "HOUSE_NUMBER_EMBEDDED_DESIGNATOR_EXPERIMENT_V4",
    "STREET_EMBEDDED_DESIGNATOR_EXPERIMENT_V4",
)
SCIENTIFIC_CORE_FIELDS: Final = CORE_COLUMNS[5:41]
_COMMIT = re.compile(r"[0-9a-f]{40}")
_LOWER_HEX_64 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class ArtifactPin:
    sha256: str
    size_bytes: int


REPAIRED_ARTIFACT_PINS: Final = {
    "development_payload": ArtifactPin(
        "dc78fd5c814739008a9ce24e91c66bf7c1121898b06ce2dfc53b0620b07a3cb1",
        7_631_865,
    ),
    "development_identities": ArtifactPin(
        "cab12eb1c1c2f61b8bbc5b53dff604e7569233518e5fb3c88467d848e648d71a",
        256_414,
    ),
    "baseline_core": ArtifactPin(
        "644b22865486c27ecb7bd15297fc131a7fa282758fb245bc8c6e885dacfecaf5",
        611_090,
    ),
    "baseline_evidence": ArtifactPin(
        "0f7ddae89755f2d8c6d2973e09be4670e851fb58867d8233998d10aa23443baa",
        551_140,
    ),
    "experimental_core": ArtifactPin(
        "1c6bc7ba74003b7910d3d83ce37e579e6182f0a4d227aea528b10165c2d50927",
        611_424,
    ),
    "experimental_evidence": ArtifactPin(
        "89080a0656eb77b5813acd7735d8721370fa8dbca9ae71cde88aed9cc54b10fb",
        552_394,
    ),
    "repair_success": ArtifactPin(
        "5a8535984fe8bfce2dcf1e7dd8ec07c4478717490e17b8ce3ea4411a37df16e9",
        1_388,
    ),
    "repair_comparison": ArtifactPin(
        "2964f134ecc98994e9b6ee89a23766c2531224e960f0506691dbf1f94857df3f",
        7_260,
    ),
}


@dataclass(frozen=True, slots=True)
class PopulationExpectation:
    development_rows: int
    scientific_change_rows: int
    experimental_evidence_rows: int
    overlap_rows: int
    changed_only_rows: int
    evidence_only_rows: int
    union_rows: int
    candidate_groups_per_rule: int
    selected_candidate_groups_per_rule: int


REPAIRED_POPULATION_EXPECTATION: Final = PopulationExpectation(
    development_rows=8_000,
    scientific_change_rows=9,
    experimental_evidence_rows=11,
    overlap_rows=9,
    changed_only_rows=0,
    evidence_only_rows=2,
    union_rows=11,
    candidate_groups_per_rule=22,
    selected_candidate_groups_per_rule=9,
)


@dataclass(frozen=True, slots=True)
class TargetedPopulation:
    changed_ids: frozenset[bytes]
    evidence_ids: frozenset[bytes]
    population: tuple[bytes, ...]
    country_parse_method_only_rows: int
    country_parse_method_changed_rows: int
    rule_candidate_groups: Mapping[str, int]
    rule_selected_candidate_groups: Mapping[str, int]

    @property
    def overlap_rows(self) -> int:
        return len(self.changed_ids & self.evidence_ids)

    @property
    def changed_only_rows(self) -> int:
        return len(self.changed_ids - self.evidence_ids)

    @property
    def evidence_only_rows(self) -> int:
        return len(self.evidence_ids - self.changed_ids)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reject_locked_path(path: Path) -> None:
    if any("locked" in part.casefold() for part in path.parts):
        raise ValueError("LOCKED paths are prohibited in targeted DEVELOPMENT review")


def read_core(path: Path) -> list[dict[str, Any]]:
    parquet = pq.ParquetFile(path, page_checksum_verification=True, pre_buffer=True)
    if not exact_core_schema_matches(parquet.schema_arrow):
        raise ValueError("targeted-review core schema mismatch")
    rows = cast(list[dict[str, Any]], parquet.read(use_threads=False).to_pylist())
    validate_core_rows(rows)
    return rows


def read_evidence(path: Path) -> list[dict[str, Any]]:
    parquet = pq.ParquetFile(path, page_checksum_verification=True, pre_buffer=True)
    if not exact_evidence_schema_matches(parquet.schema_arrow):
        raise ValueError("targeted-review evidence schema mismatch")
    rows = cast(list[dict[str, Any]], parquet.read(use_threads=False).to_pylist())
    validate_evidence_rows(rows)
    return rows


def development_identity_order_digest(
    rows: Sequence[Mapping[str, Any]],
) -> str:
    digest = hashlib.sha256(
        b"safe_geocoding_pipeline:phase03_development_comparison_identity_v1\0"
    )
    for ordinal, row in enumerate(rows, start=1):
        digest.update(ordinal.to_bytes(8, "big"))
        digest.update(bytes(row["stable_source_row_id_v1"]))
    digest.update(len(rows).to_bytes(8, "big"))
    return digest.hexdigest()


def population_digest(identities: Sequence[bytes]) -> str:
    digest = hashlib.sha256(
        b"safe_geocoding_pipeline:phase03_parser_v3_targeted_population_v1\0"
    )
    for ordinal, identity in enumerate(sorted(identities), start=1):
        digest.update(ordinal.to_bytes(8, "big"))
        digest.update(identity)
    digest.update(len(identities).to_bytes(8, "big"))
    return digest.hexdigest()


def compute_targeted_population(
    baseline: Sequence[Mapping[str, Any]],
    experimental: Sequence[Mapping[str, Any]],
    experimental_evidence: Sequence[Mapping[str, Any]],
) -> TargetedPopulation:
    """Compute the exact protected-review A union B population."""
    if len(baseline) != len(experimental):
        raise ValueError("targeted-review core row count mismatch")
    changed_ids: set[bytes] = set()
    country_method_only_rows = 0
    country_method_changed_rows = 0
    for before, after in zip(baseline, experimental, strict=True):
        if before["stable_source_row_id_v1"] != after["stable_source_row_id_v1"]:
            raise ValueError("targeted-review core identity/order mismatch")
        changed_fields = {
            field for field in SCIENTIFIC_CORE_FIELDS if before[field] != after[field]
        }
        if changed_fields:
            changed_ids.add(bytes(before["stable_source_row_id_v1"]))
        if "country_parse_method" in changed_fields:
            country_method_changed_rows += 1
        if changed_fields == {"country_parse_method"}:
            country_method_only_rows += 1

    evidence_ids = {
        bytes(row["stable_source_row_id_v1"])
        for row in experimental_evidence
        if row["rule_id"] in EXPERIMENTAL_RULE_IDS
    }
    groups: dict[tuple[bytes, int], Mapping[str, Any]] = {}
    for row in experimental_evidence:
        if row["rule_id"] not in EXPERIMENTAL_RULE_IDS:
            continue
        key = (bytes(row["stable_source_row_id_v1"]), int(row["evidence_id"]))
        existing = groups.setdefault(key, row)
        if existing["rule_id"] != row["rule_id"] or bool(existing["selected"]) != bool(
            row["selected"]
        ):
            raise ValueError("experimental evidence group is internally inconsistent")
    candidate_groups = {
        rule_id: sum(row["rule_id"] == rule_id for row in groups.values())
        for rule_id in EXPERIMENTAL_RULE_IDS
    }
    selected_groups = {
        rule_id: sum(
            row["rule_id"] == rule_id and bool(row["selected"])
            for row in groups.values()
        )
        for rule_id in EXPERIMENTAL_RULE_IDS
    }
    population = tuple(sorted(changed_ids | evidence_ids))
    return TargetedPopulation(
        changed_ids=frozenset(changed_ids),
        evidence_ids=frozenset(evidence_ids),
        population=population,
        country_parse_method_only_rows=country_method_only_rows,
        country_parse_method_changed_rows=country_method_changed_rows,
        rule_candidate_groups=candidate_groups,
        rule_selected_candidate_groups=selected_groups,
    )


def validate_population_expectation(
    population: TargetedPopulation, expectation: PopulationExpectation
) -> None:
    observed = (
        len(population.changed_ids),
        len(population.evidence_ids),
        population.overlap_rows,
        population.changed_only_rows,
        population.evidence_only_rows,
        len(population.population),
    )
    expected = (
        expectation.scientific_change_rows,
        expectation.experimental_evidence_rows,
        expectation.overlap_rows,
        expectation.changed_only_rows,
        expectation.evidence_only_rows,
        expectation.union_rows,
    )
    if observed != expected:
        raise ValueError(
            "REPAIRED_TARGETED_REVIEW_POPULATION_MISMATCH: "
            f"changed={observed[0]} evidence={observed[1]} overlap={observed[2]} "
            f"changed_only={observed[3]} evidence_only={observed[4]} "
            f"union={observed[5]}"
        )
    if population.changed_ids - population.evidence_ids:
        raise ValueError("scientific-change identity lacks experimental V4 evidence")
    if population.country_parse_method_only_rows:
        raise ValueError("country_parse_method-only population remains after repair")
    if population.country_parse_method_changed_rows:
        raise ValueError("country_parse_method changed in repaired comparison")
    for rule_id in EXPERIMENTAL_RULE_IDS:
        if (
            population.rule_candidate_groups[rule_id]
            != expectation.candidate_groups_per_rule
            or population.rule_selected_candidate_groups[rule_id]
            != expectation.selected_candidate_groups_per_rule
        ):
            raise ValueError("repaired experimental V4 rule aggregate mismatch")


def _validate_pin(path: Path, pin: ArtifactPin) -> None:
    if not path.is_file() or path.is_symlink():
        raise ValueError("repaired targeted-review input is not a regular file")
    if path.stat().st_size != pin.size_bytes or file_sha256(path) != pin.sha256:
        raise ValueError("repaired targeted-review artifact identity mismatch")


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("repaired targeted-review JSON input is invalid")
    return cast(dict[str, Any], value)


def _validate_repair_metadata(
    success: Mapping[str, Any],
    comparison: Mapping[str, Any],
    expectation: PopulationExpectation,
    expected_identity_order_digest: str,
) -> None:
    if (
        success.get("status") != "DEVELOPMENT_COUNTRY_METHOD_REPAIR_COMPARISON_COMPLETE"
        or success.get("iteration_id") != REPAIRED_ITERATION_ID
        or success.get("git_commit") != REPAIRED_EXECUTION_COMMIT
        or success.get("development_rows") != expectation.development_rows
        or success.get("locked_payload_rows_read") != 0
    ):
        raise ValueError("repaired iteration success metadata mismatch")
    if (
        comparison.get("status")
        != "EXPERIMENTAL_COMPARISON_COMPLETE_NO_PROMOTION_DECISION"
        or comparison.get("rows") != expectation.development_rows
        or comparison.get("identity_order_equal") is not True
        or comparison.get("identity_digest") != expected_identity_order_digest
    ):
        raise ValueError("repaired comparison metadata mismatch")
    baseline = cast(Mapping[str, Any], comparison.get("baseline", {}))
    experimental = cast(Mapping[str, Any], comparison.get("experimental", {}))
    if (
        baseline.get("parser_version") != PARSER_VERSION_V2_1
        or baseline.get("rule_registry_version") != RULE_REGISTRY_VERSION_V3
        or baseline.get("configuration_fingerprint")
        != REPAIRED_BASELINE_CONFIGURATION_FINGERPRINT
        or baseline.get("core_sha256") != REPAIRED_ARTIFACT_PINS["baseline_core"].sha256
        or baseline.get("evidence_sha256")
        != REPAIRED_ARTIFACT_PINS["baseline_evidence"].sha256
        or experimental.get("parser_version") != PARSER_VERSION_V3_1
        or experimental.get("rule_registry_version") != RULE_REGISTRY_VERSION_V4
        or experimental.get("configuration_fingerprint")
        != REPAIRED_EXPERIMENTAL_CONFIGURATION_FINGERPRINT
        or experimental.get("core_sha256")
        != REPAIRED_ARTIFACT_PINS["experimental_core"].sha256
        or experimental.get("evidence_sha256")
        != REPAIRED_ARTIFACT_PINS["experimental_evidence"].sha256
    ):
        raise ValueError("repaired comparison provenance mismatch")


def _atomic_json(path: Path, payload: Mapping[str, JsonValue]) -> None:
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with temporary.open("xb") as stream:
        os.chmod(temporary, 0o600)
        stream.write(canonical_json_bytes(dict(payload)) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    path.chmod(0o600)


def verify_repaired_targeted_review_population(
    *,
    development_identities_path: Path,
    baseline_core_path: Path,
    baseline_evidence_path: Path,
    experimental_core_path: Path,
    experimental_evidence_path: Path,
    repair_success_path: Path,
    repair_comparison_path: Path,
    output_path: Path,
    verification_implementation_commit: str,
    verification_implementation_fingerprint: str,
    production: bool,
) -> dict[str, Any]:
    """Verify repaired A union B without creating review inputs or labels."""
    paths = {
        "development_identities": development_identities_path,
        "baseline_core": baseline_core_path,
        "baseline_evidence": baseline_evidence_path,
        "experimental_core": experimental_core_path,
        "experimental_evidence": experimental_evidence_path,
        "repair_success": repair_success_path,
        "repair_comparison": repair_comparison_path,
    }
    for path in (*paths.values(), output_path):
        reject_locked_path(path)
    if production:
        from ..execution_policy import require_goethe_nhr_slurm

        require_goethe_nhr_slurm(
            "phase03-targeted-parser-v3-repaired-population-verify"
        )
    if output_path.exists():
        raise FileExistsError(output_path)
    if not _COMMIT.fullmatch(verification_implementation_commit) or not (
        _LOWER_HEX_64.fullmatch(verification_implementation_fingerprint)
    ):
        raise ValueError("targeted population verifier implementation identity invalid")
    for role, path in paths.items():
        _validate_pin(path, REPAIRED_ARTIFACT_PINS[role])
        reject_locked_path(path.resolve(strict=True))

    expectation = REPAIRED_POPULATION_EXPECTATION
    expected_identity_order_digest = REPAIRED_DEVELOPMENT_IDENTITY_ORDER_DIGEST
    success = _load_json(repair_success_path)
    comparison = _load_json(repair_comparison_path)
    _validate_repair_metadata(
        success, comparison, expectation, expected_identity_order_digest
    )
    identity_metadata, identities = read_identity_set(development_identities_path)
    if identity_metadata.get("partition") != "DEVELOPMENT":
        raise ValueError("targeted-review identity set is not DEVELOPMENT")
    if len(identities) != expectation.development_rows or len(set(identities)) != len(
        identities
    ):
        raise ValueError("targeted-review DEVELOPMENT identity count mismatch")
    identity_set = set(identities)

    baseline = read_core(baseline_core_path)
    baseline_evidence = read_evidence(baseline_evidence_path)
    experimental = read_core(experimental_core_path)
    experimental_evidence = read_evidence(experimental_evidence_path)
    if (
        len(baseline) != expectation.development_rows
        or len(experimental) != expectation.development_rows
    ):
        raise ValueError("targeted-review core row count mismatch")
    baseline_ids = [bytes(row["stable_source_row_id_v1"]) for row in baseline]
    experimental_ids = [bytes(row["stable_source_row_id_v1"]) for row in experimental]
    if (
        baseline_ids != experimental_ids
        or len(set(baseline_ids)) != len(baseline_ids)
        or set(baseline_ids) != identity_set
        or development_identity_order_digest(baseline) != expected_identity_order_digest
    ):
        raise ValueError("targeted-review core/DEVELOPMENT identity mismatch")
    if (
        {row["parser_version"] for row in baseline} != {PARSER_VERSION_V2_1}
        or {row["rule_registry_version"] for row in baseline}
        != {RULE_REGISTRY_VERSION_V3}
        or {row["parser_version"] for row in experimental} != {PARSER_VERSION_V3_1}
        or {row["rule_registry_version"] for row in experimental}
        != {RULE_REGISTRY_VERSION_V4}
        or {bytes(row["configuration_fingerprint"]).hex() for row in baseline}
        != {REPAIRED_BASELINE_CONFIGURATION_FINGERPRINT}
        or {bytes(row["configuration_fingerprint"]).hex() for row in experimental}
        != {REPAIRED_EXPERIMENTAL_CONFIGURATION_FINGERPRINT}
    ):
        raise ValueError("targeted-review repaired parser/configuration mismatch")
    validate_core_evidence_relationship(baseline, baseline_evidence)
    validate_core_evidence_relationship(experimental, experimental_evidence)
    if {
        bytes(row["stable_source_row_id_v1"]) for row in baseline_evidence
    } - identity_set or {
        bytes(row["stable_source_row_id_v1"]) for row in experimental_evidence
    } - identity_set:
        raise ValueError("targeted-review evidence identity mismatch")

    population = compute_targeted_population(
        baseline, experimental, experimental_evidence
    )
    validate_population_expectation(population, expectation)
    for role, path in paths.items():
        _validate_pin(path, REPAIRED_ARTIFACT_PINS[role])
    payload: dict[str, JsonValue] = {
        "report_version": REPAIRED_TARGETED_REVIEW_POPULATION_VERSION,
        "status": "REPAIRED_TARGETED_REVIEW_POPULATION_VERIFIED_NO_REVIEW_INITIALIZED",
        "repair_iteration": REPAIRED_ITERATION_ID,
        "repair_job_id": REPAIRED_JOB_ID,
        "repair_execution_commit": REPAIRED_EXECUTION_COMMIT,
        "verification_implementation_commit": verification_implementation_commit,
        "verification_implementation_fingerprint": (
            verification_implementation_fingerprint
        ),
        "population_definition": (
            "SCIENTIFIC_OUTPUT_CHANGE_UNION_EXPERIMENTAL_RULE_EVIDENCE"
        ),
        "development_rows": expectation.development_rows,
        "scientific_output_change_rows": len(population.changed_ids),
        "experimental_rule_evidence_rows": len(population.evidence_ids),
        "overlap_rows": population.overlap_rows,
        "changed_only_rows": population.changed_only_rows,
        "evidence_only_rows": population.evidence_only_rows,
        "targeted_review_population_rows": len(population.population),
        "all_scientific_changes_have_experimental_evidence": not bool(
            population.changed_ids - population.evidence_ids
        ),
        "evidence_only_rows_have_no_scientific_change": True,
        "country_parse_method_only_changed_rows": (
            population.country_parse_method_only_rows
        ),
        "country_parse_method_changed_rows": population.country_parse_method_changed_rows,
        "experimental_rule_candidate_groups": dict(population.rule_candidate_groups),
        "experimental_rule_selected_candidate_groups": dict(
            population.rule_selected_candidate_groups
        ),
        "development_identity_artifact_sha256": REPAIRED_ARTIFACT_PINS[
            "development_identities"
        ].sha256,
        "development_identity_order_digest": (expected_identity_order_digest),
        "parser_versions": {
            "baseline": PARSER_VERSION_V2_1,
            "experimental": PARSER_VERSION_V3_1,
        },
        "rule_registry_versions": {
            "baseline": RULE_REGISTRY_VERSION_V3,
            "experimental": RULE_REGISTRY_VERSION_V4,
        },
        "configuration_fingerprints": {
            "baseline": REPAIRED_BASELINE_CONFIGURATION_FINGERPRINT,
            "experimental": REPAIRED_EXPERIMENTAL_CONFIGURATION_FINGERPRINT,
        },
        "input_artifacts": {
            role: {
                "sha256": REPAIRED_ARTIFACT_PINS[role].sha256,
                "size_bytes": REPAIRED_ARTIFACT_PINS[role].size_bytes,
            }
            for role in paths
        },
        "identity_values_exported": False,
        "raw_values_exported": False,
        "review_inputs_created": False,
        "review_databases_created": False,
        "locked_rows_read": 0,
        "scientific_promotion_decision": "NOT_EVALUATED",
    }
    _atomic_json(output_path, payload)
    return cast(dict[str, Any], json.loads(canonical_json_bytes(payload)))


def validate_population_verification_report(path: Path) -> dict[str, Any]:
    """Validate a prior sanitized repaired-population report for preparation."""
    reject_locked_path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError("repaired targeted-review verification is not a regular file")
    payload = _load_json(path)
    expected_counts = {
        "development_rows": 8_000,
        "scientific_output_change_rows": 9,
        "experimental_rule_evidence_rows": 11,
        "overlap_rows": 9,
        "changed_only_rows": 0,
        "evidence_only_rows": 2,
        "targeted_review_population_rows": 11,
        "country_parse_method_only_changed_rows": 0,
        "country_parse_method_changed_rows": 0,
        "locked_rows_read": 0,
    }
    expected_rule_counts = {
        rule_id: REPAIRED_POPULATION_EXPECTATION.candidate_groups_per_rule
        for rule_id in EXPERIMENTAL_RULE_IDS
    }
    expected_selected_counts = {
        rule_id: REPAIRED_POPULATION_EXPECTATION.selected_candidate_groups_per_rule
        for rule_id in EXPERIMENTAL_RULE_IDS
    }
    expected_inputs = {
        role: {
            "sha256": REPAIRED_ARTIFACT_PINS[role].sha256,
            "size_bytes": REPAIRED_ARTIFACT_PINS[role].size_bytes,
        }
        for role in (
            "development_identities",
            "baseline_core",
            "baseline_evidence",
            "experimental_core",
            "experimental_evidence",
            "repair_success",
            "repair_comparison",
        )
    }
    if (
        payload.get("report_version") != REPAIRED_TARGETED_REVIEW_POPULATION_VERSION
        or payload.get("status")
        != "REPAIRED_TARGETED_REVIEW_POPULATION_VERIFIED_NO_REVIEW_INITIALIZED"
        or payload.get("repair_iteration") != REPAIRED_ITERATION_ID
        or payload.get("repair_job_id") != REPAIRED_JOB_ID
        or payload.get("repair_execution_commit") != REPAIRED_EXECUTION_COMMIT
        or not isinstance(payload.get("verification_implementation_commit"), str)
        or not _COMMIT.fullmatch(
            cast(str, payload.get("verification_implementation_commit"))
        )
        or not isinstance(payload.get("verification_implementation_fingerprint"), str)
        or not _LOWER_HEX_64.fullmatch(
            cast(str, payload.get("verification_implementation_fingerprint"))
        )
        or payload.get("population_definition")
        != "SCIENTIFIC_OUTPUT_CHANGE_UNION_EXPERIMENTAL_RULE_EVIDENCE"
        or any(payload.get(key) != value for key, value in expected_counts.items())
        or payload.get("all_scientific_changes_have_experimental_evidence") is not True
        or payload.get("evidence_only_rows_have_no_scientific_change") is not True
        or payload.get("experimental_rule_candidate_groups") != expected_rule_counts
        or payload.get("experimental_rule_selected_candidate_groups")
        != expected_selected_counts
        or payload.get("development_identity_artifact_sha256")
        != REPAIRED_ARTIFACT_PINS["development_identities"].sha256
        or payload.get("development_identity_order_digest")
        != REPAIRED_DEVELOPMENT_IDENTITY_ORDER_DIGEST
        or payload.get("parser_versions")
        != {
            "baseline": PARSER_VERSION_V2_1,
            "experimental": PARSER_VERSION_V3_1,
        }
        or payload.get("rule_registry_versions")
        != {
            "baseline": RULE_REGISTRY_VERSION_V3,
            "experimental": RULE_REGISTRY_VERSION_V4,
        }
        or payload.get("configuration_fingerprints")
        != {
            "baseline": REPAIRED_BASELINE_CONFIGURATION_FINGERPRINT,
            "experimental": REPAIRED_EXPERIMENTAL_CONFIGURATION_FINGERPRINT,
        }
        or payload.get("input_artifacts") != expected_inputs
        or payload.get("identity_values_exported") is not False
        or payload.get("raw_values_exported") is not False
        or payload.get("review_inputs_created") is not False
        or payload.get("review_databases_created") is not False
        or payload.get("scientific_promotion_decision") != "NOT_EVALUATED"
    ):
        raise ValueError("repaired targeted-review population verification failed")
    return payload
