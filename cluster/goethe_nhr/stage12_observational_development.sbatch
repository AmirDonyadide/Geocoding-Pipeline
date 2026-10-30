#!/usr/bin/env bash
#SBATCH --job-name=safe-stage12-observational
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --no-requeue
# Partition/account/time/memory/CPU/spill and controlled log paths must be
# supplied by the separately authorized, measured workload submission.
set -euo pipefail
umask 077
: "${SLURM_JOB_ID:?scheduled execution required}"
: "${STAGE12_EXECUTION_GIT_SHA:?exact reviewed pushed source SHA required}"
: "${STAGE12_CHECKOUT:?exact clean checkout required}"
: "${STAGE12_PYTHON:?reviewed existing runtime required}"
: "${STAGE12_CONFIGURATION:?exact phase input file required}"
: "${STAGE12_CONFIGURATION_SHA256:?phase input identity required}"
: "${STAGE12_RUNTIME_PORT:?separately reviewed integration port required}"
: "${STAGE12_RUNTIME_PORT_SHA256:?integration source identity required}"
: "${STAGE12_AUTHORIZATION_SHA256:?phase-specific issued authority required}"
: "${STAGE12_PHASE:?explicit phase required}"
: "${STAGE12_OUTPUT:?new controlled immutable output required}"
: "${STAGE12_SCRATCH:?new controlled workspace required}"
: "${STAGE12_PRIVATE_SPILL:?existing controlled spill directory required}"
[[ "${SLURM_RESTART_COUNT:-0}" == 0 ]]
[[ "${STAGE12_EXECUTION_GIT_SHA}" =~ ^[a-f0-9]{40}$ ]]
cd -- "${STAGE12_CHECKOUT}"
[[ "$(git rev-parse HEAD)" == "${STAGE12_EXECUTION_GIT_SHA}" ]]
[[ -z "$(git status --porcelain)" ]]
export SAFE_EXECUTION_SITE=goethe-nhr PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONHASHSEED=0
export PYTHONPATH="${STAGE12_CHECKOUT}/src"
export SQLITE_TMPDIR="${STAGE12_PRIVATE_SPILL}"
"${STAGE12_PYTHON}" -B -m safe_geocoding_pipeline.preprocessing.stage12_development_cli \
  "${STAGE12_PHASE}" --configuration "${STAGE12_CONFIGURATION}" \
  --configuration-sha256 "${STAGE12_CONFIGURATION_SHA256}" \
  --runtime-port "${STAGE12_RUNTIME_PORT}" --runtime-port-sha256 "${STAGE12_RUNTIME_PORT_SHA256}" \
  --authorization-sha256 "${STAGE12_AUTHORIZATION_SHA256}" \
  --output "${STAGE12_OUTPUT}" --scratch "${STAGE12_SCRATCH}"
