#!/usr/bin/env bash
#SBATCH --job-name=safe-phase03-pilot
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=12:00:00
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

readonly REPO_ROOT="/work/footprint/donyadidegan/safe_geocoding_pipeline"
readonly PHASE02_RUN="${REPO_ROOT}/staging/controlled/phase02_v1/runs/phase02_20260810T173851Z_1349152b"
readonly PHASE02_MANIFEST="${PHASE02_RUN}/dataset_manifest.json"
readonly PHASE01_ANOMALIES="${REPO_ROOT}/reports/generated/phase01/phase01_20260810T151626Z_7df9bc8f/phase01_anomalies.csv.gz"
readonly PILOT_ROOT="${REPO_ROOT}/derived/controlled/phase03_v1/pilots"
readonly REPORT_ROOT="${REPO_ROOT}/reports/generated/phase03"

export SAFE_EXECUTION_SITE=goethe-nhr
: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${PHASE03_GIT_COMMIT:?submit with PHASE03_GIT_COMMIT set to the reviewed commit}"

cd "${REPO_ROOT}"
source "${REPO_ROOT}/.venv-goethe-nhr/bin/activate"

echo "job_id=${SLURM_JOB_ID}"
echo "hostname=$(hostname)"
echo "start_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "git_commit=${PHASE03_GIT_COMMIT}"
echo "execution_site=${SAFE_EXECUTION_SITE}"

# The sourced preflight performs no row-column scan. It validates the complete
# Phase 2 file/hash/schema snapshot and exports a safe node-local temp root.
source "${REPO_ROOT}/cluster/goethe_nhr/phase03_preflight.sh"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
commit_short="${PHASE03_GIT_COMMIT:0:8}"
readonly RUN_ID="phase03_pilot_goethe_${timestamp}_${SLURM_JOB_ID}_${commit_short}"
readonly ATTEMPT_RUN="${PILOT_ROOT}/.in_progress/${RUN_ID}"
readonly FINAL_RUN="${PILOT_ROOT}/${RUN_ID}"
readonly ATTEMPT_REPORT="${REPORT_ROOT}/.in_progress/${RUN_ID}"
readonly FINAL_REPORT="${REPORT_ROOT}/${RUN_ID}"
readonly STATE_PATH="${PHASE03_NODE_TMP_ROOT}/candidate_state.sqlite3"

[[ ! -e "${ATTEMPT_RUN}" && ! -e "${FINAL_RUN}" ]] || { echo "run path exists" >&2; exit 1; }
[[ ! -e "${ATTEMPT_REPORT}" && ! -e "${FINAL_REPORT}" ]] || { echo "report path exists" >&2; exit 1; }
mkdir -p "${ATTEMPT_RUN}" "${ATTEMPT_REPORT}"
chmod 0700 "${ATTEMPT_RUN}" "${ATTEMPT_REPORT}"

mapfile -d '' PHASE02_SHARDS < <(find "${PHASE02_RUN}/data" -maxdepth 1 -type f -name '*.parquet' -print0 | sort -z)
INPUT_ARGS=()
for shard in "${PHASE02_SHARDS[@]}"; do
  INPUT_ARGS+=(--input-path "${shard}")
done

run_stage() {
  local name="$1"
  shift
  local started ended
  started="$(date +%s)"
  echo "stage_start=${name} utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  /usr/bin/time -v -o "${ATTEMPT_REPORT}/${name}.resources.txt" \
    "$@" >"${ATTEMPT_REPORT}/${name}.json"
  chmod 0600 "${ATTEMPT_REPORT}/${name}.resources.txt" "${ATTEMPT_REPORT}/${name}.json"
  ended="$(date +%s)"
  printf '{"stage":"%s","wall_seconds":%s}\n' "${name}" "$((ended - started))" \
    >"${ATTEMPT_REPORT}/${name}.timing.json"
  chmod 0600 "${ATTEMPT_REPORT}/${name}.timing.json"
  echo "stage_pass=${name} wall_seconds=$((ended - started))"
}

run_stage pilot_plan safe-geocoding-phase03 pilot-plan \
  --input-path "${PHASE02_RUN}" --output-path "${FINAL_RUN}" \
  --git-commit "${PHASE03_GIT_COMMIT}"

# PASS 1: the command is contractually restricted to country_iso_code.
run_stage pilot_profile safe-geocoding-phase03 pilot-profile \
  --phase02-manifest "${PHASE02_MANIFEST}" "${INPUT_ARGS[@]}" \
  --output-path "${ATTEMPT_RUN}/country_profile.json"

# PASS 2: candidate SQLite state is new, node-local, and never copied from the
# paused Mac run. The command reads only the frozen 16-column sampling contract.
run_stage pilot_select safe-geocoding-phase03 pilot-select \
  --phase02-manifest "${PHASE02_MANIFEST}" "${INPUT_ARGS[@]}" \
  --country-profile "${ATTEMPT_RUN}/country_profile.json" \
  --phase01-anomalies "${PHASE01_ANOMALIES}" \
  --state-path "${STATE_PATH}" \
  --output-directory "${ATTEMPT_RUN}/selection" \
  --selection-timestamp "${timestamp}" \
  --git-commit "${PHASE03_GIT_COMMIT}"

