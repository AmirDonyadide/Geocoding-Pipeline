#!/usr/bin/env bash
#SBATCH --job-name=safe-stage07-eligibility
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${SLURM_JOB_NAME:?SLURM_JOB_NAME is required}"
: "${STAGE07_ELIGIBILITY_GIT_COMMIT:?exact pushed diagnostic commit is required}"
: "${STAGE07_ELIGIBILITY_INTEGRATION_ROOT:?clean detached worktree is required}"
: "${STAGE07_ELIGIBILITY_RUNTIME_ROOT:?validated Stage 7 runtime is required}"
: "${STAGE07_ELIGIBILITY_STAGE06_ROOT:?accepted Stage 6 root is required}"
: "${STAGE07_ELIGIBILITY_STAGE07_ROOT:?immutable Stage 7 root is required}"
: "${STAGE07_ELIGIBILITY_STAGE07_MANIFEST_SHA256:?Stage 7 manifest hash is required}"
: "${STAGE07_ELIGIBILITY_REVIEW_ROOT:?immutable review root is required}"
: "${STAGE07_ELIGIBILITY_OUTPUT_DIRECTORY:?new audit output is required}"

readonly DATA_ROOT="$(realpath -e -- /work/footprint/donyadidegan/safe_geocoding_pipeline)"
readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE07_ELIGIBILITY_INTEGRATION_ROOT}")"
readonly RUNTIME_ROOT="$(realpath -e -- "${STAGE07_ELIGIBILITY_RUNTIME_ROOT}")"
readonly STAGE06_ROOT="$(realpath -e -- "${STAGE07_ELIGIBILITY_STAGE06_ROOT}")"
readonly STAGE07_ROOT="$(realpath -e -- "${STAGE07_ELIGIBILITY_STAGE07_ROOT}")"
readonly REVIEW_ROOT="$(realpath -e -- "${STAGE07_ELIGIBILITY_REVIEW_ROOT}")"
readonly OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE07_ELIGIBILITY_OUTPUT_DIRECTORY}")"

for controlled_path in \
  "${INTEGRATION_ROOT}" \
  "${RUNTIME_ROOT}" \
  "${STAGE06_ROOT}" \
  "${STAGE07_ROOT}" \
  "${REVIEW_ROOT}" \
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
[[ "$(git rev-parse HEAD)" == "${STAGE07_ELIGIBILITY_GIT_COMMIT}" ]] || {
  echo "STAGE07_GIT_COMMIT_MISMATCH" >&2
  exit 1
}
[[ -z "$(git status --porcelain)" ]] || {
  echo "STAGE07_WORKTREE_NOT_CLEAN" >&2
  exit 1
}
[[ "$(git symbolic-ref -q HEAD || true)" == "" ]] || {
  echo "STAGE07_WORKTREE_NOT_DETACHED" >&2
  exit 1
}

readonly PYTHON="${RUNTIME_ROOT}/venv/bin/python"
[[ -x "${PYTHON}" ]]
"${PYTHON}" - <<'PY'
import platform
import duckdb
import pyarrow

assert platform.python_version() == "3.14.3"
assert duckdb.__version__ == "1.5.5"
assert pyarrow.__version__ == "25.0.0"
PY

readonly SELECTION="${REVIEW_ROOT}/stage07_qualitative_selection.parquet"
readonly CLASSIFICATIONS="${REVIEW_ROOT}/stage07_qualitative_classifications.json"
readonly ELIGIBILITY_MANIFEST="${INTEGRATION_ROOT}/docs/scientific_assets/stage07_parser_country_eligibility_v1.json"
for protected_file in "${SELECTION}" "${CLASSIFICATIONS}"; do
  [[ -f "${protected_file}" && ! -L "${protected_file}" ]]
  [[ "$(stat -c %a "${protected_file}")" == "600" ]]
done
[[ -f "${ELIGIBILITY_MANIFEST}" && ! -L "${ELIGIBILITY_MANIFEST}" ]]

export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1
export PYTHONHASHSEED=0
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export PYTHONPATH="${INTEGRATION_ROOT}/src"

echo "job_id=${SLURM_JOB_ID}"
echo "git_commit=${STAGE07_ELIGIBILITY_GIT_COMMIT}"
echo "scientific_scope=non_authoritative_metadata_only"
echo "candidate_text_read=false"
echo "parser_components_read=false"
echo "parser_calls=0"
echo "network_calls=0"

"${PYTHON}" -m safe_geocoding_pipeline.preprocessing.stage07_eligibility_cli \
  --stage06-output-directory "${STAGE06_ROOT}" \
  --stage07-output-directory "${STAGE07_ROOT}" \
  --stage07-manifest-sha256 "${STAGE07_ELIGIBILITY_STAGE07_MANIFEST_SHA256}" \
  --selection "${SELECTION}" \
  --classifications "${CLASSIFICATIONS}" \
  --eligibility-manifest "${ELIGIBILITY_MANIFEST}" \
  --output "${OUTPUT_DIRECTORY}" \
  --execution-git-sha "${STAGE07_ELIGIBILITY_GIT_COMMIT}"

echo "STAGE07_COUNTRY_ELIGIBILITY_AUDIT_COMPLETE"
