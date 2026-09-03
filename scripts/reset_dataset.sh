#!/usr/bin/env bash
set -euo pipefail

PROFILE="${1:-D1}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

case "$PROFILE" in D1|D2|D3) ;; *) echo "profile must be D1, D2 or D3" >&2; exit 2 ;; esac

docker compose up -d postgres redis >/dev/null

READY=0
for _ in $(seq 1 "${BENCH_DB_HEALTH_RETRIES:-60}"); do
  if docker compose exec -T postgres pg_isready -U benchmark -d pos_benchmark >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep "${BENCH_DB_HEALTH_INTERVAL_SECONDS:-1}"
done
[[ "$READY" == "1" ]] || { echo "FAIL: postgres did not become ready" >&2; exit 1; }

SCHEMA_READY="$(docker compose exec -T postgres psql -X -qAt -U benchmark -d pos_benchmark -v ON_ERROR_STOP=1 -c "SELECT to_regclass('public.devices') IS NOT NULL")"
if [[ "$SCHEMA_READY" != "t" ]]; then
  docker compose exec -T postgres psql -X -qAt -U benchmark -d pos_benchmark -v ON_ERROR_STOP=1 -f /dev/stdin < db/003_extensions.sql
  docker compose exec -T postgres psql -X -qAt -U benchmark -d pos_benchmark -v ON_ERROR_STOP=1 -f /dev/stdin < db/001_schema.sql
  docker compose exec -T postgres psql -X -qAt -U benchmark -d pos_benchmark -v ON_ERROR_STOP=1 -f /dev/stdin < db/002_indexes.sql
fi

SEED_JSON="$(mktemp)"
CHECK_JSON="$(mktemp)"
trap 'rm -f "$SEED_JSON" "$CHECK_JSON"' EXIT

python3 db/seed/seed.py --profile "$PROFILE" > "$SEED_JSON"
python3 db/seed/seed.py --profile "$PROFILE" --fingerprint-only > "$CHECK_JSON"

python3 - "$SEED_JSON" "$CHECK_JSON" <<'PY'
import json, sys
from pathlib import Path
left=json.loads(Path(sys.argv[1]).read_text())
right=json.loads(Path(sys.argv[2]).read_text())
keys=("seed","profile","schema_hash","stable_keys_sha256","row_counts")
diff={k:(left.get(k), right.get(k)) for k in keys if left.get(k) != right.get(k)}
if diff:
    print(f"FAIL: dataset fingerprint mismatch: {diff}", file=sys.stderr)
    raise SystemExit(1)
print(json.dumps(left, sort_keys=True))
PY
