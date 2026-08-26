from __future__ import annotations

import hashlib
import json
import stat
import subprocess
from dataclasses import replace
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from safe_geocoding_pipeline.phase02.identity import stable_source_row_id_v1
from safe_geocoding_pipeline.preprocessing.benchmark_runner import (
    BENCHMARK_OUTPUT_SCHEMA_VERSION,
    benchmark_schema,
    benchmark_schema_fingerprint,
)
from safe_geocoding_pipeline.preprocessing.benchmark_sample import (
    BENCHMARK_CONTRACT_VERSION,
    FEATURE_CONTRACT_VERSION,
)
from safe_geocoding_pipeline.preprocessing.reporting.contracts import (
    DEVELOPMENT_REPORTING_CONTRACT_VERSION,
    DEVELOPMENT_REVIEW_SUBSET_CONTRACT_VERSION,
    REVIEW_ALLOCATION_POLICY_VERSION,
    REVIEW_SELECTION_ALGORITHM_VERSION,
    REVIEW_SUBSET_FINGERPRINT_DOMAIN,
    ReviewCandidate,
    ReviewSubsetConfig,
    ReviewSubsetError,
    development_review_subset_sha256_v1,
    select_development_review_subset,
)
from safe_geocoding_pipeline.preprocessing.reporting.development import (
    REVIEW_IDENTITIES_PATH,
    REVIEW_MANIFEST_NAME,
    REVIEW_SUCCESS_MARKER,
    REVIEW_SUMMARY_JSON_PATH,
    REVIEW_SUMMARY_MD_PATH,
    STAGE02_REVIEW_PATH,
    DevelopmentReviewRunConfig,
    materialize_stage02_development_review,
    validate_development_review_bundle,
)
from safe_geocoding_pipeline.preprocessing.reporting.summary import (
    SanitizedStageSummary,
    render_summary_json,
    render_summary_markdown,
    validate_sanitized_summary_payload,
)
from safe_geocoding_pipeline.preprocessing.stages.s02_harmonization import (
    Stage02InputArtifact,
    Stage02InputBinding,
    Stage02RunConfig,
    materialize_stage02,
    write_stage02_input_binding,
)
from safe_geocoding_pipeline.raw_csv import SOURCE_COLUMNS

BENCHMARK_FINGERPRINT = "01" * 32
SOURCE_POPULATION_IDENTITY = "02" * 32
EXECUTION_GIT_SHA = "a" * 40


def _candidate(index: int, *, split: str = "DEVELOPMENT") -> ReviewCandidate:
    presences = ("STANDARD_ONLY", "NATIVE_ONLY", "BOTH_PRESENT", "NEITHER_PRESENT")
    presence = presences[index % len(presences)]
    equality = (
        ("EXACTLY_EQUAL", "CASE_ONLY_OR_TRIVIALLY_EQUAL", "MATERIALLY_DIFFERENT")[
            index % 3
        ]
        if presence == "BOTH_PRESENT"
        else "NOT_BOTH_PRESENT"
    )
    scripts = ("LATIN_ONLY", "NON_LATIN_PRESENT", "MIXED_SCRIPT")
    locations = (
        "no_geocoding_information",
        "previous_geocoding_failure",
        "postcode_interpolated",
        "region_interpolated",
    )
    reasons = (
        ("PREVIOUS_GEOCODING_FAILURE", "MULTIPLE_ADDRESS_LINES")
        if index % 2
        else ("NO_GEOCODING_INFORMATION",)
    )
    return ReviewCandidate(
        stable_source_row_id_v1=hashlib.sha256(
            f"fictional-row-{index}".encode()
        ).digest(),
        source_file=f"fictional-source-{index:04d}.csv",
        benchmark_split=split,
        location_information_stratum=locations[index % len(locations)],
        batch_priority_stratum=str(index % 4),
        country_stratum=f"C{index % 47:02d}",
        standard_native_presence_class=presence,
        standard_native_equality_class=equality,
        standard_line_count=index % 5,
        native_line_count=(index + 2) % 5,
        missingness_class=(
            "POSTCODE_MISSING_CITY_PRESENT_REGION_PRESENT_COUNTRY_PRESENT"
            if index % 5 == 0
            else "POSTCODE_PRESENT_CITY_PRESENT_REGION_PRESENT_COUNTRY_PRESENT"
        ),
        combined_script_class=scripts[index % len(scripts)],
        challenge_flag=True,
        challenge_reasons=reasons,
    )


