#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], *, capture: bool = True) -> str:
    proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=capture, check=False)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "command failed").strip())
    return proc.stdout.strip() if capture else ""


def psql(sql: str) -> str:
    return run([
        "docker", "compose", "exec", "-T", "postgres", "psql", "-X", "-qAt",
        "-U", "benchmark", "-d", "pos_benchmark", "-v", "ON_ERROR_STOP=1", "-c", sql,
    ])


def scalar(sql: str) -> int:
    raw = psql(sql).strip()
    return int(raw or "0")


def reset_stats() -> None:
    psql("SELECT pg_stat_statements_reset();")


def sql_snapshot() -> list[dict[str, Any]]:
    raw = psql(r"""
SELECT coalesce(json_agg(row_to_json(x)), '[]'::json)::text
FROM (
  SELECT regexp_replace(query, '\s+', ' ', 'g') AS query,
         calls::bigint AS calls,
         rows::bigint AS rows,
         round(total_exec_time::numeric, 3)::float8 AS total_exec_time_ms
  FROM pg_stat_statements
  WHERE dbid = (SELECT oid FROM pg_database WHERE datname='pos_benchmark')
    AND userid = (SELECT usesysid FROM pg_user WHERE usename='benchmark')
    AND query !~* 'pg_stat_statements'
    AND query ~* '(companies|panel_users|stations|devices|device_credentials|device_configurations|device_current_states|device_heartbeats|programs|program_payment_methods|entitlements|wash_bays|maintenance_windows|qr_codes|rf_cards|rf_wallets|payment_transactions|payment_attempts|provider_transactions|start_rights|rf_wallet_ledger|program_executions|commands|command_results|events|audit_entries|alarms|pg_advisory_xact_lock)'
  ORDER BY query
) x;
""")
    return json.loads(raw or "[]")


def semantic_calls(snapshot: list[dict[str, Any]]) -> int:
    return sum(int(row["calls"]) for row in snapshot)


