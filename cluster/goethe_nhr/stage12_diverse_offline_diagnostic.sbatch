#!/usr/bin/env bash
#SBATCH --job-name=safe-stage12-diverse-offline
#SBATCH --partition=general1
#SBATCH --account=footprint
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=6G
#SBATCH --time=00:12:00
#SBATCH --no-requeue
set -euo pipefail
umask 077
ulimit -c 0
: "${SLURM_JOB_ID:?compute allocation required}"
: "${STAGE12_DIAGNOSTIC_SHA:?exact reviewed pushed SHA}"
: "${STAGE12_DIAGNOSTIC_CHECKOUT:?clean detached checkout}"
: "${STAGE12_DIAGNOSTIC_INPUT:?exact synthetic input}"
: "${STAGE12_DIAGNOSTIC_INPUT_SHA256:?reviewed input hash}"
: "${STAGE12_DIAGNOSTIC_OUTPUT:?fresh private output}"
readonly stage12_project=/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline
readonly stage12_python="${stage12_project}/runtimes/stage06/stage06_development_20260828T223804Z_f39047cc825d/venv/bin/python"
[[ "${SLURM_RESTART_COUNT:-0}" == 0 ]]
[[ "${STAGE12_DIAGNOSTIC_SHA}" =~ ^[a-f0-9]{40}$ ]]
[[ "${STAGE12_DIAGNOSTIC_INPUT_SHA256}" =~ ^[a-f0-9]{64}$ ]]
[[ "$(dirname -- "${STAGE12_DIAGNOSTIC_CHECKOUT}")" == "${stage12_project}/integration_stage12" ]]
[[ "$(dirname -- "${STAGE12_DIAGNOSTIC_OUTPUT}")" == "${stage12_project}/derived/controlled/stage12/client_diagnostics" ]]
[[ "$(dirname -- "${STAGE12_DIAGNOSTIC_INPUT}")" == "${stage12_project}/derived/controlled/stage12/client_diagnostics" ]]
[[ "$(realpath -e -- "${STAGE12_DIAGNOSTIC_CHECKOUT}")" == "${STAGE12_DIAGNOSTIC_CHECKOUT}" ]]
[[ "$(git -C "${STAGE12_DIAGNOSTIC_CHECKOUT}" rev-parse HEAD)" == "${STAGE12_DIAGNOSTIC_SHA}" ]]
[[ -z "$(git -C "${STAGE12_DIAGNOSTIC_CHECKOUT}" status --porcelain)" ]]
[[ -z "$(git -C "${STAGE12_DIAGNOSTIC_CHECKOUT}" symbolic-ref -q HEAD || true)" ]]
[[ "$(sha256sum "${STAGE12_DIAGNOSTIC_INPUT}" | cut -d' ' -f1)" == "${STAGE12_DIAGNOSTIC_INPUT_SHA256}" ]]
[[ -x "${stage12_python}" && ! -e "${STAGE12_DIAGNOSTIC_OUTPUT}" ]]
unset SAFE_PELIAS_API_KEY SAFE_PELIAS_API_KEY_FILE PYTHONPATH
export SAFE_EXECUTION_SITE=goethe-nhr PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONHASHSEED=0
export LANG=C.UTF-8 LC_ALL=C.UTF-8 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
PYTHONPATH="${STAGE12_DIAGNOSTIC_CHECKOUT}/src" "${stage12_python}" -B -c \
  'from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm; require_goethe_nhr_slurm("stage12 denied synthetic matrix diagnostic")'
set +e
timeout --signal=TERM --kill-after=5s 610s "${stage12_python}" -B \
  "${STAGE12_DIAGNOSTIC_CHECKOUT}/scripts/stage12_diverse_offline_diagnostic.py" \
  --input "${STAGE12_DIAGNOSTIC_INPUT}" --input-sha256 "${STAGE12_DIAGNOSTIC_INPUT_SHA256}" \
  --source "${STAGE12_DIAGNOSTIC_CHECKOUT}" --output "${STAGE12_DIAGNOSTIC_OUTPUT}"
stage12_exit=$?
set -e
exit "${stage12_exit}"
