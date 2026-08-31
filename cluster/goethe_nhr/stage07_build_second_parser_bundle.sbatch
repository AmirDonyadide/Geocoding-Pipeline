#!/usr/bin/env bash
#SBATCH --job-name=safe-stage07-second-bundle
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=24G
#SBATCH --time=06:00:00
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${SLURM_JOB_NAME:?SLURM_JOB_NAME is required}"
: "${STAGE07_SECOND_BUNDLE_GIT_COMMIT:?exact pushed commit is required}"
: "${STAGE07_SECOND_BUNDLE_INTEGRATION_ROOT:?exact detached worktree is required}"
: "${STAGE07_SECOND_BUNDLE_BUILD_ROOT:?new owner-only build root is required}"
: "${STAGE07_SECOND_BUNDLE_OUTPUT_DIRECTORY:?new immutable output is required}"

readonly DATA_ROOT="$(realpath -e -- \
  "/work/footprint/donyadidegan/safe_geocoding_pipeline")"
readonly BASE_PYTHON="${DATA_ROOT}/.venv-goethe-nhr/bin/python"
readonly LOG_ROOT="${DATA_ROOT}/logs/slurm"
readonly JOB_STDOUT="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.out"
readonly JOB_STDERR="${LOG_ROOT}/${SLURM_JOB_NAME}_${SLURM_JOB_ID}.err"

readonly PYTHON_VERSION="3.13.15"
readonly PYTHON_ARCHIVE_NAME="Python-${PYTHON_VERSION}.tgz"
readonly PYTHON_URL="https://www.python.org/ftp/python/${PYTHON_VERSION}/${PYTHON_ARCHIVE_NAME}"
readonly PYTHON_SHA256="c28d9d213c09b5b5ab2c29812950e12f746999e099b82894231be954b26baed9"
readonly SQLITE_VERSION="3.46.1"
readonly SQLITE_ARCHIVE_NAME="sqlite-autoconf-3460100.tar.gz"
readonly SQLITE_URL="https://www.sqlite.org/2024/${SQLITE_ARCHIVE_NAME}"
readonly SQLITE_SHA256="67d3fe6d268e6eaddcae3727fce58fcc8e9c53869bdd07a0c61e38ddf2965071"
readonly DEEPPARSE_VERSION="0.10.0"
readonly DEEPPARSE_WHEEL_SHA256="0e4641147f0a27875edb715248d93277082f10610f237a5e2f8c296d576884bd"
readonly BPEMB_VERSION="0.3.6"
readonly BPEMB_WHEEL_SHA256="6eabc133bbd0a7dbeb52b2cfed55ca5cacbb38b236ebb1f504b279a2d835e8b7"
readonly PYTORCH_VERSION="2.7.1+cpu"
readonly MODEL_REVISION="4af74dad1d547804dfc2de8f40fb23fbbec5b811"
readonly MODEL_CONFIG_URL="https://huggingface.co/deepparse/bpemb-attention/resolve/${MODEL_REVISION}/config.json"
readonly MODEL_CONFIG_SHA256="60155c61595e5e968a860ff40ebf777979d80b4afd923333f121d342375dc219"
readonly MODEL_WEIGHTS_URL="https://huggingface.co/deepparse/bpemb-attention/resolve/${MODEL_REVISION}/model.safetensors"
readonly MODEL_WEIGHTS_SHA256="4d761100d70631a3cb53853a530ad39f5be09cedad0f8c3be0d968bd8accecb5"
readonly BPEMB_MODEL_URL="https://bpemb.h-its.org/multi/multi/multi.wiki.bpe.vs100000.model"
readonly BPEMB_MODEL_SHA256="c6064152904900f91e04c97f95e591495f1c601eba70c3a46417f97283c2fdf1"
readonly BPEMB_ARCHIVE_URL="https://bpemb.h-its.org/multi/multi/multi.wiki.bpe.vs100000.d300.w2v.bin.tar.gz"
readonly BPEMB_ARCHIVE_SHA256="2132ce5bee66b04d39f6f013ccb766a2f595963a681da62fbb22b8aa5cce6ad8"
readonly BPEMB_EMBEDDING_SHA256="bb4d89f01e71046895fde0fe954845e3cc91ff888a63f06e6413328de308ad03"
readonly PYTHON_CONFIGURE_ARGUMENTS=(
  "--prefix=<private-python-prefix>"
  "--with-ensurepip=install"
)

