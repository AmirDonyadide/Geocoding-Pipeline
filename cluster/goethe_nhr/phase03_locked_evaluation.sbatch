#!/usr/bin/env bash
#SBATCH --job-name=safe-phase03-locked-evaluation
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=12:00:00
#SBATCH --mail-user=donyadidegan@safe-frankfurt.de
#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

readonly DATA_ROOT="/work/footprint/donyadidegan/safe_geocoding_pipeline"
readonly PHASE02_RUN="${DATA_ROOT}/staging/controlled/phase02_v1/runs/phase02_20260810T173851Z_1349152b"
readonly PHASE02_MANIFEST="${PHASE02_RUN}/dataset_manifest.json"
readonly LOCKED_ROOT="${DATA_ROOT}/derived/controlled/phase03_v1/locked_evaluations"

export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1
: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${PHASE03_GIT_COMMIT:?exact reviewed protocol implementation commit is required}"
: "${PHASE03_INTEGRATION_ROOT:?detached protocol integration worktree is required}"
: "${PHASE03_LOCKED_STAGE:?PREFLIGHT, OPEN_AND_PREPARE, INITIALIZE_REVIEW, or SCORE_AND_FINALIZE is required}"
: "${PHASE03_LOCKED_RUN_ID:?predeclared LOCKED evaluation run ID is required}"
: "${PHASE03_LOCKED_IDENTITIES:?sealed LOCKED identity file is required}"
: "${PHASE03_PILOT_SEAL:?frozen pilot seal is required}"

readonly INTEGRATION_ROOT="$(realpath -e -- "${PHASE03_INTEGRATION_ROOT}")"
readonly EXPECTED_SBATCH="${INTEGRATION_ROOT}/cluster/goethe_nhr/phase03_locked_evaluation.sbatch"
readonly ATTEMPT="${LOCKED_ROOT}/.in_progress/${PHASE03_LOCKED_RUN_ID}"
readonly FINAL="${LOCKED_ROOT}/${PHASE03_LOCKED_RUN_ID}"
readonly PREFLIGHT_REPORT="${ATTEMPT}/preflight.json"
readonly LOCKED_PAYLOAD="${ATTEMPT}/payload/locked_evaluation.parquet"
readonly TRANSFORMED="${ATTEMPT}/transformed"
readonly REVIEW_INPUT="${ATTEMPT}/review_input"
readonly REVIEW_PROGRESS="${ATTEMPT}/review_progress"

[[ "$(git -C "${INTEGRATION_ROOT}" rev-parse HEAD)" == "${PHASE03_GIT_COMMIT}" ]] || {
  echo "LOCKED_EVALUATION_GIT_COMMIT_MISMATCH" >&2
  exit 1
}
[[ -z "$(git -C "${INTEGRATION_ROOT}" symbolic-ref -q --short HEAD)" ]] || {
  echo "LOCKED_EVALUATION_WORKTREE_NOT_DETACHED" >&2
  exit 1
}
[[ -z "$(git -C "${INTEGRATION_ROOT}" status --short)" ]] || {
  echo "LOCKED_EVALUATION_WORKTREE_DIRTY" >&2
  exit 1
}
cmp -s -- "${BASH_SOURCE[0]}" "${EXPECTED_SBATCH}" || {
  echo "LOCKED_EVALUATION_SBATCH_SOURCE_MISMATCH" >&2
  exit 1
}
[[ ! -e "${FINAL}" ]] || {
  echo "LOCKED_EVALUATION_FINAL_OUTPUT_EXISTS" >&2
  exit 1
}

cd "${INTEGRATION_ROOT}"
source "${DATA_ROOT}/.venv-goethe-nhr/bin/activate"
export PYTHONPATH="${INTEGRATION_ROOT}/src"