def request(api_url: str, method: str, path: str, headers: dict[str, str] | None = None, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    payload = None if body is None else json.dumps(body, separators=(",", ":")).encode()
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(api_url + path, data=payload, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            parsed = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            parsed = {"raw": raw.decode(errors="replace")}
        return exc.code, parsed


def device_headers(key: str | None = None) -> dict[str, str]:
    headers = {"X-Device-Id": "1", "Authorization": "Device credential-1"}
    if key:
        headers["X-Idempotency-Key"] = key
    return headers


def prepare_device() -> None:
    psql("""
UPDATE device_current_states SET last_seen_at=now(), current_configuration_version=1,
 acknowledged_configuration_version=1, updated_at=now() WHERE device_id=1;
UPDATE devices SET status='ACTIVE' WHERE id=1;
UPDATE wash_bays SET status='IDLE' WHERE device_id=1;
DELETE FROM maintenance_windows WHERE device_id=1;
UPDATE entitlements SET enabled=TRUE WHERE device_id=1 AND program_id=1;
UPDATE program_payment_methods SET enabled=TRUE WHERE program_id=1;
UPDATE program_executions SET status='SUCCESS', completed_at=now()
 WHERE wash_bay_id=1 AND status IN ('CREATED','COMMAND_SENT','RUNNING');
""")


def capture(name: str, action: Callable[[], None], sql: dict[str, list[dict[str, Any]]], semantics: dict[str, int]) -> None:
    reset_stats()
    action()
    snap = sql_snapshot()
    sql[name] = snap
    semantics[name] = semantic_calls(snap)


def run_worker(runtime: str) -> str:
    if runtime == "python":
        code = (
            "import asyncio,json\n"
            "from app.db import get_session_factory\n"
            "from app.worker import sweep_target_runtime\n"
            "async def m():\n"
            "  async with get_session_factory()() as s:\n"
            "    print(json.dumps(await sweep_target_runtime(s)))\n"
            "asyncio.run(m())\n"
        )
        return run(["docker", "compose", "run", "--rm", "python-test", "python", "-c", code])
    return run(["docker", "compose", "run", "--rm", "--entrypoint", "/worker", "go-api"])


def hard_gate() -> dict[str, int]:
    return {
        "duplicate_successful_payment": scalar("""
SELECT count(*) FROM (
 SELECT device_id,idempotency_key FROM payment_transactions
 GROUP BY device_id,idempotency_key
 HAVING count(*) FILTER (WHERE status='SUCCESS') > 1
) x"""),
        "qr_double_redemption": scalar("SELECT count(*) FROM qr_codes WHERE usage_count > usage_limit"),
        "rf_double_spend": scalar("SELECT count(*) FROM rf_wallets WHERE balance_minor < 0"),
        "negative_wallet": scalar("SELECT count(*) FROM rf_wallets WHERE balance_minor < 0"),
        "duplicate_ledger_debit": scalar("""
SELECT count(*) FROM (
 SELECT payment_id FROM rf_wallet_ledger WHERE direction='DEBIT' AND payment_id IS NOT NULL
 GROUP BY payment_id HAVING count(*) > 1
) x"""),
        "idempotency_mismatch": scalar("""
SELECT count(*) FROM (
 SELECT device_id,idempotency_key FROM payment_transactions
 GROUP BY device_id,idempotency_key HAVING count(DISTINCT request_hash) > 1
) x"""),
        "illegal_command_state_transition": scalar("""
SELECT count(*) FROM commands c JOIN program_executions e ON e.id=c.program_execution_id
WHERE c.status IN ('SUCCESS','FAILED') AND e.status <> c.status"""),
        "partial_committed_financial_state": scalar("""
SELECT count(*) FROM payment_transactions p
WHERE p.idempotency_key LIKE 'corr-%' AND (
      (p.status='SUCCESS' AND NOT EXISTS (SELECT 1 FROM start_rights sr WHERE sr.payment_id=p.id))
   OR (p.status='SUCCESS' AND p.method='RF_CARD' AND NOT EXISTS (
        SELECT 1 FROM rf_wallet_ledger l WHERE l.payment_id=p.id AND l.direction='DEBIT'))
)"""),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("runtime", choices=("python", "go"))
    parser.add_argument("profile")
    parser.add_argument("output")
    args = parser.parse_args()
    api_url = os.environ.get("API_URL") or ("http://127.0.0.1:48000" if args.runtime == "python" else "http://127.0.0.1:48001")

    contracts: dict[str, Any] = {}
    sql: dict[str, list[dict[str, Any]]] = {}
    semantics: dict[str, int] = {}

    prepare_device()
    before = scalar("SELECT count(*) FROM device_heartbeats WHERE device_id=1")
    def heartbeat_case() -> None:
        status, payload = request(api_url, "POST", "/api/v1/device/heartbeat", device_headers(), {"sequence": 909090, "app_version": "correctness", "state": {"health": "OK", "signal": 77}})
        assert status == 200 and payload.get("success") is True, (status, payload)
        assert scalar("SELECT count(*) FROM device_heartbeats WHERE device_id=1") == before + 1
        assert psql("SELECT app_version FROM device_current_states WHERE device_id=1") == "correctness"
    capture("heartbeat", heartbeat_case, sql, semantics)
    contracts["heartbeat"] = True

    def configuration_case() -> None:
        status, payload = request(api_url, "GET", "/api/v1/device/configuration?current_version=1", device_headers())
        data = payload.get("data", {})
        assert status == 200 and data.get("version") == 1 and data.get("update_available") is False
        assert data.get("device_id") == "dev-0000001" and data.get("station_id") == "stn-000001"
    capture("configuration", configuration_case, sql, semantics)
    contracts["configuration"] = True

    prepare_device()
    psql("DELETE FROM payment_transactions WHERE idempotency_key LIKE 'corr-card-%'")
    def card_case() -> None:
        base = {"station_program_id": 1, "payment_method": "CARD", "configuration_version": 1, "displayed_price_minor": 1000}
        cases = [
            ("corr-card-success", "TEST_SUCCESS", 200, "SUCCESS"),
            ("corr-card-failed", "TEST_FAILED", 409, "FAILED"),
            ("corr-card-pending", "TEST_TIMEOUT", 202, "PENDING"),
        ]
        for key, scenario, expected_http, expected_db in cases:
            status, payload = request(api_url, "POST", "/api/v1/device/payments", device_headers(key), {**base, "test_scenario": scenario})
            assert status == expected_http, (key, status, payload)
            assert psql(f"SELECT status FROM payment_transactions WHERE idempotency_key='{key}'") == expected_db
    capture("card", card_case, sql, semantics)
    contracts["card"] = True

    prepare_device()
    psql("DELETE FROM payment_transactions WHERE idempotency_key='corr-same-key'")
    def same_key_case() -> None:
        body = {"station_program_id": 1, "payment_method": "CARD", "configuration_version": 1, "displayed_price_minor": 1000, "test_scenario": "TEST_SUCCESS"}
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            responses = list(pool.map(lambda _: request(api_url, "POST", "/api/v1/device/payments", device_headers("corr-same-key"), body), range(10)))
        assert all(status == 200 for status, _ in responses), responses
        ids = {payload["data"]["id"] for _, payload in responses}
        assert len(ids) == 1
        assert scalar("SELECT count(*) FROM payment_transactions WHERE idempotency_key='corr-same-key'") == 1
    capture("same_key", same_key_case, sql, semantics)
    contracts["same_key"] = True

    for concurrency in (2, 10, 100):
        name = f"qr_{concurrency}"
        prepare_device()
        psql(f"DELETE FROM payment_transactions WHERE idempotency_key LIKE 'corr-qr-{concurrency}-%'; UPDATE qr_codes SET usage_count=0,status='ACTIVE' WHERE id=1")
        def qr_case(n: int = concurrency) -> None:
            body = {"payment_method": "QR", "configuration_version": 1, "qr_token": "qr-token-1"}
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(n, 100)) as pool:
                futures = [pool.submit(request, api_url, "POST", "/api/v1/device/payments", device_headers(f"corr-qr-{n}-{i:03d}"), body) for i in range(n)]
                responses = [f.result() for f in futures]
            statuses = [status for status, _ in responses]
            assert statuses.count(200) == 1 and statuses.count(409) == n - 1, statuses
            assert scalar("SELECT usage_count FROM qr_codes WHERE id=1") == 1
            assert scalar(f"SELECT count(*) FROM payment_transactions WHERE idempotency_key LIKE 'corr-qr-{n}-%' AND status='SUCCESS'") == 1
        capture(name, qr_case, sql, semantics)
        contracts[name] = True

    for concurrency in (2, 10, 100):
        name = f"rf_{concurrency}"
        prepare_device()
        psql(f"DELETE FROM payment_transactions WHERE idempotency_key LIKE 'corr-rf-{concurrency}-%'; UPDATE rf_wallets SET balance_minor=1000,version=0,updated_at=now() WHERE id=1")
        def rf_case(n: int = concurrency) -> None:
            body = {"station_program_id": 1, "payment_method": "RF_CARD", "configuration_version": 1, "displayed_price_minor": 1000, "rf_uid": "AABBCCDD00000001"}
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(n, 100)) as pool:
                futures = [pool.submit(request, api_url, "POST", "/api/v1/device/payments", device_headers(f"corr-rf-{n}-{i:03d}"), body) for i in range(n)]
                responses = [f.result() for f in futures]
            statuses = [status for status, _ in responses]
            assert statuses.count(200) == 1 and statuses.count(409) == n - 1, statuses
            assert scalar("SELECT balance_minor FROM rf_wallets WHERE id=1") == 0
            assert scalar(f"SELECT count(*) FROM rf_wallet_ledger l JOIN payment_transactions p ON p.id=l.payment_id WHERE p.idempotency_key LIKE 'corr-rf-{n}-%' AND l.direction='DEBIT'") == 1
        capture(name, rf_case, sql, semantics)
        contracts[name] = True

    psql("""
DELETE FROM command_results WHERE command_id=1;
UPDATE commands SET device_id=1,status='PENDING',sent_at=NULL,acknowledged_at=NULL,completed_at=NULL,result_code=NULL,created_at=now() WHERE id=1;
UPDATE program_executions SET device_id=1,wash_bay_id=1,status='CREATED',started_at=NULL,completed_at=NULL WHERE id=(SELECT program_execution_id FROM commands WHERE id=1);
""")
    def command_case() -> None:
        assert request(api_url, "GET", "/api/v1/device/commands/pending", device_headers())[0] == 200
        assert request(api_url, "POST", "/api/v1/device/commands/1/acknowledge", device_headers())[0] == 200
        body = {"result": "SUCCESS", "code": None, "message": None}
        first = request(api_url, "POST", "/api/v1/device/commands/1/result", device_headers("corr-command-result"), body)
        duplicate = request(api_url, "POST", "/api/v1/device/commands/1/result", device_headers("corr-command-result"), body)
        conflict = request(api_url, "POST", "/api/v1/device/commands/1/result", device_headers("corr-command-result"), {"result": "FAILED", "code": "HW", "message": "different"})
        assert first[0] == 200 and duplicate[0] == 200 and conflict[0] == 409
        assert scalar("SELECT count(*) FROM command_results WHERE command_id=1") == 1
    capture("command", command_case, sql, semantics)
    contracts["command"] = True

    def dashboard_case() -> None:
        status, payload = request(api_url, "GET", "/api/v1/dashboard/overview?period=TODAY", {"Authorization": "Bearer panel-company-1"})
        assert status == 200, (status, payload)
        assert payload["data"]["organization"]["company_count"] == 1
    capture("dashboard", dashboard_case, sql, semantics)
    contracts["dashboard"] = True

    psql("DELETE FROM maintenance_windows; UPDATE device_current_states SET last_seen_at=now(),updated_at=now(); UPDATE device_current_states SET last_seen_at=now()-interval '10 minutes' WHERE device_id=1; DELETE FROM alarms WHERE alarm_key LIKE 'device%offline'")
    def worker_case() -> None:
        run_worker(args.runtime)
        assert scalar("SELECT count(*) FROM alarms WHERE device_id=1 AND alarm_key='device:1:offline' AND status='OPEN'") == 1
        run_worker(args.runtime)
        assert scalar("SELECT count(*) FROM alarms WHERE device_id=1 AND alarm_key='device:1:offline' AND status='OPEN'") == 1
        psql("UPDATE device_current_states SET last_seen_at=now(),updated_at=now() WHERE device_id=1")
        run_worker(args.runtime)
        assert scalar("SELECT count(*) FROM alarms WHERE device_id=1 AND alarm_key='device:1:offline' AND status='RESOLVED'") >= 1
    capture("worker", worker_case, sql, semantics)
    contracts["worker"] = True

    gate = hard_gate()
    result = {
        "runtime": args.runtime,
        "profile": args.profile,
        "hard_gate": gate,
        "contracts": contracts,
        "sql_semantics": semantics,
        "sql": sql,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"output": str(output), "hard_gate": gate, "contracts": contracts, "sql_semantics": semantics}, sort_keys=True))
    if any(gate.values()) or not all(bool(v) for v in contracts.values()):
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, RuntimeError, KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
