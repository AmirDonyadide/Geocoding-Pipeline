from __future__ import annotations

import hashlib
import json
import random
import stat
import subprocess
import unicodedata
from dataclasses import replace
from pathlib import Path
import ftfy
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from safe_geocoding_pipeline.execution_policy import ExecutionPolicyError
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
from safe_geocoding_pipeline.preprocessing.reporting.contracts import ReviewSubsetConfig
from safe_geocoding_pipeline.preprocessing.reporting.development import (
    REVIEW_IDENTITIES_PATH,
    STAGE02_REVIEW_PATH,
    DevelopmentReviewRunConfig,
    materialize_stage02_development_review,
)
from safe_geocoding_pipeline.preprocessing.reporting.stage03 import (
    STAGE03_REVIEW_PATH,
    STAGE03_SUMMARY_JSON_PATH,
    STAGE03_SUMMARY_MD_PATH,
    Stage03ReviewRunConfig,
    materialize_stage03_development_review,
    stage03_review_schema,
)
from safe_geocoding_pipeline.preprocessing.reporting.summary import (
    render_summary_json,
    render_summary_markdown,
    validate_sanitized_summary_payload,
)
from safe_geocoding_pipeline.preprocessing.stages.s02_harmonization import (
    STAGE02_CONTRACT_VERSION,
    STAGE02_STRUCTURAL_COLUMNS,
    Stage02InputArtifact,
    Stage02InputBinding,
    Stage02RunConfig,
    materialize_stage02,
    stage02_schema,
    stage02_schema_fingerprint,
    write_stage02_input_binding,
)
from safe_geocoding_pipeline.preprocessing.stages.s03_cleaning import (
    CLEAN_DERIVED_COLUMNS,
    CLEAN_SOURCE_COLUMNS,
    EXPECTED_FTFY_VERSION,
    EXPECTED_PYARROW_VERSION,
    EXPECTED_PYTHON_VERSION,
    EXPECTED_UNICODE_VERSION,
    FTFY_CONFIG,
    REASON_CODES,
    STAGE03_AUDIT_COLUMNS,
    STAGE03_CONTRACT_VERSION,
    STAGE03_IN_PROGRESS_MARKER,
    STAGE03_PROFILE_VERSION,
    CleanTextResult,
    Stage03InputBinding,
    Stage03RunConfig,
    Stage03ValidationError,
    clean_stage03_text,
    materialize_stage03,
    stage03_logical_dataset_sha256_v1,
    stage03_schema,
    stage03_schema_fingerprint,
    validate_stage03_bundle,
    validate_stage03_input_binding,
    validate_stage03_runtime,
    write_stage03_input_binding,
)
from safe_geocoding_pipeline.raw_csv import SOURCE_COLUMNS

BENCHMARK_FINGERPRINT = "33" * 32
SOURCE_POPULATION_IDENTITY = "44" * 32
EXECUTION_GIT_SHA = "a" * 40


@pytest.mark.parametrize(
    "value",
    (
        "12 Rue de l'Église",
        "خیابان\u200cآزادی",
        "شارع الشيخ زايد",
        "Москва, корпус 2",
        "東京都千代田区1丁目",
        "O'Connell-Street 1/2",
        "São Tomé",
        "Latin Москва 東京",
        "Building 🏢 7️⃣",
        "क्\u200dष मार्ग",
        "A\u200eB\u2067C\u2069",
        "ﬁ Ａ ①",
        "P&Eacute;REZ",
        "l’humanité",
    ),
)
def test_no_change_multilingual_semantic_text_and_punctuation(value: str) -> None:
    assert clean_stage03_text(value) == CleanTextResult(value, ())


