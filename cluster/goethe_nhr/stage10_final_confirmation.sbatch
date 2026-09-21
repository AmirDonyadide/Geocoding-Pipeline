#!/usr/bin/env bash
#SBATCH --job-name=safe-stage10-final
#SBATCH --partition=general1
#SBATCH --account=footprint
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --no-requeue
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077
: "${SLURM_JOB_ID:?scheduled confirmation required}"
: "${STAGE10_CONFIRMATION_SHA:?exact pushed confirmation required}"
: "${STAGE10_CONFIRMATION_CHECKOUT:?clean detached checkout required}"
: "${STAGE10_CONFIRMATION_OUTPUT:?new confirmation destination required}"
readonly stage10_project="$(realpath -e /work/footprint/donyadidegan/safe_geocoding_pipeline)"
[[ "${SLURM_RESTART_COUNT:-0}" == 0 && "${SLURM_CPUS_PER_TASK}" == 4 ]]
[[ "${STAGE10_CONFIRMATION_SHA}" =~ ^[a-f0-9]{40}$ ]]
[[ "$(realpath -e "${STAGE10_CONFIRMATION_CHECKOUT}")" == "${STAGE10_CONFIRMATION_CHECKOUT}" ]]
[[ "$(dirname "${STAGE10_CONFIRMATION_CHECKOUT}")" == "${stage10_project}/integration_stage10" ]]
[[ "$(dirname "${STAGE10_CONFIRMATION_OUTPUT}")" == "${stage10_project}/derived/controlled/stage10/confirmations" ]]
[[ "$(realpath -m "${STAGE10_CONFIRMATION_OUTPUT}")" == "${STAGE10_CONFIRMATION_OUTPUT}" ]]
[[ ! -e "${STAGE10_CONFIRMATION_OUTPUT}" && ! -L "${STAGE10_CONFIRMATION_OUTPUT}" ]]
cd "${STAGE10_CONFIRMATION_CHECKOUT}"
[[ "$(git rev-parse HEAD)" == "${STAGE10_CONFIRMATION_SHA}" ]]
[[ -z "$(git status --porcelain)" && -z "$(git symbolic-ref -q HEAD || true)" ]]
git merge-base --is-ancestor 39c0470adb6c99b7f08f70775fa2e21906e913ec HEAD
chmod 0600 "${stage10_project}/logs/slurm/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.out" \
  "${stage10_project}/logs/slurm/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.err"
export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONHASHSEED=0
export LANG=C.UTF-8 LC_ALL=C.UTF-8 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export PYTHONPATH="${STAGE10_CONFIRMATION_CHECKOUT}/src"
"${stage10_project}/runtimes/stage06/stage06_development_20260828T223804Z_f39047cc825d/venv/bin/python" \
  -B -m safe_geocoding_pipeline.preprocessing.stage10_final_confirmation \
  --execution-git-sha "${STAGE10_CONFIRMATION_SHA}" --output "${STAGE10_CONFIRMATION_OUTPUT}"
