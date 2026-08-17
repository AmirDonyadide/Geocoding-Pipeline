#!/usr/bin/env bash
#SBATCH --job-name=safe-phase03-v32-validate
#SBATCH --partition=test
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --mail-user=donyadidegan@safe-frankfurt.de
#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

readonly DATA_ROOT="/work/footprint/donyadidegan/safe_geocoding_pipeline"
: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${PHASE03_INTEGRATION_ROOT:?parser-v3.2 validation worktree is required}"
readonly INTEGRATION_ROOT="$(realpath -e -- "${PHASE03_INTEGRATION_ROOT}")"

cd "${INTEGRATION_ROOT}"
source "${DATA_ROOT}/.venv-goethe-nhr/bin/activate"
export PYTHONPATH="${INTEGRATION_ROOT}/src"
export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1

echo "job_id=${SLURM_JOB_ID}"
echo "hostname=$(hostname)"
echo "integration_root=${INTEGRATION_ROOT}"
echo "git_head=$(git rev-parse HEAD)"
echo "stage=identities"
python - <<'PY'
from safe_geocoding_pipeline.phase03.config import Phase03Config
from safe_geocoding_pipeline.phase03.constants import PARSER_VERSION_V3_2
from safe_geocoding_pipeline.phase03.engine import Phase03Engine
from safe_geocoding_pipeline.phase03.references import load_production_references
from safe_geocoding_pipeline.phase03.rules import load_rule_registry

config = Phase03Config.for_parser_version(PARSER_VERSION_V3_2)
registry = load_rule_registry(registry_version=config.rule_registry_version)
country, scripts = load_production_references(
    expected_country_reference_id=config.country_reference_version,
    expected_unicode_reference_id=config.unicode_reference_version,
)
engine = Phase03Engine(
    config,
    registry,
    country_reference=country,
    script_reference=scripts,
    implementation_fingerprint=bytes(32),
    execution_scope="DEVELOPMENT",
)
print(f"registry_sha256={registry.fingerprint}")
print(f"base_config_sha256={config.configuration_fingerprint().hex()}")
print(f"effective_config_sha256={engine.configuration_fingerprint.hex()}")
PY

echo "stage=focused"
python -m pytest -q \
  tests/test_phase03_parser_v3_2_experimental.py \
  tests/test_phase03_development_comparison_v3.py \
  tests/test_phase03_targeted_orientation_analysis.py \
  tests/test_phase03_targeted_v3_2_evaluation.py

echo "stage=phase03"
python -m pytest -q tests/test_phase03_*.py

echo "stage=repository"
python -m pytest -q \
  tests/test_cluster_execution_assets.py \
  tests/test_execution_policy.py \
  tests/test_phase01_discovery.py \
  tests/test_phase01_inventory.py \
  tests/test_phase01_profiling.py \
  tests/test_phase01_store.py \
  tests/test_phase02_integration.py \
  tests/test_phase02_unit.py \
  --deselect=tests/test_cluster_execution_assets.py::test_sync_dry_run_plan_is_minimal_complete_and_reconstructable \
  --deselect=tests/test_cluster_execution_assets.py::test_sync_uses_protect_args_with_modern_rsync \
  --deselect=tests/test_cluster_execution_assets.py::test_sync_omits_protect_args_with_old_rsync \
  --deselect=tests/test_cluster_execution_assets.py::test_sync_prefers_homebrew_rsync_over_path_rsync

echo "stage=ruff"
ruff check .
ruff format --check \
  src/safe_geocoding_pipeline/phase03/cli.py \
  src/safe_geocoding_pipeline/phase03/constants.py \
  src/safe_geocoding_pipeline/phase03/development_comparison.py \
  src/safe_geocoding_pipeline/phase03/engine.py \
  src/safe_geocoding_pipeline/phase03/rules.py \
  src/safe_geocoding_pipeline/phase03/targeted_orientation_analysis.py \
  src/safe_geocoding_pipeline/phase03/targeted_review_cli.py \
  src/safe_geocoding_pipeline/phase03/targeted_v3_2_evaluation.py \
  tests/test_phase03_development_comparison_v3.py \
  tests/test_phase03_development_v3_change_diagnostic.py \
  tests/test_phase03_parser_v3_2_experimental.py \
  tests/test_phase03_targeted_orientation_analysis.py \
  tests/test_phase03_targeted_v3_2_evaluation.py

echo "stage=mypy"
mypy src

echo "stage=shell"
bash -n cluster/goethe_nhr/phase03_parser_v3_2_validation.sbatch
bash -n cluster/goethe_nhr/phase03_development_parser_v3_2_experimental.sbatch

echo "stage=diff"
git diff --check
echo "VALIDATION_COMPLETE"
