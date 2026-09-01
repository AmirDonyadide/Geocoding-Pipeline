#!/usr/bin/env bash
#SBATCH --job-name=safe-stage07-v2-readiness
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
: "${STAGE07_V2_GIT_COMMIT:?exact pushed diagnostic commit is required}"
: "${STAGE07_V2_INTEGRATION_ROOT:?clean detached worktree is required}"
: "${STAGE07_V2_RUNTIME_ROOT:?validated Stage 7 runtime is required}"
: "${STAGE07_V2_OUTPUT_DIRECTORY:?new owner-only output is required}"

readonly DATA_ROOT="$(realpath -e -- /work/footprint/donyadidegan/safe_geocoding_pipeline)"
readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE07_V2_INTEGRATION_ROOT}")"
readonly RUNTIME_ROOT="$(realpath -e -- "${STAGE07_V2_RUNTIME_ROOT}")"
readonly OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE07_V2_OUTPUT_DIRECTORY}")"
readonly STAGE06_FIXED="${DATA_ROOT}/derived/controlled/development_reporting/stage06_review_20260828T223804Z_f39047cc825d/stage06_fixed500_verification.parquet"
readonly STAGE07_ROOT="${DATA_ROOT}/derived/controlled/stage07/development/stage07_development_4a5f749"
readonly REVIEW_ROOT="${DATA_ROOT}/derived/controlled/stage07/review/stage07_review_4a5f749"
readonly QUALITY_ROOT="${DATA_ROOT}/derived/controlled/stage07/quality_diagnostics/stage07_quality_5f324fd_attempt2"
readonly ELIGIBILITY_ROOT="${DATA_ROOT}/derived/controlled/stage07/eligibility_audits/stage07_eligibility_aa15b1c_attempt1"

for controlled_path in \
  "${INTEGRATION_ROOT}" \
  "${RUNTIME_ROOT}" \
  "${STAGE06_FIXED}" \
  "${STAGE07_ROOT}" \
  "${REVIEW_ROOT}" \
  "${QUALITY_ROOT}" \
  "${ELIGIBILITY_ROOT}" \
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
[[ "$(git rev-parse HEAD)" == "${STAGE07_V2_GIT_COMMIT}" ]]
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

mapfile -d '' REGISTRY_FILES < <(
  find "${STAGE07_ROOT}/registry/data" -maxdepth 1 -type f \
    -name 'part-*.parquet' -print0 | sort -z
)
[[ "${#REGISTRY_FILES[@]}" -eq 13 ]]

echo "job_id=${SLURM_JOB_ID}"
echo "git_commit=${STAGE07_V2_GIT_COMMIT}"
echo "scope=existing_authorized_120_plus_metadata_only_fixed500"
echo "new_semantic_candidates_inspected=0"
echo "parser_calls=0"
echo "network_calls=0"

"${PYTHON}" -m safe_geocoding_pipeline.preprocessing.stage07_v2_readiness_cli \
  --stage06-fixed500 "${STAGE06_FIXED}" \
  --stage07-fixed500 "${REVIEW_ROOT}/stage07_fixed500_verification.parquet" \
  --selection "${REVIEW_ROOT}/stage07_qualitative_selection.parquet" \
  --classifications "${REVIEW_ROOT}/stage07_qualitative_classifications.json" \
  --root-cause "${QUALITY_ROOT}/stage07_quality_root_cause_cases.parquet" \
  --eligibility "${ELIGIBILITY_ROOT}/stage07_candidate_country_eligibility.parquet" \
  --stage07-registry "${REGISTRY_FILES[@]}" \
  --output "${OUTPUT_DIRECTORY}" \
  --execution-git-sha "${STAGE07_V2_GIT_COMMIT}"

echo "STAGE07_V2_READINESS_DESIGN_AUDIT_COMPLETE"
