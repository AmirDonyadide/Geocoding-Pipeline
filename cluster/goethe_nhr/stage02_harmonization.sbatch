#!/usr/bin/env bash
#SBATCH --job-name=safe-stage02
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=04:00:00
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${STAGE02_GIT_COMMIT:?submit with the exact reviewed Stage 2 commit}"
: "${STAGE02_INTEGRATION_ROOT:?submit with an exact detached integration worktree}"
: "${STAGE02_INPUT_ROOT:?submit with the protected Stage 1 or DEVELOPMENT input root}"
: "${STAGE02_INPUT_BINDING:?submit with the protected Stage 2 input binding}"
: "${STAGE02_INPUT_BINDING_SHA256:?submit with the exact input-binding SHA-256}"
: "${STAGE02_OUTPUT_DIRECTORY:?submit with a new controlled output path}"

readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE02_INTEGRATION_ROOT}")"
readonly INPUT_ROOT="$(realpath -e -- "${STAGE02_INPUT_ROOT}")"
readonly INPUT_BINDING="$(realpath -e -- "${STAGE02_INPUT_BINDING}")"
readonly OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE02_OUTPUT_DIRECTORY}")"
readonly DATA_ROOT="/work/footprint/donyadidegan/safe_geocoding_pipeline"

cd "${INTEGRATION_ROOT}"
source "${DATA_ROOT}/.venv-goethe-nhr/bin/activate"
export PYTHONPATH="${INTEGRATION_ROOT}/src"
export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1

readonly ACTUAL_COMMIT="$(git rev-parse HEAD)"
[[ "${ACTUAL_COMMIT}" == "${STAGE02_GIT_COMMIT}" ]] || {
  echo "STAGE02_GIT_COMMIT_MISMATCH" >&2
  exit 1
}
[[ -z "$(git status --porcelain)" ]] || {
  echo "STAGE02_WORKTREE_NOT_CLEAN" >&2
  exit 1
}
[[ "$(git symbolic-ref -q HEAD || true)" == "" ]] || {
  echo "STAGE02_WORKTREE_NOT_DETACHED" >&2
  exit 1
}

echo "job_id=${SLURM_JOB_ID}"
echo "git_commit=${ACTUAL_COMMIT}"
echo "stage02_contract=stage02_schema_provenance_harmonization_contract_v1"

python -m safe_geocoding_pipeline.preprocessing.stage02_cli \
  --input-root "${INPUT_ROOT}" \
  --input-binding "${INPUT_BINDING}" \
  --expected-input-binding-sha256 "${STAGE02_INPUT_BINDING_SHA256}" \
  --output-directory "${OUTPUT_DIRECTORY}" \
  --adopting-git-commit "${STAGE02_GIT_COMMIT}"

echo "STAGE02_HARMONIZATION_PASS"
