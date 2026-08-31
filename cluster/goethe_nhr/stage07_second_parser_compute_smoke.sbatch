#!/usr/bin/env bash
#SBATCH --job-name=safe-stage07-second-smoke
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${SLURM_JOB_NAME:?SLURM_JOB_NAME is required}"
: "${STAGE07_SECOND_SMOKE_GIT_COMMIT:?exact pushed commit is required}"
: "${STAGE07_SECOND_SMOKE_INTEGRATION_ROOT:?clean detached worktree is required}"
: "${STAGE07_SECOND_SMOKE_BUNDLE_DIRECTORY:?immutable bundle is required}"
: "${STAGE07_SECOND_SMOKE_BUNDLE_FINGERPRINT:?bundle fingerprint is required}"
: "${STAGE07_SECOND_SMOKE_OUTPUT_DIRECTORY:?new output is required}"
: "${STAGE07_SECOND_SMOKE_RUNTIME_ROOT:?new runtime root is required}"

export SAFE_EXECUTION_SITE=goethe-nhr

readonly DATA_ROOT="$(realpath -e -- /work/footprint/donyadidegan/safe_geocoding_pipeline)"
readonly BASE_PYTHON="${DATA_ROOT}/.venv-goethe-nhr/bin/python"
readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE07_SECOND_SMOKE_INTEGRATION_ROOT}")"
readonly BUNDLE_DIRECTORY="$(realpath -e -- "${STAGE07_SECOND_SMOKE_BUNDLE_DIRECTORY}")"
readonly OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE07_SECOND_SMOKE_OUTPUT_DIRECTORY}")"
readonly RUNTIME_ROOT="$(realpath -m -- "${STAGE07_SECOND_SMOKE_RUNTIME_ROOT}")"

for controlled_path in \
  "${INTEGRATION_ROOT}" \
  "${BUNDLE_DIRECTORY}" \
  "${OUTPUT_DIRECTORY}" \
  "${RUNTIME_ROOT}"; do
  [[ "${controlled_path}" == "${DATA_ROOT}"/* ]] || {
    echo "STAGE07_CONTROLLED_PATH_REQUIRED" >&2
    exit 1
  }
  [[ "${controlled_path,,}" != *holdout* ]] || {
    echo "HOLDOUT_ACCESS_PROHIBITED" >&2
    exit 1
  }
done
[[ ! -e "${OUTPUT_DIRECTORY}" ]]
[[ ! -e "${RUNTIME_ROOT}" ]]

readonly LOG_ROOT="${DATA_ROOT}/logs/slurm"
readonly JOB_STDOUT="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.out"
readonly JOB_STDERR="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.err"
chmod 0600 "${JOB_STDOUT}" "${JOB_STDERR}"
[[ "$(stat -c %a "${JOB_STDOUT}")" == "600" ]]
[[ "$(stat -c %a "${JOB_STDERR}")" == "600" ]]

cd "${INTEGRATION_ROOT}"
[[ "$(git rev-parse HEAD)" == "${STAGE07_SECOND_SMOKE_GIT_COMMIT}" ]]
[[ -z "$(git status --porcelain)" ]]
[[ "$(git symbolic-ref -q HEAD || true)" == "" ]]

install -d -m 0700 "${RUNTIME_ROOT}"
export TMPDIR="${RUNTIME_ROOT}/tmp"
install -d -m 0700 "${TMPDIR}"
export PYTHONPATH="${INTEGRATION_ROOT}/src"

"${BASE_PYTHON}" \
  -m safe_geocoding_pipeline.preprocessing.stage07_second_parser_bundle_cli validate \
  --output-directory "${BUNDLE_DIRECTORY}" \
  --expected-second-parser-bundle-fingerprint \
    "${STAGE07_SECOND_SMOKE_BUNDLE_FINGERPRINT}"

readonly SECOND_PYTHON="${BUNDLE_DIRECTORY}/runtime/bin/python3.13"
[[ -x "${SECOND_PYTHON}" ]]
export HF_HOME="${BUNDLE_DIRECTORY}/cache"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_HUB_DISABLE_TELEMETRY=1
export DO_NOT_TRACK=1
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1
export PYTHONHASHSEED=0
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export LANG=C.UTF-8
export LC_ALL=C.UTF-8

echo "job_id=${SLURM_JOB_ID}"
echo "git_commit=${STAGE07_SECOND_SMOKE_GIT_COMMIT}"
echo "scope=public_synthetic_compute_smoke"
echo "network_policy=offline_denied"
echo "protected_inputs_opened=false"

"${SECOND_PYTHON}" \
  -m safe_geocoding_pipeline.preprocessing.stages.s07_second_parser_smoke \
  --bundle "${BUNDLE_DIRECTORY}" \
  --bundle-fingerprint "${STAGE07_SECOND_SMOKE_BUNDLE_FINGERPRINT}" \
  --output "${OUTPUT_DIRECTORY}/stage07_second_parser_compute_smoke.json"

echo "STAGE07_SECOND_PARSER_COMPUTE_SMOKE_PASS"
