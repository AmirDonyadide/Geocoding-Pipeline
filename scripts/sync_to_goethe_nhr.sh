#!/usr/bin/env bash
set -euo pipefail

readonly REMOTE_HOST="${GOETHE_NHR_HOST:-donyadidegan@goethe.hhlr-gu.de}"
readonly REMOTE_ROOT="${GOETHE_NHR_REPO:-/work/footprint/donyadidegan/safe_geocoding_pipeline}"
readonly PHASE02_RUN="staging/controlled/phase02_v1/runs/phase02_20260810T173851Z_1349152b"
readonly PHASE01_RUN="reports/generated/phase01/phase01_20260810T151626Z_7df9bc8f"
readonly PHASE01_ANOMALIES="${PHASE01_RUN}/phase01_anomalies.csv.gz"
readonly REQUIRED_BASELINE_COMMIT="648080ff93eb82566368286303b6fd3069d6a2f7"

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

cd "${repo_root}"

sync_commit="$(git rev-parse --verify HEAD)"
if ! git cat-file -e "${sync_commit}^{commit}"; then
  echo "Current Git commit is not reconstructable: ${sync_commit}" >&2
  exit 1
fi
if ! git merge-base --is-ancestor "${REQUIRED_BASELINE_COMMIT}" "${sync_commit}"; then
  echo "Required sync baseline is not an ancestor of HEAD: ${REQUIRED_BASELINE_COMMIT}" >&2
  exit 1
fi
if [[ "${dry_run}" == false ]] && ! git diff-index --quiet HEAD --; then
  echo "Tracked working-tree changes must be committed before a real sync." >&2
  exit 1
fi

is_prohibited_repository_path() {
  case "$1" in
    .DS_Store|*/.DS_Store|__pycache__/*|*/__pycache__/*|*.pyc|*.pyo|*.egg-info|*.egg-info/*) return 0 ;;
    .pytest_cache/*|*/.pytest_cache/*|.mypy_cache/*|*/.mypy_cache/*) return 0 ;;
    .ruff_cache/*|*/.ruff_cache/*|.agents/*|*/.agents/*|logs/*|*/logs/*) return 0 ;;
    .venv/*|*/.venv/*|.venv-goethe-nhr/*|*/.venv-goethe-nhr/*) return 0 ;;
    derived/controlled/*|reports/generated/*|staging/controlled/*) return 0 ;;
    csv_files/*|parquet_files/*|.env|*/.env|.env.*|*/.env.*|*.pem|*.key) return 0 ;;
    *) return 1 ;;
  esac
}

tracked_files=()
while IFS= read -r -d '' tracked_file; do
  if is_prohibited_repository_path "${tracked_file}"; then
    continue
  fi
  tracked_files+=("${tracked_file}")
done < <(git ls-files -z)
if [[ "${#tracked_files[@]}" -eq 0 ]]; then
  echo "No Git-tracked project files were discovered." >&2
  exit 1
fi

# Ordinary Git metadata required to reconstruct and validate the current branch.
# Codex refs, logs, checkpoints, hooks, and other agent-local state are omitted.
git_metadata=(
  .git/HEAD
  .git/config
  .git/index
  .git/objects
  .git/refs/heads
)
for optional_git_metadata in .git/packed-refs .git/shallow; do
  if [[ -e "${optional_git_metadata}" ]]; then
    git_metadata+=("${optional_git_metadata}")
  fi
done

if git config --local --name-only --get-regexp '(^|\.)http\..*\.extraheader$|(^|\.)(password|token)$' >/dev/null 2>&1; then
  echo "Potential secret-bearing local Git configuration must not be synchronized." >&2
  exit 1
fi
origin_url="$(git config --local --get remote.origin.url 2>/dev/null || true)"
if [[ "${origin_url}" =~ ^https?://[^/@]+@ ]]; then
  echo "Credential-like user information in the Git remote URL must not be synchronized." >&2
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
  "${git_metadata[@]}"
  "${tracked_files[@]}"
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
  --exclude=.git/refs/codex/
  --exclude=refs/codex/
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
    "umask 077 && mkdir -p '${REMOTE_ROOT}' '${REMOTE_ROOT}/reports/generated/phase01/phase01_20260810T151626Z_7df9bc8f' '${REMOTE_ROOT}/staging/controlled/phase02_v1/runs'"
fi

echo "git commit=${sync_commit}"
echo "Git-tracked project files=${#tracked_files[@]}"
echo "Phase 2 Parquet shards=${#phase02_shards[@]}"

# Minimal ordinary Git database metadata. There is deliberately no --delete.
"${rsync_executable}" "${rsync_options[@]}" \
  "${git_metadata[@]}" \
  "${REMOTE_HOST}:${REMOTE_ROOT}/"

# Git-tracked project files only. Untracked/ignored caches, .agents, logs,
# virtual environments, generated pilot state, secrets, and raw CSVs cannot
# hitchhike with broad source-directory recursion.
"${rsync_executable}" "${rsync_options[@]}" \
  "${tracked_files[@]}" \
  "${REMOTE_HOST}:${REMOTE_ROOT}/"

# Immutable completed Phase 2 products only.
"${rsync_executable}" "${rsync_options[@]}" \
  "${phase02_files[@]}" \
  "${REMOTE_HOST}:${REMOTE_ROOT}/"

"${rsync_executable}" "${rsync_options[@]}" \
  "${PHASE01_ANOMALIES}" \
  "${REMOTE_HOST}:${REMOTE_ROOT}/"

echo "Sync plan completed for ${REMOTE_HOST}:${REMOTE_ROOT}"
