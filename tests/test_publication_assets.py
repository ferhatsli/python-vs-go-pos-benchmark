from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
CHARTS = {
    "assets/charts/card-p95.svg": "assets/data/card-p95.csv",
    "assets/charts/dashboard-p95.svg": "assets/data/dashboard-p95.csv",
    "assets/charts/worker.svg": "assets/data/worker.csv",
    "assets/charts/d3-capacity.svg": "assets/data/d3-capacity.csv",
}


def test_quantitative_svg_contracts():
    for relative, source_csv in CHARTS.items():
        path = ROOT / relative
        text = path.read_text(encoding="utf-8")
        root = ET.fromstring(text)
        assert root.tag.endswith("svg")
        assert int(root.attrib["width"]) >= 1192
        assert "<title" in text
        assert "<desc" in text
        assert "<metadata" in text
        assert source_csv in text

import struct

STRUCTURAL = [
    "assets/diagrams/benchmark-architecture.svg",
    "assets/diagrams/dataset-scale.svg",
    "assets/diagrams/bottleneck.svg",
    "assets/diagrams/final-decision.svg",
    "assets/hero/benchmark-hero.svg",
]


def test_structural_visual_set_and_social_preview():
    for relative in STRUCTURAL:
        path = ROOT / relative
        text = path.read_text(encoding="utf-8")
        svg = ET.fromstring(text)
        assert svg.tag.endswith("svg")
        assert int(svg.attrib["width"]) >= 1192
        assert "<title" in text
        assert "<desc" in text

    png = ROOT / "assets/hero/github-social-preview.png"
    data = png.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    assert (width, height) == (1280, 640)

README_HEADINGS = [
    "TL;DR",
    "Why I Built This",
    "What Is Being Compared",
    "Benchmark Architecture",
    "Workloads and Dataset Scale",
    "Key Results",
    "D3 Findings",
    "Correctness",
    "Reproduce It",
    "Methodology",
    "Fairness and Limitations",
    "Full Report",
    "Repository Structure",
    "Citation / License",
]


def test_readme_required_headings_in_order():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    positions = []
    for heading in README_HEADINGS:
        marker = f"## {heading}"
        assert marker in text, f"missing README heading: {marker}"
        positions.append(text.index(marker))
    assert positions == sorted(positions)


def test_readme_images_are_relative_and_exist():
    from scripts.publication.validate_assets import validate_markdown

    errors = validate_markdown(ROOT / "README.md")
    assert errors == []
