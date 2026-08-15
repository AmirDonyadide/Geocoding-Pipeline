#!/usr/bin/env bash
#SBATCH --job-name=safe-phase03-v3-change-diag
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --mail-user=donyadidegan@safe-frankfurt.de
#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

readonly DATA_ROOT="/work/footprint/donyadidegan/safe_geocoding_pipeline"
readonly CONTROLLED_ROOT="${DATA_ROOT}/derived/controlled/phase03_v1"
readonly REPORT_ROOT="${DATA_ROOT}/reports/generated/phase03/parser_v3_change_diagnostics"

export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1
: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${SLURM_SUBMIT_DIR:?SLURM_SUBMIT_DIR is required}"
: "${PHASE03_GIT_COMMIT:?reviewed diagnostic commit is required}"
: "${PHASE03_INTEGRATION_ROOT:?detached integration worktree is required}"
: "${PHASE03_DEVELOPMENT_IDENTITIES:?DEVELOPMENT identity set is required}"
: "${PHASE03_PARSER_V2_CORE:?parser-v2 core is required}"
: "${PHASE03_PARSER_V2_EVIDENCE:?parser-v2 evidence is required}"
: "${PHASE03_PARSER_V3_CORE:?parser-v3 core is required}"
: "${PHASE03_PARSER_V3_EVIDENCE:?parser-v3 evidence is required}"

readonly INTEGRATION_ROOT="$(realpath -e -- "${PHASE03_INTEGRATION_ROOT}")"
readonly RESOLVED_CONTROLLED_ROOT="$(realpath -e -- "${CONTROLLED_ROOT}")"
readonly RESOLVED_REPORT_PARENT="$(realpath -e -- "${DATA_ROOT}/reports/generated/phase03")"
readonly RESOLVED_REPORT_ROOT="${RESOLVED_REPORT_PARENT}/parser_v3_change_diagnostics"
readonly SUBMIT_DIRECTORY="$(realpath -e -- "${SLURM_SUBMIT_DIR}")"
readonly EXPECTED_SBATCH="${INTEGRATION_ROOT}/cluster/goethe_nhr/phase03_parser_v3_change_diagnostic.sbatch"

[[ "${SUBMIT_DIRECTORY}" == "${INTEGRATION_ROOT}" ]] || {
  echo "V3_CHANGE_DIAGNOSTIC_SUBMIT_DIRECTORY_MISMATCH" >&2
  exit 1
}
cmp -s -- "${BASH_SOURCE[0]}" "${EXPECTED_SBATCH}" || {
  echo "V3_CHANGE_DIAGNOSTIC_SBATCH_SOURCE_MISMATCH" >&2
  exit 1
}
[[ "$(git -C "${INTEGRATION_ROOT}" rev-parse HEAD)" == "${PHASE03_GIT_COMMIT}" ]] || {
  echo "V3_CHANGE_DIAGNOSTIC_GIT_COMMIT_MISMATCH" >&2
  exit 1
}
[[ -z "$(git -C "${INTEGRATION_ROOT}" symbolic-ref -q --short HEAD)" ]] || {
  echo "V3_CHANGE_DIAGNOSTIC_WORKTREE_NOT_DETACHED" >&2
  exit 1
}
[[ -z "$(git -C "${INTEGRATION_ROOT}" status --short)" ]] || {
  echo "V3_CHANGE_DIAGNOSTIC_WORKTREE_NOT_CLEAN" >&2
  exit 1
}

