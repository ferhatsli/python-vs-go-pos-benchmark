from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (ROOT / "db" / "001_schema.sql").read_text(encoding="utf-8").lower()


def table_body(name: str) -> str:
    return SCHEMA.split(f"create table {name}", 1)[1].split(");", 1)[0]


def test_payment_and_command_parity_tables_exist() -> None:
    for table in (
        "program_payment_methods",
        "rf_cards",
        "program_executions",
        "panel_users",
        "maintenance_windows",
    ):
        assert f"create table {table}" in SCHEMA


def test_qr_scope_and_usage_state_is_explicit() -> None:
    body = table_body("qr_codes")
    for column in (
        "token_hash",
        "company_id",
        "station_id",
        "program_id",
        "status",
        "starts_at",
        "expires_at",
        "usage_limit",
        "usage_count",
    ):
        assert column in body


def test_payment_failure_state_is_persistent() -> None:
    payment = table_body("payment_transactions")
    assert "error_code" in payment
    assert "error_message" in payment


def test_rf_wallet_and_command_state_support_contention_and_result_idempotency() -> None:
    wallet = table_body("rf_wallets")
    command = table_body("commands")
    result = table_body("command_results")
    assert "rf_card_id" in wallet
    assert "version" in wallet
    assert "program_execution_id" in command
    assert "request_hash" in result
