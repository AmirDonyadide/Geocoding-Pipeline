#!/usr/bin/env bash
#SBATCH --job-name=safe-dev-report
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${DEVELOPMENT_REPORTING_GIT_COMMIT:?submit with the exact reviewed commit}"
: "${DEVELOPMENT_REPORTING_INTEGRATION_ROOT:?submit with a detached worktree}"
: "${DEVELOPMENT_REPORTING_BENCHMARK_ARTIFACT:?submit with DEVELOPMENT only}"
: "${DEVELOPMENT_REPORTING_BENCHMARK_ARTIFACT_SHA256:?submit with its SHA-256}"
: "${DEVELOPMENT_REPORTING_BENCHMARK_FINGERPRINT:?submit with benchmark identity}"
: "${DEVELOPMENT_REPORTING_STAGE02_ROOT:?submit with accepted Stage 2 output}"
: "${DEVELOPMENT_REPORTING_STAGE02_MANIFEST_SHA256:?submit with manifest SHA-256}"
: "${DEVELOPMENT_REPORTING_STAGE02_LOGICAL_FINGERPRINT:?submit with Stage 2 identity}"
: "${DEVELOPMENT_REPORTING_OUTPUT_DIRECTORY:?submit with a new protected output}"

readonly INTEGRATION_ROOT="$(realpath -e -- "${DEVELOPMENT_REPORTING_INTEGRATION_ROOT}")"
readonly BENCHMARK_ARTIFACT="$(realpath -e -- "${DEVELOPMENT_REPORTING_BENCHMARK_ARTIFACT}")"
readonly STAGE02_ROOT="$(realpath -e -- "${DEVELOPMENT_REPORTING_STAGE02_ROOT}")"
readonly OUTPUT_DIRECTORY="$(realpath -m -- "${DEVELOPMENT_REPORTING_OUTPUT_DIRECTORY}")"
readonly DATA_ROOT="/work/footprint/donyadidegan/safe_geocoding_pipeline"

[[ "${BENCHMARK_ARTIFACT,,}" != *holdout* ]] || {
  echo "HOLDOUT_ACCESS_PROHIBITED" >&2
  exit 1
}
[[ "${STAGE02_ROOT,,}" != *holdout* ]] || {
  echo "HOLDOUT_ACCESS_PROHIBITED" >&2
  exit 1
}

cd "${INTEGRATION_ROOT}"
source "${DATA_ROOT}/.venv-goethe-nhr/bin/activate"
export PYTHONPATH="${INTEGRATION_ROOT}/src"
export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1

readonly ACTUAL_COMMIT="$(git rev-parse HEAD)"
[[ "${ACTUAL_COMMIT}" == "${DEVELOPMENT_REPORTING_GIT_COMMIT}" ]] || {
  echo "DEVELOPMENT_REPORTING_GIT_COMMIT_MISMATCH" >&2
  exit 1
}
[[ -z "$(git status --porcelain)" ]] || {
  echo "DEVELOPMENT_REPORTING_WORKTREE_NOT_CLEAN" >&2
  exit 1
}
[[ "$(git symbolic-ref -q HEAD || true)" == "" ]] || {
  echo "DEVELOPMENT_REPORTING_WORKTREE_NOT_DETACHED" >&2
  exit 1
}

echo "job_id=${SLURM_JOB_ID}"
echo "git_commit=${ACTUAL_COMMIT}"
echo "reporting_contract=development_reporting_contract_v1"
echo "review_subset_contract=development_review_subset_contract_v1"

python -m safe_geocoding_pipeline.preprocessing.development_reporting_cli \
  --benchmark-development-artifact "${BENCHMARK_ARTIFACT}" \
  --expected-benchmark-artifact-sha256 \
    "${DEVELOPMENT_REPORTING_BENCHMARK_ARTIFACT_SHA256}" \
  --benchmark-fingerprint "${DEVELOPMENT_REPORTING_BENCHMARK_FINGERPRINT}" \
  --stage02-output-directory "${STAGE02_ROOT}" \
  --expected-stage02-manifest-sha256 \
    "${DEVELOPMENT_REPORTING_STAGE02_MANIFEST_SHA256}" \
  --expected-stage02-logical-fingerprint \
    "${DEVELOPMENT_REPORTING_STAGE02_LOGICAL_FINGERPRINT}" \
  --output-directory "${OUTPUT_DIRECTORY}" \
  --execution-git-sha "${DEVELOPMENT_REPORTING_GIT_COMMIT}"

echo "DEVELOPMENT_REPORTING_PASS"
