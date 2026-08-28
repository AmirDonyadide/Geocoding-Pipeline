from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from safe_geocoding_pipeline.preprocessing import stage07_design_cli
from safe_geocoding_pipeline.preprocessing.script_reference import (
    ScriptReference,
    unicode_script_reference_paths,
)
from safe_geocoding_pipeline.preprocessing.stages.s06_exact_deduplication import (
    registry_schema,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_design_diagnostic import (
    ACCEPTED_STAGE06_MANIFEST_FINGERPRINT,
    Stage07DesignDiagnosticConfig,
    Stage07DesignDiagnosticError,
    _candidate_features,
    _diagnostic_selection,
    _difference_types,
    _distribution,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_libpostal_adapter import (
    LibpostalComponent,
    PARSED_EMPTY,
    PARSED_NONEMPTY,
    ParsedAddress,
)


def _parsed(*pairs: tuple[str, str]) -> ParsedAddress:
    components = tuple(
        LibpostalComponent(label=label, value=value) for label, value in pairs
    )
    return ParsedAddress(
        status=PARSED_NONEMPTY if components else PARSED_EMPTY,
        components=components,
    )


def _scripts() -> ScriptReference:
    paths = unicode_script_reference_paths()
    return ScriptReference.from_artifact(
        paths["unicode_manifest"], paths["unicode_artifact"]
    )


def test_case_variant_difference_taxonomy_is_ordered_and_complete() -> None:
    canonical = _parsed(("house_number", "10"), ("road", "example"))
    assert _difference_types(canonical, canonical) == frozenset()
    assert _difference_types(canonical, _parsed()) == {
        "EMPTY_NONEMPTY_DIFFERENCE",
        "COMPONENT_COUNT_DIFFERENCE",
        "LABEL_DIFFERENCE",
        "VALUE_DIFFERENCE",
    }
    assert _difference_types(
        canonical, _parsed(("road", "example"), ("house_number", "10"))
    ) == {"LABEL_DIFFERENCE", "VALUE_DIFFERENCE", "ORDERING_DIFFERENCE"}
    assert _difference_types(
        canonical, _parsed(("house", "10"), ("road", "example"))
    ) == {"LABEL_DIFFERENCE"}
    assert _difference_types(
        canonical, _parsed(("house_number", "11"), ("road", "example"))
    ) == {"VALUE_DIFFERENCE"}


def test_candidate_feature_strata_cover_scripts_and_risk_boundaries() -> None:
    reference = _scripts()
    latin = _candidate_features(
        "10 example street",
        occurrence_count=2,
        standard_count=1,
        native_count=1,
        script_reference=reference,
    )
    assert latin.script_bucket == "LATIN"
    assert latin.representation_bucket == "BOTH"
    assert latin.occurrence_bucket == "REPEATED"

    arabic = _candidate_features(
        "خیابان مثال ۱۲۳",
        occurrence_count=1,
        standard_count=0,
        native_count=1,
        script_reference=reference,
    )
    assert arabic.script_bucket == "ARABIC"
    assert arabic.representation_bucket == "NATIVE_ONLY"

    mixed = _candidate_features(
        "example улица",
        occurrence_count=1,
        standard_count=1,
        native_count=0,
        script_reference=reference,
    )
    assert mixed.script_bucket == "MIXED_SCRIPT"
    assert mixed.representation_bucket == "STANDARD_ONLY"

    numeric = _candidate_features(
        "123456-7890",
        occurrence_count=1,
        standard_count=1,
        native_count=0,
        script_reference=reference,
    )
    assert numeric.numeric_heavy is True

    punctuation = _candidate_features(
        "---///***example",
        occurrence_count=1,
        standard_count=1,
        native_count=0,
        script_reference=reference,
    )
    assert punctuation.punctuation_heavy is True


def test_diagnostic_selection_is_deterministic_and_includes_required_sets(
    tmp_path: Path,
) -> None:
    values = [
        "10 example street",
        "مثال ۱۲۳",
        "пример улица",
        "東京都千代田区",
        "서울특별시",
        "example улица",
        "1234567890",
        "x" * 1_000_000,
    ]
    ids = [index.to_bytes(32, "big") for index in range(1, len(values) + 1)]
    table = pa.Table.from_arrays(
        (
            pa.array(ids, type=pa.binary(32)),
            pa.array(values, type=pa.string()),
            pa.array([1, 1, 1, 1, 1, 2, 1, 1], type=pa.uint64()),
            pa.array([1, 0, 0, 0, 0, 1, 1, 1], type=pa.uint64()),
            pa.array([0, 1, 1, 1, 1, 1, 0, 0], type=pa.uint64()),
        ),
        schema=registry_schema(),
    )
    path = tmp_path / "registry.parquet"
    pq.write_table(table, path, write_page_checksum=True, compression="zstd")
    path.chmod(0o600)

    first = _diagnostic_selection(
        (path,),
        fixed_ids=(ids[0],),
        case_ids=(ids[1],),
        script_reference=_scripts(),
        authoritative_development=False,
    )
    second = _diagnostic_selection(
        (path,),
        fixed_ids=(ids[0],),
        case_ids=(ids[1],),
        script_reference=_scripts(),
        authoritative_development=False,
    )
    assert first == second
    selected, giants, available, fingerprint = first
    assert set(ids).issubset(selected)
    assert giants == {ids[-1]}
    assert available["SCRIPT:ARABIC"] >= 1
    assert available["SCRIPT:CYRILLIC"] >= 1
    assert available["SCRIPT:HAN"] >= 1
    assert available["SCRIPT:HANGUL"] >= 1
    assert available["SCRIPT:MIXED_SCRIPT"] >= 1
    assert len(fingerprint) == 64


def test_distribution_uses_nearest_rank() -> None:
    assert _distribution([]) == {
        "min": 0,
        "median": 0,
        "mean": 0,
        "p95": 0,
        "p99": 0,
        "max": 0,
    }
    assert _distribution([0, 1, 2, 3, 100]) == {
        "min": 0,
        "median": 2,
        "mean": 21.2,
        "p95": 100,
        "p99": 100,
        "max": 100,
    }


def test_design_config_rejects_holdout_and_bad_bounds(tmp_path: Path) -> None:
    common = dict(
        stage05_output_directory=tmp_path / "stage05",
        stage06_output_directory=tmp_path / "stage06",
        expected_stage06_manifest_sha256=ACCEPTED_STAGE06_MANIFEST_FINGERPRINT,
        stage06_review_directory=tmp_path / "stage06_review",
        expected_stage06_review_manifest_sha256="1" * 64,
        parser_bundle_directory=tmp_path / "parser_bundle",
        expected_parser_bundle_fingerprint="2" * 64,
        output_directory=tmp_path / "output",
        execution_git_sha="3" * 40,
    )
    Stage07DesignDiagnosticConfig(**common).validate()
    with pytest.raises(Stage07DesignDiagnosticError, match="HOLDOUT_ACCESS_PROHIBITED"):
        Stage07DesignDiagnosticConfig(
            **{**common, "output_directory": tmp_path / "holdout" / "output"}
        ).validate()
    with pytest.raises(Stage07DesignDiagnosticError, match="INVALID_DIAGNOSTIC_BOUNDS"):
        Stage07DesignDiagnosticConfig(
            **{**common, "giant_timeout_seconds": 0}
        ).validate()


def test_design_cli_requires_slurm_before_input_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setattr(
        "sys.argv",
        [
            "stage07-design",
            "--stage05-output-directory",
            str(tmp_path / "stage05"),
            "--stage06-output-directory",
            str(tmp_path / "stage06"),
            "--expected-stage06-manifest-sha256",
            ACCEPTED_STAGE06_MANIFEST_FINGERPRINT,
            "--stage06-review-directory",
            str(tmp_path / "stage06_review"),
            "--expected-stage06-review-manifest-sha256",
            "1" * 64,
            "--parser-bundle-directory",
            str(tmp_path / "parser_bundle"),
            "--expected-parser-bundle-fingerprint",
            "2" * 64,
            "--output-directory",
            str(tmp_path / "output"),
            "--execution-git-sha",
            "3" * 40,
        ],
    )
    assert stage07_design_cli.main() == 1
    assert "HEAVY_PROCESS_CLUSTER_REQUIRED" in capsys.readouterr().err


def test_stage07_design_cluster_assets_are_fail_closed_and_offline() -> None:
    repository = Path(__file__).resolve().parents[1]
    launcher = (
        repository / "cluster/goethe_nhr/stage07_design_diagnostic.sbatch"
    ).read_text(encoding="utf-8")
    bootstrap = (repository / "cluster/goethe_nhr/stage07_bootstrap_env.sh").read_text(
        encoding="utf-8"
    )
    for required in (
        "SAFE_EXECUTION_SITE=goethe-nhr",
        "SLURM_JOB_ID:?SLURM_JOB_ID is required",
        ACCEPTED_STAGE06_MANIFEST_FINGERPRINT,
        "stage07_design_cli",
        "stage07_bootstrap_env.sh",
        "protected_parsing_network_calls=false",
        "--giant-timeout-seconds 900",
        "--giant-address-space-bytes 51539607552",
    ):
        assert required in launcher
    for forbidden in ("/scratch", "/work/footprint/public", "rsync", "git pull"):
        assert forbidden not in launcher
    assert "validate_parser_bundle" in bootstrap
    assert 'parse_address("10 synthetic example street")' in bootstrap
    assert "HOLDOUT" in launcher
    assert "STAGE08" not in launcher
