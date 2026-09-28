#!/usr/bin/env bash
#SBATCH --job-name=safe-stage10-publication-forensics
#SBATCH --partition=general1
#SBATCH --account=footprint
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=01:00:00
#SBATCH --no-requeue
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077
: "${SLURM_JOB_ID:?scheduled execution required}"
: "${STAGE10_EXECUTION_GIT_SHA:?exact pushed executable required}"
: "${STAGE10_CHECKOUT:?clean detached checkout required}"
: "${STAGE10_FORENSIC_REPORT_ROOT:?new private forensic report root required}"
readonly project="$(realpath -e /work/footprint/donyadidegan/safe_geocoding_pipeline)"
[[ "$(realpath -e "${STAGE10_CHECKOUT}")" == "${STAGE10_CHECKOUT}" ]]
[[ "$(dirname "${STAGE10_CHECKOUT}")" == "${project}/integration_stage10" ]]
[[ "$(dirname "${STAGE10_FORENSIC_REPORT_ROOT}")" == "${project}/derived/controlled/stage10/development/work" ]]
[[ ! -e "${STAGE10_FORENSIC_REPORT_ROOT}" && ! -L "${STAGE10_FORENSIC_REPORT_ROOT}" ]]
cd "${STAGE10_CHECKOUT}"
[[ "$(git rev-parse HEAD)" == "${STAGE10_EXECUTION_GIT_SHA}" ]]
[[ -z "$(git status --porcelain)" && -z "$(git symbolic-ref -q HEAD || true)" ]]
[[ "${SLURM_RESTART_COUNT:-0}" == 0 ]]
chmod 0600 "${project}/logs/slurm/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.out" \
  "${project}/logs/slurm/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.err"
export SAFE_EXECUTION_SITE=goethe-nhr PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONHASHSEED=0
export LANG=C.UTF-8 LC_ALL=C.UTF-8 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export PYTHONPATH="${STAGE10_CHECKOUT}/src"
"${project}/runtimes/stage06/stage06_development_20260828T223804Z_f39047cc825d/venv/bin/python" \
  -B -m safe_geocoding_pipeline.preprocessing.stage10_publication_forensics \
  --executable "${STAGE10_EXECUTION_GIT_SHA}" --report-root "${STAGE10_FORENSIC_REPORT_ROOT}"
