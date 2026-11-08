#!/usr/bin/env bash
#SBATCH --job-name=safe-stage12-bootstrap-a2
#SBATCH --partition=general1
#SBATCH --account=footprint
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=6G
#SBATCH --time=02:20:00
#SBATCH --no-requeue

set -euo pipefail
umask 077
ulimit -c 0
# Two scheduler logs <=4MiB each, leaving the rest of16MiB for <=6 bounded
# supplementary log slots. Exceeding this fails; it never qualifies a prefix.
ulimit -f 4096

if [[ "${BASH_SOURCE[0]}" == "$0" && "${1:-}" != --supervised ]]; then
    IFS=' ' read -r stage12_uptime stage12_unused < /proc/uptime
    [[ "$stage12_uptime" =~ ^[0-9]+\.[0-9]+$ ]]
    stage12_whole=${stage12_uptime%%.*}; stage12_fraction=${stage12_uptime#*.}00
    export STAGE12_EPOCH_START=$((10#$stage12_whole * 100 + 10#${stage12_fraction:0:2}))
    IFS= read -r STAGE12_EPOCH_BOOT < /proc/sys/kernel/random/boot_id
    export STAGE12_EPOCH_BOOT
    exec timeout --signal=TERM --kill-after=5s 8170s setpriv --no-new-privs bash "$0" --supervised
fi

# Definitions only: the strict script's main block does not run when sourced.
source "${BASH_SOURCE[0]%/*}/stage12_wf_ap2_allocation.sbatch"

stage12_check() {
    stage12_tick || return 2
    [[ "$((STAGE12_NOW + 1))" -lt "$STAGE12_END" ]] || return 2
    [[ -z "${STAGE12_A2_STAGE_END_CS:-}" || "$((STAGE12_NOW + 1))" -lt "$STAGE12_A2_STAGE_END_CS" ]]
}

stage12_a2_run() {
    local cap=$1 remaining duration status
    shift
    stage12_check
    remaining=$((STAGE12_A2_STAGE_END_CS - STAGE12_NOW - 1))
    [[ "$remaining" -le "$((STAGE12_END - STAGE12_NOW - 1))" ]] || remaining=$((STAGE12_END - STAGE12_NOW - 1))
    [[ "$remaining" -le "$((cap * 100))" ]] || remaining=$((cap * 100))
    [[ "$remaining" -gt 0 ]]
    printf -v duration '%d.%02d' "$((remaining / 100))" "$((remaining % 100))"
    STAGE12_PYTHONS=$((STAGE12_PYTHONS + 1))
    [[ "$STAGE12_PYTHONS" -le 3 ]]
    set +e
    stage12_utility timeout --signal=TERM --kill-after=1s "${duration}s" "$@"
    status=$?
    set -e
    stage12_check
    return "$status"
}

stage12_a2_logwrite() {
    local path=$1 json=$2
    [[ "$path" =~ ^/[A-Za-z0-9_./-]+$ && "$path" != *'/../'* && "${#json}" -le 4096 ]]
    # timeout+bash+sync are all counted; one exclusive log slot, no overwrite.
    STAGE12_UTILITIES=$((STAGE12_UTILITIES + 2))
    stage12_utility timeout --signal=TERM --kill-after=1s 5s bash -c \
        'set -euo pipefail; umask 077; set -o noclobber; printf "%s\n" "$2" > "$1"; sync -f "$1"' \
        a2-log "$path" "$json"
    stage12_check
}

stage12_a2_record() {
    local initial=$? saved_status=$STAGE12_STATUS persistence=0 elapsed
    trap - EXIT
    set +e
    # Supplementary intent only. This never repairs or seals A after failure.
    stage12_tick || { [[ "$initial" != 0 ]] || initial=2; }
    elapsed=$((STAGE12_NOW + 1 - STAGE12_START))
    [[ "$initial" == 0 ]] || saved_status=INCOMPLETE
    stage12_a2_logwrite "$STAGE12_AP2_OUTCOME" \
        "{\"B\":\"DISABLED\",\"exit_code\":$initial,\"policy\":\"A-BE1\",\"pre_persistence_elapsed_centiseconds\":$elapsed,\"record_stage\":\"PRE_PERSISTENCE_INTENT_NOT_TERMINAL_PROOF\",\"status\":\"$saved_status\",\"version\":\"stage12_a2_supervisor_outcome_v1\"}" || persistence=$?
    if [[ "$initial" == 0 && "$persistence" != 0 ]]; then initial=74; fi
    stage12_check || { [[ "$initial" != 0 ]] || initial=124; }
    elapsed=$((STAGE12_NOW + 1 - STAGE12_START))
    printf 'A2_SUPERVISOR_TERMINAL exit=%d elapsed_centiseconds_upper=%d B=DISABLED\n' "$initial" "$elapsed"
    exit "$initial"
}

stage12_a2_main() {
    : "${SLURM_JOB_ID:?compute allocation required}"
    : "${STAGE12_AP2_SOURCE:?reviewed detached source}"
    : "${STAGE12_AP2_SOURCE_SHA:?exact SHA}"
    : "${STAGE12_AP2_SELECTION:?canonical A2 selection}"
    : "${STAGE12_AP2_SELECTION_SHA256:?selection SHA}"
    : "${STAGE12_AP2_BOOTSTRAP:?exclusive A root}"
    : "${STAGE12_AP2_OUTCOME:?exclusive log}"
    : "${STAGE12_A2_RECORDS:?private original records}"
    : "${STAGE12_A2_FINAL:?exclusive final root}"
    [[ "$SLURM_JOB_ID" =~ ^[0-9]+$ && "${SLURM_RESTART_COUNT:-0}" == 0 ]]
    [[ "$STAGE12_AP2_SOURCE_SHA" =~ ^[a-f0-9]{40}$ && "$STAGE12_AP2_SELECTION_SHA256" =~ ^[a-f0-9]{64}$ ]]
    local project=/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline
    local parent=$project/derived/controlled/stage12/client_diagnostics
    local python=$project/runtimes/stage06/stage06_development_20260828T223804Z_f39047cc825d/venv/bin/python
    [[ "${STAGE12_AP2_SOURCE%/*}" == "$project/integration_stage12" && "$STAGE12_AP2_SOURCE" =~ ^/[A-Za-z0-9_./-]+$ && "$STAGE12_AP2_SOURCE" != *'/../'* ]]
    local path
    for path in "$STAGE12_AP2_SELECTION" "$STAGE12_AP2_BOOTSTRAP" "$STAGE12_AP2_OUTCOME" "$STAGE12_A2_RECORDS" "$STAGE12_A2_FINAL"; do
        [[ "${path%/*}" == "$parent" && "$path" =~ ^/[A-Za-z0-9_./-]+$ && "$path" != *'/../'* ]]
    done
    STAGE12_UTILITIES=2; STAGE12_PYTHONS=0; STAGE12_STATUS=INCOMPLETE
    IFS= read -r STAGE12_BOOT < /proc/sys/kernel/random/boot_id
    stage12_tick; stage12_apply_epoch
    export STAGE12_A2_CAPTURE_START_CS=$STAGE12_START
    export STAGE12_A2_STAGE_END_CS=$((STAGE12_START + 12000))
    trap stage12_a2_record EXIT
    unset GIT_DIR GIT_WORK_TREE GIT_CONFIG_COUNT GIT_CONFIG_PARAMETERS
    export GIT_OPTIONAL_LOCKS=0 GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
    local checked
    stage12_capture checked realpath -e -- "$STAGE12_AP2_SOURCE"
    [[ "$checked" == "$STAGE12_AP2_SOURCE" ]]
    stage12_capture checked git --no-optional-locks -c core.fsmonitor=false -c core.untrackedCache=false -C "$STAGE12_AP2_SOURCE" rev-parse HEAD
    [[ "$checked" == "$STAGE12_AP2_SOURCE_SHA" ]]
    stage12_capture checked git --no-optional-locks -c core.fsmonitor=false -c core.untrackedCache=false -C "$STAGE12_AP2_SOURCE" status --porcelain
    [[ -z "$checked" ]]
    stage12_capture checked git -C "$STAGE12_AP2_SOURCE" symbolic-ref -q HEAD || [[ $? == 1 ]]
    [[ -z "$checked" && -x "$python" && ! -e "$STAGE12_AP2_BOOTSTRAP" && ! -e "$STAGE12_A2_FINAL" && ! -e "$STAGE12_AP2_OUTCOME" ]]
    unset SAFE_PELIAS_API_KEY SAFE_PELIAS_API_KEY_FILE PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONUSERBASE PYTHONINSPECT
    export SAFE_EXECUTION_SITE=goethe-nhr PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHONUTF8=1 PYTHONHASHSEED=0
    export LANG=C.UTF-8 LC_ALL=C.UTF-8 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
    export PYTHONPATH="$STAGE12_AP2_SOURCE/src"
    # Bounded raw observations; no quota query and no entitlement assertion.
    local storage_observations
    STAGE12_UTILITIES=$((STAGE12_UTILITIES + 4))
    stage12_capture storage_observations timeout 15s bash -c \
        'set -euo pipefail; findmnt -n -T "$1" -o FSTYPE,TARGET,FSROOT; stat -f -c "type=%T fundamental=%S blocks=%b free=%f available=%a inodes=%c free_inodes=%d" "$1"; pan_df -P -B1 "$1"' \
        a2-storage "$parent"
    stage12_a2_logwrite "$STAGE12_A2_RECORDS/storage_launch.txt" "$storage_observations"
    stage12_a2_run 120 "$python" -s -B "$STAGE12_AP2_SOURCE/scripts/stage12_wf_ap2_bootstrap_a2.py" collect --selection "$STAGE12_AP2_SELECTION" --selection-sha256 "$STAGE12_AP2_SELECTION_SHA256"
    local hash_line manifest_hash ignored acknowledged
    stage12_capture hash_line sha256sum -- "$STAGE12_AP2_BOOTSTRAP/manifest.json"
    read -r manifest_hash ignored <<< "$hash_line"
    [[ "$manifest_hash" =~ ^[a-f0-9]{64}$ ]]
    stage12_check; acknowledged=$((STAGE12_NOW + 1))
    stage12_a2_logwrite "$STAGE12_A2_RECORDS/collector_ack.json" \
        "{\"B\":\"DISABLED\",\"capture_started_centiseconds\":$STAGE12_A2_CAPTURE_START_CS,\"collector_exit\":0,\"completed_centiseconds\":$acknowledged,\"epoch_centiseconds\":$STAGE12_START,\"job_id\":\"$SLURM_JOB_ID\",\"manifest_sha256\":\"$manifest_hash\",\"selection_sha256\":\"$STAGE12_AP2_SELECTION_SHA256\",\"source_sha\":\"$STAGE12_AP2_SOURCE_SHA\",\"version\":\"stage12_a2_collector_ack_v1\"}"
    export STAGE12_A2_STAGE_END_CS=$((acknowledged + 60000))
    local polls=0
    while [[ ! -f "$STAGE12_A2_RECORDS/a2_review.json" ]]; do
        stage12_check
        [[ "$polls" -lt 120 ]]
        polls=$((polls + 1))
        local remaining duration
        remaining=$((STAGE12_A2_STAGE_END_CS - STAGE12_NOW - 1))
        [[ "$remaining" -le 500 ]] || remaining=500
        [[ "$remaining" -gt 0 ]]
        printf -v duration '%d.%02d' "$((remaining / 100))" "$((remaining % 100))"
        stage12_utility sleep "$duration"
    done
    stage12_check
    export STAGE12_A2_STAGE_END_CS=$((STAGE12_NOW + 12000))
    stage12_a2_run 120 "$python" -s -B "$STAGE12_AP2_SOURCE/scripts/stage12_wf_ap2_bootstrap_a2.py" finalize --selection "$STAGE12_AP2_SELECTION" --selection-sha256 "$STAGE12_AP2_SELECTION_SHA256"
    stage12_check
    STAGE12_STATUS=A2_COLLECTION_COMPLETE_B_DISABLED
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    stage12_a2_main
fi
