#!/usr/bin/env bash
#SBATCH --job-name=safe-s07-evidence-rereview
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=01:00:00
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${SLURM_JOB_NAME:?SLURM_JOB_NAME is required}"
: "${STAGE07_REREVIEW_GIT_SHA:?exact pushed rereview SHA is required}"
: "${STAGE07_REREVIEW_WORKTREE:?clean detached review worktree is required}"
: "${STAGE07_REREVIEW_RUNTIME_ROOT:?validated Stage 7 runtime is required}"
: "${STAGE07_REREVIEW_STAGE06_ROOT:?immutable Stage 6 root is required}"
: "${STAGE07_REREVIEW_STAGE07_V1_ROOT:?immutable Stage 7 v1 root is required}"
: "${STAGE07_REREVIEW_ELIGIBILITY_ARTIFACT:?immutable eligibility artifact is required}"
: "${STAGE07_REREVIEW_ELIGIBILITY_MANIFEST:?immutable eligibility audit manifest is required}"
: "${STAGE07_REREVIEW_STAGE07_V2_ROOT:?immutable Stage 7 v2 root is required}"
: "${STAGE07_REREVIEW_OUTPUT_DIRECTORY:?new independent evidence output is required}"

readonly DATA_ROOT="$(realpath -e -- /work/footprint/donyadidegan/safe_geocoding_pipeline)"
readonly WORKTREE="$(realpath -e -- "${STAGE07_REREVIEW_WORKTREE}")"
readonly RUNTIME_ROOT="$(realpath -e -- "${STAGE07_REREVIEW_RUNTIME_ROOT}")"
readonly STAGE06_ROOT="$(realpath -e -- "${STAGE07_REREVIEW_STAGE06_ROOT}")"
readonly STAGE07_V1_ROOT="$(realpath -e -- "${STAGE07_REREVIEW_STAGE07_V1_ROOT}")"
readonly ELIGIBILITY_ARTIFACT="$(realpath -e -- "${STAGE07_REREVIEW_ELIGIBILITY_ARTIFACT}")"
readonly ELIGIBILITY_MANIFEST="$(realpath -e -- "${STAGE07_REREVIEW_ELIGIBILITY_MANIFEST}")"
readonly STAGE07_V2_ROOT="$(realpath -e -- "${STAGE07_REREVIEW_STAGE07_V2_ROOT}")"
readonly OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE07_REREVIEW_OUTPUT_DIRECTORY}")"

for controlled_path in \
  "${WORKTREE}" \
  "${RUNTIME_ROOT}" \
  "${STAGE06_ROOT}" \
  "${STAGE07_V1_ROOT}" \
  "${ELIGIBILITY_ARTIFACT}" \
  "${ELIGIBILITY_MANIFEST}" \
  "${STAGE07_V2_ROOT}" \
  "${OUTPUT_DIRECTORY}"; do
  [[ "${controlled_path}" == "${DATA_ROOT}"/* ]] || {
    echo "STAGE07_CONTROLLED_PATH_REQUIRED" >&2
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

[[ ! -e "${OUTPUT_DIRECTORY}" ]] || {
  echo "STAGE07_REREVIEW_OUTPUT_COLLISION" >&2
  exit 1
}

readonly LOG_ROOT="${DATA_ROOT}/logs/slurm"
readonly JOB_STDOUT="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.out"
readonly JOB_STDERR="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.err"
chmod 0600 "${JOB_STDOUT}" "${JOB_STDERR}"
[[ "$(stat -c %a "${JOB_STDOUT}")" == "600" ]]
[[ "$(stat -c %a "${JOB_STDERR}")" == "600" ]]

cd "${WORKTREE}"
[[ "$(git rev-parse HEAD)" == "${STAGE07_REREVIEW_GIT_SHA}" ]]
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
export PYTHONPATH="${WORKTREE}/src"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TMPDIR="${RUNTIME_ROOT}/tmp_evidence_rereview_${SLURM_JOB_ID}"
install -d -m 0700 "${TMPDIR}"

echo "job_id=${SLURM_JOB_ID}"
echo "review_git_sha=${STAGE07_REREVIEW_GIT_SHA}"
echo "reviewed_candidate_sha=656a16d3d1f33cb152ace557c26f42df047bc7d6"
echo "requested_memory_gib=32"
echo "requested_cpus=4"
echo "parser_calls=0"
echo "protected_scope=existing_stage06_stage07_evidence_only"
echo "holdout_access=false"
echo "production_access=false"

"${PYTHON}" -B \
  -m safe_geocoding_pipeline.preprocessing.stage07_parser_evidence_rereview_cli \
  --stage06-root "${STAGE06_ROOT}" \
  --stage07-v1-root "${STAGE07_V1_ROOT}" \
  --eligibility-artifact "${ELIGIBILITY_ARTIFACT}" \
  --eligibility-audit-manifest "${ELIGIBILITY_MANIFEST}" \
  --stage07-v2-root "${STAGE07_V2_ROOT}" \
  --source-root "${WORKTREE}" \
  --output-directory "${OUTPUT_DIRECTORY}" \
  --review-git-sha "${STAGE07_REREVIEW_GIT_SHA}" \
  --reviewed-candidate-sha 656a16d3d1f33cb152ace557c26f42df047bc7d6 \
  --batch-rows 32

echo "STAGE07_EVIDENCE_ONLY_INDEPENDENT_REREVIEW_JOB_COMPLETE"
