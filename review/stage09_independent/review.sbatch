#!/usr/bin/env bash
#SBATCH --job-name=safe-stage09-independent-review
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --no-requeue
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err
set -euo pipefail
umask 077
: "${SLURM_JOB_ID:?}"
: "${STAGE09_REVIEW_SHA:?}"
: "${STAGE09_REVIEW_CHECKOUT:?}"
readonly REVIEW_DATA_ROOT="$(realpath -e /work/footprint/donyadidegan/safe_geocoding_pipeline)"
readonly REVIEW_EXE=3e10ac7c1309c2636f35c0709fa283305d60d998
readonly REVIEW_CANDIDATE="${REVIEW_DATA_ROOT}/integration_stage09/${REVIEW_EXE}"
[[ "$(git -C "${STAGE09_REVIEW_CHECKOUT}" rev-parse HEAD)" == "${STAGE09_REVIEW_SHA}" ]]
[[ -z "$(git -C "${STAGE09_REVIEW_CHECKOUT}" status --porcelain)" ]]
[[ -z "$(git -C "${STAGE09_REVIEW_CHECKOUT}" symbolic-ref -q HEAD || true)" ]]
[[ "$(git -C "${REVIEW_CANDIDATE}" rev-parse HEAD)" == "${REVIEW_EXE}" ]]
[[ -z "$(git -C "${REVIEW_CANDIDATE}" status --porcelain)" ]]
export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONHASHSEED=0
export LANG=C.UTF-8 LC_ALL=C.UTF-8 OPENBLAS_NUM_THREADS=1
export PYTHONPATH="${REVIEW_CANDIDATE}/src"
export STAGE09_REVIEW_OUTPUT="${REVIEW_DATA_ROOT}/derived/controlled/stage09/independent_review/review_${STAGE09_REVIEW_SHA:0:12}_${SLURM_JOB_ID}"
install -d -m 0700 "${REVIEW_DATA_ROOT}/derived/controlled/stage09/independent_review"
chmod 0600 "${REVIEW_DATA_ROOT}/logs/slurm/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.out" "${REVIEW_DATA_ROOT}/logs/slurm/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.err"
"${REVIEW_DATA_ROOT}/runtimes/stage06/stage06_development_20260828T223804Z_f39047cc825d/venv/bin/python" -B "${STAGE09_REVIEW_CHECKOUT}/review/stage09_independent/review.py"
