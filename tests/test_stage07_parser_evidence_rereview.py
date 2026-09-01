from dataclasses import replace
from pathlib import Path

import pytest

from safe_geocoding_pipeline.preprocessing.stage07_parser_evidence_rereview_cli import (
    build_parser,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_parser_evidence_rereview import (
    EXPECTED_APPLICABILITY_COUNTS,
    EXPECTED_REASON_COUNTS,
    EXPECTED_TECHNICAL_COUNTS,
    EXPECTED_WARNING_COUNTS,
    REVIEWED_CANDIDATE_SHA,
    RereviewConfig,
    Stage07IndependentRereviewError,
    _validate_country_invariants,
    _validate_no_parser_call,
    _validate_tracked_reports,
)


def _config(tmp_path: Path, *, stage06_root: Path | None = None) -> RereviewConfig:
    return RereviewConfig(
        stage06_root=stage06_root or tmp_path / "stage06",
        stage07_v1_root=tmp_path / "stage07_v1",
        eligibility_artifact=tmp_path / "eligibility.parquet",
        eligibility_audit_manifest=tmp_path / "eligibility.json",
        stage07_v2_root=tmp_path / "stage07_v2",
        source_root=tmp_path / "source",
        output_directory=tmp_path / "review",
        review_git_sha="1" * 40,
    )


def test_review_config_rejects_wrong_candidate_and_prohibited_scopes(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    config.validate()

    with pytest.raises(Stage07IndependentRereviewError, match="REVIEWED_SHA_MISMATCH"):
        replace(config, reviewed_candidate_sha="2" * 40).validate()

    with pytest.raises(Stage07IndependentRereviewError, match="HOLDOUT_ACCESS"):
        _config(tmp_path, stage06_root=tmp_path / "HOLDOUT" / "stage06").validate()
    with pytest.raises(Stage07IndependentRereviewError, match="PRODUCTION_ACCESS"):
        _config(tmp_path, stage06_root=tmp_path / "production" / "stage06").validate()


def test_country_invariants_accept_unanimous_and_reject_conflict() -> None:
    unanimous: dict[str, object] = {
        "occurrence_count": 2,
        "valid_country_occurrence_count": 2,
        "missing_country_occurrence_count": 0,
        "invalid_country_occurrence_count": 0,
        "distinct_valid_country_count": 1,
        "country_provenance_status": "COUNTRY_UNANIMOUS_VALID",
        "unanimous_country_code": "it",
        "libpostal_eligibility": "PARSER_ELIGIBLE_COUNTRY",
    }
    _validate_country_invariants(unanimous)

    inconsistent = dict(unanimous)
    inconsistent["libpostal_eligibility"] = "PARSER_ELIGIBILITY_MISSING_COUNTRY"
    with pytest.raises(
        Stage07IndependentRereviewError, match="COUNTRY_APPLICABILITY_MISMATCH"
    ):
        _validate_country_invariants(inconsistent)

    for unresolved in (
        {
            "occurrence_count": 2,
            "valid_country_occurrence_count": 0,
            "missing_country_occurrence_count": 2,
            "invalid_country_occurrence_count": 0,
            "distinct_valid_country_count": 0,
            "country_provenance_status": "COUNTRY_MISSING",
            "unanimous_country_code": None,
            "libpostal_eligibility": "PARSER_ELIGIBILITY_MISSING_COUNTRY",
        },
        {
            "occurrence_count": 2,
            "valid_country_occurrence_count": 1,
            "missing_country_occurrence_count": 1,
            "invalid_country_occurrence_count": 0,
            "distinct_valid_country_count": 1,
            "country_provenance_status": "COUNTRY_PARTIAL",
            "unanimous_country_code": None,
            "libpostal_eligibility": "PARSER_ELIGIBILITY_PARTIAL_COUNTRY",
        },
        {
            "occurrence_count": 2,
            "valid_country_occurrence_count": 0,
            "missing_country_occurrence_count": 1,
            "invalid_country_occurrence_count": 1,
            "distinct_valid_country_count": 0,
            "country_provenance_status": "COUNTRY_INVALID",
            "unanimous_country_code": None,
            "libpostal_eligibility": "PARSER_ELIGIBILITY_INVALID_COUNTRY",
        },
        {
            "occurrence_count": 2,
            "valid_country_occurrence_count": 2,
            "missing_country_occurrence_count": 0,
            "invalid_country_occurrence_count": 0,
            "distinct_valid_country_count": 2,
            "country_provenance_status": "COUNTRY_CONFLICTING",
            "unanimous_country_code": None,
            "libpostal_eligibility": "PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY",
        },
    ):
        _validate_country_invariants(unresolved)


def test_candidate_projection_static_scan_has_no_parser_call() -> None:
    repository = Path(__file__).resolve().parents[1]
    _validate_no_parser_call(repository)
    _validate_tracked_reports(
        repository,
        applicability_counts=EXPECTED_APPLICABILITY_COUNTS,
        technical_counts=EXPECTED_TECHNICAL_COUNTS,
        warning_counts=EXPECTED_WARNING_COUNTS,
        reason_counts=EXPECTED_REASON_COUNTS,
    )


def test_cli_binds_exact_candidate_sha() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "--stage06-root",
            "/controlled/stage06",
            "--stage07-v1-root",
            "/controlled/stage07_v1",
            "--eligibility-artifact",
            "/controlled/eligibility.parquet",
            "--eligibility-audit-manifest",
            "/controlled/eligibility.json",
            "--stage07-v2-root",
            "/controlled/stage07_v2",
            "--source-root",
            "/controlled/source",
            "--output-directory",
            "/controlled/review",
            "--review-git-sha",
            "3" * 40,
        ]
    )
    assert args.reviewed_candidate_sha == REVIEWED_CANDIDATE_SHA
