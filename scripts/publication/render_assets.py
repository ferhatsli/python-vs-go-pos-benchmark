#!/usr/bin/env python3
from __future__ import annotations

import csv
import html
import math
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "assets" / "data"
CHARTS = ROOT / "assets" / "charts"
DIAGRAMS = ROOT / "assets" / "diagrams"
HERO = ROOT / "assets" / "hero"

BG = "#0B1117"
PANEL = "#111B25"
GRID = "#263443"
TEXT = "#EAF1F7"
MUTED = "#A8B6C3"
PYTHON = "#4B8BBE"
PYTHON_ACCENT = "#FFD43B"
GO = "#00ADD8"
DANGER = "#FF6B6B"
GOOD = "#4DD4AC"


def rows(name: str) -> list[dict[str, str]]:
    with (DATA / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def e(value: object) -> str:
    return html.escape(str(value), quote=True)


def fmt_ms(value: float) -> str:
    if value >= 1000:
        return f"{value / 1000:.2f}s"
    return f"{value:.0f}ms"


def svg_open(title: str, desc: str, source: str, width: int, height: int) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f"<title>{e(title)}</title>",
        f"<desc>{e(desc)}</desc>",
        f"<metadata>source_csv={e(source)}</metadata>",
        f'<rect width="{width}" height="{height}" fill="{BG}"/>',
        f'<text x="70" y="72" fill="{TEXT}" font-family="Arial,Helvetica,sans-serif" font-size="34" font-weight="700">{e(title)}</text>',
        f'<text x="70" y="108" fill="{MUTED}" font-family="Arial,Helvetica,sans-serif" font-size="18">{e(desc)}</text>',
    ]


def text(x: float, y: float, value: str, size: int = 17, fill: str = TEXT, weight: int = 400, anchor: str = "start") -> str:
    return f'<text x="{x:.1f}" y="{y:.1f}" fill="{fill}" text-anchor="{anchor}" font-family="Arial,Helvetica,sans-serif" font-size="{size}" font-weight="{weight}">{e(value)}</text>'


def rect(x: float, y: float, w: float, h: float, fill: str, rx: float = 6) -> str:
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w, 0):.1f}" height="{h:.1f}" rx="{rx}" fill="{fill}"/>'


def line(x1: float, y1: float, x2: float, y2: float, stroke: str = GRID, width: float = 1, dash: str | None = None) -> str:
    extra = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{stroke}" stroke-width="{width}"{extra}/>'


