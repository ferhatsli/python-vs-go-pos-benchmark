#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN_ROOT = ROOT / "results" / "track-a-20260831"
DATA_ROOT = ROOT / "assets" / "data"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def fmt(value: object) -> object:
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return value


def main() -> int:
    summary = load_json(RUN_ROOT / "summary.json")
    compact = load_json(RUN_ROOT / "evidence" / "matrix-summaries.json")
    worker_evidence = {
        item["profile"]: item
        for item in compact.get("matrices", [])
        if item.get("scenario") == "worker"
    }
    workloads = summary.get("workloads")
    if not isinstance(workloads, list) or len(workloads) != 19:
        raise SystemExit("expected 19 normalized workloads in summary.json")

    profile_order = {"D1": 1, "D2": 2, "D3": 3}

    def paired_rows(workload_name: str) -> list[dict[str, object]]:
        selected = [w for w in workloads if w["workload"] == workload_name]
        selected.sort(key=lambda w: (profile_order[w["profile"]], int(w["load"])))
        rows = []
        for w in selected:
            py = w["runtime"]["python"]
            go = w["runtime"]["go"]
            rows.append(
                {
                    "profile": w["profile"],
                    "load_level": w["load"],
                    "python_p95_ms": fmt(py["p95_ms"]),
                    "go_p95_ms": fmt(go["p95_ms"]),
                    "python_rps": fmt(py["throughput"]),
                    "go_rps": fmt(go["throughput"]),
                    "status": w["status"],
                }
            )
        return rows

    write_csv(
        DATA_ROOT / "card-p95.csv",
        ["profile", "load_level", "python_p95_ms", "go_p95_ms", "python_rps", "go_rps", "status"],
        paired_rows("payment-card"),
    )
    write_csv(
        DATA_ROOT / "dashboard-p95.csv",
        ["profile", "load_level", "python_p95_ms", "go_p95_ms", "python_rps", "go_rps", "status"],
        paired_rows("dashboard"),
    )

    worker_rows = []
    for w in sorted((x for x in workloads if x["workload"] == "worker"), key=lambda x: profile_order[x["profile"]]):
        py = w["runtime"]["python"]
        go = w["runtime"]["go"]
        evidence = worker_evidence.get(w["profile"])
        if not evidence or "worker_devices" not in evidence:
            raise SystemExit(f"missing compact worker dataset evidence for {w['profile']}")
        worker_rows.append(
            {
                "profile": w["profile"],
                "devices": int(evidence["worker_devices"]),
                "python_duration_ms": fmt(py["p95_ms"]),
                "go_duration_ms": fmt(go["p95_ms"]),
                "python_devices_per_sec": fmt(py["throughput"]),
                "go_devices_per_sec": fmt(go["throughput"]),
                "python_overrun_5s": str(float(py["p95_ms"]) > 5000).lower(),
                "go_overrun_5s": str(float(go["p95_ms"]) > 5000).lower(),
                "status": w["status"],
            }
        )
    write_csv(
        DATA_ROOT / "worker.csv",
        [
            "profile",
            "devices",
            "python_duration_ms",
            "go_duration_ms",
            "python_devices_per_sec",
            "go_devices_per_sec",
            "python_overrun_5s",
            "go_overrun_5s",
            "status",
        ],
        worker_rows,
    )

    capacity = load_json(RUN_ROOT / "evidence" / "d3-capacity.json")
    capacity_rows = []
    for key, workload in (("heartbeat_python_1667", "heartbeat"), ("card_python_1000", "payment-card")):
        entry = capacity.get(key)
        if not entry:
            raise SystemExit(f"missing capacity evidence: {key}")
        capacity_rows.append(
            {
                "workload": workload,
                "runtime": entry["runtime"],
                "load_level": entry["load"],
                "p95_ms": fmt(entry["p95_ms"]),
                "throughput": fmt(entry["throughput"]),
                "error_rate": fmt(entry["error_rate"]),
                "dropped": entry["dropped"],
                "evidence_class": entry["evidence_class"],
                "publishable": "true",
            }
        )

    diagnostics = capacity.get("diagnostics", {})
    if diagnostics.get("diagnostic_numeric_claims_publishable"):
        for entry in diagnostics.get("numeric_records", []):
            if not entry.get("source"):
                raise SystemExit("publishable diagnostic record missing raw source")
            capacity_rows.append(
                {
                    "workload": entry["workload"],
                    "runtime": entry["runtime"],
                    "load_level": entry["load_level"],
                    "p95_ms": fmt(entry["p95_ms"]),
                    "throughput": fmt(entry["throughput"]),
                    "error_rate": fmt(entry["error_rate"]),
                    "dropped": entry["dropped"],
                    "evidence_class": "diagnostic",
                    "publishable": "true",
                }
            )

    write_csv(
        DATA_ROOT / "d3-capacity.csv",
        ["workload", "runtime", "load_level", "p95_ms", "throughput", "error_rate", "dropped", "evidence_class", "publishable"],
        capacity_rows,
    )

    print(f"PASS: publication chart data -> {DATA_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
