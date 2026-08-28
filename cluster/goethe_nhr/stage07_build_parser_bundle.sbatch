#!/usr/bin/env bash
#SBATCH --job-name=safe-stage07-bundle
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=04:00:00
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${SLURM_JOB_NAME:?SLURM_JOB_NAME is required}"
: "${STAGE07_BUNDLE_GIT_COMMIT:?submit with the exact pushed bundle commit}"
: "${STAGE07_BUNDLE_INTEGRATION_ROOT:?submit with an exact detached worktree}"
: "${STAGE07_BUNDLE_BUILD_ROOT:?submit with a new owner-only build root}"
: "${STAGE07_BUNDLE_OUTPUT_DIRECTORY:?submit with a new immutable bundle path}"

readonly DATA_ROOT="$(realpath -e -- \
  "/work/footprint/donyadidegan/safe_geocoding_pipeline")"
readonly BASE_PYTHON="${DATA_ROOT}/.venv-goethe-nhr/bin/python"
readonly LIBPOSTAL_REPOSITORY="https://github.com/openvenues/libpostal.git"
readonly LIBPOSTAL_COMMIT="25099c506612b34b23b1bfe286ca6321fcf06f35"
readonly PYPPOSTAL_REPOSITORY="https://github.com/openvenues/pypostal.git"
readonly PYPPOSTAL_COMMIT="d6666a4f6a2ae0e7b83e037a35412f0f6b45c318"
readonly LIBTOOL_RELEASE_URL="https://mirrors.ibiblio.org/gnu/libtool/libtool-2.4.6.tar.gz"
readonly LIBTOOL_RELEASE_SHA256="e3bd4d5d3d025a36c21dd6af7ea818a2afcd4dfc1ea5a17b39d7854bcd0c06e3"
readonly LOG_ROOT="${DATA_ROOT}/logs/slurm"
readonly JOB_STDOUT="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.out"
readonly JOB_STDERR="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.err"

chmod 0600 "${JOB_STDOUT}" "${JOB_STDERR}"
[[ "$(stat -c %a "${JOB_STDOUT}")" == "600" ]]
[[ "$(stat -c %a "${JOB_STDERR}")" == "600" ]]

readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE07_BUNDLE_INTEGRATION_ROOT}")"
readonly BUILD_ROOT="$(realpath -m -- "${STAGE07_BUNDLE_BUILD_ROOT}")"
readonly OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE07_BUNDLE_OUTPUT_DIRECTORY}")"
for controlled_path in "${INTEGRATION_ROOT}" "${BUILD_ROOT}" "${OUTPUT_DIRECTORY}"; do
  [[ "${controlled_path}" == "${DATA_ROOT}"/* ]] || {
    echo "STAGE07_CONTROLLED_PATH_REQUIRED" >&2
    exit 1
  }
  [[ "${controlled_path,,}" != *holdout* ]] || {
    echo "HOLDOUT_ACCESS_PROHIBITED" >&2
    exit 1
  }
done
[[ ! -e "${BUILD_ROOT}" ]]
[[ ! -e "${OUTPUT_DIRECTORY}" ]]

cd "${INTEGRATION_ROOT}"
readonly ACTUAL_COMMIT="$(git rev-parse HEAD)"
[[ "${ACTUAL_COMMIT}" == "${STAGE07_BUNDLE_GIT_COMMIT}" ]] || {
  echo "STAGE07_GIT_COMMIT_MISMATCH" >&2
  exit 1
}
[[ -z "$(git status --porcelain)" ]] || {
  echo "STAGE07_WORKTREE_NOT_CLEAN" >&2
  exit 1
}
[[ "$(git symbolic-ref -q HEAD || true)" == "" ]] || {
  echo "STAGE07_WORKTREE_NOT_DETACHED" >&2
  exit 1
}
[[ -x "${BASE_PYTHON}" ]]
"${BASE_PYTHON}" - <<'PY'
import sys
import unicodedata

assert sys.version_info[:3] == (3, 14, 3), sys.version
assert unicodedata.unidata_version == "16.0.0", unicodedata.unidata_version
PY

install -d -m 0700 "${BUILD_ROOT}"
readonly LIBPOSTAL_SOURCE="${BUILD_ROOT}/libpostal-source"
readonly PYPPOSTAL_SOURCE="${BUILD_ROOT}/pypostal-source"
readonly LIBPOSTAL_PREFIX="${BUILD_ROOT}/libpostal-prefix"
readonly MODEL_PREFIX="${BUILD_ROOT}/model-prefix"
readonly LIBTOOL_ARCHIVE="${BUILD_ROOT}/libtool-2.4.6.tar.gz"
readonly LIBTOOL_SOURCE="${BUILD_ROOT}/libtool-2.4.6"
readonly LIBTOOL_PREFIX="${BUILD_ROOT}/libtool-prefix"
readonly BUILD_VENV="${BUILD_ROOT}/build-venv"
readonly WHEEL_ROOT="${BUILD_ROOT}/wheels"
readonly OUTPUT_PARENT="$(dirname "${OUTPUT_DIRECTORY}")"
readonly OUTPUT_NAME="$(basename "${OUTPUT_DIRECTORY}")"
readonly STAGING_DIRECTORY="${OUTPUT_PARENT}/.${OUTPUT_NAME}.${SLURM_JOB_ID}.in_progress"
install -d -m 0700 "${OUTPUT_PARENT}"
[[ ! -e "${STAGING_DIRECTORY}" ]]

git clone --quiet "${LIBPOSTAL_REPOSITORY}" "${LIBPOSTAL_SOURCE}"
git -C "${LIBPOSTAL_SOURCE}" checkout --quiet --detach "${LIBPOSTAL_COMMIT}"
[[ "$(git -C "${LIBPOSTAL_SOURCE}" rev-parse HEAD)" == "${LIBPOSTAL_COMMIT}" ]]
[[ -z "$(git -C "${LIBPOSTAL_SOURCE}" status --porcelain)" ]]

git clone --quiet "${PYPPOSTAL_REPOSITORY}" "${PYPPOSTAL_SOURCE}"
git -C "${PYPPOSTAL_SOURCE}" checkout --quiet --detach "${PYPPOSTAL_COMMIT}"
[[ "$(git -C "${PYPPOSTAL_SOURCE}" rev-parse HEAD)" == "${PYPPOSTAL_COMMIT}" ]]
[[ -z "$(git -C "${PYPPOSTAL_SOURCE}" status --porcelain)" ]]

curl --fail --location --retry 3 --output "${LIBTOOL_ARCHIVE}" \
  "${LIBTOOL_RELEASE_URL}"
printf '%s  %s\n' "${LIBTOOL_RELEASE_SHA256}" "${LIBTOOL_ARCHIVE}" | \
  sha256sum --check --strict -
tar -xzf "${LIBTOOL_ARCHIVE}" -C "${BUILD_ROOT}"
cd "${LIBTOOL_SOURCE}"
./configure --prefix="${LIBTOOL_PREFIX}"
make -j "${SLURM_CPUS_PER_TASK}"
make install

cd "${LIBPOSTAL_SOURCE}"
"${LIBTOOL_PREFIX}/bin/libtoolize" --copy --force
PATH="${LIBTOOL_PREFIX}/bin:${PATH}" ./bootstrap.sh
./configure --prefix="${LIBPOSTAL_PREFIX}" --datadir="${MODEL_PREFIX}"
make -j "${SLURM_CPUS_PER_TASK}"
make install

[[ "$(<"${MODEL_PREFIX}/libpostal/data_version")" == "v1" ]]
[[ "$(<"${MODEL_PREFIX}/libpostal/parser_model_file_version")" == "v1.0.0" ]]
[[ "$(<"${MODEL_PREFIX}/libpostal/language_classifier_model_file_version")" == "v1.0.0" ]]
[[ -f "${LIBPOSTAL_PREFIX}/lib/libpostal.so.1.0.1" ]]

"${BASE_PYTHON}" -m venv "${BUILD_VENV}"
readonly BUILD_PYTHON="${BUILD_VENV}/bin/python"
"${BUILD_PYTHON}" -m pip install --quiet \
  pip==26.2.1 setuptools==80.9.0 wheel==0.45.1
install -d -m 0700 "${WHEEL_ROOT}"
env LIBPOSTAL_PREFIX="${LIBPOSTAL_PREFIX}" \
  "${BUILD_PYTHON}" -m pip wheel --quiet --no-deps --no-build-isolation \
  --wheel-dir "${WHEEL_ROOT}" "${PYPPOSTAL_SOURCE}"

install -d -m 0700 \
  "${STAGING_DIRECTORY}" \
  "${STAGING_DIRECTORY}/lib" \
  "${STAGING_DIRECTORY}/data" \
  "${STAGING_DIRECTORY}/data/libpostal" \
  "${STAGING_DIRECTORY}/python" \
  "${STAGING_DIRECTORY}/licenses"
install -m 0600 "${LIBPOSTAL_PREFIX}/lib/libpostal.so.1.0.1" \
  "${STAGING_DIRECTORY}/lib/libpostal.so.1.0.1"
install -m 0600 "${LIBPOSTAL_PREFIX}/lib/libpostal.so.1.0.1" \
  "${STAGING_DIRECTORY}/lib/libpostal.so.1"
install -m 0600 "${LIBPOSTAL_PREFIX}/lib/libpostal.so.1.0.1" \
  "${STAGING_DIRECTORY}/lib/libpostal.so"
cp -R "${MODEL_PREFIX}/libpostal/." "${STAGING_DIRECTORY}/data/libpostal/"

readonly PYPPOSTAL_WHEELS=("${WHEEL_ROOT}"/postal-1.1.11-*.whl)
[[ "${#PYPPOSTAL_WHEELS[@]}" -eq 1 ]]
"${BUILD_PYTHON}" -m pip install --quiet --no-compile --no-deps \
  --target "${STAGING_DIRECTORY}/python" six==1.17.0
"${BUILD_PYTHON}" -m pip install --quiet --no-compile --no-deps \
  --target "${STAGING_DIRECTORY}/python" "${PYPPOSTAL_WHEELS[0]}"
install -m 0600 "${LIBPOSTAL_SOURCE}/LICENSE" \
  "${STAGING_DIRECTORY}/licenses/libpostal-LICENSE"
install -m 0600 "${LIBPOSTAL_SOURCE}/src/sparkey/LICENSE" \
  "${STAGING_DIRECTORY}/licenses/libpostal-sparkey-LICENSE"
install -m 0600 "${PYPPOSTAL_SOURCE}/LICENSE" \
  "${STAGING_DIRECTORY}/licenses/pypostal-LICENSE"

if find "${STAGING_DIRECTORY}" -type l -print -quit | grep -q .; then
  echo "STAGE07_PARSER_BUNDLE_SYMLINK_PROHIBITED" >&2
  exit 1
fi
find "${STAGING_DIRECTORY}" -type d -exec chmod 0700 {} +
find "${STAGING_DIRECTORY}" -type f -exec chmod 0600 {} +

export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1
export PYTHONHASHSEED=0
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export LIBPOSTAL_DATA_DIR="${STAGING_DIRECTORY}/data/libpostal"
export LD_LIBRARY_PATH="${STAGING_DIRECTORY}/lib"
export PYTHONPATH="${STAGING_DIRECTORY}/python:${INTEGRATION_ROOT}/src"

"${BASE_PYTHON}" - <<'PY'
import time

started = time.perf_counter()
from postal.parser import parse_address

initialization_ms = round((time.perf_counter() - started) * 1000)
result = parse_address("10 example street")
assert isinstance(result, list)
assert all(
    isinstance(item, tuple)
    and len(item) == 2
    and all(isinstance(value, str) for value in item)
    for item in result
)
print(f"public_parser_initialization_milliseconds={initialization_ms}")
print(f"public_parser_smoke_components={len(result)}")
PY

readonly COMPILER_IDENTITY="$(printf '%s; %s; %s; %s; %s; %s' \
  "$(gcc --version | head -n 1)" \
  "$(make --version | head -n 1)" \
  "$(autoconf --version | head -n 1)" \
  "$(automake --version | head -n 1)" \
  "$("${LIBTOOL_PREFIX}/bin/libtoolize" --version | head -n 1)" \
  "$(pkg-config --version)")"
readonly PYTHON_IDENTITY="$("${BASE_PYTHON}" --version 2>&1) / Unicode 16.0.0"
readonly GLIBC_IDENTITY="$(getconf GNU_LIBC_VERSION)"
readonly PUBLISH_OUTPUT="$("${BASE_PYTHON}" \
  -m safe_geocoding_pipeline.preprocessing.stage07_bundle_cli publish \
  --staging-directory "${STAGING_DIRECTORY}" \
  --output-directory "${OUTPUT_DIRECTORY}" \
  --execution-git-sha "${ACTUAL_COMMIT}" \
  --compiler-identity "${COMPILER_IDENTITY}" \
  --base-python-identity "${PYTHON_IDENTITY}" \
  --glibc-identity "${GLIBC_IDENTITY}")"
printf '%s\n' "${PUBLISH_OUTPUT}"
readonly BUNDLE_FINGERPRINT="$(printf '%s\n' "${PUBLISH_OUTPUT}" | \
  awk -F= '$1 == "stage07_parser_bundle_fingerprint" {print $2}')"
[[ "${BUNDLE_FINGERPRINT}" =~ ^[0-9a-f]{64}$ ]]

export LIBPOSTAL_DATA_DIR="${OUTPUT_DIRECTORY}/data/libpostal"
export LD_LIBRARY_PATH="${OUTPUT_DIRECTORY}/lib"
export PYTHONPATH="${OUTPUT_DIRECTORY}/python:${INTEGRATION_ROOT}/src"
"${BASE_PYTHON}" -m safe_geocoding_pipeline.preprocessing.stage07_bundle_cli validate \
  --output-directory "${OUTPUT_DIRECTORY}" \
  --expected-parser-bundle-fingerprint "${BUNDLE_FINGERPRINT}"

readonly PARSER_EXTENSION="$(find "${OUTPUT_DIRECTORY}/python/postal" \
  -maxdepth 1 -name '_parser*.so' -type f -print -quit)"
[[ -n "${PARSER_EXTENSION}" ]]
ldd "${PARSER_EXTENSION}" | grep -F "${OUTPUT_DIRECTORY}/lib/libpostal.so.1" >/dev/null

echo "public_assets_only=true"
echo "protected_inputs_opened=false"
echo "STAGE07_PARSER_BUNDLE_BUILD_PASS"
