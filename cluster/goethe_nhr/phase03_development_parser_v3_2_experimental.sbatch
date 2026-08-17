#!/usr/bin/env bash
#SBATCH --job-name=safe-phase03-parser-v32
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
: "${PHASE03_GIT_COMMIT:?reviewed parser-v3.2 commit is required}"
: "${PHASE03_INTEGRATION_ROOT:?detached parser-v3.2 worktree is required}"
: "${PHASE03_SOURCE_RUN_ROOT:?preserved source pilot root is required}"
: "${PHASE03_DEVELOPMENT_PAYLOAD:?frozen DEVELOPMENT payload is required}"
: "${PHASE03_DEVELOPMENT_IDENTITIES:?frozen DEVELOPMENT identities are required}"
: "${PHASE03_BASELINE_CORE:?repaired parser-v2.1 core is required}"
: "${PHASE03_BASELINE_EVIDENCE:?repaired parser-v2.1 evidence is required}"
: "${PHASE03_TARGETED_INPUT_MANIFEST:?historical targeted manifest is required}"
: "${PHASE03_TARGETED_CONTEXT:?historical protected context is required}"
: "${PHASE03_TARGETED_R01_LABELS:?completed controlled R01 labels are required}"

readonly INTEGRATION_ROOT="$(realpath -e -- "${PHASE03_INTEGRATION_ROOT}")"
readonly SOURCE_RUN_ROOT="$(realpath -e -- "${PHASE03_SOURCE_RUN_ROOT}")"
readonly RESOLVED_CONTROLLED_ROOT="$(realpath -e -- "${CONTROLLED_ROOT}")"
readonly EXPECTED_SBATCH="${INTEGRATION_ROOT}/cluster/goethe_nhr/phase03_development_parser_v3_2_experimental.sbatch"
readonly SUBMIT_DIRECTORY="$(realpath -e -- "${SLURM_SUBMIT_DIR}")"

[[ "${SUBMIT_DIRECTORY}" == "${INTEGRATION_ROOT}" ]] || {
  echo "PARSER_V3_2_SUBMIT_DIRECTORY_MISMATCH" >&2
  exit 1
}
[[ -r "${EXPECTED_SBATCH}" ]] || {
  echo "PARSER_V3_2_SBATCH_NOT_READABLE" >&2
  exit 1
}
cmp -s -- "${BASH_SOURCE[0]}" "${EXPECTED_SBATCH}" || {
  echo "PARSER_V3_2_SBATCH_SOURCE_MISMATCH" >&2
  exit 1
}
[[ "$(git -C "${INTEGRATION_ROOT}" rev-parse HEAD)" == "${PHASE03_GIT_COMMIT}" ]] || {
  echo "PARSER_V3_2_GIT_COMMIT_MISMATCH" >&2
  exit 1
}
[[ -z "$(git -C "${INTEGRATION_ROOT}" symbolic-ref -q --short HEAD)" ]] || {
  echo "PARSER_V3_2_WORKTREE_NOT_DETACHED" >&2
  exit 1
}
[[ -z "$(git -C "${INTEGRATION_ROOT}" status --short)" ]] || {
  echo "PARSER_V3_2_WORKTREE_NOT_CLEAN" >&2
  exit 1
}
[[ "${SOURCE_RUN_ROOT}" == "${RESOLVED_CONTROLLED_ROOT}/pilots/"* ]] || {
  echo "PARSER_V3_2_SOURCE_RUN_ROOT_INVALID" >&2
  exit 1
}

readonly -a INPUTS=(
  "${PHASE03_DEVELOPMENT_PAYLOAD}"
  "${PHASE03_DEVELOPMENT_IDENTITIES}"
  "${PHASE03_BASELINE_CORE}"
  "${PHASE03_BASELINE_EVIDENCE}"
  "${PHASE03_TARGETED_INPUT_MANIFEST}"
  "${PHASE03_TARGETED_CONTEXT}"
  "${PHASE03_TARGETED_R01_LABELS}"
)
for input in "${INPUTS[@]}"; do
  [[ -f "${input}" && -r "${input}" ]] || {
    echo "PARSER_V3_2_REQUIRED_INPUT_NOT_READABLE" >&2
    exit 1
  }
  resolved_input="$(realpath -e -- "${input}")"
  [[ "${resolved_input}" == "${RESOLVED_CONTROLLED_ROOT}/"* ]] || {
    echo "PARSER_V3_2_INPUT_OUTSIDE_CONTROLLED_ROOT" >&2
    exit 1
  }
  [[ "${resolved_input,,}" != *locked* ]] || {
    echo "PARSER_V3_2_LOCKED_PATH_PROHIBITED" >&2
    exit 1
  }
done
for output_root in "${ITERATION_ROOT}" "${REPORT_ROOT}"; do
  resolved_output_root="$(realpath -m -- "${output_root}")"
  [[ "${resolved_output_root}" != "${SOURCE_RUN_ROOT}" && \
    "${resolved_output_root}" != "${SOURCE_RUN_ROOT}/"* ]] || {
    echo "PARSER_V3_2_OUTPUT_UNDER_SOURCE_RUN_ROOT" >&2
    exit 1
  }