for required_command in \
  curl gcc make tar sha256sum unzip ldd readelf; do
  command -v "${required_command}" >/dev/null || {
    echo "STAGE07_SECOND_PARSER_BUILD_TOOL_MISSING" >&2
    exit 1
  }
done

chmod 0600 "${JOB_STDOUT}" "${JOB_STDERR}"
[[ "$(stat -c %a "${JOB_STDOUT}")" == "600" ]]
[[ "$(stat -c %a "${JOB_STDERR}")" == "600" ]]

readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE07_SECOND_BUNDLE_INTEGRATION_ROOT}")"
readonly BUILD_ROOT="$(realpath -m -- "${STAGE07_SECOND_BUNDLE_BUILD_ROOT}")"
readonly OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE07_SECOND_BUNDLE_OUTPUT_DIRECTORY}")"
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
[[ "${ACTUAL_COMMIT}" == "${STAGE07_SECOND_BUNDLE_GIT_COMMIT}" ]]
[[ -z "$(git status --porcelain)" ]]
[[ "$(git symbolic-ref -q HEAD || true)" == "" ]]
[[ -x "${BASE_PYTHON}" ]]

install -d -m 0700 "${BUILD_ROOT}"
readonly PYTHON_ARCHIVE="${BUILD_ROOT}/${PYTHON_ARCHIVE_NAME}"
readonly PYTHON_SOURCE="${BUILD_ROOT}/Python-${PYTHON_VERSION}"
readonly PYTHON_PREFIX="${BUILD_ROOT}/python-prefix"
readonly PIP_CACHE="${BUILD_ROOT}/pip-cache"
readonly PUBLIC_DOWNLOADS="${BUILD_ROOT}/public-downloads"
readonly CACHE_ROOT="${BUILD_ROOT}/runtime-cache"
readonly SQLITE_ARCHIVE="${PUBLIC_DOWNLOADS}/${SQLITE_ARCHIVE_NAME}"
readonly SQLITE_SOURCE="${BUILD_ROOT}/sqlite-autoconf-3460100"
readonly SQLITE_PREFIX="${BUILD_ROOT}/sqlite-prefix"
install -d -m 0700 "${PIP_CACHE}" "${PUBLIC_DOWNLOADS}" "${CACHE_ROOT}"

export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1
export PYTHONHASHSEED=0
export LANG=C.UTF-8
export LC_ALL=C.UTF-8

curl --fail --location --retry 3 --output "${PYTHON_ARCHIVE}" "${PYTHON_URL}"
printf '%s  %s\n' "${PYTHON_SHA256}" "${PYTHON_ARCHIVE}" | sha256sum --check --strict -
curl --fail --location --retry 3 --output "${SQLITE_ARCHIVE}" "${SQLITE_URL}"
printf '%s  %s\n' "${SQLITE_SHA256}" "${SQLITE_ARCHIVE}" | \
  sha256sum --check --strict -
tar -xzf "${SQLITE_ARCHIVE}" -C "${BUILD_ROOT}"
cd "${SQLITE_SOURCE}"
CFLAGS="-O2 -fPIC" ./configure \
  --prefix="${SQLITE_PREFIX}" \
  --disable-shared \
  --enable-static
make -j "${SLURM_CPUS_PER_TASK}"
make install

