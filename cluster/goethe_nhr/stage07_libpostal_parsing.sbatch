#!/usr/bin/env bash
#SBATCH --job-name=safe-stage07-parse
#SBATCH --partition=general1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=180G
#SBATCH --time=24:00:00
#SBATCH --output=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.out
#SBATCH --error=/work/footprint/donyadidegan/safe_geocoding_pipeline/logs/slurm/%x_%j.err

set -euo pipefail
umask 077

: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${STAGE07_GIT_COMMIT:?exact pushed Stage 7 implementation SHA is required}"
: "${STAGE07_INTEGRATION_ROOT:?exact detached Stage 7 worktree is required}"
: "${STAGE07_RUNTIME_ROOT:?new owner-only runtime root is required}"
: "${STAGE07_STAGE05_ROOT:?accepted Stage 5 DEVELOPMENT root is required}"
: "${STAGE07_STAGE06_ROOT:?accepted Stage 6 DEVELOPMENT root is required}"
: "${STAGE07_PARSER_BUNDLE_ROOT:?frozen parser bundle root is required}"
: "${STAGE07_PARSER_BUNDLE_FINGERPRINT:?frozen parser bundle fingerprint is required}"
: "${STAGE07_INPUT_BINDING:?new Stage 7 input binding path is required}"
: "${STAGE07_OUTPUT_DIRECTORY:?new immutable Stage 7 output path is required}"

readonly DATA_ROOT="$(realpath -e -- /work/footprint/donyadidegan/safe_geocoding_pipeline)"
readonly INTEGRATION_ROOT="$(realpath -e -- "${STAGE07_INTEGRATION_ROOT}")"
readonly RUNTIME_ROOT="$(realpath -m -- "${STAGE07_RUNTIME_ROOT}")"
readonly STAGE05_ROOT="$(realpath -e -- "${STAGE07_STAGE05_ROOT}")"
readonly STAGE06_ROOT="$(realpath -e -- "${STAGE07_STAGE06_ROOT}")"
readonly PARSER_BUNDLE_ROOT="$(realpath -e -- "${STAGE07_PARSER_BUNDLE_ROOT}")"
readonly INPUT_BINDING="$(realpath -m -- "${STAGE07_INPUT_BINDING}")"
readonly OUTPUT_DIRECTORY="$(realpath -m -- "${STAGE07_OUTPUT_DIRECTORY}")"

for controlled_path in "${INTEGRATION_ROOT}" "${RUNTIME_ROOT}" "${STAGE05_ROOT}" \
  "${STAGE06_ROOT}" "${PARSER_BUNDLE_ROOT}" "${INPUT_BINDING}" "${OUTPUT_DIRECTORY}"; do
  [[ "${controlled_path}" == "${DATA_ROOT}"/* ]] || { echo "STAGE07_CONTROLLED_PATH_REQUIRED" >&2; exit 1; }
  [[ "${controlled_path,,}" != *holdout* ]] || { echo "HOLDOUT_ACCESS_PROHIBITED" >&2; exit 1; }
done

cd "${INTEGRATION_ROOT}"
[[ "$(git rev-parse HEAD)" == "${STAGE07_GIT_COMMIT}" ]] || { echo "STAGE07_GIT_COMMIT_MISMATCH" >&2; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo "STAGE07_WORKTREE_NOT_CLEAN" >&2; exit 1; }
[[ "$(git symbolic-ref -q HEAD || true)" == "" ]] || { echo "STAGE07_WORKTREE_NOT_DETACHED" >&2; exit 1; }

STAGE07_INTEGRATION_ROOT="${INTEGRATION_ROOT}" \
STAGE07_RUNTIME_ROOT="${RUNTIME_ROOT}" \
STAGE07_PARSER_BUNDLE_ROOT="${PARSER_BUNDLE_ROOT}" \
STAGE07_PARSER_BUNDLE_FINGERPRINT="${STAGE07_PARSER_BUNDLE_FINGERPRINT}" \
  bash "${INTEGRATION_ROOT}/cluster/goethe_nhr/stage07_bootstrap_env.sh"

readonly PYTHON="${RUNTIME_ROOT}/venv/bin/python"
export SAFE_EXECUTION_SITE=goethe-nhr
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1
export PYTHONHASHSEED=0
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export LIBPOSTAL_DATA_DIR="${PARSER_BUNDLE_ROOT}/data/libpostal"
export LD_LIBRARY_PATH="${PARSER_BUNDLE_ROOT}/lib"
export PYTHONPATH="${PARSER_BUNDLE_ROOT}/python:${INTEGRATION_ROOT}/src"

echo "job_id=${SLURM_JOB_ID}"
echo "git_commit=${STAGE07_GIT_COMMIT}"
echo "parser_bundle_fingerprint=${STAGE07_PARSER_BUNDLE_FINGERPRINT}"
echo "requested_memory_gib=180"
echo "parser_concurrency=one_synchronous_supervised_child"
echo "per_candidate_address_space_limit=none"
echo "per_candidate_timeout=none"
echo "protected_parsing_network_calls=false"

binding_sha="$("${PYTHON}" -m safe_geocoding_pipeline.preprocessing.stage07_cli \
  create-input-binding \
  --parser-bundle-directory "${PARSER_BUNDLE_ROOT}" \
  --expected-parser-bundle-fingerprint "${STAGE07_PARSER_BUNDLE_FINGERPRINT}" \
  --output "${INPUT_BINDING}" | awk -F= '$1 == "stage07_input_binding_sha256" {print $2}')"
[[ -n "${binding_sha}" ]] || { echo "STAGE07_BINDING_CREATION_FAILED" >&2; exit 1; }

"${PYTHON}" -m safe_geocoding_pipeline.preprocessing.stage07_cli materialize \
  --stage05-output-directory "${STAGE05_ROOT}" \
  --stage06-output-directory "${STAGE06_ROOT}" \
  --input-binding "${INPUT_BINDING}" \
  --expected-input-binding-sha256 "${binding_sha}" \
  --parser-bundle-directory "${PARSER_BUNDLE_ROOT}" \
  --expected-parser-bundle-fingerprint "${STAGE07_PARSER_BUNDLE_FINGERPRINT}" \
  --output-directory "${OUTPUT_DIRECTORY}" \
  --execution-git-sha "${STAGE07_GIT_COMMIT}" \
  --input-batch-rows 64 \
  --output-batch-rows 64 \
  --target-batch-bytes $((128 * 1024 * 1024)) \
  --output-shard-rows 4096

echo "STAGE07_AUTHORITATIVE_DEVELOPMENT_COMPLETE"
