from __future__ import annotations

import hashlib
import json
import random
import stat
import subprocess
import unicodedata
from dataclasses import replace
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import pytest

import safe_geocoding_pipeline.preprocessing.stages.s04_lowercase as stage04_module
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
    DevelopmentReviewRunConfig,
    materialize_stage02_development_review,
)
from safe_geocoding_pipeline.preprocessing.reporting.stage04 import (
    STAGE04_REVIEW_PATH,
    STAGE04_SUMMARY_JSON_PATH,
    STAGE04_SUMMARY_MD_PATH,
    Stage04ReviewRunConfig,
    materialize_stage04_development_review,
    stage04_review_schema,
)
from safe_geocoding_pipeline.preprocessing.reporting.summary import (
    render_summary_json,
    render_summary_markdown,
    validate_sanitized_summary_payload,
)
from safe_geocoding_pipeline.preprocessing.stages.s02_harmonization import (
    STAGE02_CONTRACT_VERSION,
    Stage02InputArtifact,
    Stage02InputBinding,
    Stage02RunConfig,
    materialize_stage02,
    stage02_schema_fingerprint,
    write_stage02_input_binding,
)
from safe_geocoding_pipeline.preprocessing.stages.s03_cleaning import (
    CLEAN_DERIVED_COLUMNS,
    CLEAN_SOURCE_COLUMNS,
    STAGE03_CONTRACT_VERSION,
    STAGE03_PROFILE_VERSION,
    Stage03InputBinding,
    Stage03RunConfig,
    materialize_stage03,
    stage03_schema,
    stage03_schema_fingerprint,
    write_stage03_input_binding,
)
from safe_geocoding_pipeline.preprocessing.stages.s04_lowercase import (
    ACCEPTED_BENCHMARK_FINGERPRINT,
    ACCEPTED_DEVELOPMENT_ROWS,
    ACCEPTED_STAGE03_INPUT_BINDING_SHA256,
    ACCEPTED_STAGE03_LOGICAL_FINGERPRINT,
    ACCEPTED_STAGE03_MANIFEST_SHA256,
    ACCEPTED_STAGE03_ORDERED_IDENTITY_SHA256,
    ACCEPTED_STAGE03_SCHEMA_FINGERPRINT,
    LOWER_INPUT_COLUMNS,
    LOWER_OUTPUT_COLUMNS,
    STAGE04_AUDIT_COLUMNS,
    STAGE04_CONTRACT_VERSION,
    STAGE04_IN_PROGRESS_MARKER,
    STAGE04_PROFILE_VERSION,
    Stage04InputBinding,
    Stage04RunConfig,
    Stage04ValidationError,
    classify_script_value,
    lower_stage04_text,
    materialize_stage04,
    stage04_logical_dataset_sha256_v1,
    stage04_schema,
    stage04_schema_fingerprint,
    validate_stage04_bundle,
    validate_stage04_input_binding,
    validate_stage04_runtime,
    write_stage04_input_binding,
)
from safe_geocoding_pipeline.raw_csv import SOURCE_COLUMNS

BENCHMARK_FINGERPRINT = "33" * 32
SOURCE_POPULATION_IDENTITY = "44" * 32
EXECUTION_GIT_SHA = "a" * 40


@pytest.mark.parametrize(
    "value,expected",
    (
        ("MAIN STREET", "main street"),
        ("already lower", "already lower"),
        ("Main Street 10", "main street 10"),
        ("Apt. #10 / MAIN-ST", "apt. #10 / main-st"),
        ("123 / —", "123 / —"),
        ("", ""),
        ("  MAIN\tSTREET  ", "  main\tstreet  "),
        ("ÉCOLE", "école"),
        ("STRAẞE", "straße"),
        ("STRASSE", "strasse"),
        ("ß", "ß"),
        ("I", "i"),
        ("İ", "i\u0307"),
        ("ı", "ı"),
        ("i", "i"),
        ("ΟΣ", "ος"),
        ("Σ", "σ"),
        ("ΣΟΣ", "σος"),
        ("МОСКВА", "москва"),
        ("العربية", "العربية"),
        ("خیابان\u200cآزادی", "خیابان\u200cآزادی"),
        ("北京市", "北京市"),
        ("東京都", "東京都"),
        ("서울특별시", "서울특별시"),
        ("E\u0301COLE", "e\u0301cole"),
        ("🏢 MAIN 7️⃣", "🏢 main 7️⃣"),
    ),
)
def test_exact_python_unicode_lower_semantics(value: str, expected: str) -> None:
    observed = lower_stage04_text(value)
    assert observed == expected
    assert observed == value.lower()
    assert observed.lower() == observed


