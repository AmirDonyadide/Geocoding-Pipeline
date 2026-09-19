#!/usr/bin/env bash
#SBATCH --job-name=safe-stage10-throughput
#SBATCH --partition=general1
#SBATCH --account=footprint
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=00:30:00
#SBATCH --no-requeue
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077
: "${SLURM_JOB_ID:?scheduled diagnostic required}"
: "${STAGE10_DIAGNOSTIC_SHA:?exact pushed diagnostic required}"
: "${STAGE10_DIAGNOSTIC_CHECKOUT:?clean detached checkout required}"
: "${STAGE10_DIAGNOSTIC_OUTPUT:?new diagnostic destination required}"
readonly stage10_project="$(realpath -e /work/footprint/donyadidegan/safe_geocoding_pipeline)"
[[ "${SLURM_RESTART_COUNT:-0}" == 0 && "${SLURM_CPUS_PER_TASK}" == 4 ]]
[[ "${STAGE10_DIAGNOSTIC_SHA}" =~ ^[a-f0-9]{40}$ ]]
[[ "$(realpath -e "${STAGE10_DIAGNOSTIC_CHECKOUT}")" == "${STAGE10_DIAGNOSTIC_CHECKOUT}" ]]
[[ "$(dirname "${STAGE10_DIAGNOSTIC_CHECKOUT}")" == "${stage10_project}/integration_stage10" ]]
[[ "$(dirname "${STAGE10_DIAGNOSTIC_OUTPUT}")" == "${stage10_project}/derived/controlled/stage10/diagnostics" ]]
[[ "$(realpath -m "${STAGE10_DIAGNOSTIC_OUTPUT}")" == "${STAGE10_DIAGNOSTIC_OUTPUT}" ]]
[[ ! -e "${STAGE10_DIAGNOSTIC_OUTPUT}" && ! -L "${STAGE10_DIAGNOSTIC_OUTPUT}" ]]
cd "${STAGE10_DIAGNOSTIC_CHECKOUT}"
[[ "$(git rev-parse HEAD)" == "${STAGE10_DIAGNOSTIC_SHA}" ]]
[[ -z "$(git status --porcelain)" && -z "$(git symbolic-ref -q HEAD || true)" ]]
git merge-base --is-ancestor ba03e17b406c5f9c953359e6efce9fbc4b8d2e74 HEAD
chmod 0600 "${stage10_project}/logs/slurm/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.out" \
  "${stage10_project}/logs/slurm/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.err"
export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONHASHSEED=0
export LANG=C.UTF-8 LC_ALL=C.UTF-8 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export PYTHONPATH="${STAGE10_DIAGNOSTIC_CHECKOUT}/src"
"${stage10_project}/runtimes/stage06/stage06_development_20260828T223804Z_f39047cc825d/venv/bin/python" \
  -B -m safe_geocoding_pipeline.preprocessing.stage10_throughput_diagnostic \
  --execution-git-sha "${STAGE10_DIAGNOSTIC_SHA}" --output "${STAGE10_DIAGNOSTIC_OUTPUT}"
