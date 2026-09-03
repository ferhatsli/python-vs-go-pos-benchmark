#!/usr/bin/env bash
set -euo pipefail

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POS_ROOT="${POS_ROOT:-}"
BENCH_ROOT="${BENCH_ROOT:-$SCRIPT_ROOT}"
BASELINE_FILE="${ISOLATION_BASELINE_FILE:-$SCRIPT_ROOT/.isolation/pos-status-baseline.txt}"
SKIP_TOOL_CHECKS="${SKIP_TOOL_CHECKS:-0}"

if [[ -z "$POS_ROOT" ]]; then
  echo "ERROR: POS_ROOT must be set for private preflight operations" >&2
  exit 9
fi
if [[ ! -e "$POS_ROOT" ]]; then
  echo "ERROR: POS_ROOT does not exist: $POS_ROOT" >&2
  exit 10
fi
if [[ ! -d "$POS_ROOT/.git" && ! -f "$POS_ROOT/.git" ]]; then
  echo "ERROR: POS_ROOT is not a git repository: $POS_ROOT" >&2
  exit 11
fi

case "$BENCH_ROOT" in
  "$POS_ROOT"|"$POS_ROOT"/*)
    echo "ERROR: benchmark workspace is nested in POS_ROOT" >&2
    exit 12
    ;;
esac

mkdir -p "$(dirname "$BASELINE_FILE")"
git -C "$POS_ROOT" status --porcelain=v1 > "$BASELINE_FILE"

if [[ "$SKIP_TOOL_CHECKS" != "1" ]]; then
  missing=0
  for tool in git docker; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      echo "ERROR: required tool missing: $tool" >&2
      missing=1
    fi
  done
  if command -v docker >/dev/null 2>&1; then
    if ! docker compose version >/dev/null 2>&1; then
      echo "ERROR: docker compose is unavailable" >&2
      missing=1
    fi
  fi
  if ! command -v k6 >/dev/null 2>&1 && ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: neither local k6 nor Docker is available for k6" >&2
    missing=1
  fi
  if [[ "$missing" -ne 0 ]]; then
    exit 13
  fi
fi

echo "PASS: preflight captured POS status without mutating the source repository"
