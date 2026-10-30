#!/usr/bin/env bash
#SBATCH --job-name=safe-stage12-or2-public
#SBATCH --partition=general1
#SBATCH --account=footprint
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
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
: "${STAGE12_OR2_BUNDLE:?reviewed private evidence directory required}"
: "${STAGE12_OR2_CONFIGURATION_SHA256:?exact reviewed configuration required}"
: "${STAGE12_OR2_REVIEW_SHA256:?exact independent review binding required}"
readonly stage12_project=/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline
readonly stage12_python="${stage12_project}/runtimes/stage06/stage06_development_20260828T223804Z_f39047cc825d/venv/bin/python"
[[ "${SLURM_RESTART_COUNT:-0}" == 0 ]]
[[ "${STAGE12_EXECUTION_GIT_SHA}" =~ ^[a-f0-9]{40}$ ]]
[[ "${STAGE12_OR2_CONFIGURATION_SHA256}" =~ ^[a-f0-9]{64}$ ]]
[[ "${STAGE12_OR2_REVIEW_SHA256}" =~ ^[a-f0-9]{64}$ ]]
[[ "$(dirname -- "${STAGE12_CHECKOUT}")" == "${stage12_project}/integration_stage12" ]]
[[ "$(realpath -e -- "${STAGE12_CHECKOUT}")" == "${STAGE12_CHECKOUT}" ]]
[[ "$(dirname -- "${STAGE12_OR2_BUNDLE}")" == "${stage12_project}/derived/controlled/stage12/public_or2_configuration" ]]
[[ "$(realpath -e -- "${STAGE12_OR2_BUNDLE}")" == "${STAGE12_OR2_BUNDLE}" ]]
[[ -x "${stage12_python}" ]]
cd "${STAGE12_CHECKOUT}"
[[ "$(git rev-parse HEAD)" == "${STAGE12_EXECUTION_GIT_SHA}" ]]
[[ -z "$(git status --porcelain)" && -z "$(git symbolic-ref -q HEAD || true)" ]]
git merge-base --is-ancestor c6b6d3ce34e42216712ed6fd6dfcef0f48bcfe13 HEAD
chmod 0600 "${stage12_project}/logs/slurm/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.out" \
  "${stage12_project}/logs/slurm/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.err"
# Only the provider path is exposed to the process; no shell credential read.
unset SAFE_PELIAS_API_KEY
export SAFE_PELIAS_API_KEY_FILE="${HOME}/.config/safe-geocoding/pelias_api_key"
export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONHASHSEED=0
export LANG=C.UTF-8 LC_ALL=C.UTF-8 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export PYTHONPATH="${STAGE12_CHECKOUT}/src"
"${stage12_python}" -B -m safe_geocoding_pipeline.preprocessing.stage12_operations_cli \
  --configuration "${STAGE12_OR2_BUNDLE}/configuration.json" \
  --configuration-sha256 "${STAGE12_OR2_CONFIGURATION_SHA256}" \
  --review-binding "${STAGE12_OR2_BUNDLE}/review_binding.json" \
  --review-binding-sha256 "${STAGE12_OR2_REVIEW_SHA256}" \
  --implementation-sha "${STAGE12_EXECUTION_GIT_SHA}"
