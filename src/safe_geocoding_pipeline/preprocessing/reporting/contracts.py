from __future__ import annotations

import hashlib
import re
import struct
from collections import Counter
from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence

DEVELOPMENT_REPORTING_CONTRACT_VERSION = "development_reporting_contract_v1"
DEVELOPMENT_REVIEW_SUBSET_CONTRACT_VERSION = "development_review_subset_contract_v1"
REVIEW_SELECTION_ALGORITHM_VERSION = "development_review_balanced_selection_v1"
REVIEW_ALLOCATION_POLICY_VERSION = "development_review_allocation_policy_v1"
REVIEW_SUBSET_FINGERPRINT_DOMAIN = b"SAFE_DEVELOPMENT_REVIEW_SUBSET_V1"
REVIEW_SELECTION_RANK_DOMAIN = b"SAFE_DEVELOPMENT_REVIEW_SUBSET_V1_RANK"
REVIEW_ORDER_DOMAIN = b"SAFE_DEVELOPMENT_REVIEW_SUBSET_V1_ORDER"
REVIEW_ID_DOMAIN = b"SAFE_DEVELOPMENT_REVIEW_ID_V1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DIMENSION_ORDER = (
    "country",
    "location_information",
    "batch_priority",
    "standard_native_presence",
    "standard_native_equality",
    "combined_script",
    "standard_line_count",
    "native_line_count",
    "missingness",
    "challenge_flag",
    "challenge_reason",
)