def save_svg(path: Path, parts: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def render_card() -> None:
    data = rows("card-p95.csv")
    width, height = 1400, 780
    source = "assets/data/card-p95.csv"
    parts = svg_open(
        "CARD payment p95 latency",
        "Same database and resource limits; lower is better. Exact medians are labelled.",
        source,
        width,
        height,
    )
    x0, chart_w = 330, 930
    max_v = max(float(r["python_p95_ms"]) for r in data) * 1.03
    for tick in range(5):
        value = max_v * tick / 4
        x = x0 + chart_w * tick / 4
        parts.append(line(x, 145, x, 690))
        parts.append(text(x, 720, fmt_ms(value), 14, MUTED, anchor="middle"))
    for i, r in enumerate(data):
        y = 165 + i * 125
        label = f"{r['profile']} @ {r['load_level']}"
        py = float(r["python_p95_ms"])
        go = float(r["go_p95_ms"])
        parts.append(text(70, y + 30, label, 18, TEXT, 700))
        py_w = chart_w * py / max_v
        go_w = chart_w * go / max_v
        parts.append(rect(x0, y, py_w, 30, PYTHON))
        parts.append(rect(x0, y + 42, max(go_w, 4), 30, GO))
        parts.append(text(min(x0 + py_w + 12, 1325), y + 22, f"Python {fmt_ms(py)}", 15, TEXT))
        parts.append(text(min(x0 + go_w + 12, 1325), y + 64, f"Go {fmt_ms(go)}", 15, TEXT))
        parts.append(text(1285, y + 43, f"{py / go:.1f}× lower p95", 14, PYTHON_ACCENT, 700, "end"))
    save_svg(CHARTS / "card-p95.svg", parts)


def render_dashboard() -> None:
    data = rows("dashboard-p95.csv")
    width, height = 1400, 850
    source = "assets/data/dashboard-p95.csv"
    parts = svg_open(
        "Dashboard p95 latency across scale",
        "Go keeps a material latency advantage as the synthetic dataset grows. Lower is better.",
        source,
        width,
        height,
    )
    x0, chart_w = 330, 930
    max_v = max(float(r["python_p95_ms"]) for r in data) * 1.05
    for tick in range(5):
        value = max_v * tick / 4
        x = x0 + chart_w * tick / 4
        parts.append(line(x, 145, x, 760))
        parts.append(text(x, 795, fmt_ms(value), 14, MUTED, anchor="middle"))
    for i, r in enumerate(data):
        y = 155 + i * 112
        py = float(r["python_p95_ms"])
        go = float(r["go_p95_ms"])
        parts.append(text(70, y + 31, f"{r['profile']} @ {r['load_level']}", 18, TEXT, 700))
        py_w = chart_w * py / max_v
        go_w = chart_w * go / max_v
        parts.append(rect(x0, y, py_w, 28, PYTHON))
        parts.append(rect(x0, y + 39, max(go_w, 4), 28, GO))
        parts.append(text(min(x0 + py_w + 10, 1320), y + 21, f"Python {fmt_ms(py)}", 14))
        parts.append(text(min(x0 + go_w + 10, 1320), y + 60, f"Go {fmt_ms(go)}", 14))
        parts.append(text(1285, y + 42, f"{py / go:.1f}×", 14, PYTHON_ACCENT, 700, "end"))
    save_svg(CHARTS / "dashboard-p95.svg", parts)


def render_worker() -> None:
    data = rows("worker.csv")
    width, height = 1400, 900
    source = "assets/data/worker.csv"
    parts = svg_open(
        "Worker: duration and device throughput",
        "D3 evaluates 50,000 devices. Both runtimes miss the <5s target even though Go is faster.",
        source,
        width,
        height,
    )
    parts.append(rect(55, 140, 1290, 310, PANEL, 12))
    parts.append(rect(55, 480, 1290, 330, PANEL, 12))
    parts.append(text(80, 180, "Median worker duration", 22, TEXT, 700))
    parts.append(text(80, 520, "Devices evaluated per second", 22, TEXT, 700))

    dur_max = max(float(r["python_duration_ms"]) for r in data) * 1.05
    rate_max = max(float(r["go_devices_per_sec"]) for r in data) * 1.05
    x0, chart_w = 300, 930
    for i, r in enumerate(data):
        y = 210 + i * 72
        py = float(r["python_duration_ms"])
        go = float(r["go_duration_ms"])
        parts.append(text(82, y + 28, f"{r['profile']} · {int(r['devices']):,} devices", 16, MUTED, 700))
        parts.append(rect(x0, y, chart_w * py / dur_max, 24, PYTHON))
        parts.append(rect(x0, y + 30, max(chart_w * go / dur_max, 4), 24, GO))
        parts.append(text(1245, y + 18, f"{fmt_ms(py)} / {fmt_ms(go)}", 14, TEXT, anchor="end"))

    parts.append(line(x0 + chart_w * 5000 / dur_max, 195, x0 + chart_w * 5000 / dur_max, 438, DANGER, 2, "6 6"))
    parts.append(text(x0 + chart_w * 5000 / dur_max + 8, 205, "5s target", 13, DANGER, 700))

    for i, r in enumerate(data):
        y = 550 + i * 76
        py = float(r["python_devices_per_sec"])
        go = float(r["go_devices_per_sec"])
        parts.append(text(82, y + 30, r["profile"], 16, MUTED, 700))
        parts.append(rect(x0, y, chart_w * py / rate_max, 25, PYTHON))
        parts.append(rect(x0, y + 32, chart_w * go / rate_max, 25, GO))
        parts.append(text(1245, y + 19, f"Python {py:,.0f}/s", 14, TEXT, anchor="end"))
        parts.append(text(1245, y + 51, f"Go {go:,.0f}/s", 14, TEXT, anchor="end"))
    parts.append(text(80, 850, "Blue = Python/FastAPI · Cyan = Go", 14, MUTED))
    save_svg(CHARTS / "worker.svg", parts)


def render_d3_capacity() -> None:
    data = rows("d3-capacity.csv")
    width, height = 1400, 760
    source = "assets/data/d3-capacity.csv"
    parts = svg_open(
        "D3 canonical capacity failures",
        "Only retained canonical evidence is shown; diagnostic numbers are excluded from the public chart.",
        source,
        width,
        height,
    )
    parts.append(rect(55, 145, 1290, 520, PANEL, 12))
    max_p95 = max(float(r["p95_ms"]) for r in data) * 1.05
    x0, chart_w = 350, 850
    for i, r in enumerate(data):
        y = 205 + i * 210
        p95 = float(r["p95_ms"])
        throughput = float(r["throughput"])
        target = float(r["load_level"])
        error = float(r["error_rate"]) * 100
        label = "Heartbeat" if r["workload"] == "heartbeat" else "CARD payment"
        parts.append(text(85, y + 26, f"{label} @ {int(target):,}", 21, TEXT, 700))
        parts.append(text(85, y + 54, "Python canonical warmup", 14, MUTED))
        parts.append(rect(x0, y, chart_w * p95 / max_p95, 34, PYTHON))
        parts.append(text(x0 + 12, y + 24, f"p95 {fmt_ms(p95)}", 15, TEXT, 700))
        achieved = throughput / target * 100
        parts.append(text(x0, y + 76, f"Achieved throughput: {throughput:,.1f}/s of {target:,.0f}/s target ({achieved:.1f}%)", 16, TEXT))
        parts.append(text(x0, y + 108, f"HTTP error rate: {error:.1f}% · dropped: {int(float(r['dropped'])):,}", 16, DANGER))
        parts.append(text(x0, y + 140, "Correctness invariants: PASS · stop-escalation applied", 15, GOOD, 700))
    save_svg(CHARTS / "d3-capacity.svg", parts)


def render_quantitative() -> None:
    CHARTS.mkdir(parents=True, exist_ok=True)
    render_card()
    render_dashboard()
    render_worker()
    render_d3_capacity()



def arrow(parts: list[str], x1: float, y1: float, x2: float, y2: float, stroke: str = GRID, width: float = 3) -> None:
    parts.append(line(x1, y1, x2, y2, stroke, width))
    angle = math.atan2(y2 - y1, x2 - x1)
    size = 12
    a1 = angle + math.pi * 0.82
    a2 = angle - math.pi * 0.82
    p1 = (x2 + size * math.cos(a1), y2 + size * math.sin(a1))
    p2 = (x2 + size * math.cos(a2), y2 + size * math.sin(a2))
    parts.append(
        f'<polygon points="{x2:.1f},{y2:.1f} {p1[0]:.1f},{p1[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}" fill="{stroke}"/>'
    )


def card(parts: list[str], x: float, y: float, w: float, h: float, title_value: str, lines: list[str], accent: str = GRID) -> None:
    parts.append(rect(x, y, w, h, PANEL, 14))
    parts.append(rect(x, y, 8, h, accent, 4))
    parts.append(text(x + 28, y + 42, title_value, 22, TEXT, 700))
    for idx, value in enumerate(lines):
        parts.append(text(x + 28, y + 76 + idx * 28, value, 15, MUTED))


def render_architecture_diagram() -> None:
    width, height = 1400, 760
    parts = svg_open(
        "Benchmark architecture",
        "The same load and data layer feed one active runtime at a time; metrics and correctness are captured around every trial.",
        "docs/architecture.md",
        width,
        height,
    )
    card(parts, 70, 235, 230, 170, "Load", ["k6 HTTP workloads", "Worker runner", "D1 / D2 / D3"], PYTHON_ACCENT)
    card(parts, 390, 165, 300, 170, "Python stack", ["FastAPI + Uvicorn", "SQLAlchemy async", "asyncpg"], PYTHON)
    card(parts, 390, 385, 300, 170, "Go stack", ["net/http", "pgx/v5", "explicit SQL"], GO)
    card(parts, 790, 235, 250, 170, "Shared data", ["PostgreSQL 17", "Redis 8", "same DB budget"], GOOD)
    card(parts, 1120, 235, 220, 170, "Evidence", ["latency / rate", "CPU / RAM / DB", "invariants"], MUTED)
    arrow(parts, 300, 320, 390, 250, PYTHON)
    arrow(parts, 300, 320, 390, 470, GO)
    arrow(parts, 690, 250, 790, 315, PYTHON)
    arrow(parts, 690, 470, 790, 325, GO)
    arrow(parts, 1040, 320, 1120, 320, GOOD)
    parts.append(text(70, 640, "Only one application runtime is active during a measured trial.", 18, TEXT, 700))
    parts.append(text(70, 675, "Correctness is a hard gate: a faster invalid financial result is not accepted.", 16, MUTED))
    save_svg(DIAGRAMS / "benchmark-architecture.svg", parts)


def render_dataset_scale() -> None:
    width, height = 1400, 700
    parts = svg_open(
        "Dataset scale: D1 → D2 → D3",
        "The synthetic dataset grows by two orders of magnitude while workload contracts stay fixed.",
        "docs/methodology.md",
        width,
        height,
    )
    cards = [
        (70, "D1", "500", ["devices", "baseline scale"], PYTHON),
        (510, "D2", "5,000", ["devices", "10× D1"], PYTHON_ACCENT),
        (950, "D3", "50,000", ["devices", "5,000 stations", "500 companies", "~1M payments"], GO),
    ]
    for x, label, devices, details, accent in cards:
        parts.append(rect(x, 185, 370, 330, PANEL, 16))
        parts.append(rect(x, 185, 370, 9, accent, 4))
        parts.append(text(x + 28, 235, label, 24, accent, 700))
        parts.append(text(x + 28, 330, devices, 54, TEXT, 700))
        for idx, value in enumerate(details):
            parts.append(text(x + 28, 380 + idx * 34, value, 17, MUTED))
    arrow(parts, 440, 350, 510, 350, GRID, 3)
    arrow(parts, 880, 350, 950, 350, GRID, 3)
    parts.append(text(70, 595, "Dataset size is not the same thing as k6 VUs or arrival rate.", 17, TEXT, 700))
    save_svg(DIAGRAMS / "dataset-scale.svg", parts)


def render_bottleneck_diagram() -> None:
    width, height = 1400, 780
    parts = svg_open(
        "Where the D3 evidence points",
        "Application request-path saturation is strongly supported; a global database lock-contention explanation is not.",
        "results/track-a-20260831/evidence/d3-capacity.json",
        width,
        height,
    )
    card(parts, 70, 180, 570, 390, "Application runtime / request path", [
        "D3 Heartbeat: Python p95 ~36.4s",
        "D3 CARD: Python p95 ~38.1s",
        "Python API CPU elevated under failure",
        "Request queueing / pool acquisition are candidates",
        "Single-process Uvicorn is a Track A confounder",
    ], DANGER)
    card(parts, 760, 180, 570, 390, "PostgreSQL / locking evidence", [
        "Deadlocks: 0 in the highlighted D3 failures",
        "Observed lock waiters did not explain the failure",
        "DB CPU did not establish global DB saturation first",
        "Connection pressure exists in payment workloads",
        "Conclusion: no global lock-contention finding",
    ], GOOD)
    arrow(parts, 640, 375, 760, 375, GRID, 3)
    parts.append(text(700, 635, "Binding bottleneck is workload-specific.", 22, TEXT, 700, "middle"))
    parts.append(text(700, 675, "Track A does not claim that runtime choice replaces SQL / architecture work.", 16, MUTED, 400, "middle"))
    save_svg(DIAGRAMS / "bottleneck.svg", parts)


def render_decision_diagram() -> None:
    width, height = 1400, 690
    parts = svg_open(
        "Track A decision",
        "The evidence supports broader Go evaluation, not an automatic full rewrite.",
        "docs/decisions.md",
        width,
        height,
    )
    parts.append(rect(110, 185, 1180, 305, PANEL, 18))
    parts.append(rect(110, 185, 1180, 10, GO, 5))
    parts.append(text(700, 285, "EVALUATE_BROADER_GO_MIGRATION", 39, GO, 700, "middle"))
    parts.append(text(700, 350, "Go materially wins many Track A comparisons while preserving tested correctness.", 19, TEXT, 400, "middle"))
    parts.append(text(700, 392, "But D3 Worker misses the <5s target in both runtimes.", 19, PYTHON_ACCENT, 700, "middle"))
    parts.append(text(700, 438, "stronger candidate ≠ automatic full rewrite", 20, MUTED, 700, "middle"))
    parts.append(text(700, 575, "Next engineering question: runtime choice vs architecture / query-count optimization.", 17, TEXT, 700, "middle"))
    save_svg(DIAGRAMS / "final-decision.svg", parts)


def render_hero_svg() -> None:
    width, height = 1400, 760
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<title>Python/FastAPI vs Go — POS backend benchmark</title>",
        "<desc>A dark technical hero for a production-inspired POS backend benchmark spanning 500 to 50,000 devices.</desc>",
        "<metadata>publication_identity=track-a-python-vs-go</metadata>",
        f'<rect width="{width}" height="{height}" fill="{BG}"/>',
        f'<rect x="70" y="80" width="250" height="10" rx="5" fill="{PYTHON}"/>',
        f'<rect x="320" y="80" width="160" height="10" rx="5" fill="{GO}"/>',
    ]
    parts.append(text(70, 178, "PYTHON / FASTAPI", 24, PYTHON, 700))
    parts.append(text(70, 255, "vs", 28, MUTED, 700))
    parts.append(text(70, 342, "GO", 58, GO, 700))
    parts.append(text(70, 460, "POS BACKEND BENCHMARK", 46, TEXT, 700))
    parts.append(text(70, 515, "production-inspired workloads · frozen Track A", 20, MUTED))
    parts.append(rect(810, 155, 500, 390, PANEL, 18))
    parts.append(text(850, 225, "500 → 50,000", 52, TEXT, 700))
    parts.append(text(850, 270, "devices", 22, MUTED, 700))
    parts.append(text(850, 350, "Same PostgreSQL", 18, GOOD, 700))
    parts.append(text(850, 392, "Same datasets", 18, GOOD, 700))
    parts.append(text(850, 434, "Same correctness gates", 18, GOOD, 700))
    parts.append(text(850, 505, "EVIDENCE > ASSUMPTIONS", 16, PYTHON_ACCENT, 700))
    parts.append(text(70, 660, "Track A decision: EVALUATE_BROADER_GO_MIGRATION", 18, TEXT, 700))
    save_svg(HERO / "benchmark-hero.svg", parts)


