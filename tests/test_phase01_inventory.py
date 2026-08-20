from __future__ import annotations

import csv
import gzip
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from safe_geocoding_pipeline.phase01.config import InventoryConfig
from safe_geocoding_pipeline.phase01.constants import EXPECTED_COLUMNS, REPORT_NAMES
from safe_geocoding_pipeline.phase01.profiling import sha256_text
from safe_geocoding_pipeline.phase01.runner import run_inventory


def _copy(fixtures_dir: Path, source_dir: Path, *names: str) -> None:
    for name in names:
        shutil.copyfile(fixtures_dir / name, source_dir / name)


def _config(
    source_dir: Path,
    tmp_path: Path,
    *,
    run_id_suffix: str,
    **overrides: object,
) -> InventoryConfig:
    values: dict[str, object] = {
        "source_root": source_dir,
        "reports_root": tmp_path / "reports",
        "run_scope": "TEST",
        "run_id": f"phase01_20260101T000000Z_{run_id_suffix}",
        "insertion_batch_size": 2,
    }
    values.update(overrides)
    return InventoryConfig(**values)  # type: ignore[arg-type]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _read_gzip_csv(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _write_csv(
    path: Path, rows: list[list[str]], *, header: tuple[str, ...] = EXPECTED_COLUMNS
) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter=",", quotechar='"', doublequote=True)
        writer.writerow(header)
        writer.writerows(rows)


def _row(**values: str) -> list[str]:
    return [values.get(column, "") for column in EXPECTED_COLUMNS]


def test_ordinary_csv_preserves_csv_semantics_unicode_and_postcodes(
    fixtures_dir: Path, source_dir: Path, tmp_path: Path
) -> None:
    _copy(fixtures_dir, source_dir, "synthetic_ordinary.csv")
    outcome = run_inventory(_config(source_dir, tmp_path, run_id_suffix="ordinary"))

    assert outcome.scope_gate == "PASS"
    assert outcome.phase01_completion_gate == "NOT_EVALUATED"
    result = outcome.file_results[0]
    assert result.logical_record_count == 3
    assert result.schema_matches_expected is True
    assert result.parser_error_count == 0
    assert result.wrong_column_count_record_count == 0
    assert result.id_distinct_within_file == 3

    values = _read_csv(outcome.run_dir / "phase01_value_profile.csv")
    postcode_categories = {
        row["category"]
        for row in values
        if row["profile_family"] == "POSTCODE_LEXICAL_PATTERN"
    }
    assert "DIGITS_LEADING_ZERO" in postcode_categories
    assert "CONTAINS_WHITESPACE" in postcode_categories
    assert any(
        row["profile_family"] == "NATIVE_SCRIPT_DIAGNOSTIC"
        and row["category"] == "CONTAINS_NON_ASCII"
        for row in values
    )

    for name in REPORT_NAMES:
        assert (outcome.run_dir / name).is_file()
        assert (outcome.run_dir / name).stat().st_mode & 0o777 == 0o600
    assert outcome.run_dir.stat().st_mode & 0o777 == 0o700
    assert (outcome.run_dir / "_work").stat().st_mode & 0o777 == 0o700
    assert (outcome.run_dir / "_work/phase01.sqlite3").stat().st_mode & 0o777 == 0o600
    run_payload = json.loads(
        (outcome.run_dir / "phase01_run.json").read_text(encoding="utf-8")
    )
    assert len(run_payload["git_commit"]) == 40
    assert not (outcome.run_dir / "_IN_PROGRESS").exists()
    assert (outcome.run_dir / "_SCOPE_PASS").exists()
    assert (outcome.run_dir / "_SCOPE_PASS").stat().st_mode & 0o777 == 0o600


def test_multiline_record_tracks_logical_and_physical_lines(
    fixtures_dir: Path, source_dir: Path, tmp_path: Path
) -> None:
    _copy(fixtures_dir, source_dir, "synthetic_multiline.csv")
    outcome = run_inventory(_config(source_dir, tmp_path, run_id_suffix="multiline"))
    result = outcome.file_results[0]
    assert result.logical_record_count == 1
    assert result.multiline_record_count == 1
    assert result.max_physical_lines_per_record == 2
    anomalies = _read_gzip_csv(outcome.run_dir / "phase01_anomalies.csv.gz")
    multiline = [
        row for row in anomalies if row["anomaly_type"] == "QUOTED_MULTILINE_RECORD"
    ]
    assert len(multiline) == 1
    assert (
        int(multiline[0]["physical_line_end"])
        - int(multiline[0]["physical_line_start"])
        + 1
        == 2
    )


