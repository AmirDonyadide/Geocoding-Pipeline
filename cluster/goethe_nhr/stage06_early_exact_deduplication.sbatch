#!/usr/bin/env bash
#SBATCH --job-name=safe-stage06
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
: "${STAGE06_GIT_COMMIT:?submit with the exact pushed Stage 6 commit}"
: "${STAGE06_INTEGRATION_ROOT:?submit with an exact detached worktree}"
: "${STAGE06_RUNTIME_ROOT:?submit with a new owner-only runtime root}"
: "${STAGE06_STAGE05_ROOT:?submit with the accepted Stage 5 DEVELOPMENT bundle}"
: "${STAGE06_STAGE05_LOGICAL_FINGERPRINT:?submit with the Stage 5 logical fingerprint}"
: "${STAGE06_STAGE05_SCHEMA_FINGERPRINT:?submit with the Stage 5 schema fingerprint}"
: "${STAGE06_STAGE05_INPUT_BINDING_SHA256:?submit with the Stage 5 input binding SHA-256}"
: "${STAGE06_STAGE05_MANIFEST_SHA256:?submit with the Stage 5 manifest SHA-256}"
: "${STAGE06_STAGE05_ORDERED_IDENTITY_SHA256:?submit with the Stage 5 ordered identity SHA-256}"
: "${STAGE06_BENCHMARK_FINGERPRINT:?submit with the accepted benchmark fingerprint}"
: "${STAGE06_FIXED_500_FINGERPRINT:?submit with the fixed-500 fingerprint}"
: "${STAGE06_EXPECTED_ROWS:?submit with the exact DEVELOPMENT row count}"
: "${STAGE06_INPUT_BINDING:?submit with a new protected binding path}"
: "${STAGE06_OUTPUT_DIRECTORY:?submit with a new immutable Stage 6 path}"
: "${STAGE06_DEVELOPMENT_REVIEW_BUNDLE:?submit with the accepted fixed review bundle}"
: "${STAGE06_DEVELOPMENT_REVIEW_MANIFEST_SHA256:?submit with its exact manifest SHA-256}"
: "${STAGE06_STAGE02_LOGICAL_FINGERPRINT:?submit with the accepted Stage 2 logical fingerprint}"
: "${STAGE06_REVIEW_OUTPUT_DIRECTORY:?submit with a new Stage 6 review path}"

readonly ACCEPTED_STAGE05_LOGICAL="ba5829621fc15347d7cd4e168a48587bab896cd0be98924627876ae853dfaff2"
readonly ACCEPTED_STAGE05_SCHEMA="63d4cdb3707eda65c67cc5196891fa5005adce2b12eb7109554793c48c5303c3"
readonly ACCEPTED_STAGE05_INPUT_BINDING="7e68c33f7daa482b442eca82c00c6904ec5e38bec1b3fc598d5be4d52a6bcb9f"
readonly ACCEPTED_STAGE05_MANIFEST="fd945163e3be0242c43b98972350904631279cb99f366baadb0a3094ab6a1fc5"
readonly ACCEPTED_STAGE05_ORDERED_IDENTITY="fe2a4758582c1880d2b5c62dfc5c587d865e05d13033af9f5e8208b58e2a0487"
readonly ACCEPTED_STAGE02_LOGICAL="ff95021bd2f4b2994e9e2a766f32e792e29797a128dc64fa3aef100ff9f5ca72"
readonly ACCEPTED_BENCHMARK="014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf"
readonly ACCEPTED_FIXED_500="014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52"

[[ "${STAGE06_STAGE05_LOGICAL_FINGERPRINT}" == "${ACCEPTED_STAGE05_LOGICAL}" ]]
[[ "${STAGE06_STAGE05_SCHEMA_FINGERPRINT}" == "${ACCEPTED_STAGE05_SCHEMA}" ]]
[[ "${STAGE06_STAGE05_INPUT_BINDING_SHA256}" == "${ACCEPTED_STAGE05_INPUT_BINDING}" ]]
[[ "${STAGE06_STAGE05_MANIFEST_SHA256}" == "${ACCEPTED_STAGE05_MANIFEST}" ]]
[[ "${STAGE06_STAGE05_ORDERED_IDENTITY_SHA256}" == "${ACCEPTED_STAGE05_ORDERED_IDENTITY}" ]]
[[ "${STAGE06_STAGE02_LOGICAL_FINGERPRINT}" == "${ACCEPTED_STAGE02_LOGICAL}" ]]
[[ "${STAGE06_BENCHMARK_FINGERPRINT}" == "${ACCEPTED_BENCHMARK}" ]]
[[ "${STAGE06_FIXED_500_FINGERPRINT}" == "${ACCEPTED_FIXED_500}" ]]
[[ "${STAGE06_EXPECTED_ROWS}" == "35000" ]]