@pytest.mark.parametrize(
    "value,expected,expected_reasons",
    (
        ("  Alpha", "Alpha", ("WHITESPACE_COLLAPSED", "WHITESPACE_TRIMMED")),
        ("Alpha  ", "Alpha", ("WHITESPACE_COLLAPSED", "WHITESPACE_TRIMMED")),
        ("Alpha   Beta", "Alpha Beta", ("WHITESPACE_COLLAPSED",)),
        ("Alpha\tBeta", "Alpha Beta", ("TAB_NORMALIZED",)),
        ("Alpha\rBeta", "Alpha Beta", ("LINEBREAK_NORMALIZED",)),
        ("Alpha\nBeta", "Alpha Beta", ("LINEBREAK_NORMALIZED",)),
        (
            "Alpha\r\nBeta",
            "Alpha Beta",
            ("LINEBREAK_NORMALIZED", "WHITESPACE_COLLAPSED"),
        ),
        ("Alpha\u00a0Beta", "Alpha Beta", ("UNICODE_WHITESPACE_NORMALIZED",)),
        ("Alpha\u2003Beta", "Alpha Beta", ("UNICODE_WHITESPACE_NORMALIZED",)),
        ("Alpha\u202fBeta", "Alpha Beta", ("UNICODE_WHITESPACE_NORMALIZED",)),
        (
            "\t\u00a0\n",
            "",
            (
                "TAB_NORMALIZED",
                "LINEBREAK_NORMALIZED",
                "UNICODE_WHITESPACE_NORMALIZED",
                "WHITESPACE_COLLAPSED",
                "WHITESPACE_TRIMMED",
                "WHITESPACE_ONLY_TO_EMPTY",
            ),
        ),
    ),
)
def test_explicit_whitespace_policy(
    value: str, expected: str, expected_reasons: tuple[str, ...]
) -> None:
    assert clean_stage03_text(value) == CleanTextResult(expected, expected_reasons)


def test_unicode_nfc_and_meaningful_format_controls() -> None:
    decomposed = "Cafe\u0301"
    result = clean_stage03_text(decomposed)
    assert result == CleanTextResult("Café", ("UNICODE_NFC_NORMALIZED",))
    assert unicodedata.is_normalized("NFC", result.value)
    for preserved in (
        "A\u200bB",
        "A\u200cB",
        "A\u200dB",
        "A\u200eB",
        "A\u2067B\u2069",
        "A\ufe0fB",
        "نَ",
        "q\u0301",
        "A\ufeffB",
    ):
        assert clean_stage03_text(preserved) == CleanTextResult(preserved, ())


def test_bom_controls_and_terminal_escape_handling() -> None:
    assert clean_stage03_text("\ufeffAlpha\ufeff") == CleanTextResult(
        "Alpha", ("BOM_REMOVED",)
    )
    assert clean_stage03_text("A\x00\x07B") == CleanTextResult(
        "AB", ("CONTROL_CHARACTER_REMOVED",)
    )
    assert clean_stage03_text("A\x1cB\x7fC") == CleanTextResult(
        "ABC", ("CONTROL_CHARACTER_REMOVED",)
    )
    assert clean_stage03_text("\x1b[31mAlpha\x1b[0m") == CleanTextResult(
        "Alpha", ("TERMINAL_ESCAPE_REMOVED",)
    )


def test_conservative_ftfy_encoding_repair_only() -> None:
    repaired = clean_stage03_text("FranÃ§ois")
    assert repaired == CleanTextResult("François", ("ENCODING_REPAIRED",))
    repaired_twice = clean_stage03_text("The Mona Lisa doesnÃ¢â‚¬â„¢t")
    assert repaired_twice.reason_codes == ("ENCODING_REPAIRED",)
    assert "Ã" not in repaired_twice.value
    for untouched in (
        "P&EACUTE;REZ",
        "ﬁ ligature",
        "ＬＯＵＤ　ＮＯＩＳＥＳ",
        "curly ‘quotes’",
        "IL Y MARQUÉ…",
    ):
        result = clean_stage03_text(untouched)
        if untouched == "ＬＯＵＤ　ＮＯＩＳＥＳ":
            assert result.value == "ＬＯＵＤ ＮＯＩＳＥＳ"
            assert result.reason_codes == ("UNICODE_WHITESPACE_NORMALIZED",)
        else:
            assert result == CleanTextResult(untouched, ())
    assert FTFY_CONFIG.unescape_html is False
    assert FTFY_CONFIG.decode_inconsistent_utf8 is False
    assert FTFY_CONFIG.fix_character_width is False
    assert FTFY_CONFIG.uncurl_quotes is False
    assert FTFY_CONFIG.normalization is None