def test_no_normalization_after_lower_and_no_casefold() -> None:
    decomposed = "E\u0301COLE"
    observed = lower_stage04_text(decomposed)
    assert observed == "e\u0301cole"
    assert not unicodedata.is_normalized("NFC", observed)
    assert lower_stage04_text("Straße") == "straße"
    assert "Straße".casefold() == "strasse"
    assert lower_stage04_text("Straße") != "Straße".casefold()


def test_python_lower_can_expand_but_never_truncates() -> None:
    assert len(lower_stage04_text("İ")) == 2
    giant = "MAIN-İ-東京-🏢" * 250_000
    lowered = lower_stage04_text(giant)
    assert len(giant) > 2_000_000
    assert lowered == giant.lower()
    assert len(lowered) == len(giant) + 250_000


def test_scalar_lower_rejects_non_text_and_invalid_surrogate() -> None:
    with pytest.raises(Stage04ValidationError, match="INVALID_LOWERCASE_INPUT"):
        lower_stage04_text(None)  # type: ignore[arg-type]
    with pytest.raises(Stage04ValidationError, match="INVALID_LOWERCASE_INPUT"):
        lower_stage04_text("bad\ud800")


def test_arrow_unicode_lower_is_scientifically_forbidden() -> None:
    assert pc.utf8_lower("İ").as_py() == "i"
    assert lower_stage04_text("İ") == "i\u0307"
    assert pc.utf8_lower("ΟΣ").as_py() == "οσ"
    assert lower_stage04_text("ΟΣ") == "ος"


def test_optimized_array_path_matches_python_on_large_deterministic_corpus() -> None:
    values = [chr(codepoint) for codepoint in range(0x80)]
    for start, end in (
        (0x0080, 0x0250),
        (0x0370, 0x0530),
        (0x0530, 0x0590),
        (0x10A0, 0x1100),
        (0x1C80, 0x1CC0),
        (0x1E00, 0x2000),
        (0x2C60, 0x2D30),
        (0xA640, 0xA7FF),
    ):
        values.extend(chr(codepoint) for codepoint in range(start, end))
    rng = random.Random(20260827)
    for _ in range(25_000):
        characters: list[str] = []
        for _ in range(rng.randrange(0, 16)):
            while True:
                codepoint = rng.randrange(0x110000)
                if not 0xD800 <= codepoint <= 0xDFFF:
                    characters.append(chr(codepoint))
                    break
        values.append("".join(characters))
    values.extend(
        (
            "Iİıi",
            "ΟΣ ΣΟΣ ΟΣΑ",
            "E\u0301COLE",
            "العربية خیابان\u200cآزادی",
            "北京市 東京都 서울특별시",
            "🏢 123 —",
        )
    )
    observed = stage04_module._lower_array(pa.array(values, type=pa.string()))
    assert observed.to_pylist() == [value.lower() for value in values]


@pytest.mark.parametrize(
    "value,expected",
    (
        ("", "EMPTY"),
        ("MAIN 10", "ASCII_ONLY"),
        ("ÉCOLE", "LATIN_NON_ASCII"),
        ("МОСКВА", "CYRILLIC"),
        ("ΟΣ", "GREEK"),
        ("خیابان\u200cآزادی", "ARABIC_PERSIAN"),
        ("東京都 서울", "CJK_HANGUL"),
        ("Latin Москва", "MIXED"),
        ("कक्षा", "OTHER"),
    ),
)
def test_coarse_script_diagnostic(value: str, expected: str) -> None:
    assert classify_script_value(value) == expected