readonly LOG_ROOT="/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm"
readonly JOB_STDOUT="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.out"
readonly JOB_STDERR="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.err"
chmod 0600 "${JOB_STDOUT}" "${JOB_STDERR}"
[[ "$(stat -c %a "${JOB_STDOUT}")" == "600" ]]
[[ "$(stat -c %a "${JOB_STDERR}")" == "600" ]]

readonly DATA_ROOT="$(realpath -e -- \
  "/work/footprint/donyadidegan/safe_geocoding_pipeline")"
readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE06_INTEGRATION_ROOT}")"
readonly RUNTIME_ROOT="$(realpath -m -- "${STAGE06_RUNTIME_ROOT}")"
readonly STAGE05_ROOT="$(realpath -e -- "${STAGE06_STAGE05_ROOT}")"
readonly INPUT_BINDING="$(realpath -m -- "${STAGE06_INPUT_BINDING}")"
readonly OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE06_OUTPUT_DIRECTORY}")"
readonly REVIEW_BUNDLE="$(realpath -e -- "${STAGE06_DEVELOPMENT_REVIEW_BUNDLE}")"
readonly REVIEW_OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE06_REVIEW_OUTPUT_DIRECTORY}")"

for protected_path in \
  "${INTEGRATION_ROOT}" \
  "${RUNTIME_ROOT}" \
  "${STAGE05_ROOT}" \
  "${INPUT_BINDING}" \
  "${OUTPUT_DIRECTORY}" \
  "${REVIEW_BUNDLE}" \
  "${REVIEW_OUTPUT_DIRECTORY}"; do
  [[ "${protected_path}" == "${DATA_ROOT}"/* ]] || {
    echo "STAGE06_CONTROLLED_PATH_REQUIRED" >&2
    exit 1
  }
  [[ "${protected_path,,}" != *holdout* ]] || {
    echo "HOLDOUT_ACCESS_PROHIBITED" >&2
    exit 1
  }
done

cd "${INTEGRATION_ROOT}"
readonly ACTUAL_COMMIT="$(git rev-parse HEAD)"
[[ "${ACTUAL_COMMIT}" == "${STAGE06_GIT_COMMIT}" ]] || {
  echo "STAGE06_GIT_COMMIT_MISMATCH" >&2
  exit 1
}
[[ -z "$(git status --porcelain)" ]] || {
  echo "STAGE06_WORKTREE_NOT_CLEAN" >&2
  exit 1
}
[[ "$(git symbolic-ref -q HEAD || true)" == "" ]] || {
  echo "STAGE06_WORKTREE_NOT_DETACHED" >&2
  exit 1
}

STAGE06_INTEGRATION_ROOT="${INTEGRATION_ROOT}" \
STAGE06_RUNTIME_ROOT="${RUNTIME_ROOT}" \
  bash "${INTEGRATION_ROOT}/cluster/goethe_nhr/stage06_bootstrap_env.sh"

readonly PYTHON="${RUNTIME_ROOT}/venv/bin/python"
export PYTHONPATH="${INTEGRATION_ROOT}/src"
export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1

echo "job_id=${SLURM_JOB_ID}"
echo "git_commit=${ACTUAL_COMMIT}"
echo "stage06_contract=stage06_early_exact_deduplication_contract_v1"
echo "stage06_profile=stage06_early_exact_deduplication_profile_v1"

readonly BINDING_OUTPUT="$("${PYTHON}" \
  -m safe_geocoding_pipeline.preprocessing.stage06_cli \
  create-input-binding \
  --output "${INPUT_BINDING}" \
  --stage05-logical-fingerprint "${STAGE06_STAGE05_LOGICAL_FINGERPRINT}" \
  --stage05-schema-fingerprint "${STAGE06_STAGE05_SCHEMA_FINGERPRINT}" \
  --stage05-input-binding-sha256 "${STAGE06_STAGE05_INPUT_BINDING_SHA256}" \
  --stage05-manifest-sha256 "${STAGE06_STAGE05_MANIFEST_SHA256}" \
  --stage05-ordered-identity-sha256 "${STAGE06_STAGE05_ORDERED_IDENTITY_SHA256}" \
  --benchmark-fingerprint "${STAGE06_BENCHMARK_FINGERPRINT}" \
  --fixed-500-fingerprint "${STAGE06_FIXED_500_FINGERPRINT}" \
  --expected-row-count "${STAGE06_EXPECTED_ROWS}")"
printf '%s\n' "${BINDING_OUTPUT}"
readonly INPUT_BINDING_SHA256="${BINDING_OUTPUT#stage06_input_binding_sha256=}"
[[ "${INPUT_BINDING_SHA256}" =~ ^[0-9a-f]{64}$ ]] || {
  echo "STAGE06_INPUT_BINDING_OUTPUT_INVALID" >&2
  exit 1
}

echo "stage06_materialization_timing_begin"
readonly MATERIALIZE_OUTPUT="$("${PYTHON}" \
  -m safe_geocoding_pipeline.preprocessing.stage06_cli \
  materialize \
  --stage05-output-directory "${STAGE05_ROOT}" \
  --input-binding "${INPUT_BINDING}" \
  --expected-input-binding-sha256 "${INPUT_BINDING_SHA256}" \
  --output-directory "${OUTPUT_DIRECTORY}" \
  --execution-git-sha "${STAGE06_GIT_COMMIT}" \
  --duckdb-memory-limit 8GB \
  --duckdb-threads 4)"
printf '%s\n' "${MATERIALIZE_OUTPUT}"
echo "stage06_materialization_timing_end"
readonly STAGE06_MANIFEST_SHA256="$(printf '%s\n' "${MATERIALIZE_OUTPUT}" | \
  awk -F= '$1 == "stage06_manifest_sha256" {print $2}')"
readonly STAGE06_ELAPSED_MILLISECONDS="$(printf '%s\n' "${MATERIALIZE_OUTPUT}" | \
  awk -F= '$1 == "stage06_elapsed_milliseconds" {print $2}')"
readonly STAGE06_USER_CPU_MILLISECONDS="$(printf '%s\n' "${MATERIALIZE_OUTPUT}" | \
  awk -F= '$1 == "stage06_user_cpu_milliseconds" {print $2}')"
readonly STAGE06_SYSTEM_CPU_MILLISECONDS="$(printf '%s\n' "${MATERIALIZE_OUTPUT}" | \
  awk -F= '$1 == "stage06_system_cpu_milliseconds" {print $2}')"
readonly STAGE06_MAX_RSS_KIB="$(printf '%s\n' "${MATERIALIZE_OUTPUT}" | \
  awk -F= '$1 == "stage06_max_rss_kib" {print $2}')"
[[ "${STAGE06_MANIFEST_SHA256}" =~ ^[0-9a-f]{64}$ ]]
for performance_value in \
  "${STAGE06_ELAPSED_MILLISECONDS}" \
  "${STAGE06_USER_CPU_MILLISECONDS}" \
  "${STAGE06_SYSTEM_CPU_MILLISECONDS}" \
  "${STAGE06_MAX_RSS_KIB}"; do
  [[ "${performance_value}" =~ ^[0-9]+$ ]] || {
    echo "STAGE06_PERFORMANCE_OUTPUT_INVALID" >&2
    exit 1
  }
done

echo "stage06_published_validation_begin"
"${PYTHON}" -m safe_geocoding_pipeline.preprocessing.stage06_cli \
  validate-published \
  --stage05-output-directory "${STAGE05_ROOT}" \
  --stage06-output-directory "${OUTPUT_DIRECTORY}" \
  --expected-stage06-manifest-sha256 "${STAGE06_MANIFEST_SHA256}" \
  --duckdb-memory-limit 8GB \
  --duckdb-threads 4
echo "stage06_published_validation_end"

echo "stage06_fixed500_timing_begin"
"${PYTHON}" -m safe_geocoding_pipeline.preprocessing.stage06_cli \
  materialize-review \
  --stage05-output-directory "${STAGE05_ROOT}" \
  --stage06-output-directory "${OUTPUT_DIRECTORY}" \
  --expected-stage06-manifest-sha256 "${STAGE06_MANIFEST_SHA256}" \
  --development-review-bundle-directory "${REVIEW_BUNDLE}" \
  --expected-development-review-manifest-sha256 \
    "${STAGE06_DEVELOPMENT_REVIEW_MANIFEST_SHA256}" \
  --expected-review-subset-fingerprint "${STAGE06_FIXED_500_FINGERPRINT}" \
  --expected-benchmark-fingerprint "${STAGE06_BENCHMARK_FINGERPRINT}" \
  --expected-stage02-logical-fingerprint "${STAGE06_STAGE02_LOGICAL_FINGERPRINT}" \
  --stage06-elapsed-milliseconds "${STAGE06_ELAPSED_MILLISECONDS}" \
  --stage06-user-cpu-milliseconds "${STAGE06_USER_CPU_MILLISECONDS}" \
  --stage06-system-cpu-milliseconds "${STAGE06_SYSTEM_CPU_MILLISECONDS}" \
  --stage06-max-rss-kib "${STAGE06_MAX_RSS_KIB}" \
  --output-directory "${REVIEW_OUTPUT_DIRECTORY}" \
  --execution-git-sha "${STAGE06_GIT_COMMIT}"
echo "stage06_fixed500_timing_end"

echo "STAGE06_EARLY_EXACT_DEDUPLICATION_PASS"
