#!/usr/bin/env bash
#SBATCH --job-name=safe-stage07-quality
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=180G
#SBATCH --time=04:00:00
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${SLURM_JOB_NAME:?SLURM_JOB_NAME is required}"
: "${STAGE07_QUALITY_GIT_COMMIT:?exact pushed diagnostic commit is required}"
: "${STAGE07_QUALITY_INTEGRATION_ROOT:?exact detached worktree is required}"
: "${STAGE07_QUALITY_RUNTIME_ROOT:?new owner-only runtime root is required}"
: "${STAGE07_QUALITY_PARSER_BUNDLE_ROOT:?frozen parser bundle root is required}"
: "${STAGE07_QUALITY_SELECTION:?immutable qualitative selection is required}"
: "${STAGE07_QUALITY_CLASSIFICATIONS:?owner-only classifications are required}"
: "${STAGE07_QUALITY_COMMENTS:?owner-only abstract comments are required}"
: "${STAGE07_QUALITY_STAGE07_ROOT:?immutable authoritative Stage 7 root is required}"
: "${STAGE07_QUALITY_OUTPUT_DIRECTORY:?new owner-only diagnostic path is required}"

readonly DATA_ROOT="$(realpath -e -- /work/footprint/donyadidegan/safe_geocoding_pipeline)"
readonly PARSER_BUNDLE_FINGERPRINT="f3c6db7e9f11ab75b2207be773e946d531dbba763008d9f7e5036d8c923dc2ae"
readonly SELECTION_FINGERPRINT="1507900b27e4503eb33836c8465217092e9ffb8de2f1b6ef05026690be11a844"
readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE07_QUALITY_INTEGRATION_ROOT}")"
readonly RUNTIME_ROOT="$(realpath -m -- "${STAGE07_QUALITY_RUNTIME_ROOT}")"
readonly SOURCE_PARSER_BUNDLE_ROOT="$(realpath -e -- "${STAGE07_QUALITY_PARSER_BUNDLE_ROOT}")"
readonly PARSER_BUNDLE_ROOT="$(realpath -m -- "${RUNTIME_ROOT}.parser_bundle_view")"
readonly SELECTION="$(realpath -e -- "${STAGE07_QUALITY_SELECTION}")"
readonly CLASSIFICATIONS="$(realpath -e -- "${STAGE07_QUALITY_CLASSIFICATIONS}")"
readonly COMMENTS="$(realpath -e -- "${STAGE07_QUALITY_COMMENTS}")"
readonly STAGE07_ROOT="$(realpath -e -- "${STAGE07_QUALITY_STAGE07_ROOT}")"
readonly OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE07_QUALITY_OUTPUT_DIRECTORY}")"

for controlled_path in \
  "${INTEGRATION_ROOT}" \
  "${RUNTIME_ROOT}" \
  "${SOURCE_PARSER_BUNDLE_ROOT}" \
  "${PARSER_BUNDLE_ROOT}" \
  "${SELECTION}" \
  "${CLASSIFICATIONS}" \
  "${COMMENTS}" \
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

readonly LOG_ROOT="${DATA_ROOT}/logs/slurm"
readonly JOB_STDOUT="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.out"
readonly JOB_STDERR="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.err"
chmod 0600 "${JOB_STDOUT}" "${JOB_STDERR}"
[[ "$(stat -c %a "${JOB_STDOUT}")" == "600" ]]
[[ "$(stat -c %a "${JOB_STDERR}")" == "600" ]]
[[ "$(stat -c %a "${SELECTION}")" == "600" ]]
[[ "$(stat -c %a "${CLASSIFICATIONS}")" == "600" ]]
[[ "$(stat -c %a "${COMMENTS}")" == "600" ]]

