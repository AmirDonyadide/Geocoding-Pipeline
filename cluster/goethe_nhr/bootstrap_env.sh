#!/usr/bin/env bash
set -euo pipefail
umask 077

readonly REPO_ROOT="/work/footprint/donyadidegan/safe_geocoding_pipeline"
readonly VENV_PATH="${REPO_ROOT}/.venv-goethe-nhr"

fail_runtime() {
  echo "CLUSTER_RUNTIME_NOT_READY: $*" >&2
  exit 1
}

[[ -d "${REPO_ROOT}/.git" ]] || fail_runtime "repository is absent at ${REPO_ROOT}"
cd "${REPO_ROOT}"
mkdir -p derived/controlled reports/generated logs/slurm
chmod 0700 derived/controlled reports/generated logs/slurm

if command -v module >/dev/null 2>&1; then
  echo "Available Python modules (informational):"
  module -t avail python 2>&1 || true
fi

python_bin="${PYTHON_3_14_3:-}"
if [[ -z "${python_bin}" ]] && command -v python3.14 >/dev/null 2>&1; then
  python_bin="$(command -v python3.14)"
fi
[[ -n "${python_bin}" && -x "${python_bin}" ]] || fail_runtime \
  "set PYTHON_3_14_3 to an existing Python 3.14.3 interpreter; no other runtime is permitted"

"${python_bin}" - <<'PY' || fail_runtime "Python must be exactly 3.14.3 with Unicode data 16.0.0"
import sys
import unicodedata

assert sys.version_info[:3] == (3, 14, 3), sys.version
assert unicodedata.unidata_version == "16.0.0", unicodedata.unidata_version
PY

if [[ ! -x "${VENV_PATH}/bin/python" ]]; then
  "${python_bin}" -m venv "${VENV_PATH}" || \
    fail_runtime "could not create the isolated Python 3.14.3 environment"
fi

venv_python="${VENV_PATH}/bin/python"
"${venv_python}" - <<'PY' || fail_runtime "existing cluster virtual environment uses the wrong runtime"
import sys
import unicodedata

assert sys.version_info[:3] == (3, 14, 3), sys.version
assert unicodedata.unidata_version == "16.0.0", unicodedata.unidata_version
PY

"${venv_python}" -m pip install --upgrade pip || \
  fail_runtime "pip bootstrap failed; check cluster package-index/network policy"
"${venv_python}" -m pip install -e '.[dev]' || \
  fail_runtime "project dependency installation failed; provide compatible pinned wheels"

"${venv_python}" - <<'PY' || fail_runtime "project dependency or package validation failed"
import duckdb
import pyarrow
import safe_geocoding_pipeline

assert pyarrow.__version__ == "25.0.0", pyarrow.__version__
assert duckdb.__version__ == "1.5.5", duckdb.__version__
assert safe_geocoding_pipeline.__name__ == "safe_geocoding_pipeline"
PY

"${VENV_PATH}/bin/safe-geocoding-phase03" validate-production-references >/dev/null || \
  fail_runtime "production Phase 3 references failed validation"
"${VENV_PATH}/bin/safe-geocoding-phase03" validate-rule-registry >/dev/null || \
  fail_runtime "Phase 3 rule registry failed validation"
"${venv_python}" -m pytest -q tests/test_execution_policy.py \
  tests/test_phase03_production_references.py || fail_runtime "cluster smoke tests failed"

echo "CLUSTER_RUNTIME_READY"
echo "python=${venv_python}"
