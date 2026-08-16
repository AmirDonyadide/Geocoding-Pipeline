#!/usr/bin/env bash
#SBATCH --job-name=safe-phase03-v3-pop-verify
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --mail-user=donyadidegan@safe-frankfurt.de
#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

readonly DATA_ROOT="/work/footprint/donyadidegan/safe_geocoding_pipeline"
readonly CONTROLLED_ROOT="${DATA_ROOT}/derived/controlled/phase03_v1"
readonly SOURCE_RUN_ROOT="${CONTROLLED_ROOT}/pilots/.in_progress/phase03_pilot_goethe_20260813T224643Z_1748630_750a1655"
readonly REPAIR_ITERATION_ID="phase03_development_country_method_repair_20260816T001155Z_1749448_e4a47253"
readonly REPAIR_ITERATION_ROOT="${CONTROLLED_ROOT}/development_iterations/${REPAIR_ITERATION_ID}"
readonly REPAIR_REPORT_ROOT="${DATA_ROOT}/reports/generated/phase03/development_iterations/${REPAIR_ITERATION_ID}"
readonly OUTPUT_ROOT="${DATA_ROOT}/reports/generated/phase03/parser_v3_targeted_review_population"
readonly DEVELOPMENT_IDENTITIES="${SOURCE_RUN_ROOT}/selection/development.identities.bin"
readonly BASELINE_CORE="${REPAIR_ITERATION_ROOT}/parser_v2_1/transformed/core/development.parquet"
readonly BASELINE_EVIDENCE="${REPAIR_ITERATION_ROOT}/parser_v2_1/transformed/evidence/development.parquet"
readonly EXPERIMENTAL_CORE="${REPAIR_ITERATION_ROOT}/parser_v3_1_experimental/transformed/core/development.parquet"
readonly EXPERIMENTAL_EVIDENCE="${REPAIR_ITERATION_ROOT}/parser_v3_1_experimental/transformed/evidence/development.parquet"
readonly REPAIR_SUCCESS="${REPAIR_ITERATION_ROOT}/_SUCCESS.json"
readonly REPAIR_COMPARISON="${REPAIR_REPORT_ROOT}/parser_v2_1_v3_1_aggregate.json"

export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1
: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${SLURM_SUBMIT_DIR:?SLURM_SUBMIT_DIR is required}"
: "${PHASE03_GIT_COMMIT:?reviewed population-verification commit is required}"
: "${PHASE03_INTEGRATION_ROOT:?detached integration worktree is required}"

readonly INTEGRATION_ROOT="$(realpath -e -- "${PHASE03_INTEGRATION_ROOT}")"
readonly SUBMIT_DIRECTORY="$(realpath -e -- "${SLURM_SUBMIT_DIR}")"
readonly RESOLVED_CONTROLLED_ROOT="$(realpath -e -- "${CONTROLLED_ROOT}")"
readonly RESOLVED_REPAIR_REPORT_ROOT="$(realpath -e -- "${REPAIR_REPORT_ROOT}")"
readonly EXPECTED_SBATCH="${INTEGRATION_ROOT}/cluster/goethe_nhr/phase03_parser_v3_targeted_review_population_verify.sbatch"

[[ "${SUBMIT_DIRECTORY}" == "${INTEGRATION_ROOT}" ]] || {
  echo "TARGETED_POPULATION_SUBMIT_DIRECTORY_MISMATCH" >&2
  exit 1
}
cmp -s -- "${BASH_SOURCE[0]}" "${EXPECTED_SBATCH}" || {
  echo "TARGETED_POPULATION_SBATCH_SOURCE_MISMATCH" >&2
  exit 1
}
[[ "$(git -C "${INTEGRATION_ROOT}" rev-parse HEAD)" == "${PHASE03_GIT_COMMIT}" ]] || {
  echo "TARGETED_POPULATION_GIT_COMMIT_MISMATCH" >&2
  exit 1
}
[[ -z "$(git -C "${INTEGRATION_ROOT}" symbolic-ref -q --short HEAD)" ]] || {
  echo "TARGETED_POPULATION_WORKTREE_NOT_DETACHED" >&2
  exit 1
}
[[ -z "$(git -C "${INTEGRATION_ROOT}" status --short)" ]] || {
  echo "TARGETED_POPULATION_WORKTREE_NOT_CLEAN" >&2
  exit 1
}

