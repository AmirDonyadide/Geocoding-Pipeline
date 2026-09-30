#!/usr/bin/env bash
#SBATCH --job-name=safe-stage10-final-rereview
#SBATCH --partition=general1
#SBATCH --account=footprint
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=12:00:00
#SBATCH --no-requeue
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err
set -euo pipefail
umask 077
: "${SLURM_JOB_ID:?scheduled review required}"
: "${STAGE10_REVIEW_SHA:?exact pushed review SHA required}"
: "${STAGE10_REVIEW_CHECKOUT:?clean detached review checkout required}"
readonly review_root="$(realpath -e /work/footprint/donyadidegan/safe_geocoding_pipeline)"
readonly candidate_sha=cf9e0fe4c12eb85f78051904c636ad084d87a541
readonly candidate_checkout="${review_root}/integration_stage10/stage10_development_20260928T081247Z_cf9e0fe4c12e"
readonly review_python="${review_root}/runtimes/stage06/stage06_development_20260828T223804Z_f39047cc825d/venv/bin/python"
[[ "${SLURM_RESTART_COUNT:-0}" == 0 && "${SLURM_CPUS_PER_TASK}" == 4 ]]
[[ "${STAGE10_REVIEW_SHA}" =~ ^[a-f0-9]{40}$ ]]
[[ "$(realpath -e "${STAGE10_REVIEW_CHECKOUT}")" == "${STAGE10_REVIEW_CHECKOUT}" ]]
[[ "$(dirname "${STAGE10_REVIEW_CHECKOUT}")" == "${review_root}/integration_stage10" ]]
[[ "$(git -C "${STAGE10_REVIEW_CHECKOUT}" rev-parse HEAD)" == "${STAGE10_REVIEW_SHA}" ]]
[[ -z "$(git -C "${STAGE10_REVIEW_CHECKOUT}" status --porcelain)" ]]
[[ -z "$(git -C "${STAGE10_REVIEW_CHECKOUT}" symbolic-ref -q HEAD || true)" ]]
[[ "$(git -C "${candidate_checkout}" rev-parse HEAD)" == "${candidate_sha}" ]]
[[ -z "$(git -C "${candidate_checkout}" status --porcelain)" ]]
[[ -z "$(git -C "${candidate_checkout}" symbolic-ref -q HEAD || true)" ]]
git -C "${STAGE10_REVIEW_CHECKOUT}" diff --quiet "${candidate_sha}" HEAD -- src tests cluster scripts spec
git -C "${STAGE10_REVIEW_CHECKOUT}" merge-base --is-ancestor "${candidate_sha}" 186d4220cbdede6556ce81d16504949215a6f034
git -C "${STAGE10_REVIEW_CHECKOUT}" merge-base --is-ancestor 186d4220cbdede6556ce81d16504949215a6f034 b29b230dece88404712105fc485c41411e12ba5d
git -C "${STAGE10_REVIEW_CHECKOUT}" merge-base --is-ancestor b29b230dece88404712105fc485c41411e12ba5d HEAD
git -C "${STAGE10_REVIEW_CHECKOUT}" merge-base --is-ancestor bced5920b5234e5598f1d0b3a4cb1269780862f4 HEAD
export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONHASHSEED=0
export LANG=C.UTF-8 LC_ALL=C.UTF-8 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export PYTHONPATH="${candidate_checkout}/src"
export STAGE10_REVIEW_OUTPUT="${review_root}/derived/controlled/stage10/independent_review/rereview_${STAGE10_REVIEW_SHA:0:12}_${SLURM_JOB_ID}"
install -d -m 0700 "${review_root}/derived/controlled/stage10/independent_review"
chmod 0600 "${review_root}/logs/slurm/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.out" "${review_root}/logs/slurm/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.err"
cd "${STAGE10_REVIEW_CHECKOUT}"
"${review_python}" -B "${STAGE10_REVIEW_CHECKOUT}/review/stage10_independent/rereview.py"