@pytest.mark.parametrize(
    "fixture_name",
    [
        "synthetic_schema_reordered.csv",
        "synthetic_schema_renamed.csv",
        "synthetic_schema_missing.csv",
        "synthetic_schema_extra.csv",
    ],
)
def test_schema_deviations_fail_without_alternate_contract(
    fixture_name: str, fixtures_dir: Path, source_dir: Path, tmp_path: Path
) -> None:
    _copy(fixtures_dir, source_dir, fixture_name)
    outcome = run_inventory(
        _config(source_dir, tmp_path, run_id_suffix=fixture_name.removesuffix(".csv"))
    )
    result = outcome.file_results[0]
    assert outcome.scope_gate == "FAIL"
    assert result.scan_status == "FAILED"
    assert result.schema_matches_expected is False
    assert result.error_code == "SCHEMA_DEVIATION"
    assert all(profile.profile_complete is False for profile in result.field_profiles)


def test_wrong_column_records_are_counted_and_fail_the_scope(
    fixtures_dir: Path, source_dir: Path, tmp_path: Path
) -> None:
    _copy(fixtures_dir, source_dir, "synthetic_wrong_columns.csv")
    outcome = run_inventory(_config(source_dir, tmp_path, run_id_suffix="wrongcols"))
    result = outcome.file_results[0]
    assert result.logical_record_count == 2
    assert result.wrong_column_count_record_count == 2
    assert result.scan_status == "FAILED"
    assert outcome.scope_gate == "FAIL"
    anomalies = _read_gzip_csv(outcome.run_dir / "phase01_anomalies.csv.gz")
    assert sum(row["anomaly_type"] == "WRONG_COLUMN_COUNT" for row in anomalies) == 2


def test_malformed_quote_stops_file_without_resynchronization(
    fixtures_dir: Path, source_dir: Path, tmp_path: Path
) -> None:
    _copy(fixtures_dir, source_dir, "synthetic_malformed_quote.csv")
    outcome = run_inventory(_config(source_dir, tmp_path, run_id_suffix="badquote"))
    result = outcome.file_results[0]
    assert result.parser_error_count == 1
    assert result.counts_complete is False
    assert result.error_code == "MALFORMED_CSV"
    assert result.scan_status == "FAILED"
    assert outcome.scope_gate == "FAIL"


def test_utf8_bom_is_handled_and_invalid_utf8_fails(
    source_dir: Path, tmp_path: Path
) -> None:
    bom_file = source_dir / "bom.csv"
    content = ",".join(EXPECTED_COLUMNS) + "\n" + ",".join(_row(id="bom")) + "\n"
    bom_file.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))
    passed = run_inventory(_config(source_dir, tmp_path, run_id_suffix="bom"))
    assert passed.scope_gate == "PASS"
    assert passed.file_results[0].bom_type == "UTF8"

    invalid_source = tmp_path / "invalid_source"
    invalid_source.mkdir()
    (invalid_source / "invalid.csv").write_bytes(
        (",".join(EXPECTED_COLUMNS) + "\n").encode("utf-8") + b"bad,\xff\n"
    )
    failed = run_inventory(
        _config(invalid_source, tmp_path, run_id_suffix="invalidutf8")
    )
    assert failed.scope_gate == "FAIL"
    assert failed.file_results[0].encoding_status == "UTF8_INVALID"
    assert failed.file_results[0].error_code == "INVALID_UTF8"


def test_warning_thresholds_report_but_do_not_reject(
    source_dir: Path, tmp_path: Path
) -> None:
    long_value = "x" * 40
    _write_csv(
        source_dir / "large.csv", [_row(id="large", street_address_line_1=long_value)]
    )
    outcome = run_inventory(
        _config(
            source_dir,
            tmp_path,
            run_id_suffix="warnings",
            field_warning_chars=10,
            record_warning_chars=20,
        )
    )
    result = outcome.file_results[0]
    assert outcome.scope_gate == "PASS"
    assert result.scan_status == "COMPLETE"
    anomalies = _read_gzip_csv(outcome.run_dir / "phase01_anomalies.csv.gz")
    assert {row["anomaly_type"] for row in anomalies} >= {
        "OVERSIZED_FIELD",
        "OVERSIZED_LOGICAL_RECORD",
    }


def test_parser_hard_limit_fails_file_without_large_committed_fixture(
    source_dir: Path, tmp_path: Path
) -> None:
    _write_csv(
        source_dir / "limit.csv",
        [_row(id="limit", street_address_line_1="x" * 200)],
    )
    outcome = run_inventory(
        _config(
            source_dir,
            tmp_path,
            run_id_suffix="hardlimit",
            parser_field_limit_chars=64,
        )
    )
    result = outcome.file_results[0]
    assert outcome.scope_gate == "FAIL"
    assert result.error_code == "FIELD_LIMIT_EXCEEDED"
    assert result.counts_complete is False
    assert result.logical_record_count == 0


