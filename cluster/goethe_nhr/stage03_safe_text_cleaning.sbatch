#!/usr/bin/env bash
#SBATCH --job-name=safe-stage03
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=3-00:00:00
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${STAGE03_GIT_COMMIT:?submit with the exact pushed Stage 3 commit}"
: "${STAGE03_INTEGRATION_ROOT:?submit with an exact detached worktree}"
: "${STAGE03_RUNTIME_ROOT:?submit with an owner-only isolated runtime root}"
: "${STAGE03_STAGE02_ROOT:?submit with the accepted Stage 2 DEVELOPMENT bundle}"
: "${STAGE03_STAGE02_MANIFEST_SHA256:?submit with the Stage 2 manifest SHA-256}"
: "${STAGE03_STAGE02_LOGICAL_FINGERPRINT:?submit with the Stage 2 logical fingerprint}"
: "${STAGE03_STAGE02_SCHEMA_FINGERPRINT:?submit with the Stage 2 schema fingerprint}"
: "${STAGE03_BENCHMARK_FINGERPRINT:?submit with the accepted benchmark fingerprint}"
: "${STAGE03_EXPECTED_ROWS:?submit with the exact DEVELOPMENT row count}"
: "${STAGE03_INPUT_BINDING:?submit with a new protected binding path}"
: "${STAGE03_OUTPUT_DIRECTORY:?submit with a new protected Stage 3 path}"
: "${STAGE03_DEVELOPMENT_REVIEW_BUNDLE:?submit with the accepted fixed review bundle}"
: "${STAGE03_DEVELOPMENT_REVIEW_MANIFEST_SHA256:?submit with its exact manifest SHA-256}"
: "${STAGE03_REVIEW_SUBSET_FINGERPRINT:?submit with the fixed 500-row fingerprint}"
: "${STAGE03_REVIEW_OUTPUT_DIRECTORY:?submit with a new Stage 3 review path}"
: "${STAGE03_V1_OUTPUT_DIRECTORY:?submit with the immutable v1 Stage 3 path}"
: "${STAGE03_V1_MANIFEST_SHA256:?submit with the exact v1 manifest SHA-256}"

readonly DATA_ROOT="/work/footprint/donyadidegan/safe_geocoding_pipeline"
readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE03_INTEGRATION_ROOT}")"
readonly RUNTIME_ROOT="$(realpath -m -- "${STAGE03_RUNTIME_ROOT}")"
readonly STAGE02_ROOT="$(realpath -e -- "${STAGE03_STAGE02_ROOT}")"
readonly INPUT_BINDING="$(realpath -m -- "${STAGE03_INPUT_BINDING}")"
readonly OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE03_OUTPUT_DIRECTORY}")"
readonly REVIEW_BUNDLE="$(realpath -e -- "${STAGE03_DEVELOPMENT_REVIEW_BUNDLE}")"
readonly REVIEW_OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE03_REVIEW_OUTPUT_DIRECTORY}")"
readonly V1_OUTPUT_DIRECTORY="$(realpath -e -- "${STAGE03_V1_OUTPUT_DIRECTORY}")"

for protected_path in \
  "${STAGE02_ROOT}" \
  "${INPUT_BINDING}" \
  "${OUTPUT_DIRECTORY}" \
  "${REVIEW_BUNDLE}" \
  "${REVIEW_OUTPUT_DIRECTORY}" \
  "${V1_OUTPUT_DIRECTORY}"; do
  [[ "${protected_path,,}" != *holdout* ]] || {
    echo "HOLDOUT_ACCESS_PROHIBITED" >&2
    exit 1
  }
done

cd "${INTEGRATION_ROOT}"
readonly ACTUAL_COMMIT="$(git rev-parse HEAD)"
[[ "${ACTUAL_COMMIT}" == "${STAGE03_GIT_COMMIT}" ]] || {
  echo "STAGE03_GIT_COMMIT_MISMATCH" >&2
  exit 1
}
[[ -z "$(git status --porcelain)" ]] || {
  echo "STAGE03_WORKTREE_NOT_CLEAN" >&2
  exit 1
}
[[ "$(git symbolic-ref -q HEAD || true)" == "" ]] || {
  echo "STAGE03_WORKTREE_NOT_DETACHED" >&2
  exit 1
}

STAGE03_INTEGRATION_ROOT="${INTEGRATION_ROOT}" \
STAGE03_RUNTIME_ROOT="${RUNTIME_ROOT}" \
  bash "${INTEGRATION_ROOT}/cluster/goethe_nhr/stage03_bootstrap_env.sh"

readonly PYTHON="${RUNTIME_ROOT}/venv/bin/python"
export PYTHONPATH="${INTEGRATION_ROOT}/src"
export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1

echo "job_id=${SLURM_JOB_ID}"
echo "git_commit=${ACTUAL_COMMIT}"
echo "stage03_contract=stage03_safe_text_cleaning_contract_v1"
echo "stage03_profile=stage03_safe_text_cleaning_profile_v1"

