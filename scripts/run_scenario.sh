#!/usr/bin/env bash
set -euo pipefail

RUNTIME="${1:?usage: run_scenario.sh <python|go> <D1|D2|D3> <scenario> <run-id> <warmup|measured> <ordinal>}"
PROFILE="${2:?}"
SCENARIO="${3:?}"
RUN_ID="${4:?}"
PHASE="${5:?}"
ORDINAL="${6:?}"
LOAD_LEVEL="${BENCH_LOAD_LEVEL:-}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "${BENCH_MATRIX_LOCK_HELD:-0}" != "1" ]]; then
  LOCK_FILE="$ROOT/.isolation/.benchmark-matrix.lock"
  mkdir -p "$(dirname "$LOCK_FILE")"
  exec 8>"$LOCK_FILE"
  if ! flock -n 8; then
    echo "FAIL: another benchmark run is already active" >&2
    exit 10
  fi
  printf '%s\n' "pid=$$ runtime=$RUNTIME scenario=$SCENARIO profile=$PROFILE run_id=$RUN_ID phase=$PHASE ordinal=$ORDINAL" >&8
fi

case "$RUNTIME" in python|go) ;; *) echo "runtime must be python or go" >&2; exit 2 ;; esac
case "$PROFILE" in D1|D2|D3) ;; *) echo "profile must be D1, D2 or D3" >&2; exit 2 ;; esac
case "$PHASE" in warmup|measured) ;; *) echo "phase must be warmup or measured" >&2; exit 2 ;; esac
if [[ -n "$LOAD_LEVEL" && ! "$LOAD_LEVEL" =~ ^[1-9][0-9]*$ ]]; then
  echo "BENCH_LOAD_LEVEL must be a positive integer" >&2
  exit 2
fi
CASE_KEY="$SCENARIO"
if [[ -n "$LOAD_LEVEL" ]]; then CASE_KEY="${SCENARIO}-level-${LOAD_LEVEL}"; fi
case "$SCENARIO" in
  smoke|heartbeat|configuration|payment-card|payment-qr-contention|payment-rf-contention|dashboard|command-lifecycle)
    LOAD_FILE="load/${SCENARIO}.js" ;;
  worker)
    LOAD_FILE="" ;;
  *) echo "unsupported scenario: $SCENARIO" >&2; exit 2 ;;
esac

OUT_DIR="$ROOT/results/$RUN_ID/$PROFILE/$CASE_KEY/$RUNTIME/${PHASE}-${ORDINAL}"
if [[ -e "$OUT_DIR" && "${BENCH_OVERWRITE:-0}" != "1" ]]; then
  echo "FAIL: result directory already exists: $OUT_DIR" >&2
  exit 1
fi
rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

SAMPLER_PID=""
cleanup() {
  if [[ -n "$SAMPLER_PID" ]]; then
    kill "$SAMPLER_PID" >/dev/null 2>&1 || true
    wait "$SAMPLER_PID" >/dev/null 2>&1 || true
  fi
  docker compose stop python-api go-api python-worker go-worker >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

psql() {
  docker compose exec -T postgres psql -X -qAt -U benchmark -d pos_benchmark -v ON_ERROR_STOP=1 -c "$1"
}

prepare_scenario_fixture() {
  case "$SCENARIO" in
    payment-card|payment-qr-contention|payment-rf-contention)
      psql "UPDATE device_current_states SET last_seen_at=clock_timestamp(), updated_at=clock_timestamp(); DELETE FROM maintenance_windows;" >/dev/null
      ;;
    command-lifecycle)
      local command_vus="${COMMAND_VUS:-10}"
      if [[ "${BENCH_DRY_RUN:-0}" == "1" ]]; then command_vus=1; fi
      psql "DELETE FROM command_results WHERE command_id <= ${command_vus};
            UPDATE commands SET status='PENDING', sent_at=NULL, acknowledged_at=NULL, completed_at=NULL, result_code=NULL, created_at=clock_timestamp() WHERE id <= ${command_vus};
            UPDATE program_executions e SET status='CREATED', started_at=NULL, completed_at=NULL
            FROM commands c WHERE c.id <= ${command_vus} AND e.id=c.program_execution_id;" >/dev/null
      ;;
    worker)
      psql "DELETE FROM maintenance_windows; DELETE FROM alarms;
            UPDATE device_current_states SET last_seen_at=clock_timestamp(), updated_at=clock_timestamp();
            UPDATE device_current_states SET last_seen_at=clock_timestamp()-interval '10 minutes', updated_at=clock_timestamp() WHERE device_id=1;" >/dev/null
      ;;
  esac
}

