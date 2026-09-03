from __future__ import annotations

import runpy
import subprocess
import sys
from pathlib import Path
from typing import Callable, cast


def _report_surface_validator(
    repository: Path,
) -> Callable[[set[Path], set[Path], list[str]], None]:
    namespace = runpy.run_path(
        str(repository / "scripts" / "validate_stage_reports.py")
    )
    return cast(
        Callable[[set[Path], set[Path], list[str]], None],
        namespace["_validate_report_surface"],
    )


def test_committed_stage_reports_are_consolidated_and_valid() -> None:
    repository = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, str(repository / "scripts" / "validate_stage_reports.py")],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.strip() == "STAGE_REPORTS_VALIDATION_PASS"

    namespace = runpy.run_path(
        str(repository / "scripts" / "validate_stage_reports.py")
    )
    errors: list[str] = []
    tracked = cast(
        Callable[[list[str]], set[Path]], namespace["_tracked_report_paths"]
    )(errors)
    assert errors == []
    portable = "".join(path.read_text(encoding="utf-8") for path in sorted(tracked))
    assert "Fictional Secret Address" not in portable


def test_report_validator_ignores_ignored_ds_store_but_rejects_tracked_surface_drift() -> (
    None
):
    repository = Path(__file__).resolve().parents[1]
    namespace = runpy.run_path(
        str(repository / "scripts" / "validate_stage_reports.py")
    )
    expected = cast(Callable[[], set[Path]], namespace["_expected_report_paths"])()
    tracked_errors: list[str] = []
    tracked = cast(
        Callable[[list[str]], set[Path]], namespace["_tracked_report_paths"]
    )(tracked_errors)
    validate_surface = _report_surface_validator(repository)

    assert tracked_errors == []
    assert repository / "reports" / ".DS_Store" not in tracked
    ignored_metadata_errors: list[str] = []
    validate_surface(tracked, expected, ignored_metadata_errors)
    assert ignored_metadata_errors == []

    unexpected_errors: list[str] = []
    validate_surface(
        tracked | {repository / "reports" / "development" / "unexpected.md"},
        expected,
        unexpected_errors,
    )
    assert unexpected_errors == [
        "unexpected tracked report files: ['reports/development/unexpected.md']"
    ]

    missing_errors: list[str] = []
    validate_surface(
        tracked - {repository / "reports" / "generated" / "stage00.json"},
        expected,
        missing_errors,
    )
    assert missing_errors == [
        "missing expected tracked report files: ['reports/generated/stage00.json']"
    ]
