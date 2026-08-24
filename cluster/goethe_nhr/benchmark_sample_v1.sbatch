#!/usr/bin/env bash
#SBATCH --job-name=safe-benchmark-v1
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=32G
#SBATCH --time=12:00:00
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${BENCHMARK_GIT_COMMIT:?submit with the exact reviewed benchmark commit}"
: "${BENCHMARK_INTEGRATION_ROOT:?submit with an exact detached integration worktree}"
: "${BENCHMARK_SOURCE_ROOT:?submit with the controlled immutable source snapshot}"
: "${BENCHMARK_POPULATION_SCOPE:?submit with the controlled population-scope JSON}"
: "${BENCHMARK_POPULATION_SCOPE_SHA256:?submit with the exact scope SHA-256}"
: "${BENCHMARK_EXPECTED_SOURCE_COUNT:?submit with the authorized source count}"
: "${BENCHMARK_OUTPUT_DIRECTORY:?submit with the new controlled benchmark output path}"

readonly INTEGRATION_ROOT="$(realpath -e -- "${BENCHMARK_INTEGRATION_ROOT}")"
readonly SOURCE_ROOT="$(realpath -e -- "${BENCHMARK_SOURCE_ROOT}")"
readonly POPULATION_SCOPE="$(realpath -e -- "${BENCHMARK_POPULATION_SCOPE}")"
readonly OUTPUT_DIRECTORY="$(realpath -m -- "${BENCHMARK_OUTPUT_DIRECTORY}")"
readonly DATA_ROOT="/work/footprint/donyadidegan/safe_geocoding_pipeline"

cd "${INTEGRATION_ROOT}"
source "${DATA_ROOT}/.venv-goethe-nhr/bin/activate"
export PYTHONPATH="${INTEGRATION_ROOT}/src"
export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1

readonly ACTUAL_COMMIT="$(git rev-parse HEAD)"
[[ "${ACTUAL_COMMIT}" == "${BENCHMARK_GIT_COMMIT}" ]] || {
  echo "BENCHMARK_GIT_COMMIT_MISMATCH" >&2
  exit 1
}
[[ -z "$(git status --porcelain)" ]] || {
  echo "BENCHMARK_WORKTREE_NOT_CLEAN" >&2
  exit 1
}
[[ "$(git symbolic-ref -q HEAD || true)" == "" ]] || {
  echo "BENCHMARK_WORKTREE_NOT_DETACHED" >&2
  exit 1
}

echo "job_id=${SLURM_JOB_ID}"
echo "git_commit=${ACTUAL_COMMIT}"
echo "benchmark_contract=benchmark_sample_contract_v1"
echo "holdout_access_policy=PROGRAMMATIC_MATERIALIZATION_ONLY_NO_DISPLAY"

safe-geocoding-benchmark-sample \
  --source-root "${SOURCE_ROOT}" \
  --population-scope-file "${POPULATION_SCOPE}" \
  --expected-population-scope-sha256 "${BENCHMARK_POPULATION_SCOPE_SHA256}" \
  --expected-source-count "${BENCHMARK_EXPECTED_SOURCE_COUNT}" \
  --output-directory "${OUTPUT_DIRECTORY}" \
  --adopting-git-commit "${BENCHMARK_GIT_COMMIT}"

echo "BENCHMARK_SAMPLE_V1_MATERIALIZATION_PASS"