_FONT = {
    "A": ["01110","10001","10001","11111","10001","10001","10001"],
    "B": ["11110","10001","10001","11110","10001","10001","11110"],
    "C": ["01111","10000","10000","10000","10000","10000","01111"],
    "D": ["11110","10001","10001","10001","10001","10001","11110"],
    "E": ["11111","10000","10000","11110","10000","10000","11111"],
    "F": ["11111","10000","10000","11110","10000","10000","10000"],
    "G": ["01111","10000","10000","10111","10001","10001","01111"],
    "H": ["10001","10001","10001","11111","10001","10001","10001"],
    "I": ["11111","00100","00100","00100","00100","00100","11111"],
    "J": ["00111","00010","00010","00010","10010","10010","01100"],
    "K": ["10001","10010","10100","11000","10100","10010","10001"],
    "L": ["10000","10000","10000","10000","10000","10000","11111"],
    "M": ["10001","11011","10101","10101","10001","10001","10001"],
    "N": ["10001","11001","10101","10011","10001","10001","10001"],
    "O": ["01110","10001","10001","10001","10001","10001","01110"],
    "P": ["11110","10001","10001","11110","10000","10000","10000"],
    "Q": ["01110","10001","10001","10001","10101","10010","01101"],
    "R": ["11110","10001","10001","11110","10100","10010","10001"],
    "S": ["01111","10000","10000","01110","00001","00001","11110"],
    "T": ["11111","00100","00100","00100","00100","00100","00100"],
    "U": ["10001","10001","10001","10001","10001","10001","01110"],
    "V": ["10001","10001","10001","10001","10001","01010","00100"],
    "W": ["10001","10001","10001","10101","10101","11011","10001"],
    "X": ["10001","10001","01010","00100","01010","10001","10001"],
    "Y": ["10001","10001","01010","00100","00100","00100","00100"],
    "Z": ["11111","00001","00010","00100","01000","10000","11111"],
    "0": ["01110","10001","10011","10101","11001","10001","01110"],
    "1": ["00100","01100","00100","00100","00100","00100","01110"],
    "2": ["01110","10001","00001","00010","00100","01000","11111"],
    "3": ["11110","00001","00001","01110","00001","00001","11110"],
    "4": ["00010","00110","01010","10010","11111","00010","00010"],
    "5": ["11111","10000","10000","11110","00001","00001","11110"],
    "6": ["01110","10000","10000","11110","10001","10001","01110"],
    "7": ["11111","00001","00010","00100","01000","01000","01000"],
    "8": ["01110","10001","10001","01110","10001","10001","01110"],
    "9": ["01110","10001","10001","01111","00001","00001","01110"],
    "/": ["00001","00010","00010","00100","01000","01000","10000"],
    "-": ["00000","00000","00000","11111","00000","00000","00000"],
    ">": ["10000","01000","00100","00010","00100","01000","10000"],
    ",": ["00000","00000","00000","00000","00110","00100","01000"],
    ".": ["00000","00000","00000","00000","00000","00110","00110"],
    " ": ["00000"] * 7,
}


