#!/usr/bin/env bash
#SBATCH --job-name=safe-stage10-public-icu
#SBATCH --partition=general1
#SBATCH --account=footprint
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --no-requeue
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077
: "${SLURM_JOB_ID:?scheduled execution required}"
: "${STAGE10_PREPARATION_GIT_COMMIT:?exact pushed SHA required}"
: "${STAGE10_PREPARATION_CHECKOUT:?clean detached checkout required}"
: "${STAGE10_PUBLIC_RUNTIME_TARGET:?new immutable runtime target required}"

readonly stage10_alias=/work/footprint/donyadidegan/safe_geocoding_pipeline
readonly stage10_project="$(realpath -e -- "${stage10_alias}")"
# Canonicalize only the previously accepted /work -> /panfs mount anchor.
# Do not resolve artifact/checkout descendants through arbitrary symlinks.
stage10_public_path() {
  case "$1" in
    "${stage10_alias}"/*) printf '%s/%s\n' "${stage10_project}" "${1#"${stage10_alias}/"}" ;;
    "${stage10_project}"/*) printf '%s\n' "$1" ;;
    *) return 1 ;;
  esac
}
readonly stage10_checkout="$(stage10_public_path "${STAGE10_PREPARATION_CHECKOUT}")"
readonly stage10_target="$(stage10_public_path "${STAGE10_PUBLIC_RUNTIME_TARGET}")"
readonly stage10_python="${stage10_project}/runtimes/stage06/stage06_development_20260828T223804Z_f39047cc825d/venv/bin/python"
readonly stage10_archive="${stage10_project}/runtimes/stage10/public_sources_457157a/icu-source.tar.gz"
[[ "$(realpath -e -- "${stage10_checkout}")" == "${stage10_checkout}" ]]
[[ "$(dirname -- "${stage10_checkout}")" == "${stage10_project}/integration_stage10" ]]
[[ "$(dirname -- "${stage10_target}")" == "${stage10_project}/runtimes/stage10" ]]
[[ "$(realpath -m -- "${stage10_target}")" == "${stage10_target}" ]]
[[ ! -e "${stage10_target}" && ! -L "${stage10_target}" ]]
[[ "${SLURM_RESTART_COUNT:-0}" == 0 ]]
[[ -x "${stage10_python}" ]]
[[ "${SLURM_CPUS_PER_TASK}" == 4 ]]
[[ "${STAGE10_PREPARATION_GIT_COMMIT}" =~ ^[a-f0-9]{40}$ ]]
cd "${stage10_checkout}"
[[ "$(git rev-parse HEAD)" == "${STAGE10_PREPARATION_GIT_COMMIT}" ]]
[[ -z "$(git status --porcelain)" ]]
[[ -z "$(git symbolic-ref -q HEAD || true)" ]]
chmod 0600 "${stage10_project}/logs/slurm/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.out" \
  "${stage10_project}/logs/slurm/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.err"
printf '%s  %s\n' 629e7e6e309d1eeeb29c3eaf49e4f4532534fcf2613bcf0e51cd7850fa85a007 "${stage10_archive}" | sha256sum --check --strict -

export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONHASHSEED=0
export LANG=C.UTF-8 LC_ALL=C.UTF-8
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export PYTHONPATH="${stage10_checkout}/src"
export CONFIG_SITE=/dev/null

# Public source and invented vectors only. No downloads, pipeline readers,
# protected payload paths, retries, requeue, services or dynamic Git update.
"${stage10_python}" -B scripts/stage10_build_runtime.py \
  --archive "${stage10_archive}" \
  --output-root "${stage10_target}" \
  --repository "${stage10_checkout}" --jobs 4
