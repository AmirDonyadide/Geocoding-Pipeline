from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast

import pyarrow as pa
import pyarrow.parquet as pq

from ..execution_policy import require_goethe_nhr_slurm
from ..phase02.fingerprints import JsonValue, canonical_json_bytes, fingerprint
from ..phase02.schema import base_staging_schema, exact_schema_matches
from .config import Phase03Config
from .constants import (
    LOCKED_EVALUATION_PROTOCOL_VERSION,
    MANUAL_REVIEW_REASON_CODES_VERSION,
    PARSER_VERSION_V2_1,
    PARSER_VERSION_V3_2,
    RULE_REGISTRY_VERSION_V3,
    RULE_REGISTRY_VERSION_V5,
)
from .engine import Phase03Engine
from .errors import Phase03Error
from .pilot_orchestration import (
    phase02_manifest_identity,
    validate_explicit_phase02_inputs,
)
from .pilot_runner import identity_digest, read_identity_set
from .review import canonicalize_manual_review_reason_codes
from .review_v2 import (
    COMPONENT_LABEL_VALUES,
    ERROR_CONDITION_LABEL_VALUES,
    MAX_PROTECTED_NOTE_CHARACTERS,
    OVERALL_LABEL_VALUES,
)
from .rules import load_rule_registry
from .schema import exact_core_schema_matches, exact_evidence_schema_matches
from .targeted_experiment_review import (
    CANDIDATE_SUPPORT_VALUES,
    JOINT_LABEL_VALUES,
    RESIDUAL_ROLE_VALUES,
)
from .targeted_review_population import SCIENTIFIC_CORE_FIELDS
from .validation import validate_core_evidence_relationship
from .writer import ShardWriteResult, write_validate_and_promote_synthetic_shard

LOCKED_REVIEW_SELECTION_VERSION: Final = "phase03_locked_review_selection_v1"
LOCKED_REVIEW_SCHEMA_VERSION: Final = "phase03_locked_review_labels_v1"
LOCKED_REVIEW_VOCABULARY_VERSION: Final = "phase03_locked_review_label_vocabularies_v1"
LOCKED_REVIEW_PROGRESS_VERSION: Final = "phase03_locked_review_progress_sqlite_v1"
LOCKED_METRICS_VERSION: Final = "phase03_locked_metrics_v1"
LOCKED_DECISION_VERSION: Final = "phase03_locked_decision_v1"
LOCKED_PREFLIGHT_VERSION: Final = "phase03_locked_preflight_v1"
LOCKED_OUTPUT_MANIFEST_VERSION: Final = "phase03_locked_output_manifest_v1"

FROZEN_CANDIDATE_COMMIT: Final = "e78f52374c156477ce026e0d1dbb9755b85f5d82"
FROZEN_PROVENANCE_COMMIT: Final = "67e18738a97f4a836ded91dde37fad1543084cd3"
FROZEN_REGISTRY_SHA256: Final = (
    "4e66e0be62c3d0aae3e9452babe7d16f312c7bb49c69af1a2a0e6839cc3bb1fd"
)
FROZEN_DEVELOPMENT_CONFIGURATION_SHA256: Final = (
    "89370fddf5f9dae8f381f62344df4da96f0b3dc34627cff23a8068555b909a73"
)
FROZEN_LOCKED_CONFIGURATION_SHA256: Final = (
    "43aa0bc515886b42a42990c8e300f956c8c3c93a9d9e71571dd0eb20bd2fc609"
)
FROZEN_LOCKED_BASELINE_CONFIGURATION_SHA256: Final = (
    "a40e27d931884725218bf0041d7b56208fe5de14f40cdf42d45bbb9be115beac"
)
FROZEN_LOCKED_COUNT: Final = 4_000
FROZEN_LOCKED_IDENTITY_DIGEST: Final = (
    "dbae5d2d69db4b3e330f416a0c68d102c87b6446c04c1390f36e17dc3e8deb73"
)
FROZEN_PILOT_SEAL_SHA256: Final = (
    "ae1e9dd6eb927301eeaa33561aefc6c5197b22ab9eeea5bd8d37fcccce6616e7"
)
FROZEN_SAMPLING_CONTRACT_SHA256: Final = (
    "0fb7527db5b6a7eb1c7d7eb86d4a038abf4d605728bfe9cf761c74cd33c6d1c7"
)
LOCKED_REVIEW_COUNT: Final = 400
LOCKED_DOUBLE_REVIEW_COUNT: Final = 100
LOCKED_REVIEWER_IDS: Final = ("LOCKED-R01", "LOCKED-R02")
LOCKED_REVIEWER_ROLES: Final = {
    "LOCKED-R01": "PRIMARY",
    "LOCKED-R02": "INDEPENDENT_SECOND",
}
LOCKED_REVIEW_SEED: Final = "safe_geocoding_pipeline:phase03_locked_review_v1:seed:1"
LOCKED_V5_RULE_IDS: Final = (
    "HOUSE_NUMBER_EMBEDDED_DESIGNATOR_EXPERIMENT_V5",
    "STREET_EMBEDDED_DESIGNATOR_EXPERIMENT_V5",
)
LOCKED_AGREEMENT_FIELDS: Final = (
    "street_label",
    "house_number_label",
    "joint_street_house_label",
    "residual_role_label",
    "candidate_support_label",
    "conflict_correctness_label",
    "parser_overreach_label",
    "missed_information_label",
    "unsafe_handling_label",
    "overall_parse_acceptability_label",
)
LOCKED_LABEL_FIELDS: Final = LOCKED_AGREEMENT_FIELDS
LOCKED_ALLOWED_CHANGE_FIELDS: Final = frozenset(
    {
        "street_clean",
        "house_number_clean",
        "address_parse_status",
        "address_completeness_class",
        "address_diagnostic_flags",
        "selected_component_provenance",
    }
)
_LOWER_HEX_64 = re.compile(r"[0-9a-f]{64}")
_LOWER_HEX_40 = re.compile(r"[0-9a-f]{40}")