readonly INPUTS=(
  "${PHASE03_PARSER_V2_CORE}"
  "${PHASE03_PARSER_V2_EVIDENCE}"
  "${PHASE03_PARSER_V3_CORE}"
  "${PHASE03_PARSER_V3_EVIDENCE}"
  "${PHASE03_DEVELOPMENT_IDENTITIES}"
)
for input in "${INPUTS[@]}"; do
  [[ -f "${input}" && -r "${input}" ]] || {
    echo "V3_CHANGE_DIAGNOSTIC_INPUT_NOT_READABLE" >&2
    exit 1
  }
  resolved_input="$(realpath -e -- "${input}")"
  [[ "${resolved_input}" == "${RESOLVED_CONTROLLED_ROOT}/"* ]] || {
    echo "V3_CHANGE_DIAGNOSTIC_INPUT_OUTSIDE_CONTROLLED_ROOT" >&2
    exit 1
  }
  [[ "${resolved_input,,}" != *locked* ]] || {
    echo "V3_CHANGE_DIAGNOSTIC_LOCKED_PATH_PROHIBITED" >&2
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
    raise SystemExit("V3_CHANGE_DIAGNOSTIC_RUNTIME_MISMATCH")
if load_rule_registry(registry_version=RULE_REGISTRY_VERSION_V3).fingerprint != (
    "a2aadae857b7d4bf7262bd37e6dacf58aae220e00b402ca971c51cea320d6f55"
):
    raise SystemExit("V3_CHANGE_DIAGNOSTIC_V2_REGISTRY_MISMATCH")
if load_rule_registry(registry_version=RULE_REGISTRY_VERSION_V4).fingerprint != (
    "2137c4a78cd062aa6f07784deea6046824e99ed7712a591d841e142d2f49dfc5"
):
    raise SystemExit("V3_CHANGE_DIAGNOSTIC_V3_REGISTRY_MISMATCH")
PY

readonly TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
readonly COMMIT_SHORT="${PHASE03_GIT_COMMIT:0:8}"
readonly DIAGNOSTIC_ID="phase03_parser_v3_change_diagnostic_${TIMESTAMP}_${SLURM_JOB_ID}_${COMMIT_SHORT}"
readonly ATTEMPT_PARENT="${REPORT_ROOT}/.in_progress"
readonly ATTEMPT="${ATTEMPT_PARENT}/${DIAGNOSTIC_ID}"
readonly FINAL="${REPORT_ROOT}/${DIAGNOSTIC_ID}"

mkdir -p "${REPORT_ROOT}" "${ATTEMPT_PARENT}"
chmod 0700 "${REPORT_ROOT}" "${ATTEMPT_PARENT}"
[[ ! -e "${ATTEMPT}" && ! -e "${FINAL}" ]] || {
  echo "V3_CHANGE_DIAGNOSTIC_OUTPUT_EXISTS" >&2
  exit 1
}

echo "job_id=${SLURM_JOB_ID}"
echo "hostname=$(hostname)"
echo "start_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "git_commit=${PHASE03_GIT_COMMIT}"
echo "diagnostic_id=${DIAGNOSTIC_ID}"
echo "development_rows_expected=8000"
echo "scientific_change_rows_expected=26"
echo "experimental_evidence_rows_expected=11"
echo "overlap_rows_expected=9"
echo "changed_only_rows_expected=17"
echo "evidence_only_rows_expected=2"
echo "union_rows_expected=28"
echo "locked_payload_access=PROHIBITED"
echo "raw_values_reported=false"
echo "human_labels_read=false"

python -m safe_geocoding_pipeline.phase03.cli \
  development-diagnose-parser-v2-v3-changes \
  --baseline-core "${PHASE03_PARSER_V2_CORE}" \
  --baseline-evidence "${PHASE03_PARSER_V2_EVIDENCE}" \
  --experimental-core "${PHASE03_PARSER_V3_CORE}" \
  --experimental-evidence "${PHASE03_PARSER_V3_EVIDENCE}" \
  --development-identities "${PHASE03_DEVELOPMENT_IDENTITIES}" \
  --controlled-root "${RESOLVED_CONTROLLED_ROOT}" \
  --report-root "${RESOLVED_REPORT_ROOT}" \
  --output-directory "${ATTEMPT}" \
  --implementation-commit "${PHASE03_GIT_COMMIT}"

for input in "${INPUTS[@]}"; do
  [[ "$(sha256sum -- "${input}" | cut -d' ' -f1)" == "${INPUT_HASHES[${input}]}" ]] || {
    echo "V3_CHANGE_DIAGNOSTIC_READ_ONLY_INPUT_CHANGED" >&2
    exit 1
  }
done

mv "${ATTEMPT}" "${FINAL}"
find "${FINAL}" -type d -exec chmod 0700 {} +
find "${FINAL}" -type f -exec chmod 0600 {} +

echo "SANITIZED_DEVELOPMENT_V3_CHANGE_DIAGNOSTIC_COMPLETE"
echo "diagnostic_id=${DIAGNOSTIC_ID}"
echo "report_root=${FINAL}"
echo "locked_rows_read=0"
echo "scientific_rule_change=false"
echo "end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
