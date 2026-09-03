#!/usr/bin/env bash
set -euo pipefail
umask 077

: "${BENCHMARK_SOURCE_ROOT:?set the exact protected Mac source root}"
: "${BENCHMARK_POPULATION_SCOPE:?set the exact owner-only population scope}"
: "${BENCHMARK_POPULATION_SCOPE_SHA256:?set the authorized scope SHA-256}"
: "${BENCHMARK_REMOTE_SOURCE_ROOT:?set a new controlled Goethe source-snapshot path}"
: "${BENCHMARK_REMOTE_SCOPE_PATH:?set the controlled Goethe scope path}"

readonly REMOTE_HOST="${GOETHE_NHR_HOST:-goethe}"
readonly REMOTE_REPOSITORY="${GOETHE_NHR_REPO:-/work/footprint/donyadidegan/safe_geocoding_pipeline}"
readonly RSYNC_REMOTE_SHELL="ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=120"
readonly REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly TEMPORARY_DIRECTORY="$(mktemp -d)"
trap 'rm -rf -- "${TEMPORARY_DIRECTORY}"' EXIT
readonly FILE_LIST="${TEMPORARY_DIRECTORY}/authorized-files.nul"

[[ "${REMOTE_HOST}" =~ ^[A-Za-z0-9._@-]+$ ]] || {
  echo "UNSAFE_REMOTE_HOST" >&2
  exit 2
}
[[ "${BENCHMARK_POPULATION_SCOPE_SHA256}" =~ ^[0-9a-f]{64}$ ]] || {
  echo "INVALID_POPULATION_SCOPE_SHA256" >&2
  exit 2
}
[[ "${BENCHMARK_REMOTE_SOURCE_ROOT}" =~ ^/work/footprint/donyadidegan/safe_geocoding_pipeline/source_snapshots/[A-Za-z0-9._/-]+$ ]] || {
  echo "UNSAFE_REMOTE_SOURCE_ROOT" >&2
  exit 2
}
[[ "${BENCHMARK_REMOTE_SCOPE_PATH}" =~ ^/work/footprint/donyadidegan/safe_geocoding_pipeline/source_snapshots/[A-Za-z0-9._/-]+\.json$ ]] || {
  echo "UNSAFE_REMOTE_SCOPE_PATH" >&2
  exit 2
}

