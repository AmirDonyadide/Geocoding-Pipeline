#!/usr/bin/env bash
#SBATCH --job-name=safe-stage12-reader-profile
#SBATCH --partition=general1
#SBATCH --account=footprint
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=6G
#SBATCH --time=00:12:00
#SBATCH --no-requeue
set -euo pipefail
umask 077
ulimit -c 0
: "${SLURM_JOB_ID:?compute allocation required}"
: "${STAGE12_PROFILE_SOURCE:?exact candidate source}"
: "${STAGE12_PROFILE_BASELINE:?exact baseline source}"
: "${STAGE12_PROFILE_SHA:?candidate SHA}"
: "${STAGE12_PROFILE_BASELINE_SHA:?baseline SHA}"
: "${STAGE12_PROFILE_INPUTS:?private synthetic inputs}"
: "${STAGE12_PROFILE_ARCHIVE_SHA:?archive SHA256}"
: "${STAGE12_PROFILE_MANIFEST_SHA:?fixture manifest SHA256}"
: "${STAGE12_PROFILE_OUTPUT:?new private output}"
readonly stage12_project=/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline
readonly stage12_python="${stage12_project}/runtimes/stage06/stage06_development_20260828T223804Z_f39047cc825d/venv/bin/python"
readonly stage12_input_sha=c8523edcd72735cf93f3ce6f4be8e76bf877cd0948da0d380c0eb18da21f492a
[[ "${SLURM_RESTART_COUNT:-0}" == 0 ]]
for stage12_src in "${STAGE12_PROFILE_SOURCE}" "${STAGE12_PROFILE_BASELINE}"; do
  [[ "$(dirname -- "${stage12_src}")" == "${stage12_project}/integration_stage12" ]]
  [[ -z "$(git -C "${stage12_src}" status --porcelain)" ]]
  [[ -z "$(git -C "${stage12_src}" symbolic-ref -q HEAD || true)" ]]
  [[ "$(realpath -e -- "${stage12_src}")" == "${stage12_src}" ]]
done
[[ "$(git -C "${STAGE12_PROFILE_SOURCE}" rev-parse HEAD)" == "${STAGE12_PROFILE_SHA}" ]]
[[ "$(git -C "${STAGE12_PROFILE_BASELINE}" rev-parse HEAD)" == "${STAGE12_PROFILE_BASELINE_SHA}" ]]
[[ "$(dirname -- "${STAGE12_PROFILE_OUTPUT}")" == "${stage12_project}/derived/controlled/stage12/client_diagnostics" ]]
export SAFE_EXECUTION_SITE=goethe-nhr
PYTHONPATH="${STAGE12_PROFILE_SOURCE}/src" "${stage12_python}" -B -c \
  'from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm; require_goethe_nhr_slurm("stage12 synthetic reader profile")'
[[ "$(sha256sum "${STAGE12_PROFILE_INPUTS}/SYNTHETIC120_INPUT.json" | cut -d' ' -f1)" == "${stage12_input_sha}" ]]
[[ -x "${stage12_python}" ]]
unset SAFE_PELIAS_API_KEY SAFE_PELIAS_API_KEY_FILE PYTHONPATH
export SAFE_EXECUTION_SITE=goethe-nhr PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONHASHSEED=0
export LANG=C.UTF-8 LC_ALL=C.UTF-8 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
if [[ "${1:-}" == --pair ]]; then
  # Fixed baseline-first order, exactly one process per version. No retry.
  stage12_pair_exit=0
  for stage12_label in baseline candidate; do
    (cd "${STAGE12_PROFILE_OUTPUT}/fixture" && sha256sum --quiet -c "${STAGE12_PROFILE_INPUTS}/PROFILE_FIXTURE.sha256")
    stage12_src="${STAGE12_PROFILE_SOURCE}"
    [[ "${stage12_label}" != baseline ]] || stage12_src="${STAGE12_PROFILE_BASELINE}"
    set +e
    "${stage12_python}" -B "${STAGE12_PROFILE_SOURCE}/scripts/stage12_reader_profile.py"       --source "${stage12_src}" --fixture "${STAGE12_PROFILE_OUTPUT}/fixture/campaign"       --input "${STAGE12_PROFILE_INPUTS}/SYNTHETIC120_INPUT.json" --input-sha256 "${stage12_input_sha}"       --output "${STAGE12_PROFILE_OUTPUT}/${stage12_label}"       >"${STAGE12_PROFILE_OUTPUT}/${stage12_label}.out" 2>"${STAGE12_PROFILE_OUTPUT}/${stage12_label}.err"
    stage12_exit=$?
    set -e
    printf '%s\n' "${stage12_exit}" >"${STAGE12_PROFILE_OUTPUT}/${stage12_label}.exit"
    [[ "${stage12_exit}" == 0 ]] || stage12_pair_exit=1
  done
  exit "${stage12_pair_exit}"
fi
[[ ! -e "${STAGE12_PROFILE_OUTPUT}" ]]
[[ "$(sha256sum "${STAGE12_PROFILE_INPUTS}/PROFILE_FIXTURE.tar.gz" | cut -d' ' -f1)" == "${STAGE12_PROFILE_ARCHIVE_SHA}" ]]
[[ "$(sha256sum "${STAGE12_PROFILE_INPUTS}/PROFILE_FIXTURE.sha256" | cut -d' ' -f1)" == "${STAGE12_PROFILE_MANIFEST_SHA}" ]]
mkdir -m0700 "${STAGE12_PROFILE_OUTPUT}" "${STAGE12_PROFILE_OUTPUT}/fixture"
tar -xzf "${STAGE12_PROFILE_INPUTS}/PROFILE_FIXTURE.tar.gz" -C "${STAGE12_PROFILE_OUTPUT}/fixture" --no-same-owner
(cd "${STAGE12_PROFILE_OUTPUT}/fixture" && sha256sum --quiet -c "${STAGE12_PROFILE_INPUTS}/PROFILE_FIXTURE.sha256")
# Diagnostic-only shared600s cap, not an extension of the500s completion gate.
set +e
timeout --signal=TERM --kill-after=5s 600s bash "$0" --pair
stage12_exit=$?
set -e
printf '%s\n' "${stage12_exit}" >"${STAGE12_PROFILE_OUTPUT}/pair.exit"
exit "${stage12_exit}"
