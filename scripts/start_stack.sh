#!/usr/bin/env bash
set -euo pipefail

RUNTIME="${1:?usage: start_stack.sh <python|go>}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

case "$RUNTIME" in
  python) SERVICE="python-api"; OTHER="go-api" ;;
  go) SERVICE="go-api"; OTHER="python-api" ;;
  *) echo "runtime must be python or go" >&2; exit 2 ;;
esac

docker compose up -d postgres redis >/dev/null
docker compose stop "$OTHER" >/dev/null 2>&1 || true

if [[ -n "$(docker compose ps -q --status running "$OTHER" 2>/dev/null || true)" ]]; then
  echo "FAIL: opposite API is still running: $OTHER" >&2
  exit 1
fi

docker compose up -d "$SERVICE" >/dev/null

if [[ -n "$(docker compose ps -q --status running "$OTHER" 2>/dev/null || true)" ]]; then
  echo "FAIL: both APIs would be active" >&2
  exit 1
fi

CID="$(docker compose ps -q "$SERVICE")"
[[ -n "$CID" ]] || { echo "FAIL: $SERVICE container not found" >&2; exit 1; }

for _ in $(seq 1 "${BENCH_HEALTH_RETRIES:-60}"); do
  STATUS="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$CID" 2>/dev/null || true)"
  if [[ "$STATUS" == "healthy" ]]; then
    echo "PASS: $SERVICE healthy; opposite runtime stopped"
    exit 0
  fi
  if [[ "$STATUS" == "unhealthy" || "$STATUS" == "exited" ]]; then
    docker compose logs --tail=100 "$SERVICE" >&2 || true
    echo "FAIL: $SERVICE health=$STATUS" >&2
    exit 1
  fi
  sleep "${BENCH_HEALTH_INTERVAL_SECONDS:-1}"
done

echo "FAIL: $SERVICE did not become healthy" >&2
exit 1
