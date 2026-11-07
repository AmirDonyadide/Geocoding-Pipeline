#!/usr/bin/env bash
#SBATCH --job-name=safe-stage12-ap1-facts
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
: "${STAGE12_FACTS_SHA:?exact pushed source}"
: "${STAGE12_FACTS_CHECKOUT:?clean detached checkout}"
: "${STAGE12_FACTS_INPUT:?canonical input}"
: "${STAGE12_FACTS_INPUT_SHA256:?input hash}"
: "${STAGE12_FACTS_OUTPUT:?fresh private output}"
readonly project=/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline
readonly python="${project}/runtimes/stage06/stage06_development_20260828T223804Z_f39047cc825d/venv/bin/python"
readonly started_ns="$("${python}" -B -c 'import time;print(time.monotonic_ns())')"
[[ "${SLURM_RESTART_COUNT:-0}" == 0 ]]
[[ "${STAGE12_FACTS_SHA}" =~ ^[a-f0-9]{40}$ && "${STAGE12_FACTS_INPUT_SHA256}" =~ ^[a-f0-9]{64}$ ]]
[[ "$(dirname -- "${STAGE12_FACTS_CHECKOUT}")" == "${project}/integration_stage12" ]]
[[ "$(realpath -e -- "${STAGE12_FACTS_CHECKOUT}")" == "${STAGE12_FACTS_CHECKOUT}" ]]
[[ "$(git -C "${STAGE12_FACTS_CHECKOUT}" rev-parse HEAD)" == "${STAGE12_FACTS_SHA}" ]]
[[ -z "$(git -C "${STAGE12_FACTS_CHECKOUT}" status --porcelain)" ]]
[[ -z "$(git -C "${STAGE12_FACTS_CHECKOUT}" symbolic-ref -q HEAD || true)" ]]
[[ "$(dirname -- "${STAGE12_FACTS_INPUT}")" == "${project}/derived/controlled/stage12/client_diagnostics" ]]
[[ "$(dirname -- "${STAGE12_FACTS_OUTPUT}")" == "${project}/derived/controlled/stage12/client_diagnostics" ]]
[[ ! -e "${STAGE12_FACTS_OUTPUT}" ]]
# Exact private no-follow input read/hash/canonical parse occurs in the guarded child.
[[ -f "${STAGE12_FACTS_INPUT}" && ! -L "${STAGE12_FACTS_INPUT}" ]]
[[ "$(stat -c %a "${STAGE12_FACTS_INPUT}")" == 600 ]]
readonly remaining="$("${python}" -B -c 'import sys,time;print(max(1,(int(sys.argv[1])+605*10**9-time.monotonic_ns()+10**9-1)//10**9))' "${started_ns}")"
# Exact minimal environment: no service credential variables or user site.
# Internal600s includes setup/finalization; outer605s only terminates an overrun.
set +e
env -i PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
  SAFE_EXECUTION_SITE=goethe-nhr SLURM_JOB_ID="${SLURM_JOB_ID}" \
  PYTHONPATH="${STAGE12_FACTS_CHECKOUT}/src" PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 \
  PYTHONHASHSEED=0 PYTHONUTF8=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 ARROW_IO_THREADS=1 \
  timeout --signal=TERM --kill-after=5s "${remaining}s" "${python}" -B \
  "${STAGE12_FACTS_CHECKOUT}/scripts/stage12_ap1_runtime_facts.py" \
  --input "${STAGE12_FACTS_INPUT}" --input-sha256 "${STAGE12_FACTS_INPUT_SHA256}" \
  --source "${STAGE12_FACTS_CHECKOUT}" --source-sha "${STAGE12_FACTS_SHA}" \
  --output "${STAGE12_FACTS_OUTPUT}" --started-ns "${started_ns}"

result=$?
set -e
ended_ns="$("${python}" -B -c 'import time;print(time.monotonic_ns())')"
if (( ended_ns - started_ns >= 600000000000 )); then exit 95; fi
exit "${result}"
