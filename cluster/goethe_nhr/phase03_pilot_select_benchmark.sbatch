#!/usr/bin/env bash
#SBATCH --job-name=safe-p3-select-bench
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=1-00:00:00
#SBATCH --tmp=50000
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

# Experimental code must live in a fresh v4 isolated checkout. Production and
# earlier benchmark checkouts/evidence must not be modified by this benchmark.
readonly BENCHMARK_REPO_ROOT="${PHASE03_BENCHMARK_REPO_ROOT:-/work/footprint/donyadidegan/safe_geocoding_pipeline_benchmark_v4}"
readonly PRODUCTION_REPO_ROOT="/work/footprint/donyadidegan/safe_geocoding_pipeline"
readonly PHASE02_RUN="${PRODUCTION_REPO_ROOT}/staging/controlled/phase02_v1/runs/phase02_20260810T173851Z_1349152b"
readonly PHASE02_MANIFEST="${PHASE02_RUN}/dataset_manifest.json"
readonly PHASE01_ANOMALIES="${PRODUCTION_REPO_ROOT}/reports/generated/phase01/phase01_20260810T151626Z_7df9bc8f/phase01_anomalies.csv.gz"
readonly BENCHMARK_ROOT="${PRODUCTION_REPO_ROOT}/derived/controlled/phase03_v1/benchmarks"
readonly REPORT_ROOT="${PRODUCTION_REPO_ROOT}/reports/generated/phase03/benchmarks"
readonly EXPECTED_ROWS_PER_SHARD=100000

export SAFE_EXECUTION_SITE=goethe-nhr
: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${PHASE03_BENCHMARK_BASE_COMMIT:?set the exact local baseline commit}"
: "${PHASE03_BENCHMARK_SOURCE_SHA256:?set the exact benchmark source-tree SHA-256}"
: "${PHASE03_PRODUCTION_COUNTRY_PROFILE:?set the completed 20.6M-row production country profile}"
: "${GNU_TIME_BIN:?set GNU_TIME_BIN to the GNU time executable}"
export PHASE03_GIT_COMMIT="${PHASE03_BENCHMARK_BASE_COMMIT}"
[[ -f "${PHASE03_PRODUCTION_COUNTRY_PROFILE}" ]] || {
  echo "production country profile is missing" >&2
  exit 1
}
[[ -x "${GNU_TIME_BIN}" && "${GNU_TIME_BIN}" != "/usr/bin/time" ]] || {
  echo "GNU_TIME_BIN must be an explicit executable GNU time path" >&2
  exit 1
}
"${GNU_TIME_BIN}" --version 2>&1 | grep -Eqi 'GNU.*time|time.*GNU' || {
  echo "GNU_TIME_BIN is not GNU time" >&2
  exit 1
}

echo "requested_cpus=${SLURM_CPUS_PER_TASK}"
echo "requested_ram=64G"
echo "requested_time=1-00:00:00"
echo "input_shards=1,5,10"
echo "expected_rows=100000,500000,1000000"
echo "implementations=baseline-sqlite,optimized-sqlite,optimized-sqlite-mmap,bounded-parallel"
echo "workflow=performance_state,quota_feasible_corpus,final_equivalence"
echo "benchmark_repo_root=${BENCHMARK_REPO_ROOT}"
echo "failed_benchmark_1747375_evidence=PRESERVED"
echo "failed_benchmark_1747430_evidence=PRESERVED"
echo "failed_benchmark_1747527_evidence=PRESERVED"
echo "cancelled_production_job_1747122_evidence=PRESERVED"
echo "job_id=${SLURM_JOB_ID}"
echo "hostname=$(hostname)"
echo "start_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"

