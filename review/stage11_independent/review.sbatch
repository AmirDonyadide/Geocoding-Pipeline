#!/usr/bin/env bash
#SBATCH --job-name=safe-stage11-independent-review
#SBATCH --partition=general1
#SBATCH --account=footprint
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --no-requeue
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err
set -euo pipefail
umask 077
ulimit -c 0
: "${SLURM_JOB_ID:?scheduled review required}"
: "${STAGE11_REVIEW_SHA:?exact pushed review SHA required}"
: "${STAGE11_REVIEW_CHECKOUT:?clean detached review checkout required}"
readonly stage11_project=/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline
readonly stage11_candidate_sha=8dce0e1078e123748ae692fa824200fc3e646aa4
readonly stage11_python="${stage11_project}/runtimes/stage06/stage06_development_20260828T223804Z_f39047cc825d/venv/bin/python"
export STAGE11_CANDIDATE_CHECKOUT="${stage11_project}/integration_stage11/${stage11_candidate_sha}"
[[ "${SLURM_RESTART_COUNT:-0}" == 0 && "${SLURM_CPUS_PER_TASK}" == 2 ]]
[[ "${STAGE11_REVIEW_SHA}" =~ ^[a-f0-9]{40}$ ]]
[[ "$(dirname "${STAGE11_REVIEW_CHECKOUT}")" == "${stage11_project}/integration_stage11" ]]
[[ "$(realpath -e "${STAGE11_REVIEW_CHECKOUT}")" == "${STAGE11_REVIEW_CHECKOUT}" ]]
[[ "$(git -C "${STAGE11_REVIEW_CHECKOUT}" rev-parse HEAD)" == "${STAGE11_REVIEW_SHA}" ]]
[[ -z "$(git -C "${STAGE11_REVIEW_CHECKOUT}" status --porcelain)" ]]
[[ -z "$(git -C "${STAGE11_REVIEW_CHECKOUT}" symbolic-ref -q HEAD || true)" ]]
[[ "$(git -C "${STAGE11_CANDIDATE_CHECKOUT}" rev-parse HEAD)" == "${stage11_candidate_sha}" ]]
[[ -z "$(git -C "${STAGE11_CANDIDATE_CHECKOUT}" status --porcelain)" ]]
[[ -z "$(git -C "${STAGE11_CANDIDATE_CHECKOUT}" symbolic-ref -q HEAD || true)" ]]
git -C "${STAGE11_REVIEW_CHECKOUT}" merge-base --is-ancestor 125b3684a000ea79523f77049ae1a290b0da8109 HEAD
export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONHASHSEED=0
export LANG=C.UTF-8 LC_ALL=C.UTF-8 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export PYTHONPATH="${STAGE11_CANDIDATE_CHECKOUT}/src"
export STAGE11_REVIEW_OUTPUT="${stage11_project}/derived/controlled/stage11/independent_review/review_${STAGE11_REVIEW_SHA:0:12}_${SLURM_JOB_ID}"
install -d -m 0700 "${stage11_project}/derived/controlled/stage11/independent_review"
chmod 0600 "${stage11_project}/logs/slurm/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.out" "${stage11_project}/logs/slurm/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.err"
cd "${STAGE11_REVIEW_CHECKOUT}"
"${stage11_python}" -B review/stage11_independent/review.py
