from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOAD = ROOT / "load"
SCRIPTS = ROOT / "scripts"


def test_common_exposes_numeric_benchmark_load_level() -> None:
    source = (LOAD / "common.js").read_text(encoding="utf-8")
    assert "__ENV.BENCH_LOAD_LEVEL" in source
    assert "LOAD_LEVEL" in source


def test_level_mode_uses_constant_load_without_changing_full_ramps() -> None:
    heartbeat = (LOAD / "heartbeat.js").read_text(encoding="utf-8")
    payment = (LOAD / "payment-card.js").read_text(encoding="utf-8")
    dashboard = (LOAD / "dashboard.js").read_text(encoding="utf-8")

    assert "ramping-arrival-rate" in heartbeat
    assert "constant-arrival-rate" in heartbeat
    assert "heartbeat_level', LOAD_LEVEL" in heartbeat

    assert "ramping-vus" in payment
    assert "constant-vus" in payment
    assert "card_level', LOAD_LEVEL" in payment

    assert "ramping-vus" in dashboard
    assert "constant-vus" in dashboard
    assert "dashboard_level', LOAD_LEVEL" in dashboard


def test_scenario_artifacts_are_namespaced_by_load_level() -> None:
    source = (SCRIPTS / "run_scenario.sh").read_text(encoding="utf-8")
    assert 'LOAD_LEVEL="${BENCH_LOAD_LEVEL:-}"' in source
    assert "CASE_KEY" in source
    assert "level-${LOAD_LEVEL}" in source
    assert '"load_level"' in source
    assert '-e BENCH_LOAD_LEVEL="$LOAD_LEVEL"' in source
    assert 'BENCH_LOAD_DURATION' in source


def test_matrix_accepts_optional_level_and_uses_level_specific_cv_path() -> None:
    source = (SCRIPTS / "run_matrix.sh").read_text(encoding="utf-8")
    assert 'LEVEL="${4:-}"' in source
    assert 'export BENCH_LOAD_LEVEL="$LEVEL"' in source
    assert "CASE_KEY" in source
    assert "level-${LEVEL}" in source
    assert "matrix-summary.json" in source