[[ -d "${BENCHMARK_REPO_ROOT}/.git" ]] || {
  echo "isolated benchmark checkout missing" >&2
  exit 1
}
[[ "$(git -C "${BENCHMARK_REPO_ROOT}" rev-parse HEAD)" == "${PHASE03_BENCHMARK_BASE_COMMIT}" ]] || {
  echo "benchmark baseline commit mismatch" >&2
  exit 1
}
observed_source_sha256="$({
  cd "${BENCHMARK_REPO_ROOT}"
  while IFS= read -r -d '' file; do
    printf '%s\0' "${file}"
    git hash-object "${file}"
  done < <(git ls-files -co --exclude-standard -z)
} | sha256sum | awk '{print $1}')"
[[ "${observed_source_sha256}" == "${PHASE03_BENCHMARK_SOURCE_SHA256}" ]] || {
  echo "benchmark source-tree fingerprint mismatch" >&2
  exit 1
}
echo "benchmark_baseline_commit=${PHASE03_BENCHMARK_BASE_COMMIT}"
echo "benchmark_source_sha256=${observed_source_sha256}"
echo "benchmark_checkout_validation=PASS"

source "${PRODUCTION_REPO_ROOT}/.venv-goethe-nhr/bin/activate"
export PYTHONPATH="${BENCHMARK_REPO_ROOT}/src"
python - <<'PY'
import platform
import unicodedata
import duckdb
import pyarrow

assert platform.python_version() == "3.14.3"
assert unicodedata.unidata_version == "16.0.0"
assert pyarrow.__version__ == "25.0.0"
assert duckdb.__version__ == "1.5.5"
print("runtime_validation=PASS")
PY

readonly NODE_ROOT="/local/${SLURM_JOB_ID}/safe_phase03_select_benchmark"
mkdir -p "${NODE_ROOT}"
chmod 0700 "${NODE_ROOT}"
free_bytes="$(df -Pk "${NODE_ROOT}" | awk 'NR==2 {print $4 * 1024}')"
[[ "${free_bytes}" -ge 26843545600 ]] || {
  echo "NO_SAFE_CLUSTER_TEMP_STORAGE available=${free_bytes}" >&2
  exit 1
}
echo "node_local_free_bytes=${free_bytes}"
echo "node_local_storage_validation=PASS"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
readonly RUN_ID="phase03_select_benchmark_${timestamp}_${SLURM_JOB_ID}"
readonly LOCAL_RUN="${NODE_ROOT}/${RUN_ID}"
readonly ATTEMPT_CONTROLLED="${BENCHMARK_ROOT}/.in_progress/${RUN_ID}"
readonly FINAL_CONTROLLED="${BENCHMARK_ROOT}/${RUN_ID}"
readonly ATTEMPT_REPORT="${REPORT_ROOT}/.in_progress/${RUN_ID}"
readonly FINAL_REPORT="${REPORT_ROOT}/${RUN_ID}"
mkdir -p "${LOCAL_RUN}" "${ATTEMPT_CONTROLLED}" "${ATTEMPT_REPORT}"
chmod 0700 "${LOCAL_RUN}" "${ATTEMPT_CONTROLLED}" "${ATTEMPT_REPORT}"
readonly MISMATCH_ROOT="${ATTEMPT_CONTROLLED}/mismatches"
mkdir -p "${MISMATCH_ROOT}"
chmod 0700 "${MISMATCH_ROOT}"
export PHASE03_BENCHMARK_MISMATCH_DIRECTORY="${MISMATCH_ROOT}"