start_sampler() {
  (
    while true; do
      bash metrics/collect.sh sample "$OUT_DIR" "$RUNTIME" >/dev/null 2>&1 || true
      sleep "${BENCH_METRIC_SAMPLE_INTERVAL_SECONDS:-1}"
    done
  ) &
  SAMPLER_PID=$!
}

stop_sampler() {
  if [[ -n "$SAMPLER_PID" ]]; then
    kill "$SAMPLER_PID" >/dev/null 2>&1 || true
    wait "$SAMPLER_PID" >/dev/null 2>&1 || true
    SAMPLER_PID=""
  fi
}

capture_invariants() {
  docker compose exec -T postgres psql -X -qAt -U benchmark -d pos_benchmark -v ON_ERROR_STOP=1 -f /dev/stdin \
    < db/checks/invariants.sql > "$OUT_DIR/invariants.txt"
  if [[ -s "$OUT_DIR/invariants.txt" ]]; then return 1; fi
  return 0
}

bash scripts/verify_isolation.sh
bash scripts/stop_stack.sh all
bash scripts/reset_dataset.sh "$PROFILE" > "$OUT_DIR/dataset.json"
prepare_scenario_fixture
psql "SELECT pg_stat_statements_reset();" > "$OUT_DIR/pg-stat-reset.txt"

if [[ "$SCENARIO" == "worker" ]]; then
  bash metrics/collect.sh pre "$OUT_DIR" "$RUNTIME"
  start_sampler
  if [[ "$RUNTIME" == "python" ]]; then WORKER_SERVICE="python-worker"; else WORKER_SERVICE="go-worker"; fi
  set +e
  docker compose run --rm --build --no-deps "$WORKER_SERVICE" > "$OUT_DIR/worker.txt"
  WORKER_RC=$?
  set -e
  stop_sampler
  bash metrics/collect.sh post "$OUT_DIR" "$RUNTIME"

  python3 - "$OUT_DIR/worker.txt" "$OUT_DIR/worker-summary.json" <<'PY'
import json, sys
from pathlib import Path
src=Path(sys.argv[1]); dst=Path(sys.argv[2])
lines=[line.strip() for line in src.read_text().splitlines() if line.strip()]
if not lines:
    raise SystemExit('worker produced no summary')
payload=json.loads(lines[-1])
required=('devices_evaluated','duration_ms','devices_per_second','overrun_5s')
missing=[k for k in required if k not in payload]
if missing:
    raise SystemExit(f'missing worker summary fields: {missing}')
dst.write_text(json.dumps(payload,sort_keys=True,indent=2)+'\n')
PY

  INVARIANT_RC=0
  capture_invariants || INVARIANT_RC=$?
  docker compose stop python-worker go-worker >/dev/null 2>&1 || true
  bash scripts/verify_isolation.sh
  python3 - "$OUT_DIR" "$RUNTIME" "$PROFILE" "$SCENARIO" "$PHASE" "$ORDINAL" "$WORKER_RC" "$INVARIANT_RC" "$LOAD_LEVEL" <<'PY'
