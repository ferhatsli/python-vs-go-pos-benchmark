#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN_ID = "track-a-20260831"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def package(raw_repo_root: Path, output_root: Path) -> None:
    summary_path = ROOT / "results" / RUN_ID / "summary.json"
    summary = load_json(summary_path)

    matrices = []
    for item in summary["workloads"]:
        source = item["matrix_summary"]
        raw_path = raw_repo_root / source
        if not raw_path.is_file():
            raise SystemExit(f"missing canonical matrix summary: {source}")
        raw = load_json(raw_path)
        record = {
            "profile": item["profile"],
            "scenario": item["workload"],
            "load_level": item["load"],
            "status": item["status"],
            "source": source,
            "evidence_class": "canonical",
            "matrix": raw,
        }
        if item["workload"] == "worker":
            worker_source = (Path(source).parent / "python" / "measured-1" / "worker-summary.json").as_posix()
            worker_path = raw_repo_root / worker_source
            if not worker_path.is_file():
                raise SystemExit(f"missing worker evidence: {worker_source}")
            worker = load_json(worker_path)
            record["worker_devices"] = int(worker["devices_evaluated"])
            record["worker_source"] = worker_source
        matrices.append(record)

    write_json(
        output_root / "matrix-summaries.json",
        {
            "run_id": RUN_ID,
            "count": len(matrices),
            "matrices": matrices,
        },
    )

    failures = summary.get("d3_canonical_failures", [])
    by_path = {entry["path"]: entry for entry in failures}
    heartbeat_path = f"results/{RUN_ID}/D3/heartbeat-level-1667/python/warmup-1"
    card_path = f"results/{RUN_ID}/D3/payment-card-level-1000/python/warmup-1"
    if heartbeat_path not in by_path or card_path not in by_path:
        raise SystemExit("missing expected D3 canonical failure evidence in summary.json")

    def capacity_record(entry: dict) -> dict:
        source_dir = entry["path"]
        raw_dir = raw_repo_root / source_dir
        required = [raw_dir / "trial.json", raw_dir / "k6-summary.json", raw_dir / "invariants.txt"]
        missing = [str(p.relative_to(raw_repo_root)) for p in required if not p.is_file()]
        if missing:
            raise SystemExit(f"missing raw D3 capacity artefacts: {missing}")
        record = dict(entry)
        record["source"] = source_dir
        record["evidence_class"] = "canonical"
        return record

    diagnostic_paths = [p for p in (raw_repo_root / "results" / RUN_ID).rglob("*") if "diagnostic" in p.as_posix().lower()]
    diagnostics: dict[str, object]
    if diagnostic_paths:
        # Numeric diagnostics are not emitted automatically. A future publisher must
        # explicitly package and validate a concrete raw diagnostic artefact first.
        diagnostics = {
            "diagnostic_numeric_claims_publishable": False,
            "reason": "Diagnostic-labelled paths exist, but no explicitly packaged and validated numeric diagnostic record is configured.",
        }
    else:
        diagnostics = {
            "diagnostic_numeric_claims_publishable": False,
            "reason": "No retained raw diagnostic artefact is available in the repository evidence set.",
        }

    write_json(
        output_root / "d3-capacity.json",
        {
            "run_id": RUN_ID,
            "heartbeat_python_1667": capacity_record(by_path[heartbeat_path]),
            "card_python_1000": capacity_record(by_path[card_path]),
            "diagnostics": diagnostics,
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Package compact public benchmark evidence.")
    parser.add_argument("--raw-repo-root", type=Path, default=ROOT)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "results" / RUN_ID / "evidence",
    )
    args = parser.parse_args()
    package(args.raw_repo_root.resolve(), args.output_root.resolve())
    print(f"PASS: packaged public evidence -> {args.output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
