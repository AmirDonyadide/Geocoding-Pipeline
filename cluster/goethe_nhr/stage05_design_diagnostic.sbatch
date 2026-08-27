#!/usr/bin/env bash
#SBATCH --job-name=safe-stage05-design
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${STAGE05_DESIGN_GIT_COMMIT:?submit with the exact pushed diagnostic commit}"
: "${STAGE05_DESIGN_INTEGRATION_ROOT:?submit with an exact detached worktree}"
: "${STAGE05_DESIGN_STAGE04_ROOT:?submit with the accepted Stage 4 DEVELOPMENT bundle}"
: "${STAGE05_DESIGN_OUTPUT_DIRECTORY:?submit with a new protected diagnostic path}"

readonly DATA_ROOT="$(realpath -e -- \
  "/work/footprint/donyadidegan/safe_geocoding_pipeline")"
readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE05_DESIGN_INTEGRATION_ROOT}")"
readonly STAGE04_ROOT="$(realpath -e -- "${STAGE05_DESIGN_STAGE04_ROOT}")"
readonly OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE05_DESIGN_OUTPUT_DIRECTORY}")"

for controlled_path in "${INTEGRATION_ROOT}" "${STAGE04_ROOT}" "${OUTPUT_DIRECTORY}"; do
  [[ "${controlled_path}" == "${DATA_ROOT}"/* ]] || {
    echo "STAGE05_CONTROLLED_PATH_REQUIRED" >&2
    exit 1
  }
  [[ "${controlled_path,,}" != *holdout* ]] || {
    echo "HOLDOUT_ACCESS_PROHIBITED" >&2
    exit 1
  }
done

cd "${INTEGRATION_ROOT}"
readonly ACTUAL_COMMIT="$(git rev-parse HEAD)"
[[ "${ACTUAL_COMMIT}" == "${STAGE05_DESIGN_GIT_COMMIT}" ]] || {
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

readonly PYTHON="${DATA_ROOT}/.venv-goethe-nhr/bin/python"
[[ -x "${PYTHON}" ]] || {
  echo "STAGE05_RUNTIME_NOT_READY" >&2
  exit 1
}
export PYTHONPATH="${INTEGRATION_ROOT}/src"
export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1

echo "job_id=${SLURM_JOB_ID}"
echo "git_commit=${ACTUAL_COMMIT}"
"${PYTHON}" -m safe_geocoding_pipeline.preprocessing.stage05_design_cli \
  --stage04-output-directory "${STAGE04_ROOT}" \
  --expected-stage04-manifest-sha256 \
    "17a4854cddd8929b65ea79402f1a4f12a1574b720c1921567b577f23e152d1f3" \
  --output-directory "${OUTPUT_DIRECTORY}" \
  --execution-git-sha "${ACTUAL_COMMIT}"

echo "STAGE05_DESIGN_DIAGNOSTIC_PASS"
