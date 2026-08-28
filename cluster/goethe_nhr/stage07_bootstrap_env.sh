#!/usr/bin/env bash
set -euo pipefail
umask 077

: "${STAGE07_INTEGRATION_ROOT:?exact detached Stage 7 worktree is required}"
: "${STAGE07_RUNTIME_ROOT:?new owner-only Stage 7 runtime root is required}"
: "${STAGE07_PARSER_BUNDLE_ROOT:?frozen Stage 7 parser bundle is required}"
: "${STAGE07_PARSER_BUNDLE_FINGERPRINT:?exact parser bundle fingerprint is required}"

readonly DATA_ROOT="$(realpath -e -- \
  "/work/footprint/donyadidegan/safe_geocoding_pipeline")"
readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE07_INTEGRATION_ROOT}")"
readonly RUNTIME_ROOT="$(realpath -m -- "${STAGE07_RUNTIME_ROOT}")"
readonly PARSER_BUNDLE_ROOT="$(realpath -e -- "${STAGE07_PARSER_BUNDLE_ROOT}")"
readonly VENV_PATH="${RUNTIME_ROOT}/venv"
readonly BASE_PYTHON="${STAGE07_PYTHON_BIN:-${DATA_ROOT}/.venv-goethe-nhr/bin/python}"

fail_runtime() {
  echo "STAGE07_RUNTIME_NOT_READY: $*" >&2
  exit 1
}

for controlled_path in \
  "${INTEGRATION_ROOT}" \
  "${RUNTIME_ROOT}" \
  "${PARSER_BUNDLE_ROOT}"; do
  [[ "${controlled_path}" == "${DATA_ROOT}"/* ]] || \
    fail_runtime "controlled Goethe path required"
  [[ "${controlled_path,,}" != *holdout* ]] || \
    fail_runtime "HOLDOUT path prohibited"
done
[[ -x "${BASE_PYTHON}" ]] || fail_runtime "pinned base Python is unavailable"
"${BASE_PYTHON}" - <<'PY' || fail_runtime "base Python/Unicode runtime differs"
import sys
import unicodedata

assert sys.version_info[:3] == (3, 14, 3), sys.version
assert unicodedata.unidata_version == "16.0.0", unicodedata.unidata_version
PY

[[ ! -e "${RUNTIME_ROOT}" ]] || fail_runtime "runtime root already exists"
install -d -m 0700 "${RUNTIME_ROOT}"
"${BASE_PYTHON}" -m venv "${VENV_PATH}" || \
  fail_runtime "isolated Stage 7 environment could not be created"
"${VENV_PATH}/bin/python" -m pip install --quiet \
  pip==26.2.1 setuptools==80.9.0 wheel==0.45.1 || \
  fail_runtime "pinned packaging bootstrap failed"
"${VENV_PATH}/bin/python" -m pip install --quiet \
  duckdb==1.5.5 ftfy==6.3.1 pyarrow==25.0.0 || \
  fail_runtime "pinned runtime dependencies could not be installed"
"${VENV_PATH}/bin/python" -m pip install --quiet \
  --no-build-isolation --no-deps -e "${INTEGRATION_ROOT}" || \
  fail_runtime "exact Stage 7 dependencies could not be installed"

export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1
export PYTHONHASHSEED=0
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export LIBPOSTAL_DATA_DIR="${PARSER_BUNDLE_ROOT}/data/libpostal"
export LD_LIBRARY_PATH="${PARSER_BUNDLE_ROOT}/lib"
export PYTHONPATH="${PARSER_BUNDLE_ROOT}/python:${INTEGRATION_ROOT}/src"

"${VENV_PATH}/bin/python" - <<'PY' || fail_runtime "Stage 7 runtime differs"
import duckdb
import ftfy
import pip
import pyarrow
import setuptools
import sys
import unicodedata
import wheel

from postal.parser import parse_address
from safe_geocoding_pipeline.preprocessing.stages.s07_parser_bundle import (
    validate_parser_bundle,
)
import os
from pathlib import Path

assert sys.version_info[:3] == (3, 14, 3), sys.version
assert unicodedata.unidata_version == "16.0.0", unicodedata.unidata_version
assert ftfy.__version__ == "6.3.1", ftfy.__version__
assert pyarrow.__version__ == "25.0.0", pyarrow.__version__
assert duckdb.__version__ == "1.5.5", duckdb.__version__
assert pip.__version__ == "26.2.1", pip.__version__
assert setuptools.__version__ == "80.9.0", setuptools.__version__
assert wheel.__version__ == "0.45.1", wheel.__version__
result = parse_address("10 synthetic example street")
assert isinstance(result, list)
assert all(isinstance(item, tuple) and len(item) == 2 for item in result)
validate_parser_bundle(
    Path(os.environ["STAGE07_PARSER_BUNDLE_ROOT"]),
    expected_parser_bundle_fingerprint=os.environ[
        "STAGE07_PARSER_BUNDLE_FINGERPRINT"
    ],
)
PY

chmod 0700 "${RUNTIME_ROOT}" "${VENV_PATH}"
echo "STAGE07_RUNTIME_READY"
echo "stage07_python=${VENV_PATH}/bin/python"
echo "parser_bundle_fingerprint=${STAGE07_PARSER_BUNDLE_FINGERPRINT}"
