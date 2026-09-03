#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any


def load(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def compare_correctness(left: dict[str, Any], right: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []

    for label, payload in (("left", left), ("right", right)):
        hard_gate = payload.get("hard_gate", {})
        nonzero = {k: v for k, v in hard_gate.items() if v != 0}
        if nonzero:
            failures.append(f"{label}.hard_gate={nonzero}")

    if left.get("profile") != right.get("profile"):
        failures.append(f"profile: {left.get('profile')} != {right.get('profile')}")
    if left.get("contracts") != right.get("contracts"):
        failures.append("contracts differ")
    if left.get("sql_semantics") != right.get("sql_semantics"):
        failures.append("sql_semantics differ")
    return not failures, failures


def command_compare_correctness(left_path: str, right_path: str) -> int:
    left = load(left_path)
    right = load(right_path)
    ok, failures = compare_correctness(left, right)
    if ok:
        print(
            "PASS: cross-runtime correctness parity accepted "
            f"({left.get('runtime')} vs {right.get('runtime')}, profile={left.get('profile')})"
        )
        return 0
    print("FAIL: cross-runtime correctness parity rejected")
    for failure in failures:
        print(f"- {failure}")
    return 1


def read_statement_csv(path: Path) -> dict[str, dict[str, float]]:
    if not path.exists():
        return {}
    rows: dict[str, dict[str, float]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            queryid = str(row.get("queryid", ""))
            rows[queryid] = {
                "calls": float(row.get("calls") or 0),
                "rows": float(row.get("rows") or 0),
                "total_exec_time": float(row.get("total_exec_time") or 0),
                "wal_bytes": float(row.get("wal_bytes") or 0),
            }
    return rows


def read_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    output: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            output.append(json.loads(line))
    return output


def percent(value: Any) -> float:
    text = str(value or "0").strip().removesuffix("%")
    try:
        return float(text)
    except ValueError:
        return 0.0


def memory_bytes(value: Any) -> float:
    text = str(value or "0").split("/", 1)[0].strip()
    match = re.fullmatch(r"([0-9.]+)\s*([KMGT]?i?B)?", text, flags=re.I)
    if not match:
        return 0.0
    amount = float(match.group(1))
    unit = (match.group(2) or "B").upper()
    factors = {
        "B": 1,
        "KB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
        "TB": 1000**4,
        "KIB": 1024,
        "MIB": 1024**2,
        "GIB": 1024**3,
        "TIB": 1024**4,
    }
    return amount * factors.get(unit, 1)


def delta(current: Any, previous: Any) -> float:
    return float(current or 0) - float(previous or 0)


def derive_run(run_dir: Path, duration_seconds: float, requests: int) -> dict[str, Any]:
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be > 0")
    if requests <= 0:
        raise ValueError("requests must be > 0")

    pre = load(run_dir / "pg_pre.json")
    post = load(run_dir / "pg_post.json")
    statements_pre = read_statement_csv(run_dir / "statements_pre.csv")
    statements_post = read_statement_csv(run_dir / "statements_post.csv")
    lock_samples = read_ndjson(run_dir / "lock_samples.ndjson")
    container_samples = read_ndjson(run_dir / "container_samples.ndjson")

    statement_calls = 0.0
    statement_rows = 0.0
    statement_exec_ms = 0.0
    statement_wal_bytes = 0.0
    for queryid in set(statements_pre) | set(statements_post):
        before = statements_pre.get(queryid, {})
        after = statements_post.get(queryid, {})
        statement_calls += max(0.0, delta(after.get("calls"), before.get("calls")))
        statement_rows += max(0.0, delta(after.get("rows"), before.get("rows")))
        statement_exec_ms += max(
            0.0, delta(after.get("total_exec_time"), before.get("total_exec_time"))
        )
        statement_wal_bytes += max(0.0, delta(after.get("wal_bytes"), before.get("wal_bytes")))

    connection_values = [
        int(pre.get("connections", {}).get("total", 0)),
        int(post.get("connections", {}).get("total", 0)),
        *(int(sample.get("connections_total", 0)) for sample in lock_samples),
    ]
    waiting_values = [int(sample.get("waiting_count", 0)) for sample in lock_samples]

    postgres_samples = [sample for sample in container_samples if sample.get("role") == "postgres"]
    api_samples = [sample for sample in container_samples if sample.get("role") == "api"]

    wal_pre = float(pre.get("wal", {}).get("wal_bytes", 0) or 0)
    wal_post = float(post.get("wal", {}).get("wal_bytes", 0) or 0)
    database_pre = pre.get("database", {})
    database_post = post.get("database", {})

    return {
        "duration_seconds": duration_seconds,
        "requests": requests,
        "wal_bytes_delta": wal_post - wal_pre,
        "wal_bytes_per_second": (wal_post - wal_pre) / duration_seconds,
        "db_statement_calls_delta": statement_calls,
        "db_statements_per_request": statement_calls / requests,
        "db_rows_delta": statement_rows,
        "db_rows_per_request": statement_rows / requests,
        "db_exec_time_ms_delta": statement_exec_ms,
        "db_exec_time_ms_per_request": statement_exec_ms / requests,
        "statement_wal_bytes_delta": statement_wal_bytes,
        "statement_wal_bytes_per_request": statement_wal_bytes / requests,
        "xact_commit_delta": delta(database_post.get("xact_commit"), database_pre.get("xact_commit")),
        "temp_files_delta": delta(database_post.get("temp_files"), database_pre.get("temp_files")),
        "deadlocks_delta": delta(database_post.get("deadlocks"), database_pre.get("deadlocks")),
        "database_size_bytes_delta": delta(
            post.get("database_size_bytes"), pre.get("database_size_bytes")
        ),
        "connection_high_water": max(connection_values, default=0),
        "lock_wait_samples": sum(1 for value in waiting_values if value > 0),
        "max_waiting_backends": max(waiting_values, default=0),
        "postgres_cpu_percent_max": max(
            (percent(sample.get("stats", {}).get("CPUPerc")) for sample in postgres_samples),
            default=0.0,
        ),
        "postgres_rss_bytes_max": max(
            (memory_bytes(sample.get("stats", {}).get("MemUsage")) for sample in postgres_samples),
            default=0.0,
        ),
        "postgres_process_high_water": max(
            (int(sample.get("process_count", 0)) for sample in postgres_samples), default=0
        ),
        "api_cpu_percent_max": max(
            (percent(sample.get("stats", {}).get("CPUPerc")) for sample in api_samples), default=0.0
        ),
        "api_rss_bytes_max": max(
            (memory_bytes(sample.get("stats", {}).get("MemUsage")) for sample in api_samples),
            default=0.0,
        ),
        "api_process_high_water": max(
            (int(sample.get("process_count", 0)) for sample in api_samples), default=0
        ),
    }


def command_derive_run(run_dir: str, duration_seconds: float, requests: int) -> int:
    try:
        result = derive_run(Path(run_dir), duration_seconds, requests)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    compare = sub.add_parser("compare-correctness")
    compare.add_argument("left")
    compare.add_argument("right")

    derive = sub.add_parser("derive-run")
    derive.add_argument("run_dir")
    derive.add_argument("--duration-seconds", type=float, required=True)
    derive.add_argument("--requests", type=int, required=True)

    args = parser.parse_args()
    if args.command == "compare-correctness":
        return command_compare_correctness(args.left, args.right)
    if args.command == "derive-run":
        return command_derive_run(args.run_dir, args.duration_seconds, args.requests)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
