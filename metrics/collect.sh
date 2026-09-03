#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-}"
OUT_DIR="${2:-}"
RUNTIME="${3:-${RUNTIME:-python}}"

usage() {
  echo "usage: metrics/collect.sh <pre|sample|post|diagnostic> <output-dir> [python|go]" >&2
  exit 2
}

case "$MODE" in pre|sample|post|diagnostic) ;; *) usage ;; esac
[[ -n "$OUT_DIR" ]] || usage
[[ "$RUNTIME" == "python" || "$RUNTIME" == "go" ]] || usage
mkdir -p "$OUT_DIR"

compose() { docker compose -f "$ROOT/compose.yaml" "$@"; }
psql_file() {
  local file="$1"
  compose exec -T postgres psql -X -qAt -U benchmark -d pos_benchmark -v ON_ERROR_STOP=1 -f /dev/stdin < "$file"
}

capture_statements() {
  local phase="$1"
  compose exec -T postgres psql -X -qAt -U benchmark -d pos_benchmark -v ON_ERROR_STOP=1 -c \
    "COPY (SELECT queryid,calls,rows,total_exec_time,wal_bytes FROM pg_stat_statements WHERE dbid=(SELECT oid FROM pg_database WHERE datname=current_database()) AND query NOT ILIKE '%pg_stat_%' AND query NOT ILIKE '%pg_database_size%' ORDER BY queryid) TO STDOUT WITH CSV HEADER" \
    > "$OUT_DIR/statements_${phase}.csv"
}

capture_container() {
  local role="$1" service="$2"
  local cid stats process_count
  cid="$(compose ps -q "$service" 2>/dev/null || true)"
  [[ -n "$cid" ]] || return 0
  stats="$(docker stats --no-stream --format '{{json .}}' "$cid")"
  process_count="$(docker top "$cid" -eo pid 2>/dev/null | tail -n +2 | awk 'NF{n++} END{print n+0}')"
  ROLE="$role" PROCESS_COUNT="$process_count" STATS_JSON="$stats" python3 - <<'PY' >> "$OUT_DIR/container_samples.ndjson"
import json, os, time
print(json.dumps({
    "captured_at_unix": time.time(),
    "role": os.environ["ROLE"],
    "process_count": int(os.environ["PROCESS_COUNT"]),
    "stats": json.loads(os.environ["STATS_JSON"]),
}, sort_keys=True))
PY
}

capture_sample() {
  psql_file "$ROOT/metrics/lock-sampler.sql" >> "$OUT_DIR/lock_samples.ndjson"
  local api_service
  if [[ "$RUNTIME" == "python" ]]; then api_service="python-api"; else api_service="go-api"; fi
  capture_container api "$api_service"
  capture_container postgres postgres
  capture_container redis redis
}

capture_snapshot() {
  local phase="$1"
  psql_file "$ROOT/metrics/snapshot.sql" > "$OUT_DIR/pg_${phase}.json"
  capture_statements "$phase"
}

capture_diagnostic() {
  [[ "${BENCH_DIAGNOSTIC:-0}" == "1" ]] || {
    echo "diagnostic profiling requires BENCH_DIAGNOSTIC=1" >&2
    exit 2
  }
  if [[ "$RUNTIME" == "go" ]]; then
    # pprof is diagnostic-only. BENCH_PPROF_URL may point at an internal benchmark endpoint.
    local pprof_url="${BENCH_PPROF_URL:-http://go-api:6060/debug/pprof/profile?seconds=30}"
    echo "$pprof_url" > "$OUT_DIR/pprof.url"
    if command -v curl >/dev/null 2>&1; then
      curl -fsS "$pprof_url" -o "$OUT_DIR/go-cpu.pprof" || echo "WARN: pprof capture unavailable" >&2
    else
      echo "WARN: curl unavailable; pprof URL recorded only" >&2
    fi
  else
    # py-spy is never enabled for headline trials; this path is diagnostic-only.
    local cid pid
    cid="$(compose ps -q python-api 2>/dev/null || true)"
    [[ -n "$cid" ]] || { echo "python-api not running" >&2; exit 2; }
    pid="$(docker top "$cid" -eo pid 2>/dev/null | awk 'NR==2{print $1}')"
    if command -v py-spy >/dev/null 2>&1; then
      py-spy record --pid "$pid" --duration "${BENCH_PROFILE_SECONDS:-30}" -o "$OUT_DIR/python-profile.svg"
    else
      echo "WARN: py-spy unavailable; install it only for a diagnostic run" >&2
    fi
  fi
}

case "$MODE" in
  pre) capture_snapshot pre ;;
  sample) capture_sample ;;
  post) capture_snapshot post; capture_sample ;;
  diagnostic) capture_diagnostic ;;
esac
