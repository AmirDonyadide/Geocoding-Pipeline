#!/usr/bin/env bash
#SBATCH --job-name=safe-stage05-review
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:45:00
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${STAGE05_REVIEW_GIT_COMMIT:?exact pushed review commit required}"
: "${STAGE05_REVIEW_INTEGRATION_ROOT:?exact detached review worktree required}"
: "${STAGE05_REVIEW_PYTHON:?pinned Stage 5 Python required}"
: "${STAGE05_REVIEW_STAGE04_ROOT:?accepted Stage 4 root required}"
: "${STAGE05_REVIEW_STAGE05_ROOT:?authoritative Stage 5 root required}"
: "${STAGE05_REVIEW_INPUT_BINDING:?authoritative Stage 5 binding required}"
: "${STAGE05_REVIEW_FIXED_BUNDLE:?accepted fixed review bundle required}"
: "${STAGE05_REVIEW_STAGE05_REVIEW_ROOT:?authoritative Stage 5 review required}"
: "${STAGE05_REVIEW_OUTPUT:?new independent review output required}"

readonly DATA_ROOT="$(realpath -e -- \
  "/work/footprint/donyadidegan/safe_geocoding_pipeline")"
readonly JOB_LOG_ROOT="${DATA_ROOT}/logs/slurm"
secure_job_logs() {
  chmod 600 \
    "${JOB_LOG_ROOT}/safe-stage05-review_${SLURM_JOB_ID}.out" \
    "${JOB_LOG_ROOT}/safe-stage05-review_${SLURM_JOB_ID}.err" 2>/dev/null || true
}
trap secure_job_logs EXIT

readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE05_REVIEW_INTEGRATION_ROOT}")"
readonly PYTHON_NAME="$(basename -- "${STAGE05_REVIEW_PYTHON}")"
readonly PYTHON_DIRECTORY="$(realpath -e -- "$(dirname -- "${STAGE05_REVIEW_PYTHON}")")"
readonly PYTHON="${PYTHON_DIRECTORY}/${PYTHON_NAME}"
readonly STAGE04_ROOT="$(realpath -e -- "${STAGE05_REVIEW_STAGE04_ROOT}")"
readonly STAGE05_ROOT="$(realpath -e -- "${STAGE05_REVIEW_STAGE05_ROOT}")"
readonly INPUT_BINDING="$(realpath -e -- "${STAGE05_REVIEW_INPUT_BINDING}")"
readonly FIXED_BUNDLE="$(realpath -e -- "${STAGE05_REVIEW_FIXED_BUNDLE}")"
readonly STAGE05_REVIEW_ROOT="$(realpath -e -- "${STAGE05_REVIEW_STAGE05_REVIEW_ROOT}")"
readonly REVIEW_OUTPUT="$(realpath -m -- "${STAGE05_REVIEW_OUTPUT}")"

[[ "${PYTHON_NAME}" == "python" && -x "${PYTHON}" ]] || {
  echo "STAGE05_REVIEW_PYTHON_INVALID" >&2
  exit 1
}

for protected_path in \
  "${INTEGRATION_ROOT}" \
  "${PYTHON}" \
  "${STAGE04_ROOT}" \
  "${STAGE05_ROOT}" \
  "${INPUT_BINDING}" \
  "${FIXED_BUNDLE}" \
  "${STAGE05_REVIEW_ROOT}" \
  "${REVIEW_OUTPUT}"; do
  [[ "${protected_path}" == "${DATA_ROOT}"/* ]] || {
    echo "STAGE05_REVIEW_CONTROLLED_PATH_REQUIRED" >&2
    exit 1
  }
  [[ "${protected_path,,}" != *holdout* ]] || {
    echo "HOLDOUT_ACCESS_PROHIBITED" >&2
    exit 1
  }
done

cd "${INTEGRATION_ROOT}"
[[ "$(git rev-parse HEAD)" == "${STAGE05_REVIEW_GIT_COMMIT}" ]]
[[ -z "$(git status --porcelain)" ]]
[[ "$(git symbolic-ref -q HEAD || true)" == "" ]]

export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="${INTEGRATION_ROOT}/src"

"${PYTHON}" "${INTEGRATION_ROOT}/scripts/review_stage05_independent.py" \
  --repository "${INTEGRATION_ROOT}" \
  --stage04-root "${STAGE04_ROOT}" \
  --stage05-root "${STAGE05_ROOT}" \
  --stage05-input-binding "${INPUT_BINDING}" \
  --fixed-review-root "${FIXED_BUNDLE}" \
  --stage05-review-root "${STAGE05_REVIEW_ROOT}" \
  --output "${REVIEW_OUTPUT}" \
  --review-git-sha "${STAGE05_REVIEW_GIT_COMMIT}"

echo "STAGE05_INDEPENDENT_REVIEW_STRUCTURAL_PASS"