def test_runtime_schema_and_authoritative_constants_are_exact() -> None:
    validate_stage04_runtime()
    assert stage04_schema().names[: len(stage03_schema())] == stage03_schema().names
    assert tuple(stage04_schema().names[len(stage03_schema()) : -2]) == (
        LOWER_OUTPUT_COLUMNS
    )
    assert tuple(stage04_schema().names[-2:]) == STAGE04_AUDIT_COLUMNS
    assert len(LOWER_INPUT_COLUMNS) == len(LOWER_OUTPUT_COLUMNS) == 12
    assert LOWER_INPUT_COLUMNS == CLEAN_DERIVED_COLUMNS
    assert ACCEPTED_STAGE03_LOGICAL_FINGERPRINT == (
        "38df499bfaf61883832a9c718adf4cf92cfcea753337df68fa2e89afb6051bdb"
    )
    assert ACCEPTED_STAGE03_SCHEMA_FINGERPRINT == stage03_schema_fingerprint()
    assert ACCEPTED_STAGE03_INPUT_BINDING_SHA256 == (
        "6a2a28d276884511f5b8f63f40d14d6b7f4bf4397aa09289c53acdb92a661e6f"
    )
    assert ACCEPTED_STAGE03_MANIFEST_SHA256 == (
        "8f70745e31185abce52fdc1685c2b767f90874c21596152ea0463ec6677478d4"
    )
    assert ACCEPTED_STAGE03_ORDERED_IDENTITY_SHA256 == (
        "fe2a4758582c1880d2b5c62dfc5c587d865e05d13033af9f5e8208b58e2a0487"
    )
    assert ACCEPTED_BENCHMARK_FINGERPRINT == (
        "014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf"
    )
    assert ACCEPTED_DEVELOPMENT_ROWS == 35_000


def _source_row(index: int) -> dict[str, str]:
    cases = (
        "MAIN STREET",
        "ÉCOLE",
        "STRAẞE",
        "İSTANBUL",
        "ΟΣ",
        "МОСКВА",
        "العربية",
        "東京都",
        "서울특별시",
        "E\u0301COLE",
        "already lower",
        "🏢 123",
    )
    row = {name: "" for name in SOURCE_COLUMNS}
    row.update(
        {
            "id": f"fictional-provider-{index:05d}",
            "street_address_line_1": cases[index % len(cases)],
            "street_address_line_1_native": cases[(index + 5) % len(cases)],
            "postcode": f"AB{index:05d}",
            "city": ("Fictional City", "İSTANBUL", "МОСКВА")[index % 3],
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


def _write_benchmark_development(path: Path, *, row_count: int) -> None:
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
                "benchmark_split": "DEVELOPMENT",
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
    stage02_manifest: str,
    stage02_logical: str,
    *,
    row_count: int,
) -> tuple[Path, str, str, str, str]:
    binding = Stage03InputBinding(
        upstream_contract_version=STAGE02_CONTRACT_VERSION,
        upstream_logical_identity_sha256=stage02_logical,
        upstream_schema_fingerprint=stage02_schema_fingerprint(),
        upstream_manifest_sha256=stage02_manifest,
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
            output_directory=tmp_path / "stage03" / "accepted",
            execution_git_sha=EXECUTION_GIT_SHA,
            production=False,
            batch_rows=64,
        )
    )
    manifest = json.loads(
        (outcome.output_directory / "stage03_manifest.json").read_text(encoding="utf-8")
    )
    ordered = manifest["physical_identity"]["ordered_identity_validation"][
        "output_ordered_stable_identity_sha256_v1"
    ]
    return (
        outcome.output_directory,
        outcome.manifest_sha256,
        outcome.logical_dataset_sha256_v1,
        binding_sha,
        ordered,
    )


