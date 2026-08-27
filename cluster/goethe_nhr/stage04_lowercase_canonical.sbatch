#!/usr/bin/env bash
#SBATCH --job-name=safe-stage04
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
: "${STAGE04_GIT_COMMIT:?submit with the exact pushed Stage 4 commit}"
: "${STAGE04_INTEGRATION_ROOT:?submit with an exact detached worktree}"
: "${STAGE04_RUNTIME_ROOT:?submit with an owner-only isolated runtime root}"
: "${STAGE04_STAGE03_ROOT:?submit with the accepted Stage 3 DEVELOPMENT bundle}"
: "${STAGE04_STAGE03_LOGICAL_FINGERPRINT:?submit with the Stage 3 logical fingerprint}"
: "${STAGE04_STAGE03_SCHEMA_FINGERPRINT:?submit with the Stage 3 schema fingerprint}"
: "${STAGE04_STAGE03_INPUT_BINDING_SHA256:?submit with the Stage 3 input binding SHA-256}"
: "${STAGE04_STAGE03_MANIFEST_SHA256:?submit with the Stage 3 manifest SHA-256}"
: "${STAGE04_STAGE03_ORDERED_IDENTITY_SHA256:?submit with the Stage 3 ordered identity SHA-256}"
: "${STAGE04_BENCHMARK_FINGERPRINT:?submit with the accepted benchmark fingerprint}"
: "${STAGE04_EXPECTED_ROWS:?submit with the exact DEVELOPMENT row count}"
: "${STAGE04_INPUT_BINDING:?submit with a new protected binding path}"
: "${STAGE04_OUTPUT_DIRECTORY:?submit with a new protected Stage 4 path}"
: "${STAGE04_DEVELOPMENT_REVIEW_BUNDLE:?submit with the accepted fixed review bundle}"
: "${STAGE04_DEVELOPMENT_REVIEW_MANIFEST_SHA256:?submit with its exact manifest SHA-256}"
: "${STAGE04_STAGE02_LOGICAL_FINGERPRINT:?submit with the accepted Stage 2 logical fingerprint}"
: "${STAGE04_REVIEW_SUBSET_FINGERPRINT:?submit with the fixed 500-row fingerprint}"
: "${STAGE04_REVIEW_OUTPUT_DIRECTORY:?submit with a new Stage 4 review path}"

readonly ACCEPTED_STAGE03_LOGICAL="38df499bfaf61883832a9c718adf4cf92cfcea753337df68fa2e89afb6051bdb"
readonly ACCEPTED_STAGE03_SCHEMA="fc991ef63bd80a754114ecae6a9d3c4cf1f33a35a28581fea997edd2e4565c9b"
readonly ACCEPTED_STAGE03_INPUT_BINDING="6a2a28d276884511f5b8f63f40d14d6b7f4bf4397aa09289c53acdb92a661e6f"
readonly ACCEPTED_STAGE03_MANIFEST="8f70745e31185abce52fdc1685c2b767f90874c21596152ea0463ec6677478d4"
readonly ACCEPTED_STAGE03_ORDERED_IDENTITY="fe2a4758582c1880d2b5c62dfc5c587d865e05d13033af9f5e8208b58e2a0487"
readonly ACCEPTED_STAGE02_LOGICAL="ff95021bd2f4b2994e9e2a766f32e792e29797a128dc64fa3aef100ff9f5ca72"
readonly ACCEPTED_BENCHMARK="014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf"
readonly ACCEPTED_REVIEW_SUBSET="014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52"

[[ "${STAGE04_STAGE03_LOGICAL_FINGERPRINT}" == "${ACCEPTED_STAGE03_LOGICAL}" ]]
[[ "${STAGE04_STAGE03_SCHEMA_FINGERPRINT}" == "${ACCEPTED_STAGE03_SCHEMA}" ]]
[[ "${STAGE04_STAGE03_INPUT_BINDING_SHA256}" == "${ACCEPTED_STAGE03_INPUT_BINDING}" ]]
[[ "${STAGE04_STAGE03_MANIFEST_SHA256}" == "${ACCEPTED_STAGE03_MANIFEST}" ]]
[[ "${STAGE04_STAGE03_ORDERED_IDENTITY_SHA256}" == "${ACCEPTED_STAGE03_ORDERED_IDENTITY}" ]]
[[ "${STAGE04_STAGE02_LOGICAL_FINGERPRINT}" == "${ACCEPTED_STAGE02_LOGICAL}" ]]
[[ "${STAGE04_BENCHMARK_FINGERPRINT}" == "${ACCEPTED_BENCHMARK}" ]]
[[ "${STAGE04_REVIEW_SUBSET_FINGERPRINT}" == "${ACCEPTED_REVIEW_SUBSET}" ]]
[[ "${STAGE04_EXPECTED_ROWS}" == "35000" ]]