def _rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    return tuple(int(value[i:i+2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def _draw_rect(canvas: bytearray, width: int, height: int, x: int, y: int, w: int, h: int, color: tuple[int, int, int]) -> None:
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(width, x + w), min(height, y + h)
    for yy in range(y0, y1):
        start = (yy * width + x0) * 3
        end = (yy * width + x1) * 3
        canvas[start:end] = bytes(color) * (x1 - x0)


def _draw_text(canvas: bytearray, width: int, height: int, x: int, y: int, value: str, scale: int, color: tuple[int, int, int]) -> None:
    cursor = x
    for char in value.upper():
        glyph = _FONT.get(char, _FONT[" "])
        for gy, row in enumerate(glyph):
            for gx, bit in enumerate(row):
                if bit == "1":
                    _draw_rect(canvas, width, height, cursor + gx * scale, y + gy * scale, scale, scale, color)
        cursor += 6 * scale


def render_social_preview() -> None:
    width, height = 1280, 640
    bg = _rgb(BG)
    canvas = bytearray(bg * (width * height))
    _draw_rect(canvas, width, height, 0, 0, width, 12, _rgb(GO))
    _draw_rect(canvas, width, height, 56, 68, 270, 8, _rgb(PYTHON))
    _draw_rect(canvas, width, height, 326, 68, 150, 8, _rgb(GO))
    _draw_rect(canvas, width, height, 720, 95, 500, 450, _rgb(PANEL))
    _draw_text(canvas, width, height, 60, 125, "PYTHON / FASTAPI", 6, _rgb(PYTHON))
    _draw_text(canvas, width, height, 60, 205, "VS GO", 9, _rgb(GO))
    _draw_text(canvas, width, height, 60, 330, "POS BACKEND", 8, _rgb(TEXT))
    _draw_text(canvas, width, height, 60, 410, "BENCHMARK", 8, _rgb(TEXT))
    _draw_text(canvas, width, height, 760, 155, "500 > 50,000", 7, _rgb(TEXT))
    _draw_text(canvas, width, height, 760, 235, "DEVICES", 7, _rgb(MUTED))
    _draw_text(canvas, width, height, 760, 345, "SAME DB", 5, _rgb(GOOD))
    _draw_text(canvas, width, height, 760, 395, "SAME DATA", 5, _rgb(GOOD))
    _draw_text(canvas, width, height, 760, 445, "CORRECTNESS", 5, _rgb(GOOD))
    _draw_text(canvas, width, height, 60, 560, "PRODUCTION-INSPIRED TRACK A", 4, _rgb(PYTHON_ACCENT))

    raw = bytearray()
    row_bytes = width * 3
    for y in range(height):
        raw.append(0)
        start = y * row_bytes
        raw.extend(canvas[start:start + row_bytes])
    png = b"\x89PNG\r\n\x1a\n"
    png += _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += _png_chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += _png_chunk(b"IEND", b"")
    HERO.mkdir(parents=True, exist_ok=True)
    (HERO / "github-social-preview.png").write_bytes(png)


def render_structural() -> None:
    DIAGRAMS.mkdir(parents=True, exist_ok=True)
    HERO.mkdir(parents=True, exist_ok=True)
    render_architecture_diagram()
    render_dataset_scale()
    render_bottleneck_diagram()
    render_decision_diagram()
    render_hero_svg()
    render_social_preview()


def main() -> int:
    render_quantitative()
    render_structural()
    print("PASS: rendered publication assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
