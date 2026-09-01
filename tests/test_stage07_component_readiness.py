from __future__ import annotations

import pytest

from safe_geocoding_pipeline.preprocessing.stages.s07_component_readiness import (
    COMPONENTS_ABSTAIN,
    COMPONENTS_READY,
    NOT_ASSESSED,
    NOT_ATTEMPTED_NOT_ELIGIBLE,
    REASON_ELIGIBILITY_MISSING,
    REASON_FRAGMENTATION,
    REASON_INTERNAL_BOUNDARY,
    REASON_LEXICAL_DUPLICATION,
    REASON_LEXICAL_LOSS,
    REASON_PARSED_EMPTY,
    REASON_REPEATED_LABEL,
    REASON_TINY_FRAGMENT,
    Stage07ReadinessError,
    decide_component_readiness,
    structural_signals,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_country_eligibility import (
    PARSER_ELIGIBILITY_MISSING_COUNTRY,
    PARSER_ELIGIBLE_COUNTRY,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_libpostal_adapter import (
    PARSED_EMPTY,
    PARSED_NONEMPTY,
    LibpostalComponent,
)


def _component(value: str, label: str = "road") -> LibpostalComponent:
    return LibpostalComponent(label=label, value=value)


def test_standard_backed_aligned_parse_is_provisionally_ready() -> None:
    decision = decide_component_readiness(
        parser_applicability=PARSER_ELIGIBLE_COUNTRY,
        technical_status=PARSED_NONEMPTY,
        candidate="12 main road",
        components=(_component("12", "house_number"), _component("main road")),
        standard_occurrence_count=1,
        native_occurrence_count=0,
    )
    assert decision.status == COMPONENTS_READY
    assert decision.reason_codes == ()
    assert decision.signals is not None
    assert decision.signals.lexical_numeric_stream_equal


def test_native_only_provenance_is_not_itself_an_abstention_rule() -> None:
    decision = decide_component_readiness(
        parser_applicability=PARSER_ELIGIBLE_COUNTRY,
        technical_status=PARSED_NONEMPTY,
        candidate="synthetic road",
        components=(_component("synthetic road"),),
        standard_occurrence_count=0,
        native_occurrence_count=1,
    )
    assert decision.status == COMPONENTS_READY
    assert decision.reason_codes == ()


def test_internal_boundary_fragmentation_and_repeated_labels_are_preserved() -> None:
    signals = structural_signals(
        "synthetic",
        (_component("syn"), _component("t"), _component("hetic")),
    )
    assert signals.internal_boundary_count == 2
    assert signals.internal_single_codepoint_fragment_count == 1
    assert signals.maximum_components_per_lexical_run == 3
    assert signals.adjacent_repeated_label_internal_boundary_count == 2
    assert signals.reason_codes == (
        REASON_INTERNAL_BOUNDARY,
        REASON_TINY_FRAGMENT,
        REASON_FRAGMENTATION,
        REASON_REPEATED_LABEL,
    )


def test_many_lexical_runs_use_linear_fragmentation_sweep() -> None:
    # The former run-by-component cross product made this bounded synthetic
    # shape impractical.  The exact signal is one component per lexical run.
    run_count = 20_000
    signals = structural_signals(
        " ".join("a" for _ in range(run_count)),
        tuple(_component("a") for _ in range(run_count)),
    )
    assert signals.maximum_components_per_lexical_run == 1
    assert signals.internal_boundary_count == 0


@pytest.mark.parametrize(
    ("candidate", "values", "expected"),
    [
        ("abc123", ("abc",), REASON_LEXICAL_LOSS),
        ("abc", ("abc", "abc"), REASON_LEXICAL_DUPLICATION),
    ],
)
def test_lexical_numeric_loss_and_duplication_abstain(
    candidate: str, values: tuple[str, ...], expected: str
) -> None:
    decision = decide_component_readiness(
        parser_applicability=PARSER_ELIGIBLE_COUNTRY,
        technical_status=PARSED_NONEMPTY,
        candidate=candidate,
        components=tuple(_component(value) for value in values),
        standard_occurrence_count=1,
        native_occurrence_count=0,
    )
    assert decision.status == COMPONENTS_ABSTAIN
    assert expected in decision.reason_codes


def test_parsed_empty_is_nonnull_empty_and_abstained() -> None:
    decision = decide_component_readiness(
        parser_applicability=PARSER_ELIGIBLE_COUNTRY,
        technical_status=PARSED_EMPTY,
        candidate="!!!",
        components=(),
        standard_occurrence_count=1,
        native_occurrence_count=0,
    )
    assert decision.status == COMPONENTS_ABSTAIN
    assert decision.reason_codes == (REASON_PARSED_EMPTY,)


def test_unresolved_country_is_not_attempted_and_not_assessed() -> None:
    decision = decide_component_readiness(
        parser_applicability=PARSER_ELIGIBILITY_MISSING_COUNTRY,
        technical_status=NOT_ATTEMPTED_NOT_ELIGIBLE,
        candidate="not inspected",
        components=None,
        standard_occurrence_count=1,
        native_occurrence_count=0,
    )
    assert decision.status == NOT_ASSESSED
    assert decision.reason_codes == (REASON_ELIGIBILITY_MISSING,)
    assert decision.signals is None


def test_fail_closed_status_component_invariants() -> None:
    with pytest.raises(Stage07ReadinessError, match="exact empty"):
        decide_component_readiness(
            parser_applicability=PARSER_ELIGIBLE_COUNTRY,
            technical_status=PARSED_EMPTY,
            candidate="synthetic",
            components=(_component("synthetic"),),
            standard_occurrence_count=1,
            native_occurrence_count=0,
        )
    with pytest.raises(Stage07ReadinessError, match="cannot contain"):
        decide_component_readiness(
            parser_applicability=PARSER_ELIGIBILITY_MISSING_COUNTRY,
            technical_status=NOT_ATTEMPTED_NOT_ELIGIBLE,
            candidate="synthetic",
            components=(),
            standard_occurrence_count=1,
            native_occurrence_count=0,
        )