def file_sha256(path: Path, *, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(block_size):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_parent(path: Path) -> None:
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_json(path: Path, payload: Mapping[str, JsonValue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.tmp")
    if path.exists() or temporary.exists():
        raise FileExistsError(path)
    with temporary.open("xb") as stream:
        os.chmod(temporary, 0o600)
        stream.write(canonical_json_bytes(dict(payload)) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    path.chmod(0o600)
    _fsync_parent(path)


def _rank(domain: str, identity: bytes) -> bytes:
    if len(identity) != 32:
        raise ValueError("stable source row ID must be 32 bytes")
    return hashlib.sha256(domain.encode("utf-8") + b"\0" + identity).digest()


def _identity_set_digest(domain: str, identities: Iterable[bytes]) -> str:
    values = sorted(identities)
    digest = hashlib.sha256(domain.encode("utf-8") + b"\0")
    digest.update(len(values).to_bytes(8, "big"))
    for value in values:
        if len(value) != 32:
            raise ValueError("stable source row ID must be 32 bytes")
        digest.update(value)
    return digest.hexdigest()


def read_frozen_locked_identity_set(
    path: Path,
) -> tuple[dict[str, Any], tuple[bytes, ...]]:
    """Read and validate the one frozen LOCKED identity set, never a substitute."""
    metadata, identities = read_identity_set(path)
    if (
        metadata.get("partition") != "LOCKED_EVALUATION"
        or len(identities) != FROZEN_LOCKED_COUNT
        or len(set(identities)) != FROZEN_LOCKED_COUNT
        or identity_digest(b"phase03:locked_identities_v1\0", identities)
        != FROZEN_LOCKED_IDENTITY_DIGEST
    ):
        raise Phase03Error("LOCKED_IDENTITY_SET_MISMATCH")
    return metadata, identities


@dataclass(frozen=True, slots=True)
class LockedEvaluationContract:
    protocol_version: str = LOCKED_EVALUATION_PROTOCOL_VERSION
    candidate_commit: str = FROZEN_CANDIDATE_COMMIT
    parser_version: str = PARSER_VERSION_V3_2
    registry_version: str = RULE_REGISTRY_VERSION_V5
    registry_sha256: str = FROZEN_REGISTRY_SHA256
    locked_count: int = FROZEN_LOCKED_COUNT
    locked_identity_digest: str = FROZEN_LOCKED_IDENTITY_DIGEST
    review_count: int = LOCKED_REVIEW_COUNT
    double_review_count: int = LOCKED_DOUBLE_REVIEW_COUNT
    joint_precision_numerator: int = 95
    joint_precision_denominator: int = 100
    street_precision_numerator: int = 95
    street_precision_denominator: int = 100
    house_precision_numerator: int = 95
    house_precision_denominator: int = 100
    maximum_overreach_numerator: int = 5
    maximum_overreach_denominator: int = 100
    minimum_kappa_numerator: int = 80
    minimum_kappa_denominator: int = 100
    minimum_agreement_pairs: int = 80
    undefined_kappa_fallback_numerator: int = 95
    undefined_kappa_fallback_denominator: int = 100

    def validate(self) -> None:
        if (
            self.protocol_version != LOCKED_EVALUATION_PROTOCOL_VERSION
            or self.candidate_commit != FROZEN_CANDIDATE_COMMIT
            or self.parser_version != PARSER_VERSION_V3_2
            or self.registry_version != RULE_REGISTRY_VERSION_V5
            or self.registry_sha256 != FROZEN_REGISTRY_SHA256
            or self.locked_count != 4_000
            or self.review_count != 400
            or self.double_review_count != 100
        ):
            raise ValueError("LOCKED evaluation contract identity mismatch")
        if not _LOWER_HEX_64.fullmatch(self.locked_identity_digest):
            raise ValueError("LOCKED identity digest is invalid")
        if self.minimum_agreement_pairs > self.double_review_count:
            raise ValueError("agreement denominator exceeds double-review count")

    def payload(self) -> dict[str, JsonValue]:
        self.validate()
        return {
            **cast(dict[str, JsonValue], asdict(self)),
            "provenance_commit": FROZEN_PROVENANCE_COMMIT,
            "pilot_seal_sha256": FROZEN_PILOT_SEAL_SHA256,
            "sampling_contract_sha256": FROZEN_SAMPLING_CONTRACT_SHA256,
            "development_configuration_sha256": (
                FROZEN_DEVELOPMENT_CONFIGURATION_SHA256
            ),
            "locked_baseline_configuration_sha256": (
                FROZEN_LOCKED_BASELINE_CONFIGURATION_SHA256
            ),
            "locked_candidate_configuration_sha256": (
                FROZEN_LOCKED_CONFIGURATION_SHA256
            ),
            "review_selection_version": LOCKED_REVIEW_SELECTION_VERSION,
            "review_seed": LOCKED_REVIEW_SEED,
            "reviewer_ids": list(LOCKED_REVIEWER_IDS),
            "reviewer_roles": dict(LOCKED_REVIEWER_ROLES),
            "review_schema_version": LOCKED_REVIEW_SCHEMA_VERSION,
            "review_vocabulary_version": LOCKED_REVIEW_VOCABULARY_VERSION,
            "reason_codes_version": MANUAL_REVIEW_REASON_CODES_VERSION,
            "metrics_version": LOCKED_METRICS_VERSION,
            "decision_version": LOCKED_DECISION_VERSION,
            "agreement_fields": list(LOCKED_AGREEMENT_FIELDS),
            "agreement_pair_handling": {
                "cannot_assess": "EXCLUDED_PAIRWISE_PER_LABEL",
                "not_applicable": "RETAINED_AS_CATEGORY",
            },
            "review_selection_algorithm": {
                "reservations": [
                    "UP_TO_100_V5_SELECTED",
                    "UP_TO_100_V5_UNSELECTED",
                    "UP_TO_50_CHANGED_WITHOUT_V5_EVIDENCE",
                    "PRIORITY_UNION_TO_400",
                    "ALL_LOCKED_STRATIFIED_FILL_TO_400",
                ],
                "structural_coverage_target_per_available_category": 5,
                "identity_deduplication": True,
                "rank": "SHA256_DOMAIN_NUL_RAW_STABLE_ID_THEN_RAW_ID_TIE_BREAK",
                "double_review_targets": {
                    "v5_selected": 50,
                    "v5_unselected": 25,
                    "parser_changed": 25,
                    "total": 100,
                    "overlap_counts_toward_each_target": True,
                },
            },
            "metric_formulas": {
                "joint_precision": (
                    "R01_EXPERIMENTAL_SELECTED_JOINT_CORRECT/"
                    "R01_EXPERIMENTAL_SELECTED_JOINT_CORRECT_OR_INCORRECT"
                ),
                "street_precision": (
                    "R01_SELECTED_STREET_CORRECT/"
                    "R01_SELECTED_STREET_CORRECT_OR_INCORRECT"
                ),
                "house_precision": (
                    "R01_SELECTED_HOUSE_CORRECT/R01_SELECTED_HOUSE_CORRECT_OR_INCORRECT"
                ),
                "overreach_rate": "R01_OVERREACH_PRESENT/R01_OVERREACH_PRESENT_OR_ABSENT",
                "missed_rate": "R01_MISSED_PRESENT/R01_MISSED_PRESENT_OR_ABSENT_REPORT_ONLY",
                "empty_hard_gate_denominator": "FAIL",
                "comparison": "EXACT_INTEGER_CROSS_PRODUCT",
            },
            "decision_semantics": {
                "pass": "ALL_HARD_GATES_PASS",
                "fail": "LOCKED_FAIL_REVISE",
                "revision": "NEW_PARSER_RULE_VERSION_AND_NEW_LOCKED_SAMPLE",
            },
            "required_machine_check_fields": cast(
                list[JsonValue], sorted(_MACHINE_CHECK_FIELDS)
            ),
            "fill_rate_acceptance_metric": False,
            "automatic_promotion": False,
        }

    def fingerprint(self) -> str:
        return fingerprint(self.payload())


@dataclass(frozen=True, slots=True)
class LockedReviewCandidate:
    stable_source_row_id_v1: bytes
    parser_changed: bool
    experimental_evidence_state: str
    country_group: str
    script_family: str
    parse_status: str
    completeness: str
    conflict_state: str

    def validate(self) -> None:
        if len(self.stable_source_row_id_v1) != 32:
            raise ValueError("review candidate identity must be 32 bytes")
        if self.experimental_evidence_state not in {"SELECTED", "UNSELECTED", "NONE"}:
            raise ValueError("invalid experimental evidence state")
        if any(
            not value or "\0" in value
            for value in (
                self.country_group,
                self.script_family,
                self.parse_status,
                self.completeness,
                self.conflict_state,
            )
        ):
            raise ValueError("invalid review stratum value")

    def memberships(self) -> tuple[tuple[str, str], ...]:
        return (
            ("country_group", self.country_group),
            ("script_family", self.script_family),
            ("parse_status", self.parse_status),
            ("completeness", self.completeness),
            ("conflict_state", self.conflict_state),
            ("experimental_evidence_state", self.experimental_evidence_state),
            ("parser_change_state", "CHANGED" if self.parser_changed else "UNCHANGED"),
        )


@dataclass(frozen=True, slots=True)
class LockedReviewSelection:
    review_ids: tuple[bytes, ...]
    double_review_ids: tuple[bytes, ...]
    reviewer_one_order: tuple[bytes, ...]
    reviewer_two_order: tuple[bytes, ...]
    review_identity_digest: str
    double_review_identity_digest: str
    selection_diagnostics: tuple[str, ...]


def _coverage_select(
    candidates: Sequence[LockedReviewCandidate],
    count: int,
    *,
    domain: str,
    already_selected: set[bytes],
) -> list[LockedReviewCandidate]:
    pool = [
        candidate
        for candidate in candidates
        if candidate.stable_source_row_id_v1 not in already_selected
    ]
    if count < 0:
        raise ValueError("coverage selection count must be non-negative")
    count = min(count, len(pool))
    available = Counter(
        membership for candidate in pool for membership in candidate.memberships()
    )
    targets = {key: min(5, value) for key, value in available.items()}
    represented: Counter[tuple[str, str]] = Counter()
    selected: list[LockedReviewCandidate] = []
    while len(selected) < count:

        def key(candidate: LockedReviewCandidate) -> tuple[int, bytes, bytes]:
            gain = sum(
                represented[membership] < targets[membership]
                for membership in candidate.memberships()
            )
            return (
                -gain,
                _rank(domain, candidate.stable_source_row_id_v1),
                candidate.stable_source_row_id_v1,
            )

        chosen = min(pool, key=key)
        pool.remove(chosen)
        selected.append(chosen)
        represented.update(chosen.memberships())
    return selected


def select_locked_review_population(
    candidates: Iterable[LockedReviewCandidate],
    *,
    review_count: int = LOCKED_REVIEW_COUNT,
    double_review_count: int = LOCKED_DOUBLE_REVIEW_COUNT,
) -> LockedReviewSelection:
    values = sorted(candidates, key=lambda item: item.stable_source_row_id_v1)
    for value in values:
        value.validate()
    if len(values) < review_count:
        raise ValueError("LOCKED review population has fewer than 400 eligible rows")
    if len({item.stable_source_row_id_v1 for item in values}) != len(values):
        raise ValueError("LOCKED review population contains duplicate identities")
    if not 0 < double_review_count <= review_count:
        raise ValueError("invalid LOCKED double-review count")

    selected: list[LockedReviewCandidate] = []
    selected_ids: set[bytes] = set()
    diagnostics: list[str] = []

    def add_group(
        group: Sequence[LockedReviewCandidate], count: int, label: str
    ) -> None:
        chosen = _coverage_select(
            group,
            count,
            domain=f"{LOCKED_REVIEW_SEED}:review:{label}",
            already_selected=selected_ids,
        )
        selected.extend(chosen)
        selected_ids.update(item.stable_source_row_id_v1 for item in chosen)
        if len(chosen) < count:
            diagnostics.append(f"{label}:TARGET_NOT_FULLY_AVAILABLE")

    selected_evidence = [
        item for item in values if item.experimental_evidence_state == "SELECTED"
    ]
    unselected_evidence = [
        item for item in values if item.experimental_evidence_state == "UNSELECTED"
    ]
    changed_without_evidence = [
        item
        for item in values
        if item.parser_changed and item.experimental_evidence_state == "NONE"
    ]
    add_group(selected_evidence, min(100, len(selected_evidence)), "SELECTED_EVIDENCE")
    add_group(
        unselected_evidence,
        min(100, len(unselected_evidence)),
        "UNSELECTED_EVIDENCE",
    )
    add_group(
        changed_without_evidence,
        min(50, len(changed_without_evidence)),
        "CHANGED_WITHOUT_EVIDENCE",
    )

    priority_union = [
        item
        for item in values
        if item.parser_changed or item.experimental_evidence_state != "NONE"
    ]
    remaining = review_count - len(selected)
    available_priority = sum(
        item.stable_source_row_id_v1 not in selected_ids for item in priority_union
    )
    add_group(
        priority_union,
        min(remaining, available_priority),
        "PRIORITY_UNION",
    )
    remaining = review_count - len(selected)
    add_group(values, remaining, "STRATIFIED_FILL")
    if len(selected) != review_count or len(selected_ids) != review_count:
        raise ValueError("LOCKED review selector did not produce exactly 400 rows")

    double: list[LockedReviewCandidate] = []
    double_ids: set[bytes] = set()

    def add_double_target(
        group: Sequence[LockedReviewCandidate], target: int, label: str
    ) -> None:
        group_ids = {item.stable_source_row_id_v1 for item in group}
        already_represented = len(double_ids & group_ids)
        chosen = _coverage_select(
            group,
            max(0, min(target, len(group_ids)) - already_represented),
            domain=f"{LOCKED_REVIEW_SEED}:double:{label}",
            already_selected=double_ids,
        )
        double.extend(chosen)
        double_ids.update(item.stable_source_row_id_v1 for item in chosen)

    selected_by_id = {item.stable_source_row_id_v1: item for item in selected}
    selected_values = list(selected_by_id.values())
    add_double_target(
        [
            item
            for item in selected_values
            if item.experimental_evidence_state == "SELECTED"
        ],
        50,
        "SELECTED_EVIDENCE",
    )
    add_double_target(
        [
            item
            for item in selected_values
            if item.experimental_evidence_state == "UNSELECTED"
        ],
        25,
        "UNSELECTED_EVIDENCE",
    )
    add_double_target(
        [item for item in selected_values if item.parser_changed],
        25,
        "PARSER_CHANGED",
    )
    add_double_target(selected_values, double_review_count, "STRATIFIED_FILL")
    if len(double_ids) != double_review_count or not double_ids <= selected_ids:
        raise ValueError(
            "LOCKED double-review selector did not produce exactly 100 rows"
        )

    review_ids = tuple(sorted(selected_ids))
    double_review_ids = tuple(sorted(double_ids))
    reviewer_one_order = tuple(
        sorted(
            selected_ids,
            key=lambda value: (_rank(f"{LOCKED_REVIEW_SEED}:LOCKED-R01", value), value),
        )
    )
    reviewer_two_order = tuple(
        sorted(
            double_ids,
            key=lambda value: (_rank(f"{LOCKED_REVIEW_SEED}:LOCKED-R02", value), value),
        )
    )
    return LockedReviewSelection(
        review_ids=review_ids,
        double_review_ids=double_review_ids,
        reviewer_one_order=reviewer_one_order,
        reviewer_two_order=reviewer_two_order,
        review_identity_digest=_identity_set_digest(
            "safe_geocoding_pipeline:phase03_locked_review_population_v1",
            review_ids,
        ),
        double_review_identity_digest=_identity_set_digest(
            "safe_geocoding_pipeline:phase03_locked_double_review_population_v1",
            double_review_ids,
        ),
        selection_diagnostics=tuple(sorted(diagnostics)),
    )


@dataclass(frozen=True, slots=True)
class AgreementResult:
    field: str
    denominator: int
    agreement_numerator: int
    kappa_numerator: int | None
    kappa_denominator: int | None
    kappa_status: str
    gate_status: str


def cohen_kappa(
    first: Sequence[str], second: Sequence[str], *, field: str
) -> AgreementResult:
    if len(first) != len(second):
        raise ValueError("reviewer agreement sequences differ in length")
    pairs = [
        (left, right)
        for left, right in zip(first, second, strict=True)
        if left != "CANNOT_ASSESS" and right != "CANNOT_ASSESS"
    ]
    denominator = len(pairs)
    agreement = sum(left == right for left, right in pairs)
    if denominator < LockedEvaluationContract().minimum_agreement_pairs:
        return AgreementResult(
            field,
            denominator,
            agreement,
            None,
            None,
            "INSUFFICIENT_DENOMINATOR",
            "FAIL",
        )
    left_counts = Counter(left for left, _ in pairs)
    right_counts = Counter(right for _, right in pairs)
    expected_numerator = sum(
        left_counts[value] * right_counts[value]
        for value in set(left_counts) | set(right_counts)
    )
    kappa_denominator = denominator * denominator - expected_numerator
    contract = LockedEvaluationContract()
    if kappa_denominator == 0:
        fallback_pass = (
            agreement * contract.undefined_kappa_fallback_denominator
            >= denominator * contract.undefined_kappa_fallback_numerator
        )
        return AgreementResult(
            field,
            denominator,
            agreement,
            None,
            None,
            "UNDEFINED_DEGENERATE_MARGINALS",
            "PASS_FALLBACK_PERCENT_AGREEMENT" if fallback_pass else "FAIL",
        )
    kappa_numerator = agreement * denominator - expected_numerator
    kappa_pass = (
        kappa_numerator * contract.minimum_kappa_denominator
        >= kappa_denominator * contract.minimum_kappa_numerator
    )
    return AgreementResult(
        field,
        denominator,
        agreement,
        kappa_numerator,
        kappa_denominator,
        "DEFINED",
        "PASS" if kappa_pass else "FAIL",
    )


@dataclass(frozen=True, slots=True)
class MetricFraction:
    numerator: int
    denominator: int

    def at_least(self, numerator: int, denominator: int) -> bool:
        return (
            self.denominator > 0
            and self.numerator * denominator >= self.denominator * numerator
        )

    def at_most(self, numerator: int, denominator: int) -> bool:
        return (
            self.denominator > 0
            and self.numerator * denominator <= self.denominator * numerator
        )

    def payload(self) -> dict[str, JsonValue]:
        return {
            "numerator": self.numerator,
            "denominator": self.denominator,
            "value": self.numerator / self.denominator if self.denominator else None,
        }


@dataclass(frozen=True, slots=True)
class LockedMetricSet:
    joint_street_house_precision: MetricFraction
    street_exact_precision: MetricFraction
    house_number_exact_precision: MetricFraction
    false_structure_overreach_rate: MetricFraction
    missed_information_rate: MetricFraction
    false_negative_opportunities: int
    conflict_precision: MetricFraction
    conflict_recall: MetricFraction
    evidence_sidecar_coverage: MetricFraction


@dataclass(frozen=True, slots=True)
class LockedDecisionInputs:
    metrics: LockedMetricSet
    agreements: tuple[AgreementResult, ...]
    unexplained_scientific_changes: int = 0
    unrelated_component_regressions: int = 0
    provenance_failures: int = 0
    privacy_governance_failures: int = 0
    methodological_defect_requires_change: bool = False


_MACHINE_CHECK_FIELDS: Final = frozenset(
    {
        "unexplained_scientific_changes",
        "unrelated_component_regressions",
        "lost_existing_selections",
        "provenance_failures",
        "privacy_governance_failures",
        "systematic_methodological_defect_detected",
        "unsafe_extraction_pattern_detected",
        "required_parser_rule_modification",
    }
)


def _validate_machine_checks(
    machine_checks: Mapping[str, int | bool],
) -> dict[str, int | bool]:
    """Require every pre-registered machine gate; missing gates never pass."""
    if set(machine_checks) != _MACHINE_CHECK_FIELDS:
        raise ValueError("LOCKED machine-check field mismatch")
    count_fields = {
        "unexplained_scientific_changes",
        "unrelated_component_regressions",
        "lost_existing_selections",
        "provenance_failures",
        "privacy_governance_failures",
    }
    result: dict[str, int | bool] = {}
    for field in sorted(_MACHINE_CHECK_FIELDS):
        value = machine_checks[field]
        if field in count_fields:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"LOCKED machine-check count is invalid: {field}")
        elif not isinstance(value, bool):
            raise ValueError(f"LOCKED machine-check boolean is invalid: {field}")
        result[field] = value
    return result


def decide_locked_evaluation(inputs: LockedDecisionInputs) -> dict[str, JsonValue]:
    contract = LockedEvaluationContract()
    failures: list[str] = []
    if not inputs.metrics.joint_street_house_precision.at_least(95, 100):
        failures.append("JOINT_STREET_HOUSE_PRECISION_BELOW_0_95")
    if not inputs.metrics.street_exact_precision.at_least(95, 100):
        failures.append("STREET_EXACT_PRECISION_BELOW_0_95")
    if not inputs.metrics.house_number_exact_precision.at_least(95, 100):
        failures.append("HOUSE_NUMBER_EXACT_PRECISION_BELOW_0_95")
    if not inputs.metrics.false_structure_overreach_rate.at_most(5, 100):
        failures.append("FALSE_STRUCTURE_OVERREACH_ABOVE_0_05")
    if len(inputs.agreements) != len(LOCKED_AGREEMENT_FIELDS) or any(
        result.gate_status not in {"PASS", "PASS_FALLBACK_PERCENT_AGREEMENT"}
        for result in inputs.agreements
    ):
        failures.append("REVIEWER_AGREEMENT_GATE_FAILED")
    if inputs.unexplained_scientific_changes:
        failures.append("UNEXPLAINED_SCIENTIFIC_OUTPUT_CHANGE")
    if inputs.unrelated_component_regressions:
        failures.append("UNRELATED_COMPONENT_REGRESSION")
    if inputs.provenance_failures:
        failures.append("PROVENANCE_HASH_OR_SEAL_FAILURE")
    if inputs.privacy_governance_failures:
        failures.append("PRIVACY_OR_GOVERNANCE_FAILURE")
    if inputs.methodological_defect_requires_change:
        failures.append("METHODOLOGICAL_DEFECT_REQUIRES_CHANGE")
    status = "LOCKED_PASS" if not failures else "LOCKED_FAIL_REVISE"
    return {
        "decision_version": LOCKED_DECISION_VERSION,
        "protocol_version": contract.protocol_version,
        "status": status,
        "hard_gate_failures": cast(list[JsonValue], failures),
        "automatic_parser_promotion": False,
        "full_production_authorized": False,
        "geocoding_authorized": False,
        "revision_policy": (
            "NEW_PARSER_RULE_VERSION_AND_NEW_LOCKED_SAMPLE_REQUIRED"
            if failures
            else "SEPARATE_FINAL_PHASE03_PROMOTION_DECISION_REQUIRED"
        ),
    }


def locked_review_label_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("hashed_review_id", pa.string(), nullable=False),
            pa.field("locked_evaluation_version", pa.string(), nullable=False),
            pa.field("reviewer_id", pa.string(), nullable=False),
            pa.field("review_round", pa.uint8(), nullable=False),
            pa.field("is_independent_review", pa.bool_(), nullable=False),
            pa.field("assignment_role", pa.string(), nullable=False),
            *(
                pa.field(name, pa.string(), nullable=False)
                for name in LOCKED_LABEL_FIELDS
            ),
            pa.field("reason_codes", pa.list_(pa.string()), nullable=False),
            pa.field("reason_codes_version", pa.string(), nullable=False),
            pa.field("label_vocabulary_version", pa.string(), nullable=False),
            pa.field("label_schema_version", pa.string(), nullable=False),
        ]
    )


def locked_review_template_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("hashed_review_id", pa.string(), nullable=False),
            pa.field("locked_evaluation_version", pa.string(), nullable=False),
            pa.field("is_independent_review", pa.bool_(), nullable=False),
            pa.field("r01_display_order", pa.uint16(), nullable=False),
            pa.field("r02_display_order", pa.uint16(), nullable=True),
        ]
    )


