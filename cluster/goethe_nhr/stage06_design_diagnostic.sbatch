#!/usr/bin/env bash
#SBATCH --job-name=safe-stage06-design
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${SLURM_JOB_NAME:?SLURM_JOB_NAME is required}"
: "${STAGE06_DESIGN_GIT_COMMIT:?submit with the exact pushed diagnostic commit}"
: "${STAGE06_DESIGN_INTEGRATION_ROOT:?submit with an exact detached worktree}"
: "${STAGE06_DESIGN_RUNTIME_ROOT:?submit with a new owner-only runtime root}"
: "${STAGE06_DESIGN_STAGE05_ROOT:?submit with the accepted Stage 5 DEVELOPMENT bundle}"
: "${STAGE06_DESIGN_OUTPUT_DIRECTORY:?submit with a new protected diagnostic path}"

readonly ACCEPTED_STAGE05_MANIFEST="fd945163e3be0242c43b98972350904631279cb99f366baadb0a3094ab6a1fc5"
readonly LOG_ROOT="/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm"
readonly JOB_STDOUT="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.out"
readonly JOB_STDERR="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.err"
chmod 0600 "${JOB_STDOUT}" "${JOB_STDERR}"
[[ "$(stat -c %a "${JOB_STDOUT}")" == "600" ]]
[[ "$(stat -c %a "${JOB_STDERR}")" == "600" ]]

readonly DATA_ROOT="$(realpath -e -- \
  "/work/footprint/donyadidegan/safe_geocoding_pipeline")"
readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE06_DESIGN_INTEGRATION_ROOT}")"
readonly RUNTIME_ROOT="$(realpath -m -- "${STAGE06_DESIGN_RUNTIME_ROOT}")"
readonly STAGE05_ROOT="$(realpath -e -- "${STAGE06_DESIGN_STAGE05_ROOT}")"
readonly OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE06_DESIGN_OUTPUT_DIRECTORY}")"

for controlled_path in \
  "${INTEGRATION_ROOT}" \
  "${RUNTIME_ROOT}" \
  "${STAGE05_ROOT}" \
  "${OUTPUT_DIRECTORY}"; do
  [[ "${controlled_path}" == "${DATA_ROOT}"/* ]] || {
    echo "STAGE06_CONTROLLED_PATH_REQUIRED" >&2
    exit 1
  }
  [[ "${controlled_path,,}" != *holdout* ]] || {
    echo "HOLDOUT_ACCESS_PROHIBITED" >&2
    exit 1
  }
done

cd "${INTEGRATION_ROOT}"
readonly ACTUAL_COMMIT="$(git rev-parse HEAD)"
[[ "${ACTUAL_COMMIT}" == "${STAGE06_DESIGN_GIT_COMMIT}" ]] || {
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
"${PYTHON}" -m safe_geocoding_pipeline.preprocessing.stage06_design_cli \
  --stage05-output-directory "${STAGE05_ROOT}" \
  --expected-stage05-manifest-sha256 "${ACCEPTED_STAGE05_MANIFEST}" \
  --output-directory "${OUTPUT_DIRECTORY}" \
  --execution-git-sha "${ACTUAL_COMMIT}" \
  --duckdb-memory-limit 8GB \
  --duckdb-threads 4

echo "STAGE06_DESIGN_DIAGNOSTIC_PASS"
