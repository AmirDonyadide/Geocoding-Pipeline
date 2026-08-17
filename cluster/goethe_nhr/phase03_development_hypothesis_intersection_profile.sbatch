#!/usr/bin/env bash
#SBATCH --job-name=safe-phase03-hypothesis-profile
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --mail-user=donyadidegan@safe-frankfurt.de
#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

readonly DATA_ROOT="/work/footprint/donyadidegan/safe_geocoding_pipeline"
readonly REPORT_ROOT="${DATA_ROOT}/reports/generated/phase03/development_hypothesis_intersection_profiles"

export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1
: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${SLURM_SUBMIT_DIR:?SLURM_SUBMIT_DIR is required}"
: "${PHASE03_GIT_COMMIT:?reviewed profiler commit is required}"
: "${PHASE03_INTEGRATION_ROOT:?detached integration worktree is required}"
: "${PHASE03_DEVELOPMENT_PAYLOAD:?read-only DEVELOPMENT payload is required}"
: "${PHASE03_BASELINE_CORE:?read-only parser-v2.1 core is required}"
: "${PHASE03_BASELINE_EVIDENCE:?read-only parser-v2.1 evidence is required}"
: "${PHASE03_CANDIDATE_CORE:?read-only parser-v3.2 core is required}"
: "${PHASE03_CANDIDATE_EVIDENCE:?read-only parser-v3.2 evidence is required}"
: "${PHASE03_DEVELOPMENT_IDENTITIES:?read-only DEVELOPMENT identity set is required}"
: "${PHASE03_TARGETED_R01_CONTEXT:?read-only targeted R01 context is required}"
: "${PHASE03_TARGETED_R01_LABELS:?read-only targeted R01 labels are required}"

readonly INTEGRATION_ROOT="$(realpath -e -- "${PHASE03_INTEGRATION_ROOT}")"
readonly SUBMIT_DIRECTORY="$(realpath -e -- "${SLURM_SUBMIT_DIR}")"
readonly EXPECTED_SBATCH="${INTEGRATION_ROOT}/cluster/goethe_nhr/phase03_development_hypothesis_intersection_profile.sbatch"
readonly RESOLVED_DATA_ROOT="$(realpath -e -- "${DATA_ROOT}")"
readonly CONTROLLED_ROOT="$(realpath -e -- "${RESOLVED_DATA_ROOT}/derived/controlled/phase03_v1")"

[[ "${SUBMIT_DIRECTORY}" == "${INTEGRATION_ROOT}" ]] || {
  echo "HYPOTHESIS_PROFILE_SUBMIT_DIRECTORY_MISMATCH" >&2
  exit 1
}
[[ -r "${EXPECTED_SBATCH}" ]] || {
  echo "HYPOTHESIS_PROFILE_SBATCH_NOT_READABLE" >&2
  exit 1
}
cmp -s -- "${BASH_SOURCE[0]}" "${EXPECTED_SBATCH}" || {
  echo "HYPOTHESIS_PROFILE_SBATCH_SOURCE_MISMATCH" >&2
  exit 1
}
[[ "$(git -C "${INTEGRATION_ROOT}" rev-parse HEAD)" == "${PHASE03_GIT_COMMIT}" ]] || {
  echo "HYPOTHESIS_PROFILE_GIT_COMMIT_MISMATCH" >&2
  exit 1
}
[[ -z "$(git -C "${INTEGRATION_ROOT}" symbolic-ref -q --short HEAD)" ]] || {
  echo "HYPOTHESIS_PROFILE_WORKTREE_NOT_DETACHED" >&2
  exit 1
}
[[ -z "$(git -C "${INTEGRATION_ROOT}" status --short)" ]] || {
  echo "HYPOTHESIS_PROFILE_WORKTREE_NOT_CLEAN" >&2
  exit 1
}