tar -xzf "${PYTHON_ARCHIVE}" -C "${BUILD_ROOT}"
cd "${PYTHON_SOURCE}"
PKG_CONFIG_PATH="${SQLITE_PREFIX}/lib/pkgconfig" \
CPPFLAGS="-I${SQLITE_PREFIX}/include" \
LDFLAGS="-L${SQLITE_PREFIX}/lib" \
LIBSQLITE3_CFLAGS="-I${SQLITE_PREFIX}/include" \
LIBSQLITE3_LIBS="-L${SQLITE_PREFIX}/lib -lsqlite3 -lm -lz" \
  ./configure --prefix="${PYTHON_PREFIX}" --with-ensurepip=install
make -j "${SLURM_CPUS_PER_TASK}"
make install

readonly SECOND_PYTHON="${PYTHON_PREFIX}/bin/python3.13"
[[ -x "${SECOND_PYTHON}" ]]
"${SECOND_PYTHON}" - <<'PY'
import _hashlib
import _ssl
import bz2
import ctypes
import lzma
import multiprocessing
import sqlite3
import zlib

assert sqlite3.sqlite_version == "3.46.1", sqlite3.sqlite_version
PY
"${SECOND_PYTHON}" -m pip install --quiet --no-compile \
  pip==26.2.1 setuptools==80.9.0 wheel==0.45.1

export PIP_CACHE_DIR="${PIP_CACHE}"
"${SECOND_PYTHON}" -m pip install --quiet --no-compile \
  --report "${PUBLIC_DOWNLOADS}/pip-torch-install-report.json" \
  --index-url https://download.pytorch.org/whl/cpu \
  "torch==${PYTORCH_VERSION}"
"${SECOND_PYTHON}" -m pip install --quiet --no-compile \
  --report "${PUBLIC_DOWNLOADS}/pip-deepparse-install-report.json" \
  "deepparse==${DEEPPARSE_VERSION}" "bpemb==${BPEMB_VERSION}"
"${SECOND_PYTHON}" -m pip check

"${SECOND_PYTHON}" -m pip download --quiet --no-deps \
  --dest "${PUBLIC_DOWNLOADS}" \
  "deepparse==${DEEPPARSE_VERSION}" "bpemb==${BPEMB_VERSION}"
readonly DEEPPARSE_WHEEL="${PUBLIC_DOWNLOADS}/deepparse-${DEEPPARSE_VERSION}-py3-none-any.whl"
readonly BPEMB_WHEEL="${PUBLIC_DOWNLOADS}/bpemb-${BPEMB_VERSION}-py3-none-any.whl"
printf '%s  %s\n' "${DEEPPARSE_WHEEL_SHA256}" "${DEEPPARSE_WHEEL}" | sha256sum --check --strict -
printf '%s  %s\n' "${BPEMB_WHEEL_SHA256}" "${BPEMB_WHEEL}" | sha256sum --check --strict -

readonly HF_SNAPSHOT="${CACHE_ROOT}/models--deepparse--bpemb-attention/snapshots/${MODEL_REVISION}"
readonly HF_REFS="${CACHE_ROOT}/models--deepparse--bpemb-attention/refs"
readonly BPEMB_CACHE="${CACHE_ROOT}/multi"
install -d -m 0700 "${HF_SNAPSHOT}" "${HF_REFS}" "${BPEMB_CACHE}"
curl --fail --location --retry 3 --output "${HF_SNAPSHOT}/config.json" "${MODEL_CONFIG_URL}"
curl --fail --location --retry 3 --output "${HF_SNAPSHOT}/model.safetensors" "${MODEL_WEIGHTS_URL}"
printf '%s  %s\n' "${MODEL_CONFIG_SHA256}" "${HF_SNAPSHOT}/config.json" | sha256sum --check --strict -
printf '%s  %s\n' "${MODEL_WEIGHTS_SHA256}" "${HF_SNAPSHOT}/model.safetensors" | sha256sum --check --strict -
printf '%s' "${MODEL_REVISION}" > "${HF_REFS}/main"
[[ "$(wc -c < "${HF_REFS}/main")" -eq 40 ]]
[[ "$(< "${HF_REFS}/main")" == "${MODEL_REVISION}" ]]

