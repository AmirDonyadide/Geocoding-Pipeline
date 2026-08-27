#!/usr/bin/env bash
set -euo pipefail

# Controlled-data transfer only. Source code and Git metadata reach Goethe-NHR
# through the shared GitHub repository, never through this rsync helper.

readonly REMOTE_HOST="${GOETHE_NHR_HOST:-goethe}"
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
    echo "Usage: $0 [--dry-run]  # sync only approved controlled data"
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

cd "${repo_root}"

sync_commit="$(git rev-parse --verify HEAD)"
if ! git cat-file -e "${sync_commit}^{commit}"; then
  echo "Current Git commit is not reconstructable: ${sync_commit}" >&2
  exit 1
fi
if [[ "${dry_run}" == false ]] && [[ -n "$(git status --porcelain)" ]]; then
  echo "The Git worktree must be clean before a real controlled-data sync." >&2
  exit 1
fi

# The completed Phase 2 run is intentionally allowlisted at file level. Its
# .in_progress, _work, SQLite, DuckDB spill, and temporary state are excluded.
phase02_files=(
  "${PHASE02_RUN}/_SUCCESS.json"
  "${PHASE02_RUN}/dataset_manifest.json"
)
phase02_shards=("${PHASE02_RUN}"/data/*.parquet)
if [[ "${#phase02_shards[@]}" -ne 206 ]]; then
  echo "Expected exactly 206 authoritative Phase 2 Parquet shards; found ${#phase02_shards[@]}." >&2
  exit 1
fi
phase02_files+=("${phase02_shards[@]}")

required_paths=(
  "${phase02_files[@]}"
  "${PHASE01_ANOMALIES}"
)
for required_path in "${required_paths[@]}"; do
  if [[ ! -e "${required_path}" ]]; then
    echo "Required sync input is absent: ${required_path}" >&2
    exit 1
  fi
done

rsync_options=(
  -a
  --relative
  --itemize-changes
  --exclude=.DS_Store
  --exclude=__pycache__/
  "--exclude=*.pyc"
  "--exclude=*.pyo"
  "--exclude=*.egg-info/"
  --exclude=.pytest_cache/
  --exclude=.mypy_cache/
  --exclude=.ruff_cache/
  --exclude=.agents/
  --exclude=logs/
  --exclude=.venv/
  --exclude=.venv-goethe-nhr/
  --exclude=.in_progress/
  --exclude=_work/
  --exclude=candidate_state.sqlite3
  --exclude=phase02_state.sqlite3
  "--exclude=*duckdb_spill*/"
  --exclude=.env
  "--exclude=.env.*"
  "--exclude=*.pem"
  "--exclude=*.key"
)
if [[ "${rsync_supports_protect_args}" == true ]]; then
  rsync_options+=(--protect-args)
fi
if [[ "${dry_run}" == true ]]; then
  rsync_options+=(--dry-run)
  echo "DRY RUN: no files will be transferred."
else
  ssh "${REMOTE_HOST}" \
    "test -d '${REMOTE_ROOT}/.git' || { echo 'CLUSTER_GIT_CLONE_REQUIRED' >&2; exit 1; }; umask 077 && mkdir -p '${REMOTE_ROOT}/reports/generated/phase01/phase01_20260810T151626Z_7df9bc8f' '${REMOTE_ROOT}/staging/controlled/phase02_v1/runs'"
fi

echo "code sync=GITHUB_ONLY"
echo "local Git commit context=${sync_commit}"
echo "Phase 2 Parquet shards=${#phase02_shards[@]}"
echo "Source code and Git metadata transferred=false"

# Immutable completed Phase 2 products only.
"${rsync_executable}" "${rsync_options[@]}" \
  "${phase02_files[@]}" \
  "${REMOTE_HOST}:${REMOTE_ROOT}/"

"${rsync_executable}" "${rsync_options[@]}" \
  "${PHASE01_ANOMALIES}" \
  "${REMOTE_HOST}:${REMOTE_ROOT}/"

echo "Controlled-data sync plan completed for ${REMOTE_HOST}:${REMOTE_ROOT}"
