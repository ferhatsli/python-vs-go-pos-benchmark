from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_json(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_public_evidence_contains_all_canonical_matrix_summaries():
    payload = load_json("results/track-a-20260831/evidence/matrix-summaries.json")
    assert len(payload["matrices"]) == 19
    assert all(item["evidence_class"] == "canonical" for item in payload["matrices"])
    assert all(not item["source"].startswith(("/", "C:")) for item in payload["matrices"])


def test_d3_capacity_evidence_marks_evidence_class():
    payload = load_json("results/track-a-20260831/evidence/d3-capacity.json")
    assert payload["heartbeat_python_1667"]["evidence_class"] == "canonical"
    assert payload["card_python_1000"]["evidence_class"] == "canonical"


def test_diagnostic_numbers_require_retained_raw_source():
    payload = load_json("results/track-a-20260831/evidence/d3-capacity.json")
    if not payload["diagnostics"]["diagnostic_numeric_claims_publishable"]:
        assert "numeric_records" not in payload["diagnostics"]
        assert payload["diagnostics"]["reason"]

import csv
import math


def load_csv(relative: str):
    with (ROOT / relative).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_publication_csv_schemas():
    expected = {
        "assets/data/card-p95.csv": ["profile", "load_level", "python_p95_ms", "go_p95_ms", "python_rps", "go_rps", "status"],
        "assets/data/dashboard-p95.csv": ["profile", "load_level", "python_p95_ms", "go_p95_ms", "python_rps", "go_rps", "status"],
        "assets/data/worker.csv": ["profile", "devices", "python_duration_ms", "go_duration_ms", "python_devices_per_sec", "go_devices_per_sec", "python_overrun_5s", "go_overrun_5s", "status"],
        "assets/data/d3-capacity.csv": ["workload", "runtime", "load_level", "p95_ms", "throughput", "error_rate", "dropped", "evidence_class", "publishable"],
    }
    for path, fields in expected.items():
        rows = load_csv(path)
        assert rows
        assert list(rows[0].keys()) == fields


def _row(path: str, **match):
    for row in load_csv(path):
        if all(row[key] == str(value) for key, value in match.items()):
            return row
    raise AssertionError(f"missing row in {path}: {match}")


def test_representative_publication_facts():
    card = _row("assets/data/card-p95.csv", profile="D1", load_level=100)
    assert math.isclose(float(card["python_p95_ms"]), 2960.14, rel_tol=0.001)
    assert math.isclose(float(card["go_p95_ms"]), 155.82, rel_tol=0.001)

    dashboard = _row("assets/data/dashboard-p95.csv", profile="D3", load_level=100)
    assert math.isclose(float(dashboard["python_p95_ms"]), 2455.95, rel_tol=0.001)
    assert math.isclose(float(dashboard["go_p95_ms"]), 512.08, rel_tol=0.001)

    worker = _row("assets/data/worker.csv", profile="D3")
    assert int(worker["devices"]) == 50000
    assert math.isclose(float(worker["python_duration_ms"]), 27000.34, rel_tol=0.001)
    assert math.isclose(float(worker["go_duration_ms"]), 10149.22, rel_tol=0.001)
    assert worker["python_overrun_5s"] == "true"
    assert worker["go_overrun_5s"] == "true"


def test_d3_capacity_csv_contains_only_publishable_evidence():
    rows = load_csv("assets/data/d3-capacity.csv")
    assert {row["runtime"] for row in rows} == {"python"}
    assert {row["evidence_class"] for row in rows} == {"canonical"}
    assert {row["publishable"] for row in rows} == {"true"}


def test_worker_dataset_size_is_preserved_from_raw_evidence():
    payload = load_json("results/track-a-20260831/evidence/matrix-summaries.json")
    workers = {item["profile"]: item for item in payload["matrices"] if item["scenario"] == "worker"}
    assert workers["D1"]["worker_devices"] == 500
    assert workers["D2"]["worker_devices"] == 5000
    assert workers["D3"]["worker_devices"] == 50000
    assert all(item["worker_source"].endswith("worker-summary.json") for item in workers.values())

from scripts.publication.validate_claims import validate_markdown


def test_rejects_unqualified_language_war_claim(tmp_path):
    path = tmp_path / "article.md"
    path.write_text("Go is 19x faster than Python.\n", encoding="utf-8")
    errors = validate_markdown(path)
    assert any(error.rule == "unqualified-performance-claim" for error in errors)


def test_accepts_workload_bound_claim(tmp_path):
    path = tmp_path / "article.md"
    path.write_text(
        "At CARD @100, median p95 dropped from ~2.96s on the Python stack "
        "to ~156ms on the Go stack — roughly a 19x latency difference.\n",
        encoding="utf-8",
    )
    assert not [error for error in validate_markdown(path) if error.rule == "unqualified-performance-claim"]


def test_rejects_numeric_p99_claim(tmp_path):
    path = tmp_path / "article.md"
    path.write_text("CARD p99 was 420ms.\n", encoding="utf-8")
    errors = validate_markdown(path)
    assert any(error.rule == "unsupported-p99" for error in errors)


def test_rejects_production_identical_wording(tmp_path):
    path = tmp_path / "article.md"
    path.write_text("This reproduces our production workload.\n", encoding="utf-8")
    errors = validate_markdown(path)
    assert any(error.rule == "production-identical-wording" for error in errors)


def test_rejects_numeric_diagnostic_claim_when_not_publishable(tmp_path):
    path = tmp_path / "article.md"
    path.write_text("A diagnostic run reached 1,368 req/s.\n", encoding="utf-8")
    errors = validate_markdown(path)
    assert any(error.rule == "unpublishable-diagnostic-number" for error in errors)


def test_accepts_p99_not_captured_statement(tmp_path):
    path = tmp_path / "article.md"
    path.write_text("Stored k6 summaries do not include p99. No p99 value is inferred or published.\n", encoding="utf-8")
    errors = validate_markdown(path)
    assert not [error for error in errors if error.rule == "unsupported-p99"]


def test_medium_article_structure_contract():
    path = ROOT / "docs/publication/medium-article.md"
    text = path.read_text(encoding="utf-8")
    required = [
        "I Knew Go Would Be Faster. I Wanted to Know by How Much.",
        "production-inspired POS",
        "Frozen Track A",
        "D1, D2, and D3",
        "CARD",
        "D3 Heartbeat",
        "D3 CARD",
        "Dashboard",
        "Worker",
        "Correctness",
        "Fairness",
        "What This Benchmark Does Not Prove",
        "EVALUATE_BROADER_GO_MIGRATION",
        "Track B",
        "GitHub",
    ]
    for needle in required:
        assert needle in text, f"missing Medium article requirement: {needle}"
    assert "Figure caption:" in text
    assert "Alt text:" in text


def test_launch_copy_finalizer_replaces_verified_link_tokens():
    from scripts.publication.finalize_launch_copy import finalize_copy

    source = "Medium: {{MEDIUM_URL}}\nGitHub: {{GITHUB_URL}}\n"
    result = finalize_copy(source, "https://medium.com/example", "https://github.com/example/repo")
    assert "https://medium.com/example" in result
    assert "https://github.com/example/repo" in result
    assert "{{MEDIUM_URL}}" not in result
    assert "{{GITHUB_URL}}" not in result


def test_launch_copy_finalizer_rejects_non_https_urls():
    from scripts.publication.finalize_launch_copy import finalize_copy

    source = "Medium: {{MEDIUM_URL}}\nGitHub: {{GITHUB_URL}}\n"
    import pytest
    with pytest.raises(ValueError, match="HTTPS"):
        finalize_copy(source, "http://medium.com/example", "https://github.com/example/repo")