def locked_review_context_schema() -> pa.Schema:
    fields = list(base_staging_schema())
    fields.extend(
        [
            pa.field("hashed_review_id", pa.string(), nullable=False),
            pa.field("baseline_core_json", pa.string(), nullable=False),
            pa.field("candidate_core_json", pa.string(), nullable=False),
            pa.field("baseline_evidence_json", pa.string(), nullable=False),
            pa.field("candidate_evidence_json", pa.string(), nullable=False),
            pa.field("locked_case_metadata_json", pa.string(), nullable=False),
        ]
    )
    return pa.schema(fields)


def _validate_closed(value: Any, allowed: Sequence[str], field: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"invalid LOCKED review value for {field}")
    return value


def validate_locked_review_labels(
    labels: Mapping[str, str],
    reason_codes: Iterable[str],
    *,
    protected_note: str | None,
) -> tuple[str, ...]:
    if set(labels) != set(LOCKED_LABEL_FIELDS):
        raise ValueError("LOCKED review label field mismatch")
    street = _validate_closed(labels["street_label"], COMPONENT_LABEL_VALUES, "street")
    house = _validate_closed(
        labels["house_number_label"], COMPONENT_LABEL_VALUES, "house_number"
    )
    joint = _validate_closed(
        labels["joint_street_house_label"], JOINT_LABEL_VALUES, "joint"
    )
    residual = _validate_closed(
        labels["residual_role_label"], RESIDUAL_ROLE_VALUES, "residual_role"
    )
    candidate = _validate_closed(
        labels["candidate_support_label"],
        CANDIDATE_SUPPORT_VALUES,
        "candidate_support",
    )
    conflict = _validate_closed(
        labels["conflict_correctness_label"],
        ("CORRECT", "INCORRECT", "NOT_APPLICABLE", "CANNOT_ASSESS"),
        "conflict_correctness",
    )
    overreach = _validate_closed(
        labels["parser_overreach_label"],
        ERROR_CONDITION_LABEL_VALUES,
        "parser_overreach",
    )
    missed = _validate_closed(
        labels["missed_information_label"],
        ERROR_CONDITION_LABEL_VALUES,
        "missed_information",
    )
    unsafe = _validate_closed(
        labels["unsafe_handling_label"],
        ERROR_CONDITION_LABEL_VALUES,
        "unsafe_handling",
    )
    overall = _validate_closed(
        labels["overall_parse_acceptability_label"],
        OVERALL_LABEL_VALUES,
        "overall_parse_acceptability",
    )
    if (
        protected_note is not None
        and len(protected_note) > MAX_PROTECTED_NOTE_CHARACTERS
    ):
        raise ValueError("protected note exceeds 500 Unicode characters")
    canonical = canonicalize_manual_review_reason_codes(
        reason_codes, protected_adjudication_note=protected_note
    )
    if not canonical:
        raise ValueError("completed LOCKED review requires at least one reason code")
    reasons = set(canonical)
    uncertain = (
        "CANNOT_ASSESS" in {street, house, joint, residual, candidate, conflict}
        or overreach == "CANNOT_ASSESS"
        or missed == "CANNOT_ASSESS"
        or unsafe == "CANNOT_ASSESS"
        or overall == "CANNOT_ASSESS"
    )
    if uncertain and reasons.isdisjoint(
        {"SOURCE_AMBIGUOUS", "INSUFFICIENT_SOURCE_EVIDENCE"}
    ):
        raise ValueError("uncertain LOCKED review requires an uncertainty reason")
    if (street == "MISSED" or house == "MISSED") and missed != "PRESENT":
        raise ValueError("component MISSED requires missed information PRESENT")
    if missed == "ABSENT" and (street == "MISSED" or house == "MISSED"):
        raise ValueError("missed information ABSENT forbids component MISSED")
    if (street == "MISSED" or house == "MISSED" or missed == "PRESENT") and (
        "MISSED_EXTRACTABLE_COMPONENT" not in reasons
    ):
        raise ValueError("missed extraction requires MISSED_EXTRACTABLE_COMPONENT")
    if (
        street == "INCORRECT" or house == "INCORRECT" or joint == "INCORRECT"
    ) and reasons.isdisjoint(
        {
            "WRONG_COMPONENT_ROLE",
            "WRONG_VALUE",
            "WRONG_SPAN_BOUNDARY",
            "FALSE_POSITIVE_EXTRACTION",
            "WRONG_NORMALIZATION",
            "WRONG_PROVENANCE",
        }
    ):
        raise ValueError("incorrect LOCKED component requires an applicable reason")
    if conflict == "INCORRECT" and reasons.isdisjoint(
        {"WRONG_CONFLICT_DETECTION", "MISSED_CONFLICT"}
    ):
        raise ValueError("incorrect conflict handling requires an applicable reason")
    if overreach == "PRESENT" and reasons.isdisjoint(
        {"FALSE_POSITIVE_EXTRACTION", "WRONG_COMPONENT_ROLE"}
    ):
        raise ValueError("parser overreach requires an applicable reason")
    if unsafe == "PRESENT" and "UNSAFE_INPUT_HANDLING" not in reasons:
        raise ValueError("unsafe handling requires UNSAFE_INPUT_HANDLING")
    if "CORRECT_AS_IS" in reasons and len(reasons) != 1:
        raise ValueError("CORRECT_AS_IS is exclusive")
    if "CORRECT_AS_IS" in reasons and (
        street in {"INCORRECT", "MISSED", "CANNOT_ASSESS"}
        or house in {"INCORRECT", "MISSED", "CANNOT_ASSESS"}
        or joint in {"INCORRECT", "CANNOT_ASSESS"}
        or candidate in {"NOT_SUPPORTED", "CANNOT_ASSESS"}
        or conflict in {"INCORRECT", "CANNOT_ASSESS"}
        or overreach != "ABSENT"
        or missed != "ABSENT"
        or unsafe != "ABSENT"
        or overall != "ACCEPTABLE"
    ):
        raise ValueError("CORRECT_AS_IS conflicts with LOCKED review labels")
    return canonical


@dataclass(frozen=True, slots=True)
class LockedReviewBinding:
    locked_evaluation_version: str
    context_sha256: str
    context_size_bytes: int
    template_sha256: str
    template_size_bytes: int
    population_digest: str
    implementation_commit: str
    implementation_fingerprint: str

    def metadata(self) -> dict[str, str]:
        if not _LOWER_HEX_40.fullmatch(self.implementation_commit):
            raise ValueError("LOCKED review implementation commit is invalid")
        for value in (
            self.context_sha256,
            self.template_sha256,
            self.population_digest,
            self.implementation_fingerprint,
        ):
            if not _LOWER_HEX_64.fullmatch(value):
                raise ValueError("LOCKED review binding hash is invalid")
        return {
            "progress_schema_version": LOCKED_REVIEW_PROGRESS_VERSION,
            "locked_evaluation_version": self.locked_evaluation_version,
            "context_sha256": self.context_sha256,
            "context_size_bytes": str(self.context_size_bytes),
            "template_sha256": self.template_sha256,
            "template_size_bytes": str(self.template_size_bytes),
            "population_count": str(LOCKED_REVIEW_COUNT),
            "population_digest": self.population_digest,
            "implementation_commit": self.implementation_commit,
            "implementation_fingerprint": self.implementation_fingerprint,
            "review_selection_version": LOCKED_REVIEW_SELECTION_VERSION,
            "review_seed": LOCKED_REVIEW_SEED,
            "label_schema_version": LOCKED_REVIEW_SCHEMA_VERSION,
            "label_vocabulary_version": LOCKED_REVIEW_VOCABULARY_VERSION,
            "reason_codes_version": MANUAL_REVIEW_REASON_CODES_VERSION,
        }


