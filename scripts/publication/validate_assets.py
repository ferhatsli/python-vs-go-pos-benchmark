#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QUANTITATIVE = [
    ROOT / "assets/charts/card-p95.svg",
    ROOT / "assets/charts/dashboard-p95.svg",
    ROOT / "assets/charts/worker.svg",
    ROOT / "assets/charts/d3-capacity.svg",
]


def validate_svg(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.is_file():
        return [f"missing asset: {path.relative_to(ROOT)}"]
    text = path.read_text(encoding="utf-8")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return [f"invalid SVG {path.relative_to(ROOT)}: {exc}"]
    if not root.tag.endswith("svg"):
        errors.append(f"not an SVG root: {path.relative_to(ROOT)}")
    try:
        width = int(float(root.attrib.get("width", "0")))
    except ValueError:
        width = 0
    if width < 1192:
        errors.append(f"SVG width below 1192px: {path.relative_to(ROOT)}")
    if "<title" not in text:
        errors.append(f"missing title: {path.relative_to(ROOT)}")
    if "<desc" not in text:
        errors.append(f"missing desc: {path.relative_to(ROOT)}")
    if "<metadata" not in text:
        errors.append(f"missing metadata: {path.relative_to(ROOT)}")
    return errors


def markdown_images(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)


def validate_markdown(path: Path) -> list[str]:
    errors: list[str] = []
    for ref in markdown_images(path):
        if ref.startswith(("http://", "https://", "/")):
            errors.append(f"image reference must be repository-relative: {path}: {ref}")
            continue
        candidate = (path.parent / ref).resolve()
        try:
            candidate.relative_to(ROOT.resolve())
        except ValueError:
            errors.append(f"image reference escapes repository: {path}: {ref}")
            continue
        if not candidate.is_file():
            errors.append(f"missing markdown image: {path}: {ref}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate publication assets and Markdown image references.")
    parser.add_argument("markdown", nargs="*", type=Path)
    args = parser.parse_args()

    errors: list[str] = []
    for asset in QUANTITATIVE:
        errors.extend(validate_svg(asset))
    for markdown in args.markdown:
        path = markdown if markdown.is_absolute() else ROOT / markdown
        if not path.is_file():
            errors.append(f"missing markdown file: {markdown}")
        else:
            errors.extend(validate_markdown(path))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("PASS: publication assets validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