readonly BINDING_OUTPUT="$("${PYTHON}" -m safe_geocoding_pipeline.preprocessing.stage03_cli \
  create-input-binding \
  --output "${INPUT_BINDING}" \
  --stage02-logical-fingerprint "${STAGE03_STAGE02_LOGICAL_FINGERPRINT}" \
  --stage02-schema-fingerprint "${STAGE03_STAGE02_SCHEMA_FINGERPRINT}" \
  --stage02-manifest-sha256 "${STAGE03_STAGE02_MANIFEST_SHA256}" \
  --benchmark-fingerprint "${STAGE03_BENCHMARK_FINGERPRINT}" \
  --expected-row-count "${STAGE03_EXPECTED_ROWS}")"
printf '%s\n' "${BINDING_OUTPUT}"
readonly INPUT_BINDING_SHA256="${BINDING_OUTPUT#stage03_input_binding_sha256=}"
[[ "${INPUT_BINDING_SHA256}" =~ ^[0-9a-f]{64}$ ]] || {
  echo "STAGE03_INPUT_BINDING_OUTPUT_INVALID" >&2
  exit 1
}

echo "stage03_materialization_timing_begin"
readonly MATERIALIZE_OUTPUT="$("${PYTHON}" \
  -m safe_geocoding_pipeline.preprocessing.stage03_cli \
  materialize \
  --stage02-output-directory "${STAGE02_ROOT}" \
  --input-binding "${INPUT_BINDING}" \
  --expected-input-binding-sha256 "${INPUT_BINDING_SHA256}" \
  --output-directory "${OUTPUT_DIRECTORY}" \
  --execution-git-sha "${STAGE03_GIT_COMMIT}")"
printf '%s\n' "${MATERIALIZE_OUTPUT}"
echo "stage03_materialization_timing_end"
readonly STAGE03_MANIFEST_SHA256="$(printf '%s\n' "${MATERIALIZE_OUTPUT}" | \
  awk -F= '$1 == "stage03_manifest_sha256" {print $2}')"
[[ "${STAGE03_MANIFEST_SHA256}" =~ ^[0-9a-f]{64}$ ]] || {
  echo "STAGE03_MATERIALIZATION_OUTPUT_INVALID" >&2
  exit 1
}
readonly STAGE03_ELAPSED_MILLISECONDS="$(printf '%s\n' "${MATERIALIZE_OUTPUT}" | \
  awk -F= '$1 == "stage03_elapsed_milliseconds" {print $2}')"
readonly STAGE03_USER_CPU_MILLISECONDS="$(printf '%s\n' "${MATERIALIZE_OUTPUT}" | \
  awk -F= '$1 == "stage03_user_cpu_milliseconds" {print $2}')"
readonly STAGE03_SYSTEM_CPU_MILLISECONDS="$(printf '%s\n' "${MATERIALIZE_OUTPUT}" | \
  awk -F= '$1 == "stage03_system_cpu_milliseconds" {print $2}')"
readonly STAGE03_MAX_RSS_KIB="$(printf '%s\n' "${MATERIALIZE_OUTPUT}" | \
  awk -F= '$1 == "stage03_max_rss_kib" {print $2}')"
for performance_value in \
  "${STAGE03_ELAPSED_MILLISECONDS}" \
  "${STAGE03_USER_CPU_MILLISECONDS}" \
  "${STAGE03_SYSTEM_CPU_MILLISECONDS}" \
  "${STAGE03_MAX_RSS_KIB}"; do
  [[ "${performance_value}" =~ ^[0-9]+$ ]] || {
    echo "STAGE03_PERFORMANCE_OUTPUT_INVALID" >&2
    exit 1
  }
done

echo "stage03_review_timing_begin"
"${PYTHON}" -m safe_geocoding_pipeline.preprocessing.stage03_cli \
  materialize-review \
  --stage03-output-directory "${OUTPUT_DIRECTORY}" \
  --expected-stage03-manifest-sha256 "${STAGE03_MANIFEST_SHA256}" \
  --development-review-bundle-directory "${REVIEW_BUNDLE}" \
  --expected-development-review-manifest-sha256 \
    "${STAGE03_DEVELOPMENT_REVIEW_MANIFEST_SHA256}" \
  --expected-review-subset-fingerprint "${STAGE03_REVIEW_SUBSET_FINGERPRINT}" \
  --expected-benchmark-fingerprint "${STAGE03_BENCHMARK_FINGERPRINT}" \
  --expected-stage02-logical-fingerprint "${STAGE03_STAGE02_LOGICAL_FINGERPRINT}" \
  --v1-stage03-output-directory "${V1_OUTPUT_DIRECTORY}" \
  --expected-v1-stage03-manifest-sha256 "${STAGE03_V1_MANIFEST_SHA256}" \
  --stage03-elapsed-milliseconds "${STAGE03_ELAPSED_MILLISECONDS}" \
  --stage03-user-cpu-milliseconds "${STAGE03_USER_CPU_MILLISECONDS}" \
  --stage03-system-cpu-milliseconds "${STAGE03_SYSTEM_CPU_MILLISECONDS}" \
  --stage03-max-rss-kib "${STAGE03_MAX_RSS_KIB}" \
  --output-directory "${REVIEW_OUTPUT_DIRECTORY}" \
  --execution-git-sha "${STAGE03_GIT_COMMIT}"
echo "stage03_review_timing_end"

echo "STAGE03_SAFE_TEXT_CLEANING_PASS"
