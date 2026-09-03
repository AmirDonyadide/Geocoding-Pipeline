from __future__ import annotations

import subprocess
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
STAGE00_INVENTORY_SBATCH = (
    REPOSITORY / "cluster" / "goethe_nhr" / "stage00_inventory.sbatch"
)
STAGE01_ADOPT_SBATCH = REPOSITORY / "cluster" / "goethe_nhr" / "stage01_adopt.sbatch"


def test_stage00_inventory_launcher_is_population_scope_driven() -> None:
    script = STAGE00_INVENTORY_SBATCH.read_text(encoding="utf-8")
    assert "safe-geocoding-stage00" in script
    assert "safe-geocoding-phase" not in script
    assert "--population-scope-file" in script
    assert "--expected-population-scope-sha256" in script
    assert "STAGE00_SOURCE_ROOT" in script
    assert "STAGE00_RUN_ID" in script
    assert "SAFE_EXECUTION_SITE=goethe-nhr" in script
    assert "FULL_INVENTORY" in script
    assert "206" not in script
    assert "2822" not in script


def test_current_stage_cluster_assets_are_syntactically_valid() -> None:
    for path in (STAGE00_INVENTORY_SBATCH, STAGE01_ADOPT_SBATCH):
        subprocess.run(["bash", "-n", str(path)], check=True)