def _stage04_bundle(
    tmp_path: Path,
    stage03_root: Path,
    stage03_manifest: str,
    stage03_logical: str,
    stage03_binding: str,
    ordered_identity: str,
    *,
    row_count: int,
    batch_rows: int = 64,
    output_name: str = "candidate",
) -> tuple[Path, str, str, str]:
    binding = Stage04InputBinding(
        upstream_contract_version=STAGE03_CONTRACT_VERSION,
        upstream_profile_version=STAGE03_PROFILE_VERSION,
        upstream_logical_fingerprint=stage03_logical,
        upstream_schema_fingerprint=stage03_schema_fingerprint(),
        upstream_input_binding_sha256=stage03_binding,
        upstream_manifest_sha256=stage03_manifest,
        upstream_ordered_identity_sha256=ordered_identity,
        input_benchmark_fingerprint=BENCHMARK_FINGERPRINT,
        expected_row_count=row_count,
    )
    binding_path = tmp_path / f"stage04_binding_{output_name}" / "input.json"
    binding_sha = write_stage04_input_binding(binding_path, binding)
    outcome = materialize_stage04(
        Stage04RunConfig(
            stage03_output_directory=stage03_root,
            input_binding_file=binding_path,
            expected_input_binding_sha256=binding_sha,
            output_directory=tmp_path / "stage04" / output_name,
            execution_git_sha=EXECUTION_GIT_SHA,
            production=False,
            authoritative_development=False,
            batch_rows=batch_rows,
        )
    )
    return (
        outcome.output_directory,
        outcome.manifest_sha256,
        outcome.logical_dataset_sha256_v1,
        binding_sha,
    )


def _synthetic_upstream(
    tmp_path: Path, *, row_count: int
) -> tuple[Path, str, str, str, str, Path, Path, str]:
    benchmark_root = tmp_path / "benchmark" / "development"
    benchmark_root.mkdir(parents=True, mode=0o700)
    benchmark_path = benchmark_root / "development_view.parquet"
    _write_benchmark_development(benchmark_path, row_count=row_count)
    stage02_root, stage02_manifest, stage02_logical = _stage02_bundle(
        tmp_path, benchmark_path, row_count=row_count
    )
    stage03_root, stage03_manifest, stage03_logical, stage03_binding, ordered = (
        _stage03_bundle(
            tmp_path,
            stage02_root,
            stage02_manifest,
            stage02_logical,
            row_count=row_count,
        )
    )
    return (
        stage03_root,
        stage03_manifest,
        stage03_logical,
        stage03_binding,
        ordered,
        benchmark_path,
        stage02_root,
        stage02_logical,
    )


def test_materialization_exact_preservation_audit_metrics_and_permissions(
    tmp_path: Path,
) -> None:
    (
        stage03_root,
        stage03_manifest,
        stage03_logical,
        stage03_binding,
        ordered,
        _benchmark,
        _stage02,
        _stage02_logical,
    ) = _synthetic_upstream(tmp_path, row_count=12)
    stage03_before = pq.read_table(stage03_root / "data" / "part-000001.parquet")
    root, manifest_sha, logical, binding_sha = _stage04_bundle(
        tmp_path,
        stage03_root,
        stage03_manifest,
        stage03_logical,
        stage03_binding,
        ordered,
        row_count=12,
    )
    outcome = validate_stage04_bundle(
        root,
        expected_manifest_sha256=manifest_sha,
        authoritative_development=False,
        stage03_output_directory=stage03_root,
    )
    table = pq.read_table(root / "data" / "part-000001.parquet")
    assert table.num_rows == stage03_before.num_rows == 12
    for name in stage03_schema().names:
        assert table.column(name).equals(stage03_before.column(name))
    for source_name, input_name, output_name in zip(
        CLEAN_SOURCE_COLUMNS, LOWER_INPUT_COLUMNS, LOWER_OUTPUT_COLUMNS, strict=True
    ):
        before = table.column(input_name).to_pylist()
        after = table.column(output_name).to_pylist()
        assert after == [value.lower() for value in before]
        assert all(value.lower() == value for value in after)
        changed = table.column("stage04_changed_fields").to_pylist()
        assert all(
            (source_name in changed[index]) == (before[index] != after[index])
            for index in range(12)
        )
    assert outcome.row_count == 12
    assert outcome.logical_dataset_sha256_v1 == logical
    assert outcome.input_binding_sha256 == binding_sha
    assert outcome.ordered_identity_sha256 == ordered
    assert outcome.metrics["ROW_INTEGRITY"] == {
        "INPUT_ROWS": 12,
        "OUTPUT_ROWS": 12,
        "DROPPED_ROWS": 0,
        "ADDED_ROWS": 0,
        "DUPLICATE_IDENTITIES": 0,
    }
    assert outcome.metrics["OUTPUT_EFFECTS"]["NONEMPTY_TO_EMPTY_FIELDS"] == 0
    assert outcome.metrics["OUTPUT_EFFECTS"]["EMPTY_TO_NONEMPTY_FIELDS"] == 0
    assert outcome.metrics["OUTPUT_EFFECTS"]["IDEMPOTENCE_FAILURES"] == 0
    assert outcome.metrics["LOWERCASE_ENGINE"]["ARROW_UTF8_LOWER_VALUES"] == 0
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o600
        for path in root.rglob("*")
        if path.is_file()
    )


