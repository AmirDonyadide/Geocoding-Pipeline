#!/usr/bin/env bash
set -euo pipefail
umask 077

: "${STAGE04_INTEGRATION_ROOT:?exact detached Stage 4 worktree is required}"
: "${STAGE04_RUNTIME_ROOT:?owner-only Stage 4 runtime root is required}"

readonly DATA_ROOT="/work/footprint/donyadidegan/safe_geocoding_pipeline"
readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE04_INTEGRATION_ROOT}")"
readonly RUNTIME_ROOT="$(realpath -m -- "${STAGE04_RUNTIME_ROOT}")"
readonly VENV_PATH="${RUNTIME_ROOT}/venv"
readonly BASE_PYTHON="${STAGE04_PYTHON_BIN:-${DATA_ROOT}/.venv-goethe-nhr/bin/python}"

fail_runtime() {
  echo "STAGE04_RUNTIME_NOT_READY: $*" >&2
  exit 1
}

[[ -x "${BASE_PYTHON}" ]] || fail_runtime "pinned base Python is unavailable"
"${BASE_PYTHON}" - <<'PY' || \
  fail_runtime "base runtime is not Python 3.14.3 / Unicode 16.0.0"
import sys
import unicodedata

assert sys.version_info[:3] == (3, 14, 3), sys.version
assert unicodedata.unidata_version == "16.0.0", unicodedata.unidata_version
PY

install -d -m 0700 "${RUNTIME_ROOT}"
if [[ ! -x "${VENV_PATH}/bin/python" ]]; then
  "${BASE_PYTHON}" -m venv "${VENV_PATH}" || \
    fail_runtime "isolated Stage 4 virtual environment could not be created"
fi

"${VENV_PATH}/bin/python" -m pip install --quiet --upgrade pip || \
  fail_runtime "pip bootstrap failed"
"${VENV_PATH}/bin/python" -m pip install --quiet -e "${INTEGRATION_ROOT}" || \
  fail_runtime "exact candidate dependencies could not be installed"

PYTHONPATH="${INTEGRATION_ROOT}/src" "${VENV_PATH}/bin/python" - <<'PY' || \
  fail_runtime "Stage 4 runtime versions are not exact"
import pyarrow
import sys
import unicodedata

from safe_geocoding_pipeline.preprocessing.stages.s04_lowercase import (
    validate_stage04_runtime,
)

assert sys.version_info[:3] == (3, 14, 3), sys.version
assert unicodedata.unidata_version == "16.0.0", unicodedata.unidata_version
assert pyarrow.__version__ == "25.0.0", pyarrow.__version__
validate_stage04_runtime()
PY

chmod 0700 "${RUNTIME_ROOT}" "${VENV_PATH}"
echo "STAGE04_RUNTIME_READY"
echo "stage04_python=${VENV_PATH}/bin/python"
