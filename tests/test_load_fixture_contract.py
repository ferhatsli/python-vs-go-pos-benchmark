from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_contention_devices_skip_seeded_command_execution_range() -> None:
    common = (ROOT / "load" / "common.js").read_text(encoding="utf-8")
    assert "commandFixtureCount" in common
    assert "commandFixtureCount() + contentionIndex()" in common


def test_rf_contention_seed_wallets_have_exactly_one_purchase_balance() -> None:
    seed = (ROOT / "db" / "seed" / "seed.py").read_text(encoding="utf-8")
    assert "SELECT id, 1000, 0" in seed


def test_card_payment_devices_skip_seeded_command_execution_prefix_at_all_scales() -> None:
    common = (ROOT / "load" / "common.js").read_text(encoding="utf-8")
    card = (ROOT / "load" / "payment-card.js").read_text(encoding="utf-8")
    assert "paymentDeviceIdFor" in common
    assert "commandFixtureCount()" in common
    assert "paymentDeviceIdFor" in card
