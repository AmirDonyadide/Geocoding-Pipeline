#!/usr/bin/env bash
#SBATCH --job-name=safe-stage07-design
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --time=12:00:00
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${SLURM_JOB_NAME:?SLURM_JOB_NAME is required}"
: "${STAGE07_DESIGN_GIT_COMMIT:?submit with the exact pushed diagnostic commit}"
: "${STAGE07_DESIGN_INTEGRATION_ROOT:?submit with an exact detached worktree}"
: "${STAGE07_DESIGN_RUNTIME_ROOT:?submit with a new owner-only runtime root}"
: "${STAGE07_DESIGN_STAGE05_ROOT:?submit with accepted Stage 5 DEVELOPMENT}"
: "${STAGE07_DESIGN_STAGE06_ROOT:?submit with accepted Stage 6 DEVELOPMENT}"
: "${STAGE07_DESIGN_STAGE06_REVIEW_ROOT:?submit with accepted Stage 6 fixed-500 evidence}"
: "${STAGE07_DESIGN_PARSER_BUNDLE_ROOT:?submit with frozen public parser bundle}"
: "${STAGE07_DESIGN_PARSER_BUNDLE_FINGERPRINT:?submit with exact parser fingerprint}"
: "${STAGE07_DESIGN_OUTPUT_DIRECTORY:?submit with a new protected diagnostic path}"

readonly DATA_ROOT="$(realpath -e -- \
  "/work/footprint/donyadidegan/safe_geocoding_pipeline")"
readonly ACCEPTED_STAGE06_MANIFEST="e1da7b8ef04b65b1ece8e710720b57a8536841766fcf9de641f889b42eadd241"
readonly ACCEPTED_STAGE06_REVIEW_MANIFEST="1eda47b375a432788e5f8366ce73e5364fdf97efac1742bd95981a15b87c0fb1"
readonly LOG_ROOT="${DATA_ROOT}/logs/slurm"
readonly JOB_STDOUT="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.out"
readonly JOB_STDERR="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.err"
chmod 0600 "${JOB_STDOUT}" "${JOB_STDERR}"
[[ "$(stat -c %a "${JOB_STDOUT}")" == "600" ]]
[[ "$(stat -c %a "${JOB_STDERR}")" == "600" ]]

readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE07_DESIGN_INTEGRATION_ROOT}")"
readonly RUNTIME_ROOT="$(realpath -m -- "${STAGE07_DESIGN_RUNTIME_ROOT}")"
readonly STAGE05_ROOT="$(realpath -e -- "${STAGE07_DESIGN_STAGE05_ROOT}")"
readonly STAGE06_ROOT="$(realpath -e -- "${STAGE07_DESIGN_STAGE06_ROOT}")"
readonly STAGE06_REVIEW_ROOT="$(realpath -e -- "${STAGE07_DESIGN_STAGE06_REVIEW_ROOT}")"
readonly PARSER_BUNDLE_ROOT="$(realpath -e -- "${STAGE07_DESIGN_PARSER_BUNDLE_ROOT}")"
readonly OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE07_DESIGN_OUTPUT_DIRECTORY}")"
for controlled_path in \
  "${INTEGRATION_ROOT}" \
  "${RUNTIME_ROOT}" \
  "${STAGE05_ROOT}" \
  "${STAGE06_ROOT}" \
  "${STAGE06_REVIEW_ROOT}" \
  "${PARSER_BUNDLE_ROOT}" \
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

cd "${INTEGRATION_ROOT}"
readonly ACTUAL_COMMIT="$(git rev-parse HEAD)"
[[ "${ACTUAL_COMMIT}" == "${STAGE07_DESIGN_GIT_COMMIT}" ]] || {
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

STAGE07_INTEGRATION_ROOT="${INTEGRATION_ROOT}" \
STAGE07_RUNTIME_ROOT="${RUNTIME_ROOT}" \
STAGE07_PARSER_BUNDLE_ROOT="${PARSER_BUNDLE_ROOT}" \
STAGE07_PARSER_BUNDLE_FINGERPRINT="${STAGE07_DESIGN_PARSER_BUNDLE_FINGERPRINT}" \
  bash "${INTEGRATION_ROOT}/cluster/goethe_nhr/stage07_bootstrap_env.sh"

readonly PYTHON="${RUNTIME_ROOT}/venv/bin/python"
export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1
export PYTHONHASHSEED=0
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export LIBPOSTAL_DATA_DIR="${PARSER_BUNDLE_ROOT}/data/libpostal"
export LD_LIBRARY_PATH="${PARSER_BUNDLE_ROOT}/lib"
export PYTHONPATH="${PARSER_BUNDLE_ROOT}/python:${INTEGRATION_ROOT}/src"

echo "job_id=${SLURM_JOB_ID}"
echo "git_commit=${ACTUAL_COMMIT}"
echo "parser_bundle_fingerprint=${STAGE07_DESIGN_PARSER_BUNDLE_FINGERPRINT}"
echo "protected_parsing_network_calls=false"
"${PYTHON}" -m safe_geocoding_pipeline.preprocessing.stage07_design_cli \
  --stage05-output-directory "${STAGE05_ROOT}" \
  --stage06-output-directory "${STAGE06_ROOT}" \
  --expected-stage06-manifest-sha256 "${ACCEPTED_STAGE06_MANIFEST}" \
  --stage06-review-directory "${STAGE06_REVIEW_ROOT}" \
  --expected-stage06-review-manifest-sha256 "${ACCEPTED_STAGE06_REVIEW_MANIFEST}" \
  --parser-bundle-directory "${PARSER_BUNDLE_ROOT}" \
  --expected-parser-bundle-fingerprint "${STAGE07_DESIGN_PARSER_BUNDLE_FINGERPRINT}" \
  --output-directory "${OUTPUT_DIRECTORY}" \
  --execution-git-sha "${ACTUAL_COMMIT}" \
  --giant-timeout-seconds 900 \
  --giant-address-space-bytes 51539607552 \
  --fresh-process-timeout-seconds 1800 \
  --duckdb-memory-limit 8GB \
  --duckdb-threads 4

echo "STAGE07_DESIGN_DIAGNOSTIC_COMPLETE"