curl --fail --location --retry 3 --output \
  "${BPEMB_CACHE}/multi.wiki.bpe.vs100000.model" "${BPEMB_MODEL_URL}"
curl --fail --location --retry 3 --output \
  "${PUBLIC_DOWNLOADS}/multi.wiki.bpe.vs100000.d300.w2v.bin.tar.gz" \
  "${BPEMB_ARCHIVE_URL}"
printf '%s  %s\n' "${BPEMB_MODEL_SHA256}" \
  "${BPEMB_CACHE}/multi.wiki.bpe.vs100000.model" | sha256sum --check --strict -
printf '%s  %s\n' "${BPEMB_ARCHIVE_SHA256}" \
  "${PUBLIC_DOWNLOADS}/multi.wiki.bpe.vs100000.d300.w2v.bin.tar.gz" | \
  sha256sum --check --strict -
tar -xzf "${PUBLIC_DOWNLOADS}/multi.wiki.bpe.vs100000.d300.w2v.bin.tar.gz" \
  -C "${BPEMB_CACHE}"
printf '%s  %s\n' "${BPEMB_EMBEDDING_SHA256}" \
  "${BPEMB_CACHE}/multi.wiki.bpe.vs100000.d300.w2v.bin" | \
  sha256sum --check --strict -

"${SECOND_PYTHON}" -m pip freeze --all > "${PUBLIC_DOWNLOADS}/pip-freeze.txt"
"${SECOND_PYTHON}" -m pip list --format=json > "${PUBLIC_DOWNLOADS}/pip-list.json"
"${SECOND_PYTHON}" - <<'PY' > "${PUBLIC_DOWNLOADS}/runtime-identity.json"
import json
import platform
import sqlite3
import sys
import unicodedata

print(json.dumps({
    "implementation": platform.python_implementation(),
    "python": platform.python_version(),
    "platform": platform.platform(),
    "sqlite": sqlite3.sqlite_version,
    "executable": "<relocatable-private-bundle>/runtime/bin/python3.13",
    "unicode": unicodedata.unidata_version,
    "byteorder": sys.byteorder,
}, sort_keys=True, indent=2))
PY

export HF_HOME="${CACHE_ROOT}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_HUB_DISABLE_TELEMETRY=1
export DO_NOT_TRACK=1
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
"${SECOND_PYTHON}" - <<'PY'
import os

from huggingface_hub import try_to_load_from_cache

for filename in ("config.json", "model.safetensors"):
    resolved = try_to_load_from_cache(
        "deepparse/bpemb-attention",
        filename,
        cache_dir=os.environ["HF_HOME"],
        revision="main",
    )
    assert isinstance(resolved, str), filename
print("public_huggingface_cache_binding=PASS")
PY
"${SECOND_PYTHON}" - <<'PY'
import random
import socket

import numpy
import torch

for required_module in (
    "bpemb",
    "cloudpathlib",
    "deepparse",
    "gensim",
    "huggingface_hub",
    "pandas",
    "poutyne",
    "pymagnitudelight",
    "requests",
    "scipy",
    "sentencepiece",
    "tqdm",
    "transformers",
    "urllib3",
):
    __import__(required_module)

network_attempts = 0

def deny_network(*args, **kwargs):
    global network_attempts
    network_attempts += 1
    raise AssertionError("NETWORK_ACCESS_DENIED_DURING_OFFLINE_SMOKE")

socket.create_connection = deny_network
socket.socket.connect = deny_network
random.seed(0)
numpy.random.seed(0)
torch.manual_seed(0)
torch.set_num_threads(1)
torch.set_num_interop_threads(1)
torch.use_deterministic_algorithms(True)

from deepparse.parser import AddressParser

