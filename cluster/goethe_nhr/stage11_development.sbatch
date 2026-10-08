#!/usr/bin/env bash
#SBATCH --job-name=safe-stage11-development
#SBATCH --partition=general1
#SBATCH --account=footprint
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --tmp=2048M
#SBATCH --time=01:00:00
#SBATCH --no-requeue
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077
: "${SLURM_JOB_ID:?scheduled execution required}"
: "${STAGE11_EXECUTION_GIT_SHA:?exact pushed executable required}"
: "${STAGE11_CHECKOUT:?clean detached checkout required}"
: "${STAGE11_OUTPUT_DIRECTORY:?new immutable DEVELOPMENT target required}"
readonly stage11_project=/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline
readonly stage11_python="${stage11_project}/runtimes/stage06/stage06_development_20260828T223804Z_f39047cc825d/venv/bin/python"
[[ "${SLURM_RESTART_COUNT:-0}" == 0 && "${SLURM_CPUS_PER_TASK}" == 2 ]]
[[ "${STAGE11_EXECUTION_GIT_SHA}" =~ ^[a-f0-9]{40}$ ]]
[[ "$(dirname -- "${STAGE11_CHECKOUT}")" == "${stage11_project}/integration_stage11" ]]
[[ "$(realpath -e -- "${STAGE11_CHECKOUT}")" == "${STAGE11_CHECKOUT}" ]]
[[ "$(dirname -- "${STAGE11_OUTPUT_DIRECTORY}")" == "${stage11_project}/derived/controlled/stage11/development" ]]
[[ "$(realpath -m -- "${STAGE11_OUTPUT_DIRECTORY}")" == "${STAGE11_OUTPUT_DIRECTORY}" ]]
[[ ! -e "${STAGE11_OUTPUT_DIRECTORY}" && ! -L "${STAGE11_OUTPUT_DIRECTORY}" ]]
[[ -x "${stage11_python}" ]]
cd "${STAGE11_CHECKOUT}"
[[ "$(git rev-parse HEAD)" == "${STAGE11_EXECUTION_GIT_SHA}" ]]
[[ -z "$(git status --porcelain)" && -z "$(git symbolic-ref -q HEAD || true)" ]]
git merge-base --is-ancestor 125b3684a000ea79523f77049ae1a290b0da8109 HEAD
chmod 0600 "${stage11_project}/logs/slurm/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.out" \
  "${stage11_project}/logs/slurm/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.err"
export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONHASHSEED=0
export LANG=C.UTF-8 LC_ALL=C.UTF-8 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export PYTHONPATH="${STAGE11_CHECKOUT}/src"
# One complete offline catalog and full publication validations in this job.
# No service, budget, sampling, dynamic pull, resubmission or automatic retry.
"${stage11_python}" -B -m safe_geocoding_pipeline.preprocessing.stage11_cli \
  --execution-git-sha "${STAGE11_EXECUTION_GIT_SHA}" \
  --output-directory "${STAGE11_OUTPUT_DIRECTORY}"