def test_batch_boundary_independence(tmp_path: Path) -> None:
    (
        stage03_root,
        stage03_manifest,
        stage03_logical,
        stage03_binding,
        ordered,
        *_rest,
    ) = _synthetic_upstream(tmp_path, row_count=12)
    first, first_manifest, first_logical, _ = _stage04_bundle(
        tmp_path,
        stage03_root,
        stage03_manifest,
        stage03_logical,
        stage03_binding,
        ordered,
        row_count=12,
        batch_rows=3,
        output_name="batch3",
    )
    second, second_manifest, second_logical, _ = _stage04_bundle(
        tmp_path,
        stage03_root,
        stage03_manifest,
        stage03_logical,
        stage03_binding,
        ordered,
        row_count=12,
        batch_rows=7,
        output_name="batch7",
    )
    assert first_logical == second_logical
    first_table = pq.read_table(first / "data" / "part-000001.parquet")
    second_table = pq.read_table(second / "data" / "part-000001.parquet")
    assert first_table.replace_schema_metadata().equals(
        second_table.replace_schema_metadata()
    )
    validate_stage04_bundle(
        first,
        expected_manifest_sha256=first_manifest,
        authoritative_development=False,
    )
    validate_stage04_bundle(
        second,
        expected_manifest_sha256=second_manifest,
        authoritative_development=False,
    )


def test_binding_fingerprint_mismatch_holdout_partial_and_guard_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binding = Stage04InputBinding(
        upstream_contract_version=STAGE03_CONTRACT_VERSION,
        upstream_profile_version=STAGE03_PROFILE_VERSION,
        upstream_logical_fingerprint="10" * 32,
        upstream_schema_fingerprint=stage03_schema_fingerprint(),
        upstream_input_binding_sha256="20" * 32,
        upstream_manifest_sha256="30" * 32,
        upstream_ordered_identity_sha256="40" * 32,
        input_benchmark_fingerprint="50" * 32,
        expected_row_count=35_000,
    )
    with pytest.raises(Stage04ValidationError, match="UPSTREAM_SCHEMA_MISMATCH"):
        validate_stage04_input_binding(
            replace(binding, upstream_schema_fingerprint="ff" * 32)
        )
    with pytest.raises(
        Stage04ValidationError, match="AUTHORITATIVE_DEVELOPMENT_BINDING_MISMATCH"
    ):
        validate_stage04_input_binding(binding, authoritative_development=True)
    with pytest.raises(Stage04ValidationError, match="HOLDOUT_ACCESS_PROHIBITED"):
        write_stage04_input_binding(tmp_path / "holdout" / "binding.json", binding)
    partial = tmp_path / "partial"
    partial.mkdir(mode=0o700)
    marker = partial / STAGE04_IN_PROGRESS_MARKER
    marker.write_text("incomplete", encoding="utf-8")
    marker.chmod(0o600)
    with pytest.raises(Stage04ValidationError, match="STAGE04_INCOMPLETE"):
        validate_stage04_bundle(
            partial,
            expected_manifest_sha256="11" * 32,
            authoritative_development=False,
        )
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    config = Stage04RunConfig(
        stage03_output_directory=tmp_path / "stage03",
        input_binding_file=tmp_path / "binding",
        expected_input_binding_sha256="11" * 32,
        output_directory=tmp_path / "output",
        execution_git_sha=EXECUTION_GIT_SHA,
        production=True,
    )
    with pytest.raises(ExecutionPolicyError, match="HEAVY_PROCESS_CLUSTER_REQUIRED"):
        materialize_stage04(config)


