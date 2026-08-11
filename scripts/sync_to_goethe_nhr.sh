#!/usr/bin/env bash
set -euo pipefail

readonly REMOTE_HOST="${GOETHE_NHR_HOST:-donyadidegan@goethe.hhlr-gu.de}"
readonly REMOTE_ROOT="${GOETHE_NHR_REPO:-/work/footprint/donyadidegan/safe_geocoding_pipeline}"
readonly PHASE02_RUN="staging/controlled/phase02_v1/runs/phase02_20260810T173851Z_1349152b"
readonly PHASE01_RUN="reports/generated/phase01/phase01_20260810T151626Z_7df9bc8f"
readonly PHASE01_ANOMALIES="${PHASE01_RUN}/phase01_anomalies.csv.gz"

if [[ ! "${REMOTE_HOST}" =~ ^[A-Za-z0-9._@-]+$ ]]; then
  echo "Unsafe Goethe-NHR host value." >&2
  exit 2
fi
if [[ ! "${REMOTE_ROOT}" =~ ^/[A-Za-z0-9._/-]+$ ]]; then
  echo "Unsafe Goethe-NHR repository path." >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
dry_run=false
case "${1:-}" in
  "") ;;
  --dry-run) dry_run=true ;;
  --help|-h)
    echo "Usage: $0 [--dry-run]"
    exit 0
    ;;
  *)
    echo "Unknown argument: $1" >&2
    exit 2
    ;;
esac

select_rsync_executable() {
  local candidate path_rsync
  local candidates=()
  if [[ -n "${SAFE_RSYNC_EXECUTABLE:-}" ]]; then
    candidates+=("${SAFE_RSYNC_EXECUTABLE}")
  else
    [[ -n "${HOMEBREW_PREFIX:-}" ]] && candidates+=("${HOMEBREW_PREFIX}/bin/rsync")
    candidates+=(/opt/homebrew/bin/rsync /usr/local/bin/rsync)
    path_rsync="$(command -v rsync 2>/dev/null || true)"
    [[ -n "${path_rsync}" ]] && candidates+=("${path_rsync}")
  fi
  for candidate in "${candidates[@]}"; do
    if [[ -x "${candidate}" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done
  echo "No executable rsync was found." >&2
  return 1
}

rsync_executable="$(select_rsync_executable)"
if ! rsync_version_output="$("${rsync_executable}" --version 2>&1)"; then
  echo "Selected rsync cannot report its version: ${rsync_executable}" >&2
  exit 1
fi
rsync_version="${rsync_version_output%%$'\n'*}"
rsync_supports_protect_args=false
if "${rsync_executable}" --protect-args --version >/dev/null 2>&1; then
  rsync_supports_protect_args=true
fi

echo "rsync executable=${rsync_executable}"
echo "rsync version=${rsync_version}"
echo "dry-run=${dry_run}"
echo "rsync protect-args=${rsync_supports_protect_args}"

required_paths=(
  .git
  .gitattributes
  .gitignore
  AGENTS.md
  README.md
  cluster
  docs
  pyproject.toml
  scripts
  src
  tests
  "${PHASE02_RUN}"
  "${PHASE01_ANOMALIES}"
)
for path in "${required_paths[@]}"; do
  if [[ ! -e "${repo_root}/${path}" ]]; then
    echo "Required sync input is absent: ${path}" >&2
    exit 1
  fi
done

rsync_options=(-a --relative --itemize-changes)
if [[ "${rsync_supports_protect_args}" == true ]]; then
  rsync_options+=(--protect-args)
fi
if [[ "${dry_run}" == true ]]; then
  rsync_options+=(--dry-run)
  echo "DRY RUN: no files will be transferred."
else
  ssh "${REMOTE_HOST}" \
    "umask 077 && mkdir -p '${REMOTE_ROOT}' '${REMOTE_ROOT}/reports/generated/phase01/phase01_20260810T151626Z_7df9bc8f' '${REMOTE_ROOT}/staging/controlled/phase02_v1/runs'"
fi

cd "${repo_root}"

# The allowlist intentionally excludes .venv*, raw CSVs, all Phase 3 derived
# state (including the paused local candidate database), caches, logs, secrets,
# notebooks, and historical parquet_files. There is deliberately no --delete.
"${rsync_executable}" "${rsync_options[@]}" \
  .git .gitattributes .gitignore AGENTS.md README.md cluster docs pyproject.toml scripts src tests \
  "${REMOTE_HOST}:${REMOTE_ROOT}/"

"${rsync_executable}" "${rsync_options[@]}" \
  "${PHASE02_RUN}" \
  "${REMOTE_HOST}:${REMOTE_ROOT}/"

"${rsync_executable}" "${rsync_options[@]}" \
  "${PHASE01_ANOMALIES}" \
  "${REMOTE_HOST}:${REMOTE_ROOT}/"

echo "Sync plan completed for ${REMOTE_HOST}:${REMOTE_ROOT}"
