#!/usr/bin/env bash
#SBATCH --job-name=safe-stage12-ra-g1-public
#SBATCH --partition=general1
#SBATCH --account=footprint
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=6G
#SBATCH --time=02:20:00
#SBATCH --no-requeue
#SBATCH --output=/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage12/public_probe/ra_g1_scheduler_logs/%j.out

# One persistent PUBLIC worker and one guarded verifier; unused roles stay charged.
set -euo pipefail
umask 077
ulimit -c 0
: "${SLURM_JOB_ID:?}" "${STAGE12_PUBLIC_SOURCE:?}" "${STAGE12_PUBLIC_SHA:?}" "${STAGE12_PUBLIC_PYTHON:?}"
: "${STAGE12_PUBLIC_SELECTION:?}" "${STAGE12_PUBLIC_SELECTION_SHA:?}" "${STAGE12_PUBLIC_RESOURCE_SELECTION:?}"
: "${STAGE12_PUBLIC_ROOT:?}" "${STAGE12_PUBLIC_RETURN:?}" "${STAGE12_PUBLIC_STATE:?}" "${STAGE12_PUBLIC_HELPER_SHA:?}"
: "${STAGE12_PUBLIC_KEY_FILE:?}"
export SAFE_EXECUTION_SITE=goethe-nhr PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 GIT_OPTIONAL_LOCKS=0
unset SAFE_PELIAS_API_KEY PYTHONPATH
export SAFE_PELIAS_API_KEY_FILE="$STAGE12_PUBLIC_KEY_FILE"
cd -- "$STAGE12_PUBLIC_SOURCE"
PUBLIC_UTILITIES=0
PUBLIC_PYTHONS=0
PUBLIC_CHILD=''
PUBLIC_STATUS=INCOMPLETE
public_tick() {
    local uptime unused whole frac
    IFS=' ' read -r uptime unused < /proc/uptime
    [[ "$uptime" =~ ^[0-9]+\.[0-9]+$ ]]
    whole=${uptime%%.*}; frac=${uptime#*.}00
    PUBLIC_NOW=$((10#$whole*1000000000+10#${frac:0:2}*10000000))
}
public_tick
export STAGE12_RA_EPOCH_NS=$PUBLIC_NOW
PUBLIC_END=$((STAGE12_RA_EPOCH_NS+8160000000000))
public_check() { public_tick; [[ "$((PUBLIC_NOW+20000000))" -lt "$PUBLIC_END" ]]; }
public_utility() {
    PUBLIC_UTILITIES=$((PUBLIC_UTILITIES+1)); [[ "$PUBLIC_UTILITIES" -le 256 ]]
    public_check; "$@"
}
public_capture() {
    local name=$1 value status=0; shift
    PUBLIC_UTILITIES=$((PUBLIC_UTILITIES+1)); [[ "$PUBLIC_UTILITIES" -le 256 ]]
    public_check; value=$("$@") || status=$?; printf -v "$name" '%s' "$value"; return "$status"
}
public_trap() {
    local status=$?; trap - EXIT; set +e
    if [[ -n "$PUBLIC_CHILD" ]]; then kill -TERM "$PUBLIC_CHILD" 2>/dev/null; wait "$PUBLIC_CHILD" 2>/dev/null; fi
    public_check || status=124
    if [[ -d "$STAGE12_PUBLIC_ROOT" && ! -e "$STAGE12_PUBLIC_STATE" ]]; then
        (set -o noclobber; printf '{"version":"stage12_ra_g1_public_supervisor_intent_v1","source_sha":"%s","selection_sha256":"%s","status":"%s","exit_code":%d,"python_invocations":%d,"utility_invocations":%d,"observed_mono_ns_lower":%d,"deadline_mono_ns":%d,"post_prefix_contract":"OWN_EXCLUSIVE_WRITE_ONE_BOUNDED_SYNC_NO_RECURSIVE_QUALIFICATION"}\n' "$STAGE12_PUBLIC_SHA" "$STAGE12_PUBLIC_SELECTION_SHA" "$PUBLIC_STATUS" "$status" "$PUBLIC_PYTHONS" "$PUBLIC_UTILITIES" "$PUBLIC_NOW" "$PUBLIC_END" > "$STAGE12_PUBLIC_STATE") || status=74
        public_utility timeout --signal=TERM --kill-after=1s 5s sync -f "$STAGE12_PUBLIC_STATE" || status=74
        public_check || status=124
    else status=74; fi
    exit "$status"
}
trap public_trap EXIT
public_pause() {
    local end=$1 remaining ms delay unused status=0
    if [[ -z "${PUBLIC_WAIT_FD:-}" && -p "$STAGE12_PUBLIC_ROOT/supervisor_wait.fifo" ]]; then
        exec {PUBLIC_WAIT_FD}<>"$STAGE12_PUBLIC_ROOT/supervisor_wait.fifo"
    fi
    public_tick; remaining=$((end-PUBLIC_NOW-20000000)); [[ "$remaining" -gt 0 ]]
    if [[ -n "${PUBLIC_WAIT_FD:-}" ]]; then
        ms=$((remaining/1000000)); [[ "$ms" -le 1000 ]] || ms=1000
        printf -v delay '%d.%03d' "$((ms/1000))" "$((ms%1000))"
        IFS= read -r -t "$delay" -u "$PUBLIC_WAIT_FD" unused || status=$?
        [[ "$status" == 0 || "$status" -gt 128 ]]
    else public_utility sleep 0.05; fi
}
public_run() {
    local seconds=$1 role=$2 pid end status=0; shift 2
    public_check; end=$((PUBLIC_NOW+seconds*1000000000)); [[ "$end" -le "$PUBLIC_END" ]] || end=$PUBLIC_END
    PUBLIC_PYTHONS=$((PUBLIC_PYTHONS+1)); [[ "$PUBLIC_PYTHONS" -le 5 ]]
    "$STAGE12_PUBLIC_PYTHON" -B "$@" & pid=$!; PUBLIC_CHILD=$pid
    while kill -0 "$pid" 2>/dev/null; do
        public_check
        if [[ "$((PUBLIC_NOW+20000000))" -ge "$end" ]]; then
            kill -TERM "$pid" 2>/dev/null || true
            public_utility sleep 1 || true
            kill -KILL "$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true
            PUBLIC_CHILD=''; return 124
        fi
        public_pause "$end"
    done
    wait "$pid" || status=$?
    PUBLIC_CHILD=''; public_tick
    if [[ "$role" == PHASE_RUNNER && -d "$STAGE12_PUBLIC_ROOT" ]]; then
        local raw_status=null
        [[ "$status" != 0 ]] || raw_status=0
        [[ ! -e "$STAGE12_PUBLIC_RETURN" ]]
        (set -o noclobber; printf '{"exit_code":%d,"observed_mono_ns_lower":%d,"pid":%d,"selection_sha256":"%s","source_sha":"%s","supervisor_pid":%d,"version":"stage12_ra_g1_public_supervisor_wait_v1","wait_status":%s}\n' "$status" "$PUBLIC_NOW" "$pid" "$STAGE12_PUBLIC_SELECTION_SHA" "$STAGE12_PUBLIC_SHA" "$$" "$raw_status" > "$STAGE12_PUBLIC_RETURN")
        public_utility timeout --signal=TERM --kill-after=1s 5s sync -f "$STAGE12_PUBLIC_RETURN"
    fi
    public_check; [[ "$((PUBLIC_NOW+20000000))" -lt "$end" ]] || return 124
    return "$status"
}
public_utility chmod 600 "/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage12/public_probe/ra_g1_scheduler_logs/$SLURM_JOB_ID.out"
public_capture actual git rev-parse HEAD
[[ "$actual" == "$STAGE12_PUBLIC_SHA" ]]
public_capture changed git status --porcelain
[[ -z "$changed" ]]
public_capture actual sha256sum scripts/stage12_ra_g1_public_workflow.py
[[ "${actual%% *}" == "$STAGE12_PUBLIC_HELPER_SHA" ]]
public_run 8040 PHASE_RUNNER scripts/stage12_ra_g1_public_workflow.py worker --selection "$STAGE12_PUBLIC_SELECTION" --selection-sha256 "$STAGE12_PUBLIC_SELECTION_SHA" --resource-selection "$STAGE12_PUBLIC_RESOURCE_SELECTION"
PUBLIC_STATUS=PUBLIC_WORKER_RETURNED_PENDING_TERMINAL_VERIFICATION
public_run 120 TERMINAL_VERIFIER scripts/stage12_ra_g1_public_workflow.py verify --selection "$STAGE12_PUBLIC_SELECTION" --selection-sha256 "$STAGE12_PUBLIC_SELECTION_SHA" --resource-selection "$STAGE12_PUBLIC_RESOURCE_SELECTION"
PUBLIC_STATUS=COMPLETE_PUBLIC_SELECTED_SCOPE