parser = AddressParser(
    model_type="bpemb",
    attention_mechanism=True,
    device="cpu",
    verbose=False,
    cache_dir=__import__("os").environ["HF_HOME"],
    offline=True,
)
assert parser.version == "4af74dad1d547804dfc2de8f40fb23fbbec5b811"
candidate = "10 synthetic example road"
first = parser(
    candidate,
    with_prob=True,
    batch_size=1,
    num_workers=0,
    with_hyphen_split=False,
    pre_processors=[],
)
second = parser(
    candidate,
    with_prob=True,
    batch_size=1,
    num_workers=0,
    with_hyphen_split=False,
    pre_processors=[],
)
assert first.raw_address == candidate
assert first.address_parsed_components == second.address_parsed_components
assert parser.pre_processors.apply([candidate]) == [candidate]
assert first.address_parsed_components
assert all(
    isinstance(item, tuple)
    and len(item) == 2
    and isinstance(item[0], str)
    and isinstance(item[1], tuple)
    and len(item[1]) == 2
    and isinstance(item[1][0], str)
    and isinstance(item[1][1], float)
    for item in first.address_parsed_components
)
assert network_attempts == 0
print("public_offline_smoke=PASS")
print(f"public_offline_smoke_components={len(first.address_parsed_components)}")
print("public_offline_network_attempts=0")
PY

readonly OUTPUT_PARENT="$(dirname "${OUTPUT_DIRECTORY}")"
readonly OUTPUT_NAME="$(basename "${OUTPUT_DIRECTORY}")"
readonly STAGING_DIRECTORY="${OUTPUT_PARENT}/.${OUTPUT_NAME}.${SLURM_JOB_ID}.in_progress"
[[ ! -e "${STAGING_DIRECTORY}" ]]

find "${PYTHON_PREFIX}" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
find "${PYTHON_PREFIX}" -depth -type d -name __pycache__ -empty -delete
install -d -m 0700 "${OUTPUT_PARENT}" "${STAGING_DIRECTORY}"
install -d -m 0700 \
  "${STAGING_DIRECTORY}/runtime" \
  "${STAGING_DIRECTORY}/cache" \
  "${STAGING_DIRECTORY}/sources" \
  "${STAGING_DIRECTORY}/licenses" \
  "${STAGING_DIRECTORY}/metadata"
cp -RL "${PYTHON_PREFIX}/." "${STAGING_DIRECTORY}/runtime/"
cp -RL "${CACHE_ROOT}/." "${STAGING_DIRECTORY}/cache/"
cp -R "${PUBLIC_DOWNLOADS}/." "${STAGING_DIRECTORY}/sources/"
install -m 0600 "${PYTHON_ARCHIVE}" \
  "${STAGING_DIRECTORY}/sources/${PYTHON_ARCHIVE_NAME}"
install -m 0600 "${PYTHON_SOURCE}/LICENSE" \
  "${STAGING_DIRECTORY}/licenses/CPython-LICENSE"
sed -n '29,39p' "${SQLITE_SOURCE}/sqlite3.c" > \
  "${STAGING_DIRECTORY}/licenses/SQLite-PUBLIC-DOMAIN-NOTICE"
unzip -p "${DEEPPARSE_WHEEL}" deepparse-0.10.0.dist-info/licenses/LICENSE > \
  "${STAGING_DIRECTORY}/licenses/DeepParse-LICENSE"
unzip -p "${BPEMB_WHEEL}" bpemb-0.3.6.dist-info/LICENSE > \
  "${STAGING_DIRECTORY}/licenses/BPEmb-LICENSE"
curl --fail --location --retry 3 --output \
  "${STAGING_DIRECTORY}/licenses/DeepParse-model-card.md" \
  "https://huggingface.co/deepparse/bpemb-attention/raw/${MODEL_REVISION}/README.md"
cp "${PUBLIC_DOWNLOADS}/runtime-identity.json" \
  "${STAGING_DIRECTORY}/metadata/runtime-identity.json"

