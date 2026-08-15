#!/usr/bin/env bash
#SBATCH --job-name=safe-phase03-parser-v3-exp
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=02:00:00
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
: "${PHASE03_GIT_COMMIT:?reviewed parser-v3 experimental commit is required}"
: "${PHASE03_INTEGRATION_ROOT:?detached parser-v3 integration worktree is required}"
: "${PHASE03_SOURCE_RUN_ROOT:?preserved source pilot run root is required}"
: "${PHASE03_DEVELOPMENT_PAYLOAD:?existing 8000-row DEVELOPMENT payload is required}"
: "${PHASE03_DEVELOPMENT_IDENTITIES:?existing DEVELOPMENT identity set is required}"
: "${PHASE03_PARSER_V2_CORE:?immutable parser-v2 DEVELOPMENT core is required}"
: "${PHASE03_PARSER_V2_EVIDENCE:?immutable parser-v2 DEVELOPMENT evidence is required}"

readonly INTEGRATION_ROOT="$(realpath -e -- "${PHASE03_INTEGRATION_ROOT}")"
readonly RESOLVED_CONTROLLED_ROOT="$(realpath -e -- "${CONTROLLED_ROOT}")"
readonly SOURCE_RUN_ROOT="$(realpath -e -- "${PHASE03_SOURCE_RUN_ROOT}")"
readonly EXPECTED_SBATCH="${INTEGRATION_ROOT}/cluster/goethe_nhr/phase03_development_parser_v3_experimental.sbatch"
readonly SUBMIT_DIRECTORY="$(realpath -e -- "${SLURM_SUBMIT_DIR}")"

[[ "${SUBMIT_DIRECTORY}" == "${INTEGRATION_ROOT}" ]] || {
  echo "PARSER_V3_SUBMIT_DIRECTORY_MISMATCH" >&2
  exit 1
}
[[ -r "${EXPECTED_SBATCH}" ]] || {
  echo "PARSER_V3_INTEGRATION_SBATCH_NOT_READABLE" >&2
  exit 1
}
cmp -s -- "${BASH_SOURCE[0]}" "${EXPECTED_SBATCH}" || {
  echo "PARSER_V3_SBATCH_SOURCE_MISMATCH" >&2
  exit 1
}
[[ "$(git -C "${INTEGRATION_ROOT}" rev-parse HEAD)" == "${PHASE03_GIT_COMMIT}" ]] || {
  echo "PARSER_V3_GIT_COMMIT_MISMATCH" >&2
  exit 1
}
[[ -z "$(git -C "${INTEGRATION_ROOT}" symbolic-ref -q --short HEAD)" ]] || {
  echo "PARSER_V3_INTEGRATION_WORKTREE_NOT_DETACHED" >&2
  exit 1
}
[[ -z "$(git -C "${INTEGRATION_ROOT}" status --short)" ]] || {
  echo "PARSER_V3_GIT_WORKTREE_NOT_CLEAN" >&2
  exit 1
}
[[ "${SOURCE_RUN_ROOT}" == "${RESOLVED_CONTROLLED_ROOT}/pilots/"* ]] || {
  echo "PARSER_V3_SOURCE_RUN_ROOT_INVALID" >&2
  exit 1
}
for input in \
  "${PHASE03_DEVELOPMENT_PAYLOAD}" \
  "${PHASE03_DEVELOPMENT_IDENTITIES}" \
  "${PHASE03_PARSER_V2_CORE}" \
  "${PHASE03_PARSER_V2_EVIDENCE}"; do
  [[ -f "${input}" && -r "${input}" ]] || {
    echo "PARSER_V3_REQUIRED_INPUT_NOT_READABLE" >&2
    exit 1
  }
  resolved_input="$(realpath -e -- "${input}")"
  [[ "${resolved_input}" == "${RESOLVED_CONTROLLED_ROOT}/"* ]] || {
    echo "PARSER_V3_INPUT_OUTSIDE_CONTROLLED_ROOT" >&2
    exit 1
  }
  [[ "${resolved_input,,}" != *locked* ]] || {
    echo "PARSER_V3_LOCKED_PATH_PROHIBITED" >&2
    exit 1
  }
