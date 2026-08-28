#!/usr/bin/env bash
#SBATCH --job-name=safe-stage07-supervisor
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=180G
#SBATCH --time=12:00:00
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${SLURM_JOB_NAME:?SLURM_JOB_NAME is required}"
: "${STAGE07_SUPERVISOR_GIT_COMMIT:?submit with the exact pushed diagnostic commit}"
: "${STAGE07_SUPERVISOR_INTEGRATION_ROOT:?submit with an exact detached worktree}"
: "${STAGE07_SUPERVISOR_RUNTIME_ROOT:?submit with a new owner-only runtime root}"
: "${STAGE07_SUPERVISOR_STAGE05_ROOT:?submit with accepted Stage 5 DEVELOPMENT}"
: "${STAGE07_SUPERVISOR_STAGE06_ROOT:?submit with accepted Stage 6 DEVELOPMENT}"
: "${STAGE07_SUPERVISOR_PRIOR_DIAGNOSTIC_ROOT:?submit with immutable prior Stage 7 evidence}"
: "${STAGE07_SUPERVISOR_PARSER_BUNDLE_ROOT:?submit with frozen public parser bundle}"
: "${STAGE07_SUPERVISOR_PARSER_BUNDLE_FINGERPRINT:?submit with exact parser fingerprint}"
: "${STAGE07_SUPERVISOR_OUTPUT_DIRECTORY:?submit with a new protected diagnostic path}"

readonly DATA_ROOT="$(realpath -e -- \
  "/work/footprint/donyadidegan/safe_geocoding_pipeline")"
readonly ACCEPTED_STAGE06_MANIFEST="e1da7b8ef04b65b1ece8e710720b57a8536841766fcf9de641f889b42eadd241"
readonly PRIOR_DIAGNOSTIC_SHA="7b09fb79a6ef905c1e41d9387fc7ebfa5a24b257c8aee50d779f96aa47e32283"
readonly LOG_ROOT="${DATA_ROOT}/logs/slurm"
readonly JOB_STDOUT="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.out"
readonly JOB_STDERR="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.err"
chmod 0600 "${JOB_STDOUT}" "${JOB_STDERR}"
[[ "$(stat -c %a "${JOB_STDOUT}")" == "600" ]]
[[ "$(stat -c %a "${JOB_STDERR}")" == "600" ]]

readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE07_SUPERVISOR_INTEGRATION_ROOT}")"
readonly RUNTIME_ROOT="$(realpath -m -- "${STAGE07_SUPERVISOR_RUNTIME_ROOT}")"
readonly STAGE05_ROOT="$(realpath -e -- "${STAGE07_SUPERVISOR_STAGE05_ROOT}")"
readonly STAGE06_ROOT="$(realpath -e -- "${STAGE07_SUPERVISOR_STAGE06_ROOT}")"
readonly PRIOR_DIAGNOSTIC_ROOT="$(realpath -e -- "${STAGE07_SUPERVISOR_PRIOR_DIAGNOSTIC_ROOT}")"
readonly PARSER_BUNDLE_ROOT="$(realpath -e -- "${STAGE07_SUPERVISOR_PARSER_BUNDLE_ROOT}")"
readonly OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE07_SUPERVISOR_OUTPUT_DIRECTORY}")"
for controlled_path in \
  "${INTEGRATION_ROOT}" \
  "${RUNTIME_ROOT}" \
  "${STAGE05_ROOT}" \
  "${STAGE06_ROOT}" \
  "${PRIOR_DIAGNOSTIC_ROOT}" \
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
[[ "${ACTUAL_COMMIT}" == "${STAGE07_SUPERVISOR_GIT_COMMIT}" ]] || {
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
STAGE07_PARSER_BUNDLE_FINGERPRINT="${STAGE07_SUPERVISOR_PARSER_BUNDLE_FINGERPRINT}" \
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
echo "parser_bundle_fingerprint=${STAGE07_SUPERVISOR_PARSER_BUNDLE_FINGERPRINT}"
echo "candidate_timeout_exists=false"
echo "per_candidate_address_space_limit=none"
echo "protected_parsing_network_calls=false"
"${PYTHON}" -m safe_geocoding_pipeline.preprocessing.stage07_supervisor_cli \
  --stage05-output-directory "${STAGE05_ROOT}" \
  --stage06-output-directory "${STAGE06_ROOT}" \
  --expected-stage06-manifest-sha256 "${ACCEPTED_STAGE06_MANIFEST}" \
  --prior-diagnostic-directory "${PRIOR_DIAGNOSTIC_ROOT}" \
  --expected-prior-diagnostic-sha256 "${PRIOR_DIAGNOSTIC_SHA}" \
  --parser-bundle-directory "${PARSER_BUNDLE_ROOT}" \
  --expected-parser-bundle-fingerprint "${STAGE07_SUPERVISOR_PARSER_BUNDLE_FINGERPRINT}" \
  --output-directory "${OUTPUT_DIRECTORY}" \
  --execution-git-sha "${ACTUAL_COMMIT}" \
  --duckdb-memory-limit 8GB \
  --duckdb-threads 4

echo "STAGE07_SUPERVISOR_DIAGNOSTIC_COMPLETE"
