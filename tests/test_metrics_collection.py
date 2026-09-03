from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_postgres_metric_queries_cover_required_evidence() -> None:
    snapshot = (ROOT / "metrics" / "snapshot.sql").read_text(encoding="utf-8")
    locks = (ROOT / "metrics" / "lock-sampler.sql").read_text(encoding="utf-8")
    collect = (ROOT / "metrics" / "collect.sh").read_text(encoding="utf-8")
    for token in ("pg_stat_database", "pg_stat_wal", "pg_stat_activity", "pg_database_size"):
        assert token in snapshot
    for token in ("pg_stat_statements", "calls", "rows", "total_exec_time", "wal_bytes"):
        assert token in collect
    assert "query NOT ILIKE '%pg_stat_%'" in collect
    assert "query NOT ILIKE '%pg_database_size%'" in collect
    for token in ("wait_event_type", "wait_event", "pg_blocking_pids", "pg_locks"):
        assert token in locks
    assert "wait_event_type = 'Lock'" in locks
    assert "cardinality(blocked_by) > 0" in locks
    assert "wait_event_type IS NOT NULL OR cardinality(blocked_by) > 0" not in locks


def test_collector_supports_pre_sample_post_and_container_metrics() -> None:
    collect = (ROOT / "metrics" / "collect.sh").read_text(encoding="utf-8")
    for mode in ("pre", "sample", "post", "diagnostic"):
        assert mode in collect
    assert "usage: metrics/collect.sh <pre|sample|post|diagnostic> <output-dir> [python|go]" in collect
    assert "docker stats" in collect
    assert "docker top" in collect
    assert "python-api" in collect and "go-api" in collect and "postgres" in collect
    assert "BENCH_DIAGNOSTIC" in collect
    assert "pprof" in collect
    assert "py-spy" in collect


def write_run_fixture(root: Path) -> None:
    pre = {
        "database": {"xact_commit": 100, "temp_files": 2, "deadlocks": 0},
        "wal": {"wal_bytes": "1000"},
        "connections": {"total": 3, "active": 1},
        "database_size_bytes": 10000,
    }
    post = {
        "database": {"xact_commit": 160, "temp_files": 3, "deadlocks": 0},
        "wal": {"wal_bytes": "5000"},
        "connections": {"total": 4, "active": 2},
        "database_size_bytes": 12000,
    }
    (root / "pg_pre.json").write_text(json.dumps(pre), encoding="utf-8")
    (root / "pg_post.json").write_text(json.dumps(post), encoding="utf-8")
    (root / "statements_pre.csv").write_text(
        "queryid,calls,rows,total_exec_time,wal_bytes\n1,10,20,100.0,200\n2,5,10,50.0,50\n",
        encoding="utf-8",
    )
    (root / "statements_post.csv").write_text(
        "queryid,calls,rows,total_exec_time,wal_bytes\n1,40,80,340.0,800\n2,15,30,130.0,250\n",
        encoding="utf-8",
    )
    (root / "lock_samples.ndjson").write_text(
        "\n".join(
            [
                json.dumps({"connections_total": 5, "waiting_count": 0, "lock_count": 8}),
                json.dumps({"connections_total": 7, "waiting_count": 2, "lock_count": 12}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "container_samples.ndjson").write_text(
        "\n".join(
            [
                json.dumps({"role": "api", "process_count": 2, "stats": {"CPUPerc": "25.00%", "MemUsage": "100MiB / 1GiB"}}),
                json.dumps({"role": "postgres", "process_count": 8, "stats": {"CPUPerc": "50.00%", "MemUsage": "500MiB / 4GiB"}}),
                json.dumps({"role": "postgres", "process_count": 9, "stats": {"CPUPerc": "70.00%", "MemUsage": "600MiB / 4GiB"}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_normalize_derive_run_computes_required_deltas(tmp_path: Path) -> None:
    write_run_fixture(tmp_path)
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "metrics" / "normalize.py"),
            "derive-run",
            str(tmp_path),
            "--duration-seconds",
            "10",
            "--requests",
            "20",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(proc.stdout)
    assert data["wal_bytes_per_second"] == 400.0
    assert data["db_statements_per_request"] == 2.0
    assert data["db_rows_per_request"] == 4.0
    assert data["db_exec_time_ms_per_request"] == 16.0
    assert data["connection_high_water"] == 7
    assert data["lock_wait_samples"] == 1
    assert data["max_waiting_backends"] == 2
    assert data["postgres_cpu_percent_max"] == 70.0
    assert data["postgres_process_high_water"] == 9