select_rsync_executable() {
  local candidate path_rsync
  local candidates=()
  [[ -n "${SAFE_RSYNC_EXECUTABLE:-}" ]] && candidates+=("${SAFE_RSYNC_EXECUTABLE}")
  candidates+=(/opt/homebrew/bin/rsync /usr/local/bin/rsync)
  path_rsync="$(command -v rsync 2>/dev/null || true)"
  [[ -n "${path_rsync}" ]] && candidates+=("${path_rsync}")
  for candidate in "${candidates[@]}"; do
    if [[ -x "${candidate}" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done
  echo "RSYNC_NOT_AVAILABLE" >&2
  return 1
}

readonly RSYNC="$(select_rsync_executable)"
"${RSYNC}" --protect-args --version >/dev/null 2>&1 || {
  echo "MODERN_RSYNC_WITH_PROTECT_ARGS_REQUIRED" >&2
  exit 1
}

cd "${REPOSITORY_ROOT}"
PYTHONPATH=src python3 - \
  "${BENCHMARK_SOURCE_ROOT}" \
  "${BENCHMARK_POPULATION_SCOPE}" \
  "${BENCHMARK_POPULATION_SCOPE_SHA256}" \
  "${FILE_LIST}" <<'PY'
import os
import sys
from pathlib import Path

from safe_geocoding_pipeline.preprocessing.stages.s00_config import DEFAULT_PARSER_FIELD_LIMIT_CHARS
from safe_geocoding_pipeline.preprocessing.stages.s00_population import load_population_scope

source_root = Path(sys.argv[1])
scope_path = Path(sys.argv[2])
scope = load_population_scope(
    scope_path,
    expected_sha256=sys.argv[3],
    expected_parser_field_limit_chars=DEFAULT_PARSER_FIELD_LIMIT_CHARS,
)
observed = []
for entry in os.scandir(source_root):
    if not entry.name.lower().endswith(".csv"):
        continue
    if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
        raise SystemExit("UNSAFE_SOURCE_CSV_ENTRY")
    observed.append(entry.name)
observed.sort()
if tuple(observed) != scope.relative_paths:
    raise SystemExit("SOURCE_SCOPE_MEMBERSHIP_MISMATCH")
with Path(sys.argv[4]).open("wb") as stream:
    for relative_path in scope.relative_paths:
        stream.write(os.fsencode(relative_path))
        stream.write(b"\0")
print(f"authorized_source_files={len(scope.relative_paths)}")
PY

ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=120 "${REMOTE_HOST}" "set -eu; umask 077; \
  mkdir -p '$(dirname "${BENCHMARK_REMOTE_SOURCE_ROOT}")' '$(dirname "${BENCHMARK_REMOTE_SCOPE_PATH}")'; \
  if test -e '${BENCHMARK_REMOTE_SOURCE_ROOT}'; then \
    test -d '${BENCHMARK_REMOTE_SOURCE_ROOT}' || { echo REMOTE_SOURCE_UNSAFE >&2; exit 1; }; \
    test -f '${BENCHMARK_REMOTE_SOURCE_ROOT}/.TRANSFER_IN_PROGRESS' || { echo REMOTE_SOURCE_COLLISION >&2; exit 1; }; \
    test ! -e '${BENCHMARK_REMOTE_SOURCE_ROOT}/_TRANSFER_COMPLETE' || { echo REMOTE_SOURCE_ALREADY_COMPLETE >&2; exit 1; }; \
  else \
    mkdir -m 700 '${BENCHMARK_REMOTE_SOURCE_ROOT}'; \
    install -m 600 /dev/null '${BENCHMARK_REMOTE_SOURCE_ROOT}/.TRANSFER_IN_PROGRESS'; \
  fi; \
  chmod 700 '${BENCHMARK_REMOTE_SOURCE_ROOT}'; \
  if test -e '${BENCHMARK_REMOTE_SCOPE_PATH}'; then \
    test -f '${BENCHMARK_REMOTE_SCOPE_PATH}' || { echo REMOTE_SCOPE_UNSAFE >&2; exit 1; }; \
    test \"\$(sha256sum '${BENCHMARK_REMOTE_SCOPE_PATH}' | awk '{print \$1}')\" = '${BENCHMARK_POPULATION_SCOPE_SHA256}' || { echo REMOTE_SCOPE_COLLISION >&2; exit 1; }; \
  fi"

"${RSYNC}" -a --checksum --protect-args --from0 -e "${RSYNC_REMOTE_SHELL}" \
  --files-from="${FILE_LIST}" --chmod=D700,F600 \
  "${BENCHMARK_SOURCE_ROOT}/" \
  "${REMOTE_HOST}:${BENCHMARK_REMOTE_SOURCE_ROOT}/"

"${RSYNC}" -a --checksum --protect-args --chmod=F600 -e "${RSYNC_REMOTE_SHELL}" \
  "${BENCHMARK_POPULATION_SCOPE}" \
  "${REMOTE_HOST}:${BENCHMARK_REMOTE_SCOPE_PATH}"

verification="$("${RSYNC}" -a --checksum --protect-args --from0 \
  --files-from="${FILE_LIST}" --chmod=D700,F600 --dry-run --itemize-changes \
  -e "${RSYNC_REMOTE_SHELL}" \
  "${BENCHMARK_SOURCE_ROOT}/" \
  "${REMOTE_HOST}:${BENCHMARK_REMOTE_SOURCE_ROOT}/")"
[[ -z "${verification}" ]] || {
  echo "TRANSFER_CHECKSUM_RECONCILIATION_FAILED" >&2
  exit 1
}

ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=120 "${REMOTE_HOST}" "set -eu; \
  chmod 700 '${BENCHMARK_REMOTE_SOURCE_ROOT}'; \
  chmod 600 '${BENCHMARK_REMOTE_SCOPE_PATH}'; \
  rm '${BENCHMARK_REMOTE_SOURCE_ROOT}/.TRANSFER_IN_PROGRESS'; \
  install -m 600 /dev/null '${BENCHMARK_REMOTE_SOURCE_ROOT}/_TRANSFER_COMPLETE'"

echo "transfer_status=PASS"
echo "transfer_integrity=RSYNC_CHECKSUM_RECONCILED"
echo "external_processing=false"
