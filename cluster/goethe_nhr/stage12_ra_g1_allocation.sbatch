#!/usr/bin/env bash
#SBATCH --job-name=safe-stage12-ra-g1
#SBATCH --partition=general1
#SBATCH --account=footprint
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=6G
#SBATCH --time=02:20:00
#SBATCH --no-requeue

# Reviewed successor: direct children, no dynamic pull/source rsync or provider.
set -euo pipefail
umask 077
ulimit -c 0
: "${STAGE12_RA_SOURCE:?}" "${STAGE12_RA_SHA:?}" "${STAGE12_RA_PYTHON:?}" "${STAGE12_RA_SELECTION:?}" "${STAGE12_RA_SELECTION_SHA:?}"
: "${STAGE12_RA_ROOT:?}" "${STAGE12_RA_INPUT:?}" "${STAGE12_RA_BINDING:?}" "${STAGE12_RA_OUTPUT:?}" "${STAGE12_RA_STATE:?}" "${STAGE12_RA_RETURN:?}" "${STAGE12_RA_HELPER_SHA:?}"
export SAFE_EXECUTION_SITE=goethe-nhr PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
unset SAFE_PELIAS_API_KEY SAFE_PELIAS_API_KEY_FILE PYTHONPATH
cd -- "$STAGE12_RA_SOURCE"
STAGE12_RA_UTILITIES=0
STAGE12_RA_PYTHONS=0
STAGE12_RA_CHILD=''
STAGE12_RA_STATUS=INCOMPLETE
ra_tick() {
    local uptime unused whole frac
    IFS=' ' read -r uptime unused < /proc/uptime
    [[ "$uptime" =~ ^[0-9]+\.[0-9]+$ ]]
    whole=${uptime%%.*}; frac=${uptime#*.}00
    STAGE12_RA_NOW=$((10#$whole * 1000000000 + 10#${frac:0:2} * 10000000))
}
ra_tick
export STAGE12_RA_EPOCH_NS=$STAGE12_RA_NOW
STAGE12_RA_END_NS=$((STAGE12_RA_EPOCH_NS + 8160000000000))
ra_check() { ra_tick; [[ "$((STAGE12_RA_NOW+10000000))" -lt "$STAGE12_RA_END_NS" ]]; }
ra_utility() { STAGE12_RA_UTILITIES=$((STAGE12_RA_UTILITIES+1)); [[ "$STAGE12_RA_UTILITIES" -le 256 ]]; ra_check; "$@"; }
ra_capture() {
    local variable=$1 captured status=0; shift
    STAGE12_RA_UTILITIES=$((STAGE12_RA_UTILITIES+1)); [[ "$STAGE12_RA_UTILITIES" -le 256 ]]; ra_check
    captured=$("$@") || status=$?
    printf -v "$variable" '%s' "$captured"
    return "$status"
}
ra_record() {
    local exit_code=$?; trap - EXIT; set +e
    if [[ -n "$STAGE12_RA_CHILD" ]]; then kill -TERM "$STAGE12_RA_CHILD" 2>/dev/null; wait "$STAGE12_RA_CHILD" 2>/dev/null; fi
    ra_tick
    if [[ "$((STAGE12_RA_NOW+10000000))" -ge "$STAGE12_RA_END_NS" && "$exit_code" == 0 ]]; then exit_code=124; fi
    if [[ -d "$STAGE12_RA_ROOT" && ! -e "$STAGE12_RA_STATE" ]]; then
        (set -o noclobber; printf '{"version":"stage12_ra_g1_supervisor_terminal_intent_v1","source_sha":"%s","selection_sha256":"%s","status":"%s","exit_code":%d,"python_invocations":%d,"utility_invocations":%d,"observed_mono_ns_lower":%d,"deadline_mono_ns":%d,"B_service_authority":false}\n' "$STAGE12_RA_SHA" "$STAGE12_RA_SELECTION_SHA" "$STAGE12_RA_STATUS" "$exit_code" "$STAGE12_RA_PYTHONS" "$STAGE12_RA_UTILITIES" "$STAGE12_RA_NOW" "$STAGE12_RA_END_NS" > "$STAGE12_RA_STATE") || exit_code=74
        ra_utility timeout --signal=TERM --kill-after=1s 5s sync -f "$STAGE12_RA_STATE" || exit_code=74
        ra_check || exit_code=124
    else exit_code=74; fi
    exit "$exit_code"
}
trap ra_record EXIT
# Direct-parent watchdog uses shell /proc clock. One child at a time; no sixth Python.
ra_pause() {
    if [[ -n "${STAGE12_RA_WAIT_FD:-}" ]]; then
        local unused status=0
        IFS= read -r -t 1 -u "$STAGE12_RA_WAIT_FD" unused || status=$?
        [[ "$status" == 0 || "$status" -gt 128 ]]
    else
        ra_utility sleep 1
    fi
}
ra_run() {
    local seconds=$1 role=$2 start end status=0 pid; shift 2
    ra_check; start=$STAGE12_RA_NOW; end=$((start+seconds*1000000000))
    [[ "$end" -le "$STAGE12_RA_END_NS" ]] || end=$STAGE12_RA_END_NS
    STAGE12_RA_PYTHONS=$((STAGE12_RA_PYTHONS+1)); [[ "$STAGE12_RA_PYTHONS" -le 5 ]]
    "$STAGE12_RA_PYTHON" -B "$@" & pid=$!; STAGE12_RA_CHILD=$pid
    while kill -0 "$pid" 2>/dev/null; do
        ra_tick
        if [[ "$((STAGE12_RA_NOW+10000000))" -ge "$end" || "$((STAGE12_RA_NOW+10000000))" -ge "$STAGE12_RA_END_NS" ]]; then
            kill -TERM "$pid" 2>/dev/null || true
            ra_utility sleep 1 || true
            kill -KILL "$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true
            STAGE12_RA_CHILD=''; return 124
        fi
        ra_pause
    done
    wait "$pid" || status=$?
    STAGE12_RA_CHILD=''; ra_tick
    local return_path=''
    case "$role" in
        COLLECTOR) return_path="$STAGE12_RA_ROOT/collector.wait.record" ;;
        BINDER) return_path="$STAGE12_RA_ROOT/binder.wait.record" ;;
        PHASE_RUNNER) return_path="$STAGE12_RA_RETURN" ;;
    esac
    if [[ -n "$return_path" && -d "$STAGE12_RA_ROOT" ]]; then
        [[ ! -e "$return_path" ]]
        (set -o noclobber; printf '{"version":"stage12_ra_g1_supervisor_wait_v1","source_sha":"%s","selection_sha256":"%s","supervisor_pid":%d,"pid":%d,"exit_code":%d,"wait_status":%d,"acquired_mono_ns":%d}\n' "$STAGE12_RA_SHA" "$STAGE12_RA_SELECTION_SHA" "$$" "$pid" "$status" "$((status*256))" "$STAGE12_RA_NOW" > "$return_path")
        ra_utility timeout --signal=TERM --kill-after=1s 5s sync -f "$return_path"
    fi
    [[ "$((STAGE12_RA_NOW+10000000))" -lt "$end" ]] || return 124
    ra_check
    return "$status"
}
ra_capture actual git rev-parse HEAD
[[ "$actual" == "$STAGE12_RA_SHA" ]]
ra_capture changed git status --porcelain
[[ -z "$changed" ]]
ra_capture actual sha256sum scripts/stage12_ra_g1_allocation.py
[[ "${actual%% *}" == "$STAGE12_RA_HELPER_SHA" ]]
# COLLECTOR executes ready() before metadata; no protected source/controller gate.
ra_run 120 COLLECTOR scripts/stage12_ra_g1_allocation.py collect --selection "$STAGE12_RA_SELECTION" --selection-sha256 "$STAGE12_RA_SELECTION_SHA"
STAGE12_RA_STATUS=BOOTSTRAP_COLLECTED_DIAGNOSTIC_NOT_RELEASED
# One charged private FIFO lets builtin timed reads pace orchestration without
# creating thousands of utilities or an unregistered concurrent sleep process.
ra_utility mkfifo --mode=600 "$STAGE12_RA_ROOT/supervisor_wait.fifo"
exec {STAGE12_RA_WAIT_FD}<>"$STAGE12_RA_ROOT/supervisor_wait.fifo"
ra_run 720 BINDER scripts/stage12_ra_g1_allocation.py bind --selection "$STAGE12_RA_SELECTION" --selection-sha256 "$STAGE12_RA_SELECTION_SHA"
ra_capture actual sha256sum "$STAGE12_RA_INPUT"
STAGE12_RA_INPUT_SHA=${actual%% *}
ra_capture actual sha256sum "$STAGE12_RA_BINDING/integration_review.binding.json"
STAGE12_RA_REVIEW_SHA=${actual%% *}
STAGE12_RA_STATUS=DIAGNOSTIC_RELEASED_NOT_COMPLETE
ra_run 7200 PHASE_RUNNER scripts/stage12_ra_g1_diagnostic.py --source "$STAGE12_RA_SOURCE" --source-sha "$STAGE12_RA_SHA" --input "$STAGE12_RA_INPUT" --input-sha256 "$STAGE12_RA_INPUT_SHA" --output "$STAGE12_RA_OUTPUT" --evidence-bundle "$STAGE12_RA_BINDING" --evidence-review-sha256 "$STAGE12_RA_REVIEW_SHA"
ra_run 120 TERMINAL_VERIFIER scripts/stage12_ra_g1_allocation.py verify --selection "$STAGE12_RA_SELECTION" --selection-sha256 "$STAGE12_RA_SELECTION_SHA"
STAGE12_RA_STATUS=COMPLETE_REPRESENTATIVE_NO_SERVICE
