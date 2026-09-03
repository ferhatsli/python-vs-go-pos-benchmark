from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import yaml

RELEVANT_FILES = [
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

WORKLOADS = {
    "W1": [
        "apps/api/app/application/target_catalog_devices.py",
        "apps/api/app/api/routes/target_catalog_devices.py",
        "apps/api/app/domain/target/devices.py",
    ],
    "W2": [
        "apps/api/app/application/target_catalog_devices.py",
        "apps/api/app/api/routes/target_catalog_devices.py",
        "apps/api/app/domain/target/devices.py",
    ],
    "W3": [
        "apps/api/app/application/target_payments.py",
        "apps/api/app/domain/target/payments.py",
    ],
    "W4": [
        "apps/api/app/application/target_payments.py",
        "apps/api/app/domain/target/cashier.py",
    ],
    "W5": [
        "apps/api/app/application/target_payments.py",
        "apps/api/app/domain/target/cashier.py",
    ],
    "W6": ["performance/phase11-authenticated-load.js"],
    "W7": [
        "apps/api/app/application/target_payments.py",
        "apps/api/app/api/routes/target_payments.py",
    ],
    "W8": ["apps/api/app/application/target_worker.py"],
}

DEPENDENCY_NAMES = {"fastapi", "asyncpg", "redis", "sqlalchemy", "uvicorn", "pydantic"}


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).rstrip("\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_pyproject(path: Path) -> tuple[str | None, list[str]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    project = data.get("project", {})
    return project.get("requires-python"), list(project.get("dependencies", []))


def parse_lock_versions(path: Path) -> dict[str, str]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return {}
    versions: dict[str, str] = {}
    for pkg in data.get("package", []):
        name = str(pkg.get("name", ""))
        if name in DEPENDENCY_NAMES and pkg.get("version"):
            versions[name] = str(pkg["version"])
    return versions


def compose_images(path: Path) -> tuple[str | None, str | None]:
    if not path.exists():
        return None, None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    services = data.get("services", {}) or {}
    pg = (services.get("postgres") or {}).get("image")
    redis = (services.get("redis") or {}).get("image")
    return pg, redis


def main() -> int:
    raw_pos_root = os.environ.get("POS_ROOT")
    if not raw_pos_root:
        print("ERROR: POS_ROOT must be set for private source-freeze operations", file=sys.stderr)
        return 19
    pos_root = Path(raw_pos_root).resolve()
    out_dir = Path(os.environ.get("SOURCE_FREEZE_DIR", "docs/source-freeze")).resolve()

    if not pos_root.exists():
        print(f"ERROR: POS_ROOT does not exist: {pos_root}", file=sys.stderr)
        return 20
    if not (pos_root / ".git").exists():
        print(f"ERROR: POS_ROOT is not a git repository: {pos_root}", file=sys.stderr)
        return 21

    missing = [rel for rel in RELEVANT_FILES if not (pos_root / rel).is_file()]
    if missing:
        print("ERROR: required source files are missing:\n" + "\n".join(missing), file=sys.stderr)
        return 22

    dirty_selected = git(pos_root, "status", "--porcelain=v1", "--", *RELEVANT_FILES)
    if dirty_selected.strip():
        print("ERROR: selected benchmark source is dirty; freeze refused:\n" + dirty_selected, file=sys.stderr)
        return 23

    branch = git(pos_root, "branch", "--show-current")
    head = git(pos_root, "rev-parse", "HEAD")
    status = git(pos_root, "status", "--porcelain=v1")

    python_req, dependency_constraints = parse_pyproject(pos_root / "apps/api/pyproject.toml")
    locked_versions = parse_lock_versions(pos_root / "apps/api/uv.lock")
    pg_image, redis_image = compose_images(pos_root / "docker-compose.yml")
    if not pg_image or not redis_image:
        alt_pg, alt_redis = compose_images(pos_root / "infrastructure/target-acceptance.compose.yml")
        pg_image = pg_image or alt_pg
        redis_image = redis_image or alt_redis

    manifest = {
        "source_root": str(pos_root),
        "git": {"branch": branch, "head": head, "status": status},
        "runtime": {
            "python": python_req,
            "postgres_image": pg_image,
            "redis_image": redis_image,
            "dependency_constraints": dependency_constraints,
            "locked_versions": locked_versions,
        },
        "files": {rel: sha256(pos_root / rel) for rel in RELEVANT_FILES},
        "workloads": WORKLOADS,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = out_dir / "source-manifest.yaml"
    yaml_path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")

    md_lines = [
        "# POS Source Manifest",
        "",
        f"- Source root: `{pos_root}`",
        f"- Branch: `{branch}`",
        f"- HEAD: `{head}`",
        f"- Python target: `{python_req}`",
        f"- PostgreSQL image: `{pg_image}`",
        f"- Redis image: `{redis_image}`",
        "",
        "## Frozen file hashes",
        "",
    ]
    md_lines.extend(f"- `{rel}` — `{digest}`" for rel, digest in manifest["files"].items())
    md_lines.extend(["", "## Git status at freeze", "", "```text", status or "(clean)", "```", ""])
    (out_dir / "source-manifest.md").write_text("\n".join(md_lines), encoding="utf-8")
    print(f"PASS: source frozen at {head} ({branch})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
