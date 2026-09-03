#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DISCLAIMER = (
    "This benchmark compares these two frozen application stacks under these workloads. "
    "It does not measure the theoretical performance limit of either Python or Go."
)


@dataclass(frozen=True)
class ClaimError:
    path: str
    line: int
    rule: str
    excerpt: str


def _diagnostics_publishable() -> bool:
    path = ROOT / "results" / "track-a-20260831" / "evidence" / "d3-capacity.json"
    if not path.is_file():
        return False
    payload = json.loads(path.read_text(encoding="utf-8"))
    return bool(payload.get("diagnostics", {}).get("diagnostic_numeric_claims_publishable", False))


def validate_markdown(path: Path) -> list[ClaimError]:
    text = path.read_text(encoding="utf-8")
    errors: list[ClaimError] = []
    diagnostics_publishable = _diagnostics_publishable()

    for lineno, line in enumerate(text.splitlines(), start=1):
        lower = line.lower()
        if re.search(r"\bgo\s+is\s+(?:roughly\s+|about\s+|~)?\d+(?:\.\d+)?\s*[x×]\s+faster\s+than\s+python\b", line, re.IGNORECASE):
            errors.append(ClaimError(str(path), lineno, "unqualified-performance-claim", line.strip()))

        if re.search(r"\bp99\b\s*(?:(?:was|is|of)\s+|[:=]\s*)?~?\d", line, re.IGNORECASE):
            errors.append(ClaimError(str(path), lineno, "unsupported-p99", line.strip()))

        if "production workload" in lower and "production-inspired" not in lower:
            errors.append(ClaimError(str(path), lineno, "production-identical-wording", line.strip()))

        if not diagnostics_publishable and re.search(r"diagnostic[^\n]*\d", line, re.IGNORECASE):
            errors.append(ClaimError(str(path), lineno, "unpublishable-diagnostic-number", line.strip()))

    if path.name in {"README.md", "medium-article.md"} and DISCLAIMER not in text:
        errors.append(ClaimError(str(path), 0, "missing-fairness-disclaimer", DISCLAIMER))

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate public benchmark claims.")
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()

    errors: list[ClaimError] = []
    for path in args.paths:
        errors.extend(validate_markdown(path))

    if errors:
        for error in errors:
            print(f"{error.path}:{error.line}: {error.rule}: {error.excerpt}")
        return 1

    print("PASS: public benchmark claims validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
