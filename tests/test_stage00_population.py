from __future__ import annotations

import csv
import hashlib
import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from safe_geocoding_pipeline.preprocessing.stages.s00_config import (
    DEFAULT_PARSER_FIELD_LIMIT_CHARS,
    InventoryConfig,
)
from safe_geocoding_pipeline.preprocessing.stage00_cli import (
    build_parser,
    config_from_args,
)
from safe_geocoding_pipeline.preprocessing.stages.s00_constants import INVENTORY_VERSION
from safe_geocoding_pipeline.preprocessing.stages.s00_discovery import (
    discover_source_files,
)
from safe_geocoding_pipeline.preprocessing.stages.s00_population import (
    POPULATION_SCOPE_VERSION,
    load_population_scope,
)
from safe_geocoding_pipeline.preprocessing.stages.s00_models import FileResult
from safe_geocoding_pipeline.preprocessing.stages.s00_parser import scan_csv_file
from safe_geocoding_pipeline.preprocessing.stages.s00_runner import (
    _validate_scope,
    run_inventory,
)
from safe_geocoding_pipeline.preprocessing.stages.s00_inventory import (
    adopt_stage00_inventory,
    validate_stage00_inventory,
)
from safe_geocoding_pipeline.preprocessing.stages.s01_ingestion import (
    resolve_stage00_binding,
)
from safe_geocoding_pipeline.raw_csv import SOURCE_COLUMNS, source_schema_fingerprint

_PRODUCING_COMMIT = "1" * 40


def _write_source(path: Path, identifier: str) -> None:
    values = {column: "" for column in SOURCE_COLUMNS}
    values.update(
        {
            "id": identifier,
            "street_address_line_1": "Fictional Road 1",
            "postcode": "00123",
            "city": "Example City",
            "country_iso_code": "DE",
            "batch_priority": "1",
            "location_information": "fictional",
        }
    )
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(SOURCE_COLUMNS)
        writer.writerow([values[column] for column in SOURCE_COLUMNS])


def _write_scope(
    path: Path,
    relative_paths: list[str],
    *,
    population_id: str = "fictional-population-v1",
    expected_source_count: int | None = None,
) -> str:
    payload = {
        "population_scope_version": POPULATION_SCOPE_VERSION,
        "population_id": population_id,
        "phase01_inventory_version": INVENTORY_VERSION,
        "source_schema_fingerprint": source_schema_fingerprint(SOURCE_COLUMNS),
        "parser_field_limit_chars": DEFAULT_PARSER_FIELD_LIMIT_CHARS,
        "expected_source_count": (
            len(relative_paths)
            if expected_source_count is None
            else expected_source_count
        ),
        "relative_paths": relative_paths,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _full_config(
    source_root: Path,
    reports_root: Path,
    scope_path: Path,
    scope_sha256: str,
    *,
    run_id: str | None = None,
    resume_run_dir: Path | None = None,
) -> InventoryConfig:
    return InventoryConfig(
        source_root=source_root,
        population_scope_file=scope_path,
        expected_population_scope_sha256=scope_sha256,
        reports_root=reports_root,
        run_scope="FULL_INVENTORY",
        run_id=run_id,
        resume_run_dir=resume_run_dir,
        insertion_batch_size=2,
        require_free_bytes=0,
        authorize_full_inventory=True,
    )


def _allow_synthetic_full_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "safe_geocoding_pipeline.preprocessing.stages.s00_runner.require_goethe_nhr_slurm",
        lambda _: None,
    )


@pytest.mark.parametrize("source_count", [1, 3, 7])
def test_full_inventory_accepts_variable_authorized_populations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source_count: int
) -> None:
    _allow_synthetic_full_run(monkeypatch)
    source_root = tmp_path / "source"
    source_root.mkdir()
    relative_paths = [f"fictional_{index:04d}.csv" for index in range(source_count)]
    for index, relative_path in enumerate(relative_paths):
        _write_source(source_root / relative_path, f"fictional-{index}")
    scope_path = tmp_path / "population_scope.json"
    scope_sha256 = _write_scope(scope_path, relative_paths)

    outcome = run_inventory(
        _full_config(
            source_root,
            tmp_path / "reports",
            scope_path,
            scope_sha256,
            run_id=f"phase01_20260101T000000Z_generic{source_count}",
        )
    )

    assert outcome.stage00_completion_gate == "PASS"
    assert len(outcome.file_results) == source_count
    run = json.loads((outcome.run_dir / "phase01_run.json").read_text())
    assert run["authorized_population_scope"]["expected_source_count"] == source_count
    assert run["authorized_population_scope"]["population_scope_artifact_sha256"] == (
        scope_sha256
    )


