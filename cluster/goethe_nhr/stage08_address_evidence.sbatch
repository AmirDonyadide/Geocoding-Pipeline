#!/usr/bin/env bash
#SBATCH --job-name=safe-stage08-address-evidence
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${SLURM_JOB_NAME:?SLURM_JOB_NAME is required}"
: "${STAGE08_GIT_COMMIT:?exact pushed Stage 8 SHA is required}"
: "${STAGE08_INTEGRATION_ROOT:?clean detached worktree is required}"
: "${STAGE08_RUNTIME_ROOT:?validated controlled runtime is required}"
: "${STAGE08_STAGE07_ROOT:?immutable accepted Stage 7 v2 root is required}"
: "${STAGE08_STAGE06_ROOT:?immutable accepted Stage 6 root is required}"
: "${STAGE08_OUTPUT_DIRECTORY:?new immutable Stage 8 output is required}"

readonly DATA_ROOT="$(realpath -e -- /work/footprint/donyadidegan/safe_geocoding_pipeline)"
readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE08_INTEGRATION_ROOT}")"
readonly RUNTIME_ROOT="$(realpath -e -- "${STAGE08_RUNTIME_ROOT}")"
readonly STAGE07_ROOT="$(realpath -e -- "${STAGE08_STAGE07_ROOT}")"
readonly STAGE06_ROOT="$(realpath -e -- "${STAGE08_STAGE06_ROOT}")"
readonly OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE08_OUTPUT_DIRECTORY}")"

for controlled_path in \
  "${INTEGRATION_ROOT}" \
  "${RUNTIME_ROOT}" \
  "${STAGE07_ROOT}" \
  "${STAGE06_ROOT}" \
  "${OUTPUT_DIRECTORY}"; do
  [[ "${controlled_path}" == "${DATA_ROOT}"/* ]] || {
    echo "STAGE08_CONTROLLED_PATH_REQUIRED" >&2
    exit 1
  }
  [[ "${controlled_path,,}" != *holdout* ]] || {
    echo "HOLDOUT_ACCESS_PROHIBITED" >&2
    exit 1
  }
  [[ "${controlled_path,,}" != *production* ]] || {
    echo "PRODUCTION_ACCESS_PROHIBITED" >&2
    exit 1
  }
done
[[ ! -e "${OUTPUT_DIRECTORY}" ]] || { echo "STAGE08_OUTPUT_COLLISION" >&2; exit 1; }

readonly LOG_ROOT="${DATA_ROOT}/logs/slurm"
readonly JOB_STDOUT="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.out"
readonly JOB_STDERR="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.err"
chmod 0600 "${JOB_STDOUT}" "${JOB_STDERR}"
[[ "$(stat -c %a "${JOB_STDOUT}")" == "600" ]]
[[ "$(stat -c %a "${JOB_STDERR}")" == "600" ]]

cd "${INTEGRATION_ROOT}"
[[ "$(git rev-parse HEAD)" == "${STAGE08_GIT_COMMIT}" ]]
[[ -z "$(git status --porcelain)" ]]
[[ "$(git symbolic-ref -q HEAD || true)" == "" ]]

readonly PYTHON="${RUNTIME_ROOT}/venv/bin/python"
[[ -x "${PYTHON}" ]]
export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1
export PYTHONHASHSEED=0
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export PYTHONPATH="${INTEGRATION_ROOT}/src"
export TMPDIR="${RUNTIME_ROOT}/tmp_stage08_${SLURM_JOB_ID}"
install -d -m 0700 "${TMPDIR}"

echo "job_id=${SLURM_JOB_ID}"
echo "git_commit=${STAGE08_GIT_COMMIT}"
echo "requested_memory_gib=32"
echo "requested_cpus=4"
echo "requested_walltime=04:00:00"
echo "parser_calls=0"
echo "reference_lookups=0"
echo "network_calls=0"
echo "semantic_trust_fields=0"
echo "holdout_access=false"
echo "production_access=false"

"${PYTHON}" -B \
  -m safe_geocoding_pipeline.preprocessing.stage08_cli \
  materialize \
  --stage07-output-directory "${STAGE07_ROOT}" \
  --stage06-output-directory "${STAGE06_ROOT}" \
  --output-directory "${OUTPUT_DIRECTORY}" \
  --execution-git-sha "${STAGE08_GIT_COMMIT}" \
  --input-batch-rows 16 \
  --candidate-output-batch-rows 32 \
  --component-batch-rows 65536 \
  --target-batch-bytes $((128 * 1024 * 1024)) \
  --candidate-shard-rows 2048 \
  --component-shard-rows 500000 \
  --source-shard-rows 4096 \
  --duckdb-memory-limit 8GB \
  --duckdb-threads 4

echo "STAGE08_ADDRESS_EVIDENCE_DEVELOPMENT_COMPLETE"
