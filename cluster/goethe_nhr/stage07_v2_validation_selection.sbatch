#!/usr/bin/env bash
#SBATCH --job-name=safe-stage07-v2-selection
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${SLURM_JOB_NAME:?SLURM_JOB_NAME is required}"
: "${STAGE07_V2_SELECTION_GIT_COMMIT:?exact pushed selection commit is required}"
: "${STAGE07_V2_SELECTION_INTEGRATION_ROOT:?clean detached worktree is required}"
: "${STAGE07_V2_SELECTION_RUNTIME_ROOT:?validated Stage 7 runtime is required}"
: "${STAGE07_V2_SELECTION_STAGE07_ROOT:?immutable Stage 7 root is required}"
: "${STAGE07_V2_SELECTION_STAGE07_MANIFEST_SHA256:?Stage 7 manifest hash is required}"
: "${STAGE07_V2_SELECTION_OUTPUT_DIRECTORY:?new owner-only output is required}"

readonly DATA_ROOT="$(realpath -e -- /work/footprint/donyadidegan/safe_geocoding_pipeline)"
readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE07_V2_SELECTION_INTEGRATION_ROOT}")"
readonly RUNTIME_ROOT="$(realpath -e -- "${STAGE07_V2_SELECTION_RUNTIME_ROOT}")"
readonly STAGE07_ROOT="$(realpath -e -- "${STAGE07_V2_SELECTION_STAGE07_ROOT}")"
readonly OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE07_V2_SELECTION_OUTPUT_DIRECTORY}")"
readonly STAGE06_FIXED="${DATA_ROOT}/derived/controlled/development_reporting/stage06_review_20260828T223804Z_f39047cc825d/stage06_fixed500_verification.parquet"
readonly REVIEW_ROOT="${DATA_ROOT}/derived/controlled/stage07/review/stage07_review_4a5f749"
readonly ELIGIBILITY_ROOT="${DATA_ROOT}/derived/controlled/stage07/eligibility_audits/stage07_eligibility_aa15b1c_attempt1"

for controlled_path in \
  "${INTEGRATION_ROOT}" \
  "${RUNTIME_ROOT}" \
  "${STAGE06_FIXED}" \
  "${REVIEW_ROOT}" \
  "${ELIGIBILITY_ROOT}" \
  "${STAGE07_ROOT}" \
  "${OUTPUT_DIRECTORY}"; do
  [[ "${controlled_path}" == "${DATA_ROOT}"/* ]] || {
    echo "STAGE07_CONTROLLED_PATH_REQUIRED" >&2
    exit 1
  }
  [[ "${controlled_path,,}" != *holdout* ]] || {
    echo "HOLDOUT_ACCESS_PROHIBITED" >&2
    exit 1
  }
done
[[ ! -e "${OUTPUT_DIRECTORY}" ]]

readonly LOG_ROOT="${DATA_ROOT}/logs/slurm"
readonly JOB_STDOUT="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.out"
readonly JOB_STDERR="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.err"
chmod 0600 "${JOB_STDOUT}" "${JOB_STDERR}"
[[ "$(stat -c %a "${JOB_STDOUT}")" == "600" ]]
[[ "$(stat -c %a "${JOB_STDERR}")" == "600" ]]

cd "${INTEGRATION_ROOT}"
[[ "$(git rev-parse HEAD)" == "${STAGE07_V2_SELECTION_GIT_COMMIT}" ]]
[[ -z "$(git status --porcelain)" ]]
[[ "$(git symbolic-ref -q HEAD || true)" == "" ]]

readonly PYTHON="${RUNTIME_ROOT}/venv/bin/python"
[[ -x "${PYTHON}" ]]
export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1
export PYTHONHASHSEED=0
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export PYTHONPATH="${INTEGRATION_ROOT}/src"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

echo "job_id=${SLURM_JOB_ID}"
echo "git_commit=${STAGE07_V2_SELECTION_GIT_COMMIT}"
echo "scope=machine_only_604_untouched_fixed500_candidates"
echo "semantic_inspection=false"
echo "candidate_rank_uses_text=false"
echo "parser_calls=0"
echo "network_calls=0"

"${PYTHON}" -B \
  -m safe_geocoding_pipeline.preprocessing.stage07_v2_validation_selection_cli \
  --stage06-fixed500 "${STAGE06_FIXED}" \
  --existing-selection "${REVIEW_ROOT}/stage07_qualitative_selection.parquet" \
  --eligibility "${ELIGIBILITY_ROOT}/stage07_candidate_country_eligibility.parquet" \
  --stage07-output-directory "${STAGE07_ROOT}" \
  --stage07-manifest-sha256 "${STAGE07_V2_SELECTION_STAGE07_MANIFEST_SHA256}" \
  --output "${OUTPUT_DIRECTORY}" \
  --execution-git-sha "${STAGE07_V2_SELECTION_GIT_COMMIT}"

echo "STAGE07_V2_VALIDATION_SELECTION_FREEZE_COMPLETE"