def _summary(**updates: object) -> SanitizedStageSummary:
    values: dict[str, object] = {
        "status": "STAGE_2_ACCEPTED",
        "stage": "STAGE_2",
        "stage_contract_version": "stage02_schema_provenance_harmonization_contract_v1",
        "execution_git_sha": EXECUTION_GIT_SHA,
        "slurm_job_id": "12345",
        "development_dataset": "BENCHMARK_SAMPLE_V1_DEVELOPMENT",
        "development_fingerprint": "03" * 32,
        "input_benchmark_fingerprint": BENCHMARK_FINGERPRINT,
        "logical_fingerprint": "04" * 32,
        "schema_fingerprint": "05" * 32,
        "metric_groups": {
            "ROW_INTEGRITY": {
                "INPUT_ROWS": 35_000,
                "OUTPUT_ROWS": 35_000,
                "DROPPED_ROWS": 0,
                "ADDED_ROWS": 0,
                "DUPLICATE_IDENTITIES": 0,
            }
        },
        "checks": {
            "STABLE_IDENTITIES_PRESERVED": True,
            "RAW_FIELDS_UNCHANGED": True,
            "HOLDOUT_UNTOUCHED": True,
            "OWNER_ONLY_PERMISSIONS": True,
            "PROTECTED_REVIEW_ARTIFACT": True,
            "ATOMIC_PUBLICATION": True,
            "INPUT_IDENTITY_BOUND": True,
        },
        "interpretation_code": "STAGE02_LOSSLESS_HARMONIZATION",
    }
    values.update(updates)
    return SanitizedStageSummary(**values)  # type: ignore[arg-type]


def test_deterministic_exact_500_row_selection_and_source_coverage() -> None:
    candidates = tuple(_candidate(index) for index in range(600))
    config = ReviewSubsetConfig(target_count=500, expected_development_rows=600)
    first = select_development_review_subset(
        candidates, benchmark_fingerprint=BENCHMARK_FINGERPRINT, config=config
    )
    second = select_development_review_subset(
        tuple(reversed(candidates)),
        benchmark_fingerprint=BENCHMARK_FINGERPRINT,
        config=config,
    )
    first_ids = tuple(item.stable_source_row_id_v1 for item in first.selected)
    second_ids = tuple(item.stable_source_row_id_v1 for item in second.selected)
    assert first_ids == second_ids
    assert len(first_ids) == 500
    assert len(set(first_ids)) == 500
    assert len({item.source_file for item in first.selected}) == 500
    assert {item.location_information_stratum for item in first.selected} == {
        "no_geocoding_information",
        "previous_geocoding_failure",
        "postcode_interpolated",
        "region_interpolated",
    }


def test_selection_rejects_holdout_wrong_count_and_duplicate_identity() -> None:
    candidates = tuple(_candidate(index) for index in range(3))
    config = ReviewSubsetConfig(target_count=2, expected_development_rows=3)
    with pytest.raises(ReviewSubsetError, match="HOLDOUT_ACCESS_PROHIBITED"):
        select_development_review_subset(
            (replace(candidates[0], benchmark_split="HOLDOUT"), *candidates[1:]),
            benchmark_fingerprint=BENCHMARK_FINGERPRINT,
            config=config,
        )
    with pytest.raises(ReviewSubsetError, match="DEVELOPMENT_ROW_COUNT_MISMATCH"):
        select_development_review_subset(
            candidates[:2], benchmark_fingerprint=BENCHMARK_FINGERPRINT, config=config
        )
    with pytest.raises(ReviewSubsetError, match="DUPLICATE_REVIEW_IDENTITY"):
        select_development_review_subset(
            (
                candidates[0],
                replace(
                    candidates[1],
                    stable_source_row_id_v1=candidates[0].stable_source_row_id_v1,
                ),
                candidates[2],
            ),
            benchmark_fingerprint=BENCHMARK_FINGERPRINT,
            config=config,
        )


