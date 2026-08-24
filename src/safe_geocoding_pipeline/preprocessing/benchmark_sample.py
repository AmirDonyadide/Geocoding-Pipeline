from __future__ import annotations

import hashlib
import heapq
import math
import re
import struct
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping, Protocol, Sequence

from ..phase03.references import ScriptReference
from ..raw_csv import SOURCE_COLUMNS

BENCHMARK_CONTRACT_VERSION = "benchmark_sample_contract_v1"
FEATURE_CONTRACT_VERSION = "benchmark_sampling_features_v1"
SELECTION_ALGORITHM_VERSION = "benchmark_bounded_quota_selection_v1"
ALLOCATION_POLICY_VERSION = "benchmark_allocation_policy_v1"
BENCHMARK_FINGERPRINT_DOMAIN = b"SAFE_BENCHMARK_SAMPLE_V1"
RANK_DOMAIN = b"SAFE_BENCHMARK_SAMPLE_V1_RANK"
SPLIT_DOMAIN = b"SAFE_BENCHMARK_SAMPLE_V1_SPLIT"

STANDARD_LINES = tuple(f"street_address_line_{index}" for index in range(1, 5))
NATIVE_LINES = tuple(f"street_address_line_{index}_native" for index in range(1, 5))
APPROVED_LOCATION_VALUES = frozenset(
    {
        "no_geocoding_information",
        "previous_geocoding_failure",
        "postcode_interpolated",
        "region_interpolated",
    }
)
APPROVED_BATCH_PRIORITIES = frozenset({"0", "1", "2", "3"})

