#!/usr/bin/env bash
#SBATCH --job-name=safe-phase03-country-method-repair
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=04:00:00
#SBATCH --mail-user=donyadidegan@safe-frankfurt.de
#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

readonly DATA_ROOT="/work/footprint/donyadidegan/safe_geocoding_pipeline"
readonly CONTROLLED_ROOT="${DATA_ROOT}/derived/controlled/phase03_v1"
readonly ITERATION_ROOT="${CONTROLLED_ROOT}/development_iterations"
readonly REPORT_ROOT="${DATA_ROOT}/reports/generated/phase03/development_iterations"

export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1
: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${SLURM_SUBMIT_DIR:?SLURM_SUBMIT_DIR is required}"
: "${PHASE03_GIT_COMMIT:?reviewed country-method repair commit is required}"
: "${PHASE03_INTEGRATION_ROOT:?detached repair integration worktree is required}"
: "${PHASE03_SOURCE_RUN_ROOT:?preserved source pilot run root is required}"
: "${PHASE03_DEVELOPMENT_PAYLOAD:?existing 8000-row DEVELOPMENT payload is required}"
: "${PHASE03_DEVELOPMENT_IDENTITIES:?existing DEVELOPMENT identity set is required}"

readonly INTEGRATION_ROOT="$(realpath -e -- "${PHASE03_INTEGRATION_ROOT}")"
readonly RESOLVED_CONTROLLED_ROOT="$(realpath -e -- "${CONTROLLED_ROOT}")"
readonly SOURCE_RUN_ROOT="$(realpath -e -- "${PHASE03_SOURCE_RUN_ROOT}")"
readonly EXPECTED_SBATCH="${INTEGRATION_ROOT}/cluster/goethe_nhr/phase03_country_method_repair.sbatch"
readonly SUBMIT_DIRECTORY="$(realpath -e -- "${SLURM_SUBMIT_DIR}")"

[[ "${SUBMIT_DIRECTORY}" == "${INTEGRATION_ROOT}" ]] || {
  echo "COUNTRY_METHOD_REPAIR_SUBMIT_DIRECTORY_MISMATCH" >&2
  exit 1
}
[[ -r "${EXPECTED_SBATCH}" ]] || {
  echo "COUNTRY_METHOD_REPAIR_SBATCH_NOT_READABLE" >&2
  exit 1
}
cmp -s -- "${BASH_SOURCE[0]}" "${EXPECTED_SBATCH}" || {
  echo "COUNTRY_METHOD_REPAIR_SBATCH_SOURCE_MISMATCH" >&2
  exit 1
}
[[ "$(git -C "${INTEGRATION_ROOT}" rev-parse HEAD)" == "${PHASE03_GIT_COMMIT}" ]] || {
  echo "COUNTRY_METHOD_REPAIR_GIT_COMMIT_MISMATCH" >&2
  exit 1
}
[[ -z "$(git -C "${INTEGRATION_ROOT}" symbolic-ref -q --short HEAD)" ]] || {
  echo "COUNTRY_METHOD_REPAIR_WORKTREE_NOT_DETACHED" >&2
  exit 1
}
[[ -z "$(git -C "${INTEGRATION_ROOT}" status --short)" ]] || {
  echo "COUNTRY_METHOD_REPAIR_WORKTREE_NOT_CLEAN" >&2
  exit 1
}
[[ "${SOURCE_RUN_ROOT}" == "${RESOLVED_CONTROLLED_ROOT}/pilots/"* ]] || {
  echo "COUNTRY_METHOD_REPAIR_SOURCE_RUN_ROOT_INVALID" >&2
  exit 1
}
for input in \
  "${PHASE03_DEVELOPMENT_PAYLOAD}" \
  "${PHASE03_DEVELOPMENT_IDENTITIES}"; do
  [[ -f "${input}" && -r "${input}" ]] || {
    echo "COUNTRY_METHOD_REPAIR_REQUIRED_INPUT_NOT_READABLE" >&2
    exit 1
  }
  resolved_input="$(realpath -e -- "${input}")"
  [[ "${resolved_input}" == "${SOURCE_RUN_ROOT}/"* ]] || {
    echo "COUNTRY_METHOD_REPAIR_INPUT_OUTSIDE_SOURCE_RUN_ROOT" >&2
    exit 1
  }
  [[ "${resolved_input,,}" != *locked* ]] || {
    echo "COUNTRY_METHOD_REPAIR_LOCKED_PATH_PROHIBITED" >&2
    exit 1
  }