run_timed() {
  local label="$1"
  shift
  echo "benchmark_stage_start=${label} utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  local status=0
  if "${GNU_TIME_BIN}" -v -o "${ATTEMPT_REPORT}/${label}.resources.txt" \
    "$@" >"${ATTEMPT_REPORT}/${label}.stdout.json"; then
    status=0
  else
    status=$?
  fi
  chmod 0600 "${ATTEMPT_REPORT}/${label}.resources.txt" \
    "${ATTEMPT_REPORT}/${label}.stdout.json"
  if [[ "${status}" -ne 0 ]]; then
    echo "benchmark_stage_fail=${label} status=${status} utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >&2
    return "${status}"
  fi
  echo "benchmark_stage_pass=${label} utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}

run_engine() {
  local case_name="$1"
  local label="$2"
  local engine="$3"
  local workers="$4"
  local mmap_mib="$5"
  local benchmark_mode="$6"
  shift 6
  local output="${LOCAL_RUN}/${case_name}/${label}"
  run_timed "${case_name//\//_}_${label}" \
    python -m safe_geocoding_pipeline.phase03.pilot_select_benchmark run \
      --engine "${engine}" \
      --run-label "${label}" \
      --phase02-manifest "${PHASE02_MANIFEST}" \
      --phase01-anomalies "${PHASE01_ANOMALIES}" \
      --profile "${PHASE03_PRODUCTION_COUNTRY_PROFILE}" \
      --benchmark-mode "${benchmark_mode}" \
      --output-directory "${output}" \
      --worker-count "${workers}" \
      --sqlite-cache-size-mib 8192 \
      --sqlite-mmap-size-mib "${mmap_mib}" \
      --sqlite-insertion-batch-size 10000 \
      "$@"
  # The all-row SQLite database is disposable benchmark state. Its measured
  # size is already in benchmark_result.json; exact unlink avoids exhausting
  # node-local space across the progressive benchmark matrix.
  python - "${output}/candidate_state.sqlite3" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
if path.name != "candidate_state.sqlite3":
    raise SystemExit("unexpected disposable benchmark state path")
if path.is_file():
    path.unlink()
PY
}

# PHASE A: arbitrary prefixes measure state construction. Subset infeasibility
# is explicit and acceptable; it is never final-selection equivalence PASS.
for shard_count in 1 5 10; do
  expected_rows="$((shard_count * EXPECTED_ROWS_PER_SHARD))"
  case_name="performance/shards_${shard_count}"
  echo "phase=A case=${case_name} shards=${shard_count} expected_rows=${expected_rows}"
  mkdir -p "${LOCAL_RUN}/${case_name}"
  run_engine "${case_name}" baseline baseline-sqlite 1 0 PERFORMANCE_STATE --shard-count "${shard_count}"
  run_engine "${case_name}" optimized optimized-sqlite 1 0 PERFORMANCE_STATE --shard-count "${shard_count}"
  run_engine "${case_name}" optimized_mmap optimized-sqlite 1 8192 PERFORMANCE_STATE --shard-count "${shard_count}"
  run_engine "${case_name}" bounded_1 bounded-parallel 1 0 PERFORMANCE_STATE --shard-count "${shard_count}"
  run_engine "${case_name}" bounded_4 bounded-parallel 4 0 PERFORMANCE_STATE --shard-count "${shard_count}"
  run_engine "${case_name}" bounded_16 bounded-parallel 16 0 PERFORMANCE_STATE --shard-count "${shard_count}"
  run_timed "performance_shards_${shard_count}_compare" \
    python -m safe_geocoding_pipeline.phase03.pilot_select_benchmark compare \
      --run "${LOCAL_RUN}/${case_name}/baseline" \
      --run "${LOCAL_RUN}/${case_name}/optimized" \
      --run "${LOCAL_RUN}/${case_name}/optimized_mmap" \
      --run "${LOCAL_RUN}/${case_name}/bounded_1" \
      --run "${LOCAL_RUN}/${case_name}/bounded_4" \
      --run "${LOCAL_RUN}/${case_name}/bounded_16" \
      --output "${LOCAL_RUN}/${case_name}/equivalence.json"
done

# PHASE B: choose a deterministic strict subset of whole production shards in
# an independent benchmark order. No identity set or payload is materialized.
readonly CORPUS_MANIFEST="${LOCAL_RUN}/corpus/quota_feasible_corpus.json"
echo "phase=B action=construct_quota_feasible_corpus"
run_timed "construct_quota_feasible_corpus" \
  python -m safe_geocoding_pipeline.phase03.pilot_select_benchmark construct-corpus \
    --phase02-manifest "${PHASE02_MANIFEST}" \
    --phase01-anomalies "${PHASE01_ANOMALIES}" \
    --profile "${PHASE03_PRODUCTION_COUNTRY_PROFILE}" \
    --output "${CORPUS_MANIFEST}" \
    --worker-count 16

# PHASE C: final byte-identical 8k/4k equivalence is required only on the
# explicitly validated quota-feasible real-data corpus.
readonly FINAL_CASE="final_equivalence/quota_feasible_corpus"
mkdir -p "${LOCAL_RUN}/${FINAL_CASE}"
echo "phase=C case=${FINAL_CASE} final_selection_required=true"
run_engine "${FINAL_CASE}" baseline baseline-sqlite 1 0 FINAL_EQUIVALENCE --corpus-manifest "${CORPUS_MANIFEST}"
run_engine "${FINAL_CASE}" optimized optimized-sqlite 1 0 FINAL_EQUIVALENCE --corpus-manifest "${CORPUS_MANIFEST}"
run_engine "${FINAL_CASE}" optimized_mmap optimized-sqlite 1 8192 FINAL_EQUIVALENCE --corpus-manifest "${CORPUS_MANIFEST}"
run_engine "${FINAL_CASE}" bounded_1 bounded-parallel 1 0 FINAL_EQUIVALENCE --corpus-manifest "${CORPUS_MANIFEST}"
run_engine "${FINAL_CASE}" bounded_4 bounded-parallel 4 0 FINAL_EQUIVALENCE --corpus-manifest "${CORPUS_MANIFEST}"
run_engine "${FINAL_CASE}" bounded_16 bounded-parallel 16 0 FINAL_EQUIVALENCE --corpus-manifest "${CORPUS_MANIFEST}"
run_timed "final_equivalence_compare" \
  python -m safe_geocoding_pipeline.phase03.pilot_select_benchmark compare \
    --run "${LOCAL_RUN}/${FINAL_CASE}/baseline" \
    --run "${LOCAL_RUN}/${FINAL_CASE}/optimized" \
    --run "${LOCAL_RUN}/${FINAL_CASE}/optimized_mmap" \
    --run "${LOCAL_RUN}/${FINAL_CASE}/bounded_1" \
    --run "${LOCAL_RUN}/${FINAL_CASE}/bounded_4" \
    --run "${LOCAL_RUN}/${FINAL_CASE}/bounded_16" \
    --output "${LOCAL_RUN}/${FINAL_CASE}/equivalence.json"

echo "phase=D action=persist_after_all_equivalence_gates"

# Persist protected identity artifacts and privacy-safe result JSON only after
# every equivalence comparison passes. No raw address values are produced.
cp -a "${LOCAL_RUN}/." "${ATTEMPT_CONTROLLED}/"
find "${ATTEMPT_CONTROLLED}" -type d -exec chmod 0700 {} +
find "${ATTEMPT_CONTROLLED}" -type f -exec chmod 0600 {} +
find "${LOCAL_RUN}" -name 'benchmark_result.json' -o -name 'equivalence.json' | while read -r result; do
  relative="${result#${LOCAL_RUN}/}"
  mkdir -p "${ATTEMPT_REPORT}/$(dirname "${relative}")"
  cp "${result}" "${ATTEMPT_REPORT}/${relative}"
  chmod 0600 "${ATTEMPT_REPORT}/${relative}"
done

python - "${ATTEMPT_REPORT}/benchmark_run.json" <<'PY'
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import socket
import sys

payload = {
    "benchmark_source_sha256": os.environ["PHASE03_BENCHMARK_SOURCE_SHA256"],
    "benchmark_version": "phase03_pilot_select_benchmark_v4",
    "completed_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    "git_commit": os.environ["PHASE03_BENCHMARK_BASE_COMMIT"],
    "hostname": socket.gethostname(),
    "cancelled_production_job_1747122_evidence": "PRESERVED",
    "slurm_job_id": os.environ["SLURM_JOB_ID"],
}
path = Path(sys.argv[1])
path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
path.chmod(0o600)
PY

mkdir -p "${BENCHMARK_ROOT}" "${REPORT_ROOT}"
mv "${ATTEMPT_REPORT}" "${FINAL_REPORT}"
mv "${ATTEMPT_CONTROLLED}" "${FINAL_CONTROLLED}"
echo "PILOT_SELECT_BENCHMARK_PASS"
echo "run_id=${RUN_ID}"
echo "controlled_output=${FINAL_CONTROLLED}"
echo "sanitized_report=${FINAL_REPORT}"
echo "end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