def test_missing_header_cannot_be_reported_as_complete(
    source_dir: Path, tmp_path: Path
) -> None:
    _write_csv(source_dir / "no_header.csv", [_row(id="first-data-row")])
    text = (source_dir / "no_header.csv").read_text(encoding="utf-8").splitlines()
    (source_dir / "no_header.csv").write_text(text[1] + "\n", encoding="utf-8")
    outcome = run_inventory(_config(source_dir, tmp_path, run_id_suffix="noheader"))
    result = outcome.file_results[0]
    assert outcome.scope_gate == "FAIL"
    assert result.header_present is False
    assert result.counts_complete is False


def test_parser_limit_in_header_stops_without_resynchronization(
    source_dir: Path, tmp_path: Path
) -> None:
    oversized_header = ("x" * 100,) + EXPECTED_COLUMNS[1:]
    _write_csv(
        source_dir / "header_limit.csv", [_row(id="data")], header=oversized_header
    )
    outcome = run_inventory(
        _config(
            source_dir,
            tmp_path,
            run_id_suffix="headerlimit",
            parser_field_limit_chars=64,
        )
    )
    result = outcome.file_results[0]
    assert outcome.scope_gate == "FAIL"
    assert result.error_code == "FIELD_LIMIT_EXCEEDED"
    assert result.logical_record_count == 0
    assert result.counts_complete is False


def test_duplicate_ids_and_duplicate_files_are_exact_and_privacy_safe(
    fixtures_dir: Path, source_dir: Path, tmp_path: Path
) -> None:
    _copy(
        fixtures_dir,
        source_dir,
        "synthetic_duplicate_ids_a.csv",
        "synthetic_duplicate_ids_b.csv",
        "synthetic_duplicate_file.csv",
    )
    outcome = run_inventory(_config(source_dir, tmp_path, run_id_suffix="duplicates"))
    assert outcome.scope_gate == "PASS"
    duplicate_rows = _read_gzip_csv(outcome.run_dir / "phase01_duplicate_ids.csv.gz")
    expected_hash = sha256_text("duplicate-secret-id")
    matching = [row for row in duplicate_rows if row["id_sha256"] == expected_hash]
    assert len(matching) == 5
    assert {row["duplicate_scope"] for row in matching} == {"BOTH"}
    assert all("duplicate-secret-id" not in json.dumps(row) for row in duplicate_rows)

    manifest = _read_csv(outcome.run_dir / "phase01_file_manifest.csv")
    groups = {
        row["file_name"]: row["duplicate_file_group"]
        for row in manifest
        if row["duplicate_file_group"]
    }
    assert (
        groups["synthetic_duplicate_ids_a.csv"]
        == groups["synthetic_duplicate_file.csv"]
    )
    assert all(
        row["duplicate_verification_method"] in {"", "SIZE_AND_SHA256"}
        for row in manifest
    )


def test_native_relationships_and_placeholders_are_aggregate_only(
    source_dir: Path, tmp_path: Path
) -> None:
    rows = [
        _row(id="1"),
        _row(id="2", street_address_line_1_native="住所", postcode="."),
        _row(id="3", street_address_line_1="Address", postcode="-"),
        _row(
            id="4",
            street_address_line_1="Same",
            street_address_line_1_native="Same",
            postcode="Na",
        ),
        _row(
            id="5",
            street_address_line_1="Latin",
            street_address_line_1_native="住所",
            postcode="Nan",
        ),
        _row(id="6", postcode="Null"),
    ]
    _write_csv(source_dir / "native.csv", rows)
    outcome = run_inventory(_config(source_dir, tmp_path, run_id_suffix="native"))
    values = _read_csv(outcome.run_dir / "phase01_value_profile.csv")
    states = {
        row["category"]
        for row in values
        if row["profile_family"] == "NATIVE_PAIR_STATE"
        and row["field_name"].startswith("street_address_line_1__")
    }
    assert states == {
        "BOTH_EMPTY",
        "NATIVE_ONLY",
        "NON_NATIVE_ONLY",
        "EXACT_EQUAL",
        "DIFFERENT",
    }
    placeholder_values = {
        row["category"]
        for row in values
        if row["profile_family"] == "PLACEHOLDER_EXACT"
        and row["field_name"] == "postcode"
    }
    assert placeholder_values == {".", "-", "Na", "Nan", "Null"}