def test_review_fingerprint_independent_golden_vector_and_population_sensitivity() -> (
    None
):
    config = ReviewSubsetConfig(target_count=2, expected_development_rows=3)
    identities = (bytes(range(32)), bytes(reversed(range(32))))
    observed = development_review_subset_sha256_v1(
        benchmark_fingerprint=BENCHMARK_FINGERPRINT,
        selected_identities=identities,
        config=config,
    )
    assert (
        observed == "ea0101da4bc648ca08cb33a91564e41b8aba56f5718d0fffe23cfd7e04f0e323"
    )

    digest = hashlib.sha256(REVIEW_SUBSET_FINGERPRINT_DOMAIN)

    def text(value: str) -> None:
        encoded = value.encode("utf-8")
        digest.update(b"\x02" + len(encoded).to_bytes(8, "big") + encoded)

    def uint64(value: int) -> None:
        digest.update(b"\x01" + value.to_bytes(8, "big"))

    for value in (
        DEVELOPMENT_REPORTING_CONTRACT_VERSION,
        DEVELOPMENT_REVIEW_SUBSET_CONTRACT_VERSION,
        REVIEW_SELECTION_ALGORITHM_VERSION,
        REVIEW_ALLOCATION_POLICY_VERSION,
    ):
        text(value)
    digest.update(b"\x03" + bytes.fromhex(BENCHMARK_FINGERPRINT))
    uint64(3)
    uint64(2)
    for name, policy_value in config.policy.to_dict().items():
        text(name)
        if isinstance(policy_value, str):
            text(policy_value)
        else:
            uint64(policy_value)
    uint64(2)
    for identity in sorted(identities):
        digest.update(b"\x04" + identity)
    assert observed == digest.hexdigest()
    assert observed != development_review_subset_sha256_v1(
        benchmark_fingerprint="ff" * 32,
        selected_identities=identities,
        config=config,
    )


def test_reporting_api_is_stage_neutral_deterministic_and_allowlisted() -> None:
    summary = _summary(stage="STAGE_9")
    first_json = render_summary_json(summary)
    first_markdown = render_summary_markdown(summary)
    assert first_json == render_summary_json(summary)
    assert first_markdown == render_summary_markdown(summary)
    assert "Fictional Secret Address" not in first_json + first_markdown
    assert "STAGE_9" in first_json
    with pytest.raises(ReviewSubsetError, match="UNSAFE_SUMMARY"):
        render_summary_json(
            _summary(metric_groups={"RAW_ADDRESS_VALUES": {"SECRET": 1}})
        )
    with pytest.raises(ReviewSubsetError, match="UNSAFE_SUMMARY"):
        render_summary_json(
            _summary(metric_groups={"ROW_INTEGRITY": {"RAW_STREET": 1}})
        )


def test_committed_stage02_summary_is_canonical_and_git_safe() -> None:
    repository = Path(__file__).resolve().parents[1]
    json_path = repository / "reports" / "development" / "stage02_summary.json"
    markdown_path = repository / "reports" / "development" / "stage02_summary.md"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    summary = validate_sanitized_summary_payload(payload)
    assert json_path.read_text(encoding="utf-8") == render_summary_json(summary)
    assert markdown_path.read_text(encoding="utf-8") == render_summary_markdown(summary)
    portable = json_path.read_text() + markdown_path.read_text()
    for forbidden in (
        "street_address_line_1",
        "source_file",
        "stable_source_row_id_v1",
        "Fictional Secret Address",
    ):
        assert forbidden not in portable


def test_committed_review_subset_summary_is_canonical_and_git_safe() -> None:
    repository = Path(__file__).resolve().parents[1]
    json_path = repository / "reports" / "development" / "review_subset_v1_summary.json"
    markdown_path = (
        repository / "reports" / "development" / "review_subset_v1_summary.md"
    )
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    summary = validate_sanitized_summary_payload(payload)
    assert json_path.read_text(encoding="utf-8") == render_summary_json(summary)
    assert markdown_path.read_text(encoding="utf-8") == render_summary_markdown(summary)
    portable = json_path.read_text() + markdown_path.read_text()
    for forbidden in (
        "street_address_line_1",
        "source_file",
        "stable_source_row_id_v1",
        "Fictional Secret Address",
    ):
        assert forbidden not in portable


