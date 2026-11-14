#!/usr/bin/env bash
#SBATCH --job-name=safe-stage12a-catalog-lineage
#SBATCH --partition=general1
#SBATCH --account=footprint
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=32G
#SBATCH --time=02:05:00
#SBATCH --no-requeue
# Private fresh stdout/stderr paths are supplied by the reviewed submission.

set -euo pipefail
umask 077
ulimit -c 0
trap 'printf "%s\n" "{\"schema_version\":\"stage12a_catalog_lineage_local_v1\",\"status\":\"FAILED\",\"stage\":\"NATIVE_ENTRY\",\"code\":\"S12A_NATIVE_ENTRY_FAILED\"}" >&2' ERR
: "${SLURM_JOB_ID:?scheduled compute execution required}"
: "${STAGE12A_SOURCE:?exact private source checkout required}"
: "${STAGE12A_SOURCE_SHA:?exact pushed SHA required}"
: "${STAGE12A_CONFIGURATION:?exact private configuration required}"
: "${STAGE12A_CONFIGURATION_SHA:?exact configuration SHA256 required}"
: "${STAGE12A_SCRATCH:?exact absent scratch path required}"
readonly stage12a_project=/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline
readonly stage12a_base="${stage12a_project}/derived/controlled/stage12/12a"
readonly stage12a_python="${stage12a_project}/runtimes/stage06/stage06_development_20260828T223804Z_f39047cc825d/venv/bin/python"
[[ "${SLURM_RESTART_COUNT:-0}" == 0 && "${SLURM_CPUS_PER_TASK}" == 2 ]]
[[ "${STAGE12A_SOURCE_SHA}" =~ ^[a-f0-9]{40}$ && "${STAGE12A_CONFIGURATION_SHA}" =~ ^[a-f0-9]{64}$ ]]
[[ "$(dirname -- "${STAGE12A_SOURCE}")" == "${stage12a_project}/integration_stage12" ]]
[[ "$(realpath -e -- "${STAGE12A_SOURCE}")" == "${STAGE12A_SOURCE}" ]]
[[ "$(stat -c '%a:%u' -- "${STAGE12A_SOURCE}")" == "700:$(id -u)" ]]
[[ -z "$(git -C "${STAGE12A_SOURCE}" status --porcelain)" ]]
[[ -z "$(git -C "${STAGE12A_SOURCE}" symbolic-ref -q HEAD || true)" ]]
[[ "$(git -C "${STAGE12A_SOURCE}" rev-parse HEAD)" == "${STAGE12A_SOURCE_SHA}" ]]
[[ "${STAGE12A_CONFIGURATION}" == "${stage12a_base}/controls/"*/* ]]
[[ "$(realpath -e -- "${STAGE12A_CONFIGURATION}")" == "${STAGE12A_CONFIGURATION}" && ! -L "${STAGE12A_CONFIGURATION}" ]]
[[ "$(stat -c '%a:%u:%h' -- "${STAGE12A_CONFIGURATION}")" == "600:$(id -u):1" ]]
[[ "$(sha256sum -- "${STAGE12A_CONFIGURATION}" | cut -d' ' -f1)" == "${STAGE12A_CONFIGURATION_SHA}" ]]
readonly stage12a_logs="$(dirname -- "${STAGE12A_CONFIGURATION}")/logs"
[[ "$(realpath -e -- "${stage12a_logs}")" == "${stage12a_logs}" ]]
[[ "$(stat -c '%a:%u' -- "${stage12a_logs}")" == "700:$(id -u)" ]]
for stage12a_log in "${stage12a_logs}/slurm.out" "${stage12a_logs}/slurm.err"; do
  [[ -f "${stage12a_log}" && ! -L "${stage12a_log}" ]]
  [[ "$(realpath -e -- "${stage12a_log}")" == "${stage12a_log}" ]]
  [[ "$(stat -c '%u:%h' -- "${stage12a_log}")" == "$(id -u):1" ]]
  chmod 0600 -- "${stage12a_log}"
  [[ "$(stat -c '%a' -- "${stage12a_log}")" == 600 ]]
done
[[ "$(dirname -- "${STAGE12A_SCRATCH}")" == "${stage12a_base}/scratch" ]]
[[ "$(realpath -m -- "${STAGE12A_SCRATCH}")" == "${STAGE12A_SCRATCH}" && ! -e "${STAGE12A_SCRATCH}" && ! -L "${STAGE12A_SCRATCH}" ]]
[[ -x "${stage12a_python}" ]]
cd "${STAGE12A_SOURCE}"
# An empty environment excludes inherited service credentials and runtime knobs.
# The Python entry invokes the shared site guard before accepted input access;
# its process-wide audit denial starts before any accepted reader is opened.
exec /usr/bin/env -i \
  PATH=/usr/bin:/bin \
  SAFE_EXECUTION_SITE=goethe-nhr \
  SLURM_JOB_ID="${SLURM_JOB_ID}" SLURM_CPUS_PER_TASK=2 \
  STAGE12A_CONFIGURATION_SHA="${STAGE12A_CONFIGURATION_SHA}" \
  SQLITE_TMPDIR="${STAGE12A_SCRATCH}/sqlite_spill" \
  PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHONUTF8=1 PYTHONHASHSEED=0 \
  PYTHONPATH="${STAGE12A_SOURCE}/src" \
  LANG=C.UTF-8 LC_ALL=C.UTF-8 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  "${stage12a_python}" -s -B \
  "${STAGE12A_SOURCE}/scripts/stage12a_catalog_lineage.py" \
  --configuration "${STAGE12A_CONFIGURATION}"
