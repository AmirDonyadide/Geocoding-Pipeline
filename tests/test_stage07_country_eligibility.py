from __future__ import annotations

import json
from pathlib import Path

import pytest

from safe_geocoding_pipeline.preprocessing.stages.s07_country_eligibility import (
    COUNTRY_CONFLICTING,
    COUNTRY_CONTEXT_UNRESOLVED,
    COUNTRY_INVALID,
    COUNTRY_MISSING,
    COUNTRY_PARTIAL,
    COUNTRY_UNANIMOUS_VALID,
    DEEPPARSE,
    ELIGIBILITY_MANIFEST_RELATIVE_PATH,
    ELIGIBLE_BOTH,
    ELIGIBLE_LIBPOSTAL_ONLY,
    LIBPOSTAL,
    PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY,
    PARSER_ELIGIBILITY_INVALID_COUNTRY,
    PARSER_ELIGIBILITY_MISSING_COUNTRY,
    PARSER_ELIGIBILITY_PARTIAL_COUNTRY,
    PARSER_ELIGIBLE_COUNTRY,
    PARSER_NOT_APPLICABLE_COUNTRY,
    Stage07CountryEligibilityError,
    classify_country_provenance,
    joint_eligibility,
    load_eligibility_manifest,
    parser_eligibility,
)


REPOSITORY = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPOSITORY / ELIGIBILITY_MANIFEST_RELATIVE_PATH


def test_exact_public_eligibility_manifest_is_coherent() -> None:
    manifest = load_eligibility_manifest(MANIFEST_PATH)

    assert len(manifest.valid_iso_alpha2_codes) == 249
    assert manifest.deepparse_trained_country_codes == {
        "at",
        "au",
        "br",
        "ca",
        "ch",
        "cz",
        "de",
        "dk",
        "es",
        "fi",
        "fr",
        "gb",
        "it",
        "kr",
        "mx",
        "nl",
        "no",
        "pl",
        "ru",
        "us",
    }


@pytest.mark.parametrize(
    ("values", "expected_status", "expected_code"),
    [
        (("de", "de"), COUNTRY_UNANIMOUS_VALID, "de"),
        ((None, ""), COUNTRY_MISSING, None),
        (("de", ""), COUNTRY_PARTIAL, None),
        (("DE", None), COUNTRY_INVALID, None),
        (("de", "fr"), COUNTRY_CONFLICTING, None),
        (("de", "BAD"), COUNTRY_PARTIAL, None),
    ],
)
def test_country_provenance_statuses_are_fail_closed(
    values: tuple[str | None, ...], expected_status: str, expected_code: str | None
) -> None:
    manifest = load_eligibility_manifest(MANIFEST_PATH)
    provenance = classify_country_provenance(
        values, valid_codes=manifest.valid_iso_alpha2_codes
    )
    assert provenance.status == expected_status
    assert provenance.country_code == expected_code


def test_parser_support_is_parser_specific_and_zero_shot_is_not_training() -> None:
    manifest = load_eligibility_manifest(MANIFEST_PATH)
    trained = manifest.deepparse_trained_country_codes
    south_korea = classify_country_provenance(
        ("kr",), valid_codes=manifest.valid_iso_alpha2_codes
    )
    japan = classify_country_provenance(
        ("jp",), valid_codes=manifest.valid_iso_alpha2_codes
    )

    assert (
        parser_eligibility(
            LIBPOSTAL, south_korea, deepparse_trained_country_codes=trained
        )
        == PARSER_ELIGIBLE_COUNTRY
    )
    assert (
        parser_eligibility(
            DEEPPARSE, south_korea, deepparse_trained_country_codes=trained
        )
        == PARSER_ELIGIBLE_COUNTRY
    )
    assert (
        parser_eligibility(LIBPOSTAL, japan, deepparse_trained_country_codes=trained)
        == PARSER_ELIGIBLE_COUNTRY
    )
    assert (
        parser_eligibility(DEEPPARSE, japan, deepparse_trained_country_codes=trained)
        == PARSER_NOT_APPLICABLE_COUNTRY
    )
    assert (
        joint_eligibility(PARSER_ELIGIBLE_COUNTRY, PARSER_ELIGIBLE_COUNTRY)
        == ELIGIBLE_BOTH
    )
    assert (
        joint_eligibility(PARSER_ELIGIBLE_COUNTRY, PARSER_NOT_APPLICABLE_COUNTRY)
        == ELIGIBLE_LIBPOSTAL_ONLY
    )


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ((None,), PARSER_ELIGIBILITY_MISSING_COUNTRY),
        (("de", None), PARSER_ELIGIBILITY_PARTIAL_COUNTRY),
        (("ZZ",), PARSER_ELIGIBILITY_INVALID_COUNTRY),
        (("de", "fr"), PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY),
    ],
)
def test_unresolved_country_never_selects_a_parser_country(
    values: tuple[str | None, ...], expected: str
) -> None:
    manifest = load_eligibility_manifest(MANIFEST_PATH)
    provenance = classify_country_provenance(
        values, valid_codes=manifest.valid_iso_alpha2_codes
    )
    libpostal = parser_eligibility(
        LIBPOSTAL,
        provenance,
        deepparse_trained_country_codes=manifest.deepparse_trained_country_codes,
    )
    deepparse = parser_eligibility(
        DEEPPARSE,
        provenance,
        deepparse_trained_country_codes=manifest.deepparse_trained_country_codes,
    )
    assert libpostal == expected
    assert deepparse == expected
    assert joint_eligibility(libpostal, deepparse) == COUNTRY_CONTEXT_UNRESOLVED


def test_manifest_rejects_zero_shot_as_trained(tmp_path: Path) -> None:
    raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    raw["parsers"]["DEEPPARSE"]["zero_shot_countries_eligible"] = True
    changed = tmp_path / "eligibility.json"
    changed.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(Stage07CountryEligibilityError, match="support semantics"):
        load_eligibility_manifest(changed)


def test_candidate_with_no_occurrence_fails_closed() -> None:
    manifest = load_eligibility_manifest(MANIFEST_PATH)
    with pytest.raises(Stage07CountryEligibilityError, match="no occurrences"):
        classify_country_provenance((), valid_codes=manifest.valid_iso_alpha2_codes)
