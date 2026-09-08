#!/usr/bin/env bash
#SBATCH --job-name=safe-stage09-reference-evidence
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=24:00:00
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${SLURM_JOB_NAME:?SLURM_JOB_NAME is required}"
: "${STAGE09_GIT_COMMIT:?exact pushed executable SHA is required}"
: "${STAGE09_INTEGRATION_ROOT:?new clean detached Git checkout is required}"
: "${STAGE09_RUNTIME_ROOT:?existing exact runtime is required}"
: "${STAGE09_STAGE08_ROOT:?accepted Stage 8 DEVELOPMENT artifact is required}"
: "${STAGE09_REFERENCE_RAW_ROOT:?exact frozen offline reference bytes are required}"
: "${STAGE09_REFERENCE_PACK_ROOT:?immutable public index target is required}"
: "${STAGE09_OUTPUT_DIRECTORY:?new immutable DEVELOPMENT target is required}"

readonly DATA_ROOT="$(realpath -e -- /work/footprint/donyadidegan/safe_geocoding_pipeline)"
readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE09_INTEGRATION_ROOT}")"
readonly RUNTIME_ROOT="$(realpath -e -- "${STAGE09_RUNTIME_ROOT}")"
readonly STAGE08_ROOT="$(realpath -e -- "${STAGE09_STAGE08_ROOT}")"
readonly REFERENCE_RAW_ROOT="$(realpath -e -- "${STAGE09_REFERENCE_RAW_ROOT}")"
readonly REFERENCE_PACK_ROOT="$(realpath -m -- "${STAGE09_REFERENCE_PACK_ROOT}")"
readonly OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE09_OUTPUT_DIRECTORY}")"
readonly REFERENCE_LOCK="${INTEGRATION_ROOT}/docs/scientific_assets/stage09_reference_pack_lock_v1.json"
readonly PYTHON="${RUNTIME_ROOT}/venv/bin/python"

for controlled_path in "${INTEGRATION_ROOT}" "${RUNTIME_ROOT}" "${STAGE08_ROOT}" \
  "${REFERENCE_RAW_ROOT}" "${REFERENCE_PACK_ROOT}" "${OUTPUT_DIRECTORY}"; do
  [[ "${controlled_path}" == "${DATA_ROOT}"/* ]] || { echo STAGE09_PERSONAL_PATH_REQUIRED >&2; exit 1; }
  [[ "${controlled_path,,}" != *holdout* ]] || { echo HOLDOUT_ACCESS_PROHIBITED >&2; exit 1; }
  [[ "${controlled_path,,}" != *production* ]] || { echo PRODUCTION_ACCESS_PROHIBITED >&2; exit 1; }
done
[[ ! -e "${OUTPUT_DIRECTORY}" && ! -L "${OUTPUT_DIRECTORY}" ]] || { echo STAGE09_OUTPUT_COLLISION >&2; exit 1; }
[[ -x "${PYTHON}" ]]

readonly LOG_ROOT="${DATA_ROOT}/logs/slurm"
chmod 0600 "${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.out" \
  "${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.err"
cd "${INTEGRATION_ROOT}"
[[ "$(git rev-parse HEAD)" == "${STAGE09_GIT_COMMIT}" ]]
[[ -z "$(git status --porcelain)" ]]
[[ -z "$(git symbolic-ref -q HEAD || true)" ]]

export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1
export PYTHONHASHSEED=0
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export OMP_NUM_THREADS=4
export OPENBLAS_NUM_THREADS=1
export PYTHONPATH="${INTEGRATION_ROOT}/src"
export TMPDIR="${DATA_ROOT}/derived/controlled/stage09/tmp/job_${SLURM_JOB_ID}"
install -d -m 0700 "${TMPDIR}"
export STAGE09_PREFLIGHT_DIRECTORY="${TMPDIR}"

# Compute-node synthetic filesystem/runtime preflight. No source rows opened.
# This checks the actual filesystem primitive before any protected input.
"${PYTHON}" -B - <<'PY'
import os
from pathlib import Path
from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_io as io

require_goethe_nhr_slurm("stage09-compute-preflight")
c.require_runtime()
root = Path(os.environ["STAGE09_PREFLIGHT_DIRECTORY"])
source, target = root / "synthetic_rename_source", root / "synthetic_rename_target"
source.mkdir(mode=0o700)
io.write_exclusive(source / "synthetic.txt", b"synthetic filesystem preflight\n")
io._atomic_rename(source, target)
c.require(not source.exists() and (target / "synthetic.txt").is_file(), "SYNTHETIC_RENAME_PREFLIGHT_FAILED")
print("STAGE09_EXACT_RUNTIME_AND_FILESYSTEM_PREFLIGHT_PASS")
PY

echo "job_id=${SLURM_JOB_ID}"
echo "execution_git_sha=${STAGE09_GIT_COMMIT}"
echo "requested_cpus=4"
echo "requested_memory_gib=32"
echo "requested_walltime=24:00:00"
echo "population=DEVELOPMENT_ONLY"
echo "network_calls=0"
echo "pelias_calls=0"
echo "parser_calls=0"

arguments=(materialize
  --stage08-root "${STAGE08_ROOT}"
  --reference-raw-root "${REFERENCE_RAW_ROOT}"
  --reference-lock "${REFERENCE_LOCK}"
  --reference-pack-root "${REFERENCE_PACK_ROOT}"
  --output-directory "${OUTPUT_DIRECTORY}"
  --execution-git-sha "${STAGE09_GIT_COMMIT}")
if [[ -n "${STAGE09_REFERENCE_PACK_MANIFEST_SHA256:-}" ]]; then
  arguments+=(--reference-pack-manifest-sha256 "${STAGE09_REFERENCE_PACK_MANIFEST_SHA256}")
fi
if [[ -n "${STAGE09_RESUME_WORK_ROOT:-}" ]]; then
  arguments+=(--resume-work-root "${STAGE09_RESUME_WORK_ROOT}")
fi

# No parser environment, libpostal bundle, network fetch or pip invocation.
"${PYTHON}" -B -m safe_geocoding_pipeline.preprocessing.stage09_cli "${arguments[@]}"
