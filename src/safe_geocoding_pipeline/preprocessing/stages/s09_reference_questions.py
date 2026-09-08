"""Streaming Stage 8 argument pointers; this is not another map-back layer."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from . import s09_reference_contract as c


TRUSTED_FIELD = "stage07_trusted_country_iso_code"
COMPONENT_FIELD = "stage08_raw_libpostal_value"
ATOMIC = {
    "POSTCODE": ("Q04", "Q05"),
    "LOCALITY": ("Q09",),
    "ADMIN": ("Q10",),
    "STREET": ("Q12",),
    "PARSER_COUNTRY_CODE": ("Q14",),
}
RELATIONSHIPS = ("Q06", "Q07", "Q08", "Q11", "Q13")


@dataclass(frozen=True)
class Observation:
    role: str
    value: str | None
    origin_relation: str
    origin_field: str | None
    component_ordinal: int | None
    observed_role_count: int
    semantic_class: str

    @classmethod
    def missing(cls, role: str, count: int = 0) -> Observation:
        return cls(
            role, None, "MISSING_OR_AMBIGUOUS", None, None, count, "MECHANICAL_INDEX"
        )

    def argument(
        self, question: str, reference: str, country: str
    ) -> tuple[dict[str, Any], str | None]:
        method = (
            c.NO_NORM
            if self.value is None or self.observed_role_count != 1
            else c.normalization_method(
                question, self.role, reference, country, self.value
            )
        )
        normalized = (
            None
            if method == c.NO_NORM
            else c.normalize(method, self.value or "", country)
        )
        granularity = (
            "COUNTRY_CODE"
            if self.role in ("COUNTRY_CODE", "PARSER_COUNTRY_CODE", "TRUSTED_COUNTRY")
            else "FULL_ADMIN_CODE"
            if method == c.ISO_NORM
            else "FULL_POSTCODE"
            if self.role == "POSTCODE"
            else "UNSUPPORTED"
            if method == c.NO_NORM
            else "REFERENCE_NAME"
        )
        return (
            {
                "role": self.role,
                "origin_relation": self.origin_relation,
                "origin_field": self.origin_field,
                "component_ordinal": self.component_ordinal,
                "observed_role_count": self.observed_role_count,
                "origin_semantic_class": self.semantic_class,
                "normalization_id": method,
                "normalized_value_sha256": None
                if normalized is None
                else c.identity("NORMALIZED_VALUE", (method, normalized)),
                "value_granularity": granularity,
            },
            normalized,
        )


@dataclass(frozen=True)
class EvaluationQuestion:
    candidate_id: bytes
    source_id: bytes | None
    scope: str
    country: str
    question_id: str
    observations: tuple[Observation, ...]

    @property
    def interpretation(self) -> str:
        if self.question_id in ("Q03", "Q15") or (
            self.scope == "PARSER_CANDIDATE" and self.question_id == "Q01"
        ):
            return "CONTEXT_METADATA"
        return (
            "SOURCE_FIELD_ROLE"
            if self.scope == "SOURCE_ROW"
            else "CONDITIONAL_PARSER_ROLE"
        )

    def question_identity(self, stage08_logical: bytes) -> bytes:
        origins = tuple(
            (
                o.origin_relation,
                o.origin_field,
                o.component_ordinal,
                o.observed_role_count,
            )
            for o in self.observations
        )
        return c.identity(
            "QUESTION",
            (
                c.catalog_fingerprint(),
                stage08_logical,
                self.candidate_id,
                self.scope,
                self.source_id,
                self.question_id,
                self.interpretation,
                c.QUESTIONS[self.question_id].claim_scope,
                origins,
            ),
        )


def country_context(candidate: Mapping[str, Any]) -> tuple[str, Observation]:
    raw = candidate[TRUSTED_FIELD]
    country = (
        c.ascii_upper(raw)
        if candidate["stage07_country_provenance_status"] == "COUNTRY_UNANIMOUS_VALID"
        and raw is not None
        else "UNRESOLVED"
    )
    observation = (
        Observation(
            "TRUSTED_COUNTRY",
            raw,
            "STAGE08_CANDIDATE",
            TRUSTED_FIELD,
            None,
            1,
            "TRUSTED_SOURCE_CONTEXT",
        )
        if raw is not None
        else Observation.missing("TRUSTED_COUNTRY")
    )
    return country, observation


def source_questions(
    source: Mapping[str, Any], candidate: Mapping[str, Any]
) -> Iterator[EvaluationQuestion]:
    candidate_id = candidate["stage06_exact_candidate_id"]
    c.require(
        candidate_id
        in (
            source["stage06_standard_exact_candidate_id"],
            source["stage06_native_exact_candidate_id"],
        ),
        "SOURCE_CANDIDATE_BINDING_INVALID",
    )
    country, trusted = country_context(candidate)
    observations = {"TRUSTED_COUNTRY": trusted}
    for role, name in c.SOURCE_FIELDS.items():
        raw = source[name]
        observations[role] = (
            Observation(
                role,
                raw,
                "STAGE08_SOURCE_MAP",
                name,
                None,
                1,
                "UPSTREAM_DERIVED_REPRESENTATION",
            )
            if raw is not None
            else Observation.missing(role)
        )
    for question in c.CATALOG:
        if question.question_id == "Q14":
            continue
        yield EvaluationQuestion(
            candidate_id,
            source["stable_source_row_id_v1"],
            "SOURCE_ROW",
            country,
            question.question_id,
            tuple(
                observations.get(role, Observation.missing(role))
                for role in question.roles
            ),
        )


def parser_questions(
    candidate: Mapping[str, Any], components: Iterable[Mapping[str, Any]]
) -> Iterator[EvaluationQuestion]:
    """O(fixed role counters + singleton scalars); never a candidate-sized list."""
    country, trusted = country_context(candidate)
    candidate_id = candidate["stage06_exact_candidate_id"]
    counts = {role: 0 for role in c.PARSER_LABELS}
    singletons: dict[str, Observation] = {}
    reverse_labels = {label: role for role, label in c.PARSER_LABELS.items()}

    def emit(
        question_id: str, observations: Mapping[str, Observation]
    ) -> EvaluationQuestion:
        return EvaluationQuestion(
            candidate_id,
            None,
            "PARSER_CANDIDATE",
            country,
            question_id,
            tuple(
                observations.get(role, Observation.missing(role))
                for role in c.QUESTIONS[question_id].roles
            ),
        )

    country_code = Observation(
        "COUNTRY_CODE",
        trusted.value,
        trusted.origin_relation,
        trusted.origin_field,
        trusted.component_ordinal,
        trusted.observed_role_count,
        trusted.semantic_class,
    )
    for question_id in ("Q01", "Q02", "Q03", "Q15"):
        yield emit(
            question_id, {"COUNTRY_CODE": country_code, "TRUSTED_COUNTRY": trusted}
        )
    ordinal = 0
    for component in components:
        c.require(
            component["stage06_exact_candidate_id"] == candidate_id
            and component["stage08_component_ordinal"] == ordinal,
            "COMPONENT_ORDER_OR_CANDIDATE_INVALID",
        )
        role = reverse_labels.get(component["stage08_safe_parser_evidence_component"])
        if role is not None:
            counts[role] += 1
            observation = Observation(
                role,
                component[COMPONENT_FIELD],
                "STAGE08_COMPONENT",
                COMPONENT_FIELD,
                ordinal,
                1,
                "PARSER_EVIDENCE",
            )
            if counts[role] == 1:
                singletons[role] = observation
            else:
                singletons.pop(role, None)
            for question_id in ATOMIC.get(role, ()):
                yield emit(question_id, {"TRUSTED_COUNTRY": trusted, role: observation})
        ordinal += 1
    c.require(
        ordinal == candidate["stage08_raw_component_count"],
        "COMPONENT_TOTALITY_MISMATCH",
    )
    for role, question_ids in ATOMIC.items():
        if counts[role] == 0:
            for question_id in question_ids:
                yield emit(question_id, {"TRUSTED_COUNTRY": trusted})
    observations = {
        "TRUSTED_COUNTRY": trusted,
        **{
            role: singletons[role] if count == 1 else Observation.missing(role, count)
            for role, count in counts.items()
        },
    }
    for question_id in RELATIONSHIPS:
        yield emit(question_id, observations)
