from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOAD = ROOT / "load"

EXPECTED = {
    "common.js",
    "smoke.js",
    "heartbeat.js",
    "configuration.js",
    "payment-card.js",
    "payment-qr-contention.js",
    "payment-rf-contention.js",
    "dashboard.js",
    "command-lifecycle.js",
}


def source(name: str) -> str:
    return (LOAD / name).read_text(encoding="utf-8")


def test_load_profile_files_and_environment_contract() -> None:
    assert EXPECTED.issubset({p.name for p in LOAD.glob("*.js")})
    common = source("common.js")
    for variable in ("API_URL", "DATASET_PROFILE", "RUN_ID", "RUNTIME"):
        assert f"__ENV.{variable}" in common
    combined = "\n".join(source(name) for name in EXPECTED)
    assert re.search(r"if\s*\([^)]*RUNTIME", combined) is None
    assert re.search(r"switch\s*\([^)]*RUNTIME", combined) is None


def test_heartbeat_uses_canonical_arrival_rates() -> None:
    text = source("heartbeat.js")
    for rate in (17, 167, 1667, 3333):
        assert str(rate) in text
    assert "ramping-arrival-rate" in text


def test_payment_and_dashboard_use_canonical_concurrency_levels() -> None:
    payment = source("payment-card.js")
    for vus in (10, 100, 250, 500, 1000, 2000):
        assert str(vus) in payment
    dashboard = source("dashboard.js")
    for vus in (10, 50, 100, 200):
        assert str(vus) in dashboard


def test_contention_and_command_profiles_preserve_correctness_checks() -> None:
    qr = source("payment-qr-contention.js")
    rf = source("payment-rf-contention.js")
    command = source("command-lifecycle.js")
    assert "contentionDeviceId" in qr and "qrToken" in qr
    assert "contentionDeviceId" in rf and "rfUid" in rf
    assert "expectedStatuses(200, 409)" in qr
    assert "expectedStatuses(200, 409)" in rf
    assert "commands/pending" in command
    assert "/acknowledge" in command
    assert "/result" in command
    assert "duplicate" in command.lower()


def test_smoke_checks_health_and_core_device_endpoints() -> None:
    smoke = source("smoke.js")
    assert "/health" in smoke
    assert "/api/v1/device/heartbeat" in smoke
    assert "/api/v1/device/configuration" in smoke
