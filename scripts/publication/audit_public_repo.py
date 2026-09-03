#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    excerpt: str


_TEXT_SUFFIXES = {
    ".cfg",
    ".conf",
    ".csv",
    ".env",
    ".example",
    ".go",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".sql",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
_TEXT_NAMES = {"Dockerfile", "Makefile", "LICENSE", "CITATION.cff", ".gitignore"}
_EXCLUDED_DIRS = {".git", ".pytest_cache", ".worktrees", "__pycache__", ".venv"}
_EXCLUDED_NAMES = {".publication-audit.json"}
_SECRET_SCAN_SUFFIXES = {
    ".cfg",
    ".conf",
    ".env",
    ".example",
    ".ini",
    ".json",
    ".md",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}

_INTERNAL_COMPANY = "elar" + "tek"
_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("internal-company-name", re.compile(rf"\b{re.escape(_INTERNAL_COMPANY)}\b", re.IGNORECASE)),
    (
        "private-host-path",
        re.compile(
            r"(?:[A-Za-z]:\\+Users\\+[^\\\s]+(?:\\+|\b)|/mnt/[a-z]/Users/[^/\s]+(?:/|\b))",
            re.IGNORECASE,
        ),
    ),
    (
        "secret-assignment",
        re.compile(r"\b(?:password|api[_-]?key|secret|token)\s*=\s*[^\s#]+", re.IGNORECASE),
    ),
)


def _is_scannable(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    if path.name in _EXCLUDED_NAMES:
        return False
    if any(part in _EXCLUDED_DIRS for part in rel.parts):
        return False
    # Raw benchmark streams are intentionally excluded from this text audit.
    # Compact publication evidence is generated and validated separately.
    if rel.parts and rel.parts[0] == "results":
        return False
    return path.name in _TEXT_NAMES or path.suffix.lower() in _TEXT_SUFFIXES


def audit_tree(root: Path) -> list[Finding]:
    root = root.resolve()
    findings: list[Finding] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if not _is_scannable(path, root):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(root).as_posix()
        for line_no, line in enumerate(text.splitlines(), start=1):
            for rule, pattern in _RULES:
                if rule == "secret-assignment" and path.suffix.lower() not in _SECRET_SCAN_SUFFIXES:
                    continue
                match = pattern.search(line)
                if rule == "secret-assignment" and match:
                    lowered = match.group(0).lower()
                    if any(marker in lowered for marker in ("local-only", "placeholder", "example", "changeme", "dummy")):
                        match = None
                if match:
                    excerpt = line.strip()
                    if len(excerpt) > 240:
                        excerpt = excerpt[:237] + "..."
                    findings.append(Finding(rel, line_no, rule, excerpt))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit repository text for public-release blockers.")
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()

    findings = audit_tree(args.root)
    if findings:
        print(json.dumps([asdict(f) for f in findings], indent=2, ensure_ascii=False))
        return 1
    print("PASS: public repository text audit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
