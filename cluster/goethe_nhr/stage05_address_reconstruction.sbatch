#!/usr/bin/env bash
#SBATCH --job-name=safe-stage05
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=02:00:00
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${STAGE05_GIT_COMMIT:?submit with the exact pushed Stage 5 commit}"
: "${STAGE05_INTEGRATION_ROOT:?submit with an exact detached worktree}"
: "${STAGE05_RUNTIME_ROOT:?submit with an owner-only isolated runtime root}"
: "${STAGE05_STAGE04_ROOT:?submit with the accepted Stage 4 DEVELOPMENT bundle}"
: "${STAGE05_STAGE04_LOGICAL_FINGERPRINT:?submit with the Stage 4 logical fingerprint}"
: "${STAGE05_STAGE04_SCHEMA_FINGERPRINT:?submit with the Stage 4 schema fingerprint}"
: "${STAGE05_STAGE04_INPUT_BINDING_SHA256:?submit with the Stage 4 input binding SHA-256}"
: "${STAGE05_STAGE04_MANIFEST_SHA256:?submit with the Stage 4 manifest SHA-256}"
: "${STAGE05_STAGE04_ORDERED_IDENTITY_SHA256:?submit with the Stage 4 ordered identity SHA-256}"
: "${STAGE05_BENCHMARK_FINGERPRINT:?submit with the accepted benchmark fingerprint}"
: "${STAGE05_EXPECTED_ROWS:?submit with the exact DEVELOPMENT row count}"
: "${STAGE05_INPUT_BINDING:?submit with a new protected binding path}"
: "${STAGE05_OUTPUT_DIRECTORY:?submit with a new protected Stage 5 path}"
: "${STAGE05_DEVELOPMENT_REVIEW_BUNDLE:?submit with the accepted fixed review bundle}"
: "${STAGE05_DEVELOPMENT_REVIEW_MANIFEST_SHA256:?submit with its exact manifest SHA-256}"
: "${STAGE05_STAGE02_LOGICAL_FINGERPRINT:?submit with the accepted Stage 2 logical fingerprint}"
: "${STAGE05_REVIEW_SUBSET_FINGERPRINT:?submit with the fixed 500-row fingerprint}"
: "${STAGE05_REVIEW_OUTPUT_DIRECTORY:?submit with a new Stage 5 review path}"

readonly ACCEPTED_STAGE04_LOGICAL="054c66701f854a0108938170e1cb9bcee8a772f7fed29b82cda53c71aa9747ec"
readonly ACCEPTED_STAGE04_SCHEMA="dafb4f78b8bfce3120b6f4f7ae8cb44883f4c3a9cfd94b3137871b83c0ed5cbc"
readonly ACCEPTED_STAGE04_INPUT_BINDING="90e0e94d4359bd5927820dfc06b2cfc1dc37485c032d95726d1260ec88a534b0"
readonly ACCEPTED_STAGE04_MANIFEST="17a4854cddd8929b65ea79402f1a4f12a1574b720c1921567b577f23e152d1f3"
readonly ACCEPTED_STAGE04_ORDERED_IDENTITY="fe2a4758582c1880d2b5c62dfc5c587d865e05d13033af9f5e8208b58e2a0487"
readonly ACCEPTED_STAGE02_LOGICAL="ff95021bd2f4b2994e9e2a766f32e792e29797a128dc64fa3aef100ff9f5ca72"
readonly ACCEPTED_BENCHMARK="014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf"
readonly ACCEPTED_REVIEW_SUBSET="014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52"

[[ "${STAGE05_STAGE04_LOGICAL_FINGERPRINT}" == "${ACCEPTED_STAGE04_LOGICAL}" ]]
[[ "${STAGE05_STAGE04_SCHEMA_FINGERPRINT}" == "${ACCEPTED_STAGE04_SCHEMA}" ]]
[[ "${STAGE05_STAGE04_INPUT_BINDING_SHA256}" == "${ACCEPTED_STAGE04_INPUT_BINDING}" ]]
[[ "${STAGE05_STAGE04_MANIFEST_SHA256}" == "${ACCEPTED_STAGE04_MANIFEST}" ]]
[[ "${STAGE05_STAGE04_ORDERED_IDENTITY_SHA256}" == "${ACCEPTED_STAGE04_ORDERED_IDENTITY}" ]]
[[ "${STAGE05_STAGE02_LOGICAL_FINGERPRINT}" == "${ACCEPTED_STAGE02_LOGICAL}" ]]
[[ "${STAGE05_BENCHMARK_FINGERPRINT}" == "${ACCEPTED_BENCHMARK}" ]]
[[ "${STAGE05_REVIEW_SUBSET_FINGERPRINT}" == "${ACCEPTED_REVIEW_SUBSET}" ]]
[[ "${STAGE05_EXPECTED_ROWS}" == "35000" ]]

