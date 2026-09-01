#!/usr/bin/env bash

# Bind every mutable DeepParse runtime/cache location to a fresh owner-only
# directory outside the immutable parser/model bundle. The model cache is a
# read-only asset store supplied explicitly to DeepParse, not a mutable cache.
stage07_second_parser_bind_runtime_state() {
  if [[ "$#" -ne 2 ]]; then
    echo "STAGE07_SECOND_PARSER_RUNTIME_STATE_ARGUMENTS_INVALID" >&2
    return 2
  fi

  local runtime_root
  local runtime_parent
  local model_cache
  local bundle_root
  runtime_parent="$(cd "$(dirname -- "$1")" && pwd -P)"
  runtime_root="${runtime_parent}/$(basename -- "$1")"
  model_cache="$(cd "$2" && pwd -P)"
  bundle_root="$(cd "${model_cache}/.." && pwd -P)"
  if [[ -e "${runtime_root}" || "${runtime_root}" == "${bundle_root}" || \
    "${runtime_root}" == "${bundle_root}"/* || \
    "${bundle_root}" == "${runtime_root}"/* ]]; then
    echo "STAGE07_SECOND_PARSER_RUNTIME_STATE_TOPOLOGY_INVALID" >&2
    return 1
  fi

  install -d -m 0700 \
    "${runtime_root}" \
    "${runtime_root}/home" \
    "${runtime_root}/tmp" \
    "${runtime_root}/pycache" \
    "${runtime_root}/xdg-cache" \
    "${runtime_root}/xdg-config" \
    "${runtime_root}/xdg-data" \
    "${runtime_root}/xdg-state" \
    "${runtime_root}/hf" \
    "${runtime_root}/hf/hub" \
    "${runtime_root}/hf/assets" \
    "${runtime_root}/hf/xet" \
    "${runtime_root}/transformers" \
    "${runtime_root}/torch" \
    "${runtime_root}/torch-extensions"

  export STAGE07_SECOND_PARSER_RUNTIME_ROOT="${runtime_root}"
  export HOME="${runtime_root}/home"
  export TMPDIR="${runtime_root}/tmp"
  export TMP="${runtime_root}/tmp"
  export TEMP="${runtime_root}/tmp"
  export XDG_CACHE_HOME="${runtime_root}/xdg-cache"
  export XDG_CONFIG_HOME="${runtime_root}/xdg-config"
  export XDG_DATA_HOME="${runtime_root}/xdg-data"
  export XDG_STATE_HOME="${runtime_root}/xdg-state"
  export HF_HOME="${runtime_root}/hf"
  export HF_HUB_CACHE="${runtime_root}/hf/hub"
  export HUGGINGFACE_HUB_CACHE="${runtime_root}/hf/hub"
  export HF_ASSETS_CACHE="${runtime_root}/hf/assets"
  export HF_XET_CACHE="${runtime_root}/hf/xet"
  export TRANSFORMERS_CACHE="${runtime_root}/transformers"
  export TORCH_HOME="${runtime_root}/torch"
  export TORCH_EXTENSIONS_DIR="${runtime_root}/torch-extensions"
  export PYTHONPYCACHEPREFIX="${runtime_root}/pycache"
  export STAGE07_SECOND_PARSER_MODEL_CACHE="${model_cache}"

  export PYTHONDONTWRITEBYTECODE=1
  export HF_HUB_OFFLINE=1
  export TRANSFORMERS_OFFLINE=1
  export HF_HUB_DISABLE_TELEMETRY=1
  export DO_NOT_TRACK=1
}
