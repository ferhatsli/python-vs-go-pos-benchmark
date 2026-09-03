from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def text(name: str) -> str:
    return (SCRIPTS / name).read_text(encoding="utf-8")


def test_orchestrator_files_exist() -> None:
    for name in ("start_stack.sh", "stop_stack.sh", "reset_dataset.sh", "run_scenario.sh", "run_matrix.sh"):
        assert (SCRIPTS / name).exists(), name


def test_start_stack_enforces_one_api_at_a_time_and_health() -> None:
    source = text("start_stack.sh")
    assert "python-api" in source and "go-api" in source
    assert "docker compose stop" in source
    assert "--status running" in source
    assert "Health.Status" in source or "State.Health.Status" in source
    assert "healthy" in source


def test_reset_dataset_verifies_deterministic_fingerprint() -> None:
    source = text("reset_dataset.sh")
    assert "--fingerprint-only" in source
    assert "pg_isready" in source
    assert "to_regclass('public.devices')" in source
    assert "db/001_schema.sql" in source
    assert "stable_keys_sha256" in source
    assert "schema_hash" in source
    assert "row_counts" in source
    assert "fingerprint mismatch" in source.lower()


def test_run_scenario_enforces_canonical_trial_order() -> None:
    source = text("run_scenario.sh")
    required = [
        "verify_isolation.sh",
        "stop_stack.sh",
        "reset_dataset.sh",
        "pg_stat_statements_reset",
        "start_stack.sh",
        "metrics/collect.sh pre",
        "k6",
        "metrics/collect.sh post",
        "capture_invariants",
        "stop_stack.sh",
    ]
    positions = []
    cursor = -1
    for token in required:
        position = source.find(token, cursor + 1)
        assert position >= 0, token
        positions.append(position)
        cursor = position
    assert positions == sorted(positions)
    assert "summary-export" in source
    assert '-v "$OUT_DIR:/results"' in source
    assert "--summary-export /results/k6-summary.json" in source
    assert "dataset.json" in source


def test_verify_result_supports_trial_artifacts() -> None:
    source = text("verify_result.sh")
    assert "trial.json" in source
    assert "k6_returncode" in source
    assert "invariants.txt" in source


def test_run_matrix_uses_repo_global_nonblocking_lock() -> None:
    source = text("run_matrix.sh")
    assert ".benchmark-matrix.lock" in source
    assert "flock -n" in source
    assert "another benchmark matrix is already running" in source
    assert 'export BENCH_MATRIX_LOCK_HELD=1' in source


def test_standalone_scenario_uses_same_global_lock() -> None:
    source = text("run_scenario.sh")
    assert ".benchmark-matrix.lock" in source
    assert 'BENCH_MATRIX_LOCK_HELD' in source
    assert "flock -n" in source
    assert "another benchmark run is already active" in source


def test_run_matrix_uses_exact_ab_ba_blocks_and_two_warmups() -> None:
    source = text("run_matrix.sh")
    assert "python go" in source
    assert "go python" in source
    blocks = re.findall(r"BLOCK_ORDERS\[[0-9]+\]=\"(python go|go python)\"", source)
    assert blocks == ["python go", "go python", "python go", "go python", "python go"]
    assert "WARMUP_RUNS=2" in source
    assert "MIN_MEASURED_RUNS=5" in source
    assert "MAX_MEASURED_RUNS=10" in source
    assert "CV_LIMIT_PERCENT=10" in source
    assert "UNSTABLE" in source
    assert "p(95)" in source
