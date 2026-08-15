#!/usr/bin/env bash
#SBATCH --job-name=safe-phase03-v3-review-prep
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --mail-user=donyadidegan@safe-frankfurt.de
#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

readonly DATA_ROOT="/work/footprint/donyadidegan/safe_geocoding_pipeline"
readonly CONTROLLED_ROOT="${DATA_ROOT}/derived/controlled/phase03_v1"
readonly REVIEW_ROOT="${CONTROLLED_ROOT}/reviews/parser_v3_experimental"
readonly REPORT_ROOT="${DATA_ROOT}/reports/generated/phase03/parser_v3_targeted_review"

export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1
: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${SLURM_SUBMIT_DIR:?SLURM_SUBMIT_DIR is required}"
: "${PHASE03_GIT_COMMIT:?review implementation commit is required}"
: "${PHASE03_INTEGRATION_ROOT:?detached integration worktree is required}"
: "${PHASE03_EXPERIMENT_ITERATION:?parser-v3 iteration identity is required}"
: "${PHASE03_EXPERIMENTAL_PARSER_COMMIT:?parser-v3 execution commit is required}"
: "${PHASE03_DEVELOPMENT_PAYLOAD:?DEVELOPMENT payload is required}"
: "${PHASE03_DEVELOPMENT_IDENTITIES:?DEVELOPMENT identity set is required}"
: "${PHASE03_PARSER_V2_CORE:?parser-v2 core is required}"
: "${PHASE03_PARSER_V2_EVIDENCE:?parser-v2 evidence is required}"
: "${PHASE03_PARSER_V3_CORE:?parser-v3 core is required}"
: "${PHASE03_PARSER_V3_EVIDENCE:?parser-v3 evidence is required}"
: "${PHASE03_TARGETED_REVIEW_EXPECTED_COUNT:?reviewed expected population count is required}"

readonly INTEGRATION_ROOT="$(realpath -e -- "${PHASE03_INTEGRATION_ROOT}")"
readonly RESOLVED_CONTROLLED_ROOT="$(realpath -e -- "${CONTROLLED_ROOT}")"
readonly SUBMIT_DIRECTORY="$(realpath -e -- "${SLURM_SUBMIT_DIR}")"
readonly EXPECTED_SBATCH="${INTEGRATION_ROOT}/cluster/goethe_nhr/phase03_parser_v3_targeted_review_prepare.sbatch"

[[ "${SUBMIT_DIRECTORY}" == "${INTEGRATION_ROOT}" ]] || {
  echo "TARGETED_REVIEW_SUBMIT_DIRECTORY_MISMATCH" >&2
  exit 1
}
cmp -s -- "${BASH_SOURCE[0]}" "${EXPECTED_SBATCH}" || {
  echo "TARGETED_REVIEW_SBATCH_SOURCE_MISMATCH" >&2
  exit 1
}
[[ "$(git -C "${INTEGRATION_ROOT}" rev-parse HEAD)" == "${PHASE03_GIT_COMMIT}" ]] || {
  echo "TARGETED_REVIEW_GIT_COMMIT_MISMATCH" >&2
  exit 1
}
[[ -z "$(git -C "${INTEGRATION_ROOT}" symbolic-ref -q --short HEAD)" ]] || {
  echo "TARGETED_REVIEW_WORKTREE_NOT_DETACHED" >&2
  exit 1
}
[[ -z "$(git -C "${INTEGRATION_ROOT}" status --short)" ]] || {
  echo "TARGETED_REVIEW_WORKTREE_NOT_CLEAN" >&2
  exit 1
}
[[ "${PHASE03_EXPERIMENTAL_PARSER_COMMIT}" == "fa3b924657aed47bfe6aaa80d87353f8d9b78139" ]] || {
  echo "TARGETED_REVIEW_EXPERIMENTAL_COMMIT_MISMATCH" >&2
  exit 1
}
[[ "${PHASE03_TARGETED_REVIEW_EXPECTED_COUNT}" =~ ^[1-9][0-9]*$ ]] || {
  echo "TARGETED_REVIEW_EXPECTED_COUNT_INVALID" >&2
  exit 1
}

readonly INPUTS=(
  "${PHASE03_DEVELOPMENT_PAYLOAD}"
  "${PHASE03_DEVELOPMENT_IDENTITIES}"
  "${PHASE03_PARSER_V2_CORE}"
  "${PHASE03_PARSER_V2_EVIDENCE}"
  "${PHASE03_PARSER_V3_CORE}"
  "${PHASE03_PARSER_V3_EVIDENCE}"
)
for input in "${INPUTS[@]}"; do
  [[ -f "${input}" && -r "${input}" ]] || {
    echo "TARGETED_REVIEW_INPUT_NOT_READABLE" >&2
    exit 1
  }
  resolved_input="$(realpath -e -- "${input}")"
  [[ "${resolved_input}" == "${RESOLVED_CONTROLLED_ROOT}/"* ]] || {
    echo "TARGETED_REVIEW_INPUT_OUTSIDE_CONTROLLED_ROOT" >&2
    exit 1
  }
  [[ "${resolved_input,,}" != *locked* ]] || {
    echo "TARGETED_REVIEW_LOCKED_PATH_PROHIBITED" >&2
    exit 1
  }
done

declare -A INPUT_HASHES
for input in "${INPUTS[@]}"; do
  INPUT_HASHES["${input}"]="$(sha256sum -- "${input}" | cut -d' ' -f1)"
done

cd "${INTEGRATION_ROOT}"
source "${DATA_ROOT}/.venv-goethe-nhr/bin/activate"
export PYTHONPATH="${INTEGRATION_ROOT}/src"

