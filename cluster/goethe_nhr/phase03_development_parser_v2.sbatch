#!/usr/bin/env bash
#SBATCH --job-name=safe-phase03-parser-v2
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

readonly DATA_ROOT="/work/footprint/donyadidegan/safe_geocoding_pipeline"
readonly ITERATION_ROOT="${DATA_ROOT}/derived/controlled/phase03_v1/development_iterations"
readonly REPORT_ROOT="${DATA_ROOT}/reports/generated/phase03/development_iterations"

export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1
: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${SLURM_SUBMIT_DIR:?SLURM_SUBMIT_DIR is required}"
: "${PHASE03_GIT_COMMIT:?reviewed parser-v2 commit is required}"
: "${PHASE03_INTEGRATION_ROOT:?detached parser-v2 integration worktree is required}"
: "${PHASE03_SOURCE_RUN_ROOT:?preserved source pilot run root is required}"
: "${PHASE03_DEVELOPMENT_PAYLOAD:?existing 8000-row DEVELOPMENT payload is required}"
: "${PHASE03_DEVELOPMENT_IDENTITIES:?existing DEVELOPMENT identity set is required}"
: "${PHASE03_BASELINE_CORE:?immutable parser-v1 DEVELOPMENT core is required}"
: "${PHASE03_REVIEW_SAMPLING_STATE:?read-only pilot sampling state is required}"

readonly INTEGRATION_ROOT="$(realpath -e -- "${PHASE03_INTEGRATION_ROOT}")"
readonly SOURCE_RUN_ROOT="$(realpath -e -- "${PHASE03_SOURCE_RUN_ROOT}")"
readonly EXPECTED_SBATCH="${INTEGRATION_ROOT}/cluster/goethe_nhr/phase03_development_parser_v2.sbatch"
readonly SUBMIT_DIRECTORY="$(realpath -e -- "${SLURM_SUBMIT_DIR}")"

[[ "${SUBMIT_DIRECTORY}" == "${INTEGRATION_ROOT}" ]] || {
  echo "PARSER_V2_SUBMIT_DIRECTORY_MISMATCH" >&2
  exit 1
}
[[ -r "${EXPECTED_SBATCH}" ]] || {
  echo "PARSER_V2_INTEGRATION_SBATCH_NOT_READABLE" >&2
  exit 1
}
cmp -s -- "${BASH_SOURCE[0]}" "${EXPECTED_SBATCH}" || {
  echo "PARSER_V2_SBATCH_SOURCE_MISMATCH" >&2
  exit 1
}
[[ "$(git -C "${INTEGRATION_ROOT}" rev-parse HEAD)" == "${PHASE03_GIT_COMMIT}" ]] || {
  echo "PARSER_V2_GIT_COMMIT_MISMATCH" >&2
  exit 1
}
[[ -z "$(git -C "${INTEGRATION_ROOT}" symbolic-ref -q --short HEAD)" ]] || {
  echo "PARSER_V2_INTEGRATION_WORKTREE_NOT_DETACHED" >&2
  exit 1
}
[[ -z "$(git -C "${INTEGRATION_ROOT}" status --short)" ]] || {
  echo "PARSER_V2_GIT_WORKTREE_NOT_CLEAN" >&2
  exit 1
}
for input in \
  "${PHASE03_DEVELOPMENT_PAYLOAD}" \
  "${PHASE03_DEVELOPMENT_IDENTITIES}" \
  "${PHASE03_BASELINE_CORE}" \
  "${PHASE03_REVIEW_SAMPLING_STATE}"; do
  [[ -f "${input}" && -r "${input}" ]] || {
    echo "PARSER_V2_REQUIRED_INPUT_NOT_READABLE" >&2
    exit 1
  }
  resolved_input="$(realpath -e -- "${input}")"
  [[ "${resolved_input}" == "${SOURCE_RUN_ROOT}/"* ]] || {
    echo "PARSER_V2_INPUT_OUTSIDE_SOURCE_RUN_ROOT" >&2
    exit 1
  }
  [[ "${resolved_input,,}" != *locked* ]] || {
    echo "PARSER_V2_LOCKED_PATH_PROHIBITED" >&2
    exit 1
  }
done
for output_root in "${ITERATION_ROOT}" "${REPORT_ROOT}"; do
  resolved_output_root="$(realpath -m -- "${output_root}")"
  [[ "${resolved_output_root}" != "${SOURCE_RUN_ROOT}" && \
    "${resolved_output_root}" != "${SOURCE_RUN_ROOT}/"* ]] || {
    echo "PARSER_V2_OUTPUT_UNDER_SOURCE_RUN_ROOT" >&2
    exit 1
  }
done

cd "${INTEGRATION_ROOT}"
source "${DATA_ROOT}/.venv-goethe-nhr/bin/activate"
export PYTHONPATH="${INTEGRATION_ROOT}/src"

python - <<'PY'
import sys
import unicodedata

from safe_geocoding_pipeline.phase03.constants import RULE_REGISTRY_VERSION_V3
from safe_geocoding_pipeline.phase03.rules import load_rule_registry
from safe_geocoding_pipeline.phase03.street_resources import load_street_designators

if sys.version_info[:3] != (3, 14, 3) or unicodedata.unidata_version != "16.0.0":
    raise SystemExit("PARSER_V2_RUNTIME_MISMATCH")
