from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOAD = ROOT / "load"
RUNNABLE = [
    "smoke.js",
    "heartbeat.js",
    "configuration.js",
    "payment-card.js",
    "payment-qr-contention.js",
    "payment-rf-contention.js",
    "dashboard.js",
    "command-lifecycle.js",
]


def test_every_load_profile_has_a_hard_check_threshold() -> None:
    for name in RUNNABLE:
        text = (LOAD / name).read_text(encoding="utf-8")
        assert "thresholds" in text, name
        assert "rate==1" in text, name


def test_contention_profiles_require_exactly_one_success() -> None:
    qr = (LOAD / "payment-qr-contention.js").read_text(encoding="utf-8")
    rf = (LOAD / "payment-rf-contention.js").read_text(encoding="utf-8")
    assert "Counter" in qr and "qr_successes" in qr and "count==1" in qr
    assert "Counter" in rf and "rf_successes" in rf and "count==1" in rf


def test_non_contention_profiles_emit_checks() -> None:
    for name in ("heartbeat.js", "configuration.js", "payment-card.js", "dashboard.js"):
        text = (LOAD / name).read_text(encoding="utf-8")
        assert "check(" in text, name
