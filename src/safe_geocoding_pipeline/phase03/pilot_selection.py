from __future__ import annotations

import hashlib
import heapq
import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, TypeAlias

from .models import PilotCandidate, PilotSeal
from .sampler import PilotSamplingConfig, PilotSelection

GroupKey: TypeAlias = tuple[str, str]
QuotaBucketKey: TypeAlias = tuple[str, str, str]
HeapEntry: TypeAlias = tuple[int, bytes, PilotCandidate]
SELECTION_TRACE_VERSION = "phase03_pilot_selection_trace_v2"


class PilotSelectionInfeasibleError(ValueError):
    """A frozen quota/cap contract cannot be satisfied by this population."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str,
        dimension: str | None = None,
        category: str | None = None,
        target: int | None = None,
        represented: int | None = None,
        available: int | None = None,
        candidates_considered: int | None = None,
        cap_blocked_candidates: int | None = None,
        primary_cap: int | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.dimension = dimension
        self.category = category
        self.target = target
        self.represented = represented
        self.available = available
        self.candidates_considered = candidates_considered
        self.cap_blocked_candidates = cap_blocked_candidates
        self.primary_cap = primary_cap

    def privacy_safe_diagnostic(self) -> dict[str, int | str | None]:
        category = self.category
        if category is not None and category.startswith("UNUSUAL:"):
            category = "UNUSUAL_REDACTED"
        elif category is not None and self.dimension in {
            "country_group",
            "primary_country_group",
        }:
            category = "COUNTRY_GROUP_SHA256:" + hashlib.sha256(
                b"phase03:pilot-select-country-group-v1\0"
                + category.encode("utf-8")
            ).hexdigest()
        return {
            "available": self.available,
            "candidates_considered": self.candidates_considered,
            "cap_blocked_candidates": self.cap_blocked_candidates,
            "category": category,
            "dimension": self.dimension,
            "reason_code": self.reason_code,
            "represented": self.represented,
            "target": self.target,
            "primary_cap": self.primary_cap,
        }


@dataclass(frozen=True, slots=True)
class SelectionTraceStage:
    """Protected deterministic trace for one frozen selection stage."""

    stage_index: int
    stage_type: str
    dimension: str | None
    category: str | None
    target: int | None
    available: int | None
    represented_before: int | None
    represented_after: int | None
    selected_count_before: int
    candidates_considered: int
    candidates_cap_blocked: int
    selected_events: tuple[tuple[bytes, str, str], ...]
    cap_blocked_events: tuple[tuple[bytes, str, str], ...]
    selected_this_stage_count: int
    selected_this_stage_digest: str
    cap_blocked_digest: str
    cap_blocked_digest_complete: bool
    selected_count_after: int
    cumulative_selected_digest_before: str
    cumulative_selected_digest: str
    primary_group_counts_before: tuple[tuple[str, int], ...]
    primary_group_count_digest_before: str
    primary_group_counts: tuple[tuple[str, int], ...]
    primary_group_count_digest: str
    frontier_digest: str
    quota_frontier_digest: str | None
    fill_frontier_digest: str | None
    frontier_digest_complete: bool


@dataclass(slots=True)
class SelectionTrace:
    """Optional test/protected-benchmark trace; never a portable row report."""

    stages: list[SelectionTraceStage] = field(default_factory=list)
    trace_version: str = SELECTION_TRACE_VERSION

    def start_stage(
        self,
        *,
        stage_type: str,
        dimension: str | None = None,
        category: str | None = None,
        target: int | None = None,
        available: int | None = None,
        represented_before: int | None = None,
    ) -> SelectionStageRecorder:
        return SelectionStageRecorder(
            trace=self,
            stage_type=stage_type,
            dimension=dimension,
            category=category,
            target=target,
            available=available,
            represented_before=represented_before,
        )


@dataclass(slots=True)
class SelectionStageRecorder:
    trace: SelectionTrace
    stage_type: str
    dimension: str | None
    category: str | None
    target: int | None
    available: int | None
    represented_before: int | None
    candidates_considered: int = 0
    candidates_cap_blocked: int = 0
    selected_events: list[tuple[bytes, str, str]] = field(default_factory=list)
    cap_blocked_events: list[tuple[bytes, str, str]] = field(default_factory=list)
    frontier_digest_complete: bool = True
    _frontier_digest: Any = field(
        default_factory=lambda: hashlib.sha256(
            b"phase03:pilot-selection-trace-frontier-v1\0"
        )
    )

    def observe(
        self,
        candidate: PilotCandidate,
        *,
        rank: bytes,
        primary_group: str,
        outcome: str,
    ) -> None:
        if outcome not in {
            "SELECTED",
            "PRIMARY_CAP_BLOCKED",
            "TOTAL_COUNT_BLOCKED",
        }:
            raise ValueError("unsupported selection trace outcome")
        self.candidates_considered += 1
        if outcome == "PRIMARY_CAP_BLOCKED":
            self.candidates_cap_blocked += 1
            self.cap_blocked_events.append(
                (
                    candidate.stable_source_row_id_v1,
                    rank.hex(),
                    primary_group,
                )
            )
        elif outcome == "SELECTED":
            self.selected_events.append(
                (
                    candidate.stable_source_row_id_v1,
                    rank.hex(),
                    primary_group,
                )
            )
        digest = self._frontier_digest
        for raw in (
            candidate.stable_source_row_id_v1,
            rank,
            primary_group.encode("utf-8"),
            outcome.encode("ascii"),
        ):
            digest.update(len(raw).to_bytes(8, "big"))
            digest.update(raw)

    def reconcile_exhausted_frontier(
        self, *, candidates_considered: int, candidates_cap_blocked: int
    ) -> None:
        """Set exact aggregate counts when bounded replay omitted rejected rows."""

        if candidates_considered < self.candidates_considered or candidates_cap_blocked < self.candidates_cap_blocked:
            raise ValueError("exhausted-frontier reconciliation cannot reduce counts")
        if (
            candidates_considered != self.candidates_considered
            or candidates_cap_blocked != self.candidates_cap_blocked
        ):
            self.frontier_digest_complete = False
        self.candidates_considered = candidates_considered
        self.candidates_cap_blocked = candidates_cap_blocked

    def finish(
        self,
        *,
        selected_ids: tuple[bytes, ...],
        primary_counts: Counter[str],
    ) -> None:
        selected_event_ids = {identity for identity, _, _ in self.selected_events}
        selected_ids_before = tuple(
            identity for identity in selected_ids if identity not in selected_event_ids
        )
        primary_counts_before = primary_counts.copy()
        for _, _, primary in self.selected_events:
            primary_counts_before[primary] -= 1
            if primary_counts_before[primary] == 0:
                del primary_counts_before[primary]
        primary_counts_before_ordered = _ordered_primary_counts(primary_counts_before)
        selected_digest = _identity_digest(
            b"phase03:selection-trace-cumulative-v1\0", selected_ids
        )
        selected_digest_before = _identity_digest(
            b"phase03:selection-trace-cumulative-v1\0", selected_ids_before
        )
        primary_counts_ordered = _ordered_primary_counts(primary_counts)
        primary_digest_before = _primary_counts_digest(primary_counts_before_ordered)
        primary_digest = _primary_counts_digest(primary_counts_ordered)
        selected_this_stage_digest = _event_digest(
            b"phase03:selection-trace-selected-events-v1\0", self.selected_events
        )
        cap_blocked_digest = _event_digest(
            b"phase03:selection-trace-cap-blocked-events-v1\0",
            self.cap_blocked_events,
        )
        frontier_digest = self._frontier_digest
        represented_after = (
            None
            if self.represented_before is None
            else self.represented_before + len(self.selected_events)
        )
        self.trace.stages.append(
            SelectionTraceStage(
                stage_index=len(self.trace.stages),
                stage_type=self.stage_type,
                dimension=self.dimension,
                category=self.category,
                target=self.target,
                available=self.available,
                represented_before=self.represented_before,
                represented_after=represented_after,
                selected_count_before=len(selected_ids_before),
                candidates_considered=self.candidates_considered,
                candidates_cap_blocked=self.candidates_cap_blocked,
                selected_events=tuple(self.selected_events),
                cap_blocked_events=tuple(self.cap_blocked_events),
                selected_this_stage_count=len(self.selected_events),
                selected_this_stage_digest=selected_this_stage_digest,
                cap_blocked_digest=cap_blocked_digest,
                cap_blocked_digest_complete=(
                    len(self.cap_blocked_events) == self.candidates_cap_blocked
                ),
                selected_count_after=len(selected_ids),
                cumulative_selected_digest_before=selected_digest_before,
                cumulative_selected_digest=selected_digest,
                primary_group_counts_before=tuple(primary_counts_before_ordered),
                primary_group_count_digest_before=primary_digest_before,
                primary_group_counts=tuple(primary_counts_ordered),
                primary_group_count_digest=primary_digest,
                frontier_digest=frontier_digest.hexdigest(),
                quota_frontier_digest=(
                    frontier_digest.hexdigest()
                    if self.stage_type == "SECONDARY_QUOTA"
                    else None
                ),
                fill_frontier_digest=(
                    frontier_digest.hexdigest()
                    if self.stage_type == "DETERMINISTIC_FILL"
                    else None
                ),
                frontier_digest_complete=self.frontier_digest_complete,
            )
        )


def _ordered_primary_counts(primary_counts: Counter[str]) -> list[tuple[str, int]]:
    return [
        (primary, count)
        for primary, count in sorted(
            primary_counts.items(), key=lambda item: item[0].encode("utf-8")
        )
    ]


def _primary_counts_digest(primary_counts: list[tuple[str, int]]) -> str:
    return hashlib.sha256(
        json.dumps(
            primary_counts,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _event_digest(domain: bytes, events: list[tuple[bytes, str, str]]) -> str:
    digest = hashlib.sha256(domain)
    digest.update(len(events).to_bytes(8, "big"))
    for identity, rank, primary in events:
        for raw in (identity, bytes.fromhex(rank), primary.encode("utf-8")):
            digest.update(len(raw).to_bytes(8, "big"))
            digest.update(raw)
    return digest.hexdigest()


def _score(domain: bytes, identity: bytes) -> bytes:
    return hashlib.sha256(domain + b"\0" + identity).digest()


def _identity_digest(domain: bytes, identities: tuple[bytes, ...]) -> str:
    values = sorted(identities)
    digest = hashlib.sha256(domain)
    digest.update(len(values).to_bytes(8, "big"))
    for value in values:
        digest.update(value)
    return digest.hexdigest()


def _rank_key(domain: bytes, identity: bytes) -> int:
    """Encode the exact `(SHA-256 score, stable ID)` ordering as one integer."""
    return (int.from_bytes(_score(domain, identity), "big") << 256) | int.from_bytes(
        identity, "big"
    )


def _candidate_payload(candidate: PilotCandidate) -> dict[str, object]:
    return {
        "safety_logical_record_number": candidate.safety_logical_record_number,
        "safety_source_file": candidate.safety_source_file,
        "stable_id_hex": candidate.stable_source_row_id_v1.hex(),
        "strata": dict(
            sorted(
                candidate.strata.items(),
                key=lambda item: (item[0].encode("utf-8"), item[1].encode("utf-8")),
            )
        ),
        "targeted_safety_case": candidate.targeted_safety_case,
    }


def bounded_snapshot_state(
    snapshot: BoundedCandidateSnapshot,
) -> tuple[str, dict[str, int]]:
    """Canonical exact selector-relevant state and privacy-safe counts."""

    mandatory = [
        _candidate_payload(candidate)
        for _, candidate in sorted(snapshot.mandatory.items())
    ]
    quota_frontiers = []
    for key, entries in sorted(
        snapshot.quota_heaps.items(),
        key=lambda item: tuple(value.encode("utf-8") for value in item[0]),
    ):
        quota_frontiers.append(
            {
                "bucket": list(key),
                "candidates": [
                    {
                        "candidate": _candidate_payload(candidate),
                        "rank_key_hex": f"{-negative_rank:0128x}",
                    }
                    for negative_rank, _, candidate in sorted(
                        entries, key=lambda entry: (-entry[0], entry[1])
                    )
                ],
            }
        )
    fill_frontiers = []
    for primary, entries in sorted(
        snapshot.fill_heaps.items(), key=lambda item: item[0].encode("utf-8")
    ):
        fill_frontiers.append(
            {
                "candidates": [
                    {
                        "candidate": _candidate_payload(candidate),
                        "rank_key_hex": f"{-negative_rank:0128x}",
                    }
                    for negative_rank, _, candidate in sorted(
                        entries, key=lambda entry: (-entry[0], entry[1])
                    )
                ],
                "primary": primary,
            }
        )
    group_counts = [
        {"category": category, "count": count, "dimension": dimension}
        for (dimension, category), count in sorted(
            snapshot.group_counts.items(),
            key=lambda item: (item[0][0].encode(), item[0][1].encode()),
        )
    ]
    quota_bucket_counts = [
        {
            "category": category,
            "count": count,
            "dimension": dimension,
            "primary": primary,
        }
        for (dimension, category, primary), count in sorted(
            snapshot.quota_bucket_counts.items(),
            key=lambda item: tuple(value.encode("utf-8") for value in item[0]),
        )
    ]
    payload = {
        "fill_frontiers": fill_frontiers,
        "group_counts": group_counts,
        "mandatory": mandatory,
        "quota_frontiers": quota_frontiers,
        "quota_bucket_counts": quota_bucket_counts,
        "row_count": snapshot.row_count,
        "safety_locations": [
            [source_file, logical_record_number]
            for source_file, logical_record_number in sorted(snapshot.safety_locations)
        ],
        "state_version": "phase03_bounded_candidate_state_digest_v3",
    }
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    counts = {
        "fill_frontier_entries": sum(
            len(entries) for entries in snapshot.fill_heaps.values()
        ),
        "group_count": len(snapshot.group_counts),
        "mandatory_candidate_count": len(snapshot.mandatory),
        "primary_group_count": sum(
            1 for dimension, _ in snapshot.group_counts if dimension == "primary_country_group"
        ),
        "quota_frontier_entries": sum(
            len(entries) for entries in snapshot.quota_heaps.values()
        ),
        "quota_bucket_count": len(snapshot.quota_bucket_counts),
        "rare_candidate_count": sum(
            candidate.strata.get("country_cohort") == "RARE"
            for candidate in snapshot.mandatory.values()
        ),
        "retained_candidate_count": snapshot.retained_candidate_count(),
        "row_count": snapshot.row_count,
        "safety_candidate_count": len(snapshot.safety_locations),
    }
    return hashlib.sha256(raw).hexdigest(), counts


def _consider_lowest(
    heap: list[HeapEntry],
    *,
    limit: int,
    rank_key: int,
    candidate: PilotCandidate,
) -> None:
    if limit < 1:
        raise ValueError("bounded candidate limit must be positive")
    entry = (-rank_key, candidate.stable_source_row_id_v1, candidate)
    if len(heap) < limit:
        heapq.heappush(heap, entry)
        return
    if rank_key < -heap[0][0]:
        heapq.heapreplace(heap, entry)


@dataclass(slots=True)
class BoundedCandidateSnapshot:
    """Mergeable exact top-K state for the frozen pilot selector."""

    row_count: int = 0
    group_counts: Counter[GroupKey] = field(default_factory=Counter)
    quota_bucket_counts: Counter[QuotaBucketKey] = field(default_factory=Counter)
    mandatory: dict[bytes, PilotCandidate] = field(default_factory=dict)
    quota_heaps: dict[QuotaBucketKey, list[HeapEntry]] = field(default_factory=dict)
    fill_heaps: dict[str, list[HeapEntry]] = field(default_factory=dict)
    safety_locations: set[tuple[str, int]] = field(default_factory=set)
    seen_ids: set[bytes] | None = None

    def retained_candidate_count(self) -> int:
        return len(
            {
                *self.mandatory,
                *(
                    entry[1]
                    for heap in self.quota_heaps.values()
                    for entry in heap
                ),
                *(entry[1] for heap in self.fill_heaps.values() for entry in heap),
            }
        )


@dataclass(frozen=True, slots=True)
class BoundedPilotSelection:
    selection: PilotSelection
    selected_candidates: tuple[PilotCandidate, ...]
    population_count: int
    retained_candidate_count: int


class ExactBoundedCandidateReducer:
    """Exact bounded reducer for `phase03_sampling_contract_v1`.

    The reduction retains all mandatory candidates, the exact per-primary top-K
    quota candidates for every secondary group where K is the primary cap, and
    the exact per-primary fill candidates allowed by that cap. Population
    counts remain exact. K cannot be only the minimum quota: the frozen
    reference enters a quota cursor even when an overlapping earlier selection
    already satisfies the current minimum.
    """

    def __init__(
        self,
        config: PilotSamplingConfig,
        *,
        track_all_seen_ids: bool,
    ) -> None:
        if config.minimum_per_stratum < 1 or config.maximum_primary_stratum < 1:
            raise ValueError("pilot quota and cap must be positive")
        self.config = config
        self.quota_domain = config.seed_domain + b":quota"
        self.fill_domain = config.seed_domain + b":fill"
        self.snapshot = BoundedCandidateSnapshot(
            seen_ids=set() if track_all_seen_ids else None
        )

    def accept(self, candidate: PilotCandidate) -> None:
        identity = candidate.stable_source_row_id_v1
        if self.snapshot.seen_ids is not None:
            if identity in self.snapshot.seen_ids:
                raise ValueError("pilot population contains duplicate stable IDs")
            self.snapshot.seen_ids.add(identity)
        primary = candidate.strata.get(self.config.primary_stratum)
        if not primary:
            raise ValueError("pilot candidate lacks configured primary stratum")

        self.snapshot.row_count += 1
        self.snapshot.group_counts.update(candidate.strata.items())
        if candidate.targeted_safety_case or candidate.strata.get("country_cohort") == "RARE":
            previous = self.snapshot.mandatory.setdefault(identity, candidate)
            if previous != candidate:
                raise ValueError("pilot population contains duplicate stable IDs")
        if candidate.safety_source_file is not None:
            location = (
                candidate.safety_source_file,
                int(candidate.safety_logical_record_number or 0),
            )
            if location in self.snapshot.safety_locations:
                raise ValueError("Phase 1 safety location matched more than once")
            self.snapshot.safety_locations.add(location)

        quota_rank = _rank_key(self.quota_domain, identity)
        for dimension, category in candidate.strata.items():
            if dimension == self.config.primary_stratum:
                continue
            key = (dimension, category, primary)
            self.snapshot.quota_bucket_counts[key] += 1
            _consider_lowest(
                self.snapshot.quota_heaps.setdefault(key, []),
                # The frozen SQLite reference enters a quota cursor even when
                # earlier overlapping strata already satisfy the target. To
                # reproduce that behavior exactly, the next unselected row may
                # sit behind as many as `maximum_primary_stratum` previously
                # selected rows from the same primary group. Keeping the first
                # primary-cap rows is sufficient and necessary; an omitted row
                # cannot be selected before that primary is capped.
                limit=self.config.maximum_primary_stratum,
                rank_key=quota_rank,
                candidate=candidate,
            )
        _consider_lowest(
            self.snapshot.fill_heaps.setdefault(primary, []),
            limit=self.config.maximum_primary_stratum,
            rank_key=_rank_key(self.fill_domain, identity),
            candidate=candidate,
        )

    def merge(self, other: BoundedCandidateSnapshot) -> None:
        if self.snapshot.seen_ids is not None:
            if other.seen_ids is None:
                raise ValueError("cannot prove duplicate-free bounded-state merge")
            overlap = self.snapshot.seen_ids.intersection(other.seen_ids)
            if overlap:
                raise ValueError("pilot population contains duplicate stable IDs")
            self.snapshot.seen_ids.update(other.seen_ids)
        self.snapshot.row_count += other.row_count
        self.snapshot.group_counts.update(other.group_counts)
        self.snapshot.quota_bucket_counts.update(other.quota_bucket_counts)
        for identity, candidate in other.mandatory.items():
            previous = self.snapshot.mandatory.setdefault(identity, candidate)
            if previous != candidate:
                raise ValueError("pilot population contains duplicate stable IDs")
        overlap_locations = self.snapshot.safety_locations.intersection(
            other.safety_locations
        )
        if overlap_locations:
            raise ValueError("Phase 1 safety location matched more than once")
        self.snapshot.safety_locations.update(other.safety_locations)
        for key, entries in other.quota_heaps.items():
            destination = self.snapshot.quota_heaps.setdefault(key, [])
            for negative_rank, _, candidate in entries:
                _consider_lowest(
                    destination,
                    # Each worker already retained the first primary-cap rows
                    # for this quota/primary frontier.  The merge must use the
                    # same bound: truncating back to the minimum quota loses
                    # rows that can become eligible after overlapping earlier
                    # stages consume other candidates.
                    limit=self.config.maximum_primary_stratum,
                    rank_key=-negative_rank,
                    candidate=candidate,
                )
        for primary, entries in other.fill_heaps.items():
            destination = self.snapshot.fill_heaps.setdefault(primary, [])
            for negative_rank, _, candidate in entries:
                _consider_lowest(
                    destination,
                    limit=self.config.maximum_primary_stratum,
                    rank_key=-negative_rank,
                    candidate=candidate,
                )

    def select(
        self,
        *,
        input_phase02_manifest_identity: str,
        selection_timestamp: str,
        effective_sampling_fingerprint: str,
        trace: SelectionTrace | None = None,
    ) -> BoundedPilotSelection:
        state = self.snapshot
        if state.row_count < self.config.total_count:
            raise ValueError("pilot population is smaller than requested sample")
        selected: dict[bytes, PilotCandidate] = {}
        primary_counts: Counter[str] = Counter()

        def add(candidate: PilotCandidate) -> bool:
            identity = candidate.stable_source_row_id_v1
            if identity in selected:
                return True
            primary = candidate.strata[self.config.primary_stratum]
            if len(selected) >= self.config.total_count:
                return False
            if primary_counts[primary] >= self.config.maximum_primary_stratum:
                return False
            selected[identity] = candidate
            primary_counts[primary] += 1
            return True

        targeted = sorted(
            (
                candidate
                for candidate in state.mandatory.values()
                if candidate.targeted_safety_case
            ),
            key=lambda candidate: candidate.stable_source_row_id_v1,
        )
        stage = (
            trace.start_stage(
                stage_type="TARGETED_SAFETY",
                target=len(targeted),
                available=len(targeted),
                represented_before=0,
            )
            if trace is not None
            else None
        )
        for candidate in targeted:
            added = add(candidate)
            if stage is not None:
                stage.observe(
                    candidate,
                    rank=candidate.stable_source_row_id_v1,
                    primary_group=candidate.strata[self.config.primary_stratum],
                    outcome=(
                        "SELECTED"
                        if added
                        else "PRIMARY_CAP_BLOCKED"
                        if primary_counts[
                            candidate.strata[self.config.primary_stratum]
                        ]
                        >= self.config.maximum_primary_stratum
                        else "TOTAL_COUNT_BLOCKED"
                    ),
                )
            if not added:
                if stage is not None:
                    stage.finish(
                        selected_ids=tuple(selected), primary_counts=primary_counts
                    )
                raise PilotSelectionInfeasibleError(
                    "targeted safety cases violate primary cap",
                    reason_code="TARGETED_SAFETY_PRIMARY_CAP",
                    dimension=self.config.primary_stratum,
                    category=candidate.strata[self.config.primary_stratum],
                    primary_cap=self.config.maximum_primary_stratum,
                )
        if stage is not None:
            stage.finish(selected_ids=tuple(selected), primary_counts=primary_counts)

        rare = sorted(
            (
                candidate
                for candidate in state.mandatory.values()
                if candidate.strata.get("country_cohort") == "RARE"
            ),
            key=lambda candidate: (
                candidate.strata[self.config.primary_stratum].encode("utf-8"),
                candidate.stable_source_row_id_v1,
            ),
        )
        stage = (
            trace.start_stage(
                stage_type="RARE_MANDATORY",
                dimension="country_cohort",
                category="RARE",
                target=len(rare),
                available=len(rare),
                represented_before=sum(
                    candidate.strata.get("country_cohort") == "RARE"
                    for candidate in selected.values()
                ),
            )
            if trace is not None
            else None
        )
        for candidate in rare:
            identity = candidate.stable_source_row_id_v1
            if identity in selected:
                continue
            added = add(candidate)
            if stage is not None:
                stage.observe(
                    candidate,
                    rank=candidate.stable_source_row_id_v1,
                    primary_group=candidate.strata[self.config.primary_stratum],
                    outcome=(
                        "SELECTED"
                        if added
                        else "PRIMARY_CAP_BLOCKED"
                        if primary_counts[
                            candidate.strata[self.config.primary_stratum]
                        ]
                        >= self.config.maximum_primary_stratum
                        else "TOTAL_COUNT_BLOCKED"
                    ),
                )
            if not added:
                if stage is not None:
                    stage.finish(
                        selected_ids=tuple(selected), primary_counts=primary_counts
                    )
                raise PilotSelectionInfeasibleError(
                    "rare primary-group inclusion is infeasible",
                    reason_code="RARE_PRIMARY_CAP",
                    dimension=self.config.primary_stratum,
                    category=candidate.strata[self.config.primary_stratum],
                    primary_cap=self.config.maximum_primary_stratum,
                )
        if stage is not None:
            stage.finish(selected_ids=tuple(selected), primary_counts=primary_counts)

        group_keys = sorted(
            (
                key
                for key in state.group_counts
                if key[0] != self.config.primary_stratum
            ),
            key=lambda key: (key[0].encode("utf-8"), key[1].encode("utf-8")),
        )
        for dimension, category in group_keys:
            target = min(
                state.group_counts[(dimension, category)],
                self.config.minimum_per_stratum,
            )
            represented = sum(
                candidate.strata.get(dimension) == category
                for candidate in selected.values()
            )
            stage = (
                trace.start_stage(
                    stage_type="SECONDARY_QUOTA",
                    dimension=dimension,
                    category=category,
                    target=target,
                    available=state.group_counts[(dimension, category)],
                    represented_before=represented,
                )
                if trace is not None
                else None
            )
            candidates_by_id: dict[bytes, PilotCandidate] = {}
            for (observed_dimension, observed_category, _), entries in state.quota_heaps.items():
                if (observed_dimension, observed_category) != (dimension, category):
                    continue
                for _, identity, candidate in entries:
                    candidates_by_id[identity] = candidate
            ordered = sorted(
                candidates_by_id.values(),
                key=lambda candidate: (
                    _score(self.quota_domain, candidate.stable_source_row_id_v1),
                    candidate.stable_source_row_id_v1,
                ),
            )
            candidates_considered = 0
            cap_blocked_candidates = 0
            for candidate in ordered:
                identity = candidate.stable_source_row_id_v1
                if identity in selected:
                    continue
                candidates_considered += 1
                primary = candidate.strata[self.config.primary_stratum]
                added = add(candidate)
                if stage is not None:
                    stage.observe(
                        candidate,
                        rank=_score(
                            self.quota_domain,
                            candidate.stable_source_row_id_v1,
                        ),
                        primary_group=primary,
                        outcome=(
                            "SELECTED"
                            if added
                            else "PRIMARY_CAP_BLOCKED"
                            if primary_counts[primary]
                            >= self.config.maximum_primary_stratum
                            else "TOTAL_COUNT_BLOCKED"
                        ),
                    )
                if added:
                    represented += 1
                elif primary_counts[primary] >= self.config.maximum_primary_stratum:
                    cap_blocked_candidates += 1
                if represented >= target:
                    break
            if represented < target and stage is not None:
                if stage.represented_before is None:
                    raise AssertionError("quota stage requires represented count")
                selected_in_group_by_primary = Counter(
                    candidate.strata[self.config.primary_stratum]
                    for candidate in selected.values()
                    if candidate.strata.get(dimension) == category
                )
                exact_cap_blocked = sum(
                    count - selected_in_group_by_primary[primary]
                    for (observed_dimension, observed_category, primary), count in state.quota_bucket_counts.items()
                    if (observed_dimension, observed_category) == (dimension, category)
                    and primary_counts[primary]
                    >= self.config.maximum_primary_stratum
                )
                candidates_considered = (
                    state.group_counts[(dimension, category)]
                    - stage.represented_before
                )
                cap_blocked_candidates = exact_cap_blocked
                stage.reconcile_exhausted_frontier(
                    candidates_considered=candidates_considered,
                    candidates_cap_blocked=exact_cap_blocked,
                )
            if stage is not None:
                stage.finish(selected_ids=tuple(selected), primary_counts=primary_counts)
            if represented < target:
                raise PilotSelectionInfeasibleError(
                    "pilot quotas/caps cannot satisfy minimum stratum quota",
                    reason_code="MINIMUM_STRATUM_QUOTA",
                    dimension=dimension,
                    category=category,
                    target=target,
                    represented=represented,
                    available=state.group_counts[(dimension, category)],
                    candidates_considered=candidates_considered,
                    cap_blocked_candidates=cap_blocked_candidates,
                    primary_cap=self.config.maximum_primary_stratum,
                )

        if len(selected) > self.config.total_count:
            raise ValueError("targeted/quota selection exceeds pilot total")
        fill_candidates: dict[bytes, PilotCandidate] = {}
        for entries in state.fill_heaps.values():
            for _, identity, candidate in entries:
                fill_candidates[identity] = candidate
        stage = (
            trace.start_stage(
                stage_type="DETERMINISTIC_FILL",
                target=self.config.total_count,
                available=state.row_count,
                represented_before=len(selected),
            )
            if trace is not None
            else None
        )
        for candidate in sorted(
            fill_candidates.values(),
            key=lambda item: (
                _score(self.fill_domain, item.stable_source_row_id_v1),
                item.stable_source_row_id_v1,
            ),
        ):
            if len(selected) == self.config.total_count:
                break
            identity = candidate.stable_source_row_id_v1
            if identity in selected:
                continue
            primary = candidate.strata[self.config.primary_stratum]
            added = add(candidate)
            if stage is not None:
                stage.observe(
                    candidate,
                    rank=_score(self.fill_domain, identity),
                    primary_group=primary,
                    outcome=(
                        "SELECTED"
                        if added
                        else "PRIMARY_CAP_BLOCKED"
                        if primary_counts[primary]
                        >= self.config.maximum_primary_stratum
                        else "TOTAL_COUNT_BLOCKED"
                    ),
                )
        if stage is not None:
            stage.finish(selected_ids=tuple(selected), primary_counts=primary_counts)
        if len(selected) != self.config.total_count:
            raise PilotSelectionInfeasibleError(
                "pilot quotas/caps cannot produce the requested sample",
                reason_code="PILOT_TOTAL_UNREACHABLE_UNDER_PRIMARY_CAP",
                target=self.config.total_count,
                represented=len(selected),
                available=state.row_count,
            )

        split_domain = self.config.seed_domain + b":split"
        ordered_ids = sorted(
            selected,
            key=lambda identity: (_score(split_domain, identity), identity),
        )
        development = tuple(ordered_ids[: self.config.development_count])
        locked = tuple(ordered_ids[self.config.development_count :])
        seal = PilotSeal(
            pilot_version=self.config.pilot_version,
            sampling_config_fingerprint=effective_sampling_fingerprint,
            seed=self.config.seed_domain.decode("utf-8"),
            development_identity_digest=_identity_digest(
                b"phase03:development_identities_v1\0", development
            ),
            locked_evaluation_identity_digest=_identity_digest(
                b"phase03:locked_identities_v1\0", locked
            ),
            selection_timestamp=selection_timestamp,
            input_phase02_manifest_identity=input_phase02_manifest_identity,
            development_count=len(development),
            locked_evaluation_count=len(locked),
        )
        return BoundedPilotSelection(
            PilotSelection(development, locked, seal),
            tuple(selected[identity] for identity in sorted(selected)),
            state.row_count,
            state.retained_candidate_count(),
        )