def _source_row(index: int) -> dict[str, str]:
    row = {name: "" for name in SOURCE_COLUMNS}
    row.update(
        {
            "id": f"fictional-provider-{index}",
            "street_address_line_1": f" Fictional Secret Address {index} ",
            "street_address_line_1_native": f"架空住所{index}",
            "postcode": f"00{index:03d}",
            "city": "Fictional City",
            "region_in_country": "Fictional Region",
            "country_iso_code": ("DE", "JP", "BR")[index % 3],
            "batch_priority": str(index % 4),
            "location_information": (
                "no_geocoding_information",
                "previous_geocoding_failure",
                "postcode_interpolated",
                "region_interpolated",
            )[index % 4],
        }
    )
    return row


def _write_benchmark_development(path: Path, *, split: str = "DEVELOPMENT") -> None:
    rows: list[dict[str, object]] = []
    for index in range(6):
        source_hash = hashlib.sha256(f"source-{index}".encode()).digest()
        row: dict[str, object] = dict(_source_row(index))
        row.update(
            {
                "source_file": f"fictional-source-{index:04d}.csv",
                "source_logical_record_number": 1,
                "stable_source_row_id_v1": stable_source_row_id_v1(source_hash, 1),
                "source_file_sha256": source_hash,
                "benchmark_split": split,
                "benchmark_challenge_flag": True,
                "benchmark_challenge_reasons": (
                    "NO_GEOCODING_INFORMATION|MULTIPLE_ADDRESS_LINES"
                ),
                "location_information_stratum": (
                    "no_geocoding_information",
                    "previous_geocoding_failure",
                    "postcode_interpolated",
                    "region_interpolated",
                )[index % 4],
                "batch_priority_stratum": str(index % 4),
                "country_stratum": ("DE", "JP", "BR")[index % 3],
                "standard_native_presence_class": "BOTH_PRESENT",
                "standard_native_equality_class": "MATERIALLY_DIFFERENT",
                "standard_line_count": 1,
                "native_line_count": 1,
                "postcode_present": True,
                "city_present": True,
                "region_present": True,
                "country_present": True,
                "missingness_class": (
                    "POSTCODE_PRESENT_CITY_PRESENT_REGION_PRESENT_COUNTRY_PRESENT"
                ),
                "standard_script_class": "LATIN_ONLY",
                "native_script_class": "NON_LATIN_PRESENT",
                "combined_script_class": "MIXED_SCRIPT",
                "benchmark_feature_contract_version": FEATURE_CONTRACT_VERSION,
            }
        )
        rows.append(row)
    metadata = {
        b"benchmark_contract_version": BENCHMARK_CONTRACT_VERSION.encode(),
        b"benchmark_feature_contract_version": FEATURE_CONTRACT_VERSION.encode(),
        b"benchmark_schema_version": BENCHMARK_OUTPUT_SCHEMA_VERSION.encode(),
        b"benchmark_fingerprint": BENCHMARK_FINGERPRINT.encode(),
    }
    table = pa.Table.from_pylist(
        rows, schema=benchmark_schema().with_metadata(metadata)
    )
    pq.write_table(table, path, write_page_checksum=True, row_group_size=2)
    path.chmod(0o600)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stage02_bundle(tmp_path: Path, benchmark_path: Path) -> tuple[Path, str, str]:
    input_root = benchmark_path.parent
    input_root.chmod(0o700)
    binding = Stage02InputBinding(
        input_kind="BENCHMARK_DEVELOPMENT",
        upstream_contract_version=BENCHMARK_CONTRACT_VERSION,
        upstream_logical_identity_sha256=BENCHMARK_FINGERPRINT,
        source_population_identity_sha256=SOURCE_POPULATION_IDENTITY,
        input_schema_fingerprint=benchmark_schema_fingerprint(),
        expected_row_count=6,
        artifacts=(
            Stage02InputArtifact(
                sequence_number=1,
                relative_path=benchmark_path.name,
                size_bytes=benchmark_path.stat().st_size,
                sha256=_sha256(benchmark_path),
            ),
        ),
    )
    binding_path = tmp_path / "binding" / "stage02_input_binding.json"
    binding_sha = write_stage02_input_binding(binding_path, binding)
    stage02_root = tmp_path / "stage02" / "accepted"
    outcome = materialize_stage02(
        Stage02RunConfig(
            input_root=input_root,
            input_binding_file=binding_path,
            expected_input_binding_sha256=binding_sha,
            output_directory=stage02_root,
            adopting_git_commit=EXECUTION_GIT_SHA,
            production=False,
        )
    )
    return stage02_root, outcome.manifest_sha256, outcome.logical_dataset_sha256_v1


