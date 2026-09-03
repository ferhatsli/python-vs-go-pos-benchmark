from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NORMALIZE = ROOT / "metrics" / "normalize.py"


def result(runtime: str, *, success: int = 1, steps: dict[str, int] | None = None) -> dict[str, object]:
    return {
        "runtime": runtime,
        "profile": "D1",
        "hard_gate": {
            "duplicate_successful_payment": 0,
            "qr_double_redemption": 0,
            "rf_double_spend": 0,
            "negative_wallet": 0,
            "duplicate_ledger_debit": 0,
            "idempotency_mismatch": 0,
            "illegal_command_state_transition": 0,
            "partial_committed_financial_state": 0,
        },
        "contracts": {
            "heartbeat": True,
            "configuration": True,
            "card": True,
            "same_key": True,
            "qr_2": True,
            "qr_10": True,
            "qr_100": True,
            "rf_2": True,
            "rf_10": True,
            "rf_100": True,
            "command": True,
            "worker": True,
            "success_count": success,
        },
        "sql_semantics": steps or {"heartbeat": 6, "configuration": 3, "card": 18},
        "sql": {"heartbeat": [{"query": "SELECT $1", "calls": 1, "rows": 1, "total_exec_time_ms": 0.2}]},
    }


def run_compare(tmp_path: Path, left: dict[str, object], right: dict[str, object]) -> subprocess.CompletedProcess[str]:
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps(left), encoding="utf-8")
    b.write_text(json.dumps(right), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(NORMALIZE), "compare-correctness", str(a), str(b)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_compare_correctness_accepts_equal_semantics_and_ignores_timing(tmp_path: Path) -> None:
    left = result("python")
    right = result("go")
    right["sql"]["heartbeat"][0]["total_exec_time_ms"] = 9.9  # type: ignore[index]
    proc = run_compare(tmp_path, left, right)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PASS" in proc.stdout


def test_compare_correctness_rejects_contract_or_sql_semantic_divergence(tmp_path: Path) -> None:
    left = result("python")
    right = result("go", success=2, steps={"heartbeat": 5, "configuration": 3, "card": 18})
    proc = run_compare(tmp_path, left, right)
    assert proc.returncode != 0
    assert "FAIL" in proc.stdout
    assert "contracts" in proc.stdout
    assert "sql_semantics" in proc.stdout


def test_correctness_orchestrator_includes_full_contention_matrix() -> None:
    script = (ROOT / "scripts" / "run_correctness.sh").read_text(encoding="utf-8")
    for value in ("2", "10", "100"):
        assert f"qr_{value}" in script
        assert f"rf_{value}" in script
    assert "pg_stat_statements_reset" in script
    assert "correctness.json" in script


def test_database_invariants_include_cross_runtime_financial_and_command_gates() -> None:
    sql = (ROOT / "db" / "checks" / "invariants.sql").read_text(encoding="utf-8")
    assert "count(DISTINCT request_hash)" in sql
    assert "c.status IN ('SUCCESS', 'FAILED') AND e.status <> c.status" in sql
    assert "p.idempotency_key LIKE 'corr-%'" in sql
    assert "NOT EXISTS (SELECT 1 FROM start_rights" in sql
