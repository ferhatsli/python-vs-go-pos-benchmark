from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_worker_runtime_entrypoints_report_internal_sweep_duration() -> None:
    py = ROOT / "python" / "app" / "worker_cli.py"
    go = ROOT / "go" / "cmd" / "worker" / "main.go"
    assert py.exists()
    py_src = py.read_text(encoding="utf-8")
    go_src = go.read_text(encoding="utf-8")
    assert "perf_counter" in py_src and "duration_ms" in py_src
    assert "time.Since" in go_src and "duration_ms" in go_src


def test_worker_services_use_same_resource_budget() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    import re
    for service in ("python-worker", "go-worker"):
        marker = f"  {service}:\n"
        assert marker in compose
        tail = compose.split(marker, 1)[1]
        match = re.search(r"\n  [A-Za-z0-9_-]+:\n", tail)
        block = tail if match is None else tail[: match.start()]
        assert "cpus: 2.0" in block
        assert "mem_limit: 1g" in block
    assert "python -m app.worker_cli" in compose or 'command: ["python", "-m", "app.worker_cli"]' in compose
    assert 'entrypoint: ["/worker"]' in compose


def test_run_scenario_supports_worker_artifacts_without_k6() -> None:
    source = (ROOT / "scripts" / "run_scenario.sh").read_text(encoding="utf-8")
    assert "worker)" in source
    assert "worker-summary.json" in source
    assert "python-worker" in source and "go-worker" in source
    assert "devices_evaluated" in source
    assert "overrun_5s" in source


def test_verify_result_accepts_worker_summary() -> None:
    source = (ROOT / "scripts" / "verify_result.sh").read_text(encoding="utf-8")
    assert "worker-summary.json" in source
    assert "worker_returncode" in source


def test_matrix_uses_worker_duration_for_cv() -> None:
    source = (ROOT / "scripts" / "run_matrix.sh").read_text(encoding="utf-8")
    assert "worker-summary.json" in source
    assert "duration_ms" in source