done
for output_root in "${ITERATION_ROOT}" "${REPORT_ROOT}"; do
  resolved_output_root="$(realpath -m -- "${output_root}")"
  [[ "${resolved_output_root}" != "${SOURCE_RUN_ROOT}" && \
    "${resolved_output_root}" != "${SOURCE_RUN_ROOT}/"* ]] || {
    echo "COUNTRY_METHOD_REPAIR_OUTPUT_UNDER_SOURCE_RUN_ROOT" >&2
    exit 1
  }
done

export PHASE03_DEVELOPMENT_PAYLOAD_SHA256_BEFORE
export PHASE03_DEVELOPMENT_IDENTITIES_SHA256_BEFORE
export PHASE03_DEVELOPMENT_PAYLOAD
export PHASE03_DEVELOPMENT_IDENTITIES
PHASE03_DEVELOPMENT_PAYLOAD_SHA256_BEFORE="$(sha256sum -- "${PHASE03_DEVELOPMENT_PAYLOAD}" | cut -d' ' -f1)"
PHASE03_DEVELOPMENT_IDENTITIES_SHA256_BEFORE="$(sha256sum -- "${PHASE03_DEVELOPMENT_IDENTITIES}" | cut -d' ' -f1)"

cd "${INTEGRATION_ROOT}"
source "${DATA_ROOT}/.venv-goethe-nhr/bin/activate"
export PYTHONPATH="${INTEGRATION_ROOT}/src"

python - <<'PY'
import sys
import unicodedata

from safe_geocoding_pipeline.phase03.config import Phase03Config
from safe_geocoding_pipeline.phase03.constants import (
    PARSER_VERSION_V2_1,
    PARSER_VERSION_V3_1,
)
from safe_geocoding_pipeline.phase03.engine import Phase03Engine
from safe_geocoding_pipeline.phase03.references import load_production_references
from safe_geocoding_pipeline.phase03.rules import load_rule_registry

if sys.version_info[:3] != (3, 14, 3) or unicodedata.unidata_version != "16.0.0":
    raise SystemExit("COUNTRY_METHOD_REPAIR_RUNTIME_MISMATCH")
expected = {
    PARSER_VERSION_V2_1: (
        "a2aadae857b7d4bf7262bd37e6dacf58aae220e00b402ca971c51cea320d6f55",
        "25962a126cd5d30c13607bd564aa250e91096e6961745670772a1ce31b76ac4d",
    ),
    PARSER_VERSION_V3_1: (
        "2137c4a78cd062aa6f07784deea6046824e99ed7712a591d841e142d2f49dfc5",
        "50e06ad6d7ad428811bdefe30ed6ef7e0d6b9eacbbbdce9a53c6809fd812333a",
    ),
}
for parser_version, (registry_sha256, configuration_sha256) in expected.items():
    config = Phase03Config.for_parser_version(parser_version)
    registry = load_rule_registry(registry_version=config.rule_registry_version)
    if registry.fingerprint != registry_sha256:
        raise SystemExit("COUNTRY_METHOD_REPAIR_REGISTRY_MISMATCH")
    country, scripts = load_production_references(
        expected_country_reference_id=config.country_reference_version,
        expected_unicode_reference_id=config.unicode_reference_version,
    )
    parser = Phase03Engine(
        config,
        registry,
        country_reference=country,
        script_reference=scripts,
        implementation_fingerprint=bytes(32),
        execution_scope="DEVELOPMENT",
    )
    if parser.configuration_fingerprint.hex() != configuration_sha256:
        raise SystemExit("COUNTRY_METHOD_REPAIR_CONFIGURATION_MISMATCH")
PY

readonly TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
readonly COMMIT_SHORT="${PHASE03_GIT_COMMIT:0:8}"
readonly ITERATION_ID="phase03_development_country_method_repair_${TIMESTAMP}_${SLURM_JOB_ID}_${COMMIT_SHORT}"
readonly ATTEMPT="${ITERATION_ROOT}/.in_progress/${ITERATION_ID}"
readonly FINAL="${ITERATION_ROOT}/${ITERATION_ID}"
readonly ATTEMPT_REPORT="${REPORT_ROOT}/.in_progress/${ITERATION_ID}"
readonly FINAL_REPORT="${REPORT_ROOT}/${ITERATION_ID}"

