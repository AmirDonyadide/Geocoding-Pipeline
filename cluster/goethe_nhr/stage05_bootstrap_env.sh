#!/usr/bin/env bash
set -euo pipefail
umask 077

: "${STAGE05_INTEGRATION_ROOT:?exact detached Stage 5 worktree is required}"
: "${STAGE05_RUNTIME_ROOT:?owner-only Stage 5 runtime root is required}"

readonly DATA_ROOT="/work/footprint/donyadidegan/safe_geocoding_pipeline"
readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE05_INTEGRATION_ROOT}")"
readonly RUNTIME_ROOT="$(realpath -m -- "${STAGE05_RUNTIME_ROOT}")"
readonly VENV_PATH="${RUNTIME_ROOT}/venv"
readonly BASE_PYTHON="${STAGE05_PYTHON_BIN:-${DATA_ROOT}/.venv-goethe-nhr/bin/python}"

fail_runtime() {
  echo "STAGE05_RUNTIME_NOT_READY: $*" >&2
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
    fail_runtime "isolated Stage 5 virtual environment could not be created"
fi

"${VENV_PATH}/bin/python" -m pip install --quiet --upgrade pip || \
  fail_runtime "pip bootstrap failed"
"${VENV_PATH}/bin/python" -m pip install --quiet -e "${INTEGRATION_ROOT}" || \
  fail_runtime "exact Stage 5 candidate dependencies could not be installed"

PYTHONPATH="${INTEGRATION_ROOT}/src" "${VENV_PATH}/bin/python" - <<'PY' || \
  fail_runtime "Stage 5 runtime versions are not exact"
import ftfy
import pyarrow
import sys
import unicodedata

from safe_geocoding_pipeline.preprocessing.stages.s05_reconstruction import (
    validate_stage05_runtime,
)

assert sys.version_info[:3] == (3, 14, 3), sys.version
assert unicodedata.unidata_version == "16.0.0", unicodedata.unidata_version
assert ftfy.__version__ == "6.3.1", ftfy.__version__
assert pyarrow.__version__ == "25.0.0", pyarrow.__version__
validate_stage05_runtime()
PY

chmod 0700 "${RUNTIME_ROOT}" "${VENV_PATH}"
echo "STAGE05_RUNTIME_READY"
echo "stage05_python=${VENV_PATH}/bin/python"