def test_protected_stage02_review_materialization_and_validation(
    tmp_path: Path,
) -> None:
    benchmark_root = tmp_path / "benchmark" / "development"
    benchmark_root.mkdir(parents=True, mode=0o700)
    benchmark_path = benchmark_root / "development_view.parquet"
    _write_benchmark_development(benchmark_path)
    stage02_root, stage02_manifest_sha, stage02_fingerprint = _stage02_bundle(
        tmp_path, benchmark_path
    )
    output = tmp_path / "reporting" / "review_v1"
    outcome = materialize_stage02_development_review(
        DevelopmentReviewRunConfig(
            benchmark_development_artifact=benchmark_path,
            expected_benchmark_artifact_sha256=_sha256(benchmark_path),
            benchmark_fingerprint=BENCHMARK_FINGERPRINT,
            stage02_output_directory=stage02_root,
            expected_stage02_manifest_sha256=stage02_manifest_sha,
            expected_stage02_logical_fingerprint=stage02_fingerprint,
            output_directory=output,
            execution_git_sha=EXECUTION_GIT_SHA,
            subset_config=ReviewSubsetConfig(
                target_count=3, expected_development_rows=6
            ),
            production=False,
        )
    )
    assert outcome.selected_row_count == 3
    assert outcome.duplicate_identity_count == 0
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    for relative in (
        REVIEW_IDENTITIES_PATH,
        STAGE02_REVIEW_PATH,
        REVIEW_SUMMARY_JSON_PATH,
        REVIEW_SUMMARY_MD_PATH,
        REVIEW_MANIFEST_NAME,
        "_SUCCESS.json",
    ):
        assert stat.S_IMODE((output / relative).stat().st_mode) == 0o600
    summary_payload = (output / REVIEW_SUMMARY_JSON_PATH).read_text()
    markdown_payload = (output / REVIEW_SUMMARY_MD_PATH).read_text()
    assert "Fictional Secret Address" not in summary_payload + markdown_payload
    review_table = pq.read_table(output / STAGE02_REVIEW_PATH)
    assert review_table.num_rows == 3
    assert all(
        "Fictional Secret Address" in value
        for value in review_table["street_address_line_1"].to_pylist()
    )
    validated = validate_development_review_bundle(
        output,
        expected_manifest_sha256=outcome.manifest_sha256,
        expected_benchmark_fingerprint=BENCHMARK_FINGERPRINT,
        expected_stage02_logical_fingerprint=stage02_fingerprint,
    )
    assert validated == outcome
    with pytest.raises(ReviewSubsetError, match="OUTPUT_COLLISION"):
        materialize_stage02_development_review(
            DevelopmentReviewRunConfig(
                benchmark_development_artifact=benchmark_path,
                expected_benchmark_artifact_sha256=_sha256(benchmark_path),
                benchmark_fingerprint=BENCHMARK_FINGERPRINT,
                stage02_output_directory=stage02_root,
                expected_stage02_manifest_sha256=stage02_manifest_sha,
                expected_stage02_logical_fingerprint=stage02_fingerprint,
                output_directory=output,
                execution_git_sha=EXECUTION_GIT_SHA,
                subset_config=ReviewSubsetConfig(
                    target_count=3, expected_development_rows=6
                ),
                production=False,
            )
        )
    success_path = output / REVIEW_SUCCESS_MARKER
    success = json.loads(success_path.read_text(encoding="utf-8"))
    success["unexpected"] = "not accepted"
    success_path.write_text(
        json.dumps(success, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    success_path.chmod(0o600)
    with pytest.raises(ReviewSubsetError, match="REVIEW_MANIFEST_INVALID"):
        validate_development_review_bundle(
            output,
            expected_manifest_sha256=outcome.manifest_sha256,
            expected_benchmark_fingerprint=BENCHMARK_FINGERPRINT,
            expected_stage02_logical_fingerprint=stage02_fingerprint,
        )


def test_materializer_rejects_holdout_and_mismatched_benchmark_identity(
    tmp_path: Path,
) -> None:
    benchmark_root = tmp_path / "benchmark" / "development"
    benchmark_root.mkdir(parents=True, mode=0o700)
    benchmark_path = benchmark_root / "development_view.parquet"
    _write_benchmark_development(benchmark_path, split="HOLDOUT")
    stage02_root = tmp_path / "stage02"
    stage02_root.mkdir(mode=0o700)
    base = DevelopmentReviewRunConfig(
        benchmark_development_artifact=benchmark_path,
        expected_benchmark_artifact_sha256=_sha256(benchmark_path),
        benchmark_fingerprint=BENCHMARK_FINGERPRINT,
        stage02_output_directory=stage02_root,
        expected_stage02_manifest_sha256="06" * 32,
        expected_stage02_logical_fingerprint="07" * 32,
        output_directory=tmp_path / "output",
        execution_git_sha=EXECUTION_GIT_SHA,
        subset_config=ReviewSubsetConfig(target_count=3, expected_development_rows=6),
        production=False,
    )
    with pytest.raises(ReviewSubsetError, match="HOLDOUT_ACCESS_PROHIBITED"):
        materialize_stage02_development_review(base)
    with pytest.raises(ReviewSubsetError, match="BENCHMARK_ARTIFACT_MISMATCH"):
        materialize_stage02_development_review(
            replace(base, expected_benchmark_artifact_sha256="ff" * 32)
        )
    with pytest.raises(ReviewSubsetError, match="HOLDOUT_ACCESS_PROHIBITED"):
        replace(
            base,
            output_directory=tmp_path / "holdout-review.parquet",
        ).validate()


def test_controlled_data_path_is_git_ignored_and_untracked() -> None:
    repository = Path(__file__).resolve().parents[1]
    protected = "data/controlled/development_review_subset_v1/stage02_review.parquet"
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "--", protected],
        cwd=repository,
        check=False,
    )
    assert ignored.returncode == 0
    tracked = subprocess.run(
        ["git", "ls-files", "--", "data/controlled"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    assert tracked.stdout == ""


def test_cluster_launcher_is_exact_commit_and_holdout_fail_closed() -> None:
    repository = Path(__file__).resolve().parents[1]
    launcher = (
        repository / "cluster" / "goethe_nhr" / "development_reporting.sbatch"
    ).read_text(encoding="utf-8")
    assert "DEVELOPMENT_REPORTING_GIT_COMMIT" in launcher
    assert "git symbolic-ref -q HEAD" in launcher
    assert "HOLDOUT_ACCESS_PROHIBITED" in launcher
    assert "SAFE_EXECUTION_SITE=goethe-nhr" in launcher
    assert "--benchmark-development-artifact" in launcher
    assert "--expected-stage02-manifest-sha256" in launcher


def test_partial_review_output_is_not_accepted(tmp_path: Path) -> None:
    output = tmp_path / "partial"
    output.mkdir(mode=0o700)
    marker = output / "_IN_PROGRESS"
    marker.write_text("incomplete", encoding="utf-8")
    marker.chmod(0o600)
    with pytest.raises(ReviewSubsetError, match="REVIEW_INCOMPLETE"):
        validate_development_review_bundle(
            output,
            expected_manifest_sha256="11" * 32,
            expected_benchmark_fingerprint=BENCHMARK_FINGERPRINT,
            expected_stage02_logical_fingerprint="22" * 32,
        )


def test_review_candidate_contract_has_no_raw_address_input() -> None:
    field_names = set(ReviewCandidate.__dataclass_fields__)
    assert not field_names.intersection(SOURCE_COLUMNS)
    assert "stable_source_row_id_v1" in field_names