class LockedReviewStore:
    def __init__(self, path: Path, *, readonly: bool = False) -> None:
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError("LOCKED review database is missing")
        if path.stat().st_mode & 0o077 or path.parent.stat().st_mode & 0o077:
            raise ValueError("LOCKED review database and parent must be owner-only")
        uri = f"file:{path}?mode=ro" if readonly else str(path)
        self.connection = sqlite3.connect(uri, uri=readonly, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        if self.connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            self.connection.close()
            raise ValueError("LOCKED review database integrity check failed")

    def __enter__(self) -> LockedReviewStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.connection.close()

    @classmethod
    def create(
        cls,
        path: Path,
        *,
        binding: LockedReviewBinding,
        reviewer_id: str,
        ordered_hashed_ids: Sequence[str],
        double_review_hashed_ids: set[str],
    ) -> LockedReviewStore:
        if path.exists() or not ordered_hashed_ids:
            raise FileExistsError(
                "LOCKED review database already exists or assignment is empty"
            )
        if reviewer_id not in LOCKED_REVIEWER_IDS:
            raise ValueError("invalid LOCKED reviewer ID")
        if len(set(ordered_hashed_ids)) != len(ordered_hashed_ids):
            raise ValueError("duplicate LOCKED review assignment")
        role = LOCKED_REVIEWER_ROLES[reviewer_id]
        if (
            role == "INDEPENDENT_SECOND"
            and set(ordered_hashed_ids) != double_review_hashed_ids
        ):
            raise ValueError(
                "LOCKED-R02 assignment differs from frozen double-review set"
            )
        path.parent.mkdir(parents=True, exist_ok=False, mode=0o700)
        path.parent.chmod(0o700)
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        os.close(descriptor)
        path.chmod(0o600)
        store = cls(path)
        try:
            store.connection.executescript(
                """
                PRAGMA journal_mode=DELETE;
                PRAGMA synchronous=FULL;
                CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;
                CREATE TABLE assignment(
                    hashed_review_id TEXT PRIMARY KEY,
                    display_order INTEGER NOT NULL UNIQUE,
                    is_independent_review INTEGER NOT NULL CHECK(is_independent_review IN(0,1)),
                    status TEXT NOT NULL CHECK(status IN('PENDING','COMPLETE'))
                ) WITHOUT ROWID;
                CREATE TABLE label(
                    hashed_review_id TEXT PRIMARY KEY REFERENCES assignment(hashed_review_id),
                    labels_json TEXT,
                    reason_codes_json TEXT,
                    protected_note TEXT,
                    updated_at_utc TEXT
                ) WITHOUT ROWID;
                """
            )
            metadata = {
                **binding.metadata(),
                "reviewer_id": reviewer_id,
                "assignment_role": role,
                "expected_assignment_count": str(len(ordered_hashed_ids)),
            }
            store.connection.execute("BEGIN IMMEDIATE")
            store.connection.executemany(
                "INSERT INTO metadata(key,value) VALUES(?,?)", sorted(metadata.items())
            )
            store.connection.executemany(
                "INSERT INTO assignment VALUES(?,?,?,'PENDING')",
                [
                    (
                        hashed,
                        index,
                        int(hashed in double_review_hashed_ids),
                    )
                    for index, hashed in enumerate(ordered_hashed_ids)
                ],
            )
            store.connection.executemany(
                "INSERT INTO label(hashed_review_id) VALUES(?)",
                [(hashed,) for hashed in ordered_hashed_ids],
            )
            store.connection.commit()
            return store
        except Exception:
            store.connection.rollback()
            store.connection.close()
            path.unlink(missing_ok=True)
            path.parent.rmdir()
            raise

    def metadata(self) -> dict[str, str]:
        return {
            str(row["key"]): str(row["value"])
            for row in self.connection.execute("SELECT key,value FROM metadata")
        }

    def save_completed(
        self,
        hashed_review_id: str,
        labels: Mapping[str, str],
        reason_codes: Iterable[str],
        *,
        protected_note: str | None,
        timestamp_utc: str,
    ) -> None:
        canonical = validate_locked_review_labels(
            labels, reason_codes, protected_note=protected_note
        )
        if not _LOWER_HEX_64.fullmatch(hashed_review_id):
            raise ValueError("invalid hashed LOCKED review ID")
        self.connection.execute("BEGIN IMMEDIATE")
        cursor = self.connection.execute(
            "UPDATE label SET labels_json=?,reason_codes_json=?,protected_note=?,updated_at_utc=? "
            "WHERE hashed_review_id=?",
            (
                json.dumps(dict(labels), sort_keys=True, separators=(",", ":")),
                json.dumps(canonical, separators=(",", ":")),
                protected_note,
                timestamp_utc,
                hashed_review_id,
            ),
        )
        if cursor.rowcount != 1:
            self.connection.rollback()
            raise ValueError("LOCKED review assignment is unknown")
        self.connection.execute(
            "UPDATE assignment SET status='COMPLETE' WHERE hashed_review_id=?",
            (hashed_review_id,),
        )
        self.connection.commit()

    def summary(self) -> dict[str, int | str]:
        total, complete = self.connection.execute(
            "SELECT COUNT(*),SUM(status='COMPLETE') FROM assignment"
        ).fetchone()
        return {
            "reviewer_id": self.metadata()["reviewer_id"],
            "assignment_count": int(total),
            "complete_count": int(complete or 0),
            "pending_count": int(total) - int(complete or 0),
            "status": "COMPLETE" if total == complete else "IN_PROGRESS",
        }

    def completed_rows(self) -> list[dict[str, Any]]:
        metadata = self.metadata()
        rows: list[dict[str, Any]] = []
        for row in self.connection.execute(
            "SELECT a.hashed_review_id,a.is_independent_review,l.labels_json,"
            "l.reason_codes_json,l.protected_note FROM assignment a JOIN label l USING(hashed_review_id) "
            "WHERE a.status='COMPLETE' ORDER BY a.hashed_review_id"
        ):
            labels = json.loads(str(row["labels_json"]))
            reasons = json.loads(str(row["reason_codes_json"]))
            validate_locked_review_labels(
                labels, reasons, protected_note=cast(str | None, row["protected_note"])
            )
            rows.append(
                {
                    "hashed_review_id": str(row["hashed_review_id"]),
                    "locked_evaluation_version": metadata["locked_evaluation_version"],
                    "reviewer_id": metadata["reviewer_id"],
                    "review_round": 1,
                    "is_independent_review": bool(row["is_independent_review"]),
                    "assignment_role": metadata["assignment_role"],
                    **labels,
                    "reason_codes": reasons,
                    "reason_codes_version": MANUAL_REVIEW_REASON_CODES_VERSION,
                    "label_vocabulary_version": LOCKED_REVIEW_VOCABULARY_VERSION,
                    "label_schema_version": LOCKED_REVIEW_SCHEMA_VERSION,
                }
            )
        return rows

    def pending_ids(self) -> list[str]:
        return [
            str(row[0])
            for row in self.connection.execute(
                "SELECT hashed_review_id FROM assignment WHERE status='PENDING' "
                "ORDER BY display_order"
            )
        ]


def locked_review_implementation_fingerprint() -> str:
    path = Path(__file__)
    digest = hashlib.sha256(
        b"safe_geocoding_pipeline:phase03_locked_review_implementation_v1\0"
    )
    digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def run_locked_review(
    *,
    progress_database: Path,
    context_path: Path,
    input_function: Any = input,
    output_function: Any = print,
) -> None:
    """Run a dependency-free protected terminal review, saving before advance."""
    context_file = pq.ParquetFile(
        context_path, page_checksum_verification=True, pre_buffer=True
    )
    if not context_file.schema_arrow.remove_metadata().equals(
        locked_review_context_schema(), check_metadata=False
    ):
        raise ValueError("LOCKED review context schema mismatch")
    context_rows = {
        str(row["hashed_review_id"]): row
        for row in context_file.read(use_threads=False).to_pylist()
    }
    with LockedReviewStore(progress_database) as store:
        metadata = store.metadata()
        if file_sha256(context_path) != metadata[
            "context_sha256"
        ] or context_path.stat().st_size != int(metadata["context_size_bytes"]):
            raise ValueError("LOCKED review context binding changed")
        pending = store.pending_ids()
        for index, hashed in enumerate(pending, start=1):
            row = context_rows[hashed]
            output_function(f"LOCKED review {index}/{len(pending)}")
            for field in (
                "street_address_line_1",
                "street_address_line_2",
                "street_address_line_3",
                "street_address_line_4",
                "street_address_line_1_native",
                "street_address_line_2_native",
                "street_address_line_3_native",
                "street_address_line_4_native",
                "postcode",
                "city",
                "region_in_country",
                "country_iso_code",
            ):
                output_function(f"{field}: {row[field]}")
            protected_core_fields = (
                "street_clean",
                "house_number_clean",
                "unit_clean",
                "floor_clean",
                "building_clean",
                "organization_clean",
                "postcode_clean",
                "locality_clean",
                "region_clean",
                "country_clean",
                "address_parse_status",
                "address_completeness_class",
                "address_conflict_flags",
                "address_diagnostic_flags",
                "selected_component_provenance",
            )
            for label, source in (
                ("baseline", row["baseline_core_json"]),
                ("candidate", row["candidate_core_json"]),
            ):
                parsed = json.loads(str(source))
                output_function(
                    f"{label}: "
                    + json.dumps(
                        {field: parsed[field] for field in protected_core_fields},
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
            evidence = json.loads(str(row["candidate_evidence_json"]))
            for item in evidence:
                for prohibited in (
                    "stable_source_row_id_v1",
                    "source_file",
                    "source_logical_record_number",
                ):
                    item.pop(prohibited, None)
            output_function(
                "evidence: " + json.dumps(evidence, ensure_ascii=False, sort_keys=True)
            )
            if (
                input_function("Enter q to save no label and quit, or press Enter: ")
                .strip()
                .lower()
                == "q"
            ):
                return
            labels: dict[str, str] = {}
            vocabularies: dict[str, Sequence[str]] = {
                "street_label": COMPONENT_LABEL_VALUES,
                "house_number_label": COMPONENT_LABEL_VALUES,
                "joint_street_house_label": JOINT_LABEL_VALUES,
                "residual_role_label": RESIDUAL_ROLE_VALUES,
                "candidate_support_label": CANDIDATE_SUPPORT_VALUES,
                "conflict_correctness_label": (
                    "CORRECT",
                    "INCORRECT",
                    "NOT_APPLICABLE",
                    "CANNOT_ASSESS",
                ),
                "parser_overreach_label": ERROR_CONDITION_LABEL_VALUES,
                "missed_information_label": ERROR_CONDITION_LABEL_VALUES,
                "unsafe_handling_label": ERROR_CONDITION_LABEL_VALUES,
                "overall_parse_acceptability_label": OVERALL_LABEL_VALUES,
            }
            for field in LOCKED_LABEL_FIELDS:
                allowed = vocabularies[field]
                while True:
                    value = input_function(f"{field} {tuple(allowed)}: ").strip()
                    if value in allowed:
                        labels[field] = value
                        break
            reasons = [
                value.strip()
                for value in input_function("reason codes (comma-separated): ").split(
                    ","
                )
                if value.strip()
            ]
            note = input_function("protected note (optional, max 500): ") or None
            store.save_completed(
                hashed,
                labels,
                reasons,
                protected_note=note,
                timestamp_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            )
            output_function("saved")


def validate_locked_preflight(
    *,
    phase02_manifest_path: Path,
    phase02_input_paths: Sequence[Path],
    locked_identities_path: Path,
    pilot_seal_path: Path,
    output_path: Path,
    workflow_git_commit: str,
    production: bool,
) -> dict[str, JsonValue]:
    """Validate sealed identities and immutable inputs without reading row payload."""
    if production:
        require_goethe_nhr_slurm("phase03.locked-evaluation-preflight")
    contract = LockedEvaluationContract()
    contract.validate()
    if not _LOWER_HEX_40.fullmatch(workflow_git_commit):
        raise ValueError("LOCKED workflow Git commit is invalid")
    manifest, manifest_identity = validate_explicit_phase02_inputs(
        phase02_manifest_path, phase02_input_paths, production=production
    )
    if (
        production
        and phase02_manifest_identity(phase02_manifest_path) != manifest_identity
    ):
        raise Phase03Error("PHASE02_MANIFEST_IDENTITY_MISMATCH")
    metadata, identities = read_frozen_locked_identity_set(locked_identities_path)
    if metadata.get("manifest_identity") != manifest_identity:
        raise Phase03Error("LOCKED_IDENTITY_SET_MISMATCH")
    observed_digest = identity_digest(b"phase03:locked_identities_v1\0", identities)
    if production and file_sha256(pilot_seal_path) != FROZEN_PILOT_SEAL_SHA256:
        raise Phase03Error("LOCKED_PILOT_SEAL_HASH_MISMATCH")
    seal = json.loads(pilot_seal_path.read_text(encoding="utf-8"))
    if (
        seal.get("pilot_seal_version") != "phase03_pilot_seal_v1"
        or seal.get("locked_evaluation_count") != FROZEN_LOCKED_COUNT
        or seal.get("locked_evaluation_identity_digest") != observed_digest
        or seal.get("sampling_contract_fingerprint") != FROZEN_SAMPLING_CONTRACT_SHA256
        or seal.get("input_phase02_manifest_identity") != manifest_identity
        or seal.get("sampling_config_fingerprint")
        != metadata.get("sampling_config_fingerprint")
    ):
        raise Phase03Error("LOCKED_PILOT_SEAL_CONTENT_MISMATCH")
    registry = load_rule_registry(registry_version=RULE_REGISTRY_VERSION_V5)
    if registry.fingerprint != FROZEN_REGISTRY_SHA256:
        raise Phase03Error("LOCKED_RULE_REGISTRY_MISMATCH")
    payload: dict[str, JsonValue] = {
        "preflight_version": LOCKED_PREFLIGHT_VERSION,
        "status": "PASS_NO_LOCKED_PAYLOAD_ROWS_READ",
        "protocol_version": contract.protocol_version,
        "protocol_fingerprint": contract.fingerprint(),
        "workflow_git_commit": workflow_git_commit,
        "candidate_git_commit": FROZEN_CANDIDATE_COMMIT,
        "phase02_run_id": str(manifest.get("run_id")),
        "phase02_manifest_identity": manifest_identity,
        "phase02_shard_count": len(phase02_input_paths),
        "locked_identity_count": len(identities),
        "locked_identity_digest": observed_digest,
        "pilot_seal_sha256": file_sha256(pilot_seal_path),
        "sampling_contract_sha256": FROZEN_SAMPLING_CONTRACT_SHA256,
        "registry_version": registry.registry_version,
        "registry_sha256": registry.fingerprint,
        "locked_payload_rows_read": 0,
        "locked_payload_opened": False,
        "output_contract": "OWNER_ONLY_ATOMIC_NEW_RUN",
    }
    _atomic_json(output_path, payload)
    return payload


def validate_preflight_report(
    path: Path, *, workflow_git_commit: str
) -> dict[str, Any]:
    """Require the immutable PASS report before any LOCKED payload is opened."""
    if not path.is_file() or path.is_symlink():
        raise ValueError("LOCKED preflight report is missing or is a symlink")
    payload = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    expected = {
        "preflight_version": LOCKED_PREFLIGHT_VERSION,
        "status": "PASS_NO_LOCKED_PAYLOAD_ROWS_READ",
        "protocol_version": LOCKED_EVALUATION_PROTOCOL_VERSION,
        "protocol_fingerprint": LockedEvaluationContract().fingerprint(),
        "workflow_git_commit": workflow_git_commit,
        "candidate_git_commit": FROZEN_CANDIDATE_COMMIT,
        "phase02_shard_count": 206,
        "locked_identity_count": FROZEN_LOCKED_COUNT,
        "locked_identity_digest": FROZEN_LOCKED_IDENTITY_DIGEST,
        "pilot_seal_sha256": FROZEN_PILOT_SEAL_SHA256,
        "sampling_contract_sha256": FROZEN_SAMPLING_CONTRACT_SHA256,
        "registry_version": RULE_REGISTRY_VERSION_V5,
        "registry_sha256": FROZEN_REGISTRY_SHA256,
        "locked_payload_rows_read": 0,
        "locked_payload_opened": False,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError("LOCKED preflight report does not match frozen protocol")
    return payload


def materialize_locked_payload(
    input_paths: Sequence[Path],
    output_path: Path,
    *,
    locked_ids: set[bytes],
    batch_rows: int = 25_000,
    expected_count: int = FROZEN_LOCKED_COUNT,
    expected_identity_digest: str | None = FROZEN_LOCKED_IDENTITY_DIGEST,
    production: bool,
) -> int:
    if production:
        require_goethe_nhr_slurm("phase03.locked-evaluation-materialize")
    if len(locked_ids) != expected_count:
        raise ValueError("LOCKED identity count differs from frozen contract")
    if (
        expected_identity_digest is not None
        and identity_digest(b"phase03:locked_identities_v1\0", sorted(locked_ids))
        != expected_identity_digest
    ):
        raise ValueError("LOCKED identity digest differs from frozen contract")
    found: set[bytes] = set()
    output_batches: list[pa.RecordBatch] = []
    for path in input_paths:
        parquet = pq.ParquetFile(path, page_checksum_verification=True, pre_buffer=True)
        if not exact_schema_matches(parquet.schema_arrow):
            raise Phase03Error("PHASE02_SCHEMA_MISMATCH")
        for batch in parquet.iter_batches(batch_size=batch_rows, use_threads=False):
            ids = batch.column(batch.schema.get_field_index("stable_source_row_id_v1"))
            keep: list[int] = []
            for index, value in enumerate(ids.to_pylist()):
                identity = bytes(value)
                if identity not in locked_ids:
                    continue
                if identity in found:
                    raise ValueError("LOCKED identity appears more than once")
                found.add(identity)
                keep.append(index)
            if keep:
                output_batches.append(batch.take(pa.array(keep, type=pa.int64())))
    if found != locked_ids:
        raise ValueError("expected LOCKED identity is missing")
    table = pa.Table.from_batches(output_batches, schema=base_staging_schema())
    observed = {bytes(value) for value in table["stable_source_row_id_v1"].to_pylist()}
    if observed != locked_ids or table.num_rows != expected_count:
        raise ValueError("LOCKED-only join reconciliation failed")
    output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_path.parent.chmod(0o700)
    temporary = output_path.with_name(f".{output_path.name}.tmp")
    if output_path.exists() or temporary.exists():
        raise FileExistsError("LOCKED payload output exists")
    pq.write_table(
        table,
        temporary,
        compression="zstd",
        compression_level=3,
        row_group_size=batch_rows,
        write_statistics=False,
        write_page_checksum=True,
    )
    temporary.chmod(0o600)
    verified = pq.ParquetFile(
        temporary, page_checksum_verification=True, pre_buffer=True
    ).read(use_threads=False)
    if (
        verified.num_rows != expected_count
        or {bytes(value) for value in verified["stable_source_row_id_v1"].to_pylist()}
        != locked_ids
    ):
        raise ValueError("LOCKED payload read-back mismatch")
    os.replace(temporary, output_path)
    output_path.chmod(0o600)
    with output_path.open("rb") as stream:
        os.fsync(stream.fileno())
    _fsync_parent(output_path)
    return int(verified.num_rows)


def transform_locked_payload(
    input_path: Path,
    output_directory: Path,
    *,
    engine: Phase03Engine,
    config: Phase03Config,
    metadata: Mapping[str, str],
    expected_locked_ids: set[bytes],
    production: bool,
) -> ShardWriteResult:
    if production:
        require_goethe_nhr_slurm("phase03.locked-evaluation-transform")
    if engine.execution_scope != "LOCKED_EVALUATION":
        raise ValueError("LOCKED transform requires LOCKED_EVALUATION engine scope")
    parquet = pq.ParquetFile(
        input_path, page_checksum_verification=True, pre_buffer=True
    )
    if not exact_schema_matches(parquet.schema_arrow):
        raise Phase03Error("PHASE02_SCHEMA_MISMATCH")
    rows = parquet.read(use_threads=False).to_pylist()
    observed = {bytes(row["stable_source_row_id_v1"]) for row in rows}
    if (
        len(rows) != FROZEN_LOCKED_COUNT
        or len(observed) != FROZEN_LOCKED_COUNT
        or observed != expected_locked_ids
    ):
        raise Phase03Error("LOCKED_PAYLOAD_COUNT_OR_IDENTITY_MISMATCH")
    results = [engine.transform(row) for row in rows]
    core_rows = [result.core_row for result in results]
    evidence_rows = [row for result in results for row in result.evidence_rows]
    work = output_directory / ".in_progress"
    core = output_directory / "core" / "locked_evaluation.parquet"
    evidence = output_directory / "evidence" / "locked_evaluation.parquet"
    work.mkdir(parents=True, exist_ok=False, mode=0o700)
    result = write_validate_and_promote_synthetic_shard(
        core_rows=core_rows,
        evidence_rows=evidence_rows,
        temporary_core=work / "core.parquet.tmp",
        temporary_evidence=work / "evidence.parquet.tmp",
        final_core=core,
        final_evidence=evidence,
        config=config,
        metadata=dict(metadata),
    )
    work.rmdir()
    return result


def transform_locked_pair_atomically(
    input_path: Path,
    output_root: Path,
    *,
    baseline_engine: Phase03Engine,
    candidate_engine: Phase03Engine,
    expected_locked_ids: set[bytes],
    metadata: Mapping[str, str],
    production: bool,
) -> tuple[ShardWriteResult, ShardWriteResult]:
    """Transform both frozen parsers and promote the pair as one directory."""
    if output_root.exists():
        raise FileExistsError("LOCKED transform output already exists")
    temporary = output_root.with_name(f".{output_root.name}.transform.{os.getpid()}")
    temporary.mkdir(parents=True, exist_ok=False, mode=0o700)
    temporary.chmod(0o700)
    try:
        baseline = transform_locked_payload(
            input_path,
            temporary / "baseline",
            engine=baseline_engine,
            config=Phase03Config.for_parser_version(PARSER_VERSION_V2_1),
            metadata={**metadata, "parser_role": "FROZEN_BASELINE"},
            expected_locked_ids=expected_locked_ids,
            production=production,
        )
        candidate = transform_locked_payload(
            input_path,
            temporary / "candidate",
            engine=candidate_engine,
            config=Phase03Config.for_parser_version(PARSER_VERSION_V3_2),
            metadata={**metadata, "parser_role": "FROZEN_CANDIDATE"},
            expected_locked_ids=expected_locked_ids,
            production=production,
        )
        os.replace(temporary, output_root)
        output_root.chmod(0o700)
        _fsync_parent(output_root)
        return baseline, candidate
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise


def build_locked_engines(
    *,
    implementation_fingerprint: bytes,
    country_reference: Any,
    script_reference: Any,
) -> tuple[Phase03Engine, Phase03Engine]:
    baseline_config = Phase03Config.for_parser_version(PARSER_VERSION_V2_1)
    candidate_config = Phase03Config.for_parser_version(PARSER_VERSION_V3_2)
    baseline = Phase03Engine(
        baseline_config,
        load_rule_registry(registry_version=RULE_REGISTRY_VERSION_V3),
        country_reference=country_reference,
        script_reference=script_reference,
        implementation_fingerprint=implementation_fingerprint,
        execution_scope="LOCKED_EVALUATION",
    )
    candidate = Phase03Engine(
        candidate_config,
        load_rule_registry(registry_version=RULE_REGISTRY_VERSION_V5),
        country_reference=country_reference,
        script_reference=script_reference,
        implementation_fingerprint=implementation_fingerprint,
        execution_scope="LOCKED_EVALUATION",
        locked_evaluation_protocol_version=LOCKED_EVALUATION_PROTOCOL_VERSION,
    )
    if (
        baseline.configuration_fingerprint.hex()
        != FROZEN_LOCKED_BASELINE_CONFIGURATION_SHA256
        or candidate.configuration_fingerprint.hex()
        != FROZEN_LOCKED_CONFIGURATION_SHA256
    ):
        raise Phase03Error("LOCKED_EFFECTIVE_CONFIGURATION_MISMATCH")
    return baseline, candidate


@dataclass(frozen=True, slots=True)
class LockedComparison:
    rows: int
    scientific_change_rows: int
    experimental_evidence_rows: int
    overlap_rows: int
    changed_without_experimental_evidence: int
    unrelated_component_regressions: int
    lost_existing_selections: int
    identity_order_equal: bool
    changed_field_counts: tuple[tuple[str, int], ...]
    unrelated_changed_field_counts: tuple[tuple[str, int], ...]
    country_parse_method_change_rows: int
    native_component_change_rows: int
    experimental_rule_counts: tuple[tuple[str, int, int], ...]


def compare_locked_outputs(
    baseline_rows: Sequence[Mapping[str, Any]],
    candidate_rows: Sequence[Mapping[str, Any]],
    candidate_evidence: Sequence[Mapping[str, Any]],
    *,
    expected_rows: int = FROZEN_LOCKED_COUNT,
) -> LockedComparison:
    if len(baseline_rows) != expected_rows or len(candidate_rows) != expected_rows:
        raise ValueError("LOCKED comparison row count mismatch")
    baseline_ids = [bytes(row["stable_source_row_id_v1"]) for row in baseline_rows]
    candidate_ids = [bytes(row["stable_source_row_id_v1"]) for row in candidate_rows]
    if baseline_ids != candidate_ids or len(set(baseline_ids)) != expected_rows:
        raise ValueError("LOCKED comparison identity/order mismatch")
    changed: set[bytes] = set()
    unrelated = 0
    lost = 0
    changed_field_counts: Counter[str] = Counter()
    unrelated_changed_field_counts: Counter[str] = Counter()
    country_parse_method_change_rows = 0
    native_component_change_rows = 0
    for baseline, candidate in zip(baseline_rows, candidate_rows, strict=True):
        identity = bytes(baseline["stable_source_row_id_v1"])
        changed_fields = {
            field
            for field in SCIENTIFIC_CORE_FIELDS
            if baseline[field] != candidate[field]
        }
        if changed_fields:
            changed.add(identity)
            changed_field_counts.update(changed_fields)
        unrelated_fields = changed_fields - LOCKED_ALLOWED_CHANGE_FIELDS
        if unrelated_fields:
            unrelated += 1
            unrelated_changed_field_counts.update(unrelated_fields)
        if "country_parse_method" in changed_fields:
            country_parse_method_change_rows += 1
        if any(field.endswith("_native_clean") for field in changed_fields):
            native_component_change_rows += 1
        for field in ("street_clean", "house_number_clean"):
            if baseline[field] is not None and candidate[field] != baseline[field]:
                lost += 1
                break
    evidence_ids = {
        bytes(row["stable_source_row_id_v1"])
        for row in candidate_evidence
        if row.get("rule_id") in LOCKED_V5_RULE_IDS
    }
    rule_counts = tuple(
        (
            rule_id,
            sum(row.get("rule_id") == rule_id for row in candidate_evidence),
            sum(
                row.get("rule_id") == rule_id and bool(row.get("selected"))
                for row in candidate_evidence
            ),
        )
        for rule_id in LOCKED_V5_RULE_IDS
    )
    return LockedComparison(
        rows=len(baseline_rows),
        scientific_change_rows=len(changed),
        experimental_evidence_rows=len(evidence_ids),
        overlap_rows=len(changed & evidence_ids),
        changed_without_experimental_evidence=len(changed - evidence_ids),
        unrelated_component_regressions=unrelated,
        lost_existing_selections=lost,
        identity_order_equal=True,
        changed_field_counts=tuple(sorted(changed_field_counts.items())),
        unrelated_changed_field_counts=tuple(
            sorted(unrelated_changed_field_counts.items())
        ),
        country_parse_method_change_rows=country_parse_method_change_rows,
        native_component_change_rows=native_component_change_rows,
        experimental_rule_counts=rule_counts,
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return value


def _json_text(value: Any) -> str:
    return json.dumps(_json_safe(value), sort_keys=True, separators=(",", ":"))


def _locked_hashed_review_id(identity: bytes, locked_evaluation_version: str) -> str:
    digest = hashlib.sha256(b"safe_geocoding_pipeline:phase03_locked_review_id_v1\0")
    encoded = locked_evaluation_version.encode("utf-8")
    digest.update(len(encoded).to_bytes(8, "big"))
    digest.update(encoded)
    digest.update(identity)
    return digest.hexdigest()


def _read_core(path: Path) -> list[dict[str, Any]]:
    parquet = pq.ParquetFile(path, page_checksum_verification=True, pre_buffer=True)
    if not exact_core_schema_matches(parquet.schema_arrow):
        raise ValueError("LOCKED core schema mismatch")
    return cast(list[dict[str, Any]], parquet.read(use_threads=False).to_pylist())


def _read_evidence(path: Path) -> list[dict[str, Any]]:
    parquet = pq.ParquetFile(path, page_checksum_verification=True, pre_buffer=True)
    if not exact_evidence_schema_matches(parquet.schema_arrow):
        raise ValueError("LOCKED evidence schema mismatch")
    return cast(list[dict[str, Any]], parquet.read(use_threads=False).to_pylist())


def _script_family(row: Mapping[str, Any], script_reference: Any) -> str:
    scripts: set[str] = set()
    for field in (
        "street_address_line_1",
        "street_address_line_2",
        "street_address_line_3",
        "street_address_line_4",
        "street_address_line_1_native",
        "street_address_line_2_native",
        "street_address_line_3_native",
        "street_address_line_4_native",
    ):
        scripts.update(script_reference.distinctive_scripts(str(row[field])))
    if not scripts:
        return "UNDETERMINED"
    if len(scripts) == 1:
        value = next(iter(scripts))
        return "LATIN" if value == "Latin" else f"NON_LATIN:{value}"
    return "MIXED"


def prepare_locked_review_artifacts(
    *,
    locked_payload_path: Path,
    baseline_core_path: Path,
    baseline_evidence_path: Path,
    candidate_core_path: Path,
    candidate_evidence_path: Path,
    output_directory: Path,
    locked_evaluation_version: str,
    script_reference: Any,
    implementation_commit: str,
    production: bool,
) -> dict[str, JsonValue]:
    if production:
        require_goethe_nhr_slurm("phase03.locked-evaluation-review-prepare")
    if output_directory.exists():
        raise FileExistsError("LOCKED review output already exists")
    if not locked_evaluation_version or not _LOWER_HEX_40.fullmatch(
        implementation_commit
    ):
        raise ValueError("LOCKED review provenance is invalid")
    payload_file = pq.ParquetFile(
        locked_payload_path, page_checksum_verification=True, pre_buffer=True
    )
    if not exact_schema_matches(payload_file.schema_arrow):
        raise ValueError("LOCKED payload schema mismatch")
    payload = payload_file.read(use_threads=False)
    if payload.num_rows != FROZEN_LOCKED_COUNT:
        raise ValueError("LOCKED payload row count mismatch")
    payload_rows = cast(list[dict[str, Any]], payload.to_pylist())
    payload_ids = [bytes(row["stable_source_row_id_v1"]) for row in payload_rows]
    if len(set(payload_ids)) != FROZEN_LOCKED_COUNT:
        raise ValueError("LOCKED payload identities are not unique")

    baseline = _read_core(baseline_core_path)
    baseline_evidence = _read_evidence(baseline_evidence_path)
    candidate = _read_core(candidate_core_path)
    candidate_evidence = _read_evidence(candidate_evidence_path)
    validate_core_evidence_relationship(baseline, baseline_evidence)
    validate_core_evidence_relationship(candidate, candidate_evidence)
    if [bytes(row["stable_source_row_id_v1"]) for row in baseline] != payload_ids or [
        bytes(row["stable_source_row_id_v1"]) for row in candidate
    ] != payload_ids:
        raise ValueError("LOCKED payload/core identity order mismatch")
    if {row["parser_version"] for row in baseline} != {PARSER_VERSION_V2_1} or {
        row["parser_version"] for row in candidate
    } != {PARSER_VERSION_V3_2}:
        raise ValueError("LOCKED parser version mismatch")
    if {row["rule_registry_version"] for row in baseline} != {
        RULE_REGISTRY_VERSION_V3
    } or {row["rule_registry_version"] for row in candidate} != {
        RULE_REGISTRY_VERSION_V5
    }:
        raise ValueError("LOCKED registry version mismatch")
    comparison = compare_locked_outputs(baseline, candidate, candidate_evidence)
    if comparison.changed_without_experimental_evidence:
        raise ValueError("LOCKED scientific change lacks V5 experimental evidence")

    baseline_by_id = {bytes(row["stable_source_row_id_v1"]): row for row in baseline}
    candidate_by_id = {bytes(row["stable_source_row_id_v1"]): row for row in candidate}
    baseline_evidence_by_id: dict[bytes, list[dict[str, Any]]] = {}
    candidate_evidence_by_id: dict[bytes, list[dict[str, Any]]] = {}
    for row in baseline_evidence:
        baseline_evidence_by_id.setdefault(
            bytes(row["stable_source_row_id_v1"]), []
        ).append(row)
    for row in candidate_evidence:
        candidate_evidence_by_id.setdefault(
            bytes(row["stable_source_row_id_v1"]), []
        ).append(row)

    candidates: list[LockedReviewCandidate] = []
    for payload_row in payload_rows:
        identity = bytes(payload_row["stable_source_row_id_v1"])
        baseline_row = baseline_by_id[identity]
        candidate_row = candidate_by_id[identity]
        changed = any(
            baseline_row[field] != candidate_row[field]
            for field in SCIENTIFIC_CORE_FIELDS
        )
        v5_rows = [
            row
            for row in candidate_evidence_by_id.get(identity, [])
            if row.get("rule_id") in LOCKED_V5_RULE_IDS
        ]
        evidence_state = (
            "SELECTED"
            if any(bool(row["selected"]) for row in v5_rows)
            else "UNSELECTED"
            if v5_rows
            else "NONE"
        )
        country = candidate_row["country_clean"]
        candidates.append(
            LockedReviewCandidate(
                identity,
                changed,
                evidence_state,
                f"COUNTRY:{country}" if country is not None else "COUNTRY:UNRESOLVED",
                _script_family(payload_row, script_reference),
                str(candidate_row["address_parse_status"]),
                str(candidate_row["address_completeness_class"]),
                "CONFLICT_PRESENT"
                if candidate_row["address_conflict_flags"]
                else "NO_CONFLICT",
            )
        )
    selection = select_locked_review_population(candidates)
    selected = set(selection.review_ids)
    double = set(selection.double_review_ids)
    r01_order = {
        identity: index for index, identity in enumerate(selection.reviewer_one_order)
    }
    r02_order = {
        identity: index for index, identity in enumerate(selection.reviewer_two_order)
    }
    context_rows: list[dict[str, Any]] = []
    template_rows: list[dict[str, Any]] = []
    for payload_row in payload_rows:
        identity = bytes(payload_row["stable_source_row_id_v1"])
        if identity not in selected:
            continue
        baseline_row = baseline_by_id[identity]
        candidate_row = candidate_by_id[identity]
        v5_rows = [
            row
            for row in candidate_evidence_by_id.get(identity, [])
            if row.get("rule_id") in LOCKED_V5_RULE_IDS
        ]
        metadata = {
            "scientific_output_changed": any(
                baseline_row[field] != candidate_row[field]
                for field in SCIENTIFIC_CORE_FIELDS
            ),
            "experimental_evidence_present": bool(v5_rows),
            "experimental_selected": any(bool(row["selected"]) for row in v5_rows),
            "street_selected": candidate_row["street_clean"] is not None,
            "house_number_selected": candidate_row["house_number_clean"] is not None,
            "conflict_present": bool(candidate_row["address_conflict_flags"]),
            "evidence_sidecar_present": bool(candidate_evidence_by_id.get(identity)),
            "country_group": (
                f"COUNTRY:{candidate_row['country_clean']}"
                if candidate_row["country_clean"] is not None
                else "COUNTRY:UNRESOLVED"
            ),
            "script_family": _script_family(payload_row, script_reference),
            "parse_status": str(candidate_row["address_parse_status"]),
            "completeness": str(candidate_row["address_completeness_class"]),
            "conflict_state": (
                "CONFLICT_PRESENT"
                if candidate_row["address_conflict_flags"]
                else "NO_CONFLICT"
            ),
            "experimental_evidence_state": (
                "SELECTED"
                if any(bool(row["selected"]) for row in v5_rows)
                else "UNSELECTED"
                if v5_rows
                else "NONE"
            ),
            "parser_change_state": (
                "CHANGED"
                if any(
                    baseline_row[field] != candidate_row[field]
                    for field in SCIENTIFIC_CORE_FIELDS
                )
                else "UNCHANGED"
            ),
        }
        hashed = _locked_hashed_review_id(identity, locked_evaluation_version)
        context_rows.append(
            {
                **payload_row,
                "hashed_review_id": hashed,
                "baseline_core_json": _json_text(baseline_row),
                "candidate_core_json": _json_text(candidate_row),
                "baseline_evidence_json": _json_text(
                    baseline_evidence_by_id.get(identity, [])
                ),
                "candidate_evidence_json": _json_text(
                    candidate_evidence_by_id.get(identity, [])
                ),
                "locked_case_metadata_json": _json_text(metadata),
            }
        )
        template_rows.append(
            {
                "hashed_review_id": hashed,
                "locked_evaluation_version": locked_evaluation_version,
                "is_independent_review": identity in double,
                "r01_display_order": r01_order[identity],
                "r02_display_order": r02_order.get(identity),
            }
        )
    if len(context_rows) != 400 or len(template_rows) != 400:
        raise ValueError("LOCKED review artifact row count mismatch")
    context_rows.sort(key=lambda row: str(row["hashed_review_id"]))
    template_rows.sort(key=lambda row: str(row["hashed_review_id"]))

    temporary = output_directory.with_name(
        f".{output_directory.name}.prepare.{os.getpid()}"
    )
    temporary.mkdir(parents=True, exist_ok=False, mode=0o700)
    temporary.chmod(0o700)
    try:
        context_path = temporary / "protected_locked_review_context.parquet"
        template_path = temporary / "protected_locked_review_template.parquet"
        manifest_path = temporary / "locked_review_input_manifest.json"
        pq.write_table(
            pa.Table.from_pylist(context_rows, schema=locked_review_context_schema()),
            context_path,
            compression="zstd",
            compression_level=3,
            write_statistics=False,
            write_page_checksum=True,
        )
        pq.write_table(
            pa.Table.from_pylist(template_rows, schema=locked_review_template_schema()),
            template_path,
            compression="zstd",
            compression_level=3,
            write_statistics=False,
            write_page_checksum=True,
        )
        context_path.chmod(0o600)
        template_path.chmod(0o600)
        verified_context = pq.ParquetFile(
            context_path, page_checksum_verification=True, pre_buffer=True
        )
        verified_template = pq.ParquetFile(
            template_path, page_checksum_verification=True, pre_buffer=True
        )
        if (
            verified_context.metadata.num_rows != 400
            or verified_template.metadata.num_rows != 400
            or not verified_context.schema_arrow.remove_metadata().equals(
                locked_review_context_schema(), check_metadata=False
            )
            or not verified_template.schema_arrow.remove_metadata().equals(
                locked_review_template_schema(), check_metadata=False
            )
        ):
            raise ValueError("LOCKED review artifact read-back failed")
        manifest: dict[str, JsonValue] = {
            "manifest_version": "phase03_locked_review_input_manifest_v1",
            "status": "LOCKED_REVIEW_INPUT_PREPARED_NO_LABELS",
            "locked_evaluation_version": locked_evaluation_version,
            "protocol_version": LOCKED_EVALUATION_PROTOCOL_VERSION,
            "implementation_commit": implementation_commit,
            "implementation_fingerprint": locked_review_implementation_fingerprint(),
            "review_selection_version": LOCKED_REVIEW_SELECTION_VERSION,
            "review_seed": LOCKED_REVIEW_SEED,
            "review_count": 400,
            "double_review_count": 100,
            "review_population_digest": selection.review_identity_digest,
            "double_review_population_digest": selection.double_review_identity_digest,
            "selection_diagnostics": list(selection.selection_diagnostics),
            "comparison": cast(dict[str, JsonValue], asdict(comparison)),
            "input_artifacts": {
                "locked_payload": {
                    "sha256": file_sha256(locked_payload_path),
                    "size_bytes": locked_payload_path.stat().st_size,
                },
                "baseline_core": {
                    "sha256": file_sha256(baseline_core_path),
                    "size_bytes": baseline_core_path.stat().st_size,
                },
                "baseline_evidence": {
                    "sha256": file_sha256(baseline_evidence_path),
                    "size_bytes": baseline_evidence_path.stat().st_size,
                },
                "candidate_core": {
                    "sha256": file_sha256(candidate_core_path),
                    "size_bytes": candidate_core_path.stat().st_size,
                },
                "candidate_evidence": {
                    "sha256": file_sha256(candidate_evidence_path),
                    "size_bytes": candidate_evidence_path.stat().st_size,
                },
            },
            "output_artifacts": {
                "protected_context": {
                    "artifact_name": context_path.name,
                    "sha256": file_sha256(context_path),
                    "size_bytes": context_path.stat().st_size,
                },
                "protected_template": {
                    "artifact_name": template_path.name,
                    "sha256": file_sha256(template_path),
                    "size_bytes": template_path.stat().st_size,
                },
            },
            "raw_values_reported": False,
            "identities_reported": False,
        }
        _atomic_json(manifest_path, manifest)
        os.replace(temporary, output_directory)
        output_directory.chmod(0o700)
        _fsync_parent(output_directory)
        return manifest
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise


def initialize_locked_review_workspace(
    *,
    context_path: Path,
    template_path: Path,
    input_manifest_path: Path,
    output_directory: Path,
    implementation_commit: str,
) -> tuple[Path, Path]:
    if output_directory.exists():
        raise FileExistsError("LOCKED review workspace already exists")
    manifest = json.loads(input_manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("manifest_version") != "phase03_locked_review_input_manifest_v1"
        or manifest.get("status") != "LOCKED_REVIEW_INPUT_PREPARED_NO_LABELS"
        or manifest.get("review_count") != 400
        or manifest.get("double_review_count") != 100
        or manifest.get("implementation_commit") != implementation_commit
    ):
        raise ValueError("LOCKED review input manifest mismatch")
    output_artifacts = cast(dict[str, Any], manifest["output_artifacts"])
    if (
        file_sha256(context_path) != output_artifacts["protected_context"]["sha256"]
        or file_sha256(template_path)
        != output_artifacts["protected_template"]["sha256"]
    ):
        raise ValueError("LOCKED review input artifact hash mismatch")
    context = pq.ParquetFile(
        context_path, page_checksum_verification=True, pre_buffer=True
    )
    template_file = pq.ParquetFile(
        template_path, page_checksum_verification=True, pre_buffer=True
    )
    if (
        context.metadata.num_rows != 400
        or template_file.metadata.num_rows != 400
        or not context.schema_arrow.remove_metadata().equals(
            locked_review_context_schema(), check_metadata=False
        )
        or not template_file.schema_arrow.remove_metadata().equals(
            locked_review_template_schema(), check_metadata=False
        )
    ):
        raise ValueError("LOCKED review inputs fail schema/count validation")
    template = template_file.read(use_threads=False).to_pylist()
    if sum(bool(row["is_independent_review"]) for row in template) != 100:
        raise ValueError("LOCKED review double-review designation mismatch")
    binding = LockedReviewBinding(
        locked_evaluation_version=str(manifest["locked_evaluation_version"]),
        context_sha256=file_sha256(context_path),
        context_size_bytes=context_path.stat().st_size,
        template_sha256=file_sha256(template_path),
        template_size_bytes=template_path.stat().st_size,
        population_digest=str(manifest["review_population_digest"]),
        implementation_commit=implementation_commit,
        implementation_fingerprint=str(manifest["implementation_fingerprint"]),
    )
    hashed_by_r01 = [
        str(row["hashed_review_id"])
        for row in sorted(template, key=lambda row: int(row["r01_display_order"]))
    ]
    double_ids = {
        str(row["hashed_review_id"])
        for row in template
        if bool(row["is_independent_review"])
    }
    hashed_by_r02 = [
        str(row["hashed_review_id"])
        for row in sorted(
            (row for row in template if bool(row["is_independent_review"])),
            key=lambda row: int(row["r02_display_order"]),
        )
    ]
    temporary = output_directory.with_name(
        f".{output_directory.name}.initialize.{os.getpid()}"
    )
    temporary.mkdir(parents=True, exist_ok=False, mode=0o700)
    temporary.chmod(0o700)
    try:
        first_path = temporary / "LOCKED-R01" / "review_progress.sqlite3"
        second_path = temporary / "LOCKED-R02" / "review_progress.sqlite3"
        with LockedReviewStore.create(
            first_path,
            binding=binding,
            reviewer_id="LOCKED-R01",
            ordered_hashed_ids=hashed_by_r01,
            double_review_hashed_ids=double_ids,
        ):
            pass
        with LockedReviewStore.create(
            second_path,
            binding=binding,
            reviewer_id="LOCKED-R02",
            ordered_hashed_ids=hashed_by_r02,
            double_review_hashed_ids=double_ids,
        ):
            pass
        os.replace(temporary, output_directory)
        output_directory.chmod(0o700)
        _fsync_parent(output_directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return (
        output_directory / "LOCKED-R01" / "review_progress.sqlite3",
        output_directory / "LOCKED-R02" / "review_progress.sqlite3",
    )


def export_completed_locked_labels(
    *,
    reviewer_one_database: Path,
    reviewer_two_database: Path,
    output_path: Path,
) -> Path:
    if output_path.exists():
        raise FileExistsError("LOCKED portable label export exists")
    with (
        LockedReviewStore(reviewer_one_database, readonly=True) as first,
        LockedReviewStore(reviewer_two_database, readonly=True) as second,
    ):
        first_metadata = first.metadata()
        second_metadata = second.metadata()
        first_binding = {
            key: value
            for key, value in first_metadata.items()
            if key
            not in {"reviewer_id", "assignment_role", "expected_assignment_count"}
        }
        second_binding = {
            key: value
            for key, value in second_metadata.items()
            if key
            not in {"reviewer_id", "assignment_role", "expected_assignment_count"}
        }
        if first_binding != second_binding:
            raise ValueError("LOCKED reviewer databases have different bindings")
        if (
            first_metadata.get("reviewer_id") != "LOCKED-R01"
            or first_metadata.get("assignment_role") != "PRIMARY"
            or second_metadata.get("reviewer_id") != "LOCKED-R02"
            or second_metadata.get("assignment_role") != "INDEPENDENT_SECOND"
        ):
            raise ValueError("LOCKED reviewer identity/role mismatch")
        if (
            first.summary()["status"] != "COMPLETE"
            or second.summary()["status"] != "COMPLETE"
        ):
            raise ValueError("LOCKED reviewer databases are incomplete")
        first_rows = first.completed_rows()
        second_rows = second.completed_rows()
    if len(first_rows) != 400 or len(second_rows) != 100:
        raise ValueError("LOCKED completed review counts differ from frozen contract")
    designated = {
        str(row["hashed_review_id"])
        for row in first_rows
        if row["is_independent_review"] is True
    }
    second_ids = {str(row["hashed_review_id"]) for row in second_rows}
    if (
        len(designated) != 100
        or second_ids != designated
        or not all(row["is_independent_review"] is True for row in second_rows)
    ):
        raise ValueError("LOCKED independent-review identity mismatch")
    rows = sorted(
        [*first_rows, *second_rows],
        key=lambda row: (
            str(row["hashed_review_id"]),
            str(row["reviewer_id"]).encode("utf-8"),
        ),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_path.parent.chmod(0o700)
    temporary = output_path.with_name(f".{output_path.name}.tmp")
    pq.write_table(
        pa.Table.from_pylist(rows, schema=locked_review_label_schema()),
        temporary,
        compression="zstd",
        compression_level=3,
        write_statistics=False,
        write_page_checksum=True,
    )
    temporary.chmod(0o600)
    verified = pq.ParquetFile(
        temporary, page_checksum_verification=True, pre_buffer=True
    )
    if (
        verified.metadata.num_rows != 500
        or not verified.schema_arrow.remove_metadata().equals(
            locked_review_label_schema(), check_metadata=False
        )
        or verified.read(use_threads=False).to_pylist() != rows
    ):
        raise ValueError("LOCKED portable-label read-back validation failed")
    os.replace(temporary, output_path)
    output_path.chmod(0o600)
    _fsync_parent(output_path)
    return output_path


def _load_context_metadata(context_path: Path) -> dict[str, dict[str, Any]]:
    parquet = pq.ParquetFile(
        context_path, page_checksum_verification=True, pre_buffer=True
    )
    if not parquet.schema_arrow.remove_metadata().equals(
        locked_review_context_schema(), check_metadata=False
    ):
        raise ValueError("LOCKED review context schema mismatch")
    result: dict[str, dict[str, Any]] = {}
    table = parquet.read(
        columns=["hashed_review_id", "locked_case_metadata_json"],
        use_threads=False,
    )
    for row in table.to_pylist():
        result[str(row["hashed_review_id"])] = cast(
            dict[str, Any], json.loads(str(row["locked_case_metadata_json"]))
        )
    if len(result) != 400:
        raise ValueError("LOCKED review context identity count mismatch")
    return result


def score_completed_locked_review(
    *,
    controlled_labels_path: Path,
    context_path: Path,
    review_input_manifest_path: Path,
    output_path: Path,
    machine_checks: Mapping[str, int | bool],
) -> dict[str, JsonValue]:
    validated_machine_checks = _validate_machine_checks(machine_checks)
    review_manifest = cast(
        dict[str, Any],
        json.loads(review_input_manifest_path.read_text(encoding="utf-8")),
    )
    comparison = review_manifest.get("comparison")
    output_artifacts = review_manifest.get("output_artifacts")
    if not isinstance(comparison, dict) or not isinstance(output_artifacts, dict):
        raise ValueError("LOCKED review input manifest is incomplete")
    if (
        review_manifest.get("manifest_version")
        != "phase03_locked_review_input_manifest_v1"
        or review_manifest.get("status") != "LOCKED_REVIEW_INPUT_PREPARED_NO_LABELS"
        or file_sha256(context_path)
        != output_artifacts.get("protected_context", {}).get("sha256")
        or int(validated_machine_checks["unexplained_scientific_changes"])
        != int(comparison.get("changed_without_experimental_evidence", -1))
        or int(validated_machine_checks["unrelated_component_regressions"])
        != int(comparison.get("unrelated_component_regressions", -1))
        or int(validated_machine_checks["lost_existing_selections"])
        != int(comparison.get("lost_existing_selections", -1))
    ):
        raise ValueError("LOCKED score inputs differ from review/comparison binding")
    labels_file = pq.ParquetFile(
        controlled_labels_path, page_checksum_verification=True, pre_buffer=True
    )
    if not labels_file.schema_arrow.remove_metadata().equals(
        locked_review_label_schema(), check_metadata=False
    ):
        raise ValueError("LOCKED controlled-label schema mismatch")
    rows = cast(list[dict[str, Any]], labels_file.read(use_threads=False).to_pylist())
    if len(rows) != 500:
        raise ValueError("LOCKED controlled-label record count mismatch")
    context = _load_context_metadata(context_path)
    first = {
        str(row["hashed_review_id"]): row
        for row in rows
        if row["reviewer_id"] == "LOCKED-R01"
    }
    second = {
        str(row["hashed_review_id"]): row
        for row in rows
        if row["reviewer_id"] == "LOCKED-R02"
    }
    if len(first) != 400 or len(second) != 100 or not set(second) <= set(first):
        raise ValueError("LOCKED reviewer row identity mismatch")
    agreements = tuple(
        cohen_kappa(
            [str(first[hashed][field]) for hashed in sorted(second)],
            [str(second[hashed][field]) for hashed in sorted(second)],
            field=field,
        )
        for field in LOCKED_AGREEMENT_FIELDS
    )

    def fraction(
        field: str,
        *,
        include: Any,
        correct: Any,
    ) -> MetricFraction:
        eligible = [
            (row, context[hashed])
            for hashed, row in first.items()
            if include(row, context[hashed])
        ]
        return MetricFraction(
            sum(bool(correct(row, metadata)) for row, metadata in eligible),
            len(eligible),
        )

    street = fraction(
        "street_label",
        include=lambda row, metadata: (
            metadata["street_selected"]
            and row["street_label"] in {"CORRECT", "INCORRECT"}
        ),
        correct=lambda row, _metadata: row["street_label"] == "CORRECT",
    )
    house = fraction(
        "house_number_label",
        include=lambda row, metadata: (
            metadata["house_number_selected"]
            and row["house_number_label"] in {"CORRECT", "INCORRECT"}
        ),
        correct=lambda row, _metadata: row["house_number_label"] == "CORRECT",
    )
    joint = fraction(
        "joint_street_house_label",
        include=lambda row, metadata: (
            metadata["experimental_selected"]
            and row["joint_street_house_label"] in {"CORRECT", "INCORRECT"}
        ),
        correct=lambda row, _metadata: row["joint_street_house_label"] == "CORRECT",
    )
    overreach = fraction(
        "parser_overreach_label",
        include=lambda row, _metadata: (
            row["parser_overreach_label"] in {"ABSENT", "PRESENT"}
        ),
        correct=lambda row, _metadata: row["parser_overreach_label"] == "PRESENT",
    )
    missed = fraction(
        "missed_information_label",
        include=lambda row, _metadata: (
            row["missed_information_label"] in {"ABSENT", "PRESENT"}
        ),
        correct=lambda row, _metadata: row["missed_information_label"] == "PRESENT",
    )
    conflict_precision = fraction(
        "conflict_correctness_label",
        include=lambda row, metadata: (
            metadata["conflict_present"]
            and row["conflict_correctness_label"] in {"CORRECT", "INCORRECT"}
        ),
        correct=lambda row, _metadata: row["conflict_correctness_label"] == "CORRECT",
    )
    detected = sum(
        metadata["conflict_present"] and row["conflict_correctness_label"] == "CORRECT"
        for hashed, row in first.items()
        for metadata in (context[hashed],)
    )
    missed_conflicts = sum(
        "MISSED_CONFLICT" in row["reason_codes"] for row in first.values()
    )
    conflict_recall = MetricFraction(detected, detected + missed_conflicts)
    evidence_coverage = MetricFraction(
        sum(
            bool(metadata["evidence_sidecar_present"]) for metadata in context.values()
        ),
        len(context),
    )
    false_negatives = sum(
        metadata["experimental_evidence_present"]
        and not metadata["experimental_selected"]
        and row["candidate_support_label"] == "SUPPORTED"
        for hashed, row in first.items()
        for metadata in (context[hashed],)
    )
    metrics = LockedMetricSet(
        joint,
        street,
        house,
        overreach,
        missed,
        false_negatives,
        conflict_precision,
        conflict_recall,
        evidence_coverage,
    )

    def stratum_fraction(
        hashed_ids: Sequence[str],
        label_field: str,
        eligible_values: set[str],
        correct_value: str,
        metadata_flag: str | None = None,
    ) -> dict[str, JsonValue]:
        eligible = [
            first[hashed][label_field]
            for hashed in hashed_ids
            if first[hashed][label_field] in eligible_values
            and (metadata_flag is None or bool(context[hashed][metadata_flag]))
        ]
        return MetricFraction(
            sum(value == correct_value for value in eligible), len(eligible)
        ).payload()

    stratified: dict[str, JsonValue] = {}
    for dimension in (
        "country_group",
        "script_family",
        "parse_status",
        "completeness",
        "conflict_state",
        "experimental_evidence_state",
        "parser_change_state",
    ):
        groups: dict[str, list[str]] = {}
        for hashed in sorted(first):
            groups.setdefault(str(context[hashed][dimension]), []).append(hashed)
        reported: list[JsonValue] = []
        suppressed_rows = 0
        suppressed_categories = 0
        for category, hashed_ids in sorted(groups.items()):
            if len(hashed_ids) < 5:
                suppressed_rows += len(hashed_ids)
                suppressed_categories += 1
                continue
            reported.append(
                {
                    "category": category,
                    "review_rows": len(hashed_ids),
                    "street_exact_precision": stratum_fraction(
                        hashed_ids,
                        "street_label",
                        {"CORRECT", "INCORRECT"},
                        "CORRECT",
                        "street_selected",
                    ),
                    "house_number_exact_precision": stratum_fraction(
                        hashed_ids,
                        "house_number_label",
                        {"CORRECT", "INCORRECT"},
                        "CORRECT",
                        "house_number_selected",
                    ),
                    "joint_street_house_precision": stratum_fraction(
                        hashed_ids,
                        "joint_street_house_label",
                        {"CORRECT", "INCORRECT"},
                        "CORRECT",
                        "experimental_selected",
                    ),
                    "false_structure_overreach_rate": stratum_fraction(
                        hashed_ids,
                        "parser_overreach_label",
                        {"PRESENT", "ABSENT"},
                        "PRESENT",
                    ),
                }
            )
        stratified[dimension] = {
            "minimum_reported_rows": 5,
            "reported": reported,
            "suppressed_category_count": suppressed_categories,
            "suppressed_row_count": suppressed_rows,
            "reconciled_rows": sum(len(values) for values in groups.values()),
        }
    decision_inputs = LockedDecisionInputs(
        metrics,
        agreements,
        unexplained_scientific_changes=int(
            validated_machine_checks["unexplained_scientific_changes"]
        ),
        unrelated_component_regressions=(
            int(validated_machine_checks["unrelated_component_regressions"])
            + int(validated_machine_checks["lost_existing_selections"])
        ),
        provenance_failures=int(validated_machine_checks["provenance_failures"]),
        privacy_governance_failures=int(
            validated_machine_checks["privacy_governance_failures"]
        ),
        methodological_defect_requires_change=any(
            bool(validated_machine_checks[field])
            for field in (
                "systematic_methodological_defect_detected",
                "unsafe_extraction_pattern_detected",
                "required_parser_rule_modification",
            )
        ),
    )
    decision = decide_locked_evaluation(decision_inputs)
    payload: dict[str, JsonValue] = {
        "metrics_version": LOCKED_METRICS_VERSION,
        "status": decision["status"],
        "review_rows": 400,
        "double_review_rows": 100,
        "metrics": {
            "joint_street_house_precision": joint.payload(),
            "street_exact_precision": street.payload(),
            "house_number_exact_precision": house.payload(),
            "false_structure_overreach_rate": overreach.payload(),
            "missed_information_rate": missed.payload(),
            "false_negative_opportunities": false_negatives,
            "conflict_precision": conflict_precision.payload(),
            "conflict_recall": conflict_recall.payload(),
            "evidence_sidecar_coverage": evidence_coverage.payload(),
        },
        "agreement": [
            cast(dict[str, JsonValue], asdict(result)) for result in agreements
        ],
        "machine_checks": cast(dict[str, JsonValue], validated_machine_checks),
        "stratified_metrics": stratified,
        "adjudication": {
            "automatic_resolution": False,
            "disagreement_identity_count": len(
                {
                    hashed
                    for hashed in second
                    if any(
                        first[hashed][field] != second[hashed][field]
                        for field in LOCKED_AGREEMENT_FIELDS
                    )
                }
            ),
            "primary_labels_used_for_scientific_metrics": True,
            "independent_labels_used_only_for_agreement": True,
        },
        "decision": decision,
        "fill_rate_used": False,
        "automatic_promotion": False,
        "raw_values_reported": False,
        "identities_reported": False,
    }
    _atomic_json(output_path, payload)
    return payload


def protocol_summary(
    *, locked_configuration_fingerprint: str | None
) -> dict[str, JsonValue]:
    contract = LockedEvaluationContract()
    return {
        "protocol_version": contract.protocol_version,
        "protocol_fingerprint": contract.fingerprint(),
        "candidate_commit": FROZEN_CANDIDATE_COMMIT,
        "provenance_commit": FROZEN_PROVENANCE_COMMIT,
        "parser_version": PARSER_VERSION_V3_2,
        "registry_version": RULE_REGISTRY_VERSION_V5,
        "registry_sha256": FROZEN_REGISTRY_SHA256,
        "development_effective_configuration_sha256": (
            FROZEN_DEVELOPMENT_CONFIGURATION_SHA256
        ),
        "locked_effective_configuration_sha256": (
            locked_configuration_fingerprint or FROZEN_LOCKED_CONFIGURATION_SHA256
        ),
        "locked_identity_count": FROZEN_LOCKED_COUNT,
        "locked_identity_digest": FROZEN_LOCKED_IDENTITY_DIGEST,
        "review_population_count": LOCKED_REVIEW_COUNT,
        "independent_double_review_count": LOCKED_DOUBLE_REVIEW_COUNT,
        "review_selection_version": LOCKED_REVIEW_SELECTION_VERSION,
        "review_seed": LOCKED_REVIEW_SEED,
        "reviewer_ids": list(LOCKED_REVIEWER_IDS),
        "review_schema_version": LOCKED_REVIEW_SCHEMA_VERSION,
        "metric_definitions": {
            "joint_street_house_precision": (
                "R01 experimental-selected rows labeled joint CORRECT divided by "
                "R01 experimental-selected rows labeled joint CORRECT or INCORRECT"
            ),
            "street_exact_precision": (
                "R01 rows with selected street labeled CORRECT divided by selected-street "
                "rows labeled CORRECT or INCORRECT"
            ),
            "house_number_exact_precision": (
                "R01 rows with selected house number labeled CORRECT divided by selected-house "
                "rows labeled CORRECT or INCORRECT"
            ),
            "false_structure_overreach_rate": (
                "R01 parser-overreach PRESENT divided by PRESENT plus ABSENT"
            ),
            "missed_information_rate": (
                "R01 missed-information PRESENT divided by PRESENT plus ABSENT; report-only"
            ),
        },
        "hard_thresholds": {
            "joint_street_house_precision_minimum": "0.95",
            "street_exact_precision_minimum": "0.95",
            "house_number_exact_precision_minimum": "0.95",
            "false_structure_overreach_rate_maximum": "0.05",
            "cohen_kappa_minimum": "0.80",
            "undefined_kappa_fallback_percent_agreement_minimum": "0.95",
            "minimum_assessable_agreement_pairs_per_label": 80,
        },
        "agreement_fields": list(LOCKED_AGREEMENT_FIELDS),
        "agreement_handling": {
            "cannot_assess": "EXCLUDED_PAIRWISE_PER_LABEL",
            "not_applicable": "RETAINED_AS_A_CATEGORY",
            "undefined_kappa": (
                "PASS_ONLY_IF_AT_LEAST_80_PAIRS_AND_PERCENT_AGREEMENT_AT_LEAST_0.95"
            ),
            "adjudication": (
                "DISAGREEMENTS_REPORTED_NOT_AUTOMATICALLY_RESOLVED; PRIMARY_R01_LABELS_"
                "DRIVE_METRICS_AND_R02_DRIVES_ONLY_AGREEMENT"
            ),
        },
        "promotion_semantics": (
            "LOCKED_PASS_ONLY_MAKES_CANDIDATE_ELIGIBLE_FOR_SEPARATE_PROMOTION_DECISION"
        ),
        "locked_rows_read": 0,
    }


def finalize_locked_evaluation(
    *,
    attempt_directory: Path,
    final_directory: Path,
    score_path: Path,
    required_artifacts: Mapping[str, Path],
    workflow_git_commit: str,
) -> tuple[Path, Path]:
    if final_directory.exists():
        raise FileExistsError("final LOCKED evaluation directory already exists")
    if attempt_directory.resolve() == final_directory.resolve():
        raise ValueError("LOCKED attempt and final directories must differ")
    score = json.loads(score_path.read_text(encoding="utf-8"))
    if score.get("status") not in {"LOCKED_PASS", "LOCKED_FAIL_REVISE"}:
        raise ValueError("LOCKED score has no final deterministic decision")
    artifacts: dict[str, JsonValue] = {}
    for name, path in sorted(required_artifacts.items()):
        resolved = path.resolve(strict=True)
        try:
            relative = resolved.relative_to(attempt_directory.resolve(strict=True))
        except ValueError as error:
            raise ValueError(
                "LOCKED final artifact is outside attempt directory"
            ) from error
        if path.is_symlink() or path.stat().st_mode & 0o077:
            raise ValueError("LOCKED final artifact must be owner-only and non-symlink")
        artifacts[name] = {
            "path": relative.as_posix(),
            "sha256": file_sha256(path),
            "size_bytes": path.stat().st_size,
        }
    manifest: dict[str, JsonValue] = {
        "manifest_version": LOCKED_OUTPUT_MANIFEST_VERSION,
        "status": str(score["status"]),
        "protocol_version": LOCKED_EVALUATION_PROTOCOL_VERSION,
        "protocol_fingerprint": LockedEvaluationContract().fingerprint(),
        "candidate_commit": FROZEN_CANDIDATE_COMMIT,
        "provenance_commit": FROZEN_PROVENANCE_COMMIT,
        "workflow_git_commit": workflow_git_commit,
        "locked_count": FROZEN_LOCKED_COUNT,
        "locked_identity_digest": FROZEN_LOCKED_IDENTITY_DIGEST,
        "artifacts": artifacts,
        "automatic_promotion": False,
        "full_production_authorized": False,
        "geocoding_authorized": False,
        "raw_values_reported": False,
        "identities_reported": False,
    }
    manifest_path = attempt_directory / "dataset_manifest.json"
    success_path = attempt_directory / "_SUCCESS.json"
    _atomic_json(manifest_path, manifest)
    success: dict[str, JsonValue] = {
        "status": str(score["status"]),
        "manifest_sha256": file_sha256(manifest_path),
        "protocol_fingerprint": LockedEvaluationContract().fingerprint(),
        "automatic_promotion": False,
    }
    _atomic_json(success_path, success)
    final_directory.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    final_directory.parent.chmod(0o700)
    os.replace(attempt_directory, final_directory)
    final_directory.chmod(0o700)
    _fsync_parent(final_directory)
    return final_directory / manifest_path.name, final_directory / success_path.name