readonly INPUTS=(
  "${DEVELOPMENT_IDENTITIES}"
  "${BASELINE_CORE}"
  "${BASELINE_EVIDENCE}"
  "${EXPERIMENTAL_CORE}"
  "${EXPERIMENTAL_EVIDENCE}"
  "${REPAIR_SUCCESS}"
  "${REPAIR_COMPARISON}"
)
declare -A INPUT_HASHES
for input in "${INPUTS[@]}"; do
  [[ -f "${input}" && -r "${input}" ]] || {
    echo "TARGETED_POPULATION_INPUT_NOT_READABLE" >&2
    exit 1
  }
  resolved_input="$(realpath -e -- "${input}")"
  [[ "${resolved_input}" == "${RESOLVED_CONTROLLED_ROOT}/"* || \
      "${resolved_input}" == "${RESOLVED_REPAIR_REPORT_ROOT}/"* ]] || {
    echo "TARGETED_POPULATION_INPUT_OUTSIDE_APPROVED_ROOTS" >&2
    exit 1
  }
  [[ "${resolved_input,,}" != *locked* ]] || {
    echo "TARGETED_POPULATION_LOCKED_PATH_PROHIBITED" >&2
    exit 1
  }
  INPUT_HASHES["${input}"]="$(sha256sum -- "${input}" | cut -d' ' -f1)"
done

cd "${INTEGRATION_ROOT}"
source "${DATA_ROOT}/.venv-goethe-nhr/bin/activate"
export PYTHONPATH="${INTEGRATION_ROOT}/src"

readonly TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
readonly COMMIT_SHORT="${PHASE03_GIT_COMMIT:0:8}"
readonly VERIFICATION_ID="phase03_parser_v3_repaired_population_${TIMESTAMP}_${SLURM_JOB_ID}_${COMMIT_SHORT}"
readonly ATTEMPT="${OUTPUT_ROOT}/.in_progress/${VERIFICATION_ID}"
readonly FINAL="${OUTPUT_ROOT}/${VERIFICATION_ID}"
readonly OUTPUT="${ATTEMPT}/population_verification.json"

[[ ! -e "${ATTEMPT}" && ! -e "${FINAL}" ]] || {
  echo "TARGETED_POPULATION_OUTPUT_EXISTS" >&2
  exit 1
}
mkdir -p "${ATTEMPT}"
chmod 0700 "${ATTEMPT}"

echo "job_id=${SLURM_JOB_ID}"
echo "hostname=$(hostname)"
echo "start_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "git_commit=${PHASE03_GIT_COMMIT}"
echo "repair_execution_commit=e4a4725399a635476e7d97adcc8e446a592404cd"
echo "repair_job_id=1749448"
echo "development_rows_expected=8000"
echo "expected_population=9/11/9/0/2/11"
echo "locked_access=PROHIBITED"
echo "review_inputs_created=false"
echo "review_databases_created=false"

python -m safe_geocoding_pipeline.phase03.targeted_review_cli \
  verify-repaired-population \
  --development-identities "${DEVELOPMENT_IDENTITIES}" \
  --baseline-core "${BASELINE_CORE}" \
  --baseline-evidence "${BASELINE_EVIDENCE}" \
  --experimental-core "${EXPERIMENTAL_CORE}" \
  --experimental-evidence "${EXPERIMENTAL_EVIDENCE}" \
  --repair-success "${REPAIR_SUCCESS}" \
  --repair-comparison "${REPAIR_COMPARISON}" \
  --output "${OUTPUT}"

python - "${OUTPUT}" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload["status"] != (
    "REPAIRED_TARGETED_REVIEW_POPULATION_VERIFIED_NO_REVIEW_INITIALIZED"
):
    raise SystemExit("TARGETED_POPULATION_STATUS_MISMATCH")
expected = {
    "development_rows": 8000,
    "scientific_output_change_rows": 9,
    "experimental_rule_evidence_rows": 11,
    "overlap_rows": 9,
    "changed_only_rows": 0,
    "evidence_only_rows": 2,
    "targeted_review_population_rows": 11,
    "locked_rows_read": 0,
}
if any(payload[key] != value for key, value in expected.items()):
    raise SystemExit("TARGETED_POPULATION_COUNT_MISMATCH")
if payload["review_inputs_created"] or payload["review_databases_created"]:
    raise SystemExit("TARGETED_POPULATION_REVIEW_BOUNDARY_MISMATCH")
PY

for input in "${INPUTS[@]}"; do
  [[ "$(sha256sum -- "${input}" | cut -d' ' -f1)" == "${INPUT_HASHES[${input}]}" ]] || {
    echo "TARGETED_POPULATION_READ_ONLY_INPUT_CHANGED" >&2
    exit 1
  }
done

mkdir -p "${OUTPUT_ROOT}"
mv "${ATTEMPT}" "${FINAL}"
echo "REPAIRED_TARGETED_REVIEW_POPULATION_VERIFIED_NO_REVIEW_INITIALIZED"
echo "final_report_root=${FINAL}"
echo "end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