python - <<'PY'
import sys
import unicodedata

from safe_geocoding_pipeline.phase03.constants import (
    RULE_REGISTRY_VERSION_V3,
    RULE_REGISTRY_VERSION_V4,
)
from safe_geocoding_pipeline.phase03.rules import load_rule_registry

if sys.version_info[:3] != (3, 14, 3) or unicodedata.unidata_version != "16.0.0":
    raise SystemExit("TARGETED_REVIEW_RUNTIME_MISMATCH")
if load_rule_registry(registry_version=RULE_REGISTRY_VERSION_V3).fingerprint != (
    "a2aadae857b7d4bf7262bd37e6dacf58aae220e00b402ca971c51cea320d6f55"
):
    raise SystemExit("TARGETED_REVIEW_V2_REGISTRY_MISMATCH")
if load_rule_registry(registry_version=RULE_REGISTRY_VERSION_V4).fingerprint != (
    "2137c4a78cd062aa6f07784deea6046824e99ed7712a591d841e142d2f49dfc5"
):
    raise SystemExit("TARGETED_REVIEW_V3_REGISTRY_MISMATCH")
PY

readonly TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
readonly COMMIT_SHORT="${PHASE03_GIT_COMMIT:0:8}"
readonly REVIEW_ID="phase03_parser_v3_targeted_review_${TIMESTAMP}_${SLURM_JOB_ID}_${COMMIT_SHORT}"
readonly ATTEMPT="${REVIEW_ROOT}/.in_progress/${REVIEW_ID}"
readonly FINAL="${REVIEW_ROOT}/${REVIEW_ID}"
readonly ATTEMPT_REPORT="${REPORT_ROOT}/.in_progress/${REVIEW_ID}"
readonly FINAL_REPORT="${REPORT_ROOT}/${REVIEW_ID}"

[[ ! -e "${ATTEMPT}" && ! -e "${FINAL}" ]] || {
  echo "TARGETED_REVIEW_PATH_EXISTS" >&2
  exit 1
}
mkdir -p "${ATTEMPT}" "${ATTEMPT_REPORT}"
chmod 0700 "${ATTEMPT}" "${ATTEMPT_REPORT}"

echo "job_id=${SLURM_JOB_ID}"
echo "hostname=$(hostname)"
echo "start_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "git_commit=${PHASE03_GIT_COMMIT}"
echo "experimental_parser_commit=${PHASE03_EXPERIMENTAL_PARSER_COMMIT}"
echo "experiment_iteration=${PHASE03_EXPERIMENT_ITERATION}"
echo "targeted_review_id=${REVIEW_ID}"
echo "expected_population_count=${PHASE03_TARGETED_REVIEW_EXPECTED_COUNT}"
echo "locked_access=PROHIBITED"
echo "pilot_selection_rerun=false"
echo "human_labels_created=false"

python -m safe_geocoding_pipeline.phase03.targeted_review_cli prepare \
  --development-payload "${PHASE03_DEVELOPMENT_PAYLOAD}" \
  --development-identities "${PHASE03_DEVELOPMENT_IDENTITIES}" \
  --baseline-core "${PHASE03_PARSER_V2_CORE}" \
  --baseline-evidence "${PHASE03_PARSER_V2_EVIDENCE}" \
  --experimental-core "${PHASE03_PARSER_V3_CORE}" \
  --experimental-evidence "${PHASE03_PARSER_V3_EVIDENCE}" \
  --output-directory "${ATTEMPT}/prepared_inputs" \
  --experiment-iteration "${PHASE03_EXPERIMENT_ITERATION}" \
  --experimental-parser-commit "${PHASE03_EXPERIMENTAL_PARSER_COMMIT}" \
  --review-implementation-commit "${PHASE03_GIT_COMMIT}" \
  --expected-development-rows 8000 \
  --expected-population-count "${PHASE03_TARGETED_REVIEW_EXPECTED_COUNT}" \
  >"${ATTEMPT_REPORT}/prepare.json"
chmod 0600 "${ATTEMPT_REPORT}/prepare.json"

python - "${ATTEMPT}/prepared_inputs/targeted_review_input_manifest.json" "${PHASE03_TARGETED_REVIEW_EXPECTED_COUNT}" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if manifest["status"] != "TARGETED_REVIEW_INPUT_PREPARED_NO_LABELS":
    raise SystemExit("TARGETED_REVIEW_PREPARE_STATUS_MISMATCH")
if manifest["targeted_review_population_rows"] != int(sys.argv[2]):
    raise SystemExit("TARGETED_REVIEW_PREPARE_COUNT_MISMATCH")
if manifest["locked_rows_read"] != 0 or manifest["scientific_promotion_decision"] != "NOT_EVALUATED":
    raise SystemExit("TARGETED_REVIEW_BOUNDARY_MISMATCH")
PY

for input in "${INPUTS[@]}"; do
  [[ "$(sha256sum -- "${input}" | cut -d' ' -f1)" == "${INPUT_HASHES[${input}]}" ]] || {
    echo "TARGETED_REVIEW_READ_ONLY_INPUT_CHANGED" >&2
    exit 1
  }
done

mkdir -p "${REVIEW_ROOT}" "${REPORT_ROOT}"
mv "${ATTEMPT_REPORT}" "${FINAL_REPORT}"
mv "${ATTEMPT}" "${FINAL}"
echo "TARGETED_REVIEW_INPUT_PREPARED_NO_LABELS"
echo "final_review_root=${FINAL}"
echo "final_report_root=${FINAL_REPORT}"
echo "progress_databases_created=false"
echo "end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