mapfile -d '' PHASE02_SHARDS < <(
  find "${PHASE02_RUN}/data" -maxdepth 1 -type f -name '*.parquet' -print0 | sort -z
)
[[ "${#PHASE02_SHARDS[@]}" -eq 206 ]] || {
  echo "LOCKED_EVALUATION_PHASE02_SHARD_COUNT_MISMATCH" >&2
  exit 1
}
INPUT_ARGS=()
for shard in "${PHASE02_SHARDS[@]}"; do
  INPUT_ARGS+=(--input-path "${shard}")
done

echo "job_id=${SLURM_JOB_ID}"
echo "hostname=$(hostname)"
echo "partition=${SLURM_JOB_PARTITION:-unknown}"
echo "stage=${PHASE03_LOCKED_STAGE}"
echo "git_commit=${PHASE03_GIT_COMMIT}"
echo "run_id=${PHASE03_LOCKED_RUN_ID}"
echo "raw_values_logged=false"

if [[ "${PHASE03_LOCKED_STAGE}" == "PREFLIGHT" ]]; then
  [[ ! -e "${ATTEMPT}" ]] || {
    echo "LOCKED_EVALUATION_ATTEMPT_ALREADY_EXISTS" >&2
    exit 1
  }
  install -d -m 700 "${LOCKED_ROOT}/.in_progress" "${ATTEMPT}"
  safe-geocoding-phase03-locked-evaluation preflight \
    --phase02-manifest "${PHASE02_MANIFEST}" \
    "${INPUT_ARGS[@]}" \
    --locked-identities "${PHASE03_LOCKED_IDENTITIES}" \
    --pilot-seal "${PHASE03_PILOT_SEAL}" \
    --output "${PREFLIGHT_REPORT}" \
    --workflow-git-commit "${PHASE03_GIT_COMMIT}"
  echo "LOCKED_PREFLIGHT_COMPLETE_NO_PAYLOAD_ROWS_READ"
  exit 0
fi

[[ -f "${PREFLIGHT_REPORT}" && -r "${PREFLIGHT_REPORT}" ]] || {
  echo "LOCKED_EVALUATION_PREFLIGHT_REQUIRED" >&2
  exit 1
}
[[ "${PHASE03_LOCKED_UNSEAL_AUTHORIZATION:-}" == \
  "LOCKED_EVALUATION_EXPLICITLY_AUTHORIZED" ]] || {
  echo "LOCKED_EVALUATION_EXPLICIT_UNSEAL_AUTHORIZATION_REQUIRED" >&2
  exit 1
}

if [[ "${PHASE03_LOCKED_STAGE}" == "OPEN_AND_PREPARE" ]]; then
  [[ ! -e "${LOCKED_PAYLOAD}" && ! -e "${TRANSFORMED}" && ! -e "${REVIEW_INPUT}" ]] || {
    echo "LOCKED_EVALUATION_OPEN_STAGE_OUTPUT_EXISTS" >&2
    exit 1
  }
  safe-geocoding-phase03-locked-evaluation materialize \
    "${INPUT_ARGS[@]}" \
    --locked-identities "${PHASE03_LOCKED_IDENTITIES}" \
    --preflight-report "${PREFLIGHT_REPORT}" \
    --workflow-git-commit "${PHASE03_GIT_COMMIT}" \
    --output "${LOCKED_PAYLOAD}"
  safe-geocoding-phase03-locked-evaluation transform \
    --locked-payload "${LOCKED_PAYLOAD}" \
    --locked-identities "${PHASE03_LOCKED_IDENTITIES}" \
    --preflight-report "${PREFLIGHT_REPORT}" \
    --output-root "${TRANSFORMED}" \
    --workflow-git-commit "${PHASE03_GIT_COMMIT}"
  safe-geocoding-phase03-locked-evaluation prepare-review \
    --locked-payload "${LOCKED_PAYLOAD}" \
    --baseline-core "${TRANSFORMED}/baseline/core/locked_evaluation.parquet" \
    --baseline-evidence "${TRANSFORMED}/baseline/evidence/locked_evaluation.parquet" \
    --candidate-core "${TRANSFORMED}/candidate/core/locked_evaluation.parquet" \
    --candidate-evidence "${TRANSFORMED}/candidate/evidence/locked_evaluation.parquet" \
    --output-directory "${REVIEW_INPUT}" \
    --locked-evaluation-version "${PHASE03_LOCKED_RUN_ID}" \
    --workflow-git-commit "${PHASE03_GIT_COMMIT}"
  echo "LOCKED_OPEN_AND_REVIEW_PREPARATION_COMPLETE"
  exit 0