class ReviewSubsetError(RuntimeError):
    """Fail-closed error whose message never contains protected row values."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class ReviewSubsetPolicy:
    minimum_per_country: int = 1
    minimum_per_location: int = 30
    minimum_per_batch_priority: int = 25
    minimum_per_presence_class: int = 30
    minimum_per_equality_class: int = 20
    minimum_per_script_class: int = 30
    minimum_per_line_count: int = 12
    minimum_per_missingness_class: int = 8
    minimum_per_challenge_flag: int = 100
    minimum_per_challenge_reason: int = 20

    def to_dict(self) -> dict[str, str | int]:
        return {
            "allocation_policy_version": REVIEW_ALLOCATION_POLICY_VERSION,
            "minimum_per_country": self.minimum_per_country,
            "minimum_per_location": self.minimum_per_location,
            "minimum_per_batch_priority": self.minimum_per_batch_priority,
            "minimum_per_presence_class": self.minimum_per_presence_class,
            "minimum_per_equality_class": self.minimum_per_equality_class,
            "minimum_per_script_class": self.minimum_per_script_class,
            "minimum_per_line_count": self.minimum_per_line_count,
            "minimum_per_missingness_class": self.minimum_per_missingness_class,
            "minimum_per_challenge_flag": self.minimum_per_challenge_flag,
            "minimum_per_challenge_reason": self.minimum_per_challenge_reason,
        }

    def validate(self) -> None:
        for name, value in self.to_dict().items():
            if isinstance(value, str):
                continue
            if isinstance(value, bool) or value < 1:
                raise ReviewSubsetError(
                    "INVALID_REVIEW_POLICY", f"{name} must be a positive integer"
                )

    def minimum_for(self, dimension: str) -> int:
        values = {
            "country": self.minimum_per_country,
            "location_information": self.minimum_per_location,
            "batch_priority": self.minimum_per_batch_priority,
            "standard_native_presence": self.minimum_per_presence_class,
            "standard_native_equality": self.minimum_per_equality_class,
            "combined_script": self.minimum_per_script_class,
            "standard_line_count": self.minimum_per_line_count,
            "native_line_count": self.minimum_per_line_count,
            "missingness": self.minimum_per_missingness_class,
            "challenge_flag": self.minimum_per_challenge_flag,
            "challenge_reason": self.minimum_per_challenge_reason,
        }
        try:
            return values[dimension]
        except KeyError as error:
            raise ReviewSubsetError(
                "UNKNOWN_REVIEW_DIMENSION", "Review dimension is not versioned"
            ) from error


@dataclass(frozen=True, slots=True)
class ReviewSubsetConfig:
    target_count: int = 500
    expected_development_rows: int = 35_000
    policy: ReviewSubsetPolicy = ReviewSubsetPolicy()

    def validate(self) -> None:
        if (
            isinstance(self.target_count, bool)
            or isinstance(self.expected_development_rows, bool)
            or self.target_count < 1
            or self.expected_development_rows < self.target_count
        ):
            raise ReviewSubsetError(
                "INVALID_REVIEW_SIZE", "Review and DEVELOPMENT sizes are invalid"
            )
        self.policy.validate()


@dataclass(frozen=True, slots=True)
class ReviewCandidate:
    stable_source_row_id_v1: bytes
    source_file: str
    benchmark_split: str
    location_information_stratum: str
    batch_priority_stratum: str
    country_stratum: str
    standard_native_presence_class: str
    standard_native_equality_class: str
    standard_line_count: int
    native_line_count: int
    missingness_class: str
    combined_script_class: str
    challenge_flag: bool
    challenge_reasons: tuple[str, ...]

    def validate(self) -> None:
        if len(self.stable_source_row_id_v1) != 32:
            raise ReviewSubsetError(
                "INVALID_REVIEW_IDENTITY", "Stable source identity is not 32 bytes"
            )
        if self.benchmark_split != "DEVELOPMENT":
            raise ReviewSubsetError(
                "HOLDOUT_ACCESS_PROHIBITED", "Review candidates must be DEVELOPMENT"
            )
        text_values = (
            self.source_file,
            self.location_information_stratum,
            self.batch_priority_stratum,
            self.country_stratum,
            self.standard_native_presence_class,
            self.standard_native_equality_class,
            self.missingness_class,
            self.combined_script_class,
            *self.challenge_reasons,
        )
        if any(not value or "\x00" in value for value in text_values):
            raise ReviewSubsetError(
                "INVALID_REVIEW_FEATURE", "Review feature metadata is malformed"
            )
        if (
            not 0 <= self.standard_line_count <= 4
            or not 0 <= self.native_line_count <= 4
        ):
            raise ReviewSubsetError(
                "INVALID_REVIEW_FEATURE", "Review line-count metadata is invalid"
            )
        if len(set(self.challenge_reasons)) != len(self.challenge_reasons):
            raise ReviewSubsetError(
                "INVALID_REVIEW_FEATURE", "Challenge reasons contain duplicates"
            )

    def categories_for(self, dimension: str) -> tuple[str, ...]:
        values = {
            "country": (self.country_stratum,),
            "location_information": (self.location_information_stratum,),
            "batch_priority": (self.batch_priority_stratum,),
            "standard_native_presence": (self.standard_native_presence_class,),
            "standard_native_equality": (self.standard_native_equality_class,),
            "combined_script": (self.combined_script_class,),
            "standard_line_count": (str(self.standard_line_count),),
            "native_line_count": (str(self.native_line_count),),
            "missingness": (self.missingness_class,),
            "challenge_flag": ("CHALLENGE" if self.challenge_flag else "ORDINARY",),
            "challenge_reason": self.challenge_reasons,
        }
        try:
            return values[dimension]
        except KeyError as error:
            raise ReviewSubsetError(
                "UNKNOWN_REVIEW_DIMENSION", "Review dimension is not versioned"
            ) from error


@dataclass(frozen=True, slots=True)
class ReviewQuotaDiagnostic:
    dimension: str
    category: str
    available: int
    target: int
    achieved: int
    shortfall: int


@dataclass(frozen=True, slots=True)
class ReviewSelection:
    selected: tuple[ReviewCandidate, ...]
    quota_diagnostics: tuple[ReviewQuotaDiagnostic, ...]


class _Digest(Protocol):
    def update(self, value: bytes) -> None: ...


class _CanonicalEncoder:
    def __init__(self, digest: _Digest) -> None:
        self._digest = digest

    def uint64(self, value: int) -> None:
        if isinstance(value, bool) or not 0 <= value <= 0xFFFF_FFFF_FFFF_FFFF:
            raise ReviewSubsetError(
                "INVALID_CANONICAL_INTEGER", "Canonical integer is outside uint64"
            )
        self._digest.update(b"\x01" + struct.pack(">Q", value))

    def text(self, value: str) -> None:
        if not isinstance(value, str) or "\x00" in value:
            raise ReviewSubsetError(
                "INVALID_CANONICAL_TEXT", "Canonical text is malformed"
            )
        encoded = value.encode("utf-8", errors="strict")
        self._digest.update(b"\x02" + struct.pack(">Q", len(encoded)) + encoded)

    def digest(self, value: str) -> None:
        if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
            raise ReviewSubsetError(
                "INVALID_SHA256", "Digest must be canonical lowercase SHA-256"
            )
        self._digest.update(b"\x03" + bytes.fromhex(value))

    def raw_digest(self, value: bytes) -> None:
        if len(value) != 32:
            raise ReviewSubsetError(
                "INVALID_REVIEW_IDENTITY", "Row identity is not 32 bytes"
            )
        self._digest.update(b"\x04" + value)


def _digest_bytes(value: str) -> bytes:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ReviewSubsetError(
            "INVALID_SHA256", "Digest must be canonical lowercase SHA-256"
        )
    return bytes.fromhex(value)


def _rank(
    *, domain: bytes, benchmark_fingerprint: str, label: str, identity: bytes
) -> tuple[bytes, bytes]:
    if "\x00" in label or len(identity) != 32:
        raise ReviewSubsetError("INVALID_RANK_INPUT", "Review rank input is invalid")
    encoded = label.encode("utf-8", errors="strict")
    digest = hashlib.sha256()
    digest.update(domain)
    digest.update(_digest_bytes(benchmark_fingerprint))
    digest.update(struct.pack(">Q", len(encoded)))
    digest.update(encoded)
    digest.update(identity)
    return digest.digest(), identity


def development_review_id_v1(
    benchmark_fingerprint: str, stable_source_row_id_v1: bytes
) -> bytes:
    if len(stable_source_row_id_v1) != 32:
        raise ReviewSubsetError(
            "INVALID_REVIEW_IDENTITY", "Stable source identity is not 32 bytes"
        )
    return hashlib.sha256(
        REVIEW_ID_DOMAIN
        + _digest_bytes(benchmark_fingerprint)
        + stable_source_row_id_v1
    ).digest()


def _build_targets(
    candidates: Sequence[ReviewCandidate], policy: ReviewSubsetPolicy
) -> tuple[dict[tuple[str, str], int], dict[str, Counter[str]]]:
    counts = {dimension: Counter[str]() for dimension in _DIMENSION_ORDER}
    for candidate in candidates:
        for dimension in _DIMENSION_ORDER:
            counts[dimension].update(candidate.categories_for(dimension))
    targets: dict[tuple[str, str], int] = {}
    for dimension in _DIMENSION_ORDER:
        minimum = policy.minimum_for(dimension)
        for category, available in counts[dimension].items():
            targets[(dimension, category)] = min(minimum, available)
    return targets, counts


def select_development_review_subset(
    candidates: Sequence[ReviewCandidate],
    *,
    benchmark_fingerprint: str,
    config: ReviewSubsetConfig = ReviewSubsetConfig(),
) -> ReviewSelection:
    """Select fixed DEVELOPMENT identities from accepted structural metadata only."""
    config.validate()
    _digest_bytes(benchmark_fingerprint)
    if len(candidates) != config.expected_development_rows:
        raise ReviewSubsetError(
            "DEVELOPMENT_ROW_COUNT_MISMATCH",
            "Review input row count differs from its accepted contract",
        )
    by_identity: dict[bytes, ReviewCandidate] = {}
    for candidate in candidates:
        candidate.validate()
        if candidate.stable_source_row_id_v1 in by_identity:
            raise ReviewSubsetError(
                "DUPLICATE_REVIEW_IDENTITY", "DEVELOPMENT identity is duplicated"
            )
        by_identity[candidate.stable_source_row_id_v1] = candidate
    if len(by_identity) < config.target_count:
        raise ReviewSubsetError(
            "INSUFFICIENT_REVIEW_POPULATION", "Review target cannot be satisfied"
        )

    ordered_candidates = tuple(by_identity.values())
    targets, counts = _build_targets(ordered_candidates, config.policy)
    selected: dict[bytes, ReviewCandidate] = {}
    for dimension in _DIMENSION_ORDER:
        categories = sorted(
            counts[dimension], key=lambda value: value.encode("utf-8", errors="strict")
        )
        for category in categories:
            target = targets[(dimension, category)]
            represented = sum(
                category in item.categories_for(dimension) for item in selected.values()
            )
            candidates_for_category = sorted(
                (
                    item
                    for item in ordered_candidates
                    if category in item.categories_for(dimension)
                ),
                key=lambda item: _rank(
                    domain=REVIEW_SELECTION_RANK_DOMAIN,
                    benchmark_fingerprint=benchmark_fingerprint,
                    label=f"quota/{dimension}/{category}",
                    identity=item.stable_source_row_id_v1,
                ),
            )
            for candidate in candidates_for_category:
                if represented >= target or len(selected) >= config.target_count:
                    break
                if candidate.stable_source_row_id_v1 not in selected:
                    selected[candidate.stable_source_row_id_v1] = candidate
                    represented += 1

    represented_sources = {item.source_file for item in selected.values()}
    best_by_unrepresented_source: dict[str, ReviewCandidate] = {}
    for candidate in ordered_candidates:
        if candidate.source_file in represented_sources:
            continue
        previous = best_by_unrepresented_source.get(candidate.source_file)
        if previous is None or _rank(
            domain=REVIEW_SELECTION_RANK_DOMAIN,
            benchmark_fingerprint=benchmark_fingerprint,
            label="source-file-coverage",
            identity=candidate.stable_source_row_id_v1,
        ) < _rank(
            domain=REVIEW_SELECTION_RANK_DOMAIN,
            benchmark_fingerprint=benchmark_fingerprint,
            label="source-file-coverage",
            identity=previous.stable_source_row_id_v1,
        ):
            best_by_unrepresented_source[candidate.source_file] = candidate
    for candidate in sorted(
        best_by_unrepresented_source.values(),
        key=lambda item: _rank(
            domain=REVIEW_SELECTION_RANK_DOMAIN,
            benchmark_fingerprint=benchmark_fingerprint,
            label="source-file-coverage",
            identity=item.stable_source_row_id_v1,
        ),
    ):
        if len(selected) >= config.target_count:
            break
        selected.setdefault(candidate.stable_source_row_id_v1, candidate)

    for candidate in sorted(
        ordered_candidates,
        key=lambda item: _rank(
            domain=REVIEW_SELECTION_RANK_DOMAIN,
            benchmark_fingerprint=benchmark_fingerprint,
            label="global-fill",
            identity=item.stable_source_row_id_v1,
        ),
    ):
        if len(selected) >= config.target_count:
            break
        selected.setdefault(candidate.stable_source_row_id_v1, candidate)
    if len(selected) != config.target_count:
        raise ReviewSubsetError(
            "INSUFFICIENT_REVIEW_POPULATION", "Exact review target was not selected"
        )

    ordered = tuple(
        sorted(
            selected.values(),
            key=lambda item: _rank(
                domain=REVIEW_ORDER_DOMAIN,
                benchmark_fingerprint=benchmark_fingerprint,
                label="review-order",
                identity=item.stable_source_row_id_v1,
            ),
        )
    )
    diagnostics: list[ReviewQuotaDiagnostic] = []
    for dimension in _DIMENSION_ORDER:
        for category in sorted(
            counts[dimension], key=lambda value: value.encode("utf-8", errors="strict")
        ):
            target = targets[(dimension, category)]
            achieved = sum(
                category in item.categories_for(dimension) for item in ordered
            )
            diagnostics.append(
                ReviewQuotaDiagnostic(
                    dimension=dimension,
                    category=category,
                    available=counts[dimension][category],
                    target=target,
                    achieved=achieved,
                    shortfall=max(0, target - achieved),
                )
            )
    return ReviewSelection(ordered, tuple(diagnostics))


def development_review_subset_sha256_v1(
    *,
    benchmark_fingerprint: str,
    selected_identities: Sequence[bytes],
    config: ReviewSubsetConfig = ReviewSubsetConfig(),
) -> str:
    config.validate()
    if len(selected_identities) != config.target_count:
        raise ReviewSubsetError(
            "REVIEW_IDENTITY_COUNT_MISMATCH", "Selected identity count is not exact"
        )
    if len(set(selected_identities)) != len(selected_identities):
        raise ReviewSubsetError(
            "DUPLICATE_REVIEW_IDENTITY", "Selected review identities are duplicated"
        )
    digest = hashlib.sha256(REVIEW_SUBSET_FINGERPRINT_DOMAIN)
    encoder = _CanonicalEncoder(digest)
    for value in (
        DEVELOPMENT_REPORTING_CONTRACT_VERSION,
        DEVELOPMENT_REVIEW_SUBSET_CONTRACT_VERSION,
        REVIEW_SELECTION_ALGORITHM_VERSION,
        REVIEW_ALLOCATION_POLICY_VERSION,
    ):
        encoder.text(value)
    encoder.digest(benchmark_fingerprint)
    encoder.uint64(config.expected_development_rows)
    encoder.uint64(config.target_count)
    for name, policy_value in config.policy.to_dict().items():
        encoder.text(name)
        if isinstance(policy_value, str):
            encoder.text(policy_value)
        else:
            encoder.uint64(policy_value)
    ordered = sorted(selected_identities)
    encoder.uint64(len(ordered))
    for identity in ordered:
        encoder.raw_digest(identity)
    return digest.hexdigest()


def quota_shortfall_summary(
    diagnostics: Sequence[ReviewQuotaDiagnostic],
) -> Mapping[str, int]:
    return {
        "SHORTFALL_CATEGORY_COUNT": sum(item.shortfall > 0 for item in diagnostics),
        "SHORTFALL_TOTAL": sum(item.shortfall for item in diagnostics),
    }


__all__ = [
    "DEVELOPMENT_REPORTING_CONTRACT_VERSION",
    "DEVELOPMENT_REVIEW_SUBSET_CONTRACT_VERSION",
    "REVIEW_ALLOCATION_POLICY_VERSION",
    "REVIEW_ID_DOMAIN",
    "REVIEW_ORDER_DOMAIN",
    "REVIEW_SELECTION_ALGORITHM_VERSION",
    "REVIEW_SELECTION_RANK_DOMAIN",
    "REVIEW_SUBSET_FINGERPRINT_DOMAIN",
    "ReviewCandidate",
    "ReviewQuotaDiagnostic",
    "ReviewSelection",
    "ReviewSubsetConfig",
    "ReviewSubsetError",
    "ReviewSubsetPolicy",
    "development_review_id_v1",
    "development_review_subset_sha256_v1",
    "quota_shortfall_summary",
    "select_development_review_subset",
]
