#!/usr/bin/env bash
#SBATCH --job-name=safe-stage12-terminal
#SBATCH --partition=general1
#SBATCH --account=footprint
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:30:00
#SBATCH --no-requeue
# Exact source and exclusive stdout/stderr destinations are supplied by the sealed submission.
set -euo pipefail
umask 077
ulimit -c 0
: "${STAGE12_TC_SOURCE:?}" "${STAGE12_TC_SHA:?}" "${STAGE12_TC_PYTHON:?}"
: "${STAGE12_TC_BINDING:?}" "${STAGE12_TC_BINDING_SHA:?}"
: "${STAGE12_TC_AUTHORITY:?}" "${STAGE12_TC_AUTHORITY_SHA:?}"
successor_args=()
case "${STAGE12_TC_SAME_DOMAIN_SUCCESSOR-}" in
  "") ;;
  1) successor_args=(--same-domain-successor) ;;
  *) exit 2 ;;
esac
# Fresh r2 is opt-in and must agree with the canonical control family.
case "${STAGE12_TC_HANDOFF_WINDOW_SUCCESSOR-}" in
  "") ;;
  1)
    [[ "${STAGE12_TC_SAME_DOMAIN_SUCCESSOR-}" == 1 ]] || exit 2
    successor_args+=(--handoff-window-successor)
    ;;
  *) exit 2 ;;
esac
export SAFE_EXECUTION_SITE=goethe-nhr PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
unset SAFE_PELIAS_API_KEY SAFE_PELIAS_API_KEY_FILE PYTHONPATH
cd -- "$STAGE12_TC_SOURCE"
[[ "$(git rev-parse HEAD)" == "$STAGE12_TC_SHA" ]]
[[ -z "$(git status --porcelain)" ]]
# Resolve package imports from this exact clean checkout, as do owned children.
export PYTHONPATH="$STAGE12_TC_SOURCE/src"
# One parent process replaces this shell. It owns the original deadline and two children.
exec "$STAGE12_TC_PYTHON" -B scripts/stage12_ra_g1_terminal_parent.py run-pair   --binding "$STAGE12_TC_BINDING" --binding-sha256 "$STAGE12_TC_BINDING_SHA"   --authority "$STAGE12_TC_AUTHORITY" --authority-sha256 "$STAGE12_TC_AUTHORITY_SHA" "${successor_args[@]}"