import json, sys
from pathlib import Path
out=Path(sys.argv[1])
payload={
    'runtime':sys.argv[2], 'profile':sys.argv[3], 'scenario':sys.argv[4],
    'phase':sys.argv[5], 'ordinal':int(sys.argv[6]),
    'worker_returncode':int(sys.argv[7]), 'invariant_returncode':int(sys.argv[8]),
    'load_level': int(sys.argv[9]) if sys.argv[9] else None,
}
(out/'trial.json').write_text(json.dumps(payload,sort_keys=True,indent=2)+'\n')
PY
  if [[ "$WORKER_RC" -ne 0 || "$INVARIANT_RC" -ne 0 ]]; then
    echo "FAIL: worker trial worker_rc=$WORKER_RC invariant_rc=$INVARIANT_RC -> $OUT_DIR" >&2
    exit 1
  fi
  echo "PASS: $RUNTIME $PROFILE worker $PHASE-$ORDINAL -> $OUT_DIR"
  exit 0
fi

bash scripts/start_stack.sh "$RUNTIME"
bash metrics/collect.sh pre "$OUT_DIR" "$RUNTIME"
start_sampler

if [[ "$RUNTIME" == "python" ]]; then
  API_PORT="${BENCH_PYTHON_PORT:-48000}"
else
  API_PORT="${BENCH_GO_PORT:-48001}"
fi

K6_RUN_ID="${RUN_ID}-${PROFILE}-${CASE_KEY}-${RUNTIME}-${PHASE}-${ORDINAL}"
set +e
docker run --rm --network host \
  -v "$ROOT/load:/scripts:ro" \
  -v "$OUT_DIR:/results" \
  -e API_URL="http://127.0.0.1:${API_PORT}" \
  -e DATASET_PROFILE="$PROFILE" \
  -e RUN_ID="$K6_RUN_ID" \
  -e RUNTIME="$RUNTIME" \
  -e DRY_RUN="${BENCH_DRY_RUN:-0}" \
  -e BENCH_ACCEPTANCE="${BENCH_ACCEPTANCE:-0}" \
  -e BENCH_ACCEPTANCE_DURATION="${BENCH_ACCEPTANCE_DURATION:-15s}" \
  -e BENCH_LOAD_LEVEL="$LOAD_LEVEL" \
  -e BENCH_LOAD_DURATION="${BENCH_LOAD_DURATION:-}" \
  -e CONTENTION_VUS="${CONTENTION_VUS:-100}" \
  -e COMMAND_VUS="${COMMAND_VUS:-10}" \
  -e COMMAND_BASE_ID="${COMMAND_BASE_ID:-1}" \
  -e FIXTURE_INDEX="${FIXTURE_INDEX:-1}" \
  "${K6_IMAGE:-grafana/k6:0.55.0}" run --quiet \
  --summary-export /results/k6-summary.json "/scripts/${SCENARIO}.js" \
  > "$OUT_DIR/k6.txt" 2>&1
K6_RC=$?
set -e
stop_sampler

bash metrics/collect.sh post "$OUT_DIR" "$RUNTIME"
INVARIANT_RC=0
capture_invariants || INVARIANT_RC=$?

bash scripts/stop_stack.sh "$RUNTIME"
bash scripts/verify_isolation.sh

python3 - "$OUT_DIR" "$RUNTIME" "$PROFILE" "$SCENARIO" "$PHASE" "$ORDINAL" "$K6_RC" "$INVARIANT_RC" "$LOAD_LEVEL" <<'PY'
import json, sys
from pathlib import Path
out=Path(sys.argv[1])
payload={
    "runtime": sys.argv[2], "profile": sys.argv[3], "scenario": sys.argv[4],
    "phase": sys.argv[5], "ordinal": int(sys.argv[6]),
    "k6_returncode": int(sys.argv[7]), "invariant_returncode": int(sys.argv[8]),
    "load_level": int(sys.argv[9]) if sys.argv[9] else None,
}
(out/'trial.json').write_text(json.dumps(payload, sort_keys=True, indent=2)+'\n')
PY

if [[ "$K6_RC" -ne 0 || "$INVARIANT_RC" -ne 0 ]]; then
  echo "FAIL: trial k6_rc=$K6_RC invariant_rc=$INVARIANT_RC -> $OUT_DIR" >&2
  exit 1
fi

echo "PASS: $RUNTIME $PROFILE $SCENARIO $PHASE-$ORDINAL -> $OUT_DIR"