def test_wrong_stage03_manifest_and_binding_fail_before_output(tmp_path: Path) -> None:
    (
        stage03_root,
        stage03_manifest,
        stage03_logical,
        stage03_binding,
        ordered,
        *_rest,
    ) = _synthetic_upstream(tmp_path, row_count=2)
    binding = Stage04InputBinding(
        upstream_contract_version=STAGE03_CONTRACT_VERSION,
        upstream_profile_version=STAGE03_PROFILE_VERSION,
        upstream_logical_fingerprint=stage03_logical,
        upstream_schema_fingerprint=stage03_schema_fingerprint(),
        upstream_input_binding_sha256=stage03_binding,
        upstream_manifest_sha256="ff" * 32,
        upstream_ordered_identity_sha256=ordered,
        input_benchmark_fingerprint=BENCHMARK_FINGERPRINT,
        expected_row_count=2,
    )
    binding_path = tmp_path / "wrong" / "input.json"
    binding_sha = write_stage04_input_binding(binding_path, binding)
    with pytest.raises(Stage04ValidationError, match="STAGE03_BUNDLE_INVALID"):
        materialize_stage04(
            Stage04RunConfig(
                stage03_output_directory=stage03_root,
                input_binding_file=binding_path,
                expected_input_binding_sha256=binding_sha,
                output_directory=tmp_path / "wrong-output",
                execution_git_sha=EXECUTION_GIT_SHA,
                production=False,
                authoritative_development=False,
            )
        )
    assert stage03_manifest != "ff" * 32


def test_logical_fingerprint_ignores_physical_manifest_but_binds_science() -> None:
    base = Stage04InputBinding(
        upstream_contract_version=STAGE03_CONTRACT_VERSION,
        upstream_profile_version=STAGE03_PROFILE_VERSION,
        upstream_logical_fingerprint="10" * 32,
        upstream_schema_fingerprint=stage03_schema_fingerprint(),
        upstream_input_binding_sha256="20" * 32,
        upstream_manifest_sha256="30" * 32,
        upstream_ordered_identity_sha256="40" * 32,
        input_benchmark_fingerprint="50" * 32,
        expected_row_count=35_000,
    )
    observed = stage04_logical_dataset_sha256_v1(base)
    assert observed == stage04_logical_dataset_sha256_v1(
        replace(base, upstream_manifest_sha256="ff" * 32)
    )
    assert observed == stage04_logical_dataset_sha256_v1(
        replace(base, upstream_input_binding_sha256="ee" * 32)
    )
    assert observed != stage04_logical_dataset_sha256_v1(
        replace(base, upstream_ordered_identity_sha256="dd" * 32)
    )
    assert observed != stage04_logical_dataset_sha256_v1(
        replace(base, expected_row_count=35_001)
    )
    assert len(stage04_schema_fingerprint()) == 64