done

readonly INPUT_HASH_FILE="$(mktemp)"
trap 'rm -f -- "${INPUT_HASH_FILE}"' EXIT
for input in "${INPUTS[@]}"; do
  printf '%s  %s\n' "$(sha256sum -- "${input}" | cut -d' ' -f1)" "${input}" \
    >>"${INPUT_HASH_FILE}"
done

cd "${INTEGRATION_ROOT}"
source "${DATA_ROOT}/.venv-goethe-nhr/bin/activate"
export PYTHONPATH="${INTEGRATION_ROOT}/src"

python - <<'PY'
import sys
import unicodedata

from safe_geocoding_pipeline.phase03.config import Phase03Config
from safe_geocoding_pipeline.phase03.constants import (
    PARSER_VERSION_V2_1,
    PARSER_VERSION_V3_2,
    RULE_REGISTRY_VERSION_V3,
    RULE_REGISTRY_VERSION_V5,
)
from safe_geocoding_pipeline.phase03.engine import Phase03Engine
from safe_geocoding_pipeline.phase03.references import load_production_references
from safe_geocoding_pipeline.phase03.rules import load_rule_registry

if sys.version_info[:3] != (3, 14, 3) or unicodedata.unidata_version != "16.0.0":
    raise SystemExit("PARSER_V3_2_RUNTIME_MISMATCH")
expected = {
    PARSER_VERSION_V2_1: (
        RULE_REGISTRY_VERSION_V3,
        "a2aadae857b7d4bf7262bd37e6dacf58aae220e00b402ca971c51cea320d6f55",
        "25962a126cd5d30c13607bd564aa250e91096e6961745670772a1ce31b76ac4d",
    ),
    PARSER_VERSION_V3_2: (
        RULE_REGISTRY_VERSION_V5,
        "4e66e0be62c3d0aae3e9452babe7d16f312c7bb49c69af1a2a0e6839cc3bb1fd",
        "89370fddf5f9dae8f381f62344df4da96f0b3dc34627cff23a8068555b909a73",
    ),
}
for parser_version, (registry_version, registry_sha256, configuration_sha256) in expected.items():
    config = Phase03Config.for_parser_version(parser_version)
    registry = load_rule_registry(registry_version=registry_version)
    if registry.fingerprint != registry_sha256:
        raise SystemExit("PARSER_V3_2_REGISTRY_MISMATCH")
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
    if engine.configuration_fingerprint.hex() != configuration_sha256:
        raise SystemExit("PARSER_V3_2_CONFIGURATION_MISMATCH")
PY

readonly TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
readonly COMMIT_SHORT="${PHASE03_GIT_COMMIT:0:8}"
readonly ITERATION_ID="phase03_development_parser_v3_2_experimental_${TIMESTAMP}_${SLURM_JOB_ID}_${COMMIT_SHORT}"
readonly ATTEMPT="${ITERATION_ROOT}/.in_progress/${ITERATION_ID}"
readonly FINAL="${ITERATION_ROOT}/${ITERATION_ID}"
readonly ATTEMPT_REPORT="${REPORT_ROOT}/.in_progress/${ITERATION_ID}"
readonly FINAL_REPORT="${REPORT_ROOT}/${ITERATION_ID}"

