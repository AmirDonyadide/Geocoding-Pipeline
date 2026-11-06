#!/usr/bin/env bash
#SBATCH --job-name=safe-stage12-public-path-replay
#SBATCH --partition=general1
#SBATCH --account=footprint
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=6G
#SBATCH --time=02:10:00
#SBATCH --no-requeue
set -euo pipefail
umask 077
ulimit -c 0
: "${SLURM_JOB_ID:?compute allocation required}"
: "${STAGE12_REPLAY_SHA:?exact reviewed pushed source}"
: "${STAGE12_REPLAY_CHECKOUT:?clean detached checkout}"
: "${STAGE12_REPLAY_INPUT:?canonical reviewed TEST_ONLY input}"
: "${STAGE12_REPLAY_INPUT_SHA256:?exact input hash}"
: "${STAGE12_REPLAY_OUTPUT:?new exclusive private output}"
readonly stage12_project=/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline
readonly stage12_python="${stage12_project}/runtimes/stage06/stage06_development_20260828T223804Z_f39047cc825d/venv/bin/python"
readonly stage12_started_ns="$("${stage12_python}" -B -c 'import time; print(time.monotonic_ns())')"
[[ "${SLURM_RESTART_COUNT:-0}" == 0 ]]
[[ "${STAGE12_REPLAY_SHA}" =~ ^[a-f0-9]{40}$ ]]
[[ "${STAGE12_REPLAY_INPUT_SHA256}" =~ ^[a-f0-9]{64}$ ]]
[[ "$(dirname -- "${STAGE12_REPLAY_CHECKOUT}")" == "${stage12_project}/integration_stage12" ]]
[[ "$(dirname -- "${STAGE12_REPLAY_INPUT}")" == "${stage12_project}/derived/controlled/stage12/client_diagnostics" ]]
[[ "$(dirname -- "${STAGE12_REPLAY_OUTPUT}")" == "${stage12_project}/derived/controlled/stage12/client_diagnostics" ]]
[[ "$(realpath -e -- "${STAGE12_REPLAY_CHECKOUT}")" == "${STAGE12_REPLAY_CHECKOUT}" ]]
[[ "$(git -C "${STAGE12_REPLAY_CHECKOUT}" rev-parse HEAD)" == "${STAGE12_REPLAY_SHA}" ]]
[[ -z "$(git -C "${STAGE12_REPLAY_CHECKOUT}" status --porcelain)" ]]
[[ -z "$(git -C "${STAGE12_REPLAY_CHECKOUT}" symbolic-ref -q HEAD || true)" ]]
[[ ! -e "${STAGE12_REPLAY_OUTPUT}" && -x "${stage12_python}" ]]
unset SAFE_PELIAS_API_KEY SAFE_PELIAS_API_KEY_FILE PYTHONPATH
export SAFE_EXECUTION_SITE=goethe-nhr PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONHASHSEED=0
export LANG=C.UTF-8 LC_ALL=C.UTF-8 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
PYTHONPATH="${STAGE12_REPLAY_CHECKOUT}/src" "${stage12_python}" -B -c \
  'from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm; require_goethe_nhr_slurm("stage12 denied real-public-adapter replay")'
[[ "$(sha256sum "${STAGE12_REPLAY_INPUT}" | cut -d' ' -f1)" == "${STAGE12_REPLAY_INPUT_SHA256}" ]]
readonly stage12_metadata="${STAGE12_REPLAY_OUTPUT}_allocation_metadata"
mkdir -m 0700 "${stage12_metadata}"
printf '{"started_mono_ns":%s,"internal_seconds":7200,"job_id":"%s"}\n' \
  "${stage12_started_ns}" "${SLURM_JOB_ID}" > "${stage12_metadata}/CLOCK.json"

# Fixed read-only metadata commands on this compute allocation. These are not
# available to the denied diagnostic Python process. Both format flags affect
# display; '-f files' does not restrict the query to inodes.
stage12_metadata_command() {
  local stage12_label="$1"
  shift
  local stage12_code
  set +e
  (ulimit -f 64; timeout --signal=TERM --kill-after=1s 15s "$@") \
    > "${stage12_metadata}/${stage12_label}.out" \
    2> "${stage12_metadata}/${stage12_label}.err"
  stage12_code=$?
  set -e
  local stage12_out_bytes stage12_err_bytes
  stage12_out_bytes="$(stat -c %s "${stage12_metadata}/${stage12_label}.out")"
  stage12_err_bytes="$(stat -c %s "${stage12_metadata}/${stage12_label}.err")"
  printf '{"exit_code":%s,"stdout_bytes":%s,"stderr_bytes":%s,"selected_file_limit_bytes":65536}\n' \
    "${stage12_code}" "${stage12_out_bytes}" "${stage12_err_bytes}" \
    > "${stage12_metadata}/${stage12_label}.status.json"
}
stage12_metadata_command quota_help pan_quota --help
stage12_metadata_command project_bytes pan_df -P -B1 "${stage12_project}"
stage12_metadata_command project_inodes pan_df -P -i "${stage12_project}"
stage12_metadata_command user_quota pan_quota -c B -f files -u donyadidegan /panfs/vdura1/footprint
stage12_metadata_command group_quota pan_quota -c B -f files -g footprint /panfs/vdura1/footprint
readonly stage12_outer_remaining="$("${stage12_python}" -B -c \
  'import sys,time; print(max(1,(int(sys.argv[1])+7210*10**9-time.monotonic_ns()+10**9-1)//10**9))' "${stage12_started_ns}")"
set +e
timeout --signal=TERM --kill-after=5s "${stage12_outer_remaining}s" "${stage12_python}" -B \
  "${STAGE12_REPLAY_CHECKOUT}/scripts/stage12_public_path_replay.py" \
  --input "${STAGE12_REPLAY_INPUT}" --input-sha256 "${STAGE12_REPLAY_INPUT_SHA256}" \
  --source "${STAGE12_REPLAY_CHECKOUT}" --source-sha "${STAGE12_REPLAY_SHA}" \
  --output "${STAGE12_REPLAY_OUTPUT}" --metadata "${stage12_metadata}" \
  --started-ns "${stage12_started_ns}"
stage12_result=$?
set -e
exit "${stage12_result}"