def test_fixed_500_review_and_sanitized_summary(tmp_path: Path) -> None:
    (
        stage03_root,
        stage03_manifest,
        stage03_logical,
        stage03_binding,
        ordered,
        benchmark_path,
        stage02_root,
        stage02_logical,
    ) = _synthetic_upstream(tmp_path, row_count=500)
    stage02_manifest = json.loads(
        (stage02_root / "_SUCCESS.json").read_text(encoding="utf-8")
    )["stage02_manifest_sha256"]
    accepted_review = tmp_path / "reporting" / "review_v1"
    fixed = materialize_stage02_development_review(
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
    stage04_root, stage04_manifest, _logical, _binding = _stage04_bundle(
        tmp_path,
        stage03_root,
        stage03_manifest,
        stage03_logical,
        stage03_binding,
        ordered,
        row_count=500,
    )
    output = tmp_path / "reporting" / "stage04"
    result = materialize_stage04_development_review(
        Stage04ReviewRunConfig(
            stage04_output_directory=stage04_root,
            expected_stage04_manifest_sha256=stage04_manifest,
            development_review_bundle_directory=accepted_review,
            expected_development_review_manifest_sha256=fixed.manifest_sha256,
            expected_review_subset_fingerprint=fixed.review_subset_fingerprint,
            expected_benchmark_fingerprint=BENCHMARK_FINGERPRINT,
            expected_stage02_logical_fingerprint=stage02_logical,
            output_directory=output,
            execution_git_sha=EXECUTION_GIT_SHA,
            performance_metrics={
                "ELAPSED_MILLISECONDS": 1_000,
                "USER_CPU_MILLISECONDS": 500,
                "SYSTEM_CPU_MILLISECONDS": 100,
                "MAX_RSS_KIB": 12_345,
            },
            production=False,
            authoritative_development=False,
            operational_metadata={"slurm_job_id": "12345"},
        )
    )
    fixed_ids = pq.read_table(
        accepted_review / REVIEW_IDENTITIES_PATH,
        columns=["stable_source_row_id_v1"],
    ).column(0)
    review = pq.read_table(output / STAGE04_REVIEW_PATH)
    assert result.selected_row_count == review.num_rows == 500
    assert review.column("stable_source_row_id_v1").equals(fixed_ids)
    assert review.schema.remove_metadata().equals(
        stage04_review_schema(), check_metadata=False
    )
    assert result.qualitative_classifications["QUESTIONABLE"] == 0
    assert result.qualitative_classifications["SEMANTIC_DAMAGE"] == 0
    summary_json = (output / STAGE04_SUMMARY_JSON_PATH).read_text(encoding="utf-8")
    summary_markdown = (output / STAGE04_SUMMARY_MD_PATH).read_text(encoding="utf-8")
    summary = validate_sanitized_summary_payload(json.loads(summary_json))
    assert summary_json == render_summary_json(summary)
    assert summary_markdown == render_summary_markdown(summary)
    assert summary.status == (
        "STAGE_4_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW"
    )
    assert summary.checks["EXACT_PYTHON_LOWER_SEMANTICS"] is True
    assert summary.checks["CASEFOLD_NOT_USED"] is True
    assert summary.metric_groups["PERFORMANCE"]["ROWS_PER_SECOND_MILLI"] == 500_000
    portable = summary_json + summary_markdown
    for forbidden in (
        "Fictional City",
        "fictional-source-",
        "stable_source_row_id_v1",
        "street_address_line_1",
        "МОСКВА",
    ):
        assert forbidden not in portable


def test_stage04_cluster_assets_and_scope_guards() -> None:
    repository = Path(__file__).resolve().parents[1]
    launcher = (
        repository / "cluster" / "goethe_nhr" / "stage04_lowercase_canonical.sbatch"
    ).read_text(encoding="utf-8")
    bootstrap = (
        repository / "cluster" / "goethe_nhr" / "stage04_bootstrap_env.sh"
    ).read_text(encoding="utf-8")
    for required in (
        "STAGE04_GIT_COMMIT",
        "git symbolic-ref -q HEAD",
        "SAFE_EXECUTION_SITE=goethe-nhr",
        "HOLDOUT_ACCESS_PROHIBITED",
        'DATA_ROOT="$(realpath -e',
        "stage04_lowercase_canonical_contract_v1",
        "stage04_lowercase_canonical_profile_v1",
        "materialize-review",
        "validate-published",
        ACCEPTED_STAGE03_LOGICAL_FINGERPRINT,
        ACCEPTED_STAGE03_MANIFEST_SHA256,
        ACCEPTED_STAGE03_ORDERED_IDENTITY_SHA256,
    ):
        assert required in launcher
    assert "Python 3.14.3" in bootstrap
    assert 'pyarrow.__version__ == "25.0.0"' in bootstrap
    assert "stage05" not in launcher.casefold()
    assert "production" not in launcher.casefold()
    protected = "data/controlled/development/stage04/stage04_review.parquet"
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


def test_stage04_source_does_not_call_casefold_or_arrow_utf8_lower() -> None:
    source = Path(stage04_module.__file__).read_text(encoding="utf-8")
    assert "value.casefold()" not in source
    assert "before.casefold()" not in source
    assert "pc.utf8_lower" not in source
    assert "unicodedata.normalize" not in source
    assert "seen_stable_ids" not in source
    assert "set[bytes]" not in source
    assert STAGE04_CONTRACT_VERSION == "stage04_lowercase_canonical_contract_v1"
    assert STAGE04_PROFILE_VERSION == "stage04_lowercase_canonical_profile_v1"