fi

if [[ "${PHASE03_LOCKED_STAGE}" == "INITIALIZE_REVIEW" ]]; then
  safe-geocoding-phase03-locked-evaluation initialize-review \
    --protected-context "${REVIEW_INPUT}/protected_locked_review_context.parquet" \
    --protected-template "${REVIEW_INPUT}/protected_locked_review_template.parquet" \
    --input-manifest "${REVIEW_INPUT}/locked_review_input_manifest.json" \
    --output-directory "${REVIEW_PROGRESS}" \
    --workflow-git-commit "${PHASE03_GIT_COMMIT}"
  echo "LOCKED_REVIEW_WORKSPACES_INITIALIZED"
  exit 0
fi

if [[ "${PHASE03_LOCKED_STAGE}" == "SCORE_AND_FINALIZE" ]]; then
  : "${PHASE03_LOCKED_MACHINE_CHECKS:?completed exact machine-gate JSON is required}"
  readonly LABELS="${ATTEMPT}/controlled_labels/locked_review_labels.parquet"
  readonly SCORE="${ATTEMPT}/reports/locked_evaluation_score.json"
  install -d -m 700 "$(dirname "${LABELS}")" "$(dirname "${SCORE}")"
  safe-geocoding-phase03-locked-evaluation export-labels \
    --reviewer-one-database "${REVIEW_PROGRESS}/LOCKED-R01/review_progress.sqlite3" \
    --reviewer-two-database "${REVIEW_PROGRESS}/LOCKED-R02/review_progress.sqlite3" \
    --output "${LABELS}"
  safe-geocoding-phase03-locked-evaluation score \
    --controlled-labels "${LABELS}" \
    --protected-context "${REVIEW_INPUT}/protected_locked_review_context.parquet" \
    --review-input-manifest "${REVIEW_INPUT}/locked_review_input_manifest.json" \
    --machine-checks "${PHASE03_LOCKED_MACHINE_CHECKS}" \
    --output "${SCORE}"
  safe-geocoding-phase03-locked-evaluation finalize \
    --attempt-directory "${ATTEMPT}" \
    --final-directory "${FINAL}" \
    --score "${SCORE}" \
    --artifact "preflight=${PREFLIGHT_REPORT}" \
    --artifact "locked_payload=${LOCKED_PAYLOAD}" \
    --artifact "baseline_core=${TRANSFORMED}/baseline/core/locked_evaluation.parquet" \
    --artifact "baseline_evidence=${TRANSFORMED}/baseline/evidence/locked_evaluation.parquet" \
    --artifact "candidate_core=${TRANSFORMED}/candidate/core/locked_evaluation.parquet" \
    --artifact "candidate_evidence=${TRANSFORMED}/candidate/evidence/locked_evaluation.parquet" \
    --artifact "review_input_manifest=${REVIEW_INPUT}/locked_review_input_manifest.json" \
    --artifact "controlled_labels=${LABELS}" \
    --artifact "machine_checks=${PHASE03_LOCKED_MACHINE_CHECKS}" \
    --artifact "score=${SCORE}" \
    --workflow-git-commit "${PHASE03_GIT_COMMIT}"
  echo "LOCKED_EVALUATION_FINALIZED"
  exit 0
fi

echo "LOCKED_EVALUATION_STAGE_INVALID" >&2
exit 1
