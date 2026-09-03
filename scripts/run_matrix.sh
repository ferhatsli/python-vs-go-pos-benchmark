#!/usr/bin/env bash
set -euo pipefail

SCENARIO="${1:?usage: run_matrix.sh <scenario> <D1|D2|D3> <run-id> [load-level]}"
PROFILE="${2:?}"
RUN_ID="${3:?}"
LEVEL="${4:-}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LOCK_FILE="$ROOT/.isolation/.benchmark-matrix.lock"
mkdir -p "$(dirname "$LOCK_FILE")"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "FAIL: another benchmark matrix is already running" >&2
  exit 10
fi
printf '%s\n' "pid=$$ scenario=$SCENARIO profile=$PROFILE run_id=$RUN_ID load_level=${LEVEL:-default}" >&9
export BENCH_MATRIX_LOCK_HELD=1

if [[ -n "$LEVEL" && ! "$LEVEL" =~ ^[1-9][0-9]*$ ]]; then
  echo "load-level must be a positive integer" >&2
  exit 2
fi
export BENCH_LOAD_LEVEL="$LEVEL"
CASE_KEY="$SCENARIO"
if [[ -n "$LEVEL" ]]; then CASE_KEY="${SCENARIO}-level-${LEVEL}"; fi

WARMUP_RUNS=2
MIN_MEASURED_RUNS=5
MAX_MEASURED_RUNS=10
CV_LIMIT_PERCENT=10

declare -a BLOCK_ORDERS
BLOCK_ORDERS[0]="python go"
BLOCK_ORDERS[1]="go python"
BLOCK_ORDERS[2]="python go"
BLOCK_ORDERS[3]="go python"
BLOCK_ORDERS[4]="python go"

if [[ "${BENCH_PLAN_ONLY:-0}" == "1" ]]; then
  echo "warmups: python x${WARMUP_RUNS}, go x${WARMUP_RUNS}"
  for i in "${!BLOCK_ORDERS[@]}"; do echo "block $((i+1)): ${BLOCK_ORDERS[$i]}"; done
  echo "variance: p(95) CV <= ${CV_LIMIT_PERCENT}% after >=${MIN_MEASURED_RUNS}, max=${MAX_MEASURED_RUNS}; else UNSTABLE"
  exit 0
fi

for runtime in python go; do
  for warmup in $(seq 1 "$WARMUP_RUNS"); do
    bash scripts/run_scenario.sh "$runtime" "$PROFILE" "$SCENARIO" "$RUN_ID" warmup "$warmup"
  done
done

for i in "${!BLOCK_ORDERS[@]}"; do
  block=$((i+1))
  for runtime in ${BLOCK_ORDERS[$i]}; do
    bash scripts/run_scenario.sh "$runtime" "$PROFILE" "$SCENARIO" "$RUN_ID" measured "$block"
  done
done

cv_json() {
  local runtime="$1"
  python3 - "$ROOT/results/$RUN_ID/$PROFILE/$CASE_KEY/$runtime" <<'PY'
import glob, json, math, statistics, sys
from pathlib import Path
root=Path(sys.argv[1])
values=[]
worker_paths=sorted(root.glob('measured-*/worker-summary.json'), key=lambda p:int(p.parent.name.split('-')[-1]))
if worker_paths:
    for path in worker_paths:
        data=json.loads(path.read_text())
        raw=data.get('duration_ms')
        if raw is None:
            raise SystemExit(f'missing duration_ms in {path}')
        values.append(float(raw))
else:
    for path in sorted(root.glob('measured-*/k6-summary.json'), key=lambda p:int(p.parent.name.split('-')[-1])):
        data=json.loads(path.read_text())
        metric=data.get('metrics',{}).get('http_req_duration',{})
        raw=metric.get('values',{}).get('p(95)')
        if raw is None:
            raw=metric.get('p(95)')
        if raw is None:
            raise SystemExit(f'missing p(95) in {path}')
        values.append(float(raw))
mean=statistics.fmean(values) if values else 0.0
if len(values) < 2 or mean == 0:
    cv=0.0
else:
    cv=statistics.stdev(values)/mean*100.0
print(json.dumps({'count':len(values),'p95_values_ms':values,'cv_percent':cv}, separators=(',',':')))
PY
}

cv_exceeds() {
  python3 - "$1" "$CV_LIMIT_PERCENT" <<'PY'
import json, sys
payload=json.loads(sys.argv[1])
raise SystemExit(0 if float(payload['cv_percent']) > float(sys.argv[2]) else 1)
PY
}

measured="$MIN_MEASURED_RUNS"
while (( measured < MAX_MEASURED_RUNS )); do
  PY_CV="$(cv_json python)"
  GO_CV="$(cv_json go)"
  need_more=0
  if cv_exceeds "$PY_CV"; then need_more=1; fi
  if cv_exceeds "$GO_CV"; then need_more=1; fi
  (( need_more == 1 )) || break

  measured=$((measured+1))
  if (( measured % 2 == 0 )); then EXTRA_ORDER="go python"; else EXTRA_ORDER="python go"; fi
  for runtime in $EXTRA_ORDER; do
    bash scripts/run_scenario.sh "$runtime" "$PROFILE" "$SCENARIO" "$RUN_ID" measured "$measured"
  done
done

PY_CV="$(cv_json python)"
GO_CV="$(cv_json go)"
STATUS="STABLE"
if cv_exceeds "$PY_CV" || cv_exceeds "$GO_CV"; then STATUS="UNSTABLE"; fi

SUMMARY_DIR="$ROOT/results/$RUN_ID/$PROFILE/$CASE_KEY"
mkdir -p "$SUMMARY_DIR"
python3 - "$SUMMARY_DIR/matrix-summary.json" "$PROFILE" "$SCENARIO" "$RUN_ID" "$STATUS" "$PY_CV" "$GO_CV" "$LEVEL" <<'PY'
import json, sys
from pathlib import Path
payload={
  'profile':sys.argv[2], 'scenario':sys.argv[3], 'run_id':sys.argv[4], 'status':sys.argv[5],
  'python':json.loads(sys.argv[6]), 'go':json.loads(sys.argv[7]),
  'load_level': int(sys.argv[8]) if sys.argv[8] else None,
}
Path(sys.argv[1]).write_text(json.dumps(payload,sort_keys=True,indent=2)+'\n')
print(json.dumps(payload,sort_keys=True))
PY

echo "PASS: matrix complete status=$STATUS measured_runs=$measured"
