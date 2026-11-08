#!/usr/bin/env bash
#SBATCH --job-name=safe-stage12-wf-ap2
#SBATCH --partition=general1
#SBATCH --account=footprint
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=6G
#SBATCH --time=02:20:00
#SBATCH --no-requeue

# One batch domain, three Python processes, no step/requeue/source transfer.
# The independent review is an original file delivered during the bounded
# review stage; its existence alone never releases B (the binder verifies it).
set -euo pipefail
umask 077
ulimit -c 0

stage12_tick() {
    local uptime unused whole fraction
    IFS=' ' read -r uptime unused < /proc/uptime || return 2
    [[ "$uptime" =~ ^[0-9]+\.[0-9]+$ ]] || return 2
    whole=${uptime%%.*}; fraction=${uptime#*.}00
    STAGE12_NOW=$((10#$whole * 100 + 10#${fraction:0:2}))
    [[ -z "${STAGE12_PREVIOUS:-}" || "$STAGE12_NOW" -ge "$STAGE12_PREVIOUS" ]] || return 2
    STAGE12_PREVIOUS=$STAGE12_NOW
    IFS= read -r STAGE12_BOOT_NOW < /proc/sys/kernel/random/boot_id || return 2
    [[ "$STAGE12_BOOT_NOW" == "$STAGE12_BOOT" ]]
}

stage12_apply_epoch() {
    [[ "${STAGE12_EPOCH_START:-}" =~ ^[0-9]+$ && "${STAGE12_EPOCH_BOOT:-}" == "$STAGE12_BOOT" ]] || return 2
    [[ "$STAGE12_EPOCH_START" -le "$STAGE12_NOW" ]] || return 2
    STAGE12_START=$STAGE12_EPOCH_START
    STAGE12_END=$((STAGE12_START + 816000))
    [[ "$((STAGE12_NOW + 1))" -lt "$STAGE12_END" ]]
}

stage12_check() {
    stage12_tick || return 2
    # Start was rounded down, completion up one centisecond. No late PASS.
    [[ "$((STAGE12_NOW + 1))" -lt "$STAGE12_END" ]]
}

stage12_utility() {
    STAGE12_UTILITIES=$((STAGE12_UTILITIES + 1))
    [[ "$STAGE12_UTILITIES" -le 256 ]] || return 2
    stage12_check || return 2
    "$@"
}

stage12_capture() {
    local variable=$1 value
    shift
    STAGE12_UTILITIES=$((STAGE12_UTILITIES + 1))
    [[ "$STAGE12_UTILITIES" -le 256 ]] || return 2
    stage12_check || return 2
    local status=0
    value=$("$@") || status=$?
    printf -v "$variable" '%s' "$value"
    return "$status"
}

stage12_run() {
    local seconds=$1 start status end
    shift
    stage12_check || return 2
    start=$STAGE12_NOW
    STAGE12_PYTHONS=$((STAGE12_PYTHONS + 1))
    [[ "$STAGE12_PYTHONS" -le 3 ]] || return 2
    set +e
    stage12_utility timeout --signal=TERM --kill-after=5s "${seconds}s" "$@"
    status=$?
    set -e
    stage12_check || return 2
    end=$STAGE12_NOW
    [[ "$((end + 1 - start))" -lt "$((seconds * 100))" ]] || return 124
    return "$status"
}

stage12_record() {
    local exit_code=$? elapsed final_start persistence_status=0
    trap - EXIT
    set +e
    stage12_tick || { if [[ "$exit_code" == 0 ]]; then exit_code=2; fi; }
    elapsed=$((STAGE12_NOW + 1 - STAGE12_START))
    final_start=$STAGE12_NOW
    # One exclusive bounded final file. This is supplementary disposition,
    # never a campaign seal or a substitute for B's real opener.
    if [[ -n "${STAGE12_AP2_OUTCOME:-}" && ! -e "$STAGE12_AP2_OUTCOME" ]]; then
        (set -o noclobber; printf '{"version":"stage12_wf_ap2_supervisor_outcome_v1","status":"%s","exit_code":%d,"python_invocations":%d,"utility_invocations":%d,"pre_persistence_elapsed_centiseconds_upper":%d,"record_stage":"PRE_PERSISTENCE_INTENT_NOT_TERMINAL_PROOF","boot_clock_resolution_ms":10,"B_released":%s}\n' \
            "$STAGE12_STATUS" "$exit_code" "$STAGE12_PYTHONS" "$STAGE12_UTILITIES" "$elapsed" "$STAGE12_B_RELEASED" > "$STAGE12_AP2_OUTCOME") || persistence_status=74
        if [[ "$persistence_status" == 0 ]]; then
            stage12_utility timeout --signal=TERM --kill-after=5s 120s sync -f "$STAGE12_AP2_OUTCOME" || persistence_status=74
        fi
    else
        persistence_status=74
    fi
    if [[ "$exit_code" == 0 && "$persistence_status" != 0 ]]; then exit_code=$persistence_status; fi
    stage12_tick || { if [[ "$exit_code" == 0 ]]; then exit_code=2; fi; }
    elapsed=$((STAGE12_NOW + 1 - STAGE12_START))
    if [[ "$exit_code" == 0 && ( "$elapsed" -ge 816000 || "$((STAGE12_NOW + 1 - final_start))" -ge 12000 ) ]]; then exit_code=124; fi
    printf 'AP2_SUPERVISOR_FINAL exit=%d elapsed_centiseconds_upper=%d\n' "$exit_code" "$elapsed"
    exit "$exit_code"
}

stage12_main() {
    : "${SLURM_JOB_ID:?compute allocation required}"
    : "${STAGE12_AP2_SOURCE:?pinned detached checkout}"
    : "${STAGE12_AP2_SOURCE_SHA:?exact reviewed commit}"
    : "${STAGE12_AP2_SELECTION:?canonical issued selection}"
    : "${STAGE12_AP2_SELECTION_SHA256:?exact selection hash}"
    : "${STAGE12_AP2_BOOTSTRAP:?fresh selected A root}"
    : "${STAGE12_AP2_OUTCOME:?fresh selected outcome file}"
    [[ "${SLURM_RESTART_COUNT:-0}" == 0 ]]
    [[ "$STAGE12_AP2_SOURCE_SHA" =~ ^[a-f0-9]{40}$ && "$STAGE12_AP2_SELECTION_SHA256" =~ ^[a-f0-9]{64}$ ]]
    local project=/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline
    local parent=$project/derived/controlled/stage12/client_diagnostics
    local python=$project/runtimes/stage06/stage06_development_20260828T223804Z_f39047cc825d/venv/bin/python
    [[ "${STAGE12_AP2_SOURCE%/*}" == "$project/integration_stage12" ]]
    [[ "${STAGE12_AP2_SELECTION%/*}" == "$parent" && "${STAGE12_AP2_BOOTSTRAP%/*}" == "$parent" && "${STAGE12_AP2_OUTCOME%/*}" == "$parent" ]]
    [[ "$STAGE12_AP2_SOURCE" =~ ^/[A-Za-z0-9_./-]+$ && "$STAGE12_AP2_SELECTION" =~ ^/[A-Za-z0-9_./-]+$ && "$STAGE12_AP2_BOOTSTRAP" =~ ^/[A-Za-z0-9_./-]+$ && "$STAGE12_AP2_OUTCOME" =~ ^/[A-Za-z0-9_./-]+$ ]]
    [[ "$STAGE12_AP2_SOURCE$STAGE12_AP2_SELECTION$STAGE12_AP2_BOOTSTRAP$STAGE12_AP2_OUTCOME" != *'/../'* ]]
    STAGE12_UTILITIES=2; STAGE12_PYTHONS=0; STAGE12_STATUS=INCOMPLETE; STAGE12_B_RELEASED=false
    IFS= read -r STAGE12_BOOT < /proc/sys/kernel/random/boot_id
    stage12_tick
    stage12_apply_epoch
    trap stage12_record EXIT
    unset GIT_DIR GIT_WORK_TREE GIT_CONFIG_COUNT GIT_CONFIG_PARAMETERS
    export GIT_OPTIONAL_LOCKS=0 GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
    local checked
    stage12_capture checked realpath -e -- "$STAGE12_AP2_SOURCE"
    [[ "$checked" == "$STAGE12_AP2_SOURCE" ]]
    stage12_capture checked git --no-optional-locks -c core.fsmonitor=false -c core.untrackedCache=false -C "$STAGE12_AP2_SOURCE" rev-parse HEAD
    [[ "$checked" == "$STAGE12_AP2_SOURCE_SHA" ]]
    stage12_capture checked git --no-optional-locks -c core.fsmonitor=false -c core.untrackedCache=false -C "$STAGE12_AP2_SOURCE" status --porcelain
    [[ -z "$checked" ]]
    stage12_capture checked git --no-optional-locks -c core.fsmonitor=false -c core.untrackedCache=false -C "$STAGE12_AP2_SOURCE" symbolic-ref -q HEAD || [[ $? == 1 ]]
    [[ -z "$checked" ]]
    [[ -x "$python" && ! -e "$STAGE12_AP2_BOOTSTRAP" && ! -e "$STAGE12_AP2_OUTCOME" ]]
    unset SAFE_PELIAS_API_KEY SAFE_PELIAS_API_KEY_FILE PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONUSERBASE PYTHONINSPECT
    export SAFE_EXECUTION_SITE=goethe-nhr PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHONUTF8=1 PYTHONHASHSEED=0
    export LANG=C.UTF-8 LC_ALL=C.UTF-8 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
    export PYTHONPATH="$STAGE12_AP2_SOURCE/src"
    stage12_run 120 "$python" -s -B "$STAGE12_AP2_SOURCE/scripts/stage12_wf_ap2_allocation.py" collect --selection "$STAGE12_AP2_SELECTION" --selection-sha256 "$STAGE12_AP2_SELECTION_SHA256"
    # The original manifest binds this file; binder revalidates every original.
    local sha source records bootstrap binding input evidence output review outcome possible extra
    {
        IFS= read -r sha; IFS= read -r source; IFS= read -r records
        IFS= read -r bootstrap; IFS= read -r binding; IFS= read -r input
        IFS= read -r evidence; IFS= read -r output; IFS= read -r review
        IFS= read -r outcome; IFS= read -r possible
        ! IFS= read -r extra
    } < "$STAGE12_AP2_BOOTSTRAP/supervisor.fields"
    [[ "$sha" == "$STAGE12_AP2_SOURCE_SHA" && "$source" == "$STAGE12_AP2_SOURCE" && "$bootstrap" == "$STAGE12_AP2_BOOTSTRAP" && "$outcome" == "$STAGE12_AP2_OUTCOME" ]]
    if [[ "$possible" == 0 ]]; then
        STAGE12_STATUS=BOOTSTRAP_COLLECTED_DIAGNOSTIC_NOT_RELEASED
        return 0
    fi
    [[ "$possible" == 1 ]]
    local review_start=$STAGE12_NOW polls=0
    while [[ ! -f "$review" ]]; do
        stage12_check
        if [[ "$((STAGE12_NOW + 1 - review_start))" -ge 60000 || "$polls" -ge 120 ]]; then
            STAGE12_STATUS=BOOTSTRAP_COLLECTED_DIAGNOSTIC_NOT_RELEASED
            return 0
        fi
        polls=$((polls + 1)); stage12_utility sleep 5
    done
    stage12_check
    [[ "$((STAGE12_NOW + 1 - review_start))" -lt 60000 ]]
    stage12_run 120 "$python" -s -B "$STAGE12_AP2_SOURCE/scripts/stage12_wf_ap2_allocation.py" bind --selection "$STAGE12_AP2_SELECTION" --selection-sha256 "$STAGE12_AP2_SELECTION_SHA256"
    local input_hash review_hash ignored hash_output
    stage12_capture hash_output sha256sum -- "$input"
    read -r input_hash ignored <<< "$hash_output"
    stage12_capture hash_output sha256sum -- "$evidence/integration_review.binding.json"
    read -r review_hash ignored <<< "$hash_output"
    [[ "$input_hash" =~ ^[a-f0-9]{64}$ && "$review_hash" =~ ^[a-f0-9]{64}$ ]]
    STAGE12_B_RELEASED=true
    stage12_run 7200 "$python" -s -B "$source/scripts/stage12_diverse_offline_diagnostic.py" --wf-ap2 --source "$source" --source-sha "$sha" --input "$input" --input-sha256 "$input_hash" --output "$output" --evidence-bundle "$evidence" --evidence-review-sha256 "$review_hash"
    stage12_check
    STAGE12_STATUS=COMPLETE_DIAGNOSTIC_PROCESS_PASS_PENDING_INDEPENDENT_OUTCOME_REVIEW
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    # The scheduler's 8400 seconds and this outer termination bound cannot
    # confer successful completion after the internal 8160-second deadline.
    if [[ "${1:-}" != --supervised ]]; then
        IFS= read -r STAGE12_BOOT < /proc/sys/kernel/random/boot_id
        stage12_tick
        export STAGE12_EPOCH_START=$STAGE12_NOW STAGE12_EPOCH_BOOT=$STAGE12_BOOT
        exec timeout --signal=TERM --kill-after=5s 8170s setpriv --no-new-privs bash "$0" --supervised
    fi
    stage12_main
fi
