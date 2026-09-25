#!/usr/bin/env bash
#SBATCH --job-name=safe-stage10-public-local-probe
#SBATCH --partition=general1
#SBATCH --account=footprint
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --tmp=1024M
#SBATCH --time=00:05:00
#SBATCH --no-requeue

set -euo pipefail
umask 077
: "${SLURM_JOB_ID:?scheduled execution required}"
: "${STAGE10_PROBE_GIT_SHA:?exact pushed probe required}"
: "${STAGE10_PROBE_CHECKOUT:?detached checkout required}"
: "${STAGE10_PROBE_RECEIPTS:?private public-only receipt directory required}"
: "${STAGE10_PROBE_PANFS_COPY:?private public-only copy target required}"
export SAFE_EXECUTION_SITE=goethe-nhr PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="${STAGE10_PROBE_CHECKOUT}/src"
export GIT_OPTIONAL_LOCKS=0
test "$(git -C "$STAGE10_PROBE_CHECKOUT" rev-parse HEAD)" = "$STAGE10_PROBE_GIT_SHA"
test -z "$(git -C "$STAGE10_PROBE_CHECKOUT" status --porcelain --untracked-files=all)"
if git -C "$STAGE10_PROBE_CHECKOUT" symbolic-ref -q HEAD; then exit 2; fi
date -u +%FT%TZ
scontrol show job "$SLURM_JOB_ID"
df -k "/local/$SLURM_JOB_ID"
stat -c '%U %u %a %n' "/local/$SLURM_JOB_ID"
trap 'code=$?; printf "PROBE_TERMINAL_EXIT=%s UTC=%s\n" "$code" "$(date -u +%FT%TZ)"' EXIT
python3 -B "${STAGE10_PROBE_CHECKOUT}/scripts/stage10_local_storage_probe.py" \
  --receipt-directory "$STAGE10_PROBE_RECEIPTS" \
  --panfs-copy-directory "$STAGE10_PROBE_PANFS_COPY"
