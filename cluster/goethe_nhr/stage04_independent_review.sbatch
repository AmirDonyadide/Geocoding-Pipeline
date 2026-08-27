#!/usr/bin/env bash
#SBATCH --job-name=safe-stage04-review
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=6G
#SBATCH --time=00:30:00
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${STAGE04_REVIEW_GIT_COMMIT:?exact pushed review commit required}"
: "${STAGE04_REVIEW_INTEGRATION_ROOT:?exact detached review worktree required}"
: "${STAGE04_REVIEW_PYTHON:?pinned Stage 4 Python required}"
: "${STAGE04_REVIEW_STAGE03_ROOT:?accepted Stage 3 root required}"
: "${STAGE04_REVIEW_STAGE04_ROOT:?authoritative Stage 4 root required}"
: "${STAGE04_REVIEW_INPUT_BINDING:?authoritative input binding required}"
: "${STAGE04_REVIEW_FIXED_BUNDLE:?accepted fixed review bundle required}"
: "${STAGE04_REVIEW_STAGE04_REVIEW_ROOT:?authoritative Stage 4 review required}"
: "${STAGE04_REVIEW_OUTPUT:?new independent review output required}"

readonly DATA_ROOT="$(realpath -e -- "/work/footprint/donyadidegan/safe_geocoding_pipeline")"
readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE04_REVIEW_INTEGRATION_ROOT}")"
readonly PYTHON="$(realpath -e -- "${STAGE04_REVIEW_PYTHON}")"
readonly STAGE03_ROOT="$(realpath -e -- "${STAGE04_REVIEW_STAGE03_ROOT}")"
readonly STAGE04_ROOT="$(realpath -e -- "${STAGE04_REVIEW_STAGE04_ROOT}")"
readonly INPUT_BINDING="$(realpath -e -- "${STAGE04_REVIEW_INPUT_BINDING}")"
readonly FIXED_BUNDLE="$(realpath -e -- "${STAGE04_REVIEW_FIXED_BUNDLE}")"
readonly STAGE04_REVIEW_ROOT="$(realpath -e -- "${STAGE04_REVIEW_STAGE04_REVIEW_ROOT}")"
readonly REVIEW_OUTPUT="$(realpath -m -- "${STAGE04_REVIEW_OUTPUT}")"

for protected_path in \
  "${INTEGRATION_ROOT}" \
  "${PYTHON}" \
  "${STAGE03_ROOT}" \
  "${STAGE04_ROOT}" \
  "${INPUT_BINDING}" \
  "${FIXED_BUNDLE}" \
  "${STAGE04_REVIEW_ROOT}" \
  "${REVIEW_OUTPUT}"; do
  [[ "${protected_path}" == "${DATA_ROOT}"/* ]] || {
    echo "STAGE04_REVIEW_CONTROLLED_PATH_REQUIRED" >&2
    exit 1
  }
  [[ "${protected_path,,}" != *holdout* ]] || {
    echo "HOLDOUT_ACCESS_PROHIBITED" >&2
    exit 1
  }
done

cd "${INTEGRATION_ROOT}"
[[ "$(git rev-parse HEAD)" == "${STAGE04_REVIEW_GIT_COMMIT}" ]]
[[ -z "$(git status --porcelain)" ]]
[[ "$(git symbolic-ref -q HEAD || true)" == "" ]]

export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="${INTEGRATION_ROOT}/src"

"${PYTHON}" "${INTEGRATION_ROOT}/scripts/review_stage04_independent.py" \
  --repository "${INTEGRATION_ROOT}" \
  --stage03-root "${STAGE03_ROOT}" \
  --stage04-root "${STAGE04_ROOT}" \
  --input-binding "${INPUT_BINDING}" \
  --fixed-review-root "${FIXED_BUNDLE}" \
  --stage04-review-root "${STAGE04_REVIEW_ROOT}" \
  --output "${REVIEW_OUTPUT}" \
  --review-git-sha "${STAGE04_REVIEW_GIT_COMMIT}"

echo "STAGE04_INDEPENDENT_REVIEW_PASS"
