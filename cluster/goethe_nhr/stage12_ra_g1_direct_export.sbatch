#!/usr/bin/env bash
#SBATCH --job-name=safe-stage12-direct-export
#SBATCH --partition=general1
#SBATCH --account=footprint
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:30:00
#SBATCH --no-requeue
set -euo pipefail
umask 077
ulimit -c 0
: "${STAGE12_DR_SOURCE:?}" "${STAGE12_DR_SHA:?}" "${STAGE12_DR_PYTHON:?}"
: "${STAGE12_DR_PLAN:?}" "${STAGE12_DR_PLAN_SHA:?}" "${STAGE12_DR_OUTPUT:?}"
: "${STAGE12_DR_WINDOW_END_NS:?}" "${STAGE12_DR_EXPORT_END_NS:?}"
export SAFE_EXECUTION_SITE=goethe-nhr PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
unset SAFE_PELIAS_API_KEY SAFE_PELIAS_API_KEY_FILE PYTHONPATH
cd -- "$STAGE12_DR_SOURCE"
[[ "$(git rev-parse HEAD)" == "$STAGE12_DR_SHA" ]]
[[ -z "$(git status --porcelain)" ]]
export PYTHONPATH="$STAGE12_DR_SOURCE/src"
# One guarded exporter, no receiver, paired parent, READY or receipt protocol.
exec "$STAGE12_DR_PYTHON" -B scripts/stage12_ra_g1_direct_recovery.py export \
  --plan "$STAGE12_DR_PLAN" --plan-sha256 "$STAGE12_DR_PLAN_SHA" \
  --output "$STAGE12_DR_OUTPUT" --window-end-epoch-ns "$STAGE12_DR_WINDOW_END_NS" \
  --export-end-epoch-ns "$STAGE12_DR_EXPORT_END_NS"
