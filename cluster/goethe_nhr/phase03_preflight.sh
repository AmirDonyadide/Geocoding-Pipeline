#!/usr/bin/env bash
# Source this file from the Phase 3 SLURM job so PHASE03_NODE_TMP_ROOT is retained.
set -euo pipefail
umask 077

readonly PREFLIGHT_REPO_ROOT="/work/footprint/donyadidegan/safe_geocoding_pipeline"
readonly PREFLIGHT_PHASE02_RUN_ID="phase02_20260810T173851Z_1349152b"
readonly PREFLIGHT_PHASE02_RUN="${PREFLIGHT_REPO_ROOT}/staging/controlled/phase02_v1/runs/${PREFLIGHT_PHASE02_RUN_ID}"
readonly PREFLIGHT_PHASE02_MANIFEST="${PREFLIGHT_PHASE02_RUN}/dataset_manifest.json"
readonly PREFLIGHT_PHASE02_SUCCESS="${PREFLIGHT_PHASE02_RUN}/_SUCCESS.json"
readonly PREFLIGHT_PHASE01_ANOMALIES="${PREFLIGHT_REPO_ROOT}/reports/generated/phase01/phase01_20260810T151626Z_7df9bc8f/phase01_anomalies.csv.gz"
readonly PREFLIGHT_MINIMUM_FREE_BYTES=26843545600
readonly PREFLIGHT_EXPECTED_SAMPLING_SHA256="0fb7527db5b6a7eb1c7d7eb86d4a038abf4d605728bfe9cf761c74cd33c6d1c7"
readonly PREFLIGHT_EXPECTED_REGISTRY_SHA256="d1448859f8436dbe466cab81aee926ab6851b294f5ec664491840bac84627fd5"

preflight_fail() {
  echo "PHASE03_CLUSTER_PREFLIGHT_FAILED: $*" >&2
  return 1
}

[[ "${SAFE_EXECUTION_SITE:-}" == "goethe-nhr" ]] || preflight_fail "SAFE_EXECUTION_SITE must equal goethe-nhr"
[[ -n "${SLURM_JOB_ID:-}" ]] || preflight_fail "SLURM_JOB_ID is absent"
[[ -n "${PHASE03_GIT_COMMIT:-}" ]] || preflight_fail "PHASE03_GIT_COMMIT is absent"
[[ -d "${PREFLIGHT_REPO_ROOT}/.git" ]] || preflight_fail "repository is absent"
cd "${PREFLIGHT_REPO_ROOT}"
[[ "$(git rev-parse HEAD)" == "${PHASE03_GIT_COMMIT}" ]] || preflight_fail "Git commit mismatch"
[[ -z "$(git status --short)" ]] || preflight_fail "working tree is not clean"

python - <<'PY' || preflight_fail "runtime or execution-site validation failed"
import sys
import unicodedata

from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm

assert sys.version_info[:3] == (3, 14, 3), sys.version
assert unicodedata.unidata_version == "16.0.0", unicodedata.unidata_version
require_goethe_nhr_slurm("phase03.cluster-preflight")
PY

reference_result="$(safe-geocoding-phase03 validate-production-references)" || preflight_fail "production references failed"
registry_result="$(safe-geocoding-phase03 validate-rule-registry)" || preflight_fail "rule registry failed"
python - "${reference_result}" "${registry_result}" "${PREFLIGHT_EXPECTED_REGISTRY_SHA256}" <<'PY' || preflight_fail "reference/registry identity mismatch"
import json
import sys

references = json.loads(sys.argv[1])
registry = json.loads(sys.argv[2])
assert references["status"] == "PASS"
assert references["country_reference_version"] == "country_reference_v2_iso_normative_cldr_46_1_operational"
assert references["script_reference_version"] == "unicode_ucd_16_0_0_scripts_20240430"
assert registry["status"] == "PASS"
assert registry["registry_version"] == "phase03_rule_registry_v2"
assert registry["sha256"] == sys.argv[3]
PY

[[ -f "${PREFLIGHT_PHASE02_MANIFEST}" && -f "${PREFLIGHT_PHASE02_SUCCESS}" ]] || preflight_fail "Phase 2 manifest/success marker missing"
[[ -f "${PREFLIGHT_PHASE01_ANOMALIES}" ]] || preflight_fail "sanitized Phase 1 anomaly report missing"
mapfile -d '' PHASE02_SHARDS < <(find "${PREFLIGHT_PHASE02_RUN}/data" -maxdepth 1 -type f -name '*.parquet' -print0 | sort -z)
[[ "${#PHASE02_SHARDS[@]}" -eq 206 ]] || preflight_fail "Phase 2 shard count is not 206"