_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class BenchmarkValidationError(RuntimeError):
    """Fail-closed benchmark error whose text contains no protected row value."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class SamplingPolicy:
    minimum_per_source_file: int = 8
    minimum_per_location: int = 500
    minimum_per_batch_priority: int = 250
    minimum_per_country: int = 25
    country_extra_budget: int = 7_500
    minimum_per_presence_class: int = 250
    minimum_per_equality_class: int = 250
    minimum_per_line_count: int = 100
    minimum_per_script_class: int = 250
    minimum_per_missingness_class: int = 100
    minimum_per_challenge_reason: int = 250

    def validate(self) -> None:
        for name, value in self.to_dict().items():
            if isinstance(value, str):
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise BenchmarkValidationError(
                    "INVALID_SAMPLING_POLICY", f"{name} must be a positive integer"
                )

    def to_dict(self) -> dict[str, str | int]:
        return {
            "allocation_policy_version": ALLOCATION_POLICY_VERSION,
            "minimum_per_source_file": self.minimum_per_source_file,
            "minimum_per_location": self.minimum_per_location,
            "minimum_per_batch_priority": self.minimum_per_batch_priority,
            "minimum_per_country": self.minimum_per_country,
            "country_extra_budget": self.country_extra_budget,
            "minimum_per_presence_class": self.minimum_per_presence_class,
            "minimum_per_equality_class": self.minimum_per_equality_class,
            "minimum_per_line_count": self.minimum_per_line_count,
            "minimum_per_script_class": self.minimum_per_script_class,
            "minimum_per_missingness_class": self.minimum_per_missingness_class,
            "minimum_per_challenge_reason": self.minimum_per_challenge_reason,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkConfig:
    development_count: int = 35_000
    holdout_count: int = 15_000
    policy: SamplingPolicy = SamplingPolicy()

    @property
    def total_count(self) -> int:
        return self.development_count + self.holdout_count

    def validate(self) -> None:
        if (
            isinstance(self.development_count, bool)
            or isinstance(self.holdout_count, bool)
            or self.development_count < 1
            or self.holdout_count < 1
        ):
            raise BenchmarkValidationError(
                "INVALID_SAMPLE_SIZE", "Development and holdout counts must be positive"
            )
        self.policy.validate()


@dataclass(frozen=True, slots=True)
class SamplingFeatures:
    location_information_stratum: str
    batch_priority_stratum: str
    country_stratum: str
    standard_native_presence_class: str
    standard_native_equality_class: str
    standard_line_count: int
    native_line_count: int
    postcode_present: bool
    city_present: bool
    region_present: bool
    country_present: bool
    missingness_class: str
    standard_script_class: str
    native_script_class: str
    combined_script_class: str
    challenge_flag: bool
    challenge_reasons: tuple[str, ...]

    def categories_for(self, dimension: str, source_file: str) -> tuple[str, ...]:
        values: dict[str, tuple[str, ...]] = {
            "source_file": (source_file,),
            "location_information": (self.location_information_stratum,),
            "batch_priority": (self.batch_priority_stratum,),
            "country": (self.country_stratum,),
            "standard_native_presence": (self.standard_native_presence_class,),
            "standard_native_equality": (self.standard_native_equality_class,),
            "standard_line_count": (str(self.standard_line_count),),
            "native_line_count": (str(self.native_line_count),),
            "standard_script": (self.standard_script_class,),
            "native_script": (self.native_script_class,),
            "combined_script": (self.combined_script_class,),
            "missingness": (self.missingness_class,),
            "challenge_reason": self.challenge_reasons,
        }
        try:
            return values[dimension]
        except KeyError as error:
            raise BenchmarkValidationError(
                "UNKNOWN_STRATIFICATION_DIMENSION",
                "Sampling requested an unknown structural dimension",
            ) from error


@dataclass(frozen=True, slots=True)
class BenchmarkCandidate:
    stable_source_row_id_v1: bytes
    source_file: str
    source_logical_record_number: int
    features: SamplingFeatures

    def __post_init__(self) -> None:
        if len(self.stable_source_row_id_v1) != 32:
            raise BenchmarkValidationError(
                "INVALID_ROW_IDENTITY", "Benchmark row identity must contain 32 bytes"
            )
        if not 1 <= self.source_logical_record_number <= 0xFFFF_FFFF_FFFF_FFFF:
            raise BenchmarkValidationError(
                "INVALID_ROW_IDENTITY", "Logical record number is outside uint64"
            )


@dataclass(frozen=True, slots=True)
class QuotaDiagnostic:
    dimension: str
    category: str
    available: int
    target: int
    achieved: int
    shortfall: int


@dataclass(frozen=True, slots=True)
class BenchmarkSelection:
    development: tuple[BenchmarkCandidate, ...]
    holdout: tuple[BenchmarkCandidate, ...]
    quota_diagnostics: tuple[QuotaDiagnostic, ...]

    @property
    def all_candidates(self) -> tuple[BenchmarkCandidate, ...]:
        return self.development + self.holdout


@dataclass(frozen=True, slots=True)
class BenchmarkSourceProjection:
    relative_path: str
    size_bytes: int
    sha256: str
    logical_record_count: int


class _Digest(Protocol):
    def update(self, value: bytes) -> None: ...


class _CanonicalEncoder:
    def __init__(self, digest: _Digest) -> None:
        self._digest = digest

    def uint64(self, value: int) -> None:
        if isinstance(value, bool) or not 0 <= value <= 0xFFFF_FFFF_FFFF_FFFF:
            raise BenchmarkValidationError(
                "INVALID_CANONICAL_INTEGER", "Canonical integer is outside uint64"
            )
        self._digest.update(struct.pack(">Q", value))

    def text(self, value: str) -> None:
        if not isinstance(value, str) or "\x00" in value:
            raise BenchmarkValidationError(
                "INVALID_CANONICAL_TEXT", "Canonical text is invalid"
            )
        encoded = value.encode("utf-8", errors="strict")
        self.uint64(len(encoded))
        self._digest.update(encoded)

    def digest(self, value: str) -> None:
        if _SHA256_RE.fullmatch(value) is None:
            raise BenchmarkValidationError(
                "INVALID_SHA256", "Digest must be lowercase canonical SHA-256"
            )
        self._digest.update(bytes.fromhex(value))

    def raw_digest(self, value: bytes) -> None:
        if len(value) != 32:
            raise BenchmarkValidationError(
                "INVALID_ROW_IDENTITY", "Row identity must contain 32 bytes"
            )
        self._digest.update(value)


def _safe_stratum(value: str, *, approved: frozenset[str], domain: bytes) -> str:
    if value == "":
        return "EMPTY"
    if value in approved:
        return value
    digest = hashlib.sha256(domain + value.encode("utf-8", errors="strict")).hexdigest()
    return f"OTHER_SHA256:{digest}"


def _country_stratum(value: str) -> str:
    if value == "":
        return "EMPTY"
    if _COUNTRY_RE.fullmatch(value) is not None:
        return value
    digest = hashlib.sha256(
        b"SAFE_BENCHMARK_COUNTRY_STRATUM_V1\0" + value.encode("utf-8", errors="strict")
    ).hexdigest()
    return f"UNUSUAL_SHA256:{digest}"


def _script_class(values: Sequence[str], reference: ScriptReference) -> str:
    if not any(value != "" for value in values):
        return "EMPTY"
    scripts: set[str] = set()
    for value in values:
        scripts.update(reference.distinctive_scripts(value))
    if not scripts:
        return "COMMON_OR_UNKNOWN_ONLY"
    if scripts == {"Latin"}:
        return "LATIN_ONLY"
    if len(scripts) == 1 and "Latin" not in scripts:
        return "NON_LATIN_PRESENT"
    return "MIXED_SCRIPT"


def classify_sampling_features(
    row: Mapping[str, str], *, script_reference: ScriptReference
) -> SamplingFeatures:
    if set(row) != set(SOURCE_COLUMNS):
        raise BenchmarkValidationError(
            "SOURCE_ROW_SCHEMA_MISMATCH", "Source row does not have the exact schema"
        )
    standard = tuple(row[name] for name in STANDARD_LINES)
    native = tuple(row[name] for name in NATIVE_LINES)
    standard_count = sum(value != "" for value in standard)
    native_count = sum(value != "" for value in native)
    standard_present = standard_count > 0
    native_present = native_count > 0
    if standard_present and native_present:
        presence = "BOTH_PRESENT"
        if standard == native:
            equality = "EXACTLY_EQUAL"
        elif tuple(value.casefold() for value in standard) == tuple(
            value.casefold() for value in native
        ):
            equality = "CASE_ONLY_OR_TRIVIALLY_EQUAL"
        else:
            equality = "MATERIALLY_DIFFERENT"
    elif standard_present:
        presence = "STANDARD_ONLY"
        equality = "NOT_BOTH_PRESENT"
    elif native_present:
        presence = "NATIVE_ONLY"
        equality = "NOT_BOTH_PRESENT"
    else:
        presence = "NEITHER_PRESENT"
        equality = "NOT_BOTH_PRESENT"

    postcode_present = row["postcode"] != ""
    city_present = row["city"] != ""
    region_present = row["region_in_country"] != ""
    country_present = row["country_iso_code"] != ""
    missingness = "_".join(
        (
            f"POSTCODE_{'PRESENT' if postcode_present else 'MISSING'}",
            f"CITY_{'PRESENT' if city_present else 'MISSING'}",
            f"REGION_{'PRESENT' if region_present else 'MISSING'}",
            f"COUNTRY_{'PRESENT' if country_present else 'MISSING'}",
        )
    )
    standard_script = _script_class(standard, script_reference)
    native_script = _script_class(native, script_reference)
    combined_script = _script_class(standard + native, script_reference)
    location = _safe_stratum(
        row["location_information"],
        approved=APPROVED_LOCATION_VALUES,
        domain=b"SAFE_BENCHMARK_LOCATION_STRATUM_V1\0",
    )
    reasons: list[str] = []
    if presence == "NATIVE_ONLY":
        reasons.append("STANDARD_MISSING_NATIVE_PRESENT")
    if equality == "MATERIALLY_DIFFERENT":
        reasons.append("STANDARD_NATIVE_MATERIALLY_DIFFERENT")
    if not postcode_present:
        reasons.append("POSTCODE_MISSING")
    if not city_present:
        reasons.append("CITY_MISSING")
    if not region_present:
        reasons.append("REGION_MISSING")
    if not country_present:
        reasons.append("COUNTRY_MISSING")
    if standard_count >= 2 or native_count >= 2:
        reasons.append("MULTIPLE_ADDRESS_LINES")
    if combined_script == "NON_LATIN_PRESENT":
        reasons.append("NON_LATIN_SCRIPT")
    if combined_script == "MIXED_SCRIPT":
        reasons.append("MIXED_SCRIPT")
    if max((len(value) for value in standard + native), default=0) >= 1_024:
        reasons.append("VERY_LONG_ADDRESS_FIELD")
    if location == "previous_geocoding_failure":
        reasons.append("PREVIOUS_GEOCODING_FAILURE")
    if location == "no_geocoding_information":
        reasons.append("NO_GEOCODING_INFORMATION")

    return SamplingFeatures(
        location_information_stratum=location,
        batch_priority_stratum=_safe_stratum(
            row["batch_priority"],
            approved=APPROVED_BATCH_PRIORITIES,
            domain=b"SAFE_BENCHMARK_BATCH_STRATUM_V1\0",
        ),
        country_stratum=_country_stratum(row["country_iso_code"]),
        standard_native_presence_class=presence,
        standard_native_equality_class=equality,
        standard_line_count=standard_count,
        native_line_count=native_count,
        postcode_present=postcode_present,
        city_present=city_present,
        region_present=region_present,
        country_present=country_present,
        missingness_class=missingness,
        standard_script_class=standard_script,
        native_script_class=native_script,
        combined_script_class=combined_script,
        challenge_flag=bool(reasons),
        challenge_reasons=tuple(reasons),
    )


def rank_key_v1(label: str, identity: bytes) -> int:
    """Return the address-text-independent deterministic quota/fill rank."""
    if len(identity) != 32 or "\x00" in label:
        raise BenchmarkValidationError("INVALID_RANK_INPUT", "Rank input is invalid")
    encoded = label.encode("utf-8", errors="strict")
    digest = hashlib.sha256()
    digest.update(RANK_DOMAIN)
    digest.update(struct.pack(">Q", len(encoded)))
    digest.update(encoded)
    digest.update(identity)
    return (int.from_bytes(digest.digest(), "big") << 256) | int.from_bytes(
        identity, "big"
    )


def split_rank_v1(identity: bytes) -> int:
    if len(identity) != 32:
        raise BenchmarkValidationError(
            "INVALID_RANK_INPUT", "Split identity is invalid"
        )
    digest = hashlib.sha256(SPLIT_DOMAIN + identity).digest()
    return (int.from_bytes(digest, "big") << 256) | int.from_bytes(identity, "big")


class BoundedCandidateHeap:
    """Retain the exact smallest provenance ranks with bounded memory."""

    def __init__(self, capacity: int, *, rank_label: str) -> None:
        if capacity < 1:
            raise BenchmarkValidationError(
                "INVALID_HEAP_CAPACITY", "Candidate heap capacity must be positive"
            )
        self.capacity = capacity
        self.rank_label = rank_label
        self._entries: list[tuple[int, bytes, BenchmarkCandidate]] = []

    def offer(self, candidate: BenchmarkCandidate) -> None:
        key = rank_key_v1(self.rank_label, candidate.stable_source_row_id_v1)
        self.offer_ranked(candidate, key=key)

    def offer_ranked(self, candidate: BenchmarkCandidate, *, key: int) -> None:
        entry = (-key, candidate.stable_source_row_id_v1, candidate)
        if len(self._entries) < self.capacity:
            heapq.heappush(self._entries, entry)
        elif key < -self._entries[0][0]:
            heapq.heapreplace(self._entries, entry)

    def ordered(self) -> tuple[BenchmarkCandidate, ...]:
        return tuple(
            item[2]
            for item in sorted(
                self._entries,
                key=lambda item: -item[0],
            )
        )


def profile_feature_groups(
    rows: Iterable[tuple[str, SamplingFeatures]],
) -> dict[str, Counter[str]]:
    dimensions = (
        "source_file",
        "location_information",
        "batch_priority",
        "country",
        "standard_native_presence",
        "standard_native_equality",
        "standard_line_count",
        "native_line_count",
        "standard_script",
        "native_script",
        "combined_script",
        "missingness",
        "challenge_reason",
    )
    counters = {dimension: Counter[str]() for dimension in dimensions}
    for source_file, features in rows:
        for dimension in dimensions:
            for category in features.categories_for(dimension, source_file):
                counters[dimension][category] += 1
    return counters


def allocate_country_targets(
    country_counts: Mapping[str, int],
    country_non_latin_counts: Mapping[str, int],
    *,
    policy: SamplingPolicy,
) -> dict[str, int]:
    """Allocate exact integer minima plus sqrt-volume/non-Latin weighted extras."""
    if not country_counts or any(count < 1 for count in country_counts.values()):
        raise BenchmarkValidationError(
            "INVALID_COUNTRY_PROFILE", "Country profile must contain positive counts"
        )
    targets = {
        category: min(count, policy.minimum_per_country)
        for category, count in country_counts.items()
    }
    remaining_capacity = {
        category: country_counts[category] - targets[category]
        for category in country_counts
    }
    budget = min(policy.country_extra_budget, sum(remaining_capacity.values()))
    weights: dict[str, int] = {}
    for category, count in country_counts.items():
        non_latin = country_non_latin_counts.get(category, 0)
        if not 0 <= non_latin <= count:
            raise BenchmarkValidationError(
                "INVALID_COUNTRY_PROFILE", "Non-Latin country count is inconsistent"
            )
        weights[category] = math.isqrt(count) * (
            1_000_000 + (non_latin * 1_000_000 // count)
        )

    while budget > 0:
        active = [
            category
            for category in sorted(country_counts, key=lambda value: value.encode())
            if remaining_capacity[category] > 0
        ]
        if not active:
            break
        total_weight = sum(weights[category] for category in active)
        proposed: dict[str, int] = {}
        remainders: list[tuple[int, bytes, str]] = []
        for category in active:
            numerator = budget * weights[category]
            share, remainder = divmod(numerator, total_weight)
            share = min(share, remaining_capacity[category])
            proposed[category] = share
            remainders.append((-remainder, category.encode("utf-8"), category))
        allocated = sum(proposed.values())
        if allocated == 0:
            for _, _, category in sorted(remainders):
                if budget == 0:
                    break
                proposed[category] = 1
                budget -= 1
            allocated = sum(proposed.values())
            for category, amount in proposed.items():
                targets[category] += amount
                remaining_capacity[category] -= amount
            continue
        for category, amount in proposed.items():
            targets[category] += amount
            remaining_capacity[category] -= amount
        budget -= allocated
    return targets


def build_quota_targets(
    counts: Mapping[str, Counter[str]],
    country_non_latin_counts: Mapping[str, int],
    *,
    policy: SamplingPolicy,
) -> dict[tuple[str, str], int]:
    policy.validate()
    minima = {
        "source_file": policy.minimum_per_source_file,
        "location_information": policy.minimum_per_location,
        "batch_priority": policy.minimum_per_batch_priority,
        "standard_native_presence": policy.minimum_per_presence_class,
        "standard_native_equality": policy.minimum_per_equality_class,
        "standard_line_count": policy.minimum_per_line_count,
        "native_line_count": policy.minimum_per_line_count,
        "standard_script": policy.minimum_per_script_class,
        "native_script": policy.minimum_per_script_class,
        "combined_script": policy.minimum_per_script_class,
        "missingness": policy.minimum_per_missingness_class,
        "challenge_reason": policy.minimum_per_challenge_reason,
    }
    targets: dict[tuple[str, str], int] = {}
    for dimension, minimum in minima.items():
        for category, available in counts[dimension].items():
            targets[(dimension, category)] = min(available, minimum)
    for category, target in allocate_country_targets(
        counts["country"], country_non_latin_counts, policy=policy
    ).items():
        targets[("country", category)] = target
    return targets


def make_candidate_heaps(
    targets: Mapping[tuple[str, str], int], *, total_count: int
) -> tuple[dict[tuple[str, str], BoundedCandidateHeap], BoundedCandidateHeap]:
    heaps = {
        key: BoundedCandidateHeap(target, rank_label="quota-selection")
        for key, target in targets.items()
        if target > 0
    }
    return heaps, BoundedCandidateHeap(total_count, rank_label="quota-selection")


def offer_candidate(
    candidate: BenchmarkCandidate,
    *,
    quota_heaps: Mapping[tuple[str, str], BoundedCandidateHeap],
    global_heap: BoundedCandidateHeap,
) -> None:
    key = rank_key_v1("quota-selection", candidate.stable_source_row_id_v1)
    global_heap.offer_ranked(candidate, key=key)
    for dimension in _DIMENSION_ORDER:
        for category in candidate.features.categories_for(
            dimension, candidate.source_file
        ):
            heap = quota_heaps.get((dimension, category))
            if heap is not None:
                heap.offer_ranked(candidate, key=key)


_DIMENSION_ORDER = (
    "source_file",
    "location_information",
    "country",
    "batch_priority",
    "standard_native_presence",
    "standard_native_equality",
    "standard_line_count",
    "native_line_count",
    "standard_script",
    "native_script",
    "combined_script",
    "missingness",
    "challenge_reason",
)


def finalize_selection(
    *,
    targets: Mapping[tuple[str, str], int],
    counts: Mapping[str, Counter[str]],
    quota_heaps: Mapping[tuple[str, str], BoundedCandidateHeap],
    global_heap: BoundedCandidateHeap,
    config: BenchmarkConfig,
) -> BenchmarkSelection:
    config.validate()
    selected: dict[bytes, BenchmarkCandidate] = {}
    dimension_index = {name: index for index, name in enumerate(_DIMENSION_ORDER)}
    for key in sorted(
        targets,
        key=lambda item: (dimension_index[item[0]], item[1].encode("utf-8")),
    ):
        dimension, category = key
        target = targets[key]
        represented = sum(
            category
            in candidate.features.categories_for(dimension, candidate.source_file)
            for candidate in selected.values()
        )
        for candidate in quota_heaps[key].ordered():
            if represented >= target or len(selected) >= config.total_count:
                break
            if candidate.stable_source_row_id_v1 not in selected:
                selected[candidate.stable_source_row_id_v1] = candidate
                represented += 1
    for candidate in global_heap.ordered():
        if len(selected) == config.total_count:
            break
        selected.setdefault(candidate.stable_source_row_id_v1, candidate)
    if len(selected) != config.total_count:
        raise BenchmarkValidationError(
            "INSUFFICIENT_SAMPLE_POPULATION",
            "The eligible population cannot produce the exact benchmark size",
        )
    diagnostics: list[QuotaDiagnostic] = []
    for dimension, category in sorted(
        targets,
        key=lambda item: (dimension_index[item[0]], item[1].encode("utf-8")),
    ):
        target = targets[(dimension, category)]
        achieved = sum(
            category
            in candidate.features.categories_for(dimension, candidate.source_file)
            for candidate in selected.values()
        )
        diagnostics.append(
            QuotaDiagnostic(
                dimension=dimension,
                category=category,
                available=counts[dimension][category],
                target=target,
                achieved=achieved,
                shortfall=max(0, target - achieved),
            )
        )
    ordered_for_split = sorted(
        selected.values(), key=lambda item: split_rank_v1(item.stable_source_row_id_v1)
    )
    development = tuple(ordered_for_split[: config.development_count])
    holdout = tuple(ordered_for_split[config.development_count :])
    if len(holdout) != config.holdout_count:
        raise AssertionError("internal benchmark split count error")
    return BenchmarkSelection(development, holdout, tuple(diagnostics))


def benchmark_fingerprint_v1(
    *,
    population_scope_version: str,
    population_id: str,
    population_scope_sha256: str,
    parser_contract_fingerprint: str,
    unicode_script_reference_id: str,
    sources: Sequence[BenchmarkSourceProjection],
    selection: BenchmarkSelection,
    config: BenchmarkConfig,
) -> str:
    return benchmark_fingerprint_from_identities_v1(
        population_scope_version=population_scope_version,
        population_id=population_id,
        population_scope_sha256=population_scope_sha256,
        parser_contract_fingerprint=parser_contract_fingerprint,
        unicode_script_reference_id=unicode_script_reference_id,
        sources=sources,
        development_identities=tuple(
            item.stable_source_row_id_v1 for item in selection.development
        ),
        holdout_identities=tuple(
            item.stable_source_row_id_v1 for item in selection.holdout
        ),
        config=config,
    )


def benchmark_fingerprint_from_identities_v1(
    *,
    population_scope_version: str,
    population_id: str,
    population_scope_sha256: str,
    parser_contract_fingerprint: str,
    unicode_script_reference_id: str,
    sources: Sequence[BenchmarkSourceProjection],
    development_identities: Sequence[bytes],
    holdout_identities: Sequence[bytes],
    config: BenchmarkConfig,
) -> str:
    """Compute the benchmark identity from its minimal sealed projection."""
    config.validate()
    ordered_sources = tuple(sorted(sources, key=lambda item: item.relative_path))
    if len({item.relative_path for item in ordered_sources}) != len(ordered_sources):
        raise BenchmarkValidationError(
            "DUPLICATE_SOURCE_PATH", "Source projection contains a duplicate path"
        )
    digest = hashlib.sha256()
    digest.update(BENCHMARK_FINGERPRINT_DOMAIN)
    encoder = _CanonicalEncoder(digest)
    for value in (
        BENCHMARK_CONTRACT_VERSION,
        FEATURE_CONTRACT_VERSION,
        SELECTION_ALGORITHM_VERSION,
        ALLOCATION_POLICY_VERSION,
        population_scope_version,
        population_id,
        unicode_script_reference_id,
    ):
        encoder.text(value)
    encoder.digest(population_scope_sha256)
    encoder.digest(parser_contract_fingerprint)
    encoder.uint64(config.development_count)
    encoder.uint64(config.holdout_count)
    for key, policy_value in config.policy.to_dict().items():
        encoder.text(key)
        if isinstance(policy_value, str):
            encoder.text(policy_value)
        else:
            encoder.uint64(policy_value)
    encoder.uint64(len(ordered_sources))
    encoder.uint64(sum(item.logical_record_count for item in ordered_sources))
    for source in ordered_sources:
        encoder.text(source.relative_path)
        encoder.uint64(source.size_bytes)
        encoder.digest(source.sha256)
        encoder.uint64(source.logical_record_count)
    for split_name, identities_input, expected_count in (
        ("DEVELOPMENT", development_identities, config.development_count),
        ("HOLDOUT", holdout_identities, config.holdout_count),
    ):
        encoder.text(split_name)
        identities = sorted(identities_input)
        if len(identities) != expected_count or len(set(identities)) != len(identities):
            raise BenchmarkValidationError(
                "DUPLICATE_SELECTED_IDENTITY",
                "Selected benchmark identity count or uniqueness is invalid",
            )
        encoder.uint64(len(identities))
        for identity in identities:
            encoder.raw_digest(identity)
    return digest.hexdigest()


def development_coverage(
    development: Sequence[BenchmarkCandidate],
) -> dict[str, dict[str, int] | int]:
    counters: dict[str, Counter[str]] = {
        "location_information": Counter(),
        "batch_priority": Counter(),
        "country": Counter(),
        "standard_native_presence": Counter(),
        "standard_native_equality": Counter(),
        "standard_line_count": Counter(),
        "native_line_count": Counter(),
        "missingness": Counter(),
        "standard_script": Counter(),
        "native_script": Counter(),
        "combined_script": Counter(),
    }
    files: set[str] = set()
    challenge_count = 0
    for candidate in development:
        files.add(candidate.source_file)
        features = candidate.features
        challenge_count += features.challenge_flag
        for dimension in counters:
            for category in features.categories_for(dimension, candidate.source_file):
                counters[dimension][category] += 1
    return {
        "development_rows": len(development),
        "source_files_represented": len(files),
        "challenge_rows": challenge_count,
        **{
            dimension: dict(sorted(counter.items()))
            for dimension, counter in counters.items()
        },
    }


__all__ = [
    "ALLOCATION_POLICY_VERSION",
    "BENCHMARK_CONTRACT_VERSION",
    "BENCHMARK_FINGERPRINT_DOMAIN",
    "FEATURE_CONTRACT_VERSION",
    "SELECTION_ALGORITHM_VERSION",
    "BenchmarkCandidate",
    "BenchmarkConfig",
    "BenchmarkSelection",
    "BenchmarkSourceProjection",
    "BenchmarkValidationError",
    "BoundedCandidateHeap",
    "QuotaDiagnostic",
    "SamplingFeatures",
    "SamplingPolicy",
    "allocate_country_targets",
    "benchmark_fingerprint_v1",
    "benchmark_fingerprint_from_identities_v1",
    "build_quota_targets",
    "classify_sampling_features",
    "development_coverage",
    "finalize_selection",
    "make_candidate_heaps",
    "offer_candidate",
    "profile_feature_groups",
    "rank_key_v1",
    "split_rank_v1",
]