if find "${STAGING_DIRECTORY}" -type l -print -quit | grep -q .; then
  echo "STAGE07_SECOND_PARSER_BUNDLE_SYMLINK_PROHIBITED" >&2
  exit 1
fi
if find "${STAGING_DIRECTORY}" \( -name __pycache__ -o -name '*.pyc' -o -name '*.pyo' \) \
  -print -quit | grep -q .; then
  echo "STAGE07_SECOND_PARSER_BYTECODE_CACHE_PROHIBITED" >&2
  exit 1
fi
find "${STAGING_DIRECTORY}" -type d -exec chmod 0700 {} +
find "${STAGING_DIRECTORY}" -type f -exec chmod 0600 {} +
find "${STAGING_DIRECTORY}/runtime/bin" -maxdepth 1 -type f -exec chmod 0700 {} +

readonly COMPILER_IDENTITY="$(printf '%s; %s' \
  "$(gcc --version | head -n 1)" "$(make --version | head -n 1)")"
readonly GLIBC_IDENTITY="$(getconf GNU_LIBC_VERSION)"
export PYTHONPATH="${INTEGRATION_ROOT}/src"
export SAFE_EXECUTION_SITE=goethe-nhr
readonly PUBLISH_ARGV_HELPER="${INTEGRATION_ROOT}/cluster/goethe_nhr/stage07_second_parser_bundle_publish_argv.sh"
source "${PUBLISH_ARGV_HELPER}"
stage07_second_parser_bundle_publish_argv \
  "${BASE_PYTHON}" \
  "${STAGING_DIRECTORY}" \
  "${OUTPUT_DIRECTORY}" \
  "${ACTUAL_COMMIT}" \
  "${COMPILER_IDENTITY}" \
  "${GLIBC_IDENTITY}" \
  "${PYTHON_CONFIGURE_ARGUMENTS[@]}"
readonly PUBLISH_OUTPUT="$("${STAGE07_SECOND_PARSER_PUBLISH_ARGV[@]}")"
printf '%s\n' "${PUBLISH_OUTPUT}"
readonly BUNDLE_FINGERPRINT="$(printf '%s\n' "${PUBLISH_OUTPUT}" | \
  awk -F= '$1 == "stage07_second_parser_bundle_fingerprint" {print $2}')"
[[ "${BUNDLE_FINGERPRINT}" =~ ^[0-9a-f]{64}$ ]]

"${BASE_PYTHON}" \
  -m safe_geocoding_pipeline.preprocessing.stage07_second_parser_bundle_cli validate \
  --output-directory "${OUTPUT_DIRECTORY}" \
  --expected-second-parser-bundle-fingerprint "${BUNDLE_FINGERPRINT}"

readonly PUBLISHED_PYTHON="${OUTPUT_DIRECTORY}/runtime/bin/python3.13"
[[ -x "${PUBLISHED_PYTHON}" ]]
export HF_HOME="${OUTPUT_DIRECTORY}/cache"
"${PUBLISHED_PYTHON}" - <<'PY'
import socket
import sqlite3

def deny_network(*args, **kwargs):
    raise AssertionError("NETWORK_ACCESS_DENIED_DURING_PUBLISHED_SMOKE")

socket.create_connection = deny_network
socket.socket.connect = deny_network
assert sqlite3.sqlite_version == "3.46.1", sqlite3.sqlite_version
from deepparse.parser import AddressParser

parser = AddressParser(
    model_type="bpemb",
    attention_mechanism=True,
    device="cpu",
    verbose=False,
    cache_dir=__import__("os").environ["HF_HOME"],
    offline=True,
)
parsed = parser("20 published synthetic road", with_prob=True, pre_processors=[])
assert parsed.raw_address == "20 published synthetic road"
assert parsed.address_parsed_components
print("published_offline_smoke=PASS")
PY

echo "public_assets_only=true"
echo "protected_inputs_opened=false"
echo "STAGE07_SECOND_PARSER_BUNDLE_BUILD_PASS"
