#!/usr/bin/env bash
#SBATCH --job-name=safe-stage09-fsdiag
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:05:00
#SBATCH --no-requeue
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077
: "${SLURM_JOB_ID:?scheduled execution required}"
: "${SLURM_JOB_NAME:?scheduled execution required}"
: "${STAGE09_DIAGNOSTIC_GIT_COMMIT:?exact pushed SHA required}"
: "${STAGE09_DIAGNOSTIC_INTEGRATION_ROOT:?clean detached checkout required}"
: "${STAGE09_RUNTIME_ROOT:?exact existing runtime required}"
: "${STAGE09_DIAGNOSTIC_OUTPUT_DIRECTORY:?new synthetic-only directory required}"

readonly DATA_ROOT="$(realpath -e -- /work/footprint/donyadidegan/safe_geocoding_pipeline)"
readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE09_DIAGNOSTIC_INTEGRATION_ROOT}")"
readonly RUNTIME_ROOT="$(realpath -e -- "${STAGE09_RUNTIME_ROOT}")"
readonly OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE09_DIAGNOSTIC_OUTPUT_DIRECTORY}")"
readonly DIAGNOSTIC_PARENT="${DATA_ROOT}/derived/controlled/stage09/filesystem_diagnostics"
[[ "${INTEGRATION_ROOT}" == "${DATA_ROOT}/integration_stage09/"* ]]
[[ "${RUNTIME_ROOT}" == "${DATA_ROOT}/runtimes/stage06/"* ]]
[[ "$(dirname -- "${OUTPUT_DIRECTORY}")" == "${DIAGNOSTIC_PARENT}" ]]
[[ ! -e "${OUTPUT_DIRECTORY}" && ! -L "${OUTPUT_DIRECTORY}" ]]
[[ -x "${RUNTIME_ROOT}/venv/bin/python" ]]
chmod 0600 "${DATA_ROOT}/logs/slurm/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.out" \
  "${DATA_ROOT}/logs/slurm/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.err"
cd "${INTEGRATION_ROOT}"
[[ "$(git rev-parse HEAD)" == "${STAGE09_DIAGNOSTIC_GIT_COMMIT}" ]]
[[ -z "$(git status --porcelain)" ]]
[[ -z "$(git symbolic-ref -q HEAD || true)" ]]
export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1
export PYTHONHASHSEED=0
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export PYTHONPATH="${INTEGRATION_ROOT}/src"

# No Stage 8/reference paths, materializer invocation, fallback or retry.
"${RUNTIME_ROOT}/venv/bin/python" -B -m safe_geocoding_pipeline.preprocessing.stage09_filesystem_diagnostic \
  --output-directory "${OUTPUT_DIRECTORY}" \
  --execution-git-sha "${STAGE09_DIAGNOSTIC_GIT_COMMIT}"
