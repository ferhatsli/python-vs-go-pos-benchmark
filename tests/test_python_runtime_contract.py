from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def python_api_block() -> str:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    marker = "  python-api:\n"
    assert marker in compose
    tail = compose.split(marker, 1)[1]
    match = re.search(r"\n  [A-Za-z0-9_-]+:\n", tail)
    return tail if match is None else tail[: match.start()]


def test_python_api_runtime_uses_canonical_resource_budget() -> None:
    service = python_api_block()
    assert "cpus: 2.0" in service
    assert "mem_limit: 1g" in service
    assert "BENCH_DATABASE_URL: postgresql+asyncpg://benchmark:benchmark-local-only@postgres:5432/pos_benchmark" in service
    assert "--port" in service
    assert '"8000"' in service


def test_python_db_pool_is_exactly_forty_without_overflow() -> None:
    settings = (ROOT / "python" / "app" / "settings.py").read_text(encoding="utf-8")
    db = (ROOT / "python" / "app" / "db.py").read_text(encoding="utf-8")
    assert "DB_POOL_SIZE = 40" in settings
    assert "DB_MAX_OVERFLOW = 0" in settings
    assert "pool_size=DB_POOL_SIZE" in db
    assert "max_overflow=DB_MAX_OVERFLOW" in db


def test_python_runtime_image_contains_application_source() -> None:
    dockerfile = (ROOT / "python" / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY app /workspace/app" in dockerfile