def test_historical_206_population_scope_remains_representable(tmp_path: Path) -> None:
    paths = [f"historical_{index:04d}.csv" for index in range(1, 207)]
    scope_path = tmp_path / "historical_scope.json"
    scope_sha256 = _write_scope(scope_path, paths, population_id="historical-206")
    scope = load_population_scope(
        scope_path,
        expected_sha256=scope_sha256,
        expected_parser_field_limit_chars=DEFAULT_PARSER_FIELD_LIMIT_CHARS,
    )
    assert scope.expected_source_count == 206
    assert len(scope.relative_paths) == 206


@pytest.mark.parametrize(
    ("authorized", "present"),
    [
        (["a.csv"], ["a.csv", "extra.csv"]),
        (["a.csv", "missing.csv"], ["a.csv"]),
        (["a.csv", "expected.csv"], ["a.csv", "different.csv"]),
    ],
)
def test_authorized_population_rejects_count_and_path_set_mismatches(
    tmp_path: Path, authorized: list[str], present: list[str]
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    for index, relative_path in enumerate(present):
        _write_source(source_root / relative_path, f"fictional-{index}")
    config = InventoryConfig(source_root=source_root)
    with pytest.raises(ValueError, match="authorized population"):
        discover_source_files(config, authorized_relative_paths=tuple(authorized))


@pytest.mark.parametrize("link_is_expected", [True, False])
def test_authorized_population_rejects_expected_or_extra_csv_symlink(
    tmp_path: Path, link_is_expected: bool
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_source(source_root / "a.csv", "fictional-a")
    link_name = "expected.csv" if link_is_expected else "extra.csv"
    (source_root / link_name).symlink_to(source_root / "a.csv")
    authorized = ("a.csv", "expected.csv") if link_is_expected else ("a.csv",)
    with pytest.raises(OSError, match="unsafe CSV entry"):
        discover_source_files(
            InventoryConfig(source_root=source_root),
            authorized_relative_paths=authorized,
        )


def test_population_scope_rejects_duplicate_authorized_path(tmp_path: Path) -> None:
    scope_path = tmp_path / "duplicate_scope.json"
    scope_sha256 = _write_scope(scope_path, ["a.csv", "a.csv"])
    with pytest.raises(ValueError, match="duplicate source path"):
        load_population_scope(
            scope_path,
            expected_sha256=scope_sha256,
            expected_parser_field_limit_chars=DEFAULT_PARSER_FIELD_LIMIT_CHARS,
        )


@pytest.mark.parametrize("mutation", ["hash", "mode", "count"])
def test_population_scope_identity_permissions_and_count_fail_closed(
    tmp_path: Path, mutation: str
) -> None:
    scope_path = tmp_path / "population_scope.json"
    scope_sha256 = _write_scope(
        scope_path,
        ["a.csv"],
        expected_source_count=2 if mutation == "count" else 1,
    )
    expected_sha256 = "0" * 64 if mutation == "hash" else scope_sha256
    if mutation == "mode":
        scope_path.chmod(0o644)
    with pytest.raises((OSError, ValueError)):
        load_population_scope(
            scope_path,
            expected_sha256=expected_sha256,
            expected_parser_field_limit_chars=DEFAULT_PARSER_FIELD_LIMIT_CHARS,
        )


def test_authorized_population_rejects_broken_symlink_and_nonregular_csv(
    tmp_path: Path,
) -> None:
    for name in ("broken", "directory"):
        source_root = tmp_path / name
        source_root.mkdir()
        unsafe = source_root / "unsafe.csv"
        if name == "broken":
            unsafe.symlink_to(tmp_path / "absent.csv")
        else:
            unsafe.mkdir()
        with pytest.raises(OSError, match="unsafe CSV entry"):
            discover_source_files(
                InventoryConfig(source_root=source_root),
                authorized_relative_paths=("unsafe.csv",),
            )


def test_generic_full_inventory_scope_has_no_magic_population_count() -> None:
    assert "206" not in inspect.getsource(_validate_scope)


def test_cli_makes_full_inventory_population_scope_explicit(tmp_path: Path) -> None:
    scope_path = tmp_path / "population_scope.json"
    args = build_parser().parse_args(
        [
            "--source-root",
            str(tmp_path / "source"),
            "--population-scope-file",
            str(scope_path),
            "--expected-population-scope-sha256",
            "a" * 64,
            "--run-scope",
            "FULL_INVENTORY",
            "--authorize-full-inventory",
        ]
    )
    config = config_from_args(args)
    assert config.population_scope_file == scope_path
    assert config.expected_population_scope_sha256 == "a" * 64


def test_resume_rejects_changed_population_scope_without_mutating_completed_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_synthetic_full_run(monkeypatch)
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_source(source_root / "a.csv", "fictional-a")
    scope_path = tmp_path / "population_scope.json"
    first_sha256 = _write_scope(scope_path, ["a.csv"], population_id="population-a")
    first = run_inventory(
        _full_config(
            source_root,
            tmp_path / "reports",
            scope_path,
            first_sha256,
            run_id="phase01_20260101T000000Z_resume_scope",
        )
    )
    run_bytes = (first.run_dir / "phase01_run.json").read_bytes()
    marker_bytes = (first.run_dir / "_SCOPE_PASS").read_bytes()
    second_sha256 = _write_scope(scope_path, ["a.csv"], population_id="population-b")

    with pytest.raises(RuntimeError, match="population_scope_sha256"):
        run_inventory(
            _full_config(
                source_root,
                tmp_path / "reports",
                scope_path,
                second_sha256,
                resume_run_dir=first.run_dir,
            )
        )
    assert (first.run_dir / "phase01_run.json").read_bytes() == run_bytes
    assert (first.run_dir / "_SCOPE_PASS").read_bytes() == marker_bytes


def test_population_membership_mutation_during_inventory_fails_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_synthetic_full_run(monkeypatch)
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_source(source_root / "a.csv", "fictional-a")
    scope_path = tmp_path / "population_scope.json"
    scope_sha256 = _write_scope(scope_path, ["a.csv"])

    def scan_and_mutate(**kwargs: Any) -> FileResult:
        result = scan_csv_file(**kwargs)
        _write_source(source_root / "late.csv", "fictional-late")
        return result

    monkeypatch.setattr(
        "safe_geocoding_pipeline.preprocessing.stages.s00_runner.scan_csv_file",
        scan_and_mutate,
    )
    reports_root = tmp_path / "reports"
    run_id = "phase01_20260101T000000Z_membership_change"
    with pytest.raises(ValueError, match="authorized population"):
        run_inventory(
            _full_config(
                source_root,
                reports_root,
                scope_path,
                scope_sha256,
                run_id=run_id,
            )
        )
    run_dir = reports_root / run_id
    assert (run_dir / "_IN_PROGRESS").is_file()
    assert not (run_dir / "_SCOPE_PASS").exists()


def test_real_scans_change_stage00_population_identity_without_contract_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_synthetic_full_run(monkeypatch)
    monkeypatch.setattr(
        "safe_geocoding_pipeline.preprocessing.stages.s00_runner._git_commit",
        lambda: _PRODUCING_COMMIT,
    )
    monkeypatch.setattr(
        "safe_geocoding_pipeline.preprocessing.stages.s00_runner._git_dirty",
        lambda: False,
    )
    fingerprints: list[str] = []
    for source_count in (1, 2):
        root = tmp_path / f"source_{source_count}"
        root.mkdir()
        paths = [f"fictional_{index:04d}.csv" for index in range(source_count)]
        for index, relative_path in enumerate(paths):
            _write_source(root / relative_path, f"fictional-{source_count}-{index}")
        scope_path = tmp_path / f"scope_{source_count}.json"
        scope_sha256 = _write_scope(
            scope_path, paths, population_id=f"population-{source_count}"
        )
        outcome = run_inventory(
            _full_config(
                root,
                tmp_path / f"reports_{source_count}",
                scope_path,
                scope_sha256,
                run_id=f"phase01_20260101T000000Z_identity{source_count}",
            )
        )
        bundle = validate_stage00_inventory(
            outcome.run_dir,
            expected_file_count=source_count,
            expected_producing_git_commit=_PRODUCING_COMMIT,
        )
        fingerprints.append(bundle.source_population_sha256_v1)
        if source_count == 2:
            adoption = adopt_stage00_inventory(
                outcome.run_dir,
                tmp_path / "stage00_adoption",
                expected_file_count=source_count,
                expected_producing_git_commit=_PRODUCING_COMMIT,
                adopting_git_commit="2" * 40,
                adopting_git_dirty=False,
                adoption_timestamp_utc="2026-01-02T00:00:00Z",
            )
            binding = resolve_stage00_binding(
                adoption.adoption_record_path,
                outcome.run_dir,
                expected_stage00_adoption_sha256=adoption.adoption_record_sha256,
            )
            assert len(binding.source_inventory_bundle.records) == source_count

    assert fingerprints[0] != fingerprints[1]
