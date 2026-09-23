"""Only invented, complete-schema fixtures from the repository test suite."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_stage09_reference_evaluator import reference_view as reference_view  # noqa: E402
from test_stage10_context_pipeline import synthetic_inputs as synthetic_inputs  # noqa: E402
