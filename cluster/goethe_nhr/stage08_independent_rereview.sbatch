#!/usr/bin/env bash
#SBATCH --job-name=safe-stage08-independent-rereview
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
: "${SLURM_JOB_NAME:?SLURM_JOB_NAME is required}"
: "${STAGE08_REVIEW_GIT_SHA:?exact pushed review SHA is required}"
: "${STAGE08_REVIEW_INTEGRATION_ROOT:?clean detached review worktree is required}"
: "${STAGE08_REVIEW_RUNTIME_ROOT:?validated controlled runtime is required}"
: "${STAGE08_REVIEW_OUTPUT_DIRECTORY:?new review evidence directory is required}"

readonly DATA_ROOT="$(realpath -e -- /work/footprint/donyadidegan/safe_geocoding_pipeline)"
readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE08_REVIEW_INTEGRATION_ROOT}")"
readonly RUNTIME_ROOT="$(realpath -e -- "${STAGE08_REVIEW_RUNTIME_ROOT}")"
readonly OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE08_REVIEW_OUTPUT_DIRECTORY}")"
readonly ARTIFACT_ROOT="${DATA_ROOT}/derived/controlled/stage08/development/stage08_development_20260902T132726Z_c04cb97214a9"
readonly STAGE07_ROOT="${DATA_ROOT}/derived/controlled/stage07/evidence_only_development/stage07_evidence_e684d84_attempt1"
readonly STAGE06_ROOT="${DATA_ROOT}/derived/controlled/stage06/development/stage06_development_20260828T223804Z_f39047cc825d"
readonly REVIEW_PARENT="${DATA_ROOT}/derived/controlled/reviews/stage08/development"

for controlled_path in \
  "${INTEGRATION_ROOT}" \
  "${RUNTIME_ROOT}" \
  "${ARTIFACT_ROOT}" \
  "${STAGE07_ROOT}" \
  "${STAGE06_ROOT}" \
  "${OUTPUT_DIRECTORY}"; do
  [[ "${controlled_path}" == "${DATA_ROOT}"/* ]] || { echo "CONTROLLED_PATH_REQUIRED" >&2; exit 1; }
  [[ "${controlled_path,,}" != *holdout* ]] || { echo "HOLDOUT_ACCESS_PROHIBITED" >&2; exit 1; }
  [[ "${controlled_path,,}" != *production* ]] || { echo "PRODUCTION_ACCESS_PROHIBITED" >&2; exit 1; }
done
[[ "${OUTPUT_DIRECTORY}" == "${REVIEW_PARENT}"/* ]]
[[ ! -e "${OUTPUT_DIRECTORY}" ]]

readonly LOG_ROOT="${DATA_ROOT}/logs/slurm"
readonly JOB_STDOUT="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.out"
readonly JOB_STDERR="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.err"
chmod 0600 "${JOB_STDOUT}" "${JOB_STDERR}"

cd "${INTEGRATION_ROOT}"
[[ "$(git rev-parse HEAD)" == "${STAGE08_REVIEW_GIT_SHA}" ]]
[[ -z "$(git status --porcelain)" ]]
[[ "$(git symbolic-ref -q HEAD || true)" == "" ]]
git merge-base --is-ancestor 231cdbf9db755fb56486c46b3b3faa02f5b5f3b6 "${STAGE08_REVIEW_GIT_SHA}"
git diff --quiet \
  c04cb97214a9f1e5d2b80512c756400321eefa80 \
  231cdbf9db755fb56486c46b3b3faa02f5b5f3b6 \
  -- src tests ':(glob)cluster/**/*.sbatch' pyproject.toml uv.lock

readonly PRODUCER_RECORD="$(sacct -n -X -j 1764273 --format=JobIDRaw,State,ExitCode -P | sed -n '1p')"
IFS='|' read -r producer_job producer_state producer_exit <<< "${PRODUCER_RECORD}"
[[ "${producer_job}" == "1764273" ]]
[[ "${producer_state}" == "COMPLETED" ]]
[[ "${producer_exit}" == "0:0" ]]
readonly PRODUCER_STDERR="${LOG_ROOT}/safe-stage08-address-evidence_1764273.err"
[[ -f "${PRODUCER_STDERR}" ]]
[[ ! -s "${PRODUCER_STDERR}" ]]

readonly PYTHON="${RUNTIME_ROOT}/venv/bin/python"
[[ -x "${PYTHON}" ]]
export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1
export PYTHONHASHSEED=0
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export STAGE08_PRODUCER_STDERR_EMPTY=true

echo "review_job_id=${SLURM_JOB_ID}"
echo "review_git_sha=${STAGE08_REVIEW_GIT_SHA}"
echo "candidate_sha=231cdbf9db755fb56486c46b3b3faa02f5b5f3b6"
echo "executable_sha=c04cb97214a9f1e5d2b80512c756400321eefa80"
echo "requested_cpus=2"
echo "requested_memory_gib=16"
echo "requested_walltime=02:00:00"
echo "review_only=true"
echo "holdout_access=false"
echo "production_access=false"

"${PYTHON}" -B review/stage08_protected_independent_rereview.py
