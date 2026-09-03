from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

REQUIRED = {f"W{i}" for i in range(1, 9)}
REQUIRED_KEYS = {"version", "workload", "endpoint", "transaction", "locking", "idempotency", "invariants", "metrics"}
PLACEHOLDER_WORDS = ("TBD", "TODO", "IMPLEMENT LATER")


def main() -> int:
    contract_dir = Path(os.environ.get("CONTRACT_DIR", "contracts"))
    if not contract_dir.exists():
        print(f"ERROR: contract directory missing: {contract_dir}", file=sys.stderr)
        return 30

    seen: dict[str, Path] = {}
    errors: list[str] = []
    for path in sorted(contract_dir.glob("*.yaml")):
        if path.name == "common.yaml":
            continue
        text = path.read_text(encoding="utf-8")
        if any(word in text.upper() for word in PLACEHOLDER_WORDS):
            errors.append(f"{path.name}: placeholder text is forbidden")
            continue
        try:
            data = yaml.safe_load(text) or {}
        except yaml.YAMLError as exc:
            errors.append(f"{path.name}: invalid YAML: {exc}")
            continue
        workload = data.get("workload")
        if workload not in REQUIRED:
            errors.append(f"{path.name}: workload must be one of {sorted(REQUIRED)}")
            continue
        if workload in seen:
            errors.append(f"{path.name}: duplicate workload {workload} (already in {seen[workload].name})")
            continue
        seen[workload] = path
        missing_keys = sorted(REQUIRED_KEYS - set(data))
        if missing_keys:
            errors.append(f"{path.name}: missing keys: {', '.join(missing_keys)}")
        invariants = data.get("invariants")
        if not isinstance(invariants, list) or not invariants:
            errors.append(f"{path.name}: invariants must be a non-empty list")
        metrics = data.get("metrics")
        if not isinstance(metrics, list) or not metrics:
            errors.append(f"{path.name}: metrics must be a non-empty list")
        endpoint = data.get("endpoint")
        if not isinstance(endpoint, dict) or not endpoint.get("method") or not endpoint.get("path"):
            errors.append(f"{path.name}: endpoint.method and endpoint.path are required")

    missing = sorted(REQUIRED - set(seen))
    if missing:
        errors.append("missing workload contracts: " + ", ".join(missing))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 31

    print("PASS: workload contracts validated 8/8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
