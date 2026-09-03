from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "db" / "001_schema.sql"
INDEXES = ROOT / "db" / "002_indexes.sql"
EXTENSIONS = ROOT / "db" / "003_extensions.sql"
INVARIANTS = ROOT / "db" / "checks" / "invariants.sql"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8").lower()


def test_schema_contains_track_a_correctness_state() -> None:
    sql = read(SCHEMA)
    for table in (
        "payment_transactions",
        "qr_codes",
        "rf_wallets",
        "rf_wallet_ledger",
        "start_rights",
        "commands",
        "command_results",
        "devices",
        "device_credentials",
        "device_current_states",
        "device_configurations",
        "device_heartbeats",
        "alarms",
    ):
        assert f"create table {table}" in sql or f"create table if not exists {table}" in sql
    assert "unique (device_id, idempotency_key)" in sql
    assert "balance_minor >= 0" in sql
    assert "usage_count <= usage_limit" in sql


def test_indexes_include_worker_payment_and_open_alarm_paths() -> None:
    sql = read(INDEXES)
    assert "device_heartbeats" in sql
    assert "payment_transactions" in sql
    assert "where status = 'open'" in sql
    assert "alarms" in sql


def test_required_extensions_are_enabled() -> None:
    sql = read(EXTENSIONS)
    assert "pg_stat_statements" in sql
    assert "pgcrypto" in sql


def test_heartbeat_schema_preserves_frozen_event_fields() -> None:
    sql = read(SCHEMA)
    heartbeat = sql.split("create table device_heartbeats", 1)[1].split(");", 1)[0]
    for column in ("occurred_at", "received_at", "sequence", "payload"):
        assert column in heartbeat


def test_invariant_queries_cover_financial_and_command_hard_gates() -> None:
    sql = read(INVARIANTS)
    for token in (
        "payment_transactions",
        "rf_wallets",
        "qr_codes",
        "rf_wallet_ledger",
        "command_results",
        "commands",
    ):
        assert token in sql
