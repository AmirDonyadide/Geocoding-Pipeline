#!/usr/bin/env bash
#SBATCH --job-name=safe-stage10-development
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
: "${STAGE10_EXECUTION_GIT_SHA:?exact pushed executable required}"
: "${STAGE10_CHECKOUT:?clean detached checkout required}"
: "${STAGE10_OUTPUT_DIRECTORY:?new immutable DEVELOPMENT target required}"
: "${STAGE10_STAGE06_ROOT:?exact accepted Stage 6 root required}"
readonly stage10_alias=/work/footprint/donyadidegan/safe_geocoding_pipeline
readonly stage10_project="$(realpath -e -- "${stage10_alias}")"
stage10_path() {
  case "$1" in
    "${stage10_alias}"/*) printf '%s/%s\n' "${stage10_project}" "${1#"${stage10_alias}/"}" ;;
    "${stage10_project}"/*) printf '%s\n' "$1" ;;
    *) return 1 ;;
  esac
}
readonly stage10_checkout="$(stage10_path "${STAGE10_CHECKOUT}")"
readonly stage10_target="$(stage10_path "${STAGE10_OUTPUT_DIRECTORY}")"
readonly stage10_stage06="$(stage10_path "${STAGE10_STAGE06_ROOT}")"
readonly stage10_python="${stage10_project}/runtimes/stage06/stage06_development_20260828T223804Z_f39047cc825d/venv/bin/python"
[[ "${SLURM_RESTART_COUNT:-0}" == 0 && "${SLURM_CPUS_PER_TASK}" == 4 ]]
[[ "${STAGE10_EXECUTION_GIT_SHA}" =~ ^[a-f0-9]{40}$ ]]
[[ "$(realpath -e -- "${stage10_checkout}")" == "${stage10_checkout}" ]]
[[ "$(dirname -- "${stage10_checkout}")" == "${stage10_project}/integration_stage10" ]]
[[ "$(dirname -- "${stage10_target}")" == "${stage10_project}/derived/controlled/stage10/development" ]]
[[ "$(realpath -m -- "${stage10_target}")" == "${stage10_target}" ]]
[[ ! -e "${stage10_target}" && ! -L "${stage10_target}" ]]
[[ "$(realpath -e -- "${stage10_stage06}")" == "${stage10_stage06}" ]]
[[ -x "${stage10_python}" ]]
cd "${stage10_checkout}"
[[ "$(git rev-parse HEAD)" == "${STAGE10_EXECUTION_GIT_SHA}" ]]
[[ -z "$(git status --porcelain)" && -z "$(git symbolic-ref -q HEAD || true)" ]]
git merge-base --is-ancestor 1443bb3b3c1bb50220bf38231e01552c66c4eaee HEAD
chmod 0600 "${stage10_project}/logs/slurm/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.out" \
  "${stage10_project}/logs/slurm/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.err"
export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONHASHSEED=0
export LANG=C.UTF-8 LC_ALL=C.UTF-8
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export PYTHONPATH="${stage10_checkout}/src"
# One offline catalog, all eligible frozen families, full reopen validation.
# No submission, polling, requeue, service calls or dynamic Git update here.
"${stage10_python}" -B -m safe_geocoding_pipeline.preprocessing.stage10_cli materialize \
  --stage06-root "${stage10_stage06}" --output-directory "${stage10_target}" \
  --execution-git-sha "${STAGE10_EXECUTION_GIT_SHA}"
