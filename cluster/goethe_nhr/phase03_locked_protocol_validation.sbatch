#!/usr/bin/env bash
#SBATCH --job-name=safe-phase03-locked-protocol-validate
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
: "${PHASE03_GIT_COMMIT:?reviewed protocol implementation commit is required}"
: "${PHASE03_INTEGRATION_ROOT:?detached protocol worktree is required}"
readonly INTEGRATION_ROOT="$(realpath -e -- "${PHASE03_INTEGRATION_ROOT}")"

[[ "$(git -C "${INTEGRATION_ROOT}" rev-parse HEAD)" == "${PHASE03_GIT_COMMIT}" ]] || {
  echo "LOCKED_PROTOCOL_VALIDATION_COMMIT_MISMATCH" >&2
  exit 1
}
[[ -z "$(git -C "${INTEGRATION_ROOT}" status --short)" ]] || {
  echo "LOCKED_PROTOCOL_VALIDATION_WORKTREE_DIRTY" >&2
  exit 1
}

cd "${INTEGRATION_ROOT}"
source "${DATA_ROOT}/.venv-goethe-nhr/bin/activate"
export PYTHONPATH="${INTEGRATION_ROOT}/src"
export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1

echo "job_id=${SLURM_JOB_ID}"
echo "hostname=$(hostname)"
echo "partition=${SLURM_JOB_PARTITION:-unknown}"
echo "git_commit=${PHASE03_GIT_COMMIT}"
echo "locked_rows_read=0"
echo "stage=focused"
python -m pytest -q \
  tests/test_phase03_locked_evaluation.py \
  tests/test_phase03_parser_v3_2_experimental.py

echo "stage=phase03"
python -m pytest -q tests/test_phase03_*.py

echo "stage=repository_local_safe"
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
  src/safe_geocoding_pipeline/phase03/constants.py \
  src/safe_geocoding_pipeline/phase03/engine.py \
  src/safe_geocoding_pipeline/phase03/locked_evaluation.py \
  src/safe_geocoding_pipeline/phase03/locked_evaluation_cli.py \
  tests/test_phase03_locked_evaluation.py

echo "stage=mypy"
mypy src

echo "stage=shell"
bash -n cluster/goethe_nhr/phase03_locked_protocol_validation.sbatch
bash -n cluster/goethe_nhr/phase03_locked_evaluation.sbatch

echo "stage=diff"
git diff --check
echo "LOCKED_PROTOCOL_VALIDATION_COMPLETE"
echo "locked_rows_read=0"
