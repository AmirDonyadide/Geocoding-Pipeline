#!/usr/bin/env bash
#SBATCH --job-name=safe-stage00-inventory
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=32G
#SBATCH --time=24:00:00
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

readonly DATA_ROOT="/work/footprint/donyadidegan/safe_geocoding_pipeline"
: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${STAGE00_GIT_COMMIT:?submit with the exact reviewed Stage 0 commit}"
: "${STAGE00_INTEGRATION_ROOT:?submit with an exact detached integration worktree}"
: "${STAGE00_SOURCE_ROOT:?submit with the controlled immutable source root}"
: "${STAGE00_POPULATION_SCOPE:?submit with the controlled population-scope JSON}"
: "${STAGE00_POPULATION_SCOPE_SHA256:?submit with the exact scope SHA-256}"
: "${STAGE00_REPORTS_ROOT:?submit with the controlled Phase 1 reports root}"
: "${STAGE00_RUN_ID:?submit with the approved new Phase 1 run ID}"
readonly REQUIRE_FREE_GIB="${STAGE00_REQUIRE_FREE_GIB:-100}"
readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE00_INTEGRATION_ROOT}")"
readonly SOURCE_ROOT="$(realpath -e -- "${STAGE00_SOURCE_ROOT}")"
readonly POPULATION_SCOPE="$(realpath -e -- "${STAGE00_POPULATION_SCOPE}")"
readonly REPORTS_ROOT="$(realpath -m -- "${STAGE00_REPORTS_ROOT}")"

cd "${INTEGRATION_ROOT}"
source "${DATA_ROOT}/.venv-goethe-nhr/bin/activate"
export PYTHONPATH="${INTEGRATION_ROOT}/src"
export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1

readonly ACTUAL_COMMIT="$(git rev-parse HEAD)"
[[ "${ACTUAL_COMMIT}" == "${STAGE00_GIT_COMMIT}" ]] || {
  echo "STAGE00_COMMIT_MISMATCH" >&2
  exit 1
}
[[ -z "$(git status --porcelain)" ]] || {
  echo "STAGE00_WORKTREE_DIRTY" >&2
  exit 1
}

echo "job_id=${SLURM_JOB_ID}"
echo "git_commit=${ACTUAL_COMMIT}"
echo "stage=stage00_authoritative_phase01_inventory"

safe-geocoding-phase01 \
  --source-root "${SOURCE_ROOT}" \
  --population-scope-file "${POPULATION_SCOPE}" \
  --expected-population-scope-sha256 "${STAGE00_POPULATION_SCOPE_SHA256}" \
  --reports-root "${REPORTS_ROOT}" \
  --run-scope FULL_INVENTORY \
  --run-id "${STAGE00_RUN_ID}" \
  --require-free-gib "${REQUIRE_FREE_GIB}" \
  --authorize-full-inventory

echo "STAGE00_PHASE01_INVENTORY_PASS"
