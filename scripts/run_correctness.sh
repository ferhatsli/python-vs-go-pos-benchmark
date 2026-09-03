#!/usr/bin/env bash
set -euo pipefail

RUNTIME="${1:?usage: run_correctness.sh <python|go> <D1|D2|D3>}"
PROFILE="${2:-D1}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POS_ROOT="${POS_ROOT:-}"
cd "$ROOT"

case "$RUNTIME" in
  python) SERVICE=python-api; API_URL="${API_URL:-http://127.0.0.1:48000}" ;;
  go) SERVICE=go-api; API_URL="${API_URL:-http://127.0.0.1:48001}" ;;
  *) echo "unsupported runtime: $RUNTIME" >&2; exit 2 ;;
esac

# Mandatory matrix frozen by Task 6. Keep names stable for result comparison.
MATRIX=(heartbeat configuration card same_key qr_2 qr_10 qr_100 rf_2 rf_10 rf_100 command dashboard worker)
printf 'correctness matrix: %s\n' "${MATRIX[*]}"

./scripts/verify_isolation.sh "$POS_ROOT"
./scripts/reset_dataset.sh "$PROFILE" >/dev/null

docker compose stop python-api go-api >/dev/null 2>&1 || true
trap 'docker compose stop "$SERVICE" >/dev/null 2>&1 || true' EXIT

docker compose up -d --build "$SERVICE" >/dev/null
for _ in $(seq 1 60); do
  if curl -fsS "$API_URL/health" >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS "$API_URL/health" >/dev/null

# The driver resets pg_stat_statements before every request class with:
# SELECT pg_stat_statements_reset();
# This one reset guarantees a clean top-level start as well.
docker compose exec -T postgres psql -X -qAt -U benchmark -d pos_benchmark \
  -v ON_ERROR_STOP=1 -c 'SELECT pg_stat_statements_reset();' >/dev/null

OUT="results/correctness/${PROFILE}/${RUNTIME}/correctness.json"
API_URL="$API_URL" python3 scripts/correctness_driver.py "$RUNTIME" "$PROFILE" "$OUT"
./scripts/verify_result.sh "$OUT"
./scripts/verify_isolation.sh "$POS_ROOT"
printf 'PASS: %s correctness -> %s\n' "$RUNTIME" "$OUT"