done
for output_root in "${ITERATION_ROOT}" "${REPORT_ROOT}"; do
  resolved_output_root="$(realpath -m -- "${output_root}")"
  [[ "${resolved_output_root}" != "${SOURCE_RUN_ROOT}" && \
    "${resolved_output_root}" != "${SOURCE_RUN_ROOT}/"* ]] || {
    echo "PARSER_V3_OUTPUT_UNDER_SOURCE_RUN_ROOT" >&2
    exit 1
  }
done

export PHASE03_DEVELOPMENT_PAYLOAD_SHA256_BEFORE
export PHASE03_DEVELOPMENT_IDENTITIES_SHA256_BEFORE
export PHASE03_PARSER_V2_CORE_SHA256_BEFORE
export PHASE03_PARSER_V2_EVIDENCE_SHA256_BEFORE
PHASE03_DEVELOPMENT_PAYLOAD_SHA256_BEFORE="$(sha256sum -- "${PHASE03_DEVELOPMENT_PAYLOAD}" | cut -d' ' -f1)"
PHASE03_DEVELOPMENT_IDENTITIES_SHA256_BEFORE="$(sha256sum -- "${PHASE03_DEVELOPMENT_IDENTITIES}" | cut -d' ' -f1)"
PHASE03_PARSER_V2_CORE_SHA256_BEFORE="$(sha256sum -- "${PHASE03_PARSER_V2_CORE}" | cut -d' ' -f1)"
PHASE03_PARSER_V2_EVIDENCE_SHA256_BEFORE="$(sha256sum -- "${PHASE03_PARSER_V2_EVIDENCE}" | cut -d' ' -f1)"

cd "${INTEGRATION_ROOT}"
source "${DATA_ROOT}/.venv-goethe-nhr/bin/activate"
export PYTHONPATH="${INTEGRATION_ROOT}/src"

python - <<'PY'
import sys
import unicodedata

from safe_geocoding_pipeline.phase03.config import Phase03Config
from safe_geocoding_pipeline.phase03.constants import (
    PARSER_VERSION_V3,
    RULE_REGISTRY_VERSION_V4,
)
from safe_geocoding_pipeline.phase03.engine import Phase03Engine
from safe_geocoding_pipeline.phase03.references import load_production_references
from safe_geocoding_pipeline.phase03.rules import load_rule_registry
from safe_geocoding_pipeline.phase03.street_resources import load_street_designators

if sys.version_info[:3] != (3, 14, 3) or unicodedata.unidata_version != "16.0.0":
    raise SystemExit("PARSER_V3_RUNTIME_MISMATCH")
config = Phase03Config.for_parser_version(PARSER_VERSION_V3)
registry = load_rule_registry(registry_version=RULE_REGISTRY_VERSION_V4)
if registry.fingerprint != "2137c4a78cd062aa6f07784deea6046824e99ed7712a591d841e142d2f49dfc5":
    raise SystemExit("PARSER_V3_REGISTRY_MISMATCH")
country, scripts = load_production_references(
    expected_country_reference_id=config.country_reference_version,
    expected_unicode_reference_id=config.unicode_reference_version,
)
engine = Phase03Engine(
    config,
    registry,
    country_reference=country,
    script_reference=scripts,
    implementation_fingerprint=bytes(32),
    execution_scope="DEVELOPMENT",
)
if engine.configuration_fingerprint.hex() != "4ad2febb4c1d3a333a76a4a4ad02232958245f99715032d497ab1ee1c3266ee3":
    raise SystemExit("PARSER_V3_CONFIGURATION_MISMATCH")
street = load_street_designators()
if street.artifact_sha256 != "0bfbc60f843f8ecf8c3b84cc05e7f342a3da6f5f0f18f1961623566d15dc28cf":
    raise SystemExit("PARSER_V3_STREET_REFERENCE_MISMATCH")
PY