def test_deterministic_property_style_idempotence_over_adversarial_unicode() -> None:
    rng = random.Random(20260826)
    alphabet = (
        "abcXYZ  \t\r\n\u00a0\u2003\ufeff\x00"
        "é\u0301Москва東京العربيةخیابان\u200c\u200d🛰️'/-.,"
    )
    examples = ["", *alphabet]
    examples.extend(
        "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 80)))
        for _ in range(1_000)
    )
    for value in examples:
        first = clean_stage03_text(value)
        second = clean_stage03_text(first.value)
        assert second == CleanTextResult(first.value, ())


def test_cleaner_rejects_non_text_and_invalid_surrogate() -> None:
    with pytest.raises(Stage03ValidationError, match="INVALID_CLEANING_INPUT"):
        clean_stage03_text(None)  # type: ignore[arg-type]
    with pytest.raises(Stage03ValidationError, match="INVALID_CLEANING_INPUT"):
        clean_stage03_text("bad\ud800")


def test_runtime_and_schema_contract_are_exact() -> None:
    validate_stage03_runtime()
    assert EXPECTED_PYTHON_VERSION == (3, 14, 3)
    assert EXPECTED_UNICODE_VERSION == unicodedata.unidata_version
    assert EXPECTED_FTFY_VERSION == ftfy.__version__
    assert EXPECTED_PYARROW_VERSION == pa.__version__
    schema = stage03_schema()
    assert schema.names[: len(stage02_schema())] == stage02_schema().names
    assert tuple(schema.names[len(stage02_schema()) : -2]) == CLEAN_DERIVED_COLUMNS
    assert tuple(schema.names[-2:]) == STAGE03_AUDIT_COLUMNS
    assert schema.field("stage03_change_details").nullable is False
    assert schema.field("stage03_row_changed").nullable is False
    assert len(CLEAN_SOURCE_COLUMNS) == 12
    assert len(set(REASON_CODES)) == len(REASON_CODES)