registry = load_rule_registry(registry_version=RULE_REGISTRY_VERSION_V3)
if registry.fingerprint != "a2aadae857b7d4bf7262bd37e6dacf58aae220e00b402ca971c51cea320d6f55":
    raise SystemExit("PARSER_V2_REGISTRY_MISMATCH")
street = load_street_designators()
if street.artifact_sha256 != "0bfbc60f843f8ecf8c3b84cc05e7f342a3da6f5f0f18f1961623566d15dc28cf":
    raise SystemExit("PARSER_V2_STREET_REFERENCE_MISMATCH")
PY

readonly TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
readonly COMMIT_SHORT="${PHASE03_GIT_COMMIT:0:8}"
readonly ITERATION_ID="phase03_development_parser_v2_${TIMESTAMP}_${SLURM_JOB_ID}_${COMMIT_SHORT}"
readonly ATTEMPT="${ITERATION_ROOT}/.in_progress/${ITERATION_ID}"
readonly FINAL="${ITERATION_ROOT}/${ITERATION_ID}"
readonly ATTEMPT_REPORT="${REPORT_ROOT}/.in_progress/${ITERATION_ID}"
readonly FINAL_REPORT="${REPORT_ROOT}/${ITERATION_ID}"

[[ ! -e "${ATTEMPT}" && ! -e "${FINAL}" ]] || {
  echo "PARSER_V2_ITERATION_PATH_EXISTS" >&2
  exit 1
}
[[ ! -e "${ATTEMPT_REPORT}" && ! -e "${FINAL_REPORT}" ]] || {
  echo "PARSER_V2_REPORT_PATH_EXISTS" >&2
  exit 1
}
mkdir -p "${ATTEMPT}" "${ATTEMPT_REPORT}"
chmod 0700 "${ATTEMPT}" "${ATTEMPT_REPORT}"

echo "job_id=${SLURM_JOB_ID}"
echo "hostname=$(hostname)"
echo "start_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "git_commit=${PHASE03_GIT_COMMIT}"
echo "integration_root=${INTEGRATION_ROOT}"
echo "source_run_root=${SOURCE_RUN_ROOT}"
echo "iteration_id=${ITERATION_ID}"
echo "locked_payload_access=PROHIBITED"
echo "pilot_selection_rerun=false"

run_stage() {
  local stage="$1"
  shift
  echo "stage_start=${stage} utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  "$@" >"${ATTEMPT_REPORT}/${stage}.json"
  chmod 0600 "${ATTEMPT_REPORT}/${stage}.json"
  echo "stage_pass=${stage} utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}

phase03_cli() {
  python -m safe_geocoding_pipeline.phase03.cli "$@"
}

run_stage validate_references phase03_cli validate-production-references

run_stage transform_v2 phase03_cli development-transform \
  --input-development-payload "${PHASE03_DEVELOPMENT_PAYLOAD}" \
  --development-identities "${PHASE03_DEVELOPMENT_IDENTITIES}" \
  --output-directory "${ATTEMPT}/transformed" \
  --git-commit "${PHASE03_GIT_COMMIT}" \
  --parser-version conservative_address_parser_v2

run_stage compare_v1_v2 phase03_cli development-compare-parsers \
  --baseline-core "${PHASE03_BASELINE_CORE}" \
  --revised-core "${ATTEMPT}/transformed/core/development.parquet" \
  --output "${ATTEMPT_REPORT}/parser_v1_v2_aggregate.json"

run_stage review_sample_v2 phase03_cli development-review-sample \
  --state-path "${PHASE03_REVIEW_SAMPLING_STATE}" \
  --development-payload "${PHASE03_DEVELOPMENT_PAYLOAD}" \
  --development-core "${ATTEMPT}/transformed/core/development.parquet" \
  --development-evidence "${ATTEMPT}/transformed/evidence/development.parquet" \
  --development-identities "${PHASE03_DEVELOPMENT_IDENTITIES}" \
  --output-directory "${ATTEMPT}/review"

python - "${ATTEMPT}/_SUCCESS.json" "${ATTEMPT_REPORT}" "${ITERATION_ID}" <<'PY'
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

success_path = Path(sys.argv[1])
report_root = Path(sys.argv[2])
payload = {
    "completed_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    "development_rows": 8000,
    "git_commit": os.environ["PHASE03_GIT_COMMIT"],
    "iteration_id": sys.argv[3],
    "locked_payload_rows_read": 0,
    "parser_version": "conservative_address_parser_v2",
    "pilot_selection_rerun": False,
    "reports": {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(report_root.glob("*.json"))
    },
    "rule_registry_version": "phase03_rule_registry_v3",
    "rule_registry_sha256": "a2aadae857b7d4bf7262bd37e6dacf58aae220e00b402ca971c51cea320d6f55",
    "street_designator_reference_id": "street_designators_v2",
    "street_designator_sha256": "0bfbc60f843f8ecf8c3b84cc05e7f342a3da6f5f0f18f1961623566d15dc28cf",
    "status": "DEVELOPMENT_PARSER_V2_ITERATION_COMPLETE",
}
success_path.write_text(
    json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
success_path.chmod(0o600)
PY

mkdir -p "${ITERATION_ROOT}" "${REPORT_ROOT}"
mv "${ATTEMPT_REPORT}" "${FINAL_REPORT}"
mv "${ATTEMPT}" "${FINAL}"
echo "DEVELOPMENT_PARSER_V2_ITERATION_COMPLETE"
echo "final_iteration=${FINAL}"
echo "final_report=${FINAL_REPORT}"
echo "end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