for input in \
  "${PHASE03_DEVELOPMENT_PAYLOAD}" \
  "${PHASE03_BASELINE_CORE}" \
  "${PHASE03_BASELINE_EVIDENCE}" \
  "${PHASE03_CANDIDATE_CORE}" \
  "${PHASE03_CANDIDATE_EVIDENCE}" \
  "${PHASE03_DEVELOPMENT_IDENTITIES}" \
  "${PHASE03_TARGETED_R01_CONTEXT}" \
  "${PHASE03_TARGETED_R01_LABELS}"; do
  [[ -f "${input}" && -r "${input}" ]] || {
    echo "HYPOTHESIS_PROFILE_INPUT_NOT_READABLE" >&2
    exit 1
  }
  resolved_input="$(realpath -e -- "${input}")"
  [[ "${resolved_input}" == "${CONTROLLED_ROOT}/"* ]] || {
    echo "HYPOTHESIS_PROFILE_INPUT_OUTSIDE_CONTROLLED_DEVELOPMENT" >&2
    exit 1
  }
  [[ "${resolved_input,,}" != *locked* ]] || {
    echo "HYPOTHESIS_PROFILE_LOCKED_PATH_PROHIBITED" >&2
    exit 1
  }
done

cd "${INTEGRATION_ROOT}"
source "${DATA_ROOT}/.venv-goethe-nhr/bin/activate"
export PYTHONPATH="${INTEGRATION_ROOT}/src"

python - <<'PY'
import sys
import unicodedata

from safe_geocoding_pipeline.phase03.config import Phase03Config
from safe_geocoding_pipeline.phase03.constants import (
    PARSER_VERSION_V2_1,
    PARSER_VERSION_V3_2,
)

if sys.version_info[:3] != (3, 14, 3) or unicodedata.unidata_version != "16.0.0":
    raise SystemExit("HYPOTHESIS_PROFILE_RUNTIME_MISMATCH")
for version in (PARSER_VERSION_V2_1, PARSER_VERSION_V3_2):
    Phase03Config.for_parser_version(version).validate()
PY

readonly TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
readonly COMMIT_SHORT="${PHASE03_GIT_COMMIT:0:8}"
readonly PROFILE_ID="phase03_development_hypothesis_intersection_profile_${TIMESTAMP}_${SLURM_JOB_ID}_${COMMIT_SHORT}"
readonly ATTEMPT_PARENT="${REPORT_ROOT}/.in_progress"
readonly ATTEMPT="${ATTEMPT_PARENT}/${PROFILE_ID}"
readonly FINAL="${REPORT_ROOT}/${PROFILE_ID}"

mkdir -p "${ATTEMPT_PARENT}" "${REPORT_ROOT}"
chmod 0700 "${ATTEMPT_PARENT}" "${REPORT_ROOT}"
[[ ! -e "${ATTEMPT}" && ! -e "${FINAL}" ]] || {
  echo "HYPOTHESIS_PROFILE_OUTPUT_EXISTS" >&2
  exit 1
}

echo "job_id=${SLURM_JOB_ID}"
echo "hostname=$(hostname)"
echo "start_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "git_commit=${PHASE03_GIT_COMMIT}"
echo "profile_id=${PROFILE_ID}"
echo "development_rows_expected=8000"
echo "locked_payload_access=PROHIBITED"
echo "raw_values_reported=false"

python -m safe_geocoding_pipeline.phase03.cli \
  development-hypothesis-intersection-profile \
  --development-payload "${PHASE03_DEVELOPMENT_PAYLOAD}" \
  --baseline-core "${PHASE03_BASELINE_CORE}" \
  --baseline-evidence "${PHASE03_BASELINE_EVIDENCE}" \
  --candidate-core "${PHASE03_CANDIDATE_CORE}" \
  --candidate-evidence "${PHASE03_CANDIDATE_EVIDENCE}" \
  --development-identities "${PHASE03_DEVELOPMENT_IDENTITIES}" \
  --targeted-r01-context "${PHASE03_TARGETED_R01_CONTEXT}" \
  --targeted-r01-labels "${PHASE03_TARGETED_R01_LABELS}" \
  --output-directory "${ATTEMPT}"

mv "${ATTEMPT}" "${FINAL}"
find "${FINAL}" -type d -exec chmod 0700 {} +
find "${FINAL}" -type f -exec chmod 0600 {} +

echo "DEVELOPMENT_HYPOTHESIS_INTERSECTION_PROFILE_COMPLETE"
echo "profile_id=${PROFILE_ID}"
echo "report_root=${FINAL}"
echo "end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
