#!/usr/bin/env bash
#SBATCH --job-name=safe-stage07-evidence-v2
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
: "${STAGE07_EVIDENCE_GIT_COMMIT:?exact pushed evidence-v2 SHA is required}"
: "${STAGE07_EVIDENCE_INTEGRATION_ROOT:?clean detached worktree is required}"
: "${STAGE07_EVIDENCE_RUNTIME_ROOT:?validated Stage 7 runtime is required}"
: "${STAGE07_EVIDENCE_STAGE06_ROOT:?immutable Stage 6 root is required}"
: "${STAGE07_EVIDENCE_STAGE07_V1_ROOT:?immutable Stage 7 v1 root is required}"
: "${STAGE07_EVIDENCE_ELIGIBILITY_ROOT:?immutable eligibility audit root is required}"
: "${STAGE07_EVIDENCE_OUTPUT_DIRECTORY:?new evidence-only output is required}"

readonly DATA_ROOT="$(realpath -e -- /work/footprint/donyadidegan/safe_geocoding_pipeline)"
readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE07_EVIDENCE_INTEGRATION_ROOT}")"
readonly RUNTIME_ROOT="$(realpath -e -- "${STAGE07_EVIDENCE_RUNTIME_ROOT}")"
readonly STAGE06_ROOT="$(realpath -e -- "${STAGE07_EVIDENCE_STAGE06_ROOT}")"
readonly STAGE07_V1_ROOT="$(realpath -e -- "${STAGE07_EVIDENCE_STAGE07_V1_ROOT}")"
readonly ELIGIBILITY_ROOT="$(realpath -e -- "${STAGE07_EVIDENCE_ELIGIBILITY_ROOT}")"
readonly OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE07_EVIDENCE_OUTPUT_DIRECTORY}")"
readonly ELIGIBILITY_ARTIFACT="${ELIGIBILITY_ROOT}/stage07_candidate_country_eligibility.parquet"
readonly ELIGIBILITY_MANIFEST="${ELIGIBILITY_ROOT}/stage07_country_eligibility_manifest.json"

for controlled_path in \
  "${INTEGRATION_ROOT}" \
  "${RUNTIME_ROOT}" \
  "${STAGE06_ROOT}" \
  "${STAGE07_V1_ROOT}" \
  "${ELIGIBILITY_ROOT}" \
  "${OUTPUT_DIRECTORY}"; do
  [[ "${controlled_path}" == "${DATA_ROOT}"/* ]] || {
    echo "STAGE07_CONTROLLED_PATH_REQUIRED" >&2
    exit 1
  }
  [[ "${controlled_path,,}" != *holdout* ]] || {
    echo "HOLDOUT_ACCESS_PROHIBITED" >&2
    exit 1
  }
done
[[ ! -e "${OUTPUT_DIRECTORY}" ]] || { echo "STAGE07_OUTPUT_COLLISION" >&2; exit 1; }
[[ -f "${ELIGIBILITY_ARTIFACT}" && -f "${ELIGIBILITY_MANIFEST}" ]]

readonly LOG_ROOT="${DATA_ROOT}/logs/slurm"
readonly JOB_STDOUT="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.out"
readonly JOB_STDERR="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.err"
chmod 0600 "${JOB_STDOUT}" "${JOB_STDERR}"
[[ "$(stat -c %a "${JOB_STDOUT}")" == "600" ]]
[[ "$(stat -c %a "${JOB_STDERR}")" == "600" ]]

cd "${INTEGRATION_ROOT}"
[[ "$(git rev-parse HEAD)" == "${STAGE07_EVIDENCE_GIT_COMMIT}" ]]
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
export TMPDIR="${RUNTIME_ROOT}/tmp_evidence_${SLURM_JOB_ID}"
install -d -m 0700 "${TMPDIR}"

echo "job_id=${SLURM_JOB_ID}"
echo "git_commit=${STAGE07_EVIDENCE_GIT_COMMIT}"
echo "requested_memory_gib=32"
echo "requested_cpus=4"
echo "parser_calls=0"
echo "semantic_review=false"
echo "semantic_trust_claims=0"
echo "stage07_v1_modified=false"
echo "holdout_access=false"
echo "production_access=false"

"${PYTHON}" -B \
  -m safe_geocoding_pipeline.preprocessing.stage07_parser_evidence_cli \
  materialize \
  --stage06-output-directory "${STAGE06_ROOT}" \
  --stage07-v1-output-directory "${STAGE07_V1_ROOT}" \
  --eligibility-artifact "${ELIGIBILITY_ARTIFACT}" \
  --eligibility-audit-manifest "${ELIGIBILITY_MANIFEST}" \
  --output-directory "${OUTPUT_DIRECTORY}" \
  --execution-git-sha "${STAGE07_EVIDENCE_GIT_COMMIT}" \
  --input-batch-rows 64 \
  --output-batch-rows 64 \
  --target-batch-bytes $((128 * 1024 * 1024)) \
  --output-shard-rows 4096

echo "STAGE07_EVIDENCE_ONLY_DEVELOPMENT_COMPLETE"