run_stage pilot_validate safe-geocoding-phase03 pilot-validate \
  --phase02-manifest "${PHASE02_MANIFEST}" "${INPUT_ARGS[@]}" \
  --development-identities "${ATTEMPT_RUN}/selection/development.identities.bin" \
  --locked-identities "${ATTEMPT_RUN}/selection/locked_evaluation.identities.bin" \
  --pilot-seal "${ATTEMPT_RUN}/selection/pilot_seal.json"

# LOCKED FIREWALL: the locked identity set is used only as an exclusion set.
# No command below accepts or constructs a locked payload path.
run_stage development_materialize safe-geocoding-phase03 pilot-materialize-development \
  --phase02-manifest "${PHASE02_MANIFEST}" "${INPUT_ARGS[@]}" \
  --output-path "${ATTEMPT_RUN}/development/payload/development.parquet" \
  --development-identities "${ATTEMPT_RUN}/selection/development.identities.bin" \
  --locked-identities "${ATTEMPT_RUN}/selection/locked_evaluation.identities.bin"

run_stage development_transform safe-geocoding-phase03 development-transform \
  --input-development-payload "${ATTEMPT_RUN}/development/payload/development.parquet" \
  --development-identities "${ATTEMPT_RUN}/selection/development.identities.bin" \
  --output-directory "${ATTEMPT_RUN}/development/transformed" \
  --git-commit "${PHASE03_GIT_COMMIT}"

run_stage development_review safe-geocoding-phase03 development-review-sample \
  --state-path "${STATE_PATH}" \
  --development-payload "${ATTEMPT_RUN}/development/payload/development.parquet" \
  --development-core "${ATTEMPT_RUN}/development/transformed/core/development.parquet" \
  --development-evidence "${ATTEMPT_RUN}/development/transformed/evidence/development.parquet" \
  --development-identities "${ATTEMPT_RUN}/selection/development.identities.bin" \
  --output-directory "${ATTEMPT_RUN}/development/review"

run_stage development_final_validation python -m safe_geocoding_pipeline.phase03.cluster_reporting \
  --run-id "${RUN_ID}" --git-commit "${PHASE03_GIT_COMMIT}" \
  --development-identities "${ATTEMPT_RUN}/selection/development.identities.bin" \
  --locked-identities "${ATTEMPT_RUN}/selection/locked_evaluation.identities.bin" \
  --core "${ATTEMPT_RUN}/development/transformed/core/development.parquet" \
  --evidence "${ATTEMPT_RUN}/development/transformed/evidence/development.parquet" \
  --review-context "${ATTEMPT_RUN}/development/review/protected_review_context.parquet" \
  --portable-labels "${ATTEMPT_RUN}/development/review/portable_review_labels.parquet" \
  --transform-result "${ATTEMPT_REPORT}/development_transform.json" \
  --output "${ATTEMPT_REPORT}/DEVELOPMENT_PILOT_PASS.json"

# Persist a privacy-safe execution binding. It contains no identities or row data.
python - "${ATTEMPT_RUN}/cluster_run_metadata.json" "${RUN_ID}" "${PHASE02_MANIFEST}" \
  "${ATTEMPT_RUN}/selection/pilot_seal.json" <<'PY'
import hashlib
import json
import os
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path

path = Path(sys.argv[1])
manifest_path = Path(sys.argv[3])
seal_path = Path(sys.argv[4])
seal = json.loads(seal_path.read_text(encoding="utf-8"))
payload = {
    "git_commit": os.environ["PHASE03_GIT_COMMIT"],
    "hostname": socket.gethostname(),
    "recorded_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    "phase02_run_id": "phase02_20260810T173851Z_1349152b",
    "phase02_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    "run_id": sys.argv[2],
    "sampling_contract": "phase03_sampling_contract_v1",
    "sampling_contract_fingerprint": seal["sampling_contract_fingerprint"],
    "rule_registry_fingerprint": seal["rule_registry_fingerprint"],
    "reference_configuration_fingerprint": seal["reference_configuration_fingerprint"],
    "slurm_job_id": os.environ["SLURM_JOB_ID"],
}
path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
path.chmod(0o600)
PY

# The success marker contains no identities and is written last inside the
# hidden attempt. Reports are promoted first; the controlled run is promoted
# last, making success visible atomically.
python - "${ATTEMPT_RUN}/_SUCCESS.json" "${RUN_ID}" \
  "${ATTEMPT_REPORT}/DEVELOPMENT_PILOT_PASS.json" <<'PY'
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

path = Path(sys.argv[1])
report = Path(sys.argv[3])
payload = {
    "completed_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    "development_count": 8000,
    "double_review_count": 200,
    "gate": "DEVELOPMENT_PILOT_PASS",
    "git_commit": os.environ["PHASE03_GIT_COMMIT"],
    "locked_evaluation_count": 4000,
    "locked_payload_rows_read": 0,
    "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
    "review_count": 800,
    "run_id": sys.argv[2],
}
path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
path.chmod(0o600)
PY

mkdir -p "${PILOT_ROOT}" "${REPORT_ROOT}"
mv "${ATTEMPT_REPORT}" "${FINAL_REPORT}"
mv "${ATTEMPT_RUN}" "${FINAL_RUN}"
echo "DEVELOPMENT_PILOT_PASS"
echo "run_id=${RUN_ID}"
echo "final_run=${FINAL_RUN}"
echo "final_report=${FINAL_REPORT}"
echo "end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