readonly DATA_ROOT="$(realpath -e -- \
  "/work/footprint/donyadidegan/safe_geocoding_pipeline")"
readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE05_INTEGRATION_ROOT}")"
readonly RUNTIME_ROOT="$(realpath -m -- "${STAGE05_RUNTIME_ROOT}")"
readonly STAGE04_ROOT="$(realpath -e -- "${STAGE05_STAGE04_ROOT}")"
readonly INPUT_BINDING="$(realpath -m -- "${STAGE05_INPUT_BINDING}")"
readonly OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE05_OUTPUT_DIRECTORY}")"
readonly REVIEW_BUNDLE="$(realpath -e -- "${STAGE05_DEVELOPMENT_REVIEW_BUNDLE}")"
readonly REVIEW_OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE05_REVIEW_OUTPUT_DIRECTORY}")"

for protected_path in \
  "${INTEGRATION_ROOT}" \
  "${RUNTIME_ROOT}" \
  "${STAGE04_ROOT}" \
  "${INPUT_BINDING}" \
  "${OUTPUT_DIRECTORY}" \
  "${REVIEW_BUNDLE}" \
  "${REVIEW_OUTPUT_DIRECTORY}"; do
  [[ "${protected_path}" == "${DATA_ROOT}"/* ]] || {
    echo "STAGE05_CONTROLLED_PATH_REQUIRED" >&2
    exit 1
  }
  [[ "${protected_path,,}" != *holdout* ]] || {
    echo "HOLDOUT_ACCESS_PROHIBITED" >&2
    exit 1
  }
done

cd "${INTEGRATION_ROOT}"
readonly ACTUAL_COMMIT="$(git rev-parse HEAD)"
[[ "${ACTUAL_COMMIT}" == "${STAGE05_GIT_COMMIT}" ]] || {
  echo "STAGE05_GIT_COMMIT_MISMATCH" >&2
  exit 1
}
[[ -z "$(git status --porcelain)" ]] || {
  echo "STAGE05_WORKTREE_NOT_CLEAN" >&2
  exit 1
}
[[ "$(git symbolic-ref -q HEAD || true)" == "" ]] || {
  echo "STAGE05_WORKTREE_NOT_DETACHED" >&2
  exit 1
}

STAGE05_INTEGRATION_ROOT="${INTEGRATION_ROOT}" \
STAGE05_RUNTIME_ROOT="${RUNTIME_ROOT}" \
  bash "${INTEGRATION_ROOT}/cluster/goethe_nhr/stage05_bootstrap_env.sh"

readonly PYTHON="${RUNTIME_ROOT}/venv/bin/python"
export PYTHONPATH="${INTEGRATION_ROOT}/src"
export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1

echo "job_id=${SLURM_JOB_ID}"
echo "git_commit=${ACTUAL_COMMIT}"
echo "stage05_contract=stage05_address_reconstruction_contract_v1"
echo "stage05_profile=stage05_address_reconstruction_profile_v1"

readonly BINDING_OUTPUT="$("${PYTHON}" \
  -m safe_geocoding_pipeline.preprocessing.stage05_cli \
  create-input-binding \
  --output "${INPUT_BINDING}" \
  --stage04-logical-fingerprint "${STAGE05_STAGE04_LOGICAL_FINGERPRINT}" \
  --stage04-schema-fingerprint "${STAGE05_STAGE04_SCHEMA_FINGERPRINT}" \
  --stage04-input-binding-sha256 "${STAGE05_STAGE04_INPUT_BINDING_SHA256}" \
  --stage04-manifest-sha256 "${STAGE05_STAGE04_MANIFEST_SHA256}" \
  --stage04-ordered-identity-sha256 "${STAGE05_STAGE04_ORDERED_IDENTITY_SHA256}" \
  --benchmark-fingerprint "${STAGE05_BENCHMARK_FINGERPRINT}" \
  --expected-row-count "${STAGE05_EXPECTED_ROWS}")"
printf '%s\n' "${BINDING_OUTPUT}"
readonly INPUT_BINDING_SHA256="${BINDING_OUTPUT#stage05_input_binding_sha256=}"
[[ "${INPUT_BINDING_SHA256}" =~ ^[0-9a-f]{64}$ ]] || {
  echo "STAGE05_INPUT_BINDING_OUTPUT_INVALID" >&2
  exit 1
}

echo "stage05_materialization_timing_begin"
readonly MATERIALIZE_OUTPUT="$("${PYTHON}" \
  -m safe_geocoding_pipeline.preprocessing.stage05_cli \
  materialize \
  --stage04-output-directory "${STAGE04_ROOT}" \
  --input-binding "${INPUT_BINDING}" \
  --expected-input-binding-sha256 "${INPUT_BINDING_SHA256}" \
  --output-directory "${OUTPUT_DIRECTORY}" \
  --execution-git-sha "${STAGE05_GIT_COMMIT}")"
printf '%s\n' "${MATERIALIZE_OUTPUT}"
echo "stage05_materialization_timing_end"
readonly STAGE05_MANIFEST_SHA256="$(printf '%s\n' "${MATERIALIZE_OUTPUT}" | \
  awk -F= '$1 == "stage05_manifest_sha256" {print $2}')"
[[ "${STAGE05_MANIFEST_SHA256}" =~ ^[0-9a-f]{64}$ ]] || {
  echo "STAGE05_MATERIALIZATION_OUTPUT_INVALID" >&2
  exit 1
}
readonly STAGE05_ELAPSED_MILLISECONDS="$(printf '%s\n' "${MATERIALIZE_OUTPUT}" | \
  awk -F= '$1 == "stage05_elapsed_milliseconds" {print $2}')"
readonly STAGE05_USER_CPU_MILLISECONDS="$(printf '%s\n' "${MATERIALIZE_OUTPUT}" | \
  awk -F= '$1 == "stage05_user_cpu_milliseconds" {print $2}')"
readonly STAGE05_SYSTEM_CPU_MILLISECONDS="$(printf '%s\n' "${MATERIALIZE_OUTPUT}" | \
  awk -F= '$1 == "stage05_system_cpu_milliseconds" {print $2}')"
readonly STAGE05_MAX_RSS_KIB="$(printf '%s\n' "${MATERIALIZE_OUTPUT}" | \
  awk -F= '$1 == "stage05_max_rss_kib" {print $2}')"
for performance_value in \
  "${STAGE05_ELAPSED_MILLISECONDS}" \
  "${STAGE05_USER_CPU_MILLISECONDS}" \
  "${STAGE05_SYSTEM_CPU_MILLISECONDS}" \
  "${STAGE05_MAX_RSS_KIB}"; do
  [[ "${performance_value}" =~ ^[0-9]+$ ]] || {
    echo "STAGE05_PERFORMANCE_OUTPUT_INVALID" >&2
    exit 1
  }
done

echo "stage05_published_validation_begin"
"${PYTHON}" -m safe_geocoding_pipeline.preprocessing.stage05_cli \
  validate-published \
  --stage04-output-directory "${STAGE04_ROOT}" \
  --stage05-output-directory "${OUTPUT_DIRECTORY}" \
  --expected-stage05-manifest-sha256 "${STAGE05_MANIFEST_SHA256}"
echo "stage05_published_validation_end"

echo "stage05_review_timing_begin"
"${PYTHON}" -m safe_geocoding_pipeline.preprocessing.stage05_cli \
  materialize-review \
  --stage04-output-directory "${STAGE04_ROOT}" \
  --expected-stage04-manifest-sha256 "${STAGE05_STAGE04_MANIFEST_SHA256}" \
  --stage05-output-directory "${OUTPUT_DIRECTORY}" \
  --expected-stage05-manifest-sha256 "${STAGE05_MANIFEST_SHA256}" \
  --development-review-bundle-directory "${REVIEW_BUNDLE}" \
  --expected-development-review-manifest-sha256 \
    "${STAGE05_DEVELOPMENT_REVIEW_MANIFEST_SHA256}" \
  --expected-review-subset-fingerprint "${STAGE05_REVIEW_SUBSET_FINGERPRINT}" \
  --expected-benchmark-fingerprint "${STAGE05_BENCHMARK_FINGERPRINT}" \
  --expected-stage02-logical-fingerprint "${STAGE05_STAGE02_LOGICAL_FINGERPRINT}" \
  --stage05-elapsed-milliseconds "${STAGE05_ELAPSED_MILLISECONDS}" \
  --stage05-user-cpu-milliseconds "${STAGE05_USER_CPU_MILLISECONDS}" \
  --stage05-system-cpu-milliseconds "${STAGE05_SYSTEM_CPU_MILLISECONDS}" \
  --stage05-max-rss-kib "${STAGE05_MAX_RSS_KIB}" \
  --output-directory "${REVIEW_OUTPUT_DIRECTORY}" \
  --execution-git-sha "${STAGE05_GIT_COMMIT}"
echo "stage05_review_timing_end"

echo "STAGE05_ADDRESS_RECONSTRUCTION_PASS"
