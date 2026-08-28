#!/usr/bin/env bash
#SBATCH --job-name=safe-stage06-review
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${STAGE06_REVIEW_GIT_COMMIT:?exact pushed review commit required}"
: "${STAGE06_REVIEW_INTEGRATION_ROOT:?exact detached review worktree required}"
: "${STAGE06_REVIEW_PYTHON:?pinned Stage 6 Python required}"
: "${STAGE06_REVIEW_STAGE05_ROOT:?accepted Stage 5 root required}"
: "${STAGE06_REVIEW_STAGE06_ROOT:?authoritative Stage 6 root required}"
: "${STAGE06_REVIEW_FIXED_ROOT:?accepted fixed-500 root required}"
: "${STAGE06_REVIEW_CANDIDATE_REVIEW_ROOT:?authoritative Stage 6 review root required}"
: "${STAGE06_REVIEW_OUTPUT:?new independent-review output required}"

readonly DATA_ROOT="$(realpath -e -- \
  "/work/footprint/donyadidegan/safe_geocoding_pipeline")"
readonly LOG_ROOT="${DATA_ROOT}/logs/slurm"
readonly JOB_STDOUT="${LOG_ROOT}/safe-stage06-review_${SLURM_JOB_ID}.out"
readonly JOB_STDERR="${LOG_ROOT}/safe-stage06-review_${SLURM_JOB_ID}.err"

secure_job_logs() {
  chmod 0600 "${JOB_STDOUT}" "${JOB_STDERR}" 2>/dev/null || true
}
trap secure_job_logs EXIT
chmod 0600 "${JOB_STDOUT}" "${JOB_STDERR}"
[[ "$(stat -c %a "${JOB_STDOUT}")" == "600" ]]
[[ "$(stat -c %a "${JOB_STDERR}")" == "600" ]]

readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE06_REVIEW_INTEGRATION_ROOT}")"
readonly PYTHON_NAME="$(basename -- "${STAGE06_REVIEW_PYTHON}")"
readonly PYTHON_DIRECTORY="$(realpath -e -- "$(dirname -- "${STAGE06_REVIEW_PYTHON}")")"
readonly PYTHON="${PYTHON_DIRECTORY}/${PYTHON_NAME}"
readonly STAGE05_ROOT="$(realpath -e -- "${STAGE06_REVIEW_STAGE05_ROOT}")"
readonly STAGE06_ROOT="$(realpath -e -- "${STAGE06_REVIEW_STAGE06_ROOT}")"
readonly FIXED_ROOT="$(realpath -e -- "${STAGE06_REVIEW_FIXED_ROOT}")"
readonly CANDIDATE_REVIEW_ROOT="$(realpath -e -- \
  "${STAGE06_REVIEW_CANDIDATE_REVIEW_ROOT}")"
readonly REVIEW_OUTPUT="$(realpath -m -- "${STAGE06_REVIEW_OUTPUT}")"

[[ "${PYTHON_NAME}" == "python" && -x "${PYTHON}" ]] || {
  echo "STAGE06_REVIEW_PYTHON_INVALID" >&2
  exit 1
}

for protected_path in \
  "${INTEGRATION_ROOT}" \
  "${PYTHON}" \
  "${STAGE05_ROOT}" \
  "${STAGE06_ROOT}" \
  "${FIXED_ROOT}" \
  "${CANDIDATE_REVIEW_ROOT}" \
  "${REVIEW_OUTPUT}"; do
  [[ "${protected_path}" == "${DATA_ROOT}"/* ]] || {
    echo "STAGE06_REVIEW_CONTROLLED_PATH_REQUIRED" >&2
    exit 1
  }
  [[ "${protected_path,,}" != *holdout* ]] || {
    echo "HOLDOUT_ACCESS_PROHIBITED" >&2
    exit 1
  }
done

cd "${INTEGRATION_ROOT}"
[[ "$(git rev-parse HEAD)" == "${STAGE06_REVIEW_GIT_COMMIT}" ]]
[[ -z "$(git status --porcelain)" ]]
[[ "$(git symbolic-ref -q HEAD || true)" == "" ]]

export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1

"${PYTHON}" "${INTEGRATION_ROOT}/scripts/review_stage06_independent.py" review \
  --repository "${INTEGRATION_ROOT}" \
  --stage05-root "${STAGE05_ROOT}" \
  --stage06-root "${STAGE06_ROOT}" \
  --fixed-review-root "${FIXED_ROOT}" \
  --stage06-review-root "${CANDIDATE_REVIEW_ROOT}" \
  --output "${REVIEW_OUTPUT}" \
  --review-git-sha "${STAGE06_REVIEW_GIT_COMMIT}"

echo "STAGE06_INDEPENDENT_REVIEW_STRUCTURAL_PASS"
