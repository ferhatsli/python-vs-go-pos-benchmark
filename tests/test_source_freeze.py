from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "scripts" / "freeze_source.sh"

RELEVANT = [
    "apps/api/app/main.py",
    "apps/api/app/infrastructure/database.py",
    "apps/api/app/infrastructure/cache.py",
    "apps/api/app/application/target_payments.py",
    "apps/api/app/application/target_catalog_devices.py",
    "apps/api/app/application/target_worker.py",
    "apps/api/app/api/routes/target_payments.py",
    "apps/api/app/api/routes/target_catalog_devices.py",
    "apps/api/app/domain/target/payments.py",
    "apps/api/app/domain/target/devices.py",
    "apps/api/app/domain/target/cashier.py",
    "apps/api/pyproject.toml",
    "apps/api/uv.lock",
    "docker-compose.yml",
    "infrastructure/target-acceptance.compose.yml",
    "performance/phase11-authenticated-load.js",
    "docs/43-scale-performance-and-service-levels.md",
]


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def init_fixture(root: Path) -> None:
    for rel in RELEVANT:
        content = f"# fixture {rel}\n"
        if rel.endswith("pyproject.toml"):
            content = '''[project]\nrequires-python = ">=3.12,<3.13"\ndependencies = [\n  "fastapi>=0.116.1",\n  "asyncpg>=0.30.0",\n  "redis>=6.2.0",\n  "sqlalchemy[asyncio]>=2.0.41",\n  "uvicorn[standard]>=0.35.0",\n]\n'''
        elif rel == "docker-compose.yml":
            content = "services:\n  postgres:\n    image: postgres:17\n  redis:\n    image: redis:7.4-alpine\n"
        elif rel == "infrastructure/target-acceptance.compose.yml":
            content = "services:\n  postgres:\n    image: postgres:17\n  redis:\n    image: redis:7.4-alpine\n"
        write(root / rel, content)
    subprocess.run(["git", "init", "-q", "-b", "feature/test-source", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "fixture@example.com"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Fixture"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)


def run_freeze(pos: Path, out_dir: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update({"POS_ROOT": str(pos), "SOURCE_FREEZE_DIR": str(out_dir)})
    return subprocess.run(["bash", str(FREEZE)], cwd=ROOT, env=env, text=True, capture_output=True)


def test_freeze_records_branch_head_hashes_and_runtime_metadata(tmp_path: Path) -> None:
    pos = tmp_path / "pos"
    init_fixture(pos)
    out = tmp_path / "out"
    result = run_freeze(pos, out)
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = yaml.safe_load((out / "source-manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["git"]["branch"] == "feature/test-source"
    assert manifest["git"]["head"] == subprocess.check_output(["git", "-C", str(pos), "rev-parse", "HEAD"], text=True).strip()
    assert manifest["runtime"]["python"] == ">=3.12,<3.13"
    assert manifest["runtime"]["postgres_image"] == "postgres:17"
    assert manifest["runtime"]["redis_image"] == "redis:7.4-alpine"
    payment = pos / "apps/api/app/application/target_payments.py"
    expected = hashlib.sha256(payment.read_bytes()).hexdigest()
    assert manifest["files"]["apps/api/app/application/target_payments.py"] == expected
    assert manifest["workloads"]["W5"] == ["apps/api/app/application/target_payments.py", "apps/api/app/domain/target/cashier.py"]


def test_freeze_rejects_dirty_selected_workload_file(tmp_path: Path) -> None:
    pos = tmp_path / "pos"
    init_fixture(pos)
    target = pos / "apps/api/app/application/target_payments.py"
    target.write_text(target.read_text(encoding="utf-8") + "# dirty\n", encoding="utf-8")
    result = run_freeze(pos, tmp_path / "out")
    assert result.returncode != 0
    combined = (result.stdout + result.stderr).lower()
    assert "dirty" in combined
    assert "target_payments.py" in combined


def test_freeze_ignores_unrelated_dirty_file_but_records_status(tmp_path: Path) -> None:
    pos = tmp_path / "pos"
    init_fixture(pos)
    write(pos / "unrelated.txt", "not selected\n")
    out = tmp_path / "out"
    result = run_freeze(pos, out)
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = yaml.safe_load((out / "source-manifest.yaml").read_text(encoding="utf-8"))
    assert "?? unrelated.txt" in manifest["git"]["status"]
