#!/usr/bin/env bash
#SBATCH --job-name=safe-stage12-public-probe
#SBATCH --partition=general1
#SBATCH --account=footprint
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=6G
#SBATCH --time=00:30:00
#SBATCH --no-requeue
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077
ulimit -c 0
: "${SLURM_JOB_ID:?scheduled execution required}"
: "${STAGE12_EXECUTION_GIT_SHA:?exact pushed executable required}"
: "${STAGE12_CHECKOUT:?clean detached checkout required}"
: "${STAGE12_PUBLIC_PROBE_CONFIGURATION:?approved private configuration required}"
# Presence only: the secret is never expanded into a command argument or log.
[[ -n "${SAFE_PELIAS_API_KEY:-}" ]]
readonly stage12_project=/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline
readonly stage12_python="${stage12_project}/runtimes/stage06/stage06_development_20260828T223804Z_f39047cc825d/venv/bin/python"
[[ "${SLURM_RESTART_COUNT:-0}" == 0 ]]
[[ "${STAGE12_EXECUTION_GIT_SHA}" =~ ^[a-f0-9]{40}$ ]]
[[ "$(dirname -- "${STAGE12_CHECKOUT}")" == "${stage12_project}/integration_stage12" ]]
[[ "$(realpath -e -- "${STAGE12_CHECKOUT}")" == "${STAGE12_CHECKOUT}" ]]
[[ "$(dirname -- "${STAGE12_PUBLIC_PROBE_CONFIGURATION}")" == "${stage12_project}/derived/controlled/stage12/probe_configuration" ]]
[[ "$(realpath -e -- "${STAGE12_PUBLIC_PROBE_CONFIGURATION}")" == "${STAGE12_PUBLIC_PROBE_CONFIGURATION}" ]]
[[ -x "${stage12_python}" ]]
cd "${STAGE12_CHECKOUT}"
[[ "$(git rev-parse HEAD)" == "${STAGE12_EXECUTION_GIT_SHA}" ]]
[[ -z "$(git status --porcelain)" && -z "$(git symbolic-ref -q HEAD || true)" ]]
git merge-base --is-ancestor 7543b8bac4f2953aab311fb58f73dbcb62ba401b HEAD
chmod 0600 "${stage12_project}/logs/slurm/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.out" \
  "${stage12_project}/logs/slurm/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.err"
export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONHASHSEED=0
export LANG=C.UTF-8 LC_ALL=C.UTF-8 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export PYTHONPATH="${STAGE12_CHECKOUT}/src"
# One manually submitted public/invented workload. No protected input reader,
# dynamic pull, automatic job submission, requeue or protected parameter choice.
"${stage12_python}" -B -m safe_geocoding_pipeline.preprocessing.stage12_probe_cli \
  --configuration "${STAGE12_PUBLIC_PROBE_CONFIGURATION}" \
  --implementation-sha "${STAGE12_EXECUTION_GIT_SHA}"