readonly TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
readonly COMMIT_SHORT="${PHASE03_GIT_COMMIT:0:8}"
readonly ITERATION_ID="phase03_development_parser_v3_experimental_${TIMESTAMP}_${SLURM_JOB_ID}_${COMMIT_SHORT}"
readonly ATTEMPT="${ITERATION_ROOT}/.in_progress/${ITERATION_ID}"
readonly FINAL="${ITERATION_ROOT}/${ITERATION_ID}"
readonly ATTEMPT_REPORT="${REPORT_ROOT}/.in_progress/${ITERATION_ID}"
readonly FINAL_REPORT="${REPORT_ROOT}/${ITERATION_ID}"

[[ ! -e "${ATTEMPT}" && ! -e "${FINAL}" ]] || {
  echo "PARSER_V3_ITERATION_PATH_EXISTS" >&2
  exit 1
}
[[ ! -e "${ATTEMPT_REPORT}" && ! -e "${FINAL_REPORT}" ]] || {
  echo "PARSER_V3_REPORT_PATH_EXISTS" >&2
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
echo "parser_v2_inputs=READ_ONLY"

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

run_stage transform_v3_experimental phase03_cli development-transform \
  --input-development-payload "${PHASE03_DEVELOPMENT_PAYLOAD}" \
  --development-identities "${PHASE03_DEVELOPMENT_IDENTITIES}" \
  --output-directory "${ATTEMPT}/transformed" \
  --git-commit "${PHASE03_GIT_COMMIT}" \
  --parser-version conservative_address_parser_v3_experimental

run_stage compare_v2_v3 phase03_cli development-compare-parser-v2-v3 \
  --baseline-core "${PHASE03_PARSER_V2_CORE}" \
  --baseline-evidence "${PHASE03_PARSER_V2_EVIDENCE}" \
  --revised-core "${ATTEMPT}/transformed/core/development.parquet" \
  --revised-evidence "${ATTEMPT}/transformed/evidence/development.parquet" \
  --output "${ATTEMPT_REPORT}/parser_v2_v3_aggregate.json"

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
    "input_artifacts": {},
    "locked_payload_rows_read": 0,
    "parser_version": "conservative_address_parser_v3_experimental",
    "pilot_selection_rerun": False,
    "promotion_decision": "NOT_EVALUATED",
    "reports": {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(report_root.glob("*.json"))
    },
    "rule_registry_version": "phase03_rule_registry_v4_experimental",
    "rule_registry_sha256": "2137c4a78cd062aa6f07784deea6046824e99ed7712a591d841e142d2f49dfc5",
    "status": "DEVELOPMENT_PARSER_V3_EXPERIMENTAL_COMPARISON_COMPLETE",
}
inputs = {
    "development_payload": (
        Path(os.environ["PHASE03_DEVELOPMENT_PAYLOAD"]),
        os.environ["PHASE03_DEVELOPMENT_PAYLOAD_SHA256_BEFORE"],
    ),
    "development_identities": (
        Path(os.environ["PHASE03_DEVELOPMENT_IDENTITIES"]),
        os.environ["PHASE03_DEVELOPMENT_IDENTITIES_SHA256_BEFORE"],
    ),
    "parser_v2_core": (
        Path(os.environ["PHASE03_PARSER_V2_CORE"]),
        os.environ["PHASE03_PARSER_V2_CORE_SHA256_BEFORE"],
    ),
    "parser_v2_evidence": (
        Path(os.environ["PHASE03_PARSER_V2_EVIDENCE"]),
        os.environ["PHASE03_PARSER_V2_EVIDENCE_SHA256_BEFORE"],
    ),
}
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

for role, (path, expected_sha256) in inputs.items():
    actual_sha256 = sha256_file(path)
    if actual_sha256 != expected_sha256:
        raise SystemExit("PARSER_V3_READ_ONLY_INPUT_CHANGED")
    payload["input_artifacts"][role] = {
        "sha256": actual_sha256,
        "size_bytes": path.stat().st_size,
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
echo "DEVELOPMENT_PARSER_V3_EXPERIMENTAL_COMPARISON_COMPLETE"
echo "final_iteration=${FINAL}"
echo "final_report=${FINAL_REPORT}"
echo "end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