[[ ! -e "${ATTEMPT}" && ! -e "${FINAL}" ]] || {
  echo "COUNTRY_METHOD_REPAIR_ITERATION_PATH_EXISTS" >&2
  exit 1
}
[[ ! -e "${ATTEMPT_REPORT}" && ! -e "${FINAL_REPORT}" ]] || {
  echo "COUNTRY_METHOD_REPAIR_REPORT_PATH_EXISTS" >&2
  exit 1
}
mkdir -p "${ATTEMPT}" "${ATTEMPT_REPORT}"
chmod 0700 "${ATTEMPT}" "${ATTEMPT_REPORT}"

echo "job_id=${SLURM_JOB_ID}"
echo "hostname=$(hostname)"
echo "start_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "git_commit=${PHASE03_GIT_COMMIT}"
echo "iteration_id=${ITERATION_ID}"
echo "development_rows_expected=8000"
echo "locked_payload_access=PROHIBITED"
echo "pilot_selection_rerun=false"
echo "historical_iterations=READ_ONLY"

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

run_stage transform_v2_1 phase03_cli development-transform \
  --input-development-payload "${PHASE03_DEVELOPMENT_PAYLOAD}" \
  --development-identities "${PHASE03_DEVELOPMENT_IDENTITIES}" \
  --output-directory "${ATTEMPT}/parser_v2_1/transformed" \
  --git-commit "${PHASE03_GIT_COMMIT}" \
  --parser-version conservative_address_parser_v2_1

run_stage transform_v3_1_experimental phase03_cli development-transform \
  --input-development-payload "${PHASE03_DEVELOPMENT_PAYLOAD}" \
  --development-identities "${PHASE03_DEVELOPMENT_IDENTITIES}" \
  --output-directory "${ATTEMPT}/parser_v3_1_experimental/transformed" \
  --git-commit "${PHASE03_GIT_COMMIT}" \
  --parser-version conservative_address_parser_v3_1_experimental

run_stage compare_v2_1_v3_1 phase03_cli development-compare-parser-v2-1-v3-1 \
  --baseline-core "${ATTEMPT}/parser_v2_1/transformed/core/development.parquet" \
  --baseline-evidence "${ATTEMPT}/parser_v2_1/transformed/evidence/development.parquet" \
  --revised-core "${ATTEMPT}/parser_v3_1_experimental/transformed/core/development.parquet" \
  --revised-evidence "${ATTEMPT}/parser_v3_1_experimental/transformed/evidence/development.parquet" \
  --output "${ATTEMPT_REPORT}/parser_v2_1_v3_1_aggregate.json"

python - "${ATTEMPT}/_SUCCESS.json" "${ATTEMPT_REPORT}" "${ITERATION_ID}" <<'PY'
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


inputs = {
    "development_payload": (
        Path(os.environ["PHASE03_DEVELOPMENT_PAYLOAD"]),
        os.environ["PHASE03_DEVELOPMENT_PAYLOAD_SHA256_BEFORE"],
    ),
    "development_identities": (
        Path(os.environ["PHASE03_DEVELOPMENT_IDENTITIES"]),
        os.environ["PHASE03_DEVELOPMENT_IDENTITIES_SHA256_BEFORE"],
    ),
}
input_artifacts = {}
for role, (path, expected_sha256) in inputs.items():
    actual_sha256 = sha256_file(path)
    if actual_sha256 != expected_sha256:
        raise SystemExit("COUNTRY_METHOD_REPAIR_READ_ONLY_INPUT_CHANGED")
    input_artifacts[role] = {
        "sha256": actual_sha256,
        "size_bytes": path.stat().st_size,
    }

success_path = Path(sys.argv[1])
report_root = Path(sys.argv[2])
payload = {
    "completed_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    "development_rows": 8000,
    "git_commit": os.environ["PHASE03_GIT_COMMIT"],
    "input_artifacts": input_artifacts,
    "iteration_id": sys.argv[3],
    "locked_payload_rows_read": 0,
    "parser_versions": {
        "baseline": "conservative_address_parser_v2_1",
        "experimental": "conservative_address_parser_v3_1_experimental",
    },
    "pilot_selection_rerun": False,
    "promotion_decision": "NOT_EVALUATED",
    "reports": {
        path.name: sha256_file(path) for path in sorted(report_root.glob("*.json"))
    },
    "rule_registry_versions": {
        "baseline": "phase03_rule_registry_v3",
        "experimental": "phase03_rule_registry_v4_experimental",
    },
    "status": "DEVELOPMENT_COUNTRY_METHOD_REPAIR_COMPARISON_COMPLETE",
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
echo "DEVELOPMENT_COUNTRY_METHOD_REPAIR_COMPARISON_COMPLETE"
echo "final_iteration=${FINAL}"
echo "final_report=${FINAL_REPORT}"
echo "end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