readonly DATA_ROOT="/work/footprint/donyadidegan/safe_geocoding_pipeline"
readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE04_INTEGRATION_ROOT}")"
readonly RUNTIME_ROOT="$(realpath -m -- "${STAGE04_RUNTIME_ROOT}")"
readonly STAGE03_ROOT="$(realpath -e -- "${STAGE04_STAGE03_ROOT}")"
readonly INPUT_BINDING="$(realpath -m -- "${STAGE04_INPUT_BINDING}")"
readonly OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE04_OUTPUT_DIRECTORY}")"
readonly REVIEW_BUNDLE="$(realpath -e -- "${STAGE04_DEVELOPMENT_REVIEW_BUNDLE}")"
readonly REVIEW_OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE04_REVIEW_OUTPUT_DIRECTORY}")"

for protected_path in \
  "${INTEGRATION_ROOT}" \
  "${RUNTIME_ROOT}" \
  "${STAGE03_ROOT}" \
  "${INPUT_BINDING}" \
  "${OUTPUT_DIRECTORY}" \
  "${REVIEW_BUNDLE}" \
  "${REVIEW_OUTPUT_DIRECTORY}"; do
  [[ "${protected_path}" == "${DATA_ROOT}"/* ]] || {
    echo "STAGE04_CONTROLLED_PATH_REQUIRED" >&2
    exit 1
  }
  [[ "${protected_path,,}" != *holdout* ]] || {
    echo "HOLDOUT_ACCESS_PROHIBITED" >&2
    exit 1
  }
done

cd "${INTEGRATION_ROOT}"
readonly ACTUAL_COMMIT="$(git rev-parse HEAD)"
[[ "${ACTUAL_COMMIT}" == "${STAGE04_GIT_COMMIT}" ]] || {
  echo "STAGE04_GIT_COMMIT_MISMATCH" >&2
  exit 1
}
[[ -z "$(git status --porcelain)" ]] || {
  echo "STAGE04_WORKTREE_NOT_CLEAN" >&2
  exit 1
}
[[ "$(git symbolic-ref -q HEAD || true)" == "" ]] || {
  echo "STAGE04_WORKTREE_NOT_DETACHED" >&2
  exit 1
}

STAGE04_INTEGRATION_ROOT="${INTEGRATION_ROOT}" \
STAGE04_RUNTIME_ROOT="${RUNTIME_ROOT}" \
  bash "${INTEGRATION_ROOT}/cluster/goethe_nhr/stage04_bootstrap_env.sh"

readonly PYTHON="${RUNTIME_ROOT}/venv/bin/python"
export PYTHONPATH="${INTEGRATION_ROOT}/src"
export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1

echo "job_id=${SLURM_JOB_ID}"
echo "git_commit=${ACTUAL_COMMIT}"
echo "stage04_contract=stage04_lowercase_canonical_contract_v1"
echo "stage04_profile=stage04_lowercase_canonical_profile_v1"

readonly BINDING_OUTPUT="$("${PYTHON}" \
  -m safe_geocoding_pipeline.preprocessing.stage04_cli \
  create-input-binding \
  --output "${INPUT_BINDING}" \
  --stage03-logical-fingerprint "${STAGE04_STAGE03_LOGICAL_FINGERPRINT}" \
  --stage03-schema-fingerprint "${STAGE04_STAGE03_SCHEMA_FINGERPRINT}" \
  --stage03-input-binding-sha256 "${STAGE04_STAGE03_INPUT_BINDING_SHA256}" \
  --stage03-manifest-sha256 "${STAGE04_STAGE03_MANIFEST_SHA256}" \
  --stage03-ordered-identity-sha256 "${STAGE04_STAGE03_ORDERED_IDENTITY_SHA256}" \
  --benchmark-fingerprint "${STAGE04_BENCHMARK_FINGERPRINT}" \
  --expected-row-count "${STAGE04_EXPECTED_ROWS}")"
printf '%s\n' "${BINDING_OUTPUT}"
readonly INPUT_BINDING_SHA256="${BINDING_OUTPUT#stage04_input_binding_sha256=}"
[[ "${INPUT_BINDING_SHA256}" =~ ^[0-9a-f]{64}$ ]] || {
  echo "STAGE04_INPUT_BINDING_OUTPUT_INVALID" >&2
  exit 1
}

echo "stage04_materialization_timing_begin"
readonly MATERIALIZE_OUTPUT="$("${PYTHON}" \
  -m safe_geocoding_pipeline.preprocessing.stage04_cli \
  materialize \
  --stage03-output-directory "${STAGE03_ROOT}" \
  --input-binding "${INPUT_BINDING}" \
  --expected-input-binding-sha256 "${INPUT_BINDING_SHA256}" \
  --output-directory "${OUTPUT_DIRECTORY}" \
  --execution-git-sha "${STAGE04_GIT_COMMIT}")"
printf '%s\n' "${MATERIALIZE_OUTPUT}"
echo "stage04_materialization_timing_end"
readonly STAGE04_MANIFEST_SHA256="$(printf '%s\n' "${MATERIALIZE_OUTPUT}" | \
  awk -F= '$1 == "stage04_manifest_sha256" {print $2}')"
[[ "${STAGE04_MANIFEST_SHA256}" =~ ^[0-9a-f]{64}$ ]] || {
  echo "STAGE04_MATERIALIZATION_OUTPUT_INVALID" >&2
  exit 1
}
readonly STAGE04_ELAPSED_MILLISECONDS="$(printf '%s\n' "${MATERIALIZE_OUTPUT}" | \
  awk -F= '$1 == "stage04_elapsed_milliseconds" {print $2}')"
readonly STAGE04_USER_CPU_MILLISECONDS="$(printf '%s\n' "${MATERIALIZE_OUTPUT}" | \
  awk -F= '$1 == "stage04_user_cpu_milliseconds" {print $2}')"
readonly STAGE04_SYSTEM_CPU_MILLISECONDS="$(printf '%s\n' "${MATERIALIZE_OUTPUT}" | \
  awk -F= '$1 == "stage04_system_cpu_milliseconds" {print $2}')"
readonly STAGE04_MAX_RSS_KIB="$(printf '%s\n' "${MATERIALIZE_OUTPUT}" | \
  awk -F= '$1 == "stage04_max_rss_kib" {print $2}')"
for performance_value in \
  "${STAGE04_ELAPSED_MILLISECONDS}" \
  "${STAGE04_USER_CPU_MILLISECONDS}" \
  "${STAGE04_SYSTEM_CPU_MILLISECONDS}" \
  "${STAGE04_MAX_RSS_KIB}"; do
  [[ "${performance_value}" =~ ^[0-9]+$ ]] || {
    echo "STAGE04_PERFORMANCE_OUTPUT_INVALID" >&2
    exit 1
  }
done

echo "stage04_published_validation_begin"
"${PYTHON}" -m safe_geocoding_pipeline.preprocessing.stage04_cli \
  validate-published \
  --stage03-output-directory "${STAGE03_ROOT}" \
  --stage04-output-directory "${OUTPUT_DIRECTORY}" \
  --expected-stage04-manifest-sha256 "${STAGE04_MANIFEST_SHA256}"
echo "stage04_published_validation_end"

echo "stage04_review_timing_begin"
"${PYTHON}" -m safe_geocoding_pipeline.preprocessing.stage04_cli \
  materialize-review \
  --stage04-output-directory "${OUTPUT_DIRECTORY}" \
  --expected-stage04-manifest-sha256 "${STAGE04_MANIFEST_SHA256}" \
  --development-review-bundle-directory "${REVIEW_BUNDLE}" \
  --expected-development-review-manifest-sha256 \
    "${STAGE04_DEVELOPMENT_REVIEW_MANIFEST_SHA256}" \
  --expected-review-subset-fingerprint "${STAGE04_REVIEW_SUBSET_FINGERPRINT}" \
  --expected-benchmark-fingerprint "${STAGE04_BENCHMARK_FINGERPRINT}" \
  --expected-stage02-logical-fingerprint "${STAGE04_STAGE02_LOGICAL_FINGERPRINT}" \
  --stage04-elapsed-milliseconds "${STAGE04_ELAPSED_MILLISECONDS}" \
  --stage04-user-cpu-milliseconds "${STAGE04_USER_CPU_MILLISECONDS}" \
  --stage04-system-cpu-milliseconds "${STAGE04_SYSTEM_CPU_MILLISECONDS}" \
  --stage04-max-rss-kib "${STAGE04_MAX_RSS_KIB}" \
  --output-directory "${REVIEW_OUTPUT_DIRECTORY}" \
  --execution-git-sha "${STAGE04_GIT_COMMIT}"
echo "stage04_review_timing_end"

echo "STAGE04_LOWERCASE_CANONICAL_PASS"
