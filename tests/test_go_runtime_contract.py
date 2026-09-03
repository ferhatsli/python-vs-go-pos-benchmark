from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def service_block(name: str) -> str:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    marker = f"  {name}:\n"
    assert marker in compose
    tail = compose.split(marker, 1)[1]
    match = re.search(r"\n  [A-Za-z0-9_-]+:\n", tail)
    return tail if match is None else tail[: match.start()]


def test_go_toolchain_and_module_are_pinned() -> None:
    gomod = (ROOT / "go" / "go.mod").read_text(encoding="utf-8")
    dockerfile = (ROOT / "go" / "Dockerfile").read_text(encoding="utf-8")
    assert "go 1.27" in gomod
    assert "FROM golang:1.27.0" in dockerfile


def test_go_api_runtime_uses_canonical_resource_budget() -> None:
    service = service_block("go-api")
    assert "cpus: 2.0" in service
    assert "mem_limit: 1g" in service
    assert "BENCH_DATABASE_URL: postgres://benchmark:benchmark-local-only@postgres:5432/pos_benchmark" in service


def test_go_pool_budget_is_exactly_forty() -> None:
    db_file = ROOT / "go" / "internal" / "db" / "db.go"
    assert db_file.exists()
    source = db_file.read_text(encoding="utf-8")
    assert "MaxConns = 40" in source


def test_go_runtime_entrypoints_exist_and_support_healthcheck() -> None:
    api_main = ROOT / "go" / "cmd" / "api" / "main.go"
    worker_main = ROOT / "go" / "cmd" / "worker" / "main.go"
    assert api_main.exists()
    assert worker_main.exists()
    api_source = api_main.read_text(encoding="utf-8")
    config_source = (ROOT / "go" / "internal" / "config" / "config.go").read_text(encoding="utf-8")
    assert '"-healthcheck"' in api_source
    assert "BENCH_HTTP_ADDR" in config_source