# This validates the manifest, all 206 exact output hashes, page-readable schemas,
# completion gate, and 20,600,000-row reconciliation without scanning row columns.
python - "${PREFLIGHT_PHASE02_MANIFEST}" "${PREFLIGHT_PHASE02_SUCCESS}" "${PHASE02_SHARDS[@]}" <<'PY' || preflight_fail "Phase 2 snapshot validation failed"
import hashlib
import json
import sys
from pathlib import Path

from safe_geocoding_pipeline.phase03.pilot_orchestration import validate_explicit_phase02_inputs

manifest_path = Path(sys.argv[1])
success = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
manifest, _ = validate_explicit_phase02_inputs(
    manifest_path, [Path(value) for value in sys.argv[3:]], production=True
)
assert manifest["reconciliation"]["total_rows"] == 20_600_000
assert len(manifest["files"]) == 206
manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
assert success == {
    **success,
    "dataset_manifest_sha256": manifest_hash,
    "files": 206,
    "phase02_completion_gate": "PASS",
    "rows": 20_600_000,
    "run_id": "phase02_20260810T173851Z_1349152b",
    "run_scope": "FULL_CONVERSION",
    "scope_gate": "PASS",
}
PY

choose_node_local_tmp() {
  local candidate filesystem free_bytes job_root
  local candidates=()
  [[ -n "${SLURM_TMPDIR:-}" ]] && candidates+=("${SLURM_TMPDIR}")
  [[ -n "${TMPDIR:-}" ]] && candidates+=("${TMPDIR}")
  candidates+=(/tmp)
  for candidate in "${candidates[@]}"; do
    [[ -d "${candidate}" && -w "${candidate}" ]] || continue
    case "$(cd "${candidate}" && pwd -P)" in
      /work|/work/*|/home|/home/*|/scratch|/scratch/*) continue ;;
    esac
    filesystem="$(df -PT "${candidate}" | awk 'NR==2 {print $2}')"
    case "${filesystem}" in
      nfs|nfs4|panfs|lustre|gpfs|cifs|smbfs|ceph|fuse.sshfs) continue ;;
    esac
    free_bytes="$(df -PB1 "${candidate}" | awk 'NR==2 {print $4}')"
    [[ "${free_bytes}" =~ ^[0-9]+$ ]] || continue
    (( free_bytes >= PREFLIGHT_MINIMUM_FREE_BYTES )) || continue
    job_root="${candidate%/}/safe_geocoding_phase03_${SLURM_JOB_ID}"
    mkdir -p "${job_root}"
    chmod 0700 "${job_root}"
    PHASE03_NODE_TMP_ROOT="${job_root}"
    export PHASE03_NODE_TMP_ROOT
    echo "node_tmp_filesystem=${filesystem}"
    echo "node_tmp_free_bytes=${free_bytes}"
    echo "PHASE03_NODE_TMP_ROOT=${PHASE03_NODE_TMP_ROOT}"
    return 0
  done
  echo "NO_SAFE_CLUSTER_TEMP_STORAGE: no writable node-local filesystem has at least ${PREFLIGHT_MINIMUM_FREE_BYTES} bytes" >&2
  return 1
}

choose_node_local_tmp || return 1

mkdir -p "${PREFLIGHT_REPO_ROOT}/derived/controlled" "${PREFLIGHT_REPO_ROOT}/reports/generated" "${PREFLIGHT_REPO_ROOT}/logs/slurm"
chmod 0700 "${PREFLIGHT_REPO_ROOT}/derived/controlled" "${PREFLIGHT_REPO_ROOT}/reports/generated" "${PREFLIGHT_REPO_ROOT}/logs/slurm"

plan_json="$(safe-geocoding-phase03 pilot-plan \
  --input-path "${PREFLIGHT_PHASE02_RUN}" \
  --output-path "${PREFLIGHT_REPO_ROOT}/derived/controlled/phase03_v1/pilots" \
  --git-commit "${PHASE03_GIT_COMMIT}")" || preflight_fail "pilot-plan failed"
python - "${plan_json}" "${PREFLIGHT_EXPECTED_SAMPLING_SHA256}" <<'PY' || preflight_fail "sampling contract mismatch"
import json
import sys

plan = json.loads(sys.argv[1])
assert plan["data_read"] is False
assert plan["contract_version"] == "phase03_sampling_contract_v1"
assert plan["contract_fingerprint"] == sys.argv[2]
assert plan["pilot_total_count"] == 12_000
assert plan["development_count"] == 8_000
assert plan["locked_evaluation_count"] == 4_000
assert plan["planned_sampling_passes"] == 2
PY

echo "PHASE03_CLUSTER_PREFLIGHT_PASS"