def test_cardinality_safeguard_suppresses_raw_categories(
    source_dir: Path, tmp_path: Path
) -> None:
    rows = [
        _row(id=str(index), location_information=f"value-{index}") for index in range(4)
    ]
    _write_csv(source_dir / "categories.csv", rows)
    outcome = run_inventory(
        _config(
            source_dir,
            tmp_path,
            run_id_suffix="categories",
            categorical_max_distinct=2,
        )
    )
    values = _read_csv(outcome.run_dir / "phase01_value_profile.csv")
    location_rows = [
        row for row in values if row["profile_family"] == "LOCATION_INFORMATION_VALUE"
    ]
    assert [row["category"] for row in location_rows] == [
        "__SUPPRESSED_BY_CARDINALITY_SAFEGUARD__"
    ]
    text = (outcome.run_dir / "phase01_value_profile.csv").read_text(encoding="utf-8")
    assert "value-0" not in text
    anomalies = _read_gzip_csv(outcome.run_dir / "phase01_anomalies.csv.gz")
    assert any(row["anomaly_type"] == "CARDINALITY_LIMIT_EXCEEDED" for row in anomalies)


def test_durable_reports_exclude_sensitive_raw_values(
    source_dir: Path, tmp_path: Path
) -> None:
    secrets = {
        "id": "raw-duplicate-id-secret",
        "address": "Confidential Address Secret",
        "native": "機密住所",
        "city": "Secret City Name",
        "postcode": "00-SECRET",
    }
    row = _row(
        id=secrets["id"],
        street_address_line_1=secrets["address"],
        street_address_line_1_native=secrets["native"],
        postcode=secrets["postcode"],
        city=secrets["city"],
        country_iso_code="DE",
        batch_priority="normal",
        location_information="status",
    )
    _write_csv(source_dir / "private.csv", [row, row])
    outcome = run_inventory(_config(source_dir, tmp_path, run_id_suffix="privacy"))

    durable_texts: list[str] = []
    for name in REPORT_NAMES:
        path = outcome.run_dir / name
        if name.endswith(".gz"):
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                durable_texts.append(stream.read())
        else:
            durable_texts.append(path.read_text(encoding="utf-8"))
    joined = "\n".join(durable_texts)
    assert secrets["id"] not in joined
    assert secrets["address"] not in joined
    assert secrets["native"] not in joined
    assert secrets["city"] not in joined
    assert secrets["postcode"] not in joined
    assert hashlib.sha256(secrets["id"].encode()).hexdigest() in joined


def test_resume_reuses_only_hash_verified_completed_files(
    fixtures_dir: Path, source_dir: Path, tmp_path: Path
) -> None:
    _copy(fixtures_dir, source_dir, "synthetic_ordinary.csv")
    config = _config(source_dir, tmp_path, run_id_suffix="resume")
    first = run_inventory(config)
    resumed = run_inventory(
        InventoryConfig(
            source_root=source_dir,
            reports_root=tmp_path / "reports",
            run_scope="TEST",
            resume_run_dir=first.run_dir,
            insertion_batch_size=2,
        )
    )
    assert resumed.scope_gate == "PASS"
    payload = json.loads(
        (resumed.run_dir / "phase01_run.json").read_text(encoding="utf-8")
    )
    assert payload["resume_information"]["resumed"] is True

    with (source_dir / "synthetic_ordinary.csv").open("a", encoding="utf-8") as stream:
        stream.write("\n")
    with pytest.raises(RuntimeError, match="input_manifest_sha256"):
        run_inventory(
            InventoryConfig(
                source_root=source_dir,
                reports_root=tmp_path / "reports",
                run_scope="TEST",
                resume_run_dir=first.run_dir,
                insertion_batch_size=2,
            )
        )


def test_smoke_scope_requires_explicit_files_and_is_limited(
    fixtures_dir: Path, source_dir: Path, tmp_path: Path
) -> None:
    _copy(
        fixtures_dir,
        source_dir,
        "synthetic_ordinary.csv",
        "synthetic_multiline.csv",
        "synthetic_duplicate_ids_b.csv",
    )
    with pytest.raises(ValueError, match="explicit --include"):
        run_inventory(
            _config(
                source_dir, tmp_path, run_id_suffix="smokenone", run_scope="SMOKE_TEST"
            )
        )
    with pytest.raises(ValueError, match="at most two"):
        run_inventory(
            _config(
                source_dir,
                tmp_path,
                run_id_suffix="smokemany",
                run_scope="SMOKE_TEST",
                include_files=(
                    "synthetic_ordinary.csv",
                    "synthetic_multiline.csv",
                    "synthetic_duplicate_ids_b.csv",
                ),
            )
        )
