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

# Slurm copies this launcher into its spool; dependencies remain in Git.
# These tiny startup checks precede loading any external shell definitions.
stage12_a2_source_dependency() {
    local project=$1 source=${STAGE12_AP2_SOURCE:?reviewed source required}
    local helper canonical identity hash_line
    [[ "$source" =~ ^/[A-Za-z0-9_./-]+$ && "$source" != *'/../'* && "${source%/*}" == "$project/integration_stage12" ]] || return 2
    helper=$source/cluster/goethe_nhr/stage12_wf_ap2_allocation.sbatch
    # Five timeout+utility pairs, included in the non-resetting counter below.
    STAGE12_A2_STARTUP_UTILITIES=10
    canonical=$(timeout 15s realpath -e -- "$source") || return $?
    [[ "$canonical" == "$source" ]] || return 2
    identity=$(timeout 15s stat -c '%u:%a' -- "$source") || return $?
    [[ "$identity" == "$EUID:700" ]] || return 2
    canonical=$(timeout 15s realpath -e -- "$helper") || return $?
    [[ "$canonical" == "$helper" && -f "$helper" && ! -L "$helper" ]] || return 2
    identity=$(timeout 15s stat -c '%u:%h' -- "$helper") || return $?
    [[ "$identity" == "$EUID:1" ]] || return 2
    hash_line=$(timeout 15s sha256sum -- "$helper") || return $?
    [[ "${hash_line%% *}" == 7b386eb21f2ece47e02af1047daaf8f212b0fc870f08834f25b8e20bc276a620 ]] || return 2
    # Definitions only: strict main cannot run when sourced. Its exact bytes
    # are also part of the selected99-file original-source validation.
    source "$helper"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    stage12_a2_source_dependency /panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline
else
    # Definition-only local tests explicitly supply their reviewed checkout.
    source "${STAGE12_AP2_SOURCE:?reviewed source required}/cluster/goethe_nhr/stage12_wf_ap2_allocation.sbatch"
fi

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

stage12_a2_bind_log_parents() {
    local path canonical identity
    for path in "$STAGE12_A2_PARENT" "$STAGE12_A2_RECORDS"; do
        stage12_capture canonical realpath -e -- "$path" || return $?
        [[ "$canonical" == "$path" ]] || return 2
        stage12_capture identity stat -c '%u:%a:%d:%i' -- "$path" || return $?
        [[ "$identity" =~ ^${EUID}:700:[0-9]+:[0-9]+$ ]] || return 2
        if [[ "$path" == "$STAGE12_A2_PARENT" ]]; then
            STAGE12_A2_PARENT_ID=$identity
        else
            STAGE12_A2_RECORDS_ID=$identity
        fi
    done
}

stage12_a2_logwrite() {
    local path=$1 json=$2 parent name expected
    [[ "$path" =~ ^/[A-Za-z0-9_./-]+$ && "$path" != *'/../'* && "${#json}" -le 4096 ]] || return 2
    parent=${path%/*}; name=${path##*/}
    [[ -n "$name" && "$name" != . && "$name" != .. ]] || return 2
    [[ -n "${STAGE12_A2_PARENT_ID:-}" && -n "${STAGE12_A2_RECORDS_ID:-}" ]] || return 2
    if [[ "$parent" == "$STAGE12_A2_PARENT" ]]; then
        expected=$STAGE12_A2_PARENT_ID
    elif [[ "$parent" == "$STAGE12_A2_RECORDS" ]]; then
        expected=$STAGE12_A2_RECORDS_ID
    else
        return 2
    fi
    # Three checks, each with two realpath and three stat calls, plus
    # timeout+bash+sync: precharge all18 invocations before any child runs.
    STAGE12_UTILITIES=$((STAGE12_UTILITIES + 17))
    stage12_utility timeout --signal=TERM --kill-after=1s 5s bash -c \
        'set -euo pipefail; umask 077; set -o noclobber
         parent=$1; name=$2; json=$3; expected=$4
         root=$5; root_id=$6; records=$7; records_id=$8
         check() {
             [[ "$(realpath -e -- "$root")" == "$root" ]] || return 2
             [[ "$(stat -c "%u:%a:%d:%i" -- "$root")" == "$root_id" ]] || return 2
             [[ "$(realpath -e -- "$records")" == "$records" ]] || return 2
             [[ "$(stat -c "%u:%a:%d:%i" -- "$records")" == "$records_id" ]] || return 2
             [[ "$(stat -c "%u:%a:%d:%i" -- .)" == "$expected" ]] || return 2
         }
         cd -P -- "$parent"
         check
         printf "%s\n" "$json" > "$name"
         check
         sync -f "$name"
         check' \
        a2-log "$parent" "$name" "$json" "$expected" \
        "$STAGE12_A2_PARENT" "$STAGE12_A2_PARENT_ID" \
        "$STAGE12_A2_RECORDS" "$STAGE12_A2_RECORDS_ID" || return $?
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
    STAGE12_UTILITIES=$((2 + STAGE12_A2_STARTUP_UTILITIES)); STAGE12_PYTHONS=0; STAGE12_STATUS=INCOMPLETE
    IFS= read -r STAGE12_BOOT < /proc/sys/kernel/random/boot_id
    stage12_tick; stage12_apply_epoch
    export STAGE12_A2_CAPTURE_START_CS=$STAGE12_START
    export STAGE12_A2_STAGE_END_CS=$((STAGE12_START + 12000))
    STAGE12_A2_PARENT=$parent
    # If binding fails there is no trap write into an unchecked directory.
    stage12_a2_bind_log_parents
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
