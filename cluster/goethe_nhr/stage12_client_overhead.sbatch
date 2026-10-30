#!/usr/bin/env bash
#SBATCH --job-name=safe-stage12-offline-overhead
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
: "${STAGE12_DIAGNOSTIC_SHA:?reviewed exact pushed SHA required}"
: "${STAGE12_DIAGNOSTIC_CHECKOUT:?detached checkout required}"
: "${STAGE12_DIAGNOSTIC_BASELINE:?baseline checkout required}"
: "${STAGE12_DIAGNOSTIC_INPUT:?synthetic input required}"
: "${STAGE12_DIAGNOSTIC_OUTPUT:?new private output required}"
readonly stage12_project=/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline
readonly stage12_python="${stage12_project}/runtimes/stage06/stage06_development_20260828T223804Z_f39047cc825d/venv/bin/python"
readonly stage12_input_sha=5f5022502f0ac6d053739c2292d3b88bb25881e20d24fd9d0a0da5d1749dccf9
[[ "${SLURM_RESTART_COUNT:-0}" == 0 ]]
[[ "${STAGE12_DIAGNOSTIC_SHA}" =~ ^[a-f0-9]{40}$ ]]
[[ "$(dirname -- "${STAGE12_DIAGNOSTIC_CHECKOUT}")" == "${stage12_project}/integration_stage12" ]]
[[ "$(dirname -- "${STAGE12_DIAGNOSTIC_BASELINE}")" == "${stage12_project}/integration_stage12" ]]
[[ "$(dirname -- "${STAGE12_DIAGNOSTIC_OUTPUT}")" == "${stage12_project}/derived/controlled/stage12/client_diagnostics" ]]
[[ "$(git -C "${STAGE12_DIAGNOSTIC_CHECKOUT}" rev-parse HEAD)" == "${STAGE12_DIAGNOSTIC_SHA}" ]]
[[ "$(git -C "${STAGE12_DIAGNOSTIC_BASELINE}" rev-parse HEAD)" == 127b1e8babe4730e5ca9cf1244e2ba23394cc2d9 ]]
for stage12_tree in "${STAGE12_DIAGNOSTIC_BASELINE}" "${STAGE12_DIAGNOSTIC_CHECKOUT}"; do
  [[ -z "$(git -C "${stage12_tree}" status --porcelain)" ]]
  [[ "$(realpath -e -- "${stage12_tree}")" == "${stage12_tree}" ]]
done
[[ "$(sha256sum "${STAGE12_DIAGNOSTIC_INPUT}" | cut -d' ' -f1)" == "${stage12_input_sha}" ]]
[[ -x "${stage12_python}" && ! -e "${STAGE12_DIAGNOSTIC_OUTPUT}" ]]
mkdir -m 0700 "${STAGE12_DIAGNOSTIC_OUTPUT}"
unset SAFE_PELIAS_API_KEY SAFE_PELIAS_API_KEY_FILE
export SAFE_EXECUTION_SITE=goethe-nhr PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONHASHSEED=0
export LANG=C.UTF-8 LC_ALL=C.UTF-8 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
unset PYTHONPATH
stage12_start_seconds=$SECONDS
for stage12_label in baseline candidate; do
  stage12_source="${STAGE12_DIAGNOSTIC_BASELINE}"
  [[ "${stage12_label}" != candidate ]] || stage12_source="${STAGE12_DIAGNOSTIC_CHECKOUT}"
  set +e
  timeout --signal=TERM --kill-after=5s 250s "${stage12_python}" -B \
    "${STAGE12_DIAGNOSTIC_CHECKOUT}/scripts/stage12_client_overhead_diagnostic.py" \
    --input "${STAGE12_DIAGNOSTIC_INPUT}" --input-sha256 "${stage12_input_sha}" \
    --source "${stage12_source}" --output "${STAGE12_DIAGNOSTIC_OUTPUT}/${stage12_label}" \
    > "${STAGE12_DIAGNOSTIC_OUTPUT}/${stage12_label}.out" \
    2> "${STAGE12_DIAGNOSTIC_OUTPUT}/${stage12_label}.err"
  stage12_exit=$?
  set -e
  printf '%s\n' "${stage12_exit}" > "${STAGE12_DIAGNOSTIC_OUTPUT}/${stage12_label}.exit"
  [[ $((SECONDS - stage12_start_seconds)) -lt 600 ]]
done
printf '%s\n' "$((SECONDS - stage12_start_seconds))" > "${STAGE12_DIAGNOSTIC_OUTPUT}/elapsed_seconds"
[[ "$(cat "${STAGE12_DIAGNOSTIC_OUTPUT}/baseline.exit")" == 0 && "$(cat "${STAGE12_DIAGNOSTIC_OUTPUT}/candidate.exit")" == 0 ]]
