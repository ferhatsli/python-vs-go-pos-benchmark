from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_isolation.sh"


def run_script(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.update(env)
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=ROOT,
        env=merged,
        text=True,
        capture_output=True,
    )


def test_isolation_rejects_benchmark_nested_in_pos(tmp_path: Path) -> None:
    pos = tmp_path / "pos"
    bench = pos / "bench"
    pos.mkdir()
    bench.mkdir()
    subprocess.run(["git", "init", "-q", str(pos)], check=True)
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("", encoding="utf-8")
    result = run_script({"POS_ROOT": str(pos), "BENCH_ROOT": str(bench), "ISOLATION_BASELINE_FILE": str(baseline)})
    assert result.returncode != 0
    assert "nested" in (result.stdout + result.stderr).lower()


def test_isolation_rejects_changed_pos_status(tmp_path: Path) -> None:
    pos = tmp_path / "pos"
    bench = tmp_path / "bench"
    pos.mkdir()
    bench.mkdir()
    subprocess.run(["git", "init", "-q", str(pos)], check=True)
    subprocess.run(["git", "-C", str(pos), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(pos), "config", "user.name", "Test"], check=True)
    (pos / "tracked.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(pos), "add", "tracked.txt"], check=True)
    subprocess.run(["git", "-C", str(pos), "commit", "-qm", "init"], check=True)
    baseline_text = subprocess.check_output(["git", "-C", str(pos), "status", "--porcelain=v1"], text=True)
    baseline = tmp_path / "baseline.txt"
    baseline.write_text(baseline_text, encoding="utf-8")
    (pos / "tracked.txt").write_text("b\n", encoding="utf-8")
    result = run_script({"POS_ROOT": str(pos), "BENCH_ROOT": str(bench), "ISOLATION_BASELINE_FILE": str(baseline)})
    assert result.returncode != 0
    assert "changed" in (result.stdout + result.stderr).lower()


def test_isolation_accepts_unchanged_independent_repo(tmp_path: Path) -> None:
    pos = tmp_path / "pos"
    bench = tmp_path / "bench"
    pos.mkdir()
    bench.mkdir()
    subprocess.run(["git", "init", "-q", str(pos)], check=True)
    baseline_text = subprocess.check_output(["git", "-C", str(pos), "status", "--porcelain=v1"], text=True)
    baseline = tmp_path / "baseline.txt"
    baseline.write_text(baseline_text, encoding="utf-8")
    result = run_script({"POS_ROOT": str(pos), "BENCH_ROOT": str(bench), "ISOLATION_BASELINE_FILE": str(baseline)})
    assert result.returncode == 0, result.stdout + result.stderr


def test_workload_mode_allows_unrelated_pos_drift_but_protects_workload_sources(tmp_path: Path) -> None:
    import hashlib

    pos = tmp_path / "pos"
    bench = tmp_path / "bench"
    pos.mkdir()
    bench.mkdir()
    subprocess.run(["git", "init", "-q", str(pos)], check=True)
    protected = pos / "protected.py"
    protected.write_text("baseline\n", encoding="utf-8")
    digest = hashlib.sha256(protected.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        "files:\n"
        f"  protected.py: {digest}\n"
        "workloads:\n"
        "  W1:\n"
        "  - protected.py\n",
        encoding="utf-8",
    )
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("", encoding="utf-8")
    (pos / "unrelated.md").write_text("external work\n", encoding="utf-8")

    env = {
        "POS_ROOT": str(pos),
        "BENCH_ROOT": str(bench),
        "ISOLATION_BASELINE_FILE": str(baseline),
        "ISOLATION_MODE": "workload",
        "ISOLATION_MANIFEST_FILE": str(manifest),
    }
    allowed = run_script(env)
    assert allowed.returncode == 0, allowed.stdout + allowed.stderr
    assert "workload source hashes" in (allowed.stdout + allowed.stderr).lower()

    protected.write_text("changed\n", encoding="utf-8")
    rejected = run_script(env)
    assert rejected.returncode != 0
    assert "protected workload source changed" in (rejected.stdout + rejected.stderr).lower()


def test_frozen_mode_validates_manifest_commit_instead_of_worktree(tmp_path: Path) -> None:
    import hashlib

    pos = tmp_path / "pos"
    bench = tmp_path / "bench"
    pos.mkdir()
    bench.mkdir()
    subprocess.run(["git", "init", "-q", str(pos)], check=True)
    subprocess.run(["git", "-C", str(pos), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(pos), "config", "user.name", "Test"], check=True)
    protected = pos / "protected.py"
    protected.write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(pos), "add", "protected.py"], check=True)
    subprocess.run(["git", "-C", str(pos), "commit", "-qm", "freeze"], check=True)
    frozen = subprocess.check_output(["git", "-C", str(pos), "rev-parse", "HEAD"], text=True).strip()
    digest = hashlib.sha256(protected.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        "git:\n"
        f"  head: {frozen}\n"
        "files:\n"
        f"  protected.py: {digest}\n"
        "workloads:\n"
        "  W1:\n"
        "  - protected.py\n",
        encoding="utf-8",
    )
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("", encoding="utf-8")
    protected.write_text("parallel current work\n", encoding="utf-8")
    (pos / "unrelated.md").write_text("external work\n", encoding="utf-8")

    env = {
        "POS_ROOT": str(pos),
        "BENCH_ROOT": str(bench),
        "ISOLATION_BASELINE_FILE": str(baseline),
        "ISOLATION_MODE": "frozen",
        "ISOLATION_MANIFEST_FILE": str(manifest),
    }
    result = run_script(env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "frozen workload source hashes unchanged" in result.stdout.lower()

    manifest.write_text(manifest.read_text(encoding="utf-8").replace(digest, "0" * 64), encoding="utf-8")
    rejected = run_script(env)
    assert rejected.returncode != 0
    assert "frozen workload source mismatch" in (rejected.stdout + rejected.stderr).lower()


def _init_benchmark_repo(path: Path) -> None:
    path.mkdir()
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True)
    (path / "README.md").write_text("public benchmark\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "init"], check=True)


def test_public_mode_requires_provenance_and_clean_benchmark_repo(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _init_benchmark_repo(bench)
    provenance = tmp_path / "public-provenance.json"
    provenance.write_text('{"frozen_source_commit":"abc123","protected_workloads":{}}\n', encoding="utf-8")

    result = run_script({
        "BENCH_ROOT": str(bench),
        "ISOLATION_MODE": "public",
        "PUBLIC_PROVENANCE_FILE": str(provenance),
    })
    assert result.returncode == 0, result.stdout + result.stderr
    assert "public reproduction boundary verified" in result.stdout.lower()
    assert "frozen workload source hashes unchanged" not in result.stdout.lower()

    (bench / "README.md").write_text("dirty\n", encoding="utf-8")
    rejected = run_script({
        "BENCH_ROOT": str(bench),
        "ISOLATION_MODE": "public",
        "PUBLIC_PROVENANCE_FILE": str(provenance),
    })
    assert rejected.returncode != 0
    assert "benchmark worktree is not clean" in (rejected.stdout + rejected.stderr).lower()


def test_public_mode_allows_only_generated_results_when_overwrite_enabled(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _init_benchmark_repo(bench)
    provenance = tmp_path / "public-provenance.json"
    provenance.write_text('{"frozen_source_commit":"abc123","protected_workloads":{}}\n', encoding="utf-8")
    (bench / "results").mkdir()
    (bench / "results" / "generated.json").write_text("{}\n", encoding="utf-8")

    allowed = run_script({
        "BENCH_ROOT": str(bench),
        "ISOLATION_MODE": "public",
        "PUBLIC_PROVENANCE_FILE": str(provenance),
        "BENCH_OVERWRITE": "1",
    })
    assert allowed.returncode == 0, allowed.stdout + allowed.stderr

    (bench / "README.md").write_text("dirty\n", encoding="utf-8")
    rejected = run_script({
        "BENCH_ROOT": str(bench),
        "ISOLATION_MODE": "public",
        "PUBLIC_PROVENANCE_FILE": str(provenance),
        "BENCH_OVERWRITE": "1",
    })
    assert rejected.returncode != 0
