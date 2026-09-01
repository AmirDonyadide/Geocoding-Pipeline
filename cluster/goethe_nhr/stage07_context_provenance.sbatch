#!/usr/bin/env bash
#SBATCH --job-name=safe-stage07-context
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
: "${STAGE07_CONTEXT_GIT_COMMIT:?exact pushed diagnostic commit is required}"
: "${STAGE07_CONTEXT_INTEGRATION_ROOT:?exact detached worktree is required}"
: "${STAGE07_CONTEXT_RUNTIME_ROOT:?validated read-only runtime is required}"
: "${STAGE07_CONTEXT_STAGE06_ROOT:?accepted Stage 6 root is required}"
: "${STAGE07_CONTEXT_PARSER_BUNDLE_ROOT:?frozen parser bundle is required}"
: "${STAGE07_CONTEXT_REVIEW_ROOT:?immutable review root is required}"
: "${STAGE07_CONTEXT_LIBPOSTAL_SOURCE_ROOT:?exact pinned libpostal source is required}"
: "${STAGE07_CONTEXT_OUTPUT_DIRECTORY:?new owner-only diagnostic output is required}"

readonly DATA_ROOT="$(realpath -e -- /work/footprint/donyadidegan/safe_geocoding_pipeline)"
readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE07_CONTEXT_INTEGRATION_ROOT}")"
readonly RUNTIME_ROOT="$(realpath -e -- "${STAGE07_CONTEXT_RUNTIME_ROOT}")"
readonly STAGE06_ROOT="$(realpath -e -- "${STAGE07_CONTEXT_STAGE06_ROOT}")"
readonly PARSER_BUNDLE_ROOT="$(realpath -e -- "${STAGE07_CONTEXT_PARSER_BUNDLE_ROOT}")"
readonly REVIEW_ROOT="$(realpath -e -- "${STAGE07_CONTEXT_REVIEW_ROOT}")"
readonly LIBPOSTAL_SOURCE_ROOT="$(realpath -e -- "${STAGE07_CONTEXT_LIBPOSTAL_SOURCE_ROOT}")"
readonly OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE07_CONTEXT_OUTPUT_DIRECTORY}")"

for controlled_path in \
  "${INTEGRATION_ROOT}" \
  "${RUNTIME_ROOT}" \
  "${STAGE06_ROOT}" \
  "${PARSER_BUNDLE_ROOT}" \
  "${REVIEW_ROOT}" \
  "${LIBPOSTAL_SOURCE_ROOT}" \
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

readonly LOG_ROOT="${DATA_ROOT}/logs/slurm"
readonly JOB_STDOUT="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.out"
readonly JOB_STDERR="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.err"
chmod 0600 "${JOB_STDOUT}" "${JOB_STDERR}"
[[ "$(stat -c %a "${JOB_STDOUT}")" == "600" ]]
[[ "$(stat -c %a "${JOB_STDERR}")" == "600" ]]

cd "${INTEGRATION_ROOT}"
[[ "$(git rev-parse HEAD)" == "${STAGE07_CONTEXT_GIT_COMMIT}" ]] || {
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
[[ -x "${PYTHON}" ]] || {
  echo "STAGE07_CONTEXT_RUNTIME_INVALID" >&2
  exit 1
}
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
readonly PYPPOSTAL_SOURCE="${PARSER_BUNDLE_ROOT}/python/postal/parser.py"
readonly LIBPOSTAL_HEADER="${LIBPOSTAL_SOURCE_ROOT}/src/libpostal.h"
readonly LIBPOSTAL_IMPLEMENTATION="${LIBPOSTAL_SOURCE_ROOT}/src/address_parser.c"
for private_file in \
  "${SELECTION}" \
  "${CLASSIFICATIONS}" \
  "${PYPPOSTAL_SOURCE}" \
  "${LIBPOSTAL_HEADER}" \
  "${LIBPOSTAL_IMPLEMENTATION}"; do
  [[ -f "${private_file}" && ! -L "${private_file}" ]]
  [[ "$(stat -c %a "${private_file}")" == "600" ]]
done

export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1
export PYTHONHASHSEED=0
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export PYTHONPATH="${INTEGRATION_ROOT}/src"

echo "job_id=${SLURM_JOB_ID}"
echo "git_commit=${STAGE07_CONTEXT_GIT_COMMIT}"
echo "scientific_scope=non_authoritative_metadata_only"
echo "parser_bundle_fingerprint=f3c6db7e9f11ab75b2207be773e946d531dbba763008d9f7e5036d8c923dc2ae"
echo "selection_fingerprint=1507900b27e4503eb33836c8465217092e9ffb8de2f1b6ef05026690be11a844"
echo "parser_calls=0"
echo "candidate_text_inspection=false"
echo "protected_network_calls=false"

"${PYTHON}" -m safe_geocoding_pipeline.preprocessing.stage07_context_cli \
  --stage06-output-directory "${STAGE06_ROOT}" \
  --parser-bundle-directory "${PARSER_BUNDLE_ROOT}" \
  --selection "${SELECTION}" \
  --classifications "${CLASSIFICATIONS}" \
  --pypostal-parser-source "${PYPPOSTAL_SOURCE}" \
  --libpostal-header-source "${LIBPOSTAL_HEADER}" \
  --libpostal-address-parser-source "${LIBPOSTAL_IMPLEMENTATION}" \
  --output "${OUTPUT_DIRECTORY}" \
  --execution-git-sha "${STAGE07_CONTEXT_GIT_COMMIT}"

echo "STAGE07_CONTEXT_PROVENANCE_DIAGNOSTIC_COMPLETE"
