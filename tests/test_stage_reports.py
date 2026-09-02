from __future__ import annotations

import subprocess
import sys
from pathlib import Path


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

    portable = "".join(
        path.read_text(encoding="utf-8")
        for path in sorted((repository / "reports").rglob("*"))
        if path.is_file()
    )
    assert "Fictional Secret Address" not in portable
