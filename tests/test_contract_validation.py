from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_contracts.py"


def run_validator(contract_dir: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["CONTRACT_DIR"] = str(contract_dir)
    return subprocess.run(["python3", str(VALIDATOR)], cwd=ROOT, env=env, text=True, capture_output=True)


def contract(workload: str, *, invariants: list[str] | None = None) -> dict[str, object]:
    return {
        "version": 1,
        "workload": workload,
        "endpoint": {"method": "POST", "path": f"/benchmark/{workload.lower()}"},
        "transaction": {"commit_count": 1},
        "locking": {"required": []},
        "idempotency": {"required": False},
        "invariants": invariants or ["response_contract_preserved"],
        "metrics": ["p50", "p95", "p99", "rps", "cpu", "rss"],
    }


def test_validator_rejects_missing_workload_contracts(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "heartbeat.yaml").write_text(yaml.safe_dump(contract("W1")), encoding="utf-8")
    result = run_validator(tmp_path)
    assert result.returncode != 0
    assert "missing" in (result.stdout + result.stderr).lower()
    assert "w8" in (result.stdout + result.stderr).lower()


def test_validator_rejects_contract_without_invariants(tmp_path: Path) -> None:
    for i in range(1, 9):
        data = contract(f"W{i}")
        if i == 5:
            data["invariants"] = []
        (tmp_path / f"w{i}.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    result = run_validator(tmp_path)
    assert result.returncode != 0
    assert "invariants" in (result.stdout + result.stderr).lower()


def test_validator_accepts_complete_w1_to_w8_contract_set(tmp_path: Path) -> None:
    for i in range(1, 9):
        (tmp_path / f"w{i}.yaml").write_text(yaml.safe_dump(contract(f"W{i}")), encoding="utf-8")
    result = run_validator(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "8/8" in result.stdout
