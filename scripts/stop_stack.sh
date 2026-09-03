#!/usr/bin/env bash
set -euo pipefail

RUNTIME="${1:-all}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

case "$RUNTIME" in
  python|go|all) ;;
  *) echo "usage: stop_stack.sh [python|go|all]" >&2; exit 2 ;;
esac

# Always stop both measured APIs. This makes the postcondition stronger than
# merely stopping the requested side and prevents cross-runtime overlap.
docker compose stop python-api go-api >/dev/null 2>&1 || true

for service in python-api go-api; do
  if [[ -n "$(docker compose ps -q --status running "$service" 2>/dev/null || true)" ]]; then
    echo "FAIL: API still running after stop: $service" >&2
    exit 1
  fi
done

echo "PASS: measured APIs stopped"