cd "${INTEGRATION_ROOT}"
[[ "$(git rev-parse HEAD)" == "${STAGE07_QUALITY_GIT_COMMIT}" ]] || {
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

[[ ! -e "${PARSER_BUNDLE_ROOT}" ]] || {
  echo "STAGE07_PARSER_BUNDLE_VIEW_COLLISION" >&2
  exit 1
}
install -d -m 0700 "${PARSER_BUNDLE_ROOT}"
while IFS= read -r -d '' source_path; do
  relative_path="${source_path#"${SOURCE_PARSER_BUNDLE_ROOT}"/}"
  [[ "/${relative_path}/" != */__pycache__/* ]] || continue
  target_path="${PARSER_BUNDLE_ROOT}/${relative_path}"
  if [[ -L "${source_path}" ]]; then
    echo "STAGE07_SOURCE_BUNDLE_SYMLINK_PROHIBITED" >&2
    exit 1
  elif [[ -d "${source_path}" ]]; then
    install -d -m 0700 "${target_path}"
  elif [[ -f "${source_path}" && ! -L "${source_path}" ]]; then
    [[ "$(stat -c %a "${source_path}")" == "600" ]] || {
      echo "STAGE07_SOURCE_BUNDLE_FILE_MODE_INVALID" >&2
      exit 1
    }
    cp --reflink=auto --preserve=mode,timestamps -- \
      "${source_path}" "${target_path}"
  else
    echo "STAGE07_SOURCE_BUNDLE_TOPOLOGY_INVALID" >&2
    exit 1
  fi
done < <(find "${SOURCE_PARSER_BUNDLE_ROOT}" -mindepth 1 -print0)
[[ -z "$(find "${PARSER_BUNDLE_ROOT}" -type d ! -perm 0700 -print -quit)" ]]
[[ -z "$(find "${PARSER_BUNDLE_ROOT}" -type f ! -perm 0600 -print -quit)" ]]
[[ -z "$(find "${PARSER_BUNDLE_ROOT}" -name __pycache__ -print -quit)" ]]

export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1
export PYTHONHASHSEED=0
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
STAGE07_INTEGRATION_ROOT="${INTEGRATION_ROOT}" \
STAGE07_RUNTIME_ROOT="${RUNTIME_ROOT}" \
STAGE07_PARSER_BUNDLE_ROOT="${PARSER_BUNDLE_ROOT}" \
STAGE07_PARSER_BUNDLE_FINGERPRINT="${PARSER_BUNDLE_FINGERPRINT}" \
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

mapfile -d '' REGISTRY_FILES < <(
  find "${STAGE07_ROOT}/registry/data" -maxdepth 1 -type f \
    -name 'part-*.parquet' -print0 | sort -z
)
[[ "${#REGISTRY_FILES[@]}" -eq 13 ]] || {
  echo "STAGE07_REGISTRY_TOPOLOGY_MISMATCH" >&2
  exit 1
}

echo "job_id=${SLURM_JOB_ID}"
echo "git_commit=${STAGE07_QUALITY_GIT_COMMIT}"
echo "parser_bundle_fingerprint=${PARSER_BUNDLE_FINGERPRINT}"
echo "parser_bundle_view_excludes_runtime_cache=true"
echo "source_parser_bundle_modified=false"
echo "selection_fingerprint=${SELECTION_FINGERPRINT}"
echo "diagnostic_cases=18"
echo "requested_memory_gib=180"
echo "parser_concurrency=one_synchronous_supervised_child"
echo "per_candidate_address_space_limit=none"
echo "per_candidate_timeout=none"
echo "protected_parsing_network_calls=false"

"${PYTHON}" -m safe_geocoding_pipeline.preprocessing.stage07_quality_cli \
  --selection "${SELECTION}" \
  --classifications "${CLASSIFICATIONS}" \
  --comments "${COMMENTS}" \
  --stage07-registry "${REGISTRY_FILES[@]}" \
  --output "${OUTPUT_DIRECTORY}" \
  --execution-git-sha "${STAGE07_QUALITY_GIT_COMMIT}"

echo "STAGE07_QUALITY_ROOT_CAUSE_DIAGNOSTIC_COMPLETE"
