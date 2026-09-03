#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:?usage: verify_result.sh <correctness.json|trial-dir>}"

if [[ -d "$TARGET" ]]; then
  TRIAL="$TARGET/trial.json"
  INVARIANTS="$TARGET/invariants.txt"
  DATASET="$TARGET/dataset.json"
  [[ -f "$TRIAL" && -f "$INVARIANTS" && -f "$DATASET" ]] || {
    echo "FAIL: incomplete trial artifacts in $TARGET" >&2
    exit 1
  }
  SCENARIO="$(python3 - "$TRIAL" <<'PY'
import json,sys
print(json.load(open(sys.argv[1])).get('scenario',''))
PY
)"
  if [[ "$SCENARIO" == "worker" ]]; then
    SUMMARY="$TARGET/worker-summary.json"
  else
    SUMMARY="$TARGET/k6-summary.json"
  fi
  [[ -f "$SUMMARY" ]] || {
    echo "FAIL: incomplete trial artifacts in $TARGET" >&2
    exit 1
  }
  python3 - "$TRIAL" "$INVARIANTS" "$SUMMARY" <<'PY'
import json, sys
from pathlib import Path
trial=json.loads(Path(sys.argv[1]).read_text())
invariants=Path(sys.argv[2]).read_text().strip()
summary=json.loads(Path(sys.argv[3]).read_text())
failures=[]
if trial.get('scenario') == 'worker':
    if int(trial.get('worker_returncode', 1)) != 0:
        failures.append(f"worker_returncode={trial.get('worker_returncode')}")
    if int(summary.get('devices_evaluated', 0)) <= 0:
        failures.append('devices_evaluated<=0')
else:
    if int(trial.get('k6_returncode', 1)) != 0:
        failures.append(f"k6_returncode={trial.get('k6_returncode')}")
if int(trial.get('invariant_returncode', 1)) != 0:
    failures.append(f"invariant_returncode={trial.get('invariant_returncode')}")
if invariants:
    failures.append('invariants.txt is not empty')
if failures:
    print('FAIL: trial verification: ' + ', '.join(failures))
    raise SystemExit(1)
print(f"PASS: trial {trial.get('runtime')} {trial.get('profile')} {trial.get('scenario')} {trial.get('phase')}-{trial.get('ordinal')}")
PY
  exit 0
fi

FILE="$TARGET"
python3 - "$FILE" <<'PY'
import json, sys
from pathlib import Path
p=Path(sys.argv[1])
data=json.loads(p.read_text())
nonzero={k:v for k,v in data.get('hard_gate',{}).items() if v != 0}
false_contracts=[k for k,v in data.get('contracts',{}).items() if not bool(v)]
if nonzero or false_contracts:
    print(f"FAIL: hard_gate={nonzero} false_contracts={false_contracts}")
    raise SystemExit(1)
print(f"PASS: {data.get('runtime')} {data.get('profile')} correctness gate")
PY