def _source_row(index: int) -> dict[str, str]:
    row = {name: "" for name in SOURCE_COLUMNS}
    row.update(
        {
            "id": f"fictional-provider-{index:05d}",
            "street_address_line_1": f"Fictional Address {index}",
            "street_address_line_1_native": f"架空住所{index}",
            "postcode": f"00{index:05d}",
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
    if index == 1:
        row["street_address_line_1"] = "  Fictional\tAddress  1  "
    elif index == 2:
        row["city"] = "DÃ¼sseldorf"
    elif index == 3:
        row["street_address_line_1_native"] = "خیابان\u200cآزادی"
    elif index == 4:
        row["region_in_country"] = "Fictional\x00Region"
    elif index == 5:
        row["postcode"] = "\u00a0"
    return row


def _write_benchmark_development(
    path: Path, *, row_count: int, split: str = "DEVELOPMENT"
) -> None:
    rows: list[dict[str, object]] = []
    for index in range(row_count):
        source_hash = hashlib.sha256(f"fictional-source-{index:05d}".encode()).digest()
        row: dict[str, object] = dict(_source_row(index))
        row.update(
            {
                "source_file": f"fictional-source-{index:05d}.csv",
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
                "country_stratum": f"C{index % 47:02d}",
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
    pq.write_table(
        table,
        path,
        compression="zstd",
        write_page_checksum=True,
        row_group_size=min(100, row_count),
    )
    path.chmod(0o600)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stage02_bundle(
    tmp_path: Path, benchmark_path: Path, *, row_count: int
) -> tuple[Path, str, str]:
    input_root = benchmark_path.parent
    input_root.chmod(0o700)
    binding = Stage02InputBinding(
        input_kind="BENCHMARK_DEVELOPMENT",
        upstream_contract_version=BENCHMARK_CONTRACT_VERSION,
        upstream_logical_identity_sha256=BENCHMARK_FINGERPRINT,
        source_population_identity_sha256=SOURCE_POPULATION_IDENTITY,
        input_schema_fingerprint=benchmark_schema_fingerprint(),
        expected_row_count=row_count,
        artifacts=(
            Stage02InputArtifact(
                sequence_number=1,
                relative_path=benchmark_path.name,
                size_bytes=benchmark_path.stat().st_size,
                sha256=_sha256(benchmark_path),
            ),
        ),
    )
    binding_path = tmp_path / "stage02_binding" / "input.json"
    binding_sha = write_stage02_input_binding(binding_path, binding)
    outcome = materialize_stage02(
        Stage02RunConfig(
            input_root=input_root,
            input_binding_file=binding_path,
            expected_input_binding_sha256=binding_sha,
            output_directory=tmp_path / "stage02" / "accepted",
            adopting_git_commit=EXECUTION_GIT_SHA,
            production=False,
            batch_rows=64,
        )
    )
    return (
        outcome.output_directory,
        outcome.manifest_sha256,
        outcome.logical_dataset_sha256_v1,
    )


def _stage03_bundle(
    tmp_path: Path,
    stage02_root: Path,
    stage02_manifest_sha: str,
    stage02_logical: str,
    *,
    row_count: int,
) -> tuple[Path, str, str, str]:
    binding = Stage03InputBinding(
        upstream_contract_version=STAGE02_CONTRACT_VERSION,
        upstream_logical_identity_sha256=stage02_logical,
        upstream_schema_fingerprint=stage02_schema_fingerprint(),
        upstream_manifest_sha256=stage02_manifest_sha,
        input_benchmark_fingerprint=BENCHMARK_FINGERPRINT,
        expected_row_count=row_count,
    )
    binding_path = tmp_path / "stage03_binding" / "input.json"
    binding_sha = write_stage03_input_binding(binding_path, binding)
    outcome = materialize_stage03(
        Stage03RunConfig(
            stage02_output_directory=stage02_root,
            input_binding_file=binding_path,
            expected_input_binding_sha256=binding_sha,
            output_directory=tmp_path / "stage03" / "candidate",
            execution_git_sha=EXECUTION_GIT_SHA,
            production=False,
            batch_rows=64,
        )
    )
    return (
        outcome.output_directory,
        outcome.manifest_sha256,
        outcome.logical_dataset_sha256_v1,
        binding_sha,
    )


def _read_single_shard(root: Path) -> pa.Table:
    return pq.read_table(root / "data" / "part-000001.parquet")


def test_materialization_preserves_raw_stage02_and_audits_every_change(
    tmp_path: Path,
) -> None:
    benchmark_root = tmp_path / "benchmark" / "development"
    benchmark_root.mkdir(parents=True, mode=0o700)
    benchmark_path = benchmark_root / "development_view.parquet"
    _write_benchmark_development(benchmark_path, row_count=8)
    stage02_root, stage02_manifest, stage02_logical = _stage02_bundle(
        tmp_path, benchmark_path, row_count=8
    )
    stage02_before = _read_single_shard(stage02_root)
    stage03_root, stage03_manifest, stage03_logical, binding_sha = _stage03_bundle(
        tmp_path,
        stage02_root,
        stage02_manifest,
        stage02_logical,
        row_count=8,
    )
    outcome = validate_stage03_bundle(
        stage03_root, expected_manifest_sha256=stage03_manifest
    )
    stage03_table = _read_single_shard(stage03_root)
    assert stage03_table.num_rows == stage02_before.num_rows == 8
    for name in stage02_schema().names:
        assert stage03_table.column(name).equals(stage02_before.column(name))
    assert stage03_table["stage03_clean_street_address_line_1"].to_pylist()[1] == (
        "Fictional Address 1"
    )
    assert stage03_table["stage03_clean_city"].to_pylist()[2] == "Düsseldorf"
    assert (
        stage03_table["stage03_clean_street_address_line_1_native"].to_pylist()[3]
        == "خیابان\u200cآزادی"
    )
    assert stage03_table["stage03_clean_region_in_country"].to_pylist()[4] == (
        "FictionalRegion"
    )
    assert stage03_table["stage03_clean_postcode"].to_pylist()[5] == ""
    details = stage03_table["stage03_change_details"].to_pylist()
    assert details[0] == []
    assert [item["field_name"] for item in details[1]] == ["street_address_line_1"]
    assert stage03_table["stage03_row_changed"].to_pylist() == [
        False,
        True,
        True,
        False,
        True,
        True,
        False,
        False,
    ]
    assert outcome.row_count == 8
    assert outcome.input_binding_sha256 == binding_sha
    assert outcome.logical_dataset_sha256_v1 == stage03_logical
    assert outcome.metrics["ROW_INTEGRITY"] == {
        "INPUT_ROWS": 8,
        "OUTPUT_ROWS": 8,
        "DROPPED_ROWS": 0,
        "ADDED_ROWS": 0,
        "DUPLICATE_IDENTITIES": 0,
    }
    assert outcome.metrics["OUTPUT_EFFECTS"]["IDEMPOTENCE_FAILURES"] == 0
    assert outcome.metrics["PUNCTUATION"]["PUNCTUATION_CHANGED_FIELDS"] == 0
    assert stat.S_IMODE(stage03_root.stat().st_mode) == 0o700
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o600
        for path in stage03_root.rglob("*")
        if path.is_file()
    )


def test_logical_fingerprint_is_layout_independent_and_science_sensitive() -> None:
    base = Stage03InputBinding(
        upstream_contract_version=STAGE02_CONTRACT_VERSION,
        upstream_logical_identity_sha256="10" * 32,
        upstream_schema_fingerprint=stage02_schema_fingerprint(),
        upstream_manifest_sha256="20" * 32,
        input_benchmark_fingerprint="30" * 32,
        expected_row_count=35_000,
    )
    observed = stage03_logical_dataset_sha256_v1(base)
    assert observed == stage03_logical_dataset_sha256_v1(
        replace(base, upstream_manifest_sha256="ff" * 32)
    )
    assert observed != stage03_logical_dataset_sha256_v1(
        replace(base, expected_row_count=35_001)
    )
    assert observed != stage03_logical_dataset_sha256_v1(
        replace(base, input_benchmark_fingerprint="ee" * 32)
    )
    assert len(stage03_schema_fingerprint()) == 64


def test_binding_schema_fingerprint_holdout_and_partial_fail_closed(
    tmp_path: Path,
) -> None:
    binding = Stage03InputBinding(
        upstream_contract_version=STAGE02_CONTRACT_VERSION,
        upstream_logical_identity_sha256="10" * 32,
        upstream_schema_fingerprint=stage02_schema_fingerprint(),
        upstream_manifest_sha256="20" * 32,
        input_benchmark_fingerprint="30" * 32,
        expected_row_count=35_000,
    )
    with pytest.raises(Stage03ValidationError, match="UPSTREAM_SCHEMA_MISMATCH"):
        validate_stage03_input_binding(
            replace(binding, upstream_schema_fingerprint="ff" * 32)
        )
    bad_path = tmp_path / "holdout" / "binding.json"
    with pytest.raises(Stage03ValidationError, match="HOLDOUT_ACCESS_PROHIBITED"):
        write_stage03_input_binding(bad_path, binding)
    malformed_root = tmp_path / "malformed"
    malformed_root.mkdir(mode=0o700)
    malformed = malformed_root / "binding.json"
    malformed.write_text('{"stage03_input_binding_version":"wrong"}\n')
    malformed.chmod(0o600)
    with pytest.raises(Stage03ValidationError, match="INPUT_BINDING_INVALID"):
        from safe_geocoding_pipeline.preprocessing.stages.s03_cleaning import (
            load_stage03_input_binding,
        )

        load_stage03_input_binding(malformed, expected_sha256=_sha256(malformed))
    partial = tmp_path / "partial"
    partial.mkdir(mode=0o700)
    marker = partial / STAGE03_IN_PROGRESS_MARKER
    marker.write_text("incomplete", encoding="utf-8")
    marker.chmod(0o600)
    with pytest.raises(Stage03ValidationError, match="STAGE03_INCOMPLETE"):
        validate_stage03_bundle(partial, expected_manifest_sha256="11" * 32)


def test_wrong_stage02_fingerprint_and_production_guard_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    benchmark_root = tmp_path / "benchmark" / "development"
    benchmark_root.mkdir(parents=True, mode=0o700)
    benchmark_path = benchmark_root / "development_view.parquet"
    _write_benchmark_development(benchmark_path, row_count=2)
    stage02_root, stage02_manifest, stage02_logical = _stage02_bundle(
        tmp_path, benchmark_path, row_count=2
    )
    binding = Stage03InputBinding(
        upstream_contract_version=STAGE02_CONTRACT_VERSION,
        upstream_logical_identity_sha256="ff" * 32,
        upstream_schema_fingerprint=stage02_schema_fingerprint(),
        upstream_manifest_sha256=stage02_manifest,
        input_benchmark_fingerprint=BENCHMARK_FINGERPRINT,
        expected_row_count=2,
    )
    binding_path = tmp_path / "wrong_binding" / "input.json"
    binding_sha = write_stage03_input_binding(binding_path, binding)
    config = Stage03RunConfig(
        stage02_output_directory=stage02_root,
        input_binding_file=binding_path,
        expected_input_binding_sha256=binding_sha,
        output_directory=tmp_path / "wrong_output",
        execution_git_sha=EXECUTION_GIT_SHA,
        production=False,
    )
    with pytest.raises(Stage03ValidationError, match="STAGE02_IDENTITY_MISMATCH"):
        materialize_stage03(config)
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    with pytest.raises(ExecutionPolicyError, match="HEAVY_PROCESS_CLUSTER_REQUIRED"):
        materialize_stage03(
            replace(config, production=True, output_directory=tmp_path / "guarded")
        )
    assert stage02_logical != "ff" * 32


def test_fixed_500_review_artifact_and_sanitized_summary(
    tmp_path: Path,
) -> None:
    benchmark_root = tmp_path / "benchmark" / "development"
    benchmark_root.mkdir(parents=True, mode=0o700)
    benchmark_path = benchmark_root / "development_view.parquet"
    _write_benchmark_development(benchmark_path, row_count=500)
    stage02_root, stage02_manifest, stage02_logical = _stage02_bundle(
        tmp_path, benchmark_path, row_count=500
    )
    accepted_review = tmp_path / "reporting" / "review_v1"
    review_outcome = materialize_stage02_development_review(
        DevelopmentReviewRunConfig(
            benchmark_development_artifact=benchmark_path,
            expected_benchmark_artifact_sha256=_sha256(benchmark_path),
            benchmark_fingerprint=BENCHMARK_FINGERPRINT,
            stage02_output_directory=stage02_root,
            expected_stage02_manifest_sha256=stage02_manifest,
            expected_stage02_logical_fingerprint=stage02_logical,
            output_directory=accepted_review,
            execution_git_sha=EXECUTION_GIT_SHA,
            subset_config=ReviewSubsetConfig(
                target_count=500, expected_development_rows=500
            ),
            production=False,
        )
    )
    stage02_review_sha_before = _sha256(accepted_review / STAGE02_REVIEW_PATH)
    stage03_root, stage03_manifest, _logical, _binding_sha = _stage03_bundle(
        tmp_path,
        stage02_root,
        stage02_manifest,
        stage02_logical,
        row_count=500,
    )
    output = tmp_path / "reporting" / "stage03"
    outcome = materialize_stage03_development_review(
        Stage03ReviewRunConfig(
            stage03_output_directory=stage03_root,
            expected_stage03_manifest_sha256=stage03_manifest,
            development_review_bundle_directory=accepted_review,
            expected_development_review_manifest_sha256=(
                review_outcome.manifest_sha256
            ),
            expected_review_subset_fingerprint=(
                review_outcome.review_subset_fingerprint
            ),
            expected_benchmark_fingerprint=BENCHMARK_FINGERPRINT,
            expected_stage02_logical_fingerprint=stage02_logical,
            output_directory=output,
            execution_git_sha=EXECUTION_GIT_SHA,
            production=False,
            operational_metadata={"slurm_job_id": "12345"},
        )
    )
    assert outcome.selected_row_count == 500
    assert _sha256(accepted_review / STAGE02_REVIEW_PATH) == stage02_review_sha_before
    fixed_ids = pq.read_table(
        accepted_review / REVIEW_IDENTITIES_PATH,
        columns=["stable_source_row_id_v1"],
    ).column(0)
    review_table = pq.read_table(output / STAGE03_REVIEW_PATH)
    assert review_table.num_rows == 500
    assert review_table.column("stable_source_row_id_v1").equals(fixed_ids)
    assert review_table.schema.remove_metadata().equals(
        stage03_review_schema(), check_metadata=False
    )
    summary_json = (output / STAGE03_SUMMARY_JSON_PATH).read_text(encoding="utf-8")
    summary_markdown = (output / STAGE03_SUMMARY_MD_PATH).read_text(encoding="utf-8")
    summary = validate_sanitized_summary_payload(json.loads(summary_json))
    assert summary_json == render_summary_json(summary)
    assert summary_markdown == render_summary_markdown(summary)
    portable = summary_json + summary_markdown
    for forbidden in (
        "Fictional Address",
        "fictional-source-",
        "stable_source_row_id_v1",
        "street_address_line_1",
        "架空住所",
    ):
        assert forbidden not in portable
    assert summary.status == (
        "STAGE_3_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW"
    )
    assert summary.extra_fingerprints["review_artifact"] == (
        outcome.review_artifact_sha256
    )
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o600
        for path in output.iterdir()
        if path.is_file()
    )


def test_stage03_cluster_launcher_and_git_ignore_guards() -> None:
    repository = Path(__file__).resolve().parents[1]
    launcher = (
        repository / "cluster" / "goethe_nhr" / "stage03_safe_text_cleaning.sbatch"
    ).read_text(encoding="utf-8")
    assert "STAGE03_GIT_COMMIT" in launcher
    assert "git symbolic-ref -q HEAD" in launcher
    assert "SAFE_EXECUTION_SITE=goethe-nhr" in launcher
    assert "HOLDOUT_ACCESS_PROHIBITED" in launcher
    assert "stage03_safe_text_cleaning_contract_v1" in launcher
    assert "stage03_safe_text_cleaning_profile_v1" in launcher
    assert "materialize-review" in launcher
    protected = (
        "data/controlled/development_review_subset_v1/stages/stage03/"
        "stage03_review.parquet"
    )
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


def test_stage03_contract_versions_are_distinct_and_no_stage4_surface() -> None:
    assert STAGE03_CONTRACT_VERSION == "stage03_safe_text_cleaning_contract_v1"
    assert STAGE03_PROFILE_VERSION == "stage03_safe_text_cleaning_profile_v1"
    assert all("lower" not in name.casefold() for name in stage03_schema().names)
    assert all("canonical" not in name.casefold() for name in CLEAN_DERIVED_COLUMNS)
    assert all(name in SOURCE_COLUMNS for name in CLEAN_SOURCE_COLUMNS)
    assert not set(CLEAN_SOURCE_COLUMNS).intersection(
        {"id", "batch_priority", "location_information"}
    )
    stage02_field_count = len(stage02_schema())
    assert (
        tuple(stage03_schema().names[stage02_field_count - 4 : stage02_field_count])
        == STAGE02_STRUCTURAL_COLUMNS
    )
