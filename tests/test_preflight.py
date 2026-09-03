from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "preflight.sh"


def run_script(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.update(env)
    return subprocess.run(["bash", str(SCRIPT)], cwd=ROOT, env=merged, text=True, capture_output=True)


def init_repo(path: Path) -> None:
    path.mkdir()
    subprocess.run(["git", "init", "-q", str(path)], check=True)


def test_preflight_rejects_missing_pos_repo(tmp_path: Path) -> None:
    result = run_script({
        "POS_ROOT": str(tmp_path / "missing"),
        "BENCH_ROOT": str(tmp_path / "bench"),
        "SKIP_TOOL_CHECKS": "1",
    })
    assert result.returncode != 0
    assert "pos_root" in (result.stdout + result.stderr).lower()


def test_preflight_captures_initial_pos_status(tmp_path: Path) -> None:
    pos = tmp_path / "pos"
    bench = tmp_path / "bench"
    init_repo(pos)
    bench.mkdir()
    (pos / "untracked.txt").write_text("keep-me\n", encoding="utf-8")
    baseline = tmp_path / "baseline.txt"
    result = run_script({
        "POS_ROOT": str(pos),
        "BENCH_ROOT": str(bench),
        "ISOLATION_BASELINE_FILE": str(baseline),
        "SKIP_TOOL_CHECKS": "1",
    })
    assert result.returncode == 0, result.stdout + result.stderr
    assert baseline.exists()
    assert baseline.read_text(encoding="utf-8") == "?? untracked.txt\n"


def test_preflight_does_not_mutate_pos_repo(tmp_path: Path) -> None:
    pos = tmp_path / "pos"
    bench = tmp_path / "bench"
    init_repo(pos)
    bench.mkdir()
    before = subprocess.check_output(["git", "-C", str(pos), "status", "--porcelain=v1"], text=True)
    result = run_script({
        "POS_ROOT": str(pos),
        "BENCH_ROOT": str(bench),
        "ISOLATION_BASELINE_FILE": str(tmp_path / "baseline.txt"),
        "SKIP_TOOL_CHECKS": "1",
    })
    after = subprocess.check_output(["git", "-C", str(pos), "status", "--porcelain=v1"], text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert before == after
