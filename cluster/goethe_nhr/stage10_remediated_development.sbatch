#!/usr/bin/env bash
#SBATCH --job-name=safe-stage10-remediated-development
#SBATCH --partition=general1
#SBATCH --account=footprint
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --tmp=9216M
#SBATCH --time=36:00:00
#SBATCH --no-requeue
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077
: "${SLURM_JOB_ID:?scheduled execution required}"
: "${STAGE10_EXECUTION_GIT_SHA:?exact executable required}"
: "${STAGE10_CHECKOUT:?clean detached checkout required}"
: "${STAGE10_OUTPUT_DIRECTORY:?new DEVELOPMENT target required}"
: "${STAGE10_STAGE06_ROOT:?accepted Stage 6 root required}"
# The established launcher enforces all pre-input guards and performs exactly
# one catalog plus its three required publication replays. No second submission.
bash "${STAGE10_CHECKOUT}/cluster/goethe_nhr/stage10_development.sbatch"
# A read-only aggregate comparison in the SAME allocation; no further replay,
# generation or publication. Historical candidate stays immutable.
readonly stage10_remediation_project="$(realpath -e /work/footprint/donyadidegan/safe_geocoding_pipeline)"
export SAFE_EXECUTION_SITE=goethe-nhr PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONHASHSEED=0
export LANG=C.UTF-8 LC_ALL=C.UTF-8 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export PYTHONPATH="${STAGE10_CHECKOUT}/src"
"${stage10_remediation_project}/runtimes/stage06/stage06_development_20260828T223804Z_f39047cc825d/venv/bin/python" \
  -B -m safe_geocoding_pipeline.preprocessing.stage10_remediation_audit \
  --stage06-root "${STAGE10_STAGE06_ROOT}" --output-directory "${STAGE10_OUTPUT_DIRECTORY}" \
  --execution-git-sha "${STAGE10_EXECUTION_GIT_SHA}"
