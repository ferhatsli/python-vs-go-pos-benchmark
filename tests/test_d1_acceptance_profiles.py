from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOAD = ROOT / "load"


def test_common_exposes_runtime_agnostic_acceptance_mode() -> None:
    common = (LOAD / "common.js").read_text(encoding="utf-8")
    assert "__ENV.BENCH_ACCEPTANCE" in common
    assert "ACCEPTANCE_DURATION" in common


def test_heartbeat_acceptance_is_exactly_17_requests_per_second() -> None:
    source = (LOAD / "heartbeat.js").read_text(encoding="utf-8")
    assert "constant-arrival-rate" in source
    assert "heartbeat_acceptance', 17" in source
    assert "ACCEPTANCE_DURATION" in source


def test_payment_acceptance_is_exactly_10_concurrent_vus() -> None:
    source = (LOAD / "payment-card.js").read_text(encoding="utf-8")
    assert "constant-vus" in source
    assert "card_acceptance', 10" in source
    assert "ACCEPTANCE_DURATION" in source


def test_dashboard_acceptance_is_exactly_10_vus() -> None:
    source = (LOAD / "dashboard.js").read_text(encoding="utf-8")
    assert "constant-vus" in source
    assert "dashboard_acceptance', 10" in source
    assert "ACCEPTANCE_DURATION" in source


def test_orchestrator_forwards_acceptance_mode_to_k6() -> None:
    source = (ROOT / "scripts" / "run_scenario.sh").read_text(encoding="utf-8")
    assert 'BENCH_ACCEPTANCE="${BENCH_ACCEPTANCE:-0}"' in source
    assert 'BENCH_ACCEPTANCE_DURATION="${BENCH_ACCEPTANCE_DURATION:-15s}"' in source