[[ ! -e "${ATTEMPT}" && ! -e "${FINAL}" ]] || {
  echo "PARSER_V3_2_ITERATION_PATH_EXISTS" >&2
  exit 1
}
[[ ! -e "${ATTEMPT_REPORT}" && ! -e "${FINAL_REPORT}" ]] || {
  echo "PARSER_V3_2_REPORT_PATH_EXISTS" >&2
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
echo "targeted_r02_access=PROHIBITED"
echo "pilot_selection_rerun=false"
echo "historical_artifacts=READ_ONLY"

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

targeted_cli() {
  python -m safe_geocoding_pipeline.phase03.targeted_review_cli "$@"
}

run_stage validate_references phase03_cli validate-production-references

run_stage confirm_v3_1_orientation_evidence targeted_cli analyze-v3-1-orientations \
  --input-manifest "${PHASE03_TARGETED_INPUT_MANIFEST}" \
  --protected-context "${PHASE03_TARGETED_CONTEXT}" \
  --controlled-r01-labels "${PHASE03_TARGETED_R01_LABELS}" \
  --output "${ATTEMPT_REPORT}/v3_1_orientation_evidence.json"

python - "${ATTEMPT_REPORT}/v3_1_orientation_evidence.json" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if (
    report.get("status") != "PARSER_V3_1_ORIENTATION_HYPOTHESIS_CONFIRMED"
    or report.get("hypothesis", {}).get("confirmed") is not True
    or report.get("locked_rows_read") != 0
):
    raise SystemExit("PARSER_V3_2_ORIENTATION_EVIDENCE_NOT_CONFIRMED")
PY

run_stage transform_v3_2_experimental phase03_cli development-transform \
  --input-development-payload "${PHASE03_DEVELOPMENT_PAYLOAD}" \
  --development-identities "${PHASE03_DEVELOPMENT_IDENTITIES}" \
  --output-directory "${ATTEMPT}/transformed" \
  --git-commit "${PHASE03_GIT_COMMIT}" \
  --parser-version conservative_address_parser_v3_2_experimental

run_stage compare_v2_1_v3_2 phase03_cli development-compare-parser-v2-1-v3-2 \
  --baseline-core "${PHASE03_BASELINE_CORE}" \
  --baseline-evidence "${PHASE03_BASELINE_EVIDENCE}" \
  --revised-core "${ATTEMPT}/transformed/core/development.parquet" \
  --revised-evidence "${ATTEMPT}/transformed/evidence/development.parquet" \
  --output "${ATTEMPT_REPORT}/parser_v2_1_v3_2_aggregate.json"

python - "${ATTEMPT_REPORT}/parser_v2_1_v3_2_aggregate.json" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
changes = report["changes"]
components = changes["component_selection_changes"]
native = changes["native_component_selection_changes"]
if (
    report["rows"] != 8000
    or report["identity_order_equal"] is not True
    or changes["rows_with_scientific_output_change"] != 4
    or changes["rows_with_new_conflicts"] != 0
    or changes["status_transitions"].get("UNPARSEABLE->PARTIAL") != 4
    or components["street"] != {"newly_selected": 4, "lost_selection": 0, "changed_selection": 0}
    or components["house_number"] != {"newly_selected": 4, "lost_selection": 0, "changed_selection": 0}
    or any(
        value != {"newly_selected": 0, "lost_selection": 0, "changed_selection": 0}
        for name, value in components.items()
        if name not in {"street", "house_number"}
    )
    or any(
        value != {"newly_selected": 0, "lost_selection": 0, "changed_selection": 0}
        for value in native.values()
    )
):
    raise SystemExit("PARSER_V3_2_UNEXPLAINED_SCIENTIFIC_CHANGE")
for rule_id in (
    "HOUSE_NUMBER_EMBEDDED_DESIGNATOR_EXPERIMENT_V5",
    "STREET_EMBEDDED_DESIGNATOR_EXPERIMENT_V5",
):
    if report["experimental"]["experimental_rule_evidence"][rule_id]["selected_count"] != 4:
        raise SystemExit("PARSER_V3_2_SELECTED_COUNT_MISMATCH")
PY

run_stage evaluate_v3_2_label_reuse targeted_cli evaluate-v3-2-label-reuse \
  --input-manifest "${PHASE03_TARGETED_INPUT_MANIFEST}" \
  --protected-context "${PHASE03_TARGETED_CONTEXT}" \
  --controlled-r01-labels "${PHASE03_TARGETED_R01_LABELS}" \
  --development-identities "${PHASE03_DEVELOPMENT_IDENTITIES}" \
  --baseline-core "${PHASE03_BASELINE_CORE}" \
  --baseline-evidence "${PHASE03_BASELINE_EVIDENCE}" \
  --v3-2-core "${ATTEMPT}/transformed/core/development.parquet" \
  --v3-2-evidence "${ATTEMPT}/transformed/evidence/development.parquet" \
  --comparison-report "${ATTEMPT_REPORT}/parser_v2_1_v3_2_aggregate.json" \
  --output-directory "${ATTEMPT_REPORT}/targeted_v3_2_evaluation"

sha256sum --check --strict "${INPUT_HASH_FILE}" >/dev/null || {
  echo "PARSER_V3_2_READ_ONLY_INPUT_CHANGED" >&2
  exit 1
}

python - "${ATTEMPT}/_SUCCESS.json" "${ATTEMPT_REPORT}" "${ITERATION_ID}" <<'PY'
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

success_path = Path(sys.argv[1])
report_root = Path(sys.argv[2])

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

reports = {
    path.relative_to(report_root).as_posix(): sha256_file(path)
    for path in sorted(report_root.rglob("*.json"))
}
payload = {
    "completed_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    "development_rows": 8000,
    "git_commit": os.environ["PHASE03_GIT_COMMIT"],
    "iteration_id": sys.argv[3],
    "locked_payload_rows_read": 0,
    "targeted_r02_rows_read": 0,
    "parser_version": "conservative_address_parser_v3_2_experimental",
    "pilot_selection_rerun": False,
    "promotion_decision": "NOT_EVALUATED",
    "reports": reports,
    "rule_registry_version": "phase03_rule_registry_v5_experimental",
    "rule_registry_sha256": "4e66e0be62c3d0aae3e9452babe7d16f312c7bb49c69af1a2a0e6839cc3bb1fd",
    "status": "DEVELOPMENT_PARSER_V3_2_EXPERIMENTAL_EVALUATION_COMPLETE",
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
echo "DEVELOPMENT_PARSER_V3_2_EXPERIMENTAL_EVALUATION_COMPLETE"
echo "final_iteration=${FINAL}"
echo "final_report=${FINAL_REPORT}"
echo "end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
